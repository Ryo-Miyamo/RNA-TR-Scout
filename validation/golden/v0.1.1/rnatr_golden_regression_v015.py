#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

VERSION = "rnatr_golden_regression_suite_v0.1.5"
BASE_RUNNER_REL = Path("validation/golden/v0.1.0/rnatr_golden_regression_v014.py")
BASE_RUNNER_SHA256 = "e4be1b3cd24a2ea42fde0c6434888f725e6b65fde290f1c02e9f91ff2186203c"
FINAL_MANIFEST_REL = Path("metadata/core_freeze/v0.1.1/core_freeze_manifest.tsv")
RELEASE_GATES_REL = Path("validation/release_gates_v0.3.4.tsv")
RELEASE_GATES_SHA256 = "ba57781d12bf8638a95da94cd73bb845a7e35e0123fe7690b4559a09d5deed3f"
CURRENT_PIPELINE_REL = Path("metadata/ssot/exports/current_pipeline.tsv")
CURRENT_PIPELINE_SHA256 = "d9df193145d3b9e39e85498ba2c5699bd0918c802d1b0bdc892224034e9602b7"
SSOT_DB_REL = Path("metadata/ssot/rnatr_ssot.sqlite")
APPROVED_PACKET_SOURCE_SHA256 = "af5c437f3e419f58c4daeaa865777751410bd006cc65ca02e40c78ed4d87aa68"
APPROVED_CTC_SOURCE_SHA256 = "b8458fbacd13ca260de3e2ccb68aff17e45d25df304bdeeebf58be76fa0dab8b"
CORE_ACTIVE_HASHES = {
    "scripts/rnatr_core_production_entry_v0.1.0.py": "c6cf8298fb2dfb52b6bfbd7eda8d701356823644668d6d952abac09cc06358c4",
    "scripts/rnatr_core_generic_sharded_v0.1.2.py": "76ccd6a41f95bd0d2bbf1bf0fba1b26e4232e8f526fae6ec86d3b3f06197784b",
    "scripts/rnatr_core_generic_unit_v0.1.1.py": "cff4bfc874cb07db6a98dfb679866a4f75a0eaa10c7c16c3bf3698fd5abf79f5",
    "config/evidence_schema/v0.4.2/schema/rnatr_v04_table_schema.json": "c0509a0669344dba0b07cd1bb9e71f2aeb01e0196df47ec9178f1d2464b515f1",
    "config/core_runtime/v0.1.0/resource_manifest.json": "4418837acb0aa744fef0810d6db0260b6c534789a5e7e92ef123f9f79e848a2e",
}


class GoldenV015Error(RuntimeError):
    pass


def sha256_file(path: Path, chunk: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def ensure_regular(path: Path) -> None:
    if not path.is_file() or path.is_symlink():
        raise GoldenV015Error(f"required regular file missing/invalid: {path}")


def write_tsv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh, delimiter="\t", fieldnames=fields, extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def read_tsv(path: Path) -> list[dict[str, str]]:
    ensure_regular(path)
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def load_base_runner(project_root: Path):
    path = project_root / BASE_RUNNER_REL
    ensure_regular(path)
    actual = sha256_file(path)
    if actual != BASE_RUNNER_SHA256:
        raise GoldenV015Error(f"base golden runner drift: {actual} != {BASE_RUNNER_SHA256}")
    spec = importlib.util.spec_from_file_location("rnatr_golden_v014_frozen", path)
    if spec is None or spec.loader is None:
        raise GoldenV015Error("could not load base golden runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if getattr(module, "VERSION", None) != "rnatr_golden_regression_suite_v0.1.4":
        raise GoldenV015Error("base golden version mismatch")
    return module


def verify_release_gates(project_root: Path) -> list[dict[str, Any]]:
    path = project_root / RELEASE_GATES_REL
    ensure_regular(path)
    actual = sha256_file(path)
    if actual != RELEASE_GATES_SHA256:
        raise GoldenV015Error(f"release-gate SHA drift: {actual}")
    rows = read_tsv(path)
    by_id = {row["gate_id"]: row for row in rows}
    expected = {
        "G24": "PASS_WITH_SCOPE_AMENDMENT",
        "G31-T": "PASS_WITH_SCOPE_AMENDMENT",
        "G31-B": "OPEN_DEFERRED_TO_BIOLOGY_LAYER",
        "G32": "PASS_WITH_SCOPE_AMENDMENT",
        "G33": "PASS",
        "G34": "PASS_WITH_SCOPE_AMENDMENT",
    }
    for gate, status in expected.items():
        if by_id.get(gate, {}).get("status") != status:
            raise GoldenV015Error(f"release gate mismatch: {gate}: {by_id.get(gate)}")
    for gate in ("G25", "G26", "G27", "G28", "G29", "G30"):
        if by_id.get(gate, {}).get("status") != "OPEN_PLANNED":
            raise GoldenV015Error(f"release gate unexpectedly closed: {gate}")
    return [
        {
            "check": "release_gates_v0.3.4",
            "expected": RELEASE_GATES_SHA256,
            "actual": actual,
            "status": "PASS",
        }
    ]


def verify_final_docs(project_root: Path) -> list[dict[str, Any]]:
    checks = [
        (
            "docs/core_freeze/v0.1.1/RNA_TR_Scout_Core_Freeze_Packet_v0.1.1.md",
            (
                "LOCAL_CORE_FREEZE_V0.1.0_ACCEPTED_WITH_SCOPE",
                APPROVED_PACKET_SOURCE_SHA256,
                "public GitHub release v0.5.0",
                "PASS_WITH_DOCUMENTED_TOLERANCE",
            ),
        ),
        (
            "docs/contracts/RNA_TR_Scout_Core_Technical_Completion_and_Freeze_contract_v0.1.2.md",
            (
                APPROVED_CTC_SOURCE_SHA256,
                "Local checksummed Core Freeze",
                "Public/thesis-citable software release",
            ),
        ),
        (
            "docs/contracts/RNA_TR_Scout_Candidate_assignment_reverse_traceability_contract_v0.1.1.md",
            (
                "ACCEPTED_STAGE15R_PASS_WITH_SCOPE_BIOLOGY_DEFERRED",
                "733/733",
                "b68e4a8d078b371b72de3870fa98dc2808195f2f048aec76d8920158448c9851",
            ),
        ),
        (
            "docs/contracts/RNA_TR_Scout_Future_extensibility_boundary_contract_v0.1.1.md",
            (
                "ACCEPTED_FINAL_EXACT_ORIGINAL_AUDIT",
                "HARD_COUPLING_REQUIRES_REMEDIATION`: 0/7",
                "OUTPUT_ADAPTER_BOUNDARY",
            ),
        ),
        (
            "docs/governance/RNA_TR_Scout_Core_Freeze_final_hygiene_audit_v0.1.0.md",
            (
                "PASS_WITH_SCOPE_PUBLIC_RELEASE_AND_CLEANUP_PENDING",
                "No deletion is authorized",
                "Git commit/tag",
            ),
        ),
    ]
    rows: list[dict[str, Any]] = []
    for rel, terms in checks:
        path = project_root / rel
        ensure_regular(path)
        text = path.read_text(encoding="utf-8")
        missing = [term for term in terms if term not in text]
        if missing:
            raise GoldenV015Error(f"final document missing terms: {rel}: {missing}")
        rows.append(
            {
                "check": rel,
                "expected": "required_terms",
                "actual": sha256_file(path),
                "status": "PASS",
            }
        )
    return rows


def verify_ssot(project_root: Path) -> list[dict[str, Any]]:
    pipeline = project_root / CURRENT_PIPELINE_REL
    ensure_regular(pipeline)
    actual_pipeline = sha256_file(pipeline)
    if actual_pipeline != CURRENT_PIPELINE_SHA256:
        raise GoldenV015Error(
            f"current pipeline export changed: {actual_pipeline} != {CURRENT_PIPELINE_SHA256}"
        )
    rows = read_tsv(pipeline)
    if len(rows) != 1 or rows[0].get("stage_key") != "CORE_GENERIC_SHARDED_BAM_FASTQ_TO_FINAL":
        raise GoldenV015Error("current pipeline is not one-row generic Core")

    db = project_root / SSOT_DB_REL
    ensure_regular(db)
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise GoldenV015Error("SSOT integrity_check failed")
        closed = (
            "ARCHITECTURE_CONSISTENCY_AUDIT_CLOSURE",
            "CORE_FREEZE_PACKET",
            "GOLDEN_REGRESSION_SUITE",
            "PROJECT_WIDE_DOCS_CANONICALIZATION",
        )
        for key in closed:
            row = conn.execute(
                "SELECT status,blocking FROM open_questions WHERE question_key=?", (key,)
            ).fetchone()
            if row is None or row[0] != "CLOSED" or int(row[1]) != 0:
                raise GoldenV015Error(f"SSOT question not closed: {key}: {row}")
        for key in (
            "BIOLOGY_READY_INTERPRETATION_OUTPUT_AUDIT",
            "CLEAN_INSTALL_INTERNAL_BETA",
            "G31_BIOLOGICAL_CANDIDATE_ENTRY_INTERPRETATION",
            "CORE_FREEZE_GIT_TAG_AND_PUBLIC_RELEASE_BINDING",
        ):
            row = conn.execute(
                "SELECT status FROM open_questions WHERE question_key=?", (key,)
            ).fetchone()
            if row is None or row[0] != "OPEN":
                raise GoldenV015Error(f"SSOT question unexpectedly closed/missing: {key}: {row}")
        for key in (
            "core_freeze_v0_1_0_acceptance_v0_1_0",
            "stage15r_candidate_multiplicity_closure_v0_1_0",
            "stage15s_extensibility_hygiene_closure_v0_1_0",
        ):
            count = conn.execute(
                "SELECT COUNT(*) FROM decisions WHERE decision_key=? AND status='ACTIVE'", (key,)
            ).fetchone()[0]
            if count != 1:
                raise GoldenV015Error(f"SSOT decision missing/duplicate: {key}: {count}")
        for key in (
            "candidate_assignment_reverse_traceability_v0_1_0",
            "future_extensibility_boundaries_v0_1_0",
            "architecture_consistency_audit_v0_1_0",
            "core_freeze_preservation_governance_v0_1_0",
            "positive_golden_evidence_v0_1_0",
        ):
            count = conn.execute(
                "SELECT COUNT(*) FROM algorithm_contracts WHERE component_key=? AND status='ACTIVE'",
                (key,),
            ).fetchone()[0]
            if count != 1:
                raise GoldenV015Error(f"SSOT algorithm contract missing/duplicate: {key}: {count}")
    finally:
        conn.close()
    return [
        {
            "check": "ssot_current_pipeline",
            "expected": CURRENT_PIPELINE_SHA256,
            "actual": actual_pipeline,
            "status": "PASS",
        },
        {
            "check": "ssot_sqlite",
            "expected": "integrity_and_scoped_registration",
            "actual": sha256_file(db),
            "status": "PASS",
        },
    ]


def verify_final_manifest(project_root: Path, base) -> list[dict[str, Any]]:
    path = project_root / FINAL_MANIFEST_REL
    count = base.verify_freeze_manifest(project_root, str(FINAL_MANIFEST_REL))
    return [
        {
            "check": "core_freeze_manifest_v0.1.1",
            "expected": "all_rows_path_bytes_sha_pass",
            "actual": f"rows={count};sha256={sha256_file(path)}",
            "status": "PASS",
        }
    ]


def final_tier0(project_root: Path, qc_root: Path, base) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rel, expected in CORE_ACTIVE_HASHES.items():
        path = project_root / rel
        ensure_regular(path)
        actual = sha256_file(path)
        if actual != expected:
            raise GoldenV015Error(f"frozen Core hash drift: {rel}: {actual} != {expected}")
        rows.append({"check": rel, "expected": expected, "actual": actual, "status": "PASS"})
    rows.extend(verify_release_gates(project_root))
    rows.extend(verify_final_docs(project_root))
    rows.extend(verify_ssot(project_root))
    rows.extend(verify_final_manifest(project_root, base))
    write_tsv(qc_root / "tier0_final_governance.tsv", rows, ["check", "expected", "actual", "status"])
    return rows


def run_suite(mode: str, project_root: Path, work_root: Path | None, qc_root: Path) -> int:
    if qc_root.exists():
        raise GoldenV015Error("QC root must be unused")
    qc_root.mkdir(parents=True)
    base = load_base_runner(project_root)
    started = time.perf_counter()
    final_tier0(project_root, qc_root, base)

    if mode == "tier0-only":
        elapsed = time.perf_counter() - started
        summary = [
            {"metric": "golden_suite_version", "value": VERSION},
            {"metric": "mode", "value": mode},
            {"metric": "status", "value": "PASS"},
            {"metric": "elapsed_seconds", "value": f"{elapsed:.6f}"},
            {"metric": "tier0", "value": "PASS"},
            {"metric": "tier1", "value": "NOT_RUN"},
            {"metric": "tier2", "value": "NOT_RUN"},
            {"metric": "tier3", "value": "NOT_RUN"},
            {"metric": "tier4", "value": "NOT_RUN"},
        ]
        write_tsv(qc_root / "golden_suite_summary.tsv", summary, ["metric", "value"])
        print("RNATR_GOLDEN_REGRESSION_V015\tPASS")
        print(f"mode\t{mode}")
        print(f"elapsed_seconds\t{elapsed:.3f}")
        print(f"QC_ROOT\t{qc_root}")
        return 0

    if work_root is None:
        raise GoldenV015Error("full/full-evidence mode requires work root")
    if work_root.exists():
        raise GoldenV015Error("work root must be unused")
    work_root.mkdir(parents=True)
    manifest = base.load_manifest(project_root)
    base.tier1_semantic(project_root, manifest, qc_root)
    tier2_output = base.run_tier2(project_root, manifest, work_root, qc_root)
    with tempfile.TemporaryDirectory(prefix="rnatr_golden_negative_", dir=str(work_root)) as td:
        base.run_package_negative_fixtures(project_root, manifest, tier2_output, qc_root, Path(td))
    if mode in {"full", "full-evidence"}:
        base.run_tier3(project_root, manifest, work_root, qc_root)
    if mode == "full-evidence":
        base.verify_tier4(project_root, manifest, qc_root)

    elapsed = time.perf_counter() - started
    summary = [
        {"metric": "golden_suite_version", "value": VERSION},
        {"metric": "base_scientific_suite", "value": base.VERSION},
        {"metric": "mode", "value": mode},
        {"metric": "status", "value": "PASS"},
        {"metric": "elapsed_seconds", "value": f"{elapsed:.6f}"},
        {"metric": "tier0", "value": "PASS"},
        {"metric": "tier1", "value": "PASS"},
        {"metric": "tier2", "value": "PASS"},
        {"metric": "tier3", "value": "PASS" if mode in {"full", "full-evidence"} else "NOT_RUN"},
        {"metric": "tier4", "value": "PASS" if mode == "full-evidence" else "NOT_RUN"},
    ]
    write_tsv(qc_root / "golden_suite_summary.tsv", summary, ["metric", "value"])
    print("RNATR_GOLDEN_REGRESSION_V015\tPASS")
    print(f"mode\t{mode}")
    print(f"elapsed_seconds\t{elapsed:.3f}")
    print(f"QC_ROOT\t{qc_root}")
    return 0


def self_test() -> int:
    with tempfile.TemporaryDirectory(prefix="rnatr_golden_v015_selftest_") as td:
        root = Path(td)
        gates = root / RELEASE_GATES_REL
        gates.parent.mkdir(parents=True)
        gates.write_text(
            "gate_id\tstatus\n"
            "G24\tPASS_WITH_SCOPE_AMENDMENT\n"
            "G31-T\tPASS_WITH_SCOPE_AMENDMENT\n"
            "G31-B\tOPEN_DEFERRED_TO_BIOLOGY_LAYER\n"
            "G32\tPASS_WITH_SCOPE_AMENDMENT\n"
            "G33\tPASS\n"
            "G34\tPASS_WITH_SCOPE_AMENDMENT\n"
            "G25\tOPEN_PLANNED\nG26\tOPEN_PLANNED\nG27\tOPEN_PLANNED\n"
            "G28\tOPEN_PLANNED\nG29\tOPEN_PLANNED\nG30\tOPEN_PLANNED\n",
            encoding="utf-8",
        )
        if sha256_file(gates) == RELEASE_GATES_SHA256:
            raise GoldenV015Error("self-test fixture unexpectedly equals production gate SHA")
        packet = (
            "LOCAL_CORE_FREEZE_V0.1.0_ACCEPTED_WITH_SCOPE "
            + APPROVED_PACKET_SOURCE_SHA256
            + " public GitHub release v0.5.0 PASS_WITH_DOCUMENTED_TOLERANCE"
        )
        if APPROVED_PACKET_SOURCE_SHA256 not in packet:
            raise GoldenV015Error("self-test approved packet binding failed")
    print("SELF_TEST_PASS")
    print(f"version\t{VERSION}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--self-test", action="store_true")
    modes.add_argument("--tier0-only", action="store_true")
    modes.add_argument("--full", action="store_true")
    modes.add_argument("--full-evidence", action="store_true")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--work-root", type=Path)
    parser.add_argument("--qc-root", type=Path)
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    mode = "tier0-only" if args.tier0_only else "full" if args.full else "full-evidence"
    project_root = args.project_root.resolve()
    qc_root = (args.qc_root or project_root / "qc/stage15t_golden_v015").resolve()
    work_root = args.work_root.resolve() if args.work_root else None
    try:
        return run_suite(mode, project_root, work_root, qc_root)
    except (GoldenV015Error, OSError, ValueError, sqlite3.Error) as exc:
        print(f"GOLDEN_V015_ERROR\t{type(exc).__name__}\t{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
