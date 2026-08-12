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
SOURCE_LOG="$PROJECT_ROOT/logs/11af_measure_p3_target_entry_repeat_tracts.log"

OUTDIR="$PROJECT_ROOT/results/11_p3_repeat_parameter_resolution/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_p3_repeat_parameter_resolution/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_p3_repeat_parameter_resolution/$RUN_ID"

OCCURRENCES="$OUTDIR/repeat_parameter_occurrences.tsv"
PYTHON_BINDINGS="$OUTDIR/repeat_parameter_python_bindings.tsv"
ARGV_LAYOUT="$OUTDIR/repeat_parameter_python_argv_layout.tsv"
SHELL_ARGUMENTS="$OUTDIR/repeat_parameter_shell_arguments.tsv"
RESOLUTION="$OUTDIR/repeat_parameter_resolution.tsv"
CONTEXT="$OUTDIR/repeat_parameter_resolution_context.txt"
QC="$QCDIR/repeat_parameter_resolution.qc.tsv"
MANIFEST="$OUTDIR/${RUN_ID}.repeat_parameter_resolution.manifest.tsv"
PY="$WORKDIR/resolve_repeat_parameters.py"

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
    log_path_text,
    occurrences_path_text,
    python_bindings_path_text,
    argv_layout_path_text,
    shell_arguments_path_text,
    resolution_path_text,
    context_path_text,
    qc_path_text,
) = sys.argv[1:]

SHELL_PATH = Path(shell_path_text)
PYTHON_PATH = Path(python_path_text)
LOG_PATH = Path(log_path_text)
OCCURRENCES = Path(occurrences_path_text)
PYTHON_BINDINGS = Path(python_bindings_path_text)
ARGV_LAYOUT = Path(argv_layout_path_text)
SHELL_ARGUMENTS = Path(shell_arguments_path_text)
RESOLUTION = Path(resolution_path_text)
CONTEXT = Path(context_path_text)
QC = Path(qc_path_text)

TARGETS = (
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
log_source = (
    LOG_PATH.read_text(
        encoding="utf-8",
        errors="replace",
    )
    if LOG_PATH.is_file()
    else ""
)

shell_lines = shell_source.splitlines()
python_lines = python_source.splitlines()
log_lines = log_source.splitlines()

tree = ast.parse(
    python_source,
    filename=str(PYTHON_PATH),
)


def source_segment(node: ast.AST) -> str:
    text = ast.get_source_segment(
        python_source,
        node,
    )

    if text is None:
        start = getattr(node, "lineno", 1) - 1
        end = getattr(
            node,
            "end_lineno",
            start + 1,
        )
        text = "\n".join(
            python_lines[start:end]
        )

    return " ".join(text.split())


def target_names(node: ast.AST) -> list[str]:
    names = []

    for child in ast.walk(node):
        if (
            isinstance(child, ast.Name)
            and isinstance(child.ctx, ast.Store)
        ):
            names.append(child.id)

    return names


def is_sys_argv_slice(node: ast.AST) -> bool:
    if not isinstance(node, ast.Subscript):
        return False

    value = node.value

    if not (
        isinstance(value, ast.Attribute)
        and value.attr == "argv"
        and isinstance(value.value, ast.Name)
        and value.value.id == "sys"
    ):
        return False

    slice_node = node.slice

    if isinstance(slice_node, ast.Slice):
        lower = slice_node.lower

        return (
            isinstance(lower, ast.Constant)
            and lower.value == 1
        )

    return False


occurrence_rows = []

for source_name, path, lines in (
    ("shell", SHELL_PATH, shell_lines),
    ("python", PYTHON_PATH, python_lines),
    ("log", LOG_PATH, log_lines),
):
    for line_number, line in enumerate(
        lines,
        start=1,
    ):
        if not any(
            target.lower() in line.lower()
            for target in TARGETS
        ):
            continue

        occurrence_rows.append(
            {
                "source": source_name,
                "path": str(path),
                "line_number": line_number,
                "line": line.strip(),
            }
        )

with OCCURRENCES.open(
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=[
            "source",
            "path",
            "line_number",
            "line",
        ],
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(occurrence_rows)


binding_rows = []
argv_layout_rows = []
argv_name_to_index: dict[str, int] = {}

for node in ast.walk(tree):
    if isinstance(node, ast.Assign):
        names = target_names(node)

        if (
            isinstance(node.targets[0], (ast.Tuple, ast.List))
            and is_sys_argv_slice(node.value)
        ):
            position = 1

            for element in node.targets[0].elts:
                if isinstance(element, ast.Name):
                    argv_name_to_index[
                        element.id
                    ] = position
                    argv_layout_rows.append(
                        {
                            "python_name": element.id,
                            "sys_argv_index": position,
                            "assignment_line": (
                                node.lineno
                            ),
                        }
                    )
                    position += 1
                elif isinstance(
                    element,
                    ast.Starred,
                ):
                    argv_layout_rows.append(
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
                            "assignment_line": (
                                node.lineno
                            ),
                        }
                    )

        relevant = (
            any(
                target in names
                for target in TARGETS
            )
            or any(
                target.lower()
                in source_segment(node).lower()
                for target in TARGETS
            )
        )

        if relevant:
            binding_rows.append(
                {
                    "node_type": "Assign",
                    "line_number": node.lineno,
                    "target_names": (
                        ";".join(names)
                        if names
                        else "."
                    ),
                    "statement": (
                        source_segment(node)
                    ),
                }
            )

    elif isinstance(node, ast.AnnAssign):
        names = target_names(node)

        if any(
            target in names
            for target in TARGETS
        ):
            binding_rows.append(
                {
                    "node_type": "AnnAssign",
                    "line_number": node.lineno,
                    "target_names": (
                        ";".join(names)
                        if names
                        else "."
                    ),
                    "statement": (
                        source_segment(node)
                    ),
                }
            )

    elif isinstance(node, ast.Call):
        segment = source_segment(node)

        if any(
            target.lower() in segment.lower()
            for target in TARGETS
        ):
            binding_rows.append(
                {
                    "node_type": "Call",
                    "line_number": node.lineno,
                    "target_names": ".",
                    "statement": segment,
                }
            )

with PYTHON_BINDINGS.open(
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=[
            "node_type",
            "line_number",
            "target_names",
            "statement",
        ],
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(
        sorted(
            binding_rows,
            key=lambda row: (
                int(row["line_number"]),
                str(row["node_type"]),
            ),
        )
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
    writer.writerows(argv_layout_rows)


def normalized_shell_statements(
    lines: list[str],
) -> list[tuple[int, str]]:
    statements = []
    current = ""
    start_line = 1

    for line_number, line in enumerate(
        lines,
        start=1,
    ):
        stripped = line.rstrip()

        if not current:
            start_line = line_number

        if stripped.endswith("\\"):
            current += stripped[:-1] + " "
            continue

        current += stripped
        statements.append(
            (
                start_line,
                current.strip(),
            )
        )
        current = ""

    if current:
        statements.append(
            (
                start_line,
                current.strip(),
            )
        )

    return statements


shell_statements = normalized_shell_statements(
    shell_lines
)

heredoc_commands = []

for line_number, statement in shell_statements:
    if (
        "<<" not in statement
        or not re.search(
            r"\bpython(?:3)?\b",
            statement,
        )
    ):
        continue

    heredoc_commands.append(
        (
            line_number,
            statement,
        )
    )

selected_command = None

for line_number, statement in heredoc_commands:
    if any(
        target in statement
        for target in TARGETS
    ):
        selected_command = (
            line_number,
            statement,
        )
        break

if selected_command is None and len(
    heredoc_commands
) == 1:
    selected_command = heredoc_commands[0]


def strip_heredoc_suffix(
    statement: str,
) -> str:
    return re.sub(
        r"\s+<<\s*['\"]?[A-Za-z_][A-Za-z0-9_]*['\"]?.*$",
        "",
        statement,
    )


shell_argument_rows = []
shell_tokens: list[str] = []

if selected_command is not None:
    command_line_number, command = (
        selected_command
    )
    command_without_heredoc = (
        strip_heredoc_suffix(command)
    )

    try:
        tokens = shlex.split(
            command_without_heredoc,
            posix=True,
        )
    except ValueError:
        tokens = (
            command_without_heredoc.split()
        )

    dash_index = None

    for index, token in enumerate(tokens):
        if token == "-":
            dash_index = index
            break

    if dash_index is not None:
        shell_tokens = tokens[
            dash_index + 1:
        ]

        for index, token in enumerate(
            shell_tokens,
            start=1,
        ):
            shell_argument_rows.append(
                {
                    "sys_argv_index": index,
                    "shell_token": token,
                    "command_start_line": (
                        command_line_number
                    ),
                }
            )

with SHELL_ARGUMENTS.open(
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=[
            "sys_argv_index",
            "shell_token",
            "command_start_line",
        ],
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(shell_argument_rows)


shell_assignments: dict[str, str] = {}

assignment_pattern = re.compile(
    r"^(?:export\s+|readonly\s+|local\s+)?"
    r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$"
)

for _, statement in shell_statements:
    match = assignment_pattern.match(
        statement
    )

    if not match:
        continue

    name = match.group(1)
    expression = match.group(2).strip()
    shell_assignments[name] = expression


def unquote(text: str) -> str:
    text = text.strip()

    if (
        len(text) >= 2
        and text[0] == text[-1]
        and text[0] in {"'", '"'}
    ):
        return text[1:-1]

    return text


def resolve_shell_expression(
    expression: str,
    seen: set[str] | None = None,
) -> tuple[int | None, str]:
    seen = set() if seen is None else set(seen)
    expression = unquote(expression.strip())

    if re.fullmatch(r"[0-9]+", expression):
        return int(expression), "NUMERIC_LITERAL"

    default_match = re.fullmatch(
        r"\$\{([A-Za-z_][A-Za-z0-9_]*):-([0-9]+)\}",
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
            value, source = resolve_shell_expression(
                shell_assignments[variable],
                seen,
            )

            if value is not None:
                return (
                    value,
                    "SHELL_VARIABLE:"
                    + variable
                    + "->"
                    + source,
                )

        return (
            default,
            "SHELL_DEFAULT:"
            + variable,
        )

    variable_match = re.fullmatch(
        r"\$(?:\{)?([A-Za-z_][A-Za-z0-9_]*)(?:\})?",
        expression,
    )

    if variable_match:
        variable = variable_match.group(1)

        if (
            variable in shell_assignments
            and variable not in seen
        ):
            seen.add(variable)

            return resolve_shell_expression(
                shell_assignments[variable],
                seen,
            )

    return None, "UNRESOLVED_EXPRESSION"


python_assignments: dict[str, ast.AST] = {}

for node in tree.body:
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name):
                python_assignments[
                    target.id
                ] = node.value


def python_name_from_int_call(
    node: ast.AST,
) -> str | None:
    if not (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "int"
        and len(node.args) == 1
    ):
        return None

    argument = node.args[0]

    if isinstance(argument, ast.Name):
        return argument.id

    return None


resolution_rows = []

for target in TARGETS:
    value = None
    resolution_path = []
    python_expression = "."
    argv_index = None
    shell_token = "."

    node = python_assignments.get(target)

    if node is not None:
        python_expression = (
            ast.get_source_segment(
                python_source,
                node,
            )
            or source_segment(node)
        )
        python_expression = " ".join(
            python_expression.split()
        )

        try:
            literal = ast.literal_eval(node)
        except Exception:
            literal = None

        if isinstance(literal, int):
            value = literal
            resolution_path.append(
                "PYTHON_LITERAL"
            )
        else:
            intermediate_name = (
                python_name_from_int_call(node)
            )

            if intermediate_name is not None:
                resolution_path.append(
                    "PYTHON_INT:"
                    + intermediate_name
                )
                argv_index = (
                    argv_name_to_index.get(
                        intermediate_name
                    )
                )

    if argv_index is None:
        argv_index = argv_name_to_index.get(
            target
        )

    if (
        value is None
        and argv_index is not None
        and 1 <= argv_index <= len(
            shell_tokens
        )
    ):
        shell_token = shell_tokens[
            argv_index - 1
        ]
        value, shell_resolution = (
            resolve_shell_expression(
                shell_token
            )
        )
        resolution_path.append(
            "ARGV[{}]:{}->{}".format(
                argv_index,
                shell_token,
                shell_resolution,
            )
        )

    if value is None:
        for name in (
            target,
            "P3_" + target,
        ):
            if name not in shell_assignments:
                continue

            candidate, shell_resolution = (
                resolve_shell_expression(
                    shell_assignments[name]
                )
            )

            if candidate is not None:
                value = candidate
                resolution_path.append(
                    "SHELL_ASSIGNMENT:"
                    + name
                    + "->"
                    + shell_resolution
                )
                break

    resolution_rows.append(
        {
            "parameter": target,
            "resolved_value": (
                value
                if value is not None
                else "."
            ),
            "python_expression": (
                python_expression
            ),
            "sys_argv_index": (
                argv_index
                if argv_index is not None
                else "."
            ),
            "shell_token": shell_token,
            "resolution_path": (
                ";".join(resolution_path)
                if resolution_path
                else "UNRESOLVED"
            ),
            "status": (
                "RESOLVED"
                if value is not None
                else "UNRESOLVED"
            ),
        }
    )

with RESOLUTION.open(
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=[
            "parameter",
            "resolved_value",
            "python_expression",
            "sys_argv_index",
            "shell_token",
            "resolution_path",
            "status",
        ],
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(resolution_rows)

with CONTEXT.open(
    "w",
    encoding="utf-8",
) as handle:
    handle.write(
        "RNA-TR-Scout repeat parameter resolution context\n"
    )
    handle.write(
        "==============================================\n\n"
    )

    handle.write(
        "===== SELECTED PYTHON HEREDOC INVOCATION =====\n"
    )

    if selected_command is None:
        handle.write(
            "No Python heredoc invocation selected.\n"
        )
    else:
        handle.write(
            "start_line={}\n{}\n".format(
                selected_command[0],
                selected_command[1],
            )
        )

    handle.write(
        "\n===== SHELL ASSIGNMENTS CONTAINING TARGET TERMS =====\n"
    )

    for name, expression in sorted(
        shell_assignments.items()
    ):
        if (
            name in TARGETS
            or name in {
                "P3_ENTRY_OFFSET",
                "P3_END_TOLERANCE",
            }
            or any(
                target.lower()
                in expression.lower()
                for target in TARGETS
            )
        ):
            handle.write(
                f"{name}={expression}\n"
            )

    handle.write(
        "\n===== PYTHON TARGET CONTEXT =====\n"
    )

    for target in TARGETS:
        matching_lines = [
            index
            for index, line in enumerate(
                python_lines,
                start=1,
            )
            if target in line
        ]

        for line_number in matching_lines:
            start = max(1, line_number - 4)
            end = min(
                len(python_lines),
                line_number + 4,
            )
            handle.write(
                f"\n--- {target}: lines {start}-{end} ---\n"
            )

            for index in range(
                start,
                end + 1,
            ):
                handle.write(
                    f"{index:05d}: "
                    + python_lines[index - 1]
                    + "\n"
                )

resolved_count = sum(
    row["status"] == "RESOLVED"
    for row in resolution_rows
)
unresolved_count = (
    len(resolution_rows) - resolved_count
)

status = (
    "PASS"
    if resolved_count == len(TARGETS)
    else "REVIEW"
)

with QC.open(
    "w",
    encoding="utf-8",
) as handle:
    handle.write("metric\tvalue\n")
    handle.write(
        "target_parameters\t{}\n".format(
            len(TARGETS)
        )
    )
    handle.write(
        "shell_occurrence_rows\t{}\n".format(
            sum(
                row["source"] == "shell"
                for row in occurrence_rows
            )
        )
    )
    handle.write(
        "python_occurrence_rows\t{}\n".format(
            sum(
                row["source"] == "python"
                for row in occurrence_rows
            )
        )
    )
    handle.write(
        "log_occurrence_rows\t{}\n".format(
            sum(
                row["source"] == "log"
                for row in occurrence_rows
            )
        )
    )
    handle.write(
        "python_binding_rows\t{}\n".format(
            len(binding_rows)
        )
    )
    handle.write(
        "python_argv_layout_rows\t{}\n".format(
            len(argv_layout_rows)
        )
    )
    handle.write(
        "shell_argument_rows\t{}\n".format(
            len(shell_argument_rows)
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

    for row in resolution_rows:
        handle.write(
            "{}\t{}\n".format(
                row["parameter"].lower(),
                row["resolved_value"],
            )
        )

    handle.write(
        "parameter_resolution_status\t{}\n".format(
            status
        )
    )
PY

python -m py_compile "$PY"

rm -f \
  "$OCCURRENCES" \
  "$PYTHON_BINDINGS" \
  "$ARGV_LAYOUT" \
  "$SHELL_ARGUMENTS" \
  "$RESOLUTION" \
  "$CONTEXT" \
  "$QC" \
  "$MANIFEST"

python "$PY" \
  "$SOURCE_SCRIPT" \
  "$EXTRACTED" \
  "$SOURCE_LOG" \
  "$OCCURRENCES" \
  "$PYTHON_BINDINGS" \
  "$ARGV_LAYOUT" \
  "$SHELL_ARGUMENTS" \
  "$RESOLUTION" \
  "$CONTEXT" \
  "$QC"

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in \
      "$OCCURRENCES" \
      "$PYTHON_BINDINGS" \
      "$ARGV_LAYOUT" \
      "$SHELL_ARGUMENTS" \
      "$RESOLUTION" \
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
echo "===== PARAMETER RESOLUTION ====="
column -ts $'\t' "$RESOLUTION"

echo
echo "===== PYTHON ARGV LAYOUT ====="
column -ts $'\t' "$ARGV_LAYOUT"

echo
echo "===== SHELL ARGUMENTS ====="
column -ts $'\t' "$SHELL_ARGUMENTS"

echo
echo "===== TARGET OCCURRENCES ====="
column -ts $'\t' "$OCCURRENCES"

echo
echo "===== CONTEXT LOCATION ====="
echo "$CONTEXT"

echo
echo "===== MANIFEST ====="
column -ts $'\t' "$MANIFEST"
