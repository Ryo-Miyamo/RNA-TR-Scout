#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from typing import Any

VERSION = "rnatr_stage16ar_finalize_public_v050_release_v0.1.0"

REPO = Path(
    "/mnt/intelssd/rnatr_git_stage/"
    "LOCAL_CORE_FREEZE_V0.1.0_git_snapshot_v0.1.2"
)
PROJECT = Path("/mnt/intelssd/rnatr_project")
RELEASE_ROOT = Path("/mnt/intelssd/rnatr_release_engineering")
BRANCH = "stage16ae-public-release-packaging"
REPOSITORY = "Ryo-Miyamo/RNA-TR-Scout"
RUN_ID = "RNA_TR_SCOUT_STAGE16_RELEASE_ENGINEERING"

RELEASE_COMMIT = "9205049ed1fc343499416fa684dbc71f423754ef"
RELEASE_TREE = "feeca99eb1f22ba350b8e6276e513116b41340e1"
FREEZE_ROOT = "4b1981db955a8aa92a2a01e19bbb1cfc2aa0ebfb"
TAG = "v0.5.0"
TAG_OBJECT = "b6387580fb99d701ec34d9fb6349b40a4e277ca9"
GITHUB_RELEASE_ID = 371631603
GITHUB_RELEASE_PUBLISHED_AT = "2026-08-17T08:59:59Z"

SOURCE_ASSET = "RNA-TR-Scout-v0.5.0-source.tar.gz"
SOURCE_ASSET_SHA256 = (
    "b1b3c37f358a3a6851172b4e01eb82f41e74a5281452a12b2c8c4f3bdeac87e9"
)
SOURCE_ASSET_BYTES = 3342305
BINDING_ASSET = "RNA-TR-Scout-v0.5.0-release-binding.json"
BINDING_ASSET_SHA256 = (
    "03351293b0c04d6959c21e14108d859f3980291ea4a2a47cb6dce45018e02d7f"
)
CHECKSUM_ASSET = "SHA256SUMS.txt"
CHECKSUM_ASSET_SHA256 = (
    "66f461d7f0e04952c0c164a4fcca775121191951fe30a5117de6c800cfbaaae4"
)

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
EXPECTED_CATALOG_SHA256 = (
    "54a24e4b60d920c8fec16b2df37b47e40407de42b949b18dc6233e97d85f2fef"
)

AUDIT_BUNDLE = (
    Path.home()
    / "Downloads/rnatr_stage16ar_final_live_v050_release_audit_evidence_v0.1.0.tar.gz"
)
AUDIT_BUNDLE_SHA256 = (
    "97ceadafbaf95ac6e93a3ecf129778f81adb29bdb12b39a1b2728206bd626f08"
)
EXPECTED_AUDIT_MEMBERS = {
    "RNA-TR-Scout-v0.5.0-release-binding.json":
        "03351293b0c04d6959c21e14108d859f3980291ea4a2a47cb6dce45018e02d7f",
    "SHA256SUMS.txt":
        "66f461d7f0e04952c0c164a4fcca775121191951fe30a5117de6c800cfbaaae4",
    "rnatr_stage16an_final_pro_audit_registration.result.json":
        "ea1f4f40f059e82616daec4d3696c57601424dae82ec490cfa27a27607fc0134",
    "rnatr_stage16an_final_pro_crosscut_audit_evidence_v0.1.0.tar.gz":
        "e151959a7271246dc4385fc6c2c72e955bf69ec07d0351410d7ed1bab65009e8",
    "rnatr_stage16ao1_publication_wording_hotfix.result.json":
        "256bc0af8d670703054f34c3beafbf852bcd7741bf9e4606ecc3b37c410f12c4",
    "rnatr_stage16ao_finalize_v050_source_metadata.result.json":
        "affd865b5f342733dbcbb3c1c6806c94e39dff4ac2b64540a978ccc66cdf7c54",
    "rnatr_stage16ap_recovery_public_unauth_clone_smoke.result.json":
        "c4b2f6de824480283a0d816ec5062ff8848c08604489ee3eab7bcb6eb62bd34b",
    "rnatr_stage16ap_recovery_public_unauth_clone_smoke_bundle_2026-08-17T085155+0000.tar.gz":
        "d0a5ea395a9d6ea4e14f404b0efb80c47fa3f825141341208bf1434c760156cb",
    "rnatr_stage16aq_v050_tag_release_binding.result.json":
        "7928878ab72e12e80c0c342bd3c3422a51c01b7edaad18c81b0b53ae8883f0dc",
    "rnatr_stage16aq_v050_tag_release_binding_bundle_2026-08-17T085950+0000.tar.gz":
        "db9e2044f8acb8c4121f0faf0f90489f757f232fd2361b1788267e53ba86c7a2",
    "rnatr_stage16ar_final_live_v050_release_audit_v0.1.0.json":
        "8fde9085f069fee7bbbc54bb21cb29fd9186d1c2c100ce2dd0889f3b1f3fba8e",
    "rnatr_stage16ar_final_live_v050_release_audit_v0.1.0.md":
        "6faff3e53a917d825be96c9519ddd02a7acb5cf3334c3c852ce26740e16d7645",
}

PUBLIC_REPO_API = "https://api.github.com/repos/Ryo-Miyamo/RNA-TR-Scout"
PUBLIC_RELEASE_API = (
    "https://api.github.com/repos/Ryo-Miyamo/RNA-TR-Scout/releases/tags/v0.5.0"
)
PUBLIC_TAG_REF_API = (
    "https://api.github.com/repos/Ryo-Miyamo/RNA-TR-Scout/git/ref/tags/v0.5.0"
)
PUBLIC_TAG_OBJECT_API = (
    "https://api.github.com/repos/Ryo-Miyamo/RNA-TR-Scout/git/tags/"
    + TAG_OBJECT
)
RAW_TAG_BASE = (
    "https://raw.githubusercontent.com/Ryo-Miyamo/RNA-TR-Scout/v0.5.0"
)

RECORD_REL = Path(
    "docs/release/STAGE16AR_PUBLIC_V050_RELEASE_BINDING_v0.1.0.md"
)
REGISTRAR_REL = Path(
    "metadata/ssot/rnatr_stage16ar_finalize_public_v050_release_v0.1.0.py"
)

RECORD_TEXT = """# Stage16AR public RNA-TR-Scout v0.5.0 release binding

## Status

**PASS_PUBLIC_V0.5.0_RELEASE_BOUND_AND_REGISTERED**

## Exact public release identity

- repository: `Ryo-Miyamo/RNA-TR-Scout`
- repository visibility: public
- default branch at publication: `main`
- release tag: `v0.5.0` (annotated)
- tag object: `b6387580fb99d701ec34d9fb6349b40a4e277ca9`
- tag target commit: `9205049ed1fc343499416fa684dbc71f423754ef`
- release tree: `feeca99eb1f22ba350b8e6276e513116b41340e1`
- Local Core Freeze root: `4b1981db955a8aa92a2a01e19bbb1cfc2aa0ebfb`
- GitHub Release ID: `371631603`
- published: `2026-08-17T08:59:59Z`

## Checksummed public assets

- `RNA-TR-Scout-v0.5.0-source.tar.gz`
  - SHA-256: `b1b3c37f358a3a6851172b4e01eb82f41e74a5281452a12b2c8c4f3bdeac87e9`
- `RNA-TR-Scout-v0.5.0-release-binding.json`
  - SHA-256: `03351293b0c04d6959c21e14108d859f3980291ea4a2a47cb6dce45018e02d7f`
- `SHA256SUMS.txt`
  - SHA-256: `66f461d7f0e04952c0c164a4fcca775121191951fe30a5117de6c800cfbaaae4`

All three public assets were downloaded again and verified by SHA-256.

## Validation and citation binding

- final Pro cross-cut audit: PASS
- unauthenticated public HTTPS clone: PASS
- fresh public-source setup/native/Core/mapping smoke: PASS
- package version: `0.5.0`
- `CITATION.cff`: version `0.5.0`, date released `2026-08-17`
- GitHub license detection: `BSD-3-Clause`
- public compact catalog outer SHA-256:
  `54a24e4b60d920c8fec16b2df37b47e40407de42b949b18dc6233e97d85f2fef`

## Integrity scope

The tag is annotated but unsigned. GitHub's immutable-release feature is not
enabled for this release. Integrity is instead independently bound by the tag
object SHA, exact commit/tree SHA, public asset SHA-256 values,
`SHA256SUMS.txt`, and the release-binding JSON.

The project treats `v0.5.0` as a non-moving release reference. Any later tag or
asset drift is detectable against the registered values.

## Post-release repository state

The `v0.5.0` tag remains fixed on the exact release source commit. This
Stage16AR administrative closure is committed after the tag and may therefore
advance `main` by one documentation/SSOT-only commit without changing the
released source.

No scientific Core, runtime implementation, resource profile, native kernel,
schema, golden fixture, tag, GitHub Release body, or release asset is modified
by Stage16AR.
"""

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


class ClosureError(RuntimeError):
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
        raise ClosureError(
            f"command failed rc={p.returncode}: {' '.join(argv)}\n{p.stdout}"
        )
    return p


def git(*args: str, check: bool = True) -> str:
    return run(
        ["git", "-C", str(REPO), *args],
        check=check,
    ).stdout.rstrip("\n")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def ensure_regular(path: Path, label: str) -> Path:
    if not path.is_file() or path.is_symlink():
        raise ClosureError(f"{label} missing/invalid regular file: {path}")
    return path


def http_json(url: str) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "RNA-TR-Scout-final-release-closure/0.1",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        obj = json.loads(response.read().decode("utf-8"))
    if not isinstance(obj, dict):
        raise ClosureError(f"unexpected JSON object from {url}")
    return obj


def http_text(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "RNA-TR-Scout-final-release-closure/0.1"
        },
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        return response.read().decode("utf-8")


def http_bytes(url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "RNA-TR-Scout-final-release-closure/0.1"
        },
    )
    with urllib.request.urlopen(req, timeout=120) as response:
        return response.read()


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


def safe_extract_audit_bundle(
    bundle: Path,
    destination: Path,
) -> dict[str, Path]:
    destination.mkdir(parents=True, exist_ok=False)
    with tarfile.open(bundle, "r:gz") as tf:
        members = tf.getmembers()
        names = {member.name for member in members if member.isfile()}
        if names != set(EXPECTED_AUDIT_MEMBERS):
            raise ClosureError(
                "audit bundle member-set mismatch: "
                f"observed={sorted(names)} "
                f"expected={sorted(EXPECTED_AUDIT_MEMBERS)}"
            )
        for member in members:
            if not member.isfile() or member.issym() or member.islnk():
                raise ClosureError(
                    f"non-regular audit bundle member rejected: {member.name}"
                )
            rel = Path(member.name)
            if rel.is_absolute() or ".." in rel.parts:
                raise ClosureError(
                    f"unsafe audit member path: {member.name}"
                )
        tf.extractall(destination)

    extracted: dict[str, Path] = {}
    for name, expected_sha in EXPECTED_AUDIT_MEMBERS.items():
        path = destination / name
        if sha256_file(path) != expected_sha:
            raise ClosureError(f"audit member SHA mismatch: {name}")
        extracted[name] = path
    return extracted


def load_ssot(path: Path):
    spec = importlib.util.spec_from_file_location(
        "rnatr_ssot_stage16ar", path
    )
    if spec is None or spec.loader is None:
        raise ClosureError(f"cannot import SSOT module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


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
    stage_order: float,
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
            stage_order,
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
    decision_key: str,
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
        (decision_key,),
    ).fetchone()
    old_id = old[0] if old else None
    if old_id:
        conn.execute(
            "UPDATE decisions SET status='SUPERSEDED' "
            "WHERE decision_id=?",
            (old_id,),
        )
    decision_id = "decision_" + hashlib.sha256(
        (VERSION + "|" + decision_key).encode()
    ).hexdigest()[:20]
    conn.execute(
        """INSERT OR REPLACE INTO decisions(
               decision_id,decision_key,category,title,statement,status,
               confidence,effective_at,supersedes_decision_id,
               rationale,evidence_path
           ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (
            decision_id,
            decision_key,
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


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise ClosureError(
            f"{label}: expected exactly one source token; observed {count}"
        )
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


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
    for python in candidates:
        try:
            python = python.resolve()
        except OSError:
            continue
        if not python.is_file():
            continue
        probe = run(
            [
                str(python),
                "-c",
                "import sys,unittest,ctypes; print(sys.version.split()[0])",
            ],
            check=False,
        )
        if probe.returncode == 0:
            return python
    raise ClosureError("no suitable Python found for prospective-tree smoke")


def prospective_tree_smoke(
    tree_sha: str,
    evidence_dir: Path,
) -> dict[str, Any]:
    archive = evidence_dir / "post_release_metadata_tree.tar"
    with archive.open("wb") as output:
        process = subprocess.run(
            [
                "git", "-C", str(REPO),
                "archive", "--format=tar", tree_sha,
            ],
            stdout=output,
            stderr=subprocess.PIPE,
            check=False,
        )
    if process.returncode != 0:
        raise ClosureError(
            "git archive failed: "
            + process.stderr.decode("utf-8", errors="replace")
        )
    archive_sha = sha256_file(archive)
    archive_bytes = archive.stat().st_size
    python = find_test_python()

    with tempfile.TemporaryDirectory(
        prefix="rnatr_stage16ar_tree_"
    ) as temporary:
        source = Path(temporary) / "source"
        source.mkdir()
        with tarfile.open(archive, "r") as tf:
            for member in tf.getmembers():
                rel = Path(member.name)
                if rel.is_absolute() or ".." in rel.parts:
                    raise ClosureError(
                        f"unsafe prospective archive member: {member.name}"
                    )
            tf.extractall(source)

        env = os.environ.copy()
        env["PYTHONPATH"] = str(source / "src")
        env["RNATR_PROJECT_ROOT"] = str(source)
        env["PYTHONHASHSEED"] = "0"

        commands = {
            "compileall": [
                str(python), "-m", "compileall", "-q",
                "src", "scripts", "metadata/ssot",
            ],
            "unit_tests": [
                str(python), "-m", "unittest", "discover",
                "-s", "tests/unit", "-p", "test*.py", "-v",
            ],
            "resource_planner_tests": [
                str(python), "tests/test_resource_planner.py",
            ],
            "cli_version": [
                str(python), "-m", "rnatr_scout.cli", "version",
            ],
            "native_load": [
                str(python), "-c",
                (
                    "import ctypes; ctypes.CDLL("
                    "'src/rnatr_scout/general_caller/native_v0.4.1/"
                    "librnatr_native_periodic_kernel_v0.1.0.so'"
                    "); print('PASS_NATIVE_LOAD')"
                ),
            ],
        }
        logs: dict[str, str] = {}
        for name, argv in commands.items():
            process = run(
                argv, cwd=source, env=env, check=False
            )
            logs[name] = process.stdout
            (evidence_dir / f"{name}.log").write_text(
                process.stdout, encoding="utf-8"
            )
            if process.returncode != 0:
                raise ClosureError(
                    f"prospective tree {name} failed rc={process.returncode}"
                )

        if logs["cli_version"].strip() != "0.5.0":
            raise ClosureError("prospective tree CLI version is not 0.5.0")
        if "PASS_NATIVE_LOAD" not in logs["native_load"]:
            raise ClosureError("prospective tree native-load marker missing")

    archive.unlink()
    return {
        "tested_tree": tree_sha,
        "source_archive_sha256": archive_sha,
        "source_archive_bytes": archive_bytes,
        "python": str(python),
        "python_version": run([str(python), "--version"]).stdout.strip(),
        "compileall": "PASS",
        "unit_tests": "PASS",
        "resource_planner_tests": "PASS",
        "cli_version": "PASS",
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
        if b"\x00" not in path.read_bytes():
            result.append(path)
    return result


def verify_source_asset_bytes(data: bytes) -> None:
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        names = set(tf.getnames())
        prefix = "RNA-TR-Scout-0.5.0/"
        required = {
            prefix + "README.md",
            prefix + "LICENSE",
            prefix + "CITATION.cff",
            prefix + "pyproject.toml",
            prefix + "CHANGELOG.md",
            prefix + "docs/release/RELEASE_NOTES_v0.5.0.md",
        }
        missing = sorted(required - names)
        if missing:
            raise ClosureError(
                "public source asset missing required members: "
                + ", ".join(missing)
            )


def restore_precommit_state(db: Path, backup: Path) -> None:
    try:
        run(
            ["git", "-C", str(REPO), "reset", "--hard", RELEASE_COMMIT],
            check=False,
        )
        for rel in (RECORD_REL, REGISTRAR_REL):
            path = REPO / rel
            if path.exists():
                path.unlink()
        if backup.is_file():
            shutil.copy2(backup, db)
    except Exception:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Register the completed public RNA-TR-Scout v0.5.0 release in the "
            "operational SSOT, close the final release-binding gate, and create "
            "one post-release documentation/SSOT commit without moving v0.5.0."
        )
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--owner-visual-confirmed",
        action="store_true",
        help=(
            "Confirm that the live GitHub Release page visibly shows the correct "
            "v0.5.0 title and all three expected assets."
        ),
    )
    args = parser.parse_args()

    print("===== RNA-TR-SCOUT STAGE16AR FINAL PUBLIC V0.5.0 CLOSURE =====")
    print(f"version\t{VERSION}")
    print(f"mode\t{'EXECUTE' if args.execute else 'PREFLIGHT'}")

    ensure_regular(AUDIT_BUNDLE, "Stage16AR audit evidence bundle")
    if sha256_file(AUDIT_BUNDLE) != AUDIT_BUNDLE_SHA256:
        raise ClosureError("Stage16AR audit bundle SHA mismatch")

    run(["git", "-C", str(REPO), "fetch", "origin", "--tags"])
    branch = git("branch", "--show-current").strip()
    local_head = git("rev-parse", "HEAD").strip()
    local_tree = git("rev-parse", "HEAD^{tree}").strip()
    remote_main = git("rev-parse", "origin/main").strip()
    remote_release = git("rev-parse", f"origin/{BRANCH}").strip()
    working = run(
        [
            "git", "-C", str(REPO),
            "status", "--porcelain=v1", "--untracked-files=all",
        ]
    ).stdout.strip()

    if branch != BRANCH:
        raise ClosureError(f"expected branch {BRANCH}; observed {branch}")
    if (
        local_head != RELEASE_COMMIT
        or remote_main != RELEASE_COMMIT
        or remote_release != RELEASE_COMMIT
    ):
        raise ClosureError(
            "release/main exact precondition mismatch: "
            f"local={local_head} main={remote_main} release={remote_release}"
        )
    if local_tree != RELEASE_TREE:
        raise ClosureError(
            f"release tree mismatch: {local_tree} != {RELEASE_TREE}"
        )
    if working:
        raise ClosureError("source checkout must be clean:\n" + working)
    if run(
        [
            "git", "-C", str(REPO),
            "merge-base", "--is-ancestor", FREEZE_ROOT, RELEASE_COMMIT,
        ],
        check=False,
    ).returncode != 0:
        raise ClosureError("Freeze ancestry failed")

    tag_object = git("rev-parse", f"{TAG}^{{tag}}").strip()
    tag_commit = git("rev-parse", f"{TAG}^{{commit}}").strip()
    if tag_object != TAG_OBJECT or tag_commit != RELEASE_COMMIT:
        raise ClosureError(
            f"local tag binding mismatch: object={tag_object} commit={tag_commit}"
        )

    # Public live state.
    repo_json = http_json(PUBLIC_REPO_API)
    release_json = http_json(PUBLIC_RELEASE_API)
    tag_ref_json = http_json(PUBLIC_TAG_REF_API)
    tag_object_json = http_json(PUBLIC_TAG_OBJECT_API)

    if (
        repo_json.get("private") is not False
        or repo_json.get("visibility") != "public"
        or repo_json.get("default_branch") != "main"
    ):
        raise ClosureError("live repository public/default-main state failed")
    license_obj = repo_json.get("license")
    if (
        not isinstance(license_obj, dict)
        or license_obj.get("spdx_id") != "BSD-3-Clause"
    ):
        raise ClosureError("live GitHub license detection mismatch")

    if (
        release_json.get("id") != GITHUB_RELEASE_ID
        or release_json.get("tag_name") != TAG
        or release_json.get("name") != "RNA-TR-Scout v0.5.0"
        or release_json.get("draft") is not False
        or release_json.get("prerelease") is not False
        or release_json.get("published_at") != GITHUB_RELEASE_PUBLISHED_AT
    ):
        raise ClosureError("live GitHub Release metadata mismatch")

    ref_object = tag_ref_json.get("object")
    if (
        not isinstance(ref_object, dict)
        or ref_object.get("type") != "tag"
        or ref_object.get("sha") != TAG_OBJECT
    ):
        raise ClosureError("live annotated tag ref mismatch")
    target_object = tag_object_json.get("object")
    if (
        not isinstance(target_object, dict)
        or target_object.get("type") != "commit"
        or target_object.get("sha") != RELEASE_COMMIT
    ):
        raise ClosureError("live annotated tag target mismatch")

    tag_verification = tag_object_json.get("verification")
    tag_signed = bool(
        isinstance(tag_verification, dict)
        and tag_verification.get("verified") is True
    )
    release_immutable = bool(release_json.get("immutable", False))

    assets = release_json.get("assets")
    if not isinstance(assets, list):
        raise ClosureError("live release assets payload missing")
    asset_map = {
        asset["name"]: asset
        for asset in assets
        if isinstance(asset, dict) and isinstance(asset.get("name"), str)
    }
    expected_assets = {
        SOURCE_ASSET: SOURCE_ASSET_SHA256,
        BINDING_ASSET: BINDING_ASSET_SHA256,
        CHECKSUM_ASSET: CHECKSUM_ASSET_SHA256,
    }
    if set(asset_map) != set(expected_assets):
        raise ClosureError(
            "live release asset-name set mismatch: "
            f"observed={sorted(asset_map)} expected={sorted(expected_assets)}"
        )

    downloaded: dict[str, bytes] = {}
    for name, expected_sha in expected_assets.items():
        asset = asset_map[name]
        if asset.get("digest") != f"sha256:{expected_sha}":
            raise ClosureError(f"live GitHub digest mismatch for {name}")
        url = asset.get("browser_download_url")
        if not isinstance(url, str):
            raise ClosureError(f"download URL missing for {name}")
        data = http_bytes(url)
        if sha256_bytes(data) != expected_sha:
            raise ClosureError(f"public re-download SHA mismatch for {name}")
        downloaded[name] = data

    if len(downloaded[SOURCE_ASSET]) != SOURCE_ASSET_BYTES:
        raise ClosureError("public source asset byte-size mismatch")
    verify_source_asset_bytes(downloaded[SOURCE_ASSET])

    checksum_text = downloaded[CHECKSUM_ASSET].decode("utf-8")
    expected_checksum_text = (
        f"{SOURCE_ASSET_SHA256}  {SOURCE_ASSET}\n"
        f"{BINDING_ASSET_SHA256}  {BINDING_ASSET}\n"
    )
    if checksum_text != expected_checksum_text:
        raise ClosureError("public SHA256SUMS content mismatch")

    binding = json.loads(downloaded[BINDING_ASSET].decode("utf-8"))
    expected_binding = {
        "release_version": "0.5.0",
        "repository": REPOSITORY,
        "tag": TAG,
        "tag_kind": "annotated",
        "tag_object_sha": TAG_OBJECT,
        "commit_sha": RELEASE_COMMIT,
        "tree_sha": RELEASE_TREE,
        "freeze_root": FREEZE_ROOT,
        "source_archive_sha256": SOURCE_ASSET_SHA256,
        "source_archive_bytes": SOURCE_ASSET_BYTES,
        "license_spdx": "BSD-3-Clause",
        "license_sha256": EXPECTED_LICENSE_SHA256,
        "environment_lock_sha256": EXPECTED_LOCK_SHA256,
        "native_kernel_sha256": EXPECTED_NATIVE_SHA256,
        "release_gates_v0.3.5_sha256": EXPECTED_RELEASE_GATES_SHA256,
        "standard_catalog_outer_sha256": EXPECTED_CATALOG_SHA256,
        "citation_version": "0.5.0",
        "citation_date_released": "2026-08-17",
        "final_pro_audit": "PASS",
        "public_source_clone_setup_smoke": "PASS",
    }
    for key, expected in expected_binding.items():
        if binding.get(key) != expected:
            raise ClosureError(
                f"public binding JSON mismatch for {key}: "
                f"{binding.get(key)!r} != {expected!r}"
            )

    tag_citation = http_text(f"{RAW_TAG_BASE}/CITATION.cff")
    tag_pyproject = http_text(f"{RAW_TAG_BASE}/pyproject.toml")
    if (
        re.search(r"^version:\s*0\.5\.0\s*$", tag_citation, re.MULTILINE)
        is None
        or re.search(
            r"^date-released:\s*2026-08-17\s*$",
            tag_citation,
            re.MULTILINE,
        )
        is None
        or 'license: "BSD-3-Clause"' not in tag_citation
        or 'version = "0.5.0"' not in tag_pyproject
    ):
        raise ClosureError("tag-bound citation/package metadata mismatch")

    # Operational SSOT precondition.
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
            raise ClosureError("SSOT integrity preflight failed")
        if list(conn.execute("PRAGMA foreign_key_check")):
            raise ClosureError("SSOT foreign-key preflight failed")
        audit_q = conn.execute(
            "SELECT status,blocking FROM open_questions "
            "WHERE question_key='PUBLIC_RC_PRO_CROSSCUT_AUDIT'"
        ).fetchone()
        release_q = conn.execute(
            "SELECT status FROM open_questions "
            "WHERE question_key='CORE_FREEZE_GIT_TAG_AND_PUBLIC_RELEASE_BINDING'"
        ).fetchone()
        limitation = conn.execute(
            "SELECT status FROM limitations "
            "WHERE limitation_key='PUBLIC_V050_RELEASE_NOT_YET_COMPLETE'"
        ).fetchone()
        if (
            not audit_q
            or audit_q["status"] != "CLOSED"
            or int(audit_q["blocking"]) != 0
        ):
            raise ClosureError("final Pro audit gate is not closed")
        if not release_q or release_q["status"] != "OPEN":
            raise ClosureError("release-binding gate is not open")
        if not limitation or limitation["status"] != "ACTIVE":
            raise ClosureError(
                "public-v0.5.0-not-complete limitation precondition failed"
            )

    print("live_public_repository\tPASS")
    print("live_annotated_tag_binding\tPASS")
    print("live_github_release\tPASS")
    print("live_release_assets_redownload\tPASS")
    print("live_citation_license_binding\tPASS")
    print(f"annotated_tag_signed\t{str(tag_signed).lower()}")
    print(f"github_release_immutable_flag\t{str(release_immutable).lower()}")
    print("final_pro_gate\tCLOSED")
    print("release_binding_gate\tOPEN")
    print("planned_tag_release_asset_change\tfalse")
    print("planned_scientific_runtime_change\tfalse")
    print("owner_visual_confirmation_required_for_execute\ttrue")

    if not args.execute:
        print("status\tPREFLIGHT_PASS_READY_FOR_EXECUTE")
        return 0

    if not args.owner_visual_confirmed:
        raise ClosureError(
            "--owner-visual-confirmed is required for execute after viewing "
            "the live v0.5.0 Release title and three assets"
        )

    effective_at = utc_now()
    checkpoint = (
        ssot_root
        / "checkpoints/stage16ar_public_v050_release_binding_v0.1.0"
        / effective_at.replace(":", "").replace("+00:00", "Z")
    )
    originals = checkpoint / "originals"
    backups = checkpoint / "backups"
    live = checkpoint / "live"
    originals.mkdir(parents=True, exist_ok=False)
    backups.mkdir(parents=True, exist_ok=True)
    live.mkdir(parents=True, exist_ok=True)

    durable_audit_bundle = originals / AUDIT_BUNDLE.name
    shutil.copy2(AUDIT_BUNDLE, durable_audit_bundle)
    if sha256_file(durable_audit_bundle) != AUDIT_BUNDLE_SHA256:
        raise ClosureError("durable audit bundle SHA mismatch")
    evidence = safe_extract_audit_bundle(
        durable_audit_bundle, originals / "extracted"
    )

    # Preserve exact live state and downloaded public assets.
    live_objects = {
        "live_repository.json": repo_json,
        "live_release.json": release_json,
        "live_tag_ref.json": tag_ref_json,
        "live_tag_object.json": tag_object_json,
    }
    for name, obj in live_objects.items():
        (live / name).write_text(
            json.dumps(obj, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    for name, data in downloaded.items():
        (live / name).write_bytes(data)

    pre_db_sha = sha256_file(db)
    backup = backups / "rnatr_ssot.pre_stage16ar.sqlite"
    shutil.copy2(db, backup)
    if sha256_file(backup) != pre_db_sha:
        raise ClosureError("SSOT backup SHA mismatch")

    pushed = False
    try:
        # Post-release current-document updates. The v0.5.0 tag remains fixed.
        notes_path = ensure_regular(
            REPO / "docs/release/RELEASE_NOTES_v0.5.0.md",
            "final release notes",
        )
        replace_once(
            notes_path,
            "**FINAL v0.5.0 SOURCE — PUBLIC GIT/TAG/RELEASE BINDING PENDING**",
            "**FINAL v0.5.0 RELEASE — PUBLIC GIT/TAG/RELEASE BINDING COMPLETE**",
            "release-notes completion status",
        )
        replace_once(
            notes_path,
            (
                "Repository visibility, immutable tag, GitHub Release, source\n"
                "checksums, and citation binding will be verified in a separate "
                "publication step."
            ),
            (
                "Repository visibility, annotated tag, GitHub Release, source\n"
                "checksums, and citation binding have been verified by the "
                "Stage16AR public-release record."
            ),
            "release-notes completion paragraph",
        )
        notes_text = notes_path.read_text(encoding="utf-8")
        see_anchor = (
            "- `docs/release/STAGE16AN_FINAL_PRO_CROSSCUT_AUDIT_v0.1.0.md`\n"
            "- `validation/release_gates_v0.3.5.tsv`\n"
            "- `CHANGELOG.md`\n"
        )
        if notes_text.count(see_anchor) != 1:
            raise ClosureError("release-notes Stage16AR link anchor missing")
        notes_path.write_text(
            notes_text.replace(
                see_anchor,
                see_anchor
                + "- `docs/release/"
                  "STAGE16AR_PUBLIC_V050_RELEASE_BINDING_v0.1.0.md`\n",
                1,
            ),
            encoding="utf-8",
        )

        changelog_path = ensure_regular(
            REPO / "CHANGELOG.md", "CHANGELOG"
        )
        replace_once(
            changelog_path,
            (
                "- Immutable Git tag/GitHub Release/source-checksum/citation "
                "binding will be verified separately in the final release record."
            ),
            (
                "- Annotated Git tag, GitHub Release, public source assets, "
                "SHA-256 checksums, license, and citation binding were verified "
                "in the Stage16AR final release record."
            ),
            "CHANGELOG release-binding completion",
        )

        stage16ae_path = ensure_regular(
            REPO / "docs/release/"
            "STAGE16AE_PUBLIC_RELEASE_PACKAGING_v0.1.0.md",
            "Stage16AE record",
        )
        replace_once(
            stage16ae_path,
            (
                "**MECHANICAL PACKAGING / RC PREFLIGHT / SSOT RECONCILIATION / "
                "FINAL PRO AUDIT COMPLETE — FINAL PUBLIC BINDING PENDING**"
            ),
            (
                "**PUBLIC v0.5.0 PACKAGING, FINAL PRO AUDIT, AND RELEASE "
                "BINDING COMPLETE**"
            ),
            "Stage16AE final status",
        )
        replace_once(
            stage16ae_path,
            (
                "The release candidate has passed the final Pro cross-cut audit. "
                "Stage16AE/AF/AG and the subsequent repository/SSOT remediation "
                "are accepted for the audited RC scope. Public v0.5.0 is still "
                "not declared until final-version conversion, main/public-source "
                "verification, and immutable tag/release/citation binding complete."
            ),
            (
                "RNA-TR-Scout v0.5.0 is publicly released and checksum-bound to "
                "the exact annotated tag, commit, tree, release assets, license, "
                "and citation metadata recorded by Stage16AR."
            ),
            "Stage16AE acceptance completion",
        )

        record_path = REPO / RECORD_REL
        if record_path.exists():
            raise ClosureError(f"Stage16AR record already exists: {record_path}")
        record_path.write_text(RECORD_TEXT, encoding="utf-8")

        registrar_path = REPO / REGISTRAR_REL
        if registrar_path.exists():
            raise ClosureError(
                f"Stage16AR registrar already exists: {registrar_path}"
            )
        registrar_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(Path(__file__).resolve(), registrar_path)

        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            conn.execute("BEGIN IMMEDIATE")

            source_paths = [
                (
                    "stage16ar_final_live_audit_bundle",
                    durable_audit_bundle,
                ),
                (
                    "stage16ar_final_live_audit_json",
                    evidence[
                        "rnatr_stage16ar_final_live_v050_release_audit_v0.1.0.json"
                    ],
                ),
                (
                    "stage16ar_final_live_audit_markdown",
                    evidence[
                        "rnatr_stage16ar_final_live_v050_release_audit_v0.1.0.md"
                    ],
                ),
                (
                    "stage16ao_final_source_result",
                    evidence[
                        "rnatr_stage16ao_finalize_v050_source_metadata.result.json"
                    ],
                ),
                (
                    "stage16ao1_wording_result",
                    evidence[
                        "rnatr_stage16ao1_publication_wording_hotfix.result.json"
                    ],
                ),
                (
                    "stage16ap_public_clone_result",
                    evidence[
                        "rnatr_stage16ap_recovery_public_unauth_clone_smoke.result.json"
                    ],
                ),
                (
                    "stage16ap_public_clone_bundle",
                    evidence[
                        "rnatr_stage16ap_recovery_public_unauth_clone_smoke_bundle_2026-08-17T085155+0000.tar.gz"
                    ],
                ),
                (
                    "stage16aq_release_binding_result",
                    evidence[
                        "rnatr_stage16aq_v050_tag_release_binding.result.json"
                    ],
                ),
                (
                    "stage16aq_release_binding_bundle",
                    evidence[
                        "rnatr_stage16aq_v050_tag_release_binding_bundle_2026-08-17T085950+0000.tar.gz"
                    ],
                ),
                ("stage16ar_live_repository", live / "live_repository.json"),
                ("stage16ar_live_release", live / "live_release.json"),
                ("stage16ar_live_tag_ref", live / "live_tag_ref.json"),
                ("stage16ar_live_tag_object", live / "live_tag_object.json"),
                ("stage16ar_public_source_asset", live / SOURCE_ASSET),
                ("stage16ar_public_binding_asset", live / BINDING_ASSET),
                ("stage16ar_public_checksums_asset", live / CHECKSUM_ASSET),
                ("stage16ar_repo_record", record_path),
                ("stage16ar_registrar", registrar_path),
            ]
            for source_type, path in source_paths:
                source_document(
                    conn, path, source_type, effective_at
                )

            stages = [
                (
                    "16AO_FINAL_V050_SOURCE_METADATA",
                    185.0,
                    "Stage16AO final v0.5.0 source metadata",
                    "Convert the audited RC metadata to final 0.5.0 and validate the exact prospective source tree.",
                    "VALIDATED",
                    "PASS; scientific/runtime semantics unchanged.",
                ),
                (
                    "16AO1_PUBLICATION_WORDING_HOTFIX",
                    185.1,
                    "Stage16AO1 publication wording hotfix",
                    "Keep pre-publication final source notes in accurate pending/future tense.",
                    "VALIDATED",
                    "PASS; documentation-only.",
                ),
                (
                    "16AP_PUBLIC_MAIN_UNAUTHENTICATED_CLONE",
                    186.0,
                    "Stage16AP public main and unauthenticated clone/setup",
                    "Fast-forward exact final source to main, publicize the repository, and verify anonymous clone plus fresh source setup.",
                    "VALIDATED",
                    "PASS after wrapper-only Git-config recovery.",
                ),
                (
                    "16AQ_V050_TAG_RELEASE_BINDING",
                    187.0,
                    "Stage16AQ v0.5.0 tag and GitHub Release binding",
                    "Create and verify the annotated v0.5.0 tag, GitHub Release, public assets, SHA256SUMS, binding JSON, license and citation.",
                    "VALIDATED",
                    "PASS; public assets re-downloaded and SHA-verified.",
                ),
                (
                    "16AR_PUBLIC_V050_RELEASE_BINDING",
                    188.0,
                    "Stage16AR final public v0.5.0 release closure",
                    "Independently verify the live release, register exact identities, and close the final public-release binding gate.",
                    "RELEASED",
                    "PASS; RNA-TR-Scout v0.5.0 public release complete.",
                ),
            ]
            for stage in stages:
                ensure_stage(conn, *stage)

            stage_evidence = {
                "16AO_FINAL_V050_SOURCE_METADATA": evidence[
                    "rnatr_stage16ao_finalize_v050_source_metadata.result.json"
                ],
                "16AO1_PUBLICATION_WORDING_HOTFIX": evidence[
                    "rnatr_stage16ao1_publication_wording_hotfix.result.json"
                ],
                "16AP_PUBLIC_MAIN_UNAUTHENTICATED_CLONE": evidence[
                    "rnatr_stage16ap_recovery_public_unauth_clone_smoke.result.json"
                ],
                "16AQ_V050_TAG_RELEASE_BINDING": evidence[
                    "rnatr_stage16aq_v050_tag_release_binding.result.json"
                ],
                "16AR_PUBLIC_V050_RELEASE_BINDING": record_path,
            }
            for stage_key, path in stage_evidence.items():
                add_run_stage(
                    conn,
                    stage_key,
                    "v0.1.0",
                    "PASS",
                    "PASS",
                    str(path),
                    (
                        "PASS and bound into the final public v0.5.0 "
                        "release-evidence chain."
                    ),
                    effective_at,
                )

            superseding_decision(
                conn,
                "public_v050_release_binding_v0_1_0",
                "release_governance",
                "Accept RNA-TR-Scout v0.5.0 as the public bound release",
                (
                    "Accept public RNA-TR-Scout v0.5.0 as bound to annotated "
                    "tag object b6387580..., exact commit 9205049e..., tree "
                    "feeca99e..., checksummed source/binding assets, public "
                    "clone/setup evidence, BSD-3-Clause license detection, "
                    "and tag-bound CITATION metadata."
                ),
                (
                    "The final live Pro audit rechecked the public repository, "
                    "tag object/target, Release metadata, downloaded asset hashes, "
                    "binding manifest, citation, license and prior public-source "
                    "setup evidence with zero blocking finding."
                ),
                str(record_path),
                effective_at,
            )
            superseding_decision(
                conn,
                "v050_release_integrity_model_v0_1_0",
                "release_governance",
                "Record the v0.5.0 checksum-bound integrity model",
                (
                    "v0.5.0 uses an unsigned annotated tag plus exact tag-object, "
                    "commit, tree and public asset SHA-256 binding. GitHub's "
                    "immutable-release feature is not enabled; the project treats "
                    "the tag as non-moving and detects drift through registered hashes."
                ),
                (
                    "Signing or platform-enforced immutable releases were not "
                    "explicit v0.5.0 gates; exact object and checksum evidence "
                    "provides independently verifiable release integrity."
                ),
                str(record_path),
                effective_at,
            )

            close = conn.execute(
                """UPDATE open_questions
                   SET status='CLOSED',blocking=0,next_action=?,
                       evidence_path=?,effective_at=?
                   WHERE question_key='CORE_FREEZE_GIT_TAG_AND_PUBLIC_RELEASE_BINDING'
                     AND status='OPEN'""",
                (
                    (
                        "Completed: public v0.5.0 repository, annotated tag, "
                        "GitHub Release, source checksums, license, citation and "
                        "public clone/setup binding verified and registered."
                    ),
                    str(record_path),
                    effective_at,
                ),
            )
            if close.rowcount != 1:
                raise ClosureError(
                    "failed to close public release-binding gate"
                )

            limitation_update = conn.execute(
                """UPDATE limitations
                   SET status='SUPERSEDED',mitigation=?,evidence_path=?,
                       effective_at=?
                   WHERE limitation_key='PUBLIC_V050_RELEASE_NOT_YET_COMPLETE'
                     AND status='ACTIVE'""",
                (
                    (
                        "Resolved by Stage16AR: public repository, exact annotated "
                        "v0.5.0 tag, GitHub Release, checksummed assets, citation "
                        "and license binding are complete."
                    ),
                    str(record_path),
                    effective_at,
                ),
            )
            if limitation_update.rowcount != 1:
                raise ClosureError(
                    "failed to supersede public-release-not-complete limitation"
                )

            metrics = {
                "release_version": "0.5.0",
                "release_status": "PUBLIC_RELEASE_COMPLETE",
                "repository_visibility": "public",
                "default_branch_release_commit": RELEASE_COMMIT,
                "release_tag": TAG,
                "release_tag_kind": "annotated",
                "release_tag_object_sha": TAG_OBJECT,
                "release_tag_target_commit": RELEASE_COMMIT,
                "release_tree_sha": RELEASE_TREE,
                "freeze_root": FREEZE_ROOT,
                "github_release_id": str(GITHUB_RELEASE_ID),
                "github_release_published_at": GITHUB_RELEASE_PUBLISHED_AT,
                "github_release_asset_count": "3",
                "source_asset_sha256": SOURCE_ASSET_SHA256,
                "binding_asset_sha256": BINDING_ASSET_SHA256,
                "sha256sums_asset_sha256": CHECKSUM_ASSET_SHA256,
                "standard_catalog_outer_sha256": EXPECTED_CATALOG_SHA256,
                "github_license_detection": "BSD-3-Clause",
                "citation_version": "0.5.0",
                "citation_date_released": "2026-08-17",
                "public_unauthenticated_clone_setup": "PASS",
                "tag_signature": (
                    "SIGNED_VERIFIED" if tag_signed else "UNSIGNED_ACCEPTED"
                ),
                "github_release_immutable_flag": str(
                    release_immutable
                ).lower(),
                "integrity_model": (
                    "ANNOTATED_TAG_PLUS_EXACT_OBJECT_COMMIT_TREE_AND_SHA256_ASSETS"
                ),
                "release_binding_gate": "CLOSED",
            }
            for name, value in metrics.items():
                add_metric(
                    conn,
                    "16AR_PUBLIC_V050_RELEASE_BINDING",
                    name,
                    value,
                    str(record_path),
                    effective_at,
                )

            conn.commit()

            ssot = load_ssot(ssot_py)
            checks = ssot.validate_db(conn, PROJECT)
            failed = [check for check in checks if check[1] == "FAIL"]
            if failed:
                raise ClosureError(
                    f"post-release SSOT validation failed: {failed}"
                )
            exports = ssot.export_views(conn, ssot_root)
            ssot.write_summary(conn, ssot_root, checks, exports)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        # Sync generated SSOT snapshots into the repository.
        shutil.copy2(
            ssot_root / "CURRENT_STATE.md",
            REPO / "metadata/ssot/CURRENT_STATE.md",
        )
        for path in (ssot_root / "exports").glob("*.tsv"):
            shutil.copy2(
                path,
                REPO / "metadata/ssot/exports" / path.name,
            )

        # Verify final SSOT state.
        with sqlite3.connect(str(db)) as conn:
            conn.row_factory = sqlite3.Row
            release_q = conn.execute(
                "SELECT status,blocking FROM open_questions "
                "WHERE question_key='CORE_FREEZE_GIT_TAG_AND_PUBLIC_RELEASE_BINDING'"
            ).fetchone()
            limitation = conn.execute(
                "SELECT status FROM limitations "
                "WHERE limitation_key='PUBLIC_V050_RELEASE_NOT_YET_COMPLETE'"
            ).fetchone()
            if (
                not release_q
                or release_q["status"] != "CLOSED"
                or int(release_q["blocking"]) != 0
            ):
                raise ClosureError(
                    "release-binding gate not closed after transaction"
                )
            if not limitation or limitation["status"] != "SUPERSEDED":
                raise ClosureError(
                    "public-release limitation not superseded"
                )

        # Project/repo export identity.
        for path in (ssot_root / "exports").glob("*.tsv"):
            repo_path = REPO / "metadata/ssot/exports" / path.name
            if sha256_file(path) != sha256_file(repo_path):
                raise ClosureError(
                    f"SSOT export identity mismatch: {path.name}"
                )
        if sha256_file(
            ssot_root / "CURRENT_STATE.md"
        ) != sha256_file(REPO / "metadata/ssot/CURRENT_STATE.md"):
            raise ClosureError("CURRENT_STATE identity mismatch")

        # Exact allowed change scope.
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
            "CHANGELOG.md",
            "docs/release/RELEASE_NOTES_v0.5.0.md",
            "docs/release/STAGE16AE_PUBLIC_RELEASE_PACKAGING_v0.1.0.md",
            str(RECORD_REL),
            str(REGISTRAR_REL),
            "metadata/ssot/CURRENT_STATE.md",
        }
        unexpected = sorted(
            path
            for path in changed_paths
            if path not in exact_allowed
            and not path.startswith("metadata/ssot/exports/")
        )
        if unexpected:
            raise ClosureError(
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
            raise ClosureError(
                "scientific/runtime path changed:\n" + "\n".join(forbidden)
            )

        run(["git", "-C", str(REPO), "diff", "--check"])

        # TSV and Markdown checks.
        for path in sorted(
            (REPO / "metadata/ssot/exports").glob("*.tsv")
        ):
            if b"\r" in path.read_bytes():
                raise ClosureError(
                    f"CR byte found in generated TSV: {path}"
                )
            with path.open("r", encoding="utf-8", newline="") as fh:
                reader = csv.reader(fh, delimiter="\t")
                try:
                    header = next(reader)
                except StopIteration:
                    raise ClosureError(f"empty TSV: {path}")
                for line_number, row in enumerate(reader, start=2):
                    if len(row) != len(header):
                        raise ClosureError(
                            f"TSV field mismatch {path}:{line_number}"
                        )

        link_rows: list[dict[str, Any]] = []
        for rel in (
            "README.md",
            "CHANGELOG.md",
            "docs/release/RELEASE_NOTES_v0.5.0.md",
            "docs/release/STAGE16AE_PUBLIC_RELEASE_PACKAGING_v0.1.0.md",
            str(RECORD_REL),
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
                raise ClosureError(
                    f"broken Markdown links in {rel}: {broken}"
                )

        # Stage exact administrative closure files.
        run(
            [
                "git", "-C", str(REPO), "add",
                "CHANGELOG.md",
                "docs/release/RELEASE_NOTES_v0.5.0.md",
                "docs/release/STAGE16AE_PUBLIC_RELEASE_PACKAGING_v0.1.0.md",
                str(RECORD_REL),
                str(REGISTRAR_REL),
                "metadata/ssot/CURRENT_STATE.md",
                "metadata/ssot/exports",
            ]
        )
        run(["git", "-C", str(REPO), "diff", "--cached", "--check"])

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
            raise ClosureError(
                "forbidden staged paths:\n"
                + "\n".join(forbidden_staged)
            )

        effective_evidence = (
            RELEASE_ROOT
            / (
                "stage16ar_finalize_public_v050_release_"
                + effective_at.replace(":", "").replace("+00:00", "Z")
            )
        )
        effective_evidence.mkdir(parents=True, exist_ok=False)

        # Secret scan over the prospective repository.
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
            effective_evidence / "high_confidence_secret_hits.tsv",
            secret_hits,
            ["path", "line", "pattern"],
        )
        if secret_hits:
            raise ClosureError(
                f"high-confidence secret hits found: {secret_hits}"
            )
        write_tsv(
            effective_evidence / "markdown_link_checks.tsv",
            link_rows,
            [
                "path", "links_checked",
                "broken_links", "broken_targets",
            ],
        )

        prospective_tree = git("write-tree").strip()
        smoke = prospective_tree_smoke(
            prospective_tree, effective_evidence
        )

        # Commit one post-release administrative closure commit.
        run(
            [
                "git", "-C", str(REPO), "commit",
                "-m", "Register RNA-TR-Scout v0.5.0 public release binding",
            ]
        )
        closure_head = git("rev-parse", "HEAD").strip()
        closure_tree = git("rev-parse", "HEAD^{tree}").strip()
        if closure_tree != prospective_tree:
            raise ClosureError(
                "committed closure tree differs from tested prospective tree"
            )
        if run(
            [
                "git", "-C", str(REPO),
                "merge-base", "--is-ancestor", RELEASE_COMMIT, closure_head,
            ],
            check=False,
        ).returncode != 0:
            raise ClosureError("release commit not ancestor of closure commit")

        # Atomically advance release branch and main together. The v0.5.0 tag
        # is intentionally untouched.
        push = run(
            [
                "git", "-C", str(REPO),
                "push", "--atomic", "origin",
                f"HEAD:refs/heads/{BRANCH}",
                "HEAD:refs/heads/main",
            ],
            check=False,
        )
        (effective_evidence / "atomic_push.log").write_text(
            push.stdout, encoding="utf-8"
        )
        if push.returncode != 0:
            raise ClosureError(
                "atomic post-release branch/main push failed:\n" + push.stdout
            )
        pushed = True

        run(["git", "-C", str(REPO), "fetch", "origin", "--tags"])
        if (
            git("rev-parse", "origin/main").strip() != closure_head
            or git("rev-parse", f"origin/{BRANCH}").strip() != closure_head
        ):
            raise ClosureError(
                "remote main/release branch closure identity mismatch"
            )
        if (
            git("rev-parse", f"{TAG}^{{tag}}").strip() != TAG_OBJECT
            or git("rev-parse", f"{TAG}^{{commit}}").strip()
            != RELEASE_COMMIT
        ):
            raise ClosureError("v0.5.0 tag moved during closure")

        # Live Release and assets must remain unchanged.
        release_after = http_json(PUBLIC_RELEASE_API)
        if (
            release_after.get("id") != GITHUB_RELEASE_ID
            or release_after.get("published_at")
            != GITHUB_RELEASE_PUBLISHED_AT
        ):
            raise ClosureError("GitHub Release changed during closure")
        after_assets = {
            asset["name"]: asset.get("digest")
            for asset in release_after.get("assets", [])
            if isinstance(asset, dict)
            and isinstance(asset.get("name"), str)
        }
        expected_digests = {
            SOURCE_ASSET: f"sha256:{SOURCE_ASSET_SHA256}",
            BINDING_ASSET: f"sha256:{BINDING_ASSET_SHA256}",
            CHECKSUM_ASSET: f"sha256:{CHECKSUM_ASSET_SHA256}",
        }
        if after_assets != expected_digests:
            raise ClosureError("GitHub Release asset digests changed")

        if run(
            [
                "git", "-C", str(REPO),
                "status", "--porcelain=v1", "--untracked-files=all",
            ]
        ).stdout.strip():
            raise ClosureError("working tree not clean after closure push")

        post_db_sha = sha256_file(db)
        result = {
            "version": VERSION,
            "status": (
                "PASS_STAGE16AR_PUBLIC_V050_RELEASE_REGISTERED_AND_GATE_CLOSED"
            ),
            "effective_at": effective_at,
            "release_version": "0.5.0",
            "release_tag": TAG,
            "release_tag_object_sha": TAG_OBJECT,
            "release_commit": RELEASE_COMMIT,
            "release_tree": RELEASE_TREE,
            "freeze_root": FREEZE_ROOT,
            "github_release_id": GITHUB_RELEASE_ID,
            "github_release_published_at": GITHUB_RELEASE_PUBLISHED_AT,
            "source_asset_sha256": SOURCE_ASSET_SHA256,
            "binding_asset_sha256": BINDING_ASSET_SHA256,
            "sha256sums_asset_sha256": CHECKSUM_ASSET_SHA256,
            "closure_head": closure_head,
            "closure_tree": closure_tree,
            "main_post_release_head": closure_head,
            "tag_remained_on_release_commit": True,
            "github_release_assets_unchanged": True,
            "final_pro_audit_gate": "CLOSED",
            "release_binding_gate": "CLOSED",
            "public_v050_release_complete": True,
            "tag_signed": tag_signed,
            "github_release_immutable_flag": release_immutable,
            "integrity_scope": (
                "ANNOTATED_TAG_PLUS_EXACT_OBJECT_COMMIT_TREE_AND_SHA256_ASSETS"
            ),
            "owner_visual_confirmed": True,
            "scientific_core_changed": False,
            "runtime_semantics_changed": False,
            "tag_or_release_asset_changed": False,
            "ssot_pre_sha256": pre_db_sha,
            "ssot_post_sha256": post_db_sha,
            "ssot_backup": str(backup),
            "audit_evidence_bundle_sha256": AUDIT_BUNDLE_SHA256,
            **smoke,
            "secret_scan": "PASS",
            "markdown_link_validation": "PASS",
            "working_tree_clean_after_push": True,
            "next_step": (
                "PROJECT_RELEASE_ENGINEERING_COMPLETE_BEGIN_POST_V050_"
                "BIOLOGY_PLATFORM_OR_PERFORMANCE_LANE"
            ),
        }

        result_path = (
            effective_evidence
            / "rnatr_stage16ar_finalize_public_v050_release.result.json"
        )
        result_path.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        snapshots = effective_evidence / "snapshots"
        snapshots.mkdir()
        for path in (
            REPO / RECORD_REL,
            REPO / "CHANGELOG.md",
            REPO / "docs/release/RELEASE_NOTES_v0.5.0.md",
            REPO / "metadata/ssot/CURRENT_STATE.md",
            REPO / "metadata/ssot/exports/current_open_questions.tsv",
            REPO / "metadata/ssot/exports/current_results.tsv",
            REPO / "metadata/ssot/exports/latest_stage_status.tsv",
        ):
            shutil.copy2(path, snapshots / path.name)

        bundle = (
            effective_evidence
            / (
                "rnatr_stage16ar_finalize_public_v050_release_bundle_"
                + effective_at.replace(":", "").replace("+00:00", "Z")
                + ".tar.gz"
            )
        )
        with tarfile.open(bundle, "w:gz") as tf:
            for path in sorted(effective_evidence.rglob("*")):
                if path == bundle or not path.is_file():
                    continue
                tf.add(
                    path,
                    arcname=path.relative_to(effective_evidence).as_posix(),
                )
        bundle_sha = sha256_file(bundle)

        downloads_result = (
            Path.home()
            / "Downloads/rnatr_stage16ar_finalize_public_v050_release.result.json"
        )
        downloads_bundle = Path.home() / "Downloads" / bundle.name
        shutil.copy2(result_path, downloads_result)
        shutil.copy2(bundle, downloads_bundle)

        print("===== DONE =====")
        print(
            "status\t"
            "PASS_STAGE16AR_PUBLIC_V050_RELEASE_REGISTERED_AND_GATE_CLOSED"
        )
        print(f"release_tag\t{TAG}")
        print(f"release_commit\t{RELEASE_COMMIT}")
        print(f"closure_head\t{closure_head}")
        print("release_binding_gate\tCLOSED")
        print("public_v050_release_complete\ttrue")
        print(f"result\t{downloads_result}")
        print(f"bundle\t{downloads_bundle}")
        print(f"bundle_sha256\t{bundle_sha}")
        print("scientific_core_changed\tfalse")
        print("runtime_semantics_changed\tfalse")
        print("tag_or_release_asset_changed\tfalse")
        return 0

    except Exception:
        if not pushed:
            restore_precommit_state(db, backup)
        else:
            print(
                "WARNING: failure occurred after the atomic remote push; "
                "automatic rollback was skipped to avoid rewriting public history.",
                file=sys.stderr,
            )
        raise


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
