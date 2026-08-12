#!/usr/bin/env bash
set -euo pipefail

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
fi

conda activate rnatr-v03
source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"

PAIR_META_ALL="$PROJECT_ROOT/results/11_p3_bridge_feasibility/$RUN_ID/p3_bridge_pair_metadata.tsv.gz"
PAIR_EXPECTED="$PROJECT_ROOT/results/11_production_p3_pair_projection_fix/$RUN_ID/p3_pair_alignment_projection_replay.corrected.tsv"
REPEAT_EXPECTED="$PROJECT_ROOT/results/11_production_p3_repeat/$RUN_ID/p3_repeat_measurement_replay.tsv"
DECISION_EXPECTED="$PROJECT_ROOT/results/11_production_p3_batch/$RUN_ID/p3_production_replay.tsv"
FROZEN_EXPECTED="$PROJECT_ROOT/results/11_p3_orientation_freeze/$RUN_ID/p3_orientation_corrected_classification.tsv"

E2E_REPLAY="$PROJECT_ROOT/results/11_production_p3_end_to_end/$RUN_ID/p3_end_to_end_replay.tsv"
E2E_COMPARISON="$PROJECT_ROOT/results/11_production_p3_end_to_end/$RUN_ID/p3_end_to_end_field_comparison.tsv"
E2E_QC="$PROJECT_ROOT/qc/11_production_p3_end_to_end/$RUN_ID/p3_end_to_end_pipeline.qc.tsv"

PACKAGE_PIPELINE="$PROJECT_ROOT/src/rnatr_scout/p3_pipeline.py"
UNIT_PIPELINE="$PROJECT_ROOT/tests/unit/test_p3_pipeline.py"

OUTDIR="$PROJECT_ROOT/results/11_production_p3_end_to_end_finalize/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_production_p3_end_to_end_finalize/$RUN_ID"

PAIR_META_SELECTED="$OUTDIR/p3_bridge_pair_metadata.selected23.tsv.gz"
SELECTION_AUDIT="$OUTDIR/p3_bridge_pair_metadata.selection_audit.tsv"
SOURCE_AUDIT="$OUTDIR/p3_end_to_end_source_id_audit.tsv"
QC="$QCDIR/p3_end_to_end_finalization.qc.tsv"
MANIFEST="$OUTDIR/${RUN_ID}.p3_end_to_end_finalization.manifest.tsv"

mkdir -p "$OUTDIR" "$QCDIR"

for path in \
  "$PAIR_META_ALL" \
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
  "$PAIR_META_ALL" \
  "$PAIR_EXPECTED" \
  "$REPEAT_EXPECTED" \
  "$DECISION_EXPECTED" \
  "$FROZEN_EXPECTED" \
  "$E2E_REPLAY" \
  "$E2E_COMPARISON" \
  "$E2E_QC" \
  "$PACKAGE_PIPELINE" \
  "$UNIT_PIPELINE" \
  "$PAIR_META_SELECTED" \
  "$SELECTION_AUDIT" \
  "$SOURCE_AUDIT" \
  "$QC" <<'PY'
from __future__ import annotations

import csv
import gzip
import sys
from collections import Counter
from pathlib import Path

(
    pair_meta_all_text,
    pair_expected_text,
    repeat_expected_text,
    decision_expected_text,
    frozen_expected_text,
    e2e_replay_text,
    e2e_comparison_text,
    e2e_qc_text,
    package_pipeline_text,
    unit_pipeline_text,
    pair_meta_selected_text,
    selection_audit_text,
    source_audit_text,
    qc_text,
) = sys.argv[1:]

PAIR_META_ALL = Path(pair_meta_all_text)
PAIR_EXPECTED = Path(pair_expected_text)
REPEAT_EXPECTED = Path(repeat_expected_text)
DECISION_EXPECTED = Path(decision_expected_text)
FROZEN_EXPECTED = Path(frozen_expected_text)
E2E_REPLAY = Path(e2e_replay_text)
E2E_COMPARISON = Path(e2e_comparison_text)
E2E_QC = Path(e2e_qc_text)
PACKAGE_PIPELINE = Path(package_pipeline_text)
UNIT_PIPELINE = Path(unit_pipeline_text)
PAIR_META_SELECTED = Path(pair_meta_selected_text)
SELECTION_AUDIT = Path(selection_audit_text)
SOURCE_AUDIT = Path(source_audit_text)
QC = Path(qc_text)


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


def read_metrics(path: Path) -> dict[str, str]:
    return {
        row["metric"]: row["value"]
        for row in read_tsv(path)
    }


pair_meta_rows = read_tsv(PAIR_META_ALL)
pair_expected_rows = read_tsv(PAIR_EXPECTED)
repeat_expected_rows = read_tsv(REPEAT_EXPECTED)
decision_expected_rows = read_tsv(DECISION_EXPECTED)
frozen_rows = read_tsv(FROZEN_EXPECTED)
replay_rows = read_tsv(E2E_REPLAY)
comparison_rows = read_tsv(E2E_COMPARISON)
original_metrics = read_metrics(E2E_QC)

if not pair_meta_rows:
    raise SystemExit(
        "Pair metadata is empty"
    )

metadata_fields = list(
    pair_meta_rows[0].keys()
)

for required_field in (
    "projection_id",
    "read_id",
    "reference_id",
):
    if required_field not in metadata_fields:
        raise SystemExit(
            f"Pair metadata lacks {required_field}"
        )

metadata_lookup: dict[
    str,
    dict[str, str],
] = {}
duplicate_metadata_ids = set()

for row in pair_meta_rows:
    projection_id = row["projection_id"]

    if projection_id in metadata_lookup:
        duplicate_metadata_ids.add(
            projection_id
        )
    else:
        metadata_lookup[
            projection_id
        ] = row

if duplicate_metadata_ids:
    raise SystemExit(
        "Duplicate projection IDs in full metadata: "
        + ",".join(
            sorted(duplicate_metadata_ids)
        )
    )

expected_order = [
    row["projection_id"]
    for row in frozen_rows
]
expected_ids = set(expected_order)

if len(expected_order) != 23:
    raise SystemExit(
        "Frozen table does not contain 23 rows"
    )

if len(expected_ids) != 23:
    raise SystemExit(
        "Frozen table does not contain 23 unique IDs"
    )

missing_selected_ids = (
    expected_ids - set(metadata_lookup)
)
extra_full_metadata_ids = (
    set(metadata_lookup) - expected_ids
)

if missing_selected_ids:
    raise SystemExit(
        "Expected metadata IDs are missing: "
        + ",".join(
            sorted(missing_selected_ids)
        )
    )

selected_rows = [
    metadata_lookup[projection_id]
    for projection_id in expected_order
]

with gzip.open(
    PAIR_META_SELECTED,
    "wt",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=metadata_fields,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(selected_rows)

selected_reloaded = read_tsv(
    PAIR_META_SELECTED
)
selected_ids = {
    row["projection_id"]
    for row in selected_reloaded
}

selection_audit_rows = [
    {
        "metric":
            "full_metadata_physical_rows",
        "value":
            len(pair_meta_rows),
    },
    {
        "metric":
            "full_metadata_unique_ids",
        "value":
            len(metadata_lookup),
    },
    {
        "metric":
            "full_metadata_duplicate_ids",
        "value":
            len(duplicate_metadata_ids),
    },
    {
        "metric":
            "selected_metadata_physical_rows",
        "value":
            len(selected_reloaded),
    },
    {
        "metric":
            "selected_metadata_unique_ids",
        "value":
            len(selected_ids),
    },
    {
        "metric":
            "missing_selected_ids",
        "value":
            len(
                expected_ids
                - selected_ids
            ),
    },
    {
        "metric":
            "unexpected_selected_ids",
        "value":
            len(
                selected_ids
                - expected_ids
            ),
    },
    {
        "metric":
            "unused_full_metadata_ids",
        "value":
            len(extra_full_metadata_ids),
    },
    {
        "metric":
            "selection_id_set_matches",
        "value":
            str(
                selected_ids
                == expected_ids
            ).lower(),
    },
]

write_tsv(
    SELECTION_AUDIT,
    [
        "metric",
        "value",
    ],
    selection_audit_rows,
)


def source_id_audit(
    name: str,
    rows: list[dict[str, str]],
    relation: str,
) -> dict[str, object]:
    ids = [
        row["projection_id"]
        for row in rows
    ]
    unique_ids = set(ids)
    duplicate_ids = len(ids) - len(
        unique_ids
    )

    if relation == "exact":
        relation_ok = (
            unique_ids == expected_ids
        )
    elif relation == "superset":
        relation_ok = (
            expected_ids <= unique_ids
        )
    else:
        raise ValueError(
            f"Unknown relation: {relation}"
        )

    return {
        "source_name": name,
        "physical_rows": len(rows),
        "unique_projection_ids":
            len(unique_ids),
        "duplicate_rows":
            duplicate_ids,
        "missing_expected_ids":
            len(expected_ids - unique_ids),
        "extra_ids":
            len(unique_ids - expected_ids),
        "required_relation":
            relation,
        "relation_satisfied":
            str(relation_ok).lower(),
    }


source_audit_rows = [
    source_id_audit(
        "pair_metadata_full",
        pair_meta_rows,
        "superset",
    ),
    source_id_audit(
        "pair_metadata_selected",
        selected_reloaded,
        "exact",
    ),
    source_id_audit(
        "pair_expected",
        pair_expected_rows,
        "exact",
    ),
    source_id_audit(
        "repeat_expected",
        repeat_expected_rows,
        "exact",
    ),
    source_id_audit(
        "decision_expected",
        decision_expected_rows,
        "exact",
    ),
    source_id_audit(
        "frozen_expected",
        frozen_rows,
        "exact",
    ),
    source_id_audit(
        "end_to_end_replay",
        replay_rows,
        "exact",
    ),
]

write_tsv(
    SOURCE_AUDIT,
    [
        "source_name",
        "physical_rows",
        "unique_projection_ids",
        "duplicate_rows",
        "missing_expected_ids",
        "extra_ids",
        "required_relation",
        "relation_satisfied",
    ],
    source_audit_rows,
)

comparison_mismatches = sum(
    row["matches"] != "true"
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
projection_counts = Counter(
    row["pair_projection_status"]
    for row in replay_rows
)
repeat_class_counts = Counter(
    row["repeat_measurement_class"]
    for row in replay_rows
)
repeat_sizing_counts = Counter(
    row["repeat_sizing_status"]
    for row in replay_rows
)

standard_evidence_rows = sum(
    row["standard_evidence_emitted"]
    == "true"
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

zero_original_metrics = [
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
    for metric in zero_original_metrics
    if original_metrics.get(metric) != "0"
}

package_syntax_ok = True

for path in (
    PACKAGE_PIPELINE,
    UNIT_PIPELINE,
):
    try:
        compile(
            path.read_text(
                encoding="utf-8",
            ),
            str(path),
            "exec",
        )
    except SyntaxError:
        package_syntax_ok = False

all_source_relations_satisfied = all(
    row["relation_satisfied"]
    == "true"
    for row in source_audit_rows
)

status = "PASS"

if not all(
    [
        len(pair_meta_rows) == 1007,
        len(metadata_lookup) == 1007,
        len(duplicate_metadata_ids) == 0,
        len(selected_reloaded) == 23,
        selected_ids == expected_ids,
        len(extra_full_metadata_ids) == 984,
        all_source_relations_satisfied,
        len(replay_rows) == 23,
        len(comparison_rows) == 713,
        comparison_mismatches == 0,
        len(nonzero_original_metrics) == 0,
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
        projection_counts[
            "UNEXPECTED_REVERSE_ALIGNMENT"
        ] == 22,
        projection_counts[
            "TARGET_ENTRY_PROJECTED"
        ] == 1,
        repeat_class_counts[
            "P3_BRIDGE_ONLY_NO_TARGET_ENTRY_REPEAT_TRACT"
        ] == 22,
        repeat_class_counts[
            "LEFT_ONLY_INTERNAL"
        ] == 1,
        repeat_sizing_counts[
            "no_call"
        ] == 22,
        repeat_sizing_counts[
            "partial_internal"
        ] == 1,
        standard_evidence_rows == 0,
        repeat_estimate_rows == 0,
        repeat_lower_bound_rows == 0,
        bad_allele_status_rows == 0,
        bad_expansion_status_rows == 0,
        package_syntax_ok,
    ]
):
    status = "REVIEW"

with QC.open(
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
        "original_review_cause\t"
        "PAIR_METADATA_IS_INTENTIONAL_1007_ROW_SUPERSET\n"
    )
    handle.write(
        "full_metadata_rows\t{}\n".format(
            len(pair_meta_rows)
        )
    )
    handle.write(
        "full_metadata_unique_ids\t{}\n".format(
            len(metadata_lookup)
        )
    )
    handle.write(
        "full_metadata_duplicate_ids\t{}\n".format(
            len(duplicate_metadata_ids)
        )
    )
    handle.write(
        "selected_metadata_rows\t{}\n".format(
            len(selected_reloaded)
        )
    )
    handle.write(
        "selected_metadata_unique_ids\t{}\n".format(
            len(selected_ids)
        )
    )
    handle.write(
        "unused_full_metadata_ids\t{}\n".format(
            len(extra_full_metadata_ids)
        )
    )
    handle.write(
        "selected_metadata_id_set_matches\t{}\n".format(
            str(
                selected_ids
                == expected_ids
            ).lower()
        )
    )
    handle.write(
        "all_source_relations_satisfied\t{}\n".format(
            str(
                all_source_relations_satisfied
            ).lower()
        )
    )
    handle.write(
        "pipeline_rows\t{}\n".format(
            len(replay_rows)
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
            standard_evidence_rows
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
        "p3_end_to_end_finalization_status\t{}\n".format(
            status
        )
    )

if status != "PASS":
    raise SystemExit(
        "P3 end-to-end finalization requires review"
    )
PY

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in \
      "$PAIR_META_SELECTED" \
      "$SELECTION_AUDIT" \
      "$SOURCE_AUDIT" \
      "$QC"
    do
        if [[ "$path" == *.gz ]]; then
            rows="$(
              gzip -cd "$path" \
                | awk 'END {print NR-1}'
            )"
        else
            rows="$(
              awk 'END {print NR-1}' "$path"
            )"
        fi

        printf '%s\t%s\t%s\t%s\t%s\n' \
          "$(basename "$path")" \
          "$rows" \
          "$(stat -c '%s' "$path")" \
          "$(sha256sum "$path" | awk '{print $1}')" \
          "$path"
    done
} > "$MANIFEST"

echo "===== FINALIZATION QC ====="
column -ts $'\t' "$QC"

echo
echo "===== METADATA SELECTION AUDIT ====="
column -ts $'\t' "$SELECTION_AUDIT"

echo
echo "===== SOURCE ID AUDIT ====="
column -ts $'\t' "$SOURCE_AUDIT"

echo
echo "===== SELECTED METADATA PREVIEW ====="
gzip -cd "$PAIR_META_SELECTED" \
  | head -n 6 \
  | column -ts $'\t'

echo
echo "===== MANIFEST ====="
column -ts $'\t' "$MANIFEST"
