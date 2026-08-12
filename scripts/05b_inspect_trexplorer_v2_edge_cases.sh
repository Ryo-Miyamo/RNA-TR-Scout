#!/usr/bin/env bash
set -euo pipefail

source /mnt/intelssd/rnatr_project/config/paths.env

CATDIR="$CATALOG_ROOT/trexplorer_v2"
BED="$CATDIR/TRExplorer.repeat_catalog_v2.hg38.1_to_1000bp_motifs.bed.gz"
REF="$PROJECT_ROOT/refs/gencode_v50/GRCh38.primary_assembly.genome.fa"
AUDITDIR="$CATDIR/audit"

mkdir -p "$AUDITDIR"

NON_ACGT="$AUDITDIR/TRExplorer_v2.non_acgt_motifs.tsv"
REPEATED="$AUDITDIR/TRExplorer_v2.repeated_coordinates.tsv"
SAMPLE="$AUDITDIR/TRExplorer_v2.reference_check.random1000.tsv"
SAMPLE_SUMMARY="$AUDITDIR/TRExplorer_v2.reference_check.random1000.summary.tsv"

test -s "$BED" || { echo "ERROR: missing $BED" >&2; exit 1; }
test -s "$REF" || { echo "ERROR: missing $REF" >&2; exit 1; }

echo "===== 1. NON-ACGT MOTIFS ====="
gzip -cd "$BED" |
awk -F '\t' '
BEGIN {
    OFS = "\t"
    print "line_number", "chrom", "start", "end", "motif", "column5"
}
toupper($4) !~ /^[ACGT]+$/ {
    print NR, $1, $2, $3, $4, $5
}
' > "$NON_ACGT"

column -ts $'\t' "$NON_ACGT"
echo

echo "===== 2. REPEATED COORDINATES ====="
gzip -cd "$BED" |
awk -F '\t' '
BEGIN {
    OFS = "\t"
    print "chrom", "start", "end", "entry_count", "motifs"
}
function emit_group() {
    if (count > 1) {
        print prev_chrom, prev_start, prev_end, count, motifs
    }
}
{
    key = $1 FS $2 FS $3

    if (NR == 1) {
        prev_key = key
        prev_chrom = $1
        prev_start = $2
        prev_end = $3
        count = 1
        motifs = $4
        next
    }

    if (key == prev_key) {
        count++
        motifs = motifs "," $4
    } else {
        emit_group()
        prev_key = key
        prev_chrom = $1
        prev_start = $2
        prev_end = $3
        count = 1
        motifs = $4
    }
}
END {
    emit_group()
}
' > "$REPEATED"

echo -n "Repeated-coordinate groups: "
awk 'NR > 1 {n++} END {print n+0}' "$REPEATED"

echo "First 20 groups:"
head -n 21 "$REPEATED" | column -ts $'\t'
echo

echo "===== 3. RANDOM 1000-LOCUS REFERENCE CHECK ====="

python - "$BED" "$REF" "$SAMPLE" "$SAMPLE_SUMMARY" <<'PY'
import gzip
import math
import random
import statistics
import sys
from pathlib import Path

import pysam

bed_path, ref_path, output_path, summary_path = sys.argv[1:]
sample_size = 1000
seed = 20260803
rng = random.Random(seed)

reservoir = []

with gzip.open(bed_path, "rt") as handle:
    for index, line in enumerate(handle):
        fields = line.rstrip("\n").split("\t")
        if len(fields) != 5:
            continue

        record = (
            fields[0],
            int(fields[1]),
            int(fields[2]),
            fields[3].upper(),
            fields[4],
        )

        if len(reservoir) < sample_size:
            reservoir.append(record)
        else:
            replacement = rng.randint(0, index)
            if replacement < sample_size:
                reservoir[replacement] = record

def reverse_complement(sequence: str) -> str:
    table = str.maketrans("ACGTN", "TGCAN")
    return sequence.translate(table)[::-1]

def rotations(sequence: str):
    if not sequence:
        return []
    return [sequence[i:] + sequence[:i] for i in range(len(sequence))]

def periodic_identity(reference: str, motif: str):
    allowed = set("ACGT")
    if not motif or any(base not in allowed for base in motif):
        return None, None, None

    candidates = []
    seen = set()

    for orientation, sequence in (
        ("forward", motif),
        ("reverse_complement", reverse_complement(motif)),
    ):
        for rotation_index, rotated in enumerate(rotations(sequence)):
            if rotated in seen:
                continue
            seen.add(rotated)
            candidates.append((orientation, rotation_index, rotated))

    best = None

    for orientation, rotation_index, rotated in candidates:
        matches = sum(
            base == rotated[i % len(rotated)]
            for i, base in enumerate(reference)
        )
        identity = matches / len(reference) if reference else float("nan")

        candidate = (
            identity,
            orientation,
            rotation_index,
            rotated,
        )

        if best is None or candidate[0] > best[0]:
            best = candidate

    return best

fasta = pysam.FastaFile(ref_path)
rows = []
identities = []
invalid_fetch = 0
non_acgt = 0

for chrom, start, end, motif, column5 in reservoir:
    try:
        sequence = fasta.fetch(chrom, start, end).upper()
    except Exception:
        invalid_fetch += 1
        continue

    expected_length = end - start
    fetched_length = len(sequence)
    result = periodic_identity(sequence, motif)

    if result[0] is None:
        non_acgt += 1
        identity = None
        orientation = ""
        rotation_index = ""
        best_motif = ""
    else:
        identity, orientation, rotation_index, best_motif = result
        identities.append(identity)

    rows.append(
        (
            chrom,
            start,
            end,
            motif,
            expected_length,
            fetched_length,
            identity,
            orientation,
            rotation_index,
            best_motif,
        )
    )

with open(output_path, "w") as out:
    out.write(
        "chrom\tstart\tend\tmotif\tinterval_bp\tfetched_bp\t"
        "best_periodic_identity\tbest_orientation\t"
        "best_rotation_index\tbest_rotated_motif\n"
    )

    for row in rows:
        identity = "" if row[6] is None else f"{row[6]:.6f}"
        values = [
            str(row[0]),
            str(row[1]),
            str(row[2]),
            str(row[3]),
            str(row[4]),
            str(row[5]),
            identity,
            str(row[7]),
            str(row[8]),
            str(row[9]),
        ]
        out.write("\t".join(values) + "\n")

def percentile(values, p):
    if not values:
        return float("nan")
    ordered = sorted(values)
    position = (len(ordered) - 1) * p
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction

with open(summary_path, "w") as out:
    out.write("metric\tvalue\n")
    out.write(f"sample_seed\t{seed}\n")
    out.write(f"requested_loci\t{sample_size}\n")
    out.write(f"evaluated_loci\t{len(rows)}\n")
    out.write(f"invalid_reference_fetch\t{invalid_fetch}\n")
    out.write(f"non_acgt_sampled\t{non_acgt}\n")

    if identities:
        out.write(f"identity_min\t{min(identities):.6f}\n")
        out.write(f"identity_q1\t{percentile(identities, 0.25):.6f}\n")
        out.write(f"identity_median\t{statistics.median(identities):.6f}\n")
        out.write(f"identity_q3\t{percentile(identities, 0.75):.6f}\n")
        out.write(f"identity_max\t{max(identities):.6f}\n")
        out.write(
            "identity_ge_0.90\t"
            f"{sum(value >= 0.90 for value in identities)}\n"
        )
        out.write(
            "identity_ge_0.95\t"
            f"{sum(value >= 0.95 for value in identities)}\n"
        )
        out.write(
            "identity_eq_1.00\t"
            f"{sum(value == 1.0 for value in identities)}\n"
        )
PY

column -ts $'\t' "$SAMPLE_SUMMARY"

echo
echo "First 20 sampled loci:"
head -n 21 "$SAMPLE" | column -ts $'\t'

echo
echo "Output files:"
printf '%s\n' \
  "$NON_ACGT" \
  "$REPEATED" \
  "$SAMPLE" \
  "$SAMPLE_SUMMARY"
