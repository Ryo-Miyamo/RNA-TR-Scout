#!/usr/bin/env bash
set -euo pipefail

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
  source "$HOME/miniconda3/etc/profile.d/conda.sh"
fi
conda activate rnatr-v03
source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"
P2="$PROJECT_ROOT/results/11_p2_periodic/$RUN_ID/p2_alternate_exact_simple_periodic_evidence.tsv.gz"
ALIGN="$PROJECT_ROOT/results/11_assignment/$RUN_ID/alignment_segments.tsv.gz"
FASTQ="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_candidates_v0.3.1/ENCFF260PGB.pilot_100k.rnatr_candidate_all.fastq.gz"

OUTDIR="$PROJECT_ROOT/results/11_extreme_nonexact/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_extreme_nonexact/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_extreme_nonexact/$RUN_ID"
DATADIR="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_extreme_nonexact"

AUDIT="$OUTDIR/p2_nonexact_tracts_ge1000bp.audit.tsv"
READS="$OUTDIR/p2_nonexact_tracts_ge1000bp.reads.tsv"
OUT_FASTQ="$DATADIR/p2_nonexact_tracts_ge1000bp.unique_reads.fastq.gz"
OUT_FASTA="$DATADIR/p2_nonexact_tracts_ge1000bp.tracts.fasta.gz"
QC="$QCDIR/p2_nonexact_tracts_ge1000bp.qc.tsv"
MANIFEST="$OUTDIR/${RUN_ID}.extreme_nonexact.manifest.tsv"
PY="$WORKDIR/audit_extreme_nonexact.py"

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR" "$DATADIR"

for f in "$P2" "$ALIGN" "$FASTQ"; do
  test -s "$f" || { echo "ERROR: missing $f" >&2; exit 1; }
done

cat > "$PY" <<'PY'
import csv, gzip, math, sys
from collections import Counter, defaultdict
import pysam

p2, align_path, fastq_path, audit_path, reads_path, fastq_out, fasta_out, qc_path = sys.argv[1:]

NONEXACT = {"LEFT_ONLY_INTERNAL","RIGHT_ONLY_INTERNAL","REPEAT_ONLY_UNANCHORED","UNRESOLVED"}
EXPECTED = 37
MIN_BP = 1000

def entropy(seq):
    if not seq: return 0.0
    c = Counter(seq); n = len(seq)
    return -sum((v/n)*math.log2(v/n) for v in c.values())

def kmer_fraction(seq, k=3):
    if len(seq) < k: return 0.0
    obs = {seq[i:i+k] for i in range(len(seq)-k+1)}
    return len(obs) / min(4**k, len(seq)-k+1)

def longest_hp(seq):
    if not seq: return 0, "."
    best = cur = 1; best_base = cur_base = seq[0]
    for b in seq[1:]:
        if b == cur_base:
            cur += 1
        else:
            if cur > best: best, best_base = cur, cur_base
            cur_base, cur = b, 1
    if cur > best: best, best_base = cur, cur_base
    return best, best_base

extreme = []
with gzip.open(p2, "rt", encoding="utf-8", newline="") as h:
    for row in csv.DictReader(h, delimiter="\t"):
        if row["evidence_class"] in NONEXACT and int(row["tract_read_bp"]) >= MIN_BP:
            extreme.append(row)

read_ids = {r["read_id"] for r in extreme}
aln = defaultdict(lambda: {"records":0,"primary":0,"secondary":0,"supplementary":0,"unmapped":0,"chroms":set(),"sa":0,"chim":0,"mapq":[]})

with gzip.open(align_path, "rt", encoding="utf-8", newline="") as h:
    for r in csv.DictReader(h, delimiter="\t"):
        rid = r["read_id"]
        if rid not in read_ids: continue
        a = aln[rid]
        a["records"] += 1
        a[r["alignment_class"]] += 1
        if r["chrom"] not in {"","."}: a["chroms"].add(r["chrom"])
        if r["sa_tag_present"] == "true": a["sa"] += 1
        if r["is_chimeric_candidate"] == "true": a["chim"] += 1
        if r["mapq"] not in {"",".","None"}: a["mapq"].append(int(r["mapq"]))

fq = {}
with pysam.FastxFile(fastq_path) as src:
    for e in src:
        if e.name in read_ids:
            fq[e.name] = (e.sequence.upper(), e.quality, e.comment or "")

cols = [
"projection_id","read_id","evidence_class","target_region_id","representative_locus_id",
"motif","read_length_bp","tract_read_start","tract_read_end","tract_read_bp",
"tract_fraction_of_read","touches_raw_start","touches_raw_end","purity","edit_fraction",
"best_mapq","assignment_rank","read_candidate_target_count","target_overlap_bp",
"entropy_bits","unique_3mer_fraction","fraction_A","fraction_C","fraction_G","fraction_T",
"dominant_base","dominant_base_fraction","longest_homopolymer_bp","longest_homopolymer_base",
"longest_homopolymer_fraction","left_100bp_entropy","right_100bp_entropy",
"alignment_records","primary_alignments","secondary_alignments","supplementary_alignments",
"unique_alignment_chromosomes","alignment_chromosomes","sa_tag_records",
"chimeric_candidate_records","max_alignment_mapq","review_class","review_flags"
]

out = []
counts = Counter()
missing = set()
invalid = 0

for r in extreme:
    rid = r["read_id"]
    if rid not in fq:
        missing.add(rid); continue
    seq, qual, comment = fq[rid]
    start, end = int(r["tract_read_start"]), int(r["tract_read_end"])
    if not (0 <= start < end <= len(seq)):
        invalid += 1; continue
    tract = seq[start:end]
    left = seq[max(0,start-100):start]
    right = seq[end:min(len(seq),end+100)]
    bc = Counter(tract)
    fr = {b: bc.get(b,0)/len(tract) for b in "ACGTN"}
    dom = max(fr, key=fr.get)
    hp, hpbase = longest_hp(tract)
    ent = entropy(tract)
    k3 = kmer_fraction(tract)
    tf = len(tract)/len(seq)
    a = aln[rid]
    flags = []
    if start <= 10: flags.append("TRACT_TOUCHES_RAW_START")
    if len(seq)-end <= 10: flags.append("TRACT_TOUCHES_RAW_END")
    if tf >= 0.80: flags.append("TRACT_DOMINATES_READ")
    if fr[dom] >= 0.80: flags.append("MONONUCLEOTIDE_DOMINATED")
    if ent < 1.0: flags.append("VERY_LOW_BASE_ENTROPY")
    if k3 < 0.25: flags.append("LOW_3MER_COMPLEXITY")
    if hp/len(tract) >= 0.50: flags.append("HOMOPOLYMER_DOMINATED")
    if float(r["purity"]) >= 0.80: flags.append("HIGH_CATALOG_MOTIF_PURITY")
    if len(a["chroms"]) > 1: flags.append("MULTI_CHROMOSOME_ALIGNMENT")
    if a["supplementary"] > 0: flags.append("SUPPLEMENTARY_ALIGNMENT_PRESENT")
    if a["chim"] > 0: flags.append("CHIMERIC_ALIGNMENT_CANDIDATE")
    if int(r["target_overlap_bp"]) == 0: flags.append("NO_TARGET_OVERLAP")

    if dom in {"A","T"} and fr[dom] >= 0.80:
        review = "POLY_A_T_OR_HOMOPOLYMER_REVIEW"
    elif len(a["chroms"]) > 1 or a["chim"] > 0:
        review = "CHIMERIC_OR_MULTI_SEGMENT_REVIEW"
    elif ent < 1.0 or k3 < 0.25 or tf >= 0.80:
        review = "LOW_COMPLEXITY_LONG_TRACT_REVIEW"
    elif float(r["purity"]) >= 0.80 and int(r["target_overlap_bp"]) > 0:
        review = "HIGH_PURITY_LONG_PERIODIC_TRACT_REVIEW"
    else:
        review = "COMPOUND_OR_UNRESOLVED_SEQUENCE_REVIEW"

    counts[f"review_class::{review}"] += 1
    counts[f"evidence_class::{r['evidence_class']}"] += 1
    for f in set(flags): counts[f"flag::{f}"] += 1

    out.append({
        "projection_id":r["projection_id"],"read_id":rid,"evidence_class":r["evidence_class"],
        "target_region_id":r["target_region_id"],"representative_locus_id":r["representative_locus_id"],
        "motif":r["canonical_motif"],"read_length_bp":len(seq),"tract_read_start":start,
        "tract_read_end":end,"tract_read_bp":len(tract),"tract_fraction_of_read":f"{tf:.6f}",
        "touches_raw_start":str(start<=10).lower(),"touches_raw_end":str(len(seq)-end<=10).lower(),
        "purity":r["purity"],"edit_fraction":r["edit_fraction"],"best_mapq":r["best_mapq"],
        "assignment_rank":r["assignment_rank"],"read_candidate_target_count":r["read_candidate_target_count"],
        "target_overlap_bp":r["target_overlap_bp"],"entropy_bits":f"{ent:.6f}",
        "unique_3mer_fraction":f"{k3:.6f}","fraction_A":f"{fr['A']:.6f}",
        "fraction_C":f"{fr['C']:.6f}","fraction_G":f"{fr['G']:.6f}",
        "fraction_T":f"{fr['T']:.6f}","dominant_base":dom,
        "dominant_base_fraction":f"{fr[dom]:.6f}","longest_homopolymer_bp":hp,
        "longest_homopolymer_base":hpbase,"longest_homopolymer_fraction":f"{hp/len(tract):.6f}",
        "left_100bp_entropy":f"{entropy(left):.6f}","right_100bp_entropy":f"{entropy(right):.6f}",
        "alignment_records":a["records"],"primary_alignments":a["primary"],
        "secondary_alignments":a["secondary"],"supplementary_alignments":a["supplementary"],
        "unique_alignment_chromosomes":len(a["chroms"]),
        "alignment_chromosomes":";".join(sorted(a["chroms"])) if a["chroms"] else ".",
        "sa_tag_records":a["sa"],"chimeric_candidate_records":a["chim"],
        "max_alignment_mapq":max(a["mapq"],default=0),"review_class":review,
        "review_flags":";".join(sorted(set(flags))) if flags else "."
    })

out.sort(key=lambda x:(int(x["tract_read_bp"]),float(x["purity"])), reverse=True)
with open(audit_path,"w",encoding="utf-8",newline="") as h:
    w=csv.DictWriter(h,fieldnames=cols,delimiter="\t",lineterminator="\n")
    w.writeheader(); w.writerows(out)

perread=defaultdict(list)
for r in out: perread[r["read_id"]].append(r)
rcols=["read_id","extreme_rows","max_tract_bp","review_classes","evidence_classes","targets","motifs"]
rout=[]
for rid, rs in sorted(perread.items()):
    rout.append({
        "read_id":rid,"extreme_rows":len(rs),
        "max_tract_bp":max(int(x["tract_read_bp"]) for x in rs),
        "review_classes":";".join(sorted({x["review_class"] for x in rs})),
        "evidence_classes":";".join(sorted({x["evidence_class"] for x in rs})),
        "targets":";".join(sorted({x["target_region_id"] for x in rs})),
        "motifs":";".join(sorted({x["motif"] for x in rs}))
    })
with open(reads_path,"w",encoding="utf-8",newline="") as h:
    w=csv.DictWriter(h,fieldnames=rcols,delimiter="\t",lineterminator="\n")
    w.writeheader(); w.writerows(rout)

with gzip.open(fastq_out,"wt",encoding="utf-8") as h:
    for rid in sorted(fq):
        seq, qual, comment = fq[rid]
        header=f"@{rid}" + (f" {comment}" if comment else "")
        h.write(f"{header}\n{seq}\n+\n{qual}\n")

with gzip.open(fasta_out,"wt",encoding="utf-8") as h:
    for r in out:
        seq=fq[r["read_id"]][0][int(r["tract_read_start"]):int(r["tract_read_end"])]
        h.write(f">{r['projection_id']} read={r['read_id']} class={r['evidence_class']} target={r['target_region_id']} motif={r['motif']}\n{seq}\n")

status="PASS"
if len(extreme)!=EXPECTED or len(out)!=EXPECTED or missing or invalid:
    status="REVIEW"

lengths=[int(r["tract_read_bp"]) for r in out]
with open(qc_path,"w",encoding="utf-8") as h:
    h.write("metric\tvalue\n")
    h.write(f"expected_extreme_rows\t{EXPECTED}\n")
    h.write(f"observed_extreme_rows\t{len(extreme)}\n")
    h.write(f"audit_rows_written\t{len(out)}\n")
    h.write(f"unique_reads\t{len(read_ids)}\n")
    h.write(f"fastq_reads_found\t{len(fq)}\n")
    h.write(f"missing_fastq_reads\t{len(missing)}\n")
    h.write(f"invalid_tract_coordinates\t{invalid}\n")
    if lengths:
        s=sorted(lengths)
        h.write(f"tract_bp_min\t{min(s)}\n")
        h.write(f"tract_bp_median\t{s[len(s)//2]}\n")
        h.write(f"tract_bp_max\t{max(s)}\n")
    for k,v in sorted(counts.items()): h.write(f"{k}\t{v}\n")
    h.write(f"audit_status\t{status}\n")

if status!="PASS":
    raise SystemExit("extreme non-exact audit requires review")
PY

echo "===== INPUT INTEGRITY ====="
gzip -t "$P2"
gzip -t "$ALIGN"
gzip -t "$FASTQ"

rm -f "$AUDIT" "$READS" "$OUT_FASTQ" "$OUT_FASTA" "$QC" "$MANIFEST"

python "$PY" "$P2" "$ALIGN" "$FASTQ" "$AUDIT" "$READS" "$OUT_FASTQ" "$OUT_FASTA" "$QC"

gzip -t "$OUT_FASTQ"
gzip -t "$OUT_FASTA"

echo
echo "===== QC ====="
column -ts $'\t' "$QC"

echo
echo "===== EXTREME ROWS ====="
column -ts $'\t' "$AUDIT"

{
  printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'
  for f in "$AUDIT" "$READS" "$QC"; do
    rows="$(awk 'END {print NR-1}' "$f")"
    printf '%s\t%s\t%s\t%s\t%s\n' "$(basename "$f")" "$rows" "$(stat -c '%s' "$f")" "$(sha256sum "$f"|awk '{print $1}')" "$f"
  done
  rows="$(gzip -cd "$OUT_FASTQ"|awk 'END {print NR/4}')"
  printf '%s\t%s\t%s\t%s\t%s\n' "$(basename "$OUT_FASTQ")" "$rows" "$(stat -c '%s' "$OUT_FASTQ")" "$(sha256sum "$OUT_FASTQ"|awk '{print $1}')" "$OUT_FASTQ"
  rows="$(gzip -cd "$OUT_FASTA"|grep -c '^>')"
  printf '%s\t%s\t%s\t%s\t%s\n' "$(basename "$OUT_FASTA")" "$rows" "$(stat -c '%s' "$OUT_FASTA")" "$(sha256sum "$OUT_FASTA"|awk '{print $1}')" "$OUT_FASTA"
} > "$MANIFEST"

echo
echo "===== MANIFEST ====="
column -ts $'\t' "$MANIFEST"
