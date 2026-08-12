#!/usr/bin/env python3
from __future__ import annotations
import argparse, csv, importlib.util, json, math, sys
from dataclasses import dataclass, asdict
from pathlib import Path

CALLER_VERSION='rnatr_general_repeat_caller_ref_v0.4.0'

# v0.3.0 deliberately layers boundary/censoring semantics on the frozen v0.2.0
# reference primitives rather than reimplementing the cyclic DP.
def _load_v02():
    here=Path(__file__).resolve().parent
    p=here/'rnatr_general_repeat_caller_ref_v0.2.0.py'
    if not p.is_file():
        # local developer fallback
        p=Path('/tmp/caller_v02.py')
    if not p.is_file():
        raise FileNotFoundError(f'required v0.2.0 reference caller not found: {p}')
    spec=importlib.util.spec_from_file_location('rnatr_general_v020_ref',p)
    mod=importlib.util.module_from_spec(spec); sys.modules[spec.name]=mod; spec.loader.exec_module(mod)
    return mod

v02=_load_v02()
DNA=v02.DNA
revcomp=v02.revcomp
rotations=v02.rotations
primitive_motif=v02.primitive_motif
canonical_motif=v02.canonical_motif
Alignment=v02.Alignment
Segment=v02.Segment
exact_periodic_lps=v02.exact_periodic_lps
_periodic_agreement=v02._periodic_agreement
_best_oriented_alignment=v02._best_oriented_alignment
_label_based_segments=v02._label_based_segments

@dataclass
class Call:
    caller_version: str
    call_status: str
    canonical_motif: str
    oriented_motif: str
    motif_source: str
    read_start: int
    read_end: int
    repeat_bp_observed: int
    motif_path_bp: int
    repeat_units_path: float
    score: float
    score_per_read_bp: float
    matches: int
    mismatches: int
    insertions: int
    deletions: int
    purity: float
    prior_start: int
    prior_end: int
    prior_span_bp: int
    left_extension_bp: int
    right_extension_bp: int
    catalog_motif_used: bool
    lps_exact_sequence_bp: int
    lps_inferred_bp: int
    lps_status: str
    compound_status: str
    repeat_segment_count: int
    distinct_motif_count: int
    interruption_count: int
    repeat_segments_json: str
    interruption_segments_json: str
    # v0.3 boundary/censoring/alternative fields
    evidence_geometry: str
    sequence_context: str
    sizing_status: str
    exact_repeat_bp: int|None
    lower_bound_bp: int|None
    interval_lower_bp: int|None
    interval_upper_bp: int|None
    left_boundary_status: str
    right_boundary_status: str
    context_limited: bool
    touches_left_sequence_edge: bool
    touches_right_sequence_edge: bool
    prior_overlap_bp: int
    alternative_canonical_motif: str
    alternative_score: float|None
    primary_minus_alternative_score: float|None
    hypothesis_count: int
    note: str


def _consensus_candidates(segment:str,max_period:int,source:str):
    out=[]
    segment=segment.upper()
    maxp=min(max_period,max(1,len(segment)//3))
    for p in range(1,maxp+1):
        m,a=v02.consensus_motif(segment,p)
        if not m: continue
        try: c=canonical_motif(m)
        except Exception: continue
        # Require modest periodic support; catalog remains available regardless.
        if a < 0.52: continue
        # Penalize longer motifs slightly to suppress harmonics after primitive collapse.
        objective=a-0.003*len(c)
        out.append((objective,a,c,m,source))
    return out


def generate_hypotheses(seq:str,prior_start:int,prior_end:int,catalog_motifs,
                        max_denovo_period:int=50,top_k:int=12):
    seq=seq.upper(); span=prior_end-prior_start
    hyps={}
    catalog_canons=[]
    for raw in catalog_motifs or []:
        if not raw: continue
        c=canonical_motif(raw)
        hyps[c]={'source':'CATALOG','agreement':1.0,'seed':raw}
        catalog_canons.append(c)

    # De-novo is a rescue, not a mandatory competing scan.  If a catalog motif
    # already explains most of the projected core with good purity, preserve the
    # catalog prior and avoid an expensive all-period search.
    rescue=True
    prior_seq=seq[prior_start:prior_end]
    if catalog_canons:
        fits=[]
        for c in catalog_canons:
            a=_best_oriented_alignment(prior_seq,c)
            frac=a.aligned_read_bp/max(1,len(prior_seq))
            spb=a.score/max(1,a.aligned_read_bp)
            fits.append((a.purity,frac,spb,a.motif_path_bp/max(1,len(c))))
        best=max(fits)
        if best[0]>=0.72 and best[1]>=0.70 and best[2]>=0.45 and best[3]>=3:
            rescue=False
    if not rescue:
        return hyps

    # Multi-scale windows all remain anchored on the projected locus.
    margins=sorted(set([0,max(8,span//3),max(16,span)]))
    cand=[]
    for margin in margins:
        lo=max(0,prior_start-margin); hi=min(len(seq),prior_end+margin)
        if hi-lo<9: continue
        cand.extend(_consensus_candidates(seq[lo:hi],max_denovo_period,'DENOVO_CONTEXT'))
    lo=max(0,prior_start-max(12,span//2)); hi=min(len(seq),prior_end+max(12,span//2))
    region=seq[lo:hi]
    if len(region)>=12:
        cuts=[(0,max(3,len(region)*2//3)),(max(0,len(region)//3),len(region))]
        for a,b in cuts:
            if b-a>=9:
                cand.extend(_consensus_candidates(region[a:b],max_denovo_period,'DENOVO_RESIDUAL'))

    best={}
    for objective,agreement,c,m,source in cand:
        old=best.get(c); rec=(objective,agreement,c,m,source)
        if old is None or rec[:2]>old[:2]: best[c]=rec
    ranked=sorted(best.values(),reverse=True)
    added=0
    for objective,agreement,c,m,source in ranked:
        if c in hyps: continue
        hyps[c]={'source':source,'agreement':agreement,'seed':m}
        added+=1
        if added>=top_k: break
    return hyps


def _candidate_windows(seq_len:int,prior_start:int,prior_end:int,p:int):
    span=prior_end-prior_start
    # Geometric expansion beyond a short projected prior. Every accepted alignment
    # must still overlap the projected locus core, so remote repeat tracts cannot
    # replace the locus merely because they are longer.
    max_margin=max(prior_start,seq_len-prior_end)
    base=max(12,span//2,p)
    margins=[0,p,2*p,4*p,8*p,base,max(50,span)]
    m=max(50,span)
    while m < max_margin:
        m=min(max_margin,max(m+1,2*m))
        margins.append(m)
    margins.append(max_margin)
    out=[]; seen=set()
    for m in margins:
        m=min(max_margin,max(0,int(m)))
        lo=max(0,prior_start-m); hi=min(seq_len,prior_end+m)
        if hi<=lo or (lo,hi) in seen: continue
        seen.add((lo,hi)); out.append((lo,hi))
    return out


def _anchored_alignment(seq:str,canon:str,prior_start:int,prior_end:int):
    p=len(canon); span=prior_end-prior_start
    candidates=[]
    for lo,hi in _candidate_windows(len(seq),prior_start,prior_end,p):
        aln=_best_oriented_alignment(seq[lo:hi],canon)
        st=lo+aln.read_start; en=lo+aln.read_end
        ov=max(0,min(en,prior_end)-max(st,prior_start))
        if ov<=0: continue
        # Avoid a one-base accidental touch to a distant repeat tract.
        min_ov=min(span,max(1,min(2*p, max(1,span//4))))
        if ov<min_ov and aln.aligned_read_bp>max(span,6*p):
            continue
        ext=max(0,prior_start-st)+max(0,en-prior_end)
        objective=aln.score + 0.30*ov - 0.015*ext - 0.75*len(canon)
        candidates.append((objective,aln.score,ov,-ext,st,en,aln,lo,hi))
    if not candidates:
        # Last-resort prior-only alignment; guarantees locus anchoring.
        lo,hi=prior_start,prior_end
        aln=_best_oriented_alignment(seq[lo:hi],canon)
        st=lo+aln.read_start; en=lo+aln.read_end
        ov=max(0,min(en,prior_end)-max(st,prior_start))
        return aln,st,en,ov,lo,hi
    candidates.sort(reverse=True,key=lambda x:x[:6])
    _,_,ov,_,st,en,aln,lo,hi=candidates[0]
    return aln,st,en,ov,lo,hi


def _segment_from_anchored(seq,canon,meta,prior_start,prior_end):
    aln,st,en,ov,lo,hi=_anchored_alignment(seq,canon,prior_start,prior_end)
    # aln coordinates are local to [lo,hi], but the statistics are otherwise reusable.
    exact=exact_periodic_lps(seq[st:en],aln.oriented_motif)
    seg=Segment(canon,aln.oriented_motif,meta['source'],st,en,en-st,
                aln.motif_path_bp,aln.motif_path_bp/max(1,len(canon)),aln.score,aln.purity,
                aln.matches,aln.mismatches,aln.insertions,aln.deletions,exact,en-st)
    return seg,ov


def _normalize_geometry(x:str)->str:
    x=(x or 'SPAN').strip().upper().replace('-','_')
    aliases={'LEFT':'LEFT_CENSORED','RIGHT':'RIGHT_CENSORED','BOTH':'BOTH_CENSORED',
             'LEFT_CENSOR':'LEFT_CENSORED','RIGHT_CENSOR':'RIGHT_CENSORED',
             'BOTH_CENSOR':'BOTH_CENSORED','EXACT_SPAN':'SPAN'}
    x=aliases.get(x,x)
    allowed={'SPAN','LEFT_CENSORED','RIGHT_CENSORED','BOTH_CENSORED','UNKNOWN'}
    return x if x in allowed else 'UNKNOWN'


def _normalize_context(x:str)->str:
    x=(x or 'FULL_READ').strip().upper().replace('-','_')
    if x in {'FULL','RAW_READ','FULL_RAW_READ_FASTQ'}: x='FULL_READ'
    if x in {'WINDOW','PROJECTION_WINDOW_FASTQ'}: x='PROJECTION_WINDOW'
    return x if x in {'FULL_READ','PROJECTION_WINDOW'} else 'UNKNOWN'


def call_repeat(seq:str,prior_start:int,prior_end:int,catalog_motifs=None,
                max_denovo_period:int=50,top_k:int=12,
                evidence_geometry:str='SPAN',sequence_context:str='FULL_READ')->Call:
    seq=seq.upper()
    if prior_start<0 or prior_end>len(seq) or prior_end<=prior_start:
        raise ValueError('invalid prior interval')
    geometry=_normalize_geometry(evidence_geometry)
    context=_normalize_context(sequence_context)
    hyps=generate_hypotheses(seq,prior_start,prior_end,catalog_motifs,max_denovo_period,top_k)
    if not hyps: raise ValueError('no motif hypotheses')
    catalog_canons={canonical_motif(x) for x in (catalog_motifs or []) if x}
    span=prior_end-prior_start

    ranked=[]
    prior_seq=seq[prior_start:prior_end]
    for canon,meta in hyps.items():
        seg,ov=_segment_from_anchored(seq,canon,meta,prior_start,prior_end)
        core=_best_oriented_alignment(prior_seq,canon)
        core_units=core.motif_path_bp/max(1,len(canon))
        # Motif identity is chosen from evidence inside the projected locus core;
        # tract extension is evaluated only after the motif is anchored.  This prevents
        # a long remote periodic tract in the surrounding window from hijacking the locus.
        objective=core.score - 1.5*len(canon) + (10.0 if canon in catalog_canons else 0.0) + 2.0*core.purity
        if core_units<3: objective-=20.0
        ranked.append((objective,canon,meta,seg,ov))
    ranked.sort(key=lambda x:(x[0],x[3].score,x[4],-len(x[1])),reverse=True)
    _,base_canon,base_meta,baseline,base_ov=ranked[0]
    alt=ranked[1] if len(ranked)>1 else None

    # Compound/interruption segmentation remains conservative and anchored to the locus.
    label_margin=max(12,min(50,span//2))
    label_start=max(0,prior_start-label_margin); label_end=min(len(seq),prior_end+label_margin)
    chain=_label_based_segments(seq,label_start,label_end,hyps)
    chain=[s for s in chain if max(0,min(s.read_end,prior_end)-max(s.read_start,prior_start))>0]
    if chain:
        # Preserve v0.2.0 conservative terminal recovery for compound/interruption
        # segments while keeping neighbouring labelled segments non-overlapping.
        ext=[]
        ordered=sorted(chain,key=lambda s:s.read_start)
        for idx,s in enumerate(ordered):
            p=len(s.canonical_motif)
            prev_end=ordered[idx-1].read_end if idx else label_start
            next_start=ordered[idx+1].read_start if idx+1<len(ordered) else label_end
            lo=max(label_start,prev_end,s.read_start-2*p)
            hi=min(label_end,next_start,s.read_end+2*p)
            aln=_best_oriented_alignment(seq[lo:hi],s.canonical_motif)
            st=lo+aln.read_start; en=lo+aln.read_end
            if en>st and aln.aligned_read_bp>=max(6,2*p) and aln.purity>=0.58:
                exact=exact_periodic_lps(seq[st:en],aln.oriented_motif)
                ext.append(Segment(s.canonical_motif,aln.oriented_motif,s.motif_source,st,en,aln.aligned_read_bp,
                                   aln.motif_path_bp,aln.motif_path_bp/p,aln.score,aln.purity,
                                   aln.matches,aln.mismatches,aln.insertions,aln.deletions,exact,aln.aligned_read_bp))
            else:
                ext.append(s)
        chain=ext
    chain=sorted(chain,key=lambda s:s.read_start)
    distinct={s.canonical_motif for s in chain}
    gap_records=[]
    for a,b in zip(chain,chain[1:]):
        gap=max(0,b.read_start-a.read_end); agr=1.0
        if gap>0 and a.canonical_motif==b.canonical_motif:
            agr,_=_periodic_agreement(seq[a.read_end:b.read_start],a.canonical_motif)
        gap_records.append((gap,agr,a.canonical_motif,b.canonical_motif))
    strong=bool(chain) and all(s.purity>=0.65 and s.observed_bp>=max(6,2*len(s.canonical_motif)) for s in chain)
    compound_info=(2<=len(chain)<=4 and len(distinct)>=2 and strong)
    interrupt_info=(2<=len(chain)<=4 and len(distinct)==1 and strong and any(g>=4 and agr<0.55 for g,agr,_,_ in gap_records))
    if not (compound_info or interrupt_info): chain=[baseline]

    chain=sorted(chain,key=lambda s:s.read_start)
    interruptions=[]
    for a,b in zip(chain,chain[1:]):
        if b.read_start>a.read_end:
            interruptions.append({'read_start':a.read_end,'read_end':b.read_start,'length_bp':b.read_start-a.read_end,
                                  'sequence':seq[a.read_end:b.read_start]})
    tract_start=min(s.read_start for s in chain); tract_end=max(s.read_end for s in chain)
    motifs=sorted({s.canonical_motif for s in chain})
    primary=max(chain,key=lambda s:(s.score,s.observed_bp,s.purity))
    total_motif_path=sum(s.motif_path_bp for s in chain); total_score=sum(s.score for s in chain)
    matches=sum(s.matches for s in chain); mismatches=sum(s.mismatches for s in chain)
    insertions=sum(s.insertions for s in chain); deletions=sum(s.deletions for s in chain)
    denom=matches+mismatches+insertions+deletions; purity=matches/denom if denom else 0.0
    compound='COMPOUND' if len(motifs)>=2 else ('INTERRUPTED_SINGLE_MOTIF' if interruptions else 'SINGLE_MOTIF')
    status='PASS' if total_motif_path>=3*len(primary.canonical_motif) and purity>=0.55 else 'LOW_CONFIDENCE'

    edge_guard=max(3,2*len(primary.canonical_motif))
    touch_left=tract_start<=edge_guard
    touch_right=(len(seq)-tract_end)<=edge_guard
    context_limited=(context=='PROJECTION_WINDOW' and (touch_left or touch_right))

    # Geometry and context determine sizing semantics; sequence periodicity alone never upgrades a censored molecule.
    exact=None; lower=None; ilow=None; iup=None
    if status!='PASS':
        sizing='LOW_CONFIDENCE'
    elif geometry=='SPAN' and not context_limited:
        sizing='EXACT_SPAN'; exact=tract_end-tract_start; lower=exact; ilow=exact; iup=exact
    elif geometry=='LEFT_CENSORED':
        sizing='LOWER_BOUND_LEFT_CENSORED'; lower=tract_end-tract_start; ilow=lower
    elif geometry=='RIGHT_CENSORED':
        sizing='LOWER_BOUND_RIGHT_CENSORED'; lower=tract_end-tract_start; ilow=lower
    elif geometry=='BOTH_CENSORED':
        sizing='LOWER_BOUND_BOTH_CENSORED'; lower=tract_end-tract_start; ilow=lower
    elif context_limited:
        sizing='CONTEXT_LIMITED_LOWER_BOUND'; lower=tract_end-tract_start; ilow=lower
    else:
        sizing='LOWER_BOUND_UNKNOWN_GEOMETRY'; lower=tract_end-tract_start; ilow=lower

    def bstatus(side):
        if geometry in {'LEFT_CENSORED','BOTH_CENSORED'} and side=='L': return 'CENSORED_BY_GEOMETRY'
        if geometry in {'RIGHT_CENSORED','BOTH_CENSORED'} and side=='R': return 'CENSORED_BY_GEOMETRY'
        if context=='PROJECTION_WINDOW' and ((side=='L' and touch_left) or (side=='R' and touch_right)): return 'CONTEXT_EDGE'
        if status!='PASS': return 'LOW_CONFIDENCE'
        return 'SEQUENCE_BOUNDED'

    alt_canon=alt[1] if alt else ''
    alt_score=float(alt[0]) if alt else None
    delta=float(ranked[0][0]-alt[0]) if alt else None
    prior_ov=max(0,min(tract_end,prior_end)-max(tract_start,prior_start))
    return Call(
        CALLER_VERSION,status,primary.canonical_motif,primary.oriented_motif,primary.motif_source,
        tract_start,tract_end,tract_end-tract_start,total_motif_path,
        total_motif_path/max(1,len(primary.canonical_motif)),total_score,total_score/max(1,tract_end-tract_start),
        matches,mismatches,insertions,deletions,purity,prior_start,prior_end,span,
        max(0,prior_start-tract_start),max(0,tract_end-prior_end),
        any(s.canonical_motif in catalog_canons for s in chain),
        max(s.lps_exact_sequence_bp for s in chain),max(s.lps_inferred_bp for s in chain),
        'IMPLEMENTED_REFERENCE_V0.3.0',compound,len(chain),len(motifs),len(interruptions),
        json.dumps([asdict(s) for s in chain],separators=(',',':')),
        json.dumps(interruptions,separators=(',',':')),
        geometry,context,sizing,exact,lower,ilow,iup,bstatus('L'),bstatus('R'),context_limited,
        touch_left,touch_right,prior_ov,alt_canon,alt_score,delta,len(hyps),
        'Prior-anchored boundary selection; explicit geometry-based censoring; projection-window edges are context-limited, not biological censoring. Stronger anchored de-novo/residual hypotheses are enabled through period 50.'
    )


def cli():
    ap=argparse.ArgumentParser()
    ap.add_argument('--sequence')
    ap.add_argument('--input-tsv',type=Path)
    ap.add_argument('--output-tsv',type=Path)
    ap.add_argument('--prior-start',type=int); ap.add_argument('--prior-end',type=int)
    ap.add_argument('--catalog-motif',action='append',default=[])
    ap.add_argument('--evidence-geometry',default='SPAN')
    ap.add_argument('--sequence-context',default='FULL_READ')
    args=ap.parse_args()
    if args.input_tsv:
        if not args.output_tsv: ap.error('--output-tsv is required with --input-tsv')
        rows=[]
        with args.input_tsv.open() as fh:
            rd=csv.DictReader(fh,delimiter='\t')
            for row in rd:
                motifs=[x for x in row.get('catalog_motif','').split(',') if x]
                geom=row.get('evidence_geometry',args.evidence_geometry)
                context=row.get('sequence_context',row.get('materialization_mode',args.sequence_context))
                call=call_repeat(row['sequence'],int(row['prior_start']),int(row['prior_end']),motifs,
                                 evidence_geometry=geom,sequence_context=context)
                rows.append({'case_id':row.get('case_id',''),**asdict(call)})
        if not rows: raise SystemExit('ERROR: input TSV has no rows')
        args.output_tsv.parent.mkdir(parents=True,exist_ok=True)
        tmp=args.output_tsv.with_name('.'+args.output_tsv.name+'.part')
        with tmp.open('w',newline='') as fh:
            wr=csv.DictWriter(fh,fieldnames=list(rows[0]),delimiter='\t'); wr.writeheader(); wr.writerows(rows)
        tmp.replace(args.output_tsv)
    else:
        if args.sequence is None or args.prior_start is None or args.prior_end is None:
            ap.error('single-call mode requires --sequence --prior-start --prior-end')
        print(json.dumps(asdict(call_repeat(args.sequence,args.prior_start,args.prior_end,args.catalog_motif,
                                           evidence_geometry=args.evidence_geometry,
                                           sequence_context=args.sequence_context)),indent=2))

if __name__=='__main__': cli()
