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

VERSION = "rnatr_stage16y_finalize_release_wording_v0.1.0"
DEFAULT_REPO_ROOT = Path("/mnt/intelssd/rnatr_git_stage/LOCAL_CORE_FREEZE_V0.1.0_git_snapshot_v0.1.2")
DEFAULT_PROJECT_ROOT = Path("/mnt/intelssd/rnatr_project")
FREEZE_ROOT = "4b1981db955a8aa92a2a01e19bbb1cfc2aa0ebfb"
EXPECTED_DB_PRE_SHA = "49faa02325b024a2487a52331ccc5d5ee7e30512af564fe57c490c288fdbeea5"
LIMITATION_KEY = "PUBLIC_V050_RELEASE_NOT_YET_COMPLETE"
NEW_MITIGATION = (
    "Public catalog hosting and same-machine full-network fresh-install validation are complete. "
    "Remaining release work is to close the independent clean-machine/internal-beta gate as required, "
    "complete any storage benchmarking needed for fixed recommendations, run the final Pro cross-cut audit, "
    "and create the immutable public v0.5.0 release/tag/citation binding."
)
EVIDENCE = (
    "/mnt/intelssd/rnatr_project/metadata/ssot/checkpoints/"
    "stage16y_stage16wx_registration_v0.1.0/"
    "sha256_75f9cc560c22adb236902324d2d4771f7a1a6fee439cedf747a9cfb163fffd09/"
    "stage16y_stage16wx_registration.result.json"
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
    p = subprocess.run(cmd, cwd=str(cwd), text=True, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, check=False)
    if p.returncode != 0:
        raise FinalizeError(f"command failed ({p.returncode}): {' '.join(cmd)}\n{p.stdout}")
    return p.stdout.strip()


def load_ssot(path: Path):
    spec = importlib.util.spec_from_file_location("rnatr_ssot_stage16y_finalize", path)
    if spec is None or spec.loader is None:
        raise FinalizeError(f"cannot import SSOT module: {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser(description="Synchronize current public-v0.5.0 limitation wording after Stage16W/X closure without closing any additional release gate.")
    ap.add_argument("--repo-root", type=Path, default=DEFAULT_REPO_ROOT)
    ap.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    repo_root = args.repo_root.resolve()
    project_root = args.project_root.resolve()
    if run(["git", "status", "--porcelain"], repo_root):
        raise FinalizeError("Git working tree must be clean")
    head = run(["git", "rev-parse", "HEAD"], repo_root).splitlines()[-1]
    p = subprocess.run(["git", "merge-base", "--is-ancestor", FREEZE_ROOT, head], cwd=str(repo_root))
    if p.returncode != 0:
        raise FinalizeError("Freeze root is not an ancestor of repo HEAD")

    ssot_root = project_root / "metadata/ssot"
    db = ssot_root / "rnatr_ssot.sqlite"
    ssot_py = ssot_root / "rnatr_ssot.py"
    if not db.is_file() or not ssot_py.is_file():
        raise FinalizeError("canonical SSOT database/implementation missing")
    observed_pre = sha256_file(db)
    if observed_pre != EXPECTED_DB_PRE_SHA:
        raise FinalizeError(f"unexpected SSOT pre-SHA: {observed_pre} != {EXPECTED_DB_PRE_SHA}")

    with sqlite3.connect(str(db)) as pre:
        if pre.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or list(pre.execute("PRAGMA foreign_key_check")):
            raise FinalizeError("canonical SSOT failed integrity/foreign-key preflight")
        row = pre.execute(
            "SELECT status,statement,mitigation FROM limitations WHERE limitation_key=?",
            (LIMITATION_KEY,),
        ).fetchone()
        if not row or row[0] != "ACTIVE":
            raise FinalizeError(f"expected active limitation missing: {row}")
        if "full-network fresh-install" not in row[2]:
            raise FinalizeError("current mitigation does not contain the stale Stage16 pre-closure wording expected by this finalizer")

    print("===== RNA-TR-SCOUT STAGE16Y RELEASE-WORDING FINALIZER PREFLIGHT =====")
    print(f"version\t{VERSION}")
    print(f"repo_head\t{head}")
    print(f"ssot_pre_sha256\t{observed_pre}")
    print(f"limitation_key\t{LIMITATION_KEY}")
    print("additional_release_gates_closed\t0")
    if not args.execute:
        print("status\tPREFLIGHT_PASS_READY_FOR_EXECUTE")
        return 0

    effective_at = now_utc()
    checkpoint = ssot_root / "checkpoints/stage16y_release_wording_finalize_v0.1.0"
    checkpoint.mkdir(parents=True, exist_ok=True)
    backup = checkpoint / f"rnatr_ssot.pre_finalize.{effective_at.replace(':','').replace('+00:00','Z')}.sqlite"
    shutil.copy2(db, backup)
    if sha256_file(backup) != observed_pre:
        raise FinalizeError("backup SHA mismatch")

    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute(
            "UPDATE limitations SET mitigation=?,evidence_path=?,effective_at=? WHERE limitation_key=? AND status='ACTIVE'",
            (NEW_MITIGATION, EVIDENCE, effective_at, LIMITATION_KEY),
        )
        if cur.rowcount != 1:
            raise FinalizeError(f"expected one limitation update, observed {cur.rowcount}")
        conn.commit()

        ssot = load_ssot(ssot_py)
        checks = ssot.validate_db(conn, project_root)
        failed = [row for row in checks if row[1] == "FAIL"]
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
    result = {
        "version": VERSION,
        "status": "PASS_STAGE16Y_CURRENT_RELEASE_WORDING_SYNCHRONIZED",
        "effective_at": effective_at,
        "repo_head": head,
        "freeze_root": FREEZE_ROOT,
        "limitation_key": LIMITATION_KEY,
        "new_mitigation": NEW_MITIGATION,
        "additional_release_gates_closed": 0,
        "ssot_pre_sha256": observed_pre,
        "ssot_post_sha256": post_sha,
        "backup": str(backup),
        "summary": str(summary),
    }
    result_path = checkpoint / "stage16y_release_wording_finalize.result.json"
    tmp = result_path.with_suffix(".json.part")
    tmp.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, result_path)

    print("===== RNA-TR-SCOUT STAGE16Y RELEASE-WORDING FINALIZER RESULT =====")
    print("status\tPASS_STAGE16Y_CURRENT_RELEASE_WORDING_SYNCHRONIZED")
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
