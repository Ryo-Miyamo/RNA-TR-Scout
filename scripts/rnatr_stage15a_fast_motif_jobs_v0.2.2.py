from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import multiprocessing as mp
import os
import re
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

STAGE_VERSION = "rnatr_stage15a_fast_motif_jobs_v0.2.2"
EXPECTED_TREX_TARGETS = 349_410
EXPECTED_STRCHIVE_TARGETS = 80
IUPAC = set("ACGTRYSWKMBDHVN")
ACGT = set("ACGT")
COMPLEMENT = str.maketrans("ACGTRYSWKMBDHVN", "TGCAYRSWMKVHDBN")
MISSING_TOKENS = {"", ".", "NONE", "NA", "N/A", "NULL", "NAN"}
TARGET_METADATA: dict[tuple[str, str], dict[str, Any]] = {}

JOB_COLUMNS = [
    "schema_version",
    "projection_id",
    "read_id",
    "target_region_id",
    "target_source",
    "region_type",
    "analysis_mode",
    "representative_locus_id",
    "assignment_rank",
    "read_candidate_target_count",
    "candidate_basis",
    "geometry_class",
    "potential_evidence_class",
    "projection_status",
    "candidate_window_read_start",
    "candidate_window_read_end",
    "candidate_window_length_bp",
    "motif_candidates",
    "canonical_motifs",
    "motif_count",
    "motif_min_length_bp",
    "motif_max_length_bp",
    "motif_alphabet_class",
    "scan_strategy",
    "scan_scope",
    "scan_priority",
    "motif_scan_eligible",
    "manual_review_required",
    "gene",
    "structure_token",
    "job_flags",
]


def reverse_complement(sequence: str) -> str:
    return sequence.translate(COMPLEMENT)[::-1]


def rotations(sequence: str) -> list[str]:
    return [sequence[index:] + sequence[:index] for index in range(len(sequence))]


def canonical_motif(sequence: str) -> str:
    sequence = sequence.upper()
    candidates = rotations(sequence)
    candidates.extend(rotations(reverse_complement(sequence)))
    return min(candidates)


def clean_motif_token(token: str) -> str:
    return token.strip().strip("[](){}'\"").replace(" ", "").upper()


def split_motifs(text: str | None) -> list[str]:
    if text is None:
        return []
    text = text.strip()
    if not text or text.upper() in MISSING_TOKENS:
        return []
    tokens = re.split(r"[,;/|\s]+", text)
    motifs: list[str] = []
    for token in tokens:
        motif = clean_motif_token(token)
        if not motif or motif in MISSING_TOKENS:
            continue
        motifs.append(motif)
    return motifs


def infer_motif_from_locus_id(locus_id: str) -> list[str]:
    if not locus_id or locus_id == "." or "-" not in locus_id:
        return []
    token = locus_id.rsplit("-", 1)[-1].upper()
    if token and set(token).issubset(IUPAC):
        return [token]
    return []


def ordered_unique(values: list[str] | Any) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def motif_alphabet_class(motifs: list[str]) -> str:
    if not motifs:
        return "NONE"
    characters = set("".join(motifs))
    if characters.issubset(ACGT):
        return "ACGT_ONLY"
    if characters.issubset(IUPAC):
        return "IUPAC_DEGENERATE"
    return "UNSUPPORTED_SYMBOL"


def choose_scan_strategy(
    target_source: str,
    region_type: str,
    analysis_mode: str,
    manual_review_required: bool,
    motifs: list[str],
    alphabet_class: str,
) -> str:
    lengths = [len(motif) for motif in motifs]
    max_length = max(lengths, default=0)
    if not motifs:
        return "NO_MOTIF_MANUAL_REVIEW"
    if alphabet_class == "UNSUPPORTED_SYMBOL":
        return "UNSUPPORTED_SYMBOL_MANUAL_REVIEW"
    if target_source == "STRchive" and manual_review_required:
        return "COMPLEX_DISEASE_REGION_SEQUENCE_REVIEW"
    if region_type == "VC":
        return "VARIATION_CLUSTER_MULTI_MOTIF_SEQUENCE_SCAN"
    if analysis_mode == "sequence_level_disease_region":
        return "COMPLEX_DISEASE_REGION_SEQUENCE_REVIEW"
    if max_length > 100:
        return "LONG_UNIT_GT100_SEQUENCE_REVIEW"
    if max_length > 20:
        return "LONG_UNIT_21_TO_100_PERIODIC_SCAN"
    if alphabet_class == "IUPAC_DEGENERATE":
        return "IUPAC_PERIODIC_SCAN"
    if len(motifs) > 1:
        return "MULTI_MOTIF_PERIODIC_SCAN"
    return "SIMPLE_PERIODIC_SCAN"


def choose_scan_scope(geometry_class: str) -> str:
    if geometry_class == "BOTH_FLANKS_PROJECTABLE":
        return "PROJECTED_TARGET_PLUS_FLANKS"
    if geometry_class in {
        "LEFT_FLANK_ONLY",
        "RIGHT_FLANK_ONLY",
        "PROXIMAL_LEFT_WITH_SOFTCLIP",
        "PROXIMAL_RIGHT_WITH_SOFTCLIP",
    }:
        return "TARGET_FACING_RAW_END"
    if geometry_class == "TARGET_INTERNAL_NO_FLANK":
        return "WHOLE_CANDIDATE_WINDOW"
    return "WHOLE_CANDIDATE_WINDOW_LOW_PRIORITY"


def choose_scan_priority(
    target_source: str,
    assignment_rank: int,
    candidate_basis: str,
    potential_evidence_class: str,
) -> str:
    if target_source == "STRchive":
        return "P0_DISEASE"
    if (
        assignment_rank == 1
        and candidate_basis == "exact_overlap"
        and potential_evidence_class != "NOT_YET_CLASSIFIABLE"
    ):
        return "P1_RANK1_EXACT_GEOMETRY"
    if candidate_basis == "exact_overlap":
        return "P2_OTHER_EXACT"
    return "P3_PROXIMAL"


def load_target_metadata(analysis_regions_path: Path, disease_regions_path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    target_metadata: dict[tuple[str, str], dict[str, Any]] = {}
    with gzip.open(analysis_regions_path, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            key = ("TRExplorer", row["analysis_region_id"])
            if key in target_metadata:
                raise RuntimeError(f"Duplicate analysis target: {key}")
            motifs = split_motifs(row.get("motifs", ""))
            motifs.extend(infer_motif_from_locus_id(row.get("representative_locus_id", "")))
            motifs = ordered_unique(motifs)
            target_metadata[key] = {
                "target_source": "TRExplorer",
                "target_region_id": row["analysis_region_id"],
                "region_type": row["region_type"],
                "analysis_mode": row["analysis_mode"],
                "representative_locus_id": row["representative_locus_id"],
                "motifs": motifs,
                "manual_review_required": False,
                "structure_token": row.get("structure_token", "."),
                "gene": ".",
            }
    with gzip.open(disease_regions_path, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            key = ("STRchive", row["disease_region_id"])
            if key in target_metadata:
                raise RuntimeError(f"Duplicate disease target: {key}")
            motifs: list[str] = []
            motifs.extend(split_motifs(row.get("reference_motif", "")))
            motifs.extend(split_motifs(row.get("pathogenic_motif", "")))
            motifs = ordered_unique(motifs)
            target_metadata[key] = {
                "target_source": "STRchive",
                "target_region_id": row["disease_region_id"],
                "region_type": "DISEASE_REGION",
                "analysis_mode": row["analysis_mode_hint"],
                "representative_locus_id": row.get("matched_trexplorer_locus_id", "."),
                "motifs": motifs,
                "manual_review_required": row["manual_review_required"] == "true",
                "structure_token": ".",
                "gene": row.get("gene", "."),
            }
    trex = sum(key[0] == "TRExplorer" for key in target_metadata)
    strchive = sum(key[0] == "STRchive" for key in target_metadata)
    if trex != EXPECTED_TREX_TARGETS or strchive != EXPECTED_STRCHIVE_TARGETS:
        raise RuntimeError(
            f"catalog target count mismatch: TRExplorer={trex}, STRchive={strchive}"
        )
    return target_metadata


def write_metrics(path: Path, rows: list[tuple[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".part")
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["metric", "value"])
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def open_deterministic_gzip_text(path: Path, compresslevel: int = 1):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = path.open("wb")
    gz = gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=compresslevel, mtime=0)
    text = io.TextIOWrapper(gz, encoding="utf-8", newline="")
    return raw, gz, text


def build_job(row: dict[str, str], metadata: dict[str, Any]) -> dict[str, object]:
    motifs = ordered_unique(metadata["motifs"])
    canonical = ordered_unique(
        [canonical_motif(motif) for motif in motifs if motif and set(motif).issubset(IUPAC)]
    )
    alphabet_class = motif_alphabet_class(motifs)
    manual_review = bool(metadata["manual_review_required"])
    strategy = choose_scan_strategy(
        row["target_source"],
        row["region_type"],
        row["analysis_mode"],
        manual_review,
        motifs,
        alphabet_class,
    )
    scope = choose_scan_scope(row["geometry_class"])
    priority = choose_scan_priority(
        row["target_source"],
        int(row["assignment_rank"]),
        row["candidate_basis"],
        row["potential_evidence_class"],
    )
    window_length = int(row["candidate_window_length_bp"])
    has_window = window_length > 0
    ineligible_strategies = {
        "NO_MOTIF_MANUAL_REVIEW",
        "UNSUPPORTED_SYMBOL_MANUAL_REVIEW",
        "COMPLEX_DISEASE_REGION_SEQUENCE_REVIEW",
        "LONG_UNIT_GT100_SEQUENCE_REVIEW",
    }
    eligible = has_window and strategy not in ineligible_strategies
    job_flags: list[str] = []
    if not has_window:
        job_flags.append("NO_RAW_SEQUENCE_WINDOW")
    if row["projection_status"] != "PASS":
        job_flags.append("PROJECTION_WARN")
    if int(row["read_candidate_target_count"]) > 1:
        job_flags.append("MULTIPLE_TARGET_CANDIDATES")
    if strategy in ineligible_strategies:
        job_flags.append("MANUAL_OR_SPECIALIZED_REVIEW")
    if alphabet_class == "IUPAC_DEGENERATE":
        job_flags.append("DEGENERATE_MOTIF")
    if row["region_type"] == "VC":
        job_flags.append("VARIATION_CLUSTER")
    motif_lengths = [len(motif) for motif in motifs]
    return {
        "schema_version": "0.3.0",
        "projection_id": row["projection_id"],
        "read_id": row["read_id"],
        "target_region_id": row["target_region_id"],
        "target_source": row["target_source"],
        "region_type": row["region_type"],
        "analysis_mode": row["analysis_mode"],
        "representative_locus_id": row["representative_locus_id"],
        "assignment_rank": row["assignment_rank"],
        "read_candidate_target_count": row["read_candidate_target_count"],
        "candidate_basis": row["candidate_basis"],
        "geometry_class": row["geometry_class"],
        "potential_evidence_class": row["potential_evidence_class"],
        "projection_status": row["projection_status"],
        "candidate_window_read_start": row["candidate_window_read_start"],
        "candidate_window_read_end": row["candidate_window_read_end"],
        "candidate_window_length_bp": window_length,
        "motif_candidates": ",".join(motifs) if motifs else ".",
        "canonical_motifs": ",".join(canonical) if canonical else ".",
        "motif_count": len(motifs),
        "motif_min_length_bp": min(motif_lengths) if motif_lengths else ".",
        "motif_max_length_bp": max(motif_lengths) if motif_lengths else ".",
        "motif_alphabet_class": alphabet_class,
        "scan_strategy": strategy,
        "scan_scope": scope,
        "scan_priority": priority,
        "motif_scan_eligible": str(eligible).lower(),
        "manual_review_required": str(manual_review or strategy in ineligible_strategies).lower(),
        "gene": metadata["gene"],
        "structure_token": metadata["structure_token"] or ".",
        "job_flags": ";".join(sorted(set(job_flags))) if job_flags else ".",
    }


def build_one(task: dict[str, object]) -> dict[str, object]:
    projection_path = Path(str(task["projection_path"]))
    jobs_path = Path(str(task["jobs_path"]))
    qc_path = Path(str(task["qc_path"]))
    expected_rows = int(task["expected_rows"])
    expected_reads = int(task["expected_reads"])
    shard = str(task["shard"])
    started = time.perf_counter()
    counts: Counter[str] = Counter()
    projection_ids: set[str] = set()
    read_ids: set[str] = set()
    digest = hashlib.sha256()
    tmp = jobs_path.with_name("." + jobs_path.name + ".part")
    raw, gz, text = open_deterministic_gzip_text(tmp, compresslevel=1)
    try:
        writer = csv.DictWriter(text, fieldnames=JOB_COLUMNS, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        with gzip.open(projection_path, "rt", encoding="utf-8", newline="") as source:
            reader = csv.DictReader(source, delimiter="\t")
            for row in reader:
                counts["projection_rows"] += 1
                projection_id = row["projection_id"]
                if projection_id in projection_ids:
                    raise RuntimeError(f"Duplicate projection_id: {projection_id}")
                projection_ids.add(projection_id)
                read_ids.add(row["read_id"])
                key = (row["target_source"], row["target_region_id"])
                metadata = TARGET_METADATA.get(key)
                if metadata is None:
                    counts["missing_target_metadata"] += 1
                    continue
                job = build_job(row, metadata)
                writer.writerow(job)
                digest.update(projection_id.encode("utf-8"))
                digest.update(b"\n")
                counts[f"strategy::{job['scan_strategy']}"] += 1
                counts[f"scan_scope::{job['scan_scope']}"] += 1
                counts[f"scan_priority::{job['scan_priority']}"] += 1
                counts[f"alphabet::{job['motif_alphabet_class']}"] += 1
                counts[f"eligible::{job['motif_scan_eligible']}"] += 1
                counts[f"region_type::{job['region_type']}"] += 1
                counts[f"potential::{job['potential_evidence_class']}"] += 1
        text.flush()
        text.detach()
        gz.close()
        raw.flush()
        os.fsync(raw.fileno())
        raw.close()
    except Exception:
        try:
            text.close()
        except Exception:
            pass
        try:
            gz.close()
        except Exception:
            pass
        try:
            raw.close()
        except Exception:
            pass
        tmp.unlink(missing_ok=True)
        raise
    os.replace(tmp, jobs_path)
    observed_rows = counts["projection_rows"]
    observed_reads = len(read_ids)
    if observed_rows != expected_rows:
        raise RuntimeError(f"{shard}: projection row mismatch {observed_rows} != {expected_rows}")
    if len(projection_ids) != observed_rows:
        raise RuntimeError(f"{shard}: projection ID uniqueness mismatch")
    if observed_reads != expected_reads:
        raise RuntimeError(f"{shard}: projection read mismatch {observed_reads} != {expected_reads}")
    if counts["missing_target_metadata"] != 0:
        raise RuntimeError(f"{shard}: missing target metadata={counts['missing_target_metadata']}")
    qc_rows: list[tuple[str, object]] = [
        ("stage_version", STAGE_VERSION),
        ("expected_projection_rows", expected_rows),
        ("observed_projection_rows", observed_rows),
        ("unique_projection_ids", len(projection_ids)),
        ("expected_projection_reads", expected_reads),
        ("unique_projection_reads", observed_reads),
        ("catalog_trexplorer_targets", EXPECTED_TREX_TARGETS),
        ("catalog_strchive_targets", EXPECTED_STRCHIVE_TARGETS),
        ("missing_target_metadata", counts["missing_target_metadata"]),
    ]
    for key in sorted(counts):
        if key in {"projection_rows", "missing_target_metadata"}:
            continue
        qc_rows.append((key, counts[key]))
    elapsed = time.perf_counter() - started
    qc_rows.extend(
        [
            ("job_projection_order_sha256", digest.hexdigest()),
            ("elapsed_seconds", f"{elapsed:.9f}"),
            ("audit_status", "PASS"),
        ]
    )
    write_metrics(qc_path, qc_rows)
    return {
        "shard": shard,
        "projection_rows": observed_rows,
        "projection_reads": observed_reads,
        "jobs_bytes": jobs_path.stat().st_size,
        "job_projection_order_sha256": digest.hexdigest(),
        "elapsed_seconds": elapsed,
        "status": "PASS",
    }


def read_manifest(path: Path) -> list[dict[str, object]]:
    tasks: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        required = {"shard", "projection_path", "jobs_path", "qc_path", "expected_rows", "expected_reads"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise RuntimeError(f"invalid manifest header: {reader.fieldnames}")
        for row in reader:
            tasks.append(dict(row))
    if not tasks:
        raise RuntimeError("empty shard manifest")
    return tasks


def write_summary(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["shard", "projection_rows", "projection_reads", "jobs_bytes", "job_projection_order_sha256", "elapsed_seconds", "status"]
    tmp = path.with_name("." + path.name + ".part")
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda row: str(row["shard"])))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--analysis-regions", required=True, type=Path)
    parser.add_argument("--disease-regions", required=True, type=Path)
    parser.add_argument("--shard-manifest", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()
    for path in (args.analysis_regions, args.disease_regions, args.shard_manifest):
        if not path.is_file() or path.stat().st_size == 0:
            raise SystemExit(f"missing input: {path}")
    tasks = read_manifest(args.shard_manifest)
    if args.workers < 1 or args.workers > len(tasks):
        raise SystemExit(f"invalid workers={args.workers} for tasks={len(tasks)}")
    global TARGET_METADATA
    load_started = time.perf_counter()
    TARGET_METADATA = load_target_metadata(args.analysis_regions, args.disease_regions)
    load_seconds = time.perf_counter() - load_started
    context = mp.get_context("fork")
    rows: list[dict[str, object]] = []
    work_started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.workers, mp_context=context) as pool:
        futures = {pool.submit(build_one, task): str(task["shard"]) for task in tasks}
        for future in as_completed(futures):
            rows.append(future.result())
    work_seconds = time.perf_counter() - work_started
    if any(row["status"] != "PASS" for row in rows):
        raise SystemExit("one or more fast motif jobs failed")
    if sum(int(row["projection_rows"]) for row in rows) != 388_571:
        raise SystemExit("aggregate projection row mismatch")
    if sum(int(row["projection_reads"]) for row in rows) != 79_176:
        raise SystemExit("aggregate projection read mismatch")
    write_summary(args.summary, rows)
    print(f"stage_version\t{STAGE_VERSION}")
    print(f"catalog_load_seconds\t{load_seconds:.9f}")
    print(f"parallel_transform_seconds\t{work_seconds:.9f}")
    print(f"shards\t{len(rows)}")
    print("audit_status\tPASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
