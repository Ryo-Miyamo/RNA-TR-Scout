#!/usr/bin/env bash
set -euo pipefail

STAGE_VERSION="rnatr_bulk_longread_population_reference_acquisition_v0.1.1"
SOURCE_CACHE_VERSION="rnatr_bulk_longread_population_reference_acquisition_v0.1.0"
RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"
EXPECTED_PACKAGE_VERSION="0.3.2"

# Pinned, bulk-accessible sources.
AOU_ZENODO_RECORD_ID="19895393"
AOU_EXPECTED_TITLE="All of Us Long Reads Tandem Repeats Allele Distributions"
TREXPLORER_URL="https://hgdownload.soe.ucsc.edu/gbdb/hg38/strVar/trexplorer.bb"
TREXPLORER_EXPECTED_ITEMS="5599658"
VIENNA_BB_URL="https://hgdownload.soe.ucsc.edu/gbdb/hg38/strVar/viennaVntr.bb"
VIENNA_EXPECTED_ITEMS="361362"
VIENNA_SUMMARY_URL="https://ftp.1000genomes.ebi.ac.uk/vol1/ftp/data_collections/1KG_ONT_VIENNA/release/v1.1/vamos-vntr-genotyping/vamos-summary.tsv"
VIENNA_LEGEND_URL="https://ftp.1000genomes.ebi.ac.uk/vol1/ftp/data_collections/1KG_ONT_VIENNA/release/v1.1/vamos-vntr-genotyping/summary-statistics-legend.txt"
VIENNA_README_URL="https://ftp.1000genomes.ebi.ac.uk/vol1/ftp/data_collections/1KG_ONT_VIENNA/release/v1.1/vamos-vntr-genotyping/vamos-vntr-genotyping_README.md"
STRCHIVE_URL="https://hgdownload.soe.ucsc.edu/gbdb/hg38/strVar/strchive.bb"

CURL_RETRIES="${RNATR_DOWNLOAD_RETRIES:-10}"
CURL_TIMEOUT="${RNATR_DOWNLOAD_TIMEOUT_SEC:-0}"
CURL_FILE_ATTEMPTS="${RNATR_DOWNLOAD_FILE_ATTEMPTS:-30}"
CURL_STALL_SECONDS="${RNATR_DOWNLOAD_STALL_SECONDS:-180}"
CURL_MIN_BYTES_PER_SEC="${RNATR_DOWNLOAD_MIN_BYTES_PER_SEC:-1024}"

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
  # shellcheck disable=SC1091
  source "$HOME/miniconda3/etc/profile.d/conda.sh"
fi

conda activate rnatr-v03
# shellcheck disable=SC1091
source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

for tool in python curl sha256sum md5sum stat gzip bigBedInfo bigBedToBed awk sed grep sort column flock readlink; do
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

SOURCE_ROOT="$PROJECT_ROOT/external_reference/rnatr_population_reference/bulk_sources/$SOURCE_CACHE_VERSION"
AOU_ROOT="$SOURCE_ROOT/aou_longread_tr/zenodo_record_${AOU_ZENODO_RECORD_ID}"
TREX_ROOT="$SOURCE_ROOT/trexplorer_v2_ucsc"
VIENNA_ROOT="$SOURCE_ROOT/vienna_ont_v1.1"
DISEASE_ROOT="$SOURCE_ROOT/disease_context"
LOG_ROOT="$SOURCE_ROOT/acquisition_logs"

OUT_BASE="$PROJECT_ROOT/results/11_bulk_longread_population_reference_acquisition/$RUN_ID/$STAGE_VERSION"
QC_BASE="$PROJECT_ROOT/qc/11_bulk_longread_population_reference_acquisition/$RUN_ID/$STAGE_VERSION"
TMP_BASE="$PROJECT_ROOT/tmp/11_bulk_longread_population_reference_acquisition/$RUN_ID/$STAGE_VERSION"
LATEST_RESULT_LINK="$PROJECT_ROOT/results/11_bulk_longread_population_reference_acquisition/$RUN_ID/latest"
LATEST_QC_LINK="$PROJECT_ROOT/qc/11_bulk_longread_population_reference_acquisition/$RUN_ID/latest"
SCRIPT_DEST="$PROJECT_ROOT/scripts/$(basename "$0")"

mkdir -p \
  "$AOU_ROOT/files" "$TREX_ROOT" "$VIENNA_ROOT" "$DISEASE_ROOT" "$LOG_ROOT" \
  "$OUT_BASE" "$QC_BASE" "$TMP_BASE" "$PROJECT_ROOT/scripts"

exec 9>"$TMP_BASE/.stage.lock"
if ! flock -n 9; then
  echo "ERROR: another $STAGE_VERSION process holds the lock" >&2
  exit 1
fi

script_sha256="$(sha256sum "$0" | awk '{print $1}')"
retrieved_at_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

cat <<EOF
===== STAGE 6Z PREFLIGHT =====
stage version:                 $STAGE_VERSION
rnatr-scout version:           $installed_version
reference design:              BULK-FIRST; LONG-READ POPULATION PRIMARY
catalog/motif primary:         TRExplorer v2 (GRCh38; 5,599,658 loci)
length/LPS population primary: AoU HiFi validation cohort (2,102 individuals)
HiFi confirmation:             AoU discovery cohort (543 individuals)
ONT confirmation:              AoU/1KGP replication cohort (500 individuals)
long-VNTR secondary:           1KG Vienna ONT v1.1 (1,019 individuals)
disease context:               STRchive bulk track
TR-Atlas role:                 SUPPLEMENTARY ONLY; NO ADDITIONAL LIVE CRAWL
AoU pinned Zenodo record:      $AOU_ZENODO_RECORD_ID
resume:                        ENABLED; PARTIAL FILES PRESERVED
transfer max-time:              ${CURL_TIMEOUT}s (0 = unlimited)
per-file attempts:              $CURL_FILE_ATTEMPTS
source cache version:           $SOURCE_CACHE_VERSION
atomic finalization:           ENABLED
source SHA-256:                RECORDED LOCALLY
script SHA-256:                $script_sha256
EOF

WORK_ROOT="$(mktemp -d "$TMP_BASE/work.XXXXXXXX")"
cleanup() {
  rm -rf "$WORK_ROOT"
}
trap cleanup EXIT

STAGE_OUT="$WORK_ROOT/stage_out"
STAGE_QC="$WORK_ROOT/stage_qc"
mkdir -p "$STAGE_OUT"/{manifests,policy,provenance,summary} "$STAGE_QC"

PY_HELPER="$STAGE_OUT/provenance/zenodo_manifest.py"
cat > "$PY_HELPER" <<'PY'
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--json", required=True)
    p.add_argument("--expected-record", required=True)
    p.add_argument("--expected-title", required=True)
    p.add_argument("--manifest", required=True)
    p.add_argument("--summary", required=True)
    args = p.parse_args()

    data = json.loads(Path(args.json).read_text(encoding="utf-8"))
    record_id = str(data.get("id", ""))
    title = str(data.get("metadata", {}).get("title", ""))
    if record_id != args.expected_record:
        raise SystemExit(f"record mismatch: expected {args.expected_record}, observed {record_id}")
    if title != args.expected_title:
        raise SystemExit(f"title mismatch: expected {args.expected_title!r}, observed {title!r}")

    files = data.get("files") or []
    if not files:
        raise SystemExit("Zenodo record contains no files")

    rows = []
    for item in files:
        key = str(item.get("key", ""))
        size = int(item.get("size", 0))
        checksum = str(item.get("checksum", ""))
        links = item.get("links") or {}
        url = str(links.get("content") or links.get("self") or "")
        if not key or size <= 0 or not checksum or not url:
            raise SystemExit(f"incomplete file metadata: {item!r}")
        if "\t" in key or "\n" in key:
            raise SystemExit(f"unsafe file key: {key!r}")
        rows.append((key, size, checksum, url))

    with Path(args.manifest).open("w", encoding="utf-8") as out:
        out.write("file_key\texpected_bytes\texpected_checksum\tdownload_url\n")
        for row in rows:
            out.write("\t".join(map(str, row)) + "\n")

    meta = data.get("metadata") or {}
    summary = {
        "record_id": record_id,
        "title": title,
        "version": meta.get("version"),
        "doi": data.get("doi"),
        "conceptdoi": data.get("conceptdoi"),
        "created": data.get("created"),
        "updated": data.get("updated"),
        "file_count": len(rows),
        "total_bytes": sum(r[1] for r in rows),
    }
    Path(args.summary).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
PY
python -m py_compile "$PY_HELPER"
implementation_sha256="$(sha256sum "$PY_HELPER" | awk '{print $1}')"

curl_common=(
  --fail --location --show-error --silent
  --connect-timeout 30
  --speed-time "$CURL_STALL_SECONDS" --speed-limit "$CURL_MIN_BYTES_PER_SEC"
  --user-agent "RNA-TR-Scout-reference-builder/0.3.2"
)
if [[ "$CURL_TIMEOUT" != "0" ]]; then
  curl_common+=(--max-time "$CURL_TIMEOUT")
fi

fetch_atomic() {
  local url="$1"
  local dest="$2"
  local expected_bytes="${3:-}"
  local expected_checksum="${4:-}"
  local tmp="${dest}.part"

  mkdir -p "$(dirname "$dest")"

  verify_file() {
    local f="$1"
    [[ -s "$f" ]] || return 1
    if [[ -n "$expected_bytes" && "$(stat -c '%s' "$f")" != "$expected_bytes" ]]; then
      return 1
    fi
    if [[ -n "$expected_checksum" ]]; then
      local algo="${expected_checksum%%:*}"
      local value="${expected_checksum#*:}"
      case "$algo" in
        md5) [[ "$(md5sum "$f" | awk '{print $1}')" == "$value" ]] || return 1 ;;
        sha256) [[ "$(sha256sum "$f" | awk '{print $1}')" == "$value" ]] || return 1 ;;
        *) echo "ERROR: unsupported checksum algorithm: $algo" >&2; return 1 ;;
      esac
    fi
    return 0
  }

  if verify_file "$dest"; then
    echo -e "DOWNLOAD_SKIP\t$dest"
    return 0
  fi

  if [[ -e "$dest" ]]; then
    mv "$dest" "${dest}.invalid.$(date -u +%Y%m%dT%H%M%SZ)"
  fi

  if [[ -n "$expected_bytes" && -e "$tmp" ]]; then
    local partial_bytes
    partial_bytes="$(stat -c '%s' "$tmp")"
    if (( partial_bytes > expected_bytes )); then
      mv "$tmp" "${tmp}.oversize.$(date -u +%Y%m%dT%H%M%SZ)"
    fi
  fi

  local attempt=0
  while ! verify_file "$tmp"; do
    attempt=$((attempt + 1))
    if (( attempt > CURL_FILE_ATTEMPTS )); then
      echo "ERROR: exhausted $CURL_FILE_ATTEMPTS attempts; partial file preserved: $tmp" >&2
      return 1
    fi

    local before_bytes=0
    [[ -e "$tmp" ]] && before_bytes="$(stat -c '%s' "$tmp")"
    echo -e "DOWNLOAD_ATTEMPT\t${attempt}/${CURL_FILE_ATTEMPTS}\tresume_bytes=${before_bytes}\t${dest}"

    local -a resume_args=()
    if [[ -s "$tmp" ]]; then
      resume_args=(--continue-at -)
    fi

    if ! curl "${curl_common[@]}" "${resume_args[@]}" --output "$tmp" "$url"; then
      local after_bytes=0
      [[ -e "$tmp" ]] && after_bytes="$(stat -c '%s' "$tmp")"
      echo -e "DOWNLOAD_RETRY\tattempt=${attempt}\tbefore=${before_bytes}\tafter=${after_bytes}\t${dest}" >&2
      sleep 10
      continue
    fi

    if ! verify_file "$tmp"; then
      local after_bytes=0
      [[ -e "$tmp" ]] && after_bytes="$(stat -c '%s' "$tmp")"
      if [[ -n "$expected_bytes" && "$after_bytes" == "$expected_bytes" ]]; then
        mv "$tmp" "${tmp}.checksum_mismatch.$(date -u +%Y%m%dT%H%M%SZ)"
        echo "WARN: complete-size file failed checksum; quarantined and restarting: $dest" >&2
      else
        echo -e "DOWNLOAD_INCOMPLETE\tattempt=${attempt}\tbytes=${after_bytes}\t${dest}" >&2
      fi
      sleep 10
    fi
  done

  mv "$tmp" "$dest"
  echo -e "DOWNLOAD_PASS\t$dest"
}

# 1) Resolve and freeze the pinned AoU Zenodo record metadata.
AOU_API_JSON="$AOU_ROOT/zenodo_record_${AOU_ZENODO_RECORD_ID}.json"
AOU_API_HEADERS="$AOU_ROOT/zenodo_record_${AOU_ZENODO_RECORD_ID}.headers.txt"
AOU_API_TMP="${AOU_API_JSON}.part"
if [[ ! -s "$AOU_API_JSON" ]]; then
  curl "${curl_common[@]}" --retry "$CURL_RETRIES" --retry-all-errors --retry-delay 5 \
    --dump-header "$AOU_API_HEADERS" --output "$AOU_API_TMP" "https://zenodo.org/api/records/${AOU_ZENODO_RECORD_ID}"
  python -m json.tool "$AOU_API_TMP" >/dev/null
  mv "$AOU_API_TMP" "$AOU_API_JSON"
fi

AOU_REMOTE_MANIFEST="$STAGE_OUT/manifests/aou_zenodo_remote_files.tsv"
AOU_RECORD_SUMMARY="$STAGE_OUT/summary/aou_zenodo_record_summary.json"
python "$PY_HELPER" \
  --json "$AOU_API_JSON" \
  --expected-record "$AOU_ZENODO_RECORD_ID" \
  --expected-title "$AOU_EXPECTED_TITLE" \
  --manifest "$AOU_REMOTE_MANIFEST" \
  --summary "$AOU_RECORD_SUMMARY"

# Download every file in the pinned record. This avoids a partial, pilot-specific reference bundle.
tail -n +2 "$AOU_REMOTE_MANIFEST" | while IFS=$'\t' read -r key expected_bytes expected_checksum url; do
  fetch_atomic "$url" "$AOU_ROOT/files/$key" "$expected_bytes" "$expected_checksum"
done

# Validate gzip members and inventory headers for tabular compressed files.
AOU_HEADER_INVENTORY="$STAGE_OUT/manifests/aou_tabular_header_inventory.tsv"
printf 'file\tbytes\tsha256\theader\n' > "$AOU_HEADER_INVENTORY"
find "$AOU_ROOT/files" -maxdepth 1 -type f -name '*.gz' -print0 | sort -z | while IFS= read -r -d '' f; do
  gzip -t "$f"
  header="$(gzip -cd "$f" | head -n 1 | tr '\t' '|' | tr -d '\r' || true)"
  printf '%s\t%s\t%s\t%s\n' \
    "$(basename "$f")" "$(stat -c '%s' "$f")" "$(sha256sum "$f" | awk '{print $1}')" "$header" \
    >> "$AOU_HEADER_INVENTORY"
done

# 2) TRExplorer v2: primary locus, boundary, motif, canonical motif, purity and source catalog.
TREX_BB="$TREX_ROOT/trexplorer.bb"
fetch_atomic "$TREXPLORER_URL" "$TREX_BB"
TREX_INFO="$TREX_ROOT/trexplorer.bigBedInfo.txt"
bigBedInfo "$TREX_BB" > "$TREX_INFO"
trex_items="$(awk '$1=="itemCount:" {gsub(",", "", $2); print $2}' "$TREX_INFO")"
[[ "$trex_items" == "$TREXPLORER_EXPECTED_ITEMS" ]] || {
  echo "ERROR: TRExplorer item count mismatch: expected $TREXPLORER_EXPECTED_ITEMS observed $trex_items" >&2
  exit 1
}
bigBedToBed "$TREX_BB" "$TREX_ROOT/trexplorer.bed"
[[ "$(wc -l < "$TREX_ROOT/trexplorer.bed")" == "$TREXPLORER_EXPECTED_ITEMS" ]] || {
  echo "ERROR: TRExplorer BED row count mismatch" >&2
  exit 1
}
gzip -n -f "$TREX_ROOT/trexplorer.bed"

# 3) 1KG Vienna ONT v1.1: independent long-read VNTR range and motif-composition source.
VIENNA_BB="$VIENNA_ROOT/viennaVntr.bb"
VIENNA_SUMMARY="$VIENNA_ROOT/vamos-summary.tsv"
VIENNA_LEGEND="$VIENNA_ROOT/summary-statistics-legend.txt"
VIENNA_README="$VIENNA_ROOT/vamos-vntr-genotyping_README.md"
fetch_atomic "$VIENNA_BB_URL" "$VIENNA_BB"
fetch_atomic "$VIENNA_SUMMARY_URL" "$VIENNA_SUMMARY"
fetch_atomic "$VIENNA_LEGEND_URL" "$VIENNA_LEGEND"
fetch_atomic "$VIENNA_README_URL" "$VIENNA_README"
VIENNA_INFO="$VIENNA_ROOT/viennaVntr.bigBedInfo.txt"
bigBedInfo "$VIENNA_BB" > "$VIENNA_INFO"
vienna_items="$(awk '$1=="itemCount:" {gsub(",", "", $2); print $2}' "$VIENNA_INFO")"
[[ "$vienna_items" == "$VIENNA_EXPECTED_ITEMS" ]] || {
  echo "ERROR: Vienna item count mismatch: expected $VIENNA_EXPECTED_ITEMS observed $vienna_items" >&2
  exit 1
}
summary_rows="$(awk 'END{print NR-1}' "$VIENNA_SUMMARY")"
[[ "$summary_rows" -ge 350000 ]] || {
  echo "ERROR: Vienna summary unexpectedly small: $summary_rows data rows" >&2
  exit 1
}

# 4) Disease-context catalog. It is not a population-range source.
STRCHIVE_BB="$DISEASE_ROOT/strchive.bb"
fetch_atomic "$STRCHIVE_URL" "$STRCHIVE_BB"
bigBedInfo "$STRCHIVE_BB" > "$DISEASE_ROOT/strchive.bigBedInfo.txt"

# Freeze source files with local SHA-256 and byte counts.
LOCAL_MANIFEST="$STAGE_OUT/manifests/local_source_artifact_manifest.tsv"
printf 'resource_role\tsource_name\tlocal_path\tbytes\tsha256\n' > "$LOCAL_MANIFEST"
while IFS=$'\t' read -r role name path; do
  [[ -s "$path" ]] || continue
  printf '%s\t%s\t%s\t%s\t%s\n' \
    "$role" "$name" "$path" "$(stat -c '%s' "$path")" "$(sha256sum "$path" | awk '{print $1}')" \
    >> "$LOCAL_MANIFEST"
done <<EOF
CATALOG_MOTIF_PRIMARY	TRExplorer_v2_BigBed	$TREX_BB
CATALOG_MOTIF_PRIMARY	TRExplorer_v2_BED_GZ	$TREX_ROOT/trexplorer.bed.gz
POPULATION_VNTR_SECONDARY	Vienna_ONT_v1.1_BigBed	$VIENNA_BB
POPULATION_VNTR_SECONDARY	Vienna_ONT_v1.1_summary	$VIENNA_SUMMARY
POPULATION_VNTR_SECONDARY	Vienna_ONT_v1.1_legend	$VIENNA_LEGEND
DISEASE_CONTEXT	STRchive_BigBed	$STRCHIVE_BB
EOF

# Add every AoU record file to the local manifest.
find "$AOU_ROOT/files" -maxdepth 1 -type f -print0 | sort -z | while IFS= read -r -d '' f; do
  printf '%s\t%s\t%s\t%s\t%s\n' \
    "POPULATION_LENGTH_LPS_PRIMARY" "AoU_Zenodo_$(basename "$f")" "$f" \
    "$(stat -c '%s' "$f")" "$(sha256sum "$f" | awk '{print $1}')" \
    >> "$LOCAL_MANIFEST"
done

POLICY="$STAGE_OUT/policy/rnatr_population_reference_policy_v0.1.0.tsv"
cat > "$POLICY" <<'EOF'
priority_layer	resource	role	measurement_use	automatic_use_policy
1	TRExplorer v2	Primary GRCh38 locus/boundary/motif catalog	referenceMotif; canonicalMotif; motifSize; reference copy number; purity; source	Use for locus addressability and motif priors; verify RNA tract from raw read sequence
2	AoU HiFi validation 2102	Primary DNA long-read population distribution	allele length percentiles; LPS per locus; LPS per motif	Primary population context when exact or validated safe crosswalk and schema QC pass
3	AoU HiFi discovery 543	High-depth HiFi confirmation	allele length and LPS distributions	Use as independent HiFi confirmation; do not silently pool with validation cohort
4	AoU/1KGP ONT replication 500	Cross-platform ONT confirmation	allele length and LPS distributions	Use as replication; caller/platform-specific fields retained
5	1KG Vienna ONT 1019	Secondary long-VNTR population source	repeat-unit-count range/median; bp-length range/median; motif composition	Use for VAMOS-addressable VNTRs; do not substitute its boundary/motif model without reconciliation
6	HPRC256 within TRExplorer v2	Additional HiFi allele histogram	repeat copy-number histogram	Use as secondary population evidence where histogram exists
7	STRchive	Disease-specific context	pathogenic motif and published thresholds	Use for known disease loci only; not a general population distribution
8	TR-Atlas cached pilot subset	Supplementary short-read context	frequency bins for exact/validated loci only	No further live crawl; never primary for long repeat size or motif decomposition
RNA	RNA-TR-Scout raw-read measurement	Observed RNA molecule evidence	raw-read tract length; motif decomposition; interruptions; censoring	Catalog motifs are priors only; final RNA measurement comes from the RNA read sequence
EOF

QC_FILE="$STAGE_QC/bulk_longread_population_reference_acquisition.qc.tsv"
aou_file_count="$(awk 'END{print NR-1}' "$AOU_REMOTE_MANIFEST")"
aou_total_bytes="$(python - <<PY
import json
print(json.load(open('$AOU_RECORD_SUMMARY'))['total_bytes'])
PY
)"
aou_gz_count="$(find "$AOU_ROOT/files" -maxdepth 1 -type f -name '*.gz' | wc -l)"

cat > "$QC_FILE" <<EOF
metric	value
stage_version	$STAGE_VERSION
retrieved_at_utc	$retrieved_at_utc
rnatr_scout_version	$installed_version
script_sha256	$script_sha256
implementation_sha256	$implementation_sha256
aou_zenodo_record_id	$AOU_ZENODO_RECORD_ID
aou_record_file_count	$aou_file_count
aou_record_total_expected_bytes	$aou_total_bytes
aou_gzip_file_count	$aou_gz_count
trexplorer_item_count	$trex_items
trexplorer_expected_item_count	$TREXPLORER_EXPECTED_ITEMS
vienna_ont_item_count	$vienna_items
vienna_ont_expected_item_count	$VIENNA_EXPECTED_ITEMS
vienna_summary_data_rows	$summary_rows
tr_atlas_role	SUPPLEMENTARY_ONLY_NO_ADDITIONAL_LIVE_CRAWL
population_primary	AOU_HIFI_VALIDATION_2102
catalog_motif_primary	TREXPLORER_V2
population_secondary_long_vntr	VIENNA_ONT_V1.1_1019
final_ranking_executed	0
specialized_motif_4513_started	false
stage6z_bulk_reference_acquisition_status	PASS_READY_FOR_CROSSWALK_AND_COVERAGE_AUDIT
EOF

# Provenance copies.
cp -f "$0" "$STAGE_OUT/provenance/$(basename "$0")"
cp -f "$AOU_API_JSON" "$STAGE_OUT/provenance/"
cp -f "$AOU_API_HEADERS" "$STAGE_OUT/provenance/" 2>/dev/null || true

# Atomic result/QC installation keyed by script SHA and timestamp.
FINAL_TAG="${retrieved_at_utc//[-:]/}"
FINAL_TAG="${FINAL_TAG%Z}Z_${script_sha256:0:12}"
FINAL_OUT="$OUT_BASE/$FINAL_TAG"
FINAL_QC="$QC_BASE/$FINAL_TAG"
[[ ! -e "$FINAL_OUT" && ! -e "$FINAL_QC" ]] || {
  echo "ERROR: immutable output already exists: $FINAL_TAG" >&2
  exit 1
}
mkdir -p "$FINAL_OUT" "$FINAL_QC"
cp -a "$STAGE_OUT/." "$FINAL_OUT/"
cp -a "$STAGE_QC/." "$FINAL_QC/"

ln -sfn "$FINAL_OUT" "$LATEST_RESULT_LINK"
ln -sfn "$FINAL_QC" "$LATEST_QC_LINK"
cp -f "$0" "$SCRIPT_DEST"

cat <<EOF
STAGE6Z_STATUS	PASS_READY_FOR_CROSSWALK_AND_COVERAGE_AUDIT
CATALOG_MOTIF_PRIMARY	TRExplorer_v2
POPULATION_PRIMARY	AoU_HiFi_validation_2102
POPULATION_CONFIRMATION	AoU_HiFi_discovery_543;AoU_ONT_replication_500;HPRC256
LONG_VNTR_SECONDARY	Vienna_ONT_v1.1_1019
TRATLAS_ROLE	SUPPLEMENTARY_ONLY_NO_ADDITIONAL_LIVE_CRAWL
AOU_FILES	$aou_file_count
TREXPLORER_ITEMS	$trex_items
VIENNA_ITEMS	$vienna_items
QC	$FINAL_QC/bulk_longread_population_reference_acquisition.qc.tsv

===== STAGE 6Z FINAL QC =====
EOF
column -ts $'\t' "$FINAL_QC/bulk_longread_population_reference_acquisition.qc.tsv"

cat <<EOF

===== REFERENCE POLICY =====
EOF
column -ts $'\t' "$FINAL_OUT/policy/rnatr_population_reference_policy_v0.1.0.tsv"

cat <<EOF

===== OUTPUT =====
Installed script:          $SCRIPT_DEST
Bulk source root:          $SOURCE_ROOT
AoU source:                $AOU_ROOT
TRExplorer source:         $TREX_ROOT
Vienna ONT source:         $VIENNA_ROOT
Disease context source:    $DISEASE_ROOT
Result:                    $FINAL_OUT
QC:                        $FINAL_QC/bulk_longread_population_reference_acquisition.qc.tsv
Local artifact manifest:   $FINAL_OUT/manifests/local_source_artifact_manifest.tsv
Reference policy:          $FINAL_OUT/policy/rnatr_population_reference_policy_v0.1.0.tsv
Latest result link:        $LATEST_RESULT_LINK
Latest QC link:            $LATEST_QC_LINK

This stage downloads and freezes bulk reference sources only.
It does not crosswalk the 11,042 RNA loci, compare population distributions,
run final candidate ranking, or start specialized motif 4,513 processing.
EOF
