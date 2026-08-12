#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import importlib.util
import json
import os
import shutil
import stat
import sys
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Any, Iterable

BUILDER_VERSION = "rnatr_stage15c_build_execution_unlocked_full_runner_v0.1.4"
RUNNER_VERSION = "rnatr_stage15c_full5312696_bam_to_final_v0.1.4"
UNLOCK_SCHEMA = "rnatr.full_runner_execution_unlock.v1"
PROJECT_ROOT = Path("/mnt/intelssd/rnatr_project")
DOWNLOADS = Path.home() / "Downloads"

ANALYSIS_RUN_ID = "ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1"
MAPPING_RUN_ID = "ENCSR307SHM_full5312696_mm2splice_v1"
EXPECTED_READS = 5_312_696
EXPECTED_BAM_SHA256 = "95fc869291dd471112e31e10f81571b918621d9008580b1d09ddd3a6fefbfb85"
EXPECTED_FASTQ_SHA256 = "adb26ca39b2c93e9d5f289cdc055ebcc41ebcb23c13c2b91d6134aadcc1a6256"
SHARDS = 144
CONCURRENCY = 12
CALLER_WORKERS_PER_SHARD = 2
VALIDATOR_WORKERS = 3
SORT_BUFFER = "512M"
POST_11B_HARD_MAX = 164_204

LOCKED_RUNNER_PROJECT = PROJECT_ROOT / "scripts/rnatr_stage15c_run_full5312696_bam_to_final_v0.1.3.py"
LOCKED_RUNNER_DOWNLOAD = DOWNLOADS / "rnatr_stage15c_run_full5312696_bam_to_final_v013.py"
LOCKED_RUNNER_SHA256 = "70d82b1f8cee9c7941a796c2f059ccf88365ea0df0981f10973f18a930c3ea65"
LOCKED_RUNNER_LOCK = (
    PROJECT_ROOT / "metadata/stage15c/contract_locked_full_runner_v0.1.3"
    / "rnatr_stage15c_full_runner_lock_contract_v0.1.3.json"
)
LOCKED_RUNNER_LOCK_SHA256 = "5b37ebd7b7ad9cdeda544c39777248d44e3a310765313689233eeb32ffa54d5b"

LOCKED_PREFLIGHT_BUNDLE = DOWNLOADS / "rnatr_stage15c_fullscale_runner_preflight_v0.1.3.tar.gz"
LOCKED_PREFLIGHT_BUNDLE_SHA256 = "6534d95e9b8e2907103b6d79957a9e29ced7a4b09d355a0b9af93f85bb21ff8c"
LOCKED_PREFLIGHT_SIDECAR = Path(str(LOCKED_PREFLIGHT_BUNDLE) + ".sha256")
LOCKED_PREFLIGHT_SIDECAR_SHA256 = "b5f8d132cfb88b00c7c5b79d4520aa813ce9f55b04333dbc75c01cbbb5294f44"
LOCKED_PREFLIGHT_ROOT = (
    PROJECT_ROOT / "qc/15_stage15c_fullscale_runner_preflight" / ANALYSIS_RUN_ID / "v0.1.3"
)
LOCKED_PREFLIGHT_QC = LOCKED_PREFLIGHT_ROOT / "stage15c_fullscale_runner_preflight.qc.tsv"
LOCKED_PREFLIGHT_QC_SHA256 = "719bc1e9a2b95d2096c46e5382324ef4d5305fa9c44851c811d6a86bed278180"
LOCKED_PREFLIGHT_RESOURCE = LOCKED_PREFLIGHT_ROOT / "resource_model.tsv"
LOCKED_PREFLIGHT_RESOURCE_SHA256 = "87ec413bd9c5efd9c18db29ac48b65a6734d8233817829e4d3386201621b054f"
LOCKED_PREFLIGHT_SOURCE_GUARDS = LOCKED_PREFLIGHT_ROOT / "source_and_contract_guards.tsv"
LOCKED_PREFLIGHT_SOURCE_GUARDS_SHA256 = "76aa6319336ce300cbe8c14d2ad1aa2fa5196309726e051380d123f4c6d37120"
LOCKED_PREFLIGHT_MAPPING_INTEGRITY = LOCKED_PREFLIGHT_ROOT / "mapping_artifact_integrity.tsv"
LOCKED_PREFLIGHT_MAPPING_INTEGRITY_SHA256 = "72796145d4a7e4a7318aa708726ece0fddbb3410d6b2d3df2f49591a00c1d15c"
LOCKED_PREFLIGHT_ARTIFACT_MANIFEST_SHA256 = "98620eda9e3d1d09e9ca564f641944406f288de9a8fda50c21253947f47f23c5"
LOCKED_PREFLIGHT_CONTRACT_DOC_SHA256 = "ea910dbc1f417c3c611363d6a9f293ac8f4a24314678d91d6953fd381fc9e24b"

BUNDLE_ROOT = "rnatr_stage15c_fullscale_runner_preflight_v0.1.3"
BUNDLE_MEMBER_HASHES = {
    f"{BUNDLE_ROOT}/v0.1.3/artifact_manifest.tsv": LOCKED_PREFLIGHT_ARTIFACT_MANIFEST_SHA256,
    f"{BUNDLE_ROOT}/v0.1.3/mapping_artifact_integrity.tsv": LOCKED_PREFLIGHT_MAPPING_INTEGRITY_SHA256,
    f"{BUNDLE_ROOT}/v0.1.3/resource_model.tsv": LOCKED_PREFLIGHT_RESOURCE_SHA256,
    f"{BUNDLE_ROOT}/v0.1.3/source_and_contract_guards.tsv": LOCKED_PREFLIGHT_SOURCE_GUARDS_SHA256,
    f"{BUNDLE_ROOT}/v0.1.3/stage15c_fullscale_runner_preflight.qc.tsv": LOCKED_PREFLIGHT_QC_SHA256,
    f"{BUNDLE_ROOT}/RNA_TR_Scout_fullscale_runner_execution_contract_v0.1.3.md": LOCKED_PREFLIGHT_CONTRACT_DOC_SHA256,
    f"{BUNDLE_ROOT}/rnatr_stage15c_run_full5312696_bam_to_final_v0.1.3.py": LOCKED_RUNNER_SHA256,
}

ARCH144_CONTRACT = (
    PROJECT_ROOT / "metadata/stage15c/144shard_execution_architecture_v0.1.1"
    / "fullscale_144shard_execution_contract_v0.1.1.tsv"
)
ARCH144_CONTRACT_SHA256 = "aa933d41e75c365a58ba414a85f0415fb100bf29e9ab8974300520eb01738eec"
ARCH144_QC = (
    PROJECT_ROOT / "qc/15_stage15c_execution_architecture"
    / "ENCSR307SHM_stage15a500k_seed20260809_mm2splice_v1"
    / "v0.1.1_144shard_500k/stage15c_144shard_execution_architecture.qc.tsv"
)
ARCH144_QC_SHA256 = "43226464ef19572de3fcccef1a6e7fd169e22e20e8fa3b724f9d2f1080ce0437"
ARCH144_RESOURCE = (
    PROJECT_ROOT / "qc/15_stage15c_execution_architecture"
    / "ENCSR307SHM_stage15a500k_seed20260809_mm2splice_v1"
    / "v0.1.1_144shard_500k/replicate_S144/stage15c_144shard_fullscale_resource_model.tsv"
)
ARCH144_RESOURCE_SHA256 = "0f694387afd5320409aac021a52bd5ab942fd9b33d2446ccafa6c6060fabdc13"

META_ROOT = PROJECT_ROOT / "metadata/stage15c/execution_unlocked_full_runner_v0.1.4"
EVIDENCE_ROOT = META_ROOT / "evidence"
UNLOCK_CONTRACT = META_ROOT / "rnatr_stage15c_full_runner_execution_unlock_v0.1.4.json"
PREFLIGHT_EVIDENCE_INSTALL = EVIDENCE_ROOT / LOCKED_PREFLIGHT_BUNDLE.name
BUILD_QC_ROOT = (
    PROJECT_ROOT / "qc/15_stage15c_execution_unlocked_runner_build"
    / ANALYSIS_RUN_ID / "v0.1.4"
)
BUILDER_INSTALL = PROJECT_ROOT / "scripts/rnatr_stage15c_build_execution_unlocked_full_runner_v0.1.4.py"
RUNNER_INSTALL = PROJECT_ROOT / "scripts/rnatr_stage15c_run_full5312696_bam_to_final_v0.1.4.py"
DOC_INSTALL = PROJECT_ROOT / "docs/stage15c/RNA_TR_Scout_execution_unlocked_full_runner_build_v0.1.4.md"
RUNNER_DOWNLOAD = DOWNLOADS / "rnatr_stage15c_run_full5312696_bam_to_final_v014.py"
SUCCESS_BUNDLE = DOWNLOADS / "rnatr_stage15c_execution_unlocked_full_runner_build_v0.1.4.tar.gz"

FULL_RESULT_ROOT = (
    PROJECT_ROOT / "results/15_stage15c_fullscale_bam_to_final" / ANALYSIS_RUN_ID / "v0.1.4"
)
FULL_QC_ROOT = (
    PROJECT_ROOT / "qc/15_stage15c_fullscale_bam_to_final" / ANALYSIS_RUN_ID / "v0.1.4"
)
FINAL_PREFLIGHT_ROOT = (
    PROJECT_ROOT / "qc/15_stage15c_fullscale_runner_preflight" / ANALYSIS_RUN_ID / "v0.1.4"
)


class BuildError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def ensure_exact(path: Path, expected_sha256: str) -> None:
    if not path.is_file() or path.stat().st_size <= 0:
        raise BuildError(f"missing/empty required artifact: {path}")
    observed = sha256_file(path)
    if observed != expected_sha256:
        raise BuildError(
            f"SHA-256 mismatch: {path}: expected={expected_sha256} observed={observed}"
        )


def read_two_column(path: Path) -> dict[str, str]:
    if not path.is_file() or path.stat().st_size <= 0:
        raise BuildError(f"missing/empty two-column TSV: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        header = next(reader, None)
        if not header or len(header) < 2:
            raise BuildError(f"invalid two-column TSV: {path}")
        return {row[0]: row[1] for row in reader if len(row) >= 2}


def read_dicts(path: Path) -> list[dict[str, str]]:
    if not path.is_file() or path.stat().st_size <= 0:
        raise BuildError(f"missing/empty TSV: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if not reader.fieldnames:
            raise BuildError(f"missing TSV header: {path}")
        return list(reader)


def write_tsv(path: Path, rows: Iterable[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + f".part.{os.getpid()}")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fields, delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def write_metrics(path: Path, rows: Iterable[tuple[str, Any]]) -> None:
    write_tsv(
        path,
        ({"metric": key, "value": value} for key, value in rows),
        ["metric", "value"],
    )


def atomic_write(path: Path, payload: bytes, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + f".part.{os.getpid()}")
    with temporary.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.chmod(mode)
    os.replace(temporary, path)


def install_exact_bytes(payload: bytes, destination: Path, mode: int = 0o644) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    expected = sha256_bytes(payload)
    if destination.exists():
        if not destination.is_file() or sha256_file(destination) != expected:
            raise BuildError(f"refusing overwrite of different versioned file: {destination}")
        destination.chmod(mode)
        return "REUSED_EXACT"
    atomic_write(destination, payload, mode)
    return "INSTALLED_NEW"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise BuildError(f"transform anchor {label} expected once, observed {count}")
    return text.replace(old, new, 1)


def insert_after_once(text: str, anchor: str, payload: str, label: str) -> str:
    return replace_once(text, anchor, anchor + payload, label)


def locate_locked_runner() -> Path:
    ensure_exact(LOCKED_RUNNER_PROJECT, LOCKED_RUNNER_SHA256)
    if LOCKED_RUNNER_DOWNLOAD.exists():
        ensure_exact(LOCKED_RUNNER_DOWNLOAD, LOCKED_RUNNER_SHA256)
    return LOCKED_RUNNER_PROJECT


def verify_locked_preflight_bundle() -> dict[str, bytes]:
    ensure_exact(LOCKED_PREFLIGHT_BUNDLE, LOCKED_PREFLIGHT_BUNDLE_SHA256)
    ensure_exact(LOCKED_PREFLIGHT_SIDECAR, LOCKED_PREFLIGHT_SIDECAR_SHA256)
    expected_sidecar = (
        f"{LOCKED_PREFLIGHT_BUNDLE_SHA256}  {LOCKED_PREFLIGHT_BUNDLE.name}\n"
    ).encode("utf-8")
    if LOCKED_PREFLIGHT_SIDECAR.read_bytes() != expected_sidecar:
        raise BuildError("locked preflight sidecar content mismatch")

    observed: dict[str, bytes] = {}
    with tarfile.open(LOCKED_PREFLIGHT_BUNDLE, "r:gz") as archive:
        members = archive.getmembers()
        names = [member.name for member in members]
        if len(names) != len(set(names)):
            raise BuildError("duplicate member name in locked preflight bundle")
        if set(names) != set(BUNDLE_MEMBER_HASHES):
            missing = sorted(set(BUNDLE_MEMBER_HASHES) - set(names))
            extra = sorted(set(names) - set(BUNDLE_MEMBER_HASHES))
            raise BuildError(
                f"locked preflight bundle member mismatch missing={missing} extra={extra}"
            )
        for member in members:
            if not member.isfile() or member.issym() or member.islnk():
                raise BuildError(f"non-regular bundle member: {member.name}")
            member_path = Path(member.name)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise BuildError(f"unsafe bundle member path: {member.name}")
            handle = archive.extractfile(member)
            if handle is None:
                raise BuildError(f"cannot read bundle member: {member.name}")
            payload = handle.read()
            expected = BUNDLE_MEMBER_HASHES[member.name]
            actual = sha256_bytes(payload)
            if actual != expected:
                raise BuildError(
                    f"bundle member hash mismatch {member.name}: {actual} != {expected}"
                )
            observed[member.name] = payload

    manifest_member = f"{BUNDLE_ROOT}/v0.1.3/artifact_manifest.tsv"
    manifest_text = observed[manifest_member].decode("utf-8")
    manifest_rows = list(csv.DictReader(manifest_text.splitlines(), delimiter="\t"))
    expected_manifest = {
        "mapping_artifact_integrity.tsv": LOCKED_PREFLIGHT_MAPPING_INTEGRITY_SHA256,
        "resource_model.tsv": LOCKED_PREFLIGHT_RESOURCE_SHA256,
        "source_and_contract_guards.tsv": LOCKED_PREFLIGHT_SOURCE_GUARDS_SHA256,
        "stage15c_fullscale_runner_preflight.qc.tsv": LOCKED_PREFLIGHT_QC_SHA256,
    }
    if len(manifest_rows) != len(expected_manifest):
        raise BuildError(
            f"locked preflight artifact manifest row count mismatch: {len(manifest_rows)}"
        )
    for row in manifest_rows:
        name = row.get("artifact", "")
        if expected_manifest.get(name) != row.get("sha256"):
            raise BuildError(f"locked preflight artifact manifest mismatch: {row}")
        member_name = f"{BUNDLE_ROOT}/v0.1.3/{name}"
        if int(row.get("bytes", "-1")) != len(observed[member_name]):
            raise BuildError(f"locked preflight artifact size mismatch: {row}")
    return observed


def verify_lock_contract_semantics() -> None:
    ensure_exact(LOCKED_RUNNER_LOCK, LOCKED_RUNNER_LOCK_SHA256)
    try:
        lock = json.loads(LOCKED_RUNNER_LOCK.read_text(encoding="utf-8"))
    except Exception as exc:
        raise BuildError(f"invalid v0.1.3 lock contract: {exc}") from exc
    expected_top = {
        "schema": "rnatr.full_runner_lock.v1",
        "runner_version": "rnatr_stage15c_full5312696_bam_to_final_v0.1.3",
        "analysis_run_id": ANALYSIS_RUN_ID,
        "mapping_run_id": MAPPING_RUN_ID,
    }
    for key, expected in expected_top.items():
        if lock.get(key) != expected:
            raise BuildError(f"v0.1.3 lock contract mismatch {key}: {lock.get(key)}")
    execution = lock.get("execution", {})
    for key, expected in {
        "read_coherent_shards": SHARDS,
        "active_shard_concurrency": CONCURRENCY,
        "caller_workers_per_shard": CALLER_WORKERS_PER_SHARD,
        "validator_workers": VALIDATOR_WORKERS,
        "validator_sort_buffer": SORT_BUFFER,
        "python_hash_seed": "0",
    }.items():
        if execution.get(key) != expected:
            raise BuildError(f"v0.1.3 execution lock mismatch {key}: {execution.get(key)}")
    hard = lock.get("hard_gates", {})
    for key, expected in {
        "post_11b_candidate_rows_per_shard_max": POST_11B_HARD_MAX,
        "post_11b_gate_must_precede_candidate_extraction": True,
        "post_11b_gate_must_precede_caller_materializer": True,
        "active_pipeline_modification_allowed": False,
        "ssot_modification_allowed": False,
        "core_schema_modification_allowed": False,
    }.items():
        if hard.get(key) != expected:
            raise BuildError(f"v0.1.3 hard-gate lock mismatch {key}: {hard.get(key)}")
    authorization = lock.get("authorization", {})
    if authorization.get("full_execution_authorized") is not False:
        raise BuildError("v0.1.3 lock was not execution-locked")
    if authorization.get("preflight_authorized") is not True:
        raise BuildError("v0.1.3 lock did not authorize preflight")


def verify_project_evidence() -> dict[str, Any]:
    for path, digest in (
        (LOCKED_PREFLIGHT_QC, LOCKED_PREFLIGHT_QC_SHA256),
        (LOCKED_PREFLIGHT_RESOURCE, LOCKED_PREFLIGHT_RESOURCE_SHA256),
        (LOCKED_PREFLIGHT_SOURCE_GUARDS, LOCKED_PREFLIGHT_SOURCE_GUARDS_SHA256),
        (LOCKED_PREFLIGHT_MAPPING_INTEGRITY, LOCKED_PREFLIGHT_MAPPING_INTEGRITY_SHA256),
        (ARCH144_CONTRACT, ARCH144_CONTRACT_SHA256),
        (ARCH144_QC, ARCH144_QC_SHA256),
        (ARCH144_RESOURCE, ARCH144_RESOURCE_SHA256),
    ):
        ensure_exact(path, digest)
    verify_lock_contract_semantics()

    qc = read_two_column(LOCKED_PREFLIGHT_QC)
    required_qc = {
        "stage_version": "rnatr_stage15c_full5312696_bam_to_final_v0.1.3",
        "run_id": ANALYSIS_RUN_ID,
        "runner_sha256": LOCKED_RUNNER_SHA256,
        "input_fastq_sha256": EXPECTED_FASTQ_SHA256,
        "input_fastq_reads": str(EXPECTED_READS),
        "fastq_unique_id_rows": str(EXPECTED_READS),
        "fastq_duplicate_id_rows": "0",
        "input_bam_sha256": EXPECTED_BAM_SHA256,
        "shards": str(SHARDS),
        "stage_workers": str(CONCURRENCY),
        "caller_pipeline_workers": str(CONCURRENCY),
        "caller_workers_per_shard": str(CALLER_WORKERS_PER_SHARD),
        "validator_workers": str(VALIDATOR_WORKERS),
        "memory_readiness": "PASS",
        "storage_readiness": "PASS",
        "runtime_projection_readiness": "PASS_STRICT",
        "active_pipeline_modified": "false",
        "ssot_modified": "false",
        "core_schema_modified": "false",
        "full_5_31m_run_started": "false",
        "validated_architecture_shards": str(SHARDS),
        "post_11b_candidate_rows_per_shard_hard_max": str(POST_11B_HARD_MAX),
        "execute_authorized": "false",
        "runner_execution_locked": "true",
        "preflight_status": "PASS_LOCKED_READY_FOR_PRO_REVIEW",
        "next_gate": "UPLOAD_PREFLIGHT_BUNDLE_FOR_PRO_REVIEW_AND_EXECUTION_UNLOCK",
    }
    for key, expected in required_qc.items():
        if qc.get(key) != expected:
            raise BuildError(f"locked preflight QC mismatch {key}: {qc.get(key)} != {expected}")

    resource = read_two_column(LOCKED_PREFLIGHT_RESOURCE)
    for key, expected in {
        "shards": str(SHARDS),
        "stage_workers": str(CONCURRENCY),
        "caller_pipeline_workers": str(CONCURRENCY),
        "caller_workers_per_shard": str(CALLER_WORKERS_PER_SHARD),
        "validator_workers": str(VALIDATOR_WORKERS),
        "memory_readiness": "PASS",
        "storage_readiness": "PASS",
        "runtime_projection_readiness": "PASS_STRICT",
    }.items():
        if resource.get(key) != expected:
            raise BuildError(f"locked preflight resource mismatch {key}: {resource.get(key)}")
    materializer_fraction = float(resource["projected_materializer_memory_fraction"])
    validator_fraction = float(resource["projected_validator_memory_fraction"])
    runtime_minutes = float(resource["projected_runtime_minutes_with_5pct_shard_overhead"])
    if materializer_fraction >= 0.75 or validator_fraction >= 0.75:
        raise BuildError("locked preflight memory projection exceeds safety fraction")
    if runtime_minutes > 60.0:
        raise BuildError("locked preflight runtime projection exceeds strict 60-minute benchmark")

    guard_rows = read_dicts(LOCKED_PREFLIGHT_SOURCE_GUARDS)
    if not guard_rows or any(
        row.get("status") != "PASS"
        or row.get("expected_sha256") != row.get("observed_sha256")
        for row in guard_rows
    ):
        raise BuildError("locked preflight source/contract guards are not all PASS")
    mapping_rows = read_dicts(LOCKED_PREFLIGHT_MAPPING_INTEGRITY)
    if not mapping_rows or any(row.get("status") != "PASS" for row in mapping_rows):
        raise BuildError("locked preflight mapping integrity is not all PASS")

    contract_rows = read_dicts(ARCH144_CONTRACT)
    contract = {row["field"]: row for row in contract_rows}
    for key, expected_value, expected_status in (
        ("planned_run_id", ANALYSIS_RUN_ID, "PROVISIONAL"),
        ("read_coherent_shards", str(SHARDS), "VALIDATED_500K_EXACT_PARITY"),
        ("active_shard_concurrency", str(CONCURRENCY), "PASS"),
        ("caller_workers_per_shard", str(CALLER_WORKERS_PER_SHARD), "VALIDATED_500K"),
        ("validator_workers", str(VALIDATOR_WORKERS), "VALIDATED_500K"),
        ("validator_sort_buffer", SORT_BUFFER, "VALIDATED_500K"),
        ("full_post_11b_shard_load_hard_gate_required", "true", "MANDATORY_FOR_FULL_RUNNER"),
        ("full_runner_build_authorized", "true", "PASS"),
        ("full_empirical_run_authorized", "false", "NOT_BY_THIS_STAGE"),
    ):
        row = contract.get(key)
        if row is None or row.get("value") != expected_value or row.get("status") != expected_status:
            raise BuildError(f"144-shard contract mismatch {key}: {row}")

    arch_qc = read_two_column(ARCH144_QC)
    arch_resource = read_two_column(ARCH144_RESOURCE)
    for key, expected in {
        "planned_full_run_id": ANALYSIS_RUN_ID,
        "shard_count": str(SHARDS),
        "stage_concurrency": str(CONCURRENCY),
        "caller_workers_per_shard": str(CALLER_WORKERS_PER_SHARD),
        "validator_workers": str(VALIDATOR_WORKERS),
        "projected_shard_load_status": "PASS",
        "resource_model_fit_status": "PASS_EMPIRICAL_12_AND_144_SHARD_FIT",
        "full_memory_readiness_status": "PASS",
        "provisional_full_runner_build_authorized": "true",
        "full_empirical_run_authorized": "false",
        "audit_status": "PASS",
    }.items():
        if arch_qc.get(key) != expected:
            raise BuildError(f"144-shard QC mismatch {key}: {arch_qc.get(key)}")
    for key, expected in {
        "accepted_12shard_max_candidate_rows": str(POST_11B_HARD_MAX),
        "projected_shard_load_status": "PASS",
        "model_fit_status": "PASS_EMPIRICAL_12_AND_144_SHARD_FIT",
        "memory_readiness_status": "PASS",
        "runtime_projection_status": "PASS_STRICT_PROJECTION",
    }.items():
        if arch_resource.get(key) != expected:
            raise BuildError(f"144-shard resource mismatch {key}: {arch_resource.get(key)}")
    for label, resource_value, qc_value in (
        ("load", arch_resource.get("projected_shard_load_status"), arch_qc.get("projected_shard_load_status")),
        ("fit", arch_resource.get("model_fit_status"), arch_qc.get("resource_model_fit_status")),
        ("memory", arch_resource.get("memory_readiness_status"), arch_qc.get("full_memory_readiness_status")),
        ("runtime", arch_resource.get("runtime_projection_status"), arch_qc.get("runtime_projection_status")),
    ):
        if resource_value != qc_value:
            raise BuildError(
                f"144-shard cross-schema mismatch {label}: resource={resource_value} qc={qc_value}"
            )

    for root in (FULL_RESULT_ROOT, FULL_QC_ROOT, FINAL_PREFLIGHT_ROOT):
        if root.exists():
            raise BuildError(f"v0.1.4 output root already exists; preserve and review: {root}")

    return {
        "preflight_time_utc": qc["preflight_time_utc"],
        "logical_cpus": int(qc["logical_cpus"]),
        "rlimit_nofile_soft": int(qc["rlimit_nofile_soft"]),
        "project_free_bytes": int(resource["current_project_free_bytes"]),
        "projected_materializer_memory_fraction": materializer_fraction,
        "projected_validator_memory_fraction": validator_fraction,
        "projected_runtime_minutes": runtime_minutes,
        "validated_projection_minutes": float(
            arch_qc["execution_architecture_adjusted_full_projection_minutes"]
        ),
        "validated_projected_memory_fraction": float(
            arch_qc["projected_full_memory_fraction"]
        ),
    }


def make_unlock_contract(preflight: dict[str, Any]) -> bytes:
    payload = {
        "schema": UNLOCK_SCHEMA,
        "authorization_date": "2026-08-10",
        "builder_version": BUILDER_VERSION,
        "runner_version": RUNNER_VERSION,
        "analysis_run_id": ANALYSIS_RUN_ID,
        "mapping_run_id": MAPPING_RUN_ID,
        "input": {
            "reads": EXPECTED_READS,
            "bam_sha256": EXPECTED_BAM_SHA256,
            "fastq_sha256": EXPECTED_FASTQ_SHA256,
        },
        "validated_execution": {
            "read_coherent_shards": SHARDS,
            "active_shard_concurrency": CONCURRENCY,
            "caller_workers_per_shard": CALLER_WORKERS_PER_SHARD,
            "validator_workers": VALIDATOR_WORKERS,
            "validator_sort_buffer": SORT_BUFFER,
            "post_11b_candidate_rows_per_shard_hard_max": POST_11B_HARD_MAX,
            "post_11b_gate_must_precede_candidate_extraction": True,
            "post_11b_gate_must_precede_caller_materializer": True,
        },
        "validated_model": {
            "architecture_adjusted_projection_minutes": preflight["validated_projection_minutes"],
            "projected_full_memory_fraction": preflight["validated_projected_memory_fraction"],
            "locked_preflight_runtime_minutes_with_overhead": preflight["projected_runtime_minutes"],
            "locked_preflight_materializer_memory_fraction": preflight[
                "projected_materializer_memory_fraction"
            ],
            "locked_preflight_validator_memory_fraction": preflight[
                "projected_validator_memory_fraction"
            ],
        },
        "locked_preflight": {
            "runner_v013_sha256": LOCKED_RUNNER_SHA256,
            "runner_lock_contract_v013_sha256": LOCKED_RUNNER_LOCK_SHA256,
            "preflight_bundle_v013_sha256": LOCKED_PREFLIGHT_BUNDLE_SHA256,
            "preflight_qc_v013_sha256": LOCKED_PREFLIGHT_QC_SHA256,
            "preflight_resource_model_v013_sha256": LOCKED_PREFLIGHT_RESOURCE_SHA256,
            "preflight_source_guards_v013_sha256": LOCKED_PREFLIGHT_SOURCE_GUARDS_SHA256,
            "preflight_mapping_integrity_v013_sha256": LOCKED_PREFLIGHT_MAPPING_INTEGRITY_SHA256,
            "preflight_status": "PASS_LOCKED_READY_FOR_PRO_REVIEW",
            "execute_authorized_in_v013": False,
            "full_5_31m_run_started": False,
            "preflight_time_utc": preflight["preflight_time_utc"],
        },
        "authorization": {
            "full_execution_authorized": True,
            "authorized_scope": "CLEAN_EMPIRICAL_FULL_5312696_READ_BAM_TO_FINAL",
            "requires_exact_v014_preflight": True,
            "requires_exact_confirm_run_id": True,
            "mapping_included_in_bam_to_final_timer": False,
            "restart_resume_equivalence_deferred_to_next_blocking_gate": True,
        },
        "prohibitions": {
            "active_pipeline_modification_allowed": False,
            "ssot_modification_allowed": False,
            "core_schema_modification_allowed": False,
            "caller_modification_allowed": False,
            "materializer_modification_allowed": False,
            "accepted_500k_result_modification_allowed": False,
        },
        "provenance_amendments": [
            "v0.1.3 was execution-locked and preflighted successfully",
            "v0.1.4 corrects the execution-contract heading to v0.1.4",
            "v0.1.4 removes the stale 60-shard explanatory comment; validated execution remains 144 shards",
        ],
    }
    return (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode("utf-8")


def unlock_verifier_source(unlock_sha256: str) -> str:
    return f'''

def verify_execution_unlock_evidence() -> dict[str, Any]:
    ensure_file(EXECUTION_UNLOCK_CONTRACT)
    ensure_file(LOCKED_PREFLIGHT_EVIDENCE_BUNDLE)
    if sha256_file(EXECUTION_UNLOCK_CONTRACT) != EXECUTION_UNLOCK_CONTRACT_SHA256:
        raise RunnerError("execution unlock contract SHA-256 mismatch")
    if sha256_file(LOCKED_PREFLIGHT_EVIDENCE_BUNDLE) != LOCKED_PREFLIGHT_EVIDENCE_BUNDLE_SHA256:
        raise RunnerError("locked preflight evidence bundle SHA-256 mismatch")
    try:
        payload = json.loads(EXECUTION_UNLOCK_CONTRACT.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RunnerError(f"invalid execution unlock contract: {{exc}}") from exc
    required_top = {{
        "schema": "{UNLOCK_SCHEMA}",
        "authorization_date": "2026-08-10",
        "builder_version": "{BUILDER_VERSION}",
        "runner_version": VERSION,
        "analysis_run_id": ANALYSIS_RUN_ID,
        "mapping_run_id": MAPPING_RUN_ID,
    }}
    for key, expected in required_top.items():
        if payload.get(key) != expected:
            raise RunnerError(
                f"execution unlock contract mismatch {{key}}: "
                f"{{payload.get(key)}} != {{expected}}"
            )
    input_contract = payload.get("input", {{}})
    for key, expected in {{
        "reads": EXPECTED_READS,
        "bam_sha256": EXPECTED_BAM_SHA256,
        "fastq_sha256": "{EXPECTED_FASTQ_SHA256}",
    }}.items():
        if input_contract.get(key) != expected:
            raise RunnerError(
                f"execution unlock input mismatch {{key}}: "
                f"{{input_contract.get(key)}} != {{expected}}"
            )
    execution = payload.get("validated_execution", {{}})
    for key, expected in {{
        "read_coherent_shards": SHARDS,
        "active_shard_concurrency": STAGE_WORKERS,
        "caller_workers_per_shard": CALLER_WORKERS_PER_SHARD,
        "validator_workers": VALIDATOR_WORKERS,
        "validator_sort_buffer": EXTERNAL_SORT_BUFFER,
        "post_11b_candidate_rows_per_shard_hard_max": POST_11B_MAX_CANDIDATE_ROWS_PER_SHARD,
        "post_11b_gate_must_precede_candidate_extraction": True,
        "post_11b_gate_must_precede_caller_materializer": True,
    }}.items():
        if execution.get(key) != expected:
            raise RunnerError(
                f"execution unlock architecture mismatch {{key}}: "
                f"{{execution.get(key)}} != {{expected}}"
            )
    authorization = payload.get("authorization", {{}})
    for key, expected in {{
        "full_execution_authorized": True,
        "authorized_scope": "CLEAN_EMPIRICAL_FULL_5312696_READ_BAM_TO_FINAL",
        "requires_exact_v014_preflight": True,
        "requires_exact_confirm_run_id": True,
        "mapping_included_in_bam_to_final_timer": False,
        "restart_resume_equivalence_deferred_to_next_blocking_gate": True,
    }}.items():
        if authorization.get(key) != expected:
            raise RunnerError(
                f"execution unlock authorization mismatch {{key}}: "
                f"{{authorization.get(key)}} != {{expected}}"
            )
    prohibitions = payload.get("prohibitions", {{}})
    for key in (
        "active_pipeline_modification_allowed",
        "ssot_modification_allowed",
        "core_schema_modification_allowed",
        "caller_modification_allowed",
        "materializer_modification_allowed",
        "accepted_500k_result_modification_allowed",
    ):
        if prohibitions.get(key) is not False:
            raise RunnerError(f"execution unlock prohibition mismatch {{key}}")
    locked = payload.get("locked_preflight", {{}})
    for key, expected in {{
        "runner_v013_sha256": LOCKED_RUNNER_SOURCE_SHA256,
        "runner_lock_contract_v013_sha256": RUNNER_LOCK_CONTRACT_SHA256,
        "preflight_bundle_v013_sha256": LOCKED_PREFLIGHT_EVIDENCE_BUNDLE_SHA256,
        "preflight_qc_v013_sha256": LOCKED_PREFLIGHT_QC_SHA256,
        "preflight_resource_model_v013_sha256": LOCKED_PREFLIGHT_RESOURCE_MODEL_SHA256,
        "preflight_source_guards_v013_sha256": LOCKED_PREFLIGHT_SOURCE_GUARDS_SHA256,
        "preflight_mapping_integrity_v013_sha256": LOCKED_PREFLIGHT_MAPPING_INTEGRITY_SHA256,
        "preflight_status": "PASS_LOCKED_READY_FOR_PRO_REVIEW",
        "execute_authorized_in_v013": False,
        "full_5_31m_run_started": False,
    }}.items():
        if locked.get(key) != expected:
            raise RunnerError(
                f"execution unlock locked-preflight mismatch {{key}}: "
                f"{{locked.get(key)}} != {{expected}}"
            )
    locked_qc = read_two_column(LOCKED_PREFLIGHT_QC)
    for key, expected in {{
        "stage_version": "rnatr_stage15c_full5312696_bam_to_final_v0.1.3",
        "run_id": ANALYSIS_RUN_ID,
        "runner_sha256": LOCKED_RUNNER_SOURCE_SHA256,
        "input_fastq_reads": str(EXPECTED_READS),
        "fastq_unique_id_rows": str(EXPECTED_READS),
        "fastq_duplicate_id_rows": "0",
        "input_bam_sha256": EXPECTED_BAM_SHA256,
        "shards": str(SHARDS),
        "caller_pipeline_workers": str(CALLER_PIPELINE_WORKERS),
        "validator_workers": str(VALIDATOR_WORKERS),
        "memory_readiness": "PASS",
        "storage_readiness": "PASS",
        "runtime_projection_readiness": "PASS_STRICT",
        "full_5_31m_run_started": "false",
        "execute_authorized": "false",
        "runner_execution_locked": "true",
        "preflight_status": "PASS_LOCKED_READY_FOR_PRO_REVIEW",
    }}.items():
        if locked_qc.get(key) != expected:
            raise RunnerError(
                f"locked v0.1.3 preflight mismatch {{key}}: "
                f"{{locked_qc.get(key)}} != {{expected}}"
            )
    if locked.get("preflight_time_utc") != locked_qc.get("preflight_time_utc"):
        raise RunnerError(
            "execution unlock locked-preflight timestamp mismatch: "
            f"contract={{locked.get('preflight_time_utc')}} "
            f"qc={{locked_qc.get('preflight_time_utc')}}"
        )
    resource_model = read_two_column(LOCKED_PREFLIGHT_RESOURCE_MODEL)
    for key, expected in {{
        "shards": str(SHARDS),
        "caller_pipeline_workers": str(CALLER_PIPELINE_WORKERS),
        "validator_workers": str(VALIDATOR_WORKERS),
        "memory_readiness": "PASS",
        "storage_readiness": "PASS",
        "runtime_projection_readiness": "PASS_STRICT",
    }}.items():
        if resource_model.get(key) != expected:
            raise RunnerError(
                f"locked v0.1.3 resource model mismatch {{key}}: "
                f"{{resource_model.get(key)}} != {{expected}}"
            )
    source_guards = read_dicts(LOCKED_PREFLIGHT_SOURCE_GUARDS)
    if not source_guards or any(
        row.get("status") != "PASS"
        or row.get("expected_sha256") != row.get("observed_sha256")
        for row in source_guards
    ):
        raise RunnerError("locked v0.1.3 source/contract guards are not all PASS")
    mapping_integrity = read_dicts(LOCKED_PREFLIGHT_MAPPING_INTEGRITY)
    if not mapping_integrity or any(
        row.get("status") != "PASS" for row in mapping_integrity
    ):
        raise RunnerError("locked v0.1.3 mapping integrity is not all PASS")
    return {{
        "unlock_contract_sha256": EXECUTION_UNLOCK_CONTRACT_SHA256,
        "locked_preflight_bundle_sha256": LOCKED_PREFLIGHT_EVIDENCE_BUNDLE_SHA256,
        "locked_preflight_qc_sha256": LOCKED_PREFLIGHT_QC_SHA256,
        "locked_preflight_time_utc": locked_qc["preflight_time_utc"],
        "full_execution_authorized": True,
    }}
'''


def transform_runner(source: str, unlock_sha256: str) -> str:
    text = source
    for old, new, label in (
        (
            'VERSION = "rnatr_stage15c_full5312696_bam_to_final_v0.1.3"',
            'VERSION = "rnatr_stage15c_full5312696_bam_to_final_v0.1.4"',
            "version",
        ),
        ("FULL_EXECUTION_AUTHORIZED = False", "FULL_EXECUTION_AUTHORIZED = True", "authorization"),
        (
            "# execution-only shard count to 60. With 12 concurrent shard pipelines this",
            "# execution-only shard count to 144. With 12 concurrent shard pipelines this",
            "stale_comment",
        ),
        (
            '    PROJECT_ROOT / "results/15_stage15c_fullscale_bam_to_final" / RUN_ID / "v0.1.3"',
            '    PROJECT_ROOT / "results/15_stage15c_fullscale_bam_to_final" / RUN_ID / "v0.1.4"',
            "result_root",
        ),
        (
            '    PROJECT_ROOT / "qc/15_stage15c_fullscale_bam_to_final" / RUN_ID / "v0.1.3"',
            '    PROJECT_ROOT / "qc/15_stage15c_fullscale_bam_to_final" / RUN_ID / "v0.1.4"',
            "qc_root",
        ),
        (
            '    PROJECT_ROOT / "qc/15_stage15c_fullscale_runner_preflight" / RUN_ID / "v0.1.3"',
            '    PROJECT_ROOT / "qc/15_stage15c_fullscale_runner_preflight" / RUN_ID / "v0.1.4"',
            "preflight_root",
        ),
        (
            'DOC_PATH = PROJECT_ROOT / "docs/stage15c/RNA_TR_Scout_fullscale_runner_execution_contract_v0.1.3.md"',
            'DOC_PATH = PROJECT_ROOT / "docs/stage15c/RNA_TR_Scout_fullscale_runner_execution_contract_v0.1.4.md"',
            "doc_path",
        ),
        (
            'SCRIPT_INSTALL = PROJECT_ROOT / "scripts/rnatr_stage15c_run_full5312696_bam_to_final_v0.1.3.py"',
            'SCRIPT_INSTALL = PROJECT_ROOT / "scripts/rnatr_stage15c_run_full5312696_bam_to_final_v0.1.4.py"',
            "script_install",
        ),
        (
            'PREFLIGHT_BUNDLE = DOWNLOADS / "rnatr_stage15c_fullscale_runner_preflight_v0.1.3.tar.gz"',
            'PREFLIGHT_BUNDLE = DOWNLOADS / "rnatr_stage15c_fullscale_runner_preflight_v0.1.4.tar.gz"',
            "preflight_bundle",
        ),
        (
            'SUCCESS_BUNDLE = DOWNLOADS / "rnatr_stage15c_full_empirical_run_v0.1.3.tar.gz"',
            'SUCCESS_BUNDLE = DOWNLOADS / "rnatr_stage15c_full_empirical_run_v0.1.4.tar.gz"',
            "success_bundle",
        ),
        (
            'FAILURE_BUNDLE = DOWNLOADS / "rnatr_stage15c_full_empirical_run_v0.1.3_failure.tar.gz"',
            'FAILURE_BUNDLE = DOWNLOADS / "rnatr_stage15c_full_empirical_run_v0.1.4_failure.tar.gz"',
            "failure_bundle",
        ),
        (
            '# RNA-TR-Scout Stage 15C full-scale execution contract v0.1.0',
            '# RNA-TR-Scout Stage 15C full-scale execution contract v0.1.4',
            "contract_heading",
        ),
    ):
        text = replace_once(text, old, new, label)

    constant_anchor = (
        'FAILURE_BUNDLE = DOWNLOADS / "rnatr_stage15c_full_empirical_run_v0.1.4_failure.tar.gz"\n'
    )
    extra_constants = f'''

LOCKED_RUNNER_SOURCE = PROJECT_ROOT / "scripts/rnatr_stage15c_run_full5312696_bam_to_final_v0.1.3.py"
LOCKED_RUNNER_SOURCE_SHA256 = "{LOCKED_RUNNER_SHA256}"
LOCKED_PREFLIGHT_QC = (
    PROJECT_ROOT / "qc/15_stage15c_fullscale_runner_preflight" / RUN_ID
    / "v0.1.3/stage15c_fullscale_runner_preflight.qc.tsv"
)
LOCKED_PREFLIGHT_QC_SHA256 = "{LOCKED_PREFLIGHT_QC_SHA256}"
LOCKED_PREFLIGHT_RESOURCE_MODEL = (
    PROJECT_ROOT / "qc/15_stage15c_fullscale_runner_preflight" / RUN_ID
    / "v0.1.3/resource_model.tsv"
)
LOCKED_PREFLIGHT_RESOURCE_MODEL_SHA256 = "{LOCKED_PREFLIGHT_RESOURCE_SHA256}"
LOCKED_PREFLIGHT_SOURCE_GUARDS = (
    PROJECT_ROOT / "qc/15_stage15c_fullscale_runner_preflight" / RUN_ID
    / "v0.1.3/source_and_contract_guards.tsv"
)
LOCKED_PREFLIGHT_SOURCE_GUARDS_SHA256 = "{LOCKED_PREFLIGHT_SOURCE_GUARDS_SHA256}"
LOCKED_PREFLIGHT_MAPPING_INTEGRITY = (
    PROJECT_ROOT / "qc/15_stage15c_fullscale_runner_preflight" / RUN_ID
    / "v0.1.3/mapping_artifact_integrity.tsv"
)
LOCKED_PREFLIGHT_MAPPING_INTEGRITY_SHA256 = "{LOCKED_PREFLIGHT_MAPPING_INTEGRITY_SHA256}"
LOCKED_PREFLIGHT_EVIDENCE_BUNDLE = (
    PROJECT_ROOT / "metadata/stage15c/execution_unlocked_full_runner_v0.1.4/evidence"
    / "rnatr_stage15c_fullscale_runner_preflight_v0.1.3.tar.gz"
)
LOCKED_PREFLIGHT_EVIDENCE_BUNDLE_SHA256 = "{LOCKED_PREFLIGHT_BUNDLE_SHA256}"
EXECUTION_UNLOCK_CONTRACT = (
    PROJECT_ROOT / "metadata/stage15c/execution_unlocked_full_runner_v0.1.4"
    / "rnatr_stage15c_full_runner_execution_unlock_v0.1.4.json"
)
EXECUTION_UNLOCK_CONTRACT_SHA256 = "{unlock_sha256}"
'''
    text = insert_after_once(text, constant_anchor, extra_constants, "authorization_constants")

    guard_anchor = "        RUNNER_LOCK_CONTRACT: RUNNER_LOCK_CONTRACT_SHA256,\n"
    guard_insert = (
        "        LOCKED_RUNNER_SOURCE: LOCKED_RUNNER_SOURCE_SHA256,\n"
        "        LOCKED_PREFLIGHT_QC: LOCKED_PREFLIGHT_QC_SHA256,\n"
        "        LOCKED_PREFLIGHT_RESOURCE_MODEL: LOCKED_PREFLIGHT_RESOURCE_MODEL_SHA256,\n"
        "        LOCKED_PREFLIGHT_SOURCE_GUARDS: LOCKED_PREFLIGHT_SOURCE_GUARDS_SHA256,\n"
        "        LOCKED_PREFLIGHT_MAPPING_INTEGRITY: LOCKED_PREFLIGHT_MAPPING_INTEGRITY_SHA256,\n"
        "        LOCKED_PREFLIGHT_EVIDENCE_BUNDLE: LOCKED_PREFLIGHT_EVIDENCE_BUNDLE_SHA256,\n"
        "        EXECUTION_UNLOCK_CONTRACT: EXECUTION_UNLOCK_CONTRACT_SHA256,\n"
    )
    text = insert_after_once(text, guard_anchor, guard_insert, "hash_guard_extension")

    text = replace_once(
        text,
        "\ndef verify_mapping_binding(*, recompute_large_hashes: bool) -> dict[str, Any]:\n",
        unlock_verifier_source(unlock_sha256)
        + "\ndef verify_mapping_binding(*, recompute_large_hashes: bool) -> dict[str, Any]:\n",
        "unlock_verifier_insertion",
    )

    contract_anchor = "Contract version date: 2026-08-09\n\n## Bound input"
    contract_replacement = f'''Contract version date: 2026-08-10

## Execution authorization

- Execution-unlock contract SHA-256: `{unlock_sha256}`
- Locked v0.1.3 preflight bundle SHA-256: `{LOCKED_PREFLIGHT_BUNDLE_SHA256}`
- Locked v0.1.3 runner SHA-256: `{LOCKED_RUNNER_SHA256}`
- This v0.1.4 runner must complete its own exact-byte preflight before `--execute`.
- Full execution is authorized only for the clean empirical `{ANALYSIS_RUN_ID}` BAM-to-final run.

## Bound input'''
    text = replace_once(text, contract_anchor, contract_replacement, "contract_authorization")

    text = replace_once(
        text,
        "    architecture = verify_stage15c_144_evidence()\n    mapping = verify_mapping_binding(recompute_large_hashes=True)",
        "    architecture = verify_stage15c_144_evidence()\n"
        "    unlock = verify_execution_unlock_evidence()\n"
        "    mapping = verify_mapping_binding(recompute_large_hashes=True)",
        "preflight_unlock_call",
    )
    text = replace_once(
        text,
        '        ("execute_authorized", "false"),\n'
        '        ("runner_execution_locked", "true"),\n'
        '        ("preflight_status", "PASS_LOCKED_READY_FOR_PRO_REVIEW"),\n'
        '        ("next_gate", "UPLOAD_PREFLIGHT_BUNDLE_FOR_PRO_REVIEW_AND_EXECUTION_UNLOCK"),',
        '        ("execution_unlock_contract", EXECUTION_UNLOCK_CONTRACT),\n'
        '        ("execution_unlock_contract_sha256", unlock["unlock_contract_sha256"]),\n'
        '        ("locked_preflight_bundle_sha256", unlock["locked_preflight_bundle_sha256"]),\n'
        '        ("locked_preflight_qc_sha256", unlock["locked_preflight_qc_sha256"]),\n'
        '        ("execute_authorized", "true"),\n'
        '        ("runner_execution_locked", "false"),\n'
        '        ("preflight_status", "PASS_EXECUTION_AUTHORIZED"),\n'
        '        ("next_gate", "EXECUTE_CLEAN_EMPIRICAL_FULL_5_31M_BAM_TO_FINAL"),',
        "preflight_qc_authorization",
    )
    text = replace_once(
        text,
        '    make_bundle(PREFLIGHT_BUNDLE, [PREFLIGHT_ROOT, DOC_PATH, SCRIPT_INSTALL], "rnatr_stage15c_fullscale_runner_preflight_v0.1.3")',
        '    make_bundle(PREFLIGHT_BUNDLE, [PREFLIGHT_ROOT, DOC_PATH, SCRIPT_INSTALL, EXECUTION_UNLOCK_CONTRACT], "rnatr_stage15c_fullscale_runner_preflight_v0.1.4")',
        "preflight_bundle_authorization",
    )
    text = replace_once(
        text,
        '    print(f"preflight_status\\tPASS_LOCKED_READY_FOR_PRO_REVIEW")',
        '    print(f"preflight_status\\tPASS_EXECUTION_AUTHORIZED")',
        "preflight_print_status",
    )
    text = replace_once(text, '    print("execute_authorized\\tfalse")', '    print("execute_authorized\\ttrue")', "preflight_print_execute")
    text = replace_once(text, '    print("runner_execution_locked\\ttrue")', '    print("runner_execution_locked\\tfalse")', "preflight_print_lock")

    required_anchor = '        "full_5_31m_run_started": "false",\n        "execute_authorized": "true",\n        "preflight_status": "PASS",\n'
    required_replacement = f'''        "full_5_31m_run_started": "false",
        "execution_unlock_contract_sha256": "{unlock_sha256}",
        "locked_preflight_bundle_sha256": "{LOCKED_PREFLIGHT_BUNDLE_SHA256}",
        "locked_preflight_qc_sha256": "{LOCKED_PREFLIGHT_QC_SHA256}",
        "execute_authorized": "true",
        "runner_execution_locked": "false",
        "preflight_status": "PASS_EXECUTION_AUTHORIZED",
'''
    text = replace_once(text, required_anchor, required_replacement, "execute_preflight_required_fields")

    integrity_anchor = '    if qc.get("runner_sha256") != sha256_file(current_script):\n'
    integrity_block = '''    manifest_path = PREFLIGHT_ROOT / "artifact_manifest.tsv"
    manifest_rows = read_dicts(manifest_path)
    expected_artifacts = {
        "mapping_artifact_integrity.tsv",
        "resource_model.tsv",
        "source_and_contract_guards.tsv",
        "stage15c_fullscale_runner_preflight.qc.tsv",
    }
    observed_artifacts = {row.get("artifact", "") for row in manifest_rows}
    if observed_artifacts != expected_artifacts:
        raise RunnerError(
            "preflight artifact manifest member mismatch: "
            f"observed={sorted(observed_artifacts)} expected={sorted(expected_artifacts)}"
        )
    for row in manifest_rows:
        artifact = PREFLIGHT_ROOT / row["artifact"]
        ensure_file(artifact)
        if artifact.stat().st_size != int(row["bytes"]):
            raise RunnerError(f"preflight artifact byte mismatch: {artifact}")
        if sha256_file(artifact) != row["sha256"]:
            raise RunnerError(f"preflight artifact SHA-256 mismatch: {artifact}")
'''
    text = replace_once(text, integrity_anchor, integrity_block + integrity_anchor, "preflight_integrity")

    text = replace_once(
        text,
        '        raise RunnerError("FULL_EXECUTION_LOCKED_PENDING_PRO_REVIEW_OF_V0.1.3_PREFLIGHT")',
        '        raise RunnerError("FULL_EXECUTION_NOT_AUTHORIZED_BY_V0.1.4_UNLOCK_CONTRACT")',
        "execute_authorization_error",
    )
    text = replace_once(
        text,
        "    preflight_qc = verify_preflight_for_execute(current_script)\n"
        "    verify_hash_guards()\n"
        "    verify_stage15b_evidence()",
        "    preflight_qc = verify_preflight_for_execute(current_script)\n"
        "    verify_hash_guards()\n"
        "    verify_execution_unlock_evidence()\n"
        "    verify_stage15b_evidence()",
        "execute_unlock_call",
    )
    text = replace_once(
        text,
        '    selected_roots = [QC_ROOT, DOC_PATH, SCRIPT_INSTALL, package_manifest, PACKAGE_FINAL / "materialization.qc.tsv"]',
        '    selected_roots = [QC_ROOT, DOC_PATH, SCRIPT_INSTALL, EXECUTION_UNLOCK_CONTRACT, package_manifest, PACKAGE_FINAL / "materialization.qc.tsv"]',
        "success_bundle_unlock",
    )
    text = replace_once(
        text,
        '    make_bundle(SUCCESS_BUNDLE, selected_roots, "rnatr_stage15c_full_empirical_run_v0.1.3")',
        '    make_bundle(SUCCESS_BUNDLE, selected_roots, "rnatr_stage15c_full_empirical_run_v0.1.4")',
        "success_bundle_version",
    )
    text = replace_once(
        text,
        '        make_bundle(FAILURE_BUNDLE, [QC_ROOT, DOC_PATH, SCRIPT_INSTALL], "rnatr_stage15c_full_empirical_run_failure_v0.1.3")',
        '        make_bundle(FAILURE_BUNDLE, [QC_ROOT, DOC_PATH, SCRIPT_INSTALL, EXECUTION_UNLOCK_CONTRACT], "rnatr_stage15c_full_empirical_run_failure_v0.1.4")',
        "failure_bundle_unlock",
    )
    return text


def top_level_constants(tree: ast.Module) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)) or node.value is None:
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Name):
                try:
                    values[target.id] = ast.literal_eval(node.value)
                except Exception:
                    pass
    return values


def function_nodes(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    }


def function_source(source: str, node: ast.FunctionDef) -> str:
    lines = source.splitlines(keepends=True)
    return "".join(lines[node.lineno - 1 : node.end_lineno])


def audit_runner_source(locked_source: str, generated_source: str, unlock_sha256: str) -> list[str]:
    errors: list[str] = []
    try:
        locked_tree = ast.parse(locked_source)
        tree = ast.parse(generated_source)
    except SyntaxError as exc:
        return [f"SYNTAX_ERROR:{exc}"]
    constants = top_level_constants(tree)
    for key, expected in {
        "VERSION": RUNNER_VERSION,
        "ANALYSIS_RUN_ID": ANALYSIS_RUN_ID,
        "MAPPING_RUN_ID": MAPPING_RUN_ID,
        "SHARDS": SHARDS,
        "STAGE_WORKERS": CONCURRENCY,
        "CALLER_PIPELINE_WORKERS": CONCURRENCY,
        "CALLER_WORKERS_PER_SHARD": CALLER_WORKERS_PER_SHARD,
        "VALIDATOR_WORKERS": VALIDATOR_WORKERS,
        "EXTERNAL_SORT_BUFFER": SORT_BUFFER,
        "POST_11B_MAX_CANDIDATE_ROWS_PER_SHARD": POST_11B_HARD_MAX,
        "FULL_EXECUTION_AUTHORIZED": True,
        "EXECUTION_UNLOCK_CONTRACT_SHA256": unlock_sha256,
        "LOCKED_PREFLIGHT_EVIDENCE_BUNDLE_SHA256": LOCKED_PREFLIGHT_BUNDLE_SHA256,
        "LOCKED_RUNNER_SOURCE_SHA256": LOCKED_RUNNER_SHA256,
    }.items():
        if constants.get(key) != expected:
            errors.append(f"CONST_MISMATCH:{key}:{constants.get(key)!r}!={expected!r}")
    if "RUN_ID = ANALYSIS_RUN_ID" not in generated_source:
        errors.append("RUN_ID_NOT_BOUND_TO_ANALYSIS_RUN_ID")
    if "# execution-only shard count to 60" in generated_source:
        errors.append("STALE_60_SHARD_COMMENT")
    if "# RNA-TR-Scout Stage 15C full-scale execution contract v0.1.0" in generated_source:
        errors.append("STALE_CONTRACT_HEADING_V010")
    if "# RNA-TR-Scout Stage 15C full-scale execution contract v0.1.4" not in generated_source:
        errors.append("CONTRACT_HEADING_V014_MISSING")
    for stale in (
        'results/15_stage15c_fullscale_bam_to_final" / RUN_ID / "v0.1.3',
        'qc/15_stage15c_fullscale_bam_to_final" / RUN_ID / "v0.1.3',
        'qc/15_stage15c_fullscale_runner_preflight" / RUN_ID / "v0.1.3"\n)',
        'rnatr_stage15c_full_empirical_run_v0.1.3',
    ):
        if stale in generated_source:
            errors.append("STALE_V013_OUTPUT_PROVENANCE:" + stale)
    for required, label in (
        ('("execute_authorized", "true")', "PREFLIGHT_EXECUTE_TRUE_MISSING"),
        ('("runner_execution_locked", "false")', "PREFLIGHT_UNLOCKED_MISSING"),
        ('("preflight_status", "PASS_EXECUTION_AUTHORIZED")', "PREFLIGHT_STATUS_MISSING"),
        ("verify_execution_unlock_evidence()", "UNLOCK_VERIFY_CALL_MISSING"),
        ("LOCKED_PREFLIGHT_EVIDENCE_BUNDLE: LOCKED_PREFLIGHT_EVIDENCE_BUNDLE_SHA256", "LOCKED_BUNDLE_GUARD_MISSING"),
        ("EXECUTION_UNLOCK_CONTRACT: EXECUTION_UNLOCK_CONTRACT_SHA256", "UNLOCK_CONTRACT_GUARD_MISSING"),
        ("preflight artifact SHA-256 mismatch", "PREFLIGHT_ARTIFACT_INTEGRITY_MISSING"),
        ("SCRIPT_INSTALL, EXECUTION_UNLOCK_CONTRACT", "PREFLIGHT_BUNDLE_UNLOCK_MISSING"),
    ):
        if required not in generated_source:
            errors.append(label)

    locked_functions = function_nodes(locked_tree)
    generated_functions = function_nodes(tree)
    allowed_changes = {
        "verify_hash_guards",
        "write_execution_contract",
        "preflight",
        "verify_preflight_for_execute",
        "execute",
        "failure_bundle",
    }
    if "verify_execution_unlock_evidence" not in generated_functions:
        errors.append("UNLOCK_VERIFIER_FUNCTION_MISSING")
    for name, node in locked_functions.items():
        other = generated_functions.get(name)
        if other is None:
            errors.append(f"FUNCTION_REMOVED:{name}")
            continue
        if name not in allowed_changes:
            if function_source(locked_source, node) != function_source(generated_source, other):
                errors.append(f"UNEXPECTED_FUNCTION_CHANGE:{name}")
    extra_functions = set(generated_functions) - set(locked_functions)
    if extra_functions != {"verify_execution_unlock_evidence"}:
        errors.append("UNEXPECTED_NEW_FUNCTIONS:" + ",".join(sorted(extra_functions)))

    execute = generated_functions.get("execute")
    if execute is None:
        errors.append("EXECUTE_FUNCTION_MISSING")
        return errors
    calls: list[tuple[str, int]] = []
    for node in ast.walk(execute):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.append((node.func.id, node.lineno))
            elif isinstance(node.func, ast.Attribute):
                calls.append((node.func.attr, node.lineno))
    def first_call(name: str) -> int:
        positions = [line for function, line in calls if function == name]
        return min(positions) if positions else 10**9
    if first_call("verify_preflight_for_execute") >= first_call("verify_hash_guards"):
        errors.append("PREFLIGHT_NOT_BEFORE_HASH_GUARDS")
    if first_call("verify_hash_guards") >= first_call("verify_execution_unlock_evidence"):
        errors.append("HASH_GUARDS_NOT_BEFORE_UNLOCK_PARSE")
    if first_call("verify_execution_unlock_evidence") >= first_call("configure_modules"):
        errors.append("UNLOCK_VERIFY_NOT_BEFORE_EXECUTION_SETUP")
    if first_call("enforce_post_11b_candidate_load_hard_gate") == 10**9:
        errors.append("POST_11B_HARD_GATE_CALL_MISSING")
    if first_call("enforce_post_11b_candidate_load_hard_gate") >= first_call("extract_candidate_fastqs"):
        errors.append("POST_11B_GATE_NOT_BEFORE_CANDIDATE_EXTRACTION")
    if first_call("enforce_post_11b_candidate_load_hard_gate") >= first_call("run_caller_materializer"):
        errors.append("POST_11B_GATE_NOT_BEFORE_CALLER_MATERIALIZER")
    execute_source = function_source(generated_source, execute)
    authorization_position = execute_source.find("if not FULL_EXECUTION_AUTHORIZED")
    confirm_position = execute_source.find("if confirm_run_id != RUN_ID")
    if authorization_position < 0 or confirm_position < 0 or authorization_position > confirm_position:
        errors.append("EXECUTION_AUTHORIZATION_GUARD_NOT_EARLY")
    return errors


def mutate_once(source: str, old: str, new: str, name: str) -> str:
    count = source.count(old)
    if count != 1:
        raise BuildError(f"mutation {name} expected anchor once, observed {count}")
    return source.replace(old, new, 1)


def negative_mutation_tests(
    locked_source: str, generated_source: str, unlock_sha256: str
) -> list[dict[str, Any]]:
    tests = [
        ("shards_144_to_60", "SHARDS = 144", "SHARDS = 60", "CONST_MISMATCH:SHARDS"),
        (
            "analysis_id_to_mapping_id",
            f"ANALYSIS_RUN_ID = '{ANALYSIS_RUN_ID}'",
            f"ANALYSIS_RUN_ID = '{MAPPING_RUN_ID}'",
            "CONST_MISMATCH:ANALYSIS_RUN_ID",
        ),
        (
            "hard_max_plus_one",
            "POST_11B_MAX_CANDIDATE_ROWS_PER_SHARD = 164204",
            "POST_11B_MAX_CANDIDATE_ROWS_PER_SHARD = 164205",
            "CONST_MISMATCH:POST_11B_MAX_CANDIDATE_ROWS_PER_SHARD",
        ),
        (
            "concurrency_12_to_11",
            "STAGE_WORKERS = 12",
            "STAGE_WORKERS = 11",
            "CONST_MISMATCH:STAGE_WORKERS",
        ),
        (
            "execution_relocked",
            "FULL_EXECUTION_AUTHORIZED = True",
            "FULL_EXECUTION_AUTHORIZED = False",
            "CONST_MISMATCH:FULL_EXECUTION_AUTHORIZED",
        ),
        (
            "hard_gate_call_removed",
            "        enforce_post_11b_candidate_load_hard_gate(shards)",
            "        # mutation removed hard gate",
            "POST_11B_HARD_GATE_CALL_MISSING",
        ),
        (
            "preflight_execute_false",
            '("execute_authorized", "true")',
            '("execute_authorized", "false")',
            "PREFLIGHT_EXECUTE_TRUE_MISSING",
        ),
        (
            "unlock_hash_changed",
            f'EXECUTION_UNLOCK_CONTRACT_SHA256 = "{unlock_sha256}"',
            'EXECUTION_UNLOCK_CONTRACT_SHA256 = "' + ("0" * 64) + '"',
            "CONST_MISMATCH:EXECUTION_UNLOCK_CONTRACT_SHA256",
        ),
        (
            "contract_heading_regressed",
            "# RNA-TR-Scout Stage 15C full-scale execution contract v0.1.4",
            "# RNA-TR-Scout Stage 15C full-scale execution contract v0.1.0",
            "STALE_CONTRACT_HEADING_V010",
        ),
        (
            "stale_60_comment_reintroduced",
            "# execution-only shard count to 144. With 12 concurrent shard pipelines this",
            "# execution-only shard count to 60. With 12 concurrent shard pipelines this",
            "STALE_60_SHARD_COMMENT",
        ),
        (
            "execute_unlock_verify_removed",
            "    verify_hash_guards()\n    verify_execution_unlock_evidence()\n    verify_stage15b_evidence()",
            "    verify_hash_guards()\n    verify_stage15b_evidence()",
            "UNLOCK_VERIFY_NOT_BEFORE_EXECUTION_SETUP",
        ),
        (
            "locked_bundle_hash_changed",
            f'LOCKED_PREFLIGHT_EVIDENCE_BUNDLE_SHA256 = "{LOCKED_PREFLIGHT_BUNDLE_SHA256}"',
            'LOCKED_PREFLIGHT_EVIDENCE_BUNDLE_SHA256 = "' + ("1" * 64) + '"',
            "CONST_MISMATCH:LOCKED_PREFLIGHT_EVIDENCE_BUNDLE_SHA256",
        ),
    ]
    rows: list[dict[str, Any]] = []
    for name, old, new, expected in tests:
        mutated = mutate_once(generated_source, old, new, name)
        errors = audit_runner_source(locked_source, mutated, unlock_sha256)
        passed = any(expected in error for error in errors)
        rows.append(
            {
                "test": name,
                "expected_rejection": expected,
                "auditor_errors": ";".join(errors) or ".",
                "status": "PASS" if passed else "FAIL",
            }
        )
        if not passed:
            raise BuildError(f"negative mutation test not rejected: {name}: {errors}")
    return rows


def import_generated_runner(path: Path):
    module_name = "rnatr_stage15c_execution_unlocked_runner_selftest"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise BuildError(f"cannot import generated runner: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module_name, module


def create_synthetic_preflight_fixture(module: Any, root: Path, runner_path: Path) -> None:
    root.mkdir()
    artifacts = {
        "mapping_artifact_integrity.tsv": b"field\tvalue\nsynthetic\tPASS\n",
        "resource_model.tsv": b"metric\tvalue\nsynthetic\tPASS\n",
        "source_and_contract_guards.tsv": b"field\tvalue\nsynthetic\tPASS\n",
    }
    for name, payload in artifacts.items():
        (root / name).write_bytes(payload)
    qc_rows = [
        ("stage_version", module.VERSION),
        ("run_id", module.RUN_ID),
        ("input_fastq_reads", str(module.EXPECTED_READS)),
        ("input_bam_sha256", module.EXPECTED_BAM_SHA256),
        ("fastq_duplicate_id_rows", "0"),
        ("shards", str(module.SHARDS)),
        ("caller_pipeline_workers", str(module.CALLER_PIPELINE_WORKERS)),
        ("validator_workers", str(module.VALIDATOR_WORKERS)),
        ("logical_cpus", str(os.cpu_count() or 0)),
        ("memory_readiness", "PASS"),
        ("storage_readiness", "PASS"),
        ("runtime_projection_readiness", "PASS_STRICT"),
        ("active_pipeline_modified", "false"),
        ("ssot_modified", "false"),
        ("full_5_31m_run_started", "false"),
        ("execution_unlock_contract_sha256", module.EXECUTION_UNLOCK_CONTRACT_SHA256),
        ("locked_preflight_bundle_sha256", module.LOCKED_PREFLIGHT_EVIDENCE_BUNDLE_SHA256),
        ("locked_preflight_qc_sha256", module.LOCKED_PREFLIGHT_QC_SHA256),
        ("execute_authorized", "true"),
        ("runner_execution_locked", "false"),
        ("preflight_status", "PASS_EXECUTION_AUTHORIZED"),
        ("runner_sha256", sha256_file(runner_path)),
    ]
    with (root / "stage15c_fullscale_runner_preflight.qc.tsv").open(
        "w", encoding="utf-8"
    ) as handle:
        handle.write("metric\tvalue\n")
        for key, value in qc_rows:
            handle.write(f"{key}\t{value}\n")
    manifest_rows = []
    for name in (
        "mapping_artifact_integrity.tsv",
        "resource_model.tsv",
        "source_and_contract_guards.tsv",
        "stage15c_fullscale_runner_preflight.qc.tsv",
    ):
        path = root / name
        manifest_rows.append(
            {"artifact": name, "bytes": path.stat().st_size, "sha256": sha256_file(path)}
        )
    write_tsv(root / "artifact_manifest.tsv", manifest_rows, ["artifact", "bytes", "sha256"])


def dynamic_tests(
    runner_path: Path,
    temp_unlock_contract: Path,
    temp_preflight_bundle: Path,
) -> list[dict[str, Any]]:
    module_name, module = import_generated_runner(runner_path)
    try:
        rows: list[dict[str, Any]] = []
        passed, observed, offenders = module.candidate_load_gate_decision(
            [POST_11B_HARD_MAX] * SHARDS
        )
        if not passed or observed != POST_11B_HARD_MAX or offenders:
            raise BuildError("candidate hard-gate boundary accept test failed")
        rows.append({"test": "candidate_gate_accept_at_max", "status": "PASS", "detail": str(observed)})
        passed, observed, offenders = module.candidate_load_gate_decision(
            [POST_11B_HARD_MAX] * (SHARDS - 1) + [POST_11B_HARD_MAX + 1]
        )
        if passed or observed != POST_11B_HARD_MAX + 1 or offenders != [SHARDS - 1]:
            raise BuildError("candidate hard-gate max+1 reject test failed")
        rows.append({"test": "candidate_gate_reject_above_max", "status": "PASS", "detail": str(observed)})

        architecture = module.verify_stage15c_144_evidence()
        if architecture.get("validated_shards") != SHARDS:
            raise BuildError("generated runner real architecture evidence test failed")
        rows.append({"test": "real_144shard_evidence_binding", "status": "PASS", "detail": f"shards={SHARDS}"})

        original_unlock = module.EXECUTION_UNLOCK_CONTRACT
        original_bundle = module.LOCKED_PREFLIGHT_EVIDENCE_BUNDLE
        module.EXECUTION_UNLOCK_CONTRACT = temp_unlock_contract
        module.LOCKED_PREFLIGHT_EVIDENCE_BUNDLE = temp_preflight_bundle
        try:
            unlock = module.verify_execution_unlock_evidence()
        finally:
            module.EXECUTION_UNLOCK_CONTRACT = original_unlock
            module.LOCKED_PREFLIGHT_EVIDENCE_BUNDLE = original_bundle
        if unlock.get("full_execution_authorized") is not True:
            raise BuildError("generated runner unlock evidence test failed")
        rows.append({"test": "real_locked_preflight_and_unlock_evidence_binding", "status": "PASS", "detail": unlock["unlock_contract_sha256"]})

        fixture_root = runner_path.parent / "synthetic_v014_preflight"
        create_synthetic_preflight_fixture(module, fixture_root, runner_path)
        original_preflight_root = module.PREFLIGHT_ROOT
        module.PREFLIGHT_ROOT = fixture_root
        try:
            module.verify_preflight_for_execute(runner_path)
            rows.append({"test": "synthetic_exact_preflight_integrity_accept", "status": "PASS", "detail": "accepted"})
            tampered = fixture_root / "resource_model.tsv"
            tampered.write_bytes(tampered.read_bytes() + b"tamper\n")
            rejected = False
            try:
                module.verify_preflight_for_execute(runner_path)
            except module.RunnerError:
                rejected = True
            if not rejected:
                raise BuildError("tampered synthetic preflight was not rejected")
            rows.append({"test": "synthetic_preflight_tamper_reject", "status": "PASS", "detail": "rejected"})
        finally:
            module.PREFLIGHT_ROOT = original_preflight_root

        wrong_confirm_rejected = False
        try:
            module.execute("WRONG_RUN_ID")
        except module.RunnerError as exc:
            wrong_confirm_rejected = "--confirm-run-id" in str(exc)
        if not wrong_confirm_rejected:
            raise BuildError("wrong formal run ID was not rejected before execution")
        rows.append({"test": "wrong_confirm_run_id_rejected", "status": "PASS", "detail": "rejected"})

        if module.FULL_EXECUTION_AUTHORIZED is not True:
            raise BuildError("generated runner authorization constant is not true")
        rows.append({"test": "execution_authorization_constant", "status": "PASS", "detail": "true"})
        return rows
    finally:
        sys.modules.pop(module_name, None)


def artifact_manifest(root: Path) -> None:
    output = root / "artifact_manifest.tsv"
    rows = []
    for path in sorted(item for item in root.rglob("*") if item.is_file() and item != output):
        rows.append(
            {
                "artifact": str(path.relative_to(root)),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    write_tsv(output, rows, ["artifact", "bytes", "sha256"])


def make_bundle(root: Path, destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name("." + destination.name + f".part.{os.getpid()}")
    with tarfile.open(temporary, "w:gz", format=tarfile.PAX_FORMAT) as archive:
        archive.add(root, arcname=root.name)
    os.replace(temporary, destination)
    digest = sha256_file(destination)
    Path(str(destination) + ".sha256").write_text(
        f"{digest}  {destination.name}\n", encoding="utf-8"
    )
    return digest


def build() -> int:
    started = time.time()
    locked_runner = locate_locked_runner()
    bundle_members = verify_locked_preflight_bundle()
    evidence = verify_project_evidence()
    locked_source = locked_runner.read_text(encoding="utf-8")
    bundle_runner = bundle_members[
        f"{BUNDLE_ROOT}/rnatr_stage15c_run_full5312696_bam_to_final_v0.1.3.py"
    ]
    if bundle_runner != locked_runner.read_bytes():
        raise BuildError("locked runner in preflight bundle differs from project runner")

    unlock_payload = make_unlock_contract(evidence)
    unlock_sha = sha256_bytes(unlock_payload)
    generated = transform_runner(locked_source, unlock_sha)
    compile(generated, str(RUNNER_DOWNLOAD), "exec")
    audit_errors = audit_runner_source(locked_source, generated, unlock_sha)
    if audit_errors:
        raise BuildError("generated runner audit failed: " + ";".join(audit_errors))
    mutation_rows = negative_mutation_tests(locked_source, generated, unlock_sha)

    work = Path(tempfile.mkdtemp(prefix="rnatr_stage15c_unlock_build_"))
    package = work / "rnatr_stage15c_execution_unlocked_full_runner_build_v0.1.4"
    package.mkdir()
    try:
        runner_bytes = generated.encode("utf-8")
        runner_path = package / RUNNER_DOWNLOAD.name
        atomic_write(runner_path, runner_bytes, 0o755)
        unlock_path = package / UNLOCK_CONTRACT.name
        atomic_write(unlock_path, unlock_payload, 0o644)
        evidence_dir = package / "evidence"
        evidence_dir.mkdir()
        bundle_copy = evidence_dir / LOCKED_PREFLIGHT_BUNDLE.name
        shutil.copy2(LOCKED_PREFLIGHT_BUNDLE, bundle_copy)

        dynamic_rows = dynamic_tests(runner_path, unlock_path, bundle_copy)
        # Dynamic imports and synthetic integrity fixtures are test work products,
        # not release artifacts. Preserve only the versioned TSV test results.
        shutil.rmtree(package / "__pycache__", ignore_errors=True)
        shutil.rmtree(package / "synthetic_v014_preflight", ignore_errors=True)
        runner_sha_first = sha256_file(runner_path)
        runner_sha_second = sha256_file(runner_path)
        if runner_sha_first != runner_sha_second:
            raise BuildError("final runner hash changed between final read passes")

        source_rows = []
        for path, digest in (
            (locked_runner, LOCKED_RUNNER_SHA256),
            (LOCKED_RUNNER_LOCK, LOCKED_RUNNER_LOCK_SHA256),
            (LOCKED_PREFLIGHT_BUNDLE, LOCKED_PREFLIGHT_BUNDLE_SHA256),
            (LOCKED_PREFLIGHT_SIDECAR, LOCKED_PREFLIGHT_SIDECAR_SHA256),
            (LOCKED_PREFLIGHT_QC, LOCKED_PREFLIGHT_QC_SHA256),
            (LOCKED_PREFLIGHT_RESOURCE, LOCKED_PREFLIGHT_RESOURCE_SHA256),
            (LOCKED_PREFLIGHT_SOURCE_GUARDS, LOCKED_PREFLIGHT_SOURCE_GUARDS_SHA256),
            (LOCKED_PREFLIGHT_MAPPING_INTEGRITY, LOCKED_PREFLIGHT_MAPPING_INTEGRITY_SHA256),
            (ARCH144_CONTRACT, ARCH144_CONTRACT_SHA256),
            (ARCH144_QC, ARCH144_QC_SHA256),
            (ARCH144_RESOURCE, ARCH144_RESOURCE_SHA256),
        ):
            observed = sha256_file(path)
            source_rows.append(
                {
                    "artifact": str(path),
                    "expected_sha256": digest,
                    "observed_sha256": observed,
                    "status": "PASS" if observed == digest else "FAIL",
                }
            )
        write_tsv(
            package / "source_and_authorization_guards.tsv",
            source_rows,
            ["artifact", "expected_sha256", "observed_sha256", "status"],
        )
        write_tsv(
            package / "negative_static_mutation_tests.tsv",
            mutation_rows,
            ["test", "expected_rejection", "auditor_errors", "status"],
        )
        write_tsv(
            package / "dynamic_safety_and_evidence_tests.tsv",
            dynamic_rows,
            ["test", "status", "detail"],
        )

        qc_rows = [
            ("builder_version", BUILDER_VERSION),
            ("runner_version", RUNNER_VERSION),
            ("analysis_run_id", ANALYSIS_RUN_ID),
            ("mapping_run_id", MAPPING_RUN_ID),
            ("locked_runner_sha256", LOCKED_RUNNER_SHA256),
            ("locked_preflight_bundle_sha256", LOCKED_PREFLIGHT_BUNDLE_SHA256),
            ("locked_preflight_qc_sha256", LOCKED_PREFLIGHT_QC_SHA256),
            ("execution_unlock_contract_sha256", unlock_sha),
            ("generated_runner_sha256", runner_sha_first),
            ("generated_runner_bytes", runner_path.stat().st_size),
            ("read_coherent_shards", SHARDS),
            ("active_shard_concurrency", CONCURRENCY),
            ("caller_workers_per_shard", CALLER_WORKERS_PER_SHARD),
            ("validator_workers", VALIDATOR_WORKERS),
            ("post_11b_candidate_rows_per_shard_hard_max", POST_11B_HARD_MAX),
            ("locked_preflight_review", "PASS"),
            ("bundle_member_integrity", "PASS"),
            ("v013_lock_contract_semantics", "PASS"),
            ("control_plane_only_function_diff", "PASS"),
            ("static_contract_audit", "PASS"),
            ("negative_mutation_tests", "PASS"),
            ("dynamic_safety_and_evidence_tests", "PASS"),
            ("execution_contract_heading_version", "v0.1.4"),
            ("stale_60_shard_comment_present", "false"),
            ("full_execution_authorized_in_generated_runner", "true"),
            ("exact_v014_preflight_required_before_execute", "true"),
            ("full_5_31m_run_started", "false"),
            ("active_pipeline_modified", "false"),
            ("ssot_modified", "false"),
            ("core_schema_modified", "false"),
            ("audit_status", "PASS"),
            ("next_gate", "RUN_V0.1.4_PREFLIGHT_ONLY_THEN_REVIEW_BEFORE_EXECUTE"),
            ("elapsed_seconds", f"{time.time() - started:.6f}"),
        ]
        write_metrics(package / "execution_unlocked_runner_build.qc.tsv", qc_rows)

        document = f'''# RNA-TR-Scout Stage 15C execution-unlocked full runner build v0.1.4

This build authorizes only the clean empirical `{ANALYSIS_RUN_ID}` BAM-to-final run. It is derived from the exact v0.1.3 locked runner (`{LOCKED_RUNNER_SHA256}`) and requires the exact locked preflight bundle (`{LOCKED_PREFLIGHT_BUNDLE_SHA256}`).

The validated execution architecture is unchanged: 144 deterministic read-coherent shards, active concurrency 12, caller workers 2 per active shard, validator workers 3, external sort 512M, and a mandatory post-11b hard maximum of {POST_11B_HARD_MAX:,} candidate rows per shard. The gate must pass before candidate extraction and before caller/materializer execution.

The builder verifies that every scientific-processing function inherited from v0.1.3 remains byte-identical. Only the versioned output/provenance paths, execution authorization, unlock verification, final-preflight authorization fields, and success/failure evidence bundles are changed.

The generated v0.1.4 runner is execution-authorized, but execution is still impossible until the exact same v0.1.4 bytes complete `--preflight`. The execute path then requires the exact formal run ID and re-verifies the v0.1.4 preflight artifact manifest, runner SHA-256, unlock contract, locked v0.1.3 evidence, source guards, input binding, memory/storage model, and large input hashes before creating a full-run result root.

Execution-unlock contract SHA-256: `{unlock_sha}`
Generated runner SHA-256: `{runner_sha_first}`
'''
        atomic_write(
            package / "RNA_TR_Scout_execution_unlocked_full_runner_build_v0.1.4.md",
            document.encode("utf-8"),
            0o644,
        )
        shutil.copy2(
            Path(__file__).resolve(),
            package / "rnatr_stage15c_build_execution_unlocked_full_runner_v014.py",
        )
        artifact_manifest(package)

        builder_bytes = Path(__file__).resolve().read_bytes()
        install_statuses = {
            "builder": install_exact_bytes(builder_bytes, BUILDER_INSTALL, 0o755),
            "runner": install_exact_bytes(runner_bytes, RUNNER_INSTALL, 0o755),
            "unlock_contract": install_exact_bytes(unlock_payload, UNLOCK_CONTRACT, 0o644),
            "locked_preflight_evidence_bundle": install_exact_bytes(
                LOCKED_PREFLIGHT_BUNDLE.read_bytes(), PREFLIGHT_EVIDENCE_INSTALL, 0o644
            ),
            "build_qc": install_exact_bytes(
                (package / "execution_unlocked_runner_build.qc.tsv").read_bytes(),
                BUILD_QC_ROOT / "execution_unlocked_runner_build.qc.tsv",
                0o644,
            ),
            "negative_tests": install_exact_bytes(
                (package / "negative_static_mutation_tests.tsv").read_bytes(),
                BUILD_QC_ROOT / "negative_static_mutation_tests.tsv",
                0o644,
            ),
            "dynamic_tests": install_exact_bytes(
                (package / "dynamic_safety_and_evidence_tests.tsv").read_bytes(),
                BUILD_QC_ROOT / "dynamic_safety_and_evidence_tests.tsv",
                0o644,
            ),
            "doc": install_exact_bytes(
                (package / "RNA_TR_Scout_execution_unlocked_full_runner_build_v0.1.4.md").read_bytes(),
                DOC_INSTALL,
                0o644,
            ),
        }
        write_tsv(
            package / "project_installation.tsv",
            ({"artifact": key, "status": value} for key, value in install_statuses.items()),
            ["artifact", "status"],
        )

        download_status = install_exact_bytes(runner_bytes, RUNNER_DOWNLOAD, 0o755)
        install_exact_bytes(
            f"{runner_sha_first}  {RUNNER_DOWNLOAD.name}\n".encode("utf-8"),
            Path(str(RUNNER_DOWNLOAD) + ".sha256"),
            0o644,
        )
        artifact_manifest(package)
        bundle_sha = make_bundle(package, SUCCESS_BUNDLE)

        print("===== RNA-TR-Scout Stage 15C execution-unlocked runner build =====")
        print("build_status\tPASS")
        print(f"analysis_run_id\t{ANALYSIS_RUN_ID}")
        print(f"mapping_run_id\t{MAPPING_RUN_ID}")
        print(f"read_coherent_shards\t{SHARDS}")
        print(f"active_shard_concurrency\t{CONCURRENCY}")
        print(f"post_11b_candidate_rows_per_shard_hard_max\t{POST_11B_HARD_MAX}")
        print("locked_preflight_review\tPASS")
        print("control_plane_only_function_diff\tPASS")
        print("negative_mutation_tests\tPASS")
        print("dynamic_safety_and_evidence_tests\tPASS")
        print("full_execution_authorized_in_runner\ttrue")
        print("exact_v014_preflight_required_before_execute\ttrue")
        print("full_5_31m_run_started\tfalse")
        print("active_pipeline_modified\tfalse")
        print("ssot_modified\tfalse")
        print(f"EXECUTION_UNLOCK_CONTRACT_SHA256\t{unlock_sha}")
        print(f"RUNNER\t{RUNNER_DOWNLOAD}")
        print(f"RUNNER_SHA256\t{runner_sha_first}")
        print(f"RUNNER_DOWNLOAD_INSTALLATION\t{download_status}")
        print(f"OUTPUT_BUNDLE\t{SUCCESS_BUNDLE}")
        print(f"OUTPUT_BUNDLE_SHA256\t{bundle_sha}")
        print("NEXT_GATE\tRUN_GENERATED_V0.1.4_WITH_--preflight_ONLY")
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build and audit the Stage15C v0.1.4 execution-unlocked runner "
            "from the exact v0.1.3 locked runner and reviewed preflight evidence."
        )
    )
    parser.parse_args()
    try:
        return build()
    except Exception as exc:
        print(f"BUILD_FAIL\t{type(exc).__name__}\t{exc}", file=sys.stderr)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
