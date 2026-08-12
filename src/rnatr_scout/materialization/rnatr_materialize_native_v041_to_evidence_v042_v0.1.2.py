from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
import statistics
import sys
import time
from collections import OrderedDict, defaultdict
from pathlib import Path

import pysam

MISSING = {"", ".", "NA", "N/A", "None", "null", "nan"}
DEFAULT_CALLER_VERSION = "rnatr_general_repeat_caller_ref_v0.4.1"
MATERIALIZER_VERSION = "rnatr_native_v041_to_evidence_v042_materializer_v0.1.2"


def present(value) -> bool:
    return value not in MISSING and value is not None


def as_int(value, default=None):
    if not present(value):
        return default
    try:
        return int(float(value))
    except Exception:
        return default


def as_float(value, default=None):
    if not present(value):
        return default
    try:
        return float(value)
    except Exception:
        return default


def fmt(value):
    if value is None:
        return "."
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            return "."
        return format(value, ".12g")
    text = str(value)
    return "." if text in MISSING else text


def stable_id(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:24]


def read_gz_tsv(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_plain_tsv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".part")
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            delimiter="\t",
            lineterminator="\n",
            extrasaction="raise",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({field: fmt(row.get(field, ".")) for field in fields})
    os.replace(tmp, path)


def gzip_deterministic(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name("." + target.name + ".part")
    with source.open("rb") as inp, tmp.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=1, mtime=0) as out:
            for block in iter(lambda: inp.read(1024 * 1024), b""):
                out.write(block)
    os.replace(tmp, target)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def choose_enum(schema: dict, enum_name: str, preferences: list[str], required: bool = True) -> str:
    allowed = list(schema.get("enums", {}).get(enum_name, []))
    if not allowed:
        if required:
            raise RuntimeError(f"enum {enum_name} is absent")
        return "."
    for preference in preferences:
        for value in allowed:
            if value == preference or value.lower() == preference.lower():
                return value
    if required:
        raise RuntimeError(
            f"none of preferred values {preferences} exists in enum {enum_name}: {allowed}"
        )
    return "."


def blank_row(fields: list[str]) -> dict[str, str]:
    return {field: "." for field in fields}


def table_fields(schema: dict, table: str) -> list[str]:
    return [entry["name"] for entry in schema["tables"][table]["columns"]]


def table_specs(schema: dict, table: str) -> dict[str, dict]:
    return {entry["name"]: entry for entry in schema["tables"][table]["columns"]}


def enforce_required(schema: dict, table: str, row: dict[str, object], context: str) -> None:
    for spec in schema["tables"][table]["columns"]:
        if not spec.get("required", False):
            continue
        value = fmt(row.get(spec["name"], "."))
        if not present(value):
            raise RuntimeError(
                f"required field missing table={table} field={spec['name']} context={context}"
            )


def normalize_geometry(caller_geometry: str, sizing_status: str, called: bool, schema: dict) -> str:
    if not called:
        return choose_enum(schema, "evidence_class", ["UNRESOLVED"], required=True)
    if caller_geometry == "SPAN" and sizing_status == "exact_span":
        desired = "SPAN"
    elif caller_geometry == "LEFT_CENSORED":
        desired = "RIGHT_ANCHORED_CENSORED_LEFT"
    elif caller_geometry == "RIGHT_CENSORED":
        desired = "LEFT_ANCHORED_CENSORED_RIGHT"
    elif caller_geometry == "BOTH_CENSORED":
        desired = "BOTH_SIDES_CENSORED"
    else:
        desired = "REPEAT_ONLY_UNANCHORED"
    return choose_enum(schema, "evidence_class", [desired, "UNRESOLVED"], required=True)


def normalize_sizing(caller_status: str, caller_sizing: str, schema: dict) -> str:
    if caller_status != "CALLED":
        return choose_enum(schema, "sizing_status", ["not_attempted", "no_call"], required=True)
    if caller_sizing == "EXACT_SPAN":
        return choose_enum(schema, "sizing_status", ["exact_span"], required=True)
    if caller_sizing.startswith("LOWER_BOUND_") or caller_sizing == "CONTEXT_LIMITED_LOWER_BOUND":
        return choose_enum(schema, "sizing_status", ["lower_bound"], required=True)
    return choose_enum(schema, "sizing_status", ["no_call"], required=True)


def attempt_rank(row: dict[str, str]) -> tuple:
    integration = 1 if row.get("integration_status") == "CALLED" else 0
    call_status = 1 if row.get("call_status") == "PASS" else 0
    sizing = row.get("sizing_status", ".")
    if sizing == "EXACT_SPAN":
        sizing_rank = 3
    elif sizing.startswith("LOWER_BOUND_") or sizing == "CONTEXT_LIMITED_LOWER_BOUND":
        sizing_rank = 2
    elif sizing == "LOW_CONFIDENCE":
        sizing_rank = 1
    else:
        sizing_rank = 0
    return (
        -integration,
        -call_status,
        -sizing_rank,
        -(as_float(row.get("prior_overlap_bp"), -1e18)),
        -(as_float(row.get("score_per_read_bp"), -1e18)),
        -(as_float(row.get("purity"), -1e18)),
        -(as_float(row.get("best_mapq"), -1e18)),
        as_int(row.get("assignment_rank"), 10**9),
        row.get("projection_id", ""),
    )


def parse_json_list(value: str, field: str, projection_id: str) -> list[dict]:
    if not present(value):
        return []
    try:
        parsed = json.loads(value)
    except Exception as exc:
        raise RuntimeError(
            f"invalid JSON field={field} projection_id={projection_id}: {exc}"
        ) from exc
    if not isinstance(parsed, list):
        raise RuntimeError(f"{field} is not a list projection_id={projection_id}")
    if not all(isinstance(item, dict) for item in parsed):
        raise RuntimeError(f"{field} contains non-object projection_id={projection_id}")
    return parsed


def event_flags_for(row: dict[str, str]) -> list[str]:
    flags: list[str] = []
    if row.get("call_status") == "LOW_CONFIDENCE":
        flags.append("CALLER_LOW_CONFIDENCE")
    if row.get("context_limited") == "true":
        flags.append("CONTEXT_LIMITED")
    if (as_int(row.get("prior_overlap_bp"), 0) or 0) <= 0:
        flags.append("PRIOR_OVERLAP_NONPOSITIVE")
    if row.get("compound_status") == "COMPOUND":
        flags.append("COMPOUND_REPEAT")
    if row.get("compound_status") == "INTERRUPTED_SINGLE_MOTIF":
        flags.append("INTERRUPTED_SINGLE_MOTIF")
    return flags


def failure_for(row: dict[str, str], schema: dict) -> str:
    status = row.get("integration_status", ".")
    mapping = {
        "NOT_ATTEMPTED_NO_PROJECTED_TARGET": "GENERAL_CALLER_NO_PROJECTED_TARGET",
        "NOT_ATTEMPTED_UNSUPPORTED_STRATEGY": "GENERAL_CALLER_UNSUPPORTED_STRATEGY",
        "NOT_ATTEMPTED_NO_WINDOW_SEQUENCE": "GENERAL_CALLER_NO_WINDOW_SEQUENCE",
        "CALLER_ERROR": "GENERAL_CALLER_ERROR",
    }
    if status in mapping:
        return choose_enum(schema, "failure_code", [mapping[status]], required=True)
    if status == "CALLED" and row.get("call_status") == "LOW_CONFIDENCE":
        return choose_enum(
            schema, "failure_code", ["GENERAL_CALLER_LOW_CONFIDENCE"], required=True
        )
    if status == "CALLED" and (as_int(row.get("prior_overlap_bp"), 0) or 0) <= 0:
        return choose_enum(
            schema,
            "failure_code",
            ["GENERAL_CALLER_PRIOR_OVERLAP_NONPOSITIVE"],
            required=True,
        )
    return choose_enum(schema, "failure_code", ["NONE"], required=True)


def qc_status_for(row: dict[str, str], schema: dict) -> str:
    status = row.get("integration_status", ".")
    if status == "CALLER_ERROR":
        return choose_enum(schema, "qc_status", ["FAIL", "WARN"], required=True)
    if status != "CALLED":
        return choose_enum(schema, "qc_status", ["WARN", "FAIL"], required=True)
    if row.get("call_status") == "LOW_CONFIDENCE":
        return choose_enum(schema, "qc_status", ["WARN"], required=True)
    if (as_int(row.get("prior_overlap_bp"), 0) or 0) <= 0:
        return choose_enum(schema, "qc_status", ["WARN"], required=True)
    return choose_enum(schema, "qc_status", ["PASS"], required=True)


def confidence_for(row: dict[str, str], schema: dict) -> str:
    if row.get("integration_status") == "CALLED" and row.get("call_status") == "PASS":
        return choose_enum(schema, "confidence_label", ["MEDIUM", "HIGH"], required=True)
    return choose_enum(schema, "confidence_label", ["LOW"], required=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-root", type=Path, required=True)
    ap.add_argument("--calls", type=Path, required=True)
    ap.add_argument("--schema-dir", type=Path, required=True)
    ap.add_argument("--outdir", type=Path, required=True)
    ap.add_argument("--sample-id", default="ENCSR307SHM")
    args = ap.parse_args()

    project = args.project_root
    schema_dir = args.schema_dir
    outdir = args.outdir
    run_id = "ENCSR307SHM_pilot100k_mm2splice_v1"
    sample_id = args.sample_id
    outdir.mkdir(parents=True, exist_ok=True)

    schema_path = schema_dir / "schema/rnatr_v04_table_schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    if schema.get("schema_version") != "0.4.2":
        raise RuntimeError(f"expected schema 0.4.2, got {schema.get('schema_version')}")

    projection_path = (
        project
        / "results/11_projection"
        / run_id
        / "v0.3.3/read_target_projection.v0.3.3.tsv.gz"
    )
    if not projection_path.is_file():
        raise FileNotFoundError(projection_path)

    t0 = time.perf_counter()
    calls = read_gz_tsv(args.calls)
    projections = read_gz_tsv(projection_path)
    load_seconds = time.perf_counter() - t0

    projection_by = {row["projection_id"]: row for row in projections}
    if len(projection_by) != len(projections):
        raise RuntimeError("duplicate projection_id in projection table")
    if len(calls) != len(projections):
        raise RuntimeError(f"calls/projection row mismatch {len(calls)} != {len(projections)}")
    call_projection_ids = {row["projection_id"] for row in calls}
    if call_projection_ids != set(projection_by):
        raise RuntimeError("caller/projection ID sets differ")

    # Read metadata are already present in the projection table. FASTQ is used only
    # as an independent completeness check for read length/quality where available.
    env_text = (project / "config/paths.env").read_text(encoding="utf-8")
    import re
    match = re.search(
        r'^\s*(?:export\s+)?RAW_ROOT=(?:"|\')?([^"\']+)',
        env_text,
        re.M,
    )
    if not match:
        raise RuntimeError("RAW_ROOT not found")
    raw_root = Path(os.path.expandvars(os.path.expanduser(match.group(1).strip())))
    candidate_fastq = (
        raw_root
        / "benchmarks/ENCSR307SHM/pilot_100k_seed20260803"
        / "rnatr_candidates_v0.3.1/ENCFF260PGB.pilot_100k.rnatr_candidate_all.fastq.gz"
    )
    if not candidate_fastq.is_file():
        raise FileNotFoundError(candidate_fastq)

    wanted_reads = {row["read_id"] for row in calls}
    fastq_meta: dict[str, tuple[int, str]] = {}
    fastq_records = 0
    t_fastq = time.perf_counter()
    with pysam.FastxFile(str(candidate_fastq)) as source:
        for entry in source:
            fastq_records += 1
            if entry.name not in wanted_reads:
                continue
            mean_q = "."
            if entry.quality:
                mean_q = format(
                    sum(ord(char) - 33 for char in entry.quality) / len(entry.quality),
                    ".6f",
                )
            fastq_meta[entry.name] = (len(entry.sequence), mean_q)
    fastq_seconds = time.perf_counter() - t_fastq
    missing_fastq_reads = sorted(wanted_reads - set(fastq_meta))
    if missing_fastq_reads:
        raise RuntimeError(
            f"candidate FASTQ missing {len(missing_fastq_reads)} caller read IDs"
        )

    # Evidence groups retain insertion order from deterministic caller output.
    groups: OrderedDict[tuple[str, str, str], list[dict[str, str]]] = OrderedDict()
    for row in calls:
        key = (
            row["read_id"],
            row["target_region_id"],
            row["representative_locus_id"],
        )
        groups.setdefault(key, []).append(row)

    general_fields = table_fields(schema, "general_repeat_calls")
    read_fields = table_fields(schema, "read_evidence")
    event_fields = table_fields(schema, "repeat_events")
    segment_fields = table_fields(schema, "repeat_segments")
    interruption_fields = table_fields(schema, "repeat_interruptions")

    general_rows: list[dict[str, object]] = []
    read_rows: list[dict[str, object]] = []
    event_rows: list[dict[str, object]] = []
    segment_rows: list[dict[str, object]] = []
    interruption_rows: list[dict[str, object]] = []

    call_annotations: dict[str, dict[str, str]] = {}
    caller_record_by_projection: dict[str, str] = {}

    # First pass: deterministic IDs for every caller attempt.
    for row in calls:
        caller_version = (
            row["caller_version"] if present(row.get("caller_version")) else DEFAULT_CALLER_VERSION
        )
        caller_record_id = stable_id(
            f"GENERAL_CALL|{run_id}|{row['projection_id']}|{caller_version}"
        )
        caller_record_by_projection[row["projection_id"]] = caller_record_id

    # Per-evidence event grouping.
    evidence_data: dict[str, dict] = {}
    for key, attempts in groups.items():
        read_id, target_region_id, locus_id = key
        evidence_id = stable_id(
            f"{run_id}|{read_id}|{target_region_id}|{locus_id}"
        )
        called_with_coords = [
            row
            for row in attempts
            if row.get("integration_status") == "CALLED"
            and as_int(row.get("raw_tract_start")) is not None
            and as_int(row.get("raw_tract_end")) is not None
            and as_int(row.get("raw_tract_end")) > as_int(row.get("raw_tract_start"))
        ]
        called_with_coords.sort(
            key=lambda row: (
                as_int(row["raw_tract_start"]),
                as_int(row["raw_tract_end"]),
                row["projection_id"],
            )
        )

        interval_groups: list[list[dict[str, str]]] = []
        for row in called_with_coords:
            start = as_int(row["raw_tract_start"])
            end = as_int(row["raw_tract_end"])
            placed = False
            for interval_group in interval_groups:
                if any(
                    min(end, as_int(other["raw_tract_end"]))
                    - max(start, as_int(other["raw_tract_start"]))
                    > 0
                    for other in interval_group
                ):
                    interval_group.append(row)
                    placed = True
                    break
            if not placed:
                interval_groups.append([row])

        # Merge transitively until stable.
        changed = True
        while changed:
            changed = False
            merged: list[list[dict[str, str]]] = []
            while interval_groups:
                current = interval_groups.pop(0)
                current_start = min(as_int(x["raw_tract_start"]) for x in current)
                current_end = max(as_int(x["raw_tract_end"]) for x in current)
                keep: list[list[dict[str, str]]] = []
                for candidate in interval_groups:
                    candidate_start = min(as_int(x["raw_tract_start"]) for x in candidate)
                    candidate_end = max(as_int(x["raw_tract_end"]) for x in candidate)
                    if min(current_end, candidate_end) - max(current_start, candidate_start) > 0:
                        current.extend(candidate)
                        current_start = min(current_start, candidate_start)
                        current_end = max(current_end, candidate_end)
                        changed = True
                    else:
                        keep.append(candidate)
                interval_groups = keep
                merged.append(current)
            interval_groups = merged

        interval_groups.sort(
            key=lambda group: (
                min(as_int(row["raw_tract_start"]) for row in group),
                min(as_int(row["raw_tract_end"]) for row in group),
            )
        )

        event_descriptors = []
        for event_index, competitors in enumerate(interval_groups):
            primary = sorted(competitors, key=attempt_rank)[0]
            event_start = as_int(primary["raw_tract_start"])
            event_end = as_int(primary["raw_tract_end"])
            repeat_event_id = stable_id(
                f"REPEAT_EVENT|{evidence_id}|{event_index}|{event_start}|{event_end}"
            )
            event_descriptors.append(
                {
                    "event_index": event_index,
                    "competitors": competitors,
                    "primary": primary,
                    "repeat_event_id": repeat_event_id,
                }
            )

        best_event = None
        if event_descriptors:
            best_event = sorted(
                event_descriptors,
                key=lambda descriptor: attempt_rank(descriptor["primary"]),
            )[0]

        for descriptor in event_descriptors:
            primary = descriptor["primary"]
            is_best = descriptor is best_event
            for competitor in descriptor["competitors"]:
                if competitor is primary:
                    status = (
                        "RETAINED_PRIMARY_EVENT"
                        if is_best
                        else "RETAINED_ADDITIONAL_EVENT"
                    )
                else:
                    status = "COMPETING_OVERLAPPING_ATTEMPT"
                call_annotations[competitor["projection_id"]] = {
                    "materialization_status": status,
                    "repeat_event_id": descriptor["repeat_event_id"],
                }

        for row in attempts:
            if row["projection_id"] in call_annotations:
                continue
            if row.get("integration_status") == "CALLED":
                status = "CALLED_NOT_RETAINED"
            else:
                status = "NOT_CALLED"
            call_annotations[row["projection_id"]] = {
                "materialization_status": status,
                "repeat_event_id": ".",
            }

        best_attempt = (
            best_event["primary"]
            if best_event is not None
            else sorted(attempts, key=attempt_rank)[0]
        )
        evidence_data[evidence_id] = {
            "key": key,
            "attempts": attempts,
            "best_attempt": best_attempt,
            "events": event_descriptors,
            "best_event": best_event,
        }

    # Materialize events, components, and interruptions first so caller/read FKs can refer to them.
    event_summary_by_id: dict[str, dict] = {}
    primary_repeat_call_by_projection: dict[str, str] = {}

    for evidence_id, data in evidence_data.items():
        read_id, target_region_id, locus_id = data["key"]
        for descriptor in data["events"]:
            primary = descriptor["primary"]
            event_id = descriptor["repeat_event_id"]
            projection_id = primary["projection_id"]
            caller_record_id = caller_record_by_projection[projection_id]
            window_start = as_int(primary.get("candidate_window_read_start"))
            if window_start is None:
                raise RuntimeError(f"called row lacks candidate window start: {projection_id}")

            segment_objects = parse_json_list(
                primary.get("repeat_segments_json", "."),
                "repeat_segments_json",
                projection_id,
            )
            if not segment_objects:
                raise RuntimeError(f"called row has zero repeat segments: {projection_id}")

            expected_segment_count = as_int(primary.get("repeat_segment_count"))
            if expected_segment_count != len(segment_objects):
                raise RuntimeError(
                    f"segment count mismatch projection={projection_id} "
                    f"caller={expected_segment_count} parsed={len(segment_objects)}"
                )

            segment_material = []
            for segment_index, source in enumerate(segment_objects):
                local_start = as_int(source.get("read_start"))
                local_end = as_int(source.get("read_end"))
                if local_start is None or local_end is None or local_end <= local_start:
                    raise RuntimeError(f"invalid segment coordinates projection={projection_id}")
                raw_start = window_start + local_start
                raw_end = window_start + local_end
                observed_bp = raw_end - raw_start
                if as_int(source.get("observed_bp")) != observed_bp:
                    raise RuntimeError(
                        f"segment observed length mismatch projection={projection_id}"
                    )
                segment_material.append(
                    {
                        "source": source,
                        "segment_index": segment_index,
                        "raw_start": raw_start,
                        "raw_end": raw_end,
                    }
                )

            segment_material.sort(
                key=lambda item: (item["raw_start"], item["raw_end"], item["segment_index"])
            )
            for index, item in enumerate(segment_material):
                item["segment_index"] = index

            primary_segment = sorted(
                segment_material,
                key=lambda item: (
                    -(as_float(item["source"].get("score"), -1e18)),
                    -(as_int(item["source"].get("observed_bp"), -1)),
                    -(as_float(item["source"].get("purity"), -1e18)),
                    item["segment_index"],
                ),
            )[0]

            interruptions = parse_json_list(
                primary.get("interruption_segments_json", "."),
                "interruption_segments_json",
                projection_id,
            )
            expected_interruptions = as_int(primary.get("interruption_count"), 0)
            if expected_interruptions != len(interruptions):
                raise RuntimeError(
                    f"interruption count mismatch projection={projection_id} "
                    f"caller={expected_interruptions} parsed={len(interruptions)}"
                )

            event_start = min(item["raw_start"] for item in segment_material)
            event_end = max(item["raw_end"] for item in segment_material)
            if event_start != as_int(primary["raw_tract_start"]) or event_end != as_int(
                primary["raw_tract_end"]
            ):
                raise RuntimeError(
                    f"segment/event coordinate mismatch projection={projection_id} "
                    f"segments={event_start}-{event_end} "
                    f"caller={primary['raw_tract_start']}-{primary['raw_tract_end']}"
                )

            repeat_call_ids = {}
            for item in segment_material:
                source = item["source"]
                canonical = source.get("canonical_motif", primary.get("canonical_motif", "."))
                repeat_call_id = stable_id(
                    f"REPEAT_SEGMENT|{event_id}|{item['segment_index']}|"
                    f"{item['raw_start']}|{item['raw_end']}|{canonical}"
                )
                repeat_call_ids[item["segment_index"]] = repeat_call_id

            primary_repeat_call_id = repeat_call_ids[primary_segment["segment_index"]]
            primary_repeat_call_by_projection[projection_id] = primary_repeat_call_id

            interruption_patterns_by_segment: dict[int, list[str]] = defaultdict(list)
            normalized_interruptions = []
            for interruption_index, source in enumerate(interruptions):
                local_start = as_int(source.get("read_start"))
                local_end = as_int(source.get("read_end"))
                if local_start is None or local_end is None or local_end <= local_start:
                    raise RuntimeError(
                        f"invalid interruption coordinates projection={projection_id}"
                    )
                raw_start = window_start + local_start
                raw_end = window_start + local_end
                if raw_end - raw_start != as_int(source.get("length_bp")):
                    raise RuntimeError(
                        f"interruption length mismatch projection={projection_id}"
                    )
                left_index = None
                right_index = None
                for item in segment_material:
                    if item["raw_end"] == raw_start:
                        left_index = item["segment_index"]
                    if item["raw_start"] == raw_end:
                        right_index = item["segment_index"]
                sequence = source.get("sequence", ".")
                pattern = f"{raw_start}-{raw_end}:{sequence}"
                if left_index is not None:
                    interruption_patterns_by_segment[left_index].append(pattern)
                if right_index is not None:
                    interruption_patterns_by_segment[right_index].append(pattern)
                left_motif = (
                    segment_material[left_index]["source"].get("canonical_motif")
                    if left_index is not None
                    else None
                )
                right_motif = (
                    segment_material[right_index]["source"].get("canonical_motif")
                    if right_index is not None
                    else None
                )
                operation_class = (
                    "MOTIF_SWITCH"
                    if left_motif is not None
                    and right_motif is not None
                    and left_motif != right_motif
                    else "OTHER"
                )
                interruption_id = stable_id(
                    f"INTERRUPTION|{event_id}|{interruption_index}|{raw_start}|{raw_end}"
                )
                row = blank_row(interruption_fields)
                row.update(
                    {
                        "schema_version": "0.4.2",
                        "run_id": run_id,
                        "sample_id": sample_id,
                        "interruption_id": interruption_id,
                        "caller_record_id": caller_record_id,
                        "evidence_id": evidence_id,
                        "repeat_event_id": event_id,
                        "repeat_call_id": ".",
                        "read_id": read_id,
                        "locus_id": locus_id,
                        "interruption_index": interruption_index,
                        "read_start": raw_start,
                        "read_end": raw_end,
                        "interruption_bp": raw_end - raw_start,
                        "sequence": sequence,
                        "interruption_class": (
                            "MOTIF_SWITCH"
                            if operation_class == "MOTIF_SWITCH"
                            else "SEQUENCE_INTERRUPTION"
                        ),
                        "left_repeat_segment_index": left_index,
                        "right_repeat_segment_index": right_index,
                        "source_json": json.dumps(
                            source, sort_keys=True, separators=(",", ":")
                        ),
                        "notes": MATERIALIZER_VERSION,
                        "operation_class": operation_class,
                        "discordance_origin_status": "NOT_ASSESSED",
                        "discordance_origin_confidence": "NOT_ASSESSED",
                        "discordance_origin_evidence_flags": ".",
                        "discordance_model_id": ".",
                    }
                )
                enforce_required(schema, "repeat_interruptions", row, interruption_id)
                interruption_rows.append(row)
                normalized_interruptions.append(row)

            for item in segment_material:
                source = item["source"]
                segment_index = item["segment_index"]
                canonical = source.get("canonical_motif", primary.get("canonical_motif", "."))
                oriented = source.get("oriented_motif", primary.get("oriented_motif", "."))
                repeat_call_id = repeat_call_ids[segment_index]
                row = blank_row(segment_fields)
                row.update(
                    {
                        "schema_version": "0.4.2",
                        "run_id": run_id,
                        "sample_id": sample_id,
                        "repeat_call_id": repeat_call_id,
                        "evidence_id": evidence_id,
                        "read_id": read_id,
                        "locus_id": locus_id,
                        "segment_index": segment_index,
                        "motif": oriented,
                        "canonical_motif": canonical,
                        "read_start": item["raw_start"],
                        "read_end": item["raw_end"],
                        "repeat_bp": item["raw_end"] - item["raw_start"],
                        "repeat_units_float": (
                            (item["raw_end"] - item["raw_start"]) / max(1, len(canonical))
                        ),
                        "purity": source.get("purity", "."),
                        "match_bp": source.get("matches", "."),
                        "mismatch_bp": source.get("mismatches", "."),
                        "insertion_bp": source.get("insertions", "."),
                        "deletion_bp": source.get("deletions", "."),
                        "interruption_count": len(
                            interruption_patterns_by_segment.get(segment_index, [])
                        ),
                        "interruption_pattern": (
                            ";".join(interruption_patterns_by_segment[segment_index])
                            if interruption_patterns_by_segment.get(segment_index)
                            else "."
                        ),
                        "left_boundary_confidence": ".",
                        "right_boundary_confidence": ".",
                        "call_method": "GENERAL_CALLER_NATIVE_V0.4.1",
                        "call_score": source.get("score", "."),
                        "call_status": primary.get("call_status", "."),
                        "call_flags": ";".join(event_flags_for(primary)) or ".",
                        "repeat_event_id": event_id,
                        "caller_record_id": caller_record_id,
                        "segment_role": (
                            "PRIMARY"
                            if segment_index == primary_segment["segment_index"]
                            else "COMPONENT"
                        ),
                        "motif_source": source.get(
                            "motif_source", primary.get("motif_source", ".")
                        ),
                        "motif_path_bp": source.get("motif_path_bp", "."),
                        "repeat_units_path": source.get("repeat_units_path", "."),
                        "score_per_read_bp": (
                            as_float(source.get("score"), 0.0)
                            / max(1, item["raw_end"] - item["raw_start"])
                        ),
                        "left_boundary_status": (
                            primary.get("left_boundary_status", ".")
                            if segment_index == 0
                            else "SEQUENCE_BOUNDED"
                        ),
                        "right_boundary_status": (
                            primary.get("right_boundary_status", ".")
                            if segment_index == len(segment_material) - 1
                            else "SEQUENCE_BOUNDED"
                        ),
                        "touches_left_sequence_edge": (
                            primary.get("touches_left_sequence_edge", "false")
                            if segment_index == 0
                            else "false"
                        ),
                        "touches_right_sequence_edge": (
                            primary.get("touches_right_sequence_edge", "false")
                            if segment_index == len(segment_material) - 1
                            else "false"
                        ),
                    }
                )
                enforce_required(schema, "repeat_segments", row, repeat_call_id)
                segment_rows.append(row)

            exact = primary.get("exact_repeat_bp", ".")
            lower = (
                primary.get("interval_lower_bp")
                if present(primary.get("interval_lower_bp"))
                else primary.get("lower_bound_bp", ".")
            )
            upper = primary.get("interval_upper_bp", ".")
            normalized_sizing = normalize_sizing(
                "CALLED", primary.get("sizing_status", "."), schema
            )
            normalized_evidence = normalize_geometry(
                primary.get("evidence_geometry", "."),
                normalized_sizing,
                True,
                schema,
            )
            distinct_motifs = {
                item["source"].get("canonical_motif", ".")
                for item in segment_material
            }
            repeat_units_estimate = (
                primary.get("repeat_units_path", ".")
                if len(distinct_motifs) == 1
                else "."
            )
            matches = sum(as_int(item["source"].get("matches"), 0) for item in segment_material)
            mismatches = sum(
                as_int(item["source"].get("mismatches"), 0) for item in segment_material
            )
            insertions = sum(
                as_int(item["source"].get("insertions"), 0) for item in segment_material
            )
            deletions = sum(
                as_int(item["source"].get("deletions"), 0) for item in segment_material
            )
            denominator = matches + mismatches + insertions + deletions
            interruption_bp_total = sum(
                as_int(row["interruption_bp"], 0) for row in normalized_interruptions
            )
            flags = event_flags_for(primary)
            if len(descriptor["competitors"]) > 1:
                flags.append("OVERLAPPING_CALLER_ATTEMPTS")

            event_row = blank_row(event_fields)
            event_row.update(
                {
                    "schema_version": "0.4.2",
                    "run_id": run_id,
                    "sample_id": sample_id,
                    "repeat_event_id": event_id,
                    "evidence_id": evidence_id,
                    "primary_caller_record_id": caller_record_id,
                    "primary_repeat_call_id": primary_repeat_call_id,
                    "read_id": read_id,
                    "locus_id": locus_id,
                    "event_index": descriptor["event_index"],
                    "read_start": event_start,
                    "read_end": event_end,
                    "repeat_bp_observed": event_end - event_start,
                    "exact_repeat_bp": exact,
                    "repeat_bp_lower_bound": lower,
                    "repeat_bp_upper_bound": upper,
                    "repeat_units_estimate": repeat_units_estimate,
                    "canonical_motif": primary.get("canonical_motif", "."),
                    "oriented_motif": primary.get("oriented_motif", "."),
                    "motif_source": primary.get("motif_source", "."),
                    "compound_status": primary.get("compound_status", "."),
                    "segment_count": len(segment_material),
                    "distinct_motif_count": len(distinct_motifs),
                    "interruption_count": len(normalized_interruptions),
                    "purity": primary.get("purity", "."),
                    "score": primary.get("score", "."),
                    "score_per_read_bp": primary.get("score_per_read_bp", "."),
                    "lps_exact_sequence_bp": primary.get("lps_exact_sequence_bp", "."),
                    "lps_inferred_bp": primary.get("lps_inferred_bp", "."),
                    "lps_status": primary.get("lps_status", "."),
                    "evidence_class": normalized_evidence,
                    "sizing_status": normalized_sizing,
                    "caller_sizing_status": primary.get("sizing_status", "."),
                    "call_status": primary.get("call_status", "."),
                    "caller_evidence_geometry": primary.get("evidence_geometry", "."),
                    "sequence_context": primary.get("sequence_context", "."),
                    "context_limited": primary.get("context_limited", "false"),
                    "prior_overlap_bp": primary.get("prior_overlap_bp", "."),
                    "hypothesis_count": primary.get("hypothesis_count", "."),
                    "alternative_canonical_motif": primary.get(
                        "alternative_canonical_motif", "."
                    ),
                    "alternative_score": primary.get("alternative_score", "."),
                    "primary_minus_alternative_score": primary.get(
                        "primary_minus_alternative_score", "."
                    ),
                    "event_flags": ";".join(flags) or ".",
                    "match_bp_total": matches,
                    "mismatch_bp_total": mismatches,
                    "insertion_bp_total": insertions,
                    "deletion_bp_total": deletions,
                    "interruption_bp_total": interruption_bp_total,
                    "mismatch_fraction": (
                        mismatches / denominator if denominator else 0.0
                    ),
                    "indel_fraction": (
                        (insertions + deletions) / denominator if denominator else 0.0
                    ),
                    "edit_fraction": (
                        (mismatches + insertions + deletions) / denominator
                        if denominator
                        else 0.0
                    ),
                    "discordance_origin_status": "NOT_ASSESSED",
                    "discordance_origin_confidence": "NOT_ASSESSED",
                    "discordance_origin_evidence_flags": ".",
                    "discordance_model_id": ".",
                }
            )
            enforce_required(schema, "repeat_events", event_row, event_id)
            event_rows.append(event_row)
            event_summary_by_id[event_id] = {
                "row": event_row,
                "segment_ids": [
                    repeat_call_ids[index] for index in sorted(repeat_call_ids)
                ],
                "primary_repeat_call_id": primary_repeat_call_id,
                "primary": primary,
            }

    # Materialize lossless caller attempts.
    raw_suffix_hash = hashlib.sha256()
    output_suffix_hash = hashlib.sha256()
    caller_input_fields = list(calls[0].keys())
    expected_general_suffix = general_fields[-len(caller_input_fields) :]
    if expected_general_suffix != caller_input_fields:
        raise RuntimeError("general_repeat_calls suffix does not match caller header")

    for row in calls:
        projection_id = row["projection_id"]
        caller_version = (
            row["caller_version"] if present(row.get("caller_version")) else DEFAULT_CALLER_VERSION
        )
        caller_record_id = caller_record_by_projection[projection_id]
        key = (
            row["read_id"],
            row["target_region_id"],
            row["representative_locus_id"],
        )
        evidence_id = stable_id(
            f"{run_id}|{key[0]}|{key[1]}|{key[2]}"
        )
        annotation = call_annotations[projection_id]
        event_id = annotation["repeat_event_id"]
        primary_repeat_call_id = primary_repeat_call_by_projection.get(projection_id, ".")
        output = blank_row(general_fields)
        output.update(
            {
                "schema_version": "0.4.2",
                "run_id": run_id,
                "sample_id": sample_id,
                "caller_record_id": caller_record_id,
                "evidence_id": evidence_id,
                "materialization_status": annotation["materialization_status"],
                "repeat_event_id": event_id,
                "primary_repeat_call_id": primary_repeat_call_id,
            }
        )
        for field in caller_input_fields:
            output[field] = row[field]
        enforce_required(schema, "general_repeat_calls", output, projection_id)
        general_rows.append(output)
        raw_line = "\t".join(row[field] for field in caller_input_fields) + "\n"
        raw_suffix_hash.update(raw_line.encode())
        out_line = "\t".join(fmt(output[field]) for field in caller_input_fields) + "\n"
        output_suffix_hash.update(out_line.encode())

    if raw_suffix_hash.hexdigest() != output_suffix_hash.hexdigest():
        raise RuntimeError("lossless caller suffix hash mismatch")

    # Read-level summaries.
    event_rows_by_evidence: dict[str, list[dict[str, object]]] = defaultdict(list)
    segment_rows_by_evidence: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in event_rows:
        event_rows_by_evidence[str(row["evidence_id"])].append(row)
    for row in segment_rows:
        segment_rows_by_evidence[str(row["evidence_id"])].append(row)

    required_enum_defaults: dict[str, str] = {}
    for evidence_id, data in evidence_data.items():
        read_id, target_region_id, locus_id = data["key"]
        attempts = data["attempts"]
        best = data["best_attempt"]
        best_projection = projection_by[best["projection_id"]]
        events = event_rows_by_evidence.get(evidence_id, [])
        segments = segment_rows_by_evidence.get(evidence_id, [])
        best_event_descriptor = data["best_event"]
        best_event_row = (
            event_summary_by_id[best_event_descriptor["repeat_event_id"]]["row"]
            if best_event_descriptor is not None
            else None
        )

        row = blank_row(read_fields)

        # Exact-name projection fields are copied before semantic aliases.
        for field in read_fields:
            if field in best_projection and present(best_projection[field]):
                row[field] = best_projection[field]
            elif field in best and present(best[field]):
                row[field] = best[field]

        read_length, mean_q = fastq_meta[read_id]
        row.update(
            {
                "schema_version": "0.4.2",
                "run_id": run_id,
                "sample_id": sample_id,
                "evidence_id": evidence_id,
                "read_id": read_id,
                "read_length_bp": best_projection.get("read_length_bp", read_length),
                "mean_read_q": best_projection.get("mean_read_q", mean_q),
                "target_region_id": target_region_id,
                "target_source": best.get("target_source", "."),
                "region_type": best.get("region_type", "."),
                "analysis_mode": best_projection.get("analysis_mode", "."),
                "locus_id": locus_id,
                "primary_alignment_id": best_projection.get("best_alignment_id", "."),
                "assignment_rank": best.get("assignment_rank", "."),
                "competing_locus_count": max(
                    0, (as_int(best.get("read_candidate_target_count"), 1) or 1) - 1
                ),
                "target_overlap_bp": best_projection.get(
                    "selected_block_overlap_bp",
                    best_projection.get("target_overlap_bp_reported", "."),
                ),
                "target_distance_bp": best_projection.get(
                    "selected_block_distance_bp",
                    best_projection.get("target_distance_bp_reported", "."),
                ),
                "mapq_best": best.get("best_mapq", "."),
                "alignment_class_best": best_projection.get(
                    "best_alignment_class", "."
                ),
                "strand": best.get("strand", "."),
                "left_flank_anchor_bp": best_projection.get(
                    "genomic_left_anchor_bp", "."
                ),
                "right_flank_anchor_bp": best_projection.get(
                    "genomic_right_anchor_bp", "."
                ),
                "caller_attempt_count": len(attempts),
                "caller_called_count": sum(
                    attempt.get("integration_status") == "CALLED"
                    for attempt in attempts
                ),
                "caller_error_count": sum(
                    attempt.get("integration_status") == "CALLER_ERROR"
                    or present(attempt.get("caller_error"))
                    for attempt in attempts
                ),
                "repeat_event_count": len(events),
                "repeat_call_count": len(segments),
                "best_projection_id": best["projection_id"],
                "best_caller_record_id": caller_record_by_projection[
                    best["projection_id"]
                ],
                "best_caller_version": best.get("caller_version", "."),
                "best_caller_integration_status": best.get(
                    "integration_status", "."
                ),
                "best_caller_call_status": best.get("call_status", "."),
                "best_caller_sizing_status": best.get("sizing_status", "."),
                "molecule_cluster_id": ".",
                "confidence_label": confidence_for(best, schema),
                "confidence_score": ".",
                "qc_status": qc_status_for(best, schema),
                "failure_code": failure_for(best, schema),
                "qc_flags": ";".join(event_flags_for(best)) or ".",
                "notes": MATERIALIZER_VERSION,
            }
        )

        # Assignment status is not identical to projection status. Use a neutral,
        # schema-valid assigned state for this catalog hypothesis.
        row["assignment_status"] = choose_enum(
            schema,
            "assignment_status",
            ["ASSIGNED", "ASSIGNED_UNIQUE", "RESOLVED", "PASS"],
            required=True,
        )

        # Some historical enum fields are required. Existing projection values are
        # preferred; only analysis_mode may require a schema-level default.
        if not present(row.get("analysis_mode")):
            row["analysis_mode"] = choose_enum(
                schema,
                "analysis_mode",
                ["candidate_screening", "CATALOG_GUIDED", "TARGETED"],
                required=True,
            )

        # Flank uniqueness is not computed by the current projection layer.
        # Never infer uniqueness from anchor length, MAPQ, or geometry.
        for side in ("left", "right"):
            boolean_field = f"{side}_flank_unique"
            status_field = f"{side}_flank_uniqueness_status"
            observed = best_projection.get(boolean_field, ".")
            if observed == "true":
                row[boolean_field] = "true"
                row[status_field] = "ASSESSED_UNIQUE"
            elif observed == "false":
                row[boolean_field] = "false"
                row[status_field] = "ASSESSED_NONUNIQUE"
            else:
                row[boolean_field] = "."
                row[status_field] = "NOT_ASSESSED"

        if best_event_row is not None:
            row.update(
                {
                    "motif": best_event_row["oriented_motif"],
                    "canonical_motif": best_event_row["canonical_motif"],
                    "evidence_class": best_event_row["evidence_class"],
                    "sizing_status": best_event_row["sizing_status"],
                    "best_repeat_event_id": best_event_row["repeat_event_id"],
                    "best_repeat_call_id": best_event_row[
                        "primary_repeat_call_id"
                    ],
                    "repeat_bp_estimate": best_event_row["exact_repeat_bp"],
                    "repeat_bp_lower_bound": best_event_row[
                        "repeat_bp_lower_bound"
                    ],
                    "repeat_bp_upper_bound": best_event_row[
                        "repeat_bp_upper_bound"
                    ],
                    "repeat_units_estimate": best_event_row[
                        "repeat_units_estimate"
                    ],
                    "repeat_purity": best_event_row["purity"],
                    "interruption_count": best_event_row["interruption_count"],
                    "motif_source": best_event_row["motif_source"],
                    "compound_status": best_event_row["compound_status"],
                    "lps_exact_sequence_bp": best_event_row[
                        "lps_exact_sequence_bp"
                    ],
                    "lps_inferred_bp": best_event_row["lps_inferred_bp"],
                    "lps_status": best_event_row["lps_status"],
                    "caller_evidence_geometry": best_event_row[
                        "caller_evidence_geometry"
                    ],
                    "sequence_context": best_event_row["sequence_context"],
                    "context_limited": best_event_row["context_limited"],
                    "prior_overlap_bp": best_event_row["prior_overlap_bp"],
                    "hypothesis_count": best_event_row["hypothesis_count"],
                    "alternative_canonical_motif": best_event_row[
                        "alternative_canonical_motif"
                    ],
                    "alternative_score": best_event_row["alternative_score"],
                    "primary_minus_alternative_score": best_event_row[
                        "primary_minus_alternative_score"
                    ],
                }
            )
        else:
            catalog_motifs = [
                motif
                for motif in best.get("catalog_motifs", ".").split(",")
                if present(motif)
            ]
            if len(catalog_motifs) == 1:
                row["motif"] = catalog_motifs[0]
                row["canonical_motif"] = catalog_motifs[0]
            row["evidence_class"] = normalize_geometry(
                best.get("evidence_geometry", "."),
                "not_attempted",
                False,
                schema,
            )
            row["sizing_status"] = normalize_sizing(
                best.get("integration_status", "."), ".", schema
            )
            row["best_repeat_event_id"] = "."
            row["best_repeat_call_id"] = "."
            row["repeat_bp_estimate"] = "."
            row["repeat_bp_lower_bound"] = "."
            row["repeat_bp_upper_bound"] = "."
            row["repeat_units_estimate"] = "."
            row["repeat_purity"] = "."
            row["interruption_count"] = 0
            row["context_limited"] = "false"

        enforce_required(schema, "read_evidence", row, evidence_id)
        read_rows.append(row)

    # Stable row ordering.
    general_rows.sort(key=lambda row: str(row["projection_id"]))
    read_rows.sort(key=lambda row: str(row["evidence_id"]))
    event_rows.sort(
        key=lambda row: (
            str(row["evidence_id"]),
            as_int(row["event_index"], 0),
            str(row["repeat_event_id"]),
        )
    )
    segment_rows.sort(
        key=lambda row: (
            str(row["evidence_id"]),
            str(row["repeat_event_id"]),
            as_int(row["segment_index"], 0),
            str(row["repeat_call_id"]),
        )
    )
    interruption_rows.sort(
        key=lambda row: (
            str(row["evidence_id"]),
            str(row["repeat_event_id"]),
            as_int(row["interruption_index"], 0),
            str(row["interruption_id"]),
        )
    )

    materialization_start = time.perf_counter()
    plain_paths = {
        "read_evidence": outdir / "read_evidence.tsv",
        "general_repeat_calls": outdir / "general_repeat_calls.tsv",
        "repeat_events": outdir / "repeat_events.tsv",
        "repeat_segments": outdir / "repeat_segments.tsv",
        "repeat_interruptions": outdir / "repeat_interruptions.tsv",
    }
    write_plain_tsv(plain_paths["read_evidence"], read_fields, read_rows)
    write_plain_tsv(plain_paths["general_repeat_calls"], general_fields, general_rows)
    write_plain_tsv(plain_paths["repeat_events"], event_fields, event_rows)
    write_plain_tsv(plain_paths["repeat_segments"], segment_fields, segment_rows)
    write_plain_tsv(
        plain_paths["repeat_interruptions"], interruption_fields, interruption_rows
    )
    write_seconds = time.perf_counter() - materialization_start

    gzip_start = time.perf_counter()
    gzip_paths = {}
    for table, plain_path in plain_paths.items():
        gz_path = outdir / f"{table}.tsv.gz"
        gzip_deterministic(plain_path, gz_path)
        gzip_paths[table] = gz_path
    gzip_seconds = time.perf_counter() - gzip_start

    # Package manifest.
    manifest_rows = []
    for table in plain_paths:
        for path in [plain_paths[table], gzip_paths[table]]:
            with path.open("rb") as handle:
                size = path.stat().st_size
            row_count = {
                "read_evidence": len(read_rows),
                "general_repeat_calls": len(general_rows),
                "repeat_events": len(event_rows),
                "repeat_segments": len(segment_rows),
                "repeat_interruptions": len(interruption_rows),
            }[table]
            manifest_rows.append(
                {
                    "artifact": path.name,
                    "table": table,
                    "rows": row_count,
                    "bytes": size,
                    "sha256": sha256_file(path),
                    "path": str(path),
                }
            )
    write_plain_tsv(
        outdir / "package_manifest.tsv",
        ["artifact", "table", "rows", "bytes", "sha256", "path"],
        manifest_rows,
    )

    summary = [
        ("stage_version", MATERIALIZER_VERSION),
        ("schema_version", "0.4.2"),
        ("input_caller_attempt_rows", len(calls)),
        ("projection_rows", len(projections)),
        ("evidence_rows", len(read_rows)),
        ("left_flank_uniqueness_not_assessed_rows", sum(row.get("left_flank_uniqueness_status") == "NOT_ASSESSED" for row in read_rows)),
        ("right_flank_uniqueness_not_assessed_rows", sum(row.get("right_flank_uniqueness_status") == "NOT_ASSESSED" for row in read_rows)),
        ("called_attempt_rows", sum(row["integration_status"] == "CALLED" for row in calls)),
        ("repeat_event_rows", len(event_rows)),
        ("repeat_segment_rows", len(segment_rows)),
        ("repeat_interruption_rows", len(interruption_rows)),
        ("multi_attempt_evidence_rows", sum(len(data["attempts"]) > 1 for data in evidence_data.values())),
        ("multi_event_evidence_rows", sum(len(data["events"]) > 1 for data in evidence_data.values())),
        ("caller_suffix_lossless_sha_match", "true"),
        ("discordance_origin_not_assessed_event_rows", sum(row.get("discordance_origin_status") == "NOT_ASSESSED" for row in event_rows)),
        ("discordance_origin_not_assessed_interruption_rows", sum(row.get("discordance_origin_status") == "NOT_ASSESSED" for row in interruption_rows)),
        ("clustering_algorithm_run", "false"),
        ("cluster_analysis_status", "NOT_RUN"),
        ("input_table_load_seconds", load_seconds),
        ("fastq_scan_seconds", fastq_seconds),
        ("materialization_write_seconds", write_seconds),
        ("gzip_seconds", gzip_seconds),
        ("materializer_wall_seconds", time.perf_counter() - t0),
        ("production_outputs_modified", "false"),
        ("ssot_modified", "false"),
        ("audit_status", "PASS"),
    ]
    with (outdir / "materialization.qc.tsv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["metric", "value"])
        writer.writerows(summary)

    print("===== STAGE 14K MATERIALIZATION =====")
    for key, value in summary:
        print(f"{key}\t{value}")


if __name__ == "__main__":
    main()
