#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,gzip
from collections import defaultdict
from pathlib import Path

MISSING={"",".","NA","N/A","None","null","nan"}

def read(path):
    op=gzip.open if path.suffix==".gz" else open
    with op(path,"rt",encoding="utf-8",newline="") as f:return list(csv.DictReader(f,delimiter="\t"))

def present(v):return v not in MISSING

def require_unique(rows,key,label):
    vals=[r[key] for r in rows]
    if len(vals)!=len(set(vals)):raise SystemExit(f"duplicate {label} {key}")

def as_int(v,label):
    try:return int(v)
    except Exception as exc:raise SystemExit(f"invalid integer {label}={v!r}") from exc

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--package-dir",type=Path,required=True);args=ap.parse_args();d=args.package_dir
    reads=read(d/"read_evidence.tsv")
    calls=read(d/"general_repeat_calls.tsv")
    events=read(d/"repeat_events.tsv")
    segs=read(d/"repeat_segments.tsv")
    ints=read(d/"repeat_interruptions.tsv")

    require_unique(reads,"evidence_id","read_evidence")
    require_unique(calls,"caller_record_id","general_repeat_calls")
    require_unique(events,"repeat_event_id","repeat_events")
    require_unique(segs,"repeat_call_id","repeat_segments")
    require_unique(ints,"interruption_id","repeat_interruptions")

    read_by={r["evidence_id"]:r for r in reads}
    call_by={r["caller_record_id"]:r for r in calls}
    event_by={r["repeat_event_id"]:r for r in events}
    seg_by={r["repeat_call_id"]:r for r in segs}
    calls_by_evidence=defaultdict(list);events_by_evidence=defaultdict(list);segs_by_evidence=defaultdict(list);segs_by_event=defaultdict(list);ints_by_event=defaultdict(list)

    for r in calls:
        if r["evidence_id"] not in read_by:raise SystemExit("caller evidence FK failure")
        calls_by_evidence[r["evidence_id"]].append(r)
        if present(r.get("repeat_event_id",".")) and r["repeat_event_id"] not in event_by:raise SystemExit("caller event FK failure")
        if present(r.get("primary_repeat_call_id",".")) and r["primary_repeat_call_id"] not in seg_by:raise SystemExit("caller primary repeat FK failure")

    for r in events:
        if r["evidence_id"] not in read_by:raise SystemExit("event evidence FK failure")
        if r["primary_caller_record_id"] not in call_by:raise SystemExit("event primary caller FK failure")
        if call_by[r["primary_caller_record_id"]]["evidence_id"]!=r["evidence_id"]:raise SystemExit("event caller belongs to wrong evidence")
        if present(r.get("primary_repeat_call_id",".")) and r["primary_repeat_call_id"] not in seg_by:raise SystemExit("event primary repeat FK failure")
        if as_int(r["read_end"],"event read_end")-as_int(r["read_start"],"event read_start")!=as_int(r["repeat_bp_observed"],"repeat_bp_observed"):raise SystemExit("event coordinate length failure")
        parent=read_by[r["evidence_id"]]
        if r["read_id"]!=parent["read_id"]:raise SystemExit("event/read read_id mismatch")
        if r["locus_id"]!=parent["locus_id"]:raise SystemExit("event/read locus_id mismatch")
        if r.get("context_limited","false")=="true" and r["sizing_status"]=="exact_span":raise SystemExit("context-limited exact event forbidden")
        if r["sizing_status"]=="exact_span" and not present(r.get("exact_repeat_bp",".")):raise SystemExit("exact event missing exact_repeat_bp")
        if r["sizing_status"]=="lower_bound" and not present(r.get("repeat_bp_lower_bound",".")):raise SystemExit("lower-bound event missing lower bound")
        events_by_evidence[r["evidence_id"]].append(r)

    for r in segs:
        if r["evidence_id"] not in read_by:raise SystemExit("segment evidence FK failure")
        if r["repeat_event_id"] not in event_by:raise SystemExit("segment event FK failure")
        if r["caller_record_id"] not in call_by:raise SystemExit("segment caller FK failure")
        if event_by[r["repeat_event_id"]]["evidence_id"]!=r["evidence_id"]:raise SystemExit("segment event/evidence mismatch")
        if as_int(r["read_end"],"segment read_end")-as_int(r["read_start"],"segment read_start")!=as_int(r["repeat_bp"],"repeat_bp"):raise SystemExit("segment coordinate length failure")
        parent=read_by[r["evidence_id"]]
        if r["read_id"]!=parent["read_id"]:raise SystemExit("segment/read read_id mismatch")
        if r["locus_id"]!=parent["locus_id"]:raise SystemExit("segment/read locus_id mismatch")
        segs_by_evidence[r["evidence_id"]].append(r);segs_by_event[r["repeat_event_id"]].append(r)

    for r in ints:
        if r["evidence_id"] not in read_by:raise SystemExit("interruption evidence FK failure")
        if r["caller_record_id"] not in call_by:raise SystemExit("interruption caller FK failure")
        if r["repeat_event_id"] not in event_by:raise SystemExit("interruption event FK failure")
        if present(r.get("repeat_call_id",".")) and r["repeat_call_id"] not in seg_by:raise SystemExit("interruption repeat-call FK failure")
        if as_int(r["read_end"],"interruption read_end")-as_int(r["read_start"],"interruption read_start")!=as_int(r["interruption_bp"],"interruption_bp"):raise SystemExit("interruption coordinate length failure")
        parent=read_by[r["evidence_id"]]
        if r["read_id"]!=parent["read_id"]:raise SystemExit("interruption/read read_id mismatch")
        if r["locus_id"]!=parent["locus_id"]:raise SystemExit("interruption/read locus_id mismatch")
        ints_by_event[r["repeat_event_id"]].append(r)

    for event_id,event in event_by.items():
        parts=segs_by_event[event_id];intr=ints_by_event[event_id]
        if as_int(event["segment_count"],"event segment_count")!=len(parts):raise SystemExit("event segment_count mismatch")
        if as_int(event["distinct_motif_count"],"event distinct_motif_count")!=len({p["canonical_motif"] for p in parts}):raise SystemExit("event distinct_motif_count mismatch")
        if as_int(event["interruption_count"],"event interruption_count")!=len(intr):raise SystemExit("event interruption_count mismatch")
        if parts:
            if event["primary_repeat_call_id"] not in {p["repeat_call_id"] for p in parts}:raise SystemExit("event primary repeat mismatch")
        elif present(event.get("primary_repeat_call_id",".")):raise SystemExit("event primary repeat on zero segments")

    for evidence_id,r in read_by.items():
        ecalls=calls_by_evidence[evidence_id];eevents=events_by_evidence[evidence_id];esegs=segs_by_evidence[evidence_id]
        attempt_count=len(ecalls);called_count=sum(c.get("integration_status")=="CALLED" for c in ecalls);error_count=sum(c.get("integration_status")=="CALLER_ERROR" or present(c.get("caller_error",".")) for c in ecalls)
        if as_int(r["caller_attempt_count"],"caller_attempt_count")!=attempt_count:raise SystemExit("caller_attempt_count mismatch")
        if as_int(r["caller_called_count"],"caller_called_count")!=called_count:raise SystemExit("caller_called_count mismatch")
        if as_int(r["caller_error_count"],"caller_error_count")!=error_count:raise SystemExit("caller_error_count mismatch")
        best_id=r.get("best_caller_record_id",".")
        if attempt_count>0:
            if best_id not in call_by:raise SystemExit("best caller FK failure")
            best=call_by[best_id]
            if best["evidence_id"]!=evidence_id:raise SystemExit("best caller belongs to wrong evidence")
            if r.get("best_projection_id",".")!=best.get("projection_id","."):raise SystemExit("best projection mismatch")
            for dst,src in [("best_caller_version","caller_version"),("best_caller_integration_status","integration_status"),("best_caller_call_status","call_status"),("best_caller_sizing_status","sizing_status")]:
                if present(r.get(dst,".")) and r.get(dst)!=best.get(src):raise SystemExit(f"best caller summary mismatch {dst}")
        elif present(best_id):raise SystemExit("best caller set on zero-attempt evidence")
        if as_int(r["repeat_call_count"],"repeat_call_count")!=len(esegs):raise SystemExit("repeat_call_count mismatch")
        if as_int(r["repeat_event_count"],"repeat_event_count")!=len(eevents):raise SystemExit("repeat_event_count mismatch")
        event_ids={e["repeat_event_id"] for e in eevents};segment_ids={s["repeat_call_id"] for s in esegs}
        if eevents:
            if r["best_repeat_event_id"] not in event_ids:raise SystemExit("best repeat event FK failure")
            if r["best_repeat_call_id"] not in segment_ids:raise SystemExit("best repeat call FK failure")
        elif present(r.get("best_repeat_event_id",".")) or present(r.get("best_repeat_call_id",".")):raise SystemExit("best repeat IDs on zero-event evidence")
        if called_count==0 and eevents:raise SystemExit("zero-called evidence has retained events")
        if r.get("context_limited","false")=="true" and r["sizing_status"]=="exact_span":raise SystemExit("context-limited exact read summary forbidden")
        intervals=sorted((as_int(e["read_start"],"event start"),as_int(e["read_end"],"event end"),e["repeat_event_id"]) for e in eevents)
        for left,right in zip(intervals,intervals[1:]):
            if min(left[1],right[1])-max(left[0],right[0])>0:raise SystemExit("distinct repeat events overlap")

    print("RNATR_V04_PACKAGE_VALIDATION_PASS")

if __name__=="__main__":main()
