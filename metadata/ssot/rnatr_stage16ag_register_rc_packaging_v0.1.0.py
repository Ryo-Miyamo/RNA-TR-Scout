#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

VERSION = "rnatr_stage16ag_register_rc_packaging_v0.1.0"
FREEZE_ROOT = "4b1981db955a8aa92a2a01e19bbb1cfc2aa0ebfb"
RC_PREFLIGHT_SHA = "395f8f8abb5e327105370accdc2176635d27a64942625ad3e3b06a2e6214d233"
RC_CANDIDATE_HEAD = "c7c0d985068c4d01f7669521e6fefd146fbb1718"
RC_CANDIDATE_TREE = "568974b45cf06fd76a03e70e57a643184ecac528"
RUN_ID = "RNA_TR_SCOUT_STAGE16_RELEASE_ENGINEERING"
DEFAULT_REPO_ROOT = Path("/mnt/intelssd/rnatr_git_stage/LOCAL_CORE_FREEZE_V0.1.0_git_snapshot_v0.1.2")
DEFAULT_PROJECT_ROOT = Path("/mnt/intelssd/rnatr_project")
DEFAULT_EVIDENCE = Path.home() / "Downloads/rnatr_stage16af_rc_preflight.result.json"

class RegisterError(RuntimeError):
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
        raise RegisterError(f"command failed ({p.returncode}): {' '.join(cmd)}\n{p.stdout}")
    return p.stdout.strip()

def git_head(root: Path) -> str:
    return run(["git", "rev-parse", "HEAD"], root).splitlines()[-1]

def git_status(root: Path) -> str:
    return run(["git", "status", "--porcelain"], root)

def git_is_ancestor(root: Path, older: str, newer: str) -> bool:
    p = subprocess.run(["git", "merge-base", "--is-ancestor", older, newer],
                       cwd=str(root), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return p.returncode == 0

def ensure_regular(path: Path, label: str) -> Path:
    if not path.is_file() or path.is_symlink():
        raise RegisterError(f"{label} missing/invalid regular file: {path}")
    return path

def load_ssot(path: Path):
    spec = importlib.util.spec_from_file_location("rnatr_ssot_stage16ag", path)
    if spec is None or spec.loader is None:
        raise RegisterError(f"cannot import SSOT module: {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod

def source_document(conn: sqlite3.Connection, path: Path, source_type: str, effective_at: str) -> None:
    stat = path.stat()
    mtime = dt.datetime.fromtimestamp(stat.st_mtime, tz=dt.timezone.utc).replace(microsecond=0).isoformat()
    conn.execute(
        """INSERT INTO source_documents(source_type,path,sha256,bytes,mtime_utc,content_status,ingested_at)
           VALUES(?,?,?,?,?,?,?)
           ON CONFLICT(path) DO UPDATE SET source_type=excluded.source_type,sha256=excluded.sha256,
             bytes=excluded.bytes,mtime_utc=excluded.mtime_utc,content_status=excluded.content_status,
             ingested_at=excluded.ingested_at""",
        (source_type, str(path), sha256_file(path), stat.st_size, mtime, "PRESENT", effective_at),
    )

def ensure_stage(conn: sqlite3.Connection, key: str, order: float, name: str,
                 purpose: str, implementation_status: str, notes: str) -> None:
    conn.execute(
        """INSERT INTO stage_definitions(stage_key,stage_order,name,purpose,category,implementation_status,notes)
           VALUES(?,?,?,?,?,?,?)
           ON CONFLICT(stage_key) DO UPDATE SET stage_order=excluded.stage_order,name=excluded.name,
             purpose=excluded.purpose,category=excluded.category,
             implementation_status=excluded.implementation_status,notes=excluded.notes""",
        (key, order, name, purpose, "release_engineering", implementation_status, notes),
    )

def add_run_stage(conn: sqlite3.Connection, key: str, attempt: str, evidence: str,
                  notes: str, effective_at: str) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO run_stages(run_id,stage_key,implementation_id,attempt_tag,status,
           command_text,qc_path,qc_status,started_at,ended_at,notes)
           VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (RUN_ID, key, None, attempt, "PASS", None, evidence, "PASS", None, effective_at, notes),
    )

def superseding_decision(conn: sqlite3.Connection, key: str, category: str, title: str,
                         statement: str, rationale: str, evidence: str, effective_at: str) -> None:
    old = conn.execute("SELECT decision_id FROM decisions WHERE decision_key=? AND status='ACTIVE'", (key,)).fetchone()
    old_id = old[0] if old else None
    if old_id:
        conn.execute("UPDATE decisions SET status='SUPERSEDED' WHERE decision_id=?", (old_id,))
    new_id = "decision_" + hashlib.sha256((VERSION + "|" + key).encode()).hexdigest()[:20]
    conn.execute(
        """INSERT OR REPLACE INTO decisions(decision_id,decision_key,category,title,statement,status,
           confidence,effective_at,supersedes_decision_id,rationale,evidence_path)
           VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (new_id, key, category, title, statement, "ACTIVE", "HIGH", effective_at,
         old_id, rationale, evidence),
    )

def add_metric(conn: sqlite3.Connection, stage_key: str, name: str, value: str,
               evidence: str, effective_at: str) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO metrics(run_id,stage_key,metric_name,value_text,value_num,unit,
           denominator_num,source_path,metric_status,recorded_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (RUN_ID, stage_key, name, value, None, None, None, evidence, "CURRENT", effective_at),
    )

def main() -> int:
    ap = argparse.ArgumentParser(description="Register Stage16AE/AF public-release packaging and RC-preflight evidence into the canonical RNA-TR-Scout SSOT.")
    ap.add_argument("--repo-root", type=Path, default=DEFAULT_REPO_ROOT)
    ap.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    ap.add_argument("--evidence-json", type=Path, default=DEFAULT_EVIDENCE)
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    repo_root = args.repo_root.resolve()
    project_root = args.project_root.resolve()
    evidence = args.evidence_json.expanduser().resolve()
    ensure_regular(evidence, "Stage16AF RC preflight evidence")
    if sha256_file(evidence) != RC_PREFLIGHT_SHA:
        raise RegisterError("Stage16AF evidence SHA mismatch")
    obj = json.loads(evidence.read_text(encoding="utf-8"))

    expected = {
        "status": "PASS_STAGE16AF_RELEASE_CANDIDATE_PREFLIGHT",
        "candidate_head": RC_CANDIDATE_HEAD,
        "candidate_tree": RC_CANDIDATE_TREE,
        "candidate_package_version": "0.5.0rc1",
        "candidate_human_version": "v0.5.0-rc1",
        "freeze_root": FREEZE_ROOT,
        "freeze_ancestry": "PASS",
        "main_ancestry": "PASS",
        "software_license": "BSD-3-Clause",
        "copyright_holder": "Ryosuke Miyamoto",
        "copyright_year": 2026,
        "archived_source_python_compile": "PASS",
        "archived_source_unit_tests": "PASS",
        "resource_planner_unit_tests": "PASS",
        "setup_help_smoke": "PASS",
        "working_tree_clean_after_preflight": True,
        "public_release_created": False,
        "final_pro_crosscut_audit": "PENDING",
    }
    for k, v in expected.items():
        if obj.get(k) != v:
            raise RegisterError(f"Stage16AF evidence mismatch: {k}={obj.get(k)!r} != {v!r}")
    if obj.get("explicit_lock_sha256") != "79004c8253021a6d30b35aecf91a244a1ae1460ccfcd8d77a135716b6235955c":
        raise RegisterError("explicit lock SHA mismatch in evidence")
    if obj.get("license_sha256") != "29c5826ebe617783ca4fbde13b591bf451754db1c23adb2a5f2ac6ba133e31bb":
        raise RegisterError("license SHA mismatch in evidence")

    if git_status(repo_root):
        raise RegisterError("Git working tree must be clean before Stage16AG")
    head = git_head(repo_root)
    if not git_is_ancestor(repo_root, RC_CANDIDATE_HEAD, head):
        raise RegisterError("current release branch no longer descends from the audited RC candidate")
    if not git_is_ancestor(repo_root, FREEZE_ROOT, head):
        raise RegisterError("Freeze root is not an ancestor of current release branch")

    ssot_root = project_root / "metadata/ssot"
    db = ensure_regular(ssot_root / "rnatr_ssot.sqlite", "canonical SSOT database")
    ssot_py = ensure_regular(ssot_root / "rnatr_ssot.py", "canonical SSOT implementation")
    with sqlite3.connect(str(db)) as conn:
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or list(conn.execute("PRAGMA foreign_key_check")):
            raise RegisterError("canonical SSOT failed preflight integrity/foreign-key check")
        q = conn.execute("SELECT status FROM open_questions WHERE question_key='PUBLIC_RC_PRO_CROSSCUT_AUDIT'").fetchone()
        if not q or q[0] != "OPEN":
            raise RegisterError(f"unexpected PUBLIC_RC_PRO_CROSSCUT_AUDIT state: {q}")

    print("===== RNA-TR-SCOUT STAGE16AG PREFLIGHT =====")
    print(f"version\t{VERSION}")
    print(f"repo_head\t{head}")
    print(f"rc_candidate_head\t{RC_CANDIDATE_HEAD}")
    print(f"evidence_sha256\t{RC_PREFLIGHT_SHA}")
    print("stage16ae\tREADY_FOR_REGISTRATION")
    print("stage16af\tREADY_FOR_REGISTRATION")
    print("public_rc_pro_crosscut_audit\tREMAINS_OPEN_BLOCKING")
    if not args.execute:
        print("status\tPREFLIGHT_PASS_READY_FOR_EXECUTE")
        return 0

    effective_at = now_utc()
    durable_root = ssot_root / "checkpoints/stage16ag_rc_packaging_v0.1.0" / f"sha256_{RC_PREFLIGHT_SHA}"
    originals = durable_root / "originals"
    backups = durable_root / "backups"
    originals.mkdir(parents=True, exist_ok=True)
    backups.mkdir(parents=True, exist_ok=True)
    durable_evidence = originals / evidence.name
    if durable_evidence.exists():
        if sha256_file(durable_evidence) != RC_PREFLIGHT_SHA:
            raise RegisterError("existing durable Stage16AF evidence differs")
    else:
        shutil.copy2(evidence, durable_evidence)
    if sha256_file(durable_evidence) != RC_PREFLIGHT_SHA:
        raise RegisterError("durable Stage16AF evidence SHA mismatch")

    docs = {
        "stage16ae_packaging_record": repo_root / "docs/release/STAGE16AE_PUBLIC_RELEASE_PACKAGING_v0.1.0.md",
        "stage16ae_release_notes": repo_root / "docs/release/RELEASE_NOTES_v0.5.0-rc1.md",
        "software_license": repo_root / "LICENSE",
        "citation_metadata": repo_root / "CITATION.cff",
        "third_party_notices": repo_root / "THIRD_PARTY_NOTICES.md",
        "explicit_linux64_lock": repo_root / "environment-linux-64.lock.txt",
        "license_owner_decision": repo_root / "docs/release/LICENSE_OWNER_DECISION_v0.1.0.md",
    }
    for p in docs.values():
        ensure_regular(p, "release packaging document")

    pre_sha = sha256_file(db)
    backup = backups / f"rnatr_ssot.pre_stage16ag.{effective_at.replace(':','').replace('+00:00','Z')}.sqlite"
    shutil.copy2(db, backup)
    if sha256_file(backup) != pre_sha:
        raise RegisterError("SSOT backup SHA mismatch")

    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        conn.execute("BEGIN IMMEDIATE")
        source_document(conn, durable_evidence, "stage16af_rc_preflight_result", effective_at)
        for typ, p in docs.items():
            source_document(conn, p, typ, effective_at)

        ensure_stage(conn, "16AE_PUBLIC_RELEASE_PACKAGING", 177.0,
                     "Stage16AE public release packaging",
                     "Prepare coherent v0.5.0-rc1 packaging metadata, license/citation boundary and explicit Linux x86-64 environment lock without changing frozen scientific semantics.",
                     "VALIDATED_WITH_SCOPE",
                     "Mechanical release packaging complete for the RC candidate; public v0.5.0 tag/release remains intentionally uncreated pending final Pro audit.")
        ensure_stage(conn, "16AF_RELEASE_CANDIDATE_PREFLIGHT", 178.0,
                     "Stage16AF release candidate preflight",
                     "Validate the archived RC source snapshot, version/license/citation consistency, explicit lock, third-party notice boundary, unit tests, setup smoke and Git hygiene immediately before the final Pro audit.",
                     "VALIDATED",
                     "PASS for candidate c7c0d985068c4d01f7669521e6fefd146fbb1718; final Pro cross-cut audit remains OPEN and blocking.")

        add_run_stage(conn, "16AE_PUBLIC_RELEASE_PACKAGING", "v0.1.0", str(docs["stage16ae_packaging_record"]),
                      "v0.5.0-rc1 packaging complete: BSD-3-Clause software license, CITATION.cff, explicit Linux-64 lock, release notes and separate third-party notices are present; public release not yet created.", effective_at)
        add_run_stage(conn, "16AF_RELEASE_CANDIDATE_PREFLIGHT", "v0.1.1", str(durable_evidence),
                      "Git-archive RC preflight PASS: compile, all unit tests, resource-planner tests, CLI version, setup help, license/citation consistency, lock hygiene, ancestry and clean-tree checks all passed.", effective_at)

        superseding_decision(conn, "software_license_bsd3_v0_1_0", "release_packaging",
                             "Select BSD-3-Clause for RNA-TR-Scout software",
                             "The RNA-TR-Scout software source is licensed under BSD-3-Clause with Copyright (c) 2026, Ryosuke Miyamoto. Third-party catalog/data terms remain separately attributed and are not relicensed by the software LICENSE.",
                             "Owner selected BSD-3-Clause; root LICENSE, pyproject.toml, CITATION.cff and THIRD_PARTY_NOTICES.md are mutually consistent.", str(docs["software_license"]), effective_at)
        superseding_decision(conn, "stage16ae_public_release_packaging_acceptance_v0_1_0", "release_readiness",
                             "Accept Stage16AE mechanical public-release packaging",
                             "Accept v0.5.0-rc1 mechanical packaging as complete with BSD-3-Clause, citation metadata, explicit Linux x86-64 conda lock, release notes and third-party notice separation. This does not create or authorize the final public v0.5.0 release before the final Pro audit.",
                             "Stage16AE packaging files and Stage16AF preflight bind the candidate package identity and reproducibility metadata while preserving the Freeze root.", str(durable_evidence), effective_at)
        superseding_decision(conn, "stage16af_rc_preflight_acceptance_v0_1_0", "release_readiness",
                             "Accept Stage16AF release-candidate preflight",
                             "Accept candidate c7c0d985068c4d01f7669521e6fefd146fbb1718 / tree 568974b45cf06fd76a03e70e57a643184ecac528 as mechanically ready for the final Pro cross-cut audit. Public v0.5.0 remains unreleased.",
                             "The archived candidate passed compilation, full unit tests, resource-planner tests, version/license/citation checks, explicit-lock hygiene, setup smoke, ancestry and working-tree hygiene.", str(durable_evidence), effective_at)
        superseding_decision(conn, "release_candidate_ready_for_final_pro_audit_v0_1_0", "release_readiness",
                             "RC candidate ready for final Pro cross-cut audit",
                             "All planned High-mode release-packaging work required before the final Pro audit is complete for v0.5.0-rc1. PUBLIC_RC_PRO_CROSSCUT_AUDIT remains OPEN and is the blocking next step before final-version conversion/tag/release binding.",
                             "Stage16AF is the mechanical RC preflight checkpoint and explicitly records that no public release has been created.", str(durable_evidence), effective_at)

        add_metric(conn, "16AE_PUBLIC_RELEASE_PACKAGING", "candidate_package_version", "0.5.0rc1", str(durable_evidence), effective_at)
        add_metric(conn, "16AE_PUBLIC_RELEASE_PACKAGING", "software_license", "BSD-3-Clause", str(docs["software_license"]), effective_at)
        add_metric(conn, "16AE_PUBLIC_RELEASE_PACKAGING", "explicit_lock_sha256", obj["explicit_lock_sha256"], str(durable_evidence), effective_at)
        add_metric(conn, "16AF_RELEASE_CANDIDATE_PREFLIGHT", "candidate_head", obj["candidate_head"], str(durable_evidence), effective_at)
        add_metric(conn, "16AF_RELEASE_CANDIDATE_PREFLIGHT", "candidate_tree", obj["candidate_tree"], str(durable_evidence), effective_at)
        add_metric(conn, "16AF_RELEASE_CANDIDATE_PREFLIGHT", "git_archive_sha256", obj["git_archive_sha256"], str(durable_evidence), effective_at)
        add_metric(conn, "16AF_RELEASE_CANDIDATE_PREFLIGHT", "rc_preflight_status", "PASS", str(durable_evidence), effective_at)

        conn.execute(
            "UPDATE open_questions SET next_action=?,evidence_path=?,effective_at=? WHERE question_key='PUBLIC_RC_PRO_CROSSCUT_AUDIT' AND status='OPEN'",
            ("Run the final Pro-level cross-cut audit now against the stabilized v0.5.0-rc1 release candidate and current SSOT/Git/docs state. Do not create the final v0.5.0 tag/release before the audit passes and any blocking findings are resolved.", str(durable_evidence), effective_at),
        )
        conn.execute(
            "UPDATE open_questions SET next_action=?,evidence_path=?,effective_at=? WHERE question_key='CORE_FREEZE_GIT_TAG_AND_PUBLIC_RELEASE_BINDING' AND status='OPEN'",
            ("Mechanical v0.5.0-rc1 packaging is complete. After the final Pro cross-cut audit passes and any blocking findings are resolved, convert RC version metadata to final 0.5.0, create the immutable public Git tag/release, verify citation binding, and then adjudicate closure.", str(durable_evidence), effective_at),
        )
        row = conn.execute("SELECT limitation_key FROM limitations WHERE limitation_key='PUBLIC_V050_RELEASE_NOT_YET_COMPLETE'").fetchone()
        if row:
            conn.execute(
                "UPDATE limitations SET mitigation=?,evidence_path=?,effective_at=? WHERE limitation_key='PUBLIC_V050_RELEASE_NOT_YET_COMPLETE'",
                ("v0.5.0-rc1 mechanical packaging and RC preflight are complete. Public release remains intentionally uncreated until the final Pro cross-cut audit passes, blocking findings are resolved, final version metadata is bound, and the immutable tag/release/citation binding is verified.", str(durable_evidence), effective_at),
            )

        conn.commit()
        ssot = load_ssot(ssot_py)
        checks = ssot.validate_db(conn, project_root)
        failed = [row for row in checks if row[1] == "FAIL"]
        if failed:
            raise RegisterError(f"post-Stage16AG SSOT validation failed: {failed}")
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
        "status": "PASS_STAGE16AG_RC_PACKAGING_REGISTERED",
        "effective_at": effective_at,
        "repo_head": head,
        "rc_candidate_head": RC_CANDIDATE_HEAD,
        "rc_candidate_tree": RC_CANDIDATE_TREE,
        "freeze_root": FREEZE_ROOT,
        "stage16af_evidence_sha256": RC_PREFLIGHT_SHA,
        "software_license": "BSD-3-Clause",
        "candidate_package_version": "0.5.0rc1",
        "public_release_created": False,
        "public_rc_pro_crosscut_audit": "OPEN_BLOCKING_NEXT",
        "ssot_pre_sha256": pre_sha,
        "ssot_post_sha256": post_sha,
        "backup": str(backup),
        "summary": str(summary),
        "human_visual_review_required": False,
        "next_step": "RUN_FINAL_PRO_CROSSCUT_AUDIT",
    }
    result_path = durable_root / "stage16ag_rc_packaging_registration.result.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("===== RNA-TR-SCOUT STAGE16AG FINAL =====")
    for k in ("status", "repo_head", "rc_candidate_head", "ssot_pre_sha256", "ssot_post_sha256", "public_rc_pro_crosscut_audit", "next_step"):
        print(f"{k}\t{result[k]}")
    print(f"result\t{result_path}")
    print("human_visual_review_required\tfalse")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
