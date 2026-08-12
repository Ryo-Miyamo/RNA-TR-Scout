#!/usr/bin/env bash
set -euo pipefail

source /mnt/intelssd/rnatr_project/config/paths.env

TREXDIR="$CATALOG_ROOT/trexplorer_v2"
BASE_BED="$TREXDIR/TRExplorer.repeat_catalog_v2.hg38.1_to_1000bp_motifs.bed.gz"
FORCED="$TREXDIR/rnatr_pilot_v03/TRExplorer_v2.rnatr_forced_disease_loci.tsv.gz"

OUTROOT="$CATALOG_ROOT/strchive/current"
WORKDIR="$PROJECT_ROOT/tmp/09d_strchive_concordance"

STRCHIVE_BED="$OUTROOT/STRchive-disease-loci.hg38.general.bed"
COMMIT_JSON="$OUTROOT/STRchive.main.commit.json"
SOURCE_MANIFEST="$OUTROOT/STRchive.source_manifest.tsv"

CONCORDANCE="$OUTROOT/STRchive_vs_TRExplorer.concordance.tsv"
FORCED_AUDIT="$OUTROOT/TRExplorer_forced_vs_STRchive.tsv"
SUMMARY="$OUTROOT/STRchive_vs_TRExplorer.summary.tsv"

PYTHON_SCRIPT="$WORKDIR/audit_strchive_concordance.py"

mkdir -p "$OUTROOT" "$WORKDIR"

for path in "$BASE_BED" "${BASE_BED}.tbi" "$FORCED"; do
    test -s "$path" || {
        echo "ERROR: missing input: $path" >&2
        exit 1
    }
done

for tool in curl jq python sha256sum; do
    command -v "$tool" >/dev/null || {
        echo "ERROR: required tool not found: $tool" >&2
        exit 1
    }
done

echo "===== 1. FETCH CURRENT STRchive SOURCE ====="

curl \
  --fail \
  --location \
  --retry 5 \
  --retry-delay 3 \
  'https://raw.githubusercontent.com/dashnowlab/STRchive/refs/heads/main/data/catalogs/STRchive-disease-loci.hg38.general.bed' \
  --output "$STRCHIVE_BED"

curl \
  --fail \
  --location \
  --retry 5 \
  --retry-delay 3 \
  --header 'Accept: application/vnd.github+json' \
  --header 'X-GitHub-Api-Version: 2022-11-28' \
  'https://api.github.com/repos/dashnowlab/STRchive/commits/main' \
  --output "$COMMIT_JSON"

jq empty "$COMMIT_JSON"

COMMIT_SHA="$(jq -r '.sha' "$COMMIT_JSON")"
COMMIT_DATE="$(jq -r '.commit.committer.date' "$COMMIT_JSON")"
DATA_ROWS="$(
  awk '
    !/^#/ && NF > 0 {
        count++
    }
    END {
        print count + 0
    }
  ' "$STRCHIVE_BED"
)"

{
    printf 'field\tvalue\n'
    printf 'repository\tdashnowlab/STRchive\n'
    printf 'branch\tmain\n'
    printf 'commit_sha\t%s\n' "$COMMIT_SHA"
    printf 'commit_date\t%s\n' "$COMMIT_DATE"
    printf 'retrieved_at\t%s\n' "$(date -Is)"
    printf 'catalog_file\t%s\n' "$(basename "$STRCHIVE_BED")"
    printf 'catalog_rows\t%s\n' "$DATA_ROWS"
    printf 'catalog_bytes\t%s\n' "$(stat -c '%s' "$STRCHIVE_BED")"
    printf 'catalog_sha256\t%s\n' "$(sha256sum "$STRCHIVE_BED" | awk '{print $1}')"
} > "$SOURCE_MANIFEST"

column -ts $'\t' "$SOURCE_MANIFEST"

echo
echo "===== 2. AUDIT STRchive ↔ TRExplorer CONCORDANCE ====="

cat > "$PYTHON_SCRIPT" <<'PY'
import csv
import gzip
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Iterable

import pysam

(
    strchive_path,
    trex_bed_path,
    forced_path,
    concordance_path,
    forced_audit_path,
    summary_path,
) = sys.argv[1:]

IUPAC_COMPLEMENT = str.maketrans(
    {
        "A": "T",
        "C": "G",
        "G": "C",
        "T": "A",
        "N": "N",
        "R": "Y",
        "Y": "R",
        "S": "S",
        "W": "W",
        "K": "M",
        "M": "K",
        "B": "V",
        "D": "H",
        "H": "D",
        "V": "B",
    }
)


def reverse_complement(sequence: str) -> str:
    return sequence.translate(IUPAC_COMPLEMENT)[::-1]


def canonical_motif(sequence: str) -> str:
    sequence = sequence.strip().upper()

    if not sequence:
        return ""

    rotations = []
    for oriented in (sequence, reverse_complement(sequence)):
        rotations.extend(
            oriented[index:] + oriented[:index]
            for index in range(len(oriented))
        )

    return min(rotations)


def split_motifs(text: str) -> list[str]:
    if not text:
        return []

    values = []
    for item in re.split(r"[,;/|]", text):
        item = item.strip().upper()
        if item and item not in {"NONE", "."}:
            values.append(item)
    return values


def motif_set(reference: str, pathogenic: str) -> set[str]:
    return {
        canonical_motif(motif)
        for motif in split_motifs(reference) + split_motifs(pathogenic)
        if motif
    }


@dataclass(frozen=True)
class STRchiveLocus:
    chrom: str
    start: int
    end: int
    locus_id: str
    gene: str
    reference_motif: str
    pathogenic_motif: str
    pathogenic_min: str
    inheritance: str
    disease: str

    @property
    def motifs(self) -> set[str]:
        return motif_set(
            self.reference_motif,
            self.pathogenic_motif,
        )


@dataclass(frozen=True)
class TRExplorerLocus:
    chrom: str
    start: int
    end: int
    motif: str
    locus_id: str
    forced: bool

    @property
    def canonical(self) -> str:
        return canonical_motif(self.motif)


def read_forced_ids(path: str) -> set[str]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return {
            row["locus_id"]
            for row in reader
            if row.get("locus_id")
        }


def read_strchive(path: str) -> list[STRchiveLocus]:
    loci = []

    with open(path, encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")

        for fields in reader:
            if not fields or fields[0].startswith("#"):
                continue

            if len(fields) != 10:
                raise RuntimeError(
                    f"Unexpected STRchive field count: {len(fields)}"
                )

            loci.append(
                STRchiveLocus(
                    chrom=fields[0],
                    start=int(fields[1]),
                    end=int(fields[2]),
                    locus_id=fields[3],
                    gene=fields[4],
                    reference_motif=fields[5],
                    pathogenic_motif=fields[6],
                    pathogenic_min=fields[7],
                    inheritance=fields[8],
                    disease=fields[9],
                )
            )

    return loci


forced_ids = read_forced_ids(forced_path)
strchive = read_strchive(strchive_path)
tabix = pysam.TabixFile(trex_bed_path)

strchive_by_chrom = defaultdict(list)
for locus in strchive:
    strchive_by_chrom[locus.chrom].append(locus)

concordance_header = [
    "strchive_id",
    "gene",
    "chrom",
    "start",
    "end",
    "reference_motif",
    "pathogenic_motif",
    "candidate_count",
    "best_trexplorer_locus_id",
    "best_trexplorer_start",
    "best_trexplorer_end",
    "best_trexplorer_motif",
    "coordinate_exact",
    "overlap_bp",
    "boundary_delta_bp",
    "motif_compatible",
    "trexplorer_already_forced",
    "match_class",
    "external_override_action",
    "inheritance",
    "pathogenic_min",
    "disease",
]

summary = Counter()
best_matches = {}
all_candidate_ids = defaultdict(set)

with open(concordance_path, "w", encoding="utf-8", newline="") as output:
    writer = csv.writer(
        output,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writerow(concordance_header)

    for locus in strchive:
        query_start = max(0, locus.start - 100)
        query_end = locus.end + 100
        candidates = []

        try:
            records = tabix.fetch(
                locus.chrom,
                query_start,
                query_end,
            )
        except ValueError:
            records = []

        for record in records:
            fields = record.rstrip("\n").split("\t")
            if len(fields) < 4:
                continue

            chrom = fields[0]
            start = int(fields[1])
            end = int(fields[2])
            motif = fields[3]

            trex_id = (
                f"{chrom.removeprefix('chr')}-"
                f"{start}-{end}-{motif}"
            )

            overlap = max(
                0,
                min(locus.end, end) - max(locus.start, start),
            )
            coordinate_exact = (
                start == locus.start and end == locus.end
            )
            boundary_delta = (
                abs(start - locus.start)
                + abs(end - locus.end)
            )
            motif_compatible = (
                canonical_motif(motif) in locus.motifs
            )

            candidate = TRExplorerLocus(
                chrom=chrom,
                start=start,
                end=end,
                motif=motif,
                locus_id=trex_id,
                forced=trex_id in forced_ids,
            )

            candidates.append(
                (
                    candidate,
                    overlap,
                    coordinate_exact,
                    boundary_delta,
                    motif_compatible,
                )
            )
            all_candidate_ids[locus.locus_id].add(trex_id)

        def ranking(item):
            candidate, overlap, coordinate_exact, boundary_delta, motif_ok = item

            if coordinate_exact and motif_ok:
                match_rank = 5
            elif overlap > 0 and motif_ok:
                match_rank = 4
            elif coordinate_exact:
                match_rank = 3
            elif overlap > 0:
                match_rank = 2
            else:
                match_rank = 1

            return (
                match_rank,
                overlap,
                -boundary_delta,
                candidate.forced,
                -len(candidate.motif),
            )

        best = max(candidates, key=ranking) if candidates else None

        if best is None:
            candidate = None
            overlap = 0
            coordinate_exact = False
            boundary_delta = ""
            motif_ok = False
            match_class = "NO_CATALOG_CANDIDATE"
            action = "ADD_EXTERNAL_FALLBACK"
        else:
            (
                candidate,
                overlap,
                coordinate_exact,
                boundary_delta,
                motif_ok,
            ) = best

            if coordinate_exact and motif_ok:
                match_class = "EXACT_COORDINATE_AND_MOTIF"
            elif overlap > 0 and motif_ok:
                match_class = "OVERLAP_AND_MOTIF"
            elif coordinate_exact:
                match_class = "EXACT_COORDINATE_MOTIF_MISMATCH"
            elif overlap > 0:
                match_class = "OVERLAP_ONLY"
            else:
                match_class = "NEARBY_ONLY"

            if candidate.forced and motif_ok and overlap > 0:
                action = "ALREADY_FORCED"
            elif motif_ok and overlap > 0:
                action = "FORCE_MATCHED_TREXPLORER_LOCUS"
            else:
                action = "MANUAL_REVIEW_OR_EXTERNAL_FALLBACK"

            best_matches[locus.locus_id] = candidate.locus_id

        summary[f"match::{match_class}"] += 1
        summary[f"action::{action}"] += 1

        writer.writerow(
            [
                locus.locus_id,
                locus.gene,
                locus.chrom,
                locus.start,
                locus.end,
                locus.reference_motif,
                locus.pathogenic_motif,
                len(candidates),
                candidate.locus_id if candidate else "",
                candidate.start if candidate else "",
                candidate.end if candidate else "",
                candidate.motif if candidate else "",
                str(coordinate_exact).lower(),
                overlap,
                boundary_delta,
                str(motif_ok).lower(),
                (
                    str(candidate.forced).lower()
                    if candidate
                    else "false"
                ),
                match_class,
                action,
                locus.inheritance,
                locus.pathogenic_min,
                locus.disease,
            ]
        )

forced_audit_header = [
    "trexplorer_locus_id",
    "chrom",
    "start",
    "end",
    "motif",
    "overlapping_strchive_count",
    "motif_compatible_strchive_count",
    "strchive_ids",
    "audit_class",
]

forced_rows = []

with gzip.open(
    forced_path,
    "rt",
    encoding="utf-8",
    newline="",
) as handle:
    reader = csv.DictReader(handle, delimiter="\t")

    for row in reader:
        trex_id = row["locus_id"]
        chrom = row["chrom"]
        start = int(row["start"])
        end = int(row["end"])
        motif = row["motif"]
        canonical = canonical_motif(motif)

        overlaps = []
        compatible = []

        for locus in strchive_by_chrom.get(chrom, []):
            overlap = max(
                0,
                min(end, locus.end) - max(start, locus.start),
            )

            if overlap <= 0:
                continue

            overlaps.append(locus)
            if canonical in locus.motifs:
                compatible.append(locus)

        if compatible:
            audit_class = "MATCHED_STRCHIVE_MOTIF"
        elif overlaps:
            audit_class = "OVERLAP_STRCHIVE_MOTIF_MISMATCH"
        else:
            audit_class = "TREXPLORER_FORCED_ONLY"

        summary[f"forced_audit::{audit_class}"] += 1

        forced_rows.append(
            [
                trex_id,
                chrom,
                start,
                end,
                motif,
                len(overlaps),
                len(compatible),
                ",".join(locus.locus_id for locus in overlaps),
                audit_class,
            ]
        )

with open(
    forced_audit_path,
    "w",
    encoding="utf-8",
    newline="",
) as output:
    writer = csv.writer(
        output,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writerow(forced_audit_header)
    writer.writerows(forced_rows)

status = "PASS"
if len(strchive) == 0 or len(forced_ids) == 0:
    status = "REVIEW"

with open(summary_path, "w", encoding="utf-8") as output:
    output.write("metric\tvalue\n")
    output.write(f"strchive_loci\t{len(strchive)}\n")
    output.write(f"trexplorer_forced_loci\t{len(forced_ids)}\n")

    for key, value in sorted(summary.items()):
        output.write(f"{key}\t{value}\n")

    output.write(f"audit_status\t{status}\n")

print(
    f"[INFO] STRchive loci: {len(strchive)}",
    file=sys.stderr,
)
print(
    f"[INFO] TRExplorer forced loci: {len(forced_ids)}",
    file=sys.stderr,
)
PY

python "$PYTHON_SCRIPT" \
  "$STRCHIVE_BED" \
  "$BASE_BED" \
  "$FORCED" \
  "$CONCORDANCE" \
  "$FORCED_AUDIT" \
  "$SUMMARY"

echo
echo "===== CONCORDANCE SUMMARY ====="
column -ts $'\t' "$SUMMARY"

echo
echo "===== STRchive LOCI REQUIRING ACTION ====="
awk -F '\t' '
NR == 1 || $19 != "ALREADY_FORCED"
' "$CONCORDANCE" |
column -ts $'\t' |
sed -n '1,120p'

echo
echo "===== TRExplorer FORCED-ONLY EXAMPLES ====="
awk -F '\t' '
NR == 1 || $9 != "MATCHED_STRCHIVE_MOTIF"
' "$FORCED_AUDIT" |
column -ts $'\t' |
sed -n '1,120p'

echo
echo "===== COMPLETE ====="
echo "$SOURCE_MANIFEST"
echo "$CONCORDANCE"
echo "$FORCED_AUDIT"
echo "$SUMMARY"
