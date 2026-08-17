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

VERSION = "rnatr_stage16u_finalize_checkpoint_v0.1.0"
EXPECTED_RESULT_SHA256 = "7c4565c6ca751c6c20af7ac6a4566464cb80c65cef46e20291ce97478d66b1df"
DEFAULT_PROJECT_ROOT = Path("/mnt/intelssd/rnatr_project")
DEFAULT_RESULT = Path("/mnt/intelssd/rnatr_project/metadata/ssot/checkpoints/stage16u_release_progress_v0.1.1/2026-08-17T013902+0000/stage16u_ssot_progress_checkpoint.result.json")
RUN_ID = "RNA_TR_SCOUT_STAGE16_RELEASE_ENGINEERING"
STAGE_KEY = "16U_SSOT_PROGRESS_CHECKPOINT"
ATTEMPT_TAG = "v0.1.0"


class FinalizeError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_ssot(path: Path):
    spec = importlib.util.spec_from_file_location("rnatr_ssot_stage16u_finalize", path)
    if spec is None or spec.loader is None:
        raise FinalizeError(f"cannot import SSOT implementation: {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser(description="Bind Stage16U SSOT checkpoint to its durable result JSON and regenerate current SSOT exports.")
    ap.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    ap.add_argument("--result", type=Path, default=DEFAULT_RESULT)
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    project_root = args.project_root.resolve()
    result = args.result.resolve()
    if not result.is_file() or result.is_symlink():
        raise FinalizeError(f"durable Stage16U result missing/invalid: {result}")
    result_sha = sha256_file(result)
    if result_sha != EXPECTED_RESULT_SHA256:
        raise FinalizeError(f"Stage16U result SHA mismatch: {result_sha} != {EXPECTED_RESULT_SHA256}")

    result_obj = json.loads(result.read_text(encoding="utf-8"))
    if result_obj.get("status") != "PASS_WITH_STAGE16R_EVIDENCE_BINDING_PENDING":
        raise FinalizeError("unexpected Stage16U result status")

    ssot_root = project_root / "metadata/ssot"
    db = ssot_root / "rnatr_ssot.sqlite"
    ssot_py = ssot_root / "rnatr_ssot.py"
    if not db.is_file() or not ssot_py.is_file():
        raise FinalizeError("canonical SSOT database/implementation missing")

    with sqlite3.connect(str(db)) as conn:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk = list(conn.execute("PRAGMA foreign_key_check"))
        row = conn.execute(
            "SELECT status,qc_path,qc_status,notes FROM run_stages WHERE run_id=? AND stage_key=? AND attempt_tag=?",
            (RUN_ID, STAGE_KEY, ATTEMPT_TAG),
        ).fetchone()
    if integrity != "ok" or fk:
        raise FinalizeError(f"pre-finalize SSOT validation failed: integrity={integrity} fk={len(fk)}")
    if row is None or row[0] != "PASS":
        raise FinalizeError(f"expected existing Stage16U PASS row, observed: {row}")

    print("===== RNA-TR-SCOUT STAGE16U DURABLE-EVIDENCE FINALIZER PREFLIGHT =====")
    print(f"version\t{VERSION}")
    print(f"project_root\t{project_root}")
    print(f"result\t{result}")
    print(f"result_sha256\t{result_sha}")
    print(f"current_qc_path\t{row[1] or ''}")
    print(f"target_qc_path\t{result}")
    if not args.execute:
        print("status\tPREFLIGHT_PASS_READY_FOR_EXECUTE")
        return 0

    effective_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    backup_dir = ssot_root / "checkpoints" / "stage16u_release_progress_v0.1.1" / "finalize_durable_evidence"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f"rnatr_ssot.pre_finalize.{effective_at.replace(':','').replace('+00:00','Z')}.sqlite"
    shutil.copy2(db, backup)
    pre_sha = sha256_file(db)
    if sha256_file(backup) != pre_sha:
        raise FinalizeError("SSOT backup SHA mismatch")

    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            UPDATE run_stages
            SET qc_path=?, qc_status='PASS', notes=?
            WHERE run_id=? AND stage_key=? AND attempt_tag=? AND status='PASS'
            """,
            (
                str(result),
                "Stage16U SSOT progress checkpoint PASS; durable evidence is the exact result JSON bound by SHA-256. Stage16R remains evidence-binding pending.",
                RUN_ID, STAGE_KEY, ATTEMPT_TAG,
            ),
        )
        if conn.total_changes != 1:
            raise FinalizeError(f"expected one Stage16U row update, total_changes={conn.total_changes}")
        conn.commit()

        ssot = load_ssot(ssot_py)
        checks = ssot.validate_db(conn, project_root)
        failed = [x for x in checks if x[1] == "FAIL"]
        if failed:
            raise FinalizeError(f"post-finalize SSOT validation failed: {failed}")
        exports = ssot.export_views(conn, ssot_root)
        summary = ssot.write_summary(conn, ssot_root, checks, exports)
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

    post_sha = sha256_file(db)
    final_record = {
        "version": VERSION,
        "status": "PASS",
        "effective_at": effective_at,
        "project_root": str(project_root),
        "durable_result": str(result),
        "durable_result_sha256": result_sha,
        "ssot_db_pre_sha256": pre_sha,
        "ssot_db_post_sha256": post_sha,
        "backup": str(backup),
        "summary": str(summary),
    }
    out = backup_dir / "stage16u_durable_evidence_finalize.result.json"
    tmp = out.with_suffix(".json.part")
    tmp.write_text(json.dumps(final_record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, out)

    print("===== RNA-TR-SCOUT STAGE16U DURABLE-EVIDENCE FINALIZER RESULT =====")
    print("status\tPASS")
    print(f"ssot_db_post_sha256\t{post_sha}")
    print(f"durable_result\t{result}")
    print(f"finalize_result\t{out}")
    print(f"summary\t{summary}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
