#!/usr/bin/env bash
set -euo pipefail

STAGE_VERSION="rnatr_repeatcatalogs_crosswalk_coverage_audit_v0.1.2"
RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"
EXPECTED_ALL_LOCI=11042
EXPECTED_EXACT_LOCI=403
EXPECTED_UNMATCHED_LOCI=10639
NEARBY_BP=100
SAFE_MAX_BOUNDARY_BP=10
SAFE_MIN_RECIPROCAL_OVERLAP=0.80

: "${PROJECT_ROOT:?PROJECT_ROOT is not set; source config/paths.env first}"

QUERY_ROOT="$PROJECT_ROOT/results/11_reference_control_adapter_query_package/$RUN_ID/rnatr_reference_control_adapter_query_package_v0.1.0"
QUERY_QC="$PROJECT_ROOT/qc/11_reference_control_adapter_query_package/$RUN_ID/rnatr_reference_control_adapter_query_package_v0.1.0/reference_control_adapter_query_package.qc.tsv"
QUERIES="$QUERY_ROOT/p01_locus.reference_control_queries.tsv.gz"

STAGE6M_ROOT="$PROJECT_ROOT/results/11_repeatcatalogs_reference_1kg_audit/$RUN_ID/rnatr_freeze_tratlas_crosswalk_audit_repeatcatalogs_1kg_v0.1.0"
STAGE6M_QC="$PROJECT_ROOT/qc/11_repeatcatalogs_reference_1kg_audit/$RUN_ID/rnatr_freeze_tratlas_crosswalk_audit_repeatcatalogs_1kg_v0.1.0/repeatcatalogs_reference_1kg_audit.qc.tsv"
EXACT_MATCHES="$STAGE6M_ROOT/reference_locus/p01_locus.repeatcatalogs_reference_exact_matches.tsv.gz"

STAGE6N_ROOT="$PROJECT_ROOT/results/11_repeatcatalogs_1kg_genomewide_adapter/$RUN_ID/rnatr_repeatcatalogs_1kg_genomewide_adapter_v0.1.3"
STAGE6N_QC="$PROJECT_ROOT/qc/11_repeatcatalogs_1kg_genomewide_adapter/$RUN_ID/rnatr_repeatcatalogs_1kg_genomewide_adapter_v0.1.3/repeatcatalogs_1kg_genomewide_adapter.qc.tsv"
COMPONENTS="$STAGE6N_ROOT/distributions/repeatcatalogs_1kg_histogram.normalized.tsv.gz"

STAGE6Q_QC="$PROJECT_ROOT/qc/11_p01_multisource_context_precontrol_review/$RUN_ID/rnatr_p01_multisource_context_precontrol_review_v0.1.0/p01_multisource_context_precontrol_review.qc.tsv"

OUT_ROOT="$PROJECT_ROOT/results/11_repeatcatalogs_crosswalk_coverage_audit/$RUN_ID/$STAGE_VERSION"
QC_ROOT="$PROJECT_ROOT/qc/11_repeatcatalogs_crosswalk_coverage_audit/$RUN_ID/$STAGE_VERSION"
PROV_ROOT="$OUT_ROOT/provenance"
TABLE_ROOT="$OUT_ROOT/tables"
SUMMARY_ROOT="$OUT_ROOT/summary"
CONTRACT_ROOT="$OUT_ROOT/contracts"
PLAN_ROOT="$OUT_ROOT/external_reference_plan"
mkdir -p "$PROV_ROOT" "$TABLE_ROOT" "$SUMMARY_ROOT" "$CONTRACT_ROOT" "$PLAN_ROOT" "$QC_ROOT"

for p in "$QUERY_QC" "$QUERIES" "$STAGE6M_QC" "$EXACT_MATCHES" "$STAGE6N_QC" "$COMPONENTS" "$STAGE6Q_QC"; do
  [[ -s "$p" ]] || { echo "ERROR: missing prerequisite: $p" >&2; exit 1; }
done
for t in python gzip sha256sum; do command -v "$t" >/dev/null || { echo "ERROR: missing tool $t" >&2; exit 1; }; done

metric() { awk -F $'\t' -v k="$2" '$1==k{print $2;f=1;exit}END{if(!f)print "."}' "$1"; }
[[ "$(metric "$QUERY_QC" adapter_query_package_status)" == PASS ]] || { echo "ERROR: query package not PASS" >&2; exit 1; }
[[ "$(metric "$STAGE6M_QC" stage6m_reference_1kg_audit_status)" == PASS ]] || { echo "ERROR: Stage 6M not PASS" >&2; exit 1; }
[[ "$(metric "$STAGE6N_QC" stage6n_1kg_genomewide_adapter_status)" == PASS ]] || { echo "ERROR: Stage 6N not PASS" >&2; exit 1; }
[[ "$(metric "$STAGE6Q_QC" stage6q_multisource_context_status)" == PASS ]] || { echo "ERROR: Stage 6Q not PASS" >&2; exit 1; }

gzip -t "$QUERIES"; gzip -t "$EXACT_MATCHES"; gzip -t "$COMPONENTS"

PY_IMPL="$PROV_ROOT/rnatr_repeatcatalogs_crosswalk_coverage_audit_v0.1.2.py"
cat > "$PY_IMPL" <<'PY'
from __future__ import annotations
import argparse, csv, gzip, hashlib, math, os, tempfile
from collections import Counter, defaultdict
from pathlib import Path

VERSION="rnatr_repeatcatalogs_crosswalk_coverage_audit_v0.1.2"
IUPAC=set("ACGTRYSWKMBDHVN")
UNAMBIGUOUS=set("ACGT")
COMP=str.maketrans("ACGTRYSWKMBDHVN","TGCAYRSWMKVHDBN")
BIN=1000

class ContractError(RuntimeError): pass

def open_text(p): return gzip.open(p,"rt",encoding="utf-8",newline="") if p.suffix==".gz" else p.open("rt",encoding="utf-8",newline="")
def read_tsv(p):
    with open_text(p) as h:
        r=csv.DictReader(h,delimiter="\t")
        if r.fieldnames is None: raise ContractError(f"missing header: {p}")
        return list(r.fieldnames),list(r)
def write_tsv(p,fields,rows,gz=False):
    p.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=f".{p.name}.",dir=str(p.parent)); os.close(fd)
    try:
        h=gzip.open(tmp,"wt",encoding="utf-8",newline="") if gz else open(tmp,"wt",encoding="utf-8",newline="")
        with h:
            w=csv.DictWriter(h,fieldnames=fields,delimiter="\t",lineterminator="\n",extrasaction="raise"); w.writeheader()
            for row in rows: w.writerow({f:row.get(f,".") for f in fields})
        os.replace(tmp,p)
    except Exception:
        try: os.unlink(tmp)
        except FileNotFoundError: pass
        raise
def sha(p):
    d=hashlib.sha256()
    with p.open("rb") as h:
        for b in iter(lambda:h.read(1048576),b""): d.update(b)
    return d.hexdigest()
def chrom(x):
    x=x.strip(); return x if x.lower().startswith("chr") else "chr"+x
def rc(x): return x.translate(COMP)[::-1]
def rotations(x): return {x[i:]+x[:i] for i in range(len(x))}
def canonical(x):
    x=x.upper().replace("U","T")
    if not x or set(x)-IUPAC: raise ContractError(f"bad IUPAC motif {x}")
    return min(rotations(x)|rotations(rc(x)))
def has_ambiguous_iupac(x):
    x=x.upper().replace("U","T")
    return bool(set(x)-UNAMBIGUOUS)
def primitive(x):
    x=x.upper().replace("U","T")
    for n in range(1,len(x)+1):
        if len(x)%n==0 and x[:n]*(len(x)//n)==x: return canonical(x[:n])
    return canonical(x)
def ov(a,b,c,d): return max(0,min(b,d)-max(a,c))
def dist(a,b,c,d):
    if ov(a,b,c,d): return 0
    return c-b if b<=c else a-d
def bins_for(a,b,pad=0): return range(max(0,(a-pad)//BIN),(b-1+pad)//BIN+1)
def reciprocal(a,b,c,d):
    o=ov(a,b,c,d); return o/(b-a),o/(d-c)

def classify(q,cands,nearby,max_boundary,min_recip):
    qs,qe=q["start"],q["end"]; qcan=q["can"]; qprim=q["prim"]; m=q["mlen"]
    overlaps=[c for c in cands if ov(qs,qe,c["start"],c["end"])>0]
    pool=overlaps or nearby
    if not pool:
        return "NO_CATALOG_COVERAGE","ONE_KG_CATALOG_LOCUS_ABSENT_AT_QUERY_INTERVAL","NO_OVERLAP_OR_NEARBY_COMPONENT",None
    def score(c):
        exact=(qs==c["start"] and qe==c["end"])
        ro=reciprocal(qs,qe,c["start"],c["end"])
        return (exact and qcan==c["can"], exact and qprim==c["prim"], qcan==c["can"], qprim==c["prim"], ov(qs,qe,c["start"],c["end"]), min(ro), -dist(qs,qe,c["start"],c["end"]), c["id"])
    best=max(pool,key=score)
    cs,ce=best["start"],best["end"]; exact=(qs==cs and qe==ce); samecan=(qcan==best["can"]); sameprim=(qprim==best["prim"])
    if q.get("ambiguous",False) or best.get("ambiguous",False):
        if exact and samecan:
            return "MANUAL_REVIEW_ONLY","AMBIGUOUS_IUPAC_MOTIF_REPRESENTATION","EXACT_COORDINATE_BUT_IUPAC_AMBIGUITY_REQUIRES_MANUAL_REVIEW",best
        if overlaps:
            return "MANUAL_REVIEW_ONLY","AMBIGUOUS_IUPAC_MOTIF_REPRESENTATION","OVERLAPPING_COMPONENT_CONTAINS_IUPAC_AMBIGUITY",best
    if exact and samecan:
        reason="MOTIF_ROTATION_REVERSE_COMPLEMENT_OR_LITERAL_NOTATION_DIFFERENCE" if q["motif"]!=best["motif"] else "EXACT_COORDINATE_AND_CANONICAL_MOTIF_EQUIVALENCE"
        return "BIOLOGICALLY_EQUIVALENT_SAFE",reason,"EXACT_COORDINATES_BP_COMPARISON_SAFE",best
    if exact and sameprim and best["regions"]==1:
        return "BIOLOGICALLY_EQUIVALENT_SAFE","MOTIF_UNIT_REPRESENTATION_DIFFERENCE","SAME_PRIMITIVE_PERIOD_EXACT_COORDINATES",best
    if best["regions"]>1 or len(overlaps)>1:
        return "MANUAL_REVIEW_ONLY","COMPOUND_OR_MULTI_COMPONENT_REPEAT_STRUCTURE_DIFFERENCE","MULTI_COMPONENT_OR_AMBIGUOUS_OVERLAP",best
    if overlaps and samecan:
        rq,rcp=reciprocal(qs,qe,cs,ce); ds=qs-cs; de=qe-ce
        phase=(ds%m==0 and de%m==0); small=(abs(ds)<=max(max_boundary,2*m) and abs(de)<=max(max_boundary,2*m)); high=min(rq,rcp)>=min_recip
        if phase and small and high:
            return "BIOLOGICALLY_EQUIVALENT_SAFE","REPEAT_BOUNDARY_ONLY_DIFFERENCE","PHASE_COMPATIBLE_SMALL_BOUNDARY_OFFSET_HIGH_RECIPROCAL_OVERLAP",best
        return "MANUAL_REVIEW_ONLY","REPEAT_BOUNDARY_ONLY_DIFFERENCE",f"UNSAFE_BOUNDARY:phase={str(phase).lower()};small={str(small).lower()};high_recip={str(high).lower()}",best
    if overlaps and sameprim:
        return "MANUAL_REVIEW_ONLY","MOTIF_UNIT_REPRESENTATION_DIFFERENCE","PRIMITIVE_PERIOD_MATCH_REQUIRES_BOUNDARY_REVIEW",best
    if overlaps:
        return "MANUAL_REVIEW_ONLY","MOTIF_OR_REPEAT_STRUCTURE_MISMATCH","OVERLAP_WITH_NON_EQUIVALENT_MOTIF",best
    same_near=[c for c in nearby if c["can"]==qcan or c["prim"]==qprim]
    if same_near:
        best=max(same_near,key=score)
        return "MANUAL_REVIEW_ONLY","COORDINATE_BUILD_OR_CATALOG_DESIGN_MISMATCH","NONOVERLAPPING_NEARBY_MOTIF_EQUIVALENT_COMPONENT",best
    return "NO_CATALOG_COVERAGE","ONE_KG_CATALOG_LOCUS_ABSENT_AT_QUERY_INTERVAL","NEARBY_COMPONENTS_EXIST_BUT_NO_MOTIF_EQUIVALENCE",best

def main():
    ap=argparse.ArgumentParser()
    for name in ["queries","exact_matches","components","stage6q_qc","out_root","qc_root"]: ap.add_argument("--"+name.replace("_","-"),type=Path,required=True)
    ap.add_argument("--expected-all-loci",type=int,required=True); ap.add_argument("--expected-exact-loci",type=int,required=True); ap.add_argument("--expected-unmatched-loci",type=int,required=True)
    ap.add_argument("--nearby-bp",type=int,required=True); ap.add_argument("--safe-max-boundary-bp",type=int,required=True); ap.add_argument("--safe-min-reciprocal-overlap",type=float,required=True)
    ap.add_argument("--script-sha256",required=True); ap.add_argument("--implementation-sha256",required=True)
    a=ap.parse_args(); table=a.out_root/"tables"; summary=a.out_root/"summary"; contract=a.out_root/"contracts"; plan=a.out_root/"external_reference_plan"
    for p in [a.out_root,a.qc_root,table,summary,contract,plan]: p.mkdir(parents=True,exist_ok=True)
    qf,qr=read_tsv(a.queries); need={"reference_query_id","representative_locus_id","chrom_with_prefix","start_0based","end_0based_exclusive","canonical_query_motif","motif_length_bp","source_event_count","unique_read_count","observed_rna_repeat_bp_median","observed_rna_repeat_bp_max"}
    if need-set(qf): raise ContractError(f"missing query fields {sorted(need-set(qf))}")
    if len(qr)!=a.expected_all_loci: raise ContractError("query count mismatch")
    ef,er=read_tsv(a.exact_matches); exact={r["reference_query_id"]:r for r in er if r.get("match_status")=="EXACT_UNIQUE"}
    if len(exact)!=a.expected_exact_loci: raise ContractError("exact count mismatch")
    cf,cr=read_tsv(a.components); needc={"component_id","parent_locus_id","region_count_within_parent","chrom","start_0based","end_0based_exclusive","motif","canonical_motif"}
    if needc-set(cf): raise ContractError(f"missing component fields {sorted(needc-set(cf))}")
    comp=[]; idx=defaultdict(list)
    for r in cr:
        m=r["motif"].upper().replace("U","T"); c={"id":r["component_id"],"parent":r["parent_locus_id"],"regions":int(r["region_count_within_parent"]),"chrom":chrom(r["chrom"]),"start":int(r["start_0based"]),"end":int(r["end_0based_exclusive"]),"motif":m,"can":canonical(m),"prim":primitive(m),"ambiguous":has_ambiguous_iupac(m)}; comp.append(c)
        for b in bins_for(c["start"],c["end"],a.nearby_bp): idx[(c["chrom"],b)].append(c)
    denominator=a.expected_all_loci; exact_fraction=a.expected_exact_loci/denominator; rows=[]; tiers=Counter(); reasons=Counter()
    for r in qr:
        motif=r["canonical_query_motif"].upper().replace("U","T"); q={"id":r["reference_query_id"],"locus":r["representative_locus_id"],"chrom":chrom(r["chrom_with_prefix"]),"start":int(r["start_0based"]),"end":int(r["end_0based_exclusive"]),"motif":motif,"can":canonical(motif),"prim":primitive(motif),"mlen":int(r["motif_length_bp"]),"ambiguous":has_ambiguous_iupac(motif)}
        if q["id"] in exact:
            tier,reason,secondary,best="EXACT_MATCH","NOT_APPLICABLE_EXACT_MATCH","STAGE6M_EXACT_UNIQUE",None
        else:
            seen={}
            for b in bins_for(q["start"],q["end"],a.nearby_bp):
                for c in idx.get((q["chrom"],b),[]): seen[c["id"]]=c
            near=[c for c in seen.values() if dist(q["start"],q["end"],c["start"],c["end"])<=a.nearby_bp]
            tier,reason,secondary,best=classify(q,near,near,a.safe_max_boundary_bp,a.safe_min_reciprocal_overlap)
        tiers[tier]+=1; reasons[reason]+=1
        if best:
            o=ov(q["start"],q["end"],best["start"],best["end"]); rq,rcp=reciprocal(q["start"],q["end"],best["start"],best["end"])
            bd={"best_component_id":best["id"],"best_parent_locus_id":best["parent"],"best_component_start_0based":best["start"],"best_component_end_0based_exclusive":best["end"],"best_component_motif":best["motif"],"best_component_canonical_motif":best["can"],"best_component_primitive_motif":best["prim"],"best_component_region_count":best["regions"],"overlap_bp":o,"query_reciprocal_overlap":f"{rq:.9f}","component_reciprocal_overlap":f"{rcp:.9f}","start_delta_bp":q["start"]-best["start"],"end_delta_bp":q["end"]-best["end"],"span_delta_bp":q["end"]-q["start"]-(best["end"]-best["start"]),"nearest_distance_bp":dist(q["start"],q["end"],best["start"],best["end"])}
        else:
            bd={k:"." for k in ["best_component_id","best_parent_locus_id","best_component_start_0based","best_component_end_0based_exclusive","best_component_motif","best_component_canonical_motif","best_component_primitive_motif","best_component_region_count","start_delta_bp","end_delta_bp","span_delta_bp","nearest_distance_bp"]}; bd.update({"overlap_bp":0,"query_reciprocal_overlap":"0.000000000","component_reciprocal_overlap":"0.000000000"})
        rows.append({"reference_query_id":q["id"],"representative_locus_id":q["locus"],"chrom":q["chrom"],"query_start_0based":q["start"],"query_end_0based_exclusive":q["end"],"query_span_bp":q["end"]-q["start"],"query_motif":q["motif"],"query_canonical_motif":q["can"],"query_primitive_motif":q["prim"],"query_motif_length_bp":q["mlen"],"query_contains_ambiguous_iupac":str(q["ambiguous"]).lower(),"best_component_contains_ambiguous_iupac":str(best.get("ambiguous",False)).lower() if best else ".","source_event_count":r["source_event_count"],"unique_read_count":r["unique_read_count"],"observed_rna_repeat_bp_median":r["observed_rna_repeat_bp_median"],"observed_rna_repeat_bp_max":r["observed_rna_repeat_bp_max"],**bd,"crosswalk_tier":tier,"primary_unmatched_reason":reason,"secondary_reason":secondary,"safe_for_population_comparison":str(tier in {"EXACT_MATCH","BIOLOGICALLY_EQUIVALENT_SAFE"}).lower(),"manual_review_required":str(tier=="MANUAL_REVIEW_ONLY").lower(),"current_exact_population_coverage_numerator_loci":a.expected_exact_loci,"population_coverage_denominator_loci":denominator,"current_exact_population_coverage_fraction":f"{exact_fraction:.9f}","coverage_scope_label":"PILOT_SUBSET_REPEATCATALOGS_1KG_NOT_ALL_P01_LOCI","final_ranking_permission":"HOLD_COVERAGE_EXPANSION_GATE"})
    if sum(tiers.values())!=denominator: raise ContractError("tier accounting mismatch")
    unmatched=denominator-tiers["EXACT_MATCH"]
    if unmatched!=a.expected_unmatched_loci: raise ContractError("unmatched accounting mismatch")
    fields=list(rows[0]); safe=[r for r in rows if r["crosswalk_tier"]=="BIOLOGICALLY_EQUIVALENT_SAFE"]; manual=[r for r in rows if r["crosswalk_tier"]=="MANUAL_REVIEW_ONLY"]; absent=[r for r in rows if r["crosswalk_tier"]=="NO_CATALOG_COVERAGE"]
    write_tsv(table/"p01_locus.repeatcatalogs_crosswalk_coverage_audit.tsv.gz",fields,rows,True); write_tsv(table/"p01_locus.repeatcatalogs_safe_equivalence_candidates.tsv",fields,safe); write_tsv(table/"p01_locus.repeatcatalogs_manual_review_candidates.tsv.gz",fields,manual,True); write_tsv(table/"p01_locus.repeatcatalogs_no_catalog_coverage.tsv.gz",fields,absent,True)
    write_tsv(summary/"crosswalk_tier.distribution.tsv",["crosswalk_tier","locus_rows","denominator_all_p01_loci","fraction_of_all_p01_loci"],[{"crosswalk_tier":k,"locus_rows":v,"denominator_all_p01_loci":denominator,"fraction_of_all_p01_loci":f"{v/denominator:.9f}"} for k,v in sorted(tiers.items())])
    write_tsv(summary/"unmatched_reason.distribution.tsv",["primary_unmatched_reason","locus_rows","denominator_all_p01_loci","fraction_of_all_p01_loci","fraction_of_unmatched_loci"],[{"primary_unmatched_reason":k,"locus_rows":v,"denominator_all_p01_loci":denominator,"fraction_of_all_p01_loci":f"{v/denominator:.9f}","fraction_of_unmatched_loci":f"{(v/unmatched if k!='NOT_APPLICABLE_EXACT_MATCH' else 0):.9f}"} for k,v in sorted(reasons.items())])
    projected=a.expected_exact_loci+len(safe)
    write_tsv(summary/"population_coverage_projection.tsv",["metric","value"],[{"metric":"all_p01_loci_denominator","value":denominator},{"metric":"current_exact_comparable_loci","value":a.expected_exact_loci},{"metric":"current_exact_coverage_fraction","value":f"{exact_fraction:.9f}"},{"metric":"biologically_equivalent_safe_candidate_loci","value":len(safe)},{"metric":"projected_exact_plus_safe_loci_before_validation","value":projected},{"metric":"projected_exact_plus_safe_fraction_before_validation","value":f"{projected/denominator:.9f}"},{"metric":"manual_review_only_loci","value":len(manual)},{"metric":"no_repeatcatalogs_1kg_catalog_coverage_loci","value":len(absent)},{"metric":"five_current_candidates_scope","value":"PILOT_SUBSET_CANDIDATES_WITHIN_403_OF_11042_LOCI"},{"metric":"final_ranking_gate","value":"HOLD_COVERAGE_EXPANSION_REQUIRED"}])
    write_tsv(contract/"tiered_crosswalk_policy.tsv",["tier","definition","population_comparison_permission"],[{"tier":"EXACT_MATCH","definition":"Frozen Stage 6M exact coordinate and motif match.","population_comparison_permission":"ALLOW"},{"tier":"BIOLOGICALLY_EQUIVALENT_SAFE","definition":"Exact primitive/canonical motif equivalence or strict phase-compatible small boundary normalization.","population_comparison_permission":"PROVISIONAL_ALLOW_AFTER_VALIDATION"},{"tier":"MANUAL_REVIEW_ONLY","definition":"Boundary, compound, motif-unit, motif-structure, or nearby-coordinate mismatch not strictly safe.","population_comparison_permission":"DENY_AUTOMATIC"},{"tier":"NO_CATALOG_COVERAGE","definition":"No safely corresponding RepeatCatalogs/1KG component.","population_comparison_permission":"REQUIRES_ADDITIONAL_REFERENCE"}])
    write_tsv(contract/"coverage_gate_policy.tsv",["policy_id","rule","status","detail"],[{"policy_id":"COV01","rule":"SHOW_11042_DENOMINATOR_ON_ALL_CANDIDATE_TABLES","status":"FROZEN","detail":"Every candidate/review table must show comparable numerator and all-P01 denominator."},{"policy_id":"COV02","rule":"RELABEL_CURRENT_FIVE_AS_PILOT_SUBSET_CANDIDATES","status":"FROZEN","detail":"Five loci arose only inside 403 exact-comparable loci."},{"policy_id":"COV03","rule":"NO_FINAL_RANKING_BEFORE_COVERAGE_EXPANSION","status":"HOLD","detail":"Ranking and large specialized-motif implementation remain blocked."},{"policy_id":"COV04","rule":"NO_SIMPLE_OVERLAP_AUTOMATIC_CROSSWALK","status":"FROZEN","detail":"Overlap alone never authorizes population comparison."},{"policy_id":"COV05","rule":"DO_NOT_ASSERT_BUILD_MISMATCH_WITHOUT_LIFTOVER","status":"FROZEN","detail":"Nearby non-overlap remains coordinate-build-or-catalog-design review."},{"policy_id":"COV06","rule":"IUPAC_AMBIGUOUS_MOTIFS_REQUIRE_MANUAL_REVIEW","status":"FROZEN","detail":"IUPAC ambiguity codes such as R/Y/S/W/K/M/B/D/H/V/N are parsed without failure but are not auto-promoted to safe biological equivalence."}])
    write_tsv(plan/"population_reference_expansion_plan.tsv",["priority","source","intended_role","status"],[{"priority":1,"source":"ALLOFUS_LONG_READ_TR_DISTRIBUTIONS_TR_EXPLORER_1.0.1_AND_ADOTTO","intended_role":"ALLELE_LENGTH_AND_LPS_POPULATION_SUMMARIES","status":"NEXT_SOURCE_ACQUISITION"},{"priority":2,"source":"ADOTTO_COMPREHENSIVE_GRCH38_TR_CATALOG_HPRC_HGSVC_1KGP","intended_role":"CATALOG_AND_COMPONENT_COVERAGE_EXPANSION","status":"NEXT_SOURCE_ACQUISITION"},{"priority":3,"source":"HPRC_RELEASE2_ASSEMBLIES","intended_role":"TARGETED_VALIDATION_FOR_HARD_MANUAL_CASES","status":"DEFER_UNTIL_PROCESSED_REFERENCE_GAPS_KNOWN"}])
    ambiguous_components=sum(c["ambiguous"] for c in comp)
    qc=[{"metric":"stage_version","value":VERSION},{"metric":"v0.1.0_failure_cause","value":"IUPAC_AMBIGUITY_CODE_R_NOT_SUPPORTED_IN_COMPONENT_MOTIF"},{"metric":"v0.1.1_repair","value":"FULL_IUPAC_CANONICALIZATION_AND_CONSERVATIVE_MANUAL_REVIEW_GATE"},{"metric":"repeatcatalogs_components_with_ambiguous_iupac","value":ambiguous_components},{"metric":"reason_ambiguous_iupac_motif","value":reasons["AMBIGUOUS_IUPAC_MOTIF_REPRESENTATION"]},{"metric":"all_p01_loci_denominator","value":denominator},{"metric":"current_exact_comparable_loci","value":a.expected_exact_loci},{"metric":"current_exact_coverage_fraction","value":f"{exact_fraction:.9f}"},{"metric":"unmatched_loci","value":unmatched},{"metric":"exact_match_tier_loci","value":tiers["EXACT_MATCH"]},{"metric":"biologically_equivalent_safe_loci","value":tiers["BIOLOGICALLY_EQUIVALENT_SAFE"]},{"metric":"manual_review_only_loci","value":tiers["MANUAL_REVIEW_ONLY"]},{"metric":"no_catalog_coverage_loci","value":tiers["NO_CATALOG_COVERAGE"]},{"metric":"reason_catalog_absent","value":reasons["ONE_KG_CATALOG_LOCUS_ABSENT_AT_QUERY_INTERVAL"]},{"metric":"reason_boundary_only_difference","value":reasons["REPEAT_BOUNDARY_ONLY_DIFFERENCE"]},{"metric":"reason_motif_rotation_revcomp_literal","value":reasons["MOTIF_ROTATION_REVERSE_COMPLEMENT_OR_LITERAL_NOTATION_DIFFERENCE"]},{"metric":"reason_motif_unit_representation","value":reasons["MOTIF_UNIT_REPRESENTATION_DIFFERENCE"]},{"metric":"reason_compound_multi_component","value":reasons["COMPOUND_OR_MULTI_COMPONENT_REPEAT_STRUCTURE_DIFFERENCE"]},{"metric":"reason_motif_or_structure_mismatch","value":reasons["MOTIF_OR_REPEAT_STRUCTURE_MISMATCH"]},{"metric":"reason_coordinate_build_or_catalog_design","value":reasons["COORDINATE_BUILD_OR_CATALOG_DESIGN_MISMATCH"]},{"metric":"projected_exact_plus_safe_loci_before_validation","value":projected},{"metric":"projected_exact_plus_safe_fraction_before_validation","value":f"{projected/denominator:.9f}"},{"metric":"candidate_scope_label","value":"PILOT_SUBSET_CANDIDATES_WITHIN_403_OF_11042_LOCI"},{"metric":"final_ranking_executed","value":0},{"metric":"specialized_large_implementation_started","value":"false"},{"metric":"coverage_expansion_gate_status","value":"HOLD"},{"metric":"stage6r_crosswalk_coverage_audit_status","value":"PASS"},{"metric":"script_sha256","value":a.script_sha256},{"metric":"implementation_sha256","value":a.implementation_sha256},{"metric":"query_sha256","value":sha(a.queries)},{"metric":"exact_matches_sha256","value":sha(a.exact_matches)},{"metric":"components_sha256","value":sha(a.components)},{"metric":"stage6q_qc_sha256","value":sha(a.stage6q_qc)}]
    qcp=a.qc_root/"repeatcatalogs_crosswalk_coverage_audit.qc.tsv"; write_tsv(qcp,["metric","value"],qc)
    print("STAGE6R_STATUS\tPASS"); print(f"ALL_P01_LOCI\t{denominator}"); print(f"EXACT_MATCH\t{tiers['EXACT_MATCH']}"); print(f"BIOLOGICALLY_EQUIVALENT_SAFE\t{tiers['BIOLOGICALLY_EQUIVALENT_SAFE']}"); print(f"MANUAL_REVIEW_ONLY\t{tiers['MANUAL_REVIEW_ONLY']}"); print(f"NO_CATALOG_COVERAGE\t{tiers['NO_CATALOG_COVERAGE']}"); print(f"PROJECTED_EXACT_PLUS_SAFE\t{projected}/{denominator}"); print(f"IUPAC_AMBIGUOUS_COMPONENTS\t{sum(c['ambiguous'] for c in comp)}"); print("CURRENT_FIVE_SCOPE\tPILOT_SUBSET_CANDIDATES"); print("FINAL_RANKING_GATE\tHOLD_COVERAGE_EXPANSION_REQUIRED"); print(f"QC\t{qcp}")
if __name__=="__main__": main()
PY

python -m py_compile "$PY_IMPL"
script_sha256="$(sha256sum "$0" | awk '{print $1}')"
implementation_sha256="$(sha256sum "$PY_IMPL" | awk '{print $1}')"

echo "===== STAGE 6R PREFLIGHT ====="
echo "rnatr-scout version:       $(rnatr-scout version)"
echo "query package:             $(metric "$QUERY_QC" adapter_query_package_status)"
echo "Stage 6M exact source:     $(metric "$STAGE6M_QC" stage6m_reference_1kg_audit_status)"
echo "Stage 6N components:       $(metric "$STAGE6N_QC" stage6n_1kg_genomewide_adapter_status)"
echo "Stage 6Q source:           $(metric "$STAGE6Q_QC" stage6q_multisource_context_status)"
echo "all loci denominator:      $EXPECTED_ALL_LOCI"
echo "current exact loci:        $EXPECTED_EXACT_LOCI"
echo "unmatched loci:            $EXPECTED_UNMATCHED_LOCI"
echo "nearby review window:      ±$NEARBY_BP bp"
echo "motif alphabet:            FULL IUPAC; ambiguous motifs -> manual review"
echo "final ranking:             BLOCKED"
echo "specialized 4,513:         PAUSED"
echo "v0.1.1 failure cause:      PYTHON F-STRING QUOTE SYNTAX ERROR"
echo "v0.1.2 repair:             FULL EMBEDDED PYTHON COMPILE VERIFIED"
echo "implementation sha256:     $implementation_sha256"

RNATR_PROJECT_ROOT="$PROJECT_ROOT" python -m unittest discover -s "$PROJECT_ROOT/tests/unit" -v > "$PROV_ROOT/unit_tests.log" 2>&1
grep -qx OK "$PROV_ROOT/unit_tests.log" || { cat "$PROV_ROOT/unit_tests.log" >&2; echo "ERROR: unit tests failed" >&2; exit 1; }

python "$PY_IMPL" \
  --queries "$QUERIES" \
  --exact-matches "$EXACT_MATCHES" \
  --components "$COMPONENTS" \
  --stage6q-qc "$STAGE6Q_QC" \
  --out-root "$OUT_ROOT" \
  --qc-root "$QC_ROOT" \
  --expected-all-loci "$EXPECTED_ALL_LOCI" \
  --expected-exact-loci "$EXPECTED_EXACT_LOCI" \
  --expected-unmatched-loci "$EXPECTED_UNMATCHED_LOCI" \
  --nearby-bp "$NEARBY_BP" \
  --safe-max-boundary-bp "$SAFE_MAX_BOUNDARY_BP" \
  --safe-min-reciprocal-overlap "$SAFE_MIN_RECIPROCAL_OVERLAP" \
  --script-sha256 "$script_sha256" \
  --implementation-sha256 "$implementation_sha256"

echo
echo "===== STAGE 6R FINAL QC ====="
column -ts $'\t' "$QC_ROOT/repeatcatalogs_crosswalk_coverage_audit.qc.tsv"
echo
echo "===== CROSSWALK TIER DISTRIBUTION ====="
column -ts $'\t' "$SUMMARY_ROOT/crosswalk_tier.distribution.tsv"
echo
echo "===== UNMATCHED REASON DISTRIBUTION ====="
column -ts $'\t' "$SUMMARY_ROOT/unmatched_reason.distribution.tsv"
echo
echo "===== POPULATION COVERAGE PROJECTION ====="
column -ts $'\t' "$SUMMARY_ROOT/population_coverage_projection.tsv"
echo
echo "===== TIERED CROSSWALK POLICY ====="
column -ts $'\t' "$CONTRACT_ROOT/tiered_crosswalk_policy.tsv"
echo
echo "===== COVERAGE GATE POLICY ====="
column -ts $'\t' "$CONTRACT_ROOT/coverage_gate_policy.tsv"
echo
echo "===== EXTERNAL REFERENCE EXPANSION PLAN ====="
column -ts $'\t' "$PLAN_ROOT/population_reference_expansion_plan.tsv"
echo
echo "===== OUTPUT ====="
echo "Audit root:      $OUT_ROOT"
echo "QC:              $QC_ROOT/repeatcatalogs_crosswalk_coverage_audit.qc.tsv"
echo "All-locus audit: $TABLE_ROOT/p01_locus.repeatcatalogs_crosswalk_coverage_audit.tsv.gz"
echo "Safe candidates: $TABLE_ROOT/p01_locus.repeatcatalogs_safe_equivalence_candidates.tsv"
echo "Manual review:   $TABLE_ROOT/p01_locus.repeatcatalogs_manual_review_candidates.tsv.gz"
echo "No catalog:      $TABLE_ROOT/p01_locus.repeatcatalogs_no_catalog_coverage.tsv.gz"
echo "No final ranking or large specialized-motif implementation was run."
