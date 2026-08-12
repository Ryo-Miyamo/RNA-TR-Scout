from __future__ import annotations

import difflib
import hashlib
import re
import sys
from pathlib import Path

EXPECTED_SHA = "18a67ef312e74257549570ae81a6cca364055240f519d29dc7664e2ea1c429ea"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def patch(source: Path, destination: Path, diff_path: Path | None = None) -> None:
    observed = sha256(source)
    if observed != EXPECTED_SHA:
        raise RuntimeError(f"materializer source SHA mismatch: {observed}")
    text = source.read_text(encoding="utf-8")

    start = text.index("def write_plain_tsv(")
    end = text.index("\n\ndef gzip_deterministic", start)
    faster_writer = '''def write_plain_tsv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    """Write byte-identical TSV rows with a lower-overhead positional writer."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".part")
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\\t", lineterminator="\\n")
        writer.writerow(fields)
        for row in rows:
            writer.writerow([fmt(row.get(field, ".")) for field in fields])
    os.replace(tmp, path)
'''
    text = text[:start] + faster_writer + text[end:]

    start = text.index("    # Read metadata are already present in the projection table.")
    end = text.index("    # Evidence groups retain insertion order", start)
    projection_metadata = '''    # Stage 15A performance lane: 11d3 already stores independently audited
    # read length and mean Q in every projection row. Reuse those values and
    # require within-read consistency; do not rescan candidate FASTQ here.
    t_fastq = time.perf_counter()
    fastq_meta: dict[str, tuple[int, str]] = {}
    for projection in projections:
        read_id = projection["read_id"]
        length_text = projection.get("read_length_bp", ".")
        mean_q = projection.get("mean_read_q", ".")
        if not present(length_text):
            raise RuntimeError(
                f"projection lacks audited read length read_id={read_id} "
                f"projection_id={projection.get('projection_id', '.')}"
            )
        value = (int(length_text), mean_q)
        previous = fastq_meta.get(read_id)
        if previous is not None and previous != value:
            raise RuntimeError(
                f"inconsistent projection read metadata read_id={read_id}: "
                f"{previous} != {value}"
            )
        fastq_meta[read_id] = value
    wanted_reads = {row["read_id"] for row in calls}
    missing_projection_metadata = wanted_reads - set(fastq_meta)
    if missing_projection_metadata:
        raise RuntimeError(
            f"projection metadata missing {len(missing_projection_metadata)} caller read IDs"
        )
    fastq_seconds = time.perf_counter() - t_fastq

'''
    text = text[:start] + projection_metadata + text[end:]

    start = text.index("    gzip_start = time.perf_counter()")
    end = text.index("    summary = [", start)
    plain_only = '''    # Per-shard performance output is intentionally plain-only. The Stage 15A
    # merger performs one deterministic global gzip pass and writes the final
    # package manifest after k-way deterministic merge.
    gzip_seconds = 0.0

'''
    text = text[:start] + plain_only + text[end:]

    marker = '("gzip_seconds", gzip_seconds),\n'
    if text.count(marker) != 1:
        raise RuntimeError("materializer summary gzip marker changed")
    text = text.replace(
        marker,
        marker
        + '        ("performance_execution_mode", "SHARDED_PLAIN_ONLY"),\n'
        + '        ("projection_metadata_reused", "true"),\n',
        1,
    )

    if "candidate_fastq" in text or "pysam.FastxFile" in text:
        raise RuntimeError("candidate FASTQ rescan remains after patch")
    if "gzip_deterministic(plain_path" in text:
        raise RuntimeError("per-shard gzip loop remains after patch")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")
    destination.chmod(0o755)
    if diff_path is not None:
        diff_path.parent.mkdir(parents=True, exist_ok=True)
        diff_path.write_text(
            "".join(
                difflib.unified_diff(
                    source.read_text(encoding="utf-8").splitlines(keepends=True),
                    text.splitlines(keepends=True),
                    fromfile=str(source),
                    tofile=str(destination),
                )
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    if len(sys.argv) not in {3, 4}:
        raise SystemExit(f"usage: {sys.argv[0]} SOURCE DESTINATION [DIFF]")
    patch(
        Path(sys.argv[1]),
        Path(sys.argv[2]),
        Path(sys.argv[3]) if len(sys.argv) == 4 else None,
    )
