#!/usr/bin/env bash
set -euo pipefail

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
fi

conda activate rnatr-v03
source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"
MODEL_ID="rnatr_p3_bridge_sequence_specificity_v0.3.1"

PAIR_META="$PROJECT_ROOT/results/11_p3_bridge_feasibility/$RUN_ID/p3_bridge_pair_metadata.tsv.gz"
BATCH_PAF="$PROJECT_ROOT/results/11_p3_bridge_feasibility/$RUN_ID/p3_bridge_candidate_specific_alignments.paf"
ISOLATED="$PROJECT_ROOT/results/11_p3_isolated_pair_validation/$RUN_ID/p3_isolated_pair_validation.tsv.gz"
REFERENCE_FASTA="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_p3_bridge_feasibility/p3_bridge_candidate_references.fasta.gz"

OUTDIR="$PROJECT_ROOT/results/11_p3_bridge_specificity/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_p3_bridge_specificity/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_p3_bridge_specificity/$RUN_ID"

OUTPUT="$OUTDIR/p3_bridge_sequence_specificity.tsv"
SUMMARY="$OUTDIR/p3_bridge_sequence_specificity_summary.tsv"
REFERENCE_GROUPS="$OUTDIR/p3_reference_sequence_groups.tsv"
QC="$QCDIR/p3_bridge_sequence_specificity.qc.tsv"
PARAMETERS="$OUTDIR/${MODEL_ID}.parameters.tsv"
MANIFEST="$OUTDIR/${RUN_ID}.p3_bridge_specificity.manifest.tsv"
PY="$WORKDIR/audit_p3_bridge_specificity.py"

EXPECTED_PAIRS=1007
EXPECTED_POSITIVES=23
EXPECTED_BATCH_PAF_ROWS=61904
EXPECTED_UNIQUE_REFERENCE_SEQUENCES=622

NEAR_BEST_SCORE_FRACTION=0.95

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR"

for path in \
  "$PAIR_META" \
  "$BATCH_PAF" \
  "$ISOLATED" \
  "$REFERENCE_FASTA"
do
    test -s "$path" || {
        echo "ERROR: missing input: $path" >&2
        exit 1
    }
done

cat > "$PARAMETERS" <<EOF
parameter	value	meaning
model_id	$MODEL_ID	Sequence-specificity audit for isolated P3 bridge-positive pairs
positive_definition	isolated_combined_status=BRIDGE_PLUS_TARGET_MOTIF_SIGNAL	23 isolated-pair positives
competitive_alignment_source	$BATCH_PAF	All-query/all-reference minimap2 competition
reference_equivalence	sha256_identical_sequence	Candidate IDs with identical reference sequence are one equivalence group
near_best_score_fraction	$NEAR_BEST_SCORE_FRACTION	Distinct reference groups within 95% of best score
specificity_semantics	expected_sequence_group_vs_all_decoy_groups	This is not genomic uniqueness
call_semantics	specificity_audit_only	No evidence, allele-length, or expansion call
EOF

cat > "$PY" <<'PY'
from __future__ import annotations

import csv
import gzip
import hashlib
import sys
from collections import Counter, defaultdict

import pysam

(
    metadata_path,
    batch_paf_path,
    isolated_path,
    reference_fasta_path,
    output_path,
    summary_path,
    reference_groups_path,
    qc_path,
    model_id,
    expected_pairs_text,
    expected_positives_text,
    expected_paf_rows_text,
    expected_unique_references_text,
    near_best_fraction_text,
) = sys.argv[1:]

EXPECTED_PAIRS = int(expected_pairs_text)
EXPECTED_POSITIVES = int(expected_positives_text)
EXPECTED_PAF_ROWS = int(expected_paf_rows_text)
EXPECTED_UNIQUE_REFERENCES = int(
    expected_unique_references_text
)
NEAR_BEST_FRACTION = float(
    near_best_fraction_text
)


def parse_tags(fields):
    tags = {}

    for field in fields:
        parts = field.split(":", 2)

        if len(parts) != 3:
            continue

        name, value_type, value = parts

        if value_type == "i":
            tags[name] = int(value)
        elif value_type == "f":
            tags[name] = float(value)
        else:
            tags[name] = value

    return tags


with gzip.open(
    metadata_path,
    "rt",
    encoding="utf-8",
    newline="",
) as handle:
    metadata = {
        row["projection_id"]: row
        for row in csv.DictReader(
            handle,
            delimiter="\t",
        )
    }

with gzip.open(
    isolated_path,
    "rt",
    encoding="utf-8",
    newline="",
) as handle:
    isolated_rows = list(
        csv.DictReader(handle, delimiter="\t")
    )

isolated_lookup = {
    row["projection_id"]: row
    for row in isolated_rows
}

positive_ids = {
    row["projection_id"]
    for row in isolated_rows
    if row["isolated_combined_status"]
       == "BRIDGE_PLUS_TARGET_MOTIF_SIGNAL"
}

reference_sequences = {}

with pysam.FastxFile(
    reference_fasta_path
) as source:
    for entry in source:
        reference_sequences[entry.name] = (
            entry.sequence.upper()
        )

reference_id_to_digest = {}
digest_to_reference_ids = defaultdict(list)
digest_to_projection_ids = defaultdict(list)
digest_to_motifs = defaultdict(set)
digest_to_targets = defaultdict(set)

for projection_id, row in metadata.items():
    reference_id = row["reference_id"]
    sequence = reference_sequences.get(reference_id)

    if sequence is None:
        continue

    digest = hashlib.sha256(
        sequence.encode()
    ).hexdigest()

    reference_id_to_digest[reference_id] = digest
    digest_to_reference_ids[digest].append(
        reference_id
    )
    digest_to_projection_ids[digest].append(
        projection_id
    )
    digest_to_motifs[digest].add(
        row["canonical_motif"]
    )
    digest_to_targets[digest].add(
        row["target_region_id"]
    )

missing_reference_ids = {
    row["reference_id"]
    for row in metadata.values()
    if row["reference_id"]
       not in reference_sequences
}

alignments_by_query_digest = defaultdict(
    lambda: defaultdict(list)
)
paf_rows = 0
positive_paf_rows = 0
unknown_reference_ids = set()

with open(
    batch_paf_path,
    "r",
    encoding="utf-8",
) as handle:
    for line in handle:
        line = line.rstrip("\n")

        if not line:
            continue

        paf_rows += 1
        fields = line.split("\t")
        query_id = fields[0]

        if query_id not in positive_ids:
            continue

        positive_paf_rows += 1
        reference_id = fields[5]
        digest = reference_id_to_digest.get(
            reference_id
        )

        if digest is None:
            unknown_reference_ids.add(
                reference_id
            )
            continue

        tags = parse_tags(fields[12:])
        query_length = int(fields[1])
        query_start = int(fields[2])
        query_end = int(fields[3])
        matches = int(fields[9])
        block_length = int(fields[10])

        alignments_by_query_digest[
            query_id
        ][digest].append(
            {
                "reference_id": reference_id,
                "query_length": query_length,
                "query_start": query_start,
                "query_end": query_end,
                "query_coverage": (
                    (query_end - query_start)
                    / query_length
                    if query_length
                    else 0.0
                ),
                "reference_start": int(fields[7]),
                "reference_end": int(fields[8]),
                "identity": (
                    matches / block_length
                    if block_length
                    else 0.0
                ),
                "mapq": int(fields[11]),
                "alignment_score": tags.get(
                    "AS",
                    matches,
                ),
                "alignment_type": tags.get(
                    "tp",
                    ".",
                ),
            }
        )

reference_group_rows = []

for digest in sorted(
    digest_to_reference_ids,
    key=lambda value: (
        -len(digest_to_reference_ids[value]),
        value,
    ),
):
    reference_group_rows.append(
        {
            "reference_sequence_sha256": digest,
            "sequence_multiplicity": len(
                digest_to_reference_ids[digest]
            ),
            "projection_count": len(
                digest_to_projection_ids[digest]
            ),
            "unique_targets": len(
                digest_to_targets[digest]
            ),
            "motifs": ";".join(
                sorted(digest_to_motifs[digest])
            ),
            "reference_ids": ";".join(
                sorted(
                    digest_to_reference_ids[digest]
                )
            ),
            "projection_ids": ";".join(
                sorted(
                    digest_to_projection_ids[digest]
                )
            ),
            "target_region_ids": ";".join(
                sorted(
                    digest_to_targets[digest]
                )
            ),
        }
    )

reference_group_fields = list(
    reference_group_rows[0].keys()
)

with open(
    reference_groups_path,
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=reference_group_fields,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(reference_group_rows)

output_rows = []
counts = Counter()

for projection_id in sorted(positive_ids):
    meta = metadata[projection_id]
    isolated = isolated_lookup[projection_id]
    expected_reference_id = meta["reference_id"]
    expected_digest = (
        reference_id_to_digest[
            expected_reference_id
        ]
    )
    motif = meta["canonical_motif"]

    grouped = alignments_by_query_digest.get(
        projection_id,
        {},
    )

    digest_best = {}

    for digest, rows in grouped.items():
        rows.sort(
            key=lambda row: (
                row["alignment_score"],
                row["query_coverage"],
                row["identity"],
                row["mapq"],
            ),
            reverse=True,
        )
        digest_best[digest] = rows[0]

    ranked_digests = sorted(
        digest_best,
        key=lambda digest: (
            digest_best[digest][
                "alignment_score"
            ],
            digest_best[digest][
                "query_coverage"
            ],
            digest_best[digest]["identity"],
        ),
        reverse=True,
    )

    best_digest = (
        ranked_digests[0]
        if ranked_digests
        else None
    )
    best_score = (
        digest_best[best_digest][
            "alignment_score"
        ]
        if best_digest
        else None
    )

    expected_alignment = digest_best.get(
        expected_digest
    )
    expected_score = (
        expected_alignment[
            "alignment_score"
        ]
        if expected_alignment
        else None
    )

    decoy_digests = [
        digest
        for digest in ranked_digests
        if digest != expected_digest
    ]

    best_decoy_digest = (
        decoy_digests[0]
        if decoy_digests
        else None
    )
    best_decoy = (
        digest_best[best_decoy_digest]
        if best_decoy_digest
        else None
    )
    best_decoy_score = (
        best_decoy["alignment_score"]
        if best_decoy
        else None
    )

    same_motif_decoys = [
        digest
        for digest in decoy_digests
        if motif in digest_to_motifs[digest]
    ]
    best_same_motif_digest = (
        same_motif_decoys[0]
        if same_motif_decoys
        else None
    )
    best_same_motif = (
        digest_best[
            best_same_motif_digest
        ]
        if best_same_motif_digest
        else None
    )

    near_best_digests = []

    if best_score is not None:
        threshold = (
            best_score * NEAR_BEST_FRACTION
        )
        near_best_digests = [
            digest
            for digest in ranked_digests
            if digest_best[digest][
                "alignment_score"
            ] >= threshold
        ]

    expected_rank = (
        ranked_digests.index(
            expected_digest
        ) + 1
        if expected_digest in ranked_digests
        else None
    )

    tied_best_count = (
        sum(
            digest_best[digest][
                "alignment_score"
            ] == best_score
            for digest in ranked_digests
        )
        if best_score is not None
        else 0
    )

    if expected_alignment is None:
        specificity_status = (
            "EXPECTED_SEQUENCE_GROUP_NOT_OBSERVED"
        )

    elif expected_score == best_score:
        if tied_best_count == 1:
            specificity_status = (
                "EXPECTED_SEQUENCE_GROUP_UNIQUE_BEST"
            )
        else:
            specificity_status = (
                "EXPECTED_SEQUENCE_GROUP_TIED_BEST"
            )

    elif (
        best_score is not None
        and expected_score
            >= best_score * NEAR_BEST_FRACTION
    ):
        specificity_status = (
            "EXPECTED_SEQUENCE_GROUP_NEAR_BEST"
        )

    else:
        specificity_status = (
            "DECOY_SEQUENCE_GROUP_OUTSCORES_EXPECTED"
        )

    if (
        best_same_motif is None
        or expected_score is None
    ):
        motif_competition_status = (
            "NO_SAME_MOTIF_DECOY_ALIGNMENT"
        )
    elif (
        best_same_motif[
            "alignment_score"
        ] >= expected_score
            * NEAR_BEST_FRACTION
    ):
        motif_competition_status = (
            "SAME_MOTIF_DECOY_NEAR_EQUIVALENT"
        )
    else:
        motif_competition_status = (
            "EXPECTED_EXCEEDS_SAME_MOTIF_DECOYS"
        )

    if specificity_status == (
        "EXPECTED_SEQUENCE_GROUP_UNIQUE_BEST"
    ) and motif_competition_status != (
        "SAME_MOTIF_DECOY_NEAR_EQUIVALENT"
    ):
        bridge_interpretation = (
            "SEQUENCE_DISCRIMINATIVE_WITHIN_CANDIDATE_REFERENCE_SET"
        )
    elif specificity_status in {
        "EXPECTED_SEQUENCE_GROUP_UNIQUE_BEST",
        "EXPECTED_SEQUENCE_GROUP_TIED_BEST",
        "EXPECTED_SEQUENCE_GROUP_NEAR_BEST",
    }:
        bridge_interpretation = (
            "SEQUENCE_COMPATIBLE_BUT_NOT_CANDIDATE_SET_UNIQUE"
        )
    else:
        bridge_interpretation = (
            "ISOLATED_PAIR_COMPATIBILITY_ONLY"
        )

    counts[
        "specificity::{}".format(
            specificity_status
        )
    ] += 1
    counts[
        "motif_competition::{}".format(
            motif_competition_status
        )
    ] += 1
    counts[
        "interpretation::{}".format(
            bridge_interpretation
        )
    ] += 1

    output_rows.append(
        {
            "model_id": model_id,
            "projection_id": projection_id,
            "read_id": meta["read_id"],
            "target_region_id": meta[
                "target_region_id"
            ],
            "representative_locus_id": meta[
                "representative_locus_id"
            ],
            "canonical_motif": motif,
            "bridge_bp": meta["bridge_bp"],
            "target_entry_bp": meta[
                "target_entry_bp"
            ],
            "query_bp": meta["query_bp"],
            "isolated_identity": isolated[
                "best_identity"
            ],
            "isolated_query_coverage": isolated[
                "best_query_coverage"
            ],
            "isolated_alignment_score": isolated[
                "best_alignment_score"
            ],
            "expected_reference_sha256": (
                expected_digest
            ),
            "expected_sequence_multiplicity": len(
                digest_to_reference_ids[
                    expected_digest
                ]
            ),
            "expected_unique_targets": len(
                digest_to_targets[
                    expected_digest
                ]
            ),
            "competitive_distinct_reference_groups_aligned": len(
                ranked_digests
            ),
            "expected_reference_group_observed": str(
                expected_alignment
                is not None
            ).lower(),
            "expected_reference_group_rank": (
                expected_rank
                if expected_rank is not None
                else "."
            ),
            "expected_alignment_score": (
                expected_score
                if expected_score is not None
                else "."
            ),
            "expected_query_coverage": (
                "{:.6f}".format(
                    expected_alignment[
                        "query_coverage"
                    ]
                )
                if expected_alignment
                else "."
            ),
            "expected_identity": (
                "{:.6f}".format(
                    expected_alignment[
                        "identity"
                    ]
                )
                if expected_alignment
                else "."
            ),
            "best_overall_reference_sha256": (
                best_digest
                if best_digest
                else "."
            ),
            "best_overall_alignment_score": (
                best_score
                if best_score is not None
                else "."
            ),
            "best_decoy_reference_sha256": (
                best_decoy_digest
                if best_decoy_digest
                else "."
            ),
            "best_decoy_alignment_score": (
                best_decoy_score
                if best_decoy_score
                   is not None
                else "."
            ),
            "expected_minus_best_decoy_score": (
                expected_score
                - best_decoy_score
                if (
                    expected_score
                    is not None
                    and best_decoy_score
                    is not None
                )
                else "."
            ),
            "best_same_motif_decoy_sha256": (
                best_same_motif_digest
                if best_same_motif_digest
                else "."
            ),
            "best_same_motif_decoy_score": (
                best_same_motif[
                    "alignment_score"
                ]
                if best_same_motif
                else "."
            ),
            "near_best_distinct_reference_groups": len(
                near_best_digests
            ),
            "tied_best_distinct_reference_groups": (
                tied_best_count
            ),
            "specificity_status": (
                specificity_status
            ),
            "motif_competition_status": (
                motif_competition_status
            ),
            "bridge_specificity_interpretation": (
                bridge_interpretation
            ),
            "evidence_status": "NOT_CALLED",
            "allele_length_status": (
                "NOT_ASSESSED"
            ),
            "expansion_status": "NOT_ASSESSED",
        }
    )

output_fields = list(output_rows[0].keys())

with open(
    output_path,
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=output_fields,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(output_rows)

summary_groups = defaultdict(
    lambda: {
        "rows": 0,
        "reads": set(),
        "targets": set(),
        "multiplicities": [],
        "near_best_counts": [],
        "score_margins": [],
    }
)

for row in output_rows:
    group_names = [
        "ALL",
        "specificity::{}".format(
            row["specificity_status"]
        ),
        "interpretation::{}".format(
            row[
                "bridge_specificity_interpretation"
            ]
        ),
    ]

    for group_name in group_names:
        group = summary_groups[group_name]
        group["rows"] += 1
        group["reads"].add(row["read_id"])
        group["targets"].add(
            row["target_region_id"]
        )
        group["multiplicities"].append(
            int(
                row[
                    "expected_sequence_multiplicity"
                ]
            )
        )
        group["near_best_counts"].append(
            int(
                row[
                    "near_best_distinct_reference_groups"
                ]
            )
        )

        if (
            row[
                "expected_minus_best_decoy_score"
            ] != "."
        ):
            group["score_margins"].append(
                int(
                    row[
                        "expected_minus_best_decoy_score"
                    ]
                )
            )


def median(values):
    if not values:
        return None

    ordered = sorted(values)
    size = len(ordered)

    if size % 2:
        return float(ordered[size // 2])

    return (
        ordered[size // 2 - 1]
        + ordered[size // 2]
    ) / 2.0


summary_fields = [
    "group",
    "rows",
    "unique_reads",
    "unique_targets",
    "expected_sequence_multiplicity_median",
    "near_best_reference_groups_median",
    "expected_minus_best_decoy_score_median",
]

with open(
    summary_path,
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=summary_fields,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()

    for group_name in sorted(summary_groups):
        group = summary_groups[group_name]

        multiplicity_median = median(
            group["multiplicities"]
        )
        near_best_median = median(
            group["near_best_counts"]
        )
        margin_median = median(
            group["score_margins"]
        )

        writer.writerow(
            {
                "group": group_name,
                "rows": group["rows"],
                "unique_reads": len(
                    group["reads"]
                ),
                "unique_targets": len(
                    group["targets"]
                ),
                "expected_sequence_multiplicity_median": (
                    "{:.6f}".format(
                        multiplicity_median
                    )
                ),
                "near_best_reference_groups_median": (
                    "{:.6f}".format(
                        near_best_median
                    )
                ),
                "expected_minus_best_decoy_score_median": (
                    "{:.6f}".format(
                        margin_median
                    )
                    if margin_median
                       is not None
                    else "."
                ),
            }
        )

status = "PASS"

if (
    len(metadata) != EXPECTED_PAIRS
    or len(isolated_rows) != EXPECTED_PAIRS
    or len(positive_ids) != EXPECTED_POSITIVES
    or len(reference_sequences) != EXPECTED_PAIRS
    or len(digest_to_reference_ids)
       != EXPECTED_UNIQUE_REFERENCES
    or paf_rows != EXPECTED_PAF_ROWS
    or missing_reference_ids
    or unknown_reference_ids
    or len(output_rows) != EXPECTED_POSITIVES
):
    status = "REVIEW"

with open(
    qc_path,
    "w",
    encoding="utf-8",
) as handle:
    handle.write("metric\tvalue\n")
    handle.write(
        "expected_pairs\t{}\n".format(
            EXPECTED_PAIRS
        )
    )
    handle.write(
        "metadata_pairs\t{}\n".format(
            len(metadata)
        )
    )
    handle.write(
        "isolated_rows\t{}\n".format(
            len(isolated_rows)
        )
    )
    handle.write(
        "expected_positive_pairs\t{}\n".format(
            EXPECTED_POSITIVES
        )
    )
    handle.write(
        "observed_positive_pairs\t{}\n".format(
            len(positive_ids)
        )
    )
    handle.write(
        "reference_sequences\t{}\n".format(
            len(reference_sequences)
        )
    )
    handle.write(
        "unique_reference_sequences\t{}\n".format(
            len(digest_to_reference_ids)
        )
    )
    handle.write(
        "batch_paf_rows\t{}\n".format(
            paf_rows
        )
    )
    handle.write(
        "positive_query_paf_rows\t{}\n".format(
            positive_paf_rows
        )
    )
    handle.write(
        "missing_reference_ids\t{}\n".format(
            len(missing_reference_ids)
        )
    )
    handle.write(
        "unknown_paf_reference_ids\t{}\n".format(
            len(unknown_reference_ids)
        )
    )
    handle.write(
        "specificity_rows_written\t{}\n".format(
            len(output_rows)
        )
    )

    for key, count in sorted(counts.items()):
        handle.write(
            "{}\t{}\n".format(key, count)
        )

    handle.write("evidence_calls_emitted\t0\n")
    handle.write("allele_length_calls_emitted\t0\n")
    handle.write("expansion_calls_emitted\t0\n")
    handle.write(
        "audit_status\t{}\n".format(status)
    )

if status != "PASS":
    raise SystemExit(
        "P3 bridge specificity audit requires review"
    )
PY

echo "===== SHELL AND EMBEDDED PYTHON SYNTAX ====="
python -m py_compile "$PY"
echo "Embedded Python syntax: OK"

rm -f \
  "$OUTPUT" \
  "$SUMMARY" \
  "$REFERENCE_GROUPS" \
  "$QC" \
  "$MANIFEST"

echo
echo "===== AUDIT P3 BRIDGE SEQUENCE SPECIFICITY ====="

python "$PY" \
  "$PAIR_META" \
  "$BATCH_PAF" \
  "$ISOLATED" \
  "$REFERENCE_FASTA" \
  "$OUTPUT" \
  "$SUMMARY" \
  "$REFERENCE_GROUPS" \
  "$QC" \
  "$MODEL_ID" \
  "$EXPECTED_PAIRS" \
  "$EXPECTED_POSITIVES" \
  "$EXPECTED_BATCH_PAF_ROWS" \
  "$EXPECTED_UNIQUE_REFERENCE_SEQUENCES" \
  "$NEAR_BEST_SCORE_FRACTION"

echo
echo "===== QC ====="
column -ts $'\t' "$QC"

echo
echo "===== SUMMARY ====="
column -ts $'\t' "$SUMMARY"

echo
echo "===== POSITIVE BRIDGE SPECIFICITY ====="
column -ts $'\t' "$OUTPUT"

echo
echo "===== LARGEST REFERENCE-EQUIVALENCE GROUPS ====="
column -ts $'\t' "$REFERENCE_GROUPS" \
  | head -n 21

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in \
      "$OUTPUT" \
      "$SUMMARY" \
      "$REFERENCE_GROUPS" \
      "$QC" \
      "$PARAMETERS"
    do
        rows="$(awk 'END {print NR-1}' "$path")"

        printf '%s\t%s\t%s\t%s\t%s\n' \
          "$(basename "$path")" \
          "$rows" \
          "$(stat -c '%s' "$path")" \
          "$(sha256sum "$path" | awk '{print $1}')" \
          "$path"
    done
} > "$MANIFEST"

echo
echo "===== MANIFEST ====="
column -ts $'\t' "$MANIFEST"

echo
echo "===== COMPLETE ====="
echo "$OUTPUT"
echo "$SUMMARY"
echo "$REFERENCE_GROUPS"
echo "$QC"
