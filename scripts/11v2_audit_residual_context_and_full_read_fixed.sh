#!/usr/bin/env bash
set -euo pipefail

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
fi

conda activate rnatr-v03
source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"
MODEL_ID="rnatr_residual_context_audit_v0.3.2"

FLANK_SUMMARY="$PROJECT_ROOT/results/11_flank_rescue/$RUN_ID/reference_compatible_event_flank_rescue.tsv"
CONTEXT_META="$PROJECT_ROOT/results/11_flank_rescue/$RUN_ID/reference_compatible_event_flanks.metadata.tsv"
CONTEXT_FASTA="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_flank_rescue/reference_compatible_event_flanks.fasta.gz"
FASTQ="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_candidates_v0.3.1/ENCFF260PGB.pilot_100k.rnatr_candidate_all.fastq.gz"
BAM="$PROJECT_ROOT/results/11_mapping/$RUN_ID/${RUN_ID}.sorted.bam"
REFERENCE_FASTA="$PROJECT_ROOT/refs/gencode_v50/GRCh38.primary_assembly.genome.fa"

OUTDIR="$PROJECT_ROOT/results/11_residual_context/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_residual_context/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_residual_context/$RUN_ID"

CONTEXT_AUDIT="$OUTDIR/residual_context_audit.tsv"
WINDOWS="$OUTDIR/residual_context_windows.tsv"
BAM_AUDIT="$OUTDIR/source_read_bam_geometry.tsv"
LOCAL_PAF="$OUTDIR/full_reads_to_extended_locus.paf"
LOCAL_SUMMARY="$OUTDIR/full_reads_to_extended_locus.summary.tsv"
QC="$QCDIR/residual_context_audit.qc.tsv"
PARAMETERS="$OUTDIR/${MODEL_ID}.parameters.tsv"
MANIFEST="$OUTDIR/${RUN_ID}.residual_context_audit.manifest.tsv"

FULL_READ_FASTA="$WORKDIR/source_reads.fa"
EXTENDED_LOCUS_FASTA="$WORKDIR/extended_chr15_locus.fa"
PREPARE_PY="$WORKDIR/prepare_residual_context_audit.py"
PARSE_PY="$WORKDIR/parse_residual_context_audit.py"

EXPECTED_EVENTS=2
EXPECTED_CONTEXTS=3
LOCUS_FLANK_BP=20000
WINDOW_BP=100
WINDOW_STEP_BP=25
REPEAT_LIKE_PURITY=0.70
LOW_COMPLEXITY_ENTROPY=1.00
LOW_QUALITY_MEAN_Q=8.0

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR"

for path in \
  "$FLANK_SUMMARY" \
  "$CONTEXT_META" \
  "$CONTEXT_FASTA" \
  "$FASTQ" \
  "$BAM" \
  "$REFERENCE_FASTA" \
  "${REFERENCE_FASTA}.fai"
do
    test -s "$path" || {
        echo "ERROR: missing input: $path" >&2
        exit 1
    }
done

command -v minimap2 >/dev/null 2>&1 || {
    echo "ERROR: minimap2 is not available" >&2
    exit 1
}

cat > "$PARAMETERS" <<EOF
parameter	value	meaning
model_id	$MODEL_ID	Residual sequence audit after repeat-event boundary
extended_locus_flank_bp	$LOCUS_FLANK_BP	Bases added on each side of catalog locus
window_bp	$WINDOW_BP	Sliding-window size
window_step_bp	$WINDOW_STEP_BP	Sliding-window step
motifs_tested	AAG;AAGGAAGGAG	Current chr15 architecture hypotheses
repeat_like_purity	$REPEAT_LIKE_PURITY	Diagnostic phase-match threshold
low_complexity_entropy	$LOW_COMPLEXITY_ENTROPY	Shannon entropy threshold
low_quality_mean_q	$LOW_QUALITY_MEAN_Q	Mean Phred threshold
local_alignment	minimap2 -x splice -k12 -w5 -G200k -N50 -p0.50 -c --cs=long	Full read to extended locus
classification_semantics	context_diagnosis_only	No flank rescue, allele length, or expansion call
EOF

cat > "$PREPARE_PY" <<'PY'
from __future__ import annotations

import csv
import gzip
import re
import sys
from collections import Counter

import pysam

(
    flank_summary_path,
    context_metadata_path,
    context_fasta_path,
    fastq_path,
    bam_path,
    reference_fasta_path,
    full_read_fasta_path,
    extended_locus_fasta_path,
    bam_audit_path,
    expected_events_text,
    expected_contexts_text,
    locus_flank_text,
) = sys.argv[1:]

EXPECTED_EVENTS = int(expected_events_text)
EXPECTED_CONTEXTS = int(expected_contexts_text)
LOCUS_FLANK = int(locus_flank_text)


def parse_cluster(cluster_id):
    match = re.match(
        r"^EXTLOC_[0-9]+_(.+)_([0-9]+)_([0-9]+)$",
        cluster_id,
    )
    if match is None:
        raise ValueError(
            "Unrecognized cluster ID: {}".format(cluster_id)
        )
    return match.group(1), int(match.group(2)), int(match.group(3))


def resolve_contig(reference, chromosome):
    references = set(reference.references)

    candidates = [chromosome]

    if chromosome.startswith("chr"):
        candidates.append(chromosome[3:])
    else:
        candidates.append("chr" + chromosome)

    if chromosome in {"MT", "M", "chrM", "chrMT"}:
        candidates.extend(["chrM", "MT", "M"])

    for candidate in candidates:
        if candidate in references:
            return candidate

    raise KeyError(
        "No FASTA contig alias for {}".format(chromosome)
    )


with open(
    flank_summary_path,
    "r",
    encoding="utf-8",
    newline="",
) as handle:
    event_rows = list(
        csv.DictReader(handle, delimiter="\t")
    )

with open(
    context_metadata_path,
    "r",
    encoding="utf-8",
    newline="",
) as handle:
    context_rows = list(
        csv.DictReader(handle, delimiter="\t")
    )

if len(event_rows) != EXPECTED_EVENTS:
    raise RuntimeError(
        "Expected {} events, observed {}".format(
            EXPECTED_EVENTS,
            len(event_rows),
        )
    )

if len(context_rows) != EXPECTED_CONTEXTS:
    raise RuntimeError(
        "Expected {} contexts, observed {}".format(
            EXPECTED_CONTEXTS,
            len(context_rows),
        )
    )

read_ids = {row["read_id"] for row in event_rows}
reads = {}

with pysam.FastxFile(fastq_path) as source:
    for entry in source:
        if entry.name in read_ids:
            reads[entry.name] = {
                "sequence": entry.sequence.upper(),
                "quality": entry.quality,
            }

missing_reads = read_ids - set(reads)

if missing_reads:
    raise RuntimeError(
        "Missing reads: {}".format(
            ",".join(sorted(missing_reads))
        )
    )

with open(
    full_read_fasta_path,
    "w",
    encoding="utf-8",
) as handle:
    for read_id in sorted(reads):
        handle.write(
            ">{}\n{}\n".format(
                read_id,
                reads[read_id]["sequence"],
            )
        )

cluster_ids = {
    row["reference_locus_id"]
    for row in context_rows
}

if len(cluster_ids) != 1:
    raise RuntimeError(
        "Expected one locus cluster, observed {}".format(
            len(cluster_ids)
        )
    )

cluster_id = next(iter(cluster_ids))
chromosome, locus_start, locus_end = parse_cluster(
    cluster_id
)

reference = pysam.FastaFile(reference_fasta_path)
resolved_contig = resolve_contig(
    reference,
    chromosome,
)
contig_length = reference.get_reference_length(
    resolved_contig
)

extended_start = max(0, locus_start - LOCUS_FLANK)
extended_end = min(
    contig_length,
    locus_end + LOCUS_FLANK,
)

extended_sequence = reference.fetch(
    resolved_contig,
    extended_start,
    extended_end,
).upper()

reference.close()

with open(
    extended_locus_fasta_path,
    "w",
    encoding="utf-8",
) as handle:
    handle.write(
        ">{}|{}:{}-{}\n{}\n".format(
            cluster_id,
            resolved_contig,
            extended_start,
            extended_end,
            extended_sequence,
        )
    )

bam = pysam.AlignmentFile(bam_path, "rb")
bam_rows = []
records_by_read = {
    read_id: []
    for read_id in read_ids
}

for record in bam.fetch(until_eof=True):
    if record.query_name in records_by_read:
        records_by_read[record.query_name].append(record)

bam.close()

for read_id in sorted(read_ids):
    records = records_by_read[read_id]

    for record_index, record in enumerate(
        records,
        start=1,
    ):
        cigar = record.cigartuples or []

        left_soft = (
            cigar[0][1]
            if cigar and cigar[0][0] == 4
            else 0
        )
        right_soft = (
            cigar[-1][1]
            if cigar and cigar[-1][0] == 4
            else 0
        )
        left_hard = (
            cigar[0][1]
            if cigar and cigar[0][0] == 5
            else 0
        )
        right_hard = (
            cigar[-1][1]
            if cigar and cigar[-1][0] == 5
            else 0
        )

        bam_rows.append(
            {
                "read_id": read_id,
                "record_index": record_index,
                "alignment_class": (
                    "unmapped"
                    if record.is_unmapped
                    else "secondary"
                    if record.is_secondary
                    else "supplementary"
                    if record.is_supplementary
                    else "primary"
                ),
                "reference_name": (
                    "."
                    if record.is_unmapped
                    else record.reference_name
                ),
                "reference_start": (
                    "."
                    if record.is_unmapped
                    else record.reference_start
                ),
                "reference_end": (
                    "."
                    if record.is_unmapped
                    else record.reference_end
                ),
                "mapq": record.mapping_quality,
                "strand": (
                    "."
                    if record.is_unmapped
                    else "-"
                    if record.is_reverse
                    else "+"
                ),
                "query_alignment_start": (
                    "."
                    if record.is_unmapped
                    else record.query_alignment_start
                ),
                "query_alignment_end": (
                    "."
                    if record.is_unmapped
                    else record.query_alignment_end
                ),
                "query_length": record.query_length or ".",
                "left_softclip_bp": left_soft,
                "right_softclip_bp": right_soft,
                "left_hardclip_bp": left_hard,
                "right_hardclip_bp": right_hard,
                "cigar": (
                    "."
                    if record.cigarstring is None
                    else record.cigarstring
                ),
                "sa_tag_present": str(
                    record.has_tag("SA")
                ).lower(),
            }
        )

bam_fields = [
    "read_id",
    "record_index",
    "alignment_class",
    "reference_name",
    "reference_start",
    "reference_end",
    "mapq",
    "strand",
    "query_alignment_start",
    "query_alignment_end",
    "query_length",
    "left_softclip_bp",
    "right_softclip_bp",
    "left_hardclip_bp",
    "right_hardclip_bp",
    "cigar",
    "sa_tag_present",
]

with open(
    bam_audit_path,
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=bam_fields,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(bam_rows)
PY

cat > "$PARSE_PY" <<'PY'
from __future__ import annotations

import csv
import gzip
import math
import sys
from collections import Counter, defaultdict

import pysam

(
    flank_summary_path,
    context_metadata_path,
    context_fasta_path,
    fastq_path,
    local_paf_path,
    context_audit_path,
    windows_path,
    local_summary_path,
    qc_path,
    model_id,
    expected_events_text,
    expected_contexts_text,
    window_bp_text,
    window_step_text,
    repeat_like_purity_text,
    low_complexity_entropy_text,
    low_quality_q_text,
) = sys.argv[1:]

EXPECTED_EVENTS = int(expected_events_text)
EXPECTED_CONTEXTS = int(expected_contexts_text)
WINDOW_BP = int(window_bp_text)
WINDOW_STEP = int(window_step_text)
REPEAT_LIKE_PURITY = float(repeat_like_purity_text)
LOW_COMPLEXITY_ENTROPY = float(
    low_complexity_entropy_text
)
LOW_QUALITY_Q = float(low_quality_q_text)

MOTIFS = ["AAG", "AAGGAAGGAG"]
COMPLEMENT = str.maketrans("ACGT", "TGCA")


def reverse_complement(sequence):
    return sequence.translate(COMPLEMENT)[::-1]


def rotations(sequence):
    return [
        sequence[index:] + sequence[:index]
        for index in range(len(sequence))
    ]


def motif_phase_purity(sequence, motif):
    candidates = set(
        rotations(motif)
        + rotations(reverse_complement(motif))
    )
    best = 0.0
    best_orientation = "."

    for candidate in candidates:
        matches = sum(
            base == candidate[index % len(candidate)]
            for index, base in enumerate(sequence)
        )
        purity = matches / len(sequence) if sequence else 0.0

        if purity > best:
            best = purity
            best_orientation = candidate

    return best, best_orientation


def entropy(sequence):
    if not sequence:
        return 0.0
    counts = Counter(sequence)
    length = len(sequence)
    return -sum(
        (count / length) * math.log2(count / length)
        for count in counts.values()
    )


def mean_quality(quality):
    if not quality:
        return 0.0
    return sum(
        ord(character) - 33
        for character in quality
    ) / len(quality)


def longest_homopolymer(sequence):
    if not sequence:
        return 0, "."

    best_length = 1
    best_base = sequence[0]
    current_length = 1
    current_base = sequence[0]

    for base in sequence[1:]:
        if base == current_base:
            current_length += 1
        else:
            if current_length > best_length:
                best_length = current_length
                best_base = current_base
            current_length = 1
            current_base = base

    if current_length > best_length:
        best_length = current_length
        best_base = current_base

    return best_length, best_base


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
    flank_summary_path,
    "r",
    encoding="utf-8",
    newline="",
) as handle:
    flank_rows = list(
        csv.DictReader(handle, delimiter="\t")
    )

with open(
    context_metadata_path,
    "r",
    encoding="utf-8",
    newline="",
) as handle:
    metadata_rows = list(
        csv.DictReader(handle, delimiter="\t")
    )

metadata = {
    row["context_id"]: row
    for row in metadata_rows
}

context_sequences = {}

with pysam.FastxFile(context_fasta_path) as source:
    for entry in source:
        context_sequences[entry.name] = entry.sequence.upper()

read_ids = {
    row["read_id"]
    for row in flank_rows
}

read_records = {}

with pysam.FastxFile(fastq_path) as source:
    for entry in source:
        if entry.name in read_ids:
            read_records[entry.name] = {
                "sequence": entry.sequence.upper(),
                "quality": entry.quality,
            }

paf_rows = []

with open(
    local_paf_path,
    "r",
    encoding="utf-8",
) as handle:
    for line in handle:
        line = line.rstrip("\n")
        if not line:
            continue

        fields = line.split("\t")
        tags = parse_tags(fields[12:])

        query_length = int(fields[1])
        query_start = int(fields[2])
        query_end = int(fields[3])
        matches = int(fields[9])
        block_length = int(fields[10])

        paf_rows.append(
            {
                "read_id": fields[0],
                "query_length": query_length,
                "query_start": query_start,
                "query_end": query_end,
                "query_coverage": (
                    (query_end - query_start) / query_length
                    if query_length else 0.0
                ),
                "strand": fields[4],
                "target_id": fields[5],
                "target_start": int(fields[7]),
                "target_end": int(fields[8]),
                "matches": matches,
                "block_length": block_length,
                "identity": (
                    matches / block_length
                    if block_length else 0.0
                ),
                "mapq": int(fields[11]),
                "alignment_score": tags.get(
                    "AS",
                    matches,
                ),
                "alignment_type": tags.get("tp", "."),
            }
        )

paf_by_read = defaultdict(list)

for row in paf_rows:
    paf_by_read[row["read_id"]].append(row)

window_fields = [
    "model_id",
    "context_id",
    "event_id",
    "side",
    "window_start",
    "window_end",
    "window_bp",
    "entropy_bits",
    "mean_q",
    "dominant_base",
    "dominant_base_fraction",
    "longest_homopolymer_bp",
    "AAG_phase_purity",
    "AAG_best_orientation",
    "AAGGAAGGAG_phase_purity",
    "AAGGAAGGAG_best_orientation",
    "best_motif",
    "best_motif_purity",
]

window_rows = []
context_audit_rows = []
counts = Counter()

for context_id in sorted(metadata):
    meta = metadata[context_id]
    sequence = context_sequences[context_id]
    read = read_records[meta["read_id"]]
    context_start = int(meta["context_start"])
    context_end = int(meta["context_end"])
    quality = read["quality"][context_start:context_end]

    windows = []

    if len(sequence) <= WINDOW_BP:
        windows = [(0, len(sequence))]
    else:
        start = 0
        while start < len(sequence):
            end = min(len(sequence), start + WINDOW_BP)
            if end - start >= min(25, WINDOW_BP):
                windows.append((start, end))
            if end == len(sequence):
                break
            start += WINDOW_STEP

    best_window_purity = 0.0
    repeat_like_windows = 0

    for window_start, window_end in windows:
        window_sequence = sequence[
            window_start:window_end
        ]
        window_quality = quality[
            window_start:window_end
        ]

        base_counts = Counter(window_sequence)
        dominant_base = max(
            "ACGTN",
            key=lambda base: base_counts.get(base, 0),
        )
        dominant_fraction = (
            base_counts.get(dominant_base, 0)
            / len(window_sequence)
        )
        hp_length, _hp_base = longest_homopolymer(
            window_sequence
        )

        motif_results = {}

        for motif in MOTIFS:
            motif_results[motif] = motif_phase_purity(
                window_sequence,
                motif,
            )

        best_motif = max(
            MOTIFS,
            key=lambda motif: motif_results[motif][0],
        )
        best_purity = motif_results[best_motif][0]
        best_window_purity = max(
            best_window_purity,
            best_purity,
        )

        if best_purity >= REPEAT_LIKE_PURITY:
            repeat_like_windows += 1

        window_rows.append(
            {
                "model_id": model_id,
                "context_id": context_id,
                "event_id": meta["event_id"],
                "side": meta["side"],
                "window_start": window_start,
                "window_end": window_end,
                "window_bp": len(window_sequence),
                "entropy_bits": "{:.6f}".format(
                    entropy(window_sequence)
                ),
                "mean_q": "{:.6f}".format(
                    mean_quality(window_quality)
                ),
                "dominant_base": dominant_base,
                "dominant_base_fraction": "{:.6f}".format(
                    dominant_fraction
                ),
                "longest_homopolymer_bp": hp_length,
                "AAG_phase_purity": "{:.6f}".format(
                    motif_results["AAG"][0]
                ),
                "AAG_best_orientation": motif_results[
                    "AAG"
                ][1],
                "AAGGAAGGAG_phase_purity": "{:.6f}".format(
                    motif_results["AAGGAAGGAG"][0]
                ),
                "AAGGAAGGAG_best_orientation": motif_results[
                    "AAGGAAGGAG"
                ][1],
                "best_motif": best_motif,
                "best_motif_purity": "{:.6f}".format(
                    best_purity
                ),
            }
        )

    full_counts = Counter(sequence)
    dominant_base = max(
        "ACGTN",
        key=lambda base: full_counts.get(base, 0),
    )
    dominant_fraction = (
        full_counts.get(dominant_base, 0) / len(sequence)
    )
    hp_length, hp_base = longest_homopolymer(sequence)
    context_entropy = entropy(sequence)
    context_mean_q = mean_quality(quality)

    motif_results = {
        motif: motif_phase_purity(sequence, motif)
        for motif in MOTIFS
    }
    best_context_motif = max(
        MOTIFS,
        key=lambda motif: motif_results[motif][0],
    )
    best_context_purity = motif_results[
        best_context_motif
    ][0]

    repeat_like_fraction = (
        repeat_like_windows / len(windows)
        if windows else 0.0
    )

    previous_anchor = (
        (
            meta["side"] == "LEFT"
            and next(
                row for row in flank_rows
                if row["event_id"] == meta["event_id"]
            )["left_anchor_candidate"] == "true"
        )
        or (
            meta["side"] == "RIGHT"
            and next(
                row for row in flank_rows
                if row["event_id"] == meta["event_id"]
            )["right_anchor_candidate"] == "true"
        )
    )

    if previous_anchor:
        classification = "UNIQUE_FLANK_ANCHOR"

    elif (
        best_context_purity >= REPEAT_LIKE_PURITY
        or repeat_like_fraction >= 0.50
    ):
        classification = "REPEAT_LIKE_CONTINUATION"

    elif (
        context_entropy < LOW_COMPLEXITY_ENTROPY
        or dominant_fraction >= 0.80
        or hp_length / len(sequence) >= 0.50
    ):
        classification = "LOW_COMPLEXITY_RESIDUAL_SEQUENCE"

    elif context_mean_q < LOW_QUALITY_Q:
        classification = "LOW_QUALITY_RESIDUAL_SEQUENCE"

    elif len(sequence) < 80:
        classification = "SHORT_CONTEXT_UNRESOLVED"

    else:
        classification = "NONUNIQUE_OR_UNRESOLVED_CONTEXT"

    counts[
        "context_class::{}".format(classification)
    ] += 1

    context_audit_rows.append(
        {
            "model_id": model_id,
            "context_id": context_id,
            "event_id": meta["event_id"],
            "read_id": meta["read_id"],
            "side": meta["side"],
            "context_bp": len(sequence),
            "context_entropy_bits": "{:.6f}".format(
                context_entropy
            ),
            "context_mean_q": "{:.6f}".format(
                context_mean_q
            ),
            "dominant_base": dominant_base,
            "dominant_base_fraction": "{:.6f}".format(
                dominant_fraction
            ),
            "longest_homopolymer_bp": hp_length,
            "longest_homopolymer_base": hp_base,
            "longest_homopolymer_fraction": "{:.6f}".format(
                hp_length / len(sequence)
            ),
            "AAG_phase_purity": "{:.6f}".format(
                motif_results["AAG"][0]
            ),
            "AAGGAAGGAG_phase_purity": "{:.6f}".format(
                motif_results["AAGGAAGGAG"][0]
            ),
            "best_context_motif": best_context_motif,
            "best_context_motif_purity": "{:.6f}".format(
                best_context_purity
            ),
            "sliding_windows": len(windows),
            "repeat_like_windows": repeat_like_windows,
            "repeat_like_window_fraction": "{:.6f}".format(
                repeat_like_fraction
            ),
            "best_window_motif_purity": "{:.6f}".format(
                best_window_purity
            ),
            "previous_anchor_candidate": str(
                previous_anchor
            ).lower(),
            "residual_context_class": classification,
        }
    )

with open(
    context_audit_path,
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    fields = list(context_audit_rows[0].keys())
    writer = csv.DictWriter(
        handle,
        fieldnames=fields,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(context_audit_rows)

with open(
    windows_path,
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=window_fields,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(window_rows)

local_summary_rows = []

for read_id in sorted(read_ids):
    rows = paf_by_read.get(read_id, [])
    rows.sort(
        key=lambda row: (
            row["alignment_score"],
            row["query_coverage"],
            row["identity"],
        ),
        reverse=True,
    )

    if rows:
        best = rows[0]
        local_summary_rows.append(
            {
                "model_id": model_id,
                "read_id": read_id,
                "alignment_count": len(rows),
                "best_query_length": best["query_length"],
                "best_query_start": best["query_start"],
                "best_query_end": best["query_end"],
                "best_query_coverage": "{:.6f}".format(
                    best["query_coverage"]
                ),
                "best_strand": best["strand"],
                "best_target_id": best["target_id"],
                "best_target_start": best["target_start"],
                "best_target_end": best["target_end"],
                "best_reference_span_bp": (
                    best["target_end"] - best["target_start"]
                ),
                "best_identity": "{:.6f}".format(
                    best["identity"]
                ),
                "best_mapq": best["mapq"],
                "best_alignment_score": best[
                    "alignment_score"
                ],
                "full_read_locus_compatibility": (
                    "EXTENDED_LOCUS_ALIGNMENT_PRESENT"
                ),
            }
        )
    else:
        local_summary_rows.append(
            {
                "model_id": model_id,
                "read_id": read_id,
                "alignment_count": 0,
                "best_query_length": ".",
                "best_query_start": ".",
                "best_query_end": ".",
                "best_query_coverage": ".",
                "best_strand": ".",
                "best_target_id": ".",
                "best_target_start": ".",
                "best_target_end": ".",
                "best_reference_span_bp": ".",
                "best_identity": ".",
                "best_mapq": ".",
                "best_alignment_score": ".",
                "full_read_locus_compatibility": (
                    "NO_EXTENDED_LOCUS_ALIGNMENT"
                ),
            }
        )

with open(
    local_summary_path,
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    fields = list(local_summary_rows[0].keys())
    writer = csv.DictWriter(
        handle,
        fieldnames=fields,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(local_summary_rows)

status = "PASS"

if (
    len(flank_rows) != EXPECTED_EVENTS
    or len(metadata_rows) != EXPECTED_CONTEXTS
    or len(context_audit_rows) != EXPECTED_CONTEXTS
    or len(local_summary_rows) != EXPECTED_EVENTS
):
    status = "REVIEW"

with open(qc_path, "w", encoding="utf-8") as handle:
    handle.write("metric\tvalue\n")
    handle.write(
        "expected_events\t{}\n".format(
            EXPECTED_EVENTS
        )
    )
    handle.write(
        "observed_events\t{}\n".format(
            len(flank_rows)
        )
    )
    handle.write(
        "expected_contexts\t{}\n".format(
            EXPECTED_CONTEXTS
        )
    )
    handle.write(
        "observed_contexts\t{}\n".format(
            len(context_audit_rows)
        )
    )
    handle.write(
        "window_rows_written\t{}\n".format(
            len(window_rows)
        )
    )
    handle.write(
        "local_paf_rows\t{}\n".format(
            len(paf_rows)
        )
    )
    handle.write(
        "full_reads_with_extended_locus_alignment\t{}\n".format(
            sum(
                row["alignment_count"] > 0
                for row in local_summary_rows
            )
        )
    )

    for key, value in sorted(counts.items()):
        handle.write("{}\t{}\n".format(key, value))

    handle.write("flank_rescues_emitted\t0\n")
    handle.write("allele_length_calls_emitted\t0\n")
    handle.write("expansion_calls_emitted\t0\n")
    handle.write(
        "audit_status\t{}\n".format(status)
    )

if status != "PASS":
    raise SystemExit(
        "Residual context audit requires review"
    )
PY

echo "===== SHELL AND EMBEDDED PYTHON SYNTAX ====="
python -m py_compile "$PREPARE_PY"
python -m py_compile "$PARSE_PY"
echo "Embedded Python syntax: OK"

rm -f \
  "$FULL_READ_FASTA" \
  "$EXTENDED_LOCUS_FASTA" \
  "$CONTEXT_AUDIT" \
  "$WINDOWS" \
  "$BAM_AUDIT" \
  "$LOCAL_PAF" \
  "$LOCAL_SUMMARY" \
  "$QC" \
  "$MANIFEST"

echo
echo "===== PREPARE CONTEXT AND SOURCE-READ AUDIT ====="

python "$PREPARE_PY" \
  "$FLANK_SUMMARY" \
  "$CONTEXT_META" \
  "$CONTEXT_FASTA" \
  "$FASTQ" \
  "$BAM" \
  "$REFERENCE_FASTA" \
  "$FULL_READ_FASTA" \
  "$EXTENDED_LOCUS_FASTA" \
  "$BAM_AUDIT" \
  "$EXPECTED_EVENTS" \
  "$EXPECTED_CONTEXTS" \
  "$LOCUS_FLANK_BP"

echo
echo "===== ALIGN FULL READS TO EXTENDED LOCUS ====="

minimap2 \
  -x splice \
  -k12 \
  -w5 \
  -G200k \
  -N50 \
  -p0.50 \
  -c \
  --cs=long \
  --secondary=yes \
  -t4 \
  "$EXTENDED_LOCUS_FASTA" \
  "$FULL_READ_FASTA" \
  > "$LOCAL_PAF"

echo
echo "===== CLASSIFY RESIDUAL CONTEXTS ====="

python "$PARSE_PY" \
  "$FLANK_SUMMARY" \
  "$CONTEXT_META" \
  "$CONTEXT_FASTA" \
  "$FASTQ" \
  "$LOCAL_PAF" \
  "$CONTEXT_AUDIT" \
  "$WINDOWS" \
  "$LOCAL_SUMMARY" \
  "$QC" \
  "$MODEL_ID" \
  "$EXPECTED_EVENTS" \
  "$EXPECTED_CONTEXTS" \
  "$WINDOW_BP" \
  "$WINDOW_STEP_BP" \
  "$REPEAT_LIKE_PURITY" \
  "$LOW_COMPLEXITY_ENTROPY" \
  "$LOW_QUALITY_MEAN_Q"

echo
echo "===== QC ====="
column -ts $'\t' "$QC"

echo
echo "===== RESIDUAL CONTEXT AUDIT ====="
column -ts $'\t' "$CONTEXT_AUDIT"

echo
echo "===== SOURCE BAM GEOMETRY ====="
column -ts $'\t' "$BAM_AUDIT"

echo
echo "===== FULL READ / EXTENDED LOCUS ALIGNMENT ====="
column -ts $'\t' "$LOCAL_SUMMARY"

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in \
      "$CONTEXT_AUDIT" \
      "$WINDOWS" \
      "$BAM_AUDIT" \
      "$LOCAL_PAF" \
      "$LOCAL_SUMMARY" \
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
