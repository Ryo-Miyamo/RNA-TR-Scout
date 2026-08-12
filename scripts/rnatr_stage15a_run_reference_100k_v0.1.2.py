#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import difflib
import gzip
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

STAGE_VERSION = "rnatr_stage15a_reference_100k_v0.1.2"
RUN_ID = "ENCSR307SHM_pilot100k_mm2splice_v1"
SAMPLE_ID = "ENCSR307SHM"
PROJECT_ROOT = Path("/mnt/intelssd/rnatr_project")
ORIGINAL_RAW_ROOT = Path("/media/tokushimaneuro02/T9/rnatr_data")
BUNDLE_META_ROOT = (
    PROJECT_ROOT
    / "metadata/stage15a/v0.1.0/reference_execution_bundle"
)
CONTRACT_ROOT = BUNDLE_META_ROOT / "contract"
FIX_META_ROOT = (
    PROJECT_ROOT
    / "metadata/stage15a/v0.1.2/motif_report_fix_bundle"
)
FROZEN_VALIDATOR_SOURCE = (
    FIX_META_ROOT
    / "rnatr_v03_validate_tsv_validator_v0.3.1.py"
)
FROZEN_VALIDATOR_EXPECTED_SHA256 = (
    "10c9d4bbb5c9dac314d400768eb27206173933759c877225bd0ca2c692d8aba9"
)
RESULT_ROOT = (
    PROJECT_ROOT
    / "results/15_stage15a_bam_to_final"
    / RUN_ID
    / "v0.1.2"
)
QC_ROOT = (
    PROJECT_ROOT
    / "qc/15_stage15a_bam_to_final"
    / RUN_ID
    / "v0.1.2"
)
SHADOW = RESULT_ROOT / "shadow_project.work"
SHADOW_RAW = SHADOW / "raw_root"
FROZEN_SCRIPTS = RESULT_ROOT / "frozen_scripts"
CALLER_ROOT = RESULT_ROOT / "caller"
PACKAGE_PART = RESULT_ROOT / "package_reference.part"
PACKAGE_FINAL = RESULT_ROOT / "package_reference"
COMPARISON_DIR = QC_ROOT / "comparison"
LOG_DIR = QC_ROOT / "logs"
TIMING_DIR = QC_ROOT / "timing"
MARKER_DIR = QC_ROOT / "markers"
CONTRACT_OUT = QC_ROOT / "contract"
QUARANTINE = RESULT_ROOT / "quarantine"

ORIGINAL_PATHS_ENV = PROJECT_ROOT / "config/paths.env"
TARGET_BAM = (
    PROJECT_ROOT
    / "results/11_mapping"
    / RUN_ID
    / f"{RUN_ID}.sorted.bam"
)
TARGET_BAI = Path(str(TARGET_BAM) + ".bai")
ORIGINAL_CANDIDATE_FASTQ = (
    ORIGINAL_RAW_ROOT
    / "benchmarks/ENCSR307SHM/pilot_100k_seed20260803"
    / "rnatr_candidates_v0.3.1"
    / "ENCFF260PGB.pilot_100k.rnatr_candidate_all.fastq.gz"
)
ORIGINAL_WINDOW_FASTQ = (
    ORIGINAL_RAW_ROOT
    / "benchmarks/ENCSR307SHM/pilot_100k_seed20260803"
    / "rnatr_projection_v0.3.3"
    / "ENCFF260PGB.pilot_100k.rnatr_target_windows.v0.3.3.fastq.gz"
)
SHADOW_WINDOW_FASTQ = (
    SHADOW_RAW
    / "benchmarks/ENCSR307SHM/pilot_100k_seed20260803"
    / "rnatr_projection_v0.3.3"
    / "ENCFF260PGB.pilot_100k.rnatr_target_windows.v0.3.3.fastq.gz"
)

HOST_CALLER_DRIVER = (
    PROJECT_ROOT
    / "results/14_v041_schema_v041_100k_end_to_end"
    / RUN_ID
    / "v0.1.0/run_native_v041_100k.py"
)
DETERMINISTIC_REFERENCE_CALLS = (
    PROJECT_ROOT
    / "results/14_deterministic_general_caller"
    / RUN_ID
    / "v0.4.1_validation_v0.1.0/integration_native_100k"
    / "general_repeat_calls.v0.4.0.tsv.gz"
)
MATERIALIZER = (
    PROJECT_ROOT
    / "src/rnatr_scout/materialization"
    / "rnatr_materialize_native_v041_to_evidence_v042_v0.1.2.py"
)
SCHEMA_DIR = PROJECT_ROOT / "config/evidence_schema/v0.4.2"
SCHEMA_JSON = SCHEMA_DIR / "schema/rnatr_v04_table_schema.json"
VALIDATOR_TSV = SCHEMA_DIR / "rnatr_v042_validate_tsv.py"
VALIDATOR_PACKAGE = SCHEMA_DIR / "rnatr_v042_validate_package.py"
FROZEN_PACKAGE = (
    PROJECT_ROOT
    / "results/14_v041_schema_v042_100k_end_to_end"
    / RUN_ID
    / "v0.1.1/package"
)
PARITY_QC = (
    PROJECT_ROOT
    / "qc/15_stage15a_contract_preflight"
    / RUN_ID
    / "v0.1.2_caller_parity"
    / "stage15a0_caller_parity_resolution.qc.tsv"
)

EXPECTED_COUNTS = {
    "general_repeat_calls": 388571,
    "read_evidence": 388571,
    "repeat_events": 160297,
    "repeat_segments": 161265,
    "repeat_interruptions": 848,
}
TABLE_KEYS = {
    "general_repeat_calls": ["projection_id"],
    "read_evidence": ["evidence_id"],
    "repeat_events": ["evidence_id", "event_index", "repeat_event_id"],
    "repeat_segments": [
        "evidence_id",
        "repeat_event_id",
        "segment_index",
        "repeat_call_id",
    ],
    "repeat_interruptions": [
        "evidence_id",
        "repeat_event_id",
        "interruption_index",
        "interruption_id",
    ],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(chunk_size)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def open_binary_logical(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rb")
    return path.open("rb")


def logical_sha256(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with open_binary_logical(path) as handle:
        while True:
            block = handle.read(chunk_size)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def logical_line_count(path: Path) -> int:
    count = 0
    last = b""
    with open_binary_logical(path) as handle:
        while True:
            block = handle.read(8 * 1024 * 1024)
            if not block:
                break
            count += block.count(b"\n")
            last = block[-1:]
    if last and last != b"\n":
        count += 1
    return count


def first_logical_line(path: Path) -> str:
    with open_binary_logical(path) as handle:
        return handle.readline().decode("utf-8").rstrip("\r\n")


def data_rows(path: Path, kind: str = "tsv") -> int:
    lines = logical_line_count(path)
    if kind == "fastq":
        if lines % 4 != 0:
            raise RuntimeError(f"FASTQ line count is not divisible by four: {path}")
        return lines // 4
    if kind == "tsv":
        return max(0, lines - 1)
    return lines


def read_metric_tsv(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        try:
            next(reader)
        except StopIteration:
            return result
        for row in reader:
            if len(row) >= 2:
                result[row[0]] = row[1]
    return result


def write_metric_tsv(path: Path, rows: Iterable[tuple[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["metric", "value"])
        for key, value in rows:
            writer.writerow([key, value])


def assert_under(path: Path, root: Path) -> None:
    resolved = path.resolve(strict=False)
    root_resolved = root.resolve(strict=False)
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise RuntimeError(f"unsafe path outside isolated root: {path}") from exc


def ensure_file(path: Path) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"required file missing or empty: {path}")


def ensure_symlink(link: Path, target: Path) -> None:
    target = target.resolve()
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink():
        if link.resolve() == target:
            return
        raise RuntimeError(f"symlink points elsewhere: {link} -> {link.resolve()}")
    if link.exists():
        raise RuntimeError(f"cannot create symlink over existing path: {link}")
    link.symlink_to(target, target_is_directory=target.is_dir())


def load_required_ledger() -> dict[str, dict[str, str]]:
    path = CONTRACT_ROOT / "stage15a_required_artifacts.tsv"
    ensure_file(path)
    rows: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            rows[row["role"]] = row
    return rows


def verify_host_contract() -> list[dict[str, object]]:
    parity = read_metric_tsv(PARITY_QC)
    required_parity = {
        "audit_status": "PASS",
        "next_gate": "READY_TO_FREEZE_STAGE15A_EXECUTION_BUNDLE",
        "reference_vs_reused_exact_decompressed_match": "true",
        "package_suffix_keyed_semantic_match": "true",
        "package_missing_projection_ids": "0",
        "package_extra_projection_ids": "0",
        "package_value_mismatch_projection_ids": "0",
        "active_pipeline_modified": "false",
        "full_5_31m_run_started": "false",
    }
    for key, expected in required_parity.items():
        observed = parity.get(key)
        if observed != expected:
            raise RuntimeError(
                f"Stage15A0 parity gate mismatch: {key}={observed!r}, expected {expected!r}"
            )

    ledger = load_required_ledger()
    roles = {
        "TARGET_100K_BAM",
        "TARGET_100K_BAI",
        "MAPPING_RUN_MANIFEST",
        "CANDIDATE_RAW_FASTQ",
        "MAPPING_TARGET_BED",
        "MAPPING_TARGET_TBI",
        "MAPPING_TARGET_TSV",
        "ANALYSIS_REGIONS",
        "DISEASE_REGIONS",
        "SCHEMA_V03",
        "VALIDATOR_V03_EFFECTIVE",
        "SCHEMA_V042",
        "SCHEMA_V042_FREEZE_MANIFEST",
        "VALIDATOR_V042_TSV",
        "VALIDATOR_V042_PACKAGE",
        "GENERAL_CALLER_V041",
        "GENERAL_CALLER_V021_DEPENDENCY",
        "MATERIALIZER_V012",
        "PROMOTED_NATIVE_V041_CALLER_INTEGRATION_DRIVER",
        "NATIVE_V041_CALLER_INTEGRATION_QC",
        "DETERMINISTIC_REFERENCE_CALLS",
        "DETERMINISTIC_CALLER_VALIDATION_QC",
        "STAGE14K2_QC",
        "FROZEN_PACKAGE_MANIFEST",
        "ACTIVE_11B",
        "ACTIVE_11D3",
        "ACTIVE_11E",
    }
    audit_rows: list[dict[str, object]] = []
    for role in sorted(roles):
        if role not in ledger:
            raise RuntimeError(f"contract ledger lacks role: {role}")
        row = ledger[role]
        path = Path(row["path"])
        ensure_file(path)
        observed = sha256_file(path)
        expected = row.get("observed_sha256") or row.get("expected_sha256")
        status = "PASS" if observed == expected else "FAIL"
        audit_rows.append(
            {
                "role": role,
                "path": str(path),
                "bytes": path.stat().st_size,
                "expected_sha256": expected,
                "observed_sha256": observed,
                "status": status,
            }
        )
        if status != "PASS":
            raise RuntimeError(f"host artifact SHA mismatch for {role}: {path}")

    discovered = CONTRACT_ROOT / "stage15a_discovered_components.tsv"
    with discovered.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row["category"] != "CALLER_RUNTIME_DEPENDENCY":
                continue
            path = Path(row["path"])
            ensure_file(path)
            observed = sha256_file(path)
            status = "PASS" if observed == row["sha256"] else "FAIL"
            audit_rows.append(
                {
                    "role": "CALLER_RUNTIME_DEPENDENCY",
                    "path": str(path),
                    "bytes": path.stat().st_size,
                    "expected_sha256": row["sha256"],
                    "observed_sha256": observed,
                    "status": status,
                }
            )
            if status != "PASS":
                raise RuntimeError(f"caller runtime dependency SHA mismatch: {path}")

    CONTRACT_OUT.mkdir(parents=True, exist_ok=True)
    ledger_out = CONTRACT_OUT / "stage15a_reference_host_contract.audit.tsv"
    with ledger_out.open("w", encoding="utf-8", newline="") as handle:
        fields = [
            "role",
            "path",
            "bytes",
            "expected_sha256",
            "observed_sha256",
            "status",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(audit_rows)
    return audit_rows



def verify_frozen_reference_artifacts(label: str) -> Path:
    expected = read_metric_tsv(
        CONTRACT_ROOT / "stage15a_frozen_artifacts_and_lockstep.qc.tsv"
    )
    checks = [
        (
            "assignment",
            PROJECT_ROOT / "results/11_assignment" / RUN_ID / "read_target_candidates.tsv.gz",
            expected.get("assignment_raw_sha256"),
            expected.get("assignment_decompressed_sha256"),
            expected.get("assignment_rows"),
        ),
        (
            "projection",
            PROJECT_ROOT / "results/11_projection" / RUN_ID / "v0.3.3/read_target_projection.v0.3.3.tsv.gz",
            expected.get("projection_raw_sha256"),
            expected.get("projection_decompressed_sha256"),
            expected.get("projection_rows"),
        ),
        (
            "motif_jobs",
            PROJECT_ROOT / "results/11_motif_jobs" / RUN_ID / "motif_scan_jobs.tsv.gz",
            expected.get("motif_jobs_raw_sha256"),
            expected.get("motif_jobs_decompressed_sha256"),
            expected.get("motif_jobs_rows"),
        ),
        (
            "frozen_general_repeat_calls",
            FROZEN_PACKAGE / "general_repeat_calls.tsv.gz",
            expected.get("general_repeat_calls_raw_sha256"),
            expected.get("general_repeat_calls_decompressed_sha256"),
            expected.get("general_repeat_calls_rows"),
        ),
    ]
    rows: list[dict[str, object]] = []
    for role, path, expected_raw, expected_logical, expected_rows in checks:
        ensure_file(path)
        observed_raw = sha256_file(path)
        observed_logical = logical_sha256(path)
        observed_rows = data_rows(path, "tsv")
        status = (
            "PASS"
            if observed_raw == expected_raw
            and observed_logical == expected_logical
            and str(observed_rows) == str(expected_rows)
            else "FAIL"
        )
        rows.append(
            {
                "label": label,
                "role": role,
                "path": str(path),
                "expected_rows": expected_rows,
                "observed_rows": observed_rows,
                "expected_raw_sha256": expected_raw,
                "observed_raw_sha256": observed_raw,
                "expected_logical_sha256": expected_logical,
                "observed_logical_sha256": observed_logical,
                "status": status,
            }
        )
        if status != "PASS":
            raise RuntimeError(f"frozen reference artifact changed: {role} {path}")
    out = CONTRACT_OUT / f"stage15a_frozen_reference_{label}.audit.tsv"
    with out.open("w", encoding="utf-8", newline="") as handle:
        fields = list(rows[0])
        writer = csv.DictWriter(
            handle, fieldnames=fields, delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)
    return out

def write_shadow_paths_env() -> Path:
    shadow_env = SHADOW / "config/paths.env"
    shadow_env.parent.mkdir(parents=True, exist_ok=True)
    text = (
        "# Stage 15A isolated path plumbing. Generated; do not source for active runs.\n"
        f"source {ORIGINAL_PATHS_ENV}\n"
        f"export PROJECT_ROOT=\"{SHADOW}\"\n"
        f"export RAW_ROOT=\"{SHADOW_RAW}\"\n"
        f"export CATALOG_ROOT=\"{PROJECT_ROOT / 'catalogs'}\"\n"
    )
    shadow_env.write_text(text, encoding="utf-8")
    return shadow_env


def patch_upstream_script(source: Path, destination: Path, shadow_env: Path) -> None:
    ensure_file(source)
    original = source.read_text(encoding="utf-8")
    anchor = f"source {ORIGINAL_PATHS_ENV}"
    if original.count(anchor) != 1:
        raise RuntimeError(f"expected one paths.env anchor in {source}")
    patched = original.replace(anchor, f'source "{shadow_env}"')
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(patched, encoding="utf-8")
    destination.chmod(0o755)
    diff = "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            patched.splitlines(keepends=True),
            fromfile=str(source),
            tofile=str(destination),
        )
    )
    (destination.with_suffix(destination.suffix + ".path_plumbing.diff")).write_text(
        diff, encoding="utf-8"
    )
    changed_lines = [line for line in diff.splitlines() if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))]
    if len(changed_lines) != 2:
        raise RuntimeError(f"unexpected upstream patch scope in {destination}")


def patch_11b_validator(
    source: Path,
    destination: Path,
    frozen_validator: Path,
) -> None:
    """Patch only the Stage 15A copy of 11b to the frozen validator v0.3.1.

    The v0.3.1 validator accepts the explicit strand enum value "." for
    unmapped BAM records. No BAM filtering and no extraction logic change
    are permitted.
    """
    ensure_file(source)
    ensure_file(frozen_validator)
    original = source.read_text(encoding="utf-8")
    old = 'VALIDATOR="$SCHEMA_DIR/rnatr_v03_validate_tsv.py"'
    new = f'VALIDATOR="{frozen_validator}"'
    if original.count(old) != 1:
        raise RuntimeError(
            f"expected exactly one obsolete validator assignment in {source}"
        )
    patched = original.replace(old, new, 1)
    if "samtools view -F 4" in patched or "mapped_only" in patched:
        raise RuntimeError("11b validator fix must not filter unmapped BAM records")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(patched, encoding="utf-8")
    destination.chmod(0o755)
    diff = "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            patched.splitlines(keepends=True),
            fromfile=str(source),
            tofile=str(destination),
        )
    )
    destination.with_suffix(destination.suffix + ".validator_v031.diff").write_text(
        diff, encoding="utf-8"
    )
    changed_lines = [
        line
        for line in diff.splitlines()
        if line.startswith(("+", "-"))
        and not line.startswith(("+++", "---"))
    ]
    if len(changed_lines) != 2:
        raise RuntimeError(f"unexpected validator patch scope in {destination}")


def patch_11e_pipefail_report(source: Path, destination: Path) -> None:
    """Patch only the Stage 15A copy of 11e's human-readable top-30 report.

    The active 11e script has ``set -o pipefail`` and uses
    ``tail | sort | head -n 30``. After ``head`` has read 30 rows it closes
    the pipe, so GNU sort can receive SIGPIPE and return 141 even though the
    motif-job builder and QC have completed successfully. ``sed -n
    '1,30p'`` prints the same first 30 rows but continues consuming the full
    stream, so every pipeline component exits normally.

    No input, builder code, output table, row ordering, manifest content, or
    scientific decision rule is changed.
    """
    ensure_file(source)
    original = source.read_text(encoding="utf-8")
    old = """    tail -n +2 "$MOTIF_DICTIONARY" |
      sort -t $'\\t' -k4,4nr |
      head -n 30
"""
    new = """    tail -n +2 "$MOTIF_DICTIONARY" |
      sort -t $'\\t' -k4,4nr |
      sed -n '1,30p'
"""
    if original.count(old) != 1:
        raise RuntimeError(
            f"expected exactly one unsafe 11e top-30 pipeline in {source}"
        )
    patched = original.replace(old, new, 1)
    if "head -n 30" in patched:
        raise RuntimeError("unsafe 11e head pipeline remains after patch")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(patched, encoding="utf-8")
    destination.chmod(0o755)
    diff = "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            patched.splitlines(keepends=True),
            fromfile=str(source),
            tofile=str(destination),
        )
    )
    destination.with_suffix(destination.suffix + ".pipefail_report.diff").write_text(
        diff, encoding="utf-8"
    )
    changed_lines = [
        line
        for line in diff.splitlines()
        if line.startswith(("+", "-"))
        and not line.startswith(("+++", "---"))
    ]
    if changed_lines != ["-      head -n 30", "+      sed -n '1,30p'"]:
        raise RuntimeError(
            f"unexpected 11e report patch scope in {destination}: {changed_lines}"
        )


def patch_caller_driver(destination: Path) -> None:
    ensure_file(HOST_CALLER_DRIVER)
    original = HOST_CALLER_DRIVER.read_text(encoding="utf-8")
    patched = original
    replacements = {
        str(ORIGINAL_RAW_ROOT): str(SHADOW_RAW),
        str(PROJECT_ROOT / "results/11_motif_jobs" / RUN_ID): str(
            SHADOW / "results/11_motif_jobs" / RUN_ID
        ),
        str(PROJECT_ROOT / "results/11_projection" / RUN_ID): str(
            SHADOW / "results/11_projection" / RUN_ID
        ),
    }
    for old, new in replacements.items():
        patched = patched.replace(old, new)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(patched, encoding="utf-8")
    destination.chmod(0o755)
    diff = "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            patched.splitlines(keepends=True),
            fromfile=str(HOST_CALLER_DRIVER),
            tofile=str(destination),
        )
    )
    destination.with_suffix(".path_plumbing.diff").write_text(diff, encoding="utf-8")


def setup_isolated_root() -> dict[str, Path]:
    for directory in [
        RESULT_ROOT,
        QC_ROOT,
        SHADOW,
        FROZEN_SCRIPTS,
        CALLER_ROOT,
        COMPARISON_DIR,
        LOG_DIR,
        TIMING_DIR,
        MARKER_DIR,
        CONTRACT_OUT,
        QUARANTINE,
    ]:
        directory.mkdir(parents=True, exist_ok=True)

    sentinel = RESULT_ROOT / ".rnatr_stage15a_isolated_root"
    if not sentinel.exists():
        sentinel.write_text(
            f"stage_version\t{STAGE_VERSION}\nrun_id\t{RUN_ID}\ncreated_utc\t{utc_now()}\n",
            encoding="utf-8",
        )

    shadow_env = write_shadow_paths_env()
    ensure_symlink(
        SHADOW / "results/11_mapping" / RUN_ID,
        PROJECT_ROOT / "results/11_mapping" / RUN_ID,
    )
    ensure_symlink(
        SHADOW / "config/evidence_schema",
        PROJECT_ROOT / "config/evidence_schema",
    )
    ensure_symlink(SHADOW / "src", PROJECT_ROOT / "src")
    ensure_symlink(
        SHADOW_RAW
        / "benchmarks/ENCSR307SHM/pilot_100k_seed20260803"
        / "rnatr_candidates_v0.3.1"
        / ORIGINAL_CANDIDATE_FASTQ.name,
        ORIGINAL_CANDIDATE_FASTQ,
    )

    scripts = {
        "11b": FROZEN_SCRIPTS
        / "11b_extract_alignment_segments_and_target_candidates.stage15a.validator_v031_fix_v0.1.2.sh",
        "11d3": FROZEN_SCRIPTS / "11d3_project_targets_to_raw_reads_secondary_seq_fixed.stage15a.sh",
        "11e": FROZEN_SCRIPTS
        / "11e_prepare_motif_scan_jobs.stage15a.pipefail_report_fix_v0.1.2.sh",
        "caller": FROZEN_SCRIPTS / "run_native_v041_100k.stage15a.py",
        "validator_v031": FROZEN_SCRIPTS
        / "rnatr_v03_validate_tsv_validator_v0.3.1.py",
    }
    ensure_file(FROZEN_VALIDATOR_SOURCE)
    observed_validator_sha = sha256_file(FROZEN_VALIDATOR_SOURCE)
    if observed_validator_sha != FROZEN_VALIDATOR_EXPECTED_SHA256:
        raise RuntimeError(
            "frozen validator v0.3.1 SHA mismatch: "
            f"{observed_validator_sha}"
        )
    shutil.copy2(FROZEN_VALIDATOR_SOURCE, scripts["validator_v031"])
    scripts["validator_v031"].chmod(0o755)

    stage15a_11b_path_only = FROZEN_SCRIPTS / (
        "11b_extract_alignment_segments_and_target_candidates.stage15a.path_only.sh"
    )
    patch_upstream_script(
        CONTRACT_ROOT / "active_02_11b_extract_alignment_segments_and_target_candidates.sh",
        stage15a_11b_path_only,
        shadow_env,
    )
    patch_11b_validator(
        stage15a_11b_path_only,
        scripts["11b"],
        scripts["validator_v031"],
    )
    patch_upstream_script(
        CONTRACT_ROOT / "active_04_11d3_project_targets_to_raw_reads_secondary_seq_fixed.sh",
        scripts["11d3"],
        shadow_env,
    )
    stage15a_11e_path_only = FROZEN_SCRIPTS / (
        "11e_prepare_motif_scan_jobs.stage15a.path_only.sh"
    )
    patch_upstream_script(
        CONTRACT_ROOT / "active_05_11e_prepare_motif_scan_jobs.sh",
        stage15a_11e_path_only,
        shadow_env,
    )
    patch_11e_pipefail_report(
        stage15a_11e_path_only,
        scripts["11e"],
    )
    patch_caller_driver(scripts["caller"])

    script_ledger = CONTRACT_OUT / "stage15a_reference_frozen_scripts.tsv"
    with script_ledger.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["stage", "path", "bytes", "sha256"])
        writer.writerow([
            "11b_path_only_intermediate",
            stage15a_11b_path_only,
            stage15a_11b_path_only.stat().st_size,
            sha256_file(stage15a_11b_path_only),
        ])
        writer.writerow([
            "11e_path_only_intermediate",
            stage15a_11e_path_only,
            stage15a_11e_path_only.stat().st_size,
            sha256_file(stage15a_11e_path_only),
        ])
        for stage, path in scripts.items():
            writer.writerow([stage, path, path.stat().st_size, sha256_file(path)])
    return scripts


def output_fingerprint(path: Path) -> dict[str, object]:
    ensure_file(path)
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def marker_valid(marker: Path, outputs: Sequence[Path]) -> tuple[bool, dict[str, object] | None]:
    if not marker.is_file():
        return False, None
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except Exception:
        return False, None
    recorded = {entry["path"]: entry for entry in data.get("outputs", [])}
    for path in outputs:
        entry = recorded.get(str(path))
        if not entry or not path.is_file() or path.stat().st_size != entry.get("bytes"):
            return False, data
        if sha256_file(path) != entry.get("sha256"):
            return False, data
    return True, data


def parse_time_v(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.is_file():
        return result
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        result[key.strip()] = value.strip()
    return result


def run_logged(
    name: str,
    command: Sequence[str],
    outputs: Sequence[Path],
    *,
    env: dict[str, str] | None = None,
    production_component: bool = False,
) -> dict[str, object]:
    marker = MARKER_DIR / f"{name}.done.json"
    valid, old = marker_valid(marker, outputs)
    if valid and old is not None:
        print(f"[RESUME] {name}: verified outputs; skipping")
        return old

    for path in outputs:
        if path.exists() and marker.exists():
            raise RuntimeError(
                f"marker/output mismatch for {name}; refusing overwrite: {path}"
            )

    log_path = LOG_DIR / f"{name}.log"
    time_path = TIMING_DIR / f"{name}.time_v.txt"
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    TIMING_DIR.mkdir(parents=True, exist_ok=True)

    cmd = list(command)
    full_cmd = cmd
    if Path("/usr/bin/time").is_file():
        full_cmd = ["/usr/bin/time", "-v", "-o", str(time_path), *cmd]

    print("\n" + "=" * 78)
    print(f"RUN {name}")
    print("COMMAND:", " ".join(command))
    print("=" * 78)
    started = time.perf_counter()
    started_utc = utc_now()
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    with log_path.open("w", encoding="utf-8", newline="") as log_handle:
        process = subprocess.Popen(
            full_cmd,
            cwd=str(PROJECT_ROOT),
            env=merged_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            log_handle.write(line)
            log_handle.flush()
        return_code = process.wait()
    elapsed = time.perf_counter() - started
    if return_code != 0:
        raise RuntimeError(
            f"stage {name} failed with exit {return_code}; see {log_path}"
        )
    for path in outputs:
        ensure_file(path)
    time_info = parse_time_v(time_path)
    record: dict[str, object] = {
        "stage": name,
        "stage_version": STAGE_VERSION,
        "started_utc": started_utc,
        "finished_utc": utc_now(),
        "command": list(command),
        "elapsed_seconds": elapsed,
        "maximum_resident_set_kbytes": time_info.get(
            "Maximum resident set size (kbytes)", "."
        ),
        "production_component": production_component,
        "outputs": [output_fingerprint(path) for path in outputs],
    }
    marker.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return record


def compare_pair(
    role: str,
    candidate: Path,
    reference: Path,
    kind: str = "tsv",
) -> dict[str, object]:
    ensure_file(candidate)
    ensure_file(reference)
    candidate_raw = sha256_file(candidate)
    reference_raw = sha256_file(reference)
    candidate_logical = logical_sha256(candidate)
    reference_logical = logical_sha256(reference)
    result: dict[str, object] = {
        "role": role,
        "candidate_path": str(candidate),
        "reference_path": str(reference),
        "candidate_rows": data_rows(candidate, kind),
        "reference_rows": data_rows(reference, kind),
        "candidate_raw_sha256": candidate_raw,
        "reference_raw_sha256": reference_raw,
        "candidate_logical_sha256": candidate_logical,
        "reference_logical_sha256": reference_logical,
        "raw_equal": str(candidate_raw == reference_raw).lower(),
        "logical_equal": str(candidate_logical == reference_logical).lower(),
    }
    if kind == "tsv":
        result["header_equal"] = str(
            first_logical_line(candidate) == first_logical_line(reference)
        ).lower()
    else:
        result["header_equal"] = "."
    return result


def write_comparison(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "role",
        "candidate_path",
        "reference_path",
        "candidate_rows",
        "reference_rows",
        "candidate_raw_sha256",
        "reference_raw_sha256",
        "candidate_logical_sha256",
        "reference_logical_sha256",
        "raw_equal",
        "logical_equal",
        "header_equal",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def require_comparisons(rows: list[dict[str, object]], label: str) -> None:
    failures = [
        row
        for row in rows
        if row["logical_equal"] != "true"
        or row["candidate_rows"] != row["reference_rows"]
        or row.get("header_equal") not in {"true", "."}
    ]
    if failures:
        roles = ", ".join(str(row["role"]) for row in failures)
        raise RuntimeError(f"{label} semantic comparison failed: {roles}")


def caller_metrics(path: Path) -> dict[str, int]:
    counts = {
        "rows": 0,
        "called_attempt_rows": 0,
        "low_confidence_called_rows": 0,
        "duplicate_projection_ids": 0,
    }
    seen: set[str] = set()
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None or len(reader.fieldnames) != 77:
            raise RuntimeError(f"caller header is not 77 columns: {path}")
        for row in reader:
            counts["rows"] += 1
            projection_id = row["projection_id"]
            if projection_id in seen:
                counts["duplicate_projection_ids"] += 1
            seen.add(projection_id)
            if row.get("integration_status") == "CALLED":
                counts["called_attempt_rows"] += 1
                if row.get("call_status") == "LOW_CONFIDENCE":
                    counts["low_confidence_called_rows"] += 1
    return counts


def run_generic_validators(package_dir: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for table, expected in EXPECTED_COUNTS.items():
        path = package_dir / f"{table}.tsv.gz"
        log = LOG_DIR / f"validator_tsv_{table}.log"
        command = [
            sys.executable,
            str(VALIDATOR_TSV),
            "--schema",
            str(SCHEMA_JSON),
            "--table",
            table,
            "--input",
            str(path),
            "--max-rows",
            "1000000",
        ]
        started = time.perf_counter()
        proc = subprocess.run(command, text=True, capture_output=True)
        elapsed = time.perf_counter() - started
        log.write_text(proc.stdout + proc.stderr, encoding="utf-8")
        observed_rows = data_rows(path, "tsv")
        status = "PASS" if proc.returncode == 0 and observed_rows == expected else "FAIL"
        rows.append(
            {
                "validator": "rnatr_v042_validate_tsv.py",
                "table": table,
                "path": str(path),
                "expected_rows": expected,
                "observed_rows": observed_rows,
                "elapsed_seconds": elapsed,
                "exit_code": proc.returncode,
                "status": status,
                "log": str(log),
            }
        )
        if status != "PASS":
            raise RuntimeError(f"frozen TSV validator failed for {table}: {log}")
    return rows


def run_package_validator(package_dir: Path, label: str) -> dict[str, object]:
    help_proc = subprocess.run(
        [sys.executable, str(VALIDATOR_PACKAGE), "--help"],
        text=True,
        capture_output=True,
    )
    help_text = help_proc.stdout + help_proc.stderr
    (LOG_DIR / f"validator_package_{label}.help.txt").write_text(
        help_text, encoding="utf-8"
    )
    candidates: list[list[str]] = []
    options = [
        ("--package-dir", ["--package-dir", str(package_dir)]),
        ("--package", ["--package", str(package_dir)]),
        ("--input-dir", ["--input-dir", str(package_dir)]),
        ("--input", ["--input", str(package_dir)]),
        ("--directory", ["--directory", str(package_dir)]),
    ]
    for token, arguments in options:
        if token in help_text:
            candidates.append([sys.executable, str(VALIDATOR_PACKAGE), *arguments])
    candidates.extend(
        [
            [sys.executable, str(VALIDATOR_PACKAGE), str(package_dir)],
            [
                sys.executable,
                str(VALIDATOR_PACKAGE),
                "--schema",
                str(SCHEMA_JSON),
                "--package-dir",
                str(package_dir),
            ],
        ]
    )
    unique: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()
    for command in candidates:
        key = tuple(command)
        if key not in seen:
            seen.add(key)
            unique.append(command)

    attempts: list[str] = []
    for index, command in enumerate(unique, start=1):
        started = time.perf_counter()
        proc = subprocess.run(command, text=True, capture_output=True)
        elapsed = time.perf_counter() - started
        text = (
            "COMMAND\t"
            + " ".join(command)
            + f"\nEXIT_CODE\t{proc.returncode}\n"
            + proc.stdout
            + proc.stderr
        )
        attempt_log = LOG_DIR / f"validator_package_{label}.attempt_{index}.log"
        attempt_log.write_text(text, encoding="utf-8")
        attempts.append(str(attempt_log))
        if proc.returncode == 0:
            return {
                "validator": "rnatr_v042_validate_package.py",
                "label": label,
                "package_dir": str(package_dir),
                "command": command,
                "elapsed_seconds": elapsed,
                "exit_code": 0,
                "status": "PASS",
                "log": str(attempt_log),
            }
    raise RuntimeError(
        "frozen package validator invocation failed; see " + ", ".join(attempts)
    )


def rewrite_manifest_paths(package_dir: Path, final_dir: Path) -> None:
    manifest = package_dir / "package_manifest.tsv"
    ensure_file(manifest)
    rows: list[dict[str, str]] = []
    with manifest.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fields = reader.fieldnames
        if fields is None or "path" not in fields:
            raise RuntimeError("package manifest lacks path column")
        for row in reader:
            row["path"] = str(final_dir / row["artifact"])
            rows.append(row)
    with manifest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def fsync_tree(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_file():
            with path.open("rb") as handle:
                os.fsync(handle.fileno())
    fd = os.open(root, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_validator_ledger(rows: list[dict[str, object]]) -> Path:
    path = QC_ROOT / "stage15a_reference_validators.tsv"
    fields = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            normalized = dict(row)
            if isinstance(normalized.get("command"), list):
                normalized["command"] = " ".join(normalized["command"])
            writer.writerow(normalized)
    return path


def package_comparison(package_dir: Path) -> tuple[list[dict[str, object]], bool]:
    rows: list[dict[str, object]] = []
    for table in EXPECTED_COUNTS:
        candidate_plain = package_dir / f"{table}.tsv"
        reference_plain = FROZEN_PACKAGE / f"{table}.tsv"
        rows.append(compare_pair(f"{table}.plain", candidate_plain, reference_plain, "tsv"))
        candidate_gz = package_dir / f"{table}.tsv.gz"
        reference_gz = FROZEN_PACKAGE / f"{table}.tsv.gz"
        rows.append(compare_pair(f"{table}.gzip", candidate_gz, reference_gz, "tsv"))
    write_comparison(COMPARISON_DIR / "stage15a_reference_package_comparison.tsv", rows)
    exact_logical = all(row["logical_equal"] == "true" for row in rows)
    if not exact_logical:
        require_comparisons(rows, "package")
    return rows, exact_logical


def collect_small_artifacts(output_tar: Path) -> None:
    include: list[tuple[Path, str]] = []
    for root, prefix in [
        (QC_ROOT, "qc"),
        (RESULT_ROOT / "frozen_scripts", "results/frozen_scripts"),
    ]:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file():
                include.append((path, f"{prefix}/{path.relative_to(root)}"))

    small_paths = [
        SHADOW / "results/11_assignment" / RUN_ID / f"{RUN_ID}.assignment_output_manifest.tsv",
        SHADOW / "results/11_assignment" / RUN_ID / "rnatr_target_assignment_v0.3.1.parameters.tsv",
        SHADOW / "qc/11_assignment" / RUN_ID / "alignment_distribution_qc.tsv",
        SHADOW / "qc/11_assignment" / RUN_ID / "target_assignment_qc.tsv",
        SHADOW / "results/11_projection" / RUN_ID / "v0.3.3" / f"{RUN_ID}.raw_projection_manifest.v0.3.3.tsv",
        SHADOW / "results/11_projection" / RUN_ID / "v0.3.3" / "rnatr_raw_projection_v0.3.3.parameters.tsv",
        SHADOW / "qc/11_projection" / RUN_ID / "v0.3.3" / "raw_projection_qc.v0.3.3.tsv",
        SHADOW / "results/11_motif_jobs" / RUN_ID / f"{RUN_ID}.motif_job_preparation_manifest.tsv",
        SHADOW / "results/11_motif_jobs" / RUN_ID / "rnatr_motif_job_preparation_v0.3.1.parameters.tsv",
        SHADOW / "qc/11_motif_jobs" / RUN_ID / "motif_job_preparation_qc.tsv",
        PACKAGE_FINAL / "package_manifest.tsv",
        PACKAGE_FINAL / "materialization.qc.tsv",
    ]
    for path in small_paths:
        if path.is_file():
            include.append((path, f"selected/{path.name}"))

    output_tar.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output_tar, "w:gz") as archive:
        for path, arcname in sorted(include, key=lambda item: item[1]):
            archive.add(path, arcname=arcname, recursive=False)


def write_timing_ledger(records: list[dict[str, object]]) -> Path:
    path = QC_ROOT / "stage15a_reference_timing.tsv"
    fields = [
        "stage",
        "elapsed_seconds",
        "maximum_resident_set_kbytes",
        "production_component",
        "started_utc",
        "finished_utc",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for record in records:
            writer.writerow({key: record.get(key, ".") for key in fields})
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()
    if args.workers < 1 or args.workers > 24:
        raise SystemExit("--workers must be between 1 and 24")
    if PROJECT_ROOT.resolve() != Path("/mnt/intelssd/rnatr_project"):
        raise RuntimeError("unexpected project root")
    ensure_file(ORIGINAL_PATHS_ENV)

    print(f"===== {STAGE_VERSION} =====")
    print(f"run_id\t{RUN_ID}")
    print(f"result_root\t{RESULT_ROOT}")
    print(f"qc_root\t{QC_ROOT}")
    print("active_pipeline_switch\tPROHIBITED")
    print("full_5_31m_run\tPROHIBITED")

    verify_host_contract()
    verify_frozen_reference_artifacts("before")
    scripts = setup_isolated_root()

    timing_records: list[dict[str, object]] = []

    assignment_dir = SHADOW / "results/11_assignment" / RUN_ID
    assignment_qc = SHADOW / "qc/11_assignment" / RUN_ID
    outputs_11b = [
        assignment_dir / "alignment_segments.tsv.gz",
        assignment_dir / "alignment_target_candidates.tsv.gz",
        assignment_dir / "read_target_candidates.tsv.gz",
        assignment_qc / "alignment_distribution_qc.tsv",
        assignment_qc / "target_assignment_qc.tsv",
        assignment_dir / f"{RUN_ID}.assignment_output_manifest.tsv",
    ]
    timing_records.append(
        run_logged(
            "15A1_11b",
            ["bash", str(scripts["11b"])],
            outputs_11b,
            production_component=True,
        )
    )
    compare_11b = [
        compare_pair(
            "alignment_segments",
            outputs_11b[0],
            PROJECT_ROOT / "results/11_assignment" / RUN_ID / "alignment_segments.tsv.gz",
        ),
        compare_pair(
            "alignment_target_candidates",
            outputs_11b[1],
            PROJECT_ROOT / "results/11_assignment" / RUN_ID / "alignment_target_candidates.tsv.gz",
        ),
        compare_pair(
            "read_target_candidates",
            outputs_11b[2],
            PROJECT_ROOT / "results/11_assignment" / RUN_ID / "read_target_candidates.tsv.gz",
        ),
        compare_pair(
            "alignment_distribution_qc",
            outputs_11b[3],
            PROJECT_ROOT / "qc/11_assignment" / RUN_ID / "alignment_distribution_qc.tsv",
        ),
        compare_pair(
            "target_assignment_qc",
            outputs_11b[4],
            PROJECT_ROOT / "qc/11_assignment" / RUN_ID / "target_assignment_qc.tsv",
        ),
    ]
    write_comparison(COMPARISON_DIR / "15A1_11b_comparison.tsv", compare_11b)
    require_comparisons(compare_11b, "15A1/11b")

    projection_dir = SHADOW / "results/11_projection" / RUN_ID / "v0.3.3"
    projection_qc = SHADOW / "qc/11_projection" / RUN_ID / "v0.3.3"
    outputs_11d3 = [
        projection_dir / "read_target_projection.v0.3.3.tsv.gz",
        SHADOW_WINDOW_FASTQ,
        projection_qc / "raw_projection_qc.v0.3.3.tsv",
        projection_dir / f"{RUN_ID}.raw_projection_manifest.v0.3.3.tsv",
    ]
    timing_records.append(
        run_logged(
            "15A2_11d3",
            ["bash", str(scripts["11d3"])],
            outputs_11d3,
            production_component=True,
        )
    )
    compare_11d3 = [
        compare_pair(
            "read_target_projection",
            outputs_11d3[0],
            PROJECT_ROOT
            / "results/11_projection"
            / RUN_ID
            / "v0.3.3/read_target_projection.v0.3.3.tsv.gz",
        ),
        compare_pair(
            "target_window_fastq",
            outputs_11d3[1],
            ORIGINAL_WINDOW_FASTQ,
            "fastq",
        ),
        compare_pair(
            "raw_projection_qc",
            outputs_11d3[2],
            PROJECT_ROOT
            / "qc/11_projection"
            / RUN_ID
            / "v0.3.3/raw_projection_qc.v0.3.3.tsv",
        ),
    ]
    write_comparison(COMPARISON_DIR / "15A2_11d3_comparison.tsv", compare_11d3)
    require_comparisons(compare_11d3, "15A2/11d3")

    motif_dir = SHADOW / "results/11_motif_jobs" / RUN_ID
    motif_qc = SHADOW / "qc/11_motif_jobs" / RUN_ID
    outputs_11e = [
        motif_dir / "motif_scan_jobs.tsv.gz",
        motif_dir / "motif_scan_dictionary.tsv",
        motif_dir / "motif_scan_target_summary.tsv.gz",
        motif_qc / "motif_job_preparation_qc.tsv",
        motif_dir / f"{RUN_ID}.motif_job_preparation_manifest.tsv",
    ]
    timing_records.append(
        run_logged(
            "15A3_11e",
            ["bash", str(scripts["11e"])],
            outputs_11e,
            production_component=True,
        )
    )
    compare_11e = [
        compare_pair(
            "motif_scan_jobs",
            outputs_11e[0],
            PROJECT_ROOT / "results/11_motif_jobs" / RUN_ID / "motif_scan_jobs.tsv.gz",
        ),
        compare_pair(
            "motif_scan_dictionary",
            outputs_11e[1],
            PROJECT_ROOT / "results/11_motif_jobs" / RUN_ID / "motif_scan_dictionary.tsv",
        ),
        compare_pair(
            "motif_scan_target_summary",
            outputs_11e[2],
            PROJECT_ROOT / "results/11_motif_jobs" / RUN_ID / "motif_scan_target_summary.tsv.gz",
        ),
        compare_pair(
            "motif_job_preparation_qc",
            outputs_11e[3],
            PROJECT_ROOT / "qc/11_motif_jobs" / RUN_ID / "motif_job_preparation_qc.tsv",
        ),
    ]
    write_comparison(COMPARISON_DIR / "15A3_11e_comparison.tsv", compare_11e)
    require_comparisons(compare_11e, "15A3/11e")

    caller0 = CALLER_ROOT / "hashseed0"
    caller1 = CALLER_ROOT / "hashseed20260808"
    caller0.mkdir(parents=True, exist_ok=True)
    caller1.mkdir(parents=True, exist_ok=True)
    calls0 = caller0 / "general_repeat_calls.v0.4.0.tsv.gz"
    calls1 = caller1 / "general_repeat_calls.v0.4.0.tsv.gz"
    timing_records.append(
        run_logged(
            "15A4_caller_production",
            [
                sys.executable,
                str(scripts["caller"]),
                "--project-root",
                str(SHADOW),
                "--outdir",
                str(caller0),
                "--workers",
                str(args.workers),
            ],
            [calls0],
            env={"PYTHONHASHSEED": "0"},
            production_component=True,
        )
    )
    caller_compare0 = compare_pair(
        "native_v041_calls_vs_stage14g_reference",
        calls0,
        DETERMINISTIC_REFERENCE_CALLS,
    )
    require_comparisons([caller_compare0], "15A4 caller/reference")
    metrics0 = caller_metrics(calls0)
    expected_caller_metrics = {
        "rows": 388571,
        "called_attempt_rows": 160315,
        "low_confidence_called_rows": 6307,
        "duplicate_projection_ids": 0,
    }
    if metrics0 != expected_caller_metrics:
        raise RuntimeError(
            f"caller metric mismatch: observed={metrics0}, expected={expected_caller_metrics}"
        )

    timing_records.append(
        run_logged(
            "15A4_caller_determinism_audit",
            [
                sys.executable,
                str(scripts["caller"]),
                "--project-root",
                str(SHADOW),
                "--outdir",
                str(caller1),
                "--workers",
                str(args.workers),
            ],
            [calls1],
            env={"PYTHONHASHSEED": "20260808"},
            production_component=False,
        )
    )
    caller_compare1 = compare_pair(
        "native_v041_hashseed0_vs_hashseed20260808", calls0, calls1
    )
    caller_comparisons = [caller_compare0, caller_compare1]
    write_comparison(COMPARISON_DIR / "15A4_caller_comparison.tsv", caller_comparisons)
    require_comparisons(caller_comparisons, "15A4 caller determinism")

    package_outputs = [
        PACKAGE_PART / f"{table}.tsv" for table in EXPECTED_COUNTS
    ] + [
        PACKAGE_PART / f"{table}.tsv.gz" for table in EXPECTED_COUNTS
    ] + [
        PACKAGE_PART / "package_manifest.tsv",
        PACKAGE_PART / "materialization.qc.tsv",
    ]
    if PACKAGE_FINAL.exists() and not PACKAGE_PART.exists():
        package_outputs_final = [
            PACKAGE_FINAL / path.name for path in package_outputs
        ]
        materializer_record = {
            "stage": "15A5_reference_materializer",
            "stage_version": STAGE_VERSION,
            "started_utc": ".",
            "finished_utc": ".",
            "command": ["RESUME_FINAL_PACKAGE"],
            "elapsed_seconds": 0.0,
            "maximum_resident_set_kbytes": ".",
            "production_component": True,
            "outputs": [output_fingerprint(path) for path in package_outputs_final],
        }
        print("[RESUME] package_reference already atomically published")
    else:
        PACKAGE_PART.mkdir(parents=True, exist_ok=True)
        materializer_record = run_logged(
            "15A5_reference_materializer",
            [
                sys.executable,
                str(MATERIALIZER),
                "--project-root",
                str(SHADOW),
                "--calls",
                str(calls0),
                "--schema-dir",
                str(SCHEMA_DIR),
                "--outdir",
                str(PACKAGE_PART),
                "--sample-id",
                SAMPLE_ID,
            ],
            package_outputs,
            production_component=True,
        )
    timing_records.append(materializer_record)

    package_work = PACKAGE_FINAL if PACKAGE_FINAL.exists() and not PACKAGE_PART.exists() else PACKAGE_PART
    validator_rows: list[dict[str, object]] = []
    validator_started = time.perf_counter()
    validator_rows.extend(run_generic_validators(package_work))
    validator_rows.append(run_package_validator(package_work, "part" if package_work == PACKAGE_PART else "final_resume"))
    validator_elapsed = time.perf_counter() - validator_started
    timing_records.append(
        {
            "stage": "15A6_frozen_validators",
            "stage_version": STAGE_VERSION,
            "started_utc": ".",
            "finished_utc": utc_now(),
            "command": ["FROZEN_TSV_AND_PACKAGE_VALIDATORS"],
            "elapsed_seconds": validator_elapsed,
            "maximum_resident_set_kbytes": ".",
            "production_component": True,
            "outputs": [],
        }
    )

    package_rows, package_exact = package_comparison(package_work)
    require_comparisons(package_rows, "15A5 package")

    if package_work == PACKAGE_PART:
        rewrite_manifest_paths(PACKAGE_PART, PACKAGE_FINAL)
        fsync_tree(PACKAGE_PART)
        if PACKAGE_FINAL.exists():
            raise RuntimeError(f"final package already exists: {PACKAGE_FINAL}")
        os.replace(PACKAGE_PART, PACKAGE_FINAL)
        parent_fd = os.open(RESULT_ROOT, os.O_RDONLY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
        validator_rows.append(run_package_validator(PACKAGE_FINAL, "final_after_atomic_rename"))

    write_validator_ledger(validator_rows)
    write_timing_ledger(timing_records)

    material_qc = read_metric_tsv(PACKAGE_FINAL / "materialization.qc.tsv")
    for table, expected in EXPECTED_COUNTS.items():
        observed = data_rows(PACKAGE_FINAL / f"{table}.tsv.gz", "tsv")
        if observed != expected:
            raise RuntimeError(f"final package row mismatch {table}: {observed} != {expected}")

    production_seconds = sum(
        float(record.get("elapsed_seconds", 0.0))
        for record in timing_records
        if bool(record.get("production_component"))
        and record.get("stage")
        in {
            "15A1_11b",
            "15A2_11d3",
            "15A3_11e",
            "15A4_caller_production",
            "15A5_reference_materializer",
            "15A6_frozen_validators",
        }
    )
    projected_seconds = production_seconds * 53.1
    projected_minutes = projected_seconds / 60.0
    hard_ceiling_status = "PASS" if projected_minutes <= 60.0 else "FAIL"
    target_status = "TARGET_MET" if projected_minutes <= 30.0 else "TARGET_NOT_MET"

    # Recheck active scripts and key frozen sources after the isolated run.
    verify_host_contract()
    verify_frozen_reference_artifacts("after")

    final_qc_rows: list[tuple[str, object]] = [
        ("stage_version", STAGE_VERSION),
        ("run_id", RUN_ID),
        ("stage15a0_parity_gate", "PASS"),
        ("stage15a1_failure_v010", "OBSOLETE_VALIDATOR_PATH_IN_STAGE15A_WRAPPER"),
        ("stage15a1_fix_v011", "FROZEN_VALIDATOR_V0.3.1_NO_BAM_FILTERING"),
        ("stage15a1_unmapped_records_retained", "true"),
        ("stage15a3_failure_v011", "REPORT_ONLY_HEAD_PIPELINE_SIGPIPE_EXIT_141"),
        ("stage15a3_fix_v012", "FROZEN_11E_COPY_USES_FULL_CONSUMER_SED_FOR_TOP30"),
        ("stage15a3_scientific_algorithm_modified", "false"),
        ("isolated_shadow_root", SHADOW),
        ("target_bam", TARGET_BAM),
        ("target_bam_sha256", sha256_file(TARGET_BAM)),
        ("stage15a1_11b_semantic_parity", "true"),
        ("stage15a2_11d3_semantic_parity", "true"),
        ("stage15a3_11e_semantic_parity", "true"),
        ("stage15a4_native_caller_reference_parity", "true"),
        ("stage15a4_hashseed_determinism", "true"),
        ("caller_attempt_rows", metrics0["rows"]),
        ("called_attempt_rows", metrics0["called_attempt_rows"]),
        ("low_confidence_called_rows", metrics0["low_confidence_called_rows"]),
        ("stage15a5_reference_materializer", material_qc.get("audit_status", ".")),
        ("stage15a5_package_exact_logical_parity", str(package_exact).lower()),
        ("general_repeat_calls_rows", EXPECTED_COUNTS["general_repeat_calls"]),
        ("read_evidence_rows", EXPECTED_COUNTS["read_evidence"]),
        ("repeat_event_rows", EXPECTED_COUNTS["repeat_events"]),
        ("repeat_segment_rows", EXPECTED_COUNTS["repeat_segments"]),
        ("repeat_interruption_rows", EXPECTED_COUNTS["repeat_interruptions"]),
        ("frozen_validators", "PASS"),
        ("atomic_publication", "PASS"),
        ("active_pipeline_modified", "false"),
        ("full_5_31m_run_started", "false"),
        ("reference_bam_to_final_seconds", f"{production_seconds:.6f}"),
        ("naive_5_31m_projection_minutes", f"{projected_minutes:.6f}"),
        ("reference_lane_60min_hard_ceiling_projection", hard_ceiling_status),
        ("reference_lane_30min_target", target_status),
        ("correctness_status", "PASS"),
        ("stage15a_overall_status", "IN_PROGRESS"),
        ("audit_status", "PASS"),
        ("next_gate", "BUILD_AND_RUN_STAGE15A_PERFORMANCE_CANDIDATE"),
    ]
    final_qc = QC_ROOT / "stage15a_reference_100k.qc.tsv"
    write_metric_tsv(final_qc, final_qc_rows)

    output_tar = Path.home() / "Downloads/rnatr_stage15a_reference_100k_output_v0.1.2.tar.gz"
    collect_small_artifacts(output_tar)
    digest = sha256_file(output_tar)
    sha_path = Path(str(output_tar) + ".sha256")
    sha_path.write_text(f"{digest}  {output_tar.name}\n", encoding="utf-8")

    print("\n===== STAGE 15A REFERENCE 100K COMPLETE =====")
    for key, value in final_qc_rows:
        print(f"{key}\t{value}")
    print(f"OUTPUT_BUNDLE\t{output_tar}")
    print(f"OUTPUT_BUNDLE_SHA256\t{digest}")
    print(f"OUTPUT_SHA_FILE\t{sha_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        QC_ROOT.mkdir(parents=True, exist_ok=True)
        failure = QC_ROOT / "stage15a_reference_100k.failure.txt"
        failure.write_text(
            f"timestamp_utc\t{utc_now()}\nerror_type\t{type(exc).__name__}\nerror\t{exc}\n",
            encoding="utf-8",
        )
        print(f"ERROR: {exc}", file=sys.stderr)
        print(f"FAILURE_RECORD: {failure}", file=sys.stderr)
        raise
