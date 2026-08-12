#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import difflib
import gzip
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Iterable

try:
    import pysam
except Exception as exc:  # pragma: no cover
    pysam = None
    PYSAM_IMPORT_ERROR = exc
else:
    PYSAM_IMPORT_ERROR = None

VERSION = "rnatr_core_generic_unit_bam_fastq_to_final_v0.1.1"
MANIFEST_VERSION = "rnatr_core_result_manifest_v0.1.0"
TABLES = (
    "general_repeat_calls",
    "read_evidence",
    "repeat_events",
    "repeat_segments",
    "repeat_interruptions",
)


class CoreRunError(RuntimeError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path, chunk: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def ensure_regular(path: Path, *, nonempty: bool = True) -> None:
    if not path.is_file() or path.is_symlink():
        raise CoreRunError(f"required regular file missing/invalid: {path}")
    if nonempty and path.stat().st_size == 0:
        raise CoreRunError(f"required file is empty: {path}")


def atomic_write_text(path: Path, text: str, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + f".part.{os.getpid()}")
    with tmp.open("w", encoding="utf-8", newline="") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    if mode is not None:
        tmp.chmod(mode)
    os.replace(tmp, path)


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def write_tsv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + f".part.{os.getpid()}")
    with tmp.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh, delimiter="\t", lineterminator="\n", fieldnames=fields, extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(rows)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def write_metrics(path: Path, items: Iterable[tuple[str, Any]]) -> None:
    write_tsv(path, [{"metric": k, "value": v} for k, v in items], ["metric", "value"])


def read_metrics(path: Path) -> dict[str, str]:
    ensure_regular(path)
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        if reader.fieldnames != ["metric", "value"]:
            raise CoreRunError(f"unexpected metric header: {path}: {reader.fieldnames}")
        return {str(row["metric"]): str(row["value"]) for row in reader}


def data_rows(path: Path) -> int:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", newline="") as fh:
        return max(0, sum(1 for _ in fh) - 1)


def deterministic_gzip(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name("." + target.name + f".part.{os.getpid()}")
    with source.open("rb") as src, tmp.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=1, mtime=0) as out:
            shutil.copyfileobj(src, out, length=8 * 1024 * 1024)
        raw.flush()
        os.fsync(raw.fileno())
    os.replace(tmp, target)


def load_runtime_config(path: Path) -> dict[str, Any]:
    ensure_regular(path)
    obj = json.loads(path.read_text(encoding="utf-8"))
    if obj.get("runtime_config_version") != "rnatr_core_runtime_config_v0.1.0":
        raise CoreRunError("unsupported runtime config version")
    for section in ("components", "catalogs"):
        if not isinstance(obj.get(section), dict) or not obj[section]:
            raise CoreRunError(f"missing runtime config section: {section}")
    for key in ("schema_dir", "assignment_schema_dir", "catalog_root"):
        if not obj.get(key):
            raise CoreRunError(f"missing runtime config field: {key}")
    return obj


def guard_runtime_config(config: dict[str, Any]) -> tuple[dict[str, Path], dict[str, Path], list[dict[str, Any]]]:
    components: dict[str, Path] = {}
    catalogs: dict[str, Path] = {}
    rows: list[dict[str, Any]] = []
    for section, output in (("components", components), ("catalogs", catalogs)):
        for role, entry in sorted(config[section].items()):
            if not isinstance(entry, dict):
                raise CoreRunError(f"invalid runtime config entry: {section}.{role}")
            path = Path(str(entry.get("path", ""))).expanduser().resolve()
            ensure_regular(path)
            actual = sha256_file(path)
            expected = str(entry.get("sha256", ""))
            if not expected or actual != expected:
                raise CoreRunError(f"{section}.{role} SHA drift: {actual} != {expected}: {path}")
            output[role] = path
            rows.append({
                "section": section, "role": role, "path": str(path),
                "bytes": path.stat().st_size, "sha256": actual, "status": "PASS",
            })
    return components, catalogs, rows


def require_roles(mapping: dict[str, Path], roles: Iterable[str], label: str) -> None:
    missing = [role for role in roles if role not in mapping]
    if missing:
        raise CoreRunError(f"runtime config missing {label} roles: {','.join(missing)}")


def replace_exact(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise CoreRunError(f"{label} replacement count {count} != 1")
    return text.replace(old, new, 1)


def replace_regex(text: str, pattern: str, replacement: str, expected: int, label: str, flags: int = 0) -> str:
    updated, count = re.subn(pattern, replacement, text, flags=flags)
    if count != expected:
        raise CoreRunError(f"{label} replacement count {count} != {expected}")
    return updated


def patch_compression(text: str, expected: int, label: str) -> str:
    updated, count = re.subn(
        r'("wt",\n)(\s*)(encoding=)',
        r'\1\2compresslevel=1,\n\2\3',
        text,
    )
    if count != expected:
        raise CoreRunError(f"{label} compression patch count {count} != {expected}")
    return updated


def write_runtime_shell(
    *,
    source: Path,
    destination: Path,
    paths_env: Path,
    run_id: str,
    sample_id: str,
    role: str,
    assignment_validator: Path,
    candidate_fastq: Path,
    window_fastq: Path,
) -> dict[str, Any]:
    original = source.read_text(encoding="utf-8")
    text = replace_exact(
        original,
        "conda activate rnatr-v03",
        "# Environment is inherited from the generic entry point.",
        f"{role}:conda",
    )
    text = replace_regex(
        text,
        r'^source\s+(?:"[^"\n]*config/paths\.env"|[^\s\n]*config/paths\.env)\s*$',
        'source "${RNATR_PATHS_ENV:?RNATR_PATHS_ENV is required}"',
        1,
        f"{role}:paths_env",
        flags=re.M,
    )
    text = replace_regex(text, r'^RUN_ID=.*$', f"RUN_ID={shlex.quote(run_id)}", 1, f"{role}:run", re.M)
    text = replace_regex(text, r'^SAMPLE_ID=.*$', f"SAMPLE_ID={shlex.quote(sample_id)}", 1, f"{role}:sample", re.M)
    if role == "11b":
        text = patch_compression(text, 3, role)
        text = replace_exact(
            text,
            'VALIDATOR="$SCHEMA_DIR/rnatr_v03_validate_tsv.py"',
            'VALIDATOR="$PROJECT_ROOT/config/evidence_schema/v0.3/patches/validator_v0.3.1/rnatr_v03_validate_tsv_validator_v0.3.1.py"',
            "11b:validator",
        )
        text = replace_exact(text, '  "$BAI" \\\n', "", "11b:no_bai")
    elif role == "11d3":
        text = patch_compression(text, 2, role)
        text = replace_regex(
            text, r'^CANDIDATE_FASTQ=.*$',
            'CANDIDATE_FASTQ="$RAW_ROOT/intermediates/$RUN_ID/candidate_reads.fastq.gz"',
            1, "11d3:candidate", re.M,
        )
        text = replace_regex(
            text, r'^DATA_OUTDIR=.*$',
            'DATA_OUTDIR="$RAW_ROOT/intermediates/$RUN_ID"',
            1, "11d3:data_out", re.M,
        )
        text = replace_regex(
            text, r'^WINDOW_FASTQ=.*$',
            'WINDOW_FASTQ="$DATA_OUTDIR/target_windows.fastq.gz"',
            1, "11d3:window", re.M,
        )
        text = replace_exact(text, "EXPECTED_CANDIDATE_ROWS=388571", 'EXPECTED_CANDIDATE_ROWS="${EXPECTED_CANDIDATE_ROWS:-388571}"', "11d3:rows")
        text = replace_exact(text, "EXPECTED_CANDIDATE_READS=79176", 'EXPECTED_CANDIDATE_READS="${EXPECTED_CANDIDATE_READS:-79176}"', "11d3:reads")
        text = replace_exact(text, '  "${BAM}.bai" \\\n', "", "11d3:no_bai")
    else:
        raise CoreRunError(f"unsupported runtime shell role: {role}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(destination, text, mode=0o755)
    syntax = subprocess.run(["bash", "-n", str(destination)], text=True, capture_output=True)
    if syntax.returncode != 0:
        raise CoreRunError(f"patched shell syntax failed: {syntax.stderr.strip()}")
    diff_path = destination.with_suffix(destination.suffix + ".generic.diff")
    atomic_write_text(diff_path, "".join(difflib.unified_diff(
        original.splitlines(keepends=True), text.splitlines(keepends=True),
        fromfile=str(source), tofile=str(destination),
    )))
    return {
        "role": role, "source": str(source), "source_sha256": sha256_file(source),
        "runtime_copy": str(destination), "runtime_sha256": sha256_file(destination),
        "diff": str(diff_path), "status": "PASS",
    }


def write_generic_caller_adapter(source: Path, destination: Path) -> dict[str, Any]:
    original = source.read_text(encoding="utf-8")
    text = replace_exact(
        original,
        '    ap.add_argument("--outdir",type=Path,required=True)\n',
        '    ap.add_argument("--outdir",type=Path,required=True)\n'
        '    ap.add_argument("--caller-source",type=Path,required=True)\n',
        "caller_adapter:add_arg",
    )
    text = replace_regex(
        text,
        r'^\s*caller_p\s*=\s*Path\([^\n]+\)\s*$',
        "    caller_p=args.caller_source.resolve()",
        1,
        "caller_adapter:caller_source",
        flags=re.M,
    )
    if re.search(r'(?:/mnt/|/media/|/home/[^/]+/)', text):
        raise CoreRunError("generic caller adapter retains developer-machine path")
    compile(text, str(destination), "exec")
    atomic_write_text(destination, text, mode=0o755)
    diff_path = destination.with_suffix(destination.suffix + ".generic.diff")
    atomic_write_text(diff_path, "".join(difflib.unified_diff(
        original.splitlines(keepends=True), text.splitlines(keepends=True),
        fromfile=str(source), tofile=str(destination),
    )))
    return {
        "role": "caller_runid_adapter", "source": str(source),
        "source_sha256": sha256_file(source), "runtime_copy": str(destination),
        "runtime_sha256": sha256_file(destination), "diff": str(diff_path), "status": "PASS",
    }


def run_timed(label: str, command: list[str], log: Path, time_file: Path, env_extra: dict[str, str] | None = None) -> dict[str, Any]:
    env = os.environ.copy()
    if env_extra:
        env.update({str(k): str(v) for k, v in env_extra.items()})
    log.parent.mkdir(parents=True, exist_ok=True)
    time_file.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    with log.open("w", encoding="utf-8") as out:
        proc = subprocess.run(
            ["/usr/bin/time", "-v", "-o", str(time_file), *command],
            stdout=out, stderr=subprocess.STDOUT, text=True, env=env,
        )
    elapsed = time.perf_counter() - started
    row = {
        "stage": label, "elapsed_seconds": f"{elapsed:.9f}", "exit_code": proc.returncode,
        "command": shlex.join(command), "log": str(log), "time_v": str(time_file),
        "status": "PASS" if proc.returncode == 0 else "FAIL",
    }
    if proc.returncode != 0:
        tail = "\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-100:])
        raise CoreRunError(f"stage failed {label} rc={proc.returncode}:\n{tail}")
    return row


def exact_read_coherence(bam: Path, fastq: Path) -> dict[str, Any]:
    if pysam is None:
        raise CoreRunError(f"pysam import failed: {PYSAM_IMPORT_ERROR}")
    bam_ids: set[str] = set()
    alignment_records = 0
    primary_records = 0
    with pysam.AlignmentFile(str(bam), "rb") as handle:
        for record in handle.fetch(until_eof=True):
            alignment_records += 1
            if record.is_secondary or record.is_supplementary:
                continue
            primary_records += 1
            rid = record.query_name
            if not rid or rid in bam_ids:
                raise CoreRunError(f"missing/duplicate BAM primary read ID: {rid}")
            bam_ids.add(rid)
    fastq_ids: set[str] = set()
    with pysam.FastxFile(str(fastq)) as handle:
        for record in handle:
            if record.name in fastq_ids:
                raise CoreRunError(f"duplicate FASTQ read ID: {record.name}")
            if record.quality is None:
                raise CoreRunError(f"FASTQ record lacks quality: {record.name}")
            fastq_ids.add(record.name)
    if bam_ids != fastq_ids:
        raise CoreRunError(
            f"BAM/FASTQ exact read sets differ: bam_only={len(bam_ids-fastq_ids)} "
            f"fastq_only={len(fastq_ids-bam_ids)}"
        )
    digest = hashlib.sha256()
    for rid in sorted(bam_ids):
        digest.update(rid.encode()); digest.update(b"\n")
    return {
        "alignment_records": alignment_records, "primary_records": primary_records,
        "fastq_records": len(fastq_ids), "unique_read_ids": len(bam_ids),
        "read_id_set_sha256": digest.hexdigest(), "status": "PASS",
    }


def symlink_exact(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        raise CoreRunError(f"link destination already exists: {destination}")
    destination.symlink_to(source)


def build_manifest(
    *, output_part: Path, run_id: str, sample_id: str, bam: Path, reads_fastq: Path,
    components: dict[str, Path], catalogs: dict[str, Path], runtime_rows: list[dict[str, Any]],
    table_rows: list[dict[str, Any]], validation_rows: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    resources: dict[str, Any] = {
        "source_bam": {"logical_id": "source_bam", "kind": "BAM", "bytes": bam.stat().st_size,
                       "sha256": sha256_file(bam), "binding": "resource_bindings.local.json#/resources/source_bam"},
        "source_reads": {"logical_id": "source_reads", "kind": "FASTQ", "bytes": reads_fastq.stat().st_size,
                         "sha256": sha256_file(reads_fastq), "binding": "resource_bindings.local.json#/resources/source_reads"},
    }
    for kind, mapping in (("CATALOG_OR_ANNOTATION", catalogs), ("CORE_COMPONENT", components)):
        prefix = "catalog" if kind.startswith("CATALOG") else "component"
        for role, path in sorted(mapping.items()):
            logical = f"{prefix}:{role}"
            resources[logical] = {
                "logical_id": logical, "kind": kind, "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "binding": f"resource_bindings.local.json#/resources/{logical}",
            }
    artifacts: list[dict[str, Any]] = []
    for row in table_rows:
        artifacts.append({
            "logical_name": row["artifact"], "table": row["table"], "path": row["path"],
            "rows": row["rows"], "bytes": row["bytes"], "sha256": row["sha256"],
            "parity_contract": row["parity_contract"],
        })
    for filename, kind in (
        ("package_manifest.tsv", "PACKAGE_MANIFEST"),
        ("materialization.qc.tsv", "QC_METRICS"),
        ("validation_summary.tsv", "VALIDATION_SUMMARY"),
        ("performance.tsv", "PERFORMANCE_INSTRUMENTATION"),
        ("input_read_coherence.tsv", "INPUT_COHERENCE"),
        ("runtime_component_copies.tsv", "RUNTIME_PROVENANCE"),
        ("runtime_config_guards.tsv", "RUNTIME_PROVENANCE"),
    ):
        path = output_part / filename
        ensure_regular(path)
        artifacts.append({
            "logical_name": filename, "kind": kind, "path": filename,
            "rows": data_rows(path), "bytes": path.stat().st_size, "sha256": sha256_file(path),
            "parity_contract": "PROVENANCE_OR_QC_FIELD_SCOPED",
        })
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "core_runner_version": VERSION,
        "scientific_contract": {
            "evidence_schema": "0.4.2",
            "caller": "rnatr_general_repeat_caller_ref_v0.4.1",
            "materializer": "rnatr_native_v041_to_evidence_v042_materializer_v0.1.2",
            "target_catalog": "RNA-TR-Scout_v0.3_rnatr_pilot_v03",
            "mapping_timing_boundary": "FASTQ_TO_BAM_MAPPING_OUTSIDE_BAM_TO_FINAL_TIMER",
            "bam_only_input": False,
            "source_read_sequence_required": True,
            "internal_intermediate_layout_is_public_api": False,
        },
        "run": {"run_id": run_id, "sample_id": sample_id, "created_utc": utc_now()},
        "resources": resources,
        "artifacts": artifacts,
        "join_key_contract": {
            "read_id": "stable source-read identifier; joins Core evidence to BAM/FASTQ",
            "target_source": "namespace for target_region_id (for example analysis or disease catalog)",
            "target_region_id": "pinned mapping-target identity within target_source",
            "locus_id": "representative stable locus identity",
            "evidence_id": "unique molecule-by-locus evidence identifier",
            "repeat_event_id": "unique repeat-event identifier",
            "repeat_call_id": "unique repeat-segment/call identifier",
            "interruption_id": "unique repeat-interruption identifier",
            "caller_record_id": "unique caller-attempt identifier",
        },
        "coordinate_contract": {
            "genomic": "0_based_end_exclusive",
            "raw_read": "0_based_end_exclusive_original_FASTQ_orientation",
            "hardclip": "cigar_offset_aware",
        },
        "validation": {"status": "PASS", "records": validation_rows,
                       "summary_artifact": "validation_summary.tsv"},
        "performance_instrumentation": {"logical_name": "performance.tsv", "path": "performance.tsv"},
        "runtime_component_copies": [
            {"role": r["role"], "source_sha256": r["source_sha256"],
             "runtime_sha256": r["runtime_sha256"], "status": r["status"]}
            for r in runtime_rows
        ],
        "post_freeze_extensibility": {
            "stage_fusion_allowed_behind_contract": True,
            "streaming_allowed_behind_contract": True,
            "intermediate_io_reduction_allowed_behind_contract": True,
            "hardware_aware_concurrency_allowed_behind_contract": True,
            "golden_regression_required_for_change": True,
        },
    }
    bindings = {"binding_version": "rnatr_local_resource_bindings_v0.1.0", "resources": {}}
    bindings["resources"]["source_bam"] = {"path": str(bam.resolve())}
    bindings["resources"]["source_reads"] = {"path": str(reads_fastq.resolve())}
    for prefix, mapping in (("catalog", catalogs), ("component", components)):
        for role, path in sorted(mapping.items()):
            bindings["resources"][f"{prefix}:{role}"] = {"path": str(path.resolve())}
    return manifest, bindings


def self_test() -> int:
    with tempfile.TemporaryDirectory(prefix="rnatr_generic_unit_selftest_") as td:
        root = Path(td)
        payload = root / "x.tsv"
        payload.write_text("a\tb\n1\t2\n", encoding="utf-8")
        deterministic_gzip(payload, root / "a.tsv.gz")
        deterministic_gzip(payload, root / "b.tsv.gz")
        if sha256_file(root / "a.tsv.gz") != sha256_file(root / "b.tsv.gz"):
            raise CoreRunError("deterministic gzip self-test failed")
        cfg = root / "runtime.json"
        cfg.write_text(json.dumps({
            "runtime_config_version": "rnatr_core_runtime_config_v0.1.0",
            "components": {"x": {"path": str(payload), "sha256": sha256_file(payload)}},
            "catalogs": {"y": {"path": str(payload), "sha256": sha256_file(payload)}},
            "schema_dir": str(root), "assignment_schema_dir": str(root), "catalog_root": str(root),
        }), encoding="utf-8")
        components, catalogs, rows = guard_runtime_config(load_runtime_config(cfg))
        if components["x"] != payload.resolve() or catalogs["y"] != payload.resolve() or len(rows) != 2:
            raise CoreRunError("runtime guard self-test failed")
    print("SELF_TEST\tPASS")
    print(f"version\t{VERSION}")
    print(f"manifest_version\t{MANIFEST_VERSION}")
    return 0


def execute(args: argparse.Namespace) -> int:
    if pysam is None:
        raise CoreRunError(f"pysam import failed: {PYSAM_IMPORT_ERROR}")
    for exe in ("python", "samtools", "bedtools", "bgzip", "tabix", "sha256sum", "gzip"):
        if shutil.which(exe) is None:
            raise CoreRunError(f"required executable not found: {exe}")
    if not Path("/usr/bin/time").is_file():
        raise CoreRunError("required executable missing: /usr/bin/time")

    bam = args.bam.resolve(); reads_fastq = args.reads_fastq.resolve()
    work_root = args.work_root.resolve(); output_root = args.output_root.resolve()
    ensure_regular(bam); ensure_regular(reads_fastq)
    if work_root.exists() or output_root.exists() or Path(str(output_root) + ".part").exists():
        raise CoreRunError("work/output root already exists")
    if not args.run_id or any(ch.isspace() for ch in args.run_id):
        raise CoreRunError("run_id must be nonempty and contain no whitespace")
    if not args.sample_id or args.sample_id.strip() != args.sample_id:
        raise CoreRunError("sample_id must be nonempty and trimmed")

    config = load_runtime_config(args.runtime_config.resolve())
    components, catalogs, guard_rows = guard_runtime_config(config)
    require_roles(components, (
        "11b_target_assignment", "11d3_raw_projection", "candidate_fastq_extractor",
        "fast_motif_builder", "caller_runid_adapter", "caller_native_v041",
        "materializer_runid_adapter", "schema_v042", "validator_v042_tsv",
        "validator_v042_package", "assignment_schema_v03", "assignment_validator_v031",
    ), "component")
    require_roles(catalogs, (
        "mapping_target_bed", "mapping_target_bed_index", "mapping_target_tsv",
        "analysis_regions", "disease_regions",
    ), "catalog")
    catalog_root = Path(str(config["catalog_root"])).resolve()
    expected_catalog_paths = {
        "mapping_target_bed": catalog_root / "trexplorer_v2/rnatr_pilot_v03/final/RNA-TR-Scout_v0.3.mapping_target_regions.bed.gz",
        "mapping_target_bed_index": catalog_root / "trexplorer_v2/rnatr_pilot_v03/final/RNA-TR-Scout_v0.3.mapping_target_regions.bed.gz.tbi",
        "mapping_target_tsv": catalog_root / "trexplorer_v2/rnatr_pilot_v03/final/RNA-TR-Scout_v0.3.mapping_target_regions.tsv.gz",
        "analysis_regions": catalog_root / "trexplorer_v2/rnatr_pilot_v03/final/TRExplorer_v2.rnatr_pilot_analysis_regions.final.tsv.gz",
        "disease_regions": catalog_root / "trexplorer_v2/rnatr_pilot_v03/final/STRchive_disease_regions.final.tsv.gz",
    }
    for role, expected_path in expected_catalog_paths.items():
        if catalogs[role] != expected_path.resolve():
            raise CoreRunError(
                f"catalog role/path does not match catalog_root contract: {role}: "
                f"{catalogs[role]} != {expected_path.resolve()}"
            )
    if Path(str(catalogs["mapping_target_bed"]) + ".tbi") != catalogs["mapping_target_bed_index"]:
        raise CoreRunError("mapping target BED/index naming mismatch")

    schema_dir = Path(str(config["schema_dir"])).resolve()
    assignment_schema_dir = Path(str(config["assignment_schema_dir"])).resolve()
    expected_component_paths = {
        "schema_v042": schema_dir / "schema/rnatr_v04_table_schema.json",
        "validator_v042_tsv": schema_dir / "rnatr_v042_validate_tsv.py",
        "validator_v042_package": schema_dir / "rnatr_v042_validate_package.py",
        "assignment_schema_v03": assignment_schema_dir / "schema/rnatr_v03_table_schema.json",
        "assignment_validator_v031": assignment_schema_dir / "patches/validator_v0.3.1/rnatr_v03_validate_tsv_validator_v0.3.1.py",
    }
    for role, expected_path in expected_component_paths.items():
        if components[role] != expected_path.resolve():
            raise CoreRunError(
                f"schema/validator role path does not match directory contract: {role}: "
                f"{components[role]} != {expected_path.resolve()}"
            )
    if args.expected_bam_sha256 and sha256_file(bam) != args.expected_bam_sha256:
        raise CoreRunError("input BAM SHA mismatch")
    if args.expected_fastq_sha256 and sha256_file(reads_fastq) != args.expected_fastq_sha256:
        raise CoreRunError("input FASTQ SHA mismatch")

    work_root.mkdir(parents=True)
    project = work_root / "project"; raw_root = work_root / "raw"; qc_root = work_root / "qc"
    logs = qc_root / "logs"; timing = qc_root / "timing"; scripts = work_root / "runtime_components"
    output_part = Path(str(output_root) + ".part"); output_part.mkdir(parents=True)

    coherence = exact_read_coherence(bam, reads_fastq)
    write_metrics(qc_root / "input_read_coherence.tsv", coherence.items())
    mapping_dir = project / "results/11_mapping" / args.run_id
    local_bam = mapping_dir / f"{args.run_id}.sorted.bam"
    local_fastq = raw_root / "inputs/source_reads.fastq.gz"
    symlink_exact(bam, local_bam); symlink_exact(reads_fastq, local_fastq)
    write_metrics(mapping_dir / "run_manifest.tsv", [
        ("run_id", args.run_id), ("sample_id", args.sample_id),
        ("source_bam_logical_id", "source_bam"), ("source_reads_logical_id", "source_reads"),
        ("alignment_records", coherence["alignment_records"]),
        ("primary_reads", coherence["primary_records"]), ("fastq_reads", coherence["fastq_records"]),
        ("read_id_set_sha256", coherence["read_id_set_sha256"]), ("bam_index_required", "false"),
    ])
    config_dir = project / "config"; config_dir.mkdir(parents=True)
    paths_env = config_dir / "paths.env"
    atomic_write_text(paths_env,
        "# Generated runtime bindings; not public scientific API.\n"
        f"export PROJECT_ROOT={shlex.quote(str(project))}\n"
        f"export RAW_ROOT={shlex.quote(str(raw_root))}\n"
        f"export CATALOG_ROOT={shlex.quote(str(Path(str(config['catalog_root'])).resolve()))}\n")
    schema_parent = project / "config/evidence_schema"; schema_parent.mkdir(parents=True)
    (schema_parent / "v0.3").symlink_to(Path(str(config["assignment_schema_dir"])).resolve(), target_is_directory=True)

    candidate_fastq = raw_root / "intermediates" / args.run_id / "candidate_reads.fastq.gz"
    window_fastq = raw_root / "intermediates" / args.run_id / "target_windows.fastq.gz"
    runtime_rows = [
        write_runtime_shell(source=components["11b_target_assignment"], destination=scripts/"11b.generic_runtime.sh",
            paths_env=paths_env, run_id=args.run_id, sample_id=args.sample_id, role="11b",
            assignment_validator=components["assignment_validator_v031"], candidate_fastq=candidate_fastq, window_fastq=window_fastq),
        write_runtime_shell(source=components["11d3_raw_projection"], destination=scripts/"11d3.generic_runtime.sh",
            paths_env=paths_env, run_id=args.run_id, sample_id=args.sample_id, role="11d3",
            assignment_validator=components["assignment_validator_v031"], candidate_fastq=candidate_fastq, window_fastq=window_fastq),
        write_generic_caller_adapter(components["caller_runid_adapter"], scripts/"caller_adapter.generic.py"),
    ]
    write_tsv(qc_root/"runtime_component_copies.tsv", runtime_rows,
              ["role","source","source_sha256","runtime_copy","runtime_sha256","diff","status"])
    write_tsv(qc_root/"runtime_config_guards.tsv", guard_rows,
              ["section","role","path","bytes","sha256","status"])

    perf: list[dict[str, Any]] = []
    env_seed = {"PYTHONHASHSEED": args.pythonhashseed}
    perf.append(run_timed("11b_target_assignment", ["bash", str(scripts/"11b.generic_runtime.sh")],
                          logs/"11b.log", timing/"11b.time_v.txt", {
                              **env_seed,
                              "RNATR_PATHS_ENV": str(paths_env),
                              "EXPECTED_ALIGNMENT_RECORDS": str(coherence["alignment_records"]),
                              "EXPECTED_READS": str(coherence["primary_records"]),
                          }))
    assignment_qc = read_metrics(project/"qc/11_assignment"/args.run_id/"target_assignment_qc.tsv")
    if assignment_qc.get("audit_status") != "PASS":
        raise CoreRunError("11b QC did not PASS")
    candidate_rows = int(assignment_qc["read_target_candidates"])
    candidate_reads = int(assignment_qc["reads_with_any_candidate"])
    assignment_path = project/"results/11_assignment"/args.run_id/"read_target_candidates.tsv.gz"
    candidate_qc_path = qc_root/"candidate_fastq_extraction.qc.tsv"
    perf.append(run_timed("candidate_fastq_extraction", [
        sys.executable, str(components["candidate_fastq_extractor"]),
        "--assignment", str(assignment_path), "--input-fastq", str(local_fastq),
        "--output-fastq", str(candidate_fastq), "--qc", str(candidate_qc_path),
        "--expected-rows", str(candidate_rows), "--expected-reads", str(candidate_reads),
    ], logs/"candidate_fastq.log", timing/"candidate_fastq.time_v.txt", env_seed))
    if read_metrics(candidate_qc_path).get("audit_status") != "PASS":
        raise CoreRunError("candidate FASTQ QC did not PASS")

    perf.append(run_timed("11d3_raw_projection", ["bash", str(scripts/"11d3.generic_runtime.sh")],
                          logs/"11d3.log", timing/"11d3.time_v.txt", {
                              **env_seed, "RNATR_PATHS_ENV": str(paths_env),
                              "EXPECTED_CANDIDATE_ROWS": str(candidate_rows),
                              "EXPECTED_CANDIDATE_READS": str(candidate_reads),
                          }))
    projection_path = project/"results/11_projection"/args.run_id/"v0.3.3/read_target_projection.v0.3.3.tsv.gz"
    projection_qc = read_metrics(project/"qc/11_projection"/args.run_id/"v0.3.3/raw_projection_qc.v0.3.3.tsv")
    if projection_qc.get("audit_status") != "PASS":
        raise CoreRunError("11d3 QC did not PASS")
    if int(projection_qc["projection_rows_written"]) != candidate_rows or int(projection_qc["projection_unique_reads"]) != candidate_reads:
        raise CoreRunError("11d3 counts do not match 11b")

    jobs_path = project/"results/11_motif_jobs"/args.run_id/"motif_scan_jobs.tsv.gz"
    motif_qc_path = project/"qc/11_motif_jobs"/args.run_id/"motif_job_preparation_qc.tsv"
    motif_manifest = qc_root/"motif_builder.input.tsv"
    write_tsv(motif_manifest, [{
        "shard": "unit_000", "projection_path": str(projection_path), "jobs_path": str(jobs_path),
        "qc_path": str(motif_qc_path), "expected_rows": candidate_rows, "expected_reads": candidate_reads,
    }], ["shard","projection_path","jobs_path","qc_path","expected_rows","expected_reads"])
    perf.append(run_timed("fast_motif_jobs", [
        sys.executable, str(components["fast_motif_builder"]),
        "--analysis-regions", str(catalogs["analysis_regions"]),
        "--disease-regions", str(catalogs["disease_regions"]),
        "--shard-manifest", str(motif_manifest),
        "--summary", str(qc_root/"motif_builder.summary.tsv"), "--workers", "1",
    ], logs/"motif.log", timing/"motif.time_v.txt", env_seed))
    if read_metrics(motif_qc_path).get("audit_status") != "PASS":
        raise CoreRunError("motif QC did not PASS")

    caller_dir = work_root/"caller"
    perf.append(run_timed("native_caller_v041", [
        sys.executable, str(scripts/"caller_adapter.generic.py"),
        "--project-root", str(project), "--run-id", args.run_id,
        "--window-fastq", str(window_fastq), "--outdir", str(caller_dir),
        "--caller-source", str(components["caller_native_v041"]),
        "--workers", str(args.caller_workers),
    ], logs/"caller.log", timing/"caller.time_v.txt", env_seed))
    caller_qc = read_metrics(caller_dir/"general_repeat_integration.qc.tsv")
    if caller_qc.get("audit_status") != "PASS":
        raise CoreRunError("caller QC did not PASS")

    perf.append(run_timed("materializer_v012", [
        sys.executable, str(components["materializer_runid_adapter"]),
        "--project-root", str(project), "--run-id", args.run_id,
        "--calls", str(caller_dir/"general_repeat_calls.v0.4.0.tsv.gz"),
        "--schema-dir", str(Path(str(config["schema_dir"])).resolve()),
        "--outdir", str(output_part), "--sample-id", args.sample_id,
    ], logs/"materializer.log", timing/"materializer.time_v.txt", env_seed))
    materializer_qc = read_metrics(output_part/"materialization.qc.tsv")
    if materializer_qc.get("audit_status") != "PASS":
        raise CoreRunError("materializer QC did not PASS")

    validation_rows: list[dict[str, Any]] = []
    for table in TABLES:
        plain = output_part/f"{table}.tsv"; ensure_regular(plain)
        row = run_timed(f"validate_{table}", [
            sys.executable, str(components["validator_v042_tsv"]),
            "--schema", str(components["schema_v042"]), "--table", table,
            "--input", str(plain), "--max-rows", str(max(1, data_rows(plain)+1)),
        ], logs/f"validate_{table}.log", timing/f"validate_{table}.time_v.txt")
        validation_rows.append({"validator": "rnatr_v042_validate_tsv.py", "table": table, "status": row["status"]})
    package_validation = run_timed("validate_package_v042", [
        sys.executable, str(components["validator_v042_package"]), "--package-dir", str(output_part),
    ], logs/"validate_package.log", timing/"validate_package.time_v.txt")
    validation_rows.append({"validator": "rnatr_v042_validate_package.py", "table": "PACKAGE", "status": package_validation["status"]})

    table_rows: list[dict[str, Any]] = []
    for table in TABLES:
        plain = output_part/f"{table}.tsv"; gz = output_part/f"{table}.tsv.gz"
        deterministic_gzip(plain, gz)
        rows = data_rows(plain)
        table_rows.extend([
            {"artifact": f"{table}.tsv", "table": table, "path": f"{table}.tsv",
             "rows": rows, "bytes": plain.stat().st_size, "sha256": sha256_file(plain),
             "parity_contract": "EXACT_SHA256"},
            {"artifact": f"{table}.tsv.gz", "table": table, "path": f"{table}.tsv.gz",
             "rows": rows, "bytes": gz.stat().st_size, "sha256": sha256_file(gz),
             "parity_contract": "DETERMINISTIC_GZIP_MTIME0"},
        ])
    write_tsv(output_part/"package_manifest.tsv", table_rows,
              ["artifact","table","path","rows","bytes","sha256","parity_contract"])
    write_tsv(qc_root/"performance.tsv", perf,
              ["stage","elapsed_seconds","exit_code","command","log","time_v","status"])
    write_tsv(output_part/"validation_summary.tsv", validation_rows, ["validator","table","status"])
    for source, target in (
        (qc_root/"performance.tsv", output_part/"performance.tsv"),
        (qc_root/"input_read_coherence.tsv", output_part/"input_read_coherence.tsv"),
        (qc_root/"runtime_component_copies.tsv", output_part/"runtime_component_copies.tsv"),
        (qc_root/"runtime_config_guards.tsv", output_part/"runtime_config_guards.tsv"),
    ):
        shutil.copy2(source, target)
    manifest, bindings = build_manifest(
        output_part=output_part, run_id=args.run_id, sample_id=args.sample_id,
        bam=bam, reads_fastq=reads_fastq, components=components, catalogs=catalogs,
        runtime_rows=runtime_rows, table_rows=table_rows, validation_rows=validation_rows,
    )
    atomic_write_json(output_part/"core_result_manifest.json", manifest)
    atomic_write_json(output_part/"resource_bindings.local.json", bindings)

    for path in sorted(output_part.iterdir()):
        if path.is_file():
            with path.open("rb") as fh:
                os.fsync(fh.fileno())
    fd = os.open(output_part, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    output_root.parent.mkdir(parents=True, exist_ok=True)
    os.replace(output_part, output_root)
    fd = os.open(output_root.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

    write_metrics(qc_root/"generic_unit_final.qc.tsv", [
        ("version", VERSION), ("run_id", args.run_id), ("sample_id", args.sample_id),
        ("alignment_records", coherence["alignment_records"]),
        ("primary_reads", coherence["primary_records"]), ("fastq_reads", coherence["fastq_records"]),
        ("read_id_set_sha256", coherence["read_id_set_sha256"]),
        ("candidate_rows", candidate_rows), ("candidate_reads", candidate_reads),
        ("caller_called_rows", caller_qc.get("called_rows", ".")),
        ("atomic_publication", "PASS"), ("audit_status", "PASS"),
    ])
    print("===== RNA-TR-SCOUT GENERIC CORE UNIT FINAL =====")
    print(f"version\t{VERSION}")
    print(f"run_id\t{args.run_id}")
    print(f"sample_id\t{args.sample_id}")
    print("read_coherence\tPASS_EXACT_ID_SET")
    print(f"candidate_rows\t{candidate_rows}")
    print(f"candidate_reads\t{candidate_reads}")
    print("validators\tPASS")
    print("atomic_publication\tPASS")
    print(f"OUTPUT_ROOT\t{output_root}")
    print(f"CORE_RESULT_MANIFEST\t{output_root/'core_result_manifest.json'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--runtime-config", type=Path)
    parser.add_argument("--bam", type=Path)
    parser.add_argument("--reads-fastq", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--sample-id")
    parser.add_argument("--work-root", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--caller-workers", type=int, default=2)
    parser.add_argument("--pythonhashseed", default="0")
    parser.add_argument("--expected-bam-sha256", default="")
    parser.add_argument("--expected-fastq-sha256", default="")
    args = parser.parse_args()
    if args.self_test == args.execute:
        parser.error("choose exactly one of --self-test or --execute")
    if args.self_test:
        return self_test()
    for name in ("runtime_config", "bam", "reads_fastq", "run_id", "sample_id", "work_root", "output_root"):
        if getattr(args, name) in (None, ""):
            parser.error(f"--{name.replace('_','-')} is required with --execute")
    if args.caller_workers < 1:
        parser.error("--caller-workers must be >=1")
    return execute(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
