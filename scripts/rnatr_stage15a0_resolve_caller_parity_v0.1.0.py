#!/usr/bin/env python3
"""Resolve Stage 15A0 caller-reference parity without modifying project inputs.

This audit distinguishes:
  1. exact Stage14G reference <-> Stage14K promoted caller-output parity, and
  2. keyed, field-for-field equality of the 77-column caller suffix embedded in
     the Stage14K2 materialized package.

The second comparison is intentionally order-insensitive because materializer
v0.1.2 sorts ``general_repeat_calls`` by ``projection_id`` before publication.
Line-ending and gzip-member differences are reported separately and are not
accepted as value differences.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterable, TextIO

STAGE_VERSION = "rnatr_stage15a0_caller_parity_resolver_v0.1.0"
DEFAULT_PROJECT_ROOT = Path("/mnt/intelssd/rnatr_project")
DEFAULT_RUN_ID = "ENCSR307SHM_pilot100k_mm2splice_v1"
DEFAULT_EXPECTED_ROWS = 388_571
DEFAULT_EXPECTED_COLUMNS = 77
DEFAULT_EXPECTED_CALLED = 160_315
DEFAULT_EXPECTED_LOW_CONFIDENCE_CALLED = 6_307
EXPECTED_PACKAGE_PREFIX = [
    "schema_version",
    "run_id",
    "sample_id",
    "caller_record_id",
    "evidence_id",
    "materialization_status",
    "repeat_event_id",
    "primary_repeat_call_id",
]


class ContractError(RuntimeError):
    """Raised when a structural contract cannot be audited safely."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only Stage 15A0 parity resolver: exact Stage14G/Stage14K "
            "caller parity plus keyed equality of the Stage14K2 package suffix."
        )
    )
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--reused-calls", type=Path)
    parser.add_argument("--package-general", type=Path)
    parser.add_argument("--outdir", type=Path)
    parser.add_argument("--expected-rows", type=int, default=DEFAULT_EXPECTED_ROWS)
    parser.add_argument("--expected-columns", type=int, default=DEFAULT_EXPECTED_COLUMNS)
    parser.add_argument("--expected-called", type=int, default=DEFAULT_EXPECTED_CALLED)
    parser.add_argument(
        "--expected-low-confidence-called",
        type=int,
        default=DEFAULT_EXPECTED_LOW_CONFIDENCE_CALLED,
    )
    parser.add_argument("--max-details", type=int, default=20)
    return parser.parse_args()


def open_binary(path: Path) -> BinaryIO:
    return gzip.open(path, "rb") if path.suffix == ".gz" else path.open("rb")


def open_text(path: Path) -> TextIO:
    return (
        gzip.open(path, "rt", encoding="utf-8", newline="")
        if path.suffix == ".gz"
        else path.open("rt", encoding="utf-8", newline="")
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def decompressed_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open_binary(path) as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def newline_profile(path: Path) -> dict[str, object]:
    """Count decompressed CRLF/LF/CR without loading the file."""
    lf = 0
    cr = 0
    crlf = 0
    previous_chunk_ended_cr = False
    with open_binary(path) as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            if previous_chunk_ended_cr and block.startswith(b"\n"):
                crlf += 1
            crlf += block.count(b"\r\n")
            lf += block.count(b"\n")
            cr += block.count(b"\r")
            previous_chunk_ended_cr = block.endswith(b"\r")
    bare_lf = lf - crlf
    bare_cr = cr - crlf
    if crlf and not bare_lf and not bare_cr:
        style = "CRLF"
    elif bare_lf and not crlf and not bare_cr:
        style = "LF"
    elif not crlf and not bare_lf and not bare_cr:
        style = "NO_LINE_ENDINGS"
    else:
        style = "MIXED"
    return {
        "style": style,
        "crlf": crlf,
        "bare_lf": bare_lf,
        "bare_cr": bare_cr,
    }


def canonical_row_bytes(row: list[str]) -> bytes:
    return ("\t".join(row) + "\n").encode("utf-8")


def atomic_write_tsv(path: Path, fields: list[str], rows: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=fields,
                delimiter="\t",
                lineterminator="\n",
                extrasaction="raise",
            )
            writer.writeheader()
            writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


@dataclass
class CallerIndex:
    path: Path
    header: list[str]
    row_count: int
    duplicate_count: int
    duplicate_examples: list[str]
    row_hash_by_projection: dict[str, bytes]
    row_order_hash: str
    keyed_semantic_hash: str
    canonical_tsv_hash: str
    called_attempts: int
    low_confidence_called_attempts: int


def index_caller_table(path: Path, max_details: int) -> CallerIndex:
    row_hash_by_projection: dict[str, bytes] = {}
    duplicate_examples: list[str] = []
    duplicate_count = 0
    row_count = 0
    order_hash = hashlib.sha256()
    canonical_tsv_hash = hashlib.sha256()
    called_attempts = 0
    low_confidence_called_attempts = 0

    with open_text(path) as handle:
        reader = csv.reader(handle, delimiter="\t")
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ContractError(f"empty caller table: {path}") from exc
        if "projection_id" not in header:
            raise ContractError(f"projection_id missing from caller header: {path}")
        projection_index = header.index("projection_id")
        integration_index = header.index("integration_status") if "integration_status" in header else None
        call_status_index = header.index("call_status") if "call_status" in header else None
        canonical_tsv_hash.update(canonical_row_bytes(header))

        for line_number, row in enumerate(reader, 2):
            if len(row) != len(header):
                raise ContractError(
                    f"caller row width mismatch at {path}:{line_number}: "
                    f"{len(row)} != {len(header)}"
                )
            row_count += 1
            projection_id = row[projection_index]
            if not projection_id:
                raise ContractError(f"empty projection_id at {path}:{line_number}")
            digest = hashlib.sha256(canonical_row_bytes(row)).digest()
            if projection_id in row_hash_by_projection:
                duplicate_count += 1
                if len(duplicate_examples) < max_details:
                    duplicate_examples.append(projection_id)
            else:
                row_hash_by_projection[projection_id] = digest
            order_hash.update(projection_id.encode("utf-8"))
            order_hash.update(b"\n")
            canonical_tsv_hash.update(canonical_row_bytes(row))
            if integration_index is not None and row[integration_index] == "CALLED":
                called_attempts += 1
                if call_status_index is not None and row[call_status_index] == "LOW_CONFIDENCE":
                    low_confidence_called_attempts += 1

    keyed_hash = hashlib.sha256()
    for projection_id in sorted(row_hash_by_projection):
        keyed_hash.update(projection_id.encode("utf-8"))
        keyed_hash.update(b"\t")
        keyed_hash.update(row_hash_by_projection[projection_id].hex().encode("ascii"))
        keyed_hash.update(b"\n")

    return CallerIndex(
        path=path,
        header=header,
        row_count=row_count,
        duplicate_count=duplicate_count,
        duplicate_examples=duplicate_examples,
        row_hash_by_projection=row_hash_by_projection,
        row_order_hash=order_hash.hexdigest(),
        keyed_semantic_hash=keyed_hash.hexdigest(),
        canonical_tsv_hash=canonical_tsv_hash.hexdigest(),
        called_attempts=called_attempts,
        low_confidence_called_attempts=low_confidence_called_attempts,
    )


@dataclass
class PackageSuffixAudit:
    path: Path
    full_header: list[str]
    suffix_header: list[str]
    prefix_ok: bool
    row_count: int
    duplicate_count: int
    duplicate_examples: list[str]
    missing_ids: list[str]
    extra_ids: list[str]
    mismatch_ids: list[str]
    missing_count: int
    extra_count: int
    mismatch_count: int
    package_hash_by_projection: dict[str, bytes]
    order_hash: str
    keyed_semantic_hash: str
    canonical_suffix_tsv_hash: str


def audit_package_suffix(
    path: Path,
    reference: CallerIndex,
    max_details: int,
) -> PackageSuffixAudit:
    duplicate_count = 0
    duplicate_examples: list[str] = []
    extra_ids: list[str] = []
    mismatch_ids: list[str] = []
    row_count = 0
    package_hash_by_projection: dict[str, bytes] = {}
    order_hash = hashlib.sha256()
    canonical_suffix_tsv_hash = hashlib.sha256()

    with open_text(path) as handle:
        reader = csv.reader(handle, delimiter="\t")
        try:
            full_header = next(reader)
        except StopIteration as exc:
            raise ContractError(f"empty package table: {path}") from exc
        if len(full_header) < len(EXPECTED_PACKAGE_PREFIX):
            raise ContractError(f"package header is shorter than 8 columns: {path}")
        prefix_ok = full_header[:8] == EXPECTED_PACKAGE_PREFIX
        suffix_header = full_header[8:]
        if "projection_id" not in suffix_header:
            raise ContractError(f"projection_id missing from package suffix: {path}")
        projection_index = suffix_header.index("projection_id")
        canonical_suffix_tsv_hash.update(canonical_row_bytes(suffix_header))

        for line_number, full_row in enumerate(reader, 2):
            if len(full_row) != len(full_header):
                raise ContractError(
                    f"package row width mismatch at {path}:{line_number}: "
                    f"{len(full_row)} != {len(full_header)}"
                )
            suffix = full_row[8:]
            row_count += 1
            projection_id = suffix[projection_index]
            if not projection_id:
                raise ContractError(f"empty projection_id at {path}:{line_number}")
            digest = hashlib.sha256(canonical_row_bytes(suffix)).digest()
            if projection_id in package_hash_by_projection:
                duplicate_count += 1
                if len(duplicate_examples) < max_details:
                    duplicate_examples.append(projection_id)
            else:
                package_hash_by_projection[projection_id] = digest
            order_hash.update(projection_id.encode("utf-8"))
            order_hash.update(b"\n")
            canonical_suffix_tsv_hash.update(canonical_row_bytes(suffix))

            reference_digest = reference.row_hash_by_projection.get(projection_id)
            if reference_digest is None:
                if len(extra_ids) < max_details:
                    extra_ids.append(projection_id)
            elif reference_digest != digest:
                if len(mismatch_ids) < max_details:
                    mismatch_ids.append(projection_id)

    reference_keys = set(reference.row_hash_by_projection)
    package_keys = set(package_hash_by_projection)
    missing_all = reference_keys - package_keys
    extra_all = package_keys - reference_keys
    mismatch_all = {
        projection_id
        for projection_id in reference_keys & package_keys
        if reference.row_hash_by_projection[projection_id]
        != package_hash_by_projection[projection_id]
    }

    keyed_hash = hashlib.sha256()
    for projection_id in sorted(package_hash_by_projection):
        keyed_hash.update(projection_id.encode("utf-8"))
        keyed_hash.update(b"\t")
        keyed_hash.update(package_hash_by_projection[projection_id].hex().encode("ascii"))
        keyed_hash.update(b"\n")

    return PackageSuffixAudit(
        path=path,
        full_header=full_header,
        suffix_header=suffix_header,
        prefix_ok=prefix_ok,
        row_count=row_count,
        duplicate_count=duplicate_count,
        duplicate_examples=duplicate_examples,
        missing_ids=sorted(missing_all)[:max_details],
        extra_ids=sorted(extra_all)[:max_details],
        mismatch_ids=sorted(mismatch_all)[:max_details],
        missing_count=len(missing_all),
        extra_count=len(extra_all),
        mismatch_count=len(mismatch_all),
        package_hash_by_projection=package_hash_by_projection,
        order_hash=order_hash.hexdigest(),
        keyed_semantic_hash=keyed_hash.hexdigest(),
        canonical_suffix_tsv_hash=canonical_suffix_tsv_hash.hexdigest(),
    )


def extract_rows_by_id(path: Path, wanted: set[str], *, skip_prefix: int = 0) -> tuple[list[str], dict[str, list[str]]]:
    if not wanted:
        return [], {}
    rows: dict[str, list[str]] = {}
    with open_text(path) as handle:
        reader = csv.reader(handle, delimiter="\t")
        header = next(reader)
        effective_header = header[skip_prefix:]
        if "projection_id" not in effective_header:
            raise ContractError(f"projection_id missing while extracting rows: {path}")
        index = effective_header.index("projection_id")
        for full_row in reader:
            row = full_row[skip_prefix:]
            projection_id = row[index]
            if projection_id in wanted and projection_id not in rows:
                rows[projection_id] = row
                if len(rows) == len(wanted):
                    break
    return effective_header, rows


def write_detail_files(
    outdir: Path,
    reference: CallerIndex,
    package: PackageSuffixAudit,
    max_details: int,
) -> None:
    id_rows: list[dict[str, object]] = []
    for category, values in [
        ("REFERENCE_DUPLICATE", reference.duplicate_examples),
        ("PACKAGE_DUPLICATE", package.duplicate_examples),
        ("MISSING_FROM_PACKAGE", package.missing_ids),
        ("EXTRA_IN_PACKAGE", package.extra_ids),
        ("VALUE_MISMATCH", package.mismatch_ids),
    ]:
        id_rows.extend(
            {"category": category, "projection_id": projection_id}
            for projection_id in values[:max_details]
        )
    atomic_write_tsv(
        outdir / "stage15a0_caller_parity_id_examples.tsv",
        ["category", "projection_id"],
        id_rows,
    )

    wanted = set(package.mismatch_ids[:max_details])
    reference_header, reference_rows = extract_rows_by_id(reference.path, wanted)
    package_header, package_rows = extract_rows_by_id(package.path, wanted, skip_prefix=8)
    field_rows: list[dict[str, object]] = []
    if wanted and reference_header != package_header:
        field_rows.append(
            {
                "projection_id": ".",
                "field_index": -1,
                "field_name": "<HEADER>",
                "reference_value": "\t".join(reference_header),
                "package_value": "\t".join(package_header),
            }
        )
    elif wanted:
        for projection_id in sorted(wanted):
            ref = reference_rows.get(projection_id)
            pkg = package_rows.get(projection_id)
            if ref is None or pkg is None:
                continue
            for index, (field, a, b) in enumerate(zip(reference_header, ref, pkg)):
                if a != b:
                    field_rows.append(
                        {
                            "projection_id": projection_id,
                            "field_index": index,
                            "field_name": field,
                            "reference_value": a,
                            "package_value": b,
                        }
                    )
    atomic_write_tsv(
        outdir / "stage15a0_caller_parity_field_differences.tsv",
        [
            "projection_id",
            "field_index",
            "field_name",
            "reference_value",
            "package_value",
        ],
        field_rows,
    )


def bool_text(value: bool) -> str:
    return "true" if value else "false"


def main() -> int:
    args = parse_args()
    project_root = args.project_root.resolve()
    run_id = args.run_id

    deterministic_root = (
        project_root
        / "results/14_deterministic_general_caller"
        / run_id
        / "v0.4.1_validation_v0.1.0/integration_native_100k"
    )
    reference = args.reference or deterministic_root / "general_repeat_calls.v0.4.0.tsv.gz"
    reused_calls = args.reused_calls or (
        project_root
        / "results/14_v041_schema_v041_100k_end_to_end"
        / run_id
        / "v0.1.0/caller/general_repeat_calls.v0.4.0.tsv.gz"
    )
    package_general = args.package_general or (
        project_root
        / "results/14_v041_schema_v042_100k_end_to_end"
        / run_id
        / "v0.1.1/package/general_repeat_calls.tsv.gz"
    )
    outdir = args.outdir or (
        project_root
        / "qc/15_stage15a_contract_preflight"
        / run_id
        / "v0.1.2_caller_parity"
    )
    outdir = outdir.resolve()

    for label, path in [
        ("reference", reference),
        ("reused_calls", reused_calls),
        ("package_general", package_general),
    ]:
        if not path.is_file() or path.stat().st_size == 0:
            raise ContractError(f"missing or empty {label}: {path}")

    outdir.mkdir(parents=True, exist_ok=True)
    qc_path = outdir / "stage15a0_caller_parity_resolution.qc.tsv"
    log_path = outdir / "stage15a0_caller_parity_resolution.log"

    reference_raw_sha = sha256_file(reference)
    reused_raw_sha = sha256_file(reused_calls)
    package_raw_sha = sha256_file(package_general)
    reference_dec_sha = decompressed_sha256(reference)
    reused_dec_sha = decompressed_sha256(reused_calls)
    reference_newline = newline_profile(reference)
    reused_newline = newline_profile(reused_calls)
    package_newline = newline_profile(package_general)

    reference_index = index_caller_table(reference, args.max_details)
    reused_index = index_caller_table(reused_calls, args.max_details)
    package_audit = audit_package_suffix(package_general, reference_index, args.max_details)

    reference_vs_reused_exact = (
        reference_dec_sha == reused_dec_sha
        and reference_index.row_count == reused_index.row_count
        and reference_index.header == reused_index.header
    )
    package_header_exact = package_audit.suffix_header == reference_index.header
    package_keyed_equal = (
        package_audit.prefix_ok
        and package_header_exact
        and reference_index.duplicate_count == 0
        and package_audit.duplicate_count == 0
        and package_audit.missing_count == 0
        and package_audit.extra_count == 0
        and package_audit.mismatch_count == 0
        and package_audit.keyed_semantic_hash == reference_index.keyed_semantic_hash
    )
    package_order_equal = package_audit.order_hash == reference_index.row_order_hash
    package_canonical_order_equal = (
        package_audit.canonical_suffix_tsv_hash == reference_index.canonical_tsv_hash
    )

    structural_ok = (
        len(reference_index.header) == args.expected_columns
        and reference_index.row_count == args.expected_rows
        and reused_index.row_count == args.expected_rows
        and package_audit.row_count == args.expected_rows
        and reference_index.called_attempts == args.expected_called
        and reference_index.low_confidence_called_attempts
        == args.expected_low_confidence_called
    )

    if reference_vs_reused_exact and package_keyed_equal and structural_ok:
        status = "PASS"
        next_gate = "READY_TO_FREEZE_STAGE15A_EXECUTION_BUNDLE"
    elif not reference_vs_reused_exact or not package_keyed_equal:
        status = "REVIEW"
        next_gate = "INSPECT_CALLER_VALUE_OR_KEY_DIFFERENCES"
    else:
        status = "REVIEW"
        next_gate = "RESOLVE_EXPECTED_CARDINALITY_OR_SUMMARY_MISMATCH"

    difference_class = "NONE"
    if package_keyed_equal and not package_canonical_order_equal:
        components: list[str] = []
        if not package_order_equal:
            components.append("ROW_ORDER")
        if reference_newline["style"] != package_newline["style"]:
            components.append("LINE_ENDING")
        difference_class = "+".join(components) or "SERIALIZATION_ONLY"
    elif not package_keyed_equal:
        difference_class = "KEY_OR_VALUE_DIFFERENCE"

    metrics: list[tuple[str, object]] = [
        ("stage_version", STAGE_VERSION),
        ("run_id", run_id),
        ("script_path", str(Path(__file__).resolve())),
        ("script_sha256", sha256_file(Path(__file__).resolve())),
        ("project_root", str(project_root)),
        ("reference_path", str(reference)),
        ("reference_raw_sha256", reference_raw_sha),
        ("reference_decompressed_sha256", reference_dec_sha),
        ("reused_calls_path", str(reused_calls)),
        ("reused_calls_raw_sha256", reused_raw_sha),
        ("reused_calls_decompressed_sha256", reused_dec_sha),
        ("reference_vs_reused_exact_decompressed_match", bool_text(reference_vs_reused_exact)),
        ("package_general_path", str(package_general)),
        ("package_general_raw_sha256", package_raw_sha),
        ("package_prefix_contract_ok", bool_text(package_audit.prefix_ok)),
        ("caller_header_columns", len(reference_index.header)),
        ("package_suffix_columns", len(package_audit.suffix_header)),
        ("package_suffix_header_exact_reference", bool_text(package_header_exact)),
        ("reference_rows", reference_index.row_count),
        ("reused_calls_rows", reused_index.row_count),
        ("package_suffix_rows", package_audit.row_count),
        ("reference_duplicate_projection_ids", reference_index.duplicate_count),
        ("reused_calls_duplicate_projection_ids", reused_index.duplicate_count),
        ("package_duplicate_projection_ids", package_audit.duplicate_count),
        ("package_missing_projection_ids", package_audit.missing_count),
        ("package_extra_projection_ids", package_audit.extra_count),
        ("package_value_mismatch_projection_ids", package_audit.mismatch_count),
        ("reference_keyed_semantic_sha256", reference_index.keyed_semantic_hash),
        ("package_keyed_semantic_sha256", package_audit.keyed_semantic_hash),
        ("package_suffix_keyed_semantic_match", bool_text(package_keyed_equal)),
        ("reference_projection_order_sha256", reference_index.row_order_hash),
        ("package_projection_order_sha256", package_audit.order_hash),
        ("package_projection_order_exact_reference", bool_text(package_order_equal)),
        ("reference_canonical_tsv_sha256", reference_index.canonical_tsv_hash),
        ("package_suffix_canonical_tsv_sha256", package_audit.canonical_suffix_tsv_hash),
        ("package_suffix_exact_ordered_canonical_match", bool_text(package_canonical_order_equal)),
        ("reference_newline_style", reference_newline["style"]),
        ("reused_calls_newline_style", reused_newline["style"]),
        ("package_general_newline_style", package_newline["style"]),
        ("reference_crlf_count", reference_newline["crlf"]),
        ("reference_bare_lf_count", reference_newline["bare_lf"]),
        ("package_crlf_count", package_newline["crlf"]),
        ("package_bare_lf_count", package_newline["bare_lf"]),
        ("called_attempt_rows", reference_index.called_attempts),
        ("low_confidence_called_rows", reference_index.low_confidence_called_attempts),
        ("preflight_v011_difference_class", difference_class),
        ("active_pipeline_modified", "false"),
        ("full_5_31m_run_started", "false"),
        ("audit_status", status),
        ("next_gate", next_gate),
    ]

    atomic_write_tsv(
        qc_path,
        ["metric", "value"],
        ({"metric": key, "value": value} for key, value in metrics),
    )
    write_detail_files(outdir, reference_index, package_audit, args.max_details)

    with log_path.open("w", encoding="utf-8", newline="") as log:
        log.write("===== Stage 15A0 caller parity resolution =====\n")
        for key, value in metrics:
            log.write(f"{key}\t{value}\n")
        log.write("\nInterpretation:\n")
        if status == "PASS" and difference_class != "NONE":
            log.write(
                "The Stage 14K2 package preserves all 77 caller fields exactly by "
                "projection_id. The v0.1.1 preflight mismatch is serialization/order "
                f"only: {difference_class}.\n"
            )
        elif status == "PASS":
            log.write("Exact ordered and keyed caller parity both pass.\n")
        else:
            log.write(
                "Key/value parity is not closed. See the ID and field-difference TSV files.\n"
            )

    print("===== Stage 15A0 caller parity resolution =====")
    for key, value in metrics:
        if key in {
            "reference_vs_reused_exact_decompressed_match",
            "package_suffix_keyed_semantic_match",
            "package_projection_order_exact_reference",
            "preflight_v011_difference_class",
            "called_attempt_rows",
            "low_confidence_called_rows",
            "audit_status",
            "next_gate",
        }:
            print(f"{key}\t{value}")
    print(f"QC\t{qc_path}")
    print(f"LOG\t{log_path}")

    return 0 if status == "PASS" else 3


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ContractError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
