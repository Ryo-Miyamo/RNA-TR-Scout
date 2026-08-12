#!/usr/bin/env python3
from __future__ import annotations

import ast
import csv
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
from pathlib import Path
from typing import Any, Iterable

BUILDER_VERSION = "rnatr_stage15c_build_runtime_path_bound_full_runner_v0.1.6"
RUNNER_VERSION = "rnatr_stage15c_full5312696_bam_to_final_v0.1.6"
AMENDMENT_SCHEMA = "rnatr.runtime_path_binding_amendment.v1"
PROJECT_ROOT = Path("/mnt/intelssd/rnatr_project")
DOWNLOADS = Path.home() / "Downloads"

ANALYSIS_RUN_ID = "ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1"
MAPPING_RUN_ID = "ENCSR307SHM_full5312696_mm2splice_v1"
OLD_TEMPLATE_RUN_ID = "ENCSR307SHM_stage15a500k_seed20260809_mm2splice_v1"
EXPECTED_READS = 5_312_696
EXPECTED_ALIGNMENT_RECORDS = 9_774_085
SHARDS = 144
CONCURRENCY = 12
CALLER_WORKERS_PER_SHARD = 2
VALIDATOR_WORKERS = 3
SORT_BUFFER = "512M"
POST_11B_HARD_MAX = 164_204
EXPECTED_PATH_CHECKS_PER_SHARD = 23
EXPECTED_FULL_PATH_CHECKS = SHARDS * EXPECTED_PATH_CHECKS_PER_SHARD

OLD_BENCHMARK_ROOT = "stage15a_500k_seed20260809_v1"
NEW_BENCHMARK_ROOT = "stage15c_full5312696_v1"
OLD_CANDIDATE_FILENAME = "ENCFF260PGB.stage15a_500k.rnatr_candidate_all.fastq.gz"
NEW_CANDIDATE_FILENAME = "ENCFF260PGB.full5312696.rnatr_candidate_all.fastq.gz"
OLD_WINDOW_FILENAME = "ENCFF260PGB.stage15a_500k.rnatr_target_windows.v0.3.3.fastq.gz"
NEW_WINDOW_FILENAME = "ENCFF260PGB.full5312696.rnatr_target_windows.v0.3.3.fastq.gz"
OBSOLETE_RUNTIME_PATH_TOKENS = (
    OLD_BENCHMARK_ROOT,
    OLD_CANDIDATE_FILENAME,
    OLD_WINDOW_FILENAME,
)

BASE_RUNNER = PROJECT_ROOT / "scripts/rnatr_stage15a_run_performance_100k_v0.2.2.1.py"
BASE_RUNNER_SHA256 = "7bfb7018cea80cd92854882751cffb49bea817296f69866801a64f9529c5e1a8"

V015_RUNNER_PROJECT = PROJECT_ROOT / "scripts/rnatr_stage15c_run_full5312696_bam_to_final_v0.1.5.py"
V015_RUNNER_DOWNLOAD = DOWNLOADS / "rnatr_stage15c_run_full5312696_bam_to_final_v015.py"
V015_RUNNER_SHA256 = "ef04486e6bac8f0a3a4949267d7260d30fc02bf60ec276b4276bb39c090a9964"
V015_BUILD_QC_ROOT = (
    PROJECT_ROOT / "qc/15_stage15c_runtime_bound_runner_build"
    / ANALYSIS_RUN_ID / "v0.1.5"
)
V015_BUILD_QC = V015_BUILD_QC_ROOT / "stage15c_runtime_bound_runner_build.qc.tsv"
V015_BUILD_QC_SHA256 = "3843f59627e31711670b485ddd93fc3535d435ee75d4508c11ed67992a5e89a5"
V015_AMENDMENT = (
    PROJECT_ROOT / "metadata/stage15c/runtime_script_binding_amendment_v0.1.5"
    / "rnatr_stage15c_runtime_script_binding_amendment_v0.1.5.json"
)
V015_AMENDMENT_SHA256 = "61576df920008f0e96b73e3246dae7a53404c68c380c74f00491aa459983af82"
V015_BOUND_ROOT = PROJECT_ROOT / "scripts/stage15c/full5312696_runid_bound_v0.1.5"
V015_BOUND_SOURCES: dict[str, tuple[Path, str, str]] = {
    "11b": (
        V015_BOUND_ROOT / "11b_extract_alignment_segments_and_target_candidates.stage15c_full5312696_runid_bound_v0.1.5.sh",
        "bc7523c081434ba7e545a3191aad4e7cb8c4e9d4c1ca771b3658399875a7fcd8",
        "11b_extract_alignment_segments_and_target_candidates.stage15c_full5312696_runtime_bound_v0.1.6.sh",
    ),
    "11d3": (
        V015_BOUND_ROOT / "11d3_project_targets_to_raw_reads.stage15c_full5312696_runid_bound_v0.1.5.sh",
        "dede3a9b25f1e8fcc34ccd1ca5f95de7a15184496d7c96eddbfe119c66e57fe5",
        "11d3_project_targets_to_raw_reads.stage15c_full5312696_runtime_bound_v0.1.6.sh",
    ),
    "11e": (
        V015_BOUND_ROOT / "11e_prepare_motif_scan_jobs.stage15c_full5312696_runid_bound_v0.1.5.sh",
        "23c02846128b4cddefdba6879bbd731b30d552d70e9070b5d9122aebf7e5c0e2",
        "11e_prepare_motif_scan_jobs.stage15c_full5312696_runtime_bound_v0.1.6.sh",
    ),
}

V015_RESULT_ROOT = (
    PROJECT_ROOT / "results/15_stage15c_fullscale_bam_to_final"
    / ANALYSIS_RUN_ID / "v0.1.5"
)
V015_QC_ROOT = (
    PROJECT_ROOT / "qc/15_stage15c_fullscale_bam_to_final"
    / ANALYSIS_RUN_ID / "v0.1.5"
)
V015_PREFLIGHT_ROOT = (
    PROJECT_ROOT / "qc/15_stage15c_fullscale_runner_preflight"
    / ANALYSIS_RUN_ID / "v0.1.5"
)

BOUND_SOURCE_ROOT = PROJECT_ROOT / "scripts/stage15c/full5312696_runtime_bound_v0.1.6"
META_ROOT = PROJECT_ROOT / "metadata/stage15c/runtime_path_binding_amendment_v0.1.6"
AMENDMENT_CONTRACT = META_ROOT / "rnatr_stage15c_runtime_path_binding_amendment_v0.1.6.json"
BUILD_QC_ROOT = (
    PROJECT_ROOT / "qc/15_stage15c_runtime_path_bound_runner_build"
    / ANALYSIS_RUN_ID / "v0.1.6"
)
BUILDER_INSTALL = PROJECT_ROOT / "scripts/rnatr_stage15c_build_runtime_path_bound_full_runner_v0.1.6.py"
RUNNER_INSTALL = PROJECT_ROOT / "scripts/rnatr_stage15c_run_full5312696_bam_to_final_v0.1.6.py"
DOC_INSTALL = PROJECT_ROOT / "docs/stage15c/RNA_TR_Scout_runtime_path_binding_amendment_v0.1.6.md"
RUNNER_DOWNLOAD = DOWNLOADS / "rnatr_stage15c_run_full5312696_bam_to_final_v016.py"
SUCCESS_BUNDLE = DOWNLOADS / "rnatr_stage15c_runtime_path_bound_full_runner_build_v0.1.6.tar.gz"
FAILURE_BUNDLE = DOWNLOADS / "rnatr_stage15c_runtime_path_bound_full_runner_build_v0.1.6_failure.tar.gz"

V016_RESULT_ROOT = (
    PROJECT_ROOT / "results/15_stage15c_fullscale_bam_to_final"
    / ANALYSIS_RUN_ID / "v0.1.6"
)
V016_QC_ROOT = (
    PROJECT_ROOT / "qc/15_stage15c_fullscale_bam_to_final"
    / ANALYSIS_RUN_ID / "v0.1.6"
)
V016_PREFLIGHT_ROOT = (
    PROJECT_ROOT / "qc/15_stage15c_fullscale_runner_preflight"
    / ANALYSIS_RUN_ID / "v0.1.6"
)

SCIENTIFIC_FUNCTIONS = {
    "load_caller_totals_full",
    "derive_expected_final_rows_full",
    "aggregate_materializer_qc_full",
    "create_shards",
    "check_memavailable",
    "run_wave_stage",
    "partition_inputs",
    "load_candidate_counts",
    "candidate_load_gate_decision",
    "enforce_post_11b_candidate_load_hard_gate",
    "extract_candidate_fastqs",
    "run_fast_motif_jobs",
    "load_projection_counts",
    "run_caller_materializer",
    "run_generic_validator",
    "run_memory_bounded_validator",
    "run_validators",
    "sum_path_bytes",
    "temp_snapshot",
    "maximum_rss",
    "checkpoint_manifest",
    "post_timer_shard_audit",
}


class BuildError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def ensure_exact(path: Path, expected_sha256: str) -> None:
    if not path.is_file() or path.stat().st_size <= 0:
        raise BuildError(f"missing/empty required artifact: {path}")
    observed = sha256_file(path)
    if observed != expected_sha256:
        raise BuildError(
            f"SHA-256 mismatch: {path}: expected={expected_sha256} observed={observed}"
        )


def read_two_column(path: Path) -> dict[str, str]:
    if not path.is_file() or path.stat().st_size <= 0:
        raise BuildError(f"missing/empty two-column TSV: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        header = next(reader, None)
        if not header or len(header) < 2:
            raise BuildError(f"invalid two-column TSV: {path}")
        return {row[0]: row[1] for row in reader if len(row) >= 2}


def write_tsv(path: Path, rows: Iterable[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + f".part.{os.getpid()}")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fields, delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def write_metrics(path: Path, rows: Iterable[tuple[str, Any]]) -> None:
    write_tsv(
        path,
        ({"metric": key, "value": value} for key, value in rows),
        ["metric", "value"],
    )


def atomic_write(path: Path, payload: bytes, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + f".part.{os.getpid()}")
    with temporary.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.chmod(mode)
    os.replace(temporary, path)


def install_exact_bytes(payload: bytes, destination: Path, mode: int = 0o644) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    expected = sha256_bytes(payload)
    if destination.exists():
        if not destination.is_file() or sha256_file(destination) != expected:
            raise BuildError(f"refusing overwrite of different versioned file: {destination}")
        destination.chmod(mode)
        return "REUSED_EXACT"
    atomic_write(destination, payload, mode)
    return "INSTALLED_NEW"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise BuildError(f"transform anchor {label} expected once, observed {count}")
    return text.replace(old, new, 1)


def replace_region(text: str, start: str, end: str, replacement: str, label: str) -> str:
    start_pos = text.find(start)
    end_pos = text.find(end, start_pos + len(start)) if start_pos >= 0 else -1
    if start_pos < 0 or end_pos < 0:
        raise BuildError(f"region anchor missing for {label}: start={start_pos} end={end_pos}")
    if text.find(start, start_pos + 1) >= 0:
        raise BuildError(f"region start anchor is not unique for {label}")
    return text[:start_pos] + replacement + text[end_pos:]


def function_sources(source: str) -> dict[str, str]:
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    result: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            result[node.name] = "".join(lines[node.lineno - 1 : node.end_lineno])
    return result


def top_level_constants(source: str) -> dict[str, Any]:
    tree = ast.parse(source)
    values: dict[str, Any] = {}
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)) or node.value is None:
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Name):
                try:
                    values[target.id] = ast.literal_eval(node.value)
                except Exception:
                    pass
    return values


def undefined_uppercase_globals(source: str) -> set[str]:
    tree = ast.parse(source)
    defined: set[str] = set()
    used: set[str] = set()
    import builtins
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                defined.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                defined.add(alias.asname or alias.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    defined.add(target.id)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            used.add(node.id)
    return {
        name for name in used
        if name.isupper() and name not in defined and name not in dir(builtins)
    }


def verify_v015_evidence() -> dict[str, Any]:
    ensure_exact(V015_RUNNER_PROJECT, V015_RUNNER_SHA256)
    if V015_RUNNER_DOWNLOAD.exists():
        ensure_exact(V015_RUNNER_DOWNLOAD, V015_RUNNER_SHA256)
    ensure_exact(V015_BUILD_QC, V015_BUILD_QC_SHA256)
    ensure_exact(V015_AMENDMENT, V015_AMENDMENT_SHA256)
    ensure_exact(BASE_RUNNER, BASE_RUNNER_SHA256)
    for _, (path, expected, _) in V015_BOUND_SOURCES.items():
        ensure_exact(path, expected)

    qc = read_two_column(V015_BUILD_QC)
    required = {
        "builder_version": "rnatr_stage15c_build_runtime_bound_full_runner_v0.1.5",
        "runner_version": "rnatr_stage15c_full5312696_bam_to_final_v0.1.5",
        "analysis_run_id": ANALYSIS_RUN_ID,
        "mapping_run_id": MAPPING_RUN_ID,
        "read_coherent_shards": str(SHARDS),
        "active_shard_concurrency": str(CONCURRENCY),
        "post_11b_candidate_rows_per_shard_hard_max": str(POST_11B_HARD_MAX),
        "bound_source_templates_status": "PASS",
        "real_base_runtime_generation_fixture": "PASS",
        "scientific_processing_functions_byte_identical_to_v014": "true",
        "full_5_31m_run_started": "false",
        "active_pipeline_modified": "false",
        "ssot_modified": "false",
        "build_status": "PASS",
    }
    for key, expected in required.items():
        if qc.get(key) != expected:
            raise BuildError(f"v0.1.5 build mismatch {key}: {qc.get(key)} != {expected}")

    for root in (V015_RESULT_ROOT, V015_QC_ROOT, V015_PREFLIGHT_ROOT):
        if root.exists():
            raise BuildError(
                f"v0.1.5 runtime/preflight root exists; preserve and review before superseding: {root}"
            )
    for root in (V016_RESULT_ROOT, V016_QC_ROOT, V016_PREFLIGHT_ROOT, BUILD_QC_ROOT):
        if root.exists():
            raise BuildError(f"v0.1.6 output root already exists; preserve/review: {root}")

    prior_11d3 = V015_BOUND_SOURCES["11d3"][0].read_text(encoding="utf-8")
    observed_old_path_counts = {
        OLD_BENCHMARK_ROOT: prior_11d3.count(OLD_BENCHMARK_ROOT),
        OLD_CANDIDATE_FILENAME: prior_11d3.count(OLD_CANDIDATE_FILENAME),
        OLD_WINDOW_FILENAME: prior_11d3.count(OLD_WINDOW_FILENAME),
    }
    expected_counts = {
        OLD_BENCHMARK_ROOT: 2,
        OLD_CANDIDATE_FILENAME: 1,
        OLD_WINDOW_FILENAME: 1,
    }
    if observed_old_path_counts != expected_counts:
        raise BuildError(
            f"v0.1.5 path-defect evidence mismatch: {observed_old_path_counts} != {expected_counts}"
        )
    runner_source = V015_RUNNER_PROJECT.read_text(encoding="utf-8")
    if "BOUND_SOURCE_ROOT" not in runner_source or "BOUND_SOURCE_ROOT =" in runner_source:
        raise BuildError("v0.1.5 undefined BOUND_SOURCE_ROOT provenance mismatch")
    if undefined_uppercase_globals(runner_source) != {"BOUND_SOURCE_ROOT"}:
        raise BuildError(
            "v0.1.5 undefined-uppercase provenance mismatch: "
            + repr(undefined_uppercase_globals(runner_source))
        )
    return {
        "v015_preflight_executed": False,
        "v015_full_execution_started": False,
        "v015_runner_sha256": V015_RUNNER_SHA256,
        "v015_build_qc_sha256": V015_BUILD_QC_SHA256,
        "v015_amendment_sha256": V015_AMENDMENT_SHA256,
        "v015_undefined_bound_source_root": True,
        "v015_old_runtime_path_counts": observed_old_path_counts,
    }


def bind_runtime_sources() -> tuple[dict[str, dict[str, Any]], dict[str, bytes]]:
    records: dict[str, dict[str, Any]] = {}
    payloads: dict[str, bytes] = {}
    for role, (source, expected_sha, filename) in V015_BOUND_SOURCES.items():
        ensure_exact(source, expected_sha)
        original = source.read_text(encoding="utf-8")
        transformations: list[dict[str, Any]] = []
        bound = original
        if role == "11d3":
            plan = (
                (OLD_BENCHMARK_ROOT, NEW_BENCHMARK_ROOT, 2, "benchmark_root"),
                (OLD_CANDIDATE_FILENAME, NEW_CANDIDATE_FILENAME, 1, "candidate_filename"),
                (OLD_WINDOW_FILENAME, NEW_WINDOW_FILENAME, 1, "window_filename"),
            )
            for old, new, expected_count, label in plan:
                count = bound.count(old)
                if count != expected_count:
                    raise BuildError(
                        f"{role}: {label} replacement count {count} != {expected_count}"
                    )
                bound = bound.replace(old, new)
                transformations.append(
                    {"label": label, "old": old, "new": new, "count": count}
                )
        obsolete_counts = {token: bound.count(token) for token in OBSOLETE_RUNTIME_PATH_TOKENS}
        if any(obsolete_counts.values()):
            raise BuildError(f"{role}: obsolete runtime path token remains: {obsolete_counts}")
        if OLD_TEMPLATE_RUN_ID in bound or MAPPING_RUN_ID in bound:
            raise BuildError(f"{role}: invalid run ID in v0.1.6 bound source")
        if bound.count(ANALYSIS_RUN_ID) != 1:
            raise BuildError(f"{role}: analysis run-ID count mismatch")
        payload = bound.encode("utf-8")
        with tempfile.NamedTemporaryFile("wb", suffix=".sh", delete=False) as handle:
            handle.write(payload)
            temporary = Path(handle.name)
        try:
            syntax = subprocess.run(
                ["bash", "-n", str(temporary)], text=True, capture_output=True
            )
            if syntax.returncode != 0:
                raise BuildError(f"{role}: bound template bash -n failed: {syntax.stderr}")
        finally:
            temporary.unlink(missing_ok=True)
        destination = BOUND_SOURCE_ROOT / filename
        records[role] = {
            "role": role,
            "source_path": str(source),
            "source_sha256": expected_sha,
            "bound_path": str(destination),
            "bound_sha256": sha256_bytes(payload),
            "bound_bytes": len(payload),
            "analysis_run_id_occurrences": bound.count(ANALYSIS_RUN_ID),
            "obsolete_run_id_occurrences": bound.count(OLD_TEMPLATE_RUN_ID),
            "mapping_run_id_occurrences": bound.count(MAPPING_RUN_ID),
            "obsolete_runtime_path_token_occurrences": sum(obsolete_counts.values()),
            "transformations": transformations,
            "bash_syntax_status": "PASS",
        }
        payloads[role] = payload
    return records, payloads


def import_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise BuildError(f"cannot import module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def create_fixture_shard(base: Any, root: Path):
    project = root / "project"
    raw_root = root / "raw_root"
    mapping_dir = project / "results/11_mapping" / ANALYSIS_RUN_ID
    bench = raw_root / "benchmarks/ENCSR307SHM" / NEW_BENCHMARK_ROOT
    shard = base.Shard(
        index=0,
        name="shard_000",
        root=root,
        project=project,
        raw_root=raw_root,
        bam=mapping_dir / f"{ANALYSIS_RUN_ID}.sorted.bam",
        candidate_fastq=(
            bench / "rnatr_candidates_v0.3.1" / NEW_CANDIDATE_FILENAME
        ),
        script_11b=root / "generated_scripts/11b.stage15c_fullscale.sh",
        script_11d3=root / "generated_scripts/11d3.stage15c_fullscale.sh",
        script_11e=root / "generated_scripts/11e.stage15c_fullscale.sh",
    )
    setattr(
        shard,
        "full_fastq",
        bench / "full_fastq/ENCFF260PGB.full5312696.fastq.gz",
    )
    setattr(shard, "candidate_qc", root / "qc/candidate_fastq_extraction.qc.tsv")
    setattr(
        shard,
        "window_fastq",
        bench / "rnatr_projection_v0.3.3" / NEW_WINDOW_FILENAME,
    )
    return shard


def expected_path_anchor_lines(shard: Any, role: str) -> list[str]:
    if role == "11b":
        return [
            f'RUN_ID="{ANALYSIS_RUN_ID}"',
            'MAPDIR="$PROJECT_ROOT/results/11_mapping/$RUN_ID"',
            'BAM="$MAPDIR/${RUN_ID}.sorted.bam"',
            'OUTDIR="$PROJECT_ROOT/results/11_assignment/$RUN_ID"',
            'QCDIR="$PROJECT_ROOT/qc/11_assignment/$RUN_ID"',
            'READ_TARGETS="$OUTDIR/read_target_candidates.tsv.gz"',
            'ASSIGNMENT_QC="$QCDIR/target_assignment_qc.tsv"',
        ]
    if role == "11d3":
        candidate_relative = shard.candidate_fastq.relative_to(shard.raw_root).as_posix()
        window_parent_relative = shard.window_fastq.parent.relative_to(shard.raw_root).as_posix()
        return [
            f'RUN_ID="{ANALYSIS_RUN_ID}"',
            'BAM="$PROJECT_ROOT/results/11_mapping/$RUN_ID/${RUN_ID}.sorted.bam"',
            'READ_TARGETS="$PROJECT_ROOT/results/11_assignment/$RUN_ID/read_target_candidates.tsv.gz"',
            f'CANDIDATE_FASTQ="$RAW_ROOT/{candidate_relative}"',
            'OUTDIR="$PROJECT_ROOT/results/11_projection/$RUN_ID/v0.3.3"',
            'QCDIR="$PROJECT_ROOT/qc/11_projection/$RUN_ID/v0.3.3"',
            f'DATA_OUTDIR="$RAW_ROOT/{window_parent_relative}"',
            'PROJECTION="$OUTDIR/read_target_projection.v0.3.3.tsv.gz"',
            f'WINDOW_FASTQ="$DATA_OUTDIR/{shard.window_fastq.name}"',
            'QC_SUMMARY="$QCDIR/raw_projection_qc.v0.3.3.tsv"',
        ]
    if role == "11e":
        return [
            f'RUN_ID="{ANALYSIS_RUN_ID}"',
            'PROJECTION="$PROJECT_ROOT/results/11_projection/$RUN_ID/v0.3.3/read_target_projection.v0.3.3.tsv.gz"',
            'OUTDIR="$PROJECT_ROOT/results/11_motif_jobs/$RUN_ID"',
            'QCDIR="$PROJECT_ROOT/qc/11_motif_jobs/$RUN_ID"',
            'JOBS="$OUTDIR/motif_scan_jobs.tsv.gz"',
            'QC_SUMMARY="$QCDIR/motif_job_preparation_qc.tsv"',
        ]
    raise BuildError(f"unknown runtime role: {role}")


def normalize_generated_script(text: str, paths_env: Path) -> str:
    anchor = f'source "{paths_env}"'
    if text.count(anchor) != 1:
        raise BuildError(
            f"generated script paths.env anchor count {text.count(anchor)} != 1: {paths_env}"
        )
    return text.replace(anchor, 'source "<SHARD_PATHS_ENV>"', 1)


def audit_fixture_scripts(shard: Any) -> tuple[list[dict[str, Any]], dict[str, str]]:
    rows: list[dict[str, Any]] = []
    normalized: dict[str, str] = {}
    paths_env = shard.project / "config/paths.env"
    if not paths_env.is_file():
        raise BuildError(f"fixture paths.env missing: {paths_env}")
    env_text = paths_env.read_text(encoding="utf-8")
    env_anchors = [
        f'export PROJECT_ROOT="{shard.project}"',
        f'export RAW_ROOT="{shard.raw_root}"',
        f'export CATALOG_ROOT="{PROJECT_ROOT / "catalogs"}"',
    ]
    if any(anchor not in env_text for anchor in env_anchors):
        raise BuildError("fixture paths.env binding mismatch")
    for role, attribute in (
        ("11b", "script_11b"),
        ("11d3", "script_11d3"),
        ("11e", "script_11e"),
    ):
        path = Path(getattr(shard, attribute))
        if not path.is_file() or path.stat().st_size <= 0:
            raise BuildError(f"fixture generated script missing: {path}")
        text = path.read_text(encoding="utf-8")
        expected = expected_path_anchor_lines(shard, role)
        missing = [line for line in expected if line not in text]
        obsolete = [token for token in OBSOLETE_RUNTIME_PATH_TOKENS if token in text]
        if missing or obsolete or OLD_TEMPLATE_RUN_ID in text or MAPPING_RUN_ID in text:
            raise BuildError(
                f"fixture runtime path binding failed {role}: missing={missing} obsolete={obsolete}"
            )
        if role == "11d3":
            for anchor in (
                'EXPECTED_CANDIDATE_ROWS="${EXPECTED_CANDIDATE_ROWS:-388571}"',
                'EXPECTED_CANDIDATE_READS="${EXPECTED_CANDIDATE_READS:-79176}"',
            ):
                if anchor not in text:
                    raise BuildError(f"fixture 11d3 expected-count override missing: {anchor}")
            if '  "${BAM}.bai" \\\n' in text:
                raise BuildError("fixture 11d3 still requires shard BAI")
        if role == "11b" and '  "$BAI" \\\n' in text:
            raise BuildError("fixture 11b still requires shard BAI")
        if role == "11e":
            for anchor in (
                'EXPECTED_PROJECTION_ROWS="${EXPECTED_PROJECTION_ROWS:-388571}"',
                'EXPECTED_PROJECTION_READS="${EXPECTED_PROJECTION_READS:-79176}"',
            ):
                if anchor not in text:
                    raise BuildError(f"fixture 11e expected-count override missing: {anchor}")
        normalized_text = normalize_generated_script(text, paths_env)
        normalized_sha = sha256_bytes(normalized_text.encode("utf-8"))
        normalized[role] = normalized_sha
        syntax = subprocess.run(["bash", "-n", str(path)], text=True, capture_output=True)
        if syntax.returncode != 0:
            raise BuildError(f"fixture generated script bash syntax failed: {role}")
        normalized_payload = normalized_text.encode("utf-8")
        rows.append(
            {
                "role": role,
                "script_template_name": path.name,
                "normalized_script_bytes": len(normalized_payload),
                "normalized_sha256": normalized_sha,
                "path_binding_checks_expected": len(expected),
                "path_binding_checks_passed": len(expected),
                "obsolete_runtime_path_tokens": 0,
                "paths_env_status": "PASS",
                "expected_count_override_status": "PASS",
                "shard_bai_requirement_status": "PASS",
                "bash_syntax_status": "PASS",
                "status": "PASS",
            }
        )
    if sum(int(row["path_binding_checks_passed"]) for row in rows) != EXPECTED_PATH_CHECKS_PER_SHARD:
        raise BuildError("fixture path-binding check total mismatch")
    return rows, normalized


def build_generated_fixture(
    source_records: dict[str, dict[str, Any]], payloads: dict[str, bytes]
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    module_name = "rnatr_stage15c_v016_base_fixture"
    base = import_module(BASE_RUNNER, module_name)
    try:
        with tempfile.TemporaryDirectory(prefix="rnatr_stage15c_v016_fixture_") as temporary:
            root = Path(temporary)
            source_root = root / "bound_sources"
            source_root.mkdir()
            generated_paths: dict[str, Path] = {}
            for role in ("11b", "11d3", "11e"):
                path = source_root / Path(source_records[role]["bound_path"]).name
                path.write_bytes(payloads[role])
                path.chmod(0o755)
                generated_paths[role] = path
            base.RUN_ID = ANALYSIS_RUN_ID
            base.SOURCE_11B = generated_paths["11b"]
            base.SOURCE_11D3 = generated_paths["11d3"]
            base.SOURCE_11E = generated_paths["11e"]
            shard = create_fixture_shard(base, root / "fixture")
            base.setup_shard_files([shard])
            return audit_fixture_scripts(shard)
    finally:
        sys.modules.pop(module_name, None)


def make_amendment_contract(
    source_records: dict[str, dict[str, Any]],
    fixture_rows: list[dict[str, Any]],
    normalized_sha: dict[str, str],
    prior: dict[str, Any],
) -> bytes:
    payload = {
        "schema": AMENDMENT_SCHEMA,
        "amendment_date": "2026-08-10",
        "builder_version": BUILDER_VERSION,
        "runner_version": RUNNER_VERSION,
        "analysis_run_id": ANALYSIS_RUN_ID,
        "mapping_run_id": MAPPING_RUN_ID,
        "validated_execution": {
            "read_coherent_shards": SHARDS,
            "active_shard_concurrency": CONCURRENCY,
            "caller_workers_per_shard": CALLER_WORKERS_PER_SHARD,
            "validator_workers": VALIDATOR_WORKERS,
            "validator_sort_buffer": SORT_BUFFER,
            "post_11b_candidate_rows_per_shard_hard_max": POST_11B_HARD_MAX,
        },
        "prior_v015": prior,
        "defect_addressed": {
            "cause": "V015_11D3_RUNTIME_PATHS_RETAINED_500K_BENCHMARK_BINDINGS_AND_BOUND_SOURCE_ROOT_WAS_UNDEFINED",
            "v015_preflight_executed": False,
            "v015_full_execution_started": False,
            "v015_scientific_processing_started": False,
            "v015_result_or_qc_root_created": False,
        },
        "runtime_path_binding": {
            "obsolete_tokens": list(OBSOLETE_RUNTIME_PATH_TOKENS),
            "new_benchmark_root": NEW_BENCHMARK_ROOT,
            "new_candidate_filename": NEW_CANDIDATE_FILENAME,
            "new_window_filename": NEW_WINDOW_FILENAME,
            "expected_path_checks_per_shard": EXPECTED_PATH_CHECKS_PER_SHARD,
            "expected_full_path_checks": EXPECTED_FULL_PATH_CHECKS,
            "bound_sources": source_records,
            "fixture_rows": fixture_rows,
            "expected_generated_normalized_sha256": normalized_sha,
        },
        "authorization": {
            "v016_preflight_authorized": True,
            "v016_execution_authorized_after_exact_v016_preflight": True,
            "all_144x3_generated_scripts_must_be_audited_before_partition": True,
            "all_runtime_path_checks_must_pass_before_partition": True,
            "v014_failed_partition_reuse_allowed": False,
            "v015_runtime_artifact_reuse_allowed": False,
            "v016_fresh_partition_required": True,
            "mapping_included_in_bam_to_final_timer": False,
        },
        "prohibitions": {
            "active_pipeline_modification_allowed": False,
            "ssot_modification_allowed": False,
            "core_schema_modification_allowed": False,
            "caller_modification_allowed": False,
            "materializer_modification_allowed": False,
            "accepted_500k_result_modification_allowed": False,
            "v014_failure_artifact_deletion_allowed_by_builder": False,
        },
    }
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def runner_support_source(
    amendment_sha: str,
    source_records: dict[str, dict[str, Any]],
    normalized_sha: dict[str, str],
) -> str:
    source_paths = {role: record["bound_path"] for role, record in source_records.items()}
    source_shas = {role: record["bound_sha256"] for role, record in source_records.items()}
    return f'''PRIOR_V015_RUNNER = Path({str(V015_RUNNER_PROJECT)!r})
PRIOR_V015_RUNNER_SHA256 = {V015_RUNNER_SHA256!r}
PRIOR_V015_BUILD_QC = Path({str(V015_BUILD_QC)!r})
PRIOR_V015_BUILD_QC_SHA256 = {V015_BUILD_QC_SHA256!r}
PRIOR_V015_AMENDMENT = Path({str(V015_AMENDMENT)!r})
PRIOR_V015_AMENDMENT_SHA256 = {V015_AMENDMENT_SHA256!r}
BOUND_SOURCE_ROOT = Path({str(BOUND_SOURCE_ROOT)!r})
BOUND_RUNTIME_SOURCE_PATHS = {{role: Path(path) for role, path in {source_paths!r}.items()}}
BOUND_RUNTIME_SOURCE_SHA256 = {source_shas!r}
EXPECTED_GENERATED_NORMALIZED_SHA256 = {normalized_sha!r}
OBSOLETE_TEMPLATE_RUN_ID = {OLD_TEMPLATE_RUN_ID!r}
OBSOLETE_RUNTIME_PATH_TOKENS = {OBSOLETE_RUNTIME_PATH_TOKENS!r}
RUNTIME_SCRIPT_BINDING_AMENDMENT = Path({str(AMENDMENT_CONTRACT)!r})
RUNTIME_SCRIPT_BINDING_AMENDMENT_SHA256 = {amendment_sha!r}
EXPECTED_RUNTIME_PATH_CHECKS_PER_SHARD = {EXPECTED_PATH_CHECKS_PER_SHARD}
EXPECTED_FULL_RUNTIME_PATH_CHECKS = {EXPECTED_FULL_PATH_CHECKS}


def verify_runtime_script_binding_amendment() -> dict[str, Any]:
    for path, expected in (
        (PRIOR_V015_RUNNER, PRIOR_V015_RUNNER_SHA256),
        (PRIOR_V015_BUILD_QC, PRIOR_V015_BUILD_QC_SHA256),
        (PRIOR_V015_AMENDMENT, PRIOR_V015_AMENDMENT_SHA256),
        (RUNTIME_SCRIPT_BINDING_AMENDMENT, RUNTIME_SCRIPT_BINDING_AMENDMENT_SHA256),
    ):
        ensure_file(path)
        if sha256_file(path) != expected:
            raise RunnerError(f"runtime-path amendment prerequisite SHA mismatch: {{path}}")
    try:
        payload = json.loads(RUNTIME_SCRIPT_BINDING_AMENDMENT.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RunnerError(f"invalid runtime-path binding amendment: {{exc}}") from exc
    for key, expected in {{
        "schema": {AMENDMENT_SCHEMA!r},
        "builder_version": {BUILDER_VERSION!r},
        "runner_version": VERSION,
        "analysis_run_id": ANALYSIS_RUN_ID,
        "mapping_run_id": MAPPING_RUN_ID,
    }}.items():
        if payload.get(key) != expected:
            raise RunnerError(f"runtime-path amendment mismatch {{key}}: {{payload.get(key)}} != {{expected}}")
    execution = payload.get("validated_execution", {{}})
    for key, expected in {{
        "read_coherent_shards": SHARDS,
        "active_shard_concurrency": STAGE_WORKERS,
        "caller_workers_per_shard": CALLER_WORKERS_PER_SHARD,
        "validator_workers": VALIDATOR_WORKERS,
        "validator_sort_buffer": EXTERNAL_SORT_BUFFER,
        "post_11b_candidate_rows_per_shard_hard_max": POST_11B_MAX_CANDIDATE_ROWS_PER_SHARD,
    }}.items():
        if execution.get(key) != expected:
            raise RunnerError(f"runtime-path amendment execution mismatch {{key}}")
    authorization = payload.get("authorization", {{}})
    for key, expected in {{
        "v016_preflight_authorized": True,
        "v016_execution_authorized_after_exact_v016_preflight": True,
        "all_144x3_generated_scripts_must_be_audited_before_partition": True,
        "all_runtime_path_checks_must_pass_before_partition": True,
        "v014_failed_partition_reuse_allowed": False,
        "v015_runtime_artifact_reuse_allowed": False,
        "v016_fresh_partition_required": True,
        "mapping_included_in_bam_to_final_timer": False,
    }}.items():
        if authorization.get(key) != expected:
            raise RunnerError(f"runtime-path amendment authorization mismatch {{key}}")
    binding = payload.get("runtime_path_binding", {{}})
    if binding.get("expected_path_checks_per_shard") != EXPECTED_RUNTIME_PATH_CHECKS_PER_SHARD:
        raise RunnerError("runtime-path amendment per-shard path-check mismatch")
    if binding.get("expected_full_path_checks") != EXPECTED_FULL_RUNTIME_PATH_CHECKS:
        raise RunnerError("runtime-path amendment full path-check mismatch")
    observed_normalized = binding.get("expected_generated_normalized_sha256", {{}})
    if observed_normalized != EXPECTED_GENERATED_NORMALIZED_SHA256:
        raise RunnerError("runtime-path amendment normalized-SHA contract mismatch")
    records = binding.get("bound_sources", {{}})
    for role in ("11b", "11d3", "11e"):
        path = BOUND_RUNTIME_SOURCE_PATHS[role]
        ensure_file(path)
        if sha256_file(path) != BOUND_RUNTIME_SOURCE_SHA256[role]:
            raise RunnerError(f"runtime-bound source SHA mismatch: {{role}}")
        text = path.read_text(encoding="utf-8")
        if OBSOLETE_TEMPLATE_RUN_ID in text or MAPPING_RUN_ID in text:
            raise RunnerError(f"invalid run ID in runtime-bound source: {{role}}")
        if text.count(ANALYSIS_RUN_ID) != 1:
            raise RunnerError(f"analysis run-ID count mismatch in runtime-bound source: {{role}}")
        if any(token in text for token in OBSOLETE_RUNTIME_PATH_TOKENS):
            raise RunnerError(f"obsolete runtime path token remains in bound source: {{role}}")
        if records.get(role, {{}}).get("bound_sha256") != BOUND_RUNTIME_SOURCE_SHA256[role]:
            raise RunnerError(f"amendment bound-source SHA mismatch: {{role}}")
        syntax = subprocess.run(["bash", "-n", str(path)], text=True, capture_output=True)
        if syntax.returncode != 0:
            raise RunnerError(f"runtime-bound source bash syntax failure {{role}}: {{syntax.stderr}}")
    return {{
        "amendment_sha256": RUNTIME_SCRIPT_BINDING_AMENDMENT_SHA256,
        "bound_sources": 3,
        "path_checks_per_shard": EXPECTED_RUNTIME_PATH_CHECKS_PER_SHARD,
        "expected_full_path_checks": EXPECTED_FULL_RUNTIME_PATH_CHECKS,
        "v015_runtime_artifact_reuse_allowed": False,
        "v016_fresh_partition_required": True,
    }}


def create_runtime_script_binding_fixture(base, root: Path):
    name = "shard_000"
    project = root / "project"
    raw_root = root / "raw_root"
    mapping_dir = project / "results/11_mapping" / RUN_ID
    bench = raw_root / "benchmarks/ENCSR307SHM/{NEW_BENCHMARK_ROOT}"
    shard = base.Shard(
        index=0,
        name=name,
        root=root,
        project=project,
        raw_root=raw_root,
        bam=mapping_dir / f"{{RUN_ID}}.sorted.bam",
        candidate_fastq=bench / "rnatr_candidates_v0.3.1/{NEW_CANDIDATE_FILENAME}",
        script_11b=root / "generated_scripts/11b.stage15c_fullscale.sh",
        script_11d3=root / "generated_scripts/11d3.stage15c_fullscale.sh",
        script_11e=root / "generated_scripts/11e.stage15c_fullscale.sh",
    )
    setattr(shard, "full_fastq", bench / "full_fastq/ENCFF260PGB.full5312696.fastq.gz")
    setattr(shard, "candidate_qc", root / "qc/candidate_fastq_extraction.qc.tsv")
    setattr(shard, "window_fastq", bench / "rnatr_projection_v0.3.3/{NEW_WINDOW_FILENAME}")
    return shard


def expected_runtime_path_anchor_lines(shard: Any, role: str) -> list[str]:
    if role == "11b":
        return [
            f'RUN_ID="{{ANALYSIS_RUN_ID}}"',
            'MAPDIR="$PROJECT_ROOT/results/11_mapping/$RUN_ID"',
            'BAM="$MAPDIR/${{RUN_ID}}.sorted.bam"',
            'OUTDIR="$PROJECT_ROOT/results/11_assignment/$RUN_ID"',
            'QCDIR="$PROJECT_ROOT/qc/11_assignment/$RUN_ID"',
            'READ_TARGETS="$OUTDIR/read_target_candidates.tsv.gz"',
            'ASSIGNMENT_QC="$QCDIR/target_assignment_qc.tsv"',
        ]
    if role == "11d3":
        candidate_relative = shard.candidate_fastq.relative_to(shard.raw_root).as_posix()
        window_parent_relative = shard.window_fastq.parent.relative_to(shard.raw_root).as_posix()
        return [
            f'RUN_ID="{{ANALYSIS_RUN_ID}}"',
            'BAM="$PROJECT_ROOT/results/11_mapping/$RUN_ID/${{RUN_ID}}.sorted.bam"',
            'READ_TARGETS="$PROJECT_ROOT/results/11_assignment/$RUN_ID/read_target_candidates.tsv.gz"',
            f'CANDIDATE_FASTQ="$RAW_ROOT/{{candidate_relative}}"',
            'OUTDIR="$PROJECT_ROOT/results/11_projection/$RUN_ID/v0.3.3"',
            'QCDIR="$PROJECT_ROOT/qc/11_projection/$RUN_ID/v0.3.3"',
            f'DATA_OUTDIR="$RAW_ROOT/{{window_parent_relative}}"',
            'PROJECTION="$OUTDIR/read_target_projection.v0.3.3.tsv.gz"',
            f'WINDOW_FASTQ="$DATA_OUTDIR/{{shard.window_fastq.name}}"',
            'QC_SUMMARY="$QCDIR/raw_projection_qc.v0.3.3.tsv"',
        ]
    if role == "11e":
        return [
            f'RUN_ID="{{ANALYSIS_RUN_ID}}"',
            'PROJECTION="$PROJECT_ROOT/results/11_projection/$RUN_ID/v0.3.3/read_target_projection.v0.3.3.tsv.gz"',
            'OUTDIR="$PROJECT_ROOT/results/11_motif_jobs/$RUN_ID"',
            'QCDIR="$PROJECT_ROOT/qc/11_motif_jobs/$RUN_ID"',
            'JOBS="$OUTDIR/motif_scan_jobs.tsv.gz"',
            'QC_SUMMARY="$QCDIR/motif_job_preparation_qc.tsv"',
        ]
    raise RunnerError(f"unknown runtime role: {{role}}")


def normalize_generated_runtime_script(text: str, paths_env: Path) -> str:
    anchor = f'source "{{paths_env}}"'
    if text.count(anchor) != 1:
        raise RunnerError(
            f"runtime-generated paths.env anchor count {{text.count(anchor)}} != 1: {{paths_env}}"
        )
    return text.replace(anchor, 'source "<SHARD_PATHS_ENV>"', 1)


def audit_generated_runtime_scripts(
    shards: list[Any], output_path: Path, scope: str
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    specs = (("11b", "script_11b"), ("11d3", "script_11d3"), ("11e", "script_11e"))
    for shard in shards:
        paths_env = shard.project / "config/paths.env"
        ensure_file(paths_env)
        env_text = paths_env.read_text(encoding="utf-8")
        env_anchors = [
            f'export PROJECT_ROOT="{{shard.project}}"',
            f'export RAW_ROOT="{{shard.raw_root}}"',
            f'export CATALOG_ROOT="{{PROJECT_ROOT / "catalogs"}}"',
        ]
        paths_env_status = "PASS" if all(anchor in env_text for anchor in env_anchors) else "FAIL"
        for role, attribute in specs:
            path = Path(getattr(shard, attribute))
            ensure_file(path)
            text = path.read_text(encoding="utf-8")
            old_count = text.count(OBSOLETE_TEMPLATE_RUN_ID)
            mapping_count = text.count(MAPPING_RUN_ID)
            analysis_count = text.count(ANALYSIS_RUN_ID)
            obsolete_path_count = sum(text.count(token) for token in OBSOLETE_RUNTIME_PATH_TOKENS)
            expected_anchors = expected_runtime_path_anchor_lines(shard, role)
            missing_path_anchors = [line for line in expected_anchors if line not in text]
            normalized = normalize_generated_runtime_script(text, paths_env)
            normalized_sha = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
            expected_normalized_sha = EXPECTED_GENERATED_NORMALIZED_SHA256[role]
            expected_override_status = "PASS"
            bai_status = "PASS"
            if role == "11d3":
                for anchor in (
                    'EXPECTED_CANDIDATE_ROWS="${{EXPECTED_CANDIDATE_ROWS:-388571}}"',
                    'EXPECTED_CANDIDATE_READS="${{EXPECTED_CANDIDATE_READS:-79176}}"',
                ):
                    if anchor not in text:
                        expected_override_status = "FAIL"
                if '  "${{BAM}}.bai" \\\n' in text:
                    bai_status = "FAIL"
            elif role == "11b":
                if '  "$BAI" \\\n' in text:
                    bai_status = "FAIL"
            elif role == "11e":
                for anchor in (
                    'EXPECTED_PROJECTION_ROWS="${{EXPECTED_PROJECTION_ROWS:-388571}}"',
                    'EXPECTED_PROJECTION_READS="${{EXPECTED_PROJECTION_READS:-79176}}"',
                ):
                    if anchor not in text:
                        expected_override_status = "FAIL"
            syntax = subprocess.run(["bash", "-n", str(path)], text=True, capture_output=True)
            failure_codes: list[str] = []
            if old_count:
                failure_codes.append("OBSOLETE_500K_RUN_ID_PRESENT")
            if mapping_count:
                failure_codes.append("MAPPING_RUN_ID_PRESENT_IN_ANALYSIS_SCRIPT")
            if analysis_count < 1:
                failure_codes.append("ANALYSIS_RUN_ID_ANCHOR_MISSING")
            if obsolete_path_count:
                failure_codes.append("OBSOLETE_500K_RUNTIME_PATH_PRESENT")
            if missing_path_anchors:
                failure_codes.append("RUNTIME_PATH_ANCHOR_MISSING")
            if paths_env_status != "PASS":
                failure_codes.append("SHARD_PATHS_ENV_BINDING_FAIL")
            if normalized_sha != expected_normalized_sha:
                failure_codes.append("NORMALIZED_GENERATED_SCRIPT_SHA_MISMATCH")
            if expected_override_status != "PASS":
                failure_codes.append("EXPECTED_COUNT_OVERRIDE_MISSING")
            if bai_status != "PASS":
                failure_codes.append("SHARD_BAI_REQUIREMENT_REINTRODUCED")
            if syntax.returncode != 0:
                failure_codes.append("BASH_SYNTAX_FAIL")
            status = "PASS" if not failure_codes else "FAIL"
            rows.append({{
                "scope": scope,
                "shard": shard.name,
                "role": role,
                "path": str(path),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "normalized_sha256": normalized_sha,
                "expected_normalized_sha256": expected_normalized_sha,
                "obsolete_run_id_occurrences": old_count,
                "mapping_run_id_occurrences": mapping_count,
                "analysis_run_id_occurrences": analysis_count,
                "obsolete_runtime_path_token_occurrences": obsolete_path_count,
                "path_binding_checks_expected": len(expected_anchors),
                "path_binding_checks_passed": len(expected_anchors) - len(missing_path_anchors),
                "missing_runtime_path_anchors": len(missing_path_anchors),
                "paths_env_status": paths_env_status,
                "expected_count_override_status": expected_override_status,
                "shard_bai_requirement_status": bai_status,
                "bash_syntax_status": "PASS" if syntax.returncode == 0 else "FAIL",
                "failure_codes": ";".join(failure_codes) if failure_codes else ".",
                "status": status,
            }})
    rows.sort(key=lambda row: (str(row["shard"]), str(row["role"])))
    atomic_write_tsv(output_path, list(rows[0]), rows)
    failures = [row for row in rows if row["status"] != "PASS"]
    if failures:
        first = failures[0]
        raise RunnerError(
            "runtime-generated script path-binding audit failed: "
            f"{{first['shard']}}/{{first['role']}}:{{first['failure_codes']}}"
        )
    return rows


def setup_and_audit_shard_files(
    base, shards: list[Any], output_path: Path, scope: str
) -> list[dict[str, Any]]:
    base.setup_shard_files(shards)
    return audit_generated_runtime_scripts(shards, output_path, scope)

'''


def transform_runner(
    v015_source: str,
    amendment_sha: str,
    source_records: dict[str, dict[str, Any]],
    normalized_sha: dict[str, str],
) -> str:
    text = v015_source
    text = replace_once(
        text,
        'VERSION = "rnatr_stage15c_full5312696_bam_to_final_v0.1.5"',
        'VERSION = "rnatr_stage15c_full5312696_bam_to_final_v0.1.6"',
        "runner_version",
    )
    old_roots = '''RESULT_ROOT = (
    PROJECT_ROOT / "results/15_stage15c_fullscale_bam_to_final" / RUN_ID / "v0.1.5"
)
QC_ROOT = (
    PROJECT_ROOT / "qc/15_stage15c_fullscale_bam_to_final" / RUN_ID / "v0.1.5"
)
PREFLIGHT_ROOT = (
    PROJECT_ROOT / "qc/15_stage15c_fullscale_runner_preflight" / RUN_ID / "v0.1.5"
)
'''
    new_roots = old_roots.replace('"v0.1.5"', '"v0.1.6"')
    text = replace_once(text, old_roots, new_roots, "output_roots")
    for old, new, label in (
        (
            'DOC_PATH = PROJECT_ROOT / "docs/stage15c/RNA_TR_Scout_fullscale_runner_execution_contract_v0.1.5.md"',
            'DOC_PATH = PROJECT_ROOT / "docs/stage15c/RNA_TR_Scout_fullscale_runner_execution_contract_v0.1.6.md"',
            "doc_path",
        ),
        (
            'SCRIPT_INSTALL = PROJECT_ROOT / "scripts/rnatr_stage15c_run_full5312696_bam_to_final_v0.1.5.py"',
            'SCRIPT_INSTALL = PROJECT_ROOT / "scripts/rnatr_stage15c_run_full5312696_bam_to_final_v0.1.6.py"',
            "script_install",
        ),
        (
            'PREFLIGHT_BUNDLE = DOWNLOADS / "rnatr_stage15c_fullscale_runner_preflight_v0.1.5.tar.gz"',
            'PREFLIGHT_BUNDLE = DOWNLOADS / "rnatr_stage15c_fullscale_runner_preflight_v0.1.6.tar.gz"',
            "preflight_bundle",
        ),
        (
            'SUCCESS_BUNDLE = DOWNLOADS / "rnatr_stage15c_full_empirical_run_v0.1.5.tar.gz"',
            'SUCCESS_BUNDLE = DOWNLOADS / "rnatr_stage15c_full_empirical_run_v0.1.6.tar.gz"',
            "success_bundle",
        ),
        (
            'FAILURE_BUNDLE = DOWNLOADS / "rnatr_stage15c_full_empirical_run_v0.1.5_failure.tar.gz"',
            'FAILURE_BUNDLE = DOWNLOADS / "rnatr_stage15c_full_empirical_run_v0.1.6_failure.tar.gz"',
            "failure_bundle",
        ),
    ):
        text = replace_once(text, old, new, label)

    old_source_block_start = "SOURCE_11B = Path('/mnt/intelssd/rnatr_project/scripts/stage15c/full5312696_runid_bound_v0.1.5/"
    start_pos = text.find(old_source_block_start)
    end_marker = "\nPERF_CALLER = "
    end_pos = text.find(end_marker, start_pos)
    if start_pos < 0 or end_pos < 0:
        raise BuildError("v0.1.5 source block anchors missing")
    new_source_block = f'''SOURCE_11B = Path({source_records["11b"]["bound_path"]!r})
SOURCE_11D3 = Path({source_records["11d3"]["bound_path"]!r})
SOURCE_11E = Path({source_records["11e"]["bound_path"]!r})
SOURCE_SHA = {{
    SOURCE_11B: {source_records["11b"]["bound_sha256"]!r},
    SOURCE_11D3: {source_records["11d3"]["bound_sha256"]!r},
    SOURCE_11E: {source_records["11e"]["bound_sha256"]!r},
}}
'''
    text = text[:start_pos] + new_source_block + text[end_pos:]

    support = runner_support_source(amendment_sha, source_records, normalized_sha)
    text = replace_region(
        text,
        "PRIOR_V015_RUNNER = Path(" if "PRIOR_V015_RUNNER = Path(" in text else "ORIGINAL_RUNTIME_SOURCE_PATHS = {",
        "SSOT_GUARDS = {",
        support,
        "runtime_path_support",
    )

    text = replace_once(
        text,
        "# RNA-TR-Scout Stage 15C full-scale execution contract v0.1.5",
        "# RNA-TR-Scout Stage 15C full-scale execution contract v0.1.6",
        "contract_heading",
    )
    text = replace_once(
        text,
        "## Runtime-generated script binding amendment\n\n",
        "## Runtime-generated script ID and path binding amendments\n\n"
        f"- v0.1.6 runtime-path amendment SHA-256: `{amendment_sha}`\n"
        f"- Candidate benchmark root: `{NEW_BENCHMARK_ROOT}`\n"
        f"- Candidate FASTQ filename: `{NEW_CANDIDATE_FILENAME}`\n"
        f"- Window FASTQ filename: `{NEW_WINDOW_FILENAME}`\n"
        f"- Expected path checks: `{EXPECTED_PATH_CHECKS_PER_SHARD}` per shard / `{EXPECTED_FULL_PATH_CHECKS}` full run\n"
        "- Generated scripts are normalized for shard-specific paths.env and checked against frozen per-role SHA-256 values.\n\n",
        "contract_path_binding_section",
    )
    text = text.replace("v0.1.5 performs a fresh partition", "v0.1.6 performs a fresh partition")
    text = replace_once(
        text,
        "This v0.1.4 runner must complete its own exact-byte preflight before `--execute`.",
        "This v0.1.6 runner must complete its own exact-byte preflight before `--execute`.",
        "contract_self_version",
    )
    text = replace_once(
        text,
        "- Amendment SHA-256: `61576df920008f0e96b73e3246dae7a53404c68c380c74f00491aa459983af82`",
        "- Prior v0.1.5 run-ID binding amendment SHA-256: `61576df920008f0e96b73e3246dae7a53404c68c380c74f00491aa459983af82`",
        "contract_prior_amendment_label",
    )
    text = replace_once(
        text,
        "FULL_EXECUTION_NOT_AUTHORIZED_BY_V0.1.5_RUNTIME_BINDING_AMENDMENT",
        "FULL_EXECUTION_NOT_AUTHORIZED_BY_V0.1.6_RUNTIME_PATH_BINDING_AMENDMENT",
        "execution_authorization_error_version",
    )
    old_required_amendment = (
        '        "runtime_script_binding_amendment_sha256": '
        f'{V015_AMENDMENT_SHA256!r},'
    )
    new_required_amendment = (
        '        "runtime_script_binding_amendment_sha256": '
        f'{amendment_sha!r},'
    )
    text = replace_once(
        text,
        old_required_amendment,
        new_required_amendment,
        "execute_preflight_amendment_sha",
    )

    # Preflight: path-audit totals and provenance.
    fixture_anchor = '''    fixture_rows = setup_and_audit_shard_files(
        base, [fixture],
        PREFLIGHT_ROOT / "runtime_script_binding_fixture.audit.tsv",
        "PREFLIGHT_SYNTHETIC_ONE_SHARD",
    )
'''
    fixture_insert = fixture_anchor + '''    fixture_path_checks = sum(int(row["path_binding_checks_passed"]) for row in fixture_rows)
    if len(fixture_rows) != 3 or fixture_path_checks != EXPECTED_RUNTIME_PATH_CHECKS_PER_SHARD:
        raise RunnerError(
            f"runtime-path fixture mismatch rows={len(fixture_rows)} checks={fixture_path_checks}"
        )
'''
    text = replace_once(text, fixture_anchor, fixture_insert, "preflight_fixture_path_checks")

    old_qc_fields = '''        ("runtime_script_binding_fixture_status", "PASS"),
        ("runtime_script_binding_fixture_rows", len(fixture_rows)),
        ("runtime_script_binding_expected_full_rows", SHARDS * 3),
        ("v014_failed_partition_reused", "false"),
        ("v015_fresh_partition_required", "true"),
'''
    new_qc_fields = '''        ("runtime_script_binding_fixture_status", "PASS"),
        ("runtime_script_binding_fixture_rows", len(fixture_rows)),
        ("runtime_script_binding_expected_full_rows", SHARDS * 3),
        ("runtime_script_path_binding_fixture_status", "PASS"),
        ("runtime_script_path_binding_fixture_checks", fixture_path_checks),
        ("runtime_script_path_binding_expected_per_shard_checks", EXPECTED_RUNTIME_PATH_CHECKS_PER_SHARD),
        ("runtime_script_path_binding_expected_full_checks", EXPECTED_FULL_RUNTIME_PATH_CHECKS),
        ("runtime_generated_normalized_sha_fixture_status", "PASS"),
        ("v014_failed_partition_reused", "false"),
        ("v015_preflight_executed", "false"),
        ("v015_full_execution_started", "false"),
        ("v016_fresh_partition_required", "true"),
'''
    text = replace_once(text, old_qc_fields, new_qc_fields, "preflight_qc_path_fields")

    text = replace_once(
        text,
        '"rnatr_stage15c_fullscale_runner_preflight_v0.1.5")',
        '"rnatr_stage15c_fullscale_runner_preflight_v0.1.6")',
        "preflight_bundle_prefix",
    )

    old_required = '''        "runtime_script_binding_fixture_status": "PASS",
        "runtime_script_binding_fixture_rows": "3",
        "runtime_script_binding_expected_full_rows": "432",
        "v014_failed_partition_reused": "false",
        "v015_fresh_partition_required": "true",
'''
    new_required = f'''        "runtime_script_binding_fixture_status": "PASS",
        "runtime_script_binding_fixture_rows": "3",
        "runtime_script_binding_expected_full_rows": "432",
        "runtime_script_path_binding_fixture_status": "PASS",
        "runtime_script_path_binding_fixture_checks": "{EXPECTED_PATH_CHECKS_PER_SHARD}",
        "runtime_script_path_binding_expected_per_shard_checks": "{EXPECTED_PATH_CHECKS_PER_SHARD}",
        "runtime_script_path_binding_expected_full_checks": "{EXPECTED_FULL_PATH_CHECKS}",
        "runtime_generated_normalized_sha_fixture_status": "PASS",
        "v014_failed_partition_reused": "false",
        "v015_preflight_executed": "false",
        "v015_full_execution_started": "false",
        "v016_fresh_partition_required": "true",
'''
    text = replace_once(text, old_required, new_required, "execute_preflight_path_requirements")

    # Execute: all 432 scripts and all 3312 path checks must pass before timer/partition.
    old_count_check = '''    if len(runtime_script_rows) != SHARDS * 3:
        raise RunnerError(
            f"runtime-generated script audit row mismatch: {len(runtime_script_rows)} != {SHARDS * 3}"
        )
'''
    new_count_check = old_count_check + '''    runtime_path_checks = sum(int(row["path_binding_checks_passed"]) for row in runtime_script_rows)
    if runtime_path_checks != EXPECTED_FULL_RUNTIME_PATH_CHECKS:
        raise RunnerError(
            f"runtime-generated path-check mismatch: {runtime_path_checks} != {EXPECTED_FULL_RUNTIME_PATH_CHECKS}"
        )
'''
    text = replace_once(text, old_count_check, new_count_check, "execute_path_check_count")

    # Replace v0.1.5 provenance fields in contract/failure/final QC.
    text = text.replace(
        '("runtime_generated_script_audit_status", "PASS"),\n            ("v014_failed_partition_reused", "false"),\n            ("v015_fresh_partition_required", "true"),',
        '("runtime_generated_script_audit_status", "PASS"),\n'
        '            ("runtime_generated_path_binding_checks", runtime_path_checks),\n'
        '            ("runtime_generated_path_binding_status", "PASS"),\n'
        '            ("v014_failed_partition_reused", "false"),\n'
        '            ("v015_runtime_artifacts_reused", "false"),\n'
        '            ("v016_fresh_partition_required", "true"),'
    )
    text = text.replace(
        '("runtime_generated_script_audit_status", "PASS"),\n                ("v014_failed_partition_reused", "false"),\n                ("v015_fresh_partition_required", "true"),',
        '("runtime_generated_script_audit_status", "PASS"),\n'
        '                ("runtime_generated_path_binding_checks", runtime_path_checks),\n'
        '                ("runtime_generated_path_binding_status", "PASS"),\n'
        '                ("v014_failed_partition_reused", "false"),\n'
        '                ("v015_runtime_artifacts_reused", "false"),\n'
        '                ("v016_fresh_partition_required", "true"),'
    )
    text = text.replace(
        '("runtime_generated_script_audit_status", "PASS"),\n        ("v014_failed_partition_reused", "false"),\n        ("v015_fresh_partition_required", "true"),',
        '("runtime_generated_script_audit_status", "PASS"),\n'
        '        ("runtime_generated_path_binding_checks", runtime_path_checks),\n'
        '        ("runtime_generated_path_binding_status", "PASS"),\n'
        '        ("v014_failed_partition_reused", "false"),\n'
        '        ("v015_runtime_artifacts_reused", "false"),\n'
        '        ("v016_fresh_partition_required", "true"),'
    )

    text = text.replace(
        '"rnatr_stage15c_full_empirical_run_v0.1.5")',
        '"rnatr_stage15c_full_empirical_run_v0.1.6")',
    )
    text = text.replace(
        '"rnatr_stage15c_full_empirical_run_failure_v0.1.5")',
        '"rnatr_stage15c_full_empirical_run_failure_v0.1.6")',
    )
    return text


def audit_runner_source(
    v015_source: str,
    generated: str,
    amendment_sha: str,
    source_records: dict[str, dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    try:
        ast.parse(generated)
        ast.parse(v015_source)
    except SyntaxError as exc:
        return [f"SYNTAX_ERROR:{exc}"]
    constants = top_level_constants(generated)
    expected_constants = {
        "VERSION": RUNNER_VERSION,
        "ANALYSIS_RUN_ID": ANALYSIS_RUN_ID,
        "MAPPING_RUN_ID": MAPPING_RUN_ID,
        "SHARDS": SHARDS,
        "STAGE_WORKERS": CONCURRENCY,
        "CALLER_PIPELINE_WORKERS": CONCURRENCY,
        "CALLER_WORKERS_PER_SHARD": CALLER_WORKERS_PER_SHARD,
        "VALIDATOR_WORKERS": VALIDATOR_WORKERS,
        "EXTERNAL_SORT_BUFFER": SORT_BUFFER,
        "POST_11B_MAX_CANDIDATE_ROWS_PER_SHARD": POST_11B_HARD_MAX,
        "FULL_EXECUTION_AUTHORIZED": True,
        "RUNTIME_SCRIPT_BINDING_AMENDMENT_SHA256": amendment_sha,
        "EXPECTED_RUNTIME_PATH_CHECKS_PER_SHARD": EXPECTED_PATH_CHECKS_PER_SHARD,
        "EXPECTED_FULL_RUNTIME_PATH_CHECKS": EXPECTED_FULL_PATH_CHECKS,
        "EXPECTED_GENERATED_NORMALIZED_SHA256": {
            role: source_records[role]["expected_generated_normalized_sha256"]
            for role in ("11b", "11d3", "11e")
        },
    }
    for key, expected in expected_constants.items():
        if constants.get(key) != expected:
            errors.append(f"CONST_MISMATCH:{key}:{constants.get(key)!r}!={expected!r}")
    for token in OBSOLETE_RUNTIME_PATH_TOKENS:
        # Exactly one occurrence is allowed in the frozen prohibition tuple.
        # Any additional occurrence means an obsolete runtime path leaked into
        # executable code or documentation.
        count = generated.count(token)
        if count != 1:
            errors.append(f"OBSOLETE_RUNTIME_PATH_TOKEN_COUNT:{token}:{count}!=1")
    if undefined_uppercase_globals(generated):
        errors.append("UNDEFINED_UPPERCASE_GLOBALS:" + repr(sorted(undefined_uppercase_globals(generated))))
    for role, constant in (("11b", "SOURCE_11B"), ("11d3", "SOURCE_11D3"), ("11e", "SOURCE_11E")):
        if f"{constant} = Path({source_records[role]['bound_path']!r})" not in generated:
            errors.append(f"BOUND_SOURCE_PATH_MISMATCH:{role}")
    required_fragments = (
        "def verify_runtime_script_binding_amendment()",
        "def expected_runtime_path_anchor_lines(",
        "def normalize_generated_runtime_script(",
        "def audit_generated_runtime_scripts(",
        "runtime_script_path_binding_fixture_status",
        "runtime_generated_path_binding_checks",
        "EXPECTED_FULL_RUNTIME_PATH_CHECKS",
        "BOUND_SOURCE_ROOT = Path(",
        "# RNA-TR-Scout Stage 15C full-scale execution contract v0.1.6",
        "v016_fresh_partition_required",
    )
    for fragment in required_fragments:
        if fragment not in generated:
            errors.append(f"MISSING_FRAGMENT:{fragment}")
    forbidden_fragments = (
        'rnatr_stage15c_fullscale_runner_preflight_v0.1.5',
        'rnatr_stage15c_full_empirical_run_v0.1.5',
        'rnatr_stage15c_full_empirical_run_failure_v0.1.5',
        'v015_fresh_partition_required',
        '# RNA-TR-Scout Stage 15C full-scale execution contract v0.1.5',
        'This v0.1.4 runner must complete its own exact-byte preflight before `--execute`.',
        'FULL_EXECUTION_NOT_AUTHORIZED_BY_V0.1.5_RUNTIME_BINDING_AMENDMENT',
    )
    for fragment in forbidden_fragments:
        if fragment in generated:
            errors.append(f"FORBIDDEN_V015_FRAGMENT:{fragment}")
    required_exact_counts = {
        'runtime_generated_path_binding_checks': 3,
        'v015_runtime_artifacts_reused': 3,
        '# RNA-TR-Scout Stage 15C full-scale execution contract v0.1.6': 1,
        'rnatr_stage15c_fullscale_runner_preflight_v0.1.6': 2,
        'rnatr_stage15c_full_empirical_run_v0.1.6': 3,
        'rnatr_stage15c_full_empirical_run_failure_v0.1.6': 1,
    }
    for fragment, expected_count in required_exact_counts.items():
        observed_count = generated.count(fragment)
        if observed_count != expected_count:
            errors.append(
                f"FRAGMENT_COUNT_MISMATCH:{fragment}:{observed_count}!={expected_count}"
            )
    if ' / RUN_ID / "v0.1.5"\n)' in generated:
        errors.append("V015_OUTPUT_ROOT_REMAINED")
    if ' / RUN_ID / "v0.1.6"\n)' not in generated:
        errors.append("V016_OUTPUT_ROOT_MISSING")

    functions = function_sources(generated)
    old_functions = function_sources(v015_source)
    execute_source = functions.get("execute", "")
    preflight_source = functions.get("preflight", "")
    verify_preflight_source = functions.get("verify_preflight_for_execute", "")
    contract_source = functions.get("write_execution_contract", "")
    expected_preflight_amendment_line = (
        '"runtime_script_binding_amendment_sha256": '
        f'{amendment_sha!r}'
    )
    if expected_preflight_amendment_line not in verify_preflight_source:
        errors.append("VERIFY_PREFLIGHT_CURRENT_AMENDMENT_SHA_MISSING")
    if V015_AMENDMENT_SHA256 in verify_preflight_source:
        errors.append("VERIFY_PREFLIGHT_STALE_V015_AMENDMENT_SHA")
    if "This v0.1.6 runner must complete its own exact-byte preflight" not in contract_source:
        errors.append("CONTRACT_SELF_VERSION_MISMATCH")
    if "Prior v0.1.5 run-ID binding amendment SHA-256" not in contract_source:
        errors.append("CONTRACT_PRIOR_AMENDMENT_LABEL_MISSING")
    if "base.setup_shard_files(shards)" in execute_source:
        errors.append("DIRECT_UNAUDITED_SETUP_REMAINS_IN_EXECUTE")
    for needle in (
        "verify_runtime_script_binding_amendment()",
        "setup_and_audit_shard_files(",
        "runtime_generated_scripts_prepartition.audit.tsv",
        "runtime_path_checks = sum(",
    ):
        if needle not in execute_source:
            errors.append(f"EXECUTE_MISSING:{needle}")
    positions = {
        "verify": execute_source.find("verify_runtime_script_binding_amendment()"),
        "setup": execute_source.find("setup_and_audit_shard_files("),
        "path_count": execute_source.find("runtime_path_checks = sum("),
        "timer": execute_source.find("production_started = time.perf_counter()"),
        "partition": execute_source.find("partition_inputs(base, shards)"),
        "caller": execute_source.find("run_caller_materializer(base, shards)"),
    }
    if any(value < 0 for value in positions.values()):
        errors.append(f"EXECUTE_ORDER_ANCHOR_MISSING:{positions}")
    elif not (
        positions["verify"] < positions["setup"] < positions["path_count"]
        < positions["timer"] < positions["partition"] < positions["caller"]
    ):
        errors.append(f"EXECUTE_ORDER_INVALID:{positions}")
    for needle in (
        "create_runtime_script_binding_fixture",
        "setup_and_audit_shard_files",
        "fixture_path_checks = sum(",
    ):
        if needle not in preflight_source:
            errors.append(f"PREFLIGHT_MISSING:{needle}")
    for name in SCIENTIFIC_FUNCTIONS:
        if old_functions.get(name) != functions.get(name):
            errors.append(f"SCIENTIFIC_FUNCTION_CHANGED:{name}")
    if "enforce_post_11b_candidate_load_hard_gate" not in execute_source:
        errors.append("POST_11B_HARD_GATE_MISSING")
    else:
        gate = execute_source.find("enforce_post_11b_candidate_load_hard_gate")
        extraction = execute_source.find("extract_candidate_fastqs")
        caller = execute_source.find("run_caller_materializer")
        if not (0 <= gate < extraction < caller):
            errors.append("POST_11B_HARD_GATE_ORDER_INVALID")
    return errors


def negative_mutation_tests(
    v015_source: str,
    generated: str,
    amendment_sha: str,
    source_records: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    mutations: list[tuple[str, str]] = []
    def add(label: str, old: str, new: str) -> None:
        if generated.count(old) != 1:
            raise BuildError(f"mutation anchor {label} count {generated.count(old)} != 1")
        mutations.append((label, generated.replace(old, new, 1)))

    def add_first(label: str, old: str, new: str) -> None:
        count = generated.count(old)
        if count < 1:
            raise BuildError(f"mutation anchor {label} missing")
        mutations.append((label, generated.replace(old, new, 1)))
    add(
        "source_11d3_reverted_to_v015",
        f"SOURCE_11D3 = Path({source_records['11d3']['bound_path']!r})",
        f"SOURCE_11D3 = Path({str(V015_BOUND_SOURCES['11d3'][0])!r})",
    )
    add_first("candidate_path_anchor_reverted", NEW_CANDIDATE_FILENAME, OLD_CANDIDATE_FILENAME)
    add_first("window_path_anchor_reverted", NEW_WINDOW_FILENAME, OLD_WINDOW_FILENAME)
    add("normalized_sha_contract_changed", list(top_level_constants(generated)["EXPECTED_GENERATED_NORMALIZED_SHA256"].values())[0], "0" * 64)
    add("path_audit_function_removed", "def expected_runtime_path_anchor_lines(", "def expected_runtime_path_anchor_lines_REMOVED(")
    add("execute_path_check_count_removed", "runtime_path_checks = sum(", "runtime_path_checks_REMOVED = sum(")
    add(
        "result_root_reverted_to_v015",
        'PROJECT_ROOT / "results/15_stage15c_fullscale_bam_to_final" / RUN_ID / "v0.1.6"',
        'PROJECT_ROOT / "results/15_stage15c_fullscale_bam_to_final" / RUN_ID / "v0.1.5"',
    )
    add("analysis_run_id_changed_to_mapping", f'ANALYSIS_RUN_ID = {ANALYSIS_RUN_ID!r}', f'ANALYSIS_RUN_ID = {MAPPING_RUN_ID!r}')
    add("shards_changed_to_60", "SHARDS = 144", "SHARDS = 60")
    add("post_11b_hard_max_changed", "POST_11B_MAX_CANDIDATE_ROWS_PER_SHARD = 164204", "POST_11B_MAX_CANDIDATE_ROWS_PER_SHARD = 164205")
    add(
        "amendment_sha_changed",
        f"RUNTIME_SCRIPT_BINDING_AMENDMENT_SHA256 = {amendment_sha!r}",
        f"RUNTIME_SCRIPT_BINDING_AMENDMENT_SHA256 = {'f' * 64!r}",
    )
    add("bound_source_root_definition_removed", "BOUND_SOURCE_ROOT = Path(", "BOUND_SOURCE_ROOT_REMOVED = Path(")
    rows: list[dict[str, str]] = []
    for label, mutated in mutations:
        observed = "REJECT" if audit_runner_source(v015_source, mutated, amendment_sha, source_records) else "ACCEPT"
        rows.append({"test": label, "expected": "REJECT", "observed": observed, "status": "PASS" if observed == "REJECT" else "FAIL"})
    if any(row["status"] != "PASS" for row in rows):
        raise BuildError("negative mutation test failed")
    return rows


def dynamic_safety_tests(
    runner_path: Path,
    amendment_sha: str,
) -> list[dict[str, str]]:
    name = "rnatr_stage15c_v016_generated_runner_dynamic"
    module = import_module(runner_path, name)
    rows: list[dict[str, str]] = []
    try:
        for value, expected in ((POST_11B_HARD_MAX, "ACCEPT"), (POST_11B_HARD_MAX + 1, "REJECT")):
            passed, observed_max, offenders = module.candidate_load_gate_decision([value])
            observed = "ACCEPT" if passed else "REJECT"
            rows.append({
                "test": f"candidate_hard_gate_{value}",
                "expected": expected,
                "observed": observed,
                "status": "PASS" if observed == expected and observed_max == value else "FAIL",
            })
        amendment = module.verify_runtime_script_binding_amendment()
        rows.append({
            "test": "runtime_path_binding_amendment_real_project_verification",
            "expected": "PASS",
            "observed": "PASS" if amendment["amendment_sha256"] == amendment_sha else "FAIL",
            "status": "PASS" if amendment["amendment_sha256"] == amendment_sha else "FAIL",
        })
        with tempfile.TemporaryDirectory(prefix="rnatr_stage15c_v016_runner_fixture_") as temporary:
            root = Path(temporary)
            base = module.configure_modules()
            fixture = module.create_runtime_script_binding_fixture(base, root / "fixture")
            audit_path = root / "fixture.audit.tsv"
            fixture_rows = module.setup_and_audit_shard_files(base, [fixture], audit_path, "BUILDER_REAL_BASE_FIXTURE")
            checks = sum(int(row["path_binding_checks_passed"]) for row in fixture_rows)
            fixture_pass = (
                len(fixture_rows) == 3
                and checks == EXPECTED_PATH_CHECKS_PER_SHARD
                and all(row["status"] == "PASS" for row in fixture_rows)
            )
            rows.append({
                "test": "real_base_setup_shard_files_runtime_path_binding_fixture",
                "expected": f"PASS_3_ROWS_{EXPECTED_PATH_CHECKS_PER_SHARD}_CHECKS",
                "observed": f"PASS_3_ROWS_{checks}_CHECKS" if fixture_pass else "FAIL",
                "status": "PASS" if fixture_pass else "FAIL",
            })
        runtime_mutations = (
            (
                "mutated_candidate_runtime_path_rejected",
                "11d3",
                NEW_CANDIDATE_FILENAME,
                OLD_CANDIDATE_FILENAME,
            ),
            (
                "mutated_window_runtime_path_rejected",
                "11d3",
                NEW_WINDOW_FILENAME,
                OLD_WINDOW_FILENAME,
            ),
            (
                "mutated_benchmark_root_rejected",
                "11d3",
                NEW_BENCHMARK_ROOT,
                OLD_BENCHMARK_ROOT,
            ),
            (
                "mutated_analysis_to_mapping_run_id_rejected",
                "11b",
                ANALYSIS_RUN_ID,
                MAPPING_RUN_ID,
            ),
        )
        role_attribute = {
            "11b": "script_11b",
            "11d3": "script_11d3",
            "11e": "script_11e",
        }
        for test_name, role, old, new in runtime_mutations:
            with tempfile.TemporaryDirectory(
                prefix="rnatr_stage15c_v016_runner_mutation_"
            ) as mutation_temporary:
                mutation_root = Path(mutation_temporary)
                mutation_fixture = module.create_runtime_script_binding_fixture(
                    base, mutation_root / "fixture"
                )
                base.setup_shard_files([mutation_fixture])
                script_path = Path(getattr(mutation_fixture, role_attribute[role]))
                script_text = script_path.read_text(encoding="utf-8")
                if script_text.count(old) < 1:
                    raise BuildError(
                        f"dynamic mutation anchor missing: {test_name}: {old}"
                    )
                script_path.write_text(
                    script_text.replace(old, new, 1), encoding="utf-8"
                )
                rejected = False
                try:
                    module.audit_generated_runtime_scripts(
                        [mutation_fixture],
                        mutation_root / f"{test_name}.audit.tsv",
                        test_name,
                    )
                except Exception:
                    rejected = True
                rows.append({
                    "test": test_name,
                    "expected": "REJECT",
                    "observed": "REJECT" if rejected else "ACCEPT",
                    "status": "PASS" if rejected else "FAIL",
                })

        # Generate and audit the complete 144x3 runtime-script population in a
        # temporary tree. This is the exact pre-partition control-plane scale,
        # without reading or modifying the full BAM/FASTQ.
        with tempfile.TemporaryDirectory(
            prefix="rnatr_stage15c_v016_full144_fixture_"
        ) as full_temporary:
            full_root = Path(full_temporary)
            full_fixtures = []
            for index in range(SHARDS):
                fixture_shard = module.create_runtime_script_binding_fixture(
                    base, full_root / f"shard_{index:03d}"
                )
                fixture_shard.index = index
                fixture_shard.name = f"shard_{index:03d}"
                full_fixtures.append(fixture_shard)
            full_rows = module.setup_and_audit_shard_files(
                base,
                full_fixtures,
                full_root / "full_144x3_runtime_script.audit.tsv",
                "BUILDER_FULL_144X3_PREPARTITION_FIXTURE",
            )
            full_checks = sum(
                int(row["path_binding_checks_passed"]) for row in full_rows
            )
            role_counts = {
                role: sum(row["role"] == role for row in full_rows)
                for role in ("11b", "11d3", "11e")
            }
            full_pass = (
                len(full_rows) == SHARDS * 3
                and full_checks == EXPECTED_FULL_PATH_CHECKS
                and role_counts == {"11b": SHARDS, "11d3": SHARDS, "11e": SHARDS}
                and all(row["status"] == "PASS" for row in full_rows)
            )
            rows.append({
                "test": "full_144x3_runtime_script_generation_and_path_audit",
                "expected": f"PASS_{SHARDS * 3}_ROWS_{EXPECTED_FULL_PATH_CHECKS}_CHECKS",
                "observed": (
                    f"PASS_{len(full_rows)}_ROWS_{full_checks}_CHECKS"
                    if full_pass else
                    f"FAIL_{len(full_rows)}_ROWS_{full_checks}_CHECKS_{role_counts}"
                ),
                "status": "PASS" if full_pass else "FAIL",
            })
        # The generated module must define every uppercase global it loads.
        undefined = undefined_uppercase_globals(runner_path.read_text(encoding="utf-8"))
        rows.append({
            "test": "generated_runner_undefined_uppercase_globals",
            "expected": "NONE",
            "observed": "NONE" if not undefined else ";".join(sorted(undefined)),
            "status": "PASS" if not undefined else "FAIL",
        })
    finally:
        sys.modules.pop(name, None)
    if any(row["status"] != "PASS" for row in rows):
        raise BuildError(f"dynamic safety test failed: {rows}")
    return rows


def make_doc(amendment_sha: str, source_records: dict[str, dict[str, Any]]) -> bytes:
    lines = [
        "# RNA-TR-Scout Stage 15C runtime path-binding amendment v0.1.6",
        "",
        "## Defects addressed before v0.1.5 preflight",
        "",
        "Pro audit found that the v0.1.5 11d3 runtime template still pointed to the",
        "500k candidate/window FASTQ subpaths even though `create_shards()` used the",
        "full5312696 paths. The same audit found `BOUND_SOURCE_ROOT` referenced but not",
        "defined in v0.1.5, which would have failed at preflight bundle publication.",
        "Neither v0.1.5 preflight nor v0.1.5 full execution was started.",
        "",
        "## v0.1.6 path contract",
        "",
        f"- Analysis run ID: `{ANALYSIS_RUN_ID}`",
        f"- Mapping run ID: `{MAPPING_RUN_ID}`",
        f"- Runtime-path amendment SHA-256: `{amendment_sha}`",
        f"- Candidate benchmark root: `{NEW_BENCHMARK_ROOT}`",
        f"- Candidate FASTQ: `{NEW_CANDIDATE_FILENAME}`",
        f"- Window FASTQ: `{NEW_WINDOW_FILENAME}`",
        f"- Expected path checks: `{EXPECTED_PATH_CHECKS_PER_SHARD}` per shard / `{EXPECTED_FULL_PATH_CHECKS}` full run",
        "- All 432 generated scripts are audited before partition and timer start.",
        "- Generated scripts are normalized for shard-specific paths.env and checked",
        "  against frozen per-role SHA-256 values.",
        "- v0.1.4 failed partition and all v0.1.5 artifacts are not reused.",
        "",
        "## Bound sources",
    ]
    for role in ("11b", "11d3", "11e"):
        record = source_records[role]
        lines.extend([
            "",
            f"### {role}",
            f"- Source: `{record['source_path']}`",
            f"- Source SHA-256: `{record['source_sha256']}`",
            f"- Bound: `{record['bound_path']}`",
            f"- Bound SHA-256: `{record['bound_sha256']}`",
        ])
    lines.extend([
        "",
        "## Non-modification guarantees",
        "",
        "The amendment does not modify the active pipeline, SSOT, schema v0.4.2,",
        "caller v0.4.1, materializer v0.1.2, mapping BAM/FASTQ, accepted 500k",
        "results, or retained v0.1.4 failure provenance.",
        "",
    ])
    return "\n".join(lines).encode("utf-8")


def artifact_manifest(root: Path) -> None:
    rows = []
    output = root / "artifact_manifest.tsv"
    for path in sorted(p for p in root.rglob("*") if p.is_file() and p != output):
        rows.append({
            "relative_path": str(path.relative_to(root)),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        })
    write_tsv(output, rows, ["relative_path", "bytes", "sha256"])


def make_bundle(source_root: Path, target: Path) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(str(target) + f".part.{os.getpid()}")
    with tarfile.open(temporary, "w:gz", format=tarfile.PAX_FORMAT) as archive:
        archive.add(source_root, arcname=source_root.name)
    os.replace(temporary, target)
    digest = sha256_file(target)
    Path(str(target) + ".sha256").write_text(
        f"{digest}  {target.name}\n", encoding="utf-8"
    )
    return digest


def build() -> int:
    started = time.time()
    sys.dont_write_bytecode = True
    work_parent = Path(tempfile.mkdtemp(prefix="rnatr_stage15c_v016_builder_"))
    package = work_parent / "rnatr_stage15c_runtime_path_bound_full_runner_build_v0.1.6"
    package.mkdir(parents=True)
    success = False
    failure_text = "."
    installation: dict[str, str] = {}
    runner_sha = "."
    amendment_sha = "."
    source_records: dict[str, dict[str, Any]] = {}
    fixture_rows: list[dict[str, Any]] = []
    normalized_sha: dict[str, str] = {}
    mutation_rows: list[dict[str, str]] = []
    dynamic_rows: list[dict[str, str]] = []
    try:
        prior = verify_v015_evidence()
        source_records, bound_payloads = bind_runtime_sources()
        fixture_rows, normalized_sha = build_generated_fixture(source_records, bound_payloads)
        for role in source_records:
            source_records[role]["expected_generated_normalized_sha256"] = normalized_sha[role]
        amendment_payload = make_amendment_contract(
            source_records, fixture_rows, normalized_sha, prior
        )
        amendment_sha = sha256_bytes(amendment_payload)
        v015_source = V015_RUNNER_PROJECT.read_text(encoding="utf-8")
        generated = transform_runner(v015_source, amendment_sha, source_records, normalized_sha)
        compile(generated, str(RUNNER_DOWNLOAD), "exec")
        errors = audit_runner_source(v015_source, generated, amendment_sha, source_records)
        if errors:
            raise BuildError("generated runner static audit failed: " + ";".join(errors))
        mutation_rows = negative_mutation_tests(v015_source, generated, amendment_sha, source_records)

        for role in ("11b", "11d3", "11e"):
            installation[f"bound_{role}"] = install_exact_bytes(
                bound_payloads[role], Path(source_records[role]["bound_path"]), 0o755
            )
        installation["amendment"] = install_exact_bytes(
            amendment_payload, AMENDMENT_CONTRACT, 0o644
        )

        runner_payload = generated.encode("utf-8")
        temporary_runner = package / RUNNER_DOWNLOAD.name
        atomic_write(temporary_runner, runner_payload, 0o755)
        dynamic_rows = dynamic_safety_tests(temporary_runner, amendment_sha)
        runner_sha = sha256_file(temporary_runner)
        compile(temporary_runner.read_text(encoding="utf-8"), str(temporary_runner), "exec")
        final_errors = audit_runner_source(
            v015_source,
            temporary_runner.read_text(encoding="utf-8"),
            amendment_sha,
            source_records,
        )
        if final_errors:
            raise BuildError("final runner re-audit failed: " + ";".join(final_errors))
        if sha256_file(temporary_runner) != runner_sha:
            raise BuildError("runner bytes changed during tests")

        doc_payload = make_doc(amendment_sha, source_records)
        shutil.copy2(Path(__file__).resolve(), package / Path(__file__).name)
        atomic_write(package / AMENDMENT_CONTRACT.name, amendment_payload, 0o644)
        atomic_write(package / DOC_INSTALL.name, doc_payload, 0o644)
        for role in ("11b", "11d3", "11e"):
            atomic_write(
                package / Path(source_records[role]["bound_path"]).name,
                bound_payloads[role],
                0o755,
            )
        source_rows = []
        for role in ("11b", "11d3", "11e"):
            row = dict(source_records[role])
            row["transformations"] = json.dumps(row["transformations"], sort_keys=True)
            source_rows.append(row)
        write_tsv(
            package / "runtime_source_and_path_binding.tsv",
            source_rows,
            [
                "role", "source_path", "source_sha256", "bound_path",
                "bound_sha256", "bound_bytes", "analysis_run_id_occurrences",
                "obsolete_run_id_occurrences", "mapping_run_id_occurrences",
                "obsolete_runtime_path_token_occurrences", "transformations",
                "expected_generated_normalized_sha256", "bash_syntax_status",
            ],
        )
        write_tsv(
            package / "builder_fixture_runtime_path_audit.tsv",
            fixture_rows,
            list(fixture_rows[0]),
        )
        write_tsv(
            package / "negative_mutation_tests.tsv",
            mutation_rows,
            ["test", "expected", "observed", "status"],
        )
        write_tsv(
            package / "dynamic_safety_tests.tsv",
            dynamic_rows,
            ["test", "expected", "observed", "status"],
        )
        qc_rows = [
            ("builder_version", BUILDER_VERSION),
            ("runner_version", RUNNER_VERSION),
            ("analysis_run_id", ANALYSIS_RUN_ID),
            ("mapping_run_id", MAPPING_RUN_ID),
            ("read_coherent_shards", SHARDS),
            ("active_shard_concurrency", CONCURRENCY),
            ("caller_workers_per_shard", CALLER_WORKERS_PER_SHARD),
            ("validator_workers", VALIDATOR_WORKERS),
            ("post_11b_candidate_rows_per_shard_hard_max", POST_11B_HARD_MAX),
            ("v015_build_evidence", "PASS"),
            ("v015_preflight_executed", "false"),
            ("v015_full_execution_started", "false"),
            ("v015_runtime_path_defect_confirmed", "true"),
            ("v015_undefined_bound_source_root_confirmed", "true"),
            ("v016_bound_source_templates", len(source_records)),
            ("v016_bound_source_templates_status", "PASS"),
            ("builder_real_base_runtime_path_fixture", "PASS"),
            ("builder_fixture_rows", len(fixture_rows)),
            ("builder_fixture_path_checks", sum(int(row["path_binding_checks_passed"]) for row in fixture_rows)),
            ("expected_path_checks_per_shard", EXPECTED_PATH_CHECKS_PER_SHARD),
            ("expected_full_runtime_script_audit_rows", SHARDS * 3),
            ("expected_full_runtime_path_binding_checks", EXPECTED_FULL_PATH_CHECKS),
            ("generated_normalized_sha_contract", "PASS"),
            ("scientific_processing_functions_byte_identical_to_v015", "true"),
            ("negative_mutation_tests", "PASS"),
            ("negative_mutation_test_count", len(mutation_rows)),
            ("dynamic_safety_tests", "PASS"),
            ("dynamic_safety_test_count", len(dynamic_rows)),
            ("runtime_path_binding_amendment_sha256", amendment_sha),
            ("runner_sha256", runner_sha),
            ("full_5_31m_run_started", "false"),
            ("active_pipeline_modified", "false"),
            ("ssot_modified", "false"),
            ("build_status", "PASS"),
            ("next_gate", "RUN_GENERATED_V0.1.6_WITH_--preflight_ONLY"),
        ]
        write_metrics(package / "stage15c_runtime_path_bound_runner_build.qc.tsv", qc_rows)
        artifact_manifest(package)

        installation["builder"] = install_exact_bytes(
            Path(__file__).resolve().read_bytes(), BUILDER_INSTALL, 0o755
        )
        installation["runner"] = install_exact_bytes(
            temporary_runner.read_bytes(), RUNNER_INSTALL, 0o755
        )
        installation["runner_download"] = install_exact_bytes(
            temporary_runner.read_bytes(), RUNNER_DOWNLOAD, 0o755
        )
        installation["doc"] = install_exact_bytes(doc_payload, DOC_INSTALL, 0o644)
        BUILD_QC_ROOT.mkdir(parents=True, exist_ok=True)
        for name in (
            "stage15c_runtime_path_bound_runner_build.qc.tsv",
            "runtime_source_and_path_binding.tsv",
            "builder_fixture_runtime_path_audit.tsv",
            "negative_mutation_tests.tsv",
            "dynamic_safety_tests.tsv",
            "artifact_manifest.tsv",
        ):
            installation[f"qc::{name}"] = install_exact_bytes(
                (package / name).read_bytes(), BUILD_QC_ROOT / name, 0o644
            )
        success = True
    except Exception as exc:
        failure_text = f"{type(exc).__name__}: {exc}"
        (package / "failure.txt").write_text(
            failure_text + "\n\n" + traceback.format_exc(), encoding="utf-8"
        )
        artifact_manifest(package)
    bundle = SUCCESS_BUNDLE if success else FAILURE_BUNDLE
    bundle_sha = make_bundle(package, bundle)

    print("===== RNA-TR-Scout Stage 15C runtime-path-bound full runner build =====")
    print(f"build_status\t{'PASS' if success else 'FAIL'}")
    print(f"analysis_run_id\t{ANALYSIS_RUN_ID}")
    print(f"mapping_run_id\t{MAPPING_RUN_ID}")
    print(f"read_coherent_shards\t{SHARDS}")
    print(f"active_shard_concurrency\t{CONCURRENCY}")
    print(f"post_11b_candidate_rows_per_shard_hard_max\t{POST_11B_HARD_MAX}")
    print(f"v015_runtime_path_defect_confirmed\t{'true' if success else 'not_confirmed'}")
    print(f"v015_preflight_executed\tfalse")
    print(f"v016_runtime_path_binding\t{'PASS' if success else 'NOT_PASS'}")
    print(f"expected_full_runtime_script_audit_rows\t{SHARDS * 3}")
    print(f"expected_full_runtime_path_binding_checks\t{EXPECTED_FULL_PATH_CHECKS}")
    print(f"scientific_processing_functions_byte_identical_to_v015\t{'true' if success else 'not_confirmed'}")
    print(f"negative_mutation_tests\t{'PASS' if success else 'NOT_PASS'}")
    print(f"dynamic_safety_tests\t{'PASS' if success else 'NOT_PASS'}")
    print("full_5_31m_run_started\tfalse")
    print("active_pipeline_modified\tfalse")
    print("ssot_modified\tfalse")
    if success:
        print(f"RUNTIME_PATH_BINDING_AMENDMENT_SHA256\t{amendment_sha}")
        print(f"RUNNER\t{RUNNER_DOWNLOAD}")
        print(f"RUNNER_SHA256\t{runner_sha}")
        print(f"RUNNER_DOWNLOAD_INSTALLATION\t{installation.get('runner_download', '.')}")
        print("NEXT_GATE\tRUN_GENERATED_V0.1.6_WITH_--preflight_ONLY")
    else:
        print(f"failure\t{failure_text}")
    print(f"OUTPUT_BUNDLE\t{bundle}")
    print(f"OUTPUT_BUNDLE_SHA256\t{bundle_sha}")
    print(f"elapsed_seconds\t{time.time() - started:.6f}")
    return 0 if success else 1


def main() -> int:
    return build()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"BUILD_FAIL\t{type(exc).__name__}\t{exc}", file=sys.stderr)
        raise
