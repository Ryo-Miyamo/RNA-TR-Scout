#!/usr/bin/env bash
set -euo pipefail

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
fi

conda activate rnatr-v03
source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"
MODEL_ID="rnatr_observed_reference_direct_alignment_v0.3.1"

DATADIR="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_reference_architecture"
REFERENCE_INPUT="$DATADIR/reference_targets_and_clusters.fasta.gz"
OBSERVED_INPUT="$DATADIR/observed_reference_job_tracts.fasta.gz"
ARCHITECTURE="$PROJECT_ROOT/results/11_reference_architecture/$RUN_ID/event_reference_architecture.tsv"

OUTDIR="$PROJECT_ROOT/results/11_observed_reference_alignment/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_observed_reference_alignment/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_observed_reference_alignment/$RUN_ID"

REFERENCE_FASTA="$WORKDIR/reference_locus_cluster.fa"
OBSERVED_FASTA="$WORKDIR/observed_events.fa"
REFERENCE_META="$WORKDIR/reference_locus_cluster.metadata.tsv"
OBSERVED_META="$WORKDIR/observed_events.metadata.tsv"

PAF="$OUTDIR/observed_to_reference_locus.all_alignments.paf"
PLACEMENTS="$OUTDIR/observed_to_reference_locus.placements.tsv"
SUMMARY="$OUTDIR/observed_to_reference_locus.summary.tsv"
QC="$QCDIR/observed_to_reference_locus.qc.tsv"
PARAMETERS="$OUTDIR/${MODEL_ID}.parameters.tsv"
MANIFEST="$OUTDIR/${RUN_ID}.observed_reference_alignment.manifest.tsv"

PREPARE_PY="$WORKDIR/prepare_alignment_fastas.py"
PARSE_PY="$WORKDIR/parse_reference_alignments.py"

EXPECTED_REFERENCE_SEQUENCES=1
EXPECTED_OBSERVED_EVENTS=2

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR"

for path in \
  "$REFERENCE_INPUT" \
  "$OBSERVED_INPUT" \
  "$ARCHITECTURE"
do
    test -s "$path" || {
        echo "ERROR: missing input: $path" >&2
        exit 1
    }
done

command -v minimap2 >/dev/null 2>&1 || {
    echo "ERROR: minimap2 is not available in PATH" >&2
    exit 1
}

cat > "$PARAMETERS" <<EOF
parameter	value	meaning
model_id	$MODEL_ID	Direct raw-RNA-event to GRCh38-locus alignment
aligner	minimap2	map-ont preset with low-complexity-sensitive seeds
minimap2_parameters	-x map-ont -k7 -w3 -m20 -s20 -p0.50 -N100 -f0 -c --cs=long --secondary=yes	Retain alternative placements within the repetitive locus
near_best_score_fraction	0.95	Placements within 95% of best alignment score
minimum_query_coverage_for_compatibility	0.90	Most of observed event must align
minimum_identity_for_compatibility	0.70	Provisional ONT cDNA direct-sequence compatibility threshold
allele_length_semantics	not_measurable_for_repeat_only_unanchored	Observed event is not assumed to span the repeat allele
expansion_status	NOT_ASSESSED	No expansion call emitted
EOF

cat > "$PREPARE_PY" <<'PY'
from __future__ import annotations

import csv
import gzip
import re
import sys

(
    reference_input,
    observed_input,
    reference_output,
    observed_output,
    reference_metadata_output,
    observed_metadata_output,
    expected_reference_text,
    expected_observed_text,
) = sys.argv[1:]

EXPECTED_REFERENCE = int(expected_reference_text)
EXPECTED_OBSERVED = int(expected_observed_text)


def read_fasta(path):
    records = []
    name = None
    description = None
    parts = []

    opener = gzip.open if path.endswith(".gz") else open

    with opener(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            line = line.rstrip("\n")

            if line.startswith(">"):
                if name is not None:
                    records.append(
                        {
                            "name": name,
                            "description": description,
                            "sequence": "".join(parts).upper(),
                        }
                    )

                description = line[1:]
                name = description.split()[0]
                parts = []
            else:
                parts.append(line.strip())

    if name is not None:
        records.append(
            {
                "name": name,
                "description": description,
                "sequence": "".join(parts).upper(),
            }
        )

    return records


reference_records = [
    record
    for record in read_fasta(reference_input)
    if "source=REFERENCE_LOCUS_CLUSTER"
    in record["description"]
]

observed_records = [
    record
    for record in read_fasta(observed_input)
    if "source=OBSERVED_RAW_RNA_EVENT"
    in record["description"]
]

if len(reference_records) != EXPECTED_REFERENCE:
    raise RuntimeError(
        "Expected {} reference locus sequences, observed {}".format(
            EXPECTED_REFERENCE,
            len(reference_records),
        )
    )

if len(observed_records) != EXPECTED_OBSERVED:
    raise RuntimeError(
        "Expected {} observed events, observed {}".format(
            EXPECTED_OBSERVED,
            len(observed_records),
        )
    )

with open(
    reference_output,
    "w",
    encoding="utf-8",
) as handle:
    for record in reference_records:
        handle.write(
            ">{}\n{}\n".format(
                record["name"],
                record["sequence"],
            )
        )

with open(
    observed_output,
    "w",
    encoding="utf-8",
) as handle:
    for record in observed_records:
        handle.write(
            ">{}\n{}\n".format(
                record["name"],
                record["sequence"],
            )
        )

with open(
    reference_metadata_output,
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=[
            "sequence_id",
            "description",
            "sequence_bp",
            "coordinate",
        ],
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()

    for record in reference_records:
        coordinate_match = re.search(
            r"coordinate=([^ ]+)",
            record["description"],
        )
        writer.writerow(
            {
                "sequence_id": record["name"],
                "description": record["description"],
                "sequence_bp": len(record["sequence"]),
                "coordinate": (
                    coordinate_match.group(1)
                    if coordinate_match
                    else "."
                ),
            }
        )

with open(
    observed_metadata_output,
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=[
            "event_id",
            "description",
            "sequence_bp",
            "read_id",
            "raw_interval",
        ],
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()

    for record in observed_records:
        read_match = re.search(
            r"read=([^ ]+)",
            record["description"],
        )
        raw_match = re.search(
            r"raw=([^ ]+)",
            record["description"],
        )
        writer.writerow(
            {
                "event_id": record["name"],
                "description": record["description"],
                "sequence_bp": len(record["sequence"]),
                "read_id": (
                    read_match.group(1)
                    if read_match
                    else "."
                ),
                "raw_interval": (
                    raw_match.group(1)
                    if raw_match
                    else "."
                ),
            }
        )
PY

cat > "$PARSE_PY" <<'PY'
from __future__ import annotations

import csv
import sys
from collections import Counter, defaultdict

(
    paf_path,
    reference_metadata_path,
    observed_metadata_path,
    architecture_path,
    placements_path,
    summary_path,
    qc_path,
    model_id,
    expected_reference_text,
    expected_observed_text,
) = sys.argv[1:]

EXPECTED_REFERENCE = int(expected_reference_text)
EXPECTED_OBSERVED = int(expected_observed_text)
NEAR_BEST_FRACTION = 0.95
MIN_QUERY_COVERAGE = 0.90
MIN_IDENTITY = 0.70


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


with open(
    reference_metadata_path,
    "r",
    encoding="utf-8",
    newline="",
) as handle:
    reference_metadata = {
        row["sequence_id"]: row
        for row in csv.DictReader(handle, delimiter="\t")
    }

with open(
    observed_metadata_path,
    "r",
    encoding="utf-8",
    newline="",
) as handle:
    observed_metadata = {
        row["event_id"]: row
        for row in csv.DictReader(handle, delimiter="\t")
    }

with open(
    architecture_path,
    "r",
    encoding="utf-8",
    newline="",
) as handle:
    architecture = {
        row["event_id"]: row
        for row in csv.DictReader(handle, delimiter="\t")
    }

alignments = []

with open(
    paf_path,
    "r",
    encoding="utf-8",
) as handle:
    for line in handle:
        line = line.rstrip("\n")

        if not line:
            continue

        fields = line.split("\t")

        if len(fields) < 12:
            raise RuntimeError(
                "Malformed PAF line with {} fields".format(
                    len(fields)
                )
            )

        tags = parse_tags(fields[12:])

        query_length = int(fields[1])
        query_start = int(fields[2])
        query_end = int(fields[3])
        target_length = int(fields[6])
        target_start = int(fields[7])
        target_end = int(fields[8])
        residue_matches = int(fields[9])
        alignment_block_length = int(fields[10])

        score = tags.get(
            "AS",
            residue_matches,
        )

        identity = (
            residue_matches / alignment_block_length
            if alignment_block_length
            else 0.0
        )

        query_coverage = (
            (query_end - query_start) / query_length
            if query_length
            else 0.0
        )

        target_coverage = (
            (target_end - target_start) / target_length
            if target_length
            else 0.0
        )

        alignments.append(
            {
                "event_id": fields[0],
                "query_length": query_length,
                "query_start": query_start,
                "query_end": query_end,
                "strand": fields[4],
                "reference_id": fields[5],
                "reference_length": target_length,
                "reference_start": target_start,
                "reference_end": target_end,
                "residue_matches": residue_matches,
                "alignment_block_length": alignment_block_length,
                "identity": identity,
                "query_coverage": query_coverage,
                "reference_coverage": target_coverage,
                "mapq": int(fields[11]),
                "alignment_score": score,
                "alignment_type": tags.get("tp", "."),
                "divergence": tags.get("dv", "."),
                "cs": tags.get("cs", "."),
            }
        )

alignments_by_event = defaultdict(list)

for row in alignments:
    alignments_by_event[row["event_id"]].append(row)

placement_fields = [
    "model_id",
    "event_id",
    "read_id",
    "alignment_rank",
    "is_near_best",
    "alignment_type",
    "reference_id",
    "strand",
    "query_length",
    "query_start",
    "query_end",
    "query_coverage",
    "query_unaligned_left_bp",
    "query_unaligned_right_bp",
    "reference_length",
    "reference_start",
    "reference_end",
    "reference_span_bp",
    "reference_coverage",
    "residue_matches",
    "alignment_block_length",
    "identity",
    "alignment_score",
    "mapq",
    "divergence",
]

placement_rows = []
summary_rows = []
counts = Counter()
missing_events = []

summary_fields = [
    "model_id",
    "event_id",
    "read_id",
    "observed_event_bp",
    "reference_locus_id",
    "reference_locus_bp",
    "best_strand",
    "best_query_start",
    "best_query_end",
    "best_query_coverage",
    "best_reference_start",
    "best_reference_end",
    "best_reference_span_bp",
    "best_reference_coverage",
    "best_identity",
    "best_alignment_score",
    "best_mapq",
    "alignment_count",
    "near_best_placement_count",
    "placement_status",
    "direct_sequence_compatibility",
    "architecture_best_observed_motif",
    "architecture_best_reference_motif",
    "same_best_motif",
    "allele_length_status",
    "reference_relative_expansion_status",
    "interpretation",
]

for event_id in sorted(observed_metadata):
    event_alignments = alignments_by_event.get(
        event_id,
        [],
    )

    if not event_alignments:
        missing_events.append(event_id)
        continue

    event_alignments.sort(
        key=lambda row: (
            row["alignment_score"],
            row["residue_matches"],
            row["query_coverage"],
            row["identity"],
        ),
        reverse=True,
    )

    best = event_alignments[0]
    best_score = best["alignment_score"]

    near_best = [
        row
        for row in event_alignments
        if row["alignment_score"]
        >= best_score * NEAR_BEST_FRACTION
    ]

    if len(near_best) == 1:
        placement_status = "UNIQUE_BEST_PLACEMENT"
    else:
        placement_status = (
            "MULTIPLE_NEAR_EQUIVALENT_REPEAT_PLACEMENTS"
        )

    if (
        best["query_coverage"] >= MIN_QUERY_COVERAGE
        and best["identity"] >= MIN_IDENTITY
    ):
        compatibility = (
            "REFERENCE_COMPATIBLE_PARTIAL_TRACT"
        )
    else:
        compatibility = (
            "LOW_OR_PARTIAL_DIRECT_SEQUENCE_COMPATIBILITY"
        )

    counts[
        "placement::{}".format(placement_status)
    ] += 1
    counts[
        "compatibility::{}".format(compatibility)
    ] += 1

    for rank, row in enumerate(
        event_alignments,
        start=1,
    ):
        is_near_best = (
            row["alignment_score"]
            >= best_score * NEAR_BEST_FRACTION
        )

        placement_rows.append(
            {
                "model_id": model_id,
                "event_id": event_id,
                "read_id": observed_metadata[
                    event_id
                ]["read_id"],
                "alignment_rank": rank,
                "is_near_best": str(
                    is_near_best
                ).lower(),
                "alignment_type": row[
                    "alignment_type"
                ],
                "reference_id": row[
                    "reference_id"
                ],
                "strand": row["strand"],
                "query_length": row[
                    "query_length"
                ],
                "query_start": row[
                    "query_start"
                ],
                "query_end": row[
                    "query_end"
                ],
                "query_coverage": "{:.6f}".format(
                    row["query_coverage"]
                ),
                "query_unaligned_left_bp": row[
                    "query_start"
                ],
                "query_unaligned_right_bp": (
                    row["query_length"]
                    - row["query_end"]
                ),
                "reference_length": row[
                    "reference_length"
                ],
                "reference_start": row[
                    "reference_start"
                ],
                "reference_end": row[
                    "reference_end"
                ],
                "reference_span_bp": (
                    row["reference_end"]
                    - row["reference_start"]
                ),
                "reference_coverage": "{:.6f}".format(
                    row["reference_coverage"]
                ),
                "residue_matches": row[
                    "residue_matches"
                ],
                "alignment_block_length": row[
                    "alignment_block_length"
                ],
                "identity": "{:.6f}".format(
                    row["identity"]
                ),
                "alignment_score": row[
                    "alignment_score"
                ],
                "mapq": row["mapq"],
                "divergence": row["divergence"],
            }
        )

    architecture_row = architecture.get(
        event_id,
        {},
    )

    summary_rows.append(
        {
            "model_id": model_id,
            "event_id": event_id,
            "read_id": observed_metadata[
                event_id
            ]["read_id"],
            "observed_event_bp": observed_metadata[
                event_id
            ]["sequence_bp"],
            "reference_locus_id": best[
                "reference_id"
            ],
            "reference_locus_bp": best[
                "reference_length"
            ],
            "best_strand": best["strand"],
            "best_query_start": best[
                "query_start"
            ],
            "best_query_end": best["query_end"],
            "best_query_coverage": "{:.6f}".format(
                best["query_coverage"]
            ),
            "best_reference_start": best[
                "reference_start"
            ],
            "best_reference_end": best[
                "reference_end"
            ],
            "best_reference_span_bp": (
                best["reference_end"]
                - best["reference_start"]
            ),
            "best_reference_coverage": "{:.6f}".format(
                best["reference_coverage"]
            ),
            "best_identity": "{:.6f}".format(
                best["identity"]
            ),
            "best_alignment_score": best[
                "alignment_score"
            ],
            "best_mapq": best["mapq"],
            "alignment_count": len(
                event_alignments
            ),
            "near_best_placement_count": len(
                near_best
            ),
            "placement_status": placement_status,
            "direct_sequence_compatibility": compatibility,
            "architecture_best_observed_motif": (
                architecture_row.get(
                    "best_observed_motif",
                    ".",
                )
            ),
            "architecture_best_reference_motif": (
                architecture_row.get(
                    "best_reference_cluster_motif",
                    ".",
                )
            ),
            "same_best_motif": architecture_row.get(
                "same_best_motif",
                ".",
            ),
            "allele_length_status": (
                "NOT_MEASURABLE_REPEAT_ONLY_UNANCHORED"
            ),
            "reference_relative_expansion_status": (
                "NOT_ASSESSED"
            ),
            "interpretation": (
                "Direct alignment tests whether the observed "
                "RNA tract is compatible with a contiguous part "
                "of the GRCh38 repeat architecture; it does not "
                "measure the complete expressed allele"
            ),
        }
    )

with open(
    placements_path,
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=placement_fields,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(placement_rows)

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
    writer.writerows(summary_rows)

status = "PASS"

if (
    len(reference_metadata) != EXPECTED_REFERENCE
    or len(observed_metadata) != EXPECTED_OBSERVED
    or missing_events
    or len(summary_rows) != EXPECTED_OBSERVED
):
    status = "REVIEW"

with open(qc_path, "w", encoding="utf-8") as handle:
    handle.write("metric\tvalue\n")
    handle.write(
        "expected_reference_sequences\t{}\n".format(
            EXPECTED_REFERENCE
        )
    )
    handle.write(
        "observed_reference_sequences\t{}\n".format(
            len(reference_metadata)
        )
    )
    handle.write(
        "expected_observed_events\t{}\n".format(
            EXPECTED_OBSERVED
        )
    )
    handle.write(
        "observed_event_sequences\t{}\n".format(
            len(observed_metadata)
        )
    )
    handle.write(
        "paf_alignment_rows\t{}\n".format(
            len(alignments)
        )
    )
    handle.write(
        "events_with_best_alignment\t{}\n".format(
            len(summary_rows)
        )
    )
    handle.write(
        "events_without_alignment\t{}\n".format(
            len(missing_events)
        )
    )

    for key, value in sorted(counts.items()):
        handle.write("{}\t{}\n".format(key, value))

    handle.write(
        "allele_length_calls_emitted\t0\n"
    )
    handle.write(
        "expansion_calls_emitted\t0\n"
    )
    handle.write(
        "audit_status\t{}\n".format(status)
    )

if status != "PASS":
    raise SystemExit(
        "Observed-to-reference alignment requires review"
    )
PY

echo "===== SHELL AND EMBEDDED PYTHON SYNTAX ====="
python -m py_compile "$PREPARE_PY"
python -m py_compile "$PARSE_PY"
echo "Embedded Python syntax: OK"

rm -f \
  "$REFERENCE_FASTA" \
  "$OBSERVED_FASTA" \
  "$REFERENCE_META" \
  "$OBSERVED_META" \
  "$PAF" \
  "$PLACEMENTS" \
  "$SUMMARY" \
  "$QC" \
  "$MANIFEST"

echo
echo "===== PREPARE ALIGNMENT FASTAS ====="

python "$PREPARE_PY" \
  "$REFERENCE_INPUT" \
  "$OBSERVED_INPUT" \
  "$REFERENCE_FASTA" \
  "$OBSERVED_FASTA" \
  "$REFERENCE_META" \
  "$OBSERVED_META" \
  "$EXPECTED_REFERENCE_SEQUENCES" \
  "$EXPECTED_OBSERVED_EVENTS"

echo
echo "===== DIRECT OBSERVED-TO-REFERENCE ALIGNMENT ====="

minimap2 \
  -x map-ont \
  -k7 \
  -w3 \
  -m20 \
  -s20 \
  -p0.50 \
  -N100 \
  -f0 \
  -c \
  --cs=long \
  --secondary=yes \
  -t4 \
  "$REFERENCE_FASTA" \
  "$OBSERVED_FASTA" \
  > "$PAF"

test -s "$PAF" || {
    echo "ERROR: minimap2 produced no alignments" >&2
    exit 1
}

echo
echo "===== PARSE ALIGNMENTS ====="

python "$PARSE_PY" \
  "$PAF" \
  "$REFERENCE_META" \
  "$OBSERVED_META" \
  "$ARCHITECTURE" \
  "$PLACEMENTS" \
  "$SUMMARY" \
  "$QC" \
  "$MODEL_ID" \
  "$EXPECTED_REFERENCE_SEQUENCES" \
  "$EXPECTED_OBSERVED_EVENTS"

echo
echo "===== QC ====="
column -ts $'\t' "$QC"

echo
echo "===== SUMMARY ====="
column -ts $'\t' "$SUMMARY"

echo
echo "===== TOP PLACEMENTS ====="
awk -F '\t' '
    NR == 1 || $4 <= 10
' "$PLACEMENTS" | column -ts $'\t'

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in \
      "$PAF" \
      "$PLACEMENTS" \
      "$SUMMARY" \
      "$QC" \
      "$PARAMETERS"
    do
        if [[ "$path" == *.paf ]]; then
            rows="$(awk 'END {print NR}' "$path")"
        else
            rows="$(awk 'END {print NR-1}' "$path")"
        fi

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
echo "$PAF"
echo "$PLACEMENTS"
echo "$SUMMARY"
echo "$QC"
