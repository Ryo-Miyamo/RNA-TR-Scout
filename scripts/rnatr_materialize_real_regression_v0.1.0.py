#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,gzip,os,re,sqlite3,sys,statistics,math,importlib.util,json
from pathlib import Path

FASTQ_RE=re.compile(r"(/[A-Za-z0-9_./()\-+,:=@]+\.f(?:ast)?q(?:\.gz)?)")

def open_text(path:Path):
    return gzip.open(path,'rt',encoding='utf-8',errors='replace') if str(path).endswith('.gz') else path.open('r',encoding='utf-8',errors='replace')

def load_module(path:Path):
    spec=importlib.util.spec_from_file_location('rnatr_general_v020',path)
    mod=importlib.util.module_from_spec(spec); sys.modules[spec.name]=mod; spec.loader.exec_module(mod); return mod

def extract_paths_from_text(path:Path):
    out=[]
    if not path.is_file(): return out
    try:
        txt=path.read_text(encoding='utf-8',errors='replace')
    except Exception: return out
    for m in FASTQ_RE.finditer(txt):
        p=Path(m.group(1))
        if p.is_file(): out.append(p)
    return out

def paths_from_sqlite(db:Path):
    out=[]
    if not db.is_file(): return out
    try:
        con=sqlite3.connect(str(db))
        tables=[r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        for table in tables:
            cols=[r[1] for r in con.execute(f'PRAGMA table_info("{table}")')]
            for col in cols:
                lc=col.lower()
                if not any(k in lc for k in ('path','file','artifact','evidence','root')): continue
                try:
                    rows=con.execute(f'SELECT "{col}" FROM "{table}" WHERE CAST("{col}" AS TEXT) LIKE ? LIMIT 200',('%.fastq%',)).fetchall()
                except Exception:
                    continue
                for (v,) in rows:
                    if not v: continue
                    p=Path(str(v))
                    if p.is_file(): out.append(p)
        con.close()
    except Exception:
        pass
    return out

def walk_fastqs(root:Path,max_files=500):
    out=[]
    if not root.is_dir(): return out
    for dp,dn,fn in os.walk(root):
        # Skip hidden/cache directories that cannot contain project FASTQs.
        dn[:] = [d for d in dn if d not in {'.git','__pycache__','.cache','lost+found'}]
        for f in fn:
            fl=f.lower()
            if fl.endswith(('.fastq.gz','.fq.gz','.fastq','.fq')):
                out.append(Path(dp)/f)
                if len(out)>=max_files: return out
    return out

def candidate_score(p:Path):
    s=str(p).lower(); score=0
    if 'target_window' in s or 'target_windows' in s: score+=150
    if 'candidate' in s: score+=120
    if 'encsr307shm' in s: score+=100
    if 'pilot100k' in s or 'sample100k' in s: score+=60
    if 'intermediate' in s: score+=30
    try:
        size=p.stat().st_size
        if size<1_000_000_000: score+=30
        elif size>2_000_000_000: score-=200
    except Exception: pass
    return score

def scan_fastq(path:Path,read_ids:set[str],projection_ids:set[str]):
    read_hits={}; proj_hits={}
    try:
        with open_text(path) as fh:
            while True:
                h=fh.readline()
                if not h: break
                seq=fh.readline().strip(); plus=fh.readline(); qual=fh.readline()
                if not qual: break
                header=h[1:].strip() if h.startswith('@') else h.strip()
                token=header.split()[0] if header else ''
                if token in read_ids: read_hits.setdefault(token,seq)
                if token in projection_ids: proj_hits.setdefault(token,seq)
                # Window FASTQ headers may carry the projection/read id inside a compound header.
                if len(read_hits)<len(read_ids) or len(proj_hits)<len(projection_ids):
                    for rid in read_ids-read_hits.keys():
                        if rid and rid in header: read_hits[rid]=seq
                    for pid in projection_ids-proj_hits.keys():
                        if pid and pid in header: proj_hits[pid]=seq
                if len(read_hits)==len(read_ids) and len(proj_hits)==len(projection_ids): break
    except Exception as e:
        return {},{},f'{type(e).__name__}:{e}'
    return read_hits,proj_hits,''

def percentile(vals,q):
    if not vals: return None
    s=sorted(vals); idx=max(0,min(len(s)-1,math.ceil(q*len(s))-1)); return s[idx]

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--project-root',type=Path,required=True)
    ap.add_argument('--seed',type=Path,required=True)
    ap.add_argument('--projection',type=Path,required=True)
    ap.add_argument('--caller',type=Path,required=True)
    ap.add_argument('--output-fixtures',type=Path,required=True)
    ap.add_argument('--output-calls',type=Path,required=True)
    ap.add_argument('--output-qc',type=Path,required=True)
    ap.add_argument('--fastq',type=Path,action='append',default=[])
    a=ap.parse_args()
    for p in [a.seed,a.projection,a.caller]:
        if not p.is_file(): raise SystemExit(f'ERROR: missing required file: {p}')
    with a.seed.open() as fh:
        seeds=list(csv.DictReader(fh,delimiter='\t'))
    if not seeds: raise SystemExit('ERROR: seed manifest empty')
    required_seed={'projection_id','read_id','canonical_motif','repeat_bp_estimate'}
    if not required_seed.issubset(seeds[0]): raise SystemExit('ERROR: seed manifest missing required fields')
    pids={r['projection_id'] for r in seeds}; rids={r['read_id'] for r in seeds}
    proj={}
    with open_text(a.projection) as fh:
        rd=csv.DictReader(fh,delimiter='\t')
        req={'projection_id','read_id','projected_target_read_start','projected_target_read_end','candidate_window_read_start','candidate_window_read_end'}
        if not req.issubset(rd.fieldnames or []): raise SystemExit('ERROR: projection table missing raw-coordinate fields')
        for row in rd:
            if row['projection_id'] in pids: proj[row['projection_id']]=row
    missing_proj=pids-set(proj)
    if missing_proj: raise SystemExit(f'ERROR: projection rows missing for {len(missing_proj)} seed ids')

    candidates=[]
    candidates.extend(a.fastq)
    text_sources=[
        a.project_root/'qc/11_candidates/ENCSR307SHM_pilot100k_mm2splice_v1/candidate_materialization_qc.tsv',
        a.project_root/'qc/11_projection/ENCSR307SHM_pilot100k_mm2splice_v1/v0.3.3/raw_projection_qc.v0.3.3.tsv',
        a.project_root/'scripts/11d3_project_targets_to_raw_reads_secondary_seq_fixed.sh',
        a.project_root/'results/11_mapping/ENCSR307SHM_pilot100k_mm2splice_v1/ENCSR307SHM_pilot100k_mm2splice_v1.mapper_command.sh',
    ]
    # Also inspect small manifests/QC/checkpoint text files around the target pipeline.
    text_roots=[
        a.project_root/'qc/11_candidates/ENCSR307SHM_pilot100k_mm2splice_v1',
        a.project_root/'qc/11_projection/ENCSR307SHM_pilot100k_mm2splice_v1',
        a.project_root/'results/11_projection/ENCSR307SHM_pilot100k_mm2splice_v1',
        a.project_root/'metadata/build_tracker/checkpoints/20260803_182703_step11_rna_repeat_pilot',
    ]
    for root in text_roots:
        if root.is_dir():
            for src in root.rglob('*'):
                if src.is_file() and src.suffix.lower() in {'.tsv','.txt','.md','.json','.sh'} and src.stat().st_size<20_000_000:
                    text_sources.append(src)
    for src in text_sources: candidates.extend(extract_paths_from_text(src))
    candidates.extend(paths_from_sqlite(a.project_root/'metadata/ssot/rnatr_ssot.sqlite'))
    if not candidates:
        for root in [a.project_root/'results',Path('/media/tokushimaneuro02/T9/rnatr_reference'),Path('/media/tokushimaneuro02/T9/rnatr_project')]:
            candidates.extend(walk_fastqs(root))
    # If discovered paths exist but none are obvious/small, augment with targeted walk.
    if not any(('candidate' in str(p).lower() or 'window' in str(p).lower() or 'encsr307shm' in str(p).lower()) for p in candidates):
        for root in [Path('/media/tokushimaneuro02/T9/rnatr_reference'),a.project_root/'results']:
            candidates.extend(walk_fastqs(root))
    uniq=[]; seen=set()
    for p in candidates:
        try:p=p.resolve()
        except Exception: pass
        if p in seen or not p.is_file(): continue
        seen.add(p); uniq.append(p)
    uniq.sort(key=lambda p:(-candidate_score(p),p.stat().st_size if p.exists() else 10**18,str(p)))

    read_seq={}; proj_seq={}; source_for_read={}; source_for_proj={}; scanned=[]
    for p in uniq[:80]:
        try:size=p.stat().st_size
        except Exception: continue
        # Avoid silently decompressing enormous full-depth datasets during a 60-read fixture materialization.
        if size>2_000_000_000 and candidate_score(p)<0: continue
        rh,ph,err=scan_fastq(p,rids-set(read_seq),pids-set(proj_seq))
        scanned.append((str(p),size,len(rh),len(ph),err))
        for k,v in rh.items(): read_seq.setdefault(k,v); source_for_read.setdefault(k,str(p))
        for k,v in ph.items(): proj_seq.setdefault(k,v); source_for_proj.setdefault(k,str(p))
        if all((r['projection_id'] in proj_seq) or (r['read_id'] in read_seq) for r in seeds): break
    missing=[r for r in seeds if r['projection_id'] not in proj_seq and r['read_id'] not in read_seq]
    if missing:
        report=a.output_qc.with_suffix('.fastq_discovery.tsv')
        report.parent.mkdir(parents=True,exist_ok=True)
        with report.open('w',newline='') as fh:
            wr=csv.writer(fh,delimiter='\t'); wr.writerow(['path','bytes','new_read_hits','new_projection_hits','error']); wr.writerows(scanned)
        raise SystemExit(f'ERROR: could not materialize {len(missing)}/{len(seeds)} seed rows; discovery report: {report}')

    fixtures=[]
    for r in seeds:
        pr=proj[r['projection_id']]
        ps=int(pr['projected_target_read_start']); pe=int(pr['projected_target_read_end'])
        if r['projection_id'] in proj_seq:
            seq=proj_seq[r['projection_id']]
            ws=int(pr['candidate_window_read_start']); we=int(pr['candidate_window_read_end'])
            prior_start=ps-ws; prior_end=pe-ws; mode='PROJECTION_WINDOW_FASTQ'; source=source_for_proj[r['projection_id']]
        else:
            seq=read_seq[r['read_id']]; prior_start=ps; prior_end=pe; mode='FULL_RAW_READ_FASTQ'; source=source_for_read[r['read_id']]
        if not (0<=prior_start<prior_end<=len(seq)):
            raise SystemExit(f"ERROR: invalid materialized prior coordinates for {r['projection_id']}: {prior_start},{prior_end},len={len(seq)} mode={mode}")
        x=dict(r); x.update({'sequence':seq,'prior_start':prior_start,'prior_end':prior_end,
                             'raw_sequence_source':source,'materialization_mode':mode,
                             'fixture_status':'MATERIALIZED_RAW_SEQUENCE'})
        fixtures.append(x)
    ffields=list(fixtures[0].keys())
    a.output_fixtures.parent.mkdir(parents=True,exist_ok=True)
    tmp=a.output_fixtures.with_name('.'+a.output_fixtures.name+'.part')
    with tmp.open('w',newline='') as fh:
        wr=csv.DictWriter(fh,fieldnames=ffields,delimiter='\t'); wr.writeheader(); wr.writerows(fixtures)
    os.replace(tmp,a.output_fixtures)

    c=load_module(a.caller); calls=[]; deltas=[]; motif_ok=[]
    for r in fixtures:
        call=c.call_repeat(r['sequence'],int(r['prior_start']),int(r['prior_end']),[r['canonical_motif']])
        d=call.__dict__.copy(); old=float(r['repeat_bp_estimate'])
        delta=float(call.repeat_bp_observed)-old; deltas.append(abs(delta))
        canon_truth=c.canonical_motif(r['canonical_motif']); ok=(call.canonical_motif==canon_truth); motif_ok.append(ok)
        calls.append({'projection_id':r['projection_id'],'read_id':r['read_id'],'representative_locus_id':r.get('representative_locus_id',''),
                      'frozen_canonical_motif':r['canonical_motif'],'frozen_repeat_bp_estimate':r['repeat_bp_estimate'],
                      'new_canonical_motif':call.canonical_motif,'motif_concordant':str(ok).lower(),
                      'new_repeat_bp_observed':call.repeat_bp_observed,'new_minus_frozen_bp':delta,
                      'materialization_mode':r['materialization_mode'],'raw_sequence_source':r['raw_sequence_source'],**d})
    a.output_calls.parent.mkdir(parents=True,exist_ok=True)
    tmp=a.output_calls.with_name('.'+a.output_calls.name+'.part')
    with tmp.open('w',newline='') as fh:
        wr=csv.DictWriter(fh,fieldnames=list(calls[0]),delimiter='\t'); wr.writeheader(); wr.writerows(calls)
    os.replace(tmp,a.output_calls)
    modes={m:sum(r['materialization_mode']==m for r in fixtures) for m in sorted({r['materialization_mode'] for r in fixtures})}
    qc=[('seed_rows',len(seeds)),('materialized_rows',len(fixtures)),('unique_raw_sequence_sources',len({r['raw_sequence_source'] for r in fixtures})),
        ('projection_window_rows',modes.get('PROJECTION_WINDOW_FASTQ',0)),('full_raw_read_rows',modes.get('FULL_RAW_READ_FASTQ',0)),
        ('caller_completed_rows',len(calls)),('motif_concordance_fraction',sum(motif_ok)/len(motif_ok)),
        ('abs_new_minus_frozen_median_bp',statistics.median(deltas)),('abs_new_minus_frozen_p95_bp',percentile(deltas,.95)),
        ('compound_calls',sum(r['compound_status']=='COMPOUND' for r in calls)),('interrupted_single_motif_calls',sum(r['compound_status']=='INTERRUPTED_SINGLE_MOTIF' for r in calls)),
        ('comparison_semantics','REGRESSION_DISCOVERY_NOT_ACCEPTANCE_THRESHOLD'),('regression_status','PASS_COMPLETION_DESCRIPTIVE')]
    a.output_qc.parent.mkdir(parents=True,exist_ok=True)
    tmp=a.output_qc.with_name('.'+a.output_qc.name+'.part')
    with tmp.open('w',newline='') as fh:
        wr=csv.writer(fh,delimiter='\t'); wr.writerow(['metric','value']); wr.writerows(qc)
    os.replace(tmp,a.output_qc)
    discovery=a.output_qc.with_suffix('.fastq_discovery.tsv')
    with discovery.open('w',newline='') as fh:
        wr=csv.writer(fh,delimiter='\t'); wr.writerow(['path','bytes','new_read_hits','new_projection_hits','error']); wr.writerows(scanned)
    print(a.output_qc.read_text(),end='')

if __name__=='__main__': main()
