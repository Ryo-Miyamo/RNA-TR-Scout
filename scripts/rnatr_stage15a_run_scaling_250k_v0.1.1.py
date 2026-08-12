from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import gzip
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Iterable

import pysam

VERSION = "rnatr_stage15a_deterministic_250k_scaling_v0.1.1"
PROJECT_ROOT = Path("/mnt/intelssd/rnatr_project")
INTERNAL_RUN_ID = "ENCSR307SHM_pilot100k_mm2splice_v1"
EXTERNAL_RUN_ID = "ENCSR307SHM_stage15a250k_seed20260808_mm2splice_v1"
INPUT_VERSION = "rnatr_stage15a_250k_input_v0.1.0"
INPUT_RESULT_ROOT = PROJECT_ROOT / "results/15_stage15a_inputs" / EXTERNAL_RUN_ID / INPUT_VERSION
INPUT_QC_ROOT = PROJECT_ROOT / "qc/15_stage15a_inputs" / EXTERNAL_RUN_ID / INPUT_VERSION
INPUT_QC = INPUT_QC_ROOT / "stage15a_250k_input.qc.tsv"
RESULT_BASE = (
    PROJECT_ROOT / "results/15_stage15a_bam_to_final" / EXTERNAL_RUN_ID
    / "v0.1.1_250k_scaling"
)
QC_BASE = (
    PROJECT_ROOT / "qc/15_stage15a_bam_to_final" / EXTERNAL_RUN_ID
    / "v0.1.1_250k_scaling"
)
COMBINED_QC = QC_BASE / "stage15a_scaling_250k.qc.tsv"
BASE_RUNNER = PROJECT_ROOT / "scripts/rnatr_stage15a_run_performance_100k_v0.2.2.1.py"
BASE_RUNNER_SHA256 = "7bfb7018cea80cd92854882751cffb49bea817296f69866801a64f9529c5e1a8"
CANDIDATE_EXTRACTOR = PROJECT_ROOT / "scripts/rnatr_stage15a_extract_candidate_fastq_v0.1.0.py"
CANDIDATE_EXTRACTOR_SHA256 = "b4ecf4e5ecf1a1c0e57e96cb30f560a21230e1463777bdbb0e36601918a9abbf"
SSOT_GUARDS = {
    PROJECT_ROOT / "metadata/ssot/rnatr_ssot.py": "6e558822fedb1704f4f774130b4bb164826cc61bc8a3d6eca78fec692d8a7658",
    PROJECT_ROOT / "metadata/ssot/rnatr_ssot.sqlite": "9fbbef951130ed2128703c1e7f369d0105226d5698fc8718ae12b1cadb63f17a",
}
LATEST_SSOT_UPDATE_QC = (
    PROJECT_ROOT / "qc/15_stage15a_ssot_update" / INTERNAL_RUN_ID
    / "restart_biology_v0.1.1/stage15a_restart_biology_ssot_update.qc.tsv"
)
LATEST_SSOT_UPDATE_QC_SHA256 = "aaea24017081207c7d48517d7e600220b7af632e7e7189546a55919fabccdee8"
RESTART_100K_QC = (
    PROJECT_ROOT / "qc/15_stage15a_bam_to_final" / INTERNAL_RUN_ID
    / "v0.2.3_restart_resume_100k/stage15a_restart_resume_100k.qc.tsv"
)
RESTART_100K_QC_SHA256 = "2882679389df77b3fe859e76a234f3bf2bd5cdbce6a8daace995fd31274c2f65"
V0221_QC = (
    PROJECT_ROOT / "qc/15_stage15a_bam_to_final" / INTERNAL_RUN_ID
    / "v0.2.2.1_performance/stage15a_performance_100k.qc.tsv"
)
V0221_QC_SHA256 = "401cfa9d9e524ceebfef9f6665d0f2b435627133c40cfcb6b8df7d989e4ac733"
V0221_TIMING = (
    PROJECT_ROOT / "qc/15_stage15a_bam_to_final" / INTERNAL_RUN_ID
    / "v0.2.2.1_performance/stage15a_performance_timing.tsv"
)
V0221_TIMING_SHA256 = "dbe46beaa7f555c4d7454c3fb95851d4ddd9b05df8a8ca2b56e00479c57b8b42"
REFERENCE_100K_PACKAGE = (
    PROJECT_ROOT / "results/15_stage15a_bam_to_final" / INTERNAL_RUN_ID
    / "v0.2.2.1_performance/package_performance"
)
FULL_READS = 5_312_696
BENCHMARK_READS = 250_000
BASELINE_100K_SECONDS = 65.76363927999046
SHARDS = 12
CALLER_WORKERS_PER_SHARD = 2
CURRENT_BASE = None
DYNAMIC_CONTEXT: dict[str, object] = {}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def ensure_file(path: Path) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise FileNotFoundError(path)


def read_metrics(path: Path) -> dict[str, str]:
    ensure_file(path)
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        header = next(reader, None)
        if header != ["metric", "value"]:
            raise RuntimeError(f"unexpected metric header: {path}: {header}")
        return {row[0]: row[1] for row in reader if len(row) >= 2}


def write_metrics(path: Path, rows: Iterable[tuple[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".part")
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["metric", "value"])
        writer.writerows(rows)
    os.replace(tmp, path)


def write_dict_tsv(path: Path, rows: list[dict[str, object]]) -> None:
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
    os.replace(tmp, path)


def import_base():
    ensure_file(BASE_RUNNER)
    if sha256_file(BASE_RUNNER) != BASE_RUNNER_SHA256:
        raise RuntimeError("base v0.2.2.1 runner SHA mismatch")
    spec = importlib.util.spec_from_file_location("rnatr_stage15a_v0221_base", BASE_RUNNER)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot import base runner")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def configure_base(rep: str):
    global CURRENT_BASE
    base = import_base()
    result_root = RESULT_BASE / f"replicate_{rep}"
    qc_root = QC_BASE / f"replicate_{rep}"
    base.STAGE_VERSION = f"{VERSION}_replicate_{rep}"
    base.RESULT_ROOT = result_root
    base.QC_ROOT = qc_root
    base.LOG_ROOT = qc_root / "logs"
    base.TIMING_ROOT = qc_root / "timing"
    base.COMPARISON_ROOT = qc_root / "comparison"
    base.CONTRACT_ROOT = qc_root / "contract"
    base.MARKER_ROOT = qc_root / "markers"
    base.SHARDS_ROOT = result_root / "shards"
    base.PACKAGE_PART = result_root / "package_performance.part"
    base.PACKAGE_FINAL = result_root / "package_performance"
    input_metrics = read_metrics(INPUT_QC)
    base.BAM = Path(input_metrics["bam_250k"])
    base.BAM_SHA256 = input_metrics["bam_250k_sha256"]
    base.SSOT_GUARDS = dict(SSOT_GUARDS)
    base.EXPECTED_FINAL_ROWS = {}
    base.FAST_MOTIF_BUILDER = Path('/mnt/intelssd/rnatr_project/scripts/rnatr_stage15a_fast_motif_jobs_scaling_v0.2.2.2.py')
    base.FAST_MOTIF_BUILDER_SHA256 = '3e36454a515cd8c0411957000099867b582ae7d2bef78b7fe2ebd61bf09f4dc4'
    base.aggregate_materializer_qc = aggregate_materializer_qc_dynamic
    base.run_generic_validator = run_generic_validator_dynamic
    base.run_package_validator_prepublication = run_package_validator_dynamic
    CURRENT_BASE = base
    return base


def verify_evidence_gate(base) -> dict[Path, str]:
    for path, expected in (
        (LATEST_SSOT_UPDATE_QC, LATEST_SSOT_UPDATE_QC_SHA256),
        (RESTART_100K_QC, RESTART_100K_QC_SHA256),
        (V0221_QC, V0221_QC_SHA256),
        (V0221_TIMING, V0221_TIMING_SHA256),
        (CANDIDATE_EXTRACTOR, CANDIDATE_EXTRACTOR_SHA256),
    ):
        ensure_file(path)
        observed = sha256_file(path)
        if observed != expected:
            raise RuntimeError(f"contract SHA mismatch: {path}: {observed} != {expected}")
    ssot_qc = read_metrics(LATEST_SSOT_UPDATE_QC)
    required_ssot = {
        "audit_status": "PASS",
        "active_pipeline_byte_identical": "true",
        "core_schema_modified": "false",
        "restart_resume_validated": "true",
        "deterministic_250k_scaling": "OPEN",
        "biology_ready_contract_registered": "true",
        "stage15a_overall_status": "IN_PROGRESS",
        "full_5_31m_run_started": "false",
        "next_gate": "BUILD_AND_RUN_DETERMINISTIC_250K_BAM_INPUT_SCALING_NOT_FULL_5_31M",
    }
    for key, expected in required_ssot.items():
        if ssot_qc.get(key) != expected:
            raise RuntimeError(f"latest SSOT gate mismatch {key}: {ssot_qc.get(key)}")
    restart = read_metrics(RESTART_100K_QC)
    if restart.get("audit_status") != "PASS" or restart.get("restart_resume_validated") != "true":
        raise RuntimeError("100k restart gate is not PASS")
    baseline = read_metrics(V0221_QC)
    baseline_required = {
        "audit_status": "PASS",
        "correctness_status": "PASS",
        "performance_implementation_status": "PASS",
        "package_exact_logical_parity": "true",
        "five_m_hard_ceiling_60min": "PASS",
        "full_5_31m_run_started": "false",
    }
    for key, expected in baseline_required.items():
        if baseline.get(key) != expected:
            raise RuntimeError(f"v0.2.2.1 baseline gate mismatch {key}: {baseline.get(key)}")
    input_metrics = read_metrics(INPUT_QC)
    input_required = {
        "audit_status": "PASS",
        "subset_fastq_rows": str(BENCHMARK_READS),
        "bam_250k_unique_reads": str(BENCHMARK_READS),
        "nested_100k_alignment_parity": "PASS",
        "mapping_included_in_bam_to_final_timer": "false",
        "active_pipeline_modified": "false",
        "ssot_modified": "false",
        "full_5_31m_run_started": "false",
    }
    for key, expected in input_required.items():
        if input_metrics.get(key) != expected:
            raise RuntimeError(f"250k input gate mismatch {key}: {input_metrics.get(key)}")
    for key in ("subset_fastq", "bam_250k", "bam_250k_bai"):
        path = Path(input_metrics[key])
        ensure_file(path)
        expected = input_metrics[f"{key}_sha256"]
        if sha256_file(path) != expected:
            raise RuntimeError(f"250k input artifact SHA mismatch: {path}")
    subprocess.run(["samtools", "quickcheck", "-v", input_metrics["bam_250k"]], check=True)
    for path, expected in SSOT_GUARDS.items():
        ensure_file(path)
        if sha256_file(path) != expected:
            raise RuntimeError(f"SSOT guard mismatch: {path}")
    for path, expected in base.SOURCE_SHA.items():
        ensure_file(path)
        if sha256_file(path) != expected:
            raise RuntimeError(f"source guard mismatch: {path}")
    component_guards = [
        (base.FROZEN_V03_VALIDATOR, base.FROZEN_V03_VALIDATOR_SHA256),
        (base.CALLER_SOURCE_DRIVER, base.CALLER_SOURCE_DRIVER_SHA256),
        (base.PERF_CALLER, base.PERF_CALLER_SHA256),
        (base.PERF_MATERIALIZER, base.PERF_MATERIALIZER_SHA256),
        (base.FAST_MOTIF_BUILDER, base.FAST_MOTIF_BUILDER_SHA256),
        (base.PARALLEL_PACKAGE_VALIDATOR, base.PARALLEL_PACKAGE_VALIDATOR_SHA256),
    ]
    for path, expected in component_guards:
        ensure_file(path)
        if sha256_file(path) != expected:
            raise RuntimeError(f"performance component guard mismatch: {path}")
    for path, expected in base.ACTIVE_GUARDS.items():
        ensure_file(path)
        if sha256_file(path) != expected:
            raise RuntimeError(f"active implementation guard mismatch: {path}")
    for path in (base.ANALYSIS_REGIONS, base.DISEASE_REGIONS):
        ensure_file(path)
    for table in base.TABLE_ORDER:
        for suffix in (".tsv", ".tsv.gz"):
            ensure_file(REFERENCE_100K_PACKAGE / f"{table}{suffix}")
    for executable in ("samtools", "pigz"):
        if shutil.which(executable) is None:
            raise RuntimeError(f"required executable not found: {executable}")
    if not Path("/usr/bin/time").is_file():
        raise RuntimeError("/usr/bin/time unavailable")
    usage = shutil.disk_usage(PROJECT_ROOT)
    if usage.free < 50 * 1024**3:
        raise RuntimeError(f"insufficient project free space for dual 250k runs: {usage.free}")
    return {path: sha256_file(path) for path in base.ACTIVE_GUARDS}


def create_shards(base):
    shards = base.create_shards(SHARDS)
    for shard in shards:
        full_fastq = (
            shard.raw_root / "benchmarks/ENCSR307SHM/pilot_100k_seed20260803"
            / "stage15a_250k_full/ENCFF260PGB.stage15a_250k.full.fastq.gz"
        )
        candidate_qc = shard.root / "qc/candidate_fastq_extraction.qc.tsv"
        window_fastq = (
            shard.raw_root / "benchmarks/ENCSR307SHM/pilot_100k_seed20260803"
            / "rnatr_projection_v0.3.3/ENCFF260PGB.pilot_100k.rnatr_target_windows.v0.3.3.fastq.gz"
        )
        setattr(shard, "full_fastq", full_fastq)
        setattr(shard, "candidate_qc", candidate_qc)
        setattr(shard, "window_fastq", window_fastq)
    return shards


def partition_inputs(base, shards, input_fastq: Path) -> dict[str, object]:
    started = time.perf_counter()
    writers: list[pysam.AlignmentFile] = []
    read_sets: list[set[str]] = [set() for _ in shards]
    record_counts = [0] * len(shards)
    with pysam.AlignmentFile(str(base.BAM), "rb") as source:
        try:
            for shard in shards:
                shard.bam.parent.mkdir(parents=True, exist_ok=True)
                writers.append(pysam.AlignmentFile(str(shard.bam), "wb", template=source))
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
    with cf.ThreadPoolExecutor(max_workers=len(shards)) as pool:
        futures = [
            pool.submit(
                subprocess.run,
                ["samtools", "quickcheck", "-v", str(shard.bam)],
                text=True,
                capture_output=True,
            )
            for shard in shards
        ]
        for shard, future in zip(shards, futures):
            proc = future.result()
            if proc.returncode != 0:
                raise RuntimeError(f"shard BAM quickcheck failed: {shard.bam}: {proc.stderr}")
            if Path(str(shard.bam) + ".bai").exists():
                raise RuntimeError(f"unexpected shard BAI: {shard.bam}.bai")

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
                gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=0, mtime=0)
            )
        with pysam.FastxFile(str(input_fastq)) as source:
            for entry in source:
                if entry.name in fastq_ids:
                    raise RuntimeError(f"duplicate 250k FASTQ read ID: {entry.name}")
                fastq_ids.add(entry.name)
                if entry.quality is None:
                    raise RuntimeError(f"250k FASTQ record lacks quality: {entry.name}")
                index = base.shard_index(entry.name, len(shards))
                header = f"@{entry.name}" + (f" {entry.comment}" if entry.comment else "")
                gzip_handles[index].write(
                    f"{header}\n{entry.sequence}\n+\n{entry.quality}\n".encode("utf-8")
                )
                fastq_counts[index] += 1
    finally:
        for handle in gzip_handles:
            handle.close()
        for raw in raw_files:
            raw.close()
    bam_ids = set().union(*read_sets)
    if len(bam_ids) != BENCHMARK_READS or sum(len(s) for s in read_sets) != BENCHMARK_READS:
        raise RuntimeError("partitioned BAM unique-read count mismatch")
    if fastq_ids != bam_ids or len(fastq_ids) != BENCHMARK_READS:
        raise RuntimeError(
            f"partitioned BAM/FASTQ ID mismatch bam={len(bam_ids)} fastq={len(fastq_ids)}"
        )
    input_metrics = read_metrics(INPUT_QC)
    expected_records = int(input_metrics["bam_250k_alignment_records"])
    if sum(record_counts) != expected_records:
        raise RuntimeError(
            f"partitioned alignment record mismatch: {sum(record_counts)} != {expected_records}"
        )
    rows = []
    for i, shard in enumerate(shards):
        shard.alignment_records = record_counts[i]
        shard.unique_reads = len(read_sets[i])
        shard.candidate_fastq_reads = 0
        run_manifest = shard.bam.parent / "run_manifest.tsv"
        write_metrics(
            run_manifest,
            [
                ("run_id", INTERNAL_RUN_ID),
                ("external_benchmark_run_id", EXTERNAL_RUN_ID),
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
                "full_fastq_reads": fastq_counts[i],
                "bam_bytes": shard.bam.stat().st_size,
                "full_fastq_bytes": shard.full_fastq.stat().st_size,
                "shard_bai_created": "false",
            }
        )
    write_dict_tsv(base.QC_ROOT / "stage15a_scaling_250k_shards.fast.tsv", rows)
    return {
        "stage": "partition_250k_bam_and_associated_raw_fastq",
        "elapsed_seconds": time.perf_counter() - started,
        "alignment_records": sum(record_counts),
        "unique_reads": len(bam_ids),
        "full_fastq_reads": sum(fastq_counts),
    }


def load_candidate_counts(base, shards) -> tuple[int, int]:
    rows = []
    total_rows = 0
    total_reads = 0
    for shard in shards:
        metrics = base.read_metrics(shard.assignment_qc_path)
        if metrics.get("audit_status") != "PASS":
            raise RuntimeError(f"11b QC not PASS: {shard.name}")
        shard.candidate_rows = int(metrics["read_target_candidates"])
        shard.candidate_reads = int(metrics["reads_with_any_candidate"])
        total_rows += shard.candidate_rows
        total_reads += shard.candidate_reads
        rows.append(
            {
                "shard": shard.name,
                "candidate_rows": shard.candidate_rows,
                "candidate_reads": shard.candidate_reads,
                "status": "PASS",
            }
        )
    write_dict_tsv(base.QC_ROOT / "stage15a_scaling_250k_11b_counts.tsv", rows)
    return total_rows, total_reads


def extract_candidate_fastqs(base, shards) -> tuple[float, list[dict[str, object]]]:
    wall, records = base.run_parallel_stage(
        "15AS1C_extract_candidate_fastq",
        shards,
        lambda shard: [
            sys.executable,
            str(CANDIDATE_EXTRACTOR),
            "--assignment", str(shard.assignment_path),
            "--input-fastq", str(shard.full_fastq),
            "--output-fastq", str(shard.candidate_fastq),
            "--qc", str(shard.candidate_qc),
            "--expected-rows", str(shard.candidate_rows),
            "--expected-reads", str(shard.candidate_reads),
        ],
    )
    rows = []
    for shard in shards:
        metrics = base.read_metrics(shard.candidate_qc)
        if metrics.get("audit_status") != "PASS":
            raise RuntimeError(f"candidate FASTQ extraction not PASS: {shard.name}")
        observed = int(metrics["candidate_fastq_records_written"])
        if observed != shard.candidate_reads:
            raise RuntimeError(f"candidate FASTQ count mismatch: {shard.name}")
        shard.candidate_fastq_reads = observed
        rows.append(
            {
                "shard": shard.name,
                "candidate_reads": shard.candidate_reads,
                "candidate_fastq_reads": observed,
                "candidate_fastq_bases": metrics["candidate_fastq_bases"],
                "status": "PASS",
            }
        )
    write_dict_tsv(base.QC_ROOT / "stage15a_scaling_250k_candidate_fastq_counts.tsv", rows)
    return wall, records


def load_projection_counts(base, shards) -> tuple[int, int]:
    rows = []
    total_rows = 0
    total_reads = 0
    for shard in shards:
        projection = base.read_metrics(shard.projection_qc_path)
        motif = base.read_metrics(shard.motif_qc_path)
        if projection.get("audit_status") != "PASS" or motif.get("audit_status") != "PASS":
            raise RuntimeError(f"11d3/11e QC not PASS: {shard.name}")
        shard.projection_rows = int(projection["projection_rows_written"])
        shard.projection_reads = int(projection["projection_unique_reads"])
        motif_rows = int(motif["observed_projection_rows"])
        motif_reads = int(motif["unique_projection_reads"])
        if (
            shard.projection_rows != shard.candidate_rows
            or shard.projection_reads != shard.candidate_reads
            or motif_rows != shard.projection_rows
            or motif_reads != shard.projection_reads
        ):
            raise RuntimeError(f"11d3/11e count mismatch: {shard.name}")
        total_rows += shard.projection_rows
        total_reads += shard.projection_reads
        rows.append(
            {
                "shard": shard.name,
                "projection_rows": shard.projection_rows,
                "projection_reads": shard.projection_reads,
                "motif_job_rows": motif_rows,
                "motif_job_reads": motif_reads,
                "status": "PASS",
            }
        )
    write_dict_tsv(base.QC_ROOT / "stage15a_scaling_250k_projection_job_counts.tsv", rows)
    return total_rows, total_reads


def run_caller_materializer(base, shards, hash_seed: str):
    started = time.perf_counter()

    def one(shard):
        env = {
            "PYTHONHASHSEED": hash_seed,
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
        }
        caller = base.run_timed(
            "15AS4_native_caller_no_legacy_audit",
            shard,
            [
                sys.executable,
                str(base.PERF_CALLER),
                "--project-root", str(shard.project),
                "--outdir", str(shard.caller_outdir),
                "--workers", str(CALLER_WORKERS_PER_SHARD),
            ],
            env,
        )
        materializer = base.run_timed(
            "15AS5_materializer_plain_shards",
            shard,
            [
                sys.executable,
                str(base.PERF_MATERIALIZER),
                "--project-root", str(shard.project),
                "--calls", str(shard.calls_path),
                "--schema-dir", str(base.SCHEMA_DIR),
                "--outdir", str(shard.package_dir),
                "--sample-id", base.SAMPLE_ID,
            ],
            env,
        )
        return caller, materializer

    callers = []
    materializers = []
    errors = []
    with cf.ThreadPoolExecutor(max_workers=len(shards)) as pool:
        futures = {pool.submit(one, shard): shard.name for shard in shards}
        for future in cf.as_completed(futures):
            try:
                caller, materializer = future.result()
                callers.append(caller)
                materializers.append(materializer)
            except BaseException as exc:
                errors.append(exc)
    if errors:
        raise RuntimeError("; ".join(str(error) for error in errors))
    wall = time.perf_counter() - started
    callers.sort(key=lambda row: str(row["shard"]))
    materializers.sort(key=lambda row: str(row["shard"]))
    write_dict_tsv(base.QC_ROOT / "15AS4_native_caller.per_shard.tsv", callers)
    write_dict_tsv(base.QC_ROOT / "15AS5_materializer.per_shard.tsv", materializers)
    max_materializer = max(float(row["elapsed_seconds"]) for row in materializers)
    write_metrics(
        base.QC_ROOT / "stage15a_scaling_250k_caller_materializer.qc.tsv",
        [
            ("stage_version", base.STAGE_VERSION),
            ("hash_seed", hash_seed),
            ("pipeline_wall_seconds", wall),
            ("max_caller_shard_seconds", max(float(row["elapsed_seconds"]) for row in callers)),
            ("max_materializer_shard_seconds", max_materializer),
            ("shards", len(shards)),
            ("audit_status", "PASS"),
        ],
    )
    return wall, callers, materializers, max_materializer


def load_caller_totals(base, shards) -> dict[str, int]:
    totals = {
        "input_job_rows": 0,
        "called_rows": 0,
        "caller_error_rows": 0,
        "called_prior_overlap_nonpositive_rows": 0,
    }
    rows = []
    for shard in shards:
        metrics = base.read_metrics(shard.caller_outdir / "general_repeat_integration.qc.tsv")
        if metrics.get("audit_status") != "PASS":
            raise RuntimeError(f"caller QC not PASS: {shard.name}")
        for key in totals:
            totals[key] += int(metrics[key])
        rows.append(
            {
                "shard": shard.name,
                **{key: metrics[key] for key in totals},
                "audit_status": "PASS",
            }
        )
    if totals["caller_error_rows"] != 0:
        raise RuntimeError(f"caller errors at 250k: {totals['caller_error_rows']}")
    write_dict_tsv(base.QC_ROOT / "stage15a_scaling_250k_caller_counts.tsv", rows)
    return totals


def derive_expected_final_rows(base, shards, caller_totals: dict[str, int]) -> dict[str, int]:
    metrics = [base.read_metrics(shard.package_dir / "materialization.qc.tsv") for shard in shards]
    if any(row.get("audit_status") != "PASS" for row in metrics):
        raise RuntimeError("materializer QC not PASS")
    if any(row.get("caller_suffix_lossless_sha_match") != "true" for row in metrics):
        raise RuntimeError("caller suffix lossless parity failed")
    def sum_int(key: str) -> int:
        return sum(int(row[key]) for row in metrics)
    expected = {
        "general_repeat_calls": sum_int("input_caller_attempt_rows"),
        "read_evidence": sum_int("evidence_rows"),
        "repeat_events": sum_int("repeat_event_rows"),
        "repeat_segments": sum_int("repeat_segment_rows"),
        "repeat_interruptions": sum_int("repeat_interruption_rows"),
    }
    if expected["general_repeat_calls"] != caller_totals["input_job_rows"]:
        raise RuntimeError("caller/materializer attempt mismatch")
    if expected["read_evidence"] != expected["general_repeat_calls"]:
        raise RuntimeError("evidence/general row mismatch")
    if sum_int("called_attempt_rows") != caller_totals["called_rows"]:
        raise RuntimeError("called-attempt materializer mismatch")
    base.EXPECTED_FINAL_ROWS = dict(expected)
    DYNAMIC_CONTEXT.clear()
    DYNAMIC_CONTEXT.update(
        {
            "caller_totals": dict(caller_totals),
            "expected_final_rows": dict(expected),
            "materializer_metrics": metrics,
        }
    )
    write_metrics(
        base.QC_ROOT / "stage15a_scaling_250k_dynamic_expected_rows.tsv",
        [(key, value) for key, value in expected.items()]
        + [("called_attempt_rows", caller_totals["called_rows"])],
    )
    return expected


def aggregate_materializer_qc_dynamic(shards, materializer_wall, merge_plain_wall, gzip_wall):
    base = CURRENT_BASE
    if base is None:
        raise RuntimeError("base runner not configured")
    metrics = [base.read_metrics(shard.package_dir / "materialization.qc.tsv") for shard in shards]
    expected_rows = dict(DYNAMIC_CONTEXT["expected_final_rows"])
    caller_totals = dict(DYNAMIC_CONTEXT["caller_totals"])
    def sum_int(key: str) -> int:
        return sum(int(row[key]) for row in metrics)
    def max_float(key: str) -> float:
        return max(float(row[key]) for row in metrics)
    checks = {
        "input_caller_attempt_rows": expected_rows["general_repeat_calls"],
        "projection_rows": expected_rows["general_repeat_calls"],
        "evidence_rows": expected_rows["read_evidence"],
        "left_flank_uniqueness_not_assessed_rows": expected_rows["read_evidence"],
        "right_flank_uniqueness_not_assessed_rows": expected_rows["read_evidence"],
        "called_attempt_rows": caller_totals["called_rows"],
        "repeat_event_rows": expected_rows["repeat_events"],
        "repeat_segment_rows": expected_rows["repeat_segments"],
        "repeat_interruption_rows": expected_rows["repeat_interruptions"],
        "multi_attempt_evidence_rows": 0,
        "multi_event_evidence_rows": 0,
        "discordance_origin_not_assessed_event_rows": expected_rows["repeat_events"],
        "discordance_origin_not_assessed_interruption_rows": expected_rows["repeat_interruptions"],
    }
    observed = {key: sum_int(key) for key in checks}
    for key, expected in checks.items():
        if observed[key] != expected:
            raise RuntimeError(f"aggregate materializer mismatch {key}: {observed[key]} != {expected}")
    if any(row.get("cluster_analysis_status") != "NOT_RUN" for row in metrics):
        raise RuntimeError("unexpected cluster analysis status")
    rows = [
        ("stage_version", "rnatr_native_v041_to_evidence_v042_materializer_v0.1.2"),
        ("schema_version", "0.4.2"),
    ]
    rows.extend((key, observed[key]) for key in checks)
    rows.extend(
        [
            ("caller_suffix_lossless_sha_match", "true"),
            ("clustering_algorithm_run", "false"),
            ("cluster_analysis_status", "NOT_RUN"),
            ("input_table_load_seconds", max_float("input_table_load_seconds")),
            ("fastq_scan_seconds", max_float("fastq_scan_seconds")),
            ("materialization_write_seconds", max_float("materialization_write_seconds")),
            ("gzip_seconds", gzip_wall),
            ("materializer_wall_seconds", materializer_wall + merge_plain_wall + gzip_wall),
            ("performance_stage_version", base.STAGE_VERSION),
            ("performance_execution_mode", "250K_READ_COHERENT_SHARDS_GLOBAL_KWAY_MERGE"),
            ("shard_count", len(shards)),
            ("projection_metadata_reused", "true"),
            ("global_plain_merge_seconds", merge_plain_wall),
            ("global_parallel_gzip_seconds", gzip_wall),
            ("compression_backend", "pigz_-1_-n"),
            ("compression_threads_per_table", base.PIGZ_THREADS_PER_TABLE),
            ("production_outputs_modified", "false"),
            ("ssot_modified", "false"),
            ("audit_status", "PASS"),
        ]
    )
    return rows


def run_generic_validator_dynamic(table: str) -> dict[str, object]:
    base = CURRENT_BASE
    if base is None:
        raise RuntimeError("base runner not configured")
    path = base.PACKAGE_PART / f"{table}.tsv.gz"
    log = base.LOG_ROOT / "validators" / f"tsv_{table}.log"
    timing = base.TIMING_ROOT / "validators" / f"tsv_{table}.time_v.txt"
    log.parent.mkdir(parents=True, exist_ok=True)
    timing.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(base.VALIDATOR_TSV),
        "--schema", str(base.SCHEMA_JSON),
        "--table", table,
        "--input", str(path),
        "--max-rows", "5000000",
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
    observed = base.data_rows(path)
    status = (
        "PASS"
        if proc.returncode == 0 and observed == base.EXPECTED_FINAL_ROWS[table]
        else "FAIL"
    )
    time_values = base.parse_time_v(timing)
    return {
        "validator": "rnatr_v042_validate_tsv.py",
        "table": table,
        "elapsed_seconds": elapsed,
        "exit_code": proc.returncode,
        "maximum_resident_set_kbytes": time_values.get("Maximum resident set size (kbytes)", "."),
        "observed_rows": observed,
        "expected_rows": base.EXPECTED_FINAL_ROWS[table],
        "status": status,
        "log": str(log),
    }


def run_package_validator_dynamic() -> dict[str, object]:
    base = CURRENT_BASE
    if base is None:
        raise RuntimeError("base runner not configured")
    log = base.LOG_ROOT / "validators/package_prepublication.log"
    timing = base.TIMING_ROOT / "validators/package_prepublication.time_v.txt"
    log.parent.mkdir(parents=True, exist_ok=True)
    timing.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(base.PARALLEL_PACKAGE_VALIDATOR),
        "--schema-dir", str(base.SCHEMA_DIR),
        "--package-dir", str(base.PACKAGE_PART),
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
    time_values = base.parse_time_v(timing)
    return {
        "validator": "rnatr_stage15a_validate_package_parallel_v0.2.2.1.py",
        "table": "PACKAGE",
        "elapsed_seconds": elapsed,
        "exit_code": proc.returncode,
        "maximum_resident_set_kbytes": time_values.get("Maximum resident set size (kbytes)", "."),
        "observed_rows": ".",
        "expected_rows": ".",
        "status": "PASS" if proc.returncode == 0 else "FAIL",
        "log": str(log),
    }


def sum_path_bytes(paths: Iterable[Path]) -> int:
    total = 0
    for path in paths:
        if path.is_file():
            total += path.stat().st_size
    return total


def temp_snapshot(base, shards, stage: str) -> dict[str, object]:
    paths: list[Path] = []
    for shard in shards:
        paths.extend(
            [
                shard.bam,
                shard.full_fastq,
                shard.assignment_path,
                shard.candidate_fastq,
                shard.projection_path,
                shard.window_fastq,
                shard.jobs_path,
                shard.calls_path,
            ]
        )
        if shard.package_dir.is_dir():
            paths.extend(path for path in shard.package_dir.iterdir() if path.is_file())
    if base.PACKAGE_PART.is_dir():
        paths.extend(path for path in base.PACKAGE_PART.iterdir() if path.is_file())
    if base.PACKAGE_FINAL.is_dir():
        paths.extend(path for path in base.PACKAGE_FINAL.iterdir() if path.is_file())
    return {"stage": stage, "temporary_and_output_bytes": sum_path_bytes(paths)}


def full_caller_audit_dynamic(base, shards, expected_totals: dict[str, int]) -> None:
    rows = []
    totals = {key: 0 for key in expected_totals}
    for shard in shards:
        metrics = base.read_metrics(shard.caller_outdir / "general_repeat_integration.qc.tsv")
        output_rows = base.count_gz_tsv(shard.calls_path)[0]
        if output_rows != int(metrics["input_job_rows"]):
            raise RuntimeError(f"caller output row mismatch: {shard.name}")
        for key in totals:
            totals[key] += int(metrics[key])
        rows.append(
            {
                "shard": shard.name,
                "input_rows": metrics["input_job_rows"],
                "output_rows": output_rows,
                "called_rows": metrics["called_rows"],
                "caller_error_rows": metrics["caller_error_rows"],
                "called_prior_overlap_nonpositive_rows": metrics["called_prior_overlap_nonpositive_rows"],
                "audit_status": metrics["audit_status"],
            }
        )
    if totals != expected_totals:
        raise RuntimeError(f"post-timer caller totals mismatch: {totals} != {expected_totals}")
    write_dict_tsv(base.QC_ROOT / "stage15a_scaling_250k_caller_full_audit.tsv", rows)


def fastq_count_bases(path: Path) -> tuple[int, int]:
    rows = 0
    bases = 0
    with pysam.FastxFile(str(path)) as handle:
        for entry in handle:
            rows += 1
            bases += len(entry.sequence)
    return rows, bases


def full_development_audit(base, shards, caller_totals: dict[str, int]) -> tuple[float, dict[str, int]]:
    started = time.perf_counter()
    rows = []
    total_window_records = 0
    total_window_bases = 0
    for shard in shards:
        if Path(str(shard.bam) + ".bai").exists():
            raise RuntimeError(f"unexpected shard BAI: {shard.bam}.bai")
        full_rows, full_ids = base.count_gz_tsv(shard.assignment_path, "read_id")
        if full_rows != shard.candidate_rows or int(full_ids or 0) != shard.candidate_reads:
            raise RuntimeError(f"assignment recount mismatch: {shard.name}")
        assignment_ids = base.gz_tsv_id_set(shard.assignment_path, "read_id")
        candidate_ids = base.fastq_id_set(shard.candidate_fastq)
        if assignment_ids != candidate_ids:
            raise RuntimeError(f"candidate FASTQ lockstep mismatch: {shard.name}")
        projection_rows, projection_reads = base.count_gz_tsv(shard.projection_path, "read_id")
        job_rows, job_reads = base.count_gz_tsv(shard.jobs_path, "read_id")
        p_count, p_digest = base.gz_tsv_order_digest(shard.projection_path, "projection_id")
        j_count, j_digest = base.gz_tsv_order_digest(shard.jobs_path, "projection_id")
        if (
            projection_rows != shard.projection_rows
            or int(projection_reads or 0) != shard.projection_reads
            or job_rows != projection_rows
            or int(job_reads or 0) != shard.projection_reads
            or p_count != j_count
            or p_digest != j_digest
        ):
            raise RuntimeError(f"projection/job lockstep mismatch: {shard.name}")
        window_rows, window_bases = fastq_count_bases(shard.window_fastq)
        total_window_records += window_rows
        total_window_bases += window_bases
        rows.append(
            {
                "shard": shard.name,
                "bam_sha256": sha256_file(shard.bam),
                "full_fastq_sha256": sha256_file(shard.full_fastq),
                "candidate_fastq_sha256": sha256_file(shard.candidate_fastq),
                "candidate_rows": shard.candidate_rows,
                "candidate_reads": shard.candidate_reads,
                "projection_rows": projection_rows,
                "window_fastq_records": window_rows,
                "window_fastq_bases": window_bases,
                "projection_job_order_sha256": p_digest,
                "status": "PASS",
            }
        )
    write_dict_tsv(base.QC_ROOT / "stage15a_scaling_250k_full_development_audit.tsv", rows)
    full_caller_audit_dynamic(base, shards, caller_totals)
    elapsed = time.perf_counter() - started
    write_metrics(
        base.QC_ROOT / "stage15a_scaling_250k_post_timer_audit.qc.tsv",
        [
            ("audit_scope", "FULL_DEVELOPMENT_AUDIT_OUTSIDE_PRODUCTION_TIMER"),
            ("window_fastq_records", total_window_records),
            ("total_candidate_window_bases", total_window_bases),
            ("elapsed_seconds", elapsed),
            ("audit_status", "PASS"),
        ],
    )
    return elapsed, {
        "window_fastq_records": total_window_records,
        "total_candidate_window_bases": total_window_bases,
    }


def checkpoint_manifest(base, shards) -> tuple[str, int, int]:
    rows = []
    for shard in shards:
        roles = [
            ("shard_bam", shard.bam),
            ("shard_full_fastq", shard.full_fastq),
            ("assignment", shard.assignment_path),
            ("candidate_fastq", shard.candidate_fastq),
            ("projection", shard.projection_path),
            ("motif_jobs", shard.jobs_path),
            ("caller_calls", shard.calls_path),
            ("materialization_qc", shard.package_dir / "materialization.qc.tsv"),
        ]
        roles.extend((f"materialized_{table}", shard.package_dir / f"{table}.tsv") for table in base.TABLE_ORDER)
        for role, path in roles:
            ensure_file(path)
            rows.append(
                {
                    "role": role,
                    "shard": shard.name,
                    "path": str(path),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    for path in sorted(base.PACKAGE_FINAL.iterdir()):
        if path.is_file():
            rows.append(
                {
                    "role": "final_package_artifact",
                    "shard": ".",
                    "path": str(path),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    manifest = base.QC_ROOT / "stage15a_scaling_250k_checkpoint_manifest.tsv"
    write_dict_tsv(manifest, rows)
    # Verify every row and prove a bad SHA is rejected.
    def verify(records: list[dict[str, object]]) -> bool:
        for row in records:
            path = Path(str(row["path"]))
            if not path.is_file() or path.stat().st_size != int(row["bytes"]):
                return False
            if sha256_file(path) != str(row["sha256"]):
                return False
        return True
    if not verify(rows):
        raise RuntimeError("checkpoint manifest verification failed")
    bad = [dict(row) for row in rows]
    bad[0]["sha256"] = "0" * 64
    if verify(bad):
        raise RuntimeError("checkpoint negative fixture was not rejected")
    write_metrics(
        base.QC_ROOT / "stage15a_scaling_250k_checkpoint.qc.tsv",
        [
            ("checkpoint_rows", len(rows)),
            ("checkpoint_bytes", sum(int(row["bytes"]) for row in rows)),
            ("checkpoint_manifest_sha256", sha256_file(manifest)),
            ("checkpoint_manifest_integrity", "PASS"),
            ("checkpoint_negative_fixture_rejected", "PASS"),
            ("selective_resume_250k_executed", "false"),
            ("audit_status", "PASS"),
        ],
    )
    return sha256_file(manifest), len(rows), sum(int(row["bytes"]) for row in rows)


def maximum_rss_from_records(records: list[dict[str, object]]) -> int:
    values = []
    for row in records:
        value = row.get("maximum_resident_set_kbytes", ".")
        if str(value).isdigit():
            values.append(int(value))
    return max(values) if values else 0


def run_replicate(rep: str, hash_seed: str) -> int:
    base = configure_base(rep)
    if base.RESULT_ROOT.exists() or base.QC_ROOT.exists():
        raise RuntimeError(f"replicate root exists; preserve and review: {base.RESULT_ROOT}")
    for directory in (
        base.RESULT_ROOT,
        base.QC_ROOT,
        base.LOG_ROOT,
        base.TIMING_ROOT,
        base.COMPARISON_ROOT,
        base.CONTRACT_ROOT,
        base.MARKER_ROOT,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    print(f"===== {base.STAGE_VERSION} =====")
    print(f"external_run_id\t{EXTERNAL_RUN_ID}")
    print(f"internal_component_run_id\t{INTERNAL_RUN_ID}")
    print(f"replicate\t{rep}")
    print(f"python_hash_seed\t{hash_seed}")
    print("active_pipeline_switch\tPROHIBITED")
    print("ssot_update\tPROHIBITED")
    print("full_5_31m_run\tPROHIBITED")
    active_before = verify_evidence_gate(base)
    write_dict_tsv(
        base.CONTRACT_ROOT / "active_guards_before.tsv",
        [{"path": str(path), "sha256": digest, "status": "PASS"} for path, digest in active_before.items()],
    )
    input_metrics = read_metrics(INPUT_QC)
    input_fastq = Path(input_metrics["subset_fastq"])
    shards = create_shards(base)
    base.setup_shard_files(shards)
    timing_rows = []
    temp_rows = []
    all_stage_records: list[dict[str, object]] = []
    production_started = time.perf_counter()

    partition = partition_inputs(base, shards, input_fastq)
    timing_rows.append({"stage": "15AS0_partition_inputs", "elapsed_seconds": partition["elapsed_seconds"]})
    temp_rows.append(temp_snapshot(base, shards, "after_partition"))

    wall_11b, records_11b = base.run_parallel_stage(
        "15AS1_11b",
        shards,
        lambda shard: ["bash", str(shard.script_11b)],
        lambda shard: {
            "EXPECTED_ALIGNMENT_RECORDS": str(shard.alignment_records),
            "EXPECTED_READS": str(shard.unique_reads),
        },
    )
    timing_rows.append({"stage": "15AS1_11b", "elapsed_seconds": wall_11b})
    all_stage_records.extend(records_11b)
    candidate_rows, candidate_reads = load_candidate_counts(base, shards)
    temp_rows.append(temp_snapshot(base, shards, "after_11b"))

    wall_extract, records_extract = extract_candidate_fastqs(base, shards)
    timing_rows.append({"stage": "15AS1C_extract_candidate_fastq", "elapsed_seconds": wall_extract})
    all_stage_records.extend(records_extract)
    temp_rows.append(temp_snapshot(base, shards, "after_candidate_fastq"))

    wall_11d3, records_11d3 = base.run_parallel_stage(
        "15AS2_11d3",
        shards,
        lambda shard: ["bash", str(shard.script_11d3)],
        lambda shard: {
            "EXPECTED_CANDIDATE_ROWS": str(shard.candidate_rows),
            "EXPECTED_CANDIDATE_READS": str(shard.candidate_reads),
        },
    )
    timing_rows.append({"stage": "15AS2_11d3", "elapsed_seconds": wall_11d3})
    all_stage_records.extend(records_11d3)
    temp_rows.append(temp_snapshot(base, shards, "after_11d3"))

    wall_11e, record_11e = base.run_fast_shared_catalog_motif_jobs(shards)
    timing_rows.append({"stage": "15AS3_fast_shared_catalog_motif_jobs", "elapsed_seconds": wall_11e})
    all_stage_records.append(record_11e)
    write_dict_tsv(base.QC_ROOT / "15AS3_fast_shared_catalog_motif_jobs.tsv", [record_11e])
    projection_rows, projection_reads = load_projection_counts(base, shards)
    if projection_rows != candidate_rows or projection_reads != candidate_reads:
        raise RuntimeError("aggregate candidate/projection mismatch")
    temp_rows.append(temp_snapshot(base, shards, "after_11e"))

    wall_cm, caller_records, materializer_records, max_materializer = run_caller_materializer(
        base, shards, hash_seed
    )
    timing_rows.append({"stage": "15AS4_5_caller_materializer_pipeline", "elapsed_seconds": wall_cm})
    all_stage_records.extend(caller_records)
    all_stage_records.extend(materializer_records)
    caller_totals = load_caller_totals(base, shards)
    expected_rows = derive_expected_final_rows(base, shards, caller_totals)
    temp_rows.append(temp_snapshot(base, shards, "after_caller_materializer"))

    merge_wall, merge_plain, gzip_wall, _ = base.merge_packages(
        shards, materializer_wall=max_materializer
    )
    timing_rows.append({"stage": "15AS6_parallel_global_merge", "elapsed_seconds": merge_plain})
    timing_rows.append({"stage": "15AS6_parallel_global_gzip", "elapsed_seconds": gzip_wall})
    temp_rows.append(temp_snapshot(base, shards, "after_merge_gzip"))

    validator_wall, validator_rows = base.run_all_validators_prepublication()
    timing_rows.append({"stage": "15AS7_concurrent_frozen_validators", "elapsed_seconds": validator_wall})
    all_stage_records.extend(validator_rows)

    publish_wall, _ = base.publish_verified_package()
    timing_rows.append({"stage": "15AS8_atomic_publication", "elapsed_seconds": publish_wall})
    production_seconds = time.perf_counter() - production_started
    temp_rows.append(temp_snapshot(base, shards, "after_publication"))

    development_audit_seconds, complexity = full_development_audit(
        base, shards, caller_totals
    )
    frozen_seconds, frozen_status = base.run_frozen_package_validator_postpublication()
    negative_status = base.validator_missing_artifact_failure_parity()
    checkpoint_sha, checkpoint_rows, checkpoint_bytes = checkpoint_manifest(base, shards)
    base.verify_active_unchanged(active_before)
    base.verify_ssot_unchanged()
    base.write_stage_timing(timing_rows)
    write_dict_tsv(base.QC_ROOT / "stage15a_scaling_250k_temp_bytes.tsv", temp_rows)
    max_rss = maximum_rss_from_records(all_stage_records)
    listed_seconds = sum(float(row["elapsed_seconds"]) for row in timing_rows)
    projected_minutes = production_seconds * FULL_READS / BENCHMARK_READS / 60.0
    hard = "PASS" if projected_minutes <= 60.0 else "FAIL"
    target = "TARGET_MET" if projected_minutes <= 30.0 else "TARGET_NOT_MET"
    qc_rows = [
        ("stage_version", base.STAGE_VERSION),
        ("external_run_id", EXTERNAL_RUN_ID),
        ("internal_component_run_id", INTERNAL_RUN_ID),
        ("replicate", rep),
        ("python_hash_seed", hash_seed),
        ("input_reads", BENCHMARK_READS),
        ("alignment_records", partition["alignment_records"]),
        ("candidate_rows", candidate_rows),
        ("candidate_reads", candidate_reads),
        ("projection_rows", projection_rows),
        ("projection_reads", projection_reads),
        ("total_candidate_window_records", complexity["window_fastq_records"]),
        ("total_candidate_window_bases", complexity["total_candidate_window_bases"]),
        ("caller_attempt_rows", caller_totals["input_job_rows"]),
        ("caller_called_rows", caller_totals["called_rows"]),
        ("caller_no_call_rows", caller_totals["input_job_rows"] - caller_totals["called_rows"]),
        ("caller_error_rows", caller_totals["caller_error_rows"]),
        ("called_prior_overlap_nonpositive_rows", caller_totals["called_prior_overlap_nonpositive_rows"]),
        ("general_repeat_calls_rows", expected_rows["general_repeat_calls"]),
        ("read_evidence_rows", expected_rows["read_evidence"]),
        ("repeat_event_rows", expected_rows["repeat_events"]),
        ("repeat_segment_rows", expected_rows["repeat_segments"]),
        ("repeat_interruption_rows", expected_rows["repeat_interruptions"]),
        ("bam_to_final_cold_seconds", production_seconds),
        ("candidate_fastq_extraction_seconds", wall_extract),
        ("bam_to_final_warm_equivalent_seconds", production_seconds - wall_extract),
        ("listed_stage_seconds", listed_seconds),
        ("production_timer_unaccounted_seconds", production_seconds - listed_seconds),
        ("maximum_observed_stage_rss_kbytes", max_rss),
        ("peak_temporary_and_output_bytes", max(int(row["temporary_and_output_bytes"]) for row in temp_rows)),
        ("post_timer_development_audit_seconds", development_audit_seconds),
        ("frozen_package_validator_postpublication", frozen_status),
        ("frozen_package_validator_postpublication_seconds", frozen_seconds),
        ("negative_fixture_failure_parity", negative_status),
        ("checkpoint_manifest_sha256", checkpoint_sha),
        ("checkpoint_rows", checkpoint_rows),
        ("checkpoint_bytes", checkpoint_bytes),
        ("checkpoint_manifest_integrity", "PASS"),
        ("checkpoint_negative_fixture_rejected", "PASS"),
        ("selective_resume_250k_executed", "false"),
        ("atomic_publication", "PASS"),
        ("conservative_linear_5_31m_projection_minutes", projected_minutes),
        ("five_m_hard_ceiling_60min_projection", hard),
        ("five_m_target_30min_projection", target),
        ("active_pipeline_modified", "false"),
        ("ssot_modified", "false"),
        ("full_5_31m_run_started", "false"),
        ("package_reproducibility", "DEFERRED_TO_REPLICATE_COMPARISON"),
        ("nested_100k_package_parity", "DEFERRED_TO_REPLICATE_COMPARISON"),
        ("correctness_status", "PASS"),
        ("performance_implementation_status", "PASS"),
        ("audit_status", "PASS"),
        ("next_gate", "COMPARE_DETERMINISTIC_250K_REPLICATES"),
    ]
    final_qc = base.QC_ROOT / "stage15a_scaling_250k_replicate.qc.tsv"
    write_metrics(final_qc, qc_rows)
    print("===== 250K REPLICATE COMPLETE =====")
    for key, value in qc_rows:
        print(f"{key}\t{value}")
    print(f"QC\t{final_qc}")
    return 0


def logical_sha(path: Path) -> str:
    h = hashlib.sha256()
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def package_comparison() -> tuple[bool, bool, list[dict[str, object]]]:
    rows = []
    all_logical = True
    all_raw = True
    for table in ("general_repeat_calls", "read_evidence", "repeat_events", "repeat_segments", "repeat_interruptions"):
        for suffix in (".tsv", ".tsv.gz"):
            a = RESULT_BASE / "replicate_A/package_performance" / f"{table}{suffix}"
            b = RESULT_BASE / "replicate_B/package_performance" / f"{table}{suffix}"
            ensure_file(a)
            ensure_file(b)
            raw_a = sha256_file(a)
            raw_b = sha256_file(b)
            logical_a = logical_sha(a)
            logical_b = logical_sha(b)
            raw_equal = raw_a == raw_b
            logical_equal = logical_a == logical_b
            all_raw = all_raw and raw_equal
            all_logical = all_logical and logical_equal
            rows.append(
                {
                    "artifact": f"{table}{suffix}",
                    "a_bytes": a.stat().st_size,
                    "b_bytes": b.stat().st_size,
                    "a_raw_sha256": raw_a,
                    "b_raw_sha256": raw_b,
                    "a_logical_sha256": logical_a,
                    "b_logical_sha256": logical_b,
                    "raw_equal": str(raw_equal).lower(),
                    "logical_equal": str(logical_equal).lower(),
                }
            )
    write_dict_tsv(QC_BASE / "stage15a_scaling_250k_package_reproducibility.tsv", rows)
    if not all_logical or not all_raw:
        failures = [row["artifact"] for row in rows if row["logical_equal"] != "true" or row["raw_equal"] != "true"]
        raise RuntimeError("250k package reproducibility failed: " + ",".join(map(str, failures)))
    return all_logical, all_raw, rows


def caller_reproducibility() -> bool:
    rows = []
    all_equal = True
    for index in range(SHARDS):
        name = f"shard_{index:03d}"
        a = RESULT_BASE / f"replicate_A/shards/{name}/caller/general_repeat_calls.v0.4.0.tsv.gz"
        b = RESULT_BASE / f"replicate_B/shards/{name}/caller/general_repeat_calls.v0.4.0.tsv.gz"
        ensure_file(a)
        ensure_file(b)
        equal = logical_sha(a) == logical_sha(b)
        all_equal = all_equal and equal
        rows.append(
            {
                "shard": name,
                "a_logical_sha256": logical_sha(a),
                "b_logical_sha256": logical_sha(b),
                "logical_equal": str(equal).lower(),
            }
        )
    write_dict_tsv(QC_BASE / "stage15a_scaling_250k_caller_reproducibility.tsv", rows)
    if not all_equal:
        raise RuntimeError("250k caller reproducibility failed")
    return True


def filtered_digest(path: Path, anchor_ids: set[str]) -> tuple[int, str, str]:
    h = hashlib.sha256()
    count = 0
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None or "read_id" not in reader.fieldnames:
            raise RuntimeError(f"package table lacks read_id: {path}")
        header = "\t".join(reader.fieldnames)
        for row in reader:
            if row["read_id"] not in anchor_ids:
                continue
            h.update(("\t".join(row[field] for field in reader.fieldnames) + "\n").encode("utf-8"))
            count += 1
    return count, h.hexdigest(), hashlib.sha256(header.encode("utf-8")).hexdigest()


def load_anchor_ids() -> set[str]:
    input_metrics = read_metrics(INPUT_QC)
    anchor_fastq = Path(input_metrics["anchor_fastq"])
    ids = set()
    with pysam.FastxFile(str(anchor_fastq)) as handle:
        for entry in handle:
            if entry.name in ids:
                raise RuntimeError(f"duplicate anchor ID: {entry.name}")
            ids.add(entry.name)
    if len(ids) != 100_000:
        raise RuntimeError(f"anchor ID count mismatch: {len(ids)}")
    return ids


def nested_100k_package_audit() -> bool:
    anchor_ids = load_anchor_ids()
    candidate_package = RESULT_BASE / "replicate_A/package_performance"
    rows = []
    all_equal = True
    for table in ("general_repeat_calls", "read_evidence", "repeat_events", "repeat_segments", "repeat_interruptions"):
        reference = REFERENCE_100K_PACKAGE / f"{table}.tsv.gz"
        candidate = candidate_package / f"{table}.tsv.gz"
        ref_count, ref_digest, ref_header = filtered_digest(reference, anchor_ids)
        cand_count, cand_digest, cand_header = filtered_digest(candidate, anchor_ids)
        equal = (
            ref_count == cand_count
            and ref_digest == cand_digest
            and ref_header == cand_header
        )
        all_equal = all_equal and equal
        rows.append(
            {
                "table": table,
                "reference_anchor_rows": ref_count,
                "candidate_anchor_rows": cand_count,
                "reference_anchor_sha256": ref_digest,
                "candidate_anchor_sha256": cand_digest,
                "header_equal": str(ref_header == cand_header).lower(),
                "nested_anchor_exact_equal": str(equal).lower(),
            }
        )
    write_dict_tsv(QC_BASE / "stage15a_scaling_250k_nested_100k_package_parity.tsv", rows)
    if not all_equal:
        failed = [row["table"] for row in rows if row["nested_anchor_exact_equal"] != "true"]
        raise RuntimeError("nested 100k package parity failed: " + ",".join(map(str, failed)))
    return True


def read_timing(path: Path) -> dict[str, float]:
    rows = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            rows[row["stage"]] = float(row["elapsed_seconds"])
    return rows


def compare_checkpoint_manifests() -> bool:
    rows = []
    for rep in ("A", "B"):
        qc = QC_BASE / f"replicate_{rep}/stage15a_scaling_250k_checkpoint.qc.tsv"
        metrics = read_metrics(qc)
        status = (
            metrics.get("audit_status") == "PASS"
            and metrics.get("checkpoint_manifest_integrity") == "PASS"
            and metrics.get("checkpoint_negative_fixture_rejected") == "PASS"
        )
        if not status:
            raise RuntimeError(f"checkpoint integrity gate failed for replicate {rep}")
        rows.append({
            "replicate": rep,
            "checkpoint_rows": metrics["checkpoint_rows"],
            "checkpoint_bytes": metrics["checkpoint_bytes"],
            "checkpoint_manifest_sha256": metrics["checkpoint_manifest_sha256"],
            "integrity": metrics["checkpoint_manifest_integrity"],
            "negative_fixture_rejected": metrics["checkpoint_negative_fixture_rejected"],
            "status": "PASS",
        })
    write_dict_tsv(
        QC_BASE / "stage15a_scaling_250k_checkpoint_reproducibility.tsv", rows
    )
    return True


def compare_replicates() -> int:
    if COMBINED_QC.exists():
        raise RuntimeError(f"combined QC already exists: {COMBINED_QC}")
    QC_BASE.mkdir(parents=True, exist_ok=True)
    qcs = {}
    for rep in ("A", "B"):
        path = QC_BASE / f"replicate_{rep}/stage15a_scaling_250k_replicate.qc.tsv"
        metrics = read_metrics(path)
        if metrics.get("audit_status") != "PASS":
            raise RuntimeError(f"replicate {rep} not PASS")
        qcs[rep] = metrics
    logical, raw, _ = package_comparison()
    caller_equal = caller_reproducibility()
    checkpoint_equal = compare_checkpoint_manifests()
    nested_equal = nested_100k_package_audit()
    seconds_a = float(qcs["A"]["bam_to_final_cold_seconds"])
    seconds_b = float(qcs["B"]["bam_to_final_cold_seconds"])
    conservative_seconds = max(seconds_a, seconds_b)
    warm_a = float(qcs["A"]["bam_to_final_warm_equivalent_seconds"])
    warm_b = float(qcs["B"]["bam_to_final_warm_equivalent_seconds"])
    projected_minutes = conservative_seconds * FULL_READS / BENCHMARK_READS / 60.0
    hard = "PASS" if projected_minutes <= 60.0 else "FAIL"
    target = "TARGET_MET" if projected_minutes <= 30.0 else "TARGET_NOT_MET"
    margin = 60.0 - projected_minutes
    timing_a = read_timing(QC_BASE / "replicate_A/stage15a_performance_timing.tsv")
    timing_b = read_timing(QC_BASE / "replicate_B/stage15a_performance_timing.tsv")
    timing_100k = read_timing(V0221_TIMING)
    stage_rows = []
    all_stages = sorted(set(timing_a) | set(timing_b))
    baseline_alias = {
        "15AS0_partition_inputs": "partition_inputs",
        "15AS1_11b": "15AP1_11b",
        "15AS2_11d3": "15AP2_11d3",
        "15AS3_fast_shared_catalog_motif_jobs": "15AP3_fast_shared_catalog_motif_jobs",
        "15AS4_5_caller_materializer_pipeline": "15AP4_5_caller_materializer_pipeline",
        "15AS6_parallel_global_merge": "15AP6_parallel_global_merge",
        "15AS6_parallel_global_gzip": "15AP6_parallel_global_gzip",
        "15AS7_concurrent_frozen_validators": "15AP7_concurrent_frozen_validators",
        "15AS8_atomic_publication": "15AP8_atomic_publication",
    }
    for stage in all_stages:
        a = timing_a.get(stage, 0.0)
        b = timing_b.get(stage, 0.0)
        baseline_stage = baseline_alias.get(stage)
        baseline = timing_100k.get(baseline_stage, 0.0) if baseline_stage else 0.0
        stage_rows.append(
            {
                "stage": stage,
                "replicate_A_seconds": a,
                "replicate_B_seconds": b,
                "conservative_250k_seconds": max(a, b),
                "baseline_100k_stage": baseline_stage or ".",
                "baseline_100k_seconds": baseline if baseline_stage else ".",
                "observed_scaling_ratio": max(a, b) / baseline if baseline > 0 else ".",
                "ideal_read_count_ratio": 2.5,
            }
        )
    write_dict_tsv(QC_BASE / "stage15a_scaling_250k_stage_model.tsv", stage_rows)
    counts_keys = [
        "alignment_records", "candidate_rows", "candidate_reads", "projection_rows",
        "total_candidate_window_records", "total_candidate_window_bases",
        "caller_attempt_rows", "caller_called_rows", "caller_no_call_rows",
        "general_repeat_calls_rows", "read_evidence_rows", "repeat_event_rows",
        "repeat_segment_rows", "repeat_interruption_rows",
    ]
    for key in counts_keys:
        if qcs["A"][key] != qcs["B"][key]:
            raise RuntimeError(f"replicate complexity mismatch {key}: {qcs['A'][key]} != {qcs['B'][key]}")
    next_gate = (
        "BUILD_AND_RUN_DETERMINISTIC_500K_SCALING_NOT_FULL_5_31M"
        if hard == "PASS"
        else "PROFILE_250K_AND_IMPLEMENT_11D3_11E_FUSION_BEFORE_500K"
    )
    rows = [
        ("stage_version", VERSION),
        ("external_run_id", EXTERNAL_RUN_ID),
        ("input_reads", BENCHMARK_READS),
        ("replicate_A_hash_seed", qcs["A"]["python_hash_seed"]),
        ("replicate_B_hash_seed", qcs["B"]["python_hash_seed"]),
        ("replicate_A_bam_to_final_cold_seconds", seconds_a),
        ("replicate_B_bam_to_final_cold_seconds", seconds_b),
        ("conservative_250k_bam_to_final_cold_seconds", conservative_seconds),
        ("replicate_A_warm_equivalent_seconds", warm_a),
        ("replicate_B_warm_equivalent_seconds", warm_b),
        ("runtime_replicate_absolute_difference_seconds", abs(seconds_a - seconds_b)),
        ("runtime_replicate_relative_difference", abs(seconds_a - seconds_b) / conservative_seconds),
        ("baseline_100k_seconds", BASELINE_100K_SECONDS),
        ("observed_100k_to_250k_runtime_ratio", conservative_seconds / BASELINE_100K_SECONDS),
        ("ideal_read_count_ratio", 2.5),
        ("per_read_normalized_scaling_factor", (conservative_seconds / BENCHMARK_READS) / (BASELINE_100K_SECONDS / 100_000)),
        ("conservative_linear_5_31m_projection_minutes", projected_minutes),
        ("five_m_hard_ceiling_60min_projection", hard),
        ("five_m_hard_ceiling_margin_minutes", margin),
        ("five_m_target_30min_projection", target),
        ("package_exact_logical_reproducibility", str(logical).lower()),
        ("package_exact_raw_reproducibility", str(raw).lower()),
        ("caller_hashseed_logical_reproducibility", str(caller_equal).lower()),
        ("checkpoint_manifest_reproducibility", str(checkpoint_equal).lower()),
        ("nested_100k_package_exact_parity", str(nested_equal).lower()),
        ("checkpoint_manifest_integrity_250k", "PASS"),
        ("selective_resume_250k_executed", "false"),
        ("full_scale_restart_validated", "false"),
        ("deterministic_250k_scaling", "PASS"),
        ("active_pipeline_modified", "false"),
        ("ssot_modified", "false"),
        ("full_5_31m_run_started", "false"),
        ("stage15a_overall_status", "IN_PROGRESS"),
        ("audit_status", "PASS"),
        ("next_gate", next_gate),
    ]
    for key in counts_keys:
        rows.append((key, qcs["A"][key]))
    rows.extend(
        [
            ("replicate_A_maximum_observed_stage_rss_kbytes", qcs["A"]["maximum_observed_stage_rss_kbytes"]),
            ("replicate_B_maximum_observed_stage_rss_kbytes", qcs["B"]["maximum_observed_stage_rss_kbytes"]),
            ("replicate_A_peak_temporary_and_output_bytes", qcs["A"]["peak_temporary_and_output_bytes"]),
            ("replicate_B_peak_temporary_and_output_bytes", qcs["B"]["peak_temporary_and_output_bytes"]),
        ]
    )
    write_metrics(COMBINED_QC, rows)
    print("===== STAGE 15A DETERMINISTIC 250K SCALING COMPLETE =====")
    for key, value in rows:
        print(f"{key}\t{value}")
    print(f"QC\t{COMBINED_QC}")
    return 0


def run_subprocess_mode(args: list[str], label: str) -> None:
    logs = QC_BASE / "orchestration"
    logs.mkdir(parents=True, exist_ok=True)
    log = logs / f"{label}.log"
    time_v = logs / f"{label}.time_v.txt"
    with log.open("w", encoding="utf-8") as handle:
        proc = subprocess.run(
            ["/usr/bin/time", "-v", "-o", str(time_v), sys.executable, __file__, *args],
            stdout=handle,
            stderr=subprocess.STDOUT,
            text=True,
            env=os.environ.copy(),
        )
    if proc.returncode != 0:
        tail = "\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-80:])
        raise RuntimeError(f"{label} failed exit={proc.returncode}; log={log}\n{tail}")
    print(f"{label}\tPASS\tlog={log}")


def orchestrate() -> int:
    if RESULT_BASE.exists() or QC_BASE.exists():
        raise RuntimeError(f"250k scaling root exists; preserve and review: {RESULT_BASE} {QC_BASE}")
    RESULT_BASE.mkdir(parents=True)
    QC_BASE.mkdir(parents=True)
    run_subprocess_mode(["--replicate", "A", "--hash-seed", "0"], "replicate_A")
    run_subprocess_mode(["--replicate", "B", "--hash-seed", "20260808"], "replicate_B")
    run_subprocess_mode(["--compare"], "compare_replicates")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--orchestrate", action="store_true")
    parser.add_argument("--replicate", choices=["A", "B"])
    parser.add_argument("--hash-seed")
    parser.add_argument("--compare", action="store_true")
    args = parser.parse_args()
    modes = sum(bool(x) for x in (args.orchestrate, args.replicate, args.compare))
    if modes != 1:
        raise ValueError("choose exactly one of --orchestrate, --replicate, --compare")
    if args.orchestrate:
        return orchestrate()
    if args.replicate:
        if args.hash_seed is None:
            raise ValueError("--replicate requires --hash-seed")
        return run_replicate(args.replicate, args.hash_seed)
    return compare_replicates()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        QC_BASE.mkdir(parents=True, exist_ok=True)
        failure = QC_BASE / "stage15a_scaling_250k.failure.txt"
        failure.write_text(
            f"stage_version\t{VERSION}\n"
            f"exception_type\t{type(exc).__name__}\n"
            f"exception\t{exc}\n\n{traceback.format_exc()}",
            encoding="utf-8",
        )
        print(f"ERROR: {exc}", file=sys.stderr)
        print(f"FAILURE_RECORD\t{failure}", file=sys.stderr)
        raise
