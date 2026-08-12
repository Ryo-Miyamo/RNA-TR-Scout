from __future__ import annotations
import argparse, csv, gzip, importlib.util, json, math, multiprocessing as mp
import os, statistics, sys, time
from dataclasses import asdict
from pathlib import Path
import pysam

CALLER=None

SUPPORTED_STRATEGIES={
    "SIMPLE_PERIODIC_SCAN",
    "MULTI_MOTIF_PERIODIC_SCAN",
    "LONG_UNIT_21_TO_100_PERIODIC_SCAN",
}
DNA=set("ACGT")

def load_caller(path:Path):
    spec=importlib.util.spec_from_file_location("rnatr_general_v040_integration",path)
    mod=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=mod
    spec.loader.exec_module(mod)
    return mod

def init_worker(caller_path):
    global CALLER
    CALLER=load_caller(Path(caller_path))

def geometry_for_call(geometry,strand):
    if geometry=="BOTH_FLANKS_PROJECTABLE":
        return "SPAN"
    if geometry in {"LEFT_FLANK_ONLY","PROXIMAL_RIGHT_WITH_SOFTCLIP"}:
        return "RIGHT_CENSORED" if strand=="+" else "LEFT_CENSORED"
    if geometry in {"RIGHT_FLANK_ONLY","PROXIMAL_LEFT_WITH_SOFTCLIP"}:
        return "LEFT_CENSORED" if strand=="+" else "RIGHT_CENSORED"
    return "UNKNOWN"

def split_motifs(text):
    if not text or text==".":
        return []
    out=[]
    for x in text.split(","):
        x=x.strip().upper()
        if x and set(x)<=DNA and x not in out:
            out.append(x)
    return out

def worker(task):
    idx,job,proj,seq=task
    out={"_idx":idx,"integration_status":"."}
    strategy=job["scan_strategy"]
    if strategy not in SUPPORTED_STRATEGIES:
        out["integration_status"]="NOT_ATTEMPTED_UNSUPPORTED_STRATEGY"
        return out
    if seq is None:
        out["integration_status"]="NOT_ATTEMPTED_NO_WINDOW_SEQUENCE"
        return out
    ps=proj.get("projected_target_read_start",".")
    pe=proj.get("projected_target_read_end",".")
    ws=proj.get("candidate_window_read_start",".")
    if ps in {"",".",None} or pe in {"",".",None} or ws in {"",".",None}:
        out["integration_status"]="NOT_ATTEMPTED_NO_PROJECTED_TARGET"
        return out
    ps=int(ps);pe=int(pe);ws=int(ws)
    local_start=ps-ws;local_end=pe-ws
    if not (0<=local_start<local_end<=len(seq)):
        out["integration_status"]="NOT_ATTEMPTED_INVALID_LOCAL_PRIOR"
        return out
    motifs=split_motifs(job.get("canonical_motifs","."))
    if not motifs:
        out["integration_status"]="NOT_ATTEMPTED_NO_ACGT_CATALOG_MOTIF"
        return out
    geom=geometry_for_call(proj["geometry_class"],proj["strand"])
    try:
        call=CALLER.call_repeat(
            seq,
            local_start,
            local_end,
            motifs,
            evidence_geometry=geom,
            sequence_context="PROJECTION_WINDOW",
        )
    except Exception as e:
        out["integration_status"]="CALLER_ERROR"
        out["caller_error"]=f"{type(e).__name__}:{e}"
        return out
    d=asdict(call)
    out.update(d)
    out["integration_status"]="CALLED"
    out["local_prior_start"]=local_start
    out["local_prior_end"]=local_end
    out["raw_prior_start"]=ps
    out["raw_prior_end"]=pe
    out["raw_tract_start"]=ws+d["read_start"]
    out["raw_tract_end"]=ws+d["read_end"]
    return out

def read_gz_tsv(path):
    with gzip.open(path,"rt",encoding="utf-8",newline="") as f:
        return list(csv.DictReader(f,delimiter="\t"))

def q(vals,p):
    vals=sorted(float(x) for x in vals)
    if not vals:return float("nan")
    if len(vals)==1:return vals[0]
    x=(len(vals)-1)*p;lo=math.floor(x);hi=math.ceil(x)
    if lo==hi:return vals[lo]
    return vals[lo]*(hi-x)+vals[hi]*(x-lo)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--project-root",type=Path,required=True)
    ap.add_argument("--outdir",type=Path,required=True)
    ap.add_argument("--workers",type=int,default=16)
    args=ap.parse_args()
    P=args.project_root
    run="ENCSR307SHM_pilot100k_mm2splice_v1"
    jobs_p=P/"results/11_motif_jobs"/run/"motif_scan_jobs.tsv.gz"
    proj_p=P/"results/11_projection"/run/"v0.3.3/read_target_projection.v0.3.3.tsv.gz"
    caller_p=Path('/mnt/intelssd/rnatr_project/src/rnatr_scout/general_caller/native_v0.4.1/rnatr_general_repeat_caller_ref_v0.4.1.py')
    env=(P/"config/paths.env").read_text(encoding="utf-8")
    import re
    m=re.search(r'^\s*(?:export\s+)?RAW_ROOT=(?:"|\')?([^"\']+)',env,re.M)
    if not m: raise SystemExit("RAW_ROOT not found")
    raw=Path(os.path.expandvars(os.path.expanduser(m.group(1).strip())))
    windows_p=raw/"benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_projection_v0.3.3/ENCFF260PGB.pilot_100k.rnatr_target_windows.v0.3.3.fastq.gz"
    for p in [jobs_p,proj_p,caller_p,windows_p]:
        if not p.is_file(): raise SystemExit(f"missing input: {p}")

    args.outdir.mkdir(parents=True,exist_ok=True)
    t0=time.perf_counter()
    jobs=read_gz_tsv(jobs_p)
    projections=read_gz_tsv(proj_p)
    table_load=time.perf_counter()-t0

    if len(jobs)!=len(projections):
        raise SystemExit(f"job/projection row mismatch {len(jobs)} {len(projections)}")
    pj={r["projection_id"]:r for r in projections}
    if len(pj)!=len(projections): raise SystemExit("duplicate projection_id in projection")
    if len({r["projection_id"] for r in jobs})!=len(jobs): raise SystemExit("duplicate projection_id in jobs")

    supported_ids={
        r["projection_id"] for r in jobs
        if r["scan_strategy"] in SUPPORTED_STRATEGIES
        and split_motifs(r.get("canonical_motifs","."))
    }
    seq={}
    scanned=0
    t1=time.perf_counter()
    with pysam.FastxFile(str(windows_p)) as f:
        for e in f:
            scanned+=1
            if e.name in supported_ids:
                seq[e.name]=e.sequence.upper()
    fastq_s=time.perf_counter()-t1

    tasks=[]
    for i,j in enumerate(jobs):
        pr=pj[j["projection_id"]]
        tasks.append((i,j,pr,seq.get(j["projection_id"])))

    t2=time.perf_counter()
    ctx=mp.get_context("fork")
    chunks=max(1,len(tasks)//(args.workers*32))
    with ctx.Pool(args.workers,initializer=init_worker,initargs=(str(caller_p),)) as pool:
        results=list(pool.imap(worker,tasks,chunksize=chunks))
    caller_wall=time.perf_counter()-t2
    results.sort(key=lambda x:x["_idx"])

    call_fields=list(load_caller(caller_p).Call.__dataclass_fields__)
    base_fields=[
        "projection_id","read_id","target_region_id","target_source","region_type",
        "representative_locus_id","assignment_rank","read_candidate_target_count",
        "scan_priority","scan_strategy","geometry_class","potential_evidence_class",
        "strand","best_mapq","catalog_motifs","candidate_window_read_start",
        "candidate_window_read_end","projected_target_read_start","projected_target_read_end",
        "integration_status","caller_error","local_prior_start","local_prior_end",
        "raw_prior_start","raw_prior_end","raw_tract_start","raw_tract_end",
    ]
    fields=base_fields+call_fields
    out_p=args.outdir/"general_repeat_calls.v0.4.0.tsv.gz"
    with gzip.open(out_p,"wt",compresslevel=1,encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,delimiter="\t",lineterminator="\n",extrasaction="ignore")
        w.writeheader()
        for j,r in zip(jobs,results):
            pr=pj[j["projection_id"]]
            row={
                "projection_id":j["projection_id"],"read_id":j["read_id"],
                "target_region_id":j["target_region_id"],"target_source":j["target_source"],
                "region_type":j["region_type"],"representative_locus_id":j["representative_locus_id"],
                "assignment_rank":j["assignment_rank"],"read_candidate_target_count":j["read_candidate_target_count"],
                "scan_priority":j["scan_priority"],"scan_strategy":j["scan_strategy"],
                "geometry_class":j["geometry_class"],"potential_evidence_class":j["potential_evidence_class"],
                "strand":pr["strand"],"best_mapq":pr["best_mapq"],"catalog_motifs":j["canonical_motifs"],
                "candidate_window_read_start":pr["candidate_window_read_start"],
                "candidate_window_read_end":pr["candidate_window_read_end"],
                "projected_target_read_start":pr["projected_target_read_start"],
                "projected_target_read_end":pr["projected_target_read_end"],
            }
            row.update(r)
            row.pop("_idx",None)
            for k in fields:
                if row.get(k) is None or row.get(k)=="":
                    row[k]="."
                elif isinstance(row.get(k),bool):
                    row[k]=str(row[k]).lower()
            w.writerow(row)

    status={}
    for r in results: status[r["integration_status"]]=status.get(r["integration_status"],0)+1
    called=[r for r in results if r["integration_status"]=="CALLED"]
    errors=status.get("CALLER_ERROR",0)
    prior_bad=sum(int(r.get("prior_overlap_bp",0))<=0 for r in called)
    context=sum(bool(r.get("context_limited",False)) for r in called)
    exact=sum(r.get("sizing_status")=="EXACT_SPAN" for r in called)
    lower=sum(str(r.get("sizing_status","")).startswith("LOWER_BOUND") or r.get("sizing_status")=="CONTEXT_LIMITED_LOWER_BOUND" for r in called)

    summary=[
        ("stage_version","rnatr_stage15a_native_v041_no_legacy_audit_v0.2.0"),
        ("scientific_caller_version","rnatr_general_repeat_caller_ref_v0.4.1"),
        ("legacy_11f_11h_bridge_audit_executed","false"),
        ("legacy_11f_11h_bridge_role","AUDIT_ONLY_NOT_CALL_INPUT"),
        ("workers",args.workers),
        ("input_job_rows",len(jobs)),
        ("input_projection_rows",len(projections)),
        ("window_fastq_records_scanned",scanned),
        ("supported_projection_ids",len(supported_ids)),
        ("window_sequences_loaded",len(seq)),
        ("called_rows",len(called)),
        ("caller_error_rows",errors),
        ("called_prior_overlap_nonpositive_rows",prior_bad),
        ("exact_span_rows",exact),
        ("lower_bound_or_context_limited_rows",lower),
        ("context_limited_rows",context),
        ("table_load_seconds",table_load),
        ("window_fastq_scan_seconds",fastq_s),
        ("caller_parallel_wall_seconds",caller_wall),
        ("caller_parallel_minutes",caller_wall/60),
        ("jobs_per_second",len(tasks)/caller_wall),
        ("production_outputs_modified","false"),
        ("comparison_semantics","SCIENTIFIC_CALL_OUTPUT_ONLY_LEGACY_BRIDGE_AUDIT_OMITTED"),
        ("audit_status","PASS" if errors==0 else "FAIL"),
    ]
    qc_p=args.outdir/"general_repeat_integration.qc.tsv"
    with qc_p.open("w",encoding="utf-8",newline="") as f:
        w=csv.writer(f,delimiter="\t");w.writerow(["metric","value"]);w.writerows(summary)
        for k in sorted(status): w.writerow([f"integration_status::{k}",status[k]])

    print("===== STAGE 14B GENERAL CALLER 100K INTEGRATION =====")
    for k,v in summary: print(f"{k}\t{v}")
    print("output\t"+str(out_p))
    return 0 if errors==0 else 2

if __name__=="__main__":
    raise SystemExit(main())
