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
EXTRACTED="$PROJECT_ROOT/tmp/11_p3_repeat_contract_audit/$RUN_ID/11af_embedded_python.py"

OUTDIR="$PROJECT_ROOT/results/11_p3_repeat_parameter_resolution_v2/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_p3_repeat_parameter_resolution_v2/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_p3_repeat_parameter_resolution_v2/$RUN_ID"

INVOCATIONS="$OUTDIR/python_invocations_outside_heredocs.tsv"
ASSIGNMENTS="$OUTDIR/shell_assignments_outside_heredocs.tsv"
ARGV_LAYOUT="$OUTDIR/python_argv_layout.tsv"
MAPPING="$OUTDIR/repeat_parameter_argv_mapping.tsv"
CONTEXT="$OUTDIR/repeat_parameter_resolution_v2_context.txt"
QC="$QCDIR/repeat_parameter_resolution_v2.qc.tsv"
MANIFEST="$OUTDIR/${RUN_ID}.repeat_parameter_resolution_v2.manifest.tsv"
PY="$WORKDIR/resolve_repeat_parameters_v2.py"

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR"

for path in "$SOURCE_SCRIPT" "$EXTRACTED"; do
    test -e "$path" || {
        echo "ERROR: missing required path: $path" >&2
        exit 1
    }
done

cat > "$PY" <<'PY'
from __future__ import annotations

import ast
import csv
import re
import shlex
import sys
from pathlib import Path

(
    shell_path_text,
    python_path_text,
    invocations_path_text,
    assignments_path_text,
    argv_layout_path_text,
    mapping_path_text,
    context_path_text,
    qc_path_text,
) = sys.argv[1:]

SHELL_PATH = Path(shell_path_text)
PYTHON_PATH = Path(python_path_text)
INVOCATIONS = Path(invocations_path_text)
ASSIGNMENTS = Path(assignments_path_text)
ARGV_LAYOUT = Path(argv_layout_path_text)
MAPPING = Path(mapping_path_text)
CONTEXT = Path(context_path_text)
QC = Path(qc_path_text)

TARGET_CONSTANTS = (
    "ENTRY_OFFSET",
    "END_TOLERANCE",
)

shell_source = SHELL_PATH.read_text(
    encoding="utf-8",
    errors="replace",
)
python_source = PYTHON_PATH.read_text(
    encoding="utf-8",
    errors="replace",
)
shell_lines = shell_source.splitlines()
python_tree = ast.parse(
    python_source,
    filename=str(PYTHON_PATH),
)


def strip_heredoc_bodies(
    lines: list[str],
) -> tuple[list[tuple[int, str]], list[tuple[int, int, str]]]:
    """Return shell lines outside heredoc bodies and skipped ranges."""

    kept: list[tuple[int, str]] = []
    skipped: list[tuple[int, int, str]] = []
    active_marker: str | None = None
    heredoc_start: int | None = None

    marker_pattern = re.compile(
        r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1"
    )

    for line_number, line in enumerate(lines, start=1):
        if active_marker is not None:
            if line.strip() == active_marker:
                skipped.append(
                    (
                        heredoc_start or line_number,
                        line_number,
                        active_marker,
                    )
                )
                active_marker = None
                heredoc_start = None
            continue

        kept.append((line_number, line))
        match = marker_pattern.search(line)

        if match:
            active_marker = match.group(2)
            heredoc_start = line_number + 1

    if active_marker is not None:
        skipped.append(
            (
                heredoc_start or len(lines),
                len(lines),
                active_marker,
            )
        )

    return kept, skipped


def join_shell_statements(
    numbered_lines: list[tuple[int, str]],
) -> list[tuple[int, int, str]]:
    statements: list[tuple[int, int, str]] = []
    buffer: list[str] = []
    start_line: int | None = None
    end_line: int | None = None

    for line_number, line in numbered_lines:
        stripped = line.rstrip()

        if start_line is None:
            start_line = line_number

        end_line = line_number

        if stripped.endswith("\\"):
            buffer.append(stripped[:-1])
            continue

        buffer.append(stripped)
        statement = " ".join(
            part.strip()
            for part in buffer
        ).strip()

        if statement:
            statements.append(
                (
                    start_line,
                    end_line,
                    statement,
                )
            )

        buffer = []
        start_line = None
        end_line = None

    if buffer:
        statements.append(
            (
                start_line or 1,
                end_line or start_line or 1,
                " ".join(buffer).strip(),
            )
        )

    return statements


outside_lines, skipped_heredocs = strip_heredoc_bodies(
    shell_lines
)
statements = join_shell_statements(outside_lines)

assignment_pattern = re.compile(
    r"^(?:export\s+|readonly\s+|local\s+)?"
    r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)$"
)

shell_assignments: dict[str, str] = {}
assignment_rows: list[dict[str, object]] = []

for start_line, end_line, statement in statements:
    match = assignment_pattern.match(statement)

    if not match:
        continue

    name = match.group(1)
    expression = match.group(2).strip()

    # Exclude compound shell syntax accidentally matched as assignment.
    if name in {"if", "for", "while", "case"}:
        continue

    shell_assignments[name] = expression
    assignment_rows.append(
        {
            "name": name,
            "expression": expression,
            "start_line": start_line,
            "end_line": end_line,
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
            "name",
            "expression",
            "start_line",
            "end_line",
        ],
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(assignment_rows)


def parse_python_argv_layout(
    tree: ast.Module,
) -> tuple[list[dict[str, object]], dict[str, int]]:
    rows: list[dict[str, object]] = []
    name_to_index: dict[str, int] = {}

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue

        if len(node.targets) != 1:
            continue

        target = node.targets[0]

        if not isinstance(target, (ast.Tuple, ast.List)):
            continue

        value = node.value

        if not isinstance(value, ast.Subscript):
            continue

        base = value.value

        if not (
            isinstance(base, ast.Attribute)
            and base.attr == "argv"
            and isinstance(base.value, ast.Name)
            and base.value.id == "sys"
        ):
            continue

        slice_node = value.slice

        if not (
            isinstance(slice_node, ast.Slice)
            and isinstance(slice_node.lower, ast.Constant)
            and slice_node.lower.value == 1
        ):
            continue

        index = 1

        for element in target.elts:
            if isinstance(element, ast.Name):
                name_to_index[element.id] = index
                rows.append(
                    {
                        "python_name": element.id,
                        "sys_argv_index": index,
                        "assignment_line": node.lineno,
                    }
                )
                index += 1

            elif isinstance(element, ast.Starred):
                rows.append(
                    {
                        "python_name": (
                            "*"
                            + getattr(
                                element.value,
                                "id",
                                "unknown",
                            )
                        ),
                        "sys_argv_index": ".",
                        "assignment_line": node.lineno,
                    }
                )

    return rows, name_to_index


argv_rows, argv_name_to_index = (
    parse_python_argv_layout(python_tree)
)

with ARGV_LAYOUT.open(
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=[
            "python_name",
            "sys_argv_index",
            "assignment_line",
        ],
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(argv_rows)


def python_intermediate_name(
    constant_name: str,
) -> tuple[str | None, str]:
    for node in python_tree.body:
        if not isinstance(node, ast.Assign):
            continue

        target_names = [
            target.id
            for target in node.targets
            if isinstance(target, ast.Name)
        ]

        if constant_name not in target_names:
            continue

        expression = (
            ast.get_source_segment(
                python_source,
                node.value,
            )
            or ""
        )

        if (
            isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id in {"int", "float"}
            and len(node.value.args) == 1
            and isinstance(node.value.args[0], ast.Name)
        ):
            return (
                node.value.args[0].id,
                " ".join(expression.split()),
            )

        return None, " ".join(expression.split())

    return None, "."


target_python_bindings = {}
for constant in TARGET_CONSTANTS:
    intermediate, expression = (
        python_intermediate_name(constant)
    )
    target_python_bindings[constant] = {
        "intermediate": intermediate,
        "expression": expression,
        "argv_index": (
            argv_name_to_index.get(intermediate)
            if intermediate is not None
            else argv_name_to_index.get(constant)
        ),
    }


def find_python_token_index(tokens: list[str]) -> int | None:
    for index, token in enumerate(tokens):
        basename = Path(token).name

        if basename in {"python", "python3"}:
            return index

    return None


def stop_at_shell_operator(tokens: list[str]) -> list[str]:
    output = []

    for token in tokens:
        if token in {
            "|",
            "||",
            "&&",
            ";",
            "&",
        }:
            break

        if token.startswith(
            (
                ">",
                "1>",
                "2>",
                "&>",
            )
        ):
            break

        output.append(token)

    return output


invocation_rows: list[dict[str, object]] = []
parsed_invocations: list[dict[str, object]] = []

for start_line, end_line, statement in statements:
    if not re.search(
        r"(^|\s)(?:[^/\s]*/)?python3?(?:\s|$)",
        statement,
    ):
        continue

    try:
        tokens = shlex.split(statement, posix=True)
    except ValueError:
        tokens = statement.split()

    python_index = find_python_token_index(tokens)

    if (
        python_index is None
        or python_index + 1 >= len(tokens)
    ):
        continue

    script_token = tokens[python_index + 1]
    argument_tokens = stop_at_shell_operator(
        tokens[python_index + 2:]
    )

    score = 0
    maximum_required_index = max(
        int(binding["argv_index"])
        for binding in target_python_bindings.values()
        if binding["argv_index"] is not None
    )

    if len(argument_tokens) >= maximum_required_index:
        score += 100

    if script_token in {
        "$PY",
        "${PY}",
    }:
        score += 50

    if "11af" in statement or "target_entry" in statement:
        score += 20

    for token in argument_tokens:
        if any(
            target.lower() in token.lower()
            for target in TARGET_CONSTANTS
        ):
            score += 10

    parsed = {
        "start_line": start_line,
        "end_line": end_line,
        "statement": statement,
        "script_token": script_token,
        "argument_tokens": argument_tokens,
        "argument_count": len(argument_tokens),
        "score": score,
    }
    parsed_invocations.append(parsed)

    invocation_rows.append(
        {
            "start_line": start_line,
            "end_line": end_line,
            "script_token": script_token,
            "argument_count": len(argument_tokens),
            "score": score,
            "statement": statement,
        }
    )

with INVOCATIONS.open(
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=[
            "start_line",
            "end_line",
            "script_token",
            "argument_count",
            "score",
            "statement",
        ],
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(invocation_rows)

selected = (
    max(
        parsed_invocations,
        key=lambda row: (
            int(row["score"]),
            int(row["argument_count"]),
        ),
    )
    if parsed_invocations
    else None
)


def remove_outer_quotes(expression: str) -> str:
    expression = expression.strip()

    if (
        len(expression) >= 2
        and expression[0] == expression[-1]
        and expression[0] in {"'", '"'}
    ):
        return expression[1:-1]

    return expression


def resolve_expression(
    expression: str,
    seen: set[str] | None = None,
) -> tuple[int | None, str]:
    seen = set() if seen is None else set(seen)
    expression = remove_outer_quotes(expression)

    if re.fullmatch(r"[0-9]+", expression):
        return int(expression), "NUMERIC_LITERAL"

    default_match = re.fullmatch(
        r"\$\{([A-Za-z_][A-Za-z0-9_]*):?-([0-9]+)\}",
        expression,
    )

    if default_match:
        variable = default_match.group(1)
        default = int(default_match.group(2))

        if (
            variable in shell_assignments
            and variable not in seen
        ):
            seen.add(variable)
            value, path = resolve_expression(
                shell_assignments[variable],
                seen,
            )

            if value is not None:
                return (
                    value,
                    f"{variable}->{path}",
                )

        return (
            default,
            f"DEFAULT({variable})",
        )

    variable_match = re.fullmatch(
        r"\$(?:\{)?([A-Za-z_][A-Za-z0-9_]*)(?:\})?",
        expression,
    )

    if variable_match:
        variable = variable_match.group(1)

        if variable in seen:
            return None, f"CYCLE({variable})"

        if variable not in shell_assignments:
            return None, f"UNBOUND({variable})"

        seen.add(variable)
        value, path = resolve_expression(
            shell_assignments[variable],
            seen,
        )

        return (
            value,
            f"{variable}->{path}",
        )

    arithmetic_match = re.fullmatch(
        r"\$\(\(([0-9+\-*/% ()]+)\)\)",
        expression,
    )

    if arithmetic_match:
        arithmetic = arithmetic_match.group(1)

        if not re.fullmatch(
            r"[0-9+\-*/% ()]+",
            arithmetic,
        ):
            return None, "UNSAFE_ARITHMETIC"

        try:
            value = eval(
                arithmetic,
                {"__builtins__": {}},
                {},
            )
        except Exception:
            return None, "ARITHMETIC_ERROR"

        if isinstance(value, int):
            return value, "SHELL_ARITHMETIC"

    return None, f"UNRESOLVED({expression})"


mapping_rows: list[dict[str, object]] = []

for constant in TARGET_CONSTANTS:
    binding = target_python_bindings[constant]
    argv_index = binding["argv_index"]
    shell_token = "."
    resolved_value = None
    resolution_path = "NO_SELECTED_INVOCATION"

    if (
        selected is not None
        and argv_index is not None
        and 1 <= int(argv_index)
        <= len(selected["argument_tokens"])
    ):
        shell_token = selected["argument_tokens"][
            int(argv_index) - 1
        ]
        resolved_value, resolution_path = (
            resolve_expression(shell_token)
        )

    mapping_rows.append(
        {
            "parameter": constant,
            "python_expression": (
                binding["expression"]
            ),
            "python_intermediate_name": (
                binding["intermediate"] or "."
            ),
            "sys_argv_index": (
                argv_index
                if argv_index is not None
                else "."
            ),
            "selected_shell_token": shell_token,
            "resolved_value": (
                resolved_value
                if resolved_value is not None
                else "."
            ),
            "resolution_path": resolution_path,
            "status": (
                "RESOLVED"
                if resolved_value is not None
                else "UNRESOLVED"
            ),
        }
    )

with MAPPING.open(
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=[
            "parameter",
            "python_expression",
            "python_intermediate_name",
            "sys_argv_index",
            "selected_shell_token",
            "resolved_value",
            "resolution_path",
            "status",
        ],
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(mapping_rows)

with CONTEXT.open(
    "w",
    encoding="utf-8",
) as handle:
    handle.write(
        "RNA-TR-Scout repeat parameter resolution v2\n"
    )
    handle.write(
        "==========================================\n\n"
    )
    handle.write(
        "heredoc_bodies_skipped={}\n".format(
            len(skipped_heredocs)
        )
    )
    handle.write(
        "shell_statements_outside_heredocs={}\n".format(
            len(statements)
        )
    )
    handle.write(
        "python_invocations_found={}\n\n".format(
            len(parsed_invocations)
        )
    )

    handle.write(
        "===== SKIPPED HEREDOC RANGES =====\n"
    )
    for start, end, marker in skipped_heredocs:
        handle.write(
            f"{start}-{end}\t{marker}\n"
        )

    handle.write(
        "\n===== SELECTED PYTHON INVOCATION =====\n"
    )
    if selected is None:
        handle.write("NONE\n")
    else:
        handle.write(
            "start_line={}\nend_line={}\n"
            "script_token={}\nargument_count={}\n"
            "score={}\nstatement={}\n".format(
                selected["start_line"],
                selected["end_line"],
                selected["script_token"],
                selected["argument_count"],
                selected["score"],
                selected["statement"],
            )
        )
        handle.write("\nargv mapping:\n")

        for index, token in enumerate(
            selected["argument_tokens"],
            start=1,
        ):
            python_names = [
                row["python_name"]
                for row in argv_rows
                if row["sys_argv_index"] == index
            ]
            handle.write(
                "{}\t{}\t{}\n".format(
                    index,
                    ";".join(python_names) or ".",
                    token,
                )
            )

    handle.write(
        "\n===== RELEVANT SHELL ASSIGNMENTS =====\n"
    )
    relevant_names = set()

    for row in mapping_rows:
        token = str(row["selected_shell_token"])
        match = re.fullmatch(
            r"\$(?:\{)?([A-Za-z_][A-Za-z0-9_]*)(?:\})?",
            token,
        )

        if match:
            relevant_names.add(match.group(1))

    for name in sorted(relevant_names):
        handle.write(
            "{}={}\n".format(
                name,
                shell_assignments.get(
                    name,
                    "<UNBOUND>",
                ),
            )
        )

resolved_count = sum(
    row["status"] == "RESOLVED"
    for row in mapping_rows
)
unresolved_count = (
    len(mapping_rows) - resolved_count
)

status = (
    "PASS"
    if resolved_count == len(TARGET_CONSTANTS)
    else "REVIEW"
)

with QC.open(
    "w",
    encoding="utf-8",
) as handle:
    handle.write("metric\tvalue\n")
    handle.write(
        "heredoc_bodies_skipped\t{}\n".format(
            len(skipped_heredocs)
        )
    )
    handle.write(
        "shell_statements_outside_heredocs\t{}\n".format(
            len(statements)
        )
    )
    handle.write(
        "python_invocations_found\t{}\n".format(
            len(parsed_invocations)
        )
    )
    handle.write(
        "selected_invocation_present\t{}\n".format(
            str(selected is not None).lower()
        )
    )
    handle.write(
        "selected_invocation_argument_count\t{}\n".format(
            selected["argument_count"]
            if selected is not None
            else 0
        )
    )
    handle.write(
        "python_argv_layout_rows\t{}\n".format(
            len(argv_rows)
        )
    )
    handle.write(
        "resolved_parameters\t{}\n".format(
            resolved_count
        )
    )
    handle.write(
        "unresolved_parameters\t{}\n".format(
            unresolved_count
        )
    )

    for row in mapping_rows:
        handle.write(
            "{}\t{}\n".format(
                str(row["parameter"]).lower(),
                row["resolved_value"],
            )
        )

    handle.write(
        "parameter_resolution_v2_status\t{}\n".format(
            status
        )
    )
PY

python -m py_compile "$PY"

rm -f \
  "$INVOCATIONS" \
  "$ASSIGNMENTS" \
  "$ARGV_LAYOUT" \
  "$MAPPING" \
  "$CONTEXT" \
  "$QC" \
  "$MANIFEST"

python "$PY" \
  "$SOURCE_SCRIPT" \
  "$EXTRACTED" \
  "$INVOCATIONS" \
  "$ASSIGNMENTS" \
  "$ARGV_LAYOUT" \
  "$MAPPING" \
  "$CONTEXT" \
  "$QC"

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in \
      "$INVOCATIONS" \
      "$ASSIGNMENTS" \
      "$ARGV_LAYOUT" \
      "$MAPPING" \
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
      "$(basename "$CONTEXT")" \
      "." \
      "$(stat -c '%s' "$CONTEXT")" \
      "$(sha256sum "$CONTEXT" | awk '{print $1}')" \
      "$CONTEXT"
} > "$MANIFEST"

echo "===== QC ====="
column -ts $'\t' "$QC"

echo
echo "===== PARAMETER MAPPING ====="
column -ts $'\t' "$MAPPING"

echo
echo "===== PYTHON INVOCATIONS ====="
column -ts $'\t' "$INVOCATIONS"

echo
echo "===== RELEVANT CONTEXT ====="
cat "$CONTEXT"

echo
echo "===== MANIFEST ====="
column -ts $'\t' "$MANIFEST"
