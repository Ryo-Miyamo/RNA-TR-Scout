#!/usr/bin/env python3
from __future__ import annotations

import ast
import csv
import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any, Iterable

BUILDER_VERSION = "rnatr_stage15c_build_runtime_bound_full_runner_v0.1.5"
RUNNER_VERSION = "rnatr_stage15c_full5312696_bam_to_final_v0.1.5"
AMENDMENT_SCHEMA = "rnatr.runtime_script_binding_amendment.v1"
PROJECT_ROOT = Path("/mnt/intelssd/rnatr_project")
DOWNLOADS = Path.home() / "Downloads"

ANALYSIS_RUN_ID = "ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1"
MAPPING_RUN_ID = "ENCSR307SHM_full5312696_mm2splice_v1"
OLD_TEMPLATE_RUN_ID = "ENCSR307SHM_stage15a500k_seed20260809_mm2splice_v1"
EXPECTED_READS = 5_312_696
EXPECTED_ALIGNMENT_RECORDS = 9_774_085
SHARDS = 144
CONCURRENCY = 12
CALLER_WORKERS_PER_SHARD = 2
VALIDATOR_WORKERS = 3
SORT_BUFFER = "512M"
POST_11B_HARD_MAX = 164_204

V014_RUNNER_PROJECT = PROJECT_ROOT / "scripts/rnatr_stage15c_run_full5312696_bam_to_final_v0.1.4.py"
V014_RUNNER_DOWNLOAD = DOWNLOADS / "rnatr_stage15c_run_full5312696_bam_to_final_v014.py"
V014_RUNNER_SHA256 = "d4a91324d9549991c00c24f2aa610e02bd33d7525271ce3139093d30c17ea3cf"

V014_PREFLIGHT_ROOT = (
    PROJECT_ROOT / "qc/15_stage15c_fullscale_runner_preflight" / ANALYSIS_RUN_ID / "v0.1.4"
)
V014_PREFLIGHT_QC = V014_PREFLIGHT_ROOT / "stage15c_fullscale_runner_preflight.qc.tsv"
V014_PREFLIGHT_QC_SHA256 = "5279b4f3ae00e58853aae825bfe7034c3cb23942bd57a0f28611a6936cf38118"
V014_PREFLIGHT_RESOURCE = V014_PREFLIGHT_ROOT / "resource_model.tsv"
V014_PREFLIGHT_RESOURCE_SHA256 = "0244056d99f180cf3b9a1154f39a4aa6f5c41d1c1735c873d81293a2df494532"
V014_PREFLIGHT_SOURCE_GUARDS = V014_PREFLIGHT_ROOT / "source_and_contract_guards.tsv"
V014_PREFLIGHT_SOURCE_GUARDS_SHA256 = "7889d249beb36853c90c1d1ceee2277ea5bdbfd765d347bb995b40e0c716b9c4"
V014_PREFLIGHT_MAPPING_INTEGRITY = V014_PREFLIGHT_ROOT / "mapping_artifact_integrity.tsv"
V014_PREFLIGHT_MAPPING_INTEGRITY_SHA256 = "72796145d4a7e4a7318aa708726ece0fddbb3410d6b2d3df2f49591a00c1d15c"
V014_PREFLIGHT_ARTIFACT_MANIFEST = V014_PREFLIGHT_ROOT / "artifact_manifest.tsv"
V014_PREFLIGHT_ARTIFACT_MANIFEST_SHA256 = "3cedf283efa6678be93436aa913d7ddaefe7d83be3f642608610585135fc2f7a"

V014_UNLOCK_CONTRACT = (
    PROJECT_ROOT / "metadata/stage15c/execution_unlocked_full_runner_v0.1.4"
    / "rnatr_stage15c_full_runner_execution_unlock_v0.1.4.json"
)
V014_UNLOCK_CONTRACT_SHA256 = "a3d9474208f3519c19d3b48e948e0fc4c9b7fa14b0764446d22a67c37c4de014"

V014_FAILURE_BUNDLE = DOWNLOADS / "rnatr_stage15c_full_empirical_run_v0.1.4_failure.tar.gz"
V014_FAILURE_BUNDLE_SHA256 = "fc389f2c5c36b05e93eed870d5e7a757c6954e7eae691360e5c59c3055a6bc3f"
V014_RESULT_ROOT = (
    PROJECT_ROOT / "results/15_stage15c_fullscale_bam_to_final" / ANALYSIS_RUN_ID / "v0.1.4"
)
V014_QC_ROOT = (
    PROJECT_ROOT / "qc/15_stage15c_fullscale_bam_to_final" / ANALYSIS_RUN_ID / "v0.1.4"
)
V014_FAILURE_RECORD = V014_QC_ROOT / "stage15c_full_empirical_run.failure.txt"
V014_FAILURE_RECORD_SHA256 = "8d9ba3c828bba7243c489874813b6669b54a2c6d98bc310cc6799f5e93ab52e7"
V014_FAILURE_CONTEXT = V014_QC_ROOT / "stage15c_fullscale_failed_run_context.tsv"
V014_FAILURE_CONTEXT_SHA256 = "968968f877253660f77a5be06d0b3e303b258af3aa4503209419e3fbd76177d7"
V014_SHARD_MANIFEST = V014_QC_ROOT / "stage15c_fullscale_shards.fast.tsv"
V014_SHARD_MANIFEST_SHA256 = "7204bfd215f5443bd6abddf859fdc0a1b31e0d0367eec36dd5ab0d40a4c3b13a"

ORIGINAL_SOURCE_SPECS: dict[str, tuple[Path, str, str]] = {
    "11b": (
        PROJECT_ROOT / "scripts/11b_extract_alignment_segments_and_target_candidates.stage15a500k_runid_v0.1.0.sh",
        "ccf37ebbe71451f12d113cb4148e5415ad7cbcd59ef954b7b7dd7a6b69078075",
        "11b_extract_alignment_segments_and_target_candidates.stage15c_full5312696_runid_bound_v0.1.5.sh",
    ),
    "11d3": (
        PROJECT_ROOT / "scripts/11d3_project_targets_to_raw_reads.stage15a500k_runid_v0.1.0.sh",
        "d7411df47e54e672ea3c838746402d35787c0d1c2fe0af628e7a7f36d98ea203",
        "11d3_project_targets_to_raw_reads.stage15c_full5312696_runid_bound_v0.1.5.sh",
    ),
    "11e": (
        PROJECT_ROOT / "scripts/11e_prepare_motif_scan_jobs.stage15a500k_runid_v0.1.0.sh",
        "b648b24f22c96fa5625baf09313500c2ca54668ed318ed0aa49570a10c743e3b",
        "11e_prepare_motif_scan_jobs.stage15c_full5312696_runid_bound_v0.1.5.sh",
    ),
}

BOUND_SOURCE_ROOT = PROJECT_ROOT / "scripts/stage15c/full5312696_runid_bound_v0.1.5"
META_ROOT = PROJECT_ROOT / "metadata/stage15c/runtime_script_binding_amendment_v0.1.5"
AMENDMENT_CONTRACT = META_ROOT / "rnatr_stage15c_runtime_script_binding_amendment_v0.1.5.json"
BUILD_QC_ROOT = (
    PROJECT_ROOT / "qc/15_stage15c_runtime_bound_runner_build" / ANALYSIS_RUN_ID / "v0.1.5"
)
BUILDER_INSTALL = PROJECT_ROOT / "scripts/rnatr_stage15c_build_runtime_bound_full_runner_v0.1.5.py"
RUNNER_INSTALL = PROJECT_ROOT / "scripts/rnatr_stage15c_run_full5312696_bam_to_final_v0.1.5.py"
DOC_INSTALL = PROJECT_ROOT / "docs/stage15c/RNA_TR_Scout_runtime_script_binding_amendment_v0.1.5.md"
RUNNER_DOWNLOAD = DOWNLOADS / "rnatr_stage15c_run_full5312696_bam_to_final_v015.py"
SUCCESS_BUNDLE = DOWNLOADS / "rnatr_stage15c_runtime_bound_full_runner_build_v0.1.5.tar.gz"
FAILURE_BUNDLE = DOWNLOADS / "rnatr_stage15c_runtime_bound_full_runner_build_v0.1.5_failure.tar.gz"

V015_RESULT_ROOT = (
    PROJECT_ROOT / "results/15_stage15c_fullscale_bam_to_final" / ANALYSIS_RUN_ID / "v0.1.5"
)
V015_QC_ROOT = (
    PROJECT_ROOT / "qc/15_stage15c_fullscale_bam_to_final" / ANALYSIS_RUN_ID / "v0.1.5"
)
V015_PREFLIGHT_ROOT = (
    PROJECT_ROOT / "qc/15_stage15c_fullscale_runner_preflight" / ANALYSIS_RUN_ID / "v0.1.5"
)

SCIENTIFIC_FUNCTIONS = {
    "load_caller_totals_full",
    "derive_expected_final_rows_full",
    "aggregate_materializer_qc_full",
    "create_shards",
    "check_memavailable",
    "run_wave_stage",
    "partition_inputs",
    "load_candidate_counts",
    "candidate_load_gate_decision",
    "enforce_post_11b_candidate_load_hard_gate",
    "extract_candidate_fastqs",
    "run_fast_motif_jobs",
    "load_projection_counts",
    "run_caller_materializer",
    "run_generic_validator",
    "run_memory_bounded_validator",
    "run_validators",
    "sum_path_bytes",
    "temp_snapshot",
    "maximum_rss",
    "checkpoint_manifest",
    "post_timer_shard_audit",
}


class BuildError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


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


def insert_before_once(text: str, anchor: str, payload: str, label: str) -> str:
    return replace_once(text, anchor, payload + anchor, label)


def top_level_constants(source: str) -> dict[str, Any]:
    tree = ast.parse(source)
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


def function_sources(source: str) -> dict[str, str]:
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    result: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            result[node.name] = "".join(lines[node.lineno - 1 : node.end_lineno])
    return result


def verify_v014_evidence() -> dict[str, Any]:
    ensure_exact(V014_RUNNER_PROJECT, V014_RUNNER_SHA256)
    if V014_RUNNER_DOWNLOAD.exists():
        ensure_exact(V014_RUNNER_DOWNLOAD, V014_RUNNER_SHA256)
    for path, expected in (
        (V014_PREFLIGHT_QC, V014_PREFLIGHT_QC_SHA256),
        (V014_PREFLIGHT_RESOURCE, V014_PREFLIGHT_RESOURCE_SHA256),
        (V014_PREFLIGHT_SOURCE_GUARDS, V014_PREFLIGHT_SOURCE_GUARDS_SHA256),
        (V014_PREFLIGHT_MAPPING_INTEGRITY, V014_PREFLIGHT_MAPPING_INTEGRITY_SHA256),
        (V014_PREFLIGHT_ARTIFACT_MANIFEST, V014_PREFLIGHT_ARTIFACT_MANIFEST_SHA256),
        (V014_UNLOCK_CONTRACT, V014_UNLOCK_CONTRACT_SHA256),
        (V014_FAILURE_BUNDLE, V014_FAILURE_BUNDLE_SHA256),
        (V014_FAILURE_RECORD, V014_FAILURE_RECORD_SHA256),
        (V014_FAILURE_CONTEXT, V014_FAILURE_CONTEXT_SHA256),
        (V014_SHARD_MANIFEST, V014_SHARD_MANIFEST_SHA256),
    ):
        ensure_exact(path, expected)

    preflight = read_two_column(V014_PREFLIGHT_QC)
    for key, expected in {
        "stage_version": "rnatr_stage15c_full5312696_bam_to_final_v0.1.4",
        "run_id": ANALYSIS_RUN_ID,
        "input_fastq_reads": str(EXPECTED_READS),
        "shards": str(SHARDS),
        "caller_pipeline_workers": str(CONCURRENCY),
        "validator_workers": str(VALIDATOR_WORKERS),
        "post_11b_candidate_rows_per_shard_hard_max": str(POST_11B_HARD_MAX),
        "execute_authorized": "true",
        "runner_execution_locked": "false",
        "preflight_status": "PASS_EXECUTION_AUTHORIZED",
        "full_5_31m_run_started": "false",
    }.items():
        if preflight.get(key) != expected:
            raise BuildError(f"v0.1.4 preflight mismatch {key}: {preflight.get(key)}")

    context = read_two_column(V014_FAILURE_CONTEXT)
    for key, expected in {
        "stage_version": "rnatr_stage15c_full5312696_bam_to_final_v0.1.4",
        "run_id": ANALYSIS_RUN_ID,
        "full_5_31m_run_started": "true",
        "package_final_published": "false",
        "active_pipeline_modified": "false",
        "ssot_modified": "false",
    }.items():
        if context.get(key) != expected:
            raise BuildError(f"v0.1.4 failure-context mismatch {key}: {context.get(key)}")

    failure_text = V014_FAILURE_RECORD.read_text(encoding="utf-8", errors="replace")
    required_failure_fragments = (
        "15C1_11b failed",
        OLD_TEMPLATE_RUN_ID,
        "missing required input",
        "full_5_31m_run_started\ttrue",
        "package_final_published\tfalse",
    )
    for fragment in required_failure_fragments:
        if fragment not in failure_text:
            raise BuildError(f"v0.1.4 failure evidence lacks: {fragment}")

    shard_rows = read_dicts(V014_SHARD_MANIFEST)
    if len(shard_rows) != SHARDS:
        raise BuildError(f"v0.1.4 shard manifest rows {len(shard_rows)} != {SHARDS}")
    alignment_records = sum(int(row["alignment_records"]) for row in shard_rows)
    primary_reads = sum(int(row["primary_reads"]) for row in shard_rows)
    fastq_reads = sum(int(row["full_fastq_reads"]) for row in shard_rows)
    if alignment_records != EXPECTED_ALIGNMENT_RECORDS:
        raise BuildError(f"v0.1.4 partition alignment sum mismatch: {alignment_records}")
    if primary_reads != EXPECTED_READS or fastq_reads != EXPECTED_READS:
        raise BuildError(
            f"v0.1.4 partition read sums mismatch: primary={primary_reads} fastq={fastq_reads}"
        )
    if any(row.get("shard_bai_created") != "false" for row in shard_rows):
        raise BuildError("v0.1.4 shard manifest unexpectedly reports a shard BAI")

    for root in (V015_RESULT_ROOT, V015_QC_ROOT, V015_PREFLIGHT_ROOT):
        if root.exists():
            raise BuildError(f"v0.1.5 output root already exists; preserve/review: {root}")

    return {
        "v014_partition_shards": len(shard_rows),
        "v014_partition_alignment_records": alignment_records,
        "v014_partition_reads": primary_reads,
        "v014_package_final_published": False,
        "v014_partition_reuse_allowed": False,
        "v015_fresh_partition_required": True,
    }


def bind_runtime_sources() -> tuple[dict[str, dict[str, Any]], dict[str, bytes]]:
    records: dict[str, dict[str, Any]] = {}
    payloads: dict[str, bytes] = {}
    for role, (source, expected_sha, filename) in ORIGINAL_SOURCE_SPECS.items():
        ensure_exact(source, expected_sha)
        original = source.read_text(encoding="utf-8")
        old_count = original.count(OLD_TEMPLATE_RUN_ID)
        analysis_count_before = original.count(ANALYSIS_RUN_ID)
        mapping_count_before = original.count(MAPPING_RUN_ID)
        if old_count < 1:
            raise BuildError(f"{role}: no old 500k run-ID anchor in frozen source")
        if analysis_count_before != 0 or mapping_count_before != 0:
            raise BuildError(
                f"{role}: frozen source unexpectedly contains full IDs: "
                f"analysis={analysis_count_before} mapping={mapping_count_before}"
            )
        anchor_lines = [
            line.replace(OLD_TEMPLATE_RUN_ID, ANALYSIS_RUN_ID)
            for line in original.splitlines()
            if OLD_TEMPLATE_RUN_ID in line
        ]
        if len(anchor_lines) < 1:
            raise BuildError(f"{role}: missing run-ID anchor lines")
        bound = original.replace(OLD_TEMPLATE_RUN_ID, ANALYSIS_RUN_ID)
        if bound.count(OLD_TEMPLATE_RUN_ID) != 0:
            raise BuildError(f"{role}: old run ID remained after binding")
        if bound.count(MAPPING_RUN_ID) != 0:
            raise BuildError(f"{role}: mapping run ID appeared during binding")
        if bound.count(ANALYSIS_RUN_ID) != old_count:
            raise BuildError(
                f"{role}: analysis run-ID count mismatch after binding: "
                f"{bound.count(ANALYSIS_RUN_ID)} != {old_count}"
            )
        payload = bound.encode("utf-8")
        with tempfile.NamedTemporaryFile("wb", suffix=".sh", delete=False) as handle:
            handle.write(payload)
            temporary = Path(handle.name)
        try:
            syntax = subprocess.run(
                ["bash", "-n", str(temporary)], text=True, capture_output=True
            )
            if syntax.returncode != 0:
                raise BuildError(f"{role}: bound template bash -n failed: {syntax.stderr}")
        finally:
            temporary.unlink(missing_ok=True)
        bound_path = BOUND_SOURCE_ROOT / filename
        records[role] = {
            "role": role,
            "source_path": str(source),
            "source_sha256": expected_sha,
            "source_old_run_id_occurrences": old_count,
            "source_analysis_run_id_occurrences": analysis_count_before,
            "source_mapping_run_id_occurrences": mapping_count_before,
            "bound_path": str(bound_path),
            "bound_sha256": sha256_bytes(payload),
            "bound_bytes": len(payload),
            "bound_analysis_run_id_occurrences": bound.count(ANALYSIS_RUN_ID),
            "bound_old_run_id_occurrences": 0,
            "bound_mapping_run_id_occurrences": 0,
            "bound_anchor_lines": anchor_lines,
            "bash_syntax_status": "PASS",
        }
        payloads[role] = payload
    return records, payloads


def make_amendment_contract(
    source_records: dict[str, dict[str, Any]],
    failure: dict[str, Any],
) -> bytes:
    payload = {
        "schema": AMENDMENT_SCHEMA,
        "amendment_date": "2026-08-10",
        "builder_version": BUILDER_VERSION,
        "runner_version": RUNNER_VERSION,
        "analysis_run_id": ANALYSIS_RUN_ID,
        "mapping_run_id": MAPPING_RUN_ID,
        "obsolete_template_run_id": OLD_TEMPLATE_RUN_ID,
        "validated_execution": {
            "read_coherent_shards": SHARDS,
            "active_shard_concurrency": CONCURRENCY,
            "caller_workers_per_shard": CALLER_WORKERS_PER_SHARD,
            "validator_workers": VALIDATOR_WORKERS,
            "validator_sort_buffer": SORT_BUFFER,
            "post_11b_candidate_rows_per_shard_hard_max": POST_11B_HARD_MAX,
        },
        "prior_v014_authorization": {
            "runner_sha256": V014_RUNNER_SHA256,
            "preflight_qc_sha256": V014_PREFLIGHT_QC_SHA256,
            "execution_unlock_contract_sha256": V014_UNLOCK_CONTRACT_SHA256,
            "preflight_status": "PASS_EXECUTION_AUTHORIZED",
        },
        "v014_failure": {
            "failure_bundle_sha256": V014_FAILURE_BUNDLE_SHA256,
            "failure_record_sha256": V014_FAILURE_RECORD_SHA256,
            "failure_context_sha256": V014_FAILURE_CONTEXT_SHA256,
            "shard_manifest_sha256": V014_SHARD_MANIFEST_SHA256,
            "cause": "RUNTIME_GENERATED_SHARD_SCRIPTS_RETAINED_500K_ANALYSIS_RUN_ID",
            "partition_completed": True,
            "successful_11b_shards": 0,
            "candidate_extraction_started": False,
            "caller_started": False,
            "materializer_started": False,
            "package_final_published": False,
            **failure,
        },
        "runtime_script_binding": source_records,
        "authorization": {
            "v015_preflight_authorized": True,
            "v015_execution_authorized_after_exact_v015_preflight": True,
            "all_144x3_generated_scripts_must_be_audited_before_partition": True,
            "v014_partition_reuse_allowed": False,
            "v015_fresh_partition_required": True,
            "mapping_included_in_bam_to_final_timer": False,
        },
        "prohibitions": {
            "active_pipeline_modification_allowed": False,
            "ssot_modification_allowed": False,
            "core_schema_modification_allowed": False,
            "caller_modification_allowed": False,
            "materializer_modification_allowed": False,
            "accepted_500k_result_modification_allowed": False,
            "v014_failure_artifact_deletion_allowed_by_builder": False,
        },
    }
    return (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode("utf-8")


def runtime_binding_support_source(
    amendment_sha: str,
    source_records: dict[str, dict[str, Any]],
) -> str:
    original_map = {
        role: record["source_path"] for role, record in source_records.items()
    }
    original_sha = {
        role: record["source_sha256"] for role, record in source_records.items()
    }
    expected_counts = {
        role: record["source_old_run_id_occurrences"]
        for role, record in source_records.items()
    }
    anchors = {role: record["bound_anchor_lines"] for role, record in source_records.items()}
    bound_map = {role: record["bound_path"] for role, record in source_records.items()}
    bound_sha = {role: record["bound_sha256"] for role, record in source_records.items()}
    return f'''

ORIGINAL_RUNTIME_SOURCE_PATHS = {{
    role: Path(path) for role, path in {original_map!r}.items()
}}
ORIGINAL_RUNTIME_SOURCE_SHA256 = {original_sha!r}
BOUND_RUNTIME_SOURCE_PATHS = {{
    role: Path(path) for role, path in {bound_map!r}.items()
}}
BOUND_RUNTIME_SOURCE_SHA256 = {bound_sha!r}
BOUND_RUNTIME_SOURCE_EXPECTED_ANALYSIS_ANCHORS = {expected_counts!r}
BOUND_RUNTIME_SOURCE_ANCHOR_LINES = {anchors!r}
OBSOLETE_TEMPLATE_RUN_ID = {OLD_TEMPLATE_RUN_ID!r}
RUNTIME_SCRIPT_BINDING_AMENDMENT = Path({str(AMENDMENT_CONTRACT)!r})
RUNTIME_SCRIPT_BINDING_AMENDMENT_SHA256 = {amendment_sha!r}
PRIOR_V014_RUNNER = Path({str(V014_RUNNER_PROJECT)!r})
PRIOR_V014_RUNNER_SHA256 = {V014_RUNNER_SHA256!r}
PRIOR_V014_FAILURE_RECORD = Path({str(V014_FAILURE_RECORD)!r})
PRIOR_V014_FAILURE_RECORD_SHA256 = {V014_FAILURE_RECORD_SHA256!r}
PRIOR_V014_FAILURE_CONTEXT = Path({str(V014_FAILURE_CONTEXT)!r})
PRIOR_V014_FAILURE_CONTEXT_SHA256 = {V014_FAILURE_CONTEXT_SHA256!r}
PRIOR_V014_SHARD_MANIFEST = Path({str(V014_SHARD_MANIFEST)!r})
PRIOR_V014_SHARD_MANIFEST_SHA256 = {V014_SHARD_MANIFEST_SHA256!r}


def verify_runtime_script_binding_amendment() -> dict[str, Any]:
    ensure_file(RUNTIME_SCRIPT_BINDING_AMENDMENT)
    if sha256_file(RUNTIME_SCRIPT_BINDING_AMENDMENT) != RUNTIME_SCRIPT_BINDING_AMENDMENT_SHA256:
        raise RunnerError("runtime-script binding amendment SHA-256 mismatch")
    for path, expected in (
        (PRIOR_V014_RUNNER, PRIOR_V014_RUNNER_SHA256),
        (PRIOR_V014_FAILURE_RECORD, PRIOR_V014_FAILURE_RECORD_SHA256),
        (PRIOR_V014_FAILURE_CONTEXT, PRIOR_V014_FAILURE_CONTEXT_SHA256),
        (PRIOR_V014_SHARD_MANIFEST, PRIOR_V014_SHARD_MANIFEST_SHA256),
    ):
        ensure_file(path)
        if sha256_file(path) != expected:
            raise RunnerError(f"prior v0.1.4 evidence SHA mismatch: {{path}}")
    try:
        payload = json.loads(RUNTIME_SCRIPT_BINDING_AMENDMENT.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RunnerError(f"invalid runtime-script binding amendment: {{exc}}") from exc
    for key, expected in {{
        "schema": {AMENDMENT_SCHEMA!r},
        "builder_version": {BUILDER_VERSION!r},
        "runner_version": VERSION,
        "analysis_run_id": ANALYSIS_RUN_ID,
        "mapping_run_id": MAPPING_RUN_ID,
        "obsolete_template_run_id": OBSOLETE_TEMPLATE_RUN_ID,
    }}.items():
        if payload.get(key) != expected:
            raise RunnerError(
                f"runtime-script amendment mismatch {{key}}: {{payload.get(key)}} != {{expected}}"
            )
    execution = payload.get("validated_execution", {{}})
    for key, expected in {{
        "read_coherent_shards": SHARDS,
        "active_shard_concurrency": STAGE_WORKERS,
        "caller_workers_per_shard": CALLER_WORKERS_PER_SHARD,
        "validator_workers": VALIDATOR_WORKERS,
        "validator_sort_buffer": EXTERNAL_SORT_BUFFER,
        "post_11b_candidate_rows_per_shard_hard_max": POST_11B_MAX_CANDIDATE_ROWS_PER_SHARD,
    }}.items():
        if execution.get(key) != expected:
            raise RunnerError(f"runtime-script amendment execution mismatch {{key}}")
    authorization = payload.get("authorization", {{}})
    for key, expected in {{
        "v015_preflight_authorized": True,
        "v015_execution_authorized_after_exact_v015_preflight": True,
        "all_144x3_generated_scripts_must_be_audited_before_partition": True,
        "v014_partition_reuse_allowed": False,
        "v015_fresh_partition_required": True,
        "mapping_included_in_bam_to_final_timer": False,
    }}.items():
        if authorization.get(key) != expected:
            raise RunnerError(f"runtime-script amendment authorization mismatch {{key}}")
    failure = payload.get("v014_failure", {{}})
    for key, expected in {{
        "cause": "RUNTIME_GENERATED_SHARD_SCRIPTS_RETAINED_500K_ANALYSIS_RUN_ID",
        "partition_completed": True,
        "successful_11b_shards": 0,
        "candidate_extraction_started": False,
        "caller_started": False,
        "materializer_started": False,
        "package_final_published": False,
        "v014_partition_reuse_allowed": False,
        "v015_fresh_partition_required": True,
    }}.items():
        if failure.get(key) != expected:
            raise RunnerError(f"runtime-script amendment v014 failure mismatch {{key}}")
    records = payload.get("runtime_script_binding", {{}})
    for role in ("11b", "11d3", "11e"):
        record = records.get(role, {{}})
        original = ORIGINAL_RUNTIME_SOURCE_PATHS[role]
        bound = BOUND_RUNTIME_SOURCE_PATHS[role]
        for path in (original, bound):
            ensure_file(path)
        if sha256_file(original) != ORIGINAL_RUNTIME_SOURCE_SHA256[role]:
            raise RunnerError(f"original runtime source SHA mismatch: {{role}}")
        if sha256_file(bound) != BOUND_RUNTIME_SOURCE_SHA256[role]:
            raise RunnerError(f"bound runtime source SHA mismatch: {{role}}")
        text = bound.read_text(encoding="utf-8")
        if OBSOLETE_TEMPLATE_RUN_ID in text:
            raise RunnerError(f"obsolete run ID remains in bound source: {{role}}")
        if MAPPING_RUN_ID in text:
            raise RunnerError(f"mapping run ID contaminates bound source: {{role}}")
        if text.count(ANALYSIS_RUN_ID) != BOUND_RUNTIME_SOURCE_EXPECTED_ANALYSIS_ANCHORS[role]:
            raise RunnerError(f"analysis run-ID count mismatch in bound source: {{role}}")
        if record.get("bound_sha256") != BOUND_RUNTIME_SOURCE_SHA256[role]:
            raise RunnerError(f"amendment bound SHA mismatch: {{role}}")
        syntax = subprocess.run(["bash", "-n", str(bound)], text=True, capture_output=True)
        if syntax.returncode != 0:
            raise RunnerError(f"bound source bash syntax failure {{role}}: {{syntax.stderr}}")
    return {{
        "amendment_sha256": RUNTIME_SCRIPT_BINDING_AMENDMENT_SHA256,
        "bound_sources": 3,
        "v014_partition_reuse_allowed": False,
        "v015_fresh_partition_required": True,
    }}


def create_runtime_script_binding_fixture(base, root: Path):
    name = "shard_000"
    project = root / "project"
    raw_root = root / "raw_root"
    mapping_dir = project / "results/11_mapping" / RUN_ID
    script_dir = root / "generated_scripts"
    shard = base.Shard(
        index=0,
        name=name,
        root=root,
        project=project,
        raw_root=raw_root,
        bam=mapping_dir / f"{{RUN_ID}}.sorted.bam",
        candidate_fastq=(
            raw_root / "benchmarks/ENCSR307SHM/stage15c_full5312696_v1"
            / "rnatr_candidates_v0.3.1/ENCFF260PGB.full5312696.rnatr_candidate_all.fastq.gz"
        ),
        script_11b=script_dir / "11b.stage15c_fullscale.sh",
        script_11d3=script_dir / "11d3.stage15c_fullscale.sh",
        script_11e=script_dir / "11e.stage15c_fullscale.sh",
    )
    return shard


def audit_generated_runtime_scripts(
    shards: list[Any], output_path: Path, scope: str
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    specs = (
        ("11b", "script_11b"),
        ("11d3", "script_11d3"),
        ("11e", "script_11e"),
    )
    for shard in shards:
        for role, attribute in specs:
            path = Path(getattr(shard, attribute))
            ensure_file(path)
            text = path.read_text(encoding="utf-8")
            old_count = text.count(OBSOLETE_TEMPLATE_RUN_ID)
            mapping_count = text.count(MAPPING_RUN_ID)
            analysis_count = text.count(ANALYSIS_RUN_ID)
            missing_anchors = [
                line for line in BOUND_RUNTIME_SOURCE_ANCHOR_LINES[role]
                if line not in text
            ]
            syntax = subprocess.run(
                ["bash", "-n", str(path)], text=True, capture_output=True
            )
            status = "PASS"
            failure_codes: list[str] = []
            if old_count:
                failure_codes.append("OBSOLETE_500K_RUN_ID_PRESENT")
            if mapping_count:
                failure_codes.append("MAPPING_RUN_ID_PRESENT_IN_ANALYSIS_SCRIPT")
            if analysis_count < BOUND_RUNTIME_SOURCE_EXPECTED_ANALYSIS_ANCHORS[role]:
                failure_codes.append("INSUFFICIENT_ANALYSIS_RUN_ID_ANCHORS")
            if missing_anchors:
                failure_codes.append("BOUND_RUN_ID_ANCHOR_LINE_MISSING")
            if syntax.returncode != 0:
                failure_codes.append("BASH_SYNTAX_FAIL")
            if failure_codes:
                status = "FAIL"
            rows.append({{
                "scope": scope,
                "shard": shard.name,
                "role": role,
                "path": str(path),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "obsolete_run_id_occurrences": old_count,
                "mapping_run_id_occurrences": mapping_count,
                "analysis_run_id_occurrences": analysis_count,
                "minimum_required_analysis_anchors": BOUND_RUNTIME_SOURCE_EXPECTED_ANALYSIS_ANCHORS[role],
                "missing_bound_anchor_lines": len(missing_anchors),
                "bash_syntax_status": "PASS" if syntax.returncode == 0 else "FAIL",
                "failure_codes": ";".join(failure_codes) if failure_codes else ".",
                "status": status,
            }})
    rows.sort(key=lambda row: (str(row["shard"]), str(row["role"])))
    atomic_write_tsv(output_path, list(rows[0]), rows)
    failures = [row for row in rows if row["status"] != "PASS"]
    if failures:
        first = failures[0]
        raise RunnerError(
            "runtime-generated script binding audit failed: "
            f"{{first['shard']}}/{{first['role']}}:{{first['failure_codes']}}"
        )
    return rows


def setup_and_audit_shard_files(
    base, shards: list[Any], output_path: Path, scope: str
) -> list[dict[str, Any]]:
    base.setup_shard_files(shards)
    return audit_generated_runtime_scripts(shards, output_path, scope)
'''


def transform_runner(
    v014_source: str,
    amendment_sha: str,
    source_records: dict[str, dict[str, Any]],
) -> str:
    text = v014_source
    text = replace_once(
        text,
        'VERSION = "rnatr_stage15c_full5312696_bam_to_final_v0.1.4"',
        'VERSION = "rnatr_stage15c_full5312696_bam_to_final_v0.1.5"',
        "runner_version",
    )

    old_output_roots = '''RESULT_ROOT = (
    PROJECT_ROOT / "results/15_stage15c_fullscale_bam_to_final" / RUN_ID / "v0.1.4"
)
QC_ROOT = (
    PROJECT_ROOT / "qc/15_stage15c_fullscale_bam_to_final" / RUN_ID / "v0.1.4"
)
PREFLIGHT_ROOT = (
    PROJECT_ROOT / "qc/15_stage15c_fullscale_runner_preflight" / RUN_ID / "v0.1.4"
)
'''
    new_output_roots = '''RESULT_ROOT = (
    PROJECT_ROOT / "results/15_stage15c_fullscale_bam_to_final" / RUN_ID / "v0.1.5"
)
QC_ROOT = (
    PROJECT_ROOT / "qc/15_stage15c_fullscale_bam_to_final" / RUN_ID / "v0.1.5"
)
PREFLIGHT_ROOT = (
    PROJECT_ROOT / "qc/15_stage15c_fullscale_runner_preflight" / RUN_ID / "v0.1.5"
)
'''
    text = replace_once(text, old_output_roots, new_output_roots, "output_roots")

    direct_replacements = (
        (
            'DOC_PATH = PROJECT_ROOT / "docs/stage15c/RNA_TR_Scout_fullscale_runner_execution_contract_v0.1.4.md"',
            'DOC_PATH = PROJECT_ROOT / "docs/stage15c/RNA_TR_Scout_fullscale_runner_execution_contract_v0.1.5.md"',
            "doc_path",
        ),
        (
            'SCRIPT_INSTALL = PROJECT_ROOT / "scripts/rnatr_stage15c_run_full5312696_bam_to_final_v0.1.4.py"',
            'SCRIPT_INSTALL = PROJECT_ROOT / "scripts/rnatr_stage15c_run_full5312696_bam_to_final_v0.1.5.py"',
            "script_install",
        ),
        (
            'PREFLIGHT_BUNDLE = DOWNLOADS / "rnatr_stage15c_fullscale_runner_preflight_v0.1.4.tar.gz"',
            'PREFLIGHT_BUNDLE = DOWNLOADS / "rnatr_stage15c_fullscale_runner_preflight_v0.1.5.tar.gz"',
            "preflight_bundle",
        ),
        (
            'SUCCESS_BUNDLE = DOWNLOADS / "rnatr_stage15c_full_empirical_run_v0.1.4.tar.gz"',
            'SUCCESS_BUNDLE = DOWNLOADS / "rnatr_stage15c_full_empirical_run_v0.1.5.tar.gz"',
            "success_bundle",
        ),
        (
            'FAILURE_BUNDLE = DOWNLOADS / "rnatr_stage15c_full_empirical_run_v0.1.4_failure.tar.gz"',
            'FAILURE_BUNDLE = DOWNLOADS / "rnatr_stage15c_full_empirical_run_v0.1.5_failure.tar.gz"',
            "failure_bundle",
        ),
    )
    for old, new, label in direct_replacements:
        text = replace_once(text, old, new, label)

    # Replace frozen 500k templates with immutable v0.1.5 full-run-ID-bound templates.
    old_source_block = '''SOURCE_11B = PROJECT_ROOT / "scripts/11b_extract_alignment_segments_and_target_candidates.stage15a500k_runid_v0.1.0.sh"
SOURCE_11D3 = PROJECT_ROOT / "scripts/11d3_project_targets_to_raw_reads.stage15a500k_runid_v0.1.0.sh"
SOURCE_11E = PROJECT_ROOT / "scripts/11e_prepare_motif_scan_jobs.stage15a500k_runid_v0.1.0.sh"
SOURCE_SHA = {
    SOURCE_11B: "ccf37ebbe71451f12d113cb4148e5415ad7cbcd59ef954b7b7dd7a6b69078075",
    SOURCE_11D3: "d7411df47e54e672ea3c838746402d35787c0d1c2fe0af628e7a7f36d98ea203",
    SOURCE_11E: "b648b24f22c96fa5625baf09313500c2ca54668ed318ed0aa49570a10c743e3b",
}
'''
    new_source_block = f'''SOURCE_11B = Path({source_records["11b"]["bound_path"]!r})
SOURCE_11D3 = Path({source_records["11d3"]["bound_path"]!r})
SOURCE_11E = Path({source_records["11e"]["bound_path"]!r})
SOURCE_SHA = {{
    SOURCE_11B: {source_records["11b"]["bound_sha256"]!r},
    SOURCE_11D3: {source_records["11d3"]["bound_sha256"]!r},
    SOURCE_11E: {source_records["11e"]["bound_sha256"]!r},
}}
'''
    text = replace_once(text, old_source_block, new_source_block, "bound_source_block")

    support = runtime_binding_support_source(amendment_sha, source_records)
    text = insert_before_once(
        text,
        "\nSSOT_GUARDS = {\n",
        support,
        "runtime_binding_support",
    )

    # v0.1.4 unlock is prior authorization evidence; v0.1.5 amendment is the continuation authorization.
    text = replace_once(
        text,
        '        "builder_version": "rnatr_stage15c_build_execution_unlocked_full_runner_v0.1.4",\n'
        '        "runner_version": VERSION,',
        '        "builder_version": "rnatr_stage15c_build_execution_unlocked_full_runner_v0.1.4",\n'
        '        "runner_version": "rnatr_stage15c_full5312696_bam_to_final_v0.1.4",',
        "prior_unlock_runner_version",
    )

    # Contract version and binding/fresh-partition provenance.
    text = replace_once(
        text,
        "# RNA-TR-Scout Stage 15C full-scale execution contract v0.1.4",
        "# RNA-TR-Scout Stage 15C full-scale execution contract v0.1.5",
        "contract_heading",
    )
    text = replace_once(
        text,
        "Contract version date: 2026-08-10\n\n## Execution authorization",
        "Contract version date: 2026-08-10\n\n"
        "## Runtime-generated script binding amendment\n\n"
        f"- Amendment SHA-256: `{amendment_sha}`\n"
        f"- Obsolete template run ID: `{OLD_TEMPLATE_RUN_ID}`\n"
        f"- Bound analysis run ID: `{ANALYSIS_RUN_ID}`\n"
        "- All 144 × 3 generated scripts are audited before partitioning.\n"
        "- The failed v0.1.4 partition is not reused; v0.1.5 performs a fresh partition inside the formal timer.\n\n"
        "## Execution authorization",
        "contract_runtime_binding_section",
    )

    # Preflight: verify amendment and exercise actual base.setup_shard_files on one synthetic shard.
    text = replace_once(
        text,
        "    unlock = verify_execution_unlock_evidence()\n"
        "    mapping = verify_mapping_binding(recompute_large_hashes=True)",
        "    unlock = verify_execution_unlock_evidence()\n"
        "    runtime_binding = verify_runtime_script_binding_amendment()\n"
        "    base = configure_modules()\n"
        "    fixture_root = PREFLIGHT_ROOT / \"runtime_script_binding_fixture\"\n"
        "    fixture = create_runtime_script_binding_fixture(base, fixture_root)\n"
        "    fixture_rows = setup_and_audit_shard_files(\n"
        "        base, [fixture],\n"
        "        PREFLIGHT_ROOT / \"runtime_script_binding_fixture.audit.tsv\",\n"
        "        \"PREFLIGHT_SYNTHETIC_ONE_SHARD\",\n"
        "    )\n"
        "    shutil.rmtree(fixture_root)\n"
        "    mapping = verify_mapping_binding(recompute_large_hashes=True)",
        "preflight_runtime_binding_fixture",
    )

    qc_anchor = '        ("locked_preflight_qc_sha256", unlock["locked_preflight_qc_sha256"]),\n'
    qc_insert = (
        '        ("runtime_script_binding_amendment", RUNTIME_SCRIPT_BINDING_AMENDMENT),\n'
        '        ("runtime_script_binding_amendment_sha256", runtime_binding["amendment_sha256"]),\n'
        '        ("runtime_script_binding_fixture_status", "PASS"),\n'
        '        ("runtime_script_binding_fixture_rows", len(fixture_rows)),\n'
        '        ("runtime_script_binding_expected_full_rows", SHARDS * 3),\n'
        '        ("v014_failed_partition_reused", "false"),\n'
        '        ("v015_fresh_partition_required", "true"),\n'
    )
    text = replace_once(text, qc_anchor, qc_anchor + qc_insert, "preflight_qc_binding_fields")

    text = replace_once(
        text,
        '    make_bundle(PREFLIGHT_BUNDLE, [PREFLIGHT_ROOT, DOC_PATH, SCRIPT_INSTALL, EXECUTION_UNLOCK_CONTRACT], "rnatr_stage15c_fullscale_runner_preflight_v0.1.4")',
        '    make_bundle(PREFLIGHT_BUNDLE, [PREFLIGHT_ROOT, DOC_PATH, SCRIPT_INSTALL, EXECUTION_UNLOCK_CONTRACT, RUNTIME_SCRIPT_BINDING_AMENDMENT, BOUND_SOURCE_ROOT], "rnatr_stage15c_fullscale_runner_preflight_v0.1.5")',
        "preflight_bundle_v015",
    )

    # Preflight-for-execute must require the new audit fields and exact 5-artifact manifest.
    required_anchor = '        "locked_preflight_qc_sha256": "719bc1e9a2b95d2096c46e5382324ef4d5305fa9c44851c811d6a86bed278180",\n'
    required_insert = (
        f'        "runtime_script_binding_amendment_sha256": {amendment_sha!r},\n'
        '        "runtime_script_binding_fixture_status": "PASS",\n'
        '        "runtime_script_binding_fixture_rows": "3",\n'
        f'        "runtime_script_binding_expected_full_rows": "{SHARDS * 3}",\n'
        '        "v014_failed_partition_reused": "false",\n'
        '        "v015_fresh_partition_required": "true",\n'
    )
    text = replace_once(text, required_anchor, required_anchor + required_insert, "execute_preflight_binding_requirements")
    text = replace_once(
        text,
        '''    expected_artifacts = {
        "mapping_artifact_integrity.tsv",
        "resource_model.tsv",
        "source_and_contract_guards.tsv",
        "stage15c_fullscale_runner_preflight.qc.tsv",
    }
''',
        '''    expected_artifacts = {
        "mapping_artifact_integrity.tsv",
        "resource_model.tsv",
        "runtime_script_binding_fixture.audit.tsv",
        "source_and_contract_guards.tsv",
        "stage15c_fullscale_runner_preflight.qc.tsv",
    }
''',
        "preflight_manifest_expected_set",
    )

    # Execute: amendment verification and all 432 scripts audited before partition/timer.
    text = replace_once(
        text,
        "    verify_execution_unlock_evidence()\n"
        "    verify_stage15b_evidence()",
        "    verify_execution_unlock_evidence()\n"
        "    verify_runtime_script_binding_amendment()\n"
        "    verify_stage15b_evidence()",
        "execute_runtime_binding_verification",
    )
    text = replace_once(
        text,
        'FULL_EXECUTION_NOT_AUTHORIZED_BY_V0.1.4_UNLOCK_CONTRACT',
        'FULL_EXECUTION_NOT_AUTHORIZED_BY_V0.1.5_RUNTIME_BINDING_AMENDMENT',
        "execute_authorization_message",
    )
    text = replace_once(
        text,
        "    base.setup_shard_files(shards)\n"
        "    active_before = {path: sha256_file(path) for path in ACTIVE_GUARDS}",
        "    runtime_script_rows = setup_and_audit_shard_files(\n"
        "        base, shards,\n"
        "        CONTRACT_ROOT / \"runtime_generated_scripts_prepartition.audit.tsv\",\n"
        "        \"FULL144_PREPARTITION\",\n"
        "    )\n"
        "    if len(runtime_script_rows) != SHARDS * 3:\n"
        "        raise RunnerError(\n"
        "            f\"runtime-generated script audit row mismatch: {len(runtime_script_rows)} != {SHARDS * 3}\"\n"
        "        )\n"
        "    active_before = {path: sha256_file(path) for path in ACTIVE_GUARDS}",
        "execute_runtime_script_audit",
    )

    execution_contract_anchor = (
        '            ("locus_aggregation", "NOT_RUN"),\n'
        '            ("full_5_31m_run_started", "true"),\n'
    )
    execution_contract_insert = (
        '            ("runtime_script_binding_amendment", RUNTIME_SCRIPT_BINDING_AMENDMENT),\n'
        '            ("runtime_script_binding_amendment_sha256", RUNTIME_SCRIPT_BINDING_AMENDMENT_SHA256),\n'
        '            ("runtime_generated_script_audit_rows", len(runtime_script_rows)),\n'
        '            ("runtime_generated_script_audit_status", "PASS"),\n'
        '            ("v014_failed_partition_reused", "false"),\n'
        '            ("v015_fresh_partition_required", "true"),\n'
    )
    text = replace_once(
        text,
        execution_contract_anchor,
        '            ("locus_aggregation", "NOT_RUN"),\n'
        + execution_contract_insert
        + '            ("full_5_31m_run_started", "true"),\n',
        "execution_contract_binding_fields",
    )

    text = replace_once(
        text,
        '                ("run_id", RUN_ID),\n'
        '                ("full_5_31m_run_started", "true"),\n'
        '                ("package_final_published", str(PACKAGE_FINAL.exists()).lower()),',
        '                ("run_id", RUN_ID),\n'
        '                ("runtime_script_binding_amendment_sha256", RUNTIME_SCRIPT_BINDING_AMENDMENT_SHA256),\n'
        '                ("runtime_generated_script_audit_rows", len(runtime_script_rows)),\n'
        '                ("runtime_generated_script_audit_status", "PASS"),\n'
        '                ("v014_failed_partition_reused", "false"),\n'
        '                ("v015_fresh_partition_required", "true"),\n'
        '                ("full_5_31m_run_started", "true"),\n'
        '                ("package_final_published", str(PACKAGE_FINAL.exists()).lower()),',
        "failed_run_context_binding_fields",
    )

    text = replace_once(
        text,
        '        ("core_schema_modified", "false"),\n'
        '        ("full_5_31m_run_started", "true"),\n'
        '        ("package_final_published", "true"),',
        '        ("core_schema_modified", "false"),\n'
        '        ("runtime_script_binding_amendment_sha256", RUNTIME_SCRIPT_BINDING_AMENDMENT_SHA256),\n'
        '        ("runtime_generated_script_audit_rows", len(runtime_script_rows)),\n'
        '        ("runtime_generated_script_audit_status", "PASS"),\n'
        '        ("v014_failed_partition_reused", "false"),\n'
        '        ("v015_fresh_partition_required", "true"),\n'
        '        ("full_5_31m_run_started", "true"),\n'
        '        ("package_final_published", "true"),',
        "final_qc_binding_fields",
    )

    # Bundle the amendment/bound sources and version all archive prefixes.
    text = replace_once(
        text,
        '    selected_roots = [QC_ROOT, DOC_PATH, SCRIPT_INSTALL, EXECUTION_UNLOCK_CONTRACT, package_manifest, PACKAGE_FINAL / "materialization.qc.tsv"]',
        '    selected_roots = [QC_ROOT, DOC_PATH, SCRIPT_INSTALL, EXECUTION_UNLOCK_CONTRACT, RUNTIME_SCRIPT_BINDING_AMENDMENT, BOUND_SOURCE_ROOT, package_manifest, PACKAGE_FINAL / "materialization.qc.tsv"]',
        "success_bundle_binding_evidence",
    )
    text = replace_once(
        text,
        '    make_bundle(SUCCESS_BUNDLE, selected_roots, "rnatr_stage15c_full_empirical_run_v0.1.4")',
        '    make_bundle(SUCCESS_BUNDLE, selected_roots, "rnatr_stage15c_full_empirical_run_v0.1.5")',
        "success_bundle_prefix",
    )
    text = replace_once(
        text,
        '        make_bundle(FAILURE_BUNDLE, [QC_ROOT, DOC_PATH, SCRIPT_INSTALL, EXECUTION_UNLOCK_CONTRACT], "rnatr_stage15c_full_empirical_run_failure_v0.1.4")',
        '        make_bundle(FAILURE_BUNDLE, [QC_ROOT, DOC_PATH, SCRIPT_INSTALL, EXECUTION_UNLOCK_CONTRACT, RUNTIME_SCRIPT_BINDING_AMENDMENT, BOUND_SOURCE_ROOT], "rnatr_stage15c_full_empirical_run_failure_v0.1.5")',
        "failure_bundle_prefix",
    )
    return text


def audit_runner_source(
    v014_source: str,
    generated: str,
    amendment_sha: str,
    source_records: dict[str, dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    try:
        tree = ast.parse(generated)
        ast.parse(v014_source)
    except SyntaxError as exc:
        return [f"SYNTAX_ERROR:{exc}"]
    constants = top_level_constants(generated)
    expected_constants = {
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
        "RUNTIME_SCRIPT_BINDING_AMENDMENT_SHA256": amendment_sha,
    }
    for key, expected in expected_constants.items():
        if constants.get(key) != expected:
            errors.append(f"CONST_MISMATCH:{key}:{constants.get(key)!r}!={expected!r}")
    for role, constant in (("11b", "SOURCE_11B"), ("11d3", "SOURCE_11D3"), ("11e", "SOURCE_11E")):
        expected_path = source_records[role]["bound_path"]
        if f"{constant} = Path({expected_path!r})" not in generated:
            errors.append(f"BOUND_SOURCE_PATH_MISMATCH:{role}")
    required_fragments = (
        "def verify_runtime_script_binding_amendment()",
        "def create_runtime_script_binding_fixture(base, root: Path):",
        "def audit_generated_runtime_scripts(",
        "def setup_and_audit_shard_files(",
        "runtime_script_binding_fixture.audit.tsv",
        "runtime_generated_scripts_prepartition.audit.tsv",
        "FULL144_PREPARTITION",
        '"v014_failed_partition_reused", "false"',
        '"v015_fresh_partition_required", "true"',
        "RUNTIME_GENERATED_SHARD_SCRIPTS_RETAINED_500K_ANALYSIS_RUN_ID",
        "# RNA-TR-Scout Stage 15C full-scale execution contract v0.1.5",
        "FULL_EXECUTION_NOT_AUTHORIZED_BY_V0.1.5_RUNTIME_BINDING_AMENDMENT",
        '"runner_version": "rnatr_stage15c_full5312696_bam_to_final_v0.1.4"',
    )
    for fragment in required_fragments:
        if fragment not in generated:
            errors.append(f"MISSING_FRAGMENT:{fragment}")
    if ' / RUN_ID / "v0.1.4"\n)' in generated:
        errors.append("V014_OUTPUT_ROOT_REMAINED")
    if ' / RUN_ID / "v0.1.5"\n)' not in generated:
        errors.append("V015_OUTPUT_ROOT_MISSING")

    functions = function_sources(generated)
    execute_source = functions.get("execute", "")
    preflight_source = functions.get("preflight", "")
    if "base.setup_shard_files(shards)" in execute_source:
        errors.append("DIRECT_UNAUDITED_SETUP_REMAINS_IN_EXECUTE")
    for needle in (
        "verify_runtime_script_binding_amendment()",
        "setup_and_audit_shard_files(",
        "runtime_generated_scripts_prepartition.audit.tsv",
    ):
        if needle not in execute_source:
            errors.append(f"EXECUTE_MISSING:{needle}")
    positions = {
        "binding_verify": execute_source.find("verify_runtime_script_binding_amendment()"),
        "setup_audit": execute_source.find("setup_and_audit_shard_files("),
        "partition": execute_source.find("partition_inputs(base, shards)"),
        "timer": execute_source.find("production_started = time.perf_counter()"),
        "caller": execute_source.find("run_caller_materializer(base, shards)"),
    }
    if any(value < 0 for value in positions.values()):
        errors.append(f"EXECUTE_ORDER_ANCHOR_MISSING:{positions}")
    elif not (
        positions["binding_verify"] < positions["setup_audit"] < positions["timer"] < positions["partition"] < positions["caller"]
    ):
        errors.append(f"EXECUTE_ORDER_INVALID:{positions}")
    if "create_runtime_script_binding_fixture" not in preflight_source:
        errors.append("PREFLIGHT_FIXTURE_MISSING")
    if "setup_and_audit_shard_files" not in preflight_source:
        errors.append("PREFLIGHT_RUNTIME_AUDIT_MISSING")

    # Scientific processing functions must remain byte-identical to v0.1.4.
    old_functions = function_sources(v014_source)
    for name in SCIENTIFIC_FUNCTIONS:
        if old_functions.get(name) != functions.get(name):
            errors.append(f"SCIENTIFIC_FUNCTION_CHANGED:{name}")

    # Existing mandatory hard gate remains before candidate extraction/caller.
    if "enforce_post_11b_candidate_load_hard_gate" not in execute_source:
        errors.append("POST_11B_HARD_GATE_MISSING")
    else:
        gate = execute_source.find("enforce_post_11b_candidate_load_hard_gate")
        extraction = execute_source.find("extract_candidate_fastqs")
        caller = execute_source.find("run_caller_materializer")
        if not (0 <= gate < extraction < caller):
            errors.append("POST_11B_HARD_GATE_ORDER_INVALID")
    return errors


def mutate_once(source: str, old: str, new: str, label: str) -> str:
    if source.count(old) != 1:
        raise BuildError(f"mutation anchor {label} count={source.count(old)}")
    return source.replace(old, new, 1)


def negative_mutation_tests(
    v014_source: str,
    generated: str,
    amendment_sha: str,
    source_records: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    mutations = [
        (
            "source_11b_reverted_to_old_template",
            f'SOURCE_11B = Path({source_records["11b"]["bound_path"]!r})',
            f'SOURCE_11B = Path({str(ORIGINAL_SOURCE_SPECS["11b"][0])!r})',
        ),
        (
            "source_11d3_reverted_to_old_template",
            f'SOURCE_11D3 = Path({source_records["11d3"]["bound_path"]!r})',
            f'SOURCE_11D3 = Path({str(ORIGINAL_SOURCE_SPECS["11d3"][0])!r})',
        ),
        (
            "source_11e_reverted_to_old_template",
            f'SOURCE_11E = Path({source_records["11e"]["bound_path"]!r})',
            f'SOURCE_11E = Path({str(ORIGINAL_SOURCE_SPECS["11e"][0])!r})',
        ),
        (
            "runtime_execute_audit_removed",
            "    runtime_script_rows = setup_and_audit_shard_files(\n",
            "    runtime_script_rows = unaudited_setup_placeholder(\n",
        ),
        (
            "preflight_fixture_call_removed",
            "    fixture_rows = setup_and_audit_shard_files(\n",
            "    fixture_rows = unaudited_fixture_placeholder(\n",
        ),
        (
            "amendment_sha_changed",
            f'RUNTIME_SCRIPT_BINDING_AMENDMENT_SHA256 = {amendment_sha!r}',
            'RUNTIME_SCRIPT_BINDING_AMENDMENT_SHA256 = "0" * 64',
        ),
        (
            "result_root_reverted_to_v014",
            'PROJECT_ROOT / "results/15_stage15c_fullscale_bam_to_final" / RUN_ID / "v0.1.5"',
            'PROJECT_ROOT / "results/15_stage15c_fullscale_bam_to_final" / RUN_ID / "v0.1.4"',
        ),
        (
            "analysis_run_id_changed_to_mapping",
            f"ANALYSIS_RUN_ID = {ANALYSIS_RUN_ID!r}",
            f"ANALYSIS_RUN_ID = {MAPPING_RUN_ID!r}",
        ),
        ("shards_changed_to_60", "SHARDS = 144", "SHARDS = 60"),
        (
            "post_11b_hard_max_changed",
            "POST_11B_MAX_CANDIDATE_ROWS_PER_SHARD = 164204",
            "POST_11B_MAX_CANDIDATE_ROWS_PER_SHARD = 164205",
        ),
    ]
    rows: list[dict[str, str]] = []
    for label, old, new in mutations:
        mutated = mutate_once(generated, old, new, label)
        rejected = bool(audit_runner_source(v014_source, mutated, amendment_sha, source_records))
        rows.append({
            "test": label,
            "expected": "REJECT",
            "observed": "REJECT" if rejected else "ACCEPT",
            "status": "PASS" if rejected else "FAIL",
        })
    failures = [row for row in rows if row["status"] != "PASS"]
    if failures:
        raise BuildError(f"negative mutation test failed: {failures}")
    return rows


def import_generated_runner(path: Path):
    name = "rnatr_stage15c_runtime_bound_runner_v015_selftest"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise BuildError(f"cannot import generated runner: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return name, module


def dynamic_safety_tests(
    runner_path: Path,
    source_records: dict[str, dict[str, Any]],
    amendment_sha: str,
) -> list[dict[str, str]]:
    name, module = import_generated_runner(runner_path)
    rows: list[dict[str, str]] = []
    try:
        boundary_cases = (
            (POST_11B_HARD_MAX, "ACCEPT"),
            (POST_11B_HARD_MAX + 1, "REJECT"),
        )
        for value, expected in boundary_cases:
            passed, observed_max, offenders = module.candidate_load_gate_decision([value])
            observed = "ACCEPT" if passed else "REJECT"
            detail_ok = (
                observed_max == value
                and (offenders == [] if expected == "ACCEPT" else offenders == [0])
            )
            rows.append({
                "test": f"candidate_hard_gate_{value}",
                "expected": expected,
                "observed": observed,
                "status": "PASS" if observed == expected and detail_ok else "FAIL",
            })
        amendment = module.verify_runtime_script_binding_amendment()
        rows.append({
            "test": "runtime_binding_amendment_real_project_verification",
            "expected": "PASS",
            "observed": "PASS" if amendment["amendment_sha256"] == amendment_sha else "FAIL",
            "status": "PASS" if amendment["amendment_sha256"] == amendment_sha else "FAIL",
        })

        # Exercise the exact imported Stage15A setup_shard_files implementation on a
        # synthetic one-shard project using the installed bound sources.
        with tempfile.TemporaryDirectory(prefix="rnatr_stage15c_v015_fixture_") as temporary:
            root = Path(temporary)
            base = module.configure_modules()
            fixture = module.create_runtime_script_binding_fixture(base, root / "fixture")
            audit_path = root / "fixture_audit.tsv"
            fixture_rows = module.setup_and_audit_shard_files(
                base, [fixture], audit_path, "BUILDER_REAL_BASE_FIXTURE"
            )
            fixture_pass = (
                len(fixture_rows) == 3
                and all(row["status"] == "PASS" for row in fixture_rows)
                and all(int(row["obsolete_run_id_occurrences"]) == 0 for row in fixture_rows)
                and all(int(row["mapping_run_id_occurrences"]) == 0 for row in fixture_rows)
            )
            rows.append({
                "test": "real_base_setup_shard_files_runtime_binding_fixture",
                "expected": "PASS_3_OF_3",
                "observed": "PASS_3_OF_3" if fixture_pass else "FAIL",
                "status": "PASS" if fixture_pass else "FAIL",
            })
    finally:
        sys.modules.pop(name, None)
    failures = [row for row in rows if row["status"] != "PASS"]
    if failures:
        raise BuildError(f"dynamic safety test failed: {failures}")
    return rows


def make_doc(amendment_sha: str, source_records: dict[str, dict[str, Any]]) -> bytes:
    lines = [
        "# RNA-TR-Scout Stage 15C runtime-script binding amendment v0.1.5",
        "",
        "## Failure addressed",
        "",
        "The v0.1.4 clean full run completed a fresh 144-shard BAM/FASTQ partition,",
        "then stopped at the first 11b wave because runtime-generated shard scripts",
        f"still contained the obsolete 500k analysis run ID `{OLD_TEMPLATE_RUN_ID}`.",
        "No 11b shard passed, caller/materializer did not start, and no final package was published.",
        "",
        "## v0.1.5 contract",
        "",
        f"- Formal analysis run ID: `{ANALYSIS_RUN_ID}`",
        f"- Mapping run ID: `{MAPPING_RUN_ID}`",
        f"- Shards/concurrency: `{SHARDS}` / `{CONCURRENCY}`",
        f"- Post-11b hard maximum: `{POST_11B_HARD_MAX:,}` candidate rows/shard",
        f"- Binding amendment SHA-256: `{amendment_sha}`",
        "- The three frozen scientific shell templates are copied byte-for-byte except for",
        "  exact old-analysis-run-ID to full-analysis-run-ID substitution.",
        "- Each bound template must contain zero obsolete IDs, zero mapping IDs, preserve",
        "  all source run-ID anchor lines, and pass `bash -n`.",
        "- The exact Stage15A `setup_shard_files` function is exercised during builder and",
        "  runner preflight on a synthetic shard.",
        "- During execution all 432 generated scripts are audited before partitioning and",
        "  before the formal BAM-to-final timer.",
        "- The failed v0.1.4 partition is never reused; v0.1.5 performs a fresh partition.",
        "",
        "## Bound templates",
        "",
    ]
    for role in ("11b", "11d3", "11e"):
        record = source_records[role]
        lines.extend([
            f"### {role}",
            "",
            f"- Source: `{record['source_path']}`",
            f"- Source SHA-256: `{record['source_sha256']}`",
            f"- Bound: `{record['bound_path']}`",
            f"- Bound SHA-256: `{record['bound_sha256']}`",
            f"- Exact run-ID substitutions: `{record['source_old_run_id_occurrences']}`",
            "",
        ])
    lines.extend([
        "## Non-modification guarantees",
        "",
        "This amendment does not modify the active pipeline, SSOT, schema v0.4.2,",
        "caller v0.4.1, materializer v0.1.2, mapping BAM/FASTQ, accepted 500k results,",
        "or the retained v0.1.4 failure provenance.",
        "",
    ])
    return ("\n".join(lines)).encode("utf-8")


def artifact_manifest(root: Path) -> None:
    rows = []
    target = root / "artifact_manifest.tsv"
    for path in sorted(p for p in root.rglob("*") if p.is_file() and p != target):
        rows.append({
            "relative_path": str(path.relative_to(root)),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        })
    write_tsv(target, rows, ["relative_path", "bytes", "sha256"])


def make_bundle(source_root: Path, target: Path) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name("." + target.name + f".part.{os.getpid()}")
    with tarfile.open(temporary, "w:gz", format=tarfile.PAX_FORMAT) as archive:
        archive.add(source_root, arcname=source_root.name)
    os.replace(temporary, target)
    digest = sha256_file(target)
    Path(str(target) + ".sha256").write_text(
        f"{digest}  {target.name}\n", encoding="utf-8"
    )
    return digest


def build() -> int:
    started = time.time()
    work_parent = Path(tempfile.mkdtemp(prefix="rnatr_stage15c_v015_builder_"))
    package = work_parent / "rnatr_stage15c_runtime_bound_full_runner_build_v0.1.5"
    package.mkdir(parents=True)
    success = False
    failure_text = "."
    installation: dict[str, str] = {}
    runner_sha = "."
    amendment_sha = "."
    source_records: dict[str, dict[str, Any]] = {}
    mutation_rows: list[dict[str, str]] = []
    dynamic_rows: list[dict[str, str]] = []
    try:
        failure = verify_v014_evidence()
        source_records, bound_payloads = bind_runtime_sources()
        amendment_payload = make_amendment_contract(source_records, failure)
        amendment_sha = sha256_bytes(amendment_payload)
        v014_source = V014_RUNNER_PROJECT.read_text(encoding="utf-8")
        generated = transform_runner(v014_source, amendment_sha, source_records)
        compile(generated, str(RUNNER_DOWNLOAD), "exec")
        errors = audit_runner_source(v014_source, generated, amendment_sha, source_records)
        if errors:
            raise BuildError("generated runner static audit failed: " + ";".join(errors))
        mutation_rows = negative_mutation_tests(
            v014_source, generated, amendment_sha, source_records
        )

        # Install immutable bound sources/amendment before real-project dynamic test.
        for role in ("11b", "11d3", "11e"):
            destination = Path(source_records[role]["bound_path"])
            installation[f"bound_{role}"] = install_exact_bytes(
                bound_payloads[role], destination, 0o755
            )
        installation["amendment"] = install_exact_bytes(
            amendment_payload, AMENDMENT_CONTRACT, 0o644
        )

        runner_payload = generated.encode("utf-8")
        temporary_runner = package / RUNNER_DOWNLOAD.name
        atomic_write(temporary_runner, runner_payload, 0o755)
        dynamic_rows = dynamic_safety_tests(
            temporary_runner, source_records, amendment_sha
        )
        runner_sha = sha256_file(temporary_runner)

        # Re-audit final bytes after dynamic imports/tests.
        if sha256_bytes(temporary_runner.read_bytes()) != runner_sha:
            raise BuildError("runner bytes changed during dynamic tests")
        compile(temporary_runner.read_text(encoding="utf-8"), str(temporary_runner), "exec")
        final_errors = audit_runner_source(
            v014_source, temporary_runner.read_text(encoding="utf-8"), amendment_sha, source_records
        )
        if final_errors:
            raise BuildError("final runner re-audit failed: " + ";".join(final_errors))

        doc_payload = make_doc(amendment_sha, source_records)
        # Package exact evidence before project installation.
        shutil.copy2(Path(__file__).resolve(), package / Path(__file__).name)
        atomic_write(package / AMENDMENT_CONTRACT.name, amendment_payload, 0o644)
        atomic_write(package / DOC_INSTALL.name, doc_payload, 0o644)
        source_rows = []
        for role in ("11b", "11d3", "11e"):
            row = dict(source_records[role])
            row["bound_anchor_lines"] = json.dumps(row["bound_anchor_lines"], ensure_ascii=False)
            source_rows.append(row)
            atomic_write(package / Path(row["bound_path"]).name, bound_payloads[role], 0o755)
        write_tsv(
            package / "runtime_source_binding.tsv",
            source_rows,
            [
                "role", "source_path", "source_sha256",
                "source_old_run_id_occurrences", "source_analysis_run_id_occurrences",
                "source_mapping_run_id_occurrences", "bound_path", "bound_sha256",
                "bound_bytes", "bound_analysis_run_id_occurrences",
                "bound_old_run_id_occurrences", "bound_mapping_run_id_occurrences",
                "bound_anchor_lines", "bash_syntax_status",
            ],
        )
        write_tsv(
            package / "negative_mutation_tests.tsv",
            mutation_rows,
            ["test", "expected", "observed", "status"],
        )
        write_tsv(
            package / "dynamic_safety_tests.tsv",
            dynamic_rows,
            ["test", "expected", "observed", "status"],
        )
        qc_rows = [
            ("builder_version", BUILDER_VERSION),
            ("runner_version", RUNNER_VERSION),
            ("analysis_run_id", ANALYSIS_RUN_ID),
            ("mapping_run_id", MAPPING_RUN_ID),
            ("read_coherent_shards", SHARDS),
            ("active_shard_concurrency", CONCURRENCY),
            ("caller_workers_per_shard", CALLER_WORKERS_PER_SHARD),
            ("validator_workers", VALIDATOR_WORKERS),
            ("post_11b_candidate_rows_per_shard_hard_max", POST_11B_HARD_MAX),
            ("v014_failure_evidence", "PASS"),
            ("v014_partition_completed", "true"),
            ("v014_package_final_published", "false"),
            ("v014_failed_partition_reuse_allowed", "false"),
            ("v015_fresh_partition_required", "true"),
            ("bound_source_templates", len(source_records)),
            ("bound_source_templates_status", "PASS"),
            ("real_base_runtime_generation_fixture", "PASS"),
            ("runtime_generated_scripts_audited_before_partition", "true"),
            ("expected_full_runtime_script_audit_rows", SHARDS * 3),
            ("scientific_processing_functions_byte_identical_to_v014", "true"),
            ("negative_mutation_tests", "PASS"),
            ("negative_mutation_test_count", len(mutation_rows)),
            ("dynamic_safety_tests", "PASS"),
            ("dynamic_safety_test_count", len(dynamic_rows)),
            ("runtime_script_binding_amendment_sha256", amendment_sha),
            ("runner_sha256", runner_sha),
            ("full_5_31m_run_started", "false"),
            ("active_pipeline_modified", "false"),
            ("ssot_modified", "false"),
            ("build_status", "PASS"),
            ("next_gate", "RUN_GENERATED_V0.1.5_WITH_--preflight_ONLY"),
        ]
        write_metrics(package / "stage15c_runtime_bound_runner_build.qc.tsv", qc_rows)
        artifact_manifest(package)

        # Immutable project/download publication only after all tests pass.
        installation["builder"] = install_exact_bytes(
            Path(__file__).resolve().read_bytes(), BUILDER_INSTALL, 0o755
        )
        installation["runner"] = install_exact_bytes(
            temporary_runner.read_bytes(), RUNNER_INSTALL, 0o755
        )
        installation["runner_download"] = install_exact_bytes(
            temporary_runner.read_bytes(), RUNNER_DOWNLOAD, 0o755
        )
        installation["doc"] = install_exact_bytes(doc_payload, DOC_INSTALL, 0o644)
        BUILD_QC_ROOT.mkdir(parents=True, exist_ok=True)
        for name in (
            "stage15c_runtime_bound_runner_build.qc.tsv",
            "runtime_source_binding.tsv",
            "negative_mutation_tests.tsv",
            "dynamic_safety_tests.tsv",
            "artifact_manifest.tsv",
        ):
            installation[f"qc::{name}"] = install_exact_bytes(
                (package / name).read_bytes(), BUILD_QC_ROOT / name, 0o644
            )
        success = True
    except Exception as exc:
        failure_text = f"{type(exc).__name__}: {exc}"
        (package / "failure.txt").write_text(
            failure_text + "\n\n" + traceback.format_exc(), encoding="utf-8"
        )
        write_metrics(
            package / "stage15c_runtime_bound_runner_build.failure.tsv",
            [
                ("builder_version", BUILDER_VERSION),
                ("failure", failure_text),
                ("full_5_31m_run_started", "false"),
                ("active_pipeline_modified", "false"),
                ("ssot_modified", "false"),
                ("build_status", "FAIL"),
            ],
        )
        artifact_manifest(package)
    finally:
        elapsed = time.time() - started

    target = SUCCESS_BUNDLE if success else FAILURE_BUNDLE
    bundle_sha = make_bundle(package, target)
    print("===== RNA-TR-Scout Stage 15C runtime-bound full runner build =====")
    print(f"build_status\t{'PASS' if success else 'FAIL'}")
    print(f"analysis_run_id\t{ANALYSIS_RUN_ID}")
    print(f"mapping_run_id\t{MAPPING_RUN_ID}")
    print(f"read_coherent_shards\t{SHARDS}")
    print(f"active_shard_concurrency\t{CONCURRENCY}")
    print(f"post_11b_candidate_rows_per_shard_hard_max\t{POST_11B_HARD_MAX}")
    print(f"v014_failure_evidence\t{'PASS' if success else 'REVIEW'}")
    print("v014_failed_partition_reused\tfalse")
    print("v015_fresh_partition_required\ttrue")
    print(f"bound_source_templates\t{len(source_records)}")
    print(f"bound_source_templates_status\t{'PASS' if success else 'REVIEW'}")
    print(f"real_base_runtime_generation_fixture\t{'PASS' if success else 'NOT_PASS'}")
    print(f"expected_full_runtime_script_audit_rows\t{SHARDS * 3}")
    print(f"scientific_processing_functions_byte_identical_to_v014\t{'true' if success else 'not_confirmed'}")
    print(f"negative_mutation_tests\t{'PASS' if success else 'NOT_PASS'}")
    print(f"dynamic_safety_tests\t{'PASS' if success else 'NOT_PASS'}")
    print(f"full_5_31m_run_started\tfalse")
    print(f"active_pipeline_modified\tfalse")
    print(f"ssot_modified\tfalse")
    if success:
        print(f"RUNTIME_SCRIPT_BINDING_AMENDMENT_SHA256\t{amendment_sha}")
        print(f"RUNNER\t{RUNNER_DOWNLOAD}")
        print(f"RUNNER_SHA256\t{runner_sha}")
        print(f"RUNNER_DOWNLOAD_INSTALLATION\t{installation.get('runner_download', '.')}")
        print(f"NEXT_GATE\tRUN_GENERATED_V0.1.5_WITH_--preflight_ONLY")
    else:
        print(f"failure\t{failure_text}")
        print("NEXT_GATE\tREVIEW_V0.1.5_BUILD_FAILURE")
    print(f"OUTPUT_BUNDLE\t{target}")
    print(f"OUTPUT_BUNDLE_SHA256\t{bundle_sha}")
    print(f"elapsed_seconds\t{elapsed:.6f}")
    return 0 if success else 1


def main() -> int:
    return build()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"BUILD_FAIL\t{type(exc).__name__}\t{exc}", file=sys.stderr)
        raise
