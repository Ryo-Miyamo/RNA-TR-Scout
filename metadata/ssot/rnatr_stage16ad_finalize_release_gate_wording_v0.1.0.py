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
import subprocess
import sys

VERSION = "rnatr_stage16ad_finalize_release_gate_wording_v0.1.0"
DEFAULT_REPO_ROOT = Path("/mnt/intelssd/rnatr_git_stage/LOCAL_CORE_FREEZE_V0.1.0_git_snapshot_v0.1.2")
DEFAULT_PROJECT_ROOT = Path("/mnt/intelssd/rnatr_project")
FREEZE_ROOT = "4b1981db955a8aa92a2a01e19bbb1cfc2aa0ebfb"
QUESTION_KEY = "CORE_FREEZE_GIT_TAG_AND_PUBLIC_RELEASE_BINDING"
NEW_NEXT_ACTION = (
    "G25-G30 release-readiness work is now adjudicated. Complete remaining public-release "
    "packaging/lock/license/CITATION tasks, resolve any release-blocking findings from the "
    "final Pro cross-cut audit, then create and verify the immutable public v0.5.0 Git tag/release/citation binding."
)

class FinalizeError(RuntimeError):
    pass


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def run(cmd: list[str], cwd: Path) -> str:
    p = subprocess.run(cmd, cwd=str(cwd), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if p.returncode != 0:
        raise FinalizeError(f"command failed ({p.returncode}): {' '.join(cmd)}\n{p.stdout}")
    return p.stdout.strip()


def load_ssot(path: Path):
    spec = importlib.util.spec_from_file_location("rnatr_ssot_stage16ad", path)
    if spec is None or spec.loader is None:
        raise FinalizeError(f"cannot import SSOT module: {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser(description="Synchronize the remaining public-release binding gate wording after G25-G30 adjudication.")
    ap.add_argument("--repo-root", type=Path, default=DEFAULT_REPO_ROOT)
    ap.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    repo_root = args.repo_root.resolve()
    project_root = args.project_root.resolve()
    if run(["git", "status", "--porcelain"], repo_root):
        raise FinalizeError("Git working tree must be clean before Stage16AD")
    head = run(["git", "rev-parse", "HEAD"], repo_root).splitlines()[-1]
    if subprocess.run(["git", "merge-base", "--is-ancestor", FREEZE_ROOT, head], cwd=str(repo_root)).returncode != 0:
        raise FinalizeError("Freeze root is not an ancestor of repo HEAD")

    ssot_root = project_root / "metadata/ssot"
    db = ssot_root / "rnatr_ssot.sqlite"
    ssot_py = ssot_root / "rnatr_ssot.py"
    if not db.is_file() or not ssot_py.is_file():
        raise FinalizeError("canonical SSOT database/implementation missing")

    with sqlite3.connect(str(db)) as conn:
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or list(conn.execute("PRAGMA foreign_key_check")):
            raise FinalizeError("canonical SSOT failed integrity/foreign-key checks")
        row = conn.execute(
            "SELECT status,next_action FROM open_questions WHERE question_key=?",
            (QUESTION_KEY,),
        ).fetchone()
        if not row:
            raise FinalizeError(f"required open question missing: {QUESTION_KEY}")
        if row[0] != "OPEN":
            raise FinalizeError(f"expected {QUESTION_KEY} to remain OPEN, observed {row[0]}")
        old_next_action = row[1]

    print("===== RNA-TR-SCOUT STAGE16AD RELEASE-GATE WORDING PREFLIGHT =====")
    print(f"version\t{VERSION}")
    print(f"repo_head\t{head}")
    print(f"freeze_root\t{FREEZE_ROOT}")
    print(f"question_key\t{QUESTION_KEY}")
    print(f"old_next_action\t{old_next_action}")
    print(f"new_next_action\t{NEW_NEXT_ACTION}")
    print("gate_status_after\tOPEN")
    if not args.execute:
        print("status\tPREFLIGHT_PASS_READY_FOR_EXECUTE")
        return 0

    effective_at = now_utc()
    checkpoint = ssot_root / "checkpoints/stage16ad_release_gate_wording_v0.1.0"
    checkpoint.mkdir(parents=True, exist_ok=True)
    pre_sha = sha256_file(db)
    backup = checkpoint / f"rnatr_ssot.pre_stage16ad.{effective_at.replace(':','').replace('+00:00','Z')}.sqlite"
    shutil.copy2(db, backup)
    if sha256_file(backup) != pre_sha:
        raise FinalizeError("SSOT backup SHA mismatch")

    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "UPDATE open_questions SET next_action=?,effective_at=? WHERE question_key=? AND status='OPEN'",
            (NEW_NEXT_ACTION, effective_at, QUESTION_KEY),
        )
        conn.commit()

        ssot = load_ssot(ssot_py)
        checks = ssot.validate_db(conn, project_root)
        failed = [x for x in checks if x[1] == "FAIL"]
        if failed:
            raise FinalizeError(f"post-update SSOT validation failed: {failed}")
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
    result = {
        "version": VERSION,
        "status": "PASS_STAGE16AD_RELEASE_GATE_WORDING_SYNCHRONIZED",
        "effective_at": effective_at,
        "repo_head": head,
        "freeze_root": FREEZE_ROOT,
        "question_key": QUESTION_KEY,
        "gate_status": "OPEN",
        "old_next_action": old_next_action,
        "new_next_action": NEW_NEXT_ACTION,
        "additional_release_gates_closed": 0,
        "ssot_pre_sha256": pre_sha,
        "ssot_post_sha256": post_sha,
        "backup": str(backup),
        "summary": str(summary),
    }
    result_path = checkpoint / "stage16ad_release_gate_wording.result.json"
    tmp = result_path.with_suffix(".json.part")
    tmp.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, result_path)

    print("===== RNA-TR-SCOUT STAGE16AD RESULT =====")
    print("status\tPASS_STAGE16AD_RELEASE_GATE_WORDING_SYNCHRONIZED")
    print("gate_status\tOPEN")
    print("additional_release_gates_closed\t0")
    print(f"ssot_post_sha256\t{post_sha}")
    print(f"result\t{result_path}")
    print("human_visual_review_required\tfalse")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
