#!/usr/bin/env bash
set -euo pipefail

STAGE_VERSION="rnatr_tratlas_exact_coordinate_crosswalk_v0.1.0"
RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"
EXPECTED_PACKAGE_VERSION="0.3.2"
EXPECTED_QUERY_LOCI="11042"
EXPECTED_QUERY_EVENTS="23867"
EXPECTED_SOURCE_SHA256="abba37e49eba43a416ba3676bc664eced91f48b6ffbecd744cb09d455cf252bd"
EXPECTED_SOURCE_ROWS="913333"
EXPECTED_TR_ID_COLUMN="4"
EXPECTED_REPEATCATALOGS_EXACT="403"
EXPECTED_REPEATCATALOGS_SAFE="1"
NEARBY_BP="100"
INDEX_BIN_BP="10000"

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
  # shellcheck disable=SC1091
  source "$HOME/miniconda3/etc/profile.d/conda.sh"
fi

conda activate rnatr-v03
# shellcheck disable=SC1091
source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

QUERY_ROOT="$PROJECT_ROOT/results/11_reference_control_adapter_query_package/$RUN_ID/rnatr_reference_control_adapter_query_package_v0.1.0"
QUERY_QC="$PROJECT_ROOT/qc/11_reference_control_adapter_query_package/$RUN_ID/rnatr_reference_control_adapter_query_package_v0.1.0/reference_control_adapter_query_package.qc.tsv"
QUERIES="$QUERY_ROOT/p01_locus.reference_control_queries.tsv.gz"

STAGE6R_ROOT="$PROJECT_ROOT/results/11_repeatcatalogs_crosswalk_coverage_audit/$RUN_ID/rnatr_repeatcatalogs_crosswalk_coverage_audit_v0.1.2"
STAGE6R_QC="$PROJECT_ROOT/qc/11_repeatcatalogs_crosswalk_coverage_audit/$RUN_ID/rnatr_repeatcatalogs_crosswalk_coverage_audit_v0.1.2/repeatcatalogs_crosswalk_coverage_audit.qc.tsv"
STAGE6R_ALL="$STAGE6R_ROOT/tables/p01_locus.repeatcatalogs_crosswalk_coverage_audit.tsv.gz"

STAGE6W_RESULT_LINK="$PROJECT_ROOT/results/11_tratlas_live_bigbed_source_audit/$RUN_ID/latest"
STAGE6W_QC_LINK="$PROJECT_ROOT/qc/11_tratlas_live_bigbed_source_audit/$RUN_ID/latest"
STAGE6W_SOURCE_LINK="$PROJECT_ROOT/external_reference/tratlas/live_bigbed/latest_content_snapshot"
STAGE6W_RESULT="$(readlink -f "$STAGE6W_RESULT_LINK")"
STAGE6W_QC_ROOT="$(readlink -f "$STAGE6W_QC_LINK")"
STAGE6W_SOURCE="$(readlink -f "$STAGE6W_SOURCE_LINK")"
STAGE6W_QC="$STAGE6W_QC_ROOT/tratlas_live_bigbed_source_audit.qc.tsv"
TRATLAS_BED="$STAGE6W_RESULT/schema/hg38_version7_913341_TRs_wb.bed"
TRATLAS_BIGBED="$STAGE6W_SOURCE/hg38_version7_913341_TRs_wb.bb"
STAGE6W_MANIFEST="$STAGE6W_RESULT/tratlas_live_bigbed_source_audit.artifact_manifest.tsv"

SNAPSHOT_ID="sha256_${EXPECTED_SOURCE_SHA256}"
OUT_BASE="$PROJECT_ROOT/results/11_tratlas_exact_coordinate_crosswalk/$RUN_ID/$STAGE_VERSION"
QC_BASE="$PROJECT_ROOT/qc/11_tratlas_exact_coordinate_crosswalk/$RUN_ID/$STAGE_VERSION"
TMP_BASE="$PROJECT_ROOT/tmp/11_tratlas_exact_coordinate_crosswalk/$RUN_ID/$STAGE_VERSION"
OUT_ROOT="$OUT_BASE/$SNAPSHOT_ID"
QC_ROOT="$QC_BASE/$SNAPSHOT_ID"
FINAL_QC="$QC_ROOT/tratlas_exact_coordinate_crosswalk.qc.tsv"
ARTIFACT_MANIFEST="$OUT_ROOT/tratlas_exact_coordinate_crosswalk.artifact_manifest.tsv"
SCRIPT_DEST="$PROJECT_ROOT/scripts/$(basename "$0")"
LATEST_RESULT_LINK="$PROJECT_ROOT/results/11_tratlas_exact_coordinate_crosswalk/$RUN_ID/latest"
LATEST_QC_LINK="$PROJECT_ROOT/qc/11_tratlas_exact_coordinate_crosswalk/$RUN_ID/latest"

mkdir -p "$OUT_BASE" "$QC_BASE" "$TMP_BASE" "$PROJECT_ROOT/scripts"

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

for path in \
  "$QUERY_QC" "$QUERIES" \
  "$STAGE6R_QC" "$STAGE6R_ALL" \
  "$STAGE6W_QC" "$TRATLAS_BED" "$TRATLAS_BIGBED" "$STAGE6W_MANIFEST"
do
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

gzip -t "$QUERIES"
gzip -t "$STAGE6R_ALL"

installed_version="$(rnatr-scout version)"
[[ "$installed_version" == "$EXPECTED_PACKAGE_VERSION" ]] || {
  echo "ERROR: expected rnatr-scout $EXPECTED_PACKAGE_VERSION; observed $installed_version" >&2
  exit 1
}

require_metric "$QUERY_QC" adapter_query_package_status PASS
require_metric "$QUERY_QC" reference_query_rows "$EXPECTED_QUERY_LOCI"
require_metric "$QUERY_QC" source_event_total "$EXPECTED_QUERY_EVENTS"
require_metric "$STAGE6R_QC" stage6r_crosswalk_coverage_audit_status PASS
require_metric "$STAGE6R_QC" all_p01_loci_denominator "$EXPECTED_QUERY_LOCI"
require_metric "$STAGE6R_QC" current_exact_comparable_loci "$EXPECTED_REPEATCATALOGS_EXACT"
require_metric "$STAGE6R_QC" biologically_equivalent_safe_loci "$EXPECTED_REPEATCATALOGS_SAFE"
require_metric "$STAGE6W_QC" stage6w_tratlas_bigbed_source_audit_status PASS_READY_FOR_EXACT_CROSSWALK
require_metric "$STAGE6W_QC" source_sha256 "$EXPECTED_SOURCE_SHA256"
require_metric "$STAGE6W_QC" bigbed_bed_rows "$EXPECTED_SOURCE_ROWS"
require_metric "$STAGE6W_QC" bigbed_unique_tr_ids "$EXPECTED_SOURCE_ROWS"
require_metric "$STAGE6W_QC" bigbed_tr_id_column_index_1based "$EXPECTED_TR_ID_COLUMN"
require_metric "$STAGE6W_QC" known_anchor_status PASS_EXACT_TO_BROWSER_NUMBERS
require_metric "$STAGE6W_QC" motif_semantics_status HOLD_REQUIRES_AUTHORITATIVE_MOTIF_JOIN

observed_bigbed_sha="$(sha256sum "$TRATLAS_BIGBED" | awk '{print $1}')"
[[ "$observed_bigbed_sha" == "$EXPECTED_SOURCE_SHA256" ]] || {
  echo "ERROR: frozen BigBed SHA-256 mismatch: $observed_bigbed_sha" >&2
  exit 1
}

query_rows="$(gzip -cd "$QUERIES" | awk 'END {print (NR > 0 ? NR - 1 : 0)}')"
source_rows="$(awk 'END {print NR}' "$TRATLAS_BED")"
[[ "$query_rows" == "$EXPECTED_QUERY_LOCI" ]] || {
  echo "ERROR: expected $EXPECTED_QUERY_LOCI query rows; observed $query_rows" >&2
  exit 1
}
[[ "$source_rows" == "$EXPECTED_SOURCE_ROWS" ]] || {
  echo "ERROR: expected $EXPECTED_SOURCE_ROWS TR-Atlas rows; observed $source_rows" >&2
  exit 1
}

verify_existing_checkpoint() {
  [[ -s "$FINAL_QC" && -s "$ARTIFACT_MANIFEST" ]] || return 1
  python - "$ARTIFACT_MANIFEST" <<'PYVERIFY'
from __future__ import annotations
import csv
import hashlib
import sys
from pathlib import Path

manifest = Path(sys.argv[1])
with manifest.open("r", encoding="utf-8", newline="") as handle:
    reader = csv.DictReader(handle, delimiter="\t")
    required = {"artifact", "bytes", "sha256", "path"}
    if reader.fieldnames is None or not required.issubset(reader.fieldnames):
        raise SystemExit(1)
    for row in reader:
        path = Path(row["path"])
        if not path.is_file() or path.stat().st_size != int(row["bytes"]):
            raise SystemExit(1)
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != row["sha256"]:
            raise SystemExit(1)
PYVERIFY
}

if verify_existing_checkpoint; then
  echo "===== EXISTING HASH-VALIDATED STAGE 6X CHECKPOINT ====="
  column -ts $'\t' "$FINAL_QC"
  echo
  echo "Result: $OUT_ROOT"
  echo "QC:     $FINAL_QC"
  exit 0
fi

if [[ -e "$OUT_ROOT" || -e "$QC_ROOT" ]]; then
  echo "ERROR: existing output is not a valid immutable checkpoint" >&2
  echo "  output: $OUT_ROOT" >&2
  echo "  qc:     $QC_ROOT" >&2
  exit 1
fi

exec 9>"$TMP_BASE/.crosswalk.lock"
if ! flock -n 9; then
  echo "ERROR: another TR-Atlas exact-crosswalk process holds the lock" >&2
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
  "$STAGE_OUT/tables" "$STAGE_OUT/summary" \
  "$STAGE_OUT/contracts" "$STAGE_OUT/provenance" \
  "$STAGE_QC"

PY_IMPL="$STAGE_OUT/provenance/rnatr_tratlas_exact_coordinate_crosswalk_v0.1.0.py"
cat > "$PY_IMPL" <<'PY'
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import os
import re
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Mapping

VERSION = "rnatr_tratlas_exact_coordinate_crosswalk_v0.1.0"
TR_ID_RE = re.compile(r"^TR[0-9]+$")


class ContractError(RuntimeError):
    pass


def open_text(path: Path):
    return (
        gzip.open(path, "rt", encoding="utf-8", newline="")
        if path.suffix == ".gz"
        else path.open("rt", encoding="utf-8", newline="")
    )


def read_tsv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with open_text(path) as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise ContractError(f"missing TSV header: {path}")
        return list(reader.fieldnames), list(reader)


def atomic_write_tsv(
    path: Path,
    fields: list[str],
    rows: Iterable[Mapping[str, object]],
    *,
    gzip_output: bool = False,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    os.close(fd)
    try:
        handle = (
            gzip.open(temp_name, "wt", encoding="utf-8", newline="")
            if gzip_output
            else open(temp_name, "wt", encoding="utf-8", newline="")
        )
        with handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=fields,
                delimiter="\t",
                lineterminator="\n",
                extrasaction="raise",
            )
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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def overlap_bp(a_start: int, a_end: int, b_start: int, b_end: int) -> int:
    return max(0, min(a_end, b_end) - max(a_start, b_start))


def interval_distance(a_start: int, a_end: int, b_start: int, b_end: int) -> int:
    if overlap_bp(a_start, a_end, b_start, b_end) > 0:
        return 0
    if a_end <= b_start:
        return b_start - a_end
    return a_start - b_end


def bins_for(start: int, end: int, bin_bp: int, pad: int = 0) -> range:
    padded_start = max(0, start - pad)
    padded_end = end + pad
    return range(padded_start // bin_bp, (padded_end - 1) // bin_bp + 1)


def candidate_sort_key(
    candidate: tuple[int, int, str],
    query_start: int,
    query_end: int,
) -> tuple[object, ...]:
    start, end, tr_id = candidate
    overlap = overlap_bp(query_start, query_end, start, end)
    distance = interval_distance(query_start, query_end, start, end)
    boundary_sum = abs(query_start - start) + abs(query_end - end)
    span_delta = abs((query_end - query_start) - (end - start))
    return (-overlap, distance, boundary_sum, span_delta, tr_id)


def synthetic_regression() -> list[dict[str, object]]:
    source = [
        ("chr1", 100, 110, "TR1"),
        ("chr1", 200, 220, "TR2"),
        ("chr1", 215, 230, "TR3"),
        ("chr1", 400, 410, "TR4"),
    ]
    cases = [
        ("EXACT", "chr1", 100, 110, "EXACT_COORDINATE_TR_ID"),
        ("OVERLAP_UNIQUE", "chr1", 198, 210, "OVERLAP_UNIQUE_TR_ID_CANDIDATE"),
        ("OVERLAP_MULTIPLE", "chr1", 210, 225, "OVERLAP_MULTIPLE_TR_ID_CANDIDATES"),
        ("NEARBY_UNIQUE", "chr1", 350, 360, "NEARBY_UNIQUE_TR_ID_CANDIDATE"),
        ("NO_NEARBY", "chr2", 100, 110, "NO_TRATLAS_INTERVAL_WITHIN_WINDOW"),
    ]
    rows: list[dict[str, object]] = []
    for case_id, chrom, start, end, expected in cases:
        cands = [
            (s, e, tr)
            for c, s, e, tr in source
            if c == chrom and interval_distance(start, end, s, e) <= 100
        ]
        exact = [c for c in cands if c[0] == start and c[1] == end]
        overlaps = [c for c in cands if overlap_bp(start, end, c[0], c[1]) > 0]
        nearby = [c for c in cands if c not in overlaps]
        if exact:
            observed = "EXACT_COORDINATE_TR_ID"
        elif len(overlaps) == 1:
            observed = "OVERLAP_UNIQUE_TR_ID_CANDIDATE"
        elif len(overlaps) > 1:
            observed = "OVERLAP_MULTIPLE_TR_ID_CANDIDATES"
        elif len(nearby) == 1:
            observed = "NEARBY_UNIQUE_TR_ID_CANDIDATE"
        elif len(nearby) > 1:
            observed = "NEARBY_MULTIPLE_TR_ID_CANDIDATES"
        else:
            observed = "NO_TRATLAS_INTERVAL_WITHIN_WINDOW"
        rows.append(
            {
                "case_id": case_id,
                "observed": observed,
                "expected": expected,
                "status": "PASS" if observed == expected else "FAIL",
            }
        )
    return rows


def summarize_stratum(
    rows: list[dict[str, object]],
    stratum_field: str,
) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row[stratum_field])].append(row)
    output: list[dict[str, object]] = []
    for value, members in sorted(grouped.items(), key=lambda item: item[0]):
        denominator = len(members)
        exact = sum(row["tr_atlas_crosswalk_class"] == "EXACT_COORDINATE_TR_ID" for row in members)
        overlap_unique = sum(
            row["tr_atlas_crosswalk_class"] == "OVERLAP_UNIQUE_TR_ID_CANDIDATE"
            for row in members
        )
        rc_exact = sum(row["repeatcatalogs_crosswalk_tier"] == "EXACT_MATCH" for row in members)
        union_exact = sum(row["population_union_exact_addressable"] == "true" for row in members)
        output.append(
            {
                stratum_field: value,
                "all_p01_loci_denominator": denominator,
                "tr_atlas_exact_loci": exact,
                "tr_atlas_exact_fraction": f"{exact / denominator:.9f}",
                "tr_atlas_unique_overlap_candidate_loci": overlap_unique,
                "tr_atlas_c1_unique_addressable_candidate_loci": exact + overlap_unique,
                "repeatcatalogs_exact_loci": rc_exact,
                "repeatcatalogs_or_tratlas_exact_union_loci": union_exact,
                "repeatcatalogs_or_tratlas_exact_union_fraction": f"{union_exact / denominator:.9f}",
            }
        )
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--repeatcatalogs-audit", type=Path, required=True)
    parser.add_argument("--tratlas-bed", type=Path, required=True)
    parser.add_argument("--stage6w-qc", type=Path, required=True)
    parser.add_argument("--out-root", type=Path, required=True)
    parser.add_argument("--qc-root", type=Path, required=True)
    parser.add_argument("--expected-query-loci", type=int, required=True)
    parser.add_argument("--expected-source-rows", type=int, required=True)
    parser.add_argument("--expected-source-sha256", required=True)
    parser.add_argument("--expected-repeatcatalogs-exact", type=int, required=True)
    parser.add_argument("--expected-repeatcatalogs-safe", type=int, required=True)
    parser.add_argument("--nearby-bp", type=int, required=True)
    parser.add_argument("--index-bin-bp", type=int, required=True)
    parser.add_argument("--script-sha256", required=True)
    parser.add_argument("--implementation-sha256", required=True)
    args = parser.parse_args()

    table_root = args.out_root / "tables"
    summary_root = args.out_root / "summary"
    contract_root = args.out_root / "contracts"
    provenance_root = args.out_root / "provenance"
    for root in (
        args.out_root,
        args.qc_root,
        table_root,
        summary_root,
        contract_root,
        provenance_root,
    ):
        root.mkdir(parents=True, exist_ok=True)

    query_fields, query_rows = read_tsv(args.queries)
    required_query = {
        "reference_query_id",
        "representative_locus_id",
        "reference_build",
        "chrom_with_prefix",
        "start_0based",
        "end_0based_exclusive",
        "motif_length_bp",
        "canonical_query_motif",
        "source_event_count",
        "unique_read_count",
        "support_bin",
        "observed_rna_repeat_bp_median",
        "observed_rna_repeat_bp_max",
    }
    missing_query = required_query - set(query_fields)
    if missing_query:
        raise ContractError(f"query table missing fields: {sorted(missing_query)}")
    if len(query_rows) != args.expected_query_loci:
        raise ContractError(
            f"query row mismatch: expected={args.expected_query_loci} observed={len(query_rows)}"
        )
    if any(row["reference_build"] != "GRCh38" for row in query_rows):
        raise ContractError("query table contains non-GRCh38 rows")
    if len({row["reference_query_id"] for row in query_rows}) != len(query_rows):
        raise ContractError("duplicate reference_query_id")

    rc_fields, rc_rows = read_tsv(args.repeatcatalogs_audit)
    required_rc = {"reference_query_id", "crosswalk_tier"}
    missing_rc = required_rc - set(rc_fields)
    if missing_rc:
        raise ContractError(f"RepeatCatalogs audit missing fields: {sorted(missing_rc)}")
    rc_by_query = {row["reference_query_id"]: row["crosswalk_tier"] for row in rc_rows}
    if set(rc_by_query) != {row["reference_query_id"] for row in query_rows}:
        raise ContractError("RepeatCatalogs audit/query ID universe mismatch")
    if sum(tier == "EXACT_MATCH" for tier in rc_by_query.values()) != args.expected_repeatcatalogs_exact:
        raise ContractError("RepeatCatalogs exact count mismatch")
    if sum(tier == "BIOLOGICALLY_EQUIVALENT_SAFE" for tier in rc_by_query.values()) != args.expected_repeatcatalogs_safe:
        raise ContractError("RepeatCatalogs safe count mismatch")

    exact_map: dict[tuple[str, int, int], tuple[int, int, str]] = {}
    source_bins: dict[tuple[str, int], list[tuple[int, int, str]]] = defaultdict(list)
    source_tr_ids: set[str] = set()
    source_rows = 0
    source_chromosomes: Counter[str] = Counter()
    with args.tratlas_bed.open("r", encoding="utf-8", newline="") as handle:
        for row_number, raw in enumerate(handle, start=1):
            line = raw.rstrip("\n\r")
            if not line:
                continue
            fields = line.split("\t")
            if len(fields) != 4:
                raise ContractError(f"TR-Atlas BED row {row_number} has {len(fields)} fields")
            chrom, start_text, end_text, tr_id = fields
            try:
                start = int(start_text)
                end = int(end_text)
            except ValueError as exc:
                raise ContractError(f"invalid source coordinates at row {row_number}") from exc
            if start < 0 or end <= start or not TR_ID_RE.fullmatch(tr_id):
                raise ContractError(f"invalid TR-Atlas source row {row_number}: {line}")
            key = (chrom, start, end)
            if key in exact_map:
                raise ContractError(f"duplicate TR-Atlas interval: {key}")
            if tr_id in source_tr_ids:
                raise ContractError(f"duplicate TR-Atlas ID: {tr_id}")
            candidate = (start, end, tr_id)
            exact_map[key] = candidate
            source_tr_ids.add(tr_id)
            source_chromosomes[chrom] += 1
            source_rows += 1
            for index_bin in bins_for(start, end, args.index_bin_bp):
                source_bins[(chrom, index_bin)].append(candidate)

    if source_rows != args.expected_source_rows:
        raise ContractError(
            f"source row mismatch: expected={args.expected_source_rows} observed={source_rows}"
        )
    if len(source_tr_ids) != source_rows:
        raise ContractError("source TR-ID uniqueness mismatch")

    query_interval_counts = Counter(
        (
            row["chrom_with_prefix"],
            int(row["start_0based"]),
            int(row["end_0based_exclusive"]),
        )
        for row in query_rows
    )

    all_rows: list[dict[str, object]] = []
    candidate_rows: list[dict[str, object]] = []
    class_counts: Counter[str] = Counter()
    exact_tr_id_to_queries: dict[str, list[str]] = defaultdict(list)

    for query in sorted(query_rows, key=lambda row: row["reference_query_id"]):
        query_id = query["reference_query_id"]
        chrom = query["chrom_with_prefix"]
        start = int(query["start_0based"])
        end = int(query["end_0based_exclusive"])
        if start < 0 or end <= start:
            raise ContractError(f"invalid query interval: {query_id}")

        seen: dict[str, tuple[int, int, str]] = {}
        for index_bin in bins_for(start, end, args.index_bin_bp, args.nearby_bp):
            for candidate in source_bins.get((chrom, index_bin), []):
                c_start, c_end, tr_id = candidate
                if interval_distance(start, end, c_start, c_end) <= args.nearby_bp:
                    seen[tr_id] = candidate
        candidates = sorted(
            seen.values(),
            key=lambda candidate: candidate_sort_key(candidate, start, end),
        )
        overlaps = [
            candidate
            for candidate in candidates
            if overlap_bp(start, end, candidate[0], candidate[1]) > 0
        ]
        nearby_only = [candidate for candidate in candidates if candidate not in overlaps]
        exact_candidate = exact_map.get((chrom, start, end))

        if exact_candidate is not None:
            crosswalk_class = "EXACT_COORDINATE_TR_ID"
            best = exact_candidate
            exact_tr_id_to_queries[best[2]].append(query_id)
        elif len(overlaps) == 1:
            crosswalk_class = "OVERLAP_UNIQUE_TR_ID_CANDIDATE"
            best = overlaps[0]
        elif len(overlaps) > 1:
            crosswalk_class = "OVERLAP_MULTIPLE_TR_ID_CANDIDATES"
            best = overlaps[0]
        elif len(nearby_only) == 1:
            crosswalk_class = "NEARBY_UNIQUE_TR_ID_CANDIDATE"
            best = nearby_only[0]
        elif len(nearby_only) > 1:
            crosswalk_class = "NEARBY_MULTIPLE_TR_ID_CANDIDATES"
            best = nearby_only[0]
        else:
            crosswalk_class = "NO_TRATLAS_INTERVAL_WITHIN_WINDOW"
            best = None

        class_counts[crosswalk_class] += 1
        rc_tier = rc_by_query[query_id]
        exact_status = crosswalk_class == "EXACT_COORDINATE_TR_ID"
        c1_unique_addressable = crosswalk_class in {
            "EXACT_COORDINATE_TR_ID",
            "OVERLAP_UNIQUE_TR_ID_CANDIDATE",
        }
        rc_exact = rc_tier == "EXACT_MATCH"
        rc_safe = rc_tier == "BIOLOGICALLY_EQUIVALENT_SAFE"
        union_exact = rc_exact or exact_status
        union_exact_plus_rc_safe = rc_exact or rc_safe or exact_status

        if best is None:
            best_values: dict[str, object] = {
                "best_candidate_tratlas_tr_id": ".",
                "best_candidate_start_0based": ".",
                "best_candidate_end_0based_exclusive": ".",
                "best_candidate_span_bp": ".",
                "best_candidate_overlap_bp": 0,
                "query_reciprocal_overlap": "0.000000000",
                "candidate_reciprocal_overlap": "0.000000000",
                "nearest_distance_bp": ".",
                "start_delta_bp": ".",
                "end_delta_bp": ".",
                "span_delta_bp": ".",
            }
        else:
            c_start, c_end, tr_id = best
            overlap = overlap_bp(start, end, c_start, c_end)
            query_span = end - start
            candidate_span = c_end - c_start
            best_values = {
                "best_candidate_tratlas_tr_id": tr_id,
                "best_candidate_start_0based": c_start,
                "best_candidate_end_0based_exclusive": c_end,
                "best_candidate_span_bp": candidate_span,
                "best_candidate_overlap_bp": overlap,
                "query_reciprocal_overlap": f"{overlap / query_span:.9f}",
                "candidate_reciprocal_overlap": f"{overlap / candidate_span:.9f}",
                "nearest_distance_bp": interval_distance(start, end, c_start, c_end),
                "start_delta_bp": start - c_start,
                "end_delta_bp": end - c_end,
                "span_delta_bp": query_span - candidate_span,
            }

        row: dict[str, object] = {
            "reference_query_id": query_id,
            "representative_locus_id": query["representative_locus_id"],
            "reference_build": query["reference_build"],
            "chrom": chrom,
            "query_start_0based": start,
            "query_end_0based_exclusive": end,
            "query_span_bp": end - start,
            "canonical_query_motif": query["canonical_query_motif"],
            "motif_length_bp": query["motif_length_bp"],
            "source_event_count": query["source_event_count"],
            "unique_read_count": query["unique_read_count"],
            "support_bin": query["support_bin"],
            "observed_rna_repeat_bp_median": query["observed_rna_repeat_bp_median"],
            "observed_rna_repeat_bp_max": query["observed_rna_repeat_bp_max"],
            "query_interval_multiplicity": query_interval_counts[(chrom, start, end)],
            "candidate_count_within_window": len(candidates),
            "overlap_candidate_count": len(overlaps),
            "nearby_nonoverlap_candidate_count": len(nearby_only),
            **best_values,
            "tr_atlas_crosswalk_class": crosswalk_class,
            "tr_atlas_exact_coordinate_status": (
                "EXACT_UNIQUE_SOURCE_INTERVAL"
                if exact_status
                else "NOT_EXACT"
            ),
            "tr_atlas_motif_semantics_status": "HOLD_REQUIRES_AUTHORITATIVE_MOTIF_JOIN",
            "tr_atlas_c1_unique_addressable_candidate": str(c1_unique_addressable).lower(),
            "tr_atlas_c2_exact_tr_id_candidate": str(exact_status).lower(),
            "exact_tr_id_api_cache_permission": (
                "ALLOW_CACHE_ONLY_PENDING_MOTIF_AND_API_SCHEMA_QC"
                if exact_status
                else "DENY_NO_EXACT_TR_ID"
            ),
            "automatic_population_comparison_permission": "DENY_PENDING_AUTHORITATIVE_MOTIF_AND_API_QC",
            "repeatcatalogs_crosswalk_tier": rc_tier,
            "repeatcatalogs_exact_population_addressable": str(rc_exact).lower(),
            "population_union_exact_addressable": str(union_exact).lower(),
            "population_union_exact_plus_repeatcatalogs_safe": str(union_exact_plus_rc_safe).lower(),
            "population_coverage_denominator_loci": args.expected_query_loci,
            "final_ranking_permission": "HOLD_COVERAGE_AND_CONTROL_GATE",
        }
        all_rows.append(row)

        for rank, candidate in enumerate(candidates, start=1):
            c_start, c_end, tr_id = candidate
            overlap = overlap_bp(start, end, c_start, c_end)
            query_span = end - start
            candidate_span = c_end - c_start
            candidate_rows.append(
                {
                    "reference_query_id": query_id,
                    "representative_locus_id": query["representative_locus_id"],
                    "chrom": chrom,
                    "query_start_0based": start,
                    "query_end_0based_exclusive": end,
                    "candidate_rank": rank,
                    "tr_atlas_tr_id": tr_id,
                    "tr_atlas_start_0based": c_start,
                    "tr_atlas_end_0based_exclusive": c_end,
                    "overlap_bp": overlap,
                    "query_reciprocal_overlap": f"{overlap / query_span:.9f}",
                    "candidate_reciprocal_overlap": f"{overlap / candidate_span:.9f}",
                    "nearest_distance_bp": interval_distance(start, end, c_start, c_end),
                    "start_delta_bp": start - c_start,
                    "end_delta_bp": end - c_end,
                    "span_delta_bp": query_span - candidate_span,
                    "candidate_relation": (
                        "EXACT"
                        if start == c_start and end == c_end
                        else "OVERLAP"
                        if overlap > 0
                        else "NEARBY_NONOVERLAP"
                    ),
                    "motif_semantics_status": "NOT_AVAILABLE_IN_BIGBED",
                }
            )

    if len(all_rows) != args.expected_query_loci:
        raise ContractError("crosswalk row accounting mismatch")
    if sum(class_counts.values()) != args.expected_query_loci:
        raise ContractError("crosswalk class accounting mismatch")

    exact_count = class_counts["EXACT_COORDINATE_TR_ID"]
    if exact_count == 0:
        raise ContractError("zero exact TR-Atlas matches; coordinate contract likely failed")
    exact_unique_tr_ids = len(exact_tr_id_to_queries)
    exact_tr_ids_with_multiple_queries = sum(
        len(query_ids) > 1 for query_ids in exact_tr_id_to_queries.values()
    )
    exact_query_rows_on_multiassigned_tr_ids = sum(
        len(query_ids)
        for query_ids in exact_tr_id_to_queries.values()
        if len(query_ids) > 1
    )
    duplicate_query_interval_groups = sum(count > 1 for count in query_interval_counts.values())
    query_rows_in_duplicate_intervals = sum(
        count for count in query_interval_counts.values() if count > 1
    )

    c1_count = exact_count + class_counts["OVERLAP_UNIQUE_TR_ID_CANDIDATE"]
    rc_exact_set = {
        row["reference_query_id"]
        for row in all_rows
        if row["repeatcatalogs_crosswalk_tier"] == "EXACT_MATCH"
    }
    rc_exact_or_safe_set = {
        row["reference_query_id"]
        for row in all_rows
        if row["repeatcatalogs_crosswalk_tier"]
        in {"EXACT_MATCH", "BIOLOGICALLY_EQUIVALENT_SAFE"}
    }
    tr_exact_set = {
        row["reference_query_id"]
        for row in all_rows
        if row["tr_atlas_crosswalk_class"] == "EXACT_COORDINATE_TR_ID"
    }
    rc_tr_exact_overlap = len(rc_exact_set & tr_exact_set)
    rc_exact_or_safe_tr_exact_overlap = len(rc_exact_or_safe_set & tr_exact_set)
    union_exact_set = rc_exact_set | tr_exact_set
    union_exact_plus_safe_set = rc_exact_or_safe_set | tr_exact_set

    for row in all_rows:
        row["tr_atlas_exact_numerator_loci"] = exact_count
        row["tr_atlas_exact_fraction_of_11042"] = f"{exact_count / args.expected_query_loci:.9f}"
        row["repeatcatalogs_or_tratlas_exact_union_numerator_loci"] = len(union_exact_set)
        row["repeatcatalogs_or_tratlas_exact_union_fraction_of_11042"] = (
            f"{len(union_exact_set) / args.expected_query_loci:.9f}"
        )

    all_fields = list(all_rows[0])
    exact_rows = [
        row for row in all_rows if row["tr_atlas_crosswalk_class"] == "EXACT_COORDINATE_TR_ID"
    ]
    nonexact_rows = [
        row for row in all_rows if row["tr_atlas_crosswalk_class"] != "EXACT_COORDINATE_TR_ID"
    ]

    atomic_write_tsv(
        table_root / "p01_locus.tratlas_exact_coordinate_crosswalk.tsv.gz",
        all_fields,
        all_rows,
        gzip_output=True,
    )
    atomic_write_tsv(
        table_root / "p01_locus.tratlas_exact_matches.tsv.gz",
        all_fields,
        exact_rows,
        gzip_output=True,
    )
    atomic_write_tsv(
        table_root / "p01_locus.tratlas_nonexact_review.tsv.gz",
        all_fields,
        nonexact_rows,
        gzip_output=True,
    )
    candidate_fields = list(candidate_rows[0]) if candidate_rows else ["reference_query_id"]
    atomic_write_tsv(
        table_root / "p01_locus.tratlas_candidates_within_100bp.tsv.gz",
        candidate_fields,
        candidate_rows,
        gzip_output=True,
    )

    duplicate_interval_rows = [
        {
            "chrom": chrom,
            "start_0based": start,
            "end_0based_exclusive": end,
            "query_locus_rows": count,
            "reference_query_ids": ";".join(
                sorted(
                    row["reference_query_id"]
                    for row in all_rows
                    if row["chrom"] == chrom
                    and row["query_start_0based"] == start
                    and row["query_end_0based_exclusive"] == end
                )
            ),
            "representative_locus_ids": ";".join(
                sorted(
                    row["representative_locus_id"]
                    for row in all_rows
                    if row["chrom"] == chrom
                    and row["query_start_0based"] == start
                    and row["query_end_0based_exclusive"] == end
                )
            ),
        }
        for (chrom, start, end), count in sorted(query_interval_counts.items())
        if count > 1
    ]
    atomic_write_tsv(
        table_root / "p01_query_duplicate_intervals.tsv",
        [
            "chrom",
            "start_0based",
            "end_0based_exclusive",
            "query_locus_rows",
            "reference_query_ids",
            "representative_locus_ids",
        ],
        duplicate_interval_rows,
    )

    multiassign_rows = [
        {
            "tr_atlas_tr_id": tr_id,
            "query_locus_rows": len(query_ids),
            "reference_query_ids": ";".join(sorted(query_ids)),
        }
        for tr_id, query_ids in sorted(exact_tr_id_to_queries.items())
        if len(query_ids) > 1
    ]
    atomic_write_tsv(
        table_root / "tr_atlas_exact_tr_id_multiple_query_assignments.tsv",
        ["tr_atlas_tr_id", "query_locus_rows", "reference_query_ids"],
        multiassign_rows,
    )

    class_summary = [
        {
            "tr_atlas_crosswalk_class": crosswalk_class,
            "locus_rows": count,
            "all_p01_loci_denominator": args.expected_query_loci,
            "fraction_of_all_p01_loci": f"{count / args.expected_query_loci:.9f}",
            "population_comparison_permission": (
                "DENY_PENDING_MOTIF_AND_API_QC"
                if crosswalk_class == "EXACT_COORDINATE_TR_ID"
                else "DENY_NONEXACT"
            ),
        }
        for crosswalk_class, count in sorted(class_counts.items())
    ]
    atomic_write_tsv(
        summary_root / "tr_atlas_crosswalk_class.distribution.tsv",
        [
            "tr_atlas_crosswalk_class",
            "locus_rows",
            "all_p01_loci_denominator",
            "fraction_of_all_p01_loci",
            "population_comparison_permission",
        ],
        class_summary,
    )

    coverage_rows = [
        {"metric": "all_p01_loci_denominator", "value": args.expected_query_loci},
        {"metric": "c0_repeatcatalogs_exact_loci", "value": args.expected_repeatcatalogs_exact},
        {
            "metric": "c0_repeatcatalogs_exact_fraction",
            "value": f"{args.expected_repeatcatalogs_exact / args.expected_query_loci:.9f}",
        },
        {"metric": "c1_tratlas_unique_addressable_candidate_loci", "value": c1_count},
        {
            "metric": "c1_tratlas_unique_addressable_candidate_fraction",
            "value": f"{c1_count / args.expected_query_loci:.9f}",
        },
        {"metric": "c2_tratlas_exact_tr_id_candidate_loci", "value": exact_count},
        {
            "metric": "c2_tratlas_exact_tr_id_candidate_fraction",
            "value": f"{exact_count / args.expected_query_loci:.9f}",
        },
        {
            "metric": "repeatcatalogs_exact_and_tratlas_exact_overlap_loci",
            "value": rc_tr_exact_overlap,
        },
        {
            "metric": "repeatcatalogs_or_tratlas_exact_union_loci",
            "value": len(union_exact_set),
        },
        {
            "metric": "repeatcatalogs_or_tratlas_exact_union_fraction",
            "value": f"{len(union_exact_set) / args.expected_query_loci:.9f}",
        },
        {
            "metric": "repeatcatalogs_exact_or_safe_and_tratlas_exact_overlap_loci",
            "value": rc_exact_or_safe_tr_exact_overlap,
        },
        {
            "metric": "repeatcatalogs_exact_or_safe_or_tratlas_exact_union_loci",
            "value": len(union_exact_plus_safe_set),
        },
        {
            "metric": "repeatcatalogs_exact_or_safe_or_tratlas_exact_union_fraction",
            "value": f"{len(union_exact_plus_safe_set) / args.expected_query_loci:.9f}",
        },
        {
            "metric": "c3_tratlas_safe_equivalent_loci",
            "value": "NOT_RUN_MOTIF_SEMANTICS_UNAVAILABLE",
        },
        {
            "metric": "c4_tratlas_api_usable_loci",
            "value": "NOT_RUN_API_NOT_ACCESSED",
        },
        {
            "metric": "coverage_gate",
            "value": "HOLD_PENDING_AUTHORITATIVE_MOTIF_JOIN_API_QC_AND_RNA_CONTROLS",
        },
    ]
    atomic_write_tsv(
        summary_root / "population_coverage_accounting.tsv",
        ["metric", "value"],
        coverage_rows,
    )

    for field, filename in [
        ("chrom", "coverage_by_chromosome.tsv"),
        ("motif_length_bp", "coverage_by_motif_length.tsv"),
        ("support_bin", "coverage_by_support_bin.tsv"),
    ]:
        rows = summarize_stratum(all_rows, field)
        fields = list(rows[0]) if rows else [field]
        atomic_write_tsv(summary_root / filename, fields, rows)

    policy_rows = [
        {
            "tier": "EXACT_COORDINATE_TR_ID",
            "definition": "RNA query interval exactly equals one unique frozen TR-Atlas BigBed interval and yields one authoritative TR ID.",
            "api_cache_permission": "ALLOW_CACHE_ONLY",
            "population_comparison_permission": "DENY_PENDING_AUTHORITATIVE_MOTIF_AND_API_SCHEMA_QC",
        },
        {
            "tier": "OVERLAP_UNIQUE_TR_ID_CANDIDATE",
            "definition": "Exactly one TR-Atlas interval overlaps but boundaries differ.",
            "api_cache_permission": "DENY_AUTOMATIC",
            "population_comparison_permission": "DENY_PENDING_MOTIF_BOUNDARY_RECONCILIATION",
        },
        {
            "tier": "OVERLAP_MULTIPLE_TR_ID_CANDIDATES",
            "definition": "More than one TR-Atlas interval overlaps the RNA query.",
            "api_cache_permission": "DENY_AUTOMATIC",
            "population_comparison_permission": "DENY_AMBIGUOUS_LOCUS_ASSIGNMENT",
        },
        {
            "tier": "NEARBY_UNIQUE_OR_MULTIPLE_CANDIDATE",
            "definition": "No overlap; at least one TR-Atlas interval lies within the configured review window.",
            "api_cache_permission": "DENY_AUTOMATIC",
            "population_comparison_permission": "DENY_COORDINATE_OR_CATALOG_DESIGN_REVIEW",
        },
        {
            "tier": "NO_TRATLAS_INTERVAL_WITHIN_WINDOW",
            "definition": "No TR-Atlas interval overlaps or lies within the review window.",
            "api_cache_permission": "DENY",
            "population_comparison_permission": "DENY_NO_CATALOG_ADDRESS",
        },
    ]
    atomic_write_tsv(
        contract_root / "tr_atlas_crosswalk_promotion_policy.tsv",
        [
            "tier",
            "definition",
            "api_cache_permission",
            "population_comparison_permission",
        ],
        policy_rows,
    )

    regression_rows = synthetic_regression()
    regression_failures = sum(row["status"] != "PASS" for row in regression_rows)
    if regression_failures:
        raise ContractError(f"synthetic regression failures: {regression_failures}")
    atomic_write_tsv(
        contract_root / "synthetic_crosswalk_regression.tsv",
        ["case_id", "observed", "expected", "status"],
        regression_rows,
    )

    qc_rows = [
        {"metric": "stage_version", "value": VERSION},
        {"metric": "source_bigbed_sha256", "value": args.expected_source_sha256},
        {"metric": "source_bed_sha256", "value": sha256_file(args.tratlas_bed)},
        {"metric": "source_bigbed_rows", "value": source_rows},
        {"metric": "source_unique_tr_ids", "value": len(source_tr_ids)},
        {"metric": "source_chromosome_count", "value": len(source_chromosomes)},
        {"metric": "all_p01_loci_denominator", "value": args.expected_query_loci},
        {"metric": "query_duplicate_interval_groups", "value": duplicate_query_interval_groups},
        {"metric": "query_rows_in_duplicate_intervals", "value": query_rows_in_duplicate_intervals},
        {"metric": "tr_atlas_exact_coordinate_loci", "value": exact_count},
        {
            "metric": "tr_atlas_exact_coordinate_fraction",
            "value": f"{exact_count / args.expected_query_loci:.9f}",
        },
        {"metric": "tr_atlas_exact_unique_tr_ids", "value": exact_unique_tr_ids},
        {
            "metric": "tr_atlas_exact_tr_ids_assigned_to_multiple_query_loci",
            "value": exact_tr_ids_with_multiple_queries,
        },
        {
            "metric": "tr_atlas_exact_query_rows_on_multiassigned_tr_ids",
            "value": exact_query_rows_on_multiassigned_tr_ids,
        },
        {
            "metric": "tr_atlas_overlap_unique_candidate_loci",
            "value": class_counts["OVERLAP_UNIQUE_TR_ID_CANDIDATE"],
        },
        {
            "metric": "tr_atlas_overlap_multiple_candidate_loci",
            "value": class_counts["OVERLAP_MULTIPLE_TR_ID_CANDIDATES"],
        },
        {
            "metric": "tr_atlas_nearby_unique_candidate_loci",
            "value": class_counts["NEARBY_UNIQUE_TR_ID_CANDIDATE"],
        },
        {
            "metric": "tr_atlas_nearby_multiple_candidate_loci",
            "value": class_counts["NEARBY_MULTIPLE_TR_ID_CANDIDATES"],
        },
        {
            "metric": "tr_atlas_no_interval_within_window_loci",
            "value": class_counts["NO_TRATLAS_INTERVAL_WITHIN_WINDOW"],
        },
        {"metric": "c1_tratlas_unique_addressable_candidate_loci", "value": c1_count},
        {"metric": "c2_tratlas_exact_tr_id_candidate_loci", "value": exact_count},
        {"metric": "repeatcatalogs_exact_baseline_loci", "value": len(rc_exact_set)},
        {"metric": "repeatcatalogs_exact_or_safe_baseline_loci", "value": len(rc_exact_or_safe_set)},
        {
            "metric": "repeatcatalogs_exact_and_tratlas_exact_overlap_loci",
            "value": rc_tr_exact_overlap,
        },
        {
            "metric": "repeatcatalogs_or_tratlas_exact_union_loci",
            "value": len(union_exact_set),
        },
        {
            "metric": "repeatcatalogs_or_tratlas_exact_union_fraction",
            "value": f"{len(union_exact_set) / args.expected_query_loci:.9f}",
        },
        {
            "metric": "repeatcatalogs_exact_or_safe_or_tratlas_exact_union_loci",
            "value": len(union_exact_plus_safe_set),
        },
        {
            "metric": "repeatcatalogs_exact_or_safe_or_tratlas_exact_union_fraction",
            "value": f"{len(union_exact_plus_safe_set) / args.expected_query_loci:.9f}",
        },
        {"metric": "nearby_review_window_bp", "value": args.nearby_bp},
        {"metric": "source_index_bin_bp", "value": args.index_bin_bp},
        {"metric": "motif_semantics_status", "value": "HOLD_REQUIRES_AUTHORITATIVE_MOTIF_JOIN"},
        {"metric": "population_api_executed", "value": 0},
        {"metric": "population_comparison_executed", "value": 0},
        {"metric": "same_protocol_rna_control_available", "value": "false"},
        {"metric": "final_ranking_executed", "value": 0},
        {"metric": "specialized_motif_4513_started", "value": "false"},
        {
            "metric": "coverage_gate_status",
            "value": "HOLD_PENDING_AUTHORITATIVE_MOTIF_JOIN_API_QC_AND_RNA_CONTROLS",
        },
        {
            "metric": "promotion_to_tratlas_metadata_and_api_cache",
            "value": "PASS_EXACT_TR_IDS_ONLY",
        },
        {
            "metric": "stage6x_tratlas_exact_coordinate_crosswalk_status",
            "value": "PASS_READY_FOR_TRATLAS_METADATA_AND_API_CACHE",
        },
        {"metric": "synthetic_regression_cases", "value": len(regression_rows)},
        {"metric": "synthetic_regression_failures", "value": regression_failures},
        {"metric": "script_sha256", "value": args.script_sha256},
        {"metric": "implementation_sha256", "value": args.implementation_sha256},
        {"metric": "query_sha256", "value": sha256_file(args.queries)},
        {"metric": "repeatcatalogs_audit_sha256", "value": sha256_file(args.repeatcatalogs_audit)},
        {"metric": "stage6w_qc_sha256", "value": sha256_file(args.stage6w_qc)},
    ]
    qc_path = args.qc_root / "tratlas_exact_coordinate_crosswalk.qc.tsv"
    atomic_write_tsv(qc_path, ["metric", "value"], qc_rows)

    print("STAGE6X_STATUS\tPASS_READY_FOR_TRATLAS_METADATA_AND_API_CACHE")
    print(f"ALL_P01_LOCI\t{args.expected_query_loci}")
    print(f"TRATLAS_EXACT\t{exact_count}/{args.expected_query_loci}")
    print(f"TRATLAS_C1_UNIQUE_ADDRESSABLE\t{c1_count}/{args.expected_query_loci}")
    print(f"REPEATCATALOGS_EXACT_BASELINE\t{len(rc_exact_set)}/{args.expected_query_loci}")
    print(f"REPEATCATALOGS_OR_TRATLAS_EXACT_UNION\t{len(union_exact_set)}/{args.expected_query_loci}")
    print("MOTIF_SEMANTICS\tHOLD_REQUIRES_AUTHORITATIVE_MOTIF_JOIN")
    print("POPULATION_API\tNOT_RUN")
    print("FINAL_RANKING\tNOT_RUN")
    print(f"QC\t{qc_path}")


if __name__ == "__main__":
    main()
PY

python -m py_compile "$PY_IMPL"
SCRIPT_SHA256="$(sha256sum "$0" | awk '{print $1}')"
IMPLEMENTATION_SHA256="$(sha256sum "$PY_IMPL" | awk '{print $1}')"

RNATR_PROJECT_ROOT="$PROJECT_ROOT" \
python -m unittest discover \
  -s "$PROJECT_ROOT/tests/unit" \
  -v > "$STAGE_OUT/provenance/unit_tests.log" 2>&1

grep -qx 'OK' "$STAGE_OUT/provenance/unit_tests.log" || {
  cat "$STAGE_OUT/provenance/unit_tests.log" >&2
  echo "ERROR: project unit tests failed" >&2
  exit 1
}

echo "===== STAGE 6X PREFLIGHT ====="
echo "stage version:             $STAGE_VERSION"
echo "rnatr-scout version:       $installed_version"
echo "all loci denominator:      $EXPECTED_QUERY_LOCI"
echo "TR-Atlas source rows:      $EXPECTED_SOURCE_ROWS"
echo "TR-Atlas source SHA-256:   $EXPECTED_SOURCE_SHA256"
echo "TR-ID column:              $EXPECTED_TR_ID_COLUMN"
echo "nearby review window:      ±$NEARBY_BP bp"
echo "RepeatCatalogs baseline:   $EXPECTED_REPEATCATALOGS_EXACT/$EXPECTED_QUERY_LOCI"
echo "exact coordinate mapping:  RUN"
echo "motif equivalence:         NOT RUN; source BigBed has no motif column"
echo "population API:            NOT RUN"
echo "population comparison:     NOT RUN"
echo "final ranking:             BLOCKED"
echo "specialized motif 4,513:   PAUSED"
echo "implementation sha256:     $IMPLEMENTATION_SHA256"

python "$PY_IMPL" \
  --queries "$QUERIES" \
  --repeatcatalogs-audit "$STAGE6R_ALL" \
  --tratlas-bed "$TRATLAS_BED" \
  --stage6w-qc "$STAGE6W_QC" \
  --out-root "$STAGE_OUT" \
  --qc-root "$STAGE_QC" \
  --expected-query-loci "$EXPECTED_QUERY_LOCI" \
  --expected-source-rows "$EXPECTED_SOURCE_ROWS" \
  --expected-source-sha256 "$EXPECTED_SOURCE_SHA256" \
  --expected-repeatcatalogs-exact "$EXPECTED_REPEATCATALOGS_EXACT" \
  --expected-repeatcatalogs-safe "$EXPECTED_REPEATCATALOGS_SAFE" \
  --nearby-bp "$NEARBY_BP" \
  --index-bin-bp "$INDEX_BIN_BP" \
  --script-sha256 "$SCRIPT_SHA256" \
  --implementation-sha256 "$IMPLEMENTATION_SHA256"

cp "$0" "$STAGE_OUT/provenance/$(basename "$0")"
chmod a-w "$STAGE_OUT/provenance/$(basename "$0")"
printf 'python_path\t%s\nscript_sha256\t%s\nimplementation_sha256\t%s\nsource_bigbed_sha256\t%s\nsource_bigbed_path\t%s\nsource_bed_path\t%s\n' \
  "$(command -v python)" \
  "$SCRIPT_SHA256" \
  "$IMPLEMENTATION_SHA256" \
  "$EXPECTED_SOURCE_SHA256" \
  "$TRATLAS_BIGBED" \
  "$TRATLAS_BED" \
  > "$STAGE_OUT/provenance/tool_and_code_identity.tsv"
conda list --explicit > "$STAGE_OUT/provenance/conda_explicit_spec.txt"

printf 'artifact\tbytes\tsha256\tpath\n' > "$STAGE_OUT/tratlas_exact_coordinate_crosswalk.artifact_manifest.tsv"
add_artifact() {
  local artifact="$1"
  local path="$2"
  [[ -s "$path" ]] || return 0
  printf '%s\t%s\t%s\t%s\n' \
    "$artifact" \
    "$(stat -c '%s' "$path")" \
    "$(sha256sum "$path" | awk '{print $1}')" \
    "$path" \
    >> "$STAGE_OUT/tratlas_exact_coordinate_crosswalk.artifact_manifest.tsv"
}

while IFS= read -r -d '' path; do
  [[ "$path" == "$STAGE_OUT/tratlas_exact_coordinate_crosswalk.artifact_manifest.tsv" ]] && continue
  add_artifact "$(basename "$path")" "$path"
done < <(find "$STAGE_OUT" -type f -print0 | sort -z)
add_artifact qc "$STAGE_QC/tratlas_exact_coordinate_crosswalk.qc.tsv"

python - "$STAGE_OUT/tratlas_exact_coordinate_crosswalk.artifact_manifest.tsv" <<'PYVERIFY2'
from __future__ import annotations
import csv
import hashlib
import sys
from pathlib import Path

manifest = Path(sys.argv[1])
with manifest.open("r", encoding="utf-8", newline="") as handle:
    reader = csv.DictReader(handle, delimiter="\t")
    for row in reader:
        path = Path(row["path"])
        if not path.is_file() or path.stat().st_size != int(row["bytes"]):
            raise SystemExit(f"artifact size verification failed: {path}")
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != row["sha256"]:
            raise SystemExit(f"artifact SHA verification failed: {path}")
PYVERIFY2

mv "$STAGE_OUT" "$OUT_ROOT"
mv "$STAGE_QC" "$QC_ROOT"

python - "$ARTIFACT_MANIFEST" "$WORK_ROOT/stage_out" "$OUT_ROOT" "$WORK_ROOT/stage_qc" "$QC_ROOT" <<'PYPATHFIX'
from __future__ import annotations
import sys
from pathlib import Path

manifest = Path(sys.argv[1])
old_out, new_out, old_qc, new_qc = sys.argv[2:]
text = manifest.read_text(encoding="utf-8")
manifest.write_text(text.replace(old_out, new_out).replace(old_qc, new_qc), encoding="utf-8")
PYPATHFIX

python - "$ARTIFACT_MANIFEST" <<'PYVERIFY3'
from __future__ import annotations
import csv
import hashlib
import sys
from pathlib import Path

manifest = Path(sys.argv[1])
with manifest.open("r", encoding="utf-8", newline="") as handle:
    reader = csv.DictReader(handle, delimiter="\t")
    for row in reader:
        path = Path(row["path"])
        if not path.is_file() or path.stat().st_size != int(row["bytes"]):
            raise SystemExit(f"promoted artifact verification failed: {path}")
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != row["sha256"]:
            raise SystemExit(f"promoted artifact SHA verification failed: {path}")
PYVERIFY3

safe_install_script() {
  local source="$1"
  local destination="$2"
  mkdir -p "$(dirname "$destination")"
  if [[ -e "$destination" ]]; then
    if [[ "$(sha256sum "$source" | awk '{print $1}')" != "$(sha256sum "$destination" | awk '{print $1}')" ]]; then
      echo "ERROR: refusing to overwrite a different project script: $destination" >&2
      exit 1
    fi
    chmod +x "$destination"
    return 0
  fi
  cp "$source" "$destination"
  chmod +x "$destination"
}
safe_install_script "$0" "$SCRIPT_DEST"

rm -f "$LATEST_RESULT_LINK" "$LATEST_QC_LINK"
ln -s "$OUT_ROOT" "$LATEST_RESULT_LINK"
ln -s "$QC_ROOT" "$LATEST_QC_LINK"
chmod -R a-w "$OUT_ROOT" "$QC_ROOT"

FINAL_STATUS="$(metric "$FINAL_QC" stage6x_tratlas_exact_coordinate_crosswalk_status)"
[[ "$FINAL_STATUS" == "PASS_READY_FOR_TRATLAS_METADATA_AND_API_CACHE" ]] || {
  echo "ERROR: unexpected Stage 6X final status: $FINAL_STATUS" >&2
  exit 1
}

echo
echo "===== STAGE 6X FINAL QC ====="
column -ts $'\t' "$FINAL_QC"

echo
echo "===== TR-ATLAS CROSSWALK CLASS DISTRIBUTION ====="
column -ts $'\t' "$OUT_ROOT/summary/tr_atlas_crosswalk_class.distribution.tsv"

echo
echo "===== POPULATION COVERAGE ACCOUNTING ====="
column -ts $'\t' "$OUT_ROOT/summary/population_coverage_accounting.tsv"

echo
echo "===== COVERAGE BY SUPPORT BIN ====="
column -ts $'\t' "$OUT_ROOT/summary/coverage_by_support_bin.tsv"

echo
echo "===== TR-ATLAS CROSSWALK PROMOTION POLICY ====="
column -ts $'\t' "$OUT_ROOT/contracts/tr_atlas_crosswalk_promotion_policy.tsv"

echo
echo "===== OUTPUT ====="
echo "Installed script:          $SCRIPT_DEST"
echo "Result:                    $OUT_ROOT"
echo "QC:                        $FINAL_QC"
echo "All-locus crosswalk:       $OUT_ROOT/tables/p01_locus.tratlas_exact_coordinate_crosswalk.tsv.gz"
echo "Exact matches:             $OUT_ROOT/tables/p01_locus.tratlas_exact_matches.tsv.gz"
echo "Nonexact review:           $OUT_ROOT/tables/p01_locus.tratlas_nonexact_review.tsv.gz"
echo "Candidates within 100 bp:  $OUT_ROOT/tables/p01_locus.tratlas_candidates_within_100bp.tsv.gz"
echo "Coverage accounting:       $OUT_ROOT/summary/population_coverage_accounting.tsv"
echo "Coverage by chromosome:    $OUT_ROOT/summary/coverage_by_chromosome.tsv"
echo "Coverage by motif length:  $OUT_ROOT/summary/coverage_by_motif_length.tsv"
echo "Coverage by support bin:   $OUT_ROOT/summary/coverage_by_support_bin.tsv"
echo "Artifact manifest:         $ARTIFACT_MANIFEST"
echo "Latest result link:        $(readlink -f "$LATEST_RESULT_LINK")"
echo "Latest QC link:            $(readlink -f "$LATEST_QC_LINK")"
echo
echo "Stage 6X measures exact-coordinate catalog coverage and source-union coverage only."
echo "TR-Atlas motif semantics, population API retrieval, population comparison, final ranking,"
echo "and specialized motif 4,513 implementation were not run."
