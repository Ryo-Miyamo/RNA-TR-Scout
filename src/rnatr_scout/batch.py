"""Batch interfaces for production P3 decision classification."""

from __future__ import annotations

import csv
import os
import tempfile
from pathlib import Path
from typing import Iterable

from . import __version__
from .p3 import P3Observation, classify_p3

REQUIRED_P3_INPUT_COLUMNS = (
    "projection_id",
    "read_id",
    "target_region_id",
    "best_alignment_strand",
    "target_entry_projection_status",
    "canonical_motif",
    "target_facing_genomic_side",
    "tract_bp",
    "tract_reaches_expected_raw_end",
)

P3_BATCH_OUTPUT_COLUMNS = (
    "package_version",
    "projection_id",
    "read_id",
    "target_region_id",
    "primary_status",
    "standard_evidence_emitted",
    "evidence_class",
    "sizing_status",
    "failure_code",
    "repeat_bp_estimate",
    "repeat_bp_lower_bound",
    "allele_length_status",
    "expansion_status",
    "notes",
)


def _parse_boolean(value: str, field: str) -> bool:
    normalized = value.strip().lower()

    if normalized in {"true", "1", "yes"}:
        return True

    if normalized in {"false", "0", "no"}:
        return False

    raise ValueError(
        f"{field} must be true/false, 1/0, or yes/no; "
        f"observed {value!r}"
    )


def _parse_optional_nonnegative_integer(
    value: str,
    field: str,
) -> int | None:
    normalized = value.strip()

    if normalized in {"", "."}:
        return None

    parsed = int(normalized)

    if parsed < 0:
        raise ValueError(
            f"{field} must be non-negative"
        )

    return parsed


def classify_p3_row(
    row: dict[str, str],
) -> dict[str, object]:
    missing = [
        column
        for column in REQUIRED_P3_INPUT_COLUMNS
        if column not in row
    ]

    if missing:
        raise ValueError(
            "missing required columns in row: "
            + ",".join(missing)
        )

    projected = (
        row["target_entry_projection_status"]
        == "TARGET_ENTRY_PROJECTED"
    )

    observation = P3Observation(
        alignment_strand=row[
            "best_alignment_strand"
        ],
        target_entry_projected=projected,
        canonical_motif=row["canonical_motif"],
        target_facing_genomic_side=row[
            "target_facing_genomic_side"
        ],
        tract_bp=_parse_optional_nonnegative_integer(
            row["tract_bp"],
            "tract_bp",
        ),
        tract_reaches_expected_raw_end=(
            _parse_boolean(
                row[
                    "tract_reaches_expected_raw_end"
                ],
                "tract_reaches_expected_raw_end",
            )
        ),
    )

    decision = classify_p3(observation)

    return {
        "package_version": __version__,
        "projection_id": row["projection_id"],
        "read_id": row["read_id"],
        "target_region_id": row[
            "target_region_id"
        ],
        "primary_status": decision.primary_status,
        "standard_evidence_emitted": str(
            decision.standard_evidence_emitted
        ).lower(),
        "evidence_class": decision.evidence_class,
        "sizing_status": decision.sizing_status,
        "failure_code": decision.failure_code,
        "repeat_bp_estimate": (
            "."
            if decision.repeat_bp_estimate is None
            else decision.repeat_bp_estimate
        ),
        "repeat_bp_lower_bound": (
            "."
            if decision.repeat_bp_lower_bound is None
            else decision.repeat_bp_lower_bound
        ),
        "allele_length_status": (
            decision.allele_length_status
        ),
        "expansion_status": decision.expansion_status,
        "notes": decision.notes,
    }


def classify_p3_rows(
    rows: Iterable[dict[str, str]],
) -> list[dict[str, object]]:
    output = []

    for line_number, row in enumerate(
        rows,
        start=2,
    ):
        try:
            output.append(classify_p3_row(row))
        except Exception as error:
            raise ValueError(
                f"P3 input row {line_number}: {error}"
            ) from error

    return output


def classify_p3_tsv(
    input_path: str | Path,
    output_path: str | Path,
) -> int:
    input_path = Path(input_path)
    output_path = Path(output_path)

    with input_path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        reader = csv.DictReader(
            handle,
            delimiter="\t",
        )
        header = tuple(reader.fieldnames or ())
        missing = [
            column
            for column in REQUIRED_P3_INPUT_COLUMNS
            if column not in header
        ]

        if missing:
            raise ValueError(
                "input TSV is missing required columns: "
                + ",".join(missing)
            )

        results = classify_p3_rows(reader)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    file_descriptor, temporary_name = (
        tempfile.mkstemp(
            prefix=output_path.name + ".",
            suffix=".tmp",
            dir=output_path.parent,
            text=True,
        )
    )
    os.close(file_descriptor)
    temporary_path = Path(temporary_name)

    try:
        with temporary_path.open(
            "w",
            encoding="utf-8",
            newline="",
        ) as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=P3_BATCH_OUTPUT_COLUMNS,
                delimiter="\t",
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(results)

        temporary_path.replace(output_path)

    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise

    return len(results)
