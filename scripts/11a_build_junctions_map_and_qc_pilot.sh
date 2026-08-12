#!/usr/bin/env bash
set -euo pipefail

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
fi
conda activate rnatr-v03
source /mnt/intelssd/rnatr_project/config/paths.env

SAMPLE_ID="ENCSR307SHM"
FASTQ_ACCESSION="ENCFF260PGB"
RUN_ID="${SAMPLE_ID}_pilot100k_mm2splice_v1"
PARAMETER_SET_ID="rnatr_mm2_splice_cDNA_v0.3.1"

FASTQ="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/ENCFF260PGB.pilot_100k.seed20260803.fastq.gz"

REFDIR="$PROJECT_ROOT/refs/gencode_v50"
REF_FASTA="$REFDIR/GRCh38.primary_assembly.genome.fa"
REF_MMI="$REFDIR/GRCh38.primary_assembly.genome.mmi"
REF_FAI="$REF_FASTA.fai"
GTF="$REFDIR/gencode.v50.primary_assembly.annotation.gtf"

JUNCTION_DIR="$REFDIR/junctions"
JUNCTION_BED12="$JUNCTION_DIR/gencode.v50.multi_exon_transcripts.bed12"
JUNCTION_SUMMARY="$JUNCTION_DIR/gencode.v50.multi_exon_transcripts.summary.tsv"
JUNCTION_SHA="$JUNCTION_DIR/gencode.v50.multi_exon_transcripts.sha256"

OUTDIR="$PROJECT_ROOT/results/11_mapping/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_mapping/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_mapping/$RUN_ID"
SCHEMA_DIR="$PROJECT_ROOT/config/evidence_schema/v0.3"

BAM="$OUTDIR/${RUN_ID}.sorted.bam"
BAI="${BAM}.bai"
MM2_LOG="$OUTDIR/${RUN_ID}.minimap2.log"
COMMAND_FILE="$OUTDIR/${RUN_ID}.mapper_command.sh"
RUN_MANIFEST="$OUTDIR/run_manifest.tsv"

FLAGSTAT="$QCDIR/${RUN_ID}.flagstat.txt"
STATS="$QCDIR/${RUN_ID}.samtools_stats.txt"
IDXSTATS="$QCDIR/${RUN_ID}.idxstats.tsv"
QC_SUMMARY="$QCDIR/${RUN_ID}.mapping_qc.tsv"
TIME_SUMMARY="$QCDIR/${RUN_ID}.runtime.tsv"

JUNCTION_BUILDER="$WORKDIR/build_gencode_bed12.py"
BAM_QC="$WORKDIR/summarize_bam.py"

THREADS_MM2="${THREADS_MM2:-16}"
THREADS_SORT="${THREADS_SORT:-8}"
SECONDARY_MAX="${SECONDARY_MAX:-10}"
SORT_MEM="${SORT_MEM:-1G}"

mkdir -p \
  "$JUNCTION_DIR" \
  "$OUTDIR" \
  "$QCDIR" \
  "$WORKDIR"

for path in \
  "$FASTQ" \
  "$REF_FASTA" \
  "$REF_MMI" \
  "$REF_FAI" \
  "$GTF" \
  "$SCHEMA_DIR/schema/rnatr_v03_table_schema.json" \
  "$SCHEMA_DIR/rnatr_v03_validate_tsv.py"
do
    test -s "$path" || {
        echo "ERROR: required input missing: $path" >&2
        exit 1
    }
done

for tool in minimap2 samtools python bedtools; do
    command -v "$tool" >/dev/null || {
        echo "ERROR: required tool not found: $tool" >&2
        exit 1
    }
done

cat > "$JUNCTION_BUILDER" <<'PY'
import re
import sys
from collections import Counter

gtf_path, fai_path, output_path, summary_path = sys.argv[1:]

contig_rank = {}
with open(fai_path, encoding="utf-8") as handle:
    for rank, line in enumerate(handle):
        contig = line.split("\t", 1)[0]
        contig_rank[contig] = rank

attribute_pattern = re.compile(r'(\S+) "([^"]*)";')

transcripts = {}
counts = Counter()

with open(gtf_path, encoding="utf-8") as handle:
    for line in handle:
        if not line or line.startswith("#"):
            continue

        fields = line.rstrip("\n").split("\t")
        if len(fields) != 9 or fields[2] != "exon":
            continue

        chrom = fields[0]
        start0 = int(fields[3]) - 1
        end = int(fields[4])
        strand = fields[6]
        attrs = dict(attribute_pattern.findall(fields[8]))
        transcript_id = attrs.get("transcript_id", "")

        if not transcript_id:
            counts["exon_without_transcript_id"] += 1
            continue

        record = transcripts.get(transcript_id)

        if record is None:
            transcripts[transcript_id] = {
                "chrom": chrom,
                "strand": strand,
                "exons": [(start0, end)],
            }
        else:
            if record["chrom"] != chrom or record["strand"] != strand:
                counts["inconsistent_transcript_record"] += 1
                continue
            record["exons"].append((start0, end))

        counts["exons_read"] += 1

bed_rows = []
junctions = 0
single_exon = 0

for transcript_id, record in transcripts.items():
    exons = sorted(set(record["exons"]))

    if len(exons) < 2:
        single_exon += 1
        continue

    chrom_start = exons[0][0]
    chrom_end = exons[-1][1]
    block_sizes = [end - start for start, end in exons]
    block_starts = [start - chrom_start for start, _ in exons]

    bed_rows.append(
        (
            contig_rank.get(record["chrom"], 10**9),
            record["chrom"],
            chrom_start,
            chrom_end,
            transcript_id,
            record["strand"],
            block_sizes,
            block_starts,
        )
    )
    junctions += len(exons) - 1

bed_rows.sort(key=lambda row: (row[0], row[2], row[3], row[4]))

with open(output_path, "w", encoding="utf-8") as output:
    for (
        _rank,
        chrom,
        chrom_start,
        chrom_end,
        transcript_id,
        strand,
        block_sizes,
        block_starts,
    ) in bed_rows:
        output.write(
            "\t".join(
                [
                    chrom,
                    str(chrom_start),
                    str(chrom_end),
                    transcript_id,
                    "0",
                    strand,
                    str(chrom_start),
                    str(chrom_start),
                    "0",
                    str(len(block_sizes)),
                    ",".join(map(str, block_sizes)) + ",",
                    ",".join(map(str, block_starts)) + ",",
                ]
            )
            + "\n"
        )

with open(summary_path, "w", encoding="utf-8") as output:
    output.write("metric\tvalue\n")
    output.write(f"transcripts_seen\t{len(transcripts)}\n")
    output.write(f"multi_exon_transcripts\t{len(bed_rows)}\n")
    output.write(f"single_exon_transcripts\t{single_exon}\n")
    output.write(f"junctions_represented\t{junctions}\n")

    for key, value in sorted(counts.items()):
        output.write(f"{key}\t{value}\n")
PY

cat > "$BAM_QC" <<'PY'
import sys
from collections import Counter

import pysam

bam_path, output_path, expected_reads_text = sys.argv[1:]
expected_reads = int(expected_reads_text)

counts = Counter()
unique_reads = set()
primary_mapped_reads = set()
primary_unmapped_reads = set()
spliced_primary_reads = set()
softclipped_primary_reads = set()
insertion_primary_reads = set()
sa_primary_reads = set()

with pysam.AlignmentFile(bam_path, "rb") as bam:
    for record in bam.fetch(until_eof=True):
        counts["alignment_records"] += 1
        unique_reads.add(record.query_name)

        if record.is_unmapped:
            counts["unmapped_records"] += 1
        else:
            counts["mapped_records"] += 1

        if record.is_secondary:
            counts["secondary_records"] += 1
            continue

        if record.is_supplementary:
            counts["supplementary_records"] += 1
            continue

        counts["primary_records"] += 1

        if record.is_unmapped:
            primary_unmapped_reads.add(record.query_name)
            continue

        primary_mapped_reads.add(record.query_name)

        cigartuples = record.cigartuples or []

        if any(operation == 3 for operation, _length in cigartuples):
            spliced_primary_reads.add(record.query_name)

        if any(operation == 4 for operation, _length in cigartuples):
            softclipped_primary_reads.add(record.query_name)

        if any(operation == 1 for operation, _length in cigartuples):
            insertion_primary_reads.add(record.query_name)

        if record.has_tag("SA"):
            sa_primary_reads.add(record.query_name)

metrics = {
    **counts,
    "unique_reads": len(unique_reads),
    "primary_mapped_reads": len(primary_mapped_reads),
    "primary_unmapped_reads": len(primary_unmapped_reads),
    "spliced_primary_reads": len(spliced_primary_reads),
    "softclipped_primary_reads": len(softclipped_primary_reads),
    "insertion_primary_reads": len(insertion_primary_reads),
    "sa_tag_primary_reads": len(sa_primary_reads),
    "expected_input_reads": expected_reads,
}

metrics["primary_mapping_rate_percent"] = (
    100.0 * len(primary_mapped_reads) / expected_reads
    if expected_reads
    else 0.0
)
metrics["spliced_fraction_of_primary_mapped_percent"] = (
    100.0 * len(spliced_primary_reads) / len(primary_mapped_reads)
    if primary_mapped_reads
    else 0.0
)
metrics["softclipped_fraction_of_primary_mapped_percent"] = (
    100.0 * len(softclipped_primary_reads) / len(primary_mapped_reads)
    if primary_mapped_reads
    else 0.0
)

status = "PASS"

if len(unique_reads) != expected_reads:
    status = "REVIEW"

with open(output_path, "w", encoding="utf-8") as output:
    output.write("metric\tvalue\n")

    for key, value in metrics.items():
        if isinstance(value, float):
            output.write(f"{key}\t{value:.6f}\n")
        else:
            output.write(f"{key}\t{value}\n")

    output.write(f"audit_status\t{status}\n")

if status != "PASS":
    raise SystemExit(
        f"Expected {expected_reads} unique reads, found {len(unique_reads)}"
    )
PY

echo "===== INPUT ====="
ls -lh "$FASTQ"
echo "FASTQ MD5: $(md5sum "$FASTQ" | awk '{print $1}')"

echo
echo "===== 1. BUILD/VERIFY GENCODE BED12 ====="

if [[ ! -s "$JUNCTION_BED12" || "${REBUILD_JUNCTIONS:-0}" == "1" ]]; then
    rm -f "$JUNCTION_BED12" "$JUNCTION_SUMMARY" "$JUNCTION_SHA"

    python "$JUNCTION_BUILDER" \
      "$GTF" \
      "$REF_FAI" \
      "$JUNCTION_BED12" \
      "$JUNCTION_SUMMARY"

    sha256sum "$JUNCTION_BED12" \
      > "$JUNCTION_SHA"
fi

column -ts $'\t' "$JUNCTION_SUMMARY"
echo "BED12 bytes: $(stat -c '%s' "$JUNCTION_BED12")"
echo "BED12 SHA256: $(sha256sum "$JUNCTION_BED12" | awk '{print $1}')"

echo
echo "===== 2. MAP PILOT FASTQ ====="

printf -v RG \
  '@RG\tID:%s\tSM:%s\tPL:ONT\tLB:ONT_cDNA' \
  "$RUN_ID" \
  "$SAMPLE_ID"

printf '%q ' \
  minimap2 \
  -ax splice \
  -t "$THREADS_MM2" \
  --junc-bed "$JUNCTION_BED12" \
  --secondary=yes \
  -N "$SECONDARY_MAX" \
  --MD \
  --cs=long \
  -R "$RG" \
  "$REF_MMI" \
  "$FASTQ" \
  > "$COMMAND_FILE"

printf '%q ' \
  '|' \
  samtools sort \
  -@ "$THREADS_SORT" \
  -m "$SORT_MEM" \
  -T "$WORKDIR/sorttmp" \
  -o "$BAM" \
  - \
  >> "$COMMAND_FILE"

echo >> "$COMMAND_FILE"

START_ISO="$(date -Is)"
START_EPOCH="$(date +%s)"

set -o pipefail

minimap2 \
  -ax splice \
  -t "$THREADS_MM2" \
  --junc-bed "$JUNCTION_BED12" \
  --secondary=yes \
  -N "$SECONDARY_MAX" \
  --MD \
  --cs=long \
  -R "$RG" \
  "$REF_MMI" \
  "$FASTQ" \
  2> >(tee "$MM2_LOG" >&2) |
samtools sort \
  -@ "$THREADS_SORT" \
  -m "$SORT_MEM" \
  -T "$WORKDIR/sorttmp" \
  -o "$BAM" \
  -

END_EPOCH="$(date +%s)"
END_ISO="$(date -Is)"
WALL_SECONDS="$((END_EPOCH - START_EPOCH))"

echo
echo "===== 3. BAM INTEGRITY AND INDEX ====="

samtools quickcheck -v "$BAM"
samtools index -@ "$THREADS_SORT" "$BAM"

test -s "$BAI" || {
    echo "ERROR: BAM index was not created" >&2
    exit 1
}

echo "BAM quickcheck: OK"
ls -lh "$BAM" "$BAI"

echo
echo "===== 4. MAPPING QC ====="

samtools flagstat -@ "$THREADS_SORT" "$BAM" \
  > "$FLAGSTAT"

samtools stats -@ "$THREADS_SORT" "$BAM" \
  > "$STATS"

samtools idxstats "$BAM" \
  > "$IDXSTATS"

python "$BAM_QC" \
  "$BAM" \
  "$QC_SUMMARY" \
  100000

column -ts $'\t' "$QC_SUMMARY"

cat > "$TIME_SUMMARY" <<EOF
metric	value
start_time	$START_ISO
end_time	$END_ISO
wall_seconds	$WALL_SECONDS
threads_minimap2	$THREADS_MM2
threads_samtools_sort	$THREADS_SORT
sort_memory_per_thread	$SORT_MEM
EOF

echo
echo "===== 5. RUN MANIFEST ====="

FASTQ_MD5="$(md5sum "$FASTQ" | awk '{print $1}')"
STRCHIVE_COMMIT="$(
    awk -F '\t' '
      $1 == "commit_sha" {
          print $2
      }
    ' "$CATALOG_ROOT/strchive/current/STRchive.source_manifest.tsv"
)"
MINIMAP2_VERSION="$(minimap2 --version)"
GIT_COMMIT="."

if git -C "$PROJECT_ROOT/code" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    GIT_COMMIT="$(git -C "$PROJECT_ROOT/code" rev-parse HEAD)"
fi

MAPPER_COMMAND="$(
    tr '\t\n' '  ' < "$COMMAND_FILE" |
    sed -E 's/[[:space:]]+/ /g; s/^ //; s/ $//'
)"

cat > "$RUN_MANIFEST" <<EOF
schema_version	run_id	sample_id	input_fastq	input_fastq_md5	input_bam	reference_fasta	reference_build	gencode_release	tr_catalog_release	strchive_commit	mapper_name	mapper_version	mapper_command	parameter_set_id	library_platform	library_mode	software_git_commit	created_at	notes
0.3.0	$RUN_ID	$SAMPLE_ID	$FASTQ	$FASTQ_MD5	$BAM	$REF_FASTA	GRCh38	GENCODE_v50	TRExplorer_v2	${STRCHIVE_COMMIT:-.}	minimap2	$MINIMAP2_VERSION	$MAPPER_COMMAND	$PARAMETER_SET_ID	Oxford_Nanopore_PromethION	ONT_cDNA_subtype_unknown	$GIT_COMMIT	$END_ISO	pilot_100k_seed20260803;genome_wide_splice_mapping
EOF

python "$SCHEMA_DIR/rnatr_v03_validate_tsv.py" \
  --schema "$SCHEMA_DIR/schema/rnatr_v03_table_schema.json" \
  --table run_manifest \
  --input "$RUN_MANIFEST" \
  --max-rows 10

echo
echo "===== 6. OUTPUT MANIFEST ====="

{
    printf 'artifact\tbytes\tsha256\tpath\n'

    for path in \
      "$BAM" \
      "$BAI" \
      "$FLAGSTAT" \
      "$STATS" \
      "$IDXSTATS" \
      "$QC_SUMMARY" \
      "$TIME_SUMMARY" \
      "$RUN_MANIFEST" \
      "$COMMAND_FILE" \
      "$MM2_LOG"
    do
        printf '%s\t%s\t%s\t%s\n' \
          "$(basename "$path")" \
          "$(stat -c '%s' "$path")" \
          "$(sha256sum "$path" | awk '{print $1}')" \
          "$path"
    done
} > "$OUTDIR/${RUN_ID}.output_manifest.tsv"

column -ts $'\t' "$OUTDIR/${RUN_ID}.output_manifest.tsv"

echo
echo "===== COMPLETE ====="
echo "$BAM"
echo "$BAI"
echo "$QC_SUMMARY"
echo "$RUN_MANIFEST"
echo "$OUTDIR/${RUN_ID}.output_manifest.tsv"
