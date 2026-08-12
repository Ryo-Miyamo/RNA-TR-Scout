#!/usr/bin/env bash
set -euo pipefail

BASE_URL="https://wlcb.oit.uci.edu/TRatlas"
PROBE_ROOT="${HOME}/Downloads/tratlas_endpoint_probe/js_endpoint_probe_v0.1.0"

mkdir -p "$PROBE_ROOT"
cd "$PROBE_ROOT"

files=(
  "geo_population3_add.js"
  "main_cor_population_add.js"
  "sub_cor_population2_add.js"
  "mainbar_population_add.js"
  "subbar_population_add.js"
)

echo "===== DOWNLOAD STATIC GRAPH SCRIPTS ====="
for file in "${files[@]}"; do
  echo "downloading: $file"
  curl \
    --fail \
    --location \
    --compressed \
    --retry 3 \
    --retry-delay 2 \
    --connect-timeout 20 \
    --max-time 120 \
    -A 'Mozilla/5.0' \
    -D "${file}.headers.txt" \
    "${BASE_URL}/js/${file}" \
    -o "$file"

  test -s "$file"
  sleep 1
done

echo
echo "===== FILE SIZES ====="
wc -c "${files[@]}"

echo
echo "===== SHA256 ====="
sha256sum "${files[@]}" | tee static_js.sha256.tsv

echo
echo "===== REQUEST / ENDPOINT KEYWORDS ====="
grep -RniE \
  '\$\.ajax|\$\.getJSON|\$\.get\(|\$\.post\(|fetch\(|XMLHttpRequest|d3\.(json|csv|tsv)|Plotly\.d3|url[[:space:]]*:|type[[:space:]]*:|method[[:space:]]*:|dataType[[:space:]]*:|index_id|location\.search|\.php|\.json|\.csv|\.tsv|\.txt' \
  "${files[@]}" \
  | tee request_keyword_hits.txt \
  || true

echo
echo "===== CHART INITIALIZATION KEYWORDS ====="
grep -RniE \
  'echarts\.init|setOption|Plotly\.newPlot|series[[:space:]]*:|xAxis[[:space:]]*:|yAxis[[:space:]]*:|dataset[[:space:]]*:|data[[:space:]]*:' \
  "${files[@]}" \
  | tee chart_keyword_hits.txt \
  || true

python - <<'PY'
from pathlib import Path
import json
import re

root = Path(".")
files = [
    root / "geo_population3_add.js",
    root / "main_cor_population_add.js",
    root / "sub_cor_population2_add.js",
    root / "mainbar_population_add.js",
    root / "subbar_population_add.js",
]

request_terms = re.compile(
    r"""
    \$\.ajax
    |\$\.getJSON
    |\$\.get\s*\(
    |\$\.post\s*\(
    |fetch\s*\(
    |XMLHttpRequest
    |d3\.(?:json|csv|tsv)
    |Plotly\.d3
    |location\.search
    |index_id
    |url\s*:
    |dataType\s*:
    |(?:[A-Za-z0-9_./?-]+\.(?:php|json|csv|tsv|txt))(?:\?[^"' \t\r\n]*)?
    """,
    re.IGNORECASE | re.VERBOSE,
)

string_pattern = re.compile(
    r"""(?P<quote>["'])(?P<value>(?:\\.|(?!\1).)*)(?P=quote)""",
    re.DOTALL,
)

records = []
candidate_strings = set()

for path in files:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    for lineno, line in enumerate(lines, start=1):
        if request_terms.search(line):
            records.append(
                {
                    "file": path.name,
                    "line": lineno,
                    "text": line.strip(),
                }
            )

    for match in string_pattern.finditer(text):
        value = match.group("value")
        lower = value.lower()
        if (
            ".php" in lower
            or ".json" in lower
            or ".csv" in lower
            or ".tsv" in lower
            or ".txt" in lower
            or "index_id" in lower
            or "distribution" in lower
            or "population" in lower
        ):
            candidate_strings.add(value)

Path("request_lines.json").write_text(
    json.dumps(records, indent=2, ensure_ascii=False) + "\n",
    encoding="utf-8",
)

Path("candidate_string_literals.txt").write_text(
    "".join(f"{value}\n" for value in sorted(candidate_strings)),
    encoding="utf-8",
)

print("request-like lines:", len(records))
print("candidate string literals:", len(candidate_strings))
print("request_lines.json")
print("candidate_string_literals.txt")
PY

echo
echo "===== CANDIDATE STRING LITERALS ====="
cat candidate_string_literals.txt || true

echo
echo "===== FULL STATIC JS WITH LINE NUMBERS ====="
for file in "${files[@]}"; do
  echo
  echo "##### $file #####"
  nl -ba "$file"
done | tee full_static_js.numbered.txt

echo
echo "===== OUTPUT ====="
echo "Probe root: $PROBE_ROOT"
echo "Keyword hits: $PROBE_ROOT/request_keyword_hits.txt"
echo "Candidate strings: $PROBE_ROOT/candidate_string_literals.txt"
echo "Full numbered JS: $PROBE_ROOT/full_static_js.numbered.txt"
echo "No backend endpoint was called by this probe."
