#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

VERSION = "rnatr_stage15c_fullscale_input_binding_and_runner_preflight_v0.1.0"
PROJECT_ROOT = Path("/mnt/intelssd/rnatr_project")
SAMPLE_ID = "ENCSR307SHM"
PLANNED_RUN_ID = "ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1"
EXPECTED_READS = 5_312_696
EXPECTED_BASES = 7_165_363_866

FULL_FASTQ_DEFAULT = Path(
    "/media/tokushimaneuro02/T9/rnatr_data/downloads/ENCSR307SHM/ENCFF260PGB.fastq.gz"
)
EXPECTED_FASTQ_BYTES = 8_995_223_210
EXPECTED_FASTQ_MD5 = "23270f6b994db147df2f2f4c53f8358b"

STAGE15B_RUN_ID = "ENCSR307SHM_stage15a500k_seed20260809_mm2splice_v1"
STAGE15B_ROOT = (
    PROJECT_ROOT / "qc/15_stage15b_memory_bounded_validator" / STAGE15B_RUN_ID / "v0.1.0"
)
STAGE15B_QC = STAGE15B_ROOT / "stage15b_memory_bounded_validator.qc.tsv"
STAGE15B_QC_SHA256 = "b5f7f26f91d0edafbdc77de3373b67b8cc9ec3e16fb2f903cec4390a9d47f142"
STAGE15B_PROJECTION = STAGE15B_ROOT / "fullscale_projection_after_candidate.tsv"
STAGE15B_PROJECTION_SHA256 = "bdaccecc9ef4f17d40252445c60a4337ad774fe1ce7eb402089bf7cd8b69f578"
STAGE15B_AUDIT = STAGE15B_ROOT / "architecture_consistency_targeted_audit.tsv"
STAGE15B_AUDIT_SHA256 = "21b36fc32ad33dce3426cdada2a3070f49fe7a6466a9cabd5af0f61dd958c967"

READINESS_ROOT = (
    PROJECT_ROOT / "qc/15_stage15a_fullscale_readiness" / STAGE15B_RUN_ID / "v0.1.0"
)
READINESS_QC = READINESS_ROOT / "fullscale_readiness.qc.tsv"
READINESS_QC_SHA256 = "f9382ea2db482880bb63de75b9506f220db2b83749c38ae06e2a7632b3252250"
RESOURCE_PROJECTION = READINESS_ROOT / "fullscale_resource_projection.tsv"
RESOURCE_PROJECTION_SHA256 = "3012622750a24a81c5b9df6545b6ea3fb22818662d9debbb627b932c516dc6f7"

SCALING500_QC = (
    PROJECT_ROOT / "qc/15_stage15a_bam_to_final" / STAGE15B_RUN_ID
    / "v0.1.1_500k_scaling/stage15a_scaling_500k.qc.tsv"
)
SCALING500_QC_SHA256 = "ef27be62e633e941b21978d8354a928a7ecea33600465fe6620e82640b329e82"

BOUNDED_VALIDATOR = (
    PROJECT_ROOT / "scripts/rnatr_stage15b_validate_package_sharded_memory_bounded_v0.1.0.py"
)
BOUNDED_VALIDATOR_SHA256 = "1136086f0214bcd11a2a2d71f2e459f433c7fc9f51d170aa3b97826e8808ee99"
SCALING500_RUNNER = PROJECT_ROOT / "scripts/rnatr_stage15a_run_scaling_500k_v0.1.1.py"
SCALING500_RUNNER_SHA256 = "bc1718cd5044a472956e445b19ac3f193ffc0db868b1f53dbfe896c1e86892a6"

SSOT_GUARDS = {
    PROJECT_ROOT / "metadata/ssot/rnatr_ssot.py":
        "8aeff1eda5c301e74a9054e786ed19bf5b699ff6aa111221aa2e60f6d733b37b",
    PROJECT_ROOT / "metadata/ssot/rnatr_ssot.sqlite":
        "7edb4eb63e8f04b6fe8d8e67a82a6d9d70ba55c1946c62827d7b133e0d5a4274",
}

FROZEN_GUARDS = {
    PROJECT_ROOT / "scripts/rnatr_stage15a_run_performance_100k_v0.2.2.1.py":
        "7bfb7018cea80cd92854882751cffb49bea817296f69866801a64f9529c5e1a8",
    SCALING500_RUNNER: SCALING500_RUNNER_SHA256,
    PROJECT_ROOT / "config/evidence_schema/v0.4.2/rnatr_v04_validate_package.py":
        "370c93d7730ce919b9c86056f3cd28d49266d41dc34005450d27aaa41d22a96c",
    PROJECT_ROOT / "config/evidence_schema/v0.4.2/rnatr_v041_validate_locus_aggregation.py":
        "dc29030c2d739c87d2d8e3b6eac493e8cf131b2d7f7e819a7d4435bbcd40b29b",
    PROJECT_ROOT / "config/evidence_schema/v0.4.2/rnatr_v041_validate_package.py":
        "e978b109d094f665ec62387ffda35c81d0aa9e8156972069f18a1b0b6c49bba5",
    PROJECT_ROOT / "config/evidence_schema/v0.4.2/rnatr_v042_validate_flank_uniqueness.py":
        "039024835de2bc1f096e562eed69788ecad9e481575b1b8cd58241edf2e87ab5",
    PROJECT_ROOT / "config/evidence_schema/v0.4.2/rnatr_v042_validate_package.py":
        "45c3995550f57a65b3fec4aab7471d57b7000e19471d4c5cf7f3ae055426984e",
    PROJECT_ROOT / "config/evidence_schema/v0.4.2/schema/rnatr_v04_table_schema.json":
        "c0509a0669344dba0b07cd1bb9e71f2aeb01e0196df47ec9178f1d2464b515f1",
    BOUNDED_VALIDATOR: BOUNDED_VALIDATOR_SHA256,
}

ACTIVE_GUARDS = {
    PROJECT_ROOT / "scripts/11b_extract_alignment_segments_and_target_candidates.sh":
        "e00bdaad48080d7cfed01e1b961e0617af0f2239e014cd6fe8924460aa9afd56",
    PROJECT_ROOT / "scripts/11d3_project_targets_to_raw_reads_secondary_seq_fixed.sh":
        "9df2998915e49da27ecf80f24a733d55a498c2ba32b278df881fdefa901a83e2",
    PROJECT_ROOT / "scripts/11e_prepare_motif_scan_jobs.sh":
        "2cc13e2b95711e0d21c05eba1bec3ec26e249d3ec3e80f6ebce4c8157245038a",
    PROJECT_ROOT / "src/rnatr_scout/general_caller/native_v0.4.1/rnatr_general_repeat_caller_ref_v0.4.1.py":
        "d5a2e0545afa5d97026c3a6ac0be6bc355e87f4c130bc512b0b3bf9a5bf32351",
    PROJECT_ROOT / "src/rnatr_scout/materialization/rnatr_materialize_native_v041_to_evidence_v042_v0.1.2.py":
        "18a67ef312e74257549570ae81a6cca364055240f519d29dc7664e2ea1c429ea",
}

# Resource values are the accepted Stage 15A collector projections.
PROJECTED_FULL_TEMP_AND_OUTPUT_BYTES = 145_909_495_000
PROJECTED_FULL_FINAL_PACKAGE_BYTES = 52_078_551_000
COLLECTOR_RECOMMENDED_MINIMUM_FREE_BYTES = 250_066_597_000
OPERATIONAL_RECOMMENDED_FREE_BYTES = 300_000_000_000
MINIMUM_POST_PEAK_RESERVE_BYTES = 100_000_000_000

PLANNED_SHARDS = 12
PLANNED_CALLER_WORKERS_PER_SHARD = 2
PLANNED_VALIDATOR_WORKERS = 3
PLANNED_SORT_BUFFER = "512M"

QC_ROOT = (
    PROJECT_ROOT / "qc/15_stage15c_fullscale_preflight" / SAMPLE_ID / "v0.1.0"
)
META_ROOT = PROJECT_ROOT / "metadata/stage15c/fullscale_preflight_v0.1.0"
DOC_PATH = (
    PROJECT_ROOT / "docs/stage15c/RNA_TR_Scout_fullscale_input_binding_and_runner_preflight_v0.1.0.md"
)
SCRIPT_INSTALL = PROJECT_ROOT / "scripts/rnatr_stage15c_fullscale_input_binding_and_runner_preflight_v0.1.0.py"
DOWNLOADS = Path.home() / "Downloads"
SUCCESS_BUNDLE = DOWNLOADS / "rnatr_stage15c_fullscale_input_binding_preflight_v0.1.0.tar.gz"
FAILURE_BUNDLE = DOWNLOADS / "rnatr_stage15c_fullscale_input_binding_preflight_v0.1.0_failure.tar.gz"

EXCLUDE_BAM_PATTERNS = (
    "pilot100k",
    "sample100k",
    "stage15a250k",
    "stage15a_250k",
    "stage15a500k",
    "stage15a_500k",
    "250k",
    "500k",
    "six_sample",
    "mapped_only",
    "benchmark",
)


class PreflightError(RuntimeError):
    pass


@dataclass
class FastqStats:
    path: Path
    bytes: int
    md5: str
    sha256: str
    reads: int
    bases: int
    unique_ids: int | None
    duplicate_ids: int | None
    sorted_ids: Path | None


@dataclass
class BamBinding:
    path: Path
    bai: Path
    sha256: str
    bai_sha256: str
    bytes: int
    bai_bytes: int
    alignment_records: int
    unique_read_ids: int
    unmapped_records: int
    sort_order: str
    exact_fastq_id_parity: bool
    provenance_paths: list[Path]
    provenance_status: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def md5_sha256_file(path: Path) -> tuple[str, str]:
    md5 = hashlib.md5()
    sha = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            md5.update(block)
            sha.update(block)
    return md5.hexdigest(), sha.hexdigest()


def ensure_file(path: Path) -> None:
    if not path.is_file() or path.stat().st_size <= 0:
        raise PreflightError(f"missing or empty file: {path}")


def read_metrics(path: Path) -> dict[str, str]:
    ensure_file(path)
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames != ["metric", "value"]:
            raise PreflightError(f"unexpected metric TSV schema: {path}: {reader.fieldnames}")
        return {row["metric"]: row["value"] for row in reader}


def atomic_write_tsv(path: Path, fields: list[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".part")
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def atomic_write_metrics(path: Path, rows: Iterable[tuple[str, Any]]) -> None:
    atomic_write_tsv(
        path,
        ["metric", "value"],
        ({"metric": key, "value": str(value)} for key, value in rows),
    )


def install_exact(source: Path, destination: Path, mode: int = 0o755) -> str:
    ensure_file(source)
    digest = sha256_file(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if not destination.is_file() or sha256_file(destination) != digest:
            raise PreflightError(f"refusing to overwrite different versioned file: {destination}")
        destination.chmod(mode)
        return "REUSED_IDENTICAL"
    tmp = destination.with_name("." + destination.name + f".installing.{os.getpid()}")
    shutil.copy2(source, tmp)
    tmp.chmod(mode)
    os.replace(tmp, destination)
    return "INSTALLED_NEW"


def run_text(command: list[str], *, check: bool = True, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(command, text=True, capture_output=True, env=env)
    if check and proc.returncode != 0:
        raise PreflightError(
            f"command failed ({proc.returncode}): {' '.join(command)}\n"
            f"stdout:\n{proc.stdout[-4000:]}\nstderr:\n{proc.stderr[-4000:]}"
        )
    return proc


def count_lines(path: Path) -> int:
    proc = run_text(["wc", "-l", str(path)])
    return int(proc.stdout.split()[0])


def external_sort_unique(source: Path, destination: Path, work: Path, buffer_size: str) -> int:
    work.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    run_text(
        [
            "sort",
            "--unique",
            "--buffer-size", buffer_size,
            "--temporary-directory", str(work),
            "--output", str(destination),
            str(source),
        ],
        env=env,
    )
    return count_lines(destination)


def verify_hash_guards() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    groups = (
        ("SSOT", SSOT_GUARDS),
        ("FROZEN", FROZEN_GUARDS),
        ("ACTIVE", ACTIVE_GUARDS),
        ("EVIDENCE", {
            STAGE15B_QC: STAGE15B_QC_SHA256,
            STAGE15B_PROJECTION: STAGE15B_PROJECTION_SHA256,
            STAGE15B_AUDIT: STAGE15B_AUDIT_SHA256,
            READINESS_QC: READINESS_QC_SHA256,
            RESOURCE_PROJECTION: RESOURCE_PROJECTION_SHA256,
            SCALING500_QC: SCALING500_QC_SHA256,
        }),
    )
    for group, mapping in groups:
        for path, expected in mapping.items():
            observed = "."
            status = "FAIL"
            if path.is_file() and path.stat().st_size > 0:
                observed = sha256_file(path)
                status = "PASS" if observed == expected else "FAIL"
            rows.append({
                "guard_class": group,
                "path": str(path),
                "expected_sha256": expected,
                "observed_sha256": observed,
                "status": status,
            })
            if status != "PASS":
                raise PreflightError(f"guard mismatch: {path}: {observed} != {expected}")
    return rows


def verify_stage15b_contract() -> dict[str, Any]:
    stage = read_metrics(STAGE15B_QC)
    projection = read_metrics(STAGE15B_PROJECTION)
    readiness = read_metrics(READINESS_QC)
    scaling = read_metrics(SCALING500_QC)

    required_stage = {
        "candidate_status": "PROVISIONAL_NOT_ACTIVE",
        "validator_equivalence_status": "PASS",
        "positive_100k_accept_parity": "PASS",
        "positive_500k_accept_parity": "PASS",
        "negative_fixture_accept_reject_parity": "PASS",
        "memory_readiness_status": "PASS",
        "runtime_readiness_status": "PASS_STRICT",
        "package_manifest_integrity_500k": "PASS",
        "active_pipeline_modified": "false",
        "ssot_modified": "false",
        "core_schema_modified": "false",
        "candidate_promoted_active": "false",
        "full_5_31m_run_started": "false",
        "audit_status": "PASS",
        "stage_status": "PASS",
    }
    for key, expected in required_stage.items():
        if stage.get(key) != expected:
            raise PreflightError(f"Stage15B gate mismatch {key}: {stage.get(key)} != {expected}")

    if projection.get("memory_readiness_status") != "PASS":
        raise PreflightError("Stage15B full-scale memory projection is not PASS")
    if float(projection["projected_memory_fraction"]) >= 0.80:
        raise PreflightError(
            f"projected validator memory fraction too high: {projection['projected_memory_fraction']}"
        )
    if projection.get("runtime_readiness_status") != "PASS_STRICT":
        raise PreflightError("Stage15B projected runtime is not PASS_STRICT")

    if readiness.get("deterministic_500k_scaling") != "PASS":
        raise PreflightError("Stage15A readiness does not confirm deterministic 500k PASS")
    if scaling.get("deterministic_500k_scaling") != "PASS":
        raise PreflightError("500k final QC is not PASS")
    if scaling.get("full_5_31m_run_started") != "false":
        raise PreflightError("full 5.31M run was unexpectedly marked started")

    return {
        "stage15b_candidate_path": stage["candidate_path"],
        "stage15b_candidate_sha256": stage["candidate_sha256"],
        "projected_full_bam_to_final_minutes": float(stage["projected_full_bam_to_final_minutes"]),
        "projected_full_validator_peak_rss_kbytes": int(float(projection["projected_full_validator_peak_rss_kbytes"])),
        "host_memtotal_kbytes": int(projection["host_memtotal_kbytes"]),
        "projected_memory_fraction": float(projection["projected_memory_fraction"]),
        "validator_workers": int(projection["projected_workers"]),
        "rss_safety_factor": float(projection["rss_safety_factor"]),
    }


def storage_audit() -> dict[str, Any]:
    usage = shutil.disk_usage(PROJECT_ROOT)
    hard_required = max(
        COLLECTOR_RECOMMENDED_MINIMUM_FREE_BYTES,
        PROJECTED_FULL_TEMP_AND_OUTPUT_BYTES + MINIMUM_POST_PEAK_RESERVE_BYTES,
    )
    hard_status = "PASS" if usage.free >= hard_required else "FAIL"
    operational_status = "PASS" if usage.free >= OPERATIONAL_RECOMMENDED_FREE_BYTES else "REVIEW"
    post_peak_reserve = usage.free - PROJECTED_FULL_TEMP_AND_OUTPUT_BYTES
    if hard_status != "PASS":
        raise PreflightError(
            f"insufficient Intel SSD free bytes: {usage.free} < hard requirement {hard_required}"
        )
    return {
        "filesystem_total_bytes": usage.total,
        "filesystem_used_bytes": usage.used,
        "filesystem_free_bytes": usage.free,
        "collector_minimum_free_bytes": COLLECTOR_RECOMMENDED_MINIMUM_FREE_BYTES,
        "hard_required_free_bytes": hard_required,
        "operational_recommended_free_bytes": OPERATIONAL_RECOMMENDED_FREE_BYTES,
        "projected_temp_and_output_bytes": PROJECTED_FULL_TEMP_AND_OUTPUT_BYTES,
        "projected_final_package_bytes": PROJECTED_FULL_FINAL_PACKAGE_BYTES,
        "projected_post_peak_reserve_bytes": post_peak_reserve,
        "hard_storage_status": hard_status,
        "operational_storage_status": operational_status,
    }


def discover_bams(explicit: Path | None) -> tuple[list[dict[str, Any]], Path | None, str]:
    if explicit is not None:
        return ([{
            "path": str(explicit.resolve()),
            "bytes": explicit.stat().st_size if explicit.is_file() else 0,
            "excluded": "false",
            "exclusion_reason": ".",
            "selection_status": "EXPLICIT",
        }], explicit.resolve(), "EXPLICIT")

    roots = [
        PROJECT_ROOT / "results/11_mapping",
        PROJECT_ROOT / "results/15_stage15a_inputs",
    ]
    seen: set[Path] = set()
    rows: list[dict[str, Any]] = []
    eligible: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.sorted.bam")):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            text = str(resolved).lower()
            reason = next((token for token in EXCLUDE_BAM_PATTERNS if token in text), None)
            contains_sample = SAMPLE_ID.lower() in text
            excluded = reason is not None or not contains_sample
            if not excluded:
                eligible.append(resolved)
            rows.append({
                "path": str(resolved),
                "bytes": resolved.stat().st_size if resolved.is_file() else 0,
                "excluded": str(excluded).lower(),
                "exclusion_reason": reason or ("sample_id_absent" if not contains_sample else "."),
                "selection_status": "ELIGIBLE" if not excluded else "EXCLUDED",
            })

    selected: Path | None = None
    selection = "NONE"
    if len(eligible) == 1:
        selected = eligible[0]
        selection = "AUTO_UNIQUE"
    elif len(eligible) > 1:
        strong = [
            path for path in eligible
            if any(token in str(path).lower() for token in ("full", "5312696", "fullscale", "full_scale"))
        ]
        if len(strong) == 1:
            selected = strong[0]
            selection = "AUTO_UNIQUE_STRONG_NAME"
        else:
            selection = "AMBIGUOUS"
    return rows, selected, selection


def locate_bai(bam: Path, explicit_bai: Path | None) -> Path:
    candidates: list[Path] = []
    if explicit_bai is not None:
        candidates.append(explicit_bai)
    candidates.extend([
        Path(str(bam) + ".bai"),
        bam.with_suffix(".bam.bai"),
        bam.with_suffix(".bai"),
        Path(str(bam) + ".csi"),
    ])
    existing: list[Path] = []
    seen: set[Path] = set()
    for path in candidates:
        resolved = path.resolve() if path.exists() else path
        if resolved in seen:
            continue
        seen.add(resolved)
        if path.is_file() and path.stat().st_size > 0:
            existing.append(path.resolve())
    if len(existing) != 1:
        raise PreflightError(f"expected exactly one BAM index for {bam}, found {len(existing)}: {existing}")
    return existing[0]


def mapping_provenance(bam: Path, explicit: Path | None) -> tuple[list[Path], str]:
    if explicit is not None:
        ensure_file(explicit)
        return [explicit.resolve()], "PASS_EXPLICIT"

    candidates: list[Path] = []
    search_roots = [bam.parent, bam.parent.parent]
    patterns = (
        "*mapper_command*.sh",
        "*mapping*manifest*.tsv",
        "*mapping*.qc.tsv",
        "*mapping*q[cC]*.tsv",
        "*run_manifest*.tsv",
        "*artifact_manifest*.tsv",
    )
    seen: set[Path] = set()
    for root in search_roots:
        if not root.is_dir():
            continue
        for pattern in patterns:
            for path in sorted(root.glob(pattern)):
                if path.is_file() and path.stat().st_size > 0:
                    resolved = path.resolve()
                    if resolved not in seen:
                        candidates.append(resolved)
                        seen.add(resolved)
    has_command = any("mapper_command" in path.name for path in candidates)
    has_manifest_or_qc = any(
        ("manifest" in path.name or ".qc." in path.name or path.name.endswith("qc.tsv"))
        for path in candidates
    )
    status = "PASS" if has_command and has_manifest_or_qc else "REVIEW_REQUIRED"
    return candidates, status


def extract_bam_ids(bam: Path, destination: Path, threads: int) -> int:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as output:
        p1 = subprocess.Popen(
            ["samtools", "view", "-@", str(threads), str(bam)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert p1.stdout is not None
        p2 = subprocess.Popen(
            ["cut", "-f1"],
            stdin=p1.stdout,
            stdout=output,
            stderr=subprocess.PIPE,
        )
        p1.stdout.close()
        p2_stderr = p2.communicate()[1] or b""
        p1_stderr = p1.communicate()[1] or b""
        if p1.returncode != 0 or p2.returncode != 0:
            raise PreflightError(
                "BAM ID extraction failed: "
                f"samtools={p1.returncode} cut={p2.returncode}\n"
                f"samtools stderr={p1_stderr.decode(errors='replace')[-2000:]}\n"
                f"cut stderr={p2_stderr.decode(errors='replace')[-2000:]}"
            )
    return count_lines(destination)


def validate_fastq(path: Path, work_root: Path, write_ids: bool, sort_buffer: str) -> FastqStats:
    ensure_file(path)
    observed_bytes = path.stat().st_size
    md5, sha = md5_sha256_file(path)
    if observed_bytes != EXPECTED_FASTQ_BYTES:
        raise PreflightError(f"full FASTQ byte mismatch: {observed_bytes} != {EXPECTED_FASTQ_BYTES}")
    if md5 != EXPECTED_FASTQ_MD5:
        raise PreflightError(f"full FASTQ MD5 mismatch: {md5} != {EXPECTED_FASTQ_MD5}")

    unsorted_ids = work_root / "fastq_ids.unsorted.txt" if write_ids else None
    id_handle = unsorted_ids.open("w", encoding="utf-8", newline="") if unsorted_ids else None
    reads = 0
    bases = 0
    try:
        with gzip.open(path, "rt", encoding="ascii", errors="strict", newline="") as handle:
            while True:
                header = handle.readline()
                if not header:
                    break
                sequence = handle.readline()
                plus = handle.readline()
                quality = handle.readline()
                if not sequence or not plus or not quality:
                    raise PreflightError(f"truncated FASTQ record at read {reads + 1}")
                if not header.startswith("@"):
                    raise PreflightError(f"invalid FASTQ header at read {reads + 1}")
                if not plus.startswith("+"):
                    raise PreflightError(f"invalid FASTQ plus line at read {reads + 1}")
                seq = sequence.rstrip("\r\n")
                qual = quality.rstrip("\r\n")
                if len(seq) != len(qual):
                    raise PreflightError(
                        f"FASTQ sequence/quality length mismatch at read {reads + 1}: {len(seq)} != {len(qual)}"
                    )
                read_id = header[1:].strip().split()[0]
                if not read_id:
                    raise PreflightError(f"empty FASTQ read ID at read {reads + 1}")
                if id_handle is not None:
                    id_handle.write(read_id + "\n")
                reads += 1
                bases += len(seq)
    finally:
        if id_handle is not None:
            id_handle.close()

    if reads != EXPECTED_READS:
        raise PreflightError(f"full FASTQ read mismatch: {reads} != {EXPECTED_READS}")
    if bases != EXPECTED_BASES:
        raise PreflightError(f"full FASTQ base mismatch: {bases} != {EXPECTED_BASES}")

    unique_ids: int | None = None
    duplicate_ids: int | None = None
    sorted_ids: Path | None = None
    if unsorted_ids is not None:
        sorted_ids = work_root / "fastq_ids.sorted.unique.txt"
        unique_ids = external_sort_unique(
            unsorted_ids,
            sorted_ids,
            work_root / "sort_fastq",
            sort_buffer,
        )
        duplicate_ids = reads - unique_ids
        unsorted_ids.unlink()
        shutil.rmtree(work_root / "sort_fastq", ignore_errors=True)
        if duplicate_ids != 0:
            raise PreflightError(f"duplicate FASTQ IDs detected: {duplicate_ids}")

    return FastqStats(
        path=path.resolve(),
        bytes=observed_bytes,
        md5=md5,
        sha256=sha,
        reads=reads,
        bases=bases,
        unique_ids=unique_ids,
        duplicate_ids=duplicate_ids,
        sorted_ids=sorted_ids,
    )


def parse_sort_order(header: str) -> str:
    for line in header.splitlines():
        if line.startswith("@HD"):
            for field in line.split("\t")[1:]:
                if field.startswith("SO:"):
                    return field[3:]
    return "."


def validate_bam(
    bam: Path,
    bai: Path,
    fastq: FastqStats,
    work_root: Path,
    threads: int,
    sort_buffer: str,
    explicit_provenance: Path | None,
) -> BamBinding:
    ensure_file(bam)
    ensure_file(bai)
    run_text(["samtools", "quickcheck", "-v", str(bam)])
    header = run_text(["samtools", "view", "-H", str(bam)]).stdout
    sort_order = parse_sort_order(header)
    if sort_order != "coordinate":
        raise PreflightError(f"BAM sort order is not coordinate: {sort_order}")

    alignment_records = int(run_text(["samtools", "view", "-c", str(bam)]).stdout.strip())
    unmapped_records = int(run_text(["samtools", "view", "-c", "-f", "4", str(bam)]).stdout.strip())

    unsorted_ids = work_root / "bam_ids.unsorted.txt"
    extract_bam_ids(bam, unsorted_ids, threads)
    sorted_ids = work_root / "bam_ids.sorted.unique.txt"
    unique_ids = external_sort_unique(
        unsorted_ids,
        sorted_ids,
        work_root / "sort_bam",
        sort_buffer,
    )
    unsorted_ids.unlink()
    shutil.rmtree(work_root / "sort_bam", ignore_errors=True)

    if unique_ids != EXPECTED_READS:
        raise PreflightError(f"BAM unique read count mismatch: {unique_ids} != {EXPECTED_READS}")
    if fastq.sorted_ids is None:
        raise PreflightError("internal error: FASTQ sorted IDs were not produced for BAM parity")
    cmp_proc = subprocess.run(["cmp", "-s", str(fastq.sorted_ids), str(sorted_ids)])
    exact_parity = cmp_proc.returncode == 0
    if not exact_parity:
        diff = run_text(
            ["bash", "-lc", f"LC_ALL=C comm -3 {shlex_quote(str(fastq.sorted_ids))} {shlex_quote(str(sorted_ids))} | head -20"],
            check=False,
        )
        raise PreflightError(
            "FASTQ/BAM exact read-ID parity failed. First differences:\n" + diff.stdout
        )

    provenance_paths, provenance_status = mapping_provenance(bam, explicit_provenance)
    bam_sha = sha256_file(bam)
    bai_sha = sha256_file(bai)
    return BamBinding(
        path=bam.resolve(),
        bai=bai.resolve(),
        sha256=bam_sha,
        bai_sha256=bai_sha,
        bytes=bam.stat().st_size,
        bai_bytes=bai.stat().st_size,
        alignment_records=alignment_records,
        unique_read_ids=unique_ids,
        unmapped_records=unmapped_records,
        sort_order=sort_order,
        exact_fastq_id_parity=exact_parity,
        provenance_paths=provenance_paths,
        provenance_status=provenance_status,
    )


def shlex_quote(text: str) -> str:
    import shlex
    return shlex.quote(text)


def write_execution_contract(
    path: Path,
    stage15b: dict[str, Any],
    storage: dict[str, Any],
    fastq: FastqStats,
    bam: BamBinding | None,
    bam_selection: str,
    runner_build_authorized: bool,
    next_gate: str,
) -> None:
    rows = [
        {"field": "contract_version", "value": VERSION, "status": "FIXED"},
        {"field": "planned_run_id", "value": PLANNED_RUN_ID, "status": "PROVISIONAL"},
        {"field": "sample_id", "value": SAMPLE_ID, "status": "FIXED"},
        {"field": "input_contract", "value": "mapping-complete coordinate-sorted BAM+BAI+mapping provenance+associated raw-read FASTQ", "status": "FIXED"},
        {"field": "full_fastq", "value": str(fastq.path), "status": "BOUND_PASS"},
        {"field": "full_fastq_reads", "value": str(fastq.reads), "status": "PASS"},
        {"field": "full_fastq_bases", "value": str(fastq.bases), "status": "PASS"},
        {"field": "full_bam", "value": str(bam.path) if bam else ".", "status": "BOUND_PASS" if bam else bam_selection},
        {"field": "full_bai", "value": str(bam.bai) if bam else ".", "status": "BOUND_PASS" if bam else bam_selection},
        {"field": "mapping_time_in_bam_to_final_timer", "value": "false", "status": "FIXED"},
        {"field": "read_coherent_shards", "value": str(PLANNED_SHARDS), "status": "PROVISIONAL_FROM_500K"},
        {"field": "caller_workers_per_shard", "value": str(PLANNED_CALLER_WORKERS_PER_SHARD), "status": "PROVISIONAL_FROM_500K"},
        {"field": "validator", "value": str(BOUNDED_VALIDATOR), "status": "PROVISIONAL_EQUIVALENCE_PASS"},
        {"field": "validator_workers", "value": str(PLANNED_VALIDATOR_WORKERS), "status": "PROVISIONAL_MEMORY_PASS"},
        {"field": "validator_sort_buffer", "value": PLANNED_SORT_BUFFER, "status": "PROVISIONAL_MEMORY_PASS"},
        {"field": "validator_equivalence_scope", "value": "STAGE15A_READ_COHERENT_SHARDS_CORE_V042_NO_LOCUS_AGGREGATION", "status": "FIXED"},
        {"field": "locus_aggregation", "value": "NOT_RUN", "status": "OUT_OF_CORE_SCOPE"},
        {"field": "projected_full_bam_to_final_minutes", "value": f"{stage15b['projected_full_bam_to_final_minutes']:.9f}", "status": "PASS_STRICT_PROJECTION_ONLY"},
        {"field": "runtime_gate_strict_minutes", "value": "60.0", "status": "FIXED"},
        {"field": "runtime_gate_thesis_tolerance_minutes", "value": "62.0", "status": "FIXED"},
        {"field": "projected_validator_memory_fraction", "value": f"{stage15b['projected_memory_fraction']:.6f}", "status": "PASS"},
        {"field": "current_free_bytes", "value": str(storage["filesystem_free_bytes"]), "status": storage["hard_storage_status"]},
        {"field": "projected_temp_and_output_bytes", "value": str(PROJECTED_FULL_TEMP_AND_OUTPUT_BYTES), "status": "PROJECTION"},
        {"field": "atomic_publication_required", "value": "true", "status": "FIXED"},
        {"field": "checkpoint_hash_verification_required", "value": "true", "status": "FIXED"},
        {"field": "corrupt_checkpoint_rejection_required", "value": "true", "status": "FIXED"},
        {"field": "selective_resume_required", "value": "true", "status": "FIXED"},
        {"field": "second_resume_noop_required", "value": "true", "status": "FIXED"},
        {"field": "clean_vs_resume_exact_parity_required", "value": "true", "status": "FIXED"},
        {"field": "runner_build_authorized", "value": str(runner_build_authorized).lower(), "status": "PASS" if runner_build_authorized else "BLOCKED"},
        {"field": "full_empirical_run_authorized", "value": "false", "status": "NOT_BY_PREFLIGHT"},
        {"field": "full_5_31m_run_started", "value": "false", "status": "PASS"},
        {"field": "active_pipeline_modified", "value": "false", "status": "PASS"},
        {"field": "ssot_modified", "value": "false", "status": "PASS"},
        {"field": "core_schema_modified", "value": "false", "status": "PASS"},
        {"field": "next_gate", "value": next_gate, "status": "OPEN"},
    ]
    atomic_write_tsv(path, ["field", "value", "status"], rows)


def write_doc(
    path: Path,
    status: str,
    fastq: FastqStats,
    bam: BamBinding | None,
    storage: dict[str, Any],
    stage15b: dict[str, Any],
    next_gate: str,
) -> None:
    bam_text = str(bam.path) if bam else "NOT_BOUND"
    provenance = bam.provenance_status if bam else "NOT_EVALUATED"
    text = f"""# RNA-TR-Scout Stage 15C\n## Full-scale input binding and provisional-runner preflight v0.1.0\n\n- Created: {utc_now()}\n- Status: **{status}**\n- Full 5.31M run started: **false**\n- Active pipeline modified: **false**\n- SSOT modified: **false**\n- Core schema modified: **false**\n\n## Purpose\n\nBind the exact 5,312,696-read input contract and close the resource/guard preflight before building the provisional full-scale BAM-to-final runner. This stage never starts the full run.\n\n## Bound raw-read sequence store\n\n- FASTQ: `{fastq.path}`\n- bytes: `{fastq.bytes}`\n- MD5: `{fastq.md5}`\n- SHA-256: `{fastq.sha256}`\n- reads: `{fastq.reads}`\n- bases: `{fastq.bases}`\n\n## Mapping-complete BAM binding\n\n- BAM: `{bam_text}`\n- mapping provenance status: `{provenance}`\n\nThe BAM-input contract requires a mapping-complete coordinate-sorted BAM, its BAI/CSI, mapping provenance, and the associated raw-read FASTQ. Mapping time remains separate from the BAM-to-final performance timer.\n\n## Resource contract\n\n- Intel SSD free bytes: `{storage['filesystem_free_bytes']}`\n- projected peak temporary+output bytes: `{PROJECTED_FULL_TEMP_AND_OUTPUT_BYTES}`\n- projected post-peak reserve bytes: `{storage['projected_post_peak_reserve_bytes']}`\n- storage hard gate: `{storage['hard_storage_status']}`\n- storage operational recommendation: `{storage['operational_storage_status']}`\n- Stage15B projected validator memory fraction: `{stage15b['projected_memory_fraction']:.6f}`\n- Stage15B projected BAM-to-final runtime: `{stage15b['projected_full_bam_to_final_minutes']:.6f} min`\n\n## Provisional execution architecture\n\n```text\n12 read-coherent shards\ncaller workers per shard: 2\nmemory-bounded validator workers: 3\nexternal-sort buffer: 512M\ncore schema: v0.4.2 unchanged\nlocus aggregation: NOT_RUN\natomic publication required\n```\n\n## Restart contract retained for the later full-scale test\n\n```text\nintentional stop\ncheckpoint SHA verification\ncorrupt-checkpoint rejection\nreuse completed work\nresume missing work only\nclean/resume exact final-package parity\nsecond resume is a no-op\n```\n\n## Next gate\n\n`{next_gate}`\n"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".part")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def source_snapshot(paths: list[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        if path.is_file() and path.stat().st_size > 0:
            rows.append({
                "path": str(path),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            })
    return rows


def pack_bundle(bundle: Path, roots: list[tuple[Path, str]]) -> str:
    if bundle.exists() or bundle.with_suffix(bundle.suffix + ".sha256").exists():
        raise PreflightError(f"refusing to overwrite existing bundle: {bundle}")
    with tempfile.TemporaryDirectory(prefix="rnatr_stage15c_bundle_") as tmp_text:
        tmp = Path(tmp_text)
        for source, arcroot in roots:
            if not source.exists():
                continue
            destination = tmp / arcroot
            if source.is_dir():
                shutil.copytree(source, destination, symlinks=False)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
        manifest_rows: list[dict[str, Any]] = []
        for path in sorted(p for p in tmp.rglob("*") if p.is_file()):
            relative = path.relative_to(tmp)
            manifest_rows.append({
                "artifact": relative.as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            })
        atomic_write_tsv(tmp / "artifact_manifest.tsv", ["artifact", "bytes", "sha256"], manifest_rows)
        with tarfile.open(bundle, "w:gz", format=tarfile.PAX_FORMAT) as tar:
            for path in sorted(tmp.iterdir()):
                tar.add(path, arcname=path.name, recursive=True)
    digest = sha256_file(bundle)
    bundle.with_suffix(bundle.suffix + ".sha256").write_text(
        f"{digest}  {bundle.name}\n", encoding="utf-8"
    )
    return digest


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only full-scale input binding and provisional-runner preflight; never starts the 5.31M run."
    )
    parser.add_argument("--fastq", type=Path, default=FULL_FASTQ_DEFAULT)
    parser.add_argument("--bam", type=Path, default=None)
    parser.add_argument("--bai", type=Path, default=None)
    parser.add_argument("--mapping-provenance", type=Path, default=None)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--sort-buffer", default=PLANNED_SORT_BUFFER)
    args = parser.parse_args()

    if args.threads < 1:
        raise SystemExit("--threads must be >=1")
    for executable in ("samtools", "sort", "cut", "cmp", "wc"):
        if shutil.which(executable) is None:
            raise SystemExit(f"required executable unavailable: {executable}")

    if QC_ROOT.exists() or META_ROOT.exists():
        raise SystemExit(
            "versioned Stage15C preflight output already exists; preserve provenance and do not overwrite:\n"
            f"{QC_ROOT}\n{META_ROOT}"
        )

    source_path = Path(__file__).resolve()
    started = time.perf_counter()
    work_root = PROJECT_ROOT / "tmp/stage15c_fullscale_input_binding_v0.1.0"
    if work_root.exists():
        raise SystemExit(f"stale work root exists; inspect before removal: {work_root}")
    work_root.mkdir(parents=True)
    QC_ROOT.mkdir(parents=True)
    META_ROOT.mkdir(parents=True)

    bundle = SUCCESS_BUNDLE
    try:
        install_status = install_exact(source_path, SCRIPT_INSTALL, 0o755)
        guard_rows = verify_hash_guards()
        atomic_write_tsv(
            QC_ROOT / "preflight_hash_guards.tsv",
            ["guard_class", "path", "expected_sha256", "observed_sha256", "status"],
            guard_rows,
        )
        guard_before = {Path(row["path"]): row["observed_sha256"] for row in guard_rows}

        stage15b = verify_stage15b_contract()
        storage = storage_audit()
        atomic_write_metrics(
            QC_ROOT / "storage_readiness_current.tsv",
            [(key, value) for key, value in storage.items()],
        )

        discovery_rows, selected_bam, selection_status = discover_bams(args.bam)
        atomic_write_tsv(
            QC_ROOT / "full_bam_discovery.tsv",
            ["path", "bytes", "excluded", "exclusion_reason", "selection_status"],
            discovery_rows or [{
                "path": ".", "bytes": 0, "excluded": "false",
                "exclusion_reason": "no_bam_found", "selection_status": "NONE",
            }],
        )

        need_fastq_ids = selected_bam is not None
        fastq_started = time.perf_counter()
        fastq = validate_fastq(
            args.fastq.resolve(),
            work_root,
            need_fastq_ids,
            args.sort_buffer,
        )
        fastq_seconds = time.perf_counter() - fastq_started
        atomic_write_metrics(
            QC_ROOT / "full_fastq_binding.qc.tsv",
            [
                ("path", fastq.path),
                ("bytes", fastq.bytes),
                ("md5", fastq.md5),
                ("sha256", fastq.sha256),
                ("reads", fastq.reads),
                ("bases", fastq.bases),
                ("unique_ids", fastq.unique_ids if fastq.unique_ids is not None else "NOT_RUN_NO_BAM_BOUND"),
                ("duplicate_ids", fastq.duplicate_ids if fastq.duplicate_ids is not None else "NOT_RUN_NO_BAM_BOUND"),
                ("elapsed_seconds", f"{fastq_seconds:.9f}"),
                ("write_to_t9", "false"),
                ("audit_status", "PASS"),
            ],
        )

        bam_binding: BamBinding | None = None
        if selected_bam is not None:
            bai = locate_bai(selected_bam, args.bai)
            bam_started = time.perf_counter()
            bam_binding = validate_bam(
                selected_bam,
                bai,
                fastq,
                work_root,
                args.threads,
                args.sort_buffer,
                args.mapping_provenance,
            )
            bam_seconds = time.perf_counter() - bam_started
            atomic_write_metrics(
                QC_ROOT / "full_bam_binding.qc.tsv",
                [
                    ("path", bam_binding.path),
                    ("bytes", bam_binding.bytes),
                    ("sha256", bam_binding.sha256),
                    ("bai", bam_binding.bai),
                    ("bai_bytes", bam_binding.bai_bytes),
                    ("bai_sha256", bam_binding.bai_sha256),
                    ("alignment_records", bam_binding.alignment_records),
                    ("unique_read_ids", bam_binding.unique_read_ids),
                    ("unmapped_records", bam_binding.unmapped_records),
                    ("sort_order", bam_binding.sort_order),
                    ("exact_fastq_id_parity", str(bam_binding.exact_fastq_id_parity).lower()),
                    ("mapping_provenance_status", bam_binding.provenance_status),
                    ("elapsed_seconds", f"{bam_seconds:.9f}"),
                    ("audit_status", "PASS" if bam_binding.provenance_status == "PASS" or bam_binding.provenance_status == "PASS_EXPLICIT" else "REVIEW"),
                ],
            )
            provenance_rows = [
                {
                    "path": str(path),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
                for path in bam_binding.provenance_paths
            ]
            atomic_write_tsv(
                QC_ROOT / "mapping_provenance_inventory.tsv",
                ["path", "bytes", "sha256"],
                provenance_rows or [{"path": ".", "bytes": 0, "sha256": "."}],
            )

        if selection_status == "AMBIGUOUS":
            status = "REVIEW_AMBIGUOUS_FULL_BAM"
            next_gate = "RERUN_STAGE15C_WITH_EXPLICIT_FULL_BAM_AND_MAPPING_PROVENANCE"
            runner_build_authorized = False
        elif selected_bam is None:
            status = "BLOCKED_FULL_MAPPING_REQUIRED"
            next_gate = "BUILD_OR_BIND_MAPPING_COMPLETE_FULL_5312696_READ_BAM_SEPARATE_FROM_BAM_TO_FINAL_TIMER"
            runner_build_authorized = False
        elif bam_binding is None:
            status = "BLOCKED_FULL_BAM_BINDING_FAILED"
            next_gate = "REPAIR_FULL_BAM_INPUT_BINDING"
            runner_build_authorized = False
        elif bam_binding.provenance_status not in {"PASS", "PASS_EXPLICIT"}:
            status = "REVIEW_MAPPING_PROVENANCE_REQUIRED"
            next_gate = "BIND_MAPPING_COMMAND_AND_MAPPING_RUN_MANIFEST_THEN_BUILD_PROVISIONAL_RUNNER"
            runner_build_authorized = False
        else:
            status = "PASS_READY_TO_BUILD_PROVISIONAL_FULLSCALE_RUNNER"
            next_gate = "BUILD_PROVISIONAL_FULLSCALE_RUNNER_WITH_STAGE15B_VALIDATOR_RESTART_AND_ATOMIC_PUBLICATION"
            runner_build_authorized = True

        write_execution_contract(
            META_ROOT / "fullscale_execution_contract_v0.1.0.tsv",
            stage15b,
            storage,
            fastq,
            bam_binding,
            selection_status,
            runner_build_authorized,
            next_gate,
        )
        write_doc(
            DOC_PATH,
            status,
            fastq,
            bam_binding,
            storage,
            stage15b,
            next_gate,
        )

        snapshot_paths = [
            SCRIPT_INSTALL,
            DOC_PATH,
            STAGE15B_QC,
            STAGE15B_PROJECTION,
            STAGE15B_AUDIT,
            READINESS_QC,
            RESOURCE_PROJECTION,
            SCALING500_QC,
            BOUNDED_VALIDATOR,
            SCALING500_RUNNER,
        ]
        snapshot_rows = source_snapshot(snapshot_paths)
        # Reuse hashes already computed during binding so the 9-GB FASTQ and
        # potentially large BAM are not read a second time solely for this manifest.
        snapshot_rows.append({
            "path": str(fastq.path),
            "bytes": fastq.bytes,
            "sha256": fastq.sha256,
        })
        if bam_binding:
            snapshot_rows.extend([
                {
                    "path": str(bam_binding.path),
                    "bytes": bam_binding.bytes,
                    "sha256": bam_binding.sha256,
                },
                {
                    "path": str(bam_binding.bai),
                    "bytes": bam_binding.bai_bytes,
                    "sha256": bam_binding.bai_sha256,
                },
            ])
            snapshot_rows.extend(source_snapshot(bam_binding.provenance_paths))
        atomic_write_tsv(
            META_ROOT / "bound_input_and_source_manifest.tsv",
            ["path", "bytes", "sha256"],
            snapshot_rows,
        )

        # Verify guarded sources were not changed by this stage.
        after_rows: list[dict[str, Any]] = []
        for path, before in guard_before.items():
            after = sha256_file(path)
            state = "PASS" if after == before else "FAIL"
            after_rows.append({
                "path": str(path),
                "before_sha256": before,
                "after_sha256": after,
                "status": state,
            })
            if state != "PASS":
                raise PreflightError(f"guarded source changed during preflight: {path}")
        atomic_write_tsv(
            QC_ROOT / "postflight_unchanged_guards.tsv",
            ["path", "before_sha256", "after_sha256", "status"],
            after_rows,
        )

        elapsed = time.perf_counter() - started
        atomic_write_metrics(
            QC_ROOT / "stage15c_fullscale_preflight.qc.tsv",
            [
                ("stage_version", VERSION),
                ("planned_run_id", PLANNED_RUN_ID),
                ("status", status),
                ("full_fastq_binding", "PASS"),
                ("full_bam_selection_status", selection_status),
                ("full_bam_bound", str(bam_binding is not None).lower()),
                ("mapping_provenance_status", bam_binding.provenance_status if bam_binding else "NOT_EVALUATED"),
                ("fastq_bam_exact_read_id_parity", str(bam_binding.exact_fastq_id_parity).lower() if bam_binding else "NOT_RUN"),
                ("stage15b_validator_equivalence", "PASS"),
                ("memory_readiness_status", "PASS"),
                ("storage_readiness_status", storage["hard_storage_status"]),
                ("operational_storage_status", storage["operational_storage_status"]),
                ("runner_build_authorized", str(runner_build_authorized).lower()),
                ("full_empirical_run_authorized", "false"),
                ("active_pipeline_modified", "false"),
                ("ssot_modified", "false"),
                ("core_schema_modified", "false"),
                ("full_5_31m_run_started", "false"),
                ("script_installation", install_status),
                ("script_sha256", sha256_file(SCRIPT_INSTALL)),
                ("elapsed_seconds", f"{elapsed:.9f}"),
                ("audit_status", "PASS"),
                ("next_gate", next_gate),
            ],
        )

        shutil.rmtree(work_root)
        bundle_sha = pack_bundle(
            bundle,
            [
                (QC_ROOT, "qc"),
                (META_ROOT, "metadata"),
                (DOC_PATH, "docs/" + DOC_PATH.name),
                (SCRIPT_INSTALL, "sources/" + SCRIPT_INSTALL.name),
            ],
        )

        print("===== RNA-TR-Scout Stage 15C full-scale preflight =====")
        print(f"stage status\t{status}")
        print(f"full FASTQ\tPASS\t{fastq.path}")
        print(f"full FASTQ reads\t{fastq.reads}")
        print(f"full BAM selection\t{selection_status}")
        print(f"full BAM bound\t{str(bam_binding is not None).lower()}")
        if bam_binding:
            print(f"full BAM\t{bam_binding.path}")
            print(f"FASTQ/BAM read-ID parity\t{str(bam_binding.exact_fastq_id_parity).lower()}")
            print(f"mapping provenance\t{bam_binding.provenance_status}")
        print(f"Intel SSD free bytes\t{storage['filesystem_free_bytes']}")
        print(f"storage readiness\t{storage['hard_storage_status']}")
        print(f"memory readiness\tPASS")
        print(f"runner build authorized\t{str(runner_build_authorized).lower()}")
        print("full empirical run authorized\tfalse")
        print("full 5.31M started\tfalse")
        print(f"next gate\t{next_gate}")
        print(f"OUTPUT_BUNDLE\t{bundle}")
        print(f"OUTPUT_BUNDLE_SHA256\t{bundle_sha}")
        return 0

    except Exception as exc:
        elapsed = time.perf_counter() - started
        QC_ROOT.mkdir(parents=True, exist_ok=True)
        atomic_write_metrics(
            QC_ROOT / "stage15c_fullscale_preflight.failure.qc.tsv",
            [
                ("stage_version", VERSION),
                ("failure_type", type(exc).__name__),
                ("failure_message", str(exc)),
                ("elapsed_seconds", f"{elapsed:.9f}"),
                ("active_pipeline_modified", "false"),
                ("ssot_modified", "false"),
                ("core_schema_modified", "false"),
                ("full_5_31m_run_started", "false"),
                ("audit_status", "FAIL"),
            ],
        )
        (QC_ROOT / "failure_traceback.log").write_text(traceback.format_exc(), encoding="utf-8")
        if work_root.exists():
            shutil.rmtree(work_root, ignore_errors=True)
        bundle = FAILURE_BUNDLE
        try:
            bundle_sha = pack_bundle(
                bundle,
                [
                    (QC_ROOT, "qc"),
                    (META_ROOT, "metadata"),
                    (source_path, "sources/" + source_path.name),
                ],
            )
            print(f"OUTPUT_FAILURE_BUNDLE\t{bundle}", file=sys.stderr)
            print(f"OUTPUT_FAILURE_BUNDLE_SHA256\t{bundle_sha}", file=sys.stderr)
        except Exception as pack_exc:
            print(f"failure bundle packaging also failed: {pack_exc}", file=sys.stderr)
        print(f"STAGE15C_PREFLIGHT_FAIL\t{type(exc).__name__}\t{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
