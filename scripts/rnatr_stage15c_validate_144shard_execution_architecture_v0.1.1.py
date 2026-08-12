#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import hashlib
import importlib.util
import os
import resource as resource_module
import shutil
import subprocess
import sys
import tarfile
import time
import traceback
from pathlib import Path
from typing import Iterable

VERSION = "rnatr_stage15c_validate_144shard_execution_architecture_v0.1.1"
PROJECT_ROOT = Path("/mnt/intelssd/rnatr_project")
SAMPLE_ID = "ENCSR307SHM"
RUN_ID = "ENCSR307SHM_stage15a500k_seed20260809_mm2splice_v1"
PLANNED_FULL_RUN_ID = "ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1"
BENCHMARK_READS = 500_000
FULL_READS = 5_312_696
SHARD_COUNT = 144
STAGE_CONCURRENCY = 12
CALLER_WORKERS_PER_SHARD = 2
VALIDATOR_WORKERS = 3
VALIDATOR_SORT_BUFFER = "512M"
PYTHON_HASH_SEED = "0"
MEMORY_SAFETY_FACTOR = 1.25
MEMORY_FRACTION_LIMIT = 0.80
FIT_R2_MINIMUM = 0.90
FIT_STABLE_DYNAMIC_FRACTION_MAXIMUM = 0.15
FIT_STABLE_OBSERVED_RANGE_FRACTION_MAXIMUM = 0.25
FIT_RESIDUAL_MULTIPLIER = 2.0
SYSTEM_RESERVE_KB = 8 * 1024 * 1024
MIN_FREE_BYTES_BEFORE_AUDIT = 300_000_000_000
MIN_FREE_BYTES_AFTER_AUDIT = 250_066_597_000
MIN_NOFILE_SOFT = 512

BASE_RUNNER = PROJECT_ROOT / "scripts/rnatr_stage15a_run_performance_100k_v0.2.2.1.py"
BASE_RUNNER_SHA256 = "7bfb7018cea80cd92854882751cffb49bea817296f69866801a64f9529c5e1a8"
SCALING_RUNNER = PROJECT_ROOT / "scripts/rnatr_stage15a_run_scaling_500k_v0.1.1.py"
SCALING_RUNNER_SHA256 = "bc1718cd5044a472956e445b19ac3f193ffc0db868b1f53dbfe896c1e86892a6"
BOUNDED_VALIDATOR = PROJECT_ROOT / "scripts/rnatr_stage15b_validate_package_sharded_memory_bounded_v0.1.0.py"
BOUNDED_VALIDATOR_SHA256 = "1136086f0214bcd11a2a2d71f2e459f433c7fc9f51d170aa3b97826e8808ee99"
PREFLIGHT_QC = (
    PROJECT_ROOT / "qc/15_stage15c_fullscale_preflight" / SAMPLE_ID / "v0.1.0"
    / "stage15c_fullscale_preflight.qc.tsv"
)
PREFLIGHT_QC_SHA256 = "8363e0967621183ae7085cc8dfcfbdd4277b84214dad0d88074d03d8c4e50547"
# The project-side preflight QC is guarded by the exact SHA captured in the
# successfully uploaded Stage 15C bundle. The bundle itself is not used as an
# execution source.

STAGE15B_QC = (
    PROJECT_ROOT / "qc/15_stage15b_memory_bounded_validator" / RUN_ID
    / "v0.1.0/stage15b_memory_bounded_validator.qc.tsv"
)
STAGE15B_QC_SHA256 = "b5f7f26f91d0edafbdc77de3373b67b8cc9ec3e16fb2f903cec4390a9d47f142"
STAGE15B_REFERENCE_VALIDATOR_TIMING = (
    PROJECT_ROOT / "qc/15_stage15b_memory_bounded_validator" / RUN_ID
    / "v0.1.0/positive_500k_candidate/shard_frozen_v042_validation.tsv"
)
STAGE15B_REFERENCE_VALIDATOR_TIMING_SHA256 = "f9491e4c47209e9c09587693e1b0dae036acf56dbc73300936badf0890cc539a"

INPUT_QC = (
    PROJECT_ROOT / "qc/15_stage15a_inputs" / RUN_ID
    / "rnatr_stage15a_500k_input_v0.1.0/stage15a_500k_input.qc.tsv"
)
REFERENCE_ROOT = (
    PROJECT_ROOT / "results/15_stage15a_bam_to_final" / RUN_ID
    / "v0.1.1_500k_scaling/replicate_A"
)
REFERENCE_QC_ROOT = (
    PROJECT_ROOT / "qc/15_stage15a_bam_to_final" / RUN_ID
    / "v0.1.1_500k_scaling/replicate_A"
)
REFERENCE_PACKAGE = REFERENCE_ROOT / "package_performance"
REFERENCE_CANDIDATE_COUNTS = REFERENCE_QC_ROOT / "stage15a_scaling_500k_11b_counts.tsv"
REFERENCE_CALLER_TIMING = REFERENCE_QC_ROOT / "15AS4_native_caller.per_shard.tsv"
REFERENCE_MATERIALIZER_TIMING = REFERENCE_QC_ROOT / "15AS5_materializer.per_shard.tsv"
REFERENCE_COMBINED_QC = (
    PROJECT_ROOT / "qc/15_stage15a_bam_to_final" / RUN_ID
    / "v0.1.1_500k_scaling/stage15a_scaling_500k.qc.tsv"
)
REFERENCE_COMBINED_QC_SHA256 = "ef27be62e633e941b21978d8354a928a7ecea33600465fe6620e82640b329e82"
REFERENCE_PACKAGE_MANIFEST = REFERENCE_PACKAGE / "package_manifest.tsv"
REFERENCE_PACKAGE_MANIFEST_SHA256 = "8dabd9db91af5e80e6b47416d144307cee0011e26f76f98622dcacfa24f716cb"

RESULT_BASE = (
    PROJECT_ROOT / "results/15_stage15c_execution_architecture" / RUN_ID
    / "v0.1.1_144shard_500k"
)
QC_BASE = (
    PROJECT_ROOT / "qc/15_stage15c_execution_architecture" / RUN_ID
    / "v0.1.1_144shard_500k"
)
REP_LABEL = "S144"
RESULT_ROOT = RESULT_BASE / f"replicate_{REP_LABEL}"
QC_ROOT = QC_BASE / f"replicate_{REP_LABEL}"
DOC_PATH = (
    PROJECT_ROOT / "docs/stage15c"
    / "RNA_TR_Scout_144shard_fullscale_execution_architecture_validation_v0.1.1.md"
)
PLANNED_GATES_PATH = (
    PROJECT_ROOT / "validation/release_readiness_planned_gates_v0.1.0.tsv"
)
SCRIPT_INSTALL = PROJECT_ROOT / "scripts/rnatr_stage15c_validate_144shard_execution_architecture_v0.1.1.py"
META_ROOT = PROJECT_ROOT / "metadata/stage15c/144shard_execution_architecture_v0.1.1"
DOWNLOADS = Path.home() / "Downloads"
SUCCESS_BUNDLE = DOWNLOADS / "rnatr_stage15c_144shard_execution_architecture_v0.1.1.tar.gz"
FAILURE_BUNDLE = DOWNLOADS / "rnatr_stage15c_144shard_execution_architecture_v0.1.1_failure.tar.gz"

CORE_TABLES = (
    "general_repeat_calls",
    "read_evidence",
    "repeat_events",
    "repeat_segments",
    "repeat_interruptions",
)

EXTRA_GUARDS = {
    BASE_RUNNER: BASE_RUNNER_SHA256,
    SCALING_RUNNER: SCALING_RUNNER_SHA256,
    BOUNDED_VALIDATOR: BOUNDED_VALIDATOR_SHA256,
    PROJECT_ROOT / "scripts/11b_extract_alignment_segments_and_target_candidates.stage15a500k_runid_v0.1.0.sh":
        "ccf37ebbe71451f12d113cb4148e5415ad7cbcd59ef954b7b7dd7a6b69078075",
    PROJECT_ROOT / "scripts/11d3_project_targets_to_raw_reads.stage15a500k_runid_v0.1.0.sh":
        "d7411df47e54e672ea3c838746402d35787c0d1c2fe0af628e7a7f36d98ea203",
    PROJECT_ROOT / "scripts/11e_prepare_motif_scan_jobs.stage15a500k_runid_v0.1.0.sh":
        "b648b24f22c96fa5625baf09313500c2ca54668ed318ed0aa49570a10c743e3b",
    PROJECT_ROOT / "scripts/rnatr_stage15a_native_v041_runid_adapter_v0.2.1.py":
        "18d40dba5733efbfa633fff1d52372db49c63bcf315acb7f86acbdc64c89e386",
    PROJECT_ROOT / "scripts/rnatr_materialize_native_v041_to_evidence_v042_runid_adapter_v0.2.1.py":
        "7ba7f5082c9671be55b6b223c20f5bc8b933ad8b4658b1789187e043943949d4",
    PROJECT_ROOT / "scripts/rnatr_stage15a_fast_motif_jobs_scaling_v0.2.2.2.py":
        "3e36454a515cd8c0411957000099867b582ae7d2bef78b7fe2ebd61bf09f4dc4",
    PROJECT_ROOT / "scripts/rnatr_stage15a_extract_candidate_fastq_v0.1.0.py":
        "b4ecf4e5ecf1a1c0e57e96cb30f560a21230e1463777bdbb0e36601918a9abbf",
}

DOC_TEXT = f"""# RNA-TR-Scout Stage 15C — 144-shard execution architecture validation v0.1.1

## Amendment provenance

v0.1.1 supersedes the failed v0.1.0 execution attempt only at the orchestration-code level.
v0.1.0 stopped during host preflight before partitioning or scientific processing because
the Python standard-library module name `resource` was shadowed by a later local variable.
v0.1.1 aliases the module as `resource_module`, renames the local resource-model dictionary,
and writes to new versioned result/QC/metadata roots. No scientific parameter, shard design,
caller, materializer, schema, reference, validator semantics, or accepted prior result is changed.

## Purpose

Stage 15B established a memory-bounded final package validator, but that PASS
was validator-scoped. The frozen materializer v0.1.2 loads caller and output
rows into Python lists/dictionaries. Therefore, applying the 12-shard 500k
execution layout unchanged to the 5,312,696-read sample could create an unsafe
caller/materializer concurrency peak even though the validator is now bounded.

This stage validates a resource-bounded execution-only change:

- scientific caller: unchanged v0.4.1
- materializer: unchanged v0.1.2
- core schema: unchanged v0.4.2
- read-coherent partitioning: SHA-256(read_id) modulo shard count
- candidate architecture: {SHARD_COUNT} shards
- maximum concurrent shard pipelines: {STAGE_CONCURRENCY}
- caller workers per active shard: {CALLER_WORKERS_PER_SHARD}
- memory-bounded validator workers: {VALIDATOR_WORKERS}

The existing deterministic 500k input is rerun once. The 144-shard final core
files must be byte-identical and logically identical to the accepted 12-shard
replicate-A package. This establishes that shard count is an execution
parameter rather than a scientific parameter for the validated core scope.

The count 144 is deliberate: 5,312,696 / 144 is about 36,894 input reads per
full-scale shard, below the accepted 500,000 / 12 = 41,667 reads per shard.
The audit projects candidate-row imbalance from the accepted 500k data and
requires the planned full-scale maximum shard load to remain within the
observed accepted 12-shard 500k range. The provisional full runner must also
apply an empirical post-11b hard gate: before any caller/materializer starts,
it must stop if an observed full-scale shard exceeds the accepted per-shard
candidate-load bound. It must never silently continue with an unsafe shard.

## Scope and exclusions

This stage does not run the full 5.31M BAM-to-final analysis, switch the active
pipeline, update SSOT, modify schema/caller/materializer, run locus aggregation,
or claim cross-hardware release determinism. It produces a host-specific
resource model and either authorizes or blocks construction of the provisional
full runner.
"""

PLANNED_GATES_TEXT = """gate_id\trequirement\tcategory\tblocking_for_internal_beta\tstatus\tnext_action
G25\tAutomatic version-pinned reference bootstrap with resumable download and checksum verification; large references excluded from GitHub\trelease_readiness\ttrue\tOPEN_PLANNED\tImplement a reference manifest, downloader, cache, and setup command after Core Technical Completion performance gates
G26\tCPU, available RAM, output space, and temporary space detection before execution\trelease_readiness\ttrue\tOPEN_PLANNED\tExpose a resource-detection report in the release CLI and retain explicit override provenance
G27\tMemory-aware automatic selection of shard count and caller/materializer/validator concurrency with --threads --memory-gb --tmp-dir overrides\trelease_readiness\ttrue\tOPEN_PLANNED\tUse empirical per-stage resource models; never change scientific parameters silently
G28\tScientific logical output reproducibility across supported hardware and concurrency profiles for identical input/version/reference/parameters\trelease_readiness\ttrue\tOPEN_PLANNED\tRun cross-profile and cross-machine exact logical comparisons before release candidate
G29\tClean-machine clone-to-setup-to-test reproducibility without developer-local paths or hidden references\trelease_readiness\ttrue\tOPEN_PLANNED\tValidate in a clean VM/container or independent workstation before v0.5.0-rc1
G30\tEmpirical minimum recommended and tested hardware profiles documented in README\trelease_readiness\ttrue\tOPEN_PLANNED\tDerive CPU RAM and free-storage specifications from release-scale measurements
"""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def logical_sha256(path: Path) -> str:
    import gzip
    h = hashlib.sha256()
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def ensure_nonempty(path: Path) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"missing or empty file: {path}")


def read_metrics(path: Path) -> dict[str, str]:
    ensure_nonempty(path)
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        header = next(reader, None)
        if header != ["metric", "value"]:
            raise RuntimeError(f"unexpected metric header: {path}: {header}")
        return {row[0]: row[1] for row in reader if len(row) >= 2}


def read_dict_tsv(path: Path) -> list[dict[str, str]]:
    ensure_nonempty(path)
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise RuntimeError(f"missing TSV header: {path}")
        return list(reader)


def atomic_write_metrics(path: Path, rows: Iterable[tuple[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".part")
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["metric", "value"])
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def atomic_write_dict_tsv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        raise RuntimeError(f"refusing empty TSV: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".part")
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(rows[0]), delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def atomic_write_text(path: Path, text: str, mode: int = 0o644) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = text.encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    if path.exists():
        if not path.is_file() or sha256_file(path) != digest:
            raise RuntimeError(f"versioned destination exists with different bytes: {path}")
        path.chmod(mode)
        return "REUSED_EXACT"
    tmp = path.with_name("." + path.name + f".installing.{os.getpid()}")
    with tmp.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    tmp.chmod(mode)
    os.replace(tmp, path)
    return "INSTALLED_NEW"


def install_exact(source: Path, destination: Path, mode: int = 0o755) -> str:
    ensure_nonempty(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_sha = sha256_file(source)
    if destination.exists():
        if not destination.is_file() or sha256_file(destination) != source_sha:
            raise RuntimeError(f"versioned destination exists with different bytes: {destination}")
        destination.chmod(mode)
        return "REUSED_EXACT"
    tmp = destination.with_name("." + destination.name + f".installing.{os.getpid()}")
    shutil.copy2(source, tmp)
    tmp.chmod(mode)
    os.replace(tmp, destination)
    return "INSTALLED_NEW"


def import_file(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def memtotal_kb() -> int:
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        if line.startswith("MemTotal:"):
            return int(line.split()[1])
    raise RuntimeError("MemTotal unavailable")


def parse_time_v(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        text = raw.strip()
        if ":" not in text:
            continue
        key, value = text.rsplit(":", 1)
        values[key.strip()] = value.strip()
    return values


def verify_static_guards() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    exact_guards = dict(EXTRA_GUARDS)
    exact_guards.update(
        {
            PREFLIGHT_QC: PREFLIGHT_QC_SHA256,
            STAGE15B_QC: STAGE15B_QC_SHA256,
            STAGE15B_REFERENCE_VALIDATOR_TIMING: STAGE15B_REFERENCE_VALIDATOR_TIMING_SHA256,
            REFERENCE_COMBINED_QC: REFERENCE_COMBINED_QC_SHA256,
            REFERENCE_PACKAGE_MANIFEST: REFERENCE_PACKAGE_MANIFEST_SHA256,
        }
    )
    for path, expected in exact_guards.items():
        ensure_nonempty(path)
        observed = sha256_file(path)
        status = "PASS" if observed == expected else "FAIL"
        rows.append(
            {
                "path": str(path),
                "expected_sha256": expected,
                "observed_sha256": observed,
                "status": status,
            }
        )
        if status != "PASS":
            raise RuntimeError(f"guard mismatch: {path}: {observed} != {expected}")

    for path in (
        INPUT_QC,
        REFERENCE_CANDIDATE_COUNTS,
        REFERENCE_CALLER_TIMING,
        REFERENCE_MATERIALIZER_TIMING,
    ):
        ensure_nonempty(path)

    preflight = read_metrics(PREFLIGHT_QC)
    for key, expected in {
        "status": "PASS_READY_TO_BUILD_PROVISIONAL_FULLSCALE_RUNNER",
        "full_bam_bound": "true",
        "mapping_provenance_status": "PASS",
        "fastq_bam_exact_read_id_parity": "true",
        "stage15b_validator_equivalence": "PASS",
        "memory_readiness_status": "PASS",
        "storage_readiness_status": "PASS",
        "runner_build_authorized": "true",
        "full_empirical_run_authorized": "false",
        "full_5_31m_run_started": "false",
        "audit_status": "PASS",
    }.items():
        if preflight.get(key) != expected:
            raise RuntimeError(f"Stage15C input preflight mismatch {key}: {preflight.get(key)} != {expected}")

    stage15b = read_metrics(STAGE15B_QC)
    for key, expected in {
        "candidate_sha256": BOUNDED_VALIDATOR_SHA256,
        "positive_100k_accept_parity": "PASS",
        "positive_500k_accept_parity": "PASS",
        "negative_fixture_accept_reject_parity": "PASS",
        "negative_fixture_count": "10",
        "validator_equivalence_status": "PASS",
        "package_manifest_integrity_500k": "PASS",
        "active_pipeline_modified": "false",
        "ssot_modified": "false",
        "core_schema_modified": "false",
        "candidate_promoted_active": "false",
        "full_5_31m_run_started": "false",
        "audit_status": "PASS",
    }.items():
        if stage15b.get(key) != expected:
            raise RuntimeError(f"Stage15B gate mismatch {key}: {stage15b.get(key)} != {expected}")

    combined = read_metrics(REFERENCE_COMBINED_QC)
    for key, expected in {
        "formal_run_id_contract": "PASS",
        "input_reads": str(BENCHMARK_READS),
        "package_exact_logical_reproducibility": "true",
        "package_exact_raw_reproducibility": "true",
        "caller_hashseed_logical_reproducibility": "true",
        "checkpoint_logical_reproducibility": "true",
        "nested_250k_scientific_parity": "true",
        "deterministic_500k_scaling": "PASS",
        "active_pipeline_modified": "false",
        "ssot_modified": "false",
        "full_5_31m_run_started": "false",
        "audit_status": "PASS",
    }.items():
        if combined.get(key) != expected:
            raise RuntimeError(f"accepted 500k gate mismatch {key}: {combined.get(key)} != {expected}")

    reference_manifest_rows = read_dict_tsv(REFERENCE_PACKAGE_MANIFEST)
    expected_artifacts = {
        f"{table}{suffix}" for table in CORE_TABLES for suffix in (".tsv", ".tsv.gz")
    }
    if len(reference_manifest_rows) != 10:
        raise RuntimeError(f"reference 500k manifest rows != 10: {len(reference_manifest_rows)}")
    by_artifact = {row["artifact"]: row for row in reference_manifest_rows}
    if set(by_artifact) != expected_artifacts:
        raise RuntimeError("reference 500k package manifest artifact set mismatch")
    for artifact, record in by_artifact.items():
        path = REFERENCE_PACKAGE / artifact
        ensure_nonempty(path)
        observed_sha = sha256_file(path)
        status = (
            "PASS"
            if path.stat().st_size == int(record["bytes"])
            and observed_sha == record["sha256"]
            else "FAIL"
        )
        rows.append(
            {
                "path": str(path),
                "expected_sha256": record["sha256"],
                "observed_sha256": observed_sha,
                "status": status,
            }
        )
        if status != "PASS":
            raise RuntimeError(f"reference package manifest integrity mismatch: {path}")

    count_rows = read_dict_tsv(REFERENCE_CANDIDATE_COUNTS)
    if len(count_rows) != 12:
        raise RuntimeError(f"accepted 500k candidate-count shard rows != 12: {len(count_rows)}")
    if sum(int(row["candidate_rows"]) for row in count_rows) != 1_948_859:
        raise RuntimeError("accepted 500k candidate-row total mismatch")
    if sum(int(row["candidate_reads"]) for row in count_rows) != 396_549:
        raise RuntimeError("accepted 500k candidate-read total mismatch")
    count_shards = {row["shard"] for row in count_rows}

    for label, path in (
        ("caller", REFERENCE_CALLER_TIMING),
        ("materializer", REFERENCE_MATERIALIZER_TIMING),
        ("validator", STAGE15B_REFERENCE_VALIDATOR_TIMING),
    ):
        timing_rows = read_dict_tsv(path)
        if len(timing_rows) != 12:
            raise RuntimeError(f"accepted 500k {label} timing rows != 12")
        if {row["shard"] for row in timing_rows} != count_shards:
            raise RuntimeError(f"accepted 500k {label} timing shard set mismatch")
        if any(row.get("exit_code") != "0" for row in timing_rows):
            raise RuntimeError(f"accepted 500k {label} timing contains nonzero exit")
        if label == "validator" and any(row.get("status") != "PASS" for row in timing_rows):
            raise RuntimeError("accepted 500k validator timing contains non-PASS row")

    return rows

def configure_modules():
    scaling = import_file(SCALING_RUNNER, "rnatr_stage15a_scaling500_for_stage15c144")
    scaling.RESULT_BASE = RESULT_BASE
    scaling.QC_BASE = QC_BASE
    scaling.COMBINED_QC = QC_BASE / "stage15c_144shard_execution_architecture.qc.tsv"
    scaling.SHARDS = SHARD_COUNT
    scaling.CALLER_WORKERS_PER_SHARD = CALLER_WORKERS_PER_SHARD
    base = scaling.configure_base(REP_LABEL)
    base.STAGE_VERSION = VERSION
    base.PIGZ_THREADS_PER_TABLE = 4
    return scaling, base


def make_limited_parallel(base):
    def run_parallel_stage(label, shards, command_builder, env_builder=None):
        started = time.perf_counter()
        records: list[dict[str, object]] = []
        errors: list[BaseException] = []
        workers = min(STAGE_CONCURRENCY, len(shards))
        with cf.ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(
                    base.run_timed,
                    label,
                    shard,
                    command_builder(shard),
                    env_builder(shard) if env_builder else None,
                ): shard
                for shard in shards
            }
            for future in cf.as_completed(futures):
                try:
                    records.append(future.result())
                except BaseException as exc:
                    errors.append(exc)
        wall = time.perf_counter() - started
        records.sort(key=lambda row: str(row["shard"]))
        if records:
            atomic_write_dict_tsv(base.QC_ROOT / f"{label}.per_shard.tsv", records)
        if errors:
            raise RuntimeError("; ".join(str(error) for error in errors))
        print(f"{label}\tPASS\twall_seconds={wall:.3f}\tconcurrency={workers}")
        return wall, records
    return run_parallel_stage


def partition_inputs_limited(scaling, base, shards, input_fastq: Path) -> dict[str, object]:
    """Partition the accepted 500k input into 144 read-coherent shards.

    This is semantically identical to the accepted scaling runner partitioner,
    except that shard BAM quickchecks are capped at STAGE_CONCURRENCY rather
    than launching one samtools process per shard simultaneously.
    """
    started = time.perf_counter()
    writers = []
    read_sets: list[set[str]] = [set() for _ in shards]
    record_counts = [0] * len(shards)
    with scaling.pysam.AlignmentFile(str(base.BAM), "rb") as source:
        try:
            for shard in shards:
                shard.bam.parent.mkdir(parents=True, exist_ok=True)
                writers.append(
                    scaling.pysam.AlignmentFile(str(shard.bam), "wb", template=source)
                )
            for record in source.fetch(until_eof=True):
                read_id = record.query_name
                if not read_id:
                    raise RuntimeError("BAM record lacks query_name")
                index = base.shard_index(read_id, len(shards))
                writers[index].write(record)
                record_counts[index] += 1
                read_sets[index].add(read_id)
        finally:
            for writer in writers:
                writer.close()

    def quickcheck(shard):
        proc = subprocess.run(
            ["samtools", "quickcheck", "-v", str(shard.bam)],
            text=True,
            capture_output=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"shard BAM quickcheck failed: {shard.bam}: {proc.stderr.strip()}"
            )
        if Path(str(shard.bam) + ".bai").exists():
            raise RuntimeError(f"unexpected shard BAI: {shard.bam}.bai")

    with cf.ThreadPoolExecutor(
        max_workers=min(STAGE_CONCURRENCY, len(shards))
    ) as pool:
        list(pool.map(quickcheck, shards))

    raw_files = []
    gzip_handles = []
    fastq_counts = [0] * len(shards)
    fastq_ids: set[str] = set()
    try:
        for shard in shards:
            shard.full_fastq.parent.mkdir(parents=True, exist_ok=True)
            raw = shard.full_fastq.open("wb")
            raw_files.append(raw)
            gzip_handles.append(
                scaling.gzip.GzipFile(
                    filename="", mode="wb", fileobj=raw, compresslevel=0, mtime=0
                )
            )
        with scaling.pysam.FastxFile(str(input_fastq)) as source:
            for entry in source:
                if entry.name in fastq_ids:
                    raise RuntimeError(f"duplicate 500k FASTQ read ID: {entry.name}")
                fastq_ids.add(entry.name)
                if entry.quality is None:
                    raise RuntimeError(
                        f"500k FASTQ record lacks quality: {entry.name}"
                    )
                index = base.shard_index(entry.name, len(shards))
                header = f"@{entry.name}" + (
                    f" {entry.comment}" if entry.comment else ""
                )
                gzip_handles[index].write(
                    f"{header}\n{entry.sequence}\n+\n{entry.quality}\n".encode(
                        "utf-8"
                    )
                )
                fastq_counts[index] += 1
    finally:
        for handle in gzip_handles:
            handle.close()
        for raw in raw_files:
            raw.close()

    bam_ids = set().union(*read_sets)
    if len(bam_ids) != BENCHMARK_READS or sum(map(len, read_sets)) != BENCHMARK_READS:
        raise RuntimeError("partitioned BAM unique-read count mismatch")
    if fastq_ids != bam_ids or len(fastq_ids) != BENCHMARK_READS:
        raise RuntimeError(
            f"partitioned BAM/FASTQ ID mismatch bam={len(bam_ids)} "
            f"fastq={len(fastq_ids)}"
        )
    input_metrics = read_metrics(INPUT_QC)
    expected_records = int(input_metrics["bam_500k_alignment_records"])
    if sum(record_counts) != expected_records:
        raise RuntimeError(
            f"partitioned alignment record mismatch: {sum(record_counts)} "
            f"!= {expected_records}"
        )

    rows: list[dict[str, object]] = []
    for index, shard in enumerate(shards):
        shard.alignment_records = record_counts[index]
        shard.unique_reads = len(read_sets[index])
        shard.candidate_fastq_reads = 0
        atomic_write_metrics(
            shard.bam.parent / "run_manifest.tsv",
            [
                ("run_id", RUN_ID),
                ("run_id_contract", "FORMAL_EXTERNAL_RUN_ID_NO_COMPATIBILITY_ALIAS"),
                ("stage15a_shard", shard.name),
                ("source_bam", base.BAM),
                ("alignment_records", shard.alignment_records),
                ("unique_reads", shard.unique_reads),
                ("shard_bai_created", "false"),
            ],
        )
        rows.append(
            {
                "shard": shard.name,
                "alignment_records": shard.alignment_records,
                "unique_reads": shard.unique_reads,
                "full_fastq_reads": fastq_counts[index],
                "bam_bytes": shard.bam.stat().st_size,
                "full_fastq_bytes": shard.full_fastq.stat().st_size,
                "shard_bai_created": "false",
            }
        )
    atomic_write_dict_tsv(
        base.QC_ROOT / "stage15a_scaling_500k_shards.fast.tsv", rows
    )
    return {
        "stage": "partition_500k_bam_and_associated_raw_fastq_limited_quickcheck",
        "elapsed_seconds": time.perf_counter() - started,
        "alignment_records": sum(record_counts),
        "unique_reads": len(bam_ids),
        "full_fastq_reads": sum(fastq_counts),
        "quickcheck_concurrency": min(STAGE_CONCURRENCY, len(shards)),
    }


def run_motif_limited(base, shards):
    manifest = base.QC_ROOT / "stage15c_144shard_fast_motif_jobs.input.tsv"
    summary = base.QC_ROOT / "stage15c_144shard_fast_motif_jobs.per_shard.tsv"
    rows = [
        {
            "shard": shard.name,
            "projection_path": str(shard.projection_path),
            "jobs_path": str(shard.jobs_path),
            "qc_path": str(shard.motif_qc_path),
            "expected_rows": shard.candidate_rows,
            "expected_reads": shard.candidate_reads,
        }
        for shard in shards
    ]
    atomic_write_dict_tsv(manifest, rows)
    log = base.LOG_ROOT / "15C144_fast_shared_catalog_motif_jobs.log"
    timing = base.TIMING_ROOT / "15C144_fast_shared_catalog_motif_jobs.time_v.txt"
    log.parent.mkdir(parents=True, exist_ok=True)
    timing.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(base.FAST_MOTIF_BUILDER),
        "--analysis-regions", str(base.ANALYSIS_REGIONS),
        "--disease-regions", str(base.DISEASE_REGIONS),
        "--shard-manifest", str(manifest),
        "--summary", str(summary),
        "--workers", str(STAGE_CONCURRENCY),
    ]
    started = time.perf_counter()
    with log.open("w", encoding="utf-8") as handle:
        proc = subprocess.run(
            ["/usr/bin/time", "-v", "-o", str(timing), *command],
            stdout=handle,
            stderr=subprocess.STDOUT,
            text=True,
        )
    elapsed = time.perf_counter() - started
    if proc.returncode != 0:
        tail = "\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-60:])
        raise RuntimeError(f"limited motif job preparation failed; log={log}\n{tail}")
    values = parse_time_v(timing)
    return elapsed, {
        "stage": "15C144_fast_shared_catalog_motif_jobs",
        "shard": "ALL",
        "elapsed_seconds": elapsed,
        "exit_code": proc.returncode,
        "maximum_resident_set_kbytes": values.get("Maximum resident set size (kbytes)", "."),
        "log": str(log),
        "command": " ".join(command),
    }


def run_caller_materializer_limited(base, shards, hash_seed: str):
    started = time.perf_counter()

    def one(shard):
        caller = base.run_timed(
            "15C144_native_caller",
            shard,
            [
                sys.executable,
                str(base.PERF_CALLER),
                "--project-root", str(shard.project),
                "--run-id", RUN_ID,
                "--window-fastq", str(shard.window_fastq),
                "--outdir", str(shard.caller_outdir),
                "--workers", str(CALLER_WORKERS_PER_SHARD),
            ],
            env_extra={"PYTHONHASHSEED": hash_seed},
        )
        materializer = base.run_timed(
            "15C144_materializer",
            shard,
            [
                sys.executable,
                str(base.PERF_MATERIALIZER),
                "--project-root", str(shard.project),
                "--run-id", RUN_ID,
                "--calls", str(shard.calls_path),
                "--schema-dir", str(base.SCHEMA_DIR),
                "--outdir", str(shard.package_dir),
                "--sample-id", base.SAMPLE_ID,
            ],
            env_extra={"PYTHONHASHSEED": hash_seed},
        )
        return caller, materializer

    callers: list[dict[str, object]] = []
    materializers: list[dict[str, object]] = []
    with cf.ThreadPoolExecutor(max_workers=STAGE_CONCURRENCY) as pool:
        futures = {pool.submit(one, shard): shard.name for shard in shards}
        for future in cf.as_completed(futures):
            caller, materializer = future.result()
            callers.append(caller)
            materializers.append(materializer)
    wall = time.perf_counter() - started
    callers.sort(key=lambda row: str(row["shard"]))
    materializers.sort(key=lambda row: str(row["shard"]))
    atomic_write_dict_tsv(base.QC_ROOT / "15C144_native_caller.per_shard.tsv", callers)
    atomic_write_dict_tsv(base.QC_ROOT / "15C144_materializer.per_shard.tsv", materializers)
    max_materializer = max(float(row["elapsed_seconds"]) for row in materializers)
    atomic_write_metrics(
        base.QC_ROOT / "stage15c_144shard_caller_materializer.qc.tsv",
        [
            ("stage_version", VERSION),
            ("run_id", RUN_ID),
            ("hash_seed", hash_seed),
            ("pipeline_wall_seconds", wall),
            ("active_shard_concurrency", STAGE_CONCURRENCY),
            ("caller_workers_per_active_shard", CALLER_WORKERS_PER_SHARD),
            ("max_caller_shard_seconds", max(float(row["elapsed_seconds"]) for row in callers)),
            ("max_materializer_shard_seconds", max_materializer),
            ("shards", len(shards)),
            ("audit_status", "PASS"),
        ],
    )
    return wall, callers, materializers, max_materializer


def run_bounded_validator(base) -> tuple[float, dict[str, object]]:
    output = base.QC_ROOT / "memory_bounded_validator_prepublication"
    if output.exists():
        raise RuntimeError(f"validator output already exists: {output}")
    log = base.LOG_ROOT / "validators/memory_bounded_prepublication.log"
    time_log = base.TIMING_ROOT / "validators/memory_bounded_prepublication.time_v.txt"
    log.parent.mkdir(parents=True, exist_ok=True)
    time_log.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(BOUNDED_VALIDATOR),
        "--package-dir", str(base.PACKAGE_PART),
        "--shards-root", str(base.SHARDS_ROOT),
        "--schema-dir", str(base.SCHEMA_DIR),
        "--output-dir", str(output),
        "--workers", str(VALIDATOR_WORKERS),
        "--expected-shards", str(SHARD_COUNT),
        "--sort-buffer", VALIDATOR_SORT_BUFFER,
    ]
    started = time.perf_counter()
    with log.open("w", encoding="utf-8") as handle:
        proc = subprocess.run(
            ["/usr/bin/time", "-v", "-o", str(time_log), *command],
            stdout=handle,
            stderr=subprocess.STDOUT,
            text=True,
        )
    elapsed = time.perf_counter() - started
    if proc.returncode != 0:
        tail = "\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-80:])
        raise RuntimeError(f"memory-bounded validator failed; log={log}\n{tail}")
    text = log.read_text(encoding="utf-8", errors="replace")
    if "RNATR_STAGE15B_SHARDED_MEMORY_BOUNDED_PACKAGE_VALIDATION_PASS" not in text:
        raise RuntimeError("memory-bounded validator PASS marker absent")
    values = parse_time_v(time_log)
    record = {
        "stage": "15C144_memory_bounded_validator",
        "shard": "ALL",
        "elapsed_seconds": elapsed,
        "exit_code": proc.returncode,
        "maximum_resident_set_kbytes": values.get("Maximum resident set size (kbytes)", "."),
        "log": str(log),
        "command": " ".join(command),
        "validator_output": str(output),
        "status": "PASS",
    }
    atomic_write_dict_tsv(base.QC_ROOT / "stage15c_144shard_validator.tsv", [record])
    return elapsed, record


def compare_core_package(candidate: Path, reference: Path, out_path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for table in CORE_TABLES:
        for suffix in (".tsv", ".tsv.gz"):
            cand = candidate / f"{table}{suffix}"
            ref = reference / f"{table}{suffix}"
            ensure_nonempty(cand)
            ensure_nonempty(ref)
            cand_raw = sha256_file(cand)
            ref_raw = sha256_file(ref)
            cand_logical = logical_sha256(cand)
            ref_logical = logical_sha256(ref)
            raw_equal = cand_raw == ref_raw
            logical_equal = cand_logical == ref_logical
            status = "PASS" if raw_equal and logical_equal else "FAIL"
            rows.append({
                "artifact": cand.name,
                "candidate_bytes": cand.stat().st_size,
                "reference_bytes": ref.stat().st_size,
                "candidate_raw_sha256": cand_raw,
                "reference_raw_sha256": ref_raw,
                "raw_equal": str(raw_equal).lower(),
                "candidate_logical_sha256": cand_logical,
                "reference_logical_sha256": ref_logical,
                "logical_equal": str(logical_equal).lower(),
                "status": status,
            })
    atomic_write_dict_tsv(out_path, rows)
    failures = [row["artifact"] for row in rows if row["status"] != "PASS"]
    if failures:
        raise RuntimeError("144-shard core package differs from 12-shard reference: " + ",".join(map(str, failures)))
    return rows


def verify_package_manifest(package: Path, out_path: Path) -> tuple[float, list[dict[str, object]]]:
    started = time.perf_counter()
    manifest_path = package / "package_manifest.tsv"
    rows = read_dict_tsv(manifest_path)
    expected = {f"{table}{suffix}" for table in CORE_TABLES for suffix in (".tsv", ".tsv.gz")}
    by_artifact = {row["artifact"]: row for row in rows}
    if set(by_artifact) != expected:
        raise RuntimeError("package manifest artifact set mismatch")
    audit: list[dict[str, object]] = []
    for artifact in sorted(expected):
        path = package / artifact
        record = by_artifact[artifact]
        ensure_nonempty(path)
        observed = sha256_file(path)
        status = (
            "PASS"
            if path.stat().st_size == int(record["bytes"]) and observed == record["sha256"]
            else "FAIL"
        )
        audit.append({
            "artifact": artifact,
            "manifest_bytes": record["bytes"],
            "observed_bytes": path.stat().st_size,
            "manifest_sha256": record["sha256"],
            "observed_sha256": observed,
            "status": status,
        })
        if status != "PASS":
            raise RuntimeError(f"package manifest integrity failed: {artifact}")
    atomic_write_dict_tsv(out_path, audit)
    return time.perf_counter() - started, audit


def fit_linear(points: list[tuple[float, float]]) -> dict[str, float]:
    if len(points) < 2:
        raise RuntimeError("not enough points for linear fit")
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    xbar = sum(xs) / len(xs)
    ybar = sum(ys) / len(ys)
    denom = sum((x - xbar) ** 2 for x in xs)
    slope = sum((x - xbar) * (y - ybar) for x, y in points) / denom if denom else 0.0
    if slope < 0:
        slope = 0.0
    intercept = max(0.0, ybar - slope * xbar)
    predicted = [intercept + slope * x for x in xs]
    ss_res = sum((y - p) ** 2 for y, p in zip(ys, predicted))
    ss_tot = sum((y - ybar) ** 2 for y in ys)
    r2 = 1.0 - ss_res / ss_tot if ss_tot else 1.0
    max_positive_residual = max((y - p for y, p in zip(ys, predicted)), default=0.0)
    max_y = max(ys)
    min_y = min(ys)
    dynamic_fraction = (slope * (max(xs) - min(xs)) / max_y) if max_y else 0.0
    observed_range_fraction = ((max_y - min_y) / max_y) if max_y else 0.0
    return {
        "intercept": intercept,
        "slope": slope,
        "r2": r2,
        "max_positive_residual": max(0.0, max_positive_residual),
        "dynamic_fraction": dynamic_fraction,
        "observed_range_fraction": observed_range_fraction,
    }


def timing_points(candidate_counts_path: Path, timing_path: Path) -> list[tuple[float, float]]:
    counts = {row["shard"]: int(row["candidate_rows"]) for row in read_dict_tsv(candidate_counts_path)}
    rows = read_dict_tsv(timing_path)
    points = []
    for row in rows:
        shard = row["shard"]
        if shard not in counts:
            raise RuntimeError(f"timing shard missing candidate count: {shard}")
        rss = int(row["maximum_resident_set_kbytes"])
        points.append((float(counts[shard]), float(rss)))
    return points


def build_resource_model(base, caller_records, materializer_records, validator_record, production_seconds):
    new_counts_path = base.QC_ROOT / "stage15a_scaling_500k_11b_counts.tsv"
    new_counts = read_dict_tsv(new_counts_path)
    total_candidate_rows = sum(int(row["candidate_rows"]) for row in new_counts)
    max_candidate_rows = max(int(row["candidate_rows"]) for row in new_counts)
    projected_total = total_candidate_rows * FULL_READS / BENCHMARK_READS
    # Preserve the observed 144-shard imbalance and add a separate 5% reserve.
    projected_max_shard_rows = max_candidate_rows * FULL_READS / BENCHMARK_READS * 1.05
    reference_count_rows = read_dict_tsv(REFERENCE_CANDIDATE_COUNTS)
    reference_max_candidate_rows = max(
        int(row["candidate_rows"]) for row in reference_count_rows
    )
    reference_mean_candidate_rows = (
        sum(int(row["candidate_rows"]) for row in reference_count_rows)
        / len(reference_count_rows)
    )
    projected_shard_load_ratio = (
        projected_max_shard_rows / reference_max_candidate_rows
    )
    projected_shard_load_status = (
        "PASS"
        if projected_max_shard_rows <= reference_max_candidate_rows
        else "BLOCKED_PROJECTED_FULL_SHARD_EXCEEDS_ACCEPTED_500K_SHARD"
    )

    caller_new_path = base.QC_ROOT / "15C144_native_caller.per_shard.tsv"
    materializer_new_path = base.QC_ROOT / "15C144_materializer.per_shard.tsv"
    validator_output = Path(str(validator_record["validator_output"]))
    validator_new_path = validator_output / "shard_frozen_v042_validation.tsv"

    caller_points = (
        timing_points(REFERENCE_CANDIDATE_COUNTS, REFERENCE_CALLER_TIMING)
        + timing_points(new_counts_path, caller_new_path)
    )
    materializer_points = (
        timing_points(REFERENCE_CANDIDATE_COUNTS, REFERENCE_MATERIALIZER_TIMING)
        + timing_points(new_counts_path, materializer_new_path)
    )
    validator_points = (
        timing_points(REFERENCE_CANDIDATE_COUNTS, STAGE15B_REFERENCE_VALIDATOR_TIMING)
        + timing_points(new_counts_path, validator_new_path)
    )

    caller_fit = fit_linear(caller_points)
    materializer_fit = fit_linear(materializer_points)
    validator_fit = fit_linear(validator_points)

    def project_stage(fit: dict[str, float], current_records: list[dict[str, str]] | list[dict[str, object]]):
        current_rss = [int(row["maximum_resident_set_kbytes"]) for row in current_records]
        max_current_rss = max(current_rss)
        fitted_raw = (
            fit["intercept"]
            + fit["slope"] * projected_max_shard_rows
            + FIT_RESIDUAL_MULTIPLIER * fit["max_positive_residual"]
        )
        fitted_with_safety = max(fitted_raw, float(max_current_rss)) * MEMORY_SAFETY_FACTOR
        # A deliberately crude sensitivity bound is retained for audit only. It
        # scales the entire current process RSS, including fixed Python/runtime
        # overhead, and therefore must not silently replace the empirical
        # two-scale fit used for the execution decision.
        naive_proportional = (
            max_current_rss * FULL_READS / BENCHMARK_READS * MEMORY_SAFETY_FACTOR
        )
        if fit["r2"] >= FIT_R2_MINIMUM:
            fit_status = "PASS_LINEAR_FIT"
        elif (
            fit["dynamic_fraction"] <= FIT_STABLE_DYNAMIC_FRACTION_MAXIMUM
            and fit["observed_range_fraction"] <= FIT_STABLE_OBSERVED_RANGE_FRACTION_MAXIMUM
        ):
            fit_status = "PASS_STABLE_FIXED_OVERHEAD"
        else:
            fit_status = "REVIEW_WEAK_FIT"
        return {
            "fitted_with_safety_kb": fitted_with_safety,
            "naive_proportional_sensitivity_kb": naive_proportional,
            "fit_status": fit_status,
            "max_current_rss_kb": max_current_rss,
        }

    validator_new_rows = read_dict_tsv(validator_new_path)
    caller_projection = project_stage(caller_fit, caller_records)
    materializer_projection = project_stage(materializer_fit, materializer_records)
    validator_projection = project_stage(validator_fit, validator_new_rows)

    host_kb = memtotal_kb()
    caller_peak = (
        caller_projection["fitted_with_safety_kb"] * STAGE_CONCURRENCY
        + SYSTEM_RESERVE_KB
    )
    materializer_peak = (
        materializer_projection["fitted_with_safety_kb"] * STAGE_CONCURRENCY
        + SYSTEM_RESERVE_KB
    )
    validator_peak = (
        validator_projection["fitted_with_safety_kb"] * VALIDATOR_WORKERS
        + SYSTEM_RESERVE_KB
    )
    projected_peak = max(caller_peak, materializer_peak, validator_peak)
    fraction = projected_peak / host_kb

    naive_caller_peak = (
        caller_projection["naive_proportional_sensitivity_kb"] * STAGE_CONCURRENCY
        + SYSTEM_RESERVE_KB
    )
    naive_materializer_peak = (
        materializer_projection["naive_proportional_sensitivity_kb"] * STAGE_CONCURRENCY
        + SYSTEM_RESERVE_KB
    )
    naive_validator_peak = (
        validator_projection["naive_proportional_sensitivity_kb"] * VALIDATOR_WORKERS
        + SYSTEM_RESERVE_KB
    )
    naive_peak = max(naive_caller_peak, naive_materializer_peak, naive_validator_peak)
    naive_fraction = naive_peak / host_kb

    fit_statuses = {
        "caller": caller_projection["fit_status"],
        "materializer": materializer_projection["fit_status"],
        "validator": validator_projection["fit_status"],
    }
    model_fit_status = (
        "PASS_EMPIRICAL_12_AND_144_SHARD_FIT"
        if all(value.startswith("PASS_") for value in fit_statuses.values())
        else "REVIEW_WEAK_STAGE_FIT"
    )
    if projected_shard_load_status != "PASS":
        memory_status = "BLOCKED_PROJECTED_SHARD_LOAD_EXCEEDS_REFERENCE"
    elif model_fit_status != "PASS_EMPIRICAL_12_AND_144_SHARD_FIT":
        memory_status = "REVIEW_MODEL_FIT_REQUIRED"
    elif fraction <= MEMORY_FRACTION_LIMIT:
        memory_status = "PASS"
    else:
        memory_status = "BLOCKED_PROJECTED_PEAK_EXCEEDS_LIMIT"

    sensitivity_status = (
        "NAIVE_FIXED_OVERHEAD_SCALING_WITHIN_HOST"
        if naive_fraction <= 1.0
        else "NAIVE_FIXED_OVERHEAD_SCALING_EXCEEDS_HOST_NOT_DECISION_MODEL"
    )

    direct_runtime_minutes = production_seconds * FULL_READS / BENCHMARK_READS / 60.0
    stage15b_metrics = read_metrics(STAGE15B_QC)
    base_full_projection_minutes = float(
        stage15b_metrics["projected_full_bam_to_final_minutes"]
    )
    base_500k_equivalent_seconds = (
        base_full_projection_minutes * 60.0 * BENCHMARK_READS / FULL_READS
    )
    execution_fixed_overhead_seconds = max(
        0.0, production_seconds - base_500k_equivalent_seconds
    )
    adjusted_runtime_minutes = (
        base_full_projection_minutes + execution_fixed_overhead_seconds / 60.0
    )
    runtime_status = (
        "PASS_STRICT_PROJECTION" if adjusted_runtime_minutes <= 60.0
        else "PASS_TOLERANCE_PROJECTION" if adjusted_runtime_minutes <= 62.0
        else "REVIEW_EMPIRICAL_FULL_REQUIRED"
    )

    validator_qc = read_metrics(validator_output / "memory_bounded_validator.qc.tsv")
    model_rows = [
        ("model_version", VERSION),
        ("decision_scope", "AUTHORIZE_PROVISIONAL_FULL_RUNNER_BUILD_NOT_FULL_EXECUTION"),
        ("benchmark_reads", BENCHMARK_READS),
        ("full_reads", FULL_READS),
        ("accepted_500k_reference_shards", 12),
        ("accepted_500k_mean_input_reads_per_shard", f"{BENCHMARK_READS / 12:.3f}"),
        ("planned_full_mean_input_reads_per_shard", f"{FULL_READS / SHARD_COUNT:.3f}"),
        ("planned_to_accepted_mean_input_read_ratio", f"{(FULL_READS / SHARD_COUNT) / (BENCHMARK_READS / 12):.6f}"),
        ("benchmark_shards", SHARD_COUNT),
        ("active_shard_concurrency", STAGE_CONCURRENCY),
        ("caller_workers_per_shard", CALLER_WORKERS_PER_SHARD),
        ("validator_workers", VALIDATOR_WORKERS),
        ("observed_total_candidate_rows_500k", total_candidate_rows),
        ("observed_max_candidate_rows_per_144shard_500k", max_candidate_rows),
        ("accepted_12shard_mean_candidate_rows", f"{reference_mean_candidate_rows:.3f}"),
        ("accepted_12shard_max_candidate_rows", reference_max_candidate_rows),
        ("projected_total_candidate_rows_full", f"{projected_total:.3f}"),
        ("projected_max_candidate_rows_per_144shard_full_with_imbalance", f"{projected_max_shard_rows:.3f}"),
        ("projected_to_accepted_max_candidate_row_ratio", f"{projected_shard_load_ratio:.6f}"),
        ("projected_shard_load_status", projected_shard_load_status),
        ("caller_rss_fit_intercept_kb", f"{caller_fit['intercept']:.3f}"),
        ("caller_rss_fit_slope_kb_per_candidate_row", f"{caller_fit['slope']:.9f}"),
        ("caller_rss_fit_r2", f"{caller_fit['r2']:.6f}"),
        ("caller_rss_fit_dynamic_fraction", f"{caller_fit['dynamic_fraction']:.6f}"),
        ("caller_rss_fit_observed_range_fraction", f"{caller_fit['observed_range_fraction']:.6f}"),
        ("caller_rss_fit_max_positive_residual_kb", f"{caller_fit['max_positive_residual']:.3f}"),
        ("caller_rss_fit_status", caller_projection["fit_status"]),
        ("materializer_rss_fit_intercept_kb", f"{materializer_fit['intercept']:.3f}"),
        ("materializer_rss_fit_slope_kb_per_candidate_row", f"{materializer_fit['slope']:.9f}"),
        ("materializer_rss_fit_r2", f"{materializer_fit['r2']:.6f}"),
        ("materializer_rss_fit_dynamic_fraction", f"{materializer_fit['dynamic_fraction']:.6f}"),
        ("materializer_rss_fit_observed_range_fraction", f"{materializer_fit['observed_range_fraction']:.6f}"),
        ("materializer_rss_fit_max_positive_residual_kb", f"{materializer_fit['max_positive_residual']:.3f}"),
        ("materializer_rss_fit_status", materializer_projection["fit_status"]),
        ("validator_rss_fit_intercept_kb", f"{validator_fit['intercept']:.3f}"),
        ("validator_rss_fit_slope_kb_per_candidate_row", f"{validator_fit['slope']:.9f}"),
        ("validator_rss_fit_r2", f"{validator_fit['r2']:.6f}"),
        ("validator_rss_fit_dynamic_fraction", f"{validator_fit['dynamic_fraction']:.6f}"),
        ("validator_rss_fit_observed_range_fraction", f"{validator_fit['observed_range_fraction']:.6f}"),
        ("validator_rss_fit_max_positive_residual_kb", f"{validator_fit['max_positive_residual']:.3f}"),
        ("validator_rss_fit_status", validator_projection["fit_status"]),
        ("fit_r2_minimum", FIT_R2_MINIMUM),
        ("fit_stable_dynamic_fraction_maximum", FIT_STABLE_DYNAMIC_FRACTION_MAXIMUM),
        ("fit_stable_observed_range_fraction_maximum", FIT_STABLE_OBSERVED_RANGE_FRACTION_MAXIMUM),
        ("fit_residual_multiplier", FIT_RESIDUAL_MULTIPLIER),
        ("memory_safety_factor", MEMORY_SAFETY_FACTOR),
        ("system_reserve_kb", SYSTEM_RESERVE_KB),
        ("model_fit_status", model_fit_status),
        ("projected_caller_per_shard_rss_kb", f"{caller_projection['fitted_with_safety_kb']:.3f}"),
        ("projected_materializer_per_shard_rss_kb", f"{materializer_projection['fitted_with_safety_kb']:.3f}"),
        ("projected_validator_per_shard_rss_kb", f"{validator_projection['fitted_with_safety_kb']:.3f}"),
        ("projected_caller_stage_peak_kb", f"{caller_peak:.3f}"),
        ("projected_materializer_stage_peak_kb", f"{materializer_peak:.3f}"),
        ("projected_validator_stage_peak_kb", f"{validator_peak:.3f}"),
        ("projected_overall_peak_kb", f"{projected_peak:.3f}"),
        ("host_memtotal_kb", host_kb),
        ("projected_memory_fraction", f"{fraction:.6f}"),
        ("memory_fraction_limit", MEMORY_FRACTION_LIMIT),
        ("memory_readiness_status", memory_status),
        ("naive_proportional_caller_stage_peak_kb", f"{naive_caller_peak:.3f}"),
        ("naive_proportional_materializer_stage_peak_kb", f"{naive_materializer_peak:.3f}"),
        ("naive_proportional_validator_stage_peak_kb", f"{naive_validator_peak:.3f}"),
        ("naive_proportional_overall_peak_kb", f"{naive_peak:.3f}"),
        ("naive_proportional_memory_fraction", f"{naive_fraction:.6f}"),
        ("naive_proportional_sensitivity_status", sensitivity_status),
        ("production_500k_seconds", f"{production_seconds:.9f}"),
        ("base_stage15b_full_projection_minutes", f"{base_full_projection_minutes:.9f}"),
        ("base_500k_equivalent_seconds", f"{base_500k_equivalent_seconds:.9f}"),
        ("execution_fixed_overhead_seconds", f"{execution_fixed_overhead_seconds:.9f}"),
        ("adjusted_full_projection_minutes", f"{adjusted_runtime_minutes:.9f}"),
        ("naive_direct_linear_full_projection_minutes", f"{direct_runtime_minutes:.9f}"),
        ("runtime_projection_status", runtime_status),
        ("validator_current_max_single_shard_rss_kb", validator_projection["max_current_rss_kb"]),
        ("validator_reported_equivalence_scope", validator_qc.get("equivalence_scope", ".")),
    ]
    path = base.QC_ROOT / "stage15c_144shard_fullscale_resource_model.tsv"
    atomic_write_metrics(path, model_rows)
    return {
        "memory_status": memory_status,
        "memory_fraction": fraction,
        "model_fit_status": model_fit_status,
        "sensitivity_status": sensitivity_status,
        "naive_memory_fraction": naive_fraction,
        "runtime_status": runtime_status,
        "runtime_minutes": adjusted_runtime_minutes,
        "naive_runtime_minutes": direct_runtime_minutes,
        "projected_shard_load_status": projected_shard_load_status,
        "projected_shard_load_ratio": projected_shard_load_ratio,
        "resource_model_path": path,
    }

def snapshot_bytes(base, shards, stage: str) -> dict[str, object]:
    paths: list[Path] = []
    paths.extend(shard.root for shard in shards)
    if base.PACKAGE_PART.exists():
        paths.append(base.PACKAGE_PART)
    if base.PACKAGE_FINAL.exists():
        paths.append(base.PACKAGE_FINAL)
    total = 0
    seen: set[tuple[int, int]] = set()
    for root in paths:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            stat = path.stat()
            key = (stat.st_dev, stat.st_ino)
            if key in seen:
                continue
            seen.add(key)
            total += stat.st_size
    return {"stage": stage, "temporary_and_output_bytes": total}


def max_rss(records: list[dict[str, object]]) -> int:
    values = []
    for row in records:
        value = str(row.get("maximum_resident_set_kbytes", "."))
        if value.isdigit():
            values.append(int(value))
    return max(values) if values else 0


def verify_unchanged(base, active_before: dict[Path, str]) -> None:
    base.verify_active_unchanged(active_before)
    base.verify_ssot_unchanged()


def artifact_manifest(paths: list[Path], output: Path) -> None:
    rows = []
    for path in sorted({p.resolve() for p in paths if p.is_file()}, key=str):
        rows.append({
            "artifact": path.name,
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "path": str(path),
        })
    atomic_write_dict_tsv(output, rows)


def pack_bundle(bundle: Path, success: bool) -> None:
    tmp_root = Path(os.environ.get("TMPDIR", "/tmp")) / f"rnatr_stage15c144_bundle_{os.getpid()}"
    if tmp_root.exists():
        shutil.rmtree(tmp_root)
    package = tmp_root / ("rnatr_stage15c_144shard_execution_architecture_v0.1.1" if success else "rnatr_stage15c_144shard_execution_architecture_v0.1.1_failure")
    for sub in ("qc", "docs", "sources", "metadata", "logs"):
        (package / sub).mkdir(parents=True, exist_ok=True)
    if QC_BASE.exists():
        selected_names = {
            "stage15c_144shard_execution_architecture.qc.tsv",
            "stage15c_144shard_execution_architecture.failure.qc.tsv",
            "stage15c_144shard_fullscale_resource_model.tsv",
            "stage15c_144shard_core_package_parity.tsv",
            "stage15c_144shard_package_manifest_integrity.tsv",
            "stage15c_144shard_stage_timing.tsv",
            "stage15c_144shard_temp_bytes.tsv",
            "stage15c_144shard_validator.tsv",
            "static_source_guards.tsv",
            "stage15a_scaling_500k_shards.fast.tsv",
            "stage15a_scaling_500k_11b_counts.tsv",
            "stage15a_scaling_500k_candidate_fastq_counts.tsv",
            "stage15a_scaling_500k_projection_job_counts.tsv",
            "stage15a_scaling_500k_dynamic_expected_rows.tsv",
            "15C144_native_caller.per_shard.tsv",
            "15C144_materializer.per_shard.tsv",
            "stage15c_144shard_caller_materializer.qc.tsv",
            "stage15c_144shard_fast_motif_jobs.input.tsv",
            "stage15c_144shard_fast_motif_jobs.per_shard.tsv",
            "15C144_fast_shared_catalog_motif_jobs.tsv",
            "active_guards_before.tsv",
            "active_guards_after.tsv",
            "ssot_guards_after.tsv",
            "failure_traceback.log",
        }
        for path in QC_BASE.rglob("*"):
            if path.is_file() and path.name in selected_names:
                rel = path.relative_to(QC_BASE)
                dest = package / "qc" / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, dest)
        validator_root = QC_ROOT / "memory_bounded_validator_prepublication"
        if validator_root.is_dir():
            for name in (
                "memory_bounded_validator.qc.tsv",
                "shard_frozen_v042_validation.tsv",
                "global_id_uniqueness.tsv",
                "final_shard_row_parity.tsv",
                "frozen_source_guards.tsv",
            ):
                path = validator_root / name
                if path.is_file():
                    shutil.copy2(path, package / "qc" / f"validator_{name}")
    for path, sub in (
        (DOC_PATH, "docs"),
        (PLANNED_GATES_PATH, "docs"),
        (SCRIPT_INSTALL, "sources"),
    ):
        if path.is_file():
            shutil.copy2(path, package / sub / path.name)
    if META_ROOT.is_dir():
        for path in META_ROOT.rglob("*"):
            if path.is_file():
                shutil.copy2(path, package / "metadata" / path.name)
    files = [p for p in package.rglob("*") if p.is_file()]
    manifest_rows = [
        {
            "path": str(p.relative_to(package)),
            "bytes": p.stat().st_size,
            "sha256": sha256_file(p),
        }
        for p in sorted(files)
    ]
    atomic_write_dict_tsv(package / "artifact_manifest.tsv", manifest_rows)
    bundle.parent.mkdir(parents=True, exist_ok=True)
    if bundle.exists():
        raise RuntimeError(f"refusing to overwrite bundle: {bundle}")
    with tarfile.open(bundle, "w:gz", format=tarfile.PAX_FORMAT) as tar:
        tar.add(package, arcname=package.name)
    bundle.with_suffix(bundle.suffix + ".sha256").write_text(
        f"{sha256_file(bundle)}  {bundle.name}\n", encoding="utf-8"
    )
    shutil.rmtree(tmp_root)


def run_audit() -> bool:
    if RESULT_BASE.exists() or QC_BASE.exists():
        raise RuntimeError(
            "144-shard audit root already exists; preserve it and review rather than overwrite: "
            f"{RESULT_BASE}"
        )
    free_before = shutil.disk_usage(PROJECT_ROOT).free
    if free_before < MIN_FREE_BYTES_BEFORE_AUDIT:
        raise RuntimeError(
            f"Intel SSD free space below {MIN_FREE_BYTES_BEFORE_AUDIT}: {free_before}"
        )
    if (os.cpu_count() or 1) < 24:
        raise RuntimeError(f"fewer than 24 logical CPUs available: {os.cpu_count()}")
    nofile_soft, nofile_hard = resource_module.getrlimit(resource_module.RLIMIT_NOFILE)
    if nofile_soft < MIN_NOFILE_SOFT:
        raise RuntimeError(
            f"open-file soft limit below {MIN_NOFILE_SOFT}: soft={nofile_soft} hard={nofile_hard}"
        )

    QC_BASE.mkdir(parents=True, exist_ok=False)
    META_ROOT.mkdir(parents=True, exist_ok=True)
    static_rows = verify_static_guards()
    atomic_write_dict_tsv(QC_BASE / "static_source_guards.tsv", static_rows)

    scaling, base = configure_modules()
    active_before = scaling.verify_evidence_gate(base)
    atomic_write_dict_tsv(
        base.CONTRACT_ROOT / "active_guards_before.tsv",
        [{"path": str(path), "sha256": digest, "status": "PASS"} for path, digest in active_before.items()],
    )
    base.run_parallel_stage = make_limited_parallel(base)

    input_metrics = read_metrics(INPUT_QC)
    input_fastq = Path(input_metrics["subset_fastq"])
    ensure_nonempty(input_fastq)
    shards = scaling.create_shards(base)
    if len(shards) != SHARD_COUNT:
        raise RuntimeError(f"shard count construction mismatch: {len(shards)}")
    base.setup_shard_files(shards)

    timing_rows: list[dict[str, object]] = []
    temp_rows: list[dict[str, object]] = []
    stage_records: list[dict[str, object]] = []
    production_started = time.perf_counter()

    partition = partition_inputs_limited(scaling, base, shards, input_fastq)
    timing_rows.append({"stage": "15C144_partition_inputs", "elapsed_seconds": partition["elapsed_seconds"]})
    temp_rows.append(snapshot_bytes(base, shards, "after_partition"))

    wall_11b, rec_11b = base.run_parallel_stage(
        "15C144_11b",
        shards,
        lambda shard: ["bash", str(shard.script_11b)],
        lambda shard: {
            "EXPECTED_ALIGNMENT_RECORDS": str(shard.alignment_records),
            "EXPECTED_READS": str(shard.unique_reads),
        },
    )
    timing_rows.append({"stage": "15C144_11b", "elapsed_seconds": wall_11b})
    stage_records.extend(rec_11b)
    candidate_rows, candidate_reads = scaling.load_candidate_counts(base, shards)
    temp_rows.append(snapshot_bytes(base, shards, "after_11b"))

    wall_extract, rec_extract = scaling.extract_candidate_fastqs(base, shards)
    timing_rows.append({"stage": "15C144_extract_candidate_fastq", "elapsed_seconds": wall_extract})
    stage_records.extend(rec_extract)
    temp_rows.append(snapshot_bytes(base, shards, "after_candidate_fastq"))

    wall_11d3, rec_11d3 = base.run_parallel_stage(
        "15C144_11d3",
        shards,
        lambda shard: ["bash", str(shard.script_11d3)],
        lambda shard: {
            "EXPECTED_CANDIDATE_ROWS": str(shard.candidate_rows),
            "EXPECTED_CANDIDATE_READS": str(shard.candidate_reads),
        },
    )
    timing_rows.append({"stage": "15C144_11d3", "elapsed_seconds": wall_11d3})
    stage_records.extend(rec_11d3)
    temp_rows.append(snapshot_bytes(base, shards, "after_11d3"))

    wall_11e, rec_11e = run_motif_limited(base, shards)
    timing_rows.append({"stage": "15C144_fast_shared_catalog_motif_jobs", "elapsed_seconds": wall_11e})
    stage_records.append(rec_11e)
    atomic_write_dict_tsv(base.QC_ROOT / "15C144_fast_shared_catalog_motif_jobs.tsv", [rec_11e])
    projection_rows, projection_reads = scaling.load_projection_counts(base, shards)
    if projection_rows != candidate_rows or projection_reads != candidate_reads:
        raise RuntimeError("aggregate candidate/projection mismatch")
    temp_rows.append(snapshot_bytes(base, shards, "after_11e"))

    wall_cm, caller_records, materializer_records, max_materializer = run_caller_materializer_limited(
        base, shards, PYTHON_HASH_SEED
    )
    timing_rows.append({"stage": "15C144_caller_materializer_pipeline", "elapsed_seconds": wall_cm})
    stage_records.extend(caller_records)
    stage_records.extend(materializer_records)
    caller_totals = scaling.load_caller_totals(base, shards)
    expected_rows = scaling.derive_expected_final_rows(base, shards, caller_totals)
    temp_rows.append(snapshot_bytes(base, shards, "after_caller_materializer"))

    _, merge_plain, gzip_wall, _ = base.merge_packages(shards, materializer_wall=max_materializer)
    timing_rows.append({"stage": "15C144_global_merge", "elapsed_seconds": merge_plain})
    timing_rows.append({"stage": "15C144_global_gzip", "elapsed_seconds": gzip_wall})
    temp_rows.append(snapshot_bytes(base, shards, "after_merge_gzip"))

    validator_wall, validator_record = run_bounded_validator(base)
    timing_rows.append({"stage": "15C144_memory_bounded_validator", "elapsed_seconds": validator_wall})
    stage_records.append(validator_record)

    publish_wall, _ = base.publish_verified_package()
    timing_rows.append({"stage": "15C144_atomic_publication", "elapsed_seconds": publish_wall})
    production_seconds = time.perf_counter() - production_started
    temp_rows.append(snapshot_bytes(base, shards, "after_publication"))

    comparison_rows = compare_core_package(
        base.PACKAGE_FINAL,
        REFERENCE_PACKAGE,
        base.QC_ROOT / "stage15c_144shard_core_package_parity.tsv",
    )
    manifest_seconds, _ = verify_package_manifest(
        base.PACKAGE_FINAL,
        base.QC_ROOT / "stage15c_144shard_package_manifest_integrity.tsv",
    )
    verify_unchanged(base, active_before)

    atomic_write_dict_tsv(base.QC_ROOT / "stage15c_144shard_stage_timing.tsv", timing_rows)
    atomic_write_dict_tsv(base.QC_ROOT / "stage15c_144shard_temp_bytes.tsv", temp_rows)
    resource_model = build_resource_model(
        base, caller_records, materializer_records, validator_record, production_seconds
    )

    package_parity = all(row["status"] == "PASS" for row in comparison_rows)
    memory_pass = resource_model["memory_status"] == "PASS"
    shard_load_pass = resource_model["projected_shard_load_status"] == "PASS"
    build_authorized = package_parity and memory_pass and shard_load_pass
    free_after = shutil.disk_usage(PROJECT_ROOT).free
    if free_after < MIN_FREE_BYTES_AFTER_AUDIT:
        build_authorized = False
        storage_status = "BLOCKED"
    else:
        storage_status = "PASS"

    qc_rows = [
        ("stage_version", VERSION),
        ("source_run_id", RUN_ID),
        ("planned_full_run_id", PLANNED_FULL_RUN_ID),
        ("input_reads", BENCHMARK_READS),
        ("shard_count", SHARD_COUNT),
        ("stage_concurrency", STAGE_CONCURRENCY),
        ("caller_workers_per_shard", CALLER_WORKERS_PER_SHARD),
        ("validator_workers", VALIDATOR_WORKERS),
        ("python_hash_seed", PYTHON_HASH_SEED),
        ("open_file_soft_limit", nofile_soft),
        ("open_file_hard_limit", nofile_hard),
        ("alignment_records", partition["alignment_records"]),
        ("candidate_rows", candidate_rows),
        ("candidate_reads", candidate_reads),
        ("projection_rows", projection_rows),
        ("projection_reads", projection_reads),
        ("caller_attempt_rows", caller_totals["input_job_rows"]),
        ("caller_called_rows", caller_totals["called_rows"]),
        ("general_repeat_calls_rows", expected_rows["general_repeat_calls"]),
        ("read_evidence_rows", expected_rows["read_evidence"]),
        ("repeat_event_rows", expected_rows["repeat_events"]),
        ("repeat_segment_rows", expected_rows["repeat_segments"]),
        ("repeat_interruption_rows", expected_rows["repeat_interruptions"]),
        ("core_package_raw_and_logical_parity_to_12shard", str(package_parity).lower()),
        ("memory_bounded_validator", "PASS"),
        ("atomic_publication", "PASS"),
        ("package_manifest_integrity", "PASS"),
        ("package_manifest_integrity_seconds_post_timer", f"{manifest_seconds:.9f}"),
        ("bam_to_final_500k_seconds", f"{production_seconds:.9f}"),
        ("execution_architecture_adjusted_full_projection_minutes", f"{resource_model['runtime_minutes']:.9f}"),
        ("naive_direct_linear_full_projection_minutes", f"{resource_model['naive_runtime_minutes']:.9f}"),
        ("runtime_projection_status", resource_model["runtime_status"]),
        ("projected_shard_load_status", resource_model["projected_shard_load_status"]),
        ("projected_to_accepted_max_candidate_row_ratio", f"{resource_model['projected_shard_load_ratio']:.6f}"),
        ("maximum_observed_child_rss_kbytes", max_rss(stage_records)),
        ("peak_temporary_and_output_bytes", max(int(row["temporary_and_output_bytes"]) for row in temp_rows)),
        ("resource_model_fit_status", resource_model["model_fit_status"]),
        ("projected_full_memory_fraction", f"{resource_model['memory_fraction']:.6f}"),
        ("full_memory_readiness_status", resource_model["memory_status"]),
        ("naive_proportional_memory_fraction_sensitivity", f"{resource_model['naive_memory_fraction']:.6f}"),
        ("naive_proportional_sensitivity_status", resource_model["sensitivity_status"]),
        ("free_bytes_before", free_before),
        ("free_bytes_after", free_after),
        ("storage_status_after_audit", storage_status),
        ("scientific_output_independent_of_12_vs_144_shards", str(package_parity).lower()),
        ("cross_hardware_determinism", "NOT_RUN"),
        ("reference_bootstrap", "PLANNED_OPEN"),
        ("adaptive_hardware_policy", "PLANNED_OPEN"),
        ("full_post_11b_shard_load_hard_gate_required", "true"),
        ("active_pipeline_modified", "false"),
        ("ssot_modified", "false"),
        ("core_schema_modified", "false"),
        ("full_5_31m_run_started", "false"),
        ("provisional_full_runner_build_authorized", str(build_authorized).lower()),
        ("full_empirical_run_authorized", "false"),
        ("audit_status", "PASS" if build_authorized else "REVIEW"),
        ("next_gate", "BUILD_144SHARD_PROVISIONAL_FULL_RUNNER" if build_authorized else "REVIEW_RESOURCE_MODEL_BEFORE_FULL_RUNNER"),
    ]
    final_qc = QC_BASE / "stage15c_144shard_execution_architecture.qc.tsv"
    atomic_write_metrics(final_qc, qc_rows)

    contract_rows = [
        {"field": "contract_version", "value": VERSION, "status": "PROVISIONAL"},
        {"field": "planned_run_id", "value": PLANNED_FULL_RUN_ID, "status": "PROVISIONAL"},
        {"field": "read_coherent_shards", "value": SHARD_COUNT, "status": "VALIDATED_500K_EXACT_PARITY"},
        {"field": "active_shard_concurrency", "value": STAGE_CONCURRENCY, "status": resource_model["memory_status"]},
        {"field": "caller_workers_per_shard", "value": CALLER_WORKERS_PER_SHARD, "status": "VALIDATED_500K"},
        {"field": "validator_workers", "value": VALIDATOR_WORKERS, "status": "VALIDATED_500K"},
        {"field": "validator_sort_buffer", "value": VALIDATOR_SORT_BUFFER, "status": "VALIDATED_500K"},
        {"field": "scientific_output_12_vs_144_shards", "value": str(package_parity).lower(), "status": "PASS" if package_parity else "FAIL"},
        {"field": "projected_shard_load_status", "value": resource_model["projected_shard_load_status"], "status": "PASS" if resource_model["projected_shard_load_status"] == "PASS" else "BLOCKED"},
        {"field": "full_post_11b_shard_load_hard_gate_required", "value": "true", "status": "MANDATORY_FOR_FULL_RUNNER"},
        {"field": "resource_model_fit_status", "value": resource_model["model_fit_status"], "status": "PASS" if resource_model["model_fit_status"].startswith("PASS") else "REVIEW"},
        {"field": "projected_full_memory_fraction", "value": f"{resource_model['memory_fraction']:.6f}", "status": resource_model["memory_status"]},
        {"field": "naive_proportional_memory_fraction_sensitivity", "value": f"{resource_model['naive_memory_fraction']:.6f}", "status": resource_model["sensitivity_status"]},
        {"field": "runtime_projection_minutes", "value": f"{resource_model['runtime_minutes']:.9f}", "status": resource_model["runtime_status"]},
        {"field": "full_runner_build_authorized", "value": str(build_authorized).lower(), "status": "PASS" if build_authorized else "BLOCKED"},
        {"field": "full_empirical_run_authorized", "value": "false", "status": "NOT_BY_THIS_STAGE"},
    ]
    contract_path = META_ROOT / "fullscale_144shard_execution_contract_v0.1.1.tsv"
    atomic_write_dict_tsv(contract_path, contract_rows)
    artifact_manifest(
        [
            final_qc,
            resource_model["resource_model_path"],
            contract_path,
            DOC_PATH,
            PLANNED_GATES_PATH,
            SCRIPT_INSTALL,
        ],
        META_ROOT / "installation_and_evidence_manifest.tsv",
    )

    print("===== RNA-TR-Scout Stage 15C 144-shard architecture validation =====")
    for key, value in qc_rows:
        print(f"{key}\t{value}")
    if build_authorized:
        print("EXECUTION_ARCHITECTURE_DECISION	PASS_READY_TO_BUILD_144SHARD_PROVISIONAL_FULL_RUNNER")
    else:
        print("EXECUTION_ARCHITECTURE_DECISION	REVIEW_COMPLETED_FULL_RUNNER_BUILD_NOT_AUTHORIZED")
    # A resource-model REVIEW/BLOCK is a valid completed audit result, not a
    # technical script failure. Full execution remains prohibited either way.
    return build_authorized


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-run", action="store_true", help="install and static-check only; do not run the 500k audit")
    args = parser.parse_args()

    self_path = Path(__file__).resolve()
    install_status = install_exact(self_path, SCRIPT_INSTALL)
    doc_status = atomic_write_text(DOC_PATH, DOC_TEXT)
    gates_status = atomic_write_text(PLANNED_GATES_PATH, PLANNED_GATES_TEXT)
    static_compile = subprocess.run([sys.executable, "-m", "py_compile", str(SCRIPT_INSTALL)], text=True, capture_output=True)
    if static_compile.returncode != 0:
        raise SystemExit(static_compile.stderr)

    print("===== Stage 15C 144-shard execution architecture preflight =====")
    print("amendment\tv0.1.1 fixes v0.1.0 resource-module/local-variable name collision; scientific design unchanged")
    print(f"script_installation\t{install_status}")
    print(f"design_installation\t{doc_status}")
    print(f"release_readiness_gates_installation\t{gates_status}")
    print(f"shards\t{SHARD_COUNT}")
    print(f"active_shard_concurrency\t{STAGE_CONCURRENCY}")
    print(f"full_5_31m_run_started\tfalse")
    print(f"active_pipeline_modified\tfalse")
    print(f"ssot_modified\tfalse")

    if args.no_run:
        print("STATIC_INSTALL_PASS")
        return 0

    try:
        build_authorized = run_audit()
        pack_bundle(SUCCESS_BUNDLE, success=True)
        stage_status = (
            "PASS_READY_TO_BUILD_144SHARD_PROVISIONAL_FULL_RUNNER"
            if build_authorized
            else "REVIEW_COMPLETED_FULL_RUNNER_BUILD_NOT_AUTHORIZED"
        )
        print(f"STAGE15C_144SHARD_EXECUTION_ARCHITECTURE_STATUS\t{stage_status}")
        print(f"OUTPUT_BUNDLE\t{SUCCESS_BUNDLE}")
        print(f"OUTPUT_BUNDLE_SHA256\t{sha256_file(SUCCESS_BUNDLE)}")
        return 0
    except Exception as exc:
        QC_BASE.mkdir(parents=True, exist_ok=True)
        (QC_BASE / "failure_traceback.log").write_text(traceback.format_exc(), encoding="utf-8")
        atomic_write_metrics(
            QC_BASE / "stage15c_144shard_execution_architecture.failure.qc.tsv",
            [
                ("stage_version", VERSION),
                ("failure_type", type(exc).__name__),
                ("failure_message", str(exc)),
                ("active_pipeline_modified", "false"),
                ("ssot_modified", "false"),
                ("full_5_31m_run_started", "false"),
                ("audit_status", "FAIL"),
            ],
        )
        try:
            pack_bundle(FAILURE_BUNDLE, success=False)
            print(f"OUTPUT_FAILURE_BUNDLE\t{FAILURE_BUNDLE}", file=sys.stderr)
            print(f"OUTPUT_FAILURE_BUNDLE_SHA256\t{sha256_file(FAILURE_BUNDLE)}", file=sys.stderr)
        except Exception as pack_exc:
            print(f"failure bundle creation also failed: {pack_exc}", file=sys.stderr)
        print(f"STAGE15C_144SHARD_EXECUTION_ARCHITECTURE_STATUS\tFAIL\t{type(exc).__name__}\t{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
