#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

VERSION = "rnatr_core_production_entry_v0.1.0"
RESOURCE_MANIFEST_VERSION = "rnatr_core_resource_manifest_v0.1.0"
RUNTIME_CONFIG_VERSION = "rnatr_core_runtime_config_v0.1.0"
DEFAULT_RESOURCE_MANIFEST_RELATIVE = Path("config/core_runtime/v0.1.0/resource_manifest.json")

class EntryError(RuntimeError):
    pass

def sha256_file(path: Path, chunk: int = 8 * 1024 * 1024) -> str:
    h=hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            block=fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()

def ensure_regular(path: Path) -> None:
    if not path.is_file() or path.is_symlink():
        raise EntryError(f"required regular file missing/invalid: {path}")

def canonical_json(obj: Any) -> bytes:
    return (json.dumps(obj,indent=2,sort_keys=True)+"\n").encode("utf-8")

def atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix="."+path.name+".",suffix=".tmp",dir=str(path.parent))
    try:
        with os.fdopen(fd,"wb") as fh:
            fh.write(payload); fh.flush(); os.fsync(fh.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name): os.unlink(name)

def load_resource_manifest(project_root: Path, manifest_path: Path) -> dict[str,Any]:
    ensure_regular(manifest_path)
    manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("resource_manifest_version")!=RESOURCE_MANIFEST_VERSION:
        raise EntryError("unsupported resource-manifest version")
    for key in ("components","catalogs","production_code"):
        if not isinstance(manifest.get(key),dict) or not manifest[key]:
            raise EntryError(f"resource manifest lacks {key}")
    return manifest

def resolve_entry(project_root: Path, role: str, entry: dict[str,Any]) -> tuple[Path,str]:
    rel=Path(str(entry.get("relative_path","")))
    if rel.is_absolute() or ".." in rel.parts or not rel.parts:
        raise EntryError(f"unsafe resource relative path: {role}: {rel}")
    path=(project_root/rel).resolve()
    try:
        path.relative_to(project_root)
    except ValueError as exc:
        raise EntryError(f"resource escapes project root: {role}: {path}") from exc
    ensure_regular(path)
    expected=str(entry.get("sha256",""))
    actual=sha256_file(path)
    if actual!=expected:
        raise EntryError(f"resource SHA drift: {role}: {path}: {actual} != {expected}")
    return path,expected

def build_runtime_config(project_root: Path, manifest: dict[str,Any]) -> tuple[dict[str,Any],dict[str,Path]]:
    code={}
    for role,entry in sorted(manifest["production_code"].items()):
        code[role]=resolve_entry(project_root,f"production_code:{role}",entry)[0]
    config={
        "runtime_config_version":RUNTIME_CONFIG_VERSION,
        "scientific_input_contract":manifest["scientific_input_contract"],
        "mapping_timing_boundary":manifest["mapping_timing_boundary"],
        "assignment_schema_dir":str((project_root/manifest["assignment_schema_dir"]).resolve()),
        "catalog_root":str((project_root/manifest["catalog_root"]).resolve()),
        "schema_dir":str((project_root/manifest["schema_dir"]).resolve()),
        "components":{},"catalogs":{},
    }
    for section in ("components","catalogs"):
        for role,entry in sorted(manifest[section].items()):
            path,expected=resolve_entry(project_root,f"{section}:{role}",entry)
            config[section][role]={"path":str(path),"sha256":expected}
    return config,code

def control_root_for(work_root: Path, explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.resolve()
    return work_root.parent/(work_root.name+".control")

def prepare_control(mode: str, control_root: Path, runtime_config: dict[str,Any], resource_manifest: Path) -> Path:
    config_path=control_root/"runtime_config.json"
    provenance_path=control_root/"production_entry_provenance.json"
    payload=canonical_json(runtime_config)
    provenance=canonical_json({
        "entry_version":VERSION,
        "resource_manifest_path":str(resource_manifest.resolve()),
        "resource_manifest_sha256":sha256_file(resource_manifest),
        "runtime_config_sha256":hashlib.sha256(payload).hexdigest(),
    })
    if mode=="--start":
        if control_root.exists():
            raise EntryError(f"start requires unused control root: {control_root}")
        control_root.mkdir(parents=True)
        atomic_write(config_path,payload)
        atomic_write(provenance_path,provenance)
    else:
        ensure_regular(config_path); ensure_regular(provenance_path)
        if config_path.read_bytes()!=payload:
            raise EntryError("resume runtime config differs from the start-time reviewed config")
        if provenance_path.read_bytes()!=provenance:
            raise EntryError("resume production-entry provenance differs from current resource manifest")
    return config_path

def run(args: argparse.Namespace) -> int:
    project_root=args.project_root.resolve()
    if not project_root.is_dir():
        raise EntryError(f"project root missing: {project_root}")
    manifest_path=(args.resource_manifest.resolve() if args.resource_manifest else project_root/DEFAULT_RESOURCE_MANIFEST_RELATIVE)
    manifest=load_resource_manifest(project_root,manifest_path)
    runtime_config,code=build_runtime_config(project_root,manifest)
    work_root=args.work_root.resolve(); output_root=args.output_root.resolve()
    control_root=control_root_for(work_root,args.control_root)
    mode="--start" if args.start else "--resume"
    config_path=prepare_control(mode,control_root,runtime_config,manifest_path)
    cmd=[
        sys.executable,"-u",str(code["orchestrator"]),mode,
        "--runtime-config",str(config_path),
        "--unit-runner",str(code["unit_runner"]),
        "--bam",str(args.bam.resolve()),
        "--reads-fastq",str(args.reads_fastq.resolve()),
        "--run-id",args.run_id,"--sample-id",args.sample_id,
        "--work-root",str(work_root),"--output-root",str(output_root),
        "--shards",str(args.shards),
        "--max-unit-workers",str(args.max_unit_workers),
        "--caller-workers",str(args.caller_workers),
        "--pythonhashseed",str(args.pythonhashseed),
    ]
    if args.expected_bam_sha256:
        cmd += ["--expected-bam-sha256",args.expected_bam_sha256]
    if args.expected_fastq_sha256:
        cmd += ["--expected-fastq-sha256",args.expected_fastq_sha256]
    if args.audit_recover_published_state:
        cmd[3]="--audit-recover-published-state"
    proc=subprocess.run(cmd)
    return proc.returncode

def self_test() -> int:
    with tempfile.TemporaryDirectory(prefix="rnatr_entry_selftest_") as td:
        root=Path(td)/"project"; root.mkdir()
        scripts=root/"scripts"; scripts.mkdir()
        payload=scripts/"payload.py"; payload.write_text("print('x')\n",encoding="utf-8")
        digest=sha256_file(payload)
        manifest={
            "resource_manifest_version":RESOURCE_MANIFEST_VERSION,
            "scientific_input_contract":"MAPPED_BAM_PLUS_READ_COHERENT_SOURCE_FASTQ",
            "mapping_timing_boundary":"FASTQ_TO_BAM_MAPPING_EXCLUDED",
            "assignment_schema_dir":"schema03","catalog_root":"catalogs","schema_dir":"schema04",
            "production_code":{"orchestrator":{"relative_path":"scripts/payload.py","sha256":digest},"unit_runner":{"relative_path":"scripts/payload.py","sha256":digest},"prebiology_smoke":{"relative_path":"scripts/payload.py","sha256":digest}},
            "components":{"x":{"relative_path":"scripts/payload.py","sha256":digest}},
            "catalogs":{"y":{"relative_path":"scripts/payload.py","sha256":digest}},
        }
        mp=root/"manifest.json"; mp.write_bytes(canonical_json(manifest))
        loaded=load_resource_manifest(root,mp)
        config,code=build_runtime_config(root,loaded)
        if config["components"]["x"]["sha256"]!=digest or code["orchestrator"]!=payload.resolve():
            raise EntryError("self-test runtime config failed")
        control=Path(td)/"control"
        cp=prepare_control("--start",control,config,mp)
        prepare_control("--resume",control,config,mp)
        if not cp.is_file(): raise EntryError("self-test control file missing")
    print("SELF_TEST\tPASS")
    print(f"version\t{VERSION}")
    return 0

def main() -> int:
    p=argparse.ArgumentParser(description="Generic RNA-TR-Scout mapped-BAM + source-FASTQ Core production entry point")
    modes=p.add_mutually_exclusive_group(required=True)
    modes.add_argument("--self-test",action="store_true")
    modes.add_argument("--start",action="store_true")
    modes.add_argument("--resume",action="store_true")
    p.add_argument("--project-root",type=Path,default=Path.cwd())
    p.add_argument("--resource-manifest",type=Path)
    p.add_argument("--bam",type=Path)
    p.add_argument("--reads-fastq",type=Path)
    p.add_argument("--run-id")
    p.add_argument("--sample-id")
    p.add_argument("--work-root",type=Path)
    p.add_argument("--output-root",type=Path)
    p.add_argument("--control-root",type=Path)
    p.add_argument("--shards",type=int)
    p.add_argument("--max-unit-workers",type=int)
    p.add_argument("--caller-workers",type=int)
    p.add_argument("--pythonhashseed",default="0")
    p.add_argument("--expected-bam-sha256",default="")
    p.add_argument("--expected-fastq-sha256",default="")
    p.add_argument("--audit-recover-published-state",action="store_true")
    args=p.parse_args()
    if args.self_test: return self_test()
    for name in ("bam","reads_fastq","run_id","sample_id","work_root","output_root","shards","max_unit_workers","caller_workers"):
        if getattr(args,name) in (None,""): p.error(f"--{name.replace('_','-')} is required")
    if args.shards<1 or args.max_unit_workers<1 or args.caller_workers<1: p.error("shards/workers must be >=1")
    return run(args)

if __name__=="__main__":
    try: raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}",file=sys.stderr)
        raise
