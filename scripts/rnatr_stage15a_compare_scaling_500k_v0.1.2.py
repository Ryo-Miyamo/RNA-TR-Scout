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

VERSION = "rnatr_stage15a_deterministic_500k_scaling_v0.1.2_compare_amendment"
PROJECT_ROOT = Path("/mnt/intelssd/rnatr_project")
INTERNAL_RUN_ID = "ENCSR307SHM_stage15a500k_seed20260809_mm2splice_v1"
EXTERNAL_RUN_ID = "ENCSR307SHM_stage15a500k_seed20260809_mm2splice_v1"
INPUT_VERSION = "rnatr_stage15a_500k_input_v0.1.0"
INPUT_RESULT_ROOT = PROJECT_ROOT / "results/15_stage15a_inputs" / EXTERNAL_RUN_ID / INPUT_VERSION
INPUT_QC_ROOT = PROJECT_ROOT / "qc/15_stage15a_inputs" / EXTERNAL_RUN_ID / INPUT_VERSION
INPUT_QC = INPUT_QC_ROOT / "stage15a_500k_input.qc.tsv"
RESULT_BASE = (
    PROJECT_ROOT / "results/15_stage15a_bam_to_final" / EXTERNAL_RUN_ID
    / "v0.1.1_500k_scaling"
)
QC_BASE = (
    PROJECT_ROOT / "qc/15_stage15a_bam_to_final" / EXTERNAL_RUN_ID
    / "v0.1.1_500k_scaling"
)
COMBINED_QC = QC_BASE / "stage15a_scaling_500k.qc.tsv"
BASE_RUNNER = PROJECT_ROOT / "scripts/rnatr_stage15a_run_performance_100k_v0.2.2.1.py"
BASE_RUNNER_SHA256 = "7bfb7018cea80cd92854882751cffb49bea817296f69866801a64f9529c5e1a8"
CANDIDATE_EXTRACTOR = PROJECT_ROOT / "scripts/rnatr_stage15a_extract_candidate_fastq_v0.1.0.py"
CANDIDATE_EXTRACTOR_SHA256 = "b4ecf4e5ecf1a1c0e57e96cb30f560a21230e1463777bdbb0e36601918a9abbf"
SSOT_GUARDS = {
    PROJECT_ROOT / "metadata/ssot/rnatr_ssot.py": "8aeff1eda5c301e74a9054e786ed19bf5b699ff6aa111221aa2e60f6d733b37b",
    PROJECT_ROOT / "metadata/ssot/rnatr_ssot.sqlite": "7edb4eb63e8f04b6fe8d8e67a82a6d9d70ba55c1946c62827d7b133e0d5a4274",
}
LATEST_SSOT_UPDATE_QC = (
    PROJECT_ROOT / "qc/15_stage15a_ssot_update"
    / "ENCSR307SHM_stage15a250k_seed20260808_mm2splice_v1"
    / "250k_archaudit_v0.1.1/stage15a_250k_archaudit_ssot_update.qc.tsv"
)
LATEST_SSOT_UPDATE_QC_SHA256 = "d2a8ae8d87ab222fdce57ab3fd88cc3e824d6ba7a0a7b92c7611a29dc381511c"
POST250K_AUDIT_QC = (
    PROJECT_ROOT / "qc/15_architecture_consistency_audit"
    / "ENCSR307SHM_stage15a250k_seed20260808_mm2splice_v1"
    / "post_250k_v0.1.1/architecture_consistency_audit.qc.tsv"
)
POST250K_AUDIT_QC_SHA256 = "949bd376480c1deaf3bb55b12f190b1773c9244ea37203412d28443cd75aafda"
CHECKPOINT_AMENDMENT = (
    PROJECT_ROOT / "qc/15_architecture_consistency_audit"
    / "ENCSR307SHM_stage15a250k_seed20260808_mm2splice_v1"
    / "post_250k_v0.1.1/checkpoint_logical_reproducibility.tsv"
)
CHECKPOINT_AMENDMENT_SHA256 = "caddd55fbfaeb3be6277f9bd57d35b732e022f626a1c4dcc29ee5f2d1ce5a39b"
SCALING_250K_QC = (
    PROJECT_ROOT / "qc/15_stage15a_bam_to_final"
    / "ENCSR307SHM_stage15a250k_seed20260808_mm2splice_v1"
    / "v0.1.2_250k_scaling/stage15a_scaling_250k.qc.tsv"
)
SCALING_250K_QC_SHA256 = "a2504e27c84ca3d77a53c4484d977042259c2f92caeb4962479b065d80caffea"
ANCHOR_250K_INPUT_QC = (
    PROJECT_ROOT / "qc/15_stage15a_inputs"
    / "ENCSR307SHM_stage15a250k_seed20260808_mm2splice_v1"
    / "rnatr_stage15a_250k_input_v0.1.0/stage15a_250k_input.qc.tsv"
)
ANCHOR_250K_INPUT_QC_SHA256 = "9e81684ab9afd9a22ab9d2bf96e778fd4b3216a97c5e56ee123c245ae4b2db75"
REFERENCE_250K_PACKAGE_MANIFEST_SHA256 = "34e17476592053be20b6b2c9ef19f8dc6705c9bcb25e12066b4d4ee887efaaf1"
REFERENCE_250K_PACKAGE = (
    PROJECT_ROOT / "results/15_stage15a_bam_to_final"
    / "ENCSR307SHM_stage15a250k_seed20260808_mm2splice_v1"
    / "v0.1.2_250k_scaling/replicate_A/package_performance"
)
REFERENCE_250K_RESULT = (
    PROJECT_ROOT / "results/15_stage15a_bam_to_final"
    / "ENCSR307SHM_stage15a250k_seed20260808_mm2splice_v1"
    / "v0.1.2_250k_scaling"
)
RELEASE_GATES_V024 = PROJECT_ROOT / "validation/release_gates_v0.2.4.tsv"
RELEASE_GATES_V024_SHA256 = "90ecf0c5f9cf0ba68361a5538d98aabc63afbe063fec5ee1060a7d0e508cce87"
FULL_READS = 5_312_696
BENCHMARK_READS = 500_000
BASELINE_250K_SECONDS = 169.0068411460379
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
    base.RUN_ID = EXTERNAL_RUN_ID
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
    base.BAM = Path(input_metrics["bam_500k"])
    base.BAM_SHA256 = input_metrics["bam_500k_sha256"]
    base.SSOT_GUARDS = dict(SSOT_GUARDS)
    base.EXPECTED_FINAL_ROWS = {}

    base.SOURCE_11B = PROJECT_ROOT / "scripts/11b_extract_alignment_segments_and_target_candidates.stage15a500k_runid_v0.1.0.sh"
    base.SOURCE_11D3 = PROJECT_ROOT / "scripts/11d3_project_targets_to_raw_reads.stage15a500k_runid_v0.1.0.sh"
    base.SOURCE_11E = PROJECT_ROOT / "scripts/11e_prepare_motif_scan_jobs.stage15a500k_runid_v0.1.0.sh"
    base.SOURCE_SHA = {
        base.SOURCE_11B: "ccf37ebbe71451f12d113cb4148e5415ad7cbcd59ef954b7b7dd7a6b69078075",
        base.SOURCE_11D3: "d7411df47e54e672ea3c838746402d35787c0d1c2fe0af628e7a7f36d98ea203",
        base.SOURCE_11E: "b648b24f22c96fa5625baf09313500c2ca54668ed318ed0aa49570a10c743e3b",
    }
    base.PERF_CALLER = PROJECT_ROOT / "scripts/rnatr_stage15a_native_v041_runid_adapter_v0.2.1.py"
    base.PERF_CALLER_SHA256 = "18d40dba5733efbfa633fff1d52372db49c63bcf315acb7f86acbdc64c89e386"
    base.PERF_MATERIALIZER = PROJECT_ROOT / "scripts/rnatr_materialize_native_v041_to_evidence_v042_runid_adapter_v0.2.1.py"
    base.PERF_MATERIALIZER_SHA256 = "7ba7f5082c9671be55b6b223c20f5bc8b933ad8b4658b1789187e043943949d4"
    base.FAST_MOTIF_BUILDER = PROJECT_ROOT / "scripts/rnatr_stage15a_fast_motif_jobs_scaling_v0.2.2.2.py"
    base.FAST_MOTIF_BUILDER_SHA256 = "3e36454a515cd8c0411957000099867b582ae7d2bef78b7fe2ebd61bf09f4dc4"

    base.aggregate_materializer_qc = aggregate_materializer_qc_dynamic
    base.run_generic_validator = run_generic_validator_dynamic
    base.run_package_validator_prepublication = run_package_validator_dynamic
    CURRENT_BASE = base
    return base


def verify_evidence_gate(base) -> dict[Path, str]:
    evidence = [
        (LATEST_SSOT_UPDATE_QC, LATEST_SSOT_UPDATE_QC_SHA256),
        (POST250K_AUDIT_QC, POST250K_AUDIT_QC_SHA256),
        (CHECKPOINT_AMENDMENT, CHECKPOINT_AMENDMENT_SHA256),
        (SCALING_250K_QC, SCALING_250K_QC_SHA256),
        (ANCHOR_250K_INPUT_QC, ANCHOR_250K_INPUT_QC_SHA256),
        (RELEASE_GATES_V024, RELEASE_GATES_V024_SHA256),
        (CANDIDATE_EXTRACTOR, CANDIDATE_EXTRACTOR_SHA256),
    ]
    for path, expected in evidence:
        ensure_file(path)
        observed = sha256_file(path)
        if observed != expected:
            raise RuntimeError(f"contract SHA mismatch: {path}: {observed} != {expected}")

    ssot_qc = read_metrics(LATEST_SSOT_UPDATE_QC)
    ssot_required = {
        "audit_status": "PASS",
        "active_pipeline_byte_identical": "true",
        "core_schema_modified": "false",
        "deterministic_250k_scaling_registered": "true",
        "checkpoint_original_claim_supported": "false",
        "checkpoint_replacement_logical_reproducibility": "true",
        "architecture_audit_status": "REVIEW",
        "architecture_audit_blocking_conflicts": "0",
        "release_gates_version": "v0.2.4",
        "full_5_31m_run_started": "false",
        "biology_layer_started": "false",
        "next_gate": "BUILD_DETERMINISTIC_500K_SCALING_WITH_CORRECTED_CHECKPOINT_AND_RUN_ID_CONTRACT",
    }
    for key, expected in ssot_required.items():
        if ssot_qc.get(key) != expected:
            raise RuntimeError(f"current SSOT gate mismatch {key}: {ssot_qc.get(key)}")

    audit = read_metrics(POST250K_AUDIT_QC)
    if (
        audit.get("architecture_audit_status") != "REVIEW"
        or audit.get("blocking_conflicts") != "0"
        or audit.get("replacement_checkpoint_logical_reproducibility") != "true"
    ):
        raise RuntimeError("post-250k architecture audit gate is not clean REVIEW")

    scaling = read_metrics(SCALING_250K_QC)
    required_scaling = {
        "audit_status": "PASS",
        "deterministic_250k_scaling": "PASS",
        "package_exact_raw_reproducibility": "true",
        "package_exact_logical_reproducibility": "true",
        "caller_hashseed_logical_reproducibility": "true",
        "nested_100k_package_exact_parity": "true",
        "full_5_31m_run_started": "false",
    }
    for key, expected in required_scaling.items():
        if scaling.get(key) != expected:
            raise RuntimeError(f"250k scaling gate mismatch {key}: {scaling.get(key)}")

    input_metrics = read_metrics(INPUT_QC)
    input_required = {
        "audit_status": "PASS",
        "subset_fastq_rows": str(BENCHMARK_READS),
        "bam_500k_unique_reads": str(BENCHMARK_READS),
        "nested_250k_alignment_parity": "PASS",
        "mapping_included_in_bam_to_final_timer": "false",
        "active_pipeline_modified": "false",
        "ssot_modified": "false",
        "full_5_31m_run_started": "false",
    }
    for key, expected in input_required.items():
        if input_metrics.get(key) != expected:
            raise RuntimeError(f"500k input gate mismatch {key}: {input_metrics.get(key)}")
    for key in ("subset_fastq", "bam_500k", "bam_500k_bai"):
        path = Path(input_metrics[key])
        ensure_file(path)
        if sha256_file(path) != input_metrics[f"{key}_sha256"]:
            raise RuntimeError(f"500k input artifact SHA mismatch: {path}")
    subprocess.run(["samtools", "quickcheck", "-v", input_metrics["bam_500k"]], check=True)

    for path, expected in SSOT_GUARDS.items():
        ensure_file(path)
        if sha256_file(path) != expected:
            raise RuntimeError(f"SSOT guard mismatch: {path}")
    for path, expected in base.SOURCE_SHA.items():
        ensure_file(path)
        if sha256_file(path) != expected:
            raise RuntimeError(f"run-ID source guard mismatch: {path}")
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
    reference_manifest = REFERENCE_250K_PACKAGE / "package_manifest.tsv"
    ensure_file(reference_manifest)
    if sha256_file(reference_manifest) != REFERENCE_250K_PACKAGE_MANIFEST_SHA256:
        raise RuntimeError("reference 250k package manifest SHA mismatch")
    with reference_manifest.open("r", encoding="utf-8", newline="") as handle:
        manifest_rows = list(csv.DictReader(handle, delimiter="\t"))
    if len(manifest_rows) != 10:
        raise RuntimeError(f"reference 250k package manifest row mismatch: {len(manifest_rows)}")
    for row in manifest_rows:
        path = REFERENCE_250K_PACKAGE / row["artifact"]
        ensure_file(path)
        if path.stat().st_size != int(row["bytes"]):
            raise RuntimeError(f"reference 250k package byte mismatch: {path}")
        if sha256_file(path) != row["sha256"]:
            raise RuntimeError(f"reference 250k package SHA mismatch: {path}")
    for executable in ("samtools", "pigz"):
        if shutil.which(executable) is None:
            raise RuntimeError(f"required executable not found: {executable}")
    if not Path("/usr/bin/time").is_file():
        raise RuntimeError("/usr/bin/time unavailable")
    usage = shutil.disk_usage(PROJECT_ROOT)
    if usage.free < 100 * 1024**3:
        raise RuntimeError(f"insufficient project free space for dual 500k runs: {usage.free}")
    return {path: sha256_file(path) for path in base.ACTIVE_GUARDS}


def create_shards(base):
    shards = base.create_shards(SHARDS)
    for shard in shards:
        bench = shard.raw_root / "benchmarks/ENCSR307SHM/stage15a_500k_seed20260809_v1"
        shard.candidate_fastq = (
            bench / "rnatr_candidates_v0.3.1"
            / "ENCFF260PGB.stage15a_500k.rnatr_candidate_all.fastq.gz"
        )
        setattr(
            shard,
            "full_fastq",
            bench / "stage15a_500k_full"
            / "ENCFF260PGB.stage15a_500k.full.fastq.gz",
        )
        setattr(shard, "candidate_qc", shard.root / "qc/candidate_fastq_extraction.qc.tsv")
        setattr(
            shard,
            "window_fastq",
            bench / "rnatr_projection_v0.3.3"
            / "ENCFF260PGB.stage15a_500k.rnatr_target_windows.v0.3.3.fastq.gz",
        )
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
                    raise RuntimeError(f"duplicate 500k FASTQ read ID: {entry.name}")
                fastq_ids.add(entry.name)
                if entry.quality is None:
                    raise RuntimeError(f"500k FASTQ record lacks quality: {entry.name}")
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
    expected_records = int(input_metrics["bam_500k_alignment_records"])
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
                ("run_id", EXTERNAL_RUN_ID),
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
                "full_fastq_reads": fastq_counts[i],
                "bam_bytes": shard.bam.stat().st_size,
                "full_fastq_bytes": shard.full_fastq.stat().st_size,
                "shard_bai_created": "false",
            }
        )
    write_dict_tsv(base.QC_ROOT / "stage15a_scaling_500k_shards.fast.tsv", rows)
    return {
        "stage": "partition_500k_bam_and_associated_raw_fastq",
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
    write_dict_tsv(base.QC_ROOT / "stage15a_scaling_500k_11b_counts.tsv", rows)
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
    write_dict_tsv(base.QC_ROOT / "stage15a_scaling_500k_candidate_fastq_counts.tsv", rows)
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
    write_dict_tsv(base.QC_ROOT / "stage15a_scaling_500k_projection_job_counts.tsv", rows)
    return total_rows, total_reads



def run_caller_materializer(base, shards, hash_seed: str):
    started = time.perf_counter()

    def one(shard):
        caller = base.run_timed(
            "15AS4_native_caller",
            shard,
            [
                sys.executable,
                str(base.PERF_CALLER),
                "--project-root", str(shard.project),
                "--run-id", EXTERNAL_RUN_ID,
                "--window-fastq", str(shard.window_fastq),
                "--outdir", str(shard.caller_outdir),
                "--workers", str(CALLER_WORKERS_PER_SHARD),
            ],
            env_extra={"PYTHONHASHSEED": hash_seed},
        )
        materializer = base.run_timed(
            "15AS5_materializer",
            shard,
            [
                sys.executable,
                str(base.PERF_MATERIALIZER),
                "--project-root", str(shard.project),
                "--run-id", EXTERNAL_RUN_ID,
                "--calls", str(shard.calls_path),
                "--schema-dir", str(base.SCHEMA_DIR),
                "--outdir", str(shard.package_dir),
                "--sample-id", base.SAMPLE_ID,
            ],
            env_extra={"PYTHONHASHSEED": hash_seed},
        )
        return caller, materializer

    callers = []
    materializers = []
    with cf.ThreadPoolExecutor(max_workers=len(shards)) as pool:
        futures = {pool.submit(one, shard): shard.name for shard in shards}
        for future in cf.as_completed(futures):
            caller, materializer = future.result()
            callers.append(caller)
            materializers.append(materializer)
    wall = time.perf_counter() - started
    callers.sort(key=lambda row: str(row["shard"]))
    materializers.sort(key=lambda row: str(row["shard"]))
    write_dict_tsv(base.QC_ROOT / "15AS4_native_caller.per_shard.tsv", callers)
    write_dict_tsv(base.QC_ROOT / "15AS5_materializer.per_shard.tsv", materializers)
    max_materializer = max(float(row["elapsed_seconds"]) for row in materializers)
    write_metrics(
        base.QC_ROOT / "stage15a_scaling_500k_caller_materializer.qc.tsv",
        [
            ("stage_version", base.STAGE_VERSION),
            ("run_id", EXTERNAL_RUN_ID),
            ("hash_seed", hash_seed),
            ("pipeline_wall_seconds", wall),
            ("max_caller_shard_seconds", max(float(row["elapsed_seconds"]) for row in callers)),
            ("max_materializer_shard_seconds", max_materializer),
            ("shards", len(shards)),
            ("run_id_compatibility_alias_used", "false"),
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
        raise RuntimeError(f"caller errors at 500k: {totals['caller_error_rows']}")
    write_dict_tsv(base.QC_ROOT / "stage15a_scaling_500k_caller_counts.tsv", rows)
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
        base.QC_ROOT / "stage15a_scaling_500k_dynamic_expected_rows.tsv",
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
            ("performance_execution_mode", "500K_READ_COHERENT_SHARDS_GLOBAL_KWAY_MERGE"),
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
    write_dict_tsv(base.QC_ROOT / "stage15a_scaling_500k_caller_full_audit.tsv", rows)


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
    write_dict_tsv(base.QC_ROOT / "stage15a_scaling_500k_full_development_audit.tsv", rows)
    full_caller_audit_dynamic(base, shards, caller_totals)
    elapsed = time.perf_counter() - started
    write_metrics(
        base.QC_ROOT / "stage15a_scaling_500k_post_timer_audit.qc.tsv",
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
                    "role": f"final_package::{path.name}",
                    "shard": ".",
                    "path": str(path),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    manifest = base.QC_ROOT / "stage15a_scaling_500k_checkpoint_manifest.tsv"
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
        base.QC_ROOT / "stage15a_scaling_500k_checkpoint.qc.tsv",
        [
            ("checkpoint_rows", len(rows)),
            ("checkpoint_bytes", sum(int(row["bytes"]) for row in rows)),
            ("checkpoint_manifest_sha256", sha256_file(manifest)),
            ("checkpoint_manifest_integrity", "PASS"),
            ("checkpoint_negative_fixture_rejected", "PASS"),
            ("checkpoint_key_contract", "ROLE_SHARD_WITH_UNIQUE_FINAL_PACKAGE_BASENAME"),
            ("final_package_checkpoint_artifacts", sum(1 for row in rows if str(row["role"]).startswith("final_package::"))),
            ("selective_resume_500k_executed", "false"),
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
    print(f"internal_component_run_id\t{EXTERNAL_RUN_ID}")
    print("run_id_compatibility_alias_used\tfalse")
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
    write_dict_tsv(base.QC_ROOT / "stage15a_scaling_500k_temp_bytes.tsv", temp_rows)
    max_rss = maximum_rss_from_records(all_stage_records)
    listed_seconds = sum(float(row["elapsed_seconds"]) for row in timing_rows)
    projected_minutes = production_seconds * FULL_READS / BENCHMARK_READS / 60.0
    hard = "PASS" if projected_minutes <= 60.0 else "FAIL"
    target = "TARGET_MET" if projected_minutes <= 30.0 else "TARGET_NOT_MET"
    qc_rows = [
        ("stage_version", base.STAGE_VERSION),
        ("external_run_id", EXTERNAL_RUN_ID),
        ("internal_component_run_id", EXTERNAL_RUN_ID),
        ("run_id_compatibility_alias_used", "false"),
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
        ("selective_resume_500k_executed", "false"),
        ("atomic_publication", "PASS"),
        ("conservative_linear_5_31m_projection_minutes", projected_minutes),
        ("five_m_hard_ceiling_60min_projection", hard),
        ("five_m_target_30min_projection", target),
        ("active_pipeline_modified", "false"),
        ("ssot_modified", "false"),
        ("full_5_31m_run_started", "false"),
        ("package_reproducibility", "DEFERRED_TO_REPLICATE_COMPARISON"),
        ("nested_250k_scientific_parity", "DEFERRED_TO_REPLICATE_COMPARISON"),
        ("correctness_status", "PASS"),
        ("performance_implementation_status", "PASS"),
        ("audit_status", "PASS"),
        ("next_gate", "COMPARE_DETERMINISTIC_500K_REPLICATES"),
    ]
    final_qc = base.QC_ROOT / "stage15a_scaling_500k_replicate.qc.tsv"
    write_metrics(final_qc, qc_rows)
    print("===== 500K REPLICATE COMPLETE =====")
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
    write_dict_tsv(QC_BASE / "stage15a_scaling_500k_package_reproducibility.tsv", rows)
    if not all_logical or not all_raw:
        failures = [row["artifact"] for row in rows if row["logical_equal"] != "true" or row["raw_equal"] != "true"]
        raise RuntimeError("500k package reproducibility failed: " + ",".join(map(str, failures)))
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
    write_dict_tsv(QC_BASE / "stage15a_scaling_500k_caller_reproducibility.tsv", rows)
    if not all_equal:
        raise RuntimeError("500k caller reproducibility failed")
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
    ensure_file(ANCHOR_250K_INPUT_QC)
    if sha256_file(ANCHOR_250K_INPUT_QC) != ANCHOR_250K_INPUT_QC_SHA256:
        raise RuntimeError("anchor 250k input QC SHA mismatch")
    input_qc = read_metrics(ANCHOR_250K_INPUT_QC)
    required = {
        "audit_status": "PASS",
        "subset_fastq_rows": "250000",
        "nested_100k_alignment_parity": "PASS",
        "full_5_31m_run_started": "false",
    }
    for key, expected in required.items():
        if input_qc.get(key) != expected:
            raise RuntimeError(f"anchor 250k input gate mismatch {key}: {input_qc.get(key)}")
    path = Path(input_qc["subset_fastq"])
    ensure_file(path)
    if sha256_file(path) != input_qc["subset_fastq_sha256"]:
        raise RuntimeError("anchor 250k subset FASTQ SHA mismatch")
    ids: set[str] = set()
    with pysam.FastxFile(str(path)) as handle:
        for entry in handle:
            if entry.name in ids:
                raise RuntimeError(f"duplicate anchor ID: {entry.name}")
            ids.add(entry.name)
    if len(ids) != 250_000:
        raise RuntimeError(f"anchor ID count mismatch: {len(ids)}")
    return ids


RUN_DERIVED_ID_FIELDS = {
    "general_repeat_calls": {
        "run_id", "caller_record_id", "evidence_id", "repeat_event_id",
        "primary_repeat_call_id",
    },
    "read_evidence": {
        "run_id", "evidence_id", "best_repeat_call_id",
        "best_caller_record_id", "best_repeat_event_id",
    },
    "repeat_events": {
        "run_id", "repeat_event_id", "evidence_id",
        "primary_caller_record_id", "primary_repeat_call_id",
    },
    "repeat_segments": {
        "run_id", "repeat_call_id", "evidence_id",
        "repeat_event_id", "caller_record_id",
    },
    "repeat_interruptions": {
        "run_id", "interruption_id", "caller_record_id", "evidence_id",
        "repeat_event_id", "repeat_call_id",
    },
}

NATURAL_KEYS = {
    "general_repeat_calls": ("projection_id",),
    "read_evidence": ("read_id", "target_region_id", "locus_id", "best_projection_id"),
    "repeat_events": ("read_id", "locus_id", "event_index", "read_start", "read_end"),
    "repeat_segments": (
        "read_id", "locus_id", "segment_index", "read_start", "read_end",
        "canonical_motif",
    ),
    "repeat_interruptions": (
        "read_id", "locus_id", "interruption_index", "read_start", "read_end",
        "sequence",
    ),
}


def normalized_filtered_digest(
    path: Path, table: str, anchor_ids: set[str]
) -> tuple[int, str, str]:
    opener = gzip.open if path.suffix == ".gz" else open
    records = []
    with opener(path, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise RuntimeError(f"missing header: {path}")
        kept_fields = [
            field for field in reader.fieldnames
            if field not in RUN_DERIVED_ID_FIELDS[table]
        ]
        for row in reader:
            if row.get("read_id") not in anchor_ids:
                continue
            records.append(
                tuple(row.get(field, ".") for field in kept_fields)
            )
    key_fields = NATURAL_KEYS[table]
    field_index = {field: i for i, field in enumerate(kept_fields)}
    missing = [field for field in key_fields if field not in field_index]
    if missing:
        raise RuntimeError(f"natural key fields missing {table}: {missing}")
    key_indices = tuple(field_index[field] for field in key_fields)
    records.sort(key=lambda values: tuple(values[i] for i in key_indices))
    h = hashlib.sha256()
    h.update(("\t".join(kept_fields) + "\n").encode("utf-8"))
    for values in records:
        h.update(("\t".join(values) + "\n").encode("utf-8"))
    return len(records), h.hexdigest(), hashlib.sha256(
        ("\t".join(kept_fields) + "\n").encode("utf-8")
    ).hexdigest()


def aggregate_anchor_caller_digest(result_root: Path, anchor_ids: set[str]) -> tuple[int, str, str]:
    rows = []
    header = None
    for shard in sorted((result_root / "shards").glob("shard_*")):
        path = shard / "caller/general_repeat_calls.v0.4.0.tsv.gz"
        ensure_file(path)
        with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if reader.fieldnames is None:
                raise RuntimeError(f"missing caller header: {path}")
            if header is None:
                header = list(reader.fieldnames)
            elif header != list(reader.fieldnames):
                raise RuntimeError("caller headers differ across shards")
            for row in reader:
                if row["read_id"] in anchor_ids:
                    rows.append(tuple(row[field] for field in header))
    if header is None:
        raise RuntimeError("no caller files found")
    projection_index = header.index("projection_id")
    rows.sort(key=lambda values: values[projection_index])
    h = hashlib.sha256()
    h.update(("\t".join(header) + "\n").encode("utf-8"))
    for values in rows:
        h.update(("\t".join(values) + "\n").encode("utf-8"))
    return len(rows), h.hexdigest(), hashlib.sha256(
        ("\t".join(header) + "\n").encode("utf-8")
    ).hexdigest()


def nested_250k_scientific_audit() -> bool:
    anchor_ids = load_anchor_ids()
    candidate_root = RESULT_BASE / "replicate_A"
    reference_root = REFERENCE_250K_RESULT / "replicate_A"

    caller_ref = aggregate_anchor_caller_digest(reference_root, anchor_ids)
    caller_cand = aggregate_anchor_caller_digest(candidate_root, anchor_ids)
    caller_equal = caller_ref == caller_cand
    caller_rows = [{
        "artifact": "general_caller_attempts",
        "reference_anchor_rows": caller_ref[0],
        "candidate_anchor_rows": caller_cand[0],
        "reference_anchor_sha256": caller_ref[1],
        "candidate_anchor_sha256": caller_cand[1],
        "header_sha256_equal": str(caller_ref[2] == caller_cand[2]).lower(),
        "normalized_scientific_equal": str(caller_equal).lower(),
        "comparison_mode": "EXACT_CALLER_ROWS_BY_PROJECTION_ID",
    }]

    package_rows = []
    package_equal = True
    for table in (
        "general_repeat_calls", "read_evidence", "repeat_events",
        "repeat_segments", "repeat_interruptions",
    ):
        ref = REFERENCE_250K_PACKAGE / f"{table}.tsv.gz"
        cand = candidate_root / "package_performance" / f"{table}.tsv.gz"
        ref_digest = normalized_filtered_digest(ref, table, anchor_ids)
        cand_digest = normalized_filtered_digest(cand, table, anchor_ids)
        equal = ref_digest == cand_digest
        package_equal = package_equal and equal
        package_rows.append({
            "table": table,
            "reference_anchor_rows": ref_digest[0],
            "candidate_anchor_rows": cand_digest[0],
            "reference_normalized_sha256": ref_digest[1],
            "candidate_normalized_sha256": cand_digest[1],
            "normalized_header_sha256_equal": str(ref_digest[2] == cand_digest[2]).lower(),
            "run_id_normalized_scientific_equal": str(equal).lower(),
            "comparison_mode": "RUN_ID_AND_RUN_DERIVED_IDS_EXCLUDED_ALL_SCIENTIFIC_FIELDS_EXACT",
        })
    write_dict_tsv(
        QC_BASE / "stage15a_scaling_500k_nested_250k_caller_parity.tsv",
        caller_rows,
    )
    write_dict_tsv(
        QC_BASE / "stage15a_scaling_500k_nested_250k_package_semantic_parity.tsv",
        package_rows,
    )
    all_equal = caller_equal and package_equal
    if not all_equal:
        failed = [
            row["table"] for row in package_rows
            if row["run_id_normalized_scientific_equal"] != "true"
        ]
        if not caller_equal:
            failed.insert(0, "general_caller_attempts")
        raise RuntimeError("nested 250k scientific parity failed: " + ",".join(failed))
    return caller_equal, package_equal


def read_timing(path: Path) -> dict[str, float]:
    rows = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            rows[row["stage"]] = float(row["elapsed_seconds"])
    return rows



def checkpoint_payload_digest(path: Path, role: str) -> tuple[str, str]:
    if role == "materialization_qc" or role == "final_package::materialization.qc.tsv":
        metrics = read_metrics(path)
        kept = {
            key: value
            for key, value in metrics.items()
            if key not in {"stage_version", "performance_stage_version"} and not key.endswith("_seconds")
        }
        payload = json.dumps(kept, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(payload).hexdigest(), "SEMANTIC_METRICS_EXCLUDING_TIMING_AND_STAGE_VERSION"
    if role == "final_package::package_manifest.tsv":
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            required = ["artifact", "table", "rows", "bytes", "sha256", "path"]
            if reader.fieldnames != required:
                raise RuntimeError(f"unexpected package manifest header: {path}: {reader.fieldnames}")
            rows = [
                (row["artifact"], row["table"], row["rows"], row["bytes"], row["sha256"])
                for row in reader
            ]
        rows.sort(key=lambda row: row[0])
        h = hashlib.sha256()
        h.update(b"artifact\ttable\trows\tbytes\tsha256\n")
        for row in rows:
            h.update(("\t".join(row) + "\n").encode("utf-8"))
        return h.hexdigest(), "PACKAGE_MANIFEST_EXCLUDING_REPLICATE_SPECIFIC_PATH"
    if path.suffix == ".gz":
        return logical_sha(path), "DECOMPRESSED_BYTES"
    return sha256_file(path), "RAW_BYTES"


def compare_checkpoint_manifests() -> bool:
    manifests = {}
    for rep in ("A", "B"):
        qc = QC_BASE / f"replicate_{rep}/stage15a_scaling_500k_checkpoint.qc.tsv"
        metrics = read_metrics(qc)
        required = {
            "audit_status": "PASS",
            "checkpoint_manifest_integrity": "PASS",
            "checkpoint_negative_fixture_rejected": "PASS",
            "checkpoint_key_contract": "ROLE_SHARD_WITH_UNIQUE_FINAL_PACKAGE_BASENAME",
            "final_package_checkpoint_artifacts": "12",
        }
        for key, expected in required.items():
            if metrics.get(key) != expected:
                raise RuntimeError(f"checkpoint gate failed replicate={rep} {key}")
        manifest = QC_BASE / f"replicate_{rep}/stage15a_scaling_500k_checkpoint_manifest.tsv"
        ensure_file(manifest)
        if sha256_file(manifest) != metrics["checkpoint_manifest_sha256"]:
            raise RuntimeError(f"checkpoint manifest SHA mismatch replicate={rep}")
        with manifest.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle, delimiter="\t"))
        keyed = {}
        for row in rows:
            key = (row["role"], row["shard"])
            if key in keyed:
                raise RuntimeError(f"duplicate checkpoint key replicate={rep}: {key}")
            path = Path(row["path"])
            ensure_file(path)
            if path.stat().st_size != int(row["bytes"]):
                raise RuntimeError(f"checkpoint byte mismatch: {path}")
            if sha256_file(path) != row["sha256"]:
                raise RuntimeError(f"checkpoint SHA mismatch: {path}")
            keyed[key] = row
        manifests[rep] = keyed

    if set(manifests["A"]) != set(manifests["B"]):
        raise RuntimeError("checkpoint role×shard key sets differ")

    rows = []
    all_equal = True
    raw_differences = 0
    for key in sorted(manifests["A"]):
        role, shard = key
        a = manifests["A"][key]
        b = manifests["B"][key]
        path_a = Path(a["path"])
        path_b = Path(b["path"])
        raw_equal = a["sha256"] == b["sha256"]
        if not raw_equal:
            raw_differences += 1
        logical_a, mode_a = checkpoint_payload_digest(path_a, role)
        logical_b, mode_b = checkpoint_payload_digest(path_b, role)
        if mode_a != mode_b:
            raise RuntimeError(f"checkpoint comparison mode mismatch: {key}")
        logical_equal = logical_a == logical_b
        all_equal = all_equal and logical_equal
        rows.append(
            {
                "role": role,
                "shard": shard,
                "comparison_mode": mode_a,
                "a_raw_sha256": a["sha256"],
                "b_raw_sha256": b["sha256"],
                "raw_equal": str(raw_equal).lower(),
                "a_logical_sha256": logical_a,
                "b_logical_sha256": logical_b,
                "logical_equal": str(logical_equal).lower(),
                "status": "PASS" if logical_equal else "FAIL",
            }
        )
    write_dict_tsv(
        QC_BASE / "stage15a_scaling_500k_checkpoint_logical_reproducibility.tsv",
        rows,
    )
    write_metrics(
        QC_BASE / "stage15a_scaling_500k_checkpoint_reproducibility.qc.tsv",
        [
            ("role_shard_rows", len(rows)),
            ("raw_difference_rows", raw_differences),
            ("logical_difference_rows", sum(row["logical_equal"] != "true" for row in rows)),
            ("checkpoint_logical_reproducibility", str(all_equal).lower()),
            ("original_250k_checker_amendment_applied", "true"),
            ("audit_status", "PASS" if all_equal else "FAIL"),
        ],
    )
    if not all_equal:
        failed = [f"{r['role']}::{r['shard']}" for r in rows if r["logical_equal"] != "true"]
        raise RuntimeError("checkpoint logical reproducibility failed: " + ",".join(failed[:20]))
    return True


def compare_replicates() -> int:
    if COMBINED_QC.exists():
        raise RuntimeError(f"combined QC already exists: {COMBINED_QC}")
    QC_BASE.mkdir(parents=True, exist_ok=True)
    qcs = {}
    for rep in ("A", "B"):
        path = QC_BASE / f"replicate_{rep}/stage15a_scaling_500k_replicate.qc.tsv"
        metrics = read_metrics(path)
        if metrics.get("audit_status") != "PASS":
            raise RuntimeError(f"replicate {rep} not PASS")
        if metrics.get("run_id_compatibility_alias_used") != "false":
            raise RuntimeError(f"replicate {rep} used a run-ID compatibility alias")
        qcs[rep] = metrics

    logical, raw, _ = package_comparison()
    caller_equal = caller_reproducibility()
    checkpoint_equal = compare_checkpoint_manifests()
    nested_caller_equal, nested_package_equal = nested_250k_scientific_audit()
    nested_equal = nested_caller_equal and nested_package_equal

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
    stage_rows = []
    for stage in sorted(set(timing_a) | set(timing_b)):
        a = timing_a.get(stage, 0.0)
        b = timing_b.get(stage, 0.0)
        stage_rows.append({
            "stage": stage,
            "replicate_A_seconds": a,
            "replicate_B_seconds": b,
            "conservative_500k_seconds": max(a, b),
        })
    write_dict_tsv(QC_BASE / "stage15a_scaling_500k_stage_model.tsv", stage_rows)

    counts_keys = [
        "alignment_records", "candidate_rows", "candidate_reads", "projection_rows",
        "total_candidate_window_records", "total_candidate_window_bases",
        "caller_attempt_rows", "caller_called_rows", "caller_no_call_rows",
        "general_repeat_calls_rows", "read_evidence_rows", "repeat_event_rows",
        "repeat_segment_rows", "repeat_interruption_rows",
    ]
    for key in counts_keys:
        if qcs["A"][key] != qcs["B"][key]:
            raise RuntimeError(
                f"replicate complexity mismatch {key}: "
                f"{qcs['A'][key]} != {qcs['B'][key]}"
            )

    baseline_ratio = conservative_seconds / BASELINE_250K_SECONDS
    normalized = (
        (conservative_seconds / BENCHMARK_READS)
        / (BASELINE_250K_SECONDS / 250_000)
    )
    next_gate = (
        "DESIGN_EMPIRICAL_FULL_5_31M_CORE_COMPLETION_RUN_WITH_FULL_SCALE_RESTART_AUDIT"
        if hard == "PASS"
        else "OPTIMIZE_CRITICAL_PATH_BEFORE_FULL_5_31M_CORE_COMPLETION_RUN"
    )

    rows = [
        ("stage_version", VERSION),
        ("run_id", EXTERNAL_RUN_ID),
        ("formal_run_id_contract", "PASS"),
        ("run_id_compatibility_alias_used", "false"),
        ("input_reads", BENCHMARK_READS),
        ("replicate_A_hash_seed", qcs["A"]["python_hash_seed"]),
        ("replicate_B_hash_seed", qcs["B"]["python_hash_seed"]),
        ("replicate_A_bam_to_final_cold_seconds", seconds_a),
        ("replicate_B_bam_to_final_cold_seconds", seconds_b),
        ("conservative_500k_bam_to_final_cold_seconds", conservative_seconds),
        ("replicate_A_warm_equivalent_seconds", warm_a),
        ("replicate_B_warm_equivalent_seconds", warm_b),
        ("runtime_replicate_absolute_difference_seconds", abs(seconds_a - seconds_b)),
        (
            "runtime_replicate_relative_difference",
            abs(seconds_a - seconds_b) / conservative_seconds,
        ),
        ("baseline_250k_seconds", BASELINE_250K_SECONDS),
        ("observed_250k_to_500k_runtime_ratio", baseline_ratio),
        ("ideal_read_count_ratio", 2.0),
        ("per_read_normalized_scaling_factor", normalized),
        ("conservative_linear_5_31m_projection_minutes", projected_minutes),
        ("five_m_hard_ceiling_60min_projection", hard),
        ("five_m_hard_ceiling_margin_minutes", margin),
        ("five_m_target_30min_projection", target),
        ("package_exact_logical_reproducibility", str(logical).lower()),
        ("package_exact_raw_reproducibility", str(raw).lower()),
        ("caller_hashseed_logical_reproducibility", str(caller_equal).lower()),
        ("checkpoint_logical_reproducibility", str(checkpoint_equal).lower()),
        ("nested_250k_scientific_parity", str(nested_equal).lower()),
        ("nested_250k_exact_caller_parity", str(nested_caller_equal).lower()),
        ("nested_250k_run_id_normalized_package_parity", str(nested_package_equal).lower()),
        ("checkpoint_manifest_integrity_500k", "PASS"),
        ("selective_resume_500k_executed", "false"),
        ("full_scale_restart_validated", "false"),
        ("deterministic_500k_scaling", "PASS"),
        ("active_pipeline_modified", "false"),
        ("ssot_modified", "false"),
        ("full_5_31m_run_started", "false"),
        ("core_technical_completion_status", "IN_PROGRESS"),
        ("stage15a_overall_status", "IN_PROGRESS"),
        ("audit_status", "PASS"),
        ("next_gate", next_gate),
    ]
    for key in counts_keys:
        rows.append((key, qcs["A"][key]))
    rows.extend([
        (
            "replicate_A_maximum_observed_stage_rss_kbytes",
            qcs["A"]["maximum_observed_stage_rss_kbytes"],
        ),
        (
            "replicate_B_maximum_observed_stage_rss_kbytes",
            qcs["B"]["maximum_observed_stage_rss_kbytes"],
        ),
        (
            "replicate_A_peak_temporary_and_output_bytes",
            qcs["A"]["peak_temporary_and_output_bytes"],
        ),
        (
            "replicate_B_peak_temporary_and_output_bytes",
            qcs["B"]["peak_temporary_and_output_bytes"],
        ),
    ])
    write_metrics(COMBINED_QC, rows)
    print("===== STAGE 15A DETERMINISTIC 500K SCALING COMPLETE =====")
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
        raise RuntimeError(f"500k scaling root exists; preserve and review: {RESULT_BASE} {QC_BASE}")
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
        failure = QC_BASE / "stage15a_scaling_500k.failure.txt"
        failure.write_text(
            f"stage_version\t{VERSION}\n"
            f"exception_type\t{type(exc).__name__}\n"
            f"exception\t{exc}\n\n{traceback.format_exc()}",
            encoding="utf-8",
        )
        print(f"ERROR: {exc}", file=sys.stderr)
        print(f"FAILURE_RECORD\t{failure}", file=sys.stderr)
        raise
