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

ISOLATED="$PROJECT_ROOT/results/11_p3_isolated_pair_validation/$RUN_ID/p3_isolated_pair_validation.tsv.gz"
SIZING="$PROJECT_ROOT/results/11_p3_target_entry_sizing/$RUN_ID/p3_target_entry_repeat_evidence.tsv"

OUTDIR="$PROJECT_ROOT/results/11_production_p3_bridge/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_production_p3_bridge/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_production_p3_bridge/$RUN_ID"

REPLAY="$OUTDIR/p3_bridge_validation_replay.tsv"
QC="$QCDIR/p3_bridge_alignment_core.qc.tsv"
UNIT_LOG="$OUTDIR/unit_tests.log"
MANIFEST="$OUTDIR/${RUN_ID}.production_p3_bridge.manifest.tsv"

STAGE="$WORKDIR/stage"
STAGE_PACKAGE="$STAGE/rnatr_scout"
STAGE_TESTS="$STAGE/tests"

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR"

for path in \
  "$PACKAGE_DIR" \
  "$UNIT_DIR" \
  "$ISOLATED" \
  "$SIZING"
do
    test -e "$path" || {
        echo "ERROR: missing required path: $path" >&2
        exit 1
    }
done

if [[ -e "$PACKAGE_DIR/p3_bridge.py" ]]; then
    echo "ERROR: production module already exists: $PACKAGE_DIR/p3_bridge.py" >&2
    exit 1
fi

if [[ -e "$UNIT_DIR/test_p3_bridge.py" ]]; then
    echo "ERROR: unit test already exists: $UNIT_DIR/test_p3_bridge.py" >&2
    exit 1
fi

installed_version="$(rnatr-scout version)"

if [[ "$installed_version" != "$PACKAGE_VERSION" ]]; then
    echo "ERROR: unexpected installed version: $installed_version" >&2
    exit 1
fi

rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -a "$PACKAGE_DIR" "$STAGE_PACKAGE"
cp -a "$UNIT_DIR" "$STAGE_TESTS"

cat > "$STAGE_PACKAGE/p3_bridge.py" <<'PY'
"""Production validation of candidate P3 bridge alignments."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class BridgeAlignmentObservation:
    """Minimal alignment data needed for P3 bridge validation."""

    alignment_present: bool
    alignment_strand: str | None
    query_start: int | None
    reference_start: int | None
    query_coverage: float | None
    identity: float | None
    reference_end: int | None
    bridge_bp: int
    target_entry_bp: int
    query_can_reach_target_entry: bool


@dataclass(frozen=True)
class BridgeAlignmentDecision:
    """Guarded interpretation of one candidate bridge alignment."""

    bridge_status: str
    bridge_valid: bool
    required_reference_end: int
    orientation_consistent: bool
    boundary_connected: bool
    quality_pass: bool
    target_entry_reached: bool
    notes: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _validate_observation(
    observation: BridgeAlignmentObservation,
) -> None:
    if observation.bridge_bp < 0:
        raise ValueError("bridge_bp must be non-negative")

    if observation.target_entry_bp <= 0:
        raise ValueError(
            "target_entry_bp must be positive"
        )

    optional_nonnegative = (
        observation.query_start,
        observation.reference_start,
        observation.reference_end,
    )

    if any(
        value is not None and value < 0
        for value in optional_nonnegative
    ):
        raise ValueError(
            "alignment coordinates must be non-negative"
        )

    for name, value in (
        ("query_coverage", observation.query_coverage),
        ("identity", observation.identity),
    ):
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValueError(
                f"{name} must be between 0 and 1"
            )

    if (
        observation.alignment_strand is not None
        and observation.alignment_strand not in {"+", "-"}
    ):
        raise ValueError(
            "alignment_strand must be '+', '-', or None"
        )


def evaluate_bridge_alignment(
    observation: BridgeAlignmentObservation,
    *,
    minimum_target_entry_bp: int = 12,
    boundary_tolerance_bp: int = 10,
    minimum_identity: float = 0.70,
    minimum_query_coverage: float = 0.70,
) -> BridgeAlignmentDecision:
    """Evaluate whether a normalized alignment proves a P3 bridge.

    Query and candidate reference must both run from the mapped-block
    boundary toward the target. Therefore a valid bridge requires a
    plus-orientation alignment.
    """

    _validate_observation(observation)

    if minimum_target_entry_bp <= 0:
        raise ValueError(
            "minimum_target_entry_bp must be positive"
        )

    if boundary_tolerance_bp < 0:
        raise ValueError(
            "boundary_tolerance_bp must be non-negative"
        )

    if not 0.0 <= minimum_identity <= 1.0:
        raise ValueError(
            "minimum_identity must be between 0 and 1"
        )

    if not 0.0 <= minimum_query_coverage <= 1.0:
        raise ValueError(
            "minimum_query_coverage must be between 0 and 1"
        )

    required_reference_end = (
        observation.bridge_bp
        + min(
            observation.target_entry_bp,
            minimum_target_entry_bp,
        )
    )

    defaults = {
        "required_reference_end": required_reference_end,
        "orientation_consistent": False,
        "boundary_connected": False,
        "quality_pass": False,
        "target_entry_reached": False,
    }

    if not observation.query_can_reach_target_entry:
        return BridgeAlignmentDecision(
            bridge_status=(
                "QUERY_TOO_SHORT_TO_REACH_TARGET"
            ),
            bridge_valid=False,
            notes=(
                "The target-facing query is shorter than the "
                "bridge plus required target-entry support."
            ),
            **defaults,
        )

    if not observation.alignment_present:
        return BridgeAlignmentDecision(
            bridge_status="NO_CANDIDATE_ALIGNMENT",
            bridge_valid=False,
            notes=(
                "No candidate-reference alignment was available."
            ),
            **defaults,
        )

    required_fields = {
        "alignment_strand":
            observation.alignment_strand,
        "query_start": observation.query_start,
        "reference_start": observation.reference_start,
        "query_coverage": observation.query_coverage,
        "identity": observation.identity,
        "reference_end": observation.reference_end,
    }
    missing = [
        name
        for name, value in required_fields.items()
        if value is None
    ]

    if missing:
        raise ValueError(
            "alignment_present is true but fields are missing: "
            + ",".join(missing)
        )

    orientation_consistent = (
        observation.alignment_strand == "+"
    )

    if not orientation_consistent:
        return BridgeAlignmentDecision(
            bridge_status=(
                "ORIENTATION_INCONSISTENT_BRIDGE"
            ),
            bridge_valid=False,
            orientation_consistent=False,
            boundary_connected=False,
            quality_pass=False,
            target_entry_reached=False,
            required_reference_end=(
                required_reference_end
            ),
            notes=(
                "Query and candidate reference were normalized "
                "toward the target, but alignment was reverse."
            ),
        )

    boundary_connected = (
        observation.query_start
        <= boundary_tolerance_bp
        and observation.reference_start
        <= boundary_tolerance_bp
    )

    if not boundary_connected:
        return BridgeAlignmentDecision(
            bridge_status=(
                "ALIGNMENT_NOT_CONNECTED_TO_BLOCK_BOUNDARY"
            ),
            bridge_valid=False,
            orientation_consistent=True,
            boundary_connected=False,
            quality_pass=False,
            target_entry_reached=False,
            required_reference_end=(
                required_reference_end
            ),
            notes=(
                "Alignment does not begin near both normalized "
                "block-boundary sequence starts."
            ),
        )

    quality_pass = (
        observation.identity >= minimum_identity
        and observation.query_coverage
        >= minimum_query_coverage
    )

    if not quality_pass:
        return BridgeAlignmentDecision(
            bridge_status=(
                "LOW_QUALITY_BRIDGE_ALIGNMENT"
            ),
            bridge_valid=False,
            orientation_consistent=True,
            boundary_connected=True,
            quality_pass=False,
            target_entry_reached=False,
            required_reference_end=(
                required_reference_end
            ),
            notes=(
                "Boundary-connected alignment does not satisfy "
                "identity and query-coverage thresholds."
            ),
        )

    target_entry_reached = (
        observation.reference_end
        >= required_reference_end
    )

    if not target_entry_reached:
        return BridgeAlignmentDecision(
            bridge_status=(
                "BRIDGE_STOPS_BEFORE_TARGET_ENTRY"
            ),
            bridge_valid=False,
            orientation_consistent=True,
            boundary_connected=True,
            quality_pass=True,
            target_entry_reached=False,
            required_reference_end=(
                required_reference_end
            ),
            notes=(
                "Alignment supports the bridge but does not reach "
                "the required number of target-entry bases."
            ),
        )

    return BridgeAlignmentDecision(
        bridge_status="BRIDGE_REACHES_TARGET_ENTRY",
        bridge_valid=True,
        orientation_consistent=True,
        boundary_connected=True,
        quality_pass=True,
        target_entry_reached=True,
        required_reference_end=required_reference_end,
        notes=(
            "Plus-orientation, boundary-connected, quality-passing "
            "alignment reaches the required target entry."
        ),
    )
PY

cat > "$STAGE_TESTS/test_p3_bridge.py" <<'PY'
from __future__ import annotations

import unittest

from rnatr_scout.p3_bridge import (
    BridgeAlignmentObservation,
    evaluate_bridge_alignment,
)


def observation(**updates):
    values = {
        "alignment_present": True,
        "alignment_strand": "+",
        "query_start": 0,
        "reference_start": 0,
        "query_coverage": 0.80,
        "identity": 0.90,
        "reference_end": 30,
        "bridge_bp": 7,
        "target_entry_bp": 60,
        "query_can_reach_target_entry": True,
    }
    values.update(updates)
    return BridgeAlignmentObservation(**values)


class TestP3Bridge(unittest.TestCase):
    def test_valid_bridge(self):
        decision = evaluate_bridge_alignment(
            observation()
        )
        self.assertTrue(decision.bridge_valid)
        self.assertEqual(
            decision.bridge_status,
            "BRIDGE_REACHES_TARGET_ENTRY",
        )
        self.assertEqual(
            decision.required_reference_end,
            19,
        )

    def test_query_too_short(self):
        decision = evaluate_bridge_alignment(
            observation(
                query_can_reach_target_entry=False
            )
        )
        self.assertEqual(
            decision.bridge_status,
            "QUERY_TOO_SHORT_TO_REACH_TARGET",
        )

    def test_no_alignment(self):
        decision = evaluate_bridge_alignment(
            observation(
                alignment_present=False,
                alignment_strand=None,
                query_start=None,
                reference_start=None,
                query_coverage=None,
                identity=None,
                reference_end=None,
            )
        )
        self.assertEqual(
            decision.bridge_status,
            "NO_CANDIDATE_ALIGNMENT",
        )

    def test_reverse_rejected_before_other_checks(self):
        decision = evaluate_bridge_alignment(
            observation(
                alignment_strand="-",
                query_start=100,
                identity=0.10,
            )
        )
        self.assertEqual(
            decision.bridge_status,
            "ORIENTATION_INCONSISTENT_BRIDGE",
        )

    def test_boundary_required(self):
        decision = evaluate_bridge_alignment(
            observation(query_start=11)
        )
        self.assertEqual(
            decision.bridge_status,
            "ALIGNMENT_NOT_CONNECTED_TO_BLOCK_BOUNDARY",
        )

    def test_quality_required(self):
        decision = evaluate_bridge_alignment(
            observation(identity=0.69)
        )
        self.assertEqual(
            decision.bridge_status,
            "LOW_QUALITY_BRIDGE_ALIGNMENT",
        )

    def test_target_entry_required(self):
        decision = evaluate_bridge_alignment(
            observation(reference_end=18)
        )
        self.assertEqual(
            decision.bridge_status,
            "BRIDGE_STOPS_BEFORE_TARGET_ENTRY",
        )

    def test_missing_fields_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_bridge_alignment(
                observation(identity=None)
            )


if __name__ == "__main__":
    unittest.main()
PY

python - "$STAGE_PACKAGE/cli.py" <<'PYPATCH'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

import_anchor = (
    "from .p3_geometry import (\n"
    "    candidate_reference_geometry,\n"
    "    expected_orientation_transform,\n"
    ")\n"
)
import_replacement = (
    import_anchor
    + "from .p3_bridge import (\n"
      "    BridgeAlignmentObservation,\n"
      "    evaluate_bridge_alignment,\n"
      ")\n"
)

if import_anchor not in text:
    raise SystemExit(
        "CLI import anchor not found"
    )

text = text.replace(
    import_anchor,
    import_replacement,
    1,
)

parser_anchor = (
    "    contract_parser = subparsers.add_parser(\n"
    "        \"contract-check\",\n"
)
parser_block = """    bridge_parser = subparsers.add_parser(
        "p3-bridge-evaluate",
        help="Evaluate one normalized candidate bridge alignment",
    )
    bridge_parser.add_argument(
        "--alignment-present",
        required=True,
        type=_boolean,
    )
    bridge_parser.add_argument(
        "--alignment-strand",
        choices=["+", "-"],
    )
    bridge_parser.add_argument(
        "--query-start",
        type=int,
    )
    bridge_parser.add_argument(
        "--reference-start",
        type=int,
    )
    bridge_parser.add_argument(
        "--query-coverage",
        type=float,
    )
    bridge_parser.add_argument(
        "--identity",
        type=float,
    )
    bridge_parser.add_argument(
        "--reference-end",
        type=int,
    )
    bridge_parser.add_argument(
        "--bridge-bp",
        required=True,
        type=int,
    )
    bridge_parser.add_argument(
        "--target-entry-bp",
        required=True,
        type=int,
    )
    bridge_parser.add_argument(
        "--query-can-reach-target-entry",
        required=True,
        type=_boolean,
    )
    bridge_parser.add_argument(
        "--minimum-target-entry-bp",
        type=int,
        default=12,
    )
    bridge_parser.add_argument(
        "--boundary-tolerance-bp",
        type=int,
        default=10,
    )
    bridge_parser.add_argument(
        "--minimum-identity",
        type=float,
        default=0.70,
    )
    bridge_parser.add_argument(
        "--minimum-query-coverage",
        type=float,
        default=0.70,
    )

"""

if parser_anchor not in text:
    raise SystemExit(
        "CLI parser anchor not found"
    )

text = text.replace(
    parser_anchor,
    parser_block + parser_anchor,
    1,
)

handler_anchor = (
    "    if arguments.command == \"contract-check\":\n"
)
handler_block = """    if arguments.command == "p3-bridge-evaluate":
        observation = BridgeAlignmentObservation(
            alignment_present=arguments.alignment_present,
            alignment_strand=arguments.alignment_strand,
            query_start=arguments.query_start,
            reference_start=arguments.reference_start,
            query_coverage=arguments.query_coverage,
            identity=arguments.identity,
            reference_end=arguments.reference_end,
            bridge_bp=arguments.bridge_bp,
            target_entry_bp=arguments.target_entry_bp,
            query_can_reach_target_entry=(
                arguments.query_can_reach_target_entry
            ),
        )
        decision = evaluate_bridge_alignment(
            observation,
            minimum_target_entry_bp=(
                arguments.minimum_target_entry_bp
            ),
            boundary_tolerance_bp=(
                arguments.boundary_tolerance_bp
            ),
            minimum_identity=arguments.minimum_identity,
            minimum_query_coverage=(
                arguments.minimum_query_coverage
            ),
        )
        print(
            json.dumps(
                decision.to_dict(),
                sort_keys=True,
            )
        )
        return 0

"""

if handler_anchor not in text:
    raise SystemExit(
        "CLI handler anchor not found"
    )

text = text.replace(
    handler_anchor,
    handler_block + handler_anchor,
    1,
)

path.write_text(text, encoding="utf-8")
PYPATCH

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

echo
echo "===== STAGED CLI SMOKE TEST ====="
PYTHONPATH="$STAGE" \
python -m rnatr_scout.cli p3-bridge-evaluate \
  --alignment-present true \
  --alignment-strand + \
  --query-start 0 \
  --reference-start 0 \
  --query-coverage 0.80 \
  --identity 0.90 \
  --reference-end 30 \
  --bridge-bp 7 \
  --target-entry-bp 60 \
  --query-can-reach-target-entry true

timestamp="$(date +%Y%m%d_%H%M%S)"
BACKUP="$PROJECT_ROOT/metadata/code_backups/11aq_${timestamp}"
mkdir -p "$BACKUP"

cp "$PACKAGE_DIR/cli.py" "$BACKUP/cli.py"
cp -a "$UNIT_DIR" "$BACKUP/unit_tests"

cp "$STAGE_PACKAGE/p3_bridge.py" \
  "$PACKAGE_DIR/p3_bridge.py"
cp "$STAGE_PACKAGE/cli.py" \
  "$PACKAGE_DIR/cli.py"
cp "$STAGE_TESTS/test_p3_bridge.py" \
  "$UNIT_DIR/test_p3_bridge.py"

echo
echo "===== INSTALLED PACKAGE UNIT TESTS ====="
RNATR_PROJECT_ROOT="$PROJECT_ROOT" \
python -m unittest discover \
  -s "$UNIT_DIR" \
  -v

echo
echo "===== REPLAY 23 PILOT BRIDGE ALIGNMENTS ====="

python - \
  "$ISOLATED" \
  "$SIZING" \
  "$REPLAY" \
  "$QC" <<'PYREPLAY'
from __future__ import annotations

import csv
import gzip
import sys
from collections import Counter
from pathlib import Path

from rnatr_scout.p3_bridge import (
    BridgeAlignmentObservation,
    evaluate_bridge_alignment,
)

isolated_path = Path(sys.argv[1])
sizing_path = Path(sys.argv[2])
replay_path = Path(sys.argv[3])
qc_path = Path(sys.argv[4])

with gzip.open(
    isolated_path,
    "rt",
    encoding="utf-8",
    newline="",
) as handle:
    isolated_lookup = {
        row["projection_id"]: row
        for row in csv.DictReader(
            handle,
            delimiter="\t",
        )
    }

with sizing_path.open(
    "r",
    encoding="utf-8",
    newline="",
) as handle:
    sizing_rows = list(
        csv.DictReader(handle, delimiter="\t")
    )


def optional_int(value: str):
    return None if value == "." else int(value)


def optional_float(value: str):
    return None if value == "." else float(value)


results = []
missing_isolated = 0
status_counts = Counter()

for sizing in sizing_rows:
    projection_id = sizing["projection_id"]
    isolated = isolated_lookup.get(projection_id)

    if isolated is None:
        missing_isolated += 1
        continue

    alignment_present = (
        int(isolated["isolated_alignment_count"]) > 0
        and isolated["best_query_start"] != "."
    )

    observation = BridgeAlignmentObservation(
        alignment_present=alignment_present,
        alignment_strand=(
            sizing["best_alignment_strand"]
            if alignment_present
            else None
        ),
        query_start=optional_int(
            isolated["best_query_start"]
        ),
        reference_start=optional_int(
            isolated["best_reference_start"]
        ),
        query_coverage=optional_float(
            isolated["best_query_coverage"]
        ),
        identity=optional_float(
            isolated["best_identity"]
        ),
        reference_end=optional_int(
            isolated["best_reference_end"]
        ),
        bridge_bp=int(isolated["bridge_bp"]),
        target_entry_bp=int(
            isolated["target_entry_bp"]
        ),
        query_can_reach_target_entry=(
            isolated[
                "query_can_reach_target_entry"
            ] == "true"
        ),
    )

    decision = evaluate_bridge_alignment(
        observation
    )
    status_counts[
        decision.bridge_status
    ] += 1

    results.append(
        {
            "projection_id": projection_id,
            "read_id": sizing["read_id"],
            "target_region_id": sizing[
                "target_region_id"
            ],
            "alignment_strand": (
                sizing["best_alignment_strand"]
            ),
            "query_start": isolated[
                "best_query_start"
            ],
            "reference_start": isolated[
                "best_reference_start"
            ],
            "query_coverage": isolated[
                "best_query_coverage"
            ],
            "identity": isolated[
                "best_identity"
            ],
            "reference_end": isolated[
                "best_reference_end"
            ],
            "bridge_bp": isolated["bridge_bp"],
            "target_entry_bp": isolated[
                "target_entry_bp"
            ],
            "production_bridge_status": (
                decision.bridge_status
            ),
            "production_bridge_valid": str(
                decision.bridge_valid
            ).lower(),
            "expected_sizing_projection_status": (
                sizing[
                    "target_entry_projection_status"
                ]
            ),
        }
    )

with replay_path.open(
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=list(results[0].keys()),
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(results)

valid_rows = sum(
    row["production_bridge_valid"] == "true"
    for row in results
)
projected_rows = sum(
    row["expected_sizing_projection_status"]
    == "TARGET_ENTRY_PROJECTED"
    for row in results
)
consistency_mismatches = sum(
    (
        row["production_bridge_valid"] == "true"
    )
    != (
        row["expected_sizing_projection_status"]
        == "TARGET_ENTRY_PROJECTED"
    )
    for row in results
)

status = "PASS"

if (
    len(sizing_rows) != 23
    or len(results) != 23
    or missing_isolated
    or valid_rows != 1
    or projected_rows != 1
    or consistency_mismatches
    or status_counts[
        "ORIENTATION_INCONSISTENT_BRIDGE"
    ] != 22
    or status_counts[
        "BRIDGE_REACHES_TARGET_ENTRY"
    ] != 1
):
    status = "REVIEW"

with qc_path.open(
    "w",
    encoding="utf-8",
) as handle:
    handle.write("metric\tvalue\n")
    handle.write("package_version\t0.3.2\n")
    handle.write(
        "sizing_rows\t{}\n".format(
            len(sizing_rows)
        )
    )
    handle.write(
        "bridge_rows_replayed\t{}\n".format(
            len(results)
        )
    )
    handle.write(
        "missing_isolated_rows\t{}\n".format(
            missing_isolated
        )
    )
    handle.write(
        "production_valid_bridges\t{}\n".format(
            valid_rows
        )
    )
    handle.write(
        "previous_projected_entries\t{}\n".format(
            projected_rows
        )
    )
    handle.write(
        "bridge_projection_consistency_mismatches\t{}\n".format(
            consistency_mismatches
        )
    )

    for key, value in sorted(
        status_counts.items()
    ):
        handle.write(
            "bridge_status::{}\t{}\n".format(
                key,
                value,
            )
        )

    handle.write(
        "bridge_alignment_core_status\t{}\n".format(
            status
        )
    )

if status != "PASS":
    raise SystemExit(
        "Production bridge replay requires review"
    )
PYREPLAY

echo
echo "===== INSTALLED CLI SMOKE TEST ====="
rnatr-scout p3-bridge-evaluate \
  --alignment-present true \
  --alignment-strand + \
  --query-start 0 \
  --reference-start 0 \
  --query-coverage 0.80 \
  --identity 0.90 \
  --reference-end 30 \
  --bridge-bp 7 \
  --target-entry-bp 60 \
  --query-can-reach-target-entry true

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in \
      "$PACKAGE_DIR/p3_bridge.py" \
      "$PACKAGE_DIR/cli.py" \
      "$UNIT_DIR/test_p3_bridge.py" \
      "$REPLAY" \
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
echo "===== BRIDGE REPLAY ====="
column -ts $'\t' "$REPLAY"

echo
echo "===== MANIFEST ====="
column -ts $'\t' "$MANIFEST"

echo
echo "===== BACKUP ====="
echo "$BACKUP"
