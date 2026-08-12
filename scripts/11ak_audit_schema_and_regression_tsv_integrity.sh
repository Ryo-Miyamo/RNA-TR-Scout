#!/usr/bin/env bash
set -euo pipefail

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
fi

conda activate rnatr-v03
source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"

SCHEMA_DIR="$PROJECT_ROOT/config/evidence_schema/v0.3.1"
REGRESSION_DIR="$PROJECT_ROOT/tests/regression/v0.3.1"

OUTDIR="$PROJECT_ROOT/results/11_contract_integrity_audit/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_contract_integrity_audit/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_contract_integrity_audit/$RUN_ID"

DETAILS="$OUTDIR/schema_template_integrity.tsv"
REGRESSION_DETAILS="$OUTDIR/regression_tsv_integrity.tsv"
EXTRA_FILES="$OUTDIR/schema_recursive_only_files.tsv"
SUMMARY="$OUTDIR/contract_integrity_summary.tsv"
QC="$QCDIR/contract_integrity_audit.qc.tsv"
MANIFEST="$OUTDIR/${RUN_ID}.contract_integrity_audit.manifest.tsv"
PY="$WORKDIR/audit_contract_integrity.py"

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR"

for path in \
  "$SCHEMA_DIR" \
  "$REGRESSION_DIR"
do
    test -e "$path" || {
        echo "ERROR: missing required path: $path" >&2
        exit 1
    }
done

cat > "$PY" <<'PY'
from __future__ import annotations

import csv
import gzip
import json
import sys
from collections import Counter
from pathlib import Path

(
    schema_dir_text,
    regression_dir_text,
    details_path_text,
    regression_details_path_text,
    extra_files_path_text,
    summary_path_text,
    qc_path_text,
) = sys.argv[1:]

SCHEMA_DIR = Path(schema_dir_text)
REGRESSION_DIR = Path(regression_dir_text)
DETAILS = Path(details_path_text)
REGRESSION_DETAILS = Path(
    regression_details_path_text
)
EXTRA_FILES = Path(extra_files_path_text)
SUMMARY = Path(summary_path_text)
QC = Path(qc_path_text)


def read_tsv_rows(path: Path):
    with path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        return list(
            csv.reader(
                handle,
                delimiter="\t",
            )
        )


def read_gzip_tsv_rows(path: Path):
    with gzip.open(
        path,
        "rt",
        encoding="utf-8",
        newline="",
    ) as handle:
        return list(
            csv.reader(
                handle,
                delimiter="\t",
            )
        )


def dictionary_columns(path: Path):
    rows = read_tsv_rows(path)

    if not rows:
        return []

    header = rows[0]
    name_index = header.index("column_name")
    order_index = header.index("column_order")

    parsed = []

    for row in rows[1:]:
        if not row:
            continue

        parsed.append(
            (
                int(row[order_index]),
                row[name_index],
            )
        )

    parsed.sort()
    return [name for _, name in parsed]


schema_json_path = (
    SCHEMA_DIR
    / "schema"
    / "rnatr_v03_table_schema.json"
)
schema_object = json.loads(
    schema_json_path.read_text(
        encoding="utf-8"
    )
)

tables = schema_object["tables"]

detail_rows = []
template_mismatch_count = 0
dictionary_mismatch_count = 0
template_missing_count = 0
dictionary_missing_count = 0

for table_name, table_spec in sorted(
    tables.items()
):
    json_columns = [
        column["name"]
        for column in table_spec["columns"]
    ]

    dictionary_path = (
        SCHEMA_DIR
        / "dictionaries"
        / "{}.columns.tsv".format(
            table_name
        )
    )
    template_path = (
        SCHEMA_DIR
        / "templates"
        / "{}.tsv".format(
            table_name
        )
    )

    dictionary_exists = (
        dictionary_path.is_file()
    )
    template_exists = template_path.is_file()

    if dictionary_exists:
        dictionary_names = dictionary_columns(
            dictionary_path
        )
    else:
        dictionary_names = []
        dictionary_missing_count += 1

    if template_exists:
        template_rows = read_tsv_rows(
            template_path
        )
        template_names = (
            template_rows[0]
            if template_rows
            else []
        )
    else:
        template_names = []
        template_missing_count += 1

    dictionary_matches = (
        dictionary_names == json_columns
    )
    template_matches = (
        template_names == json_columns
    )

    if not dictionary_matches:
        dictionary_mismatch_count += 1

    if not template_matches:
        template_mismatch_count += 1

    maximum_length = max(
        len(json_columns),
        len(dictionary_names),
        len(template_names),
    )

    for index in range(maximum_length):
        json_name = (
            json_columns[index]
            if index < len(json_columns)
            else "."
        )
        dictionary_name = (
            dictionary_names[index]
            if index < len(dictionary_names)
            else "."
        )
        template_name = (
            template_names[index]
            if index < len(template_names)
            else "."
        )

        if (
            json_name == dictionary_name
            and json_name == template_name
        ):
            row_status = "MATCH"
        else:
            row_status = "MISMATCH"

        detail_rows.append(
            {
                "table_name": table_name,
                "column_position_1based": (
                    index + 1
                ),
                "json_schema_column": json_name,
                "dictionary_column": (
                    dictionary_name
                ),
                "template_column": template_name,
                "row_status": row_status,
            }
        )

with DETAILS.open(
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    fields = [
        "table_name",
        "column_position_1based",
        "json_schema_column",
        "dictionary_column",
        "template_column",
        "row_status",
    ]
    writer = csv.DictWriter(
        handle,
        fieldnames=fields,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(detail_rows)

shallow_files = {
    path.resolve()
    for path in SCHEMA_DIR.glob("*")
    if path.is_file()
}

for directory in SCHEMA_DIR.glob("*"):
    if not directory.is_dir():
        continue

    for path in directory.glob("*"):
        if path.is_file():
            shallow_files.add(path.resolve())

recursive_files = {
    path.resolve()
    for path in SCHEMA_DIR.rglob("*")
    if path.is_file()
}

recursive_only = sorted(
    recursive_files - shallow_files
)

with EXTRA_FILES.open(
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.writer(
        handle,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writerow(
        [
            "relative_path",
            "bytes",
        ]
    )

    for path in recursive_only:
        writer.writerow(
            [
                str(
                    path.relative_to(
                        SCHEMA_DIR.resolve()
                    )
                ),
                path.stat().st_size,
            ]
        )

expected_regression_header = [
    "fixture_version",
    "case_id",
    "category",
    "source_artifact",
    "source_key",
    "read_id",
    "target_region_id",
    "representative_locus_id",
    "canonical_motif",
    "raw_interval_start",
    "raw_interval_end",
    "observed_bp",
    "source_evidence_class",
    "source_sizing_status",
    "expected_primary_class",
    "expected_sizing_status",
    "expected_guardrail",
    "rationale",
]

regression_path = (
    REGRESSION_DIR
    / "regression_cases.tsv"
)
decision_rules_path = (
    REGRESSION_DIR
    / "decision_rules.tsv"
)
manifest_path = (
    REGRESSION_DIR
    / "regression_fixture.manifest.tsv"
)

regression_rows = read_tsv_rows(
    regression_path
)
decision_rows = read_tsv_rows(
    decision_rules_path
)
manifest_rows = read_tsv_rows(
    manifest_path
)

regression_header = (
    regression_rows[0]
    if regression_rows
    else []
)
regression_data_rows = (
    regression_rows[1:]
    if regression_rows
    else []
)

regression_detail_rows = []
regression_width_counts = Counter()

for line_number, row in enumerate(
    regression_data_rows,
    start=2,
):
    width = len(row)
    regression_width_counts[width] += 1

    case_id = (
        row[1]
        if len(row) > 1
        else "."
    )

    regression_detail_rows.append(
        {
            "line_number": line_number,
            "case_id": case_id,
            "observed_field_count": width,
            "expected_field_count": len(
                expected_regression_header
            ),
            "row_status": (
                "PASS"
                if width
                   == len(
                       expected_regression_header
                   )
                else "FAIL"
            ),
        }
    )

with REGRESSION_DETAILS.open(
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    fields = [
        "line_number",
        "case_id",
        "observed_field_count",
        "expected_field_count",
        "row_status",
    ]
    writer = csv.DictWriter(
        handle,
        fieldnames=fields,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(
        regression_detail_rows
    )

regression_header_matches = (
    regression_header
    == expected_regression_header
)
regression_bad_width_rows = sum(
    row["row_status"] == "FAIL"
    for row in regression_detail_rows
)

decision_header_expected = [
    "rule_id",
    "rule_name",
    "condition",
    "required_action",
    "guardrail",
]
decision_header_matches = (
    bool(decision_rows)
    and decision_rows[0]
        == decision_header_expected
)
decision_bad_width_rows = sum(
    len(row)
    != len(decision_header_expected)
    for row in decision_rows[1:]
)

manifest_header_expected = [
    "artifact",
    "data_rows",
    "bytes",
    "sha256",
    "path",
]
manifest_header_matches = (
    bool(manifest_rows)
    and manifest_rows[0]
        == manifest_header_expected
)
manifest_bad_width_rows = sum(
    len(row)
    != len(manifest_header_expected)
    for row in manifest_rows[1:]
)

summary_rows = [
    (
        "schema_files_shallow_depth_2",
        len(shallow_files),
    ),
    (
        "schema_files_recursive",
        len(recursive_files),
    ),
    (
        "schema_recursive_only_files",
        len(recursive_only),
    ),
    (
        "schema_tables",
        len(tables),
    ),
    (
        "dictionary_missing_tables",
        dictionary_missing_count,
    ),
    (
        "template_missing_tables",
        template_missing_count,
    ),
    (
        "dictionary_mismatch_tables",
        dictionary_mismatch_count,
    ),
    (
        "template_mismatch_tables",
        template_mismatch_count,
    ),
    (
        "regression_header_fields",
        len(regression_header),
    ),
    (
        "regression_expected_header_fields",
        len(expected_regression_header),
    ),
    (
        "regression_header_matches",
        str(
            regression_header_matches
        ).lower(),
    ),
    (
        "regression_data_rows",
        len(regression_data_rows),
    ),
    (
        "regression_bad_width_rows",
        regression_bad_width_rows,
    ),
    (
        "decision_rules_header_matches",
        str(
            decision_header_matches
        ).lower(),
    ),
    (
        "decision_rules_bad_width_rows",
        decision_bad_width_rows,
    ),
    (
        "manifest_header_matches",
        str(
            manifest_header_matches
        ).lower(),
    ),
    (
        "manifest_bad_width_rows",
        manifest_bad_width_rows,
    ),
]

for width, count in sorted(
    regression_width_counts.items()
):
    summary_rows.append(
        (
            "regression_rows_with_{}_fields".format(
                width
            ),
            count,
        )
    )

with SUMMARY.open(
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.writer(
        handle,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writerow(
        [
            "metric",
            "value",
        ]
    )
    writer.writerows(summary_rows)

status = "PASS"

if (
    dictionary_missing_count
    or template_missing_count
    or dictionary_mismatch_count
    or template_mismatch_count
    or not regression_header_matches
    or regression_bad_width_rows
    or not decision_header_matches
    or decision_bad_width_rows
    or not manifest_header_matches
    or manifest_bad_width_rows
):
    status = "REVIEW"

with QC.open(
    "w",
    encoding="utf-8",
) as handle:
    handle.write("metric\tvalue\n")

    for metric, value in summary_rows:
        handle.write(
            "{}\t{}\n".format(
                metric,
                value,
            )
        )

    handle.write(
        "integrity_status\t{}\n".format(
            status
        )
    )
PY

python -m py_compile "$PY"

rm -f \
  "$DETAILS" \
  "$REGRESSION_DETAILS" \
  "$EXTRA_FILES" \
  "$SUMMARY" \
  "$QC" \
  "$MANIFEST"

python "$PY" \
  "$SCHEMA_DIR" \
  "$REGRESSION_DIR" \
  "$DETAILS" \
  "$REGRESSION_DETAILS" \
  "$EXTRA_FILES" \
  "$SUMMARY" \
  "$QC"

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in \
      "$DETAILS" \
      "$REGRESSION_DETAILS" \
      "$EXTRA_FILES" \
      "$SUMMARY" \
      "$QC"
    do
        printf '%s\t%s\t%s\t%s\t%s\n' \
          "$(basename "$path")" \
          "$(awk 'END {print NR-1}' "$path")" \
          "$(stat -c '%s' "$path")" \
          "$(sha256sum "$path" | awk '{print $1}')" \
          "$path"
    done
} > "$MANIFEST"

echo "===== QC ====="
column -ts $'\t' "$QC"

echo
echo "===== SCHEMA RECURSIVE-ONLY FILES ====="
column -ts $'\t' "$EXTRA_FILES"

echo
echo "===== SCHEMA/TEMPLATE MISMATCHES ====="
awk -F '\t' '
    NR == 1 || $6 == "MISMATCH"
' "$DETAILS" \
  | column -ts $'\t'

echo
echo "===== REGRESSION ROW WIDTH FAILURES ====="
awk -F '\t' '
    NR == 1 || $5 == "FAIL"
' "$REGRESSION_DETAILS" \
  | column -ts $'\t'

echo
echo "===== SUMMARY ====="
column -ts $'\t' "$SUMMARY"

echo
echo "===== MANIFEST ====="
column -ts $'\t' "$MANIFEST"
