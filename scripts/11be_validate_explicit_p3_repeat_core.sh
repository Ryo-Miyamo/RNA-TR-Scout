#!/usr/bin/env bash
set -euo pipefail

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
fi

conda activate rnatr-v03
source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"

SIZING="$PROJECT_ROOT/results/11_p3_target_entry_sizing/$RUN_ID/p3_target_entry_repeat_evidence.tsv"
QUERY_FASTA="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_p3_bridge_feasibility/p3_bridge_queries.fasta.gz"
RAW_FASTQ="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_candidates_v0.3.1/ENCFF260PGB.pilot_100k.rnatr_candidate_all.fastq.gz"

OUTDIR="$PROJECT_ROOT/results/11_p3_repeat_core_explicit_validation/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_p3_repeat_core_explicit_validation/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_p3_repeat_core_explicit_validation/$RUN_ID"

MODULE="$OUTDIR/p3_repeat_explicit_candidate.py"
REPLAY="$OUTDIR/p3_repeat_positive_case_explicit_replay.tsv"
QC="$QCDIR/p3_repeat_explicit_validation.qc.tsv"
ERROR_REPORT="$OUTDIR/p3_repeat_explicit_validation.error.txt"
MANIFEST="$OUTDIR/${RUN_ID}.p3_repeat_explicit_validation.manifest.tsv"
VALIDATOR="$WORKDIR/validate_explicit_repeat_core.py"

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR"

for path in \
  "$SIZING" \
  "$QUERY_FASTA" \
  "$RAW_FASTQ"
do
    test -s "$path" || {
        echo "ERROR: missing required input: $path" >&2
        exit 1
    }
done

cat > "$MODULE" <<'PY'
"""Explicit P3 repeat core copied from the validated 11af algorithm.

This validation module is deliberately handwritten and self-contained.
It contains no code extraction, no command-line parsing, and no top-level
pipeline side effects.
"""

from __future__ import annotations

from dataclasses import dataclass

MIN_REPEAT_BP = 12
MIN_PURITY = 0.70
MIN_PATH_RATIO = 0.75
MAX_PATH_RATIO = 1.25
ENTRY_OFFSET = 5
END_TOLERANCE = 10
MAX_DELETIONS = 1

MATCH_SCORE = 3
MISMATCH_PENALTY = 4
INSERTION_PENALTY = 4
DELETION_PENALTY = 4

COMPLEMENT = str.maketrans("ACGT", "TGCA")


def reverse_complement(sequence):
    return sequence.translate(COMPLEMENT)[::-1]


def rotations(sequence):
    return [
        sequence[index:] + sequence[:index]
        for index in range(len(sequence))
    ]


def canonical_motif(sequence):
    candidates = []

    for oriented in (
        sequence,
        reverse_complement(sequence),
    ):
        candidates.extend(rotations(oriented))

    return min(candidates)


@dataclass(frozen=True)
class State:
    score: int
    motif_positions: int
    matches: int
    mismatches: int
    insertions: int
    deletions: int
    starting_phase: int
    orientation: str


def state_rank(state):
    return (
        state.score,
        state.matches,
        state.motif_positions,
        -state.mismatches,
        -state.insertions,
        -state.deletions,
        -state.starting_phase,
    )


def update(container, index, candidate):
    current = container[index]

    if (
        current is None
        or state_rank(candidate)
        > state_rank(current)
    ):
        container[index] = candidate


def prefix_periodicity(sequence, motif):
    orientations = sorted(
        set(
            rotations(motif)
            + rotations(
                reverse_complement(motif)
            )
        )
    )
    prefix_best = [None] * (len(sequence) + 1)

    for orientation in orientations:
        motif_length = len(orientation)
        previous = [
            State(
                score=0,
                motif_positions=0,
                matches=0,
                mismatches=0,
                insertions=0,
                deletions=0,
                starting_phase=phase,
                orientation=orientation,
            )
            for phase in range(motif_length)
        ]

        for sequence_index, base in enumerate(
            sequence,
            start=1,
        ):
            current = [None] * motif_length

            for expected_phase, state in enumerate(
                previous
            ):
                if state is None:
                    continue

                update(
                    current,
                    expected_phase,
                    State(
                        score=(
                            state.score
                            - INSERTION_PENALTY
                        ),
                        motif_positions=(
                            state.motif_positions
                        ),
                        matches=state.matches,
                        mismatches=state.mismatches,
                        insertions=(
                            state.insertions + 1
                        ),
                        deletions=state.deletions,
                        starting_phase=(
                            state.starting_phase
                        ),
                        orientation=orientation,
                    ),
                )

                for deleted in range(
                    MAX_DELETIONS + 1
                ):
                    phase = (
                        expected_phase + deleted
                    ) % motif_length
                    is_match = (
                        base == orientation[phase]
                    )
                    delta = (
                        MATCH_SCORE
                        if is_match
                        else -MISMATCH_PENALTY
                    )
                    delta -= (
                        deleted
                        * DELETION_PENALTY
                    )

                    update(
                        current,
                        (phase + 1)
                        % motif_length,
                        State(
                            score=(
                                state.score + delta
                            ),
                            motif_positions=(
                                state.motif_positions
                                + deleted
                                + 1
                            ),
                            matches=(
                                state.matches
                                + (
                                    1
                                    if is_match
                                    else 0
                                )
                            ),
                            mismatches=(
                                state.mismatches
                                + (
                                    0
                                    if is_match
                                    else 1
                                )
                            ),
                            insertions=(
                                state.insertions
                            ),
                            deletions=(
                                state.deletions
                                + deleted
                            ),
                            starting_phase=(
                                state.starting_phase
                            ),
                            orientation=orientation,
                        ),
                    )

            best_state = max(
                (
                    state
                    for state in current
                    if state is not None
                ),
                key=state_rank,
            )

            existing = prefix_best[
                sequence_index
            ]

            if (
                existing is None
                or state_rank(best_state)
                > state_rank(existing)
            ):
                prefix_best[
                    sequence_index
                ] = best_state

            previous = current

    return prefix_best


def longest_valid_periodic_prefix(
    sequence,
    motif,
):
    if not sequence:
        return None

    prefix_states = prefix_periodicity(
        sequence,
        motif,
    )
    best = None
    motif_length = len(motif)

    for prefix_bp in range(
        MIN_REPEAT_BP,
        len(sequence) + 1,
    ):
        state = prefix_states[prefix_bp]

        if state is None:
            continue

        denominator = (
            state.matches
            + state.mismatches
            + state.insertions
            + state.deletions
        )
        purity = (
            state.matches / denominator
            if denominator
            else 0.0
        )
        observed_units = (
            prefix_bp / motif_length
        )
        path_units = (
            state.motif_positions
            / motif_length
        )
        path_ratio = (
            path_units / observed_units
            if observed_units
            else 0.0
        )

        if (
            purity < MIN_PURITY
            or path_ratio < MIN_PATH_RATIO
            or path_ratio > MAX_PATH_RATIO
            or state.score <= 0
        ):
            continue

        candidate = {
            "prefix_bp": prefix_bp,
            "purity": purity,
            "observed_units": observed_units,
            "path_units": path_units,
            "path_ratio": path_ratio,
            "matches": state.matches,
            "mismatches": state.mismatches,
            "insertions": state.insertions,
            "deletions": state.deletions,
            "score": state.score,
            "orientation": state.orientation,
            "starting_phase": (
                state.starting_phase
            ),
        }

        if (
            best is None
            or (
                candidate["prefix_bp"],
                candidate["purity"],
                candidate["score"],
            )
            > (
                best["prefix_bp"],
                best["purity"],
                best["score"],
            )
        ):
            best = candidate

    return best


def oriented_to_raw_interval(
    oriented_start,
    oriented_end,
    raw_clip_start,
    raw_clip_end,
    transform,
):
    if transform == "AS_RAW":
        return (
            raw_clip_start + oriented_start,
            raw_clip_start + oriented_end,
        )

    if transform == "REVERSE_COMPLEMENT":
        return (
            raw_clip_end - oriented_end,
            raw_clip_end - oriented_start,
        )

    raise ValueError(
        "Unknown orientation transform: {}".format(
            transform
        )
    )
PY

cat > "$VALIDATOR" <<'PY'
from __future__ import annotations

import csv
import gzip
import importlib.util
import sys
import traceback
from pathlib import Path

(
    module_text,
    sizing_text,
    query_fasta_text,
    raw_fastq_text,
    replay_text,
    qc_text,
    error_text,
) = sys.argv[1:]

MODULE = Path(module_text)
SIZING = Path(sizing_text)
QUERY_FASTA = Path(query_fasta_text)
RAW_FASTQ = Path(raw_fastq_text)
REPLAY = Path(replay_text)
QC = Path(qc_text)
ERROR = Path(error_text)

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

metrics = {
    "validation_strategy":
        "EXPLICIT_SELF_CONTAINED_11AF_REPEAT_CORE",
    "comparison_fields_expected":
        len(COMPARISON_FIELDS),
    "validation_error_type": ".",
    "validation_error_message": ".",
}


def read_tsv(path):
    with path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        return list(
            csv.DictReader(
                handle,
                delimiter="\t",
            )
        )


def write_tsv(path, fields, rows):
    with path.open(
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
        writer.writerows(rows)


def load_fasta_record(path, wanted_id):
    found = None

    with gzip.open(
        path,
        "rt",
        encoding="utf-8",
    ) as handle:
        record_id = None
        parts = []

        for line in handle:
            line = line.strip()

            if not line:
                continue

            if line.startswith(">"):
                if (
                    record_id == wanted_id
                    and found is None
                ):
                    found = "".join(parts).upper()

                record_id = line[1:].split()[0]
                parts = []
                continue

            if record_id is not None:
                parts.append(line)

        if (
            record_id == wanted_id
            and found is None
        ):
            found = "".join(parts).upper()

    if found is None:
        raise KeyError(
            f"FASTA record not found: {wanted_id}"
        )

    return found


def load_fastq_record(path, wanted_id):
    with gzip.open(
        path,
        "rt",
        encoding="utf-8",
    ) as handle:
        while True:
            header = handle.readline()

            if not header:
                break

            sequence = handle.readline()
            plus = handle.readline()
            quality = handle.readline()

            if not (
                sequence
                and plus
                and quality
            ):
                raise ValueError(
                    "truncated FASTQ record"
                )

            if not header.startswith("@"):
                raise ValueError(
                    "invalid FASTQ header"
                )

            read_id = header[1:].split()[0]

            if read_id == wanted_id:
                return sequence.strip().upper()

    raise KeyError(
        f"FASTQ record not found: {wanted_id}"
    )


def main():
    module_source = MODULE.read_text(
        encoding="utf-8",
    )
    compile(
        module_source,
        str(MODULE),
        "exec",
    )

    spec = importlib.util.spec_from_file_location(
        "p3_repeat_explicit_candidate",
        MODULE,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(
            "unable to load explicit repeat module"
        )

    module = importlib.util.module_from_spec(
        spec
    )
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    metrics[
        "candidate_module_contains_sys_argv"
    ] = str(
        "sys.argv" in module_source
    ).lower()

    required_constants = {
        "MIN_REPEAT_BP": 12,
        "MIN_PURITY": 0.70,
        "MIN_PATH_RATIO": 0.75,
        "MAX_PATH_RATIO": 1.25,
        "ENTRY_OFFSET": 5,
        "END_TOLERANCE": 10,
        "MAX_DELETIONS": 1,
        "MATCH_SCORE": 3,
        "MISMATCH_PENALTY": 4,
        "INSERTION_PENALTY": 4,
        "DELETION_PENALTY": 4,
    }

    constant_mismatches = 0

    for name, expected in required_constants.items():
        observed = getattr(module, name)

        if observed != expected:
            constant_mismatches += 1

    metrics[
        "required_constants"
    ] = len(required_constants)
    metrics[
        "constant_mismatches"
    ] = constant_mismatches
    metrics[
        "entry_offset"
    ] = module.ENTRY_OFFSET
    metrics[
        "end_tolerance"
    ] = module.END_TOLERANCE

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
        "sizing_rows"
    ] = len(sizing_rows)
    metrics[
        "positive_contract_rows"
    ] = len(positive_rows)

    if len(positive_rows) != 1:
        raise ValueError(
            "expected exactly one positive row; "
            f"observed {len(positive_rows)}"
        )

    row = positive_rows[0]
    projection_id = row["projection_id"]
    read_id = row["read_id"]

    query_sequence = load_fasta_record(
        QUERY_FASTA,
        projection_id,
    )
    raw_read = load_fastq_record(
        RAW_FASTQ,
        read_id,
    )

    raw_clip_start = int(
        row["raw_clip_start"]
    )
    raw_clip_end = int(
        row["raw_clip_end"]
    )
    raw_clip = raw_read[
        raw_clip_start:raw_clip_end
    ]

    if (
        row["orientation_transform"]
        == "AS_RAW"
    ):
        oriented_clip = raw_clip

    elif (
        row["orientation_transform"]
        == "REVERSE_COMPLEMENT"
    ):
        oriented_clip = (
            module.reverse_complement(
                raw_clip
            )
        )

    else:
        raise ValueError(
            "unexpected orientation transform: "
            + row["orientation_transform"]
        )

    raw_clip_length_match = (
        len(raw_clip)
        == int(row["raw_clip_bp"])
    )
    query_length_match = (
        len(query_sequence)
        == int(row["query_sequence_bp"])
    )
    query_prefix_match = (
        oriented_clip[
            :len(query_sequence)
        ]
        == query_sequence
    )

    metrics[
        "raw_clip_length_matches"
    ] = str(
        raw_clip_length_match
    ).lower()
    metrics[
        "query_sequence_length_matches"
    ] = str(
        query_length_match
    ).lower()
    metrics[
        "query_prefix_matches_oriented_clip"
    ] = str(
        query_prefix_match
    ).lower()

    if not (
        raw_clip_length_match
        and query_length_match
        and query_prefix_match
    ):
        raise ValueError(
            "raw/query sequence contract mismatch"
        )

    motif = module.canonical_motif(
        row["canonical_motif"]
    )
    target_entry_query = int(
        row["target_entry_query_offset"]
    )

    minimum_start = max(
        0,
        target_entry_query
        - module.ENTRY_OFFSET,
    )
    maximum_start = min(
        len(oriented_clip),
        target_entry_query
        + module.ENTRY_OFFSET,
    )

    best_tract = None

    for tract_start in range(
        minimum_start,
        maximum_start + 1,
    ):
        call = (
            module.longest_valid_periodic_prefix(
                oriented_clip[
                    tract_start:
                ],
                motif,
            )
        )

        if call is None:
            continue

        tract_end = (
            tract_start
            + call["prefix_bp"]
        )
        reaches_end = (
            len(oriented_clip)
            - tract_end
            <= module.END_TOLERANCE
        )
        candidate = dict(call)
        candidate.update(
            {
                "tract_start":
                    tract_start,
                "tract_end":
                    tract_end,
                "entry_offset":
                    tract_start
                    - target_entry_query,
                "reaches_clip_end":
                    reaches_end,
            }
        )

        rank = (
            candidate["prefix_bp"],
            candidate["purity"],
            candidate["score"],
            -abs(
                candidate[
                    "entry_offset"
                ]
            ),
        )

        if (
            best_tract is None
            or rank > best_tract["_rank"]
        ):
            candidate["_rank"] = rank
            best_tract = candidate

    if best_tract is None:
        raise ValueError(
            "explicit repeat core did not "
            "recover the positive tract"
        )

    (
        tract_raw_start,
        tract_raw_end,
    ) = module.oriented_to_raw_interval(
        best_tract["tract_start"],
        best_tract["tract_end"],
        raw_clip_start,
        raw_clip_end,
        row["orientation_transform"],
    )

    target_side = row[
        "target_facing_genomic_side"
    ]

    if best_tract[
        "reaches_clip_end"
    ]:
        sizing_status = "lower_bound"
        evidence_class = (
            "LEFT_ANCHORED_CENSORED_RIGHT"
            if target_side
            == "GENOMIC_RIGHT"
            else "RIGHT_ANCHORED_CENSORED_LEFT"
        )
    else:
        sizing_status = (
            "partial_internal"
        )
        evidence_class = (
            "LEFT_ONLY_INTERNAL"
            if target_side
            == "GENOMIC_RIGHT"
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
                best_tract[
                    "observed_units"
                ]
            ),
        "repeat_units_motif_path":
            "{:.6f}".format(
                best_tract[
                    "path_units"
                ]
            ),
        "motif_path_to_read_units_ratio":
            "{:.6f}".format(
                best_tract[
                    "path_ratio"
                ]
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
            best_tract[
                "orientation"
            ],
        "entry_offset_selected_bp":
            best_tract[
                "entry_offset"
            ],
        "distance_from_tract_to_oriented_clip_end_bp":
            len(oriented_clip)
            - best_tract["tract_end"],
        "tract_reaches_expected_raw_end":
            str(
                best_tract[
                    "reaches_clip_end"
                ]
            ).lower(),
        "evidence_class":
            evidence_class,
        "sizing_status":
            sizing_status,
    }

    replay_rows = []
    field_mismatches = 0

    for field in COMPARISON_FIELDS:
        expected = str(row[field])
        observed = str(produced[field])
        matches = expected == observed

        if not matches:
            field_mismatches += 1

        replay_rows.append(
            {
                "projection_id":
                    projection_id,
                "field":
                    field,
                "expected":
                    expected,
                "produced":
                    observed,
                "matches":
                    str(matches).lower(),
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

    if metrics[
        "candidate_module_contains_sys_argv"
    ] != "false":
        return "REVIEW"

    if constant_mismatches:
        return "REVIEW"

    if field_mismatches:
        return "REVIEW"

    return "PASS"


status = "ERROR"

try:
    status = main()
    ERROR.write_text(
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
    ERROR.write_text(
        traceback.format_exc(),
        encoding="utf-8",
    )

metrics[
    "explicit_repeat_core_validation_status"
] = status

with QC.open(
    "w",
    encoding="utf-8",
) as handle:
    handle.write("metric\tvalue\n")

    ordered_keys = [
        "validation_strategy",
        "candidate_module_contains_sys_argv",
        "required_constants",
        "constant_mismatches",
        "entry_offset",
        "end_tolerance",
        "sizing_rows",
        "positive_contract_rows",
        "raw_clip_length_matches",
        "query_sequence_length_matches",
        "query_prefix_matches_oriented_clip",
        "positive_cases_replayed",
        "comparison_fields_expected",
        "comparison_fields",
        "field_mismatches",
        "validation_error_type",
        "validation_error_message",
        "explicit_repeat_core_validation_status",
    ]

    for key in ordered_keys:
        handle.write(
            "{}\t{}\n".format(
                key,
                metrics.get(key, "."),
            )
        )
PY

python -m py_compile "$MODULE"
python -m py_compile "$VALIDATOR"

rm -f \
  "$REPLAY" \
  "$QC" \
  "$ERROR_REPORT" \
  "$MANIFEST"

python "$VALIDATOR" \
  "$MODULE" \
  "$SIZING" \
  "$QUERY_FASTA" \
  "$RAW_FASTQ" \
  "$REPLAY" \
  "$QC" \
  "$ERROR_REPORT"

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in \
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
      "$MODULE" \
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
      $1 == "explicit_repeat_core_validation_status" {
        print $2
      }
    ' "$QC"
)"

if [[ "$status" != "PASS" ]]; then
    echo
    echo "Validation did not PASS; inspect QC and error report." >&2
    exit 1
fi
