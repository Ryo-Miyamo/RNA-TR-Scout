#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import heapq
import json
import math
import multiprocessing as mp
import os
import pickle
import shutil
import statistics
import subprocess
import sys
import tarfile
import tempfile
import time
import traceback
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

VERSION = "rnatr_stage15d_g31_row_expansion_audit_v0.1.0"
PROJECT_ROOT = Path("/mnt/intelssd/rnatr_project")
DOWNLOADS = Path.home() / "Downloads"

FULL_RUN_ID = "ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1"
FULL_VERSION = "v0.1.6"
FULL_RESULT_ROOT = (
    PROJECT_ROOT / "results/15_stage15c_fullscale_bam_to_final"
    / FULL_RUN_ID / FULL_VERSION
)
FULL_SHARDS_ROOT = FULL_RESULT_ROOT / "shards"
FULL_PACKAGE = FULL_RESULT_ROOT / "package_full"
FULL_QC_ROOT = (
    PROJECT_ROOT / "qc/15_stage15c_fullscale_bam_to_final"
    / FULL_RUN_ID / FULL_VERSION
)
FULL_QC = FULL_QC_ROOT / "stage15c_full_empirical_run.qc.tsv"
FULL_CHECKPOINT = FULL_QC_ROOT / "stage15c_fullscale_checkpoint_manifest.tsv"
FULL_PACKAGE_MANIFEST = FULL_PACKAGE / "package_manifest.tsv"
FULL_VALIDATOR_QC = (
    FULL_QC_ROOT / "validators/memory_bounded_prepublication"
    / "memory_bounded_validator.qc.tsv"
)
FULL_GLOBAL_ID_UNIQUENESS = (
    FULL_QC_ROOT / "validators/memory_bounded_prepublication"
    / "global_id_uniqueness.tsv"
)
FULL_RUNNER = PROJECT_ROOT / "scripts/rnatr_stage15c_run_full5312696_bam_to_final_v0.1.6.py"
RUNTIME_PATH_AMENDMENT = (
    PROJECT_ROOT / "metadata/stage15c/runtime_path_binding_amendment_v0.1.6"
    / "rnatr_stage15c_runtime_path_binding_amendment_v0.1.6.json"
)
BOUND_SOURCE_ROOT = PROJECT_ROOT / "scripts/stage15c/full5312696_runtime_bound_v0.1.6"
BOUND_11B = BOUND_SOURCE_ROOT / "11b_extract_alignment_segments_and_target_candidates.stage15c_full5312696_runtime_bound_v0.1.6.sh"
BOUND_11D3 = BOUND_SOURCE_ROOT / "11d3_project_targets_to_raw_reads.stage15c_full5312696_runtime_bound_v0.1.6.sh"
BOUND_11E = BOUND_SOURCE_ROOT / "11e_prepare_motif_scan_jobs.stage15c_full5312696_runtime_bound_v0.1.6.sh"

EXPECTED_GUARDS = {
    FULL_QC: "3b95addc1e7aa50ddf22d90dab3373025b9c7b41569fcb2aaea7d2910b35fd07",
    FULL_CHECKPOINT: "f00d67e28413d66730b8c2ffab0f52b9ce9e1553e5cc9a3f9d768e4a7a0083b4",
    FULL_PACKAGE_MANIFEST: "335058228a3f3c4205161f3d24b208009175aed5e50f995a74e04100b4f3a738",
    FULL_VALIDATOR_QC: "ff32021f730d7c16f2aa4a8788d803bb49d3a07c42642cbdee412387797d1794",
    FULL_GLOBAL_ID_UNIQUENESS: "20268319ab0825de5dccf257c8c9a52367cadeacd342f14e902811303900295c",
    FULL_RUNNER: "cca6b2d4c6e773392d3a8c24cd2fd2a1f0a41a713338b4ccdec1ba7fab5bafcc",
    RUNTIME_PATH_AMENDMENT: "c972777c13834ca9c16bc7d4aaecbebb20d46d3518d266a851f17a7b4751d97a",
    BOUND_11B: "bc7523c081434ba7e545a3191aad4e7cb8c4e9d4c1ca771b3658399875a7fcd8",
    BOUND_11D3: "aa91b0ec33caee71c223ea6ac161de2b2ceb0095ae33a404f85bba51a81553c3",
    BOUND_11E: "23c02846128b4cddefdba6879bbd731b30d552d70e9070b5d9122aebf7e5c0e2",
}

EXPECTED_FULL = {
    "input_reads": 5_312_696,
    "alignment_records": 9_774_085,
    "primary_mapped_reads": 5_123_713,
    "primary_unmapped_reads": 188_983,
    "candidate_rows": 20_656_258,
    "candidate_reads": 4_212_263,
    "projection_rows": 20_656_258,
    "projection_reads": 4_212_263,
    "caller_attempt_rows": 20_656_258,
    "general_repeat_calls_rows": 20_656_258,
    "read_evidence_rows": 20_656_258,
    "repeat_events_rows": 8_523_140,
    "repeat_segments_rows": 8_573_315,
    "repeat_interruptions_rows": 43_399,
    "shards": 144,
}

RUN_500K = "ENCSR307SHM_stage15a500k_seed20260809_mm2splice_v1"
ROOT_500K = (
    PROJECT_ROOT / "results/15_stage15a_bam_to_final" / RUN_500K
    / "v0.1.1_500k_scaling/replicate_A"
)
SHARDS_500K = ROOT_500K / "shards"
QC_500K = (
    PROJECT_ROOT / "qc/15_stage15a_bam_to_final" / RUN_500K
    / "v0.1.1_500k_scaling/stage15a_scaling_500k.qc.tsv"
)
QC_500K_SHA256 = "ef27be62e633e941b21978d8354a928a7ecea33600465fe6620e82640b329e82"
EXPECTED_500K = {
    "input_reads": 500_000,
    "candidate_rows": 1_948_859,
    "candidate_reads": 396_549,
    "projection_rows": 1_948_859,
    "caller_attempt_rows": 1_948_859,
    "general_repeat_calls_rows": 1_948_859,
    "read_evidence_rows": 1_948_859,
}
RUN_100K = "ENCSR307SHM_pilot100k_mm2splice_v1"
ROOT_100K = (
    PROJECT_ROOT / "results/15_stage15a_bam_to_final" / RUN_100K
    / "v0.2.2.1_performance"
)
SHARDS_100K = ROOT_100K / "shards"

TARGET_BED = (
    PROJECT_ROOT / "catalogs/trexplorer_v2/rnatr_pilot_v03/final"
    / "RNA-TR-Scout_v0.3.mapping_target_regions.bed.gz"
)
GENOME_FAI = PROJECT_ROOT / "refs/gencode_v50/GRCh38.primary_assembly.genome.fa.fai"
TARGET_PADDING_BP = 500
EXPECTED_TARGET_ROWS = 349_490

QC_ROOT = (
    PROJECT_ROOT / "qc/15_stage15d_g31_row_expansion_audit"
    / FULL_RUN_ID / "v0.1.0"
)
WORK_ROOT = (
    PROJECT_ROOT / "work/15_stage15d_g31_row_expansion_audit"
    / FULL_RUN_ID / "v0.1.0"
)
DOC_PATH = (
    PROJECT_ROOT / "docs/stage15d"
    / "RNA_TR_Scout_G31_fullscale_row_expansion_and_candidate_entry_audit_v0.1.0.md"
)
GATE_PATH = PROJECT_ROOT / "validation/core_freeze_g31_row_expansion_gate_v0.1.0.tsv"
SCRIPT_INSTALL = PROJECT_ROOT / "scripts/rnatr_stage15d_g31_row_expansion_audit_v0.1.0.py"
SUCCESS_BUNDLE = DOWNLOADS / "rnatr_stage15d_g31_row_expansion_audit_v0.1.0.tar.gz"
FAILURE_BUNDLE = DOWNLOADS / "rnatr_stage15d_g31_row_expansion_audit_v0.1.0_failure.tar.gz"
MINIMUM_FREE_BYTES = 60_000_000_000
TOP_DOSSIER_ROWS = 5000

REQUIRED_ROLES = (
    "assignment",
    "projection",
    "motif_jobs",
    "caller_calls",
    "materialized_general_repeat_calls",
    "materialized_read_evidence",
)

ASSIGNMENT_REQUIRED = {
    "read_id", "target_region_id", "target_source", "region_type",
    "analysis_mode", "representative_locus_id", "assignment_rank",
    "read_candidate_target_count", "best_alignment_id",
    "best_alignment_class", "candidate_basis", "target_overlap_bp",
    "target_distance_bp", "primary_support", "supplementary_support",
    "secondary_support",
}
PROJECTION_REQUIRED = {
    "projection_id", "read_id", "target_region_id", "target_source",
    "representative_locus_id", "assignment_rank",
    "read_candidate_target_count", "best_alignment_id", "candidate_basis",
    "geometry_class", "potential_evidence_class", "projection_status",
}
JOBS_REQUIRED = {
    "projection_id", "read_id", "target_region_id", "target_source",
    "representative_locus_id", "assignment_rank",
    "read_candidate_target_count", "candidate_basis", "canonical_motifs",
    "motif_candidates", "motif_count", "scan_strategy",
    "motif_scan_eligible", "manual_review_required",
}
CALLER_REQUIRED = {
    "projection_id", "read_id", "target_region_id", "target_source",
    "representative_locus_id", "assignment_rank",
    "read_candidate_target_count", "catalog_motifs", "integration_status",
    "canonical_motif", "hypothesis_count",
}
GENERAL_REQUIRED = {
    "caller_record_id", "evidence_id", "projection_id", "read_id",
    "target_region_id", "target_source", "representative_locus_id",
    "assignment_rank", "read_candidate_target_count", "integration_status",
    "canonical_motif", "hypothesis_count",
}
EVIDENCE_REQUIRED = {
    "evidence_id", "read_id", "target_region_id", "target_source",
    "locus_id", "canonical_motif", "best_projection_id",
    "best_caller_record_id", "caller_attempt_count", "hypothesis_count",
}

G_TARGET_META: dict[tuple[str, str], tuple[str, str, str, str, int, int]] = {}
G_SHARD_COUNT = 0
G_PROFILE = ""
G_RESULT_DIR: Path | None = None


class AuditError(RuntimeError):
    pass


@dataclass(frozen=True)
class Profile:
    name: str
    input_reads: int
    shards_root: Path
    expected_shards: int
    required: bool = True


def sha256_file(path: Path, chunk_size: int = 4 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(chunk_size), b""):
            h.update(block)
    return h.hexdigest()


def ensure_file(path: Path) -> None:
    if not path.is_file() or path.stat().st_size <= 0:
        raise AuditError(f"missing or empty file: {path}")


def open_text(path: Path):
    if str(path).endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8", newline="")
    return path.open("r", encoding="utf-8", newline="")


def read_metrics(path: Path) -> dict[str, str]:
    ensure_file(path)
    result: dict[str, str] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        next(reader, None)
        for row in reader:
            if len(row) >= 2:
                result[row[0]] = row[1]
    return result


def read_dict_rows(path: Path) -> list[dict[str, str]]:
    ensure_file(path)
    with open_text(path) as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise AuditError(f"missing TSV header: {path}")
        return [dict(row) for row in reader]


def write_tsv(path: Path, fieldnames: Sequence[str], rows: Iterable[Mapping[str, Any]], *, gzip_output: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + f".part.{os.getpid()}")
    use_gzip = gzip_output or str(path).endswith(".gz")
    if use_gzip:
        raw = tmp.open("wb")
        gz = gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=1, mtime=0)
        handle = io.TextIOWrapper(gz, encoding="utf-8", newline="")
    else:
        raw = None
        gz = None
        handle = tmp.open("w", encoding="utf-8", newline="")
    try:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), delimiter="\t", lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    finally:
        handle.close()
        if raw is not None and not raw.closed:
            raw.close()
    os.replace(tmp, path)


def write_metrics(path: Path, rows: Iterable[tuple[str, Any]]) -> None:
    write_tsv(path, ["metric", "value"], ({"metric": k, "value": v} for k, v in rows))


def stable_row_digest(row: Mapping[str, str], fields: Sequence[str]) -> bytes:
    h = hashlib.blake2b(digest_size=16)
    for field in fields:
        h.update(row.get(field, "").encode("utf-8", errors="surrogatepass"))
        h.update(b"\0")
    return h.digest()


def bool_value(value: str) -> bool:
    return value.strip().lower() == "true"


def int_value(value: str, default: int = 0) -> int:
    value = value.strip()
    if value in {"", ".", "NA", "None"}:
        return default
    return int(value)


def split_csv_tokens(value: str) -> tuple[str, ...]:
    if not value or value == ".":
        return ()
    return tuple(dict.fromkeys(token.strip().upper() for token in value.split(",") if token.strip()))


def normalized_locus(raw_locus: str, target: tuple[str, str]) -> str:
    raw_locus = raw_locus.strip()
    if raw_locus not in {"", ".", "NA", "None"}:
        return raw_locus
    return f"TARGET::{target[0]}::{target[1]}"


def shard_index(identifier: str, count: int) -> int:
    digest = hashlib.sha256(identifier.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % count


def assert_header(path: Path, fieldnames: Sequence[str] | None, required: set[str]) -> list[str]:
    if fieldnames is None:
        raise AuditError(f"missing TSV header: {path}")
    fields = list(fieldnames)
    missing = sorted(required - set(fields))
    if missing:
        raise AuditError(f"missing required columns in {path}: {','.join(missing)}")
    return fields


class SelectedTsv:
    """Fast TSV reader that materializes only required columns.

    Only required columns are materialized, avoiding a full 70-column
    DictReader allocation for the large v0.4.2 tables. Exact duplicate rows
    are implied by and rejected through the table's deterministic primary key.
    """

    def __init__(self, path: Path, required: set[str]) -> None:
        self.path = path
        self.required = required
        self.handle: Any | None = None
        self.fieldnames: list[str] = []
        self.indices: list[tuple[str, int]] = []

    def __enter__(self) -> "SelectedTsv":
        self.handle = open_text(self.path)
        header_line = self.handle.readline()
        if not header_line:
            raise AuditError(f"empty TSV: {self.path}")
        self.fieldnames = header_line.rstrip("\n\r").split("\t")
        assert_header(self.path, self.fieldnames, self.required)
        index = {field: i for i, field in enumerate(self.fieldnames)}
        self.indices = [(field, index[field]) for field in sorted(self.required)]
        return self

    def __iter__(self) -> Iterator[dict[str, str]]:
        if self.handle is None:
            raise AuditError("SelectedTsv is not open")
        expected_columns = len(self.fieldnames)
        for line_number, line in enumerate(self.handle, start=2):
            stripped = line.rstrip("\n\r")
            parts = stripped.split("\t")
            if len(parts) != expected_columns:
                raise AuditError(
                    f"TSV column-count mismatch path={self.path} line={line_number} "
                    f"expected={expected_columns} observed={len(parts)}"
                )
            yield {field: parts[position] for field, position in self.indices}

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.handle is not None:
            self.handle.close()
        self.handle = None


def one_glob(root: Path, pattern: str) -> Path:
    matches = sorted(root.glob(pattern))
    if len(matches) != 1:
        raise AuditError(f"expected exactly one match: root={root} pattern={pattern} observed={len(matches)}")
    ensure_file(matches[0])
    return matches[0]


def discover_shards(profile: Profile) -> list[dict[str, Any]]:
    if not profile.shards_root.is_dir():
        if profile.required:
            raise AuditError(f"missing shards root: {profile.shards_root}")
        return []
    shard_dirs = sorted(path for path in profile.shards_root.glob("shard_*") if path.is_dir())
    if len(shard_dirs) != profile.expected_shards:
        raise AuditError(
            f"unexpected shard count profile={profile.name}: "
            f"expected={profile.expected_shards} observed={len(shard_dirs)}"
        )
    rows: list[dict[str, Any]] = []
    for index, shard in enumerate(shard_dirs):
        expected_name = f"shard_{index:03d}"
        if shard.name != expected_name:
            raise AuditError(f"non-contiguous shard names: expected={expected_name} observed={shard.name}")
        rows.append({
            "profile": profile.name,
            "input_reads": profile.input_reads,
            "shard": shard.name,
            "shard_index": index,
            "shard_count": profile.expected_shards,
            "assignment": one_glob(shard, "project/results/11_assignment/*/read_target_candidates.tsv.gz"),
            "projection": one_glob(shard, "project/results/11_projection/*/v0.3.3/read_target_projection.v0.3.3.tsv.gz"),
            "motif_jobs": one_glob(shard, "project/results/11_motif_jobs/*/motif_scan_jobs.tsv.gz"),
            "caller_calls": one_glob(shard, "caller/general_repeat_calls.v0.4.0.tsv.gz"),
            "materialized_general_repeat_calls": one_glob(shard, "package_plain/general_repeat_calls.tsv"),
            "materialized_read_evidence": one_glob(shard, "package_plain/read_evidence.tsv"),
        })
    return rows


def checkpoint_role_map() -> dict[tuple[str, str], dict[str, str]]:
    ensure_file(FULL_CHECKPOINT)
    rows: dict[tuple[str, str], dict[str, str]] = {}
    with FULL_CHECKPOINT.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise AuditError("checkpoint manifest missing header")
        for row in reader:
            key = (row["shard"], row["role"])
            if key in rows:
                raise AuditError(f"duplicate checkpoint role: {key}")
            rows[key] = dict(row)
    return rows


def validate_full_shards_against_checkpoint(shards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    manifest = checkpoint_role_map()
    out: list[dict[str, Any]] = []
    for shard in shards:
        for role in REQUIRED_ROLES:
            key = (shard["shard"], role)
            if key not in manifest:
                raise AuditError(f"checkpoint role missing: {key}")
            row = manifest[key]
            path = Path(row["path"])
            if path != shard[role]:
                raise AuditError(f"checkpoint/discovery path mismatch {key}: {path} != {shard[role]}")
            ensure_file(path)
            bytes_ok = path.stat().st_size == int(row["bytes"])
            if not bytes_ok:
                raise AuditError(f"checkpoint size mismatch: {path}")
            out.append({
                "shard": shard["shard"], "role": role, "path": str(path),
                "expected_bytes": row["bytes"], "observed_bytes": path.stat().st_size,
                "checkpoint_sha256": row["sha256"], "status": "PASS_STAT_SIZE",
            })
    return out


def read_fai(path: Path) -> dict[str, int]:
    ensure_file(path)
    result: dict[str, int] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            fields = line.rstrip("\n").split("\t")
            if len(fields) >= 2:
                result[fields[0]] = int(fields[1])
    if not result:
        raise AuditError(f"empty FAI: {path}")
    return result


def interval_clusters(intervals: list[tuple[int, int, tuple[str, str]]], chrom: str, prefix: str) -> tuple[dict[tuple[str, str], str], list[dict[str, Any]]]:
    intervals = sorted(intervals, key=lambda x: (x[0], x[1], x[2]))
    mapping: dict[tuple[str, str], str] = {}
    rows: list[dict[str, Any]] = []
    if not intervals:
        return mapping, rows
    cluster_index = 0
    start, end, key = intervals[0]
    members = [key]
    for s, e, k in intervals[1:]:
        if s < end:
            end = max(end, e)
            members.append(k)
        else:
            cid = f"{prefix}:{chrom}:{cluster_index:06d}"
            unique_members = sorted(set(members))
            for member in unique_members:
                mapping[member] = cid
            rows.append({
                "cluster_id": cid, "chrom": chrom, "start": start, "end": end,
                "span_bp": end - start, "target_count": len(unique_members),
                "target_keys": ";".join(f"{a}|{b}" for a, b in unique_members),
            })
            cluster_index += 1
            start, end, members = s, e, [k]
    cid = f"{prefix}:{chrom}:{cluster_index:06d}"
    unique_members = sorted(set(members))
    for member in unique_members:
        mapping[member] = cid
    rows.append({
        "cluster_id": cid, "chrom": chrom, "start": start, "end": end,
        "span_bp": end - start, "target_count": len(unique_members),
        "target_keys": ";".join(f"{a}|{b}" for a, b in unique_members),
    })
    return mapping, rows


def interval_union_depth(intervals: list[tuple[int, int]]) -> tuple[int, int, int]:
    if not intervals:
        return 0, 0, 0
    events: list[tuple[int, int]] = []
    total = 0
    for start, end in intervals:
        if end <= start:
            continue
        total += end - start
        events.append((start, 1))
        events.append((end, -1))
    events.sort(key=lambda x: (x[0], x[1]))  # end before start at same coordinate
    depth = 0
    max_depth = 0
    union = 0
    previous: int | None = None
    for position, delta in events:
        if previous is not None and position > previous and depth > 0:
            union += position - previous
        depth += delta
        max_depth = max(max_depth, depth)
        previous = position
    return total, union, max_depth


def read_catalog_geometry() -> tuple[dict[tuple[str, str], tuple[str, str, str, str, int, int]], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    genome = read_fai(GENOME_FAI)
    ensure_file(TARGET_BED)
    raw_by_chrom: dict[str, list[tuple[int, int, tuple[str, str]]]] = defaultdict(list)
    padded_by_chrom: dict[str, list[tuple[int, int, tuple[str, str]]]] = defaultdict(list)
    raw_by_source_chrom: dict[str, dict[str, list[tuple[int, int]]]] = defaultdict(lambda: defaultdict(list))
    padded_by_source_chrom: dict[str, dict[str, list[tuple[int, int]]]] = defaultdict(lambda: defaultdict(list))
    preliminary: dict[tuple[str, str], tuple[str, str, str, int, int]] = {}
    exact_groups: dict[tuple[str, int, int], list[tuple[str, str]]] = defaultdict(list)
    source_counts = Counter()
    region_counts = Counter()
    with gzip.open(TARGET_BED, "rt", encoding="utf-8", newline="") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip() or line.startswith("#") or line.startswith("track") or line.startswith("browser"):
                continue
            fields = line.rstrip("\n").split("\t")
            if len(fields) < 8:
                raise AuditError(f"target BED has <8 columns at line {line_number}")
            chrom, start_text, end_text, target_id, source, region_type, analysis_mode, locus = fields[:8]
            try:
                start, end = int(start_text), int(end_text)
            except ValueError:
                if line_number == 1:
                    continue
                raise
            if chrom not in genome:
                raise AuditError(f"target chromosome absent from FAI: {chrom}")
            if not (0 <= start < end <= genome[chrom]):
                raise AuditError(f"invalid target interval: {chrom}:{start}-{end}")
            key = (source, target_id)
            if key in preliminary:
                raise AuditError(f"duplicate target key in BED: {key}")
            preliminary[key] = (locus or ".", region_type or ".", analysis_mode or ".", start, end)
            padded_start = max(0, start - TARGET_PADDING_BP)
            padded_end = min(genome[chrom], end + TARGET_PADDING_BP)
            raw_by_chrom[chrom].append((start, end, key))
            padded_by_chrom[chrom].append((padded_start, padded_end, key))
            raw_by_source_chrom[source][chrom].append((start, end))
            padded_by_source_chrom[source][chrom].append((padded_start, padded_end))
            exact_groups[(chrom, start, end)].append(key)
            source_counts[source] += 1
            region_counts[region_type] += 1

    raw_mapping: dict[tuple[str, str], str] = {}
    padded_mapping: dict[tuple[str, str], str] = {}
    raw_clusters: list[dict[str, Any]] = []
    padded_clusters: list[dict[str, Any]] = []
    raw_total = raw_union = raw_max_depth = 0
    padded_total = padded_union = padded_max_depth = 0
    for chrom in sorted(genome):
        mapping, clusters = interval_clusters(raw_by_chrom.get(chrom, []), chrom, "RAW")
        raw_mapping.update(mapping)
        raw_clusters.extend(clusters)
        mapping, clusters = interval_clusters(padded_by_chrom.get(chrom, []), chrom, "PAD500")
        padded_mapping.update(mapping)
        padded_clusters.extend(clusters)
        total, union, depth = interval_union_depth([(s, e) for s, e, _ in raw_by_chrom.get(chrom, [])])
        raw_total += total; raw_union += union; raw_max_depth = max(raw_max_depth, depth)
        total, union, depth = interval_union_depth([(s, e) for s, e, _ in padded_by_chrom.get(chrom, [])])
        padded_total += total; padded_union += union; padded_max_depth = max(padded_max_depth, depth)

    source_geometry_rows: list[dict[str, Any]] = []
    for source in sorted(source_counts):
        source_raw_total = source_raw_union = source_raw_depth = 0
        source_padded_total = source_padded_union = source_padded_depth = 0
        for chrom in genome:
            total, union, depth = interval_union_depth(raw_by_source_chrom[source].get(chrom, []))
            source_raw_total += total
            source_raw_union += union
            source_raw_depth = max(source_raw_depth, depth)
            total, union, depth = interval_union_depth(padded_by_source_chrom[source].get(chrom, []))
            source_padded_total += total
            source_padded_union += union
            source_padded_depth = max(source_padded_depth, depth)
        source_geometry_rows.append({
            "target_source": source,
            "target_count": source_counts[source],
            "raw_total_bp": source_raw_total,
            "raw_union_bp": source_raw_union,
            "raw_genome_fraction": f"{source_raw_union / sum(genome.values()):.12f}",
            "raw_redundancy_ratio": f"{source_raw_total / source_raw_union:.9f}" if source_raw_union else "0.000000000",
            "raw_max_overlap_depth": source_raw_depth,
            "padded500_total_bp": source_padded_total,
            "padded500_union_bp": source_padded_union,
            "padded500_genome_fraction": f"{source_padded_union / sum(genome.values()):.12f}",
            "padded500_redundancy_ratio": f"{source_padded_total / source_padded_union:.9f}" if source_padded_union else "0.000000000",
            "padded500_max_overlap_depth": source_padded_depth,
        })

    target_meta: dict[tuple[str, str], tuple[str, str, str, str, int, int]] = {}
    for key, (locus, region_type, analysis_mode, start, end) in preliminary.items():
        target_meta[key] = (locus, raw_mapping[key], padded_mapping[key], region_type, start, end)

    alias_rows: list[dict[str, Any]] = []
    for (chrom, start, end), keys in sorted(exact_groups.items()):
        if len(keys) > 1:
            alias_rows.append({
                "chrom": chrom, "start": start, "end": end,
                "target_count": len(keys),
                "target_keys": ";".join(f"{a}|{b}" for a, b in sorted(keys)),
            })
    genome_bp = sum(genome.values())
    if len(target_meta) != EXPECTED_TARGET_ROWS:
        raise AuditError(
            f"mapping-target catalog row mismatch: {len(target_meta)} != {EXPECTED_TARGET_ROWS}"
        )
    summary = {
        "catalog_targets": len(target_meta),
        "expected_catalog_targets": EXPECTED_TARGET_ROWS,
        "target_bed_sha256": sha256_file(TARGET_BED),
        "genome_fai_sha256": sha256_file(GENOME_FAI),
        "catalog_sources": len(source_counts),
        "genome_bp": genome_bp,
        "raw_interval_total_bp": raw_total,
        "raw_interval_union_bp": raw_union,
        "raw_genome_fraction": raw_union / genome_bp,
        "raw_redundancy_ratio": raw_total / raw_union if raw_union else 0.0,
        "raw_max_overlap_depth": raw_max_depth,
        "raw_overlap_clusters": len(raw_clusters),
        "raw_multitarget_clusters": sum(int(row["target_count"]) > 1 for row in raw_clusters),
        "padded_interval_total_bp": padded_total,
        "padded_interval_union_bp": padded_union,
        "padded_genome_fraction": padded_union / genome_bp,
        "padded_redundancy_ratio": padded_total / padded_union if padded_union else 0.0,
        "padded_max_overlap_depth": padded_max_depth,
        "padded_overlap_clusters": len(padded_clusters),
        "padded_multitarget_clusters": sum(int(row["target_count"]) > 1 for row in padded_clusters),
        "exact_coordinate_alias_groups": len(alias_rows),
        "exact_coordinate_alias_targets": sum(int(row["target_count"]) for row in alias_rows),
        "source_counts_json": json.dumps(source_counts, sort_keys=True),
        "region_type_counts_json": json.dumps(region_counts, sort_keys=True),
        "candidate_rate_interpretation_caution": "GENOME_FRACTION_IS_CONTEXT_ONLY_RNA_ALIGNMENTS_ARE_TRANSCRIBED_REGION_CONCENTRATED",
    }
    return target_meta, summary, alias_rows, raw_clusters, padded_clusters, source_geometry_rows


def semantics_audit() -> list[dict[str, Any]]:
    checks = [
        (BOUND_11B, "TARGET_PADDING_BP=500", 'TARGET_PADDING_BP="${TARGET_PADDING_BP:-500}"'),
        (BOUND_11B, "non_splice_blocks", "def non_splice_reference_blocks"),
        (BOUND_11B, "candidate_not_final_call", "candidate_status\tnot_final_call"),
        (BOUND_11B, "primary_support_preserved", 'record["alignment_class"] == "primary"'),
        (BOUND_11B, "supplementary_support_preserved", 'record["alignment_class"] == "supplementary"'),
        (BOUND_11B, "secondary_support_preserved", 'record["alignment_class"] == "secondary"'),
        (BOUND_11D3, "projection_one_per_candidate", "projection_rows_written"),
        (BOUND_11E, "one_job_per_projection", 'counts["projection_rows"]'),
        (BOUND_11E, "motif_hypotheses_within_job", '"canonical_motifs"'),
    ]
    rows: list[dict[str, Any]] = []
    for path, contract, token in checks:
        ensure_file(path)
        text = path.read_text(encoding="utf-8", errors="replace")
        status = "PASS" if token in text else "FAIL"
        rows.append({"component": path.name, "contract": contract, "token": token, "status": status})
        if status != "PASS":
            raise AuditError(f"assignment semantics token absent: {contract} in {path}")
    return rows


def init_worker(shard_count: int, profile: str, result_dir: str) -> None:
    global G_SHARD_COUNT, G_PROFILE, G_RESULT_DIR
    G_SHARD_COUNT = shard_count
    G_PROFILE = profile
    G_RESULT_DIR = Path(result_dir)


def new_read_state() -> dict[str, Any]:
    return {
        "rows": 0,
        "exact": False,
        "primary": False,
        "supplementary": False,
        "secondary": False,
        "targets": set(),
        "loci": set(),
        "raw_clusters": set(),
        "padded_clusters": set(),
        "sources": set(),
        "region_types": set(),
        "catalog_motifs": set(),
        "locus_catalog_motifs": set(),
        "motifs": set(),
        "locus_motifs": set(),
        "declared_counts": set(),
        "ranks": set(),
    }


def semantic_group_summary(groups: Mapping[tuple[str, str, str], dict[str, Any]]) -> tuple[Counter, list[dict[str, Any]]]:
    classes = Counter()
    examples: list[dict[str, Any]] = []
    for (read_id, locus, motif), data in groups.items():
        rows = int(data["rows"])
        if rows <= 1:
            continue
        targets = set(data["targets"])
        raw = {G_TARGET_META[target][1] for target in targets if target in G_TARGET_META}
        padded = {G_TARGET_META[target][2] for target in targets if target in G_TARGET_META}
        excess = rows - 1
        if len(raw) == 1:
            classification = "WITHIN_RAW_OVERLAP_OR_EXACT_ALIAS"
        elif len(padded) == 1:
            classification = "WITHIN_500BP_PADDING_CLUSTER"
        else:
            classification = "ACROSS_DISTINCT_PADDED_CLUSTERS"
        classes[f"groups::{classification}"] += 1
        classes[f"excess_rows::{classification}"] += excess
        if len(examples) < 200:
            examples.append({
                "read_id": read_id,
                "locus": locus,
                "motif": motif,
                "rows": rows,
                "excess_rows": excess,
                "target_count": len(targets),
                "raw_cluster_count": len(raw),
                "padded_cluster_count": len(padded),
                "classification": classification,
                "target_keys": ";".join(f"{a}|{b}" for a, b in sorted(targets)),
            })
    return classes, examples


def process_shard(task: dict[str, Any]) -> str:
    if G_RESULT_DIR is None:
        raise AuditError("worker result directory not initialized")
    shard_name = task["shard"]
    shard_idx = int(task["shard_index"])
    if int(task["shard_count"]) != G_SHARD_COUNT:
        raise AuditError("worker shard-count mismatch")

    result: dict[str, Any] = {
        "profile": G_PROFILE,
        "shard": shard_name,
        "shard_index": shard_idx,
        "stage_rows": Counter(),
        "stage_unique_reads": Counter(),
        "lineage": Counter(),
        "duplicates": Counter(),
        "candidate_categories": Counter(),
        "row_categories": Counter(),
        "histograms": defaultdict(Counter),
        "concentration": defaultdict(Counter),
        "semantic_duplicate_classes": defaultdict(Counter),
        "semantic_examples": [],
        "top_reads": [],
        "headers": {},
    }

    read_state: dict[str, dict[str, Any]] = {}
    assignment_info: dict[tuple[str, str, str], tuple[str, str, str, str, int, str]] = {}
    assignment_read_ids: set[str] = set()

    assignment_path = Path(task["assignment"])
    with SelectedTsv(assignment_path, ASSIGNMENT_REQUIRED) as table:
        fields = table.fieldnames
        result["headers"]["assignment"] = fields
        for row in table:
            result["stage_rows"]["assignment"] += 1
            read_id = row["read_id"]
            if shard_index(read_id, G_SHARD_COUNT) != shard_idx:
                result["lineage"]["read_in_wrong_shard::assignment"] += 1
            assignment_read_ids.add(read_id)
            target = (row["target_source"], row["target_region_id"])
            if target not in G_TARGET_META:
                result["lineage"]["assignment_target_missing_from_catalog"] += 1
                continue
            locus_catalog, raw_cluster, padded_cluster, region_catalog, _, _ = G_TARGET_META[target]
            raw_locus = row["representative_locus_id"] or "."
            locus = normalized_locus(raw_locus, target)
            if locus_catalog not in {"", "."} and raw_locus != locus_catalog:
                result["lineage"]["assignment_locus_catalog_mismatch"] += 1
            key = (read_id, target[0], target[1])
            if key in assignment_info:
                result["duplicates"]["assignment_key_duplicate_rows"] += 1
            else:
                assignment_info[key] = (
                    row["best_alignment_id"], raw_locus, locus, row["candidate_basis"],
                    int_value(row["assignment_rank"]), row["region_type"],
                )

            state = read_state.setdefault(read_id, new_read_state())
            state["rows"] += 1
            state["targets"].add(target)
            state["loci"].add(locus)
            state["raw_clusters"].add(raw_cluster)
            state["padded_clusters"].add(padded_cluster)
            state["sources"].add(target[0])
            state["region_types"].add(row["region_type"])
            state["declared_counts"].add(int_value(row["read_candidate_target_count"]))
            state["ranks"].add(int_value(row["assignment_rank"]))
            state["exact"] = state["exact"] or row["candidate_basis"] == "exact_overlap"
            state["primary"] = state["primary"] or bool_value(row["primary_support"])
            state["supplementary"] = state["supplementary"] or bool_value(row["supplementary_support"])
            state["secondary"] = state["secondary"] or bool_value(row["secondary_support"])

            result["concentration"]["target_rows"][target] += 1
            result["concentration"]["locus_rows"][locus] += 1
            result["concentration"]["raw_cluster_rows"][raw_cluster] += 1
            result["concentration"]["padded_cluster_rows"][padded_cluster] += 1
            result["concentration"]["source_rows"][target[0]] += 1
            result["concentration"]["region_type_rows"][row["region_type"]] += 1
            result["row_categories"][f"candidate_basis::{row['candidate_basis']}"] += 1
            support_key = (
                f"P{int(bool_value(row['primary_support']))}"
                f"S{int(bool_value(row['supplementary_support']))}"
                f"X{int(bool_value(row['secondary_support']))}"
            )
            result["row_categories"][f"support_combination::{support_key}"] += 1

    result["stage_unique_reads"]["assignment"] = len(assignment_read_ids)
    result["lineage"]["assignment_key_count"] = len(assignment_info)
    result["lineage"]["assignment_catalog_missing_rows"] += result["lineage"]["assignment_target_missing_from_catalog"]

    for read_id, state in read_state.items():
        rows = int(state["rows"])
        if state["declared_counts"] != {rows}:
            result["lineage"]["read_candidate_target_count_mismatch_reads"] += 1
        if state["ranks"] != set(range(1, rows + 1)):
            result["lineage"]["assignment_rank_sequence_mismatch_reads"] += 1
        result["histograms"]["candidate_rows_per_read"][rows] += 1
        result["histograms"]["unique_target_regions_per_read"][len(state["targets"])] += 1
        result["histograms"]["unique_catalog_sources_per_read"][len(state["sources"])] += 1
        result["histograms"]["unique_loci_per_read"][len(state["loci"])] += 1
        result["histograms"]["unique_raw_clusters_per_read"][len(state["raw_clusters"])] += 1
        result["histograms"]["unique_padded_clusters_per_read"][len(state["padded_clusters"])] += 1
        result["candidate_categories"]["candidate_reads"] += 1
        result["candidate_categories"]["exact_any_reads" if state["exact"] else "proximal_only_reads"] += 1
        if state["primary"]:
            support_class = "primary_supported_reads"
        elif state["supplementary"]:
            support_class = "supplementary_only_reads"
        elif state["secondary"]:
            support_class = "secondary_only_reads"
        else:
            support_class = "no_support_flag_reads"
        result["candidate_categories"][support_class] += 1
        combo = "+".join(sorted(state["sources"])) or "."
        support_combo = (
            f"P{int(state['primary'])}"
            f"S{int(state['supplementary'])}"
            f"X{int(state['secondary'])}"
        )
        basis_class = "EXACT_ANY" if state["exact"] else "PROXIMAL_ONLY"
        result["candidate_categories"][f"source_combination::{combo}"] += 1
        result["candidate_categories"][f"support_combination_reads::{support_combo}"] += 1
        result["candidate_categories"][f"entry_basis_support::{basis_class}|{support_class}"] += 1
        result["candidate_categories"][f"entry_basis_support_combo::{basis_class}|{support_combo}"] += 1
        result["candidate_categories"][f"entry_basis_source::{basis_class}|{combo}"] += 1
        result["candidate_categories"]["assignment_excess_over_unique_loci"] += rows - len(state["loci"])
        result["candidate_categories"]["assignment_excess_over_unique_raw_clusters"] += rows - len(state["raw_clusters"])
        result["candidate_categories"]["assignment_excess_over_unique_padded_clusters"] += rows - len(state["padded_clusters"])
        for target in state["targets"]:
            result["concentration"]["target_unique_reads"][target] += 1
        for locus in state["loci"]:
            result["concentration"]["locus_unique_reads"][locus] += 1
        for cluster in state["raw_clusters"]:
            result["concentration"]["raw_cluster_unique_reads"][cluster] += 1
        for cluster in state["padded_clusters"]:
            result["concentration"]["padded_cluster_unique_reads"][cluster] += 1
        for source in state["sources"]:
            result["concentration"]["source_unique_reads"][source] += 1
        for region_type in state["region_types"]:
            result["concentration"]["region_type_unique_reads"][region_type] += 1

    # 11d3 projection: exact candidate-key and projection-ID conservation.
    projection_info: dict[str, tuple[str, tuple[str, str], str, str, str, int]] = {}
    projection_key_seen: set[tuple[str, str, str]] = set()
    projection_read_ids: set[str] = set()
    projection_path = Path(task["projection"])
    with SelectedTsv(projection_path, PROJECTION_REQUIRED) as table:
        fields = table.fieldnames
        result["headers"]["projection"] = fields
        for row in table:
            result["stage_rows"]["projection"] += 1
            read_id = row["read_id"]
            projection_read_ids.add(read_id)
            if shard_index(read_id, G_SHARD_COUNT) != shard_idx:
                result["lineage"]["read_in_wrong_shard::projection"] += 1
            target = (row["target_source"], row["target_region_id"])
            raw_locus = row["representative_locus_id"] or "."
            locus = normalized_locus(raw_locus, target)
            key = (read_id, target[0], target[1])
            if key not in assignment_info:
                result["lineage"]["projection_extra_candidate_keys"] += 1
            if key in projection_key_seen:
                result["duplicates"]["projection_candidate_key_duplicates"] += 1
            projection_key_seen.add(key)
            projection_id = row["projection_id"]
            if projection_id in projection_info:
                result["duplicates"]["projection_id_duplicates"] += 1
            else:
                projection_info[projection_id] = (
                    read_id, target, raw_locus, locus,
                    row["candidate_basis"], int_value(row["assignment_rank"]),
                )
            if key in assignment_info:
                best_alignment, assignment_raw_locus, assignment_locus, basis, rank, _ = assignment_info[key]
                if (
                    row["best_alignment_id"] != best_alignment
                    or raw_locus != assignment_raw_locus
                    or locus != assignment_locus
                    or row["candidate_basis"] != basis
                    or int_value(row["assignment_rank"]) != rank
                ):
                    result["lineage"]["assignment_projection_field_mismatch"] += 1
    result["stage_unique_reads"]["projection"] = len(projection_read_ids)
    result["lineage"]["projection_missing_candidate_keys"] = len(set(assignment_info) - projection_key_seen)
    result["lineage"]["projection_id_count"] = len(projection_info)
    del assignment_info, projection_key_seen

    # 11e jobs: one job row per projection, with within-row motif fan-out measured separately.
    job_info: dict[str, tuple[str, tuple[str, str], str, str, tuple[str, ...], str]] = {}
    job_projection_seen: set[str] = set()
    job_read_ids: set[str] = set()
    job_semantic_groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    jobs_path = Path(task["motif_jobs"])
    with SelectedTsv(jobs_path, JOBS_REQUIRED) as table:
        fields = table.fieldnames
        result["headers"]["motif_jobs"] = fields
        for row in table:
            result["stage_rows"]["motif_jobs"] += 1
            pid = row["projection_id"]
            read_id = row["read_id"]
            job_read_ids.add(read_id)
            if shard_index(read_id, G_SHARD_COUNT) != shard_idx:
                result["lineage"]["read_in_wrong_shard::motif_jobs"] += 1
            if pid not in projection_info:
                result["lineage"]["motif_job_extra_projection_ids"] += 1
            if pid in job_projection_seen:
                result["duplicates"]["motif_job_projection_id_duplicates"] += 1
            job_projection_seen.add(pid)
            target = (row["target_source"], row["target_region_id"])
            raw_locus = row["representative_locus_id"] or "."
            locus = normalized_locus(raw_locus, target)
            canonical = split_csv_tokens(row["canonical_motifs"])
            candidates = split_csv_tokens(row["motif_candidates"])
            job_info[pid] = (read_id, target, raw_locus, locus, canonical, row["scan_strategy"])
            result["row_categories"][f"scan_strategy::{row['scan_strategy']}"] += 1
            result["row_categories"][f"motif_scan_eligible::{row['motif_scan_eligible']}"] += 1
            result["row_categories"]["catalog_motif_count_sum"] += int_value(row["motif_count"])
            result["row_categories"]["canonical_motif_hypothesis_sum"] += len(canonical)
            state = read_state.get(read_id)
            if state is None:
                result["lineage"]["job_read_missing_from_assignment"] += 1
            else:
                for motif in candidates:
                    state["catalog_motifs"].add(motif)
                    state["locus_catalog_motifs"].add((locus, motif))
                for motif in canonical:
                    state["motifs"].add(motif)
                    state["locus_motifs"].add((locus, motif))
            for motif in candidates:
                result["concentration"]["catalog_motif_candidate_rows"][motif] += 1
                result["concentration"]["locus_catalog_motif_rows"][(locus, motif)] += 1
            for motif in canonical:
                result["concentration"]["motif_hypothesis_rows"][motif] += 1
                result["concentration"]["locus_motif_hypothesis_rows"][(locus, motif)] += 1
                sem_key = (read_id, locus, motif)
                group = job_semantic_groups.setdefault(sem_key, {"rows": 0, "targets": set()})
                group["rows"] += 1
                group["targets"].add(target)
            if pid in projection_info:
                pr_read, pr_target, pr_raw_locus, pr_locus, pr_basis, pr_rank = projection_info[pid]
                if (
                    read_id != pr_read or target != pr_target
                    or raw_locus != pr_raw_locus or locus != pr_locus
                    or row["candidate_basis"] != pr_basis
                    or int_value(row["assignment_rank"]) != pr_rank
                ):
                    result["lineage"]["projection_job_field_mismatch"] += 1
    result["stage_unique_reads"]["motif_jobs"] = len(job_read_ids)
    result["lineage"]["motif_job_missing_projection_ids"] = len(set(projection_info) - job_projection_seen)
    result["lineage"]["motif_job_projection_id_count"] = len(job_projection_seen)
    classes, examples = semantic_group_summary(job_semantic_groups)
    result["semantic_duplicate_classes"]["motif_job_locus_motif"].update(classes)
    result["semantic_examples"].extend({"stage": "motif_jobs", **row} for row in examples)
    del projection_info, job_projection_seen, job_semantic_groups

    for read_id, state in read_state.items():
        result["histograms"]["unique_catalog_motif_candidates_per_read"][len(state["catalog_motifs"])] += 1
        result["histograms"]["unique_locus_catalog_motifs_per_read"][len(state["locus_catalog_motifs"])] += 1
        result["histograms"]["unique_canonical_motifs_per_read"][len(state["motifs"])] += 1
        result["histograms"]["unique_locus_motifs_per_read"][len(state["locus_motifs"])] += 1
        for motif in state["catalog_motifs"]:
            result["concentration"]["catalog_motif_unique_reads"][motif] += 1
        for locus_motif in state["locus_catalog_motifs"]:
            result["concentration"]["locus_catalog_motif_unique_reads"][locus_motif] += 1
        for motif in state["motifs"]:
            result["concentration"]["motif_unique_reads"][motif] += 1
        for locus_motif in state["locus_motifs"]:
            result["concentration"]["locus_motif_unique_reads"][locus_motif] += 1
        dossier = {
            "read_id": read_id,
            "candidate_rows": int(state["rows"]),
            "unique_loci": len(state["loci"]),
            "unique_raw_clusters": len(state["raw_clusters"]),
            "unique_padded_clusters": len(state["padded_clusters"]),
            "unique_catalog_motifs": len(state["catalog_motifs"]),
            "unique_locus_catalog_motifs": len(state["locus_catalog_motifs"]),
            "unique_motifs": len(state["motifs"]),
            "unique_locus_motifs": len(state["locus_motifs"]),
            "candidate_basis": "EXACT_ANY" if state["exact"] else "PROXIMAL_ONLY",
            "primary_support": str(state["primary"]).lower(),
            "supplementary_support": str(state["supplementary"]).lower(),
            "secondary_support": str(state["secondary"]).lower(),
            "source_combination": "+".join(sorted(state["sources"])) or ".",
        }
        score = (int(state["rows"]), len(state["locus_motifs"]), len(state["loci"]), read_id)
        if len(result["top_reads"]) < 1000:
            heapq.heappush(result["top_reads"], (score, dossier))
        elif score > result["top_reads"][0][0]:
            heapq.heapreplace(result["top_reads"], (score, dossier))

    # Caller: one attempt row per job/projection.
    caller_info: dict[str, tuple[str, tuple[str, str], str, str, str, str, str]] = {}
    caller_projection_seen: set[str] = set()
    caller_read_ids: set[str] = set()
    caller_semantic_groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    caller_path = Path(task["caller_calls"])
    with SelectedTsv(caller_path, CALLER_REQUIRED) as table:
        fields = table.fieldnames
        result["headers"]["caller_calls"] = fields
        for row in table:
            result["stage_rows"]["caller_calls"] += 1
            pid = row["projection_id"]
            read_id = row["read_id"]
            caller_read_ids.add(read_id)
            if shard_index(read_id, G_SHARD_COUNT) != shard_idx:
                result["lineage"]["read_in_wrong_shard::caller"] += 1
            if pid not in job_info:
                result["lineage"]["caller_extra_projection_ids"] += 1
            if pid in caller_projection_seen:
                result["duplicates"]["caller_projection_id_duplicates"] += 1
            caller_projection_seen.add(pid)
            target = (row["target_source"], row["target_region_id"])
            raw_locus = row["representative_locus_id"] or "."
            locus = normalized_locus(raw_locus, target)
            canonical = row["canonical_motif"]
            integration = row["integration_status"]
            catalog_motifs = row["catalog_motifs"]
            semantic_motif = canonical if canonical not in {"", "."} else "CATALOG_SET:" + catalog_motifs
            caller_info[pid] = (read_id, target, raw_locus, locus, canonical, integration, row["hypothesis_count"])
            result["row_categories"][f"integration_status::{integration}"] += 1
            result["row_categories"]["caller_hypothesis_count_sum"] += int_value(row["hypothesis_count"])
            sem_key = (read_id, locus, semantic_motif)
            group = caller_semantic_groups.setdefault(sem_key, {"rows": 0, "targets": set()})
            group["rows"] += 1
            group["targets"].add(target)
            if pid in job_info:
                j_read, j_target, j_raw_locus, j_locus, j_motifs, _ = job_info[pid]
                if (
                    read_id != j_read or target != j_target
                    or raw_locus != j_raw_locus or locus != j_locus
                ):
                    result["lineage"]["job_caller_field_mismatch"] += 1
                if integration == "CALLED" and canonical not in j_motifs:
                    result["lineage"]["called_motif_not_in_job_canonical_motifs"] += 1
    result["stage_unique_reads"]["caller_calls"] = len(caller_read_ids)
    result["lineage"]["caller_missing_projection_ids"] = len(set(job_info) - caller_projection_seen)
    result["lineage"]["caller_projection_id_count"] = len(caller_projection_seen)
    classes, examples = semantic_group_summary(caller_semantic_groups)
    result["semantic_duplicate_classes"]["caller_read_locus_motif"].update(classes)
    result["semantic_examples"].extend({"stage": "caller", **row} for row in examples)
    del job_info, caller_projection_seen, caller_semantic_groups

    # Materialized general_repeat_calls: verify lossless attempt-level key preservation.
    general_projection_seen: set[str] = set()
    caller_record_ids: set[str] = set()
    evidence_by_id: dict[str, tuple[str, str, tuple[str, str], str, str, str, str]] = {}
    general_read_ids: set[str] = set()
    general_semantic_groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    general_path = Path(task["materialized_general_repeat_calls"])
    with SelectedTsv(general_path, GENERAL_REQUIRED) as table:
        fields = table.fieldnames
        result["headers"]["materialized_general_repeat_calls"] = fields
        for row in table:
            result["stage_rows"]["general_repeat_calls"] += 1
            pid = row["projection_id"]
            read_id = row["read_id"]
            general_read_ids.add(read_id)
            target = (row["target_source"], row["target_region_id"])
            raw_locus = row["representative_locus_id"] or "."
            locus = normalized_locus(raw_locus, target)
            canonical = row["canonical_motif"]
            integration = row["integration_status"]
            semantic_motif = canonical if canonical not in {"", "."} else "NO_CALLED_MOTIF"
            if pid not in caller_info:
                result["lineage"]["general_extra_projection_ids"] += 1
            if pid in general_projection_seen:
                result["duplicates"]["general_projection_id_duplicates"] += 1
            general_projection_seen.add(pid)
            caller_record_id = row["caller_record_id"]
            evidence_id = row["evidence_id"]
            if caller_record_id in caller_record_ids:
                result["duplicates"]["caller_record_id_duplicates"] += 1
            caller_record_ids.add(caller_record_id)
            if evidence_id in evidence_by_id:
                result["duplicates"]["general_evidence_id_duplicates"] += 1
            evidence_by_id[evidence_id] = (pid, read_id, target, raw_locus, locus, canonical, caller_record_id)
            sem_key = (read_id, locus, semantic_motif)
            group = general_semantic_groups.setdefault(sem_key, {"rows": 0, "targets": set()})
            group["rows"] += 1
            group["targets"].add(target)
            if pid in caller_info:
                c_read, c_target, c_raw_locus, c_locus, c_canonical, c_integration, c_hypothesis = caller_info[pid]
                if (
                    read_id != c_read or target != c_target
                    or raw_locus != c_raw_locus or locus != c_locus
                    or canonical != c_canonical or integration != c_integration
                    or row["hypothesis_count"] != c_hypothesis
                ):
                    result["lineage"]["caller_general_lossless_field_mismatch"] += 1
    result["stage_unique_reads"]["general_repeat_calls"] = len(general_read_ids)
    result["lineage"]["general_missing_projection_ids"] = len(set(caller_info) - general_projection_seen)
    result["lineage"]["general_projection_id_count"] = len(general_projection_seen)
    result["lineage"]["caller_record_id_count"] = len(caller_record_ids)
    result["lineage"]["general_evidence_id_count"] = len(evidence_by_id)
    classes, examples = semantic_group_summary(general_semantic_groups)
    result["semantic_duplicate_classes"]["general_read_locus_motif"].update(classes)
    result["semantic_examples"].extend({"stage": "general_repeat_calls", **row} for row in examples)
    del caller_info, general_projection_seen, caller_record_ids, general_semantic_groups

    # read_evidence: one evidence row per materialized attempt in this core profile.
    evidence_seen: set[str] = set()
    evidence_read_ids: set[str] = set()
    evidence_semantic_groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    evidence_path = Path(task["materialized_read_evidence"])
    with SelectedTsv(evidence_path, EVIDENCE_REQUIRED) as table:
        fields = table.fieldnames
        result["headers"]["materialized_read_evidence"] = fields
        for row in table:
            result["stage_rows"]["read_evidence"] += 1
            evidence_id = row["evidence_id"]
            read_id = row["read_id"]
            evidence_read_ids.add(read_id)
            target = (row["target_source"], row["target_region_id"])
            raw_locus = row["locus_id"] or "."
            locus = normalized_locus(raw_locus, target)
            canonical = row["canonical_motif"]
            semantic_motif = canonical if canonical not in {"", "."} else "NO_CALLED_MOTIF"
            if evidence_id not in evidence_by_id:
                result["lineage"]["read_evidence_extra_evidence_ids"] += 1
            if evidence_id in evidence_seen:
                result["duplicates"]["read_evidence_id_duplicates"] += 1
            evidence_seen.add(evidence_id)
            sem_key = (read_id, locus, semantic_motif)
            group = evidence_semantic_groups.setdefault(sem_key, {"rows": 0, "targets": set()})
            group["rows"] += 1
            group["targets"].add(target)
            if evidence_id in evidence_by_id:
                pid, g_read, g_target, g_raw_locus, g_locus, g_canonical, g_caller_record = evidence_by_id[evidence_id]
                if (
                    read_id != g_read or target != g_target
                    or raw_locus != g_raw_locus or locus != g_locus
                    or canonical != g_canonical or row["best_projection_id"] != pid
                    or row["best_caller_record_id"] != g_caller_record
                ):
                    result["lineage"]["general_read_evidence_field_mismatch"] += 1
    result["stage_unique_reads"]["read_evidence"] = len(evidence_read_ids)
    result["lineage"]["read_evidence_missing_evidence_ids"] = len(set(evidence_by_id) - evidence_seen)
    result["lineage"]["read_evidence_id_count"] = len(evidence_seen)
    classes, examples = semantic_group_summary(evidence_semantic_groups)
    result["semantic_duplicate_classes"]["read_evidence_read_locus_motif"].update(classes)
    result["semantic_examples"].extend({"stage": "read_evidence", **row} for row in examples)

    # Convert heap to ordinary rows before pickling.
    result["top_reads"] = [row for _, row in sorted(result["top_reads"], reverse=True)]
    output = G_RESULT_DIR / f"{G_PROFILE}.{shard_name}.pickle.gz"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as raw_handle:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw_handle, compresslevel=1, mtime=0) as handle:
            pickle.dump(result, handle, protocol=pickle.HIGHEST_PROTOCOL)
    return str(output)


def merge_nested_counter(destination: defaultdict[str, Counter], source: Mapping[str, Counter]) -> None:
    for key, counter in source.items():
        destination[key].update(counter)


def load_and_merge_results(paths: Sequence[str], profile: Profile) -> dict[str, Any]:
    aggregate: dict[str, Any] = {
        "profile": profile.name,
        "input_reads": profile.input_reads,
        "stage_rows": Counter(),
        "stage_unique_reads": Counter(),
        "lineage": Counter(),
        "duplicates": Counter(),
        "candidate_categories": Counter(),
        "row_categories": Counter(),
        "histograms": defaultdict(Counter),
        "concentration": defaultdict(Counter),
        "semantic_duplicate_classes": defaultdict(Counter),
        "semantic_examples": [],
        "top_reads": [],
        "headers": defaultdict(Counter),
        "per_shard": [],
    }
    top_heap: list[tuple[tuple[int, int, int, str], dict[str, Any]]] = []
    for path_text in paths:
        with gzip.open(path_text, "rb") as handle:
            result = pickle.load(handle)
        aggregate["stage_rows"].update(result["stage_rows"])
        aggregate["stage_unique_reads"].update(result["stage_unique_reads"])
        aggregate["lineage"].update(result["lineage"])
        aggregate["duplicates"].update(result["duplicates"])
        aggregate["candidate_categories"].update(result["candidate_categories"])
        aggregate["row_categories"].update(result["row_categories"])
        merge_nested_counter(aggregate["histograms"], result["histograms"])
        merge_nested_counter(aggregate["concentration"], result["concentration"])
        merge_nested_counter(aggregate["semantic_duplicate_classes"], result["semantic_duplicate_classes"])
        if len(aggregate["semantic_examples"]) < 5000:
            remaining = 5000 - len(aggregate["semantic_examples"])
            aggregate["semantic_examples"].extend(result["semantic_examples"][:remaining])
        for role, fields in result["headers"].items():
            aggregate["headers"][role]["\t".join(fields)] += 1
        aggregate["per_shard"].append({
            "profile": profile.name,
            "shard": result["shard"],
            "assignment_rows": result["stage_rows"]["assignment"],
            "candidate_reads": result["stage_unique_reads"]["assignment"],
            "projection_rows": result["stage_rows"]["projection"],
            "motif_job_rows": result["stage_rows"]["motif_jobs"],
            "caller_rows": result["stage_rows"]["caller_calls"],
            "general_repeat_calls_rows": result["stage_rows"]["general_repeat_calls"],
            "read_evidence_rows": result["stage_rows"]["read_evidence"],
            "hard_violation_count": sum(v for k, v in result["lineage"].items() if not k.endswith("_count")) + sum(result["duplicates"].values()),
        })
        for dossier in result["top_reads"]:
            score = (
                int(dossier["candidate_rows"]), int(dossier["unique_locus_motifs"]),
                int(dossier["unique_loci"]), str(dossier["read_id"]),
            )
            if len(top_heap) < TOP_DOSSIER_ROWS:
                heapq.heappush(top_heap, (score, dossier))
            elif score > top_heap[0][0]:
                heapq.heapreplace(top_heap, (score, dossier))
    aggregate["top_reads"] = [row for _, row in sorted(top_heap, reverse=True)]
    aggregate["per_shard"].sort(key=lambda row: row["shard"])
    return aggregate


def weighted_quantile(hist: Mapping[int, int], probability: float) -> float:
    total = sum(hist.values())
    if total == 0:
        return float("nan")
    target = probability * (total - 1)
    cumulative = 0
    for value in sorted(hist):
        next_cumulative = cumulative + hist[value]
        if target < next_cumulative:
            return float(value)
        cumulative = next_cumulative
    return float(max(hist))


def histogram_mean(hist: Mapping[int, int]) -> float:
    total = sum(hist.values())
    return sum(value * count for value, count in hist.items()) / total if total else float("nan")


def multiplicity_rows(profile_name: str, histograms: Mapping[str, Counter]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    bins = [
        ("1", lambda x: x == 1),
        ("2_5", lambda x: 2 <= x <= 5),
        ("6_10", lambda x: 6 <= x <= 10),
        ("11_20", lambda x: 11 <= x <= 20),
        ("21_50", lambda x: 21 <= x <= 50),
        ("GT50", lambda x: x > 50),
    ]
    for metric, hist in sorted(histograms.items()):
        total = sum(hist.values())
        summary = {
            "profile": profile_name, "metric": metric, "row_type": "SUMMARY",
            "category": ".", "reads": total,
            "fraction": "1.000000000" if total else "0.000000000",
            "mean": f"{histogram_mean(hist):.9f}" if total else ".",
            "p50": f"{weighted_quantile(hist, 0.5):.3f}" if total else ".",
            "p90": f"{weighted_quantile(hist, 0.9):.3f}" if total else ".",
            "p95": f"{weighted_quantile(hist, 0.95):.3f}" if total else ".",
            "p99": f"{weighted_quantile(hist, 0.99):.3f}" if total else ".",
            "p99_9": f"{weighted_quantile(hist, 0.999):.3f}" if total else ".",
            "max": max(hist) if hist else ".",
        }
        rows.append(summary)
        for label, predicate in bins:
            count = sum(c for v, c in hist.items() if predicate(v))
            rows.append({
                "profile": profile_name, "metric": metric, "row_type": "BIN",
                "category": label, "reads": count,
                "fraction": f"{count / total:.9f}" if total else "0.000000000",
                "mean": ".", "p50": ".", "p90": ".", "p95": ".",
                "p99": ".", "p99_9": ".", "max": ".",
            })
    return rows


def gini(values: Sequence[int]) -> float:
    positive = sorted(value for value in values if value > 0)
    n = len(positive)
    if n == 0:
        return 0.0
    total = sum(positive)
    weighted = sum((index + 1) * value for index, value in enumerate(positive))
    return (2 * weighted) / (n * total) - (n + 1) / n


def concentration_summary(dimension: str, counts: Mapping[Any, int], total: int) -> dict[str, Any]:
    values = sorted(counts.values(), reverse=True)
    def share(n: int) -> float:
        return sum(values[:n]) / total if total else 0.0
    return {
        "dimension": dimension,
        "categories": len(values),
        "total_units": total,
        "maximum_count": values[0] if values else 0,
        "top1_share": f"{share(1):.9f}",
        "top10_share": f"{share(10):.9f}",
        "top100_share": f"{share(100):.9f}",
        "hhi": f"{sum((value / total) ** 2 for value in values):.12f}" if total else "0.000000000000",
        "gini": f"{gini(values):.12f}",
    }


def key_text(key: Any) -> str:
    if isinstance(key, tuple):
        return "|".join(str(x) for x in key)
    return str(key)


def write_concentration(path: Path, profile: str, dimension: str, row_counts: Mapping[Any, int], unique_counts: Mapping[Any, int] | None = None) -> None:
    total_rows = sum(row_counts.values())
    rows = []
    for rank, (key, count) in enumerate(sorted(row_counts.items(), key=lambda x: (-x[1], key_text(x[0]))), start=1):
        rows.append({
            "profile": profile, "dimension": dimension, "rank": rank,
            "key": key_text(key), "row_or_hypothesis_count": count,
            "row_share": f"{count / total_rows:.12f}" if total_rows else "0.000000000000",
            "unique_reads": unique_counts.get(key, ".") if unique_counts is not None else ".",
        })
    write_tsv(path, ["profile", "dimension", "rank", "key", "row_or_hypothesis_count", "row_share", "unique_reads"], rows, gzip_output=True)


def hard_violation_counts(aggregate: Mapping[str, Any]) -> tuple[int, list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    total = 0
    for category in ("lineage", "duplicates"):
        for metric, value in sorted(aggregate[category].items()):
            if category == "lineage" and metric.endswith("_count"):
                continue
            severity = "HARD_FAIL" if value else "PASS"
            rows.append({"category": category, "metric": metric, "value": value, "severity": severity})
            if value:
                total += int(value)
    return total, rows


def profile_summary(aggregate: Mapping[str, Any]) -> dict[str, Any]:
    input_reads = int(aggregate["input_reads"])
    stage_rows = aggregate["stage_rows"]
    candidate_reads = int(aggregate["candidate_categories"]["candidate_reads"])
    candidate_rows = int(stage_rows["assignment"])
    primary_supported = int(aggregate["candidate_categories"]["primary_supported_reads"])
    hard_total, _ = hard_violation_counts(aggregate)
    return {
        "profile": aggregate["profile"],
        "input_reads": input_reads,
        "candidate_reads": candidate_reads,
        "candidate_read_rate": candidate_reads / input_reads if input_reads else 0.0,
        "candidate_rows": candidate_rows,
        "candidate_rows_per_input_read": candidate_rows / input_reads if input_reads else 0.0,
        "candidate_rows_per_candidate_read": candidate_rows / candidate_reads if candidate_reads else 0.0,
        "exact_any_candidate_reads": aggregate["candidate_categories"]["exact_any_reads"],
        "proximal_only_candidate_reads": aggregate["candidate_categories"]["proximal_only_reads"],
        "primary_supported_candidate_reads": primary_supported,
        "supplementary_only_candidate_reads": aggregate["candidate_categories"]["supplementary_only_reads"],
        "secondary_only_candidate_reads": aggregate["candidate_categories"]["secondary_only_reads"],
        "projection_rows": stage_rows["projection"],
        "motif_job_rows": stage_rows["motif_jobs"],
        "canonical_motif_hypothesis_rows": aggregate["row_categories"]["canonical_motif_hypothesis_sum"],
        "caller_rows": stage_rows["caller_calls"],
        "caller_hypothesis_count_sum": aggregate["row_categories"]["caller_hypothesis_count_sum"],
        "general_repeat_calls_rows": stage_rows["general_repeat_calls"],
        "read_evidence_rows": stage_rows["read_evidence"],
        "hard_violation_count": hard_total,
    }


def create_bundle(bundle: Path, roots: Sequence[Path], arc_root: str) -> str:
    bundle.parent.mkdir(parents=True, exist_ok=True)
    tmp = bundle.with_name("." + bundle.name + f".part.{os.getpid()}")
    with tarfile.open(tmp, "w:gz", format=tarfile.PAX_FORMAT) as tar:
        for root in roots:
            if not root.exists():
                continue
            if root.is_file():
                tar.add(root, arcname=f"{arc_root}/{root.name}")
            else:
                for path in sorted(root.rglob("*")):
                    if path.is_file():
                        tar.add(path, arcname=f"{arc_root}/{root.name}/{path.relative_to(root)}")
    os.replace(tmp, bundle)
    digest = sha256_file(bundle)
    Path(str(bundle) + ".sha256").write_text(f"{digest}  {bundle.name}\n", encoding="utf-8")
    return digest


def install_exact(source: Path, destination: Path, mode: int = 0o644) -> str:
    ensure_file(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = source.read_bytes()
    if destination.exists():
        if not destination.is_file() or destination.read_bytes() != payload:
            raise AuditError(f"refusing overwrite of different versioned artifact: {destination}")
        return "REUSED_EXACT"
    tmp = destination.with_name("." + destination.name + f".part.{os.getpid()}")
    tmp.write_bytes(payload)
    tmp.chmod(mode)
    os.replace(tmp, destination)
    return "INSTALLED_NEW"


def guard_preflight() -> tuple[dict[str, str], list[dict[str, Any]]]:
    guards: list[dict[str, Any]] = []
    for path, expected in EXPECTED_GUARDS.items():
        ensure_file(path)
        observed = sha256_file(path)
        status = "PASS" if observed == expected else "FAIL"
        guards.append({"path": str(path), "expected_sha256": expected, "observed_sha256": observed, "status": status})
        if status != "PASS":
            raise AuditError(f"guard mismatch: {path}: {observed} != {expected}")
    ensure_file(QC_500K)
    observed_500k_qc_sha = sha256_file(QC_500K)
    guards.append({
        "path": str(QC_500K),
        "expected_sha256": QC_500K_SHA256,
        "observed_sha256": observed_500k_qc_sha,
        "status": "PASS" if observed_500k_qc_sha == QC_500K_SHA256 else "FAIL",
    })
    if observed_500k_qc_sha != QC_500K_SHA256:
        raise AuditError(
            f"500k QC guard mismatch: {observed_500k_qc_sha} != {QC_500K_SHA256}"
        )
    qc_500k = read_metrics(QC_500K)
    for key, expected in EXPECTED_500K.items():
        if qc_500k.get(key) != str(expected):
            raise AuditError(
                f"500k QC mismatch {key}: {qc_500k.get(key)} != {expected}"
            )
    if (
        qc_500k.get("deterministic_500k_scaling") != "PASS"
        or qc_500k.get("audit_status") != "PASS"
        or qc_500k.get("package_exact_logical_reproducibility") != "true"
    ):
        raise AuditError("500k accepted comparison profile is not formally PASS")
    qc = read_metrics(FULL_QC)
    for key, expected in EXPECTED_FULL.items():
        if qc.get(key) != str(expected):
            raise AuditError(f"full QC mismatch {key}: {qc.get(key)} != {expected}")
    required_status = {
        "execution_correctness_status": "PASS", "stage_status": "PASS",
        "audit_status": "PASS", "package_final_published": "true",
        "runtime_generated_script_audit_status": "PASS",
        "runtime_generated_path_binding_status": "PASS",
        "v014_failed_partition_reused": "false",
        "v015_runtime_artifacts_reused": "false",
        "v016_fresh_partition_required": "true",
    }
    for key, expected in required_status.items():
        if qc.get(key) != expected:
            raise AuditError(f"full QC status mismatch {key}: {qc.get(key)} != {expected}")

    validator_qc = read_metrics(FULL_VALIDATOR_QC)
    validator_required = {
        "observed_shards": str(EXPECTED_FULL["shards"]),
        "global_unique_tables": "5",
        "final_shard_row_parity": "PASS",
        "audit_status": "PASS",
        "validation_status": "PASS",
    }
    for key, expected in validator_required.items():
        if validator_qc.get(key) != expected:
            raise AuditError(
                f"full memory-bounded validator mismatch {key}: "
                f"{validator_qc.get(key)} != {expected}"
            )

    expected_global_rows = {
        "read_evidence": EXPECTED_FULL["read_evidence_rows"],
        "general_repeat_calls": EXPECTED_FULL["general_repeat_calls_rows"],
        "repeat_events": EXPECTED_FULL["repeat_events_rows"],
        "repeat_segments": EXPECTED_FULL["repeat_segments_rows"],
        "repeat_interruptions": EXPECTED_FULL["repeat_interruptions_rows"],
    }
    global_rows = read_dict_rows(FULL_GLOBAL_ID_UNIQUENESS)
    if len(global_rows) != 5:
        raise AuditError(f"unexpected global-ID uniqueness row count: {len(global_rows)}")
    seen_tables: set[str] = set()
    for row in global_rows:
        table = row.get("table", "")
        if table in seen_tables or table not in expected_global_rows:
            raise AuditError(f"unexpected/duplicate global-ID uniqueness table: {table}")
        seen_tables.add(table)
        if (
            int_value(row.get("rows", "0")) != expected_global_rows[table]
            or int_value(row.get("duplicate_rows", "0")) != 0
            or row.get("status") != "PASS"
        ):
            raise AuditError(f"global-ID uniqueness mismatch for {table}: {row}")

    disk = shutil.disk_usage(PROJECT_ROOT)
    if disk.free < MINIMUM_FREE_BYTES:
        raise AuditError(f"insufficient free space for G31 audit: {disk.free} < {MINIMUM_FREE_BYTES}")
    return qc, guards


def run_profile(profile: Profile, target_meta: dict[tuple[str, str], tuple[str, str, str, str, int, int]], workers: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    global G_TARGET_META
    G_TARGET_META = target_meta  # inherited copy-on-write by the fork workers
    shards = discover_shards(profile)
    if not shards:
        return {}, []
    result_dir = WORK_ROOT / "worker_results" / profile.name
    result_dir.mkdir(parents=True, exist_ok=False)
    print(f"G31_PROFILE\t{profile.name}\tshards={len(shards)}\tworkers={workers}\tSTART", flush=True)
    ctx = mp.get_context("fork")
    paths: list[str] = []
    with ctx.Pool(
        processes=min(workers, len(shards)),
        initializer=init_worker,
        initargs=(profile.expected_shards, profile.name, str(result_dir)),
    ) as pool:
        for index, path in enumerate(pool.imap_unordered(process_shard, shards, chunksize=1), start=1):
            paths.append(path)
            print(f"G31_PROFILE\t{profile.name}\tcompleted_shards={index}/{len(shards)}", flush=True)
    aggregate = load_and_merge_results(sorted(paths), profile)
    print(f"G31_PROFILE\t{profile.name}\tPASS\trows={aggregate['stage_rows']['assignment']}\treads={aggregate['stage_unique_reads']['assignment']}", flush=True)
    return aggregate, shards


def self_test() -> None:
    # Histogram and interval utilities.
    hist = Counter({1: 2, 3: 2, 10: 1})
    assert weighted_quantile(hist, 0.5) == 3.0
    assert abs(histogram_mean(hist) - 3.6) < 1e-9
    total, union, depth = interval_union_depth([(0, 10), (5, 12), (12, 15)])
    assert (total, union, depth) == (20, 15, 2)
    mapping, clusters = interval_clusters([(0, 10, ("A", "1")), (5, 8, ("B", "2")), (20, 30, ("A", "3"))], "chr1", "RAW")
    assert mapping[("A", "1")] == mapping[("B", "2")]
    assert mapping[("A", "1")] != mapping[("A", "3")]
    assert len(clusters) == 2
    assert shard_index("read-A", 12) == shard_index("read-A", 12)

    # Synthetic full-lineage worker test.
    with tempfile.TemporaryDirectory(prefix="rnatr_g31_selftest_") as tmp_text:
        tmp = Path(tmp_text)
        result_dir = tmp / "results"; result_dir.mkdir()
        target_meta = {
            ("CAT", "T1"): ("L1", "RAW:1", "PAD:1", "TR", 100, 110),
            ("CAT", "T2"): ("L1", "RAW:1", "PAD:1", "TR", 101, 111),
        }
        count = 1
        read_id = "read-A"
        shard = shard_index(read_id, count)
        paths = {}
        def make(path: Path, fields: list[str], rows: list[dict[str, Any]], gz: bool) -> Path:
            write_tsv(path, fields, rows, gzip_output=gz)
            return path
        assignment_rows = []
        projection_rows = []
        job_rows = []
        caller_rows = []
        general_rows = []
        evidence_rows = []
        for i, target_id in enumerate(("T1", "T2"), start=1):
            pid = f"P{i}"; eid = f"E{i}"; cid = f"C{i}"
            assignment_rows.append({
                "read_id": read_id, "target_region_id": target_id, "target_source": "CAT",
                "region_type": "TR", "analysis_mode": "A", "representative_locus_id": "L1",
                "assignment_rank": i, "read_candidate_target_count": 2, "best_alignment_id": "ALN1",
                "best_alignment_class": "primary", "candidate_basis": "exact_overlap",
                "target_overlap_bp": 10, "target_distance_bp": 0, "primary_support": "true",
                "supplementary_support": "false", "secondary_support": "false",
            })
            projection_rows.append({
                "projection_id": pid, "read_id": read_id, "target_region_id": target_id,
                "target_source": "CAT", "representative_locus_id": "L1", "assignment_rank": i,
                "read_candidate_target_count": 2, "best_alignment_id": "ALN1", "candidate_basis": "exact_overlap",
                "geometry_class": "BOTH_FLANKS_PROJECTABLE", "potential_evidence_class": "SPAN_POTENTIAL",
                "projection_status": "PASS",
            })
            job_rows.append({
                "projection_id": pid, "read_id": read_id, "target_region_id": target_id,
                "target_source": "CAT", "representative_locus_id": "L1", "assignment_rank": i,
                "read_candidate_target_count": 2, "candidate_basis": "exact_overlap",
                "canonical_motifs": "CAG", "motif_candidates": "CAG", "motif_count": 1,
                "scan_strategy": "SIMPLE_PERIODIC_SCAN", "motif_scan_eligible": "true",
                "manual_review_required": "false",
            })
            caller_rows.append({
                "projection_id": pid, "read_id": read_id, "target_region_id": target_id,
                "target_source": "CAT", "representative_locus_id": "L1", "assignment_rank": i,
                "read_candidate_target_count": 2, "catalog_motifs": "CAG",
                "integration_status": "CALLED", "canonical_motif": "CAG", "hypothesis_count": 1,
            })
            general_rows.append({
                "caller_record_id": cid, "evidence_id": eid, "projection_id": pid, "read_id": read_id,
                "target_region_id": target_id, "target_source": "CAT", "representative_locus_id": "L1",
                "assignment_rank": i, "read_candidate_target_count": 2, "integration_status": "CALLED",
                "canonical_motif": "CAG", "hypothesis_count": 1,
            })
            evidence_rows.append({
                "evidence_id": eid, "read_id": read_id, "target_region_id": target_id, "target_source": "CAT",
                "locus_id": "L1", "canonical_motif": "CAG", "best_projection_id": pid,
                "best_caller_record_id": cid, "caller_attempt_count": 1, "hypothesis_count": 1,
            })
        paths["assignment"] = make(tmp / "assignment.tsv.gz", list(assignment_rows[0]), assignment_rows, True)
        paths["projection"] = make(tmp / "projection.tsv.gz", list(projection_rows[0]), projection_rows, True)
        paths["motif_jobs"] = make(tmp / "jobs.tsv.gz", list(job_rows[0]), job_rows, True)
        paths["caller_calls"] = make(tmp / "caller.tsv.gz", list(caller_rows[0]), caller_rows, True)
        paths["materialized_general_repeat_calls"] = make(tmp / "general.tsv", list(general_rows[0]), general_rows, False)
        paths["materialized_read_evidence"] = make(tmp / "evidence.tsv", list(evidence_rows[0]), evidence_rows, False)
        global G_TARGET_META
        G_TARGET_META = target_meta
        init_worker(count, "synthetic", str(result_dir))
        output = process_shard({"shard": "shard_000", "shard_index": shard, "shard_count": count, **paths})
        with gzip.open(output, "rb") as handle:
            result = pickle.load(handle)
        assert result["stage_rows"]["assignment"] == 2
        assert result["stage_rows"]["read_evidence"] == 2
        assert result["candidate_categories"]["candidate_reads"] == 1
        assert result["candidate_categories"]["assignment_excess_over_unique_loci"] == 1
        assert sum(result["duplicates"].values()) == 0
        hard = sum(v for k, v in result["lineage"].items() if not k.endswith("_count"))
        assert hard == 0, result["lineage"]
        merged = load_and_merge_results(
            [output], Profile("synthetic", 1, tmp, 1, True)
        )
        merged_summary = profile_summary(merged)
        assert merged_summary["candidate_reads"] == 1
        assert merged_summary["candidate_rows"] == 2
        assert abs(merged_summary["candidate_read_rate"] - 1.0) < 1e-12
        assert merged["concentration"]["target_rows"][("CAT", "T1")] == 1
        assert merged["semantic_duplicate_classes"]["general_read_locus_motif"][
            "excess_rows::WITHIN_RAW_OVERLAP_OR_EXACT_ALIAS"
        ] == 1
    print("SELF_TEST_PASS")


def main_audit(workers: int) -> int:
    started = time.perf_counter()
    if os.environ.get("PYTHONHASHSEED") != "0":
        raise AuditError("PYTHONHASHSEED=0 is required for deterministic G31 audit outputs")
    if QC_ROOT.exists() or WORK_ROOT.exists():
        raise AuditError(f"versioned G31 output/work root already exists: {QC_ROOT} {WORK_ROOT}")
    QC_ROOT.mkdir(parents=True)
    WORK_ROOT.mkdir(parents=True)

    print("G31_PREFLIGHT\tSTART", flush=True)
    qc, guard_rows = guard_preflight()
    semantics = semantics_audit()
    print("G31_PREFLIGHT\tPASS", flush=True)
    print("G31_CATALOG_GEOMETRY\tSTART", flush=True)
    target_meta, catalog_summary, alias_rows, raw_clusters, padded_clusters, source_geometry_rows = read_catalog_geometry()
    print(
        f"G31_CATALOG_GEOMETRY\tPASS\ttargets={catalog_summary['catalog_targets']}"
        f"\traw_union_bp={catalog_summary['raw_interval_union_bp']}"
        f"\tpadded_union_bp={catalog_summary['padded_interval_union_bp']}",
        flush=True,
    )
    full_profile = Profile("full_5312696", EXPECTED_FULL["input_reads"], FULL_SHARDS_ROOT, EXPECTED_FULL["shards"], True)
    p500 = Profile("accepted_500k", 500_000, SHARDS_500K, 12, True)
    p100 = Profile("accepted_100k", 100_000, SHARDS_100K, 12, False)

    full_shards = discover_shards(full_profile)
    checkpoint_rows = validate_full_shards_against_checkpoint(full_shards)
    # run_profile discovers again deliberately; discovery is cheap and serves as a second path check.
    aggregates: dict[str, dict[str, Any]] = {}
    aggregate, _ = run_profile(full_profile, target_meta, workers)
    aggregates[full_profile.name] = aggregate
    aggregate, _ = run_profile(p500, target_meta, workers)
    aggregates[p500.name] = aggregate
    if SHARDS_100K.is_dir():
        aggregate, _ = run_profile(p100, target_meta, workers)
        aggregates[p100.name] = aggregate

    full = aggregates[full_profile.name]
    summaries = [profile_summary(aggregates[name]) for name in aggregates]
    full_summary = next(row for row in summaries if row["profile"] == full_profile.name)

    # Exact expected full counts and candidate-entry denominator checks.
    expected_stage = {
        "assignment": EXPECTED_FULL["candidate_rows"],
        "projection": EXPECTED_FULL["projection_rows"],
        "motif_jobs": EXPECTED_FULL["projection_rows"],
        "caller_calls": EXPECTED_FULL["caller_attempt_rows"],
        "general_repeat_calls": EXPECTED_FULL["general_repeat_calls_rows"],
        "read_evidence": EXPECTED_FULL["read_evidence_rows"],
    }
    for stage, expected in expected_stage.items():
        if full["stage_rows"][stage] != expected:
            full["lineage"][f"full_expected_row_mismatch::{stage}"] += abs(full["stage_rows"][stage] - expected)
    if full["candidate_categories"]["candidate_reads"] != EXPECTED_FULL["candidate_reads"]:
        full["lineage"]["full_expected_candidate_read_mismatch"] += abs(
            full["candidate_categories"]["candidate_reads"] - EXPECTED_FULL["candidate_reads"]
        )
    accepted_500k = aggregates["accepted_500k"]
    expected_500k_stage = {
        "assignment": EXPECTED_500K["candidate_rows"],
        "projection": EXPECTED_500K["projection_rows"],
        "motif_jobs": EXPECTED_500K["projection_rows"],
        "caller_calls": EXPECTED_500K["caller_attempt_rows"],
        "general_repeat_calls": EXPECTED_500K["general_repeat_calls_rows"],
        "read_evidence": EXPECTED_500K["read_evidence_rows"],
    }
    for stage, expected in expected_500k_stage.items():
        if accepted_500k["stage_rows"][stage] != expected:
            accepted_500k["lineage"][f"accepted_500k_expected_row_mismatch::{stage}"] += abs(
                accepted_500k["stage_rows"][stage] - expected
            )
    if accepted_500k["candidate_categories"]["candidate_reads"] != EXPECTED_500K["candidate_reads"]:
        accepted_500k["lineage"]["accepted_500k_expected_candidate_read_mismatch"] += abs(
            accepted_500k["candidate_categories"]["candidate_reads"]
            - EXPECTED_500K["candidate_reads"]
        )

    # Candidate-entry decomposition must partition the candidate universe exactly.
    for profile_name, profile_aggregate in aggregates.items():
        candidate_count = int(profile_aggregate["candidate_categories"]["candidate_reads"])
        assignment_rows = int(profile_aggregate["stage_rows"]["assignment"])
        exact_partition = (
            int(profile_aggregate["candidate_categories"]["exact_any_reads"])
            + int(profile_aggregate["candidate_categories"]["proximal_only_reads"])
        )
        support_partition = sum(
            int(profile_aggregate["candidate_categories"][key])
            for key in (
                "primary_supported_reads", "supplementary_only_reads",
                "secondary_only_reads", "no_support_flag_reads",
            )
        )
        source_combo_partition = sum(
            int(value) for key, value in profile_aggregate["candidate_categories"].items()
            if key.startswith("source_combination::")
        )
        basis_support_partition = sum(
            int(value) for key, value in profile_aggregate["candidate_categories"].items()
            if key.startswith("entry_basis_support::")
        )
        basis_support_combo_partition = sum(
            int(value) for key, value in profile_aggregate["candidate_categories"].items()
            if key.startswith("entry_basis_support_combo::")
        )
        basis_source_partition = sum(
            int(value) for key, value in profile_aggregate["candidate_categories"].items()
            if key.startswith("entry_basis_source::")
        )
        row_basis_partition = sum(
            int(value) for key, value in profile_aggregate["row_categories"].items()
            if key.startswith("candidate_basis::")
        )
        row_support_partition = sum(
            int(value) for key, value in profile_aggregate["row_categories"].items()
            if key.startswith("support_combination::")
        )
        checks = {
            "candidate_exact_proximal_partition_mismatch": (exact_partition, candidate_count),
            "candidate_support_partition_mismatch": (support_partition, candidate_count),
            "candidate_source_combination_partition_mismatch": (source_combo_partition, candidate_count),
            "candidate_basis_support_partition_mismatch": (basis_support_partition, candidate_count),
            "candidate_basis_support_combo_partition_mismatch": (basis_support_combo_partition, candidate_count),
            "candidate_basis_source_partition_mismatch": (basis_source_partition, candidate_count),
            "assignment_row_basis_partition_mismatch": (row_basis_partition, assignment_rows),
            "assignment_row_support_partition_mismatch": (row_support_partition, assignment_rows),
        }
        for metric, (observed, expected) in checks.items():
            if observed != expected:
                profile_aggregate["lineage"][metric] += abs(observed - expected) or 1

    # Recompute profile summaries after expected-count checks were added.
    summaries = [profile_summary(aggregates[name]) for name in aggregates]
    full_summary = next(row for row in summaries if row["profile"] == full_profile.name)
    hard_total = 0
    hard_rows: list[dict[str, Any]] = []
    for profile_name, profile_aggregate in aggregates.items():
        profile_hard, profile_rows = hard_violation_counts(profile_aggregate)
        hard_total += profile_hard
        hard_rows.extend({"profile": profile_name, **row} for row in profile_rows)
    candidate_rate = full_summary["candidate_read_rate"]
    primary_supported = int(full_summary["primary_supported_candidate_reads"])
    primary_mapped = EXPECTED_FULL["primary_mapped_reads"]
    exact_reads = int(full_summary["exact_any_candidate_reads"])
    proximal_reads = int(full_summary["proximal_only_candidate_reads"])

    summary_by_name = {row["profile"]: row for row in summaries}
    p500_summary = summary_by_name["accepted_500k"]
    rate_delta_500k = candidate_rate - p500_summary["candidate_read_rate"]
    multiplicity_delta_500k = (
        full_summary["candidate_rows_per_candidate_read"]
        - p500_summary["candidate_rows_per_candidate_read"]
    )
    scale_stability = (
        "PASS_STABLE"
        if abs(rate_delta_500k) <= 0.01
        and abs(multiplicity_delta_500k) / p500_summary["candidate_rows_per_candidate_read"] <= 0.05
        else "REVIEW_SCALE_SHIFT"
    )

    # Write primary audit outputs.
    write_tsv(QC_ROOT / "preflight_hash_guards.tsv", list(guard_rows[0]), guard_rows)
    write_tsv(QC_ROOT / "checkpoint_stat_integrity.tsv", list(checkpoint_rows[0]), checkpoint_rows)
    write_tsv(QC_ROOT / "candidate_assignment_semantics.tsv", list(semantics[0]), semantics)
    write_metrics(QC_ROOT / "catalog_geometry_summary.tsv", [(k, v) for k, v in catalog_summary.items()])
    write_tsv(
        QC_ROOT / "catalog_source_geometry.tsv",
        ["target_source", "target_count", "raw_total_bp", "raw_union_bp", "raw_genome_fraction", "raw_redundancy_ratio", "raw_max_overlap_depth", "padded500_total_bp", "padded500_union_bp", "padded500_genome_fraction", "padded500_redundancy_ratio", "padded500_max_overlap_depth"],
        source_geometry_rows,
    )
    write_tsv(QC_ROOT / "catalog_exact_coordinate_alias_groups.tsv.gz", ["chrom", "start", "end", "target_count", "target_keys"], alias_rows, gzip_output=True)
    write_tsv(QC_ROOT / "catalog_raw_overlap_clusters.tsv.gz", ["cluster_id", "chrom", "start", "end", "span_bp", "target_count", "target_keys"], raw_clusters, gzip_output=True)
    write_tsv(QC_ROOT / "catalog_padded500_overlap_clusters.tsv.gz", ["cluster_id", "chrom", "start", "end", "span_bp", "target_count", "target_keys"], padded_clusters, gzip_output=True)

    profile_fields = list(summaries[0])
    write_tsv(QC_ROOT / "cross_scale_profile_summary.tsv", profile_fields, summaries)
    cross_rows = []
    for row in summaries:
        cross_rows.extend([
            {"profile": row["profile"], "metric": "candidate_read_rate", "value": f"{row['candidate_read_rate']:.12f}"},
            {"profile": row["profile"], "metric": "candidate_rows_per_candidate_read", "value": f"{row['candidate_rows_per_candidate_read']:.12f}"},
            {"profile": row["profile"], "metric": "candidate_rows_per_input_read", "value": f"{row['candidate_rows_per_input_read']:.12f}"},
        ])
    write_tsv(QC_ROOT / "cross_scale_comparison.tsv", ["profile", "metric", "value"], cross_rows)

    category_rows: list[dict[str, Any]] = []
    for profile_name, aggregate in aggregates.items():
        for category_class in ("candidate_categories", "row_categories"):
            for metric, value in sorted(aggregate[category_class].items()):
                category_rows.append({
                    "profile": profile_name,
                    "category_class": category_class,
                    "metric": metric,
                    "value": value,
                })
    write_tsv(
        QC_ROOT / "candidate_and_row_category_counts.tsv",
        ["profile", "category_class", "metric", "value"],
        category_rows,
    )

    candidate_entry_rows = [
        ("input_reads", EXPECTED_FULL["input_reads"]),
        ("primary_mapped_reads", primary_mapped),
        ("primary_unmapped_reads", EXPECTED_FULL["primary_unmapped_reads"]),
        ("candidate_reads", full_summary["candidate_reads"]),
        ("candidate_read_rate_all_input", f"{candidate_rate:.12f}"),
        ("candidate_read_rate_percent_all_input", f"{candidate_rate * 100:.6f}"),
        ("primary_supported_candidate_reads", primary_supported),
        ("primary_mapped_non_candidate_reads", primary_mapped - primary_supported),
        ("candidate_reads_without_primary_support", full_summary["candidate_reads"] - primary_supported),
        ("primary_supported_candidate_rate_among_primary_mapped", f"{primary_supported / primary_mapped:.12f}"),
        ("primary_supported_candidate_rate_percent_among_primary_mapped", f"{primary_supported / primary_mapped * 100:.6f}"),
        ("all_candidate_reads_over_primary_mapped_context_ratio", f"{full_summary['candidate_reads'] / primary_mapped:.12f}"),
        ("exact_any_candidate_reads", exact_reads),
        ("exact_any_fraction_of_candidate_reads", f"{exact_reads / full_summary['candidate_reads']:.12f}"),
        ("exact_any_candidate_rate_all_input", f"{exact_reads / EXPECTED_FULL['input_reads']:.12f}"),
        ("proximal_only_candidate_reads", proximal_reads),
        ("proximal_only_fraction_of_candidate_reads", f"{proximal_reads / full_summary['candidate_reads']:.12f}"),
        ("proximal_only_candidate_rate_all_input", f"{proximal_reads / EXPECTED_FULL['input_reads']:.12f}"),
        ("exact_overlap_assignment_rows", full["row_categories"]["candidate_basis::exact_overlap"]),
        ("exact_overlap_assignment_row_fraction", f"{full['row_categories']['candidate_basis::exact_overlap'] / full_summary['candidate_rows']:.12f}"),
        ("proximal_within_padding_assignment_rows", full["row_categories"]["candidate_basis::proximal_within_padding"]),
        ("proximal_within_padding_assignment_row_fraction", f"{full['row_categories']['candidate_basis::proximal_within_padding'] / full_summary['candidate_rows']:.12f}"),
        ("supplementary_only_candidate_reads", full_summary["supplementary_only_candidate_reads"]),
        ("secondary_only_candidate_reads", full_summary["secondary_only_candidate_reads"]),
        ("catalog_raw_union_genome_fraction", f"{catalog_summary['raw_genome_fraction']:.12f}"),
        ("catalog_padded500_union_genome_fraction", f"{catalog_summary['padded_genome_fraction']:.12f}"),
        ("catalog_raw_redundancy_ratio", f"{catalog_summary['raw_redundancy_ratio']:.9f}"),
        ("catalog_padded500_redundancy_ratio", f"{catalog_summary['padded_redundancy_ratio']:.9f}"),
        ("assignment_excess_over_unique_loci", full["candidate_categories"]["assignment_excess_over_unique_loci"]),
        ("assignment_excess_over_unique_loci_fraction_of_candidate_rows", f"{full['candidate_categories']['assignment_excess_over_unique_loci'] / full_summary['candidate_rows']:.12f}"),
        ("candidate_rows_after_per_read_locus_dedup", full_summary["candidate_rows"] - full["candidate_categories"]["assignment_excess_over_unique_loci"]),
        ("assignment_excess_over_unique_raw_clusters", full["candidate_categories"]["assignment_excess_over_unique_raw_clusters"]),
        ("assignment_excess_over_unique_raw_clusters_fraction_of_candidate_rows", f"{full['candidate_categories']['assignment_excess_over_unique_raw_clusters'] / full_summary['candidate_rows']:.12f}"),
        ("candidate_rows_after_per_read_raw_cluster_dedup", full_summary["candidate_rows"] - full["candidate_categories"]["assignment_excess_over_unique_raw_clusters"]),
        ("assignment_excess_over_unique_padded_clusters", full["candidate_categories"]["assignment_excess_over_unique_padded_clusters"]),
        ("assignment_excess_over_unique_padded_clusters_fraction_of_candidate_rows", f"{full['candidate_categories']['assignment_excess_over_unique_padded_clusters'] / full_summary['candidate_rows']:.12f}"),
        ("candidate_rows_after_per_read_padded_cluster_dedup", full_summary["candidate_rows"] - full["candidate_categories"]["assignment_excess_over_unique_padded_clusters"]),
        ("full_minus_500k_candidate_rate", f"{rate_delta_500k:.12f}"),
        ("full_minus_500k_rows_per_candidate_read", f"{multiplicity_delta_500k:.12f}"),
        ("cross_scale_candidate_entry_stability", scale_stability),
        ("catalog_coverage_interpretation", "GENOME_WIDE_FRACTION_IS_CONTEXT_ONLY_TRANSCRIPTOME_EXPRESSION_IS_NONUNIFORM"),
        ("candidate_entry_rate_machine_status", "REVIEW_EXPLICIT_PRO_INTERPRETATION_REQUIRED"),
    ]
    write_metrics(QC_ROOT / "candidate_entry_rate_and_reason_audit.tsv", candidate_entry_rows)

    read_class_rows: list[dict[str, Any]] = []
    for metric, value in sorted(full["candidate_categories"].items()):
        if not (
            metric.startswith("entry_basis_")
            or metric.startswith("source_combination::")
            or metric.startswith("support_combination_reads::")
        ):
            continue
        read_class_rows.append({
            "metric": metric,
            "candidate_reads": value,
            "fraction_of_all_input_reads": f"{value / EXPECTED_FULL['input_reads']:.12f}",
            "fraction_of_candidate_reads": f"{value / full_summary['candidate_reads']:.12f}",
        })
    write_tsv(
        QC_ROOT / "candidate_entry_read_class_decomposition.tsv",
        ["metric", "candidate_reads", "fraction_of_all_input_reads", "fraction_of_candidate_reads"],
        read_class_rows,
    )

    source_geometry = {row["target_source"]: row for row in source_geometry_rows}
    source_entry_rows: list[dict[str, Any]] = []
    all_sources = sorted(
        set(source_geometry)
        | set(full["concentration"]["source_rows"])
        | set(full["concentration"]["source_unique_reads"])
    )
    for source in all_sources:
        geometry = source_geometry.get(source, {})
        assignment_rows = int(full["concentration"]["source_rows"].get(source, 0))
        source_reads = int(full["concentration"]["source_unique_reads"].get(source, 0))
        source_entry_rows.append({
            "target_source": source,
            "catalog_target_count": geometry.get("target_count", 0),
            "raw_union_bp": geometry.get("raw_union_bp", 0),
            "raw_genome_fraction": geometry.get("raw_genome_fraction", "0.000000000000"),
            "raw_redundancy_ratio": geometry.get("raw_redundancy_ratio", "0.000000000"),
            "padded500_union_bp": geometry.get("padded500_union_bp", 0),
            "padded500_genome_fraction": geometry.get("padded500_genome_fraction", "0.000000000000"),
            "padded500_redundancy_ratio": geometry.get("padded500_redundancy_ratio", "0.000000000"),
            "assignment_rows": assignment_rows,
            "unique_candidate_reads": source_reads,
            "candidate_read_rate_all_input": f"{source_reads / EXPECTED_FULL['input_reads']:.12f}",
            "fraction_of_all_candidate_reads": f"{source_reads / full_summary['candidate_reads']:.12f}",
            "assignment_rows_per_source_candidate_read": f"{assignment_rows / source_reads:.9f}" if source_reads else ".",
        })
    write_tsv(
        QC_ROOT / "candidate_entry_by_catalog_source.tsv",
        [
            "target_source", "catalog_target_count", "raw_union_bp",
            "raw_genome_fraction", "raw_redundancy_ratio",
            "padded500_union_bp", "padded500_genome_fraction",
            "padded500_redundancy_ratio", "assignment_rows",
            "unique_candidate_reads", "candidate_read_rate_all_input",
            "fraction_of_all_candidate_reads",
            "assignment_rows_per_source_candidate_read",
        ],
        source_entry_rows,
    )

    region_catalog_counts = json.loads(catalog_summary["region_type_counts_json"])
    region_entry_rows: list[dict[str, Any]] = []
    for region_type in sorted(
        set(region_catalog_counts)
        | set(full["concentration"]["region_type_rows"])
        | set(full["concentration"]["region_type_unique_reads"])
    ):
        assignment_rows = int(full["concentration"]["region_type_rows"].get(region_type, 0))
        region_reads = int(full["concentration"]["region_type_unique_reads"].get(region_type, 0))
        region_entry_rows.append({
            "region_type": region_type,
            "catalog_target_count": int(region_catalog_counts.get(region_type, 0)),
            "assignment_rows": assignment_rows,
            "unique_candidate_reads": region_reads,
            "candidate_read_rate_all_input": f"{region_reads / EXPECTED_FULL['input_reads']:.12f}",
            "fraction_of_all_candidate_reads": f"{region_reads / full_summary['candidate_reads']:.12f}",
            "assignment_rows_per_region_candidate_read": f"{assignment_rows / region_reads:.9f}" if region_reads else ".",
        })
    write_tsv(
        QC_ROOT / "candidate_entry_by_region_type.tsv",
        [
            "region_type", "catalog_target_count", "assignment_rows",
            "unique_candidate_reads", "candidate_read_rate_all_input",
            "fraction_of_all_candidate_reads",
            "assignment_rows_per_region_candidate_read",
        ],
        region_entry_rows,
    )

    cross_entry_rows: list[dict[str, Any]] = []
    for row in summaries:
        candidate_count = int(row["candidate_reads"])
        for metric in (
            "exact_any_candidate_reads", "proximal_only_candidate_reads",
            "primary_supported_candidate_reads",
            "supplementary_only_candidate_reads",
            "secondary_only_candidate_reads",
        ):
            value = int(row[metric])
            cross_entry_rows.append({
                "profile": row["profile"],
                "metric": metric,
                "candidate_reads": value,
                "fraction_of_candidate_reads": f"{value / candidate_count:.12f}" if candidate_count else "0.000000000000",
                "fraction_of_input_reads": f"{value / int(row['input_reads']):.12f}" if int(row["input_reads"]) else "0.000000000000",
            })
    write_tsv(
        QC_ROOT / "cross_scale_candidate_entry_decomposition.tsv",
        ["profile", "metric", "candidate_reads", "fraction_of_candidate_reads", "fraction_of_input_reads"],
        cross_entry_rows,
    )

    flow_rows = []
    previous: int | None = None
    for stage in ("assignment", "projection", "motif_jobs", "caller_calls", "general_repeat_calls", "read_evidence"):
        rows = full["stage_rows"][stage]
        flow_rows.append({
            "stage": stage, "rows": rows,
            "unique_reads": full["stage_unique_reads"][stage],
            "delta_from_previous": "." if previous is None else rows - previous,
            "expected_rows": expected_stage[stage],
            "expected_match": str(rows == expected_stage[stage]).lower(),
        })
        previous = rows
    flow_rows.append({
        "stage": "job_canonical_motif_hypotheses", "rows": full["row_categories"]["canonical_motif_hypothesis_sum"],
        "unique_reads": full["stage_unique_reads"]["motif_jobs"], "delta_from_previous": ".",
        "expected_rows": "NOT_ONE_TO_ONE_BY_DESIGN", "expected_match": "DESCRIPTIVE",
    })
    flow_rows.append({
        "stage": "caller_hypothesis_count_sum", "rows": full["row_categories"]["caller_hypothesis_count_sum"],
        "unique_reads": full["stage_unique_reads"]["caller_calls"], "delta_from_previous": ".",
        "expected_rows": "CALLER_INTERNAL_HYPOTHESIS_TOTAL", "expected_match": "DESCRIPTIVE",
    })
    write_tsv(QC_ROOT / "stage_flow_conservation.tsv", list(flow_rows[0]), flow_rows)
    write_tsv(QC_ROOT / "hard_lineage_and_duplicate_audit.tsv", ["profile", "category", "metric", "value", "severity"], hard_rows)

    mult_rows: list[dict[str, Any]] = []
    for name, aggregate in aggregates.items():
        mult_rows.extend(multiplicity_rows(name, aggregate["histograms"]))
    write_tsv(
        QC_ROOT / "read_multiplicity_distribution.tsv",
        ["profile", "metric", "row_type", "category", "reads", "fraction", "mean", "p50", "p90", "p95", "p99", "p99_9", "max"],
        mult_rows,
    )

    per_shard_rows = []
    for aggregate in aggregates.values():
        per_shard_rows.extend(aggregate["per_shard"])
    write_tsv(QC_ROOT / "per_shard_row_expansion_summary.tsv", list(per_shard_rows[0]), per_shard_rows)

    semantic_rows = []
    for stage, counter in full["semantic_duplicate_classes"].items():
        for metric, value in sorted(counter.items()):
            semantic_rows.append({"stage": stage, "metric": metric, "value": value})
    write_tsv(QC_ROOT / "semantic_duplicate_classification.tsv", ["stage", "metric", "value"], semantic_rows)
    write_tsv(
        QC_ROOT / "semantic_duplicate_examples.tsv.gz",
        ["stage", "read_id", "locus", "motif", "rows", "excess_rows", "target_count", "raw_cluster_count", "padded_cluster_count", "classification", "target_keys"],
        full["semantic_examples"], gzip_output=True,
    )
    write_tsv(
        QC_ROOT / "high_multiplicity_tail_dossier.tsv.gz",
        ["read_id", "candidate_rows", "unique_loci", "unique_raw_clusters", "unique_padded_clusters", "unique_catalog_motifs", "unique_locus_catalog_motifs", "unique_motifs", "unique_locus_motifs", "candidate_basis", "primary_support", "supplementary_support", "secondary_support", "source_combination"],
        full["top_reads"], gzip_output=True,
    )

    concentration_dimensions = [
        ("target", "target_rows", "target_unique_reads"),
        ("locus", "locus_rows", "locus_unique_reads"),
        ("raw_catalog_cluster", "raw_cluster_rows", "raw_cluster_unique_reads"),
        ("padded500_catalog_cluster", "padded_cluster_rows", "padded_cluster_unique_reads"),
        ("catalog_motif_candidate", "catalog_motif_candidate_rows", "catalog_motif_unique_reads"),
        ("locus_catalog_motif_candidate", "locus_catalog_motif_rows", "locus_catalog_motif_unique_reads"),
        ("canonical_motif_hypothesis", "motif_hypothesis_rows", "motif_unique_reads"),
        ("locus_motif_hypothesis", "locus_motif_hypothesis_rows", "locus_motif_unique_reads"),
        ("catalog_source", "source_rows", "source_unique_reads"),
        ("region_type", "region_type_rows", "region_type_unique_reads"),
    ]
    concentration_summary_rows = []
    for dimension, rows_key, unique_key in concentration_dimensions:
        counts = full["concentration"][rows_key]
        uniques = full["concentration"][unique_key] if unique_key else None
        concentration_summary_rows.append(concentration_summary(dimension, counts, sum(counts.values())))
        write_concentration(QC_ROOT / f"{dimension}_concentration.tsv.gz", full_profile.name, dimension, counts, uniques)
    write_tsv(QC_ROOT / "concentration_summary.tsv", list(concentration_summary_rows[0]), concentration_summary_rows)

    header_rows = []
    for profile_name, aggregate in aggregates.items():
        for role, variants in aggregate["headers"].items():
            for header, count in variants.items():
                header_rows.append({"profile": profile_name, "role": role, "shards": count, "header": header})
    write_tsv(QC_ROOT / "table_header_inventory.tsv", ["profile", "role", "shards", "header"], header_rows)

    candidate_rate_expected = EXPECTED_FULL["candidate_reads"] / EXPECTED_FULL["input_reads"]
    final_machine_status = "FAIL_OVEREXPANSION_OR_LINEAGE" if hard_total else "REVIEW_G31_PRO_INTERPRETATION_REQUIRED"
    gate_status = "OPEN_BLOCKING" if hard_total == 0 else "FAIL_BLOCKING"
    qc_rows = [
        ("stage_version", VERSION),
        ("gate_id", "G31"),
        ("gate_name", "FULL_SCALE_ROW_EXPANSION_MULTIPLICITY_AND_CANDIDATE_ENTRY_AUDIT"),
        ("full_run_id", FULL_RUN_ID),
        ("input_reads", EXPECTED_FULL["input_reads"]),
        ("candidate_reads", full_summary["candidate_reads"]),
        ("candidate_read_rate", f"{candidate_rate:.12f}"),
        ("candidate_read_rate_percent", f"{candidate_rate * 100:.6f}"),
        ("expected_candidate_read_rate_from_full_qc", f"{candidate_rate_expected:.12f}"),
        ("candidate_rows", full_summary["candidate_rows"]),
        ("candidate_rows_per_candidate_read", f"{full_summary['candidate_rows_per_candidate_read']:.12f}"),
        ("candidate_rows_per_input_read", f"{full_summary['candidate_rows_per_input_read']:.12f}"),
        ("stage_row_conservation", "PASS" if all(full["stage_rows"][stage] == EXPECTED_FULL["candidate_rows"] for stage in ("assignment", "projection", "motif_jobs", "caller_calls", "general_repeat_calls", "read_evidence")) else "FAIL"),
        ("hard_lineage_or_exact_duplicate_violations", hard_total),
        ("key_level_lineage_status", "PASS" if hard_total == 0 else "FAIL"),
        ("primary_key_duplicate_status", "PASS" if sum(full["duplicates"].values()) == 0 else "FAIL"),
        ("global_primary_id_uniqueness_guard", "PASS"),
        ("exact_full_row_duplicate_inference", "ZERO_WHEN_DETERMINISTIC_PRIMARY_KEY_DUPLICATES_ARE_ZERO"),
        ("catalog_geometry_quantified", "PASS"),
        ("candidate_entry_by_catalog_source_quantified", "PASS"),
        ("candidate_entry_by_region_type_quantified", "PASS"),
        ("candidate_entry_basis_support_source_decomposition", "PASS"),
        ("candidate_entry_rate_reason_decomposition", "PASS"),
        ("candidate_entry_decomposition_partition_conservation", "PASS" if hard_total == 0 else "SEE_HARD_AUDIT"),
        ("candidate_entry_rate_explicitly_audited", "true"),
        ("candidate_entry_rate_interpretation_status", "REVIEW_EXPLICIT_PRO_INTERPRETATION_REQUIRED"),
        ("cross_scale_stability_status", scale_stability),
        ("validator_pass_treated_as_sufficient_for_g31", "false"),
        ("g31_machine_status", final_machine_status),
        ("g31_core_freeze_gate_status", gate_status),
        ("core_freeze_authorized_by_this_audit", "false"),
        ("active_pipeline_modified", "false"),
        ("ssot_modified", "false"),
        ("full_5_31m_rerun", "false"),
        ("audit_mode", "READ_ONLY_EXISTING_ARTIFACTS_MEMORY_BOUNDED_SHARD_PARALLEL"),
        ("workers", workers),
        ("elapsed_seconds", f"{time.perf_counter() - started:.6f}"),
        ("next_gate", "PRO_INTERPRET_G31_CANDIDATE_ENTRY_MULTIPLICITY_CONCENTRATION_AND_CATALOG_OVERLAP"),
    ]
    write_metrics(QC_ROOT / "stage15d_g31_row_expansion_audit.qc.tsv", qc_rows)

    gate_rows = [{
        "gate_id": "G31",
        "requirement": "Full-scale row expansion, multiplicity, concentration, catalog overlap, and 11b candidate-entry-rate audit",
        "blocking_for_core_freeze": "true",
        "current_status": gate_status,
        "machine_result": final_machine_status,
        "evidence": str(QC_ROOT / "stage15d_g31_row_expansion_audit.qc.tsv"),
        "validator_pass_sufficient": "false",
        "ssot_registration": "NOT_RUN",
    }]
    write_tsv(GATE_PATH, list(gate_rows[0]), gate_rows)

    doc = f"""# RNA-TR-Scout G31 full-scale row-expansion and candidate-entry audit v0.1.0

## Core Freeze role

G31 is a blocking Core Freeze gate. A schema/package validator PASS is necessary but not sufficient. This audit examines whether the full 5.31M result's 20,656,258 attempt/evidence rows represent intended lossless candidate multiplicity or over-expansion.

## Explicit candidate-entry-rate question

The audit explicitly evaluates the observed 11b candidate rate:

- input reads: {EXPECTED_FULL['input_reads']:,}
- candidate reads: {EXPECTED_FULL['candidate_reads']:,}
- candidate read rate: {candidate_rate * 100:.6f}%

The reason decomposition includes exact-overlap versus padding-only candidates, primary/supplementary/secondary support, catalog source combinations, raw and plus/minus-500-bp catalog coverage, exact-coordinate aliases, raw/padded overlap clusters, and 100k/500k/full scale stability. Genome-wide catalog coverage is contextual only because RNA alignments are concentrated in transcribed regions.

## Lineage

The audit verifies key-level conservation across 11b assignment, 11d3 projection, 11e job preparation, caller attempts, general_repeat_calls, and read_evidence. It separately measures within-job canonical motif hypotheses and caller hypothesis counts, so one job row is not incorrectly treated as one motif hypothesis.

## Decisions

- Hard lineage/ID/full-row duplicate violations cause `FAIL_OVEREXPANSION_OR_LINEAGE`.
- If hard checks pass, concentration, semantic duplicates, catalog overlap, high-multiplicity tails, and the 79.29% candidate-entry rate still require Pro interpretation.
- The machine therefore does not auto-PASS G31 solely from validators or row conservation.

This stage reads existing artifacts only. It does not rerun 5.31M, alter the active pipeline, modify SSOT, or change core schema/caller/materializer outputs.
"""
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DOC_PATH.exists() and DOC_PATH.read_text(encoding="utf-8") != doc:
        raise AuditError(f"refusing overwrite of different versioned document: {DOC_PATH}")
    DOC_PATH.write_text(doc, encoding="utf-8", newline="\n")
    install_status = install_exact(Path(__file__).resolve(), SCRIPT_INSTALL, 0o755)

    artifact_rows = []
    for path in sorted(QC_ROOT.rglob("*")):
        if path.is_file():
            artifact_rows.append({
                "relative_path": str(path.relative_to(QC_ROOT)),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            })
    write_tsv(QC_ROOT / "artifact_manifest.tsv", ["relative_path", "bytes", "sha256"], artifact_rows)
    digest = create_bundle(
        SUCCESS_BUNDLE,
        [QC_ROOT, DOC_PATH, GATE_PATH, SCRIPT_INSTALL],
        "rnatr_stage15d_g31_row_expansion_audit_v0.1.0",
    )
    shutil.rmtree(WORK_ROOT)

    print("===== RNA-TR-SCOUT STAGE 15D G31 ROW-EXPANSION AUDIT =====")
    for key, value in qc_rows:
        print(f"{key}\t{value}")
    print(f"script_installation\t{install_status}")
    print(f"OUTPUT_BUNDLE\t{SUCCESS_BUNDLE}")
    print(f"OUTPUT_BUNDLE_SHA256\t{digest}")
    return 0


def failure_bundle(exc: BaseException) -> None:
    try:
        QC_ROOT.mkdir(parents=True, exist_ok=True)
        failure = QC_ROOT / "stage15d_g31_row_expansion_audit.failure.txt"
        failure.write_text(
            f"stage_version\t{VERSION}\n"
            f"exception_type\t{type(exc).__name__}\n"
            f"exception\t{exc}\n"
            f"active_pipeline_modified\tfalse\n"
            f"ssot_modified\tfalse\n"
            f"full_5_31m_rerun\tfalse\n\n"
            + traceback.format_exc(),
            encoding="utf-8",
        )
        digest = create_bundle(
            FAILURE_BUNDLE,
            [QC_ROOT, WORK_ROOT, Path(__file__).resolve()],
            "rnatr_stage15d_g31_row_expansion_audit_v0.1.0_failure",
        )
        print(f"FAILURE_BUNDLE\t{FAILURE_BUNDLE}", file=sys.stderr)
        print(f"FAILURE_BUNDLE_SHA256\t{digest}", file=sys.stderr)
    except Exception as bundle_exc:
        print(f"WARNING: failure bundle creation failed: {bundle_exc}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=min(6, os.cpu_count() or 1))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.workers < 1 or args.workers > 12:
        raise AuditError("--workers must be between 1 and 12")
    return main_audit(args.workers)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        if "--self-test" not in sys.argv:
            failure_bundle(exc)
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
