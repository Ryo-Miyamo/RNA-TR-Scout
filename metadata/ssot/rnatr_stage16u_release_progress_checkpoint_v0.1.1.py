#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys

VERSION = "rnatr_stage16u_release_progress_checkpoint_v0.1.1"
DEFAULT_PROJECT_ROOT = Path("/mnt/intelssd/rnatr_project")
DEFAULT_REPO_ROOT = Path("/mnt/intelssd/rnatr_git_stage/LOCAL_CORE_FREEZE_V0.1.0_git_snapshot_v0.1.2")


class DriverError(RuntimeError):
    pass


def load_base(path: Path):
    spec = importlib.util.spec_from_file_location("rnatr_stage16u_checkpoint_v010", path)
    if spec is None or spec.loader is None:
        raise DriverError(f"cannot import Stage16U base updater: {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Stage16U SSOT progress checkpoint driver for installations where the "
            "Git checkout and the canonical project/SSOT database are separate."
        )
    )
    ap.add_argument("--repo-root", type=Path, default=DEFAULT_REPO_ROOT)
    ap.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    repo_root = args.repo_root.resolve()
    project_root = args.project_root.resolve()
    if not repo_root.is_dir():
        raise DriverError(f"Git repository root missing: {repo_root}")
    if not project_root.is_dir():
        raise DriverError(f"project root missing: {project_root}")

    base_path = Path(__file__).resolve().with_name(
        "rnatr_stage16u_release_progress_checkpoint_v0.1.0.py"
    )
    if not base_path.is_file():
        raise DriverError(f"required Stage16U v0.1.0 module missing beside driver: {base_path}")
    base = load_base(base_path)

    # Git provenance is checked against the dedicated source checkout.
    if base.git_status(repo_root):
        raise DriverError("Git working tree must be clean before Stage16U SSOT checkpoint")
    head = base.git_head(repo_root)
    if head != base.EXPECTED_MAIN:
        raise DriverError(
            f"expected Git checkout at current main {base.EXPECTED_MAIN}, observed {head}; "
            "fetch and fast-forward main before running"
        )
    if not base.git_is_ancestor(repo_root, base.FREEZE_ROOT, head):
        raise DriverError("immutable Core Freeze root is not an ancestor of current Git HEAD")

    # The canonical database and generated SSOT exports live in the historical
    # project root, not in the release Git checkout.
    ssot_root = project_root / "metadata/ssot"
    db = base.ensure_file(ssot_root / "rnatr_ssot.sqlite", "SSOT database")
    ssot_py = base.ensure_file(ssot_root / "rnatr_ssot.py", "canonical SSOT implementation")

    # Release-engineering evidence comes from the exact current Git checkout.
    evidence = {
        "stage16s": base.ensure_file(repo_root / "docs/release/STAGE16S_CROSS_HARDWARE_PARITY_v0.1.1.md", "Stage16S record"),
        "stage16t": base.ensure_file(repo_root / "docs/release/STAGE16T_USER_FACING_DOCUMENTATION_REVIEW_v0.1.0.md", "Stage16T record"),
        "readme": base.ensure_file(repo_root / "README.md", "README"),
        "public_workflow": base.ensure_file(repo_root / "src/rnatr_scout/public_workflow.py", "public workflow"),
        "mapping_contract": base.ensure_file(repo_root / "docs/release/MAPPING_CONTRACT_ONT_CDNA_v0.1.0.md", "mapping contract"),
        "resource_manifest": base.ensure_file(repo_root / "config/core_runtime/v0.1.0/resource_manifest.json", "Core resource manifest"),
        "resource_profile": base.ensure_file(repo_root / "config/resources/standard_v0.1.1/validated_profile.json", "standard resource profile"),
        "caller_adapter": base.ensure_file(repo_root / "scripts/rnatr_stage15a_native_v041_runid_adapter_v0.2.1.py", "production caller adapter"),
        "motif_builder": base.ensure_file(repo_root / "scripts/rnatr_stage15a_fast_motif_jobs_scaling_v0.2.2.2.py", "motif builder"),
    }

    pre_sha = base.sha256_file(db)
    with sqlite3.connect(str(db)) as pre:
        base.check_expected_schema(pre)
        integrity = pre.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise DriverError(f"pre-update sqlite integrity failed: {integrity}")
        fk = list(pre.execute("PRAGMA foreign_key_check"))
        if fk:
            raise DriverError(f"pre-update foreign-key check failed: {len(fk)} rows")

    print("===== RNA-TR-SCOUT STAGE16U SSOT PROGRESS CHECKPOINT PREFLIGHT =====")
    print(f"version\t{VERSION}")
    print(f"repo_root\t{repo_root}")
    print(f"project_root\t{project_root}")
    print(f"head\t{head}")
    print(f"freeze_root\t{base.FREEZE_ROOT}")
    print(f"ssot_db\t{db}")
    print(f"ssot_db_pre_sha256\t{pre_sha}")
    print("stage16q\tPASS_FROM_GIT_ANCESTRY")
    print("stage16r\tEVIDENCE_BINDING_PENDING")
    print("stage16s\tPASS_FORMAL_RECORD_PRESENT")
    print("stage16t\tPASS_OWNER_REVIEW_RECORD_PRESENT")

    if not args.execute:
        print("status\tPREFLIGHT_PASS_READY_FOR_EXECUTE")
        return 0

    effective_at = now_utc()
    checkpoint_root = (
        ssot_root / "checkpoints" / "stage16u_release_progress_v0.1.1" /
        effective_at.replace(":", "").replace("+00:00", "Z")
    )
    checkpoint_root.mkdir(parents=True, exist_ok=False)
    backup = checkpoint_root / "rnatr_ssot.pre_stage16u.sqlite"
    shutil.copy2(db, backup)
    backup_sha = base.sha256_file(backup)
    if backup_sha != pre_sha:
        raise DriverError("database backup SHA differs from pre-update database")

    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        conn.execute("BEGIN IMMEDIATE")
        base.check_expected_schema(conn)
        # base.apply_checkpoint only uses its root argument as release-run provenance.
        # Passing repo_root is intentional; validation/export below use project_root.
        state = base.apply_checkpoint(conn, repo_root, evidence, effective_at)
        conn.commit()

        ssot_mod = base.load_ssot_module(ssot_py)
        checks = ssot_mod.validate_db(conn, project_root)
        failed = [row for row in checks if row[1] == "FAIL"]
        if failed:
            raise DriverError(f"post-update SSOT validation failed: {failed}")
        exports = ssot_mod.export_views(conn, ssot_root)
        summary_path = ssot_mod.write_summary(conn, ssot_root, checks, exports)
    except Exception:
        try:
            conn.close()
        finally:
            shutil.copy2(backup, db)
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass

    post_sha = base.sha256_file(db)
    result = {
        "version": VERSION,
        "status": "PASS_WITH_STAGE16R_EVIDENCE_BINDING_PENDING",
        "effective_at": effective_at,
        "repo_root": str(repo_root),
        "project_root": str(project_root),
        "current_main": base.EXPECTED_MAIN,
        "freeze_root": base.FREEZE_ROOT,
        "ssot_db": str(db),
        "ssot_db_pre_sha256": pre_sha,
        "ssot_db_post_sha256": post_sha,
        "backup": str(backup),
        "backup_sha256": backup_sha,
        "summary": str(summary_path),
        "state": state,
        "evidence_sha256": {k: base.sha256_file(v) for k, v in evidence.items()},
        "driver_sha256": base.sha256_file(Path(__file__).resolve()),
        "base_updater_sha256": base.sha256_file(base_path),
    }
    result_path = checkpoint_root / "stage16u_ssot_progress_checkpoint.result.json"
    tmp = result_path.with_suffix(".json.part")
    tmp.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, result_path)

    print("===== RNA-TR-SCOUT STAGE16U SSOT PROGRESS CHECKPOINT RESULT =====")
    print("status\tPASS_WITH_STAGE16R_EVIDENCE_BINDING_PENDING")
    print(f"ssot_db_post_sha256\t{post_sha}")
    print(f"backup\t{backup}")
    print(f"result\t{result_path}")
    print(f"summary\t{summary_path}")
    print("next_required\tBIND_AUTHORITATIVE_STAGE16R_RESULT_BEFORE_PUBLIC_RC_PRO_AUDIT")
    print("review_project_ssot_diff\tcompare metadata/ssot/CURRENT_STATE.md and metadata/ssot/exports against the prior Git snapshot")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
