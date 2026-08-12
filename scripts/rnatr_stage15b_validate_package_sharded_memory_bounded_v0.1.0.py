#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import gzip
import hashlib
import os
import shutil
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

VERSION = "rnatr_stage15b_validate_package_sharded_memory_bounded_v0.1.0"
EQUIVALENCE_SCOPE = "STAGE15A_READ_COHERENT_SHARDS_CORE_V042_NO_LOCUS_AGGREGATION"
CORE_TABLES = (
    "read_evidence",
    "general_repeat_calls",
    "repeat_events",
    "repeat_segments",
    "repeat_interruptions",
)
UNIQUE_FIELDS = {
    "read_evidence": "evidence_id",
    "general_repeat_calls": "caller_record_id",
    "repeat_events": "repeat_event_id",
    "repeat_segments": "repeat_call_id",
    "repeat_interruptions": "interruption_id",
}
AGGREGATION_TABLES = (
    "locus_repeat_distributions",
    "repeat_length_clusters",
    "repeat_length_cluster_membership",
)
FROZEN_SHA256 = {
    "rnatr_v04_validate_package.py": "370c93d7730ce919b9c86056f3cd28d49266d41dc34005450d27aaa41d22a96c",
    "rnatr_v041_validate_locus_aggregation.py": "dc29030c2d739c87d2d8e3b6eac493e8cf131b2d7f7e819a7d4435bbcd40b29b",
    "rnatr_v041_validate_package.py": "e978b109d094f665ec62387ffda35c81d0aa9e8156972069f18a1b0b6c49bba5",
    "rnatr_v042_validate_flank_uniqueness.py": "039024835de2bc1f096e562eed69788ecad9e481575b1b8cd58241edf2e87ab5",
    "rnatr_v042_validate_package.py": "45c3995550f57a65b3fec4aab7471d57b7000e19471d4c5cf7f3ae055426984e",
}
PASS_MARKER = "RNATR_V042_PACKAGE_VALIDATION_PASS"


@dataclass(frozen=True)
class ShardResult:
    shard: str
    package_dir: str
    elapsed_seconds: float
    maximum_resident_set_kbytes: int
    exit_code: int
    marker_present: bool
    status: str
    stdout_log: str
    stderr_log: str
    time_log: str


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def logical_sha256(path: Path) -> str:
    h = hashlib.sha256()
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def atomic_write_tsv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".part")
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


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


def ensure_nonempty(path: Path) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"missing or empty file: {path}")


def verify_frozen_sources(schema_dir: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for name, expected in FROZEN_SHA256.items():
        path = schema_dir / name
        ensure_nonempty(path)
        observed = sha256_file(path)
        status = "PASS" if observed == expected else "FAIL"
        rows.append({
            "component": name,
            "path": str(path),
            "expected_sha256": expected,
            "observed_sha256": observed,
            "status": status,
        })
        if status != "PASS":
            raise RuntimeError(f"frozen validator SHA mismatch: {path}: {observed} != {expected}")
    return rows


def package_core_paths(package_dir: Path) -> dict[str, Path]:
    paths = {table: package_dir / f"{table}.tsv" for table in CORE_TABLES}
    for path in paths.values():
        ensure_nonempty(path)
    return paths


def check_core_aggregation_absent(package_dir: Path) -> None:
    present: list[str] = []
    for table in AGGREGATION_TABLES:
        for suffix in (".tsv", ".tsv.gz"):
            if (package_dir / f"{table}{suffix}").exists():
                present.append(f"{table}{suffix}")
    if present:
        raise RuntimeError(
            "core memory-bounded validator v0.1.0 requires locus aggregation NOT_RUN; "
            f"unexpected aggregate artifacts in {package_dir}: {','.join(sorted(present))}"
        )


def discover_shard_packages(shards_root: Path, expected_shards: int | None) -> list[Path]:
    if not shards_root.is_dir():
        raise RuntimeError(f"shards root missing: {shards_root}")
    candidates = sorted(shards_root.glob("shard_*/package_plain"))
    if not candidates:
        candidates = sorted(shards_root.glob("shard_*/package_performance"))
    if not candidates:
        raise RuntimeError(f"no shard package directories found under {shards_root}")
    if expected_shards is not None and len(candidates) != expected_shards:
        raise RuntimeError(f"shard count mismatch: {len(candidates)} != {expected_shards}")
    for package in candidates:
        package_core_paths(package)
        check_core_aggregation_absent(package)
    return candidates


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


def run_one_shard(
    package_dir: Path,
    validator: Path,
    log_root: Path,
    python_executable: str,
) -> ShardResult:
    shard = package_dir.parent.name
    shard_log = log_root / shard
    shard_log.mkdir(parents=True, exist_ok=False)
    stdout_log = shard_log / "frozen_v042.stdout.log"
    stderr_log = shard_log / "frozen_v042.stderr.log"
    time_log = shard_log / "frozen_v042.time_v.txt"
    command = [
        "/usr/bin/time", "-v", "-o", str(time_log),
        python_executable, str(validator), "--package-dir", str(package_dir),
    ]
    started = time.perf_counter()
    proc = subprocess.run(command, text=True, capture_output=True)
    elapsed = time.perf_counter() - started
    stdout_log.write_text(proc.stdout, encoding="utf-8")
    stderr_log.write_text(proc.stderr, encoding="utf-8")
    time_values = parse_time_v(time_log)
    rss = int(time_values.get("Maximum resident set size (kbytes)", "0") or 0)
    marker = PASS_MARKER in proc.stdout
    status = "PASS" if proc.returncode == 0 and marker else "FAIL"
    return ShardResult(
        shard=shard,
        package_dir=str(package_dir),
        elapsed_seconds=elapsed,
        maximum_resident_set_kbytes=rss,
        exit_code=proc.returncode,
        marker_present=marker,
        status=status,
        stdout_log=str(stdout_log),
        stderr_log=str(stderr_log),
        time_log=str(time_log),
    )


def validate_shards(
    shard_packages: list[Path],
    schema_dir: Path,
    output_dir: Path,
    workers: int,
    python_executable: str,
) -> tuple[float, list[ShardResult]]:
    validator = schema_dir / "rnatr_v042_validate_package.py"
    log_root = output_dir / "shard_validator_logs"
    log_root.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    results: list[ShardResult] = []
    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(run_one_shard, package, validator, log_root, python_executable): package
            for package in shard_packages
        }
        for future in cf.as_completed(futures):
            results.append(future.result())
    elapsed = time.perf_counter() - started
    results.sort(key=lambda row: row.shard)
    rows = [
        {
            "shard": row.shard,
            "package_dir": row.package_dir,
            "elapsed_seconds": f"{row.elapsed_seconds:.9f}",
            "maximum_resident_set_kbytes": row.maximum_resident_set_kbytes,
            "exit_code": row.exit_code,
            "marker_present": str(row.marker_present).lower(),
            "status": row.status,
            "stdout_log": row.stdout_log,
            "stderr_log": row.stderr_log,
            "time_log": row.time_log,
        }
        for row in results
    ]
    atomic_write_tsv(
        output_dir / "shard_frozen_v042_validation.tsv",
        list(rows[0].keys()) if rows else ["shard"],
        rows,
    )
    failures = [row.shard for row in results if row.status != "PASS"]
    if failures:
        raise RuntimeError("one or more shard frozen v0.4.2 validators failed: " + ",".join(failures))
    return elapsed, results


def read_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        line = handle.readline()
    if not line:
        raise RuntimeError(f"empty TSV: {path}")
    if not line.endswith("\n"):
        raise RuntimeError(f"unterminated TSV header: {path}")
    return line.rstrip("\n").split("\t")


def wc_lines(path: Path) -> int:
    proc = subprocess.run(["wc", "-l", str(path)], text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"wc failed for {path}: {proc.stderr.strip()}")
    return int(proc.stdout.split()[0])


def global_unique_check(
    table: str,
    field: str,
    shard_paths: list[Path],
    work_root: Path,
    sort_buffer: str,
) -> dict[str, object]:
    started = time.perf_counter()
    headers = [read_header(path) for path in shard_paths]
    if any(header != headers[0] for header in headers[1:]):
        raise RuntimeError(f"shard header mismatch for {table}")
    header = headers[0]
    if field not in header:
        raise RuntimeError(f"unique field {field} missing from {table}")
    column = header.index(field) + 1

    table_work = work_root / table
    table_work.mkdir(parents=True, exist_ok=False)
    unsorted_ids = table_work / f"{field}.unsorted.txt"
    sorted_ids = table_work / f"{field}.sorted.txt"
    awk_program = "FNR>1 {print $col}"
    with unsorted_ids.open("wb") as output:
        proc = subprocess.run(
            ["awk", "-F", "\t", "-v", f"col={column}", awk_program, *map(str, shard_paths)],
            stdout=output,
            stderr=subprocess.PIPE,
        )
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace") if proc.stderr else ""
        raise RuntimeError(f"ID extraction failed for {table}: {stderr.strip()}")
    extracted_rows = wc_lines(unsorted_ids)

    env = os.environ.copy()
    env["LC_ALL"] = "C"
    sort_temp = table_work / "sort_tmp"
    sort_temp.mkdir()
    sort_started = time.perf_counter()
    proc = subprocess.run(
        [
            "sort", "--buffer-size", sort_buffer,
            "--temporary-directory", str(sort_temp),
            "--output", str(sorted_ids),
            str(unsorted_ids),
        ],
        text=True,
        capture_output=True,
        env=env,
    )
    sort_seconds = time.perf_counter() - sort_started
    if proc.returncode != 0:
        raise RuntimeError(f"external sort failed for {table}: {proc.stderr.strip()}")

    duplicate = None
    counted = 0
    previous: bytes | None = None
    with sorted_ids.open("rb") as handle:
        for line in handle:
            value = line[:-1] if line.endswith(b"\n") else line
            if previous is not None and value == previous:
                duplicate = value.decode("utf-8", errors="replace")
                break
            previous = value
            counted += 1
    if duplicate is None and counted != extracted_rows:
        raise RuntimeError(f"sorted ID row count mismatch for {table}: {counted} != {extracted_rows}")
    temp_peak = max(unsorted_ids.stat().st_size, sorted_ids.stat().st_size)
    shutil.rmtree(table_work)
    elapsed = time.perf_counter() - started
    if duplicate is not None:
        raise RuntimeError(f"duplicate {table} {field}: {duplicate}")
    return {
        "table": table,
        "unique_field": field,
        "rows": extracted_rows,
        "duplicate_rows": 0,
        "sort_buffer": sort_buffer,
        "sort_seconds": f"{sort_seconds:.9f}",
        "elapsed_seconds": f"{elapsed:.9f}",
        "temporary_bytes_upper_observed": temp_peak,
        "status": "PASS",
    }


def validate_global_uniqueness(
    shard_packages: list[Path],
    output_dir: Path,
    sort_buffer: str,
) -> tuple[float, list[dict[str, object]]]:
    work_root = output_dir / "global_unique_work"
    work_root.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    rows: list[dict[str, object]] = []
    try:
        for table in CORE_TABLES:
            paths = [package / f"{table}.tsv" for package in shard_packages]
            rows.append(global_unique_check(table, UNIQUE_FIELDS[table], paths, work_root, sort_buffer))
    finally:
        if work_root.exists():
            shutil.rmtree(work_root)
    elapsed = time.perf_counter() - started
    atomic_write_tsv(
        output_dir / "global_id_uniqueness.tsv",
        list(rows[0].keys()) if rows else ["table"],
        rows,
    )
    return elapsed, rows


def verify_final_row_parity(package_dir: Path, uniqueness_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    counts = {str(row["table"]): int(row["rows"]) for row in uniqueness_rows}
    rows: list[dict[str, object]] = []
    for table in CORE_TABLES:
        path = package_dir / f"{table}.tsv"
        ensure_nonempty(path)
        final_rows = max(0, wc_lines(path) - 1)
        shard_rows = counts[table]
        status = "PASS" if final_rows == shard_rows else "FAIL"
        rows.append({
            "table": table,
            "shard_union_rows": shard_rows,
            "final_plain_rows": final_rows,
            "status": status,
        })
        if status != "PASS":
            raise RuntimeError(f"final/shard row-count mismatch {table}: {final_rows} != {shard_rows}")
    return rows


def read_manifest(path: Path) -> list[dict[str, str]]:
    ensure_nonempty(path)
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        required = {"artifact", "table", "rows", "bytes", "sha256"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise RuntimeError(f"invalid package manifest header: {path}")
        return list(reader)


def verify_artifact_integrity(package_dir: Path, row_counts: dict[str, int]) -> tuple[float, list[dict[str, object]]]:
    started = time.perf_counter()
    manifest = read_manifest(package_dir / "package_manifest.tsv")
    by_artifact = {row["artifact"]: row for row in manifest}
    expected = {f"{table}{suffix}" for table in CORE_TABLES for suffix in (".tsv", ".tsv.gz")}
    if set(by_artifact) != expected:
        raise RuntimeError(
            "package manifest artifact set mismatch: "
            f"missing={sorted(expected-set(by_artifact))} extra={sorted(set(by_artifact)-expected)}"
        )
    rows: list[dict[str, object]] = []
    for table in CORE_TABLES:
        plain = package_dir / f"{table}.tsv"
        compressed = package_dir / f"{table}.tsv.gz"
        plain_logical = sha256_file(plain)
        gzip_logical = logical_sha256(compressed)
        for artifact, path in ((plain.name, plain), (compressed.name, compressed)):
            record = by_artifact[artifact]
            observed_raw = sha256_file(path)
            bytes_ok = path.stat().st_size == int(record["bytes"])
            raw_ok = observed_raw == record["sha256"]
            rows_ok = int(record["rows"]) == row_counts[table]
            logical_ok = plain_logical == gzip_logical
            status = "PASS" if bytes_ok and raw_ok and rows_ok and logical_ok else "FAIL"
            rows.append({
                "artifact": artifact,
                "table": table,
                "manifest_rows": record["rows"],
                "observed_rows": row_counts[table],
                "manifest_bytes": record["bytes"],
                "observed_bytes": path.stat().st_size,
                "manifest_sha256": record["sha256"],
                "observed_sha256": observed_raw,
                "plain_gzip_logical_equal": str(logical_ok).lower(),
                "status": status,
            })
            if status != "PASS":
                raise RuntimeError(f"package artifact integrity failure: {artifact}")
    elapsed = time.perf_counter() - started
    return elapsed, rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-dir", required=True, type=Path)
    parser.add_argument("--shards-root", required=True, type=Path)
    parser.add_argument("--schema-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--expected-shards", type=int, default=None)
    parser.add_argument("--sort-buffer", default="512M")
    parser.add_argument("--verify-artifact-integrity", action="store_true")
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args()

    package_dir = args.package_dir.resolve()
    shards_root = args.shards_root.resolve()
    schema_dir = args.schema_dir.resolve()
    output_dir = args.output_dir.resolve()
    if output_dir.exists():
        raise SystemExit(f"output directory already exists: {output_dir}")
    output_dir.mkdir(parents=True)
    if args.workers < 1:
        raise SystemExit("--workers must be >=1")
    for executable in ("/usr/bin/time",):
        if not Path(executable).is_file():
            raise SystemExit(f"required executable missing: {executable}")
    for executable in ("awk", "sort", "wc"):
        if shutil.which(executable) is None:
            raise SystemExit(f"required executable missing: {executable}")

    started = time.perf_counter()
    metrics: list[tuple[str, object]] = [
        ("validator_version", VERSION),
        ("equivalence_scope", EQUIVALENCE_SCOPE),
        ("package_dir", package_dir),
        ("shards_root", shards_root),
        ("schema_dir", schema_dir),
        ("workers", args.workers),
        ("sort_buffer", args.sort_buffer),
        ("artifact_integrity_requested", str(args.verify_artifact_integrity).lower()),
    ]
    try:
        package_core_paths(package_dir)
        check_core_aggregation_absent(package_dir)
        source_rows = verify_frozen_sources(schema_dir)
        atomic_write_tsv(
            output_dir / "frozen_source_guards.tsv",
            list(source_rows[0].keys()),
            source_rows,
        )
        shard_packages = discover_shard_packages(shards_root, args.expected_shards)
        metrics.append(("observed_shards", len(shard_packages)))

        shard_seconds, shard_results = validate_shards(
            shard_packages, schema_dir, output_dir, args.workers, args.python
        )
        unique_seconds, unique_rows = validate_global_uniqueness(
            shard_packages, output_dir, args.sort_buffer
        )
        parity_rows = verify_final_row_parity(package_dir, unique_rows)
        atomic_write_tsv(
            output_dir / "final_shard_row_parity.tsv",
            list(parity_rows[0].keys()),
            parity_rows,
        )

        artifact_seconds = 0.0
        artifact_rows: list[dict[str, object]] = []
        if args.verify_artifact_integrity:
            row_counts = {str(row["table"]): int(row["rows"]) for row in unique_rows}
            artifact_seconds, artifact_rows = verify_artifact_integrity(package_dir, row_counts)
            atomic_write_tsv(
                output_dir / "package_artifact_integrity.tsv",
                list(artifact_rows[0].keys()),
                artifact_rows,
            )

        max_shard_rss = max((row.maximum_resident_set_kbytes for row in shard_results), default=0)
        sum_shard_rss = sum(row.maximum_resident_set_kbytes for row in shard_results)
        elapsed = time.perf_counter() - started
        metrics.extend([
            ("shard_validation_seconds", f"{shard_seconds:.9f}"),
            ("global_uniqueness_seconds", f"{unique_seconds:.9f}"),
            ("artifact_integrity_seconds", f"{artifact_seconds:.9f}"),
            ("maximum_single_shard_rss_kbytes", max_shard_rss),
            ("sum_shard_rss_kbytes", sum_shard_rss),
            ("global_unique_tables", len(unique_rows)),
            ("final_shard_row_parity", "PASS"),
            ("locus_aggregation_status", "NOT_RUN"),
            ("frozen_semantics_modified", "false"),
            ("core_schema_modified", "false"),
            ("active_pipeline_modified", "false"),
            ("ssot_modified", "false"),
            ("full_5_31m_run_started", "false"),
            ("elapsed_seconds", f"{elapsed:.9f}"),
            ("audit_status", "PASS"),
            ("validation_status", "PASS"),
        ])
        atomic_write_metrics(output_dir / "memory_bounded_validator.qc.tsv", metrics)
        print(f"RNATR_STAGE15B_VALIDATOR_VERSION\t{VERSION}")
        print(f"RNATR_STAGE15B_EQUIVALENCE_SCOPE\t{EQUIVALENCE_SCOPE}")
        print(f"RNATR_STAGE15B_SHARDS\t{len(shard_packages)}")
        print(f"RNATR_STAGE15B_MAX_SINGLE_SHARD_RSS_KBYTES\t{max_shard_rss}")
        print(f"RNATR_STAGE15B_ELAPSED_SECONDS\t{elapsed:.9f}")
        print("RNATR_STAGE15B_SHARDED_MEMORY_BOUNDED_PACKAGE_VALIDATION_PASS")
        return 0
    except Exception as exc:
        elapsed = time.perf_counter() - started
        metrics.extend([
            ("elapsed_seconds", f"{elapsed:.9f}"),
            ("audit_status", "FAIL"),
            ("validation_status", "FAIL"),
            ("failure_type", type(exc).__name__),
            ("failure_message", str(exc)),
            ("active_pipeline_modified", "false"),
            ("ssot_modified", "false"),
            ("full_5_31m_run_started", "false"),
        ])
        atomic_write_metrics(output_dir / "memory_bounded_validator.qc.tsv", metrics)
        (output_dir / "failure_traceback.log").write_text(traceback.format_exc(), encoding="utf-8")
        print(f"RNATR_STAGE15B_SHARDED_MEMORY_BOUNDED_PACKAGE_VALIDATION_FAIL\t{type(exc).__name__}\t{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
