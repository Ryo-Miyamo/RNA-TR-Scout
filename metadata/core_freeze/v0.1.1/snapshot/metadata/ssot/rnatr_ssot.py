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

TOOL_VERSION = "rnatr_ssot_v0.1.2"
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



def resolve_current_validator(project_root: Path) -> Path:
    """
    Resolve the adopted validator explicitly.

    Do not infer the current validator from the legacy 11b shell variable:
    older scripts can contain VALIDATOR="$SCHEMA_DIR/..." and that string is
    provenance, not the current adopted implementation.
    """
    preferred = (
        project_root
        / "config/evidence_schema/v0.3/patches/validator_v0.3.1"
        / "rnatr_v03_validate_tsv_validator_v0.3.1.py"
    )
    if preferred.is_file():
        return preferred.resolve()

    patch_root = (
        project_root
        / "config/evidence_schema/v0.3/patches/validator_v0.3.1"
    )
    candidates = sorted(
        path.resolve()
        for path in patch_root.glob("*.py")
        if path.is_file()
        and "validate" in path.name.lower()
        and "0.3.1" in path.name.lower()
    )
    if len(candidates) == 1:
        return candidates[0]

    raise SSOTError(
        "Current validator v0.3.1 could not be resolved uniquely. "
        f"Preferred={preferred}; candidates={candidates}"
    )


def ensure_no_unexpanded_path_variables(path_text: str, label: str) -> None:
    if "$" in path_text:
        raise SSOTError(
            f"Unexpanded shell variable is not allowed in current SSOT {label}: "
            f"{path_text}"
        )


STAGE15T_EFFECTIVE_AT = "2026-08-12T09:45:00+00:00"

def _stage15t_decision_id(key: str) -> str:
    return decision_id_for(key, STAGE15T_EFFECTIVE_AT)

def _stage15t_interpretation_id(key: str) -> str:
    return interpretation_id_for(key, STAGE15T_EFFECTIVE_AT)

def _stage15t_contract_id(key: str) -> str:
    token = f"stage15t\0{key}\0{STAGE15T_EFFECTIVE_AT}"
    return "contract_" + hashlib.sha256(token.encode("utf-8")).hexdigest()[:20]


def _stage15t_apply_registration_overlay(conn, project_root):
    conn.row_factory = sqlite3.Row
    close_questions = {
        "ARCHITECTURE_CONSISTENCY_AUDIT_CLOSURE": "Closed for local Core Freeze; retain exact-original audit cadence for future major changes.",
        "CORE_FREEZE_PACKET": "Core Freeze Packet v0.1.1 registered and checksum-bound for local Core Freeze scope.",
        "GOLDEN_REGRESSION_SUITE": "Canonical Stage15Q full-evidence suite accepted and final-governance revalidation required by Stage15T.",
        "PROJECT_WIDE_DOCS_CANONICALIZATION": "Canonical project-wide layout registered; deletion remains separately controlled.",
    }
    for key, next_action in close_questions.items():
        row = conn.execute("SELECT status FROM open_questions WHERE question_key=?", (key,)).fetchone()
        if row is None or row[0] != "OPEN":
            raise Stage15TError(f"SSOT baseline question mismatch: {key}: {row}")
        conn.execute(
            "UPDATE open_questions SET status='CLOSED',blocking=0,next_action=?,evidence_path=?,effective_at=? WHERE question_key=?",
            (next_action, f"{project_root}/docs/core_freeze/v0.1.1/RNA_TR_Scout_Core_Freeze_Packet_v0.1.1.md", STAGE15T_EFFECTIVE_AT, key),
        )
    row = conn.execute("SELECT status FROM open_questions WHERE question_key='BIOLOGY_READY_INTERPRETATION_OUTPUT_AUDIT'").fetchone()
    if row is None or row[0] != "OPEN":
        raise Stage15TError("SSOT biology question baseline mismatch")
    conn.execute(
        "UPDATE open_questions SET blocking=0,next_action=?,evidence_path=?,effective_at=? WHERE question_key='BIOLOGY_READY_INTERPRETATION_OUTPUT_AUDIT'",
        (
            "Begin post-Freeze G20-G23 sidecar/interpretation implementation without rewriting the Core five-table source of truth.",
            f"{project_root}/docs/core_freeze/v0.1.1/RNA_TR_Scout_Core_Freeze_Packet_v0.1.1.md",
            STAGE15T_EFFECTIVE_AT,
        ),
    )
    if conn.execute("SELECT COUNT(*) FROM open_questions WHERE question_key='CORE_FREEZE_GIT_TAG_AND_PUBLIC_RELEASE_BINDING'").fetchone()[0] != 0:
        raise Stage15TError("SSOT new Git/public-release question already exists")
    conn.execute(
        "INSERT INTO open_questions(question_key,question,priority,status,blocking,next_action,evidence_path,effective_at) VALUES(?,?,?,?,?,?,?,?)",
        (
            "CORE_FREEZE_GIT_TAG_AND_PUBLIC_RELEASE_BINDING",
            "Has the local Core Freeze been converted into a clean-install, cross-hardware, full-commit/tag-bound, thesis-citable public v0.5.0 release?",
            "HIGH", "OPEN", 0,
            "Complete G25-G30, repository/lock/license/CITATION work, clean install and immutable Git release binding.",
            f"{project_root}/docs/contracts/RNA_TR_Scout_Core_Technical_Completion_and_Freeze_contract_v0.1.2.md",
            STAGE15T_EFFECTIVE_AT,
        ),
    )

    decision_rows = [
        (
            "core_freeze_v0_1_0_acceptance_v0_1_0", "core_freeze", "Accept local checksummed Core Freeze v0.1.0",
            "The validated generic Core is accepted as LOCAL_CORE_FREEZE_V0.1.0_ACCEPTED_WITH_SCOPE, permitting biology-sidecar work while public release gates remain open.",
            "HIGH", "Stage15Q golden plus Stage15R/15S exact-original closure and owner approval support the scoped local Freeze.",
            f"{project_root}/docs/core_freeze/v0.1.1/RNA_TR_Scout_Core_Freeze_Packet_v0.1.1.md",
        ),
        (
            "stage15r_candidate_multiplicity_closure_v0_1_0", "architecture", "Close technical candidate-multiplicity inspection",
            "Stage15R technical reverse traceability passed with biology weighting deferred post-Freeze.",
            "HIGH", "57 representative reads and 733/733 assignment-to-evidence chains had zero unresolved trace failures.",
            f"{project_root}/docs/contracts/RNA_TR_Scout_Candidate_assignment_reverse_traceability_contract_v0.1.1.md",
        ),
        (
            "stage15s_extensibility_hygiene_closure_v0_1_0", "architecture", "Accept future-extensibility and final-hygiene audit",
            "Seven extension boundaries contain no pre-Freeze hard coupling and final hygiene passes with cleanup/Git/public-release scope retained.",
            "HIGH", "Exact active code, schemas, manifests, contracts and both SSOT SQLite originals were audited.",
            f"{project_root}/docs/governance/RNA_TR_Scout_Core_Freeze_final_hygiene_audit_v0.1.0.md",
        ),
    ]
    for key, category, title, statement, confidence, rationale, evidence in decision_rows:
        if conn.execute("SELECT COUNT(*) FROM decisions WHERE decision_key=? AND status='ACTIVE'", (key,)).fetchone()[0] != 0:
            raise Stage15TError(f"SSOT decision already active: {key}")
        conn.execute(
            "INSERT INTO decisions(decision_id,decision_key,category,title,statement,status,confidence,effective_at,supersedes_decision_id,rationale,evidence_path) VALUES(?,?,?,?,?,'ACTIVE',?,?,NULL,?,?)",
            (_stage15t_decision_id(key), key, category, title, statement, confidence, STAGE15T_EFFECTIVE_AT, rationale, evidence),
        )

    ikey = "candidate_assignment_count_not_biological_event_count_v0_1_0"
    if conn.execute("SELECT COUNT(*) FROM interpretations WHERE interpretation_key=? AND status='ACTIVE'", (ikey,)).fetchone()[0] != 0:
        raise Stage15TError("SSOT interpretation already active")
    conn.execute(
        "INSERT INTO interpretations(interpretation_id,interpretation_key,fact_statement,interpretation,do_not_interpret_as,status,confidence,effective_at,supersedes_interpretation_id,evidence_path,evidence_metrics_json) VALUES(?,?,?,?,?,'ACTIVE','HIGH',?,NULL,?,?)",
        (
            _stage15t_interpretation_id(ikey), ikey,
            "Full-scale candidate multiplicity is approximately 4.90 technical assignments per candidate read, and Stage15R recovered all selected logical traces.",
            "Candidate multiplicity is a technical assignment count; biological weighting of secondary, overlap/alias and proximity/padding assignments belongs to post-Freeze sidecars.",
            "Do not interpret candidate count as independent biological repeat-event or molecule count.",
            STAGE15T_EFFECTIVE_AT,
            f"{project_root}/docs/contracts/RNA_TR_Scout_Candidate_assignment_reverse_traceability_contract_v0.1.1.md",
            json.dumps({"representative_reads": 57, "assignment_rows": 733, "unresolved": 0}, sort_keys=True),
        ),
    )

    update_contracts = {
        "architecture_consistency_audit_v0_1_0": (
            "Architecture consistency audit contract v0.1.0", "PASS_LOCAL_CORE_FREEZE_CHECKPOINTS",
            "POST250K, PRE-RC, post-promotion, PRE_BIOLOGY, Stage15R and final exact-original Stage15S audits are complete for local Core Freeze; future major changes retain the audit cadence.",
            f"{project_root}/docs/governance/RNA_TR_Scout_Core_Freeze_final_hygiene_audit_v0.1.0.md",
        ),
        "core_freeze_preservation_governance_v0_1_0": (
            "Core Freeze preservation and governance contract", "SATISFIED_LOCAL_CORE_FREEZE_V0_1_0",
            "Owner-approved Packet, canonical golden evidence, documentation layout, exact evidence retention and checksum manifest satisfy local Core Freeze scope; cleanup/public release remain open.",
            f"{project_root}/docs/core_freeze/v0.1.1/RNA_TR_Scout_Core_Freeze_Packet_v0.1.1.md",
        ),
        "positive_golden_evidence_v0_1_0": (
            "Positive Core golden evidence", "CANONICAL_FULL_EVIDENCE_SUITE_PASS",
            "Stage15Q canonical Tier0-Tier4 full-evidence suite passed with fixed real-read/100k exact parity, negative fixtures, restart/no-op/publication recovery and release-scale scope verification.",
            f"{project_root}/validation/golden/v0.1.0/rnatr_golden_regression_v014.py",
        ),
    }
    for key, (name, state, statement, evidence) in update_contracts.items():
        active = conn.execute("SELECT active_implementation_id FROM algorithm_contracts WHERE component_key=? AND status='ACTIVE'", (key,)).fetchall()
        if len(active) != 1:
            raise Stage15TError(f"SSOT contract baseline mismatch: {key}: {len(active)}")
        active_impl = active[0][0]
        conn.execute("UPDATE algorithm_contracts SET status='SUPERSEDED' WHERE component_key=? AND status='ACTIVE'", (key,))
        conn.execute(
            "INSERT INTO algorithm_contracts(contract_id,component_key,component_name,implementation_state,contract_statement,active_implementation_id,evidence_path,effective_at,status) VALUES(?,?,?,?,?,?,?,?, 'ACTIVE')",
            (_stage15t_contract_id(key), key, name, state, statement, active_impl, evidence, STAGE15T_EFFECTIVE_AT),
        )
    new_contracts = {
        "candidate_assignment_reverse_traceability_v0_1_0": (
            "Candidate-assignment reverse traceability", "PASS_WITH_SCOPE_BIOLOGY_DEFERRED",
            "Logical read_id-to-assignment-to-projection-to-caller-to-materialized-evidence trace is frozen; Stage-internal paths are replaceable under parity and guarantee gates.",
            f"{project_root}/docs/contracts/RNA_TR_Scout_Candidate_assignment_reverse_traceability_contract_v0.1.1.md",
        ),
        "future_extensibility_boundaries_v0_1_0": (
            "Future-extensibility boundaries", "PASS_NO_HARD_COUPLING",
            "All seven audited boundaries are open/current-profile-scoped/post-Freeze extensions; zero hard couplings require pre-Freeze Core remediation.",
            f"{project_root}/docs/contracts/RNA_TR_Scout_Future_extensibility_boundary_contract_v0.1.1.md",
        ),
    }
    for key, (name, state, statement, evidence) in new_contracts.items():
        if conn.execute("SELECT COUNT(*) FROM algorithm_contracts WHERE component_key=? AND status='ACTIVE'", (key,)).fetchone()[0] != 0:
            raise Stage15TError(f"SSOT new contract already active: {key}")
        conn.execute(
            "INSERT INTO algorithm_contracts(contract_id,component_key,component_name,implementation_state,contract_statement,active_implementation_id,evidence_path,effective_at,status) VALUES(?,?,?,?,?,NULL,?,?, 'ACTIVE')",
            (_stage15t_contract_id(key), key, name, state, statement, evidence, STAGE15T_EFFECTIVE_AT),
        )

    for key in ("CORE_FREEZE_GOVERNANCE_ARTIFACTS_NOT_YET_CREATED", "GENERIC_ACTIVE_PATH_GOLDEN_SUITE_NOT_YET_CANONICALLY_PACKAGED"):
        row = conn.execute("SELECT status FROM limitations WHERE limitation_key=?", (key,)).fetchone()
        if row is None or row[0] != "ACTIVE":
            raise Stage15TError(f"SSOT limitation baseline mismatch: {key}: {row}")
        conn.execute("UPDATE limitations SET status='SUPERSEDED',effective_at=? WHERE limitation_key=?", (STAGE15T_EFFECTIVE_AT, key))
    new_limit = "LOCAL_CORE_FREEZE_NOT_PUBLIC_GIT_RELEASE"
    if conn.execute("SELECT COUNT(*) FROM limitations WHERE limitation_key=?", (new_limit,)).fetchone()[0] != 0:
        raise Stage15TError("SSOT local/public limitation already exists")
    conn.execute(
        "INSERT INTO limitations(limitation_key,statement,severity,status,mitigation,evidence_path,effective_at) VALUES(?,?,?,'ACTIVE',?,?,?)",
        (
            new_limit,
            "The local checksummed Core contract is frozen for biology-sidecar work, but clean-install, cross-hardware, full Git commit/tag and thesis-citable public v0.5.0 release remain incomplete.",
            "HIGH",
            "Keep G25-G30 and Git/public-release binding open; never cite the local Freeze as the final public release.",
            f"{project_root}/docs/contracts/RNA_TR_Scout_Core_Technical_Completion_and_Freeze_contract_v0.1.2.md",
            STAGE15T_EFFECTIVE_AT,
        ),
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
    validator_path = resolve_current_validator(project_root)
    validator = str(validator_path)
    ensure_no_unexpanded_path_variables(validator, "validator_path")
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
        ("SIX_SAMPLE_REPLAY","Can the frozen P0/P1 pipeline be replayed across the six equalized fetal-brain datasets without mixing obsolete validators or implementations?","RESOLVED",0,
         "Completed in Stage 6AM v0.1.5; retain as closed historical gate.",str(project_root / "qc/11_six_sample_frozen_p01_replay/ENCSR307SHM_pilot100k_mm2splice_v1/rnatr_six_sample_frozen_p01_replay_v0.1.5/six_sample_frozen_p01_replay.qc.tsv")),
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
            (key,question,priority,("CLOSED" if priority=="RESOLVED" else "OPEN"),blocking,next_action,evidence,"2026-08-06T00:00:00+00:00"),
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

    # Stage 6AM v0.1.5 completed successfully on 2026-08-07.
    stage6am_root = project_root / "results/11_six_sample_frozen_p01_replay/ENCSR307SHM_pilot100k_mm2splice_v1/rnatr_six_sample_frozen_p01_replay_v0.1.5"
    stage6am_qc = project_root / "qc/11_six_sample_frozen_p01_replay/ENCSR307SHM_pilot100k_mm2splice_v1/rnatr_six_sample_frozen_p01_replay_v0.1.5/six_sample_frozen_p01_replay.qc.tsv"
    stage6am_summary = stage6am_root / "six_sample_frozen_p01_replay.summary.tsv"
    stage6am_provenance = stage6am_root / "run_stage_provenance.tsv"

    conn.execute(
        """
        UPDATE open_questions
        SET status='CLOSED',
            blocking=0,
            next_action='Completed: Stage 6AM v0.1.5 passed all six equalized fetal-brain datasets with SSOT-verified scripts and validator_v0.3.1.',
            evidence_path=?,
            effective_at='2026-08-07T03:03:38+00:00'
        WHERE question_key='SIX_SAMPLE_REPLAY'
        """,
        (str(stage6am_qc),),
    )

    conn.execute(
        """
        INSERT OR REPLACE INTO open_questions(
            question_key,question,priority,status,blocking,next_action,evidence_path,effective_at
        ) VALUES(?,?,?,?,?,?,?,?)
        """,
        (
            'PERFORMANCE_OPTIMIZATION_11F_11H',
            'How should the production caller reduce runtime, especially in 11f periodic baseline and 11h target-constrained refinement, and where can CPU parallelization, compiled code, or GPU batching help?',
            'HIGH','OPEN',0,
            'After the current technical-calibration and general-caller contract reach a stable checkpoint, profile 11f/11h first; separate Python overhead, DP compute, repeated work, and I/O, then benchmark CPU parallel, compiled, and GPU implementations against the CPU reference.',
            str(stage6am_provenance),
            '2026-08-07T03:03:38+00:00',
        ),
    )

    conn.execute(
        """
        INSERT OR REPLACE INTO limitations(
            limitation_key,statement,severity,status,mitigation,evidence_path,effective_at
        ) VALUES(?,?,?,?,?,?,?)
        """,
        (
            'CURRENT_RUNTIME_NOT_PRODUCTION_SCALE',
            'The current frozen P0/P1 implementation requires roughly 10-12 minutes per 100k-read sample in full runs; 11f and 11h account for about 80% of measured stage runtime.',
            'HIGH','ACTIVE',
            'Keep the current implementation as the correctness reference, then profile and optimize after the caller contract is stabilized; prioritize elimination of duplicate computation, CPU parallelization/compiled code, and GPU suitability for batched periodic DP.',
            str(stage6am_provenance),
            '2026-08-07T03:03:38+00:00',
        ),
    )

    add_decision(
        conn,
        key='six_sample_replay_complete',
        category='project_state',
        title='Six-sample frozen P0/P1 replay complete',
        statement='Stage 6AM v0.1.5 completed all six equalized 100k-read fetal-brain PromethION comparison datasets with the SSOT-verified frozen pipeline and validator_v0.3.1.',
        status='ACTIVE',
        confidence='HIGH',
        rationale='All six samples passed 11b, raw-read projection, motif-job preparation, baseline/refinement/finalization, exact-span calibration, calibrated evidence, and v0.3.3 span normalization. ENCSR327TOR 11j was reconciled as an expected-count metadata-only issue; no algorithm recomputation was required.',
        evidence_path=str(stage6am_qc),
        effective_at='2026-08-07T03:03:38+00:00',
    )

    add_interpretation(
        conn,
        key='coarse_pipeline_yield_target_within_six_sample_panel',
        fact='The original target pilot has 49,793 final P0/P1 evidence rows and 23,867 exact-span rows; the six equalized comparison datasets span 46,160-53,509 final rows and 22,114-25,886 exact-span rows.',
        interpretation='At coarse pipeline-yield level, the target pilot is within the technical-comparison panel range and does not show a gross global assignment or P0/P1 evidence-yield imbalance.',
        do_not='Do not interpret coarse row-count similarity as evidence that individual repeat loci, repeat lengths, motifs, or biology are normal; locus- and motif-level comparison is the next gate.',
        confidence='HIGH',
        evidence_path=str(stage6am_summary),
        evidence_metrics={
            'target_final_evidence_rows':49793,
            'panel_final_evidence_min':46160,
            'panel_final_evidence_max':53509,
            'target_exact_span_rows':23867,
            'panel_exact_span_min':22114,
            'panel_exact_span_max':25886,
        },
        status='ACTIVE',
        effective_at='2026-08-07T03:03:38+00:00',
    )

    # Stage 12A general caller bootstrap v0.1.0
    stage6am_qc = project_root / "qc/11_six_sample_frozen_p01_replay/ENCSR307SHM_pilot100k_mm2splice_v1/rnatr_six_sample_frozen_p01_replay_v0.1.5/six_sample_frozen_p01_replay.qc.tsv"
    stage6am_summary = project_root / "results/11_six_sample_frozen_p01_replay/ENCSR307SHM_pilot100k_mm2splice_v1/rnatr_six_sample_frozen_p01_replay_v0.1.5/six_sample_frozen_p01_replay.summary.tsv"
    stage6am_provenance = project_root / "results/11_six_sample_frozen_p01_replay/ENCSR307SHM_pilot100k_mm2splice_v1/rnatr_six_sample_frozen_p01_replay_v0.1.5/run_stage_provenance.tsv"
    general_contract = project_root / "docs/design/RNA_TR_Scout_general_repeat_caller_contract_v0.1.0.md"
    general_bench = project_root / "benchmarks/general_repeat_caller/v0.1.0"

    conn.execute("UPDATE open_questions SET status='CLOSED', blocking=0, next_action='Completed: six equalized 100k-read fetal-brain datasets replayed through the frozen P0/P1 pipeline; use as engineering validation only.', evidence_path=?, effective_at='2026-08-07T03:03:38+00:00' WHERE question_key='SIX_SAMPLE_REPLAY'", (str(stage6am_qc),))
    conn.execute("UPDATE open_questions SET status='CLOSED', blocking=0, next_action='Architecture contract frozen in v0.1.0; implementation remains a separate blocking task.', evidence_path=?, effective_at='2026-08-07T03:30:00+00:00' WHERE question_key='GENERAL_REPEAT_CALLER_CONTRACT'", (str(general_contract),))
    conn.execute("UPDATE open_questions SET status='OPEN', blocking=0, next_action='DEFER until the general caller is stable and fast enough to process many RNA long-read samples; do not estimate a precise locus/motif technical floor from the six-sample pilot.', evidence_path=?, effective_at='2026-08-07T03:30:00+00:00' WHERE question_key='RNA_TECHNICAL_FLOOR'", (str(stage6am_summary),))

    conn.execute('INSERT OR REPLACE INTO open_questions(question_key,question,priority,status,blocking,next_action,evidence_path,effective_at) VALUES(?,?,?,?,?,?,?,?)', ('GENERAL_REPEAT_CALLER_IMPLEMENTATION','Can the frozen general-caller contract be implemented for compound repeats, interruptions, RNA LPS, de-novo motif rescue, and censored molecules while preserving raw-read/locus-assignment semantics?','CRITICAL','OPEN',1,'Implement compound/interruption segmentation and LPS next, then materialize real P0/P1 raw-sequence regression fixtures and benchmark against the frozen pipeline.',str(general_contract),'2026-08-07T03:30:00+00:00'))
    conn.execute('INSERT OR REPLACE INTO open_questions(question_key,question,priority,status,blocking,next_action,evidence_path,effective_at) VALUES(?,?,?,?,?,?,?,?)', ('PERFORMANCE_OPTIMIZATION_11F_11H','How should production runtime be reduced, especially the computation corresponding to 11f/11h, and where can compiled CPU or GPU batching help?','HIGH','OPEN',0,'Profile after caller semantics stabilize; preserve the CPU/reference implementation as the correctness oracle.',str(stage6am_provenance),'2026-08-07T03:30:00+00:00'))
    conn.execute('INSERT OR REPLACE INTO limitations(limitation_key,statement,severity,status,mitigation,evidence_path,effective_at) VALUES(?,?,?,?,?,?,?)', ('SIX_SAMPLE_PANEL_ENGINEERING_ONLY','The six equalized fetal-brain 100k-read datasets are too small and biologically heterogeneous to define precise locus/motif/length/support-specific RNA technical distributions.','HIGH','ACTIVE','Use them only for engineering robustness and gross-artifact checks. Perform precise RNA background calibration only after the caller is stable/fast and many samples can be processed.',str(stage6am_summary),'2026-08-07T03:30:00+00:00'))
    conn.execute('INSERT OR REPLACE INTO limitations(limitation_key,statement,severity,status,mitigation,evidence_path,effective_at) VALUES(?,?,?,?,?,?,?)', ('CURRENT_RUNTIME_NOT_PRODUCTION_SCALE','The frozen P0/P1 implementation is too slow for routine full-depth cohorts; 11f and 11h are the primary observed hotspots.','HIGH','ACTIVE','Do not optimize prematurely. First stabilize general-caller semantics, then profile duplicate computation, Python overhead, compiled CPU, and GPU batching.',str(stage6am_provenance),'2026-08-07T03:30:00+00:00'))

    add_decision(conn,key='six_sample_scope_engineering_validation',category='development_scope',title='Six-sample panel is engineering validation only',statement='The six 100k-read fetal-brain comparison datasets close the replay/robustness gate but will not be used to estimate a precise RNA technical floor.',status='ACTIVE',confidence='HIGH',rationale='Six samples cannot separate technical variability, biological individual variability, expression/isoform differences, and sparse low-support loci with sufficient precision.',evidence_path=str(stage6am_summary),effective_at='2026-08-07T03:30:00+00:00')
    add_decision(conn,key='general_repeat_caller_contract_v0_1_0',category='algorithm_design',title='General repeat caller contract v0.1.0 frozen',statement='General repeat measurement will re-estimate raw-read repeat boundaries with an error-aware cyclic repeat model, treat catalog motifs as priors, preserve censored semantics, and explicitly support compound/interruption/LPS outputs.',status='ACTIVE',confidence='HIGH',rationale='This separates locus assignment from repeat measurement and provides a stable contract for implementation and benchmarking.',evidence_path=str(general_contract),effective_at='2026-08-07T03:30:00+00:00')
    add_interpretation(conn,key='stage6am_coarse_yield_sanity_only',fact='The target final P0/P1 evidence count and exact-span count fall within the six-sample replay ranges.',interpretation='No gross target-specific pipeline-yield failure is apparent at this coarse engineering level.',do_not='Do not interpret six-sample similarity as a locus-specific normal range, technical floor, pathogenicity result, or personal DNA genotype.',confidence='HIGH',evidence_path=str(stage6am_summary),evidence_metrics={'target_final_rows':49793,'panel_final_min':46160,'panel_final_max':53509,'target_exact_span':23867,'panel_exact_span_min':22114,'panel_exact_span_max':25886},status='ACTIVE',effective_at='2026-08-07T03:30:00+00:00')
    add_contract(conn,key='repeat_definition',name='Repeat definition and sizing',state='CONTRACT_FROZEN_REFERENCE_CORE_PROTOTYPE',statement='General-caller v0.1.0 contract freezes raw-read boundary re-estimation with cyclic error-aware motif alignment; catalog motifs are priors. The reference v0.1.0 single-motif core is implemented, while compound/interruption segmentation, LPS, censored interval inference, and production optimization remain pending.',implementation_id=None,evidence_path=str(general_contract))
    add_contract(conn,key='rna_lps',name='RNA longest pure segment',state='CONTRACT_FROZEN_NOT_IMPLEMENTED',statement='Final caller will keep exact-sequence LPS and error-aware inferred LPS distinct. Neither is complete in reference v0.1.0.',implementation_id=None,evidence_path=str(general_contract))
    # Stage 12B compound/interruption/LPS reference v0.2.0
    general_ref_v02 = project_root / "src/rnatr_scout/general_caller/rnatr_general_repeat_caller_ref_v0.2.0.py"
    general_ref_v02_note = project_root / "docs/design/RNA_TR_Scout_general_repeat_caller_reference_v0.2.0.md"
    stage12b_qc = project_root / "qc/12_general_repeat_caller_compound_lps/v0.2.0/general_repeat_caller_stage12b.qc.tsv"
    stage12b_real_qc = project_root / "benchmarks/general_repeat_caller/v0.2.0/real_p01_regression.qc.tsv"

    conn.execute("UPDATE open_questions SET status='OPEN', blocking=1, next_action='Reference v0.2.0 now implements conservative compound/interruption segmentation and distinct exact/inferred LPS, and materializes 60 real P0/P1 raw-sequence regression fixtures. Next implement censored interval/lower-bound semantics and stronger residual/de-novo motif rescue, then disease-locus/simulation benchmarks.', evidence_path=?, effective_at='2026-08-07T03:50:00+00:00' WHERE question_key='GENERAL_REPEAT_CALLER_IMPLEMENTATION'", (str(stage12b_qc),))
    conn.execute('INSERT OR REPLACE INTO limitations(limitation_key,statement,severity,status,mitigation,evidence_path,effective_at) VALUES(?,?,?,?,?,?,?)', ('REFERENCE_COMPOUND_SEGMENTATION_HEURISTIC','Reference v0.2.0 compound/interruption segmentation is a conservative engineering implementation, not yet a production statistical model.','MEDIUM','ACTIVE','Retain v0.1.0 single-motif semantics unless explicit multi-segment evidence is present; validate with broader simulation and disease-locus fixtures before production use.',str(general_ref_v02_note),'2026-08-07T03:50:00+00:00'))
    add_decision(conn,key='general_repeat_caller_reference_v0_2_0',category='algorithm_design',title='General repeat caller reference v0.2.0 implemented',statement='Reference v0.2.0 adds conservative compound-repeat and interruption segmentation plus distinct exact-sequence and error-aware inferred LPS while preserving v0.1.0 simple-periodic regression behavior by default.',status='ACTIVE',confidence='MEDIUM',rationale='A compound interpretation replaces the single-motif reference only when explicit strong multi-segment evidence is present; otherwise the v0.1.0-style result remains the oracle.',evidence_path=str(stage12b_qc),effective_at='2026-08-07T03:50:00+00:00')
    add_interpretation(conn,key='real_p01_regression_v0_2_0_is_engineering_fixture',fact='Sixty real P0/P1 exact-span seed rows were materialized back to raw read/window sequence and called by reference v0.2.0.',interpretation='This provides a real-data engineering regression set for tracking semantic changes while the general caller is developed.',do_not='Do not use the 60-row regression comparison as a biological accuracy estimate, technical population distribution, pathogenicity result, or acceptance threshold for repeat length differences.',confidence='HIGH',evidence_path=str(stage12b_real_qc),evidence_metrics={},status='ACTIVE',effective_at='2026-08-07T03:50:00+00:00')
    add_contract(conn,key='repeat_definition',name='Repeat definition and sizing',state='CONTRACT_FROZEN_REFERENCE_COMPOUND_LPS_PROTOTYPE',statement='General-caller contract remains frozen. Reference v0.2.0 preserves raw-read cyclic repeat measurement and adds conservative compound/interruption segmentation; censored interval inference and stronger residual de-novo rescue remain pending.',implementation_id=None,evidence_path=str(general_ref_v02_note))
    add_contract(conn,key='rna_lps',name='RNA longest pure segment',state='REFERENCE_DUAL_LPS_IMPLEMENTED_V0.2.0',statement='Reference v0.2.0 reports lps_exact_sequence_bp separately from lps_inferred_bp. These are engineering reference semantics and must remain distinct in later optimized implementations.',implementation_id=None,evidence_path=str(general_ref_v02_note))
    # Stage 12D boundary/censor/de-novo reference v0.3.0
    general_ref_v03 = project_root / "src/rnatr_scout/general_caller/rnatr_general_repeat_caller_ref_v0.3.0.py"
    general_ref_v03_note = project_root / "docs/design/RNA_TR_Scout_general_repeat_caller_reference_v0.3.0.md"
    stage12d_qc = project_root / "qc/12_general_repeat_caller_boundary_censor_denovo/v0.3.0/general_repeat_caller_stage12d.qc.tsv"
    stage12c_qc = project_root / "qc/12_general_repeat_caller_real_regression_audit/v0.2.0/general_repeat_caller_real_regression_audit.qc.tsv"

    conn.execute("UPDATE open_questions SET status='OPEN', blocking=1, next_action='Reference v0.3.0 now implements prior-anchored soft boundaries, explicit geometry-based censored lower-bound semantics, projection-window context limitation, conditional de-novo/residual rescue through period 50, and alternative-motif score reporting. Next run disease-locus and broad simulation benchmarks before production optimization.', evidence_path=?, effective_at='2026-08-07T05:00:00+00:00' WHERE question_key='GENERAL_REPEAT_CALLER_IMPLEMENTATION'", (str(stage12d_qc),))
    conn.execute('INSERT OR REPLACE INTO limitations(limitation_key,statement,severity,status,mitigation,evidence_path,effective_at) VALUES(?,?,?,?,?,?,?)', ('PROJECTION_WINDOW_IS_NOT_MOLECULE_CENSORING','A projection-window edge is an analysis-context limit and must not be interpreted as biological/read censoring.','HIGH','ACTIVE','Use explicit evidence geometry for LEFT/RIGHT/BOTH censoring; report projection-window edge truncation separately as CONTEXT_LIMITED_LOWER_BOUND. Materialize full raw reads for later molecule-level validation when needed.',str(general_ref_v03_note),'2026-08-07T05:00:00+00:00'))
    add_decision(conn,key='general_repeat_caller_reference_v0_3_0',category='algorithm_design',title='General repeat caller reference v0.3.0 implemented',statement='Reference v0.3.0 anchors motif selection to the projected locus core before soft tract extension, separates explicit censoring from projection-window context limits, and uses conditional anchored de-novo rescue through period 50.',status='ACTIVE',confidence='MEDIUM',rationale='The 60-row real software-regression audit showed tract-boundary extension as the dominant discrepancy driver (21/60), motif-selection/de-novo differences in 11/60, and window-edge/context effects in 5/60. The contract change addresses those engineering failure modes without treating the frozen caller as biological truth.',evidence_path=str(stage12d_qc),effective_at='2026-08-07T05:00:00+00:00')
    add_interpretation(conn,key='real_p01_regression_driver_audit_stage12c',fact='In the 60-row real P0/P1 software-regression audit, likely drivers were tract-boundary extension 21, small difference 19, motif selection/de-novo 11, window edge/context 5, internal sizing semantics 3, and compound/interruption 1.',interpretation='The next reference caller should constrain motif/tract selection to remain locus-anchored and should distinguish artificial sequence-window limits from explicit molecule censoring.',do_not='Do not interpret these 60 rows as an accuracy estimate, biological distribution, normal range, or population technical floor.',confidence='HIGH',evidence_path=str(stage12c_qc),evidence_metrics={'tract_boundary_extension':21,'small_difference':19,'motif_selection_or_denovo':11,'window_edge_or_context':5,'internal_sizing_semantics':3,'compound_or_interruption':1},status='ACTIVE',effective_at='2026-08-07T05:00:00+00:00')
    add_contract(conn,key='repeat_definition',name='Repeat definition and sizing',state='REFERENCE_V0.3.0_PRE_BENCHMARK',statement='Reference v0.3.0 preserves raw-read cyclic measurement, compound/interruption segmentation and dual LPS, and adds prior-anchored soft boundary inference plus alternative-motif evidence. Disease/simulation benchmarking remains required before production freeze.',implementation_id=None,evidence_path=str(general_ref_v03_note))
    add_contract(conn,key='censoring_semantics',name='RNA repeat censoring and interval semantics',state='REFERENCE_IMPLEMENTED_V0.3.0',statement='SPAN may yield exact length when sequence context bounds the tract. LEFT/RIGHT/BOTH-censored molecules yield observed repeat lower bounds only with no invented finite upper bound. Projection-window edges are context limits, not biological censoring.',implementation_id=None,evidence_path=str(general_ref_v03_note))
    add_contract(conn,key='motif_hypothesis',name='Motif hypothesis and rescue semantics',state='REFERENCE_IMPLEMENTED_V0.3.0',statement='Catalog motif is the primary prior. De-novo/residual search through period 50 is conditionally activated only when catalog support in the projected core is inadequate, with primitive/rotation/reverse-complement collapse and alternative score reporting.',implementation_id=None,evidence_path=str(general_ref_v03_note))
    # Stage 12G freeze general repeat caller v0.4.0
    general_ref_v04 = project_root / "src/rnatr_scout/general_caller/rnatr_general_repeat_caller_ref_v0.4.0.py"
    general_ref_v04_note = project_root / "docs/design/RNA_TR_Scout_general_repeat_caller_reference_v0.4.0.md"
    general_ref_v04_freeze = project_root / "metadata/general_caller/general_repeat_caller_freeze_v0.4.0.tsv"
    stage12e_qc = project_root / "qc/12_general_repeat_caller_disease_sim/v0.4.0_stage12e_wrapper_v0.4.1/general_repeat_caller_stage12e.qc.tsv"
    stage12f_qc = project_root / "qc/12_general_repeat_caller_v03_v04_paired_regression_audit/v0.1.0/v03_v04_paired_real_regression.qc.tsv"

    conn.execute("UPDATE open_questions SET status='CLOSED', blocking=0, next_action='General repeat caller reference v0.4.0 frozen after backward regression, disease-inspired/broad simulation benchmark, short-prior expansion stress test, and paired v0.3/v0.4 real-read software regression.', evidence_path=?, effective_at='2026-08-07T07:15:00+00:00' WHERE question_key IN ('GENERAL_REPEAT_CALLER_CONTRACT','GENERAL_REPEAT_CALLER_IMPLEMENTATION')", (str(general_ref_v04_freeze),))
    conn.execute("UPDATE open_questions SET status='OPEN', blocking=1, next_action='Profile the current production path, especially 11f periodic baseline and 11h refinement, then design integration of frozen general caller v0.4.0. Measure Python/DP/I-O shares before choosing CPU compiled or GPU acceleration.', evidence_path=?, effective_at='2026-08-07T07:15:00+00:00' WHERE question_key='PERFORMANCE_OPTIMIZATION_11F_11H'", (str(general_ref_v04_freeze),))
    conn.execute('INSERT OR REPLACE INTO limitations(limitation_key,statement,severity,status,mitigation,evidence_path,effective_at) VALUES(?,?,?,?,?,?,?)', ('V04_LONG_EXTENSION_CONFIDENCE','Reference v0.4.0 intentionally permits locus-anchored tract extension beyond a short projected prior. In the 60-row software regression, 10 calls were >20 bp longer than v0.3; five newly reached projection-window context edges. These differences are not evidence of biological error because the frozen P0/P1 caller is not truth.','MEDIUM','ACTIVE','Keep v0.4.0 expansion recovery. Treat projection-window edge calls as context-limited lower bounds, retain purity and boundary/context metadata, and validate selected long-extension cases on full raw reads or orthogonal truth in later benchmark work.',str(stage12f_qc),'2026-08-07T07:15:00+00:00'))
    add_decision(conn,key='general_repeat_caller_reference_v0_4_0_frozen',category='algorithm_design',title='General repeat caller v0.4.0 frozen',statement='Freeze rnatr_general_repeat_caller_ref_v0.4.0 as the measurement reference implementation. Preserve locus-anchored geometric expansion for recovery of repeats longer than the projected prior; do not force agreement to the legacy P0/P1 caller.',status='ACTIVE',confidence='HIGH',rationale='Backward regressions passed. The 122-case benchmark completed 100%, disease-inspired exact-boundary motif accuracy was 100%, short-prior expansion recovery median was ~100.3% with P10 100%, censoring invariants passed, and de-novo/compound/interruption classification metrics were 100%. Paired real-read comparison showed 50/60 v0.3/v0.4 calls within 5 bp and zero motif changes; projection-window edge extensions are represented as context-limited lower bounds.',evidence_path=str(general_ref_v04_freeze),effective_at='2026-08-07T07:15:00+00:00')
    add_interpretation(conn,key='v04_boundary_tradeoff_stage12f',fact='In the paired 60-row v0.3/v0.4 software regression, 50/60 calls were within 5 bp, 10 were >20 bp longer in v0.4, nine had >25 bp additional extension, five newly reached projection-window context edges, and zero changed motif identity.',interpretation='The observed v0.4 extension tradeoff does not justify truncating the caller back toward the legacy implementation. Simulation truth demonstrates that larger search windows are required to recover repeats substantially longer than the projected prior, while context-edge calls already have lower-bound semantics.',do_not='Do not treat legacy P0/P1 repeat length as ground truth, do not interpret the 60-row set as a biological normal range, and do not infer pathogenicity from the simulated disease-inspired motifs.',confidence='HIGH',evidence_path=str(stage12f_qc),evidence_metrics={'paired_rows':60,'within_5bp':50,'v04_gt20bp_longer':10,'additional_extension_gt25bp':9,'new_context_limited':5,'motif_changed':0},status='ACTIVE',effective_at='2026-08-07T07:15:00+00:00')
    add_contract(conn,key='repeat_definition',name='Repeat definition and sizing',state='FROZEN_REFERENCE_V0.4.0',statement='Frozen reference v0.4.0 uses locus-core motif anchoring followed by geometric tract expansion, raw-read cyclic error-aware sizing, compound/interruption segmentation, and dual LPS semantics. Expansion beyond the projected prior is permitted when the locus remains overlapped; projection-window edges yield context-limited lower bounds.',implementation_id=None,evidence_path=str(general_ref_v04_note))
    add_contract(conn,key='general_caller_freeze',name='General repeat caller freeze',state='FROZEN_V0.4.0',statement='General caller measurement semantics are frozen for production-integration and performance work. Subsequent optimization must preserve v0.4.0 call semantics and pass frozen regression/benchmark gates.',implementation_id=None,evidence_path=str(general_ref_v04_freeze))
    # Stage 13 performance phase checkpoint v0.1.0
    performance_stage13a_log = project_root / "logs/13a_performance_discovery_v0.1.0.log"
    general_ref_v04_freeze = project_root / "metadata/general_caller/general_repeat_caller_freeze_v0.4.0.tsv"

    conn.execute(
        """
        UPDATE open_questions
        SET priority='CRITICAL',
            status='OPEN',
            blocking=1,
            next_action='Performance phase started after general caller v0.4.0 freeze. Complete read-only Stage 13A discovery, then profile 11f/11h dynamically on a small frozen fixture; separate Python overhead, DP compute, repeated work, and I/O before deciding CPU compiled versus GPU acceleration.',
            evidence_path=?,
            effective_at='2026-08-07T07:19:00+00:00'
        WHERE question_key='PERFORMANCE_OPTIMIZATION_11F_11H'
        """,
        (str(performance_stage13a_log),),
    )

    add_decision(
        conn,
        key='performance_profiling_phase_started',
        category='project_state',
        title='Performance profiling phase started',
        statement='General repeat caller v0.4.0 is frozen. RNA-TR-Scout has entered the performance/prod-integration phase; Stage 13A is read-only discovery and its measurements are not accepted until its QC reaches PASS.',
        status='ACTIVE',
        confidence='HIGH',
        rationale='The caller measurement semantics were frozen in Stage 12G. Runtime is now a production-blocking engineering requirement, with 11f periodic baseline and 11h refinement the leading bottleneck candidates from prior six-sample execution history. Exact optimization choices must follow profiling rather than assumption.',
        evidence_path=str(general_ref_v04_freeze),
        effective_at='2026-08-07T07:19:00+00:00',
    )

    add_interpretation(
        conn,
        key='performance_stage13a_in_progress_checkpoint',
        fact='Stage 13A performance discovery has been launched after the v0.4.0 general-caller freeze.',
        interpretation='This checkpoint records project state only. Stage 13A is intended to collect existing runtime provenance, implementation structure, and CPU/GPU environment without replaying the heavy 100k-read pipeline.',
        do_not='Do not record Stage 13A runtime shares, GPU suitability, or optimization recommendations as final until Stage 13A QC is PASS and its outputs have been reviewed.',
        confidence='HIGH',
        evidence_path=str(performance_stage13a_log),
        evidence_metrics={'stage13a_status':'IN_PROGRESS_OR_PENDING_REVIEW','general_caller':'FROZEN_V0.4.0'},
        status='ACTIVE',
        effective_at='2026-08-07T07:19:00+00:00',
    )

    # Stage 13A finalized performance discovery v0.1.0
    stage13a_qc = project_root / "qc/13_performance_discovery/v0.1.0/performance_discovery.qc.tsv"
    stage13a_hotfix_qc = project_root / "qc/13_performance_discovery/v0.1.1/performance_discovery_hotfix.qc.tsv"
    stage13a_runtime = project_root / "results/13_performance_discovery/v0.1.0/stage_runtime_summary.tsv"
    stage13a_sources = project_root / "results/13_performance_discovery/v0.1.1/exact_stage_source_resolution.tsv"
    stage13a_gpu = project_root / "results/13_performance_discovery/v0.1.1/gpu_probe.txt"

    conn.execute(
        """
        UPDATE open_questions
        SET priority='CRITICAL',
            status='OPEN',
            blocking=1,
            next_action='Stage 13A finalized: 11f and 11h account for 80.1387% of profiled frozen-stage runtime. Exact active sources are 11f_run_high_confidence_simple_periodic_baseline.sh and 11h_target_constrained_periodic_refinement.sh. RTX 3090 24GB (compute capability 8.6) is available; CUDA toolkit 11.5 is installed, but Python GPU/Numba libraries are not yet installed. Next: dynamic profile the exact 11f/11h compute kernels on a small frozen fixture before choosing CPU compiled versus GPU acceleration.',
            evidence_path=?,
            effective_at='2026-08-07T07:31:00+00:00'
        WHERE question_key='PERFORMANCE_OPTIMIZATION_11F_11H'
        """,
        (str(stage13a_qc),),
    )

    conn.execute(
        'INSERT OR REPLACE INTO limitations(limitation_key,statement,severity,status,mitigation,evidence_path,effective_at) VALUES(?,?,?,?,?,?,?)',
        (
            'PERFORMANCE_11F_11H_DOMINATE_RUNTIME',
            'Across five complete 100k-read frozen replays, 11f averaged 308.6 s (48.6444% of profiled stage time) and 11h averaged 199.8 s (31.4943%), for a combined 80.1387%.',
            'CRITICAL','ACTIVE',
            'Profile the exact 11f/11h compute kernels on a small frozen fixture. Preserve frozen v0.4.0 semantics while testing removal of duplicate work, CPU parallelization, compiled kernels, and GPU batching.',
            str(stage13a_runtime),
            '2026-08-07T07:31:00+00:00'
        ),
    )

    add_decision(
        conn,
        key='stage13a_performance_discovery_finalized',
        category='performance',
        title='Stage 13A performance discovery finalized',
        statement='Performance optimization will focus first on exact stages 11f and 11h, which together account for 80.1387% of profiled frozen-stage runtime. GPU hardware is available but GPU acceleration is not yet selected; the decision is deferred until dynamic kernel profiling.',
        status='ACTIVE',
        confidence='HIGH',
        rationale='Runtime provenance from five complete 100k-read replays identifies 11f and 11h as the dominant stages. SHA-based source resolution identified the exact scripts. Hardware probing confirmed an RTX 3090 with 24GB VRAM and compute capability 8.6, while the current rnatr-v03 environment lacks numba, torch, cupy, and jax.',
        evidence_path=str(stage13a_hotfix_qc),
        effective_at='2026-08-07T07:31:00+00:00',
    )

    add_interpretation(
        conn,
        key='gpu_available_not_yet_selected',
        fact='The workstation exposes a functional NVIDIA GeForce RTX 3090 with 24576 MiB VRAM, compute capability 8.6, driver 595.84, and CUDA toolkit 11.5; nvidia-smi exits successfully.',
        interpretation='GPU acceleration is technically feasible on this machine, but suitability for RNA-TR-Scout remains unresolved until 11f/11h dynamic profiling identifies whether their dominant kernels are sufficiently compute-heavy and batchable.',
        do_not='Do not install a GPU software stack or rewrite the caller for CUDA merely because a GPU is present. First quantify Python overhead, I/O, duplicate computation, and the DP/scoring kernel share.',
        confidence='HIGH',
        evidence_path=str(stage13a_gpu),
        evidence_metrics={
            'gpu':'NVIDIA GeForce RTX 3090',
            'vram_mib':24576,
            'compute_capability':'8.6',
            'driver':'595.84',
            'cuda_toolkit':'11.5',
            'numba':'NOT_AVAILABLE',
            'torch':'NOT_AVAILABLE',
            'cupy':'NOT_AVAILABLE',
            'jax':'NOT_AVAILABLE'
        },
        status='ACTIVE',
        effective_at='2026-08-07T07:31:00+00:00',
    )
    # Stage 13F runtime-discovered active 11f/11h promotion v0.1.1
    _cur = conn.execute('UPDATE "implementations" SET "script_path"=?, "script_sha256"=? WHERE "implementation_id"=?', (str(project_root / 'scripts/11f_run_high_confidence_simple_periodic_baseline.parallel_v0.1.0.sh'), '08d70a104ec384914a9e7e72cc18b67481b94805940fb67900d19c8fde397684', 'impl_92f0f4fe33897d713ac97b6f'));
    assert _cur.rowcount == 1, 'Stage 13F 11f active row update failed'
    _cur = conn.execute('UPDATE "implementations" SET "script_path"=?, "script_sha256"=? WHERE "implementation_id"=?', (str(project_root / 'scripts/11h_target_constrained_periodic_refinement.parallel_v0.1.0.sh'), 'bad281accad9937429f450e538c657ae04e1090eba05157a0c911b375b82c7e0', 'impl_d6c366aaa77a3ed65a8087cb'));
    assert _cur.rowcount == 1, 'Stage 13F 11h active row update failed'
    stage13e_qc = project_root / 'qc/13_parallel_active_promotion/v0.1.0/parallel_active_promotion.qc.tsv'
    conn.execute("UPDATE open_questions SET status='CLOSED', blocking=0, next_action=?, evidence_path=?, effective_at=? WHERE question_key='PERFORMANCE_OPTIMIZATION_11F_11H'", ('Resolved for frozen P0/P1: exact 16-process 11f/11h are active after full regression parity. Revisit GPU after general-caller production integration if needed.', str(stage13e_qc), '2026-08-07T08:15:00+00:00'))
    conn.execute("INSERT OR REPLACE INTO open_questions(question_key,question,priority,status,blocking,next_action,evidence_path,effective_at) VALUES(?,?,?,?,?,?,?,?)", ('GENERAL_CALLER_PRODUCTION_INTEGRATION','How should frozen general repeat caller v0.4.0 replace or consolidate the legacy periodic measurement path in production while preserving assignment, geometry, multi-event behavior, and auditability?','CRITICAL','OPEN',1,'Collect exact integration contracts and build an isolated 100k integrated candidate. Do not run the full 5.31M-read sample until integrated 100k regression and performance QC pass.',str(stage13e_qc),'2026-08-07T08:15:00+00:00'))
    add_decision(conn,key='parallel_11f_11h_active_v0_1_0',category='performance',title='Parallel 11f/11h active',statement='Activate versioned 16-process multiprocessing implementations for frozen P0/P1 stages 11f and 11h; algorithms and output semantics are unchanged.',status='ACTIVE',confidence='HIGH',rationale='Stage 13C matched all 49,793 jobs in both kernels; Stage 13D and 13E each matched 10/10 major artifacts while reducing the stage pair from about 508 s historically to about 75 s.',evidence_path=str(stage13e_qc),effective_at='2026-08-07T08:15:00+00:00')
    add_interpretation(conn,key='cpu_parallel_active_gpu_deferred',fact='The productionized 16-process 11f/11h pair preserves all audited legacy outputs exactly and runs in about 75 seconds on the 100k pilot versus a historical mean near 508 seconds.',interpretation='CPU multiprocessing is the active first-line performance solution. RTX 3090 acceleration remains available but is deferred until general caller v0.4.0 integration reveals the new bottleneck.',do_not='Do not delete serial reference implementations or treat GPU deferral as permanent.',confidence='HIGH',evidence_path=str(stage13e_qc),evidence_metrics={'workers':16,'matched_artifacts':10,'legacy_pair_seconds':508.4,'parallel_pair_seconds_approx':75.0,'gpu_used':False},status='ACTIVE',effective_at='2026-08-07T08:15:00+00:00')

    # Stage 14H deterministic general caller v0.4.1 promotion and validation contract
    general_v041_manifest = project_root / 'metadata/general_caller/general_repeat_caller_v0.4.1.validation_manifest.tsv'
    general_v041_qc = project_root / 'qc/14_general_caller_v041_promotion/v0.1.0/general_caller_v041_promotion.qc.tsv'
    validation_contract = project_root / 'validation/VALIDATION_CONTRACT_v0.1.0.md'
    validation_gates = project_root / 'validation/release_gates_v0.1.0.tsv'

    conn.execute("UPDATE open_questions SET next_action=?, evidence_path=?, effective_at=? WHERE question_key='GENERAL_CALLER_PRODUCTION_INTEGRATION'", ('Deterministic general caller v0.4.1 is the frozen measurement reference and native implementation is validated. Next map native v0.4.1 calls into final evidence schema and pass isolated 100k end-to-end before any full 5.31M run.', str(general_v041_qc), '2026-08-07T12:45:00+00:00'))

    add_decision(conn,key='general_repeat_caller_v0_4_1_frozen_reference',category='algorithm_design',title='Deterministic general caller v0.4.1 frozen',statement='Promote deterministic Python general caller v0.4.1 as the frozen measurement reference; validated native implementation must remain exactly equivalent for production integration.',status='ACTIVE',confidence='HIGH',rationale='v0.4.0 hash-order nondeterminism was isolated to pre-existing exact-tie orientation behavior. v0.4.1 fixes only this tie rule, passes all truth/regression suites, and Python/native outputs are identical for all 388,571 rows of the 100k engineering dataset.',evidence_path=str(general_v041_manifest),effective_at='2026-08-07T12:45:00+00:00')

    add_interpretation(conn,key='native_v041_performance_validated_caller_only',fact='Native deterministic v0.4.1 runs the 100k general-caller workload in about 21.35 seconds versus about 555 seconds for deterministic Python, about 26x faster. Linear 5.31M caller-only projection is about 18.9 minutes.',interpretation='The measurement engine now meets the 30-minute caller-only target without GPU. Whole BAM-input pipeline performance remains a blocking release gate.',do_not='Do not claim the complete RNA-TR-Scout pipeline runs in 18.9 minutes; this is caller-only.',confidence='HIGH',evidence_path=str(general_v041_qc),evidence_metrics={'native_speedup':25.9993073603451,'projected_full_caller_minutes':18.901733196639434,'gpu_used':False},status='ACTIVE',effective_at='2026-08-07T12:45:00+00:00')

    add_contract(conn,key='general_caller_deterministic_tie_break_v041',name='General caller deterministic orientation tie break',state='FROZEN_V0.4.1',statement='Existing score/ranking semantics are unchanged. On an otherwise exact orientation tie, evaluate input/canonical motif first, reverse complement second, and retain first on equality. Hash/set iteration order is never semantic input.',implementation_id=None,evidence_path=str(project_root / 'validation/TIE_BREAKING_CONTRACT_general_caller_v0.4.1.md'))

    add_contract(conn,key='validation_truth_hierarchy',name='Validation truth hierarchy',state='ACTIVE_V0.1.0',statement='Correctness evidence is ordered: Tier 1 constructed truth > Tier 2 experimental/orthogonal truth > Tier 3 replicate/cross-platform empirical agreement > Tier 4 software regression. Lower tiers cannot override higher-tier truth.',implementation_id=None,evidence_path=str(validation_contract))

    conn.execute('INSERT OR REPLACE INTO limitations(limitation_key,statement,severity,status,mitigation,evidence_path,effective_at) VALUES(?,?,?,?,?,?,?)', ('BIOLOGICAL_TRUTH_VALIDATION_INCOMPLETE','Algorithmic and implementation validation is strong, but truth-bearing biological validation on experimental/same-individual orthogonal repeat measurements remains incomplete.','HIGH','ACTIVE','After 100k production integration and performance gates stabilize, validate on disease-repeat / synthetic-RNA / orthogonal DNA truth datasets before strong biological claims.',str(validation_gates),'2026-08-07T12:45:00+00:00'))

    # Stage 14L2 schema v0.4.2 failure/materialization semantics promotion
    stage14l2_qc = project_root / 'qc/14_schema_v042_promotion/ENCSR307SHM_pilot100k_mm2splice_v1/v0.1.2/schema_v042_promotion.qc.tsv'
    stage14l2_manifest = project_root / 'metadata/evidence_schema/evidence_schema_v0.4.2.promotion_manifest.v0.1.2.tsv'
    stage14l2_contract = project_root / 'results/14_schema_v042_promotion/ENCSR307SHM_pilot100k_mm2splice_v1/v0.1.2/FAILURE_CODE_QC_FLAGS_MATERIALIZATION_CONTRACT_v0.1.0.md'

    conn.execute("UPDATE open_questions SET next_action=?, evidence_path=?, effective_at=? WHERE question_key='GENERAL_CALLER_PRODUCTION_INTEGRATION'", ('Schema v0.4.2 and materializer v0.1.2 are validated from frozen motif/projection jobs through a 100k package. Next build an isolated mapping-complete BAM-input to final-package run before active switch or 5.31M execution.', str(stage14l2_qc), '2026-08-08T02:00:00+00:00'))

    add_decision(conn,key='evidence_schema_v0_4_2_validated_candidate_v012',category='schema_design',title='Evidence schema v0.4.2 validated production candidate',statement='Promote schema v0.4.2 and materializer v0.1.2 as validated production candidates for prepared-job-to-package processing. Keep active BAM-to-final switch gated on an isolated 100k BAM-input test.',status='ACTIVE',confidence='HIGH',rationale='Stage14K2 passed all package validators. Stage14L2 resolved the 18 CALLED_NOT_RETAINED rows by explicitly separating singular failure_code, non-exclusive qc_flags, and materialization_status semantics without rewriting the validated package.',evidence_path=str(stage14l2_manifest),effective_at='2026-08-08T02:00:00+00:00')

    add_interpretation(conn,key='failure_code_qc_flags_materialization_are_orthogonal',fact='All 18 CALLED_NOT_RETAINED attempts in the frozen 100k set are caller LOW_CONFIDENCE and have prior_overlap_bp <= 0. Their primary failure_code is GENERAL_CALLER_LOW_CONFIDENCE, while qc_flags retain both CALLER_LOW_CONFIDENCE and PRIOR_OVERLAP_NONPOSITIVE and materialization_status records non-eventization.',interpretation='LOW_CONFIDENCE alone is not the eventization blocker: 6,307 CALLED attempts are LOW_CONFIDENCE and 6,289 are still eventized. The nonpositive locus-prior overlap is the eventization guard and remains explicitly encoded.',do_not='Do not force failure_code to duplicate materialization_status or discard secondary QC conditions.',confidence='HIGH',evidence_path=str(stage14l2_qc),evidence_metrics={'low_confidence_called':6307,'low_confidence_eventized':6289,'called_not_retained':18},status='ACTIVE',effective_at='2026-08-08T02:00:00+00:00')

    add_contract(conn,key='failure_code_qc_flags_materialization_v010',name='Failure code, QC flags, and materialization status',state='FROZEN_V0.1.0',statement='failure_code is a singular primary evidence failure classification; qc_flags are non-exclusive simultaneous conditions; materialization_status records whether a caller attempt is normalized as a locus-associated repeat_event. These fields are not required to contain the same reason.',implementation_id=None,evidence_path=str(stage14l2_contract))

    add_contract(conn,key='evidence_schema_v042',name='Evidence schema v0.4.2',state='FROZEN_VALIDATED_PRODUCTION_CANDIDATE',statement='Schema v0.4.2 plus materializer v0.1.2 is validated for frozen prepared-job-to-package 100k processing. Active BAM-to-final use remains blocked until the isolated BAM-input gate passes.',implementation_id=None,evidence_path=str(stage14l2_manifest))

    # Stage 14M handover checkpoint after Stage14L2
    stage14m_summary = project_root / 'docs/handovers/20260808_stage14l2_to_stage15a.md'
    stage14m_checkpoint = project_root / 'metadata/ssot/checkpoints/20260808_stage14l2_to_stage15a/stage14l2_handover_checkpoint.tsv'
    stage14l2_qc = project_root / 'qc/14_schema_v042_promotion/ENCSR307SHM_pilot100k_mm2splice_v1/v0.1.2/schema_v042_promotion.qc.tsv'

    conn.execute("UPDATE open_questions SET next_action=?, evidence_path=?, effective_at=? WHERE question_key='GENERAL_CALLER_PRODUCTION_INTEGRATION'", ('Stage15A: design and run an isolated mapping-complete 100k BAM-to-final schema v0.4.2 integration using active 11b/11d3/11e contracts, deterministic native caller v0.4.1, materializer v0.1.2, full package validation, restartability, and runtime audit. Do not switch the active pipeline or run full 5.31M until this gate passes.', str(stage14m_summary), '2026-08-08T02:30:00+00:00'))

    add_decision(conn,key='stage14l2_handover_checkpoint_v010',category='project_state',title='Stage14L2 handover checkpoint',statement='Checkpoint the project after Stage14L2. Prepared motif/projection jobs through deterministic native caller v0.4.1 and schema v0.4.2 validated package are PASS for the 100k target pilot; the active production pipeline remains the legacy P0/P1 path pending an isolated BAM-to-final gate.',status='ACTIVE',confidence='HIGH',rationale='Stage14L2, schema promotion, failure/QC/materialization contract, package validators, and SSOT rebuild all passed. The next unresolved production boundary is mapping-complete BAM input through final package.',evidence_path=str(stage14m_checkpoint),effective_at='2026-08-08T02:30:00+00:00')

    add_interpretation(conn,key='stage14l2_validation_boundary_v010',fact='The validated Stage14L2 boundary begins from frozen motif/projection jobs, not from BAM. Schema v0.4.2 and materializer v0.1.2 are validated candidates, while active pipeline stages remain MAP_SPLICE plus legacy 11b through 11k3.',interpretation='The next release-critical test is an isolated 100k BAM-to-final run. Stage14L2 must not be described as whole-pipeline or full-scale validation.',do_not='Do not switch active implementations, delete legacy references, or run the full 5.31M sample before the isolated BAM-input gate passes.',confidence='HIGH',evidence_path=str(stage14m_summary),evidence_metrics={'caller_attempt_rows':388571,'repeat_event_rows':160297,'bam_to_final_validated':False,'active_pipeline_switched':False},status='ACTIVE',effective_at='2026-08-08T02:30:00+00:00')

    add_interpretation(conn,key='stage14l2_performance_boundary_v010',fact='At 100k scale the native caller takes roughly 18-21 seconds, materialization roughly 68 seconds, and package validation roughly 16 seconds. Materialization is now the dominant downstream bottleneck.',interpretation='Stage15A should combine BAM-to-final integration with streaming and I/O redesign; the 5M BAM-input target remains 30 minutes with a 60-minute hard ceiling.',do_not='Do not infer whole-pipeline runtime from the caller-only 18.9-minute full-sample projection.',confidence='HIGH',evidence_path=str(stage14m_summary),evidence_metrics={'native_caller_seconds_100k':21.35,'materializer_seconds_100k':68.13,'package_validator_seconds_100k':16.17,'target_minutes_5m':30,'hard_ceiling_minutes_5m':60},status='ACTIVE',effective_at='2026-08-08T02:30:00+00:00')

    add_contract(conn,key='stage15a_bam_to_final_gate_v010',name='Stage15A BAM-to-final 100k gate',state='OPEN_BLOCKING',statement='Before active pipeline promotion or full 5.31M execution, run the mapping-complete target 100k BAM through target assignment, raw-read projection, motif jobs, deterministic native caller v0.4.1, materializer v0.1.2, schema v0.4.2 validators, manifests, restartability, and runtime audit in an isolated output root.',implementation_id=None,evidence_path=str(stage14m_summary))

    # Stage 15A reference SSOT registration v0.1.0
    stage15a_ref_effective_at = "2026-08-08T06:12:17+00:00"
    stage15a_ref_run_id = "ENCSR307SHM_pilot100k_mm2splice_v1"
    stage15a_ref_stage_key = "15A_BAM_TO_FINAL_REFERENCE"
    stage15a_ref_impl_id = "impl_stage15a_reference_v0_1_3"
    stage15a_ref_qc = project_root / "qc/15_stage15a_bam_to_final/ENCSR307SHM_pilot100k_mm2splice_v1/v0.1.3/stage15a_reference_100k.qc.tsv"
    stage15a_ref_timing = project_root / "qc/15_stage15a_bam_to_final/ENCSR307SHM_pilot100k_mm2splice_v1/v0.1.3/stage15a_reference_timing.tsv"
    stage15a_ref_package_manifest = project_root / "results/15_stage15a_bam_to_final/ENCSR307SHM_pilot100k_mm2splice_v1/v0.1.3/package_reference/package_manifest.tsv"
    stage15a_ref_runner = project_root / "scripts/rnatr_stage15a_resume_reference_100k_v0.1.3.py"
    stage15a_ref_validator_tsv = project_root / "config/evidence_schema/v0.4.2/rnatr_v042_validate_tsv.py"
    stage15a_ref_validator_package = project_root / "config/evidence_schema/v0.4.2/rnatr_v042_validate_package.py"

    stage15a_ref_required_hashes = {
        stage15a_ref_qc: "c5f379afaa5d4f9b7d4eadfac833d430801918713506c5821bd8a404cf57059a",
        stage15a_ref_timing: "95445da53f04cf8f5b96f27f3b4e126d696f64761c096968ddccef722530e629",
        stage15a_ref_package_manifest: "1c85d06e1b2b06da7092956ab47ebe32b401a69701ed560ca8ba683f6b263d42",
        stage15a_ref_runner: "cdd2a9746467d2262bab86515bbb676aae8358daa147439d0249d10dfe14236b",
        stage15a_ref_validator_tsv: "10c9d4bbb5c9dac314d400768eb27206173933759c877225bd0ca2c692d8aba9",
        stage15a_ref_validator_package: "45c3995550f57a65b3fec4aab7471d57b7000e19471d4c5cf7f3ae055426984e",
    }
    for stage15a_ref_path, stage15a_ref_expected_sha in stage15a_ref_required_hashes.items():
        if not stage15a_ref_path.is_file():
            raise SSOTError(f"Stage 15A reference artifact missing: {stage15a_ref_path}")
        stage15a_ref_observed_sha = sha256_file(stage15a_ref_path)
        if stage15a_ref_observed_sha != stage15a_ref_expected_sha:
            raise SSOTError(
                f"Stage 15A reference artifact SHA mismatch: {stage15a_ref_path}: "
                f"{stage15a_ref_observed_sha} != {stage15a_ref_expected_sha}"
            )

    stage15a_ref_values = {}
    with stage15a_ref_qc.open("r", encoding="utf-8", newline="") as stage15a_ref_handle:
        stage15a_ref_reader = csv.DictReader(stage15a_ref_handle, delimiter="\t")
        if stage15a_ref_reader.fieldnames != ["metric", "value"]:
            raise SSOTError("Stage 15A reference QC header mismatch")
        for stage15a_ref_row in stage15a_ref_reader:
            stage15a_ref_values[stage15a_ref_row["metric"]] = stage15a_ref_row["value"]

    stage15a_ref_expected_values = {
        "stage_version": "rnatr_stage15a_reference_100k_v0.1.3",
        "run_id": stage15a_ref_run_id,
        "stage15a_reference_graph": "11b>11d3>11e>11f>11h>native_v041>materializer_v012>schema_v042",
        "stage15a1_11b_semantic_parity": "true",
        "stage15a2_11d3_semantic_parity": "true",
        "stage15a3_11e_semantic_parity": "true",
        "stage15a4_11f_semantic_parity": "true",
        "stage15a5_11h_semantic_parity": "true",
        "stage15a6_native_caller_reference_parity": "true",
        "stage15a6_hashseed_determinism": "true",
        "stage15a7_reference_materializer": "PASS",
        "stage15a7_package_exact_logical_parity": "true",
        "frozen_validators": "PASS",
        "atomic_publication": "PASS",
        "active_pipeline_modified": "false",
        "ssot_modified": "false",
        "full_5_31m_run_started": "false",
        "caller_attempt_rows": "388571",
        "called_attempt_rows": "160315",
        "low_confidence_called_rows": "6307",
        "general_repeat_calls_rows": "388571",
        "read_evidence_rows": "388571",
        "repeat_event_rows": "160297",
        "repeat_segment_rows": "161265",
        "repeat_interruption_rows": "848",
        "reference_bam_to_final_composed_seconds": "333.981925",
        "naive_5_31m_projection_minutes": "295.724073",
        "reference_lane_60min_hard_ceiling_projection": "FAIL",
        "reference_lane_30min_target": "TARGET_NOT_MET",
        "correctness_status": "PASS",
        "stage15a_overall_status": "IN_PROGRESS",
        "audit_status": "PASS",
        "next_gate": "BUILD_AND_RUN_STAGE15A_PERFORMANCE_CANDIDATE",
    }
    for stage15a_ref_metric, stage15a_ref_expected in stage15a_ref_expected_values.items():
        stage15a_ref_observed = stage15a_ref_values.get(stage15a_ref_metric)
        if stage15a_ref_observed != stage15a_ref_expected:
            raise SSOTError(
                f"Stage 15A reference QC mismatch for {stage15a_ref_metric}: "
                f"{stage15a_ref_observed!r} != {stage15a_ref_expected!r}"
            )

    if conn.execute(
        "SELECT COUNT(*) FROM runs WHERE run_id=?",
        (stage15a_ref_run_id,),
    ).fetchone()[0] != 1:
        raise SSOTError(f"Stage 15A target run is not uniquely registered: {stage15a_ref_run_id}")

    conn.execute(
        """
        INSERT OR REPLACE INTO stage_definitions(
            stage_key,stage_order,name,purpose,category,
            implementation_status,notes
        ) VALUES(?,?,?,?,?,?,?)
        """,
        (
            stage15a_ref_stage_key,
            150.0,
            "Stage 15A isolated BAM-to-final reference lane",
            "Validate the mapping-complete 100k BAM plus associated raw-read sequence store through target assignment, raw-read projection, motif jobs, validated periodic priors, deterministic native general caller v0.4.1, materializer v0.1.2, and evidence schema v0.4.2.",
            "integration_validation",
            "IMPLEMENTED_WITH_GATE",
            "Correctness reference passed in isolation. Performance, restartability at production scale, the 60-minute hard ceiling, and active-pipeline promotion remain open.",
        ),
    )

    conn.execute(
        """
        INSERT OR REPLACE INTO implementations(
            implementation_id,stage_key,version,script_path,script_sha256,
            validator_path,validator_sha256,package_version,parameters_json,
            lifecycle_status,supersedes_implementation_id,rationale,
            evidence_path,effective_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            stage15a_ref_impl_id,
            stage15a_ref_stage_key,
            "rnatr_stage15a_reference_100k_v0.1.3",
            str(stage15a_ref_runner),
            sha256_file(stage15a_ref_runner),
            str(stage15a_ref_validator_package),
            sha256_file(stage15a_ref_validator_package),
            "evidence_schema_v0.4.2",
            json.dumps(
                {
                    "input_contract": "sorted_mapping_complete_BAM+BAI+mapping_manifest+associated_raw_read_sequence_store",
                    "run_id": stage15a_ref_run_id,
                    "graph": stage15a_ref_values["stage15a_reference_graph"],
                    "native_caller": "v0.4.1",
                    "materializer": "v0.1.2",
                    "schema": "v0.4.2",
                    "reference_lane": True,
                    "active_pipeline_switch": False,
                    "full_5_31m_run": False,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            "PROVISIONAL",
            None,
            "Accepted as the isolated 100k correctness and regression reference only. It must not enter current_pipeline until the Stage 15A performance/restart gate passes and a separate activation decision is made.",
            str(stage15a_ref_qc),
            stage15a_ref_effective_at,
        ),
    )

    conn.execute(
        """
        INSERT OR REPLACE INTO run_stages(
            run_id,stage_key,implementation_id,attempt_tag,status,
            command_text,qc_path,qc_status,started_at,ended_at,notes
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            stage15a_ref_run_id,
            stage15a_ref_stage_key,
            stage15a_ref_impl_id,
            "v0.1.3",
            "PASS",
            f"python {stage15a_ref_runner}",
            str(stage15a_ref_qc),
            "PASS",
            "2026-08-08T05:05:26+00:00",
            stage15a_ref_effective_at,
            "11b/11d3/11e were verified byte-exact resumptions from v0.1.2; 11f/11h, native caller, materializer, validators, and atomic publication were executed and passed in v0.1.3.",
        ),
    )

    stage15a_ref_metrics = [
        ("stage15a_reference_correctness_status", "PASS", None, None, None),
        ("stage15a_overall_status", "IN_PROGRESS", None, None, None),
        ("bam_to_final_100k_correctness_validated", "true", 1.0, "boolean", 100000.0),
        ("bam_to_final_100k_performance_validated", "false", 0.0, "boolean", 100000.0),
        ("active_pipeline_switched_to_v042", "false", 0.0, "boolean", None),
        ("full_5_31m_run_started", "false", 0.0, "boolean", 5312696.0),
        ("package_exact_logical_parity", "true", 1.0, "boolean", 388571.0),
        ("native_caller_reference_parity", "true", 1.0, "boolean", 388571.0),
        ("hashseed_determinism", "true", 1.0, "boolean", 388571.0),
        ("caller_attempt_rows", stage15a_ref_values["caller_attempt_rows"], float(stage15a_ref_values["caller_attempt_rows"]), "rows", None),
        ("called_attempt_rows", stage15a_ref_values["called_attempt_rows"], float(stage15a_ref_values["called_attempt_rows"]), "rows", None),
        ("low_confidence_called_rows", stage15a_ref_values["low_confidence_called_rows"], float(stage15a_ref_values["low_confidence_called_rows"]), "rows", None),
        ("general_repeat_calls_rows", stage15a_ref_values["general_repeat_calls_rows"], float(stage15a_ref_values["general_repeat_calls_rows"]), "rows", None),
        ("read_evidence_rows", stage15a_ref_values["read_evidence_rows"], float(stage15a_ref_values["read_evidence_rows"]), "rows", None),
        ("repeat_event_rows", stage15a_ref_values["repeat_event_rows"], float(stage15a_ref_values["repeat_event_rows"]), "rows", None),
        ("repeat_segment_rows", stage15a_ref_values["repeat_segment_rows"], float(stage15a_ref_values["repeat_segment_rows"]), "rows", None),
        ("repeat_interruption_rows", stage15a_ref_values["repeat_interruption_rows"], float(stage15a_ref_values["repeat_interruption_rows"]), "rows", None),
        ("reference_bam_to_final_composed_seconds", stage15a_ref_values["reference_bam_to_final_composed_seconds"], float(stage15a_ref_values["reference_bam_to_final_composed_seconds"]), "seconds", 100000.0),
        ("naive_5_31m_projection_minutes", stage15a_ref_values["naive_5_31m_projection_minutes"], float(stage15a_ref_values["naive_5_31m_projection_minutes"]), "minutes", 5312696.0),
        ("reference_lane_30min_target", stage15a_ref_values["reference_lane_30min_target"], None, None, 5312696.0),
        ("reference_lane_60min_hard_ceiling_projection", stage15a_ref_values["reference_lane_60min_hard_ceiling_projection"], None, None, 5312696.0),
        ("next_gate", stage15a_ref_values["next_gate"], None, None, None),
    ]
    for (
        stage15a_ref_metric_name,
        stage15a_ref_value_text,
        stage15a_ref_value_num,
        stage15a_ref_unit,
        stage15a_ref_denominator,
    ) in stage15a_ref_metrics:
        conn.execute(
            """
            INSERT OR REPLACE INTO metrics(
                run_id,stage_key,metric_name,value_text,value_num,unit,
                denominator_num,source_path,metric_status,recorded_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (
                stage15a_ref_run_id,
                stage15a_ref_stage_key,
                stage15a_ref_metric_name,
                stage15a_ref_value_text,
                stage15a_ref_value_num,
                stage15a_ref_unit,
                stage15a_ref_denominator,
                str(stage15a_ref_qc),
                "CURRENT",
                stage15a_ref_effective_at,
            ),
        )

    add_decision(
        conn,
        key="stage15a_reference_correctness_pass_v0_1_3",
        category="integration",
        title="Stage 15A isolated 100k BAM-to-final correctness reference accepted",
        statement="The isolated Stage 15A v0.1.3 path from the target 100k mapping-complete BAM and associated raw-read sequence store through schema v0.4.2 is accepted as the correctness and regression reference. It is not the active production pipeline and it has not passed the production performance gate.",
        status="ACTIVE",
        confidence="HIGH",
        rationale="All upstream semantic comparisons, native-caller reference parity, hash-seed determinism, five-table validation, cross-table validation, exact logical package parity, and atomic publication passed. The measured reference runtime still fails both the 30-minute target and the 60-minute projected hard ceiling at 5.31M reads.",
        evidence_path=str(stage15a_ref_qc),
        effective_at=stage15a_ref_effective_at,
    )

    add_interpretation(
        conn,
        key="stage15a_reference_correctness_scope",
        fact="Stage 15A v0.1.3 produced a schema v0.4.2 package with exact logical parity to the frozen reference after an isolated 100k BAM-input replay; all correctness gates passed and the active pipeline remained unchanged.",
        interpretation="The target 100k BAM-to-final correctness integration is closed for the reference lane. The next work is performance, restart/resume, and production-scale gating.",
        do_not="Do not interpret this as active-pipeline promotion, proof of a 30- or 60-minute 5.31M runtime, authorization to run the full 5.31M sample, biological truth validation, pathogenicity assessment, or inferred personal DNA genotype.",
        confidence="HIGH",
        evidence_path=str(stage15a_ref_qc),
        evidence_metrics={
            "caller_attempt_rows": int(stage15a_ref_values["caller_attempt_rows"]),
            "called_attempt_rows": int(stage15a_ref_values["called_attempt_rows"]),
            "package_exact_logical_parity": True,
            "reference_bam_to_final_composed_seconds": float(stage15a_ref_values["reference_bam_to_final_composed_seconds"]),
            "naive_5_31m_projection_minutes": float(stage15a_ref_values["naive_5_31m_projection_minutes"]),
            "active_pipeline_modified": False,
            "full_5_31m_run_started": False,
        },
        status="ACTIVE",
        effective_at=stage15a_ref_effective_at,
    )

    conn.execute(
        """
        INSERT OR REPLACE INTO limitations(
            limitation_key,statement,severity,status,mitigation,
            evidence_path,effective_at
        ) VALUES(?,?,?,?,?,?,?)
        """,
        (
            "CURRENT_RUNTIME_NOT_PRODUCTION_SCALE",
            "The Stage 15A v0.1.3 isolated reference path required 333.981925 seconds for the composed 100k BAM-input correctness lane. A naive linear projection is 295.724073 minutes for 5.31M reads, so the 30-minute target and 60-minute hard ceiling are not met by the reference architecture.",
            "CRITICAL",
            "ACTIVE",
            "Run the isolated Stage 15A performance candidate with exact package parity, restart/resume, bounded memory, fused or parallel materialization/validation, and atomic publication. Do not run the full 5.31M sample or activate schema v0.4.2 until the conservative projection is at most 60 minutes; continue optimization until the 30-minute target is met.",
            str(stage15a_ref_qc),
            stage15a_ref_effective_at,
        ),
    )

    conn.execute(
        """
        INSERT OR REPLACE INTO open_questions(
            question_key,question,priority,status,blocking,next_action,
            evidence_path,effective_at
        ) VALUES(?,?,?,?,?,?,?,?)
        """,
        (
            "GENERAL_CALLER_PRODUCTION_INTEGRATION",
            "Can the validated Stage 15A native-caller/schema path be promoted from isolated 100k correctness validation to a restartable production-scale BAM-input pipeline that meets the 30-minute target and 60-minute hard ceiling?",
            "CRITICAL",
            "OPEN",
            1,
            "Run the Stage 15A 100k performance candidate and require exact logical package parity, restart/resume, bounded memory, frozen-validator agreement, and atomic publication. Require a conservative 5.31M projection of at most 60 minutes before any full 5.31M run; keep the active pipeline unchanged.",
            str(stage15a_ref_qc),
            stage15a_ref_effective_at,
        ),
    )

    conn.execute(
        """
        UPDATE open_questions
        SET status='CLOSED',blocking=0,
            next_action='Completed by Stage 15A v0.1.3 isolated 100k correctness reference; performance and activation remain tracked under GENERAL_CALLER_PRODUCTION_INTEGRATION.',
            evidence_path=?,effective_at=?
        WHERE question_key IN (
            'BAM_TO_FINAL_100K_INTEGRATION',
            'STAGE15A_100K_BAM_TO_FINAL_CORRECTNESS'
        )
        """,
        (str(stage15a_ref_qc), stage15a_ref_effective_at),
    )

    stage15a_ref_failures = [
        (
            "stage15a_v010_obsolete_validator_path",
            "v0.1.0",
            "Stage 15A1 stopped because the wrapper invoked an obsolete alignment-segment validator that rejected the valid unmapped strand value '.'.",
            "Wrapper path plumbing selected an obsolete validator; BAM contents and 11b semantics were not the cause.",
            "Resolved in v0.1.1 by freezing validator_v0.3.1 without filtering or altering BAM records.",
        ),
        (
            "stage15a_v011_report_only_sigpipe",
            "v0.1.1",
            "Stage 15A3 stopped with exit 141 after 11e computation completed.",
            "A report-only sort-to-head pipeline raised SIGPIPE under pipefail.",
            "Resolved in v0.1.2 by replacing the display-only head consumer with full-consuming sed; algorithmic output was unchanged.",
        ),
        (
            "stage15a_v012_missing_periodic_priors",
            "v0.1.2",
            "Stage 15A4 caller startup stopped because the isolated graph had not produced the validated 11f/11h periodic-prior artifact required by the promoted caller driver.",
            "The execution graph omitted validated dependencies 11f and 11h.",
            "Resolved in v0.1.3 by executing fresh isolated 11f and 11h outputs and verifying their semantic parity before the native caller.",
        ),
    ]
    for (
        stage15a_ref_failure_id,
        stage15a_ref_attempt,
        stage15a_ref_summary,
        stage15a_ref_root_cause,
        stage15a_ref_resolution,
    ) in stage15a_ref_failures:
        conn.execute(
            """
            INSERT OR REPLACE INTO failures(
                failure_id,run_id,stage_key,attempt_version,status,summary,
                root_cause,resolution,source_path,superseded_by,recorded_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                stage15a_ref_failure_id,
                stage15a_ref_run_id,
                stage15a_ref_stage_key,
                stage15a_ref_attempt,
                "RESOLVED",
                stage15a_ref_summary,
                stage15a_ref_root_cause,
                stage15a_ref_resolution,
                str(stage15a_ref_qc),
                "rnatr_stage15a_reference_100k_v0.1.3",
                stage15a_ref_effective_at,
            ),
        )

    for stage15a_ref_source_path, stage15a_ref_source_type in [
        (stage15a_ref_qc, "stage15a_reference_qc"),
        (stage15a_ref_timing, "stage15a_reference_timing"),
        (stage15a_ref_package_manifest, "stage15a_reference_package_manifest"),
        (stage15a_ref_runner, "stage15a_reference_runner"),
    ]:
        source_document(
            conn,
            stage15a_ref_source_path,
            stage15a_ref_source_type,
            force_hash=True,
        )


    # Stage 15A performance SSOT registration v0.2.2.1
    stage15a_perf_effective_at = "2026-08-08T11:31:27+00:00"
    stage15a_perf_run_id = "ENCSR307SHM_pilot100k_mm2splice_v1"
    stage15a_perf_stage_key = "15A_BAM_TO_FINAL_PERFORMANCE"

    stage15a_perf_v020_failure = project_root / "qc/15_stage15a_bam_to_final/ENCSR307SHM_pilot100k_mm2splice_v1/v0.2.0_performance/stage15a_performance_100k.failure.txt"
    stage15a_perf_v0201_qc = project_root / "qc/15_stage15a_bam_to_final/ENCSR307SHM_pilot100k_mm2splice_v1/v0.2.0.1_performance/stage15a_performance_100k.qc.tsv"
    stage15a_perf_v0201_timing = project_root / "qc/15_stage15a_bam_to_final/ENCSR307SHM_pilot100k_mm2splice_v1/v0.2.0.1_performance/stage15a_performance_timing.tsv"
    stage15a_perf_v0201_runner = project_root / "scripts/rnatr_stage15a_run_performance_100k_v0.2.0.1.py"
    stage15a_perf_v021_qc = project_root / "qc/15_stage15a_bam_to_final/ENCSR307SHM_pilot100k_mm2splice_v1/v0.2.1_performance/stage15a_performance_100k.qc.tsv"
    stage15a_perf_v021_timing = project_root / "qc/15_stage15a_bam_to_final/ENCSR307SHM_pilot100k_mm2splice_v1/v0.2.1_performance/stage15a_performance_timing.tsv"
    stage15a_perf_v021_runner = project_root / "scripts/rnatr_stage15a_run_performance_100k_v0.2.1.py"
    stage15a_perf_v022_failure = project_root / "qc/15_stage15a_bam_to_final/ENCSR307SHM_pilot100k_mm2splice_v1/v0.2.2_performance/stage15a_performance_100k.failure.txt"
    stage15a_perf_v022_validator_log = project_root / "qc/15_stage15a_bam_to_final/ENCSR307SHM_pilot100k_mm2splice_v1/v0.2.2_performance/logs/validators/package_prepublication.log"
    stage15a_perf_v022_runner = project_root / "scripts/rnatr_stage15a_run_performance_100k_v0.2.2.py"
    stage15a_perf_v0221_qc = project_root / "qc/15_stage15a_bam_to_final/ENCSR307SHM_pilot100k_mm2splice_v1/v0.2.2.1_performance/stage15a_performance_100k.qc.tsv"
    stage15a_perf_v0221_timing = project_root / "qc/15_stage15a_bam_to_final/ENCSR307SHM_pilot100k_mm2splice_v1/v0.2.2.1_performance/stage15a_performance_timing.tsv"
    stage15a_perf_v0221_comparison = project_root / "qc/15_stage15a_bam_to_final/ENCSR307SHM_pilot100k_mm2splice_v1/v0.2.2.1_performance/comparison/stage15a_performance_package_comparison.tsv"
    stage15a_perf_v0221_post_audit = project_root / "qc/15_stage15a_bam_to_final/ENCSR307SHM_pilot100k_mm2splice_v1/v0.2.2.1_performance/stage15a_performance_post_timer_audit.qc.tsv"
    stage15a_perf_v0221_validators = project_root / "qc/15_stage15a_bam_to_final/ENCSR307SHM_pilot100k_mm2splice_v1/v0.2.2.1_performance/stage15a_performance_validators.tsv"
    stage15a_perf_v0221_atomic = project_root / "qc/15_stage15a_bam_to_final/ENCSR307SHM_pilot100k_mm2splice_v1/v0.2.2.1_performance/stage15a_performance_atomic_publication.tsv"
    stage15a_perf_v0221_manifest = project_root / "results/15_stage15a_bam_to_final/ENCSR307SHM_pilot100k_mm2splice_v1/v0.2.2.1_performance/package_performance/package_manifest.tsv"
    stage15a_perf_v0221_runner = project_root / "scripts/rnatr_stage15a_run_performance_100k_v0.2.2.1.py"
    stage15a_perf_v0221_parallel_validator = project_root / "scripts/rnatr_stage15a_validate_package_parallel_v0.2.2.1.py"
    stage15a_perf_frozen_package_validator = project_root / "config/evidence_schema/v0.4.2/rnatr_v042_validate_package.py"

    stage15a_perf_required_hashes = {
        stage15a_perf_v020_failure: "82b0ce0beee7a7f1bc6d07501bba57dcc738302288ef835ab04d92a71b507115",
        stage15a_perf_v0201_qc: "c634e60d79b96f0bb4513593410b9f1dec005d2d080216d103819b674e23c909",
        stage15a_perf_v0201_timing: "7ec30246eed790296c8647a85c50014ee16fab011b014a36cde350817c465035",
        stage15a_perf_v0201_runner: "568c51aeefb78dd3da7244837377e28cb96735bd5afa4a34e99efcdc8200a747",
        stage15a_perf_v021_qc: "5d4d40beecd2326082b1a7656144a7fb904cb078664afdbd1aca9e0d4f1d26ce",
        stage15a_perf_v021_timing: "4c8cba890f5545e5080b7af8dec04ea868398cd48ba2a081fe1bdb1a837d9570",
        stage15a_perf_v021_runner: "371bc8fd3d02d96adf295d891948f09488caaec05511e29e1fd874898de7294c",
        stage15a_perf_v022_failure: "241557dd8f3f16ec03007b6895a30423cb7584fe71d562268ba1972645f6646f",
        stage15a_perf_v022_validator_log: "5dfb8f13066343aeb0a76ec8ce54c8001b26ca9ddc0eb67033dde932364c7904",
        stage15a_perf_v022_runner: "2ac29866d08bb0e70d7d169d90346386eb9623c63f011cc0a68471822528f96f",
        stage15a_perf_v0221_qc: "401cfa9d9e524ceebfef9f6665d0f2b435627133c40cfcb6b8df7d989e4ac733",
        stage15a_perf_v0221_timing: "dbe46beaa7f555c4d7454c3fb95851d4ddd9b05df8a8ca2b56e00479c57b8b42",
        stage15a_perf_v0221_comparison: "28df037888876656e9a4f5a2b460bc09613cd0ae4badf757e362f5f39f271661",
        stage15a_perf_v0221_post_audit: "46e698553f4dea7b953600a2d0ef68bdd81031c131d0a3ca67c526cded4893fe",
        stage15a_perf_v0221_validators: "ff15379adcba8ab063f10e721ee7ca04861e34c0a0853650b2537202ef5eab9b",
        stage15a_perf_v0221_atomic: "8214f65b7c27ca509ade30b973cfe0cbe00c1c0c4ce7fb5aae13901447f2b63a",
        stage15a_perf_v0221_manifest: "0e74e2eaf8cac0bc75ca0c89a725576946ac61476bce4cf4e76951402f4c13e3",
        stage15a_perf_v0221_runner: "7bfb7018cea80cd92854882751cffb49bea817296f69866801a64f9529c5e1a8",
        stage15a_perf_v0221_parallel_validator: "b635ed213b65cee005914f0fded9337871903a7e5682f9a897dff9cbc9bb0b09",
        stage15a_perf_frozen_package_validator: "45c3995550f57a65b3fec4aab7471d57b7000e19471d4c5cf7f3ae055426984e",
    }
    for stage15a_perf_path, stage15a_perf_expected_sha in stage15a_perf_required_hashes.items():
        if not stage15a_perf_path.is_file():
            raise SSOTError(f"Stage 15A performance artifact missing: {stage15a_perf_path}")
        stage15a_perf_observed_sha = sha256_file(stage15a_perf_path)
        if stage15a_perf_observed_sha != stage15a_perf_expected_sha:
            raise SSOTError(
                f"Stage 15A performance artifact SHA mismatch: {stage15a_perf_path}: "
                f"{stage15a_perf_observed_sha} != {stage15a_perf_expected_sha}"
            )

    def stage15a_perf_read_metrics(stage15a_perf_path):
        stage15a_perf_values = {}
        with stage15a_perf_path.open("r", encoding="utf-8", newline="") as stage15a_perf_handle:
            stage15a_perf_reader = csv.DictReader(stage15a_perf_handle, delimiter="\t")
            if stage15a_perf_reader.fieldnames != ["metric", "value"]:
                raise SSOTError(f"Stage 15A performance QC header mismatch: {stage15a_perf_path}")
            for stage15a_perf_row in stage15a_perf_reader:
                stage15a_perf_values[stage15a_perf_row["metric"]] = stage15a_perf_row["value"]
        return stage15a_perf_values

    stage15a_perf_v0201_values = stage15a_perf_read_metrics(stage15a_perf_v0201_qc)
    stage15a_perf_v021_values = stage15a_perf_read_metrics(stage15a_perf_v021_qc)
    stage15a_perf_v0221_values = stage15a_perf_read_metrics(stage15a_perf_v0221_qc)

    stage15a_perf_expected = {
        "stage_version": "rnatr_stage15a_sharded_bam_to_final_performance_v0.2.2.1",
        "run_id": stage15a_perf_run_id,
        "performance_candidate_bam_to_final_seconds": "65.76363927999046",
        "performance_candidate_speedup": "5.078519507992296",
        "conservative_linear_5_31m_projection_minutes": "58.230370558041365",
        "five_m_hard_ceiling_60min": "PASS",
        "five_m_target_30min": "TARGET_NOT_MET",
        "package_exact_logical_parity": "true",
        "frozen_tsv_validators": "PASS",
        "parallel_exact_component_package_validator_prepublication": "PASS",
        "frozen_package_validator_postpublication": "PASS",
        "parallel_validator_missing_artifact_failure_parity": "PASS",
        "atomic_publication": "PASS",
        "active_pipeline_modified": "false",
        "ssot_modified": "false",
        "full_5_31m_run_started": "false",
        "correctness_status": "PASS",
        "performance_implementation_status": "PASS",
        "stage15a_overall_status": "IN_PROGRESS",
        "next_gate": "RUN_STAGE15A_RESTART_AND_DETERMINISTIC_250K_SCALING_NOT_FULL_5_31M",
    }
    for stage15a_perf_metric, stage15a_perf_wanted in stage15a_perf_expected.items():
        stage15a_perf_observed = stage15a_perf_v0221_values.get(stage15a_perf_metric)
        if stage15a_perf_observed != stage15a_perf_wanted:
            raise SSOTError(
                f"Stage 15A v0.2.2.1 QC mismatch {stage15a_perf_metric}: "
                f"{stage15a_perf_observed!r} != {stage15a_perf_wanted!r}"
            )

    if conn.execute("SELECT COUNT(*) FROM runs WHERE run_id=?", (stage15a_perf_run_id,)).fetchone()[0] != 1:
        raise SSOTError(f"Stage 15A performance target run is not uniquely registered: {stage15a_perf_run_id}")

    conn.execute(
        """
        INSERT OR REPLACE INTO stage_definitions(
            stage_key,stage_order,name,purpose,category,implementation_status,notes
        ) VALUES(?,?,?,?,?,?,?)
        """,
        (
            stage15a_perf_stage_key,
            151.0,
            "Stage 15A isolated BAM-to-final performance lane",
            "Develop and validate an exact-parity, read-coherently sharded, restartable production candidate for mapping-complete BAM plus associated raw-read sequence store to schema v0.4.2 package.",
            "performance_validation",
            "IMPLEMENTED_WITH_GATE",
            "v0.2.2.1 passes the 100k correctness and conservative 60-minute linear-projection gate. Restart/resume, deterministic 250k scaling, empirical full-scale runtime, and the 30-minute target remain open.",
        ),
    )

    stage15a_perf_impl_rows = [
        (
            "impl_stage15a_performance_v0_2_0_1",
            "rnatr_stage15a_sharded_bam_to_final_performance_v0.2.0.1",
            stage15a_perf_v0201_runner,
            "SUPERSEDED",
            None,
            stage15a_perf_v0201_qc,
            "First exact-parity sharded performance implementation; superseded after 99.788-second 100k result projected 88.358 minutes.",
        ),
        (
            "impl_stage15a_performance_v0_2_1",
            "rnatr_stage15a_sharded_bam_to_final_performance_v0.2.1",
            stage15a_perf_v021_runner,
            "SUPERSEDED",
            "impl_stage15a_performance_v0_2_0_1",
            stage15a_perf_v021_qc,
            "Low-risk critical-path revision; superseded after 81.400-second 100k result projected 72.076 minutes.",
        ),
        (
            "impl_stage15a_performance_v0_2_2_1",
            "rnatr_stage15a_sharded_bam_to_final_performance_v0.2.2.1",
            stage15a_perf_v0221_runner,
            "PROVISIONAL",
            "impl_stage15a_performance_v0_2_1",
            stage15a_perf_v0221_qc,
            "Accepted as the current isolated performance candidate because exact logical parity, validators, failure-parity testing, atomic publication, and a conservative 58.230-minute 5.31M projection passed. It is not ACTIVE.",
        ),
    ]
    for (
        stage15a_perf_impl_id,
        stage15a_perf_version,
        stage15a_perf_runner,
        stage15a_perf_lifecycle,
        stage15a_perf_supersedes,
        stage15a_perf_evidence,
        stage15a_perf_rationale,
    ) in stage15a_perf_impl_rows:
        conn.execute(
            """
            INSERT OR REPLACE INTO implementations(
                implementation_id,stage_key,version,script_path,script_sha256,
                validator_path,validator_sha256,package_version,parameters_json,
                lifecycle_status,supersedes_implementation_id,rationale,
                evidence_path,effective_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                stage15a_perf_impl_id,
                stage15a_perf_stage_key,
                stage15a_perf_version,
                str(stage15a_perf_runner),
                sha256_file(stage15a_perf_runner),
                str(stage15a_perf_v0221_parallel_validator if stage15a_perf_impl_id.endswith("2_2_1") else stage15a_perf_frozen_package_validator),
                sha256_file(stage15a_perf_v0221_parallel_validator if stage15a_perf_impl_id.endswith("2_2_1") else stage15a_perf_frozen_package_validator),
                "evidence_schema_v0.4.2",
                json.dumps(
                    {
                        "input_contract": "sorted_mapping_complete_BAM+associated_raw_read_sequence_store",
                        "run_id": stage15a_perf_run_id,
                        "read_coherent_sharding": True,
                        "shard_count": 12 if stage15a_perf_impl_id != "impl_stage15a_performance_v0_2_0_1" else 6,
                        "caller_workers_total": 24,
                        "native_caller": "v0.4.1",
                        "materializer_semantics": "v0.1.2",
                        "schema": "v0.4.2",
                        "active_pipeline_switch": False,
                        "full_5_31m_run": False,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                stage15a_perf_lifecycle,
                stage15a_perf_supersedes,
                stage15a_perf_rationale,
                str(stage15a_perf_evidence),
                stage15a_perf_effective_at,
            ),
        )

    stage15a_perf_run_rows = [
        ("impl_stage15a_performance_v0_2_0_1", "v0.2.0.1", "PASS", stage15a_perf_v0201_qc, "PASS", "2026-08-08T08:18:56+00:00", "Exact-parity performance baseline; hard-ceiling projection failed."),
        ("impl_stage15a_performance_v0_2_1", "v0.2.1", "PASS", stage15a_perf_v021_qc, "PASS", "2026-08-08T08:51:31+00:00", "Critical-path optimization; hard-ceiling projection remained above 60 minutes."),
        (None, "v0.2.2", "FAIL", stage15a_perf_v022_failure, "FAIL", "2026-08-08T09:24:43+00:00", "Performance computation reached final validation but the new parallel validator passed an incorrect CLI argument to the flank-uniqueness component."),
        ("impl_stage15a_performance_v0_2_2_1", "v0.2.2.1", "PASS", stage15a_perf_v0221_qc, "PASS", stage15a_perf_effective_at, "Corrected validator wiring; 100k exact-parity production timer passed the conservative 60-minute linear-projection gate."),
    ]
    for (
        stage15a_perf_impl_id,
        stage15a_perf_attempt,
        stage15a_perf_status,
        stage15a_perf_qc_path,
        stage15a_perf_qc_status,
        stage15a_perf_ended_at,
        stage15a_perf_notes,
    ) in stage15a_perf_run_rows:
        conn.execute(
            """
            INSERT OR REPLACE INTO run_stages(
                run_id,stage_key,implementation_id,attempt_tag,status,
                command_text,qc_path,qc_status,started_at,ended_at,notes
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                stage15a_perf_run_id,
                stage15a_perf_stage_key,
                stage15a_perf_impl_id,
                stage15a_perf_attempt,
                stage15a_perf_status,
                None if stage15a_perf_impl_id is None else f"python {dict((row[0], row[2]) for row in stage15a_perf_impl_rows)[stage15a_perf_impl_id]}",
                str(stage15a_perf_qc_path),
                stage15a_perf_qc_status,
                None,
                stage15a_perf_ended_at,
                stage15a_perf_notes,
            ),
        )

    stage15a_perf_observed_metrics = [
        ("v0_2_0_1_bam_to_final_seconds", stage15a_perf_v0201_values["performance_candidate_bam_to_final_seconds"], "seconds", 100000.0, stage15a_perf_v0201_qc),
        ("v0_2_0_1_projection_minutes", stage15a_perf_v0201_values["conservative_linear_5_31m_projection_minutes"], "minutes", 5312696.0, stage15a_perf_v0201_qc),
        ("v0_2_1_bam_to_final_seconds", stage15a_perf_v021_values["performance_candidate_bam_to_final_seconds"], "seconds", 100000.0, stage15a_perf_v021_qc),
        ("v0_2_1_projection_minutes", stage15a_perf_v021_values["conservative_linear_5_31m_projection_minutes"], "minutes", 5312696.0, stage15a_perf_v021_qc),
    ]
    for stage15a_perf_name, stage15a_perf_text, stage15a_perf_unit, stage15a_perf_denominator, stage15a_perf_source in stage15a_perf_observed_metrics:
        conn.execute(
            """
            INSERT OR REPLACE INTO metrics(
                run_id,stage_key,metric_name,value_text,value_num,unit,
                denominator_num,source_path,metric_status,recorded_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (
                stage15a_perf_run_id,
                stage15a_perf_stage_key,
                stage15a_perf_name,
                stage15a_perf_text,
                float(stage15a_perf_text),
                stage15a_perf_unit,
                stage15a_perf_denominator,
                str(stage15a_perf_source),
                "OBSERVED",
                stage15a_perf_effective_at,
            ),
        )

    stage15a_perf_current_metrics = [
        ("stage15a_performance_100k_status", "PASS", None, None, 100000.0),
        ("stage15a_overall_status", "IN_PROGRESS", None, None, None),
        ("bam_to_final_100k_performance_validated", "true", 1.0, "boolean", 100000.0),
        ("restart_resume_validated", "false", 0.0, "boolean", None),
        ("deterministic_250k_scaling_validated", "false", 0.0, "boolean", 250000.0),
        ("full_5_31m_empirical_runtime_validated", "false", 0.0, "boolean", 5312696.0),
        ("active_pipeline_switched_to_v042", "false", 0.0, "boolean", None),
        ("full_5_31m_run_started", "false", 0.0, "boolean", 5312696.0),
        ("package_exact_logical_parity", "true", 1.0, "boolean", 388571.0),
        ("general_repeat_calls_rows", stage15a_perf_v0221_values["general_repeat_calls_rows"], float(stage15a_perf_v0221_values["general_repeat_calls_rows"]), "rows", None),
        ("read_evidence_rows", stage15a_perf_v0221_values["read_evidence_rows"], float(stage15a_perf_v0221_values["read_evidence_rows"]), "rows", None),
        ("repeat_event_rows", stage15a_perf_v0221_values["repeat_event_rows"], float(stage15a_perf_v0221_values["repeat_event_rows"]), "rows", None),
        ("repeat_segment_rows", stage15a_perf_v0221_values["repeat_segment_rows"], float(stage15a_perf_v0221_values["repeat_segment_rows"]), "rows", None),
        ("repeat_interruption_rows", stage15a_perf_v0221_values["repeat_interruption_rows"], float(stage15a_perf_v0221_values["repeat_interruption_rows"]), "rows", None),
        ("performance_candidate_bam_to_final_seconds", stage15a_perf_v0221_values["performance_candidate_bam_to_final_seconds"], float(stage15a_perf_v0221_values["performance_candidate_bam_to_final_seconds"]), "seconds", 100000.0),
        ("performance_candidate_speedup", stage15a_perf_v0221_values["performance_candidate_speedup"], float(stage15a_perf_v0221_values["performance_candidate_speedup"]), "fold", 100000.0),
        ("conservative_linear_5_31m_projection_minutes", stage15a_perf_v0221_values["conservative_linear_5_31m_projection_minutes"], float(stage15a_perf_v0221_values["conservative_linear_5_31m_projection_minutes"]), "minutes", 5312696.0),
        ("five_m_hard_ceiling_60min_projection", stage15a_perf_v0221_values["five_m_hard_ceiling_60min"], None, None, 5312696.0),
        ("five_m_target_30min", stage15a_perf_v0221_values["five_m_target_30min"], None, None, 5312696.0),
        ("hard_ceiling_evidence_scope", "100K_LINEAR_PROJECTION_NOT_EMPIRICAL_5_31M", None, None, 5312696.0),
        ("next_gate", stage15a_perf_v0221_values["next_gate"], None, None, None),
    ]
    for (
        stage15a_perf_metric_name,
        stage15a_perf_value_text,
        stage15a_perf_value_num,
        stage15a_perf_unit,
        stage15a_perf_denominator,
    ) in stage15a_perf_current_metrics:
        conn.execute(
            """
            INSERT OR REPLACE INTO metrics(
                run_id,stage_key,metric_name,value_text,value_num,unit,
                denominator_num,source_path,metric_status,recorded_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (
                stage15a_perf_run_id,
                stage15a_perf_stage_key,
                stage15a_perf_metric_name,
                stage15a_perf_value_text,
                stage15a_perf_value_num,
                stage15a_perf_unit,
                stage15a_perf_denominator,
                str(stage15a_perf_v0221_qc),
                "CURRENT",
                stage15a_perf_effective_at,
            ),
        )

    add_decision(
        conn,
        key="stage15a_performance_100k_v0_2_2_1_projection_pass",
        category="performance",
        title="Stage 15A v0.2.2.1 accepted as the current 100k performance candidate",
        statement="Stage 15A v0.2.2.1 is accepted as the current isolated 100k BAM-to-final performance candidate. It preserves exact logical package parity and yields a conservative linear 5.31M projection of 58.230370558041365 minutes, passing the projected 60-minute hard-ceiling gate while missing the 30-minute target.",
        status="ACTIVE",
        confidence="HIGH",
        rationale="The 65.76363927999046-second production timer includes frozen table validation, exact-component package validation, and atomic publication. Full post-timer development audit, frozen post-publication validation, exact reference comparison, and negative-fixture failure parity also passed. Restartability and intermediate-scale scaling remain unvalidated.",
        evidence_path=str(stage15a_perf_v0221_qc),
        effective_at=stage15a_perf_effective_at,
    )

    add_interpretation(
        conn,
        key="stage15a_performance_projection_scope_v0_2_2_1",
        fact="The exact-parity Stage 15A v0.2.2.1 100k performance lane completed in 65.76363927999046 seconds and linearly projects to 58.230370558041365 minutes for 5,312,696 reads.",
        interpretation="The 100k-derived conservative projection now passes the 60-minute hard-ceiling criterion and justifies restart/resume plus deterministic 250k scaling as the next gate.",
        do_not="Do not describe this as an observed full 5.31M runtime, completion of Stage 15A, attainment of the 30-minute target, active-pipeline promotion, authorization to run full 5.31M, biological truth validation, or pathogenicity assessment.",
        confidence="HIGH",
        evidence_path=str(stage15a_perf_v0221_qc),
        evidence_metrics={
            "performance_candidate_bam_to_final_seconds": 65.76363927999046,
            "conservative_linear_5_31m_projection_minutes": 58.230370558041365,
            "package_exact_logical_parity": True,
            "active_pipeline_modified": False,
            "full_5_31m_run_started": False,
        },
        status="ACTIVE",
        effective_at=stage15a_perf_effective_at,
    )

    conn.execute(
        """
        INSERT OR REPLACE INTO limitations(
            limitation_key,statement,severity,status,mitigation,
            evidence_path,effective_at
        ) VALUES(?,?,?,?,?,?,?)
        """,
        (
            "CURRENT_RUNTIME_NOT_PRODUCTION_SCALE",
            "Stage 15A v0.2.2.1 improved the isolated 100k BAM-to-final production timer to 65.76363927999046 seconds and passes a conservative 58.230370558041365-minute linear projection for 5.31M reads. However, the 30-minute target is not met and restartability, memory behavior, and intermediate/full-scale nonlinearity have not yet been empirically validated.",
            "HIGH",
            "ACTIVE",
            "Validate restart/resume and deterministic 250k scaling before any full 5.31M execution. Continue structural optimization toward the 30-minute target after the scaling model is updated.",
            str(stage15a_perf_v0221_qc),
            stage15a_perf_effective_at,
        ),
    )

    conn.execute(
        """
        INSERT OR REPLACE INTO limitations(
            limitation_key,statement,severity,status,mitigation,
            evidence_path,effective_at
        ) VALUES(?,?,?,?,?,?,?)
        """,
        (
            "STAGE15A_FULL_SCALE_RUNTIME_NOT_EMPIRICALLY_VALIDATED",
            "The current 58.230-minute value is a linear projection from 100k reads, not an observed 5.31M BAM-to-final runtime. Startup overhead, memory pressure, storage contention, candidate density, and scaling nonlinearity remain uncertain.",
            "HIGH",
            "ACTIVE",
            "Run deterministic 250k scaling with stage-level wall time, peak RSS, temporary bytes, exact package reproducibility, and restart/resume audit before considering a full-depth run.",
            str(stage15a_perf_v0221_qc),
            stage15a_perf_effective_at,
        ),
    )

    conn.execute(
        """
        INSERT OR REPLACE INTO open_questions(
            question_key,question,priority,status,blocking,next_action,
            evidence_path,effective_at
        ) VALUES(?,?,?,?,?,?,?,?)
        """,
        (
            "GENERAL_CALLER_PRODUCTION_INTEGRATION",
            "Can the exact-parity Stage 15A performance candidate remain restartable, deterministic, and within the 60-minute hard ceiling as input size increases, while continuing toward the 30-minute target?",
            "CRITICAL",
            "OPEN",
            1,
            "Run Stage 15A restart/resume validation and a deterministic 250k BAM-input scaling benchmark. Require exact package reproducibility, bounded memory, complete artifact audit, and updated scaling estimates. Do not run full 5.31M or change current_pipeline yet.",
            str(stage15a_perf_v0221_qc),
            stage15a_perf_effective_at,
        ),
    )

    add_contract(
        conn,
        key="stage15a_performance_candidate_v0221",
        name="Stage 15A performance candidate v0.2.2.1",
        state="100K_PROJECTED_60MIN_PASS_RESTART_250K_OPEN",
        statement="v0.2.2.1 is the current exact-parity isolated performance candidate. Its 65.763639-second 100k production timer linearly projects to 58.230371 minutes for 5.31M reads. This projection is not empirical full-scale validation; restart/resume and deterministic 250k scaling remain blocking.",
        implementation_id="impl_stage15a_performance_v0_2_2_1",
        evidence_path=str(stage15a_perf_v0221_qc),
    )

    stage15a_perf_failures = [
        (
            "stage15a_perf_v020_escape_anchor",
            "v0.2.0",
            "The first performance runner stopped before partitioning because a Python patch anchor encoded shell backslash-t as a literal TAB and matched zero lines.",
            "Wrapper string escaping, not performance architecture or scientific logic.",
            "Resolved in v0.2.0.1 by correcting the anchor escape and rerunning in a new isolated root.",
            stage15a_perf_v020_failure,
            "rnatr_stage15a_sharded_bam_to_final_performance_v0.2.0.1",
        ),
        (
            "stage15a_perf_v022_validator_cli_wiring",
            "v0.2.2",
            "The performance computation reached final validation but the flank-uniqueness validator received --package-dir instead of its required --input argument.",
            "Parallel validator CLI wiring error; all upstream computation and generic validators had completed.",
            "Resolved in v0.2.2.1 by component-specific argument wiring and a negative-fixture failure-parity test.",
            stage15a_perf_v022_failure,
            "rnatr_stage15a_sharded_bam_to_final_performance_v0.2.2.1",
        ),
    ]
    for (
        stage15a_perf_failure_id,
        stage15a_perf_attempt,
        stage15a_perf_summary,
        stage15a_perf_root_cause,
        stage15a_perf_resolution,
        stage15a_perf_source,
        stage15a_perf_superseded_by,
    ) in stage15a_perf_failures:
        conn.execute(
            """
            INSERT OR REPLACE INTO failures(
                failure_id,run_id,stage_key,attempt_version,status,summary,
                root_cause,resolution,source_path,superseded_by,recorded_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                stage15a_perf_failure_id,
                stage15a_perf_run_id,
                stage15a_perf_stage_key,
                stage15a_perf_attempt,
                "RESOLVED",
                stage15a_perf_summary,
                stage15a_perf_root_cause,
                stage15a_perf_resolution,
                str(stage15a_perf_source),
                stage15a_perf_superseded_by,
                stage15a_perf_effective_at,
            ),
        )

    for stage15a_perf_source_path, stage15a_perf_source_type in [
        (stage15a_perf_v020_failure, "stage15a_performance_failure_v020"),
        (stage15a_perf_v0201_qc, "stage15a_performance_qc_v0201"),
        (stage15a_perf_v0201_timing, "stage15a_performance_timing_v0201"),
        (stage15a_perf_v0201_runner, "stage15a_performance_runner_v0201"),
        (stage15a_perf_v021_qc, "stage15a_performance_qc_v021"),
        (stage15a_perf_v021_timing, "stage15a_performance_timing_v021"),
        (stage15a_perf_v021_runner, "stage15a_performance_runner_v021"),
        (stage15a_perf_v022_failure, "stage15a_performance_failure_v022"),
        (stage15a_perf_v022_validator_log, "stage15a_performance_validator_failure_v022"),
        (stage15a_perf_v022_runner, "stage15a_performance_runner_v022"),
        (stage15a_perf_v0221_qc, "stage15a_performance_qc_v0221"),
        (stage15a_perf_v0221_timing, "stage15a_performance_timing_v0221"),
        (stage15a_perf_v0221_comparison, "stage15a_performance_comparison_v0221"),
        (stage15a_perf_v0221_post_audit, "stage15a_performance_post_audit_v0221"),
        (stage15a_perf_v0221_validators, "stage15a_performance_validators_v0221"),
        (stage15a_perf_v0221_atomic, "stage15a_performance_atomic_publication_v0221"),
        (stage15a_perf_v0221_manifest, "stage15a_performance_package_manifest_v0221"),
        (stage15a_perf_v0221_runner, "stage15a_performance_runner_v0221"),
        (stage15a_perf_v0221_parallel_validator, "stage15a_performance_parallel_validator_v0221"),
    ]:
        source_document(conn, stage15a_perf_source_path, stage15a_perf_source_type, force_hash=True)


    # Stage 15A restart/resume and biology-ready output contract registration v0.1.0
    stage15a_restart_effective_at = "2026-08-08T13:40:00+00:00"
    stage15a_restart_run_id = "ENCSR307SHM_pilot100k_mm2splice_v1"
    stage15a_restart_stage_key = "15A_RESTART_RESUME_VALIDATION"
    stage15a_biology_stage_key = "BIOLOGY_READY_OUTPUT_AUDIT"

    stage15a_restart_root = project_root / "qc/15_stage15a_bam_to_final/ENCSR307SHM_pilot100k_mm2splice_v1/v0.2.3_restart_resume_100k"
    stage15a_restart_result_root = project_root / "results/15_stage15a_bam_to_final/ENCSR307SHM_pilot100k_mm2splice_v1/v0.2.3_restart_resume_100k"
    stage15a_restart_qc = stage15a_restart_root / "stage15a_restart_resume_100k.qc.tsv"
    stage15a_restart_prepare_qc = stage15a_restart_root / "stage15a_restart_prepare.qc.tsv"
    stage15a_restart_noop_qc = stage15a_restart_root / "stage15a_restart_noop.qc.tsv"
    stage15a_restart_comparison = stage15a_restart_root / "comparison/stage15a_performance_package_comparison.tsv"
    stage15a_restart_checkpoint_manifest = stage15a_restart_result_root / "checkpoints/checkpoint_manifest.tsv"
    stage15a_restart_package_manifest = stage15a_restart_result_root / "package_resume/package_manifest.tsv"
    stage15a_restart_runner = project_root / "scripts/rnatr_stage15a_restart_resume_100k_v0.1.0.py"
    stage15a_restart_installer = project_root / "scripts/rnatr_stage15a_restart_resume_100k_v010.sh"
    stage15a_biology_contract = project_root / "docs/stage15a/RNA_TR_Scout_Biology_ready_interpretation_output_contract_v0.1.0.md"
    stage15a_release_gates_v023 = project_root / "validation/release_gates_v0.2.3.tsv"

    def stage15a_metric_map(path: Path) -> dict[str, str]:
        header, rows = read_tsv(path)
        if header != ["metric", "value"]:
            raise SSOTError(f"expected metric/value TSV: {path}")
        return {row["metric"]: row["value"] for row in rows}

    stage15a_restart_values = stage15a_metric_map(stage15a_restart_qc)
    stage15a_restart_expected = {
        "stage_version": "rnatr_stage15a_restart_resume_100k_v0.1.0",
        "run_id": stage15a_restart_run_id,
        "source_performance_version": "v0.2.2.1_performance",
        "restart_scope": "FRESH_CALLER_CHECKPOINT_TO_FINAL_WITH_SELECTIVE_MATERIALIZER_RESUME",
        "checkpoint_rows_verified": "138",
        "checkpoint_negative_fixture_rejected": "PASS",
        "completed_caller_reused_on_resume": "true",
        "partial_package_published_before_resume": "false",
        "resumed_materializer_logical_parity": "true",
        "package_exact_logical_parity": "true",
        "package_exact_raw_parity": "true",
        "frozen_tsv_validators": "PASS",
        "parallel_exact_component_package_validator": "PASS",
        "frozen_package_validator_postpublication": "PASS",
        "negative_fixture_failure_parity": "PASS",
        "atomic_publication": "PASS",
        "active_pipeline_modified": "false",
        "ssot_modified": "false",
        "full_5_31m_run_started": "false",
        "restart_resume_validated": "true",
        "stage15a_overall_status": "IN_PROGRESS",
        "audit_status": "PASS",
        "next_gate": "BUILD_AND_RUN_DETERMINISTIC_250K_BAM_INPUT_SCALING_NOT_FULL_5_31M",
    }
    for stage15a_restart_metric, stage15a_restart_wanted in stage15a_restart_expected.items():
        stage15a_restart_observed = stage15a_restart_values.get(stage15a_restart_metric)
        if stage15a_restart_observed != stage15a_restart_wanted:
            raise SSOTError(
                f"Stage 15A restart QC mismatch {stage15a_restart_metric}: "
                f"{stage15a_restart_observed!r} != {stage15a_restart_wanted!r}"
            )

    stage15a_prepare_values = stage15a_metric_map(stage15a_restart_prepare_qc)
    for key, wanted in {
        "fresh_caller_logical_parity": "true",
        "partial_package_published": "false",
        "intentional_interruption_status": "PASS",
        "expected_exit_code": "75",
    }.items():
        if stage15a_prepare_values.get(key) != wanted:
            raise SSOTError(f"Stage 15A prepare QC mismatch {key}")

    stage15a_noop_values = stage15a_metric_map(stage15a_restart_noop_qc)
    for key, wanted in {
        "resume_mode": "NOOP_COMPLETE_CHECKPOINT",
        "package_unchanged": "true",
        "audit_status": "PASS",
    }.items():
        if stage15a_noop_values.get(key) != wanted:
            raise SSOTError(f"Stage 15A no-op QC mismatch {key}")

    stage15a_comparison_header, stage15a_comparison_rows = read_tsv(stage15a_restart_comparison)
    if len(stage15a_comparison_rows) != 10:
        raise SSOTError(f"expected 10 restart package comparison rows, found {len(stage15a_comparison_rows)}")
    for row in stage15a_comparison_rows:
        if row.get("header_equal") != "true" or row.get("raw_equal") != "true" or row.get("logical_equal") != "true":
            raise SSOTError(f"restart package parity failed for {row.get('role')}")

    ensure_stage(
        conn,
        stage15a_restart_stage_key,
        order=151.1,
        name="Stage 15A selective restart/resume validation",
        purpose="Validate checkpoint integrity, intentional interruption, selective materializer resume, exact package parity, no-op resume, and atomic publication for the 100k isolated performance candidate.",
        category="production_validation",
        status="IMPLEMENTED_WITH_GATE",
        notes="100k caller-checkpoint-to-final selective restart PASS. This does not establish arbitrary upstream-stage recovery, peak-memory scaling, or full 5.31M restartability.",
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO implementations(
            implementation_id,stage_key,version,script_path,script_sha256,
            validator_path,validator_sha256,package_version,parameters_json,
            lifecycle_status,supersedes_implementation_id,rationale,
            evidence_path,effective_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            "impl_stage15a_restart_resume_100k_v0_1_0",
            stage15a_restart_stage_key,
            "rnatr_stage15a_restart_resume_100k_v0.1.0",
            str(stage15a_restart_runner),
            sha256_file(stage15a_restart_runner),
            None,
            None,
            "evidence_schema_v0.4.2",
            json.dumps(
                {
                    "scope": "fresh_caller_checkpoint_to_final_selective_materializer_resume",
                    "source_performance_version": "v0.2.2.1_performance",
                    "intentional_exit_code": 75,
                    "checkpoint_rows": 138,
                    "adopted_upstream_shards": 12,
                    "resumed_materializer_shards": 1,
                    "second_resume_noop_required": True,
                    "full_5_31m_run": False,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            "PROVISIONAL",
            None,
            "Validated selective 100k restart/resume with exact raw and logical package parity, negative checkpoint rejection, no partial publication, atomic publication, and an unchanged no-op second resume. Full-scale and arbitrary upstream-stage restart remain open.",
            str(stage15a_restart_qc),
            stage15a_restart_effective_at,
        ),
    )

    add_decision(
        conn,
        key="stage15a_restart_resume_scope_v0_1_0",
        category="production_validation",
        title="Accept selective 100k restart/resume and retain full-scale restart gate",
        statement="Stage 15A v0.1.0 passes fresh-caller-checkpoint-to-final selective restart/resume for the 100k exact-parity performance candidate. G07 remains OPEN because arbitrary upstream-stage recovery, peak-memory behavior, and full-scale restartability are not yet validated.",
        status="ACTIVE",
        confidence="HIGH",
        rationale="An intentional exit 75 occurred after a fresh caller checkpoint and before one materializer shard; no partial final package was published. Resume verified 138 checkpoint rows, reused completed work, rebuilt a byte-identical package, and a second resume was a no-op.",
        evidence_path=str(stage15a_restart_qc),
        effective_at=stage15a_restart_effective_at,
    )

    add_interpretation(
        conn,
        key="stage15a_restart_resume_100k_scope",
        fact="The 100k restart audit completed with checkpoint integrity, negative-fixture rejection, selective reuse, exact package parity, atomic publication, and no-op second resume all PASS.",
        interpretation="The v0.2.2.1 production candidate has a validated checkpoint-to-final restart path suitable for proceeding to deterministic 250k scaling.",
        do_not="Do not interpret this as validation of arbitrary interruption at 11b/11d3/11e, full-scale memory safety, empirical 5.31M restartability, Stage 15A completion, or authorization for the full 5.31M run.",
        confidence="HIGH",
        evidence_path=str(stage15a_restart_qc),
        evidence_metrics={
            "checkpoint_rows_verified": 138,
            "package_exact_logical_parity": True,
            "package_exact_raw_parity": True,
            "partial_package_published_before_resume": False,
            "restart_resume_validated": True,
        },
        status="ACTIVE",
        effective_at=stage15a_restart_effective_at,
    )

    add_contract(
        conn,
        key="stage15a_restart_resume_v0_1_0",
        name="Stage 15A selective restart/resume contract v0.1.0",
        state="100K_SELECTIVE_RESTART_PASS_250K_AND_FULL_SCALE_OPEN",
        statement="The current candidate must verify checkpoint hashes, reject corrupt checkpoints, avoid partial publication, reuse completed caller/materializer shards, rebuild an exact-parity package, publish atomically, and produce an unchanged no-op second resume. The validated scope is caller-checkpoint-to-final at 100k, not arbitrary-stage or full-scale restart.",
        implementation_id="impl_stage15a_restart_resume_100k_v0_1_0",
        evidence_path=str(stage15a_restart_qc),
    )

    add_contract(
        conn,
        key="stage15a_performance_candidate_v0221",
        name="Stage 15A performance candidate v0.2.2.1",
        state="100K_PROJECTED_60MIN_PASS_RESTART_PASS_250K_OPEN",
        statement="v0.2.2.1 remains the current exact-parity isolated performance candidate. Its 65.763639-second 100k timer projects to 58.230371 minutes for 5.31M and its selective 100k caller-checkpoint-to-final restart path is validated. Deterministic 250k/intermediate scaling, arbitrary upstream-stage recovery, empirical full-scale runtime, and the 30-minute target remain open.",
        implementation_id="impl_stage15a_performance_v0_2_2_1",
        evidence_path=str(stage15a_restart_qc),
    )

    conn.execute(
        """
        INSERT OR REPLACE INTO limitations(
            limitation_key,statement,severity,status,mitigation,evidence_path,effective_at
        ) VALUES(?,?,?,?,?,?,?)
        """,
        (
            "STAGE15A_RESTART_SCOPE_IS_SELECTIVE_100K",
            "Restart/resume is validated only from a fresh caller checkpoint through selective materializer resume, merge, validation, and atomic publication at 100k. Arbitrary interruption at upstream stages, peak-memory scaling, and full 5.31M restartability are not established.",
            "HIGH",
            "ACTIVE",
            "Run deterministic 250k scaling with memory and temporary-byte capture; extend checkpoint coverage before any full-depth execution.",
            str(stage15a_restart_qc),
            stage15a_restart_effective_at,
        ),
    )

    conn.execute(
        """
        INSERT OR REPLACE INTO open_questions(
            question_key,question,priority,status,blocking,next_action,evidence_path,effective_at
        ) VALUES(?,?,?,?,?,?,?,?)
        """,
        (
            "GENERAL_CALLER_PRODUCTION_INTEGRATION",
            "Can the exact-parity Stage 15A candidate preserve its projected <=60-minute runtime, determinism, bounded memory, artifact completeness, and restart contract as BAM input increases?",
            "CRITICAL",
            "OPEN",
            1,
            "Run deterministic 250k BAM-input scaling next. Capture stage wall time, peak RSS, temporary bytes, alignment/candidate/window/output complexity variables, package reproducibility, and checkpoint behavior. Do not run full 5.31M or change current_pipeline.",
            str(stage15a_restart_qc),
            stage15a_restart_effective_at,
        ),
    )

    ensure_stage(
        conn,
        stage15a_biology_stage_key,
        order=152.0,
        name="Biology-ready and interpretation-ready output audit",
        purpose="Preserve lossless molecule-level repeat architecture while adding read-keyed transcript, haplotype, observability, and molecule-independence sidecars plus traceable sample-level interpretation outputs.",
        category="biology_output_contract",
        status="PAUSED",
        notes="Contract designed and registered. Implementation begins after Stage 15A scaling architecture stabilizes; G20-G23 remain OPEN and are blocking for biology-ready v1/cohort triage, not for the immediate 250k performance benchmark.",
    )

    add_decision(
        conn,
        key="biology_ready_core_sidecar_separation_v0_1_0",
        category="biology_output_architecture",
        title="Keep schema v0.4.2 core repeat tables stable and add read-keyed biology sidecars",
        statement="The v0.4.2 core 5-table package remains the repeat-measurement source of truth. Transcript/isoform, haplotype, observability, and duplicate/molecule-independence states will be added as versioned read/evidence-keyed sidecars rather than by inflating or rewriting the core tables.",
        status="ACTIVE",
        confidence="HIGH",
        rationale="The core already preserves repeat length, purity, LPS, segments, interruptions, alignment discordance, geometry, and censoring. The missing biology dimensions have different provenance, update cadence, missingness, and validation requirements and therefore belong in independently versioned sidecars.",
        evidence_path=str(stage15a_biology_contract),
        effective_at=stage15a_restart_effective_at,
    )

    add_decision(
        conn,
        key="purpose_specific_candidate_ranking_lanes_v0_1_0",
        category="interpretation_output_architecture",
        title="Use purpose-specific ranking lanes rather than one universal score",
        statement="Candidate triage will maintain separate KNOWN_DISEASE, EXPANSION_DISCOVERY, RNA_PROCESSING, REPEAT_HETEROGENEITY, HAPLOTYPE_CONTROLLED, and TECHNICAL_CONFIDENCE lanes. Known disease repeats are retained independently of generic ranking thresholds.",
        status="ACTIVE",
        confidence="HIGH",
        rationale="Expansion discovery, RNA processing, heterogeneity, phase-controlled evidence, and technical confidence answer different scientific questions and should not be collapsed into a single opaque score.",
        evidence_path=str(stage15a_biology_contract),
        effective_at=stage15a_restart_effective_at,
    )

    add_interpretation(
        conn,
        key="core_v042_repeat_ready_not_biology_ready",
        fact="The v0.4.2 core package losslessly preserves read-level repeat calls/events, repeat length state, purity, LPS, compound segments, structured interruptions, discordance operations, geometry, and censoring, but it does not yet materialize transcript/isoform, haplotype, explicit observability, molecule-independence, sample-locus summary, multi-lane ranking, or dossier outputs.",
        interpretation="The current output is repeat-ready and suitable as the immutable substrate for biology enrichment, but it is not yet biology-ready or interpretation-ready for large-cohort triage.",
        do_not="Do not call read_id an independent biological molecule without evidence, infer haplotypes or allele meaning without phase evidence, treat sidecar missingness as a negative result, or replace molecule-level distributions with summary-only output.",
        confidence="HIGH",
        evidence_path=str(stage15a_biology_contract),
        evidence_metrics={
            "core_table_count": 5,
            "biology_sidecar_count_designed": 4,
            "ranking_lane_count_designed": 6,
            "biology_ready_status": "NOT_IMPLEMENTED",
        },
        status="ACTIVE",
        effective_at=stage15a_restart_effective_at,
    )

    add_contract(
        conn,
        key="biology_ready_read_keyed_sidecars_v0_1_0",
        name="Biology-ready read-keyed sidecar contract v0.1.0",
        state="DESIGNED_NOT_IMPLEMENTED",
        statement="Versioned sidecars must provide transcript/isoform state, haplotype state, observability, and molecule independence with explicit missingness and provenance, joinable by read_id/evidence_id without altering the core repeat source of truth.",
        implementation_id=None,
        evidence_path=str(stage15a_biology_contract),
    )
    add_contract(
        conn,
        key="interpretation_hierarchy_v0_1_0",
        name="Molecule-to-dossier interpretation hierarchy v0.1.0",
        state="DESIGNED_NOT_IMPLEMENTED",
        statement="Interpretation proceeds from raw repeat evidence to molecule_repeat_state, censor-aware sample_locus_summary, purpose-specific ranking lanes, and researcher-facing dossier. Molecule-level distributions and reverse traceability are mandatory.",
        implementation_id=None,
        evidence_path=str(stage15a_biology_contract),
    )

    conn.execute(
        """
        INSERT OR REPLACE INTO limitations(
            limitation_key,statement,severity,status,mitigation,evidence_path,effective_at
        ) VALUES(?,?,?,?,?,?,?)
        """,
        (
            "CORE_V042_NOT_YET_BIOLOGY_OR_INTERPRETATION_READY",
            "The core package does not yet contain versioned transcript/isoform, haplotype, explicit observability, or molecule-independence sidecars and does not yet generate sample-locus summaries, purpose-specific ranking lanes, or researcher-facing dossiers.",
            "HIGH",
            "ACTIVE",
            "Complete the formal output audit and implement G20-G23 after Stage 15A scaling architecture stabilizes, while preserving the core 5-table package and read-level distributions.",
            str(stage15a_biology_contract),
            stage15a_restart_effective_at,
        ),
    )

    conn.execute(
        """
        INSERT OR REPLACE INTO open_questions(
            question_key,question,priority,status,blocking,next_action,evidence_path,effective_at
        ) VALUES(?,?,?,?,?,?,?,?)
        """,
        (
            "BIOLOGY_READY_INTERPRETATION_OUTPUT_AUDIT",
            "Can the final output support same-haplotype molecule-level repeat heterogeneity, repeat-to-isoform/splicing association, observability-aware inference, molecule-independence-aware support, purpose-specific triage, and fully traceable researcher dossiers without losing core read-level repeat information?",
            "CRITICAL",
            "OPEN",
            1,
            "After deterministic scaling stabilizes the production architecture, audit the current core package against G20-G23, freeze sidecar schemas and validators, then implement molecule_repeat_state, sample_locus_summary, ranking lanes, and dossier traceability.",
            str(stage15a_biology_contract),
            stage15a_restart_effective_at,
        ),
    )

    for stage15a_restart_source_path, stage15a_restart_source_type in [
        (stage15a_restart_qc, "stage15a_restart_resume_qc"),
        (stage15a_restart_prepare_qc, "stage15a_restart_prepare_qc"),
        (stage15a_restart_noop_qc, "stage15a_restart_noop_qc"),
        (stage15a_restart_comparison, "stage15a_restart_package_comparison"),
        (stage15a_restart_checkpoint_manifest, "stage15a_restart_checkpoint_manifest"),
        (stage15a_restart_package_manifest, "stage15a_restart_package_manifest"),
        (stage15a_restart_runner, "stage15a_restart_runner"),
        (stage15a_restart_installer, "stage15a_restart_installer"),
        (stage15a_biology_contract, "biology_ready_output_contract"),
        (stage15a_release_gates_v023, "release_gates"),
    ]:
        source_document(conn, stage15a_restart_source_path, stage15a_restart_source_type, force_hash=True)

    for metric_name, metric_value, metric_unit in [
        ("restart_resume_validated", 1, None),
        ("restart_checkpoint_rows_verified", 138, "rows"),
        ("restart_materializer_resume_seconds", float(stage15a_restart_values["materializer_resume_seconds"]), "seconds"),
        ("restart_validator_seconds", float(stage15a_restart_values["validator_seconds"]), "seconds"),
        ("restart_package_exact_raw_parity", 1, None),
        ("restart_noop_manifest_unchanged", 1, None),
    ]:
        add_current_metric(
            conn,
            run_id=stage15a_restart_run_id,
            stage_key=stage15a_restart_stage_key,
            name=metric_name,
            value=metric_value,
            source_path=str(stage15a_restart_qc),
            unit=metric_unit,
        )


    # Stage 15A 250k scaling and post-250k architecture audit registration v0.1.0
    stage15a_250k_effective_at = "2026-08-09T00:00:00+00:00"
    stage15a_250k_run_id = "ENCSR307SHM_stage15a250k_seed20260808_mm2splice_v1"
    stage15a_250k_parent_run_id = "ENCSR307SHM_pilot100k_mm2splice_v1"
    stage15a_250k_stage_key = "15A_DETERMINISTIC_SCALING"
    stage15a_arch_stage_key = "ARCHITECTURE_CONSISTENCY_AUDIT"

    stage15a_250k_root = project_root / "qc/15_stage15a_bam_to_final/ENCSR307SHM_stage15a250k_seed20260808_mm2splice_v1/v0.1.2_250k_scaling"
    stage15a_250k_result_root = project_root / "results/15_stage15a_bam_to_final/ENCSR307SHM_stage15a250k_seed20260808_mm2splice_v1/v0.1.2_250k_scaling"
    stage15a_250k_qc = stage15a_250k_root / "stage15a_scaling_250k.qc.tsv"
    stage15a_250k_stage_model = stage15a_250k_root / "stage15a_scaling_250k_stage_model.tsv"
    stage15a_250k_package_repro = stage15a_250k_root / "stage15a_scaling_250k_package_reproducibility.tsv"
    stage15a_250k_caller_repro = stage15a_250k_root / "stage15a_scaling_250k_caller_reproducibility.tsv"
    stage15a_250k_nested = stage15a_250k_root / "stage15a_scaling_250k_nested_100k_package_parity.tsv"
    stage15a_250k_checkpoint_original = stage15a_250k_root / "stage15a_scaling_250k_checkpoint_reproducibility.tsv"
    stage15a_250k_checkpoint_a = stage15a_250k_root / "replicate_A/stage15a_scaling_250k_checkpoint_manifest.tsv"
    stage15a_250k_checkpoint_b = stage15a_250k_root / "replicate_B/stage15a_scaling_250k_checkpoint_manifest.tsv"

    stage15a_arch_root = project_root / "qc/15_architecture_consistency_audit/ENCSR307SHM_stage15a250k_seed20260808_mm2splice_v1/post_250k_v0.1.1"
    stage15a_arch_qc = stage15a_arch_root / "architecture_consistency_audit.qc.tsv"
    stage15a_arch_findings = stage15a_arch_root / "architecture_findings.tsv"
    stage15a_arch_checkpoint = stage15a_arch_root / "checkpoint_logical_reproducibility.tsv"
    stage15a_arch_lifecycle = stage15a_arch_root / "script_lifecycle_ledger.tsv"
    stage15a_arch_report = project_root / "docs/stage15a/RNA_TR_Scout_Architecture_consistency_audit_post250k_v0.1.1.md"
    stage15a_arch_contract = project_root / "docs/stage15a/RNA_TR_Scout_Architecture_consistency_audit_contract_v0.1.0.md"
    stage15a_arch_script = project_root / "scripts/rnatr_stage15a_architecture_audit_post250k_v0.1.1.py"
    stage15a_release_gates_v024 = project_root / "validation/release_gates_v0.2.4.tsv"

    stage15a_scaler_v010 = project_root / "scripts/rnatr_stage15a_run_scaling_250k_v0.1.0.py"
    stage15a_scaler_v011 = project_root / "scripts/rnatr_stage15a_run_scaling_250k_v0.1.1.py"
    stage15a_scaler_v012 = project_root / "scripts/rnatr_stage15a_run_scaling_250k_v0.1.2.py"
    stage15a_fast11e_scaling = project_root / "scripts/rnatr_stage15a_fast_motif_jobs_scaling_v0.2.2.2.py"
    stage15a_candidate_extractor = project_root / "scripts/rnatr_stage15a_extract_candidate_fastq_v0.1.0.py"
    stage15a_prepare_250k = project_root / "scripts/rnatr_stage15a_prepare_250k_input_v0.1.0.py"
    stage15a_scaling_installer_v010 = project_root / "scripts/rnatr_stage15a_scaling_250k_v010.sh"

    stage15a_250k_expected_sha = {
        stage15a_250k_qc: "a2504e27c84ca3d77a53c4484d977042259c2f92caeb4962479b065d80caffea",
        stage15a_250k_stage_model: "b039c012e484971df1a653da470669fe427c7abaea7936da16615e20b3ef110d",
        stage15a_250k_package_repro: "88d2964250995734dc927902b2fb8fb1c6aaaf32dc885ecccd59af0a131e7af6",
        stage15a_250k_caller_repro: "85ed21187acd95f4422fbe089f4a33a974337ef3dddec2c7c713ec56ca01c790",
        stage15a_250k_nested: "5f013c1f8be6997beb1b58c377641701e48d04b7b0b26405344aef7209fa766f",
        stage15a_250k_checkpoint_original: "bd7daff866bf66db06c79f4aec8bc8e756db8631dd2fc57d9681340c6ccc5523",
        stage15a_250k_checkpoint_a: "4eb500026b95700de95877421801fc312bcba4f423d20d1605c9d67165228cae",
        stage15a_250k_checkpoint_b: "9763f5ac94da6fdf9c2ada92687681440c0cea054920a567cfb21e2daf8a2b32",
        stage15a_arch_qc: "949bd376480c1deaf3bb55b12f190b1773c9244ea37203412d28443cd75aafda",
        stage15a_arch_findings: "db7a4b3bc93a2a947056a8b32f3f102b19612030421365f6adc8079998c51683",
        stage15a_arch_checkpoint: "caddd55fbfaeb3be6277f9bd57d35b732e022f626a1c4dcc29ee5f2d1ce5a39b",
        stage15a_arch_lifecycle: "906e3d866e13b581c0eae5af1ab26f508d82113cc95ebb0a48235d7759824b72",
        stage15a_arch_report: "a0e81e495f154e2f8fafb76334e444775f7559766e9d077a185c87a0a6b912ab",
        stage15a_arch_contract: "5ff06d5806b700181447fd4a3406d534ac0c4136cda90adf426f1e0a0fe6b449",
        stage15a_arch_script: "02435c9813470a4590299875106f596e0ccab7830f040e38a63810c847d0d843",
        stage15a_release_gates_v024: "90ecf0c5f9cf0ba68361a5538d98aabc63afbe063fec5ee1060a7d0e508cce87",
        stage15a_scaler_v010: "7ce76d5867275b875e67bcff9020c1f1359ab0f2183604628d01538794df02de",
        stage15a_scaler_v011: "569bd8ea30c1df19e9ce3899347e366e1b487c964ed01bb2b167b646deede9a6",
        stage15a_scaler_v012: "dbc78c93087bf5bc74d6fea2c47b1c3d6c2986b62de9e7a7e73c21993facb375",
        stage15a_fast11e_scaling: "3e36454a515cd8c0411957000099867b582ae7d2bef78b7fe2ebd61bf09f4dc4",
        stage15a_candidate_extractor: "b4ecf4e5ecf1a1c0e57e96cb30f560a21230e1463777bdbb0e36601918a9abbf",
        stage15a_prepare_250k: "caab4e711265b1ed7572cfb69fc8b4472b81e2c9270e78b6caee33560e4966bf",
        stage15a_scaling_installer_v010: "d63655201f30afc532f31033c3107a826ccce8d4c58347ca0413b4022238d246",
    }
    for stage15a_path, stage15a_expected_sha in stage15a_250k_expected_sha.items():
        if not stage15a_path.is_file():
            raise SSOTError(f"Stage15A 250k/audit artifact missing: {stage15a_path}")
        stage15a_observed_sha = sha256_file(stage15a_path)
        if stage15a_observed_sha != stage15a_expected_sha:
            raise SSOTError(
                f"Stage15A 250k/audit artifact SHA mismatch: {stage15a_path}: "
                f"{stage15a_observed_sha} != {stage15a_expected_sha}"
            )

    def stage15a_250k_metric_map(path: Path) -> dict[str, str]:
        header, rows = read_tsv(path)
        if header != ["metric", "value"]:
            raise SSOTError(f"expected metric/value TSV: {path}")
        return {row["metric"]: row["value"] for row in rows}

    stage15a_250k_values = stage15a_250k_metric_map(stage15a_250k_qc)
    stage15a_250k_expected = {
        "stage_version": "rnatr_stage15a_deterministic_250k_scaling_v0.1.2",
        "external_run_id": stage15a_250k_run_id,
        "input_reads": "250000",
        "package_exact_logical_reproducibility": "true",
        "package_exact_raw_reproducibility": "true",
        "caller_hashseed_logical_reproducibility": "true",
        "checkpoint_manifest_reproducibility": "true",
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
    for stage15a_metric, stage15a_wanted in stage15a_250k_expected.items():
        stage15a_observed = stage15a_250k_values.get(stage15a_metric)
        if stage15a_observed != stage15a_wanted:
            raise SSOTError(
                f"Stage15A 250k QC mismatch {stage15a_metric}: "
                f"{stage15a_observed!r} != {stage15a_wanted!r}"
            )

    stage15a_arch_values = stage15a_250k_metric_map(stage15a_arch_qc)
    stage15a_arch_expected = {
        "audit_version": "rnatr_stage15a_architecture_consistency_audit_post250k_v0.1.1",
        "run_id": stage15a_250k_run_id,
        "deterministic_250k_scaling": "PASS",
        "original_checkpoint_reproducibility_claim_supported": "false",
        "replacement_checkpoint_logical_reproducibility": "true",
        "checkpoint_logical_difference_rows": "0",
        "active_pipeline_stage_count": "11",
        "active_pipeline_modified": "false",
        "core_schema_modified": "false",
        "ssot_modified": "false",
        "ssot_integrity": "ok",
        "ssot_foreign_key_failures": "0",
        "release_gate_G06": "OPEN",
        "release_gate_G07": "OPEN",
        "release_gate_G17": "PASS",
        "release_gates_G20_G23": "OPEN",
        "blocking_conflicts": "0",
        "review_items": "3",
        "open_items": "2",
        "full_5_31m_run_started": "false",
        "architecture_audit_status": "REVIEW",
    }
    for stage15a_metric, stage15a_wanted in stage15a_arch_expected.items():
        stage15a_observed = stage15a_arch_values.get(stage15a_metric)
        if stage15a_observed != stage15a_wanted:
            raise SSOTError(
                f"Stage15A architecture audit mismatch {stage15a_metric}: "
                f"{stage15a_observed!r} != {stage15a_wanted!r}"
            )

    stage15a_package_header, stage15a_package_rows = read_tsv(stage15a_250k_package_repro)
    if len(stage15a_package_rows) != 10:
        raise SSOTError(f"expected 10 250k package reproducibility rows, found {len(stage15a_package_rows)}")
    for row in stage15a_package_rows:
        if row.get("raw_equal") != "true" or row.get("logical_equal") != "true":
            raise SSOTError(f"250k package reproducibility failed: {row.get('artifact')}")

    _, stage15a_caller_rows = read_tsv(stage15a_250k_caller_repro)
    if len(stage15a_caller_rows) != 12 or any(row.get("logical_equal") != "true" for row in stage15a_caller_rows):
        raise SSOTError("250k caller reproducibility table failed")

    _, stage15a_nested_rows = read_tsv(stage15a_250k_nested)
    if len(stage15a_nested_rows) != 5:
        raise SSOTError(f"expected 5 nested-100k rows, found {len(stage15a_nested_rows)}")
    for row in stage15a_nested_rows:
        if row.get("header_equal") != "true" or row.get("nested_anchor_exact_equal") != "true":
            raise SSOTError(f"nested 100k parity failed: {row.get('table')}")

    _, stage15a_checkpoint_rows = read_tsv(stage15a_arch_checkpoint)
    if len(stage15a_checkpoint_rows) != 157:
        raise SSOTError(f"expected 157 replacement checkpoint rows, found {len(stage15a_checkpoint_rows)}")
    for row in stage15a_checkpoint_rows:
        if row.get("logical_equal") != "true" or row.get("status") != "PASS":
            raise SSOTError(f"replacement checkpoint reproducibility failed: {row.get('role')}/{row.get('shard')}")

    _, stage15a_finding_rows = read_tsv(stage15a_arch_findings)
    if any(row.get("status") == "CONFLICT" for row in stage15a_finding_rows):
        raise SSOTError("post-250k architecture audit contains a blocking CONFLICT")

    stage15a_parent = conn.execute(
        "SELECT dataset_id FROM runs WHERE run_id=?", (stage15a_250k_parent_run_id,)
    ).fetchone()
    if stage15a_parent is None:
        raise SSOTError("parent 100k run is not registered")

    ensure_stage(
        conn,
        stage15a_250k_stage_key,
        order=151.2,
        name="Stage 15A deterministic intermediate scaling",
        purpose="Measure deterministic BAM-to-final scaling, package/caller/checkpoint reproducibility, memory, and artifact growth before any full 5.31M run.",
        category="production_validation",
        status="IMPLEMENTED_WITH_GATE",
        notes="250k exact package/caller reproducibility PASS. Linear 5.31M projection is 59.858798 minutes with only 0.141202-minute margin; deterministic 500k remains mandatory and G06/G07 remain OPEN.",
    )
    ensure_stage(
        conn,
        stage15a_arch_stage_key,
        order=151.3,
        name="Architecture consistency audit",
        purpose="Cross-audit SSOT, active paths, frozen schema/contracts, performance gates, validation/restart scope, biology roadmap, and script lifecycle at major checkpoints.",
        category="governance_validation",
        status="IMPLEMENTED_WITH_GATE",
        notes="Post-250k audit v0.1.1 completed with REVIEW, zero blocking conflicts, three review items, and two open items. Pre-biology and pre-release-candidate audits remain required.",
    )

    ensure_run(
        conn,
        stage15a_250k_run_id,
        dataset_id=stage15a_parent[0],
        parent_run_id=stage15a_250k_parent_run_id,
        run_role="DETERMINISTIC_SCALING_BENCHMARK",
        pipeline_version="rnatr_stage15a_deterministic_250k_scaling_v0.1.2",
        status="PASS_WITH_OPEN_GATES",
        root_path=str(stage15a_250k_result_root),
        notes="Nested deterministic 250k subset; two hash-seed replicates; full 5.31M not run; active pipeline unchanged.",
    )

    stage15a_impl_rows = [
        ("impl_stage15a_scaling_250k_v0_1_0", stage15a_250k_stage_key, "rnatr_stage15a_deterministic_250k_scaling_v0.1.0", stage15a_scaler_v010, "SUPERSEDED", None, "Initial 250k runner; stopped at a 100k-only aggregate fast-11e guard."),
        ("impl_stage15a_scaling_250k_v0_1_1", stage15a_250k_stage_key, "rnatr_stage15a_deterministic_250k_scaling_v0.1.1", stage15a_scaler_v011, "SUPERSEDED", "impl_stage15a_scaling_250k_v0_1_0", "Dynamic fast-11e guard fix; outer invocation omitted --orchestrate and stopped before replicate processing."),
        ("impl_stage15a_scaling_250k_v0_1_2", stage15a_250k_stage_key, "rnatr_stage15a_deterministic_250k_scaling_v0.1.2", stage15a_scaler_v012, "PROVISIONAL", "impl_stage15a_scaling_250k_v0_1_1", "Current deterministic 250k scaling implementation with exact final-package and caller reproducibility."),
        ("impl_stage15a_fast11e_scaling_v0_2_2_2", stage15a_250k_stage_key, "rnatr_stage15a_fast_motif_jobs_scaling_v0.2.2.2", stage15a_fast11e_scaling, "PROVISIONAL", None, "Scaling-aware shared-catalog 11e component with dynamic expected rows/reads."),
        ("impl_stage15a_candidate_fastq_v0_1_0", stage15a_250k_stage_key, "rnatr_stage15a_extract_candidate_fastq_v0.1.0", stage15a_candidate_extractor, "PROVISIONAL", None, "Current candidate-FASTQ extraction support component used by deterministic scaling."),
        ("impl_stage15a_prepare_250k_input_v0_1_0", stage15a_250k_stage_key, "rnatr_stage15a_prepare_250k_input_v0.1.0", stage15a_prepare_250k, "REFERENCE_SUPPORT", None, "Validated deterministic nested-250k FASTQ/BAM preparation and mapping-input provenance component."),
        ("impl_stage15a_scaling_installer_v0_1_0", stage15a_250k_stage_key, "rnatr_stage15a_scaling_250k_bundle_v0.1.0", stage15a_scaling_installer_v010, "SUPERSEDED", None, "Historical installer retained for provenance; its scientific runner was superseded by v0.1.2."),
        ("impl_stage15a_archaudit_post250k_v0_1_1", stage15a_arch_stage_key, "rnatr_stage15a_architecture_consistency_audit_post250k_v0.1.1", stage15a_arch_script, "REFERENCE_AUDIT", None, "Read-only post-250k cross-domain architecture audit and checkpoint reproducibility amendment."),
    ]
    for impl_id, stage_key, version, script_path, lifecycle, supersedes, rationale in stage15a_impl_rows:
        conn.execute(
            """
            INSERT OR REPLACE INTO implementations(
                implementation_id,stage_key,version,script_path,script_sha256,
                validator_path,validator_sha256,package_version,parameters_json,
                lifecycle_status,supersedes_implementation_id,rationale,
                evidence_path,effective_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                impl_id, stage_key, version, str(script_path), sha256_file(script_path),
                None, None, "evidence_schema_v0.4.2",
                json.dumps({"full_5_31m_run": False, "active_pipeline_switch": False}, sort_keys=True),
                lifecycle, supersedes, rationale,
                str(stage15a_arch_qc if stage_key == stage15a_arch_stage_key else stage15a_250k_qc),
                stage15a_250k_effective_at,
            ),
        )

    conn.execute(
        """
        INSERT OR REPLACE INTO run_stages(
            run_id,stage_key,implementation_id,attempt_tag,status,command_text,
            qc_path,qc_status,started_at,ended_at,notes
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            stage15a_250k_run_id, stage15a_250k_stage_key,
            "impl_stage15a_scaling_250k_v0_1_2", "v0.1.2_replicates_A_B",
            "PASS", None, str(stage15a_250k_qc), "PASS",
            None, stage15a_250k_effective_at,
            "Two deterministic hash-seed replicates; exact package/caller reproducibility; 500k remains next gate.",
        ),
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO run_stages(
            run_id,stage_key,implementation_id,attempt_tag,status,command_text,
            qc_path,qc_status,started_at,ended_at,notes
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            stage15a_250k_run_id, stage15a_arch_stage_key,
            "impl_stage15a_archaudit_post250k_v0_1_1", "post_250k_v0.1.1",
            "REVIEW", None, str(stage15a_arch_qc), "REVIEW",
            None, stage15a_250k_effective_at,
            "Zero blocking conflicts; checkpoint amendment PASS; three review and two open items remain.",
        ),
    )

    stage15a_250k_metrics = [
        ("input_reads", stage15a_250k_values["input_reads"], "reads"),
        ("bam_to_final_conservative_seconds", stage15a_250k_values["conservative_250k_bam_to_final_cold_seconds"], "seconds"),
        ("linear_5_31m_projection_minutes", stage15a_250k_values["conservative_linear_5_31m_projection_minutes"], "minutes"),
        ("hard_ceiling_margin_minutes", stage15a_250k_values["five_m_hard_ceiling_margin_minutes"], "minutes"),
        ("per_read_normalized_scaling_factor", stage15a_250k_values["per_read_normalized_scaling_factor"], None),
        ("alignment_records", stage15a_250k_values["alignment_records"], "rows"),
        ("candidate_rows", stage15a_250k_values["candidate_rows"], "rows"),
        ("candidate_reads", stage15a_250k_values["candidate_reads"], "reads"),
        ("candidate_window_bases", stage15a_250k_values["total_candidate_window_bases"], "bp"),
        ("caller_attempt_rows", stage15a_250k_values["caller_attempt_rows"], "rows"),
        ("caller_called_rows", stage15a_250k_values["caller_called_rows"], "rows"),
        ("repeat_event_rows", stage15a_250k_values["repeat_event_rows"], "rows"),
        ("maximum_observed_stage_rss_kbytes", max(float(stage15a_250k_values["replicate_A_maximum_observed_stage_rss_kbytes"]), float(stage15a_250k_values["replicate_B_maximum_observed_stage_rss_kbytes"])), "kB"),
        ("peak_temporary_and_output_bytes", max(float(stage15a_250k_values["replicate_A_peak_temporary_and_output_bytes"]), float(stage15a_250k_values["replicate_B_peak_temporary_and_output_bytes"])), "bytes"),
        ("package_exact_raw_reproducibility", 1, None),
        ("package_exact_logical_reproducibility", 1, None),
        ("caller_hashseed_logical_reproducibility", 1, None),
        ("nested_100k_package_exact_parity", 1, None),
        ("replacement_checkpoint_logical_reproducibility", 1, None),
        ("original_checkpoint_claim_supported", 0, None),
    ]
    for metric_name, metric_value, metric_unit in stage15a_250k_metrics:
        add_current_metric(
            conn, run_id=stage15a_250k_run_id, stage_key=stage15a_250k_stage_key,
            name=metric_name, value=metric_value, source_path=str(stage15a_250k_qc), unit=metric_unit,
        )
    for metric_name, metric_value in [
        ("blocking_conflicts", stage15a_arch_values["blocking_conflicts"]),
        ("review_items", stage15a_arch_values["review_items"]),
        ("open_items", stage15a_arch_values["open_items"]),
        ("architecture_audit_status", stage15a_arch_values["architecture_audit_status"]),
        ("replacement_checkpoint_logical_reproducibility", 1),
    ]:
        add_current_metric(
            conn, run_id=stage15a_250k_run_id, stage_key=stage15a_arch_stage_key,
            name=metric_name, value=metric_value, source_path=str(stage15a_arch_qc),
        )

    add_decision(
        conn, key="stage15a_deterministic_250k_scaling_acceptance_v0_1_2",
        category="performance_validation", title="Accept deterministic 250k scaling as intermediate exact-parity evidence",
        statement="Stage15A v0.1.2 passes two-replicate 250k final-package and caller reproducibility and exact nested-100k parity. It does not close G06 or authorize full 5.31M because the linear 60-minute margin is only 0.141202 minutes.",
        status="ACTIVE", confidence="HIGH",
        rationale="The benchmark is deterministic and exact-parity, but the observed scaling margin is too small to absorb larger-scale nonlinearity.",
        evidence_path=str(stage15a_250k_qc), effective_at=stage15a_250k_effective_at,
    )
    add_decision(
        conn, key="stage15a_checkpoint_reproducibility_amendment_v0_1_0",
        category="validation_contract", title="Supersede unsupported 250k checkpoint reproducibility claim with role-by-shard logical audit",
        statement="The original v0.1.2 QC field checkpoint_manifest_reproducibility=true was not supported by its implementation because the checker validated each replicate separately without A/B comparison. The historical QC is preserved and superseded by a 157-row role×shard logical comparison with zero differences.",
        status="ACTIVE", confidence="HIGH",
        rationale="Historical evidence must be amended rather than silently rewritten. Compressed deterministic TSVs are compared by decompressed bytes, runtime QC by timing-excluded semantic metrics, and other deterministic artifacts by raw bytes.",
        evidence_path=str(stage15a_arch_checkpoint), effective_at=stage15a_250k_effective_at,
    )
    add_decision(
        conn, key="architecture_consistency_audit_cadence_v0_1_0",
        category="architecture_governance", title="Require cross-domain Architecture consistency audits at major checkpoints",
        statement="Run formal audits after 250k scaling, before biology-layer implementation, and before release candidate. Audit SSOT, active paths, schema/contracts, performance gates, restart/validation scope, biology roadmap, and script lifecycle for contradictions, obsolete remnants, implementation-state inflation, frozen-contract drift, and planned-item omissions.",
        status="ACTIVE", confidence="HIGH",
        rationale="The development graph is complex enough that local stage PASS does not guarantee global architectural consistency.",
        evidence_path=str(stage15a_arch_contract), effective_at=stage15a_250k_effective_at,
    )
    add_decision(
        conn, key="stage15a_internal_run_id_compatibility_alias_v0_1_0",
        category="provenance", title="Treat the internal 100k run ID used inside the 250k scaling graph as a temporary compatibility alias",
        statement="The external run identity is the deterministic 250k run. Internal component paths that still use ENCSR307SHM_pilot100k_mm2splice_v1 are a compatibility shim only and must be encapsulated or removed before release candidate.",
        status="ACTIVE", confidence="HIGH",
        rationale="The alias did not alter scientific rows or package identity, but it can confuse provenance and must not become a release contract.",
        evidence_path=str(stage15a_arch_qc), effective_at=stage15a_250k_effective_at,
    )

    add_interpretation(
        conn, key="stage15a_250k_scaling_margin_interpretation",
        fact="The conservative 250k BAM-to-final time is 169.006841 seconds and linearly projects to 59.858798 minutes for 5,312,696 reads, leaving only 0.141202 minutes below the 60-minute ceiling.",
        interpretation="The intermediate scaling benchmark passes exact reproducibility and a formal linear projection but does not provide enough margin to close the production hard-ceiling gate; deterministic 500k remains mandatory.",
        do_not="Do not describe this as empirical full-5.31M runtime, completion of G06, attainment of the 30-minute target, or authorization to run the full sample.",
        confidence="HIGH", evidence_path=str(stage15a_250k_qc),
        evidence_metrics={"input_reads": 250000, "projected_minutes": 59.85879792861273, "margin_minutes": 0.14120207138726926, "normalized_scaling_factor": 1.0279652585921333},
        status="ACTIVE", effective_at=stage15a_250k_effective_at,
    )
    add_interpretation(
        conn, key="stage15a_post250k_architecture_audit_interpretation",
        fact="The post-250k architecture audit found zero blocking conflicts, three review items, and two open items; frozen components and the active pipeline remained unchanged.",
        interpretation="The architecture may proceed to SSOT registration and deterministic 500k, but Stage15A remains IN_PROGRESS and the review/open items must remain explicit.",
        do_not="Do not interpret REVIEW as Stage15A PASS, active promotion, G06/G07 closure, biology-ready implementation, or release readiness.",
        confidence="HIGH", evidence_path=str(stage15a_arch_report),
        evidence_metrics={"conflicts": 0, "review_items": 3, "open_items": 2, "audit_status": "REVIEW"},
        status="ACTIVE", effective_at=stage15a_250k_effective_at,
    )

    def stage15a_register_contract(key: str, name: str, state: str, statement: str, implementation_id: str | None, evidence_path: Path) -> None:
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
                key, name, state, statement, implementation_id, str(evidence_path),
                stage15a_250k_effective_at, "ACTIVE",
            ),
        )

    stage15a_register_contract(
        "stage15a_performance_candidate_v0221", "Stage 15A performance candidate v0.2.2.1",
        "100K_AND_250K_EXACT_PARITY_500K_OPEN",
        "100k and deterministic 250k exact-parity evidence are accepted. G06 remains OPEN pending deterministic 500k and later empirical full-scale runtime; the 30-minute target remains unmet.",
        "impl_stage15a_performance_v0_2_2_1", stage15a_250k_qc,
    )
    stage15a_register_contract(
        "stage15a_restart_resume_v0_1_0", "Stage 15A restart/resume contract v0.1.0",
        "100K_SELECTIVE_RESTART_PASS_250K_CHECKPOINT_LOGICAL_PASS_250K_RESUME_OPEN",
        "100k selective caller-checkpoint-to-final resume is validated and 250k role×shard logical checkpoint reproducibility passes. 250k selective resume, arbitrary upstream recovery, concurrent-memory accounting, and full-scale restart remain OPEN.",
        "impl_stage15a_restart_resume_100k_v0_1_0", stage15a_arch_checkpoint,
    )
    stage15a_register_contract(
        "stage15a_deterministic_scaling_v0_1_2", "Stage 15A deterministic scaling contract v0.1.2",
        "250K_PASS_500K_REQUIRED",
        "Two 250k hash-seed replicates must have exact final-package/caller reproducibility and preserve the nested 100k anchor. The 59.858798-minute linear projection is insufficient to close G06 because margin is only 0.141202 minutes; deterministic 500k is mandatory.",
        "impl_stage15a_scaling_250k_v0_1_2", stage15a_250k_qc,
    )
    stage15a_register_contract(
        "stage15a_checkpoint_reproducibility_v0_1_0", "Stage 15A checkpoint logical reproducibility amendment v0.1.0",
        "LOGICAL_REPRODUCIBILITY_PASS_ORIGINAL_QC_SUPERSEDED",
        "Checkpoint reproducibility is established only by role×shard A/B comparison using decompressed bytes for compressed deterministic TSVs, timing-excluded semantic metrics for runtime QC, and raw bytes for other deterministic artifacts. The original v0.1.2 boolean claim is historical but unsupported as implemented.",
        "impl_stage15a_archaudit_post250k_v0_1_1", stage15a_arch_checkpoint,
    )
    stage15a_register_contract(
        "architecture_consistency_audit_v0_1_0", "Architecture consistency audit contract v0.1.0",
        "POST250K_REVIEW_ZERO_CONFLICTS_PREBIOLOGY_AND_PRERC_OPEN",
        "Major-checkpoint audits must cross-check SSOT, active paths, schema/contracts, performance, validation/restart, biology roadmap, and lifecycle. Post-250k is complete with REVIEW and zero conflicts; pre-biology and pre-release-candidate audits remain mandatory.",
        "impl_stage15a_archaudit_post250k_v0_1_1", stage15a_arch_contract,
    )

    conn.execute(
        """
        INSERT OR REPLACE INTO limitations(
            limitation_key,statement,severity,status,mitigation,evidence_path,effective_at
        ) VALUES(?,?,?,?,?,?,?)
        """,
        ("STAGE15A_250K_60MIN_MARGIN_TOO_SMALL", "The deterministic 250k linear projection is 59.858798 minutes, leaving only 0.141202 minutes below the 60-minute ceiling and therefore insufficient safety margin for gate closure.", "HIGH", "ACTIVE", "Run deterministic 500k with corrected checkpoint comparison and reassess nonlinearity before any full 5.31M run.", str(stage15a_250k_qc), stage15a_250k_effective_at),
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO limitations(
            limitation_key,statement,severity,status,mitigation,evidence_path,effective_at
        ) VALUES(?,?,?,?,?,?,?)
        """,
        ("STAGE15A_INTERNAL_RUN_ID_COMPATIBILITY_ALIAS", "The 250k external run uses the historical 100k run ID internally for component paths and compatibility plumbing.", "MODERATE", "ACTIVE", "Encapsulate or remove the alias before release candidate and require external/internal provenance consistency in the pre-release architecture audit.", str(stage15a_arch_qc), stage15a_250k_effective_at),
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO limitations(
            limitation_key,statement,severity,status,mitigation,evidence_path,effective_at
        ) VALUES(?,?,?,?,?,?,?)
        """,
        ("STAGE15A_250K_SELECTIVE_RESUME_NOT_EXECUTED", "The 250k benchmark validates checkpoint integrity and A/B logical reproducibility but does not execute selective resume or arbitrary upstream recovery at 250k scale.", "HIGH", "ACTIVE", "Keep G07 OPEN and perform a larger-scale restart/memory audit before the full sample.", str(stage15a_arch_qc), stage15a_250k_effective_at),
    )

    conn.execute(
        """
        INSERT OR REPLACE INTO open_questions(
            question_key,question,priority,status,blocking,next_action,evidence_path,effective_at
        ) VALUES(?,?,?,?,?,?,?,?)
        """,
        ("GENERAL_CALLER_PRODUCTION_INTEGRATION", "Can the exact-parity Stage 15A candidate remain deterministic, restartable, artifact-complete, and within the 60-minute hard ceiling as BAM input increases, while continuing toward the 30-minute target?", "CRITICAL", "OPEN", 1, "Run deterministic 500k BAM-input scaling with the corrected role×shard checkpoint checker and a release-oriented external run-ID contract. Capture runtime, RSS, temporary bytes, package/caller/checkpoint reproducibility, and preserve the full 5.31M prohibition.", str(stage15a_arch_report), stage15a_250k_effective_at),
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO open_questions(
            question_key,question,priority,status,blocking,next_action,evidence_path,effective_at
        ) VALUES(?,?,?,?,?,?,?,?)
        """,
        ("ARCHITECTURE_CONSISTENCY_AUDIT_CLOSURE", "Are SSOT, active code/path, schema/contracts, performance gates, validation/restart scope, biology roadmap, and implementation lifecycle mutually consistent at each major checkpoint?", "CRITICAL", "OPEN", 1, "Post-250k audit is complete. Repeat the audit before biology-layer implementation and before release candidate; close any blocking CONFLICT before proceeding.", str(stage15a_arch_contract), stage15a_250k_effective_at),
    )
    conn.execute(
        """
        UPDATE open_questions
        SET next_action=?, evidence_path=?, effective_at=?
        WHERE question_key='BIOLOGY_READY_INTERPRETATION_OUTPUT_AUDIT'
        """,
        ("After performance architecture stabilizes, run the designated pre-biology Architecture consistency audit, then audit the core package against G20-G23, freeze sidecar schemas/validators, and implement molecule-level biology and interpretation layers.", str(stage15a_arch_contract), stage15a_250k_effective_at),
    )

    stage15a_failures = [
        ("stage15a_250k_v010_fixed_100k_fast11e_guard", "v0.1.0", "The deterministic 250k run stopped after 11d3 because the fast shared-catalog 11e builder retained fixed 100k aggregate row/read guards.", "A fixture-size assumption was embedded in a scaling component.", "Resolved by v0.1.1 dynamic expected rows/reads derived from the shard manifest.", stage15a_scaler_v010, "rnatr_stage15a_deterministic_250k_scaling_v0.1.1"),
        ("stage15a_250k_v011_missing_orchestrate_mode", "v0.1.1", "The repair launcher stopped before replicate processing because it invoked the multi-mode scaling runner without --orchestrate.", "Outer orchestration wiring omitted a required mode flag.", "Resolved by v0.1.2 explicit --orchestrate execution; validated 250k input and mapping were reused.", stage15a_scaler_v011, "rnatr_stage15a_deterministic_250k_scaling_v0.1.2"),
        ("stage15a_250k_v012_checkpoint_claim_unsupported", "v0.1.2", "The QC field checkpoint_manifest_reproducibility=true was emitted although the function validated each replicate manifest independently and did not perform A/B comparison.", "The checker name and returned boolean overstated its implemented scope.", "Resolved by post-250k audit v0.1.1 role×shard logical comparison: 157/157 PASS, zero logical differences. Historical QC preserved and superseded by amendment.", stage15a_250k_checkpoint_original, "stage15a_checkpoint_reproducibility_v0_1_0"),
    ]
    for failure_id, attempt, summary, root_cause, resolution, source_path, superseded_by in stage15a_failures:
        conn.execute(
            """
            INSERT OR REPLACE INTO failures(
                failure_id,run_id,stage_key,attempt_version,status,summary,
                root_cause,resolution,source_path,superseded_by,recorded_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (failure_id, stage15a_250k_run_id, stage15a_250k_stage_key, attempt, "RESOLVED", summary, root_cause, resolution, str(source_path), superseded_by, stage15a_250k_effective_at),
        )

    for source_path, source_type in [
        (stage15a_250k_qc, "stage15a_250k_scaling_qc"),
        (stage15a_250k_stage_model, "stage15a_250k_stage_model"),
        (stage15a_250k_package_repro, "stage15a_250k_package_reproducibility"),
        (stage15a_250k_caller_repro, "stage15a_250k_caller_reproducibility"),
        (stage15a_250k_nested, "stage15a_250k_nested_100k_parity"),
        (stage15a_250k_checkpoint_original, "stage15a_250k_original_checkpoint_claim"),
        (stage15a_250k_checkpoint_a, "stage15a_250k_checkpoint_manifest_A"),
        (stage15a_250k_checkpoint_b, "stage15a_250k_checkpoint_manifest_B"),
        (stage15a_arch_qc, "stage15a_post250k_architecture_audit_qc"),
        (stage15a_arch_findings, "stage15a_post250k_architecture_findings"),
        (stage15a_arch_checkpoint, "stage15a_checkpoint_logical_amendment"),
        (stage15a_arch_lifecycle, "stage15a_script_lifecycle_ledger"),
        (stage15a_arch_report, "stage15a_post250k_architecture_report"),
        (stage15a_arch_contract, "architecture_consistency_audit_contract"),
        (stage15a_arch_script, "stage15a_architecture_audit_script"),
        (stage15a_release_gates_v024, "release_gates"),
        (stage15a_scaler_v010, "stage15a_250k_scaler_v010"),
        (stage15a_scaler_v011, "stage15a_250k_scaler_v011"),
        (stage15a_scaler_v012, "stage15a_250k_scaler_v012"),
        (stage15a_fast11e_scaling, "stage15a_scaling_fast11e"),
        (stage15a_candidate_extractor, "stage15a_candidate_fastq_extractor"),
        (stage15a_prepare_250k, "stage15a_prepare_250k_input"),
        (stage15a_scaling_installer_v010, "stage15a_250k_initial_installer"),
    ]:
        source_document(conn, source_path, source_type, force_hash=True)



    # Stage 15D full-scale empirical completion and G31 scope registration v0.1.0
    stage15d_effective_at = "2026-08-10T00:00:00+00:00"
    stage15d_run_500k = "ENCSR307SHM_stage15a500k_seed20260809_mm2splice_v1"
    stage15d_mapping_run = "ENCSR307SHM_full5312696_mm2splice_v1"
    stage15d_full_run = "ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1"
    stage15d_evidence_guards = {'/mnt/intelssd/rnatr_project/qc/15_stage15a_bam_to_final/ENCSR307SHM_stage15a500k_seed20260809_mm2splice_v1/v0.1.1_500k_scaling/stage15a_scaling_500k.qc.tsv': 'ef27be62e633e941b21978d8354a928a7ecea33600465fe6620e82640b329e82', '/mnt/intelssd/rnatr_project/qc/11_mapping/ENCSR307SHM_full5312696_mm2splice_v1/ENCSR307SHM_full5312696_mm2splice_v1.mapping_qc.tsv': '96c723fd7248faeca0e674a5a6d59d92c0516e8ae4a63c037d8b5a1150861c3e', '/mnt/intelssd/rnatr_project/qc/11_mapping/ENCSR307SHM_full5312696_mm2splice_v1/ENCSR307SHM_full5312696_mm2splice_v1.read_id_parity.tsv': '47c37eb77fa16847ba9d1b6fe4c8c40dfa9661837c3bc95efda2f330fe3ecd7c', '/mnt/intelssd/rnatr_project/qc/15_stage15b_memory_bounded_validator/ENCSR307SHM_stage15a500k_seed20260809_mm2splice_v1/v0.1.0/stage15b_memory_bounded_validator.qc.tsv': 'b5f7f26f91d0edafbdc77de3373b67b8cc9ec3e16fb2f903cec4390a9d47f142', '/mnt/intelssd/rnatr_project/qc/15_stage15c_execution_architecture/ENCSR307SHM_stage15a500k_seed20260809_mm2splice_v1/v0.1.1_144shard_500k/stage15c_144shard_execution_architecture.qc.tsv': '43226464ef19572de3fcccef1a6e7fd169e22e20e8fa3b724f9d2f1080ce0437', '/mnt/intelssd/rnatr_project/qc/15_stage15c_fullscale_bam_to_final/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.6/stage15c_full_empirical_run.qc.tsv': '3b95addc1e7aa50ddf22d90dab3373025b9c7b41569fcb2aaea7d2910b35fd07', '/mnt/intelssd/rnatr_project/results/15_stage15c_fullscale_bam_to_final/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.6/package_full/package_manifest.tsv': '335058228a3f3c4205161f3d24b208009175aed5e50f995a74e04100b4f3a738', '/mnt/intelssd/rnatr_project/qc/15_stage15c_fullscale_bam_to_final/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.6/stage15c_fullscale_checkpoint_manifest.tsv': 'f00d67e28413d66730b8c2ffab0f52b9ce9e1553e5cc9a3f9d768e4a7a0083b4', '/mnt/intelssd/rnatr_project/qc/15_stage15d_g31_row_expansion_audit/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15d_g31_row_expansion_audit.qc.tsv': '8cfb7eb4c5dc85c554b52deae630f15a3602117a689146ceb7a0c55ef008c163', '/mnt/intelssd/rnatr_project/qc/15_stage15d_g31_row_expansion_audit/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/candidate_entry_rate_and_reason_audit.tsv': '474f6280a1a5e98fb3940dc3e941c20b93870b7791da74157678efaf83c4d4fc', '/mnt/intelssd/rnatr_project/qc/15_stage15d_g31_row_expansion_audit/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/cross_scale_comparison.tsv': '0f5939b753506c44881574cd1f1a217134902ad64bacec4b7dc7dbb534edf904', '/mnt/intelssd/rnatr_project/qc/15_stage15d_g31_row_expansion_audit/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/hard_lineage_and_duplicate_audit.tsv': '47c8579614e2905ef6f68924a0e0b174b1b743658be747d9ebbeee7a9c5e6a5b', '/mnt/intelssd/rnatr_project/qc/15_stage15d_g31_row_expansion_audit/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/concentration_summary.tsv': 'c4f92a75afc0cc63ee27052ded3d2b6198b2b0b7071097a4aedc290ad046d836', '/mnt/intelssd/rnatr_project/scripts/rnatr_stage15c_run_full5312696_bam_to_final_v0.1.6.py': 'cca6b2d4c6e773392d3a8c24cd2fd2a1f0a41a713338b4ccdec1ba7fab5bafcc', '/mnt/intelssd/rnatr_project/scripts/rnatr_stage15b_validate_package_sharded_memory_bounded_v0.1.0.py': '1136086f0214bcd11a2a2d71f2e459f433c7fc9f51d170aa3b97826e8808ee99', '/mnt/intelssd/rnatr_project/scripts/rnatr_stage15c_validate_144shard_execution_architecture_v0.1.1.py': 'fe8f4bdada0336d6e8afc0008f5800d920a49a28a1541f10a89b439d88770b72', '/mnt/intelssd/rnatr_project/scripts/rnatr_stage15d_g31_row_expansion_audit_v0.1.0.py': 'fa9c56d6aeb8488e69ed937ac9d89b1a7c62afee9baeb6fe410b5fa2c182d608', '/mnt/intelssd/rnatr_project/scripts/rnatr_stage15c_map_full_ENCSR307SHM_mm2splice_v010.sh': '2818b171a0e892b42746e890f98b6705820a2ed9e3a3fad196c07baa7c4c3724'}
    stage15d_source_guards = {'/mnt/intelssd/rnatr_project/docs/handover/RNA_TR_Scout_handover_Stage15C_full_empirical_to_determinism_restart_20260810.md': 'd42e4c98379dd1e5b42f17771d4622cab568e6c3b028be9458816d5c8cf548ba', '/mnt/intelssd/rnatr_project/scripts/rnatr_stage15d_update_ssot_fullscale_handover_v0.1.0.py': 'acd40e90bf3379ab3fc395c0c905d2379868cd6673d53b0105a89fb7af8317a7', '/mnt/intelssd/rnatr_project/validation/release_gates_v0.3.0.tsv': '4d5d0572a11ac111c3ac12e1121fd6101ec3a59d7c69e53aa46855f351356715'}

    def _s15d_sha256(path):
        digest = hashlib.sha256()
        with Path(path).open("rb") as handle:
            for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    def _s15d_guard(path_text, expected):
        path = Path(path_text)
        if not path.is_file() or path.stat().st_size <= 0:
            raise RuntimeError(f"Stage15D SSOT evidence missing: {path}")
        observed = _s15d_sha256(path)
        if observed != expected:
            raise RuntimeError(f"Stage15D SSOT evidence drift: {path}: {observed} != {expected}")
        return path

    for _s15d_path, _s15d_expected in {**stage15d_evidence_guards, **stage15d_source_guards}.items():
        _s15d_guard(_s15d_path, _s15d_expected)

    _s15d_parent = conn.execute(
        "SELECT dataset_id FROM runs WHERE run_id=?", ("ENCSR307SHM_pilot100k_mm2splice_v1",)
    ).fetchone()
    if _s15d_parent is None:
        raise RuntimeError("Stage15D SSOT registration requires the registered 100k parent run")
    _s15d_dataset_id = _s15d_parent[0]

    def _s15d_stage(key, order, name, purpose, category, implementation_status, notes):
        conn.execute(
            """INSERT INTO stage_definitions(
                   stage_key,stage_order,name,purpose,category,implementation_status,notes
               ) VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(stage_key) DO UPDATE SET
                   stage_order=excluded.stage_order,name=excluded.name,
                   purpose=excluded.purpose,category=excluded.category,
                   implementation_status=excluded.implementation_status,
                   notes=excluded.notes""",
            (key, order, name, purpose, category, implementation_status, notes),
        )

    def _s15d_run(run_id, parent_run_id, role, pipeline_version, status, root_path, notes):
        conn.execute(
            """INSERT INTO runs(
                   run_id,dataset_id,parent_run_id,run_role,pipeline_version,status,
                   started_at,ended_at,root_path,notes
               ) VALUES(?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(run_id) DO UPDATE SET
                   dataset_id=excluded.dataset_id,
                   parent_run_id=excluded.parent_run_id,
                   run_role=excluded.run_role,
                   pipeline_version=excluded.pipeline_version,
                   status=excluded.status,
                   root_path=excluded.root_path,
                   notes=excluded.notes""",
            (run_id, _s15d_dataset_id, parent_run_id, role, pipeline_version, status,
             None, None, root_path, notes),
        )

    def _s15d_impl(impl_id, stage_key, version, script_path, script_sha, lifecycle, rationale, evidence_path):
        conn.execute(
            """INSERT OR REPLACE INTO implementations(
                   implementation_id,stage_key,version,script_path,script_sha256,
                   validator_path,validator_sha256,package_version,parameters_json,
                   lifecycle_status,supersedes_implementation_id,rationale,
                   evidence_path,effective_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (impl_id,stage_key,version,script_path,script_sha,None,None,"v0.4.2",None,
             lifecycle,None,rationale,evidence_path,stage15d_effective_at),
        )

    def _s15d_run_stage(run_id, stage_key, impl_id, attempt, status, qc_path, qc_status, notes):
        conn.execute(
            """INSERT OR REPLACE INTO run_stages(
                   run_id,stage_key,implementation_id,attempt_tag,status,command_text,
                   qc_path,qc_status,started_at,ended_at,notes
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (run_id,stage_key,impl_id,attempt,status,None,qc_path,qc_status,None,None,notes),
        )

    def _s15d_metric(run_id, stage_key, name, value_text, value_num, unit, denominator, source_path, status="CURRENT"):
        conn.execute(
            """INSERT OR REPLACE INTO metrics(
                   run_id,stage_key,metric_name,value_text,value_num,unit,
                   denominator_num,source_path,metric_status,recorded_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (run_id,stage_key,name,str(value_text),value_num,unit,denominator,
             str(source_path),status,stage15d_effective_at),
        )

    def _s15d_decision(key, category, title, statement, confidence, rationale, evidence_path):
        decision_id = "decision_" + hashlib.sha256(key.encode()).hexdigest()[:20]
        conn.execute(
            """INSERT OR REPLACE INTO decisions(
                   decision_id,decision_key,category,title,statement,status,confidence,
                   effective_at,supersedes_decision_id,rationale,evidence_path
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (decision_id,key,category,title,statement,"ACTIVE",confidence,
             stage15d_effective_at,None,rationale,str(evidence_path)),
        )

    def _s15d_interpretation(key, fact, interpretation, do_not, confidence, evidence_path, metrics):
        interpretation_id = "interpretation_" + hashlib.sha256(key.encode()).hexdigest()[:20]
        conn.execute(
            """INSERT OR REPLACE INTO interpretations(
                   interpretation_id,interpretation_key,fact_statement,interpretation,
                   do_not_interpret_as,status,confidence,effective_at,
                   supersedes_interpretation_id,evidence_path,evidence_metrics_json
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (interpretation_id,key,fact,interpretation,do_not,"ACTIVE",confidence,
             stage15d_effective_at,None,str(evidence_path),json.dumps(metrics,sort_keys=True)),
        )

    def _s15d_contract(key, name, state, statement, impl_id, evidence_path):
        contract_id = "contract_" + hashlib.sha256(key.encode()).hexdigest()[:20]
        conn.execute(
            """INSERT OR REPLACE INTO algorithm_contracts(
                   contract_id,component_key,component_name,implementation_state,
                   contract_statement,active_implementation_id,evidence_path,
                   effective_at,status
               ) VALUES(?,?,?,?,?,?,?,?,?)""",
            (contract_id,key,name,state,statement,impl_id,str(evidence_path),
             stage15d_effective_at,"ACTIVE"),
        )

    def _s15d_source(path_text, source_type, expected):
        path = _s15d_guard(path_text, expected)
        mtime = __import__("datetime").datetime.fromtimestamp(
            path.stat().st_mtime, __import__("datetime").timezone.utc
        ).replace(microsecond=0).isoformat()
        conn.execute(
            """INSERT INTO source_documents(
                   source_type,path,sha256,bytes,mtime_utc,content_status,ingested_at
               ) VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(path) DO UPDATE SET
                   source_type=excluded.source_type,sha256=excluded.sha256,
                   bytes=excluded.bytes,mtime_utc=excluded.mtime_utc,
                   content_status=excluded.content_status,ingested_at=excluded.ingested_at""",
            (source_type,str(path),expected,path.stat().st_size,mtime,"PRESENT",stage15d_effective_at),
        )

    _s15d_stage("15A_DETERMINISTIC_500K_SCALING",151.4,"Stage 15A deterministic 500k scaling",
                "Validate exact package/caller/checkpoint reproducibility and empirical scaling before full execution.",
                "production_validation","IMPLEMENTED_WITH_GATE",
                "500k deterministic scaling PASS; full empirical runtime subsequently completed.")
    _s15d_stage("15B_MEMORY_BOUNDED_VALIDATOR",151.5,"Stage 15B memory-bounded package validator",
                "Preserve frozen validator accept/reject semantics with shard-bounded memory and global external-sort uniqueness.",
                "validation","IMPLEMENTED_WITH_GATE","100k/500k positive parity and 10 negative fixtures PASS; candidate remains provisional, not active.")
    _s15d_stage("15C_FULL_MAPPING",151.6,"Stage 15C full splice-aware mapping",
                "Create the mapping-complete 5,312,696-read BAM with exact FASTQ/BAM read-ID parity.",
                "mapping_validation","IMPLEMENTED_WITH_GATE","Mapping time is reported separately and excluded from BAM-to-final runtime gate.")
    _s15d_stage("15C_FULLSCALE_EXECUTION_ARCHITECTURE",151.7,"Stage 15C 144-shard execution architecture",
                "Validate shard count as an execution parameter and bind memory-aware full-scale concurrency.",
                "execution_architecture","IMPLEMENTED_WITH_GATE","500k 12-vs-144-shard exact package parity PASS; cross-hardware determinism remains open.")
    _s15d_stage("15C_FULL_EMPIRICAL_BAM_TO_FINAL",151.8,"Stage 15C full 5.31M empirical BAM-to-final",
                "Run mapping-complete full BAM through target assignment, projection, caller, materialization, validation, and atomic publication.",
                "production_validation","IMPLEMENTED_WITH_GATE","Correctness/memory/storage/publication PASS; runtime PASS_WITH_DOCUMENTED_TOLERANCE; restart/determinism open.")
    _s15d_stage("15D_G31_ROW_EXPANSION_AUDIT",151.9,"Stage 15D G31 row-expansion and candidate-entry audit",
                "Quantify full-scale row lineage, multiplicity, duplicate/concentration, catalog geometry, and candidate-entry rate.",
                "governance_validation","IMPLEMENTED_WITH_GATE","Original machine FAIL preserved; technical multiplicity accepted by scope amendment, biology interpretation deferred.")

    _s15d_run(stage15d_run_500k,"ENCSR307SHM_pilot100k_mm2splice_v1","DETERMINISTIC_SCALING_BENCHMARK",
               "rnatr_stage15a_deterministic_500k_scaling_v0.1.4_compare_amendment",
               "PASS","/mnt/intelssd/rnatr_project/results/15_stage15a_bam_to_final/ENCSR307SHM_stage15a500k_seed20260809_mm2splice_v1/v0.1.1_500k_scaling",
               "Exact package/caller/checkpoint reproducibility and nested-250k parity PASS; active pipeline unchanged.")
    _s15d_run(stage15d_mapping_run,"ENCSR307SHM_pilot100k_mm2splice_v1","FULL_MAPPING_BENCHMARK",
               "minimap2_splice_cDNA_full_v1","PASS",
               "/mnt/intelssd/rnatr_project/results/11_mapping/ENCSR307SHM_full5312696_mm2splice_v1",
               "5,312,696 primary records with exact FASTQ/BAM read-ID multiset parity; mapping excluded from BAM-to-final gate.")
    _s15d_run(stage15d_full_run,stage15d_mapping_run,"FULL_EMPIRICAL_CORE_BENCHMARK",
               "rnatr_stage15c_full5312696_bam_to_final_v0.1.6",
               "PASS_WITH_DOCUMENTED_TOLERANCE",
               "/mnt/intelssd/rnatr_project/results/15_stage15c_fullscale_bam_to_final/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.6",
               "Full 5.31M BAM-to-final correctness PASS at 60.041256352 min; restart/resume and release-scale determinism remain open.")

    _s15d_impl("impl_stage15a_scaling_500k_v0_1_4","15A_DETERMINISTIC_500K_SCALING",
               "v0.1.4_compare_amendment",None,None,"PROVISIONAL",
               "Accepted deterministic 500k scaling evidence; not an active pipeline implementation.","/mnt/intelssd/rnatr_project/qc/15_stage15a_bam_to_final/ENCSR307SHM_stage15a500k_seed20260809_mm2splice_v1/v0.1.1_500k_scaling/stage15a_scaling_500k.qc.tsv")
    _s15d_impl("impl_stage15b_memory_bounded_validator_v0_1_0","15B_MEMORY_BOUNDED_VALIDATOR",
               "v0.1.0","/mnt/intelssd/rnatr_project/scripts/rnatr_stage15b_validate_package_sharded_memory_bounded_v0.1.0.py","1136086f0214bcd11a2a2d71f2e459f433c7fc9f51d170aa3b97826e8808ee99","PROVISIONAL",
               "Frozen-semantics equivalent memory-bounded package validator; active promotion deferred.","/mnt/intelssd/rnatr_project/qc/15_stage15b_memory_bounded_validator/ENCSR307SHM_stage15a500k_seed20260809_mm2splice_v1/v0.1.0/stage15b_memory_bounded_validator.qc.tsv")
    _s15d_impl("impl_stage15c_full_mapping_v0_1_0","15C_FULL_MAPPING","v0.1.0",
               "/mnt/intelssd/rnatr_project/scripts/rnatr_stage15c_map_full_ENCSR307SHM_mm2splice_v010.sh","2818b171a0e892b42746e890f98b6705820a2ed9e3a3fad196c07baa7c4c3724","REFERENCE",
               "Full mapping implementation used to create the benchmark BAM.","/mnt/intelssd/rnatr_project/qc/11_mapping/ENCSR307SHM_full5312696_mm2splice_v1/ENCSR307SHM_full5312696_mm2splice_v1.mapping_qc.tsv")
    _s15d_impl("impl_stage15c_144shard_architecture_v0_1_1","15C_FULLSCALE_EXECUTION_ARCHITECTURE",
               "v0.1.1","/mnt/intelssd/rnatr_project/scripts/rnatr_stage15c_validate_144shard_execution_architecture_v0.1.1.py","fe8f4bdada0336d6e8afc0008f5800d920a49a28a1541f10a89b439d88770b72","REFERENCE_AUDIT",
               "Execution-only 144-shard architecture with exact 500k scientific parity.","/mnt/intelssd/rnatr_project/qc/15_stage15c_execution_architecture/ENCSR307SHM_stage15a500k_seed20260809_mm2splice_v1/v0.1.1_144shard_500k/stage15c_144shard_execution_architecture.qc.tsv")
    _s15d_impl("impl_stage15c_full_runner_v0_1_6","15C_FULL_EMPIRICAL_BAM_TO_FINAL","v0.1.6",
               "/mnt/intelssd/rnatr_project/scripts/rnatr_stage15c_run_full5312696_bam_to_final_v0.1.6.py","cca6b2d4c6e773392d3a8c24cd2fd2a1f0a41a713338b4ccdec1ba7fab5bafcc","PROVISIONAL",
               "Validated full-scale candidate; explicit active-path promotion remains prohibited.","/mnt/intelssd/rnatr_project/qc/15_stage15c_fullscale_bam_to_final/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.6/stage15c_full_empirical_run.qc.tsv")
    _s15d_impl("impl_stage15d_g31_audit_v0_1_0","15D_G31_ROW_EXPANSION_AUDIT","v0.1.0",
               "/mnt/intelssd/rnatr_project/scripts/rnatr_stage15d_g31_row_expansion_audit_v0.1.0.py","fa9c56d6aeb8488e69ed937ac9d89b1a7c62afee9baeb6fe410b5fa2c182d608","REFERENCE_AUDIT",
               "Read-only full-scale multiplicity audit; original machine result retained and scope-amended by Pro/user decision.","/mnt/intelssd/rnatr_project/qc/15_stage15d_g31_row_expansion_audit/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15d_g31_row_expansion_audit.qc.tsv")

    _s15d_run_stage(stage15d_run_500k,"15A_DETERMINISTIC_500K_SCALING","impl_stage15a_scaling_500k_v0_1_4",
                     "v0.1.4","PASS","/mnt/intelssd/rnatr_project/qc/15_stage15a_bam_to_final/ENCSR307SHM_stage15a500k_seed20260809_mm2splice_v1/v0.1.1_500k_scaling/stage15a_scaling_500k.qc.tsv","PASS","500k deterministic package/caller/checkpoint/nested parity PASS.")
    _s15d_run_stage(stage15d_run_500k,"15B_MEMORY_BOUNDED_VALIDATOR","impl_stage15b_memory_bounded_validator_v0_1_0",
                     "v0.1.0","PASS","/mnt/intelssd/rnatr_project/qc/15_stage15b_memory_bounded_validator/ENCSR307SHM_stage15a500k_seed20260809_mm2splice_v1/v0.1.0/stage15b_memory_bounded_validator.qc.tsv","PASS","Frozen/candidate accept-reject equivalence PASS.")
    _s15d_run_stage(stage15d_run_500k,"15C_FULLSCALE_EXECUTION_ARCHITECTURE","impl_stage15c_144shard_architecture_v0_1_1",
                     "v0.1.1","PASS","/mnt/intelssd/rnatr_project/qc/15_stage15c_execution_architecture/ENCSR307SHM_stage15a500k_seed20260809_mm2splice_v1/v0.1.1_144shard_500k/stage15c_144shard_execution_architecture.qc.tsv","PASS","12-vs-144 shard scientific output exact parity PASS.")
    _s15d_run_stage(stage15d_mapping_run,"15C_FULL_MAPPING","impl_stage15c_full_mapping_v0_1_0",
                     "v0.1.0","PASS","/mnt/intelssd/rnatr_project/qc/11_mapping/ENCSR307SHM_full5312696_mm2splice_v1/ENCSR307SHM_full5312696_mm2splice_v1.mapping_qc.tsv","PASS","Full mapping and read-ID parity PASS.")
    _s15d_run_stage(stage15d_full_run,"15C_FULL_EMPIRICAL_BAM_TO_FINAL","impl_stage15c_full_runner_v0_1_6",
                     "v0.1.6","PASS_WITH_DOCUMENTED_TOLERANCE","/mnt/intelssd/rnatr_project/qc/15_stage15c_fullscale_bam_to_final/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.6/stage15c_full_empirical_run.qc.tsv","PASS","Correctness/memory/storage/publication PASS; runtime exceeded 60 min by 2.475 s within declared tolerance.")
    _s15d_run_stage(stage15d_full_run,"15D_G31_ROW_EXPANSION_AUDIT","impl_stage15d_g31_audit_v0_1_0",
                     "v0.1.0","REVIEW_SCOPE_AMENDMENT","/mnt/intelssd/rnatr_project/qc/15_stage15d_g31_row_expansion_audit/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15d_g31_row_expansion_audit.qc.tsv","MACHINE_FAIL_PRESERVED_G31T_PASS_G31B_DEFERRED",
                     "Original machine FAIL remains immutable; technical integrity closed by scope amendment, biology interpretation deferred.")

    for _name,_value,_num,_unit,_denom in [
        ("input_reads",500000,500000,"reads",None),
        ("bam_to_final_seconds",335.3816997719696,335.3816997719696,"seconds",None),
        ("full_projection_minutes",59.39270049505812,59.39270049505812,"minutes",None),
        ("candidate_rows",1948859,1948859,"rows",None),
        ("candidate_reads",396549,396549,"reads",500000),
    ]:
        _s15d_metric(stage15d_run_500k,"15A_DETERMINISTIC_500K_SCALING",_name,_value,_num,_unit,_denom,"/mnt/intelssd/rnatr_project/qc/15_stage15a_bam_to_final/ENCSR307SHM_stage15a500k_seed20260809_mm2splice_v1/v0.1.1_500k_scaling/stage15a_scaling_500k.qc.tsv")

    for _name,_value,_num,_unit,_denom in [
        ("input_reads",5312696,5312696,"reads",None),
        ("bam_to_final_seconds",3602.475381092,3602.475381092,"seconds",None),
        ("bam_to_final_minutes",60.041256352,60.041256352,"minutes",None),
        ("candidate_reads",4212263,4212263,"reads",5312696),
        ("candidate_rows",20656258,20656258,"rows",None),
        ("caller_called_rows",8524435,8524435,"rows",20656258),
        ("caller_no_call_rows",12131823,12131823,"rows",20656258),
        ("caller_error_rows",0,0,"rows",20656258),
        ("repeat_events_rows",8523140,8523140,"rows",None),
        ("repeat_segments_rows",8573315,8573315,"rows",None),
        ("repeat_interruptions_rows",43399,43399,"rows",None),
        ("maximum_host_used_fraction",0.272065,0.272065,"fraction",1),
        ("peak_temporary_and_output_bytes",146580576495,146580576495,"bytes",None),
        ("minimum_project_free_bytes",165594337280,165594337280,"bytes",None),
        ("checkpoint_rows",1884,1884,"rows",None),
        ("checkpoint_bytes",140029015504,140029015504,"bytes",None),
    ]:
        _s15d_metric(stage15d_full_run,"15C_FULL_EMPIRICAL_BAM_TO_FINAL",_name,_value,_num,_unit,_denom,"/mnt/intelssd/rnatr_project/qc/15_stage15c_fullscale_bam_to_final/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.6/stage15c_full_empirical_run.qc.tsv")

    for _name,_value,_num,_unit,_denom,_source in [
        ("candidate_read_rate",0.792867312566,0.792867312566,"fraction",5312696,"/mnt/intelssd/rnatr_project/qc/15_stage15d_g31_row_expansion_audit/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15d_g31_row_expansion_audit.qc.tsv"),
        ("candidate_rows_per_candidate_read",4.903838625461,4.903838625461,"ratio",4212263,"/mnt/intelssd/rnatr_project/qc/15_stage15d_g31_row_expansion_audit/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15d_g31_row_expansion_audit.qc.tsv"),
        ("candidate_rows_per_input_read",3.888093352226,3.888093352226,"ratio",5312696,"/mnt/intelssd/rnatr_project/qc/15_stage15d_g31_row_expansion_audit/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15d_g31_row_expansion_audit.qc.tsv"),
        ("exact_overlap_candidate_reads",3020451,3020451,"reads",5312696,"/mnt/intelssd/rnatr_project/qc/15_stage15d_g31_row_expansion_audit/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/candidate_entry_rate_and_reason_audit.tsv"),
        ("proximal_only_candidate_reads",1191812,1191812,"reads",5312696,"/mnt/intelssd/rnatr_project/qc/15_stage15d_g31_row_expansion_audit/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/candidate_entry_rate_and_reason_audit.tsv"),
        ("assignment_excess_over_unique_loci",6431,6431,"rows",20656258,"/mnt/intelssd/rnatr_project/qc/15_stage15d_g31_row_expansion_audit/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/candidate_entry_rate_and_reason_audit.tsv"),
    ]:
        _s15d_metric(stage15d_full_run,"15D_G31_ROW_EXPANSION_AUDIT",_name,_value,_num,_unit,_denom,_source)

    _s15d_decision(
        "stage15c_full_empirical_acceptance_v0_1_6","performance_validation",
        "Accept full 5.31M empirical BAM-to-final with documented first-freeze tolerance",
        "The 5,312,696-read BAM-to-final v0.1.6 run completed in 60.041256352 minutes with correctness, memory, storage, validators, runtime-generated script/path binding, and atomic publication PASS. The result is PASS_WITH_DOCUMENTED_TOLERANCE, not strict <=60-minute PASS.",
        "HIGH","The strict threshold was exceeded by only 2.475 seconds and the predeclared thesis/core-freeze tolerance allows <=62 minutes; the 30-minute target remains open.","/mnt/intelssd/rnatr_project/qc/15_stage15c_fullscale_bam_to_final/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.6/stage15c_full_empirical_run.qc.tsv")
    _s15d_decision(
        "stage15c_active_promotion_deferred_v0_1_0","architecture_governance",
        "Keep the validated Stage15C candidate provisional until remaining release gates close",
        "Do not modify current_pipeline or promote the Stage15C runner before release-scale determinism, full-scale restart/resume, PRE_RELEASE_CANDIDATE Architecture audit, clean-install, and explicit promotion.",
        "HIGH","Empirical full-scale PASS is necessary but not sufficient for active release promotion.","/mnt/intelssd/rnatr_project/qc/15_stage15c_fullscale_bam_to_final/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.6/stage15c_full_empirical_run.qc.tsv")
    _s15d_decision(
        "g31_scope_split_technical_vs_biology_v0_1_0","validation_scope",
        "Split G31 into technical multiplicity integrity and biological candidate-entry interpretation",
        "Preserve the original G31 v0.1.0 machine FAIL. Adopt G31-T PASS_WITH_SCOPE_AMENDMENT because row conservation, primary-ID uniqueness, cross-scale stability, low read-locus excess, and low target concentration show no scale-dependent technical runaway. Defer G31-B candidate-rate and multiplicity meaning to the biology layer as nonblocking for current technical freeze.",
        "HIGH","The machine fail used broader field-level semantic assumptions than the technical runaway question; deep biological interpretation is intentionally deferred by user decision.","/mnt/intelssd/rnatr_project/qc/15_stage15d_g31_row_expansion_audit/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15d_g31_row_expansion_audit.qc.tsv")
    _s15d_decision(
        "internal_beta_release_readiness_g25_g30_v0_1_0","release_readiness",
        "Register portable internal-beta requirements as planned blocking gates",
        "G25-G30 require reference bootstrap, hardware detection, adaptive concurrency, cross-hardware logical determinism, clean-machine reproducibility, and empirical hardware documentation. All remain OPEN_PLANNED and must not be reported as implemented.",
        "HIGH","The project is now complex enough that developer-local paths and manual resource tuning are unacceptable release assumptions.","/mnt/intelssd/rnatr_project/validation/release_gates_v0.3.0.tsv")

    _s15d_interpretation(
        "stage15c_full_runtime_60_041_minutes_v0_1_0",
        "The empirical BAM-to-final timer was 60.041256352 minutes; mapping was excluded while partition, validators, and atomic publication were included.",
        "This satisfies the predeclared documented first-freeze tolerance but not the strict <=60.000-minute threshold.",
        "Do not report this result as strict 60-minute PASS or as meeting the 30-minute target.",
        "HIGH","/mnt/intelssd/rnatr_project/qc/15_stage15c_fullscale_bam_to_final/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.6/stage15c_full_empirical_run.qc.tsv",{"seconds_over_60min":2.475381092,"tolerance_ceiling_minutes":62.0})
    _s15d_interpretation(
        "g31_fullscale_multiplicity_scope_v0_1_0",
        "Candidate/projection/caller/general/read_evidence rows were all 20,656,258; unique read-locus rows were 20,649,827; candidate rate and rows/read were stable across 100k, 500k, and full scale.",
        "There is no evidence of scale-dependent row runaway or unexplained post-11b row birth for the current technical scope.",
        "Do not treat this as complete biological validation of every field-level caller/materializer semantic or as proof that candidate entry is optimally narrow.",
        "HIGH","/mnt/intelssd/rnatr_project/qc/15_stage15d_g31_row_expansion_audit/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15d_g31_row_expansion_audit.qc.tsv",{"read_locus_excess_rows":6431,"candidate_rows":20656258,"top1_target_share":0.002830522})
    _s15d_interpretation(
        "g31_candidate_entry_79pct_v0_1_0",
        "4,212,263 of 5,312,696 reads (79.2867%) entered the broad 11b candidate set; 3,020,451 had exact catalog overlap and 1,191,812 were proximity-only within +/-500 bp.",
        "The rate describes sensitivity-oriented candidate entry in a transcriptome-concentrated RNA dataset and is deferred for biology/algorithmic interpretation.",
        "Do not interpret 79.2867% as repeat-positive prevalence, pathogenicity, expansion prevalence, or final candidate prevalence.",
        "HIGH","/mnt/intelssd/rnatr_project/qc/15_stage15d_g31_row_expansion_audit/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/candidate_entry_rate_and_reason_audit.tsv",{"candidate_rate":0.792867312566,"exact_overlap_reads":3020451,"proximal_only_reads":1191812})

    _s15d_contract(
        "stage15b_memory_bounded_validator_v0_1_0","Stage15B memory-bounded package validator",
        "EQUIVALENCE_PASS_PROVISIONAL_NOT_ACTIVE",
        "Shard-wise frozen v0.4.2 validation plus exact global external-sort primary-ID uniqueness must preserve frozen accept/reject semantics. Positive 100k/500k and 10 negative fixtures pass. Scope excludes locus aggregation.",
        "impl_stage15b_memory_bounded_validator_v0_1_0","/mnt/intelssd/rnatr_project/qc/15_stage15b_memory_bounded_validator/ENCSR307SHM_stage15a500k_seed20260809_mm2splice_v1/v0.1.0/stage15b_memory_bounded_validator.qc.tsv")
    _s15d_contract(
        "stage15c_fullscale_execution_v0_1_6","Stage15C full-scale execution contract",
        "EMPIRICAL_FULLSCALE_PASS_WITH_TOLERANCE_RESTART_DETERMINISM_OPEN",
        "Use 144 read-coherent shards, concurrency 12, caller workers 2/shard, validator workers 3, 512M external sort, PYTHONHASHSEED=0, prepartition runtime-script/path audit, and post-11b maximum 164204 candidate rows/shard. Full empirical correctness passes; restart/resume and release-scale determinism remain open.",
        "impl_stage15c_full_runner_v0_1_6","/mnt/intelssd/rnatr_project/qc/15_stage15c_fullscale_bam_to_final/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.6/stage15c_full_empirical_run.qc.tsv")
    _s15d_contract(
        "g31_technical_multiplicity_integrity_v0_1_0","G31-T technical multiplicity integrity",
        "PASS_WITH_SCOPE_AMENDMENT",
        "Technical freeze accepts row conservation, primary-ID uniqueness, stable cross-scale candidate rate/multiplicity, minimal read-locus excess, and low target concentration as evidence against scale-dependent runaway. The original machine FAIL remains historical evidence.",
        "impl_stage15d_g31_audit_v0_1_0","/mnt/intelssd/rnatr_project/qc/15_stage15d_g31_row_expansion_audit/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15d_g31_row_expansion_audit.qc.tsv")
    _s15d_contract(
        "g31_biological_candidate_entry_interpretation_v0_1_0","G31-B biological candidate-entry interpretation",
        "OPEN_DEFERRED_TO_BIOLOGY_LAYER",
        "Interpret the 79.2867% candidate-entry rate, +/-500bp padding, ~4.9 loci/read, catalog overlap, motif equivalence, and recall-preserving narrowing only in the later biology/optimization phase.",
        None,"/mnt/intelssd/rnatr_project/qc/15_stage15d_g31_row_expansion_audit/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/candidate_entry_rate_and_reason_audit.tsv")
    _s15d_contract(
        "release_readiness_g25_g30_v0_1_0","Internal-beta release readiness G25-G30",
        "DESIGNED_NOT_IMPLEMENTED",
        "Portable reference bootstrap, resource detection, adaptive concurrency, cross-hardware determinism, clean-machine install, and empirical hardware profiles are required before internal beta/release candidate.",
        None,"/mnt/intelssd/rnatr_project/validation/release_gates_v0.3.0.tsv")

    for _key,_statement,_severity,_mitigation,_evidence in [
        ("STAGE15C_FULL_RUNTIME_USES_DOCUMENTED_TOLERANCE","The empirical full BAM-to-final runtime is 60.041256352 minutes and therefore is not strict <=60-minute PASS.","MODERATE","Retain exact wording in SSOT, thesis, release notes, and benchmark tables; continue the 30-minute optimization target.","/mnt/intelssd/rnatr_project/qc/15_stage15c_fullscale_bam_to_final/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.6/stage15c_full_empirical_run.qc.tsv"),
        ("STAGE15C_RELEASE_SCALE_DETERMINISM_OPEN","Release-scale independent deterministic reproduction of the full scientific package has not yet been executed.","HIGH","Run release-scale logical reproducibility before Core Freeze.","/mnt/intelssd/rnatr_project/qc/15_stage15c_fullscale_bam_to_final/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.6/stage15c_full_empirical_run.qc.tsv"),
        ("STAGE15C_FULLSCALE_RESTART_RESUME_OPEN","Full-scale intentional-stop, corrupt-checkpoint rejection, selective resume, clean/resumed parity, and second-resume no-op are not yet validated.","HIGH","Execute the versioned full-scale restart/resume contract using the v0.1.6 checkpoint inventory.","/mnt/intelssd/rnatr_project/qc/15_stage15c_fullscale_bam_to_final/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.6/stage15c_fullscale_checkpoint_manifest.tsv"),
        ("G31_BIOLOGICAL_CANDIDATE_ENTRY_DEFERRED","The biological meaning and optimality of the 79.2867% candidate-entry rate and ~4.9 loci/read remain unresolved.","MODERATE","Address in the biology/optimization layer without blocking current technical-freeze planning.","/mnt/intelssd/rnatr_project/qc/15_stage15d_g31_row_expansion_audit/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/candidate_entry_rate_and_reason_audit.tsv"),
        ("STAGE15C_ACTIVE_PIPELINE_NOT_PROMOTED","The empirically validated Stage15C candidate is not the current active pipeline.","HIGH","Promote only after determinism, restart/resume, pre-release audit, and clean-install gates close.","/mnt/intelssd/rnatr_project/qc/15_stage15c_fullscale_bam_to_final/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.6/stage15c_full_empirical_run.qc.tsv"),
    ]:
        conn.execute(
            """INSERT OR REPLACE INTO limitations(
                   limitation_key,statement,severity,status,mitigation,evidence_path,effective_at
               ) VALUES(?,?,?,?,?,?,?)""",
            (_key,_statement,_severity,"ACTIVE",_mitigation,_evidence,stage15d_effective_at),
        )

    for _key,_question,_priority,_blocking,_next,_evidence in [
        ("RELEASE_SCALE_DETERMINISM","Does an independent release-scale execution reproduce the full scientific package exactly at the logical level?","CRITICAL",1,"Design and execute a second release-scale comparison with runtime-only metadata excluded from scientific parity.","/mnt/intelssd/rnatr_project/qc/15_stage15c_fullscale_bam_to_final/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.6/stage15c_full_empirical_run.qc.tsv"),
        ("FULLSCALE_RESTART_RESUME","Can the full run reject corrupt checkpoints, selectively resume, match the clean package, and become a second-resume no-op?","CRITICAL",1,"Run intentional-stop/corruption/selective-resume validation from the v0.1.6 checkpoint inventory.","/mnt/intelssd/rnatr_project/qc/15_stage15c_fullscale_bam_to_final/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.6/stage15c_fullscale_checkpoint_manifest.tsv"),
        ("PRE_RELEASE_CANDIDATE_ARCHITECTURE_AUDIT","Are SSOT, active paths, frozen schema/contracts, runtime-generated artifacts, restart, biology roadmap, and release gates globally consistent?","CRITICAL",1,"Run PRE_RELEASE_CANDIDATE Architecture consistency audit after determinism/restart.","/mnt/intelssd/rnatr_project/qc/15_stage15c_fullscale_bam_to_final/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.6/stage15c_full_empirical_run.qc.tsv"),
        ("ACTIVE_PATH_PROMOTION","When and how should the validated Stage15 candidate replace the legacy active P0/P1 pipeline?","CRITICAL",1,"Perform explicit versioned promotion only after remaining Core Freeze gates pass.","/mnt/intelssd/rnatr_project/qc/15_stage15c_fullscale_bam_to_final/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.6/stage15c_full_empirical_run.qc.tsv"),
        ("CLEAN_INSTALL_INTERNAL_BETA","Can an independent clean machine install software/references and reproduce a test run without developer-local paths?","HIGH",1,"Implement and validate G25-G30 before v0.5.0-rc1/internal beta.","/mnt/intelssd/rnatr_project/validation/release_gates_v0.3.0.tsv"),
        ("G31_BIOLOGICAL_CANDIDATE_ENTRY_INTERPRETATION","What biological and algorithmic factors explain the broad candidate-entry rate and ~4.9 loci/read, and can entry be narrowed without recall loss?","MODERATE",0,"Defer to biology/optimization phase; retain exact/proximal/catalog-source decomposition.","/mnt/intelssd/rnatr_project/qc/15_stage15d_g31_row_expansion_audit/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/candidate_entry_rate_and_reason_audit.tsv"),
    ]:
        conn.execute(
            """INSERT OR REPLACE INTO open_questions(
                   question_key,question,priority,status,blocking,next_action,evidence_path,effective_at
               ) VALUES(?,?,?,?,?,?,?,?)""",
            (_key,_question,_priority,"OPEN",_blocking,_next,_evidence,stage15d_effective_at),
        )

    for _failure_id,_attempt,_summary,_root_cause,_resolution,_source,_superseded in [
        ("stage15c_full_v014_runtime_runid_binding","v0.1.4","Full execution stopped in the first 11b wave after fresh partition.","Runtime-generated 11b scripts retained the deterministic-500k analysis run ID and searched for nonexistent 500k-named shard BAMs.","v0.1.6 audits 432 generated scripts and 3312 path bindings before the timer/partition and uses fresh artifacts.","/mnt/intelssd/rnatr_project/qc/15_stage15c_fullscale_bam_to_final/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.4/stage15c_full_empirical_run.failure.txt","rnatr_stage15c_full5312696_bam_to_final_v0.1.6"),
        ("stage15c_full_v015_runtime_path_binding","v0.1.5","The v0.1.5 runner was rejected before preflight/execution.","Run ID rebinding did not replace old 500k candidate/window paths and BOUND_SOURCE_ROOT was undefined.","v0.1.6 binds and audits full runtime ID plus path graph; v0.1.5 artifacts were not reused.","/mnt/intelssd/rnatr_project/qc/15_stage15c_runtime_bound_runner_build/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.5","rnatr_stage15c_full5312696_bam_to_final_v0.1.6"),
    ]:
        conn.execute(
            """INSERT OR REPLACE INTO failures(
                   failure_id,run_id,stage_key,attempt_version,status,summary,
                   root_cause,resolution,source_path,superseded_by,recorded_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (_failure_id,stage15d_full_run,"15C_FULL_EMPIRICAL_BAM_TO_FINAL",_attempt,
             "RESOLVED",_summary,_root_cause,_resolution,_source,_superseded,stage15d_effective_at),
        )

    for _path_text,_expected in {**stage15d_evidence_guards, **stage15d_source_guards}.items():
        _s15d_source(_path_text,"stage15d_fullscale_registration_evidence",_expected)


    # Stage 15E determinism/restart acceptance and Stage 15F registration v0.1.1
    stage15e_effective_at = '2026-08-10T12:30:00+00:00'
    stage15e_base_run = 'ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1'
    stage15e_validation_run = 'ENCSR307SHM_stage15e_determinism_restart_hashseed20260810_v1'
    stage15e_evidence_guards = {'/mnt/intelssd/rnatr_project/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15e_combined_determinism_restart.qc.tsv': '13a827f1f00aa433476913a37bfa28b73d8415e607390f8f867c942100c9d544', '/mnt/intelssd/rnatr_project/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15e_first_resume.qc.tsv': '87f274eb3e0b07dad8c518bb029e749f36ff0c1001dd44d606d25da0e3a30ef6', '/mnt/intelssd/rnatr_project/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15e_intentional_stop.qc.tsv': '77dcc41f058ccc2f86c006a7394fa0cacc85766b9b25b656e0d7a257160e3ebb', '/mnt/intelssd/rnatr_project/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/state/stage15e_state.json': 'd81316286a47fd5647768c7f39109a33e7f3fa6bb90b8cf1633df92d24cf3454', '/mnt/intelssd/rnatr_project/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/guards/second_resume_noop.source_and_state_guards.tsv': '6cec8a72a4bc6828cf55799935d2cd1e5db80f795a6c9a8f95af15cc87c691ba', '/mnt/intelssd/rnatr_project/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/checkpoint/intentional_stop.checkpoint_rehash.qc.tsv': '4f11cddf740a113c52697e89851fedf8f6f60bfd71a4fd6ee8fa8f35d866f579', '/mnt/intelssd/rnatr_project/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/checkpoint/first_resume.checkpoint_rehash.qc.tsv': 'bd34f9f63143f3c1a17fee44ea71726e5e97e25d84b495aec5da9eff6317b8b1', '/mnt/intelssd/rnatr_project/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/negative_fixture/corrupt_checkpoint_rejection.qc.tsv': 'aa1284c8ed5d9e14663d79bd6afe40b5479c61e8ed2ec4722fdd688477087199', '/mnt/intelssd/rnatr_project/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/determinism/target_caller_parity.tsv': '7aaa721c28231b68e2d47497ac20c07124ac32eed9fe6fdd6e5c4965ee6d69eb', '/mnt/intelssd/rnatr_project/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/determinism/target_caller_qc_stable_parity.tsv': 'd1d6ca434d9aff7e8b4f5d3f02dc291cabd36ce4c007ec9fed30d5f832e3e02a', '/mnt/intelssd/rnatr_project/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/determinism/target_materializer_qc_stable_parity.tsv': '1c8b044aefcabe5eeb5e1de01abc02daa27c467cdc608693377195745dfa98a5', '/mnt/intelssd/rnatr_project/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/determinism/target_materializer_table_parity.tsv': '363261726f1945a4c9ff40bd9681bce8dc4718f05f31e45ffdb983b3b57dc639', '/mnt/intelssd/rnatr_project/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/determinism/full_package_table_parity.tsv': 'aa1c7b14f5d756f63318f57c3b37639481850296c65f73edef62b33e6be9569c', '/mnt/intelssd/rnatr_project/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/determinism/package_manifest_logical_parity.tsv': '22002643de110544781dec1e51472a88ed2ebf41837524923eebc20fe58a234f', '/mnt/intelssd/rnatr_project/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/reconstruction/stage15e_reconstruction.qc.tsv': 'd9d64701680c71b904e1df1e195c0018b61742cc5f14eec22e998c55c4071671', '/mnt/intelssd/rnatr_project/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15c_fullscale_validators.tsv': '45a8b5dd7be3f91ae054ffda3ae4c3dd5512e024041752d28b5695c84465a185', '/mnt/intelssd/rnatr_project/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15a_performance_atomic_publication.tsv': '6cff188fd1a7da50b5256cb45ed72e9ddb16c35452696d1d1b69af17a65a0944', '/mnt/intelssd/rnatr_project/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/noop/scientific_artifact_snapshot.tsv': '294f54661e2faadf86619e340633569773e788e1238848e95c9e6f9dea5f25bf', '/mnt/intelssd/rnatr_project/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/noop/second_resume_artifact_immutability.tsv': '85f7a23420c4f75d54085a316b271eecf0657ef6dfe28f5ff5c87a48318cd312', '/mnt/intelssd/rnatr_project/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/noop/second_resume_noop.qc.tsv': '2c3087affb375f656e4b13d0167f77cecf85644817cdcd585678e4b9f7e057ac', '/mnt/intelssd/rnatr_project/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/command_ledger.tsv': 'b003fb5c0ee344f0460cfb0fe70b28f7d2a2cb243948db13f129917e7dfe44dc', '/mnt/intelssd/rnatr_project/results/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/package_full/package_manifest.tsv': 'dd64ad79ef1301ed44255112e9b9a95ec42398a03c7fb6898ccb5417371ec06f', '/mnt/intelssd/rnatr_project/results/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/package_full/materialization.qc.tsv': 'f0090a2b82d8b4302aeb83b68448b1a18d51d454b8da510757d9fc17f26a54d6', '/mnt/intelssd/rnatr_project/qc/15_stage15c_fullscale_bam_to_final/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.6/stage15c_full_empirical_run.qc.tsv': '3b95addc1e7aa50ddf22d90dab3373025b9c7b41569fcb2aaea7d2910b35fd07', '/mnt/intelssd/rnatr_project/qc/15_stage15c_fullscale_bam_to_final/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.6/stage15c_fullscale_checkpoint_manifest.tsv': 'f00d67e28413d66730b8c2ffab0f52b9ce9e1553e5cc9a3f9d768e4a7a0083b4', '/mnt/intelssd/rnatr_project/results/15_stage15c_fullscale_bam_to_final/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.6/package_full/package_manifest.tsv': '335058228a3f3c4205161f3d24b208009175aed5e50f995a74e04100b4f3a738'}
    stage15e_source_guards = {'/mnt/intelssd/rnatr_project/scripts/rnatr_stage15e_run_combined_determinism_restart_v0.1.0.py': '70998ac5c04d01d95955a3fecddbe7aa685f9d9fa396993f0fe616058558730d', '/mnt/intelssd/rnatr_project/scripts/rnatr_stage15f_register_stage15e_and_collect_prerc_preflight_v0.1.1.py': '550cb54c6cdedb2299c16d3f40b2ed3f9695fd37abb24aa2ff04d4a0ea245c43', '/mnt/intelssd/rnatr_project/docs/stage15e/RNA_TR_Scout_Stage15E_determinism_restart_acceptance_v0.1.1.md': '18c053c612baef0d729641af7b1707d5c2db355ecbf6686d3291a10918832baf', '/mnt/intelssd/rnatr_project/docs/stage15e/RNA_TR_Scout_Stage15E_combined_final_Pro_audit_v0.1.0.tsv': 'a1c2e37d6e5202c9242e18586fc2ecfcfb2976f24ba19e3efed3d303899047c6', '/mnt/intelssd/rnatr_project/docs/governance/RNA_TR_Scout_Core_Freeze_governance_requirements_v0.1.0.md': 'e2fd5db5fd8627528aefcb0cc8aabd07cfe93fd8330b880d98f48fc460f2e4e6', '/mnt/intelssd/rnatr_project/metadata/stage15e/determinism_restart_v0.1.0/final_bundle_binding.json': '09df9c4ae7f912259d275590efb9eb198731851d98bfe7f0345ea7a70274988f', '/mnt/intelssd/rnatr_project/validation/release_gates_v0.3.1.tsv': '7d6795222e05d7892118bf0b4dde392b2e33b820934be987d632290f0722fda8'}

    def _s15f_sha256(path):
        digest = hashlib.sha256()
        with Path(path).open("rb") as handle:
            for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    def _s15f_guard(path_text, expected):
        path = Path(path_text)
        if not path.is_file() or path.stat().st_size <= 0:
            raise RuntimeError("Stage15E registration evidence missing: %s" % path)
        observed = _s15f_sha256(path)
        if observed != expected:
            raise RuntimeError("Stage15E registration evidence drift: %s: %s != %s" % (path, observed, expected))
        return path

    for _s15f_path, _s15f_expected in {**stage15e_evidence_guards, **stage15e_source_guards}.items():
        _s15f_guard(_s15f_path, _s15f_expected)

    _s15f_parent = conn.execute("SELECT dataset_id FROM runs WHERE run_id=?", (stage15e_base_run,)).fetchone()
    if _s15f_parent is None:
        raise RuntimeError("Stage15E registration requires registered Stage15C full run")
    _s15f_dataset_id = _s15f_parent[0]

    def _s15f_stage(key, order, name, purpose, category, implementation_status, notes):
        conn.execute("""INSERT INTO stage_definitions(stage_key,stage_order,name,purpose,category,implementation_status,notes)
                        VALUES(?,?,?,?,?,?,?) ON CONFLICT(stage_key) DO UPDATE SET stage_order=excluded.stage_order,
                        name=excluded.name,purpose=excluded.purpose,category=excluded.category,
                        implementation_status=excluded.implementation_status,notes=excluded.notes""",
                     (key,order,name,purpose,category,implementation_status,notes))

    def _s15f_run(run_id,parent_run_id,role,pipeline_version,status,root_path,notes):
        conn.execute("""INSERT INTO runs(run_id,dataset_id,parent_run_id,run_role,pipeline_version,status,started_at,ended_at,root_path,notes)
                        VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(run_id) DO UPDATE SET dataset_id=excluded.dataset_id,
                        parent_run_id=excluded.parent_run_id,run_role=excluded.run_role,pipeline_version=excluded.pipeline_version,
                        status=excluded.status,root_path=excluded.root_path,notes=excluded.notes""",
                     (run_id,_s15f_dataset_id,parent_run_id,role,pipeline_version,status,None,None,root_path,notes))

    def _s15f_impl(impl_id,stage_key,version,script_path,script_sha,lifecycle,rationale,evidence_path):
        conn.execute("""INSERT OR REPLACE INTO implementations(implementation_id,stage_key,version,script_path,script_sha256,
                        validator_path,validator_sha256,package_version,parameters_json,lifecycle_status,
                        supersedes_implementation_id,rationale,evidence_path,effective_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (impl_id,stage_key,version,script_path,script_sha,None,None,"v0.4.2",None,lifecycle,None,rationale,evidence_path,stage15e_effective_at))

    def _s15f_run_stage(run_id,stage_key,impl_id,attempt,status,qc_path,qc_status,notes):
        conn.execute("""INSERT OR REPLACE INTO run_stages(run_id,stage_key,implementation_id,attempt_tag,status,command_text,
                        qc_path,qc_status,started_at,ended_at,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                     (run_id,stage_key,impl_id,attempt,status,None,qc_path,qc_status,None,None,notes))

    def _s15f_metric(name,value_text,value_num,unit,denominator,source_path,status="CURRENT"):
        conn.execute("""INSERT OR REPLACE INTO metrics(run_id,stage_key,metric_name,value_text,value_num,unit,
                        denominator_num,source_path,metric_status,recorded_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                     (stage15e_validation_run,"15E_RELEASE_SCALE_DETERMINISM_RESTART",name,str(value_text),value_num,unit,
                      denominator,str(source_path),status,stage15e_effective_at))

    def _s15f_decision(key,category,title,statement,confidence,rationale,evidence_path):
        decision_id = "decision_" + hashlib.sha256(key.encode()).hexdigest()[:20]
        conn.execute("""INSERT OR REPLACE INTO decisions(decision_id,decision_key,category,title,statement,status,confidence,
                        effective_at,supersedes_decision_id,rationale,evidence_path) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                     (decision_id,key,category,title,statement,"ACTIVE",confidence,stage15e_effective_at,None,rationale,str(evidence_path)))

    def _s15f_interpretation(key,fact,interpretation,do_not,confidence,evidence_path,metrics):
        interpretation_id = "interpretation_" + hashlib.sha256(key.encode()).hexdigest()[:20]
        conn.execute("""INSERT OR REPLACE INTO interpretations(interpretation_id,interpretation_key,fact_statement,interpretation,
                        do_not_interpret_as,status,confidence,effective_at,supersedes_interpretation_id,evidence_path,evidence_metrics_json)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                     (interpretation_id,key,fact,interpretation,do_not,"ACTIVE",confidence,stage15e_effective_at,None,
                      str(evidence_path),json.dumps(metrics,sort_keys=True)))

    def _s15f_contract(key,name,state,statement,impl_id,evidence_path,status="ACTIVE"):
        contract_id = "contract_" + hashlib.sha256(key.encode()).hexdigest()[:20]
        conn.execute("""INSERT OR REPLACE INTO algorithm_contracts(contract_id,component_key,component_name,implementation_state,
                        contract_statement,active_implementation_id,evidence_path,effective_at,status) VALUES(?,?,?,?,?,?,?,?,?)""",
                     (contract_id,key,name,state,statement,impl_id,str(evidence_path),stage15e_effective_at,status))

    def _s15f_source(path_text,source_type,expected):
        path = _s15f_guard(path_text,expected)
        mtime = __import__("datetime").datetime.fromtimestamp(path.stat().st_mtime,__import__("datetime").timezone.utc).replace(microsecond=0).isoformat()
        conn.execute("""INSERT INTO source_documents(source_type,path,sha256,bytes,mtime_utc,content_status,ingested_at)
                        VALUES(?,?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET source_type=excluded.source_type,
                        sha256=excluded.sha256,bytes=excluded.bytes,mtime_utc=excluded.mtime_utc,
                        content_status=excluded.content_status,ingested_at=excluded.ingested_at""",
                     (source_type,str(path),expected,path.stat().st_size,mtime,"PRESENT",stage15e_effective_at))

    _s15f_stage("15E_RELEASE_SCALE_DETERMINISM_RESTART",152.0,"Stage 15E release-scale determinism and restart/resume",
                "Validate checkpoint integrity, different-hash-seed scientific parity, intentional stop, selective caller-to-final resume, full package reconstruction, atomic publication, and second-resume idempotence at full scale.",
                "production_validation","IMPLEMENTED_WITH_SCOPE_AMENDMENT",
                "PASS for checkpoint-based reconstruction with one fresh target shard and 143 frozen reused shards; not an upstream BAM partition/11b/11d3/11e full rerun or cross-hardware test.")
    _s15f_stage("15C_FULL_EMPIRICAL_BAM_TO_FINAL",151.8,"Stage 15C full 5.31M empirical BAM-to-final",
                "Run mapping-complete full BAM through target assignment, projection, caller, materialization, validation, and atomic publication.",
                "production_validation","IMPLEMENTED_WITH_GATE",
                "Correctness/memory/storage/publication PASS and runtime PASS_WITH_DOCUMENTED_TOLERANCE; Stage15E subsequently closed checkpoint-based release-scale determinism and selective caller-to-final restart/resume.")
    conn.execute("UPDATE stage_definitions SET notes=? WHERE stage_key='15A_BAM_TO_FINAL_PERFORMANCE'",
                 ("Historical isolated candidate. Deterministic 500k, full empirical execution, and Stage15E scoped determinism/restart subsequently passed; 30-minute optimization remains nonblocking for first freeze.",))
    conn.execute("UPDATE stage_definitions SET notes=? WHERE stage_key='15A_RESTART_RESUME_VALIDATION'",
                 ("Historical 100k selective-resume validation. Stage15E subsequently passed full-scale checkpoint-based caller-to-final selective restart/resume and no-op verification.",))
    conn.execute("UPDATE stage_definitions SET notes=? WHERE stage_key='15A_DETERMINISTIC_SCALING'",
                 ("Historical 250k scaling gate. Deterministic 500k and full empirical execution subsequently passed.",))

    _s15f_run(stage15e_validation_run,stage15e_base_run,"RELEASE_SCALE_DETERMINISM_RESTART_VALIDATION",
               "rnatr_stage15e_combined_determinism_restart_v0.1.0","PASS_WITH_SCOPE_AMENDMENT",
               '/mnt/intelssd/rnatr_project/results/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0',
               "Different-hash-seed target caller/materializer parity, 144-shard exact package reconstruction, checkpoint rejection, intentional stop/selective resume, atomic publication, and second-resume no-op PASS within the frozen checkpoint-based scope.")
    conn.execute("UPDATE runs SET notes=? WHERE run_id=?",
                 ("Full 5.31M BAM-to-final correctness PASS at 60.041256352 min with documented tolerance. Stage15E subsequently closed checkpoint-based release-scale reconstruction and selective caller-to-final restart/resume; active pipeline remains unpromoted.",stage15e_base_run))
    _s15f_impl("impl_stage15e_combined_determinism_restart_v0_1_0","15E_RELEASE_SCALE_DETERMINISM_RESTART","v0.1.0",
               '/mnt/intelssd/rnatr_project/scripts/rnatr_stage15e_run_combined_determinism_restart_v0.1.0.py','70998ac5c04d01d95955a3fecddbe7aa685f9d9fa396993f0fe616058558730d',"VALIDATION_ONLY_FROZEN_EVIDENCE",
               "Governance/validation harness; not an active scientific production entry point.",'/mnt/intelssd/rnatr_project/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15e_combined_determinism_restart.qc.tsv')
    _s15f_run_stage(stage15e_validation_run,"15E_RELEASE_SCALE_DETERMINISM_RESTART","impl_stage15e_combined_determinism_restart_v0_1_0",
                     "hashseed20260810_intentional_stop_resume_noop","PASS",
                     '/mnt/intelssd/rnatr_project/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15e_combined_determinism_restart.qc.tsv',"PASS",
                     "Checkpoint-based scope explicitly excludes upstream BAM partition/11b/11d3/11e full rerun and cross-hardware validation.")

    _s15f_qc = Path('/mnt/intelssd/rnatr_project/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15e_combined_determinism_restart.qc.tsv')
    _s15f_caller = Path('/mnt/intelssd/rnatr_project/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/determinism/target_caller_qc_stable_parity.tsv')
    _s15f_materializer = Path('/mnt/intelssd/rnatr_project/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/determinism/target_materializer_qc_stable_parity.tsv')
    _s15f_package = Path('/mnt/intelssd/rnatr_project/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/determinism/full_package_table_parity.tsv')
    _s15f_rehash = Path('/mnt/intelssd/rnatr_project/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/checkpoint/first_resume.checkpoint_rehash.qc.tsv')
    _s15f_noop = Path('/mnt/intelssd/rnatr_project/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/noop/second_resume_noop.qc.tsv')
    for _name,_text,_num,_unit,_den,_source in [
        ("scope","CHECKPOINT_BASED_RELEASE_SCALE_RECONSTRUCTION_NOT_UPSTREAM_BAM_PARTITION_11B_11D3_11E_RERUN",None,None,None,_s15f_qc),
        ("baseline_hash_seed","0",0,None,None,_s15f_qc),("determinism_hash_seed","20260810",20260810,None,None,_s15f_qc),
        ("checkpoint_artifacts","1884",1884,"artifacts",None,_s15f_rehash),("checkpoint_bytes","140029015504",140029015504,"bytes",None,_s15f_rehash),
        ("target_shard","shard_065",65,"shard_index",None,_s15f_qc),("target_caller_input_rows","146558",146558,"rows",None,_s15f_caller),
        ("target_caller_called_rows","61333",61333,"rows",None,_s15f_caller),("target_materializer_repeat_event_rows","61323",61323,"rows",None,_s15f_materializer),
        ("reconstruction_shards","144",144,"shards",None,_s15f_qc),("fresh_target_shards","1",1,"shards",144,_s15f_qc),("frozen_reused_shards","143",143,"shards",144,_s15f_qc),
        ("read_evidence_rows","20656258",20656258,"rows",None,_s15f_package),("general_repeat_calls_rows","20656258",20656258,"rows",None,_s15f_package),
        ("repeat_events_rows","8523140",8523140,"rows",None,_s15f_package),("repeat_segments_rows","8573315",8573315,"rows",None,_s15f_package),
        ("repeat_interruptions_rows","43399",43399,"rows",None,_s15f_package),("frozen_validator_count","6",6,"validators",None,_s15f_qc),
        ("second_resume_scientific_commands","0",0,"commands",None,_s15f_noop),("clean_runtime_minutes","60.041256352",60.041256352,"minutes",None,_s15f_qc),
        ("release_scale_determinism","PASS_CHECKPOINT_BASED_RECONSTRUCTION_SCOPE",None,None,None,_s15f_qc),
        ("fullscale_restart_resume","PASS_SELECTIVE_CALLER_TO_FINAL_SCOPE",None,None,None,_s15f_qc),
        ("second_resume_noop","PASS",None,None,None,_s15f_noop),
    ]: _s15f_metric(_name,_text,_num,_unit,_den,_source)

    conn.execute("UPDATE decisions SET status='SUPERSEDED' WHERE decision_key='stage15a_restart_resume_scope_v0_1_0' AND status='ACTIVE'")
    _s15f_decision("stage15e_determinism_restart_acceptance_v0_1_0","production_validation","Accept Stage15E scoped release-scale determinism and restart/resume",
                   "Accept exact checkpoint-based full-package reconstruction and selective caller-to-final restart/resume with corrupt-manifest rejection, atomic publication, and second-resume no-op. Preserve the explicit exclusion of upstream BAM partition/11b/11d3/11e full rerun and cross-hardware claims.",
                   "HIGH","All frozen Stage15E validators and parity checks passed and the clean Stage15C benchmark remained unchanged.",_s15f_qc)
    _s15f_decision("stage15e_cross_hardware_not_closed_v0_1_0","release_readiness","Do not close cross-hardware determinism from Stage15E",
                   "Stage15E is same-machine checkpoint-based evidence. G28 remains OPEN_PLANNED until supported hardware/concurrency profiles and an independent machine are compared.",
                   "HIGH","The validated scope is narrower than G28.",_s15f_qc)
    _s15f_decision("stage15e_active_promotion_remains_deferred_v0_1_0","architecture","Keep Stage15 candidate provisional after Stage15E",
                   "Do not modify current_pipeline during Stage15E registration. Run PRE_RELEASE_CANDIDATE Architecture consistency audit, then perform an explicit versioned active-path promotion only after all Core Freeze governance gates are explicitly accounted for.",
                   "HIGH","Stage15E closes determinism/restart but not architecture audit, promotion, Core Freeze Packet, golden regression, documentation canonicalization, or clean-install gates.",'/mnt/intelssd/rnatr_project/validation/release_gates_v0.3.1.tsv')
    _s15f_decision("core_freeze_preservation_artifacts_required_v0_1_0","core_freeze_governance","Require Core Freeze Packet and golden regression suite",
                   "Core Freeze requires a versioned checksummed Core Freeze Packet plus a machine-executable golden regression suite. SSOT alone is not sufficient to preserve the long-term scientific contract.",
                   "HIGH","The packet preserves the concise human-readable contract and the regression suite enforces it mechanically.",'/mnt/intelssd/rnatr_project/docs/governance/RNA_TR_Scout_Core_Freeze_governance_requirements_v0.1.0.md')
    _s15f_decision("authoritative_originals_required_for_prerc_and_freeze_v0_1_0","architecture_governance","Require exact originals for PRE-RC and Core Freeze reconstruction",
                   "PRE_RELEASE_CANDIDATE and Core Freeze conclusions must be based on reread original code, SSOT, schema, contracts, validators, runners, manifests, and formal evidence. Conversation summaries and memory are not authoritative.",
                   "HIGH","Missing, ambiguous, or size-capped originals must remain unresolved until supplied and reread.",'/mnt/intelssd/rnatr_project/docs/governance/RNA_TR_Scout_Core_Freeze_governance_requirements_v0.1.0.md')
    _s15f_decision("project_docs_and_downloads_canonicalization_v0_1_0","artifact_governance","Canonicalize project docs before Downloads cleanup",
                   "Promote project-wide authoritative documents to a durable one-source layout, preserve stage-local history or pointers, and only then classify, move, or delete accumulated Downloads artifacts by checksum-backed inventory.",
                   "HIGH","This prevents deletion of active evidence and avoids competing authoritative copies.",'/mnt/intelssd/rnatr_project/docs/governance/RNA_TR_Scout_Core_Freeze_governance_requirements_v0.1.0.md')

    _s15f_interpretation("stage15e_full_package_parity_v0_1_0","The reconstructed five-table package matched the clean Stage15C package at all required plain/raw and gzip/logical comparison points.",
                         "Within the checkpoint-based scope, scientific output is reproducible under a different hash seed and selective target-shard recomputation.",
                         "An independent upstream full rerun, arbitrary upstream recovery, or cross-machine reproducibility.","HIGH",_s15f_package,
                         {"reconstruction_shards":144,"fresh_target_shards":1,"frozen_reused_shards":143})
    _s15f_interpretation("stage15e_second_resume_idempotence_v0_1_0","The second resume executed zero scientific commands and preserved 20 scientific artifacts by size, mtime, inode, device, and SHA-256.",
                         "The completed Stage15E resume state is idempotent and does not silently rewrite the scientific package.",
                         "A guarantee for future changed code, references, parameters, or arbitrary upstream checkpoints.","HIGH",_s15f_noop,{"scientific_commands":0,"artifacts":20})
    _s15f_interpretation("stage15e_corruption_fixture_scope_v0_1_0","The negative fixture changed the expected SHA in a copied manifest and the same checkpoint validator rejected the mismatch without modifying source artifacts.",
                         "The SHA-binding rejection path is validated.",
                         "A physical bit-flip of the source checkpoint artifact or every possible corruption mode.","HIGH",
                         '/mnt/intelssd/rnatr_project/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/negative_fixture/corrupt_checkpoint_rejection.qc.tsv',{"source_artifact_corrupted":False})

    conn.execute("UPDATE algorithm_contracts SET status='SUPERSEDED' WHERE component_key IN ('stage15a_bam_to_final_gate_v010','stage15a_deterministic_scaling_v0_1_2','stage15a_performance_candidate_v0221','stage15a_restart_resume_v0_1_0') AND status='ACTIVE'")
    _s15f_contract("stage15e_release_scale_determinism_restart_v0_1_0","Stage15E release-scale determinism and restart/resume",
                   "PASS_CHECKPOINT_BASED_RECONSTRUCTION_AND_SELECTIVE_CALLER_TO_FINAL_RESUME",
                   "Rehash the frozen 1,884-artifact checkpoint before reuse; reject SHA drift; fresh-run the target caller under a different hash seed; stop before materialization; selectively resume materializer and 144-shard reconstruction; require clean-package parity and all frozen validators before atomic publication; require second resume to be a no-op. Scope excludes upstream BAM partition/11b/11d3/11e full rerun and cross-hardware claims.",
                   "impl_stage15e_combined_determinism_restart_v0_1_0",_s15f_qc)
    _s15f_contract("stage15c_fullscale_execution_v0_1_6","Stage15C full-scale execution contract",
                   "EMPIRICAL_FULLSCALE_PASS_WITH_TOLERANCE_STAGE15E_DETERMINISM_RESTART_PASS_SCOPED",
                   "Use 144 read-coherent shards, concurrency 12, caller workers 2/shard, validator workers 3, 512M external sort, PYTHONHASHSEED=0 for the clean benchmark, prepartition runtime-script/path audit, bounded validation, and atomic publication. Stage15E adds checkpoint-based different-hash-seed reconstruction and selective caller-to-final resume evidence; active promotion and G25-G30 remain open.",
                   "impl_stage15c_full_runner_v0_1_6",_s15f_qc)
    _s15f_contract("release_readiness_g25_g30_v0_1_0","Internal-beta release readiness G25-G30","DESIGNED_NOT_IMPLEMENTED",
                   "Portable reference bootstrap, resource detection, adaptive concurrency, cross-hardware determinism, clean-machine install, and empirical hardware profiles remain required before internal beta/release candidate. Stage15E does not close these gates.",
                   None,'/mnt/intelssd/rnatr_project/validation/release_gates_v0.3.1.tsv')
    _s15f_contract("core_freeze_preservation_governance_v0_1_0","Core Freeze preservation and governance contract","DESIGNED_REQUIRED_BEFORE_CORE_FREEZE",
                   "Before Core Freeze, reread exact originals; create a checksummed Core Freeze Packet and golden regression suite; establish one canonical project-wide documentation layout with stage-local history/pointers; and defer Downloads deletion until an authoritative retention inventory is verified.",
                   None,'/mnt/intelssd/rnatr_project/docs/governance/RNA_TR_Scout_Core_Freeze_governance_requirements_v0.1.0.md')

    for _key,_question,_priority,_status,_blocking,_next,_evidence in [
        ("RELEASE_SCALE_DETERMINISM","Does an independent release-scale execution reproduce the full scientific package exactly at the logical level?","RESOLVED","CLOSED",0,
         "Closed for checkpoint-based reconstruction by Stage15E. Preserve the explicit exclusion of upstream full rerun and cross-hardware evidence; G28 remains open.",str(_s15f_qc)),
        ("FULLSCALE_RESTART_RESUME","Can the full run reject corrupt checkpoints, selectively resume, match the clean package, and become a second-resume no-op?","RESOLVED","CLOSED",0,
         "Closed for copied-manifest SHA rejection and selective caller-to-final resume by Stage15E; arbitrary upstream recovery is outside the accepted scope.",str(_s15f_qc)),
        ("GENERAL_CALLER_PRODUCTION_INTEGRATION","Can the exact-parity Stage 15A candidate remain deterministic, restartable, artifact-complete, and within the 60-minute hard ceiling as BAM input increases, while continuing toward the 30-minute target?","RESOLVED","CLOSED",0,
         "Core integration is validated at full scale with documented 60-62 minute tolerance and Stage15E scoped determinism/restart. Continue 30-minute optimization as a separate nonblocking engineering target.",str(_s15f_qc)),
        ("PRE_RELEASE_CANDIDATE_ARCHITECTURE_AUDIT","Are SSOT, active paths, frozen schema/contracts, runtime-generated artifacts, restart, biology roadmap, and release gates globally consistent?","CRITICAL","OPEN",1,
         "Run the PRE_RELEASE_CANDIDATE Architecture consistency audit immediately using the Stage15F post-registration input bundle.",str(_s15f_qc)),
        ("ARCHITECTURE_CONSISTENCY_AUDIT_CLOSURE","Are SSOT, active code/path, schema/contracts, performance gates, validation/restart scope, biology roadmap, and implementation lifecycle mutually consistent at each major checkpoint?","CRITICAL","OPEN",1,
         "Post-250k audit is complete. Perform PRE_RELEASE_CANDIDATE audit now and preserve PRE_BIOLOGY audit as a later mandatory checkpoint.",str(_s15f_qc)),
        ("ACTIVE_PATH_PROMOTION","When and how should the validated Stage15 candidate replace the legacy active P0/P1 pipeline?","CRITICAL","OPEN",1,
         "After PRE_RELEASE_CANDIDATE audit closure and an explicit plan for G32-G34, perform a versioned promotion with rollback and golden-regression guards.",str(_s15f_qc)),
        ("CLEAN_INSTALL_INTERNAL_BETA","Can an independent clean machine install software/references and reproduce a test run without developer-local paths?","HIGH","OPEN",1,
         "Implement and validate G25-G30 before v0.5.0-rc1/internal beta.",str('/mnt/intelssd/rnatr_project/validation/release_gates_v0.3.1.tsv')),
        ("CORE_FREEZE_PACKET","Has a versioned checksummed Core Freeze Packet been reconstructed from exact originals and accepted as the concise human-readable Core contract?","CRITICAL","OPEN",1,
         "After PRE-RC architecture reconstruction and active-path decision, create and audit the packet specified by G32.",'/mnt/intelssd/rnatr_project/docs/governance/RNA_TR_Scout_Core_Freeze_governance_requirements_v0.1.0.md'),
        ("GOLDEN_REGRESSION_SUITE","Does a fixed-input expected-output suite mechanically enforce the frozen Core scientific contract, including exact/logical parity rules and negative fixtures?","CRITICAL","OPEN",1,
         "Build, run, and freeze the G33 suite before Core Freeze; future biology and performance changes must run it.",'/mnt/intelssd/rnatr_project/docs/governance/RNA_TR_Scout_Core_Freeze_governance_requirements_v0.1.0.md'),
        ("PROJECT_WIDE_DOCS_CANONICALIZATION","Is there one unambiguous project-wide authoritative location for architecture, governance, contracts, Core Freeze, and regression documents?","CRITICAL","OPEN",1,
         "Choose the canonical layout only after rereading the actual repository; retain stage-local copies as history or pointers and close G34 before Core Freeze.",'/mnt/intelssd/rnatr_project/docs/governance/RNA_TR_Scout_Core_Freeze_governance_requirements_v0.1.0.md'),
        ("DOWNLOADS_ARTIFACT_CLEANUP","Which accumulated Downloads artifacts must be preserved, moved, retained temporarily, or deleted?","MODERATE","OPEN",0,
         "After authoritative destinations and checksums are established, produce an explicit retention/deletion plan and execute cleanup separately.",'/mnt/intelssd/rnatr_project/docs/governance/RNA_TR_Scout_Core_Freeze_governance_requirements_v0.1.0.md'),
    ]:
        conn.execute("""INSERT OR REPLACE INTO open_questions(question_key,question,priority,status,blocking,next_action,evidence_path,effective_at)
                        VALUES(?,?,?,?,?,?,?,?)""",(_key,_question,_priority,_status,_blocking,_next,_evidence,stage15e_effective_at))

    for _key,_statement,_severity,_mitigation,_evidence in [
        ("STAGE15E_CHECKPOINT_BASED_SCOPE_NOT_UPSTREAM_FULL_RERUN","Stage15E proves checkpoint-based reconstruction with one fresh target shard and selective caller-to-final resume; it is not an independent upstream BAM partition/11b/11d3/11e full rerun.","HIGH","Do not generalize the evidence beyond the registered scope; retain G28 and clean-install gates.",str(_s15f_qc)),
        ("STAGE15E_SAME_MACHINE_NOT_CROSS_HARDWARE","Stage15E was executed on the same machine and does not establish scientific reproducibility across supported hardware/concurrency profiles.","HIGH","Close G28 with explicit cross-profile and cross-machine comparisons.",str(_s15f_qc)),
        ("STAGE15E_CORRUPTION_FIXTURE_IS_COPIED_MANIFEST_SHA_MISMATCH","The corruption negative fixture altered an expected SHA in a copied manifest, not the source checkpoint bytes.","MODERATE","Interpret as validation of SHA-bound rejection logic, not exhaustive physical-corruption coverage.",'/mnt/intelssd/rnatr_project/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/negative_fixture/corrupt_checkpoint_rejection.qc.tsv'),
        ("STAGE15C_ACTIVE_PIPELINE_NOT_PROMOTED","The empirically validated Stage15 candidate remains provisional and is not the current active pipeline.","HIGH","Run PRE_RELEASE_CANDIDATE audit, then explicit active-path promotion with rollback and golden regression.",str(_s15f_qc)),
        ("CORE_FREEZE_GOVERNANCE_ARTIFACTS_NOT_YET_CREATED","Core Freeze Packet, golden regression suite, and project-wide documentation canonicalization are required but not yet complete.","HIGH","Keep G32-G34 and the corresponding SSOT questions open until exact-original reconstruction and formal artifact audits pass.",'/mnt/intelssd/rnatr_project/docs/governance/RNA_TR_Scout_Core_Freeze_governance_requirements_v0.1.0.md'),
    ]:
        conn.execute("""INSERT OR REPLACE INTO limitations(limitation_key,statement,severity,status,mitigation,evidence_path,effective_at)
                        VALUES(?,?,?,?,?,?,?)""",(_key,_statement,_severity,"ACTIVE",_mitigation,_evidence,stage15e_effective_at))

    for _path_text,_expected in {**stage15e_evidence_guards, **stage15e_source_guards}.items():
        _s15f_source(_path_text,"stage15e_determinism_restart_registration_evidence",_expected)


    # Stage 15G PRE_RELEASE_CANDIDATE architecture remediation v0.1.1
    stage15g_contract_path = '/mnt/intelssd/rnatr_project/metadata/stage15g/prerc_architecture_remediation_v0.1.1/remediation_contract.json'
    stage15g_contract_sha256 = '00f4520c3c425c280e2742b455d1bc695610d9f30d2a48cb1a6f64a3889333d3'
    stage15g_lifecycle_plan_path = '/mnt/intelssd/rnatr_project/metadata/stage15g/prerc_architecture_remediation_v0.1.1/lifecycle_plan.tsv'
    stage15g_lifecycle_plan_sha256 = '9f21b04031e346e86f78f4e4f02994a8325c7920cf302c3f6f86f80af2c683c9'
    stage15g_source_guards = {'/mnt/intelssd/rnatr_project/scripts/rnatr_stage15g_remediate_prerc_architecture_v0.1.1.py': '321f415bd15b00684c5888c95a67ad32353d103118fb74dee5a9e375a11711bb', '/mnt/intelssd/rnatr_project/docs/stage15g/RNA_TR_Scout_PRE_RELEASE_CANDIDATE_Architecture_audit_v0.1.1.md': 'f4a550b42ee031091176eeabf5ddfc761adba56bda6c4a919d940f28e90dedfc', '/mnt/intelssd/rnatr_project/docs/stage15g/RNA_TR_Scout_Stage15G_PRE_RC_architecture_remediation_contract_v0.1.0.md': '94fae606568414305f8f273a5d293742696226988cc555aa542b0b6c993f7720', '/mnt/intelssd/rnatr_project/docs/stage15g/rnatr_prerc_architecture_audit_v0.1.1.tsv': '19892ef404fad1bf9b13a9bdeed4191b409aa5ec3b6fbc4fe20429c7033365cc', '/mnt/intelssd/rnatr_project/metadata/stage15g/prerc_architecture_remediation_v0.1.1/lifecycle_plan.tsv': '9f21b04031e346e86f78f4e4f02994a8325c7920cf302c3f6f86f80af2c683c9', '/mnt/intelssd/rnatr_project/metadata/stage15g/prerc_architecture_remediation_v0.1.1/state_remediation_plan.tsv': '65fd5ecf4dfd2dd5b8e22b6c518ae0251e8d9b63bdf7cc62d277e74336ca0510', '/mnt/intelssd/rnatr_project/metadata/stage15g/prerc_architecture_remediation_v0.1.1/remediation_contract.json': '00f4520c3c425c280e2742b455d1bc695610d9f30d2a48cb1a6f64a3889333d3', '/mnt/intelssd/rnatr_project/validation/release_gates_v0.3.2.tsv': '641fb974203decd7ce65d52057f6ba40ae2fd8f8a9060e84175d38b198eb6421', '/mnt/intelssd/rnatr_project/scripts/rnatr_stage15c_run_full5312696_bam_to_final_v0.1.6.py': 'cca6b2d4c6e773392d3a8c24cd2fd2a1f0a41a713338b4ccdec1ba7fab5bafcc', '/mnt/intelssd/rnatr_project/metadata/stage15c/runtime_path_binding_amendment_v0.1.6/rnatr_stage15c_runtime_path_binding_amendment_v0.1.6.json': 'c972777c13834ca9c16bc7d4aaecbebb20d46d3518d266a851f17a7b4751d97a', '/mnt/intelssd/rnatr_project/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15e_combined_determinism_restart.qc.tsv': '13a827f1f00aa433476913a37bfa28b73d8415e607390f8f867c942100c9d544'}

    def _s15g_sha256(path):
        digest = hashlib.sha256()
        with Path(path).open("rb") as handle:
            for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    def _s15g_guard(path_text, expected):
        path = Path(path_text)
        if not path.is_file() or path.stat().st_size <= 0:
            raise RuntimeError("Stage15G evidence missing: %s" % path)
        observed = _s15g_sha256(path)
        if observed != expected:
            raise RuntimeError("Stage15G evidence drift: %s: %s != %s" % (path, observed, expected))
        return path

    for _s15g_path, _s15g_expected in stage15g_source_guards.items():
        _s15g_guard(_s15g_path, _s15g_expected)
    _s15g_contract = json.loads(_s15g_guard(stage15g_contract_path, stage15g_contract_sha256).read_text(encoding="utf-8"))
    if _s15g_contract.get("schema") != "rnatr.stage15g.prerc_architecture_remediation.v1":
        raise RuntimeError("Stage15G contract schema mismatch")
    if _s15g_contract.get("version") != 'rnatr_stage15g_prerc_architecture_remediation_v0.1.1':
        raise RuntimeError("Stage15G contract version mismatch")
    _s15g_effective_at = _s15g_contract["effective_at"]

    _s15g_parent = conn.execute("SELECT dataset_id FROM runs WHERE run_id=?", ('ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1',)).fetchone()
    if _s15g_parent is None:
        raise RuntimeError("Stage15G requires registered Stage15C full run")
    _s15g_dataset_id = _s15g_parent[0]
    conn.execute("""INSERT INTO stage_definitions(stage_key,stage_order,name,purpose,category,implementation_status,notes)
                    VALUES(?,?,?,?,?,?,?) ON CONFLICT(stage_key) DO UPDATE SET stage_order=excluded.stage_order,name=excluded.name,
                    purpose=excluded.purpose,category=excluded.category,implementation_status=excluded.implementation_status,notes=excluded.notes""",
                 ("15G_PRERC_ARCHITECTURE_REMEDIATION",153.0,"Stage15G PRE-RC architecture remediation",
                  "Supersede stale current-state SSOT metadata, normalize implementation lifecycle, and close PRE-RC consistency without scientific or active-path mutation.",
                  "architecture_governance","IMPLEMENTED_SUPPORT_ONLY","G24 remains OPEN for PRE_BIOLOGY; no active pipeline promotion."))
    conn.execute("""INSERT INTO runs(run_id,dataset_id,parent_run_id,run_role,pipeline_version,status,started_at,ended_at,root_path,notes)
                    VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(run_id) DO UPDATE SET dataset_id=excluded.dataset_id,
                    parent_run_id=excluded.parent_run_id,run_role=excluded.run_role,pipeline_version=excluded.pipeline_version,
                    status=excluded.status,root_path=excluded.root_path,notes=excluded.notes""",
                 ('ENCSR307SHM_stage15g_prerc_architecture_remediation_v0_1_1',_s15g_dataset_id,'ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1',"architecture_governance",'rnatr_stage15g_prerc_architecture_remediation_v0.1.1',"PASS",None,None,
                  '/mnt/intelssd/rnatr_project/qc/15_stage15g_prerc_architecture_remediation/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.1',"Metadata/lifecycle remediation only; active pipeline, schema, and scientific outputs unchanged."))
    conn.execute("""INSERT OR REPLACE INTO implementations(implementation_id,stage_key,version,script_path,script_sha256,
                    validator_path,validator_sha256,package_version,parameters_json,lifecycle_status,supersedes_implementation_id,
                    rationale,evidence_path,effective_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                 ("impl_stage15g_prerc_architecture_remediation_v0_1_1","15G_PRERC_ARCHITECTURE_REMEDIATION","v0.1.1",
                  '/mnt/intelssd/rnatr_project/scripts/rnatr_stage15g_remediate_prerc_architecture_v0.1.1.py','321f415bd15b00684c5888c95a67ad32353d103118fb74dee5a9e375a11711bb',None,None,None,None,"SUPPORT",None,
                  "Versioned SSOT/governance updater; not a scientific production entry point.",'/mnt/intelssd/rnatr_project/docs/stage15g/RNA_TR_Scout_PRE_RELEASE_CANDIDATE_Architecture_audit_v0.1.1.md',_s15g_effective_at))
    conn.execute("""INSERT OR REPLACE INTO run_stages(run_id,stage_key,implementation_id,attempt_tag,status,command_text,qc_path,qc_status,started_at,ended_at,notes)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                 ('ENCSR307SHM_stage15g_prerc_architecture_remediation_v0_1_1',"15G_PRERC_ARCHITECTURE_REMEDIATION","impl_stage15g_prerc_architecture_remediation_v0_1_1",
                  "v0.1.1","PASS",None,'/mnt/intelssd/rnatr_project/qc/15_stage15g_prerc_architecture_remediation/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.1/stage15g_prerc_architecture_remediation.qc.tsv',"PASS",None,None,
                  "Successful SSOT rebuild is conditional on all exact remediation guards."))

    # Supersede exact historical/current rows. Source baseline and the immutable contract are SHA-bound.
    for _entry in _s15g_contract["state_plan"]:
        _table = _entry["object_type"]
        _expected = json.loads(_entry["expected_row_json"])
        if _table == "limitations":
            _keycol = "limitation_key"; _id = _entry["object_key"]
        elif _table == "decisions":
            _keycol = "decision_id"; _id = _entry["object_id"]
        elif _table == "interpretations":
            _keycol = "interpretation_id"; _id = _entry["object_id"]
        elif _table == "algorithm_contracts":
            _keycol = "contract_id"; _id = _entry["object_id"]
        else:
            raise RuntimeError("unknown Stage15G state-plan table: %s" % _table)
        _cursor = conn.execute("SELECT * FROM %s WHERE %s=?" % (_table,_keycol), (_id,))
        _row = _cursor.fetchone()
        if _row is None:
            raise RuntimeError("Stage15G expected row missing: %s:%s" % (_table,_id))
        _observed = {d[0]: _row[i] for i,d in enumerate(_cursor.description)}
        if _observed != _expected:
            raise RuntimeError("Stage15G expected row drift: %s:%s" % (_table,_id))
        conn.execute("UPDATE %s SET status='SUPERSEDED' WHERE %s=? AND status='ACTIVE'" % (_table,_keycol), (_id,))
        if conn.execute("SELECT changes()").fetchone()[0] != 1:
            raise RuntimeError("Stage15G supersede count mismatch: %s:%s" % (_table,_id))

    for _r in _s15g_contract["replacement_decisions"]:
        conn.execute("""INSERT OR REPLACE INTO decisions(decision_id,decision_key,category,title,statement,status,confidence,effective_at,
                        supersedes_decision_id,rationale,evidence_path) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                     (_r["decision_id"],_r["decision_key"],_r["category"],_r["title"],_r["statement"],"ACTIVE",_r["confidence"],
                      _s15g_effective_at,_r.get("supersedes_decision_id"),_r["rationale"],_r["evidence_path"]))
    for _r in _s15g_contract["replacement_interpretations"]:
        conn.execute("""INSERT OR REPLACE INTO interpretations(interpretation_id,interpretation_key,fact_statement,interpretation,
                        do_not_interpret_as,status,confidence,effective_at,supersedes_interpretation_id,evidence_path,evidence_metrics_json)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                     (_r["interpretation_id"],_r["interpretation_key"],_r["fact_statement"],_r["interpretation"],_r["do_not_interpret_as"],
                      "ACTIVE",_r["confidence"],_s15g_effective_at,_r.get("supersedes_interpretation_id"),_r["evidence_path"],
                      json.dumps(_r["evidence_metrics"],sort_keys=True)))
    for _r in _s15g_contract["replacement_contracts"]:
        conn.execute("""INSERT OR REPLACE INTO algorithm_contracts(contract_id,component_key,component_name,implementation_state,
                        contract_statement,active_implementation_id,evidence_path,effective_at,status) VALUES(?,?,?,?,?,?,?,?,?)""",
                     (_r["contract_id"],_r["component_key"],_r["component_name"],_r["implementation_state"],_r["contract_statement"],
                      _r.get("active_implementation_id"),_r["evidence_path"],_s15g_effective_at,"ACTIVE"))
    for _r in _s15g_contract["new_limitations"]:
        conn.execute("""INSERT OR REPLACE INTO limitations(limitation_key,statement,severity,status,mitigation,evidence_path,effective_at)
                        VALUES(?,?,?,?,?,?,?)""",
                     (_r["limitation_key"],_r["statement"],_r["severity"],"ACTIVE",_r["mitigation"],_r["evidence_path"],_s15g_effective_at))
    for _r in _s15g_contract["question_updates"]:
        _existing = conn.execute("SELECT question,priority FROM open_questions WHERE question_key=?",(_r["question_key"],)).fetchone()
        if _existing is None:
            raise RuntimeError("Stage15G question missing: %s" % _r["question_key"])
        conn.execute("""UPDATE open_questions SET status=?,blocking=?,next_action=?,evidence_path=?,effective_at=? WHERE question_key=?""",
                     (_r["status"],int(_r["blocking"]),_r["next_action"],_r["evidence_path"],_s15g_effective_at,_r["question_key"]))
        if conn.execute("SELECT changes()").fetchone()[0] != 1:
            raise RuntimeError("Stage15G question update count mismatch: %s" % _r["question_key"])

    # Exact implementation-ID/path/SHA lifecycle normalization.
    with _s15g_guard(stage15g_lifecycle_plan_path,stage15g_lifecycle_plan_sha256).open("r",encoding="utf-8",newline="") as _handle:
        _lifecycle_rows = list(csv.DictReader(_handle,delimiter="	"))
    if len(_lifecycle_rows) != len(_s15g_contract["lifecycle_plan"]):
        raise RuntimeError("Stage15G lifecycle plan row-count mismatch")
    for _r in _lifecycle_rows:
        _row = conn.execute("SELECT stage_key,script_path,script_sha256,lifecycle_status FROM implementations WHERE implementation_id=?",(_r["implementation_id"],)).fetchone()
        if _row is None:
            raise RuntimeError("Stage15G implementation missing: %s" % _r["implementation_id"])
        _expected = (_r["stage_key"],None if _r["script_path"]=="." else _r["script_path"],None if _r["script_sha256"]=="." else _r["script_sha256"],_r["current_lifecycle_status"])
        if tuple(_row) != _expected:
            raise RuntimeError("Stage15G implementation drift: %s" % _r["implementation_id"])
        conn.execute("UPDATE implementations SET lifecycle_status=?,rationale=? WHERE implementation_id=?",
                     (_r["proposed_lifecycle_status"],_r["rationale"],_r["implementation_id"]))
        if conn.execute("SELECT changes()").fetchone()[0] != 1:
            raise RuntimeError("Stage15G lifecycle update count mismatch: %s" % _r["implementation_id"])

    # Register immutable Stage15G source documents.
    for _path_text,_expected in stage15g_source_guards.items():
        _path = _s15g_guard(_path_text,_expected)
        _mtime = __import__("datetime").datetime.fromtimestamp(_path.stat().st_mtime,__import__("datetime").timezone.utc).replace(microsecond=0).isoformat()
        conn.execute("""INSERT INTO source_documents(source_type,path,sha256,bytes,mtime_utc,content_status,ingested_at)
                        VALUES(?,?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET source_type=excluded.source_type,sha256=excluded.sha256,
                        bytes=excluded.bytes,mtime_utc=excluded.mtime_utc,content_status=excluded.content_status,ingested_at=excluded.ingested_at""",
                     ("stage15g_prerc_architecture_remediation_evidence",str(_path),_expected,_path.stat().st_size,_mtime,"PRESENT",_s15g_effective_at))

    # Hard postconditions inside the atomic SSOT rebuild.
    # Verify only the exact implementation rows owned by this immutable remediation plan.
    # Future SSOT rebuilds may legitimately discover scripts introduced after Stage15G; those
    # future rows must not make this historical insertion fail merely because they are DISCOVERED.
    for _r in _lifecycle_rows:
        _row = conn.execute("SELECT stage_key,script_path,script_sha256,lifecycle_status FROM implementations WHERE implementation_id=?",(_r["implementation_id"],)).fetchone()
        _expected = (_r["stage_key"],None if _r["script_path"]=="." else _r["script_path"],None if _r["script_sha256"]=="." else _r["script_sha256"],_r["proposed_lifecycle_status"])
        if _row is None or tuple(_row) != _expected:
            raise RuntimeError("Stage15G lifecycle postcondition mismatch: %s" % _r["implementation_id"])
        if _r["proposed_lifecycle_status"] not in ['ACTIVE', 'OBSOLETE_FAILED_HISTORICAL', 'PROVISIONAL', 'REFERENCE', 'SUPERSEDED', 'SUPPORT']:
            raise RuntimeError("Stage15G plan contains noncanonical lifecycle: %s" % _r["implementation_id"])
    _stage15g_support = conn.execute("SELECT stage_key,script_path,script_sha256,lifecycle_status FROM implementations WHERE implementation_id='impl_stage15g_prerc_architecture_remediation_v0_1_1'").fetchone()
    if _stage15g_support is None or tuple(_stage15g_support) != ("15G_PRERC_ARCHITECTURE_REMEDIATION",'/mnt/intelssd/rnatr_project/scripts/rnatr_stage15g_remediate_prerc_architecture_v0.1.1.py','321f415bd15b00684c5888c95a67ad32353d103118fb74dee5a9e375a11711bb',"SUPPORT"):
        raise RuntimeError("Stage15G explicit SUPPORT implementation postcondition mismatch")
    for _key in ['CALLER_GENERALIZATION_INCOMPLETE', 'CURRENT_RUNTIME_NOT_PRODUCTION_SCALE', 'RNA_LPS_MISSING', 'STAGE15A_250K_60MIN_MARGIN_TOO_SMALL', 'STAGE15A_250K_SELECTIVE_RESUME_NOT_EXECUTED', 'STAGE15A_FULL_SCALE_RUNTIME_NOT_EMPIRICALLY_VALIDATED', 'STAGE15A_RESTART_SCOPE_IS_SELECTIVE_100K', 'STAGE15A_INTERNAL_RUN_ID_COMPATIBILITY_ALIAS', 'STAGE15C_ACTIVE_PIPELINE_NOT_PROMOTED', 'STAGE15C_FULLSCALE_RESTART_RESUME_OPEN', 'STAGE15C_RELEASE_SCALE_DETERMINISM_OPEN']:
        if conn.execute("SELECT COUNT(*) FROM limitations WHERE limitation_key=? AND status='ACTIVE'",(_key,)).fetchone()[0] != 0:
            raise RuntimeError("Stage15G stale limitation remains ACTIVE: %s" % _key)
    for _key in ['analysis_pause_for_ssot', 'evidence_schema_v0_4_2_validated_candidate_v012', 'final_ranking_gate', 'performance_profiling_phase_started', 'stage14l2_handover_checkpoint_v010', 'stage15a_internal_run_id_compatibility_alias_v0_1_0', 'stage15a_performance_100k_v0_2_2_1_projection_pass', 'stage15c_active_promotion_deferred_v0_1_0', 'stage15e_active_promotion_remains_deferred_v0_1_0']:
        if conn.execute("SELECT COUNT(*) FROM decisions WHERE decision_key=? AND status='ACTIVE'",(_key,)).fetchone()[0] != 0 and _key != "final_ranking_gate":
            raise RuntimeError("Stage15G stale decision remains ACTIVE: %s" % _key)
    for _key in ['native_v041_performance_validated_caller_only', 'performance_stage13a_in_progress_checkpoint', 'stage14l2_performance_boundary_v010', 'stage14l2_validation_boundary_v010', 'stage15a_250k_scaling_margin_interpretation', 'stage15a_performance_projection_scope_v0_2_2_1', 'stage15a_post250k_architecture_audit_interpretation', 'stage15a_reference_correctness_scope', 'stage15a_restart_resume_100k_scope']:
        _expected_count = 1 if _key in ("native_v041_performance_validated_caller_only","stage15a_reference_correctness_scope") else 0
        if conn.execute("SELECT COUNT(*) FROM interpretations WHERE interpretation_key=? AND status='ACTIVE'",(_key,)).fetchone()[0] != _expected_count:
            raise RuntimeError("Stage15G stale interpretation active-count mismatch: %s" % _key)
    for _key in ['architecture_consistency_audit_v0_1_0', 'evidence_schema_v042']:
        if conn.execute("SELECT COUNT(*) FROM algorithm_contracts WHERE component_key=? AND status='ACTIVE'",(_key,)).fetchone()[0] != 1:
            raise RuntimeError("Stage15G replacement contract count mismatch: %s" % _key)
    if conn.execute("SELECT status FROM open_questions WHERE question_key='PRE_RELEASE_CANDIDATE_ARCHITECTURE_AUDIT'").fetchone()[0] != "CLOSED":
        raise RuntimeError("Stage15G PRE-RC question not closed")


    # Stage 15N generic active path promotion v0.1.0
    _s15n_effective_at = '2026-08-11T15:30:00+00:00'
    _s15n_installed = {'scripts/rnatr_core_production_entry_v0.1.0.py': 'c6cf8298fb2dfb52b6bfbd7eda8d701356823644668d6d952abac09cc06358c4', 'scripts/rnatr_core_generic_sharded_v0.1.2.py': '76ccd6a41f95bd0d2bbf1bf0fba1b26e4232e8f526fae6ec86d3b3f06197784b', 'scripts/rnatr_core_generic_unit_v0.1.1.py': 'cff4bfc874cb07db6a98dfb679866a4f75a0eaa10c7c16c3bf3698fd5abf79f5', 'scripts/rnatr_prebiology_manifest_smoke_v0.1.0.py': 'eeb6442cdf9bebfec631ef718ad6298e27ec0d753a9f9ea999a24d4998d181dc', 'config/core_runtime/v0.1.0/resource_manifest.json': '4418837acb0aa744fef0810d6db0260b6c534789a5e7e92ef123f9f79e848a2e', 'scripts/rnatr_stage15n_promote_generic_active_path_v0.1.0.py': '64aac7a5430eee51cfe39628abf6d093758912f5340dbc9c0ecad522f19535c6', 'validation/release_gates_v0.3.3.tsv': '6df48d735b7e44c7854d5c4e081161d7a61bc3fcf0c8db2698718cf4242ee65f'}
    for _s15n_rel_text,_s15n_expected_sha in _s15n_installed.items():
        _s15n_path=(project_root/Path(_s15n_rel_text)).resolve()
        if not _s15n_path.is_file() or sha256_file(_s15n_path)!=_s15n_expected_sha:
            raise RuntimeError(f"Stage15N installed-source guard failed: {_s15n_path}")
        source_document(conn,_s15n_path,"stage15n_generic_active_path_promotion",force_hash=True)

    _s15n_expected_impl_rows = {'impl_e7e046cdd146161435cc918c': {'implementation_id': 'impl_e7e046cdd146161435cc918c', 'stage_key': '11b_TARGET_ASSIGNMENT', 'version': 'rnatr_target_assignment_v0.3.1', 'script_path': '/mnt/intelssd/rnatr_project/scripts/11b_extract_alignment_segments_and_target_candidates.sh', 'script_sha256': 'e00bdaad48080d7cfed01e1b961e0617af0f2239e014cd6fe8924460aa9afd56', 'validator_path': '/mnt/intelssd/rnatr_project/config/evidence_schema/v0.3/patches/validator_v0.3.1/rnatr_v03_validate_tsv_validator_v0.3.1.py', 'validator_sha256': '10c9d4bbb5c9dac314d400768eb27206173933759c877225bd0ca2c692d8aba9', 'package_version': 'rnatr-scout 0.3.2', 'parameters_json': '{"deletion_D": "included", "secondary": "retain", "splice_N": "excluded_from_blocks", "supplementary": "retain", "target_padding_bp": 500}', 'lifecycle_status': 'ACTIVE', 'supersedes_implementation_id': None, 'rationale': 'Current frozen target-assignment producer for the 100k pilot.', 'evidence_path': '/mnt/intelssd/rnatr_project/metadata/build_tracker/checkpoints/20260803_182703_step11_rna_repeat_pilot/step11_checkpoint.md', 'effective_at': '2026-08-06T00:00:00+00:00'}, 'impl_af6072bfd6029316076d69f0': {'implementation_id': 'impl_af6072bfd6029316076d69f0', 'stage_key': '11d3_RAW_READ_PROJECTION', 'version': 'v0.3.3', 'script_path': '/mnt/intelssd/rnatr_project/scripts/11d3_project_targets_to_raw_reads_secondary_seq_fixed.sh', 'script_sha256': '9df2998915e49da27ecf80f24a733d55a498c2ba32b278df881fdefa901a83e2', 'validator_path': None, 'validator_sha256': None, 'package_version': 'rnatr-scout 0.3.2', 'parameters_json': '{"projection_version": "v0.3.3"}', 'lifecycle_status': 'ACTIVE', 'supersedes_implementation_id': None, 'rationale': 'Adopted projection implementation; supersedes 11d and 11d2.', 'evidence_path': '/mnt/intelssd/rnatr_project/metadata/build_tracker/checkpoints/20260803_182703_step11_rna_repeat_pilot/step11_checkpoint.md', 'effective_at': '2026-08-06T00:00:00+00:00'}, 'impl_c8e1b04b961f0c51335fc530': {'implementation_id': 'impl_c8e1b04b961f0c51335fc530', 'stage_key': '11e_MOTIF_JOBS', 'version': 'current', 'script_path': '/mnt/intelssd/rnatr_project/scripts/11e_prepare_motif_scan_jobs.sh', 'script_sha256': '2cc13e2b95711e0d21c05eba1bec3ec26e249d3ec3e80f6ebce4c8157245038a', 'validator_path': None, 'validator_sha256': None, 'package_version': 'rnatr-scout 0.3.2', 'parameters_json': '{}', 'lifecycle_status': 'ACTIVE', 'supersedes_implementation_id': None, 'rationale': 'Frozen motif-job preparation used for the target pilot.', 'evidence_path': '/mnt/intelssd/rnatr_project/metadata/build_tracker/checkpoints/20260803_182703_step11_rna_repeat_pilot/step11_checkpoint.md', 'effective_at': '2026-08-06T00:00:00+00:00'}, 'impl_92f0f4fe33897d713ac97b6f': {'implementation_id': 'impl_92f0f4fe33897d713ac97b6f', 'stage_key': '11f_PERIODIC_BASELINE', 'version': 'current', 'script_path': '/mnt/intelssd/rnatr_project/scripts/11f_run_high_confidence_simple_periodic_baseline.parallel_v0.1.0.sh', 'script_sha256': '08d70a104ec384914a9e7e72cc18b67481b94805940fb67900d19c8fde397684', 'validator_path': None, 'validator_sha256': None, 'package_version': 'rnatr-scout 0.3.2', 'parameters_json': '{}', 'lifecycle_status': 'ACTIVE', 'supersedes_implementation_id': None, 'rationale': 'Initial P0/P1 simple-periodic measurement stage.', 'evidence_path': '/mnt/intelssd/rnatr_project/metadata/build_tracker/checkpoints/20260803_182703_step11_rna_repeat_pilot/step11_checkpoint.md', 'effective_at': '2026-08-06T00:00:00+00:00'}, 'impl_dc6362d60631a353eb3c7c86': {'implementation_id': 'impl_dc6362d60631a353eb3c7c86', 'stage_key': '11g_BASELINE_AUDIT', 'version': 'current', 'script_path': '/mnt/intelssd/rnatr_project/scripts/11g_audit_periodic_baseline_target_concordance.sh', 'script_sha256': 'fd75fbe3641b53da589008898f5700a3a4f729fdefaeda4a1041d7dc6fb11d1e', 'validator_path': None, 'validator_sha256': None, 'package_version': 'rnatr-scout 0.3.2', 'parameters_json': '{}', 'lifecycle_status': 'ACTIVE', 'supersedes_implementation_id': None, 'rationale': 'Required audit before refinement.', 'evidence_path': '/mnt/intelssd/rnatr_project/metadata/build_tracker/checkpoints/20260803_182703_step11_rna_repeat_pilot/step11_checkpoint.md', 'effective_at': '2026-08-06T00:00:00+00:00'}, 'impl_d6c366aaa77a3ed65a8087cb': {'implementation_id': 'impl_d6c366aaa77a3ed65a8087cb', 'stage_key': '11h_PERIODIC_REFINEMENT', 'version': 'current', 'script_path': '/mnt/intelssd/rnatr_project/scripts/11h_target_constrained_periodic_refinement.parallel_v0.1.0.sh', 'script_sha256': 'bad281accad9937429f450e538c657ae04e1090eba05157a0c911b375b82c7e0', 'validator_path': None, 'validator_sha256': None, 'package_version': 'rnatr-scout 0.3.2', 'parameters_json': '{}', 'lifecycle_status': 'ACTIVE', 'supersedes_implementation_id': None, 'rationale': 'Frozen refinement stage.', 'evidence_path': '/mnt/intelssd/rnatr_project/metadata/build_tracker/checkpoints/20260803_182703_step11_rna_repeat_pilot/step11_checkpoint.md', 'effective_at': '2026-08-06T00:00:00+00:00'}, 'impl_e6358231c8574b2fe5d863cc': {'implementation_id': 'impl_e6358231c8574b2fe5d863cc', 'stage_key': '11i_INTERNAL_RECLASSIFICATION', 'version': 'schema v0.3.1', 'script_path': '/mnt/intelssd/rnatr_project/scripts/11i_reclassify_internal_one_flank_and_audit_span.sh', 'script_sha256': 'efe060f78240db5ffc5c59319bacb44dcd0bc61ee3d2ee613d904b07f4e42112', 'validator_path': None, 'validator_sha256': None, 'package_version': 'rnatr-scout 0.3.2', 'parameters_json': '{}', 'lifecycle_status': 'ACTIVE', 'supersedes_implementation_id': None, 'rationale': 'Adds LEFT_ONLY_INTERNAL/RIGHT_ONLY_INTERNAL and partial_internal handling.', 'evidence_path': '/mnt/intelssd/rnatr_project/metadata/build_tracker/checkpoints/20260803_182703_step11_rna_repeat_pilot/step11_checkpoint.md', 'effective_at': '2026-08-06T00:00:00+00:00'}, 'impl_8d45b3c305f18ac517f8886a': {'implementation_id': 'impl_8d45b3c305f18ac517f8886a', 'stage_key': '11j_EXACT_SPAN_CALIBRATION', 'version': 'current', 'script_path': '/mnt/intelssd/rnatr_project/scripts/11j_audit_exact_span_global_periodicity.sh', 'script_sha256': '3e78d17c0589b480b8661020972eef67bb4a2a5bfc3bd45aeca4575e638ea538', 'validator_path': None, 'validator_sha256': None, 'package_version': 'rnatr-scout 0.3.2', 'parameters_json': '{}', 'lifecycle_status': 'ACTIVE', 'supersedes_implementation_id': None, 'rationale': 'Frozen exact-span global calibration stage.', 'evidence_path': '/mnt/intelssd/rnatr_project/metadata/build_tracker/checkpoints/20260803_182703_step11_rna_repeat_pilot/step11_checkpoint.md', 'effective_at': '2026-08-06T00:00:00+00:00'}, 'impl_485fcc3aa81a169bcee6b348': {'implementation_id': 'impl_485fcc3aa81a169bcee6b348', 'stage_key': '11k3_SPAN_NORMALIZATION', 'version': 'v0.3.3', 'script_path': '/mnt/intelssd/rnatr_project/scripts/11k3_normalize_calibrated_span_fields_fixed.sh', 'script_sha256': '7a86f68cb88ee3906e445aa1598ee48d4240dcb39cd4870cd1abab157b9b41f4', 'validator_path': None, 'validator_sha256': None, 'package_version': 'rnatr-scout 0.3.2', 'parameters_json': '{"span_field_normalization": "v0.3.3"}', 'lifecycle_status': 'ACTIVE', 'supersedes_implementation_id': None, 'rationale': 'Adopted normalized evidence output; supersedes 11k2.', 'evidence_path': '/mnt/intelssd/rnatr_project/metadata/build_tracker/checkpoints/20260803_182703_step11_rna_repeat_pilot/step11_checkpoint.md', 'effective_at': '2026-08-06T00:00:00+00:00'}, 'impl_d8a9c3243eef120461ac2de3': {'implementation_id': 'impl_d8a9c3243eef120461ac2de3', 'stage_key': '11k_CALIBRATED_EVIDENCE', 'version': 'current', 'script_path': '/mnt/intelssd/rnatr_project/scripts/11k_finalize_calibrated_simple_periodic_evidence.sh', 'script_sha256': '54f793c5d207acc429f3329200c8ec4025aee01cd890e55fb507dc2073f0ba30', 'validator_path': None, 'validator_sha256': None, 'package_version': 'rnatr-scout 0.3.2', 'parameters_json': '{}', 'lifecycle_status': 'ACTIVE', 'supersedes_implementation_id': None, 'rationale': 'Produces the calibrated 49,793-row P0/P1 evidence table.', 'evidence_path': '/mnt/intelssd/rnatr_project/metadata/build_tracker/checkpoints/20260803_182703_step11_rna_repeat_pilot/step11_checkpoint.md', 'effective_at': '2026-08-06T00:00:00+00:00'}, 'impl_8e35dcc35a40649c98d0334e': {'implementation_id': 'impl_8e35dcc35a40649c98d0334e', 'stage_key': 'MAP_SPLICE', 'version': 'rnatr_mm2_splice_cDNA_v0.3.1', 'script_path': '/mnt/intelssd/rnatr_project/results/11_mapping/ENCSR307SHM_pilot100k_mm2splice_v1/ENCSR307SHM_pilot100k_mm2splice_v1.mapper_command.sh', 'script_sha256': 'de9ad6e4cfaea3c83158619ac39c3b73e88704cf880da51c1306378fbd956bb7', 'validator_path': None, 'validator_sha256': None, 'package_version': 'minimap2 2.31-r1302', 'parameters_json': '{"MD": true, "N": 10, "cs": "long", "junction_bed": "GENCODE v50", "preset": "splice", "secondary": true, "threads": 16}', 'lifecycle_status': 'ACTIVE', 'supersedes_implementation_id': None, 'rationale': 'Frozen mapping configuration used by the target pilot and six equalized comparison datasets.', 'evidence_path': '/mnt/intelssd/rnatr_project/qc/11_equalized_100k_mapping/ENCSR307SHM_pilot100k_mm2splice_v1/rnatr_equalized_100k_mm2splice_mapping_v0.1.1/equalized_100k_mapping.qc.tsv', 'effective_at': '2026-08-06T00:00:00+00:00'}, 'impl_stage15a_reference_v0_1_3': {'implementation_id': 'impl_stage15a_reference_v0_1_3', 'stage_key': '15A_BAM_TO_FINAL_REFERENCE', 'version': 'rnatr_stage15a_reference_100k_v0.1.3', 'script_path': '/mnt/intelssd/rnatr_project/scripts/rnatr_stage15a_resume_reference_100k_v0.1.3.py', 'script_sha256': 'cdd2a9746467d2262bab86515bbb676aae8358daa147439d0249d10dfe14236b', 'validator_path': '/mnt/intelssd/rnatr_project/config/evidence_schema/v0.4.2/rnatr_v042_validate_package.py', 'validator_sha256': '45c3995550f57a65b3fec4aab7471d57b7000e19471d4c5cf7f3ae055426984e', 'package_version': 'evidence_schema_v0.4.2', 'parameters_json': '{"active_pipeline_switch": false, "full_5_31m_run": false, "graph": "11b>11d3>11e>11f>11h>native_v041>materializer_v012>schema_v042", "input_contract": "sorted_mapping_complete_BAM+BAI+mapping_manifest+associated_raw_read_sequence_store", "materializer": "v0.1.2", "native_caller": "v0.4.1", "reference_lane": true, "run_id": "ENCSR307SHM_pilot100k_mm2splice_v1", "schema": "v0.4.2"}', 'lifecycle_status': 'PROVISIONAL', 'supersedes_implementation_id': None, 'rationale': 'Accepted as the isolated 100k correctness and regression reference only. It must not enter current_pipeline until the Stage 15A performance/restart gate passes and a separate activation decision is made.', 'evidence_path': '/mnt/intelssd/rnatr_project/qc/15_stage15a_bam_to_final/ENCSR307SHM_pilot100k_mm2splice_v1/v0.1.3/stage15a_reference_100k.qc.tsv', 'effective_at': '2026-08-08T06:12:17+00:00'}, 'impl_stage15a_performance_v0_2_2_1': {'implementation_id': 'impl_stage15a_performance_v0_2_2_1', 'stage_key': '15A_BAM_TO_FINAL_PERFORMANCE', 'version': 'rnatr_stage15a_sharded_bam_to_final_performance_v0.2.2.1', 'script_path': '/mnt/intelssd/rnatr_project/scripts/rnatr_stage15a_run_performance_100k_v0.2.2.1.py', 'script_sha256': '7bfb7018cea80cd92854882751cffb49bea817296f69866801a64f9529c5e1a8', 'validator_path': '/mnt/intelssd/rnatr_project/scripts/rnatr_stage15a_validate_package_parallel_v0.2.2.1.py', 'validator_sha256': 'b635ed213b65cee005914f0fded9337871903a7e5682f9a897dff9cbc9bb0b09', 'package_version': 'evidence_schema_v0.4.2', 'parameters_json': '{"active_pipeline_switch": false, "caller_workers_total": 24, "full_5_31m_run": false, "input_contract": "sorted_mapping_complete_BAM+associated_raw_read_sequence_store", "materializer_semantics": "v0.1.2", "native_caller": "v0.4.1", "read_coherent_sharding": true, "run_id": "ENCSR307SHM_pilot100k_mm2splice_v1", "schema": "v0.4.2", "shard_count": 12}', 'lifecycle_status': 'PROVISIONAL', 'supersedes_implementation_id': 'impl_stage15a_performance_v0_2_1', 'rationale': 'Accepted as the current isolated performance candidate because exact logical parity, validators, failure-parity testing, atomic publication, and a conservative 58.230-minute 5.31M projection passed. It is not ACTIVE.', 'evidence_path': '/mnt/intelssd/rnatr_project/qc/15_stage15a_bam_to_final/ENCSR307SHM_pilot100k_mm2splice_v1/v0.2.2.1_performance/stage15a_performance_100k.qc.tsv', 'effective_at': '2026-08-08T11:31:27+00:00'}, 'impl_stage15a_scaling_500k_v0_1_4': {'implementation_id': 'impl_stage15a_scaling_500k_v0_1_4', 'stage_key': '15A_DETERMINISTIC_500K_SCALING', 'version': 'v0.1.4_compare_amendment', 'script_path': None, 'script_sha256': None, 'validator_path': None, 'validator_sha256': None, 'package_version': 'v0.4.2', 'parameters_json': None, 'lifecycle_status': 'PROVISIONAL', 'supersedes_implementation_id': None, 'rationale': 'Accepted deterministic 500k scaling evidence; not an active pipeline implementation.', 'evidence_path': '/mnt/intelssd/rnatr_project/qc/15_stage15a_bam_to_final/ENCSR307SHM_stage15a500k_seed20260809_mm2splice_v1/v0.1.1_500k_scaling/stage15a_scaling_500k.qc.tsv', 'effective_at': '2026-08-10T00:00:00+00:00'}, 'impl_stage15a_scaling_250k_v0_1_2': {'implementation_id': 'impl_stage15a_scaling_250k_v0_1_2', 'stage_key': '15A_DETERMINISTIC_SCALING', 'version': 'rnatr_stage15a_deterministic_250k_scaling_v0.1.2', 'script_path': '/mnt/intelssd/rnatr_project/scripts/rnatr_stage15a_run_scaling_250k_v0.1.2.py', 'script_sha256': 'dbc78c93087bf5bc74d6fea2c47b1c3d6c2986b62de9e7a7e73c21993facb375', 'validator_path': None, 'validator_sha256': None, 'package_version': 'evidence_schema_v0.4.2', 'parameters_json': '{"active_pipeline_switch": false, "full_5_31m_run": false}', 'lifecycle_status': 'PROVISIONAL', 'supersedes_implementation_id': 'impl_stage15a_scaling_250k_v0_1_1', 'rationale': 'Current deterministic 250k scaling implementation with exact final-package and caller reproducibility.', 'evidence_path': '/mnt/intelssd/rnatr_project/qc/15_stage15a_bam_to_final/ENCSR307SHM_stage15a250k_seed20260808_mm2splice_v1/v0.1.2_250k_scaling/stage15a_scaling_250k.qc.tsv', 'effective_at': '2026-08-09T00:00:00+00:00'}, 'impl_stage15a_restart_resume_100k_v0_1_0': {'implementation_id': 'impl_stage15a_restart_resume_100k_v0_1_0', 'stage_key': '15A_RESTART_RESUME_VALIDATION', 'version': 'rnatr_stage15a_restart_resume_100k_v0.1.0', 'script_path': '/mnt/intelssd/rnatr_project/scripts/rnatr_stage15a_restart_resume_100k_v0.1.0.py', 'script_sha256': '4f9159e47a1fb9df1c3496181b24181102fb760463d0fd38c3236216bd448b44', 'validator_path': None, 'validator_sha256': None, 'package_version': 'evidence_schema_v0.4.2', 'parameters_json': '{"adopted_upstream_shards": 12, "checkpoint_rows": 138, "full_5_31m_run": false, "intentional_exit_code": 75, "resumed_materializer_shards": 1, "scope": "fresh_caller_checkpoint_to_final_selective_materializer_resume", "second_resume_noop_required": true, "source_performance_version": "v0.2.2.1_performance"}', 'lifecycle_status': 'PROVISIONAL', 'supersedes_implementation_id': None, 'rationale': 'Validated selective 100k restart/resume with exact raw and logical package parity, negative checkpoint rejection, no partial publication, atomic publication, and an unchanged no-op second resume. Full-scale and arbitrary upstream-stage restart remain open.', 'evidence_path': '/mnt/intelssd/rnatr_project/qc/15_stage15a_bam_to_final/ENCSR307SHM_pilot100k_mm2splice_v1/v0.2.3_restart_resume_100k/stage15a_restart_resume_100k.qc.tsv', 'effective_at': '2026-08-08T13:40:00+00:00'}, 'impl_stage15c_full_runner_v0_1_6': {'implementation_id': 'impl_stage15c_full_runner_v0_1_6', 'stage_key': '15C_FULL_EMPIRICAL_BAM_TO_FINAL', 'version': 'v0.1.6', 'script_path': '/mnt/intelssd/rnatr_project/scripts/rnatr_stage15c_run_full5312696_bam_to_final_v0.1.6.py', 'script_sha256': 'cca6b2d4c6e773392d3a8c24cd2fd2a1f0a41a713338b4ccdec1ba7fab5bafcc', 'validator_path': None, 'validator_sha256': None, 'package_version': 'v0.4.2', 'parameters_json': None, 'lifecycle_status': 'PROVISIONAL', 'supersedes_implementation_id': None, 'rationale': 'Validated full-scale candidate; explicit active-path promotion remains prohibited.', 'evidence_path': '/mnt/intelssd/rnatr_project/qc/15_stage15c_fullscale_bam_to_final/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.6/stage15c_full_empirical_run.qc.tsv', 'effective_at': '2026-08-10T00:00:00+00:00'}, 'impl_stage15a_fast11e_scaling_v0_2_2_2': {'implementation_id': 'impl_stage15a_fast11e_scaling_v0_2_2_2', 'stage_key': '15A_DETERMINISTIC_SCALING', 'version': 'rnatr_stage15a_fast_motif_jobs_scaling_v0.2.2.2', 'script_path': '/mnt/intelssd/rnatr_project/scripts/rnatr_stage15a_fast_motif_jobs_scaling_v0.2.2.2.py', 'script_sha256': '3e36454a515cd8c0411957000099867b582ae7d2bef78b7fe2ebd61bf09f4dc4', 'validator_path': None, 'validator_sha256': None, 'package_version': 'evidence_schema_v0.4.2', 'parameters_json': '{"active_pipeline_switch": false, "full_5_31m_run": false}', 'lifecycle_status': 'PROVISIONAL', 'supersedes_implementation_id': None, 'rationale': 'Scaling-aware shared-catalog 11e component with dynamic expected rows/reads.', 'evidence_path': '/mnt/intelssd/rnatr_project/qc/15_stage15a_bam_to_final/ENCSR307SHM_stage15a250k_seed20260808_mm2splice_v1/v0.1.2_250k_scaling/stage15a_scaling_250k.qc.tsv', 'effective_at': '2026-08-09T00:00:00+00:00'}, 'impl_stage15a_candidate_fastq_v0_1_0': {'implementation_id': 'impl_stage15a_candidate_fastq_v0_1_0', 'stage_key': '15A_DETERMINISTIC_SCALING', 'version': 'rnatr_stage15a_extract_candidate_fastq_v0.1.0', 'script_path': '/mnt/intelssd/rnatr_project/scripts/rnatr_stage15a_extract_candidate_fastq_v0.1.0.py', 'script_sha256': 'b4ecf4e5ecf1a1c0e57e96cb30f560a21230e1463777bdbb0e36601918a9abbf', 'validator_path': None, 'validator_sha256': None, 'package_version': 'evidence_schema_v0.4.2', 'parameters_json': '{"active_pipeline_switch": false, "full_5_31m_run": false}', 'lifecycle_status': 'PROVISIONAL', 'supersedes_implementation_id': None, 'rationale': 'Current candidate-FASTQ extraction support component used by deterministic scaling.', 'evidence_path': '/mnt/intelssd/rnatr_project/qc/15_stage15a_bam_to_final/ENCSR307SHM_stage15a250k_seed20260808_mm2splice_v1/v0.1.2_250k_scaling/stage15a_scaling_250k.qc.tsv', 'effective_at': '2026-08-09T00:00:00+00:00'}, 'impl_stage15b_memory_bounded_validator_v0_1_0': {'implementation_id': 'impl_stage15b_memory_bounded_validator_v0_1_0', 'stage_key': '15B_MEMORY_BOUNDED_VALIDATOR', 'version': 'v0.1.0', 'script_path': '/mnt/intelssd/rnatr_project/scripts/rnatr_stage15b_validate_package_sharded_memory_bounded_v0.1.0.py', 'script_sha256': '1136086f0214bcd11a2a2d71f2e459f433c7fc9f51d170aa3b97826e8808ee99', 'validator_path': None, 'validator_sha256': None, 'package_version': 'v0.4.2', 'parameters_json': None, 'lifecycle_status': 'PROVISIONAL', 'supersedes_implementation_id': None, 'rationale': 'Frozen-semantics equivalent memory-bounded package validator; active promotion deferred.', 'evidence_path': '/mnt/intelssd/rnatr_project/qc/15_stage15b_memory_bounded_validator/ENCSR307SHM_stage15a500k_seed20260809_mm2splice_v1/v0.1.0/stage15b_memory_bounded_validator.qc.tsv', 'effective_at': '2026-08-10T00:00:00+00:00'}, 'impl_1d28c1ed1d62458b4f8d6e9b': {'implementation_id': 'impl_1d28c1ed1d62458b4f8d6e9b', 'stage_key': 'UNCLASSIFIED', 'version': None, 'script_path': '/mnt/intelssd/rnatr_project/config/evidence_schema/v0.3/patches/validator_v0.3.1/rnatr_v03_validate_tsv_validator_v0.3.1.py', 'script_sha256': '10c9d4bbb5c9dac314d400768eb27206173933759c877225bd0ca2c692d8aba9', 'validator_path': None, 'validator_sha256': None, 'package_version': None, 'parameters_json': None, 'lifecycle_status': 'REFERENCE', 'supersedes_implementation_id': None, 'rationale': 'Exact file is present but file existence does not imply ACTIVE; conservatively classify as REFERENCE.', 'evidence_path': '/mnt/intelssd/rnatr_project/config/evidence_schema/v0.3/patches/validator_v0.3.1/rnatr_v03_validate_tsv_validator_v0.3.1.py', 'effective_at': '2026-08-03T05:56:50+00:00'}, 'impl_ebf658aeb944b57193a8feae': {'implementation_id': 'impl_ebf658aeb944b57193a8feae', 'stage_key': 'SCRIPT_rnatr_stage15a_native_v041_runid_adapter_v0.2.1', 'version': None, 'script_path': '/mnt/intelssd/rnatr_project/scripts/rnatr_stage15a_native_v041_runid_adapter_v0.2.1.py', 'script_sha256': '18d40dba5733efbfa633fff1d52372db49c63bcf315acb7f86acbdc64c89e386', 'validator_path': None, 'validator_sha256': None, 'package_version': None, 'parameters_json': None, 'lifecycle_status': 'REFERENCE', 'supersedes_implementation_id': None, 'rationale': 'Exact file is present but file existence does not imply ACTIVE; conservatively classify as REFERENCE.', 'evidence_path': '/mnt/intelssd/rnatr_project/scripts/rnatr_stage15a_native_v041_runid_adapter_v0.2.1.py', 'effective_at': '2026-08-09T00:56:04+00:00'}, 'impl_6fee299d6f4f1740d021d601': {'implementation_id': 'impl_6fee299d6f4f1740d021d601', 'stage_key': 'SCRIPT_rnatr_materialize_native_v041_to_evidence_v042_runid_adapter_v0.2.1', 'version': None, 'script_path': '/mnt/intelssd/rnatr_project/scripts/rnatr_materialize_native_v041_to_evidence_v042_runid_adapter_v0.2.1.py', 'script_sha256': '7ba7f5082c9671be55b6b223c20f5bc8b933ad8b4658b1789187e043943949d4', 'validator_path': None, 'validator_sha256': None, 'package_version': None, 'parameters_json': None, 'lifecycle_status': 'REFERENCE', 'supersedes_implementation_id': None, 'rationale': 'Exact file is present but file existence does not imply ACTIVE; conservatively classify as REFERENCE.', 'evidence_path': '/mnt/intelssd/rnatr_project/scripts/rnatr_materialize_native_v041_to_evidence_v042_runid_adapter_v0.2.1.py', 'effective_at': '2026-08-09T00:56:04+00:00'}, 'impl_2e51d966539df8cbf9a52508': {'implementation_id': 'impl_2e51d966539df8cbf9a52508', 'stage_key': 'UNCLASSIFIED', 'version': None, 'script_path': '/mnt/intelssd/rnatr_project/config/evidence_schema/v0.4.2/rnatr_v042_validate_package.py', 'script_sha256': '45c3995550f57a65b3fec4aab7471d57b7000e19471d4c5cf7f3ae055426984e', 'validator_path': None, 'validator_sha256': None, 'package_version': None, 'parameters_json': None, 'lifecycle_status': 'REFERENCE', 'supersedes_implementation_id': None, 'rationale': 'Exact file is present but file existence does not imply ACTIVE; conservatively classify as REFERENCE.', 'evidence_path': '/mnt/intelssd/rnatr_project/config/evidence_schema/v0.4.2/rnatr_v042_validate_package.py', 'effective_at': '2026-08-07T15:45:20+00:00'}, 'impl_026821e074645628484419a9': {'implementation_id': 'impl_026821e074645628484419a9', 'stage_key': 'UNCLASSIFIED', 'version': None, 'script_path': '/mnt/intelssd/rnatr_project/config/evidence_schema/v0.4.2/rnatr_v042_validate_tsv.py', 'script_sha256': '10c9d4bbb5c9dac314d400768eb27206173933759c877225bd0ca2c692d8aba9', 'validator_path': None, 'validator_sha256': None, 'package_version': None, 'parameters_json': None, 'lifecycle_status': 'REFERENCE', 'supersedes_implementation_id': None, 'rationale': 'Exact file is present but file existence does not imply ACTIVE; conservatively classify as REFERENCE.', 'evidence_path': '/mnt/intelssd/rnatr_project/config/evidence_schema/v0.4.2/rnatr_v042_validate_tsv.py', 'effective_at': '2026-08-03T05:56:50+00:00'}}
    _s15n_transitions = {'impl_e7e046cdd146161435cc918c': 'SUPPORT', 'impl_af6072bfd6029316076d69f0': 'SUPPORT', 'impl_c8e1b04b961f0c51335fc530': 'SUPERSEDED', 'impl_92f0f4fe33897d713ac97b6f': 'SUPERSEDED', 'impl_dc6362d60631a353eb3c7c86': 'SUPERSEDED', 'impl_d6c366aaa77a3ed65a8087cb': 'SUPERSEDED', 'impl_e6358231c8574b2fe5d863cc': 'SUPERSEDED', 'impl_8d45b3c305f18ac517f8886a': 'SUPERSEDED', 'impl_485fcc3aa81a169bcee6b348': 'SUPERSEDED', 'impl_d8a9c3243eef120461ac2de3': 'SUPERSEDED', 'impl_8e35dcc35a40649c98d0334e': 'REFERENCE', 'impl_stage15a_reference_v0_1_3': 'REFERENCE', 'impl_stage15a_performance_v0_2_2_1': 'REFERENCE', 'impl_stage15a_scaling_500k_v0_1_4': 'REFERENCE', 'impl_stage15a_scaling_250k_v0_1_2': 'REFERENCE', 'impl_stage15a_restart_resume_100k_v0_1_0': 'REFERENCE', 'impl_stage15c_full_runner_v0_1_6': 'REFERENCE', 'impl_stage15a_fast11e_scaling_v0_2_2_2': 'SUPPORT', 'impl_stage15a_candidate_fastq_v0_1_0': 'SUPPORT', 'impl_stage15b_memory_bounded_validator_v0_1_0': 'SUPPORT', 'impl_1d28c1ed1d62458b4f8d6e9b': 'SUPPORT', 'impl_ebf658aeb944b57193a8feae': 'SUPPORT', 'impl_6fee299d6f4f1740d021d601': 'SUPPORT', 'impl_2e51d966539df8cbf9a52508': 'SUPPORT', 'impl_026821e074645628484419a9': 'SUPPORT'}
    for _s15n_iid,_s15n_expected in _s15n_expected_impl_rows.items():
        _s15n_row=conn.execute("SELECT * FROM implementations WHERE implementation_id=?",(_s15n_iid,)).fetchone()
        if _s15n_row is None or dict(_s15n_row)!=_s15n_expected:
            raise RuntimeError(f"Stage15N implementation baseline mismatch: {_s15n_iid}")
        conn.execute("UPDATE implementations SET lifecycle_status=?, rationale=? WHERE implementation_id=?",(_s15n_transitions[_s15n_iid],"Lifecycle updated by Stage15N generic active-path promotion; exact prior row remains identifiable by implementation_id.",_s15n_iid))

    _s15n_stage_defs = [('CORE_GENERIC_SHARDED_BAM_FASTQ_TO_FINAL', 20.0, 'Generic sharded BAM+FASTQ to final Core', 'From mapped BAM and read-coherent source FASTQ to a validated schema v0.4.2 package and portable Core result manifest.', 'production_orchestration', 'ACTIVE', 'Composite public Core entry; mapping remains separate.'), ('CORE_GENERIC_SHARDED_ORCHESTRATOR', 20.1, 'Generic sharded Core orchestrator', 'Read-coherent partition, bounded unit execution, deterministic merge, validation, publication and restart recovery.', 'production_support', 'IMPLEMENTED_SUPPORT_ONLY', 'Internal support implementation behind the active public entry.'), ('CORE_GENERIC_UNIT_BAM_FASTQ_TO_FINAL', 20.2, 'Generic read-coherent Core unit', 'Execute the frozen scientific components for one BAM/FASTQ read-coherent unit.', 'production_support', 'IMPLEMENTED_SUPPORT_ONLY', 'Validated by Stage15J and composed by the sharded orchestrator.'), ('CORE_RUNTIME_RESOURCE_MANIFEST', 20.3, 'Core runtime resource manifest', 'Resolve project-relative checksum-pinned components/catalogs into run-local bindings.', 'production_support', 'IMPLEMENTED_SUPPORT_ONLY', 'Public path contract is project-relative; run-local config may contain local paths.'), ('PREBIOLOGY_RESULT_MANIFEST_SMOKE', 20.4, 'PRE_BIOLOGY result-manifest interface smoke', 'Read-only resolution from portable Core result manifest through stable read/locus identities to BAM and pinned annotation.', 'architecture_validation', 'IMPLEMENTED_SUPPORT_ONLY', 'Not full biology implementation.'), ('15N_GENERIC_ACTIVE_PATH_PROMOTION', 155.0, 'Stage15N generic active-path promotion', 'Atomically install and register the generic active Core path with rollback and postconditions.', 'architecture_governance', 'IMPLEMENTED_SUPPORT_ONLY', 'Metadata/governance updater.')]
    for _s15n_def in _s15n_stage_defs:
        conn.execute("INSERT OR REPLACE INTO stage_definitions(stage_key,stage_order,name,purpose,category,implementation_status,notes) VALUES(?,?,?,?,?,?,?)",_s15n_def)

    _s15n_impls = [{'implementation_id': 'impl_core_generic_production_entry_v0_1_0', 'stage_key': 'CORE_GENERIC_SHARDED_BAM_FASTQ_TO_FINAL', 'version': 'v0.1.0', 'script_path': '/mnt/intelssd/rnatr_project/scripts/rnatr_core_production_entry_v0.1.0.py', 'script_sha256': 'c6cf8298fb2dfb52b6bfbd7eda8d701356823644668d6d952abac09cc06358c4', 'validator_path': '/mnt/intelssd/rnatr_project/config/evidence_schema/v0.4.2/rnatr_v042_validate_package.py', 'validator_sha256': '45c3995550f57a65b3fec4aab7471d57b7000e19471d4c5cf7f3ae055426984e', 'package_version': 'evidence_schema_v0.4.2', 'parameters_json': '{"caller_workers": "explicit_required", "input_contract": "MAPPED_BAM_PLUS_READ_COHERENT_SOURCE_FASTQ", "mapping_in_core_timer": false, "max_unit_workers": "explicit_required", "publication": "VALIDATE_THEN_ATOMIC_RENAME", "restart": "SHA_BOUND_SHARD_STATE_AND_POST_PUBLICATION_STATE_RECOVERY", "result_manifest_version": "rnatr_core_result_manifest_v0.1.0", "schema": "v0.4.2", "sharding_algorithm": "sha256(read_id)[0:8]_big_endian_modulo_shard_count", "shards": "explicit_required"}', 'lifecycle_status': 'ACTIVE', 'supersedes_implementation_id': None, 'rationale': 'Composite generic Core production entry accepted by Stage15J/L/M; replaces the legacy 11-row P0/P1 active path while retaining all legacy history.', 'evidence_path': '/mnt/intelssd/rnatr_project/qc/15_stage15n_generic_active_path_promotion/v0.1.0/stage15n_generic_active_path_promotion.qc.tsv', 'effective_at': '2026-08-11T15:30:00+00:00'}, {'implementation_id': 'impl_core_generic_sharded_v0_1_2', 'stage_key': 'CORE_GENERIC_SHARDED_ORCHESTRATOR', 'version': 'v0.1.2', 'script_path': '/mnt/intelssd/rnatr_project/scripts/rnatr_core_generic_sharded_v0.1.2.py', 'script_sha256': '76ccd6a41f95bd0d2bbf1bf0fba1b26e4232e8f526fae6ec86d3b3f06197784b', 'validator_path': None, 'validator_sha256': None, 'package_version': 'evidence_schema_v0.4.2', 'parameters_json': '{"merge": "deterministic_k_way", "partition": "sha256_first8_big_endian_modulo", "post_publication_state_recovery": true}', 'lifecycle_status': 'SUPPORT', 'supersedes_implementation_id': None, 'rationale': 'Generic sharding/merge/restart/publication implementation supporting the active composite entry.', 'evidence_path': '/mnt/intelssd/rnatr_project/qc/15_stage15n_generic_active_path_promotion/v0.1.0/stage15n_generic_active_path_promotion.qc.tsv', 'effective_at': '2026-08-11T15:30:00+00:00'}, {'implementation_id': 'impl_core_generic_unit_v0_1_1', 'stage_key': 'CORE_GENERIC_UNIT_BAM_FASTQ_TO_FINAL', 'version': 'v0.1.1', 'script_path': '/mnt/intelssd/rnatr_project/scripts/rnatr_core_generic_unit_v0.1.1.py', 'script_sha256': 'cff4bfc874cb07db6a98dfb679866a4f75a0eaa10c7c16c3bf3698fd5abf79f5', 'validator_path': '/mnt/intelssd/rnatr_project/config/evidence_schema/v0.4.2/rnatr_v042_validate_package.py', 'validator_sha256': '45c3995550f57a65b3fec4aab7471d57b7000e19471d4c5cf7f3ae055426984e', 'package_version': 'evidence_schema_v0.4.2', 'parameters_json': None, 'lifecycle_status': 'SUPPORT', 'supersedes_implementation_id': None, 'rationale': 'Accepted generic read-coherent unit used by the active sharded orchestrator.', 'evidence_path': '/mnt/intelssd/rnatr_project/qc/15_stage15n_generic_active_path_promotion/v0.1.0/stage15n_generic_active_path_promotion.qc.tsv', 'effective_at': '2026-08-11T15:30:00+00:00'}, {'implementation_id': 'impl_prebiology_manifest_smoke_v0_1_0', 'stage_key': 'PREBIOLOGY_RESULT_MANIFEST_SMOKE', 'version': 'v0.1.0', 'script_path': '/mnt/intelssd/rnatr_project/scripts/rnatr_prebiology_manifest_smoke_v0.1.0.py', 'script_sha256': 'eeb6442cdf9bebfec631ef718ad6298e27ec0d753a9f9ea999a24d4998d181dc', 'validator_path': None, 'validator_sha256': None, 'package_version': 'rnatr_core_result_manifest_v0.1.0', 'parameters_json': None, 'lifecycle_status': 'SUPPORT', 'supersedes_implementation_id': None, 'rationale': 'Read-only stable read/locus identity interface smoke supporting G24 PRE_BIOLOGY acceptance.', 'evidence_path': '/mnt/intelssd/rnatr_project/qc/15_stage15n_generic_active_path_promotion/v0.1.0/stage15n_generic_active_path_promotion.qc.tsv', 'effective_at': '2026-08-11T15:30:00+00:00'}, {'implementation_id': 'impl_core_resource_manifest_v0_1_0', 'stage_key': 'CORE_RUNTIME_RESOURCE_MANIFEST', 'version': 'v0.1.0', 'script_path': None, 'script_sha256': None, 'validator_path': None, 'validator_sha256': None, 'package_version': 'rnatr_core_resource_manifest_v0.1.0', 'parameters_json': '{"path": "/mnt/intelssd/rnatr_project/config/core_runtime/v0.1.0/resource_manifest.json", "sha256": "4418837acb0aa744fef0810d6db0260b6c534789a5e7e92ef123f9f79e848a2e"}', 'lifecycle_status': 'SUPPORT', 'supersedes_implementation_id': None, 'rationale': 'Project-relative checksum-pinned resource contract used to build run-local runtime configuration.', 'evidence_path': '/mnt/intelssd/rnatr_project/config/core_runtime/v0.1.0/resource_manifest.json', 'effective_at': '2026-08-11T15:30:00+00:00'}, {'implementation_id': 'impl_stage15n_generic_active_path_promotion_v0_1_0', 'stage_key': '15N_GENERIC_ACTIVE_PATH_PROMOTION', 'version': 'v0.1.0', 'script_path': '/mnt/intelssd/rnatr_project/scripts/rnatr_stage15n_promote_generic_active_path_v0.1.0.py', 'script_sha256': '64aac7a5430eee51cfe39628abf6d093758912f5340dbc9c0ecad522f19535c6', 'validator_path': None, 'validator_sha256': None, 'package_version': None, 'parameters_json': None, 'lifecycle_status': 'SUPPORT', 'supersedes_implementation_id': None, 'rationale': 'Versioned rollback-safe SSOT/current-pipeline promotion updater; not a scientific production entry.', 'evidence_path': '/mnt/intelssd/rnatr_project/qc/15_stage15n_generic_active_path_promotion/v0.1.0/stage15n_generic_active_path_promotion.qc.tsv', 'effective_at': '2026-08-11T15:30:00+00:00'}]
    for _s15n_r in _s15n_impls:
        conn.execute("""INSERT OR REPLACE INTO implementations(implementation_id,stage_key,version,script_path,script_sha256,validator_path,validator_sha256,package_version,parameters_json,lifecycle_status,supersedes_implementation_id,rationale,evidence_path,effective_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(_s15n_r['implementation_id'],_s15n_r['stage_key'],_s15n_r['version'],_s15n_r['script_path'],_s15n_r['script_sha256'],_s15n_r['validator_path'],_s15n_r['validator_sha256'],_s15n_r['package_version'],_s15n_r['parameters_json'],_s15n_r['lifecycle_status'],_s15n_r['supersedes_implementation_id'],_s15n_r['rationale'],_s15n_r['evidence_path'],_s15n_r['effective_at']))

    for _s15n_path,_s15n_sha in (('/mnt/intelssd/rnatr_project/scripts/rnatr_core_production_entry_v0.1.0.py','c6cf8298fb2dfb52b6bfbd7eda8d701356823644668d6d952abac09cc06358c4'),('/mnt/intelssd/rnatr_project/scripts/rnatr_core_generic_sharded_v0.1.2.py','76ccd6a41f95bd0d2bbf1bf0fba1b26e4232e8f526fae6ec86d3b3f06197784b'),('/mnt/intelssd/rnatr_project/scripts/rnatr_core_generic_unit_v0.1.1.py','cff4bfc874cb07db6a98dfb679866a4f75a0eaa10c7c16c3bf3698fd5abf79f5'),('/mnt/intelssd/rnatr_project/scripts/rnatr_prebiology_manifest_smoke_v0.1.0.py','eeb6442cdf9bebfec631ef718ad6298e27ec0d753a9f9ea999a24d4998d181dc'),('/mnt/intelssd/rnatr_project/scripts/rnatr_stage15n_promote_generic_active_path_v0.1.0.py','64aac7a5430eee51cfe39628abf6d093758912f5340dbc9c0ecad522f19535c6')):
        _s15n_stage="SCRIPT_"+Path(_s15n_path).stem
        _s15n_auto=implementation_id_for(_s15n_stage,_s15n_path,_s15n_sha)
        conn.execute("UPDATE implementations SET lifecycle_status='SUPERSEDED', rationale='Auto-discovery duplicate of an explicit Stage15N implementation.' WHERE implementation_id=? AND lifecycle_status='DISCOVERED'",(_s15n_auto,))

    _s15n_baseline_decisions = {'stage15_active_path_promotion_state_v0_1_0': {'decision_id': 'decision_922af47b2246dc9d6f975e9f', 'decision_key': 'stage15_active_path_promotion_state_v0_1_0', 'category': 'architecture_governance', 'title': 'Keep Stage15 candidate provisional after PRE-RC remediation and design a generic production entry point', 'statement': 'PRE_RELEASE_CANDIDATE current-state consistency is remediated, but the Stage15 candidate remains PROVISIONAL. Before promotion, construct and audit a generic portable production entry point with exact component bindings, rollback, and golden-regression guards; do not expose the dataset- and machine-bound benchmark runner unchanged as the public production CLI. G25-G30 and G32-G34 remain open.', 'status': 'ACTIVE', 'confidence': 'HIGH', 'effective_at': '2026-08-11T00:30:00+00:00', 'supersedes_decision_id': 'decision_9107f3c1daa35a2bc291', 'rationale': 'Full-scale correctness, documented-tolerance performance, and scoped determinism/restart are accepted; release packaging, portability, explicit promotion, freeze preservation, and clean-install gates are separate.', 'evidence_path': '/mnt/intelssd/rnatr_project/docs/stage15g/RNA_TR_Scout_PRE_RELEASE_CANDIDATE_Architecture_audit_v0.1.1.md'}, 'current_validator': {'decision_id': 'decision_58fd5e253a56fab18320f234', 'decision_key': 'current_validator', 'category': 'pipeline', 'title': 'Current alignment-segment validator', 'statement': "validator_v0.3.1 is current and accepts strand='.' for unmapped alignment records.", 'status': 'ACTIVE', 'confidence': 'HIGH', 'effective_at': '2026-08-06T00:00:00+00:00', 'supersedes_decision_id': None, 'rationale': 'Prevents recurrence of the obsolete validator error during full-BAM replay.', 'evidence_path': '/mnt/intelssd/rnatr_project/config/evidence_schema/v0.3/patches/validator_v0.3.1/rnatr_v03_validate_tsv_validator_v0.3.1.py'}}
    for _s15n_key,_s15n_expected in _s15n_baseline_decisions.items():
        _s15n_rows=conn.execute("SELECT * FROM decisions WHERE decision_key=? AND status='ACTIVE'",(_s15n_key,)).fetchall()
        if len(_s15n_rows)!=1 or dict(_s15n_rows[0])!=_s15n_expected:
            raise RuntimeError(f"Stage15N decision baseline mismatch: {_s15n_key}")
        conn.execute("UPDATE decisions SET status='SUPERSEDED' WHERE decision_id=?",(_s15n_expected['decision_id'],))
    _s15n_decisions = [{'decision_key': 'stage15_active_path_promotion_state_v0_1_0', 'category': 'architecture_governance', 'title': 'Promote the generic sharded Core to the active production path', 'statement': 'The active Core is the generic mapped-BAM plus read-coherent-source-FASTQ production entry v0.1.0, using sharded orchestrator v0.1.2, generic unit v0.1.1, evidence schema v0.4.2, portable result manifest v0.1.0, SHA-bound restart and post-publication final-state recovery. The legacy 11-row P0/P1 path is retained as history but is no longer current.', 'confidence': 'HIGH', 'supersedes_decision_id': 'decision_922af47b2246dc9d6f975e9f', 'rationale': 'Stage15J/L/M establish generic unit, full-input sharding, exact 100k parity, restart/no-op, PRE_BIOLOGY interface, and publication-boundary recovery while Stage15C/15E retain full-scale evidence.', 'evidence_path': '/mnt/intelssd/rnatr_project/qc/15_stage15n_generic_active_path_promotion/v0.1.0/stage15n_generic_active_path_promotion.qc.tsv'}, {'decision_key': 'current_validator', 'category': 'pipeline', 'title': 'Current Core package validation contract', 'statement': 'Evidence schema v0.4.2 table and package validators are the current active final-package validators; the v0.3.1 assignment validator remains a supporting intermediate validator.', 'confidence': 'HIGH', 'supersedes_decision_id': 'decision_58fd5e253a56fab18320f234', 'rationale': 'The active Core publishes schema v0.4.2 only after all validators pass.', 'evidence_path': '/mnt/intelssd/rnatr_project/qc/15_stage15n_generic_active_path_promotion/v0.1.0/stage15n_generic_active_path_promotion.qc.tsv'}, {'decision_key': 'generic_core_input_contract_v0_1_0', 'category': 'pipeline', 'title': 'Generic Core input requires mapped BAM plus read-coherent source FASTQ', 'statement': 'BAM alone is not the complete scientific input because raw source read sequence/quality is used by candidate extraction and hardclip-aware projection. BAM-to-final remains a timing boundary with mapping excluded.', 'confidence': 'HIGH', 'supersedes_decision_id': None, 'rationale': 'Stage15H-I exact-original review and Stage15J/L execution confirm the two-resource contract.', 'evidence_path': '/mnt/intelssd/rnatr_project/docs/stage15n/RNA_TR_Scout_Stage15N_generic_active_path_promotion_contract_v0.1.0.md'}, {'decision_key': 'mapping_baseline_separate_from_core_v0_1_0', 'category': 'performance_governance', 'title': 'Keep minimap2 splice mapping as a separate frozen scientific baseline', 'statement': 'The current minimap2 splice configuration remains the FASTQ-to-BAM scientific baseline outside the active Core. Mapping acceleration is a post-Freeze Performance lane gated by TR-locus recall, locus assignment and final-output parity.', 'confidence': 'HIGH', 'supersedes_decision_id': None, 'rationale': 'Pre-Freeze work freezes validated scientific behavior rather than beginning a new mapping-optimization effort.', 'evidence_path': '/mnt/intelssd/rnatr_project/docs/stage15n/RNA_TR_Scout_Stage15N_generic_active_path_promotion_contract_v0.1.0.md'}, {'decision_key': 'portable_core_result_manifest_v0_1_0', 'category': 'architecture', 'title': 'Portable Core result manifest is the biology-facing interface', 'statement': 'Downstream layers resolve stable read_id, target_source, target_region_id, locus_id and evidence/event/call identifiers through core_result_manifest.json; machine-local paths remain in a separate local binding file.', 'confidence': 'HIGH', 'supersedes_decision_id': None, 'rationale': 'Stage15J/L PRE_BIOLOGY smoke passes without Stage/dataset/developer-path dependence in the portable interface.', 'evidence_path': '/mnt/intelssd/rnatr_project/qc/15_stage15n_generic_active_path_promotion/v0.1.0/stage15n_generic_active_path_promotion.qc.tsv'}]
    for _s15n_r in _s15n_decisions:
        _s15n_id=decision_id_for(_s15n_r['decision_key'],_s15n_effective_at)
        conn.execute("""INSERT OR REPLACE INTO decisions(decision_id,decision_key,category,title,statement,status,confidence,effective_at,supersedes_decision_id,rationale,evidence_path) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",(_s15n_id,_s15n_r['decision_key'],_s15n_r['category'],_s15n_r['title'],_s15n_r['statement'],'ACTIVE',_s15n_r['confidence'],_s15n_effective_at,_s15n_r['supersedes_decision_id'],_s15n_r['rationale'],_s15n_r['evidence_path']))

    _s15n_baseline_interps = {'stage15a_reference_correctness_scope': {'interpretation_id': 'interp_1e482e9258389e0a9bed61b9', 'interpretation_key': 'stage15a_reference_correctness_scope', 'fact_statement': 'Stage15A v0.1.3 remains the isolated 100k correctness/regression reference; Stage15C v0.1.6 supplies empirical full-scale evidence and Stage15E supplies scoped checkpoint-based determinism/restart evidence.', 'interpretation': 'Use the 100k reference for focused correctness regression and the Stage15C/Stage15E artifacts for registered release-scale performance/restart evidence. None of these alone constitutes active-path promotion or the final golden regression suite.', 'do_not_interpret_as': 'Do not treat the historical v0.1.3 performance result as the current full-scale result, and do not treat Stage15E as an upstream full rerun or cross-machine proof.', 'status': 'ACTIVE', 'confidence': 'HIGH', 'effective_at': '2026-08-11T00:30:00+00:00', 'supersedes_interpretation_id': 'interp_f7db9e29c2358766276d040c', 'evidence_path': '/mnt/intelssd/rnatr_project/docs/stage15g/RNA_TR_Scout_PRE_RELEASE_CANDIDATE_Architecture_audit_v0.1.1.md', 'evidence_metrics_json': '{"stage15a_100k_reference": "PASS", "stage15c_fullscale": "PASS_WITH_DOCUMENTED_TOLERANCE", "stage15e_scope": "CHECKPOINT_BASED"}'}}
    for _s15n_key,_s15n_expected in _s15n_baseline_interps.items():
        _s15n_rows=conn.execute("SELECT * FROM interpretations WHERE interpretation_key=? AND status='ACTIVE'",(_s15n_key,)).fetchall()
        if len(_s15n_rows)!=1 or dict(_s15n_rows[0])!=_s15n_expected:
            raise RuntimeError(f"Stage15N interpretation baseline mismatch: {_s15n_key}")
        conn.execute("UPDATE interpretations SET status='SUPERSEDED' WHERE interpretation_id=?",(_s15n_expected['interpretation_id'],))
    _s15n_interps = [{'interpretation_key': 'stage15a_reference_correctness_scope', 'fact_statement': 'Stage15J and Stage15L reproduce the frozen 100k reference exactly through generic unit and generic sharded paths, while Stage15C and Stage15E retain empirical full-scale and scoped release-scale restart evidence.', 'interpretation': 'The accepted positive golden evidence now supports active-path promotion. G33 nevertheless remains open until fixed inputs, executable suite, negative fixtures and canonical placement are frozen.', 'do_not_interpret_as': 'Do not interpret active-path promotion as completion of the canonical golden regression suite, clean-install release, cross-hardware proof, biology implementation, or Core Freeze.', 'confidence': 'HIGH', 'supersedes_interpretation_id': 'interp_1e482e9258389e0a9bed61b9', 'evidence_path': '/mnt/intelssd/rnatr_project/qc/15_stage15n_generic_active_path_promotion/v0.1.0/stage15n_generic_active_path_promotion.qc.tsv', 'evidence_metrics': {'stage15j': 'PASS', 'stage15l': 'PASS_5_OF_5_EXACT_SHA256', 'stage15m_recovery': 'PASS'}}, {'interpretation_key': 'generic_active_path_promotion_scope_v0_1_0', 'fact_statement': 'The generic entry/unit/sharded paths pass fixed-input exact parity, validation, restart/no-op, portable manifest smoke and post-publication state recovery on the current machine, and bind unchanged scientific components to Stage15C/15E evidence.', 'interpretation': 'The generic Core may become the internal active production path.', 'do_not_interpret_as': 'Do not claim clean-install public release, cross-hardware reproducibility, arbitrary crash-instant coverage beyond registered tests, or closure of G24/G25-G34.', 'confidence': 'HIGH', 'supersedes_interpretation_id': None, 'evidence_path': '/mnt/intelssd/rnatr_project/qc/15_stage15n_generic_active_path_promotion/v0.1.0/stage15n_generic_active_path_promotion.qc.tsv', 'evidence_metrics': {'tier2': 'PASS', '100k_sharded': 'PASS', 'post_publication_recovery': 'PASS', 'fullscale_binding': 'Stage15C_Stage15E'}}, {'interpretation_key': 'mapping_baseline_scope_v0_1_0', 'fact_statement': 'The active Core accepts mapped BAM plus source FASTQ and does not run minimap2; the historical validated minimap2 splice configuration remains separately registered.', 'interpretation': 'Mapping runtime and optimization are separate from the active BAM-to-final Core contract.', 'do_not_interpret_as': 'Do not infer that source FASTQ is unnecessary or that any accelerated mapper is scientifically interchangeable without recall/assignment/final-output gates.', 'confidence': 'HIGH', 'supersedes_interpretation_id': None, 'evidence_path': '/mnt/intelssd/rnatr_project/docs/stage15n/RNA_TR_Scout_Stage15N_generic_active_path_promotion_contract_v0.1.0.md', 'evidence_metrics': {'mapping_in_core_timer': False}}, {'interpretation_key': 'prebiology_interface_smoke_scope_v0_1_0', 'fact_statement': 'The portable result manifest resolves a stable read identifier to BAM and a stable target/locus identity to pinned annotation in read-only smoke tests.', 'interpretation': 'The Core exposes a viable biology-layer connection interface before Freeze.', 'do_not_interpret_as': 'Do not interpret the smoke as implementation or validation of isoform, haplotype, observability, ranking, or disease biology.', 'confidence': 'HIGH', 'supersedes_interpretation_id': None, 'evidence_path': '/mnt/intelssd/rnatr_project/qc/15_stage15n_generic_active_path_promotion/v0.1.0/stage15n_generic_active_path_promotion.qc.tsv', 'evidence_metrics': {'stage15j_smoke': 'PASS', 'stage15l_smoke': 'PASS'}}]
    for _s15n_r in _s15n_interps:
        _s15n_id=interpretation_id_for(_s15n_r['interpretation_key'],_s15n_effective_at)
        conn.execute("""INSERT OR REPLACE INTO interpretations(interpretation_id,interpretation_key,fact_statement,interpretation,do_not_interpret_as,status,confidence,effective_at,supersedes_interpretation_id,evidence_path,evidence_metrics_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",(_s15n_id,_s15n_r['interpretation_key'],_s15n_r['fact_statement'],_s15n_r['interpretation'],_s15n_r['do_not_interpret_as'],'ACTIVE',_s15n_r['confidence'],_s15n_effective_at,_s15n_r['supersedes_interpretation_id'],_s15n_r['evidence_path'],json.dumps(_s15n_r['evidence_metrics'],sort_keys=True)))

    _s15n_baseline_contracts = {'evidence_schema_v042': {'contract_id': 'contract_1dd06f8e9188e7a0b93bce02', 'component_key': 'evidence_schema_v042', 'component_name': 'Evidence schema v0.4.2', 'implementation_state': 'FULLSCALE_VALIDATED_FROZEN_CORE_CANDIDATE_NOT_ACTIVE_PIPELINE', 'contract_statement': 'Schema v0.4.2 plus materializer v0.1.2 is the frozen Core evidence contract for the validated Stage15 candidate. It passed isolated 100k correctness, deterministic 250k/500k scaling, empirical 5,312,696-read execution, frozen validators, and Stage15E scoped package reconstruction/restart. This contract does not itself promote current_pipeline, provide biology sidecars, or close G25-G34.', 'active_implementation_id': None, 'evidence_path': '/mnt/intelssd/rnatr_project/qc/15_stage15e_determinism_restart/ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/v0.1.0/stage15e_combined_determinism_restart.qc.tsv', 'effective_at': '2026-08-11T00:30:00+00:00', 'status': 'ACTIVE'}, 'architecture_consistency_audit_v0_1_0': {'contract_id': 'contract_e542c6ab04bd8e6594f7f9f9', 'component_key': 'architecture_consistency_audit_v0_1_0', 'component_name': 'Architecture consistency audit contract v0.1.0', 'implementation_state': 'POST250K_AND_PRERC_PASS_PREBIOLOGY_OPEN', 'contract_statement': 'Major-checkpoint audits cross-check exact-original SSOT, active paths, schema/contracts, performance, validation/restart scope, biology roadmap, release gates, and lifecycle. POST_250K and PRE_RELEASE_CANDIDATE are complete; PRE_BIOLOGY remains mandatory, and focused audits are required around active-path promotion or other major architecture changes. Conversation summaries and memory are not authoritative evidence.', 'active_implementation_id': 'impl_stage15g_prerc_architecture_remediation_v0_1_1', 'evidence_path': '/mnt/intelssd/rnatr_project/docs/stage15g/RNA_TR_Scout_PRE_RELEASE_CANDIDATE_Architecture_audit_v0.1.1.md', 'effective_at': '2026-08-11T00:30:00+00:00', 'status': 'ACTIVE'}}
    for _s15n_key,_s15n_expected in _s15n_baseline_contracts.items():
        _s15n_rows=conn.execute("SELECT * FROM algorithm_contracts WHERE component_key=? AND status='ACTIVE'",(_s15n_key,)).fetchall()
        if len(_s15n_rows)!=1 or dict(_s15n_rows[0])!=_s15n_expected:
            raise RuntimeError(f"Stage15N contract baseline mismatch: {_s15n_key}")
        conn.execute("UPDATE algorithm_contracts SET status='SUPERSEDED' WHERE contract_id=?",(_s15n_expected['contract_id'],))
    _s15n_contracts = [{'component_key': 'evidence_schema_v042', 'component_name': 'Evidence schema v0.4.2', 'implementation_state': 'ACTIVE_FROZEN_CORE_EVIDENCE_CONTRACT', 'contract_statement': 'Schema v0.4.2 plus materializer v0.1.2 is the active Core evidence contract. It passed generic single-unit and 12-shard exact 100k parity, empirical 5.31M execution, scoped release-scale reconstruction/restart, frozen validators and portable manifest publication. Biology sidecars and G25-G34 remain separate.', 'active_implementation_id': 'impl_core_generic_production_entry_v0_1_0', 'supersedes_contract_id': 'contract_1dd06f8e9188e7a0b93bce02', 'evidence_path': '/mnt/intelssd/rnatr_project/qc/15_stage15n_generic_active_path_promotion/v0.1.0/stage15n_generic_active_path_promotion.qc.tsv'}, {'component_key': 'architecture_consistency_audit_v0_1_0', 'component_name': 'Architecture consistency audit contract v0.1.0', 'implementation_state': 'POST250K_PRERC_AND_PROMOTION_AUTOMATED_PASS_PREBIOLOGY_OPEN', 'contract_statement': 'Major-checkpoint audits use exact originals across SSOT, active code/path, schemas/contracts, performance, restart, biology roadmap, release gates and lifecycle. POST_250K and PRE-RC are complete; Stage15N promotion has exact automated postconditions and requires focused Pro review; the formal exact-original PRE_BIOLOGY audit remains mandatory.', 'active_implementation_id': 'impl_stage15n_generic_active_path_promotion_v0_1_0', 'supersedes_contract_id': 'contract_e542c6ab04bd8e6594f7f9f9', 'evidence_path': '/mnt/intelssd/rnatr_project/qc/15_stage15n_generic_active_path_promotion/v0.1.0/stage15n_generic_active_path_promotion.qc.tsv'}, {'component_key': 'generic_active_core_path_v0_1_0', 'component_name': 'Generic active Core production entry', 'implementation_state': 'ACTIVE', 'contract_statement': 'The public Core entry takes mapped BAM plus read-coherent source FASTQ and explicit run/sample/work/output/sharding/concurrency parameters, resolves project-relative checksum-pinned resources, and invokes the generic sharded Core without dataset or developer-machine binding.', 'active_implementation_id': 'impl_core_generic_production_entry_v0_1_0', 'supersedes_contract_id': None, 'evidence_path': '/mnt/intelssd/rnatr_project/qc/15_stage15n_generic_active_path_promotion/v0.1.0/stage15n_generic_active_path_promotion.qc.tsv'}, {'component_key': 'generic_sharded_orchestrator_v0_1_2', 'component_name': 'Generic sharded Core orchestrator v0.1.2', 'implementation_state': 'ACTIVE_SUPPORT', 'contract_statement': 'Use the frozen read-ID SHA-256 partition, bounded validated units, deterministic defensive k-way merge, validate-before-atomic-publication, SHA-bound resume/no-op, and recovery of missing final state from an already published validated package with zero scientific commands.', 'active_implementation_id': 'impl_core_generic_sharded_v0_1_2', 'supersedes_contract_id': None, 'evidence_path': '/mnt/intelssd/rnatr_project/qc/15_stage15n_generic_active_path_promotion/v0.1.0/stage15n_generic_active_path_promotion.qc.tsv'}, {'component_key': 'generic_unit_runner_v0_1_1', 'component_name': 'Generic read-coherent Core unit v0.1.1', 'implementation_state': 'ACTIVE_SUPPORT', 'contract_statement': 'Execute the exact frozen target assignment, raw-read projection, motif preparation, caller v0.4.1, materializer v0.1.2 and schema v0.4.2 validators for one read-coherent BAM/FASTQ unit.', 'active_implementation_id': 'impl_core_generic_unit_v0_1_1', 'supersedes_contract_id': None, 'evidence_path': '/mnt/intelssd/rnatr_project/qc/15_stage15n_generic_active_path_promotion/v0.1.0/stage15n_generic_active_path_promotion.qc.tsv'}, {'component_key': 'core_result_manifest_v0_1_0', 'component_name': 'Portable Core result manifest v0.1.0', 'implementation_state': 'ACTIVE_INTERFACE', 'contract_statement': 'Publish logical resources, checksums, versions, relative artifacts, stable join keys, coordinate/scientific semantics, validation and performance references without absolute paths; keep local paths in resource_bindings.local.json.', 'active_implementation_id': 'impl_core_generic_production_entry_v0_1_0', 'supersedes_contract_id': None, 'evidence_path': '/mnt/intelssd/rnatr_project/qc/15_stage15n_generic_active_path_promotion/v0.1.0/stage15n_generic_active_path_promotion.qc.tsv'}, {'component_key': 'prebiology_manifest_smoke_v0_1_0', 'component_name': 'PRE_BIOLOGY manifest interface smoke v0.1.0', 'implementation_state': 'PASS_READ_ONLY_INTERFACE', 'contract_statement': 'From the formal result manifest and local binding file, resolve stable read_id to a primary BAM alignment and target_source/target_region_id/locus_id to one pinned annotation without Stage/dataset/developer-path assumptions.', 'active_implementation_id': 'impl_prebiology_manifest_smoke_v0_1_0', 'supersedes_contract_id': None, 'evidence_path': '/mnt/intelssd/rnatr_project/qc/15_stage15n_generic_active_path_promotion/v0.1.0/stage15n_generic_active_path_promotion.qc.tsv'}, {'component_key': 'fastq_to_bam_mapping_baseline_v0_3_1', 'component_name': 'Frozen minimap2 splice FASTQ-to-BAM baseline', 'implementation_state': 'REFERENCE_BASELINE_OUTSIDE_ACTIVE_CORE', 'contract_statement': 'Retain minimap2 2.31-r1302 splice mapping with junction BED, secondary alignments, N=10, MD and cs=long as the current scientific mapping baseline. Mapping is outside BAM-to-final timing; post-Freeze acceleration requires TR-locus recall, locus assignment and final-output parity.', 'active_implementation_id': 'impl_8e35dcc35a40649c98d0334e', 'supersedes_contract_id': None, 'evidence_path': '/mnt/intelssd/rnatr_project/docs/stage15n/RNA_TR_Scout_Stage15N_generic_active_path_promotion_contract_v0.1.0.md'}, {'component_key': 'positive_golden_evidence_v0_1_0', 'component_name': 'Positive Core golden evidence', 'implementation_state': 'EVIDENCE_ACCEPTED_CANONICAL_SUITE_OPEN', 'contract_statement': 'Stage15J Tier-2 and Stage15L 100k exact five-table parity/restart/no-op plus Stage15C/15E Tier-3 evidence guard the promoted active path. G33 remains open until canonical fixed inputs, executable suite, negative fixtures, manifests and placement are frozen.', 'active_implementation_id': None, 'supersedes_contract_id': None, 'evidence_path': '/mnt/intelssd/rnatr_project/qc/15_stage15n_generic_active_path_promotion/v0.1.0/stage15n_generic_active_path_promotion.qc.tsv'}]
    for _s15n_r in _s15n_contracts:
        _s15n_id='contract_'+hashlib.sha256(f"{_s15n_r['component_key']}\0{_s15n_effective_at}".encode('utf-8')).hexdigest()[:24]
        conn.execute("""INSERT OR REPLACE INTO algorithm_contracts(contract_id,component_key,component_name,implementation_state,contract_statement,active_implementation_id,evidence_path,effective_at,status) VALUES(?,?,?,?,?,?,?,?,?)""",(_s15n_id,_s15n_r['component_key'],_s15n_r['component_name'],_s15n_r['implementation_state'],_s15n_r['contract_statement'],_s15n_r['active_implementation_id'],_s15n_r['evidence_path'],_s15n_effective_at,'ACTIVE'))

    _s15n_limit=conn.execute("SELECT * FROM limitations WHERE limitation_key=?",('STAGE15_ACTIVE_PATH_AND_PORTABLE_ENTRYPOINT_NOT_PROMOTED',)).fetchone()
    if _s15n_limit is None or dict(_s15n_limit)!={'limitation_key': 'STAGE15_ACTIVE_PATH_AND_PORTABLE_ENTRYPOINT_NOT_PROMOTED', 'statement': 'The empirically validated Stage15 candidate remains PROVISIONAL; current_pipeline still points to the legacy P0/P1 path, and the validated full-scale runner is dataset- and machine-bound rather than a generic public production entry point.', 'severity': 'HIGH', 'status': 'ACTIVE', 'mitigation': 'Design and audit a generic portable production entry point with exact component/resource bindings, versioned active-path promotion, rollback, and golden-regression guards. Keep G25-G30 and G32-G34 open until separately satisfied.', 'evidence_path': '/mnt/intelssd/rnatr_project/docs/stage15g/RNA_TR_Scout_PRE_RELEASE_CANDIDATE_Architecture_audit_v0.1.1.md', 'effective_at': '2026-08-11T00:30:00+00:00'}:
        raise RuntimeError('Stage15N limitation baseline mismatch')
    conn.execute("UPDATE limitations SET status='SUPERSEDED' WHERE limitation_key='STAGE15_ACTIVE_PATH_AND_PORTABLE_ENTRYPOINT_NOT_PROMOTED'")
    _s15n_new_limits=[{'limitation_key': 'GENERIC_ACTIVE_PATH_NOT_CLEAN_INSTALL_OR_CROSS_HARDWARE', 'statement': 'The generic Core is promoted for the current internal project, but clean-machine installation, automatic bootstrap/resource selection, cross-hardware/concurrency reproducibility and public release packaging remain open.', 'severity': 'HIGH', 'mitigation': 'Keep G25-G30 and G28 open; do not claim v1/public clean-install readiness until independently validated.', 'evidence_path': '/mnt/intelssd/rnatr_project/qc/15_stage15n_generic_active_path_promotion/v0.1.0/stage15n_generic_active_path_promotion.qc.tsv'}, {'limitation_key': 'GENERIC_ACTIVE_PATH_GOLDEN_SUITE_NOT_YET_CANONICALLY_PACKAGED', 'statement': 'Positive golden and release-scale evidence is accepted, but the formal fixed-input executable golden suite, negative fixtures and canonical long-term placement are not yet complete.', 'severity': 'HIGH', 'mitigation': 'Complete G33 and G34 before Core Freeze; preserve current Downloads/evidence artifacts until canonical checksummed placement.', 'evidence_path': '/mnt/intelssd/rnatr_project/docs/stage15n/RNA_TR_Scout_Stage15N_generic_active_path_promotion_contract_v0.1.0.md'}, {'limitation_key': 'GENERIC_ACTIVE_PATH_MAPPING_IS_SEPARATE_BASELINE', 'statement': 'The active Core starts from mapped BAM plus source FASTQ and does not itself execute FASTQ-to-BAM mapping.', 'severity': 'MODERATE', 'mitigation': 'Keep the minimap2 splice baseline separately versioned; evaluate any mapping acceleration only in the post-Freeze Performance lane with scientific parity gates.', 'evidence_path': '/mnt/intelssd/rnatr_project/docs/stage15n/RNA_TR_Scout_Stage15N_generic_active_path_promotion_contract_v0.1.0.md'}]
    for _s15n_r in _s15n_new_limits:
        conn.execute("INSERT OR REPLACE INTO limitations(limitation_key,statement,severity,status,mitigation,evidence_path,effective_at) VALUES(?,?,?,?,?,?,?)",(_s15n_r['limitation_key'],_s15n_r['statement'],_s15n_r['severity'],'ACTIVE',_s15n_r['mitigation'],_s15n_r['evidence_path'],_s15n_effective_at))

    _s15n_questions_expected={'ACTIVE_PATH_PROMOTION': {'question_key': 'ACTIVE_PATH_PROMOTION', 'question': 'When and how should the validated Stage15 candidate replace the legacy active P0/P1 pipeline?', 'priority': 'CRITICAL', 'status': 'OPEN', 'blocking': 1, 'next_action': 'Design a generic portable production entry point from the exact validated components, define promotion/rollback and golden-regression guards, and run a separate versioned promotion preflight. Do not promote the dataset-bound Stage15C benchmark runner unchanged.', 'evidence_path': '/mnt/intelssd/rnatr_project/docs/stage15g/RNA_TR_Scout_PRE_RELEASE_CANDIDATE_Architecture_audit_v0.1.1.md', 'effective_at': '2026-08-11T00:30:00+00:00'}, 'ARCHITECTURE_CONSISTENCY_AUDIT_CLOSURE': {'question_key': 'ARCHITECTURE_CONSISTENCY_AUDIT_CLOSURE', 'question': 'Are SSOT, active code/path, schema/contracts, performance gates, validation/restart scope, biology roadmap, and implementation lifecycle mutually consistent at each major checkpoint?', 'priority': 'CRITICAL', 'status': 'OPEN', 'blocking': 1, 'next_action': 'POST_250K and PRE_RELEASE_CANDIDATE checkpoints are complete. Perform the exact-original PRE_BIOLOGY audit before biology-layer implementation; add focused audits around active-path promotion or major contract changes.', 'evidence_path': '/mnt/intelssd/rnatr_project/validation/release_gates_v0.3.2.tsv', 'effective_at': '2026-08-11T00:30:00+00:00'}, 'GOLDEN_REGRESSION_SUITE': {'question_key': 'GOLDEN_REGRESSION_SUITE', 'question': 'Does a fixed-input expected-output suite mechanically enforce the frozen Core scientific contract, including exact/logical parity rules and negative fixtures?', 'priority': 'CRITICAL', 'status': 'OPEN', 'blocking': 1, 'next_action': 'Build, run, and freeze the G33 suite before Core Freeze; future biology and performance changes must run it.', 'evidence_path': '/mnt/intelssd/rnatr_project/docs/governance/RNA_TR_Scout_Core_Freeze_governance_requirements_v0.1.0.md', 'effective_at': '2026-08-10T12:30:00+00:00'}, 'BIOLOGY_READY_INTERPRETATION_OUTPUT_AUDIT': {'question_key': 'BIOLOGY_READY_INTERPRETATION_OUTPUT_AUDIT', 'question': 'Can the final output support same-haplotype molecule-level repeat heterogeneity, repeat-to-isoform/splicing association, observability-aware inference, molecule-independence-aware support, purpose-specific triage, and fully traceable researcher dossiers without losing core read-level repeat information?', 'priority': 'CRITICAL', 'status': 'OPEN', 'blocking': 1, 'next_action': 'After active-path promotion and Core Freeze preservation artifacts are complete, run PRE_BIOLOGY Architecture audit, then freeze sidecar schemas/validators and implement G20-G23 without rewriting the core 5-table source of truth.', 'evidence_path': '/mnt/intelssd/rnatr_project/docs/governance/RNA_TR_Scout_Core_Freeze_governance_requirements_v0.1.0.md', 'effective_at': '2026-08-11T00:30:00+00:00'}}
    for _s15n_key,_s15n_expected in _s15n_questions_expected.items():
        _s15n_row=conn.execute("SELECT * FROM open_questions WHERE question_key=?",(_s15n_key,)).fetchone()
        if _s15n_row is None or dict(_s15n_row)!=_s15n_expected:
            raise RuntimeError(f"Stage15N open-question baseline mismatch: {_s15n_key}")
    conn.execute("UPDATE open_questions SET status='CLOSED',blocking=0,next_action=?,evidence_path=?,effective_at=? WHERE question_key='ACTIVE_PATH_PROMOTION'",('Closed by Stage15N generic active-path promotion; continue post-promotion Architecture review and remaining Freeze/release gates.','/mnt/intelssd/rnatr_project/qc/15_stage15n_generic_active_path_promotion/v0.1.0/stage15n_generic_active_path_promotion.qc.tsv',_s15n_effective_at))
    conn.execute("UPDATE open_questions SET next_action=?,evidence_path=?,effective_at=? WHERE question_key='ARCHITECTURE_CONSISTENCY_AUDIT_CLOSURE'",('Review the Stage15N post-promotion bundle using exact originals, then perform the mandatory formal PRE_BIOLOGY Architecture audit before biology implementation.','/mnt/intelssd/rnatr_project/qc/15_stage15n_generic_active_path_promotion/v0.1.0/stage15n_generic_active_path_promotion.qc.tsv',_s15n_effective_at))
    conn.execute("UPDATE open_questions SET next_action=?,evidence_path=?,effective_at=? WHERE question_key='GOLDEN_REGRESSION_SUITE'",('Canonicalize the accepted Stage15J/L/M positive evidence with fixed inputs, executable suite, negative fixtures, manifests and long-term placement before Core Freeze.','/mnt/intelssd/rnatr_project/qc/15_stage15n_generic_active_path_promotion/v0.1.0/stage15n_generic_active_path_promotion.qc.tsv',_s15n_effective_at))
    conn.execute("UPDATE open_questions SET next_action=?,evidence_path=?,effective_at=? WHERE question_key='BIOLOGY_READY_INTERPRETATION_OUTPUT_AUDIT'",('Complete G32-G34, run the exact-original PRE_BIOLOGY Architecture audit and then implement G20-G23 sidecars without rewriting the active Core 5-table source of truth.','/mnt/intelssd/rnatr_project/qc/15_stage15n_generic_active_path_promotion/v0.1.0/stage15n_generic_active_path_promotion.qc.tsv',_s15n_effective_at))

    _s15n_pipeline=conn.execute("SELECT stage_key,implementation_id FROM implementations WHERE lifecycle_status='ACTIVE'").fetchall()
    if len(_s15n_pipeline)!=1 or tuple(_s15n_pipeline[0])!=('CORE_GENERIC_SHARDED_BAM_FASTQ_TO_FINAL','impl_core_generic_production_entry_v0_1_0'):
        raise RuntimeError(f"Stage15N active pipeline postcondition mismatch: {[tuple(r) for r in _s15n_pipeline]}")
    _s15n_discovered=conn.execute("SELECT COUNT(*) FROM implementations WHERE lifecycle_status='DISCOVERED'").fetchone()[0]
    if _s15n_discovered!=0:
        raise RuntimeError(f"Stage15N DISCOVERED implementation postcondition mismatch: {_s15n_discovered}")


    # Stage15T final local Core Freeze registration v0.1.0
    _s15t_effective_at = "2026-08-12T09:45:00+00:00"
    _s15t_source_guards = {
        "docs/README_CANONICAL_STRUCTURE_v0.1.1.md": "aeee3c7d4d133b283739fd4343b5f2efd11a3aa7cf8563e828c44e99af9154b2",
        "docs/CURRENT_CANONICAL_STRUCTURE.tsv": "e026a022b1ee20100f3b321c27e4a19c50c44f4ec294157646f725cca99bf253",
        "docs/contracts/CURRENT_CONTRACTS_v0.1.0.tsv": "be29ba879099256b9f340a7d0a8e51447b6181ce68b71ac87140d5edaafe1857",
        "docs/contracts/RNA_TR_Scout_Candidate_assignment_reverse_traceability_contract_v0.1.1.md": "3216bcfd71600af4b44478a438b677c5480e4267549f42db3e87bd51bf6e7a0b",
        "docs/contracts/RNA_TR_Scout_Core_Technical_Completion_and_Freeze_contract_v0.1.2.md": "613ec36efcc43e04553efc8f0191222ca24e243f91fe2b4e74d71a22beae0ea1",
        "docs/contracts/RNA_TR_Scout_Future_extensibility_boundary_contract_v0.1.1.md": "8e9f10da2a1e47f616e60fb5e9705213ab7b08eaf8f69e3ca9939f4124dd0779",
        "docs/contracts/approved_sources/RNA_TR_Scout_Core_Technical_Completion_and_Freeze_contract_v0.1.2_OWNER_APPROVED_SOURCE.md": "b8458fbacd13ca260de3e2ccb68aff17e45d25df304bdeeebf58be76fa0dab8b",
        "docs/core_freeze/v0.1.1/RNA_TR_Scout_Core_Freeze_Packet_v0.1.1.md": "b1d89230bf0d7f13b0345e99443e36a350861ce336e607a7ba10c8d2004a062e",
        "docs/core_freeze/v0.1.1/approved_sources/RNA_TR_Scout_Core_Freeze_Packet_v0.1.1_OWNER_APPROVED_SOURCE.md": "af5c437f3e419f58c4daeaa865777751410bd006cc65ca02e40c78ed4d87aa68",
        "docs/governance/RNA_TR_Scout_Core_Freeze_final_hygiene_audit_v0.1.0.md": "6f00dacc456828c32d7fcf8ac77dc28d7ff75a359a45a64cf5e6b82b2ae05f59",
        "validation/golden/v0.1.1/README.md": "bfa399305f584c3e7acd7c88c857dc199a261ad5b266fc3a84f19605bdcf866a",
        "validation/golden/v0.1.1/rnatr_golden_regression_v015.py": "3974219d51490389ce2cb994dec4271188726a2bea3fe1e0517ceb5a1021c2e0",
        "validation/release_gates_v0.3.4.tsv": "ba57781d12bf8638a95da94cd73bb845a7e35e0123fe7690b4559a09d5deed3f"
}
    for _s15t_rel, _s15t_expected in _s15t_source_guards.items():
        _s15t_path = (project_root / _s15t_rel).resolve()
        if not _s15t_path.is_file() or sha256_file(_s15t_path) != _s15t_expected:
            raise RuntimeError(f"Stage15T source guard failed: {_s15t_rel}")
        source_document(conn, _s15t_path, "stage15t_final_core_freeze_registration", force_hash=True)

    # Apply the audited Stage15T registration overlay after all source guards pass.
    _stage15t_apply_registration_overlay(conn, str(project_root))


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

    legacy_required_stages = [
        "MAP_SPLICE","11b_TARGET_ASSIGNMENT","11d3_RAW_READ_PROJECTION",
        "11e_MOTIF_JOBS","11f_PERIODIC_BASELINE","11g_BASELINE_AUDIT",
        "11h_PERIODIC_REFINEMENT","11i_INTERNAL_RECLASSIFICATION",
        "11j_EXACT_SPAN_CALIBRATION","11k_CALIBRATED_EVIDENCE",
        "11k3_SPAN_NORMALIZATION",
    ]
    generic_stage = "CORE_GENERIC_SHARDED_BAM_FASTQ_TO_FINAL"
    generic_active = conn.execute(
        "SELECT COUNT(*) FROM implementations WHERE stage_key=? AND lifecycle_status='ACTIVE'",
        (generic_stage,),
    ).fetchone()[0]
    legacy_counts = {
        stage: conn.execute(
            "SELECT COUNT(*) FROM implementations WHERE stage_key=? AND lifecycle_status='ACTIVE'",
            (stage,),
        ).fetchone()[0]
        for stage in legacy_required_stages
    }
    generic_mode_ok = generic_active == 1 and all(count == 0 for count in legacy_counts.values())
    legacy_mode_ok = generic_active == 0 and all(count == 1 for count in legacy_counts.values())
    checks.append((
        "active_pipeline_mode",
        "PASS" if (generic_mode_ok or legacy_mode_ok) else "FAIL",
        "GENERIC_CORE" if generic_mode_ok else ("LEGACY_P0_P1" if legacy_mode_ok else f"INVALID:generic={generic_active};legacy={legacy_counts}"),
    ))
    checks.append((
        f"active_impl::{generic_stage}",
        "PASS" if generic_active == (1 if generic_mode_ok else 0) else "FAIL",
        str(generic_active),
    ))
    for stage,count in legacy_counts.items():
        expected = 0 if generic_mode_ok else 1
        checks.append((f"active_impl::{stage}", "PASS" if count == expected else "FAIL", str(count)))

    active_missing = conn.execute(
        """
        SELECT script_path FROM implementations
        WHERE lifecycle_status='ACTIVE' AND (script_path IS NULL OR script_path='')
        """
    ).fetchall()
    checks.append(("active_implementation_paths_present", "PASS" if not active_missing else "FAIL", str(len(active_missing))))

    unexpanded_paths = []
    for row in conn.execute(
        """
        SELECT stage_key, script_path, validator_path
        FROM implementations
        WHERE lifecycle_status='ACTIVE'
        """
    ):
        for label, value in (("script", row[1]), ("validator", row[2])):
            if value and "$" in value:
                unexpanded_paths.append(f"{row[0]}:{label}:{value}")
    checks.append((
        "active_paths_have_no_shell_variables",
        "PASS" if not unexpanded_paths else "FAIL",
        ";".join(unexpanded_paths) if unexpanded_paths else "0",
    ))

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

    # Validate the adopted final-package validator for the active pipeline mode.
    generic_row = conn.execute(
        "SELECT validator_path FROM current_pipeline WHERE stage_key='CORE_GENERIC_SHARDED_BAM_FASTQ_TO_FINAL'"
    ).fetchone()
    if generic_row and generic_row[0]:
        validator_path = Path(generic_row[0])
        validator_exists = validator_path.is_file()
        checks.append(("current_validator_exists", "PASS" if validator_exists else "FAIL", str(validator_path)))
        validator_ok = (
            validator_path.name == "rnatr_v042_validate_package.py"
            and "v0.4.2" in str(validator_path)
        )
        checks.append(("current_validator_is_v0.4.2_package", "PASS" if validator_ok else "FAIL", str(validator_path)))
        validator_sha = sha256_file(validator_path) if validator_exists else "."
        checks.append(("current_validator_sha256_recorded", "PASS" if validator_exists and len(validator_sha) == 64 else "FAIL", validator_sha))
    else:
        row = conn.execute(
            "SELECT validator_path FROM current_pipeline WHERE stage_key='11b_TARGET_ASSIGNMENT'"
        ).fetchone()
        if row and row[0]:
            validator_path = Path(row[0])
            validator_exists = validator_path.is_file()
            checks.append(("current_validator_exists", "PASS" if validator_exists else "FAIL", str(validator_path)))
            validator_name_ok = "0.3.1" in validator_path.name
            checks.append(("current_validator_is_v0.3.1", "PASS" if validator_name_ok else "FAIL", validator_path.name))
            validator_sha = sha256_file(validator_path) if validator_exists else "."
            checks.append(("current_validator_sha256_recorded", "PASS" if validator_exists and len(validator_sha) == 64 else "FAIL", validator_sha))
        else:
            checks.append(("current_validator_exists", "FAIL", "not recorded"))
            checks.append(("current_validator_mode", "FAIL", "neither generic Core nor legacy 11b validator recorded"))
            checks.append(("current_validator_sha256_recorded", "FAIL", "not recorded"))

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

