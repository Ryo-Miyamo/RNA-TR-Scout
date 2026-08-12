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

SCHEMA_DIR="$PROJECT_ROOT/config/evidence_schema/v0.3.2"
FIXTURE_DIR="$PROJECT_ROOT/tests/regression/v0.3.2"

OUTDIR="$PROJECT_ROOT/results/11_production_package/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_production_package/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_production_package/$RUN_ID"

QC="$QCDIR/production_package_skeleton.qc.tsv"
MANIFEST="$OUTDIR/${RUN_ID}.production_package_skeleton.manifest.tsv"
UNIT_LOG="$OUTDIR/unit_tests.log"
SMOKE_LOG="$OUTDIR/cli_smoke_tests.log"

STAGE="$WORKDIR/package_stage"
STAGE_SRC="$STAGE/src/rnatr_scout"
STAGE_TESTS="$STAGE/tests/unit"

FINAL_PYPROJECT="$PROJECT_ROOT/pyproject.toml"
FINAL_PACKAGE="$PROJECT_ROOT/src/rnatr_scout"
FINAL_TESTS="$PROJECT_ROOT/tests/unit"

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR"

for path in "$SCHEMA_DIR" "$FIXTURE_DIR"; do
    test -e "$path" || {
        echo "ERROR: missing required path: $path" >&2
        exit 1
    }
done

for path in \
  "$FINAL_PYPROJECT" \
  "$FINAL_PACKAGE"
do
    if [[ -e "$path" ]]; then
        echo "ERROR: production package target already exists: $path" >&2
        echo "Review the existing package before running this creator." >&2
        exit 1
    fi
done

if [[ -e "$FINAL_TESTS" ]]; then
    echo "ERROR: unit-test target already exists: $FINAL_TESTS" >&2
    exit 1
fi

rm -rf "$STAGE"
mkdir -p "$STAGE_SRC" "$STAGE_TESTS"

cat > "$STAGE/pyproject.toml" <<'EOF'
[build-system]
requires = ["setuptools>=64"]
build-backend = "setuptools.build_meta"

[project]
name = "rna-tr-scout"
version = "0.3.2"
description = "Long-read RNA tandem-repeat evidence caller"
requires-python = ">=3.10"
authors = [
  {name = "RNA-TR-Scout developers"}
]
license = {text = "Research software; license not yet selected"}
dependencies = []

[project.scripts]
rnatr-scout = "rnatr_scout.cli:main"

[tool.setuptools]
package-dir = {"" = "src"}

[tool.setuptools.packages.find]
where = ["src"]
EOF

cat > "$STAGE_SRC/__init__.py" <<'PY'
"""RNA-TR-Scout production package."""

from .p3 import P3Decision, P3Observation, classify_p3

__all__ = [
    "P3Decision",
    "P3Observation",
    "classify_p3",
]

__version__ = "0.3.2"
PY

cat > "$STAGE_SRC/__main__.py" <<'PY'
from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
PY

cat > "$STAGE_SRC/p3.py" <<'PY'
"""Pure P3 bridge and one-flank evidence rules.

P3 means that a mapped alignment block stops before a repeat target
and the target-facing raw-read sequence is examined for a bridge into
the target. This module deliberately does not perform alignment or
repeat scanning. It converts validated observations into guarded
evidence classifications.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

TargetSide = Literal["GENOMIC_LEFT", "GENOMIC_RIGHT"]


@dataclass(frozen=True)
class P3Observation:
    """Validated inputs required for the P3 decision layer."""

    alignment_strand: str
    target_entry_projected: bool
    canonical_motif: str
    target_facing_genomic_side: TargetSide
    tract_bp: int | None
    tract_reaches_expected_raw_end: bool


@dataclass(frozen=True)
class P3Decision:
    """Schema-oriented P3 result with mandatory sizing guardrails."""

    primary_status: str
    standard_evidence_emitted: bool
    evidence_class: str
    sizing_status: str
    failure_code: str
    repeat_bp_estimate: float | None
    repeat_bp_lower_bound: float | None
    allele_length_status: str
    expansion_status: str
    notes: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _validate_observation(observation: P3Observation) -> None:
    if observation.alignment_strand not in {"+", "-"}:
        raise ValueError(
            "alignment_strand must be '+' or '-'"
        )

    if observation.target_facing_genomic_side not in {
        "GENOMIC_LEFT",
        "GENOMIC_RIGHT",
    }:
        raise ValueError(
            "target_facing_genomic_side must be "
            "GENOMIC_LEFT or GENOMIC_RIGHT"
        )

    motif = observation.canonical_motif.upper()

    if not motif or any(base not in "ACGT" for base in motif):
        raise ValueError(
            "canonical_motif must contain only A/C/G/T"
        )

    if observation.tract_bp is not None and observation.tract_bp < 0:
        raise ValueError("tract_bp must be non-negative")


def classify_p3(observation: P3Observation) -> P3Decision:
    """Apply frozen P3 v0.3.2 decision rules.

    Rule priority:
      1. Orientation
      2. Target-entry projection
      3. Homopolymer routing
      4. Repeat-tract availability
      5. Censored versus internal one-flank evidence

    Exact allele length and expansion status are intentionally
    unavailable for every P3 result.
    """

    _validate_observation(observation)
    motif = observation.canonical_motif.upper()

    common = {
        "repeat_bp_estimate": None,
        "allele_length_status": "NOT_MEASURABLE_ONE_FLANK_P3",
        "expansion_status": "NOT_ASSESSED",
    }

    if observation.alignment_strand != "+":
        return P3Decision(
            primary_status="REJECT_ORIENTATION_INCONSISTENT_BRIDGE",
            standard_evidence_emitted=False,
            evidence_class="UNRESOLVED",
            sizing_status="no_call",
            failure_code="ORIENTATION_INCONSISTENT_BRIDGE",
            repeat_bp_lower_bound=None,
            notes=(
                "Query and candidate reference were normalized from "
                "mapped-block boundary toward target, but only "
                "reverse-orientation compatibility was observed."
            ),
            **common,
        )

    if not observation.target_entry_projected:
        return P3Decision(
            primary_status="REJECT_TARGET_ENTRY_NOT_PROJECTED",
            standard_evidence_emitted=False,
            evidence_class="UNRESOLVED",
            sizing_status="no_call",
            failure_code="TARGET_ENTRY_NOT_PROJECTED",
            repeat_bp_lower_bound=None,
            notes=(
                "A plus-orientation bridge was not sufficient to "
                "project the target-entry query coordinate through "
                "a validated CIGAR."
            ),
            **common,
        )

    if len(motif) == 1:
        return P3Decision(
            primary_status=(
                "HOMOPOLYMER_REVIEW_NO_STANDARD_P3_EVIDENCE"
            ),
            standard_evidence_emitted=False,
            evidence_class="UNRESOLVED",
            sizing_status="no_call",
            failure_code="HOMOPOLYMER_REVIEW",
            repeat_bp_lower_bound=None,
            notes=(
                "Mononucleotide A/T-like signal is routed to "
                "dedicated homopolymer or poly(A)/poly(T) review."
            ),
            **common,
        )

    if observation.tract_bp is None or observation.tract_bp == 0:
        return P3Decision(
            primary_status=(
                "ORIENTATION_VALID_BRIDGE_ONLY_NO_REPEAT_TRACT"
            ),
            standard_evidence_emitted=False,
            evidence_class="UNRESOLVED",
            sizing_status="no_call",
            failure_code="REPEAT_NOT_FOUND",
            repeat_bp_lower_bound=None,
            notes=(
                "The bridge and target entry are supported, but no "
                "qualifying target-entry repeat tract was measured."
            ),
            **common,
        )

    if observation.tract_reaches_expected_raw_end:
        if observation.target_facing_genomic_side == "GENOMIC_RIGHT":
            evidence_class = "LEFT_ANCHORED_CENSORED_RIGHT"
        else:
            evidence_class = "RIGHT_ANCHORED_CENSORED_LEFT"

        return P3Decision(
            primary_status="P3_CENSORED_LOWER_BOUND",
            standard_evidence_emitted=True,
            evidence_class=evidence_class,
            sizing_status="lower_bound",
            failure_code="NONE",
            repeat_bp_lower_bound=float(observation.tract_bp),
            notes=(
                "One validated genomic flank and a target-entry "
                "repeat tract reaching the expected raw-read end "
                "support a censored lower bound only."
            ),
            **common,
        )

    if observation.target_facing_genomic_side == "GENOMIC_RIGHT":
        evidence_class = "LEFT_ONLY_INTERNAL"
    else:
        evidence_class = "RIGHT_ONLY_INTERNAL"

    return P3Decision(
        primary_status="P3_PARTIAL_INTERNAL",
        standard_evidence_emitted=True,
        evidence_class=evidence_class,
        sizing_status="partial_internal",
        failure_code="NONE",
        repeat_bp_lower_bound=None,
        notes=(
            "One validated genomic flank and an internal "
            "target-entry repeat tract support partial_internal; "
            "neither exact size nor lower bound is emitted."
        ),
        **common,
    )
PY

cat > "$STAGE_SRC/contract.py" <<'PY'
"""Schema and regression-fixture contract checks."""

from __future__ import annotations

import csv
import json
from pathlib import Path

EXPECTED_FAILURE_CODES = {
    "ORIENTATION_INCONSISTENT_BRIDGE",
    "TARGET_ENTRY_NOT_PROJECTED",
    "HOMOPOLYMER_REVIEW",
}
EXPECTED_CASE_IDS = {"RC019", "RC020"}
EXPECTED_RULE_IDS = {"R014", "R015", "R016"}


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def check_contract(
    schema_dir: str | Path,
    fixture_dir: str | Path,
) -> dict[str, object]:
    schema_dir = Path(schema_dir)
    fixture_dir = Path(fixture_dir)

    version = (
        schema_dir / "SCHEMA_VERSION"
    ).read_text(encoding="utf-8").strip()

    enum_rows = _read_tsv(
        schema_dir
        / "dictionaries"
        / "rnatr_v03_enums.tsv"
    )
    tsv_failure_codes = {
        row["allowed_value"]
        for row in enum_rows
        if row["enum_name"] == "failure_code"
    }

    schema_json = json.loads(
        (
            schema_dir
            / "schema"
            / "rnatr_v03_table_schema.json"
        ).read_text(encoding="utf-8")
    )
    json_failure_codes = set(
        schema_json["enums"]["failure_code"]
    )

    cases = _read_tsv(
        fixture_dir / "regression_cases.tsv"
    )
    rules = _read_tsv(
        fixture_dir / "decision_rules.tsv"
    )

    case_ids = {row["case_id"] for row in cases}
    rule_ids = {row["rule_id"] for row in rules}

    failures: list[str] = []

    if version != "0.3.2":
        failures.append(
            f"unexpected schema version: {version}"
        )

    if not EXPECTED_FAILURE_CODES <= tsv_failure_codes:
        failures.append(
            "P3 failure codes missing from TSV enums"
        )

    if tsv_failure_codes != json_failure_codes:
        failures.append(
            "JSON and TSV failure-code enums differ"
        )

    if not EXPECTED_CASE_IDS <= case_ids:
        failures.append(
            "P3 regression cases RC019/RC020 missing"
        )

    if not EXPECTED_RULE_IDS <= rule_ids:
        failures.append(
            "P3 decision rules R014-R016 missing"
        )

    return {
        "status": "PASS" if not failures else "FAIL",
        "schema_version": version,
        "regression_cases": len(cases),
        "decision_rules": len(rules),
        "p3_failure_codes_present": len(
            EXPECTED_FAILURE_CODES & tsv_failure_codes
        ),
        "p3_case_ids_present": len(
            EXPECTED_CASE_IDS & case_ids
        ),
        "p3_rule_ids_present": len(
            EXPECTED_RULE_IDS & rule_ids
        ),
        "failures": failures,
    }
PY

cat > "$STAGE_SRC/cli.py" <<'PY'
"""Command-line interface for RNA-TR-Scout."""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
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

cat > "$STAGE_TESTS/__init__.py" <<'PY'
"""Unit tests for RNA-TR-Scout."""
PY

cat > "$STAGE_TESTS/test_p3.py" <<'PY'
from __future__ import annotations

import unittest

from rnatr_scout.p3 import (
    P3Observation,
    classify_p3,
)


def observation(**updates):
    values = {
        "alignment_strand": "+",
        "target_entry_projected": True,
        "canonical_motif": "CAG",
        "target_facing_genomic_side": "GENOMIC_RIGHT",
        "tract_bp": 30,
        "tract_reaches_expected_raw_end": False,
    }
    values.update(updates)
    return P3Observation(**values)


class TestP3Rules(unittest.TestCase):
    def test_orientation_has_highest_priority(self):
        decision = classify_p3(
            observation(
                alignment_strand="-",
                canonical_motif="A",
            )
        )
        self.assertEqual(
            decision.failure_code,
            "ORIENTATION_INCONSISTENT_BRIDGE",
        )
        self.assertFalse(
            decision.standard_evidence_emitted
        )

    def test_target_entry_projection_required(self):
        decision = classify_p3(
            observation(
                target_entry_projected=False
            )
        )
        self.assertEqual(
            decision.failure_code,
            "TARGET_ENTRY_NOT_PROJECTED",
        )

    def test_homopolymer_is_review_only(self):
        decision = classify_p3(
            observation(canonical_motif="A")
        )
        self.assertEqual(
            decision.failure_code,
            "HOMOPOLYMER_REVIEW",
        )
        self.assertEqual(
            decision.sizing_status,
            "no_call",
        )

    def test_bridge_only_is_no_call(self):
        decision = classify_p3(
            observation(tract_bp=None)
        )
        self.assertEqual(
            decision.failure_code,
            "REPEAT_NOT_FOUND",
        )
        self.assertFalse(
            decision.standard_evidence_emitted
        )

    def test_genomic_right_internal(self):
        decision = classify_p3(observation())
        self.assertEqual(
            decision.evidence_class,
            "LEFT_ONLY_INTERNAL",
        )
        self.assertEqual(
            decision.sizing_status,
            "partial_internal",
        )
        self.assertIsNone(
            decision.repeat_bp_lower_bound
        )

    def test_genomic_left_internal(self):
        decision = classify_p3(
            observation(
                target_facing_genomic_side=(
                    "GENOMIC_LEFT"
                )
            )
        )
        self.assertEqual(
            decision.evidence_class,
            "RIGHT_ONLY_INTERNAL",
        )

    def test_genomic_right_censored(self):
        decision = classify_p3(
            observation(
                tract_reaches_expected_raw_end=True
            )
        )
        self.assertEqual(
            decision.evidence_class,
            "LEFT_ANCHORED_CENSORED_RIGHT",
        )
        self.assertEqual(
            decision.repeat_bp_lower_bound,
            30.0,
        )

    def test_genomic_left_censored(self):
        decision = classify_p3(
            observation(
                target_facing_genomic_side=(
                    "GENOMIC_LEFT"
                ),
                tract_reaches_expected_raw_end=True,
            )
        )
        self.assertEqual(
            decision.evidence_class,
            "RIGHT_ANCHORED_CENSORED_LEFT",
        )

    def test_exact_and_expansion_are_never_emitted(self):
        decision = classify_p3(
            observation(
                tract_reaches_expected_raw_end=True
            )
        )
        self.assertIsNone(
            decision.repeat_bp_estimate
        )
        self.assertEqual(
            decision.expansion_status,
            "NOT_ASSESSED",
        )

    def test_invalid_motif_rejected(self):
        with self.assertRaises(ValueError):
            classify_p3(
                observation(canonical_motif="CAN")
            )


if __name__ == "__main__":
    unittest.main()
PY

cat > "$STAGE_TESTS/test_contract.py" <<'PY'
from __future__ import annotations

import os
import unittest
from pathlib import Path

from rnatr_scout.contract import check_contract


class TestContract(unittest.TestCase):
    def test_v032_contract(self):
        project_root = Path(
            os.environ["RNATR_PROJECT_ROOT"]
        )
        result = check_contract(
            project_root
            / "config"
            / "evidence_schema"
            / "v0.3.2",
            project_root
            / "tests"
            / "regression"
            / "v0.3.2",
        )
        self.assertEqual(
            result["status"],
            "PASS",
            result["failures"],
        )
        self.assertEqual(
            result["regression_cases"],
            20,
        )
        self.assertEqual(
            result["decision_rules"],
            16,
        )


if __name__ == "__main__":
    unittest.main()
PY

echo "===== STAGED PYTHON SYNTAX ====="
python -m compileall -q "$STAGE/src" "$STAGE/tests"
echo "Python compileall: PASS"

echo
echo "===== STAGED UNIT TESTS ====="
RNATR_PROJECT_ROOT="$PROJECT_ROOT" \
PYTHONPATH="$STAGE/src" \
python -m unittest discover \
  -s "$STAGE/tests/unit" \
  -v \
  2>&1 | tee "$UNIT_LOG"

echo
echo "===== STAGED CLI SMOKE TESTS ====="
{
    PYTHONPATH="$STAGE/src" \
      python -m rnatr_scout.cli version

    PYTHONPATH="$STAGE/src" \
      python -m rnatr_scout.cli contract-check \
      --schema-dir "$SCHEMA_DIR" \
      --fixture-dir "$FIXTURE_DIR"

    PYTHONPATH="$STAGE/src" \
      python -m rnatr_scout.cli p3-classify \
      --alignment-strand - \
      --target-entry-projected true \
      --motif CAG \
      --target-side GENOMIC_RIGHT \
      --tract-bp 30

    PYTHONPATH="$STAGE/src" \
      python -m rnatr_scout.cli p3-classify \
      --alignment-strand + \
      --target-entry-projected true \
      --motif A \
      --target-side GENOMIC_RIGHT \
      --tract-bp 30

    PYTHONPATH="$STAGE/src" \
      python -m rnatr_scout.cli p3-classify \
      --alignment-strand + \
      --target-entry-projected true \
      --motif CAG \
      --target-side GENOMIC_RIGHT \
      --tract-bp 45 \
      --tract-reaches-raw-end true
} 2>&1 | tee "$SMOKE_LOG"

echo
echo "===== INSTALL PRODUCTION PACKAGE ====="
mkdir -p "$PROJECT_ROOT/src" "$PROJECT_ROOT/tests"

cp "$STAGE/pyproject.toml" "$FINAL_PYPROJECT"
cp -a "$STAGE_SRC" "$FINAL_PACKAGE"
cp -a "$STAGE_TESTS" "$FINAL_TESTS"

python -m pip install \
  --no-deps \
  --no-build-isolation \
  -e "$PROJECT_ROOT"

echo
echo "===== INSTALLED CLI CHECK ====="
installed_version="$(
    rnatr-scout version
)"

contract_json="$(
    rnatr-scout contract-check \
      --schema-dir "$SCHEMA_DIR" \
      --fixture-dir "$FIXTURE_DIR"
)"

orientation_json="$(
    rnatr-scout p3-classify \
      --alignment-strand - \
      --target-entry-projected true \
      --motif CAG \
      --target-side GENOMIC_RIGHT \
      --tract-bp 30
)"

homopolymer_json="$(
    rnatr-scout p3-classify \
      --alignment-strand + \
      --target-entry-projected true \
      --motif A \
      --target-side GENOMIC_RIGHT \
      --tract-bp 30
)"

censored_json="$(
    rnatr-scout p3-classify \
      --alignment-strand + \
      --target-entry-projected true \
      --motif CAG \
      --target-side GENOMIC_RIGHT \
      --tract-bp 45 \
      --tract-reaches-raw-end true
)"

python - \
  "$installed_version" \
  "$contract_json" \
  "$orientation_json" \
  "$homopolymer_json" \
  "$censored_json" \
  "$QC" <<'PYQC'
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

(
    version,
    contract_text,
    orientation_text,
    homopolymer_text,
    censored_text,
    qc_path,
) = sys.argv[1:]

contract = json.loads(contract_text)
orientation = json.loads(orientation_text)
homopolymer = json.loads(homopolymer_text)
censored = json.loads(censored_text)

checks = {
    "installed_version_matches": (
        version == "0.3.2"
    ),
    "contract_check_pass": (
        contract["status"] == "PASS"
    ),
    "orientation_guardrail_pass": (
        orientation["failure_code"]
        == "ORIENTATION_INCONSISTENT_BRIDGE"
        and not orientation[
            "standard_evidence_emitted"
        ]
    ),
    "homopolymer_guardrail_pass": (
        homopolymer["failure_code"]
        == "HOMOPOLYMER_REVIEW"
        and not homopolymer[
            "standard_evidence_emitted"
        ]
    ),
    "censored_guardrail_pass": (
        censored["evidence_class"]
        == "LEFT_ANCHORED_CENSORED_RIGHT"
        and censored["sizing_status"]
        == "lower_bound"
        and censored["repeat_bp_estimate"]
        is None
        and censored["repeat_bp_lower_bound"]
        == 45.0
        and censored["expansion_status"]
        == "NOT_ASSESSED"
    ),
}

status = (
    "PASS"
    if all(checks.values())
    else "REVIEW"
)

rows = [
    ("package_version", version),
    ("package_python_files", 5),
    ("unit_test_modules", 2),
    ("unit_tests_expected", 11),
    (
        "contract_check_status",
        contract["status"],
    ),
]

for name, passed in checks.items():
    rows.append(
        (
            name,
            str(passed).lower(),
        )
    )

rows.append(("package_status", status))

path = Path(qc_path)
path.parent.mkdir(
    parents=True,
    exist_ok=True,
)

with path.open(
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.writer(
        handle,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writerow(["metric", "value"])
    writer.writerows(rows)

if status != "PASS":
    raise SystemExit(
        "Production package smoke checks require review"
    )
PYQC

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in \
      "$FINAL_PYPROJECT" \
      "$FINAL_PACKAGE/__init__.py" \
      "$FINAL_PACKAGE/__main__.py" \
      "$FINAL_PACKAGE/p3.py" \
      "$FINAL_PACKAGE/contract.py" \
      "$FINAL_PACKAGE/cli.py" \
      "$FINAL_TESTS/test_p3.py" \
      "$FINAL_TESTS/test_contract.py" \
      "$UNIT_LOG" \
      "$SMOKE_LOG" \
      "$QC"
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
echo "===== INSTALLED VERSION ====="
rnatr-scout version

echo
echo "===== INSTALLED CONTRACT CHECK ====="
rnatr-scout contract-check \
  --schema-dir "$SCHEMA_DIR" \
  --fixture-dir "$FIXTURE_DIR"

echo
echo "===== MANIFEST ====="
column -ts $'\t' "$MANIFEST"
