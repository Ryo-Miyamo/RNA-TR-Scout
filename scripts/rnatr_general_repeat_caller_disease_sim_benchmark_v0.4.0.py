#!/usr/bin/env python3
from __future__ import annotations
import argparse, csv, importlib.util, json, math, os, random, statistics, sys, time
from dataclasses import asdict
from pathlib import Path
from collections import Counter, defaultdict

DNA="ACGT"

DISEASE_PANEL = [
    ("C9ORF72","GGGGCC","ALS/FTD","PMC3202986"),
    ("RFC1","AAGGG","CANVAS/RFC1 spectrum","PMC10689911"),
    ("FGF14","GAA","SCA27B/ATX-FGF14","PMC9892775"),
    ("NOTCH2NLC","GGC","NIID-related disorders","PMC6612530"),
    ("DMPK","CTG","DM1","PMC3499739"),
    ("CNBP","CCTG","DM2","PMC3499739"),
    ("NOP56","GGCCTG","SCA36","PMC3135815"),
    ("FMR1","CGG","FMR1 repeat disorders","PMC6619443"),
    ("BEAN1","TGGAA","SCA31 motif component","PMC9606279"),
    ("HTT","CAG","Huntington disease/polyQ model","PMC3907474"),
]

def load_module(path: Path):
    spec=importlib.util.spec_from_file_location("rnatr_v03_bench",path)
    mod=importlib.util.module_from_spec(spec); sys.modules[spec.name]=mod; spec.loader.exec_module(mod)
    return mod

def rand_flank(rng, n):
    # Mild anti-periodicity: random DNA, retry homopolymer-heavy flanks.
    for _ in range(20):
        s="".join(rng.choice(DNA) for _ in range(n))
        if max((s.count(b) for b in DNA), default=0) < 0.45*n:
            return s
    return s

def mutate(seq, rng, sub=0.0, ins=0.0, dele=0.0):
    out=[]
    for b in seq:
        if rng.random() < dele:
            # deleted from observed read
            pass
        else:
            if rng.random() < sub:
                out.append(rng.choice([x for x in DNA if x!=b]))
            else:
                out.append(b)
        if rng.random() < ins:
            out.append(rng.choice(DNA))
    return "".join(out)

def primitive_random_motif(rng, p):
    while True:
        s="".join(rng.choice(DNA) for _ in range(p))
        ok=True
        for d in range(1,p):
            if p%d==0 and s==s[:d]*(p//d):
                ok=False; break
        if ok:
            return s

def percentile(vals,q):
    vals=sorted(float(x) for x in vals)
    if not vals: return float("nan")
    if len(vals)==1: return vals[0]
    x=(len(vals)-1)*q; lo=math.floor(x); hi=math.ceil(x)
    if lo==hi:return vals[lo]
    return vals[lo]*(hi-x)+vals[hi]*(x-lo)

def safe_median(vals):
    vals=[float(x) for x in vals if x is not None and not (isinstance(x,float) and math.isnan(x))]
    return statistics.median(vals) if vals else float("nan")

def write_tsv(path, rows, fields=None):
    path.parent.mkdir(parents=True,exist_ok=True)
    if fields is None:
        fields=list(rows[0].keys()) if rows else []
    tmp=path.with_name("."+path.name+".part")
    with tmp.open("w",newline="",encoding="utf-8") as fh:
        wr=csv.DictWriter(fh,fieldnames=fields,delimiter="\t",extrasaction="ignore")
        wr.writeheader(); wr.writerows(rows)
    os.replace(tmp,path)

def build_cases(mod, seed=20260807):
    rng=random.Random(seed)
    cases=[]
    counter=0
    def add(**kw):
        nonlocal counter
        counter+=1
        kw["case_id"]=f"B{counter:04d}"
        cases.append(kw)

    profiles=[
        ("perfect",0.00,0.00,0.00),
        ("mild",0.025,0.010,0.010),
        ("moderate",0.055,0.020,0.020),
        ("high",0.090,0.035,0.035),
    ]
    exact_lengths=[60,300]
    # Disease-inspired motif panel: exact-boundary cases, catalog-guided.
    for locus,motif,disease,ref in DISEASE_PANEL:
        for bp in exact_lengths:
            units=max(4,math.ceil(bp/len(motif)))
            truth=motif*units
            for pname,sub,ins,dele in [profiles[0],profiles[2],profiles[3]]:
                mrng=random.Random(rng.randrange(1<<62))
                obs=mutate(truth,mrng,sub,ins,dele)
                left=rand_flank(mrng,80); right=rand_flank(mrng,80)
                seq=left+obs+right
                st=len(left); en=st+len(obs)
                add(category="DISEASE_EXACT_BOUNDARY",subtype=pname,locus=locus,disease_context=disease,
                    source_reference=ref,motif=motif,catalog_motif=motif,sequence=seq,prior_start=st,prior_end=en,
                    evidence_geometry="SPAN",sequence_context="FULL_READ",truth_full_repeat_bp=len(obs),
                    truth_observed_repeat_bp=len(obs),truth_underlying_repeat_bp=len(truth),
                    truth_compound="SINGLE_MOTIF",truth_censored="false",support_group_id="",replicate=1)

    # Expansion stress: prior is a short central core, not the full tract.
    for locus,motif,disease,ref in DISEASE_PANEL:
        for bp in [300,900]:
            units=max(6,math.ceil(bp/len(motif))); truth=motif*units
            for pname,sub,ins,dele in [profiles[0]]:
                mrng=random.Random(rng.randrange(1<<62)); obs=mutate(truth,mrng,sub,ins,dele)
                left=rand_flank(mrng,100); right=rand_flank(mrng,100); seq=left+obs+right
                full_st=len(left); full_en=full_st+len(obs)
                core=max(3*len(motif),min(60,len(obs)//3))
                mid=(full_st+full_en)//2; st=max(full_st,mid-core//2); en=min(full_en,st+core)
                add(category="EXPANSION_STRESS_SHORT_PRIOR",subtype=pname,locus=locus,disease_context=disease,
                    source_reference=ref,motif=motif,catalog_motif=motif,sequence=seq,prior_start=st,prior_end=en,
                    evidence_geometry="SPAN",sequence_context="FULL_READ",truth_full_repeat_bp=len(obs),
                    truth_observed_repeat_bp=len(obs),truth_underlying_repeat_bp=len(truth),
                    truth_compound="SINGLE_MOTIF",truth_censored="false",support_group_id="",replicate=1)

    # Explicit censoring semantics.
    for locus,motif,disease,ref in DISEASE_PANEL[:4]:
        units=max(12,math.ceil(300/len(motif))); full=motif*units
        for geom in ["LEFT_CENSORED","RIGHT_CENSORED","BOTH_CENSORED"]:
            mrng=random.Random(rng.randrange(1<<62)); full_obs=mutate(full,mrng,0.04,0.015,0.015)
            n=len(full_obs)
            if geom=="LEFT_CENSORED":
                obs=full_obs[n//3:]; right=rand_flank(mrng,80); seq=obs+right; st=0; en=len(obs)
            elif geom=="RIGHT_CENSORED":
                obs=full_obs[:2*n//3]; left=rand_flank(mrng,80); seq=left+obs; st=len(left); en=len(seq)
            else:
                obs=full_obs[n//3:2*n//3]; seq=obs; st=0; en=len(obs)
            add(category="CENSORED",subtype=geom,locus=locus,disease_context=disease,source_reference=ref,
                motif=motif,catalog_motif=motif,sequence=seq,prior_start=st,prior_end=en,
                evidence_geometry=geom,sequence_context="FULL_READ",truth_full_repeat_bp=len(full_obs),
                truth_observed_repeat_bp=len(obs),truth_underlying_repeat_bp=len(full),
                truth_compound="SINGLE_MOTIF",truth_censored="true",support_group_id="",replicate=1)

    # Projection-window context edge: not biological censoring.
    for motif in ["CAG","AAGGG","GGGGCC","TGGAA"]:
        mrng=random.Random(rng.randrange(1<<62)); truth=motif*30
        obs=mutate(truth,mrng,0.03,0.01,0.01); seq=obs+rand_flank(mrng,60)
        add(category="PROJECTION_CONTEXT",subtype="LEFT_CONTEXT_EDGE",locus="GENERIC",disease_context="",
            source_reference="",motif=motif,catalog_motif=motif,sequence=seq,prior_start=0,prior_end=len(obs),
            evidence_geometry="SPAN",sequence_context="PROJECTION_WINDOW",truth_full_repeat_bp=len(obs),
            truth_observed_repeat_bp=len(obs),truth_underlying_repeat_bp=len(truth),
            truth_compound="SINGLE_MOTIF",truth_censored="false",support_group_id="",replicate=1)

    # De-novo, no catalog, spanning motif sizes through 50.
    for p in [1,3,5,6,12,20,37,50]:
        motif = ("A" if p==1 else primitive_random_motif(rng,p))
        for pname,sub,ins,dele in [profiles[0]]:
            mrng=random.Random(rng.randrange(1<<62)); truth=motif*max(8,math.ceil(240/p))
            obs=mutate(truth,mrng,sub,ins,dele); left=rand_flank(mrng,70); right=rand_flank(mrng,70)
            seq=left+obs+right; st=len(left); en=st+len(obs)
            add(category="DENOVO",subtype=f"period_{p}_{pname}",locus="GENERIC_DENOVO",disease_context="",
                source_reference="",motif=motif,catalog_motif="",sequence=seq,prior_start=st,prior_end=en,
                evidence_geometry="SPAN",sequence_context="FULL_READ",truth_full_repeat_bp=len(obs),
                truth_observed_repeat_bp=len(obs),truth_underlying_repeat_bp=len(truth),
                truth_compound="SINGLE_MOTIF",truth_censored="false",support_group_id="",replicate=1)

    # Interrupted single motif.
    for motif in ["CAG","CGG","CTG","GGC"]:
        for gap in ["TTAACCGG"]:
            mrng=random.Random(rng.randrange(1<<62)); a=motif*15; b=motif*15
            tract=a+gap+b; left=rand_flank(mrng,80); right=rand_flank(mrng,80); seq=left+tract+right
            st=len(left); en=st+len(tract)
            add(category="INTERRUPTION",subtype=f"gap_{len(gap)}",locus="GENERIC_INTERRUPTED",disease_context="",
                source_reference="",motif=motif,catalog_motif=motif,sequence=seq,prior_start=st,prior_end=en,
                evidence_geometry="SPAN",sequence_context="FULL_READ",truth_full_repeat_bp=len(tract),
                truth_observed_repeat_bp=len(tract),truth_underlying_repeat_bp=len(tract),
                truth_compound="INTERRUPTED_SINGLE_MOTIF",truth_censored="false",support_group_id="",replicate=1)

    # Compound motifs (including SCA31/RFC1-inspired alternatives, used as sequence-shape tests only).
    compounds=[("TGGAA","TAGAA","BEAN1_SHAPE"),("AAGGG","AAAGG","RFC1_SHAPE"),
               ("CAG","CAA","POLYQ_SHAPE"),("GGCCTG","GGCTTG","HEX_SHAPE")]
    for m1,m2,label in compounds:
        for reps in [(12,12)]:
            mrng=random.Random(rng.randrange(1<<62)); tract=m1*reps[0]+m2*reps[1]
            left=rand_flank(mrng,80); right=rand_flank(mrng,80); seq=left+tract+right; st=len(left); en=st+len(tract)
            add(category="COMPOUND",subtype=label,locus="GENERIC_COMPOUND",disease_context="",
                source_reference="",motif=m1,catalog_motif=f"{m1},{m2}",sequence=seq,prior_start=st,prior_end=en,
                evidence_geometry="SPAN",sequence_context="FULL_READ",truth_full_repeat_bp=len(tract),
                truth_observed_repeat_bp=len(tract),truth_underlying_repeat_bp=len(tract),
                truth_compound="COMPOUND",truth_censored="false",support_group_id="",replicate=1)

    # Support groups: five molecules per truth, moderate errors.
    for locus,motif in [("HTT","CAG"),("RFC1","AAGGG")]:
        truth=motif*max(12,math.ceil(300/len(motif)))
        gid=f"SUPPORT5_{locus}"
        for rep in range(1,6):
            mrng=random.Random(rng.randrange(1<<62)); obs=mutate(truth,mrng,0.06,0.02,0.02)
            left=rand_flank(mrng,80); right=rand_flank(mrng,80); seq=left+obs+right; st=len(left); en=st+len(obs)
            add(category="SUPPORT_STABILITY",subtype="moderate_error",locus=locus,disease_context="",
                source_reference="",motif=motif,catalog_motif=motif,sequence=seq,prior_start=st,prior_end=en,
                evidence_geometry="SPAN",sequence_context="FULL_READ",truth_full_repeat_bp=len(obs),
                truth_observed_repeat_bp=len(obs),truth_underlying_repeat_bp=len(truth),
                truth_compound="SINGLE_MOTIF",truth_censored="false",support_group_id=gid,replicate=rep)
    return cases

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--caller",type=Path,required=True)
    ap.add_argument("--outdir",type=Path,required=True)
    args=ap.parse_args()
    mod=load_module(args.caller); outdir=args.outdir; outdir.mkdir(parents=True,exist_ok=True)
    cases=build_cases(mod)
    panel_rows=[{"locus":a,"motif":b,"context":c,"source_reference":d,
                 "benchmark_semantics":"MOTIF_SHAPE_ONLY_NO_DISEASE_THRESHOLD"} for a,b,c,d in DISEASE_PANEL]
    write_tsv(outdir/"disease_inspired_motif_panel.tsv",panel_rows)

    call_rows=[]; runtimes=[]
    for case in cases:
        motifs=[x for x in case["catalog_motif"].split(",") if x]
        t0=time.perf_counter()
        try:
            c=mod.call_repeat(case["sequence"],int(case["prior_start"]),int(case["prior_end"]),motifs,
                              evidence_geometry=case["evidence_geometry"],sequence_context=case["sequence_context"])
            elapsed=time.perf_counter()-t0
            d=asdict(c); err=""
        except Exception as e:
            elapsed=time.perf_counter()-t0
            d={}; err=f"{type(e).__name__}:{e}"
        runtimes.append(elapsed)
        truth_canon=mod.canonical_motif(case["motif"])
        called=d.get("canonical_motif","")
        motif_ok=(called==truth_canon)
        exact=d.get("exact_repeat_bp")
        lower=d.get("lower_bound_bp")
        abs_err=abs(exact-case["truth_observed_repeat_bp"]) if isinstance(exact,int) else None
        rel_err=(abs_err/max(1,case["truth_observed_repeat_bp"])) if abs_err is not None else None
        call_rows.append({
            **{k:v for k,v in case.items() if k!="sequence"},
            "sequence_length_bp":len(case["sequence"]),
            "truth_canonical_motif":truth_canon,
            "caller_completed":str(not bool(err)).lower(),
            "error":err,
            "called_canonical_motif":called,
            "motif_correct":str(motif_ok).lower() if not err else "false",
            "call_status":d.get("call_status",""),
            "sizing_status":d.get("sizing_status",""),
            "exact_repeat_bp":"" if exact is None else exact,
            "lower_bound_bp":"" if lower is None else lower,
            "interval_upper_bp":"" if d.get("interval_upper_bp") is None else d.get("interval_upper_bp"),
            "repeat_bp_observed":d.get("repeat_bp_observed",""),
            "abs_exact_length_error_bp":"" if abs_err is None else abs_err,
            "relative_exact_length_error":"" if rel_err is None else rel_err,
            "compound_status":d.get("compound_status",""),
            "interruption_count":d.get("interruption_count",""),
            "lps_exact_sequence_bp":d.get("lps_exact_sequence_bp",""),
            "lps_inferred_bp":d.get("lps_inferred_bp",""),
            "prior_overlap_bp":d.get("prior_overlap_bp",""),
            "context_limited":d.get("context_limited",""),
            "motif_source":d.get("motif_source",""),
            "hypothesis_count":d.get("hypothesis_count",""),
            "runtime_ms":elapsed*1000,
        })
    write_tsv(outdir/"simulation_cases.tsv",cases)
    write_tsv(outdir/"simulation_calls.tsv",call_rows)

    complete=[r for r in call_rows if r["caller_completed"]=="true"]
    exactcat=[r for r in complete if r["category"]=="DISEASE_EXACT_BOUNDARY"]
    exact_lowmod=[r for r in exactcat if r["subtype"] in {"perfect","mild","moderate"}]
    soft=[r for r in complete if r["category"]=="EXPANSION_STRESS_SHORT_PRIOR"]
    cens=[r for r in complete if r["category"]=="CENSORED"]
    context=[r for r in complete if r["category"]=="PROJECTION_CONTEXT"]
    denovo=[r for r in complete if r["category"]=="DENOVO"]
    intr=[r for r in complete if r["category"]=="INTERRUPTION"]
    comp=[r for r in complete if r["category"]=="COMPOUND"]

    def frac(rows,pred):
        return sum(1 for r in rows if pred(r))/len(rows) if rows else float("nan")
    def vals(rows,key):
        out=[]
        for r in rows:
            x=r.get(key,"")
            if x=="" or x is None: continue
            out.append(float(x))
        return out

    # Support aggregation: median exact call across 5 molecules vs truth median observed length.
    support_summary=[]
    groups=defaultdict(list)
    for r in complete:
        if r["support_group_id"]:
            groups[r["support_group_id"]].append(r)
    for gid,g in sorted(groups.items()):
        exacts=[float(r["exact_repeat_bp"]) for r in g if r["exact_repeat_bp"]!=""]
        truths=[float(r["truth_observed_repeat_bp"]) for r in g]
        single=[float(r["abs_exact_length_error_bp"]) for r in g if r["abs_exact_length_error_bp"]!=""]
        support_summary.append({
            "support_group_id":gid,"n":len(g),"single_read_abs_error_median_bp":safe_median(single),
            "median_call_bp":safe_median(exacts),"median_truth_observed_bp":safe_median(truths),
            "median_of_5_abs_error_bp":abs(safe_median(exacts)-safe_median(truths)) if exacts else "",
        })
    write_tsv(outdir/"support_stability_summary.tsv",support_summary)

    runtime_by_cat=[]
    for cat in sorted(set(r["category"] for r in complete)):
        g=[r for r in complete if r["category"]==cat]
        rv=vals(g,"runtime_ms")
        runtime_by_cat.append({"category":cat,"n":len(g),"runtime_ms_median":safe_median(rv),"runtime_ms_p95":percentile(rv,.95)})
    write_tsv(outdir/"runtime_by_category.tsv",runtime_by_cat)

    # Expansion-stress recovery fraction: called observed tract / true observed tract.
    for r in soft:
        try: r["_recovery"]=float(r["repeat_bp_observed"])/max(1,float(r["truth_observed_repeat_bp"]))
        except: r["_recovery"]=float("nan")

    metrics=[
        ("stage_version","rnatr_general_repeat_caller_disease_sim_benchmark_v0.4.0"),
        ("caller_version",getattr(mod,"CALLER_VERSION","unknown")),
        ("fixture_count",len(cases)),
        ("caller_completed_rows",len(complete)),
        ("completion_fraction",len(complete)/len(cases)),
        ("disease_inspired_loci",len(DISEASE_PANEL)),
        ("disease_exact_boundary_rows",len(exactcat)),
        ("disease_exact_boundary_motif_accuracy",frac(exactcat,lambda r:r["motif_correct"]=="true")),
        ("disease_exact_boundary_pass_fraction",frac(exactcat,lambda r:r["call_status"]=="PASS")),
        ("disease_exact_boundary_abs_error_median_bp",safe_median(vals(exactcat,"abs_exact_length_error_bp"))),
        ("disease_exact_boundary_abs_error_p95_bp",percentile(vals(exactcat,"abs_exact_length_error_bp"),.95)),
        ("disease_exact_boundary_relative_error_median",safe_median(vals(exactcat,"relative_exact_length_error"))),
        ("disease_exact_boundary_relative_error_p95",percentile(vals(exactcat,"relative_exact_length_error"),.95)),
        ("disease_exact_lowmoderate_motif_accuracy",frac(exact_lowmod,lambda r:r["motif_correct"]=="true")),
        ("disease_exact_lowmoderate_relative_error_p95",percentile(vals(exact_lowmod,"relative_exact_length_error"),.95)),
        ("expansion_stress_rows",len(soft)),
        ("expansion_stress_recovery_fraction_median",safe_median([r["_recovery"] for r in soft])),
        ("expansion_stress_recovery_fraction_p10",percentile([r["_recovery"] for r in soft],.10)),
        ("censored_rows",len(cens)),
        ("censored_no_exact_fraction",frac(cens,lambda r:r["exact_repeat_bp"]=="")),
        ("censored_lower_bound_present_fraction",frac(cens,lambda r:r["lower_bound_bp"]!="")),
        ("censored_no_invented_upper_bound_fraction",frac(cens,lambda r:r["interval_upper_bp"]=="")),
        ("censored_lower_bound_not_exceed_full_truth_fraction",frac(cens,lambda r:r["lower_bound_bp"]!="" and float(r["lower_bound_bp"])<=float(r["truth_full_repeat_bp"]))),
        ("projection_context_rows",len(context)),
        ("projection_context_limited_fraction",frac(context,lambda r:str(r["context_limited"]).lower()=="true")),
        ("denovo_rows",len(denovo)),
        ("denovo_motif_accuracy",frac(denovo,lambda r:r["motif_correct"]=="true")),
        ("denovo_pass_fraction",frac(denovo,lambda r:r["call_status"]=="PASS")),
        ("compound_rows",len(comp)),
        ("compound_classification_fraction",frac(comp,lambda r:r["compound_status"]=="COMPOUND")),
        ("interruption_rows",len(intr)),
        ("interruption_classification_fraction",frac(intr,lambda r:r["compound_status"]=="INTERRUPTED_SINGLE_MOTIF")),
        ("all_completed_calls_overlap_prior_fraction",frac(complete,lambda r:str(r["prior_overlap_bp"]) not in {"","None"} and float(r["prior_overlap_bp"])>0)),
        ("support_group_count",len(support_summary)),
        ("support_single_read_abs_error_median_bp",safe_median([r["single_read_abs_error_median_bp"] for r in support_summary])),
        ("support_median_of_5_abs_error_median_bp",safe_median([r["median_of_5_abs_error_bp"] for r in support_summary])),
        ("runtime_total_seconds",sum(runtimes)),
        ("runtime_per_call_median_ms",safe_median([x*1000 for x in runtimes])),
        ("runtime_per_call_p95_ms",percentile([x*1000 for x in runtimes],.95)),
        ("benchmark_semantics","CALLER_MEASUREMENT_BENCHMARK_NOT_PATHOGENICITY_NOT_POPULATION_CALIBRATION"),
    ]
    md=dict(metrics)
    invariant_pass = (
        md["completion_fraction"]==1.0 and
        md["censored_no_exact_fraction"]==1.0 and
        md["censored_lower_bound_present_fraction"]==1.0 and
        md["censored_no_invented_upper_bound_fraction"]==1.0 and
        md["censored_lower_bound_not_exceed_full_truth_fraction"]==1.0 and
        md["all_completed_calls_overlap_prior_fraction"]==1.0
    )
    core_pass = md["disease_exact_lowmoderate_motif_accuracy"] >= 0.95
    expansion_pass = (
        md["expansion_stress_recovery_fraction_median"] >= 0.90 and
        md["expansion_stress_recovery_fraction_p10"] >= 0.80
    )
    audit="PASS" if invariant_pass and core_pass and expansion_pass else "REVIEW"
    metrics += [
        ("semantic_invariants_status","PASS" if invariant_pass else "FAIL"),
        ("catalog_guided_core_status","PASS" if core_pass else "REVIEW"),
        ("expansion_stress_status","PASS" if expansion_pass else "REVIEW"),
        ("accuracy_threshold_scope","CATALOG_GUIDED_LOW_TO_MODERATE_ERROR_MOTIF_IDENTITY_AND_SHORT_PRIOR_EXPANSION_RECOVERY_ARE_GATED; OTHER_METRICS_DESCRIPTIVE"),
        ("pathogenicity_assessed","false"),
        ("population_normal_range_estimated","false"),
        ("next_gate","INTERPRET_BENCHMARK_FAILURE_MODES_THEN_FREEZE_GENERAL_CALLER_OR_PATCH_V0.4"),
        ("audit_status",audit),
    ]
    qrows=[{"metric":k,"value":v} for k,v in metrics]
    write_tsv(outdir/"disease_sim_benchmark.qc.tsv",qrows,["metric","value"])

    # Summary by disease locus for exact-boundary cases.
    locrows=[]
    for locus in sorted(set(r["locus"] for r in exactcat)):
        g=[r for r in exactcat if r["locus"]==locus]
        locrows.append({
            "locus":locus,"n":len(g),"motif_accuracy":frac(g,lambda r:r["motif_correct"]=="true"),
            "pass_fraction":frac(g,lambda r:r["call_status"]=="PASS"),
            "abs_error_median_bp":safe_median(vals(g,"abs_exact_length_error_bp")),
            "abs_error_p95_bp":percentile(vals(g,"abs_exact_length_error_bp"),.95),
            "relative_error_p95":percentile(vals(g,"relative_exact_length_error"),.95),
        })
    write_tsv(outdir/"disease_locus_summary.tsv",locrows)

    print("===== DISEASE-INSPIRED + BROAD SIMULATION BENCHMARK =====")
    for k,v in metrics: print(f"{k}\t{v}")
    if audit!="PASS":
        raise SystemExit(3)

if __name__=="__main__":
    main()
