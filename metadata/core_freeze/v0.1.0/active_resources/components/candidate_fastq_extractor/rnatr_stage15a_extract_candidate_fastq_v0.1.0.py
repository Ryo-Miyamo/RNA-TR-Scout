from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import os
import time
from pathlib import Path

import pysam

VERSION = "rnatr_stage15a_extract_candidate_fastq_v0.1.0"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--assignment", type=Path, required=True)
    parser.add_argument("--input-fastq", type=Path, required=True)
    parser.add_argument("--output-fastq", type=Path, required=True)
    parser.add_argument("--qc", type=Path, required=True)
    parser.add_argument("--expected-rows", type=int, required=True)
    parser.add_argument("--expected-reads", type=int, required=True)
    args = parser.parse_args()

    started = time.perf_counter()
    read_ids: set[str] = set()
    rows = 0
    with gzip.open(args.assignment, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None or "read_id" not in reader.fieldnames:
            raise RuntimeError(f"assignment lacks read_id: {args.assignment}")
        for row in reader:
            rows += 1
            read_ids.add(row["read_id"])
    if rows != args.expected_rows or len(read_ids) != args.expected_reads:
        raise RuntimeError(
            f"assignment count mismatch rows={rows}/{args.expected_rows} "
            f"reads={len(read_ids)}/{args.expected_reads}"
        )

    args.output_fastq.parent.mkdir(parents=True, exist_ok=True)
    args.qc.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.output_fastq.with_name("." + args.output_fastq.name + ".part")
    raw = tmp.open("wb")
    gz = gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=0, mtime=0)
    written_ids: set[str] = set()
    scanned = 0
    bases = 0
    try:
        with pysam.FastxFile(str(args.input_fastq)) as handle:
            for entry in handle:
                scanned += 1
                if entry.name not in read_ids:
                    continue
                if entry.name in written_ids:
                    raise RuntimeError(f"duplicate input FASTQ read ID: {entry.name}")
                if entry.quality is None:
                    raise RuntimeError(f"FASTQ record lacks quality: {entry.name}")
                header = f"@{entry.name}" + (f" {entry.comment}" if entry.comment else "")
                gz.write(
                    f"{header}\n{entry.sequence}\n+\n{entry.quality}\n".encode("utf-8")
                )
                written_ids.add(entry.name)
                bases += len(entry.sequence)
    finally:
        gz.close()
        raw.close()
    if written_ids != read_ids:
        missing = sorted(read_ids - written_ids)[:20]
        extra = sorted(written_ids - read_ids)[:20]
        raise RuntimeError(
            f"candidate FASTQ ID mismatch missing={missing} extra={extra}"
        )
    os.replace(tmp, args.output_fastq)
    elapsed = time.perf_counter() - started
    with args.qc.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["metric", "value"])
        writer.writerows(
            [
                ("stage_version", VERSION),
                ("assignment_rows", rows),
                ("candidate_reads", len(read_ids)),
                ("input_fastq_records_scanned", scanned),
                ("candidate_fastq_records_written", len(written_ids)),
                ("candidate_fastq_bases", bases),
                ("candidate_fastq_bytes", args.output_fastq.stat().st_size),
                ("candidate_fastq_sha256", "DEFERRED_POST_PRODUCTION_AUDIT"),
                ("elapsed_seconds", elapsed),
                ("audit_status", "PASS"),
            ]
        )
    print(f"CANDIDATE_FASTQ_EXTRACTION_PASS\treads={len(read_ids)}\trows={rows}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
