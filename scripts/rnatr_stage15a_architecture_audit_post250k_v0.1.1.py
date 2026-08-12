#!/usr/bin/env python3
from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.util
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import traceback
from pathlib import Path
from typing import Any, Iterable

VERSION = "rnatr_stage15a_architecture_consistency_audit_post250k_v0.1.1"
PROJECT_ROOT = Path("/mnt/intelssd/rnatr_project")
RUN_ID = "ENCSR307SHM_stage15a250k_seed20260808_mm2splice_v1"
INTERNAL_RUN_ID = "ENCSR307SHM_pilot100k_mm2splice_v1"

RESULT_BASE = (
    PROJECT_ROOT / "results/15_stage15a_bam_to_final" / RUN_ID
    / "v0.1.2_250k_scaling"
)
SCALING_QC_BASE = (
    PROJECT_ROOT / "qc/15_stage15a_bam_to_final" / RUN_ID
    / "v0.1.2_250k_scaling"
)
AUDIT_ROOT = (
    PROJECT_ROOT / "qc/15_architecture_consistency_audit" / RUN_ID
    / "post_250k_v0.1.1"
)
DOC_PATH = (
    PROJECT_ROOT / "docs/stage15a"
    / "RNA_TR_Scout_Architecture_consistency_audit_post250k_v0.1.1.md"
)
INSTALL_PATH = (
    PROJECT_ROOT / "scripts"
    / "rnatr_stage15a_architecture_audit_post250k_v0.1.1.py"
)

SSOT_ROOT = PROJECT_ROOT / "metadata/ssot"
SSOT_CLI = SSOT_ROOT / "rnatr_ssot.py"
SSOT_DB = SSOT_ROOT / "rnatr_ssot.sqlite"
SSOT_EXPORTS = SSOT_ROOT / "exports"
CURRENT_PIPELINE = SSOT_EXPORTS / "current_pipeline.tsv"
CURRENT_RESULTS = SSOT_EXPORTS / "current_results.tsv"
CURRENT_CONTRACTS = SSOT_EXPORTS / "current_algorithm_contract.tsv"
CURRENT_QUESTIONS = SSOT_EXPORTS / "current_open_questions.tsv"
CURRENT_LIMITATIONS = SSOT_EXPORTS / "current_known_limitations.tsv"

RELEASE_GATES = PROJECT_ROOT / "validation/release_gates_v0.2.3.tsv"
BIOLOGY_CONTRACT = (
    PROJECT_ROOT / "docs/stage15a"
    / "RNA_TR_Scout_Biology_ready_interpretation_output_contract_v0.1.0.md"
)

SCALING_RUNNER = (
    PROJECT_ROOT / "scripts/rnatr_stage15a_run_scaling_250k_v0.1.2.py"
)
FAST_11E = (
    PROJECT_ROOT / "scripts/rnatr_stage15a_fast_motif_jobs_scaling_v0.2.2.2.py"
)
BASE_PERFORMANCE_RUNNER = (
    PROJECT_ROOT / "scripts/rnatr_stage15a_run_performance_100k_v0.2.2.1.py"
)

FINAL_QC = SCALING_QC_BASE / "stage15a_scaling_250k.qc.tsv"
PACKAGE_REPRO = SCALING_QC_BASE / "stage15a_scaling_250k_package_reproducibility.tsv"
CALLER_REPRO = SCALING_QC_BASE / "stage15a_scaling_250k_caller_reproducibility.tsv"
NESTED_100K = SCALING_QC_BASE / "stage15a_scaling_250k_nested_100k_package_parity.tsv"
STAGE_MODEL = SCALING_QC_BASE / "stage15a_scaling_250k_stage_model.tsv"

CHECKPOINT_MANIFEST_A = (
    SCALING_QC_BASE / "replicate_A/stage15a_scaling_250k_checkpoint_manifest.tsv"
)
CHECKPOINT_MANIFEST_B = (
    SCALING_QC_BASE / "replicate_B/stage15a_scaling_250k_checkpoint_manifest.tsv"
)
CHECKPOINT_QC_A = (
    SCALING_QC_BASE / "replicate_A/stage15a_scaling_250k_checkpoint.qc.tsv"
)
CHECKPOINT_QC_B = (
    SCALING_QC_BASE / "replicate_B/stage15a_scaling_250k_checkpoint.qc.tsv"
)
REP_QC_A = SCALING_QC_BASE / "replicate_A/stage15a_scaling_250k_replicate.qc.tsv"
REP_QC_B = SCALING_QC_BASE / "replicate_B/stage15a_scaling_250k_replicate.qc.tsv"

EXPECTED_SHA = {
    SSOT_CLI: "6e558822fedb1704f4f774130b4bb164826cc61bc8a3d6eca78fec692d8a7658",
    SSOT_DB: "9fbbef951130ed2128703c1e7f369d0105226d5698fc8718ae12b1cadb63f17a",
    RELEASE_GATES: "5e7938b097fe2210e3cb159c10f424c11f2633f6d4452114fa894f359da681db",
    BIOLOGY_CONTRACT: "90a86b3b5391abfbd17b6766254af307134f21a9357b50f8b28b0004d7148a87",
    SCALING_RUNNER: "dbc78c93087bf5bc74d6fea2c47b1c3d6c2986b62de9e7a7e73c21993facb375",
    FAST_11E: "3e36454a515cd8c0411957000099867b582ae7d2bef78b7fe2ebd61bf09f4dc4",
    BASE_PERFORMANCE_RUNNER: "7bfb7018cea80cd92854882751cffb49bea817296f69866801a64f9529c5e1a8",
    FINAL_QC: "a2504e27c84ca3d77a53c4484d977042259c2f92caeb4962479b065d80caffea",
    PACKAGE_REPRO: "88d2964250995734dc927902b2fb8fb1c6aaaf32dc885ecccd59af0a131e7af6",
    CALLER_REPRO: "85ed21187acd95f4422fbe089f4a33a974337ef3dddec2c7c713ec56ca01c790",
    NESTED_100K: "5f013c1f8be6997beb1b58c377641701e48d04b7b0b26405344aef7209fa766f",
    CHECKPOINT_MANIFEST_A: "4eb500026b95700de95877421801fc312bcba4f423d20d1605c9d67165228cae",
    CHECKPOINT_MANIFEST_B: "9763f5ac94da6fdf9c2ada92687681440c0cea054920a567cfb21e2daf8a2b32",
}

FULL_READS = 5_312_696
BENCHMARK_READS = 250_000

DOWNLOADS = Path.home() / "Downloads"
SUCCESS_BUNDLE = (
    DOWNLOADS
    / "rnatr_stage15a_architecture_audit_post250k_output_v0.1.1.tar.gz"
)
FAILURE_BUNDLE = (
    DOWNLOADS
    / "rnatr_stage15a_architecture_audit_post250k_failure_v0.1.1.tar.gz"
)


class AuditError(RuntimeError):
    pass


def ensure_file(path: Path) -> None:
    if not path.is_file() or path.stat().st_size <= 0:
        raise AuditError(f"missing or empty file: {path}")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def sha256_gzip_payload(path: Path) -> str:
    h = hashlib.sha256()
    with gzip.open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_tsv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    ensure_file(path)
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise AuditError(f"missing TSV header: {path}")
        return list(reader.fieldnames), list(reader)


def read_metrics(path: Path) -> dict[str, str]:
    header, rows = read_tsv(path)
    if header != ["metric", "value"]:
        raise AuditError(f"expected metric/value TSV: {path}: {header}")
    return {row["metric"]: row["value"] for row in rows}


def write_tsv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    if not rows:
        raise AuditError(f"refusing empty TSV: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = list(rows[0])
    tmp = path.with_name("." + path.name + ".part")
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fields, delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp, path)


def write_metrics(path: Path, rows: Iterable[tuple[str, Any]]) -> None:
    write_tsv(
        path,
        [{"metric": k, "value": str(v)} for k, v in rows],
        ["metric", "value"],
    )


def verify_expected_sha() -> None:
    for path, expected in EXPECTED_SHA.items():
        ensure_file(path)
        observed = sha256_file(path)
        if observed != expected:
            raise AuditError(
                f"contract SHA mismatch: {path}: {observed} != {expected}"
            )


def verify_final_250k_gate() -> dict[str, str]:
    metrics = read_metrics(FINAL_QC)
    expected = {
        "stage_version": "rnatr_stage15a_deterministic_250k_scaling_v0.1.2",
        "input_reads": "250000",
        "package_exact_logical_reproducibility": "true",
        "package_exact_raw_reproducibility": "true",
        "caller_hashseed_logical_reproducibility": "true",
        "nested_100k_package_exact_parity": "true",
        "checkpoint_manifest_integrity_250k": "PASS",
        "selective_resume_250k_executed": "false",
        "full_scale_restart_validated": "false",
        "deterministic_250k_scaling": "PASS",
        "active_pipeline_modified": "false",
        "ssot_modified": "false",
        "full_5_31m_run_started": "false",
        "stage15a_overall_status": "IN_PROGRESS",
        "audit_status": "PASS",
        "next_gate": "BUILD_AND_RUN_DETERMINISTIC_500K_SCALING_NOT_FULL_5_31M",
    }
    for key, wanted in expected.items():
        if metrics.get(key) != wanted:
            raise AuditError(
                f"250k final QC mismatch {key}: {metrics.get(key)!r} != {wanted!r}"
            )
    return metrics


def run_ssot_validate(log_path: Path) -> None:
    cmd = [
        sys.executable,
        str(SSOT_CLI),
        "--project-root",
        str(PROJECT_ROOT),
        "validate",
    ]
    proc = subprocess.run(cmd, text=True, capture_output=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(proc.stdout + proc.stderr, encoding="utf-8")
    if proc.returncode != 0:
        raise AuditError(f"SSOT validate failed; see {log_path}")


def validate_sqlite() -> tuple[str, int]:
    conn = sqlite3.connect(SSOT_DB)
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk_rows = list(conn.execute("PRAGMA foreign_key_check"))
    finally:
        conn.close()
    if integrity != "ok":
        raise AuditError(f"SQLite integrity failed: {integrity}")
    if fk_rows:
        raise AuditError(f"SQLite foreign-key failures: {len(fk_rows)}")
    return integrity, len(fk_rows)


def verify_active_pipeline() -> tuple[int, str, list[dict[str, str]]]:
    header, rows = read_tsv(CURRENT_PIPELINE)
    required = {
        "stage_key",
        "script_path",
        "script_sha256",
        "validator_path",
        "validator_sha256",
    }
    if not required.issubset(header):
        raise AuditError(f"unexpected current_pipeline schema: {header}")
    if len(rows) != 11:
        raise AuditError(f"expected 11 active pipeline stages, found {len(rows)}")
    canonical = hashlib.sha256()
    for row in rows:
        stage = row["stage_key"]
        if stage.startswith("15A") or "STAGE15A" in stage.upper():
            raise AuditError(f"Stage15A incorrectly present in current_pipeline: {stage}")
        script = Path(row["script_path"])
        ensure_file(script)
        observed = sha256_file(script)
        if observed != row["script_sha256"]:
            raise AuditError(f"active script SHA mismatch: {script}")
        validator_text = row.get("validator_path", "")
        validator_sha = row.get("validator_sha256", "")
        if validator_text and validator_text != ".":
            validator = Path(validator_text)
            ensure_file(validator)
            if validator_sha and validator_sha != ".":
                if sha256_file(validator) != validator_sha:
                    raise AuditError(f"active validator SHA mismatch: {validator}")
        canonical.update(
            (
                stage
                + "\t"
                + row["script_path"]
                + "\t"
                + row["script_sha256"]
                + "\n"
            ).encode("utf-8")
        )
    return len(rows), canonical.hexdigest(), rows


def verify_base_component_guards() -> dict[str, str]:
    spec = importlib.util.spec_from_file_location(
        "rnatr_stage15a_base_v0221_archaudit", BASE_PERFORMANCE_RUNNER
    )
    if spec is None or spec.loader is None:
        raise AuditError("cannot import v0.2.2.1 base runner")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    checked: dict[str, str] = {}

    mappings = []
    # Historical performance runners pinned the SSOT SHA only as a run-time
    # immutability guard.  The SSOT is intentionally versioned and has since been
    # updated by formally audited Stage15A registrations.  Current SSOT source/DB
    # are independently pinned in EXPECTED_SHA and validated above, so treating
    # an old runner's SSOT_GUARDS as a frozen scientific component is a false
    # drift signal.  SOURCE_SHA and ACTIVE_GUARDS remain frozen-component checks.
    for attr in ("SOURCE_SHA", "ACTIVE_GUARDS"):
        value = getattr(module, attr, {})
        if isinstance(value, dict):
            mappings.extend(value.items())

    direct_pairs = [
        ("FROZEN_V03_VALIDATOR", "FROZEN_V03_VALIDATOR_SHA256"),
        ("CALLER_SOURCE_DRIVER", "CALLER_SOURCE_DRIVER_SHA256"),
        ("PERF_CALLER", "PERF_CALLER_SHA256"),
        ("PERF_MATERIALIZER", "PERF_MATERIALIZER_SHA256"),
        ("FAST_MOTIF_BUILDER", "FAST_MOTIF_BUILDER_SHA256"),
        ("PARALLEL_PACKAGE_VALIDATOR", "PARALLEL_PACKAGE_VALIDATOR_SHA256"),
    ]
    for path_attr, sha_attr in direct_pairs:
        if hasattr(module, path_attr) and hasattr(module, sha_attr):
            mappings.append((getattr(module, path_attr), getattr(module, sha_attr)))

    seen: set[Path] = set()
    for raw_path, expected in mappings:
        path = Path(raw_path)
        if path in seen:
            continue
        seen.add(path)
        ensure_file(path)
        observed = sha256_file(path)
        if observed != expected:
            raise AuditError(f"frozen component drift: {path}")
        checked[str(path)] = observed
    return checked


def verify_release_and_biology_contract() -> dict[str, str]:
    _, gates = read_tsv(RELEASE_GATES)
    by_id = {row["gate_id"]: row for row in gates}
    expected = {
        "G06": "OPEN",
        "G07": "OPEN",
        "G17": "PASS",
        "G20": "OPEN",
        "G21": "OPEN",
        "G22": "OPEN",
        "G23": "OPEN",
    }
    for gate, status in expected.items():
        if by_id.get(gate, {}).get("status") != status:
            raise AuditError(
                f"release gate mismatch {gate}: {by_id.get(gate, {}).get('status')}"
            )

    _, contracts = read_tsv(CURRENT_CONTRACTS)
    contract_rows = {
        row["component_key"]: row for row in contracts
    }
    for key in (
        "biology_ready_read_keyed_sidecars_v0_1_0",
        "interpretation_hierarchy_v0_1_0",
    ):
        row = contract_rows.get(key)
        if row is None:
            raise AuditError(f"biology contract missing from SSOT: {key}")
        if row["implementation_state"] != "DESIGNED_NOT_IMPLEMENTED":
            raise AuditError(
                f"biology contract incorrectly implemented: {key}: "
                f"{row['implementation_state']}"
            )

    _, questions = read_tsv(CURRENT_QUESTIONS)
    q_by_id = {row["question_key"]: row for row in questions}
    if q_by_id.get("BIOLOGY_READY_INTERPRETATION_OUTPUT_AUDIT", {}).get("blocking") != "1":
        raise AuditError("biology-ready output audit is not a blocking SSOT question")

    return {gate: by_id[gate]["status"] for gate in expected}


def semantic_metric_digest(path: Path) -> str:
    metrics = read_metrics(path)
    ignored = {"stage_version"}
    kept = {}
    for key, value in metrics.items():
        if key in ignored or key.endswith("_seconds"):
            continue
        kept[key] = value
    payload = json.dumps(kept, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def logical_digest(path: Path, role: str) -> tuple[str, str]:
    if role == "materialization_qc":
        return semantic_metric_digest(path), "SEMANTIC_METRICS_EXCLUDING_TIMING_AND_STAGE_VERSION"
    if path.suffix == ".gz":
        return sha256_gzip_payload(path), "DECOMPRESSED_BYTES"
    return sha256_file(path), "RAW_BYTES"


def checkpoint_logical_audit(output_path: Path) -> tuple[bool, int, int]:
    _, a_rows = read_tsv(CHECKPOINT_MANIFEST_A)
    _, b_rows = read_tsv(CHECKPOINT_MANIFEST_B)
    a = {(r["role"], r["shard"]): r for r in a_rows}
    b = {(r["role"], r["shard"]): r for r in b_rows}
    if set(a) != set(b):
        missing = sorted(set(a) - set(b))
        extra = sorted(set(b) - set(a))
        raise AuditError(
            f"checkpoint key-set mismatch: missing_in_B={missing}, extra_in_B={extra}"
        )

    out_rows: list[dict[str, Any]] = []
    raw_diff_count = 0
    logical_diff_count = 0

    for key in sorted(a):
        role, shard = key
        ra = a[key]
        rb = b[key]
        path_a = Path(ra["path"])
        path_b = Path(rb["path"])
        ensure_file(path_a)
        ensure_file(path_b)

        observed_a = sha256_file(path_a)
        observed_b = sha256_file(path_b)
        if observed_a != ra["sha256"]:
            raise AuditError(f"checkpoint A manifest integrity mismatch: {path_a}")
        if observed_b != rb["sha256"]:
            raise AuditError(f"checkpoint B manifest integrity mismatch: {path_b}")
        if path_a.stat().st_size != int(ra["bytes"]):
            raise AuditError(f"checkpoint A byte mismatch: {path_a}")
        if path_b.stat().st_size != int(rb["bytes"]):
            raise AuditError(f"checkpoint B byte mismatch: {path_b}")

        raw_equal = observed_a == observed_b
        if not raw_equal:
            raw_diff_count += 1

        logical_a, mode_a = logical_digest(path_a, role)
        logical_b, mode_b = logical_digest(path_b, role)
        if mode_a != mode_b:
            raise AuditError(f"comparison-mode mismatch for {role}/{shard}")
        logical_equal = logical_a == logical_b
        if not logical_equal:
            logical_diff_count += 1

        out_rows.append(
            {
                "role": role,
                "shard": shard,
                "comparison_mode": mode_a,
                "a_bytes": ra["bytes"],
                "b_bytes": rb["bytes"],
                "a_raw_sha256": observed_a,
                "b_raw_sha256": observed_b,
                "raw_equal": str(raw_equal).lower(),
                "a_logical_sha256": logical_a,
                "b_logical_sha256": logical_b,
                "logical_equal": str(logical_equal).lower(),
                "status": "PASS" if logical_equal else "CONFLICT",
            }
        )

    write_tsv(output_path, out_rows)
    return logical_diff_count == 0, raw_diff_count, logical_diff_count


def original_checkpoint_checker_is_sufficient() -> bool:
    text = SCALING_RUNNER.read_text(encoding="utf-8")
    start = text.find("def compare_checkpoint_manifests()")
    end = text.find("\ndef compare_replicates()", start)
    if start < 0 or end < 0:
        raise AuditError("cannot locate checkpoint comparison function")
    block = text[start:end]
    # The v0.1.2 implementation validates each replicate separately, writes
    # both manifest SHAs, and returns True without cross-replicate comparison.
    has_cross_comparison = (
        "logical_equal" in block
        or "raw_equal" in block
        or "rows[0]" in block
        or "rows[1]" in block
    )
    return has_cross_comparison


def verify_final_reproducibility_tables() -> None:
    _, package_rows = read_tsv(PACKAGE_REPRO)
    if len(package_rows) != 10:
        raise AuditError(f"expected 10 package reproducibility rows, found {len(package_rows)}")
    for row in package_rows:
        if row["raw_equal"] != "true" or row["logical_equal"] != "true":
            raise AuditError(f"final package reproducibility failed: {row['artifact']}")

    _, caller_rows = read_tsv(CALLER_REPRO)
    if len(caller_rows) != 12:
        raise AuditError(f"expected 12 caller reproducibility rows, found {len(caller_rows)}")
    for row in caller_rows:
        if row["logical_equal"] != "true":
            raise AuditError(f"caller logical reproducibility failed: {row['shard']}")

    _, nested_rows = read_tsv(NESTED_100K)
    if len(nested_rows) != 5:
        raise AuditError(f"expected 5 nested-100k rows, found {len(nested_rows)}")
    for row in nested_rows:
        if row["header_equal"] != "true" or row["nested_anchor_exact_equal"] != "true":
            raise AuditError(f"nested 100k parity failed: {row['table']}")


def lifecycle_ledger(output_path: Path, active_rows: list[dict[str, str]]) -> tuple[int, int]:
    active_paths = {Path(row["script_path"]) for row in active_rows}
    conn = sqlite3.connect(SSOT_DB)
    try:
        implementation_rows = list(
            conn.execute(
                """
                SELECT script_path, lifecycle_status, stage_key, version
                FROM implementations
                WHERE script_path IS NOT NULL
                """
            )
        )
    finally:
        conn.close()
    ssot_by_path = {
        Path(path): {
            "lifecycle": lifecycle or "",
            "stage_key": stage_key or "",
            "version": version or "",
        }
        for path, lifecycle, stage_key, version in implementation_rows
        if path
    }

    rows = []
    unclassified = 0
    obsolete = 0
    for path in sorted((PROJECT_ROOT / "scripts").glob("rnatr_stage15a*")):
        if path in active_paths:
            lifecycle = "ACTIVE"
            basis = "current_pipeline"
        elif path == SCALING_RUNNER:
            lifecycle = "PROVISIONAL_CURRENT_250K_SCALING"
            basis = "250k PASS evidence"
        elif path == FAST_11E:
            lifecycle = "PROVISIONAL_CURRENT_SCALING_COMPONENT"
            basis = "250k PASS evidence"
        elif path in ssot_by_path:
            lifecycle = "SSOT_" + ssot_by_path[path]["lifecycle"]
            basis = ssot_by_path[path]["stage_key"]
        elif any(
            token in path.name
            for token in (
                "fix_v011",
                "fix_v012",
                "fix_v013",
                "fix_performance",
                "fix_scaling",
                "update_ssot",
                "contract_preflight",
                "resolve_caller_parity",
                "pack_parity",
            )
        ):
            lifecycle = "SUPPORT_OR_MIGRATION_TOOL"
            basis = "filename/provenance role"
        elif any(
            token in path.name
            for token in (
                "run_reference_100k_v0.1.0",
                "run_reference_100k_v0.1.1",
                "run_reference_100k_v0.1.2",
                "run_scaling_250k_v0.1.0",
                "run_scaling_250k_v0.1.1",
            )
        ):
            lifecycle = "OBSOLETE_FAILED_HISTORICAL"
            basis = "superseded failed attempt"
            obsolete += 1
        else:
            lifecycle = "REVIEW_UNCLASSIFIED"
            basis = "not in current_pipeline/SSOT/known support patterns"
            unclassified += 1
        rows.append(
            {
                "path": str(path),
                "sha256": sha256_file(path),
                "lifecycle_class": lifecycle,
                "classification_basis": basis,
                "is_active_pipeline": str(path in active_paths).lower(),
            }
        )
    if not rows:
        rows.append(
            {
                "path": ".",
                "sha256": ".",
                "lifecycle_class": "OPEN",
                "classification_basis": "no Stage15A scripts found",
                "is_active_pipeline": "false",
            }
        )
    write_tsv(output_path, rows)
    return unclassified, obsolete


def build_findings(
    metrics: dict[str, str],
    checkpoint_logical_equal: bool,
    original_checker_sufficient: bool,
    unclassified_scripts: int,
) -> list[dict[str, str]]:
    projection = float(metrics["conservative_linear_5_31m_projection_minutes"])
    margin = float(metrics["five_m_hard_ceiling_margin_minutes"])
    internal_alias = (
        read_metrics(REP_QC_A).get("internal_component_run_id") != RUN_ID
    )

    findings = [
        {
            "finding_id": "AC001",
            "domain": "SSOT_ACTIVE_PIPELINE",
            "status": "PASS",
            "finding": "The live current_pipeline remains the 11-stage legacy active path; no Stage15A candidate is active.",
            "required_action": "Keep active switch prohibited until later promotion gate.",
        },
        {
            "finding_id": "AC002",
            "domain": "SCHEMA_FREEZE",
            "status": "PASS",
            "finding": "Frozen component guards pass; replicate A/B final packages are raw and logically identical, and the nested 100k package is exact.",
            "required_action": "Retain evidence schema v0.4.2 as immutable core source of truth.",
        },
        {
            "finding_id": "AC003",
            "domain": "DETERMINISM",
            "status": "PASS",
            "finding": "Two 250k hash-seed replicates have exact final-package and caller logical reproducibility.",
            "required_action": "Carry the same determinism checks into 500k.",
        },
        {
            "finding_id": "AC004",
            "domain": "CHECKPOINT_REPRODUCIBILITY",
            "status": "PASS" if checkpoint_logical_equal else "CONFLICT",
            "finding": (
                "A replacement role×shard logical checkpoint comparison passes."
                if checkpoint_logical_equal
                else "A replacement role×shard logical checkpoint comparison fails."
            ),
            "required_action": (
                "Supersede the unsupported v0.1.2 checkpoint_manifest_reproducibility=true claim with this amendment; do not alter original QC."
                if not original_checker_sufficient
                else "No amendment required."
            ),
        },
        {
            "finding_id": "AC005",
            "domain": "PROVENANCE_RUN_ID",
            "status": "REVIEW" if internal_alias else "PASS",
            "finding": (
                "The external run is 250k, but internal component paths and IDs still use the 100k compatibility alias."
                if internal_alias
                else "External and internal run IDs are aligned."
            ),
            "required_action": "Document the compatibility shim now; remove or encapsulate it before release candidate.",
        },
        {
            "finding_id": "AC006",
            "domain": "PERFORMANCE_GATE",
            "status": "REVIEW",
            "finding": (
                f"The 250k linear projection is {projection:.6f} min with only "
                f"{margin:.6f} min margin to the 60-min ceiling."
            ),
            "required_action": "Keep G06 OPEN and run deterministic 500k; full 5.31M remains prohibited.",
        },
        {
            "finding_id": "AC007",
            "domain": "RESTART_MEMORY_ARTIFACT",
            "status": "OPEN",
            "finding": "100k selective resume is validated, but 250k selective resume, arbitrary upstream recovery, concurrent-memory semantics, and full-scale restart remain unvalidated.",
            "required_action": "Keep G07 OPEN; add a larger-scale resume/memory audit before full run.",
        },
        {
            "finding_id": "AC008",
            "domain": "BIOLOGY_ROADMAP",
            "status": "PASS",
            "finding": "Biology-ready sidecars and interpretation hierarchy are registered as DESIGNED_NOT_IMPLEMENTED; G20-G23 remain OPEN.",
            "required_action": "Do not start biology implementation until performance architecture stabilizes and the pre-biology audit runs.",
        },
        {
            "finding_id": "AC009",
            "domain": "SCRIPT_LIFECYCLE",
            "status": "REVIEW" if unclassified_scripts else "PASS",
            "finding": (
                f"{unclassified_scripts} Stage15A scripts are not classified by active pipeline, SSOT lifecycle, or known support/obsolete patterns."
                if unclassified_scripts
                else "Stage15A scripts are classifiable as active, provisional, reference, support, or obsolete historical artifacts."
            ),
            "required_action": "Retain historical scripts for provenance, but maintain an explicit lifecycle ledger and never infer activity from file presence.",
        },
        {
            "finding_id": "AC010",
            "domain": "PLANNED_ITEMS",
            "status": "OPEN",
            "finding": "500k scaling, empirical full-scale runtime, broader restart/memory validation, 30-min optimization, active promotion, and G20-G23 biology outputs remain planned and not implemented.",
            "required_action": "Register this audit and 250k evidence, then proceed only to deterministic 500k.",
        },
    ]
    return findings


def render_report(
    metrics: dict[str, str],
    findings: list[dict[str, str]],
    checkpoint_logical_equal: bool,
    original_checker_sufficient: bool,
    active_pipeline_sha: str,
    unclassified_scripts: int,
    obsolete_scripts: int,
) -> str:
    stage_rows = read_tsv(STAGE_MODEL)[1]
    stage_lines = "\n".join(
        f"| {row['stage']} | {float(row['conservative_250k_seconds']):.3f} | "
        f"{row['observed_scaling_ratio']} |"
        for row in stage_rows
    )
    finding_lines = "\n".join(
        f"| {row['finding_id']} | {row['domain']} | {row['status']} | "
        f"{row['finding']} | {row['required_action']} |"
        for row in findings
    )
    projection = float(metrics["conservative_linear_5_31m_projection_minutes"])
    margin = float(metrics["five_m_hard_ceiling_margin_minutes"])
    normalized = float(metrics["per_read_normalized_scaling_factor"])
    rss_gib = max(
        float(metrics["replicate_A_maximum_observed_stage_rss_kbytes"]),
        float(metrics["replicate_B_maximum_observed_stage_rss_kbytes"]),
    ) / 1024 / 1024
    temp_gb = max(
        float(metrics["replicate_A_peak_temporary_and_output_bytes"]),
        float(metrics["replicate_B_peak_temporary_and_output_bytes"]),
    ) / 1_000_000_000

    return f"""# RNA-TR-Scout Architecture Consistency Audit — post-250k v0.1.1

Date: 2026-08-09  
Audit status: **REVIEW**  
Mutation policy: SSOT, active pipeline, core schema, and prior result artifacts were not modified.

## 1. 250k scaling result

- Deterministic 250k scaling: `PASS`
- Replicate A/B final package raw equality: `true`
- Replicate A/B final package logical equality: `true`
- Caller hash-seed logical reproducibility: `true`
- Nested original-100k package exact parity: `true`
- Conservative 250k BAM-to-final time: `{metrics['conservative_250k_bam_to_final_cold_seconds']}` seconds
- Linear 5.31M projection: `{projection:.6f}` minutes
- Margin to 60-minute ceiling: `{margin:.6f}` minutes
- Per-read normalized 100k→250k scaling factor: `{normalized:.6f}`
- Maximum observed stage RSS: `{rss_gib:.3f}` GiB
- Peak temporary+output footprint: `{temp_gb:.3f}` GB

The linear projection technically passes 60 minutes, but the margin is too small to close G06. Deterministic 500k remains mandatory.

## 2. Architecture findings

| ID | Domain | Status | Finding | Required action |
|---|---|---|---|---|
{finding_lines}

## 3. Checkpoint amendment

The original v0.1.2 function named `compare_checkpoint_manifests()` did **not** compare replicate A against replicate B. It validated each replicate independently and returned `True`. Therefore the original field:

```text
checkpoint_manifest_reproducibility=true
```

was not supported by the implementation and must be superseded, not silently rewritten.

Replacement audit result:

```text
checkpoint_logical_reproducibility={str(checkpoint_logical_equal).lower()}
original_checker_sufficient={str(original_checker_sufficient).lower()}
```

Compressed TSV checkpoint artifacts are compared by decompressed bytes; runtime materialization QC is compared after excluding timing and stage-version fields; other deterministic artifacts are compared by raw bytes.

## 4. Stage scaling profile

| Stage | Conservative 250k seconds | 100k→250k ratio |
|---|---:|---:|
{stage_lines}

## 5. Cross-domain consistency

- Active pipeline rows: `11`
- Active pipeline canonical SHA-256: `{active_pipeline_sha}`
- Stage15A in current_pipeline: `false`
- Core schema/frozen component drift: `false`
- Historical runner SSOT guards: `excluded from frozen-component drift; current SSOT source/DB are independently SHA-pinned and validated`
- Biology sidecars implemented: `false`
- Interpretation layer implemented: `false`
- G06: `OPEN`
- G07: `OPEN`
- G20-G23: `OPEN`
- Unclassified Stage15A scripts: `{unclassified_scripts}`
- Explicit obsolete historical scripts: `{obsolete_scripts}`

## 6. Gate decision

Do **not** run the full 5.31M sample.

Next sequence:

```text
post-250k architecture audit
→ register 250k result + checkpoint amendment + audit in SSOT
→ deterministic 500k BAM-input scaling with corrected checkpoint checker
→ reassess G06/G07
```

Biology-layer implementation remains paused until the designated pre-biology Architecture consistency audit.
"""


def create_bundle(source_root: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    output.with_suffix(output.suffix + ".sha256").unlink(missing_ok=True)
    with tarfile.open(output, "w:gz", format=tarfile.PAX_FORMAT) as tar:
        for path in sorted(source_root.rglob("*")):
            arcname = path.relative_to(source_root.parent)
            tar.add(path, arcname=str(arcname), recursive=False)
    digest = sha256_file(output)
    Path(str(output) + ".sha256").write_text(
        f"{digest}  {output}\n", encoding="utf-8"
    )


def main() -> int:
    if PROJECT_ROOT != Path("/mnt/intelssd/rnatr_project"):
        raise AuditError(f"unexpected PROJECT_ROOT: {PROJECT_ROOT}")
    if AUDIT_ROOT.exists():
        raise AuditError(f"audit root already exists; preserve it: {AUDIT_ROOT}")

    verify_expected_sha()
    metrics = verify_final_250k_gate()
    verify_final_reproducibility_tables()

    AUDIT_ROOT.mkdir(parents=True, exist_ok=False)
    (AUDIT_ROOT / "logs").mkdir(parents=True)
    (AUDIT_ROOT / "evidence").mkdir(parents=True)
    (AUDIT_ROOT / "metadata").mkdir(parents=True)

    run_ssot_validate(AUDIT_ROOT / "logs/ssot_validate.log")
    integrity, fk_count = validate_sqlite()
    active_count, active_sha, active_rows = verify_active_pipeline()
    component_guards = verify_base_component_guards()
    release_status = verify_release_and_biology_contract()

    checkpoint_equal, raw_diffs, logical_diffs = checkpoint_logical_audit(
        AUDIT_ROOT / "checkpoint_logical_reproducibility.tsv"
    )
    original_sufficient = original_checkpoint_checker_is_sufficient()

    unclassified, obsolete = lifecycle_ledger(
        AUDIT_ROOT / "script_lifecycle_ledger.tsv", active_rows
    )
    findings = build_findings(
        metrics, checkpoint_equal, original_sufficient, unclassified
    )
    write_tsv(AUDIT_ROOT / "architecture_findings.tsv", findings)

    blocking_conflicts = sum(
        1 for row in findings if row["status"] == "CONFLICT"
    )
    review_items = sum(1 for row in findings if row["status"] == "REVIEW")
    open_items = sum(1 for row in findings if row["status"] == "OPEN")

    if not checkpoint_equal:
        audit_status = "CONFLICT"
        next_gate = "RESOLVE_CHECKPOINT_LOGICAL_REPRODUCIBILITY"
    else:
        audit_status = "REVIEW"
        next_gate = (
            "REGISTER_250K_CHECKPOINT_AMENDMENT_AND_ARCHITECTURE_AUDIT_"
            "THEN_BUILD_DETERMINISTIC_500K"
        )

    write_metrics(
        AUDIT_ROOT / "architecture_consistency_audit.qc.tsv",
        [
            ("audit_version", VERSION),
            ("run_id", RUN_ID),
            ("input_reads", metrics["input_reads"]),
            ("deterministic_250k_scaling", metrics["deterministic_250k_scaling"]),
            ("package_exact_raw_reproducibility", metrics["package_exact_raw_reproducibility"]),
            ("package_exact_logical_reproducibility", metrics["package_exact_logical_reproducibility"]),
            ("caller_hashseed_logical_reproducibility", metrics["caller_hashseed_logical_reproducibility"]),
            ("nested_100k_package_exact_parity", metrics["nested_100k_package_exact_parity"]),
            ("original_checkpoint_reproducibility_claim_supported", str(original_sufficient).lower()),
            ("replacement_checkpoint_logical_reproducibility", str(checkpoint_equal).lower()),
            ("checkpoint_raw_difference_rows", raw_diffs),
            ("checkpoint_logical_difference_rows", logical_diffs),
            ("active_pipeline_stage_count", active_count),
            ("active_pipeline_canonical_sha256", active_sha),
            ("active_pipeline_modified", "false"),
            ("core_schema_modified", "false"),
            ("ssot_modified", "false"),
            ("ssot_integrity", integrity),
            ("ssot_foreign_key_failures", fk_count),
            ("frozen_component_guard_count", len(component_guards)),
            ("historical_runner_ssot_guard_policy", "EXCLUDED_FROM_FROZEN_COMPONENT_DRIFT_CURRENT_SSOT_PINNED_SEPARATELY"),
            ("release_gate_G06", release_status["G06"]),
            ("release_gate_G07", release_status["G07"]),
            ("release_gate_G17", release_status["G17"]),
            ("release_gates_G20_G23", "OPEN"),
            ("internal_component_run_id_alias", read_metrics(REP_QC_A)["internal_component_run_id"]),
            ("external_run_id", RUN_ID),
            ("unclassified_stage15a_scripts", unclassified),
            ("obsolete_historical_stage15a_scripts", obsolete),
            ("blocking_conflicts", blocking_conflicts),
            ("review_items", review_items),
            ("open_items", open_items),
            ("five_m_projection_minutes", metrics["conservative_linear_5_31m_projection_minutes"]),
            ("five_m_hard_ceiling_margin_minutes", metrics["five_m_hard_ceiling_margin_minutes"]),
            ("full_5_31m_run_started", "false"),
            ("architecture_audit_status", audit_status),
            ("next_gate", next_gate),
        ],
    )

    report = render_report(
        metrics,
        findings,
        checkpoint_equal,
        original_sufficient,
        active_sha,
        unclassified,
        obsolete,
    )
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(report, encoding="utf-8")
    shutil.copy2(DOC_PATH, AUDIT_ROOT / DOC_PATH.name)

    INSTALL_PATH.parent.mkdir(parents=True, exist_ok=True)
    if Path(__file__).resolve() != INSTALL_PATH.resolve():
        shutil.copy2(Path(__file__).resolve(), INSTALL_PATH)
    shutil.copy2(INSTALL_PATH, AUDIT_ROOT / INSTALL_PATH.name)

    for source in (
        FINAL_QC,
        PACKAGE_REPRO,
        CALLER_REPRO,
        NESTED_100K,
        STAGE_MODEL,
        CHECKPOINT_MANIFEST_A,
        CHECKPOINT_MANIFEST_B,
        RELEASE_GATES,
        BIOLOGY_CONTRACT,
    ):
        shutil.copy2(source, AUDIT_ROOT / "evidence" / source.name)

    write_tsv(
        AUDIT_ROOT / "metadata/frozen_component_guards.tsv",
        [
            {"path": path, "sha256": digest}
            for path, digest in sorted(component_guards.items())
        ],
    )

    create_bundle(AUDIT_ROOT, SUCCESS_BUNDLE)

    print("===== STAGE 15A POST-250K ARCHITECTURE CONSISTENCY AUDIT =====")
    print(f"250k scaling\t{metrics['deterministic_250k_scaling']}")
    print(f"checkpoint logical reproducibility\t{str(checkpoint_equal).lower()}")
    print(f"original checkpoint checker sufficient\t{str(original_sufficient).lower()}")
    print(f"architecture audit status\t{audit_status}")
    print(f"blocking conflicts\t{blocking_conflicts}")
    print(f"review items\t{review_items}")
    print(f"open items\t{open_items}")
    print(f"full 5.31M started\tfalse")
    print(f"next gate\t{next_gate}")
    print(f"QC\t{AUDIT_ROOT / 'architecture_consistency_audit.qc.tsv'}")
    print(f"REPORT\t{DOC_PATH}")
    print(f"OUTPUT_BUNDLE\t{SUCCESS_BUNDLE}")
    print(f"OUTPUT_SHA_FILE\t{SUCCESS_BUNDLE}.sha256")
    return 0


def failure_bundle(exc: BaseException) -> None:
    with tempfile.TemporaryDirectory(prefix="rnatr_archaudit_failure_") as tmp:
        root = Path(tmp) / "rnatr_stage15a_architecture_audit_post250k_failure_v0.1.1"
        root.mkdir(parents=True)
        (root / "failure.txt").write_text(
            "".join(traceback.format_exception(exc)), encoding="utf-8"
        )
        try:
            shutil.copy2(Path(__file__).resolve(), root / Path(__file__).name)
        except Exception:
            pass
        for path in (FINAL_QC, CHECKPOINT_MANIFEST_A, CHECKPOINT_MANIFEST_B):
            try:
                if path.is_file():
                    shutil.copy2(path, root / path.name)
            except Exception:
                pass
        create_bundle(root, FAILURE_BUNDLE)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except BaseException as exc:
        failure_bundle(exc)
        print(f"ERROR: {exc}", file=sys.stderr)
        print(f"Failure bundle: {FAILURE_BUNDLE}", file=sys.stderr)
        print(f"Failure SHA: {FAILURE_BUNDLE}.sha256", file=sys.stderr)
        raise
