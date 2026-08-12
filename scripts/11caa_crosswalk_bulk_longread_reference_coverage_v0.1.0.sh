#!/usr/bin/env bash
set -euo pipefail

STAGE_VERSION="rnatr_bulk_longread_reference_crosswalk_coverage_v0.1.0"
RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"
EXPECTED_PACKAGE_VERSION="0.3.2"
EXPECTED_QUERY_LOCI="11042"
EXPECTED_TREX_ROWS="5599658"
EXPECTED_VIENNA_ROWS="361362"
SOURCE_CACHE_VERSION="rnatr_bulk_longread_population_reference_acquisition_v0.1.0"
NEARBY_BP="100"
INDEX_BIN_BP="10000"
MIN_RECIPROCAL_OVERLAP="0.66"

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
  # shellcheck disable=SC1091
  source "$HOME/miniconda3/etc/profile.d/conda.sh"
fi
conda activate rnatr-v03
# shellcheck disable=SC1091
source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

for tool in python gzip sha256sum stat readlink flock column bigBedInfo; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "ERROR: required tool unavailable: $tool" >&2
    exit 1
  }
done

installed_version="$(rnatr-scout version)"
[[ "$installed_version" == "$EXPECTED_PACKAGE_VERSION" ]] || {
  echo "ERROR: expected rnatr-scout $EXPECTED_PACKAGE_VERSION; observed $installed_version" >&2
  exit 1
}

QUERY_ROOT="$PROJECT_ROOT/results/11_reference_control_adapter_query_package/$RUN_ID/rnatr_reference_control_adapter_query_package_v0.1.0"
QUERY_QC="$PROJECT_ROOT/qc/11_reference_control_adapter_query_package/$RUN_ID/rnatr_reference_control_adapter_query_package_v0.1.0/reference_control_adapter_query_package.qc.tsv"
QUERIES="$QUERY_ROOT/p01_locus.reference_control_queries.tsv.gz"

STAGE6R_ROOT="$PROJECT_ROOT/results/11_repeatcatalogs_crosswalk_coverage_audit/$RUN_ID/rnatr_repeatcatalogs_crosswalk_coverage_audit_v0.1.2"
STAGE6R_QC="$PROJECT_ROOT/qc/11_repeatcatalogs_crosswalk_coverage_audit/$RUN_ID/rnatr_repeatcatalogs_crosswalk_coverage_audit_v0.1.2/repeatcatalogs_crosswalk_coverage_audit.qc.tsv"
STAGE6R_ALL="$STAGE6R_ROOT/tables/p01_locus.repeatcatalogs_crosswalk_coverage_audit.tsv.gz"

SOURCE_ROOT="$PROJECT_ROOT/external_reference/rnatr_population_reference/bulk_sources/$SOURCE_CACHE_VERSION"
AOU_ROOT="$SOURCE_ROOT/aou_longread_tr/zenodo_record_19895393"
TREX_ROOT="$SOURCE_ROOT/trexplorer_v2_ucsc"
VIENNA_ROOT="$SOURCE_ROOT/vienna_ont_v1.1"
TREX_BB="$TREX_ROOT/trexplorer.bb"
TREX_BED_GZ="$TREX_ROOT/trexplorer.bed.gz"
VIENNA_BB="$VIENNA_ROOT/viennaVntr.bb"
VIENNA_SUMMARY="$VIENNA_ROOT/vamos-summary.tsv"

STAGE6Z_RESULT_LINK="$PROJECT_ROOT/results/11_bulk_longread_population_reference_acquisition/$RUN_ID/latest"
STAGE6Z_QC_LINK="$PROJECT_ROOT/qc/11_bulk_longread_population_reference_acquisition/$RUN_ID/latest"
STAGE6Z_RESULT="$(readlink -f "$STAGE6Z_RESULT_LINK")"
STAGE6Z_QC_ROOT="$(readlink -f "$STAGE6Z_QC_LINK")"
STAGE6Z_QC="$STAGE6Z_QC_ROOT/bulk_longread_population_reference_acquisition.qc.tsv"
STAGE6Z_MANIFEST="$STAGE6Z_RESULT/manifests/local_source_artifact_manifest.tsv"

for path in \
  "$QUERY_QC" "$QUERIES" \
  "$STAGE6R_QC" "$STAGE6R_ALL" \
  "$STAGE6Z_QC" "$STAGE6Z_MANIFEST" \
  "$TREX_BB" "$TREX_BED_GZ" \
  "$VIENNA_BB" "$VIENNA_SUMMARY" \
  "$AOU_ROOT/files"
do
  [[ -e "$path" ]] || {
    echo "ERROR: missing prerequisite: $path" >&2
    exit 1
  }
done

gzip -t "$QUERIES"
gzip -t "$STAGE6R_ALL"
gzip -t "$TREX_BED_GZ"

metric() {
  local file="$1" key="$2"
  awk -F $'\t' -v key="$key" '$1==key {print $2; found=1; exit} END{if(!found) print "."}' "$file"
}
require_metric() {
  local file="$1" key="$2" expected="$3" observed
  observed="$(metric "$file" "$key")"
  [[ "$observed" == "$expected" ]] || {
    echo "ERROR: $file expected $key=$expected; observed $observed" >&2
    exit 1
  }
}
require_metric "$QUERY_QC" adapter_query_package_status PASS
require_metric "$QUERY_QC" reference_query_rows "$EXPECTED_QUERY_LOCI"
require_metric "$STAGE6R_QC" stage6r_crosswalk_coverage_audit_status PASS
require_metric "$STAGE6R_QC" all_p01_loci_denominator "$EXPECTED_QUERY_LOCI"
require_metric "$STAGE6Z_QC" stage6z_bulk_reference_acquisition_status PASS_READY_FOR_CROSSWALK_AND_COVERAGE_AUDIT
require_metric "$STAGE6Z_QC" trexplorer_item_count "$EXPECTED_TREX_ROWS"
require_metric "$STAGE6Z_QC" vienna_ont_item_count "$EXPECTED_VIENNA_ROWS"

query_sha="$(sha256sum "$QUERIES" | awk '{print $1}')"
manifest_sha="$(sha256sum "$STAGE6Z_MANIFEST" | awk '{print $1}')"
script_sha="$(sha256sum "$0" | awk '{print $1}')"
source_signature="$(printf '%s\n%s\n' "$query_sha" "$manifest_sha" | sha256sum | awk '{print $1}')"
SNAPSHOT_ID="sha256_${source_signature}"

OUT_BASE="$PROJECT_ROOT/results/11_bulk_longread_reference_crosswalk_coverage/$RUN_ID/$STAGE_VERSION"
QC_BASE="$PROJECT_ROOT/qc/11_bulk_longread_reference_crosswalk_coverage/$RUN_ID/$STAGE_VERSION"
TMP_BASE="$PROJECT_ROOT/tmp/11_bulk_longread_reference_crosswalk_coverage/$RUN_ID/$STAGE_VERSION"
OUT_ROOT="$OUT_BASE/$SNAPSHOT_ID"
QC_ROOT="$QC_BASE/$SNAPSHOT_ID"
FINAL_QC="$QC_ROOT/bulk_longread_reference_crosswalk_coverage.qc.tsv"
ARTIFACT_MANIFEST="$OUT_ROOT/bulk_longread_reference_crosswalk_coverage.artifact_manifest.tsv"
LATEST_RESULT_LINK="$PROJECT_ROOT/results/11_bulk_longread_reference_crosswalk_coverage/$RUN_ID/latest"
LATEST_QC_LINK="$PROJECT_ROOT/qc/11_bulk_longread_reference_crosswalk_coverage/$RUN_ID/latest"
SCRIPT_DEST="$PROJECT_ROOT/scripts/$(basename "$0")"
mkdir -p "$OUT_BASE" "$QC_BASE" "$TMP_BASE" "$PROJECT_ROOT/scripts"

if [[ -s "$FINAL_QC" && -s "$ARTIFACT_MANIFEST" ]]; then
  echo "===== EXISTING STAGE 6AA CHECKPOINT ====="
  column -ts $'\t' "$FINAL_QC"
  echo
  echo "Result: $OUT_ROOT"
  exit 0
fi
if [[ -e "$OUT_ROOT" || -e "$QC_ROOT" ]]; then
  echo "ERROR: partial or invalid immutable checkpoint exists" >&2
  echo "  $OUT_ROOT" >&2
  echo "  $QC_ROOT" >&2
  exit 1
fi

exec 9>"$TMP_BASE/.stage.lock"
flock -n 9 || { echo "ERROR: another Stage 6AA process holds the lock" >&2; exit 1; }
WORK_ROOT="$(mktemp -d "$TMP_BASE/work.XXXXXXXX")"
trap 'rm -rf "$WORK_ROOT"' EXIT
STAGE_OUT="$WORK_ROOT/stage_out"
STAGE_QC="$WORK_ROOT/stage_qc"
mkdir -p "$STAGE_OUT"/{tables,summary,schema,provenance,contracts} "$STAGE_QC"

TREX_AS="$STAGE_OUT/schema/trexplorer.autosql.txt"
VIENNA_AS="$STAGE_OUT/schema/viennaVntr.autosql.txt"
bigBedInfo -as "$TREX_BB" > "$TREX_AS" 2>&1 || true
bigBedInfo -as "$VIENNA_BB" > "$VIENNA_AS" 2>&1 || true

PY_IMPL="$STAGE_OUT/provenance/rnatr_bulk_longread_reference_crosswalk_coverage_v0.1.0.py"
cat > "$PY_IMPL" <<'PY'
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import os
import re
import tempfile
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

VERSION = "rnatr_bulk_longread_reference_crosswalk_coverage_v0.1.0"
csv.field_size_limit(sys.maxsize)
IUPAC_COMP = str.maketrans("ACGTRYSWKMBDHVN", "TGCAYRSWMKVHDBN")


class ContractError(RuntimeError):
    pass


def open_text(path: Path):
    return gzip.open(path, "rt", encoding="utf-8", errors="replace", newline="") if path.suffix == ".gz" else path.open("rt", encoding="utf-8", errors="replace", newline="")


def read_tsv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with open_text(path) as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise ContractError(f"missing header: {path}")
        return list(reader.fieldnames), list(reader)


def atomic_tsv(path: Path, fields: list[str], rows: Iterable[Mapping[str, object]], gzip_output: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    os.close(fd)
    try:
        opener = gzip.open if gzip_output else open
        mode = "wt"
        with opener(tmp, mode, encoding="utf-8", newline="") as out:
            writer = csv.DictWriter(out, fieldnames=fields, delimiter="\t", lineterminator="\n", extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({k: row.get(k, ".") for k in fields})
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def norm_name(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def clean_motif(text: str) -> str:
    return re.sub(r"[^ACGTRYSWKMBDHVN]", "", (text or "").upper())


def rotations(seq: str) -> list[str]:
    return [seq[i:] + seq[:i] for i in range(len(seq))] if seq else []


def dihedral_canonical(seq: str) -> str:
    seq = clean_motif(seq)
    if not seq:
        return ""
    rc = seq.translate(IUPAC_COMP)[::-1]
    return min(rotations(seq) + rotations(rc))


def primitive_root(seq: str) -> str:
    seq = clean_motif(seq)
    if not seq:
        return ""
    for k in range(1, len(seq) + 1):
        if len(seq) % k == 0 and seq == seq[:k] * (len(seq) // k):
            return seq[:k]
    return seq


def motif_relation(a: str, b: str) -> str:
    a = clean_motif(a)
    b = clean_motif(b)
    if not a or not b:
        return "MOTIF_UNAVAILABLE"
    if dihedral_canonical(a) == dihedral_canonical(b):
        return "STRICT_DIHEDRAL_EQUIVALENT"
    if dihedral_canonical(primitive_root(a)) == dihedral_canonical(primitive_root(b)):
        return "PRIMITIVE_DIHEDRAL_EQUIVALENT"
    return "MOTIF_MISMATCH"


def overlap_bp(a0: int, a1: int, b0: int, b1: int) -> int:
    return max(0, min(a1, b1) - max(a0, b0))


def interval_distance(a0: int, a1: int, b0: int, b1: int) -> int:
    ov = overlap_bp(a0, a1, b0, b1)
    if ov:
        return 0
    return b0 - a1 if a1 <= b0 else a0 - b1


def bins_for(start: int, end: int, bin_bp: int, pad: int = 0) -> range:
    s = max(0, start - pad)
    e = end + pad
    return range(s // bin_bp, (e - 1) // bin_bp + 1)


def parse_autosql_fields(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    fields: list[str] = []
    in_body = False
    for raw in text.splitlines():
        line = raw.strip()
        if line == "(":
            in_body = True
            continue
        if not in_body:
            continue
        if line.startswith(")"):
            break
        m = re.match(r"(?:[A-Za-z][A-Za-z0-9]*(?:\[[^\]]+\])?)\s+([A-Za-z_][A-Za-z0-9_]*)\s*;", line)
        if m:
            fields.append(m.group(1))
    return fields


def choose_field(fields: list[str], preferred: list[str], contains: list[str] | None = None) -> int | None:
    normalized = [norm_name(x) for x in fields]
    for wanted in preferred:
        nw = norm_name(wanted)
        if nw in normalized:
            return normalized.index(nw)
    if contains:
        for i, name in enumerate(normalized):
            if all(token in name for token in contains):
                return i
    return None


@dataclass(frozen=True)
class SourceRec:
    chrom: str
    start: int
    end: int
    source_id: str
    motif: str
    reference_motif: str
    motif_size: str
    purity: str
    source_catalogs: str
    hprc_histogram: str


def parse_trexplorer(
    bed_gz: Path,
    autosql: Path,
    queries: list[dict[str, str]],
    nearby_bp: int,
    bin_bp: int,
    expected_rows: int,
) -> tuple[dict[str, list[SourceRec]], dict[str, object], list[str]]:
    fields = parse_autosql_fields(autosql)
    if len(fields) < 3:
        fields = ["chrom", "chromStart", "chromEnd"]
    idx_id = choose_field(fields, ["name", "id", "trId", "locusId", "regionId"])
    idx_canon = choose_field(fields, ["canonicalMotif", "canonMotif", "motifCanonical"])
    idx_ref = choose_field(fields, ["referenceMotif", "refMotif", "motif"])
    idx_msize = choose_field(fields, ["motifSize", "motifLength", "period"])
    idx_purity = choose_field(fields, ["purity", "referencePurity", "refPurity"])
    idx_source = choose_field(fields, ["source", "sources", "catalogSource", "catalogs"])
    hprc_candidates = [i for i, f in enumerate(fields) if "hprc" in norm_name(f) and any(t in norm_name(f) for t in ("hist", "copy", "allele"))]
    idx_hprc = hprc_candidates[0] if hprc_candidates else None

    qbins: dict[tuple[str, int], list[str]] = defaultdict(list)
    qcoords: dict[str, tuple[str, int, int]] = {}
    for q in queries:
        qid = q["reference_query_id"]
        chrom = q["chrom_with_prefix"]
        start = int(q["start_0based"])
        end = int(q["end_0based_exclusive"])
        qcoords[qid] = (chrom, start, end)
        for b in bins_for(start, end, bin_bp, nearby_bp):
            qbins[(chrom, b)].append(qid)

    candidates: dict[str, list[SourceRec]] = defaultdict(list)
    row_count = 0
    malformed = 0
    field_counts: Counter[int] = Counter()
    with gzip.open(bed_gz, "rt", encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            if not raw.strip():
                continue
            row_count += 1
            if row_count % 1000000 == 0:
                print(f"TREXPLORER_SCAN_PROGRESS\t{row_count}/{expected_rows}", flush=True)
            parts = raw.rstrip("\r\n").split("\t")
            field_counts[len(parts)] += 1
            if len(parts) < 3:
                malformed += 1
                continue
            try:
                chrom, start, end = parts[0], int(parts[1]), int(parts[2])
            except ValueError:
                malformed += 1
                continue
            if start < 0 or end <= start:
                malformed += 1
                continue
            qids: set[str] = set()
            for b in bins_for(start, end, bin_bp):
                qids.update(qbins.get((chrom, b), []))
            if not qids:
                continue
            source_id = parts[idx_id] if idx_id is not None and idx_id < len(parts) else f"{chrom}:{start}-{end}"
            motif = parts[idx_canon] if idx_canon is not None and idx_canon < len(parts) else ""
            ref_motif = parts[idx_ref] if idx_ref is not None and idx_ref < len(parts) else ""
            if not motif:
                motif = ref_motif
            rec = SourceRec(
                chrom=chrom,
                start=start,
                end=end,
                source_id=source_id,
                motif=motif,
                reference_motif=ref_motif,
                motif_size=parts[idx_msize] if idx_msize is not None and idx_msize < len(parts) else ".",
                purity=parts[idx_purity] if idx_purity is not None and idx_purity < len(parts) else ".",
                source_catalogs=parts[idx_source] if idx_source is not None and idx_source < len(parts) else ".",
                hprc_histogram=parts[idx_hprc] if idx_hprc is not None and idx_hprc < len(parts) else ".",
            )
            for qid in qids:
                qc, qs, qe = qcoords[qid]
                if interval_distance(qs, qe, start, end) <= nearby_bp:
                    candidates[qid].append(rec)

    print(f"TREXPLORER_SCAN_DONE\trows={row_count}\tquery_loci_with_candidates={len(candidates)}", flush=True)
    if row_count != expected_rows:
        raise ContractError(f"TRExplorer row mismatch expected={expected_rows} observed={row_count}")
    if malformed:
        raise ContractError(f"TRExplorer malformed rows: {malformed}")

    schema = {
        "autosql_fields": ";".join(fields),
        "field_count_distribution": ";".join(f"{k}={v}" for k, v in sorted(field_counts.items())),
        "id_field": fields[idx_id] if idx_id is not None else ".",
        "canonical_motif_field": fields[idx_canon] if idx_canon is not None else ".",
        "reference_motif_field": fields[idx_ref] if idx_ref is not None else ".",
        "motif_size_field": fields[idx_msize] if idx_msize is not None else ".",
        "purity_field": fields[idx_purity] if idx_purity is not None else ".",
        "source_field": fields[idx_source] if idx_source is not None else ".",
        "hprc_histogram_field": fields[idx_hprc] if idx_hprc is not None else ".",
        "motif_schema_status": "PASS" if idx_canon is not None or idx_ref is not None else "HOLD_NO_MOTIF_FIELD",
    }
    return candidates, schema, fields


COORD_RE = re.compile(r"(?P<chrom>(?:chr)?(?:[0-9]+|X|Y|M|MT))[:_-](?P<start>[0-9]+)[-_](?P<end>[0-9]+)", re.I)


def normalize_chrom(chrom: str) -> str:
    chrom = chrom.strip()
    if not chrom.lower().startswith("chr"):
        chrom = "chr" + chrom
    if chrom.lower() == "chrmt":
        chrom = "chrM"
    return chrom


def candidate_intervals(row: list[str], fields: list[str]) -> list[tuple[str, int, int, str]]:
    out: list[tuple[str, int, int, str]] = []
    norm = [norm_name(x) for x in fields]
    chrom_i = next((i for i, x in enumerate(norm) if x in {"chrom", "chr", "chromosome"} or x.endswith("chromosome")), None)
    start_i = next((i for i, x in enumerate(norm) if x in {"start", "chromstart", "begin", "pos", "position"} or x.endswith("start") or x.endswith("startposition")), None)
    end_i = next((i for i, x in enumerate(norm) if x in {"end", "chromend", "stop"} or x.endswith("end") or x.endswith("endposition")), None)
    if chrom_i is not None and start_i is not None and end_i is not None and max(chrom_i, start_i, end_i) < len(row):
        chrom = normalize_chrom(row[chrom_i])
        try:
            s, e = int(float(row[start_i])), int(float(row[end_i]))
            if e > s >= 0:
                out.append((chrom, s, e, "SEPARATE_0_BASED_HALF_OPEN"))
                if s > 0:
                    out.append((chrom, s - 1, e, "SEPARATE_1_BASED_INCLUSIVE"))
        except ValueError:
            pass
    for value in row:
        m = COORD_RE.search(value)
        if not m:
            continue
        chrom = normalize_chrom(m.group("chrom"))
        s, e = int(m.group("start")), int(m.group("end"))
        if e > s >= 0:
            out.append((chrom, s, e, "COMPOSITE_0_BASED_HALF_OPEN"))
            if s > 0:
                out.append((chrom, s - 1, e, "COMPOSITE_1_BASED_INCLUSIVE"))
    # preserve order and remove duplicates
    seen = set()
    unique = []
    for item in out:
        key = item[:3]
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def scan_population_table(path: Path, coordinate_map: Mapping[tuple[str, int, int], set[str]]) -> tuple[set[str], dict[str, object]]:
    matched: set[str] = set()
    methods: Counter[str] = Counter()
    rows = 0
    parseable = 0
    with open_text(path) as handle:
        reader = csv.reader(handle, delimiter="\t")
        try:
            fields = next(reader)
        except StopIteration:
            return matched, {"file": path.name, "rows": 0, "schema_status": "EMPTY"}
        fields = [x.strip().lstrip("#") for x in fields]
        for row in reader:
            if not row:
                continue
            rows += 1
            if rows % 1000000 == 0:
                print(f"POPULATION_TABLE_PROGRESS\t{path.name}\trows={rows}", flush=True)
            candidates = candidate_intervals(row, fields)
            if candidates:
                parseable += 1
            row_matches: set[str] = set()
            for chrom, start, end, method in candidates:
                qids = coordinate_map.get((chrom, start, end))
                if qids:
                    row_matches.update(qids)
                    methods[method] += 1
            matched.update(row_matches)
    normalized = [norm_name(x) for x in fields]
    percentile_fields = [f for f, n in zip(fields, normalized) if re.search(r"(^p(?:ct|ercentile)?[0-9]+$)|(^[0-9]+(?:\.[0-9]+)?percentile$)", n)]
    stat_fields = [f for f, n in zip(fields, normalized) if any(token in n for token in ("min", "max", "median", "mean", "mode", "mad", "std", "sd", "percentile"))]
    print(f"POPULATION_TABLE_DONE\t{path.name}\trows={rows}\tmatched_query_loci={len(matched)}", flush=True)
    schema = {
        "file": path.name,
        "rows": rows,
        "columns": len(fields),
        "header": "|".join(fields),
        "coordinate_parseable_rows": parseable,
        "coordinate_parseable_fraction": f"{parseable / rows:.9f}" if rows else "0.000000000",
        "matched_query_loci": len(matched),
        "coordinate_match_methods": ";".join(f"{k}={v}" for k, v in sorted(methods.items())) or ".",
        "percentile_fields": ";".join(percentile_fields) or ".",
        "statistic_fields": ";".join(stat_fields) or ".",
        "schema_status": "PASS" if parseable > 0 else "HOLD_COORDINATE_PARSE_FAILED",
    }
    return matched, schema


def classify_trex(query: dict[str, str], candidates: list[SourceRec], min_ro: float) -> tuple[dict[str, object], list[dict[str, object]]]:
    qstart = int(query["start_0based"])
    qend = int(query["end_0based_exclusive"])
    qspan = qend - qstart
    qmotif = query["canonical_query_motif"]
    ranked = []
    for rec in candidates:
        ov = overlap_bp(qstart, qend, rec.start, rec.end)
        cspan = rec.end - rec.start
        qro = ov / qspan if qspan else 0.0
        cro = ov / cspan if cspan else 0.0
        relation = motif_relation(qmotif, rec.motif or rec.reference_motif)
        exact = rec.start == qstart and rec.end == qend
        phase = False
        motif_len = len(clean_motif(qmotif))
        if motif_len:
            phase = ((qstart - rec.start) % motif_len == 0 and (qend - rec.end) % motif_len == 0)
        ranked.append((
            0 if exact else 1 if ov > 0 else 2,
            0 if relation == "STRICT_DIHEDRAL_EQUIVALENT" else 1 if relation == "PRIMITIVE_DIHEDRAL_EQUIVALENT" else 2,
            -(min(qro, cro)),
            abs(qstart - rec.start) + abs(qend - rec.end),
            rec.source_id,
            rec,
            ov,
            qro,
            cro,
            relation,
            phase,
        ))
    ranked.sort(key=lambda x: x[:5])
    details: list[dict[str, object]] = []
    for rank, item in enumerate(ranked, 1):
        rec, ov, qro, cro, relation, phase = item[5:]
        details.append({
            "reference_query_id": query["reference_query_id"],
            "candidate_rank": rank,
            "trexplorer_id": rec.source_id,
            "trexplorer_chrom": rec.chrom,
            "trexplorer_start_0based": rec.start,
            "trexplorer_end_0based_exclusive": rec.end,
            "trexplorer_motif": rec.motif or ".",
            "trexplorer_reference_motif": rec.reference_motif or ".",
            "motif_relation": relation,
            "overlap_bp": ov,
            "query_reciprocal_overlap": f"{qro:.9f}",
            "source_reciprocal_overlap": f"{cro:.9f}",
            "phase_compatible": str(phase).lower(),
            "coordinate_relation": "EXACT" if rec.start == qstart and rec.end == qend else "OVERLAP" if ov else "NEARBY",
            "purity": rec.purity,
            "source_catalogs": rec.source_catalogs,
            "hprc_histogram_available": str(rec.hprc_histogram not in {"", ".", "NA", "na"}).lower(),
        })
    if not ranked:
        return {
            "trexplorer_crosswalk_class": "NO_TREXPLORER_WITHIN_100BP",
            "trexplorer_safe_equivalent": False,
        }, details
    best = ranked[0]
    rec, ov, qro, cro, relation, phase = best[5:]
    exact = rec.start == qstart and rec.end == qend
    overlaps = [x for x in ranked if x[6] > 0]
    exacts = [x for x in ranked if x[5].start == qstart and x[5].end == qend]
    if exact and len(exacts) > 1:
        cls = "EXACT_COORDINATE_MULTIPLE_CANDIDATES"
    elif exact:
        cls = "EXACT_COORDINATE_STRICT_MOTIF" if relation == "STRICT_DIHEDRAL_EQUIVALENT" else "EXACT_COORDINATE_PRIMITIVE_MOTIF" if relation == "PRIMITIVE_DIHEDRAL_EQUIVALENT" else "EXACT_COORDINATE_MOTIF_MISMATCH_OR_UNAVAILABLE"
    elif len(overlaps) == 1:
        if relation == "STRICT_DIHEDRAL_EQUIVALENT" and phase and min(qro, cro) >= min_ro:
            cls = "OVERLAP_UNIQUE_SAFE_EQUIVALENT_PROVISIONAL"
        elif relation == "STRICT_DIHEDRAL_EQUIVALENT":
            cls = "OVERLAP_UNIQUE_STRICT_MOTIF_REVIEW"
        elif relation == "PRIMITIVE_DIHEDRAL_EQUIVALENT":
            cls = "OVERLAP_UNIQUE_PRIMITIVE_MOTIF_REVIEW"
        else:
            cls = "OVERLAP_UNIQUE_MOTIF_MISMATCH_OR_UNAVAILABLE"
    elif len(overlaps) > 1:
        cls = "OVERLAP_MULTIPLE_CANDIDATES"
    else:
        cls = "NEARBY_NONOVERLAP_CANDIDATE"
    safe = cls in {"EXACT_COORDINATE_STRICT_MOTIF", "OVERLAP_UNIQUE_SAFE_EQUIVALENT_PROVISIONAL"}
    return {
        "trexplorer_crosswalk_class": cls,
        "trexplorer_safe_equivalent": safe,
        "trexplorer_best_id": rec.source_id,
        "trexplorer_best_chrom": rec.chrom,
        "trexplorer_best_start_0based": rec.start,
        "trexplorer_best_end_0based_exclusive": rec.end,
        "trexplorer_best_motif": rec.motif or ".",
        "trexplorer_best_reference_motif": rec.reference_motif or ".",
        "trexplorer_best_motif_relation": relation,
        "trexplorer_best_overlap_bp": ov,
        "trexplorer_best_query_reciprocal_overlap": f"{qro:.9f}",
        "trexplorer_best_source_reciprocal_overlap": f"{cro:.9f}",
        "trexplorer_best_phase_compatible": str(phase).lower(),
        "trexplorer_best_purity": rec.purity,
        "trexplorer_best_source_catalogs": rec.source_catalogs,
        "hprc256_histogram_available": rec.hprc_histogram not in {"", ".", "NA", "na"},
        "trexplorer_exact_candidate_count": len(exacts),
        "trexplorer_overlap_candidate_count": len(overlaps),
        "trexplorer_total_candidates_within_100bp": len(ranked),
    }, details


def summarize_by(rows: list[dict[str, object]], field: str, flags: list[str], denominator: int) -> list[dict[str, object]]:
    groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        groups[str(row[field])].append(row)
    out = []
    for key, group in sorted(groups.items()):
        record: dict[str, object] = {field: key, "locus_denominator": len(group), "global_denominator": denominator}
        for flag in flags:
            count = sum(bool(r.get(flag)) for r in group)
            record[f"{flag}_loci"] = count
            record[f"{flag}_fraction"] = f"{count / len(group):.9f}" if group else "0.000000000"
        out.append(record)
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--queries", type=Path, required=True)
    p.add_argument("--repeatcatalogs", type=Path, required=True)
    p.add_argument("--trex-bed-gz", type=Path, required=True)
    p.add_argument("--trex-autosql", type=Path, required=True)
    p.add_argument("--aou-files", type=Path, required=True)
    p.add_argument("--vienna-summary", type=Path, required=True)
    p.add_argument("--out-root", type=Path, required=True)
    p.add_argument("--qc-root", type=Path, required=True)
    p.add_argument("--expected-query-loci", type=int, required=True)
    p.add_argument("--expected-trex-rows", type=int, required=True)
    p.add_argument("--nearby-bp", type=int, required=True)
    p.add_argument("--index-bin-bp", type=int, required=True)
    p.add_argument("--min-reciprocal-overlap", type=float, required=True)
    p.add_argument("--script-sha", required=True)
    p.add_argument("--query-sha", required=True)
    p.add_argument("--source-manifest-sha", required=True)
    args = p.parse_args()

    for sub in ("tables", "summary", "schema", "contracts", "provenance"):
        (args.out_root / sub).mkdir(parents=True, exist_ok=True)
    args.qc_root.mkdir(parents=True, exist_ok=True)

    qfields, queries = read_tsv(args.queries)
    required = {"reference_query_id", "representative_locus_id", "reference_build", "chrom_with_prefix", "start_0based", "end_0based_exclusive", "motif_length_bp", "canonical_query_motif", "source_event_count", "unique_read_count", "support_bin", "observed_rna_repeat_bp_median", "observed_rna_repeat_bp_max"}
    missing = required - set(qfields)
    if missing:
        raise ContractError(f"query fields missing: {sorted(missing)}")
    if len(queries) != args.expected_query_loci:
        raise ContractError(f"query count mismatch: {len(queries)}")
    if any(q["reference_build"] != "GRCh38" for q in queries):
        raise ContractError("non-GRCh38 query")

    _, rc_rows = read_tsv(args.repeatcatalogs)
    rc_by = {r["reference_query_id"]: r["crosswalk_tier"] for r in rc_rows}
    if set(rc_by) != {q["reference_query_id"] for q in queries}:
        raise ContractError("RepeatCatalogs/query ID mismatch")

    print("STAGE6AA_PHASE\tTRExplorer_crosswalk_scan", flush=True)
    trex_candidates, trex_schema, trex_fields = parse_trexplorer(args.trex_bed_gz, args.trex_autosql, queries, args.nearby_bp, args.index_bin_bp, args.expected_trex_rows)
    all_rows: list[dict[str, object]] = []
    candidate_rows: list[dict[str, object]] = []
    coordinate_map: dict[tuple[str, int, int], set[str]] = defaultdict(set)
    query_by_id = {q["reference_query_id"]: q for q in queries}

    for q in sorted(queries, key=lambda x: x["reference_query_id"]):
        qid = q["reference_query_id"]
        result, details = classify_trex(q, trex_candidates.get(qid, []), args.min_reciprocal_overlap)
        candidate_rows.extend(details)
        row: dict[str, object] = {
            "reference_query_id": qid,
            "representative_locus_id": q["representative_locus_id"],
            "reference_build": q["reference_build"],
            "chrom": q["chrom_with_prefix"],
            "query_start_0based": int(q["start_0based"]),
            "query_end_0based_exclusive": int(q["end_0based_exclusive"]),
            "query_motif": q["canonical_query_motif"],
            "motif_length_bp": q["motif_length_bp"],
            "unique_read_count": q["unique_read_count"],
            "support_bin": q["support_bin"],
            "observed_rna_repeat_bp_median": q["observed_rna_repeat_bp_median"],
            "observed_rna_repeat_bp_max": q["observed_rna_repeat_bp_max"],
            "repeatcatalogs_crosswalk_tier": rc_by[qid],
            **result,
        }
        all_rows.append(row)
        coordinate_map[(row["chrom"], row["query_start_0based"], row["query_end_0based_exclusive"])].add(qid)
        if bool(row.get("trexplorer_safe_equivalent")):
            coordinate_map[(str(row.get("trexplorer_best_chrom")), int(row.get("trexplorer_best_start_0based")), int(row.get("trexplorer_best_end_0based_exclusive")))].add(qid)

    # Select only global TRExplorer cohort files. Ancestry-specific files remain available for a later stratum stage.
    patterns = {
        "aou_validation_allele": re.compile(r"^ValidationCohort_alleleLengthStats\.TR_Explorer_1\.0\.1\.txt\.gz$"),
        "aou_validation_lps_locus": re.compile(r"^ValidationCohort_lpsPerLocusStats\.TR_Explorer_1\.0\.1\.txt\.gz$"),
        "aou_validation_lps_motif": re.compile(r"^ValidationCohort_lpsPerMotifStats\.TR_Explorer_1\.0\.1\.txt\.gz$"),
        "aou_discovery_allele": re.compile(r"^DiscoveryCohort_alleleLengthStats\.TR_Explorer_1\.0\.1\.txt\.gz$"),
        "aou_discovery_lps_locus": re.compile(r"^DiscoveryCohort_lpsPerLocusStats\.TR_Explorer_1\.0\.1\.txt\.gz$"),
        "aou_discovery_lps_motif": re.compile(r"^DiscoveryCohort_lpsPerMotifStats\.TR_Explorer_1\.0\.1\.txt\.gz$"),
        "aou_replication_allele": re.compile(r"^ReplicationCohort_alleleLengthStats\.TRExplorer_1\.0\.1\.txt\.gz$"),
        "aou_replication_lps_locus": re.compile(r"^ReplicationCohort_lpsPerLocusStats\.TRExplorer_1\.0\.1\.txt\.gz$"),
        "aou_replication_lps_motif": re.compile(r"^ReplicationCohort_lpsPerMotifStats\.TRExplorer_1\.0\.1\.txt\.gz$"),
    }
    aou_sets: dict[str, set[str]] = {}
    schema_rows: list[dict[str, object]] = []
    files = list(args.aou_files.iterdir())
    print("STAGE6AA_PHASE\tAoU_population_table_scan", flush=True)
    for key, pattern in patterns.items():
        matches = [f for f in files if f.is_file() and pattern.match(f.name)]
        if len(matches) != 1:
            aou_sets[key] = set()
            schema_rows.append({"resource_key": key, "file": ".", "schema_status": f"HOLD_EXPECTED_ONE_FILE_OBSERVED_{len(matches)}"})
            continue
        print(f"AOU_FILE_START\t{key}\t{matches[0].name}", flush=True)
        matched, schema = scan_population_table(matches[0], coordinate_map)
        aou_sets[key] = matched
        schema_rows.append({"resource_key": key, **schema})

    print("STAGE6AA_PHASE\tVienna_ONT_summary_scan", flush=True)
    vienna_matched, vienna_schema = scan_population_table(args.vienna_summary, coordinate_map)
    schema_rows.append({"resource_key": "vienna_ont_summary", **vienna_schema})

    for row in all_rows:
        qid = str(row["reference_query_id"])
        for key, matched in aou_sets.items():
            row[f"{key}_addressable"] = qid in matched
        row["vienna_ont_addressable"] = qid in vienna_matched
        row["aou_validation_length_and_lps_addressable"] = qid in (aou_sets.get("aou_validation_allele", set()) & aou_sets.get("aou_validation_lps_locus", set()))
        row["longread_population_any_addressable"] = any([
            bool(row["aou_validation_allele_addressable"]),
            bool(row["aou_discovery_allele_addressable"]),
            bool(row["aou_replication_allele_addressable"]),
            bool(row["vienna_ont_addressable"]),
            bool(row.get("hprc256_histogram_available")),
        ])
        row["population_reference_union_with_repeatcatalogs"] = row["longread_population_any_addressable"] or row["repeatcatalogs_crosswalk_tier"] in {"EXACT_MATCH", "BIOLOGICALLY_EQUIVALENT_SAFE"}
        row["automatic_population_comparison_permission"] = "ALLOW_CONTEXT_ONLY_AFTER_STAT_FIELD_QC" if row["aou_validation_allele_addressable"] and bool(row.get("trexplorer_safe_equivalent")) else "HOLD_NO_PRIMARY_EXACT_OR_SAFE_CROSSWALK"
        row["final_ranking_permission"] = "HOLD_SAME_PROTOCOL_RNA_CONTROL_AND_COVERAGE_GATE"

    flags = [
        "trexplorer_safe_equivalent",
        "aou_validation_allele_addressable",
        "aou_validation_lps_locus_addressable",
        "aou_validation_lps_motif_addressable",
        "aou_validation_length_and_lps_addressable",
        "aou_discovery_allele_addressable",
        "aou_replication_allele_addressable",
        "vienna_ont_addressable",
        "hprc256_histogram_available",
        "longread_population_any_addressable",
        "population_reference_union_with_repeatcatalogs",
    ]
    counts = {flag: sum(bool(r.get(flag)) for r in all_rows) for flag in flags}
    exact_strict = sum(r["trexplorer_crosswalk_class"] == "EXACT_COORDINATE_STRICT_MOTIF" for r in all_rows)
    overlap_safe = sum(r["trexplorer_crosswalk_class"] == "OVERLAP_UNIQUE_SAFE_EQUIVALENT_PROVISIONAL" for r in all_rows)
    no_trex = sum(r["trexplorer_crosswalk_class"] == "NO_TREXPLORER_WITHIN_100BP" for r in all_rows)

    all_fields = list(all_rows[0])
    atomic_tsv(args.out_root / "tables/p01_locus.bulk_longread_reference_crosswalk.tsv.gz", all_fields, all_rows, gzip_output=True)
    candidate_fields = list(candidate_rows[0]) if candidate_rows else ["reference_query_id"]
    atomic_tsv(args.out_root / "tables/p01_locus.trexplorer_candidates_within_100bp.tsv.gz", candidate_fields, candidate_rows, gzip_output=True)
    schema_fields = sorted({k for row in schema_rows for k in row})
    atomic_tsv(args.out_root / "schema/population_source_schema_audit.tsv", schema_fields, schema_rows)
    atomic_tsv(args.out_root / "schema/trexplorer_schema_audit.tsv", ["metric", "value"], [{"metric": k, "value": v} for k, v in trex_schema.items()])

    coverage_rows = [
        {"metric": "all_p01_loci_denominator", "value": args.expected_query_loci},
        {"metric": "trexplorer_exact_strict_motif_loci", "value": exact_strict},
        {"metric": "trexplorer_overlap_safe_equivalent_provisional_loci", "value": overlap_safe},
        {"metric": "trexplorer_safe_equivalent_total_loci", "value": counts["trexplorer_safe_equivalent"]},
        {"metric": "trexplorer_no_interval_within_100bp_loci", "value": no_trex},
    ]
    for flag in flags:
        coverage_rows.append({"metric": f"{flag}_loci", "value": counts[flag]})
        coverage_rows.append({"metric": f"{flag}_fraction", "value": f"{counts[flag] / args.expected_query_loci:.9f}"})
    coverage_rows.extend([
        {"metric": "coverage_gate", "value": "HOLD_PENDING_STAT_FIELD_SEMANTICS_AND_SAME_PROTOCOL_RNA_CONTROLS"},
        {"metric": "final_ranking", "value": "NOT_RUN"},
        {"metric": "specialized_motif_4513", "value": "PAUSED"},
    ])
    atomic_tsv(args.out_root / "summary/population_coverage_accounting.tsv", ["metric", "value"], coverage_rows)

    strat_flags = ["trexplorer_safe_equivalent", "aou_validation_allele_addressable", "aou_validation_lps_locus_addressable", "vienna_ont_addressable", "longread_population_any_addressable", "population_reference_union_with_repeatcatalogs"]
    for field, filename in [("support_bin", "coverage_by_support_bin.tsv"), ("motif_length_bp", "coverage_by_motif_length.tsv"), ("chrom", "coverage_by_chromosome.tsv")]:
        rows = summarize_by(all_rows, field, strat_flags, args.expected_query_loci)
        atomic_tsv(args.out_root / f"summary/{filename}", list(rows[0]) if rows else [field], rows)

    class_counts = Counter(str(r["trexplorer_crosswalk_class"]) for r in all_rows)
    class_rows = [{"trexplorer_crosswalk_class": k, "locus_rows": v, "denominator": args.expected_query_loci, "fraction": f"{v / args.expected_query_loci:.9f}"} for k, v in sorted(class_counts.items())]
    atomic_tsv(args.out_root / "summary/trexplorer_crosswalk_class.distribution.tsv", ["trexplorer_crosswalk_class", "locus_rows", "denominator", "fraction"], class_rows)

    primary_schema = {r["resource_key"]: r.get("schema_status", ".") for r in schema_rows}
    qc_rows = [
        {"metric": "stage_version", "value": VERSION},
        {"metric": "all_p01_loci_denominator", "value": args.expected_query_loci},
        {"metric": "trexplorer_source_rows", "value": args.expected_trex_rows},
        {"metric": "trexplorer_motif_schema_status", "value": trex_schema["motif_schema_status"]},
        {"metric": "trexplorer_exact_strict_motif_loci", "value": exact_strict},
        {"metric": "trexplorer_overlap_safe_equivalent_provisional_loci", "value": overlap_safe},
        {"metric": "trexplorer_safe_equivalent_total_loci", "value": counts["trexplorer_safe_equivalent"]},
        {"metric": "aou_validation_allele_schema_status", "value": primary_schema.get("aou_validation_allele", ".")},
        {"metric": "aou_validation_lps_locus_schema_status", "value": primary_schema.get("aou_validation_lps_locus", ".")},
        {"metric": "aou_validation_lps_motif_schema_status", "value": primary_schema.get("aou_validation_lps_motif", ".")},
        {"metric": "aou_validation_allele_addressable_loci", "value": counts["aou_validation_allele_addressable"]},
        {"metric": "aou_validation_lps_locus_addressable_loci", "value": counts["aou_validation_lps_locus_addressable"]},
        {"metric": "aou_validation_lps_motif_addressable_loci", "value": counts["aou_validation_lps_motif_addressable"]},
        {"metric": "aou_validation_length_and_lps_addressable_loci", "value": counts["aou_validation_length_and_lps_addressable"]},
        {"metric": "aou_discovery_allele_addressable_loci", "value": counts["aou_discovery_allele_addressable"]},
        {"metric": "aou_replication_allele_addressable_loci", "value": counts["aou_replication_allele_addressable"]},
        {"metric": "vienna_ont_addressable_loci", "value": counts["vienna_ont_addressable"]},
        {"metric": "hprc256_histogram_available_loci", "value": counts["hprc256_histogram_available"]},
        {"metric": "longread_population_any_addressable_loci", "value": counts["longread_population_any_addressable"]},
        {"metric": "population_reference_union_with_repeatcatalogs_loci", "value": counts["population_reference_union_with_repeatcatalogs"]},
        {"metric": "population_reference_union_with_repeatcatalogs_fraction", "value": f"{counts['population_reference_union_with_repeatcatalogs'] / args.expected_query_loci:.9f}"},
        {"metric": "same_protocol_rna_control_available", "value": "false"},
        {"metric": "final_ranking_executed", "value": 0},
        {"metric": "specialized_motif_4513_started", "value": "false"},
        {"metric": "coverage_gate_status", "value": "HOLD_PENDING_STAT_FIELD_SEMANTICS_AND_SAME_PROTOCOL_RNA_CONTROLS"},
        {"metric": "script_sha256", "value": args.script_sha},
        {"metric": "query_sha256", "value": args.query_sha},
        {"metric": "source_manifest_sha256", "value": args.source_manifest_sha},
        {"metric": "stage6aa_bulk_longread_reference_crosswalk_coverage_status", "value": "PASS_READY_FOR_POPULATION_STAT_SEMANTICS_AND_RNA_LENGTH_COMPARISON"},
    ]
    atomic_tsv(args.qc_root / "bulk_longread_reference_crosswalk_coverage.qc.tsv", ["metric", "value"], qc_rows)

    contract_rows = [
        {"layer": "CATALOG", "resource": "TRExplorer v2", "use": "locus/boundary/motif prior", "automatic_rule": "exact strict motif or provisional safe-equivalent only"},
        {"layer": "PRIMARY_POPULATION", "resource": "AoU HiFi validation 2102", "use": "allele length and LPS distributions", "automatic_rule": "requires primary schema PASS and TRExplorer exact/safe crosswalk"},
        {"layer": "CONFIRMATION", "resource": "AoU HiFi discovery 543", "use": "high-depth confirmation", "automatic_rule": "do not pool silently"},
        {"layer": "CONFIRMATION", "resource": "AoU/1KGP ONT replication 500", "use": "cross-platform confirmation", "automatic_rule": "retain platform/caller identity"},
        {"layer": "SECONDARY", "resource": "Vienna ONT 1019", "use": "long-VNTR range and motif composition", "automatic_rule": "coordinate reconciliation required"},
        {"layer": "RNA", "resource": "RNA-TR-Scout raw read", "use": "observed tract/motif/interruptions", "automatic_rule": "catalog motif remains a prior"},
    ]
    atomic_tsv(args.out_root / "contracts/reference_use_contract.tsv", ["layer", "resource", "use", "automatic_rule"], contract_rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
PY
python -m py_compile "$PY_IMPL"
implementation_sha="$(sha256sum "$PY_IMPL" | awk '{print $1}')"

cat <<EOF
===== STAGE 6AA PREFLIGHT =====
stage version:                 $STAGE_VERSION
rnatr-scout version:           $installed_version
query loci denominator:        $EXPECTED_QUERY_LOCI
catalog/motif source:          TRExplorer v2 ($EXPECTED_TREX_ROWS loci)
primary population source:     AoU HiFi validation 2,102
confirmation sources:          AoU HiFi discovery 543; AoU/1KGP ONT 500; HPRC256
secondary source:              Vienna ONT 1,019
crosswalk:                     exact + motif-aware conservative safe-equivalent
population comparison:         coverage only; RNA-vs-percentile comparison NOT RUN
reference files:               READ ONLY
T9 access:                     NONE
final ranking:                 BLOCKED
script SHA-256:                $script_sha
implementation SHA-256:        $implementation_sha
EOF

python "$PY_IMPL" \
  --queries "$QUERIES" \
  --repeatcatalogs "$STAGE6R_ALL" \
  --trex-bed-gz "$TREX_BED_GZ" \
  --trex-autosql "$TREX_AS" \
  --aou-files "$AOU_ROOT/files" \
  --vienna-summary "$VIENNA_SUMMARY" \
  --out-root "$STAGE_OUT" \
  --qc-root "$STAGE_QC" \
  --expected-query-loci "$EXPECTED_QUERY_LOCI" \
  --expected-trex-rows "$EXPECTED_TREX_ROWS" \
  --nearby-bp "$NEARBY_BP" \
  --index-bin-bp "$INDEX_BIN_BP" \
  --min-reciprocal-overlap "$MIN_RECIPROCAL_OVERLAP" \
  --script-sha "$script_sha" \
  --query-sha "$query_sha" \
  --source-manifest-sha "$manifest_sha"

cp -f "$0" "$STAGE_OUT/provenance/$(basename "$0")"
printf 'input\tpath\tsha256\n' > "$STAGE_OUT/provenance/input_manifest.tsv"
printf 'query_package\t%s\t%s\n' "$QUERIES" "$query_sha" >> "$STAGE_OUT/provenance/input_manifest.tsv"
printf 'stage6z_manifest\t%s\t%s\n' "$STAGE6Z_MANIFEST" "$manifest_sha" >> "$STAGE_OUT/provenance/input_manifest.tsv"
printf 'trexplorer_bigbed\t%s\t%s\n' "$TREX_BB" "$(awk -F $'\t' '$2=="TRExplorer_v2_BigBed"{print $5}' "$STAGE6Z_MANIFEST")" >> "$STAGE_OUT/provenance/input_manifest.tsv"
printf 'vienna_summary\t%s\t%s\n' "$VIENNA_SUMMARY" "$(awk -F $'\t' '$2=="Vienna_ONT_v1.1_summary"{print $5}' "$STAGE6Z_MANIFEST")" >> "$STAGE_OUT/provenance/input_manifest.tsv"

ART_TMP="$STAGE_OUT/bulk_longread_reference_crosswalk_coverage.artifact_manifest.tsv"
printf 'artifact\tbytes\tsha256\tpath\n' > "$ART_TMP"
find "$STAGE_OUT" "$STAGE_QC" -type f ! -name "$(basename "$ART_TMP")" -print0 | sort -z | while IFS= read -r -d '' f; do
  printf '%s\t%s\t%s\t%s\n' "$(basename "$f")" "$(stat -c '%s' "$f")" "$(sha256sum "$f" | awk '{print $1}')" "$f" >> "$ART_TMP"
done

mkdir -p "$(dirname "$OUT_ROOT")" "$(dirname "$QC_ROOT")"
mv "$STAGE_OUT" "$OUT_ROOT"
mv "$STAGE_QC" "$QC_ROOT"
ln -sfn "$OUT_ROOT" "$LATEST_RESULT_LINK"
ln -sfn "$QC_ROOT" "$LATEST_QC_LINK"
cp -f "$0" "$SCRIPT_DEST"

# Rewrite manifest paths from temporary workspace to immutable output locations.
python - "$OUT_ROOT/bulk_longread_reference_crosswalk_coverage.artifact_manifest.tsv" "$WORK_ROOT/stage_out" "$OUT_ROOT" "$WORK_ROOT/stage_qc" "$QC_ROOT" <<'PYFIX'
from pathlib import Path
import sys
p = Path(sys.argv[1])
text = p.read_text(encoding="utf-8")
text = text.replace(sys.argv[2], sys.argv[3]).replace(sys.argv[4], sys.argv[5])
p.write_text(text, encoding="utf-8")
PYFIX

cat <<EOF
STAGE6AA_STATUS\tPASS_READY_FOR_POPULATION_STAT_SEMANTICS_AND_RNA_LENGTH_COMPARISON
ALL_P01_LOCI\t$EXPECTED_QUERY_LOCI
QC\t$FINAL_QC

===== STAGE 6AA FINAL QC =====
EOF
column -ts $'\t' "$FINAL_QC"

cat <<EOF

===== POPULATION COVERAGE ACCOUNTING =====
EOF
column -ts $'\t' "$OUT_ROOT/summary/population_coverage_accounting.tsv"

cat <<EOF

===== TREXPLORER CROSSWALK CLASS DISTRIBUTION =====
EOF
column -ts $'\t' "$OUT_ROOT/summary/trexplorer_crosswalk_class.distribution.tsv"

cat <<EOF

===== SOURCE SCHEMA AUDIT =====
EOF
column -ts $'\t' "$OUT_ROOT/schema/population_source_schema_audit.tsv"

cat <<EOF

===== OUTPUT =====
Installed script:          $SCRIPT_DEST
Result:                    $OUT_ROOT
QC:                        $FINAL_QC
All-locus crosswalk:       $OUT_ROOT/tables/p01_locus.bulk_longread_reference_crosswalk.tsv.gz
TRExplorer candidates:     $OUT_ROOT/tables/p01_locus.trexplorer_candidates_within_100bp.tsv.gz
Coverage accounting:       $OUT_ROOT/summary/population_coverage_accounting.tsv
Coverage by support bin:   $OUT_ROOT/summary/coverage_by_support_bin.tsv
Coverage by motif length:  $OUT_ROOT/summary/coverage_by_motif_length.tsv
Coverage by chromosome:    $OUT_ROOT/summary/coverage_by_chromosome.tsv
Source schema audit:       $OUT_ROOT/schema/population_source_schema_audit.tsv
Reference contract:        $OUT_ROOT/contracts/reference_use_contract.tsv
Artifact manifest:         $OUT_ROOT/bulk_longread_reference_crosswalk_coverage.artifact_manifest.tsv
Latest result link:        $LATEST_RESULT_LINK
Latest QC link:            $LATEST_QC_LINK

This stage measures crosswalk and population-reference addressability only.
It does not compare RNA lengths to P95/P99/P99.9, run final ranking,
or start specialized motif 4,513 processing.
EOF
