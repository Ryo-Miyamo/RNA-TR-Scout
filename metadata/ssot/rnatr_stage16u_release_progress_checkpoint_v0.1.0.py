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
from typing import Any

VERSION = "rnatr_stage16u_release_progress_checkpoint_v0.1.0"
EXPECTED_MAIN = "be1de2ecdcaa681e3a3424486d340280001b0bf0"
FREEZE_ROOT = "4b1981db955a8aa92a2a01e19bbb1cfc2aa0ebfb"
DEFAULT_PROJECT_ROOT = Path("/mnt/intelssd/rnatr_project")


class CheckpointError(RuntimeError):
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
        raise CheckpointError(f"command failed ({p.returncode}): {' '.join(cmd)}\n{p.stdout}")
    return p.stdout.strip()


def git_head(root: Path) -> str:
    return run(["git", "rev-parse", "HEAD"], root).splitlines()[-1]


def git_is_ancestor(root: Path, older: str, newer: str) -> bool:
    p = subprocess.run(["git", "merge-base", "--is-ancestor", older, newer],
                       cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return p.returncode == 0


def git_status(root: Path) -> str:
    return run(["git", "status", "--porcelain"], root)


def load_ssot_module(path: Path):
    spec = importlib.util.spec_from_file_location("rnatr_ssot_stage16u_base", path)
    if spec is None or spec.loader is None:
        raise CheckpointError(f"cannot import SSOT module: {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def ensure_file(path: Path, label: str) -> Path:
    if not path.is_file() or path.is_symlink():
        raise CheckpointError(f"{label} missing/invalid: {path}")
    return path


def source_document(conn: sqlite3.Connection, path: Path, source_type: str, effective_at: str) -> None:
    ensure_file(path, source_type)
    stat = path.stat()
    mtime = dt.datetime.fromtimestamp(stat.st_mtime, tz=dt.timezone.utc).replace(microsecond=0).isoformat()
    conn.execute(
        """
        INSERT INTO source_documents(source_type,path,sha256,bytes,mtime_utc,content_status,ingested_at)
        VALUES(?,?,?,?,?,?,?)
        ON CONFLICT(path) DO UPDATE SET
          source_type=excluded.source_type,
          sha256=excluded.sha256,
          bytes=excluded.bytes,
          mtime_utc=excluded.mtime_utc,
          content_status=excluded.content_status,
          ingested_at=excluded.ingested_at
        """,
        (source_type, str(path), sha256_file(path), stat.st_size, mtime, "PRESENT", effective_at),
    )


def ensure_stage(conn: sqlite3.Connection, key: str, order: float, name: str,
                 purpose: str, implementation_status: str) -> None:
    conn.execute(
        """
        INSERT INTO stage_definitions(stage_key,stage_order,name,purpose,category,implementation_status,notes)
        VALUES(?,?,?,?,?,?,?)
        ON CONFLICT(stage_key) DO UPDATE SET
          stage_order=excluded.stage_order,
          name=excluded.name,
          purpose=excluded.purpose,
          category=excluded.category,
          implementation_status=excluded.implementation_status,
          notes=excluded.notes
        """,
        (key, order, name, purpose, "release_engineering", implementation_status,
         "Post-Freeze release-engineering checkpoint; does not alter frozen Core semantics."),
    )


def add_run_stage(conn: sqlite3.Connection, run_id: str, stage_key: str,
                  attempt: str, status: str, evidence: str, notes: str,
                  effective_at: str) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO run_stages(
          run_id,stage_key,implementation_id,attempt_tag,status,command_text,
          qc_path,qc_status,started_at,ended_at,notes
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
        """,
        (run_id, stage_key, None, attempt, status, None, evidence,
         status if status == "PASS" else None, None, effective_at, notes),
    )


def decision_id(key: str) -> str:
    return "decision_" + hashlib.sha256((VERSION + "|" + key).encode()).hexdigest()[:20]


def add_decision(conn: sqlite3.Connection, key: str, category: str, title: str,
                 statement: str, confidence: str, rationale: str,
                 evidence: str, effective_at: str) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO decisions(
          decision_id,decision_key,category,title,statement,status,confidence,
          effective_at,supersedes_decision_id,rationale,evidence_path
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
        """,
        (decision_id(key), key, category, title, statement, "ACTIVE", confidence,
         effective_at, None, rationale, evidence),
    )


def add_limitation(conn: sqlite3.Connection, key: str, statement: str,
                   severity: str, mitigation: str, evidence: str,
                   effective_at: str) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO limitations(
          limitation_key,statement,severity,status,mitigation,evidence_path,effective_at
        ) VALUES(?,?,?,?,?,?,?)
        """,
        (key, statement, severity, "ACTIVE", mitigation, evidence, effective_at),
    )


def add_question(conn: sqlite3.Connection, key: str, question: str, priority: str,
                 blocking: int, next_action: str, evidence: str,
                 effective_at: str) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO open_questions(
          question_key,question,priority,status,blocking,next_action,evidence_path,effective_at
        ) VALUES(?,?,?,?,?,?,?,?)
        """,
        (key, question, priority, "OPEN", blocking, next_action, evidence, effective_at),
    )


def add_metric(conn: sqlite3.Connection, run_id: str, stage_key: str,
               name: str, value: str, source: str, effective_at: str) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO metrics(
          run_id,stage_key,metric_name,value_text,value_num,unit,denominator_num,
          source_path,metric_status,recorded_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?)
        """,
        (run_id, stage_key, name, value, None, None, None, source, "CURRENT", effective_at),
    )


def check_expected_schema(conn: sqlite3.Connection) -> None:
    required = {
        "source_documents", "runs", "stage_definitions", "run_stages", "metrics",
        "decisions", "limitations", "open_questions",
    }
    observed = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    missing = sorted(required - observed)
    if missing:
        raise CheckpointError(f"SSOT schema missing required tables: {missing}")


def apply_checkpoint(conn: sqlite3.Connection, root: Path, evidence: dict[str, Path],
                     effective_at: str) -> dict[str, Any]:
    run_id = "RNA_TR_SCOUT_STAGE16_RELEASE_ENGINEERING"
    conn.execute(
        """
        INSERT INTO runs(run_id,dataset_id,parent_run_id,run_role,pipeline_version,status,
                         started_at,ended_at,root_path,notes)
        VALUES(?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(run_id) DO UPDATE SET
          pipeline_version=excluded.pipeline_version,
          status=excluded.status,
          ended_at=excluded.ended_at,
          root_path=excluded.root_path,
          notes=excluded.notes
        """,
        (run_id, None, None, "release_engineering", "post-freeze-stage16", "IN_PROGRESS",
         "2026-08-13T00:00:00+00:00", None, str(root),
         "Post-Freeze release engineering; frozen scientific Core remains immutable."),
    )

    for path, source_type in [
        (evidence["stage16s"], "stage16s_cross_hardware_record"),
        (evidence["stage16t"], "stage16t_documentation_review"),
        (evidence["readme"], "researcher_facing_readme"),
        (evidence["public_workflow"], "public_cli_implementation"),
        (evidence["mapping_contract"], "ont_cdna_mapping_contract"),
        (evidence["resource_manifest"], "frozen_core_resource_manifest"),
        (evidence["resource_profile"], "standard_resource_profile"),
        (evidence["caller_adapter"], "production_caller_adapter"),
        (evidence["motif_builder"], "motif_job_builder"),
    ]:
        source_document(conn, path, source_type, effective_at)

    ensure_stage(conn, "16Q_PUBLIC_CLI_INTEGRATION", 166.0,
                 "Stage16Q public CLI integration",
                 "Expose resources-status, mapping, FASTQ-to-final and BAM+FASTQ user workflows while delegating scientific execution to the frozen production path.",
                 "IMPLEMENTED_VALIDATED")
    ensure_stage(conn, "16R_FRESH_END_TO_END", 168.0,
                 "Stage16R fresh end-to-end validation",
                 "Validate fresh clone + fresh environment + fresh resource setup + public CLI from 100k FASTQ through mapping, BAM, frozen Core and final five tables.",
                 "EVIDENCE_BINDING_PENDING")
    ensure_stage(conn, "16S_CROSS_HARDWARE_PARITY", 169.0,
                 "Stage16S cross-hardware parity",
                 "Reproduce frozen-Core scientific output and restart behavior on a second Linux x86-64 machine.",
                 "VALIDATED_WITH_SCOPE")
    ensure_stage(conn, "16T_USER_FACING_DOCUMENTATION", 170.0,
                 "Stage16T user-facing documentation",
                 "Prepare and owner-review researcher-facing README and user guide while retaining detailed audit records separately.",
                 "VALIDATED")
    ensure_stage(conn, "16U_SSOT_PROGRESS_CHECKPOINT", 171.0,
                 "Stage16U SSOT release-progress checkpoint",
                 "Reconcile post-Freeze release-engineering state across Git, validation records and the SSOT database without changing frozen Core contracts.",
                 "VALIDATED_WITH_SCOPE")

    add_run_stage(conn, run_id, "16Q_PUBLIC_CLI_INTEGRATION", "v0.1.0", "PASS",
                  "git:2191352170afe284c88cccd92c192efda2465b09",
                  "Public CLI integration is present in main ancestry; Stage16Q commit explicitly preserves frozen Core.", effective_at)
    add_run_stage(conn, run_id, "16R_FRESH_END_TO_END", "v0.1.0", "EVIDENCE_BINDING_PENDING",
                  "", "Stage16R PASS is not registered because an authoritative formal result artifact is not yet bound into the repository/SSOT checkpoint.", effective_at)
    add_run_stage(conn, run_id, "16S_CROSS_HARDWARE_PARITY", "v0.1.1", "PASS",
                  str(evidence["stage16s"]),
                  "Exact five-table scientific parity and SECOND_RESUME_NOOP reproduced on second Linux x86-64 PC; validator expected-SHA transcription error corrected in v0.1.1.", effective_at)
    add_run_stage(conn, run_id, "16T_USER_FACING_DOCUMENTATION", "v0.1.0", "PASS",
                  str(evidence["stage16t"]),
                  "Owner review accepted and documentation integrated into main.", effective_at)
    add_run_stage(conn, run_id, "16U_SSOT_PROGRESS_CHECKPOINT", "v0.1.0", "PASS",
                  str(Path(__file__).resolve()),
                  "Post-Freeze release-engineering progress reconciled; Stage16R remains evidence-binding pending.", effective_at)

    # Supersede statements that are no longer current after Stage16S/T.
    conn.execute("UPDATE decisions SET status='SUPERSEDED' WHERE decision_key IN (?,?) AND status='ACTIVE'",
                 ("stage15e_cross_hardware_not_closed_v0_1_0", "internal_beta_release_readiness_g25_g30_v0_1_0"))
    conn.execute("UPDATE limitations SET status='SUPERSEDED' WHERE limitation_key IN (?,?,?) AND status='ACTIVE'",
                 ("GENERIC_ACTIVE_PATH_NOT_CLEAN_INSTALL_OR_CROSS_HARDWARE",
                  "STAGE15E_SAME_MACHINE_NOT_CROSS_HARDWARE",
                  "LOCAL_CORE_FREEZE_NOT_PUBLIC_GIT_RELEASE"))

    add_decision(conn, "stage16_release_engineering_progress_checkpoint_v0_1_0",
                 "release_readiness", "Register post-Freeze Stage16 release-engineering progress",
                 f"At this checkpoint current main is {EXPECTED_MAIN}; Stage16Q public CLI integration, Stage16S scoped cross-hardware scientific parity, and Stage16T owner-reviewed user documentation are accepted. Stage16R is not asserted PASS until its authoritative fresh end-to-end result artifact is bound. The immutable Core Freeze root remains {FREEZE_ROOT}.",
                 "HIGH",
                 "Git main and Stage16S/T formal records are authoritative and present; the older SSOT snapshot predates Stage16 release engineering.",
                 str(evidence["stage16t"]), effective_at)

    add_decision(conn, "stage16s_cross_hardware_parity_acceptance_v0_1_0",
                 "production_validation", "Accept scoped second-machine scientific parity",
                 "Accept Stage16S v0.1.1 as exact five-table scientific parity for the tested Tier2 input on the tested second Linux x86-64 machine, including native kernel execution and second-resume no-op. Do not generalize this to arbitrary platforms or hardware.",
                 "HIGH", "The formal Stage16S v0.1.1 record distinguishes the corrected validator-side expected-SHA error from scientific output.",
                 str(evidence["stage16s"]), effective_at)

    add_decision(conn, "stage16t_user_facing_documentation_acceptance_v0_1_0",
                 "documentation", "Accept researcher-facing documentation checkpoint",
                 "Accept the Stage16T README and user guide as the current internal pre-release user-facing documentation, with internal Freeze/Stage/golden terminology kept in release records rather than ordinary-user prose.",
                 "HIGH", "Owner visual review was explicitly completed before Stage16T PASS and main integration.",
                 str(evidence["stage16t"]), effective_at)

    add_decision(conn, "public_rc_single_pro_crosscut_audit_required_v0_1_0",
                 "release_governance", "Require one Pro cross-cut audit immediately before public RC",
                 "Before declaring the public v0.5.0 release candidate, perform one Pro-level cross-cut audit of Freeze exact state, current main, active production path, reference/catalog/mapping/CLI/install, golden and validation evidence, cross-hardware results, documentation, unresolved scope, and SSOT/Git/docs state consistency.",
                 "HIGH",
                 "The existing architecture-audit cadence already requires a pre-release-candidate audit; this decision fixes the post-Freeze Stage16 timing and scope while allowing normal High-mode engineering to continue beforehand.",
                 str(evidence["stage16t"]), effective_at)

    add_decision(conn, "caller_complex_strategy_gaps_deferred_from_release_engineering_v0_1_0",
                 "caller_scope", "Keep complex caller coverage gaps separate from release engineering",
                 "VC, IUPAC-degenerate, complex disease-region, >100-bp repeat-unit, no-motif and unsupported-symbol strategies are not all automatically measured by the current production caller. Preserve these as explicit v0.5.0 scope limitations and future caller/biology work; do not change frozen caller semantics during current release engineering.",
                 "HIGH",
                 "The motif-job builder emits specialized strategies while the production caller adapter automatically executes only SIMPLE_PERIODIC_SCAN, MULTI_MOTIF_PERIODIC_SCAN and LONG_UNIT_21_TO_100_PERIODIC_SCAN.",
                 str(evidence["caller_adapter"]), effective_at)

    add_limitation(conn, "PUBLIC_V050_RELEASE_NOT_YET_COMPLETE",
                   "The private repository and user-facing workflow are substantially release-engineered, but the current state is not yet the public RNA-TR-Scout v0.5.0 release candidate or final release.",
                   "HIGH",
                   "Complete remaining public resource distribution, full-network fresh-install/RC validation, storage benchmarking where needed, and the final Pro cross-cut audit before public release claims.",
                   str(evidence["stage16t"]), effective_at)

    add_limitation(conn, "PUBLIC_CATALOG_BUNDLE_URL_PENDING",
                   "The compact validated RNA-TR-Scout catalog bundle does not yet have a finalized automatic public download URL.",
                   "HIGH",
                   "Finalize a stable public hosting location and bind the distributed bundle by the validated SHA-256 before public RC.",
                   str(evidence["resource_profile"]), effective_at)

    add_limitation(conn, "FULL_NETWORK_FRESH_INSTALL_RC_PENDING",
                   "The final public-RC validation still needs a fresh install that exercises the intended public network resource acquisition path rather than relying on already-available large reference source files.",
                   "HIGH",
                   "Run the final fresh-clone/fresh-environment/fresh-resource-install workflow with public acquisition paths after catalog hosting is fixed.",
                   str(evidence["resource_profile"]), effective_at)

    add_limitation(conn, "FULLSCALE_PEAK_DISK_USAGE_NOT_FORMALLY_BENCHMARKED",
                   "A 5.31-million-read restart audit observed approximately 140 GB of checkpoint/work files at one stage, but true peak disk usage has not yet been formally measured.",
                   "MODERATE",
                   "Measure peak disk usage in a full-scale release-engineering run before publishing a fixed large-run storage recommendation; do not present 300 GB as a measured requirement.",
                   str(evidence["stage16t"]), effective_at)

    add_limitation(conn, "CALLER_AUTOMATIC_STRATEGY_COVERAGE_GAPS",
                   "The production caller adapter automatically executes SIMPLE_PERIODIC_SCAN, MULTI_MOTIF_PERIODIC_SCAN and LONG_UNIT_21_TO_100_PERIODIC_SCAN. Specialized motif-job strategies including VARIATION_CLUSTER_MULTI_MOTIF_SEQUENCE_SCAN, IUPAC_PERIODIC_SCAN, COMPLEX_DISEASE_REGION_SEQUENCE_REVIEW, LONG_UNIT_GT100_SEQUENCE_REVIEW, NO_MOTIF_MANUAL_REVIEW and UNSUPPORTED_SYMBOL_MANUAL_REVIEW are not all automatically converted into final repeat measurements.",
                   "HIGH",
                   "Retain candidate/projection evidence and explicit not-attempted states, avoid interpreting unmeasured rows as repeat absence, state this limitation in v0.5.0 scope, and address specialized strategies after release engineering without changing the frozen Core contract.",
                   str(evidence["caller_adapter"]), effective_at)

    add_question(conn, "STAGE16R_AUTHORITATIVE_EVIDENCE_BINDING",
                 "Where is the authoritative Stage16R fresh clone + fresh environment + fresh resource setup + 100k FASTQ-to-final result artifact, and does it formally establish PASS for the exact intended scope?",
                 "HIGH", 1,
                 "Locate and hash the formal Stage16R result artifact, adjudicate it from the original evidence, then register PASS only if supported. Do not infer PASS from conversation summaries.",
                 "git:2191352170afe284c88cccd92c192efda2465b09", effective_at)

    add_question(conn, "PUBLIC_RC_PRO_CROSSCUT_AUDIT",
                 "Does the complete post-Freeze release-engineering state pass a final Pro-level cross-cut audit without Freeze drift, obsolete active paths, implementation-state inflation, release-claim overreach, or SSOT/Git/docs state drift?",
                 "CRITICAL", 1,
                 "Run once immediately before public RC after remaining High-mode release-engineering tasks stabilize.",
                 str(evidence["stage16t"]), effective_at)

    add_question(conn, "PUBLIC_CATALOG_BUNDLE_HOSTING",
                 "What stable public location will distribute the compact validated catalog bundle with exact SHA binding?",
                 "HIGH", 1,
                 "Finalize hosting and update the standard resource profile/public acquisition path before public RC.",
                 str(evidence["resource_profile"]), effective_at)

    add_question(conn, "FULL_NETWORK_FRESH_INSTALL_RC",
                 "Can a fresh clone on a clean supported machine acquire the intended public resources over the network and run the public FASTQ-to-final workflow successfully?",
                 "HIGH", 1,
                 "Execute the final network fresh-install validation after catalog hosting is finalized.",
                 str(evidence["resource_profile"]), effective_at)

    add_question(conn, "FULLSCALE_PEAK_DISK_BENCHMARK",
                 "What is the measured peak disk usage of a representative approximately five-million-read release workflow?",
                 "MODERATE", 0,
                 "Instrument a full-scale run and record peak working-set disk usage before publishing a fixed storage recommendation.",
                 str(evidence["stage16t"]), effective_at)

    add_metric(conn, run_id, "16U_SSOT_PROGRESS_CHECKPOINT", "current_main_commit",
               EXPECTED_MAIN, str(evidence["stage16t"]), effective_at)
    add_metric(conn, run_id, "16U_SSOT_PROGRESS_CHECKPOINT", "immutable_core_freeze_root",
               FREEZE_ROOT, str(evidence["resource_manifest"]), effective_at)
    add_metric(conn, run_id, "16U_SSOT_PROGRESS_CHECKPOINT", "stage16s_cross_hardware_status",
               "PASS_WITH_TESTED_SCOPE", str(evidence["stage16s"]), effective_at)
    add_metric(conn, run_id, "16U_SSOT_PROGRESS_CHECKPOINT", "stage16t_documentation_status",
               "PASS_OWNER_REVIEW_ACCEPTED", str(evidence["stage16t"]), effective_at)
    add_metric(conn, run_id, "16U_SSOT_PROGRESS_CHECKPOINT", "stage16r_evidence_binding_status",
               "PENDING", "git:2191352170afe284c88cccd92c192efda2465b09", effective_at)

    return {
        "run_id": run_id,
        "stage16q": "PASS",
        "stage16r": "EVIDENCE_BINDING_PENDING",
        "stage16s": "PASS_WITH_TESTED_SCOPE",
        "stage16t": "PASS_OWNER_REVIEW_ACCEPTED",
        "current_main": EXPECTED_MAIN,
        "freeze_root": FREEZE_ROOT,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Register the post-Freeze Stage16 release-engineering progress checkpoint in the RNA-TR-Scout SSOT database.")
    ap.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    ap.add_argument("--execute", action="store_true", help="Apply the transactional database update and regenerate SSOT exports. Without this flag, perform preflight only.")
    args = ap.parse_args()

    root = args.project_root.resolve()
    if not root.is_dir():
        raise CheckpointError(f"project root missing: {root}")
    if git_status(root):
        raise CheckpointError("working tree must be clean before Stage16U SSOT checkpoint")

    head = git_head(root)
    if head != EXPECTED_MAIN:
        raise CheckpointError(f"expected current main {EXPECTED_MAIN}, observed {head}; pull/checkout exact main before running")
    if not git_is_ancestor(root, FREEZE_ROOT, head):
        raise CheckpointError("immutable Core Freeze root is not an ancestor of current HEAD")

    ssot_root = root / "metadata/ssot"
    db = ensure_file(ssot_root / "rnatr_ssot.sqlite", "SSOT database")
    ssot_py = ensure_file(ssot_root / "rnatr_ssot.py", "SSOT implementation")

    evidence = {
        "stage16s": ensure_file(root / "docs/release/STAGE16S_CROSS_HARDWARE_PARITY_v0.1.1.md", "Stage16S record"),
        "stage16t": ensure_file(root / "docs/release/STAGE16T_USER_FACING_DOCUMENTATION_REVIEW_v0.1.0.md", "Stage16T record"),
        "readme": ensure_file(root / "README.md", "README"),
        "public_workflow": ensure_file(root / "src/rnatr_scout/public_workflow.py", "public workflow"),
        "mapping_contract": ensure_file(root / "docs/release/MAPPING_CONTRACT_ONT_CDNA_v0.1.0.md", "mapping contract"),
        "resource_manifest": ensure_file(root / "config/core_runtime/v0.1.0/resource_manifest.json", "Core resource manifest"),
        "resource_profile": ensure_file(root / "config/resources/standard_v0.1.1/validated_profile.json", "standard resource profile"),
        "caller_adapter": ensure_file(root / "scripts/rnatr_stage15a_native_v041_runid_adapter_v0.2.1.py", "production caller adapter"),
        "motif_builder": ensure_file(root / "scripts/rnatr_stage15a_fast_motif_jobs_scaling_v0.2.2.2.py", "motif builder"),
    }

    pre_sha = sha256_file(db)
    with sqlite3.connect(str(db)) as pre:
        check_expected_schema(pre)
        integrity = pre.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise CheckpointError(f"pre-update sqlite integrity failed: {integrity}")

    print("===== RNA-TR-SCOUT STAGE16U SSOT PROGRESS CHECKPOINT PREFLIGHT =====")
    print(f"version\t{VERSION}")
    print(f"project_root\t{root}")
    print(f"head\t{head}")
    print(f"freeze_root\t{FREEZE_ROOT}")
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
    checkpoint_root = ssot_root / "checkpoints" / "stage16u_release_progress_v0.1.0" / effective_at.replace(":", "").replace("+00:00", "Z")
    checkpoint_root.mkdir(parents=True, exist_ok=False)
    backup = checkpoint_root / "rnatr_ssot.pre_stage16u.sqlite"
    shutil.copy2(db, backup)
    backup_sha = sha256_file(backup)
    if backup_sha != pre_sha:
        raise CheckpointError("database backup SHA differs from pre-update database")

    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        conn.execute("BEGIN IMMEDIATE")
        check_expected_schema(conn)
        state = apply_checkpoint(conn, root, evidence, effective_at)
        conn.commit()

        ssot_mod = load_ssot_module(ssot_py)
        checks = ssot_mod.validate_db(conn, root)
        failed = [row for row in checks if row[1] == "FAIL"]
        if failed:
            raise CheckpointError(f"post-update SSOT validation failed: {failed}")
        exports = ssot_mod.export_views(conn, ssot_root)
        summary_path = ssot_mod.write_summary(conn, ssot_root, checks, exports)
    except Exception:
        conn.close()
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
        "status": "PASS_WITH_STAGE16R_EVIDENCE_BINDING_PENDING",
        "effective_at": effective_at,
        "project_root": str(root),
        "current_main": EXPECTED_MAIN,
        "freeze_root": FREEZE_ROOT,
        "ssot_db": str(db),
        "ssot_db_pre_sha256": pre_sha,
        "ssot_db_post_sha256": post_sha,
        "backup": str(backup),
        "backup_sha256": backup_sha,
        "summary": str(summary_path),
        "state": state,
        "evidence_sha256": {k: sha256_file(v) for k, v in evidence.items()},
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
    print("review_git_diff\tgit diff -- metadata/ssot/CURRENT_STATE.md metadata/ssot/exports")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
