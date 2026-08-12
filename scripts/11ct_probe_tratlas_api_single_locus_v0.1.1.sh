#!/usr/bin/env bash
set -euo pipefail

TR_ID="${1:-TR137069}"
BASE_URL="https://wlcb.oit.uci.edu/TRgnomAD/api"
OUT_ROOT="${HOME}/Downloads/tratlas_endpoint_probe/api_single_locus_v0.1.1/${TR_ID}"

mkdir -p "$OUT_ROOT"

declare -A URLS=(
  [main_population]="${BASE_URL}/main_population_All.php?trId=${TR_ID}&datasetId=main_pop_test"
  [sub_population]="${BASE_URL}/sub_population_All.php?trId=${TR_ID}&datasetId=sub_pop_test"
  [main_trds]="${BASE_URL}/main_cor_test.php?trId=${TR_ID}&datasetId=main_cor_test"
  [sub_trds]="${BASE_URL}/sub_cor_test.php?trId=${TR_ID}&datasetId=sub_cor_test"
  [sub_map]="${BASE_URL}/sub_map.php?trId=${TR_ID}"
)

echo "===== TR-ATLAS PUBLIC API SINGLE-LOCUS PROBE ====="
echo "TR ID:      $TR_ID"
echo "Output:     $OUT_ROOT"
echo "Requesting: 5 public JSON endpoints"
echo "Rate:       one request per second"
echo "Parser:     accepts finite numeric JSON strings"
echo

for name in \
  main_population \
  sub_population \
  main_trds \
  sub_trds \
  sub_map
do
  url="${URLS[$name]}"
  echo "request: $name"

  curl \
    --fail \
    --location \
    --compressed \
    --retry 3 \
    --retry-delay 2 \
    --connect-timeout 20 \
    --max-time 120 \
    -A 'Mozilla/5.0' \
    -H 'Accept: application/json,text/plain,*/*' \
    -D "$OUT_ROOT/${name}.headers.txt" \
    "$url" \
    -o "$OUT_ROOT/${name}.json"

  test -s "$OUT_ROOT/${name}.json"
  sleep 1
done

sha256sum "$OUT_ROOT"/*.json \
  | tee "$OUT_ROOT/raw_json.sha256.tsv"

python - "$OUT_ROOT" "$TR_ID" <<'PY'
from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path
from typing import Any

out_root = Path(sys.argv[1])
tr_id = sys.argv[2]

MAIN_NAMES = {
    "data1": "All",
    "data2": "African",
    "data3": "South_Asian",
    "data4": "East_Asian",
    "data5": "European",
    "data6": "Hispanic",
}

SUB_NAMES = {
    "data1": "All",
    "data2": "Other_African",
    "data3": "British",
    "data4": "Irish",
    "data5": "Estonian",
    "data6": "Other_European",
    "data7": "Caribbean",
    "data8": "Cuban",
    "data9": "Dominican",
    "data10": "Puerto_Rican",
    "data11": "Other_Hispanic",
    "data12": "Chinese",
    "data13": "Indian",
    "data14": "Pakistani",
    "data15": "MENA",
    "data16": "Other_Asian",
}


class ProbeError(RuntimeError):
    pass


def load_json(name: str) -> Any:
    path = out_root / f"{name}.json"
    text = path.read_text(encoding="utf-8", errors="strict").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        preview = text[:500].replace("\n", "\\n")
        raise ProbeError(
            f"{name} is not valid JSON: {exc}; preview={preview}"
        ) from exc


def write_tsv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def describe(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {
            "python_type": "object",
            "element_count": len(value),
            "keys_or_preview": ";".join(sorted(map(str, value.keys()))),
        }
    if isinstance(value, list):
        return {
            "python_type": "array",
            "element_count": len(value),
            "keys_or_preview": json.dumps(value[:2], ensure_ascii=False),
        }
    return {
        "python_type": type(value).__name__,
        "element_count": 1,
        "keys_or_preview": repr(value),
    }


def coerce_finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise ProbeError(f"{field}: boolean is not a numeric value")

    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise ProbeError(f"{field}: empty numeric string")
        try:
            number = float(stripped)
        except ValueError as exc:
            raise ProbeError(
                f"{field}: invalid numeric string {value!r}"
            ) from exc
    else:
        raise ProbeError(
            f"{field}: unsupported numeric type "
            f"{type(value).__name__}: {value!r}"
        )

    if not math.isfinite(number):
        raise ProbeError(f"{field}: non-finite numeric value {value!r}")

    return number


def extract_pair(item: Any) -> tuple[float, float]:
    if isinstance(item, list) and len(item) >= 2:
        return (
            coerce_finite_number(item[0], "array allele length"),
            coerce_finite_number(item[1], "array frequency"),
        )

    if isinstance(item, dict):
        if "value" in item:
            value = item["value"]
            if isinstance(value, list) and len(value) >= 2:
                return (
                    coerce_finite_number(
                        value[0],
                        "value allele length",
                    ),
                    coerce_finite_number(
                        value[1],
                        "value frequency",
                    ),
                )

        x_keys = ("x", "length", "allele", "allele_length")
        y_keys = ("y", "frequency", "freq")
        x = next((item[key] for key in x_keys if key in item), None)
        y = next((item[key] for key in y_keys if key in item), None)

        if x is not None and y is not None:
            return (
                coerce_finite_number(x, "object allele length"),
                coerce_finite_number(y, "object frequency"),
            )

    raise ProbeError(f"unrecognized frequency point: {item!r}")


def weighted_quantile(
    points: list[tuple[float, float]],
    probability: float,
) -> float:
    if not 0 <= probability <= 1:
        raise ValueError(probability)
    ordered = sorted((x, max(0.0, y)) for x, y in points)
    total = sum(y for _, y in ordered)
    if total <= 0:
        return math.nan
    target = probability * total
    cumulative = 0.0
    for x, weight in ordered:
        cumulative += weight
        if cumulative >= target:
            return x
    return ordered[-1][0]


def parse_frequency_payload(
    endpoint_name: str,
    payload: Any,
    population_names: dict[str, str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(payload, dict):
        raise ProbeError(
            f"{endpoint_name}: expected JSON object, got {type(payload).__name__}"
        )

    long_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []

    for key, population in population_names.items():
        series = payload.get(key)
        if series is None:
            summary_rows.append(
                {
                    "tr_id": tr_id,
                    "endpoint": endpoint_name,
                    "series_key": key,
                    "population": population,
                    "status": "MISSING_SERIES_KEY",
                    "point_count": 0,
                    "frequency_sum": ".",
                    "minimum_length": ".",
                    "p50_length": ".",
                    "p95_length": ".",
                    "p99_length": ".",
                    "maximum_nonzero_length": ".",
                }
            )
            continue
        if not isinstance(series, list):
            raise ProbeError(
                f"{endpoint_name}.{key}: expected array, "
                f"got {type(series).__name__}"
            )

        points = [extract_pair(item) for item in series]
        points.sort()

        for allele_length, frequency in points:
            long_rows.append(
                {
                    "tr_id": tr_id,
                    "endpoint": endpoint_name,
                    "series_key": key,
                    "population": population,
                    "allele_length": f"{allele_length:.12g}",
                    "reported_frequency": f"{frequency:.12g}",
                }
            )

        positive = [(x, y) for x, y in points if y > 0]
        summary_rows.append(
            {
                "tr_id": tr_id,
                "endpoint": endpoint_name,
                "series_key": key,
                "population": population,
                "status": "PASS" if points else "EMPTY_SERIES",
                "point_count": len(points),
                "frequency_sum": (
                    f"{sum(y for _, y in points):.12g}"
                    if points
                    else "0"
                ),
                "minimum_length": (
                    f"{min(x for x, _ in points):.12g}"
                    if points
                    else "."
                ),
                "p50_length": (
                    f"{weighted_quantile(points, 0.50):.12g}"
                    if positive
                    else "."
                ),
                "p95_length": (
                    f"{weighted_quantile(points, 0.95):.12g}"
                    if positive
                    else "."
                ),
                "p99_length": (
                    f"{weighted_quantile(points, 0.99):.12g}"
                    if positive
                    else "."
                ),
                "maximum_nonzero_length": (
                    f"{max(x for x, y in positive):.12g}"
                    if positive
                    else "."
                ),
            }
        )

    return long_rows, summary_rows


payloads = {
    name: load_json(name)
    for name in (
        "main_population",
        "sub_population",
        "main_trds",
        "sub_trds",
        "sub_map",
    )
}

schema_rows: list[dict[str, Any]] = []
for endpoint, payload in payloads.items():
    top = describe(payload)
    schema_rows.append(
        {
            "tr_id": tr_id,
            "endpoint": endpoint,
            "json_top_type": top["python_type"],
            "top_element_count": top["element_count"],
            "top_keys_or_preview": top["keys_or_preview"],
        }
    )

main_long, main_summary = parse_frequency_payload(
    "main_population",
    payloads["main_population"],
    MAIN_NAMES,
)
sub_long, sub_summary = parse_frequency_payload(
    "sub_population",
    payloads["sub_population"],
    SUB_NAMES,
)

write_tsv(
    out_root / "api_schema_summary.tsv",
    [
        "tr_id",
        "endpoint",
        "json_top_type",
        "top_element_count",
        "top_keys_or_preview",
    ],
    schema_rows,
)

frequency_fields = [
    "tr_id",
    "endpoint",
    "series_key",
    "population",
    "allele_length",
    "reported_frequency",
]
write_tsv(
    out_root / "main_population_frequency.long.tsv",
    frequency_fields,
    main_long,
)
write_tsv(
    out_root / "sub_population_frequency.long.tsv",
    frequency_fields,
    sub_long,
)

summary_fields = [
    "tr_id",
    "endpoint",
    "series_key",
    "population",
    "status",
    "point_count",
    "frequency_sum",
    "minimum_length",
    "p50_length",
    "p95_length",
    "p99_length",
    "maximum_nonzero_length",
]
write_tsv(
    out_root / "frequency_distribution.summary.tsv",
    summary_fields,
    main_summary + sub_summary,
)

contracts = [
    {
        "rule_id": "FIX01",
        "rule": "V0_1_0_NUMERIC_STRING_SCHEMA_FAILURE_REPAIRED",
        "status": "PASS",
        "detail": (
            "TR-Atlas frequency points encode allele length and frequency "
            "as JSON strings inside value arrays; v0.1.1 safely converts "
            "finite numeric strings before distribution parsing."
        ),
    },
    {
        "rule_id": "API01",
        "rule": "PUBLIC_BROWSER_API_ENDPOINT_CONFIRMED",
        "status": "PASS",
        "detail": (
            "The browser JavaScript calls public JSON endpoints for "
            "main- and sub-population allele-frequency plots."
        ),
    },
    {
        "rule_id": "API02",
        "rule": "FREQUENCIES_NOT_COUNTS_UNTIL_SCHEMA_VALIDATED",
        "status": "FROZEN",
        "detail": (
            "Do not infer allele counts or exact denominators from the "
            "frequency arrays unless a denominator field is independently confirmed."
        ),
    },
    {
        "rule_id": "API03",
        "rule": "P95_P99_DERIVED_FROM_REPORTED_FREQUENCIES",
        "status": "PROVISIONAL",
        "detail": (
            "Derived quantiles are exploratory until cross-checked against "
            "the chr1 Zenodo files and browser summaries."
        ),
    },
    {
        "rule_id": "API04",
        "rule": "NO_BULK_CRAWL_IN_SINGLE_LOCUS_PROBE",
        "status": "FROZEN",
        "detail": (
            "This probe requests one TR ID only and does not establish "
            "permission or policy for high-volume retrieval."
        ),
    },
]
write_tsv(
    out_root / "api_probe.contract.tsv",
    ["rule_id", "rule", "status", "detail"],
    contracts,
)

print("API_PROBE_STATUS\tPASS")
print(f"TR_ID\t{tr_id}")
print(f"MAIN_FREQUENCY_ROWS\t{len(main_long)}")
print(f"SUB_FREQUENCY_ROWS\t{len(sub_long)}")
print(f"OUTPUT\t{out_root}")
PY

echo
echo "===== JSON TOP-LEVEL SCHEMA ====="
column -ts $'\t' "$OUT_ROOT/api_schema_summary.tsv"

echo
echo "===== FREQUENCY DISTRIBUTION SUMMARY ====="
column -ts $'\t' "$OUT_ROOT/frequency_distribution.summary.tsv"

echo
echo "===== MAIN POPULATION JSON PREVIEW ====="
python -m json.tool "$OUT_ROOT/main_population.json" | sed -n '1,160p'

echo
echo "===== SUB POPULATION JSON PREVIEW ====="
python -m json.tool "$OUT_ROOT/sub_population.json" | sed -n '1,200p'

echo
echo "===== API PROBE CONTRACT ====="
column -ts $'\t' "$OUT_ROOT/api_probe.contract.tsv"

echo
echo "===== OUTPUT ====="
echo "Raw main JSON:   $OUT_ROOT/main_population.json"
echo "Raw sub JSON:    $OUT_ROOT/sub_population.json"
echo "Main long table: $OUT_ROOT/main_population_frequency.long.tsv"
echo "Sub long table:  $OUT_ROOT/sub_population_frequency.long.tsv"
echo "Summary:         $OUT_ROOT/frequency_distribution.summary.tsv"
echo "This is a one-locus public-endpoint probe, not a bulk download."
