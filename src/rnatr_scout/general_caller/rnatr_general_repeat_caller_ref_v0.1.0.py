#!/usr/bin/env python3
from __future__ import annotations
import argparse, csv, json, math
from dataclasses import dataclass, asdict
from pathlib import Path

DNA='ACGT'
COMP=str.maketrans('ACGTN','TGCAN')

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
    lps_status: str
    compound_status: str
    note: str

CALLER_VERSION='rnatr_general_repeat_caller_ref_v0.1.0'

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
                        max_denovo_period:int=20,top_k:int=6):
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

def call_repeat(seq:str,prior_start:int,prior_end:int,catalog_motifs=None,
                max_denovo_period:int=20,top_k:int=6)->Call:
    seq=seq.upper()
    if prior_start<0 or prior_end>len(seq) or prior_end<=prior_start:
        raise ValueError('invalid prior interval')
    hyps=generate_hypotheses(seq,prior_start,prior_end,catalog_motifs,max_denovo_period,top_k)
    if not hyps:
        raise ValueError('no motif hypotheses')
    catalog_canons={canonical_motif(x) for x in (catalog_motifs or []) if x}
    ranked=[]
    for canon,meta in hyps.items():
        best=None
        for oriented in {canon,revcomp(canon)}:
            aln=cyclic_local_align(seq,oriented)
            if best is None or aln.score>best.score: best=aln
        units=best.motif_path_bp/max(1,len(canon))
        objective=best.score-1.5*len(canon)+(8.0 if canon in catalog_canons else 0.0)
        if units<3: objective-=20.0
        ranked.append((objective,canon,meta,best))
    ranked.sort(key=lambda x:(x[0],x[3].score,-len(x[1])),reverse=True)
    objective,canon,meta,best=ranked[0]
    status='PASS' if best.aligned_read_bp>=3*len(canon) and best.purity>=0.55 else 'LOW_CONFIDENCE'
    return Call(
        CALLER_VERSION,status,canon,best.oriented_motif,meta['source'],best.read_start,best.read_end,
        best.aligned_read_bp,best.motif_path_bp,best.motif_path_bp/len(canon),best.score,
        best.score/max(1,best.aligned_read_bp),best.matches,best.mismatches,best.insertions,best.deletions,
        best.purity,prior_start,prior_end,prior_end-prior_start,prior_start-best.read_start,
        best.read_end-prior_end,canon in catalog_canons,
        'NOT_IMPLEMENTED_IN_REF_V0.1.0','NOT_IMPLEMENTED_IN_REF_V0.1.0',
        'Reference single-motif core only; compound segmentation, interruption-aware LPS, censored inference, and production optimization are later stages.'
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
