#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import importlib.util
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any

VERSION = "rnatr_stage16an_register_final_pro_audit_v0.1.0"

REPO = Path(
    "/mnt/intelssd/rnatr_git_stage/"
    "LOCAL_CORE_FREEZE_V0.1.0_git_snapshot_v0.1.2"
)
PROJECT = Path("/mnt/intelssd/rnatr_project")
RELEASE_ROOT = Path("/mnt/intelssd/rnatr_release_engineering")
BRANCH = "stage16ae-public-release-packaging"
EXPECTED_HEAD = "9d660e96e54c796696a28ebe686019d5636bb420"
EXPECTED_TREE = "45833fce5a6d47b1cf706d537fb1777304f3f7b5"
EXPECTED_MAIN = "dc785a1760c34f680d38ddb78e44b59830e2f7de"
FREEZE_ROOT = "4b1981db955a8aa92a2a01e19bbb1cfc2aa0ebfb"
RUN_ID = "RNA_TR_SCOUT_STAGE16_RELEASE_ENGINEERING"

AUDIT_BUNDLE = (
    Path.home()
    / "Downloads/rnatr_stage16an_final_pro_crosscut_audit_evidence_v0.1.0.tar.gz"
)
AUDIT_BUNDLE_SHA256 = (
    "e151959a7271246dc4385fc6c2c72e955bf69ec07d0351410d7ed1bab65009e8"
)
EXPECTED_MEMBERS = {
    "rnatr_stage16al_final_pro_crosscut_audit_evidence_v0.1.0.tar.gz":
        "049f40ef57356742022c57b05c8dae1208c876e9d80ec3d8b387e882198d2f63",
    "rnatr_stage16am_final_pro_metadata_remediation.result.json":
        "3e7dcfb9cbdda75f3b94593de02247b432d63e5c028d4e742cbf4363c6759b7e",
    "rnatr_stage16am_final_pro_metadata_remediation_bundle_2026-08-17T080014+0000.tar.gz":
        "a7290f00e370bc556cbe992f48a5e07ef870ccc3eaa8567724dc8c29d3a95dd0",
    "rnatr_stage16an_final_pro_crosscut_audit_v0.1.0.json":
        "c2ff338d67e6ac1aae7e55da7c8a79a8d79b3d039423b010ab046a4f5bbc04a8",
    "rnatr_stage16an_final_pro_crosscut_audit_v0.1.0.md":
        "696b65340ab4abc2dd95bf811835fdb2434a23ed9432e8555a4c35f17f374707",
}

EXPECTED_PACKAGE_VERSION = "0.5.0rc1"
EXPECTED_CFF_VERSION = "0.5.0-rc1"
EXPECTED_LICENSE_SHA256 = (
    "29c5826ebe617783ca4fbde13b591bf451754db1c23adb2a5f2ac6ba133e31bb"
)
EXPECTED_LOCK_SHA256 = (
    "79004c8253021a6d30b35aecf91a244a1ae1460ccfcd8d77a135716b6235955c"
)
EXPECTED_NATIVE_SHA256 = (
    "9745a4e33e9a899ec78417b499ccc35f770b7fd7adfffe1ab533fa14ead3ae69"
)
EXPECTED_RELEASE_GATES_SHA256 = (
    "f394b17ca51b4dadc45ad6b9806612c4ca35f5602cb7c51c0e25aeb39ed43131"
)

AUDIT_RECORD_REL = Path(
    "docs/release/STAGE16AN_FINAL_PRO_CROSSCUT_AUDIT_v0.1.0.md"
)
REGISTRAR_REL = Path(
    "metadata/ssot/rnatr_stage16an_register_final_pro_audit_v0.1.0.py"
)

SECRET_PATTERNS = {
    "PRIVATE_KEY_BLOCK": re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"
    ),
    "GITHUB_TOKEN": re.compile(
        r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b"
    ),
    "AWS_ACCESS_KEY": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "SLACK_TOKEN": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
}


class AuditRegistrationError(RuntimeError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def run(
    argv: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    p = subprocess.run(
        argv,
        cwd=str(cwd) if cwd else None,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if check and p.returncode != 0:
        raise AuditRegistrationError(
            f"command failed rc={p.returncode}: {' '.join(argv)}\n{p.stdout}"
        )
    return p


def git(*args: str, check: bool = True) -> str:
    return run(["git", "-C", str(REPO), *args], check=check).stdout.rstrip("\n")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def ensure_regular(path: Path, label: str) -> Path:
    if not path.is_file() or path.is_symlink():
        raise AuditRegistrationError(
            f"{label} missing/invalid regular file: {path}"
        )
    return path


def write_tsv(
    path: Path,
    rows: list[dict[str, Any]],
    fields: list[str],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            delimiter="\t",
            fieldnames=fields,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def load_ssot(path: Path):
    spec = importlib.util.spec_from_file_location(
        "rnatr_ssot_stage16an", path
    )
    if spec is None or spec.loader is None:
        raise AuditRegistrationError(f"cannot import SSOT module: {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def source_document(
    conn: sqlite3.Connection,
    path: Path,
    source_type: str,
    effective_at: str,
) -> None:
    stat = path.stat()
    mtime = dt.datetime.fromtimestamp(
        stat.st_mtime, tz=dt.timezone.utc
    ).replace(microsecond=0).isoformat()
    conn.execute(
        """INSERT INTO source_documents(
               source_type,path,sha256,bytes,mtime_utc,
               content_status,ingested_at
           ) VALUES(?,?,?,?,?,?,?)
           ON CONFLICT(path) DO UPDATE SET
               source_type=excluded.source_type,
               sha256=excluded.sha256,
               bytes=excluded.bytes,
               mtime_utc=excluded.mtime_utc,
               content_status=excluded.content_status,
               ingested_at=excluded.ingested_at""",
        (
            source_type,
            str(path),
            sha256_file(path),
            stat.st_size,
            mtime,
            "PRESENT",
            effective_at,
        ),
    )


def ensure_stage(
    conn: sqlite3.Connection,
    stage_key: str,
    order: float,
    name: str,
    purpose: str,
    implementation_status: str,
    notes: str,
) -> None:
    conn.execute(
        """INSERT INTO stage_definitions(
               stage_key,stage_order,name,purpose,category,
               implementation_status,notes
           ) VALUES(?,?,?,?,?,?,?)
           ON CONFLICT(stage_key) DO UPDATE SET
               stage_order=excluded.stage_order,
               name=excluded.name,
               purpose=excluded.purpose,
               category=excluded.category,
               implementation_status=excluded.implementation_status,
               notes=excluded.notes""",
        (
            stage_key,
            order,
            name,
            purpose,
            "release_engineering",
            implementation_status,
            notes,
        ),
    )


def add_run_stage(
    conn: sqlite3.Connection,
    stage_key: str,
    attempt: str,
    status: str,
    qc_status: str,
    evidence_path: str,
    notes: str,
    effective_at: str,
) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO run_stages(
               run_id,stage_key,implementation_id,attempt_tag,status,
               command_text,qc_path,qc_status,started_at,ended_at,notes
           ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (
            RUN_ID,
            stage_key,
            None,
            attempt,
            status,
            None,
            evidence_path,
            qc_status,
            None,
            effective_at,
            notes,
        ),
    )


def superseding_decision(
    conn: sqlite3.Connection,
    key: str,
    category: str,
    title: str,
    statement: str,
    rationale: str,
    evidence_path: str,
    effective_at: str,
) -> None:
    old = conn.execute(
        "SELECT decision_id FROM decisions "
        "WHERE decision_key=? AND status='ACTIVE'",
        (key,),
    ).fetchone()
    old_id = old[0] if old else None
    if old_id:
        conn.execute(
            "UPDATE decisions SET status='SUPERSEDED' "
            "WHERE decision_id=?",
            (old_id,),
        )
    decision_id = "decision_" + hashlib.sha256(
        (VERSION + "|" + key).encode()
    ).hexdigest()[:20]
    conn.execute(
        """INSERT OR REPLACE INTO decisions(
               decision_id,decision_key,category,title,statement,status,
               confidence,effective_at,supersedes_decision_id,
               rationale,evidence_path
           ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (
            decision_id,
            key,
            category,
            title,
            statement,
            "ACTIVE",
            "HIGH",
            effective_at,
            old_id,
            rationale,
            evidence_path,
        ),
    )


def add_metric(
    conn: sqlite3.Connection,
    stage_key: str,
    name: str,
    value: str,
    evidence_path: str,
    effective_at: str,
) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO metrics(
               run_id,stage_key,metric_name,value_text,value_num,unit,
               denominator_num,source_path,metric_status,recorded_at
           ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (
            RUN_ID,
            stage_key,
            name,
            value,
            None,
            None,
            None,
            evidence_path,
            "CURRENT",
            effective_at,
        ),
    )


def safe_extract_bundle(
    bundle: Path,
    destination: Path,
) -> dict[str, Path]:
    destination.mkdir(parents=True, exist_ok=False)
    with tarfile.open(bundle, "r:gz") as tf:
        members = tf.getmembers()
        names = {m.name for m in members if m.isfile()}
        if names != set(EXPECTED_MEMBERS):
            raise AuditRegistrationError(
                "audit bundle member-set mismatch: "
                f"observed={sorted(names)} expected={sorted(EXPECTED_MEMBERS)}"
            )
        for member in members:
            if not member.isfile() or member.issym() or member.islnk():
                raise AuditRegistrationError(
                    f"non-regular audit member rejected: {member.name}"
                )
            rel = Path(member.name)
            if rel.is_absolute() or ".." in rel.parts:
                raise AuditRegistrationError(
                    f"unsafe audit member path: {member.name}"
                )
        tf.extractall(destination)

    extracted: dict[str, Path] = {}
    for name, expected_sha in EXPECTED_MEMBERS.items():
        path = destination / name
        if sha256_file(path) != expected_sha:
            raise AuditRegistrationError(
                f"audit member SHA mismatch: {name}"
            )
        extracted[name] = path
    return extracted


def update_docs(audit_md: Path) -> None:
    audit_target = REPO / AUDIT_RECORD_REL
    if audit_target.exists():
        raise AuditRegistrationError(
            f"final audit record already exists: {audit_target}"
        )
    audit_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(audit_md, audit_target)

    stage16ae_path = ensure_regular(
        REPO / "docs/release/STAGE16AE_PUBLIC_RELEASE_PACKAGING_v0.1.0.md",
        "Stage16AE record",
    )
    stage16ae = stage16ae_path.read_text(encoding="utf-8")
    old_status = (
        "**MECHANICAL PACKAGING / RC PREFLIGHT / SSOT RECONCILIATION "
        "COMPLETE — FINAL PRO AUDIT PENDING**"
    )
    new_status = (
        "**MECHANICAL PACKAGING / RC PREFLIGHT / SSOT RECONCILIATION / "
        "FINAL PRO AUDIT COMPLETE — FINAL PUBLIC BINDING PENDING**"
    )
    if stage16ae.count(old_status) != 1:
        raise AuditRegistrationError(
            "unexpected Stage16AE final-audit status anchor"
        )
    stage16ae = stage16ae.replace(old_status, new_status, 1)
    old_task = "- [ ] run the final Pro-level cross-cut audit."
    new_task = "- [x] run the final Pro-level cross-cut audit."
    if stage16ae.count(old_task) != 1:
        raise AuditRegistrationError(
            "unexpected Stage16AE final-audit checklist anchor"
        )
    stage16ae = stage16ae.replace(old_task, new_task, 1)
    old_acceptance = (
        "The post-license RC preflight and SSOT packaging-state reconciliation "
        "are complete. Stage16AE/AF/AG are therefore ready for the final Pro "
        "cross-cut audit. Public v0.5.0 is not declared merely by completing "
        "these mechanical steps."
    )
    new_acceptance = (
        "The release candidate has passed the final Pro cross-cut audit. "
        "Stage16AE/AF/AG and the subsequent repository/SSOT remediation are "
        "accepted for the audited RC scope. Public v0.5.0 is still not declared "
        "until final-version conversion, main/public-source verification, and "
        "immutable tag/release/citation binding complete."
    )
    if stage16ae.count(old_acceptance) != 1:
        raise AuditRegistrationError(
            "unexpected Stage16AE acceptance anchor"
        )
    stage16ae_path.write_text(
        stage16ae.replace(old_acceptance, new_acceptance, 1),
        encoding="utf-8",
    )

    notes_path = ensure_regular(
        REPO / "docs/release/RELEASE_NOTES_v0.5.0-rc1.md",
        "RC release notes",
    )
    notes = notes_path.read_text(encoding="utf-8")
    old_notes_status = (
        "**RELEASE CANDIDATE PACKAGING — FINAL PRO CROSS-CUT AUDIT PENDING**"
    )
    new_notes_status = (
        "**RELEASE CANDIDATE PASSED FINAL PRO CROSS-CUT AUDIT — "
        "FINAL PUBLIC BINDING PENDING**"
    )
    if notes.count(old_notes_status) != 1:
        raise AuditRegistrationError(
            "unexpected RC release-notes status anchor"
        )
    notes = notes.replace(old_notes_status, new_notes_status, 1)
    for line in (
        "- run the final Pro-level cross-cut audit;\n",
        "- resolve any audit-blocking findings;\n",
    ):
        if notes.count(line) != 1:
            raise AuditRegistrationError(
                f"unexpected release-notes remaining-work anchor: {line!r}"
            )
        notes = notes.replace(line, "", 1)
    notes_path.write_text(notes, encoding="utf-8")

    changelog_path = ensure_regular(REPO / "CHANGELOG.md", "CHANGELOG")
    changelog = changelog_path.read_text(encoding="utf-8")
    old_line = (
        "- Final public release date, immutable tag, release archive, and "
        "citation binding will be filled only after the final Pro audit and "
        "release binding complete."
    )
    new_line = (
        "- Final public release date, immutable tag, release archive, and "
        "citation binding will be filled during the final release-binding stage."
    )
    if changelog.count(old_line) != 1:
        raise AuditRegistrationError("unexpected CHANGELOG final-audit anchor")
    changelog_path.write_text(
        changelog.replace(old_line, new_line, 1),
        encoding="utf-8",
    )


def copy_registrar() -> None:
    target = REPO / REGISTRAR_REL
    if target.exists():
        raise AuditRegistrationError(
            f"registrar target already exists: {target}"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(Path(__file__).resolve(), target)


def find_test_python() -> Path:
    candidates = [
        Path(
            "/mnt/intelssd/rnatr_release_engineering/"
            "stage16x_full_network_fresh_install_v011_20260817T022512Z/"
            "env/bin/python"
        ),
        Path.home()
        / ".local/share/rnatr-scout/envs/source-checkout-v0.1/bin/python",
        Path(sys.executable),
    ]
    for py in candidates:
        try:
            py = py.resolve()
        except OSError:
            continue
        if not py.is_file():
            continue
        probe = run(
            [
                str(py),
                "-c",
                "import sys,unittest,ctypes; print(sys.version.split()[0])",
            ],
            check=False,
        )
        if probe.returncode == 0:
            return py
    raise AuditRegistrationError("no suitable Python for archive smoke")


def markdown_link_check(root: Path, rel: str) -> tuple[int, list[str]]:
    path = root / rel
    text = path.read_text(encoding="utf-8")
    links = re.findall(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", text)
    checked = 0
    broken: list[str] = []
    for raw in links:
        target = raw.strip()
        if (
            not target
            or target.startswith("#")
            or "://" in target
            or target.startswith("mailto:")
        ):
            continue
        if ' "' in target:
            target = target.split(' "', 1)[0]
        target = target.split("#", 1)[0]
        if not target:
            continue
        checked += 1
        resolved = (path.parent / target).resolve()
        try:
            resolved.relative_to(root.resolve())
        except ValueError:
            broken.append(target)
            continue
        if not resolved.exists():
            broken.append(target)
    return checked, broken


def prospective_archive_smoke(
    tree_sha: str,
    evidence_out: Path,
) -> dict[str, Any]:
    archive = evidence_out / "prospective_source.tar"
    with archive.open("wb") as out:
        p = subprocess.run(
            ["git", "-C", str(REPO), "archive", "--format=tar", tree_sha],
            stdout=out,
            stderr=subprocess.PIPE,
            check=False,
        )
    if p.returncode != 0:
        raise AuditRegistrationError(
            "git archive failed: "
            + p.stderr.decode("utf-8", errors="replace")
        )
    archive_sha = sha256_file(archive)
    archive_bytes = archive.stat().st_size
    py = find_test_python()

    logs: dict[str, str] = {}
    with tempfile.TemporaryDirectory(
        prefix="rnatr_stage16an_archive_"
    ) as td:
        source = Path(td) / "source"
        source.mkdir()
        with tarfile.open(archive, "r") as tf:
            for member in tf.getmembers():
                rel = Path(member.name)
                if rel.is_absolute() or ".." in rel.parts:
                    raise AuditRegistrationError(
                        f"unsafe source archive member: {member.name}"
                    )
            tf.extractall(source)

        env = os.environ.copy()
        env["PYTHONPATH"] = str(source / "src")
        env["RNATR_PROJECT_ROOT"] = str(source)
        env["PYTHONHASHSEED"] = "0"

        commands = {
            "compileall": [
                str(py), "-m", "compileall", "-q",
                "src", "scripts", "metadata/ssot",
            ],
            "unit_tests": [
                str(py), "-m", "unittest", "discover",
                "-s", "tests/unit", "-p", "test*.py", "-v",
            ],
            "resource_planner_tests": [
                str(py), "tests/test_resource_planner.py",
            ],
            "cli_version": [
                str(py), "-m", "rnatr_scout.cli", "version",
            ],
            "cli_help": [
                str(py), "-m", "rnatr_scout.cli", "--help",
            ],
            "setup_help": [
                str(py),
                "scripts/rnatr_setup_source_checkout_v0.1.1.py",
                "--help",
            ],
            "native_load": [
                str(py), "-c",
                (
                    "import ctypes; ctypes.CDLL("
                    "'src/rnatr_scout/general_caller/native_v0.4.1/"
                    "librnatr_native_periodic_kernel_v0.1.0.so'"
                    "); print('PASS_NATIVE_LOAD')"
                ),
            ],
        }
        for name, argv in commands.items():
            p = run(argv, cwd=source, env=env, check=False)
            logs[name] = p.stdout
            (evidence_out / f"{name}.log").write_text(
                p.stdout, encoding="utf-8"
            )
            if p.returncode != 0:
                raise AuditRegistrationError(
                    f"prospective archive {name} failed rc={p.returncode}"
                )

        if logs["cli_version"].strip() != EXPECTED_PACKAGE_VERSION:
            raise AuditRegistrationError(
                "prospective archive CLI version mismatch"
            )
        for command in ("run", "map", "resources-status", "system-info"):
            if command not in logs["cli_help"]:
                raise AuditRegistrationError(
                    f"public CLI command missing: {command}"
                )
        if "PASS_NATIVE_LOAD" not in logs["native_load"]:
            raise AuditRegistrationError("native-load marker missing")

    archive.unlink()
    return {
        "tested_tree": tree_sha,
        "source_archive_sha256": archive_sha,
        "source_archive_bytes": archive_bytes,
        "python": str(py),
        "python_version": run([str(py), "--version"]).stdout.strip(),
        "compileall": "PASS",
        "unit_tests": "PASS",
        "resource_planner_tests": "PASS",
        "cli_version": "PASS",
        "cli_help": "PASS",
        "setup_help": "PASS",
        "native_load": "PASS",
    }


def text_files_for_secret_scan() -> list[Path]:
    result: list[Path] = []
    for rel in git("ls-files", "--cached", "-z").split("\0"):
        if not rel:
            continue
        path = REPO / rel
        if not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
            continue
        if path.suffix.lower() not in {
            ".py", ".sh", ".md", ".txt", ".tsv", ".csv", ".json",
            ".toml", ".yml", ".yaml", ".cff", ".ini", ".cfg", ".conf",
        } and path.name not in {
            "README.md", "LICENSE", "CITATION.cff",
            "THIRD_PARTY_NOTICES.md", "CHANGELOG.md",
        }:
            continue
        data = path.read_bytes()
        if b"\x00" not in data:
            result.append(path)
    return result


def restore_precommit(db: Path, backup: Path) -> None:
    try:
        run(
            ["git", "-C", str(REPO), "reset", "--hard", EXPECTED_HEAD],
            check=False,
        )
        for rel in (AUDIT_RECORD_REL, REGISTRAR_REL):
            path = REPO / rel
            if path.exists():
                path.unlink()
        if backup.is_file():
            shutil.copy2(backup, db)
    except Exception:
        pass


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Register the final Pro cross-cut audit PASS, close the audit gate, "
            "and verify the exact metadata-only prospective tree."
        )
    )
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    print("===== RNA-TR-SCOUT STAGE16AN FINAL PRO AUDIT REGISTRATION =====")
    print(f"version\t{VERSION}")
    print(f"mode\t{'EXECUTE' if args.execute else 'PREFLIGHT'}")

    ensure_regular(AUDIT_BUNDLE, "Stage16AN audit evidence bundle")
    if sha256_file(AUDIT_BUNDLE) != AUDIT_BUNDLE_SHA256:
        raise AuditRegistrationError("Stage16AN audit bundle SHA mismatch")

    run(["git", "-C", str(REPO), "fetch", "origin", "--tags"])
    branch = git("branch", "--show-current").strip()
    head = git("rev-parse", "HEAD").strip()
    tree = git("rev-parse", "HEAD^{tree}").strip()
    remote = git("rev-parse", f"origin/{BRANCH}").strip()
    origin_main = git("rev-parse", "origin/main").strip()
    status = run(
        [
            "git", "-C", str(REPO),
            "status", "--porcelain=v1", "--untracked-files=all",
        ]
    ).stdout.strip()

    if branch != BRANCH:
        raise AuditRegistrationError(
            f"expected branch {BRANCH}; observed {branch}"
        )
    if head != EXPECTED_HEAD or remote != EXPECTED_HEAD:
        raise AuditRegistrationError(
            f"head drift: local={head} remote={remote} expected={EXPECTED_HEAD}"
        )
    if tree != EXPECTED_TREE:
        raise AuditRegistrationError(
            f"tree drift: {tree} != {EXPECTED_TREE}"
        )
    if origin_main != EXPECTED_MAIN:
        raise AuditRegistrationError(
            f"origin/main drift: {origin_main} != {EXPECTED_MAIN}"
        )
    if run(
        [
            "git", "-C", str(REPO),
            "merge-base", "--is-ancestor", origin_main, head,
        ],
        check=False,
    ).returncode != 0:
        raise AuditRegistrationError(
            "origin/main is not an ancestor of the audited release branch"
        )
    if status:
        raise AuditRegistrationError(
            "working tree must be clean:\n" + status
        )
    if run(
        [
            "git", "-C", str(REPO),
            "merge-base", "--is-ancestor", FREEZE_ROOT, head,
        ],
        check=False,
    ).returncode != 0:
        raise AuditRegistrationError("Freeze ancestry failed")

    remote_tags = run(
        ["git", "-C", str(REPO), "ls-remote", "--tags", "origin"]
    ).stdout.splitlines()
    tag_refs = {
        line.split("\t", 1)[1]
        for line in remote_tags
        if "\t" in line
    }
    forbidden_tags = {
        "refs/tags/v0.5.0",
        "refs/tags/v0.5.0^{}",
        "refs/tags/v0.5.0-rc1",
        "refs/tags/v0.5.0-rc1^{}",
    }
    if tag_refs & forbidden_tags:
        raise AuditRegistrationError(
            f"final/RC public software tag already exists: {sorted(tag_refs & forbidden_tags)}"
        )

    if (REPO / AUDIT_RECORD_REL).exists():
        raise AuditRegistrationError(
            f"audit record already exists: {AUDIT_RECORD_REL}"
        )
    if (REPO / REGISTRAR_REL).exists():
        raise AuditRegistrationError(
            f"registrar already exists: {REGISTRAR_REL}"
        )

    # Exact package/scientific identity guards.
    if sha256_file(REPO / "LICENSE") != EXPECTED_LICENSE_SHA256:
        raise AuditRegistrationError("LICENSE SHA drift")
    if sha256_file(
        REPO / "environment-linux-64.lock.txt"
    ) != EXPECTED_LOCK_SHA256:
        raise AuditRegistrationError("environment lock SHA drift")
    native = (
        REPO
        / "src/rnatr_scout/general_caller/native_v0.4.1/"
        "librnatr_native_periodic_kernel_v0.1.0.so"
    )
    if sha256_file(native) != EXPECTED_NATIVE_SHA256:
        raise AuditRegistrationError("native kernel SHA drift")
    if sha256_file(
        REPO / "validation/release_gates_v0.3.5.tsv"
    ) != EXPECTED_RELEASE_GATES_SHA256:
        raise AuditRegistrationError("release-gate table SHA drift")
    if f'version = "{EXPECTED_PACKAGE_VERSION}"' not in (
        REPO / "pyproject.toml"
    ).read_text(encoding="utf-8"):
        raise AuditRegistrationError("package version drift")
    if f"version: {EXPECTED_CFF_VERSION}" not in (
        REPO / "CITATION.cff"
    ).read_text(encoding="utf-8"):
        raise AuditRegistrationError("CITATION version drift")

    ssot_root = PROJECT / "metadata/ssot"
    db = ensure_regular(
        ssot_root / "rnatr_ssot.sqlite", "canonical SSOT database"
    )
    ssot_py = ensure_regular(
        ssot_root / "rnatr_ssot.py", "canonical SSOT implementation"
    )
    with sqlite3.connect(str(db)) as conn:
        conn.row_factory = sqlite3.Row
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise AuditRegistrationError("SSOT integrity preflight failed")
        if list(conn.execute("PRAGMA foreign_key_check")):
            raise AuditRegistrationError("SSOT foreign-key preflight failed")
        audit_q = conn.execute(
            "SELECT status,blocking FROM open_questions "
            "WHERE question_key='PUBLIC_RC_PRO_CROSSCUT_AUDIT'"
        ).fetchone()
        if (
            not audit_q
            or audit_q["status"] != "OPEN"
            or int(audit_q["blocking"]) != 1
        ):
            raise AuditRegistrationError(
                f"unexpected final-Pro gate precondition: {audit_q}"
            )
        release_q = conn.execute(
            "SELECT status FROM open_questions "
            "WHERE question_key='CORE_FREEZE_GIT_TAG_AND_PUBLIC_RELEASE_BINDING'"
        ).fetchone()
        if not release_q or release_q["status"] != "OPEN":
            raise AuditRegistrationError(
                f"unexpected release-binding gate state: {release_q}"
            )

    print("git_exact_target\tPASS")
    print("freeze_ancestry\tPASS")
    print("main_ancestry\tPASS")
    print("no_final_public_tag\tPASS")
    print("audit_bundle\tPASS")
    print("package_scientific_identity\tPASS")
    print("ssot_preflight\tPASS")
    print("planned_runtime_scientific_change\tfalse")
    print("planned_public_release_creation\tfalse")

    if not args.execute:
        print("status\tPREFLIGHT_PASS_READY_FOR_EXECUTE")
        return 0

    effective_at = utc_now()
    checkpoint = (
        ssot_root
        / "checkpoints/stage16an_final_pro_crosscut_audit_v0.1.0"
        / effective_at.replace(":", "").replace("+00:00", "Z")
    )
    originals = checkpoint / "originals"
    backups = checkpoint / "backups"
    originals.mkdir(parents=True, exist_ok=False)
    backups.mkdir(parents=True, exist_ok=True)

    durable_bundle = originals / AUDIT_BUNDLE.name
    shutil.copy2(AUDIT_BUNDLE, durable_bundle)
    if sha256_file(durable_bundle) != AUDIT_BUNDLE_SHA256:
        raise AuditRegistrationError("durable audit bundle SHA mismatch")
    evidence = safe_extract_bundle(
        durable_bundle, originals / "extracted"
    )

    audit_json = evidence[
        "rnatr_stage16an_final_pro_crosscut_audit_v0.1.0.json"
    ]
    audit_md = evidence[
        "rnatr_stage16an_final_pro_crosscut_audit_v0.1.0.md"
    ]
    stage16am_result = evidence[
        "rnatr_stage16am_final_pro_metadata_remediation.result.json"
    ]
    stage16am_bundle = evidence[
        "rnatr_stage16am_final_pro_metadata_remediation_bundle_2026-08-17T080014+0000.tar.gz"
    ]

    audit_obj = json.loads(audit_json.read_text(encoding="utf-8"))
    if audit_obj.get("status") != "PASS_FINAL_PRO_CROSSCUT_AUDIT":
        raise AuditRegistrationError("unexpected final audit status")
    target = audit_obj.get("audit_target", {})
    if (
        target.get("commit") != EXPECTED_HEAD
        or target.get("tree") != EXPECTED_TREE
        or target.get("source_archive_sha256")
        != "93a5df2228996513d18851b8cb0c9a86b4e44547fcb5343fe14b1cb4522924b6"
    ):
        raise AuditRegistrationError("final audit target mismatch")
    if audit_obj.get("blocking_findings") != []:
        raise AuditRegistrationError("final audit unexpectedly has blockers")

    am_obj = json.loads(stage16am_result.read_text(encoding="utf-8"))
    if (
        am_obj.get("status")
        != "PASS_STAGE16AM_METADATA_REMEDIATION_AND_POST_REMEDIATION_RC_PREFLIGHT"
        or am_obj.get("post_head") != EXPECTED_HEAD
        or am_obj.get("post_tree") != EXPECTED_TREE
    ):
        raise AuditRegistrationError("Stage16AM evidence mismatch")

    pre_db_sha = sha256_file(db)
    backup = backups / "rnatr_ssot.pre_stage16an.sqlite"
    shutil.copy2(db, backup)
    if sha256_file(backup) != pre_db_sha:
        raise AuditRegistrationError("SSOT backup SHA mismatch")

    pushed = False
    try:
        update_docs(audit_md)
        copy_registrar()

        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            conn.execute("BEGIN IMMEDIATE")

            for source_type, path in (
                ("stage16an_final_pro_audit_json", audit_json),
                ("stage16an_final_pro_audit_markdown", audit_md),
                ("stage16an_final_pro_audit_bundle", durable_bundle),
                ("stage16am_post_remediation_result", stage16am_result),
                ("stage16am_post_remediation_bundle", stage16am_bundle),
                ("stage16an_repo_audit_record", REPO / AUDIT_RECORD_REL),
                ("stage16an_registrar", REPO / REGISTRAR_REL),
            ):
                source_document(
                    conn, path, source_type, effective_at
                )

            ensure_stage(
                conn,
                "16AN_FINAL_PRO_CROSSCUT_AUDIT",
                184.0,
                "Stage16AN final Pro cross-cut audit",
                (
                    "Independently re-audit the exact post-remediation RC across "
                    "Freeze state, runtime, packaging, resources, validation, "
                    "documentation, repository hygiene and SSOT/Git/docs consistency."
                ),
                "VALIDATED",
                (
                    "PASS for commit 9d660e96e54c796696a28ebe686019d5636bb420; "
                    "final public version/tag/release binding remains separate."
                ),
            )
            add_run_stage(
                conn,
                "16AN_FINAL_PRO_CROSSCUT_AUDIT",
                "v0.1.0",
                "PASS",
                "PASS",
                str(audit_json),
                (
                    "All cross-cut audit domains PASS or PASS_WITH_REGISTERED_SCOPE; "
                    "the four pre-remediation metadata findings are closed and no "
                    "blocking finding remains."
                ),
                effective_at,
            )

            superseding_decision(
                conn,
                "public_rc_pro_crosscut_audit_pass_v0_1_0",
                "release_governance",
                "Accept the final Pro cross-cut audit",
                (
                    "The exact post-remediation RNA-TR-Scout v0.5.0 RC passes the "
                    "final Pro audit for Freeze integrity, scientific/runtime identity, "
                    "release packaging, standard resources, scoped portability, "
                    "documentation, repository hygiene and SSOT/Git/docs consistency. "
                    "Proceed only to guarded final-version and public-release binding."
                ),
                (
                    "Stage16AN reread the Stage16AH/AL/AM evidence, exact remote commit/"
                    "tree, current governance tables and the validated source archive; "
                    "no blocking finding remains."
                ),
                str(REPO / AUDIT_RECORD_REL),
                effective_at,
            )
            superseding_decision(
                conn,
                "release_candidate_ready_for_final_pro_audit_v0_1_0",
                "release_readiness",
                "Release candidate passed final Pro audit",
                (
                    "The audited RC passed the final Pro cross-cut audit. Scientific/"
                    "runtime changes are no longer authorized for this release line; "
                    "the next permitted work is final 0.5.0 metadata, main/public-source "
                    "verification and immutable tag/release/citation binding."
                ),
                (
                    "The Stage16AM prospective tree and exact remote commit are "
                    "scientifically identical to the previously validated candidate, "
                    "and Stage16AN closes all audit findings."
                ),
                str(REPO / AUDIT_RECORD_REL),
                effective_at,
            )

            close = conn.execute(
                """UPDATE open_questions
                   SET status='CLOSED',blocking=0,next_action=?,
                       evidence_path=?,effective_at=?
                   WHERE question_key='PUBLIC_RC_PRO_CROSSCUT_AUDIT'
                     AND status='OPEN' AND blocking=1""",
                (
                    (
                        "Completed: final Pro cross-cut audit PASS. Proceed with "
                        "guarded final-version and public-release binding only."
                    ),
                    str(REPO / AUDIT_RECORD_REL),
                    effective_at,
                ),
            )
            if close.rowcount != 1:
                raise AuditRegistrationError(
                    "failed to close PUBLIC_RC_PRO_CROSSCUT_AUDIT"
                )

            release_update = conn.execute(
                """UPDATE open_questions
                   SET next_action=?,evidence_path=?,effective_at=?
                   WHERE question_key='CORE_FREEZE_GIT_TAG_AND_PUBLIC_RELEASE_BINDING'
                     AND status='OPEN'""",
                (
                    (
                        "Convert RC metadata to final 0.5.0, test the exact prospective "
                        "release tree, fast-forward into main, make the repository "
                        "public, verify an unauthenticated public-source clone/setup, "
                        "create and verify the immutable v0.5.0 tag/GitHub Release/"
                        "source checksums/citation, then register final binding."
                    ),
                    str(REPO / AUDIT_RECORD_REL),
                    effective_at,
                ),
            )
            if release_update.rowcount != 1:
                raise AuditRegistrationError(
                    "failed to update release-binding gate"
                )

            limitation_update = conn.execute(
                """UPDATE limitations
                   SET statement=?,mitigation=?,evidence_path=?,effective_at=?
                   WHERE limitation_key='PUBLIC_V050_RELEASE_NOT_YET_COMPLETE'
                     AND status='ACTIVE'""",
                (
                    (
                        "The final Pro audit has passed, but the repository remains "
                        "a private pre-release RC and no final v0.5.0 tag/GitHub "
                        "Release has yet been created."
                    ),
                    (
                        "Complete guarded final 0.5.0 metadata conversion, main "
                        "integration, public visibility and unauthenticated clone/setup "
                        "smoke, then create/verify the immutable tag, release, source "
                        "checksums and citation binding."
                    ),
                    str(REPO / AUDIT_RECORD_REL),
                    effective_at,
                ),
            )
            if limitation_update.rowcount != 1:
                raise AuditRegistrationError(
                    "failed to update public-release limitation"
                )

            for name, value in (
                ("audited_commit", EXPECTED_HEAD),
                ("audited_tree", EXPECTED_TREE),
                (
                    "audited_source_archive_sha256",
                    "93a5df2228996513d18851b8cb0c9a86b4e44547fcb5343fe14b1cb4522924b6",
                ),
                ("audit_status", "PASS_FINAL_PRO_CROSSCUT_AUDIT"),
                ("blocking_findings", "0"),
                (
                    "release_authorization",
                    "FINAL_VERSION_AND_PUBLIC_BINDING_ONLY",
                ),
                ("public_release_created", "false"),
            ):
                add_metric(
                    conn,
                    "16AN_FINAL_PRO_CROSSCUT_AUDIT",
                    name,
                    value,
                    str(audit_json),
                    effective_at,
                )

            conn.commit()

            ssot = load_ssot(ssot_py)
            checks = ssot.validate_db(conn, PROJECT)
            failed = [row for row in checks if row[1] == "FAIL"]
            if failed:
                raise AuditRegistrationError(
                    f"post-audit SSOT validation failed: {failed}"
                )
            exports = ssot.export_views(conn, ssot_root)
            ssot.write_summary(conn, ssot_root, checks, exports)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        shutil.copy2(
            ssot_root / "CURRENT_STATE.md",
            REPO / "metadata/ssot/CURRENT_STATE.md",
        )
        for path in (ssot_root / "exports").glob("*.tsv"):
            shutil.copy2(
                path,
                REPO / "metadata/ssot/exports" / path.name,
            )

        # Validate current state before staging.
        with sqlite3.connect(str(db)) as check_conn:
            check_conn.row_factory = sqlite3.Row
            audit_q = check_conn.execute(
                "SELECT status,blocking FROM open_questions "
                "WHERE question_key='PUBLIC_RC_PRO_CROSSCUT_AUDIT'"
            ).fetchone()
            if (
                not audit_q
                or audit_q["status"] != "CLOSED"
                or int(audit_q["blocking"]) != 0
            ):
                raise AuditRegistrationError(
                    f"final audit gate not closed: {audit_q}"
                )
            release_q = check_conn.execute(
                "SELECT status FROM open_questions "
                "WHERE question_key='CORE_FREEZE_GIT_TAG_AND_PUBLIC_RELEASE_BINDING'"
            ).fetchone()
            if not release_q or release_q["status"] != "OPEN":
                raise AuditRegistrationError(
                    "release-binding gate closed prematurely"
                )

        # Project/repo SSOT identity.
        for path in (ssot_root / "exports").glob("*.tsv"):
            repo_path = REPO / "metadata/ssot/exports" / path.name
            if sha256_file(path) != sha256_file(repo_path):
                raise AuditRegistrationError(
                    f"SSOT export identity mismatch: {path.name}"
                )
        if sha256_file(
            ssot_root / "CURRENT_STATE.md"
        ) != sha256_file(REPO / "metadata/ssot/CURRENT_STATE.md"):
            raise AuditRegistrationError(
                "CURRENT_STATE identity mismatch"
            )

        # Exact changed-file scope.
        status_lines = run(
            [
                "git", "-C", str(REPO),
                "status", "--porcelain=v1", "--untracked-files=all",
            ]
        ).stdout.splitlines()
        changed_paths: set[str] = set()
        for line in status_lines:
            if not line:
                continue
            path = line[3:]
            if " -> " in path:
                path = path.split(" -> ", 1)[1]
            changed_paths.add(path)

        exact_allowed = {
            str(AUDIT_RECORD_REL),
            str(REGISTRAR_REL),
            "docs/release/STAGE16AE_PUBLIC_RELEASE_PACKAGING_v0.1.0.md",
            "docs/release/RELEASE_NOTES_v0.5.0-rc1.md",
            "CHANGELOG.md",
            "metadata/ssot/CURRENT_STATE.md",
        }
        unexpected = sorted(
            path
            for path in changed_paths
            if path not in exact_allowed
            and not path.startswith("metadata/ssot/exports/")
        )
        if unexpected:
            raise AuditRegistrationError(
                "unexpected changed paths:\n" + "\n".join(unexpected)
            )
        forbidden = sorted(
            path
            for path in changed_paths
            if path.startswith(
                ("src/", "scripts/", "config/", "validation/", "tests/")
            )
        )
        if forbidden:
            raise AuditRegistrationError(
                "runtime/scientific paths changed:\n"
                + "\n".join(forbidden)
            )

        run(["git", "-C", str(REPO), "diff", "--check"])

        # TSV structure and LF-only generated exports.
        tsvs = sorted(
            (REPO / "metadata/ssot/exports").glob("*.tsv")
        )
        for path in tsvs:
            if b"\r" in path.read_bytes():
                raise AuditRegistrationError(
                    f"CR byte found in generated TSV: {path}"
                )
            with path.open("r", encoding="utf-8", newline="") as fh:
                reader = csv.reader(fh, delimiter="\t")
                try:
                    header = next(reader)
                except StopIteration:
                    raise AuditRegistrationError(
                        f"empty TSV: {path}"
                    )
                for line_no, row in enumerate(reader, start=2):
                    if len(row) != len(header):
                        raise AuditRegistrationError(
                            f"TSV field mismatch {path}:{line_no}"
                        )

        link_rows: list[dict[str, Any]] = []
        for rel in (
            "README.md",
            "DEVELOPMENT.md",
            "docs/USER_GUIDE.md",
            "docs/history/DEVELOPMENT_HISTORY_v0.5.0.md",
            "CHANGELOG.md",
            "docs/release/RELEASE_NOTES_v0.5.0-rc1.md",
            "docs/release/STAGE16AE_PUBLIC_RELEASE_PACKAGING_v0.1.0.md",
            str(AUDIT_RECORD_REL),
        ):
            checked, broken = markdown_link_check(REPO, rel)
            link_rows.append(
                {
                    "path": rel,
                    "links_checked": checked,
                    "broken_links": len(broken),
                    "broken_targets": ",".join(broken),
                }
            )
            if broken:
                raise AuditRegistrationError(
                    f"broken links in {rel}: {broken}"
                )

        run(
            [
                "git", "-C", str(REPO), "add",
                str(AUDIT_RECORD_REL),
                str(REGISTRAR_REL),
                "docs/release/STAGE16AE_PUBLIC_RELEASE_PACKAGING_v0.1.0.md",
                "docs/release/RELEASE_NOTES_v0.5.0-rc1.md",
                "CHANGELOG.md",
                "metadata/ssot/CURRENT_STATE.md",
                "metadata/ssot/exports",
            ]
        )
        run(
            ["git", "-C", str(REPO), "diff", "--cached", "--check"]
        )

        staged = run(
            [
                "git", "-C", str(REPO),
                "diff", "--cached", "--name-only",
            ]
        ).stdout.splitlines()
        forbidden_staged = [
            path
            for path in staged
            if path.startswith(
                ("src/", "scripts/", "config/", "validation/", "tests/")
            )
        ]
        if forbidden_staged:
            raise AuditRegistrationError(
                "forbidden staged paths:\n"
                + "\n".join(forbidden_staged)
            )

        prospective_tree = git("write-tree").strip()
        evidence_out = (
            RELEASE_ROOT
            / (
                "stage16an_final_pro_audit_registration_"
                + effective_at.replace(":", "").replace("+00:00", "Z")
            )
        )
        evidence_out.mkdir(parents=True, exist_ok=False)

        secret_hits: list[dict[str, Any]] = []
        for path in text_files_for_secret_scan():
            text = path.read_text(encoding="utf-8", errors="replace")
            rel = path.relative_to(REPO).as_posix()
            for pattern_name, regex in SECRET_PATTERNS.items():
                for match in regex.finditer(text):
                    secret_hits.append(
                        {
                            "path": rel,
                            "line": text.count("\n", 0, match.start()) + 1,
                            "pattern": pattern_name,
                        }
                    )
        write_tsv(
            evidence_out / "high_confidence_secret_hits.tsv",
            secret_hits,
            ["path", "line", "pattern"],
        )
        if secret_hits:
            raise AuditRegistrationError(
                f"secret scan hits: {secret_hits}"
            )
        write_tsv(
            evidence_out / "markdown_link_checks.tsv",
            link_rows,
            [
                "path", "links_checked",
                "broken_links", "broken_targets",
            ],
        )

        smoke = prospective_archive_smoke(
            prospective_tree, evidence_out
        )

        run(
            [
                "git", "-C", str(REPO), "commit",
                "-m", "Register final Pro cross-cut audit pass",
            ]
        )
        post_head = git("rev-parse", "HEAD").strip()
        post_tree = git("rev-parse", "HEAD^{tree}").strip()
        if post_tree != prospective_tree:
            raise AuditRegistrationError(
                "committed tree differs from tested prospective tree"
            )
        if run(
            [
                "git", "-C", str(REPO),
                "merge-base", "--is-ancestor", FREEZE_ROOT, post_head,
            ],
            check=False,
        ).returncode != 0:
            raise AuditRegistrationError(
                "Freeze ancestry lost after registration commit"
            )

        run(["git", "-C", str(REPO), "push", "origin", BRANCH])
        pushed = True
        run(["git", "-C", str(REPO), "fetch", "origin"])
        remote_post = git("rev-parse", f"origin/{BRANCH}").strip()
        if remote_post != post_head:
            raise AuditRegistrationError(
                "remote head mismatch after push"
            )
        if run(
            [
                "git", "-C", str(REPO),
                "status", "--porcelain=v1", "--untracked-files=all",
            ]
        ).stdout.strip():
            raise AuditRegistrationError(
                "working tree not clean after push"
            )

        post_db_sha = sha256_file(db)
        result = {
            "version": VERSION,
            "status": (
                "PASS_STAGE16AN_FINAL_PRO_AUDIT_REGISTERED_AND_GATE_CLOSED"
            ),
            "effective_at": effective_at,
            "branch": BRANCH,
            "audited_head": EXPECTED_HEAD,
            "audited_tree": EXPECTED_TREE,
            "audited_source_archive_sha256": (
                "93a5df2228996513d18851b8cb0c9a86b4e44547fcb5343fe14b1cb4522924b6"
            ),
            "registration_head": post_head,
            "registration_tree": post_tree,
            "freeze_root": FREEZE_ROOT,
            "freeze_ancestor_preserved": True,
            "audit_evidence_bundle_sha256": AUDIT_BUNDLE_SHA256,
            "final_pro_audit_status": "PASS_FINAL_PRO_CROSSCUT_AUDIT",
            "final_pro_audit_gate": "CLOSED",
            "release_binding_gate": "OPEN",
            "release_authorization": (
                "FINAL_VERSION_AND_PUBLIC_RELEASE_BINDING_ONLY"
            ),
            "runtime_code_changed": False,
            "scientific_core_changed": False,
            "package_identity_changed": False,
            "public_release_created": False,
            "ssot_pre_sha256": pre_db_sha,
            "ssot_post_sha256": post_db_sha,
            "ssot_backup": str(backup),
            **smoke,
            "secret_scan": "PASS",
            "markdown_link_validation": "PASS",
            "working_tree_clean_after_push": True,
            "human_visual_review_required": False,
            "next_step": (
                "SWITCH_TO_HIGH_FOR_GUARDED_FINAL_0_5_0_VERSION_MAIN_PUBLIC_"
                "CLONE_TAG_RELEASE_AND_CITATION_BINDING"
            ),
        }

        result_path = (
            evidence_out
            / "rnatr_stage16an_final_pro_audit_registration.result.json"
        )
        result_path.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        snapshots = evidence_out / "snapshots"
        snapshots.mkdir()
        for path in (
            REPO / AUDIT_RECORD_REL,
            REPO / "docs/release/RELEASE_NOTES_v0.5.0-rc1.md",
            REPO / "docs/release/STAGE16AE_PUBLIC_RELEASE_PACKAGING_v0.1.0.md",
            REPO / "CHANGELOG.md",
            REPO / "metadata/ssot/CURRENT_STATE.md",
            REPO / "metadata/ssot/exports/current_open_questions.tsv",
            REPO / "metadata/ssot/exports/current_results.tsv",
            REPO / "metadata/ssot/exports/latest_stage_status.tsv",
        ):
            shutil.copy2(path, snapshots / path.name)

        bundle = (
            evidence_out
            / (
                "rnatr_stage16an_final_pro_audit_registration_bundle_"
                + effective_at.replace(":", "").replace("+00:00", "Z")
                + ".tar.gz"
            )
        )
        with tarfile.open(bundle, "w:gz") as tf:
            for path in sorted(evidence_out.rglob("*")):
                if path == bundle or not path.is_file():
                    continue
                tf.add(
                    path,
                    arcname=path.relative_to(evidence_out).as_posix(),
                )
        bundle_sha = sha256_file(bundle)
        manifest = {
            "bundle": bundle.name,
            "bundle_sha256": bundle_sha,
            "audited_head": EXPECTED_HEAD,
            "registration_head": post_head,
            "members": {
                path.relative_to(evidence_out).as_posix(): sha256_file(path)
                for path in sorted(evidence_out.rglob("*"))
                if path.is_file() and path != bundle
            },
        }
        (evidence_out / "bundle_manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        downloads_result = (
            Path.home()
            / "Downloads/rnatr_stage16an_final_pro_audit_registration.result.json"
        )
        downloads_bundle = Path.home() / "Downloads" / bundle.name
        shutil.copy2(result_path, downloads_result)
        shutil.copy2(bundle, downloads_bundle)

        print("===== DONE =====")
        print(
            "status\t"
            "PASS_STAGE16AN_FINAL_PRO_AUDIT_REGISTERED_AND_GATE_CLOSED"
        )
        print(f"audited_head\t{EXPECTED_HEAD}")
        print(f"registration_head\t{post_head}")
        print(f"registration_tree\t{post_tree}")
        print(f"source_archive_sha256\t{smoke['source_archive_sha256']}")
        print(f"result\t{downloads_result}")
        print(f"bundle\t{downloads_bundle}")
        print(f"bundle_sha256\t{bundle_sha}")
        print("final_pro_audit_gate\tCLOSED")
        print("release_binding_gate\tOPEN")
        print("runtime_code_changed\tfalse")
        print("scientific_core_changed\tfalse")
        print("package_identity_changed\tfalse")
        return 0

    except Exception:
        if not pushed:
            restore_precommit(db, backup)
        else:
            print(
                "WARNING: failure after remote push; automatic rollback skipped "
                "to avoid local/remote divergence.",
                file=sys.stderr,
            )
        raise


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
