#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path

VERSION="rnatr_map_ont_cdna_v0.1.0"
MANIFEST_VERSION="rnatr_mapping_resource_manifest_v0.1.0"
PARAMETER_SET_ID="rnatr_mm2_splice_cDNA_v0.3.1"
DEFAULT_MANIFEST=Path("config/mapping/ont_cdna_v0.1.0/resource_manifest.json")

class MappingError(RuntimeError): pass

def sha256_file(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(8*1024*1024), b""): h.update(block)
    return h.hexdigest()

def ensure_regular(path: Path) -> None:
    if not path.is_file() or path.is_symlink():
        raise MappingError(f"required regular file missing/invalid: {path}")

def load_manifest(path: Path) -> dict:
    ensure_regular(path)
    obj=json.loads(path.read_text(encoding="utf-8"))
    if obj.get("mapping_resource_manifest_version") != MANIFEST_VERSION:
        raise MappingError("unsupported mapping resource manifest")
    if obj.get("parameter_set_id") != PARAMETER_SET_ID:
        raise MappingError("unexpected mapping parameter set")
    return obj

def resolve_resources(root: Path, manifest: dict) -> dict[str,Path]:
    out={}
    for role,entry in sorted(manifest["resources"].items()):
        rel=Path(entry["relative_path"])
        if rel.is_absolute() or ".." in rel.parts or not rel.parts:
            raise MappingError(f"unsafe mapping resource path: {role}: {rel}")
        p=(root/rel).resolve()
        try: p.relative_to(root)
        except ValueError as exc: raise MappingError(f"resource escapes root: {p}") from exc
        ensure_regular(p)
        actual=sha256_file(p)
        if actual != entry["sha256"]:
            raise MappingError(f"mapping resource SHA drift: {role}: {actual} != {entry['sha256']}")
        out[role]=p
    return out

def tool_version(exe: str) -> str:
    p=shutil.which(exe)
    if not p: raise MappingError(f"required executable missing: {exe}")
    proc=subprocess.run([p,"--version"],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    if proc.returncode: raise MappingError(f"{exe} --version failed")
    return proc.stdout.strip().splitlines()[0]

def self_test() -> int:
    rg="@RG\\tID:test\\tSM:test\\tPL:ONT\\tLB:ONT_cDNA"
    if "\t" in rg: raise MappingError("read-group contains literal tab")
    print("SELF_TEST\tPASS")
    print(f"version\t{VERSION}")
    print(f"parameter_set_id\t{PARAMETER_SET_ID}")
    return 0

def main() -> int:
    ap=argparse.ArgumentParser(description="Portable RNA-TR-Scout ONT-cDNA splice-aware mapping entry")
    modes=ap.add_mutually_exclusive_group(required=True)
    modes.add_argument("--self-test",action="store_true")
    modes.add_argument("--run",action="store_true")
    ap.add_argument("--project-root",type=Path,default=Path.cwd())
    ap.add_argument("--resource-root",type=Path)
    ap.add_argument("--resource-manifest",type=Path)
    ap.add_argument("--fastq",type=Path)
    ap.add_argument("--output-bam",type=Path)
    ap.add_argument("--run-id")
    ap.add_argument("--sample-id")
    ap.add_argument("--expected-fastq-sha256",default="")
    ap.add_argument("--work-dir",type=Path)
    args=ap.parse_args()
    if args.self_test: return self_test()
    for name in ("fastq","output_bam","run_id","sample_id"):
        if getattr(args,name) in (None,""): ap.error(f"--{name.replace('_','-')} is required")
    project_root=args.project_root.resolve()
    resource_root=args.resource_root.resolve() if args.resource_root else project_root
    manifest_path=args.resource_manifest.resolve() if args.resource_manifest else project_root/DEFAULT_MANIFEST
    manifest=load_manifest(manifest_path)
    resources=resolve_resources(resource_root,manifest)
    fastq=args.fastq.resolve(); ensure_regular(fastq)
    fastq_sha=sha256_file(fastq)
    if args.expected_fastq_sha256 and fastq_sha != args.expected_fastq_sha256:
        raise MappingError("FASTQ SHA mismatch")
    mmv=tool_version("minimap2"); samv=tool_version("samtools")
    if mmv != manifest["tool_contract"]["minimap2"]:
        raise MappingError(f"minimap2 version mismatch: {mmv}")
    if not samv.startswith("samtools "+manifest["tool_contract"]["samtools"]):
        raise MappingError(f"samtools version mismatch: {samv}")
    output_bam=args.output_bam.resolve()
    output_bai=Path(str(output_bam)+".bai")
    output_manifest=Path(str(output_bam)+".mapping_manifest.json")
    for p in (output_bam,output_bai,output_manifest):
        if p.exists() or p.is_symlink(): raise MappingError(f"refusing overwrite: {p}")
    output_bam.parent.mkdir(parents=True,exist_ok=True)
    work=args.work_dir.resolve() if args.work_dir else output_bam.parent/(output_bam.name+".work")
    if work.exists(): raise MappingError(f"work dir exists: {work}")
    work.mkdir(parents=True)
    rg=f"@RG\\tID:{args.run_id}\\tSM:{args.sample_id}\\tPL:ONT\\tLB:ONT_cDNA"
    mm_cmd=["minimap2","-ax","splice","-t","16","--junc-bed",str(resources["junction_bed12"]),
            "--secondary=yes","-N","10","--MD","--cs=long","-R",rg,
            str(resources["reference_mmi"]),str(fastq)]
    sort_cmd=["samtools","sort","-@","8","-m","1G","-T",str(work/"sorttmp"),"-o",str(output_bam),"-"]
    mm_log=Path(str(output_bam)+".minimap2.log"); sort_log=Path(str(output_bam)+".samtools_sort.log")
    started=time.perf_counter()
    with mm_log.open("wb") as me, sort_log.open("wb") as se:
        mm=subprocess.Popen(mm_cmd,stdout=subprocess.PIPE,stderr=me)
        assert mm.stdout is not None
        so=subprocess.Popen(sort_cmd,stdin=mm.stdout,stdout=subprocess.DEVNULL,stderr=se)
        mm.stdout.close()
        src=so.wait(); mrc=mm.wait()
    if mrc or src: raise MappingError(f"mapping pipeline failed minimap2={mrc} sort={src}")
    qc=subprocess.run(["samtools","quickcheck","-v",str(output_bam)],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    if qc.returncode: raise MappingError("samtools quickcheck failed: "+qc.stdout)
    idx=subprocess.run(["samtools","index","-@","8",str(output_bam)],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    if idx.returncode: raise MappingError("samtools index failed: "+idx.stdout)
    elapsed=time.perf_counter()-started
    result={"mapping_entry_version":VERSION,"mapping_resource_manifest_version":MANIFEST_VERSION,
            "parameter_set_id":PARAMETER_SET_ID,"profile":manifest["profile"],
            "run_id":args.run_id,"sample_id":args.sample_id,
            "tools":{"minimap2":mmv,"samtools":samv},
            "input":{"fastq":str(fastq),"fastq_sha256":fastq_sha},
            "resources":{r:{"path":str(p),"sha256":manifest["resources"][r]["sha256"]} for r,p in resources.items()},
            "commands":{"minimap2":mm_cmd,"samtools_sort":sort_cmd},
            "outputs":{"bam":str(output_bam),"bam_sha256":sha256_file(output_bam),
                       "bai":str(output_bai),"bai_sha256":sha256_file(output_bai)},
            "mapping_wall_seconds":elapsed,"status":"PASS"}
    fd,tmp=tempfile.mkstemp(prefix="."+output_manifest.name+".",suffix=".part",dir=str(output_manifest.parent))
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as fh:
            json.dump(result,fh,indent=2,sort_keys=True); fh.write("\n"); fh.flush(); os.fsync(fh.fileno())
        os.replace(tmp,output_manifest)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
    print("RNATR_ONT_CDNA_MAPPING\tPASS")
    print(f"bam\t{output_bam}")
    print(f"manifest\t{output_manifest}")
    return 0

if __name__=="__main__":
    try: raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}",file=sys.stderr); raise
