#!/usr/bin/env bash
set -euo pipefail

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
fi

conda activate rnatr-v03
source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"
PACKAGE_VERSION="0.3.2"

PACKAGE_DIR="$PROJECT_ROOT/src/rnatr_scout"
UNIT_DIR="$PROJECT_ROOT/tests/unit"

SIZING="$PROJECT_ROOT/results/11_p3_target_entry_sizing/$RUN_ID/p3_target_entry_repeat_evidence.tsv"
FROZEN="$PROJECT_ROOT/results/11_p3_orientation_freeze/$RUN_ID/p3_orientation_corrected_classification.tsv"

OUTDIR="$PROJECT_ROOT/results/11_production_p3_batch/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_production_p3_batch/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_production_p3_batch/$RUN_ID"

OUTPUT="$OUTDIR/p3_production_replay.tsv"
QC="$QCDIR/p3_production_replay.qc.tsv"
UNIT_LOG="$OUTDIR/unit_tests.log"
MANIFEST="$OUTDIR/${RUN_ID}.production_p3_batch.manifest.tsv"

STAGE="$WORKDIR/stage"
STAGE_PACKAGE="$STAGE/rnatr_scout"
STAGE_TESTS="$STAGE/tests"

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR"

for path in \
  "$PACKAGE_DIR" \
  "$UNIT_DIR" \
  "$SIZING" \
  "$FROZEN"
do
    test -e "$path" || {
        echo "ERROR: missing required path: $path" >&2
        exit 1
    }
done

installed_version="$(rnatr-scout version)"

if [[ "$installed_version" != "$PACKAGE_VERSION" ]]; then
    echo "ERROR: unexpected installed package version: $installed_version" >&2
    exit 1
fi

rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -a "$PACKAGE_DIR" "$STAGE_PACKAGE"
cp -a "$UNIT_DIR" "$STAGE_TESTS"

cat > "$STAGE_PACKAGE/batch.py" <<'PY'
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
PY

cat > "$STAGE_PACKAGE/cli.py" <<'PY'
"""Command-line interface for RNA-TR-Scout."""

from __future__ import annotations

import argparse
import json

from . import __version__
from .batch import classify_p3_tsv
from .contract import check_contract
from .p3 import P3Observation, classify_p3


def _boolean(text: str) -> bool:
    normalized = text.strip().lower()

    if normalized in {"true", "yes", "1"}:
        return True

    if normalized in {"false", "no", "0"}:
        return False

    raise argparse.ArgumentTypeError(
        "expected true/false, yes/no, or 1/0"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rnatr-scout",
        description=(
            "Long-read RNA tandem-repeat evidence caller"
        ),
    )
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    subparsers.add_parser(
        "version",
        help="Print package version",
    )

    p3_parser = subparsers.add_parser(
        "p3-classify",
        help="Apply the frozen P3 decision layer",
    )
    p3_parser.add_argument(
        "--alignment-strand",
        required=True,
        choices=["+", "-"],
    )
    p3_parser.add_argument(
        "--target-entry-projected",
        required=True,
        type=_boolean,
    )
    p3_parser.add_argument(
        "--motif",
        required=True,
    )
    p3_parser.add_argument(
        "--target-side",
        required=True,
        choices=[
            "GENOMIC_LEFT",
            "GENOMIC_RIGHT",
        ],
    )
    p3_parser.add_argument(
        "--tract-bp",
        type=int,
        default=None,
    )
    p3_parser.add_argument(
        "--tract-reaches-raw-end",
        type=_boolean,
        default=False,
    )

    batch_parser = subparsers.add_parser(
        "p3-batch-classify",
        help=(
            "Apply P3 decision rules to every row of a TSV"
        ),
    )
    batch_parser.add_argument(
        "--input-tsv",
        required=True,
    )
    batch_parser.add_argument(
        "--output-tsv",
        required=True,
    )

    contract_parser = subparsers.add_parser(
        "contract-check",
        help="Check schema v0.3.2 and regression fixture",
    )
    contract_parser.add_argument(
        "--schema-dir",
        required=True,
    )
    contract_parser.add_argument(
        "--fixture-dir",
        required=True,
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)

    if arguments.command == "version":
        print(__version__)
        return 0

    if arguments.command == "p3-classify":
        observation = P3Observation(
            alignment_strand=arguments.alignment_strand,
            target_entry_projected=(
                arguments.target_entry_projected
            ),
            canonical_motif=arguments.motif,
            target_facing_genomic_side=(
                arguments.target_side
            ),
            tract_bp=arguments.tract_bp,
            tract_reaches_expected_raw_end=(
                arguments.tract_reaches_raw_end
            ),
        )
        decision = classify_p3(observation)
        print(
            json.dumps(
                decision.to_dict(),
                sort_keys=True,
            )
        )
        return 0

    if arguments.command == "p3-batch-classify":
        rows = classify_p3_tsv(
            arguments.input_tsv,
            arguments.output_tsv,
        )
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "rows_written": rows,
                    "output_tsv": arguments.output_tsv,
                },
                sort_keys=True,
            )
        )
        return 0

    if arguments.command == "contract-check":
        result = check_contract(
            arguments.schema_dir,
            arguments.fixture_dir,
        )
        print(
            json.dumps(
                result,
                sort_keys=True,
            )
        )
        return 0 if result["status"] == "PASS" else 1

    parser.error(
        f"unsupported command: {arguments.command}"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
PY

cat > "$STAGE_TESTS/test_batch.py" <<'PY'
from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from rnatr_scout.batch import (
    classify_p3_row,
    classify_p3_tsv,
)


def base_row():
    return {
        "projection_id": "projection-1",
        "read_id": "read-1",
        "target_region_id": "target-1",
        "best_alignment_strand": "+",
        "target_entry_projection_status":
            "TARGET_ENTRY_PROJECTED",
        "canonical_motif": "CAG",
        "target_facing_genomic_side":
            "GENOMIC_RIGHT",
        "tract_bp": "30",
        "tract_reaches_expected_raw_end":
            "false",
    }


class TestP3Batch(unittest.TestCase):
    def test_row_classification(self):
        result = classify_p3_row(base_row())
        self.assertEqual(
            result["evidence_class"],
            "LEFT_ONLY_INTERNAL",
        )

    def test_orientation_negative(self):
        row = base_row()
        row["best_alignment_strand"] = "-"
        result = classify_p3_row(row)
        self.assertEqual(
            result["failure_code"],
            "ORIENTATION_INCONSISTENT_BRIDGE",
        )

    def test_tsv_atomic_output(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            input_path = directory / "input.tsv"
            output_path = directory / "output.tsv"
            row = base_row()

            with input_path.open(
                "w",
                encoding="utf-8",
                newline="",
            ) as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=list(row.keys()),
                    delimiter="\t",
                    lineterminator="\n",
                )
                writer.writeheader()
                writer.writerow(row)

            count = classify_p3_tsv(
                input_path,
                output_path,
            )
            self.assertEqual(count, 1)
            self.assertTrue(output_path.is_file())

            with output_path.open(
                "r",
                encoding="utf-8",
                newline="",
            ) as handle:
                results = list(
                    csv.DictReader(
                        handle,
                        delimiter="\t",
                    )
                )

            self.assertEqual(
                results[0]["sizing_status"],
                "partial_internal",
            )

    def test_missing_header_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            input_path = directory / "input.tsv"
            output_path = directory / "output.tsv"
            input_path.write_text(
                "projection_id\tread_id\np\tr\n",
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                classify_p3_tsv(
                    input_path,
                    output_path,
                )


if __name__ == "__main__":
    unittest.main()
PY

echo "===== STAGED PYTHON SYNTAX ====="
python -m compileall -q \
  "$STAGE_PACKAGE" \
  "$STAGE_TESTS"
echo "Python compileall: PASS"

echo
echo "===== STAGED UNIT TESTS ====="
RNATR_PROJECT_ROOT="$PROJECT_ROOT" \
PYTHONPATH="$STAGE" \
python -m unittest discover \
  -s "$STAGE_TESTS" \
  -v \
  2>&1 | tee "$UNIT_LOG"

timestamp="$(date +%Y%m%d_%H%M%S)"
BACKUP="$PROJECT_ROOT/metadata/code_backups/11ao_${timestamp}"
mkdir -p "$BACKUP"

cp "$PACKAGE_DIR/cli.py" "$BACKUP/cli.py"
cp -a "$UNIT_DIR" "$BACKUP/unit_tests"

cp "$STAGE_PACKAGE/batch.py" \
  "$PACKAGE_DIR/batch.py"
cp "$STAGE_PACKAGE/cli.py" \
  "$PACKAGE_DIR/cli.py"
cp "$STAGE_TESTS/test_batch.py" \
  "$UNIT_DIR/test_batch.py"

echo
echo "===== INSTALLED PACKAGE UNIT TESTS ====="
RNATR_PROJECT_ROOT="$PROJECT_ROOT" \
python -m unittest discover \
  -s "$UNIT_DIR" \
  -v

rm -f "$OUTPUT"

echo
echo "===== PRODUCTION REPLAY OF 23 P3 ROWS ====="
rnatr-scout p3-batch-classify \
  --input-tsv "$SIZING" \
  --output-tsv "$OUTPUT"

python - \
  "$OUTPUT" \
  "$FROZEN" \
  "$QC" <<'PYQC'
from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

output_path = Path(sys.argv[1])
frozen_path = Path(sys.argv[2])
qc_path = Path(sys.argv[3])


def read_tsv(path: Path):
    with path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        return list(
            csv.DictReader(handle, delimiter="\t")
        )


outputs = read_tsv(output_path)
frozen = read_tsv(frozen_path)

output_lookup = {
    row["projection_id"]: row
    for row in outputs
}
frozen_lookup = {
    row["projection_id"]: row
    for row in frozen
}

missing_output = (
    set(frozen_lookup) - set(output_lookup)
)
unexpected_output = (
    set(output_lookup) - set(frozen_lookup)
)

status_mismatches = 0
emission_mismatches = 0
guardrail_failures = 0

for projection_id in sorted(
    set(output_lookup) & set(frozen_lookup)
):
    produced = output_lookup[projection_id]
    expected = frozen_lookup[projection_id]

    if (
        produced["primary_status"]
        != expected["frozen_p3_status"]
    ):
        status_mismatches += 1

    if (
        produced["standard_evidence_emitted"]
        != expected[
            "standard_p3_evidence_emitted"
        ]
    ):
        emission_mismatches += 1

    if (
        produced["repeat_bp_estimate"] != "."
        or produced["expansion_status"]
           != "NOT_ASSESSED"
    ):
        guardrail_failures += 1

status_counts = Counter(
    row["primary_status"]
    for row in outputs
)
failure_counts = Counter(
    row["failure_code"]
    for row in outputs
)

status = "PASS"

if (
    len(outputs) != 23
    or len(frozen) != 23
    or missing_output
    or unexpected_output
    or status_mismatches
    or emission_mismatches
    or guardrail_failures
    or status_counts[
        "REJECT_ORIENTATION_INCONSISTENT_BRIDGE"
    ] != 22
    or status_counts[
        "HOMOPOLYMER_REVIEW_NO_STANDARD_P3_EVIDENCE"
    ] != 1
):
    status = "REVIEW"

with qc_path.open(
    "w",
    encoding="utf-8",
) as handle:
    handle.write("metric\tvalue\n")
    handle.write(
        "package_version\t0.3.2\n"
    )
    handle.write(
        "production_rows_written\t{}\n".format(
            len(outputs)
        )
    )
    handle.write(
        "frozen_rows_expected\t{}\n".format(
            len(frozen)
        )
    )
    handle.write(
        "missing_output_rows\t{}\n".format(
            len(missing_output)
        )
    )
    handle.write(
        "unexpected_output_rows\t{}\n".format(
            len(unexpected_output)
        )
    )
    handle.write(
        "primary_status_mismatches\t{}\n".format(
            status_mismatches
        )
    )
    handle.write(
        "evidence_emission_mismatches\t{}\n".format(
            emission_mismatches
        )
    )
    handle.write(
        "length_expansion_guardrail_failures\t{}\n".format(
            guardrail_failures
        )
    )

    for key, count in sorted(
        status_counts.items()
    ):
        handle.write(
            "primary_status::{}\t{}\n".format(
                key,
                count,
            )
        )

    for key, count in sorted(
        failure_counts.items()
    ):
        handle.write(
            "failure_code::{}\t{}\n".format(
                key,
                count,
            )
        )

    handle.write(
        "production_replay_status\t{}\n".format(
            status
        )
    )

if status != "PASS":
    raise SystemExit(
        "Production P3 replay requires review"
    )
PYQC

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in \
      "$PACKAGE_DIR/batch.py" \
      "$PACKAGE_DIR/cli.py" \
      "$UNIT_DIR/test_batch.py" \
      "$OUTPUT" \
      "$QC" \
      "$UNIT_LOG"
    do
        if [[ "$path" == *.tsv ]]; then
            rows="$(awk 'END {print NR-1}' "$path")"
        else
            rows="."
        fi

        printf '%s\t%s\t%s\t%s\t%s\n' \
          "$(basename "$path")" \
          "$rows" \
          "$(stat -c '%s' "$path")" \
          "$(sha256sum "$path" | awk '{print $1}')" \
          "$path"
    done
} > "$MANIFEST"

echo
echo "===== QC ====="
column -ts $'\t' "$QC"

echo
echo "===== PRODUCTION OUTPUT ====="
column -ts $'\t' "$OUTPUT"

echo
echo "===== MANIFEST ====="
column -ts $'\t' "$MANIFEST"

echo
echo "===== BACKUP ====="
echo "$BACKUP"
