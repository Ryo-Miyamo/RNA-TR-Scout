#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import importlib.util
import os
import shutil
import subprocess
import sys
import time
import traceback
from collections import defaultdict
from pathlib import Path

import pysam

VERSION = "rnatr_stage15a_prepare_500k_input_v0.1.0"
PROJECT_ROOT_DEFAULT = Path("/mnt/intelssd/rnatr_project")
EXTERNAL_RUN_ID = "ENCSR307SHM_stage15a500k_seed20260809_mm2splice_v1"
INPUT_VERSION = "rnatr_stage15a_500k_input_v0.1.0"
SELECTION_SEED = "rnatr_stage15a_500k_seed20260809_v1"
TOTAL_SELECTED_READS = 500_000
ANCHOR_READS = 250_000
ADDITIONAL_READS = 250_000
EXPECTED_FULL_READS = 5_312_696
EXPECTED_FULL_FASTQ_BYTES = 8_995_223_210
EXPECTED_FULL_FASTQ_MD5 = "23270f6b994db147df2f2f4c53f8358b"

HELPER_PATH = Path(
    "/mnt/intelssd/rnatr_project/scripts/"
    "rnatr_stage15a_prepare_250k_input_v0.1.0.py"
)
HELPER_SHA256 = "caab4e711265b1ed7572cfb69fc8b4472b81e2c9270e78b6caee33560e4966bf"

ANCHOR_RUN_ID = "ENCSR307SHM_stage15a250k_seed20260808_mm2splice_v1"
ANCHOR_INPUT_VERSION = "rnatr_stage15a_250k_input_v0.1.0"
ANCHOR_INPUT_QC = (
    PROJECT_ROOT_DEFAULT / "qc/15_stage15a_inputs" / ANCHOR_RUN_ID
    / ANCHOR_INPUT_VERSION / "stage15a_250k_input.qc.tsv"
)
ANCHOR_INPUT_QC_SHA256 = "9e81684ab9afd9a22ab9d2bf96e778fd4b3216a97c5e56ee123c245ae4b2db75"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def ensure_file(path: Path) -> None:
    if not path.is_file() or path.stat().st_size <= 0:
        raise FileNotFoundError(path)


def load_helper():
    ensure_file(HELPER_PATH)
    observed = sha256_file(HELPER_PATH)
    if observed != HELPER_SHA256:
        raise RuntimeError(f"prepare-250k helper SHA mismatch: {observed}")
    spec = importlib.util.spec_from_file_location("rnatr_prepare250k_helper", HELPER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot import prepare-250k helper")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.EXTERNAL_RUN_ID = EXTERNAL_RUN_ID
    module.INPUT_VERSION = INPUT_VERSION
    module.SELECTION_SEED = SELECTION_SEED
    module.TOTAL_SELECTED_READS = TOTAL_SELECTED_READS
    module.ANCHOR_READS = ANCHOR_READS
    module.ADDITIONAL_READS = ADDITIONAL_READS
    module.EXPECTED_FULL_READS = EXPECTED_FULL_READS
    module.EXPECTED_FULL_FASTQ_BYTES = EXPECTED_FULL_FASTQ_BYTES
    module.EXPECTED_FULL_FASTQ_MD5 = EXPECTED_FULL_FASTQ_MD5
    return module


def read_metrics(path: Path) -> dict[str, str]:
    ensure_file(path)
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        header = next(reader, None)
        if header != ["metric", "value"]:
            raise RuntimeError(f"unexpected metric header: {path}: {header}")
        return {row[0]: row[1] for row in reader if len(row) >= 2}


def write_metrics(path: Path, rows: list[tuple[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".part")
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["metric", "value"])
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())
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
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def write_subset_fastq_and_manifest(
    helper,
    full_fastq: Path,
    anchor_ids: set[str],
    additional_ids: set[str],
    additional_scores: dict[str, int],
    output_fastq: Path,
    selection_manifest: Path,
) -> tuple[int, int]:
    selected = anchor_ids | additional_ids
    if len(selected) != TOTAL_SELECTED_READS:
        raise RuntimeError(f"selected ID set mismatch: {len(selected)}")
    output_fastq.parent.mkdir(parents=True, exist_ok=True)
    selection_manifest.parent.mkdir(parents=True, exist_ok=True)
    fastq_tmp = output_fastq.with_name("." + output_fastq.name + ".part")
    manifest_tmp = selection_manifest.with_name("." + selection_manifest.name + ".part")
    written = 0
    total_bases = 0
    seen: set[str] = set()

    raw = fastq_tmp.open("wb")
    gz = gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=1, mtime=0)
    manifest_raw = manifest_tmp.open("wb")
    manifest_gz = gzip.GzipFile(
        filename="", mode="wb", fileobj=manifest_raw, compresslevel=1, mtime=0
    )
    import io
    manifest_text = io.TextIOWrapper(manifest_gz, encoding="utf-8", newline="")
    writer = csv.writer(manifest_text, delimiter="\t", lineterminator="\n")
    writer.writerow(["read_id", "selection_class", "selection_score_sha256_hex"])

    try:
        with pysam.FastxFile(str(full_fastq)) as handle:
            for entry in handle:
                read_id = entry.name
                if read_id not in selected:
                    continue
                if read_id in seen:
                    raise RuntimeError(f"selected read ID occurs more than once: {read_id}")
                seen.add(read_id)
                if entry.quality is None:
                    raise RuntimeError(f"selected FASTQ record lacks quality: {read_id}")
                header = f"@{read_id}" + (f" {entry.comment}" if entry.comment else "")
                gz.write(
                    f"{header}\n{entry.sequence}\n+\n{entry.quality}\n".encode("utf-8")
                )
                selection_class = (
                    "ANCHOR_VALIDATED_250K"
                    if read_id in anchor_ids
                    else "ADDITIONAL_DETERMINISTIC_250K"
                )
                score = helper.deterministic_score(read_id)
                if read_id in additional_ids and additional_scores[read_id] != score:
                    raise RuntimeError(f"selection score mismatch: {read_id}")
                writer.writerow([read_id, selection_class, f"{score:064x}"])
                written += 1
                total_bases += len(entry.sequence)
    finally:
        manifest_text.flush()
        manifest_text.detach()
        manifest_gz.close()
        manifest_raw.close()
        gz.close()
        raw.close()

    if written != TOTAL_SELECTED_READS or len(seen) != TOTAL_SELECTED_READS:
        raise RuntimeError(f"subset FASTQ write count mismatch: {written}/{len(seen)}")
    if seen != selected:
        raise RuntimeError(
            f"subset selected-ID mismatch missing={len(selected-seen)} "
            f"extra={len(seen-selected)}"
        )
    os.replace(fastq_tmp, output_fastq)
    os.replace(manifest_tmp, selection_manifest)
    return written, total_bases


def nested_250k_alignment_audit(
    helper,
    anchor_ids: set[str],
    anchor_bam: Path,
    bam_500k: Path,
    output: Path,
) -> dict[str, object]:
    reference: dict[str, list[tuple[object, ...]]] = defaultdict(list)
    with pysam.AlignmentFile(str(anchor_bam), "rb") as handle:
        for record in handle.fetch(until_eof=True):
            if not record.query_name:
                raise RuntimeError("anchor 250k BAM record lacks read ID")
            reference[record.query_name].append(helper.alignment_signature(record))
    if set(reference) != anchor_ids:
        raise RuntimeError(
            f"anchor FASTQ/BAM ID mismatch: fastq={len(anchor_ids)} bam={len(reference)}"
        )

    observed: dict[str, list[tuple[object, ...]]] = defaultdict(list)
    total_records = 0
    all_reads: set[str] = set()
    with pysam.AlignmentFile(str(bam_500k), "rb") as handle:
        for record in handle.fetch(until_eof=True):
            total_records += 1
            if not record.query_name:
                raise RuntimeError("500k BAM record lacks read ID")
            all_reads.add(record.query_name)
            if record.query_name in anchor_ids:
                observed[record.query_name].append(helper.alignment_signature(record))

    missing = sorted(set(reference) - set(observed))
    extra = sorted(set(observed) - set(reference))
    mismatch: list[str] = []
    for read_id in sorted(set(reference) & set(observed)):
        if sorted(reference[read_id], key=repr) != sorted(observed[read_id], key=repr):
            mismatch.append(read_id)
            if len(mismatch) >= 20:
                break

    rows = [
        {"metric": "reference_anchor_read_ids", "value": len(reference)},
        {"metric": "observed_anchor_read_ids", "value": len(observed)},
        {"metric": "missing_anchor_read_ids", "value": len(missing)},
        {"metric": "extra_anchor_read_ids", "value": len(extra)},
        {"metric": "alignment_mismatch_read_ids", "value": len(mismatch)},
        {"metric": "bam_500k_alignment_records", "value": total_records},
        {"metric": "bam_500k_unique_reads", "value": len(all_reads)},
        {
            "metric": "mismatch_examples",
            "value": ";".join(mismatch[:20]) if mismatch else ".",
        },
        {
            "metric": "audit_status",
            "value": "PASS" if not missing and not extra and not mismatch else "FAIL",
        },
    ]
    write_dict_tsv(output, rows)
    if missing or extra or mismatch:
        raise RuntimeError(
            f"nested 250k alignment parity failed missing={len(missing)} "
            f"extra={len(extra)} mismatch_examples={mismatch[:10]}"
        )
    if len(all_reads) != TOTAL_SELECTED_READS:
        raise RuntimeError(f"500k BAM unique reads mismatch: {len(all_reads)}")
    return {
        "alignment_records": total_records,
        "unique_reads": len(all_reads),
        "anchor_alignment_parity": "PASS",
    }


def validate_reusable(qc_path: Path) -> bool:
    if not qc_path.is_file():
        return False
    metrics = read_metrics(qc_path)
    required_values = {
        "audit_status": "PASS",
        "subset_fastq_rows": str(TOTAL_SELECTED_READS),
        "bam_500k_unique_reads": str(TOTAL_SELECTED_READS),
        "nested_250k_alignment_parity": "PASS",
        "mapping_included_in_bam_to_final_timer": "false",
        "full_5_31m_run_started": "false",
    }
    for key, expected in required_values.items():
        if metrics.get(key) != expected:
            return False
    for key in ("subset_fastq", "bam_500k", "bam_500k_bai"):
        path = Path(metrics[key])
        ensure_file(path)
        if sha256_file(path) != metrics[f"{key}_sha256"]:
            raise RuntimeError(f"reusable input artifact SHA mismatch: {path}")
    subprocess.run(["samtools", "quickcheck", "-v", metrics["bam_500k"]], check=True)
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT_DEFAULT)
    args = parser.parse_args()
    project_root = args.project_root.resolve()
    if project_root != PROJECT_ROOT_DEFAULT:
        raise RuntimeError(f"unexpected project root: {project_root}")

    helper = load_helper()
    paths_env = project_root / "config/paths.env"
    ensure_file(paths_env)
    env = helper.parse_paths_env(paths_env)
    raw_root = Path(env.get("RAW_ROOT", "/media/tokushimaneuro02/T9/rnatr_data"))

    anchor_qc = project_root / ANCHOR_INPUT_QC.relative_to(PROJECT_ROOT_DEFAULT)
    ensure_file(anchor_qc)
    if sha256_file(anchor_qc) != ANCHOR_INPUT_QC_SHA256:
        raise RuntimeError("validated 250k input QC SHA mismatch")
    anchor_metrics = read_metrics(anchor_qc)
    anchor_required = {
        "audit_status": "PASS",
        "subset_fastq_rows": str(ANCHOR_READS),
        "bam_250k_unique_reads": str(ANCHOR_READS),
        "nested_100k_alignment_parity": "PASS",
        "mapping_included_in_bam_to_final_timer": "false",
        "active_pipeline_modified": "false",
        "ssot_modified": "false",
        "full_5_31m_run_started": "false",
    }
    for key, expected in anchor_required.items():
        if anchor_metrics.get(key) != expected:
            raise RuntimeError(
                f"anchor 250k input gate mismatch {key}: {anchor_metrics.get(key)}"
            )

    anchor_fastq = Path(anchor_metrics["subset_fastq"])
    anchor_bam = Path(anchor_metrics["bam_250k"])
    anchor_bai = Path(anchor_metrics["bam_250k_bai"])
    for key, path in (
        ("subset_fastq", anchor_fastq),
        ("bam_250k", anchor_bam),
        ("bam_250k_bai", anchor_bai),
    ):
        ensure_file(path)
        if sha256_file(path) != anchor_metrics[f"{key}_sha256"]:
            raise RuntimeError(f"anchor artifact SHA mismatch: {path}")

    result_root = (
        project_root / "results/15_stage15a_inputs" / EXTERNAL_RUN_ID / INPUT_VERSION
    )
    qc_root = project_root / "qc/15_stage15a_inputs" / EXTERNAL_RUN_ID / INPUT_VERSION
    qc_path = qc_root / "stage15a_500k_input.qc.tsv"
    if validate_reusable(qc_path):
        print("STAGE15A_500K_INPUT_REUSED_PASS")
        print(f"QC\t{qc_path}")
        return 0
    if result_root.exists() or qc_root.exists():
        raise RuntimeError(
            f"incomplete/nonvalidated 500k input root exists; preserve and review: "
            f"{result_root} {qc_root}"
        )

    result_root.mkdir(parents=True)
    qc_root.mkdir(parents=True)
    (qc_root / "logs").mkdir(parents=True)

    full_fastq = raw_root / "downloads/ENCSR307SHM/ENCFF260PGB.fastq.gz"
    subset_dir = raw_root / "benchmarks/ENCSR307SHM/stage15a_500k_seed20260809_v1"
    subset_fastq = subset_dir / "ENCFF260PGB.stage15a_500k.seed20260809.fastq.gz"
    selection_manifest = result_root / "selection/stage15a_500k.selection.tsv.gz"
    progress = qc_root / "selection.progress.tsv"
    bam = result_root / "mapping" / f"{EXTERNAL_RUN_ID}.sorted.bam"
    bai = Path(str(bam) + ".bai")

    for unexpected in (subset_fastq, bam, bai):
        if unexpected.exists():
            raise RuntimeError(
                f"orphan 500k artifact without validated QC; preserve/review: {unexpected}"
            )

    ensure_file(full_fastq)
    if full_fastq.stat().st_size != EXPECTED_FULL_FASTQ_BYTES:
        raise RuntimeError(
            f"full FASTQ size mismatch: {full_fastq.stat().st_size} "
            f"!= {EXPECTED_FULL_FASTQ_BYTES}"
        )
    if shutil.disk_usage(project_root).free < 20 * 1024**3:
        raise RuntimeError("insufficient free space for 500k mapping input")
    if shutil.disk_usage(raw_root).free < 5 * 1024**3:
        raise RuntimeError("insufficient RAW_ROOT free space for 500k subset")

    md5_started = time.perf_counter()
    observed_md5 = helper.md5_file(full_fastq)
    md5_seconds = time.perf_counter() - md5_started
    if observed_md5 != EXPECTED_FULL_FASTQ_MD5:
        raise RuntimeError(f"full FASTQ MD5 mismatch: {observed_md5}")

    anchor_ids, anchor_bases = helper.load_anchor_ids(anchor_fastq)
    selection_started = time.perf_counter()
    additional_ids, additional_scores, full_count, full_bases = (
        helper.select_additional_ids(full_fastq, anchor_ids, progress)
    )
    subset_rows, subset_bases = write_subset_fastq_and_manifest(
        helper,
        full_fastq,
        anchor_ids,
        additional_ids,
        additional_scores,
        subset_fastq,
        selection_manifest,
    )
    selection_seconds = time.perf_counter() - selection_started

    verified_rows, subset_ids, verified_bases = helper.count_fastq(
        subset_fastq, collect_ids=True
    )
    if (
        verified_rows != TOTAL_SELECTED_READS
        or subset_ids is None
        or len(subset_ids) != TOTAL_SELECTED_READS
        or subset_ids != anchor_ids | additional_ids
        or verified_bases != subset_bases
    ):
        raise RuntimeError("post-write 500k subset verification failed")

    mapping_seconds, mapping_time = helper.run_mapping(
        subset_fastq, bam, project_root, result_root, qc_root
    )
    nested = nested_250k_alignment_audit(
        helper,
        anchor_ids,
        anchor_bam,
        bam,
        qc_root / "nested_250k_alignment_parity.tsv",
    )

    subset_sha = sha256_file(subset_fastq)
    bam_sha = sha256_file(bam)
    bai_sha = sha256_file(bai)
    mapper_command = bam.parent / f"{EXTERNAL_RUN_ID}.mapper_command.sh"
    artifact_manifest = result_root / "stage15a_500k_input.artifact_manifest.tsv"
    helper.build_artifact_manifest(
        [
            ("full_fastq", full_fastq),
            ("anchor_250k_fastq", anchor_fastq),
            ("subset_fastq", subset_fastq),
            ("selection_manifest", selection_manifest),
            ("bam_500k", bam),
            ("bam_500k_bai", bai),
            ("mapper_command", mapper_command),
            ("anchor_250k_bam", anchor_bam),
        ],
        artifact_manifest,
    )

    run_manifest = bam.parent / "run_manifest.tsv"
    write_metrics(
        run_manifest,
        [
            ("run_id", EXTERNAL_RUN_ID),
            ("input_version", INPUT_VERSION),
            ("subset_seed", SELECTION_SEED),
            ("input_fastq", subset_fastq),
            ("input_fastq_sha256", subset_sha),
            ("input_reads", TOTAL_SELECTED_READS),
            ("alignment_records", nested["alignment_records"]),
            ("unique_bam_reads", nested["unique_reads"]),
            ("mapper", "minimap2_splice"),
            ("mapping_time_reported_separately", "true"),
            ("audit_status", "PASS"),
        ],
    )

    qc_rows: list[tuple[str, object]] = [
        ("stage_version", VERSION),
        ("run_id", EXTERNAL_RUN_ID),
        ("input_version", INPUT_VERSION),
        ("selection_seed", SELECTION_SEED),
        ("selection_policy", "ALL_VALIDATED_250K_PLUS_DETERMINISTIC_ADDITIONAL_250K"),
        ("full_fastq", full_fastq),
        ("full_fastq_bytes", full_fastq.stat().st_size),
        ("full_fastq_md5", observed_md5),
        ("full_fastq_md5_seconds", md5_seconds),
        ("full_fastq_reads", full_count),
        ("full_fastq_bases", full_bases),
        ("anchor_input_qc", anchor_qc),
        ("anchor_input_qc_sha256", sha256_file(anchor_qc)),
        ("anchor_fastq", anchor_fastq),
        ("anchor_fastq_sha256", sha256_file(anchor_fastq)),
        ("anchor_bam", anchor_bam),
        ("anchor_bam_sha256", sha256_file(anchor_bam)),
        ("anchor_reads", ANCHOR_READS),
        ("anchor_bases", anchor_bases),
        ("additional_selected_reads", ADDITIONAL_READS),
        ("subset_fastq", subset_fastq),
        ("subset_fastq_sha256", subset_sha),
        ("subset_fastq_rows", subset_rows),
        ("subset_fastq_bases", subset_bases),
        ("selection_manifest", selection_manifest),
        ("selection_manifest_sha256", sha256_file(selection_manifest)),
        ("selection_seconds", selection_seconds),
        ("bam_500k", bam),
        ("bam_500k_sha256", bam_sha),
        ("bam_500k_bai", bai),
        ("bam_500k_bai_sha256", bai_sha),
        ("bam_500k_alignment_records", nested["alignment_records"]),
        ("bam_500k_unique_reads", nested["unique_reads"]),
        ("nested_250k_alignment_parity", nested["anchor_alignment_parity"]),
        ("mapping_seconds", mapping_seconds),
        (
            "mapping_maximum_resident_set_kbytes",
            mapping_time.get("Maximum resident set size (kbytes)", "."),
        ),
        ("mapping_included_in_bam_to_final_timer", "false"),
        ("artifact_manifest", artifact_manifest),
        ("active_pipeline_modified", "false"),
        ("ssot_modified", "false"),
        ("full_5_31m_run_started", "false"),
        ("audit_status", "PASS"),
        ("next_gate", "RUN_DETERMINISTIC_500K_BAM_INPUT_SCALING_REPLICATES"),
    ]
    write_metrics(qc_path, qc_rows)
    print("===== STAGE 15A 500K INPUT PREPARATION COMPLETE =====")
    for key, value in qc_rows:
        print(f"{key}\t{value}")
    print(f"QC\t{qc_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        traceback.print_exc()
        raise
