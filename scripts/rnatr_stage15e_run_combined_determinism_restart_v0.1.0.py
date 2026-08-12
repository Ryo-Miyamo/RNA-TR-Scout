#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import fcntl
import gzip
import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import traceback
from collections import Counter, defaultdict
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

VERSION = "rnatr_stage15e_combined_determinism_restart_v0.1.0"
SELF_NORMALIZED_SHA256 = "3003886bb419bdbda5321469daf70a3fa653485b3cc9264758880259f5c48e71"

PROJECT_ROOT = Path("/mnt/intelssd/rnatr_project")
BASE_RUN_ID = "ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1"
BASE_VERSION = "v0.1.6"
BASE_RESULT_ROOT = (
    PROJECT_ROOT
    / "results/15_stage15c_fullscale_bam_to_final"
    / BASE_RUN_ID
    / BASE_VERSION
)
BASE_QC_ROOT = (
    PROJECT_ROOT
    / "qc/15_stage15c_fullscale_bam_to_final"
    / BASE_RUN_ID
    / BASE_VERSION
)
BASE_SHARDS_ROOT = BASE_RESULT_ROOT / "shards"
BASE_PACKAGE = BASE_RESULT_ROOT / "package_full"
CHECKPOINT_MANIFEST = BASE_QC_ROOT / "stage15c_fullscale_checkpoint_manifest.tsv"
BASE_PACKAGE_MANIFEST = BASE_PACKAGE / "package_manifest.tsv"
BASE_FULL_QC = BASE_QC_ROOT / "stage15c_full_empirical_run.qc.tsv"
BASE_PACKAGE_INTEGRITY = (
    BASE_QC_ROOT / "validators/memory_bounded_prepublication/package_artifact_integrity.tsv"
)
BASE_MEMORY_BOUNDED_QC = (
    BASE_QC_ROOT / "validators/memory_bounded_prepublication/memory_bounded_validator.qc.tsv"
)

RESULT_ROOT = (
    PROJECT_ROOT
    / "results/15_stage15e_determinism_restart"
    / BASE_RUN_ID
    / "v0.1.0"
)
QC_ROOT = (
    PROJECT_ROOT
    / "qc/15_stage15e_determinism_restart"
    / BASE_RUN_ID
    / "v0.1.0"
)
LOG_ROOT = QC_ROOT / "logs"
TIMING_ROOT = QC_ROOT / "timing"
STATE_ROOT = QC_ROOT / "state"
STATE_PATH = STATE_ROOT / "stage15e_state.json"
STATE_SHA_PATH = STATE_ROOT / "stage15e_state.json.sha256"
COMMAND_LEDGER = QC_ROOT / "command_ledger.tsv"
REUSE_SHARDS_ROOT = RESULT_ROOT / "reuse_shards"
PACKAGE_PART = RESULT_ROOT / "package_full.part"
PACKAGE_FINAL = RESULT_ROOT / "package_full"
TARGET_ROOT = RESULT_ROOT / "target_restart/shard_065"
TARGET_CALLER_DIR = TARGET_ROOT / "caller"
TARGET_PACKAGE_DIR = TARGET_ROOT / "package_plain"

TARGET_SHARD = "shard_065"
TARGET_INDEX = 65
TARGET_BASE_ROOT = BASE_SHARDS_ROOT / TARGET_SHARD
TARGET_PROJECT = TARGET_BASE_ROOT / "project"
TARGET_WINDOW_FASTQ = (
    TARGET_BASE_ROOT
    / "raw_root/benchmarks/ENCSR307SHM/stage15c_full5312696_v1"
    / "rnatr_projection_v0.3.3"
    / "ENCFF260PGB.full5312696.rnatr_target_windows.v0.3.3.fastq.gz"
)
TARGET_BASE_CALLS = TARGET_BASE_ROOT / "caller/general_repeat_calls.v0.4.0.tsv.gz"
TARGET_BASE_CALLER_QC = TARGET_BASE_ROOT / "caller/general_repeat_integration.qc.tsv"
TARGET_BASE_PACKAGE = TARGET_BASE_ROOT / "package_plain"

BASE_RUNNER = PROJECT_ROOT / "scripts/rnatr_stage15a_run_performance_100k_v0.2.2.1.py"
FULL_RUNNER = PROJECT_ROOT / "scripts/rnatr_stage15c_run_full5312696_bam_to_final_v0.1.6.py"
CALLER_ADAPTER = PROJECT_ROOT / "scripts/rnatr_stage15a_native_v041_runid_adapter_v0.2.1.py"
MATERIALIZER_ADAPTER = PROJECT_ROOT / "scripts/rnatr_materialize_native_v041_to_evidence_v042_runid_adapter_v0.2.1.py"
MEMORY_BOUNDED_VALIDATOR = PROJECT_ROOT / "scripts/rnatr_stage15b_validate_package_sharded_memory_bounded_v0.1.0.py"
SCHEMA_DIR = PROJECT_ROOT / "config/evidence_schema/v0.4.2"
SCHEMA_JSON = SCHEMA_DIR / "schema/rnatr_v04_table_schema.json"
VALIDATOR_TSV = SCHEMA_DIR / "rnatr_v042_validate_tsv.py"

TABLE_ORDER = (
    "read_evidence",
    "general_repeat_calls",
    "repeat_events",
    "repeat_segments",
    "repeat_interruptions",
)
TABLE_KEY_FIELDS: dict[str, tuple[str, ...]] = {
    "general_repeat_calls": ("projection_id",),
    "read_evidence": ("evidence_id",),
    "repeat_events": ("evidence_id", "event_index", "repeat_event_id"),
    "repeat_segments": ("evidence_id", "repeat_event_id", "segment_index", "repeat_call_id"),
    "repeat_interruptions": (
        "evidence_id", "repeat_event_id", "interruption_index", "interruption_id"
    ),
}
EXPECTED_SHARDS = 144
EXPECTED_CHECKPOINT_ROWS = 1884
EXPECTED_CHECKPOINT_BYTES = 140_029_015_504
EXPECTED_PACKAGE_MANIFEST_ROWS = 10
EXPECTED_PACKAGE_BYTES = 52_420_730_937
EXPECTED_CHECKPOINT_MANIFEST_SHA256 = "f00d67e28413d66730b8c2ffab0f52b9ce9e1553e5cc9a3f9d768e4a7a0083b4"
EXPECTED_PACKAGE_MANIFEST_SHA256 = "335058228a3f3c4205161f3d24b208009175aed5e50f995a74e04100b4f3a738"
EXPECTED_BASE_FULL_QC_SHA256 = "3b95addc1e7aa50ddf22d90dab3373025b9c7b41569fcb2aaea7d2910b35fd07"
AMENDMENT_PREFLIGHT_BUNDLE_SHA256 = "a73f81b903b0146f6a2e2ffed970770cec8cec0ec3c7e6f408488d5d0abe6466"
EXPECTED_HASH_SEED = "20260810"
BASE_HASH_SEED = "0"
MINIMUM_FREE_BYTES = 110_000_000_000
INTENTIONAL_STOP_EXIT_CODE = 75
STOP_CONFIRM = "START_STAGE15E_DETERMINISM_RESTART_V010"
RESUME_CONFIRM = "RESUME_STAGE15E_DETERMINISM_RESTART_V010"
LOCK_PATH = Path("/tmp/rnatr_stage15e_combined_determinism_restart_v010.lock")
DOWNLOADS = Path.home() / "Downloads"

SUCCESS_BUNDLE = DOWNLOADS / "rnatr_stage15e_combined_determinism_restart_v0.1.0_output.tar.gz"
FAILURE_BUNDLE = DOWNLOADS / "rnatr_stage15e_combined_determinism_restart_v0.1.0_failure.tar.gz"
STOP_BUNDLE = DOWNLOADS / "rnatr_stage15e_combined_determinism_restart_v0.1.0_intentional_stop.tar.gz"
FIRST_RESUME_BUNDLE = DOWNLOADS / "rnatr_stage15e_combined_determinism_restart_v0.1.0_first_resume.tar.gz"

SOURCE_GUARDS: dict[Path, str] = {
    FULL_RUNNER: "cca6b2d4c6e773392d3a8c24cd2fd2a1f0a41a713338b4ccdec1ba7fab5bafcc",
    BASE_RUNNER: "7bfb7018cea80cd92854882751cffb49bea817296f69866801a64f9529c5e1a8",
    CALLER_ADAPTER: "18d40dba5733efbfa633fff1d52372db49c63bcf315acb7f86acbdc64c89e386",
    MATERIALIZER_ADAPTER: "7ba7f5082c9671be55b6b223c20f5bc8b933ad8b4658b1789187e043943949d4",
    MEMORY_BOUNDED_VALIDATOR: "1136086f0214bcd11a2a2d71f2e459f433c7fc9f51d170aa3b97826e8808ee99",
    PROJECT_ROOT / "src/rnatr_scout/general_caller/native_v0.4.1/rnatr_general_repeat_caller_ref_v0.4.1.py": "d5a2e0545afa5d97026c3a6ac0be6bc355e87f4c130bc512b0b3bf9a5bf32351",
    PROJECT_ROOT / "src/rnatr_scout/materialization/rnatr_materialize_native_v041_to_evidence_v042_v0.1.2.py": "18a67ef312e74257549570ae81a6cca364055240f519d29dc7664e2ea1c429ea",
    SCHEMA_JSON: "c0509a0669344dba0b07cd1bb9e71f2aeb01e0196df47ec9178f1d2464b515f1",
    SCHEMA_DIR / "rnatr_v042_validate_tsv.py": "10c9d4bbb5c9dac314d400768eb27206173933759c877225bd0ca2c692d8aba9",
    SCHEMA_DIR / "rnatr_v042_validate_package.py": "45c3995550f57a65b3fec4aab7471d57b7000e19471d4c5cf7f3ae055426984e",
    SCHEMA_DIR / "rnatr_v041_validate_package.py": "e978b109d094f665ec62387ffda35c81d0aa9e8156972069f18a1b0b6c49bba5",
    SCHEMA_DIR / "rnatr_v042_validate_flank_uniqueness.py": "039024835de2bc1f096e562eed69788ecad9e481575b1b8cd58241edf2e87ab5",
    SCHEMA_DIR / "rnatr_v04_validate_package.py": "370c93d7730ce919b9c86056f3cd28d49266d41dc34005450d27aaa41d22a96c",
    SCHEMA_DIR / "rnatr_v041_validate_locus_aggregation.py": "dc29030c2d739c87d2d8e3b6eac493e8cf131b2d7f7e819a7d4435bbcd40b29b",
    PROJECT_ROOT / "metadata/ssot/rnatr_ssot.py": "001d91048297e34f4d0663f86075e3c5f8894be751675bf767df6ea940aa2904",
    PROJECT_ROOT / "metadata/ssot/rnatr_ssot.sqlite": "cf50c3a06c81471d38eb244c2ba7c93bd324f6339cfb76771926099558d264ad",
    PROJECT_ROOT / "metadata/ssot/exports/current_pipeline.tsv": "75965e89a6444852cb03c9d8ad0856dd04d136e07ad83316283c5615f82cafb3",
    PROJECT_ROOT / "validation/release_gates_v0.3.0.tsv": "4d5d0572a11ac111c3ac12e1121fd6101ec3a59d7c69e53aa46855f351356715",
    CHECKPOINT_MANIFEST: EXPECTED_CHECKPOINT_MANIFEST_SHA256,
    BASE_PACKAGE_MANIFEST: EXPECTED_PACKAGE_MANIFEST_SHA256,
    BASE_FULL_QC: EXPECTED_BASE_FULL_QC_SHA256,
    BASE_PACKAGE_INTEGRITY: "5d0199ddfa3baa3076530622afa7a3cf6fcbfbd66e6a29d9c7e7e60dafc4219d",
    BASE_MEMORY_BOUNDED_QC: "ff32021f730d7c16f2aa4a8788d803bb49d3a07c42642cbdee412387797d1794",
}

TARGET_INPUT_GUARDS: dict[Path, str] = {
    TARGET_PROJECT / "config/paths.env": "df5f0f6ffe41c381d29dea9a6c172e809a0ca7471e8275253bba89f2c5df9b37",
    TARGET_PROJECT / f"results/11_projection/{BASE_RUN_ID}/v0.3.3/{BASE_RUN_ID}.raw_projection_manifest.v0.3.3.tsv": "37c0080262be3594daae0b8980b61203fea54e9c24287770d8bd9174c2d1df5b",
    TARGET_PROJECT / f"results/11_projection/{BASE_RUN_ID}/v0.3.3/read_target_projection.v0.3.3.tsv.gz": "3ebaeda51ee920fcb977dbe5ad9c1f6f7d182b5b7d13df80e29ee65323ff864f",
    TARGET_WINDOW_FASTQ: "d5e983a52c43e1ea35b2cb33d12a0b1e955c78c0fc7f2d53fa106365cd0f1164",
    TARGET_PROJECT / f"qc/11_projection/{BASE_RUN_ID}/v0.3.3/raw_projection_qc.v0.3.3.tsv": "9b12a38dd2fd9d1bef19f6c3549caff826bef8c88f8cde2b39b30bb8d7d34c75",
    TARGET_PROJECT / f"results/11_projection/{BASE_RUN_ID}/v0.3.3/rnatr_raw_projection_v0.3.3.parameters.tsv": "ab9564d5037c174c5fdbe5ed2dfc860a422b92da9ef1c4a796610c31b5d5121c",
}

EXPECTED_TARGET_WINDOW_FASTQ_BYTES = 46_436_427
EXPECTED_TARGET_WINDOW_FASTQ_RECORDS = 146_524
EXPECTED_TARGET_CALLER_ROWS = 146_558
EXPECTED_TARGET_CALLER_LOGICAL_SHA256: str | None = None  # derived from frozen baseline at execute

EXPECTED_SHARD_ROLES = {
    "shard_bam",
    "shard_full_fastq",
    "assignment",
    "candidate_fastq",
    "projection",
    "motif_jobs",
    "caller_calls",
    "materialization_qc",
    *(f"materialized_{table}" for table in TABLE_ORDER),
}
EXPECTED_FINAL_NAMES = {
    *(f"{table}.tsv" for table in TABLE_ORDER),
    *(f"{table}.tsv.gz" for table in TABLE_ORDER),
    "package_manifest.tsv",
    "materialization.qc.tsv",
}

CALLER_VOLATILE_QC_KEYS = {
    "table_load_seconds",
    "window_fastq_scan_seconds",
    "caller_parallel_wall_seconds",
    "caller_parallel_minutes",
    "jobs_per_second",
}
MATERIALIZER_VOLATILE_QC_KEYS = {
    "input_table_load_seconds",
    "fastq_scan_seconds",
    "materialization_write_seconds",
    "gzip_seconds",
    "materializer_wall_seconds",
}


class HarnessError(RuntimeError):
    pass


class CheckpointMismatch(HarnessError):
    pass


class ExpectedIntentionalStop(Exception):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def normalized_self_sha256(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    normalized = re.sub(
        r'^SELF_NORMALIZED_SHA256 = "[^"]*"$',
        'SELF_NORMALIZED_SHA256 = "<NORMALIZED>"',
        text,
        flags=re.MULTILINE,
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def verify_self_identity() -> None:
    observed = normalized_self_sha256(Path(__file__).resolve())
    if observed != SELF_NORMALIZED_SHA256:
        raise HarnessError(
            f"harness normalized SHA mismatch: {observed} != {SELF_NORMALIZED_SHA256}"
        )


def sha256_file(path: Path, block_size: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            h.update(block)
    return h.hexdigest()


def logical_sha256(path: Path) -> str:
    h = hashlib.sha256()
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def count_data_rows(path: Path) -> int:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rb") as handle:
        count = sum(1 for _ in handle)
    return max(0, count - 1)


def ensure_regular_file(path: Path, *, nonempty: bool = True, reject_symlink: bool = True) -> None:
    if reject_symlink and path.is_symlink():
        raise HarnessError(f"symlink not allowed for frozen input: {path}")
    try:
        st = path.stat()
    except FileNotFoundError as exc:
        raise HarnessError(f"missing file: {path}") from exc
    if not stat.S_ISREG(st.st_mode):
        raise HarnessError(f"not a regular file: {path}")
    if nonempty and st.st_size <= 0:
        raise HarnessError(f"empty file: {path}")


def fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".part")
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    fsync_dir(path.parent)


def atomic_write_json(path: Path, obj: Any) -> None:
    atomic_write_text(path, json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def atomic_write_tsv(path: Path, fieldnames: Sequence[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".part")
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, ".") for key in fieldnames})
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    fsync_dir(path.parent)


def atomic_write_metrics(path: Path, rows: Iterable[tuple[str, Any]]) -> None:
    atomic_write_tsv(path, ["metric", "value"], ({"metric": k, "value": v} for k, v in rows))


def read_dicts(path: Path) -> list[dict[str, str]]:
    ensure_regular_file(path)
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise HarnessError(f"missing TSV header: {path}")
        return list(reader)


def read_metrics(path: Path) -> dict[str, str]:
    rows = read_dicts(path)
    if not rows or set(rows[0]) != {"metric", "value"}:
        raise HarnessError(f"invalid two-column metrics TSV: {path}")
    values: dict[str, str] = {}
    for row in rows:
        key = row["metric"]
        if key in values:
            raise HarnessError(f"duplicate metric {key}: {path}")
        values[key] = row["value"]
    return values


def stat_fingerprint(path: Path) -> dict[str, int]:
    st = path.stat()
    return {
        "bytes": st.st_size,
        "mtime_ns": st.st_mtime_ns,
        "inode": st.st_ino,
        "device": st.st_dev,
    }


def path_is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except ValueError:
        return False


@contextmanager
def exclusive_lock() -> Iterator[None]:
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("a+") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise HarnessError(f"another Stage15E harness process holds {LOCK_PATH}") from exc
        handle.seek(0)
        handle.truncate()
        handle.write(f"pid={os.getpid()}\tstarted={utc_now()}\n")
        handle.flush()
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def verify_environment() -> dict[str, Any]:
    if not PROJECT_ROOT.is_dir():
        raise HarnessError(f"project root missing: {PROJECT_ROOT}")
    if EXPECTED_HASH_SEED == BASE_HASH_SEED:
        raise HarnessError("determinism hash seed must differ from baseline seed")
    observed_hash_seed = os.environ.get("PYTHONHASHSEED", ".")
    if observed_hash_seed != EXPECTED_HASH_SEED:
        raise HarnessError(
            f"scientific invocation requires PYTHONHASHSEED={EXPECTED_HASH_SEED}; "
            f"observed={observed_hash_seed}"
        )
    try:
        import pysam  # type: ignore
    except Exception as exc:
        raise HarnessError(f"pysam import failed: {exc}") from exc
    if getattr(pysam, "__version__", None) != "0.24.0":
        raise HarnessError(f"pysam version mismatch: {getattr(pysam, '__version__', None)} != 0.24.0")
    missing_tools = [tool for tool in ("pigz", "awk", "sort", "wc") if shutil.which(tool) is None]
    if missing_tools:
        raise HarnessError("missing required tools: " + ",".join(missing_tools))
    if not Path("/usr/bin/time").is_file():
        raise HarnessError("missing /usr/bin/time")
    usage = shutil.disk_usage(PROJECT_ROOT)
    if usage.free < MINIMUM_FREE_BYTES:
        raise HarnessError(f"insufficient project free bytes: {usage.free} < {MINIMUM_FREE_BYTES}")
    return {
        "timestamp_utc": utc_now(),
        "python": sys.version,
        "python_executable": sys.executable,
        "pysam_version": getattr(pysam, "__version__", "."),
        "project_total_bytes": usage.total,
        "project_used_bytes": usage.used,
        "project_free_bytes": usage.free,
        "minimum_free_bytes": MINIMUM_FREE_BYTES,
        "logical_cpus": os.cpu_count() or 0,
        "hash_seed_baseline": BASE_HASH_SEED,
        "hash_seed_stage15e": EXPECTED_HASH_SEED,
        "hash_seed_observed": observed_hash_seed,
        "tools": {tool: shutil.which(tool) for tool in ("pigz", "awk", "sort", "wc")},
    }


def verify_guards(label: str, write_report: bool = True) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for guard_class, guards in (("SOURCE_STATE", SOURCE_GUARDS), ("TARGET_INPUT", TARGET_INPUT_GUARDS)):
        for path, expected in guards.items():
            ensure_regular_file(path)
            observed = sha256_file(path)
            status_text = "PASS" if observed == expected else "FAIL"
            rows.append({
                "guard_class": guard_class,
                "path": str(path),
                "bytes": path.stat().st_size,
                "expected_sha256": expected,
                "observed_sha256": observed,
                "status": status_text,
            })
            if status_text != "PASS":
                raise HarnessError(f"guard SHA mismatch: {path}: {observed} != {expected}")
    if TARGET_WINDOW_FASTQ.stat().st_size != EXPECTED_TARGET_WINDOW_FASTQ_BYTES:
        raise HarnessError("target window FASTQ byte mismatch")
    if write_report:
        atomic_write_tsv(
            QC_ROOT / f"guards/{label}.source_and_state_guards.tsv",
            ["guard_class", "path", "bytes", "expected_sha256", "observed_sha256", "status"],
            rows,
        )
    return rows


def copy_frozen_checkpoint_manifest_to_qc() -> Path:
    """Copy the immutable source manifest byte-for-byte before creating a corrupt fixture."""
    ensure_regular_file(CHECKPOINT_MANIFEST)
    destination = QC_ROOT / "contract/frozen_stage15c_checkpoint_manifest.tsv"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        ensure_regular_file(destination)
        observed = sha256_file(destination)
        if observed != EXPECTED_CHECKPOINT_MANIFEST_SHA256:
            raise HarnessError(
                f"existing checkpoint-manifest copy SHA mismatch: {observed}"
            )
        return destination
    temporary = destination.with_name("." + destination.name + ".part")
    if temporary.exists():
        temporary.unlink()
    shutil.copyfile(CHECKPOINT_MANIFEST, temporary)
    fsync_file(temporary)
    observed = sha256_file(temporary)
    if observed != EXPECTED_CHECKPOINT_MANIFEST_SHA256:
        temporary.unlink(missing_ok=True)
        raise HarnessError(
            f"checkpoint-manifest copy SHA mismatch: {observed} != "
            f"{EXPECTED_CHECKPOINT_MANIFEST_SHA256}"
        )
    os.replace(temporary, destination)
    fsync_dir(destination.parent)
    if destination.read_bytes() != CHECKPOINT_MANIFEST.read_bytes():
        raise HarnessError("checkpoint-manifest copy is not byte-identical")
    return destination


def load_checkpoint_manifest() -> list[dict[str, str]]:
    if sha256_file(CHECKPOINT_MANIFEST) != EXPECTED_CHECKPOINT_MANIFEST_SHA256:
        raise HarnessError("checkpoint manifest SHA mismatch")
    rows = read_dicts(CHECKPOINT_MANIFEST)
    required = {"role", "shard", "path", "bytes", "sha256"}
    if not rows or set(rows[0]) != required:
        raise HarnessError(f"checkpoint manifest header mismatch: {set(rows[0]) if rows else set()}")
    if len(rows) != EXPECTED_CHECKPOINT_ROWS:
        raise HarnessError(f"checkpoint row mismatch: {len(rows)} != {EXPECTED_CHECKPOINT_ROWS}")
    total_bytes = sum(int(row["bytes"]) for row in rows)
    if total_bytes != EXPECTED_CHECKPOINT_BYTES:
        raise HarnessError(f"checkpoint byte mismatch: {total_bytes} != {EXPECTED_CHECKPOINT_BYTES}")
    paths = [row["path"] for row in rows]
    if len(paths) != len(set(paths)):
        raise HarnessError("checkpoint manifest contains duplicate paths")
    for row in rows:
        if not re.fullmatch(r"[0-9a-f]{64}", row["sha256"]):
            raise HarnessError(f"invalid checkpoint SHA: {row}")
        path = Path(row["path"])
        if not path.is_absolute() or not path_is_within(path, BASE_RESULT_ROOT):
            raise HarnessError(f"checkpoint path outside frozen result root: {path}")
    by_shard: dict[str, set[str]] = defaultdict(set)
    final_names: set[str] = set()
    for row in rows:
        if row["shard"] == ".":
            if not row["role"].startswith("final_package::"):
                raise HarnessError(f"invalid final checkpoint role: {row['role']}")
            final_names.add(row["role"].split("::", 1)[1])
        else:
            by_shard[row["shard"]].add(row["role"])
            if f"/shards/{row['shard']}/" not in row["path"]:
                raise HarnessError(f"checkpoint shard/path binding mismatch: {row}")
    expected_names = [f"shard_{i:03d}" for i in range(EXPECTED_SHARDS)]
    if sorted(by_shard) != expected_names:
        raise HarnessError("checkpoint shard name set mismatch")
    for shard in expected_names:
        if by_shard[shard] != EXPECTED_SHARD_ROLES:
            raise HarnessError(
                f"checkpoint role set mismatch for {shard}: "
                f"missing={sorted(EXPECTED_SHARD_ROLES - by_shard[shard])} "
                f"extra={sorted(by_shard[shard] - EXPECTED_SHARD_ROLES)}"
            )
    if final_names != EXPECTED_FINAL_NAMES:
        raise HarnessError(
            f"final checkpoint artifact set mismatch: missing={sorted(EXPECTED_FINAL_NAMES-final_names)} "
            f"extra={sorted(final_names-EXPECTED_FINAL_NAMES)}"
        )
    return rows


def load_package_manifest() -> list[dict[str, str]]:
    if sha256_file(BASE_PACKAGE_MANIFEST) != EXPECTED_PACKAGE_MANIFEST_SHA256:
        raise HarnessError("base package manifest SHA mismatch")
    rows = read_dicts(BASE_PACKAGE_MANIFEST)
    required = {"artifact", "table", "rows", "bytes", "sha256", "path"}
    if not rows or set(rows[0]) != required:
        raise HarnessError("base package manifest header mismatch")
    if len(rows) != EXPECTED_PACKAGE_MANIFEST_ROWS:
        raise HarnessError("base package manifest row mismatch")
    if sum(int(row["bytes"]) for row in rows) != EXPECTED_PACKAGE_BYTES:
        raise HarnessError("base package manifest byte mismatch")
    expected_artifacts = {f"{table}{suffix}" for table in TABLE_ORDER for suffix in (".tsv", ".tsv.gz")}
    if {row["artifact"] for row in rows} != expected_artifacts:
        raise HarnessError("base package manifest artifact set mismatch")
    for row in rows:
        if Path(row["path"]) != BASE_PACKAGE / row["artifact"]:
            raise HarnessError(f"base package manifest path mismatch: {row}")
    return rows


def load_baseline_package_integrity(
    package_rows: list[dict[str, str]],
) -> dict[str, dict[str, str]]:
    qc = read_metrics(BASE_MEMORY_BOUNDED_QC)
    required_qc = {
        "validator_version": "rnatr_stage15b_validate_package_sharded_memory_bounded_v0.1.0",
        "artifact_integrity_requested": "true",
        "observed_shards": str(EXPECTED_SHARDS),
        "final_shard_row_parity": "PASS",
        "audit_status": "PASS",
        "validation_status": "PASS",
    }
    for key, expected in required_qc.items():
        if qc.get(key) != expected:
            raise HarnessError(
                f"baseline memory-bounded QC mismatch {key}: {qc.get(key)} != {expected}"
            )

    rows = read_dicts(BASE_PACKAGE_INTEGRITY)
    expected_fields = {
        "artifact", "table", "manifest_rows", "observed_rows",
        "manifest_bytes", "observed_bytes", "manifest_sha256",
        "observed_sha256", "plain_gzip_logical_equal", "status",
    }
    if not rows or set(rows[0]) != expected_fields:
        raise HarnessError("baseline package-integrity header mismatch")
    artifacts = [row["artifact"] for row in rows]
    if len(rows) != EXPECTED_PACKAGE_MANIFEST_ROWS or len(artifacts) != len(set(artifacts)):
        raise HarnessError("baseline package-integrity row/uniqueness mismatch")
    by_artifact = {row["artifact"]: row for row in rows}
    manifest_by_artifact = {row["artifact"]: row for row in package_rows}
    if set(by_artifact) != set(manifest_by_artifact):
        raise HarnessError("baseline package-integrity artifact set mismatch")
    for artifact, manifest in manifest_by_artifact.items():
        record = by_artifact[artifact]
        if not (
            record["table"] == manifest["table"]
            and record["manifest_rows"] == record["observed_rows"] == manifest["rows"]
            and record["manifest_bytes"] == record["observed_bytes"] == manifest["bytes"]
            and record["manifest_sha256"] == record["observed_sha256"] == manifest["sha256"]
            and record["plain_gzip_logical_equal"] == "true"
            and record["status"] == "PASS"
        ):
            raise HarnessError(f"baseline package-integrity binding failed: {artifact}")
    return by_artifact


def verify_package_checkpoint_binding(
    checkpoint_rows: list[dict[str, str]], package_rows: list[dict[str, str]]
) -> None:
    final = {
        row["role"].split("::", 1)[1]: row
        for row in checkpoint_rows
        if row["shard"] == "." and row["role"].startswith("final_package::")
    }
    for row in package_rows:
        cp = final.get(row["artifact"])
        if cp is None:
            raise HarnessError(f"package artifact absent from checkpoint: {row['artifact']}")
        if (cp["path"], cp["bytes"], cp["sha256"]) != (row["path"], row["bytes"], row["sha256"]):
            raise HarnessError(f"package/checkpoint binding mismatch: {row['artifact']}")


def checkpoint_row_map(rows: list[dict[str, str]]) -> dict[tuple[str, str], dict[str, str]]:
    return {(row["shard"], row["role"]): row for row in rows if row["shard"] != "."}


def validate_checkpoint_row(row: dict[str, str]) -> tuple[str, dict[str, int]]:
    path = Path(row["path"])
    ensure_regular_file(path)
    before = stat_fingerprint(path)
    if before["bytes"] != int(row["bytes"]):
        raise CheckpointMismatch(
            f"checkpoint size mismatch: {path}: {before['bytes']} != {row['bytes']}"
        )
    observed = sha256_file(path)
    after = stat_fingerprint(path)
    if before != after:
        raise CheckpointMismatch(f"checkpoint artifact changed while hashing: {path}")
    if observed != row["sha256"]:
        raise CheckpointMismatch(
            f"checkpoint SHA mismatch: {path}: {observed} != {row['sha256']}"
        )
    return observed, before


def rehash_checkpoint(label: str) -> tuple[list[dict[str, Any]], dict[str, dict[str, int]]]:
    rows = load_checkpoint_manifest()
    package_rows = load_package_manifest()
    verify_package_checkpoint_binding(rows, package_rows)
    report: list[dict[str, Any]] = []
    snapshot: dict[str, dict[str, int]] = {}
    cumulative = 0
    next_progress = 10_000_000_000
    started = time.perf_counter()
    print(f"CHECKPOINT_REHASH\t{label}\tSTART\trows={len(rows)}\tbytes={EXPECTED_CHECKPOINT_BYTES}")
    for index, row in enumerate(rows, start=1):
        path = Path(row["path"])
        observed, before = validate_checkpoint_row(row)
        status_text = "PASS"
        report.append({
            "index": index,
            "role": row["role"],
            "shard": row["shard"],
            "path": row["path"],
            "bytes": row["bytes"],
            "expected_sha256": row["sha256"],
            "observed_sha256": observed,
            "mtime_ns": before["mtime_ns"],
            "inode": before["inode"],
            "device": before["device"],
            "status": status_text,
        })
        snapshot[row["path"]] = before
        cumulative += before["bytes"]
        if cumulative >= next_progress or index == len(rows):
            print(
                f"CHECKPOINT_REHASH\t{label}\tPROGRESS\trows={index}/{len(rows)}"
                f"\tbytes={cumulative}/{EXPECTED_CHECKPOINT_BYTES}"
            )
            while next_progress <= cumulative:
                next_progress += 10_000_000_000
    elapsed = time.perf_counter() - started
    report_path = QC_ROOT / f"checkpoint/{label}.checkpoint_rehash.tsv"
    atomic_write_tsv(
        report_path,
        [
            "index", "role", "shard", "path", "bytes", "expected_sha256",
            "observed_sha256", "mtime_ns", "inode", "device", "status",
        ],
        report,
    )
    atomic_write_metrics(
        QC_ROOT / f"checkpoint/{label}.checkpoint_rehash.qc.tsv",
        [
            ("label", label),
            ("checkpoint_manifest", CHECKPOINT_MANIFEST),
            ("checkpoint_manifest_sha256", EXPECTED_CHECKPOINT_MANIFEST_SHA256),
            ("checkpoint_rows", len(rows)),
            ("checkpoint_bytes", cumulative),
            ("elapsed_seconds", f"{elapsed:.9f}"),
            ("full_checkpoint_rehash", "PASS"),
            ("baseline_modified_during_rehash", "false"),
            ("audit_status", "PASS"),
        ],
    )
    print(f"CHECKPOINT_REHASH\t{label}\tPASS\telapsed_seconds={elapsed:.3f}")
    return report, snapshot


def compare_snapshot_to_report(snapshot: dict[str, dict[str, int]], report_path: Path) -> None:
    prior = read_dicts(report_path)
    if len(prior) != EXPECTED_CHECKPOINT_ROWS:
        raise HarnessError("prior checkpoint report row mismatch")
    for row in prior:
        path = row["path"]
        expected = {
            "bytes": int(row["bytes"]),
            "mtime_ns": int(row["mtime_ns"]),
            "inode": int(row["inode"]),
            "device": int(row["device"]),
        }
        if snapshot.get(path) != expected:
            raise HarnessError(f"checkpoint stat changed between stop and resume: {path}")


def verify_snapshot_unchanged(snapshot: dict[str, dict[str, int]], label: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path_text, expected in snapshot.items():
        path = Path(path_text)
        ensure_regular_file(path)
        observed = stat_fingerprint(path)
        status_text = "PASS" if observed == expected else "FAIL"
        rows.append({
            "path": path_text,
            **{f"expected_{k}": v for k, v in expected.items()},
            **{f"observed_{k}": v for k, v in observed.items()},
            "status": status_text,
        })
        if status_text != "PASS":
            raise HarnessError(f"baseline artifact stat changed after reconstruction: {path}")
    atomic_write_tsv(
        QC_ROOT / f"checkpoint/{label}.baseline_stat_immutability.tsv",
        [
            "path", "expected_bytes", "expected_mtime_ns", "expected_inode", "expected_device",
            "observed_bytes", "observed_mtime_ns", "observed_inode", "observed_device", "status",
        ],
        rows,
    )
    return rows


def run_corrupt_manifest_negative_fixture(
    checkpoint_rows: list[dict[str, str]], frozen_manifest_copy: Path
) -> None:
    if ledger_rows():
        raise HarnessError("negative fixture must run before scientific commands")
    ensure_regular_file(frozen_manifest_copy)
    if sha256_file(frozen_manifest_copy) != EXPECTED_CHECKPOINT_MANIFEST_SHA256:
        raise HarnessError("frozen checkpoint-manifest copy changed before negative fixture")
    fixture_rows = [dict(row) for row in checkpoint_rows]
    victim = fixture_rows[0]
    original_sha = victim["sha256"]
    victim["sha256"] = "0" * 64
    fixture_path = QC_ROOT / "negative_fixture/checkpoint_manifest.corrupt.tsv"
    atomic_write_tsv(fixture_path, ["role", "shard", "path", "bytes", "sha256"], fixture_rows)
    victim_path = Path(victim["path"])
    observed = "."
    rejection_message = "."
    try:
        validate_checkpoint_row(victim)
    except CheckpointMismatch as exc:
        observed = sha256_file(victim_path)
        rejection_message = str(exc)
        rejected = observed == original_sha and observed != victim["sha256"]
    else:
        rejected = False
    if not rejected:
        raise HarnessError("corrupt checkpoint fixture was not rejected by the production checkpoint validator")
    atomic_write_metrics(
        QC_ROOT / "negative_fixture/corrupt_checkpoint_rejection.qc.tsv",
        [
            ("fixture_type", "CORRUPTED_SHA_IN_DERIVED_MANIFEST_COPY"),
            ("frozen_manifest_copy", frozen_manifest_copy),
            ("frozen_manifest_copy_sha256", sha256_file(frozen_manifest_copy)),
            ("fixture_manifest", fixture_path),
            ("fixture_manifest_sha256", sha256_file(fixture_path)),
            ("victim_role", victim["role"]),
            ("victim_shard", victim["shard"]),
            ("victim_path", victim_path),
            ("fixture_expected_sha256", victim["sha256"]),
            ("observed_sha256", observed),
            ("rejection_message", rejection_message),
            ("validator_path", "validate_checkpoint_row"),
            ("same_validator_used_for_full_checkpoint_rehash", "true"),
            ("source_checkpoint_artifact_corrupted", "false"),
            ("source_checkpoint_manifest_modified", "false"),
            ("frozen_manifest_copy_modified", "false"),
            ("scientific_commands_before_fixture", 0),
            ("corrupt_checkpoint_rejection", "PASS"),
            ("audit_status", "PASS"),
        ],
    )


def ledger_rows() -> list[dict[str, str]]:
    if not COMMAND_LEDGER.is_file():
        return []
    return read_dicts(COMMAND_LEDGER)


def append_ledger(row: dict[str, Any]) -> None:
    rows: list[dict[str, Any]] = [dict(existing) for existing in ledger_rows()]
    rows.append(row)
    fields = [
        "sequence", "phase", "label", "command_json", "hash_seed", "started_utc",
        "finished_utc", "elapsed_seconds", "returncode", "stdout_log", "time_log", "status",
    ]
    atomic_write_tsv(COMMAND_LEDGER, fields, rows)


def run_timed_command(label: str, phase: str, command: list[str], env_extra: dict[str, str]) -> dict[str, Any]:
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    TIMING_ROOT.mkdir(parents=True, exist_ok=True)
    stdout_log = LOG_ROOT / f"{label}.log"
    time_log = TIMING_ROOT / f"{label}.time_v.txt"
    if stdout_log.exists() or time_log.exists():
        raise HarnessError(f"command log already exists for {label}")
    env = os.environ.copy()
    env.update(env_extra)
    env["LC_ALL"] = "C"
    env["PYTHONUNBUFFERED"] = "1"
    started_utc = utc_now()
    started = time.perf_counter()
    with stdout_log.open("w", encoding="utf-8") as handle:
        proc = subprocess.run(
            ["/usr/bin/time", "-v", "-o", str(time_log), *command],
            stdout=handle,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )
        handle.flush()
        os.fsync(handle.fileno())
    elapsed = time.perf_counter() - started
    row = {
        "sequence": len(ledger_rows()) + 1,
        "phase": phase,
        "label": label,
        "command_json": json.dumps(command, ensure_ascii=False),
        "hash_seed": env.get("PYTHONHASHSEED", "."),
        "started_utc": started_utc,
        "finished_utc": utc_now(),
        "elapsed_seconds": f"{elapsed:.9f}",
        "returncode": proc.returncode,
        "stdout_log": str(stdout_log),
        "time_log": str(time_log),
        "status": "PASS" if proc.returncode == 0 else "FAIL",
    }
    append_ledger(row)
    if proc.returncode != 0:
        raise HarnessError(f"command failed ({label}) returncode={proc.returncode}; log={stdout_log}")
    return row


def compare_stable_metrics(
    baseline_path: Path,
    candidate_path: Path,
    volatile_keys: set[str],
    output_path: Path,
) -> None:
    baseline = read_metrics(baseline_path)
    candidate = read_metrics(candidate_path)
    if set(baseline) != set(candidate):
        raise HarnessError(
            f"metric key set mismatch: {baseline_path.name}: "
            f"missing={sorted(set(baseline)-set(candidate))} extra={sorted(set(candidate)-set(baseline))}"
        )
    rows: list[dict[str, Any]] = []
    failures: list[str] = []
    for key in baseline:
        comparison = "VOLATILE_EXCLUDED" if key in volatile_keys else "EXACT"
        equal = baseline[key] == candidate[key] if comparison == "EXACT" else True
        status_text = "PASS" if equal else "FAIL"
        rows.append({
            "metric": key,
            "comparison": comparison,
            "baseline": baseline[key],
            "candidate": candidate[key],
            "status": status_text,
        })
        if not equal:
            failures.append(key)
    atomic_write_tsv(output_path, ["metric", "comparison", "baseline", "candidate", "status"], rows)
    if failures:
        raise HarnessError("stable metric parity failed: " + ",".join(failures))


def first_logical_difference(left: Path, right: Path, max_text: int = 500) -> dict[str, Any]:
    left_opener = gzip.open if left.suffix == ".gz" else open
    right_opener = gzip.open if right.suffix == ".gz" else open
    with left_opener(left, "rb") as a, right_opener(right, "rb") as b:
        line_number = 0
        while True:
            line_number += 1
            la = a.readline()
            lb = b.readline()
            if la != lb:
                return {
                    "line_number": line_number,
                    "left_sha256": hashlib.sha256(la).hexdigest(),
                    "right_sha256": hashlib.sha256(lb).hexdigest(),
                    "left_excerpt": la[:max_text].decode("utf-8", errors="replace").rstrip("\n"),
                    "right_excerpt": lb[:max_text].decode("utf-8", errors="replace").rstrip("\n"),
                }
            if not la:
                return {"line_number": 0, "left_sha256": ".", "right_sha256": ".", "left_excerpt": ".", "right_excerpt": "."}


def read_tsv_header(path: Path) -> list[str]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", errors="replace", newline="") as handle:
        line = handle.readline()
    return line.rstrip("\r\n").split("\t") if line else []


def table_difference_dossier(
    baseline: Path, candidate: Path, table: str, context: str
) -> dict[str, Any]:
    baseline_rows = count_data_rows(baseline)
    candidate_rows = count_data_rows(candidate)
    baseline_opener = gzip.open if baseline.suffix == ".gz" else open
    candidate_opener = gzip.open if candidate.suffix == ".gz" else open
    with baseline_opener(
        baseline, "rt", encoding="utf-8", errors="replace", newline=""
    ) as baseline_handle, candidate_opener(
        candidate, "rt", encoding="utf-8", errors="replace", newline=""
    ) as candidate_handle:
        baseline_reader = csv.DictReader(baseline_handle, delimiter="\t")
        candidate_reader = csv.DictReader(candidate_handle, delimiter="\t")
        baseline_header = list(baseline_reader.fieldnames or [])
        candidate_header = list(candidate_reader.fieldnames or [])
        first_differing_data_row = 0
        baseline_row: dict[str, str] | None = None
        candidate_row: dict[str, str] | None = None
        while True:
            first_differing_data_row += 1
            try:
                baseline_row = next(baseline_reader)
            except StopIteration:
                baseline_row = None
            try:
                candidate_row = next(candidate_reader)
            except StopIteration:
                candidate_row = None
            if baseline_row != candidate_row:
                break
            if baseline_row is None:
                first_differing_data_row = 0
                break

    key_fields = TABLE_KEY_FIELDS.get(table, ())
    missing_baseline_keys = [field for field in key_fields if field not in baseline_header]
    missing_candidate_keys = [field for field in key_fields if field not in candidate_header]
    key_values: dict[str, dict[str, str]] = {}
    for field in key_fields:
        key_values[field] = {
            "baseline": "." if baseline_row is None else str(baseline_row.get(field, ".")),
            "candidate": "." if candidate_row is None else str(candidate_row.get(field, ".")),
        }

    all_fields = list(dict.fromkeys([*baseline_header, *candidate_header]))
    differing_fields: list[dict[str, str]] = []
    if baseline_row != candidate_row:
        for field in all_fields:
            baseline_value = "." if baseline_row is None else str(baseline_row.get(field, "."))
            candidate_value = "." if candidate_row is None else str(candidate_row.get(field, "."))
            if baseline_value != candidate_value:
                differing_fields.append({
                    "field": field,
                    "baseline": baseline_value[:1000],
                    "candidate": candidate_value[:1000],
                })

    return {
        "context": context,
        "table": table,
        "baseline_path": str(baseline),
        "candidate_path": str(candidate),
        "baseline_rows": baseline_rows,
        "candidate_rows": candidate_rows,
        "baseline_header": baseline_header,
        "candidate_header": candidate_header,
        "header_equal": baseline_header == candidate_header,
        "key_fields": list(key_fields),
        "missing_baseline_key_fields": missing_baseline_keys,
        "missing_candidate_key_fields": missing_candidate_keys,
        "first_differing_data_row": first_differing_data_row,
        "first_difference_key_values": key_values,
        "differing_field_count": len(differing_fields),
        "differing_fields": differing_fields,
        "first_logical_difference": first_logical_difference(baseline, candidate),
        "baseline_raw_sha256": sha256_file(baseline),
        "candidate_raw_sha256": sha256_file(candidate),
        "baseline_logical_sha256": logical_sha256(baseline),
        "candidate_logical_sha256": logical_sha256(candidate),
    }


def compare_target_caller() -> dict[str, Any]:
    candidate_calls = TARGET_CALLER_DIR / "general_repeat_calls.v0.4.0.tsv.gz"
    candidate_qc = TARGET_CALLER_DIR / "general_repeat_integration.qc.tsv"
    for path in (TARGET_BASE_CALLS, TARGET_BASE_CALLER_QC, candidate_calls, candidate_qc):
        ensure_regular_file(path)
    baseline_rows = count_data_rows(TARGET_BASE_CALLS)
    candidate_rows = count_data_rows(candidate_calls)
    baseline_logical = logical_sha256(TARGET_BASE_CALLS)
    candidate_logical = logical_sha256(candidate_calls)
    status_text = "PASS" if (
        baseline_rows == candidate_rows == EXPECTED_TARGET_CALLER_ROWS
        and baseline_logical == candidate_logical
    ) else "FAIL"
    row = {
        "target_shard": TARGET_SHARD,
        "baseline_rows": baseline_rows,
        "candidate_rows": candidate_rows,
        "baseline_raw_sha256": sha256_file(TARGET_BASE_CALLS),
        "candidate_raw_sha256": sha256_file(candidate_calls),
        "baseline_logical_sha256": baseline_logical,
        "candidate_logical_sha256": candidate_logical,
        "logical_parity": str(baseline_logical == candidate_logical).lower(),
        "raw_parity_required": "false",
        "hash_seed_baseline": BASE_HASH_SEED,
        "hash_seed_candidate": EXPECTED_HASH_SEED,
        "status": status_text,
    }
    atomic_write_tsv(
        QC_ROOT / "determinism/target_caller_parity.tsv",
        list(row),
        [row],
    )
    if status_text != "PASS":
        dossier = table_difference_dossier(
            TARGET_BASE_CALLS, candidate_calls, "general_repeat_calls", "TARGET_CALLER"
        )
        atomic_write_json(QC_ROOT / "determinism/target_caller_difference_dossier.json", dossier)
        raise HarnessError("target caller logical parity failed")
    compare_stable_metrics(
        TARGET_BASE_CALLER_QC,
        candidate_qc,
        CALLER_VOLATILE_QC_KEYS,
        QC_ROOT / "determinism/target_caller_qc_stable_parity.tsv",
    )
    return row


def compare_target_materializer(checkpoint_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    row_map = checkpoint_row_map(checkpoint_rows)
    expected_files = {*(f"{table}.tsv" for table in TABLE_ORDER), "materialization.qc.tsv"}
    entries = list(TARGET_PACKAGE_DIR.iterdir())
    invalid_entries = [
        path.name for path in entries
        if path.is_symlink() or not path.is_file()
    ]
    if invalid_entries:
        raise HarnessError(
            "fresh target package contains symlink/non-regular entries: "
            + ",".join(sorted(invalid_entries))
        )
    actual_files = {path.name for path in entries}
    if actual_files != expected_files:
        raise HarnessError(
            f"fresh target package file set mismatch: missing={sorted(expected_files-actual_files)} "
            f"extra={sorted(actual_files-expected_files)}"
        )
    rows: list[dict[str, Any]] = []
    for table in TABLE_ORDER:
        baseline = TARGET_BASE_PACKAGE / f"{table}.tsv"
        candidate = TARGET_PACKAGE_DIR / f"{table}.tsv"
        ensure_regular_file(baseline)
        ensure_regular_file(candidate)
        baseline_sha = sha256_file(baseline)
        candidate_sha = sha256_file(candidate)
        baseline_rows = count_data_rows(baseline)
        candidate_rows = count_data_rows(candidate)
        cp = row_map[(TARGET_SHARD, f"materialized_{table}")]
        status_text = "PASS" if (
            baseline_sha == candidate_sha == cp["sha256"]
            and baseline.stat().st_size == candidate.stat().st_size == int(cp["bytes"])
            and baseline_rows == candidate_rows
        ) else "FAIL"
        rows.append({
            "table": table,
            "baseline_rows": baseline_rows,
            "candidate_rows": candidate_rows,
            "baseline_bytes": baseline.stat().st_size,
            "candidate_bytes": candidate.stat().st_size,
            "checkpoint_sha256": cp["sha256"],
            "baseline_sha256": baseline_sha,
            "candidate_sha256": candidate_sha,
            "raw_parity": str(baseline_sha == candidate_sha).lower(),
            "logical_parity": str(baseline_sha == candidate_sha).lower(),
            "status": status_text,
        })
        if status_text != "PASS":
            dossier = table_difference_dossier(
                baseline, candidate, table, "TARGET_MATERIALIZER"
            )
            atomic_write_json(QC_ROOT / f"determinism/target_materializer_{table}_difference_dossier.json", dossier)
            raise HarnessError(f"target materializer parity failed: {table}")
    atomic_write_tsv(
        QC_ROOT / "determinism/target_materializer_table_parity.tsv",
        list(rows[0]),
        rows,
    )
    compare_stable_metrics(
        TARGET_BASE_PACKAGE / "materialization.qc.tsv",
        TARGET_PACKAGE_DIR / "materialization.qc.tsv",
        MATERIALIZER_VOLATILE_QC_KEYS,
        QC_ROOT / "determinism/target_materializer_qc_stable_parity.tsv",
    )
    return rows


def import_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise HarnessError(f"cannot import module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def create_reuse_shards(checkpoint_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    if REUSE_SHARDS_ROOT.exists():
        raise HarnessError(f"reuse shard root already exists: {REUSE_SHARDS_ROOT}")
    row_map = checkpoint_row_map(checkpoint_rows)
    rows: list[dict[str, Any]] = []
    REUSE_SHARDS_ROOT.mkdir(parents=True)
    for index in range(EXPECTED_SHARDS):
        shard = f"shard_{index:03d}"
        source = TARGET_PACKAGE_DIR if shard == TARGET_SHARD else Path(row_map[(shard, "materialization_qc")]["path"]).parent
        ensure_regular_file(source / "materialization.qc.tsv")
        for table in TABLE_ORDER:
            ensure_regular_file(source / f"{table}.tsv")
        shard_root = REUSE_SHARDS_ROOT / shard
        shard_root.mkdir()
        link = shard_root / "package_plain"
        os.symlink(source, link, target_is_directory=True)
        if link.resolve() != source.resolve():
            raise HarnessError(f"reuse symlink target mismatch: {link}")
        rows.append({
            "shard": shard,
            "source_class": "FRESH_TARGET" if shard == TARGET_SHARD else "FROZEN_BASELINE",
            "source_package": str(source),
            "reuse_link": str(link),
            "status": "PASS",
        })
    atomic_write_tsv(
        QC_ROOT / "reconstruction/reuse_shard_binding.tsv",
        ["shard", "source_class", "source_package", "reuse_link", "status"],
        rows,
    )
    return rows


def configure_merge_modules(package_rows: list[dict[str, str]]):
    base = import_module(BASE_RUNNER, "rnatr_stage15e_base_v0221")
    full = import_module(FULL_RUNNER, "rnatr_stage15e_full_v016")
    expected_rows = {row["table"]: int(row["rows"]) for row in package_rows if row["artifact"].endswith(".tsv")}
    if set(expected_rows) != set(TABLE_ORDER):
        raise HarnessError("could not derive expected final rows")
    full_qc = read_metrics(BASE_FULL_QC)
    called_rows = int(full_qc["caller_called_rows"])

    base.STAGE_VERSION = VERSION
    base.RUN_ID = BASE_RUN_ID
    base.SAMPLE_ID = "ENCSR307SHM"
    base.RESULT_ROOT = RESULT_ROOT
    base.QC_ROOT = QC_ROOT
    base.LOG_ROOT = LOG_ROOT
    base.TIMING_ROOT = TIMING_ROOT
    base.COMPARISON_ROOT = QC_ROOT / "comparison"
    base.CONTRACT_ROOT = QC_ROOT / "contract"
    base.MARKER_ROOT = QC_ROOT / "markers"
    base.SHARDS_ROOT = REUSE_SHARDS_ROOT
    base.PACKAGE_PART = PACKAGE_PART
    base.PACKAGE_FINAL = PACKAGE_FINAL
    base.SCHEMA_DIR = SCHEMA_DIR
    base.SCHEMA_JSON = SCHEMA_JSON
    base.VALIDATOR_TSV = VALIDATOR_TSV
    base.EXPECTED_FINAL_ROWS = dict(expected_rows)
    base.TABLE_ORDER = list(TABLE_ORDER)

    full.VERSION = VERSION
    full.CURRENT_BASE = base
    full.DYNAMIC_CONTEXT.clear()
    full.DYNAMIC_CONTEXT.update({
        "expected_final_rows": dict(expected_rows),
        "caller_totals": {"called_rows": called_rows},
    })
    full.RESULT_ROOT = RESULT_ROOT
    full.QC_ROOT = QC_ROOT
    full.LOG_ROOT = LOG_ROOT
    full.TIMING_ROOT = TIMING_ROOT
    full.PACKAGE_PART = PACKAGE_PART
    full.PACKAGE_FINAL = PACKAGE_FINAL
    full.SHARDS_ROOT = REUSE_SHARDS_ROOT
    full.SCHEMA_DIR = SCHEMA_DIR
    full.SCHEMA_JSON = SCHEMA_JSON
    full.VALIDATOR_TSV = VALIDATOR_TSV
    full.MEMORY_BOUNDED_VALIDATOR = MEMORY_BOUNDED_VALIDATOR
    full.TABLE_ORDER = TABLE_ORDER
    full.SHARDS = EXPECTED_SHARDS
    full.VALIDATOR_WORKERS = 3
    full.EXTERNAL_SORT_BUFFER = "512M"
    full.CALLER_PIPELINE_WORKERS = 1
    base.aggregate_materializer_qc = full.aggregate_materializer_qc_full

    shards = []
    dummy = Path("/dev/null")
    for index in range(EXPECTED_SHARDS):
        name = f"shard_{index:03d}"
        root = REUSE_SHARDS_ROOT / name
        shards.append(
            base.Shard(
                index=index,
                name=name,
                root=root,
                project=root,
                raw_root=root,
                bam=dummy,
                candidate_fastq=dummy,
                script_11b=dummy,
                script_11d3=dummy,
                script_11e=dummy,
            )
        )
    return base, full, shards, expected_rows


def run_reconstruction_and_validators(
    checkpoint_rows: list[dict[str, str]], package_rows: list[dict[str, str]], materializer_elapsed: float
) -> tuple[dict[str, Any], Any]:
    if PACKAGE_PART.exists() or PACKAGE_FINAL.exists():
        raise HarnessError("package part/final must be absent before reconstruction")
    create_reuse_shards(checkpoint_rows)
    base, full, shards, expected_rows = configure_merge_modules(package_rows)
    started = time.perf_counter()
    total, merge_plain, gzip_wall, merge_rows = base.merge_packages(
        shards, materializer_wall=materializer_elapsed
    )
    validator_wall, validator_rows = full.run_validators(base)
    elapsed = time.perf_counter() - started
    atomic_write_metrics(
        QC_ROOT / "reconstruction/stage15e_reconstruction_prepublication.qc.tsv",
        [
            ("harness_version", VERSION),
            ("scope", "CHECKPOINT_BASED_RELEASE_SCALE_RECONSTRUCTION_NOT_UPSTREAM_BAM_PARTITION_11B_11D3_11E_RERUN"),
            ("shards", EXPECTED_SHARDS),
            ("fresh_target_shards", 1),
            ("frozen_reused_shards", EXPECTED_SHARDS - 1),
            ("merge_total_seconds", f"{total:.9f}"),
            ("merge_plain_seconds", f"{merge_plain:.9f}"),
            ("gzip_seconds", f"{gzip_wall:.9f}"),
            ("validator_wall_seconds", f"{validator_wall:.9f}"),
            ("prepublication_elapsed_seconds", f"{elapsed:.9f}"),
            ("package_part", PACKAGE_PART),
            ("package_final_visible", str(PACKAGE_FINAL.exists()).lower()),
            ("atomic_publication", "PENDING_CLEAN_PACKAGE_PARITY"),
            ("expected_rows", json.dumps(expected_rows, sort_keys=True)),
            ("validators_passed", sum(1 for row in validator_rows if row.get("status") == "PASS")),
            ("clean_60_041_benchmark_overwritten", "false"),
            ("audit_status", "PASS_PREPUBLICATION"),
        ],
    )
    return ({
        "merge_total_seconds": total,
        "merge_plain_seconds": merge_plain,
        "gzip_seconds": gzip_wall,
        "validator_wall_seconds": validator_wall,
        "prepublication_elapsed_seconds": elapsed,
        "merge_rows": merge_rows,
        "validator_rows": validator_rows,
        "expected_rows": expected_rows,
    }, base)


def compare_reconstructed_package(
    package_rows: list[dict[str, str]], candidate_root: Path
) -> list[dict[str, Any]]:
    candidate_manifest = candidate_root / "package_manifest.tsv"
    ensure_regular_file(candidate_manifest)
    candidate_rows = read_dicts(candidate_manifest)
    required_manifest_fields = {"artifact", "table", "rows", "bytes", "sha256", "path"}
    if not candidate_rows or set(candidate_rows[0]) != required_manifest_fields:
        raise HarnessError("candidate package manifest header mismatch")
    if len(candidate_rows) != EXPECTED_PACKAGE_MANIFEST_ROWS:
        raise HarnessError(
            f"candidate package manifest row mismatch: {len(candidate_rows)} != "
            f"{EXPECTED_PACKAGE_MANIFEST_ROWS}"
        )
    candidate_artifacts = [row["artifact"] for row in candidate_rows]
    if len(candidate_artifacts) != len(set(candidate_artifacts)):
        raise HarnessError("candidate package manifest contains duplicate artifacts")
    baseline_integrity = load_baseline_package_integrity(package_rows)
    baseline_by = {row["artifact"]: row for row in package_rows}
    candidate_by = {row["artifact"]: row for row in candidate_rows}
    if set(candidate_by) != set(baseline_by):
        raise HarnessError("candidate package manifest artifact set mismatch")
    integrity_path = QC_ROOT / "validators/memory_bounded_prepublication/package_artifact_integrity.tsv"
    integrity_rows = read_dicts(integrity_path)
    integrity_artifacts = [row["artifact"] for row in integrity_rows]
    if len(integrity_artifacts) != len(set(integrity_artifacts)):
        raise HarnessError("package artifact integrity report contains duplicate artifacts")
    integrity = {row["artifact"]: row for row in integrity_rows}
    expected_integrity_artifacts = {f"{table}{suffix}" for table in TABLE_ORDER for suffix in (".tsv", ".tsv.gz")}
    if not expected_integrity_artifacts.issubset(integrity):
        raise HarnessError(
            "package artifact integrity report missing artifacts: "
            + ",".join(sorted(expected_integrity_artifacts - set(integrity)))
        )
    rows: list[dict[str, Any]] = []
    normalized: list[dict[str, Any]] = []
    for table in TABLE_ORDER:
        baseline_plain = baseline_by[f"{table}.tsv"]
        candidate_plain = candidate_by[f"{table}.tsv"]
        baseline_gzip = baseline_by[f"{table}.tsv.gz"]
        candidate_gzip = candidate_by[f"{table}.tsv.gz"]
        candidate_plain_path = candidate_root / f"{table}.tsv"
        candidate_gzip_path = candidate_root / f"{table}.tsv.gz"
        observed_plain = sha256_file(candidate_plain_path)
        observed_gzip = sha256_file(candidate_gzip_path)
        baseline_logical_equal = (
            baseline_integrity[f"{table}.tsv"].get("plain_gzip_logical_equal") == "true"
            and baseline_integrity[f"{table}.tsv.gz"].get("plain_gzip_logical_equal") == "true"
        )
        candidate_logical_equal = (
            integrity[f"{table}.tsv"].get("plain_gzip_logical_equal") == "true"
            and integrity[f"{table}.tsv.gz"].get("plain_gzip_logical_equal") == "true"
        )
        plain_raw_equal = observed_plain == baseline_plain["sha256"]
        gzip_raw_equal = observed_gzip == baseline_gzip["sha256"]
        gzip_logical_parity = (
            baseline_logical_equal and candidate_logical_equal and plain_raw_equal
        )
        manifest_ok = (
            candidate_plain["artifact"] == f"{table}.tsv"
            and candidate_gzip["artifact"] == f"{table}.tsv.gz"
            and candidate_plain["table"] == baseline_plain["table"] == table
            and candidate_gzip["table"] == baseline_gzip["table"] == table
            and candidate_plain["rows"] == baseline_plain["rows"]
            and candidate_gzip["rows"] == baseline_gzip["rows"]
            and candidate_plain["sha256"] == observed_plain
            and candidate_gzip["sha256"] == observed_gzip
            and int(candidate_plain["bytes"]) == candidate_plain_path.stat().st_size
            and int(candidate_gzip["bytes"]) == candidate_gzip_path.stat().st_size
            and Path(candidate_plain["path"]) == PACKAGE_FINAL / f"{table}.tsv"
            and Path(candidate_gzip["path"]) == PACKAGE_FINAL / f"{table}.tsv.gz"
            and integrity[f"{table}.tsv"].get("status") == "PASS"
            and integrity[f"{table}.tsv.gz"].get("status") == "PASS"
        )
        status_text = "PASS" if plain_raw_equal and gzip_logical_parity and manifest_ok else "FAIL"
        rows.append({
            "table": table,
            "rows": baseline_plain["rows"],
            "baseline_plain_sha256": baseline_plain["sha256"],
            "candidate_plain_sha256": observed_plain,
            "plain_raw_parity": str(plain_raw_equal).lower(),
            "baseline_gzip_raw_sha256": baseline_gzip["sha256"],
            "candidate_gzip_raw_sha256": observed_gzip,
            "gzip_raw_parity": str(gzip_raw_equal).lower(),
            "gzip_raw_parity_required": "false",
            "baseline_plain_gzip_logical_equal": str(baseline_logical_equal).lower(),
            "candidate_plain_gzip_logical_equal": str(candidate_logical_equal).lower(),
            "clean_vs_candidate_gzip_logical_parity": str(gzip_logical_parity).lower(),
            "baseline_logical_sha256": baseline_plain["sha256"],
            "candidate_logical_sha256": observed_plain,
            "manifest_binding": "PASS" if manifest_ok else "FAIL",
            "status": status_text,
        })
        for artifact in (f"{table}.tsv", f"{table}.tsv.gz"):
            normalized.append({
                "artifact": artifact,
                "table": table,
                "rows": baseline_plain["rows"],
                "baseline_logical_sha256": baseline_plain["sha256"],
                "candidate_logical_sha256": observed_plain,
                "runtime_path_excluded": "true",
                "status": status_text,
            })
        if status_text != "PASS":
            dossier = table_difference_dossier(
                BASE_PACKAGE / f"{table}.tsv", candidate_plain_path, table, "FULL_PACKAGE"
            )
            atomic_write_json(QC_ROOT / f"determinism/full_package_{table}_difference_dossier.json", dossier)
            raise HarnessError(f"reconstructed package parity failed: {table}")
    atomic_write_tsv(
        QC_ROOT / "determinism/full_package_table_parity.tsv",
        list(rows[0]),
        rows,
    )
    atomic_write_tsv(
        QC_ROOT / "determinism/package_manifest_logical_parity.tsv",
        list(normalized[0]),
        normalized,
    )
    return rows


def scientific_artifact_paths() -> list[Path]:
    paths = [
        TARGET_CALLER_DIR / "general_repeat_calls.v0.4.0.tsv.gz",
        TARGET_CALLER_DIR / "general_repeat_integration.qc.tsv",
        TARGET_PACKAGE_DIR / "materialization.qc.tsv",
    ]
    paths.extend(TARGET_PACKAGE_DIR / f"{table}.tsv" for table in TABLE_ORDER)
    paths.extend(PACKAGE_FINAL / name for name in sorted(EXPECTED_FINAL_NAMES))
    return paths


def create_scientific_snapshot(known_sha256: dict[str, str] | None = None) -> list[dict[str, Any]]:
    known = known_sha256 or {}
    rows: list[dict[str, Any]] = []
    for path in scientific_artifact_paths():
        ensure_regular_file(path)
        fp = stat_fingerprint(path)
        path_text = str(path)
        digest = known[path_text] if path_text in known else sha256_file(path)
        rows.append({
            "path": path_text,
            **fp,
            "sha256": digest,
        })
    atomic_write_tsv(
        QC_ROOT / "noop/scientific_artifact_snapshot.tsv",
        ["path", "bytes", "mtime_ns", "inode", "device", "sha256"],
        rows,
    )
    return rows


def verify_scientific_snapshot_noop() -> list[dict[str, Any]]:
    snapshot_path = QC_ROOT / "noop/scientific_artifact_snapshot.tsv"
    snapshot = read_dicts(snapshot_path)
    expected_paths = {str(path) for path in scientific_artifact_paths()}
    if {row["path"] for row in snapshot} != expected_paths:
        raise HarnessError("scientific snapshot path set mismatch")
    rows: list[dict[str, Any]] = []
    total = sum(int(row["bytes"]) for row in snapshot)
    cumulative = 0
    next_progress = 10_000_000_000
    print(f"SECOND_RESUME_NOOP_REHASH\tSTART\tfiles={len(snapshot)}\tbytes={total}")
    for index, row in enumerate(snapshot, start=1):
        path = Path(row["path"])
        ensure_regular_file(path)
        observed_fp = stat_fingerprint(path)
        observed_sha = sha256_file(path)
        status_text = "PASS" if (
            observed_fp["bytes"] == int(row["bytes"])
            and observed_fp["mtime_ns"] == int(row["mtime_ns"])
            and observed_fp["inode"] == int(row["inode"])
            and observed_fp["device"] == int(row["device"])
            and observed_sha == row["sha256"]
        ) else "FAIL"
        rows.append({
            "path": str(path),
            "expected_bytes": row["bytes"],
            "observed_bytes": observed_fp["bytes"],
            "expected_mtime_ns": row["mtime_ns"],
            "observed_mtime_ns": observed_fp["mtime_ns"],
            "expected_inode": row["inode"],
            "observed_inode": observed_fp["inode"],
            "expected_device": row["device"],
            "observed_device": observed_fp["device"],
            "expected_sha256": row["sha256"],
            "observed_sha256": observed_sha,
            "status": status_text,
        })
        if status_text != "PASS":
            raise HarnessError(f"second-resume no-op artifact changed: {path}")
        cumulative += observed_fp["bytes"]
        if cumulative >= next_progress or index == len(snapshot):
            print(f"SECOND_RESUME_NOOP_REHASH\tPROGRESS\tfiles={index}/{len(snapshot)}\tbytes={cumulative}/{total}")
            while next_progress <= cumulative:
                next_progress += 10_000_000_000
    atomic_write_tsv(
        QC_ROOT / "noop/second_resume_artifact_immutability.tsv",
        list(rows[0]),
        rows,
    )
    print("SECOND_RESUME_NOOP_REHASH\tPASS")
    return rows


def load_state() -> dict[str, Any]:
    ensure_regular_file(STATE_PATH)
    ensure_regular_file(STATE_SHA_PATH)
    fields = STATE_SHA_PATH.read_text(encoding="utf-8").strip().split()
    if len(fields) != 2 or fields[1] != STATE_PATH.name or not re.fullmatch(r"[0-9a-f]{64}", fields[0]):
        raise HarnessError(f"invalid state SHA sidecar: {STATE_SHA_PATH}")
    observed = sha256_file(STATE_PATH)
    if observed != fields[0]:
        raise HarnessError(f"state SHA mismatch: {observed} != {fields[0]}")
    obj = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    if obj.get("harness_version") != VERSION or obj.get("base_run_id") != BASE_RUN_ID:
        raise HarnessError("state identity mismatch")
    return obj


def save_state(state: dict[str, Any]) -> None:
    state["updated_utc"] = utc_now()
    atomic_write_json(STATE_PATH, state)
    digest = sha256_file(STATE_PATH)
    atomic_write_text(STATE_SHA_PATH, f"{digest}  {STATE_PATH.name}\n")


def ensure_new_roots_absent() -> None:
    if RESULT_ROOT.exists() or QC_ROOT.exists():
        raise HarnessError(
            "Stage15E result/QC root already exists; do not rerun intentional-stop. "
            f"result={RESULT_ROOT.exists()} qc={QC_ROOT.exists()}"
        )


def package_selected_files(bundle: Path, label: str, extra_files: Sequence[Path] = ()) -> tuple[Path, str]:
    DOWNLOADS.mkdir(parents=True, exist_ok=True)
    tmp_dir = Path(tempfile.mkdtemp(prefix="rnatr_stage15e_bundle_", dir=str(DOWNLOADS)))
    try:
        root = tmp_dir / label
        root.mkdir()
        candidates: list[Path] = []
        if QC_ROOT.is_dir():
            for path in QC_ROOT.rglob("*"):
                if not path.is_file() or path.is_symlink():
                    continue
                # Full validator shard logs are redundant and can be very large; retain summaries and failures only.
                if "shard_validator_logs" in path.parts and not path.name.endswith("stderr.log"):
                    continue
                if "global_unique_work" in path.parts:
                    continue
                candidates.append(path)
        for path in extra_files:
            if path.is_file() and not path.is_symlink():
                candidates.append(path)
        script = Path(__file__).resolve()
        candidates.append(script)
        for path in (
            PACKAGE_FINAL / "package_manifest.tsv",
            PACKAGE_FINAL / "materialization.qc.tsv",
            TARGET_CALLER_DIR / "general_repeat_integration.qc.tsv",
            TARGET_PACKAGE_DIR / "materialization.qc.tsv",
        ):
            if path.is_file():
                candidates.append(path)
        seen: set[Path] = set()
        manifest_rows: list[dict[str, Any]] = []
        for source in sorted(candidates, key=lambda p: str(p)):
            resolved = source.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            if path_is_within(source, PROJECT_ROOT):
                rel = Path("project") / source.relative_to(PROJECT_ROOT)
            elif source == script:
                rel = Path(script.name)
            else:
                rel = Path("external") / source.name
            destination = root / rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            digest = sha256_file(destination)
            manifest_rows.append({
                "relative_path": rel.as_posix(),
                "bytes": destination.stat().st_size,
                "sha256": digest,
            })
        atomic_write_tsv(root / "artifact_manifest.tsv", ["relative_path", "bytes", "sha256"], manifest_rows)
        tmp_bundle = bundle.with_name("." + bundle.name + ".part")
        if tmp_bundle.exists():
            tmp_bundle.unlink()
        with tarfile.open(tmp_bundle, "w:gz", compresslevel=6) as tf:
            tf.add(root, arcname=root.name, recursive=True)
        os.replace(tmp_bundle, bundle)
        digest = sha256_file(bundle)
        atomic_write_text(Path(str(bundle) + ".sha256"), f"{digest}  {bundle.name}\n")
        return bundle, digest
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def intentional_stop() -> int:
    verify_self_identity()
    ensure_new_roots_absent()
    env_info = verify_environment()
    RESULT_ROOT.mkdir(parents=True)
    QC_ROOT.mkdir(parents=True)
    atomic_write_json(QC_ROOT / "system/intentional_stop_environment.json", env_info)
    verify_guards("intentional_stop_before")
    frozen_manifest_copy = copy_frozen_checkpoint_manifest_to_qc()
    checkpoint_rows = load_checkpoint_manifest()
    package_rows = load_package_manifest()
    verify_package_checkpoint_binding(checkpoint_rows, package_rows)
    _, stop_snapshot = rehash_checkpoint("intentional_stop")
    run_corrupt_manifest_negative_fixture(checkpoint_rows, frozen_manifest_copy)

    if TARGET_CALLER_DIR.exists() or TARGET_PACKAGE_DIR.exists() or PACKAGE_PART.exists() or PACKAGE_FINAL.exists():
        raise HarnessError("fresh outputs unexpectedly exist before caller")
    TARGET_ROOT.mkdir(parents=True, exist_ok=True)
    caller_command = [
        sys.executable,
        str(CALLER_ADAPTER),
        "--project-root", str(TARGET_PROJECT),
        "--run-id", BASE_RUN_ID,
        "--window-fastq", str(TARGET_WINDOW_FASTQ),
        "--outdir", str(TARGET_CALLER_DIR),
        "--workers", "2",
    ]
    caller_record = run_timed_command(
        "target_caller_hashseed20260810",
        "INTENTIONAL_STOP",
        caller_command,
        {"PYTHONHASHSEED": EXPECTED_HASH_SEED},
    )
    caller_parity = compare_target_caller()
    if TARGET_PACKAGE_DIR.exists() or PACKAGE_PART.exists() or PACKAGE_FINAL.exists():
        raise HarnessError("materializer or package became visible before intentional stop")
    verify_snapshot_unchanged(stop_snapshot, "intentional_stop_after_caller")
    verify_guards("intentional_stop_after")
    current_ledger = ledger_rows()
    if len(current_ledger) != 1:
        raise HarnessError(f"intentional-stop command ledger row mismatch: {len(current_ledger)} != 1")
    state = {
        "harness_version": VERSION,
        "base_run_id": BASE_RUN_ID,
        "scope": "CHECKPOINT_BASED_RELEASE_SCALE_RECONSTRUCTION_NOT_UPSTREAM_BAM_PARTITION_11B_11D3_11E_RERUN",
        "phase": "INTENTIONAL_STOP_AFTER_CALLER",
        "created_utc": utc_now(),
        "hash_seed_baseline": BASE_HASH_SEED,
        "hash_seed_stage15e": EXPECTED_HASH_SEED,
        "target_shard": TARGET_SHARD,
        "checkpoint_manifest_sha256": EXPECTED_CHECKPOINT_MANIFEST_SHA256,
        "frozen_checkpoint_manifest_copy": str(frozen_manifest_copy),
        "frozen_checkpoint_manifest_copy_sha256": sha256_file(frozen_manifest_copy),
        "checkpoint_stop_report": str(QC_ROOT / "checkpoint/intentional_stop.checkpoint_rehash.tsv"),
        "checkpoint_stop_report_sha256": sha256_file(QC_ROOT / "checkpoint/intentional_stop.checkpoint_rehash.tsv"),
        "caller_command_record": caller_record,
        "caller_output_sha256": sha256_file(TARGET_CALLER_DIR / "general_repeat_calls.v0.4.0.tsv.gz"),
        "caller_output_logical_sha256": caller_parity["candidate_logical_sha256"],
        "caller_qc_sha256": sha256_file(TARGET_CALLER_DIR / "general_repeat_integration.qc.tsv"),
        "command_ledger_rows": len(current_ledger),
        "command_ledger_sha256": sha256_file(COMMAND_LEDGER),
        "materializer_started": False,
        "package_part_visible": False,
        "package_final_visible": False,
        "active_pipeline_modified": False,
        "ssot_modified": False,
        "core_schema_modified": False,
        "baseline_snapshot_entries": len(stop_snapshot),
    }
    save_state(state)
    atomic_write_metrics(
        QC_ROOT / "stage15e_intentional_stop.qc.tsv",
        [
            ("harness_version", VERSION),
            ("amendment_preflight_bundle_sha256", AMENDMENT_PREFLIGHT_BUNDLE_SHA256),
            ("target_shard", TARGET_SHARD),
            ("target_window_fastq_bytes", EXPECTED_TARGET_WINDOW_FASTQ_BYTES),
            ("target_window_fastq_records_frozen_preflight", EXPECTED_TARGET_WINDOW_FASTQ_RECORDS),
            ("hash_seed_baseline", BASE_HASH_SEED),
            ("hash_seed_stage15e", EXPECTED_HASH_SEED),
            ("frozen_checkpoint_manifest_copied_byte_identical", "PASS"),
            ("frozen_checkpoint_manifest_copy_sha256", sha256_file(frozen_manifest_copy)),
            ("full_checkpoint_rehash_before_reuse", "PASS"),
            ("corrupt_checkpoint_rejection", "PASS"),
            ("fresh_target_caller", "PASS"),
            ("target_caller_logical_parity", "PASS"),
            ("baseline_checkpoint_stat_immutability_after_caller", "PASS"),
            ("source_state_guards_after_caller", "PASS"),
            ("materializer_started", "false"),
            ("package_part_visible", "false"),
            ("package_final_visible", "false"),
            ("intentional_stop", "PASS_EXPECTED"),
            ("intentional_stop_exit_code", INTENTIONAL_STOP_EXIT_CODE),
            ("next_action", "UPLOAD_INTENTIONAL_STOP_BUNDLE_FOR_PRO_REVIEW_BEFORE_RESUME"),
            ("audit_status", "PASS"),
        ],
    )
    bundle, digest = package_selected_files(STOP_BUNDLE, "rnatr_stage15e_intentional_stop_v0.1.0")
    print("===== RNA-TR-SCOUT STAGE15E INTENTIONAL STOP =====")
    print("intentional_stop_status\tPASS_EXPECTED")
    print(f"intentional_stop_exit_code\t{INTENTIONAL_STOP_EXIT_CODE}")
    print("fresh_target_caller\tPASS")
    print("materializer_started\tfalse")
    print("package_final_visible\tfalse")
    print(f"STOP_BUNDLE\t{bundle}")
    print(f"STOP_BUNDLE_SHA256\t{digest}")
    print("next_action\tUPLOAD_STOP_BUNDLE_FOR_PRO_REVIEW_BEFORE_RESUME")
    raise ExpectedIntentionalStop


def first_resume(state: dict[str, Any]) -> int:
    if state.get("phase") != "INTENTIONAL_STOP_AFTER_CALLER":
        raise HarnessError(f"invalid state for first resume: {state.get('phase')}")
    env_info = verify_environment()
    atomic_write_json(QC_ROOT / "system/first_resume_environment.json", env_info)
    verify_guards("first_resume_before")
    frozen_manifest_copy = Path(state["frozen_checkpoint_manifest_copy"])
    if (
        sha256_file(frozen_manifest_copy) != state["frozen_checkpoint_manifest_copy_sha256"]
        or state["frozen_checkpoint_manifest_copy_sha256"] != EXPECTED_CHECKPOINT_MANIFEST_SHA256
    ):
        raise HarnessError("frozen checkpoint-manifest copy changed before resume")
    if sha256_file(QC_ROOT / "checkpoint/intentional_stop.checkpoint_rehash.tsv") != state["checkpoint_stop_report_sha256"]:
        raise HarnessError("intentional-stop checkpoint report changed")
    checkpoint_rows = load_checkpoint_manifest()
    package_rows = load_package_manifest()
    _, resume_snapshot = rehash_checkpoint("first_resume")
    compare_snapshot_to_report(
        resume_snapshot,
        QC_ROOT / "checkpoint/intentional_stop.checkpoint_rehash.tsv",
    )
    if len(ledger_rows()) != int(state["command_ledger_rows"]):
        raise HarnessError("command ledger row count changed before resume")
    if sha256_file(COMMAND_LEDGER) != state["command_ledger_sha256"]:
        raise HarnessError("command ledger content changed before resume")
    candidate_calls = TARGET_CALLER_DIR / "general_repeat_calls.v0.4.0.tsv.gz"
    candidate_qc = TARGET_CALLER_DIR / "general_repeat_integration.qc.tsv"
    if sha256_file(candidate_calls) != state["caller_output_sha256"]:
        raise HarnessError("fresh caller output changed after intentional stop")
    if sha256_file(candidate_qc) != state["caller_qc_sha256"]:
        raise HarnessError("fresh caller QC changed after intentional stop")
    compare_target_caller()
    if TARGET_PACKAGE_DIR.exists() or PACKAGE_PART.exists() or PACKAGE_FINAL.exists():
        raise HarnessError("resume outputs unexpectedly exist before selective materializer")

    materializer_command = [
        sys.executable,
        str(MATERIALIZER_ADAPTER),
        "--project-root", str(TARGET_PROJECT),
        "--run-id", BASE_RUN_ID,
        "--calls", str(candidate_calls),
        "--schema-dir", str(SCHEMA_DIR),
        "--outdir", str(TARGET_PACKAGE_DIR),
        "--sample-id", "ENCSR307SHM",
    ]
    materializer_record = run_timed_command(
        "target_materializer_hashseed20260810",
        "FIRST_RESUME",
        materializer_command,
        {"PYTHONHASHSEED": EXPECTED_HASH_SEED},
    )
    target_materializer_rows = compare_target_materializer(checkpoint_rows)
    if len(ledger_rows()) != int(state["command_ledger_rows"]) + 1:
        raise HarnessError("selective resume command count mismatch")
    if sha256_file(candidate_calls) != state["caller_output_sha256"]:
        raise HarnessError("caller output changed during selective resume")

    reconstruction, merge_base = run_reconstruction_and_validators(
        checkpoint_rows,
        package_rows,
        float(materializer_record["elapsed_seconds"]),
    )
    package_parity_rows = compare_reconstructed_package(package_rows, PACKAGE_PART)
    if PACKAGE_FINAL.exists():
        raise HarnessError("final package became visible before clean-package parity gate")
    publish_started = time.perf_counter()
    publish_wall, publish_row = merge_base.publish_verified_package()
    publication_elapsed = time.perf_counter() - publish_started
    if publish_row.get("status") != "PASS" or PACKAGE_PART.exists() or not PACKAGE_FINAL.is_dir():
        raise HarnessError("atomic publication failed after clean-package parity")
    reconstruction.update({
        "publish_seconds": publish_wall,
        "publication_elapsed_seconds": publication_elapsed,
    })
    atomic_write_metrics(
        QC_ROOT / "reconstruction/stage15e_reconstruction.qc.tsv",
        [
            ("harness_version", VERSION),
            ("scope", "CHECKPOINT_BASED_RELEASE_SCALE_RECONSTRUCTION_NOT_UPSTREAM_BAM_PARTITION_11B_11D3_11E_RERUN"),
            ("shards", EXPECTED_SHARDS),
            ("fresh_target_shards", 1),
            ("frozen_reused_shards", EXPECTED_SHARDS - 1),
            ("merge_total_seconds", f"{reconstruction['merge_total_seconds']:.9f}"),
            ("merge_plain_seconds", f"{reconstruction['merge_plain_seconds']:.9f}"),
            ("gzip_seconds", f"{reconstruction['gzip_seconds']:.9f}"),
            ("validator_wall_seconds", f"{reconstruction['validator_wall_seconds']:.9f}"),
            ("clean_package_parity_before_publication", "PASS"),
            ("atomic_publish_seconds", f"{publish_wall:.9f}"),
            ("package_final", PACKAGE_FINAL),
            ("atomic_publication", "PASS"),
            ("clean_60_041_benchmark_overwritten", "false"),
            ("audit_status", "PASS"),
        ],
    )
    verify_snapshot_unchanged(resume_snapshot, "after_reconstruction")
    verify_guards("first_resume_after")
    known_hashes: dict[str, str] = {
        str(TARGET_CALLER_DIR / "general_repeat_calls.v0.4.0.tsv.gz"): state["caller_output_sha256"],
    }
    for row in target_materializer_rows:
        known_hashes[str(TARGET_PACKAGE_DIR / f"{row['table']}.tsv")] = row["candidate_sha256"]
    for row in package_parity_rows:
        known_hashes[str(PACKAGE_FINAL / f"{row['table']}.tsv")] = row["candidate_plain_sha256"]
        known_hashes[str(PACKAGE_FINAL / f"{row['table']}.tsv.gz")] = row["candidate_gzip_raw_sha256"]
    snapshot_rows = create_scientific_snapshot(known_hashes)
    state.update({
        "phase": "FIRST_RESUME_COMPLETE_AWAITING_NOOP",
        "first_resume_completed_utc": utc_now(),
        "materializer_started": True,
        "materializer_command_record": materializer_record,
        "package_part_visible": PACKAGE_PART.exists(),
        "package_final_visible": PACKAGE_FINAL.exists(),
        "command_ledger_rows_after_first_resume": len(ledger_rows()),
        "command_ledger_sha256_after_first_resume": sha256_file(COMMAND_LEDGER),
        "scientific_snapshot": str(QC_ROOT / "noop/scientific_artifact_snapshot.tsv"),
        "scientific_snapshot_sha256": sha256_file(QC_ROOT / "noop/scientific_artifact_snapshot.tsv"),
        "scientific_snapshot_rows": len(snapshot_rows),
        "reconstruction_metrics": {
            key: value for key, value in reconstruction.items() if key not in {"merge_rows", "validator_rows"}
        },
        "active_pipeline_modified": False,
        "ssot_modified": False,
        "core_schema_modified": False,
    })
    save_state(state)
    atomic_write_metrics(
        QC_ROOT / "stage15e_first_resume.qc.tsv",
        [
            ("harness_version", VERSION),
            ("full_checkpoint_rehash_again_before_resume", "PASS"),
            ("checkpoint_unchanged_between_stop_and_resume", "PASS"),
            ("caller_reexecuted_on_resume", "false"),
            ("selective_materializer_resume", "PASS"),
            ("target_materializer_raw_parity", "PASS"),
            ("fresh_target_used_in_full_reconstruction", "true"),
            ("full_package_plain_raw_parity", "PASS"),
            ("full_package_gzip_logical_parity", "PASS"),
            ("memory_bounded_validator", "PASS"),
            ("atomic_publication", "PASS"),
            ("package_final_visible", "true"),
            ("baseline_result_modified", "false"),
            ("clean_60_041_benchmark_overwritten", "false"),
            ("second_resume_noop", "PENDING"),
            ("next_action", "RUN_SAME_RESUME_COMMAND_A_SECOND_TIME"),
            ("audit_status", "PASS_FIRST_RESUME"),
        ],
    )
    bundle, digest = package_selected_files(
        FIRST_RESUME_BUNDLE,
        "rnatr_stage15e_first_resume_v0.1.0",
    )
    print("===== RNA-TR-SCOUT STAGE15E FIRST RESUME =====")
    print("first_resume_status\tPASS")
    print("selective_resume\tPASS")
    print("full_package_reconstruction\tPASS")
    print("atomic_publication\tPASS")
    print("second_resume_noop\tPENDING")
    print(f"FIRST_RESUME_BUNDLE\t{bundle}")
    print(f"FIRST_RESUME_BUNDLE_SHA256\t{digest}")
    print("next_action\tRUN_THE_SAME_RESUME_COMMAND_ONCE_MORE")
    return 0


def second_resume_noop(state: dict[str, Any]) -> int:
    if state.get("phase") != "FIRST_RESUME_COMPLETE_AWAITING_NOOP":
        raise HarnessError(f"invalid state for second resume: {state.get('phase')}")
    ledger_before = ledger_rows()
    expected_ledger_rows = int(state["command_ledger_rows_after_first_resume"])
    if len(ledger_before) != expected_ledger_rows:
        raise HarnessError("command ledger row count changed before second resume")
    if sha256_file(COMMAND_LEDGER) != state["command_ledger_sha256_after_first_resume"]:
        raise HarnessError("command ledger content changed before second resume")
    if sha256_file(QC_ROOT / "noop/scientific_artifact_snapshot.tsv") != state["scientific_snapshot_sha256"]:
        raise HarnessError("scientific snapshot manifest changed")
    verify_self_identity()
    # No subprocess or scientific-stage function is invoked below this point.
    verify_guards("second_resume_noop")
    verify_scientific_snapshot_noop()
    if len(ledger_rows()) != expected_ledger_rows:
        raise HarnessError("command was executed during second-resume no-op")
    if PACKAGE_PART.exists():
        raise HarnessError("package part reappeared during no-op")
    if not PACKAGE_FINAL.is_dir():
        raise HarnessError("published package missing during no-op")
    atomic_write_metrics(
        QC_ROOT / "noop/second_resume_noop.qc.tsv",
        [
            ("harness_version", VERSION),
            ("invocation", "SECOND_RESUME"),
            ("scientific_command_execution_count", 0),
            ("caller_reexecuted", "false"),
            ("materializer_reexecuted", "false"),
            ("merge_reexecuted", "false"),
            ("validator_reexecuted", "false"),
            ("package_rewritten", "false"),
            ("scientific_artifact_size_mtime_inode_sha_unchanged", "PASS"),
            ("second_resume_noop", "PASS"),
            ("audit_status", "PASS"),
        ],
    )
    state.update({
        "phase": "COMPLETE",
        "completed_utc": utc_now(),
        "second_resume_noop": "PASS",
        "second_resume_scientific_command_count": 0,
        "release_scale_determinism": "PASS_CHECKPOINT_BASED_RECONSTRUCTION_SCOPE",
        "fullscale_restart_resume": "PASS_SELECTIVE_CALLER_TO_FINAL_SCOPE",
    })
    save_state(state)
    atomic_write_metrics(
        QC_ROOT / "stage15e_combined_determinism_restart.qc.tsv",
        [
            ("stage_version", VERSION),
            ("run_id", BASE_RUN_ID),
            ("scope", "CHECKPOINT_BASED_RELEASE_SCALE_RECONSTRUCTION_NOT_UPSTREAM_BAM_PARTITION_11B_11D3_11E_RERUN"),
            ("baseline_hash_seed", BASE_HASH_SEED),
            ("determinism_hash_seed", EXPECTED_HASH_SEED),
            ("hash_seed_different", "true"),
            ("full_checkpoint_rehash_before_stop", "PASS"),
            ("full_checkpoint_rehash_before_resume", "PASS"),
            ("corrupt_checkpoint_rejection", "PASS_COPIED_MANIFEST_SHA_NEGATIVE_FIXTURE"),
            ("source_checkpoint_artifact_corrupted", "false"),
            ("intentional_stop_after_fresh_caller", "PASS"),
            ("final_package_visible_at_stop", "false"),
            ("selective_resume_caller_reused", "PASS"),
            ("selective_resume_materializer_executed", "PASS"),
            ("target_caller_logical_parity", "PASS"),
            ("target_materializer_raw_parity", "PASS"),
            ("full_reconstruction_shards", EXPECTED_SHARDS),
            ("fresh_target_shards", 1),
            ("full_package_plain_raw_parity", "PASS"),
            ("full_package_gzip_logical_parity", "PASS"),
            ("package_manifest_logical_parity", "PASS"),
            ("baseline_package_integrity_evidence", "PASS_GUARDED_STAGE15C_MEMORY_BOUNDED_VALIDATOR"),
            ("frozen_validators", "PASS"),
            ("memory_bounded_validator", "PASS"),
            ("atomic_publication", "PASS"),
            ("second_resume_noop", "PASS"),
            ("second_resume_scientific_commands", 0),
            ("release_scale_determinism", "PASS_CHECKPOINT_BASED_RECONSTRUCTION_SCOPE"),
            ("fullscale_restart_resume", "PASS_SELECTIVE_CALLER_TO_FINAL_SCOPE"),
            ("clean_full_runtime_minutes", "60.041256352"),
            ("clean_full_runtime_status", "PASS_WITH_DOCUMENTED_TOLERANCE"),
            ("clean_runtime_benchmark_overwritten", "false"),
            ("baseline_result_modified", "false"),
            ("baseline_qc_modified", "false"),
            ("active_pipeline_modified", "false"),
            ("ssot_modified", "false"),
            ("core_schema_modified", "false"),
            ("stage_status", "PASS"),
            ("audit_status", "PASS"),
            ("next_gate", "REGISTER_STAGE15E_DETERMINISM_RESTART_AND_BEGIN_CORE_FREEZE_REVIEW"),
        ],
    )
    bundle, digest = package_selected_files(
        SUCCESS_BUNDLE,
        "rnatr_stage15e_combined_determinism_restart_v0.1.0_output",
    )
    print("===== RNA-TR-SCOUT STAGE15E COMBINED FINAL =====")
    print("release_scale_determinism\tPASS_CHECKPOINT_BASED_RECONSTRUCTION_SCOPE")
    print("fullscale_restart_resume\tPASS_SELECTIVE_CALLER_TO_FINAL_SCOPE")
    print("second_resume_noop\tPASS")
    print("clean_runtime_benchmark_overwritten\tfalse")
    print("active_pipeline_modified\tfalse")
    print("ssot_modified\tfalse")
    print("core_schema_modified\tfalse")
    print("audit_status\tPASS")
    print("next_gate\tREGISTER_STAGE15E_DETERMINISM_RESTART_AND_BEGIN_CORE_FREEZE_REVIEW")
    print(f"OUTPUT_BUNDLE\t{bundle}")
    print(f"OUTPUT_BUNDLE_SHA256\t{digest}")
    return 0


def already_complete(state: dict[str, Any]) -> int:
    if state.get("phase") != "COMPLETE":
        raise HarnessError("unexpected complete-state handler")
    verify_self_identity()
    verify_guards("already_complete")
    if not PACKAGE_FINAL.is_dir():
        raise HarnessError("complete state exists but published package is missing")
    final_qc = QC_ROOT / "stage15e_combined_determinism_restart.qc.tsv"
    metrics = read_metrics(final_qc)
    if metrics.get("audit_status") != "PASS" or metrics.get("stage_status") != "PASS":
        raise HarnessError("complete state exists but final Stage15E QC is not PASS")

    sidecar = Path(str(SUCCESS_BUNDLE) + ".sha256")
    bundle_status = "REUSED_EXISTING"
    digest = "."
    if SUCCESS_BUNDLE.is_file() and sidecar.is_file():
        tokens = sidecar.read_text(encoding="utf-8").strip().split()
        if tokens and re.fullmatch(r"[0-9a-f]{64}", tokens[0]):
            observed = sha256_file(SUCCESS_BUNDLE)
            if observed == tokens[0]:
                digest = observed
            else:
                bundle_status = "RECREATED_AFTER_SHA_MISMATCH"
        else:
            bundle_status = "RECREATED_AFTER_INVALID_SIDECAR"
    else:
        bundle_status = "RECREATED_AFTER_MISSING_BUNDLE_OR_SIDECAR"
    if digest == ".":
        _, digest = package_selected_files(
            SUCCESS_BUNDLE,
            "rnatr_stage15e_combined_determinism_restart_v0.1.0_output",
        )

    print("stage15e_status\tALREADY_COMPLETE")
    print("release_scale_determinism\tPASS_CHECKPOINT_BASED_RECONSTRUCTION_SCOPE")
    print("fullscale_restart_resume\tPASS_SELECTIVE_CALLER_TO_FINAL_SCOPE")
    print(f"output_bundle_status\t{bundle_status}")
    print(f"OUTPUT_BUNDLE\t{SUCCESS_BUNDLE}")
    print(f"OUTPUT_BUNDLE_SHA256\t{digest}")
    return 0


def resume() -> int:
    verify_self_identity()
    if not RESULT_ROOT.is_dir() or not QC_ROOT.is_dir():
        raise HarnessError("Stage15E roots do not exist; intentional-stop must run first")
    state = load_state()
    phase = state.get("phase")
    if phase == "INTENTIONAL_STOP_AFTER_CALLER":
        return first_resume(state)
    if phase == "FIRST_RESUME_COMPLETE_AWAITING_NOOP":
        return second_resume_noop(state)
    if phase == "COMPLETE":
        return already_complete(state)
    raise HarnessError(f"unsupported state phase: {phase}")


def self_test() -> int:
    verify_self_identity()
    with tempfile.TemporaryDirectory(prefix="rnatr_stage15e_selftest_") as tmp_text:
        tmp = Path(tmp_text)
        plain = tmp / "x.tsv"
        gz = tmp / "x.tsv.gz"
        atomic_write_text(plain, "id\tvalue\na\t1\nb\t2\n")
        with gz.open("wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=1, mtime=0) as handle:
                handle.write(plain.read_bytes())
        if logical_sha256(gz) != sha256_file(plain):
            raise HarnessError("self-test logical gzip hash failed")
        metrics_a = tmp / "a.tsv"
        metrics_b = tmp / "b.tsv"
        atomic_write_metrics(metrics_a, [("stable", "x"), ("elapsed_seconds", "1")])
        atomic_write_metrics(metrics_b, [("stable", "x"), ("elapsed_seconds", "2")])
        old_qc = globals()["QC_ROOT"]
        try:
            globals()["QC_ROOT"] = tmp / "qc"
            compare_stable_metrics(metrics_a, metrics_b, {"elapsed_seconds"}, tmp / "qc/parity.tsv")
        finally:
            globals()["QC_ROOT"] = old_qc
        snap = stat_fingerprint(plain)
        if snap["bytes"] != plain.stat().st_size:
            raise HarnessError("self-test stat fingerprint failed")
        rows = [{"relative_path": "x.tsv", "bytes": plain.stat().st_size, "sha256": sha256_file(plain)}]
        atomic_write_tsv(tmp / "manifest.tsv", list(rows[0]), rows)
        if read_dicts(tmp / "manifest.tsv")[0]["sha256"] != rows[0]["sha256"]:
            raise HarnessError("self-test TSV roundtrip failed")
        checkpoint_row = {
            "role": "fixture",
            "shard": "shard_000",
            "path": str(plain),
            "bytes": str(plain.stat().st_size),
            "sha256": sha256_file(plain),
        }
        validate_checkpoint_row(checkpoint_row)
        corrupt = dict(checkpoint_row)
        corrupt["sha256"] = "0" * 64
        try:
            validate_checkpoint_row(corrupt)
        except CheckpointMismatch:
            pass
        else:
            raise HarnessError("self-test corrupt checkpoint rejection failed")
        diff = first_logical_difference(plain, plain)
        if diff["line_number"] != 0:
            raise HarnessError("self-test logical comparison failed")
        different = tmp / "different.tsv"
        atomic_write_text(different, "id\tvalue\na\t1\nb\t3\n")
        old_keys = dict(TABLE_KEY_FIELDS)
        try:
            TABLE_KEY_FIELDS["fixture"] = ("id",)
            dossier = table_difference_dossier(plain, different, "fixture", "SELF_TEST")
        finally:
            TABLE_KEY_FIELDS.clear()
            TABLE_KEY_FIELDS.update(old_keys)
        if (
            dossier["first_differing_data_row"] != 2
            or dossier["first_difference_key_values"].get("id", {}).get("baseline") != "b"
            or dossier["differing_field_count"] != 1
        ):
            raise HarnessError("self-test key/field difference dossier failed")
    print("SELF_TEST\tPASS")
    print(f"version\t{VERSION}")
    print(f"normalized_source_sha256\t{SELF_NORMALIZED_SHA256}")
    print(f"intentional_stop_exit_code\t{INTENTIONAL_STOP_EXIT_CODE}")
    return 0


def failure_bundle(exc: BaseException) -> None:
    try:
        DOWNLOADS.mkdir(parents=True, exist_ok=True)
        failure_root = QC_ROOT if QC_ROOT.exists() else DOWNLOADS / ".rnatr_stage15e_failure_context"
        failure_root.mkdir(parents=True, exist_ok=True)
        atomic_write_text(
            failure_root / "stage15e_failure.txt",
            "\n".join([
                f"harness_version\t{VERSION}",
                f"failure_time_utc\t{utc_now()}",
                f"exception_type\t{type(exc).__name__}",
                f"exception\t{exc}",
                f"result_root_exists\t{str(RESULT_ROOT.exists()).lower()}",
                f"qc_root_exists\t{str(QC_ROOT.exists()).lower()}",
                f"package_part_exists\t{str(PACKAGE_PART.exists()).lower()}",
                f"package_final_exists\t{str(PACKAGE_FINAL.exists()).lower()}",
                "active_pipeline_modified\tfalse",
                "ssot_modified\tfalse",
                "core_schema_modified\tfalse",
                "",
                traceback.format_exc(),
            ]) + "\n",
        )
        bundle, digest = package_selected_files(
            FAILURE_BUNDLE,
            "rnatr_stage15e_combined_determinism_restart_v0.1.0_failure",
            [failure_root / "stage15e_failure.txt"],
        )
        print(f"FAILURE_BUNDLE\t{bundle}", file=sys.stderr)
        print(f"FAILURE_BUNDLE_SHA256\t{digest}", file=sys.stderr)
    except Exception as bundle_exc:
        print(f"WARNING: failure bundle creation failed: {bundle_exc}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="RNA-TR-Scout Stage15E checkpoint-based release-scale determinism and restart/resume harness"
    )
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--self-test", action="store_true")
    modes.add_argument("--intentional-stop", action="store_true")
    modes.add_argument("--resume", action="store_true")
    parser.add_argument("--confirm-run-id", default="")
    parser.add_argument("--confirm-action", default="")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if args.confirm_run_id != BASE_RUN_ID:
        raise HarnessError(f"--confirm-run-id must exactly equal {BASE_RUN_ID}")
    expected_action = STOP_CONFIRM if args.intentional_stop else RESUME_CONFIRM
    if args.confirm_action != expected_action:
        raise HarnessError(f"--confirm-action must exactly equal {expected_action}")
    with exclusive_lock():
        if args.intentional_stop:
            return intentional_stop()
        return resume()


if __name__ == "__main__":
    try:
        exit_code = main()
    except ExpectedIntentionalStop:
        raise SystemExit(INTENTIONAL_STOP_EXIT_CODE)
    except Exception as exc:
        failure_bundle(exc)
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
    else:
        raise SystemExit(exit_code)
