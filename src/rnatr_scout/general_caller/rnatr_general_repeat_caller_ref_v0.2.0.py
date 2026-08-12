#!/usr/bin/env python3
from __future__ import annotations
import argparse, csv, json, math
from dataclasses import dataclass, asdict
from pathlib import Path
from bisect import bisect_right

DNA='ACGT'
COMP=str.maketrans('ACGTN','TGCAN')
CALLER_VERSION='rnatr_general_repeat_caller_ref_v0.2.0'


def revcomp(s:str)->str:
    return s.upper().translate(COMP)[::-1]


def rotations(s:str):
    s=s.upper()
    return [s[i:]+s[:i] for i in range(len(s))]


def primitive_motif(s:str)->str:
    s=s.upper()
    if not s or any(c not in DNA for c in s):
        raise ValueError(f'invalid motif: {s!r}')
    for p in range(1,len(s)+1):
        if len(s)%p==0 and s==s[:p]*(len(s)//p):
            return s[:p]
    return s


def canonical_motif(s:str)->str:
    p=primitive_motif(s)
    return min(rotations(p)+rotations(revcomp(p)))


@dataclass
class Alignment:
    score: float
    read_start: int
    read_end: int
    aligned_read_bp: int
    motif_path_bp: int
    matches: int
    mismatches: int
    insertions: int
    deletions: int
    purity: float
    phase_start: int
    phase_end: int
    oriented_motif: str
    ops: str


@dataclass
class Segment:
    canonical_motif: str
    oriented_motif: str
    motif_source: str
    read_start: int
    read_end: int
    observed_bp: int
    motif_path_bp: int
    repeat_units_path: float
    score: float
    purity: float
    matches: int
    mismatches: int
    insertions: int
    deletions: int
    lps_exact_sequence_bp: int
    lps_inferred_bp: int


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
    note: str


def cyclic_local_align(seq:str,motif:str,match:float=2.0,mismatch:float=-3.0,
                       ins:float=-3.0,dele:float=-3.0,max_del:int=2)->Alignment:
    seq=seq.upper(); motif=motif.upper()
    if not seq or not motif:
        raise ValueError('sequence and motif must be non-empty')
    n,p=len(seq),len(motif)
    neg=-1e100
    prev_m=[neg]*p; prev_i=[neg]*p
    tb_m=[[None]*p for _ in range(n)]
    tb_i=[[None]*p for _ in range(n)]
    best=(0.0,None,None,None)
    for i,b in enumerate(seq):
        cur_m=[neg]*p; cur_i=[neg]*p
        for j in range(p):
            emit=match if b==motif[j] else mismatch
            best_m=emit; pred=None
            pj=(j-1)%p
            for st,arr in (('M',prev_m),('I',prev_i)):
                sc=arr[pj]+emit
                if sc>best_m:
                    best_m=sc; pred=(st,pj,0)
            for d in range(1,max_del+1):
                pj=(j-d-1)%p
                for st,arr in (('M',prev_m),('I',prev_i)):
                    sc=arr[pj]+dele*d+emit
                    if sc>best_m:
                        best_m=sc; pred=(st,pj,d)
            if best_m>0:
                cur_m[j]=best_m; tb_m[i][j]=pred
                if best_m>best[0]: best=(best_m,i,'M',j)
            cand_m=prev_m[j]+ins; cand_i=prev_i[j]+ins
            if cand_m>0 or cand_i>0:
                if cand_m>=cand_i:
                    cur_i[j]=cand_m; tb_i[i][j]=('M',j,0)
                else:
                    cur_i[j]=cand_i; tb_i[i][j]=('I',j,0)
                if cur_i[j]>best[0]: best=(cur_i[j],i,'I',j)
        prev_m,prev_i=cur_m,cur_i
    if best[1] is None:
        return Alignment(0.0,0,0,0,0,0,0,0,0,0.0,0,0,motif,'')
    score,i,state,j=best
    end=i+1; phase_end=j
    matches=mismatches=insertions=deletions=0; ops=[]
    while i>=0:
        if state=='M':
            if seq[i]==motif[j]: matches+=1; ops.append('=')
            else: mismatches+=1; ops.append('X')
            pred=tb_m[i][j]
            if pred is None:
                start=i; phase_start=j; break
            pst,pj,d=pred
            if d:
                deletions+=d; ops.extend('D'*d)
            i-=1; state=pst; j=pj
        else:
            insertions+=1; ops.append('I')
            pred=tb_i[i][j]
            if pred is None:
                start=i; phase_start=j; break
            pst,pj,_=pred
            i-=1; state=pst; j=pj
    aligned=end-start
    motif_path=matches+mismatches+deletions
    denom=matches+mismatches+insertions+deletions
    purity=matches/denom if denom else 0.0
    return Alignment(score,start,end,aligned,motif_path,matches,mismatches,insertions,deletions,
                     purity,phase_start,phase_end,motif,''.join(reversed(ops)))


def consensus_motif(segment:str,p:int):
    if p<1 or len(segment)<3*p: return None,0.0
    motif=[]; agree=0; total=0
    for j in range(p):
        counts={b:0 for b in DNA}
        for i in range(j,len(segment),p):
            b=segment[i]
            if b in counts: counts[b]+=1
        b=max(counts,key=counts.get)
        motif.append(b); agree+=counts[b]; total+=sum(counts.values())
    return ''.join(motif), (agree/total if total else 0.0)


def generate_hypotheses(seq:str,prior_start:int,prior_end:int,catalog_motifs,
                        max_denovo_period:int=30,top_k:int=10):
    hyps={}
    for raw in catalog_motifs or []:
        if not raw: continue
        c=canonical_motif(raw)
        hyps[c]={'source':'CATALOG','agreement':1.0,'seed':raw}
    lo=max(0,prior_start); hi=min(len(seq),prior_end)
    segment=seq[lo:hi].upper()
    cands=[]
    maxp=min(max_denovo_period,max(1,len(segment)//3))
    for p in range(1,maxp+1):
        m,a=consensus_motif(segment,p)
        if not m: continue
        c=canonical_motif(m)
        cands.append((a-0.005*len(c),a,c,m))
    cands.sort(reverse=True)
    denovo_n=0
    for _,a,c,m in cands:
        if c in hyps: continue
        hyps[c]={'source':'DENOVO','agreement':a,'seed':m}
        denovo_n+=1
        if denovo_n>=top_k: break
    return hyps


def exact_periodic_lps(segment:str,motif:str)->int:
    segment=segment.upper(); motif=motif.upper()
    if not segment or not motif: return 0
    best=0
    p=len(motif)
    for phase in range(p):
        run=0
        for i,b in enumerate(segment):
            if b==motif[(i+phase)%p]:
                run+=1; best=max(best,run)
            else:
                run=0
    return best



def _periodic_agreement(segment:str,motif:str):
    segment=segment.upper(); motif=motif.upper()
    if not segment or not motif: return 0.0,motif
    best=(-1.0,motif)
    for oriented in {motif,revcomp(motif)}:
        p=len(oriented)
        for phase in range(p):
            m=sum(1 for i,b in enumerate(segment) if b==oriented[(i+phase)%p])
            sc=m/len(segment)
            if sc>best[0]: best=(sc,oriented)
    return best


def _label_based_segments(seq:str,region_start:int,region_end:int,hyps,
                          threshold:float=0.72,margin:float=0.04):
    region=seq[region_start:region_end]
    canons=list(hyps)
    labels=[]
    for pos in range(len(region)):
        scored=[]
        for canon in canons:
            p=len(canon); w=max(9,3*p)
            lo=max(0,pos-w//2); hi=min(len(region),lo+w)
            lo=max(0,hi-w)
            if hi-lo<max(6,2*p): continue
            sc,orient=_periodic_agreement(region[lo:hi],canon)
            scored.append((sc,canon,orient))
        scored.sort(reverse=True)
        if not scored or scored[0][0]<threshold:
            labels.append(None)
        elif len(scored)>1 and scored[0][0]-scored[1][0]<margin:
            labels.append(None)
        else:
            labels.append(scored[0][1])
    def runs(vals):
        out=[]; st=0
        for i in range(1,len(vals)+1):
            if i==len(vals) or vals[i]!=vals[st]:
                out.append([st,i,vals[st]]); st=i
        return out
    # Drop very short motif runs.
    for st,en,lab in runs(labels):
        if lab is not None and en-st<max(6,2*len(lab)):
            for i in range(st,en): labels[i]=None
    # Fill tiny background gaps when the same motif flanks them.
    rr=runs(labels)
    for idx in range(1,len(rr)-1):
        st,en,lab=rr[idx]
        if lab is None and en-st<=2 and rr[idx-1][2] is not None and rr[idx-1][2]==rr[idx+1][2]:
            for i in range(st,en): labels[i]=rr[idx-1][2]
    segs=[]
    for st,en,lab in runs(labels):
        if lab is None: continue
        pad=len(lab)
        sub_st=max(0,st-pad); sub_en=min(len(region),en+pad)
        aln=_best_oriented_alignment(region[sub_st:sub_en],lab)
        abs_st=region_start+sub_st+aln.read_start
        abs_en=region_start+sub_st+aln.read_end
        # Keep label-derived segments non-overlapping; refinement may use padding to
        # identify phase, but reported segment boundaries stay inside the labelled run.
        abs_st=max(abs_st,region_start+st); abs_en=min(abs_en,region_start+en)
        if abs_en<=abs_st: continue
        clipped=_best_oriented_alignment(seq[abs_st:abs_en],lab)
        if clipped.aligned_read_bp<max(6,2*len(lab)) or clipped.purity<0.58: continue
        abs_st2=abs_st+clipped.read_start; abs_en2=abs_st+clipped.read_end
        exact=exact_periodic_lps(seq[abs_st2:abs_en2],clipped.oriented_motif)
        segs.append(Segment(lab,clipped.oriented_motif,hyps[lab]['source'],abs_st2,abs_en2,clipped.aligned_read_bp,
                            clipped.motif_path_bp,clipped.motif_path_bp/len(lab),clipped.score,clipped.purity,
                            clipped.matches,clipped.mismatches,clipped.insertions,clipped.deletions,exact,clipped.aligned_read_bp))
    # Resolve overlaps by keeping the stronger local segment.
    return _dedup_segments(segs)

def _best_oriented_alignment(seq:str,canon:str)->Alignment:
    best=None
    for oriented in {canon,revcomp(canon)}:
        aln=cyclic_local_align(seq,oriented)
        if best is None or (aln.score,aln.aligned_read_bp,aln.purity)>(best.score,best.aligned_read_bp,best.purity):
            best=aln
    return best


def _recursive_segments(seq:str,canon:str,source:str,offset:int=0,
                        min_units:float=3.0,min_purity:float=0.58,
                        min_score_per_bp:float=0.35,max_segments:int=8):
    out=[]
    def rec(sub:str,base:int,depth:int):
        if depth>=max_segments or len(sub)<3*len(canon): return
        aln=_best_oriented_alignment(sub,canon)
        if aln.aligned_read_bp < max(6,int(math.ceil(min_units*len(canon)))): return
        if aln.purity < min_purity: return
        if aln.score/max(1,aln.aligned_read_bp) < min_score_per_bp: return
        st=base+aln.read_start; en=base+aln.read_end
        raw=seq[st-offset:en-offset] if offset else seq[st:en]
        # raw indexing above is only used when offset==0 in current implementation.
        exact=exact_periodic_lps(sub[aln.read_start:aln.read_end],aln.oriented_motif)
        out.append(Segment(canon,aln.oriented_motif,source,st,en,aln.aligned_read_bp,
                           aln.motif_path_bp,aln.motif_path_bp/len(canon),aln.score,aln.purity,
                           aln.matches,aln.mismatches,aln.insertions,aln.deletions,
                           exact,aln.aligned_read_bp))
        left=sub[:aln.read_start]; right=sub[aln.read_end:]
        if len(left)>=3*len(canon): rec(left,base,depth+1)
        if len(right)>=3*len(canon): rec(right,en,depth+1)
    rec(seq,offset,0)
    return out


def _dedup_segments(cands):
    cands=sorted(cands,key=lambda s:(s.read_start,s.read_end,-s.score,s.canonical_motif))
    kept=[]
    for s in sorted(cands,key=lambda s:(-s.score,-s.observed_bp,s.read_start,s.canonical_motif)):
        duplicate=False
        for k in kept:
            ov=max(0,min(s.read_end,k.read_end)-max(s.read_start,k.read_start))
            denom=max(1,min(s.observed_bp,k.observed_bp))
            if ov/denom>=0.85 and s.canonical_motif==k.canonical_motif:
                duplicate=True; break
        if not duplicate: kept.append(s)
    return sorted(kept,key=lambda s:(s.read_start,s.read_end,s.canonical_motif))


def _select_chain(cands,prior_start,prior_end,switch_penalty=8.0,max_bridge_bp=30):
    if not cands: return []
    cands=sorted(cands,key=lambda s:(s.read_end,s.read_start,-s.score,s.canonical_motif))
    n=len(cands)
    best=[-1e100]*n; prev=[None]*n
    for j,s in enumerate(cands):
        prior_ov=max(0,min(s.read_end,prior_end)-max(s.read_start,prior_start))
        base=s.score - 1.0*len(s.canonical_motif) + (6.0 if prior_ov>0 else 0.0)
        best[j]=base
        for i in range(j):
            p=cands[i]
            gap=s.read_start-p.read_end
            if gap<0 or gap>max_bridge_bp: continue
            penalty=switch_penalty if p.canonical_motif!=s.canonical_motif else 2.0
            cand=best[i]+base-penalty-0.15*gap
            if cand>best[j]:
                best[j]=cand; prev[j]=i
    j=max(range(n),key=lambda x:best[x])
    chain=[]
    while j is not None:
        chain.append(cands[j]); j=prev[j]
    chain.reverse()
    # Require chain to touch the soft prior; otherwise use best overlapping segment if available.
    if not any(max(0,min(s.read_end,prior_end)-max(s.read_start,prior_start))>0 for s in chain):
        overlap=[s for s in cands if max(0,min(s.read_end,prior_end)-max(s.read_start,prior_start))>0]
        if overlap: return [max(overlap,key=lambda s:(s.score,s.observed_bp,s.purity))]
    return chain


def call_repeat(seq:str,prior_start:int,prior_end:int,catalog_motifs=None,
                max_denovo_period:int=30,top_k:int=10,roi_margin:int|None=None,
                max_bridge_bp:int=30)->Call:
    seq=seq.upper()
    if prior_start<0 or prior_end>len(seq) or prior_end<=prior_start:
        raise ValueError('invalid prior interval')
    hyps=generate_hypotheses(seq,prior_start,prior_end,catalog_motifs,max_denovo_period,top_k)
    if not hyps: raise ValueError('no motif hypotheses')
    catalog_canons={canonical_motif(x) for x in (catalog_motifs or []) if x}
    span=prior_end-prior_start
    margin=max(50,span) if roi_margin is None else max(0,int(roi_margin))
    roi_start=max(0,prior_start-margin); roi_end=min(len(seq),prior_end+margin)
    roi=seq[roi_start:roi_end]
    # Establish the v0.1-style single-motif reference result first. Compound or
    # interruption segmentation is allowed to replace it only when there is explicit
    # multi-segment evidence; this preserves single-motif regression semantics.
    ranked=[]
    for canon,meta in hyps.items():
        aln=_best_oriented_alignment(seq,canon)
        units=aln.motif_path_bp/max(1,len(canon))
        objective=aln.score-1.5*len(canon)+(8.0 if canon in catalog_canons else 0.0)
        if units<3: objective-=20.0
        ranked.append((objective,canon,meta,aln))
    ranked.sort(key=lambda x:(x[0],x[3].score,-len(x[1])),reverse=True)
    _,base_canon,base_meta,base_aln=ranked[0]
    base_st=base_aln.read_start; base_en=base_aln.read_end
    base_exact=exact_periodic_lps(seq[base_st:base_en],base_aln.oriented_motif)
    baseline=Segment(base_canon,base_aln.oriented_motif,base_meta['source'],base_st,base_en,
                     base_aln.aligned_read_bp,base_aln.motif_path_bp,
                     base_aln.motif_path_bp/max(1,len(base_canon)),base_aln.score,base_aln.purity,
                     base_aln.matches,base_aln.mismatches,base_aln.insertions,base_aln.deletions,
                     base_exact,base_aln.aligned_read_bp)

    # Use local periodic-agreement labels to expose compound switches and explicit
    # interruption gaps. The soft prior plus a modest margin defines the segmentation ROI.
    label_margin=max(12,min(50,span//2))
    label_start=max(0,prior_start-label_margin); label_end=min(len(seq),prior_end+label_margin)
    chain=_label_based_segments(seq,label_start,label_end,hyps)
    chain=[s for s in chain if max(0,min(s.read_end,prior_end)-max(s.read_start,prior_start))>0 or
           (s.read_start<=prior_start and s.read_end>=prior_end)]
    if chain:
        # Recover terminal bases that conservative local labels may trim, without
        # allowing one repeat segment to swallow a neighbouring segment.
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
        gap=max(0,b.read_start-a.read_end)
        agr=1.0
        if gap>0 and a.canonical_motif==b.canonical_motif:
            agr,_=_periodic_agreement(seq[a.read_end:b.read_start],a.canonical_motif)
        gap_records.append((gap,agr,a.canonical_motif,b.canonical_motif))
    strong_segments=all(s.purity>=0.65 and s.observed_bp>=max(6,2*len(s.canonical_motif)) for s in chain)
    compound_informative=(2<=len(chain)<=4 and len(distinct)>=2 and strong_segments)
    interruption_informative=(2<=len(chain)<=4 and len(distinct)==1 and strong_segments and
                              any(g>=4 and agr<0.55 for g,agr,_,_ in gap_records))
    informative=compound_informative or interruption_informative
    if not informative:
        chain=[baseline]
    chain=sorted(chain,key=lambda s:s.read_start)
    interruptions=[]
    for a,b in zip(chain,chain[1:]):
        if b.read_start>a.read_end:
            interruptions.append({'read_start':a.read_end,'read_end':b.read_start,
                                  'length_bp':b.read_start-a.read_end,
                                  'sequence':seq[a.read_end:b.read_start]})
    tract_start=min(s.read_start for s in chain); tract_end=max(s.read_end for s in chain)
    motifs=sorted({s.canonical_motif for s in chain})
    primary=max(chain,key=lambda s:(s.score,s.observed_bp,s.purity))
    total_motif_path=sum(s.motif_path_bp for s in chain)
    total_score=sum(s.score for s in chain)
    total_matches=sum(s.matches for s in chain); total_mismatches=sum(s.mismatches for s in chain)
    total_insertions=sum(s.insertions for s in chain); total_deletions=sum(s.deletions for s in chain)
    denom=total_matches+total_mismatches+total_insertions+total_deletions
    purity=total_matches/denom if denom else 0.0
    if len(motifs)>=2: compound='COMPOUND'
    elif interruptions: compound='INTERRUPTED_SINGLE_MOTIF'
    else: compound='SINGLE_MOTIF'
    status='PASS' if total_motif_path>=3*len(primary.canonical_motif) and purity>=0.55 else 'LOW_CONFIDENCE'
    return Call(
        CALLER_VERSION,status,primary.canonical_motif,primary.oriented_motif,primary.motif_source,
        tract_start,tract_end,tract_end-tract_start,total_motif_path,
        total_motif_path/max(1,len(primary.canonical_motif)),total_score,
        total_score/max(1,tract_end-tract_start),total_matches,total_mismatches,total_insertions,total_deletions,
        purity,prior_start,prior_end,span,prior_start-tract_start,tract_end-prior_end,
        any(s.canonical_motif in catalog_canons for s in chain),
        max(s.lps_exact_sequence_bp for s in chain),max(s.lps_inferred_bp for s in chain),
        'IMPLEMENTED_REFERENCE_V0.2.0',compound,len(chain),len(motifs),len(interruptions),
        json.dumps([asdict(s) for s in chain],separators=(',',':')),
        json.dumps(interruptions,separators=(',',':')),
        'Reference compound/interruption/LPS implementation. Censored interval inference, stronger de-novo rescue, and production optimization remain later stages.'
    )


def cli():
    ap=argparse.ArgumentParser()
    ap.add_argument('--sequence')
    ap.add_argument('--input-tsv',type=Path)
    ap.add_argument('--output-tsv',type=Path)
    ap.add_argument('--prior-start',type=int)
    ap.add_argument('--prior-end',type=int)
    ap.add_argument('--catalog-motif',action='append',default=[])
    args=ap.parse_args()
    if args.input_tsv:
        if not args.output_tsv: ap.error('--output-tsv is required with --input-tsv')
        rows=[]
        with args.input_tsv.open() as fh:
            rd=csv.DictReader(fh,delimiter='\t')
            for row in rd:
                motifs=[x for x in row.get('catalog_motif','').split(',') if x]
                call=call_repeat(row['sequence'],int(row['prior_start']),int(row['prior_end']),motifs)
                out={'case_id':row.get('case_id',''),**asdict(call)}
                rows.append(out)
        args.output_tsv.parent.mkdir(parents=True,exist_ok=True)
        tmp=args.output_tsv.with_name('.'+args.output_tsv.name+'.part')
        with tmp.open('w',newline='') as fh:
            wr=csv.DictWriter(fh,fieldnames=list(rows[0].keys()),delimiter='\t')
            wr.writeheader(); wr.writerows(rows)
        tmp.replace(args.output_tsv)
    else:
        if args.sequence is None or args.prior_start is None or args.prior_end is None:
            ap.error('single-call mode requires --sequence --prior-start --prior-end')
        print(json.dumps(asdict(call_repeat(args.sequence,args.prior_start,args.prior_end,args.catalog_motif)),indent=2))


if __name__=='__main__': cli()
