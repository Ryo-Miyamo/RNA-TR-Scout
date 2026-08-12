#!/usr/bin/env bash
set -euo pipefail

STAGE_VERSION="rnatr_tratlas_live_bigbed_source_audit_v0.1.0"
RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"
EXPECTED_PACKAGE_VERSION="0.3.2"
EXPECTED_QUERY_LOCI="11042"
EXPECTED_REPEATCATALOGS_EXACT="403"
EXPECTED_REPEATCATALOGS_SAFE="1"
EXPECTED_REPEATCATALOGS_MANUAL="52"
EXPECTED_REPEATCATALOGS_NO_CATALOG="10586"
BIGBED_URL="https://wlcb.oit.uci.edu/TRatlas/top/hg38_version7_913341_TRs_wb.bb"
BIGBED_FILENAME="hg38_version7_913341_TRs_wb.bb"
FILENAME_DECLARED_ROWS="913341"
PLAUSIBLE_MIN_ROWS="800000"
PLAUSIBLE_MAX_ROWS="1000000"
KNOWN_TR_ID="TR137069"
KNOWN_CHROM="chr15"
KNOWN_BROWSER_START="81650448"
KNOWN_BROWSER_END="81650492"

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

SOURCE_BASE="$PROJECT_ROOT/external_reference/tratlas/live_bigbed"
SNAPSHOT_BASE="$SOURCE_BASE/snapshots"
ACQUISITION_LOG_BASE="$SOURCE_BASE/acquisition_logs/$STAGE_VERSION"
OUT_BASE="$PROJECT_ROOT/results/11_tratlas_live_bigbed_source_audit/$RUN_ID/$STAGE_VERSION"
QC_BASE="$PROJECT_ROOT/qc/11_tratlas_live_bigbed_source_audit/$RUN_ID/$STAGE_VERSION"
TMP_BASE="$PROJECT_ROOT/tmp/11_tratlas_live_bigbed_source_audit/$RUN_ID/$STAGE_VERSION"
SCRIPT_DEST="$PROJECT_ROOT/scripts/$(basename "$0")"
LATEST_SOURCE_LINK="$SOURCE_BASE/latest_content_snapshot"
LATEST_RESULT_LINK="$PROJECT_ROOT/results/11_tratlas_live_bigbed_source_audit/$RUN_ID/latest"
LATEST_QC_LINK="$PROJECT_ROOT/qc/11_tratlas_live_bigbed_source_audit/$RUN_ID/latest"

mkdir -p \
  "$SNAPSHOT_BASE" "$ACQUISITION_LOG_BASE" \
  "$OUT_BASE" "$QC_BASE" "$TMP_BASE" \
  "$PROJECT_ROOT/scripts"

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

for path in "$QUERY_QC" "$QUERIES" "$STAGE6R_QC"; do
  [[ -s "$path" ]] || {
    echo "ERROR: missing or empty prerequisite: $path" >&2
    exit 1
  }
done

gzip -t "$QUERIES"

installed_version="$(rnatr-scout version)"
[[ "$installed_version" == "$EXPECTED_PACKAGE_VERSION" ]] || {
  echo "ERROR: expected rnatr-scout $EXPECTED_PACKAGE_VERSION; observed $installed_version" >&2
  exit 1
}

require_metric "$QUERY_QC" adapter_query_package_status PASS
require_metric "$STAGE6R_QC" stage6r_crosswalk_coverage_audit_status PASS
require_metric "$STAGE6R_QC" all_p01_loci_denominator "$EXPECTED_QUERY_LOCI"
require_metric "$STAGE6R_QC" current_exact_comparable_loci "$EXPECTED_REPEATCATALOGS_EXACT"
require_metric "$STAGE6R_QC" biologically_equivalent_safe_loci "$EXPECTED_REPEATCATALOGS_SAFE"
require_metric "$STAGE6R_QC" manual_review_only_loci "$EXPECTED_REPEATCATALOGS_MANUAL"
require_metric "$STAGE6R_QC" no_catalog_coverage_loci "$EXPECTED_REPEATCATALOGS_NO_CATALOG"
require_metric "$STAGE6R_QC" coverage_expansion_gate_status HOLD

query_rows="$(gzip -cd "$QUERIES" | awk 'END {print (NR > 0 ? NR - 1 : 0)}')"
[[ "$query_rows" == "$EXPECTED_QUERY_LOCI" ]] || {
  echo "ERROR: expected $EXPECTED_QUERY_LOCI query loci; observed $query_rows" >&2
  exit 1
}

for tool in curl sha256sum gzip python flock file stat; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "ERROR: required tool unavailable: $tool" >&2
    exit 1
  }
done

missing_ucsc=()
for tool in bigBedInfo bigBedToBed; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    missing_ucsc+=("$tool")
  fi
done
if (( ${#missing_ucsc[@]} > 0 )); then
  echo "ERROR: UCSC BigBed tools are missing: ${missing_ucsc[*]}" >&2
  echo "Install once in rnatr-v03, then rerun:" >&2
  echo "  conda install -n rnatr-v03 -c bioconda ucsc-bigbedinfo ucsc-bigbedtobed" >&2
  exit 1
fi

exec 9>"$TMP_BASE/.acquisition.lock"
if ! flock -n 9; then
  echo "ERROR: another TR-Atlas BigBed acquisition/audit process holds the lock" >&2
  exit 1
fi

WORK_ROOT="$(mktemp -d "$TMP_BASE/work.XXXXXXXX")"
cleanup() {
  rm -rf "$WORK_ROOT"
}
trap cleanup EXIT

BB_PART="$WORK_ROOT/$BIGBED_FILENAME.part"
HEADERS_PART="$WORK_ROOT/http_headers.txt"
CURL_META_PART="$WORK_ROOT/curl_transfer.tsv"
RETRIEVED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf '%s\n' "$RETRIEVED_AT" > "$WORK_ROOT/retrieved_at_utc.txt"

UNIT_TEST_LOG="$WORK_ROOT/unit_tests.log"
RNATR_PROJECT_ROOT="$PROJECT_ROOT" \
python -m unittest discover \
  -s "$PROJECT_ROOT/tests/unit" \
  -v > "$UNIT_TEST_LOG" 2>&1

grep -qx 'OK' "$UNIT_TEST_LOG" || {
  cat "$UNIT_TEST_LOG" >&2
  echo "ERROR: unit tests failed" >&2
  exit 1
}

echo "===== STAGE 6W PREFLIGHT ====="
echo "stage version:             $STAGE_VERSION"
echo "rnatr-scout version:       $installed_version"
echo "query loci denominator:    $EXPECTED_QUERY_LOCI"
echo "RepeatCatalogs exact:      $EXPECTED_REPEATCATALOGS_EXACT/$EXPECTED_QUERY_LOCI"
echo "coverage gate:             HOLD"
echo "source type:               LIVE UNVERSIONED BIGBED"
echo "source URL:                $BIGBED_URL"
echo "download:                  RESUMABLE; CONTENT-ADDRESSED; SHA256"
echo "schema assumptions:        NONE BEFORE AUDIT"
echo "known anchor:              $KNOWN_TR_ID $KNOWN_CHROM:$KNOWN_BROWSER_START-$KNOWN_BROWSER_END"
echo "crosswalk:                 NOT RUN IN THIS STAGE"
echo "API crawl:                 NOT RUN IN THIS STAGE"
echo "final ranking:             BLOCKED"
echo "specialized motif 4,513:   PAUSED"

echo
echo "===== DOWNLOAD TR-ATLAS LIVE BIGBED ====="
curl \
  --fail \
  --location \
  --retry 6 \
  --retry-all-errors \
  --retry-delay 2 \
  --connect-timeout 30 \
  --max-time 7200 \
  --continue-at - \
  --user-agent "RNA-TR-Scout/${STAGE_VERSION}" \
  --dump-header "$HEADERS_PART" \
  --output "$BB_PART" \
  --write-out $'http_code\t%{http_code}\nurl_effective\t%{url_effective}\ncontent_type\t%{content_type}\nsize_download\t%{size_download}\nremote_ip\t%{remote_ip}\nssl_verify_result\t%{ssl_verify_result}\ntime_total_seconds\t%{time_total}\n' \
  "$BIGBED_URL" > "$CURL_META_PART"

[[ -s "$BB_PART" ]] || {
  echo "ERROR: downloaded BigBed is empty" >&2
  exit 1
}

http_code="$(metric "$CURL_META_PART" http_code)"
case "$http_code" in
  200|206) ;;
  *)
    echo "ERROR: unexpected HTTP status: $http_code" >&2
    exit 1
    ;;
esac

BIGBED_SHA256="$(sha256sum "$BB_PART" | awk '{print $1}')"
BIGBED_BYTES="$(stat -c '%s' "$BB_PART")"
SNAPSHOT_ID="sha256_${BIGBED_SHA256}"
SNAPSHOT_ROOT="$SNAPSHOT_BASE/$SNAPSHOT_ID"
SNAPSHOT_BB="$SNAPSHOT_ROOT/$BIGBED_FILENAME"
OUT_ROOT="$OUT_BASE/$SNAPSHOT_ID"
QC_ROOT="$QC_BASE/$SNAPSHOT_ID"
FINAL_QC="$QC_ROOT/tratlas_live_bigbed_source_audit.qc.tsv"
ARTIFACT_MANIFEST="$OUT_ROOT/tratlas_live_bigbed_source_audit.artifact_manifest.tsv"

verify_existing_checkpoint() {
  [[ -s "$FINAL_QC" && -s "$ARTIFACT_MANIFEST" && -s "$SNAPSHOT_BB" ]] || return 1
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
  existing_status="$(metric "$FINAL_QC" stage6w_tratlas_bigbed_source_audit_status)"
  echo
  echo "===== EXISTING HASH-VALIDATED STAGE 6W CHECKPOINT ====="
  column -ts $'\t' "$FINAL_QC"
  echo
  echo "Snapshot: $SNAPSHOT_BB"
  echo "Result:   $OUT_ROOT"
  echo "QC:       $FINAL_QC"
  if [[ "$existing_status" == "PASS_READY_FOR_EXACT_CROSSWALK" ]]; then
    exit 0
  fi
  exit 2
fi

if [[ -e "$OUT_ROOT" || -e "$QC_ROOT" ]]; then
  echo "ERROR: content-addressed output exists but is not a valid immutable PASS checkpoint" >&2
  echo "  output: $OUT_ROOT" >&2
  echo "  qc:     $QC_ROOT" >&2
  exit 1
fi

STAGE_OUT="$WORK_ROOT/stage_out"
STAGE_QC="$WORK_ROOT/stage_qc"
mkdir -p \
  "$STAGE_OUT/source" "$STAGE_OUT/provenance" \
  "$STAGE_OUT/schema" "$STAGE_OUT/contracts" \
  "$STAGE_QC"

if [[ -e "$SNAPSHOT_ROOT" ]]; then
  [[ -s "$SNAPSHOT_BB" ]] || {
    echo "ERROR: existing content snapshot is incomplete: $SNAPSHOT_ROOT" >&2
    exit 1
  }
  observed_existing_sha="$(sha256sum "$SNAPSHOT_BB" | awk '{print $1}')"
  [[ "$observed_existing_sha" == "$BIGBED_SHA256" ]] || {
    echo "ERROR: existing content snapshot SHA mismatch" >&2
    exit 1
  }
  rm -f "$BB_PART"
else
  mkdir -p "$SNAPSHOT_ROOT"
  mv "$BB_PART" "$SNAPSHOT_BB"
  chmod a-w "$SNAPSHOT_BB"
fi

ACQUISITION_ID="${RETRIEVED_AT//[:T-]/}_${BIGBED_SHA256:0:12}"
ACQUISITION_ROOT="$ACQUISITION_LOG_BASE/$ACQUISITION_ID"
mkdir -p "$ACQUISITION_ROOT"
cp "$HEADERS_PART" "$ACQUISITION_ROOT/http_headers.txt"
cp "$CURL_META_PART" "$ACQUISITION_ROOT/curl_transfer.tsv"
cp "$WORK_ROOT/retrieved_at_utc.txt" "$ACQUISITION_ROOT/retrieved_at_utc.txt"
printf 'source_url\t%s\nsha256\t%s\nbytes\t%s\nsnapshot_path\t%s\n' \
  "$BIGBED_URL" "$BIGBED_SHA256" "$BIGBED_BYTES" "$SNAPSHOT_BB" \
  > "$ACQUISITION_ROOT/acquisition_identity.tsv"

cp "$ACQUISITION_ROOT/http_headers.txt" "$STAGE_OUT/source/http_headers.txt"
cp "$ACQUISITION_ROOT/curl_transfer.tsv" "$STAGE_OUT/source/curl_transfer.tsv"
cp "$ACQUISITION_ROOT/retrieved_at_utc.txt" "$STAGE_OUT/source/retrieved_at_utc.txt"
cp "$ACQUISITION_ROOT/acquisition_identity.tsv" "$STAGE_OUT/source/acquisition_identity.tsv"
cp "$UNIT_TEST_LOG" "$STAGE_OUT/provenance/unit_tests.log"
file "$SNAPSHOT_BB" > "$STAGE_OUT/source/file_identification.txt"

bigBedInfo "$SNAPSHOT_BB" > "$STAGE_OUT/schema/bigBedInfo.txt"
if bigBedInfo -as "$SNAPSHOT_BB" \
  > "$STAGE_OUT/schema/bigBedInfo.autosql.txt" \
  2> "$STAGE_OUT/schema/bigBedInfo.autosql.stderr.txt"; then
  printf 'PASS\n' > "$STAGE_OUT/schema/bigBedInfo.autosql.status.txt"
else
  printf 'NOT_AVAILABLE_OR_UNSUPPORTED\n' \
    > "$STAGE_OUT/schema/bigBedInfo.autosql.status.txt"
fi

BED_PART="$WORK_ROOT/${BIGBED_FILENAME%.bb}.bed.part"
BED_FINAL="$STAGE_OUT/schema/${BIGBED_FILENAME%.bb}.bed"
bigBedToBed "$SNAPSHOT_BB" "$BED_PART"
[[ -s "$BED_PART" ]] || {
  echo "ERROR: bigBedToBed produced an empty BED" >&2
  exit 1
}
mv "$BED_PART" "$BED_FINAL"

PY_IMPL="$STAGE_OUT/provenance/rnatr_tratlas_live_bigbed_source_audit_v0.1.0.py"
cat > "$PY_IMPL" <<'PY'
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sqlite3
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping

VERSION = "rnatr_tratlas_live_bigbed_source_audit_v0.1.0"
TR_ID_RE = re.compile(r"^TR[0-9]+$")
IUPAC_RE = re.compile(r"^[ACGTRYSWKMBDHVN]+$", re.IGNORECASE)
NUMERIC_RE = re.compile(r"^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$")
MISSING = {"", ".", "NA", "N/A", "null", "None"}


class ContractError(RuntimeError):
    pass


@dataclass
class FieldProfile:
    nonmissing: int = 0
    tr_id_like: int = 0
    iupac_like: int = 0
    numeric_like: int = 0
    min_length: int | None = None
    max_length: int = 0
    examples: list[str] = field(default_factory=list)

    def observe(self, value: str) -> None:
        if value in MISSING:
            return
        self.nonmissing += 1
        length = len(value)
        self.min_length = length if self.min_length is None else min(self.min_length, length)
        self.max_length = max(self.max_length, length)
        if len(self.examples) < 8 and value not in self.examples:
            self.examples.append(value)
        if TR_ID_RE.fullmatch(value):
            self.tr_id_like += 1
        if IUPAC_RE.fullmatch(value) and not TR_ID_RE.fullmatch(value):
            self.iupac_like += 1
        if NUMERIC_RE.fullmatch(value):
            self.numeric_like += 1


def atomic_write_tsv(
    path: Path,
    fields: list[str],
    rows: Iterable[Mapping[str, object]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        newline="",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        temp_path = Path(handle.name)
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
    temp_path.replace(path)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        newline="",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        temp_path = Path(handle.name)
        handle.write(text)
    temp_path.replace(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_key_value(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        values[key.strip()] = value.strip()
    return values


def parse_int(value: str, field_name: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise ContractError(f"invalid integer in {field_name}: {value!r}") from exc


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bed", type=Path, required=True)
    parser.add_argument("--bigbed", type=Path, required=True)
    parser.add_argument("--bigbed-info", type=Path, required=True)
    parser.add_argument("--out-root", type=Path, required=True)
    parser.add_argument("--qc-root", type=Path, required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--retrieved-at", required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--source-bytes", type=int, required=True)
    parser.add_argument("--expected-query-loci", type=int, required=True)
    parser.add_argument("--repeatcatalogs-exact", type=int, required=True)
    parser.add_argument("--repeatcatalogs-safe", type=int, required=True)
    parser.add_argument("--repeatcatalogs-manual", type=int, required=True)
    parser.add_argument("--repeatcatalogs-no-catalog", type=int, required=True)
    parser.add_argument("--filename-declared-rows", type=int, required=True)
    parser.add_argument("--plausible-min-rows", type=int, required=True)
    parser.add_argument("--plausible-max-rows", type=int, required=True)
    parser.add_argument("--known-tr-id", required=True)
    parser.add_argument("--known-chrom", required=True)
    parser.add_argument("--known-browser-start", type=int, required=True)
    parser.add_argument("--known-browser-end", type=int, required=True)
    parser.add_argument("--script-sha256", required=True)
    args = parser.parse_args()

    schema_root = args.out_root / "schema"
    source_root = args.out_root / "source"
    contract_root = args.out_root / "contracts"
    provenance_root = args.out_root / "provenance"
    for root in (args.out_root, args.qc_root, schema_root, source_root, contract_root, provenance_root):
        root.mkdir(parents=True, exist_ok=True)

    observed_source_sha = sha256_file(args.bigbed)
    if observed_source_sha != args.source_sha256:
        raise ContractError("BigBed SHA-256 changed before schema audit")
    if args.bigbed.stat().st_size != args.source_bytes:
        raise ContractError("BigBed byte count changed before schema audit")

    database_path = provenance_root / "schema_audit.sqlite"
    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA journal_mode=OFF")
    connection.execute("PRAGMA synchronous=OFF")
    connection.execute("PRAGMA temp_store=FILE")
    connection.execute("CREATE TABLE full_rows (row_hash TEXT PRIMARY KEY)")
    connection.execute(
        "CREATE TABLE intervals (chrom TEXT, start INTEGER, end INTEGER, PRIMARY KEY(chrom,start,end))"
    )
    connection.execute(
        "CREATE TABLE tr_tokens (column_index INTEGER, tr_id TEXT, row_number INTEGER, chrom TEXT, start INTEGER, end INTEGER)"
    )

    data_rows = 0
    invalid_coordinate_rows = 0
    nonpositive_interval_rows = 0
    full_duplicate_rows = 0
    duplicate_interval_rows = 0
    chromosome_reentry_violations = 0
    within_chrom_sort_violations = 0
    field_count_distribution: Counter[int] = Counter()
    chromosome_counts: Counter[str] = Counter()
    field_profiles: list[FieldProfile] = []
    first_rows: list[str] = []
    last_rows: list[str] = []
    anchor_rows: list[dict[str, object]] = []
    seen_chromosomes: set[str] = set()
    current_chrom: str | None = None
    previous_start_end: tuple[int, int] | None = None

    def ensure_profiles(count: int) -> None:
        while len(field_profiles) < count:
            field_profiles.append(FieldProfile())

    with args.bed.open("r", encoding="utf-8", newline="") as handle:
        for row_number, raw in enumerate(handle, start=1):
            line = raw.rstrip("\n\r")
            if not line:
                continue
            fields = line.split("\t")
            data_rows += 1
            field_count_distribution[len(fields)] += 1
            ensure_profiles(len(fields))
            for index, value in enumerate(fields):
                field_profiles[index].observe(value)

            if len(first_rows) < 5:
                first_rows.append(line)
            last_rows.append(line)
            if len(last_rows) > 5:
                last_rows.pop(0)

            if len(fields) < 3:
                invalid_coordinate_rows += 1
                continue
            chrom = fields[0]
            try:
                start = int(fields[1])
                end = int(fields[2])
            except ValueError:
                invalid_coordinate_rows += 1
                continue
            if start < 0 or end <= start:
                nonpositive_interval_rows += 1

            chromosome_counts[chrom] += 1
            if current_chrom is None:
                current_chrom = chrom
                seen_chromosomes.add(chrom)
                previous_start_end = (start, end)
            elif chrom != current_chrom:
                if chrom in seen_chromosomes:
                    chromosome_reentry_violations += 1
                seen_chromosomes.add(chrom)
                current_chrom = chrom
                previous_start_end = (start, end)
            else:
                assert previous_start_end is not None
                if (start, end) < previous_start_end:
                    within_chrom_sort_violations += 1
                previous_start_end = (start, end)

            row_hash = hashlib.sha256(line.encode("utf-8")).hexdigest()
            cursor = connection.execute(
                "INSERT OR IGNORE INTO full_rows(row_hash) VALUES (?)", (row_hash,)
            )
            if cursor.rowcount == 0:
                full_duplicate_rows += 1
            cursor = connection.execute(
                "INSERT OR IGNORE INTO intervals(chrom,start,end) VALUES (?,?,?)",
                (chrom, start, end),
            )
            if cursor.rowcount == 0:
                duplicate_interval_rows += 1

            for column_index, value in enumerate(fields):
                if TR_ID_RE.fullmatch(value):
                    connection.execute(
                        "INSERT INTO tr_tokens(column_index,tr_id,row_number,chrom,start,end) VALUES (?,?,?,?,?,?)",
                        (column_index, value, row_number, chrom, start, end),
                    )
                if value == args.known_tr_id:
                    anchor_rows.append(
                        {
                            "row_number": row_number,
                            "column_index_1based": column_index + 1,
                            "chrom": chrom,
                            "start_0based": start,
                            "end_0based_exclusive": end,
                            "full_row": line,
                        }
                    )
            if data_rows % 50000 == 0:
                connection.commit()
    connection.commit()

    id_candidates: list[dict[str, object]] = []
    for column_index, token_count, unique_count in connection.execute(
        "SELECT column_index, COUNT(*), COUNT(DISTINCT tr_id) FROM tr_tokens GROUP BY column_index ORDER BY COUNT(*) DESC, column_index"
    ):
        duplicate_id_values = connection.execute(
            "SELECT COUNT(*) FROM (SELECT tr_id FROM tr_tokens WHERE column_index=? GROUP BY tr_id HAVING COUNT(*)>1)",
            (column_index,),
        ).fetchone()[0]
        id_candidates.append(
            {
                "column_index_1based": column_index + 1,
                "tr_id_like_rows": token_count,
                "tr_id_like_fraction_of_all_rows": f"{token_count / data_rows:.12f}" if data_rows else "0",
                "unique_tr_ids": unique_count,
                "duplicated_tr_id_values": duplicate_id_values,
                "candidate_status": (
                    "PRIMARY_CANDIDATE"
                    if token_count == max((row[1] for row in connection.execute(
                        "SELECT column_index, COUNT(*) FROM tr_tokens GROUP BY column_index"
                    )), default=0)
                    else "SECONDARY_CANDIDATE"
                ),
            }
        )

    primary_id_candidate = id_candidates[0] if id_candidates else None
    id_column_ready = False
    id_column_index_1based: int | None = None
    unique_tr_ids = 0
    duplicate_tr_id_values = 0
    tr_id_fraction = 0.0
    if primary_id_candidate is not None:
        id_column_index_1based = int(primary_id_candidate["column_index_1based"])
        unique_tr_ids = int(primary_id_candidate["unique_tr_ids"])
        duplicate_tr_id_values = int(primary_id_candidate["duplicated_tr_id_values"])
        tr_id_fraction = float(primary_id_candidate["tr_id_like_fraction_of_all_rows"])
        id_column_ready = (
            tr_id_fraction >= 0.99
            and unique_tr_ids == data_rows
            and duplicate_tr_id_values == 0
        )

    motif_candidates: list[dict[str, object]] = []
    for index, profile in enumerate(field_profiles):
        if profile.iupac_like == 0:
            continue
        fraction = profile.iupac_like / data_rows if data_rows else 0.0
        motif_candidates.append(
            {
                "column_index_1based": index + 1,
                "iupac_like_rows": profile.iupac_like,
                "iupac_like_fraction_of_all_rows": f"{fraction:.12f}",
                "min_value_length": profile.min_length if profile.min_length is not None else ".",
                "max_value_length": profile.max_length,
                "examples": ";".join(profile.examples),
            }
        )
    motif_candidates.sort(
        key=lambda row: (-int(row["iupac_like_rows"]), int(row["column_index_1based"]))
    )
    motif_column_candidate = (
        motif_candidates[0]
        if motif_candidates and float(motif_candidates[0]["iupac_like_fraction_of_all_rows"]) >= 0.80
        else None
    )

    bigbed_info = read_key_value(args.bigbed_info)
    item_count_raw = bigbed_info.get("itemCount", ".")
    try:
        bigbed_item_count = int(item_count_raw.replace(",", ""))
    except (ValueError, AttributeError):
        bigbed_item_count = None
    item_count_parity = bigbed_item_count is None or bigbed_item_count == data_rows

    anchor_count = len(anchor_rows)
    anchor_coordinate_status = "FAIL_NOT_UNIQUE"
    if anchor_count == 1:
        anchor = anchor_rows[0]
        observed = (
            str(anchor["chrom"]),
            int(anchor["start_0based"]),
            int(anchor["end_0based_exclusive"]),
        )
        exact_bed = (
            args.known_chrom,
            args.known_browser_start,
            args.known_browser_end,
        )
        display_to_bed = (
            args.known_chrom,
            args.known_browser_start - 1,
            args.known_browser_end,
        )
        if observed == exact_bed:
            anchor_coordinate_status = "PASS_EXACT_TO_BROWSER_NUMBERS"
        elif observed == display_to_bed:
            anchor_coordinate_status = "PASS_BROWSER_1BASED_START_TO_BED_0BASED"
        else:
            anchor_coordinate_status = "FAIL_COORDINATE_DISCREPANCY"

    uniform_field_count = len(field_count_distribution) == 1
    plausible_row_count = args.plausible_min_rows <= data_rows <= args.plausible_max_rows
    filename_count_status = (
        "PASS_MATCH"
        if data_rows == args.filename_declared_rows
        else "REVIEW_FILENAME_LABEL_DIFFERS_FROM_OBSERVED_ROWS"
    )

    fatal_reasons: list[str] = []
    if not plausible_row_count:
        fatal_reasons.append("ROW_COUNT_OUTSIDE_PLAUSIBLE_RANGE")
    if not uniform_field_count:
        fatal_reasons.append("NONUNIFORM_FIELD_COUNT")
    if invalid_coordinate_rows:
        fatal_reasons.append("INVALID_COORDINATE_ROWS")
    if nonpositive_interval_rows:
        fatal_reasons.append("NONPOSITIVE_INTERVAL_ROWS")
    if chromosome_reentry_violations or within_chrom_sort_violations:
        fatal_reasons.append("BED_SORT_ORDER_VIOLATION")
    if full_duplicate_rows:
        fatal_reasons.append("DUPLICATE_FULL_ROWS")
    if not id_column_ready:
        fatal_reasons.append("UNIQUE_TR_ID_COLUMN_NOT_RESOLVED")
    if not item_count_parity:
        fatal_reasons.append("BIGBEDINFO_ITEMCOUNT_BED_ROW_MISMATCH")
    if anchor_coordinate_status.startswith("FAIL"):
        fatal_reasons.append("KNOWN_TR137069_ANCHOR_FAILED")

    stage_status = (
        "PASS_READY_FOR_EXACT_CROSSWALK"
        if not fatal_reasons
        else "HOLD_SCHEMA_OR_SOURCE_REVIEW"
    )
    safe_equivalence_status = (
        "MOTIF_COLUMN_CANDIDATE_REQUIRES_SEMANTIC_VALIDATION"
        if motif_column_candidate is not None
        else "HOLD_REQUIRES_AUTHORITATIVE_MOTIF_JOIN"
    )

    field_rows = []
    for index, profile in enumerate(field_profiles):
        field_rows.append(
            {
                "column_index_1based": index + 1,
                "nonmissing_rows": profile.nonmissing,
                "nonmissing_fraction": f"{profile.nonmissing / data_rows:.12f}" if data_rows else "0",
                "tr_id_like_rows": profile.tr_id_like,
                "iupac_like_rows": profile.iupac_like,
                "numeric_like_rows": profile.numeric_like,
                "min_value_length": profile.min_length if profile.min_length is not None else ".",
                "max_value_length": profile.max_length,
                "examples": ";".join(profile.examples),
            }
        )
    atomic_write_tsv(
        schema_root / "bigbed_field_profile.tsv",
        [
            "column_index_1based",
            "nonmissing_rows",
            "nonmissing_fraction",
            "tr_id_like_rows",
            "iupac_like_rows",
            "numeric_like_rows",
            "min_value_length",
            "max_value_length",
            "examples",
        ],
        field_rows,
    )
    atomic_write_tsv(
        schema_root / "tr_id_column_candidates.tsv",
        [
            "column_index_1based",
            "tr_id_like_rows",
            "tr_id_like_fraction_of_all_rows",
            "unique_tr_ids",
            "duplicated_tr_id_values",
            "candidate_status",
        ],
        id_candidates,
    )
    atomic_write_tsv(
        schema_root / "motif_column_candidates.tsv",
        [
            "column_index_1based",
            "iupac_like_rows",
            "iupac_like_fraction_of_all_rows",
            "min_value_length",
            "max_value_length",
            "examples",
        ],
        motif_candidates,
    )
    atomic_write_tsv(
        schema_root / "chromosome_coverage.tsv",
        ["chrom", "rows", "fraction_of_all_rows"],
        [
            {
                "chrom": chrom,
                "rows": rows,
                "fraction_of_all_rows": f"{rows / data_rows:.12f}" if data_rows else "0",
            }
            for chrom, rows in chromosome_counts.items()
        ],
    )
    atomic_write_tsv(
        schema_root / "known_anchor_TR137069.tsv",
        [
            "row_number",
            "column_index_1based",
            "chrom",
            "start_0based",
            "end_0based_exclusive",
            "full_row",
        ],
        anchor_rows,
    )
    atomic_write_text(
        schema_root / "first_last_rows.txt",
        "# FIRST FIVE ROWS\n"
        + "\n".join(first_rows)
        + "\n# LAST FIVE ROWS\n"
        + "\n".join(last_rows)
        + "\n",
    )

    schema_metrics = [
        ("stage_version", VERSION),
        ("source_url", args.source_url),
        ("source_retrieved_at_utc", args.retrieved_at),
        ("source_sha256", args.source_sha256),
        ("source_bytes", args.source_bytes),
        ("bed_data_rows", data_rows),
        ("filename_declared_rows", args.filename_declared_rows),
        ("filename_count_status", filename_count_status),
        ("plausible_row_count_range", f"{args.plausible_min_rows}-{args.plausible_max_rows}"),
        ("plausible_row_count_status", "PASS" if plausible_row_count else "FAIL"),
        ("bigbed_info_item_count", bigbed_item_count if bigbed_item_count is not None else "."),
        ("bigbed_item_count_parity", "PASS" if item_count_parity else "FAIL"),
        ("field_count_distribution", ";".join(f"{key}={value}" for key, value in sorted(field_count_distribution.items()))),
        ("uniform_field_count_status", "PASS" if uniform_field_count else "FAIL"),
        ("chromosome_count", len(chromosome_counts)),
        ("chromosomes", ";".join(chromosome_counts.keys())),
        ("invalid_coordinate_rows", invalid_coordinate_rows),
        ("nonpositive_interval_rows", nonpositive_interval_rows),
        ("chromosome_reentry_violations", chromosome_reentry_violations),
        ("within_chrom_sort_violations", within_chrom_sort_violations),
        ("full_duplicate_rows", full_duplicate_rows),
        ("duplicate_interval_rows", duplicate_interval_rows),
        ("tr_id_column_index_1based", id_column_index_1based if id_column_index_1based is not None else "."),
        ("tr_id_like_fraction", f"{tr_id_fraction:.12f}"),
        ("unique_tr_ids", unique_tr_ids),
        ("duplicated_tr_id_values", duplicate_tr_id_values),
        ("tr_id_column_readiness", "PASS" if id_column_ready else "FAIL"),
        ("known_anchor_tr_id", args.known_tr_id),
        ("known_anchor_rows", anchor_count),
        ("known_anchor_coordinate_status", anchor_coordinate_status),
        ("motif_column_candidate_1based", motif_column_candidate["column_index_1based"] if motif_column_candidate else "."),
        ("motif_semantics_status", safe_equivalence_status),
        ("fatal_reason_count", len(fatal_reasons)),
        ("fatal_reasons", ";".join(fatal_reasons) if fatal_reasons else "."),
        ("exact_crosswalk_permission", "ALLOW_NEXT_STAGE" if stage_status == "PASS_READY_FOR_EXACT_CROSSWALK" else "HOLD"),
        ("safe_equivalence_crosswalk_permission", "HOLD_PENDING_MOTIF_SEMANTICS"),
        ("api_frequency_download_executed", 0),
        ("rna_population_comparison_executed", 0),
        ("final_ranking_executed", 0),
        ("specialized_motif_4513_started", "false"),
        ("stage6w_tratlas_bigbed_source_audit_status", stage_status),
    ]
    atomic_write_tsv(
        schema_root / "tratlas_live_bigbed_schema_audit.tsv",
        ["metric", "value"],
        [{"metric": key, "value": value} for key, value in schema_metrics],
    )

    source_registry_rows = [
        {
            "source_id": "TRATLAS_LIVE_BIGBED_CONTENT_SNAPSHOT",
            "source_role": "TR_ID_COORDINATE_CROSSWALK_SOURCE",
            "versioning_status": "LIVE_UNVERSIONED_CONTENT_ADDRESSED_LOCALLY",
            "retrieval_url": args.source_url,
            "retrieved_at_utc": args.retrieved_at,
            "sha256": args.source_sha256,
            "bytes": args.source_bytes,
            "local_path": str(args.bigbed),
            "allowed_use": "EXACT_CROSSWALK_AFTER_SCHEMA_PASS",
            "prohibited_use": "DO_NOT_CALL_POPULATION_DISTRIBUTION_FROM_BIGBED_ALONE",
        }
    ]
    atomic_write_tsv(
        source_root / "tratlas_live_bigbed_source_registry.tsv",
        [
            "source_id",
            "source_role",
            "versioning_status",
            "retrieval_url",
            "retrieved_at_utc",
            "sha256",
            "bytes",
            "local_path",
            "allowed_use",
            "prohibited_use",
        ],
        source_registry_rows,
    )

    coverage_contract_rows = [
        {
            "metric_id": "C0_REPEATCATALOGS_EXACT",
            "numerator_definition": "RepeatCatalogs/1KG exact population-comparable loci",
            "denominator": args.expected_query_loci,
            "current_numerator": args.repeatcatalogs_exact,
            "automatic_population_use": "ALLOW",
            "purpose": "frozen baseline; never present without /11042 denominator",
        },
        {
            "metric_id": "C1_TRATLAS_CATALOG_ADDRESSABLE",
            "numerator_definition": "RNA loci with any uniquely addressable TR-Atlas interval/TR ID candidate",
            "denominator": args.expected_query_loci,
            "current_numerator": "NOT_RUN",
            "automatic_population_use": "DENY",
            "purpose": "catalog coverage only; not yet distribution-comparable",
        },
        {
            "metric_id": "C2_TRATLAS_EXACT_ID",
            "numerator_definition": "RNA loci with unique exact coordinate and authoritative TR ID",
            "denominator": args.expected_query_loci,
            "current_numerator": "NOT_RUN",
            "automatic_population_use": "PROVISIONAL_PENDING_API_QC",
            "purpose": "exact crosswalk coverage",
        },
        {
            "metric_id": "C3_TRATLAS_SAFE_EQUIVALENT",
            "numerator_definition": "C2 plus motif/phase/boundary-validated biologically equivalent loci",
            "denominator": args.expected_query_loci,
            "current_numerator": "NOT_RUN",
            "automatic_population_use": "ALLOW_ONLY_AFTER_RULE_VALIDATION",
            "purpose": "safe crosswalk coverage; overlap alone never counts",
        },
        {
            "metric_id": "C4_TRATLAS_API_USABLE",
            "numerator_definition": "C2/C3 loci with cached main-population response passing schema and frequency checks",
            "denominator": args.expected_query_loci,
            "current_numerator": "NOT_RUN",
            "automatic_population_use": "ALLOW_CONTEXT_ONLY",
            "purpose": "actual TR-Atlas population-comparable coverage",
        },
        {
            "metric_id": "C5_POPULATION_UNION_USABLE",
            "numerator_definition": "unique RNA loci usable from RepeatCatalogs/1KG, TR-Atlas, AoU, Adotto, or validated long-read source",
            "denominator": args.expected_query_loci,
            "current_numerator": "NOT_RUN",
            "automatic_population_use": "ALLOW_CONTEXT_ONLY",
            "purpose": "source-union coverage after discordance resolution",
        },
        {
            "metric_id": "COV_STRATIFIED",
            "numerator_definition": "C2-C5 reported by chromosome, motif length, RNA support bin, and locus class",
            "denominator": "stratum-specific and global 11042",
            "current_numerator": "NOT_RUN",
            "automatic_population_use": "REQUIRED",
            "purpose": "prevent a high global percentage from hiding systematic coverage holes",
        },
    ]
    atomic_write_tsv(
        contract_root / "population_coverage_accounting_contract.tsv",
        [
            "metric_id",
            "numerator_definition",
            "denominator",
            "current_numerator",
            "automatic_population_use",
            "purpose",
        ],
        coverage_contract_rows,
    )

    policy_rows = [
        ("TB01", "LIVE_SOURCE_CONTENT_ADDRESSING", "FROZEN", "URL, retrieval time, headers, bytes, and SHA-256 are mandatory."),
        ("TB02", "NO_ROW_COUNT_ASSUMPTION_FROM_FILENAME", "FROZEN", "The filename label 913341 is audited but not treated as ground truth."),
        ("TB03", "NO_EQUALITY_ASSUMPTION_WITH_TRDS_UNIVERSE", "FROZEN", "BigBed track rows and the 857975-TR TRDS universe may represent different resource layers."),
        ("TB04", "EXACT_CROSSWALK_REQUIRES_UNIQUE_TR_ID", "FROZEN", "A unique exact coordinate plus authoritative TR ID is required."),
        ("TB05", "OVERLAP_DOES_NOT_AUTHORIZE_DISTRIBUTION_TRANSFER", "FROZEN", "Overlap-only loci remain manual review."),
        ("TB06", "SAFE_EQUIVALENCE_REQUIRES_MOTIF_PHASE_BOUNDARY_VALIDATION", "HOLD", safe_equivalence_status),
        ("TB07", "BIGBED_ALONE_IS_NOT_A_POPULATION_DISTRIBUTION", "FROZEN", "API distribution retrieval and schema QC are separate stages."),
        ("TB08", "GLOBAL_AND_STRATIFIED_COVERAGE_REQUIRED", "FROZEN", "Always show numerator/11042 plus chromosome, motif-length, support-bin, and locus-class strata."),
        ("TB09", "NO_FINAL_RANKING_BEFORE_COVERAGE_AND_CONTROL_GATES", "HOLD", "same-protocol RNA controls and adequate population-reference coverage remain required."),
    ]
    atomic_write_tsv(
        contract_root / "tratlas_bigbed_crosswalk_policy.tsv",
        ["policy_id", "rule", "status", "detail"],
        [
            {"policy_id": policy_id, "rule": rule, "status": status, "detail": detail}
            for policy_id, rule, status, detail in policy_rows
        ],
    )

    qc_rows = [
        ("stage_version", VERSION),
        ("source_sha256", args.source_sha256),
        ("source_bytes", args.source_bytes),
        ("source_retrieved_at_utc", args.retrieved_at),
        ("all_p01_loci_denominator", args.expected_query_loci),
        ("repeatcatalogs_exact_baseline", args.repeatcatalogs_exact),
        ("repeatcatalogs_safe_baseline", args.repeatcatalogs_safe),
        ("repeatcatalogs_manual_baseline", args.repeatcatalogs_manual),
        ("repeatcatalogs_no_catalog_baseline", args.repeatcatalogs_no_catalog),
        ("bigbed_bed_rows", data_rows),
        ("bigbed_unique_tr_ids", unique_tr_ids),
        ("bigbed_tr_id_column_index_1based", id_column_index_1based if id_column_index_1based is not None else "."),
        ("bigbed_duplicate_full_rows", full_duplicate_rows),
        ("bigbed_duplicate_interval_rows", duplicate_interval_rows),
        ("known_anchor_status", anchor_coordinate_status),
        ("motif_semantics_status", safe_equivalence_status),
        ("exact_crosswalk_executed", 0),
        ("population_api_executed", 0),
        ("final_ranking_executed", 0),
        ("coverage_gate_status", "HOLD"),
        ("script_sha256", args.script_sha256),
        ("implementation_sha256", sha256_file(Path(__file__))),
        ("stage6w_tratlas_bigbed_source_audit_status", stage_status),
    ]
    qc_path = args.qc_root / "tratlas_live_bigbed_source_audit.qc.tsv"
    atomic_write_tsv(
        qc_path,
        ["metric", "value"],
        [{"metric": key, "value": value} for key, value in qc_rows],
    )

    connection.close()
    database_path.unlink(missing_ok=True)

    print(f"STAGE6W_STATUS\t{stage_status}")
    print(f"BIGBED_ROWS\t{data_rows}")
    print(f"UNIQUE_TR_IDS\t{unique_tr_ids}")
    print(f"TR_ID_COLUMN_1BASED\t{id_column_index_1based if id_column_index_1based is not None else '.'}")
    print(f"KNOWN_ANCHOR\t{anchor_coordinate_status}")
    print(f"MOTIF_SEMANTICS\t{safe_equivalence_status}")
    print("EXACT_CROSSWALK\tNOT_RUN")
    print("POPULATION_API\tNOT_RUN")
    print("FINAL_RANKING\tNOT_RUN")
    print(f"QC\t{qc_path}")



if __name__ == "__main__":
    main()
PY

python -m py_compile "$PY_IMPL"
SCRIPT_SHA256="$(sha256sum "$0" | awk '{print $1}')"
IMPLEMENTATION_SHA256="$(sha256sum "$PY_IMPL" | awk '{print $1}')"

python "$PY_IMPL" \
  --bed "$BED_FINAL" \
  --bigbed "$SNAPSHOT_BB" \
  --bigbed-info "$STAGE_OUT/schema/bigBedInfo.txt" \
  --out-root "$STAGE_OUT" \
  --qc-root "$STAGE_QC" \
  --source-url "$BIGBED_URL" \
  --retrieved-at "$RETRIEVED_AT" \
  --source-sha256 "$BIGBED_SHA256" \
  --source-bytes "$BIGBED_BYTES" \
  --expected-query-loci "$EXPECTED_QUERY_LOCI" \
  --repeatcatalogs-exact "$EXPECTED_REPEATCATALOGS_EXACT" \
  --repeatcatalogs-safe "$EXPECTED_REPEATCATALOGS_SAFE" \
  --repeatcatalogs-manual "$EXPECTED_REPEATCATALOGS_MANUAL" \
  --repeatcatalogs-no-catalog "$EXPECTED_REPEATCATALOGS_NO_CATALOG" \
  --filename-declared-rows "$FILENAME_DECLARED_ROWS" \
  --plausible-min-rows "$PLAUSIBLE_MIN_ROWS" \
  --plausible-max-rows "$PLAUSIBLE_MAX_ROWS" \
  --known-tr-id "$KNOWN_TR_ID" \
  --known-chrom "$KNOWN_CHROM" \
  --known-browser-start "$KNOWN_BROWSER_START" \
  --known-browser-end "$KNOWN_BROWSER_END" \
  --script-sha256 "$SCRIPT_SHA256"

STAGE_STATUS="$(metric "$STAGE_QC/tratlas_live_bigbed_source_audit.qc.tsv" stage6w_tratlas_bigbed_source_audit_status)"

cp "$0" "$STAGE_OUT/provenance/$(basename "$0")"
chmod a-w "$STAGE_OUT/provenance/$(basename "$0")"
printf 'bigBedInfo_path\t%s\nbigBedToBed_path\t%s\npython_path\t%s\nscript_sha256\t%s\nimplementation_sha256\t%s\n' \
  "$(command -v bigBedInfo)" \
  "$(command -v bigBedToBed)" \
  "$(command -v python)" \
  "$SCRIPT_SHA256" \
  "$IMPLEMENTATION_SHA256" \
  > "$STAGE_OUT/provenance/tool_and_code_identity.tsv"
conda list --explicit > "$STAGE_OUT/provenance/conda_explicit_spec.txt"

printf 'artifact\tbytes\tsha256\tpath\n' > "$STAGE_OUT/tratlas_live_bigbed_source_audit.artifact_manifest.tsv"
add_artifact() {
  local artifact="$1"
  local path="$2"
  [[ -s "$path" ]] || return 0
  printf '%s\t%s\t%s\t%s\n' \
    "$artifact" \
    "$(stat -c '%s' "$path")" \
    "$(sha256sum "$path" | awk '{print $1}')" \
    "$path" \
    >> "$STAGE_OUT/tratlas_live_bigbed_source_audit.artifact_manifest.tsv"
}

add_artifact source_bigbed "$SNAPSHOT_BB"
while IFS= read -r -d '' path; do
  [[ "$path" == "$STAGE_OUT/tratlas_live_bigbed_source_audit.artifact_manifest.tsv" ]] && continue
  add_artifact "$(basename "$path")" "$path"
done < <(find "$STAGE_OUT" -type f -print0 | sort -z)
add_artifact qc "$STAGE_QC/tratlas_live_bigbed_source_audit.qc.tsv"

python - "$STAGE_OUT/tratlas_live_bigbed_source_audit.artifact_manifest.tsv" <<'PYVERIFY'
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
        raise SystemExit("invalid artifact manifest header")
    for row in reader:
        path = Path(row["path"])
        if not path.is_file():
            raise SystemExit(f"missing artifact: {path}")
        if path.stat().st_size != int(row["bytes"]):
            raise SystemExit(f"byte mismatch: {path}")
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != row["sha256"]:
            raise SystemExit(f"SHA-256 mismatch: {path}")
PYVERIFY

mv "$STAGE_OUT" "$OUT_ROOT"
mv "$STAGE_QC" "$QC_ROOT"

# Repair manifest paths after atomic directory promotion.
python - "$ARTIFACT_MANIFEST" "$WORK_ROOT/stage_out" "$OUT_ROOT" "$WORK_ROOT/stage_qc" "$QC_ROOT" <<'PYPATHFIX'
from __future__ import annotations
import sys
from pathlib import Path

manifest = Path(sys.argv[1])
old_out, new_out, old_qc, new_qc = sys.argv[2:]
text = manifest.read_text(encoding="utf-8")
text = text.replace(old_out, new_out).replace(old_qc, new_qc)
manifest.write_text(text, encoding="utf-8")
PYPATHFIX

# Re-verify after path repair/promotion.
python - "$ARTIFACT_MANIFEST" <<'PYVERIFY2'
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
            raise SystemExit(f"artifact verification failed: {path}")
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != row["sha256"]:
            raise SystemExit(f"artifact SHA verification failed: {path}")
PYVERIFY2

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

rm -f "$LATEST_SOURCE_LINK" "$LATEST_RESULT_LINK" "$LATEST_QC_LINK"
ln -s "$SNAPSHOT_ROOT" "$LATEST_SOURCE_LINK"
ln -s "$OUT_ROOT" "$LATEST_RESULT_LINK"
ln -s "$QC_ROOT" "$LATEST_QC_LINK"

chmod -R a-w "$OUT_ROOT" "$QC_ROOT"

echo
echo "===== STAGE 6W FINAL QC ====="
column -ts $'\t' "$FINAL_QC"

echo
echo "===== BIGBED SCHEMA AUDIT ====="
column -ts $'\t' "$OUT_ROOT/schema/tratlas_live_bigbed_schema_audit.tsv"

echo
echo "===== TR-ID COLUMN CANDIDATES ====="
column -ts $'\t' "$OUT_ROOT/schema/tr_id_column_candidates.tsv"

echo
echo "===== MOTIF COLUMN CANDIDATES ====="
column -ts $'\t' "$OUT_ROOT/schema/motif_column_candidates.tsv"

echo
echo "===== KNOWN ANCHOR ====="
column -ts $'\t' "$OUT_ROOT/schema/known_anchor_TR137069.tsv"

echo
echo "===== COVERAGE ACCOUNTING CONTRACT ====="
column -ts $'\t' "$OUT_ROOT/contracts/population_coverage_accounting_contract.tsv"

echo
echo "===== OUTPUT ====="
echo "Installed script:          $SCRIPT_DEST"
echo "Content snapshot:          $SNAPSHOT_BB"
echo "Source SHA-256:            $BIGBED_SHA256"
echo "Acquisition log:           $ACQUISITION_ROOT"
echo "Audit result:              $OUT_ROOT"
echo "Audit QC:                  $FINAL_QC"
echo "Artifact manifest:         $ARTIFACT_MANIFEST"
echo "Latest source link:        $(readlink -f "$LATEST_SOURCE_LINK")"
echo "Latest result link:        $(readlink -f "$LATEST_RESULT_LINK")"
echo "Latest QC link:            $(readlink -f "$LATEST_QC_LINK")"
echo
echo "Stage 6W only freezes and audits the live BigBed source."
echo "No 11,042-locus crosswalk, API frequency crawl, population comparison, or final ranking was run."

if [[ "$STAGE_STATUS" != "PASS_READY_FOR_EXACT_CROSSWALK" ]]; then
  echo "Stage 6W completed as HOLD. The immutable audit outputs were retained for diagnosis." >&2
  exit 2
fi
