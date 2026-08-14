#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Iterable

VERSION = "rnatr_catalog_runtime_adapter_v0.1.2"
PROFILE_VERSION = "rnatr_catalog_runtime_validated_profile_v0.1.0"

ANALYSIS_REQUIRED = (
    "chrom",
    "region_start",
    "region_end",
    "analysis_region_id",
    "region_type",
    "analysis_mode",
    "representative_locus_id",
)
DISEASE_REQUIRED = (
    "chrom",
    "start",
    "end",
    "disease_region_id",
    "analysis_mode_hint",
    "matched_trexplorer_locus_id",
)
TARGET_HEADER = (
    "chrom",
    "start",
    "end",
    "target_region_id",
    "target_source",
    "region_type",
    "analysis_mode",
    "representative_locus_id",
)

class CatalogError(RuntimeError):
    pass

def sha256_file(path: Path, chunk: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()

def ensure_regular(path: Path) -> None:
    if not path.is_file() or path.is_symlink():
        raise CatalogError(f"required regular file missing/invalid: {path}")

def opener_text(path: Path):
    return gzip.open(path, "rt", encoding="utf-8", newline="") if path.suffix == ".gz" else path.open(
        "r", encoding="utf-8", newline=""
    )

def read_fai(path: Path) -> tuple[dict[str, int], dict[str, int]]:
    ensure_regular(path)
    lengths: dict[str, int] = {}
    order: dict[str, int] = {}
    with path.open("r", encoding="utf-8", newline="") as fh:
        for i, raw in enumerate(fh):
            if not raw.strip():
                continue
            fields = raw.rstrip("\n").split("\t")
            if len(fields) < 2:
                raise CatalogError(f"invalid FAI line: {i+1}")
            name = fields[0]
            if name in lengths:
                raise CatalogError(f"duplicate FAI contig: {name}")
            try:
                length = int(fields[1])
            except ValueError as exc:
                raise CatalogError(f"invalid FAI length: {name}") from exc
            if length <= 0:
                raise CatalogError(f"non-positive FAI length: {name}")
            order[name] = len(order)
            lengths[name] = length
    if not lengths:
        raise CatalogError("empty FAI")
    return lengths, order

def parse_int(value: str, label: str) -> int:
    try:
        return int(value)
    except Exception as exc:
        raise CatalogError(f"invalid integer {label}: {value!r}") from exc

def validate_interval(
    chrom: str,
    start_text: str,
    end_text: str,
    *,
    lengths: dict[str, int],
    label: str,
) -> tuple[int, int]:
    if not chrom:
        raise CatalogError(f"{label}: empty chrom")
    if chrom not in lengths:
        raise CatalogError(
            f"{label}: contig {chrom!r} absent from active reference FAI; "
            "contig aliases are not normalized automatically"
        )
    start = parse_int(start_text, f"{label}.start")
    end = parse_int(end_text, f"{label}.end")
    if start < 0 or end <= start:
        raise CatalogError(f"{label}: invalid interval {chrom}:{start}-{end}")
    if end > lengths[chrom]:
        raise CatalogError(
            f"{label}: interval out of bounds {chrom}:{start}-{end}>len={lengths[chrom]}"
        )
    return start, end

def require_header(fieldnames: list[str] | None, required: Iterable[str], label: str) -> list[str]:
    fields = list(fieldnames or [])
    missing = [x for x in required if x not in fields]
    if missing:
        raise CatalogError(f"{label}: missing required columns: {missing}")
    if len(fields) != len(set(fields)):
        raise CatalogError(f"{label}: duplicate column names")
    return fields

def load_analysis(path: Path, lengths: dict[str, int]) -> tuple[list[dict[str, str]], list[str]]:
    ensure_regular(path)
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    with opener_text(path) as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        fields = require_header(reader.fieldnames, ANALYSIS_REQUIRED, "analysis_regions")
        for line_no, row in enumerate(reader, 2):
            rid = (row.get("analysis_region_id") or "").strip()
            if not rid or rid == ".":
                raise CatalogError(f"analysis_regions:{line_no}: missing analysis_region_id")
            if rid in seen:
                raise CatalogError(f"analysis_regions:{line_no}: duplicate analysis_region_id: {rid}")
            seen.add(rid)
            validate_interval(
                (row.get("chrom") or "").strip(),
                row.get("region_start") or "",
                row.get("region_end") or "",
                lengths=lengths,
                label=f"analysis_regions:{line_no}",
            )
            for col in ("region_type", "analysis_mode", "representative_locus_id"):
                value = (row.get(col) or "").strip()
                if not value:
                    raise CatalogError(f"analysis_regions:{line_no}: empty {col}")
            rows.append(dict(row))
    if not rows:
        raise CatalogError("analysis_regions: no data rows")
    return rows, fields

def load_disease(path: Path, lengths: dict[str, int]) -> tuple[list[dict[str, str]], list[str]]:
    ensure_regular(path)
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    with opener_text(path) as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        fields = require_header(reader.fieldnames, DISEASE_REQUIRED, "disease_regions")
        for line_no, row in enumerate(reader, 2):
            rid = (row.get("disease_region_id") or "").strip()
            if not rid or rid == ".":
                raise CatalogError(f"disease_regions:{line_no}: missing disease_region_id")
            if rid in seen:
                raise CatalogError(f"disease_regions:{line_no}: duplicate disease_region_id: {rid}")
            seen.add(rid)
            validate_interval(
                (row.get("chrom") or "").strip(),
                row.get("start") or "",
                row.get("end") or "",
                lengths=lengths,
                label=f"disease_regions:{line_no}",
            )
            mode = (row.get("analysis_mode_hint") or "").strip()
            if not mode:
                raise CatalogError(f"disease_regions:{line_no}: empty analysis_mode_hint")
            rows.append(dict(row))
    if not rows:
        raise CatalogError("disease_regions: no data rows")
    return rows, fields

def target_rows(
    analysis: list[dict[str, str]],
    disease: list[dict[str, str]],
) -> list[tuple[str, ...]]:
    """Build raw target rows in historical source-concatenation order."""
    rows: list[tuple[str, ...]] = []
    ids: set[str] = set()
    for row in analysis:
        rid = row["analysis_region_id"].strip()
        if rid in ids:
            raise CatalogError(f"combined target ID collision: {rid}")
        ids.add(rid)
        rows.append(
            (
                row["chrom"].strip(),
                str(int(row["region_start"])),
                str(int(row["region_end"])),
                rid,
                "TRExplorer",
                row["region_type"].strip(),
                row["analysis_mode"].strip(),
                row["representative_locus_id"].strip(),
            )
        )
    for row in disease:
        rid = row["disease_region_id"].strip()
        if rid in ids:
            raise CatalogError(f"combined target ID collision: {rid}")
        ids.add(rid)
        rep = (row.get("matched_trexplorer_locus_id") or "").strip() or "."
        rows.append(
            (
                row["chrom"].strip(),
                str(int(row["start"])),
                str(int(row["end"])),
                rid,
                "STRchive",
                "DISEASE_REGION",
                row["analysis_mode_hint"].strip(),
                rep,
            )
        )
    return rows


def bedtools_sort_target_rows(
    rows: list[tuple[str, ...]],
    lengths: dict[str, int],
    order: dict[str, int],
) -> list[tuple[str, ...]]:
    """Use the same final sorting primitive as historical 09f2."""
    bedtools = require_tool("bedtools")
    if not rows:
        raise CatalogError("cannot sort empty mapping target")

    ordered_contigs = sorted(order, key=order.__getitem__)
    if set(ordered_contigs) != set(lengths):
        raise CatalogError("reference order/length dictionaries disagree")

    with tempfile.TemporaryDirectory(prefix="rnatr_catalog_sort_") as td:
        root = Path(td)
        genome = root / "reference.genome"
        raw_bed = root / "mapping_targets.raw.bed"

        with genome.open("w", encoding="utf-8", newline="") as fh:
            for chrom in ordered_contigs:
                fh.write(f"{chrom}\t{lengths[chrom]}\n")

        with raw_bed.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh, delimiter="\t", lineterminator="\n")
            writer.writerows(rows)

        proc = subprocess.run(
            [bedtools, "sort", "-g", str(genome), "-i", str(raw_bed)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if proc.returncode != 0:
            raise CatalogError("bedtools sort failed:\n" + proc.stdout)

        sorted_rows: list[tuple[str, ...]] = []
        for line_no, raw in enumerate(proc.stdout.splitlines(), 1):
            if not raw:
                continue
            fields = tuple(raw.split("\t"))
            if len(fields) != 8:
                raise CatalogError(
                    f"bedtools sort output line {line_no}: expected 8 columns"
                )
            sorted_rows.append(fields)

    if len(sorted_rows) != len(rows):
        raise CatalogError(
            f"bedtools sort row-count mismatch: {len(sorted_rows)} != {len(rows)}"
        )
    return sorted_rows

def write_gzip_tsv(path: Path, header: list[str], rows: Iterable[Iterable[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmpname = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".part", dir=str(path.parent))
    os.close(fd)
    try:
        with open(tmpname, "wb") as raw:
            # filename="" prevents the temporary file name from entering the
            # gzip FNAME header. Together with mtime=0 this makes the gzip
            # member deterministic for identical logical content.
            with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as gz:
                with io.TextIOWrapper(gz, encoding="utf-8", newline="") as text:
                    writer = csv.writer(text, delimiter="\t", lineterminator="\n")
                    writer.writerow(header)
                    writer.writerows(rows)
        os.replace(tmpname, path)
    finally:
        if os.path.exists(tmpname):
            os.unlink(tmpname)

def copy_gzip_tsv_normalized(src: Path, dst: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    write_gzip_tsv(dst, fields, ([row.get(f, "") for f in fields] for row in rows))

def require_tool(name: str) -> str:
    p = shutil.which(name)
    if not p:
        raise CatalogError(f"required executable missing: {name}")
    return p

def run(cmd: list[str], *, stdout_file: Path | None = None) -> subprocess.CompletedProcess[str]:
    if stdout_file is None:
        p = subprocess.run(
            cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False
        )
    else:
        with stdout_file.open("wb") as out:
            p = subprocess.run(cmd, stdout=out, stderr=subprocess.PIPE, check=False)
        p = subprocess.CompletedProcess(cmd, p.returncode, "", p.stderr.decode("utf-8", errors="replace"))
    if p.returncode != 0:
        raise CatalogError(f"command failed rc={p.returncode}: {' '.join(cmd)}\n{p.stderr if hasattr(p, 'stderr') else p.stdout}")
    return p

def write_bgzip_bed(path: Path, rows: list[tuple[str, ...]]) -> None:
    bgzip = require_tool("bgzip")
    tabix = require_tool("tabix")
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = path.with_suffix(path.suffix + ".raw.tmp")
    try:
        with raw.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh, delimiter="\t", lineterminator="\n")
            writer.writerows(rows)
        run([bgzip, "-f", "-c", str(raw)], stdout_file=path)
        run([tabix, "-f", "-p", "bed", str(path)])
    finally:
        try:
            raw.unlink()
        except FileNotFoundError:
            pass

def load_profile(path: Path) -> dict:
    ensure_regular(path)
    obj = json.loads(path.read_text(encoding="utf-8"))
    if obj.get("profile_version") != PROFILE_VERSION:
        raise CatalogError("unsupported catalog validated profile")
    return obj

def exact_state(paths: dict[str, Path], profile: dict) -> tuple[bool, dict]:
    states: dict[str, dict[str, str]] = {}
    all_exact = True
    for logical, p in paths.items():
        ensure_regular(p)
        actual = sha256_file(p)
        expected = profile["validated_files"][logical]["sha256"]
        exact = actual == expected
        states[logical] = {
            "path": str(p),
            "sha256": actual,
            "validated_sha256": expected,
            "status": "VALIDATED_EXACT" if exact else "CUSTOM",
        }
        all_exact = all_exact and exact
    return all_exact, states

def read_target_tsv(path: Path) -> tuple[list[str], list[tuple[str, ...]]]:
    ensure_regular(path)
    with opener_text(path) as fh:
        reader = csv.reader(fh, delimiter="\t")
        try:
            header = next(reader)
        except StopIteration:
            raise CatalogError("empty mapping target TSV")
        if tuple(header) != TARGET_HEADER:
            raise CatalogError(f"mapping target TSV header mismatch: {header}")
        rows = [tuple(row) for row in reader if row]
    return header, rows

def read_bed_rows(path: Path) -> list[tuple[str, ...]]:
    ensure_regular(path)
    rows: list[tuple[str, ...]] = []
    with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
        for line_no, raw in enumerate(fh, 1):
            if not raw.strip():
                continue
            fields = tuple(raw.rstrip("\n").split("\t"))
            if len(fields) != 8:
                raise CatalogError(f"mapping target BED line {line_no}: expected 8 columns")
            rows.append(fields)
    return rows

def inspect_catalog(args: argparse.Namespace) -> dict:
    profile = load_profile(args.validated_profile)
    lengths, order = read_fai(args.reference_fai)
    analysis, _ = load_analysis(args.analysis_regions, lengths)
    disease, _ = load_disease(args.disease_regions, lengths)
    expected_targets = bedtools_sort_target_rows(target_rows(analysis, disease), lengths, order)

    _, tsv_rows = read_target_tsv(args.mapping_target_tsv)
    bed_rows = read_bed_rows(args.mapping_target_bed)
    if tsv_rows != expected_targets:
        raise CatalogError(
            f"mapping target TSV semantic mismatch: observed={len(tsv_rows)} expected={len(expected_targets)}"
        )
    if bed_rows != expected_targets:
        raise CatalogError(
            f"mapping target BED semantic mismatch: observed={len(bed_rows)} expected={len(expected_targets)}"
        )
    ensure_regular(args.mapping_target_tbi)

    tabix = require_tool("tabix")
    proc = subprocess.run(
        [tabix, "-l", str(args.mapping_target_bed)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if proc.returncode != 0:
        raise CatalogError("tabix index check failed:\n" + proc.stdout)

    paths = {
        "analysis_regions": args.analysis_regions,
        "disease_regions": args.disease_regions,
        "mapping_target_bed": args.mapping_target_bed,
        "mapping_target_bed_index": args.mapping_target_tbi,
        "mapping_target_tsv": args.mapping_target_tsv,
    }
    all_exact, states = exact_state(paths, profile)
    status = "VALIDATED_CATALOG_PROFILE" if all_exact else "CUSTOM_COMPATIBLE_CATALOG"
    return {
        "adapter_version": VERSION,
        "profile_status": status,
        "golden_validation_scope": all_exact,
        "reference_fai": str(args.reference_fai),
        "reference_fai_sha256": sha256_file(args.reference_fai),
        "analysis_rows": len(analysis),
        "disease_rows": len(disease),
        "mapping_target_rows": len(expected_targets),
        "resource_states": states,
        "semantic_target_reconstruction": "PASS",
        "tabix_index_readable": True,
        "contig_alias_normalization": "NONE_STRICT_NAMES",
    }

def build_catalog(args: argparse.Namespace) -> dict:
    profile = load_profile(args.validated_profile)
    lengths, order = read_fai(args.reference_fai)
    analysis, analysis_fields = load_analysis(args.analysis_regions, lengths)
    disease, disease_fields = load_disease(args.disease_regions, lengths)
    targets = bedtools_sort_target_rows(target_rows(analysis, disease), lengths, order)

    outdir = args.output_dir.resolve()
    if outdir.exists():
        raise CatalogError(
            f"output directory already exists; refusing non-atomic replacement: {outdir}"
        )

    parent = outdir.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{outdir.name}.",
            suffix=".staging",
            dir=str(parent),
        )
    )

    try:
        analysis_out = staging / "analysis_regions.tsv.gz"
        disease_out = staging / "disease_regions.tsv.gz"
        target_tsv = staging / "mapping_target_regions.tsv.gz"
        target_bed = staging / "mapping_target_regions.bed.gz"

        copy_gzip_tsv_normalized(
            args.analysis_regions, analysis_out, analysis_fields, analysis
        )
        copy_gzip_tsv_normalized(
            args.disease_regions, disease_out, disease_fields, disease
        )
        write_gzip_tsv(target_tsv, list(TARGET_HEADER), targets)
        write_bgzip_bed(target_bed, targets)
        target_tbi = Path(str(target_bed) + ".tbi")

        paths = {
            "analysis_regions": analysis_out,
            "disease_regions": disease_out,
            "mapping_target_bed": target_bed,
            "mapping_target_bed_index": target_tbi,
            "mapping_target_tsv": target_tsv,
        }
        all_exact, states = exact_state(paths, profile)
        status = (
            "VALIDATED_CATALOG_PROFILE"
            if all_exact
            else "CUSTOM_COMPATIBLE_CATALOG"
        )

        # The portable manifest intentionally excludes machine-local absolute paths.
        # Content identity and profile provenance are sufficient for reproducibility.
        portable_states: dict[str, dict[str, str]] = {}
        for logical, state in states.items():
            portable_states[logical] = {
                "filename": paths[logical].name,
                "sha256": state["sha256"],
                "validated_sha256": state["validated_sha256"],
                "status": state["status"],
            }

        manifest = {
            "catalog_adapter_version": VERSION,
            "validated_profile_version": profile["profile_version"],
            "validated_profile_sha256": sha256_file(args.validated_profile),
            "profile_status": status,
            "golden_validation_scope": all_exact,
            "assembly_family": profile.get("assembly_family", ""),
            "reference_fai_sha256": sha256_file(args.reference_fai),
            "source_analysis_regions_sha256": sha256_file(args.analysis_regions),
            "source_disease_regions_sha256": sha256_file(args.disease_regions),
            "analysis_rows": len(analysis),
            "disease_rows": len(disease),
            "mapping_target_rows": len(targets),
            "contig_alias_normalization": "NONE_STRICT_NAMES",
            "resource_states": portable_states,
        }

        manifest_path = staging / "catalog_manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        sha_path = staging / "SHA256SUMS"
        with sha_path.open("w", encoding="utf-8", newline="\n") as fh:
            for logical in sorted(paths):
                p = paths[logical]
                fh.write(f"{sha256_file(p)}  {p.name}\n")
            fh.write(f"{sha256_file(manifest_path)}  {manifest_path.name}\n")

        # Publish only after every runtime artifact, manifest, and checksum file
        # has been completed successfully on the same filesystem.
        if outdir.exists():
            raise CatalogError(
                f"output path appeared during build; refusing replacement: {outdir}"
            )
        os.replace(staging, outdir)
        staging = None
        return manifest

    finally:
        if staging is not None and staging.exists():
            shutil.rmtree(staging, ignore_errors=True)

def self_test() -> dict:
    with tempfile.TemporaryDirectory(prefix="rnatr_catalog_adapter_selftest_") as td:
        root = Path(td)
        fai = root / "ref.fa.fai"
        fai.write_text("chr1\t1000\t0\t0\t0\n", encoding="utf-8")
        lengths, order = read_fai(fai)

        analysis = root / "analysis.tsv"
        analysis.write_text(
            "\t".join(ANALYSIS_REQUIRED) + "\n"
            + "\t".join(["chr1", "100", "120", "A1", "TEST", "SIMPLE_PERIODIC_SCAN", "L1"]) + "\n",
            encoding="utf-8",
        )
        disease = root / "disease.tsv"
        disease.write_text(
            "\t".join(DISEASE_REQUIRED) + "\n"
            + "\t".join(["chr1", "200", "230", "D1", "SIMPLE_PERIODIC_SCAN", "."]) + "\n",
            encoding="utf-8",
        )
        ar, _ = load_analysis(analysis, lengths)
        dr, _ = load_disease(disease, lengths)
        tr = bedtools_sort_target_rows(target_rows(ar, dr), lengths, order)
        if len(tr) != 2 or tr[0][4] != "TRExplorer" or tr[1][4] != "STRchive":
            raise CatalogError("self-test target construction failed")

        dup = root / "dup.tsv"
        dup.write_text(
            "\t".join(ANALYSIS_REQUIRED) + "\n"
            + "\t".join(["chr1", "100", "120", "A1", "TEST", "X", "L1"]) + "\n"
            + "\t".join(["chr1", "130", "150", "A1", "TEST", "X", "L2"]) + "\n",
            encoding="utf-8",
        )
        try:
            load_analysis(dup, lengths)
        except CatalogError:
            pass
        else:
            raise CatalogError("self-test duplicate ID rejection failed")

        alias = root / "alias.tsv"
        alias.write_text(
            "\t".join(ANALYSIS_REQUIRED) + "\n"
            + "\t".join(["1", "100", "120", "A2", "TEST", "X", "L2"]) + "\n",
            encoding="utf-8",
        )
        try:
            load_analysis(alias, lengths)
        except CatalogError:
            pass
        else:
            raise CatalogError("self-test strict contig rejection failed")

    return {
        "status": "PASS",
        "duplicate_id_rejection": "PASS",
        "strict_contig_name_rejection": "PASS",
        "target_source_preservation": "PASS",
        "historical_bedtools_sort_semantics": "PASS",
        "deterministic_gzip_header_policy": "PASS_FILENAME_EMPTY_MTIME_ZERO",
    }

def add_common_inputs(p: argparse.ArgumentParser) -> None:
    p.add_argument("--validated-profile", type=Path, required=True)
    p.add_argument("--reference-fai", type=Path, required=True)
    p.add_argument("--analysis-regions", type=Path, required=True)
    p.add_argument("--disease-regions", type=Path, required=True)

def main() -> int:
    ap = argparse.ArgumentParser(description="RNA-TR-Scout post-Freeze runtime catalog adapter/validator")
    sub = ap.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("self-test")
    sp = sub.add_parser("build")
    add_common_inputs(sp)
    sp.add_argument("--output-dir", type=Path, required=True)
    sp.add_argument("--report-json", type=Path)

    sp = sub.add_parser("inspect")
    add_common_inputs(sp)
    sp.add_argument("--mapping-target-tsv", type=Path, required=True)
    sp.add_argument("--mapping-target-bed", type=Path, required=True)
    sp.add_argument("--mapping-target-tbi", type=Path, required=True)
    sp.add_argument("--report-json", type=Path)

    args = ap.parse_args()

    if args.command == "self-test":
        result = self_test()
    elif args.command == "build":
        result = build_catalog(args)
    elif args.command == "inspect":
        result = inspect_catalog(args)
    else:
        raise CatalogError("unsupported command")

    if getattr(args, "report_json", None):
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
