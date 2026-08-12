#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Any

VERSION = "rnatr_golden_regression_suite_v0.1.4"
MANIFEST_REL = Path("validation/golden/v0.1.0/golden_suite_manifest.json")


class GoldenError(RuntimeError):
    pass


def sha256_file(path: Path, chunk: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def ensure_regular(path: Path) -> None:
    if not path.is_file() or path.is_symlink():
        raise GoldenError(f"required regular file missing/invalid: {path}")


def read_tsv(path: Path) -> list[dict[str, str]]:
    ensure_regular(path)
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def write_tsv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            delimiter="\t",
            fieldnames=fields,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def data_rows(path: Path) -> int:
    with path.open("rb") as fh:
        return max(0, sum(1 for _ in fh) - 1)


def load_manifest(project_root: Path) -> dict[str, Any]:
    path = project_root / MANIFEST_REL
    ensure_regular(path)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("golden_suite_version") != VERSION:
        raise GoldenError("unsupported golden-suite manifest version")
    return manifest


def run_command(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    expected_returncodes: set[int] | None = None,
    log: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    expected_returncodes = {0} if expected_returncodes is None else expected_returncodes
    proc = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
    )
    if log is not None:
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(proc.stdout, encoding="utf-8")
    if proc.returncode not in expected_returncodes:
        raise GoldenError(
            f"command failed rc={proc.returncode}: {' '.join(command)}\n"
            f"{proc.stdout[-4000:]}"
        )
    return proc


def verify_hash_guard(project_root: Path, rel: str, expected: str) -> dict[str, Any]:
    path = project_root / rel
    ensure_regular(path)
    actual = sha256_file(path)
    status = "PASS" if actual == expected else "FAIL"
    if status != "PASS":
        raise GoldenError(f"hash guard failed: {rel}: {actual} != {expected}")
    return {
        "path": rel,
        "bytes": path.stat().st_size,
        "expected_sha256": expected,
        "actual_sha256": actual,
        "status": status,
    }


def fixed_binding_hits(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    forbidden = (
        "/mnt/intelssd",
        "/media/",
        "ENCSR307SHM",
        "ENCFF260PGB",
        "/home/tokushimaneuro02",
    )
    return [token for token in forbidden if token in text]



def has_absolute_path(obj: Any) -> bool:
    if isinstance(obj, dict):
        return any(has_absolute_path(value) for value in obj.values())
    if isinstance(obj, list):
        return any(has_absolute_path(value) for value in obj)
    if isinstance(obj, str):
        return obj.startswith("/") or (
            len(obj) >= 3 and obj[1] == ":" and obj[2] in {"/", "\\"}
        )
    return False


def unit_attempt_count(work_root: Path) -> int:
    units = work_root / "units"
    if not units.is_dir():
        return 0
    return sum(
        1
        for path in units.glob("shard_*/attempt_*")
        if path.is_dir()
    )


def accepted_completed_shard_drift_rejection(output: str) -> bool:
    accepted = (
        "completed shard scientific table drift",
        "unit package validator failed",
        "completed shard manifest SHA drift",
        "completed shard input guard mismatch",
    )
    return any(token in output for token in accepted)

def verify_resource_manifest(project_root: Path, rel: str) -> int:
    path = project_root / rel
    ensure_regular(path)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    checked = 0
    for section in ("components", "catalogs", "production_code"):
        mapping = manifest.get(section)
        if not isinstance(mapping, dict) or not mapping:
            raise GoldenError(f"resource manifest lacks {section}")
        for role, entry in mapping.items():
            relative = Path(str(entry.get("relative_path", "")))
            if relative.is_absolute() or ".." in relative.parts or not relative.parts:
                raise GoldenError(f"unsafe resource relative path: {section}:{role}")
            resource = project_root / relative
            ensure_regular(resource)
            if sha256_file(resource) != entry.get("sha256"):
                raise GoldenError(f"resource SHA drift: {section}:{role}:{resource}")
            checked += 1
    return checked



def verify_freeze_manifest(project_root: Path, rel: str) -> int:
    manifest_path = project_root / rel
    rows = read_tsv(manifest_path)
    if not rows:
        raise GoldenError("Core Freeze manifest is empty")
    seen: set[str] = set()
    for row in rows:
        raw = row.get("path", "")
        path_rel = Path(raw)
        if not raw or path_rel.is_absolute() or ".." in path_rel.parts or raw in seen:
            raise GoldenError(f"unsafe/duplicate Core Freeze manifest path: {raw!r}")
        seen.add(raw)
        path = project_root / path_rel
        ensure_regular(path)
        if path.stat().st_size != int(row["bytes"]):
            raise GoldenError(f"Core Freeze manifest size drift: {path}")
        if sha256_file(path) != row["sha256"]:
            raise GoldenError(f"Core Freeze manifest SHA drift: {path}")
    return len(rows)


def validate_sidecar_example_contract(example: dict[str, Any], contract: dict[str, Any]) -> None:
    if example.get("contract_version") != contract.get("contract_version"):
        raise GoldenError("biology-sidecar contract version mismatch")
    core = example.get("core_reference")
    sidecar = example.get("sidecar")
    identity = example.get("identity_example")
    if not isinstance(core, dict) or not isinstance(sidecar, dict) or not isinstance(identity, dict):
        raise GoldenError("biology-sidecar example lacks required object sections")
    for field in contract["core_reference_required"]:
        value = core.get(field)
        if not isinstance(value, str) or not value:
            raise GoldenError(f"biology-sidecar core reference missing: {field}")
    core_sha = core["core_result_manifest_sha256"]
    if not re.fullmatch(r"[0-9a-f]{64}", core_sha):
        raise GoldenError("biology-sidecar Core manifest SHA is invalid")
    required_sidecar = contract["sidecar_required"]
    for field in required_sidecar:
        value = sidecar.get(field)
        if not isinstance(value, str) or not value:
            raise GoldenError(f"biology-sidecar field missing: {field}")
    if sidecar["validation_status"] not in required_sidecar["validation_status"]:
        raise GoldenError("biology-sidecar validation status is invalid")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", sidecar["created_utc"]):
        raise GoldenError("biology-sidecar created_utc is not fixed RFC3339 UTC")
    read_identity = identity.get("read_identity", {})
    evidence_identity = identity.get("evidence_identity", {})
    locus_identity = identity.get("locus_identity", {})
    if read_identity.get("core_result_manifest_sha256") != core_sha:
        raise GoldenError("biology-sidecar read identity Core SHA mismatch")
    if evidence_identity.get("core_result_manifest_sha256") != core_sha:
        raise GoldenError("biology-sidecar evidence identity Core SHA mismatch")
    for field in contract["identity_scope"]["read_identity"]:
        if field not in read_identity:
            raise GoldenError(f"biology-sidecar read identity lacks {field}")
    for field in contract["identity_scope"]["evidence_identity"]:
        if field not in evidence_identity:
            raise GoldenError(f"biology-sidecar evidence identity lacks {field}")
    for field in contract["identity_scope"]["locus_identity"]:
        if field not in locus_identity:
            raise GoldenError(f"biology-sidecar locus identity lacks {field}")
    if identity.get("molecule_identity_asserted") is not False:
        raise GoldenError("biology-sidecar improperly asserts molecule identity")
    if example.get("core_five_tables_immutable") is not True:
        raise GoldenError("biology-sidecar does not preserve Core-table immutability")
    if example.get("reverse_traceability_required") is not True:
        raise GoldenError("biology-sidecar reverse traceability is not required")
    if has_absolute_path(example):
        raise GoldenError("portable biology-sidecar example contains absolute path")


def tier0_static(
    project_root: Path,
    manifest: dict[str, Any],
    qc_root: Path,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rel, expected in manifest["tier0"]["hash_guards"].items():
        rows.append(verify_hash_guard(project_root, rel, expected))

    pipeline = read_tsv(project_root / manifest["tier0"]["current_pipeline"])
    if (
        len(pipeline) != 1
        or pipeline[0].get("stage_key")
        != "CORE_GENERIC_SHARDED_BAM_FASTQ_TO_FINAL"
    ):
        raise GoldenError("current pipeline is not the one-row generic Core")

    for rel in manifest["tier0"]["public_code_no_fixed_binding"]:
        path = project_root / rel
        ensure_regular(path)
        hits = fixed_binding_hits(path)
        if hits:
            raise GoldenError(f"public fixed binding found: {path}: {hits}")

    resource_count = verify_resource_manifest(
        project_root, manifest["tier0"]["resource_manifest"]
    )
    freeze_manifest_count = verify_freeze_manifest(
        project_root, manifest["tier0"]["freeze_manifest"]
    )

    result_contract = json.loads(
        (project_root / manifest["tier0"]["result_manifest_contract"]).read_text(
            encoding="utf-8"
        )
    )
    expected_keys = {
        "read_id", "target_source", "target_region_id", "locus_id",
        "evidence_id", "repeat_event_id", "repeat_call_id",
        "interruption_id", "caller_record_id",
    }
    if not expected_keys.issubset(set(result_contract["required_join_keys"])):
        raise GoldenError("result-manifest join-key contract is incomplete")

    sidecar_contract = json.loads(
        (project_root / manifest["tier0"]["biology_sidecar_contract"]).read_text(
            encoding="utf-8"
        )
    )
    if (
        sidecar_contract.get("core_five_tables_immutable") is not True
        or sidecar_contract.get("reverse_traceability_required") is not True
        or sidecar_contract.get("portable_manifest_absolute_paths_forbidden")
        is not True
    ):
        raise GoldenError("biology-sidecar contract invariants failed")
    if sidecar_contract["identity_scope"]["read_identity"] != [
        "core_result_manifest_sha256", "read_id"
    ]:
        raise GoldenError("biology-sidecar read identity is not Core-result scoped")
    if sidecar_contract["identity_scope"]["molecule_identity"] != (
        "optional_sidecar_defined_not_equivalent_to_read_id_by_default"
    ):
        raise GoldenError("molecule-identity guardrail is missing")

    freeze_scope = (
        project_root / manifest["tier0"]["scientific_freeze_scope"]
    ).read_text(encoding="utf-8")
    if (
        "not universal requirements" not in freeze_scope
        or "Current validated ONT-cDNA profile" not in freeze_scope
    ):
        raise GoldenError("platform-profile scoping is not explicit")

    trace_contract = (
        project_root / manifest["tier0"]["candidate_assignment_trace_contract"]
    ).read_text(encoding="utf-8")
    required_trace_terms = (
        "PENDING_STAGE15R_READ_ONLY_INSPECTION_BEFORE_FINAL_CORE_FREEZE_GO",
        "candidate assignment rows: 20,656,258",
        "read_id",
        "assignment basis and geometry",
        "Stage fusion",
    )
    if not all(term in trace_contract for term in required_trace_terms):
        raise GoldenError("candidate-assignment reverse-trace contract is incomplete")

    future_contract = (
        project_root / manifest["tier0"]["future_extensibility_contract"]
    ).read_text(encoding="utf-8")
    required_future_terms = (
        "PENDING_FINAL_EXACT_ORIGINAL_AUDIT_BEFORE_CORE_FREEZE_GO",
        "TARGET_SELECTION_EXTENSION_BOUNDARY",
        "MULTISAMPLE_NAMESPACE_EXTENSION_BOUNDARY",
        "PHYSICAL_STORAGE_ABSTRACTION_BOUNDARY",
        "READ_INSPECTION_REVERSE_TRACE_BOUNDARY",
        "FORCED_LOCUS_ANALYSIS_EXTENSION_BOUNDARY",
        "REFERENCE_ASSEMBLY_CATALOG_ADAPTER_BOUNDARY",
        "OUTPUT_ADAPTER_BOUNDARY",
        "No pre-Freeze implementation",
    )
    if not all(term in future_contract for term in required_future_terms):
        raise GoldenError("future-extensibility boundary contract is incomplete")

    boundary_rows = read_tsv(
        project_root / manifest["tier0"]["cross_platform_boundary_contract"]
    )
    by_surface = {row["surface"]: row for row in boundary_rows}
    expected_boundary = {
        "canonical_sequence_alignment_resolution": (
            "EXTENSION_BOUNDARY", "FREEZE_INTERFACE_NOT_PHYSICAL_FORMAT"
        ),
        "BAM_plus_source_FASTQ": (
            "CURRENT_ONT_CDNA_PROFILE", "SCOPED_BASELINE"
        ),
        "POD5_Dorado_direct_RNA": (
            "FUTURE_PLATFORM_PROFILE", "NOT_REQUIRED_PRE_FREEZE"
        ),
        "PacBio_IsoSeq": (
            "FUTURE_PLATFORM_PROFILE", "NOT_REQUIRED_PRE_FREEZE"
        ),
        "PacBio_Kinnex": (
            "FUTURE_PLATFORM_PROFILE", "NOT_REQUIRED_PRE_FREEZE"
        ),
    }
    for surface, (classification, freeze_status) in expected_boundary.items():
        row = by_surface.get(surface)
        if row is None:
            raise GoldenError(f"cross-platform boundary lacks {surface}")
        if (
            row.get("classification") != classification
            or row.get("freeze_status") != freeze_status
        ):
            raise GoldenError(
                f"cross-platform boundary mismatch for {surface}: {row}"
            )

    rows.extend([
        {
            "path": "STRUCTURAL:current_pipeline",
            "bytes": 0, "expected_sha256": ".", "actual_sha256": ".",
            "status": "PASS",
        },
        {
            "path": "STRUCTURAL:manifest_biology_platform_boundary",
            "bytes": resource_count,
            "expected_sha256": ".", "actual_sha256": ".",
            "status": "PASS",
        },
        {
            "path": "STRUCTURAL:core_freeze_manifest",
            "bytes": freeze_manifest_count,
            "expected_sha256": ".", "actual_sha256": ".",
            "status": "PASS",
        },
        {
            "path": "STRUCTURAL:candidate_assignment_reverse_traceability",
            "bytes": 0,
            "expected_sha256": ".", "actual_sha256": ".",
            "status": "PASS_PENDING_STAGE15R",
        },
        {
            "path": "STRUCTURAL:future_extensibility_boundaries",
            "bytes": 0,
            "expected_sha256": ".", "actual_sha256": ".",
            "status": "PASS_PENDING_FINAL_EXACT_ORIGINAL_AUDIT",
        },
    ])
    write_tsv(
        qc_root / "tier0_static.tsv", rows,
        ["path", "bytes", "expected_sha256", "actual_sha256", "status"],
    )
    return rows



def fastq_ids(path: Path) -> set[str]:
    ids: set[str] = set()
    with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
        while True:
            header = fh.readline()
            if not header:
                break
            seq = fh.readline()
            plus = fh.readline()
            qual = fh.readline()
            if not (seq and plus and qual):
                raise GoldenError(f"truncated FASTQ: {path}")
            if not header.startswith("@") or not plus.startswith("+"):
                raise GoldenError(f"invalid FASTQ structure: {path}")
            rid = header[1:].strip().split()[0]
            if rid in ids:
                raise GoldenError(f"duplicate FASTQ read ID: {rid}: {path}")
            ids.add(rid)
    return ids


def validate_regression_fixture(root: Path, expected: dict[str, Any]) -> dict[str, Any]:
    fixture = root / expected["relative_root"]
    files = {
        "regression_fixture.manifest.tsv": fixture / "regression_fixture.manifest.tsv",
        "regression_cases.tsv": fixture / "regression_cases.tsv",
        "decision_rules.tsv": fixture / "decision_rules.tsv",
        "regression_reads.fastq.gz": fixture / "data/regression_reads.fastq.gz",
        "regression_fixture.qc.tsv": fixture / "regression_fixture.qc.tsv",
        "README.md": fixture / "README.md",
    }
    for path in files.values():
        ensure_regular(path)
    manifest_rows = read_tsv(files["regression_fixture.manifest.tsv"])
    by_name = {row["artifact"]: row for row in manifest_rows}
    for artifact in (
        "regression_cases.tsv",
        "decision_rules.tsv",
        "regression_reads.fastq.gz",
        "regression_fixture.qc.tsv",
        "README.md",
    ):
        path = files[artifact]
        row = by_name.get(artifact)
        if row is None:
            raise GoldenError(f"fixture manifest lacks {artifact}: {fixture}")
        if int(row["bytes"]) != path.stat().st_size:
            raise GoldenError(f"fixture size mismatch: {path}")
        if row["sha256"] != sha256_file(path):
            raise GoldenError(f"fixture SHA mismatch: {path}")

    cases = read_tsv(files["regression_cases.tsv"])
    rules = read_tsv(files["decision_rules.tsv"])
    read_ids = fastq_ids(files["regression_reads.fastq.gz"])
    case_ids = {row["read_id"] for row in cases}
    if case_ids != read_ids:
        raise GoldenError(
            f"regression FASTQ/case read-set mismatch: {fixture}: "
            f"case_only={len(case_ids-read_ids)} read_only={len(read_ids-case_ids)}"
        )
    if len(cases) != int(expected["cases"]) or len(rules) != int(expected["rules"]):
        raise GoldenError(f"regression fixture count mismatch: {fixture}")
    return {
        "fixture": expected["name"],
        "cases": len(cases),
        "unique_reads": len(read_ids),
        "rules": len(rules),
        "status": "PASS",
    }


def expect_failure(
    command: list[str],
    *,
    log: Path,
    required_text: str | None = None,
) -> None:
    proc = run_command(
        command,
        expected_returncodes=set(range(1, 256)),
        log=log,
    )
    if required_text and required_text not in proc.stdout:
        raise GoldenError(f"expected rejection text not found: {required_text}: {log}")


def build_bindings_for_manifest(
    project_root: Path,
    portable_manifest: dict[str, Any],
    source_bam: Path,
    source_reads: Path,
) -> dict[str, Any]:
    resource_manifest = json.loads(
        (
            project_root / "config/core_runtime/v0.1.0/resource_manifest.json"
        ).read_text(encoding="utf-8")
    )
    bindings: dict[str, Any] = {
        "binding_version": "rnatr_local_resource_bindings_v0.1.0",
        "resources": {
            "source_bam": {"path": str(source_bam.resolve())},
            "source_reads": {"path": str(source_reads.resolve())},
        },
    }
    for logical_id in portable_manifest["resources"]:
        if logical_id in bindings["resources"]:
            continue
        if logical_id.startswith("component:"):
            role = logical_id.split(":", 1)[1]
            section = "components"
        elif logical_id.startswith("catalog:"):
            role = logical_id.split(":", 1)[1]
            section = "catalogs"
        else:
            raise GoldenError(f"unknown portable resource namespace: {logical_id}")
        entry = resource_manifest[section][role]
        bindings["resources"][logical_id] = {
            "path": str((project_root / entry["relative_path"]).resolve())
        }
    return bindings


def expected_table_parity(
    output_root: Path,
    expected: dict[str, Any],
    qc_path: Path,
) -> list[dict[str, Any]]:
    rows = []
    for filename, spec in expected.items():
        path = output_root / filename
        ensure_regular(path)
        actual_rows = data_rows(path)
        actual_sha = sha256_file(path)
        status = (
            "PASS"
            if actual_rows == int(spec["rows"]) and actual_sha == spec["sha256"]
            else "FAIL"
        )
        rows.append(
            {
                "artifact": filename,
                "expected_rows": spec["rows"],
                "actual_rows": actual_rows,
                "expected_sha256": spec["sha256"],
                "actual_sha256": actual_sha,
                "status": status,
            }
        )
        if status != "PASS":
            raise GoldenError(f"golden table parity failed: {path}")
    write_tsv(
        qc_path,
        rows,
        [
            "artifact",
            "expected_rows",
            "actual_rows",
            "expected_sha256",
            "actual_sha256",
            "status",
        ],
    )
    return rows


def public_entry_command(
    *,
    project_root: Path,
    public_entry: Path,
    mode: str,
    profile: dict[str, Any],
    work_root: Path,
    output_root: Path,
    control_root: Path,
) -> list[str]:
    return [
        sys.executable,
        "-u",
        str(public_entry),
        mode,
        "--project-root",
        str(project_root),
        "--bam",
        str(project_root / profile["bam"]),
        "--reads-fastq",
        str(project_root / profile["fastq"]),
        "--run-id",
        profile["run_id"],
        "--sample-id",
        profile["sample_id"],
        "--work-root",
        str(work_root),
        "--output-root",
        str(output_root),
        "--control-root",
        str(control_root),
        "--shards",
        str(profile["shards"]),
        "--max-unit-workers",
        str(profile["max_unit_workers"]),
        "--caller-workers",
        str(profile["caller_workers"]),
        "--pythonhashseed",
        profile.get("pythonhashseed", "0"),
        "--expected-bam-sha256",
        profile["bam_sha256"],
        "--expected-fastq-sha256",
        profile["fastq_sha256"],
    ]


def run_prebiology_smoke(
    project_root: Path,
    manifest: dict[str, Any],
    output_root: Path,
    qc_path: Path,
) -> None:
    smoke = project_root / manifest["tier0"]["prebiology_smoke"]
    run_command(
        [
            sys.executable,
            "-u",
            str(smoke),
            "--manifest",
            str(output_root / "core_result_manifest.json"),
            "--bindings",
            str(output_root / "resource_bindings.local.json"),
            "--output-qc",
            str(qc_path),
        ],
        log=qc_path.with_suffix(".log"),
    )



def run_biology_sidecar_interface_smoke(
    project_root: Path,
    manifest: dict[str, Any],
    output_root: Path,
    qc_root: Path,
) -> Path:
    contract_path = project_root / manifest["tier0"]["biology_sidecar_contract"]
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    core_manifest_path = output_root / "core_result_manifest.json"
    ensure_regular(core_manifest_path)
    core_manifest = json.loads(core_manifest_path.read_text(encoding="utf-8"))
    core_sha = sha256_file(core_manifest_path)

    read_path = output_root / "read_evidence.tsv"
    ensure_regular(read_path)
    selected: dict[str, str] | None = None
    with read_path.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            required = (
                "read_id", "evidence_id", "target_source",
                "target_region_id", "locus_id",
            )
            if all(row.get(key) not in {None, "", "."} for key in required):
                selected = row
                break
    if selected is None:
        raise GoldenError("biology-sidecar smoke found no joinable evidence row")

    catalog_logical_id = "catalog:mapping_target_tsv"
    catalog_entry = core_manifest.get("resources", {}).get(catalog_logical_id)
    if not isinstance(catalog_entry, dict) or not catalog_entry.get("sha256"):
        raise GoldenError("biology-sidecar smoke lacks pinned mapping-target catalog")

    example = {
        "contract_version": contract["contract_version"],
        "core_reference": {
            "core_result_manifest_version": core_manifest["manifest_version"],
            "core_result_manifest_sha256": core_sha,
            "run_id": core_manifest["run"]["run_id"],
            "sample_id": core_manifest["run"]["sample_id"],
            "core_evidence_schema_version": core_manifest["scientific_contract"][
                "evidence_schema"
            ],
        },
        "sidecar": {
            "sidecar_name": "rnatr_prebiology_interface_example",
            "sidecar_software_version": VERSION,
            "sidecar_schema_version": "v0.1.0",
            "created_utc": "2000-01-01T00:00:00Z",
            "validation_status": "PASS",
        },
        "identity_example": {
            "read_identity": {
                "core_result_manifest_sha256": core_sha,
                "read_id": selected["read_id"],
            },
            "locus_identity": {
                "catalog_logical_id": catalog_logical_id,
                "catalog_sha256": catalog_entry["sha256"],
                "target_source": selected["target_source"],
                "target_region_id": selected["target_region_id"],
                "locus_id": selected["locus_id"],
            },
            "evidence_identity": {
                "core_result_manifest_sha256": core_sha,
                "evidence_id": selected["evidence_id"],
            },
            "molecule_identity_asserted": False,
            "molecule_identity_status": "NOT_DEFINED_BY_CORE_READ_ID",
        },
        "resources": {
            catalog_logical_id: {
                "sha256": catalog_entry["sha256"],
                "kind": catalog_entry.get("kind", "CATALOG_OR_ANNOTATION"),
            }
        },
        "core_five_tables_immutable": True,
        "reverse_traceability_required": True,
    }
    validate_sidecar_example_contract(example, contract)
    if example["core_reference"]["core_result_manifest_sha256"] != core_sha:
        raise GoldenError("biology-sidecar Core manifest SHA binding failed")
    if contract["identity_scope"]["read_identity"] != [
        "core_result_manifest_sha256", "read_id"
    ]:
        raise GoldenError("biology-sidecar read identity contract drift")

    example_path = qc_root / "tier2_biology_sidecar_manifest.example.json"
    example_path.write_text(
        json.dumps(example, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_tsv(
        qc_root / "tier2_biology_sidecar_interface_smoke.tsv",
        [{
            "core_result_manifest_sha256": core_sha,
            "read_id": selected["read_id"],
            "evidence_id": selected["evidence_id"],
            "catalog_logical_id": catalog_logical_id,
            "catalog_sha256": catalog_entry["sha256"],
            "target_source": selected["target_source"],
            "target_region_id": selected["target_region_id"],
            "locus_id": selected["locus_id"],
            "molecule_identity_asserted": "false",
            "status": "PASS",
        }],
        [
            "core_result_manifest_sha256", "read_id", "evidence_id",
            "catalog_logical_id", "catalog_sha256", "target_source",
            "target_region_id", "locus_id", "molecule_identity_asserted",
            "status",
        ],
    )
    return example_path

def run_package_negative_fixtures(
    project_root: Path,
    manifest: dict[str, Any],
    tier2_output: Path,
    qc_root: Path,
    scratch: Path,
) -> list[dict[str, str]]:
    smoke = project_root / manifest["tier0"]["prebiology_smoke"]
    package_validator = project_root / manifest["tier0"]["package_validator"]
    source_bam = project_root / manifest["tier2"]["bam"]
    source_reads = project_root / manifest["tier2"]["fastq"]
    rows: list[dict[str, str]] = []

    # N01: absolute path in portable manifest.
    n01 = scratch / "N01"
    shutil.copytree(tier2_output, n01)
    mpath = n01 / "core_result_manifest.json"
    pobj = json.loads(mpath.read_text(encoding="utf-8"))
    pobj["test_absolute_path"] = "/tmp/forbidden"
    mpath.write_text(json.dumps(pobj, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    bindings = build_bindings_for_manifest(project_root, pobj, source_bam, source_reads)
    bpath = n01 / "resource_bindings.local.json"
    bpath.write_text(json.dumps(bindings, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    expect_failure(
        [sys.executable, str(smoke), "--manifest", str(mpath), "--bindings", str(bpath), "--output-qc", str(n01 / "qc.tsv")],
        log=qc_root / "negative_N01.log",
        required_text="absolute path",
    )
    rows.append({"test_id": "N01", "status": "PASS_REJECTED"})

    # N02: resource hash drift.
    n02 = scratch / "N02"
    shutil.copytree(tier2_output, n02)
    mpath = n02 / "core_result_manifest.json"
    pobj = json.loads(mpath.read_text(encoding="utf-8"))
    first_key = sorted(pobj["resources"])[0]
    pobj["resources"][first_key]["sha256"] = "0" * 64
    mpath.write_text(json.dumps(pobj, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    bindings = build_bindings_for_manifest(project_root, pobj, source_bam, source_reads)
    bpath = n02 / "resource_bindings.local.json"
    bpath.write_text(json.dumps(bindings, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    expect_failure(
        [sys.executable, str(smoke), "--manifest", str(mpath), "--bindings", str(bpath), "--output-qc", str(n02 / "qc.tsv")],
        log=qc_root / "negative_N02.log",
        required_text="resource SHA mismatch",
    )
    rows.append({"test_id": "N02", "status": "PASS_REJECTED"})

    # N03: missing required table.
    n03 = scratch / "N03"
    shutil.copytree(tier2_output, n03)
    (n03 / "repeat_interruptions.tsv").unlink()
    expect_failure(
        [sys.executable, str(package_validator), "--package-dir", str(n03)],
        log=qc_root / "negative_N03.log",
    )
    rows.append({"test_id": "N03", "status": "PASS_REJECTED"})

    # N04: duplicate evidence primary ID.
    n04 = scratch / "N04"
    shutil.copytree(tier2_output, n04)
    read_path = n04 / "read_evidence.tsv"
    lines = read_path.read_bytes().splitlines(keepends=True)
    if len(lines) < 2:
        raise GoldenError("Tier2 read_evidence has no data row")
    with read_path.open("ab") as fh:
        fh.write(lines[1])
    expect_failure(
        [sys.executable, str(package_validator), "--package-dir", str(n04)],
        log=qc_root / "negative_N04.log",
        required_text="duplicate read_evidence evidence_id",
    )
    rows.append({"test_id": "N04", "status": "PASS_REJECTED"})

    # N05: broken event-to-evidence FK.
    n05 = scratch / "N05"
    shutil.copytree(tier2_output, n05)
    event_path = n05 / "repeat_events.tsv"
    with event_path.open("r", encoding="utf-8", newline="") as fh:
        event_rows = list(csv.reader(fh, delimiter="\t"))
    evidence_index = event_rows[0].index("evidence_id")
    event_rows[1][evidence_index] = "missing_evidence_for_negative_fixture"
    with event_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t", lineterminator="\n")
        writer.writerows(event_rows)
    expect_failure(
        [sys.executable, str(package_validator), "--package-dir", str(n05)],
        log=qc_root / "negative_N05.log",
        required_text="event evidence FK failure",
    )
    rows.append({"test_id": "N05", "status": "PASS_REJECTED"})

    # N10: physical ONT-cDNA input profile must not be universalized.
    sidecar = json.loads(
        (project_root / manifest["tier0"]["biology_sidecar_contract"]).read_text(encoding="utf-8")
    )
    freeze_scope = (project_root / manifest["tier0"]["scientific_freeze_scope"]).read_text(encoding="utf-8")
    if sidecar.get("core_five_tables_immutable") is not True:
        raise GoldenError("N10 sidecar immutability guard failed")
    if "not universal requirements" not in freeze_scope:
        raise GoldenError("N10 platform-profile scoping text missing")
    rows.append({"test_id": "N10", "status": "PASS_CONTRACT_SCOPED"})
    write_tsv(qc_root / "tier1_negative_fixtures.tsv", rows, ["test_id", "status"])
    return rows


def tier1_semantic(
    project_root: Path,
    manifest: dict[str, Any],
    qc_root: Path,
) -> list[dict[str, Any]]:
    rows = []
    golden_root = project_root / "validation/golden/v0.1.0"
    for fixture in manifest["tier1"]["regression_fixtures"]:
        rows.append(validate_regression_fixture(golden_root, fixture))

    canonical_manifest = project_root / manifest["tier1"]["general_caller_manifest"]
    manifest_rows = read_tsv(canonical_manifest)
    for row in manifest_rows:
        path = project_root / row["relative_path"]
        ensure_regular(path)
        if int(row["bytes"]) != path.stat().st_size or row["sha256"] != sha256_file(path):
            raise GoldenError(f"general-caller original drift: {path}")
    rows.append(
        {
            "fixture": "general_caller_validation_originals",
            "cases": len(manifest_rows),
            "unique_reads": ".",
            "rules": ".",
            "status": "PASS",
        }
    )
    write_tsv(qc_root / "tier1_semantic.tsv", rows, ["fixture", "cases", "unique_reads", "rules", "status"])
    return rows



def run_tier2(
    project_root: Path,
    manifest: dict[str, Any],
    suite_work: Path,
    qc_root: Path,
) -> Path:
    profile = manifest["tier2"]
    root = suite_work / "tier2"
    work, output, control = root / "work", root / "output", root / "control"
    public_entry = project_root / manifest["tier0"]["public_entry"]
    run_command(
        public_entry_command(
            project_root=project_root,
            public_entry=public_entry,
            mode="--start",
            profile=profile,
            work_root=work,
            output_root=output,
            control_root=control,
        ),
        log=qc_root / "tier2_execution.log",
    )
    expected_table_parity(
        output, profile["expected_plain_tables"],
        qc_root / "tier2_exact_parity.tsv",
    )
    run_prebiology_smoke(
        project_root, manifest, output,
        qc_root / "tier2_prebiology_smoke.tsv",
    )
    run_biology_sidecar_interface_smoke(
        project_root, manifest, output, qc_root
    )
    return output



def fingerprints(root: Path) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(root.iterdir()):
        if path.is_file():
            stat = path.stat()
            rows.append(
                {
                    "name": path.name,
                    "bytes": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                    "inode": stat.st_ino,
                    "device": stat.st_dev,
                    "sha256": sha256_file(path),
                }
            )
    return rows


def expect_resume_failure(command: list[str], log: Path, required_text: str) -> None:
    proc = run_command(command, expected_returncodes=set(range(1, 256)), log=log)
    if required_text not in proc.stdout:
        raise GoldenError(f"resume rejection text missing: {required_text}: {log}")



def run_tier3(
    project_root: Path,
    manifest: dict[str, Any],
    suite_work: Path,
    qc_root: Path,
) -> Path:
    profile = manifest["tier3"]
    root = suite_work / "tier3"
    work, output, control = root / "work", root / "output", root / "control"
    public_entry = project_root / manifest["tier0"]["public_entry"]
    start_command = public_entry_command(
        project_root=project_root, public_entry=public_entry, mode="--start",
        profile=profile, work_root=work, output_root=output,
        control_root=control,
    )
    env = os.environ.copy()
    env["RNATR_TEST_STOP_AFTER_SHARDS"] = str(
        profile["intentional_stop_after_shards"]
    )
    stop = run_command(
        start_command, env=env, expected_returncodes={75},
        log=qc_root / "tier3_intentional_stop.log",
    )
    if "INTENTIONAL_STOP\tPASS_EXPECTED" not in stop.stdout:
        raise GoldenError("Tier3 intentional-stop marker missing")

    resume_command = public_entry_command(
        project_root=project_root, public_entry=public_entry, mode="--resume",
        profile=profile, work_root=work, output_root=output,
        control_root=control,
    )
    run_command(resume_command, log=qc_root / "tier3_first_resume.log")
    expected_table_parity(
        output, profile["expected_plain_tables"],
        qc_root / "tier3_exact_parity.tsv",
    )
    run_prebiology_smoke(
        project_root, manifest, output,
        qc_root / "tier3_prebiology_smoke.tsv",
    )

    before = fingerprints(output)
    attempts_before_noop = unit_attempt_count(work)
    second = run_command(
        resume_command, log=qc_root / "tier3_second_resume.log"
    )
    if "SECOND_RESUME_NOOP\tPASS" not in second.stdout:
        raise GoldenError("Tier3 second-resume no-op marker missing")
    after = fingerprints(output)
    attempts_after_noop = unit_attempt_count(work)
    if before != after:
        raise GoldenError("Tier3 output fingerprints changed on second resume")
    if attempts_before_noop != attempts_after_noop:
        raise GoldenError("Tier3 unit-attempt count changed on second resume")
    write_tsv(
        qc_root / "tier3_output_fingerprints.tsv", before,
        ["name", "bytes", "mtime_ns", "inode", "device", "sha256"],
    )

    # N06: partition-manifest drift.
    n06 = root / "negative_N06"
    (n06 / "state").mkdir(parents=True)
    (n06 / "partitions").mkdir(parents=True)
    shutil.copy2(work / "state/run.json", n06 / "state/run.json")
    shutil.copy2(
        work / "partitions/partition_manifest.tsv",
        n06 / "partitions/partition_manifest.tsv",
    )
    with (n06 / "partitions/partition_manifest.tsv").open(
        "a", encoding="utf-8"
    ) as fh:
        fh.write("#negative-drift\n")
    n06_command = public_entry_command(
        project_root=project_root, public_entry=public_entry, mode="--resume",
        profile=profile, work_root=n06, output_root=output,
        control_root=control,
    )
    expect_resume_failure(
        n06_command, qc_root / "negative_N06.log",
        "partition-manifest SHA drift",
    )

    # N07: completed shard output drift; reject without a new attempt, restore, revalidate.
    state_files = sorted((work / "state").glob("shard_*.json"))
    if not state_files:
        raise GoldenError("Tier3 has no shard states")
    state = json.loads(state_files[0].read_text(encoding="utf-8"))
    unit_output = Path(state["output_root"])
    unit_table = unit_output / "read_evidence.tsv"
    backup = root / "negative_N07_read_evidence.backup"
    shutil.copy2(unit_table, backup)
    backup_sha = sha256_file(backup)
    attempts_before_drift = unit_attempt_count(work)
    try:
        with unit_table.open("ab") as fh:
            fh.write(b"#negative-drift\n")
        proc = run_command(
            resume_command,
            expected_returncodes=set(range(1, 256)),
            log=qc_root / "negative_N07.log",
        )
        if not accepted_completed_shard_drift_rejection(proc.stdout):
            raise GoldenError(
                "Tier3 N07 did not produce an accepted completed-shard rejection class"
            )
        if unit_attempt_count(work) != attempts_before_drift:
            raise GoldenError("Tier3 N07 created a new unit attempt")
    finally:
        shutil.copy2(backup, unit_table)
    if sha256_file(unit_table) != backup_sha:
        raise GoldenError("Tier3 N07 restoration failed")
    package_validator = project_root / manifest["tier0"]["package_validator"]
    run_command(
        [sys.executable, str(package_validator), "--package-dir", str(unit_output)],
        log=qc_root / "negative_N07_restored_validator.log",
    )

    # N08: output published but copied external final state missing.
    n08 = root / "negative_N08"
    (n08 / "state").mkdir(parents=True)
    (n08 / "partitions").mkdir(parents=True)
    shutil.copy2(work / "state/run.json", n08 / "state/run.json")
    shutil.copy2(
        work / "partitions/partition_manifest.tsv",
        n08 / "partitions/partition_manifest.tsv",
    )
    for state_file in sorted((work / "state").glob("shard_*.json")):
        shutil.copy2(state_file, n08 / "state" / state_file.name)
    n08_command = public_entry_command(
        project_root=project_root, public_entry=public_entry, mode="--resume",
        profile=profile, work_root=n08, output_root=output,
        control_root=control,
    )
    n08_output_before = fingerprints(output)
    recovered = run_command(n08_command, log=qc_root / "negative_N08.log")
    n08_output_after = fingerprints(output)
    if n08_output_before != n08_output_after:
        raise GoldenError("Tier3 N08 changed published output fingerprints")
    if (
        "POST_PUBLICATION_FINAL_STATE_RECOVERY\tPASS" not in recovered.stdout
        or "scientific_commands\t0" not in recovered.stdout
    ):
        raise GoldenError("Tier3 N08 recovery marker missing")
    if (
        (n08 / "state/final.json").read_bytes()
        != (work / "state/final.json").read_bytes()
    ):
        raise GoldenError("Tier3 N08 recovered state is not byte-identical")

    write_tsv(
        qc_root / "tier3_restart_negative_fixtures.tsv",
        [
            {"test_id": "N06", "status": "PASS_REJECTED"},
            {
                "test_id": "N07",
                "status": "PASS_REJECTED_NO_NEW_ATTEMPT_RESTORED_VALIDATED",
            },
            {
                "test_id": "N08",
                "status": "PASS_RECOVERED_ZERO_SCIENTIFIC_COMMAND_OUTPUT_UNCHANGED",
            },
            {
                "test_id": "N09",
                "status": "PASS_NOOP_UNCHANGED_FINGERPRINTS_AND_ATTEMPTS",
            },
        ],
        ["test_id", "status"],
    )
    return output



def verify_tier4(project_root: Path, manifest: dict[str, Any], qc_root: Path) -> list[dict[str, Any]]:
    rows = []
    for item in manifest["tier4"]["evidence"]:
        path = project_root / item["path"]
        ensure_regular(path)
        actual = sha256_file(path)
        status = "PASS" if actual == item["sha256"] else "FAIL"
        if status != "PASS":
            raise GoldenError(f"Tier4 evidence drift: {path}")
        rows.append({"name": item["name"], "path": item["path"], "sha256": actual, "scope": item["scope"], "status": status})
    write_tsv(qc_root / "tier4_evidence_scope.tsv", rows, ["name", "path", "sha256", "scope", "status"])
    return rows


def run_suite(mode: str, project_root: Path, work_root: Path, qc_root: Path) -> int:
    if work_root.exists() or qc_root.exists():
        raise GoldenError("golden suite requires unused work/QC roots")
    work_root.mkdir(parents=True)
    qc_root.mkdir(parents=True)
    manifest = load_manifest(project_root)
    started = time.perf_counter()

    tier0_static(project_root, manifest, qc_root)
    tier1_semantic(project_root, manifest, qc_root)
    tier2_output = run_tier2(project_root, manifest, work_root, qc_root)
    with tempfile.TemporaryDirectory(prefix="rnatr_golden_negative_", dir=str(work_root)) as td:
        run_package_negative_fixtures(project_root, manifest, tier2_output, qc_root, Path(td))

    if mode in {"full", "full-evidence"}:
        run_tier3(project_root, manifest, work_root, qc_root)
    if mode == "full-evidence":
        verify_tier4(project_root, manifest, qc_root)

    elapsed = time.perf_counter() - started
    summary = [
        {"metric": "golden_suite_version", "value": VERSION},
        {"metric": "mode", "value": mode},
        {"metric": "status", "value": "PASS"},
        {"metric": "elapsed_seconds", "value": elapsed},
        {"metric": "tier0", "value": "PASS"},
        {"metric": "tier1", "value": "PASS"},
        {"metric": "tier2", "value": "PASS"},
        {"metric": "tier3", "value": "PASS" if mode in {"full", "full-evidence"} else "NOT_RUN"},
        {"metric": "tier4", "value": "PASS" if mode == "full-evidence" else "NOT_RUN"},
    ]
    write_tsv(qc_root / "golden_suite_summary.tsv", summary, ["metric", "value"])
    print("RNATR_GOLDEN_REGRESSION\tPASS")
    print(f"mode\t{mode}")
    print(f"elapsed_seconds\t{elapsed:.3f}")
    print(f"QC_ROOT\t{qc_root}")
    return 0



def self_test() -> int:
    if VERSION != "rnatr_golden_regression_suite_v0.1.4":
        raise GoldenError("self-test version mismatch")
    with tempfile.TemporaryDirectory(prefix="rnatr_golden_selftest_") as td:
        root = Path(td)
        path = root / "x.tsv"
        path.write_text("a\n1\n", encoding="utf-8")
        if data_rows(path) != 1:
            raise GoldenError("self-test row count failed")
        if not has_absolute_path({"x": "/tmp/a"}):
            raise GoldenError("self-test absolute-path detection failed")
        if has_absolute_path({"x": "relative/a"}):
            raise GoldenError("self-test relative-path classification failed")
        if not accepted_completed_shard_drift_rejection(
            "ERROR: unit package validator failed: fixture"
        ):
            raise GoldenError("self-test drift rejection classification failed")
        (root / "units/shard_000/attempt_001").mkdir(parents=True)
        if unit_attempt_count(root) != 1:
            raise GoldenError("self-test unit attempt count failed")
        contract = {
            "contract_version": "x",
            "core_reference_required": {
                "core_result_manifest_version": "string",
                "core_result_manifest_sha256": "sha256",
                "run_id": "string",
                "sample_id": "string",
                "core_evidence_schema_version": "string",
            },
            "sidecar_required": {
                "sidecar_name": "string",
                "sidecar_software_version": "string",
                "sidecar_schema_version": "string",
                "created_utc": "RFC3339",
                "validation_status": ["PASS", "FAIL"],
            },
            "identity_scope": {
                "read_identity": ["core_result_manifest_sha256", "read_id"],
                "evidence_identity": ["core_result_manifest_sha256", "evidence_id"],
                "locus_identity": [
                    "catalog_logical_id", "catalog_sha256", "target_source",
                    "target_region_id", "locus_id",
                ],
            },
        }
        example = {
            "contract_version": "x",
            "core_reference": {
                "core_result_manifest_version": "m",
                "core_result_manifest_sha256": "a" * 64,
                "run_id": "r", "sample_id": "s",
                "core_evidence_schema_version": "0.4.2",
            },
            "sidecar": {
                "sidecar_name": "x", "sidecar_software_version": "1",
                "sidecar_schema_version": "1",
                "created_utc": "2000-01-01T00:00:00Z",
                "validation_status": "PASS",
            },
            "identity_example": {
                "read_identity": {
                    "core_result_manifest_sha256": "a" * 64,
                    "read_id": "read",
                },
                "evidence_identity": {
                    "core_result_manifest_sha256": "a" * 64,
                    "evidence_id": "evidence",
                },
                "locus_identity": {
                    "catalog_logical_id": "catalog:x",
                    "catalog_sha256": "b" * 64,
                    "target_source": "x", "target_region_id": "y",
                    "locus_id": "z",
                },
                "molecule_identity_asserted": False,
            },
            "core_five_tables_immutable": True,
            "reverse_traceability_required": True,
        }
        validate_sidecar_example_contract(example, contract)
        fixture_future = " ".join((
            "PENDING_FINAL_EXACT_ORIGINAL_AUDIT_BEFORE_CORE_FREEZE_GO",
            "TARGET_SELECTION_EXTENSION_BOUNDARY",
            "MULTISAMPLE_NAMESPACE_EXTENSION_BOUNDARY",
            "PHYSICAL_STORAGE_ABSTRACTION_BOUNDARY",
            "READ_INSPECTION_REVERSE_TRACE_BOUNDARY",
            "FORCED_LOCUS_ANALYSIS_EXTENSION_BOUNDARY",
            "REFERENCE_ASSEMBLY_CATALOG_ADAPTER_BOUNDARY",
            "OUTPUT_ADAPTER_BOUNDARY",
            "No pre-Freeze implementation",
        ))
        if "OUTPUT_ADAPTER_BOUNDARY" not in fixture_future:
            raise GoldenError("self-test future-extensibility fixture failed")
    print("SELF_TEST\tPASS")
    print(f"version\t{VERSION}")
    return 0



def main() -> int:
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--self-test", action="store_true")
    modes.add_argument("--quick", action="store_true")
    modes.add_argument("--full", action="store_true")
    modes.add_argument("--full-evidence", action="store_true")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--work-root", type=Path)
    parser.add_argument("--qc-root", type=Path)
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if args.work_root is None or args.qc_root is None:
        parser.error("--work-root and --qc-root are required")
    mode = "quick" if args.quick else "full" if args.full else "full-evidence"
    return run_suite(mode, args.project_root.resolve(), args.work_root.resolve(), args.qc_root.resolve())


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
