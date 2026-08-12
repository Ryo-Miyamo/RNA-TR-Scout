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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

BUILDER_VERSION = "rnatr_stage15c_build_contract_locked_full_runner_v0.1.1"
RUNNER_VERSION = "rnatr_stage15c_full5312696_bam_to_final_v0.1.1"
LOCK_SCHEMA = "rnatr.full_runner_lock.v1"
PROJECT_ROOT = Path("/mnt/intelssd/rnatr_project")
DOWNLOADS = Path.home() / "Downloads"

ANALYSIS_RUN_ID_EXPECTED = "ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1"
MAPPING_RUN_ID = "ENCSR307SHM_full5312696_mm2splice_v1"
EXPECTED_READS = 5_312_696
EXPECTED_BAM_BYTES = 9_072_339_104
EXPECTED_BAM_SHA256 = "95fc869291dd471112e31e10f81571b918621d9008580b1d09ddd3a6fefbfb85"
EXPECTED_FASTQ_BYTES = 8_995_223_210
EXPECTED_FASTQ_MD5 = "23270f6b994db147df2f2f4c53f8358b"

KNOWN_BAD_TEMPLATE = DOWNLOADS / "rnatr_stage15c_run_full5312696_bam_to_final_v010.py"
KNOWN_BAD_TEMPLATE_SHA256 = "ec0ab9f75c539e5df280fff9078a3a64f29cd93b3c1b489b085664071688d9c9"

ARCH_SCRIPT = PROJECT_ROOT / "scripts/rnatr_stage15c_validate_144shard_execution_architecture_v0.1.1.py"
ARCH_SCRIPT_SHA256 = "fe8f4bdada0336d6e8afc0008f5800d920a49a28a1541f10a89b439d88770b72"
ARCH_META_ROOT = PROJECT_ROOT / "metadata/stage15c/144shard_execution_architecture_v0.1.1"
ARCH_CONTRACT = ARCH_META_ROOT / "fullscale_144shard_execution_contract_v0.1.1.tsv"
ARCH_CONTRACT_SHA256 = "aa933d41e75c365a58ba414a85f0415fb100bf29e9ab8974300520eb01738eec"
STAGE15B_RUN_ID = "ENCSR307SHM_stage15a500k_seed20260809_mm2splice_v1"
ARCH_QC = (
    PROJECT_ROOT / "qc/15_stage15c_execution_architecture" / STAGE15B_RUN_ID
    / "v0.1.1_144shard_500k/stage15c_144shard_execution_architecture.qc.tsv"
)
ARCH_QC_SHA256 = "43226464ef19572de3fcccef1a6e7fd169e22e20e8fa3b724f9d2f1080ce0437"
ARCH_RESOURCE = (
    PROJECT_ROOT / "qc/15_stage15c_execution_architecture" / STAGE15B_RUN_ID
    / "v0.1.1_144shard_500k/replicate_S144/stage15c_144shard_fullscale_resource_model.tsv"
)
ARCH_RESOURCE_SHA256 = "0f694387afd5320409aac021a52bd5ab942fd9b33d2446ccafa6c6060fabdc13"
INPUT_BINDING_QC = (
    PROJECT_ROOT / "qc/15_stage15c_fullscale_preflight/ENCSR307SHM/v0.1.0"
    / "stage15c_fullscale_preflight.qc.tsv"
)
INPUT_BINDING_QC_SHA256 = "8363e0967621183ae7085cc8dfcfbdd4277b84214dad0d88074d03d8c4e50547"

BUILD_META_ROOT = PROJECT_ROOT / "metadata/stage15c/contract_locked_full_runner_v0.1.1"
BUILD_QC_ROOT = (
    PROJECT_ROOT / "qc/15_stage15c_contract_locked_runner_build"
    / ANALYSIS_RUN_ID_EXPECTED / "v0.1.1"
)
DOC_PATH = PROJECT_ROOT / "docs/stage15c/RNA_TR_Scout_contract_driven_full_runner_build_v0.1.1.md"
BUILDER_INSTALL = PROJECT_ROOT / "scripts/rnatr_stage15c_build_contract_locked_full_runner_v0.1.1.py"
RUNNER_INSTALL = PROJECT_ROOT / "scripts/rnatr_stage15c_run_full5312696_bam_to_final_v0.1.1.py"
LOCK_INSTALL = BUILD_META_ROOT / "rnatr_stage15c_full_runner_lock_contract_v0.1.1.json"
RUNNER_DOWNLOAD = DOWNLOADS / "rnatr_stage15c_run_full5312696_bam_to_final_v011.py"
SUCCESS_BUNDLE = DOWNLOADS / "rnatr_stage15c_contract_locked_full_runner_build_v0.1.1.tar.gz"
FAILURE_BUNDLE = DOWNLOADS / "rnatr_stage15c_contract_locked_full_runner_build_v0.1.1_failure.tar.gz"

class BuildError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def ensure_exact(path: Path, expected_sha256: str) -> None:
    if not path.is_file() or path.stat().st_size <= 0:
        raise BuildError(f"missing/empty required artifact: {path}")
    observed = sha256_file(path)
    if observed != expected_sha256:
        raise BuildError(
            f"SHA-256 mismatch: {path}: expected={expected_sha256} observed={observed}"
        )


def read_two_column(path: Path) -> dict[str, str]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        header = next(reader, None)
        if not header or len(header) < 2:
            raise BuildError(f"invalid two-column TSV: {path}")
        return {row[0]: row[1] for row in reader if len(row) >= 2}


def read_dicts(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if not reader.fieldnames:
            raise BuildError(f"missing TSV header: {path}")
        return list(reader)


def atomic_write(path: Path, payload: bytes, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + f".part.{os.getpid()}")
    with tmp.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    tmp.chmod(mode)
    os.replace(tmp, path)


def install_exact_bytes(payload: bytes, destination: Path, mode: int = 0o644) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(payload).hexdigest()
    if destination.exists():
        if not destination.is_file() or sha256_file(destination) != digest:
            raise BuildError(f"refusing overwrite of different versioned file: {destination}")
        destination.chmod(mode)
        return "REUSED_EXACT"
    atomic_write(destination, payload, mode)
    return "INSTALLED_NEW"


def write_tsv(path: Path, rows: Iterable[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + f".part.{os.getpid()}")
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        handle.flush(); os.fsync(handle.fileno())
    os.replace(tmp, path)


def write_metrics(path: Path, metrics: Iterable[tuple[str, Any]]) -> None:
    write_tsv(path, ({"metric": k, "value": v} for k, v in metrics), ["metric", "value"])


def load_validated_contract() -> dict[str, Any]:
    for path, digest in (
        (ARCH_SCRIPT, ARCH_SCRIPT_SHA256),
        (ARCH_CONTRACT, ARCH_CONTRACT_SHA256),
        (ARCH_QC, ARCH_QC_SHA256),
        (ARCH_RESOURCE, ARCH_RESOURCE_SHA256),
        (INPUT_BINDING_QC, INPUT_BINDING_QC_SHA256),
        (KNOWN_BAD_TEMPLATE, KNOWN_BAD_TEMPLATE_SHA256),
    ):
        ensure_exact(path, digest)

    contract_rows = read_dicts(ARCH_CONTRACT)
    contract = {row["field"]: row for row in contract_rows}
    required_contract = {
        "planned_run_id": (ANALYSIS_RUN_ID_EXPECTED, "PROVISIONAL"),
        "read_coherent_shards": ("144", "VALIDATED_500K_EXACT_PARITY"),
        "active_shard_concurrency": ("12", "PASS"),
        "caller_workers_per_shard": ("2", "VALIDATED_500K"),
        "validator_workers": ("3", "VALIDATED_500K"),
        "validator_sort_buffer": ("512M", "VALIDATED_500K"),
        "scientific_output_12_vs_144_shards": ("true", "PASS"),
        "projected_shard_load_status": ("PASS", "PASS"),
        "full_post_11b_shard_load_hard_gate_required": ("true", "MANDATORY_FOR_FULL_RUNNER"),
        "resource_model_fit_status": ("PASS_EMPIRICAL_12_AND_144_SHARD_FIT", "PASS"),
        "full_runner_build_authorized": ("true", "PASS"),
        "full_empirical_run_authorized": ("false", "NOT_BY_THIS_STAGE"),
    }
    for key, (value, status) in required_contract.items():
        row = contract.get(key)
        if row is None or row.get("value") != value or row.get("status") != status:
            raise BuildError(f"validated contract mismatch: {key}: {row}")

    qc = read_two_column(ARCH_QC)
    required_qc = {
        "planned_full_run_id": ANALYSIS_RUN_ID_EXPECTED,
        "shard_count": "144",
        "stage_concurrency": "12",
        "caller_workers_per_shard": "2",
        "validator_workers": "3",
        "python_hash_seed": "0",
        "core_package_raw_and_logical_parity_to_12shard": "true",
        "memory_bounded_validator": "PASS",
        "atomic_publication": "PASS",
        "projected_shard_load_status": "PASS",
        "resource_model_fit_status": "PASS_EMPIRICAL_12_AND_144_SHARD_FIT",
        "full_memory_readiness_status": "PASS",
        "storage_status_after_audit": "PASS",
        "scientific_output_independent_of_12_vs_144_shards": "true",
        "full_post_11b_shard_load_hard_gate_required": "true",
        "provisional_full_runner_build_authorized": "true",
        "full_empirical_run_authorized": "false",
        "audit_status": "PASS",
    }
    for key, expected in required_qc.items():
        if qc.get(key) != expected:
            raise BuildError(f"validated architecture QC mismatch {key}: {qc.get(key)} != {expected}")

    resource = read_two_column(ARCH_RESOURCE)
    accepted_max = int(resource.get("accepted_12shard_max_candidate_rows", "-1"))
    if accepted_max != 164_204:
        raise BuildError(f"unexpected accepted candidate hard max: {accepted_max}")
    # The resource-model TSV and the top-level QC intentionally use slightly
    # different field names.  Bind to the resource-model schema itself, then
    # cross-check the corresponding top-level QC fields rather than aliasing
    # names by assumption.
    required_resource = {
        "projected_shard_load_status": "PASS",
        "model_fit_status": "PASS_EMPIRICAL_12_AND_144_SHARD_FIT",
        "memory_readiness_status": "PASS",
        "runtime_projection_status": "PASS_STRICT_PROJECTION",
    }
    for key, expected in required_resource.items():
        if resource.get(key) != expected:
            raise BuildError(
                f"resource model mismatch {key}: {resource.get(key)} != {expected}"
            )

    cross_schema_pairs = {
        "projected_shard_load_status": (
            resource.get("projected_shard_load_status"),
            qc.get("projected_shard_load_status"),
        ),
        "fit_status": (
            resource.get("model_fit_status"),
            qc.get("resource_model_fit_status"),
        ),
        "memory_readiness": (
            resource.get("memory_readiness_status"),
            qc.get("full_memory_readiness_status"),
        ),
        "runtime_projection": (
            resource.get("runtime_projection_status"),
            qc.get("runtime_projection_status"),
        ),
    }
    for label, (resource_value, qc_value) in cross_schema_pairs.items():
        if resource_value != qc_value:
            raise BuildError(
                f"resource/QC cross-schema mismatch {label}: "
                f"resource={resource_value} qc={qc_value}"
            )

    binding = read_two_column(INPUT_BINDING_QC)
    required_binding = {
        "planned_run_id": ANALYSIS_RUN_ID_EXPECTED,
        "runner_build_authorized": "true",
        "full_empirical_run_authorized": "false",
        "full_5_31m_run_started": "false",
        "audit_status": "PASS",
    }
    for key, expected in required_binding.items():
        if binding.get(key) != expected:
            raise BuildError(f"input-binding mismatch {key}: {binding.get(key)} != {expected}")

    return {
        "analysis_run_id": contract["planned_run_id"]["value"],
        "mapping_run_id": MAPPING_RUN_ID,
        "expected_reads": EXPECTED_READS,
        "expected_bam_bytes": EXPECTED_BAM_BYTES,
        "expected_bam_sha256": EXPECTED_BAM_SHA256,
        "expected_fastq_bytes": EXPECTED_FASTQ_BYTES,
        "expected_fastq_md5": EXPECTED_FASTQ_MD5,
        "read_coherent_shards": int(contract["read_coherent_shards"]["value"]),
        "active_shard_concurrency": int(contract["active_shard_concurrency"]["value"]),
        "caller_workers_per_shard": int(contract["caller_workers_per_shard"]["value"]),
        "validator_workers": int(contract["validator_workers"]["value"]),
        "validator_sort_buffer": contract["validator_sort_buffer"]["value"],
        "python_hash_seed": qc["python_hash_seed"],
        "post_11b_max_candidate_rows_per_shard": accepted_max,
        "validated_projection_minutes": float(qc["execution_architecture_adjusted_full_projection_minutes"]),
        "validated_projected_memory_fraction": float(qc["projected_full_memory_fraction"]),
        "full_post_11b_shard_load_hard_gate_required": True,
        "full_execution_authorized": False,
        "source_evidence": {
            "architecture_script": {"path": str(ARCH_SCRIPT), "sha256": ARCH_SCRIPT_SHA256},
            "architecture_contract": {"path": str(ARCH_CONTRACT), "sha256": ARCH_CONTRACT_SHA256},
            "architecture_qc": {"path": str(ARCH_QC), "sha256": ARCH_QC_SHA256},
            "architecture_resource_model": {"path": str(ARCH_RESOURCE), "sha256": ARCH_RESOURCE_SHA256},
            "input_binding_qc": {"path": str(INPUT_BINDING_QC), "sha256": INPUT_BINDING_QC_SHA256},
            "rejected_v010_implementation_template": {"path": str(KNOWN_BAD_TEMPLATE), "sha256": KNOWN_BAD_TEMPLATE_SHA256},
        },
    }


def make_lock_payload(contract: dict[str, Any]) -> bytes:
    lock = {
        "schema": LOCK_SCHEMA,
        "runner_version": RUNNER_VERSION,
        "analysis_run_id": contract["analysis_run_id"],
        "mapping_run_id": contract["mapping_run_id"],
        "input": {
            "reads": contract["expected_reads"],
            "bam_bytes": contract["expected_bam_bytes"],
            "bam_sha256": contract["expected_bam_sha256"],
            "fastq_bytes": contract["expected_fastq_bytes"],
            "fastq_md5": contract["expected_fastq_md5"],
        },
        "execution": {
            "read_coherent_shards": contract["read_coherent_shards"],
            "active_shard_concurrency": contract["active_shard_concurrency"],
            "caller_workers_per_shard": contract["caller_workers_per_shard"],
            "validator_workers": contract["validator_workers"],
            "validator_sort_buffer": contract["validator_sort_buffer"],
            "python_hash_seed": contract["python_hash_seed"],
        },
        "hard_gates": {
            "post_11b_candidate_rows_per_shard_max": contract["post_11b_max_candidate_rows_per_shard"],
            "post_11b_gate_must_precede_candidate_extraction": True,
            "post_11b_gate_must_precede_caller_materializer": True,
            "active_pipeline_modification_allowed": False,
            "ssot_modification_allowed": False,
            "core_schema_modification_allowed": False,
        },
        "validated_model": {
            "adjusted_projection_minutes": contract["validated_projection_minutes"],
            "projected_full_memory_fraction": contract["validated_projected_memory_fraction"],
        },
        "authorization": {
            "runner_build_authorized": True,
            "preflight_authorized": True,
            "full_execution_authorized": False,
            "unlock_requires_new_version_after_pro_review": True,
        },
        "source_evidence": contract["source_evidence"],
    }
    return (json.dumps(lock, sort_keys=True, indent=2) + "\n").encode("utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise BuildError(f"transform anchor {label} expected once, observed {count}")
    return text.replace(old, new, 1)


def transform_template(source: str, c: dict[str, Any], lock_sha256: str) -> str:
    text = source
    text = replace_once(text,
        'VERSION = "rnatr_stage15c_full5312696_bam_to_final_v0.1.0"',
        'VERSION = "rnatr_stage15c_full5312696_bam_to_final_v0.1.1"', 'version')
    text = replace_once(text,
        'RUN_ID = "ENCSR307SHM_full5312696_mm2splice_v1"',
        f'ANALYSIS_RUN_ID = {c["analysis_run_id"]!r}\nMAPPING_RUN_ID = {c["mapping_run_id"]!r}\nRUN_ID = ANALYSIS_RUN_ID',
        'run_ids')
    for old, new, label in (
        ('MAPPING_ROOT = PROJECT_ROOT / "results/11_mapping" / RUN_ID', 'MAPPING_ROOT = PROJECT_ROOT / "results/11_mapping" / MAPPING_RUN_ID', 'mapping_root'),
        ('MAPPING_QC_ROOT = PROJECT_ROOT / "qc/11_mapping" / RUN_ID', 'MAPPING_QC_ROOT = PROJECT_ROOT / "qc/11_mapping" / MAPPING_RUN_ID', 'mapping_qc_root'),
        ('FULL_BAM = MAPPING_ROOT / f"{RUN_ID}.sorted.bam"', 'FULL_BAM = MAPPING_ROOT / f"{MAPPING_RUN_ID}.sorted.bam"', 'bam_name'),
        ('MAPPING_QC = MAPPING_QC_ROOT / f"{RUN_ID}.mapping_qc.tsv"', 'MAPPING_QC = MAPPING_QC_ROOT / f"{MAPPING_RUN_ID}.mapping_qc.tsv"', 'mapping_qc_name'),
        ('READ_ID_QC = MAPPING_QC_ROOT / f"{RUN_ID}.read_id_parity.tsv"', 'READ_ID_QC = MAPPING_QC_ROOT / f"{MAPPING_RUN_ID}.read_id_parity.tsv"', 'read_id_qc_name'),
        ('MAPPING_ARTIFACT_MANIFEST = MAPPING_ROOT / f"{RUN_ID}.artifact_manifest.tsv"', 'MAPPING_ARTIFACT_MANIFEST = MAPPING_ROOT / f"{MAPPING_RUN_ID}.artifact_manifest.tsv"', 'mapping_manifest_name'),
        ('SHARDS = 60', f'SHARDS = {c["read_coherent_shards"]}', 'shards'),
    ):
        text = replace_once(text, old, new, label)

    # Versioned paths; all are inactive/provisional.
    text = text.replace('/ "v0.1.0"\n)', '/ "v0.1.1"\n)')
    text = text.replace('RNA_TR_Scout_fullscale_runner_execution_contract_v0.1.0.md', 'RNA_TR_Scout_fullscale_runner_execution_contract_v0.1.1.md')
    text = text.replace('rnatr_stage15c_run_full5312696_bam_to_final_v0.1.0.py', 'rnatr_stage15c_run_full5312696_bam_to_final_v0.1.1.py')
    text = text.replace('rnatr_stage15c_fullscale_runner_preflight_v0.1.0.tar.gz', 'rnatr_stage15c_fullscale_runner_preflight_v0.1.1.tar.gz')
    text = text.replace('rnatr_stage15c_full_empirical_run_v0.1.0.tar.gz', 'rnatr_stage15c_full_empirical_run_v0.1.1.tar.gz')
    text = text.replace('rnatr_stage15c_full_empirical_run_v0.1.0_failure.tar.gz', 'rnatr_stage15c_full_empirical_run_v0.1.1_failure.tar.gz')
    text = text.replace('rnatr_stage15c_fullscale_runner_preflight_v0.1.0', 'rnatr_stage15c_fullscale_runner_preflight_v0.1.1')
    text = text.replace('rnatr_stage15c_full_empirical_run_failure_v0.1.0', 'rnatr_stage15c_full_empirical_run_failure_v0.1.1')
    text = text.replace('rnatr_stage15c_full_empirical_run_v0.1.0', 'rnatr_stage15c_full_empirical_run_v0.1.1')
    text = text.replace('60_READ_COHERENT_SHARDS', f'{c["read_coherent_shards"]}_READ_COHERENT_SHARDS')
    text = text.replace('60 deterministic read-coherent shards', f'{c["read_coherent_shards"]} deterministic read-coherent shards')
    text = text.replace('60-shard', f'{c["read_coherent_shards"]}-shard')
    text = text.replace('60 shards', f'{c["read_coherent_shards"]} shards')

    anchor = 'CANDIDATE500_QC_SHA256 = "d843f1ee03be93b54840356547a66f0fd645b7c573a3299c7eccb535253fc89b"\n'
    insert = anchor + f'''\nARCH144_SCRIPT = PROJECT_ROOT / "scripts/rnatr_stage15c_validate_144shard_execution_architecture_v0.1.1.py"\nARCH144_SCRIPT_SHA256 = "{ARCH_SCRIPT_SHA256}"\nARCH144_CONTRACT = PROJECT_ROOT / "metadata/stage15c/144shard_execution_architecture_v0.1.1/fullscale_144shard_execution_contract_v0.1.1.tsv"\nARCH144_CONTRACT_SHA256 = "{ARCH_CONTRACT_SHA256}"\nARCH144_QC = (\n    PROJECT_ROOT / "qc/15_stage15c_execution_architecture" / STAGE15B_RUN_ID\n    / "v0.1.1_144shard_500k/stage15c_144shard_execution_architecture.qc.tsv"\n)\nARCH144_QC_SHA256 = "{ARCH_QC_SHA256}"\nARCH144_RESOURCE_MODEL = (\n    PROJECT_ROOT / "qc/15_stage15c_execution_architecture" / STAGE15B_RUN_ID\n    / "v0.1.1_144shard_500k/replicate_S144/stage15c_144shard_fullscale_resource_model.tsv"\n)\nARCH144_RESOURCE_MODEL_SHA256 = "{ARCH_RESOURCE_SHA256}"\nSTAGE15C_INPUT_BINDING_QC = (\n    PROJECT_ROOT / "qc/15_stage15c_fullscale_preflight" / SAMPLE_ID\n    / "v0.1.0/stage15c_fullscale_preflight.qc.tsv"\n)\nSTAGE15C_INPUT_BINDING_QC_SHA256 = "{INPUT_BINDING_QC_SHA256}"\nPOST_11B_MAX_CANDIDATE_ROWS_PER_SHARD = {c["post_11b_max_candidate_rows_per_shard"]}\nFULL_EXECUTION_AUTHORIZED = False\nRUNNER_LOCK_CONTRACT = PROJECT_ROOT / "metadata/stage15c/contract_locked_full_runner_v0.1.1/rnatr_stage15c_full_runner_lock_contract_v0.1.1.json"\nRUNNER_LOCK_CONTRACT_SHA256 = "{lock_sha256}"\n'''
    text = replace_once(text, anchor, insert, 'architecture_constants')

    guard_anchor = '        CANDIDATE500_QC: CANDIDATE500_QC_SHA256,\n'
    guard_insert = guard_anchor + '''        ARCH144_SCRIPT: ARCH144_SCRIPT_SHA256,\n        ARCH144_CONTRACT: ARCH144_CONTRACT_SHA256,\n        ARCH144_QC: ARCH144_QC_SHA256,\n        ARCH144_RESOURCE_MODEL: ARCH144_RESOURCE_MODEL_SHA256,\n        STAGE15C_INPUT_BINDING_QC: STAGE15C_INPUT_BINDING_QC_SHA256,\n        RUNNER_LOCK_CONTRACT: RUNNER_LOCK_CONTRACT_SHA256,\n'''
    text = replace_once(text, guard_anchor, guard_insert, 'hash_guards')

    verify_anchor = '\ndef verify_mapping_binding(*, recompute_large_hashes: bool) -> dict[str, Any]:\n'
    verify_func = f'''\ndef verify_stage15c_144_evidence() -> dict[str, Any]:\n    contract_rows = read_dicts(ARCH144_CONTRACT)\n    contract = {{row["field"]: row for row in contract_rows}}\n    required_contract = {{\n        "planned_run_id": (ANALYSIS_RUN_ID, "PROVISIONAL"),\n        "read_coherent_shards": (str(SHARDS), "VALIDATED_500K_EXACT_PARITY"),\n        "active_shard_concurrency": (str(STAGE_WORKERS), "PASS"),\n        "caller_workers_per_shard": (str(CALLER_WORKERS_PER_SHARD), "VALIDATED_500K"),\n        "validator_workers": (str(VALIDATOR_WORKERS), "VALIDATED_500K"),\n        "validator_sort_buffer": (EXTERNAL_SORT_BUFFER, "VALIDATED_500K"),\n        "scientific_output_12_vs_144_shards": ("true", "PASS"),\n        "projected_shard_load_status": ("PASS", "PASS"),\n        "full_post_11b_shard_load_hard_gate_required": ("true", "MANDATORY_FOR_FULL_RUNNER"),\n        "resource_model_fit_status": ("PASS_EMPIRICAL_12_AND_144_SHARD_FIT", "PASS"),\n        "full_runner_build_authorized": ("true", "PASS"),\n        "full_empirical_run_authorized": ("false", "NOT_BY_THIS_STAGE"),\n    }}\n    for key, (expected_value, expected_status) in required_contract.items():\n        row = contract.get(key)\n        if row is None or row.get("value") != expected_value or row.get("status") != expected_status:\n            raise RunnerError(f"144-shard contract mismatch {{key}}: {{row}}")\n    qc = read_two_column(ARCH144_QC)\n    required_qc = {{\n        "planned_full_run_id": ANALYSIS_RUN_ID,\n        "shard_count": str(SHARDS),\n        "stage_concurrency": str(STAGE_WORKERS),\n        "caller_workers_per_shard": str(CALLER_WORKERS_PER_SHARD),\n        "validator_workers": str(VALIDATOR_WORKERS),\n        "python_hash_seed": PYTHON_HASH_SEED,\n        "core_package_raw_and_logical_parity_to_12shard": "true",\n        "memory_bounded_validator": "PASS",\n        "atomic_publication": "PASS",\n        "projected_shard_load_status": "PASS",\n        "resource_model_fit_status": "PASS_EMPIRICAL_12_AND_144_SHARD_FIT",\n        "full_memory_readiness_status": "PASS",\n        "storage_status_after_audit": "PASS",\n        "scientific_output_independent_of_12_vs_144_shards": "true",\n        "full_post_11b_shard_load_hard_gate_required": "true",\n        "provisional_full_runner_build_authorized": "true",\n        "full_empirical_run_authorized": "false",\n        "audit_status": "PASS",\n    }}\n    for key, expected in required_qc.items():\n        if qc.get(key) != expected:\n            raise RunnerError(f"144-shard QC mismatch {{key}}: {{qc.get(key)}} != {{expected}}")\n    resource_model = read_two_column(ARCH144_RESOURCE_MODEL)\n    required_resource = {{\n        "accepted_12shard_max_candidate_rows": str(POST_11B_MAX_CANDIDATE_ROWS_PER_SHARD),\n        "projected_shard_load_status": "PASS",\n        "resource_model_fit_status": "PASS_EMPIRICAL_12_AND_144_SHARD_FIT",\n        "full_memory_readiness_status": "PASS",\n    }}\n    for key, expected in required_resource.items():\n        if resource_model.get(key) != expected:\n            raise RunnerError(f"144-shard resource mismatch {{key}}: {{resource_model.get(key)}} != {{expected}}")\n    input_binding = read_two_column(STAGE15C_INPUT_BINDING_QC)\n    required_binding = {{\n        "planned_run_id": ANALYSIS_RUN_ID,\n        "runner_build_authorized": "true",\n        "full_empirical_run_authorized": "false",\n        "full_5_31m_run_started": "false",\n        "audit_status": "PASS",\n    }}\n    for key, expected in required_binding.items():\n        if input_binding.get(key) != expected:\n            raise RunnerError(f"input-binding mismatch {{key}}: {{input_binding.get(key)}} != {{expected}}")\n    return {{\n        "validated_shards": SHARDS,\n        "validated_concurrency": STAGE_WORKERS,\n        "caller_workers_per_shard": CALLER_WORKERS_PER_SHARD,\n        "validator_workers": VALIDATOR_WORKERS,\n        "sort_buffer": EXTERNAL_SORT_BUFFER,\n        "post_11b_max_candidate_rows_per_shard": POST_11B_MAX_CANDIDATE_ROWS_PER_SHARD,\n        "validated_projection_minutes": float(qc["execution_architecture_adjusted_full_projection_minutes"]),\n        "validated_projected_memory_fraction": float(qc["projected_full_memory_fraction"]),\n    }}\n\n'''
    text = replace_once(text, verify_anchor, '\n' + verify_func + verify_anchor, 'verify_architecture')

    gate_anchor = '\ndef extract_candidate_fastqs(base, shards: list[Any]) -> tuple[float, list[dict[str, Any]]]:\n'
    gate_func = '''\ndef candidate_load_gate_decision(candidate_rows: Iterable[int]) -> tuple[bool, int, list[int]]:\n    values = [int(value) for value in candidate_rows]\n    if not values:\n        raise RunnerError("post-11b candidate-load gate received no shards")\n    offenders = [\n        index for index, value in enumerate(values)\n        if value > POST_11B_MAX_CANDIDATE_ROWS_PER_SHARD\n    ]\n    return len(offenders) == 0, max(values), offenders\n\n\ndef enforce_post_11b_candidate_load_hard_gate(shards: list[Any]) -> None:\n    values = [int(shard.candidate_rows) for shard in shards]\n    passed, observed_max, offenders = candidate_load_gate_decision(values)\n    rows = []\n    for index, shard in enumerate(shards):\n        value = int(shard.candidate_rows)\n        rows.append({\n            "shard": shard.name,\n            "candidate_rows": value,\n            "hard_max_candidate_rows": POST_11B_MAX_CANDIDATE_ROWS_PER_SHARD,\n            "status": "PASS" if value <= POST_11B_MAX_CANDIDATE_ROWS_PER_SHARD else "FAIL",\n        })\n    atomic_write_tsv(\n        QC_ROOT / "stage15c_fullscale_post_11b_candidate_load_hard_gate.tsv",\n        list(rows[0]),\n        rows,\n    )\n    atomic_write_metrics(\n        QC_ROOT / "stage15c_fullscale_post_11b_candidate_load_hard_gate.qc.tsv",\n        [\n            ("shards", len(shards)),\n            ("hard_max_candidate_rows_per_shard", POST_11B_MAX_CANDIDATE_ROWS_PER_SHARD),\n            ("observed_max_candidate_rows_per_shard", observed_max),\n            ("offending_shards", len(offenders)),\n            ("caller_materializer_started_before_gate", "false"),\n            ("gate_status", "PASS" if passed else "FAIL"),\n        ],\n    )\n    if not passed:\n        names = [shards[index].name for index in offenders]\n        raise RunnerError(\n            "POST_11B_CANDIDATE_LOAD_HARD_GATE_FAILED: "\n            f"max={observed_max} hard_max={POST_11B_MAX_CANDIDATE_ROWS_PER_SHARD} "\n            f"offenders={','.join(names)}; caller/materializer not started"\n        )\n\n'''
    text = replace_once(text, gate_anchor, '\n' + gate_func + gate_anchor, 'hard_gate_function')

    call_anchor = '        candidate_rows, candidate_reads = load_candidate_counts(base, shards)\n        temp_rows.append(temp_snapshot(shards, "after_11b"))\n'
    call_new = '        candidate_rows, candidate_reads = load_candidate_counts(base, shards)\n        enforce_post_11b_candidate_load_hard_gate(shards)\n        temp_rows.append(temp_snapshot(shards, "after_11b"))\n'
    text = replace_once(text, call_anchor, call_new, 'hard_gate_call')

    preflight_anchor = '    verify_stage15b_evidence()\n    mapping = verify_mapping_binding(recompute_large_hashes=True)\n'
    preflight_new = '    verify_stage15b_evidence()\n    architecture = verify_stage15c_144_evidence()\n    mapping = verify_mapping_binding(recompute_large_hashes=True)\n'
    text = replace_once(text, preflight_anchor, preflight_new, 'preflight_architecture_gate')

    preflight_qc_old = '        ("execute_authorized", "true"),\n        ("preflight_status", "PASS"),\n        ("next_gate", "EXECUTE_CLEAN_EMPIRICAL_FULL_5_31M_BAM_TO_FINAL"),'
    preflight_qc_new = '        ("validated_architecture_shards", architecture["validated_shards"]),\n        ("validated_projection_minutes", architecture["validated_projection_minutes"]),\n        ("post_11b_candidate_rows_per_shard_hard_max", architecture["post_11b_max_candidate_rows_per_shard"]),\n        ("execute_authorized", "false"),\n        ("runner_execution_locked", "true"),\n        ("preflight_status", "PASS_LOCKED_READY_FOR_PRO_REVIEW"),\n        ("next_gate", "UPLOAD_PREFLIGHT_BUNDLE_FOR_PRO_REVIEW_AND_EXECUTION_UNLOCK"),'
    text = replace_once(text, preflight_qc_old, preflight_qc_new, 'preflight_lock_qc')
    text = replace_once(text, '    print(f"preflight_status\\tPASS")', '    print(f"preflight_status\\tPASS_LOCKED_READY_FOR_PRO_REVIEW")', 'preflight_status_print')
    text = replace_once(text, '    print("execute_authorized\\ttrue")', '    print("execute_authorized\\tfalse")\n    print("runner_execution_locked\\ttrue")', 'execute_auth_print')

    execute_anchor = 'def execute(confirm_run_id: str) -> int:\n    global FULL_RUN_ACTUALLY_STARTED\n'
    execute_new = 'def execute(confirm_run_id: str) -> int:\n    global FULL_RUN_ACTUALLY_STARTED\n    if not FULL_EXECUTION_AUTHORIZED:\n        raise RunnerError("FULL_EXECUTION_LOCKED_PENDING_PRO_REVIEW_OF_V0.1.1_PREFLIGHT")\n'
    text = replace_once(text, execute_anchor, execute_new, 'execute_lock')

    # Add the distinct run IDs to the immutable execution record.
    contract_anchor = '            ("run_id", RUN_ID),\n            ("input_bam", FULL_BAM),'
    contract_new = '            ("run_id", RUN_ID),\n            ("analysis_run_id", ANALYSIS_RUN_ID),\n            ("mapping_run_id", MAPPING_RUN_ID),\n            ("input_bam", FULL_BAM),'
    text = replace_once(text, contract_anchor, contract_new, 'execution_run_ids')

    text = text.replace('## Why the provisional architecture uses 144 shards', '## Validated provisional architecture: 144 shards')
    return text


def assignment_map(tree: ast.Module) -> dict[str, ast.AST]:
    result: dict[str, ast.AST] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            result[node.targets[0].id] = node.value
    return result


def literal(assignments: dict[str, ast.AST], name: str) -> Any:
    node = assignments.get(name)
    if node is None:
        raise BuildError(f"missing top-level constant: {name}")
    try:
        return ast.literal_eval(node)
    except Exception as exc:
        raise BuildError(f"top-level constant is not literal: {name}: {ast.unparse(node)}") from exc


def function_node(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise BuildError(f"missing function: {name}")


def call_lines(fn: ast.FunctionDef, name: str) -> list[int]:
    lines = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            target = node.func
            called = target.id if isinstance(target, ast.Name) else target.attr if isinstance(target, ast.Attribute) else None
            if called == name:
                lines.append(node.lineno)
    return sorted(lines)


def audit_runner_source(source: str, c: dict[str, Any], lock_sha256: str, *, require_locked: bool) -> list[str]:
    errors: list[str] = []
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [f"SYNTAX_ERROR:{exc}"]
    assignments = assignment_map(tree)

    expected_literals = {
        "VERSION": RUNNER_VERSION,
        "ANALYSIS_RUN_ID": c["analysis_run_id"],
        "MAPPING_RUN_ID": c["mapping_run_id"],
        "SHARDS": c["read_coherent_shards"],
        "STAGE_WORKERS": c["active_shard_concurrency"],
        "CALLER_PIPELINE_WORKERS": c["active_shard_concurrency"],
        "CALLER_WORKERS_PER_SHARD": c["caller_workers_per_shard"],
        "VALIDATOR_WORKERS": c["validator_workers"],
        "EXTERNAL_SORT_BUFFER": c["validator_sort_buffer"],
        "PYTHON_HASH_SEED": c["python_hash_seed"],
        "POST_11B_MAX_CANDIDATE_ROWS_PER_SHARD": c["post_11b_max_candidate_rows_per_shard"],
        "RUNNER_LOCK_CONTRACT_SHA256": lock_sha256,
        "FULL_EXECUTION_AUTHORIZED": False if require_locked else True,
    }
    for name, expected in expected_literals.items():
        try:
            observed = literal(assignments, name)
            if observed != expected:
                errors.append(f"CONST_MISMATCH:{name}:{observed!r}!={expected!r}")
        except BuildError as exc:
            errors.append(str(exc))

    run_id_node = assignments.get("RUN_ID")
    if not isinstance(run_id_node, ast.Name) or run_id_node.id != "ANALYSIS_RUN_ID":
        errors.append("RUN_ID_NOT_ALIAS_OF_ANALYSIS_RUN_ID")

    for name in ("MAPPING_ROOT", "MAPPING_QC_ROOT", "FULL_BAM", "MAPPING_QC", "READ_ID_QC", "MAPPING_ARTIFACT_MANIFEST"):
        node = assignments.get(name)
        if node is None or "MAPPING_RUN_ID" not in ast.unparse(node):
            errors.append(f"MAPPING_PATH_NOT_BOUND_TO_MAPPING_RUN_ID:{name}")

    for required_fn in (
        "verify_stage15c_144_evidence",
        "candidate_load_gate_decision",
        "enforce_post_11b_candidate_load_hard_gate",
        "execute",
    ):
        try:
            function_node(tree, required_fn)
        except BuildError as exc:
            errors.append(str(exc))

    try:
        execute_fn = function_node(tree, "execute")
        load_lines = call_lines(execute_fn, "load_candidate_counts")
        gate_lines = call_lines(execute_fn, "enforce_post_11b_candidate_load_hard_gate")
        extract_lines = call_lines(execute_fn, "extract_candidate_fastqs")
        caller_lines = call_lines(execute_fn, "run_caller_materializer")
        if not (len(load_lines) == len(gate_lines) == len(extract_lines) == len(caller_lines) == 1):
            errors.append(
                f"CALL_CARDINALITY:load={load_lines},gate={gate_lines},extract={extract_lines},caller={caller_lines}"
            )
        elif not (load_lines[0] < gate_lines[0] < extract_lines[0] < caller_lines[0]):
            errors.append(
                f"HARD_GATE_CALL_ORDER_INVALID:{load_lines[0]},{gate_lines[0]},{extract_lines[0]},{caller_lines[0]}"
            )
        if require_locked:
            lock_if_lines = []
            for node in ast.walk(execute_fn):
                if isinstance(node, ast.If) and isinstance(node.test, ast.UnaryOp) and isinstance(node.test.op, ast.Not):
                    if isinstance(node.test.operand, ast.Name) and node.test.operand.id == "FULL_EXECUTION_AUTHORIZED":
                        lock_if_lines.append(node.lineno)
            first_science = min(load_lines + extract_lines + caller_lines) if (load_lines or extract_lines or caller_lines) else 10**9
            if not lock_if_lines or min(lock_if_lines) >= first_science:
                errors.append("EXECUTION_LOCK_NOT_EARLY")
    except BuildError as exc:
        errors.append(str(exc))

    if '"execute_authorized", "false"' not in source:
        errors.append("PREFLIGHT_DOES_NOT_RECORD_EXECUTE_FALSE")
    if '"runner_execution_locked", "true"' not in source:
        errors.append("PREFLIGHT_DOES_NOT_RECORD_LOCK_TRUE")
    if "FULL5312696_60_READ_COHERENT_SHARDS" in source or "SHARDS = 60" in source:
        errors.append("RESIDUAL_UNVALIDATED_60_SHARD_ARCHITECTURE")
    if c["analysis_run_id"] == c["mapping_run_id"]:
        errors.append("CONTRACT_RUN_ID_TYPES_COLLAPSED")
    return errors


def mutate_one(source: str, old: str, new: str, label: str) -> str:
    if source.count(old) != 1:
        raise BuildError(f"negative mutation anchor {label} not unique: {source.count(old)}")
    return source.replace(old, new, 1)


def negative_static_tests(generated: str, c: dict[str, Any], lock_sha256: str) -> list[dict[str, Any]]:
    cases = [
        ("mutate_shards_144_to_60", f'SHARDS = {c["read_coherent_shards"]}', 'SHARDS = 60', "CONST_MISMATCH:SHARDS"),
        ("mutate_analysis_run_id", f'ANALYSIS_RUN_ID = {c["analysis_run_id"]!r}', f'ANALYSIS_RUN_ID = {c["mapping_run_id"]!r}', "CONST_MISMATCH:ANALYSIS_RUN_ID"),
        ("mutate_hard_max_plus_one", f'POST_11B_MAX_CANDIDATE_ROWS_PER_SHARD = {c["post_11b_max_candidate_rows_per_shard"]}', f'POST_11B_MAX_CANDIDATE_ROWS_PER_SHARD = {c["post_11b_max_candidate_rows_per_shard"] + 1}', "CONST_MISMATCH:POST_11B_MAX_CANDIDATE_ROWS_PER_SHARD"),
        ("mutate_execution_unlock", 'FULL_EXECUTION_AUTHORIZED = False', 'FULL_EXECUTION_AUTHORIZED = True', "CONST_MISMATCH:FULL_EXECUTION_AUTHORIZED"),
        ("remove_hard_gate_call", '        enforce_post_11b_candidate_load_hard_gate(shards)\n', '        pass  # negative mutation removes mandatory post-11b hard gate\n', "CALL_CARDINALITY"),
    ]
    rows = []
    for name, old, new, expected_fragment in cases:
        mutated = mutate_one(generated, old, new, name)
        errors = audit_runner_source(mutated, c, lock_sha256, require_locked=True)
        passed = any(expected_fragment in error for error in errors)
        rows.append({
            "test": name,
            "expected_rejection_fragment": expected_fragment,
            "auditor_error_count": len(errors),
            "auditor_errors": ";".join(errors),
            "status": "PASS" if passed else "FAIL",
        })
        if not passed:
            raise BuildError(f"negative static test did not reject mutation {name}: {errors}")
    return rows


def dynamic_safety_tests(path: Path, c: dict[str, Any]) -> list[dict[str, Any]]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    gate_fn = function_node(tree, "candidate_load_gate_decision")
    segment = ast.get_source_segment(source, gate_fn)
    if not segment:
        raise BuildError("cannot extract candidate_load_gate_decision source")

    class IsolatedRunnerError(RuntimeError):
        pass

    namespace: dict[str, Any] = {
        "Iterable": Iterable,
        "RunnerError": IsolatedRunnerError,
        "POST_11B_MAX_CANDIDATE_ROWS_PER_SHARD": c["post_11b_max_candidate_rows_per_shard"],
    }
    exec(compile(segment, "<isolated_candidate_gate>", "exec"), namespace, namespace)
    decision = namespace["candidate_load_gate_decision"]
    limit = c["post_11b_max_candidate_rows_per_shard"]
    ok, observed, offenders = decision([1, limit, 100])
    case1 = ok is True and observed == limit and offenders == []
    bad_ok, bad_observed, bad_offenders = decision([limit + 1])
    case2 = bad_ok is False and bad_observed == limit + 1 and bad_offenders == [0]

    execute_fn = function_node(tree, "execute")
    lock_lines = []
    for node in ast.walk(execute_fn):
        if isinstance(node, ast.If) and isinstance(node.test, ast.UnaryOp) and isinstance(node.test.op, ast.Not):
            if isinstance(node.test.operand, ast.Name) and node.test.operand.id == "FULL_EXECUTION_AUTHORIZED":
                lock_lines.append(node.lineno)
    science_lines = []
    for name in ("load_candidate_counts", "extract_candidate_fastqs", "run_caller_materializer"):
        science_lines.extend(call_lines(execute_fn, name))
    case3 = bool(lock_lines) and bool(science_lines) and min(lock_lines) < min(science_lines)

    rows = [
        {"test": "candidate_gate_at_limit_accepts", "status": "PASS" if case1 else "FAIL", "detail": f"ok={ok};observed={observed};offenders={offenders}"},
        {"test": "candidate_gate_limit_plus_one_rejects", "status": "PASS" if case2 else "FAIL", "detail": f"ok={bad_ok};observed={bad_observed};offenders={bad_offenders}"},
        {"test": "execute_lock_precedes_scientific_calls", "status": "PASS" if case3 else "FAIL", "detail": f"lock_lines={lock_lines};science_lines={sorted(science_lines)}"},
    ]
    if any(row["status"] != "PASS" for row in rows):
        raise BuildError(f"dynamic/structural safety test failure: {rows}")
    return rows


def known_bad_rejection(template: str, c: dict[str, Any], lock_sha256: str) -> dict[str, Any]:
    errors = audit_runner_source(template, c, lock_sha256, require_locked=True)
    required_fragments = (
        "missing top-level constant: ANALYSIS_RUN_ID",
        "CONST_MISMATCH:SHARDS",
        "missing function: enforce_post_11b_candidate_load_hard_gate",
        "missing top-level constant: FULL_EXECUTION_AUTHORIZED",
    )
    status = "PASS" if all(any(fragment in e for e in errors) for fragment in required_fragments) else "FAIL"
    if status != "PASS":
        raise BuildError(f"auditor did not reject known bad v0.1.0 as expected: {errors}")
    return {
        "artifact": str(KNOWN_BAD_TEMPLATE),
        "sha256": KNOWN_BAD_TEMPLATE_SHA256,
        "classification": "DO_NOT_EXECUTE_REJECTED_USED_ONLY_AS_IMPLEMENTATION_TEMPLATE",
        "auditor_errors": ";".join(errors),
        "status": status,
    }


def make_bundle(root: Path, bundle: Path) -> str:
    tmp = bundle.with_name("." + bundle.name + f".part.{os.getpid()}")
    with tarfile.open(tmp, "w:gz", format=tarfile.PAX_FORMAT) as tar:
        tar.add(root, arcname=root.name)
    os.replace(tmp, bundle)
    digest = sha256_file(bundle)
    bundle.with_name(bundle.name + ".sha256").write_text(f"{digest}  {bundle.name}\n", encoding="utf-8")
    return digest


def artifact_manifest(root: Path) -> None:
    rows = []
    for path in sorted(p for p in root.rglob("*") if p.is_file() and p.name != "artifact_manifest.tsv"):
        rows.append({"relative_path": str(path.relative_to(root)), "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    write_tsv(root / "artifact_manifest.tsv", rows, ["relative_path", "bytes", "sha256"])


def build() -> int:
    started = time.time()
    if PROJECT_ROOT != Path("/mnt/intelssd/rnatr_project"):
        raise BuildError("unexpected project root")
    if BUILD_QC_ROOT.exists() or BUILD_META_ROOT.exists():
        raise BuildError(
            "versioned build root already exists; preserve and review rather than overwrite: "
            f"{BUILD_QC_ROOT} {BUILD_META_ROOT}"
        )
    c = load_validated_contract()
    lock_payload = make_lock_payload(c)
    lock_sha = hashlib.sha256(lock_payload).hexdigest()
    template = KNOWN_BAD_TEMPLATE.read_text(encoding="utf-8")
    known_bad = known_bad_rejection(template, c, lock_sha)
    generated = transform_template(template, c, lock_sha)
    compile(generated, str(RUNNER_DOWNLOAD), "exec")
    audit_errors = audit_runner_source(generated, c, lock_sha, require_locked=True)
    if audit_errors:
        raise BuildError("generated runner static audit failed: " + ";".join(audit_errors))
    static_negative = negative_static_tests(generated, c, lock_sha)

    work = Path(tempfile.mkdtemp(prefix="rnatr_contract_locked_build_"))
    package = work / "rnatr_stage15c_contract_locked_full_runner_build_v0.1.1"
    package.mkdir()
    try:
        runner_bytes = generated.encode("utf-8")
        runner_path = package / RUNNER_DOWNLOAD.name
        atomic_write(runner_path, runner_bytes, 0o755)
        lock_path = package / LOCK_INSTALL.name
        atomic_write(lock_path, lock_payload, 0o644)
        dynamic = dynamic_safety_tests(runner_path, c)
        runner_sha = sha256_file(runner_path)
        # Re-read/re-hash after all tests; bytes must not change after this point.
        runner_sha_second = sha256_file(runner_path)
        if runner_sha != runner_sha_second:
            raise BuildError("runner hash changed between final hash passes")

        source_guards = [
            {"artifact": str(path), "expected_sha256": digest, "observed_sha256": sha256_file(path), "status": "PASS"}
            for path, digest in (
                (ARCH_SCRIPT, ARCH_SCRIPT_SHA256),
                (ARCH_CONTRACT, ARCH_CONTRACT_SHA256),
                (ARCH_QC, ARCH_QC_SHA256),
                (ARCH_RESOURCE, ARCH_RESOURCE_SHA256),
                (INPUT_BINDING_QC, INPUT_BINDING_QC_SHA256),
                (KNOWN_BAD_TEMPLATE, KNOWN_BAD_TEMPLATE_SHA256),
            )
        ]
        write_tsv(package / "source_evidence_guards.tsv", source_guards, ["artifact", "expected_sha256", "observed_sha256", "status"])
        write_tsv(package / "known_bad_v010_rejection.tsv", [known_bad], ["artifact", "sha256", "classification", "auditor_errors", "status"])
        write_tsv(package / "negative_static_mutation_tests.tsv", static_negative, ["test", "expected_rejection_fragment", "auditor_error_count", "auditor_errors", "status"])
        write_tsv(package / "dynamic_safety_tests.tsv", dynamic, ["test", "status", "detail"])

        qc_metrics = [
            ("builder_version", BUILDER_VERSION),
            ("runner_version", RUNNER_VERSION),
            ("analysis_run_id", c["analysis_run_id"]),
            ("mapping_run_id", c["mapping_run_id"]),
            ("source_architecture_contract_sha256", ARCH_CONTRACT_SHA256),
            ("source_architecture_qc_sha256", ARCH_QC_SHA256),
            ("source_architecture_resource_model_sha256", ARCH_RESOURCE_SHA256),
            ("lock_contract_sha256", lock_sha),
            ("runner_sha256", runner_sha),
            ("runner_bytes", runner_path.stat().st_size),
            ("read_coherent_shards", c["read_coherent_shards"]),
            ("active_shard_concurrency", c["active_shard_concurrency"]),
            ("caller_workers_per_shard", c["caller_workers_per_shard"]),
            ("validator_workers", c["validator_workers"]),
            ("post_11b_candidate_rows_per_shard_hard_max", c["post_11b_max_candidate_rows_per_shard"]),
            ("known_bad_v010_rejected", "true"),
            ("static_audit", "PASS"),
            ("negative_static_mutation_tests", "PASS"),
            ("dynamic_candidate_gate_tests", "PASS"),
            ("execution_lock_test", "PASS"),
            ("runner_execution_locked", "true"),
            ("preflight_authorized", "true"),
            ("full_empirical_run_authorized", "false"),
            ("full_5_31m_run_started", "false"),
            ("active_pipeline_modified", "false"),
            ("ssot_modified", "false"),
            ("core_schema_modified", "false"),
            ("audit_status", "PASS"),
            ("next_gate", "RUN_V0.1.1_PREFLIGHT_ONLY_AND_UPLOAD_BUNDLE_FOR_PRO_REVIEW"),
            ("elapsed_seconds", f"{time.time() - started:.6f}"),
        ]
        write_metrics(package / "contract_locked_runner_build.qc.tsv", qc_metrics)

        doc = f'''# RNA-TR-Scout Stage 15C contract-driven full runner build v0.1.1\n\nThis build changes the development control plane, not the scientific core. Builder v0.1.1 is an orchestration/schema-binding amendment: v0.1.0 incorrectly requested top-level QC field names from the resource-model TSV and stopped before runner generation. v0.1.1 binds each file to its own schema and cross-checks the corresponding values across files. The validated 144-shard scientific/execution contract is unchanged.\n\nThe sole execution architecture source is the validated Stage 15C 144-shard contract (`{ARCH_CONTRACT_SHA256}`). The generated runner cannot choose a different shard count or full analysis run ID. A post-11b candidate-load hard gate of {c["post_11b_max_candidate_rows_per_shard"]:,} rows/shard is mandatory and is statically required to execute before candidate extraction and before caller/materializer.\n\nThe prior v0.1.0 runner (`{KNOWN_BAD_TEMPLATE_SHA256}`) is retained as failure provenance and is rejected by the new auditor. It is used only as an implementation template from which contract-controlled substitutions are made.\n\nThe v0.1.1 generated runner is intentionally execution-locked. Only `--preflight` is authorized. Full execution requires a new version after Pro review of the v0.1.1 preflight bundle. Active pipeline, SSOT, core schema, caller, materializer, accepted 500k results, and full BAM/FASTQ are not modified by this build.\n'''
        atomic_write(package / "RNA_TR_Scout_contract_driven_full_runner_build_v0.1.1.md", doc.encode("utf-8"), 0o644)
        shutil.copy2(Path(__file__).resolve(), package / "rnatr_stage15c_build_contract_locked_full_runner_v010.py")
        artifact_manifest(package)

        # Install exact versioned artifacts only after all tests pass.
        builder_bytes = Path(__file__).resolve().read_bytes()
        install_statuses = {
            "builder": install_exact_bytes(builder_bytes, BUILDER_INSTALL, 0o755),
            "runner": install_exact_bytes(runner_bytes, RUNNER_INSTALL, 0o755),
            "lock": install_exact_bytes(lock_payload, LOCK_INSTALL, 0o644),
            "qc": install_exact_bytes((package / "contract_locked_runner_build.qc.tsv").read_bytes(), BUILD_QC_ROOT / "contract_locked_runner_build.qc.tsv", 0o644),
            "known_bad_rejection": install_exact_bytes((package / "known_bad_v010_rejection.tsv").read_bytes(), BUILD_QC_ROOT / "known_bad_v010_rejection.tsv", 0o644),
            "negative_static": install_exact_bytes((package / "negative_static_mutation_tests.tsv").read_bytes(), BUILD_QC_ROOT / "negative_static_mutation_tests.tsv", 0o644),
            "dynamic_safety": install_exact_bytes((package / "dynamic_safety_tests.tsv").read_bytes(), BUILD_QC_ROOT / "dynamic_safety_tests.tsv", 0o644),
            "doc": install_exact_bytes((package / "RNA_TR_Scout_contract_driven_full_runner_build_v0.1.1.md").read_bytes(), DOC_PATH, 0o644),
        }
        write_tsv(package / "project_installation.tsv", ({"artifact": k, "status": v} for k, v in install_statuses.items()), ["artifact", "status"])
        # Downloads: exact generated bytes + SHA sidecar. Never overwrite different bytes.
        download_status = install_exact_bytes(runner_bytes, RUNNER_DOWNLOAD, 0o755)
        runner_sidecar = RUNNER_DOWNLOAD.with_name(RUNNER_DOWNLOAD.name + ".sha256")
        sidecar_payload = f"{runner_sha}  {RUNNER_DOWNLOAD.name}\n".encode("utf-8")
        install_exact_bytes(sidecar_payload, runner_sidecar, 0o644)

        artifact_manifest(package)
        bundle_sha = make_bundle(package, SUCCESS_BUNDLE)
        print("===== RNA-TR-Scout Stage 15C contract-locked runner build =====")
        print("build_status\tPASS")
        print(f"analysis_run_id\t{c['analysis_run_id']}")
        print(f"mapping_run_id\t{c['mapping_run_id']}")
        print(f"read_coherent_shards\t{c['read_coherent_shards']}")
        print(f"active_shard_concurrency\t{c['active_shard_concurrency']}")
        print(f"post_11b_candidate_rows_per_shard_hard_max\t{c['post_11b_max_candidate_rows_per_shard']}")
        print("known_bad_v010_rejected\ttrue")
        print("negative_mutation_tests\tPASS")
        print("dynamic_safety_tests\tPASS")
        print("runner_execution_locked\ttrue")
        print("full_5_31m_run_started\tfalse")
        print("active_pipeline_modified\tfalse")
        print("ssot_modified\tfalse")
        print(f"LOCK_CONTRACT_SHA256\t{lock_sha}")
        print(f"RUNNER\t{RUNNER_DOWNLOAD}")
        print(f"RUNNER_SHA256\t{runner_sha}")
        print(f"RUNNER_DOWNLOAD_INSTALLATION\t{download_status}")
        print(f"OUTPUT_BUNDLE\t{SUCCESS_BUNDLE}")
        print(f"OUTPUT_BUNDLE_SHA256\t{bundle_sha}")
        print("NEXT_GATE\tRUN_GENERATED_V0.1.1_WITH_--preflight_ONLY")
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and audit the contract-locked Stage15C full runner v0.1.1 (builder amendment v0.1.1)")
    parser.parse_args()
    try:
        return build()
    except Exception as exc:
        print(f"BUILD_FAIL\t{type(exc).__name__}\t{exc}", file=sys.stderr)
        raise

if __name__ == "__main__":
    raise SystemExit(main())
