#!/usr/bin/env bash
set -Eeuo pipefail

INSTALLER_VERSION="rnatr_ssot_installer_v0.1.0"
PROJECT_ROOT="/mnt/intelssd/rnatr_project"
SSOT_ROOT="$PROJECT_ROOT/metadata/ssot"
CLI="$SSOT_ROOT/rnatr_ssot.py"
DESIGN="$PROJECT_ROOT/docs/design/RNA_TR_Scout_SSOT_design_v0.1.0.md"
INSTALLED_SCRIPT="$PROJECT_ROOT/scripts/00_build_rnatr_ssot_db_v0.1.0.sh"

[[ "$PROJECT_ROOT" == "/mnt/intelssd/rnatr_project" ]] || {
  echo "ERROR: unexpected project root" >&2
  exit 2
}
[[ -d "$PROJECT_ROOT" ]] || {
  echo "ERROR: project root missing: $PROJECT_ROOT" >&2
  exit 2
}

mkdir -p "$SSOT_ROOT" "$(dirname "$DESIGN")" "$(dirname "$INSTALLED_SCRIPT")"

cat > "$CLI.part" <<'PYCODE'
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

TOOL_VERSION = "rnatr_ssot_v0.1.0"
SCHEMA_VERSION = 1
DEFAULT_PROJECT_ROOT = Path("/mnt/intelssd/rnatr_project")
MAX_QC_BYTES = 25 * 1024 * 1024
MAX_MANIFEST_BYTES = 50 * 1024 * 1024
MAX_DIRECT_HASH_BYTES = 256 * 1024 * 1024
NOW = lambda: dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()

SCHEMA_SQL = r"""
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = DELETE;
PRAGMA synchronous = FULL;

CREATE TABLE schema_info (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE ingestion_runs (
    ingestion_id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    tool_version TEXT NOT NULL,
    project_root TEXT NOT NULL,
    old_tracker_db_sha256 TEXT,
    notes TEXT
);

CREATE TABLE source_documents (
    source_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL,
    path TEXT NOT NULL UNIQUE,
    sha256 TEXT,
    bytes INTEGER,
    mtime_utc TEXT,
    content_status TEXT NOT NULL DEFAULT 'PRESENT',
    ingested_at TEXT NOT NULL
);

CREATE TABLE legacy_records (
    legacy_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_path TEXT NOT NULL,
    source_table TEXT NOT NULL,
    row_number INTEGER NOT NULL,
    record_json TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    UNIQUE(source_path, source_table, row_number)
);

CREATE TABLE datasets (
    dataset_id TEXT PRIMARY KEY,
    accession TEXT,
    sample_label TEXT,
    organism TEXT,
    tissue TEXT,
    developmental_stage TEXT,
    sex TEXT,
    platform TEXT,
    library_method TEXT,
    dataset_role TEXT NOT NULL,
    status TEXT NOT NULL,
    source_path TEXT,
    metadata_json TEXT,
    notes TEXT
);

CREATE TABLE runs (
    run_id TEXT PRIMARY KEY,
    dataset_id TEXT REFERENCES datasets(dataset_id),
    parent_run_id TEXT REFERENCES runs(run_id),
    run_role TEXT,
    pipeline_version TEXT,
    status TEXT NOT NULL,
    started_at TEXT,
    ended_at TEXT,
    root_path TEXT,
    notes TEXT
);

CREATE TABLE stage_definitions (
    stage_key TEXT PRIMARY KEY,
    stage_order REAL,
    name TEXT NOT NULL,
    purpose TEXT,
    category TEXT,
    implementation_status TEXT,
    notes TEXT
);

CREATE TABLE implementations (
    implementation_id TEXT PRIMARY KEY,
    stage_key TEXT NOT NULL REFERENCES stage_definitions(stage_key),
    version TEXT,
    script_path TEXT,
    script_sha256 TEXT,
    validator_path TEXT,
    validator_sha256 TEXT,
    package_version TEXT,
    parameters_json TEXT,
    lifecycle_status TEXT NOT NULL,
    supersedes_implementation_id TEXT REFERENCES implementations(implementation_id),
    rationale TEXT,
    evidence_path TEXT,
    effective_at TEXT NOT NULL
);

CREATE UNIQUE INDEX one_active_implementation_per_stage
ON implementations(stage_key)
WHERE lifecycle_status = 'ACTIVE';

CREATE TABLE run_stages (
    run_stage_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    stage_key TEXT NOT NULL REFERENCES stage_definitions(stage_key),
    implementation_id TEXT REFERENCES implementations(implementation_id),
    attempt_tag TEXT NOT NULL,
    status TEXT NOT NULL,
    command_text TEXT,
    qc_path TEXT,
    qc_status TEXT,
    started_at TEXT,
    ended_at TEXT,
    notes TEXT,
    UNIQUE(run_id, stage_key, attempt_tag)
);

CREATE TABLE artifacts (
    artifact_id TEXT PRIMARY KEY,
    run_id TEXT REFERENCES runs(run_id),
    stage_key TEXT REFERENCES stage_definitions(stage_key),
    artifact_role TEXT,
    path TEXT NOT NULL UNIQUE,
    sha256 TEXT,
    bytes INTEGER,
    data_rows INTEGER,
    schema_version TEXT,
    status TEXT NOT NULL,
    is_current INTEGER NOT NULL DEFAULT 0 CHECK(is_current IN (0,1)),
    created_at TEXT,
    source_manifest_path TEXT,
    notes TEXT
);

CREATE TABLE artifact_relations (
    relation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
    child_artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
    relation_type TEXT NOT NULL,
    notes TEXT,
    UNIQUE(parent_artifact_id, child_artifact_id, relation_type)
);

CREATE TABLE metrics (
    metric_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT REFERENCES runs(run_id),
    stage_key TEXT REFERENCES stage_definitions(stage_key),
    metric_name TEXT NOT NULL,
    value_text TEXT NOT NULL,
    value_num REAL,
    unit TEXT,
    denominator_num REAL,
    source_path TEXT NOT NULL,
    metric_status TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    UNIQUE(run_id, stage_key, metric_name, source_path)
);

CREATE TABLE decisions (
    decision_id TEXT PRIMARY KEY,
    decision_key TEXT NOT NULL,
    category TEXT,
    title TEXT NOT NULL,
    statement TEXT NOT NULL,
    status TEXT NOT NULL,
    confidence TEXT,
    effective_at TEXT NOT NULL,
    supersedes_decision_id TEXT REFERENCES decisions(decision_id),
    rationale TEXT,
    evidence_path TEXT
);

CREATE UNIQUE INDEX one_active_decision_per_key
ON decisions(decision_key)
WHERE status = 'ACTIVE';

CREATE TABLE interpretations (
    interpretation_id TEXT PRIMARY KEY,
    interpretation_key TEXT NOT NULL,
    fact_statement TEXT NOT NULL,
    interpretation TEXT NOT NULL,
    do_not_interpret_as TEXT,
    status TEXT NOT NULL,
    confidence TEXT,
    effective_at TEXT NOT NULL,
    supersedes_interpretation_id TEXT REFERENCES interpretations(interpretation_id),
    evidence_path TEXT,
    evidence_metrics_json TEXT
);

CREATE UNIQUE INDEX one_active_interpretation_per_key
ON interpretations(interpretation_key)
WHERE status = 'ACTIVE';

CREATE TABLE algorithm_contracts (
    contract_id TEXT PRIMARY KEY,
    component_key TEXT NOT NULL,
    component_name TEXT NOT NULL,
    implementation_state TEXT NOT NULL,
    contract_statement TEXT NOT NULL,
    active_implementation_id TEXT REFERENCES implementations(implementation_id),
    evidence_path TEXT,
    effective_at TEXT NOT NULL,
    status TEXT NOT NULL
);

CREATE UNIQUE INDEX one_active_contract_per_component
ON algorithm_contracts(component_key)
WHERE status = 'ACTIVE';

CREATE TABLE reference_hierarchy (
    reference_key TEXT PRIMARY KEY,
    priority INTEGER,
    resource_name TEXT NOT NULL,
    role TEXT NOT NULL,
    platform TEXT,
    cohort_size INTEGER,
    measurement_use TEXT,
    automatic_use_policy TEXT,
    status TEXT NOT NULL,
    source_path TEXT,
    effective_at TEXT NOT NULL
);

CREATE TABLE limitations (
    limitation_key TEXT PRIMARY KEY,
    statement TEXT NOT NULL,
    severity TEXT,
    status TEXT NOT NULL,
    mitigation TEXT,
    evidence_path TEXT,
    effective_at TEXT NOT NULL
);

CREATE TABLE open_questions (
    question_key TEXT PRIMARY KEY,
    question TEXT NOT NULL,
    priority TEXT,
    status TEXT NOT NULL,
    blocking INTEGER NOT NULL DEFAULT 0 CHECK(blocking IN (0,1)),
    next_action TEXT,
    evidence_path TEXT,
    effective_at TEXT NOT NULL
);

CREATE TABLE failures (
    failure_id TEXT PRIMARY KEY,
    run_id TEXT REFERENCES runs(run_id),
    stage_key TEXT REFERENCES stage_definitions(stage_key),
    attempt_version TEXT,
    status TEXT NOT NULL,
    summary TEXT NOT NULL,
    root_cause TEXT,
    resolution TEXT,
    source_path TEXT,
    superseded_by TEXT,
    recorded_at TEXT NOT NULL
);

CREATE TABLE scan_warnings (
    warning_id INTEGER PRIMARY KEY AUTOINCREMENT,
    warning_type TEXT NOT NULL,
    path TEXT,
    message TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);

CREATE VIEW current_pipeline AS
SELECT
    sd.stage_order,
    sd.stage_key,
    sd.name,
    sd.purpose,
    sd.category,
    i.version,
    i.script_path,
    i.script_sha256,
    i.validator_path,
    i.validator_sha256,
    i.package_version,
    i.parameters_json,
    i.rationale,
    i.evidence_path,
    i.effective_at
FROM stage_definitions sd
JOIN implementations i ON i.stage_key = sd.stage_key
WHERE i.lifecycle_status = 'ACTIVE'
ORDER BY sd.stage_order, sd.stage_key;

CREATE VIEW current_decisions AS
SELECT decision_key, category, title, statement, confidence, rationale,
       evidence_path, effective_at
FROM decisions
WHERE status = 'ACTIVE'
ORDER BY category, decision_key;

CREATE VIEW current_interpretations AS
SELECT interpretation_key, fact_statement, interpretation,
       do_not_interpret_as, confidence, evidence_path, effective_at
FROM interpretations
WHERE status = 'ACTIVE'
ORDER BY interpretation_key;

CREATE VIEW current_algorithm_contract AS
SELECT component_key, component_name, implementation_state,
       contract_statement, active_implementation_id,
       evidence_path, effective_at
FROM algorithm_contracts
WHERE status = 'ACTIVE'
ORDER BY component_key;

CREATE VIEW current_reference_hierarchy AS
SELECT priority, reference_key, resource_name, role, platform, cohort_size,
       measurement_use, automatic_use_policy, source_path, effective_at
FROM reference_hierarchy
WHERE status = 'ACTIVE'
ORDER BY priority, reference_key;

CREATE VIEW current_known_limitations AS
SELECT limitation_key, severity, statement, mitigation, evidence_path, effective_at
FROM limitations
WHERE status = 'ACTIVE'
ORDER BY
    CASE severity WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2
                  WHEN 'MODERATE' THEN 3 ELSE 4 END,
    limitation_key;

CREATE VIEW current_open_questions AS
SELECT question_key, priority, blocking, question, next_action,
       evidence_path, effective_at
FROM open_questions
WHERE status = 'OPEN'
ORDER BY blocking DESC,
    CASE priority WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2
                  WHEN 'MODERATE' THEN 3 ELSE 4 END,
    question_key;

CREATE VIEW current_results AS
SELECT run_id, stage_key, metric_name, value_text, value_num, unit,
       denominator_num, source_path, recorded_at
FROM metrics
WHERE metric_status = 'CURRENT'
ORDER BY stage_key, metric_name;

CREATE VIEW current_runs AS
SELECT r.run_id, r.dataset_id, d.accession, d.sample_label, d.dataset_role,
       r.run_role, r.pipeline_version, r.status, r.started_at, r.ended_at,
       r.root_path, r.notes
FROM runs r
LEFT JOIN datasets d ON d.dataset_id = r.dataset_id
ORDER BY r.run_id;

CREATE VIEW latest_stage_status AS
WITH ranked AS (
    SELECT rs.*,
           ROW_NUMBER() OVER (
               PARTITION BY rs.run_id, rs.stage_key
               ORDER BY COALESCE(rs.ended_at, rs.started_at, '') DESC,
                        rs.run_stage_id DESC
           ) AS rn
    FROM run_stages rs
)
SELECT run_id, stage_key, implementation_id, attempt_tag, status,
       qc_path, qc_status, started_at, ended_at, notes
FROM ranked
WHERE rn = 1
ORDER BY run_id, stage_key;

CREATE VIEW current_artifacts AS
SELECT artifact_id, run_id, stage_key, artifact_role, path, sha256,
       bytes, data_rows, schema_version, status, created_at,
       source_manifest_path, notes
FROM artifacts
WHERE is_current = 1
ORDER BY stage_key, artifact_role, path;

CREATE VIEW project_dashboard AS
SELECT 'active_pipeline_stages' AS item,
       CAST((SELECT COUNT(*) FROM current_pipeline) AS TEXT) AS value
UNION ALL
SELECT 'active_decisions', CAST((SELECT COUNT(*) FROM current_decisions) AS TEXT)
UNION ALL
SELECT 'active_interpretations', CAST((SELECT COUNT(*) FROM current_interpretations) AS TEXT)
UNION ALL
SELECT 'active_algorithm_contracts', CAST((SELECT COUNT(*) FROM current_algorithm_contract) AS TEXT)
UNION ALL
SELECT 'active_references', CAST((SELECT COUNT(*) FROM current_reference_hierarchy) AS TEXT)
UNION ALL
SELECT 'active_limitations', CAST((SELECT COUNT(*) FROM current_known_limitations) AS TEXT)
UNION ALL
SELECT 'open_questions', CAST((SELECT COUNT(*) FROM current_open_questions) AS TEXT)
UNION ALL
SELECT 'current_metrics', CAST((SELECT COUNT(*) FROM current_results) AS TEXT)
UNION ALL
SELECT 'runs', CAST((SELECT COUNT(*) FROM runs) AS TEXT)
UNION ALL
SELECT 'artifacts', CAST((SELECT COUNT(*) FROM artifacts) AS TEXT)
UNION ALL
SELECT 'legacy_records', CAST((SELECT COUNT(*) FROM legacy_records) AS TEXT)
UNION ALL
SELECT 'scan_warnings', CAST((SELECT COUNT(*) FROM scan_warnings) AS TEXT);
"""


class SSOTError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_mtime_utc(path: Path) -> str:
    return dt.datetime.fromtimestamp(
        path.stat().st_mtime, tz=dt.timezone.utc
    ).replace(microsecond=0).isoformat()


def open_text(path: Path):
    if path.name.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    return path.open("rt", encoding="utf-8", errors="replace")


def read_tsv(path: Path, max_rows: int | None = None) -> tuple[list[str], list[dict[str, str]]]:
    with open_text(path) as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fields = list(reader.fieldnames or [])
        rows: list[dict[str, str]] = []
        for index, row in enumerate(reader, start=1):
            rows.append({str(k): "" if v is None else str(v) for k, v in row.items()})
            if max_rows is not None and index >= max_rows:
                break
    return fields, rows


def numeric_value(value: str) -> float | None:
    text = value.strip()
    if text in {"", ".", "NA", "N/A", "nan", "None", "null", "true", "false"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def normalize_status(value: str) -> str:
    text = (value or "").strip().upper()
    if "FAIL" in text or "ERROR" in text:
        return "FAIL"
    if "PASS" in text or text == "COMPLETE":
        return "PASS"
    if "HOLD" in text or "BLOCK" in text or "PAUSE" in text:
        return "HOLD"
    if "REVIEW" in text:
        return "REVIEW"
    if "IN_PROGRESS" in text or "RUNNING" in text:
        return "IN_PROGRESS"
    if "NOT_RUN" in text or "NOT RUN" in text:
        return "NOT_RUN"
    return text if text else "OBSERVED"


def infer_run_id(path: Path) -> str | None:
    for part in path.parts:
        if re.fullmatch(r"ENCSR[0-9A-Z]+(?:_[A-Za-z0-9._-]+)?", part):
            return part
    match = re.search(r"(ENCSR[0-9A-Z]+(?:_[A-Za-z0-9._-]+)?)", str(path))
    return match.group(1) if match else None


def infer_stage_key(path: Path, project_root: Path) -> str:
    try:
        rel = path.resolve().relative_to(project_root.resolve())
    except Exception:
        rel = path
    parts = rel.parts
    for anchor in ("results", "qc"):
        if anchor in parts:
            index = parts.index(anchor)
            if index + 1 < len(parts):
                return parts[index + 1]
    if "scripts" in parts:
        name = path.name
        match = re.match(r"^([0-9]+[a-z0-9]*)[_-]", name, re.I)
        return match.group(1) if match else f"SCRIPT_{path.stem}"
    if "checkpoints" in parts:
        return "BUILD_TRACKER_CHECKPOINT"
    return "UNCLASSIFIED"


def artifact_id_for(path: str) -> str:
    return "artifact_" + hashlib.sha256(path.encode("utf-8")).hexdigest()[:24]


def implementation_id_for(stage_key: str, path: str, sha: str | None) -> str:
    token = f"{stage_key}\0{path}\0{sha or '.'}"
    return "impl_" + hashlib.sha256(token.encode("utf-8")).hexdigest()[:24]


def decision_id_for(key: str, effective_at: str) -> str:
    return "decision_" + hashlib.sha256(
        f"{key}\0{effective_at}".encode("utf-8")
    ).hexdigest()[:24]


def interpretation_id_for(key: str, effective_at: str) -> str:
    return "interp_" + hashlib.sha256(
        f"{key}\0{effective_at}".encode("utf-8")
    ).hexdigest()[:24]


def source_document(
    conn: sqlite3.Connection,
    path: Path,
    source_type: str,
    *,
    content_status: str | None = None,
    force_hash: bool = False,
) -> None:
    exists = path.is_file()
    status = content_status or ("PRESENT" if exists else "MISSING")
    size = path.stat().st_size if exists else None
    mtime = file_mtime_utc(path) if exists else None
    digest = None
    if exists and (force_hash or (size is not None and size <= MAX_DIRECT_HASH_BYTES)):
        digest = sha256_file(path)
    conn.execute(
        """
        INSERT INTO source_documents(
            source_type, path, sha256, bytes, mtime_utc,
            content_status, ingested_at
        ) VALUES(?,?,?,?,?,?,?)
        ON CONFLICT(path) DO UPDATE SET
            source_type=excluded.source_type,
            sha256=COALESCE(excluded.sha256, source_documents.sha256),
            bytes=excluded.bytes,
            mtime_utc=excluded.mtime_utc,
            content_status=excluded.content_status,
            ingested_at=excluded.ingested_at
        """,
        (source_type, str(path), digest, size, mtime, status, NOW()),
    )


def warn(conn: sqlite3.Connection, warning_type: str, message: str, path: Path | None = None) -> None:
    conn.execute(
        "INSERT INTO scan_warnings(warning_type,path,message,recorded_at) VALUES(?,?,?,?)",
        (warning_type, str(path) if path else None, message, NOW()),
    )


def ensure_stage(
    conn: sqlite3.Connection,
    stage_key: str,
    *,
    order: float | None = None,
    name: str | None = None,
    purpose: str | None = None,
    category: str | None = None,
    status: str | None = None,
    notes: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO stage_definitions(
            stage_key, stage_order, name, purpose, category,
            implementation_status, notes
        ) VALUES(?,?,?,?,?,?,?)
        ON CONFLICT(stage_key) DO UPDATE SET
            stage_order=COALESCE(excluded.stage_order, stage_definitions.stage_order),
            name=CASE
                WHEN stage_definitions.name LIKE 'Discovered stage:%'
                THEN excluded.name
                ELSE stage_definitions.name
            END,
            purpose=COALESCE(excluded.purpose, stage_definitions.purpose),
            category=COALESCE(excluded.category, stage_definitions.category),
            implementation_status=COALESCE(excluded.implementation_status, stage_definitions.implementation_status),
            notes=COALESCE(excluded.notes, stage_definitions.notes)
        """,
        (
            stage_key,
            order,
            name or f"Discovered stage: {stage_key}",
            purpose,
            category,
            status,
            notes,
        ),
    )


def ensure_run(
    conn: sqlite3.Connection,
    run_id: str,
    *,
    dataset_id: str | None = None,
    parent_run_id: str | None = None,
    run_role: str | None = None,
    pipeline_version: str | None = None,
    status: str = "DISCOVERED",
    root_path: str | None = None,
    notes: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO runs(
            run_id,dataset_id,parent_run_id,run_role,pipeline_version,
            status,root_path,notes
        ) VALUES(?,?,?,?,?,?,?,?)
        ON CONFLICT(run_id) DO UPDATE SET
            dataset_id=COALESCE(excluded.dataset_id, runs.dataset_id),
            parent_run_id=COALESCE(excluded.parent_run_id, runs.parent_run_id),
            run_role=COALESCE(excluded.run_role, runs.run_role),
            pipeline_version=COALESCE(excluded.pipeline_version, runs.pipeline_version),
            status=CASE WHEN excluded.status='DISCOVERED' THEN runs.status ELSE excluded.status END,
            root_path=COALESCE(excluded.root_path, runs.root_path),
            notes=COALESCE(excluded.notes, runs.notes)
        """,
        (
            run_id,
            dataset_id,
            parent_run_id,
            run_role,
            pipeline_version,
            status,
            root_path,
            notes,
        ),
    )


def insert_metric(
    conn: sqlite3.Connection,
    run_id: str | None,
    stage_key: str | None,
    name: str,
    value: str,
    source_path: str,
    *,
    status: str = "OBSERVED",
    unit: str | None = None,
    denominator: float | None = None,
) -> None:
    if stage_key:
        ensure_stage(conn, stage_key)
    if run_id:
        ensure_run(conn, run_id)
    conn.execute(
        """
        INSERT INTO metrics(
            run_id,stage_key,metric_name,value_text,value_num,
            unit,denominator_num,source_path,metric_status,recorded_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(run_id,stage_key,metric_name,source_path) DO UPDATE SET
            value_text=excluded.value_text,
            value_num=excluded.value_num,
            unit=excluded.unit,
            denominator_num=excluded.denominator_num,
            metric_status=excluded.metric_status,
            recorded_at=excluded.recorded_at
        """,
        (
            run_id,
            stage_key,
            name,
            value,
            numeric_value(value),
            unit,
            denominator,
            source_path,
            status,
            NOW(),
        ),
    )


def register_artifact(
    conn: sqlite3.Connection,
    path: Path,
    *,
    run_id: str | None,
    stage_key: str | None,
    role: str | None,
    sha256: str | None,
    bytes_value: int | None,
    rows_value: int | None,
    schema_version: str | None = None,
    status: str = "OBSERVED",
    is_current: bool = False,
    manifest_path: str | None = None,
    notes: str | None = None,
) -> None:
    if run_id:
        ensure_run(conn, run_id)
    if stage_key:
        ensure_stage(conn, stage_key)
    conn.execute(
        """
        INSERT INTO artifacts(
            artifact_id,run_id,stage_key,artifact_role,path,sha256,bytes,
            data_rows,schema_version,status,is_current,created_at,
            source_manifest_path,notes
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(path) DO UPDATE SET
            run_id=COALESCE(excluded.run_id, artifacts.run_id),
            stage_key=COALESCE(excluded.stage_key, artifacts.stage_key),
            artifact_role=COALESCE(excluded.artifact_role, artifacts.artifact_role),
            sha256=COALESCE(excluded.sha256, artifacts.sha256),
            bytes=COALESCE(excluded.bytes, artifacts.bytes),
            data_rows=COALESCE(excluded.data_rows, artifacts.data_rows),
            schema_version=COALESCE(excluded.schema_version, artifacts.schema_version),
            status=excluded.status,
            is_current=MAX(artifacts.is_current, excluded.is_current),
            source_manifest_path=COALESCE(excluded.source_manifest_path, artifacts.source_manifest_path),
            notes=COALESCE(excluded.notes, artifacts.notes)
        """,
        (
            artifact_id_for(str(path)),
            run_id,
            stage_key,
            role,
            str(path),
            sha256,
            bytes_value,
            rows_value,
            schema_version,
            status,
            1 if is_current else 0,
            file_mtime_utc(path) if path.exists() else None,
            manifest_path,
            notes,
        ),
    )


def parse_two_column_metrics(
    conn: sqlite3.Connection,
    path: Path,
    project_root: Path,
    *,
    status: str = "OBSERVED",
) -> tuple[int, str | None]:
    fields, rows = read_tsv(path, max_rows=50000)
    if len(fields) < 2:
        return 0, None
    key_field = fields[0]
    value_field = fields[1]
    if key_field.lower() not in {"metric", "field", "parameter", "key", "item"}:
        return 0, None
    run_id = infer_run_id(path)
    stage_key = infer_stage_key(path, project_root)
    qc_status: str | None = None
    count = 0
    for row in rows:
        key = row.get(key_field, "").strip()
        value = row.get(value_field, "").strip()
        if not key:
            continue
        insert_metric(
            conn,
            run_id,
            stage_key,
            key,
            value,
            str(path),
            status=status,
        )
        count += 1
        key_lower = key.lower()
        if (
            key_lower == "audit_status"
            or key_lower == "status"
            or key_lower.endswith("_status")
            or key_lower.endswith("status")
        ):
            normalized = normalize_status(value)
            if normalized in {"PASS", "FAIL", "HOLD", "REVIEW", "IN_PROGRESS", "NOT_RUN"}:
                qc_status = normalized
    if run_id:
        ensure_run(conn, run_id, root_path=str(path.parent))
        ensure_stage(conn, stage_key)
        attempt_tag = hashlib.sha256(str(path).encode()).hexdigest()[:16]
        conn.execute(
            """
            INSERT INTO run_stages(
                run_id,stage_key,implementation_id,attempt_tag,status,
                qc_path,qc_status,ended_at,notes
            ) VALUES(?,?,?,?,?,?,?,?,?)
            ON CONFLICT(run_id,stage_key,attempt_tag) DO UPDATE SET
                status=excluded.status,
                qc_status=excluded.qc_status,
                ended_at=excluded.ended_at,
                notes=excluded.notes
            """,
            (
                run_id,
                stage_key,
                None,
                attempt_tag,
                qc_status or "OBSERVED",
                str(path),
                qc_status,
                file_mtime_utc(path),
                "Auto-ingested from QC/metric TSV.",
            ),
        )
    return count, qc_status


def import_legacy_sqlite(conn: sqlite3.Connection, old_db: Path) -> str | None:
    if not old_db.is_file():
        warn(conn, "OLD_TRACKER_MISSING", "Legacy build-tracker SQLite database not found.", old_db)
        source_document(conn, old_db, "legacy_tracker_sqlite")
        return None
    source_document(conn, old_db, "legacy_tracker_sqlite", force_hash=True)
    old_sha = sha256_file(old_db)
    uri = f"file:{old_db}?mode=ro"
    old = sqlite3.connect(uri, uri=True)
    old.row_factory = sqlite3.Row
    try:
        tables = [
            row[0]
            for row in old.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        for table in tables:
            columns = [row[1] for row in old.execute(f'PRAGMA table_info("{table}")')]
            for row_number, row in enumerate(old.execute(f'SELECT * FROM "{table}"'), start=1):
                record = {columns[index]: row[index] for index in range(len(columns))}
                conn.execute(
                    """
                    INSERT OR REPLACE INTO legacy_records(
                        source_path,source_table,row_number,record_json,imported_at
                    ) VALUES(?,?,?,?,?)
                    """,
                    (
                        str(old_db),
                        table,
                        row_number,
                        json.dumps(record, ensure_ascii=False, default=str, sort_keys=True),
                        NOW(),
                    ),
                )
                lower_table = table.lower()
                keys = {str(k).lower(): k for k in record}
                if "step" in lower_table:
                    stage_value = None
                    for candidate in ("step_id", "step", "id", "number"):
                        if candidate in keys:
                            stage_value = record[keys[candidate]]
                            break
                    if stage_value is not None:
                        stage_key = f"LEGACY_STEP_{stage_value}"
                        ensure_stage(
                            conn,
                            stage_key,
                            name=str(record.get(keys.get("title"), f"Legacy step {stage_value}")),
                            category=str(record.get(keys.get("category"), "legacy")),
                            status=str(record.get(keys.get("status"), "LEGACY")),
                            purpose=str(record.get(keys.get("expected"), "")),
                            notes=str(record.get(keys.get("notes"), "")),
                        )
                elif "decision" in lower_table:
                    title = str(record.get(keys.get("title"), record.get(keys.get("decision"), table)))
                    statement = str(record.get(keys.get("statement"), record.get(keys.get("decision"), record)))
                    key = "legacy_" + hashlib.sha256(
                        f"{table}\0{row_number}".encode()
                    ).hexdigest()[:16]
                    effective = NOW()
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO decisions(
                            decision_id,decision_key,category,title,statement,status,
                            confidence,effective_at,rationale,evidence_path
                        ) VALUES(?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            decision_id_for(key, effective),
                            key,
                            "legacy",
                            title,
                            statement,
                            "LEGACY",
                            "UNREVIEWED",
                            effective,
                            "Imported from prior tracker without promotion to current state.",
                            str(old_db),
                        ),
                    )
    finally:
        old.close()
    return old_sha


def import_legacy_exports(conn: sqlite3.Connection, tracker_root: Path) -> None:
    for path in sorted(tracker_root.glob("rnatr_build_*.tsv")):
        if not path.is_file():
            continue
        source_document(conn, path, "legacy_tracker_export", force_hash=True)
        try:
            _, rows = read_tsv(path)
        except Exception as exc:
            warn(conn, "LEGACY_EXPORT_PARSE_ERROR", str(exc), path)
            continue
        for row_number, row in enumerate(rows, start=1):
            conn.execute(
                """
                INSERT OR REPLACE INTO legacy_records(
                    source_path,source_table,row_number,record_json,imported_at
                ) VALUES(?,?,?,?,?)
                """,
                (
                    str(path),
                    path.stem,
                    row_number,
                    json.dumps(row, ensure_ascii=False, sort_keys=True),
                    NOW(),
                ),
            )


def scan_scripts(conn: sqlite3.Connection, project_root: Path) -> None:
    roots = [
        project_root / "scripts",
        project_root / "config" / "evidence_schema",
        project_root / "metadata" / "build_tracker",
    ]
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in {".sh", ".py"}:
                continue
            source_document(conn, path, "script", force_hash=True)
            stage_key = infer_stage_key(path, project_root)
            ensure_stage(conn, stage_key, category="discovered")
            digest = sha256_file(path)
            impl_id = implementation_id_for(stage_key, str(path), digest)
            conn.execute(
                """
                INSERT OR IGNORE INTO implementations(
                    implementation_id,stage_key,version,script_path,script_sha256,
                    lifecycle_status,rationale,evidence_path,effective_at
                ) VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (
                    impl_id,
                    stage_key,
                    None,
                    str(path),
                    digest,
                    "DISCOVERED",
                    "Auto-discovered implementation; not promoted to current pipeline.",
                    str(path),
                    file_mtime_utc(path),
                ),
            )


def scan_qc(conn: sqlite3.Connection, project_root: Path) -> None:
    root = project_root / "qc"
    if not root.exists():
        warn(conn, "QC_ROOT_MISSING", "QC directory is missing.", root)
        return
    scanned = 0
    for path in sorted(root.rglob("*.tsv")) + sorted(root.rglob("*.tsv.gz")):
        if not path.is_file() or path.stat().st_size > MAX_QC_BYTES:
            continue
        source_document(conn, path, "qc_or_metric_tsv")
        try:
            parsed, _ = parse_two_column_metrics(conn, path, project_root)
            scanned += parsed
        except Exception as exc:
            warn(conn, "QC_PARSE_ERROR", str(exc), path)
    insert_metric(
        conn, None, "SSOT_INGEST", "qc_metric_rows_ingested",
        str(scanned), str(root), status="CURRENT"
    )


def candidate_manifest_files(project_root: Path) -> Iterator[Path]:
    roots = [
        project_root / "results",
        project_root / "qc",
        project_root / "metadata" / "build_tracker" / "checkpoints",
    ]
    seen: set[Path] = set()
    for root in roots:
        if not root.exists():
            continue
        for pattern in ("*manifest*.tsv", "*manifest*.tsv.gz", "*artifacts*.tsv", "*artifacts*.tsv.gz"):
            for path in root.rglob(pattern):
                if path.is_file() and path not in seen:
                    seen.add(path)
                    yield path


def scan_manifests(conn: sqlite3.Connection, project_root: Path) -> None:
    manifest_count = 0
    artifact_count = 0
    path_keys = ("path", "local_path", "file", "filepath", "artifact_path")
    sha_keys = ("sha256", "source_sha256", "local_sha256")
    byte_keys = ("bytes", "size", "file_size", "observed_bytes")
    row_keys = ("data_rows", "rows", "records", "row_count")
    role_keys = ("role", "artifact", "artifact_role", "name")
    schema_keys = ("schema_version", "evidence_schema_version")

    for manifest in sorted(candidate_manifest_files(project_root)):
        if manifest.stat().st_size > MAX_MANIFEST_BYTES:
            warn(conn, "MANIFEST_TOO_LARGE", "Manifest skipped because it exceeds scan limit.", manifest)
            continue
        source_document(conn, manifest, "artifact_manifest", force_hash=True)
        try:
            fields, rows = read_tsv(manifest, max_rows=200000)
        except Exception as exc:
            warn(conn, "MANIFEST_PARSE_ERROR", str(exc), manifest)
            continue
        field_set = set(fields)
        manifest_count += 1
        for row in rows:
            raw_path = next((row.get(key, "") for key in path_keys if key in field_set and row.get(key, "")), "")
            role = next((row.get(key, "") for key in role_keys if key in field_set and row.get(key, "")), "")
            if not raw_path and role:
                raw_path = role
            if not raw_path:
                continue
            artifact_path = Path(raw_path)
            if not artifact_path.is_absolute():
                candidate1 = manifest.parent / artifact_path
                candidate2 = project_root / artifact_path
                artifact_path = candidate1 if candidate1.exists() or not candidate2.exists() else candidate2
            sha = next((row.get(key, "") for key in sha_keys if key in field_set and row.get(key, "")), "") or None
            bytes_text = next((row.get(key, "") for key in byte_keys if key in field_set and row.get(key, "")), "")
            rows_text = next((row.get(key, "") for key in row_keys if key in field_set and row.get(key, "")), "")
            schema_version = next((row.get(key, "") for key in schema_keys if key in field_set and row.get(key, "")), "") or None
            try:
                bytes_value = int(float(bytes_text)) if bytes_text not in {"", "."} else None
            except ValueError:
                bytes_value = None
            try:
                rows_value = int(float(rows_text)) if rows_text not in {"", "."} else None
            except ValueError:
                rows_value = None
            run_id = infer_run_id(artifact_path) or infer_run_id(manifest)
            stage_key = infer_stage_key(artifact_path if artifact_path.is_absolute() else manifest, project_root)
            register_artifact(
                conn,
                artifact_path,
                run_id=run_id,
                stage_key=stage_key,
                role=role or artifact_path.name,
                sha256=sha,
                bytes_value=bytes_value,
                rows_value=rows_value,
                schema_version=schema_version,
                status="OBSERVED",
                manifest_path=str(manifest),
            )
            artifact_count += 1
    insert_metric(
        conn, None, "SSOT_INGEST", "artifact_manifests_ingested",
        str(manifest_count), str(project_root), status="CURRENT"
    )
    insert_metric(
        conn, None, "SSOT_INGEST", "manifest_artifact_rows_ingested",
        str(artifact_count), str(project_root), status="CURRENT"
    )


def scan_checkpoints(conn: sqlite3.Connection, project_root: Path) -> None:
    root = project_root / "metadata" / "build_tracker" / "checkpoints"
    if not root.exists():
        warn(conn, "CHECKPOINT_ROOT_MISSING", "Checkpoint root is missing.", root)
        return
    count = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() in {".md", ".json", ".log"}:
            source_document(conn, path, "checkpoint_document")
            count += 1
        elif path.suffix.lower() == ".tsv" or path.name.endswith(".tsv.gz"):
            source_document(conn, path, "checkpoint_tsv")
            count += 1
            if path.stat().st_size <= MAX_QC_BYTES:
                try:
                    parse_two_column_metrics(conn, path, project_root)
                except Exception as exc:
                    warn(conn, "CHECKPOINT_PARSE_ERROR", str(exc), path)
    insert_metric(
        conn, None, "SSOT_INGEST", "checkpoint_files_indexed",
        str(count), str(root), status="CURRENT"
    )


def extract_shell_assignment(path: Path, variable: str, project_root: Path) -> str | None:
    if not path.is_file():
        return None
    pattern = re.compile(rf'(?m)^{re.escape(variable)}=(?:"([^"]*)"|\'([^\']*)\'|([^\s#]+))')
    text = path.read_text(encoding="utf-8", errors="replace")
    match = pattern.search(text)
    if not match:
        return None
    value = next(group for group in match.groups() if group is not None)
    value = value.replace("${PROJECT_ROOT}", str(project_root)).replace("$PROJECT_ROOT", str(project_root))
    return value


def add_dataset(conn: sqlite3.Connection, **values: Any) -> None:
    conn.execute(
        """
        INSERT INTO datasets(
            dataset_id,accession,sample_label,organism,tissue,
            developmental_stage,sex,platform,library_method,
            dataset_role,status,source_path,metadata_json,notes
        ) VALUES(
            :dataset_id,:accession,:sample_label,:organism,:tissue,
            :developmental_stage,:sex,:platform,:library_method,
            :dataset_role,:status,:source_path,:metadata_json,:notes
        )
        ON CONFLICT(dataset_id) DO UPDATE SET
            accession=excluded.accession,
            sample_label=excluded.sample_label,
            organism=excluded.organism,
            tissue=excluded.tissue,
            developmental_stage=excluded.developmental_stage,
            sex=excluded.sex,
            platform=excluded.platform,
            library_method=excluded.library_method,
            dataset_role=excluded.dataset_role,
            status=excluded.status,
            source_path=excluded.source_path,
            metadata_json=excluded.metadata_json,
            notes=excluded.notes
        """,
        values,
    )


def add_active_implementation(
    conn: sqlite3.Connection,
    project_root: Path,
    *,
    stage_key: str,
    order: float,
    name: str,
    purpose: str,
    category: str,
    version: str,
    script_path: str,
    package_version: str | None,
    parameters: dict[str, Any] | None,
    rationale: str,
    evidence_path: str,
    validator_path: str | None = None,
) -> str:
    ensure_stage(
        conn,
        stage_key,
        order=order,
        name=name,
        purpose=purpose,
        category=category,
        status="IMPLEMENTED",
    )
    script = Path(script_path)
    script_sha = sha256_file(script) if script.is_file() else None
    validator_sha = sha256_file(Path(validator_path)) if validator_path and Path(validator_path).is_file() else None
    if not script.is_file():
        warn(conn, "ACTIVE_SCRIPT_MISSING", "Active implementation script is missing.", script)
    if validator_path and not Path(validator_path).is_file():
        warn(conn, "ACTIVE_VALIDATOR_MISSING", "Active validator is missing.", Path(validator_path))
    impl_id = implementation_id_for(stage_key, script_path, script_sha)
    conn.execute(
        """
        INSERT INTO implementations(
            implementation_id,stage_key,version,script_path,script_sha256,
            validator_path,validator_sha256,package_version,parameters_json,
            lifecycle_status,rationale,evidence_path,effective_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(implementation_id) DO UPDATE SET
            lifecycle_status='ACTIVE',
            rationale=excluded.rationale,
            evidence_path=excluded.evidence_path,
            effective_at=excluded.effective_at
        """,
        (
            impl_id,
            stage_key,
            version,
            script_path,
            script_sha,
            validator_path,
            validator_sha,
            package_version,
            json.dumps(parameters or {}, ensure_ascii=False, sort_keys=True),
            "ACTIVE",
            rationale,
            evidence_path,
            "2026-08-06T00:00:00+00:00",
        ),
    )
    source_document(conn, script, "active_pipeline_script", force_hash=True)
    if validator_path:
        source_document(conn, Path(validator_path), "active_validator", force_hash=True)
    return impl_id


def add_decision(
    conn: sqlite3.Connection,
    *,
    key: str,
    category: str,
    title: str,
    statement: str,
    status: str,
    confidence: str,
    rationale: str,
    evidence_path: str,
    effective_at: str = "2026-08-06T00:00:00+00:00",
    supersedes: str | None = None,
) -> str:
    decision_id = decision_id_for(key, effective_at)
    conn.execute(
        """
        INSERT OR REPLACE INTO decisions(
            decision_id,decision_key,category,title,statement,status,
            confidence,effective_at,supersedes_decision_id,rationale,evidence_path
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            decision_id,key,category,title,statement,status,confidence,
            effective_at,supersedes,rationale,evidence_path
        ),
    )
    return decision_id


def add_interpretation(
    conn: sqlite3.Connection,
    *,
    key: str,
    fact: str,
    interpretation: str,
    do_not: str,
    confidence: str,
    evidence_path: str,
    evidence_metrics: dict[str, Any],
    status: str = "ACTIVE",
    effective_at: str = "2026-08-06T00:00:00+00:00",
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO interpretations(
            interpretation_id,interpretation_key,fact_statement,interpretation,
            do_not_interpret_as,status,confidence,effective_at,evidence_path,
            evidence_metrics_json
        ) VALUES(?,?,?,?,?,?,?,?,?,?)
        """,
        (
            interpretation_id_for(key, effective_at),
            key,fact,interpretation,do_not,status,confidence,effective_at,
            evidence_path,json.dumps(evidence_metrics, ensure_ascii=False, sort_keys=True)
        ),
    )


def add_contract(
    conn: sqlite3.Connection,
    *,
    key: str,
    name: str,
    state: str,
    statement: str,
    implementation_id: str | None,
    evidence_path: str,
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO algorithm_contracts(
            contract_id,component_key,component_name,implementation_state,
            contract_statement,active_implementation_id,evidence_path,
            effective_at,status
        ) VALUES(?,?,?,?,?,?,?,?,?)
        """,
        (
            "contract_" + hashlib.sha256(key.encode()).hexdigest()[:20],
            key,name,state,statement,implementation_id,evidence_path,
            "2026-08-06T00:00:00+00:00","ACTIVE"
        ),
    )


def add_current_metric(
    conn: sqlite3.Connection,
    *,
    run_id: str | None,
    stage_key: str,
    name: str,
    value: str | int | float,
    source_path: str,
    unit: str | None = None,
    denominator: float | None = None,
) -> None:
    insert_metric(
        conn, run_id, stage_key, name, str(value), source_path,
        status="CURRENT", unit=unit, denominator=denominator
    )


def seed_curated(conn: sqlite3.Connection, project_root: Path) -> None:
    evidence_checkpoint = project_root / "metadata/build_tracker/checkpoints/20260803_182703_step11_rna_repeat_pilot/step11_checkpoint.md"
    hierarchy_doc = project_root / "docs/design/RNA-TR-Scout_population_reference_hierarchy_20260805.md"
    if not hierarchy_doc.exists():
        hierarchy_doc = project_root / "metadata/ssot/RNA_TR_Scout_SSOT_design_v0.1.0.md"

    target_meta = project_root / "metadata/encode/ENCSR307SHM"
    datasets = [
        dict(dataset_id="ENCODE_ENCSR307SHM", accession="ENCSR307SHM",
             sample_label="Homo sapiens fetal brain, female, 85 days",
             organism="Homo sapiens", tissue="brain", developmental_stage="embryo 85 days",
             sex="female", platform="Oxford Nanopore PromethION", library_method=None,
             dataset_role="TARGET_PILOT", status="ACTIVE", source_path=str(target_meta),
             metadata_json=None, notes="Primary 100k-read development pilot."),
        dict(dataset_id="ENCODE_ENCSR327TOR", accession="ENCSR327TOR",
             sample_label="Homo sapiens fetal brain, female, 117 days",
             organism="Homo sapiens", tissue="brain", developmental_stage="embryo 117 days",
             sex="female", platform="Oxford Nanopore PromethION", library_method=None,
             dataset_role="RNA_TECHNICAL_COMPARISON", status="ACTIVE",
             source_path="/media/tokushimaneuro02/T9/rnatr_reference/encode_ont_cdna_calibration/primary_fetal_brain_promethion_v0.1.0/ENCSR327TOR",
             metadata_json=None, notes="Closely matched comparison dataset; not a biological normal control."),
        dict(dataset_id="ENCODE_ENCSR582TMC", accession="ENCSR582TMC",
             sample_label="Homo sapiens fetal brain, female, 105 days",
             organism="Homo sapiens", tissue="brain", developmental_stage="embryo 105 days",
             sex="female", platform="Oxford Nanopore PromethION", library_method=None,
             dataset_role="RNA_TECHNICAL_COMPARISON", status="ACTIVE",
             source_path="/media/tokushimaneuro02/T9/rnatr_reference/encode_ont_cdna_calibration/primary_fetal_brain_promethion_v0.1.0/ENCSR582TMC",
             metadata_json=None, notes="Closely matched comparison dataset; not a biological normal control."),
        dict(dataset_id="ENCODE_ENCSR598UIY", accession="ENCSR598UIY",
             sample_label="Homo sapiens fetal brain, male, 104 days",
             organism="Homo sapiens", tissue="brain", developmental_stage="embryo 104 days",
             sex="male", platform="Oxford Nanopore PromethION", library_method=None,
             dataset_role="RNA_TECHNICAL_COMPARISON", status="ACTIVE",
             source_path="/media/tokushimaneuro02/T9/rnatr_reference/encode_ont_cdna_calibration/primary_fetal_brain_promethion_v0.1.0/ENCSR598UIY",
             metadata_json=None, notes="Closely matched comparison dataset; not a biological normal control."),
        dict(dataset_id="ENCODE_ENCSR852YUV", accession="ENCSR852YUV",
             sample_label="Homo sapiens fetal brain, 112 days",
             organism="Homo sapiens", tissue="brain", developmental_stage="embryo 112 days",
             sex=None, platform="Oxford Nanopore PromethION", library_method=None,
             dataset_role="RNA_TECHNICAL_COMPARISON", status="ACTIVE",
             source_path="/media/tokushimaneuro02/T9/rnatr_reference/encode_ont_cdna_calibration/primary_fetal_brain_promethion_v0.1.0/ENCSR852YUV",
             metadata_json=None, notes="Closely matched comparison dataset; not a biological normal control."),
        dict(dataset_id="ENCODE_ENCSR859DYW", accession="ENCSR859DYW",
             sample_label="Homo sapiens fetal brain, female, 109 days",
             organism="Homo sapiens", tissue="brain", developmental_stage="embryo 109 days",
             sex="female", platform="Oxford Nanopore PromethION", library_method=None,
             dataset_role="RNA_TECHNICAL_COMPARISON", status="ACTIVE",
             source_path="/media/tokushimaneuro02/T9/rnatr_reference/encode_ont_cdna_calibration/primary_fetal_brain_promethion_v0.1.0/ENCSR859DYW",
             metadata_json=None, notes="Closely matched comparison dataset; not a biological normal control."),
        dict(dataset_id="ENCODE_ENCSR887OJA", accession="ENCSR887OJA",
             sample_label="Homo sapiens fetal brain, male, 101 days",
             organism="Homo sapiens", tissue="brain", developmental_stage="embryo 101 days",
             sex="male", platform="Oxford Nanopore PromethION", library_method=None,
             dataset_role="RNA_TECHNICAL_COMPARISON", status="ACTIVE",
             source_path="/media/tokushimaneuro02/T9/rnatr_reference/encode_ont_cdna_calibration/primary_fetal_brain_promethion_v0.1.0/ENCSR887OJA",
             metadata_json=None, notes="Closely matched comparison dataset; not a biological normal control."),
    ]
    for dataset in datasets:
        add_dataset(conn, **dataset)

    ensure_run(
        conn, "ENCSR307SHM_pilot100k_mm2splice_v1",
        dataset_id="ENCODE_ENCSR307SHM", run_role="DEVELOPMENT_PILOT",
        pipeline_version="rnatr-scout 0.3.2", status="IN_PROGRESS",
        root_path=str(project_root),
        notes="Step 11 remains in progress; exact-span P0/P1 and P3 branches have completed subcomponents."
    )
    for accession in ("ENCSR327TOR","ENCSR582TMC","ENCSR598UIY","ENCSR852YUV","ENCSR859DYW","ENCSR887OJA"):
        ensure_run(
            conn, f"{accession}_sample100k_seed20260803_mm2splice_v1",
            dataset_id=f"ENCODE_{accession}",
            parent_run_id="ENCSR307SHM_pilot100k_mm2splice_v1",
            run_role="RNA_TECHNICAL_COMPARISON_MAPPING",
            pipeline_version="rnatr_mm2_splice_cDNA_v0.3.1",
            status="MAPPED",
            root_path=str(project_root / "results/11_equalized_100k_mapping/ENCSR307SHM_pilot100k_mm2splice_v1/rnatr_equalized_100k_mm2splice_mapping_v0.1.1/bam" / accession),
            notes="100k-read equalized comparison dataset."
        )

    mapping_command = project_root / "results/11_mapping/ENCSR307SHM_pilot100k_mm2splice_v1/ENCSR307SHM_pilot100k_mm2splice_v1.mapper_command.sh"
    mapping_impl = add_active_implementation(
        conn, project_root,
        stage_key="MAP_SPLICE", order=10, name="Splice-aware genome mapping",
        purpose="Map ONT cDNA long reads to GRCh38 while retaining secondary and supplementary alignments.",
        category="mapping", version="rnatr_mm2_splice_cDNA_v0.3.1",
        script_path=str(mapping_command), package_version="minimap2 2.31-r1302",
        parameters={"preset":"splice","threads":16,"secondary":True,"N":10,"MD":True,"cs":"long","junction_bed":"GENCODE v50"},
        rationale="Frozen mapping configuration used by the target pilot and six equalized comparison datasets.",
        evidence_path=str(project_root / "qc/11_equalized_100k_mapping/ENCSR307SHM_pilot100k_mm2splice_v1/rnatr_equalized_100k_mm2splice_mapping_v0.1.1/equalized_100k_mapping.qc.tsv"),
    )

    script_11b = project_root / "scripts/11b_extract_alignment_segments_and_target_candidates.sh"
    validator = extract_shell_assignment(script_11b, "VALIDATOR", project_root)
    if validator is None:
        validator = str(project_root / "config/evidence_schema/v0.3/patches/validator_v0.3.1/rnatr_v03_validate_tsv_validator_v0.3.1.py")
    impl_11b = add_active_implementation(
        conn, project_root,
        stage_key="11b_TARGET_ASSIGNMENT", order=20,
        name="Candidate target assignment",
        purpose="Assign mapped RNA reads to catalog-guided target regions using non-splice alignment blocks.",
        category="locus_assignment", version="rnatr_target_assignment_v0.3.1",
        script_path=str(script_11b), validator_path=validator,
        package_version="rnatr-scout 0.3.2",
        parameters={"target_padding_bp":500,"splice_N":"excluded_from_blocks","deletion_D":"included","secondary":"retain","supplementary":"retain"},
        rationale="Current frozen target-assignment producer for the 100k pilot.",
        evidence_path=str(evidence_checkpoint),
    )
    impl_11d3 = add_active_implementation(
        conn, project_root,
        stage_key="11d3_RAW_READ_PROJECTION", order=30,
        name="Raw-read target projection v0.3.3",
        purpose="Project assigned genomic target regions back to raw-read coordinates with hard-clip and secondary-sequence fixes.",
        category="raw_read_projection", version="v0.3.3",
        script_path=str(project_root / "scripts/11d3_project_targets_to_raw_reads_secondary_seq_fixed.sh"),
        package_version="rnatr-scout 0.3.2",
        parameters={"projection_version":"v0.3.3"},
        rationale="Adopted projection implementation; supersedes 11d and 11d2.",
        evidence_path=str(evidence_checkpoint),
    )
    impl_11e = add_active_implementation(
        conn, project_root, stage_key="11e_MOTIF_JOBS", order=40,
        name="Motif job classification", purpose="Classify projected candidates into motif scan jobs and priorities.",
        category="motif_classification", version="current",
        script_path=str(project_root / "scripts/11e_prepare_motif_scan_jobs.sh"),
        package_version="rnatr-scout 0.3.2", parameters={},
        rationale="Frozen motif-job preparation used for the target pilot.",
        evidence_path=str(evidence_checkpoint),
    )
    impl_11f = add_active_implementation(
        conn, project_root, stage_key="11f_PERIODIC_BASELINE", order=50,
        name="Simple-periodic baseline", purpose="Generate high-confidence motif-guided periodic calls.",
        category="repeat_measurement", version="current",
        script_path=str(project_root / "scripts/11f_run_high_confidence_simple_periodic_baseline.sh"),
        package_version="rnatr-scout 0.3.2", parameters={},
        rationale="Initial P0/P1 simple-periodic measurement stage.",
        evidence_path=str(evidence_checkpoint),
    )
    impl_11g = add_active_implementation(
        conn, project_root, stage_key="11g_BASELINE_AUDIT", order=60,
        name="Periodic baseline concordance audit", purpose="Audit baseline tract and target concordance.",
        category="technical_audit", version="current",
        script_path=str(project_root / "scripts/11g_audit_periodic_baseline_target_concordance.sh"),
        package_version="rnatr-scout 0.3.2", parameters={},
        rationale="Required audit before refinement.",
        evidence_path=str(evidence_checkpoint),
    )
    impl_11h = add_active_implementation(
        conn, project_root, stage_key="11h_PERIODIC_REFINEMENT", order=70,
        name="Target-constrained periodic refinement", purpose="Refine motif-guided tract calls within projected target geometry.",
        category="repeat_measurement", version="current",
        script_path=str(project_root / "scripts/11h_target_constrained_periodic_refinement.sh"),
        package_version="rnatr-scout 0.3.2", parameters={},
        rationale="Frozen refinement stage.",
        evidence_path=str(evidence_checkpoint),
    )
    impl_11i = add_active_implementation(
        conn, project_root, stage_key="11i_INTERNAL_RECLASSIFICATION", order=80,
        name="One-flank internal reclassification", purpose="Classify one-flank internal evidence and finalize sizing status.",
        category="evidence_classification", version="schema v0.3.1",
        script_path=str(project_root / "scripts/11i_reclassify_internal_one_flank_and_audit_span.sh"),
        package_version="rnatr-scout 0.3.2", parameters={},
        rationale="Adds LEFT_ONLY_INTERNAL/RIGHT_ONLY_INTERNAL and partial_internal handling.",
        evidence_path=str(evidence_checkpoint),
    )
    impl_11j = add_active_implementation(
        conn, project_root, stage_key="11j_EXACT_SPAN_CALIBRATION", order=90,
        name="Exact-span global periodicity calibration", purpose="Audit and calibrate exact-span periodicity across the full projected tract.",
        category="repeat_measurement", version="current",
        script_path=str(project_root / "scripts/11j_audit_exact_span_global_periodicity.sh"),
        package_version="rnatr-scout 0.3.2", parameters={},
        rationale="Frozen exact-span global calibration stage.",
        evidence_path=str(evidence_checkpoint),
    )
    impl_11k = add_active_implementation(
        conn, project_root, stage_key="11k_CALIBRATED_EVIDENCE", order=100,
        name="Calibrated simple-periodic evidence", purpose="Finalize calibrated P0/P1 repeat evidence.",
        category="evidence_finalization", version="current",
        script_path=str(project_root / "scripts/11k_finalize_calibrated_simple_periodic_evidence.sh"),
        package_version="rnatr-scout 0.3.2", parameters={},
        rationale="Produces the calibrated 49,793-row P0/P1 evidence table.",
        evidence_path=str(evidence_checkpoint),
    )
    impl_11k3 = add_active_implementation(
        conn, project_root, stage_key="11k3_SPAN_NORMALIZATION", order=110,
        name="Span-field normalization v0.3.3", purpose="Normalize exact-span fields and preserve pre-normalization values.",
        category="schema_normalization", version="v0.3.3",
        script_path=str(project_root / "scripts/11k3_normalize_calibrated_span_fields_fixed.sh"),
        package_version="rnatr-scout 0.3.2", parameters={"span_field_normalization":"v0.3.3"},
        rationale="Adopted normalized evidence output; supersedes 11k2.",
        evidence_path=str(evidence_checkpoint),
    )

    superseded = [
        ("11d3_RAW_READ_PROJECTION", project_root / "scripts/11d_project_targets_to_raw_reads.sh", "v0.3.1", "Superseded by 11d3."),
        ("11d3_RAW_READ_PROJECTION", project_root / "scripts/11d2_project_targets_to_raw_reads_hardclip_fixed.sh", "v0.3.2", "Superseded by 11d3 secondary-sequence fix."),
        ("11k3_SPAN_NORMALIZATION", project_root / "scripts/11k2_normalize_calibrated_span_fields.sh", "v0.3.2", "Superseded by 11k3 fixed normalization."),
    ]
    for stage_key, path, version, reason in superseded:
        if path.is_file():
            digest = sha256_file(path)
            conn.execute(
                """
                INSERT OR IGNORE INTO implementations(
                    implementation_id,stage_key,version,script_path,script_sha256,
                    lifecycle_status,rationale,evidence_path,effective_at
                ) VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (
                    implementation_id_for(stage_key, str(path), digest),
                    stage_key,version,str(path),digest,"SUPERSEDED",
                    reason,str(evidence_checkpoint),"2026-08-06T00:00:00+00:00"
                ),
            )

    add_decision(
        conn, key="primary_locus_catalog", category="reference",
        title="Primary locus and motif catalog",
        statement="TRExplorer v2 is the primary GRCh38 locus, boundary, and motif-prior catalog.",
        status="ACTIVE", confidence="HIGH",
        rationale="It provides near-complete addressability of the 11,042 pilot loci; RNA read sequence remains primary for observed molecule composition.",
        evidence_path=str(hierarchy_doc),
    )
    add_decision(
        conn, key="primary_population_reference", category="reference",
        title="Primary DNA population distribution",
        statement="AoU PacBio HiFi validation cohort (2,102 individuals) is the primary genome-wide DNA repeat-length and LPS context.",
        status="ACTIVE", confidence="HIGH",
        rationale="Large long-read cohort with allele-length and LPS percentiles; cohorts are not silently pooled.",
        evidence_path=str(hierarchy_doc),
    )
    add_decision(
        conn, key="tr_atlas_role", category="reference",
        title="TR-Atlas role",
        statement="TR-Atlas is supplementary short-read population context only; no further genome-wide live crawl is planned.",
        status="ACTIVE", confidence="HIGH",
        rationale="It is not the primary source for long-repeat sizing or motif decomposition.",
        evidence_path=str(hierarchy_doc),
    )
    add_decision(
        conn, key="general_locus_interpretation", category="interpretation",
        title="General-locus result terminology",
        statement="General loci are reported as population-relative longer, shorter, central, or non-comparable RNA observations; pathogenicity is not assigned.",
        status="ACTIVE", confidence="HIGH",
        rationale="Pathogenic thresholds are not established for most loci and RNA measurements do not directly reveal personal DNA genotype.",
        evidence_path=str(project_root / "results/11_population_relative_length_interpretation/ENCSR307SHM_pilot100k_mm2splice_v1"),
    )
    add_decision(
        conn, key="rna_comparison_panel_role", category="controls",
        title="Six fetal-brain datasets are a technical comparison panel",
        statement="The six fetal-brain PromethION datasets are used for RNA technical-bias characterization, not claimed as biological normal controls.",
        status="ACTIVE", confidence="HIGH",
        rationale="They match tissue, developmental period, laboratory, award, and platform, but library-method metadata are incomplete.",
        evidence_path=str(project_root / "qc/11_ont_cdna_calibration_panel_resolution/ENCSR307SHM_pilot100k_mm2splice_v1"),
    )
    add_decision(
        conn, key="large_file_storage", category="infrastructure",
        title="Large-file storage policy",
        statement="New raw FASTQ and other large public datasets are downloaded directly to /media/tokushimaneuro02/T9; Intel SSD retains active indexes, catalogs, QC, manifests, scripts, and compact results.",
        status="ACTIVE", confidence="HIGH",
        rationale="Avoids unnecessary Intel SSD consumption while preserving fast access to active indexes.",
        evidence_path=str(project_root / "qc/11_primary_fetal_brain_promethion_fastq_acquisition/ENCSR307SHM_pilot100k_mm2splice_v1"),
    )
    add_decision(
        conn, key="step11_status", category="project_state",
        title="Step 11 remains in progress",
        statement="Step 11 is not complete despite completed P0/P1 and P3 subbranches.",
        status="ACTIVE", confidence="HIGH",
        rationale="The build tracker explicitly retains Step 11 as in_progress.",
        evidence_path=str(evidence_checkpoint),
    )
    add_decision(
        conn, key="final_ranking_gate", category="project_state",
        title="Final ranking remains blocked",
        statement="Final candidate ranking is not executed until technical calibration, RNA LPS, and caller-contract gates are resolved.",
        status="ACTIVE", confidence="HIGH",
        rationale="Prevents DNA-to-RNA tail flags from being treated as biological or pathogenic calls.",
        evidence_path=str(project_root / "qc/11_population_relative_length_bias_stratification/ENCSR307SHM_pilot100k_mm2splice_v1"),
    )
    add_decision(
        conn, key="current_projection_implementation", category="pipeline",
        title="Current raw-read projection implementation",
        statement="11d3 / projection v0.3.3 is current; 11d and 11d2 are superseded.",
        status="ACTIVE", confidence="HIGH",
        rationale="Secondary-sequence and hard-clip fixes are incorporated.",
        evidence_path=str(evidence_checkpoint),
    )
    add_decision(
        conn, key="current_validator", category="pipeline",
        title="Current alignment-segment validator",
        statement="validator_v0.3.1 is current and accepts strand='.' for unmapped alignment records.",
        status="ACTIVE", confidence="HIGH",
        rationale="Prevents recurrence of the obsolete validator error during full-BAM replay.",
        evidence_path=validator,
    )
    add_decision(
        conn, key="analysis_pause_for_ssot", category="project_state",
        title="Replay paused for SSOT normalization",
        statement="The six-sample P0/P1 replay is paused until the SSOT database is built and validated.",
        status="ACTIVE", confidence="HIGH",
        rationale="Avoids further execution based on mixed old/new implementation memory.",
        evidence_path=str(project_root / "results/11_six_sample_frozen_p01_replay.stage6am_v0.1.1.console.log"),
    )

    add_interpretation(
        conn, key="population_coverage",
        fact="TRExplorer strict motif coverage is 11,028/11,042 and long-read population context is available for approximately 79.3% of pilot loci.",
        interpretation="Catalog addressability is nearly complete; population-distribution coverage remains incomplete but is no longer the dominant 3.65% bottleneck.",
        do_not="Do not describe 11,042 as all genomic TR loci or 79.3% as universal genome coverage.",
        confidence="HIGH",
        evidence_path=str(project_root / "results/11_bulk_longread_reference_crosswalk_coverage/ENCSR307SHM_pilot100k_mm2splice_v1/latest/summary/population_coverage_accounting.tsv"),
        evidence_metrics={"trexplorer_exact":11028,"denominator":11042,"longread_any":8755,"union_with_repeatcatalogs":8756},
    )
    add_interpretation(
        conn, key="max_statistic_inflation",
        fact="For loci with at least 10 RNA reads, the maximum is above the upper tail in 75.8% while median-longer shift is 2.6%.",
        interpretation="Maximum repeat length is strongly support-count dependent and primarily represents existence of an extreme molecule, not a locus-wide shift.",
        do_not="Do not interpret max-tail frequency as the fraction of biologically expanded loci.",
        confidence="HIGH",
        evidence_path=str(project_root / "results/11_population_relative_length_bias_stratification/ENCSR307SHM_pilot100k_mm2splice_v1"),
        evidence_metrics={"support_10_plus_max_longer_fraction":0.758169935,"median_longer_fraction":0.026143791},
    )
    add_interpretation(
        conn, key="homopolymer_bias",
        fact="Homopolymer loci show large bidirectional RNA-versus-DNA dispersion.",
        interpretation="Homopolymers require a separate technical class and cannot use the same small-difference thresholds as non-homopolymer repeats.",
        do_not="Do not treat a few-base homopolymer deviation as biological repeat extension or shortening.",
        confidence="HIGH",
        evidence_path=str(project_root / "results/11_population_relative_length_bias_stratification/ENCSR307SHM_pilot100k_mm2splice_v1"),
        evidence_metrics={"max_longer_fraction":0.390799031,"max_shorter_fraction":0.172881356},
    )
    add_interpretation(
        conn, key="rna_dna_median_difference",
        fact="Across comparable loci, RNA median minus AoU DNA median is centered at 0 bp with typical 10th–90th percentile differences of roughly -1.5 to +2 bp.",
        interpretation="Most small RNA-versus-DNA differences are within a technical floor rather than persuasive biological shifts.",
        do_not="Do not promote 1–4 bp differences or single-read maximum exceedances as definitive extension or shortening.",
        confidence="MODERATE",
        evidence_path=str(project_root / "results/11_population_relative_length_bias_stratification/ENCSR307SHM_pilot100k_mm2splice_v1"),
        evidence_metrics={"median_delta_bp_median":0,"q10":-1.5,"q90":2},
    )

    contracts = [
        ("locus_assignment","Locus assignment","IMPLEMENTED",
         "Catalog-guided target assignment uses splice-aware genomic mapping, 500-bp candidate padding, N-excluded alignment blocks, D-inclusive reference blocks, and retention of secondary/supplementary alignments.",
         impl_11b,str(evidence_checkpoint)),
        ("raw_read_projection","Raw-read projection","IMPLEMENTED",
         "Assigned genomic targets are projected to raw-read coordinates by the adopted 11d3 v0.3.3 implementation.",
         impl_11d3,str(evidence_checkpoint)),
        ("repeat_definition","Repeat definition and sizing","PARTIALLY_IMPLEMENTED",
         "Current P0/P1 measurement is catalog-motif-guided and raw-read-based; a final general caller that jointly re-estimates boundaries, motif composition, interruptions, compound structure, and LPS is not complete.",
         impl_11k3,str(evidence_checkpoint)),
        ("molecule_vs_locus_statistics","Molecule and locus statistics","IMPLEMENTED",
         "Single-read/extreme-molecule evidence, maximum, and locus-level median shifts are kept distinct.",
         None,str(project_root / "results/11_population_relative_length_interpretation/ENCSR307SHM_pilot100k_mm2splice_v1")),
        ("population_context","DNA population context","IMPLEMENTED_WITH_GATE",
         "DNA long-read distributions provide population context only after validated crosswalk; they do not infer personal DNA genotype or pathogenicity from RNA.",
         None,str(hierarchy_doc)),
        ("rna_lps","RNA longest pure segment","NOT_IMPLEMENTED",
         "AoU LPS statistics are attached as reference context, but RNA-side LPS measurement is not yet available.",
         None,str(project_root / "qc/11_aou_stat_semantics_rna_length_comparison/ENCSR307SHM_pilot100k_mm2splice_v1/latest")),
        ("transcript_observability","Transcript projection and repeat observability","DESIGNED_NOT_IMPLEMENTED",
         "The design distinguishes repeat absent from repeat not reached and will project loci to CDS/UTR/intron/isoform context after core caller stabilization.",
         None,str(project_root / "docs/design")),
        ("unmapped_alignment_validation","Unmapped alignment validation","IMPLEMENTED",
         "Unmapped BAM rows remain in full-read accounting with strand='.' accepted by validator_v0.3.1.",
         impl_11b,validator),
    ]
    for key,name,state,statement,impl,evidence in contracts:
        add_contract(conn,key=key,name=name,state=state,statement=statement,implementation_id=impl,evidence_path=evidence)

    references = [
        ("TREXPLORER_V2",1,"TRExplorer v2","Primary GRCh38 locus, boundary, and motif-prior catalog","DNA catalog",None,
         "Coordinates, canonical motif, motif size, reference copy number, purity, annotations",
         "Use for locus addressability and motif priors; verify observed RNA tract from raw-read sequence."),
        ("AOU_HIFI_VALIDATION_2102",2,"AoU HiFi validation cohort","Primary DNA long-read population distribution","PacBio HiFi",2102,
         "Allele-length percentiles; LPS per locus; LPS per motif",
         "Primary population context after exact or validated safe crosswalk."),
        ("AOU_HIFI_DISCOVERY_543",3,"AoU HiFi discovery cohort","Higher-depth HiFi confirmation","PacBio HiFi",543,
         "Allele-length and LPS distributions","Independent confirmation; do not silently pool."),
        ("AOU_1KGP_ONT_REPLICATION_500",4,"AoU/1KGP ONT replication","Cross-platform ONT confirmation","ONT DNA",500,
         "Allele-length and LPS distributions","Replication evidence with platform/caller retained."),
        ("VIENNA_ONT_V1_1",5,"1KG Vienna ONT v1.1","Secondary long-VNTR population source","ONT DNA",1019,
         "Repeat-unit and bp-length range/median; motif composition","Use only after boundary/motif reconciliation."),
        ("HPRC256",6,"HPRC256 within TRExplorer","Secondary HiFi allele histogram","PacBio HiFi",256,
         "Copy-number histogram","Secondary population evidence where available."),
        ("STRCHIVE",7,"STRchive","Known disease-locus context","Literature curation",None,
         "Known motif and published thresholds","Known disease loci only; not genome-wide population distribution."),
        ("TR_ATLAS",8,"TR-Atlas cached pilot subset","Supplementary short-read population context","Short-read DNA",None,
         "Frequency bins for exact/validated loci","No further live crawl; never primary for long-repeat sizing."),
    ]
    for key,priority,name,role,platform,cohort,use,policy in references:
        conn.execute(
            """
            INSERT OR REPLACE INTO reference_hierarchy(
                reference_key,priority,resource_name,role,platform,cohort_size,
                measurement_use,automatic_use_policy,status,source_path,effective_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (key,priority,name,role,platform,cohort,use,policy,"ACTIVE",str(hierarchy_doc),"2026-08-06T00:00:00+00:00"),
        )

    limitations = [
        ("GENERAL_PATHOGENICITY_UNDEFINED","Pathogenic/benign thresholds are not established for most TR loci.","CRITICAL",
         "Report population-relative RNA observations; reserve disease thresholds for curated known loci."),
        ("RNA_DNA_METHOD_DIFFERENCE","RNA ONT cDNA measurements and DNA HiFi population calls have platform, library, caller, and biological differences.","HIGH",
         "Use the six fetal-brain RNA datasets for technical-bias characterization and retain DNA comparison as context."),
        ("RNA_LPS_MISSING","RNA-side longest-pure-segment measurement is not implemented.","HIGH",
         "Implement raw-read motif decomposition and LPS after the general repeat caller contract is fixed."),
        ("CALLER_GENERALIZATION_INCOMPLETE","The current caller is catalog-motif-guided; general boundary/motif/interruption/compound-repeat inference remains incomplete.","CRITICAL",
         "Prioritize core caller specification and benchmark before broad biological interpretation."),
        ("POPULATION_COVERAGE_GAP","Approximately 20.7% of pilot loci lack current long-read population distribution context.","MODERATE",
         "Retain NOT_COMPARABLE; reconcile Vienna and add validated sources without unsafe overlap matching."),
        ("LIBRARY_METHOD_METADATA_INCOMPLETE","The target and six fetal-brain comparison datasets lack explicit library-method metadata in ENCODE.","MODERATE",
         "Describe them as closely matched PromethION datasets, not proven identical-protocol controls."),
        ("VIENNA_BOUNDARY_UNRESOLVED","Vienna ONT exact-coordinate coverage is zero under current exact matching because boundary definitions differ.","MODERATE",
         "Perform overlap plus motif reconciliation as a separate audited stage."),
    ]
    for key,statement,severity,mitigation in limitations:
        conn.execute(
            """
            INSERT OR REPLACE INTO limitations(
                limitation_key,statement,severity,status,mitigation,evidence_path,effective_at
            ) VALUES(?,?,?,?,?,?,?)
            """,
            (key,statement,severity,"ACTIVE",mitigation,str(hierarchy_doc),"2026-08-06T00:00:00+00:00"),
        )

    questions = [
        ("GENERAL_REPEAT_CALLER_CONTRACT","What exact algorithm will jointly infer RNA repeat boundaries, motif composition, interruptions, compound structure, total tract length, and LPS?","CRITICAL",1,
         "Freeze the algorithm contract and build synthetic plus real benchmark fixtures before final candidate ranking.",str(evidence_checkpoint)),
        ("SIX_SAMPLE_REPLAY","Can the frozen P0/P1 pipeline be replayed across the six equalized fetal-brain datasets without mixing obsolete validators or implementations?","CRITICAL",1,
         "Resume only after this SSOT database validates the active pipeline and failure history.",str(project_root / "results/11_six_sample_frozen_p01_replay.stage6am_v0.1.1.console.log")),
        ("RNA_TECHNICAL_FLOOR","What locus-, motif-, support-, and platform-specific difference should define the technical floor for longer/shorter RNA observations?","HIGH",1,
         "Complete the six-sample comparison using molecule- and locus-level statistics.",str(project_root / "results/11_population_relative_length_bias_stratification/ENCSR307SHM_pilot100k_mm2splice_v1")),
        ("TRANSCRIPT_OBSERVABILITY","Which genomic TR loci are actually reached and represented in complete RNA molecules, and how does this vary across CDS, UTR, intron, isoform, and platform?","HIGH",0,
         "Add transcript projection and observability after core caller stabilization.",str(project_root / "docs/design")),
        ("VIENNA_RECONCILIATION","How much additional population coverage is gained after safe Vienna ONT boundary/motif reconciliation?","MODERATE",0,
         "Run a separate audited reconciliation stage.",str(hierarchy_doc)),
    ]
    for key,question,priority,blocking,next_action,evidence in questions:
        conn.execute(
            """
            INSERT OR REPLACE INTO open_questions(
                question_key,question,priority,status,blocking,next_action,evidence_path,effective_at
            ) VALUES(?,?,?,?,?,?,?,?)
            """,
            (key,question,priority,"OPEN",blocking,next_action,evidence,"2026-08-06T00:00:00+00:00"),
        )

    failure_stage = "SIX_SAMPLE_P01_REPLAY"
    ensure_stage(conn, failure_stage, order=300, name="Six-sample P0/P1 replay", category="calibration", status="PAUSED")
    failures = [
        ("FAIL_6Z_V010",None,"11_bulk_longread_population_reference_acquisition","v0.1.0","RESOLVED",
         "Bulk-reference download timed out repeatedly near completion.","A 120-second total curl transfer timeout was inappropriate for ~205 MB and larger files.","v0.1.1 removed total transfer timeout and preserved partial files.",
         str(project_root / "qc/11_bulk_longread_population_reference_acquisition/ENCSR307SHM_pilot100k_mm2splice_v1")),
        ("FAIL_6AB_V010","ENCSR307SHM_pilot100k_mm2splice_v1","11_aou_stat_semantics_rna_length_comparison","v0.1.0","RESOLVED",
         "AoU comparison matched zero loci.","The parser read only TRID instead of the Stage 6AA-compatible all-field coordinate representation.","v0.1.1 reused the compatible parser and matched 8,556 loci.",
         str(project_root / "qc/11_aou_stat_semantics_rna_length_comparison/ENCSR307SHM_pilot100k_mm2splice_v1")),
        ("FAIL_6AE_V010","ENCSR307SHM_pilot100k_mm2splice_v1","11_matched_ont_cdna_control_discovery","v0.1.0","RESOLVED",
         "ENCODE discovery incorrectly returned zero human candidates.","Wrong ENCODE metadata fields and organism hierarchy were parsed.","v0.1.2 used replicate→library→biosample and identified three explicit PCR-cDNA plus fetal-brain PromethION candidates.",
         str(project_root / "qc/11_matched_ont_cdna_control_discovery/ENCSR307SHM_pilot100k_mm2splice_v1")),
        ("FAIL_6AI_V010","ENCSR307SHM_pilot100k_mm2splice_v1","11_equalized_100k_mapping","v0.1.0","RESOLVED",
         "minimap2 rejected the read-group line.","The script passed literal tab characters instead of escaped \\t.","v0.1.1 corrected the read-group encoding and mapped all six datasets.",
         str(project_root / "qc/11_equalized_100k_mapping/ENCSR307SHM_pilot100k_mm2splice_v1")),
        ("FAIL_6AM_V010",None,failure_stage,"v0.1.0","RESOLVED",
         "Replay stopped at 11b alignment-segment validation.","An obsolete validator treated strand='.' on unmapped records as missing.","Use validator_v0.3.1 while preserving full BAM accounting.",
         str(project_root / "results/11_six_sample_frozen_p01_replay.stage6am.console.log")),
        ("FAIL_6AM_V011",None,failure_stage,"v0.1.1","RESOLVED",
         "Mapped-only replay still failed 11b validation.","Filtering unmapped records violated the frozen 100,000-read accounting contract.","Preserve the full BAM and use the corrected validator; do not mapped-only filter.",
         str(project_root / "results/11_six_sample_frozen_p01_replay.stage6am_v0.1.1.console.log")),
        ("SAFETY_T9_ROOT_COPY",None,"INFRASTRUCTURE_FILE_TRANSFER","2026-08-06","RESOLVED",
         "An empty source variable caused an rsync command to copy the filesystem root into a dedicated T9 folder.","File-transfer commands relied on a possibly unset shell variable.","The erroneous T9 folder was manually removed; future large downloads use fixed absolute paths, mount checks, and no implicit move/delete.",
         "/media/tokushimaneuro02/T9/rnatr_reference/rnatr_population_reference/bulk_sources"),
    ]
    for failure_id,run_id,stage_key,version,status,summary,root_cause,resolution,source in failures:
        ensure_stage(conn, stage_key)
        if run_id:
            ensure_run(conn, run_id)
        conn.execute(
            """
            INSERT OR REPLACE INTO failures(
                failure_id,run_id,stage_key,attempt_version,status,summary,
                root_cause,resolution,source_path,recorded_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (failure_id,run_id,stage_key,version,status,summary,root_cause,resolution,source,NOW()),
        )

    current_metrics = [
        ("ENCSR307SHM_pilot100k_mm2splice_v1","P01_BACKBONE","exact_span_events",23867,
         project_root / "metadata/build_tracker/checkpoints/20260803_182703_step11_rna_repeat_pilot/step11_checkpoint.md",None,None),
        ("ENCSR307SHM_pilot100k_mm2splice_v1","P01_BACKBONE","exact_span_loci",11042,
         project_root / "results/11_p01_event_to_locus_backbone/ENCSR307SHM_pilot100k_mm2splice_v1",None,None),
        ("ENCSR307SHM_pilot100k_mm2splice_v1","11_bulk_longread_reference_crosswalk_coverage","trexplorer_exact_strict_motif_loci",11028,
         project_root / "results/11_bulk_longread_reference_crosswalk_coverage/ENCSR307SHM_pilot100k_mm2splice_v1/latest/summary/population_coverage_accounting.tsv",None,11042),
        ("ENCSR307SHM_pilot100k_mm2splice_v1","11_bulk_longread_reference_crosswalk_coverage","aou_validation_length_and_lps_addressable_loci",8556,
         project_root / "results/11_bulk_longread_reference_crosswalk_coverage/ENCSR307SHM_pilot100k_mm2splice_v1/latest/summary/population_coverage_accounting.tsv",None,11042),
        ("ENCSR307SHM_pilot100k_mm2splice_v1","11_bulk_longread_reference_crosswalk_coverage","longread_population_any_addressable_loci",8755,
         project_root / "results/11_bulk_longread_reference_crosswalk_coverage/ENCSR307SHM_pilot100k_mm2splice_v1/latest/summary/population_coverage_accounting.tsv",None,11042),
        ("ENCSR307SHM_pilot100k_mm2splice_v1","11_bulk_longread_reference_crosswalk_coverage","population_reference_union_with_repeatcatalogs_loci",8756,
         project_root / "results/11_bulk_longread_reference_crosswalk_coverage/ENCSR307SHM_pilot100k_mm2splice_v1/latest/summary/population_coverage_accounting.tsv",None,11042),
        ("ENCSR307SHM_pilot100k_mm2splice_v1","11_aou_stat_semantics_rna_length_comparison","primary_population_length_comparable_loci",8549,
         project_root / "qc/11_aou_stat_semantics_rna_length_comparison/ENCSR307SHM_pilot100k_mm2splice_v1/latest/aou_stat_semantics_rna_length_comparison.qc.tsv",None,11042),
        ("ENCSR307SHM_pilot100k_mm2splice_v1","11_population_relative_length_interpretation","rna_max_tail_loci",2829,
         project_root / "qc/11_population_relative_length_interpretation/ENCSR307SHM_pilot100k_mm2splice_v1",None,8549),
        ("ENCSR307SHM_pilot100k_mm2splice_v1","11_population_relative_length_interpretation","rna_median_tail_loci",2588,
         project_root / "qc/11_population_relative_length_interpretation/ENCSR307SHM_pilot100k_mm2splice_v1",None,8549),
        ("ENCSR307SHM_pilot100k_mm2splice_v1","11_population_relative_length_interpretation","rna_max_or_median_tail_union_loci",3122,
         project_root / "qc/11_population_relative_length_interpretation/ENCSR307SHM_pilot100k_mm2splice_v1",None,8549),
        ("ENCSR307SHM_pilot100k_mm2splice_v1","11_population_relative_length_interpretation","multiread_max_only_longer_molecule_loci",534,
         project_root / "qc/11_population_relative_length_interpretation/ENCSR307SHM_pilot100k_mm2splice_v1",None,None),
        ("ENCSR307SHM_pilot100k_mm2splice_v1","11_population_relative_length_interpretation","multiread_median_shift_longer_loci",381,
         project_root / "qc/11_population_relative_length_interpretation/ENCSR307SHM_pilot100k_mm2splice_v1",None,None),
        ("ENCSR307SHM_pilot100k_mm2splice_v1","11_population_relative_length_interpretation","multiread_median_shift_shorter_loci",409,
         project_root / "qc/11_population_relative_length_interpretation/ENCSR307SHM_pilot100k_mm2splice_v1",None,None),
        (None,"11_primary_fetal_brain_promethion_fastq_acquisition","primary_fastq_total_bytes",51197490146,
         project_root / "qc/11_primary_fetal_brain_promethion_fastq_acquisition/ENCSR307SHM_pilot100k_mm2splice_v1", "bytes",None),
        (None,"11_equalized_100k_read_pilot_builder","validated_total_reads",600000,
         project_root / "qc/11_equalized_100k_read_pilot_builder/ENCSR307SHM_pilot100k_mm2splice_v1", "reads",None),
        (None,"11_equalized_100k_mapping","mapped_bam_count",6,
         project_root / "qc/11_equalized_100k_mapping/ENCSR307SHM_pilot100k_mm2splice_v1/rnatr_equalized_100k_mm2splice_mapping_v0.1.1/equalized_100k_mapping.qc.tsv",None,None),
    ]
    for run_id,stage_key,name,value,source,unit,denominator in current_metrics:
        ensure_stage(conn, stage_key)
        add_current_metric(
            conn,run_id=run_id,stage_key=stage_key,name=name,value=value,
            source_path=str(source),unit=unit,denominator=denominator
        )

    current_artifacts = [
        ("ENCSR307SHM_pilot100k_mm2splice_v1","11b_TARGET_ASSIGNMENT","target_assignment",
         project_root / "results/11_assignment/ENCSR307SHM_pilot100k_mm2splice_v1/read_target_candidates.tsv.gz",388571),
        ("ENCSR307SHM_pilot100k_mm2splice_v1","11d3_RAW_READ_PROJECTION","raw_read_projection",
         project_root / "results/11_projection/ENCSR307SHM_pilot100k_mm2splice_v1/v0.3.3/read_target_projection.v0.3.3.tsv.gz",388571),
        ("ENCSR307SHM_pilot100k_mm2splice_v1","11e_MOTIF_JOBS","motif_scan_jobs",
         project_root / "results/11_motif_jobs/ENCSR307SHM_pilot100k_mm2splice_v1/motif_scan_jobs.tsv.gz",388571),
        ("ENCSR307SHM_pilot100k_mm2splice_v1","11k3_SPAN_NORMALIZATION","calibrated_p01_evidence_v0.3.3",
         project_root / "results/11_periodic_calibrated/ENCSR307SHM_pilot100k_mm2splice_v1/v0.3.3/simple_periodic_evidence.calibrated.v0.3.3.tsv.gz",49793),
    ]
    for run_id,stage_key,role,path,rows in current_artifacts:
        digest = sha256_file(path) if path.is_file() and path.stat().st_size <= MAX_DIRECT_HASH_BYTES else None
        register_artifact(
            conn,path,run_id=run_id,stage_key=stage_key,role=role,sha256=digest,
            bytes_value=path.stat().st_size if path.is_file() else None,
            rows_value=rows,schema_version="v0.3.3" if "v0.3.3" in str(path) else None,
            status="CURRENT" if path.is_file() else "EXPECTED_MISSING",
            is_current=True,notes="Curated current artifact."
        )
        if not path.is_file():
            warn(conn,"CURRENT_ARTIFACT_MISSING","Curated current artifact is missing.",path)


def validate_db(conn: sqlite3.Connection, project_root: Path) -> list[tuple[str, str, str]]:
    checks: list[tuple[str, str, str]] = []

    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    checks.append(("sqlite_integrity", "PASS" if integrity == "ok" else "FAIL", str(integrity)))

    fk_rows = conn.execute("PRAGMA foreign_key_check").fetchall()
    checks.append(("foreign_key_check", "PASS" if not fk_rows else "FAIL", str(len(fk_rows))))

    required_stages = [
        "MAP_SPLICE","11b_TARGET_ASSIGNMENT","11d3_RAW_READ_PROJECTION",
        "11e_MOTIF_JOBS","11f_PERIODIC_BASELINE","11g_BASELINE_AUDIT",
        "11h_PERIODIC_REFINEMENT","11i_INTERNAL_RECLASSIFICATION",
        "11j_EXACT_SPAN_CALIBRATION","11k_CALIBRATED_EVIDENCE",
        "11k3_SPAN_NORMALIZATION",
    ]
    for stage in required_stages:
        count = conn.execute(
            "SELECT COUNT(*) FROM implementations WHERE stage_key=? AND lifecycle_status='ACTIVE'",
            (stage,),
        ).fetchone()[0]
        checks.append((f"active_impl::{stage}", "PASS" if count == 1 else "FAIL", str(count)))

    active_missing = conn.execute(
        """
        SELECT script_path FROM implementations
        WHERE lifecycle_status='ACTIVE' AND (script_path IS NULL OR script_path='')
        """
    ).fetchall()
    checks.append(("active_implementation_paths_present", "PASS" if not active_missing else "FAIL", str(len(active_missing))))

    missing_files = []
    for row in conn.execute(
        "SELECT script_path FROM implementations WHERE lifecycle_status='ACTIVE'"
    ):
        if not Path(row[0]).is_file():
            missing_files.append(row[0])
    checks.append(("active_implementation_files_exist", "PASS" if not missing_files else "FAIL", ";".join(missing_files) or "0"))

    current_views = [
        "current_pipeline","current_decisions","current_interpretations",
        "current_algorithm_contract","current_reference_hierarchy",
        "current_known_limitations","current_open_questions","current_results",
    ]
    for view in current_views:
        count = conn.execute(f"SELECT COUNT(*) FROM {view}").fetchone()[0]
        checks.append((f"view_rows::{view}", "PASS" if count > 0 else "FAIL", str(count)))

    target_artifacts = conn.execute(
        "SELECT COUNT(*) FROM current_artifacts WHERE run_id='ENCSR307SHM_pilot100k_mm2splice_v1'"
    ).fetchone()[0]
    checks.append(("current_target_artifacts", "PASS" if target_artifacts >= 4 else "FAIL", str(target_artifacts)))

    old_records = conn.execute("SELECT COUNT(*) FROM legacy_records").fetchone()[0]
    old_db = project_root / "metadata/build_tracker/rnatr_build_tracker.sqlite"
    old_expected = old_db.is_file()
    checks.append((
        "legacy_tracker_import",
        "PASS" if (old_records > 0 or not old_expected) else "FAIL",
        str(old_records),
    ))

    failures = [check for check in checks if check[1] == "FAIL"]
    if failures:
        return checks

    # Ensure the current validator decision and current 11b validator agree.
    row = conn.execute(
        """
        SELECT validator_path FROM current_pipeline
        WHERE stage_key='11b_TARGET_ASSIGNMENT'
        """
    ).fetchone()
    if row and row[0]:
        validator_exists = Path(row[0]).is_file()
        checks.append(("current_validator_exists", "PASS" if validator_exists else "FAIL", row[0]))
    else:
        checks.append(("current_validator_exists", "FAIL", "not recorded"))

    return checks


def export_query(conn: sqlite3.Connection, query: str, output: Path) -> int:
    cursor = conn.execute(query)
    fields = [description[0] for description in cursor.description or []]
    rows = cursor.fetchall()
    tmp = output.with_name(f".{output.name}.{os.getpid()}.part")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(fields)
        for row in rows:
            writer.writerow(list(row))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, output)
    return len(rows)


def export_views(conn: sqlite3.Connection, ssot_root: Path) -> dict[str, int]:
    export_root = ssot_root / "exports"
    views = [
        "project_dashboard",
        "current_pipeline",
        "current_decisions",
        "current_interpretations",
        "current_algorithm_contract",
        "current_reference_hierarchy",
        "current_known_limitations",
        "current_open_questions",
        "current_results",
        "current_runs",
        "latest_stage_status",
        "current_artifacts",
    ]
    counts = {}
    for view in views:
        counts[view] = export_query(
            conn, f"SELECT * FROM {view}", export_root / f"{view}.tsv"
        )
    return counts


def write_summary(
    conn: sqlite3.Connection,
    ssot_root: Path,
    checks: Sequence[tuple[str, str, str]],
    exports: dict[str, int],
) -> Path:
    summary = ssot_root / "CURRENT_STATE.md"
    pipeline = conn.execute(
        "SELECT stage_order,stage_key,name,version,script_path FROM current_pipeline"
    ).fetchall()
    decisions = conn.execute(
        "SELECT decision_key,statement FROM current_decisions"
    ).fetchall()
    questions = conn.execute(
        "SELECT question_key,priority,blocking,question FROM current_open_questions"
    ).fetchall()
    metrics = conn.execute(
        "SELECT stage_key,metric_name,value_text,denominator_num FROM current_results"
    ).fetchall()
    lines = [
        "# RNA-TR-Scout Single Source of Truth",
        "",
        f"- Generated: {NOW()}",
        f"- Tool: {TOOL_VERSION}",
        f"- Database: `{ssot_root / 'rnatr_ssot.sqlite'}`",
        "- Existing legacy build-tracker database: read-only source; not modified.",
        "",
        "## Validation",
        "",
        "| check | status | detail |",
        "|---|---:|---|",
    ]
    lines.extend(
        f"| {name} | {status} | {str(detail).replace('|','/')} |"
        for name,status,detail in checks
    )
    lines.extend([
        "",
        "## Current pipeline",
        "",
        "| order | stage | name | version | script |",
        "|---:|---|---|---|---|",
    ])
    lines.extend(
        f"| {order} | {stage} | {name} | {version or '.'} | `{script or '.'}` |"
        for order,stage,name,version,script in pipeline
    )
    lines.extend([
        "",
        "## Current decisions",
        "",
    ])
    lines.extend(f"- **{key}** — {statement}" for key,statement in decisions)
    lines.extend([
        "",
        "## Current key results",
        "",
        "| stage | metric | value | denominator |",
        "|---|---|---:|---:|",
    ])
    lines.extend(
        f"| {stage or '.'} | {metric} | {value} | {denom if denom is not None else '.'} |"
        for stage,metric,value,denom in metrics
    )
    lines.extend([
        "",
        "## Blocking and open questions",
        "",
    ])
    lines.extend(
        f"- **{priority} / blocking={bool(blocking)} / {key}** — {question}"
        for key,priority,blocking,question in questions
    )
    lines.extend([
        "",
        "## Exports",
        "",
    ])
    lines.extend(
        f"- `{name}.tsv`: {count} rows"
        for name,count in sorted(exports.items())
    )
    tmp = summary.with_name(f".{summary.name}.{os.getpid()}.part")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp, summary)
    return summary


def rebuild(project_root: Path, allow_nonstandard_root: bool = False) -> int:
    project_root = project_root.resolve()
    if project_root != DEFAULT_PROJECT_ROOT and not allow_nonstandard_root:
        raise SSOTError(
            f"Refusing nonstandard project root without --allow-nonstandard-root: {project_root}"
        )
    if not project_root.is_dir():
        raise SSOTError(f"Project root not found: {project_root}")

    ssot_root = project_root / "metadata" / "ssot"
    ssot_root.mkdir(parents=True, exist_ok=True)
    final_db = ssot_root / "rnatr_ssot.sqlite"
    fd, temp_name = tempfile.mkstemp(
        prefix=".rnatr_ssot.", suffix=".part.sqlite", dir=ssot_root
    )
    os.close(fd)
    temp_db = Path(temp_name)
    started = NOW()
    old_db = project_root / "metadata" / "build_tracker" / "rnatr_build_tracker.sqlite"
    old_sha: str | None = None

    try:
        conn = sqlite3.connect(temp_db)
        conn.row_factory = sqlite3.Row
        conn.executescript(SCHEMA_SQL)
        conn.execute("INSERT INTO schema_info(key,value) VALUES('schema_version',?)", (str(SCHEMA_VERSION),))
        conn.execute("INSERT INTO schema_info(key,value) VALUES('tool_version',?)", (TOOL_VERSION,))
        conn.execute("INSERT INTO schema_info(key,value) VALUES('project_root',?)", (str(project_root),))
        conn.execute("INSERT INTO schema_info(key,value) VALUES('generated_at',?)", (started,))
        ingestion_id = conn.execute(
            """
            INSERT INTO ingestion_runs(
                started_at,status,tool_version,project_root,notes
            ) VALUES(?,?,?,?,?)
            """,
            (started, "RUNNING", TOOL_VERSION, str(project_root),
             "Atomic rebuild from legacy tracker, scripts, checkpoints, QC, manifests, and curated current decisions."),
        ).lastrowid

        ensure_stage(conn, "SSOT_INGEST", order=0, name="SSOT ingestion", purpose="Build the single source of truth database.", category="infrastructure", status="IMPLEMENTED")
        old_sha = import_legacy_sqlite(conn, old_db)
        import_legacy_exports(conn, project_root / "metadata" / "build_tracker")
        scan_scripts(conn, project_root)
        scan_qc(conn, project_root)
        scan_manifests(conn, project_root)
        scan_checkpoints(conn, project_root)
        seed_curated(conn, project_root)

        checks = validate_db(conn, project_root)
        failed = [row for row in checks if row[1] == "FAIL"]
        conn.execute(
            """
            UPDATE ingestion_runs SET finished_at=?,status=?,old_tracker_db_sha256=?
            WHERE ingestion_id=?
            """,
            (NOW(), "FAIL" if failed else "PASS", old_sha, ingestion_id),
        )
        conn.commit()

        if failed:
            report = "; ".join(f"{name}:{detail}" for name,_,detail in failed)
            raise SSOTError(f"SSOT validation failed: {report}")

        backup = None
        if final_db.exists():
            backup_dir = ssot_root / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup = backup_dir / f"rnatr_ssot.{stamp}.sqlite"
            shutil.copy2(final_db, backup)
        os.replace(temp_db, final_db)
        conn.close()

        final_conn = sqlite3.connect(final_db)
        final_conn.row_factory = sqlite3.Row
        exports = export_views(final_conn, ssot_root)
        summary = write_summary(final_conn, ssot_root, checks, exports)
        final_conn.close()

        validation_path = ssot_root / "exports" / "validation.tsv"
        with validation_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
            writer.writerow(["check", "status", "detail"])
            writer.writerows(checks)

        print("===== RNA-TR-SCOUT SSOT BUILD =====")
        print(f"status\tPASS")
        print(f"tool_version\t{TOOL_VERSION}")
        print(f"database\t{final_db}")
        print(f"database_sha256\t{sha256_file(final_db)}")
        print(f"legacy_tracker\t{old_db}")
        print(f"legacy_tracker_sha256\t{old_sha or '.'}")
        print(f"legacy_tracker_modified\tfalse")
        print(f"summary\t{summary}")
        print(f"exports\t{ssot_root / 'exports'}")
        print(f"backup_created\t{backup or '.'}")
        print(f"warnings\t{sqlite3.connect(final_db).execute('SELECT COUNT(*) FROM scan_warnings').fetchone()[0]}")
        return 0
    finally:
        if temp_db.exists():
            temp_db.unlink()


def connect_existing(project_root: Path) -> sqlite3.Connection:
    db = project_root / "metadata" / "ssot" / "rnatr_ssot.sqlite"
    if not db.is_file():
        raise SSOTError(f"SSOT database not found: {db}")
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def print_rows(cursor: sqlite3.Cursor) -> None:
    fields = [item[0] for item in cursor.description or []]
    rows = cursor.fetchall()
    if not fields:
        return
    print("\t".join(fields))
    for row in rows:
        print("\t".join("." if value is None else str(value) for value in row))


def show(project_root: Path, view: str) -> int:
    allowed = {
        "dashboard": "project_dashboard",
        "pipeline": "current_pipeline",
        "decisions": "current_decisions",
        "interpretations": "current_interpretations",
        "algorithm": "current_algorithm_contract",
        "references": "current_reference_hierarchy",
        "limitations": "current_known_limitations",
        "questions": "current_open_questions",
        "results": "current_results",
        "runs": "current_runs",
        "stages": "latest_stage_status",
        "artifacts": "current_artifacts",
    }
    if view not in allowed:
        raise SSOTError(f"Unknown view: {view}; choose from {sorted(allowed)}")
    conn = connect_existing(project_root)
    try:
        print_rows(conn.execute(f"SELECT * FROM {allowed[view]}"))
    finally:
        conn.close()
    return 0


def validate_existing(project_root: Path) -> int:
    conn = connect_existing(project_root)
    try:
        checks = validate_db(conn, project_root)
        print("check\tstatus\tdetail")
        for row in checks:
            print("\t".join(str(value) for value in row))
        return 1 if any(status == "FAIL" for _,status,_ in checks) else 0
    finally:
        conn.close()


def query_read_only(project_root: Path, sql: str) -> int:
    normalized = sql.lstrip().upper()
    if not (normalized.startswith("SELECT") or normalized.startswith("WITH") or normalized.startswith("PRAGMA")):
        raise SSOTError("Only read-only SELECT/WITH/PRAGMA queries are allowed.")
    forbidden = re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|VACUUM|ATTACH|DETACH)\b", re.I)
    if forbidden.search(sql):
        raise SSOTError("Write-capable SQL is not allowed.")
    conn = connect_existing(project_root)
    try:
        print_rows(conn.execute(sql))
    finally:
        conn.close()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="RNA-TR-Scout Single Source of Truth database"
    )
    parser.add_argument(
        "--project-root", type=Path, default=DEFAULT_PROJECT_ROOT
    )
    parser.add_argument(
        "--allow-nonstandard-root", action="store_true",
        help="Required only for testing outside /mnt/intelssd/rnatr_project."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("rebuild", help="Atomically rebuild the SSOT database.")
    show_parser = sub.add_parser("show", help="Show a curated current-state view.")
    show_parser.add_argument(
        "view",
        choices=[
            "dashboard","pipeline","decisions","interpretations","algorithm",
            "references","limitations","questions","results","runs","stages","artifacts"
        ],
    )
    sub.add_parser("validate", help="Validate the existing SSOT database.")
    query_parser = sub.add_parser("query", help="Run a read-only SQL query.")
    query_parser.add_argument("sql")

    args = parser.parse_args(argv)
    try:
        if args.command == "rebuild":
            return rebuild(args.project_root, args.allow_nonstandard_root)
        if args.command == "show":
            return show(args.project_root.resolve(), args.view)
        if args.command == "validate":
            return validate_existing(args.project_root.resolve())
        if args.command == "query":
            return query_read_only(args.project_root.resolve(), args.sql)
        raise SSOTError(f"Unhandled command: {args.command}")
    except (SSOTError, sqlite3.Error, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

PYCODE
python -m py_compile "$CLI.part"
mv "$CLI.part" "$CLI"
chmod 0755 "$CLI"

cat > "$DESIGN.part" <<'MDCODE'
# RNA-TR-Scout Single Source of Truth database

## Purpose

The SSOT database separates:

1. **Facts** — runs, stages, scripts, checksums, inputs, outputs, QC, counts.
2. **Decisions** — which implementation or reference is currently adopted and what it supersedes.
3. **Interpretations** — what an observed result means, and what it must not be interpreted as.

The legacy build tracker remains read-only and is imported for provenance.

## Installed paths

```text
/mnt/intelssd/rnatr_project/metadata/ssot/
├── rnatr_ssot.sqlite
├── rnatr_ssot.py
├── CURRENT_STATE.md
├── exports/
└── backups/
```

## Current-state views

- `current_pipeline`
- `current_decisions`
- `current_interpretations`
- `current_algorithm_contract`
- `current_reference_hierarchy`
- `current_known_limitations`
- `current_open_questions`
- `current_results`
- `current_runs`
- `latest_stage_status`
- `current_artifacts`
- `project_dashboard`

## Commands

```bash
SSOT=/mnt/intelssd/rnatr_project/metadata/ssot/rnatr_ssot.py

python "$SSOT" rebuild
python "$SSOT" validate
python "$SSOT" show dashboard
python "$SSOT" show pipeline
python "$SSOT" show algorithm
python "$SSOT" show decisions
python "$SSOT" show interpretations
python "$SSOT" show references
python "$SSOT" show limitations
python "$SSOT" show questions
python "$SSOT" show results
```

Read-only SQL is also available:

```bash
python "$SSOT" query \
  "SELECT * FROM current_pipeline ORDER BY stage_order"
```

## Update policy

After a new pipeline stage finishes, run:

```bash
python /mnt/intelssd/rnatr_project/metadata/ssot/rnatr_ssot.py rebuild
```

The rebuild is atomic. An existing SSOT database is backed up first. The legacy tracker database, raw data, results, QC, scripts, and references are not modified.

A future production wrapper should call `rebuild` only after its own outputs and QC have been atomically finalized.

## Status vocabulary

### Decisions and interpretations

- `ACTIVE`
- `SUPERSEDED`
- `PROVISIONAL`
- `REJECTED`
- `LEGACY`

### Algorithm implementation state

- `IMPLEMENTED`
- `IMPLEMENTED_WITH_GATE`
- `PARTIALLY_IMPLEMENTED`
- `DESIGNED_NOT_IMPLEMENTED`
- `NOT_IMPLEMENTED`
- `DEPRECATED`

## Scientific interpretation rule

For general loci, RNA-TR-Scout reports population-relative longer, shorter, central, or non-comparable observations. It does not assign pathogenicity. Known disease-locus thresholds remain a separate curated context.

MDCODE
mv "$DESIGN.part" "$DESIGN"

SELF="$(readlink -f "$0")"
if [[ "$SELF" != "$INSTALLED_SCRIPT" ]]; then
  if [[ -e "$INSTALLED_SCRIPT" ]]; then
    old_sha="$(sha256sum "$INSTALLED_SCRIPT" | awk '{print $1}')"
    new_sha="$(sha256sum "$SELF" | awk '{print $1}')"
    if [[ "$old_sha" != "$new_sha" ]]; then
      echo "ERROR: installed script path already contains different content: $INSTALLED_SCRIPT" >&2
      exit 2
    fi
  else
    cp "$SELF" "$INSTALLED_SCRIPT.part"
    chmod 0755 "$INSTALLED_SCRIPT.part"
    mv "$INSTALLED_SCRIPT.part" "$INSTALLED_SCRIPT"
  fi
fi

echo "===== RNATR SSOT INSTALL / MIGRATION ====="
echo "installer version:       $INSTALLER_VERSION"
echo "project root:            $PROJECT_ROOT"
echo "legacy tracker policy:   READ ONLY"
echo "new database:            $SSOT_ROOT/rnatr_ssot.sqlite"
echo "atomic rebuild:          ENABLED"
echo "existing SSOT backup:    ENABLED"
echo "raw/results/qc/scripts:  NOT MODIFIED"
echo "T9 access:               NOT USED"
echo "CLI SHA-256:             $(sha256sum "$CLI" | awk '{print $1}')"
echo "Design:                  $DESIGN"

python "$CLI" --project-root "$PROJECT_ROOT" rebuild

echo
echo "===== CURRENT DASHBOARD ====="
python "$CLI" --project-root "$PROJECT_ROOT" show dashboard

echo
echo "===== CURRENT PIPELINE ====="
python "$CLI" --project-root "$PROJECT_ROOT" show pipeline

echo
echo "===== BLOCKING QUESTIONS ====="
python "$CLI" --project-root "$PROJECT_ROOT" query   "SELECT question_key,priority,blocking,question,next_action FROM current_open_questions WHERE blocking=1 ORDER BY priority,question_key"

echo
echo "Installed CLI:  $CLI"
echo "Database:       $SSOT_ROOT/rnatr_ssot.sqlite"
echo "Current state:  $SSOT_ROOT/CURRENT_STATE.md"
echo "Exports:        $SSOT_ROOT/exports"
echo "Legacy tracker: unchanged"
