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
FROZEN_RULES="$PROJECT_ROOT/results/11_p3_orientation_freeze/$RUN_ID/p3_frozen_rules.tsv"
FROZEN_CLASSIFICATION="$PROJECT_ROOT/results/11_p3_orientation_freeze/$RUN_ID/p3_orientation_corrected_classification.tsv"

OUTDIR="$PROJECT_ROOT/results/11_p3_integration_contract/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_p3_integration_contract/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_p3_integration_contract/$RUN_ID"

REPORT="$OUTDIR/p3_integration_contract_report.txt"
FILES="$OUTDIR/p3_integration_contract_files.tsv"
QC="$QCDIR/p3_integration_contract.qc.tsv"
MANIFEST="$OUTDIR/${RUN_ID}.p3_integration_contract.manifest.tsv"
PY="$WORKDIR/extract_p3_integration_contract.py"

EXPECTED_SCHEMA_FILES=27
EXPECTED_REGRESSION_FILES=5
EXPECTED_FROZEN_RULES=5
EXPECTED_FROZEN_ROWS=23

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR"

for path in \
  "$SCHEMA_DIR" \
  "$REGRESSION_DIR" \
  "$FROZEN_RULES" \
  "$FROZEN_CLASSIFICATION"
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
import hashlib
import json
import os
import sys
from pathlib import Path

(
    project_root_text,
    schema_dir_text,
    regression_dir_text,
    frozen_rules_text,
    frozen_classification_text,
    report_path_text,
    files_path_text,
    qc_path_text,
    expected_schema_files_text,
    expected_regression_files_text,
    expected_frozen_rules_text,
    expected_frozen_rows_text,
) = sys.argv[1:]

PROJECT_ROOT = Path(project_root_text)
SCHEMA_DIR = Path(schema_dir_text)
REGRESSION_DIR = Path(regression_dir_text)
FROZEN_RULES = Path(frozen_rules_text)
FROZEN_CLASSIFICATION = Path(
    frozen_classification_text
)
REPORT = Path(report_path_text)
FILES = Path(files_path_text)
QC = Path(qc_path_text)

EXPECTED_SCHEMA_FILES = int(
    expected_schema_files_text
)
EXPECTED_REGRESSION_FILES = int(
    expected_regression_files_text
)
EXPECTED_FROZEN_RULES = int(
    expected_frozen_rules_text
)
EXPECTED_FROZEN_ROWS = int(
    expected_frozen_rows_text
)


def open_text(path: Path):
    if path.suffix == ".gz":
        return gzip.open(
            path,
            "rt",
            encoding="utf-8",
            errors="replace",
        )

    return path.open(
        "r",
        encoding="utf-8",
        errors="replace",
    )


def line_count(path: Path):
    try:
        with open_text(path) as handle:
            return sum(1 for _ in handle)
    except Exception:
        return None


def sha256(path: Path):
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)

            if not block:
                break

            digest.update(block)

    return digest.hexdigest()


def render_file(
    output,
    path: Path,
    maximum_lines: int | None = None,
):
    print(
        "\n--- {} ---".format(path),
        file=output,
    )

    try:
        with open_text(path) as handle:
            for index, line in enumerate(
                handle,
                start=1,
            ):
                if (
                    maximum_lines is not None
                    and index > maximum_lines
                ):
                    print(
                        "[truncated after {} lines]".format(
                            maximum_lines
                        ),
                        file=output,
                    )
                    break

                print(
                    line.rstrip("\n"),
                    file=output,
                )

    except UnicodeDecodeError:
        print(
            "[binary or undecodable file]",
            file=output,
        )


def recursively_find(
    value,
    path=(),
):
    matches = []
    terms = {
        "read_evidence",
        "repeat_segments",
        "evidence_class",
        "sizing_status",
        "rna_evidence_status",
        "evaluability_status",
    }

    if isinstance(value, dict):
        for key, child in value.items():
            child_path = path + (str(key),)

            if any(
                term in str(key).lower()
                for term in terms
            ):
                matches.append(
                    (
                        ".".join(child_path),
                        child,
                    )
                )

            matches.extend(
                recursively_find(
                    child,
                    child_path,
                )
            )

    elif isinstance(value, list):
        for index, child in enumerate(value):
            matches.extend(
                recursively_find(
                    child,
                    path + (str(index),),
                )
            )

    return matches


schema_files = sorted(
    path
    for path in SCHEMA_DIR.rglob("*")
    if path.is_file()
)
regression_files = sorted(
    path
    for path in REGRESSION_DIR.rglob("*")
    if path.is_file()
)

production_candidates = sorted(
    {
        *PROJECT_ROOT.glob("pyproject.toml"),
        *PROJECT_ROOT.glob("setup.py"),
        *PROJECT_ROOT.glob("setup.cfg"),
        *PROJECT_ROOT.glob("src/**/*.py"),
        *PROJECT_ROOT.glob("code/**/*.py"),
        *PROJECT_ROOT.glob("rnatr/**/*.py"),
        *PROJECT_ROOT.glob("rna_tr_scout/**/*.py"),
        *PROJECT_ROOT.glob("bin/*"),
    }
)

production_candidates = [
    path
    for path in production_candidates
    if path.is_file()
]

file_rows = []

for category, paths in [
    ("schema", schema_files),
    ("regression", regression_files),
    ("production_candidate", production_candidates),
    (
        "frozen_input",
        [FROZEN_RULES, FROZEN_CLASSIFICATION],
    ),
]:
    for path in paths:
        file_rows.append(
            {
                "category": category,
                "path": str(path),
                "bytes": path.stat().st_size,
                "lines": (
                    line_count(path)
                    if path.suffix.lower()
                    in {
                        ".tsv",
                        ".csv",
                        ".txt",
                        ".md",
                        ".json",
                        ".yaml",
                        ".yml",
                        ".gz",
                    }
                    else "."
                ),
                "sha256": sha256(path),
            }
        )

with FILES.open(
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=[
            "category",
            "path",
            "bytes",
            "lines",
            "sha256",
        ],
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(file_rows)

read_evidence_dictionary = (
    SCHEMA_DIR
    / "dictionaries"
    / "read_evidence.columns.tsv"
)
repeat_segments_dictionary = (
    SCHEMA_DIR
    / "dictionaries"
    / "repeat_segments.columns.tsv"
)
enums_dictionary = (
    SCHEMA_DIR
    / "dictionaries"
    / "rnatr_v03_enums.tsv"
)
table_schema = (
    SCHEMA_DIR
    / "schema"
    / "rnatr_v03_table_schema.json"
)
read_evidence_template = (
    SCHEMA_DIR
    / "templates"
    / "read_evidence.tsv"
)
repeat_segments_template = (
    SCHEMA_DIR
    / "templates"
    / "repeat_segments.tsv"
)
validator = (
    SCHEMA_DIR
    / "rnatr_v03_validate_tsv.py"
)

required_contract_files = [
    read_evidence_dictionary,
    repeat_segments_dictionary,
    enums_dictionary,
    table_schema,
    read_evidence_template,
    repeat_segments_template,
    validator,
]

missing_contract_files = [
    path
    for path in required_contract_files
    if not path.is_file()
]

with REPORT.open(
    "w",
    encoding="utf-8",
) as output:
    print(
        "RNA-TR-Scout P3 integration contract report",
        file=output,
    )
    print(
        "===========================================",
        file=output,
    )
    print(
        "project_root={}".format(PROJECT_ROOT),
        file=output,
    )
    print(
        "schema_dir={}".format(SCHEMA_DIR),
        file=output,
    )
    print(
        "regression_dir={}".format(
            REGRESSION_DIR
        ),
        file=output,
    )

    print(
        "\n===== PRODUCTION PACKAGE ASSESSMENT =====",
        file=output,
    )

    if production_candidates:
        for path in production_candidates:
            print(path, file=output)
    else:
        print(
            "NO_PRODUCTION_CALLER_PACKAGE_DETECTED",
            file=output,
        )
        print(
            "No pyproject/setup/src/code Python caller "
            "implementation was found.",
            file=output,
        )

    print(
        "\n===== READ_EVIDENCE DICTIONARY =====",
        file=output,
    )
    render_file(
        output,
        read_evidence_dictionary,
    )

    print(
        "\n===== REPEAT_SEGMENTS DICTIONARY =====",
        file=output,
    )
    render_file(
        output,
        repeat_segments_dictionary,
    )

    print(
        "\n===== ENUMS =====",
        file=output,
    )
    render_file(
        output,
        enums_dictionary,
    )

    print(
        "\n===== READ_EVIDENCE TEMPLATE =====",
        file=output,
    )
    render_file(
        output,
        read_evidence_template,
        maximum_lines=10,
    )

    print(
        "\n===== REPEAT_SEGMENTS TEMPLATE =====",
        file=output,
    )
    render_file(
        output,
        repeat_segments_template,
        maximum_lines=10,
    )

    print(
        "\n===== JSON SCHEMA RELEVANT NODES =====",
        file=output,
    )

    try:
        schema_object = json.loads(
            table_schema.read_text(
                encoding="utf-8"
            )
        )
        matches = recursively_find(
            schema_object
        )
        seen = set()

        for path, value in matches:
            serialized = json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
            signature = (
                path,
                serialized,
            )

            if signature in seen:
                continue

            seen.add(signature)
            print(
                "\n### {}".format(path),
                file=output,
            )
            print(
                serialized,
                file=output,
            )

    except Exception as error:
        print(
            "JSON_SCHEMA_PARSE_ERROR: {}".format(
                error
            ),
            file=output,
        )

    print(
        "\n===== VALIDATOR SYMBOLS =====",
        file=output,
    )

    validator_terms = (
        "read_evidence",
        "repeat_segments",
        "evidence_class",
        "sizing_status",
        "enum",
        "schema_version",
    )

    with validator.open(
        "r",
        encoding="utf-8",
        errors="replace",
    ) as handle:
        for line_number, line in enumerate(
            handle,
            start=1,
        ):
            if any(
                term in line
                for term in validator_terms
            ):
                print(
                    "{}:{}:{}".format(
                        validator,
                        line_number,
                        line.rstrip("\n"),
                    ),
                    file=output,
                )

    print(
        "\n===== REGRESSION FILE INVENTORY =====",
        file=output,
    )

    for path in regression_files:
        print(
            "{}\t{}\t{} bytes".format(
                path,
                line_count(path),
                path.stat().st_size,
            ),
            file=output,
        )

    print(
        "\n===== REGRESSION FILE PREVIEWS =====",
        file=output,
    )

    for path in regression_files:
        suffixes = "".join(path.suffixes).lower()

        if suffixes.endswith(
            (
                ".tsv",
                ".csv",
                ".txt",
                ".md",
                ".json",
                ".yaml",
                ".yml",
                ".tsv.gz",
                ".csv.gz",
                ".txt.gz",
            )
        ):
            render_file(
                output,
                path,
                maximum_lines=120,
            )
        elif suffixes.endswith(
            (
                ".fastq",
                ".fq",
                ".fastq.gz",
                ".fq.gz",
                ".fasta",
                ".fa",
                ".fasta.gz",
                ".fa.gz",
            )
        ):
            render_file(
                output,
                path,
                maximum_lines=24,
            )
        else:
            print(
                "\n--- {} ---".format(path),
                file=output,
            )
            print(
                "[binary or non-previewed]",
                file=output,
            )

    print(
        "\n===== FROZEN P3 RULES =====",
        file=output,
    )
    render_file(
        output,
        FROZEN_RULES,
    )

    print(
        "\n===== FROZEN P3 CLASSIFICATION COUNTS =====",
        file=output,
    )

    with FROZEN_CLASSIFICATION.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        rows = list(
            csv.DictReader(
                handle,
                delimiter="\t",
            )
        )

    frozen_counts = {}
    emission_counts = {}

    for row in rows:
        frozen_counts[
            row["frozen_p3_status"]
        ] = (
            frozen_counts.get(
                row["frozen_p3_status"],
                0,
            )
            + 1
        )
        emission_counts[
            row[
                "standard_p3_evidence_emitted"
            ]
        ] = (
            emission_counts.get(
                row[
                    "standard_p3_evidence_emitted"
                ],
                0,
            )
            + 1
        )

    for key, value in sorted(
        frozen_counts.items()
    ):
        print(
            "frozen_status::{}\t{}".format(
                key,
                value,
            ),
            file=output,
        )

    for key, value in sorted(
        emission_counts.items()
    ):
        print(
            "standard_evidence_emitted::{}\t{}".format(
                key,
                value,
            ),
            file=output,
        )

    print(
        "\n===== PROVISIONAL INTEGRATION DECISION =====",
        file=output,
    )
    print(
        "1. Preserve schema v0.3.1 as an immutable checkpoint.",
        file=output,
    )
    print(
        "2. Create schema v0.3.2 only after enumerating "
        "the exact P3 fields/enums required.",
        file=output,
    )
    print(
        "3. Create a new production Python package and CLI; "
        "do not treat exploratory scripts as the final caller.",
        file=output,
    )
    print(
        "4. Add P3 orientation-inconsistent and homopolymer "
        "negative regression cases before full-cohort execution.",
        file=output,
    )
    print(
        "5. Keep exact length, allele length, expansion, and "
        "pathogenicity unavailable for one-flank P3 calls.",
        file=output,
    )

schema_file_count = len(schema_files)
regression_file_count = len(regression_files)
frozen_rule_rows = max(
    0,
    line_count(FROZEN_RULES) - 1,
)
frozen_rows = max(
    0,
    line_count(FROZEN_CLASSIFICATION) - 1,
)

status = "PASS"

if (
    schema_file_count
    != EXPECTED_SCHEMA_FILES
    or regression_file_count
       != EXPECTED_REGRESSION_FILES
    or frozen_rule_rows
       != EXPECTED_FROZEN_RULES
    or frozen_rows
       != EXPECTED_FROZEN_ROWS
    or missing_contract_files
):
    status = "REVIEW"

with QC.open(
    "w",
    encoding="utf-8",
) as handle:
    handle.write("metric\tvalue\n")
    handle.write(
        "schema_files\t{}\n".format(
            schema_file_count
        )
    )
    handle.write(
        "regression_files\t{}\n".format(
            regression_file_count
        )
    )
    handle.write(
        "production_package_files\t{}\n".format(
            len(production_candidates)
        )
    )
    handle.write(
        "required_contract_files\t{}\n".format(
            len(required_contract_files)
        )
    )
    handle.write(
        "missing_contract_files\t{}\n".format(
            len(missing_contract_files)
        )
    )
    handle.write(
        "frozen_rule_rows\t{}\n".format(
            frozen_rule_rows
        )
    )
    handle.write(
        "frozen_classification_rows\t{}\n".format(
            frozen_rows
        )
    )
    handle.write(
        "report_bytes\t{}\n".format(
            REPORT.stat().st_size
        )
    )
    handle.write(
        "contract_status\t{}\n".format(
            status
        )
    )

if status != "PASS":
    raise SystemExit(
        "P3 integration contract extraction requires review"
    )
PY

python -m py_compile "$PY"

rm -f \
  "$REPORT" \
  "$FILES" \
  "$QC" \
  "$MANIFEST"

python "$PY" \
  "$PROJECT_ROOT" \
  "$SCHEMA_DIR" \
  "$REGRESSION_DIR" \
  "$FROZEN_RULES" \
  "$FROZEN_CLASSIFICATION" \
  "$REPORT" \
  "$FILES" \
  "$QC" \
  "$EXPECTED_SCHEMA_FILES" \
  "$EXPECTED_REGRESSION_FILES" \
  "$EXPECTED_FROZEN_RULES" \
  "$EXPECTED_FROZEN_ROWS"

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in "$FILES" "$QC"; do
        printf '%s\t%s\t%s\t%s\t%s\n' \
          "$(basename "$path")" \
          "$(awk 'END {print NR-1}' "$path")" \
          "$(stat -c '%s' "$path")" \
          "$(sha256sum "$path" | awk '{print $1}')" \
          "$path"
    done

    printf '%s\t%s\t%s\t%s\t%s\n' \
      "$(basename "$REPORT")" \
      "." \
      "$(stat -c '%s' "$REPORT")" \
      "$(sha256sum "$REPORT" | awk '{print $1}')" \
      "$REPORT"
} > "$MANIFEST"

echo "===== QC ====="
column -ts $'\t' "$QC"

echo
echo "===== CONTRACT REPORT ====="
cat "$REPORT"

echo
echo "===== MANIFEST ====="
column -ts $'\t' "$MANIFEST"
