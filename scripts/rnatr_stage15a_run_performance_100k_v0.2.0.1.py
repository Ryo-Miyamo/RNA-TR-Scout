from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import difflib
import gzip
import hashlib
import heapq
import json
import multiprocessing as mp
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

import pysam

STAGE_VERSION = "rnatr_stage15a_sharded_bam_to_final_performance_v0.2.0.1"
PROJECT_ROOT = Path("/mnt/intelssd/rnatr_project")
RUN_ID = "ENCSR307SHM_pilot100k_mm2splice_v1"
SAMPLE_ID = "ENCSR307SHM"
RESULT_ROOT = PROJECT_ROOT / "results/15_stage15a_bam_to_final" / RUN_ID / "v0.2.0.1_performance"
QC_ROOT = PROJECT_ROOT / "qc/15_stage15a_bam_to_final" / RUN_ID / "v0.2.0.1_performance"
LOG_ROOT = QC_ROOT / "logs"
TIMING_ROOT = QC_ROOT / "timing"
COMPARISON_ROOT = QC_ROOT / "comparison"
CONTRACT_ROOT = QC_ROOT / "contract"
MARKER_ROOT = QC_ROOT / "markers"
SHARDS_ROOT = RESULT_ROOT / "shards"
PACKAGE_PART = RESULT_ROOT / "package_performance.part"
PACKAGE_FINAL = RESULT_ROOT / "package_performance"
REFERENCE_ROOT = PROJECT_ROOT / "results/15_stage15a_bam_to_final" / RUN_ID / "v0.1.3"
REFERENCE_QC = PROJECT_ROOT / "qc/15_stage15a_bam_to_final" / RUN_ID / "v0.1.3/stage15a_reference_100k.qc.tsv"
REFERENCE_PACKAGE = REFERENCE_ROOT / "package_reference"
REFERENCE_TIMING = PROJECT_ROOT / "qc/15_stage15a_bam_to_final" / RUN_ID / "v0.1.3/stage15a_reference_timing.tsv"
ORIGINAL_PATHS_ENV = PROJECT_ROOT / "config/paths.env"
BAM = PROJECT_ROOT / "results/11_mapping" / RUN_ID / f"{RUN_ID}.sorted.bam"
BAM_SHA256 = "0b1ec4e051ac1067fe7207c076e1eff10e45335b49190902944496a9461300e6"
SOURCE_11B = PROJECT_ROOT / "scripts/11b_extract_alignment_segments_and_target_candidates.sh"
SOURCE_11D3 = PROJECT_ROOT / "scripts/11d3_project_targets_to_raw_reads_secondary_seq_fixed.sh"
SOURCE_11E = PROJECT_ROOT / "scripts/11e_prepare_motif_scan_jobs.sh"
SOURCE_SHA = {
    SOURCE_11B: "e00bdaad48080d7cfed01e1b961e0617af0f2239e014cd6fe8924460aa9afd56",
    SOURCE_11D3: "9df2998915e49da27ecf80f24a733d55a498c2ba32b278df881fdefa901a83e2",
    SOURCE_11E: "2cc13e2b95711e0d21c05eba1bec3ec26e249d3ec3e80f6ebce4c8157245038a",
}
FROZEN_V03_VALIDATOR = PROJECT_ROOT / "scripts/rnatr_v03_validate_tsv_validator_v0.3.1.py"
FROZEN_V03_VALIDATOR_SHA256 = "10c9d4bbb5c9dac314d400768eb27206173933759c877225bd0ca2c692d8aba9"
CALLER_SOURCE_DRIVER = REFERENCE_ROOT / "frozen_scripts/run_native_v041_100k.stage15a_v0.1.3.py"
CALLER_SOURCE_DRIVER_SHA256 = "4a8fe5115e6697ebb1f3fc8a3d456cc3e2d7a8f63562e6c167dc449564eaf8e8"
ACTIVE_GUARDS = {
    PROJECT_ROOT / "scripts/11b_extract_alignment_segments_and_target_candidates.sh": "e00bdaad48080d7cfed01e1b961e0617af0f2239e014cd6fe8924460aa9afd56",
    PROJECT_ROOT / "scripts/11d3_project_targets_to_raw_reads_secondary_seq_fixed.sh": "9df2998915e49da27ecf80f24a733d55a498c2ba32b278df881fdefa901a83e2",
    PROJECT_ROOT / "scripts/11e_prepare_motif_scan_jobs.sh": "2cc13e2b95711e0d21c05eba1bec3ec26e249d3ec3e80f6ebce4c8157245038a",
    PROJECT_ROOT / "src/rnatr_scout/general_caller/native_v0.4.1/rnatr_general_repeat_caller_ref_v0.4.1.py": "d5a2e0545afa5d97026c3a6ac0be6bc355e87f4c130bc512b0b3bf9a5bf32351",
    PROJECT_ROOT / "src/rnatr_scout/materialization/rnatr_materialize_native_v041_to_evidence_v042_v0.1.2.py": "18a67ef312e74257549570ae81a6cca364055240f519d29dc7664e2ea1c429ea",
    PROJECT_ROOT / "config/evidence_schema/v0.4.2/schema/rnatr_v04_table_schema.json": "c0509a0669344dba0b07cd1bb9e71f2aeb01e0196df47ec9178f1d2464b515f1",
    PROJECT_ROOT / "config/evidence_schema/v0.4.2/rnatr_v042_validate_tsv.py": "10c9d4bbb5c9dac314d400768eb27206173933759c877225bd0ca2c692d8aba9",
    PROJECT_ROOT / "config/evidence_schema/v0.4.2/rnatr_v042_validate_package.py": "45c3995550f57a65b3fec4aab7471d57b7000e19471d4c5cf7f3ae055426984e",
}
SCHEMA_DIR = PROJECT_ROOT / "config/evidence_schema/v0.4.2"
SCHEMA_JSON = SCHEMA_DIR / "schema/rnatr_v04_table_schema.json"
VALIDATOR_TSV = SCHEMA_DIR / "rnatr_v042_validate_tsv.py"
VALIDATOR_PACKAGE = SCHEMA_DIR / "rnatr_v042_validate_package.py"
PERF_CALLER = PROJECT_ROOT / "scripts/rnatr_stage15a_native_v041_no_legacy_audit_v0.2.0.py"
PERF_CALLER_SHA256 = "5b4ab08f51d0318990a321273cf5ba1b5547726c7a037c73bba5aa982788f7ec"
PERF_MATERIALIZER = PROJECT_ROOT / "scripts/rnatr_materialize_native_v041_to_evidence_v042_performance_v0.2.0.py"
PERF_MATERIALIZER_SHA256 = "e36c991f9ff58db9bd6a09a47fe6cd32df5afeae814c7e023050401ea93fa82e"
REFERENCE_SECONDS = 333.981925
FULL_READS = 5_312_696
PIGZ_THREADS_PER_TABLE = 4
EXPECTED_FINAL_ROWS = {
    "general_repeat_calls": 388_571,
    "read_evidence": 388_571,
    "repeat_events": 160_297,
    "repeat_segments": 161_265,
    "repeat_interruptions": 848,
}
TABLE_ORDER = [
    "read_evidence",
    "general_repeat_calls",
    "repeat_events",
    "repeat_segments",
    "repeat_interruptions",
]
KEY_FIELDS = {
    "general_repeat_calls": (("projection_id", False),),
    "read_evidence": (("evidence_id", False),),
    "repeat_events": (("evidence_id", False), ("event_index", True), ("repeat_event_id", False)),
    "repeat_segments": (
        ("evidence_id", False),
        ("repeat_event_id", False),
        ("segment_index", True),
        ("repeat_call_id", False),
    ),
    "repeat_interruptions": (
        ("evidence_id", False),
        ("repeat_event_id", False),
        ("interruption_index", True),
        ("interruption_id", False),
    ),
}


@dataclass
class Shard:
    index: int
    name: str
    root: Path
    project: Path
    raw_root: Path
    bam: Path
    candidate_fastq: Path
    script_11b: Path
    script_11d3: Path
    script_11e: Path
    alignment_records: int = 0
    unique_reads: int = 0
    candidate_fastq_reads: int = 0
    candidate_rows: int = 0
    candidate_reads: int = 0
    projection_rows: int = 0
    projection_reads: int = 0

    @property
    def assignment_path(self) -> Path:
        return self.project / "results/11_assignment" / RUN_ID / "read_target_candidates.tsv.gz"

    @property
    def projection_path(self) -> Path:
        return self.project / "results/11_projection" / RUN_ID / "v0.3.3/read_target_projection.v0.3.3.tsv.gz"

    @property
    def jobs_path(self) -> Path:
        return self.project / "results/11_motif_jobs" / RUN_ID / "motif_scan_jobs.tsv.gz"

    @property
    def caller_outdir(self) -> Path:
        return self.root / "caller"

    @property
    def calls_path(self) -> Path:
        return self.caller_outdir / "general_repeat_calls.v0.4.0.tsv.gz"

    @property
    def package_dir(self) -> Path:
        return self.root / "package_plain"


def utc_now() -> str:
    import datetime as dt

    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


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
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["metric", "value"])
        writer.writerows(rows)


def write_dict_tsv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise RuntimeError(f"refusing empty TSV: {path}")
    fields = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


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


def shard_index(identifier: str, count: int) -> int:
    digest = hashlib.sha256(identifier.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % count


def count_gz_tsv(path: Path, read_field: str | None = None) -> tuple[int, int | None]:
    rows = 0
    reads: set[str] | None = set() if read_field else None
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise RuntimeError(f"missing header: {path}")
        if read_field and read_field not in reader.fieldnames:
            raise RuntimeError(f"missing {read_field}: {path}")
        for row in reader:
            rows += 1
            if reads is not None:
                reads.add(row[read_field])
    return rows, (len(reads) if reads is not None else None)


def gz_tsv_id_set(path: Path, field: str) -> set[str]:
    values: set[str] = set()
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None or field not in reader.fieldnames:
            raise RuntimeError(f"missing {field}: {path}")
        for row in reader:
            value = row[field]
            if value in values:
                continue
            values.add(value)
    return values


def fastq_id_set(path: Path) -> set[str]:
    values: set[str] = set()
    with pysam.FastxFile(str(path)) as source:
        for entry in source:
            if entry.name in values:
                raise RuntimeError(f"duplicate FASTQ read ID in shard: {path}: {entry.name}")
            values.add(entry.name)
    return values


def gz_tsv_order_digest(path: Path, field: str) -> tuple[int, str]:
    count = 0
    digest = hashlib.sha256()
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None or field not in reader.fieldnames:
            raise RuntimeError(f"missing {field}: {path}")
        for row in reader:
            value = row[field]
            digest.update(value.encode("utf-8"))
            digest.update(b"\n")
            count += 1
    return count, digest.hexdigest()


def data_rows(path: Path) -> int:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", newline="") as handle:
        total = sum(1 for _ in handle)
    return max(0, total - 1)


def logical_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    if path.suffix == ".gz":
        with gzip.open(path, "rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    else:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    return digest.hexdigest()


def header_bytes(path: Path) -> bytes:
    if path.suffix == ".gz":
        with gzip.open(path, "rb") as handle:
            return handle.readline()
    with path.open("rb") as handle:
        return handle.readline()


def verify_contract() -> dict[Path, str]:
    reference = read_metrics(REFERENCE_QC)
    required = {
        "audit_status": "PASS",
        "correctness_status": "PASS",
        "stage15a7_package_exact_logical_parity": "true",
        "active_pipeline_modified": "false",
        "ssot_modified": "false",
        "full_5_31m_run_started": "false",
        "next_gate": "BUILD_AND_RUN_STAGE15A_PERFORMANCE_CANDIDATE",
    }
    for key, expected in required.items():
        observed = reference.get(key)
        if observed != expected:
            raise RuntimeError(f"reference gate mismatch {key}: {observed} != {expected}")
    ensure_file(BAM)
    ensure_file(Path(str(BAM) + ".bai"))
    if sha256_file(BAM) != BAM_SHA256:
        raise RuntimeError("target BAM SHA mismatch")
    for path, expected in SOURCE_SHA.items():
        ensure_file(path)
        observed = sha256_file(path)
        if observed != expected:
            raise RuntimeError(f"frozen source SHA mismatch: {path}: {observed}")
    for path, expected in (
        (FROZEN_V03_VALIDATOR, FROZEN_V03_VALIDATOR_SHA256),
        (CALLER_SOURCE_DRIVER, CALLER_SOURCE_DRIVER_SHA256),
        (PERF_CALLER, PERF_CALLER_SHA256),
        (PERF_MATERIALIZER, PERF_MATERIALIZER_SHA256),
    ):
        ensure_file(path)
        observed = sha256_file(path)
        if observed != expected:
            raise RuntimeError(f"Stage 15A performance component SHA mismatch: {path}: {observed}")
    for executable in ("samtools", "pigz"):
        if shutil.which(executable) is None:
            raise RuntimeError(f"required executable not found: {executable}")
    if not Path("/usr/bin/time").is_file():
        raise RuntimeError("required executable not found: /usr/bin/time")
    for path, expected in ACTIVE_GUARDS.items():
        ensure_file(path)
        observed = sha256_file(path)
        if observed != expected:
            raise RuntimeError(f"active guard SHA mismatch: {path}: {observed}")
    for table, expected in EXPECTED_FINAL_ROWS.items():
        for suffix in (".tsv", ".tsv.gz"):
            path = REFERENCE_PACKAGE / f"{table}{suffix}"
            ensure_file(path)
            observed = data_rows(path)
            if observed != expected:
                raise RuntimeError(f"reference row mismatch {path}: {observed} != {expected}")
    usage = shutil.disk_usage(PROJECT_ROOT)
    if usage.free < 15 * 1024**3:
        raise RuntimeError(f"insufficient free space under project root: {usage.free}")
    return {path: sha256_file(path) for path in ACTIVE_GUARDS}


def create_shards(count: int) -> list[Shard]:
    shards: list[Shard] = []
    for index in range(count):
        name = f"shard_{index:03d}"
        root = SHARDS_ROOT / name
        project = root / "project"
        raw_root = root / "raw_root"
        mapping_dir = project / "results/11_mapping" / RUN_ID
        bam = mapping_dir / f"{RUN_ID}.sorted.bam"
        candidate_fastq = (
            raw_root
            / "benchmarks/ENCSR307SHM/pilot_100k_seed20260803"
            / "rnatr_candidates_v0.3.1/ENCFF260PGB.pilot_100k.rnatr_candidate_all.fastq.gz"
        )
        script_dir = root / "frozen_scripts"
        shards.append(
            Shard(
                index=index,
                name=name,
                root=root,
                project=project,
                raw_root=raw_root,
                bam=bam,
                candidate_fastq=candidate_fastq,
                script_11b=script_dir / "11b.stage15a_performance.sh",
                script_11d3=script_dir / "11d3.stage15a_performance.sh",
                script_11e=script_dir / "11e.stage15a_performance.sh",
            )
        )
    return shards


def patch_paths_and_compression(
    source: Path,
    destination: Path,
    paths_env: Path,
    expected_compression_patches: int,
    extra_replacements: tuple[tuple[str, str], ...] = (),
) -> None:
    original = source.read_text(encoding="utf-8")
    text = original
    pattern = re.compile(
        r'^source\s+(?:"[^"\n]*config/paths\.env"|[^\s\n]*config/paths\.env)\s*$',
        re.M,
    )
    text, path_count = pattern.subn(f'source "{paths_env}"', text)
    if path_count != 1:
        raise RuntimeError(f"paths.env patch count {path_count} for {source}")
    text, compression_count = re.subn(
        r'("wt",\n)(\s*)(encoding=)',
        r'\1\2compresslevel=1,\n\2\3',
        text,
    )
    if compression_count != expected_compression_patches:
        raise RuntimeError(
            f"compression patch count {compression_count} != "
            f"{expected_compression_patches}: {source}"
        )
    for old, replacement in extra_replacements:
        count = text.count(old)
        if count != 1:
            raise RuntimeError(
                f"expected one replacement anchor in {source}; found {count}: {old}"
            )
        text = text.replace(old, replacement, 1)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")
    destination.chmod(0o755)
    diff_path = destination.with_suffix(destination.suffix + ".stage15a_v020.diff")
    diff_path.write_text(
        "".join(
            difflib.unified_diff(
                original.splitlines(keepends=True),
                text.splitlines(keepends=True),
                fromfile=str(source),
                tofile=str(destination),
            )
        ),
        encoding="utf-8",
    )
    syntax = subprocess.run(
        ["bash", "-n", str(destination)],
        text=True,
        capture_output=True,
    )
    if syntax.returncode != 0:
        raise RuntimeError(
            f"patched shell syntax failed: {destination}: {syntax.stderr.strip()}"
        )


def setup_shard_files(shards: list[Shard]) -> None:
    host_schema_v03 = PROJECT_ROOT / "config/evidence_schema/v0.3"
    ensure_file(host_schema_v03 / "schema/rnatr_v03_table_schema.json")
    for shard in shards:
        shard.bam.parent.mkdir(parents=True, exist_ok=True)
        shard.candidate_fastq.parent.mkdir(parents=True, exist_ok=True)
        config_dir = shard.project / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        paths_env = config_dir / "paths.env"
        paths_env.write_text(
            "# Stage 15A v0.2.0 read-coherent shard; never source for active runs.\n"
            f"source {ORIGINAL_PATHS_ENV}\n"
            f"export PROJECT_ROOT=\"{shard.project}\"\n"
            f"export RAW_ROOT=\"{shard.raw_root}\"\n"
            f"export CATALOG_ROOT=\"{PROJECT_ROOT / 'catalogs'}\"\n",
            encoding="utf-8",
        )
        schema_parent = shard.project / "config/evidence_schema"
        schema_parent.mkdir(parents=True, exist_ok=True)
        schema_link = schema_parent / "v0.3"
        if schema_link.is_symlink() or schema_link.is_file():
            schema_link.unlink()
        elif schema_link.exists():
            raise RuntimeError(f"refusing to replace non-symlink schema directory: {schema_link}")
        schema_link.symlink_to(host_schema_v03, target_is_directory=True)
        patch_paths_and_compression(
            SOURCE_11B,
            shard.script_11b,
            paths_env,
            3,
            (
                (
                    'VALIDATOR="$SCHEMA_DIR/rnatr_v03_validate_tsv.py"',
                    f'VALIDATOR="{FROZEN_V03_VALIDATOR}"',
                ),
            ),
        )
        patch_paths_and_compression(
            SOURCE_11D3,
            shard.script_11d3,
            paths_env,
            2,
            (
                (
                    "EXPECTED_CANDIDATE_ROWS=388571",
                    'EXPECTED_CANDIDATE_ROWS="${EXPECTED_CANDIDATE_ROWS:-388571}"',
                ),
                (
                    "EXPECTED_CANDIDATE_READS=79176",
                    'EXPECTED_CANDIDATE_READS="${EXPECTED_CANDIDATE_READS:-79176}"',
                ),
            ),
        )
        unsafe_top30 = """    tail -n +2 "$MOTIF_DICTIONARY" |
      sort -t $'\\t' -k4,4nr |
      head -n 30
"""
        safe_top30 = unsafe_top30.replace("head -n 30", "sed -n '1,30p'")
        patch_paths_and_compression(
            SOURCE_11E,
            shard.script_11e,
            paths_env,
            2,
            (
                (
                    "EXPECTED_PROJECTION_ROWS=388571",
                    'EXPECTED_PROJECTION_ROWS="${EXPECTED_PROJECTION_ROWS:-388571}"',
                ),
                (
                    "EXPECTED_PROJECTION_READS=79176",
                    'EXPECTED_PROJECTION_READS="${EXPECTED_PROJECTION_READS:-79176}"',
                ),
                (unsafe_top30, safe_top30),
            ),
        )


def partition_inputs(shards: list[Shard], candidate_fastq_source: Path) -> dict[str, object]:
    started = time.perf_counter()
    writers: list[pysam.AlignmentFile] = []
    read_sets: list[set[str]] = [set() for _ in shards]
    record_counts = [0 for _ in shards]
    with pysam.AlignmentFile(str(BAM), "rb") as source:
        try:
            for shard in shards:
                writers.append(pysam.AlignmentFile(str(shard.bam), "wb", template=source))
            for record in source.fetch(until_eof=True):
                read_id = record.query_name
                if not read_id:
                    raise RuntimeError("BAM record lacks query_name")
                index = shard_index(read_id, len(shards))
                writers[index].write(record)
                record_counts[index] += 1
                read_sets[index].add(read_id)
        finally:
            for writer in writers:
                writer.close()

    def index_bam(shard: Shard) -> None:
        quickcheck = subprocess.run(
            ["samtools", "quickcheck", "-v", str(shard.bam)],
            text=True,
            capture_output=True,
        )
        if quickcheck.returncode != 0:
            raise RuntimeError(
                f"shard BAM quickcheck failed: {shard.bam}: {quickcheck.stderr.strip()}"
            )
        subprocess.run(
            ["samtools", "index", "-@", "2", str(shard.bam)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        ensure_file(Path(str(shard.bam) + ".bai"))

    with cf.ThreadPoolExecutor(max_workers=min(len(shards), 6)) as pool:
        list(pool.map(index_bam, shards))

    raw_files = [shard.candidate_fastq.open("wb") for shard in shards]
    gzip_handles = [
        gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=1, mtime=0)
        for raw in raw_files
    ]
    fastq_counts = [0 for _ in shards]
    candidate_seen: set[str] = set()
    try:
        with pysam.FastxFile(str(candidate_fastq_source)) as source:
            for entry in source:
                if entry.name in candidate_seen:
                    raise RuntimeError(f"duplicate candidate FASTQ read ID: {entry.name}")
                candidate_seen.add(entry.name)
                index = shard_index(entry.name, len(shards))
                header = f"@{entry.name}"
                if entry.comment:
                    header += f" {entry.comment}"
                if entry.quality is None:
                    raise RuntimeError(f"candidate FASTQ record lacks quality: {entry.name}")
                quality = entry.quality
                block = f"{header}\n{entry.sequence}\n+\n{quality}\n".encode("utf-8")
                gzip_handles[index].write(block)
                fastq_counts[index] += 1
    finally:
        for handle in gzip_handles:
            handle.close()
        for raw in raw_files:
            raw.close()

    rows: list[dict[str, object]] = []
    for index, shard in enumerate(shards):
        shard.alignment_records = record_counts[index]
        shard.unique_reads = len(read_sets[index])
        shard.candidate_fastq_reads = fastq_counts[index]
        run_manifest = shard.bam.parent / "run_manifest.tsv"
        run_manifest.write_text(
            "metric\tvalue\n"
            f"run_id\t{RUN_ID}\n"
            f"stage15a_shard\t{shard.name}\n"
            f"source_bam\t{BAM}\n"
            f"alignment_records\t{shard.alignment_records}\n"
            f"unique_reads\t{shard.unique_reads}\n",
            encoding="utf-8",
        )
        rows.append(
            {
                "shard": shard.name,
                "alignment_records": shard.alignment_records,
                "unique_reads": shard.unique_reads,
                "candidate_fastq_reads": shard.candidate_fastq_reads,
                "bam_bytes": shard.bam.stat().st_size,
                "bam_sha256": sha256_file(shard.bam),
                "candidate_fastq_bytes": shard.candidate_fastq.stat().st_size,
                "candidate_fastq_sha256": sha256_file(shard.candidate_fastq),
            }
        )
    if sum(record_counts) != 184_820:
        raise RuntimeError(f"partitioned alignment count mismatch: {sum(record_counts)}")
    total_unique = set().union(*read_sets)
    if len(total_unique) != 100_000 or sum(len(values) for values in read_sets) != 100_000:
        raise RuntimeError("partitioned unique-read count mismatch")
    if len(candidate_seen) != 79_176 or sum(fastq_counts) != 79_176:
        raise RuntimeError(f"partitioned candidate FASTQ count mismatch: {sum(fastq_counts)}")
    write_dict_tsv(QC_ROOT / "stage15a_performance_shards.tsv", rows)
    return {
        "stage": "partition_inputs",
        "elapsed_seconds": time.perf_counter() - started,
        "shards": len(shards),
        "alignment_records": sum(record_counts),
        "unique_reads": sum(len(values) for values in read_sets),
        "candidate_fastq_reads": sum(fastq_counts),
    }


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


def run_timed(label: str, shard: Shard, command: list[str], env_extra: dict[str, str] | None = None) -> dict[str, object]:
    log = LOG_ROOT / label / f"{shard.name}.log"
    timing = TIMING_ROOT / label / f"{shard.name}.time_v.txt"
    log.parent.mkdir(parents=True, exist_ok=True)
    timing.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    if env_extra:
        env.update({key: str(value) for key, value in env_extra.items()})
    started = time.perf_counter()
    with log.open("w", encoding="utf-8") as handle:
        proc = subprocess.run(
            ["/usr/bin/time", "-v", "-o", str(timing), *command],
            stdout=handle,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )
    elapsed = time.perf_counter() - started
    timing_values = parse_time_v(timing)
    record = {
        "stage": label,
        "shard": shard.name,
        "elapsed_seconds": elapsed,
        "exit_code": proc.returncode,
        "maximum_resident_set_kbytes": timing_values.get("Maximum resident set size (kbytes)", "."),
        "log": str(log),
        "command": " ".join(command),
    }
    if proc.returncode != 0:
        tail = "\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-30:])
        raise RuntimeError(f"{label} failed for {shard.name}; log={log}\n{tail}")
    return record


def run_parallel_stage(
    label: str,
    shards: list[Shard],
    command_builder,
    env_builder=None,
) -> tuple[float, list[dict[str, object]]]:
    started = time.perf_counter()
    records: list[dict[str, object]] = []
    errors: list[BaseException] = []
    with cf.ThreadPoolExecutor(max_workers=len(shards)) as pool:
        futures = {
            pool.submit(
                run_timed,
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
    write_dict_tsv(QC_ROOT / f"{label}.per_shard.tsv", records) if records else None
    if errors:
        raise RuntimeError("; ".join(str(error) for error in errors))
    print(f"{label}\tPASS\twall_seconds={wall:.3f}")
    return wall, records


def update_candidate_counts(shards: list[Shard]) -> None:
    audit_rows: list[dict[str, object]] = []
    for shard in shards:
        rows, reads = count_gz_tsv(shard.assignment_path, "read_id")
        shard.candidate_rows = rows
        shard.candidate_reads = int(reads or 0)
        assignment_ids = gz_tsv_id_set(shard.assignment_path, "read_id")
        fastq_ids = fastq_id_set(shard.candidate_fastq)
        set_equal = assignment_ids == fastq_ids
        if not set_equal:
            missing = sorted(assignment_ids - fastq_ids)[:10]
            extra = sorted(fastq_ids - assignment_ids)[:10]
            raise RuntimeError(
                f"candidate FASTQ/read-target ID mismatch in {shard.name}: "
                f"missing={missing} extra={extra}"
            )
        if shard.candidate_reads != shard.candidate_fastq_reads:
            raise RuntimeError(
                f"candidate FASTQ/read-target count mismatch in {shard.name}: "
                f"{shard.candidate_fastq_reads} != {shard.candidate_reads}"
            )
        audit_rows.append(
            {
                "shard": shard.name,
                "candidate_rows": shard.candidate_rows,
                "candidate_reads": shard.candidate_reads,
                "candidate_fastq_reads": shard.candidate_fastq_reads,
                "read_id_set_equal": str(set_equal).lower(),
            }
        )
    if sum(shard.candidate_rows for shard in shards) != 388_571:
        raise RuntimeError("merged 11b candidate row count mismatch")
    if sum(shard.candidate_reads for shard in shards) != 79_176:
        raise RuntimeError("merged 11b candidate-read count mismatch")
    write_dict_tsv(QC_ROOT / "stage15a_performance_11b_fastq_lockstep.tsv", audit_rows)


def update_projection_counts(shards: list[Shard]) -> None:
    audit_rows: list[dict[str, object]] = []
    for shard in shards:
        rows, reads = count_gz_tsv(shard.projection_path, "read_id")
        shard.projection_rows = rows
        shard.projection_reads = int(reads or 0)
        projection_count, projection_order_sha = gz_tsv_order_digest(
            shard.projection_path, "projection_id"
        )
        job_count, job_order_sha = gz_tsv_order_digest(shard.jobs_path, "projection_id")
        order_equal = (
            projection_count == job_count and projection_order_sha == job_order_sha
        )
        if not order_equal:
            raise RuntimeError(f"11e projection/job order lockstep mismatch in {shard.name}")
        job_rows, job_reads = count_gz_tsv(shard.jobs_path, "read_id")
        if job_rows != rows or int(job_reads or 0) != shard.projection_reads:
            raise RuntimeError(f"11e row/read lockstep mismatch in {shard.name}")
        audit_rows.append(
            {
                "shard": shard.name,
                "projection_rows": rows,
                "projection_reads": shard.projection_reads,
                "job_rows": job_rows,
                "job_reads": int(job_reads or 0),
                "projection_order_sha256": projection_order_sha,
                "job_order_sha256": job_order_sha,
                "projection_job_order_equal": str(order_equal).lower(),
            }
        )
    if sum(shard.projection_rows for shard in shards) != 388_571:
        raise RuntimeError("merged projection row count mismatch")
    if sum(shard.projection_reads for shard in shards) != 79_176:
        raise RuntimeError("merged projection-read count mismatch")
    write_dict_tsv(QC_ROOT / "stage15a_performance_11e_lockstep.tsv", audit_rows)


def audit_caller_shards(shards: list[Shard]) -> None:
    rows: list[dict[str, object]] = []
    total_input = 0
    total_called = 0
    total_errors = 0
    total_prior_nonpositive = 0
    for shard in shards:
        qc_path = shard.caller_outdir / "general_repeat_integration.qc.tsv"
        metrics = read_metrics(qc_path)
        if metrics.get("audit_status") != "PASS":
            raise RuntimeError(f"caller shard did not report PASS: {shard.name}")
        input_rows = int(metrics["input_job_rows"])
        called_rows = int(metrics["called_rows"])
        error_rows = int(metrics["caller_error_rows"])
        prior_nonpositive = int(metrics["called_prior_overlap_nonpositive_rows"])
        output_rows = count_gz_tsv(shard.calls_path)[0]
        if input_rows != output_rows:
            raise RuntimeError(
                f"caller input/output row mismatch {shard.name}: {input_rows} != {output_rows}"
            )
        total_input += input_rows
        total_called += called_rows
        total_errors += error_rows
        total_prior_nonpositive += prior_nonpositive
        rows.append(
            {
                "shard": shard.name,
                "input_rows": input_rows,
                "output_rows": output_rows,
                "called_rows": called_rows,
                "caller_error_rows": error_rows,
                "called_prior_overlap_nonpositive_rows": prior_nonpositive,
                "audit_status": metrics["audit_status"],
            }
        )
    expected = (388_571, 160_315, 0, 18)
    observed = (total_input, total_called, total_errors, total_prior_nonpositive)
    if observed != expected:
        raise RuntimeError(f"aggregate caller metric mismatch: {observed} != {expected}")
    write_dict_tsv(QC_ROOT / "stage15a_performance_caller_shards.tsv", rows)


def numeric_key(value: bytes) -> int:
    if value in {b"", b"."}:
        return 0
    return int(value)


def merge_table_plain(table: str, input_paths: list[Path], output_dir: Path) -> dict[str, object]:
    fields_spec = KEY_FIELDS[table]
    handles = [path.open("rb") for path in input_paths]
    try:
        headers = [handle.readline() for handle in handles]
        if not headers or any(header != headers[0] for header in headers):
            raise RuntimeError(f"shard headers differ for {table}")
        header = headers[0]
        if not header.endswith(b"\n"):
            raise RuntimeError(f"unterminated header for {table}")
        field_names = header.rstrip(b"\n").decode("utf-8").split("\t")
        indices: list[tuple[int, bool]] = []
        for name, numeric in fields_spec:
            if name not in field_names:
                raise RuntimeError(f"missing merge key {name} in {table}")
            indices.append((field_names.index(name), numeric))

        previous_by_shard: list[tuple | None] = [None] * len(handles)
        heap: list[tuple[tuple, int, bytes]] = []

        def make_key(line: bytes) -> tuple:
            parts = line.rstrip(b"\n").split(b"\t")
            if len(parts) != len(field_names):
                raise RuntimeError(
                    f"column-count mismatch in {table}: {len(parts)} != {len(field_names)}"
                )
            values: list[object] = []
            for index, numeric in indices:
                raw = parts[index]
                values.append(numeric_key(raw) if numeric else raw)
            return tuple(values)

        def push(index: int) -> None:
            line = handles[index].readline()
            if not line:
                return
            if not line.endswith(b"\n"):
                raise RuntimeError(f"unterminated line in {input_paths[index]}")
            key = make_key(line)
            previous = previous_by_shard[index]
            if previous is not None and key < previous:
                raise RuntimeError(f"unsorted shard materializer output: {input_paths[index]}")
            previous_by_shard[index] = key
            heapq.heappush(heap, (key, index, line))

        for index in range(len(handles)):
            push(index)

        plain = output_dir / f"{table}.tsv"
        plain_tmp = plain.with_name("." + plain.name + ".part")
        row_count = 0
        last_key: tuple | None = None
        digest = hashlib.sha256()
        with plain_tmp.open("wb") as plain_handle:
            plain_handle.write(header)
            digest.update(header)
            while heap:
                key, index, line = heapq.heappop(heap)
                if last_key is not None and key == last_key:
                    raise RuntimeError(f"duplicate global merge key in {table}: {key}")
                last_key = key
                plain_handle.write(line)
                digest.update(line)
                row_count += 1
                push(index)
            plain_handle.flush()
            os.fsync(plain_handle.fileno())
        os.replace(plain_tmp, plain)
        return {
            "table": table,
            "rows": row_count,
            "plain_bytes": plain.stat().st_size,
            "plain_sha256": digest.hexdigest(),
        }
    finally:
        for handle in handles:
            handle.close()


def gzip_table(table: str, output_dir: Path) -> dict[str, object]:
    plain = output_dir / f"{table}.tsv"
    compressed = output_dir / f"{table}.tsv.gz"
    gzip_tmp = compressed.with_name("." + compressed.name + ".part")
    with gzip_tmp.open("wb") as output_handle:
        proc = subprocess.run(
            [
                "pigz",
                "-1",
                "-n",
                "-p",
                str(PIGZ_THREADS_PER_TABLE),
                "-c",
                str(plain),
            ],
            stdout=output_handle,
            stderr=subprocess.PIPE,
            text=False,
        )
        output_handle.flush()
        os.fsync(output_handle.fileno())
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace") if proc.stderr else ""
        raise RuntimeError(f"pigz failed for {table}: {stderr.strip()}")
    os.replace(gzip_tmp, compressed)
    return {
        "table": table,
        "gzip_bytes": compressed.stat().st_size,
        "gzip_sha256": sha256_file(compressed),
        "compression_backend": "pigz_-1_-n",
        "compression_threads": PIGZ_THREADS_PER_TABLE,
    }


def aggregate_materializer_qc(
    shards: list[Shard],
    materializer_wall: float,
    merge_plain_wall: float,
    gzip_wall: float,
) -> list[tuple[str, object]]:
    metrics = [read_metrics(shard.package_dir / "materialization.qc.tsv") for shard in shards]
    if any(row.get("audit_status") != "PASS" for row in metrics):
        raise RuntimeError("one or more shard materializers did not report PASS")
    if any(row.get("caller_suffix_lossless_sha_match") != "true" for row in metrics):
        raise RuntimeError("one or more shard materializers lost caller suffix parity")

    def sum_int(key: str) -> int:
        return sum(int(row[key]) for row in metrics)

    def max_float(key: str) -> float:
        return max(float(row[key]) for row in metrics)

    expected = {
        "input_caller_attempt_rows": EXPECTED_FINAL_ROWS["general_repeat_calls"],
        "projection_rows": EXPECTED_FINAL_ROWS["general_repeat_calls"],
        "evidence_rows": EXPECTED_FINAL_ROWS["read_evidence"],
        "left_flank_uniqueness_not_assessed_rows": EXPECTED_FINAL_ROWS["read_evidence"],
        "right_flank_uniqueness_not_assessed_rows": EXPECTED_FINAL_ROWS["read_evidence"],
        "called_attempt_rows": 160_315,
        "repeat_event_rows": EXPECTED_FINAL_ROWS["repeat_events"],
        "repeat_segment_rows": EXPECTED_FINAL_ROWS["repeat_segments"],
        "repeat_interruption_rows": EXPECTED_FINAL_ROWS["repeat_interruptions"],
        "multi_attempt_evidence_rows": 0,
        "multi_event_evidence_rows": 0,
        "discordance_origin_not_assessed_event_rows": EXPECTED_FINAL_ROWS["repeat_events"],
        "discordance_origin_not_assessed_interruption_rows": EXPECTED_FINAL_ROWS["repeat_interruptions"],
    }
    observed: dict[str, int] = {}
    for key, expected_value in expected.items():
        observed[key] = sum_int(key)
        if observed[key] != expected_value:
            raise RuntimeError(
                f"aggregate materializer metric mismatch {key}: "
                f"{observed[key]} != {expected_value}"
            )
    if any(row.get("cluster_analysis_status") != "NOT_RUN" for row in metrics):
        raise RuntimeError("unexpected cluster analysis status in shard materializer")

    rows: list[tuple[str, object]] = [
        ("stage_version", "rnatr_native_v041_to_evidence_v042_materializer_v0.1.2"),
        ("schema_version", "0.4.2"),
    ]
    rows.extend((key, observed[key]) for key in expected)
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
            ("performance_stage_version", STAGE_VERSION),
            ("performance_execution_mode", "READ_COHERENT_SHARDS_GLOBAL_KWAY_MERGE"),
            ("shard_count", len(shards)),
            ("projection_metadata_reused", "true"),
            ("global_plain_merge_seconds", merge_plain_wall),
            ("global_parallel_gzip_seconds", gzip_wall),
            ("compression_backend", "pigz_-1_-n"),
            ("compression_threads_per_table", PIGZ_THREADS_PER_TABLE),
            ("production_outputs_modified", "false"),
            ("ssot_modified", "false"),
            ("audit_status", "PASS"),
        ]
    )
    return rows


def merge_packages(
    shards: list[Shard], materializer_wall: float
) -> tuple[float, float, float, list[dict[str, object]]]:
    total_started = time.perf_counter()
    PACKAGE_PART.mkdir(parents=True, exist_ok=False)

    merge_started = time.perf_counter()
    process_context = mp.get_context("fork")
    with cf.ProcessPoolExecutor(
        max_workers=len(TABLE_ORDER), mp_context=process_context
    ) as pool:
        futures = {
            pool.submit(
                merge_table_plain,
                table,
                [shard.package_dir / f"{table}.tsv" for shard in shards],
                PACKAGE_PART,
            ): table
            for table in TABLE_ORDER
        }
        plain_rows = [future.result() for future in cf.as_completed(futures)]
    merge_plain_wall = time.perf_counter() - merge_started
    plain_by_table = {str(row["table"]): row for row in plain_rows}
    for table in TABLE_ORDER:
        record = plain_by_table[table]
        expected = EXPECTED_FINAL_ROWS[table]
        if record["rows"] != expected:
            raise RuntimeError(f"merged {table} rows {record['rows']} != {expected}")
        print(f"merge_plain_{table}\tPASS\trows={record['rows']}")

    gzip_started = time.perf_counter()
    with cf.ProcessPoolExecutor(
        max_workers=len(TABLE_ORDER), mp_context=process_context
    ) as pool:
        gzip_rows = list(pool.map(gzip_table, TABLE_ORDER, [PACKAGE_PART] * len(TABLE_ORDER)))
    gzip_wall = time.perf_counter() - gzip_started
    gzip_by_table = {str(row["table"]): row for row in gzip_rows}

    rows: list[dict[str, object]] = []
    for table in TABLE_ORDER:
        combined = dict(plain_by_table[table])
        combined.update(gzip_by_table[table])
        rows.append(combined)

    manifest_rows: list[dict[str, object]] = []
    by_table = {str(row["table"]): row for row in rows}
    for table in TABLE_ORDER:
        record = by_table[table]
        for suffix, bytes_key, sha_key in (
            (".tsv", "plain_bytes", "plain_sha256"),
            (".tsv.gz", "gzip_bytes", "gzip_sha256"),
        ):
            artifact = f"{table}{suffix}"
            manifest_rows.append(
                {
                    "artifact": artifact,
                    "table": table,
                    "rows": record["rows"],
                    "bytes": record[bytes_key],
                    "sha256": record[sha_key],
                    "path": str(PACKAGE_FINAL / artifact),
                }
            )
    write_dict_tsv(PACKAGE_PART / "package_manifest.tsv", manifest_rows)
    write_metrics(
        PACKAGE_PART / "materialization.qc.tsv",
        aggregate_materializer_qc(
            shards,
            materializer_wall=materializer_wall,
            merge_plain_wall=merge_plain_wall,
            gzip_wall=gzip_wall,
        ),
    )
    write_dict_tsv(QC_ROOT / "stage15a_performance_merge.tsv", rows)
    total = time.perf_counter() - total_started
    return total, merge_plain_wall, gzip_wall, rows


def run_generic_validator(table: str) -> dict[str, object]:
    path = PACKAGE_PART / f"{table}.tsv.gz"
    log = LOG_ROOT / "validators" / f"tsv_{table}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
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
    observed = data_rows(path)
    status = "PASS" if proc.returncode == 0 and observed == EXPECTED_FINAL_ROWS[table] else "FAIL"
    return {
        "validator": "rnatr_v042_validate_tsv.py",
        "table": table,
        "elapsed_seconds": elapsed,
        "exit_code": proc.returncode,
        "observed_rows": observed,
        "expected_rows": EXPECTED_FINAL_ROWS[table],
        "status": status,
        "log": str(log),
    }


def run_package_validator_prepublication() -> dict[str, object]:
    log = LOG_ROOT / "validators/package_prepublication.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, str(VALIDATOR_PACKAGE), "--package-dir", str(PACKAGE_PART)]
    started = time.perf_counter()
    proc = subprocess.run(command, text=True, capture_output=True)
    elapsed = time.perf_counter() - started
    log.write_text(proc.stdout + proc.stderr, encoding="utf-8")
    return {
        "validator": "rnatr_v042_validate_package.py",
        "table": "PACKAGE",
        "elapsed_seconds": elapsed,
        "exit_code": proc.returncode,
        "observed_rows": ".",
        "expected_rows": ".",
        "status": "PASS" if proc.returncode == 0 else "FAIL",
        "log": str(log),
    }


def run_all_validators_prepublication() -> tuple[float, list[dict[str, object]]]:
    started = time.perf_counter()
    rows: list[dict[str, object]] = []
    with cf.ThreadPoolExecutor(max_workers=6) as pool:
        futures = [
            pool.submit(run_generic_validator, table) for table in EXPECTED_FINAL_ROWS
        ]
        futures.append(pool.submit(run_package_validator_prepublication))
        for future in cf.as_completed(futures):
            rows.append(future.result())
    wall = time.perf_counter() - started
    rows.sort(key=lambda row: str(row["table"]))
    write_dict_tsv(QC_ROOT / "stage15a_performance_validators.tsv", rows)
    failures = [str(row["table"]) for row in rows if row["status"] != "PASS"]
    if failures:
        raise RuntimeError("one or more frozen validators failed: " + ",".join(failures))
    return wall, rows


def fsync_tree(root: Path) -> None:
    for path in sorted(root.iterdir()):
        if path.is_file():
            with path.open("rb") as handle:
                os.fsync(handle.fileno())
    fd = os.open(root, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def publish_verified_package() -> tuple[float, dict[str, object]]:
    started = time.perf_counter()
    required_names = [
        *(f"{table}.tsv" for table in TABLE_ORDER),
        *(f"{table}.tsv.gz" for table in TABLE_ORDER),
        "package_manifest.tsv",
        "materialization.qc.tsv",
    ]
    before = {}
    for name in required_names:
        path = PACKAGE_PART / name
        ensure_file(path)
        stat = path.stat()
        before[name] = {
            "bytes": stat.st_size,
            "device": stat.st_dev,
            "inode": stat.st_ino,
        }
    fsync_tree(PACKAGE_PART)
    if PACKAGE_FINAL.exists():
        raise RuntimeError(f"final package already exists: {PACKAGE_FINAL}")
    os.replace(PACKAGE_PART, PACKAGE_FINAL)
    parent_fd = os.open(RESULT_ROOT, os.O_RDONLY)
    try:
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)
    for name, fingerprint in before.items():
        path = PACKAGE_FINAL / name
        ensure_file(path)
        stat = path.stat()
        if (
            stat.st_size != fingerprint["bytes"]
            or stat.st_dev != fingerprint["device"]
            or stat.st_ino != fingerprint["inode"]
        ):
            raise RuntimeError(f"post-publication inode fingerprint mismatch: {path}")
    elapsed = time.perf_counter() - started
    row = {
        "publication": "ATOMIC_RENAME_AFTER_ALL_FROZEN_VALIDATORS_PASS",
        "source": str(PACKAGE_PART),
        "destination": str(PACKAGE_FINAL),
        "required_artifacts": len(required_names),
        "post_rename_inode_fingerprint_match": "true",
        "elapsed_seconds": elapsed,
        "status": "PASS",
    }
    write_dict_tsv(QC_ROOT / "stage15a_performance_atomic_publication.tsv", [row])
    return elapsed, row


def compare_package() -> tuple[list[dict[str, object]], bool, bool]:
    rows: list[dict[str, object]] = []
    all_logical = True
    all_raw = True
    for table in EXPECTED_FINAL_ROWS:
        for suffix, kind in ((".tsv", "plain"), (".tsv.gz", "gzip")):
            candidate = PACKAGE_FINAL / f"{table}{suffix}"
            reference = REFERENCE_PACKAGE / f"{table}{suffix}"
            candidate_rows = data_rows(candidate)
            reference_rows = data_rows(reference)
            candidate_raw = sha256_file(candidate)
            reference_raw = sha256_file(reference)
            candidate_logical = logical_sha256(candidate)
            reference_logical = logical_sha256(reference)
            header_equal = header_bytes(candidate) == header_bytes(reference)
            logical_equal = (
                candidate_rows == reference_rows
                and candidate_logical == reference_logical
                and header_equal
            )
            raw_equal = candidate_raw == reference_raw
            all_logical = all_logical and logical_equal
            all_raw = all_raw and raw_equal
            rows.append(
                {
                    "role": f"{table}.{kind}",
                    "candidate_rows": candidate_rows,
                    "reference_rows": reference_rows,
                    "candidate_raw_sha256": candidate_raw,
                    "reference_raw_sha256": reference_raw,
                    "candidate_logical_sha256": candidate_logical,
                    "reference_logical_sha256": reference_logical,
                    "header_equal": str(header_equal).lower(),
                    "raw_equal": str(raw_equal).lower(),
                    "logical_equal": str(logical_equal).lower(),
                    "candidate_path": str(candidate),
                    "reference_path": str(reference),
                }
            )
    write_dict_tsv(COMPARISON_ROOT / "stage15a_performance_package_comparison.tsv", rows)
    if not all_logical:
        failures = [row["role"] for row in rows if row["logical_equal"] != "true"]
        raise RuntimeError("performance package parity failed: " + ",".join(map(str, failures)))
    return rows, all_logical, all_raw


def write_stage_timing(records: list[dict[str, object]]) -> None:
    write_dict_tsv(QC_ROOT / "stage15a_performance_timing.tsv", records)


def verify_active_unchanged(before: dict[Path, str]) -> bool:
    rows: list[dict[str, object]] = []
    okay = True
    for path, before_sha in before.items():
        after_sha = sha256_file(path)
        status = "PASS" if after_sha == before_sha else "FAIL"
        okay = okay and status == "PASS"
        rows.append(
            {
                "path": str(path),
                "before_sha256": before_sha,
                "after_sha256": after_sha,
                "status": status,
            }
        )
    write_dict_tsv(CONTRACT_ROOT / "active_guards_after.tsv", rows)
    if not okay:
        raise RuntimeError("active pipeline guard changed")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shards", type=int, default=6)
    parser.add_argument("--caller-workers-per-shard", type=int, default=4)
    args = parser.parse_args()
    if args.shards < 2 or args.shards > 12:
        raise ValueError("--shards must be between 2 and 12")
    if args.caller_workers_per_shard < 1:
        raise ValueError("--caller-workers-per-shard must be >=1")
    if args.shards * args.caller_workers_per_shard > (os.cpu_count() or 1):
        raise ValueError("caller worker product exceeds visible CPU count")

    if RESULT_ROOT.exists() or QC_ROOT.exists():
        raise RuntimeError(
            f"v0.2.0.1 performance root already exists; preserve it and review before rerun: {RESULT_ROOT}"
        )
    for directory in (RESULT_ROOT, QC_ROOT, LOG_ROOT, TIMING_ROOT, COMPARISON_ROOT, CONTRACT_ROOT, MARKER_ROOT):
        directory.mkdir(parents=True, exist_ok=True)

    overall_started = time.perf_counter()
    print(f"===== {STAGE_VERSION} =====")
    print(f"run_id\t{RUN_ID}")
    print(f"shards\t{args.shards}")
    print(f"caller_workers_per_shard\t{args.caller_workers_per_shard}")
    print("active_pipeline_switch\tPROHIBITED")
    print("full_5_31m_run\tPROHIBITED")
    print("legacy_11f_11h_execution\tOMITTED_AUDIT_ONLY_DEPENDENCY")

    active_before = verify_contract()
    write_dict_tsv(
        CONTRACT_ROOT / "active_guards_before.tsv",
        [
            {"path": str(path), "sha256": digest, "status": "PASS"}
            for path, digest in active_before.items()
        ],
    )
    env_values = parse_paths_env(ORIGINAL_PATHS_ENV)
    raw_root = Path(env_values.get("RAW_ROOT", "/media/tokushimaneuro02/T9/rnatr_data"))
    candidate_fastq_source = (
        raw_root
        / "benchmarks/ENCSR307SHM/pilot_100k_seed20260803"
        / "rnatr_candidates_v0.3.1/ENCFF260PGB.pilot_100k.rnatr_candidate_all.fastq.gz"
    )
    ensure_file(candidate_fastq_source)

    shards = create_shards(args.shards)
    setup_shard_files(shards)
    production_started = time.perf_counter()
    timing_rows: list[dict[str, object]] = []

    partition_record = partition_inputs(shards, candidate_fastq_source)
    timing_rows.append(
        {"stage": "partition_inputs", "elapsed_seconds": partition_record["elapsed_seconds"]}
    )
    print(f"partition_inputs\tPASS\twall_seconds={partition_record['elapsed_seconds']:.3f}")

    wall_11b, per_11b = run_parallel_stage(
        "15AP1_11b",
        shards,
        lambda shard: ["bash", str(shard.script_11b)],
        lambda shard: {
            "EXPECTED_ALIGNMENT_RECORDS": str(shard.alignment_records),
            "EXPECTED_READS": str(shard.unique_reads),
        },
    )
    timing_rows.append({"stage": "15AP1_11b", "elapsed_seconds": wall_11b})
    update_candidate_counts(shards)

    wall_11d3, per_11d3 = run_parallel_stage(
        "15AP2_11d3",
        shards,
        lambda shard: ["bash", str(shard.script_11d3)],
        lambda shard: {
            "EXPECTED_CANDIDATE_ROWS": str(shard.candidate_rows),
            "EXPECTED_CANDIDATE_READS": str(shard.candidate_reads),
        },
    )
    timing_rows.append({"stage": "15AP2_11d3", "elapsed_seconds": wall_11d3})

    wall_11e, per_11e = run_parallel_stage(
        "15AP3_11e",
        shards,
        lambda shard: ["bash", str(shard.script_11e)],
        lambda shard: {
            "EXPECTED_PROJECTION_ROWS": str(shard.candidate_rows),
            "EXPECTED_PROJECTION_READS": str(shard.candidate_reads),
        },
    )
    timing_rows.append({"stage": "15AP3_11e", "elapsed_seconds": wall_11e})
    update_projection_counts(shards)

    wall_caller, per_caller = run_parallel_stage(
        "15AP4_native_caller_no_legacy_audit",
        shards,
        lambda shard: [
            sys.executable,
            str(PERF_CALLER),
            "--project-root",
            str(shard.project),
            "--outdir",
            str(shard.caller_outdir),
            "--workers",
            str(args.caller_workers_per_shard),
        ],
    )
    timing_rows.append({"stage": "15AP4_native_caller_no_legacy_audit", "elapsed_seconds": wall_caller})
    audit_caller_shards(shards)

    wall_materializer, per_materializer = run_parallel_stage(
        "15AP5_materializer_plain_shards",
        shards,
        lambda shard: [
            sys.executable,
            str(PERF_MATERIALIZER),
            "--project-root",
            str(shard.project),
            "--calls",
            str(shard.calls_path),
            "--schema-dir",
            str(SCHEMA_DIR),
            "--outdir",
            str(shard.package_dir),
            "--sample-id",
            SAMPLE_ID,
        ],
    )
    timing_rows.append({"stage": "15AP5_materializer_plain_shards", "elapsed_seconds": wall_materializer})

    merge_wall, merge_plain_wall, gzip_wall, merge_rows = merge_packages(
        shards, materializer_wall=wall_materializer
    )
    timing_rows.append({"stage": "15AP6_parallel_global_merge", "elapsed_seconds": merge_plain_wall})
    timing_rows.append({"stage": "15AP6_parallel_global_gzip", "elapsed_seconds": gzip_wall})
    print(
        f"15AP6_global_merge_and_gzip\tPASS\twall_seconds={merge_wall:.3f}"
        f"\tmerge={merge_plain_wall:.3f}\tgzip={gzip_wall:.3f}"
    )

    validator_wall, validator_rows = run_all_validators_prepublication()
    timing_rows.append(
        {"stage": "15AP7_concurrent_frozen_validators", "elapsed_seconds": validator_wall}
    )
    print(f"15AP7_concurrent_frozen_validators\tPASS\twall_seconds={validator_wall:.3f}")

    publish_wall, publication_row = publish_verified_package()
    timing_rows.append({"stage": "15AP8_atomic_publication", "elapsed_seconds": publish_wall})
    print(f"15AP8_atomic_publication\tPASS\twall_seconds={publish_wall:.3f}")
    production_seconds = time.perf_counter() - production_started

    comparison_started = time.perf_counter()
    comparison_rows, logical_parity, raw_parity = compare_package()
    comparison_seconds = time.perf_counter() - comparison_started
    print(f"reference_package_logical_parity\t{str(logical_parity).lower()}")
    print(f"reference_package_raw_parity\t{str(raw_parity).lower()}")

    verify_active_unchanged(active_before)
    write_stage_timing(timing_rows)
    factor = FULL_READS / 100_000
    projected_minutes = production_seconds * factor / 60.0
    hard_status = "PASS" if projected_minutes <= 60.0 else "FAIL"
    target_status = "TARGET_MET" if projected_minutes <= 30.0 else "TARGET_NOT_MET"
    speedup = REFERENCE_SECONDS / production_seconds
    next_gate = (
        "RUN_STAGE15A_RESTART_AND_LARGER_SCALE_WITHOUT_FULL_5_31M"
        if hard_status == "PASS"
        else "OPTIMIZE_STAGE15A_CRITICAL_PATH_V0.2.1"
    )
    final_rows: list[tuple[str, object]] = [
        ("stage_version", STAGE_VERSION),
        ("run_id", RUN_ID),
        ("reference_v013_correctness", "PASS"),
        ("candidate_graph", "read_hash_partition>parallel_11b>parallel_11d3>parallel_11e>native_v041_no_legacy_audit>parallel_materializer>parallel_global_merge>parallel_global_gzip>concurrent_frozen_tsv_and_package_validation>atomic_publish"),
        ("shard_count", args.shards),
        ("caller_workers_per_shard", args.caller_workers_per_shard),
        ("legacy_11f_11h_executed", "false"),
        ("legacy_11f_11h_role", "AUDIT_ONLY_NOT_SCIENTIFIC_CALL_INPUT"),
        ("scientific_caller_version", "rnatr_general_repeat_caller_ref_v0.4.1"),
        ("materialization_semantics", "rnatr_native_v041_to_evidence_v042_materializer_v0.1.2"),
        ("schema_version", "0.4.2"),
        ("read_coherent_sharding", "true"),
        ("cross_shard_evidence_group_split", "false"),
        ("general_repeat_calls_rows", EXPECTED_FINAL_ROWS["general_repeat_calls"]),
        ("read_evidence_rows", EXPECTED_FINAL_ROWS["read_evidence"]),
        ("repeat_event_rows", EXPECTED_FINAL_ROWS["repeat_events"]),
        ("repeat_segment_rows", EXPECTED_FINAL_ROWS["repeat_segments"]),
        ("repeat_interruption_rows", EXPECTED_FINAL_ROWS["repeat_interruptions"]),
        ("package_exact_logical_parity", str(logical_parity).lower()),
        ("package_exact_raw_parity", str(raw_parity).lower()),
        ("frozen_tsv_validators", "PASS"),
        ("frozen_package_validator_prepublication", "PASS"),
        ("validator_execution", "CONCURRENT_SINGLE_PASS_BEFORE_PUBLICATION"),
        ("atomic_publication", "PASS"),
        ("post_rename_inode_fingerprint_match", "true"),
        ("active_pipeline_modified", "false"),
        ("ssot_modified", "false"),
        ("full_5_31m_run_started", "false"),
        ("reference_bam_to_final_seconds", REFERENCE_SECONDS),
        ("performance_candidate_bam_to_final_seconds", production_seconds),
        ("performance_candidate_speedup", speedup),
        ("development_reference_comparison_seconds", comparison_seconds),
        ("conservative_linear_5_31m_projection_minutes", projected_minutes),
        ("five_m_hard_ceiling_60min", hard_status),
        ("five_m_target_30min", target_status),
        ("correctness_status", "PASS"),
        ("performance_implementation_status", "PASS"),
        ("stage15a_overall_status", "IN_PROGRESS"),
        ("audit_status", "PASS"),
        ("next_gate", next_gate),
        ("overall_development_wall_seconds", time.perf_counter() - overall_started),
    ]
    final_qc = QC_ROOT / "stage15a_performance_100k.qc.tsv"
    write_metrics(final_qc, final_rows)
    print("===== STAGE 15A PERFORMANCE 100K COMPLETE =====")
    for key, value in final_rows:
        print(f"{key}\t{value}")
    print(f"QC\t{final_qc}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        QC_ROOT.mkdir(parents=True, exist_ok=True)
        failure = QC_ROOT / "stage15a_performance_100k.failure.txt"
        failure.write_text(
            f"stage_version\t{STAGE_VERSION}\n"
            f"timestamp_utc\t{utc_now()}\n"
            f"exception_type\t{type(exc).__name__}\n"
            f"exception\t{exc}\n\n"
            + traceback.format_exc(),
            encoding="utf-8",
        )
        print(f"ERROR: {exc}", file=sys.stderr)
        print(f"FAILURE_RECORD\t{failure}", file=sys.stderr)
        raise
