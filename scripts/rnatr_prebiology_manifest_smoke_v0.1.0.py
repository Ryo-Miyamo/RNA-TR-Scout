#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable, Iterator

try:
    import pysam
except Exception as exc:  # pragma: no cover - depends on runtime env
    pysam = None
    PYSAM_IMPORT_ERROR = exc
else:
    PYSAM_IMPORT_ERROR = None

VERSION = "rnatr_prebiology_manifest_interface_smoke_v0.1.0"
MANIFEST_VERSION = "rnatr_core_result_manifest_v0.1.0"
BINDING_VERSION = "rnatr_local_resource_bindings_v0.1.0"


class SmokeError(RuntimeError):
    pass


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
        raise SmokeError(f"required regular file missing/invalid: {path}")
    if nonempty and path.stat().st_size == 0:
        raise SmokeError(f"required file is empty: {path}")


def write_tsv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + f".part.{os.getpid()}")
    with tmp.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh, delimiter="\t", lineterminator="\n", fieldnames=fields,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def load_json(path: Path) -> dict[str, Any]:
    ensure_regular(path)
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise SmokeError(f"JSON root is not an object: {path}")
    return obj


def reject_absolute_paths(value: Any, pointer: str = "$") -> None:
    """Reject machine-local absolute paths anywhere in the portable manifest."""
    if isinstance(value, dict):
        for key, item in value.items():
            reject_absolute_paths(item, f"{pointer}/{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            reject_absolute_paths(item, f"{pointer}/{index}")
    elif isinstance(value, str):
        # URI-like references are allowed; native absolute paths are not.
        if value.startswith(("/", "file:/", "file://")):
            raise SmokeError(f"portable manifest contains absolute path at {pointer}: {value}")


def validate_relative_artifact_path(text: str) -> Path:
    path = Path(text)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise SmokeError(f"unsafe/non-portable artifact path: {text}")
    # Artifact paths must be package-relative and must not expose Stage/dataset layout.
    lowered = text.lower()
    forbidden = ("stage15", "encsr", "/mnt/", "/media/", "/home/")
    if any(token in lowered for token in forbidden):
        raise SmokeError(f"artifact path leaks Stage/dataset/developer binding: {text}")
    return path


def iter_tsv(path: Path) -> Iterator[dict[str, str]]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        if reader.fieldnames is None:
            raise SmokeError(f"missing TSV header: {path}")
        yield from reader


def resource_path(bindings: dict[str, Any], logical_id: str) -> Path:
    resources = bindings.get("resources")
    if not isinstance(resources, dict) or logical_id not in resources:
        raise SmokeError(f"binding missing resource: {logical_id}")
    entry = resources[logical_id]
    if not isinstance(entry, dict) or not entry.get("path"):
        raise SmokeError(f"invalid binding entry: {logical_id}")
    return Path(str(entry["path"])).expanduser().resolve()


def validate_resource_hashes(manifest: dict[str, Any], bindings: dict[str, Any]) -> list[dict[str, Any]]:
    resources = manifest.get("resources")
    if not isinstance(resources, dict) or not resources:
        raise SmokeError("portable manifest has no resources")
    rows: list[dict[str, Any]] = []
    for logical_id, entry in sorted(resources.items()):
        if not isinstance(entry, dict):
            raise SmokeError(f"invalid resource entry: {logical_id}")
        if str(entry.get("logical_id")) != logical_id:
            raise SmokeError(f"logical resource ID mismatch: {logical_id}")
        path = resource_path(bindings, logical_id)
        ensure_regular(path)
        actual = sha256_file(path)
        expected = str(entry.get("sha256", ""))
        status = "PASS" if expected and actual == expected else "FAIL"
        rows.append({
            "logical_id": logical_id,
            "kind": str(entry.get("kind", ".")),
            "path": str(path),
            "bytes": path.stat().st_size,
            "expected_sha256": expected,
            "actual_sha256": actual,
            "status": status,
        })
        if status != "PASS":
            raise SmokeError(f"resource SHA mismatch: {logical_id}: {path}")
    return rows


def find_artifact(manifest: dict[str, Any], logical_name: str, package_root: Path) -> Path:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise SmokeError("portable manifest artifacts is not a list")
    matches = [entry for entry in artifacts
               if isinstance(entry, dict) and str(entry.get("logical_name")) == logical_name]
    if len(matches) != 1:
        raise SmokeError(f"artifact multiplicity mismatch for {logical_name}: {len(matches)}")
    rel = validate_relative_artifact_path(str(matches[0].get("path", "")))
    path = package_root / rel
    ensure_regular(path)
    expected = str(matches[0].get("sha256", ""))
    actual = sha256_file(path)
    if not expected or expected != actual:
        raise SmokeError(f"artifact SHA mismatch: {logical_name}: {path}")
    return path


def primary_bam_records(bam: Path, read_ids: set[str]) -> dict[str, list[dict[str, Any]]]:
    if pysam is None:
        raise SmokeError(f"pysam import failed: {PYSAM_IMPORT_ERROR}")
    found: dict[str, list[dict[str, Any]]] = {rid: [] for rid in read_ids}
    with pysam.AlignmentFile(str(bam), "rb") as handle:
        for record in handle.fetch(until_eof=True):
            rid = record.query_name
            if rid not in found or record.is_secondary or record.is_supplementary:
                continue
            found[rid].append({
                "read_id": rid,
                "reference_name": record.reference_name if record.reference_name is not None else ".",
                "reference_start": record.reference_start,
                "reference_end": record.reference_end,
                "strand": "-" if record.is_reverse else "+",
                "mapq": record.mapping_quality,
                "cigar": record.cigarstring or ".",
            })
    return found


def locus_columns(header: Iterable[str]) -> tuple[str, ...]:
    candidates = (
        "representative_locus_id", "locus_id", "matched_trexplorer_locus_id",
        "trexplorer_locus_id",
    )
    header_set = set(header)
    return tuple(name for name in candidates if name in header_set)


def catalog_matches(
    catalog: Path,
    keys: set[tuple[str, str, str]],
) -> dict[tuple[str, str, str], list[dict[str, str]]]:
    opener = gzip.open if catalog.suffix == ".gz" else open
    matches: dict[tuple[str, str, str], list[dict[str, str]]] = {key: [] for key in keys}
    with opener(catalog, "rt", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        if (reader.fieldnames is None or "target_region_id" not in reader.fieldnames
                or "target_source" not in reader.fieldnames):
            raise SmokeError(f"mapping target catalog lacks target_source/target_region_id: {catalog}")
        locus_fields = locus_columns(reader.fieldnames)
        if not locus_fields:
            raise SmokeError(f"mapping target catalog lacks a recognized locus field: {catalog}")
        for row in reader:
            source = row.get("target_source", "")
            target = row.get("target_region_id", "")
            row_loci = {row.get(field, "") for field in locus_fields} - {"", "."}
            for locus in row_loci:
                key = (source, target, locus)
                if key in matches:
                    matches[key].append(row)
    return matches


def choose_joinable_evidence(
    evidence_path: Path,
    catalog_path: Path,
    bam_path: Path,
) -> tuple[dict[str, str], dict[str, Any], dict[str, str]]:
    required = ("read_id", "target_source", "target_region_id", "locus_id", "evidence_id")
    candidates: list[dict[str, str]] = []
    for row in iter_tsv(evidence_path):
        if any(row.get(key, "") in ("", ".") for key in required):
            continue
        candidates.append(row)
        if len(candidates) >= 10000:
            break
    if not candidates:
        raise SmokeError("read_evidence has no complete join-key row")

    keys = {(row["target_source"], row["target_region_id"], row["locus_id"]) for row in candidates}
    catalog_by_key = catalog_matches(catalog_path, keys)
    read_ids = {row["read_id"] for row in candidates}
    bam_by_read = primary_bam_records(bam_path, read_ids)
    for row in candidates:
        key = (row["target_source"], row["target_region_id"], row["locus_id"])
        catalog_rows = catalog_by_key.get(key, [])
        bam_rows = bam_by_read.get(row["read_id"], [])
        if len(catalog_rows) == 1 and len(bam_rows) == 1:
            return row, bam_rows[0], catalog_rows[0]
    raise SmokeError("no read_evidence row resolved uniquely to both BAM and pinned catalog")

def run_smoke(manifest_path: Path, bindings_path: Path, output_qc: Path) -> int:
    if pysam is None:
        raise SmokeError(f"pysam import failed: {PYSAM_IMPORT_ERROR}")
    manifest_path = manifest_path.resolve()
    bindings_path = bindings_path.resolve()
    manifest = load_json(manifest_path)
    bindings = load_json(bindings_path)
    if manifest.get("manifest_version") != MANIFEST_VERSION:
        raise SmokeError("unsupported Core result manifest version")
    if bindings.get("binding_version") != BINDING_VERSION:
        raise SmokeError("unsupported local resource-binding version")
    reject_absolute_paths(manifest)

    join_contract = manifest.get("join_key_contract")
    for key in ("read_id", "locus_id", "target_source", "target_region_id", "evidence_id"):
        if not isinstance(join_contract, dict) or key not in join_contract:
            raise SmokeError(f"portable manifest lacks join-key contract: {key}")

    resource_rows = validate_resource_hashes(manifest, bindings)
    package_root = manifest_path.parent
    evidence = find_artifact(manifest, "read_evidence.tsv", package_root)
    bam = resource_path(bindings, "source_bam")
    catalog = resource_path(bindings, "catalog:mapping_target_tsv")
    selected, bam_row, catalog_row = choose_joinable_evidence(evidence, catalog, bam)

    rows = [
        {"check": "portable_manifest_has_no_absolute_paths", "value": "true", "status": "PASS"},
        {"check": "resource_hashes", "value": len(resource_rows), "status": "PASS"},
        {"check": "read_id", "value": selected["read_id"], "status": "PASS"},
        {"check": "target_source", "value": selected["target_source"], "status": "PASS"},
        {"check": "target_region_id", "value": selected["target_region_id"], "status": "PASS"},
        {"check": "locus_id", "value": selected["locus_id"], "status": "PASS"},
        {"check": "evidence_id", "value": selected["evidence_id"], "status": "PASS"},
        {"check": "bam_reference", "value": bam_row["reference_name"], "status": "PASS"},
        {"check": "bam_reference_start", "value": bam_row["reference_start"], "status": "PASS"},
        {"check": "bam_reference_end", "value": bam_row["reference_end"], "status": "PASS"},
        {"check": "bam_strand", "value": bam_row["strand"], "status": "PASS"},
        {"check": "bam_mapq", "value": bam_row["mapq"], "status": "PASS"},
        {"check": "catalog_target_source", "value": catalog_row.get("target_source", "."), "status": "PASS"},
        {"check": "catalog_target_region_id", "value": catalog_row["target_region_id"], "status": "PASS"},
        {"check": "catalog_chrom", "value": catalog_row.get("chrom", "."), "status": "PASS"},
        {"check": "catalog_start", "value": catalog_row.get("start", "."), "status": "PASS"},
        {"check": "catalog_end", "value": catalog_row.get("end", "."), "status": "PASS"},
        {"check": "catalog_annotation_join", "value": "PASS", "status": "PASS"},
        {"check": "stage_or_dataset_path_dependency", "value": "false", "status": "PASS"},
        {"check": "prebiology_interface_smoke", "value": "PASS", "status": "PASS"},
    ]
    write_tsv(output_qc, rows, ["check", "value", "status"])
    print("PREBIOLOGY_INTERFACE_SMOKE\tPASS")
    print(f"read_id\t{selected['read_id']}")
    print(f"target_source\t{selected['target_source']}")
    print(f"target_region_id\t{selected['target_region_id']}")
    print(f"locus_id\t{selected['locus_id']}")
    print(f"evidence_id\t{selected['evidence_id']}")
    print(f"QC\t{output_qc.resolve()}")
    return 0


def self_test() -> int:
    with tempfile.TemporaryDirectory(prefix="rnatr_prebiology_smoke_selftest_") as td:
        root = Path(td)
        manifest = {
            "manifest_version": MANIFEST_VERSION,
            "resources": {},
            "artifacts": [{"logical_name": "read_evidence.tsv", "path": "read_evidence.tsv"}],
            "join_key_contract": {key: "x" for key in
                                  ("read_id", "locus_id", "target_source", "target_region_id", "evidence_id")},
        }
        reject_absolute_paths(manifest)
        validate_relative_artifact_path("read_evidence.tsv")
        try:
            reject_absolute_paths({"x": "/mnt/example"})
        except SmokeError:
            pass
        else:
            raise SmokeError("self-test absolute-path rejection failed")
        try:
            validate_relative_artifact_path("stage15/read_evidence.tsv")
        except SmokeError:
            pass
        else:
            raise SmokeError("self-test Stage-path rejection failed")
        catalog = root / "catalog.tsv.gz"
        with gzip.open(catalog, "wt", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(
                fh, delimiter="\t", lineterminator="\n",
                fieldnames=["target_source", "target_region_id", "representative_locus_id", "chrom", "start", "end"],
            )
            writer.writeheader()
            writer.writerow({
                "target_source": "ANALYSIS", "target_region_id": "target1", "representative_locus_id": "locus1",
                "chrom": "chr1", "start": "10", "end": "20",
            })
        rows = catalog_matches(catalog, {("ANALYSIS", "target1", "locus1")})[("ANALYSIS", "target1", "locus1")]
        if len(rows) != 1 or rows[0]["target_region_id"] != "target1":
            raise SmokeError("self-test catalog resolver failed")
    print("SELF_TEST\tPASS")
    print(f"version\t{VERSION}")
    if pysam is None:
        print("pysam_runtime_test\tSKIPPED_NOT_INSTALLED_IN_BUILD_ENV")
    else:
        print("pysam_runtime_test\tAVAILABLE")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--bindings", type=Path)
    parser.add_argument("--output-qc", type=Path)
    args = parser.parse_args()
    if args.self_test:
        if any(value is not None for value in (args.manifest, args.bindings, args.output_qc)):
            parser.error("--self-test cannot be combined with runtime arguments")
        return self_test()
    if any(value is None for value in (args.manifest, args.bindings, args.output_qc)):
        parser.error("--manifest, --bindings and --output-qc are required")
    return run_smoke(args.manifest, args.bindings, args.output_qc)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=os.sys.stderr)
        raise
