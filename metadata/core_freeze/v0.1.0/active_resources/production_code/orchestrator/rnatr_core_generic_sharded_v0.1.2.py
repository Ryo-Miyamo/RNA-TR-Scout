#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import gzip
import hashlib
import heapq
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

VERSION = "rnatr_core_generic_sharded_bam_fastq_to_final_v0.1.2"
MANIFEST_VERSION = "rnatr_core_result_manifest_v0.1.0"
BINDING_VERSION = "rnatr_local_resource_bindings_v0.1.0"

TABLE_ORDER = (
    "read_evidence",
    "general_repeat_calls",
    "repeat_events",
    "repeat_segments",
    "repeat_interruptions",
)
KEY_FIELDS = {
    "general_repeat_calls": (("projection_id", False),),
    "read_evidence": (("evidence_id", False),),
    "repeat_events": (("evidence_id", False), ("event_index", True), ("repeat_event_id", False)),
    "repeat_segments": (
        ("evidence_id", False), ("repeat_event_id", False),
        ("segment_index", True), ("repeat_call_id", False),
    ),
    "repeat_interruptions": (
        ("evidence_id", False), ("repeat_event_id", False),
        ("interruption_index", True), ("interruption_id", False),
    ),
}

try:
    import pysam
except Exception as exc:
    pysam = None
    PYSAM_IMPORT_ERROR = repr(exc)
else:
    PYSAM_IMPORT_ERROR = ""

class ShardedRunError(RuntimeError):
    pass

def utc_now() -> str:
    import datetime as dt
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")

def sha256_file(path: Path, chunk: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()

def ensure_regular(path: Path) -> None:
    if not path.is_file() or path.is_symlink():
        raise ShardedRunError(f"required regular file missing/invalid: {path}")

def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="."+path.name+".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)

def atomic_write_json(path: Path, obj: Any) -> None:
    atomic_write_text(path, json.dumps(obj, indent=2, sort_keys=True) + "\n")

def write_tsv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sio = io.StringIO()
    w = csv.DictWriter(sio, delimiter="\t", fieldnames=fields, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    atomic_write_text(path, sio.getvalue())

def write_metrics(path: Path, items: list[tuple[str, Any]]) -> None:
    write_tsv(path, [{"metric":k,"value":v} for k,v in items], ["metric","value"])

def read_metrics(path: Path) -> dict[str, str]:
    ensure_regular(path)
    with path.open("r", encoding="utf-8", newline="") as fh:
        rows=list(csv.DictReader(fh, delimiter="\t"))
    return {r["metric"]:r["value"] for r in rows}

def read_json(path: Path) -> dict[str, Any]:
    ensure_regular(path)
    return json.loads(path.read_text(encoding="utf-8"))

def shard_index(identifier: str, count: int) -> int:
    digest=hashlib.sha256(identifier.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % count

def read_id_digest(values: set[str]) -> str:
    h=hashlib.sha256()
    for value in sorted(values):
        h.update(value.encode("utf-8")); h.update(b"\n")
    return h.hexdigest()

def data_rows(path: Path) -> int:
    with path.open("rb") as fh:
        n=sum(1 for _ in fh)
    return max(0,n-1)

def deterministic_gzip(source: Path, destination: Path) -> dict[str, Any]:
    raw=destination.open("wb")
    try:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=6, mtime=0) as gz:
            with source.open("rb") as src:
                shutil.copyfileobj(src,gz,1024*1024)
    finally:
        raw.close()
    return {"bytes":destination.stat().st_size,"sha256":sha256_file(destination)}

def partition_inputs(
    bam: Path, reads_fastq: Path, partition_root: Path, shard_count: int
) -> list[dict[str, Any]]:
    if pysam is None:
        raise ShardedRunError(f"pysam import failed: {PYSAM_IMPORT_ERROR}")
    if partition_root.exists():
        raise ShardedRunError(f"partition root already exists: {partition_root}")
    part=Path(str(partition_root)+".part")
    if part.exists():
        raise ShardedRunError(f"partition .part already exists: {part}")
    part.mkdir(parents=True)

    writers=[]
    alignment_counts=[0]*shard_count
    primary_ids=[set() for _ in range(shard_count)]
    bam_paths=[part/f"shard_{i:03d}/input.bam" for i in range(shard_count)]
    with pysam.AlignmentFile(str(bam),"rb") as source:
        try:
            for p in bam_paths:
                p.parent.mkdir(parents=True, exist_ok=True)
                writers.append(pysam.AlignmentFile(str(p),"wb",template=source))
            for rec in source.fetch(until_eof=True):
                rid=rec.query_name
                if not rid:
                    raise ShardedRunError("BAM record lacks query_name")
                idx=shard_index(rid,shard_count)
                writers[idx].write(rec)
                alignment_counts[idx]+=1
                if not rec.is_secondary and not rec.is_supplementary:
                    if rid in primary_ids[idx]:
                        raise ShardedRunError(f"duplicate primary BAM read ID: {rid}")
                    primary_ids[idx].add(rid)
        finally:
            for w in writers:
                w.close()

    fastq_paths=[part/f"shard_{i:03d}/source_reads.fastq.gz" for i in range(shard_count)]
    raw_handles=[]; gz_handles=[]
    fastq_ids=[set() for _ in range(shard_count)]
    try:
        for p in fastq_paths:
            raw=p.open("wb"); raw_handles.append(raw)
            gz_handles.append(gzip.GzipFile(filename="",mode="wb",fileobj=raw,compresslevel=0,mtime=0))
        with pysam.FastxFile(str(reads_fastq)) as fh:
            for entry in fh:
                if entry.quality is None:
                    raise ShardedRunError(f"FASTQ read lacks quality: {entry.name}")
                idx=shard_index(entry.name,shard_count)
                if entry.name in fastq_ids[idx]:
                    raise ShardedRunError(f"duplicate FASTQ read ID: {entry.name}")
                fastq_ids[idx].add(entry.name)
                header=f"@{entry.name}" + (f" {entry.comment}" if entry.comment else "")
                gz_handles[idx].write(f"{header}\n{entry.sequence}\n+\n{entry.quality}\n".encode("utf-8"))
    finally:
        for g in gz_handles:
            g.close()
        for r in raw_handles:
            r.close()

    rows=[]
    global_primary=set()
    global_fastq=set()
    for i in range(shard_count):
        if primary_ids[i] != fastq_ids[i]:
            raise ShardedRunError(
                f"per-shard BAM/FASTQ read-ID mismatch shard_{i:03d}: "
                f"bam_only={len(primary_ids[i]-fastq_ids[i])} fastq_only={len(fastq_ids[i]-primary_ids[i])}"
            )
        if global_primary.intersection(primary_ids[i]) or global_fastq.intersection(fastq_ids[i]):
            raise ShardedRunError("cross-shard duplicate read ID")
        global_primary.update(primary_ids[i]); global_fastq.update(fastq_ids[i])
        proc=subprocess.run(["samtools","quickcheck","-v",str(bam_paths[i])],
                            text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        if proc.returncode != 0:
            raise ShardedRunError(f"samtools quickcheck failed: {bam_paths[i]}: {proc.stderr.strip()}")
        rows.append({
            "shard":f"shard_{i:03d}",
            "alignment_records":alignment_counts[i],
            "primary_reads":len(primary_ids[i]),
            "fastq_reads":len(fastq_ids[i]),
            "read_id_set_sha256":read_id_digest(primary_ids[i]),
            "bam_path":str(partition_root/f"shard_{i:03d}/input.bam"),
            "bam_bytes":bam_paths[i].stat().st_size,
            "bam_sha256":sha256_file(bam_paths[i]),
            "fastq_path":str(partition_root/f"shard_{i:03d}/source_reads.fastq.gz"),
            "fastq_bytes":fastq_paths[i].stat().st_size,
            "fastq_sha256":sha256_file(fastq_paths[i]),
            "status":"PASS_EXACT_ID_SET",
        })
    if global_primary != global_fastq:
        raise ShardedRunError("global BAM/FASTQ read-ID mismatch after partition")
    os.replace(part,partition_root)
    write_tsv(
        partition_root/"partition_manifest.tsv", rows,
        ["shard","alignment_records","primary_reads","fastq_reads","read_id_set_sha256",
         "bam_path","bam_bytes","bam_sha256","fastq_path","fastq_bytes","fastq_sha256","status"]
    )
    return rows

def verify_partition(partition_root: Path, shard_count: int) -> list[dict[str,str]]:
    manifest=partition_root/"partition_manifest.tsv"
    ensure_regular(manifest)
    with manifest.open("r",encoding="utf-8",newline="") as fh:
        rows=list(csv.DictReader(fh,delimiter="\t"))
    if len(rows)!=shard_count:
        raise ShardedRunError(f"partition manifest shard count mismatch: {len(rows)} != {shard_count}")
    for i,row in enumerate(rows):
        if row["shard"] != f"shard_{i:03d}":
            raise ShardedRunError("partition manifest shard ordering/name mismatch")
        for kind in ("bam","fastq"):
            p=Path(row[f"{kind}_path"])
            ensure_regular(p)
            if p.stat().st_size != int(row[f"{kind}_bytes"]):
                raise ShardedRunError(f"partition size drift: {p}")
            if sha256_file(p) != row[f"{kind}_sha256"]:
                raise ShardedRunError(f"partition SHA drift: {p}")
        if row["primary_reads"] != row["fastq_reads"] or row["status"]!="PASS_EXACT_ID_SET":
            raise ShardedRunError(f"partition coherence state invalid: {row['shard']}")
    return rows

def validate_runtime_config(config_path: Path) -> dict[str, Any]:
    config=read_json(config_path)
    if config.get("runtime_config_version") != "rnatr_core_runtime_config_v0.1.0":
        raise ShardedRunError("unsupported runtime-config version")
    for section in ("components","catalogs"):
        mapping=config.get(section)
        if not isinstance(mapping,dict) or not mapping:
            raise ShardedRunError(f"runtime config lacks {section}")
        for role,entry in mapping.items():
            p=Path(str(entry["path"])).resolve()
            ensure_regular(p)
            if sha256_file(p) != entry["sha256"]:
                raise ShardedRunError(f"runtime config SHA drift: {section}:{role}: {p}")
    return config

def shard_state_path(work_root: Path, shard: str) -> Path:
    return work_root/"state"/f"{shard}.json"

def validate_unit_result(result_root: Path, runtime_config: dict[str,Any]) -> dict[str,Any]:
    ensure_regular(result_root/"core_result_manifest.json")
    manifest=read_json(result_root/"core_result_manifest.json")
    if manifest.get("manifest_version") != MANIFEST_VERSION:
        raise ShardedRunError(f"unit manifest version mismatch: {result_root}")
    table_rows=[]
    for table in TABLE_ORDER:
        p=result_root/f"{table}.tsv"; ensure_regular(p)
        table_rows.append({"table":table,"rows":data_rows(p),"bytes":p.stat().st_size,"sha256":sha256_file(p)})
    validator=Path(runtime_config["components"]["validator_v042_package"]["path"]).resolve()
    proc=subprocess.run([sys.executable,str(validator),"--package-dir",str(result_root)],
                        text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise ShardedRunError(f"unit package validator failed: {result_root}: {proc.stdout[-500:]} {proc.stderr[-500:]}")
    return {
        "core_result_manifest_sha256":sha256_file(result_root/"core_result_manifest.json"),
        "tables":table_rows,
        "validator_status":"PASS",
    }

def run_unit(
    *, unit_runner: Path, runtime_config_path: Path, work_root: Path,
    run_id: str, sample_id: str, shard_row: dict[str,str],
    caller_workers: int, pythonhashseed: str
) -> dict[str,Any]:
    shard=shard_row["shard"]
    unit_base=work_root/"units"/shard
    unit_base.mkdir(parents=True, exist_ok=True)
    existing_attempts=[]
    for path in unit_base.glob("attempt_*"):
        if path.is_dir():
            try:
                existing_attempts.append(int(path.name.split("_",1)[1]))
            except Exception:
                raise ShardedRunError(f"invalid unit attempt directory: {path}")
    attempt_number=(max(existing_attempts)+1) if existing_attempts else 1
    attempt_dir=unit_base/f"attempt_{attempt_number:03d}"
    attempt_dir.mkdir(parents=True, exist_ok=False)
    unit_work=attempt_dir/"work"
    unit_output=attempt_dir/"result"
    attempt_dir.parent.mkdir(parents=True,exist_ok=True)
    cmd=[
        sys.executable,str(unit_runner),"--execute",
        "--runtime-config",str(runtime_config_path),
        "--bam",shard_row["bam_path"],
        "--reads-fastq",shard_row["fastq_path"],
        "--run-id",run_id,
        "--sample-id",sample_id,
        "--work-root",str(unit_work),
        "--output-root",str(unit_output),
        "--caller-workers",str(caller_workers),
        "--pythonhashseed",pythonhashseed,
        "--expected-bam-sha256",shard_row["bam_sha256"],
        "--expected-fastq-sha256",shard_row["fastq_sha256"],
    ]
    log=attempt_dir/"unit_runner.log"
    started=time.perf_counter()
    with log.open("w",encoding="utf-8") as fh:
        proc=subprocess.run(cmd,text=True,stdout=fh,stderr=subprocess.STDOUT)
    elapsed=time.perf_counter()-started
    if proc.returncode != 0:
        raise ShardedRunError(f"generic unit failed for {shard}; see {log}")
    runtime=validate_runtime_config(runtime_config_path)
    checked=validate_unit_result(unit_output,runtime)
    state={
        "shard":shard,
        "status":"COMPLETE",
        "attempt":attempt_number,
        "completed_utc":utc_now(),
        "elapsed_seconds":elapsed,
        "input_bam_sha256":shard_row["bam_sha256"],
        "input_fastq_sha256":shard_row["fastq_sha256"],
        "output_root":str(unit_output),
        **checked,
    }
    atomic_write_json(shard_state_path(work_root,shard),state)
    return state

def verify_completed_shard(
    work_root: Path, shard_row: dict[str,str], runtime_config: dict[str,Any]
) -> dict[str,Any] | None:
    path=shard_state_path(work_root,shard_row["shard"])
    if not path.exists():
        return None
    state=read_json(path)
    if state.get("status")!="COMPLETE":
        return None
    if state.get("input_bam_sha256") != shard_row["bam_sha256"] or state.get("input_fastq_sha256") != shard_row["fastq_sha256"]:
        raise ShardedRunError(f"completed shard input guard mismatch: {shard_row['shard']}")
    result_root=Path(state["output_root"])
    checked=validate_unit_result(result_root,runtime_config)
    if checked["core_result_manifest_sha256"] != state["core_result_manifest_sha256"]:
        raise ShardedRunError(f"completed shard manifest SHA drift: {shard_row['shard']}")
    expected={r["table"]:r["sha256"] for r in state["tables"]}
    actual={r["table"]:r["sha256"] for r in checked["tables"]}
    if actual != expected:
        raise ShardedRunError(f"completed shard scientific table drift: {shard_row['shard']}")
    return state

def numeric_key(raw: bytes) -> int:
    if raw in {b"", b"."}:
        return 0
    try:
        return int(raw)
    except Exception as exc:
        raise ShardedRunError(f"invalid numeric merge key: {raw!r}") from exc

def merge_table_plain(table: str, input_paths: list[Path], output_dir: Path) -> dict[str,Any]:
    fields_spec=KEY_FIELDS[table]
    handles=[p.open("rb") for p in input_paths]
    try:
        headers=[h.readline() for h in handles]
        if not headers or any(x != headers[0] for x in headers):
            raise ShardedRunError(f"shard headers differ for {table}")
        header=headers[0]
        if not header.endswith(b"\n"):
            raise ShardedRunError(f"unterminated header for {table}")
        field_names=header.rstrip(b"\n").decode("utf-8").split("\t")
        indices=[]
        for name,numeric in fields_spec:
            if name not in field_names:
                raise ShardedRunError(f"missing merge key {name} in {table}")
            indices.append((field_names.index(name),numeric))
        previous=[None]*len(handles)
        heap=[]
        def make_key(line: bytes):
            parts=line.rstrip(b"\n").split(b"\t")
            if len(parts) != len(field_names):
                raise ShardedRunError(
                    f"column-count mismatch in {table}: {len(parts)} != {len(field_names)}"
                )
            vals=[]
            for idx,numeric in indices:
                vals.append(numeric_key(parts[idx]) if numeric else parts[idx])
            return tuple(vals)
        def push(i:int):
            line=handles[i].readline()
            if not line:
                return
            if not line.endswith(b"\n"):
                raise ShardedRunError(f"unterminated line: {input_paths[i]}")
            key=make_key(line)
            if previous[i] is not None and key < previous[i]:
                raise ShardedRunError(f"unsorted shard output: {input_paths[i]}")
            previous[i]=key
            heapq.heappush(heap,(key,i,line))
        for i in range(len(handles)):
            push(i)
        output=output_dir/f"{table}.tsv"
        tmp=output_dir/f".{table}.tsv.part"
        rows=0; last=None; digest=hashlib.sha256()
        with tmp.open("wb") as out:
            out.write(header); digest.update(header)
            while heap:
                key,i,line=heapq.heappop(heap)
                if last is not None and key==last:
                    raise ShardedRunError(f"duplicate global merge key in {table}: {key}")
                last=key
                out.write(line); digest.update(line); rows+=1
                push(i)
            out.flush(); os.fsync(out.fileno())
        os.replace(tmp,output)
        return {"table":table,"rows":rows,"bytes":output.stat().st_size,"sha256":digest.hexdigest()}
    finally:
        for h in handles:
            h.close()

def build_merged_manifest(
    *, output_part: Path, run_id: str, sample_id: str, bam: Path, reads_fastq: Path,
    runtime_config: dict[str,Any], table_rows: list[dict[str,Any]], shard_count: int
) -> tuple[dict[str,Any],dict[str,Any]]:
    resources={
        "source_bam":{"logical_id":"source_bam","kind":"BAM","bytes":bam.stat().st_size,
                      "sha256":sha256_file(bam),"binding":"resource_bindings.local.json#/resources/source_bam"},
        "source_reads":{"logical_id":"source_reads","kind":"FASTQ","bytes":reads_fastq.stat().st_size,
                        "sha256":sha256_file(reads_fastq),"binding":"resource_bindings.local.json#/resources/source_reads"},
    }
    bindings={"binding_version":BINDING_VERSION,"resources":{
        "source_bam":{"path":str(bam.resolve())},
        "source_reads":{"path":str(reads_fastq.resolve())},
    }}
    for section,kind,prefix in (
        ("catalogs","CATALOG_OR_ANNOTATION","catalog"),
        ("components","CORE_COMPONENT","component"),
    ):
        for role,entry in sorted(runtime_config[section].items()):
            p=Path(entry["path"]).resolve()
            logical=f"{prefix}:{role}"
            resources[logical]={
                "logical_id":logical,"kind":kind,"bytes":p.stat().st_size,
                "sha256":entry["sha256"],"binding":f"resource_bindings.local.json#/resources/{logical}",
            }
            bindings["resources"][logical]={"path":str(p)}
    artifacts=[]
    for row in table_rows:
        artifacts.append({
            "logical_name":row["artifact"],"table":row["table"],"path":row["path"],
            "rows":row["rows"],"bytes":row["bytes"],"sha256":row["sha256"],
            "parity_contract":row["parity_contract"],
        })
    for filename,kind in (
        ("package_manifest.tsv","PACKAGE_MANIFEST"),
        ("validation_summary.tsv","VALIDATION_SUMMARY"),
        ("performance.tsv","PERFORMANCE_INSTRUMENTATION"),
        ("input_read_coherence.tsv","INPUT_COHERENCE"),
        ("shard_manifest.tsv","SHARD_PROVENANCE"),
    ):
        p=output_part/filename; ensure_regular(p)
        artifacts.append({
            "logical_name":filename,"kind":kind,"path":filename,
            "rows":data_rows(p),"bytes":p.stat().st_size,"sha256":sha256_file(p),
            "parity_contract":"PROVENANCE_OR_QC_FIELD_SCOPED",
        })
    manifest={
        "manifest_version":MANIFEST_VERSION,
        "core_runner_version":VERSION,
        "scientific_contract":{
            "evidence_schema":"0.4.2",
            "caller":"rnatr_general_repeat_caller_ref_v0.4.1",
            "materializer":"rnatr_native_v041_to_evidence_v042_materializer_v0.1.2",
            "target_catalog":"RNA-TR-Scout_v0.3_rnatr_pilot_v03",
            "mapping_timing_boundary":"FASTQ_TO_BAM_MAPPING_OUTSIDE_BAM_TO_FINAL_TIMER",
            "bam_only_input":False,
            "source_read_sequence_required":True,
            "internal_intermediate_layout_is_public_api":False,
        },
        "run":{"run_id":run_id,"sample_id":sample_id,"created_utc":utc_now()},
        "sharding":{
            "algorithm":"sha256(read_id)[0:8]_big_endian_modulo_shard_count",
            "shard_count":shard_count,
            "unit_runner":"rnatr_core_generic_unit_bam_fastq_to_final_v0.1.1",
        },
        "resources":resources,
        "artifacts":artifacts,
        "join_key_contract":{
            "read_id":"stable source-read identifier; joins Core evidence to BAM/FASTQ",
            "target_source":"namespace for target_region_id",
            "target_region_id":"pinned mapping-target identity within target_source",
            "locus_id":"representative stable locus identity",
            "evidence_id":"unique molecule-by-locus evidence identifier",
            "repeat_event_id":"unique repeat-event identifier",
            "repeat_call_id":"unique repeat-segment/call identifier",
            "interruption_id":"unique repeat-interruption identifier",
            "caller_record_id":"unique caller-attempt identifier",
        },
        "coordinate_contract":{
            "genomic":"0_based_end_exclusive",
            "raw_read":"0_based_end_exclusive_original_FASTQ_orientation",
            "hardclip":"cigar_offset_aware",
        },
        "validation":{"status":"PASS","summary_artifact":"validation_summary.tsv"},
        "performance_instrumentation":{"logical_name":"performance.tsv","path":"performance.tsv"},
        "post_freeze_extensibility":{
            "stage_fusion_allowed_behind_contract":True,
            "streaming_allowed_behind_contract":True,
            "intermediate_io_reduction_allowed_behind_contract":True,
            "hardware_aware_concurrency_allowed_behind_contract":True,
            "golden_regression_required_for_change":True,
        },
    }
    return manifest,bindings

def merge_and_publish(
    *, work_root: Path, output_root: Path, runtime_config: dict[str,Any],
    shard_rows: list[dict[str,str]], run_id: str, sample_id: str,
    bam: Path, reads_fastq: Path
) -> dict[str,Any]:
    if output_root.exists() or Path(str(output_root)+".part").exists():
        raise ShardedRunError("final output root already exists")
    part=Path(str(output_root)+".part")
    part.mkdir(parents=True)
    perf=[]
    started=time.perf_counter()
    plain_rows=[]
    for table in TABLE_ORDER:
        inputs=[]
        for row in shard_rows:
            state=read_json(shard_state_path(work_root,row["shard"]))
            inputs.append(Path(state["output_root"])/f"{table}.tsv")
        t0=time.perf_counter()
        merged=merge_table_plain(table,inputs,part)
        merged["elapsed_seconds"]=time.perf_counter()-t0
        plain_rows.append(merged)
    merge_seconds=time.perf_counter()-started

    table_rows=[]
    for row in plain_rows:
        p=part/f"{row['table']}.tsv"
        gz=part/f"{row['table']}.tsv.gz"
        g=deterministic_gzip(p,gz)
        table_rows.extend([
            {"artifact":p.name,"table":row["table"],"path":p.name,"rows":row["rows"],
             "bytes":p.stat().st_size,"sha256":row["sha256"],"parity_contract":"EXACT_SHA256"},
            {"artifact":gz.name,"table":row["table"],"path":gz.name,"rows":row["rows"],
             "bytes":g["bytes"],"sha256":g["sha256"],"parity_contract":"DETERMINISTIC_GZIP_MTIME0"},
        ])
    write_tsv(part/"package_manifest.tsv",table_rows,
              ["artifact","table","path","rows","bytes","sha256","parity_contract"])

    validator=Path(runtime_config["components"]["validator_v042_package"]["path"]).resolve()
    t0=time.perf_counter()
    proc=subprocess.run([sys.executable,str(validator),"--package-dir",str(part)],
                        text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    validator_seconds=time.perf_counter()-t0
    if proc.returncode != 0:
        raise ShardedRunError(f"merged package validator failed: {proc.stdout[-1000:]} {proc.stderr[-1000:]}")
    write_tsv(part/"validation_summary.tsv",[
        {"validator":"rnatr_v042_validate_package.py","table":"PACKAGE","status":"PASS"}
    ],["validator","table","status"])

    # Input coherence is inherited from partition conservation.
    write_metrics(part/"input_read_coherence.tsv",[
        ("shard_count",len(shard_rows)),
        ("primary_reads",sum(int(r["primary_reads"]) for r in shard_rows)),
        ("fastq_reads",sum(int(r["fastq_reads"]) for r in shard_rows)),
        ("global_partition_read_coherence","PASS_EXACT_ID_SET"),
    ])
    shard_manifest=[]
    for row in shard_rows:
        state=read_json(shard_state_path(work_root,row["shard"]))
        shard_manifest.append({
            "shard":row["shard"],"primary_reads":row["primary_reads"],
            "alignment_records":row["alignment_records"],
            "input_bam_sha256":row["bam_sha256"],"input_fastq_sha256":row["fastq_sha256"],
            "unit_manifest_sha256":state["core_result_manifest_sha256"],
            "unit_elapsed_seconds":state["elapsed_seconds"],"status":"PASS",
        })
    write_tsv(part/"shard_manifest.tsv",shard_manifest,
              ["shard","primary_reads","alignment_records","input_bam_sha256","input_fastq_sha256",
               "unit_manifest_sha256","unit_elapsed_seconds","status"])
    write_tsv(part/"performance.tsv",[
        {"stage":"global_merge_and_gzip","elapsed_seconds":merge_seconds,"status":"PASS"},
        {"stage":"global_package_validator","elapsed_seconds":validator_seconds,"status":"PASS"},
    ],["stage","elapsed_seconds","status"])

    # Create manifest after all files above exist.
    manifest,bindings=build_merged_manifest(
        output_part=part,run_id=run_id,sample_id=sample_id,bam=bam,reads_fastq=reads_fastq,
        runtime_config=runtime_config,table_rows=table_rows,shard_count=len(shard_rows)
    )
    atomic_write_json(part/"core_result_manifest.json",manifest)
    atomic_write_json(part/"resource_bindings.local.json",bindings)

    for p in sorted(part.iterdir()):
        if p.is_file():
            with p.open("rb") as fh:
                os.fsync(fh.fileno())
    output_root.parent.mkdir(parents=True,exist_ok=True)
    os.replace(part,output_root)
    fd=os.open(output_root.parent,os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)
    return {
        "output_root":str(output_root),
        "core_result_manifest_sha256":sha256_file(output_root/"core_result_manifest.json"),
        "tables":[
            {"table":t,"rows":data_rows(output_root/f"{t}.tsv"),
             "sha256":sha256_file(output_root/f"{t}.tsv")}
            for t in TABLE_ORDER
        ],
    }

def read_tsv_rows(path: Path) -> list[dict[str,str]]:
    ensure_regular(path)
    with path.open("r",encoding="utf-8",newline="") as fh:
        return list(csv.DictReader(fh,delimiter="\t"))


def _has_absolute_path(obj: Any) -> bool:
    if isinstance(obj,dict):
        return any(_has_absolute_path(v) for v in obj.values())
    if isinstance(obj,list):
        return any(_has_absolute_path(v) for v in obj)
    if isinstance(obj,str):
        return obj.startswith("/") or (len(obj)>=3 and obj[1]==":" and obj[2] in {"/","\\"})
    return False


def _decompressed_sha256(path: Path) -> str:
    h=hashlib.sha256()
    with gzip.open(path,"rb") as fh:
        while True:
            block=fh.read(8*1024*1024)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def _final_state_equal(left: dict[str,Any], right: dict[str,Any]) -> bool:
    if left.get("output_root") != right.get("output_root"):
        return False
    if left.get("core_result_manifest_sha256") != right.get("core_result_manifest_sha256"):
        return False
    def norm(obj: dict[str,Any]) -> dict[str,tuple[int,str]]:
        return {
            str(row["table"]):(int(row["rows"]),str(row["sha256"]))
            for row in obj.get("tables",[])
        }
    return norm(left)==norm(right)


def reconstruct_published_final_state(
    *, output_root: Path, work_root: Path, runtime_config: dict[str,Any],
    partition_rows: list[dict[str,str]], run_id: str, sample_id: str,
    bam: Path, reads_fastq: Path, shard_count: int,
) -> dict[str,Any]:
    if not output_root.is_dir() or output_root.is_symlink():
        raise ShardedRunError(f"published output root missing/invalid: {output_root}")
    if Path(str(output_root)+".part").exists():
        raise ShardedRunError("published output and .part both exist")

    completed={}
    for row in partition_rows:
        state=verify_completed_shard(work_root,row,runtime_config)
        if state is None:
            raise ShardedRunError(f"published output exists but shard is incomplete: {row['shard']}")
        completed[row["shard"]]=state

    manifest_path=output_root/"core_result_manifest.json"
    bindings_path=output_root/"resource_bindings.local.json"
    package_manifest_path=output_root/"package_manifest.tsv"
    validation_path=output_root/"validation_summary.tsv"
    shard_manifest_path=output_root/"shard_manifest.tsv"
    for path in (
        manifest_path,bindings_path,package_manifest_path,validation_path,
        shard_manifest_path,output_root/"performance.tsv",
        output_root/"input_read_coherence.tsv",
    ):
        ensure_regular(path)

    manifest=read_json(manifest_path)
    bindings=read_json(bindings_path)
    if _has_absolute_path(manifest):
        raise ShardedRunError("portable Core result manifest contains an absolute path")
    if manifest.get("manifest_version") != MANIFEST_VERSION:
        raise ShardedRunError("published manifest version mismatch")
    if manifest.get("core_runner_version") not in {
        "rnatr_core_generic_sharded_bam_fastq_to_final_v0.1.1", VERSION
    }:
        raise ShardedRunError("published Core runner version is not recovery-compatible")
    if bindings.get("binding_version") != BINDING_VERSION:
        raise ShardedRunError("published local-binding version mismatch")
    if (
        manifest.get("run",{}).get("run_id") != run_id
        or manifest.get("run",{}).get("sample_id") != sample_id
    ):
        raise ShardedRunError("published manifest run/sample mismatch")
    sharding=manifest.get("sharding",{})
    if int(sharding.get("shard_count",-1)) != shard_count:
        raise ShardedRunError("published manifest shard-count mismatch")
    if sharding.get("unit_runner") != "rnatr_core_generic_unit_bam_fastq_to_final_v0.1.1":
        raise ShardedRunError("published unit-runner version mismatch")
    if sharding.get("algorithm") != "sha256(read_id)[0:8]_big_endian_modulo_shard_count":
        raise ShardedRunError("published manifest partition algorithm mismatch")

    resources=manifest.get("resources")
    binding_resources=bindings.get("resources")
    if (
        not isinstance(resources,dict)
        or not isinstance(binding_resources,dict)
        or set(resources)!=set(binding_resources)
    ):
        raise ShardedRunError("published manifest/local-binding resource mismatch")
    for key,path,expected_kind in (
        ("source_bam",bam,"BAM"),("source_reads",reads_fastq,"FASTQ"),
    ):
        entry=resources.get(key,{})
        if (
            entry.get("kind") != expected_kind
            or entry.get("sha256") != sha256_file(path)
            or int(entry.get("bytes",-1)) != path.stat().st_size
        ):
            raise ShardedRunError(f"published source resource drift: {key}")
        if Path(binding_resources[key].get("path","")).resolve() != path.resolve():
            raise ShardedRunError(f"published local source binding drift: {key}")
    for section,prefix in (("components","component"),("catalogs","catalog")):
        for role,expected in runtime_config[section].items():
            key=f"{prefix}:{role}"
            entry=resources.get(key,{})
            if entry.get("sha256") != expected["sha256"]:
                raise ShardedRunError(f"published runtime resource SHA mismatch: {key}")
            bound=Path(binding_resources.get(key,{}).get("path","")).resolve()
            if bound != Path(expected["path"]).resolve():
                raise ShardedRunError(f"published runtime resource binding mismatch: {key}")

    package_rows=read_tsv_rows(package_manifest_path)
    expected_names=(
        {f"{table}.tsv" for table in TABLE_ORDER}
        | {f"{table}.tsv.gz" for table in TABLE_ORDER}
    )
    if len(package_rows)!=10 or {row.get("artifact") for row in package_rows}!=expected_names:
        raise ShardedRunError("published package-manifest artifact set mismatch")
    package_by={row["artifact"]:row for row in package_rows}
    table_state=[]
    for table in TABLE_ORDER:
        plain=output_root/f"{table}.tsv"
        gz=output_root/f"{table}.tsv.gz"
        ensure_regular(plain)
        ensure_regular(gz)
        plain_row=package_by[plain.name]
        gz_row=package_by[gz.name]
        plain_sha=sha256_file(plain)
        gz_sha=sha256_file(gz)
        rows=data_rows(plain)
        if (
            int(plain_row["rows"])!=rows
            or int(plain_row["bytes"])!=plain.stat().st_size
            or plain_row["sha256"]!=plain_sha
        ):
            raise ShardedRunError(f"published plain table drift: {table}")
        if (
            int(gz_row["rows"])!=rows
            or int(gz_row["bytes"])!=gz.stat().st_size
            or gz_row["sha256"]!=gz_sha
        ):
            raise ShardedRunError(f"published gzip table drift: {table}")
        if _decompressed_sha256(gz)!=plain_sha:
            raise ShardedRunError(f"published gzip logical-content drift: {table}")
        table_state.append({"table":table,"rows":rows,"sha256":plain_sha})

    validator=Path(
        runtime_config["components"]["validator_v042_package"]["path"]
    ).resolve()
    proc=subprocess.run(
        [sys.executable,str(validator),"--package-dir",str(output_root)],
        text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
    )
    if proc.returncode!=0:
        raise ShardedRunError(
            f"published package validator failed: "
            f"{proc.stdout[-500:]} {proc.stderr[-500:]}"
        )
    validation_rows=read_tsv_rows(validation_path)
    if len(validation_rows)!=1 or validation_rows[0].get("status")!="PASS":
        raise ShardedRunError("published validation summary is not PASS")

    shard_rows=read_tsv_rows(shard_manifest_path)
    if (
        len(shard_rows)!=shard_count
        or [r.get("shard") for r in shard_rows] != [r["shard"] for r in partition_rows]
    ):
        raise ShardedRunError("published shard manifest ordering/count mismatch")
    for published,partition in zip(shard_rows,partition_rows):
        state=completed[partition["shard"]]
        if published.get("status")!="PASS":
            raise ShardedRunError(
                f"published shard status is not PASS: {partition['shard']}"
            )
        expected=(
            partition["bam_sha256"],partition["fastq_sha256"],
            state["core_result_manifest_sha256"],
        )
        observed=(
            published.get("input_bam_sha256"),
            published.get("input_fastq_sha256"),
            published.get("unit_manifest_sha256"),
        )
        if observed!=expected:
            raise ShardedRunError(
                f"published shard provenance drift: {partition['shard']}"
            )

    artifact_by={
        a.get("path"):a
        for a in manifest.get("artifacts",[])
        if isinstance(a,dict)
    }
    required_artifacts=expected_names|{
        "package_manifest.tsv","validation_summary.tsv","performance.tsv",
        "input_read_coherence.tsv","shard_manifest.tsv",
    }
    if not required_artifacts.issubset(set(artifact_by)):
        raise ShardedRunError("portable manifest lacks required published artifacts")
    for name in required_artifacts:
        path=output_root/name
        entry=artifact_by[name]
        if (
            int(entry.get("bytes",-1))!=path.stat().st_size
            or entry.get("sha256")!=sha256_file(path)
        ):
            raise ShardedRunError(f"portable manifest artifact drift: {name}")

    return {
        "output_root":str(output_root),
        "core_result_manifest_sha256":sha256_file(manifest_path),
        "tables":table_state,
    }


def verify_final_noop(output_root: Path, final_state: dict[str,Any]) -> None:
    ensure_regular(output_root/"core_result_manifest.json")
    if (
        sha256_file(output_root/"core_result_manifest.json")
        != final_state["core_result_manifest_sha256"]
    ):
        raise ShardedRunError("final manifest SHA drift")
    expected={
        r["table"]:(int(r["rows"]),r["sha256"])
        for r in final_state["tables"]
    }
    actual={
        t:(data_rows(output_root/f"{t}.tsv"),sha256_file(output_root/f"{t}.tsv"))
        for t in TABLE_ORDER
    }
    if expected != actual:
        raise ShardedRunError("final scientific table drift")

def run_pending(
    *, unit_runner: Path, runtime_config_path: Path, work_root: Path,
    shard_rows: list[dict[str,str]], run_id: str, sample_id: str,
    caller_workers: int, pythonhashseed: str, max_workers: int, stop_after: int
) -> int:
    runtime=validate_runtime_config(runtime_config_path)
    pending=[]
    for row in shard_rows:
        state=verify_completed_shard(work_root,row,runtime)
        if state is None:
            pending.append(row)
    if not pending:
        return 0

    if stop_after > 0:
        completed_now=0
        for row in pending:
            run_unit(
                unit_runner=unit_runner,runtime_config_path=runtime_config_path,work_root=work_root,
                run_id=run_id,sample_id=sample_id,shard_row=row,caller_workers=caller_workers,
                pythonhashseed=pythonhashseed
            )
            completed_now += 1
            if completed_now >= stop_after:
                return 75
        return 0

    def task(row):
        return run_unit(
            unit_runner=unit_runner,runtime_config_path=runtime_config_path,work_root=work_root,
            run_id=run_id,sample_id=sample_id,shard_row=row,caller_workers=caller_workers,
            pythonhashseed=pythonhashseed
        )
    with cf.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures=[pool.submit(task,row) for row in pending]
        for f in cf.as_completed(futures):
            f.result()
    return 0

def _load_resume_context(
    *, bam: Path, reads_fastq: Path, work_root: Path, shard_count: int
) -> tuple[dict[str,Any],list[dict[str,str]]]:
    if not work_root.is_dir():
        raise ShardedRunError("resume work root missing")
    run_state=read_json(work_root/"state/run.json")
    if (
        run_state.get("bam_sha256")!=sha256_file(bam)
        or run_state.get("fastq_sha256")!=sha256_file(reads_fastq)
    ):
        raise ShardedRunError("resume top-level input SHA drift")
    if int(run_state.get("shards",-1))!=shard_count:
        raise ShardedRunError("resume shard-count mismatch")
    partition_manifest=work_root/"partitions/partition_manifest.tsv"
    ensure_regular(partition_manifest)
    if (
        sha256_file(partition_manifest)
        != run_state.get("partition_manifest_sha256")
    ):
        raise ShardedRunError("resume partition-manifest SHA drift")
    return run_state,verify_partition(work_root/"partitions",shard_count)


def execute(args: argparse.Namespace) -> int:
    if pysam is None:
        raise ShardedRunError(f"pysam import failed: {PYSAM_IMPORT_ERROR}")
    for exe in ("samtools","python","bedtools","bgzip","tabix","gzip"):
        if shutil.which(exe) is None:
            raise ShardedRunError(f"required executable not found: {exe}")
    bam=args.bam.resolve()
    reads_fastq=args.reads_fastq.resolve()
    unit_runner=args.unit_runner.resolve()
    config_path=args.runtime_config.resolve()
    work_root=args.work_root.resolve()
    output_root=args.output_root.resolve()
    ensure_regular(bam)
    ensure_regular(reads_fastq)
    ensure_regular(unit_runner)
    ensure_regular(config_path)
    if args.expected_bam_sha256 and sha256_file(bam)!=args.expected_bam_sha256:
        raise ShardedRunError("input BAM SHA mismatch")
    if (
        args.expected_fastq_sha256
        and sha256_file(reads_fastq)!=args.expected_fastq_sha256
    ):
        raise ShardedRunError("input FASTQ SHA mismatch")
    runtime=validate_runtime_config(config_path)
    final_state_path=work_root/"state/final.json"

    if args.start:
        if (
            work_root.exists()
            or output_root.exists()
            or Path(str(output_root)+".part").exists()
        ):
            raise ShardedRunError("start requires unused work/output roots")
        work_root.mkdir(parents=True)
        partition_root=work_root/"partitions"
        partition_rows=partition_inputs(
            bam,reads_fastq,partition_root,args.shards
        )
        partition_manifest_sha256=sha256_file(
            partition_root/"partition_manifest.tsv"
        )
        atomic_write_json(work_root/"state/run.json",{
            "version":VERSION,
            "run_id":args.run_id,
            "sample_id":args.sample_id,
            "bam_sha256":sha256_file(bam),
            "fastq_sha256":sha256_file(reads_fastq),
            "shards":args.shards,
            "partition_manifest_sha256":partition_manifest_sha256,
            "created_utc":utc_now(),
        })
    else:
        _,partition_rows=_load_resume_context(
            bam=bam,reads_fastq=reads_fastq,work_root=work_root,
            shard_count=args.shards,
        )
        if output_root.exists():
            reconstructed=reconstruct_published_final_state(
                output_root=output_root,work_root=work_root,
                runtime_config=runtime,partition_rows=partition_rows,
                run_id=args.run_id,sample_id=args.sample_id,bam=bam,
                reads_fastq=reads_fastq,shard_count=args.shards,
            )
            if final_state_path.is_file():
                existing=read_json(final_state_path)
                if not _final_state_equal(existing,reconstructed):
                    raise ShardedRunError(
                        "existing final state disagrees with reconstructed publication"
                    )
                if args.audit_recover_published_state:
                    print("POST_PUBLICATION_RECOVERY_AUDIT\tPASS")
                    print("existing_final_state_match\tPASS")
                    print("scientific_commands\t0")
                else:
                    print("SECOND_RESUME_NOOP\tPASS")
                print(f"OUTPUT_ROOT\t{output_root}")
                return 0
            if args.audit_recover_published_state:
                print("POST_PUBLICATION_RECOVERY_AUDIT\tPASS")
                print("existing_final_state_match\tMISSING_RECOVERABLE")
                print("scientific_commands\t0")
                print(f"OUTPUT_ROOT\t{output_root}")
                return 0
            atomic_write_json(final_state_path,reconstructed)
            print("POST_PUBLICATION_FINAL_STATE_RECOVERY\tPASS")
            print("scientific_commands\t0")
            print(f"OUTPUT_ROOT\t{output_root}")
            return 0
        if args.audit_recover_published_state:
            raise ShardedRunError(
                "recovery audit requires an existing published output"
            )

    stop_after=int(os.environ.get("RNATR_TEST_STOP_AFTER_SHARDS","0"))
    rc=run_pending(
        unit_runner=unit_runner,runtime_config_path=config_path,
        work_root=work_root,shard_rows=partition_rows,
        run_id=args.run_id,sample_id=args.sample_id,
        caller_workers=args.caller_workers,
        pythonhashseed=args.pythonhashseed,
        max_workers=args.max_unit_workers,
        stop_after=stop_after if args.start else 0,
    )
    if rc==75:
        complete=sum(
            1 for row in partition_rows
            if shard_state_path(work_root,row["shard"]).is_file()
        )
        print("INTENTIONAL_STOP\tPASS_EXPECTED")
        print(f"completed_shards\t{complete}")
        return 75

    for row in partition_rows:
        if verify_completed_shard(work_root,row,runtime) is None:
            raise ShardedRunError(f"shard did not complete: {row['shard']}")
    output_part=Path(str(output_root)+".part")
    if args.resume and output_part.exists() and not output_root.exists():
        if not output_part.is_dir() or output_part.is_symlink():
            raise ShardedRunError(
                f"invalid stale output .part path: {output_part}"
            )
        shutil.rmtree(output_part)
    final_state=merge_and_publish(
        work_root=work_root,output_root=output_root,runtime_config=runtime,
        shard_rows=partition_rows,run_id=args.run_id,
        sample_id=args.sample_id,bam=bam,reads_fastq=reads_fastq,
    )
    atomic_write_json(final_state_path,final_state)
    print("===== RNA-TR-SCOUT GENERIC SHARDED CORE FINAL =====")
    print(f"version\t{VERSION}")
    print(f"shards\t{args.shards}")
    print("global_partition_coherence\tPASS_EXACT_ID_SET")
    print("all_shards_complete\tPASS")
    print("global_merge\tPASS")
    print("package_validator\tPASS")
    print("atomic_publication\tPASS")
    print(f"OUTPUT_ROOT\t{output_root}")
    print(f"CORE_RESULT_MANIFEST\t{output_root/'core_result_manifest.json'}")
    return 0

def self_test() -> int:
    # Stable sharding and merge semantics without requiring pysam.
    if shard_index("readA",12) != shard_index("readA",12):
        raise ShardedRunError("self-test shard index instability")
    with tempfile.TemporaryDirectory(prefix="rnatr_sharded_selftest_") as td:
        root=Path(td)
        a=root/"a.tsv"; b=root/"b.tsv"; out=root/"out"; out.mkdir()
        header="projection_id\tvalue\n"
        a.write_text(header+"p001\ta\np003\tc\n",encoding="utf-8")
        b.write_text(header+"p002\tb\np004\td\n",encoding="utf-8")
        row=merge_table_plain("general_repeat_calls",[a,b],out)
        if row["rows"]!=4:
            raise ShardedRunError("self-test merge row count failed")
        expected=header+"p001\ta\np002\tb\np003\tc\np004\td\n"
        if (out/"general_repeat_calls.tsv").read_text(encoding="utf-8")!=expected:
            raise ShardedRunError("self-test merge order failed")
        if numeric_key(b".") != 0 or numeric_key(b"") != 0 or numeric_key(b"3") != 3:
            raise ShardedRunError("self-test numeric-key compatibility failed")
        left={
            "output_root":"/x",
            "core_result_manifest_sha256":"abc",
            "tables":[{"table":"read_evidence","rows":1,"sha256":"def"}],
        }
        right={
            "output_root":"/x",
            "core_result_manifest_sha256":"abc",
            "tables":[{"table":"read_evidence","rows":1,"sha256":"def"}],
        }
        if not _final_state_equal(left,right):
            raise ShardedRunError("self-test final-state equivalence failed")
        if (
            not _has_absolute_path({"x":"/tmp/a"})
            or _has_absolute_path({"x":"relative/a"})
        ):
            raise ShardedRunError("self-test portable-path detection failed")
    print("SELF_TEST\tPASS")
    print(f"version\t{VERSION}")
    if pysam is None:
        print("pysam_runtime_test\tSKIPPED_NOT_INSTALLED_IN_BUILD_ENV")
    else:
        print("pysam_runtime_test\tAVAILABLE")
    return 0

def main() -> int:
    p=argparse.ArgumentParser()
    modes=p.add_mutually_exclusive_group(required=True)
    modes.add_argument("--self-test",action="store_true")
    modes.add_argument("--start",action="store_true")
    modes.add_argument("--resume",action="store_true")
    modes.add_argument("--audit-recover-published-state",action="store_true")
    p.add_argument("--runtime-config",type=Path)
    p.add_argument("--unit-runner",type=Path)
    p.add_argument("--bam",type=Path)
    p.add_argument("--reads-fastq",type=Path)
    p.add_argument("--run-id")
    p.add_argument("--sample-id")
    p.add_argument("--work-root",type=Path)
    p.add_argument("--output-root",type=Path)
    p.add_argument("--shards",type=int,default=12)
    p.add_argument("--max-unit-workers",type=int,default=3)
    p.add_argument("--caller-workers",type=int,default=2)
    p.add_argument("--pythonhashseed",default="0")
    p.add_argument("--expected-bam-sha256",default="")
    p.add_argument("--expected-fastq-sha256",default="")
    args=p.parse_args()
    if args.self_test:
        return self_test()
    if args.audit_recover_published_state:
        args.resume=True
    for name in ("runtime_config","unit_runner","bam","reads_fastq","run_id","sample_id","work_root","output_root"):
        if getattr(args,name) in (None,""):
            p.error(f"--{name.replace('_','-')} is required")
    if args.shards<1 or args.max_unit_workers<1 or args.caller_workers<1:
        p.error("shards/workers must be >=1")
    return execute(args)

if __name__=="__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}",file=sys.stderr)
        raise
