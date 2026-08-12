#!/usr/bin/env bash
set -euo pipefail

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
fi

conda activate rnatr-v03
source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"

SCHEMA="$PROJECT_ROOT/config/evidence_schema/v0.3.2"
FIXTURE="$PROJECT_ROOT/tests/regression/v0.3.2"
BUILD_SCRIPT="$PROJECT_ROOT/scripts/11al_create_schema_and_regression_v0.3.2.sh"

OUTDIR="$PROJECT_ROOT/results/11_schema_regression_v032_postcheck/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_schema_regression_v032_postcheck/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_schema_regression_v032_postcheck/$RUN_ID"

QC="$QCDIR/schema_regression_v0.3.2.postcheck.qc.tsv"
SUMMARY="$OUTDIR/schema_regression_v0.3.2.postcheck.summary.tsv"
MANIFEST="$OUTDIR/${RUN_ID}.schema_regression_v0.3.2.postcheck.manifest.tsv"
PY="$WORKDIR/postcheck_schema_regression_v032.py"

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR"

for path in \
  "$SCHEMA" \
  "$FIXTURE" \
  "$BUILD_SCRIPT"
do
    test -e "$path" || {
        echo "ERROR: missing required path: $path" >&2
        exit 1
    }
done

echo "===== PATCH DISPLAY-ONLY AWK BLOCK ====="

python - "$BUILD_SCRIPT" <<'PYFIX'
from pathlib import Path
import shutil
import sys
from datetime import datetime

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

old = r'''awk -F '\t' '
  NR == 1 ||
  (
    $1 == "failure_code" &&
    (
      $2 == "ORIENTATION_INCONSISTENT_BRIDGE" ||
      $2 == "TARGET_ENTRY_NOT_PROJECTED" ||
      $2 == "HOMOPOLYMER_REVIEW"
    )
  )
' \
  "$NEW_SCHEMA/dictionaries/rnatr_v03_enums.tsv" \
  | column -ts $'\t'
'''

new = r'''awk -F '\t' '
  NR == 1 {
    print
    next
  }
  $1 == "failure_code" &&
  (
    $2 == "ORIENTATION_INCONSISTENT_BRIDGE" ||
    $2 == "TARGET_ENTRY_NOT_PROJECTED" ||
    $2 == "HOMOPOLYMER_REVIEW"
  ) {
    print
  }
' \
  "$NEW_SCHEMA/dictionaries/rnatr_v03_enums.tsv" \
  | column -ts $'\t'
'''

if old in text:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(
        path.name + ".before_awk_display_fix." + timestamp
    )
    shutil.copy2(path, backup)
    path.write_text(
        text.replace(old, new, 1),
        encoding="utf-8",
    )
    print(f"PATCHED\t{path}")
    print(f"BACKUP\t{backup}")
elif new in text:
    print(f"ALREADY_PATCHED\t{path}")
else:
    raise SystemExit(
        "Expected AWK block was not found; script left unchanged."
    )
PYFIX

bash -n "$BUILD_SCRIPT"
echo "Build script shell syntax after patch: PASS"

cat > "$PY" <<'PY'
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import sys
from pathlib import Path

(
    schema_text,
    fixture_text,
    qc_text,
    summary_text,
) = sys.argv[1:]

SCHEMA = Path(schema_text)
FIXTURE = Path(fixture_text)
QC = Path(qc_text)
SUMMARY = Path(summary_text)

EXPECTED_CODES = {
    "ORIENTATION_INCONSISTENT_BRIDGE",
    "TARGET_ENTRY_NOT_PROJECTED",
    "HOMOPOLYMER_REVIEW",
}

EXPECTED_CASE_IDS = {"RC019", "RC020"}
EXPECTED_RULE_IDS = {"R014", "R015", "R016"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)

            if not block:
                break

            digest.update(block)

    return digest.hexdigest()


def read_tsv(path: Path):
    with path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        return list(
            csv.DictReader(handle, delimiter="\t")
        )


def raw_widths(path: Path):
    with path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        rows = list(
            csv.reader(handle, delimiter="\t")
        )

    if not rows:
        return 0, []

    width = len(rows[0])
    failures = [
        index
        for index, row in enumerate(rows, start=1)
        if len(row) != width
    ]
    return width, failures


schema_version = (
    SCHEMA / "SCHEMA_VERSION"
).read_text(encoding="utf-8").strip()

enum_path = (
    SCHEMA
    / "dictionaries"
    / "rnatr_v03_enums.tsv"
)
enum_rows = read_tsv(enum_path)

tsv_failure_codes = {
    row["allowed_value"]
    for row in enum_rows
    if row["enum_name"] == "failure_code"
}

code_counts = {
    code: sum(
        row["enum_name"] == "failure_code"
        and row["allowed_value"] == code
        for row in enum_rows
    )
    for code in EXPECTED_CODES
}

schema_json_path = (
    SCHEMA
    / "schema"
    / "rnatr_v03_table_schema.json"
)
schema_json = json.loads(
    schema_json_path.read_text(encoding="utf-8")
)
json_failure_codes = set(
    schema_json["enums"]["failure_code"]
)

dictionary_mismatches = 0
template_mismatches = 0

for table_name, table_spec in schema_json[
    "tables"
].items():
    expected_columns = [
        column["name"]
        for column in table_spec["columns"]
    ]

    dictionary_rows = read_tsv(
        SCHEMA
        / "dictionaries"
        / f"{table_name}.columns.tsv"
    )
    dictionary_rows.sort(
        key=lambda row: int(row["column_order"])
    )
    dictionary_columns = [
        row["column_name"]
        for row in dictionary_rows
    ]

    with (
        SCHEMA
        / "templates"
        / f"{table_name}.tsv"
    ).open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        template_columns = next(
            csv.reader(handle, delimiter="\t")
        )

    if dictionary_columns != expected_columns:
        dictionary_mismatches += 1

    if template_columns != expected_columns:
        template_mismatches += 1

schema_manifest_path = (
    SCHEMA / "MANIFEST.sha256"
)
schema_manifest_failures = 0
schema_manifest_entries = {}

with schema_manifest_path.open(
    "r",
    encoding="utf-8",
) as handle:
    for line in handle:
        line = line.rstrip("\n")

        if not line:
            continue

        digest, relative = line.split("  ", 1)
        schema_manifest_entries[relative] = digest

for relative, expected_digest in (
    schema_manifest_entries.items()
):
    path = SCHEMA / relative

    if (
        not path.is_file()
        or sha256(path) != expected_digest
    ):
        schema_manifest_failures += 1

actual_schema_files = {
    str(path.relative_to(SCHEMA))
    for path in SCHEMA.rglob("*")
    if path.is_file()
    and path.name != "MANIFEST.sha256"
}
manifest_schema_files = set(
    schema_manifest_entries
)
schema_manifest_missing_files = len(
    actual_schema_files - manifest_schema_files
)
schema_manifest_extra_files = len(
    manifest_schema_files - actual_schema_files
)

cases_path = FIXTURE / "regression_cases.tsv"
rules_path = FIXTURE / "decision_rules.tsv"
fastq_path = (
    FIXTURE / "data" / "regression_reads.fastq.gz"
)
fixture_manifest_path = (
    FIXTURE / "regression_fixture.manifest.tsv"
)

case_rows = read_tsv(cases_path)
rule_rows = read_tsv(rules_path)

case_header_width, case_width_failures = (
    raw_widths(cases_path)
)
rule_header_width, rule_width_failures = (
    raw_widths(rules_path)
)

case_ids = [row["case_id"] for row in case_rows]
rule_ids = [row["rule_id"] for row in rule_rows]

case_versions = {
    row["fixture_version"]
    for row in case_rows
}
case_read_ids = {
    row["read_id"]
    for row in case_rows
}

fastq_read_ids = []

with gzip.open(
    fastq_path,
    "rt",
    encoding="utf-8",
) as handle:
    line_number = 0

    for line in handle:
        line_number += 1

        if line_number % 4 == 1:
            fastq_read_ids.append(
                line[1:].split()[0]
            )

fastq_read_id_set = set(fastq_read_ids)
missing_case_reads = (
    case_read_ids - fastq_read_id_set
)

fixture_manifest_rows = read_tsv(
    fixture_manifest_path
)
fixture_manifest_failures = 0

for row in fixture_manifest_rows:
    path = Path(row["path"])

    if not path.is_file():
        fixture_manifest_failures += 1
        continue

    if int(row["bytes"]) != path.stat().st_size:
        fixture_manifest_failures += 1
        continue

    if row["sha256"] != sha256(path):
        fixture_manifest_failures += 1

metrics = [
    ("schema_version", schema_version),
    (
        "new_failure_codes_present",
        len(EXPECTED_CODES & tsv_failure_codes),
    ),
    (
        "new_failure_code_duplicate_rows",
        sum(
            max(0, count - 1)
            for count in code_counts.values()
        ),
    ),
    (
        "json_tsv_failure_enums_match",
        str(
            json_failure_codes
            == tsv_failure_codes
        ).lower(),
    ),
    (
        "dictionary_mismatch_tables",
        dictionary_mismatches,
    ),
    (
        "template_mismatch_tables",
        template_mismatches,
    ),
    (
        "schema_manifest_entries",
        len(schema_manifest_entries),
    ),
    (
        "schema_manifest_hash_failures",
        schema_manifest_failures,
    ),
    (
        "schema_manifest_missing_files",
        schema_manifest_missing_files,
    ),
    (
        "schema_manifest_extra_files",
        schema_manifest_extra_files,
    ),
    ("regression_cases", len(case_rows)),
    ("unique_case_ids", len(set(case_ids))),
    (
        "regression_case_versions",
        ";".join(sorted(case_versions)),
    ),
    (
        "new_p3_case_ids_present",
        len(EXPECTED_CASE_IDS & set(case_ids)),
    ),
    (
        "case_header_fields",
        case_header_width,
    ),
    (
        "case_width_failures",
        len(case_width_failures),
    ),
    ("decision_rules", len(rule_rows)),
    ("unique_rule_ids", len(set(rule_ids))),
    (
        "new_p3_rule_ids_present",
        len(EXPECTED_RULE_IDS & set(rule_ids)),
    ),
    (
        "rule_header_fields",
        rule_header_width,
    ),
    (
        "rule_width_failures",
        len(rule_width_failures),
    ),
    (
        "unique_fastq_reads",
        len(fastq_read_id_set),
    ),
    (
        "duplicate_fastq_read_ids",
        len(fastq_read_ids)
        - len(fastq_read_id_set),
    ),
    (
        "missing_case_reads",
        len(missing_case_reads),
    ),
    (
        "fixture_manifest_rows",
        len(fixture_manifest_rows),
    ),
    (
        "fixture_manifest_failures",
        fixture_manifest_failures,
    ),
]

status = "PASS"

if (
    schema_version != "0.3.2"
    or not EXPECTED_CODES <= tsv_failure_codes
    or any(count != 1 for count in code_counts.values())
    or json_failure_codes != tsv_failure_codes
    or dictionary_mismatches
    or template_mismatches
    or schema_manifest_failures
    or schema_manifest_missing_files
    or schema_manifest_extra_files
    or len(case_rows) != 20
    or len(set(case_ids)) != 20
    or case_versions != {"v0.3.2"}
    or not EXPECTED_CASE_IDS <= set(case_ids)
    or case_header_width != 18
    or case_width_failures
    or len(rule_rows) != 16
    or len(set(rule_ids)) != 16
    or not EXPECTED_RULE_IDS <= set(rule_ids)
    or rule_header_width != 5
    or rule_width_failures
    or len(fastq_read_id_set) != 19
    or len(fastq_read_ids) != 19
    or missing_case_reads
    or fixture_manifest_failures
):
    status = "REVIEW"

metrics.append(("postcheck_status", status))

for path in (QC, SUMMARY):
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
        writer.writerows(metrics)

if status != "PASS":
    raise SystemExit(
        "Schema/regression v0.3.2 postcheck requires review"
    )
PY

python -m py_compile "$PY"

rm -f "$QC" "$SUMMARY" "$MANIFEST"

python "$PY" \
  "$SCHEMA" \
  "$FIXTURE" \
  "$QC" \
  "$SUMMARY"

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in "$QC" "$SUMMARY"; do
        printf '%s\t%s\t%s\t%s\t%s\n' \
          "$(basename "$path")" \
          "$(awk 'END {print NR-1}' "$path")" \
          "$(stat -c '%s' "$path")" \
          "$(sha256sum "$path" | awk '{print $1}')" \
          "$path"
    done
} > "$MANIFEST"

echo
echo "===== POSTCHECK QC ====="
column -ts $'\t' "$QC"

echo
echo "===== NEW FAILURE CODES ====="
awk -F '\t' '
  NR == 1 {
    print
    next
  }
  $1 == "failure_code" &&
  (
    $2 == "ORIENTATION_INCONSISTENT_BRIDGE" ||
    $2 == "TARGET_ENTRY_NOT_PROJECTED" ||
    $2 == "HOMOPOLYMER_REVIEW"
  ) {
    print
  }
' \
  "$SCHEMA/dictionaries/rnatr_v03_enums.tsv" \
  | column -ts $'\t'

echo
echo "===== NEW REGRESSION CASES ====="
awk -F '\t' '
  NR == 1 {
    print
    next
  }
  $2 == "RC019" || $2 == "RC020" {
    print
  }
' \
  "$FIXTURE/regression_cases.tsv" \
  | column -ts $'\t'

echo
echo "===== NEW DECISION RULES ====="
awk -F '\t' '
  NR == 1 {
    print
    next
  }
  $1 == "R014" ||
  $1 == "R015" ||
  $1 == "R016" {
    print
  }
' \
  "$FIXTURE/decision_rules.tsv" \
  | column -ts $'\t'

echo
echo "===== MANIFEST ====="
column -ts $'\t' "$MANIFEST"
