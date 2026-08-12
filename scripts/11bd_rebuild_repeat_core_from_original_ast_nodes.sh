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
CORE_FUNCTIONS="$PROJECT_ROOT/results/11_p3_repeat_core_contract/$RUN_ID/p3_repeat_core_functions.py"
SIZING="$PROJECT_ROOT/results/11_p3_target_entry_sizing/$RUN_ID/p3_target_entry_repeat_evidence.tsv"
QUERY_FASTA="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_p3_bridge_feasibility/p3_bridge_queries.fasta.gz"

OUTDIR="$PROJECT_ROOT/results/11_p3_repeat_core_validation_v5/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_p3_repeat_core_validation_v5/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_p3_repeat_core_validation_v5/$RUN_ID"

CANDIDATE_MODULE="$OUTDIR/p3_repeat_core_candidate.v5.py"
ARGUMENTS="$OUTDIR/p3_repeat_resolved_arguments.v5.tsv"
DEPENDENCIES="$OUTDIR/p3_repeat_ast_dependencies.v5.tsv"
REPLAY="$OUTDIR/p3_repeat_positive_case_replay.v5.tsv"
ERROR_REPORT="$OUTDIR/p3_repeat_core_validation_v5.error.txt"
QC="$QCDIR/p3_repeat_core_positive_validation_v5.qc.tsv"
MANIFEST="$OUTDIR/${RUN_ID}.p3_repeat_core_positive_validation_v5.manifest.tsv"
PY="$WORKDIR/validate_repeat_core_v5.py"

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR"

for path in \
  "$SOURCE_SCRIPT" \
  "$EXTRACTED" \
  "$CORE_FUNCTIONS" \
  "$SIZING" \
  "$QUERY_FASTA"
do
    test -e "$path" || {
        echo "ERROR: missing required path: $path" >&2
        exit 1
    }
done

cat > "$PY" <<'PY'
from __future__ import annotations

import ast
import builtins
import copy
import csv
import gzip
import re
import shlex
import sys
import traceback
from pathlib import Path

(
    source_script_text,
    extracted_text,
    core_functions_text,
    sizing_text,
    query_fasta_text,
    candidate_module_text,
    arguments_text,
    dependencies_text,
    replay_text,
    error_report_text,
    qc_text,
) = sys.argv[1:]

SOURCE_SCRIPT = Path(source_script_text)
EXTRACTED = Path(extracted_text)
CORE_FUNCTIONS = Path(core_functions_text)
SIZING = Path(sizing_text)
QUERY_FASTA = Path(query_fasta_text)
CANDIDATE_MODULE = Path(candidate_module_text)
ARGUMENTS = Path(arguments_text)
DEPENDENCIES = Path(dependencies_text)
REPLAY = Path(replay_text)
ERROR_REPORT = Path(error_report_text)
QC = Path(qc_text)

COMPARISON_FIELDS = [
    "tract_oriented_start",
    "tract_oriented_end",
    "tract_raw_start",
    "tract_raw_end",
    "tract_bp",
    "repeat_units_observed_read",
    "repeat_units_motif_path",
    "motif_path_to_read_units_ratio",
    "matches",
    "mismatches",
    "insertions",
    "deletions",
    "purity",
    "score",
    "selected_orientation",
    "entry_offset_selected_bp",
    "distance_from_tract_to_oriented_clip_end_bp",
    "tract_reaches_expected_raw_end",
    "evidence_class",
    "sizing_status",
]

metrics: dict[str, object] = {
    "source_strategy": (
        "ORIGINAL_REQUIRED_AST_NODES_PLUS_FROZEN_ARGV_CONSTANTS"
    ),
    "comparison_fields_expected": len(COMPARISON_FIELDS),
    "validation_error_type": ".",
    "validation_error_message": ".",
}


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        return list(
            csv.DictReader(handle, delimiter="\t")
        )


def write_tsv(
    path: Path,
    fieldnames: list[str],
    rows: list[dict[str, object]],
) -> None:
    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def load_fasta(path: Path) -> dict[str, str]:
    records: dict[str, str] = {}
    opener = gzip.open if path.suffix == ".gz" else open

    with opener(
        path,
        "rt",
        encoding="utf-8",
    ) as handle:
        record_id: str | None = None
        parts: list[str] = []

        for line_number, line in enumerate(
            handle,
            start=1,
        ):
            line = line.strip()

            if not line:
                continue

            if line.startswith(">"):
                if record_id is not None:
                    if record_id in records:
                        raise ValueError(
                            f"duplicate FASTA ID: {record_id}"
                        )

                    records[record_id] = "".join(parts).upper()

                record_id = line[1:].split()[0]

                if not record_id:
                    raise ValueError(
                        f"empty FASTA ID at line {line_number}"
                    )

                parts = []
                continue

            if record_id is None:
                raise ValueError(
                    "FASTA sequence before first header"
                )

            parts.append(line)

        if record_id is not None:
            if record_id in records:
                raise ValueError(
                    f"duplicate FASTA ID: {record_id}"
                )

            records[record_id] = "".join(parts).upper()

    return records


def strip_heredoc_bodies(
    lines: list[str],
) -> list[tuple[int, str]]:
    kept: list[tuple[int, str]] = []
    active_marker: str | None = None
    marker_pattern = re.compile(
        r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1"
    )

    for line_number, line in enumerate(lines, start=1):
        if active_marker is not None:
            if line.strip() == active_marker:
                active_marker = None
            continue

        kept.append((line_number, line))
        match = marker_pattern.search(line)

        if match:
            active_marker = match.group(2)

    return kept


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

    return statements


def parse_argv_layout(
    module: ast.Module,
) -> dict[str, int]:
    layout: dict[str, int] = {}

    for node in ast.walk(module):
        if not isinstance(node, ast.Assign):
            continue

        if len(node.targets) != 1:
            continue

        target = node.targets[0]
        value = node.value

        if not isinstance(target, (ast.Tuple, ast.List)):
            continue

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
            and isinstance(
                slice_node.lower,
                ast.Constant,
            )
            and slice_node.lower.value == 1
        ):
            continue

        index = 1

        for element in target.elts:
            if isinstance(element, ast.Name):
                layout[element.id] = index
                index += 1

    return layout


def stop_at_shell_operator(
    tokens: list[str],
) -> list[str]:
    output: list[str] = []

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


def select_python_invocation(
    statements: list[tuple[int, int, str]],
    required_argument_count: int,
) -> dict[str, object]:
    candidates: list[dict[str, object]] = []

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

        python_index = None

        for index, token in enumerate(tokens):
            if Path(token).name in {
                "python",
                "python3",
            }:
                python_index = index
                break

        if (
            python_index is None
            or python_index + 1 >= len(tokens)
        ):
            continue

        script_token = tokens[python_index + 1]
        arguments = stop_at_shell_operator(
            tokens[python_index + 2:]
        )
        score = len(arguments)

        if script_token in {
            "$PY",
            "${PY}",
        }:
            score += 100

        if len(arguments) >= required_argument_count:
            score += 100

        candidates.append(
            {
                "start_line": start_line,
                "end_line": end_line,
                "script_token": script_token,
                "arguments": arguments,
                "score": score,
            }
        )

    if not candidates:
        raise ValueError(
            "no Python invocation found outside heredoc bodies"
        )

    return max(
        candidates,
        key=lambda row: (
            int(row["score"]),
            len(row["arguments"]),
        ),
    )


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
    assignments: dict[str, str],
    seen: set[str] | None = None,
) -> tuple[object | None, str]:
    seen = set() if seen is None else set(seen)
    expression = unquote(expression)

    if re.fullmatch(
        r"[+-]?[0-9]+",
        expression,
    ):
        return int(expression), "INTEGER_LITERAL"

    if re.fullmatch(
        r"[+-]?(?:[0-9]+\.[0-9]*|\.[0-9]+)",
        expression,
    ):
        return float(expression), "FLOAT_LITERAL"

    variable_match = re.fullmatch(
        r"\$(?:\{)?([A-Za-z_][A-Za-z0-9_]*)(?:\})?",
        expression,
    )

    if variable_match:
        variable = variable_match.group(1)

        if variable in seen:
            return None, f"CYCLE({variable})"

        if variable not in assignments:
            return None, f"UNBOUND({variable})"

        seen.add(variable)
        value, route = resolve_shell_expression(
            assignments[variable],
            assignments,
            seen,
        )
        return value, f"{variable}->{route}"

    default_match = re.fullmatch(
        r"\$\{([A-Za-z_][A-Za-z0-9_]*):-"
        r"([+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+))\}",
        expression,
    )

    if default_match:
        variable = default_match.group(1)
        default_text = default_match.group(2)

        if (
            variable in assignments
            and variable not in seen
        ):
            seen.add(variable)
            value, route = resolve_shell_expression(
                assignments[variable],
                assignments,
                seen,
            )

            if value is not None:
                return value, f"{variable}->{route}"

        default_value: int | float

        if "." in default_text:
            default_value = float(default_text)
        else:
            default_value = int(default_text)

        return default_value, f"DEFAULT({variable})"

    return expression, "STRING_OR_EXPRESSION"


def assigned_top_level_names(
    node: ast.AST,
) -> set[str]:
    names: set[str] = set()

    if isinstance(node, ast.Assign):
        targets = node.targets

    elif isinstance(node, ast.AnnAssign):
        targets = [node.target]

    elif isinstance(
        node,
        (ast.FunctionDef, ast.ClassDef),
    ):
        names.add(node.name)
        return names

    elif isinstance(node, ast.Import):
        for alias in node.names:
            names.add(
                alias.asname
                or alias.name.split(".")[0]
            )
        return names

    elif isinstance(node, ast.ImportFrom):
        for alias in node.names:
            names.add(alias.asname or alias.name)
        return names

    else:
        return names

    for target in targets:
        for child in ast.walk(target):
            if (
                isinstance(child, ast.Name)
                and isinstance(child.ctx, ast.Store)
            ):
                names.add(child.id)

    return names


def loaded_names(
    node: ast.AST,
) -> set[str]:
    return {
        child.id
        for child in ast.walk(node)
        if (
            isinstance(child, ast.Name)
            and isinstance(child.ctx, ast.Load)
        )
    }


def contains_sys_argv(
    node: ast.AST,
) -> bool:
    for child in ast.walk(node):
        if not isinstance(child, ast.Attribute):
            continue

        if (
            child.attr == "argv"
            and isinstance(child.value, ast.Name)
            and child.value.id == "sys"
        ):
            return True

    return False


def function_global_names(
    functions: list[ast.FunctionDef],
) -> set[str]:
    loaded: set[str] = set()
    locally_bound: set[str] = set()
    function_names = {
        function.name
        for function in functions
    }

    for function in functions:
        locally_bound.update(
            argument.arg
            for argument in (
                list(function.args.posonlyargs)
                + list(function.args.args)
                + list(function.args.kwonlyargs)
            )
        )

        if function.args.vararg is not None:
            locally_bound.add(function.args.vararg.arg)

        if function.args.kwarg is not None:
            locally_bound.add(function.args.kwarg.arg)

        for child in ast.walk(function):
            if isinstance(child, ast.Name):
                if isinstance(child.ctx, ast.Load):
                    loaded.add(child.id)
                elif isinstance(
                    child.ctx,
                    (ast.Store, ast.Del),
                ):
                    locally_bound.add(child.id)

    return (
        loaded
        - locally_bound
        - function_names
        - set(dir(builtins))
    )


def runtime_literal_from_assignment(
    node: ast.AST,
    resolved_arguments: dict[str, object],
) -> tuple[bool, object | None, str]:
    if isinstance(node, ast.Assign):
        value_node = node.value
    elif isinstance(node, ast.AnnAssign):
        value_node = node.value
    else:
        return False, None, "NOT_ASSIGNMENT"

    if not (
        isinstance(value_node, ast.Call)
        and isinstance(value_node.func, ast.Name)
        and value_node.func.id in {
            "int",
            "float",
            "str",
        }
        and len(value_node.args) == 1
        and not value_node.keywords
        and isinstance(value_node.args[0], ast.Name)
    ):
        return False, None, "NOT_ARGV_CONVERSION"

    intermediate_name = value_node.args[0].id

    if intermediate_name not in resolved_arguments:
        return (
            False,
            None,
            f"UNRESOLVED_INTERMEDIATE:{intermediate_name}",
        )

    raw_value = resolved_arguments[
        intermediate_name
    ]

    if value_node.func.id == "int":
        value = int(raw_value)
    elif value_node.func.id == "float":
        value = float(raw_value)
    else:
        value = str(raw_value)

    return (
        True,
        value,
        f"FROZEN_FROM:{intermediate_name}",
    )


def main() -> str:
    shell_source = SOURCE_SCRIPT.read_text(
        encoding="utf-8",
        errors="replace",
    )
    extracted_source = EXTRACTED.read_text(
        encoding="utf-8",
        errors="replace",
    )
    core_source = CORE_FUNCTIONS.read_text(
        encoding="utf-8",
        errors="replace",
    )

    extracted_tree = ast.parse(
        extracted_source,
        filename=str(EXTRACTED),
    )
    core_tree = ast.parse(
        core_source,
        filename=str(CORE_FUNCTIONS),
    )

    core_functions = [
        copy.deepcopy(node)
        for node in core_tree.body
        if isinstance(node, ast.FunctionDef)
    ]

    if len(core_functions) != 8:
        raise ValueError(
            "expected 8 core functions; "
            f"observed {len(core_functions)}"
        )

    metrics["core_functions_loaded"] = len(
        core_functions
    )

    argv_layout = parse_argv_layout(
        extracted_tree
    )

    if len(argv_layout) != 23:
        raise ValueError(
            "expected 23 argv bindings; "
            f"observed {len(argv_layout)}"
        )

    metrics[
        "python_argv_layout_rows"
    ] = len(argv_layout)

    outside_lines = strip_heredoc_bodies(
        shell_source.splitlines()
    )
    statements = join_shell_statements(
        outside_lines
    )

    assignment_pattern = re.compile(
        r"^(?:export\s+|readonly\s+|local\s+)?"
        r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)$"
    )
    shell_assignments: dict[str, str] = {}

    for _, _, statement in statements:
        match = assignment_pattern.match(statement)

        if match:
            shell_assignments[
                match.group(1)
            ] = match.group(2).strip()

    selected_invocation = select_python_invocation(
        statements,
        max(argv_layout.values()),
    )
    arguments = list(
        selected_invocation["arguments"]
    )

    metrics[
        "selected_invocation_argument_count"
    ] = len(arguments)

    resolved_arguments: dict[str, object] = {}
    argument_rows: list[dict[str, object]] = []

    for name, index in sorted(
        argv_layout.items(),
        key=lambda item: item[1],
    ):
        if index > len(arguments):
            raise ValueError(
                f"missing shell argument {index} for {name}"
            )

        token = arguments[index - 1]
        value, route = resolve_shell_expression(
            token,
            shell_assignments,
        )

        if value is None:
            raise ValueError(
                f"unable to resolve {name}: {route}"
            )

        resolved_arguments[name] = value
        argument_rows.append(
            {
                "python_name": name,
                "sys_argv_index": index,
                "shell_token": token,
                "resolved_value": value,
                "resolution_path": route,
            }
        )

    write_tsv(
        ARGUMENTS,
        [
            "python_name",
            "sys_argv_index",
            "shell_token",
            "resolved_value",
            "resolution_path",
        ],
        argument_rows,
    )

    metrics[
        "resolved_python_arguments"
    ] = len(resolved_arguments)

    name_to_node: dict[str, ast.AST] = {}
    node_order: dict[int, int] = {}

    for order, node in enumerate(
        extracted_tree.body
    ):
        node_order[id(node)] = order

        for name in assigned_top_level_names(node):
            name_to_node[name] = node

    core_function_names = {
        function.name
        for function in core_functions
    }
    required_names = function_global_names(
        core_functions
    )
    required_names.update(
        {
            "ENTRY_OFFSET",
            "END_TOLERANCE",
        }
    )

    metrics[
        "initial_required_global_names"
    ] = len(required_names)

    included_import_nodes: dict[int, ast.AST] = {}
    included_assignment_nodes: dict[int, ast.AST] = {}
    synthetic_nodes: dict[
        tuple[int, str],
        ast.Assign,
    ] = {}
    dependency_rows: list[dict[str, object]] = []
    resolved_names = set(core_function_names)
    pending = list(sorted(required_names))

    while pending:
        name = pending.pop()

        if name in resolved_names:
            continue

        resolved_names.add(name)
        node = name_to_node.get(name)

        if node is None:
            raise ValueError(
                f"required global has no top-level definition: {name}"
            )

        if isinstance(
            node,
            (ast.Import, ast.ImportFrom),
        ):
            included_import_nodes[
                id(node)
            ] = copy.deepcopy(node)
            dependency_rows.append(
                {
                    "global_name": name,
                    "node_order": node_order[id(node)],
                    "node_type": type(node).__name__,
                    "action": "INCLUDE_ORIGINAL_IMPORT",
                    "detail": ".",
                }
            )
            continue

        if not isinstance(
            node,
            (ast.Assign, ast.AnnAssign),
        ):
            raise ValueError(
                f"unsupported dependency node for {name}: "
                f"{type(node).__name__}"
            )

        frozen, value, route = (
            runtime_literal_from_assignment(
                node,
                resolved_arguments,
            )
        )

        if frozen:
            synthetic_nodes[
                (
                    node_order[id(node)],
                    name,
                )
            ] = ast.Assign(
                targets=[
                    ast.Name(
                        id=name,
                        ctx=ast.Store(),
                    )
                ],
                value=ast.Constant(value=value),
            )
            dependency_rows.append(
                {
                    "global_name": name,
                    "node_order": node_order[id(node)],
                    "node_type": type(node).__name__,
                    "action": "FREEZE_ARGV_DERIVED_LITERAL",
                    "detail": f"{route};value={value!r}",
                }
            )
            continue

        if contains_sys_argv(node):
            raise ValueError(
                f"required assignment for {name} contains sys.argv "
                "and was not recognized as a frozen runtime constant"
            )

        included_assignment_nodes[
            id(node)
        ] = copy.deepcopy(node)
        dependency_rows.append(
            {
                "global_name": name,
                "node_order": node_order[id(node)],
                "node_type": type(node).__name__,
                "action": "INCLUDE_ORIGINAL_ASSIGNMENT_AST",
                "detail": ast.unparse(node),
            }
        )

        for dependency in sorted(
            loaded_names(node)
        ):
            if (
                dependency in resolved_names
                or dependency in core_function_names
                or dependency in dir(builtins)
            ):
                continue

            if dependency in name_to_node:
                pending.append(dependency)

    write_tsv(
        DEPENDENCIES,
        [
            "global_name",
            "node_order",
            "node_type",
            "action",
            "detail",
        ],
        sorted(
            dependency_rows,
            key=lambda row: (
                int(row["node_order"]),
                str(row["global_name"]),
            ),
        ),
    )

    metrics[
        "included_original_import_nodes"
    ] = len(included_import_nodes)
    metrics[
        "included_original_assignment_nodes"
    ] = len(included_assignment_nodes)
    metrics[
        "frozen_runtime_constant_nodes"
    ] = len(synthetic_nodes)

    module_body: list[ast.stmt] = [
        ast.Expr(
            value=ast.Constant(
                value=(
                    "Clean P3 repeat core reconstructed from "
                    "audited functions and required original AST nodes."
                )
            )
        ),
        ast.ImportFrom(
            module="__future__",
            names=[
                ast.alias(
                    name="annotations",
                    asname=None,
                )
            ],
            level=0,
        ),
    ]

    ordered_items: list[
        tuple[int, int, ast.stmt]
    ] = []

    for node_id, node in included_import_nodes.items():
        original_node = next(
            item
            for item in extracted_tree.body
            if id(item) == node_id
        )

        if (
            isinstance(original_node, ast.ImportFrom)
            and original_node.module == "__future__"
        ):
            continue

        ordered_items.append(
            (
                node_order[node_id],
                0,
                node,
            )
        )

    for node_id, node in included_assignment_nodes.items():
        ordered_items.append(
            (
                node_order[node_id],
                1,
                node,
            )
        )

    for (order, name), node in synthetic_nodes.items():
        ordered_items.append(
            (
                order,
                1,
                node,
            )
        )

    for _, _, node in sorted(
        ordered_items,
        key=lambda item: (
            item[0],
            item[1],
        ),
    ):
        module_body.append(node)

    module_body.extend(core_functions)

    candidate_tree = ast.Module(
        body=module_body,
        type_ignores=[],
    )
    ast.fix_missing_locations(candidate_tree)

    candidate_has_sys_argv = (
        contains_sys_argv(candidate_tree)
    )
    metrics[
        "candidate_ast_contains_sys_argv"
    ] = str(candidate_has_sys_argv).lower()

    if candidate_has_sys_argv:
        raise ValueError(
            "candidate AST contains sys.argv"
        )

    candidate_source = ast.unparse(
        candidate_tree
    ) + "\n"
    CANDIDATE_MODULE.write_text(
        candidate_source,
        encoding="utf-8",
    )

    code = compile(
        candidate_tree,
        str(CANDIDATE_MODULE),
        "exec",
    )
    namespace: dict[str, object] = {}
    exec(code, namespace)

    missing_functions = [
        name
        for name in core_function_names
        if name not in namespace
    ]

    if missing_functions:
        raise ValueError(
            "candidate functions missing: "
            + ",".join(sorted(missing_functions))
        )

    metrics[
        "candidate_functions_available"
    ] = len(core_function_names)

    sizing_rows = read_tsv(SIZING)
    positive_rows = [
        row
        for row in sizing_rows
        if (
            row.get("tract_bp")
            not in {
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

    metrics[
        "positive_contract_rows"
    ] = len(positive_rows)

    if len(positive_rows) != 1:
        raise ValueError(
            "expected one positive contract row; "
            f"observed {len(positive_rows)}"
        )

    row = positive_rows[0]
    projection_id = row["projection_id"]
    sequences = load_fasta(QUERY_FASTA)

    if projection_id not in sequences:
        raise ValueError(
            f"positive query sequence missing: {projection_id}"
        )

    oriented_clip = sequences[projection_id]
    target_entry_query = int(
        row["target_entry_query_offset"]
    )
    motif = namespace[
        "canonical_motif"
    ](
        row["canonical_motif"]
    )
    entry_offset = int(
        namespace["ENTRY_OFFSET"]
    )
    end_tolerance = int(
        namespace["END_TOLERANCE"]
    )

    metrics["entry_offset"] = entry_offset
    metrics[
        "end_tolerance"
    ] = end_tolerance

    minimum_start = max(
        0,
        target_entry_query - entry_offset,
    )
    maximum_start = min(
        len(oriented_clip),
        target_entry_query + entry_offset,
    )

    best_tract = None

    for tract_start in range(
        minimum_start,
        maximum_start + 1,
    ):
        call = namespace[
            "longest_valid_periodic_prefix"
        ](
            oriented_clip[tract_start:],
            motif,
        )

        if call is None:
            continue

        tract_end = (
            tract_start + call["prefix_bp"]
        )
        reaches_end = (
            len(oriented_clip) - tract_end
            <= end_tolerance
        )
        candidate = dict(call)
        candidate.update(
            {
                "tract_start": tract_start,
                "tract_end": tract_end,
                "entry_offset": (
                    tract_start
                    - target_entry_query
                ),
                "reaches_clip_end": (
                    reaches_end
                ),
            }
        )
        rank = (
            candidate["prefix_bp"],
            candidate["purity"],
            candidate["score"],
            -abs(candidate["entry_offset"]),
        )

        if (
            best_tract is None
            or rank > best_tract["_rank"]
        ):
            candidate["_rank"] = rank
            best_tract = candidate

    if best_tract is None:
        raise ValueError(
            "clean repeat core did not recover positive tract"
        )

    raw_start, raw_end = namespace[
        "oriented_to_raw_interval"
    ](
        best_tract["tract_start"],
        best_tract["tract_end"],
        int(row["raw_clip_start"]),
        int(row["raw_clip_end"]),
        row["orientation_transform"],
    )

    target_side = row[
        "target_facing_genomic_side"
    ]

    if best_tract["reaches_clip_end"]:
        produced_sizing = "lower_bound"
        produced_class = (
            "LEFT_ANCHORED_CENSORED_RIGHT"
            if target_side == "GENOMIC_RIGHT"
            else "RIGHT_ANCHORED_CENSORED_LEFT"
        )
    else:
        produced_sizing = "partial_internal"
        produced_class = (
            "LEFT_ONLY_INTERNAL"
            if target_side == "GENOMIC_RIGHT"
            else "RIGHT_ONLY_INTERNAL"
        )

    produced = {
        "tract_oriented_start":
            best_tract["tract_start"],
        "tract_oriented_end":
            best_tract["tract_end"],
        "tract_raw_start":
            raw_start,
        "tract_raw_end":
            raw_end,
        "tract_bp":
            best_tract["prefix_bp"],
        "repeat_units_observed_read":
            "{:.6f}".format(
                best_tract["observed_units"]
            ),
        "repeat_units_motif_path":
            "{:.6f}".format(
                best_tract["path_units"]
            ),
        "motif_path_to_read_units_ratio":
            "{:.6f}".format(
                best_tract["path_ratio"]
            ),
        "matches":
            best_tract["matches"],
        "mismatches":
            best_tract["mismatches"],
        "insertions":
            best_tract["insertions"],
        "deletions":
            best_tract["deletions"],
        "purity":
            "{:.6f}".format(
                best_tract["purity"]
            ),
        "score":
            best_tract["score"],
        "selected_orientation":
            best_tract["orientation"],
        "entry_offset_selected_bp":
            best_tract["entry_offset"],
        "distance_from_tract_to_oriented_clip_end_bp":
            (
                len(oriented_clip)
                - best_tract["tract_end"]
            ),
        "tract_reaches_expected_raw_end":
            str(
                best_tract[
                    "reaches_clip_end"
                ]
            ).lower(),
        "evidence_class":
            produced_class,
        "sizing_status":
            produced_sizing,
    }

    replay_rows: list[dict[str, object]] = []
    field_mismatches = 0

    for field in COMPARISON_FIELDS:
        expected = str(row[field])
        observed = str(produced[field])
        matches = expected == observed

        if not matches:
            field_mismatches += 1

        replay_rows.append(
            {
                "projection_id": projection_id,
                "field": field,
                "expected": expected,
                "produced": observed,
                "matches": str(matches).lower(),
            }
        )

    write_tsv(
        REPLAY,
        [
            "projection_id",
            "field",
            "expected",
            "produced",
            "matches",
        ],
        replay_rows,
    )

    metrics[
        "positive_cases_replayed"
    ] = 1
    metrics[
        "comparison_fields"
    ] = len(replay_rows)
    metrics[
        "field_mismatches"
    ] = field_mismatches

    return (
        "PASS"
        if field_mismatches == 0
        else "REVIEW"
    )


status = "ERROR"

try:
    status = main()
    ERROR_REPORT.write_text(
        "No validation exception.\n",
        encoding="utf-8",
    )

except Exception as error:
    metrics[
        "validation_error_type"
    ] = type(error).__name__
    metrics[
        "validation_error_message"
    ] = str(error).replace(
        "\t",
        " ",
    ).replace(
        "\n",
        " ",
    )
    ERROR_REPORT.write_text(
        traceback.format_exc(),
        encoding="utf-8",
    )

metrics[
    "repeat_core_positive_validation_v5_status"
] = status

with QC.open(
    "w",
    encoding="utf-8",
) as handle:
    handle.write("metric\tvalue\n")

    ordered_keys = [
        "source_strategy",
        "core_functions_loaded",
        "python_argv_layout_rows",
        "selected_invocation_argument_count",
        "resolved_python_arguments",
        "initial_required_global_names",
        "included_original_import_nodes",
        "included_original_assignment_nodes",
        "frozen_runtime_constant_nodes",
        "candidate_ast_contains_sys_argv",
        "candidate_functions_available",
        "entry_offset",
        "end_tolerance",
        "positive_contract_rows",
        "positive_cases_replayed",
        "comparison_fields_expected",
        "comparison_fields",
        "field_mismatches",
        "validation_error_type",
        "validation_error_message",
        "repeat_core_positive_validation_v5_status",
    ]

    for key in ordered_keys:
        handle.write(
            "{}\t{}\n".format(
                key,
                metrics.get(key, "."),
            )
        )
PY

python -m py_compile "$PY"

rm -f \
  "$CANDIDATE_MODULE" \
  "$ARGUMENTS" \
  "$DEPENDENCIES" \
  "$REPLAY" \
  "$ERROR_REPORT" \
  "$QC" \
  "$MANIFEST"

python "$PY" \
  "$SOURCE_SCRIPT" \
  "$EXTRACTED" \
  "$CORE_FUNCTIONS" \
  "$SIZING" \
  "$QUERY_FASTA" \
  "$CANDIDATE_MODULE" \
  "$ARGUMENTS" \
  "$DEPENDENCIES" \
  "$REPLAY" \
  "$ERROR_REPORT" \
  "$QC"

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in \
      "$ARGUMENTS" \
      "$DEPENDENCIES" \
      "$REPLAY" \
      "$QC"
    do
        if [[ -f "$path" ]]; then
            printf '%s\t%s\t%s\t%s\t%s\n' \
              "$(basename "$path")" \
              "$(awk 'END {print NR-1}' "$path")" \
              "$(stat -c '%s' "$path")" \
              "$(sha256sum "$path" | awk '{print $1}')" \
              "$path"
        fi
    done

    for path in \
      "$CANDIDATE_MODULE" \
      "$ERROR_REPORT"
    do
        if [[ -f "$path" ]]; then
            printf '%s\t%s\t%s\t%s\t%s\n' \
              "$(basename "$path")" \
              "." \
              "$(stat -c '%s' "$path")" \
              "$(sha256sum "$path" | awk '{print $1}')" \
              "$path"
        fi
    done
} > "$MANIFEST"

echo "===== QC ====="
column -ts $'\t' "$QC"

echo
echo "===== ERROR REPORT ====="
cat "$ERROR_REPORT"

if [[ -f "$DEPENDENCIES" ]]; then
    echo
    echo "===== AST DEPENDENCIES ====="
    column -ts $'\t' "$DEPENDENCIES"
fi

if [[ -f "$REPLAY" ]]; then
    echo
    echo "===== FIELD COMPARISON ====="
    column -ts $'\t' "$REPLAY"
fi

echo
echo "===== MANIFEST ====="
column -ts $'\t' "$MANIFEST"

status="$(
    awk -F '\t' '
      $1 == "repeat_core_positive_validation_v5_status" {
        print $2
      }
    ' "$QC"
)"

if [[ "$status" != "PASS" ]]; then
    echo
    echo "Validation did not PASS; inspect QC and error report above." >&2
    exit 1
fi
