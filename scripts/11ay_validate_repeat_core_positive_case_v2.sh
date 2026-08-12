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
QUERY_FASTA="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_p3_bridge_feasibility/p3_bridge_queries.fasta.gz"
PARAMETERS="$PROJECT_ROOT/results/11_p3_repeat_parameter_resolution_v2/$RUN_ID/repeat_parameter_argv_mapping.tsv"

OUTDIR="$PROJECT_ROOT/results/11_p3_repeat_core_validation_v2/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_p3_repeat_core_validation_v2/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_p3_repeat_core_validation_v2/$RUN_ID"

CANDIDATE_MODULE="$OUTDIR/p3_repeat_core_candidate.py"
REPLAY="$OUTDIR/p3_repeat_positive_case_replay.tsv"
DEPENDENCIES="$OUTDIR/p3_repeat_core_dependency_closure.tsv"
PARAMETERS_USED="$OUTDIR/p3_repeat_runtime_parameters_used.tsv"
QC="$QCDIR/p3_repeat_core_positive_validation_v2.qc.tsv"
MANIFEST="$OUTDIR/${RUN_ID}.p3_repeat_core_positive_validation_v2.manifest.tsv"
PY="$WORKDIR/validate_repeat_core_positive_v2.py"

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR"

for path in \
  "$EXTRACTED" \
  "$SIZING" \
  "$QUERY_FASTA" \
  "$PARAMETERS"
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
import sys
from pathlib import Path

(
    extracted_text,
    sizing_text,
    query_fasta_text,
    parameters_text,
    candidate_module_text,
    replay_text,
    dependencies_text,
    parameters_used_text,
    qc_text,
) = sys.argv[1:]

EXTRACTED = Path(extracted_text)
SIZING = Path(sizing_text)
QUERY_FASTA = Path(query_fasta_text)
PARAMETERS = Path(parameters_text)
CANDIDATE_MODULE = Path(candidate_module_text)
REPLAY = Path(replay_text)
DEPENDENCIES = Path(dependencies_text)
PARAMETERS_USED = Path(parameters_used_text)
QC = Path(qc_text)

ROOT_FUNCTIONS = {
    "canonical_motif",
    "longest_valid_periodic_prefix",
    "oriented_to_raw_interval",
}
REQUIRED_PARAMETERS = {
    "ENTRY_OFFSET",
    "END_TOLERANCE",
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


def load_fasta(path: Path) -> dict[str, str]:
    records: dict[str, str] = {}
    opener = gzip.open if path.suffix == ".gz" else open

    with opener(
        path,
        "rt",
        encoding="utf-8",
    ) as handle:
        record_id: str | None = None
        sequence_parts: list[str] = []

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
                    records[record_id] = "".join(
                        sequence_parts
                    ).upper()

                record_id = line[1:].split()[0]

                if not record_id:
                    raise ValueError(
                        f"empty FASTA ID at line {line_number}"
                    )

                sequence_parts = []
                continue

            if record_id is None:
                raise ValueError(
                    "FASTA sequence before first header"
                )

            sequence_parts.append(line)

        if record_id is not None:
            if record_id in records:
                raise ValueError(
                    f"duplicate FASTA ID: {record_id}"
                )

            records[record_id] = "".join(
                sequence_parts
            ).upper()

    return records


parameter_rows = read_tsv(PARAMETERS)
parameter_values: dict[str, int] = {}

for row in parameter_rows:
    name = row["parameter"]

    if name not in REQUIRED_PARAMETERS:
        continue

    if row["status"] != "RESOLVED":
        raise SystemExit(
            f"Parameter is not resolved: {name}"
        )

    parameter_values[name] = int(
        row["resolved_value"]
    )

missing_parameters = (
    REQUIRED_PARAMETERS - set(parameter_values)
)

if missing_parameters:
    raise SystemExit(
        "Missing resolved parameters: "
        + ",".join(sorted(missing_parameters))
    )

with PARAMETERS_USED.open(
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
            "parameter",
            "value",
            "source",
        ]
    )

    for name in sorted(parameter_values):
        writer.writerow(
            [
                name,
                parameter_values[name],
                str(PARAMETERS),
            ]
        )

python_source = EXTRACTED.read_text(
    encoding="utf-8",
    errors="replace",
)
tree = ast.parse(
    python_source,
    filename=str(EXTRACTED),
)


def assigned_names(node: ast.AST) -> set[str]:
    names: set[str] = set()

    if isinstance(node, ast.Assign):
        targets = node.targets

    elif isinstance(node, ast.AnnAssign):
        targets = [node.target]

    elif isinstance(node, ast.FunctionDef):
        names.add(node.name)
        return names

    elif isinstance(node, ast.ClassDef):
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
            names.add(
                alias.asname or alias.name
            )
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
        "Missing repeat-core root functions: "
        + ",".join(sorted(missing_roots))
    )

selected_nodes: set[ast.AST] = set()
resolved_names: set[str] = set()
pending = list(ROOT_FUNCTIONS)
dependency_rows: list[dict[str, str]] = []
builtin_names = set(dir(builtins))

while pending:
    name = pending.pop()

    if name in resolved_names:
        continue

    resolved_names.add(name)
    node = name_to_node.get(name)

    if node is None:
        continue

    selected_nodes.add(node)

    for dependency in sorted(
        loaded_names(node)
    ):
        dependency_node = name_to_node.get(
            dependency
        )

        if dependency_node is not None:
            resolution = "TOP_LEVEL_NODE"
        elif dependency in builtin_names:
            resolution = "BUILTIN"
        else:
            resolution = "FUNCTION_LOCAL_OR_RUNTIME"

        dependency_rows.append(
            {
                "requested_by": name,
                "dependency_name": dependency,
                "resolution": resolution,
            }
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

ordered_nodes = sorted(
    selected_nodes,
    key=lambda node: node_order[id(node)],
)

module_source = (
    '"""Exact repeat-core dependency closure extracted from 11af.\n\n'
    "Validation artifact; not yet installed as production code.\n"
    '"""\n\n'
    + "\n\n".join(
        ast.unparse(node)
        for node in ordered_nodes
    )
    + "\n"
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
            "requested_by",
            "dependency_name",
            "resolution",
        ],
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(
        sorted(
            dependency_rows,
            key=lambda row: (
                row["requested_by"],
                row["dependency_name"],
            ),
        )
    )

spec = importlib.util.spec_from_file_location(
    "p3_repeat_core_candidate",
    CANDIDATE_MODULE,
)

if spec is None or spec.loader is None:
    raise SystemExit(
        "Unable to import extracted repeat-core module"
    )

candidate = importlib.util.module_from_spec(
    spec
)
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
        "Expected exactly one positive sizing row; "
        f"observed {len(positive_rows)}"
    )

row = positive_rows[0]
projection_id = row["projection_id"]
sequences = load_fasta(QUERY_FASTA)

if projection_id not in sequences:
    raise SystemExit(
        f"Positive query sequence is absent: {projection_id}"
    )

if row.get("query_prefix_matches") not in {
    None,
    "",
    ".",
    "true",
}:
    raise SystemExit(
        "Positive contract row has unexpected "
        "query_prefix_matches value: "
        + row["query_prefix_matches"]
    )

oriented_clip = sequences[projection_id]
target_entry_query = int(
    row["target_entry_query_offset"]
)
entry_offset = parameter_values[
    "ENTRY_OFFSET"
]
end_tolerance = parameter_values[
    "END_TOLERANCE"
]
motif = candidate.canonical_motif(
    row["canonical_motif"]
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
        "Extracted repeat core failed to recover "
        "the positive tract"
    )

tract_raw_start, tract_raw_end = (
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
    produced_sizing_status = "lower_bound"
    produced_evidence_class = (
        "LEFT_ANCHORED_CENSORED_RIGHT"
        if target_side == "GENOMIC_RIGHT"
        else "RIGHT_ANCHORED_CENSORED_LEFT"
    )
else:
    produced_sizing_status = (
        "partial_internal"
    )
    produced_evidence_class = (
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
        tract_raw_start,
    "tract_raw_end":
        tract_raw_end,
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
        produced_evidence_class,
    "sizing_status":
        produced_sizing_status,
}

comparison_fields = list(produced)
comparison_rows = []
field_mismatches = 0

for field in comparison_fields:
    expected = str(row[field])
    observed = str(produced[field])
    matches = expected == observed

    if not matches:
        field_mismatches += 1

    comparison_rows.append(
        {
            "projection_id": projection_id,
            "field": field,
            "expected": expected,
            "produced": observed,
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
    len(positive_rows) != 1
    or len(ordered_nodes) < len(
        ROOT_FUNCTIONS
    )
    or field_mismatches
):
    status = "REVIEW"

with QC.open(
    "w",
    encoding="utf-8",
) as handle:
    handle.write("metric\tvalue\n")
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
        "root_functions_requested\t{}\n".format(
            len(ROOT_FUNCTIONS)
        )
    )
    handle.write(
        "dependency_nodes_extracted\t{}\n".format(
            len(ordered_nodes)
        )
    )
    handle.write(
        "positive_cases_replayed\t1\n"
    )
    handle.write(
        "comparison_fields\t{}\n".format(
            len(comparison_fields)
        )
    )
    handle.write(
        "field_mismatches\t{}\n".format(
            field_mismatches
        )
    )
    handle.write(
        "repeat_core_positive_validation_v2_status\t{}\n".format(
            status
        )
    )

if status != "PASS":
    raise SystemExit(
        "Repeat-core positive validation v2 requires review"
    )
PY

python -m py_compile "$PY"

rm -f \
  "$CANDIDATE_MODULE" \
  "$REPLAY" \
  "$DEPENDENCIES" \
  "$PARAMETERS_USED" \
  "$QC" \
  "$MANIFEST"

python "$PY" \
  "$EXTRACTED" \
  "$SIZING" \
  "$QUERY_FASTA" \
  "$PARAMETERS" \
  "$CANDIDATE_MODULE" \
  "$REPLAY" \
  "$DEPENDENCIES" \
  "$PARAMETERS_USED" \
  "$QC"

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in \
      "$REPLAY" \
      "$DEPENDENCIES" \
      "$PARAMETERS_USED" \
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
echo "===== PARAMETERS USED ====="
column -ts $'\t' "$PARAMETERS_USED"

echo
echo "===== FIELD COMPARISON ====="
column -ts $'\t' "$REPLAY"

echo
echo "===== MANIFEST ====="
column -ts $'\t' "$MANIFEST"
