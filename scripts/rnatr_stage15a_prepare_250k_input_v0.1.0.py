from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import hashlib
import heapq
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import traceback
from collections import defaultdict
from pathlib import Path
from typing import Iterable

import pysam

VERSION = "rnatr_stage15a_prepare_250k_input_v0.1.0"
PROJECT_ROOT_DEFAULT = Path("/mnt/intelssd/rnatr_project")
EXTERNAL_RUN_ID = "ENCSR307SHM_stage15a250k_seed20260808_mm2splice_v1"
INPUT_VERSION = "rnatr_stage15a_250k_input_v0.1.0"
SELECTION_SEED = "rnatr_stage15a_250k_seed20260808_v1"
TOTAL_SELECTED_READS = 250_000
ANCHOR_READS = 100_000
ADDITIONAL_READS = TOTAL_SELECTED_READS - ANCHOR_READS
EXPECTED_FULL_READS = 5_312_696
EXPECTED_FULL_FASTQ_BYTES = 8_995_223_210
EXPECTED_FULL_FASTQ_MD5 = "23270f6b994db147df2f2f4c53f8358b"
ORIGINAL_100K_RUN_ID = "ENCSR307SHM_pilot100k_mm2splice_v1"
ORIGINAL_100K_BAM_SHA256 = "0b1ec4e051ac1067fe7207c076e1eff10e45335b49190902944496a9461300e6"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def md5_file(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def ensure_file(path: Path) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise FileNotFoundError(path)


def parse_paths_env(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    result: dict[str, str] = {}
    for key in ("PROJECT_ROOT", "RAW_ROOT", "CATALOG_ROOT"):
        matches = re.findall(
            rf'^\s*(?:export\s+)?{key}=(?:"|\')?([^"\'\n]+)', text, re.M
        )
        if matches:
            result[key] = os.path.expanduser(os.path.expandvars(matches[-1].strip()))
    return result


def write_metrics(path: Path, rows: Iterable[tuple[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".part")
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["metric", "value"])
        writer.writerows(rows)
    os.replace(tmp, path)


def read_metrics(path: Path) -> dict[str, str]:
    ensure_file(path)
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        header = next(reader, None)
        if header != ["metric", "value"]:
            raise RuntimeError(f"unexpected metrics header: {path}: {header}")
        return {row[0]: row[1] for row in reader if len(row) >= 2}


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


def count_fastq(path: Path, collect_ids: bool = False) -> tuple[int, set[str] | None, int]:
    count = 0
    ids: set[str] | None = set() if collect_ids else None
    total_bases = 0
    with pysam.FastxFile(str(path)) as handle:
        for entry in handle:
            count += 1
            total_bases += len(entry.sequence)
            if ids is not None:
                if entry.name in ids:
                    raise RuntimeError(f"duplicate FASTQ read ID: {entry.name}: {path}")
                ids.add(entry.name)
    return count, ids, total_bases


def deterministic_score(read_id: str) -> int:
    payload = (SELECTION_SEED + "\0" + read_id).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest(), "big")


def load_anchor_ids(anchor_fastq: Path) -> tuple[set[str], int]:
    count, ids, bases = count_fastq(anchor_fastq, collect_ids=True)
    if count != ANCHOR_READS or ids is None or len(ids) != ANCHOR_READS:
        raise RuntimeError(
            f"anchor FASTQ count mismatch: rows={count} unique={0 if ids is None else len(ids)}"
        )
    return ids, bases


def select_additional_ids(
    full_fastq: Path,
    anchor_ids: set[str],
    progress_path: Path,
) -> tuple[set[str], dict[str, int], int, int]:
    # Heap root is the currently largest selected score (stored as negative).
    heap: list[tuple[int, str]] = []
    anchor_found = 0
    full_count = 0
    full_bases = 0
    started = time.perf_counter()
    with pysam.FastxFile(str(full_fastq)) as handle:
        for entry in handle:
            full_count += 1
            full_bases += len(entry.sequence)
            read_id = entry.name
            if read_id in anchor_ids:
                anchor_found += 1
            else:
                score = deterministic_score(read_id)
                item = (-score, read_id)
                if len(heap) < ADDITIONAL_READS:
                    heapq.heappush(heap, item)
                elif score < -heap[0][0]:
                    heapq.heapreplace(heap, item)
            if full_count % 500_000 == 0:
                progress_path.write_text(
                    "metric\tvalue\n"
                    f"records_scanned\t{full_count}\n"
                    f"anchor_found\t{anchor_found}\n"
                    f"additional_heap_size\t{len(heap)}\n"
                    f"elapsed_seconds\t{time.perf_counter() - started:.6f}\n",
                    encoding="utf-8",
                )
                print(
                    f"[250K SELECT] scanned={full_count:,} anchor={anchor_found:,} "
                    f"heap={len(heap):,}",
                    flush=True,
                )
    if full_count != EXPECTED_FULL_READS:
        raise RuntimeError(f"full FASTQ read count mismatch: {full_count} != {EXPECTED_FULL_READS}")
    if anchor_found != ANCHOR_READS:
        raise RuntimeError(f"anchor IDs found in full FASTQ: {anchor_found} != {ANCHOR_READS}")
    if len(heap) != ADDITIONAL_READS:
        raise RuntimeError(f"additional selection size mismatch: {len(heap)}")
    selected_scores = {read_id: -neg_score for neg_score, read_id in heap}
    return set(selected_scores), selected_scores, full_count, full_bases


def write_subset_fastq_and_manifest(
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
    manifest_text = __import__("io").TextIOWrapper(manifest_gz, encoding="utf-8", newline="")
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
                gz.write(f"{header}\n{entry.sequence}\n+\n{entry.quality}\n".encode("utf-8"))
                selection_class = "ANCHOR_100K" if read_id in anchor_ids else "ADDITIONAL_150K"
                score = deterministic_score(read_id)
                if selection_class == "ADDITIONAL_150K" and additional_scores[read_id] != score:
                    raise RuntimeError(f"selection score mismatch for {read_id}")
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
            f"subset FASTQ selected-ID mismatch: missing={len(selected-seen)} extra={len(seen-selected)}"
        )
    os.replace(fastq_tmp, output_fastq)
    os.replace(manifest_tmp, selection_manifest)
    return written, total_bases


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


def run_mapping(
    subset_fastq: Path,
    bam: Path,
    project_root: Path,
    result_root: Path,
    qc_root: Path,
) -> tuple[float, dict[str, str]]:
    refdir = project_root / "refs/gencode_v50"
    ref_mmi = refdir / "GRCh38.primary_assembly.genome.mmi"
    junction_bed = refdir / "junctions/gencode.v50.multi_exon_transcripts.bed12"
    ensure_file(ref_mmi)
    ensure_file(junction_bed)
    for exe in ("minimap2", "samtools"):
        if shutil.which(exe) is None:
            raise RuntimeError(f"required executable unavailable: {exe}")
    if not Path("/usr/bin/time").is_file():
        raise RuntimeError("/usr/bin/time unavailable")

    mapping_dir = bam.parent
    mapping_dir.mkdir(parents=True, exist_ok=True)
    work_dir = result_root / "work/mapping"
    work_dir.mkdir(parents=True, exist_ok=True)
    logs = qc_root / "logs/mapping"
    logs.mkdir(parents=True, exist_ok=True)
    bam_tmp = bam.with_name("." + bam.name + ".part")
    bai_tmp = Path(str(bam_tmp) + ".bai")
    sort_prefix = work_dir / "sorttmp"
    mm2_log = logs / "minimap2.log"
    sort_log = logs / "samtools_sort.log"
    time_v = qc_root / "mapping.time_v.txt"
    command_file = mapping_dir / f"{EXTERNAL_RUN_ID}.mapper_command.sh"

    rg = (
        f"@RG\\tID:{EXTERNAL_RUN_ID}\\tSM:ENCSR307SHM"
        "\\tPL:ONT\\tLB:ONT_cDNA"
    )
    mm2 = [
        "minimap2", "-ax", "splice", "-t", "16",
        "--junc-bed", str(junction_bed),
        "--secondary=yes", "-N", "10", "--MD", "--cs=long",
        "-R", rg, str(ref_mmi), str(subset_fastq),
    ]
    sort = [
        "samtools", "sort", "-@", "8", "-m", "1G",
        "-T", str(sort_prefix), "-o", str(bam_tmp), "-",
    ]
    pipeline = (
        f"{shlex.join(mm2)} 2> {shlex.quote(str(mm2_log))} | "
        f"{shlex.join(sort)} 2> {shlex.quote(str(sort_log))}"
    )
    command_file.write_text(pipeline + "\n", encoding="utf-8")
    started = time.perf_counter()
    proc = subprocess.run(
        ["/usr/bin/time", "-v", "-o", str(time_v), "bash", "-o", "pipefail", "-c", pipeline],
        text=True,
    )
    elapsed = time.perf_counter() - started
    if proc.returncode != 0:
        raise RuntimeError(
            f"250k mapping failed exit={proc.returncode}; logs={mm2_log},{sort_log}"
        )
    subprocess.run(["samtools", "quickcheck", "-v", str(bam_tmp)], check=True)
    subprocess.run(["samtools", "index", "-@", "8", str(bam_tmp), str(bai_tmp)], check=True)
    os.replace(bam_tmp, bam)
    os.replace(bai_tmp, Path(str(bam) + ".bai"))
    return elapsed, parse_time_v(time_v)


def alignment_signature(record: pysam.AlignedSegment) -> tuple[object, ...]:
    tags = tuple(
        sorted(
            (tag, repr(value), value_type)
            for tag, value, value_type in record.get_tags(with_value_type=True)
            if tag != "RG"
        )
    )
    return (
        record.flag,
        record.reference_id,
        record.reference_start,
        record.mapping_quality,
        record.cigarstring or "*",
        record.next_reference_id,
        record.next_reference_start,
        record.template_length,
        record.query_length,
        tags,
    )


def nested_alignment_audit(
    anchor_ids: set[str], original_bam: Path, bam_250k: Path, output: Path
) -> dict[str, object]:
    ensure_file(original_bam)
    if sha256_file(original_bam) != ORIGINAL_100K_BAM_SHA256:
        raise RuntimeError("original 100k BAM SHA mismatch")
    reference: dict[str, list[tuple[object, ...]]] = defaultdict(list)
    with pysam.AlignmentFile(str(original_bam), "rb") as handle:
        for record in handle.fetch(until_eof=True):
            if not record.query_name:
                raise RuntimeError("original BAM record lacks read ID")
            reference[record.query_name].append(alignment_signature(record))
    observed: dict[str, list[tuple[object, ...]]] = defaultdict(list)
    total_records = 0
    all_reads: set[str] = set()
    with pysam.AlignmentFile(str(bam_250k), "rb") as handle:
        for record in handle.fetch(until_eof=True):
            total_records += 1
            if not record.query_name:
                raise RuntimeError("250k BAM record lacks read ID")
            all_reads.add(record.query_name)
            if record.query_name in anchor_ids:
                observed[record.query_name].append(alignment_signature(record))
    missing = sorted(set(reference) - set(observed))
    extra = sorted(set(observed) - set(reference))
    mismatch: list[str] = []
    for read_id in sorted(set(reference) & set(observed)):
        if sorted(reference[read_id], key=repr) != sorted(observed[read_id], key=repr):
            mismatch.append(read_id)
            if len(mismatch) >= 20:
                break
    rows = [
        {
            "metric": "reference_read_ids",
            "value": len(reference),
        },
        {"metric": "observed_anchor_read_ids", "value": len(observed)},
        {"metric": "missing_anchor_read_ids", "value": len(missing)},
        {"metric": "extra_anchor_read_ids", "value": len(extra)},
        {"metric": "alignment_mismatch_read_ids", "value": len(mismatch)},
        {"metric": "bam_250k_alignment_records", "value": total_records},
        {"metric": "bam_250k_unique_reads", "value": len(all_reads)},
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
            f"nested 100k alignment parity failed missing={len(missing)} "
            f"extra={len(extra)} mismatch_examples={mismatch[:10]}"
        )
    if len(all_reads) != TOTAL_SELECTED_READS:
        raise RuntimeError(f"250k BAM unique reads mismatch: {len(all_reads)}")
    return {
        "alignment_records": total_records,
        "unique_reads": len(all_reads),
        "anchor_alignment_parity": "PASS",
    }


def build_artifact_manifest(paths: list[tuple[str, Path]], output: Path) -> None:
    rows = []
    for role, path in paths:
        ensure_file(path)
        rows.append(
            {
                "role": role,
                "path": str(path),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    write_dict_tsv(output, rows)


def validate_reusable(qc_path: Path) -> bool:
    if not qc_path.is_file():
        return False
    metrics = read_metrics(qc_path)
    if metrics.get("audit_status") != "PASS":
        return False
    required = {
        Path(metrics["subset_fastq"]): metrics["subset_fastq_sha256"],
        Path(metrics["bam_250k"]): metrics["bam_250k_sha256"],
        Path(metrics["bam_250k_bai"]): metrics["bam_250k_bai_sha256"],
    }
    for path, expected in required.items():
        ensure_file(path)
        if sha256_file(path) != expected:
            raise RuntimeError(f"reusable input artifact SHA mismatch: {path}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT_DEFAULT)
    args = parser.parse_args()
    project_root = args.project_root.resolve()
    paths_env = project_root / "config/paths.env"
    ensure_file(paths_env)
    env = parse_paths_env(paths_env)
    raw_root = Path(env.get("RAW_ROOT", "/media/tokushimaneuro02/T9/rnatr_data"))

    result_root = project_root / "results/15_stage15a_inputs" / EXTERNAL_RUN_ID / INPUT_VERSION
    qc_root = project_root / "qc/15_stage15a_inputs" / EXTERNAL_RUN_ID / INPUT_VERSION
    qc_path = qc_root / "stage15a_250k_input.qc.tsv"
    if validate_reusable(qc_path):
        print("STAGE15A_250K_INPUT_REUSED_PASS")
        print(f"QC\t{qc_path}")
        return 0
    if result_root.exists() or qc_root.exists():
        raise RuntimeError(
            f"incomplete/nonvalidated 250k input root exists; preserve and review: "
            f"{result_root} {qc_root}"
        )
    result_root.mkdir(parents=True)
    qc_root.mkdir(parents=True)
    (qc_root / "logs").mkdir(parents=True)

    full_fastq = raw_root / "downloads/ENCSR307SHM/ENCFF260PGB.fastq.gz"
    anchor_fastq = (
        raw_root / "benchmarks/ENCSR307SHM/pilot_100k_seed20260803"
        / "ENCFF260PGB.pilot_100k.seed20260803.fastq.gz"
    )
    subset_dir = raw_root / "benchmarks/ENCSR307SHM/stage15a_250k_seed20260808_v1"
    subset_fastq = subset_dir / "ENCFF260PGB.stage15a_250k.seed20260808.fastq.gz"
    selection_manifest = result_root / "selection/stage15a_250k.selection.tsv.gz"
    progress = qc_root / "selection.progress.tsv"
    bam = result_root / "mapping" / f"{EXTERNAL_RUN_ID}.sorted.bam"
    bai = Path(str(bam) + ".bai")
    original_bam = (
        project_root / "results/11_mapping" / ORIGINAL_100K_RUN_ID
        / f"{ORIGINAL_100K_RUN_ID}.sorted.bam"
    )

    for unexpected in (subset_fastq, bam, bai):
        if unexpected.exists():
            raise RuntimeError(
                f"orphan 250k input artifact exists without validated QC; preserve and review: {unexpected}"
            )

    for path in (full_fastq, anchor_fastq, original_bam, Path(str(original_bam) + ".bai")):
        ensure_file(path)
    if full_fastq.stat().st_size != EXPECTED_FULL_FASTQ_BYTES:
        raise RuntimeError(
            f"full FASTQ size mismatch: {full_fastq.stat().st_size} != {EXPECTED_FULL_FASTQ_BYTES}"
        )
    full_md5_started = time.perf_counter()
    observed_md5 = md5_file(full_fastq)
    full_md5_seconds = time.perf_counter() - full_md5_started
    if observed_md5 != EXPECTED_FULL_FASTQ_MD5:
        raise RuntimeError(f"full FASTQ MD5 mismatch: {observed_md5}")

    anchor_ids, anchor_bases = load_anchor_ids(anchor_fastq)
    selection_started = time.perf_counter()
    additional_ids, additional_scores, full_count, full_bases = select_additional_ids(
        full_fastq, anchor_ids, progress
    )
    subset_rows, subset_bases = write_subset_fastq_and_manifest(
        full_fastq,
        anchor_ids,
        additional_ids,
        additional_scores,
        subset_fastq,
        selection_manifest,
    )
    selection_seconds = time.perf_counter() - selection_started
    verified_subset_rows, subset_ids, verified_subset_bases = count_fastq(
        subset_fastq, collect_ids=True
    )
    if (
        verified_subset_rows != TOTAL_SELECTED_READS
        or subset_ids is None
        or len(subset_ids) != TOTAL_SELECTED_READS
        or subset_ids != anchor_ids | additional_ids
        or verified_subset_bases != subset_bases
    ):
        raise RuntimeError("post-write 250k subset verification failed")

    mapping_seconds, mapping_time = run_mapping(
        subset_fastq, bam, project_root, result_root, qc_root
    )
    nested = nested_alignment_audit(
        anchor_ids,
        original_bam,
        bam,
        qc_root / "nested_100k_alignment_parity.tsv",
    )
    subset_sha = sha256_file(subset_fastq)
    bam_sha = sha256_file(bam)
    bai_sha = sha256_file(bai)
    mapper_command = bam.parent / f"{EXTERNAL_RUN_ID}.mapper_command.sh"
    input_manifest = result_root / "stage15a_250k_input.artifact_manifest.tsv"
    build_artifact_manifest(
        [
            ("full_fastq", full_fastq),
            ("anchor_fastq", anchor_fastq),
            ("subset_fastq", subset_fastq),
            ("selection_manifest", selection_manifest),
            ("bam_250k", bam),
            ("bam_250k_bai", bai),
            ("mapper_command", mapper_command),
            ("original_100k_bam", original_bam),
        ],
        input_manifest,
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
        ("full_fastq", full_fastq),
        ("full_fastq_bytes", full_fastq.stat().st_size),
        ("full_fastq_md5", observed_md5),
        ("full_fastq_md5_seconds", full_md5_seconds),
        ("full_fastq_reads", full_count),
        ("full_fastq_bases", full_bases),
        ("anchor_fastq", anchor_fastq),
        ("anchor_fastq_sha256", sha256_file(anchor_fastq)),
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
        ("bam_250k", bam),
        ("bam_250k_sha256", bam_sha),
        ("bam_250k_bai", bai),
        ("bam_250k_bai_sha256", bai_sha),
        ("bam_250k_alignment_records", nested["alignment_records"]),
        ("bam_250k_unique_reads", nested["unique_reads"]),
        ("nested_100k_alignment_parity", nested["anchor_alignment_parity"]),
        ("mapping_seconds", mapping_seconds),
        ("mapping_maximum_resident_set_kbytes", mapping_time.get("Maximum resident set size (kbytes)", ".")),
        ("mapping_included_in_bam_to_final_timer", "false"),
        ("artifact_manifest", input_manifest),
        ("active_pipeline_modified", "false"),
        ("ssot_modified", "false"),
        ("full_5_31m_run_started", "false"),
        ("audit_status", "PASS"),
        ("next_gate", "RUN_DETERMINISTIC_250K_BAM_INPUT_SCALING_REPLICATES"),
    ]
    write_metrics(qc_path, qc_rows)
    print("===== STAGE 15A 250K INPUT PREPARATION COMPLETE =====")
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
