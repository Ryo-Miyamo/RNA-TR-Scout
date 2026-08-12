#!/usr/bin/env bash
set -euo pipefail

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
fi

conda activate rnatr-v03
source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1"
PARAMETER_SET_ID="rnatr_motif_job_preparation_v0.3.1"

PROJECTION="$PROJECT_ROOT/results/11_projection/$RUN_ID/v0.3.3/read_target_projection.v0.3.3.tsv.gz"

ANALYSIS_REGIONS="$CATALOG_ROOT/trexplorer_v2/rnatr_pilot_v03/final/TRExplorer_v2.rnatr_pilot_analysis_regions.final.tsv.gz"
DISEASE_REGIONS="$CATALOG_ROOT/trexplorer_v2/rnatr_pilot_v03/final/STRchive_disease_regions.final.tsv.gz"

OUTDIR="$PROJECT_ROOT/results/11_motif_jobs/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_motif_jobs/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_motif_jobs/$RUN_ID"

JOBS="$OUTDIR/motif_scan_jobs.tsv.gz"
MOTIF_DICTIONARY="$OUTDIR/motif_scan_dictionary.tsv"
TARGET_SUMMARY="$OUTDIR/motif_scan_target_summary.tsv.gz"
QC_SUMMARY="$QCDIR/motif_job_preparation_qc.tsv"
PARAMETERS="$OUTDIR/${PARAMETER_SET_ID}.parameters.tsv"
MANIFEST="$OUTDIR/${RUN_ID}.motif_job_preparation_manifest.tsv"

BUILDER="$WORKDIR/prepare_motif_scan_jobs.py"

EXPECTED_PROJECTION_ROWS=388571
EXPECTED_PROJECTION_READS=79176
EXPECTED_TR_EXPLORER_TARGETS=349410
EXPECTED_STRCHIVE_TARGETS=80

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR"

for path in \
  "$PROJECTION" \
  "$ANALYSIS_REGIONS" \
  "$DISEASE_REGIONS"
do
    test -s "$path" || {
        echo "ERROR: required input missing: $path" >&2
        exit 1
    }
done

for tool in python gzip sha256sum; do
    command -v "$tool" >/dev/null || {
        echo "ERROR: required tool not found: $tool" >&2
        exit 1
    }
done

cat > "$PARAMETERS" <<EOF
parameter	value	meaning
parameter_set_id	$PARAMETER_SET_ID	Motif scan job-preparation parameter set
simple_motif_max_bp	20	Maximum unit length for the first periodic baseline scanner
long_motif_max_bp	100	Units longer than this require sequence-level/manual review
iupac_support	ACGTRYSWKMBDHVN	IUPAC DNA alphabet supported for motif representation
variation_cluster_policy	sequence_level_multi_motif	Do not reduce VC regions to a single copy-number motif
complex_strchive_policy	sequence_level_manual_review	Retain the full disease-region sequence
no_window_policy	not_scan_eligible	Projection rows without a raw sequence window remain documented
candidate_status	pre_scan_jobs	No row is yet a repeat call
EOF

cat > "$BUILDER" <<'PY'
from __future__ import annotations

import csv
import gzip
import re
import sys
from collections import Counter, defaultdict

(
    projection_path,
    analysis_regions_path,
    disease_regions_path,
    jobs_path,
    motif_dictionary_path,
    target_summary_path,
    qc_path,
    expected_projection_rows_text,
    expected_projection_reads_text,
    expected_trex_targets_text,
    expected_strchive_targets_text,
) = sys.argv[1:]

expected_projection_rows = int(expected_projection_rows_text)
expected_projection_reads = int(expected_projection_reads_text)
expected_trex_targets = int(expected_trex_targets_text)
expected_strchive_targets = int(expected_strchive_targets_text)

IUPAC = set("ACGTRYSWKMBDHVN")
ACGT = set("ACGT")
COMPLEMENT = str.maketrans(
    "ACGTRYSWKMBDHVN",
    "TGCAYRSWMKVHDBN",
)

MISSING_TOKENS = {
    "",
    ".",
    "NONE",
    "NA",
    "N/A",
    "NULL",
    "NAN",
}


def reverse_complement(sequence: str) -> str:
    return sequence.translate(COMPLEMENT)[::-1]


def rotations(sequence: str):
    return [
        sequence[index:] + sequence[:index]
        for index in range(len(sequence))
    ]


def canonical_motif(sequence: str) -> str:
    sequence = sequence.upper()

    candidates = rotations(sequence)
    candidates.extend(rotations(reverse_complement(sequence)))

    return min(candidates)


def clean_motif_token(token: str) -> str:
    return (
        token.strip()
        .strip("[](){}'\"")
        .replace(" ", "")
        .upper()
    )


def split_motifs(text: str):
    if text is None:
        return []

    text = text.strip()

    if not text or text.upper() in MISSING_TOKENS:
        return []

    # Catalog motif lists are expected to use comma, semicolon, slash,
    # vertical bar, or whitespace delimiters. Parentheses and quotes are
    # formatting characters rather than motif bases.
    tokens = re.split(r"[,;/|\s]+", text)
    motifs = []

    for token in tokens:
        motif = clean_motif_token(token)

        if not motif or motif in MISSING_TOKENS:
            continue

        motifs.append(motif)

    return motifs


def infer_motif_from_locus_id(locus_id: str):
    if not locus_id or locus_id == "." or "-" not in locus_id:
        return []

    token = locus_id.rsplit("-", 1)[-1].upper()

    if token and set(token).issubset(IUPAC):
        return [token]

    return []


def ordered_unique(values):
    seen = set()
    output = []

    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)

    return output


def motif_alphabet_class(motifs):
    if not motifs:
        return "NONE"

    characters = set("".join(motifs))

    if characters.issubset(ACGT):
        return "ACGT_ONLY"

    if characters.issubset(IUPAC):
        return "IUPAC_DEGENERATE"

    return "UNSUPPORTED_SYMBOL"


def choose_scan_strategy(
    target_source,
    region_type,
    analysis_mode,
    manual_review_required,
    motifs,
    alphabet_class,
):
    lengths = [len(motif) for motif in motifs]
    max_length = max(lengths, default=0)

    if not motifs:
        return "NO_MOTIF_MANUAL_REVIEW"

    if alphabet_class == "UNSUPPORTED_SYMBOL":
        return "UNSUPPORTED_SYMBOL_MANUAL_REVIEW"

    if (
        target_source == "STRchive"
        and manual_review_required
    ):
        return "COMPLEX_DISEASE_REGION_SEQUENCE_REVIEW"

    if region_type == "VC":
        return "VARIATION_CLUSTER_MULTI_MOTIF_SEQUENCE_SCAN"

    if analysis_mode == "sequence_level_disease_region":
        return "COMPLEX_DISEASE_REGION_SEQUENCE_REVIEW"

    if max_length > 100:
        return "LONG_UNIT_GT100_SEQUENCE_REVIEW"

    if max_length > 20:
        return "LONG_UNIT_21_TO_100_PERIODIC_SCAN"

    if alphabet_class == "IUPAC_DEGENERATE":
        return "IUPAC_PERIODIC_SCAN"

    if len(motifs) > 1:
        return "MULTI_MOTIF_PERIODIC_SCAN"

    return "SIMPLE_PERIODIC_SCAN"


def choose_scan_scope(geometry_class):
    if geometry_class == "BOTH_FLANKS_PROJECTABLE":
        return "PROJECTED_TARGET_PLUS_FLANKS"

    if geometry_class in {
        "LEFT_FLANK_ONLY",
        "RIGHT_FLANK_ONLY",
        "PROXIMAL_LEFT_WITH_SOFTCLIP",
        "PROXIMAL_RIGHT_WITH_SOFTCLIP",
    }:
        return "TARGET_FACING_RAW_END"

    if geometry_class == "TARGET_INTERNAL_NO_FLANK":
        return "WHOLE_CANDIDATE_WINDOW"

    return "WHOLE_CANDIDATE_WINDOW_LOW_PRIORITY"


def choose_scan_priority(
    target_source,
    assignment_rank,
    candidate_basis,
    potential_evidence_class,
):
    if target_source == "STRchive":
        return "P0_DISEASE"

    if (
        assignment_rank == 1
        and candidate_basis == "exact_overlap"
        and potential_evidence_class != "NOT_YET_CLASSIFIABLE"
    ):
        return "P1_RANK1_EXACT_GEOMETRY"

    if candidate_basis == "exact_overlap":
        return "P2_OTHER_EXACT"

    return "P3_PROXIMAL"


target_metadata = {}

with gzip.open(
    analysis_regions_path,
    "rt",
    encoding="utf-8",
    newline="",
) as handle:
    reader = csv.DictReader(handle, delimiter="\t")

    for row in reader:
        key = ("TRExplorer", row["analysis_region_id"])

        if key in target_metadata:
            raise RuntimeError(f"Duplicate analysis target: {key}")

        motifs = split_motifs(row.get("motifs", ""))
        motifs.extend(
            infer_motif_from_locus_id(
                row.get("representative_locus_id", "")
            )
        )
        motifs = ordered_unique(motifs)

        target_metadata[key] = {
            "target_source": "TRExplorer",
            "target_region_id": row["analysis_region_id"],
            "region_type": row["region_type"],
            "analysis_mode": row["analysis_mode"],
            "representative_locus_id": row[
                "representative_locus_id"
            ],
            "motifs": motifs,
            "manual_review_required": False,
            "structure_token": row.get("structure_token", "."),
            "gene": ".",
        }

with gzip.open(
    disease_regions_path,
    "rt",
    encoding="utf-8",
    newline="",
) as handle:
    reader = csv.DictReader(handle, delimiter="\t")

    for row in reader:
        key = ("STRchive", row["disease_region_id"])

        if key in target_metadata:
            raise RuntimeError(f"Duplicate disease target: {key}")

        motifs = []
        motifs.extend(split_motifs(row.get("reference_motif", "")))
        motifs.extend(split_motifs(row.get("pathogenic_motif", "")))
        motifs = ordered_unique(motifs)

        target_metadata[key] = {
            "target_source": "STRchive",
            "target_region_id": row["disease_region_id"],
            "region_type": "DISEASE_REGION",
            "analysis_mode": row["analysis_mode_hint"],
            "representative_locus_id": row.get(
                "matched_trexplorer_locus_id",
                ".",
            ),
            "motifs": motifs,
            "manual_review_required": (
                row["manual_review_required"] == "true"
            ),
            "structure_token": ".",
            "gene": row.get("gene", "."),
        }

trex_target_count = sum(
    key[0] == "TRExplorer"
    for key in target_metadata
)
strchive_target_count = sum(
    key[0] == "STRchive"
    for key in target_metadata
)

job_columns = [
    "schema_version",
    "projection_id",
    "read_id",
    "target_region_id",
    "target_source",
    "region_type",
    "analysis_mode",
    "representative_locus_id",
    "assignment_rank",
    "read_candidate_target_count",
    "candidate_basis",
    "geometry_class",
    "potential_evidence_class",
    "projection_status",
    "candidate_window_read_start",
    "candidate_window_read_end",
    "candidate_window_length_bp",
    "motif_candidates",
    "canonical_motifs",
    "motif_count",
    "motif_min_length_bp",
    "motif_max_length_bp",
    "motif_alphabet_class",
    "scan_strategy",
    "scan_scope",
    "scan_priority",
    "motif_scan_eligible",
    "manual_review_required",
    "gene",
    "structure_token",
    "job_flags",
]

counts = Counter()
projection_ids = set()
read_ids = set()
observed_targets = set()
motif_stats = defaultdict(
    lambda: {
        "projection_count": 0,
        "target_keys": set(),
        "read_ids": set(),
        "strategies": Counter(),
        "alphabet_classes": Counter(),
    }
)
target_stats = defaultdict(
    lambda: {
        "projection_count": 0,
        "read_ids": set(),
        "exact_projection_count": 0,
        "rank1_projection_count": 0,
        "scan_eligible_count": 0,
        "strategies": Counter(),
    }
)

with gzip.open(
    projection_path,
    "rt",
    encoding="utf-8",
    newline="",
) as source, gzip.open(
    jobs_path,
    "wt",
    encoding="utf-8",
    newline="",
) as output:
    reader = csv.DictReader(source, delimiter="\t")
    writer = csv.DictWriter(
        output,
        fieldnames=job_columns,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()

    for row in reader:
        counts["projection_rows"] += 1
        projection_id = row["projection_id"]

        if projection_id in projection_ids:
            raise RuntimeError(
                f"Duplicate projection_id: {projection_id}"
            )
        projection_ids.add(projection_id)

        read_ids.add(row["read_id"])

        key = (
            row["target_source"],
            row["target_region_id"],
        )
        metadata = target_metadata.get(key)

        if metadata is None:
            counts["missing_target_metadata"] += 1
            continue

        observed_targets.add(key)

        motifs = ordered_unique(metadata["motifs"])
        canonical = ordered_unique(
            canonical_motif(motif)
            for motif in motifs
            if motif and set(motif).issubset(IUPAC)
        )

        alphabet_class = motif_alphabet_class(motifs)
        manual_review = metadata["manual_review_required"]

        strategy = choose_scan_strategy(
            row["target_source"],
            row["region_type"],
            row["analysis_mode"],
            manual_review,
            motifs,
            alphabet_class,
        )
        scope = choose_scan_scope(row["geometry_class"])
        priority = choose_scan_priority(
            row["target_source"],
            int(row["assignment_rank"]),
            row["candidate_basis"],
            row["potential_evidence_class"],
        )

        window_length = int(row["candidate_window_length_bp"])
        has_window = window_length > 0

        ineligible_strategies = {
            "NO_MOTIF_MANUAL_REVIEW",
            "UNSUPPORTED_SYMBOL_MANUAL_REVIEW",
            "COMPLEX_DISEASE_REGION_SEQUENCE_REVIEW",
            "LONG_UNIT_GT100_SEQUENCE_REVIEW",
        }

        eligible = (
            has_window
            and strategy not in ineligible_strategies
        )

        job_flags = []

        if not has_window:
            job_flags.append("NO_RAW_SEQUENCE_WINDOW")

        if row["projection_status"] != "PASS":
            job_flags.append("PROJECTION_WARN")

        if int(row["read_candidate_target_count"]) > 1:
            job_flags.append("MULTIPLE_TARGET_CANDIDATES")

        if strategy in ineligible_strategies:
            job_flags.append("MANUAL_OR_SPECIALIZED_REVIEW")

        if alphabet_class == "IUPAC_DEGENERATE":
            job_flags.append("DEGENERATE_MOTIF")

        if row["region_type"] == "VC":
            job_flags.append("VARIATION_CLUSTER")

        motif_lengths = [len(motif) for motif in motifs]

        writer.writerow(
            {
                "schema_version": "0.3.0",
                "projection_id": projection_id,
                "read_id": row["read_id"],
                "target_region_id": row["target_region_id"],
                "target_source": row["target_source"],
                "region_type": row["region_type"],
                "analysis_mode": row["analysis_mode"],
                "representative_locus_id": row[
                    "representative_locus_id"
                ],
                "assignment_rank": row["assignment_rank"],
                "read_candidate_target_count": row[
                    "read_candidate_target_count"
                ],
                "candidate_basis": row["candidate_basis"],
                "geometry_class": row["geometry_class"],
                "potential_evidence_class": row[
                    "potential_evidence_class"
                ],
                "projection_status": row["projection_status"],
                "candidate_window_read_start": row[
                    "candidate_window_read_start"
                ],
                "candidate_window_read_end": row[
                    "candidate_window_read_end"
                ],
                "candidate_window_length_bp": window_length,
                "motif_candidates": (
                    ",".join(motifs) if motifs else "."
                ),
                "canonical_motifs": (
                    ",".join(canonical) if canonical else "."
                ),
                "motif_count": len(motifs),
                "motif_min_length_bp": (
                    min(motif_lengths) if motif_lengths else "."
                ),
                "motif_max_length_bp": (
                    max(motif_lengths) if motif_lengths else "."
                ),
                "motif_alphabet_class": alphabet_class,
                "scan_strategy": strategy,
                "scan_scope": scope,
                "scan_priority": priority,
                "motif_scan_eligible": str(eligible).lower(),
                "manual_review_required": str(
                    manual_review
                    or strategy in ineligible_strategies
                ).lower(),
                "gene": metadata["gene"],
                "structure_token": metadata[
                    "structure_token"
                ] or ".",
                "job_flags": (
                    ";".join(sorted(set(job_flags)))
                    if job_flags else "."
                ),
            }
        )

        counts[f"strategy::{strategy}"] += 1
        counts[f"scan_scope::{scope}"] += 1
        counts[f"scan_priority::{priority}"] += 1
        counts[f"alphabet::{alphabet_class}"] += 1
        counts[f"eligible::{str(eligible).lower()}"] += 1
        counts[
            f"region_type::{row['region_type']}"
        ] += 1
        counts[
            f"potential::{row['potential_evidence_class']}"
        ] += 1

        target_record = target_stats[key]
        target_record["projection_count"] += 1
        target_record["read_ids"].add(row["read_id"])
        target_record["strategies"][strategy] += 1

        if row["candidate_basis"] == "exact_overlap":
            target_record["exact_projection_count"] += 1

        if int(row["assignment_rank"]) == 1:
            target_record["rank1_projection_count"] += 1

        if eligible:
            target_record["scan_eligible_count"] += 1

        for motif in canonical:
            motif_record = motif_stats[motif]
            motif_record["projection_count"] += 1
            motif_record["target_keys"].add(key)
            motif_record["read_ids"].add(row["read_id"])
            motif_record["strategies"][strategy] += 1
            motif_record["alphabet_classes"][alphabet_class] += 1

motif_dictionary_columns = [
    "canonical_motif",
    "motif_length_bp",
    "alphabet_class",
    "projection_count",
    "unique_target_count",
    "unique_read_count",
    "scan_strategies",
]

with open(
    motif_dictionary_path,
    "w",
    encoding="utf-8",
    newline="",
) as output:
    writer = csv.DictWriter(
        output,
        fieldnames=motif_dictionary_columns,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()

    for motif in sorted(
        motif_stats,
        key=lambda value: (len(value), value),
    ):
        record = motif_stats[motif]
        alphabet_class = (
            "ACGT_ONLY"
            if set(motif).issubset(ACGT)
            else "IUPAC_DEGENERATE"
        )

        writer.writerow(
            {
                "canonical_motif": motif,
                "motif_length_bp": len(motif),
                "alphabet_class": alphabet_class,
                "projection_count": record[
                    "projection_count"
                ],
                "unique_target_count": len(
                    record["target_keys"]
                ),
                "unique_read_count": len(record["read_ids"]),
                "scan_strategies": ";".join(
                    sorted(record["strategies"])
                ),
            }
        )

target_summary_columns = [
    "target_source",
    "target_region_id",
    "region_type",
    "analysis_mode",
    "representative_locus_id",
    "gene",
    "motif_candidates",
    "canonical_motifs",
    "projection_count",
    "unique_read_count",
    "exact_projection_count",
    "rank1_projection_count",
    "scan_eligible_count",
    "scan_strategies",
    "manual_review_required",
]

with gzip.open(
    target_summary_path,
    "wt",
    encoding="utf-8",
    newline="",
) as output:
    writer = csv.DictWriter(
        output,
        fieldnames=target_summary_columns,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()

    for key in sorted(target_stats):
        metadata = target_metadata[key]
        record = target_stats[key]
        motifs = ordered_unique(metadata["motifs"])
        canonical = ordered_unique(
            canonical_motif(motif)
            for motif in motifs
            if motif and set(motif).issubset(IUPAC)
        )

        writer.writerow(
            {
                "target_source": key[0],
                "target_region_id": key[1],
                "region_type": metadata["region_type"],
                "analysis_mode": metadata["analysis_mode"],
                "representative_locus_id": metadata[
                    "representative_locus_id"
                ],
                "gene": metadata["gene"],
                "motif_candidates": (
                    ",".join(motifs) if motifs else "."
                ),
                "canonical_motifs": (
                    ",".join(canonical) if canonical else "."
                ),
                "projection_count": record[
                    "projection_count"
                ],
                "unique_read_count": len(record["read_ids"]),
                "exact_projection_count": record[
                    "exact_projection_count"
                ],
                "rank1_projection_count": record[
                    "rank1_projection_count"
                ],
                "scan_eligible_count": record[
                    "scan_eligible_count"
                ],
                "scan_strategies": ";".join(
                    sorted(record["strategies"])
                ),
                "manual_review_required": str(
                    metadata["manual_review_required"]
                ).lower(),
            }
        )

status = "PASS"

if (
    counts["projection_rows"] != expected_projection_rows
    or len(projection_ids) != expected_projection_rows
    or len(read_ids) != expected_projection_reads
    or trex_target_count != expected_trex_targets
    or strchive_target_count != expected_strchive_targets
    or counts["missing_target_metadata"] != 0
):
    status = "REVIEW"

with open(qc_path, "w", encoding="utf-8") as output:
    output.write("metric\tvalue\n")
    output.write(
        f"expected_projection_rows\t"
        f"{expected_projection_rows}\n"
    )
    output.write(
        f"observed_projection_rows\t"
        f"{counts['projection_rows']}\n"
    )
    output.write(
        f"unique_projection_ids\t{len(projection_ids)}\n"
    )
    output.write(
        f"expected_projection_reads\t"
        f"{expected_projection_reads}\n"
    )
    output.write(f"unique_projection_reads\t{len(read_ids)}\n")
    output.write(
        f"catalog_trexplorer_targets\t{trex_target_count}\n"
    )
    output.write(
        f"catalog_strchive_targets\t{strchive_target_count}\n"
    )
    output.write(
        f"observed_target_regions\t{len(observed_targets)}\n"
    )
    output.write(
        f"unique_canonical_motifs\t{len(motif_stats)}\n"
    )
    output.write(
        f"missing_target_metadata\t"
        f"{counts['missing_target_metadata']}\n"
    )

    for key, value in sorted(counts.items()):
        if key in {
            "projection_rows",
            "missing_target_metadata",
        }:
            continue
        output.write(f"{key}\t{value}\n")

    output.write(f"audit_status\t{status}\n")

if status != "PASS":
    raise SystemExit("Motif job preparation requires review")
PY

echo "===== 1. INPUT INTEGRITY ====="

gzip -t "$PROJECTION"
gzip -t "$ANALYSIS_REGIONS"
gzip -t "$DISEASE_REGIONS"

echo "Inputs: PASS"

echo
echo "===== 2. PARAMETERS ====="
column -ts $'\t' "$PARAMETERS"

echo
echo "===== 3. PREPARE MOTIF SCAN JOBS ====="

rm -f \
  "$JOBS" \
  "$MOTIF_DICTIONARY" \
  "$TARGET_SUMMARY" \
  "$QC_SUMMARY" \
  "$MANIFEST"

python "$BUILDER" \
  "$PROJECTION" \
  "$ANALYSIS_REGIONS" \
  "$DISEASE_REGIONS" \
  "$JOBS" \
  "$MOTIF_DICTIONARY" \
  "$TARGET_SUMMARY" \
  "$QC_SUMMARY" \
  "$EXPECTED_PROJECTION_ROWS" \
  "$EXPECTED_PROJECTION_READS" \
  "$EXPECTED_TR_EXPLORER_TARGETS" \
  "$EXPECTED_STRCHIVE_TARGETS"

gzip -t "$JOBS"
gzip -t "$TARGET_SUMMARY"

echo
echo "===== MOTIF JOB PREPARATION QC ====="
column -ts $'\t' "$QC_SUMMARY"

echo
echo "===== 4. MOST COMMON CANONICAL MOTIFS ====="

{
    head -n 1 "$MOTIF_DICTIONARY"
    tail -n +2 "$MOTIF_DICTIONARY" |
      sort -t $'\t' -k4,4nr |
      head -n 30
} |
column -ts $'\t'

echo
echo "===== 5. OUTPUT MANIFEST ====="

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in "$JOBS" "$TARGET_SUMMARY"; do
        rows="$(gzip -cd "$path" | awk 'END {print NR-1}')"

        printf '%s\t%s\t%s\t%s\t%s\n' \
          "$(basename "$path")" \
          "$rows" \
          "$(stat -c '%s' "$path")" \
          "$(sha256sum "$path" | awk '{print $1}')" \
          "$path"
    done

    for path in \
      "$MOTIF_DICTIONARY" \
      "$QC_SUMMARY" \
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

column -ts $'\t' "$MANIFEST"

echo
echo "===== COMPLETE ====="
echo "$JOBS"
echo "$MOTIF_DICTIONARY"
echo "$TARGET_SUMMARY"
echo "$QC_SUMMARY"
echo "$MANIFEST"
