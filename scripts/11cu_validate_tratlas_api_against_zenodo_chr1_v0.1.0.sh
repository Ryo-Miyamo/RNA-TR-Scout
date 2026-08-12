#!/usr/bin/env bash
set -euo pipefail

VALIDATION_VERSION="rnatr_tratlas_api_zenodo_crossvalidation_v0.1.0"
RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"
API_BASE="https://wlcb.oit.uci.edu/TRgnomAD/api"
EXPECTED_POPULATIONS=5
SELECTED_TR_IDS=5
REQUEST_DELAY_SECONDS=1

: "${PROJECT_ROOT:?PROJECT_ROOT is not set; source config/paths.env first}"

ZENODO_SCHEMA_ROOT="$PROJECT_ROOT/results/11_tratlas_primary_frequency_schema/$RUN_ID/rnatr_tratlas_primary_frequency_schema_v0.1.1"
ZENODO_SCHEMA_QC="$PROJECT_ROOT/qc/11_tratlas_primary_frequency_schema/$RUN_ID/rnatr_tratlas_primary_frequency_schema_v0.1.1/tratlas_primary_frequency_schema.qc.tsv"
ZENODO_ALLELES="$ZENODO_SCHEMA_ROOT/tratlas_primary_frequency.normalized_alleles.tsv.gz"

OUT_ROOT="$PROJECT_ROOT/results/11_tratlas_api_zenodo_crossvalidation/$RUN_ID/$VALIDATION_VERSION"
QC_ROOT="$PROJECT_ROOT/qc/11_tratlas_api_zenodo_crossvalidation/$RUN_ID/$VALIDATION_VERSION"
PROV_ROOT="$OUT_ROOT/provenance"
RAW_ROOT="$OUT_ROOT/raw_api_json"
TABLE_ROOT="$OUT_ROOT/tables"
SUMMARY_ROOT="$OUT_ROOT/summary"
CONTRACT_ROOT="$OUT_ROOT/contracts"

mkdir -p \
  "$OUT_ROOT" "$QC_ROOT" "$PROV_ROOT" "$RAW_ROOT" \
  "$TABLE_ROOT" "$SUMMARY_ROOT" "$CONTRACT_ROOT"

for path in "$ZENODO_SCHEMA_QC" "$ZENODO_ALLELES"; do
  [[ -s "$path" ]] || {
    echo "ERROR: missing or empty prerequisite: $path" >&2
    exit 1
  }
done

for tool in python curl gzip sha256sum; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "ERROR: required tool unavailable: $tool" >&2
    exit 1
  }
done

metric() {
  local file="$1"
  local key="$2"
  awk -F $'\t' -v key="$key" \
    '$1 == key {print $2; found=1; exit} END {if (!found) print "."}' \
    "$file"
}

[[ "$(metric "$ZENODO_SCHEMA_QC" tratlas_primary_frequency_schema_status)" == "PASS" ]] || {
  echo "ERROR: pinned Zenodo frequency schema source is not PASS" >&2
  exit 1
}

gzip -t "$ZENODO_ALLELES"

SELECTOR="$PROV_ROOT/select_chr1_crossvalidation_tr_ids.py"
cat > "$SELECTOR" <<'PY'
from __future__ import annotations

import csv
import gzip
import sys
from collections import defaultdict
from pathlib import Path

source = Path(sys.argv[1])
destination = Path(sys.argv[2])
selected_count = int(sys.argv[3])

expected = {
    "African",
    "East Asian",
    "European",
    "Hispanic",
    "South Asian",
}

by_tr_population: dict[str, dict[str, list[dict[str, str]]]] = defaultdict(
    lambda: defaultdict(list)
)
coordinates: dict[str, tuple[str, int, int]] = {}

with gzip.open(source, "rt", encoding="utf-8", newline="") as handle:
    reader = csv.DictReader(handle, delimiter="\t")
    required = {
        "population_group",
        "tr_id",
        "source_locator_type",
        "chrom",
        "start_0based_as_reported",
        "end_0based_exclusive_as_reported",
        "allele_repeat_units",
        "reported_frequency",
    }
    missing = required - set(reader.fieldnames or [])
    if missing:
        raise SystemExit(f"missing normalized fields: {sorted(missing)}")

    for row in reader:
        if row["source_locator_type"] != "GENOMIC_COORDINATE":
            continue
        if row["chrom"] != "chr1":
            continue
        tr_id = row["tr_id"]
        population = row["population_group"]
        by_tr_population[tr_id][population].append(row)
        coordinates[tr_id] = (
            row["chrom"],
            int(row["start_0based_as_reported"]),
            int(row["end_0based_exclusive_as_reported"]),
        )

eligible = []
for tr_id, population_rows in by_tr_population.items():
    if set(population_rows) != expected:
        continue
    sums = {
        population: sum(
            float(row["reported_frequency"])
            for row in rows
        )
        for population, rows in population_rows.items()
    }
    if min(sums.values()) < 0.95:
        continue
    chrom, start, end = coordinates[tr_id]
    eligible.append((start, end, tr_id, sums))

eligible.sort()
if len(eligible) < selected_count:
    raise SystemExit(
        f"not enough eligible common TR IDs: {len(eligible)}"
    )

if selected_count == 1:
    indexes = [len(eligible) // 2]
else:
    indexes = [
        round(index * (len(eligible) - 1) / (selected_count - 1))
        for index in range(selected_count)
    ]

selected = [eligible[index] for index in indexes]
if len({row[2] for row in selected}) != selected_count:
    raise SystemExit("selection did not produce unique TR IDs")

destination.parent.mkdir(parents=True, exist_ok=True)
with destination.open("w", encoding="utf-8", newline="") as handle:
    writer = csv.writer(
        handle,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writerow(
        [
            "selection_order",
            "tr_id",
            "chrom",
            "start_0based",
            "end_0based_exclusive",
            "zenodo_population_count",
            "minimum_zenodo_frequency_sum",
            "maximum_zenodo_frequency_sum",
        ]
    )
    for order, (start, end, tr_id, sums) in enumerate(
        selected,
        start=1,
    ):
        writer.writerow(
            [
                order,
                tr_id,
                "chr1",
                start,
                end,
                len(sums),
                f"{min(sums.values()):.15g}",
                f"{max(sums.values()):.15g}",
            ]
        )

print("SELECTOR_STATUS\tPASS")
print(f"ELIGIBLE_COMMON_TR_IDS\t{len(eligible)}")
print(f"SELECTED_TR_IDS\t{len(selected)}")
print(
    "SELECTED_IDS\t"
    + ";".join(row[2] for row in selected)
)
PY

python -m py_compile "$SELECTOR"

SELECTED_TABLE="$TABLE_ROOT/selected_chr1_crossvalidation_tr_ids.tsv"
python "$SELECTOR" \
  "$ZENODO_ALLELES" \
  "$SELECTED_TABLE" \
  "$SELECTED_TR_IDS"

echo
echo "===== SELECTED CHR1 TR IDS ====="
column -ts $'\t' "$SELECTED_TABLE"

echo
echo "===== DOWNLOAD MAIN-POPULATION API JSON ====="
tail -n +2 "$SELECTED_TABLE" \
  | while IFS=$'\t' read -r \
      selection_order tr_id chrom start end population_count min_sum max_sum
    do
      url="${API_BASE}/main_population_All.php?trId=${tr_id}&datasetId=main_pop_test"
      echo "request ${selection_order}/${SELECTED_TR_IDS}: ${tr_id}"

      curl \
        --fail \
        --location \
        --compressed \
        --retry 3 \
        --retry-delay 2 \
        --connect-timeout 20 \
        --max-time 120 \
        -A "RNA-TR-Scout/${VALIDATION_VERSION} crossvalidation" \
        -H 'Accept: application/json,text/plain,*/*' \
        -D "$RAW_ROOT/${tr_id}.main_population.headers.txt" \
        "$url" \
        -o "$RAW_ROOT/${tr_id}.main_population.json"

      python -m json.tool \
        "$RAW_ROOT/${tr_id}.main_population.json" \
        >/dev/null

      sleep "$REQUEST_DELAY_SECONDS"
    done

sha256sum "$RAW_ROOT"/*.main_population.json \
  > "$PROV_ROOT/api_response.sha256.tsv"

PY_IMPL="$PROV_ROOT/rnatr_tratlas_api_zenodo_crossvalidation_v0.1.0.py"
cat > "$PY_IMPL" <<'PY'
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

VERSION = "rnatr_tratlas_api_zenodo_crossvalidation_v0.1.0"

API_SERIES_TO_POPULATION = {
    "data2": "African",
    "data3": "South Asian",
    "data4": "East Asian",
    "data5": "European",
    "data6": "Hispanic",
}


class ContractError(RuntimeError):
    pass


def open_text(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", newline="")
    return path.open("rt", encoding="utf-8", newline="")


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
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=str(path.parent),
    )
    os.close(fd)
    try:
        with open(tmp_name, "wt", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=fields,
                delimiter="\t",
                lineterminator="\n",
                extrasaction="raise",
            )
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {field: row.get(field, ".") for field in fields}
                )
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def coerce_finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise ContractError(f"{field}: boolean is not numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ContractError(
            f"{field}: invalid numeric value {value!r}"
        ) from exc
    if not math.isfinite(number):
        raise ContractError(
            f"{field}: non-finite numeric value {value!r}"
        )
    return number


def parse_api_series(
    payload: Mapping[str, Any],
    key: str,
) -> dict[int, float]:
    series = payload.get(key)
    if not isinstance(series, list):
        raise ContractError(f"API series missing or not array: {key}")

    parsed: dict[int, float] = {}
    for item in series:
        if not isinstance(item, dict):
            raise ContractError(f"{key}: non-object point {item!r}")
        value = item.get("value")
        if not isinstance(value, list) or len(value) < 2:
            raise ContractError(f"{key}: malformed value {value!r}")
        allele_float = coerce_finite_number(
            value[0],
            f"{key} allele",
        )
        if not allele_float.is_integer():
            raise ContractError(
                f"{key}: noninteger allele repeat unit {allele_float}"
            )
        allele = int(allele_float)
        frequency = coerce_finite_number(
            value[1],
            f"{key} frequency",
        )
        if frequency < 0 or frequency > 1 + 1e-12:
            raise ContractError(
                f"{key}: frequency outside [0,1]: {frequency}"
            )
        if allele in parsed:
            raise ContractError(
                f"{key}: duplicate allele repeat unit {allele}"
            )
        parsed[allele] = frequency
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zenodo-alleles", type=Path, required=True)
    parser.add_argument("--selected-table", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--out-root", type=Path, required=True)
    parser.add_argument("--qc-root", type=Path, required=True)
    parser.add_argument("--expected-tr-ids", type=int, required=True)
    parser.add_argument("--expected-populations", type=int, required=True)
    parser.add_argument("--script-sha256", required=True)
    parser.add_argument("--implementation-sha256", required=True)
    args = parser.parse_args()

    table_root = args.out_root / "tables"
    summary_root = args.out_root / "summary"
    contract_root = args.out_root / "contracts"
    for root in (
        args.out_root,
        args.qc_root,
        table_root,
        summary_root,
        contract_root,
    ):
        root.mkdir(parents=True, exist_ok=True)

    selected_fields, selected_rows = read_tsv(args.selected_table)
    required_selected = {
        "selection_order",
        "tr_id",
        "chrom",
        "start_0based",
        "end_0based_exclusive",
    }
    missing = required_selected - set(selected_fields)
    if missing:
        raise ContractError(
            f"selected table missing fields: {sorted(missing)}"
        )
    if len(selected_rows) != args.expected_tr_ids:
        raise ContractError("selected TR ID count mismatch")

    selected_ids = {row["tr_id"] for row in selected_rows}
    if len(selected_ids) != len(selected_rows):
        raise ContractError("duplicate selected TR IDs")

    zenodo_fields, zenodo_rows = read_tsv(args.zenodo_alleles)
    required_zenodo = {
        "population_group",
        "tr_id",
        "allele_repeat_units",
        "reported_frequency",
    }
    missing = required_zenodo - set(zenodo_fields)
    if missing:
        raise ContractError(
            f"Zenodo normalized table missing fields: {sorted(missing)}"
        )

    zenodo: dict[tuple[str, str], dict[int, float]] = defaultdict(dict)
    for row in zenodo_rows:
        tr_id = row["tr_id"]
        if tr_id not in selected_ids:
            continue
        population = row["population_group"]
        allele = int(row["allele_repeat_units"])
        frequency = float(row["reported_frequency"])
        key = (tr_id, population)
        if allele in zenodo[key]:
            raise ContractError(
                f"duplicate Zenodo allele: {tr_id}/{population}/{allele}"
            )
        zenodo[key][allele] = frequency

    comparison_rows: list[dict[str, object]] = []
    group_summary_rows: list[dict[str, object]] = []
    mismatch_counts = Counter()

    for selected in selected_rows:
        tr_id = selected["tr_id"]
        api_path = (
            args.raw_root / f"{tr_id}.main_population.json"
        )
        if not api_path.is_file():
            raise ContractError(f"missing API response: {api_path}")
        with api_path.open("rt", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ContractError(
                f"API payload root is not object: {tr_id}"
            )

        for series_key, population in API_SERIES_TO_POPULATION.items():
            api = parse_api_series(payload, series_key)
            zeno = zenodo.get((tr_id, population))
            if zeno is None:
                raise ContractError(
                    f"missing Zenodo distribution: {tr_id}/{population}"
                )

            alleles = sorted(set(api) | set(zeno))
            exact_frequency_rows = 0
            tolerance_frequency_rows = 0
            group_mismatches = 0

            for allele in alleles:
                api_value = api.get(allele)
                zenodo_value = zeno.get(allele)
                if api_value is None:
                    status = "API_MISSING_ALLELE"
                    difference = "."
                    group_mismatches += 1
                    mismatch_counts[status] += 1
                elif zenodo_value is None:
                    status = "ZENODO_MISSING_ALLELE"
                    difference = "."
                    group_mismatches += 1
                    mismatch_counts[status] += 1
                else:
                    delta = api_value - zenodo_value
                    difference = f"{delta:.17g}"
                    if api_value == zenodo_value:
                        status = "EXACT_FLOAT_MATCH"
                        exact_frequency_rows += 1
                    elif math.isclose(
                        api_value,
                        zenodo_value,
                        rel_tol=1e-12,
                        abs_tol=1e-15,
                    ):
                        status = "NUMERIC_TOLERANCE_MATCH"
                        tolerance_frequency_rows += 1
                    else:
                        status = "FREQUENCY_MISMATCH"
                        group_mismatches += 1
                        mismatch_counts[status] += 1

                comparison_rows.append(
                    {
                        "selection_order": selected[
                            "selection_order"
                        ],
                        "tr_id": tr_id,
                        "chrom": selected["chrom"],
                        "start_0based": selected["start_0based"],
                        "end_0based_exclusive": selected[
                            "end_0based_exclusive"
                        ],
                        "series_key": series_key,
                        "population": population,
                        "allele_repeat_units": allele,
                        "api_frequency": (
                            f"{api_value:.17g}"
                            if api_value is not None
                            else "."
                        ),
                        "zenodo_frequency": (
                            f"{zenodo_value:.17g}"
                            if zenodo_value is not None
                            else "."
                        ),
                        "api_minus_zenodo": difference,
                        "comparison_status": status,
                    }
                )

            group_summary_rows.append(
                {
                    "selection_order": selected[
                        "selection_order"
                    ],
                    "tr_id": tr_id,
                    "population": population,
                    "api_allele_rows": len(api),
                    "zenodo_allele_rows": len(zeno),
                    "union_allele_rows": len(alleles),
                    "exact_float_match_rows": exact_frequency_rows,
                    "numeric_tolerance_match_rows": (
                        tolerance_frequency_rows
                    ),
                    "mismatch_rows": group_mismatches,
                    "api_frequency_sum": f"{sum(api.values()):.15g}",
                    "zenodo_frequency_sum": (
                        f"{sum(zeno.values()):.15g}"
                    ),
                    "frequency_sum_delta": (
                        f"{sum(api.values()) - sum(zeno.values()):.17g}"
                    ),
                    "group_validation_status": (
                        "PASS_IDENTICAL_DISTRIBUTION"
                        if group_mismatches == 0
                        else "FAIL_DISTRIBUTION_MISMATCH"
                    ),
                }
            )

    expected_groups = (
        args.expected_tr_ids * args.expected_populations
    )
    if len(group_summary_rows) != expected_groups:
        raise ContractError("population group comparison count mismatch")

    failed_groups = sum(
        row["group_validation_status"]
        != "PASS_IDENTICAL_DISTRIBUTION"
        for row in group_summary_rows
    )
    validation_status = (
        "PASS"
        if failed_groups == 0
        else "FAIL"
    )

    atomic_write_tsv(
        table_root / "api_vs_zenodo.allele_frequency_comparison.tsv",
        list(comparison_rows[0].keys()),
        comparison_rows,
    )
    atomic_write_tsv(
        summary_root / "api_vs_zenodo.population_group_summary.tsv",
        list(group_summary_rows[0].keys()),
        group_summary_rows,
    )

    registry_rows = [
        {
            "source_id": "TRATLAS_CELL2024_RESOURCE",
            "source_role": "PARENT_RESOURCE",
            "versioning_status": (
                "PUBLICATION_DEFINED_RESOURCE_LIVE_BROWSER"
            ),
            "scope": (
                "GENOME_WIDE_TR_RESOURCE_BROWSER_AND_BACKEND"
            ),
            "allowed_use": (
                "RESOURCE_IDENTITY_AND_PARENT_PROVENANCE"
            ),
        },
        {
            "source_id": (
                "TRATLAS_ZENODO_10806728_PRIMARY_FREQUENCY_PREFIX_EXPORTS"
            ),
            "source_role": "PINNED_VERSIONED_VALIDATION_SOURCE",
            "versioning_status": (
                "PINNED_VERSION_DOI_10.5281/ZENODO.10806728"
            ),
            "scope": (
                "FIVE_10000_ROW_PRIMARY_POPULATION_FILES_CHR1_PREFIX_ONLY"
            ),
            "allowed_use": (
                "SCHEMA_VALIDATION_AND_EXACT_LOCUS_CONTEXT_WITHIN_OBSERVED_SCOPE"
            ),
        },
        {
            "source_id": "TRATLAS_PUBLIC_BROWSER_API_MAIN_POPULATION",
            "source_role": "LIVE_LOCUS_FREQUENCY_API",
            "versioning_status": (
                "UNVERSIONED_LIVE_ENDPOINT_RESPONSE_SHA256_REQUIRED"
            ),
            "scope": (
                "TR_ID_SPECIFIC_ALL_PLUS_FIVE_PRIMARY_POPULATIONS"
            ),
            "allowed_use": (
                "PROVISIONAL_AFTER_ZENODO_CROSSVALIDATION_AND_CACHED_RESPONSE_PINNING"
            ),
        },
        {
            "source_id": "TRATLAS_PUBLIC_BROWSER_API_SUB_POPULATION",
            "source_role": "LIVE_LOCUS_FREQUENCY_API",
            "versioning_status": (
                "UNVERSIONED_LIVE_ENDPOINT_RESPONSE_SHA256_REQUIRED"
            ),
            "scope": (
                "TR_ID_SPECIFIC_ALL_PLUS_FIFTEEN_SUBPOPULATIONS"
            ),
            "allowed_use": (
                "PROVISIONAL_SCHEMA_AUDIT_REQUIRED_DENOMINATOR_UNAVAILABLE"
            ),
        },
        {
            "source_id": "TRATLAS_ZENODO_10806728_TRDS",
            "source_role": "PINNED_POPULATION_DISTANCE_SOURCE",
            "versioning_status": (
                "PINNED_VERSION_DOI_10.5281/ZENODO.10806728"
            ),
            "scope": (
                "GENOME_WIDE_TR_ID_POPULATION_DISTANCE_NOT_ALLELE_DISTRIBUTION"
            ),
            "allowed_use": (
                "DISPARITY_CONTEXT_ONLY_NOT_P95_P99_MAX_RECONSTRUCTION"
            ),
        },
    ]
    atomic_write_tsv(
        summary_root / "tratlas_source_registry.corrected.tsv",
        [
            "source_id",
            "source_role",
            "versioning_status",
            "scope",
            "allowed_use",
        ],
        registry_rows,
    )

    atomic_write_tsv(
        contract_root / "tratlas_api_use_policy.tsv",
        ["policy_id", "rule", "status", "rationale"],
        [
            {
                "policy_id": "TA01",
                "rule": (
                    "CACHE_EVERY_API_RESPONSE_WITH_URL_TIMESTAMP_HEADERS_AND_SHA256"
                ),
                "status": "FROZEN",
                "rationale": (
                    "The public browser API is live and does not expose "
                    "an explicit version identifier."
                ),
            },
            {
                "policy_id": "TA02",
                "rule": (
                    "VALIDATE_PRIMARY_POPULATION_API_AGAINST_PINNED_ZENODO_ROWS"
                ),
                "status": (
                    "PASS" if validation_status == "PASS" else "FAIL"
                ),
                "rationale": (
                    "A live API may be used only after exact or numerical "
                    "agreement with the version-pinned chr1 source is demonstrated."
                ),
            },
            {
                "policy_id": "TA03",
                "rule": (
                    "NORMALIZE_FREQUENCY_BY_REPORTED_SUM_FOR_CDF_WITH_SUM_RECORDED"
                ),
                "status": "PROVISIONAL",
                "rationale": (
                    "Most API series sum slightly below one; every locus-"
                    "population sum must be retained and low-sum series flagged."
                ),
            },
            {
                "policy_id": "TA04",
                "rule": (
                    "DO_NOT_INFER_ALLELE_COUNTS_OR_ZERO_TAIL_CONFIDENCE_WITHOUT_DENOMINATOR"
                ),
                "status": "FROZEN",
                "rationale": (
                    "The frequency endpoints do not expose a verified allele denominator."
                ),
            },
            {
                "policy_id": "TA05",
                "rule": (
                    "NO_HIGH_VOLUME_RETRIEVAL_BEFORE_TR_ID_CROSSWALK_AND_RATE_POLICY"
                ),
                "status": "HOLD",
                "rationale": (
                    "First determine which of the 11042 RNA loci safely "
                    "map to TR IDs and request only required loci at a conservative rate."
                ),
            },
            {
                "policy_id": "TA06",
                "rule": "FINAL_RANKING_REMAINS_BLOCKED",
                "status": "HOLD",
                "rationale": (
                    "Population coverage, source versioning, denominators, "
                    "RNA controls, and calibrated weights remain incomplete."
                ),
            },
        ],
    )

    qc_rows = [
        {"metric": "validation_version", "value": VERSION},
        {
            "metric": "selected_chr1_tr_ids",
            "value": args.expected_tr_ids,
        },
        {
            "metric": "primary_population_groups_per_tr",
            "value": args.expected_populations,
        },
        {
            "metric": "population_group_comparisons",
            "value": len(group_summary_rows),
        },
        {
            "metric": "allele_frequency_comparison_rows",
            "value": len(comparison_rows),
        },
        {
            "metric": "failed_population_group_comparisons",
            "value": failed_groups,
        },
        {
            "metric": "api_missing_allele_rows",
            "value": mismatch_counts["API_MISSING_ALLELE"],
        },
        {
            "metric": "zenodo_missing_allele_rows",
            "value": mismatch_counts["ZENODO_MISSING_ALLELE"],
        },
        {
            "metric": "frequency_mismatch_rows",
            "value": mismatch_counts["FREQUENCY_MISMATCH"],
        },
        {
            "metric": "api_zenodo_crossvalidation_status",
            "value": validation_status,
        },
        {
            "metric": "api_versioning_status",
            "value": (
                "UNVERSIONED_LIVE_ENDPOINT_RESPONSES_PINNED_BY_SHA256"
            ),
        },
        {
            "metric": "population_denominator_available",
            "value": "false",
        },
        {
            "metric": "bulk_retrieval_executed",
            "value": 0,
        },
        {
            "metric": "final_candidate_ranking_executed",
            "value": 0,
        },
        {
            "metric": "script_sha256",
            "value": args.script_sha256,
        },
        {
            "metric": "implementation_sha256",
            "value": args.implementation_sha256,
        },
        {
            "metric": "zenodo_normalized_alleles_sha256",
            "value": sha256_file(args.zenodo_alleles),
        },
    ]
    qc_path = (
        args.qc_root / "tratlas_api_zenodo_crossvalidation.qc.tsv"
    )
    atomic_write_tsv(qc_path, ["metric", "value"], qc_rows)

    print(
        "TRATLAS_API_ZENODO_CROSSVALIDATION_STATUS\t"
        f"{validation_status}"
    )
    print(f"SELECTED_TR_IDS\t{args.expected_tr_ids}")
    print(f"POPULATION_GROUP_COMPARISONS\t{len(group_summary_rows)}")
    print(f"FAILED_GROUPS\t{failed_groups}")
    print(f"FREQUENCY_MISMATCH_ROWS\t{mismatch_counts['FREQUENCY_MISMATCH']}")
    print("BULK_RETRIEVAL\tNOT_RUN")
    print("FINAL_RANKING\tNOT_RUN")
    print(f"QC\t{qc_path}")

    if validation_status != "PASS":
        raise SystemExit(
            "TR-Atlas API and pinned Zenodo frequency distributions differ"
        )


if __name__ == "__main__":
    main()
PY

python -m py_compile "$PY_IMPL"
script_sha256="$(sha256sum "$0" | awk '{print $1}')"
implementation_sha256="$(sha256sum "$PY_IMPL" | awk '{print $1}')"

echo
echo "===== TR-ATLAS API/ZENODO CROSSVALIDATION PREFLIGHT ====="
echo "pinned Zenodo schema:      $(metric "$ZENODO_SCHEMA_QC" tratlas_primary_frequency_schema_status)"
echo "pinned Zenodo version:     $(metric "$ZENODO_SCHEMA_QC" source_version_doi)"
echo "selected TR IDs:           $SELECTED_TR_IDS"
echo "populations per TR:        $EXPECTED_POPULATIONS"
echo "API requests:              $SELECTED_TR_IDS"
echo "request delay:             ${REQUEST_DELAY_SECONDS}s"
echo "bulk retrieval:            NO"
echo "final ranking:             NO"
echo "implementation sha256:     $implementation_sha256"

python "$PY_IMPL" \
  --zenodo-alleles "$ZENODO_ALLELES" \
  --selected-table "$SELECTED_TABLE" \
  --raw-root "$RAW_ROOT" \
  --out-root "$OUT_ROOT" \
  --qc-root "$QC_ROOT" \
  --expected-tr-ids "$SELECTED_TR_IDS" \
  --expected-populations "$EXPECTED_POPULATIONS" \
  --script-sha256 "$script_sha256" \
  --implementation-sha256 "$implementation_sha256"

echo
echo "===== FINAL QC ====="
column -ts $'\t' \
  "$QC_ROOT/tratlas_api_zenodo_crossvalidation.qc.tsv"

echo
echo "===== POPULATION GROUP COMPARISON ====="
column -ts $'\t' \
  "$SUMMARY_ROOT/api_vs_zenodo.population_group_summary.tsv"

echo
echo "===== CORRECTED TR-ATLAS SOURCE REGISTRY ====="
column -ts $'\t' \
  "$SUMMARY_ROOT/tratlas_source_registry.corrected.tsv"

echo
echo "===== TR-ATLAS API USE POLICY ====="
column -ts $'\t' \
  "$CONTRACT_ROOT/tratlas_api_use_policy.tsv"

echo
echo "===== OUTPUT ====="
echo "Validation root: $OUT_ROOT"
echo "QC:              $QC_ROOT/tratlas_api_zenodo_crossvalidation.qc.tsv"
echo "Selected IDs:    $SELECTED_TABLE"
echo "Group summary:   $SUMMARY_ROOT/api_vs_zenodo.population_group_summary.tsv"
echo "Allele compare:  $TABLE_ROOT/api_vs_zenodo.allele_frequency_comparison.tsv"
echo "Registry:        $SUMMARY_ROOT/tratlas_source_registry.corrected.tsv"
echo "No bulk retrieval or final ranking was run."
