#!/usr/bin/env bash
set -euo pipefail

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
fi

conda activate rnatr-v03
source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"

EXTRACTED="$PROJECT_ROOT/tmp/11_p3_repeat_contract_audit/$RUN_ID/11af_embedded_python.py"
SIZING="$PROJECT_ROOT/results/11_p3_target_entry_sizing/$RUN_ID/p3_target_entry_repeat_evidence.tsv"

OUTDIR="$PROJECT_ROOT/results/11_p3_repeat_core_contract/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_p3_repeat_core_contract/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_p3_repeat_core_contract/$RUN_ID"

CORE_SOURCE="$OUTDIR/p3_repeat_core_functions.py"
RUN_PAIR_CONTEXT="$OUTDIR/p3_repeat_run_pair_relevant_context.txt"
IMPORTS="$OUTDIR/p3_repeat_imports.tsv"
CALL_GRAPH="$OUTDIR/p3_repeat_call_graph.tsv"
ASSIGNMENTS="$OUTDIR/p3_repeat_relevant_assignments.tsv"
POSITIVE="$OUTDIR/p3_repeat_positive_contract.tsv"
QC="$QCDIR/p3_repeat_core_contract.qc.tsv"
MANIFEST="$OUTDIR/${RUN_ID}.p3_repeat_core_contract.manifest.tsv"
PY="$WORKDIR/extract_p3_repeat_core_contract.py"

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR"

for path in "$EXTRACTED" "$SIZING"; do
    test -e "$path" || {
        echo "ERROR: missing required path: $path" >&2
        exit 1
    }
done

cat > "$PY" <<'PY'
from __future__ import annotations

import ast
import csv
import sys
from pathlib import Path

(
    extracted_text,
    sizing_text,
    core_source_text,
    run_pair_context_text,
    imports_text,
    call_graph_text,
    assignments_text,
    positive_text,
    qc_text,
) = sys.argv[1:]

EXTRACTED = Path(extracted_text)
SIZING = Path(sizing_text)
CORE_SOURCE = Path(core_source_text)
RUN_PAIR_CONTEXT = Path(run_pair_context_text)
IMPORTS = Path(imports_text)
CALL_GRAPH = Path(call_graph_text)
ASSIGNMENTS = Path(assignments_text)
POSITIVE = Path(positive_text)
QC = Path(qc_text)

CORE_FUNCTIONS = [
    "reverse_complement",
    "rotations",
    "canonical_motif",
    "state_rank",
    "update",
    "prefix_periodicity",
    "longest_valid_periodic_prefix",
    "oriented_to_raw_interval",
]

RELEVANT_TERMS = (
    "tract",
    "purity",
    "motif",
    "target_entry",
    "repeat",
    "mismatch",
    "match_bp",
    "raw_end",
    "lower_bound",
    "partial_internal",
    "evidence_class",
    "sizing_status",
    "prefix_periodicity",
    "longest_valid_periodic_prefix",
    "oriented_to_raw_interval",
)

source = EXTRACTED.read_text(
    encoding="utf-8",
    errors="replace",
)
source_lines = source.splitlines()
tree = ast.parse(source, filename=str(EXTRACTED))

functions: dict[str, ast.FunctionDef] = {}
for node in tree.body:
    if isinstance(node, ast.FunctionDef):
        functions[node.name] = node

missing_core_functions = [
    name
    for name in CORE_FUNCTIONS
    if name not in functions
]

if "run_pair" not in functions:
    raise SystemExit("run_pair() was not found")

function_chunks = []
for name in CORE_FUNCTIONS:
    node = functions.get(name)

    if node is None:
        continue

    chunk = ast.get_source_segment(source, node)

    if chunk is None:
        start = node.lineno - 1
        end = getattr(node, "end_lineno", node.lineno)
        chunk = "\n".join(source_lines[start:end])

    function_chunks.append(chunk.rstrip())

CORE_SOURCE.write_text(
    '"""Exact repeat-core functions extracted from 11af.\n\n'
    "Audit artifact only; not yet installed as production code.\n"
    '"""\n\n'
    + "\n\n\n".join(function_chunks)
    + "\n",
    encoding="utf-8",
)

import_rows = []
for node in tree.body:
    if isinstance(node, ast.Import):
        for alias in node.names:
            import_rows.append(
                {
                    "import_type": "import",
                    "module": alias.name,
                    "name": ".",
                    "alias": alias.asname or ".",
                    "line_number": node.lineno,
                }
            )

    elif isinstance(node, ast.ImportFrom):
        module = node.module or "."

        for alias in node.names:
            import_rows.append(
                {
                    "import_type": "from",
                    "module": module,
                    "name": alias.name,
                    "alias": alias.asname or ".",
                    "line_number": node.lineno,
                }
            )

with IMPORTS.open(
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=[
            "import_type",
            "module",
            "name",
            "alias",
            "line_number",
        ],
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(import_rows)

defined_function_names = set(functions)
call_rows = []

for function_name, node in functions.items():
    calls = []

    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue

        called_name = None

        if isinstance(child.func, ast.Name):
            called_name = child.func.id

        elif isinstance(child.func, ast.Attribute):
            parts = []
            cursor = child.func

            while isinstance(cursor, ast.Attribute):
                parts.append(cursor.attr)
                cursor = cursor.value

            if isinstance(cursor, ast.Name):
                parts.append(cursor.id)
                called_name = ".".join(reversed(parts))

        if called_name is not None:
            calls.append(
                (
                    called_name,
                    child.lineno,
                    called_name in defined_function_names,
                )
            )

    for called_name, line_number, internal in sorted(
        set(calls),
        key=lambda item: (
            item[0],
            item[1],
        ),
    ):
        call_rows.append(
            {
                "caller": function_name,
                "callee": called_name,
                "line_number": line_number,
                "internal_function": str(internal).lower(),
            }
        )

with CALL_GRAPH.open(
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=[
            "caller",
            "callee",
            "line_number",
            "internal_function",
        ],
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(call_rows)

run_pair = functions["run_pair"]
run_start = run_pair.lineno
run_end = getattr(
    run_pair,
    "end_lineno",
    run_pair.lineno,
)

relevant_line_numbers = set()
for line_number in range(run_start, run_end + 1):
    line = source_lines[line_number - 1]
    lowered = line.lower()

    if any(term in lowered for term in RELEVANT_TERMS):
        relevant_line_numbers.add(line_number)

expanded = set()
for line_number in relevant_line_numbers:
    expanded.update(
        range(
            max(run_start, line_number - 4),
            min(run_end, line_number + 4) + 1,
        )
    )

merged_ranges = []
for line_number in sorted(expanded):
    if (
        not merged_ranges
        or line_number > merged_ranges[-1][1] + 1
    ):
        merged_ranges.append(
            [line_number, line_number]
        )
    else:
        merged_ranges[-1][1] = line_number

with RUN_PAIR_CONTEXT.open(
    "w",
    encoding="utf-8",
) as handle:
    handle.write(
        "Exact relevant contexts from 11af run_pair()\n"
    )
    handle.write(
        "=========================================\n\n"
    )

    for start, end in merged_ranges:
        handle.write(
            f"----- lines {start}-{end} -----\n"
        )

        for line_number in range(start, end + 1):
            handle.write(
                f"{line_number:05d}: "
                + source_lines[line_number - 1]
                + "\n"
            )

        handle.write("\n")

assignment_rows = []

for node in ast.walk(run_pair):
    targets = []
    value_node = None

    if isinstance(node, ast.Assign):
        targets = node.targets
        value_node = node.value

    elif isinstance(node, ast.AnnAssign):
        targets = [node.target]
        value_node = node.value

    elif isinstance(node, ast.AugAssign):
        targets = [node.target]
        value_node = node.value

    else:
        continue

    target_names = []

    for target in targets:
        if isinstance(target, ast.Name):
            target_names.append(target.id)

        elif isinstance(target, ast.Tuple):
            target_names.extend(
                element.id
                for element in target.elts
                if isinstance(element, ast.Name)
            )

    if not target_names:
        continue

    relevant = any(
        any(term in name.lower() for term in RELEVANT_TERMS)
        for name in target_names
    )

    if not relevant:
        continue

    expression = (
        ast.get_source_segment(source, value_node)
        if value_node is not None
        else None
    )

    assignment_rows.append(
        {
            "line_number": node.lineno,
            "target_names": ";".join(target_names),
            "expression": (
                expression.replace("\n", " ").strip()
                if expression is not None
                else "."
            ),
        }
    )

with ASSIGNMENTS.open(
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=[
            "line_number",
            "target_names",
            "expression",
        ],
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(
        sorted(
            assignment_rows,
            key=lambda row: int(
                row["line_number"]
            ),
        )
    )

with SIZING.open(
    "r",
    encoding="utf-8",
    newline="",
) as handle:
    sizing_rows = list(
        csv.DictReader(handle, delimiter="\t")
    )

positive_rows = [
    row
    for row in sizing_rows
    if (
        row.get("tract_bp") not in {
            None,
            "",
            ".",
            "0",
        }
        or row.get("sizing_status")
        in {
            "partial_internal",
            "lower_bound",
            "exact_span",
        }
    )
]

if positive_rows:
    fields = list(positive_rows[0].keys())
else:
    fields = list(sizing_rows[0].keys())

with POSITIVE.open(
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=fields,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(positive_rows)

external_roots = sorted(
    {
        row["module"].split(".")[0]
        for row in import_rows
        if row["module"].split(".")[0]
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
    }
)

status = "PASS"

if (
    missing_core_functions
    or len(function_chunks) != len(CORE_FUNCTIONS)
    or not merged_ranges
    or not assignment_rows
    or len(positive_rows) != 1
):
    status = "REVIEW"

with QC.open(
    "w",
    encoding="utf-8",
) as handle:
    handle.write("metric\tvalue\n")
    handle.write(
        "core_functions_requested\t{}\n".format(
            len(CORE_FUNCTIONS)
        )
    )
    handle.write(
        "core_functions_extracted\t{}\n".format(
            len(function_chunks)
        )
    )
    handle.write(
        "missing_core_functions\t{}\n".format(
            len(missing_core_functions)
        )
    )
    handle.write(
        "run_pair_context_ranges\t{}\n".format(
            len(merged_ranges)
        )
    )
    handle.write(
        "relevant_run_pair_assignments\t{}\n".format(
            len(assignment_rows)
        )
    )
    handle.write(
        "import_rows\t{}\n".format(
            len(import_rows)
        )
    )
    handle.write(
        "external_import_roots\t{}\n".format(
            len(external_roots)
        )
    )
    handle.write(
        "external_import_names\t{}\n".format(
            ";".join(external_roots)
            if external_roots
            else "."
        )
    )
    handle.write(
        "call_graph_rows\t{}\n".format(
            len(call_rows)
        )
    )
    handle.write(
        "positive_contract_rows\t{}\n".format(
            len(positive_rows)
        )
    )
    handle.write(
        "repeat_core_contract_status\t{}\n".format(
            status
        )
    )

if status != "PASS":
    raise SystemExit(
        "Repeat-core contract extraction requires review"
    )
PY

python -m py_compile "$PY"

rm -f \
  "$CORE_SOURCE" \
  "$RUN_PAIR_CONTEXT" \
  "$IMPORTS" \
  "$CALL_GRAPH" \
  "$ASSIGNMENTS" \
  "$POSITIVE" \
  "$QC" \
  "$MANIFEST"

python "$PY" \
  "$EXTRACTED" \
  "$SIZING" \
  "$CORE_SOURCE" \
  "$RUN_PAIR_CONTEXT" \
  "$IMPORTS" \
  "$CALL_GRAPH" \
  "$ASSIGNMENTS" \
  "$POSITIVE" \
  "$QC"

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in \
      "$IMPORTS" \
      "$CALL_GRAPH" \
      "$ASSIGNMENTS" \
      "$POSITIVE" \
      "$QC"
    do
        printf '%s\t%s\t%s\t%s\t%s\n' \
          "$(basename "$path")" \
          "$(awk 'END {print NR-1}' "$path")" \
          "$(stat -c '%s' "$path")" \
          "$(sha256sum "$path" | awk '{print $1}')" \
          "$path"
    done

    for path in \
      "$CORE_SOURCE" \
      "$RUN_PAIR_CONTEXT"
    do
        printf '%s\t%s\t%s\t%s\t%s\n' \
          "$(basename "$path")" \
          "." \
          "$(stat -c '%s' "$path")" \
          "$(sha256sum "$path" | awk '{print $1}')" \
          "$path"
    done
} > "$MANIFEST"

echo "===== QC ====="
column -ts $'\t' "$QC"

echo
echo "===== IMPORTS ====="
column -ts $'\t' "$IMPORTS"

echo
echo "===== RELEVANT ASSIGNMENTS ====="
column -ts $'\t' "$ASSIGNMENTS"

echo
echo "===== POSITIVE CONTRACT ROW ====="
column -ts $'\t' "$POSITIVE"

echo
echo "===== CORE SOURCE LOCATION ====="
echo "$CORE_SOURCE"

echo
echo "===== RUN_PAIR CONTEXT LOCATION ====="
echo "$RUN_PAIR_CONTEXT"

echo
echo "===== MANIFEST ====="
column -ts $'\t' "$MANIFEST"
