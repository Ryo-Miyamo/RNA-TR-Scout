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

VERSION = "rnatr_stage16y_register_stage16wx_v0.1.0"
DEFAULT_REPO_ROOT = Path("/mnt/intelssd/rnatr_git_stage/LOCAL_CORE_FREEZE_V0.1.0_git_snapshot_v0.1.2")
DEFAULT_PROJECT_ROOT = Path("/mnt/intelssd/rnatr_project")
DEFAULT_DOWNLOADS = Path.home() / "Downloads"
DEFAULT_STAGE16W_ROOT = Path("/mnt/intelssd/rnatr_release_engineering/stage16w_public_catalog_distribution")
FREEZE_ROOT = "4b1981db955a8aa92a2a01e19bbb1cfc2aa0ebfb"
STAGE16W_SOURCE = "24ccb15e01921f05465f8bddb59f743d1ef4cc6f"
RUN_ID = "RNA_TR_SCOUT_STAGE16_RELEASE_ENGINEERING"
CATALOG_SHA = "54a24e4b60d920c8fec16b2df37b47e40407de42b949b18dc6233e97d85f2fef"
STAGE16X_SHA = "75f9cc560c22adb236902324d2d4771f7a1a6fee439cedf747a9cfb163fffd09"
FASTQ_SHA = "559dd0f3cb7d7de3c108a68a0d36efb895aae8f63e1a78aa4acd1d91b2c27173"

EXPECTED_TABLES = {
    "general_repeat_calls.tsv": (388571, "21edb2595f24849282cf2d67e9f0a257d756c8d9c82d9619b297fd83d769bf85"),
    "read_evidence.tsv": (388571, "4c66159929b780ff6b637f1842b5fa994b4322e5deae17fef3a24a313d4190f9"),
    "repeat_events.tsv": (160297, "3996edc2491e2ca3f47be5ec5c931f8ac9b2e66213d93e864253a11a4a1bc51e"),
    "repeat_interruptions.tsv": (848, "d835cc0786c5972e6fe114d1524d72948010d29dc6ba1ad18e1918b07c7f5556"),
    "repeat_segments.tsv": (161265, "ac8ac589591a9629100b5edc2613bc77b21346eb389d06b57254e7afecb8859e"),
}


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


def ensure_file(path: Path, label: str) -> Path:
    if not path.is_file() or path.is_symlink():
        raise RegisterError(f"{label} missing/invalid: {path}")
    return path


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
    p = subprocess.run(["git", "merge-base", "--is-ancestor", older, newer], cwd=str(root))
    return p.returncode == 0


def load_ssot(path: Path):
    spec = importlib.util.spec_from_file_location("rnatr_ssot_stage16y", path)
    if spec is None or spec.loader is None:
        raise RegisterError(f"cannot import SSOT module: {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RegisterError(f"invalid JSON: {path}: {exc}") from exc


def locate_stage16x(downloads: Path, explicit: Path | None) -> Path:
    if explicit is not None:
        p = explicit.resolve()
        ensure_file(p, "Stage16X authoritative JSON")
        if sha256_file(p) != STAGE16X_SHA:
            raise RegisterError(f"Stage16X JSON SHA mismatch: {sha256_file(p)} != {STAGE16X_SHA}")
        return p
    candidates = sorted(downloads.glob("rnatr_stage16x_full_network_fresh_install_result_v0.1.2_*.json"))
    exact = [p for p in candidates if p.is_file() and not p.is_symlink() and sha256_file(p) == STAGE16X_SHA]
    if len(exact) != 1:
        raise RegisterError(f"expected exactly one exact Stage16X JSON in {downloads}; found {len(exact)}")
    return exact[0].resolve()


def verify_stage16w(repack_path: Path, publish_path: Path) -> tuple[dict, dict]:
    repack = load_json(ensure_file(repack_path, "Stage16W repack result"))
    publish = load_json(ensure_file(publish_path, "Stage16W publish result"))
    if repack.get("status") != "PASS_RUNTIME_5_OF_5_EXACT_PUBLIC_METADATA_REPACK":
        raise RegisterError("Stage16W repack status mismatch")
    if repack.get("output_bundle_sha256") != CATALOG_SHA:
        raise RegisterError("Stage16W repack bundle SHA mismatch")
    if repack.get("runtime_members_exact") != 5 or repack.get("required_notice_members_present") is not True:
        raise RegisterError("Stage16W repack runtime/notice proof mismatch")
    if publish.get("status") != "PASS_PUBLIC_RELEASE_ASSET_UNAUTHENTICATED_EXACT_SHA":
        raise RegisterError("Stage16W publish status mismatch")
    if publish.get("resource_repository") != "Ryo-Miyamo/RNA-TR-Scout-resources":
        raise RegisterError("Stage16W resource repository mismatch")
    if publish.get("resource_repository_visibility") != "PUBLIC":
        raise RegisterError("Stage16W resource repository is not PUBLIC")
    if publish.get("release_tag") != "catalog-grch38-v0.1.0":
        raise RegisterError("Stage16W release tag mismatch")
    if publish.get("asset_sha256") != CATALOG_SHA or publish.get("unauthenticated_download_exact_sha") is not True:
        raise RegisterError("Stage16W public asset SHA/download proof mismatch")
    return repack, publish


def verify_stage16x(path: Path) -> dict:
    if sha256_file(path) != STAGE16X_SHA:
        raise RegisterError("Stage16X authoritative JSON SHA mismatch")
    x = load_json(path)
    expected = {
        "version": "rnatr_stage16x_full_network_fresh_install_v0.1.2",
        "status": "PASS_FULL_NETWORK_FRESH_INSTALL_PUBLIC_FASTQ_TO_FINAL",
        "source_commit": STAGE16W_SOURCE,
        "freeze_root": FREEZE_ROOT,
        "network_reference_downloads": "PASS_2_OF_2_EXACT",
        "network_catalog_download": "PASS_PUBLIC_RELEASE_ASSET_EXACT",
        "catalog_outer_sha256": CATALOG_SHA,
        "tier3_fastq_sha256": FASTQ_SHA,
        "public_command": "rnatr-scout run",
        "public_input_mode": "FASTQ_AUTO_MAPPING",
        "mapping": "PASS",
        "final_exact_plain_table_parity": "PASS_5_OF_5",
        "public_resume": "PASS_SECOND_RESUME_NOOP",
        "post_resume_final_parity": "PASS_5_OF_5",
    }
    for key, value in expected.items():
        if x.get(key) != value:
            raise RegisterError(f"Stage16X field mismatch: {key}={x.get(key)!r}, expected {value!r}")
    if x.get("mapping_rerun_on_resume") is not False:
        raise RegisterError("Stage16X mapping_rerun_on_resume must be false")
    if x.get("mapping_artifacts_unchanged_on_resume") is not True:
        raise RegisterError("Stage16X mapping artifacts were not proven unchanged")
    if x.get("fresh_clone_git_clean_after_validation") is not True:
        raise RegisterError("Stage16X fresh clone was not Git-clean after validation")
    manifest = x.get("resource_install_manifest", {})
    if manifest.get("status") != "PASS_STANDARD_RESOURCES_READY":
        raise RegisterError("Stage16X resource manifest not READY")
    if manifest.get("catalog_public_url_finalized") is not True:
        raise RegisterError("Stage16X catalog public URL was not finalized")
    if manifest.get("reference_source_fasta") != "PASS_DOWNLOADED_EXACT" or manifest.get("reference_source_gtf") != "PASS_DOWNLOADED_EXACT":
        raise RegisterError("Stage16X reference network downloads not exact")
    if manifest.get("catalog_source") != "PASS_DOWNLOADED_EXACT":
        raise RegisterError("Stage16X catalog network download not exact")
    tables = x.get("final_tables", {})
    if set(tables) != set(EXPECTED_TABLES):
        raise RegisterError("Stage16X final table set mismatch")
    for name, (rows, digest) in EXPECTED_TABLES.items():
        item = tables.get(name, {})
        if item.get("rows") != rows or item.get("sha256") != digest:
            raise RegisterError(f"Stage16X table mismatch: {name}")
    return x


def verify_repo_profile(repo_root: Path) -> Path:
    p = ensure_file(repo_root / "config/resources/standard_v0.1.1/validated_profile.json", "standard resource profile")
    obj = load_json(p)
    cat = obj.get("catalog_bundle", {})
    if cat.get("sha256") != CATALOG_SHA:
        raise RegisterError("repo profile does not bind the public catalog outer SHA")
    url = str(cat.get("public_url", ""))
    if not url.startswith("https://github.com/Ryo-Miyamo/RNA-TR-Scout-resources/releases/download/catalog-grch38-v0.1.0/"):
        raise RegisterError("repo profile public catalog URL mismatch")
    return p


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


def ensure_stage(conn: sqlite3.Connection, key: str, order: float, name: str, purpose: str) -> None:
    conn.execute(
        """INSERT INTO stage_definitions(stage_key,stage_order,name,purpose,category,implementation_status,notes)
           VALUES(?,?,?,?,?,?,?)
           ON CONFLICT(stage_key) DO UPDATE SET stage_order=excluded.stage_order,name=excluded.name,
             purpose=excluded.purpose,category=excluded.category,implementation_status=excluded.implementation_status,
             notes=excluded.notes""",
        (key, order, name, purpose, "release_engineering", "VALIDATED_WITH_SCOPE",
         "Post-Freeze release engineering; no frozen scientific Core semantics changed."),
    )


def add_run_stage(conn: sqlite3.Connection, key: str, attempt: str, evidence: str, notes: str, effective_at: str) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO run_stages(run_id,stage_key,implementation_id,attempt_tag,status,command_text,
           qc_path,qc_status,started_at,ended_at,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (RUN_ID, key, None, attempt, "PASS", None, evidence, "PASS", None, effective_at, notes),
    )


def decision_id(key: str) -> str:
    return "decision_" + hashlib.sha256((VERSION + "|" + key).encode()).hexdigest()[:20]


def superseding_decision(conn: sqlite3.Connection, key: str, category: str, title: str,
                         statement: str, rationale: str, evidence: str, effective_at: str) -> None:
    row = conn.execute("SELECT decision_id FROM decisions WHERE decision_key=? AND status='ACTIVE'", (key,)).fetchone()
    old = row[0] if row else None
    if old:
        conn.execute("UPDATE decisions SET status='SUPERSEDED' WHERE decision_id=?", (old,))
    conn.execute(
        """INSERT OR REPLACE INTO decisions(decision_id,decision_key,category,title,statement,status,confidence,
           effective_at,supersedes_decision_id,rationale,evidence_path) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (decision_id(key), key, category, title, statement, "ACTIVE", "HIGH", effective_at, old, rationale, evidence),
    )


def add_metric(conn: sqlite3.Connection, stage: str, name: str, value: str, source: str, effective_at: str) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO metrics(run_id,stage_key,metric_name,value_text,value_num,unit,
           denominator_num,source_path,metric_status,recorded_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (RUN_ID, stage, name, value, None, None, None, source, "CURRENT", effective_at),
    )


def close_question(conn: sqlite3.Connection, key: str, closure: str) -> None:
    row = conn.execute("SELECT status FROM open_questions WHERE question_key=?", (key,)).fetchone()
    if row is None:
        raise RegisterError(f"expected SSOT open question missing: {key}")
    if row[0] == "OPEN":
        conn.execute("UPDATE open_questions SET status='CLOSED',next_action=? WHERE question_key=?", (closure, key))
    elif row[0] != "CLOSED":
        raise RegisterError(f"unexpected question status {key}: {row[0]}")


def supersede_limitation(conn: sqlite3.Connection, key: str) -> None:
    row = conn.execute("SELECT status FROM limitations WHERE limitation_key=?", (key,)).fetchone()
    if row and row[0] == "ACTIVE":
        conn.execute("UPDATE limitations SET status='SUPERSEDED' WHERE limitation_key=?", (key,))


def copy_exact(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        if not dst.is_file() or sha256_file(dst) != sha256_file(src):
            raise RegisterError(f"durable destination differs: {dst}")
    else:
        shutil.copy2(src, dst)
    if sha256_file(dst) != sha256_file(src):
        raise RegisterError(f"durable copy SHA mismatch: {dst}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Register Stage16W public catalog distribution and Stage16X full-network fresh-install PASS into the canonical RNA-TR-Scout SSOT.")
    ap.add_argument("--repo-root", type=Path, default=DEFAULT_REPO_ROOT)
    ap.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    ap.add_argument("--downloads", type=Path, default=DEFAULT_DOWNLOADS)
    ap.add_argument("--stage16w-root", type=Path, default=DEFAULT_STAGE16W_ROOT)
    ap.add_argument("--stage16x-result", type=Path)
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    repo_root = args.repo_root.resolve()
    project_root = args.project_root.resolve()
    downloads = args.downloads.expanduser().resolve()
    wroot = args.stage16w_root.resolve()
    if git_status(repo_root):
        raise RegisterError("Git working tree must be clean before Stage16Y")
    head = git_head(repo_root)
    if not git_is_ancestor(repo_root, STAGE16W_SOURCE, head):
        raise RegisterError(f"repo HEAD {head} does not descend from Stage16W source {STAGE16W_SOURCE}")
    if not git_is_ancestor(repo_root, FREEZE_ROOT, head):
        raise RegisterError("Freeze root is not an ancestor of repo HEAD")

    profile = verify_repo_profile(repo_root)
    repack_path = wroot / "stage16w_public_catalog_repack.result.json"
    publish_path = wroot / "stage16w_public_catalog_publish.result.json"
    repack, publish = verify_stage16w(repack_path, publish_path)
    x_path = locate_stage16x(downloads, args.stage16x_result)
    x = verify_stage16x(x_path)

    ssot_root = project_root / "metadata/ssot"
    db = ensure_file(ssot_root / "rnatr_ssot.sqlite", "canonical SSOT database")
    ssot_py = ensure_file(ssot_root / "rnatr_ssot.py", "canonical SSOT implementation")

    with sqlite3.connect(str(db)) as pre:
        if pre.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or list(pre.execute("PRAGMA foreign_key_check")):
            raise RegisterError("canonical SSOT failed preflight integrity/foreign-key check")
        for q in ("PUBLIC_CATALOG_BUNDLE_HOSTING", "FULL_NETWORK_FRESH_INSTALL_RC"):
            row = pre.execute("SELECT status FROM open_questions WHERE question_key=?", (q,)).fetchone()
            if not row or row[0] not in {"OPEN", "CLOSED"}:
                raise RegisterError(f"unexpected SSOT question state: {q}: {row}")

    print("===== RNA-TR-SCOUT STAGE16Y REGISTER STAGE16W/X PREFLIGHT =====")
    print(f"version\t{VERSION}")
    print(f"repo_head\t{head}")
    print(f"freeze_root\t{FREEZE_ROOT}")
    print(f"stage16w_publish_status\t{publish['status']}")
    print(f"catalog_outer_sha256\t{CATALOG_SHA}")
    print(f"stage16x_json\t{x_path}")
    print(f"stage16x_json_sha256\t{sha256_file(x_path)}")
    print(f"stage16x_status\t{x['status']}")
    print(f"final_parity\t{x['final_exact_plain_table_parity']}")
    print(f"resume\t{x['public_resume']}")
    if not args.execute:
        print("status\tPREFLIGHT_PASS_READY_FOR_EXECUTE")
        return 0

    durable_root = ssot_root / "checkpoints/stage16y_stage16wx_registration_v0.1.0" / f"sha256_{STAGE16X_SHA}"
    originals = durable_root / "originals"
    copy_exact(repack_path, originals / repack_path.name)
    copy_exact(publish_path, originals / publish_path.name)
    copy_exact(x_path, originals / "rnatr_stage16x_full_network_fresh_install_result_v0.1.2.json")
    durable_repack = originals / repack_path.name
    durable_publish = originals / publish_path.name
    durable_x = originals / "rnatr_stage16x_full_network_fresh_install_result_v0.1.2.json"

    effective_at = now_utc()
    backup_dir = durable_root / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    pre_sha = sha256_file(db)
    backup = backup_dir / f"rnatr_ssot.pre_stage16y.{effective_at.replace(':','').replace('+00:00','Z')}.sqlite"
    shutil.copy2(db, backup)
    if sha256_file(backup) != pre_sha:
        raise RegisterError("SSOT backup SHA mismatch")

    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        conn.execute("BEGIN IMMEDIATE")
        source_document(conn, durable_repack, "stage16w_public_catalog_repack_result", effective_at)
        source_document(conn, durable_publish, "stage16w_public_catalog_publish_result", effective_at)
        source_document(conn, durable_x, "stage16x_full_network_fresh_install_result", effective_at)
        source_document(conn, profile, "standard_resource_profile_public_catalog_bound", effective_at)

        ensure_stage(conn, "16W_PUBLIC_CATALOG_DISTRIBUTION", 172.0,
                     "Stage16W public catalog distribution",
                     "Publish the exact validated compact catalog bundle at a stable public location with third-party notices, provenance and exact SHA binding.")
        ensure_stage(conn, "16X_FULL_NETWORK_FRESH_INSTALL", 173.0,
                     "Stage16X full-network fresh-install validation",
                     "Validate fresh isolated environment/cache setup, official reference downloads, public catalog download and public 100k FASTQ-to-final execution with exact golden parity and resume.")
        add_run_stage(conn, "16W_PUBLIC_CATALOG_DISTRIBUTION", "v0.1.0", str(durable_publish),
                      "Public resource repository/release asset published; unauthenticated exact-SHA download PASS; runtime 5/5 members remained exact after metadata-only repack.", effective_at)
        add_run_stage(conn, "16X_FULL_NETWORK_FRESH_INSTALL", "v0.1.2", str(durable_x),
                      "Fresh isolated environment and dedicated caches; official GENCODE downloads 2/2 exact; public catalog release asset exact; public FASTQ auto-mapping to final 5/5 exact parity; SECOND_RESUME_NOOP PASS. v0.1.2 continued the same v0.1.1 fresh run after a wrapper-only post-setup assertion error.", effective_at)

        close_question(conn, "PUBLIC_CATALOG_BUNDLE_HOSTING",
                       "CLOSED: catalog-grch38-v0.1.0 is publicly hosted in Ryo-Miyamo/RNA-TR-Scout-resources and unauthenticated exact-SHA download was validated.")
        close_question(conn, "FULL_NETWORK_FRESH_INSTALL_RC",
                       "CLOSED: Stage16X validated official GENCODE and public catalog network acquisition from fresh dedicated caches followed by public 100k FASTQ-to-final exact 5/5 parity and second-resume no-op.")
        supersede_limitation(conn, "PUBLIC_CATALOG_BUNDLE_URL_PENDING")
        supersede_limitation(conn, "FULL_NETWORK_FRESH_INSTALL_RC_PENDING")

        superseding_decision(
            conn, "stage16_release_engineering_progress_checkpoint_v0_1_0",
            "release_readiness", "Register post-Freeze Stage16 release-engineering progress",
            f"Current release engineering includes Stage16Q public CLI PASS, Stage16R fresh-machine-equivalent FASTQ-to-final PASS, Stage16S scoped second-machine parity PASS, Stage16T owner-reviewed documentation PASS, Stage16W public catalog hosting PASS and Stage16X full-network fresh-install/public FASTQ-to-final PASS. The immutable Core Freeze root remains {FREEZE_ROOT}. Remaining work includes unresolved public-release packaging/claims, any still-required operational benchmark, and the single Pro cross-cut audit immediately before public RC.",
            "Stage16W/X authoritative results directly close the public catalog hosting and full-network resource acquisition gates without altering frozen Core semantics.", str(durable_x), effective_at)
        superseding_decision(
            conn, "stage16w_public_catalog_distribution_acceptance_v0_1_0",
            "resource_distribution", "Accept Stage16W public catalog distribution",
            f"Accept the public `Ryo-Miyamo/RNA-TR-Scout-resources` release `catalog-grch38-v0.1.0` as the standard catalog distribution for this validated profile. The outer archive SHA-256 is {CATALOG_SHA}; unauthenticated download is exact; the five scientific runtime member bytes remain unchanged.",
            "The public publication result and deterministic repack result jointly establish public accessibility, exact outer-archive identity, required notices/provenance and 5/5 runtime-member identity preservation.", str(durable_publish), effective_at)
        superseding_decision(
            conn, "stage16x_full_network_fresh_install_acceptance_v0_1_0",
            "production_validation", "Accept Stage16X full-network fresh-install validation",
            "Accept Stage16X v0.1.2 as PASS for fresh isolated source/environment/cache setup on the validated Linux x86-64 host, official GENCODE network acquisition, public catalog release-asset acquisition, public `rnatr-scout run` FASTQ auto-mapping, exact 5/5 final-table parity and second-resume no-op. This closes the intended full-network acquisition gate but is not a universal portability claim or a formal full-scale peak-disk benchmark.",
            "The authoritative Stage16X JSON binds exact reference/catalog downloads, standard resource validation, exact Tier3 fixture identity, final five-table SHA/row identities, mapping/resume behavior and clean Git state.", str(durable_x), effective_at)

        add_metric(conn, "16W_PUBLIC_CATALOG_DISTRIBUTION", "stage16w_status", publish["status"], str(durable_publish), effective_at)
        add_metric(conn, "16W_PUBLIC_CATALOG_DISTRIBUTION", "stage16w_catalog_outer_sha256", CATALOG_SHA, str(durable_publish), effective_at)
        add_metric(conn, "16W_PUBLIC_CATALOG_DISTRIBUTION", "stage16w_resource_repository", publish["resource_repository"], str(durable_publish), effective_at)
        add_metric(conn, "16W_PUBLIC_CATALOG_DISTRIBUTION", "stage16w_release_tag", publish["release_tag"], str(durable_publish), effective_at)
        add_metric(conn, "16X_FULL_NETWORK_FRESH_INSTALL", "stage16x_status", x["status"], str(durable_x), effective_at)
        add_metric(conn, "16X_FULL_NETWORK_FRESH_INSTALL", "stage16x_source_commit", x["source_commit"], str(durable_x), effective_at)
        add_metric(conn, "16X_FULL_NETWORK_FRESH_INSTALL", "stage16x_network_reference_downloads", x["network_reference_downloads"], str(durable_x), effective_at)
        add_metric(conn, "16X_FULL_NETWORK_FRESH_INSTALL", "stage16x_network_catalog_download", x["network_catalog_download"], str(durable_x), effective_at)
        add_metric(conn, "16X_FULL_NETWORK_FRESH_INSTALL", "stage16x_final_exact_plain_table_parity", x["final_exact_plain_table_parity"], str(durable_x), effective_at)
        add_metric(conn, "16X_FULL_NETWORK_FRESH_INSTALL", "stage16x_public_resume", x["public_resume"], str(durable_x), effective_at)
        add_metric(conn, "16X_FULL_NETWORK_FRESH_INSTALL", "stage16x_public_fastq_to_final_seconds", str(x.get("timing_seconds", {}).get("public_fastq_to_final", "")), str(durable_x), effective_at)

        conn.commit()
        ssot = load_ssot(ssot_py)
        checks = ssot.validate_db(conn, project_root)
        failed = [row for row in checks if row[1] == "FAIL"]
        if failed:
            raise RegisterError(f"post-Stage16Y SSOT validation failed: {failed}")
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
        "status": "PASS_STAGE16W_X_REGISTERED_AND_DIRECT_GATES_CLOSED",
        "effective_at": effective_at,
        "repo_head": head,
        "freeze_root": FREEZE_ROOT,
        "stage16w": {
            "repack_result": str(durable_repack),
            "publish_result": str(durable_publish),
            "catalog_outer_sha256": CATALOG_SHA,
            "public_catalog_hosting_gate": "CLOSED",
        },
        "stage16x": {
            "result": str(durable_x),
            "result_sha256": STAGE16X_SHA,
            "status": x["status"],
            "full_network_fresh_install_gate": "CLOSED",
            "final_parity": x["final_exact_plain_table_parity"],
            "resume": x["public_resume"],
        },
        "remaining_explicitly_open": [
            "PUBLIC_RC_PRO_CROSSCUT_AUDIT",
            "FULLSCALE_PEAK_DISK_BENCHMARK",
            "CORE_FREEZE_GIT_TAG_AND_PUBLIC_RELEASE_BINDING",
        ],
        "ssot_pre_sha256": pre_sha,
        "ssot_post_sha256": post_sha,
        "backup": str(backup),
        "summary": str(summary),
    }
    result_path = durable_root / "stage16y_stage16wx_registration.result.json"
    tmp = result_path.with_suffix(".json.part")
    tmp.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, result_path)

    print("===== RNA-TR-SCOUT STAGE16Y RESULT =====")
    print("status\tPASS_STAGE16W_X_REGISTERED_AND_DIRECT_GATES_CLOSED")
    print(f"stage16x_json_sha256\t{STAGE16X_SHA}")
    print("public_catalog_bundle_hosting\tCLOSED")
    print("full_network_fresh_install_rc\tCLOSED")
    print("public_rc_pro_crosscut_audit\tREMAINS_OPEN")
    print("fullscale_peak_disk_benchmark\tREMAINS_OPEN")
    print(f"ssot_db_post_sha256\t{post_sha}")
    print(f"result\t{result_path}")
    print("human_visual_review_required\tfalse")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
