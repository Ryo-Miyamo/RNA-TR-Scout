#!/usr/bin/env bash
set -euo pipefail

source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

SOURCE="$PROJECT_ROOT/config/evidence_schema/v0.3"
DEST="$PROJECT_ROOT/config/evidence_schema/v0.3.1"
TMP="${DEST}.tmp.$$"

test -s "$SOURCE/schema/rnatr_v03_table_schema.json" || {
    echo "ERROR: source schema missing: $SOURCE" >&2
    exit 1
}

rm -rf "$TMP"
cp -a "$SOURCE" "$TMP"

python - "$TMP" <<'PY'
from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
schema_path = root / "schema" / "rnatr_v03_table_schema.json"
schema = json.loads(schema_path.read_text(encoding="utf-8"))

schema["schema_version"] = "0.3.1"

evidence_values = schema["enums"]["evidence_class"]
for value in ["LEFT_ONLY_INTERNAL", "RIGHT_ONLY_INTERNAL"]:
    if value not in evidence_values:
        evidence_values.insert(
            evidence_values.index("REPEAT_ONLY_UNANCHORED"),
            value,
        )

sizing_values = schema["enums"]["sizing_status"]
if "partial_internal" not in sizing_values:
    sizing_values.insert(
        sizing_values.index("no_call"),
        "partial_internal",
    )

semantic = (
    "LEFT_ONLY_INTERNAL and RIGHT_ONLY_INTERNAL indicate a "
    "target-overlapping repeat tract supported by one genomic flank, "
    "without reaching the expected raw-read end; they are neither exact "
    "sizes nor censored lower bounds."
)
if semantic not in schema["critical_semantics"]:
    schema["critical_semantics"].append(semantic)

schema_path.write_text(
    json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
(root / "SCHEMA_VERSION").write_text("0.3.1\n", encoding="utf-8")

enums_path = root / "dictionaries" / "rnatr_v03_enums.tsv"
with enums_path.open(encoding="utf-8", newline="") as handle:
    reader = csv.DictReader(handle, delimiter="\t")
    fieldnames = reader.fieldnames
    rows = list(reader)

existing = {(row["enum_name"], row["allowed_value"]) for row in rows}
new_rows = [
    {
        "enum_name": "evidence_class",
        "allowed_value": "LEFT_ONLY_INTERNAL",
        "meaning": (
            "Genomic-left flank anchored and target-overlapping repeat "
            "tract observed internally, but the tract does not reach the "
            "expected raw-read end; no exact size or lower bound."
        ),
    },
    {
        "enum_name": "evidence_class",
        "allowed_value": "RIGHT_ONLY_INTERNAL",
        "meaning": (
            "Genomic-right flank anchored and target-overlapping repeat "
            "tract observed internally, but the tract does not reach the "
            "expected raw-read end; no exact size or lower bound."
        ),
    },
    {
        "enum_name": "sizing_status",
        "allowed_value": "partial_internal",
        "meaning": (
            "Partial internal repeat tract observed; neither exact size "
            "nor censored lower bound."
        ),
    },
]

for row in new_rows:
    key = (row["enum_name"], row["allowed_value"])
    if key not in existing:
        rows.append(row)

with enums_path.open("w", encoding="utf-8", newline="") as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=fieldnames,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(rows)

fixed_validator = (
    root / "patches" / "validator_v0.3.1"
    / "rnatr_v03_validate_tsv_validator_v0.3.1.py"
)
canonical_validator = root / "rnatr_v03_validate_tsv.py"
if fixed_validator.exists():
    canonical_validator.write_bytes(fixed_validator.read_bytes())
    canonical_validator.chmod(0o755)

(root / "SCHEMA_PATCH_0.3.1.md").write_text(
    """# Evidence schema patch 0.3.1

## Added evidence classes

- `LEFT_ONLY_INTERNAL`
- `RIGHT_ONLY_INTERNAL`

These states retain one-flank, target-overlapping repeat evidence when the
tract does not reach the expected raw-read end. They must not be interpreted
as exact repeat sizes or censored lower bounds.

## Added sizing status

- `partial_internal`

## Rationale

The first target-constrained pilot produced one-flank reads containing a
repeat tract over the target but not continuing to the raw-read boundary.
Classifying those rows as `UNRESOLVED` discarded useful sequence evidence;
classifying them as censored would falsely imply a repeat-length lower bound.
""",
    encoding="utf-8",
)

(root / "INSTALLATION.tsv").write_text(
    "field\tvalue\n"
    "schema_version\t0.3.1\n"
    "source_schema\t0.3.0\n"
    "patch_reason\tadd one-flank internal repeat evidence states\n",
    encoding="utf-8",
)

manifest_path = root / "MANIFEST.sha256"
files = sorted(
    path for path in root.rglob("*")
    if path.is_file() and path != manifest_path
)
manifest_path.write_text(
    "\n".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  "
        f"{path.relative_to(root)}"
        for path in files
    )
    + "\n",
    encoding="utf-8",
)
PY

(
    cd "$TMP"
    sha256sum -c MANIFEST.sha256
)

python -m json.tool \
  "$TMP/schema/rnatr_v03_table_schema.json" \
  >/dev/null

for table in \
  run_manifest \
  alignment_segments \
  read_evidence \
  repeat_segments \
  molecule_clusters \
  molecule_membership \
  locus_summary \
  region_summary \
  qc_metrics
do
    python "$TMP/rnatr_v03_validate_tsv.py" \
      --schema "$TMP/schema/rnatr_v03_table_schema.json" \
      --table "$table" \
      --input "$TMP/templates/${table}.tsv" \
      --max-rows 1
done

rm -rf "$DEST"
mv "$TMP" "$DEST"

echo "===== SCHEMA 0.3.1 INSTALLED ====="
cat "$DEST/SCHEMA_VERSION"

python - "$DEST/schema/rnatr_v03_table_schema.json" <<'PY'
import json
import sys

schema = json.load(open(sys.argv[1], encoding="utf-8"))

print("evidence_class:")
for value in schema["enums"]["evidence_class"]:
    print(f"  {value}")

print("sizing_status:")
for value in schema["enums"]["sizing_status"]:
    print(f"  {value}")
PY
