#!/usr/bin/env bash
set -euo pipefail

source /mnt/intelssd/rnatr_project/config/paths.env

BUNDLE="${1:-$HOME/Downloads/rnatr_v03_evidence_schema_bundle.tar.gz}"
DEST="$PROJECT_ROOT/config/evidence_schema/v0.3"
TMP_DEST="${DEST}.tmp.$$"

test -s "$BUNDLE" || {
    echo "ERROR: schema bundle not found: $BUNDLE" >&2
    exit 1
}

rm -rf "$TMP_DEST"
mkdir -p "$TMP_DEST"

echo "===== BUNDLE ====="
ls -lh "$BUNDLE"
echo "SHA256: $(sha256sum "$BUNDLE" | awk '{print $1}')"

echo
echo "===== EXTRACT ====="

tar -xzf "$BUNDLE" \
  -C "$TMP_DEST" \
  --strip-components=1

echo
echo "===== MANIFEST CHECK ====="

(
    cd "$TMP_DEST"
    sha256sum -c MANIFEST.sha256
)

echo
echo "===== JSON CHECK ====="

python -m json.tool \
  "$TMP_DEST/schema/rnatr_v03_table_schema.json" \
  >/dev/null

echo "Schema JSON: OK"

echo
echo "===== HEADER VALIDATION ====="

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
    echo "--- $table ---"

    python "$TMP_DEST/rnatr_v03_validate_tsv.py" \
      --schema "$TMP_DEST/schema/rnatr_v03_table_schema.json" \
      --table "$table" \
      --input "$TMP_DEST/templates/${table}.tsv" \
      --max-rows 1
done

cat > "$TMP_DEST/INSTALLATION.tsv" <<EOF
field	value
schema_version	$(cat "$TMP_DEST/SCHEMA_VERSION")
installed_at	$(date -Is)
source_bundle	$BUNDLE
source_bundle_sha256	$(sha256sum "$BUNDLE" | awk '{print $1}')
destination	$DEST
EOF

rm -rf "$DEST"
mv "$TMP_DEST" "$DEST"

echo
echo "===== INSTALLED ====="

column -ts $'\t' "$DEST/INSTALLATION.tsv"

echo
echo "Schema version: $(cat "$DEST/SCHEMA_VERSION")"
echo "Destination: $DEST"
