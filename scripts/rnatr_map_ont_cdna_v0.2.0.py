#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

VERSION = "rnatr_map_ont_cdna_v0.2.0"
PROFILE_VERSION = "rnatr_ont_cdna_validated_profile_v0.2.0"
DEFAULT_PROFILE = Path("config/mapping/ont_cdna_v0.2.0/validated_profile.json")


class MappingError(RuntimeError):
    pass


def sha256_file(path: Path, chunk: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def ensure_regular(path: Path) -> None:
    if not path.is_file() or path.is_symlink():
        raise MappingError(f"required regular file missing/invalid: {path}")


def load_profile(path: Path) -> dict:
    ensure_regular(path)
    obj = json.loads(path.read_text(encoding="utf-8"))
    if obj.get("profile_version") != PROFILE_VERSION:
        raise MappingError("unsupported validated profile")
    return obj


def tool_version(exe: str) -> str:
    resolved = shutil.which(exe)
    if not resolved:
        raise MappingError(f"required executable missing: {exe}")
    proc = subprocess.run(
        [resolved, "--version"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if proc.returncode != 0:
        raise MappingError(f"{exe} --version failed")
    return proc.stdout.strip().splitlines()[0]


def resolve_path(
    explicit: Path | None,
    *,
    resource_root: Path,
    profile_entry: dict,
    required: bool,
) -> Path | None:
    if explicit is not None:
        p = explicit.resolve()
    else:
        rel = Path(str(profile_entry.get("relative_path", "")))
        if rel.is_absolute() or ".." in rel.parts or not rel.parts:
            raise MappingError(f"unsafe profile resource path: {rel}")
        p = (resource_root / rel).resolve()
    if required:
        ensure_regular(p)
    elif not p.is_file():
        return None
    return p


def fasta_lengths_from_fai(path: Path) -> dict[str, int]:
    lengths: dict[str, int] = {}
    with path.open("r", encoding="utf-8", newline="") as fh:
        for line_number, raw in enumerate(fh, 1):
            if not raw.strip():
                continue
            fields = raw.rstrip("\n").split("\t")
            if len(fields) < 2:
                raise MappingError(f"invalid FAI line {line_number}: {path}")
            name = fields[0]
            try:
                length = int(fields[1])
            except ValueError as exc:
                raise MappingError(f"invalid FAI length line {line_number}") from exc
            if name in lengths:
                raise MappingError(f"duplicate FAI contig: {name}")
            lengths[name] = length
    if not lengths:
        raise MappingError(f"empty FAI: {path}")
    return lengths


def fasta_lengths_by_scan(path: Path) -> dict[str, int]:
    lengths: dict[str, int] = {}
    current: str | None = None
    n = 0
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", errors="strict", newline="") as fh:
        for raw in fh:
            if raw.startswith(">"):
                if current is not None:
                    lengths[current] = n
                current = raw[1:].strip().split()[0]
                if not current or current in lengths:
                    raise MappingError(f"invalid/duplicate FASTA contig: {current!r}")
                n = 0
            else:
                if current is None:
                    raise MappingError("FASTA sequence encountered before header")
                n += len(raw.strip())
    if current is not None:
        lengths[current] = n
    if not lengths:
        raise MappingError(f"empty FASTA: {path}")
    return lengths


def get_reference_lengths(fasta: Path, fai: Path | None) -> tuple[dict[str, int], str]:
    if fai is not None:
        return fasta_lengths_from_fai(fai), "FAI"
    return fasta_lengths_by_scan(fasta), "FASTA_STREAM_SCAN"


def iter_bed_intervals(path: Path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", errors="replace", newline="") as fh:
        for line_number, raw in enumerate(fh, 1):
            if not raw.strip() or raw.startswith("#") or raw.startswith("track") or raw.startswith("browser"):
                continue
            fields = raw.rstrip("\n").split("\t")
            if len(fields) < 3:
                raise MappingError(f"BED line has <3 columns: {path}:{line_number}")
            try:
                start = int(fields[1])
                end = int(fields[2])
            except ValueError as exc:
                raise MappingError(f"BED coordinates invalid: {path}:{line_number}") from exc
            if start < 0 or end <= start:
                raise MappingError(f"BED interval invalid: {path}:{line_number}")
            yield line_number, fields[0], start, end


def check_coordinate_compatibility(
    lengths: dict[str, int],
    bed: Path,
    *,
    label: str,
    max_examples: int = 20,
) -> dict:
    total = 0
    missing_contig = 0
    out_of_bounds = 0
    examples: list[str] = []
    for line_number, chrom, start, end in iter_bed_intervals(bed):
        total += 1
        if chrom not in lengths:
            missing_contig += 1
            if len(examples) < max_examples:
                examples.append(f"{label}:{line_number}:missing_contig:{chrom}:{start}-{end}")
            continue
        if end > lengths[chrom]:
            out_of_bounds += 1
            if len(examples) < max_examples:
                examples.append(
                    f"{label}:{line_number}:out_of_bounds:{chrom}:{start}-{end}>len={lengths[chrom]}"
                )
    status = "PASS" if total > 0 and missing_contig == 0 and out_of_bounds == 0 else "FAIL"
    return {
        "label": label,
        "bed": str(bed),
        "intervals": total,
        "missing_contig_intervals": missing_contig,
        "out_of_bounds_intervals": out_of_bounds,
        "examples": examples,
        "status": status,
    }


def classify_exact(path: Path | None, profile_entry: dict) -> dict:
    if path is None:
        return {
            "path": "",
            "sha256": "",
            "validated_sha256": profile_entry.get("sha256", ""),
            "profile_status": "NOT_SUPPLIED",
        }
    actual = sha256_file(path)
    expected = str(profile_entry.get("sha256", ""))
    return {
        "path": str(path),
        "sha256": actual,
        "validated_sha256": expected,
        "profile_status": "VALIDATED_EXACT" if actual == expected else "CUSTOM",
    }


def atomic_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmpname = tempfile.mkstemp(
        prefix="." + path.name + ".", suffix=".part", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=2, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmpname, path)
    finally:
        if os.path.exists(tmpname):
            os.unlink(tmpname)


def build_mmi(fasta: Path, out_mmi: Path) -> None:
    proc = subprocess.run(
        ["minimap2", "-d", str(out_mmi), str(fasta)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if proc.returncode != 0:
        raise MappingError("minimap2 index build failed:\n" + proc.stdout)
    ensure_regular(out_mmi)


def inspect_resources(args: argparse.Namespace, *, for_run: bool) -> tuple[dict, dict[str, Path | None]]:
    project_root = args.project_root.resolve()
    resource_root = args.resource_root.resolve() if args.resource_root else project_root
    profile_path = (
        args.validated_profile.resolve()
        if args.validated_profile
        else project_root / DEFAULT_PROFILE
    )
    profile = load_profile(profile_path)
    r = profile["resources"]

    fasta = resolve_path(
        args.reference_fasta,
        resource_root=resource_root,
        profile_entry=r["reference_fasta"],
        required=True,
    )
    assert fasta is not None

    # Classify the FASTA before resolving derived resources.
    # A custom FASTA must never silently inherit the validated FASTA's FAI/MMI.
    fasta_state = classify_exact(fasta, r["reference_fasta"])
    fasta_is_validated = fasta_state["profile_status"] == "VALIDATED_EXACT"

    if fasta_is_validated:
        if args.reference_fai is not None:
            fai = resolve_path(
                args.reference_fai,
                resource_root=resource_root,
                profile_entry=r["reference_fai"],
                required=True,
            )
            fai_guard = classify_exact(fai, r["reference_fai"])
            if fai_guard["profile_status"] != "VALIDATED_EXACT":
                raise MappingError(
                    "A custom FAI cannot be used with the exact validated FASTA "
                    "in v0.2 because its binding to that FASTA is not independently "
                    "verified. Omit --reference-fai or use the exact validated FAI."
                )
            fai_resolution = "USER_SUPPLIED_VALIDATED_EXACT"
        else:
            fai = resolve_path(
                None,
                resource_root=resource_root,
                profile_entry=r["reference_fai"],
                required=False,
            )
            fai_resolution = "VALIDATED_DEFAULT_IF_PRESENT"
    else:
        if args.reference_fai is not None:
            raise MappingError(
                "Custom FASTA compatibility is evaluated from the FASTA itself. "
                "Custom --reference-fai is not accepted in v0.2 because its binding "
                "to the FASTA cannot be independently verified. Omit --reference-fai; "
                "the FASTA will be scanned read-only."
            )
        fai = None
        fai_resolution = "FASTA_STREAM_SCAN_FOR_CUSTOM_FASTA"

    junction = resolve_path(
        args.junction_bed,
        resource_root=resource_root,
        profile_entry=r["junction_bed12"],
        required=True,
    )
    assert junction is not None

    if args.compatibility_bed is not None:
        raise MappingError(
            "Custom --compatibility-bed is not accepted by the v0.2 reference "
            "compatibility path. Reference compatibility must be evaluated against "
            "the frozen validated RNA-TR-Scout mapping-target catalog. Custom "
            "TRExplorer/STRchive catalogs require the separate post-Freeze catalog "
            "adapter and validator."
        )
    compatibility_bed = resolve_path(
        None,
        resource_root=resource_root,
        profile_entry=r["compatibility_bed"],
        required=True,
    )
    assert compatibility_bed is not None

    explicit_mmi = args.reference_mmi is not None
    if explicit_mmi:
        requested_mmi = resolve_path(
            args.reference_mmi,
            resource_root=resource_root,
            profile_entry=r["reference_mmi"],
            required=True,
        )
        mmi_guard = classify_exact(requested_mmi, r["reference_mmi"])
        if (
            not fasta_is_validated
            or mmi_guard["profile_status"] != "VALIDATED_EXACT"
        ):
            raise MappingError(
                "Custom/unbound MMI is not accepted in v0.2 because an MMI cannot "
                "be independently bound to the supplied FASTA from the index alone. "
                "Omit --reference-mmi; RNA-TR-Scout will build a run-local MMI from "
                "the active custom FASTA."
            )
        mmi = requested_mmi
        mmi_resolution = "USER_SUPPLIED_VALIDATED_EXACT"
    elif fasta_is_validated:
        mmi = resolve_path(
            None,
            resource_root=resource_root,
            profile_entry=r["reference_mmi"],
            required=False,
        )
        mmi_resolution = "VALIDATED_DEFAULT_IF_PRESENT"
    else:
        # Never combine a custom FASTA with an unbound prebuilt MMI.
        mmi = None
        mmi_resolution = "BUILD_RUN_LOCAL_FROM_CUSTOM_FASTA"

    lengths, length_source = get_reference_lengths(fasta, fai)
    target_check = check_coordinate_compatibility(
        lengths, compatibility_bed, label="mapping_target_catalog"
    )
    junction_check = check_coordinate_compatibility(
        lengths, junction, label="splice_junction_bed12"
    )
    if target_check["status"] != "PASS" or junction_check["status"] != "PASS":
        raise MappingError(
            "reference coordinate system is incompatible with required mapping/catalog intervals"
        )

    mm_version = tool_version("minimap2")
    sam_version = tool_version("samtools")
    validated_mm = profile["tools"]["minimap2"]["validated_version"]
    validated_sam_prefix = profile["tools"]["samtools"]["validated_version_prefix"]
    mm_status = "VALIDATED_TOOL_VERSION" if mm_version == validated_mm else "CUSTOM_TOOL_VERSION"
    sam_status = "VALIDATED_TOOL_VERSION" if sam_version.startswith(validated_sam_prefix) else "CUSTOM_TOOL_VERSION"

    resource_states = {
        "reference_fasta": fasta_state,
        "reference_fai": classify_exact(fai, r["reference_fai"]),
        "junction_bed12": classify_exact(junction, r["junction_bed12"]),
        "compatibility_bed": classify_exact(compatibility_bed, r["compatibility_bed"]),
        "reference_mmi": classify_exact(mmi, r["reference_mmi"]),
    }

    all_validated = (
        resource_states["reference_fasta"]["profile_status"] == "VALIDATED_EXACT"
        and resource_states["reference_fai"]["profile_status"] in {"VALIDATED_EXACT", "NOT_SUPPLIED"}
        and resource_states["junction_bed12"]["profile_status"] == "VALIDATED_EXACT"
        and resource_states["compatibility_bed"]["profile_status"] == "VALIDATED_EXACT"
        and resource_states["reference_mmi"]["profile_status"] == "VALIDATED_EXACT"
        and mm_status == "VALIDATED_TOOL_VERSION"
        and sam_status == "VALIDATED_TOOL_VERSION"
    )

    profile_status = (
        "VALIDATED_PROFILE"
        if all_validated
        else "CUSTOM_GRCH38_COMPATIBLE"
    )

    mmi_plan = "USE_SUPPLIED_OR_VALIDATED_MMI"
    if mmi is None:
        mmi_plan = "BUILD_RUN_LOCAL_MMI"
    elif not explicit_mmi and mm_status != "VALIDATED_TOOL_VERSION":
        # Avoid silently coupling an unvalidated minimap2 version to the validated prebuilt MMI.
        mmi_plan = "BUILD_RUN_LOCAL_MMI"

    report = {
        "mapping_entry_version": VERSION,
        "validated_profile_version": PROFILE_VERSION,
        "validated_profile_name": profile["profile_name"],
        "profile_status": profile_status,
        "golden_validation_scope": profile_status == "VALIDATED_PROFILE",
        "validated_assembly_family": profile["validated_scope"]["assembly_family"],
        "assembly_compatibility": "GRCH38_TARGET_COORDINATE_COMPATIBLE",
        "assembly_identity_proven": profile_status == "VALIDATED_PROFILE",
        "reference_length_source": length_source,
        "reference_contigs": len(lengths),
        "reference_fai_resolution": fai_resolution,
        "reference_mmi_resolution": mmi_resolution,
        "tools": {
            "minimap2": {
                "actual_version": mm_version,
                "validated_version": validated_mm,
                "profile_status": mm_status,
            },
            "samtools": {
                "actual_version": sam_version,
                "validated_version_prefix": validated_sam_prefix,
                "profile_status": sam_status,
            },
        },
        "resources": resource_states,
        "compatibility_checks": {
            "mapping_target_catalog": target_check,
            "splice_junction_bed12": junction_check,
        },
        "mmi_plan": mmi_plan,
        "custom_resource_execution_allowed": True,
        "warnings": [],
    }

    if profile_status != "VALIDATED_PROFILE":
        report["warnings"].append(
            "Execution is outside exact golden-validation scope; actual resource/tool provenance will be recorded."
        )
    if not fasta_is_validated:
        report["warnings"].append(
            "Custom FASTA compatibility was evaluated from the FASTA itself; "
            "RNA-TR-Scout will not use an unverified custom FAI or prebuilt MMI "
            "as compatibility evidence in v0.2."
        )
    if profile_status != "VALIDATED_PROFILE":
        report["warnings"].append(
            "GRCh38 target-coordinate compatibility does not by itself prove assembly identity; this run is recorded as a compatible custom profile."
        )

    paths: dict[str, Path | None] = {
        "fasta": fasta,
        "fai": fai,
        "junction": junction,
        "compatibility_bed": compatibility_bed,
        "mmi": mmi,
        "profile_path": profile_path,
    }
    return report, paths


def self_test() -> int:
    with tempfile.TemporaryDirectory(prefix="rnatr_map_v020_selftest_") as td:
        root = Path(td)
        fasta = root / "ref.fa"
        fai = root / "ref.fa.fai"
        bed_ok = root / "ok.bed"
        bed_bad = root / "bad.bed"
        fasta.write_text(">chr1\nAAAAAA\n>chr2\nCCCC\n", encoding="utf-8")
        fai.write_text("chr1\t6\t6\t6\t7\nchr2\t4\t19\t4\t5\n", encoding="utf-8")
        bed_ok.write_text("chr1\t0\t6\nchr2\t1\t4\n", encoding="utf-8")
        bed_bad.write_text("chr1\t0\t7\n", encoding="utf-8")
        lengths = fasta_lengths_from_fai(fai)
        ok = check_coordinate_compatibility(lengths, bed_ok, label="ok")
        bad = check_coordinate_compatibility(lengths, bed_bad, label="bad")
        if ok["status"] != "PASS" or bad["status"] != "FAIL":
            raise MappingError("compatibility self-test failed")
        if classify_exact(fasta, {"sha256": "0" * 64})["profile_status"] != "CUSTOM":
            raise MappingError("custom-profile self-test failed")
    print("SELF_TEST\tPASS")
    print(f"version\t{VERSION}")
    print("policy\tSHA_AND_VERSION_IDENTIFY_VALIDATED_PROFILE_NOT_GENERAL_PERMISSION")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="RNA-TR-Scout ONT-cDNA mapper with validated/custom compatibility classification"
    )
    modes = ap.add_mutually_exclusive_group(required=True)
    modes.add_argument("--self-test", action="store_true")
    modes.add_argument("--inspect", action="store_true")
    modes.add_argument("--run", action="store_true")

    ap.add_argument("--project-root", type=Path, default=Path.cwd())
    ap.add_argument("--resource-root", type=Path)
    ap.add_argument("--validated-profile", type=Path)

    ap.add_argument("--reference-fasta", type=Path)
    ap.add_argument("--reference-fai", type=Path)
    ap.add_argument("--reference-mmi", type=Path)
    ap.add_argument("--junction-bed", type=Path)
    ap.add_argument("--compatibility-bed", type=Path)

    ap.add_argument("--fastq", type=Path)
    ap.add_argument("--output-bam", type=Path)
    ap.add_argument("--run-id")
    ap.add_argument("--sample-id")
    ap.add_argument("--expected-fastq-sha256", default="")
    ap.add_argument("--work-dir", type=Path)
    ap.add_argument("--inspection-json", type=Path)

    args = ap.parse_args()

    if args.self_test:
        return self_test()

    inspection, paths = inspect_resources(args, for_run=args.run)

    if args.inspection_json:
        atomic_json(args.inspection_json.resolve(), inspection)

    if args.inspect:
        print(json.dumps(inspection, indent=2, sort_keys=True))
        return 0

    for name in ("fastq", "output_bam", "run_id", "sample_id"):
        if getattr(args, name) in (None, ""):
            ap.error(f"--{name.replace('_','-')} is required for --run")

    fastq = args.fastq.resolve()
    ensure_regular(fastq)
    fastq_sha = sha256_file(fastq)
    if args.expected_fastq_sha256 and fastq_sha != args.expected_fastq_sha256:
        raise MappingError(
            f"FASTQ SHA drift: {fastq_sha} != {args.expected_fastq_sha256}"
        )

    output_bam = args.output_bam.resolve()
    output_bai = Path(str(output_bam) + ".bai")
    output_manifest = Path(str(output_bam) + ".mapping_manifest.json")
    for p in (output_bam, output_bai, output_manifest):
        if p.exists() or p.is_symlink():
            raise MappingError(f"refusing to overwrite existing output: {p}")
    output_bam.parent.mkdir(parents=True, exist_ok=True)

    work_dir = (
        args.work_dir.resolve()
        if args.work_dir
        else output_bam.parent / (output_bam.name + ".work")
    )
    if work_dir.exists():
        raise MappingError(f"work directory already exists: {work_dir}")
    work_dir.mkdir(parents=True)

    fasta = paths["fasta"]
    junction = paths["junction"]
    mmi = paths["mmi"]
    assert isinstance(fasta, Path)
    assert isinstance(junction, Path)

    if inspection["mmi_plan"] == "BUILD_RUN_LOCAL_MMI":
        mmi = work_dir / "reference.generated.mmi"
        build_mmi(fasta, mmi)
        inspection["resources"]["reference_mmi"] = {
            "path": str(mmi),
            "sha256": sha256_file(mmi),
            "validated_sha256": "",
            "profile_status": "RUN_LOCAL_GENERATED",
        }
    if not isinstance(mmi, Path):
        raise MappingError("no usable minimap2 index resolved")

    rg = (
        f"@RG\\tID:{args.run_id}\\tSM:{args.sample_id}"
        "\\tPL:ONT\\tLB:ONT_cDNA"
    )
    if "\t" in rg:
        raise MappingError("read-group unexpectedly contains literal tab")

    mm_cmd = [
        "minimap2",
        "-ax", "splice",
        "-t", "16",
        "--junc-bed", str(junction),
        "--secondary=yes",
        "-N", "10",
        "--MD",
        "--cs=long",
        "-R", rg,
        str(mmi),
        str(fastq),
    ]
    sort_cmd = [
        "samtools", "sort",
        "-@", "8",
        "-m", "1G",
        "-T", str(work_dir / "sorttmp"),
        "-o", str(output_bam),
        "-",
    ]

    mm_log = Path(str(output_bam) + ".minimap2.log")
    sort_log = Path(str(output_bam) + ".samtools_sort.log")

    started = time.perf_counter()
    with mm_log.open("wb") as mm_err, sort_log.open("wb") as sort_err:
        mm = subprocess.Popen(mm_cmd, stdout=subprocess.PIPE, stderr=mm_err)
        assert mm.stdout is not None
        sorter = subprocess.Popen(
            sort_cmd,
            stdin=mm.stdout,
            stdout=subprocess.DEVNULL,
            stderr=sort_err,
        )
        mm.stdout.close()
        sort_rc = sorter.wait()
        mm_rc = mm.wait()

    if mm_rc != 0 or sort_rc != 0:
        raise MappingError(
            f"mapping pipeline failed: minimap2={mm_rc} samtools_sort={sort_rc}"
        )

    qc = subprocess.run(
        ["samtools", "quickcheck", "-v", str(output_bam)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if qc.returncode != 0:
        raise MappingError("samtools quickcheck failed:\n" + qc.stdout)

    idx = subprocess.run(
        ["samtools", "index", "-@", "8", str(output_bam)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if idx.returncode != 0:
        raise MappingError("samtools index failed:\n" + idx.stdout)

    elapsed = time.perf_counter() - started

    result = dict(inspection)
    result.update(
        {
            "run_id": args.run_id,
            "sample_id": args.sample_id,
            "input": {
                "fastq": str(fastq),
                "fastq_sha256": fastq_sha,
            },
            "commands": {
                "minimap2": mm_cmd,
                "samtools_sort": sort_cmd,
            },
            "outputs": {
                "bam": str(output_bam),
                "bam_sha256": sha256_file(output_bam),
                "bai": str(output_bai),
                "bai_sha256": sha256_file(output_bai),
                "minimap2_log": str(mm_log),
                "samtools_sort_log": str(sort_log),
            },
            "mapping_wall_seconds": elapsed,
            "status": "PASS",
        }
    )
    atomic_json(output_manifest, result)

    print("RNATR_ONT_CDNA_MAPPING\tPASS")
    print(f"profile_status\t{result['profile_status']}")
    print(f"golden_validation_scope\t{str(result['golden_validation_scope']).lower()}")
    print(f"minimap2_profile\t{result['tools']['minimap2']['profile_status']}")
    print(f"bam\t{output_bam}")
    print(f"manifest\t{output_manifest}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
