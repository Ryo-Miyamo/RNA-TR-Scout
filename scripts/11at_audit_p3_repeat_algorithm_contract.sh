#!/usr/bin/env bash
set -euo pipefail

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
fi

conda activate rnatr-v03
source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"

SOURCE_SCRIPT="$PROJECT_ROOT/scripts/11af_measure_p3_target_entry_repeat_tracts.sh"
SIZING="$PROJECT_ROOT/results/11_p3_target_entry_sizing/$RUN_ID/p3_target_entry_repeat_evidence.tsv"
PAIR_PROJECTION="$PROJECT_ROOT/results/11_production_p3_pair_projection_fix/$RUN_ID/p3_pair_alignment_projection_replay.corrected.tsv"
PACKAGE_PAIR="$PROJECT_ROOT/src/rnatr_scout/p3_pair.py"
PACKAGE_CIGAR="$PROJECT_ROOT/src/rnatr_scout/cigar.py"

OUTDIR="$PROJECT_ROOT/results/11_p3_repeat_contract_audit/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_p3_repeat_contract_audit/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_p3_repeat_contract_audit/$RUN_ID"

REPORT="$OUTDIR/p3_repeat_algorithm_contract_report.txt"
FUNCTIONS="$OUTDIR/p3_repeat_python_functions.tsv"
CONSTANTS="$OUTDIR/p3_repeat_python_constants.tsv"
KEYWORDS="$OUTDIR/p3_repeat_keyword_lines.tsv"
SIZING_SUMMARY="$OUTDIR/p3_repeat_sizing_summary.tsv"
POSITIVE_ROWS="$OUTDIR/p3_repeat_positive_rows.tsv"
QC="$QCDIR/p3_repeat_algorithm_contract_audit.qc.tsv"
MANIFEST="$OUTDIR/${RUN_ID}.p3_repeat_algorithm_contract_audit.manifest.tsv"
PY="$WORKDIR/audit_p3_repeat_contract.py"
EXTRACTED="$WORKDIR/11af_embedded_python.py"

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR"

for path in \
  "$SOURCE_SCRIPT" \
  "$SIZING" \
  "$PAIR_PROJECTION" \
  "$PACKAGE_PAIR" \
  "$PACKAGE_CIGAR"
do
    test -e "$path" || {
        echo "ERROR: missing required path: $path" >&2
        exit 1
    }
done

cat > "$PY" <<'PY'
from __future__ import annotations

import ast
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

(
    source_script_text,
    sizing_text,
    pair_projection_text,
    package_pair_text,
    package_cigar_text,
    extracted_text,
    report_text,
    functions_text,
    constants_text,
    keywords_text,
    sizing_summary_text,
    positive_rows_text,
    qc_text,
) = sys.argv[1:]

SOURCE_SCRIPT = Path(source_script_text)
SIZING = Path(sizing_text)
PAIR_PROJECTION = Path(pair_projection_text)
PACKAGE_PAIR = Path(package_pair_text)
PACKAGE_CIGAR = Path(package_cigar_text)
EXTRACTED = Path(extracted_text)
REPORT = Path(report_text)
FUNCTIONS = Path(functions_text)
CONSTANTS = Path(constants_text)
KEYWORDS = Path(keywords_text)
SIZING_SUMMARY = Path(sizing_summary_text)
POSITIVE_ROWS = Path(positive_rows_text)
QC = Path(qc_text)

KEYWORD_PATTERN = re.compile(
    r"tract|purity|motif|target_entry|repeat|mismatch|match_bp|"
    r"raw_end|lower_bound|partial_internal|cigar|projection",
    re.IGNORECASE,
)


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def extract_python_blocks(text: str) -> list[tuple[str, str]]:
    pattern = re.compile(
        r"<<['\"]?(PY[A-Z0-9_]*)['\"]?\n(.*?)\n\1(?:\n|$)",
        re.DOTALL,
    )
    return [
        (marker, body)
        for marker, body in pattern.findall(text)
    ]


source_text = SOURCE_SCRIPT.read_text(
    encoding="utf-8",
    errors="replace",
)
blocks = extract_python_blocks(source_text)

compiled_blocks: list[tuple[str, str]] = []
for marker, body in blocks:
    try:
        compile(body, f"{SOURCE_SCRIPT.name}:{marker}", "exec")
    except SyntaxError:
        continue
    compiled_blocks.append((marker, body))

if not compiled_blocks:
    raise SystemExit(
        "No compilable embedded Python block found in 11af"
    )

# Prefer the largest Python block because 11af's main implementation is
# expected to be the longest heredoc.
marker, python_source = max(
    compiled_blocks,
    key=lambda item: len(item[1]),
)
EXTRACTED.write_text(
    python_source.rstrip() + "\n",
    encoding="utf-8",
)

tree = ast.parse(
    python_source,
    filename=str(EXTRACTED),
)
source_lines = python_source.splitlines()

function_rows: list[dict[str, object]] = []
constant_rows: list[dict[str, object]] = []

for node in tree.body:
    if isinstance(
        node,
        (ast.FunctionDef, ast.AsyncFunctionDef),
    ):
        signature = ast.get_source_segment(
            python_source,
            node,
        )
        first_line = (
            signature.splitlines()[0]
            if signature
            else node.name
        )
        function_rows.append(
            {
                "function_name": node.name,
                "start_line": node.lineno,
                "end_line": getattr(
                    node,
                    "end_lineno",
                    node.lineno,
                ),
                "signature": first_line.strip(),
            }
        )

    if isinstance(node, ast.Assign):
        try:
            value = ast.literal_eval(node.value)
        except Exception:
            continue

        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue

            name = target.id
            if not (
                name.isupper()
                or any(
                    token in name.lower()
                    for token in (
                        "threshold",
                        "minimum",
                        "maximum",
                        "purity",
                        "motif",
                        "entry",
                        "tract",
                        "flank",
                    )
                )
            ):
                continue

            constant_rows.append(
                {
                    "name": name,
                    "value": json.dumps(
                        value,
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    "line_number": node.lineno,
                }
            )

keyword_rows: list[dict[str, object]] = []
for line_number, line in enumerate(
    source_lines,
    start=1,
):
    if KEYWORD_PATTERN.search(line):
        keyword_rows.append(
            {
                "line_number": line_number,
                "source_line": line.rstrip(),
            }
        )

with FUNCTIONS.open(
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=[
            "function_name",
            "start_line",
            "end_line",
            "signature",
        ],
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(function_rows)

with CONSTANTS.open(
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=[
            "name",
            "value",
            "line_number",
        ],
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(constant_rows)

with KEYWORDS.open(
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=[
            "line_number",
            "source_line",
        ],
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(keyword_rows)

sizing_rows = read_tsv(SIZING)
pair_rows = read_tsv(PAIR_PROJECTION)

if not sizing_rows:
    raise SystemExit("Sizing TSV is empty")

sizing_columns = list(sizing_rows[0].keys())
pair_columns = list(pair_rows[0].keys()) if pair_rows else []

summary_counter: Counter[tuple[str, str]] = Counter()

summary_dimensions = [
    "target_entry_projection_status",
    "best_alignment_strand",
    "evidence_class",
    "sizing_status",
    "canonical_motif",
]

for row in sizing_rows:
    for dimension in summary_dimensions:
        if dimension in row:
            summary_counter[
                (dimension, row[dimension])
            ] += 1

positive_rows = [
    row
    for row in sizing_rows
    if (
        row.get("evidence_class")
        not in {
            "",
            ".",
            "P3_BRIDGE_ONLY_NO_TARGET_ENTRY_REPEAT_TRACT",
            "UNRESOLVED",
        }
        or row.get("sizing_status")
        in {
            "partial_internal",
            "lower_bound",
            "exact_span",
        }
        or (
            row.get("tract_bp")
            not in {"", ".", "0", None}
        )
    )
]

with SIZING_SUMMARY.open(
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
            "dimension",
            "value",
            "rows",
        ]
    )
    for (dimension, value), count in sorted(
        summary_counter.items()
    ):
        writer.writerow(
            [
                dimension,
                value,
                count,
            ]
        )

with POSITIVE_ROWS.open(
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=sizing_columns,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(positive_rows)

imports: list[str] = []
for node in tree.body:
    if isinstance(node, ast.Import):
        imports.extend(
            alias.name
            for alias in node.names
        )
    elif isinstance(node, ast.ImportFrom):
        module = node.module or ""
        imports.append(module)

function_names = {
    row["function_name"]
    for row in function_rows
}

likely_repeat_functions = sorted(
    name
    for name in function_names
    if any(
        token in name.lower()
        for token in (
            "repeat",
            "tract",
            "motif",
            "period",
            "scan",
            "purity",
            "align",
            "project",
        )
    )
)

uses_external_python_packages = sorted(
    module
    for module in set(imports)
    if module.split(".")[0]
    not in {
        "__future__",
        "argparse",
        "collections",
        "csv",
        "dataclasses",
        "functools",
        "gzip",
        "hashlib",
        "itertools",
        "json",
        "math",
        "os",
        "pathlib",
        "re",
        "shutil",
        "statistics",
        "subprocess",
        "sys",
        "tempfile",
        "typing",
    }
)

pair_projection_ids = {
    row["projection_id"]
    for row in pair_rows
    if "projection_id" in row
}
sizing_projection_ids = {
    row["projection_id"]
    for row in sizing_rows
    if "projection_id" in row
}

missing_pair_rows = (
    sizing_projection_ids - pair_projection_ids
)
unexpected_pair_rows = (
    pair_projection_ids - sizing_projection_ids
)

with REPORT.open(
    "w",
    encoding="utf-8",
) as handle:
    handle.write(
        "RNA-TR-Scout P3 repeat algorithm contract audit\n"
    )
    handle.write(
        "============================================\n\n"
    )
    handle.write(
        f"source_script={SOURCE_SCRIPT}\n"
    )
    handle.write(
        f"embedded_python_marker={marker}\n"
    )
    handle.write(
        f"embedded_python_lines={len(source_lines)}\n"
    )
    handle.write(
        f"embedded_python_functions={len(function_rows)}\n"
    )
    handle.write(
        "likely_repeat_functions="
        + (
            ",".join(likely_repeat_functions)
            if likely_repeat_functions
            else "."
        )
        + "\n"
    )
    handle.write(
        "python_imports="
        + ",".join(sorted(set(imports)))
        + "\n"
    )
    handle.write(
        "external_python_packages="
        + (
            ",".join(uses_external_python_packages)
            if uses_external_python_packages
            else "."
        )
        + "\n\n"
    )

    handle.write(
        "===== SIZING CONTRACT =====\n"
    )
    handle.write(
        "sizing_rows={}\n".format(
            len(sizing_rows)
        )
    )
    handle.write(
        "sizing_columns={}\n".format(
            len(sizing_columns)
        )
    )
    handle.write(
        "positive_or_tract_rows={}\n".format(
            len(positive_rows)
        )
    )
    handle.write(
        "pair_projection_rows={}\n".format(
            len(pair_rows)
        )
    )
    handle.write(
        "missing_pair_projection_ids={}\n".format(
            len(missing_pair_rows)
        )
    )
    handle.write(
        "unexpected_pair_projection_ids={}\n".format(
            len(unexpected_pair_rows)
        )
    )
    handle.write(
        "sizing_header="
        + "\t".join(sizing_columns)
        + "\n"
    )
    handle.write(
        "pair_projection_header="
        + "\t".join(pair_columns)
        + "\n\n"
    )

    handle.write(
        "===== FUNCTION INDEX =====\n"
    )
    for row in function_rows:
        handle.write(
            "{function_name}\t{start_line}-{end_line}\t"
            "{signature}\n".format(**row)
        )

    handle.write(
        "\n===== CONSTANTS / LITERAL PARAMETERS =====\n"
    )
    for row in constant_rows:
        handle.write(
            "{name}\t{value}\tline={line_number}\n".format(
                **row
            )
        )

    handle.write(
        "\n===== RELEVANT SOURCE CONTEXT =====\n"
    )
    relevant_line_numbers = {
        int(row["line_number"])
        for row in keyword_rows
    }
    expanded_line_numbers: set[int] = set()
    for line_number in relevant_line_numbers:
        expanded_line_numbers.update(
            range(
                max(1, line_number - 2),
                min(
                    len(source_lines),
                    line_number + 2,
                )
                + 1,
            )
        )

    previous = None
    for line_number in sorted(
        expanded_line_numbers
    ):
        if (
            previous is not None
            and line_number > previous + 1
        ):
            handle.write("...\n")
        handle.write(
            f"{line_number:05d}: "
            + source_lines[line_number - 1]
            + "\n"
        )
        previous = line_number

    handle.write(
        "\n===== PRODUCTION INTEGRATION BOUNDARY =====\n"
    )
    handle.write(
        "Upstream production modules already provide:\n"
    )
    handle.write(
        "- normalized query/reference pair alignment\n"
    )
    handle.write(
        "- bridge validation\n"
    )
    handle.write(
        "- target-entry query offset\n"
    )
    handle.write(
        "- explicit reverse-alignment status\n"
    )
    handle.write(
        "The next production module should begin from the "
        "target-entry query offset and reproduce the observed "
        "tract, purity, boundary, and sizing fields without "
        "re-running locus assignment.\n"
    )

status = "PASS"

if (
    len(sizing_rows) != 23
    or len(pair_rows) != 23
    or missing_pair_rows
    or unexpected_pair_rows
    or len(positive_rows) != 1
    or not function_rows
    or not keyword_rows
):
    status = "REVIEW"

with QC.open(
    "w",
    encoding="utf-8",
) as handle:
    handle.write("metric\tvalue\n")
    handle.write(
        "embedded_python_blocks_found\t{}\n".format(
            len(blocks)
        )
    )
    handle.write(
        "compilable_python_blocks\t{}\n".format(
            len(compiled_blocks)
        )
    )
    handle.write(
        "selected_python_lines\t{}\n".format(
            len(source_lines)
        )
    )
    handle.write(
        "python_functions\t{}\n".format(
            len(function_rows)
        )
    )
    handle.write(
        "literal_parameters\t{}\n".format(
            len(constant_rows)
        )
    )
    handle.write(
        "keyword_source_lines\t{}\n".format(
            len(keyword_rows)
        )
    )
    handle.write(
        "sizing_rows\t{}\n".format(
            len(sizing_rows)
        )
    )
    handle.write(
        "pair_projection_rows\t{}\n".format(
            len(pair_rows)
        )
    )
    handle.write(
        "missing_pair_projection_ids\t{}\n".format(
            len(missing_pair_rows)
        )
    )
    handle.write(
        "unexpected_pair_projection_ids\t{}\n".format(
            len(unexpected_pair_rows)
        )
    )
    handle.write(
        "positive_or_tract_rows\t{}\n".format(
            len(positive_rows)
        )
    )
    handle.write(
        "external_python_packages\t{}\n".format(
            len(uses_external_python_packages)
        )
    )
    handle.write(
        "repeat_contract_audit_status\t{}\n".format(
            status
        )
    )

if status != "PASS":
    raise SystemExit(
        "P3 repeat algorithm contract audit requires review"
    )
PY

python -m py_compile "$PY"

rm -f \
  "$REPORT" \
  "$FUNCTIONS" \
  "$CONSTANTS" \
  "$KEYWORDS" \
  "$SIZING_SUMMARY" \
  "$POSITIVE_ROWS" \
  "$QC" \
  "$MANIFEST" \
  "$EXTRACTED"

python "$PY" \
  "$SOURCE_SCRIPT" \
  "$SIZING" \
  "$PAIR_PROJECTION" \
  "$PACKAGE_PAIR" \
  "$PACKAGE_CIGAR" \
  "$EXTRACTED" \
  "$REPORT" \
  "$FUNCTIONS" \
  "$CONSTANTS" \
  "$KEYWORDS" \
  "$SIZING_SUMMARY" \
  "$POSITIVE_ROWS" \
  "$QC"

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in \
      "$FUNCTIONS" \
      "$CONSTANTS" \
      "$KEYWORDS" \
      "$SIZING_SUMMARY" \
      "$POSITIVE_ROWS" \
      "$QC"
    do
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
echo "===== FUNCTIONS ====="
column -ts $'\t' "$FUNCTIONS"

echo
echo "===== CONSTANTS ====="
column -ts $'\t' "$CONSTANTS"

echo
echo "===== SIZING SUMMARY ====="
column -ts $'\t' "$SIZING_SUMMARY"

echo
echo "===== POSITIVE / TRACT ROWS ====="
column -ts $'\t' "$POSITIVE_ROWS"

echo
echo "===== REPORT LOCATION ====="
echo "$REPORT"

echo
echo "===== MANIFEST ====="
column -ts $'\t' "$MANIFEST"
