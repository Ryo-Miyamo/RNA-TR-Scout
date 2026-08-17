#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
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

VERSION = "rnatr_stage16v_bind_stage16r_evidence_v0.1.0"
DEFAULT_REPO_ROOT = Path("/mnt/intelssd/rnatr_git_stage/LOCAL_CORE_FREEZE_V0.1.0_git_snapshot_v0.1.2")
DEFAULT_PROJECT_ROOT = Path("/mnt/intelssd/rnatr_project")
DEFAULT_SOURCE_ROOT = Path("/home/tokushimaneuro02/Downloads")
BASE_MAIN = "8f0ef10651c0750d34adf08ca4d2010203550fef"
STAGE16R_SOURCE = "2191352170afe284c88cccd92c192efda2465b09"
FREEZE_ROOT = "4b1981db955a8aa92a2a01e19bbb1cfc2aa0ebfb"
RUN_ID = "RNA_TR_SCOUT_STAGE16_RELEASE_ENGINEERING"
STAGE_KEY = "16R_FRESH_END_TO_END"

FILES = {
    "json": ("rnatr_stage16r_fresh_public_fastq_e2e_v0.1.0.json", "4445143bb1f138b39e240a9ed85c8bc0f1b31ff632db9aad781b9a44f60829ee"),
    "text": ("rnatr_stage16r_fresh_public_fastq_e2e_v0.1.0.txt", "368f68846d76e79e83bfa6b3c143f056a2630b2f1654db1f15638af02e650993"),
    "script": ("rnatr_stage16r_fresh_public_fastq_e2e_v010.py", "00c33aca303692e1c17b46906898415cf273d21bc263dc3b78f0151b44a18752"),
    "script_sha": ("rnatr_stage16r_fresh_public_fastq_e2e_v010.py.sha256", None),
}

EXPECTED_FINAL_TABLES = {
    "general_repeat_calls.tsv": (388571, "21edb2595f24849282cf2d67e9f0a257d756c8d9c82d9619b297fd83d769bf85"),
    "read_evidence.tsv": (388571, "4c66159929b780ff6b637f1842b5fa994b4322e5deae17fef3a24a313d4190f9"),
    "repeat_events.tsv": (160297, "3996edc2491e2ca3f47be5ec5c931f8ac9b2e66213d93e864253a11a4a1bc51e"),
    "repeat_interruptions.tsv": (848, "d835cc0786c5972e6fe114d1524d72948010d29dc6ba1ad18e1918b07c7f5556"),
    "repeat_segments.tsv": (161265, "ac8ac589591a9629100b5edc2613bc77b21346eb389d06b57254e7afecb8859e"),
}


class BindError(RuntimeError):
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
        raise BindError(f"command failed ({p.returncode}): {' '.join(cmd)}\n{p.stdout}")
    return p.stdout.strip()


def git_head(root: Path) -> str:
    return run(["git", "rev-parse", "HEAD"], root).splitlines()[-1]


def git_status(root: Path) -> str:
    return run(["git", "status", "--porcelain"], root)


def git_is_ancestor(root: Path, older: str, newer: str) -> bool:
    p = subprocess.run(["git", "merge-base", "--is-ancestor", older, newer], cwd=str(root))
    return p.returncode == 0


def load_ssot(path: Path):
    spec = importlib.util.spec_from_file_location("rnatr_ssot_stage16v", path)
    if spec is None or spec.loader is None:
        raise BindError(f"cannot import SSOT module: {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def verify_source_artifacts(source_root: Path) -> tuple[dict[str, Path], dict[str, str], dict]:
    paths: dict[str, Path] = {}
    hashes: dict[str, str] = {}
    for key, (name, expected) in FILES.items():
        p = source_root / name
        if not p.is_file() or p.is_symlink():
            raise BindError(f"missing/invalid Stage16R original: {p}")
        observed = sha256_file(p)
        if expected and observed != expected:
            raise BindError(f"SHA mismatch for {p.name}: {observed} != {expected}")
        paths[key] = p
        hashes[key] = observed

    recorded = paths["script_sha"].read_text(encoding="utf-8").strip().split()
    if len(recorded) < 2 or recorded[0] != FILES["script"][1] or recorded[-1] != FILES["script"][0]:
        raise BindError("script SHA sidecar does not bind the expected Stage16R script")

    payload = json.loads(paths["json"].read_text(encoding="utf-8"))
    exact = {
        "version": "rnatr_stage16r_fresh_public_fastq_e2e_v0.1.0",
        "status": "PASS_FRESH_MACHINE_EQUIVALENT_PUBLIC_FASTQ_TO_FINAL",
        "source_head": STAGE16R_SOURCE,
        "remote_main": STAGE16R_SOURCE,
        "fresh_clone_head": STAGE16R_SOURCE,
        "fresh_clone_source": "PRIVATE_GITHUB_ORIGIN",
        "freeze_root": FREEZE_ROOT,
        "fresh_environment": "PASS_CREATED",
        "fresh_standard_resources": "PASS_STANDARD_RESOURCES_READY",
        "reference_source_mode": "LOCAL_EXACT_OFFICIAL_GENCODE_CACHE",
        "catalog_source_mode": "LOCAL_EXACT_STAGE16L_RELEASE_BUNDLE",
        "tier3_fastq_sha": "PASS_EXACT",
        "public_command": "rnatr-scout run",
        "public_input_mode": "FASTQ_AUTO_MAPPING",
        "mapping": "PASS",
        "mapping_artifacts_present": "PASS_3_OF_3",
        "final_exact_plain_table_parity": "PASS_5_OF_5",
        "public_resume": "PASS_SECOND_RESUME_NOOP",
        "post_resume_final_parity": "PASS_5_OF_5",
        "post_e2e_setup_verify_only": "PASS",
    }
    for key, value in exact.items():
        if payload.get(key) != value:
            raise BindError(f"Stage16R JSON field mismatch: {key}={payload.get(key)!r}, expected {value!r}")

    expected_true = [
        "fresh_clone_git_clean_after_setup", "fresh_clone_git_clean_after_e2e",
        "fresh_clone_git_clean_after_resume", "mapping_golden_validation_scope",
        "mapping_artifacts_unchanged_on_resume", "full_large_network_download_deferred_to_rc",
    ]
    for key in expected_true:
        if payload.get(key) is not True:
            raise BindError(f"Stage16R JSON expected true: {key}")
    expected_false = [
        "source_git_mutated", "frozen_core_modified", "large_reference_network_download",
        "mapping_rerun_on_resume", "human_visual_review_required",
    ]
    for key in expected_false:
        if payload.get(key) is not False:
            raise BindError(f"Stage16R JSON expected false: {key}")

    tables = payload.get("final_tables")
    if not isinstance(tables, dict) or set(tables) != set(EXPECTED_FINAL_TABLES):
        raise BindError("Stage16R final table set mismatch")
    for name, (rows, digest) in EXPECTED_FINAL_TABLES.items():
        item = tables.get(name, {})
        if item.get("rows") != rows or item.get("sha256") != digest:
            raise BindError(f"Stage16R final table identity mismatch: {name}")

    return paths, hashes, payload


def copy_durable(paths: dict[str, Path], project_root: Path) -> tuple[Path, dict[str, str]]:
    digest = FILES["json"][1]
    root = project_root / "metadata/ssot/checkpoints/stage16v_stage16r_evidence_binding_v0.1.0" / f"sha256_{digest}"
    originals = root / "originals"
    originals.mkdir(parents=True, exist_ok=True)
    copied: dict[str, str] = {}
    for key, src in paths.items():
        dst = originals / src.name
        if dst.exists():
            if not dst.is_file() or sha256_file(dst) != sha256_file(src):
                raise BindError(f"existing durable copy differs: {dst}")
        else:
            shutil.copy2(src, dst)
        copied[key] = sha256_file(dst)
    return root, copied


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


def superseding_decision(conn: sqlite3.Connection, decision_key: str, category: str, title: str,
                         statement: str, confidence: str, rationale: str, evidence_path: str,
                         effective_at: str) -> None:
    old = conn.execute(
        "SELECT decision_id FROM decisions WHERE decision_key=? AND status='ACTIVE'",
        (decision_key,),
    ).fetchone()
    old_id = old[0] if old else None
    if old_id:
        conn.execute("UPDATE decisions SET status='SUPERSEDED' WHERE decision_id=?", (old_id,))
    new_id = "decision_" + hashlib.sha256((VERSION + "|" + decision_key).encode()).hexdigest()[:20]
    conn.execute(
        """INSERT OR REPLACE INTO decisions(decision_id,decision_key,category,title,statement,status,confidence,
           effective_at,supersedes_decision_id,rationale,evidence_path) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (new_id, decision_key, category, title, statement, "ACTIVE", confidence, effective_at,
         old_id, rationale, evidence_path),
    )


def add_metric(conn: sqlite3.Connection, name: str, value: str, source: str, effective_at: str) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO metrics(run_id,stage_key,metric_name,value_text,value_num,unit,
           denominator_num,source_path,metric_status,recorded_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (RUN_ID, STAGE_KEY, name, value, None, None, None, source, "CURRENT", effective_at),
    )


def apply_db(conn: sqlite3.Connection, durable_json: Path, payload: dict, effective_at: str) -> None:
    conn.execute(
        """UPDATE stage_definitions SET implementation_status=?, notes=? WHERE stage_key=?""",
        ("VALIDATED_WITH_SCOPE",
         "PASS for fresh-machine-equivalent public FASTQ-to-final at source 219135... using exact local official GENCODE cache and exact Stage16L catalog bundle; full large network resource acquisition remains RC scope.",
         STAGE_KEY),
    )
    cur = conn.execute(
        """UPDATE run_stages SET status='PASS',qc_path=?,qc_status='PASS',ended_at=?,notes=?
           WHERE run_id=? AND stage_key=? AND attempt_tag='v0.1.0'""",
        (str(durable_json), effective_at,
         "Stage16R original result bound by exact SHA. Fresh private-GitHub clone, fresh environment, standard resources, public rnatr-scout run FASTQ auto-mapping, exact 5/5 final-table parity and SECOND_RESUME_NOOP PASS. Reference/catalog payloads were exact local sources; full large network acquisition remains deferred to RC.",
         RUN_ID, STAGE_KEY),
    )
    if cur.rowcount != 1:
        raise BindError(f"expected exactly one Stage16R pending row, updated {cur.rowcount}")

    conn.execute(
        "UPDATE open_questions SET status='CLOSED',next_action=? WHERE question_key='STAGE16R_AUTHORITATIVE_EVIDENCE_BINDING' AND status='OPEN'",
        ("CLOSED: original Stage16R JSON/script/text were recovered, SHA-verified, durably copied and bound to the SSOT Stage16R PASS row.",),
    )

    superseding_decision(
        conn,
        "stage16_release_engineering_progress_checkpoint_v0_1_0",
        "release_readiness",
        "Register post-Freeze Stage16 release-engineering progress",
        f"Current release-engineering state now includes Stage16Q public CLI PASS, Stage16R fresh-machine-equivalent public FASTQ-to-final PASS with exact local reference/catalog resources, Stage16S scoped cross-hardware scientific parity PASS, and Stage16T owner-reviewed user documentation PASS. Full large-network resource acquisition remains a separate public-RC gate. The immutable Core Freeze root remains {FREEZE_ROOT}.",
        "HIGH",
        "Stage16R original evidence was recovered from Downloads, verified against exact file SHA-256 and internal result semantics, copied to a durable SSOT checkpoint path, and bound without changing the frozen Core.",
        str(durable_json), effective_at,
    )
    superseding_decision(
        conn,
        "stage16r_fresh_public_fastq_e2e_acceptance_v0_1_0",
        "production_validation",
        "Accept Stage16R fresh public FASTQ-to-final validation",
        "Accept Stage16R v0.1.0 as PASS for a fresh private-GitHub clone, fresh isolated environment, validated standard resources from exact local official/reference bundles, public `rnatr-scout run` FASTQ auto-mapping, exact five-table parity, and second-resume no-op. This is fresh-machine-equivalent validation, not final proof of full large-reference/catalog network acquisition.",
        "HIGH",
        "The authoritative result reports source/fresh-clone head 2191352170afe284c88cccd92c192efda2465b09, Freeze root unchanged, mapping PASS, 5/5 final-table parity, post-resume 5/5 parity, clean Git state throughout, and no Core/source mutation.",
        str(durable_json), effective_at,
    )

    add_metric(conn, "stage16r_status", "PASS_FRESH_MACHINE_EQUIVALENT_PUBLIC_FASTQ_TO_FINAL", str(durable_json), effective_at)
    add_metric(conn, "stage16r_source_head", STAGE16R_SOURCE, str(durable_json), effective_at)
    add_metric(conn, "stage16r_final_exact_plain_table_parity", "PASS_5_OF_5", str(durable_json), effective_at)
    add_metric(conn, "stage16r_public_resume", "PASS_SECOND_RESUME_NOOP", str(durable_json), effective_at)
    add_metric(conn, "stage16r_post_resume_final_parity", "PASS_5_OF_5", str(durable_json), effective_at)
    add_metric(conn, "stage16r_resource_scope", "LOCAL_EXACT_OFFICIAL_GENCODE_CACHE_PLUS_LOCAL_EXACT_STAGE16L_BUNDLE;FULL_LARGE_NETWORK_DEFERRED_TO_RC", str(durable_json), effective_at)
    add_metric(conn, "stage16r_public_fastq_to_final_seconds", str(payload["public_fastq_to_final_seconds"]), str(durable_json), effective_at)


def main() -> int:
    ap = argparse.ArgumentParser(description="Bind recovered authoritative Stage16R evidence into the canonical RNA-TR-Scout SSOT.")
    ap.add_argument("--repo-root", type=Path, default=DEFAULT_REPO_ROOT)
    ap.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    ap.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    repo_root = args.repo_root.resolve()
    project_root = args.project_root.resolve()
    source_root = args.source_root.resolve()
    if git_status(repo_root):
        raise BindError("Git working tree must be clean before Stage16V binding")
    head = git_head(repo_root)
    if not git_is_ancestor(repo_root, BASE_MAIN, head):
        raise BindError(f"repo HEAD {head} does not descend from Stage16U main {BASE_MAIN}")
    if not git_is_ancestor(repo_root, FREEZE_ROOT, head):
        raise BindError("Freeze root is not an ancestor of current repo HEAD")

    paths, source_hashes, payload = verify_source_artifacts(source_root)
    ssot_root = project_root / "metadata/ssot"
    db = ssot_root / "rnatr_ssot.sqlite"
    ssot_py = ssot_root / "rnatr_ssot.py"
    if not db.is_file() or not ssot_py.is_file():
        raise BindError("canonical SSOT database/implementation missing")

    with sqlite3.connect(str(db)) as pre:
        integ = pre.execute("PRAGMA integrity_check").fetchone()[0]
        if integ != "ok" or list(pre.execute("PRAGMA foreign_key_check")):
            raise BindError("canonical SSOT failed preflight integrity/foreign-key check")
        row = pre.execute(
            "SELECT status,qc_path FROM latest_stage_status WHERE run_id=? AND stage_key=?",
            (RUN_ID, STAGE_KEY),
        ).fetchone()
        if not row or row[0] not in {"EVIDENCE_BINDING_PENDING", "PASS"}:
            raise BindError(f"unexpected current Stage16R SSOT row: {row}")

    print("===== RNA-TR-SCOUT STAGE16V STAGE16R EVIDENCE BINDING PREFLIGHT =====")
    print(f"version\t{VERSION}")
    print(f"repo_head\t{head}")
    print(f"stage16r_source_head\t{payload['source_head']}")
    print(f"stage16r_json_sha256\t{source_hashes['json']}")
    print(f"stage16r_script_sha256\t{source_hashes['script']}")
    print(f"stage16r_status\t{payload['status']}")
    print(f"final_parity\t{payload['final_exact_plain_table_parity']}")
    print(f"resume\t{payload['public_resume']}")
    print(f"reference_source_mode\t{payload['reference_source_mode']}")
    print(f"catalog_source_mode\t{payload['catalog_source_mode']}")
    print(f"full_large_network_download_deferred_to_rc\t{str(payload['full_large_network_download_deferred_to_rc']).lower()}")
    if not args.execute:
        print("status\tPREFLIGHT_PASS_READY_FOR_EXECUTE")
        return 0

    durable_root, copied_hashes = copy_durable(paths, project_root)
    durable_json = durable_root / "originals" / FILES["json"][0]
    effective_at = now_utc()
    backup_dir = durable_root / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    pre_sha = sha256_file(db)
    backup = backup_dir / f"rnatr_ssot.pre_stage16v.{effective_at.replace(':','').replace('+00:00','Z')}.sqlite"
    shutil.copy2(db, backup)
    if sha256_file(backup) != pre_sha:
        raise BindError("SSOT backup SHA mismatch")

    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        conn.execute("BEGIN IMMEDIATE")
        for key, src_type in [("json","stage16r_authoritative_json"),("text","stage16r_authoritative_text"),
                              ("script","stage16r_authoritative_runner"),("script_sha","stage16r_runner_sha_sidecar")]:
            source_document(conn, durable_root / "originals" / FILES[key][0], src_type, effective_at)
        apply_db(conn, durable_json, payload, effective_at)
        conn.commit()

        ssot = load_ssot(ssot_py)
        checks = ssot.validate_db(conn, project_root)
        failed = [x for x in checks if x[1] == "FAIL"]
        if failed:
            raise BindError(f"post-binding SSOT validation failed: {failed}")
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
        "status": "PASS_STAGE16R_AUTHORITATIVE_EVIDENCE_BOUND_WITH_SCOPE",
        "effective_at": effective_at,
        "repo_head": head,
        "stage16r_source_head": STAGE16R_SOURCE,
        "freeze_root": FREEZE_ROOT,
        "source_hashes": source_hashes,
        "durable_copy_hashes": copied_hashes,
        "durable_stage16r_json": str(durable_json),
        "stage16r_result_status": payload["status"],
        "stage16r_scope": {
            "fresh_clone": True,
            "fresh_environment": True,
            "public_fastq_to_final": True,
            "exact_final_parity_5_of_5": True,
            "second_resume_noop": True,
            "full_large_network_resource_acquisition": False,
            "full_large_network_resource_acquisition_deferred_to_rc": True,
        },
        "ssot_pre_sha256": pre_sha,
        "ssot_post_sha256": post_sha,
        "backup": str(backup),
        "summary": str(summary),
    }
    result_path = durable_root / "stage16v_stage16r_evidence_binding.result.json"
    tmp = result_path.with_suffix(".json.part")
    tmp.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, result_path)

    print("===== RNA-TR-SCOUT STAGE16V STAGE16R EVIDENCE BINDING RESULT =====")
    print("status\tPASS_STAGE16R_AUTHORITATIVE_EVIDENCE_BOUND_WITH_SCOPE")
    print(f"durable_stage16r_json\t{durable_json}")
    print(f"binding_result\t{result_path}")
    print(f"ssot_db_post_sha256\t{post_sha}")
    print("stage16r\tPASS_FRESH_MACHINE_EQUIVALENT_PUBLIC_FASTQ_TO_FINAL")
    print("full_network_rc_gate\tREMAINS_OPEN")
    print("human_visual_review_required\tfalse")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
