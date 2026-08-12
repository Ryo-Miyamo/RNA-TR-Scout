#!/usr/bin/env bash
set -euo pipefail

STAGE_VERSION="rnatr_tratlas_metadata_overlap_reconciliation_v0.1.0"
RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"
EXPECTED_PACKAGE_VERSION="0.3.2"
EXPECTED_QUERY_LOCI="11042"
EXPECTED_TRATLAS_EXACT="403"
EXPECTED_TRATLAS_C1="2880"
EXPECTED_OVERLAP_UNIQUE="2477"
EXPECTED_SOURCE_SHA256="abba37e49eba43a416ba3676bc664eced91f48b6ffbecd744cb09d455cf252bd"
RECIPROCAL_OVERLAP_THRESHOLD="0.66"
REQUEST_DELAY_SEC="${TRATLAS_REQUEST_DELAY_SEC:-0.25}"
REQUEST_TIMEOUT_SEC="${TRATLAS_REQUEST_TIMEOUT_SEC:-60}"
REQUEST_RETRIES="${TRATLAS_REQUEST_RETRIES:-5}"

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
  # shellcheck disable=SC1091
  source "$HOME/miniconda3/etc/profile.d/conda.sh"
fi

conda activate rnatr-v03
# shellcheck disable=SC1091
source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

STAGE6X_RESULT_LINK="$PROJECT_ROOT/results/11_tratlas_exact_coordinate_crosswalk/$RUN_ID/latest"
STAGE6X_QC_LINK="$PROJECT_ROOT/qc/11_tratlas_exact_coordinate_crosswalk/$RUN_ID/latest"
STAGE6X_RESULT="$(readlink -f "$STAGE6X_RESULT_LINK")"
STAGE6X_QC_ROOT="$(readlink -f "$STAGE6X_QC_LINK")"
STAGE6X_QC="$STAGE6X_QC_ROOT/tratlas_exact_coordinate_crosswalk.qc.tsv"
CROSSWALK="$STAGE6X_RESULT/tables/p01_locus.tratlas_exact_coordinate_crosswalk.tsv.gz"

CACHE_ROOT="$PROJECT_ROOT/external_reference/tratlas/live_metadata/distribution_pages"
CACHE_OBJECTS="$CACHE_ROOT/objects"
CACHE_REFS="$CACHE_ROOT/refs"
CACHE_LOCKS="$CACHE_ROOT/locks"
CACHE_LOGS="$CACHE_ROOT/acquisition_logs/$STAGE_VERSION"

OUT_BASE="$PROJECT_ROOT/results/11_tratlas_metadata_overlap_reconciliation/$RUN_ID/$STAGE_VERSION"
QC_BASE="$PROJECT_ROOT/qc/11_tratlas_metadata_overlap_reconciliation/$RUN_ID/$STAGE_VERSION"
TMP_BASE="$PROJECT_ROOT/tmp/11_tratlas_metadata_overlap_reconciliation/$RUN_ID/$STAGE_VERSION"
LATEST_RESULT_LINK="$PROJECT_ROOT/results/11_tratlas_metadata_overlap_reconciliation/$RUN_ID/latest"
LATEST_QC_LINK="$PROJECT_ROOT/qc/11_tratlas_metadata_overlap_reconciliation/$RUN_ID/latest"
SCRIPT_DEST="$PROJECT_ROOT/scripts/$(basename "$0")"

mkdir -p \
  "$CACHE_OBJECTS" "$CACHE_REFS" "$CACHE_LOCKS" "$CACHE_LOGS" \
  "$OUT_BASE" "$QC_BASE" "$TMP_BASE" "$PROJECT_ROOT/scripts"

metric() {
  local file="$1"
  local key="$2"
  awk -F $'\t' -v key="$key" \
    '$1 == key {print $2; found=1; exit} END {if (!found) print "."}' \
    "$file"
}

require_metric() {
  local file="$1"
  local key="$2"
  local expected="$3"
  local observed
  observed="$(metric "$file" "$key")"
  [[ "$observed" == "$expected" ]] || {
    echo "ERROR: $file: expected $key=$expected; observed $observed" >&2
    exit 1
  }
}

for path in "$STAGE6X_QC" "$CROSSWALK"; do
  [[ -s "$path" ]] || {
    echo "ERROR: missing or empty prerequisite: $path" >&2
    exit 1
  }
done

for tool in python gzip sha256sum stat readlink flock column; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "ERROR: required tool unavailable: $tool" >&2
    exit 1
  }
done

gzip -t "$CROSSWALK"

installed_version="$(rnatr-scout version)"
[[ "$installed_version" == "$EXPECTED_PACKAGE_VERSION" ]] || {
  echo "ERROR: expected rnatr-scout $EXPECTED_PACKAGE_VERSION; observed $installed_version" >&2
  exit 1
}

require_metric "$STAGE6X_QC" stage6x_tratlas_exact_coordinate_crosswalk_status PASS_READY_FOR_TRATLAS_METADATA_AND_API_CACHE
require_metric "$STAGE6X_QC" all_p01_loci_denominator "$EXPECTED_QUERY_LOCI"
require_metric "$STAGE6X_QC" tr_atlas_exact_coordinate_loci "$EXPECTED_TRATLAS_EXACT"
require_metric "$STAGE6X_QC" c1_tratlas_unique_addressable_candidate_loci "$EXPECTED_TRATLAS_C1"
require_metric "$STAGE6X_QC" tr_atlas_overlap_unique_candidate_loci "$EXPECTED_OVERLAP_UNIQUE"
require_metric "$STAGE6X_QC" source_bigbed_sha256 "$EXPECTED_SOURCE_SHA256"

script_sha256="$(sha256sum "$0" | awk '{print $1}')"
crosswalk_sha256="$(sha256sum "$CROSSWALK" | awk '{print $1}')"
stage6x_qc_sha256="$(sha256sum "$STAGE6X_QC" | awk '{print $1}')"

cat <<EOF
===== STAGE 6Y PREFLIGHT =====
stage version:                  $STAGE_VERSION
rnatr-scout version:            $installed_version
all loci denominator:           $EXPECTED_QUERY_LOCI
TR-Atlas exact loci:            $EXPECTED_TRATLAS_EXACT
TR-Atlas overlap-unique loci:   $EXPECTED_OVERLAP_UNIQUE
unique-addressable candidates:  $EXPECTED_TRATLAS_C1
metadata source:                LIVE UNVERSIONED Distribution.php pages
metadata scope:                 exact + overlap-unique candidate TR IDs only
known parser anchor:            TR137069 chr15:81650448-81650492 unit TG reference (TG)22
request delay:                  ${REQUEST_DELAY_SEC}s
request timeout:                ${REQUEST_TIMEOUT_SEC}s
request retries:                $REQUEST_RETRIES
raw response cache:             CONTENT-ADDRESSED; RESUMABLE
frequency API:                  NOT RUN
population comparison:          NOT RUN
final ranking:                  BLOCKED
specialized motif 4,513:        PAUSED
script sha256:                  $script_sha256
EOF

exec 9>"$TMP_BASE/.metadata.lock"
if ! flock -n 9; then
  echo "ERROR: another Stage 6Y process holds the lock" >&2
  exit 1
fi

WORK_ROOT="$(mktemp -d "$TMP_BASE/work.XXXXXXXX")"
cleanup() {
  rm -rf "$WORK_ROOT"
}
trap cleanup EXIT

STAGE_OUT="$WORK_ROOT/stage_out"
STAGE_QC="$WORK_ROOT/stage_qc"
mkdir -p \
  "$STAGE_OUT/tables" "$STAGE_OUT/summary" "$STAGE_OUT/contracts" \
  "$STAGE_OUT/provenance" "$STAGE_OUT/manifests" "$STAGE_QC"

PY_IMPL="$STAGE_OUT/provenance/rnatr_tratlas_metadata_overlap_reconciliation_v0.1.0.py"
cat > "$PY_IMPL" <<'PY'
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import html
import json
import math
import os
import random
import re
import tempfile
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable, Mapping

VERSION = "rnatr_tratlas_metadata_overlap_reconciliation_v0.1.0"
BASE_URL = "https://wlcb.oit.uci.edu/TRatlas/Distribution.php?index_id={tr_id}"
TR_ID_RE = re.compile(r"^TR[0-9]+$")
POSITION_RE = re.compile(r"(chr(?:[0-9]+|X|Y|M|MT))\s*:\s*([0-9,]+)\s*-\s*([0-9,]+)", re.I)
REFERENCE_RE = re.compile(r"^\(([A-Za-z]+)\)([0-9]+(?:\.[0-9]+)?)$")
ACGT_RE = re.compile(r"^[ACGT]+$")


class ContractError(RuntimeError):
    pass


class CellTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cell_depth = 0
        self.current: list[str] = []
        self.cells: list[str] = []
        self.all_text: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in {"td", "th"}:
            if self.cell_depth == 0:
                self.current = []
            self.cell_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"td", "th"} and self.cell_depth:
            self.cell_depth -= 1
            if self.cell_depth == 0:
                text = normalize_space(" ".join(self.current))
                if text:
                    self.cells.append(text)
                self.current = []

    def handle_data(self, data: str) -> None:
        text = normalize_space(data)
        if not text:
            return
        self.all_text.append(text)
        if self.cell_depth:
            self.current.append(text)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value).replace("\xa0", " ")).strip()


def open_text(path: Path):
    return gzip.open(path, "rt", encoding="utf-8", newline="") if path.suffix == ".gz" else path.open("rt", encoding="utf-8", newline="")


def read_tsv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with open_text(path) as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise ContractError(f"missing TSV header: {path}")
        return list(reader.fieldnames), list(reader)


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    os.close(fd)
    try:
        with open(temp_name, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def atomic_write_json(path: Path, payload: object) -> None:
    atomic_write_bytes(path, (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8"))


def atomic_write_tsv(path: Path, fields: list[str], rows: Iterable[Mapping[str, object]], gzip_output: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    os.close(fd)
    try:
        handle = gzip.open(temp_name, "wt", encoding="utf-8", newline="") if gzip_output else open(temp_name, "wt", encoding="utf-8", newline="")
        with handle:
            writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n", extrasaction="raise")
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field, ".") for field in fields})
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def gzip_bytes(data: bytes) -> bytes:
    return gzip.compress(data, compresslevel=9, mtime=0)


def gunzip_path(path: Path) -> bytes:
    with gzip.open(path, "rb") as handle:
        return handle.read()


def reverse_complement(seq: str) -> str:
    return seq.translate(str.maketrans("ACGT", "TGCA"))[::-1]


def primitive_root(seq: str) -> str:
    for length in range(1, len(seq) + 1):
        if len(seq) % length == 0 and seq == seq[:length] * (len(seq) // length):
            return seq[:length]
    return seq


def canonical_motif(seq: str) -> str | None:
    seq = re.sub(r"\s+", "", seq.upper())
    if not seq or not ACGT_RE.fullmatch(seq):
        return None
    candidates: list[str] = []
    for base in (seq, reverse_complement(seq)):
        candidates.extend(base[i:] + base[:i] for i in range(len(base)))
    return min(candidates)


def canonical_primitive_motif(seq: str) -> str | None:
    seq = re.sub(r"\s+", "", seq.upper())
    if not seq or not ACGT_RE.fullmatch(seq):
        return None
    return canonical_motif(primitive_root(seq))


def find_value_after_label(cells: list[str], labels: set[str]) -> str | None:
    normalized = [normalize_space(cell).rstrip(":") for cell in cells]
    label_norm = {normalize_space(label).rstrip(":").lower() for label in labels}
    for index, cell in enumerate(normalized[:-1]):
        compact = re.sub(r"\s+", " ", cell).lower()
        if compact in label_norm:
            return normalized[index + 1]
    return None


def parse_metadata(raw: bytes, expected_tr_id: str) -> dict[str, object]:
    text = raw.decode("utf-8", errors="replace")
    parser = CellTextParser()
    parser.feed(text)
    cells = parser.cells
    all_text = normalize_space(" ".join(parser.all_text))

    if "Unable to open file" in all_text:
        return {
            "metadata_parse_status": "FAIL_REMOTE_PAGE_UNAVAILABLE",
            "metadata_parse_reason": "Unable to open file",
            "metadata_tr_id": ".",
            "metadata_chrom": ".",
            "metadata_start_0based": ".",
            "metadata_end_0based_exclusive": ".",
            "metadata_tr_unit": ".",
            "metadata_reference": ".",
            "metadata_reference_unit": ".",
            "metadata_reference_copy_number": ".",
            "metadata_reference_bp": ".",
            "metadata_nearest_gene": ".",
            "metadata_genome_feature": ".",
            "metadata_cell_count": len(cells),
        }

    tr_id = find_value_after_label(cells, {"TR ID"})
    position = find_value_after_label(cells, {"Position (hg38)", "Position  (hg38)", "Position"})
    unit = find_value_after_label(cells, {"TR unit", "Repeat unit", "Unit"})
    reference = find_value_after_label(cells, {"Reference"})
    nearest_gene = find_value_after_label(cells, {"Nearest gene"})
    genome_feature = find_value_after_label(cells, {"Genome feature"})

    if tr_id is None:
        match = re.search(r"TR\s*ID\s*(TR[0-9]+)", all_text, re.I)
        tr_id = match.group(1) if match else None
    if position is None:
        match = POSITION_RE.search(all_text)
        position = match.group(0) if match else None
    if unit is None:
        match = re.search(r"TR\s*unit\s*([A-Za-z]+)", all_text, re.I)
        unit = match.group(1) if match else None
    if reference is None:
        match = re.search(r"Reference\s*(\([A-Za-z]+\)[0-9]+(?:\.[0-9]+)?)", all_text, re.I)
        reference = match.group(1) if match else None

    position_match = POSITION_RE.search(position or "")
    if position_match:
        chrom = position_match.group(1)
        start = int(position_match.group(2).replace(",", ""))
        end = int(position_match.group(3).replace(",", ""))
    else:
        chrom = None
        start = None
        end = None

    unit_raw = normalize_space(unit or "")
    unit_clean = unit_raw.upper() if re.fullmatch(r"[A-Za-z]+", unit_raw) else None
    reference_clean = normalize_space(reference or "") or None
    reference_match = REFERENCE_RE.fullmatch(reference_clean or "")
    if reference_match:
        reference_unit = reference_match.group(1).upper()
        reference_copy_number = float(reference_match.group(2))
        reference_bp = reference_copy_number * len(reference_unit)
    else:
        reference_unit = None
        reference_copy_number = None
        reference_bp = None

    missing = [
        name for name, value in (
            ("tr_id", tr_id), ("position", position_match), ("unit", unit_clean), ("reference", reference_clean)
        ) if value is None
    ]
    if missing:
        status = "FAIL_MISSING_REQUIRED_FIELDS"
        reason = ";".join(missing)
    elif tr_id != expected_tr_id:
        status = "FAIL_TR_ID_MISMATCH"
        reason = f"expected={expected_tr_id};observed={tr_id}"
    else:
        status = "PASS"
        reason = "."

    return {
        "metadata_parse_status": status,
        "metadata_parse_reason": reason,
        "metadata_tr_id": tr_id or ".",
        "metadata_chrom": chrom or ".",
        "metadata_start_0based": start if start is not None else ".",
        "metadata_end_0based_exclusive": end if end is not None else ".",
        "metadata_tr_unit": unit_clean or ".",
        "metadata_reference": reference_clean or ".",
        "metadata_reference_unit": reference_unit or ".",
        "metadata_reference_copy_number": f"{reference_copy_number:g}" if reference_copy_number is not None else ".",
        "metadata_reference_bp": f"{reference_bp:g}" if reference_bp is not None else ".",
        "metadata_nearest_gene": nearest_gene or ".",
        "metadata_genome_feature": genome_feature or ".",
        "metadata_cell_count": len(cells),
    }


def validate_cached_ref(ref_path: Path) -> dict[str, object] | None:
    if not ref_path.is_file():
        return None
    try:
        ref = json.loads(ref_path.read_text(encoding="utf-8"))
        object_path = Path(ref["object_path"])
        if not object_path.is_file():
            return None
        raw = gunzip_path(object_path)
        if sha256_bytes(raw) != ref["content_sha256"]:
            return None
        if len(raw) != int(ref["raw_bytes"]):
            return None
        return ref
    except Exception:
        return None


def fetch_one(tr_id: str, cache_objects: Path, cache_refs: Path, timeout: int, retries: int, delay: float) -> tuple[dict[str, object] | None, str | None]:
    ref_path = cache_refs / f"{tr_id}.json"
    cached = validate_cached_ref(ref_path)
    if cached is not None:
        cached = dict(cached)
        cached["cache_status"] = "REUSED_VALIDATED_CACHE"
        return cached, None

    url = BASE_URL.format(tr_id=tr_id)
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "RNA-TR-Scout/0.3.2 academic-metadata-cache",
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Encoding": "identity",
                    "Connection": "close",
                },
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
                status = int(getattr(response, "status", 200))
                headers = {key.lower(): value for key, value in response.headers.items()}
            if status != 200:
                raise RuntimeError(f"HTTP status {status}")
            if not raw:
                raise RuntimeError("empty response")
            digest = sha256_bytes(raw)
            object_path = cache_objects / digest[:2] / f"sha256_{digest}.html.gz"
            if not object_path.exists():
                atomic_write_bytes(object_path, gzip_bytes(raw))
            ref = {
                "tr_id": tr_id,
                "url": url,
                "retrieved_at_utc": utc_now(),
                "http_status": status,
                "content_sha256": digest,
                "raw_bytes": len(raw),
                "compressed_object_bytes": object_path.stat().st_size,
                "object_path": str(object_path.resolve()),
                "headers": headers,
                "attempt": attempt,
                "cache_status": "DOWNLOADED_AND_CACHED",
            }
            atomic_write_json(ref_path, {key: value for key, value in ref.items() if key != "cache_status"})
            if delay > 0:
                time.sleep(delay)
            return ref, None
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, RuntimeError) as error:
            last_error = f"{type(error).__name__}: {error}"
            retry_after = None
            if isinstance(error, urllib.error.HTTPError):
                retry_after = error.headers.get("Retry-After") if error.headers else None
                if error.code not in {408, 425, 429, 500, 502, 503, 504}:
                    break
            if attempt < retries:
                if retry_after and retry_after.isdigit():
                    sleep_for = min(120.0, float(retry_after))
                else:
                    sleep_for = min(60.0, (2 ** (attempt - 1)) + random.random())
                time.sleep(sleep_for)
    return None, last_error or "unknown fetch error"


def overlap_bp(a_start: int, a_end: int, b_start: int, b_end: int) -> int:
    return max(0, min(a_end, b_end) - max(a_start, b_start))


def classify_join(row: dict[str, str], metadata: dict[str, object], reciprocal_threshold: float) -> dict[str, object]:
    q_start = int(row["query_start_0based"])
    q_end = int(row["query_end_0based_exclusive"])
    c_start = int(row["best_candidate_start_0based"])
    c_end = int(row["best_candidate_end_0based_exclusive"])
    q_motif = row["canonical_query_motif"].upper()
    unit = str(metadata.get("metadata_tr_unit", ".")).upper()
    ref_unit = str(metadata.get("metadata_reference_unit", ".")).upper()
    page_chrom = str(metadata.get("metadata_chrom", "."))
    page_start = metadata.get("metadata_start_0based", ".")
    page_end = metadata.get("metadata_end_0based_exclusive", ".")

    q_can = canonical_motif(q_motif)
    unit_can = canonical_motif(unit)
    ref_unit_can = canonical_motif(ref_unit)
    q_primitive = canonical_primitive_motif(q_motif)
    unit_primitive = canonical_primitive_motif(unit)

    strict_equivalent = q_can is not None and unit_can is not None and len(q_motif) == len(unit) and q_can == unit_can
    primitive_equivalent = q_primitive is not None and unit_primitive is not None and q_primitive == unit_primitive
    metadata_coordinate_match = (
        metadata.get("metadata_parse_status") == "PASS"
        and page_chrom == row["chrom"]
        and page_start != "."
        and page_end != "."
        and int(page_start) == c_start
        and int(page_end) == c_end
    )
    metadata_unit_reference_match = unit_can is not None and ref_unit_can is not None and unit_can == ref_unit_can

    ref_bp_raw = metadata.get("metadata_reference_bp", ".")
    try:
        reference_span_match = math.isclose(float(ref_bp_raw), float(c_end - c_start), abs_tol=1e-9)
    except (TypeError, ValueError):
        reference_span_match = False

    motif_length = len(unit) if ACGT_RE.fullmatch(unit) else None
    if motif_length:
        start_phase_aligned = (q_start - c_start) % motif_length == 0
        end_phase_aligned = (q_end - c_end) % motif_length == 0
    else:
        start_phase_aligned = False
        end_phase_aligned = False
    phase_aligned = start_phase_aligned and end_phase_aligned

    overlap = overlap_bp(q_start, q_end, c_start, c_end)
    q_recip = overlap / (q_end - q_start)
    c_recip = overlap / (c_end - c_start)
    reciprocal_pass = q_recip >= reciprocal_threshold and c_recip >= reciprocal_threshold

    source_class = row["tr_atlas_crosswalk_class"]
    if metadata.get("metadata_parse_status") != "PASS":
        reconciliation = "METADATA_PARSE_FAILED"
        promotion = "DENY"
    elif not metadata_coordinate_match:
        reconciliation = "METADATA_BIGBED_COORDINATE_MISMATCH"
        promotion = "DENY_SOURCE_DRIFT"
    elif source_class == "EXACT_COORDINATE_TR_ID":
        if strict_equivalent and metadata_unit_reference_match and reference_span_match:
            reconciliation = "EXACT_COORDINATE_STRICT_MOTIF_REFERENCE_VALIDATED"
            promotion = "ALLOW_FREQUENCY_API_CACHE_PENDING_SCHEMA_QC"
        elif primitive_equivalent:
            reconciliation = "EXACT_COORDINATE_PRIMITIVE_MOTIF_ONLY_MANUAL"
            promotion = "DENY_MOTIF_UNIT_SEMANTICS"
        else:
            reconciliation = "EXACT_COORDINATE_MOTIF_OR_REFERENCE_MISMATCH"
            promotion = "DENY_MOTIF_MISMATCH"
    elif source_class == "OVERLAP_UNIQUE_TR_ID_CANDIDATE":
        if strict_equivalent and metadata_unit_reference_match and reference_span_match and phase_aligned and reciprocal_pass:
            reconciliation = "OVERLAP_STRICT_MOTIF_PHASE_ALIGNED_RECIPROCAL_66_PROVISIONAL"
            promotion = "ALLOW_FREQUENCY_API_CACHE_WITH_OFFSET_CALIBRATION_PENDING_SCHEMA_QC"
        elif strict_equivalent and metadata_unit_reference_match and reference_span_match and phase_aligned:
            reconciliation = "OVERLAP_STRICT_MOTIF_PHASE_ALIGNED_LOW_RECIPROCAL_MANUAL"
            promotion = "DENY_LOW_RECIPROCAL_OVERLAP"
        elif strict_equivalent and metadata_unit_reference_match and reference_span_match:
            reconciliation = "OVERLAP_STRICT_MOTIF_PHASE_MISMATCH_MANUAL"
            promotion = "DENY_PHASE_MISMATCH"
        elif primitive_equivalent:
            reconciliation = "OVERLAP_PRIMITIVE_MOTIF_ONLY_MANUAL"
            promotion = "DENY_MOTIF_UNIT_SEMANTICS"
        else:
            reconciliation = "OVERLAP_MOTIF_OR_REFERENCE_MISMATCH"
            promotion = "DENY_MOTIF_MISMATCH"
    else:
        reconciliation = "UNEXPECTED_SOURCE_CLASS"
        promotion = "DENY"

    bp_offset_tratlas_to_query = (q_end - q_start) - (c_end - c_start)
    unit_offset = bp_offset_tratlas_to_query / motif_length if motif_length else None

    return {
        "query_motif_canonical_recomputed": q_can or ".",
        "tratlas_unit_canonical": unit_can or ".",
        "query_primitive_motif": q_primitive or ".",
        "tratlas_primitive_motif": unit_primitive or ".",
        "strict_motif_equivalent": str(strict_equivalent).lower(),
        "primitive_motif_equivalent": str(primitive_equivalent).lower(),
        "metadata_bigbed_coordinate_match": str(metadata_coordinate_match).lower(),
        "metadata_unit_reference_match": str(metadata_unit_reference_match).lower(),
        "metadata_reference_span_match": str(reference_span_match).lower(),
        "boundary_start_phase_aligned": str(start_phase_aligned).lower(),
        "boundary_end_phase_aligned": str(end_phase_aligned).lower(),
        "boundary_phase_aligned": str(phase_aligned).lower(),
        "reciprocal_overlap_threshold": f"{reciprocal_threshold:.2f}",
        "reciprocal_overlap_pass": str(reciprocal_pass).lower(),
        "tratlas_to_query_bp_offset": bp_offset_tratlas_to_query,
        "tratlas_to_query_unit_offset": f"{unit_offset:g}" if unit_offset is not None else ".",
        "metadata_reconciliation_class": reconciliation,
        "frequency_api_cache_promotion": promotion,
        "automatic_population_comparison_permission": "DENY_PENDING_FREQUENCY_API_SCHEMA_QC_AND_OFFSET_VALIDATION",
    }


def summarize(rows: list[dict[str, object]], stratum: str) -> list[dict[str, object]]:
    groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        groups[str(row[stratum])].append(row)
    out: list[dict[str, object]] = []
    for value, members in sorted(groups.items()):
        n = len(members)
        exact_valid = sum(row["metadata_reconciliation_class"] == "EXACT_COORDINATE_STRICT_MOTIF_REFERENCE_VALIDATED" for row in members)
        provisional = sum(row["metadata_reconciliation_class"] == "OVERLAP_STRICT_MOTIF_PHASE_ALIGNED_RECIPROCAL_66_PROVISIONAL" for row in members)
        api_cache = sum(str(row["frequency_api_cache_promotion"]).startswith("ALLOW_") for row in members)
        out.append({
            stratum: value,
            "candidate_loci": n,
            "exact_metadata_validated_loci": exact_valid,
            "overlap_provisional_safe_loci": provisional,
            "frequency_api_cache_eligible_loci": api_cache,
            "frequency_api_cache_eligible_fraction": f"{api_cache / n:.9f}" if n else "0.000000000",
        })
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--crosswalk", type=Path, required=True)
    parser.add_argument("--stage6x-qc", type=Path, required=True)
    parser.add_argument("--cache-objects", type=Path, required=True)
    parser.add_argument("--cache-refs", type=Path, required=True)
    parser.add_argument("--out-root", type=Path, required=True)
    parser.add_argument("--qc-root", type=Path, required=True)
    parser.add_argument("--expected-query-loci", type=int, required=True)
    parser.add_argument("--expected-exact", type=int, required=True)
    parser.add_argument("--expected-overlap-unique", type=int, required=True)
    parser.add_argument("--expected-c1", type=int, required=True)
    parser.add_argument("--reciprocal-threshold", type=float, required=True)
    parser.add_argument("--request-delay", type=float, required=True)
    parser.add_argument("--request-timeout", type=int, required=True)
    parser.add_argument("--request-retries", type=int, required=True)
    parser.add_argument("--script-sha256", required=True)
    parser.add_argument("--implementation-sha256", required=True)
    parser.add_argument("--crosswalk-sha256", required=True)
    parser.add_argument("--stage6x-qc-sha256", required=True)
    args = parser.parse_args()

    for path in (args.cache_objects, args.cache_refs, args.out_root, args.qc_root):
        path.mkdir(parents=True, exist_ok=True)

    fields, all_crosswalk = read_tsv(args.crosswalk)
    required = {
        "reference_query_id", "representative_locus_id", "chrom", "query_start_0based",
        "query_end_0based_exclusive", "canonical_query_motif", "motif_length_bp",
        "unique_read_count", "support_bin", "best_candidate_tratlas_tr_id",
        "best_candidate_start_0based", "best_candidate_end_0based_exclusive",
        "query_reciprocal_overlap", "candidate_reciprocal_overlap",
        "start_delta_bp", "end_delta_bp", "span_delta_bp", "tr_atlas_crosswalk_class",
        "repeatcatalogs_crosswalk_tier",
    }
    missing = required - set(fields)
    if missing:
        raise ContractError(f"crosswalk missing fields: {sorted(missing)}")
    if len(all_crosswalk) != args.expected_query_loci:
        raise ContractError(f"expected {args.expected_query_loci} crosswalk rows; observed {len(all_crosswalk)}")

    selected = [
        row for row in all_crosswalk
        if row["tr_atlas_crosswalk_class"] in {"EXACT_COORDINATE_TR_ID", "OVERLAP_UNIQUE_TR_ID_CANDIDATE"}
    ]
    exact_n = sum(row["tr_atlas_crosswalk_class"] == "EXACT_COORDINATE_TR_ID" for row in selected)
    overlap_n = sum(row["tr_atlas_crosswalk_class"] == "OVERLAP_UNIQUE_TR_ID_CANDIDATE" for row in selected)
    if exact_n != args.expected_exact or overlap_n != args.expected_overlap_unique or len(selected) != args.expected_c1:
        raise ContractError(f"selected accounting mismatch exact={exact_n} overlap={overlap_n} total={len(selected)}")

    candidate_ids = sorted({row["best_candidate_tratlas_tr_id"] for row in selected})
    if any(not TR_ID_RE.fullmatch(tr_id) for tr_id in candidate_ids):
        raise ContractError("invalid TR ID among selected candidates")
    id_to_query_count = Counter(row["best_candidate_tratlas_tr_id"] for row in selected)
    required_ids = sorted(set(candidate_ids) | {"TR137069"})

    acquisition_rows: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    refs: dict[str, dict[str, object]] = {}
    downloaded = 0
    reused = 0
    for index, tr_id in enumerate(required_ids, start=1):
        ref, error = fetch_one(
            tr_id,
            args.cache_objects,
            args.cache_refs,
            args.request_timeout,
            args.request_retries,
            args.request_delay,
        )
        if ref is None:
            failures.append({"tr_id": tr_id, "url": BASE_URL.format(tr_id=tr_id), "error": error or "unknown"})
        else:
            refs[tr_id] = ref
            if ref["cache_status"] == "DOWNLOADED_AND_CACHED":
                downloaded += 1
            else:
                reused += 1
            acquisition_rows.append({
                "tr_id": tr_id,
                "url": ref["url"],
                "retrieved_at_utc": ref["retrieved_at_utc"],
                "http_status": ref["http_status"],
                "content_sha256": ref["content_sha256"],
                "raw_bytes": ref["raw_bytes"],
                "compressed_object_bytes": ref["compressed_object_bytes"],
                "object_path": ref["object_path"],
                "cache_status": ref["cache_status"],
                "query_locus_count": id_to_query_count.get(tr_id, 0),
            })
        if index % 100 == 0 or index == len(required_ids):
            print(f"METADATA_PROGRESS\t{index}/{len(required_ids)}\tdownloaded={downloaded}\treused={reused}\tfailures={len(failures)}", flush=True)

    atomic_write_tsv(
        args.out_root / "manifests" / "tratlas_distribution_metadata_acquisition.tsv",
        ["tr_id", "url", "retrieved_at_utc", "http_status", "content_sha256", "raw_bytes", "compressed_object_bytes", "object_path", "cache_status", "query_locus_count"],
        acquisition_rows,
    )
    atomic_write_tsv(
        args.out_root / "tables" / "tratlas_distribution_metadata_fetch_failures.tsv",
        ["tr_id", "url", "error"],
        failures,
    )
    if failures:
        raise ContractError(f"metadata fetch incomplete: {len(failures)} failures; rerun to resume")

    canonical_manifest_rows = [
        {
            "tr_id": row["tr_id"],
            "url": row["url"],
            "retrieved_at_utc": row["retrieved_at_utc"],
            "http_status": row["http_status"],
            "content_sha256": row["content_sha256"],
            "raw_bytes": row["raw_bytes"],
        }
        for row in sorted(acquisition_rows, key=lambda item: str(item["tr_id"]))
    ]
    canonical_bytes = (json.dumps(canonical_manifest_rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    manifest_sha = sha256_bytes(canonical_bytes)
    atomic_write_bytes(args.out_root / "manifests" / "canonical_metadata_snapshot_manifest.json", canonical_bytes)
    atomic_write_bytes(args.out_root / "manifests" / "metadata_snapshot_sha256.txt", (manifest_sha + "\n").encode("ascii"))

    parsed_by_id: dict[str, dict[str, object]] = {}
    metadata_rows: list[dict[str, object]] = []
    for tr_id in required_ids:
        ref = refs[tr_id]
        raw = gunzip_path(Path(str(ref["object_path"])))
        parsed = parse_metadata(raw, tr_id)
        parsed_by_id[tr_id] = parsed
        metadata_rows.append({
            "tr_id": tr_id,
            "url": ref["url"],
            "retrieved_at_utc": ref["retrieved_at_utc"],
            "content_sha256": ref["content_sha256"],
            **parsed,
        })

    metadata_fields = list(metadata_rows[0])
    atomic_write_tsv(args.out_root / "tables" / "tratlas_distribution_metadata.parsed.tsv.gz", metadata_fields, metadata_rows, gzip_output=True)

    anchor = parsed_by_id["TR137069"]
    anchor_status = (
        "PASS"
        if anchor.get("metadata_parse_status") == "PASS"
        and anchor.get("metadata_chrom") == "chr15"
        and anchor.get("metadata_start_0based") == 81650448
        and anchor.get("metadata_end_0based_exclusive") == 81650492
        and anchor.get("metadata_tr_unit") == "TG"
        and anchor.get("metadata_reference") == "(TG)22"
        else "FAIL"
    )
    if anchor_status != "PASS":
        raise ContractError(f"known parser anchor failed: {anchor}")

    reconciled: list[dict[str, object]] = []
    for row in selected:
        tr_id = row["best_candidate_tratlas_tr_id"]
        metadata = parsed_by_id[tr_id]
        joined = classify_join(row, metadata, args.reciprocal_threshold)
        reconciled.append({
            **row,
            "candidate_tr_id_query_multiplicity": id_to_query_count[tr_id],
            "metadata_url": refs[tr_id]["url"],
            "metadata_retrieved_at_utc": refs[tr_id]["retrieved_at_utc"],
            "metadata_content_sha256": refs[tr_id]["content_sha256"],
            **metadata,
            **joined,
            "population_coverage_denominator_loci": args.expected_query_loci,
            "final_ranking_permission": "HOLD_COVERAGE_AND_RNA_CONTROL_GATE",
        })

    reconciliation_counts = Counter(str(row["metadata_reconciliation_class"]) for row in reconciled)
    exact_validated = reconciliation_counts["EXACT_COORDINATE_STRICT_MOTIF_REFERENCE_VALIDATED"]
    overlap_provisional = reconciliation_counts["OVERLAP_STRICT_MOTIF_PHASE_ALIGNED_RECIPROCAL_66_PROVISIONAL"]
    api_eligible = exact_validated + overlap_provisional
    parse_failures = sum(row["metadata_parse_status"] != "PASS" for row in reconciled)
    source_drift = sum(row["metadata_bigbed_coordinate_match"] != "true" for row in reconciled if row["metadata_parse_status"] == "PASS")
    multiassigned_tr_ids = sum(count > 1 for count in id_to_query_count.values())
    query_rows_on_multiassigned = sum(count for count in id_to_query_count.values() if count > 1)

    rc_exact_or_safe = {
        row["reference_query_id"] for row in all_crosswalk
        if row["repeatcatalogs_crosswalk_tier"] in {"EXACT_MATCH", "BIOLOGICALLY_EQUIVALENT_SAFE"}
    }
    eligible_queries = {
        str(row["reference_query_id"]) for row in reconciled
        if str(row["frequency_api_cache_promotion"]).startswith("ALLOW_")
    }
    provisional_union = rc_exact_or_safe | eligible_queries

    all_fields = list(reconciled[0])
    atomic_write_tsv(args.out_root / "tables" / "p01_locus.tratlas_metadata_overlap_reconciliation.tsv.gz", all_fields, reconciled, gzip_output=True)
    atomic_write_tsv(
        args.out_root / "tables" / "p01_locus.tratlas_frequency_api_cache_eligible.tsv.gz",
        all_fields,
        [row for row in reconciled if str(row["frequency_api_cache_promotion"]).startswith("ALLOW_")],
        gzip_output=True,
    )
    atomic_write_tsv(
        args.out_root / "tables" / "p01_locus.tratlas_metadata_manual_review.tsv.gz",
        all_fields,
        [row for row in reconciled if not str(row["frequency_api_cache_promotion"]).startswith("ALLOW_")],
        gzip_output=True,
    )

    distribution_rows = [
        {
            "metadata_reconciliation_class": key,
            "locus_rows": count,
            "all_p01_loci_denominator": args.expected_query_loci,
            "fraction_of_all_p01_loci": f"{count / args.expected_query_loci:.9f}",
        }
        for key, count in sorted(reconciliation_counts.items())
    ]
    atomic_write_tsv(
        args.out_root / "summary" / "metadata_reconciliation_class.distribution.tsv",
        ["metadata_reconciliation_class", "locus_rows", "all_p01_loci_denominator", "fraction_of_all_p01_loci"],
        distribution_rows,
    )

    support_summary = summarize(reconciled, "support_bin")
    motif_summary = summarize(reconciled, "motif_length_bp")
    atomic_write_tsv(args.out_root / "summary" / "coverage_by_support_bin.tsv", list(support_summary[0]), support_summary)
    atomic_write_tsv(args.out_root / "summary" / "coverage_by_motif_length.tsv", list(motif_summary[0]), motif_summary)

    qc = [
        ("stage_version", VERSION),
        ("metadata_snapshot_manifest_sha256", manifest_sha),
        ("source_crosswalk_sha256", args.crosswalk_sha256),
        ("source_stage6x_qc_sha256", args.stage6x_qc_sha256),
        ("all_p01_loci_denominator", args.expected_query_loci),
        ("selected_exact_loci", exact_n),
        ("selected_overlap_unique_loci", overlap_n),
        ("selected_unique_addressable_loci", len(selected)),
        ("selected_unique_tr_ids", len(candidate_ids)),
        ("candidate_tr_ids_assigned_to_multiple_query_loci", multiassigned_tr_ids),
        ("query_loci_on_multiassigned_candidate_tr_ids", query_rows_on_multiassigned),
        ("metadata_required_tr_ids_including_anchor", len(required_ids)),
        ("metadata_downloaded_this_run", downloaded),
        ("metadata_reused_validated_cache", reused),
        ("metadata_fetch_failures", len(failures)),
        ("metadata_parse_failures_in_selected_loci", parse_failures),
        ("metadata_bigbed_coordinate_mismatch_loci", source_drift),
        ("known_anchor_status", anchor_status),
        ("exact_coordinate_strict_motif_reference_validated_loci", exact_validated),
        ("overlap_strict_motif_phase_aligned_reciprocal_66_provisional_loci", overlap_provisional),
        ("frequency_api_cache_eligible_loci", api_eligible),
        ("frequency_api_cache_eligible_fraction_of_11042", f"{api_eligible / args.expected_query_loci:.9f}"),
        ("repeatcatalogs_exact_or_safe_or_tratlas_metadata_validated_provisional_union_loci", len(provisional_union)),
        ("repeatcatalogs_exact_or_safe_or_tratlas_metadata_validated_provisional_union_fraction", f"{len(provisional_union) / args.expected_query_loci:.9f}"),
        ("theoretical_tratlas_c1_plus_repeatcatalogs_upper_bound_loci", min(args.expected_query_loci, args.expected_c1 + 1)),
        ("theoretical_tratlas_c1_plus_repeatcatalogs_upper_bound_fraction", f"{min(args.expected_query_loci, args.expected_c1 + 1) / args.expected_query_loci:.9f}"),
        ("reciprocal_overlap_threshold", f"{args.reciprocal_threshold:.2f}"),
        ("frequency_api_executed", 0),
        ("population_comparison_executed", 0),
        ("same_protocol_rna_control_available", "false"),
        ("final_ranking_executed", 0),
        ("specialized_motif_4513_started", "false"),
        ("coverage_gate_status", "HOLD_TRATLAS_ALONE_CANNOT_SOLVE_COVERAGE_AND_RNA_CONTROLS_MISSING"),
        ("promotion_to_frequency_api_cache", "PASS_ELIGIBLE_METADATA_VALIDATED_TR_IDS_ONLY" if parse_failures == 0 and source_drift == 0 else "HOLD_METADATA_QC"),
        ("stage6y_tratlas_metadata_overlap_reconciliation_status", "PASS_READY_FOR_FREQUENCY_API_CACHE" if parse_failures == 0 and source_drift == 0 else "HOLD_METADATA_QC"),
        ("script_sha256", args.script_sha256),
        ("implementation_sha256", args.implementation_sha256),
    ]
    atomic_write_tsv(args.qc_root / "tratlas_metadata_overlap_reconciliation.qc.tsv", ["metric", "value"], [{"metric": k, "value": v} for k, v in qc])
    atomic_write_bytes(args.out_root / "manifests" / "snapshot_id.txt", (f"metadata_manifest_sha256_{manifest_sha}\n").encode("ascii"))

    print(f"STAGE6Y_STATUS\t{qc[-3][1]}")
    print(f"METADATA_SNAPSHOT_SHA256\t{manifest_sha}")
    print(f"EXACT_METADATA_VALIDATED\t{exact_validated}/{args.expected_query_loci}")
    print(f"OVERLAP_PROVISIONAL_SAFE\t{overlap_provisional}/{args.expected_query_loci}")
    print(f"FREQUENCY_API_CACHE_ELIGIBLE\t{api_eligible}/{args.expected_query_loci}")
    print(f"PROVISIONAL_POPULATION_UNION\t{len(provisional_union)}/{args.expected_query_loci}")
    print("FREQUENCY_API\tNOT_RUN")
    print("FINAL_RANKING\tNOT_RUN")


if __name__ == "__main__":
    main()
PY

python -m py_compile "$PY_IMPL"
implementation_sha256="$(sha256sum "$PY_IMPL" | awk '{print $1}')"

set +e
python "$PY_IMPL" \
  --crosswalk "$CROSSWALK" \
  --stage6x-qc "$STAGE6X_QC" \
  --cache-objects "$CACHE_OBJECTS" \
  --cache-refs "$CACHE_REFS" \
  --out-root "$STAGE_OUT" \
  --qc-root "$STAGE_QC" \
  --expected-query-loci "$EXPECTED_QUERY_LOCI" \
  --expected-exact "$EXPECTED_TRATLAS_EXACT" \
  --expected-overlap-unique "$EXPECTED_OVERLAP_UNIQUE" \
  --expected-c1 "$EXPECTED_TRATLAS_C1" \
  --reciprocal-threshold "$RECIPROCAL_OVERLAP_THRESHOLD" \
  --request-delay "$REQUEST_DELAY_SEC" \
  --request-timeout "$REQUEST_TIMEOUT_SEC" \
  --request-retries "$REQUEST_RETRIES" \
  --script-sha256 "$script_sha256" \
  --implementation-sha256 "$implementation_sha256" \
  --crosswalk-sha256 "$crosswalk_sha256" \
  --stage6x-qc-sha256 "$stage6x_qc_sha256"
python_status=$?
set -e

if [[ "$python_status" -ne 0 ]]; then
  partial_log="$CACHE_LOGS/$(date -u +%Y%m%dT%H%M%SZ)_partial"
  mkdir -p "$partial_log"
  cp -a "$STAGE_OUT/." "$partial_log/" 2>/dev/null || true
  echo "ERROR: Stage 6Y did not complete. The content-addressed cache was preserved." >&2
  echo "Rerun the same command to resume." >&2
  echo "Partial log: $partial_log" >&2
  exit "$python_status"
fi

snapshot_id="$(tr -d '\n' < "$STAGE_OUT/manifests/snapshot_id.txt")"
[[ "$snapshot_id" =~ ^metadata_manifest_sha256_[0-9a-f]{64}$ ]] || {
  echo "ERROR: invalid snapshot ID: $snapshot_id" >&2
  exit 1
}

OUT_ROOT="$OUT_BASE/$snapshot_id"
QC_ROOT="$QC_BASE/$snapshot_id"
FINAL_QC="$QC_ROOT/tratlas_metadata_overlap_reconciliation.qc.tsv"
ARTIFACT_MANIFEST="$OUT_ROOT/tratlas_metadata_overlap_reconciliation.artifact_manifest.tsv"

if [[ -e "$OUT_ROOT" || -e "$QC_ROOT" ]]; then
  if [[ -s "$FINAL_QC" && -s "$ARTIFACT_MANIFEST" ]]; then
    echo "===== EXISTING STAGE 6Y CHECKPOINT ====="
    column -ts $'\t' "$FINAL_QC"
    echo
    echo "Result: $OUT_ROOT"
    echo "QC:     $FINAL_QC"
    exit 0
  fi
  echo "ERROR: target checkpoint exists but is incomplete: $snapshot_id" >&2
  exit 1
fi

mv "$STAGE_OUT" "$OUT_ROOT"
mv "$STAGE_QC" "$QC_ROOT"

{
  printf 'artifact\tbytes\tsha256\tpath\n'
  while IFS= read -r -d '' file; do
    rel="${file#"$OUT_ROOT/"}"
    [[ "$rel" == "tratlas_metadata_overlap_reconciliation.artifact_manifest.tsv" ]] && continue
    printf '%s\t%s\t%s\t%s\n' \
      "$rel" \
      "$(stat -c '%s' "$file")" \
      "$(sha256sum "$file" | awk '{print $1}')" \
      "$file"
  done < <(find "$OUT_ROOT" -type f -print0 | sort -z)
  while IFS= read -r -d '' file; do
    printf 'qc/%s\t%s\t%s\t%s\n' \
      "$(basename "$file")" \
      "$(stat -c '%s' "$file")" \
      "$(sha256sum "$file" | awk '{print $1}')" \
      "$file"
  done < <(find "$QC_ROOT" -type f -print0 | sort -z)
} > "$ARTIFACT_MANIFEST"

cp "$0" "$SCRIPT_DEST"
ln -sfn "$OUT_ROOT" "$LATEST_RESULT_LINK"
ln -sfn "$QC_ROOT" "$LATEST_QC_LINK"

cat <<EOF

===== STAGE 6Y FINAL QC =====
EOF
column -ts $'\t' "$FINAL_QC"

cat <<EOF

===== METADATA RECONCILIATION CLASS DISTRIBUTION =====
EOF
column -ts $'\t' "$OUT_ROOT/summary/metadata_reconciliation_class.distribution.tsv"

cat <<EOF

===== COVERAGE BY SUPPORT BIN =====
EOF
column -ts $'\t' "$OUT_ROOT/summary/coverage_by_support_bin.tsv"

cat <<EOF

===== OUTPUT =====
Installed script:          $SCRIPT_DEST
Result:                    $OUT_ROOT
QC:                        $FINAL_QC
Reconciled loci:           $OUT_ROOT/tables/p01_locus.tratlas_metadata_overlap_reconciliation.tsv.gz
API-cache eligible loci:   $OUT_ROOT/tables/p01_locus.tratlas_frequency_api_cache_eligible.tsv.gz
Manual-review loci:        $OUT_ROOT/tables/p01_locus.tratlas_metadata_manual_review.tsv.gz
Parsed metadata:           $OUT_ROOT/tables/tratlas_distribution_metadata.parsed.tsv.gz
Acquisition manifest:      $OUT_ROOT/manifests/tratlas_distribution_metadata_acquisition.tsv
Snapshot manifest:         $OUT_ROOT/manifests/canonical_metadata_snapshot_manifest.json
Artifact manifest:         $ARTIFACT_MANIFEST
Latest result link:        $LATEST_RESULT_LINK
Latest QC link:            $LATEST_QC_LINK

Stage 6Y caches and validates official TR-Atlas metadata for exact and unique-overlap candidates.
It does not fetch population-frequency API responses, perform RNA-vs-population comparisons,
start final ranking, or resume specialized motif 4,513 implementation.
EOF
