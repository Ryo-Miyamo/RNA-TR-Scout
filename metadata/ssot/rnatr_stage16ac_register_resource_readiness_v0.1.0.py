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
import tarfile
import tempfile

VERSION = "rnatr_stage16ac_register_resource_readiness_v0.1.0"
FREEZE_ROOT = "4b1981db955a8aa92a2a01e19bbb1cfc2aa0ebfb"
STAGE16Z_SOURCE = "b8705454aaf73a6f0364b12f6e95b7d5cb995fc2"
RUN_ID = "RNA_TR_SCOUT_STAGE16_RELEASE_ENGINEERING"

DEFAULT_REPO_ROOT = Path("/mnt/intelssd/rnatr_git_stage/LOCAL_CORE_FREEZE_V0.1.0_git_snapshot_v0.1.2")
DEFAULT_PROJECT_ROOT = Path("/mnt/intelssd/rnatr_project")
DEFAULT_BUNDLE = Path.home() / "Downloads/rnatr_stage16zaa_release_readiness_evidence_v0.1.0.tar.gz"

BUNDLE_SHA = "559f8f78b65ea1edb871e7783cc859e71a97249cccf5a93925b42e8e6601a6b8"
MEMBERS = {
    "rnatr_stage16z_resource_planner_preflight_v0.1.0.json": "b85bd0ca8addd88f2d5fd68f8ee49a5765bfe1a4d1eb6c6adbce410f85bf85cb",
    "rnatr_stage16z_tier3_auto_parity_validation_v0.1.0_20260817T045332Z.json": "b1c166f60ed5ae9266d5cccc5dac573e09865d67ea50b0b0c52af411981ce02a",
    "rnatr_stage16aa_independent_machine_fresh_validation_v0.1.0_20260817T041347Z.json": "38ba94527d42bb08e13e600ea7c41ef4768c1571a70b6d1c7e50ab9f82a544f1",
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


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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


def load_ssot(path: Path):
    spec = importlib.util.spec_from_file_location("rnatr_ssot_stage16ac", path)
    if spec is None or spec.loader is None:
        raise RegisterError(f"cannot import SSOT module: {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def ensure_regular(path: Path, label: str) -> Path:
    if not path.is_file() or path.is_symlink():
        raise RegisterError(f"{label} missing/invalid regular file: {path}")
    return path


def verify_bundle(path: Path) -> dict[str, tuple[bytes, dict]]:
    ensure_regular(path, "Stage16Z/AA evidence bundle")
    observed = sha256_file(path)
    if observed != BUNDLE_SHA:
        raise RegisterError(f"evidence bundle SHA mismatch: {observed} != {BUNDLE_SHA}")

    out: dict[str, tuple[bytes, dict]] = {}
    with tarfile.open(path, "r:gz") as tf:
        members = tf.getmembers()
        names = {m.name for m in members}
        if names != set(MEMBERS):
            raise RegisterError(f"unexpected evidence bundle members: {sorted(names)}")
        for member in members:
            if not member.isfile() or member.name.startswith("/") or ".." in Path(member.name).parts:
                raise RegisterError(f"unsafe evidence member: {member.name}")
            fh = tf.extractfile(member)
            if fh is None:
                raise RegisterError(f"cannot read evidence member: {member.name}")
            data = fh.read()
            digest = sha256_bytes(data)
            if digest != MEMBERS[member.name]:
                raise RegisterError(f"evidence member SHA mismatch: {member.name}: {digest}")
            try:
                obj = json.loads(data.decode("utf-8"))
            except Exception as exc:
                raise RegisterError(f"invalid JSON evidence member: {member.name}") from exc
            out[member.name] = (data, obj)
    return out


def verify_payloads(items: dict[str, tuple[bytes, dict]]) -> tuple[dict, dict, dict]:
    pre = items["rnatr_stage16z_resource_planner_preflight_v0.1.0.json"][1]
    tier3 = items["rnatr_stage16z_tier3_auto_parity_validation_v0.1.0_20260817T045332Z.json"][1]
    aa = items["rnatr_stage16aa_independent_machine_fresh_validation_v0.1.0_20260817T041347Z.json"][1]

    if pre.get("status") != "PASS_STAGE16Z_STATIC_AND_POLICY_PREFLIGHT":
        raise RegisterError("Stage16Z preflight status mismatch")
    if pre.get("git_head") != STAGE16Z_SOURCE:
        raise RegisterError("Stage16Z preflight source mismatch")
    profiles = pre.get("auto_profiles", {})
    expected_profiles = {
        "tier2": (1, 1, 2),
        "tier3": (12, 3, 2),
        "500k": (12, 12, 2),
        "full5312696": (144, 12, 2),
    }
    for key, values in expected_profiles.items():
        p = profiles.get(key, {})
        observed = (p.get("shards"), p.get("max_unit_workers"), p.get("caller_workers"))
        if observed != values:
            raise RegisterError(f"Stage16Z preflight profile mismatch {key}: {observed} != {values}")

    expected_tier3 = {
        "status": "PASS_STAGE16Z_TIER3_AUTO_RESOURCE_EXACT_PARITY",
        "source_head": STAGE16Z_SOURCE,
        "freeze_root": FREEZE_ROOT,
        "auto_profile_exact": True,
        "final_exact_plain_table_parity": "PASS_5_OF_5",
        "public_resume": "PASS_SECOND_RESUME_NOOP",
        "mapping_rerun_on_resume": False,
        "post_resume_final_parity": "PASS_5_OF_5",
        "source_git_clean_after_validation": True,
    }
    for key, value in expected_tier3.items():
        if tier3.get(key) != value:
            raise RegisterError(f"Stage16Z Tier3 field mismatch: {key}={tier3.get(key)!r}")
    plan = tier3.get("resource_plan", {})
    if (plan.get("shards"), plan.get("max_unit_workers"), plan.get("caller_workers")) != (12, 3, 2):
        raise RegisterError("Stage16Z Tier3 resource plan mismatch")
    if plan.get("mode") != "AUTO" or plan.get("policy_version") != "rnatr_resource_policy_v0.1.0":
        raise RegisterError("Stage16Z Tier3 policy identity mismatch")

    expected_aa = {
        "status": "PASS_INDEPENDENT_MACHINE_FRESH_INSTALL_RESOURCE_AUTO_TIER2_PARITY",
        "hostname": "deeplearningboxii",
        "source_head": STAGE16Z_SOURCE,
        "freeze_root": FREEZE_ROOT,
        "fresh_environment": True,
        "fresh_network_resource_install": True,
        "final_exact_plain_table_parity": "PASS_5_OF_5",
        "public_resume": "PASS_SECOND_RESUME_NOOP",
        "post_resume_final_parity": "PASS_5_OF_5",
        "fresh_clone_git_clean_after_validation": True,
    }
    for key, value in expected_aa.items():
        if aa.get(key) != value:
            raise RegisterError(f"Stage16AA field mismatch: {key}={aa.get(key)!r}")
    rp = aa.get("resource_auto_plan", {})
    if (rp.get("shards"), rp.get("max_unit_workers"), rp.get("caller_workers")) != (1, 1, 2):
        raise RegisterError("Stage16AA Tier2 resource plan mismatch")
    ri = aa.get("resource_install_manifest", {})
    for key in ("reference_source_fasta", "reference_source_gtf", "catalog_source"):
        if ri.get(key) != "PASS_DOWNLOADED_EXACT":
            raise RegisterError(f"Stage16AA network resource status mismatch: {key}")
    if ri.get("status") != "PASS_STANDARD_RESOURCES_READY":
        raise RegisterError("Stage16AA standard-resource status mismatch")

    return pre, tier3, aa


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
                         statement: str, rationale: str, evidence: str,
                         effective_at: str) -> None:
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


def add_or_update_limitation(conn: sqlite3.Connection, key: str, statement: str,
                             severity: str, mitigation: str, evidence: str,
                             effective_at: str) -> None:
    conn.execute(
        """INSERT INTO limitations(limitation_key,statement,severity,status,mitigation,evidence_path,effective_at)
           VALUES(?,?,?,?,?,?,?)
           ON CONFLICT(limitation_key) DO UPDATE SET statement=excluded.statement,
             severity=excluded.severity,status=excluded.status,mitigation=excluded.mitigation,
             evidence_path=excluded.evidence_path,effective_at=excluded.effective_at""",
        (key, statement, severity, "ACTIVE", mitigation, evidence, effective_at),
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Register Stage16Z/AA resource and independent-machine release-readiness evidence into the canonical RNA-TR-Scout SSOT.")
    ap.add_argument("--repo-root", type=Path, default=DEFAULT_REPO_ROOT)
    ap.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    ap.add_argument("--evidence-bundle", type=Path, default=DEFAULT_BUNDLE)
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    repo_root = args.repo_root.resolve()
    project_root = args.project_root.resolve()
    bundle = args.evidence_bundle.expanduser().resolve()

    if git_status(repo_root):
        raise RegisterError("Git working tree must be clean before Stage16AC")
    head = git_head(repo_root)
    if not git_is_ancestor(repo_root, STAGE16Z_SOURCE, head):
        raise RegisterError(f"repo HEAD {head} does not descend from Stage16Z source {STAGE16Z_SOURCE}")
    if not git_is_ancestor(repo_root, FREEZE_ROOT, head):
        raise RegisterError("Freeze root is not an ancestor of repo HEAD")

    items = verify_bundle(bundle)
    pre, tier3, aa = verify_payloads(items)

    ssot_root = project_root / "metadata/ssot"
    db = ensure_regular(ssot_root / "rnatr_ssot.sqlite", "canonical SSOT database")
    ssot_py = ensure_regular(ssot_root / "rnatr_ssot.py", "canonical SSOT implementation")

    with sqlite3.connect(str(db)) as conn:
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or list(conn.execute("PRAGMA foreign_key_check")):
            raise RegisterError("canonical SSOT failed preflight integrity/foreign-key check")
        q = conn.execute("SELECT status FROM open_questions WHERE question_key='CLEAN_INSTALL_INTERNAL_BETA'").fetchone()
        if not q or q[0] not in {"OPEN", "CLOSED"}:
            raise RegisterError(f"unexpected CLEAN_INSTALL_INTERNAL_BETA state: {q}")

    print("===== RNA-TR-SCOUT STAGE16AC PREFLIGHT =====")
    print(f"version\t{VERSION}")
    print(f"repo_head\t{head}")
    print(f"bundle_sha256\t{BUNDLE_SHA}")
    print(f"stage16z_preflight\t{pre['status']}")
    print(f"stage16z_tier3\t{tier3['status']}")
    print(f"stage16aa\t{aa['status']}")
    print("g25_g29\tREADY_FOR_PASS_REGISTRATION")
    print("g30\tREADY_FOR_PASS_WITH_SCOPE_REGISTRATION")
    if not args.execute:
        print("status\tPREFLIGHT_PASS_READY_FOR_EXECUTE")
        return 0

    durable_root = ssot_root / "checkpoints/stage16ac_resource_readiness_v0.1.0" / f"sha256_{MEMBERS['rnatr_stage16aa_independent_machine_fresh_validation_v0.1.0_20260817T041347Z.json']}"
    originals = durable_root / "originals"
    originals.mkdir(parents=True, exist_ok=True)

    bundle_copy = originals / bundle.name
    if bundle_copy.exists():
        if sha256_file(bundle_copy) != BUNDLE_SHA:
            raise RegisterError("existing durable evidence bundle differs")
    else:
        shutil.copy2(bundle, bundle_copy)
    if sha256_file(bundle_copy) != BUNDLE_SHA:
        raise RegisterError("durable evidence bundle copy SHA mismatch")

    durable_members: dict[str, Path] = {}
    for name, (data, _obj) in items.items():
        dst = originals / name
        if dst.exists():
            if sha256_file(dst) != MEMBERS[name]:
                raise RegisterError(f"existing durable member differs: {dst}")
        else:
            dst.write_bytes(data)
        if sha256_file(dst) != MEMBERS[name]:
            raise RegisterError(f"durable member SHA mismatch: {dst}")
        durable_members[name] = dst

    evidence_aa = str(durable_members["rnatr_stage16aa_independent_machine_fresh_validation_v0.1.0_20260817T041347Z.json"])
    evidence_tier3 = str(durable_members["rnatr_stage16z_tier3_auto_parity_validation_v0.1.0_20260817T045332Z.json"])
    evidence_pre = str(durable_members["rnatr_stage16z_resource_planner_preflight_v0.1.0.json"])
    adjudication = repo_root / "docs/release/STAGE16AB_G25_G30_RELEASE_READINESS_ADJUDICATION_v0.1.0.md"
    hardware_doc = repo_root / "docs/release/HARDWARE_PROFILE_v0.1.0.md"
    stage16z_doc = repo_root / "docs/release/STAGE16Z_RESOURCE_AWARE_PUBLIC_CLI_v0.1.0.md"
    stage16aa_doc = repo_root / "docs/release/STAGE16AA_INDEPENDENT_MACHINE_FRESH_VALIDATION_v0.1.0.md"
    for p in (adjudication, hardware_doc, stage16z_doc, stage16aa_doc):
        ensure_regular(p, "formal release record")

    effective_at = now_utc()
    backup_dir = durable_root / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    pre_sha = sha256_file(db)
    backup = backup_dir / f"rnatr_ssot.pre_stage16ac.{effective_at.replace(':','').replace('+00:00','Z')}.sqlite"
    shutil.copy2(db, backup)
    if sha256_file(backup) != pre_sha:
        raise RegisterError("SSOT backup SHA mismatch")

    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        conn.execute("BEGIN IMMEDIATE")
        source_document(conn, bundle_copy, "stage16zaa_release_readiness_evidence_bundle", effective_at)
        source_document(conn, Path(evidence_pre), "stage16z_resource_planner_preflight", effective_at)
        source_document(conn, Path(evidence_tier3), "stage16z_tier3_auto_parity_result", effective_at)
        source_document(conn, Path(evidence_aa), "stage16aa_independent_machine_result", effective_at)
        for p, typ in ((adjudication, "stage16ab_g25_g30_adjudication"),
                       (hardware_doc, "hardware_profile"),
                       (stage16z_doc, "stage16z_formal_record"),
                       (stage16aa_doc, "stage16aa_formal_record")):
            source_document(conn, p, typ, effective_at)

        ensure_stage(conn, "16Z_RESOURCE_AWARE_PUBLIC_CLI", 174.0,
                     "Stage16Z resource-aware public CLI",
                     "Detect CPU/RAM/tmp/free-space state and automatically select conservative Core scheduling while preserving frozen scientific semantics.",
                     "VALIDATED_WITH_SCOPE",
                     "PASS_WITH_SCOPE: Tier2 and Tier3 automatic execution retained exact golden parity; mapping-thread tuning and peak-disk minimum remain separate scopes.")
        ensure_stage(conn, "16AA_INDEPENDENT_MACHINE_FRESH_VALIDATION", 175.0,
                     "Stage16AA independent-machine fresh validation",
                     "Validate fresh clone, fresh environment, network resources, resource auto-selection, exact scientific output and resume on the second Linux x86-64 host.",
                     "VALIDATED_WITH_SCOPE",
                     "PASS on deeplearningboxii for the exact Tier2 fixture and current Linux x86-64 ONT-cDNA release scope.")
        ensure_stage(conn, "16AB_G25_G30_RELEASE_READINESS", 176.0,
                     "Stage16AB G25-G30 release-readiness adjudication",
                     "Reconcile G25-G30 against current post-Freeze implementation/evidence and define the hardware-profile scope honestly.",
                     "VALIDATED_WITH_SCOPE",
                     "G25-G29 PASS; G30 PASS_WITH_SCOPE because tested/recommended profiles are established while empirical minimum remains unmeasured and nonblocking.")

        add_run_stage(conn, "16Z_RESOURCE_AWARE_PUBLIC_CLI", "v0.1.0", evidence_tier3,
                      "Resource-aware Core scheduling validated by static/policy tests, Tier3 100k automatic 12/3/2 execution with exact 5/5 parity, and independent-machine Tier2 automatic execution.", effective_at)
        add_run_stage(conn, "16AA_INDEPENDENT_MACHINE_FRESH_VALIDATION", "v0.1.0", evidence_aa,
                      "Independent second machine completed fresh private-GitHub clone, fresh environment, exact network resources, automatic Tier2 Core plan, exact 5/5 parity and SECOND_RESUME_NOOP.", effective_at)
        add_run_stage(conn, "16AB_G25_G30_RELEASE_READINESS", "v0.1.0", str(adjudication),
                      "G25-G29 accepted; G30 documented as tested/recommended complete with empirical minimum unresolved nonblocking; CLEAN_INSTALL_INTERNAL_BETA closed for current tested scope.", effective_at)

        q = conn.execute("SELECT status FROM open_questions WHERE question_key='CLEAN_INSTALL_INTERNAL_BETA'").fetchone()
        if q and q[0] == "OPEN":
            conn.execute(
                "UPDATE open_questions SET status='CLOSED',next_action=?,evidence_path=?,effective_at=? WHERE question_key='CLEAN_INSTALL_INTERNAL_BETA'",
                ("CLOSED: Stage16AA independently reproduced fresh clone/environment/network resources, resource auto-selection, exact Tier2 output and resume on deeplearningboxii; G25-G29 are accepted and G30 is documented with a scoped empirical-minimum amendment.", evidence_aa, effective_at),
            )

        superseding_decision(conn, "stage16_release_engineering_progress_checkpoint_v0_1_0",
                             "release_readiness", "Register post-Freeze Stage16 release-engineering progress",
                             f"Current release engineering now includes public catalog/network-install closure plus Stage16Z resource-aware Core scheduling and Stage16AA independent-machine fresh validation. G25-G29 are accepted. G30 has tested and recommended hardware profiles documented while the empirical minimum remains explicitly unmeasured and nonblocking. CLEAN_INSTALL_INTERNAL_BETA is closed for the current Linux x86-64 ONT-cDNA scope. The immutable Core Freeze root remains {FREEZE_ROOT}.",
                             "Stage16Z Tier3 and Stage16AA Tier2 results retain exact frozen scientific-table identities under automatic scheduling; the second host also completed fresh environment and network-resource setup.", evidence_aa, effective_at)
        superseding_decision(conn, "stage16z_resource_aware_public_cli_acceptance_v0_1_0",
                             "release_readiness", "Accept Stage16Z resource-aware public CLI",
                             "Accept resource detection and automatic Core scheduling for the current Linux x86-64 release scope. Tier2 and Tier3 automatic profiles retain exact scientific parity; resume reuses the recorded plan. Mapping-thread tuning and full-scale peak disk remain separate scopes.",
                             "Static policy tests, primary-host Tier3 execution and second-host Tier2 execution satisfy the Stage16Z acceptance contract.", evidence_tier3, effective_at)
        superseding_decision(conn, "stage16aa_independent_machine_acceptance_v0_1_0",
                             "production_validation", "Accept independent-machine fresh-install validation",
                             "Accept Stage16AA as PASS for independent second-host fresh clone, fresh environment, exact network resources, automatic Core resource selection, exact Tier2 five-table parity and second-resume no-op on Linux x86-64.",
                             "The authoritative result binds the second host, exact fixture/resource identities, automatic 1/1/2 plan, 5/5 parity and clean Git state.", evidence_aa, effective_at)
        superseding_decision(conn, "g25_g29_release_readiness_closure_v0_1_0",
                             "release_readiness", "Close G25-G29 for current tested scope",
                             "G25 reference bootstrap, G26 resource detection, G27 memory-aware Core scheduling, G28 scoped cross-hardware reproducibility and G29 clean-machine clone-to-test reproducibility are accepted for the currently tested Linux x86-64 ONT-cDNA release scope.",
                             "Stage16W/X/S/Z/AA collectively provide direct network-install, resource-planning, cross-hardware and independent-machine evidence without changing the frozen Core.", str(adjudication), effective_at)
        superseding_decision(conn, "g30_hardware_profile_pass_with_scope_v0_1_0",
                             "release_readiness", "Record G30 hardware profile with scoped minimum amendment",
                             "G30 is PASS_WITH_SCOPE: tested hardware profiles and a release-scale recommended profile are documented; a lower empirical CPU/RAM minimum is not established and is intentionally not invented. The minimum remains a nonblocking limitation while user-facing documentation preserves this distinction.",
                             "Two tested Linux x86-64 hosts provide 24/36 logical CPUs with approximately 128 GB RAM, while no lower full-scale configuration has been empirically validated.", str(hardware_doc), effective_at)

        add_or_update_limitation(conn, "HARDWARE_EMPIRICAL_MINIMUM_NOT_ESTABLISHED",
                                 "A lower empirical CPU/RAM minimum for the approximately-five-million-read workflow has not been established.",
                                 "MODERATE",
                                 "Publish tested and recommended profiles only; let the resource-aware Core planner reduce concurrency on lower-resource hosts; do not claim an unvalidated full-scale minimum.",
                                 str(hardware_doc), effective_at)

        row = conn.execute("SELECT limitation_key FROM limitations WHERE limitation_key='PUBLIC_V050_RELEASE_NOT_YET_COMPLETE'").fetchone()
        if row:
            conn.execute(
                "UPDATE limitations SET mitigation=?,evidence_path=?,effective_at=? WHERE limitation_key='PUBLIC_V050_RELEASE_NOT_YET_COMPLETE'",
                ("Independent clean-machine/internal-beta validation and resource-aware scheduling are complete. Remaining release work is the dedicated peak-disk benchmark if a fixed storage recommendation is to be published, the final Pro cross-cut audit, and immutable public v0.5.0 release/tag/citation binding.", str(adjudication), effective_at),
            )

        for gate, status in (("G25", "PASS"), ("G26", "PASS_WITH_DEFINED_SCOPE"),
                             ("G27", "PASS_WITH_DEFINED_SCOPE"), ("G28", "PASS_WITH_SCOPE"),
                             ("G29", "PASS"), ("G30", "PASS_WITH_SCOPE_AMENDMENT")):
            add_metric(conn, "16AB_G25_G30_RELEASE_READINESS", f"{gate.lower()}_status", status, str(adjudication), effective_at)
        add_metric(conn, "16AA_INDEPENDENT_MACHINE_FRESH_VALIDATION", "hostname", aa["hostname"], evidence_aa, effective_at)
        add_metric(conn, "16AA_INDEPENDENT_MACHINE_FRESH_VALIDATION", "logical_cpus", str(aa["system_info"]["logical_cpus"]), evidence_aa, effective_at)
        add_metric(conn, "16AA_INDEPENDENT_MACHINE_FRESH_VALIDATION", "memory_total_bytes", str(aa["system_info"]["memory_total_bytes"]), evidence_aa, effective_at)
        add_metric(conn, "16Z_RESOURCE_AWARE_PUBLIC_CLI", "tier3_auto_profile", "12_SHARDS_3_UNITS_2_CALLER_WORKERS", evidence_tier3, effective_at)
        add_metric(conn, "16Z_RESOURCE_AWARE_PUBLIC_CLI", "tier3_exact_parity", "PASS_5_OF_5", evidence_tier3, effective_at)

        conn.commit()
        ssot = load_ssot(ssot_py)
        checks = ssot.validate_db(conn, project_root)
        failed = [row for row in checks if row[1] == "FAIL"]
        if failed:
            raise RegisterError(f"post-Stage16AC SSOT validation failed: {failed}")
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
        "status": "PASS_STAGE16AC_RESOURCE_READINESS_REGISTERED",
        "effective_at": effective_at,
        "repo_head": head,
        "freeze_root": FREEZE_ROOT,
        "evidence_bundle_sha256": BUNDLE_SHA,
        "stage16z_preflight_sha256": MEMBERS["rnatr_stage16z_resource_planner_preflight_v0.1.0.json"],
        "stage16z_tier3_sha256": MEMBERS["rnatr_stage16z_tier3_auto_parity_validation_v0.1.0_20260817T045332Z.json"],
        "stage16aa_sha256": MEMBERS["rnatr_stage16aa_independent_machine_fresh_validation_v0.1.0_20260817T041347Z.json"],
        "gates": {
            "G25": "PASS",
            "G26": "PASS_WITH_DEFINED_SCOPE",
            "G27": "PASS_WITH_DEFINED_SCOPE",
            "G28": "PASS_WITH_SCOPE",
            "G29": "PASS",
            "G30": "PASS_WITH_SCOPE_AMENDMENT_EMPIRICAL_MINIMUM_UNRESOLVED_NONBLOCKING",
        },
        "clean_install_internal_beta": "CLOSED",
        "remaining_release_gates": [
            "PUBLIC_RC_PRO_CROSSCUT_AUDIT",
            "FULLSCALE_PEAK_DISK_BENCHMARK",
            "CORE_FREEZE_GIT_TAG_AND_PUBLIC_RELEASE_BINDING",
        ],
        "ssot_pre_sha256": pre_sha,
        "ssot_post_sha256": post_sha,
        "backup": str(backup),
        "summary": str(summary),
        "human_visual_review_required": False,
    }
    result_path = durable_root / "stage16ac_resource_readiness_registration.result.json"
    tmp = result_path.with_suffix(".json.part")
    tmp.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, result_path)

    print("===== RNA-TR-SCOUT STAGE16AC RESULT =====")
    print("status\tPASS_STAGE16AC_RESOURCE_READINESS_REGISTERED")
    print("g25_g29\tPASS_REGISTERED")
    print("g30\tPASS_WITH_SCOPE_AMENDMENT")
    print("clean_install_internal_beta\tCLOSED")
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
