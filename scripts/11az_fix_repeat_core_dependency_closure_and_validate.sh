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
SIZING="$PROJECT_ROOT/results/11_p3_target_entry_sizing/$RUN_ID/p3_target_entry_repeat_evidence.tsv"
QUERY_FASTA="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_p3_bridge_feasibility/p3_bridge_queries.fasta.gz"

OUTDIR="$PROJECT_ROOT/results/11_p3_repeat_core_validation_v3/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_p3_repeat_core_validation_v3/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_p3_repeat_core_validation_v3/$RUN_ID"

CANDIDATE_MODULE="$OUTDIR/p3_repeat_core_candidate.v3.py"
PARAMETERS="$OUTDIR/p3_repeat_all_runtime_parameters.tsv"
DEPENDENCIES="$OUTDIR/p3_repeat_dependency_closure.v3.tsv"
REPLAY="$OUTDIR/p3_repeat_positive_case_replay.v3.tsv"
QC="$QCDIR/p3_repeat_core_positive_validation_v3.qc.tsv"
MANIFEST="$OUTDIR/${RUN_ID}.p3_repeat_core_positive_validation_v3.manifest.tsv"
PY="$WORKDIR/validate_repeat_core_positive_v3.py"

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR"

for path in \
  "$SOURCE_SCRIPT" \
  "$EXTRACTED" \
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
import csv
import gzip
import importlib.util
import re
import shlex
import sys
from pathlib import Path

(
    source_script_text,
    extracted_text,
    sizing_text,
    query_fasta_text,
    candidate_module_text,
    parameters_text,
    dependencies_text,
    replay_text,
    qc_text,
) = sys.argv[1:]

SOURCE_SCRIPT = Path(source_script_text)
EXTRACTED = Path(extracted_text)
SIZING = Path(sizing_text)
QUERY_FASTA = Path(query_fasta_text)
CANDIDATE_MODULE = Path(candidate_module_text)
PARAMETERS = Path(parameters_text)
DEPENDENCIES = Path(dependencies_text)
REPLAY = Path(replay_text)
QC = Path(qc_text)

ROOT_FUNCTIONS = {
    "canonical_motif",
    "longest_valid_periodic_prefix",
    "oriented_to_raw_interval",
}

shell_source = SOURCE_SCRIPT.read_text(
    encoding="utf-8",
    errors="replace",
)
python_source = EXTRACTED.read_text(
    encoding="utf-8",
    errors="replace",
)
shell_lines = shell_source.splitlines()
tree = ast.parse(
    python_source,
    filename=str(EXTRACTED),
)


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        return list(
            csv.DictReader(handle, delimiter="\t")
        )


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


outside_lines = strip_heredoc_bodies(shell_lines)
statements = join_shell_statements(outside_lines)

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
                layout[element.id] = index
                index += 1

    return layout


argv_layout = parse_argv_layout(tree)


def stop_at_shell_operator(
    tokens: list[str],
) -> list[str]:
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


python_invocations = []

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
        if Path(token).name in {"python", "python3"}:
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

    if script_token in {"$PY", "${PY}"}:
        score += 100

    if len(arguments) >= len(argv_layout):
        score += 100

    python_invocations.append(
        {
            "start_line": start_line,
            "end_line": end_line,
            "script_token": script_token,
            "arguments": arguments,
            "score": score,
        }
    )

if not python_invocations:
    raise SystemExit(
        "No Python invocation found outside heredoc bodies"
    )

selected_invocation = max(
    python_invocations,
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
    seen: set[str] | None = None,
) -> tuple[int | float | str | None, str]:
    seen = set() if seen is None else set(seen)
    expression = unquote(expression)

    if re.fullmatch(r"[+-]?[0-9]+", expression):
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

        if variable not in shell_assignments:
            return None, f"UNBOUND({variable})"

        seen.add(variable)
        value, route = resolve_shell_expression(
            shell_assignments[variable],
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
            variable in shell_assignments
            and variable not in seen
        ):
            seen.add(variable)
            value, route = resolve_shell_expression(
                shell_assignments[variable],
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


resolved_argv: dict[str, object] = {}
parameter_rows = []

for python_name, argv_index in sorted(
    argv_layout.items(),
    key=lambda item: item[1],
):
    if argv_index > len(
        selected_invocation["arguments"]
    ):
        continue

    token = selected_invocation[
        "arguments"
    ][argv_index - 1]
    value, route = resolve_shell_expression(token)
    resolved_argv[python_name] = value

    parameter_rows.append(
        {
            "python_name": python_name,
            "sys_argv_index": argv_index,
            "shell_token": token,
            "resolved_value": (
                value
                if value is not None
                else "."
            ),
            "resolution_path": route,
        }
    )

with PARAMETERS.open(
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=[
            "python_name",
            "sys_argv_index",
            "shell_token",
            "resolved_value",
            "resolution_path",
        ],
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(parameter_rows)


def assigned_names(node: ast.AST) -> set[str]:
    names: set[str] = set()

    if isinstance(node, ast.Assign):
        targets = node.targets

    elif isinstance(node, ast.AnnAssign):
        targets = [node.target]

    elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
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


def loaded_names(node: ast.AST) -> set[str]:
    return {
        child.id
        for child in ast.walk(node)
        if (
            isinstance(child, ast.Name)
            and isinstance(child.ctx, ast.Load)
        )
    }


def contains_sys_argv(node: ast.AST) -> bool:
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


name_to_node: dict[str, ast.AST] = {}
node_order: dict[int, int] = {}

for index, node in enumerate(tree.body):
    node_order[id(node)] = index

    for name in assigned_names(node):
        name_to_node[name] = node

missing_roots = (
    ROOT_FUNCTIONS - set(name_to_node)
)

if missing_roots:
    raise SystemExit(
        "Missing repeat root functions: "
        + ",".join(sorted(missing_roots))
    )

python_assignments = {
    name: node
    for name, node in name_to_node.items()
    if isinstance(node, (ast.Assign, ast.AnnAssign))
}


def argv_conversion_assignment(
    node: ast.AST,
    target_name: str,
) -> tuple[object | None, str | None]:
    if not isinstance(node, (ast.Assign, ast.AnnAssign)):
        return None, None

    value_node = node.value

    if not (
        isinstance(value_node, ast.Call)
        and isinstance(value_node.func, ast.Name)
        and value_node.func.id in {"int", "float", "str"}
        and len(value_node.args) == 1
        and isinstance(value_node.args[0], ast.Name)
    ):
        return None, None

    intermediate = value_node.args[0].id

    if intermediate not in resolved_argv:
        return None, intermediate

    raw_value = resolved_argv[intermediate]

    if value_node.func.id == "int":
        return int(raw_value), intermediate

    if value_node.func.id == "float":
        return float(raw_value), intermediate

    return str(raw_value), intermediate


selected_nodes: set[ast.AST] = set()
synthetic_assignments: dict[str, object] = {}
dependency_rows = []
pending = list(ROOT_FUNCTIONS)
resolved_names: set[str] = set()
builtin_names = set(dir(builtins))

while pending:
    name = pending.pop()

    if name in resolved_names:
        continue

    resolved_names.add(name)
    node = name_to_node.get(name)

    if node is None:
        continue

    if contains_sys_argv(node):
        dependency_rows.append(
            {
                "requested_name": name,
                "node_type": type(node).__name__,
                "action": "EXCLUDED_SYS_ARGV_SIDE_EFFECT",
                "replacement": ".",
            }
        )
        continue

    value, intermediate = argv_conversion_assignment(
        node,
        name,
    )

    if intermediate is not None:
        if value is None:
            raise SystemExit(
                f"Unable to resolve runtime constant {name} "
                f"from {intermediate}"
            )

        synthetic_assignments[name] = value
        dependency_rows.append(
            {
                "requested_name": name,
                "node_type": type(node).__name__,
                "action": "SYNTHETIC_LITERAL_ASSIGNMENT",
                "replacement": repr(value),
            }
        )
        continue

    selected_nodes.add(node)
    dependency_rows.append(
        {
            "requested_name": name,
            "node_type": type(node).__name__,
            "action": "INCLUDED_ORIGINAL_NODE",
            "replacement": ".",
        }
    )

    for dependency in sorted(loaded_names(node)):
        dependency_node = name_to_node.get(
            dependency
        )

        if (
            dependency_node is not None
            and dependency not in resolved_names
        ):
            pending.append(dependency)

for node in tree.body:
    if (
        isinstance(node, ast.ImportFrom)
        and node.module == "__future__"
    ):
        selected_nodes.add(node)

ordered_original_nodes = sorted(
    selected_nodes,
    key=lambda node: node_order[id(node)],
)

module_parts = [
    '"""Exact 11af repeat core with runtime constants frozen.\n\n'
    "Validation artifact only; no command-line argument side effects.\n"
    '"""',
]

for name, value in sorted(
    synthetic_assignments.items()
):
    module_parts.append(
        f"{name} = {value!r}"
    )

module_parts.extend(
    ast.unparse(node)
    for node in ordered_original_nodes
)

module_source = "\n\n".join(
    module_parts
) + "\n"

if "sys.argv" in module_source:
    raise SystemExit(
        "Candidate module still contains sys.argv"
    )

compile(
    module_source,
    str(CANDIDATE_MODULE),
    "exec",
)
CANDIDATE_MODULE.write_text(
    module_source,
    encoding="utf-8",
)

with DEPENDENCIES.open(
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=[
            "requested_name",
            "node_type",
            "action",
            "replacement",
        ],
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(dependency_rows)

spec = importlib.util.spec_from_file_location(
    "p3_repeat_core_candidate_v3",
    CANDIDATE_MODULE,
)

if spec is None or spec.loader is None:
    raise SystemExit(
        "Unable to import candidate repeat module"
    )

candidate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate)

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

if len(positive_rows) != 1:
    raise SystemExit(
        "Expected one positive sizing row; observed "
        f"{len(positive_rows)}"
    )

row = positive_rows[0]
projection_id = row["projection_id"]
sequences = load_fasta(QUERY_FASTA)

if projection_id not in sequences:
    raise SystemExit(
        f"Positive query sequence missing: {projection_id}"
    )

oriented_clip = sequences[projection_id]
target_entry_query = int(
    row["target_entry_query_offset"]
)
motif = candidate.canonical_motif(
    row["canonical_motif"]
)

entry_offset = int(
    getattr(candidate, "ENTRY_OFFSET")
)
end_tolerance = int(
    getattr(candidate, "END_TOLERANCE")
)

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
    call = (
        candidate.longest_valid_periodic_prefix(
            oriented_clip[tract_start:],
            motif,
        )
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
    proposed = dict(call)
    proposed.update(
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
        proposed["prefix_bp"],
        proposed["purity"],
        proposed["score"],
        -abs(proposed["entry_offset"]),
    )

    if (
        best_tract is None
        or rank > best_tract["_rank"]
    ):
        proposed["_rank"] = rank
        best_tract = proposed

if best_tract is None:
    raise SystemExit(
        "Candidate repeat core did not recover positive tract"
    )

raw_start, raw_end = (
    candidate.oriented_to_raw_interval(
        best_tract["tract_start"],
        best_tract["tract_end"],
        int(row["raw_clip_start"]),
        int(row["raw_clip_end"]),
        row["orientation_transform"],
    )
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

comparison_rows = []
field_mismatches = 0

for field, observed in produced.items():
    expected = str(row[field])
    produced_text = str(observed)
    matches = expected == produced_text

    if not matches:
        field_mismatches += 1

    comparison_rows.append(
        {
            "projection_id": projection_id,
            "field": field,
            "expected": expected,
            "produced": produced_text,
            "matches": str(matches).lower(),
        }
    )

with REPLAY.open(
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=[
            "projection_id",
            "field",
            "expected",
            "produced",
            "matches",
        ],
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(comparison_rows)

status = "PASS"

if (
    "sys.argv" in module_source
    or len(positive_rows) != 1
    or field_mismatches
):
    status = "REVIEW"

with QC.open(
    "w",
    encoding="utf-8",
) as handle:
    handle.write("metric\tvalue\n")
    handle.write(
        "selected_invocation_argument_count\t{}\n".format(
            len(
                selected_invocation[
                    "arguments"
                ]
            )
        )
    )
    handle.write(
        "resolved_python_arguments\t{}\n".format(
            len(resolved_argv)
        )
    )
    handle.write(
        "synthetic_runtime_constants\t{}\n".format(
            len(synthetic_assignments)
        )
    )
    handle.write(
        "candidate_contains_sys_argv\t{}\n".format(
            str(
                "sys.argv" in module_source
            ).lower()
        )
    )
    handle.write(
        "entry_offset\t{}\n".format(
            entry_offset
        )
    )
    handle.write(
        "end_tolerance\t{}\n".format(
            end_tolerance
        )
    )
    handle.write(
        "positive_cases_replayed\t1\n"
    )
    handle.write(
        "comparison_fields\t{}\n".format(
            len(comparison_rows)
        )
    )
    handle.write(
        "field_mismatches\t{}\n".format(
            field_mismatches
        )
    )
    handle.write(
        "repeat_core_positive_validation_v3_status\t{}\n".format(
            status
        )
    )

if status != "PASS":
    raise SystemExit(
        "Repeat-core positive validation v3 requires review"
    )
PY

python -m py_compile "$PY"

rm -f \
  "$CANDIDATE_MODULE" \
  "$PARAMETERS" \
  "$DEPENDENCIES" \
  "$REPLAY" \
  "$QC" \
  "$MANIFEST"

python "$PY" \
  "$SOURCE_SCRIPT" \
  "$EXTRACTED" \
  "$SIZING" \
  "$QUERY_FASTA" \
  "$CANDIDATE_MODULE" \
  "$PARAMETERS" \
  "$DEPENDENCIES" \
  "$REPLAY" \
  "$QC"

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in \
      "$PARAMETERS" \
      "$DEPENDENCIES" \
      "$REPLAY" \
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
      "$(basename "$CANDIDATE_MODULE")" \
      "." \
      "$(stat -c '%s' "$CANDIDATE_MODULE")" \
      "$(sha256sum "$CANDIDATE_MODULE" | awk '{print $1}')" \
      "$CANDIDATE_MODULE"
} > "$MANIFEST"

echo "===== QC ====="
column -ts $'\t' "$QC"

echo
echo "===== SYNTHETIC CONSTANTS ====="
awk -F '\t' '
  NR == 1 || $3 == "SYNTHETIC_LITERAL_ASSIGNMENT" {
    print
  }
' "$DEPENDENCIES" \
  | column -ts $'\t'

echo
echo "===== FIELD COMPARISON ====="
column -ts $'\t' "$REPLAY"

echo
echo "===== ALL RESOLVED PYTHON ARGUMENTS ====="
column -ts $'\t' "$PARAMETERS"

echo
echo "===== MANIFEST ====="
column -ts $'\t' "$MANIFEST"
