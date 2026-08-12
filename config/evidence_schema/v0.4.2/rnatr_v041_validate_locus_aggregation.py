#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,gzip,re
from pathlib import Path

MISSING={"",".","NA","N/A","None","null","nan"}

def present(v):return v not in MISSING
def read(path):
    if not path.exists():return None
    op=gzip.open if path.suffix==".gz" else open
    with op(path,"rt",encoding="utf-8",newline="") as f:return list(csv.DictReader(f,delimiter="\t"))
def as_bool(v,label):
    if v=="true":return True
    if v=="false":return False
    raise SystemExit(f"invalid boolean {label}={v!r}")
def require_unique(rows,key,label):
    vals=[r[key] for r in rows]
    if len(vals)!=len(set(vals)):raise SystemExit(f"duplicate {label} {key}")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--package-dir",type=Path,required=True)
    args=ap.parse_args();d=args.package_dir

    paths={
      "events":d/"repeat_events.tsv",
      "distributions":d/"locus_repeat_distributions.tsv",
      "clusters":d/"repeat_length_clusters.tsv",
      "memberships":d/"repeat_length_cluster_membership.tsv",
    }
    for key,p in list(paths.items()):
        gz=Path(str(p)+".gz")
        if not p.exists() and gz.exists():paths[key]=gz

    aggregate_present=[paths[k].exists() for k in ["distributions","clusters","memberships"]]
    if not any(aggregate_present):
        print("RNATR_V041_LOCUS_AGGREGATION_NOT_RUN_PASS");return
    if not all(aggregate_present):raise SystemExit("partial locus-aggregation package is forbidden")
    if not paths["events"].exists():raise SystemExit("repeat_events required when clustering tables are present")

    events=read(paths["events"]) or []
    distributions=read(paths["distributions"]) or []
    clusters=read(paths["clusters"]) or []
    memberships=read(paths["memberships"]) or []

    require_unique(events,"repeat_event_id","repeat_events")
    require_unique(distributions,"locus_distribution_id","locus_repeat_distributions")
    require_unique(clusters,"repeat_length_cluster_id","repeat_length_clusters")
    require_unique(memberships,"cluster_membership_id","repeat_length_cluster_membership")

    event_by={r["repeat_event_id"]:r for r in events}
    dist_by={r["locus_distribution_id"]:r for r in distributions}
    cluster_by={r["repeat_length_cluster_id"]:r for r in clusters}

    for r in distributions:
        if not r["locus_distribution_id"].startswith("RLD_"):raise SystemExit("locus_distribution_id must use RLD_ prefix")
        if r.get("read_level_distribution_preserved")!="true":raise SystemExit("read-level distribution preservation must be true")
        if r["cluster_analysis_status"]=="NOT_RUN" and r["distribution_status"]=="CLUSTERING_COMPLETE":raise SystemExit("NOT_RUN cannot be CLUSTERING_COMPLETE")

    for r in clusters:
        if not r["repeat_length_cluster_id"].startswith("RLC_"):raise SystemExit("repeat_length_cluster_id must use RLC_ prefix")
        if r["locus_distribution_id"] not in dist_by:raise SystemExit("cluster distribution FK failure")
        if r["locus_id"]!=dist_by[r["locus_distribution_id"]]["locus_id"]:raise SystemExit("cluster/distribution locus mismatch")
        semantics=r["cluster_semantics"];phase=r["phase_status"]
        hap=present(r.get("haplotype_id","."));allele=present(r.get("allele_label","."))
        if semantics=="UNPHASED_LENGTH_CLUSTER":
            if phase!="UNPHASED" or hap or allele:raise SystemExit("unphased cluster cannot carry haplotype/allele semantics")
            if not re.fullmatch(r"C[1-9][0-9]*",r["cluster_label"]):raise SystemExit("unphased label must be C1/C2/...")
        if hap or allele:
            if phase not in {"SNP_PHASED","MATCHED_DNA_SUPPORTED","ORTHOGONAL_SUPPORTED"}:raise SystemExit("haplotype/allele label requires phase support")
            if semantics=="UNPHASED_LENGTH_CLUSTER":raise SystemExit("allele label forbidden for unphased cluster")
        if semantics=="SNP_PHASED_HAPLOTYPE_CLUSTER" and phase!="SNP_PHASED":raise SystemExit("SNP phased semantics require SNP_PHASED")
        if semantics=="MATCHED_DNA_SUPPORTED_ALLELE_CLUSTER" and phase not in {"MATCHED_DNA_SUPPORTED","ORTHOGONAL_SUPPORTED"}:raise SystemExit("DNA-supported allele semantics lack support")

    for r in memberships:
        if not r["cluster_membership_id"].startswith("RLM_"):raise SystemExit("cluster_membership_id must use RLM_ prefix")
        if r["repeat_event_id"] not in event_by:raise SystemExit("membership repeat_event FK failure")
        if r["repeat_length_cluster_id"] not in cluster_by:raise SystemExit("membership cluster FK failure")
        event=event_by[r["repeat_event_id"]];cluster=cluster_by[r["repeat_length_cluster_id"]]
        if r["locus_id"]!=event["locus_id"] or r["locus_id"]!=cluster["locus_id"]:raise SystemExit("membership locus mismatch")
        mtype=r["length_measurement_type"];status=r["membership_status"];used=as_bool(r["used_for_fit"],"used_for_fit")
        if mtype=="EXACT" and event.get("sizing_status")!="exact_span":raise SystemExit("EXACT membership points to non-exact event")
        if mtype!="EXACT" and status=="FIT_EXACT":raise SystemExit("censored/context-limited event cannot be FIT_EXACT")
        if mtype=="CONTEXT_LIMITED_LOWER_BOUND" and used:raise SystemExit("context-limited event cannot be used for fit")
        if used and mtype!="EXACT":
            if cluster["censor_handling_method"]!="CENSOR_AWARE_INTERVAL_LIKELIHOOD":raise SystemExit("censored fit requires explicit censor-aware method")
            if status not in {"CENSORED_COMPATIBLE","CENSORED_AMBIGUOUS"}:raise SystemExit("invalid censored fit membership status")
        if not used and status=="FIT_EXACT":raise SystemExit("FIT_EXACT requires used_for_fit=true")

    print("RNATR_V041_LOCUS_AGGREGATION_VALIDATION_PASS")

if __name__=="__main__":main()
