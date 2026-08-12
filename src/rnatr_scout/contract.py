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
