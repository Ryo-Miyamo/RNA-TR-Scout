#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,importlib.util,sys,json,statistics,random
from pathlib import Path


def load_module(path:Path):
    spec=importlib.util.spec_from_file_location('rnatr_general_ref_v020',path)
    mod=importlib.util.module_from_spec(spec); sys.modules[spec.name]=mod; spec.loader.exec_module(mod); return mod


def mutate(seq, rate, seed):
    rng=random.Random(seed); bases='ACGT'; out=[]
    for b in seq:
        if rng.random()<rate:
            out.append(rng.choice([x for x in bases if x!=b]))
        else: out.append(b)
    return ''.join(out)


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--caller',type=Path,required=True); ap.add_argument('--outdir',type=Path,required=True); a=ap.parse_args()
    c=load_module(a.caller); a.outdir.mkdir(parents=True,exist_ok=True)
    fixtures=[]
    def add(case_id,seq,st,en,motifs,expect_status,expect_len=None,expect_lps=None):
        fixtures.append(dict(case_id=case_id,sequence=seq,prior_start=st,prior_end=en,catalog_motif=','.join(motifs),expect_status=expect_status,expect_len=expect_len,expect_lps=expect_lps))
    add('pure_cag','GGGTTT'+'CAG'*20+'AAACCC',6,66,['CAG'],'SINGLE_MOTIF',60,60)
    add('pure_ac','TTTT'+'AC'*25+'GGGG',4,54,['AC'],'SINGLE_MOTIF',50,50)
    add('interrupted_cag','GGGTTT'+'CAG'*12+'TTGGAACC'+'CAG'*10+'AAACCC',6,80,['CAG'],'INTERRUPTED_SINGLE_MOTIF',74,36)
    add('compound_cag_caa','GGGTTT'+'CAG'*12+'CAA'*10+'AAACCC',6,72,['CAG','CAA'],'COMPOUND',None,None)
    add('compound_gcc_gct','TTTT'+'GCC'*10+'GCT'*9+'GGGG',4,61,['GCC','GCT'],'COMPOUND',None,None)
    # Error-aware single motif: exact LPS should be shorter than inferred continuity.
    core='CAG'*24; err=mutate(core,0.06,17)
    add('error_cag','GGG'+err+'CCC',3,3+len(err),['CAG'],'SINGLE_MOTIF',None,None)

    rows=[]; failures=[]
    for f in fixtures:
        call=c.call_repeat(f['sequence'],f['prior_start'],f['prior_end'],f['catalog_motif'].split(','),max_denovo_period=12)
        ok_status=(call.compound_status==f['expect_status'])
        ok_len=True if f['expect_len'] is None else abs(call.repeat_bp_observed-f['expect_len'])<=2
        ok_lps=True if f['expect_lps'] is None else abs(call.lps_exact_sequence_bp-f['expect_lps'])<=2
        if f['case_id']=='error_cag':
            ok_lps = call.lps_exact_sequence_bp < call.lps_inferred_bp
        passed=ok_status and ok_len and ok_lps and call.call_status in {'PASS','LOW_CONFIDENCE'}
        row={**f,'observed_compound_status':call.compound_status,'observed_repeat_bp':call.repeat_bp_observed,
             'lps_exact_sequence_bp':call.lps_exact_sequence_bp,'lps_inferred_bp':call.lps_inferred_bp,
             'repeat_segment_count':call.repeat_segment_count,'interruption_count':call.interruption_count,
             'call_status':call.call_status,'test_status':'PASS' if passed else 'FAIL'}
        rows.append(row)
        if not passed: failures.append(row)
    out=a.outdir/'compound_interruption_lps_selftest.tsv'
    with out.open('w',newline='') as fh:
        wr=csv.DictWriter(fh,fieldnames=list(rows[0]),delimiter='\t'); wr.writeheader(); wr.writerows(rows)
    metrics=[
        ('fixture_count',len(rows)),('fixture_pass_count',sum(r['test_status']=='PASS' for r in rows)),
        ('compound_fixture_count',sum(r['expect_status']=='COMPOUND' for r in rows)),
        ('interruption_fixture_count',sum(r['expect_status']=='INTERRUPTED_SINGLE_MOTIF' for r in rows)),
        ('lps_dual_semantics_test','PASS' if next(r for r in rows if r['case_id']=='error_cag')['test_status']=='PASS' else 'FAIL'),
        ('selftest_status','PASS' if not failures else 'FAIL')]
    q=a.outdir/'compound_interruption_lps_selftest.qc.tsv'
    with q.open('w',newline='') as fh:
        wr=csv.writer(fh,delimiter='\t'); wr.writerow(['metric','value']); wr.writerows(metrics)
    print(q.read_text(),end='')
    if failures:
        print(json.dumps(failures,indent=2),file=sys.stderr); raise SystemExit(2)

if __name__=='__main__': main()
