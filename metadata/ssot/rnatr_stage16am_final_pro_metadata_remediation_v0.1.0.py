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

VERSION = "rnatr_stage16am_final_pro_metadata_remediation_recovery_v0.1.1"

REPO = Path(
    "/mnt/intelssd/rnatr_git_stage/"
    "LOCAL_CORE_FREEZE_V0.1.0_git_snapshot_v0.1.2"
)
PROJECT = Path("/mnt/intelssd/rnatr_project")
RELEASE_ROOT = Path("/mnt/intelssd/rnatr_release_engineering")
BRANCH = "stage16ae-public-release-packaging"
EXPECTED_HEAD = "fb76836852dd7e9f65a385b3ede72353b2a350c9"
FREEZE_ROOT = "4b1981db955a8aa92a2a01e19bbb1cfc2aa0ebfb"
RUN_ID = "RNA_TR_SCOUT_STAGE16_RELEASE_ENGINEERING"

EVIDENCE_BUNDLE = (
    Path.home()
    / "Downloads/rnatr_stage16al_final_pro_crosscut_audit_evidence_v0.1.0.tar.gz"
)
EVIDENCE_BUNDLE_SHA256 = (
    "049f40ef57356742022c57b05c8dae1208c876e9d80ec3d8b387e882198d2f63"
)

EXPECTED_EVIDENCE_MEMBERS = {
    "rnatr_stage16al_final_pro_crosscut_audit_pre_remediation_v0.1.0.json":
        "3a3388f3c7849b68399ddd464a05f5f26446ca0f84c52f325ce0707575c34455",
    "rnatr_stage16al_final_pro_crosscut_audit_pre_remediation_v0.1.0.md":
        "a755e849e80803f31f88dd98835f716cfc1fbe85108b8390019b3a0052441b18",
    "rnatr_stage16ah_pro_crosscut_audit_collection_20260817T064303Z.tar.gz":
        "59cf996fd5c95461dfdd24a7ea457aa30a6d0979f89bed149e8ddd81b41909e2",
    "rnatr_stage16ai_safe_hygiene_remediation.result.json":
        "843e87f60566f706824d2a90d31d4410816d0db85e3f82cd5a9d4b4e40416a30",
    "rnatr_stage16aj_development_history_navigation.result.json":
        "cc295ba36d9dfe7d5ce10302a4b398cdeaf0dbe64a8d8ecd7db9b74c9d5cace4",
    "DEVELOPMENT_HISTORY_v0.5.0.md":
        "75484d5cb610103c778afb17d3b4bea94ed6dd4ae4c253d77ad98d801b4b13a0",
    "rnatr_stage16ak_rc_preflight_rebind.result.json":
        "2702e9988633ccdc61580c981b31b5f831a7c24fc2724bbc45b8da5ca31a967f",
    "rnatr_stage16ak_rc_preflight_rebind_bundle_20260817T071839Z.tar.gz":
        "7503de0cbf39167faaa3f06b9dddca181790e40462f66eefcf7a283a22609d79",
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

OLD_GATE_REL = Path("validation/release_gates_v0.3.4.tsv")
NEW_GATE_REL = Path("validation/release_gates_v0.3.5.tsv")
OLD_CANONICAL_README_REL = Path("docs/README_CANONICAL_STRUCTURE_v0.1.1.md")
NEW_CANONICAL_README_REL = Path("docs/README_CANONICAL_STRUCTURE_v0.1.2.md")
CANONICAL_TSV_REL = Path("docs/CURRENT_CANONICAL_STRUCTURE.tsv")
CHANGELOG_REL = Path("CHANGELOG.md")
STAGE_RECORD_REL = Path(
    "docs/release/STAGE16AM_FINAL_PRO_METADATA_REMEDIATION_v0.1.0.md"
)
REGISTRAR_REL = Path(
    "metadata/ssot/rnatr_stage16am_final_pro_metadata_remediation_v0.1.0.py"
)

GATE_UPDATES = {
    "G25": {
        "status": "PASS",
        "evidence_or_next_action": (
            "Stage16X and Stage16AA validated version-pinned GENCODE reference "
            "and public compact-catalog bootstrap with resumable/checksum-verified "
            "network acquisition and standard-resource validation."
        ),
    },
    "G26": {
        "status": "PASS_WITH_DEFINED_SCOPE",
        "evidence_or_next_action": (
            "Stage16Z/Stage16AA detect and record logical CPUs, total/available "
            "RAM, selected tmp directory, tmp free space and working-filesystem "
            "free space. This does not claim a measured full-scale peak-disk minimum."
        ),
    },
    "G27": {
        "status": "PASS_WITH_DEFINED_SCOPE",
        "evidence_or_next_action": (
            "rnatr_resource_policy_v0.1.0 plus actual Tier2 automatic 1/1/2 and "
            "Tier3 automatic 12/3/2 execution achieved exact 5/5 final-table parity; "
            "manual overrides are guarded and recorded. Mapping threads remain a "
            "separately versioned profile."
        ),
    },
    "G28": {
        "status": "PASS_WITH_SCOPE",
        "evidence_or_next_action": (
            "Stage16S/Stage16AA reproduced exact Tier2 five-table scientific output "
            "and SECOND_RESUME_NOOP on a second tested Linux x86-64 host, including "
            "the frozen native kernel. This is not an arbitrary hardware/platform claim."
        ),
    },
    "G29": {
        "status": "PASS",
        "evidence_or_next_action": (
            "Stage16AA completed a fresh authenticated private-GitHub clone, fresh "
            "isolated environment, exact network reference/catalog installation, "
            "automatic Core plan, exact Tier2 5/5 parity and second-resume no-op "
            "with a clean source checkout."
        ),
    },
    "G30": {
        "status": "PASS_WITH_SCOPE_AMENDMENT",
        "evidence_or_next_action": (
            "Tested Linux x86-64 hosts have 24/36 logical CPUs and approximately "
            "128 GB RAM; the current approximately-five-million-read recommendation "
            "is >=24 logical CPU threads, approximately 128 GB RAM and fast local "
            "SSD/NVMe. A lower empirical CPU/RAM minimum remains unestablished and "
            "nonblocking; full-scale peak disk is a separate open benchmark."
        ),
    },
}

CHANGELOG_TEXT = """# Changelog

This changelog summarizes the public RNA-TR-Scout release line. Detailed validation scope, exact evidence identities, and release-engineering records are retained under `docs/release/`, `metadata/ssot/`, and the linked Freeze/golden records.

## [0.5.0] - Unreleased

### Added

- Source-checkout setup and verification for the validated Linux x86-64 environment.
- Public `rnatr-scout run`, `map`, `resources-status`, and `system-info` workflows.
- Automatic checksum-verified GENCODE v50 reference bootstrap and compact GRCh38 repeat-catalog installation.
- CPU/RAM/tmp/free-space detection and conservative automatic Core resource planning.
- Restart/resume and completed-run second-resume no-op behavior.
- User, developer, and development-history navigation.
- BSD-3-Clause software license, `CITATION.cff`, third-party notices, and an explicit Linux-64 conda lock.

### Validated release scope

- Oxford Nanopore cDNA long-read RNA sequencing.
- GRCh38 / GENCODE v50.
- Linux x86-64.
- FASTQ-to-final and compatible mapped-BAM plus source-FASTQ workflows.
- Exact frozen five-table scientific parity on the validated fixtures, including independent second-host validation within the documented scope.

### Important scope limits

- RNA non-observation is not genomic absence.
- The current automatic caller does not completely measure every complex or sequence-variable repeat architecture.
- ONT direct RNA, PacBio Iso-Seq, PacBio Kinnex, and non-x86-64 systems are not yet standard validated profiles.
- Full-scale peak disk usage and a lower empirical full-scale CPU/RAM minimum remain unmeasured.
- Final public release date, immutable tag, release archive, and citation binding will be filled only after the final Pro audit and release binding complete.
"""

CANONICAL_README_TEXT = """# RNA-TR-Scout canonical documentation and Freeze structure

## Current authoritative project-wide locations

- public usage: `README.md` and `docs/USER_GUIDE.md`
- developer navigation: `DEVELOPMENT.md`
- development-history navigation: `docs/history/DEVELOPMENT_HISTORY_v0.5.0.md`
- architecture and formal audits: `docs/architecture/`
- governance and final hygiene: `docs/governance/`
- scientific/interface contracts: `docs/contracts/`
- registered local Core Freeze packet: `docs/core_freeze/v0.1.1/`
- canonical scientific fixtures/base suite: `validation/golden/v0.1.0/`
- final-governance wrapper: `validation/golden/v0.1.1/`
- registered local Freeze snapshot/evidence: `metadata/core_freeze/v0.1.1/`
- current release-gate table: `validation/release_gates_v0.3.5.tsv`
- Git-tracked current SSOT state: `metadata/ssot/CURRENT_STATE.md` and `metadata/ssot/exports/`

## Historical locations

`docs/README_CANONICAL_STRUCTURE_v0.1.1.md`,
`validation/release_gates_v0.3.4.tsv`,
`docs/core_freeze/v0.1.0/`,
`metadata/core_freeze/v0.1.0/`, and earlier release-gate tables remain history or immutable Freeze evidence as applicable. Stage-local documents and scripts remain historical validation/reproducibility evidence unless a current contract or active-path record says otherwise.

No bulk move or deletion is authorized by this registration. Cleanup requires a separate checksum-backed approval.
"""

STAGE_RECORD_TEXT = """# Stage16AM final-Pro metadata remediation v0.1.0

## Status

**PASS_METADATA_ONLY_REMEDIATION — FINAL PRO RE-AUDIT STILL REQUIRED**

## Audit target

- pre-remediation RC head: `fb76836852dd7e9f65a385b3ede72353b2a350c9`
- immutable Core Freeze root: `4b1981db955a8aa92a2a01e19bbb1cfc2aa0ebfb`
- pre-remediation Pro adjudication: `REMEDIATION_REQUIRED_BEFORE_FINAL_PRO_PASS`

## Remediated findings

1. The canonical release-gate table is advanced to `validation/release_gates_v0.3.5.tsv`, with G25-G29 accepted and G30 accepted with its explicit empirical-minimum scope amendment. The v0.3.4 table and Freeze snapshots remain unchanged as history/evidence.
2. The stale active SSOT algorithm contract that described G25-G30 as `DESIGNED_NOT_IMPLEMENTED` is superseded by the scoped accepted state.
3. Stage16AI/AJ/AK and the pre-remediation Pro audit evidence are bound durably into the operational SSOT; the final Pro audit remains open.
4. A root `CHANGELOG.md` is added for the v0.5.0 release line.
5. Current canonical-structure navigation is advanced without moving or deleting historical evidence.

## Safety boundary

This remediation changes no scientific/runtime/package-identity path. It does not modify `src/`, runtime `scripts/`, `config/`, golden fixtures, the native kernel, frozen manifests, or the five-table scientific contract.

## Remaining gate

The exact post-remediation commit must pass archive-based source checks and the final Pro cross-cut audit before final-version conversion, public visibility/tag/release creation, or citation binding.
"""

SECRET_PATTERNS = {
    "PRIVATE_KEY_BLOCK": re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"
    ),
    "GITHUB_TOKEN": re.compile(
        r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b"
    ),
    "AWS_ACCESS_KEY": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
}


class RemediationError(RuntimeError):
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
        raise RemediationError(
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
        raise RemediationError(f"{label} missing/invalid regular file: {path}")
    return path


def write_tsv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(
            fh,
            delimiter="\t",
            fieldnames=fields,
            extrasaction="ignore",
            lineterminator="\n",
        )
        w.writeheader()
        w.writerows(rows)


def load_ssot(path: Path):
    spec = importlib.util.spec_from_file_location(
        "rnatr_ssot_stage16am", path
    )
    if spec is None or spec.loader is None:
        raise RemediationError(f"cannot import SSOT module: {path}")
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
               source_type,path,sha256,bytes,mtime_utc,content_status,ingested_at
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
    key: str,
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
            key,
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
    key: str,
    attempt: str,
    status: str,
    qc_status: str,
    evidence: str,
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
            key,
            None,
            attempt,
            status,
            None,
            evidence,
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
    evidence: str,
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
            "UPDATE decisions SET status='SUPERSEDED' WHERE decision_id=?",
            (old_id,),
        )
    new_id = "decision_" + hashlib.sha256(
        (VERSION + "|" + key).encode()
    ).hexdigest()[:20]
    conn.execute(
        """INSERT OR REPLACE INTO decisions(
               decision_id,decision_key,category,title,statement,status,
               confidence,effective_at,supersedes_decision_id,
               rationale,evidence_path
           ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (
            new_id,
            key,
            category,
            title,
            statement,
            "ACTIVE",
            "HIGH",
            effective_at,
            old_id,
            rationale,
            evidence,
        ),
    )


def add_metric(
    conn: sqlite3.Connection,
    stage_key: str,
    name: str,
    value: str,
    evidence: str,
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
            evidence,
            "CURRENT",
            effective_at,
        ),
    )


def safe_extract_bundle(bundle: Path, target: Path) -> dict[str, Path]:
    target.mkdir(parents=True, exist_ok=True)
    extracted: dict[str, Path] = {}
    with tarfile.open(bundle, "r:gz") as tf:
        members = tf.getmembers()
        names = {m.name for m in members if m.isfile()}
        if names != set(EXPECTED_EVIDENCE_MEMBERS):
            raise RemediationError(
                "evidence bundle member set mismatch: "
                f"observed={sorted(names)} expected={sorted(EXPECTED_EVIDENCE_MEMBERS)}"
            )
        for m in members:
            if not m.isfile() or m.issym() or m.islnk():
                raise RemediationError(
                    f"non-regular evidence bundle member rejected: {m.name}"
                )
            p = Path(m.name)
            if p.is_absolute() or ".." in p.parts:
                raise RemediationError(
                    f"unsafe evidence bundle member path: {m.name}"
                )
        tf.extractall(target)
    for name, digest in EXPECTED_EVIDENCE_MEMBERS.items():
        p = target / name
        if sha256_file(p) != digest:
            raise RemediationError(
                f"evidence member SHA mismatch: {name}"
            )
        extracted[name] = p
    return extracted


def update_release_gates() -> None:
    source = ensure_regular(REPO / OLD_GATE_REL, "current release-gate table")
    target = REPO / NEW_GATE_REL
    if target.exists():
        raise RemediationError(f"new release-gate target already exists: {target}")

    with source.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        fields = reader.fieldnames
        if fields != [
            "gate_id",
            "gate",
            "level",
            "blocking_for_v1",
            "status",
            "evidence_or_next_action",
        ]:
            raise RemediationError(
                f"unexpected release-gate header: {fields}"
            )
        rows = list(reader)

    seen = set()
    for row in rows:
        gate_id = row["gate_id"]
        if gate_id in GATE_UPDATES:
            row.update(GATE_UPDATES[gate_id])
            seen.add(gate_id)
    if seen != set(GATE_UPDATES):
        raise RemediationError(
            f"missing G25-G30 rows in source table: {sorted(set(GATE_UPDATES)-seen)}"
        )
    write_tsv(target, rows, fields)


def update_canonical_structure() -> None:
    old_readme = ensure_regular(
        REPO / OLD_CANONICAL_README_REL,
        "prior canonical structure README",
    )
    if "validation/release_gates_v0.3.4.tsv" not in old_readme.read_text(
        encoding="utf-8"
    ):
        raise RemediationError(
            "prior canonical structure does not identify release_gates_v0.3.4"
        )
    new_readme = REPO / NEW_CANONICAL_README_REL
    if new_readme.exists():
        raise RemediationError(
            f"new canonical structure README already exists: {new_readme}"
        )
    new_readme.write_text(CANONICAL_README_TEXT, encoding="utf-8")

    tsv_path = ensure_regular(
        REPO / CANONICAL_TSV_REL,
        "current canonical structure table",
    )
    with tsv_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        fields = reader.fieldnames
        rows = list(reader)
    if fields != [
        "role", "current_path", "status", "prior_version_or_scope"
    ]:
        raise RemediationError(
            f"unexpected canonical structure header: {fields}"
        )

    found = set()
    for row in rows:
        if row["role"] == "canonical_structure":
            if row["current_path"] != str(OLD_CANONICAL_README_REL):
                raise RemediationError(
                    "unexpected prior canonical_structure pointer"
                )
            row["current_path"] = str(NEW_CANONICAL_README_REL)
            row["prior_version_or_scope"] = (
                f"{OLD_CANONICAL_README_REL} retained as prior registered "
                "navigation state"
            )
            found.add("canonical_structure")
        elif row["role"] == "release_gates":
            if row["current_path"] != str(OLD_GATE_REL):
                raise RemediationError(
                    "unexpected prior release_gates pointer"
                )
            row["current_path"] = str(NEW_GATE_REL)
            row["prior_version_or_scope"] = (
                f"{OLD_GATE_REL} retained as Local Core Freeze-era history"
            )
            found.add("release_gates")
    if found != {"canonical_structure", "release_gates"}:
        raise RemediationError(
            f"canonical pointer rows missing: {found}"
        )
    write_tsv(tsv_path, rows, fields)


def update_public_docs() -> None:
    changelog = REPO / CHANGELOG_REL
    if changelog.exists():
        raise RemediationError("root CHANGELOG.md already exists")
    changelog.write_text(CHANGELOG_TEXT, encoding="utf-8")

    readme_path = ensure_regular(REPO / "README.md", "README")
    readme = readme_path.read_text(encoding="utf-8")
    anchor = (
        "- [Development history](docs/history/DEVELOPMENT_HISTORY_v0.5.0.md) "
        "— narrative map of how the project reached the v0.5.0 release line\n"
    )
    if anchor not in readme:
        raise RemediationError("README changelog insertion anchor missing")
    readme = readme.replace(
        anchor,
        anchor
        + "- [Changelog](CHANGELOG.md) — concise public release-line summary\n",
        1,
    )
    readme_path.write_text(readme, encoding="utf-8")

    history_path = ensure_regular(
        REPO / "docs/history/DEVELOPMENT_HISTORY_v0.5.0.md",
        "development history",
    )
    history = history_path.read_text(encoding="utf-8")
    if history.count("releaseable software") != 1:
        raise RemediationError(
            "expected exactly one releaseable-software editorial token"
        )
    history_path.write_text(
        history.replace("releaseable software", "releasable software", 1),
        encoding="utf-8",
    )

    stage16ae_path = ensure_regular(
        REPO / "docs/release/STAGE16AE_PUBLIC_RELEASE_PACKAGING_v0.1.0.md",
        "Stage16AE record",
    )
    stage16ae = stage16ae_path.read_text(encoding="utf-8")
    anchor2 = (
        "- [x] create v0.5.0-rc1 release-notes draft;\n"
    )
    if anchor2 not in stage16ae:
        raise RemediationError(
            "Stage16AE changelog checklist anchor missing"
        )
    stage16ae = stage16ae.replace(
        anchor2,
        anchor2 + "- [x] add root `CHANGELOG.md` for the public release line;\n",
        1,
    )
    stage16ae_path.write_text(stage16ae, encoding="utf-8")

    record_path = REPO / STAGE_RECORD_REL
    if record_path.exists():
        raise RemediationError(
            f"Stage16AM record already exists: {record_path}"
        )
    record_path.write_text(STAGE_RECORD_TEXT, encoding="utf-8")


def copy_registrar_source() -> None:
    target = REPO / REGISTRAR_REL
    if target.exists():
        raise RemediationError(
            f"Stage16AM registrar target already exists: {target}"
        )
    source = Path(__file__).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


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
    raise RemediationError("no suitable Python found for archive smoke")


def markdown_link_check(root: Path, rel: str) -> tuple[int, list[str]]:
    path = root / rel
    text = path.read_text(encoding="utf-8")
    links = re.findall(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", text)
    checked = 0
    broken: list[str] = []
    for raw in links:
        target = raw.strip()
        if not target or target.startswith("#") or "://" in target:
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


def text_files_for_secret_scan() -> list[Path]:
    paths: list[Path] = []
    tracked = git("ls-files", "--cached", "-z").split("\0")
    for rel in tracked:
        if not rel:
            continue
        p = REPO / rel
        if not p.is_file() or p.stat().st_size > 8 * 1024 * 1024:
            continue
        if p.suffix.lower() not in {
            ".py", ".sh", ".md", ".txt", ".tsv", ".csv", ".json",
            ".toml", ".yml", ".yaml", ".cff", ".ini", ".cfg", ".conf",
        } and p.name not in {
            "README.md", "LICENSE", "CITATION.cff",
            "THIRD_PARTY_NOTICES.md", "CHANGELOG.md",
        }:
            continue
        data = p.read_bytes()
        if b"\x00" not in data:
            paths.append(p)
    return paths


def prospective_archive_smoke(
    tree_sha: str,
    out: Path,
) -> dict[str, Any]:
    archive = out / "prospective_source.tar"
    with archive.open("wb") as fh:
        p = subprocess.run(
            ["git", "-C", str(REPO), "archive", "--format=tar", tree_sha],
            stdout=fh,
            stderr=subprocess.PIPE,
            check=False,
        )
    if p.returncode != 0:
        raise RemediationError(
            "git archive failed: "
            + p.stderr.decode("utf-8", errors="replace")
        )
    archive_sha = sha256_file(archive)
    archive_bytes = archive.stat().st_size
    py = find_test_python()
    logs: dict[str, str] = {}

    with tempfile.TemporaryDirectory(
        prefix="rnatr_stage16am_archive_"
    ) as td:
        src = Path(td) / "source"
        src.mkdir()
        with tarfile.open(archive, "r") as tf:
            for m in tf.getmembers():
                p = Path(m.name)
                if p.is_absolute() or ".." in p.parts:
                    raise RemediationError(
                        f"unsafe prospective archive member: {m.name}"
                    )
            tf.extractall(src)

        env = os.environ.copy()
        env["PYTHONPATH"] = str(src / "src")
        env["RNATR_PROJECT_ROOT"] = str(src)
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
            p = run(argv, cwd=src, env=env, check=False)
            logs[name] = p.stdout
            (out / f"{name}.log").write_text(
                p.stdout, encoding="utf-8"
            )
            if p.returncode != 0:
                raise RemediationError(
                    f"prospective archive {name} failed rc={p.returncode}"
                )

        if logs["cli_version"].strip() != EXPECTED_PACKAGE_VERSION:
            raise RemediationError(
                f"prospective CLI version mismatch: {logs['cli_version']!r}"
            )
        for token in ("run", "map", "resources-status", "system-info"):
            if token not in logs["cli_help"]:
                raise RemediationError(
                    f"prospective CLI help missing public command: {token}"
                )
        if "PASS_NATIVE_LOAD" not in logs["native_load"]:
            raise RemediationError("prospective native-load marker missing")

    archive.unlink()
    return {
        "tree_sha": tree_sha,
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


def restore_precommit_state(db: Path, backup: Path) -> None:
    try:
        run(
            ["git", "-C", str(REPO), "reset", "--hard", EXPECTED_HEAD],
            check=False,
        )
        for rel in (
            NEW_GATE_REL,
            NEW_CANONICAL_README_REL,
            CHANGELOG_REL,
            STAGE_RECORD_REL,
            REGISTRAR_REL,
        ):
            p = REPO / rel
            if p.exists():
                if p.is_dir():
                    shutil.rmtree(p)
                else:
                    p.unlink()
        if backup.is_file():
            shutil.copy2(backup, db)
    except Exception:
        pass


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Apply the metadata-only remediation required by the pre-remediation "
            "final Pro audit and create a post-remediation exact RC preflight."
        )
    )
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    print("===== RNA-TR-SCOUT STAGE16AM FINAL-PRO METADATA REMEDIATION =====")
    print(f"version\t{VERSION}")
    print(f"mode\t{'EXECUTE' if args.execute else 'PREFLIGHT'}")

    ensure_regular(EVIDENCE_BUNDLE, "Stage16AL evidence bundle")
    if sha256_file(EVIDENCE_BUNDLE) != EVIDENCE_BUNDLE_SHA256:
        raise RemediationError("Stage16AL evidence bundle SHA mismatch")

    run(["git", "-C", str(REPO), "fetch", "origin", "--tags"])
    branch = git("branch", "--show-current").strip()
    head = git("rev-parse", "HEAD").strip()
    remote = git("rev-parse", f"origin/{BRANCH}").strip()
    status = run(
        [
            "git", "-C", str(REPO),
            "status", "--porcelain=v1", "--untracked-files=all",
        ]
    ).stdout.strip()

    if branch != BRANCH:
        raise RemediationError(f"expected branch {BRANCH}; observed {branch}")
    if head != EXPECTED_HEAD or remote != EXPECTED_HEAD:
        raise RemediationError(
            f"head drift: local={head} remote={remote} expected={EXPECTED_HEAD}"
        )
    if status:
        raise RemediationError("working tree must be clean:\n" + status)
    if run(
        [
            "git", "-C", str(REPO),
            "merge-base", "--is-ancestor", FREEZE_ROOT, head,
        ],
        check=False,
    ).returncode != 0:
        raise RemediationError("Freeze root ancestry failed")

    # Pre-remediation file-state guards.
    for rel in (
        NEW_GATE_REL,
        NEW_CANONICAL_README_REL,
        CHANGELOG_REL,
        STAGE_RECORD_REL,
        REGISTRAR_REL,
    ):
        if (REPO / rel).exists():
            raise RemediationError(
                f"unexpected pre-existing remediation target: {rel}"
            )

    old_gate = ensure_regular(REPO / OLD_GATE_REL, "release_gates_v0.3.4")
    with old_gate.open("r", encoding="utf-8", newline="") as fh:
        gate_rows = {
            row["gate_id"]: row
            for row in csv.DictReader(fh, delimiter="\t")
        }
    for gate in GATE_UPDATES:
        if gate_rows.get(gate, {}).get("status") != "OPEN_PLANNED":
            raise RemediationError(
                f"unexpected pre-remediation {gate} state: "
                f"{gate_rows.get(gate)}"
            )

    canonical_tsv = ensure_regular(
        REPO / CANONICAL_TSV_REL, "canonical structure table"
    ).read_text(encoding="utf-8")
    if str(OLD_GATE_REL) not in canonical_tsv:
        raise RemediationError("current canonical release-gate pointer is not v0.3.4")

    if "releaseable software" not in ensure_regular(
        REPO / "docs/history/DEVELOPMENT_HISTORY_v0.5.0.md",
        "development history",
    ).read_text(encoding="utf-8"):
        raise RemediationError(
            "expected development-history editorial token is absent"
        )

    # Package identity guard.
    if sha256_file(REPO / "LICENSE") != EXPECTED_LICENSE_SHA256:
        raise RemediationError("LICENSE SHA drift")
    if sha256_file(
        REPO / "environment-linux-64.lock.txt"
    ) != EXPECTED_LOCK_SHA256:
        raise RemediationError("explicit lock SHA drift")
    native = (
        REPO
        / "src/rnatr_scout/general_caller/native_v0.4.1/"
        "librnatr_native_periodic_kernel_v0.1.0.so"
    )
    if sha256_file(native) != EXPECTED_NATIVE_SHA256:
        raise RemediationError("native kernel SHA drift")
    if f'version = "{EXPECTED_PACKAGE_VERSION}"' not in (
        REPO / "pyproject.toml"
    ).read_text(encoding="utf-8"):
        raise RemediationError("package version drift")
    if f"version: {EXPECTED_CFF_VERSION}" not in (
        REPO / "CITATION.cff"
    ).read_text(encoding="utf-8"):
        raise RemediationError("CITATION version drift")

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
            raise RemediationError("SSOT integrity preflight failed")
        if list(conn.execute("PRAGMA foreign_key_check")):
            raise RemediationError("SSOT foreign-key preflight failed")
        stale = list(
            conn.execute(
                "SELECT contract_id,implementation_state,status "
                "FROM algorithm_contracts "
                "WHERE component_key='release_readiness_g25_g30_v0_1_0' "
                "AND status='ACTIVE'"
            )
        )
        if (
            len(stale) != 1
            or stale[0]["implementation_state"] != "DESIGNED_NOT_IMPLEMENTED"
        ):
            raise RemediationError(
                f"unexpected stale algorithm-contract precondition: {stale}"
            )
        q = conn.execute(
            "SELECT status,blocking FROM open_questions "
            "WHERE question_key='PUBLIC_RC_PRO_CROSSCUT_AUDIT'"
        ).fetchone()
        if not q or q["status"] != "OPEN" or int(q["blocking"]) != 1:
            raise RemediationError(
                f"unexpected final-Pro open-question state: {q}"
            )

    print("git_exact_head\tPASS")
    print("freeze_ancestry\tPASS")
    print("evidence_bundle\tPASS")
    print("stale_release_gate_table_precondition\tPASS")
    print("stale_algorithm_contract_precondition\tPASS")
    print("package_identity\tPASS")
    print("ssot_preflight\tPASS")
    print("planned_runtime_or_scientific_change\tfalse")
    print("planned_file_move_delete\tfalse")

    if not args.execute:
        print("status\tPREFLIGHT_PASS_READY_FOR_EXECUTE")
        return 0

    effective_at = utc_now()
    checkpoint = (
        ssot_root
        / "checkpoints/stage16am_final_pro_metadata_remediation_v0.1.0"
        / effective_at.replace(":", "").replace("+00:00", "Z")
    )
    originals = checkpoint / "originals"
    backups = checkpoint / "backups"
    originals.mkdir(parents=True, exist_ok=False)
    backups.mkdir(parents=True, exist_ok=True)

    durable_bundle = originals / EVIDENCE_BUNDLE.name
    shutil.copy2(EVIDENCE_BUNDLE, durable_bundle)
    if sha256_file(durable_bundle) != EVIDENCE_BUNDLE_SHA256:
        raise RemediationError("durable audit bundle SHA mismatch")
    evidence = safe_extract_bundle(durable_bundle, originals / "extracted")

    pre_db_sha = sha256_file(db)
    backup = backups / "rnatr_ssot.pre_stage16am.sqlite"
    shutil.copy2(db, backup)
    if sha256_file(backup) != pre_db_sha:
        raise RemediationError("SSOT backup SHA mismatch")

    pushed = False
    try:
        update_release_gates()
        update_canonical_structure()
        update_public_docs()
        copy_registrar_source()

        audit_json = evidence[
            "rnatr_stage16al_final_pro_crosscut_audit_pre_remediation_v0.1.0.json"
        ]
        audit_md = evidence[
            "rnatr_stage16al_final_pro_crosscut_audit_pre_remediation_v0.1.0.md"
        ]
        stage16ai = evidence[
            "rnatr_stage16ai_safe_hygiene_remediation.result.json"
        ]
        stage16aj = evidence[
            "rnatr_stage16aj_development_history_navigation.result.json"
        ]
        stage16ak = evidence[
            "rnatr_stage16ak_rc_preflight_rebind.result.json"
        ]

        # Validate evidence semantics, not just bytes.
        audit_obj = json.loads(audit_json.read_text(encoding="utf-8"))
        if audit_obj.get("status") != "REMEDIATION_REQUIRED_BEFORE_FINAL_PRO_PASS":
            raise RemediationError("unexpected Stage16AL audit status")
        if (
            audit_obj.get("audit_target", {}).get("candidate_head")
            != EXPECTED_HEAD
        ):
            raise RemediationError("Stage16AL audit target mismatch")
        ak_obj = json.loads(stage16ak.read_text(encoding="utf-8"))
        if (
            ak_obj.get("status")
            != "PASS_STAGE16AK_RC_PREFLIGHT_REBOUND_TO_CURRENT_HEAD"
            or ak_obj.get("candidate_head") != EXPECTED_HEAD
        ):
            raise RemediationError("Stage16AK evidence semantic mismatch")

        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            conn.execute("BEGIN IMMEDIATE")

            for typ, p in (
                ("stage16al_final_pro_audit_pre_remediation_json", audit_json),
                ("stage16al_final_pro_audit_pre_remediation_markdown", audit_md),
                ("stage16ai_safe_hygiene_result", stage16ai),
                ("stage16aj_development_history_result", stage16aj),
                ("stage16ak_rc_preflight_rebind_result", stage16ak),
                ("stage16am_audit_evidence_bundle", durable_bundle),
                ("stage16am_release_gate_table", REPO / NEW_GATE_REL),
                ("stage16am_changelog", REPO / CHANGELOG_REL),
                ("stage16am_canonical_structure", REPO / NEW_CANONICAL_README_REL),
                ("stage16am_remediation_record", REPO / STAGE_RECORD_REL),
                ("stage16am_registrar", REPO / REGISTRAR_REL),
            ):
                source_document(conn, p, typ, effective_at)

            stages = [
                (
                    "16AI_REPOSITORY_HYGIENE",
                    179.0,
                    "Stage16AI repository hygiene remediation",
                    "Shorten public resource wording, establish public/internal script boundaries, add developer navigation and repair stale current SSOT metrics without runtime change.",
                    "VALIDATED",
                    "Documentation/SSOT-only PASS; no file move/delete or scientific/runtime change.",
                ),
                (
                    "16AJ_DEVELOPMENT_HISTORY_NAVIGATION",
                    180.0,
                    "Stage16AJ development-history navigation",
                    "Add a non-authoritative history narrative and clarify operational SQLite SSOT versus Git-tracked exports.",
                    "VALIDATED",
                    "PASS; history is navigation, not SSOT or contract.",
                ),
                (
                    "16AK_RC_PREFLIGHT_REBIND",
                    181.0,
                    "Stage16AK exact RC preflight rebind",
                    "Rebind archive/unit/CLI/native/SSOT/link/secret checks to exact candidate fb768368 after documentation-only changes.",
                    "VALIDATED",
                    "PASS for exact head fb76836852dd7e9f65a385b3ede72353b2a350c9.",
                ),
                (
                    "16AL_FINAL_PRO_CROSSCUT_AUDIT",
                    182.0,
                    "Stage16AL final Pro cross-cut audit",
                    "Adjudicate Freeze, runtime, packaging, resources, validation, documentation, repository hygiene and SSOT/Git/docs consistency.",
                    "REMEDIATION_REQUIRED",
                    "No scientific failure; four metadata/governance packaging blockers require correction before final PASS.",
                ),
                (
                    "16AM_FINAL_PRO_METADATA_REMEDIATION",
                    183.0,
                    "Stage16AM final-Pro metadata remediation",
                    "Resolve canonical release-gate, algorithm-contract, exact RC evidence-binding and CHANGELOG findings without scientific/runtime mutation.",
                    "VALIDATED",
                    "Metadata-only remediation; final Pro re-audit remains OPEN.",
                ),
            ]
            for row in stages:
                ensure_stage(conn, *row)

            add_run_stage(
                conn,
                "16AI_REPOSITORY_HYGIENE",
                "v0.1.1",
                "PASS",
                "PASS",
                str(stage16ai),
                "README/USER_GUIDE/DEVELOPMENT and stale-current-metric remediation PASS; runtime/scientific Core unchanged.",
                effective_at,
            )
            add_run_stage(
                conn,
                "16AJ_DEVELOPMENT_HISTORY_NAVIGATION",
                "v0.1.1",
                "PASS",
                "PASS",
                str(stage16aj),
                "Development-history navigation and operational-SSOT explanation PASS; links validated.",
                effective_at,
            )
            add_run_stage(
                conn,
                "16AK_RC_PREFLIGHT_REBIND",
                "v0.1.0",
                "PASS",
                "PASS",
                str(stage16ak),
                "Exact current-head archive compile/unit/CLI/native, SSOT identity, link and secret checks PASS.",
                effective_at,
            )
            add_run_stage(
                conn,
                "16AL_FINAL_PRO_CROSSCUT_AUDIT",
                "v0.1.0",
                "REMEDIATION_REQUIRED",
                "REVIEW",
                str(audit_json),
                "Scientific/runtime domains pass; current release-gate table, active G25-G30 algorithm contract, exact RC SSOT binding and root CHANGELOG require remediation.",
                effective_at,
            )
            add_run_stage(
                conn,
                "16AM_FINAL_PRO_METADATA_REMEDIATION",
                "v0.1.0",
                "PASS",
                "PASS",
                str(REPO / STAGE_RECORD_REL),
                "P1-P4 metadata/governance findings remediated without runtime/scientific mutation; final Pro re-audit remains blocking.",
                effective_at,
            )

            # Supersede the stale active release-readiness algorithm contract.
            old = conn.execute(
                "SELECT contract_id FROM algorithm_contracts "
                "WHERE component_key='release_readiness_g25_g30_v0_1_0' "
                "AND status='ACTIVE'"
            ).fetchone()
            if not old:
                raise RemediationError(
                    "stale active G25-G30 algorithm contract disappeared"
                )
            old_id = old["contract_id"]
            conn.execute(
                "UPDATE algorithm_contracts SET status='SUPERSEDED' "
                "WHERE contract_id=?",
                (old_id,),
            )
            new_contract_id = "contract_" + hashlib.sha256(
                (VERSION + "|release_readiness_g25_g30_v0_2_0").encode()
            ).hexdigest()[:20]
            conn.execute(
                """INSERT INTO algorithm_contracts(
                       contract_id,component_key,component_name,
                       implementation_state,contract_statement,
                       active_implementation_id,evidence_path,
                       effective_at,status
                   ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    new_contract_id,
                    "release_readiness_g25_g30_v0_1_0",
                    "Internal-beta release readiness G25-G30",
                    "PASS_G25_G29_G30_WITH_SCOPE_AMENDMENT",
                    (
                        "G25 reference bootstrap and checksum-verified resource "
                        "acquisition, G26 system-resource detection, G27 memory-aware "
                        "Core planning, G28 scoped Linux x86-64 cross-hardware parity "
                        "and G29 independent fresh clone/setup/test are accepted. "
                        "G30 tested and recommended profiles are accepted while a "
                        "lower empirical full-scale minimum remains explicitly "
                        "unmeasured and nonblocking."
                    ),
                    None,
                    str(
                        REPO
                        / "docs/release/"
                        "STAGE16AB_G25_G30_RELEASE_READINESS_ADJUDICATION_v0.1.0.md"
                    ),
                    effective_at,
                    "ACTIVE",
                ),
            )

            superseding_decision(
                conn,
                "stage16t_user_facing_documentation_acceptance_v0_1_0",
                "documentation",
                "Accept current v0.5.0 RC user/developer/history navigation",
                (
                    "Accept the current README and USER_GUIDE as the ordinary-user "
                    "surface, DEVELOPMENT.md as navigation to current contracts/SSOT "
                    "and post-Freeze lanes, and DEVELOPMENT_HISTORY_v0.5.0.md as "
                    "non-authoritative historical navigation. Stage-numbered files "
                    "remain validation/reproducibility history rather than ordinary "
                    "user entry points."
                ),
                (
                    "Stage16AI/AJ owner-reviewed documentation-only changes improved "
                    "usability and future-development continuity without changing "
                    "runtime or scientific semantics."
                ),
                str(stage16aj),
                effective_at,
            )
            superseding_decision(
                conn,
                "release_candidate_ready_for_final_pro_audit_v0_1_0",
                "release_readiness",
                "Current RC ready for final Pro re-audit after metadata remediation",
                (
                    "The exact post-remediation RC remains scientifically identical "
                    "to the Stage16AF-tested candidate. Canonical gate/SSOT/CHANGELOG "
                    "drift is repaired; PUBLIC_RC_PRO_CROSSCUT_AUDIT remains OPEN "
                    "until an independent final re-audit passes."
                ),
                (
                    "Stage16AK proves exact current-head source checks, and Stage16AM "
                    "changes only release-governance/documentation/SSOT metadata."
                ),
                str(REPO / STAGE_RECORD_REL),
                effective_at,
            )
            superseding_decision(
                conn,
                "canonical_release_gate_table_v0_3_5",
                "release_governance",
                "Promote release-gate table v0.3.5 as current",
                (
                    "Use validation/release_gates_v0.3.5.tsv as the current release-"
                    "gate table. It preserves prior gates and records the formal "
                    "G25-G30 Stage16AB adjudication; v0.3.4 remains historical/Freeze-"
                    "era evidence."
                ),
                "The prior current pointer contradicted accepted Stage16 evidence.",
                str(REPO / NEW_GATE_REL),
                effective_at,
            )
            superseding_decision(
                conn,
                "public_rc_pro_audit_pre_remediation_v0_1_0",
                "release_governance",
                "Record final Pro pre-remediation adjudication",
                (
                    "The first final Pro adjudication found no scientific/runtime "
                    "failure but required four metadata/governance packaging "
                    "remediations before final PASS."
                ),
                (
                    "Canonical gate and algorithm-contract drift, exact RC evidence "
                    "binding, and root CHANGELOG completeness required correction."
                ),
                str(audit_json),
                effective_at,
            )

            audit_update = conn.execute(
                """UPDATE open_questions
                   SET evidence_path=?,next_action=?,effective_at=?
                   WHERE question_key='PUBLIC_RC_PRO_CROSSCUT_AUDIT'
                     AND status='OPEN'""",
                (
                    str(REPO / STAGE_RECORD_REL),
                    (
                        "Run the independent final Pro cross-cut re-audit against the "
                        "exact post-Stage16AM commit/tree/source-archive evidence. Do "
                        "not convert to final 0.5.0 or create a public tag/release "
                        "until that re-audit passes."
                    ),
                    effective_at,
                ),
            )
            if audit_update.rowcount != 1:
                raise RemediationError(
                    "failed to update PUBLIC_RC_PRO_CROSSCUT_AUDIT"
                )

            conn.execute(
                """UPDATE open_questions
                   SET next_action=?,effective_at=?
                   WHERE question_key='CORE_FREEZE_GIT_TAG_AND_PUBLIC_RELEASE_BINDING'
                     AND status='OPEN'""",
                (
                    (
                        "After the final Pro re-audit passes, convert RC metadata to "
                        "0.5.0, integrate the exact release commit into main, make the "
                        "repository public, perform an unauthenticated public-source "
                        "clone/setup smoke, create and verify the immutable v0.5.0 "
                        "tag/release/source checksums, and verify citation binding."
                    ),
                    effective_at,
                ),
            )

            conn.execute(
                """UPDATE limitations
                   SET statement=?,mitigation=?,evidence_path=?,effective_at=?
                   WHERE limitation_key='PUBLIC_V050_RELEASE_NOT_YET_COMPLETE'
                     AND status='ACTIVE'""",
                (
                    (
                        "The repository remains a private pre-release RC and no final "
                        "RNA-TR-Scout v0.5.0 public tag/release has been created."
                    ),
                    (
                        "Complete the final Pro re-audit, final metadata conversion, "
                        "main integration, public visibility/unauthenticated clone "
                        "smoke, immutable tag/release/source checksums and citation "
                        "binding before declaring v0.5.0."
                    ),
                    str(REPO / STAGE_RECORD_REL),
                    effective_at,
                ),
            )

            metrics = [
                (
                    "16AK_RC_PREFLIGHT_REBIND",
                    "candidate_head",
                    EXPECTED_HEAD,
                    str(stage16ak),
                ),
                (
                    "16AK_RC_PREFLIGHT_REBIND",
                    "candidate_tree",
                    json.loads(stage16ak.read_text())["candidate_tree"],
                    str(stage16ak),
                ),
                (
                    "16AK_RC_PREFLIGHT_REBIND",
                    "archive_source_sha256",
                    json.loads(stage16ak.read_text())["archive_source_sha256"],
                    str(stage16ak),
                ),
                (
                    "16AK_RC_PREFLIGHT_REBIND",
                    "rc_preflight_status",
                    "PASS",
                    str(stage16ak),
                ),
                (
                    "16AL_FINAL_PRO_CROSSCUT_AUDIT",
                    "pre_remediation_audit_status",
                    "REMEDIATION_REQUIRED_BEFORE_FINAL_PRO_PASS",
                    str(audit_json),
                ),
                (
                    "16AL_FINAL_PRO_CROSSCUT_AUDIT",
                    "blocking_metadata_findings",
                    "4",
                    str(audit_json),
                ),
                (
                    "16AM_FINAL_PRO_METADATA_REMEDIATION",
                    "current_release_gate_table",
                    "validation/release_gates_v0.3.5.tsv",
                    str(REPO / NEW_GATE_REL),
                ),
                (
                    "16AM_FINAL_PRO_METADATA_REMEDIATION",
                    "g25_g30_contract_status",
                    "PASS_G25_G29_G30_WITH_SCOPE_AMENDMENT",
                    str(REPO / STAGE_RECORD_REL),
                ),
                (
                    "16AM_FINAL_PRO_METADATA_REMEDIATION",
                    "root_changelog_status",
                    "PRESENT",
                    str(REPO / CHANGELOG_REL),
                ),
                (
                    "16AM_FINAL_PRO_METADATA_REMEDIATION",
                    "runtime_scientific_change",
                    "false",
                    str(REPO / STAGE_RECORD_REL),
                ),
            ]
            for stage_key, name, value, evidence_path in metrics:
                add_metric(
                    conn,
                    stage_key,
                    name,
                    value,
                    evidence_path,
                    effective_at,
                )

            conn.commit()

            ssot = load_ssot(ssot_py)
            checks = ssot.validate_db(conn, PROJECT)
            failed = [row for row in checks if row[1] == "FAIL"]
            if failed:
                raise RemediationError(
                    f"post-remediation SSOT validation failed: {failed}"
                )
            exports = ssot.export_views(conn, ssot_root)
            ssot.write_summary(conn, ssot_root, checks, exports)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        # Sync generated SSOT state to Git.
        shutil.copy2(
            ssot_root / "CURRENT_STATE.md",
            REPO / "metadata/ssot/CURRENT_STATE.md",
        )
        for p in (ssot_root / "exports").glob("*.tsv"):
            shutil.copy2(
                p,
                REPO / "metadata/ssot/exports" / p.name,
            )

        # Verify changed-file scope before staging.
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
            "README.md",
            "CHANGELOG.md",
            "docs/history/DEVELOPMENT_HISTORY_v0.5.0.md",
            str(CANONICAL_TSV_REL),
            str(NEW_CANONICAL_README_REL),
            "docs/release/STAGE16AE_PUBLIC_RELEASE_PACKAGING_v0.1.0.md",
            str(STAGE_RECORD_REL),
            str(NEW_GATE_REL),
            str(REGISTRAR_REL),
            "metadata/ssot/CURRENT_STATE.md",
        }
        unexpected = sorted(
            p
            for p in changed_paths
            if p not in exact_allowed
            and not p.startswith("metadata/ssot/exports/")
        )
        if unexpected:
            raise RemediationError(
                "unexpected changed paths:\n" + "\n".join(unexpected)
            )
        forbidden = sorted(
            p
            for p in changed_paths
            if p.startswith(("src/", "config/", "validation/golden/", "tests/"))
            or (
                p.startswith("scripts/")
                and p != str(REGISTRAR_REL)
            )
        )
        if forbidden:
            raise RemediationError(
                "runtime/scientific paths changed:\n" + "\n".join(forbidden)
            )

        run(["git", "-C", str(REPO), "diff", "--check"])

        # TSV structure.
        for p in sorted(
            (REPO / "metadata/ssot/exports").glob("*.tsv")
        ) + [REPO / NEW_GATE_REL, REPO / CANONICAL_TSV_REL]:
            with p.open("r", encoding="utf-8", newline="") as fh:
                r = csv.reader(fh, delimiter="\t")
                try:
                    header = next(r)
                except StopIteration:
                    raise RemediationError(f"empty TSV: {p}")
                for line_no, row in enumerate(r, start=2):
                    if len(row) != len(header):
                        raise RemediationError(
                            f"TSV field-count mismatch {p}:{line_no}"
                        )

        # Explicit newline hygiene guard: repository TSVs created/rewritten by
        # Stage16AM must use LF-only line endings. A CR byte would be reported by
        # `git diff --check` as trailing whitespace.
        newline_guard_paths = [
            REPO / NEW_GATE_REL,
            REPO / CANONICAL_TSV_REL,
        ] + sorted((REPO / "metadata/ssot/exports").glob("*.tsv"))
        crlf_offenders = [
            str(p.relative_to(REPO))
            for p in newline_guard_paths
            if b"\r" in p.read_bytes()
        ]
        if crlf_offenders:
            raise RemediationError(
                "CR bytes remain in generated/reconciled TSV files:\n"
                + "\n".join(crlf_offenders)
            )

        # Gate and pointer exactness.
        with (REPO / NEW_GATE_REL).open(
            "r", encoding="utf-8", newline=""
        ) as fh:
            rows = {
                row["gate_id"]: row
                for row in csv.DictReader(fh, delimiter="\t")
            }
        for gate, expected in GATE_UPDATES.items():
            if rows[gate]["status"] != expected["status"]:
                raise RemediationError(
                    f"post-remediation {gate} status mismatch"
                )
        pointer_text = (REPO / CANONICAL_TSV_REL).read_text(
            encoding="utf-8"
        )
        if str(NEW_GATE_REL) not in pointer_text:
            raise RemediationError("canonical gate pointer not advanced")

        # SSOT current algorithm contract exactness.
        with sqlite3.connect(str(db)) as check_conn:
            check_conn.row_factory = sqlite3.Row
            current_contract = list(
                check_conn.execute(
                    "SELECT implementation_state FROM current_algorithm_contract "
                    "WHERE component_key='release_readiness_g25_g30_v0_1_0'"
                )
            )
            if (
                len(current_contract) != 1
                or current_contract[0]["implementation_state"]
                != "PASS_G25_G29_G30_WITH_SCOPE_AMENDMENT"
            ):
                raise RemediationError(
                    f"current G25-G30 algorithm contract mismatch: "
                    f"{current_contract}"
                )
            q = check_conn.execute(
                "SELECT status,blocking FROM open_questions "
                "WHERE question_key='PUBLIC_RC_PRO_CROSSCUT_AUDIT'"
            ).fetchone()
            if not q or q["status"] != "OPEN" or int(q["blocking"]) != 1:
                raise RemediationError(
                    "final Pro audit gate was closed prematurely"
                )

        # Project SSOT exports must be identical to Git working copies.
        for p in (ssot_root / "exports").glob("*.tsv"):
            repo_p = REPO / "metadata/ssot/exports" / p.name
            if sha256_file(p) != sha256_file(repo_p):
                raise RemediationError(
                    f"SSOT export identity mismatch: {p.name}"
                )
        if sha256_file(
            ssot_root / "CURRENT_STATE.md"
        ) != sha256_file(REPO / "metadata/ssot/CURRENT_STATE.md"):
            raise RemediationError("CURRENT_STATE identity mismatch")

        # Markdown local links.
        link_rows: list[dict[str, Any]] = []
        for rel in (
            "README.md",
            "DEVELOPMENT.md",
            "docs/USER_GUIDE.md",
            "docs/history/DEVELOPMENT_HISTORY_v0.5.0.md",
            str(NEW_CANONICAL_README_REL),
            str(STAGE_RECORD_REL),
            "CHANGELOG.md",
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
                raise RemediationError(
                    f"broken Markdown links in {rel}: {broken}"
                )

        # Stage exactly the expected repository changes.
        add_paths = [
            "README.md",
            "CHANGELOG.md",
            "docs/history/DEVELOPMENT_HISTORY_v0.5.0.md",
            str(CANONICAL_TSV_REL),
            str(NEW_CANONICAL_README_REL),
            "docs/release/STAGE16AE_PUBLIC_RELEASE_PACKAGING_v0.1.0.md",
            str(STAGE_RECORD_REL),
            str(NEW_GATE_REL),
            str(REGISTRAR_REL),
            "metadata/ssot/CURRENT_STATE.md",
            "metadata/ssot/exports",
        ]
        run(["git", "-C", str(REPO), "add", *add_paths])
        run(["git", "-C", str(REPO), "diff", "--cached", "--check"])

        staged = run(
            [
                "git", "-C", str(REPO),
                "diff", "--cached", "--name-only",
            ]
        ).stdout.splitlines()
        forbidden_staged = [
            p for p in staged
            if p.startswith(("src/", "config/", "validation/golden/", "tests/"))
            or p.startswith("scripts/")
        ]
        if forbidden_staged:
            raise RemediationError(
                "forbidden staged paths:\n" + "\n".join(forbidden_staged)
            )

        prospective_tree = git("write-tree").strip()

        evidence_out = (
            RELEASE_ROOT
            / (
                "stage16am_final_pro_metadata_remediation_"
                + effective_at.replace(":", "").replace("+00:00", "Z")
            )
        )
        evidence_out.mkdir(parents=True, exist_ok=False)

        # Secret scan includes staged new files.
        secret_hits: list[dict[str, Any]] = []
        for p in text_files_for_secret_scan():
            text = p.read_text(encoding="utf-8", errors="replace")
            rel = p.relative_to(REPO).as_posix()
            for label, regex in SECRET_PATTERNS.items():
                for m in regex.finditer(text):
                    secret_hits.append(
                        {
                            "path": rel,
                            "line": text.count("\n", 0, m.start()) + 1,
                            "pattern": label,
                        }
                    )
        write_tsv(
            evidence_out / "high_confidence_secret_hits.tsv",
            secret_hits,
            ["path", "line", "pattern"],
        )
        if secret_hits:
            raise RemediationError(
                f"high-confidence secret hits found: {secret_hits}"
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
            prospective_tree,
            evidence_out,
        )

        # Commit only after prospective exact-tree tests pass.
        run(
            [
                "git", "-C", str(REPO), "commit",
                "-m",
                "Reconcile final Pro audit metadata and release gates",
            ]
        )
        post_head = git("rev-parse", "HEAD").strip()
        post_tree = git("rev-parse", "HEAD^{tree}").strip()
        if post_tree != prospective_tree:
            raise RemediationError(
                f"committed tree differs from tested prospective tree: "
                f"{post_tree} != {prospective_tree}"
            )
        if run(
            [
                "git", "-C", str(REPO),
                "merge-base", "--is-ancestor", FREEZE_ROOT, post_head,
            ],
            check=False,
        ).returncode != 0:
            raise RemediationError("Freeze ancestry lost after commit")

        run(["git", "-C", str(REPO), "push", "origin", BRANCH])
        pushed = True
        run(["git", "-C", str(REPO), "fetch", "origin"])
        remote_post = git("rev-parse", f"origin/{BRANCH}").strip()
        if remote_post != post_head:
            raise RemediationError(
                f"remote post-head mismatch: {remote_post} != {post_head}"
            )
        if run(
            [
                "git", "-C", str(REPO),
                "status", "--porcelain=v1", "--untracked-files=all",
            ]
        ).stdout.strip():
            raise RemediationError(
                "working tree not clean after commit/push"
            )

        post_db_sha = sha256_file(db)
        result = {
            "version": VERSION,
            "status": (
                "PASS_STAGE16AM_METADATA_REMEDIATION_AND_POST_REMEDIATION_"
                "RC_PREFLIGHT"
            ),
            "effective_at": effective_at,
            "branch": BRANCH,
            "pre_head": EXPECTED_HEAD,
            "post_head": post_head,
            "post_tree": post_tree,
            "freeze_root": FREEZE_ROOT,
            "freeze_ancestor_preserved": True,
            "audit_evidence_bundle_sha256": EVIDENCE_BUNDLE_SHA256,
            "pre_remediation_audit_status": (
                "REMEDIATION_REQUIRED_BEFORE_FINAL_PRO_PASS"
            ),
            "recovery_from": (
                "rnatr_stage16am_final_pro_metadata_remediation_v0.1.0_"
                "tsv_crlf_diff_check_failure"
            ),
            "recovery_failure_class": (
                "WRAPPER_ONLY_CSV_DEFAULT_CRLF_CAUSED_GIT_DIFF_CHECK_FAILURE"
            ),
            "remediated_findings": [
                "P1_CANONICAL_RELEASE_GATE_TABLE_STALE",
                "P2_CURRENT_ALGORITHM_CONTRACT_G25_G30_STALE",
                "P3_EXACT_CURRENT_RC_NOT_YET_BOUND_IN_SSOT",
                "P4_ROOT_CHANGELOG_MISSING",
            ],
            "current_release_gate_table": str(NEW_GATE_REL),
            "current_release_gate_table_sha256": sha256_file(
                REPO / NEW_GATE_REL
            ),
            "changelog_sha256": sha256_file(REPO / CHANGELOG_REL),
            "canonical_structure_sha256": sha256_file(
                REPO / NEW_CANONICAL_README_REL
            ),
            "g25_g30_current_algorithm_contract": (
                "PASS_G25_G29_G30_WITH_SCOPE_AMENDMENT"
            ),
            "final_pro_audit_gate": "OPEN_BLOCKING_REAUDIT_REQUIRED",
            "runtime_code_changed": False,
            "scientific_core_changed": False,
            "package_identity_changed": False,
            "repo_files_moved": False,
            "repo_files_deleted": False,
            "ssot_pre_sha256": pre_db_sha,
            "ssot_post_sha256": post_db_sha,
            "ssot_backup": str(backup),
            "tested_prospective_tree": prospective_tree,
            **smoke,
            "high_confidence_secret_scan": "PASS",
            "markdown_link_validation": "PASS",
            "working_tree_clean_after_push": True,
            "final_public_release_created": False,
            "human_visual_review_required": False,
            "next_step": (
                "UPLOAD_STAGE16AM_RESULT_AND_BUNDLE_THEN_RUN_INDEPENDENT_"
                "FINAL_PRO_CROSSCUT_REAUDIT"
            ),
        }
        result_path = (
            evidence_out
            / "rnatr_stage16am_final_pro_metadata_remediation.result.json"
        )
        result_path.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        # Include durable audit summary and relevant current files in evidence bundle.
        snapshot_dir = evidence_out / "snapshots"
        snapshot_dir.mkdir()
        for p in (
            REPO / NEW_GATE_REL,
            REPO / CHANGELOG_REL,
            REPO / NEW_CANONICAL_README_REL,
            REPO / CANONICAL_TSV_REL,
            REPO / STAGE_RECORD_REL,
            REPO / "metadata/ssot/CURRENT_STATE.md",
            REPO / "metadata/ssot/exports/current_algorithm_contract.tsv",
            REPO / "metadata/ssot/exports/current_open_questions.tsv",
            REPO / "metadata/ssot/exports/current_results.tsv",
        ):
            shutil.copy2(p, snapshot_dir / p.name)

        bundle = (
            evidence_out
            / (
                "rnatr_stage16am_final_pro_metadata_remediation_bundle_"
                + effective_at.replace(":", "").replace("+00:00", "Z")
                + ".tar.gz"
            )
        )
        with tarfile.open(bundle, "w:gz") as tf:
            for p in sorted(evidence_out.rglob("*")):
                if p == bundle or not p.is_file():
                    continue
                tf.add(
                    p,
                    arcname=p.relative_to(evidence_out).as_posix(),
                )
        bundle_sha = sha256_file(bundle)
        manifest = {
            "bundle": bundle.name,
            "bundle_sha256": bundle_sha,
            "post_head": post_head,
            "post_tree": post_tree,
            "members": {
                p.relative_to(evidence_out).as_posix(): sha256_file(p)
                for p in sorted(evidence_out.rglob("*"))
                if p.is_file() and p != bundle
            },
        }
        manifest_path = evidence_out / "bundle_manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        downloads_result = (
            Path.home()
            / "Downloads/rnatr_stage16am_final_pro_metadata_remediation.result.json"
        )
        downloads_bundle = Path.home() / "Downloads" / bundle.name
        shutil.copy2(result_path, downloads_result)
        shutil.copy2(bundle, downloads_bundle)

        print("===== DONE =====")
        print(
            "status\t"
            "PASS_STAGE16AM_METADATA_REMEDIATION_AND_POST_REMEDIATION_RC_PREFLIGHT"
        )
        print(f"pre_head\t{EXPECTED_HEAD}")
        print(f"post_head\t{post_head}")
        print(f"post_tree\t{post_tree}")
        print(f"source_archive_sha256\t{smoke['source_archive_sha256']}")
        print(f"result\t{downloads_result}")
        print(f"bundle\t{downloads_bundle}")
        print(f"bundle_sha256\t{bundle_sha}")
        print("runtime_code_changed\tfalse")
        print("scientific_core_changed\tfalse")
        print("package_identity_changed\tfalse")
        print("final_pro_audit_gate\tOPEN_BLOCKING_REAUDIT_REQUIRED")
        return 0

    except Exception:
        if not pushed:
            restore_precommit_state(db, backup)
        else:
            print(
                "WARNING: failure occurred after remote push; automatic rollback "
                "was intentionally skipped to avoid local/remote divergence.",
                file=sys.stderr,
            )
        raise


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
