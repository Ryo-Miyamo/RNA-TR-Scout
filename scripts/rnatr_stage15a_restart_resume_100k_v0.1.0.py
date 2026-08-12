from __future__ import annotations

import argparse
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
from pathlib import Path
from typing import Iterable

STAGE_VERSION = "rnatr_stage15a_restart_resume_100k_v0.1.0"
PROJECT_ROOT = Path("/mnt/intelssd/rnatr_project")
RUN_ID = "ENCSR307SHM_pilot100k_mm2splice_v1"
SAMPLE_ID = "ENCSR307SHM"
VERSION = "v0.2.3_restart_resume_100k"
RESULT_ROOT = PROJECT_ROOT / "results/15_stage15a_bam_to_final" / RUN_ID / VERSION
QC_ROOT = PROJECT_ROOT / "qc/15_stage15a_bam_to_final" / RUN_ID / VERSION
LOG_ROOT = QC_ROOT / "logs"
TIMING_ROOT = QC_ROOT / "timing"
COMPARISON_ROOT = QC_ROOT / "comparison"
CONTRACT_ROOT = QC_ROOT / "contract"
CHECKPOINT_ROOT = RESULT_ROOT / "checkpoints"
PACKAGE_PART = RESULT_ROOT / "package_resume.part"
PACKAGE_FINAL = RESULT_ROOT / "package_resume"
SOURCE_VERSION = "v0.2.2.1_performance"
SOURCE_RESULT = PROJECT_ROOT / "results/15_stage15a_bam_to_final" / RUN_ID / SOURCE_VERSION
SOURCE_QC_ROOT = PROJECT_ROOT / "qc/15_stage15a_bam_to_final" / RUN_ID / SOURCE_VERSION
SOURCE_PACKAGE = SOURCE_RESULT / "package_performance"
SOURCE_RUNNER = PROJECT_ROOT / "scripts/rnatr_stage15a_run_performance_100k_v0.2.2.1.py"
SOURCE_RUNNER_SHA256 = "7bfb7018cea80cd92854882751cffb49bea817296f69866801a64f9529c5e1a8"
SOURCE_QC = SOURCE_QC_ROOT / "stage15a_performance_100k.qc.tsv"
SOURCE_QC_SHA256 = "401cfa9d9e524ceebfef9f6665d0f2b435627133c40cfcb6b8df7d989e4ac733"
SOURCE_PACKAGE_MANIFEST = SOURCE_PACKAGE / "package_manifest.tsv"
SOURCE_PACKAGE_MANIFEST_SHA256 = "0e74e2eaf8cac0bc75ca0c89a725576946ac61476bce4cf4e76951402f4c13e3"
SSOT_GUARDS = {
    PROJECT_ROOT / "metadata/ssot/rnatr_ssot.py": "90acacb80a281b9c7a3a60ef9771c987fd515ab09825ac969787708d27b6bb33",
    PROJECT_ROOT / "metadata/ssot/rnatr_ssot.sqlite": "93e20ba78fe63f91380bfb788e56a2317afe2d8214976526386c2a39d01887d9",
}
EXPECTED_FINAL_ROWS = {
    "general_repeat_calls": 388_571,
    "read_evidence": 388_571,
    "repeat_events": 160_297,
    "repeat_segments": 161_265,
    "repeat_interruptions": 848,
}
TABLES = [
    "general_repeat_calls",
    "read_evidence",
    "repeat_events",
    "repeat_segments",
    "repeat_interruptions",
]
INTERRUPTED_MARKER = CHECKPOINT_ROOT / "INTENTIONAL_INTERRUPTION.json"
COMPLETE_MARKER = CHECKPOINT_ROOT / "RESUME_COMPLETE.json"
CHECKPOINT_MANIFEST = CHECKPOINT_ROOT / "checkpoint_manifest.tsv"


def utc_now() -> str:
    import datetime as dt
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def ensure_file(path: Path) -> None:
    if not path.is_file() or path.stat().st_size <= 0:
        raise FileNotFoundError(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def logical_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def data_rows(path: Path) -> int:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", newline="") as handle:
        return max(0, sum(1 for _ in handle) - 1)


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


def read_dict_tsv(path: Path) -> list[dict[str, str]]:
    ensure_file(path)
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return list(reader)


def load_source_module():
    ensure_file(SOURCE_RUNNER)
    observed = sha256_file(SOURCE_RUNNER)
    if observed != SOURCE_RUNNER_SHA256:
        raise RuntimeError(f"source runner SHA mismatch: {observed}")
    spec = importlib.util.spec_from_file_location("rnatr_stage15a_v0221_source", SOURCE_RUNNER)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot import source runner")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.STAGE_VERSION = STAGE_VERSION
    module.RESULT_ROOT = RESULT_ROOT
    module.QC_ROOT = QC_ROOT
    module.LOG_ROOT = LOG_ROOT
    module.TIMING_ROOT = TIMING_ROOT
    module.COMPARISON_ROOT = COMPARISON_ROOT
    module.CONTRACT_ROOT = CONTRACT_ROOT
    module.MARKER_ROOT = CHECKPOINT_ROOT
    module.SHARDS_ROOT = RESULT_ROOT / "shards"
    module.PACKAGE_PART = PACKAGE_PART
    module.PACKAGE_FINAL = PACKAGE_FINAL
    module.REFERENCE_PACKAGE = SOURCE_PACKAGE
    module.EXPECTED_FINAL_ROWS = dict(EXPECTED_FINAL_ROWS)
    module.SSOT_GUARDS = dict(SSOT_GUARDS)
    return module


def verify_package_manifest() -> None:
    ensure_file(SOURCE_PACKAGE_MANIFEST)
    if sha256_file(SOURCE_PACKAGE_MANIFEST) != SOURCE_PACKAGE_MANIFEST_SHA256:
        raise RuntimeError("source package manifest SHA mismatch")
    rows = read_dict_tsv(SOURCE_PACKAGE_MANIFEST)
    if len(rows) != 10:
        raise RuntimeError(f"source package manifest row count != 10: {len(rows)}")
    for row in rows:
        path = SOURCE_PACKAGE / row["artifact"]
        ensure_file(path)
        if path.stat().st_size != int(row["bytes"]):
            raise RuntimeError(f"source package byte mismatch: {path}")
        if sha256_file(path) != row["sha256"]:
            raise RuntimeError(f"source package SHA mismatch: {path}")
        if data_rows(path) != int(row["rows"]):
            raise RuntimeError(f"source package row mismatch: {path}")


def verify_contract() -> dict[Path, str]:
    ensure_file(SOURCE_QC)
    if sha256_file(SOURCE_QC) != SOURCE_QC_SHA256:
        raise RuntimeError("source v0.2.2.1 QC SHA mismatch")
    metrics = read_metrics(SOURCE_QC)
    required = {
        "audit_status": "PASS",
        "correctness_status": "PASS",
        "performance_implementation_status": "PASS",
        "package_exact_logical_parity": "true",
        "frozen_tsv_validators": "PASS",
        "frozen_package_validator_postpublication": "PASS",
        "atomic_publication": "PASS",
        "active_pipeline_modified": "false",
        "ssot_modified": "false",
        "full_5_31m_run_started": "false",
        "next_gate": "RUN_STAGE15A_RESTART_AND_DETERMINISTIC_250K_SCALING_NOT_FULL_5_31M",
    }
    for key, expected in required.items():
        if metrics.get(key) != expected:
            raise RuntimeError(f"source gate mismatch {key}: {metrics.get(key)} != {expected}")
    for path, expected in SSOT_GUARDS.items():
        ensure_file(path)
        observed = sha256_file(path)
        if observed != expected:
            raise RuntimeError(f"SSOT guard mismatch: {path}: {observed}")
    module = load_source_module()
    active_before: dict[Path, str] = {}
    for path, expected in module.ACTIVE_GUARDS.items():
        ensure_file(path)
        observed = sha256_file(path)
        if observed != expected:
            raise RuntimeError(f"active guard mismatch: {path}: {observed}")
        active_before[path] = observed
    verify_package_manifest()
    if shutil.disk_usage(PROJECT_ROOT).free < 3 * 1024**3:
        raise RuntimeError("less than 3 GiB free space under project root")
    return active_before


def source_shard_root(index: int) -> Path:
    return SOURCE_RESULT / "shards" / f"shard_{index:03d}"


def source_project(index: int) -> Path:
    return source_shard_root(index) / "project"


def source_calls(index: int) -> Path:
    return source_shard_root(index) / "caller/general_repeat_calls.v0.4.0.tsv.gz"


def source_caller_qc(index: int) -> Path:
    return source_shard_root(index) / "caller/general_repeat_integration.qc.tsv"


def source_package_plain(index: int) -> Path:
    return source_shard_root(index) / "package_plain"


def choose_interruption_shard() -> int:
    candidates: list[tuple[int, int]] = []
    for index in range(12):
        metrics = read_metrics(source_caller_qc(index))
        if metrics.get("audit_status") != "PASS":
            raise RuntimeError(f"source caller QC not PASS: shard_{index:03d}")
        candidates.append((int(metrics["input_job_rows"]), index))
    candidates.sort(reverse=True)
    return candidates[0][1]


def make_shards(module):
    shards = []
    for index in range(12):
        name = f"shard_{index:03d}"
        src_root = source_shard_root(index)
        root = RESULT_ROOT / "shards" / name
        project = src_root / "project"
        raw_root = src_root / "raw_root"
        bam = project / "results/11_mapping" / RUN_ID / f"{RUN_ID}.sorted.bam"
        candidate_fastq = raw_root / "benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_candidates_v0.3.1/ENCFF260PGB.pilot_100k.rnatr_candidate_all.fastq.gz"
        script_dir = src_root / "frozen_scripts"
        shard = module.Shard(
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
        shards.append(shard)
    return shards


def checkpoint_artifacts(module, shards, interrupted_index: int, fresh_caller: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for shard in shards:
        upstream = [
            ("bam", shard.bam),
            ("candidate_fastq", shard.candidate_fastq),
            ("assignment", shard.assignment_path),
            ("projection", shard.projection_path),
            ("motif_jobs", shard.jobs_path),
        ]
        for role, path in upstream:
            ensure_file(path)
            rows.append({
                "checkpoint_stage": "UPSTREAM_ADOPTED",
                "shard": shard.name,
                "role": role,
                "path": str(path),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "provenance": SOURCE_VERSION,
            })
        caller_path = fresh_caller if shard.index == interrupted_index else source_calls(shard.index)
        ensure_file(caller_path)
        rows.append({
            "checkpoint_stage": "CALLER_COMPLETE",
            "shard": shard.name,
            "role": "general_repeat_calls",
            "path": str(caller_path),
            "bytes": caller_path.stat().st_size,
            "sha256": sha256_file(caller_path),
            "provenance": "FRESH_PRE_INTERRUPTION" if shard.index == interrupted_index else SOURCE_VERSION,
        })
        if shard.index != interrupted_index:
            for table in TABLES:
                path = source_package_plain(shard.index) / f"{table}.tsv"
                ensure_file(path)
                rows.append({
                    "checkpoint_stage": "MATERIALIZER_COMPLETE",
                    "shard": shard.name,
                    "role": table,
                    "path": str(path),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                    "provenance": SOURCE_VERSION,
                })
            qc = source_package_plain(shard.index) / "materialization.qc.tsv"
            ensure_file(qc)
            rows.append({
                "checkpoint_stage": "MATERIALIZER_COMPLETE",
                "shard": shard.name,
                "role": "materialization_qc",
                "path": str(qc),
                "bytes": qc.stat().st_size,
                "sha256": sha256_file(qc),
                "provenance": SOURCE_VERSION,
            })
    return rows


def validate_checkpoint_manifest(path: Path) -> int:
    rows = read_dict_tsv(path)
    if not rows:
        raise RuntimeError("empty checkpoint manifest")
    for row in rows:
        artifact = Path(row["path"])
        ensure_file(artifact)
        if artifact.stat().st_size != int(row["bytes"]):
            raise RuntimeError(f"checkpoint byte mismatch: {artifact}")
        if sha256_file(artifact) != row["sha256"]:
            raise RuntimeError(f"checkpoint SHA mismatch: {artifact}")
    return len(rows)


def safe_symlink(source: Path, destination: Path) -> None:
    ensure_file(source) if source.is_file() else None
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        if destination.resolve() != source.resolve():
            raise RuntimeError(f"unexpected existing symlink: {destination}")
        return
    if destination.exists():
        raise RuntimeError(f"refusing existing path: {destination}")
    destination.symlink_to(source, target_is_directory=source.is_dir())


def run_command(label: str, command: list[str], log: Path, timing: Path) -> float:
    log.parent.mkdir(parents=True, exist_ok=True)
    timing.parent.mkdir(parents=True, exist_ok=True)
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
        tail = "\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-40:])
        raise RuntimeError(f"{label} failed ({proc.returncode}): {log}\n{tail}")
    return elapsed


def compare_artifact(candidate: Path, reference: Path, role: str) -> dict[str, object]:
    ensure_file(candidate)
    ensure_file(reference)
    candidate_rows = data_rows(candidate)
    reference_rows = data_rows(reference)
    candidate_logical = logical_sha256(candidate)
    reference_logical = logical_sha256(reference)
    equal = candidate_rows == reference_rows and candidate_logical == reference_logical
    if not equal:
        raise RuntimeError(f"restart artifact logical mismatch: {role}")
    return {
        "role": role,
        "candidate_rows": candidate_rows,
        "reference_rows": reference_rows,
        "candidate_raw_sha256": sha256_file(candidate),
        "reference_raw_sha256": sha256_file(reference),
        "candidate_logical_sha256": candidate_logical,
        "reference_logical_sha256": reference_logical,
        "logical_equal": str(equal).lower(),
    }


def verify_unchanged(active_before: dict[Path, str]) -> None:
    rows = []
    for path, before in active_before.items():
        after = sha256_file(path)
        status = "PASS" if before == after else "FAIL"
        rows.append({"path": str(path), "before_sha256": before, "after_sha256": after, "status": status})
        if status != "PASS":
            raise RuntimeError(f"active source changed: {path}")
    write_dict_tsv(CONTRACT_ROOT / "active_guards_after.tsv", rows)
    ssot_rows = []
    for path, expected in SSOT_GUARDS.items():
        observed = sha256_file(path)
        status = "PASS" if observed == expected else "FAIL"
        ssot_rows.append({"path": str(path), "expected_sha256": expected, "observed_sha256": observed, "status": status})
        if status != "PASS":
            raise RuntimeError(f"SSOT changed: {path}")
    write_dict_tsv(CONTRACT_ROOT / "ssot_guards_after.tsv", ssot_rows)


def prepare() -> int:
    if RESULT_ROOT.exists() or QC_ROOT.exists():
        raise RuntimeError(f"restart test root already exists; preserve it: {RESULT_ROOT}")
    for directory in (RESULT_ROOT, QC_ROOT, LOG_ROOT, TIMING_ROOT, COMPARISON_ROOT, CONTRACT_ROOT, CHECKPOINT_ROOT):
        directory.mkdir(parents=True, exist_ok=True)
    active_before = verify_contract()
    module = load_source_module()
    shards = make_shards(module)
    interrupted_index = choose_interruption_shard()
    interrupted_name = f"shard_{interrupted_index:03d}"

    for shard in shards:
        shard.root.mkdir(parents=True, exist_ok=True)
        (shard.root / "SOURCE_PROJECT.txt").write_text(str(shard.project) + "\n", encoding="utf-8")
        if shard.index != interrupted_index:
            safe_symlink(source_shard_root(shard.index) / "caller", shard.root / "caller")
            safe_symlink(source_package_plain(shard.index), shard.root / "package_plain")

    interrupted_shard = shards[interrupted_index]
    fresh_caller = interrupted_shard.root / "caller/general_repeat_calls.v0.4.0.tsv.gz"
    caller_elapsed = run_command(
        "fresh_caller_before_interruption",
        [
            sys.executable,
            str(module.PERF_CALLER),
            "--project-root", str(interrupted_shard.project),
            "--outdir", str(interrupted_shard.root / "caller"),
            "--workers", "2",
        ],
        LOG_ROOT / "prepare/fresh_caller.log",
        TIMING_ROOT / "prepare/fresh_caller.time_v.txt",
    )
    caller_compare = compare_artifact(fresh_caller, source_calls(interrupted_index), f"{interrupted_name}.caller")
    write_dict_tsv(COMPARISON_ROOT / "fresh_caller_pre_interruption.tsv", [caller_compare])

    checkpoint_rows = checkpoint_artifacts(module, shards, interrupted_index, fresh_caller)
    write_dict_tsv(CHECKPOINT_MANIFEST, checkpoint_rows)
    checkpoint_count = validate_checkpoint_manifest(CHECKPOINT_MANIFEST)
    if PACKAGE_PART.exists() or PACKAGE_FINAL.exists():
        raise RuntimeError("package was unexpectedly published before injected interruption")

    interrupted_payload = {
        "stage_version": STAGE_VERSION,
        "timestamp_utc": utc_now(),
        "interruption_type": "INTENTIONAL_AFTER_FRESH_CALLER_BEFORE_MATERIALIZER",
        "interrupted_shard": interrupted_name,
        "fresh_caller_elapsed_seconds": caller_elapsed,
        "checkpoint_rows": checkpoint_count,
        "partial_package_published": False,
        "expected_exit_code": 75,
    }
    INTERRUPTED_MARKER.write_text(json.dumps(interrupted_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_metrics(
        QC_ROOT / "stage15a_restart_prepare.qc.tsv",
        [
            ("stage_version", STAGE_VERSION),
            ("source_performance_version", SOURCE_VERSION),
            ("interrupted_shard", interrupted_name),
            ("fresh_caller_logical_parity", caller_compare["logical_equal"]),
            ("fresh_caller_elapsed_seconds", caller_elapsed),
            ("checkpoint_rows", checkpoint_count),
            ("adopted_materializer_shards", 11),
            ("pending_materializer_shards", 1),
            ("partial_package_published", "false"),
            ("intentional_interruption_status", "PASS"),
            ("expected_exit_code", 75),
        ],
    )
    write_dict_tsv(
        CONTRACT_ROOT / "active_guards_before.tsv",
        [{"path": str(path), "sha256": digest, "status": "PASS"} for path, digest in active_before.items()],
    )
    print("STAGE15A_RESTART_PREPARE_INTENTIONAL_STOP")
    print(f"interrupted_shard\t{interrupted_name}")
    print(f"checkpoint_rows\t{checkpoint_count}")
    print("partial_package_published\tfalse")
    return 75


def negative_checkpoint_test() -> str:
    rows = read_dict_tsv(CHECKPOINT_MANIFEST)
    fixture = QC_ROOT / "negative_checkpoint_fixture.tsv"
    mutated = [dict(row) for row in rows]
    mutated[0]["sha256"] = "0" * 64
    write_dict_tsv(fixture, mutated)
    try:
        validate_checkpoint_manifest(fixture)
    except RuntimeError:
        return "PASS"
    raise RuntimeError("negative checkpoint fixture was not rejected")


def resume() -> int:
    active_before = verify_contract()
    module = load_source_module()
    if COMPLETE_MARKER.is_file():
        marker = json.loads(COMPLETE_MARKER.read_text(encoding="utf-8"))
        manifest = PACKAGE_FINAL / "package_manifest.tsv"
        ensure_file(manifest)
        observed = sha256_file(manifest)
        if observed != marker["package_manifest_sha256"]:
            raise RuntimeError("completed package manifest changed before no-op resume")
        write_metrics(
            QC_ROOT / "stage15a_restart_noop.qc.tsv",
            [
                ("stage_version", STAGE_VERSION),
                ("resume_mode", "NOOP_COMPLETE_CHECKPOINT"),
                ("package_manifest_sha256", observed),
                ("package_unchanged", "true"),
                ("audit_status", "PASS"),
            ],
        )
        print("STAGE15A_RESTART_RESUME_NOOP_PASS")
        return 0

    ensure_file(INTERRUPTED_MARKER)
    interruption = json.loads(INTERRUPTED_MARKER.read_text(encoding="utf-8"))
    interrupted_name = interruption["interrupted_shard"]
    interrupted_index = int(interrupted_name.split("_")[-1])
    checkpoint_count = validate_checkpoint_manifest(CHECKPOINT_MANIFEST)
    negative_status = negative_checkpoint_test()
    shards = make_shards(module)

    for shard in shards:
        shard.root.mkdir(parents=True, exist_ok=True)
        if shard.index != interrupted_index:
            safe_symlink(source_shard_root(shard.index) / "caller", shard.root / "caller")
            safe_symlink(source_package_plain(shard.index), shard.root / "package_plain")

    interrupted_shard = shards[interrupted_index]
    fresh_calls = interrupted_shard.root / "caller/general_repeat_calls.v0.4.0.tsv.gz"
    ensure_file(fresh_calls)
    materializer_elapsed = run_command(
        "resume_missing_materializer",
        [
            sys.executable,
            str(module.PERF_MATERIALIZER),
            "--project-root", str(interrupted_shard.project),
            "--calls", str(fresh_calls),
            "--schema-dir", str(module.SCHEMA_DIR),
            "--outdir", str(interrupted_shard.root / "package_plain"),
            "--sample-id", SAMPLE_ID,
        ],
        LOG_ROOT / "resume/materializer.log",
        TIMING_ROOT / "resume/materializer.time_v.txt",
    )

    materializer_comparisons = []
    for table in TABLES:
        materializer_comparisons.append(
            compare_artifact(
                interrupted_shard.root / "package_plain" / f"{table}.tsv",
                source_package_plain(interrupted_index) / f"{table}.tsv",
                f"{interrupted_name}.{table}",
            )
        )
    write_dict_tsv(COMPARISON_ROOT / "resumed_materializer_shard.tsv", materializer_comparisons)

    source_materializer_timing = read_dict_tsv(SOURCE_QC_ROOT / "15AP5_materializer_plain_shards.per_shard.tsv")
    max_source_materializer = max(float(row["elapsed_seconds"]) for row in source_materializer_timing)
    merge_wall, merge_plain_wall, gzip_wall, _ = module.merge_packages(
        shards, materializer_wall=max(max_source_materializer, materializer_elapsed)
    )
    validator_wall, _ = module.run_all_validators_prepublication()
    publish_wall, _ = module.publish_verified_package()
    frozen_seconds, frozen_status = module.run_frozen_package_validator_postpublication()
    failure_parity = module.validator_missing_artifact_failure_parity()
    _, logical_parity, raw_parity = module.compare_package()
    if not logical_parity:
        raise RuntimeError("resumed package does not match v0.2.2.1 logically")
    verify_unchanged(active_before)

    final_manifest = PACKAGE_FINAL / "package_manifest.tsv"
    ensure_file(final_manifest)
    final_manifest_sha = sha256_file(final_manifest)
    complete_payload = {
        "stage_version": STAGE_VERSION,
        "timestamp_utc": utc_now(),
        "interrupted_shard": interrupted_name,
        "package_manifest_sha256": final_manifest_sha,
        "package_exact_logical_parity": True,
        "package_exact_raw_parity": raw_parity,
        "restart_resume_validated": True,
    }
    COMPLETE_MARKER.write_text(json.dumps(complete_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_metrics(
        QC_ROOT / "stage15a_restart_resume_100k.qc.tsv",
        [
            ("stage_version", STAGE_VERSION),
            ("run_id", RUN_ID),
            ("source_performance_version", SOURCE_VERSION),
            ("restart_scope", "FRESH_CALLER_CHECKPOINT_TO_FINAL_WITH_SELECTIVE_MATERIALIZER_RESUME"),
            ("interrupted_shard", interrupted_name),
            ("checkpoint_rows_verified", checkpoint_count),
            ("checkpoint_negative_fixture_rejected", negative_status),
            ("completed_caller_reused_on_resume", "true"),
            ("adopted_upstream_shards", 12),
            ("adopted_caller_shards", 11),
            ("fresh_pre_interruption_caller_shards", 1),
            ("adopted_materializer_shards", 11),
            ("resumed_materializer_shards", 1),
            ("partial_package_published_before_resume", "false"),
            ("resumed_materializer_logical_parity", "true"),
            ("package_exact_logical_parity", str(logical_parity).lower()),
            ("package_exact_raw_parity", str(raw_parity).lower()),
            ("frozen_tsv_validators", "PASS"),
            ("parallel_exact_component_package_validator", "PASS"),
            ("frozen_package_validator_postpublication", frozen_status),
            ("negative_fixture_failure_parity", failure_parity),
            ("atomic_publication", "PASS"),
            ("materializer_resume_seconds", materializer_elapsed),
            ("merge_wall_seconds", merge_wall),
            ("merge_plain_seconds", merge_plain_wall),
            ("gzip_seconds", gzip_wall),
            ("validator_seconds", validator_wall),
            ("publication_seconds", publish_wall),
            ("frozen_postpublication_validator_seconds", frozen_seconds),
            ("active_pipeline_modified", "false"),
            ("ssot_modified", "false"),
            ("full_5_31m_run_started", "false"),
            ("restart_resume_validated", "true"),
            ("stage15a_overall_status", "IN_PROGRESS"),
            ("audit_status", "PASS"),
            ("next_gate", "BUILD_AND_RUN_DETERMINISTIC_250K_BAM_INPUT_SCALING_NOT_FULL_5_31M"),
        ],
    )
    print("STAGE15A_RESTART_RESUME_100K_PASS")
    print(f"interrupted_shard\t{interrupted_name}")
    print(f"package_exact_logical_parity\t{str(logical_parity).lower()}")
    print("restart_resume_validated\ttrue")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prepare", action="store_true")
    group.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    return prepare() if args.prepare else resume()


if __name__ == "__main__":
    raise SystemExit(main())
