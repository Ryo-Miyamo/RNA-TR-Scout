#!/usr/bin/env bash
set -euo pipefail

# RNA-TR-Scout Stage 15C
# Full ENCSR307SHM (ENCFF260PGB; 5,312,696 reads) splice-aware mapping.
#
# Scientific mapping contract:
#   EXACT parity with ENCSR307SHM_pilot100k_mm2splice_v1
#   minimap2 -ax splice -t 16 --junc-bed FROZEN_BED12
#            --secondary=yes -N 10 --MD --cs=long -R RG
#   samtools sort -@ 8 -m 1G
#
# Safety:
#   - full FASTQ on T9 is read-only
#   - no SSOT, active pipeline, caller, schema, or Stage15A/B result is modified
#   - final BAM/BAI are published only after mapping/index/QC/read-ID parity PASS
#   - pre-existing final BAM/BAI are never overwritten
#   - stale partial outputs cause a hard stop rather than silent deletion
#
# This stage creates the mapping-complete BAM required by the later
# empirical 5.31M BAM-to-final Core Technical Completion run.
# It DOES NOT start RNA-TR-Scout BAM-to-final processing.

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
    # shellcheck disable=SC1091
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
fi
conda activate rnatr-v03

PROJECT_ROOT="/mnt/intelssd/rnatr_project"
PATHS_ENV="$PROJECT_ROOT/config/paths.env"
[[ -s "$PATHS_ENV" ]] || { echo "ERROR: missing $PATHS_ENV" >&2; exit 1; }
# shellcheck disable=SC1090
source "$PATHS_ENV"
[[ "${PROJECT_ROOT:-}" == "/mnt/intelssd/rnatr_project" ]] || {
    echo "ERROR: PROJECT_ROOT mismatch after paths.env: ${PROJECT_ROOT:-UNSET}" >&2
    exit 1
}
cd "$PROJECT_ROOT"

STAGE_VERSION="rnatr_stage15c_full_mapping_v0.1.0"
SAMPLE_ID="ENCSR307SHM"
FASTQ_ACCESSION="ENCFF260PGB"
RUN_ID="ENCSR307SHM_full5312696_mm2splice_v1"
PARENT_RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"
PARAMETER_SET_ID="rnatr_mm2_splice_cDNA_v0.3.1"

FASTQ="/media/tokushimaneuro02/T9/rnatr_data/downloads/ENCSR307SHM/ENCFF260PGB.fastq.gz"
EXPECTED_FASTQ_BYTES=8995223210
EXPECTED_FASTQ_MD5="23270f6b994db147df2f2f4c53f8358b"
EXPECTED_READS=5312696

REFDIR="$PROJECT_ROOT/refs/gencode_v50"
REF_FASTA="$REFDIR/GRCh38.primary_assembly.genome.fa"
REF_MMI="$REFDIR/GRCh38.primary_assembly.genome.mmi"
REF_FAI="$REF_FASTA.fai"
JUNCTION_BED12="$REFDIR/junctions/gencode.v50.multi_exon_transcripts.bed12"
JUNCTION_SHA_FILE="$REFDIR/junctions/gencode.v50.multi_exon_transcripts.sha256"

ORIGINAL_COMMAND_FILE="$PROJECT_ROOT/results/11_mapping/$PARENT_RUN_ID/${PARENT_RUN_ID}.mapper_command.sh"
ORIGINAL_QC="$PROJECT_ROOT/qc/11_mapping/$PARENT_RUN_ID/${PARENT_RUN_ID}.mapping_qc.tsv"
EXPECTED_ORIGINAL_COMMAND_SHA256="de9ad6e4cfaea3c83158619ac39c3b73e88704cf880da51c1306378fbd956bb7"
EXPECTED_JUNCTION_SHA256="34b5a798c2f9bba3b42592e6d2c6599dc77597ff4e8e8f073c4d20fe012a6d5c"

OUTDIR="$PROJECT_ROOT/results/11_mapping/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_mapping/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_mapping/$RUN_ID"
SCRIPT_ARCHIVE="$PROJECT_ROOT/scripts/$(basename "${BASH_SOURCE[0]}")"

BAM="$OUTDIR/${RUN_ID}.sorted.bam"
BAI="${BAM}.bai"
MM2_LOG="$OUTDIR/${RUN_ID}.minimap2.log"
COMMAND_FILE="$OUTDIR/${RUN_ID}.mapper_command.sh"
RUN_MANIFEST="$OUTDIR/run_manifest.tsv"
PARAMETERS="$OUTDIR/${STAGE_VERSION}.parameters.tsv"
ARTIFACT_MANIFEST="$OUTDIR/${RUN_ID}.artifact_manifest.tsv"

FLAGSTAT="$QCDIR/${RUN_ID}.flagstat.txt"
STATS="$QCDIR/${RUN_ID}.samtools_stats.txt"
IDXSTATS="$QCDIR/${RUN_ID}.idxstats.tsv"
QC_SUMMARY="$QCDIR/${RUN_ID}.mapping_qc.tsv"
TIME_SUMMARY="$QCDIR/${RUN_ID}.runtime.tsv"
RESOURCE_TIME="$QCDIR/${RUN_ID}.pipeline.time_v.txt"
READ_ID_QC="$QCDIR/${RUN_ID}.read_id_parity.tsv"

THREADS_MM2=16
THREADS_SORT=8
SECONDARY_MAX=10
SORT_MEM="1G"
SORT_ID_MEM="512M"

# Preserve enough free Intel SSD for the later full BAM-to-final run.
# Stage15A/15B readiness required ~250.1 GB; 300 GB is a deliberate
# pre-mapping floor to preserve a practical margin after BAM creation.
MINIMUM_INTEL_FREE_BYTES=300000000000

for tool in \
    minimap2 samtools seqkit gzip md5sum sha256sum awk sed grep cut sort cmp \
    stat findmnt df python cp date column /usr/bin/time
do
    command -v "$tool" >/dev/null 2>&1 || {
        echo "ERROR: required tool unavailable: $tool" >&2
        exit 1
    }
done

for p in \
    "$FASTQ" "$REF_FASTA" "$REF_MMI" "$REF_FAI" \
    "$JUNCTION_BED12" "$JUNCTION_SHA_FILE" \
    "$ORIGINAL_COMMAND_FILE" "$ORIGINAL_QC"
do
    [[ -s "$p" ]] || { echo "ERROR: required input missing/empty: $p" >&2; exit 1; }
done

# Input mount is read-only-by-contract (the script never writes there).
T9_SOURCE="$(findmnt -n -o SOURCE --target "$FASTQ")"
T9_FSTYPE="$(findmnt -n -o FSTYPE --target "$FASTQ")"
[[ -n "$T9_SOURCE" && -n "$T9_FSTYPE" ]] || {
    echo "ERROR: could not resolve T9 mount for $FASTQ" >&2
    exit 1
}

INTEL_FREE_BYTES="$(df --output=avail -B1 "$PROJECT_ROOT" | awk 'NR==2 {print $1}')"
[[ "$INTEL_FREE_BYTES" =~ ^[0-9]+$ ]] || {
    echo "ERROR: could not determine Intel SSD free bytes" >&2
    exit 1
}
(( INTEL_FREE_BYTES >= MINIMUM_INTEL_FREE_BYTES )) || {
    echo "ERROR: Intel SSD free space below 300 GB pre-mapping safety floor" >&2
    echo "observed=$INTEL_FREE_BYTES required=$MINIMUM_INTEL_FREE_BYTES" >&2
    exit 1
}

OBS_ORIG_CMD_SHA="$(sha256sum "$ORIGINAL_COMMAND_FILE" | awk '{print $1}')"
[[ "$OBS_ORIG_CMD_SHA" == "$EXPECTED_ORIGINAL_COMMAND_SHA256" ]] || {
    echo "ERROR: frozen original mapper command SHA-256 mismatch" >&2
    echo "expected=$EXPECTED_ORIGINAL_COMMAND_SHA256" >&2
    echo "observed=$OBS_ORIG_CMD_SHA" >&2
    exit 1
}

OBS_JUNCTION_SHA="$(sha256sum "$JUNCTION_BED12" | awk '{print $1}')"
FILE_JUNCTION_SHA="$(awk 'NR==1 {print $1}' "$JUNCTION_SHA_FILE")"
[[ "$OBS_JUNCTION_SHA" == "$EXPECTED_JUNCTION_SHA256" ]] || {
    echo "ERROR: frozen junction BED12 SHA-256 mismatch" >&2
    exit 1
}
[[ "$FILE_JUNCTION_SHA" == "$EXPECTED_JUNCTION_SHA256" ]] || {
    echo "ERROR: junction SHA sidecar disagrees with frozen SHA" >&2
    exit 1
}

for token in \
    "minimap2" \
    "-ax splice" \
    "-t 16" \
    "--junc-bed $JUNCTION_BED12" \
    "--secondary=yes" \
    "-N 10" \
    "--MD" \
    "--cs=long" \
    "$REF_MMI"
do
    grep -Fq -- "$token" "$ORIGINAL_COMMAND_FILE" || {
        echo "ERROR: frozen pilot command lacks required token: $token" >&2
        exit 1
    }
done

FASTQ_BYTES="$(stat -c '%s' "$FASTQ")"
[[ "$FASTQ_BYTES" == "$EXPECTED_FASTQ_BYTES" ]] || {
    echo "ERROR: FASTQ byte size mismatch expected=$EXPECTED_FASTQ_BYTES observed=$FASTQ_BYTES" >&2
    exit 1
}
gzip -t "$FASTQ"

echo "Computing full FASTQ MD5 and read count..."
FASTQ_MD5="$(md5sum "$FASTQ" | awk '{print $1}')"
[[ "$FASTQ_MD5" == "$EXPECTED_FASTQ_MD5" ]] || {
    echo "ERROR: FASTQ MD5 mismatch expected=$EXPECTED_FASTQ_MD5 observed=$FASTQ_MD5" >&2
    exit 1
}

FASTQ_READS="$(
    seqkit stats -T "$FASTQ" |
    awk -F '\t' '
        NR==1 {
            for (i=1;i<=NF;i++) if ($i=="num_seqs") c=i
            next
        }
        NR==2 {
            if (!c) exit 2
            print $c
        }
    '
)"
[[ "$FASTQ_READS" == "$EXPECTED_READS" ]] || {
    echo "ERROR: FASTQ read count mismatch expected=$EXPECTED_READS observed=$FASTQ_READS" >&2
    exit 1
}

# Reference hashes are recorded for this full-scale mapping provenance.
# They are not substituted for the frozen path/command/junction guards.
echo "Computing reference/input provenance SHA-256 values..."
FASTQ_SHA256="$(sha256sum "$FASTQ" | awk '{print $1}')"
REF_FASTA_SHA256="$(sha256sum "$REF_FASTA" | awk '{print $1}')"
REF_MMI_SHA256="$(sha256sum "$REF_MMI" | awk '{print $1}')"
REF_FAI_SHA256="$(sha256sum "$REF_FAI" | awk '{print $1}')"

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR"

# Archive the exact executable used, without modifying any active-path pointer.
if [[ ! -e "$SCRIPT_ARCHIVE" ]]; then
    cp "${BASH_SOURCE[0]}" "$SCRIPT_ARCHIVE"
elif ! cmp -s "${BASH_SOURCE[0]}" "$SCRIPT_ARCHIVE"; then
    echo "ERROR: project script archive already exists with different bytes: $SCRIPT_ARCHIVE" >&2
    exit 1
fi

cat > "$PARAMETERS" <<EOF
parameter	value	meaning
stage_version	$STAGE_VERSION	Full ENCSR307SHM mapping stage
run_id	$RUN_ID	Formal full mapping run ID
parent_run_id	$PARENT_RUN_ID	Frozen 100k pilot mapping contract
sample_id	$SAMPLE_ID	ENCODE experiment
fastq_accession	$FASTQ_ACCESSION	ENCODE full FASTQ accession
expected_reads	$EXPECTED_READS	Full FASTQ read count
parameter_set_id	$PARAMETER_SET_ID	Frozen ONT cDNA mapping parameter set
aligner	minimap2	Genome-wide splice-aware mapper
minimap2_parameters	-ax splice -t 16 --junc-bed FROZEN_BED12 --secondary=yes -N 10 --MD --cs=long -R RG	Exact pilot settings
samtools_sort_parameters	-@ 8 -m 1G	Frozen pilot sort settings
reference_index	$REF_MMI	Frozen GENCODE v50 GRCh38 minimap2 index
junction_bed12	$JUNCTION_BED12	Frozen GENCODE v50 multi-exon transcript BED12
source_fastq	$FASTQ	Read-only T9 input
bam_output	$BAM	Intel SSD final sorted BAM
source_fastq_move_or_delete	NOT_USED	Input remains on T9
active_pipeline_promotion	NOT_RUN	Mapping artifact only
ssot_update	NOT_RUN	No SSOT mutation
bam_to_final	NOT_RUN	Full RNA-TR-Scout analysis starts only after mapping QC
EOF

# Build a streaming BAM QC helper; no all-read in-memory set is used.
BAM_QC_PY="$WORKDIR/summarize_full_bam_streaming.py"
cat > "$BAM_QC_PY" <<'PY'
from __future__ import annotations
import collections
import sys
import pysam

bam_path, out_path, expected_text = sys.argv[1:]
expected = int(expected_text)

counts = collections.Counter()
mapq_hist = collections.Counter()

with pysam.AlignmentFile(bam_path, "rb") as bam:
    for r in bam.fetch(until_eof=True):
        counts["alignment_records"] += 1
        if r.is_secondary:
            counts["secondary_records"] += 1
            continue
        if r.is_supplementary:
            counts["supplementary_records"] += 1
            continue

        counts["primary_records"] += 1
        if r.is_unmapped:
            counts["primary_unmapped_reads"] += 1
            continue

        counts["primary_mapped_reads"] += 1
        mapq_hist[int(r.mapping_quality)] += 1
        cig = r.cigartuples or []
        if any(op == 3 for op, _ in cig):
            counts["spliced_primary_reads"] += 1
        if any(op == 4 for op, _ in cig):
            counts["softclipped_primary_reads"] += 1
        if any(op == 1 for op, _ in cig):
            counts["insertion_primary_reads"] += 1
        if r.has_tag("SA"):
            counts["sa_tag_primary_reads"] += 1

def median_from_hist(hist):
    n = sum(hist.values())
    if n == 0:
        return 0
    left = (n - 1) // 2
    right = n // 2
    seen = 0
    lv = rv = None
    for val in sorted(hist):
        nxt = seen + hist[val]
        if lv is None and left < nxt:
            lv = val
        if right < nxt:
            rv = val
            break
        seen = nxt
    return (lv + rv) / 2 if lv != rv else lv

failures = []
if counts["primary_records"] != expected:
    failures.append("PRIMARY_RECORD_COUNT_MISMATCH")
if counts["primary_mapped_reads"] + counts["primary_unmapped_reads"] != expected:
    failures.append("PRIMARY_PARTITION_MISMATCH")

mapped = counts["primary_mapped_reads"]
metrics = {
    **counts,
    "expected_input_reads": expected,
    "primary_mapping_rate_percent": (100.0 * mapped / expected) if expected else 0.0,
    "primary_mapq_median": median_from_hist(mapq_hist),
    "primary_mapq60_reads": mapq_hist.get(60, 0),
    "audit_failure_codes": ";".join(failures) if failures else ".",
    "audit_status": "FAIL" if failures else "PASS",
}

with open(out_path, "w", encoding="utf-8") as out:
    out.write("metric\tvalue\n")
    for k, v in metrics.items():
        if isinstance(v, float):
            out.write(f"{k}\t{v:.6f}\n")
        else:
            out.write(f"{k}\t{v}\n")

if failures:
    raise SystemExit("BAM QC failed: " + ",".join(failures))
PY
python -m py_compile "$BAM_QC_PY"

printf -v RG \
    '@RG\\tID:%s\\tSM:%s\\tPL:ONT\\tLB:ONT_cDNA' \
    "$RUN_ID" "$SAMPLE_ID"
[[ "$RG" != *$'\t'* ]] || { echo "ERROR: RG contains literal tab" >&2; exit 1; }

{
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
        "$FASTQ"
    printf '%s ' '|'
    printf '%q ' \
        samtools sort \
        -@ "$THREADS_SORT" \
        -m "$SORT_MEM" \
        -T "$WORKDIR/sorttmp" \
        -o "$BAM" \
        -
    echo
} > "$COMMAND_FILE"

cat > "$RUN_MANIFEST" <<EOF
field	value
stage_version	$STAGE_VERSION
run_id	$RUN_ID
sample_id	$SAMPLE_ID
fastq_accession	$FASTQ_ACCESSION
input_fastq	$FASTQ
input_fastq_bytes	$FASTQ_BYTES
input_fastq_reads	$FASTQ_READS
input_fastq_md5	$FASTQ_MD5
input_fastq_sha256	$FASTQ_SHA256
reference_build	GRCh38
reference_release	GENCODE_v50_primary_assembly
reference_fasta	$REF_FASTA
reference_fasta_sha256	$REF_FASTA_SHA256
reference_mmi	$REF_MMI
reference_mmi_sha256	$REF_MMI_SHA256
reference_fai	$REF_FAI
reference_fai_sha256	$REF_FAI_SHA256
junction_bed12	$JUNCTION_BED12
junction_bed12_sha256	$OBS_JUNCTION_SHA
frozen_pilot_command	$ORIGINAL_COMMAND_FILE
frozen_pilot_command_sha256	$OBS_ORIG_CMD_SHA
minimap2_version	$(minimap2 --version 2>&1 | head -n1)
samtools_version	$(samtools --version | head -n1)
threads_minimap2	$THREADS_MM2
threads_samtools_sort	$THREADS_SORT
sort_memory_per_thread	$SORT_MEM
t9_mount_source	$T9_SOURCE
t9_filesystem	$T9_FSTYPE
intel_free_bytes_before_mapping	$INTEL_FREE_BYTES
source_data_moved_or_deleted	false
active_pipeline_modified	false
ssot_modified	false
full_bam_to_final_started	false
EOF

echo "===== RNA-TR-SCOUT STAGE 15C FULL MAPPING PREFLIGHT ====="
echo "run ID:                  $RUN_ID"
echo "input FASTQ:             $FASTQ"
echo "input reads:             $FASTQ_READS"
echo "input bytes:             $FASTQ_BYTES"
echo "FASTQ MD5:               $FASTQ_MD5"
echo "mapping parameter parity: EXACT with $PARENT_RUN_ID"
echo "minimap2:                -ax splice -t 16 --junc-bed ... --secondary=yes -N 10 --MD --cs=long"
echo "samtools sort:           -@ 8 -m 1G"
echo "reference index:         $REF_MMI"
echo "junction SHA-256:        $OBS_JUNCTION_SHA"
echo "Intel SSD free bytes:    $INTEL_FREE_BYTES"
echo "full BAM-to-final:       NOT STARTED"

if [[ -e "$BAM" || -e "$BAI" ]]; then
    if [[ -s "$BAM" && -s "$BAI" ]]; then
        echo "FINAL_BAM_EXISTS: validating existing final BAM; no remapping"
    else
        echo "ERROR: incomplete final BAM/BAI exists; refusing overwrite" >&2
        echo "BAM=$BAM" >&2
        echo "BAI=$BAI" >&2
        exit 1
    fi
else
    shopt -s nullglob
    stale_parts=("$OUTDIR"/."$RUN_ID".*.part.* "$OUTDIR"/."$RUN_ID".*.part.bam*)
    shopt -u nullglob
    if ((${#stale_parts[@]} > 0)); then
        echo "ERROR: stale partial mapping outputs exist; refusing silent deletion" >&2
        printf '  %s\n' "${stale_parts[@]}" >&2
        exit 1
    fi

    nonce="$$.$RANDOM"
    BAM_PART="$OUTDIR/.${RUN_ID}.${nonce}.part.bam"
    BAI_PART="$OUTDIR/.${RUN_ID}.${nonce}.part.bam.bai"
    LOG_PART="$OUTDIR/.${RUN_ID}.${nonce}.part.minimap2.log"
    TIMEV_PART="$QCDIR/.${RUN_ID}.${nonce}.part.pipeline.time_v.txt"

    START_ISO="$(date -Is)"
    START_EPOCH="$(date +%s)"

    echo
    echo "MAP_START	$(date -Is)	$RUN_ID"
    echo "NOTE: mapping is timed separately from the BAM-to-final <=60 min gate."

    # /usr/bin/time measures the whole minimap2|samtools-sort pipeline.
    export THREADS_MM2 THREADS_SORT SECONDARY_MAX SORT_MEM
    export JUNCTION_BED12 REF_MMI FASTQ RG BAM_PART WORKDIR LOG_PART
    /usr/bin/time -v -o "$TIMEV_PART" \
        bash -o pipefail -c '
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
                2> >(tee "$LOG_PART" >&2) |
            samtools sort \
                -@ "$THREADS_SORT" \
                -m "$SORT_MEM" \
                -T "$WORKDIR/sorttmp" \
                -o "$BAM_PART" \
                -
        '

    END_EPOCH="$(date +%s)"
    END_ISO="$(date -Is)"
    WALL_SECONDS="$((END_EPOCH - START_EPOCH))"

    samtools quickcheck -v "$BAM_PART"
    samtools index -@ "$THREADS_SORT" "$BAM_PART" "$BAI_PART"
    [[ -s "$BAI_PART" ]] || { echo "ERROR: BAM index not created" >&2; exit 1; }

    # Publish BAM/BAI only after mapping and index integrity PASS.
    mv "$BAM_PART" "$BAM"
    mv "$BAI_PART" "$BAI"
    mv "$LOG_PART" "$MM2_LOG"
    mv "$TIMEV_PART" "$RESOURCE_TIME"

    cat > "$TIME_SUMMARY" <<EOF
metric	value
start_time	$START_ISO
end_time	$END_ISO
wall_seconds	$WALL_SECONDS
wall_minutes	$(awk -v s="$WALL_SECONDS" 'BEGIN{printf "%.6f", s/60}')
threads_minimap2	$THREADS_MM2
threads_samtools_sort	$THREADS_SORT
sort_memory_per_thread	$SORT_MEM
performance_reporting_scope	FASTQ_TO_SORTED_BAM_MAPPING_ONLY
included_in_60min_bam_to_final_gate	false
EOF

    echo "MAP_PASS	$(date -Is)	$RUN_ID"
fi

samtools quickcheck -v "$BAM"
[[ -s "$BAI" ]] || { echo "ERROR: final BAI missing" >&2; exit 1; }

echo "Running streaming BAM QC..."
python "$BAM_QC_PY" "$BAM" "$QC_SUMMARY" "$EXPECTED_READS"
[[ "$(awk -F '\t' '$1=="audit_status"{print $2}' "$QC_SUMMARY")" == "PASS" ]] || {
    echo "ERROR: full BAM QC is not PASS" >&2
    exit 1
}

samtools flagstat -@ "$THREADS_SORT" "$BAM" > "$FLAGSTAT"
samtools stats -@ "$THREADS_SORT" "$BAM" > "$STATS"
samtools idxstats "$BAM" > "$IDXSTATS"

# Exact read-ID universe parity with fixed-memory external sorting.
IDROOT="$WORKDIR/read_id_parity"
mkdir -p "$IDROOT/fastq_sort_tmp" "$IDROOT/bam_sort_tmp"

echo "Checking exact FASTQ <-> primary BAM read-ID parity (external sort)..."
seqkit seq -n -i "$FASTQ" |
    LC_ALL=C sort -S "$SORT_ID_MEM" -T "$IDROOT/fastq_sort_tmp" \
    > "$IDROOT/fastq.ids.sorted.txt"

samtools view -F 2304 "$BAM" |
    cut -f1 |
    LC_ALL=C sort -S "$SORT_ID_MEM" -T "$IDROOT/bam_sort_tmp" \
    > "$IDROOT/bam_primary.ids.sorted.txt"

FASTQ_ID_ROWS="$(wc -l < "$IDROOT/fastq.ids.sorted.txt")"
BAM_ID_ROWS="$(wc -l < "$IDROOT/bam_primary.ids.sorted.txt")"

if cmp -s "$IDROOT/fastq.ids.sorted.txt" "$IDROOT/bam_primary.ids.sorted.txt"; then
    ID_PARITY="PASS"
else
    ID_PARITY="FAIL"
fi

cat > "$READ_ID_QC" <<EOF
metric	value
fastq_id_rows	$FASTQ_ID_ROWS
bam_primary_id_rows	$BAM_ID_ROWS
expected_reads	$EXPECTED_READS
sorted_multiset_exact_parity	$ID_PARITY
sort_memory	$SORT_ID_MEM
comparison_scope	full_FASTQ_vs_nonsecondary_nonsupplementary_BAM_records
EOF

[[ "$FASTQ_ID_ROWS" == "$EXPECTED_READS" ]] || {
    echo "ERROR: FASTQ ID row count mismatch" >&2; exit 1;
}
[[ "$BAM_ID_ROWS" == "$EXPECTED_READS" ]] || {
    echo "ERROR: BAM primary ID row count mismatch" >&2; exit 1;
}
[[ "$ID_PARITY" == "PASS" ]] || {
    echo "ERROR: FASTQ/BAM primary read-ID multiset parity failed" >&2; exit 1;
}

# ID lists are validation work products, not release artifacts.
rm -f "$IDROOT/fastq.ids.sorted.txt" "$IDROOT/bam_primary.ids.sorted.txt"
rmdir "$IDROOT/fastq_sort_tmp" "$IDROOT/bam_sort_tmp" 2>/dev/null || true
rmdir "$IDROOT" 2>/dev/null || true

BAM_BYTES="$(stat -c '%s' "$BAM")"
BAI_BYTES="$(stat -c '%s' "$BAI")"
BAM_SHA256="$(sha256sum "$BAM" | awk '{print $1}')"
BAI_SHA256="$(sha256sum "$BAI" | awk '{print $1}')"
INTEL_FREE_AFTER="$(df --output=avail -B1 "$PROJECT_ROOT" | awk 'NR==2 {print $1}')"

cat >> "$RUN_MANIFEST" <<EOF
output_bam	$BAM
output_bam_bytes	$BAM_BYTES
output_bam_sha256	$BAM_SHA256
output_bai	$BAI
output_bai_bytes	$BAI_BYTES
output_bai_sha256	$BAI_SHA256
intel_free_bytes_after_mapping	$INTEL_FREE_AFTER
mapping_qc	$QC_SUMMARY
read_id_parity_qc	$READ_ID_QC
mapping_status	PASS
EOF

# Artifact manifest excludes itself.
{
    printf 'artifact\tbytes\tsha256\tpath\n'
    while IFS= read -r p; do
        printf '%s\t%s\t%s\t%s\n' \
            "$(basename "$p")" \
            "$(stat -c '%s' "$p")" \
            "$(sha256sum "$p" | awk '{print $1}')" \
            "$p"
    done < <(
        find "$OUTDIR" "$QCDIR" \
            -type f \
            ! -name '*.part.*' \
            ! -path "$ARTIFACT_MANIFEST" \
            -print |
        LC_ALL=C sort
    )
} > "$ARTIFACT_MANIFEST"

echo
echo "===== STAGE 15C FULL MAPPING FINAL ====="
column -ts $'\t' "$QC_SUMMARY"
echo
column -ts $'\t' "$READ_ID_QC"
echo
echo "BAM:                    $BAM"
echo "BAI:                    $BAI"
echo "BAM bytes:              $BAM_BYTES"
echo "BAM SHA-256:            $BAM_SHA256"
echo "Intel free after bytes: $INTEL_FREE_AFTER"
if [[ -s "$TIME_SUMMARY" ]]; then
    echo
    column -ts $'\t' "$TIME_SUMMARY"
fi
echo
echo "MAPPING_STATUS	PASS"
echo "FULL_BAM_TO_FINAL_STARTED	false"
echo "ACTIVE_PIPELINE_MODIFIED	false"
echo "SSOT_MODIFIED	false"
echo "NEXT_GATE	STAGE15C_FULL_BAM_BINDING_AND_PROVISIONAL_BAM_TO_FINAL_RUNNER"
echo "QC	$QC_SUMMARY"
echo "MANIFEST	$ARTIFACT_MANIFEST"
