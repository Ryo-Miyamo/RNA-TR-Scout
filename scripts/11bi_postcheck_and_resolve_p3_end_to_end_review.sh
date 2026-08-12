#!/usr/bin/env bash
set -euo pipefail

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
fi

conda activate rnatr-v03
source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"

PAIR_META="$PROJECT_ROOT/results/11_p3_bridge_feasibility/$RUN_ID/p3_bridge_pair_metadata.tsv.gz"
PAIR_EXPECTED="$PROJECT_ROOT/results/11_production_p3_pair_projection_fix/$RUN_ID/p3_pair_alignment_projection_replay.corrected.tsv"
REPEAT_EXPECTED="$PROJECT_ROOT/results/11_production_p3_repeat/$RUN_ID/p3_repeat_measurement_replay.tsv"
DECISION_EXPECTED="$PROJECT_ROOT/results/11_production_p3_batch/$RUN_ID/p3_production_replay.tsv"
FROZEN_EXPECTED="$PROJECT_ROOT/results/11_p3_orientation_freeze/$RUN_ID/p3_orientation_corrected_classification.tsv"

E2E_REPLAY="$PROJECT_ROOT/results/11_production_p3_end_to_end/$RUN_ID/p3_end_to_end_replay.tsv"
E2E_COMPARISON="$PROJECT_ROOT/results/11_production_p3_end_to_end/$RUN_ID/p3_end_to_end_field_comparison.tsv"
E2E_QC="$PROJECT_ROOT/qc/11_production_p3_end_to_end/$RUN_ID/p3_end_to_end_pipeline.qc.tsv"

PACKAGE_PIPELINE="$PROJECT_ROOT/src/rnatr_scout/p3_pipeline.py"
UNIT_PIPELINE="$PROJECT_ROOT/tests/unit/test_p3_pipeline.py"

OUTDIR="$PROJECT_ROOT/results/11_production_p3_end_to_end_postcheck/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_production_p3_end_to_end_postcheck/$RUN_ID"

INPUT_AUDIT="$OUTDIR/p3_end_to_end_input_audit.tsv"
DUPLICATE_AUDIT="$OUTDIR/p3_end_to_end_duplicate_audit.tsv"
TRIGGERS="$OUTDIR/p3_end_to_end_original_review_triggers.tsv"
POSTCHECK="$QCDIR/p3_end_to_end_postcheck.qc.tsv"
MANIFEST="$OUTDIR/${RUN_ID}.p3_end_to_end_postcheck.manifest.tsv"

mkdir -p "$OUTDIR" "$QCDIR"

for path in \
  "$PAIR_META" \
  "$PAIR_EXPECTED" \
  "$REPEAT_EXPECTED" \
  "$DECISION_EXPECTED" \
  "$FROZEN_EXPECTED" \
  "$E2E_REPLAY" \
  "$E2E_COMPARISON" \
  "$E2E_QC" \
  "$PACKAGE_PIPELINE" \
  "$UNIT_PIPELINE"
do
    test -s "$path" || {
        echo "ERROR: missing required artifact: $path" >&2
        exit 1
    }
done

python - \
  "$PAIR_META" \
  "$PAIR_EXPECTED" \
  "$REPEAT_EXPECTED" \
  "$DECISION_EXPECTED" \
  "$FROZEN_EXPECTED" \
  "$E2E_REPLAY" \
  "$E2E_COMPARISON" \
  "$E2E_QC" \
  "$PACKAGE_PIPELINE" \
  "$UNIT_PIPELINE" \
  "$INPUT_AUDIT" \
  "$DUPLICATE_AUDIT" \
  "$TRIGGERS" \
  "$POSTCHECK" <<'PY'
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

(
    pair_meta_text,
    pair_expected_text,
    repeat_expected_text,
    decision_expected_text,
    frozen_expected_text,
    replay_text,
    comparison_text,
    original_qc_text,
    package_pipeline_text,
    unit_pipeline_text,
    input_audit_text,
    duplicate_audit_text,
    triggers_text,
    postcheck_text,
) = sys.argv[1:]

PAIR_META = Path(pair_meta_text)
PAIR_EXPECTED = Path(pair_expected_text)
REPEAT_EXPECTED = Path(repeat_expected_text)
DECISION_EXPECTED = Path(decision_expected_text)
FROZEN_EXPECTED = Path(frozen_expected_text)
REPLAY = Path(replay_text)
COMPARISON = Path(comparison_text)
ORIGINAL_QC = Path(original_qc_text)
PACKAGE_PIPELINE = Path(package_pipeline_text)
UNIT_PIPELINE = Path(unit_pipeline_text)
INPUT_AUDIT = Path(input_audit_text)
DUPLICATE_AUDIT = Path(duplicate_audit_text)
TRIGGERS = Path(triggers_text)
POSTCHECK = Path(postcheck_text)


def open_text(path: Path):
    if path.suffix == ".gz":
        return gzip.open(
            path,
            "rt",
            encoding="utf-8",
            newline="",
        )

    return path.open(
        "r",
        encoding="utf-8",
        newline="",
    )


def read_tsv(path: Path) -> list[dict[str, str]]:
    with open_text(path) as handle:
        return list(
            csv.DictReader(
                handle,
                delimiter="\t",
            )
        )


def write_tsv(
    path: Path,
    fields: list[str],
    rows: list[dict[str, object]],
) -> None:
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


def canonical_row(row: dict[str, str]) -> str:
    return json.dumps(
        row,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def audit_table(
    *,
    name: str,
    path: Path,
    expected_ids: set[str],
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    dict[str, object],
]:
    rows = read_tsv(path)

    if rows and "projection_id" not in rows[0]:
        raise ValueError(
            f"{name} lacks projection_id"
        )

    grouped: dict[
        str,
        list[dict[str, str]],
    ] = defaultdict(list)

    for row in rows:
        grouped[
            row["projection_id"]
        ].append(row)

    observed_ids = set(grouped)
    duplicate_ids = {
        projection_id
        for projection_id, group
        in grouped.items()
        if len(group) > 1
    }
    conflicting_duplicate_ids = set()
    exact_duplicate_rows = 0
    duplicate_rows = []

    for projection_id in sorted(
        duplicate_ids
    ):
        group = grouped[projection_id]
        variants = {
            canonical_row(row)
            for row in group
        }

        if len(variants) > 1:
            conflicting_duplicate_ids.add(
                projection_id
            )
            duplicate_type = (
                "CONFLICTING_DUPLICATE_ID"
            )
        else:
            exact_duplicate_rows += (
                len(group) - 1
            )
            duplicate_type = (
                "EXACT_DUPLICATE_ROWS"
            )

        duplicate_rows.append(
            {
                "source_name": name,
                "projection_id":
                    projection_id,
                "rows_for_id":
                    len(group),
                "unique_row_variants":
                    len(variants),
                "duplicate_type":
                    duplicate_type,
            }
        )

    missing_ids = expected_ids - observed_ids
    extra_ids = observed_ids - expected_ids

    audit_row = {
        "source_name": name,
        "path": str(path),
        "physical_rows": len(rows),
        "unique_projection_ids":
            len(observed_ids),
        "duplicate_projection_ids":
            len(duplicate_ids),
        "exact_duplicate_rows":
            exact_duplicate_rows,
        "conflicting_duplicate_ids":
            len(conflicting_duplicate_ids),
        "missing_expected_ids":
            len(missing_ids),
        "extra_unexpected_ids":
            len(extra_ids),
        "id_set_matches_expected":
            str(
                observed_ids == expected_ids
            ).lower(),
    }

    details = {
        "rows": rows,
        "observed_ids": observed_ids,
        "missing_ids": missing_ids,
        "extra_ids": extra_ids,
        "conflicting_duplicate_ids":
            conflicting_duplicate_ids,
        "exact_duplicate_rows":
            exact_duplicate_rows,
    }

    return [audit_row], duplicate_rows, details


def read_metric_tsv(path: Path) -> dict[str, str]:
    metrics = {}

    with path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        reader = csv.DictReader(
            handle,
            delimiter="\t",
        )

        for row in reader:
            metrics[row["metric"]] = row[
                "value"
            ]

    return metrics


frozen_rows = read_tsv(
    FROZEN_EXPECTED
)
expected_ids = {
    row["projection_id"]
    for row in frozen_rows
}

sources = [
    (
        "pair_metadata",
        PAIR_META,
    ),
    (
        "pair_expected",
        PAIR_EXPECTED,
    ),
    (
        "repeat_expected",
        REPEAT_EXPECTED,
    ),
    (
        "decision_expected",
        DECISION_EXPECTED,
    ),
    (
        "frozen_expected",
        FROZEN_EXPECTED,
    ),
]

input_audit_rows = []
duplicate_audit_rows = []
source_details = {}

for name, path in sources:
    audit_rows, duplicate_rows, details = (
        audit_table(
            name=name,
            path=path,
            expected_ids=expected_ids,
        )
    )
    input_audit_rows.extend(
        audit_rows
    )
    duplicate_audit_rows.extend(
        duplicate_rows
    )
    source_details[name] = details

write_tsv(
    INPUT_AUDIT,
    [
        "source_name",
        "path",
        "physical_rows",
        "unique_projection_ids",
        "duplicate_projection_ids",
        "exact_duplicate_rows",
        "conflicting_duplicate_ids",
        "missing_expected_ids",
        "extra_unexpected_ids",
        "id_set_matches_expected",
    ],
    input_audit_rows,
)

write_tsv(
    DUPLICATE_AUDIT,
    [
        "source_name",
        "projection_id",
        "rows_for_id",
        "unique_row_variants",
        "duplicate_type",
    ],
    duplicate_audit_rows,
)

replay_rows = read_tsv(REPLAY)
comparison_rows = read_tsv(
    COMPARISON
)
original_metrics = read_metric_tsv(
    ORIGINAL_QC
)

replay_ids = {
    row["projection_id"]
    for row in replay_rows
}
comparison_ids = {
    row["projection_id"]
    for row in comparison_rows
}

comparison_mismatches = sum(
    row.get("matches") != "true"
    for row in comparison_rows
)

primary_counts = Counter(
    row["primary_status"]
    for row in replay_rows
)
failure_counts = Counter(
    row["failure_code"]
    for row in replay_rows
)
pair_projection_counts = Counter(
    row["pair_projection_status"]
    for row in replay_rows
)
repeat_measurement_counts = Counter(
    row["repeat_measurement_class"]
    for row in replay_rows
)
repeat_sizing_counts = Counter(
    row["repeat_sizing_status"]
    for row in replay_rows
)

emitted_rows = sum(
    row[
        "standard_evidence_emitted"
    ] == "true"
    for row in replay_rows
)
repeat_estimate_rows = sum(
    row["repeat_bp_estimate"] != "."
    for row in replay_rows
)
repeat_lower_bound_rows = sum(
    row["repeat_bp_lower_bound"] != "."
    for row in replay_rows
)
bad_allele_status_rows = sum(
    row["allele_length_status"]
    != "NOT_MEASURABLE_ONE_FLANK_P3"
    for row in replay_rows
)
bad_expansion_status_rows = sum(
    row["expansion_status"]
    != "NOT_ASSESSED"
    for row in replay_rows
)

zero_qc_metrics = [
    "missing_metadata_rows",
    "missing_query_rows",
    "missing_reference_rows",
    "missing_raw_reads",
    "orientation_transform_mismatches",
    "query_prefix_mismatches",
    "pair_projection_status_mismatches",
    "pair_query_offset_mismatches",
    "repeat_field_mismatches",
    "decision_field_mismatches",
    "frozen_status_mismatches",
    "frozen_emission_mismatches",
    "guardrail_failures",
    "standard_p3_evidence_emitted",
]

nonzero_original_metrics = {
    metric: original_metrics.get(
        metric,
        "<MISSING>",
    )
    for metric in zero_qc_metrics
    if original_metrics.get(metric) != "0"
}

original_trigger_rows = []


def add_trigger(
    name: str,
    observed: object,
    expected: object,
) -> None:
    original_trigger_rows.append(
        {
            "predicate": name,
            "observed": observed,
            "expected": expected,
            "triggered": str(
                str(observed)
                != str(expected)
            ).lower(),
        }
    )


add_trigger(
    "unique_expected_ids",
    len(expected_ids),
    23,
)

for audit_row in input_audit_rows:
    add_trigger(
        "physical_rows::"
        + str(
            audit_row["source_name"]
        ),
        audit_row["physical_rows"],
        23,
    )

add_trigger(
    "pipeline_rows",
    len(replay_rows),
    23,
)
add_trigger(
    "total_field_comparisons",
    len(comparison_rows),
    713,
)
add_trigger(
    "comparison_mismatches",
    comparison_mismatches,
    0,
)
add_trigger(
    "standard_evidence_emitted",
    emitted_rows,
    0,
)
add_trigger(
    "primary_orientation_reject",
    primary_counts[
        "REJECT_ORIENTATION_INCONSISTENT_BRIDGE"
    ],
    22,
)
add_trigger(
    "primary_homopolymer_review",
    primary_counts[
        "HOMOPOLYMER_REVIEW_NO_STANDARD_P3_EVIDENCE"
    ],
    1,
)
add_trigger(
    "failure_orientation",
    failure_counts[
        "ORIENTATION_INCONSISTENT_BRIDGE"
    ],
    22,
)
add_trigger(
    "failure_homopolymer",
    failure_counts[
        "HOMOPOLYMER_REVIEW"
    ],
    1,
)

write_tsv(
    TRIGGERS,
    [
        "predicate",
        "observed",
        "expected",
        "triggered",
    ],
    original_trigger_rows,
)

triggered_predicates = [
    row
    for row in original_trigger_rows
    if row["triggered"] == "true"
]

all_source_id_sets_match = all(
    details["observed_ids"]
    == expected_ids
    for details in source_details.values()
)
conflicting_duplicates = sum(
    len(
        details[
            "conflicting_duplicate_ids"
        ]
    )
    for details in source_details.values()
)
total_exact_duplicate_rows = sum(
    int(
        details[
            "exact_duplicate_rows"
        ]
    )
    for details in source_details.values()
)

package_syntax_ok = True

for path in (
    PACKAGE_PIPELINE,
    UNIT_PIPELINE,
):
    try:
        compile(
            path.read_text(
                encoding="utf-8"
            ),
            str(path),
            "exec",
        )
    except SyntaxError:
        package_syntax_ok = False

safe_content_pass = all(
    [
        len(expected_ids) == 23,
        all_source_id_sets_match,
        conflicting_duplicates == 0,
        replay_ids == expected_ids,
        comparison_ids == expected_ids,
        len(replay_rows) == 23,
        len(comparison_rows) == 713,
        comparison_mismatches == 0,
        not nonzero_original_metrics,
        primary_counts[
            "REJECT_ORIENTATION_INCONSISTENT_BRIDGE"
        ] == 22,
        primary_counts[
            "HOMOPOLYMER_REVIEW_NO_STANDARD_P3_EVIDENCE"
        ] == 1,
        failure_counts[
            "ORIENTATION_INCONSISTENT_BRIDGE"
        ] == 22,
        failure_counts[
            "HOMOPOLYMER_REVIEW"
        ] == 1,
        pair_projection_counts[
            "UNEXPECTED_REVERSE_ALIGNMENT"
        ] == 22,
        pair_projection_counts[
            "TARGET_ENTRY_PROJECTED"
        ] == 1,
        repeat_measurement_counts[
            "P3_BRIDGE_ONLY_NO_TARGET_ENTRY_REPEAT_TRACT"
        ] == 22,
        repeat_measurement_counts[
            "LEFT_ONLY_INTERNAL"
        ] == 1,
        repeat_sizing_counts[
            "no_call"
        ] == 22,
        repeat_sizing_counts[
            "partial_internal"
        ] == 1,
        emitted_rows == 0,
        repeat_estimate_rows == 0,
        repeat_lower_bound_rows == 0,
        bad_allele_status_rows == 0,
        bad_expansion_status_rows == 0,
        package_syntax_ok,
    ]
)

postcheck_status = (
    "PASS"
    if safe_content_pass
    else "REVIEW"
)

with POSTCHECK.open(
    "w",
    encoding="utf-8",
) as handle:
    handle.write("metric\tvalue\n")
    handle.write(
        "original_pipeline_status\t{}\n".format(
            original_metrics.get(
                "p3_end_to_end_pipeline_status",
                "<MISSING>",
            )
        )
    )
    handle.write(
        "expected_unique_candidates\t{}\n".format(
            len(expected_ids)
        )
    )
    handle.write(
        "all_source_id_sets_match\t{}\n".format(
            str(
                all_source_id_sets_match
            ).lower()
        )
    )
    handle.write(
        "total_exact_duplicate_rows\t{}\n".format(
            total_exact_duplicate_rows
        )
    )
    handle.write(
        "conflicting_duplicate_ids\t{}\n".format(
            conflicting_duplicates
        )
    )
    handle.write(
        "original_triggered_predicates\t{}\n".format(
            len(triggered_predicates)
        )
    )

    for row in triggered_predicates:
        handle.write(
            "trigger::{}\t{}!= {}\n".format(
                row["predicate"],
                row["observed"],
                row["expected"],
            )
        )

    handle.write(
        "pipeline_rows\t{}\n".format(
            len(replay_rows)
        )
    )
    handle.write(
        "pipeline_unique_ids\t{}\n".format(
            len(replay_ids)
        )
    )
    handle.write(
        "comparison_rows\t{}\n".format(
            len(comparison_rows)
        )
    )
    handle.write(
        "comparison_mismatches\t{}\n".format(
            comparison_mismatches
        )
    )
    handle.write(
        "nonzero_original_qc_metrics\t{}\n".format(
            len(nonzero_original_metrics)
        )
    )
    handle.write(
        "standard_evidence_emitted\t{}\n".format(
            emitted_rows
        )
    )
    handle.write(
        "repeat_estimate_rows\t{}\n".format(
            repeat_estimate_rows
        )
    )
    handle.write(
        "repeat_lower_bound_rows\t{}\n".format(
            repeat_lower_bound_rows
        )
    )
    handle.write(
        "bad_allele_status_rows\t{}\n".format(
            bad_allele_status_rows
        )
    )
    handle.write(
        "bad_expansion_status_rows\t{}\n".format(
            bad_expansion_status_rows
        )
    )
    handle.write(
        "primary_orientation_reject\t{}\n".format(
            primary_counts[
                "REJECT_ORIENTATION_INCONSISTENT_BRIDGE"
            ]
        )
    )
    handle.write(
        "primary_homopolymer_review\t{}\n".format(
            primary_counts[
                "HOMOPOLYMER_REVIEW_NO_STANDARD_P3_EVIDENCE"
            ]
        )
    )
    handle.write(
        "package_python_syntax_ok\t{}\n".format(
            str(package_syntax_ok).lower()
        )
    )
    handle.write(
        "p3_end_to_end_postcheck_status\t{}\n".format(
            postcheck_status
        )
    )

if postcheck_status != "PASS":
    raise SystemExit(
        "P3 end-to-end postcheck requires review"
    )
PY

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in \
      "$INPUT_AUDIT" \
      "$DUPLICATE_AUDIT" \
      "$TRIGGERS" \
      "$POSTCHECK"
    do
        printf '%s\t%s\t%s\t%s\t%s\n' \
          "$(basename "$path")" \
          "$(awk 'END {print NR-1}' "$path")" \
          "$(stat -c '%s' "$path")" \
          "$(sha256sum "$path" | awk '{print $1}')" \
          "$path"
    done
} > "$MANIFEST"

echo "===== POSTCHECK QC ====="
column -ts $'\t' "$POSTCHECK"

echo
echo "===== INPUT AUDIT ====="
column -ts $'\t' "$INPUT_AUDIT"

echo
echo "===== ORIGINAL REVIEW TRIGGERS ====="
column -ts $'\t' "$TRIGGERS"

echo
echo "===== DUPLICATE AUDIT ====="
if [[ "$(awk 'END {print NR}' "$DUPLICATE_AUDIT")" -gt 1 ]]; then
    column -ts $'\t' "$DUPLICATE_AUDIT"
else
    echo "No duplicate projection IDs."
fi

echo
echo "===== MANIFEST ====="
column -ts $'\t' "$MANIFEST"
