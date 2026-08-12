#!/usr/bin/env python3
from __future__ import annotations
import argparse, importlib.util, sys, csv, os
from pathlib import Path

def load(path:Path):
    spec=importlib.util.spec_from_file_location('rnatr_v03_test',path)
    mod=importlib.util.module_from_spec(spec); sys.modules[spec.name]=mod; spec.loader.exec_module(mod); return mod

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--caller',type=Path,required=True); ap.add_argument('--outdir',type=Path,required=True); a=ap.parse_args()
    m=load(a.caller); a.outdir.mkdir(parents=True,exist_ok=True)
    cases=[]
    def add(name,seq,ps,pe,motifs,geom,ctx,check):
        c=m.call_repeat(seq,ps,pe,motifs,evidence_geometry=geom,sequence_context=ctx)
        ok=bool(check(c))
        cases.append({'case_id':name,'canonical_motif':c.canonical_motif,'motif_source':c.motif_source,'repeat_bp_observed':c.repeat_bp_observed,
                      'sizing_status':c.sizing_status,'exact_repeat_bp':c.exact_repeat_bp,'lower_bound_bp':c.lower_bound_bp,
                      'left_boundary_status':c.left_boundary_status,'right_boundary_status':c.right_boundary_status,
                      'context_limited':str(c.context_limited).lower(),'prior_overlap_bp':c.prior_overlap_bp,
                      'hypothesis_count':c.hypothesis_count,'call_status':c.call_status,'test_status':'PASS' if ok else 'FAIL'})
        return c,ok

    cag=m.canonical_motif('CAG')
    seq='GGGTTT'+'CAG'*20+'AACCGG'
    add('exact_span',seq,6,66,['CAG'],'SPAN','FULL_READ',lambda c:c.sizing_status=='EXACT_SPAN' and c.exact_repeat_bp==60 and c.interval_upper_bp==60 and c.canonical_motif==cag)
    seq='CAG'*20+'AACCGG'
    add('left_censored',seq,0,60,['CAG'],'LEFT_CENSORED','FULL_READ',lambda c:c.sizing_status=='LOWER_BOUND_LEFT_CENSORED' and c.exact_repeat_bp is None and c.lower_bound_bp>=55 and c.left_boundary_status=='CENSORED_BY_GEOMETRY')
    seq='GGGTTT'+'CAG'*20
    add('right_censored',seq,6,66,['CAG'],'RIGHT_CENSORED','FULL_READ',lambda c:c.sizing_status=='LOWER_BOUND_RIGHT_CENSORED' and c.exact_repeat_bp is None and c.lower_bound_bp>=55 and c.right_boundary_status=='CENSORED_BY_GEOMETRY')
    seq='CAG'*20
    add('both_censored',seq,0,60,['CAG'],'BOTH_CENSORED','FULL_READ',lambda c:c.sizing_status=='LOWER_BOUND_BOTH_CENSORED' and c.exact_repeat_bp is None and c.lower_bound_bp>=55)
    seq='CAG'*20+'AACCGG'
    add('projection_window_edge',seq,0,60,['CAG'],'SPAN','PROJECTION_WINDOW',lambda c:c.sizing_status=='CONTEXT_LIMITED_LOWER_BOUND' and c.context_limited and c.left_boundary_status=='CONTEXT_EDGE')
    seq='A'*80+'GGGG'+'CAG'*10+'TTTT'+'A'*100
    add('remote_repeat_decoy',seq,84,114,['CAG'],'SPAN','FULL_READ',lambda c:c.canonical_motif==cag and 27<=c.repeat_bp_observed<=36 and c.prior_overlap_bp>=20)
    mot='ACGTTGCA'; seq='GGG'+mot*8+'TTT'; truth=m.canonical_motif(mot)
    add('denovo_no_catalog',seq,3,3+len(mot)*8,[],'SPAN','FULL_READ',lambda c:c.canonical_motif==truth and c.motif_source.startswith('DENOVO'))
    mot='GGGCCC'; seq='ATGCAT'+mot*12+'TACG'; truth=m.canonical_motif(mot)
    add('denovo_rescue_wrong_catalog',seq,6,6+len(mot)*12,['CAG'],'SPAN','FULL_READ',lambda c:c.canonical_motif==truth and c.motif_source.startswith('DENOVO'))
    mot='ACGTTGCAACCTGATCGTACGATTCGGAATCGTACGA'; seq='GATTACA'+mot*4+'CCGT'; truth=m.canonical_motif(mot)
    add('denovo_period37',seq,7,7+len(mot)*4,[],'SPAN','FULL_READ',lambda c:c.canonical_motif==truth and len(c.canonical_motif)==37 and c.motif_source.startswith('DENOVO'))

    fields=list(cases[0]); detail=a.outdir/'boundary_censor_denovo_selftest.tsv'; tmp=detail.with_name('.'+detail.name+'.part')
    with tmp.open('w',newline='') as fh:
        wr=csv.DictWriter(fh,fieldnames=fields,delimiter='\t');wr.writeheader();wr.writerows(cases)
    os.replace(tmp,detail)
    passed=sum(r['test_status']=='PASS' for r in cases)
    metrics=[('fixture_count',len(cases)),('fixture_pass_count',passed),('geometry_censoring_cases',4),('projection_context_case',1),('boundary_decoy_case',1),('denovo_cases',3),('max_denovo_period_tested',37),('selftest_status','PASS' if passed==len(cases) else 'FAIL')]
    qc=a.outdir/'boundary_censor_denovo_selftest.qc.tsv'; tmp=qc.with_name('.'+qc.name+'.part')
    with tmp.open('w',newline='') as fh:
        wr=csv.writer(fh,delimiter='\t');wr.writerow(['metric','value']);wr.writerows(metrics)
    os.replace(tmp,qc); print(qc.read_text(),end='')
    if passed!=len(cases): raise SystemExit(3)
if __name__=='__main__': main()
