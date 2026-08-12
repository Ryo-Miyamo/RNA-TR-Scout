#!/usr/bin/env bash
set -euo pipefail

STAGE_VERSION="rnatr_aou_stat_semantics_rna_length_comparison_v0.1.1"
RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"
EXPECTED_PACKAGE_VERSION="0.3.2"
EXPECTED_QUERY_LOCI="11042"
EXPECTED_AOU_PRIMARY="8556"
SOURCE_CACHE_VERSION="rnatr_bulk_longread_population_reference_acquisition_v0.1.0"

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
  # shellcheck disable=SC1091
  source "$HOME/miniconda3/etc/profile.d/conda.sh"
fi
conda activate rnatr-v03
# shellcheck disable=SC1091
source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

for tool in python gzip sha256sum readlink flock column; do
  command -v "$tool" >/dev/null 2>&1 || { echo "ERROR: missing tool: $tool" >&2; exit 1; }
done

[[ "$(rnatr-scout version)" == "$EXPECTED_PACKAGE_VERSION" ]] || {
  echo "ERROR: rnatr-scout version mismatch" >&2
  exit 1
}

STAGE6AA_RESULT="$(readlink -f "$PROJECT_ROOT/results/11_bulk_longread_reference_crosswalk_coverage/$RUN_ID/latest")"
STAGE6AA_QC_ROOT="$(readlink -f "$PROJECT_ROOT/qc/11_bulk_longread_reference_crosswalk_coverage/$RUN_ID/latest")"
STAGE6AA_QC="$STAGE6AA_QC_ROOT/bulk_longread_reference_crosswalk_coverage.qc.tsv"
CROSSWALK="$STAGE6AA_RESULT/tables/p01_locus.bulk_longread_reference_crosswalk.tsv.gz"
SOURCE_ROOT="$PROJECT_ROOT/external_reference/rnatr_population_reference/bulk_sources/$SOURCE_CACHE_VERSION"
AOU_FILES="$SOURCE_ROOT/aou_longread_tr/zenodo_record_19895393/files"
ALLELE="$AOU_FILES/ValidationCohort_alleleLengthStats.TR_Explorer_1.0.1.txt.gz"
LPS_LOCUS="$AOU_FILES/ValidationCohort_lpsPerLocusStats.TR_Explorer_1.0.1.txt.gz"
LPS_MOTIF="$AOU_FILES/ValidationCohort_lpsPerMotifStats.TR_Explorer_1.0.1.txt.gz"

for p in "$STAGE6AA_QC" "$CROSSWALK" "$ALLELE" "$LPS_LOCUS" "$LPS_MOTIF"; do
  [[ -s "$p" ]] || { echo "ERROR: missing prerequisite: $p" >&2; exit 1; }
done
for p in "$CROSSWALK" "$ALLELE" "$LPS_LOCUS" "$LPS_MOTIF"; do gzip -t "$p"; done

metric() { awk -F $'\t' -v k="$2" '$1==k{print $2; found=1; exit} END{if(!found) print "."}' "$1"; }
[[ "$(metric "$STAGE6AA_QC" stage6aa_bulk_longread_reference_crosswalk_coverage_status)" == "PASS_READY_FOR_POPULATION_STAT_SEMANTICS_AND_RNA_LENGTH_COMPARISON" ]] || {
  echo "ERROR: Stage 6AA checkpoint not ready" >&2; exit 1;
}
[[ "$(metric "$STAGE6AA_QC" all_p01_loci_denominator)" == "$EXPECTED_QUERY_LOCI" ]] || exit 1
[[ "$(metric "$STAGE6AA_QC" aou_validation_allele_addressable_loci)" == "$EXPECTED_AOU_PRIMARY" ]] || exit 1

script_sha="$(sha256sum "$0" | awk '{print $1}')"
crosswalk_sha="$(sha256sum "$CROSSWALK" | awk '{print $1}')"
allele_sha="$(sha256sum "$ALLELE" | awk '{print $1}')"
lps_locus_sha="$(sha256sum "$LPS_LOCUS" | awk '{print $1}')"
lps_motif_sha="$(sha256sum "$LPS_MOTIF" | awk '{print $1}')"
snapshot_sig="$(printf '%s\n%s\n%s\n%s\n' "$crosswalk_sha" "$allele_sha" "$lps_locus_sha" "$lps_motif_sha" | sha256sum | awk '{print $1}')"
SNAPSHOT_ID="sha256_${snapshot_sig}"

OUT_BASE="$PROJECT_ROOT/results/11_aou_stat_semantics_rna_length_comparison/$RUN_ID/$STAGE_VERSION"
QC_BASE="$PROJECT_ROOT/qc/11_aou_stat_semantics_rna_length_comparison/$RUN_ID/$STAGE_VERSION"
TMP_BASE="$PROJECT_ROOT/tmp/11_aou_stat_semantics_rna_length_comparison/$RUN_ID/$STAGE_VERSION"
OUT_ROOT="$OUT_BASE/$SNAPSHOT_ID"
QC_ROOT="$QC_BASE/$SNAPSHOT_ID"
FINAL_QC="$QC_ROOT/aou_stat_semantics_rna_length_comparison.qc.tsv"
MANIFEST="$OUT_ROOT/aou_stat_semantics_rna_length_comparison.artifact_manifest.tsv"
LATEST_RESULT="$PROJECT_ROOT/results/11_aou_stat_semantics_rna_length_comparison/$RUN_ID/latest"
LATEST_QC="$PROJECT_ROOT/qc/11_aou_stat_semantics_rna_length_comparison/$RUN_ID/latest"
SCRIPT_DEST="$PROJECT_ROOT/scripts/$(basename "$0")"
mkdir -p "$OUT_BASE" "$QC_BASE" "$TMP_BASE" "$PROJECT_ROOT/scripts"

if [[ -s "$FINAL_QC" && -s "$MANIFEST" ]]; then
  echo "===== EXISTING STAGE 6AB CHECKPOINT ====="
  column -ts $'\t' "$FINAL_QC"
  exit 0
fi
[[ ! -e "$OUT_ROOT" && ! -e "$QC_ROOT" ]] || { echo "ERROR: partial immutable checkpoint exists" >&2; exit 1; }

exec 9>"$TMP_BASE/.stage.lock"
flock -n 9 || { echo "ERROR: Stage 6AB lock held" >&2; exit 1; }
WORK="$(mktemp -d "$TMP_BASE/work.XXXXXXXX")"
trap 'rm -rf "$WORK"' EXIT
STAGE_OUT="$WORK/stage_out"
STAGE_QC="$WORK/stage_qc"
mkdir -p "$STAGE_OUT"/{tables,summary,schema,provenance,contracts} "$STAGE_QC"

PY_IMPL="$STAGE_OUT/provenance/rnatr_aou_stat_semantics_rna_length_comparison_v0.1.1.py"
cat > "$PY_IMPL" <<'PY'
from __future__ import annotations
import argparse, csv, gzip, math, os, re, statistics, tempfile, sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Mapping

VERSION = "rnatr_aou_stat_semantics_rna_length_comparison_v0.1.1"
csv.field_size_limit(sys.maxsize)
COORD_RE = re.compile(r"(?P<chrom>(?:chr)?(?:[0-9]+|X|Y|M|MT))[:_-](?P<start>[0-9]+)[-_](?P<end>[0-9]+)", re.I)
IUPAC_COMP = str.maketrans("ACGTRYSWKMBDHVN", "TGCAYRSWMKVHDBN")
PCTS = ["0thPercentile","1stPercentile","5thPercentile","10thPercentile","25thPercentile","50thPercentile","75thPercentile","90thPercentile","95thPercentile","99thPercentile","99.9thPercentile","100thPercentile"]

class ContractError(RuntimeError): pass

def open_text(path: Path):
    return gzip.open(path, "rt", encoding="utf-8", errors="replace", newline="") if path.suffix == ".gz" else path.open("rt", encoding="utf-8", errors="replace", newline="")

def read_tsv(path: Path):
    with open_text(path) as h:
        r=csv.DictReader(h, delimiter="\t")
        if not r.fieldnames: raise ContractError(f"missing header: {path}")
        return list(r.fieldnames), list(r)

def atomic_tsv(path: Path, fields: list[str], rows: Iterable[Mapping[str, object]], gz=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=f".{path.name}.",dir=str(path.parent)); os.close(fd)
    try:
        opener=gzip.open if gz else open
        with opener(tmp,"wt",encoding="utf-8",newline="") as out:
            w=csv.DictWriter(out,fieldnames=fields,delimiter="\t",lineterminator="\n",extrasaction="ignore")
            w.writeheader()
            for row in rows: w.writerow({k:row.get(k,".") for k in fields})
        os.replace(tmp,path)
    except Exception:
        try: os.unlink(tmp)
        except FileNotFoundError: pass
        raise

def normalize_chrom(x:str)->str:
    x=x.strip(); return x if x.startswith("chr") else f"chr{x}"

def clean_motif(x:str)->str: return re.sub(r"[^ACGTRYSWKMBDHVN]","",(x or "").upper())
def rotations(s:str): return [s[i:]+s[:i] for i in range(len(s))] if s else []
def canonical(s:str)->str:
    s=clean_motif(s)
    if not s:return ""
    rc=s.translate(IUPAC_COMP)[::-1]
    return min(rotations(s)+rotations(rc))

def norm_name(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())

def candidate_intervals(row: Mapping[str, str], fields: list[str]):
    out=[]
    normalized=[norm_name(x) for x in fields]
    chrom_i=next((i for i,x in enumerate(normalized) if x in {"chrom","chr","chromosome"} or x.endswith("chromosome")),None)
    start_i=next((i for i,x in enumerate(normalized) if x in {"start","chromstart","begin","pos","position"} or x.endswith("start") or x.endswith("startposition")),None)
    end_i=next((i for i,x in enumerate(normalized) if x in {"end","chromend","stop"} or x.endswith("end") or x.endswith("endposition")),None)
    values=[row.get(f,"") for f in fields]
    if chrom_i is not None and start_i is not None and end_i is not None:
        try:
            chrom=normalize_chrom(values[chrom_i]); s=int(float(values[start_i])); e=int(float(values[end_i]))
            if e>s>=0:
                out.append((chrom,s,e,"SEPARATE_0_BASED_HALF_OPEN"))
                if s>0: out.append((chrom,s-1,e,"SEPARATE_1_BASED_INCLUSIVE"))
        except (TypeError,ValueError):
            pass
    for value in values:
        m=COORD_RE.search(value or "")
        if not m: continue
        chrom=normalize_chrom(m.group("chrom")); s=int(m.group("start")); e=int(m.group("end"))
        if e>s>=0:
            out.append((chrom,s,e,"COMPOSITE_0_BASED_HALF_OPEN"))
            if s>0: out.append((chrom,s-1,e,"COMPOSITE_1_BASED_INCLUSIVE"))
    seen=set(); unique=[]
    for item in out:
        key=item[:3]
        if key not in seen:
            seen.add(key); unique.append(item)
    return unique

def fnum(x):
    try:
        v=float(x)
        return v if math.isfinite(v) else None
    except Exception:return None

def score_log_ratio(values):
    vals=[abs(math.log2(a/b)) for a,b in values if a and b and a>0 and b>0]
    return statistics.median(vals) if vals else float("inf")

def infer_allele_unit(records):
    bp=[]; ru=[]
    for r in records:
        raw=fnum(r.get("mode")) or fnum(r.get("50thPercentile"))
        span=r["reference_span_bp"]; mlen=r["motif_length_bp"]
        if raw and span>0 and mlen>0:
            bp.append((raw,span)); ru.append((raw*mlen,span))
    sbp=score_log_ratio(bp); sru=score_log_ratio(ru)
    if not math.isfinite(sbp) or not math.isfinite(sru): return "HOLD_INSUFFICIENT",sbp,sru
    margin=abs(sbp-sru)
    if margin < 0.20:return "HOLD_AMBIGUOUS",sbp,sru
    return ("PASS_BP" if sbp<sru else "PASS_REPEAT_UNITS"),sbp,sru

def convert(v, unit, motif_len):
    x=fnum(v)
    if x is None:return None
    if unit=="PASS_BP":return x
    if unit=="PASS_REPEAT_UNITS":return x*motif_len
    return None

def classify(obs,pmin,p1,p5,p95,p99,p999,pmax):
    if obs is None or p5 is None or p95 is None:return "NO_COMPARISON"
    if pmin is not None and obs<pmin:return "BELOW_OBSERVED_MIN"
    if p1 is not None and obs<p1:return "BELOW_P1"
    if obs<p5:return "BELOW_P5"
    if pmax is not None and obs>pmax:return "ABOVE_OBSERVED_MAX"
    if p999 is not None and obs>p999:return "ABOVE_P99_9"
    if p99 is not None and obs>p99:return "ABOVE_P99"
    if obs>p95:return "ABOVE_P95"
    return "WITHIN_P5_P95"

def scan_file(path:Path, coord_map, motif_specific=False):
    found=defaultdict(list); rows=0; parseable=0; methods=Counter()
    with open_text(path) as h:
        rd=csv.DictReader(h,delimiter="\t")
        if not rd.fieldnames:raise ContractError(f"missing header {path}")
        fields=list(rd.fieldnames)
        for row in rd:
            rows+=1
            if rows%1000000==0:print(f"AOU_SCAN_PROGRESS\t{path.name}\t{rows}",flush=True)
            candidates=candidate_intervals(row,fields)
            if candidates: parseable+=1
            qids=set()
            for chrom,start,end,method in candidates:
                hits=coord_map.get((chrom,start,end))
                if hits:
                    qids.update(hits); methods[method]+=1
            if not qids:continue
            for qid in qids:found[qid].append(dict(row))
    method_text=";".join(f"{k}={v}" for k,v in sorted(methods.items())) or "."
    print(f"AOU_SCAN_DONE\t{path.name}\trows={rows}\tparseable_rows={parseable}\tmatched_loci={len(found)}\tmatch_methods={method_text}",flush=True)
    return found,fields,rows

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--crosswalk",type=Path,required=True); ap.add_argument("--allele",type=Path,required=True)
    ap.add_argument("--lps-locus",type=Path,required=True); ap.add_argument("--lps-motif",type=Path,required=True)
    ap.add_argument("--out-root",type=Path,required=True); ap.add_argument("--qc-root",type=Path,required=True)
    ap.add_argument("--expected-loci",type=int,required=True); ap.add_argument("--expected-primary",type=int,required=True)
    ap.add_argument("--script-sha",required=True); ap.add_argument("--crosswalk-sha",required=True)
    args=ap.parse_args()
    for d in ("tables","summary","schema","contracts","provenance"):(args.out_root/d).mkdir(parents=True,exist_ok=True)
    args.qc_root.mkdir(parents=True,exist_ok=True)

    fields,rows=read_tsv(args.crosswalk)
    if len(rows)!=args.expected_loci:raise ContractError("crosswalk denominator mismatch")
    req={"reference_query_id","chrom","query_start_0based","query_end_0based_exclusive","query_motif","motif_length_bp","unique_read_count","support_bin","observed_rna_repeat_bp_median","observed_rna_repeat_bp_max","trexplorer_safe_equivalent","trexplorer_best_chrom","trexplorer_best_start_0based","trexplorer_best_end_0based_exclusive","aou_validation_allele_addressable"}
    miss=req-set(fields)
    if miss:raise ContractError(f"missing fields: {sorted(miss)}")
    byid={r["reference_query_id"]:r for r in rows}
    coord_map=defaultdict(set)
    for r in rows:
        qid=r["reference_query_id"]
        coord_map[(r["chrom"],int(r["query_start_0based"]),int(r["query_end_0based_exclusive"]))].add(qid)
        if r.get("trexplorer_safe_equivalent")=="True" or r.get("trexplorer_safe_equivalent")=="true":
            coord_map[(r["trexplorer_best_chrom"],int(r["trexplorer_best_start_0based"]),int(r["trexplorer_best_end_0based_exclusive"]))].add(qid)

    print("STAGE6AB_PHASE\tAoU_validation_allele",flush=True)
    allele,allele_fields,allele_rows=scan_file(args.allele,coord_map)
    print("STAGE6AB_PHASE\tAoU_validation_lps_locus",flush=True)
    lpsloc,lpsloc_fields,lpsloc_rows=scan_file(args.lps_locus,coord_map)
    print("STAGE6AB_PHASE\tAoU_validation_lps_motif",flush=True)
    lpsmot,lpsmot_fields,lpsmot_rows=scan_file(args.lps_motif,coord_map,True)

    unit_records=[]
    for qid,alist in allele.items():
        if len(alist)!=1:continue
        q=byid[qid]; rec=dict(alist[0])
        rec["reference_span_bp"]=int(q["trexplorer_best_end_0based_exclusive"])-int(q["trexplorer_best_start_0based"])
        rec["motif_length_bp"]=int(q["motif_length_bp"])
        unit_records.append(rec)
    allele_unit,sbp,sru=infer_allele_unit(unit_records)

    # Empirical LPS unit inference: choose the hypothesis that minimizes LPS>allele violations.
    def infer_lps(source, motif_specific):
        results=[]
        for qid,recs in source.items():
            if qid not in allele or len(allele[qid])!=1:continue
            q=byid[qid]; a=allele[qid][0]
            amax=convert(a.get("100thPercentile"),allele_unit,int(q["motif_length_bp"]))
            if amax is None:continue
            chosen=recs
            if motif_specific:
                eq=[r for r in recs if canonical(r.get("LPS_Motif",""))==canonical(q["query_motif"])]
                if not eq:continue
                chosen=eq
            for r in chosen:
                raw=fnum(r.get("100thPercentile"));
                if raw is None:continue
                mlen=len(clean_motif(r.get("LPS_Motif",""))) if motif_specific else int(q["motif_length_bp"])
                if mlen<=0:continue
                results.append((raw,raw*mlen,amax))
        if not results:return "HOLD_INSUFFICIENT",0,0,len(results)
        bpv=sum(1 for bp,ru,a in results if bp>a+1e-6)/len(results)
        ruv=sum(1 for bp,ru,a in results if ru>a+1e-6)/len(results)
        if abs(bpv-ruv)<0.02:return "HOLD_AMBIGUOUS",bpv,ruv,len(results)
        return ("PASS_BP" if bpv<ruv else "PASS_REPEAT_UNITS"),bpv,ruv,len(results)
    lps_locus_unit,ll_bp,ll_ru,ll_n=infer_lps(lpsloc,False)
    lps_motif_unit,lm_bp,lm_ru,lm_n=infer_lps(lpsmot,True)

    out=[]; class_counts=Counter(); motif_rows_attached=0; allele_attached=0
    for qid in sorted(byid):
        q=byid[qid]; safe=str(q.get("trexplorer_safe_equivalent","")).lower()=="true"
        ar=allele.get(qid,[])
        a=ar[0] if len(ar)==1 else None
        mlen=int(q["motif_length_bp"])
        record=dict(q)
        record.update({
            "aou_validation_allele_row_count":len(ar),"aou_allele_unit_status":allele_unit,
            "aou_allele_N":a.get("N", ".") if a else ".",
        })
        for f in PCTS+["mean","std","mad","mode","uniqueLengths","uniqueAlleleSeqs"]:
            raw=a.get(f) if a else None
            record[f"aou_allele_{f}_raw"]=raw if raw not in (None,"") else "."
            bp=convert(raw,allele_unit,mlen) if a else None
            record[f"aou_allele_{f}_bp"]=f"{bp:.6f}" if bp is not None else "."
        # Motif-specific LPS row: strict canonical match, then highest N_motif.
        eq=[]
        for r in lpsmot.get(qid,[]):
            if canonical(r.get("LPS_Motif",""))==canonical(q["query_motif"]):eq.append(r)
        eq.sort(key=lambda r:fnum(r.get("N_motif")) or -1,reverse=True)
        lm=eq[0] if eq else None
        if lm:motif_rows_attached+=1
        record["aou_lps_motif_row_count_strict"]=len(eq)
        record["aou_lps_motif_unit_status"]=lps_motif_unit
        record["aou_lps_motif"]=lm.get("LPS_Motif",".") if lm else "."
        record["aou_lps_motif_N"]=lm.get("N_motif",".") if lm else "."
        lm_len=len(clean_motif(lm.get("LPS_Motif",""))) if lm else 0
        for f in PCTS+["mean","std","mad","mode","uniqueLengths"]:
            raw=lm.get(f) if lm else None
            record[f"aou_lps_motif_{f}_raw"]=raw if raw not in (None,"") else "."
            bp=convert(raw,lps_motif_unit,lm_len) if lm else None
            record[f"aou_lps_motif_{f}_bp"]=f"{bp:.6f}" if bp is not None else "."
        obsmax=fnum(q.get("observed_rna_repeat_bp_max")); obsmed=fnum(q.get("observed_rna_repeat_bp_median"))
        pmin=convert(a.get("0thPercentile"),allele_unit,mlen) if a else None
        p1=convert(a.get("1stPercentile"),allele_unit,mlen) if a else None
        p5=convert(a.get("5thPercentile"),allele_unit,mlen) if a else None
        p95=convert(a.get("95thPercentile"),allele_unit,mlen) if a else None
        p99=convert(a.get("99thPercentile"),allele_unit,mlen) if a else None
        p999=convert(a.get("99.9thPercentile"),allele_unit,mlen) if a else None
        pmax=convert(a.get("100thPercentile"),allele_unit,mlen) if a else None
        permission = safe and a is not None and allele_unit in {"PASS_BP","PASS_REPEAT_UNITS"}
        record["primary_population_length_comparison_permission"]="ALLOW_CONTEXT_ONLY" if permission else "HOLD"
        record["rna_max_vs_aou_allele_class"]=classify(obsmax,pmin,p1,p5,p95,p99,p999,pmax) if permission else "NO_COMPARISON"
        record["rna_median_vs_aou_allele_class"]=classify(obsmed,pmin,p1,p5,p95,p99,p999,pmax) if permission else "NO_COMPARISON"
        record["rna_lps_vs_aou_lps_permission"]="HOLD_RNA_LPS_NOT_YET_MEASURED"
        record["final_ranking_permission"]="HOLD_SAME_PROTOCOL_RNA_CONTROL_AND_RNA_LPS"
        if a:allele_attached+=1
        class_counts[record["rna_max_vs_aou_allele_class"]]+=1
        out.append(record)

    if allele_attached != args.expected_primary:
        raise ContractError(f"AoU primary matched-locus mismatch expected={args.expected_primary} observed={allele_attached}")

    fields_out=sorted({k for r in out for k in r})
    atomic_tsv(args.out_root/"tables/p01_locus.aou_validation_rna_length_comparison.tsv.gz",fields_out,out,True)
    tail_classes={"BELOW_OBSERVED_MIN","BELOW_P1","BELOW_P5","ABOVE_P95","ABOVE_P99","ABOVE_P99_9","ABOVE_OBSERVED_MAX"}
    candidate=[r for r in out if r["rna_max_vs_aou_allele_class"] in tail_classes or r["rna_median_vs_aou_allele_class"] in tail_classes]
    atomic_tsv(args.out_root/"tables/p01_locus.aou_validation_rna_length_tail_flags.tsv.gz",fields_out,candidate,True)

    semantics=[
        {"resource":"AoU validation alleleLengthStats","unit_status":allele_unit,"bp_hypothesis_score":f"{sbp:.6f}","repeat_unit_hypothesis_score":f"{sru:.6f}","audit_n":len(unit_records),"automatic_use":"ALLOW" if allele_unit.startswith("PASS") else "HOLD"},
        {"resource":"AoU validation lpsPerLocusStats","unit_status":lps_locus_unit,"bp_hypothesis_violation_fraction":f"{ll_bp:.6f}","repeat_unit_hypothesis_violation_fraction":f"{ll_ru:.6f}","audit_n":ll_n,"automatic_use":"ATTACH_ONLY_NO_RNA_LPS"},
        {"resource":"AoU validation lpsPerMotifStats","unit_status":lps_motif_unit,"bp_hypothesis_violation_fraction":f"{lm_bp:.6f}","repeat_unit_hypothesis_violation_fraction":f"{lm_ru:.6f}","audit_n":lm_n,"automatic_use":"ATTACH_ONLY_NO_RNA_LPS"},
    ]
    sf=sorted({k for r in semantics for k in r}); atomic_tsv(args.out_root/"schema/aou_statistic_unit_semantics.tsv",sf,semantics)
    class_rows=[{"rna_max_vs_aou_allele_class":k,"locus_rows":v,"denominator":args.expected_loci,"fraction":f"{v/args.expected_loci:.9f}"} for k,v in sorted(class_counts.items())]
    atomic_tsv(args.out_root/"summary/rna_max_vs_aou_allele_class.distribution.tsv",list(class_rows[0]) if class_rows else ["rna_max_vs_aou_allele_class"],class_rows)
    support=defaultdict(Counter)
    for r in out:support[r["support_bin"]][r["rna_max_vs_aou_allele_class"]]+=1
    support_rows=[]
    for sb,c in sorted(support.items()):
        n=sum(c.values()); rec={"support_bin":sb,"locus_denominator":n}
        for k in ("BELOW_OBSERVED_MIN","BELOW_P1","BELOW_P5","WITHIN_P5_P95","ABOVE_P95","ABOVE_P99","ABOVE_P99_9","ABOVE_OBSERVED_MAX","NO_COMPARISON"):rec[k]=c.get(k,0)
        support_rows.append(rec)
    atomic_tsv(args.out_root/"summary/rna_max_tail_flags_by_support_bin.tsv",list(support_rows[0]) if support_rows else ["support_bin"],support_rows)

    comparable=sum(1 for r in out if r["primary_population_length_comparison_permission"]=="ALLOW_CONTEXT_ONLY")
    tail_classes={"BELOW_OBSERVED_MIN","BELOW_P1","BELOW_P5","ABOVE_P95","ABOVE_P99","ABOVE_P99_9","ABOVE_OBSERVED_MAX"}
    tail=sum(1 for r in out if r["rna_max_vs_aou_allele_class"] in tail_classes or r["rna_median_vs_aou_allele_class"] in tail_classes)
    qc=[
        {"metric":"stage_version","value":VERSION},{"metric":"all_p01_loci_denominator","value":args.expected_loci},
        {"metric":"aou_validation_expected_addressable_loci","value":args.expected_primary},{"metric":"aou_validation_allele_rows_scanned","value":allele_rows},
        {"metric":"aou_validation_lps_locus_rows_scanned","value":lpsloc_rows},{"metric":"aou_validation_lps_motif_rows_scanned","value":lpsmot_rows},
        {"metric":"aou_allele_unit_status","value":allele_unit},{"metric":"aou_lps_locus_unit_status","value":lps_locus_unit},{"metric":"aou_lps_motif_unit_status","value":lps_motif_unit},
        {"metric":"primary_population_length_comparable_loci","value":comparable},{"metric":"primary_population_length_comparable_fraction","value":f"{comparable/args.expected_loci:.9f}"},
        {"metric":"motif_specific_lps_rows_attached_loci","value":motif_rows_attached},{"metric":"rna_max_population_tail_flag_loci","value":tail},
        {"metric":"rna_lps_measurement_available","value":"false"},{"metric":"same_protocol_rna_control_available","value":"false"},
        {"metric":"final_ranking_executed","value":0},{"metric":"coverage_gate_status","value":"HOLD_PENDING_SAME_PROTOCOL_RNA_CONTROLS_AND_RNA_LPS_MEASUREMENT"},
        {"metric":"script_sha256","value":args.script_sha},{"metric":"crosswalk_sha256","value":args.crosswalk_sha},
        {"metric":"stage6ab_status","value":"PASS_PRIMARY_LENGTH_CONTEXT_READY" if allele_unit.startswith("PASS") else "HOLD_ALLELE_UNIT_SEMANTICS_AMBIGUOUS"},
    ]
    atomic_tsv(args.qc_root/"aou_stat_semantics_rna_length_comparison.qc.tsv",["metric","value"],qc)
    contract=[
        {"item":"AoU allele length","rule":"Compare RNA total repeat bp only after empirical unit semantics PASS","status":"ENFORCED"},
        {"item":"AoU LPS","rule":"Attach motif-specific population LPS; do not compare until RNA LPS is measured","status":"ENFORCED"},
        {"item":"Bidirectional tail flag","rule":"Classify shorter and longer population-relative observations; context only, not genotype or pathogenicity","status":"ENFORCED"},
        {"item":"Final ranking","rule":"Blocked until same-protocol RNA controls and RNA LPS/motif decomposition","status":"HOLD"},
    ]
    atomic_tsv(args.out_root/"contracts/comparison_use_contract.tsv",["item","rule","status"],contract)
    return 0

if __name__=="__main__":raise SystemExit(main())
PY

python -m py_compile "$PY_IMPL"
implementation_sha="$(sha256sum "$PY_IMPL" | awk '{print $1}')"

echo "===== STAGE 6AB PREFLIGHT ====="
echo "stage version:              $STAGE_VERSION"
echo "all loci denominator:       $EXPECTED_QUERY_LOCI"
echo "AoU primary addressable:    $EXPECTED_AOU_PRIMARY"
echo "task:                       infer statistic units; compare RNA total repeat bp bidirectionally to AoU allele distribution
coordinate parser:          Stage 6AA-compatible all-field parser"
echo "RNA LPS comparison:         NOT RUN; RNA LPS not yet measured"
echo "Vienna reconciliation:      DEFERRED; non-exact boundary audit"
echo "final ranking:              BLOCKED"
echo "script SHA-256:             $script_sha"

python "$PY_IMPL" \
  --crosswalk "$CROSSWALK" \
  --allele "$ALLELE" \
  --lps-locus "$LPS_LOCUS" \
  --lps-motif "$LPS_MOTIF" \
  --out-root "$STAGE_OUT" \
  --qc-root "$STAGE_QC" \
  --expected-loci "$EXPECTED_QUERY_LOCI" \
  --expected-primary "$EXPECTED_AOU_PRIMARY" \
  --script-sha "$script_sha" \
  --crosswalk-sha "$crosswalk_sha"

mkdir -p "$(dirname "$OUT_ROOT")" "$(dirname "$QC_ROOT")"
mv "$STAGE_OUT" "$OUT_ROOT"
mv "$STAGE_QC" "$QC_ROOT"
cp -f "$0" "$SCRIPT_DEST"

{
  printf 'artifact\tsha256\n'
  while IFS= read -r -d '' f; do printf '%s\t%s\n' "${f#$OUT_ROOT/}" "$(sha256sum "$f"|awk '{print $1}')"; done < <(find "$OUT_ROOT" -type f -print0 | sort -z)
  printf 'QC/aou_stat_semantics_rna_length_comparison.qc.tsv\t%s\n' "$(sha256sum "$FINAL_QC"|awk '{print $1}')"
} > "$MANIFEST"

ln -sfn "$OUT_ROOT" "$LATEST_RESULT"
ln -sfn "$QC_ROOT" "$LATEST_QC"

echo
echo "===== STAGE 6AB FINAL QC ====="
column -ts $'\t' "$FINAL_QC"
echo
echo "===== AOU STATISTIC UNIT SEMANTICS ====="
column -ts $'\t' "$OUT_ROOT/schema/aou_statistic_unit_semantics.tsv"
echo
echo "===== RNA MAX VS AOU ALLELE DISTRIBUTION ====="
column -ts $'\t' "$OUT_ROOT/summary/rna_max_vs_aou_allele_class.distribution.tsv"
echo
echo "===== OUTPUT ====="
echo "Result:        $OUT_ROOT"
echo "QC:            $FINAL_QC"
echo "Comparison:    $OUT_ROOT/tables/p01_locus.aou_validation_rna_length_comparison.tsv.gz"
echo "Tail flags:    $OUT_ROOT/tables/p01_locus.aou_validation_rna_length_tail_flags.tsv.gz"
echo "Latest result: $LATEST_RESULT"
echo "Latest QC:     $LATEST_QC"
