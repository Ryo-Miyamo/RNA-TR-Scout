#!/usr/bin/env bash
set -euo pipefail

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
fi

conda activate rnatr-v03
source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"

OUTDIR="$PROJECT_ROOT/results/11_p3_integration_inventory/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_p3_integration_inventory/$RUN_ID"

REPORT="$OUTDIR/p3_integration_inventory.txt"
FILES="$OUTDIR/p3_integration_candidate_files.tsv"
QC="$QCDIR/p3_integration_inventory.qc.tsv"
MANIFEST="$OUTDIR/${RUN_ID}.p3_integration_inventory.manifest.tsv"

SCHEMA_DIR="$PROJECT_ROOT/config/evidence_schema/v0.3.1"
REGRESSION_DIR="$PROJECT_ROOT/tests/regression/v0.3.1"
FROZEN_RULES="$PROJECT_ROOT/results/11_p3_orientation_freeze/$RUN_ID/p3_frozen_rules.tsv"
FROZEN_CLASSIFICATION="$PROJECT_ROOT/results/11_p3_orientation_freeze/$RUN_ID/p3_orientation_corrected_classification.tsv"

mkdir -p "$OUTDIR" "$QCDIR"

for path in \
  "$SCHEMA_DIR" \
  "$REGRESSION_DIR" \
  "$FROZEN_RULES" \
  "$FROZEN_CLASSIFICATION"
do
    test -e "$path" || {
        echo "ERROR: missing required path: $path" >&2
        exit 1
    }
done

rm -f "$REPORT" "$FILES" "$QC" "$MANIFEST"

{
    echo "RNA-TR-Scout P3 integration inventory"
    echo "====================================="
    echo
    echo "project_root=$PROJECT_ROOT"
    echo "run_id=$RUN_ID"
    echo "generated_at=$(date --iso-8601=seconds)"
    echo

    echo "===== TOP-LEVEL PROJECT STRUCTURE ====="
    find "$PROJECT_ROOT" \
      -mindepth 1 \
      -maxdepth 2 \
      \( \
        -path "$PROJECT_ROOT/results" \
        -o -path "$PROJECT_ROOT/results/*" \
        -o -path "$PROJECT_ROOT/logs" \
        -o -path "$PROJECT_ROOT/logs/*" \
        -o -path "$PROJECT_ROOT/tmp" \
        -o -path "$PROJECT_ROOT/tmp/*" \
      \) -prune \
      -o -maxdepth 2 -printf '%y\t%p\n' \
      | sort
    echo

    echo "===== PACKAGE / CLI CANDIDATES ====="
    find "$PROJECT_ROOT" \
      -type f \
      \( \
        -name 'pyproject.toml' \
        -o -name 'setup.py' \
        -o -name 'setup.cfg' \
        -o -name 'environment.yml' \
        -o -name 'environment.yaml' \
        -o -name 'Snakefile' \
        -o -name '*.smk' \
        -o -name '*.py' \
      \) \
      ! -path "$PROJECT_ROOT/results/*" \
      ! -path "$PROJECT_ROOT/tmp/*" \
      ! -path "$PROJECT_ROOT/logs/*" \
      | sort
    echo

    echo "===== EVIDENCE SCHEMA FILES ====="
    find "$SCHEMA_DIR" \
      -maxdepth 2 \
      -type f \
      -printf '%p\n' \
      | sort
    echo

    echo "===== EVIDENCE SCHEMA CONTENT PREVIEW ====="
    while IFS= read -r path; do
        echo
        echo "--- $path ---"

        case "$path" in
            *.gz)
                gzip -cd "$path" | head -n 80
                ;;
            *)
                head -n 80 "$path"
                ;;
        esac
    done < <(
        find "$SCHEMA_DIR" \
          -maxdepth 2 \
          -type f \
          | sort
    )
    echo

    echo "===== REGRESSION FILES ====="
    find "$REGRESSION_DIR" \
      -maxdepth 3 \
      -type f \
      -printf '%p\n' \
      | sort
    echo

    echo "===== REGRESSION TABULAR HEADERS / PREVIEWS ====="
    while IFS= read -r path; do
        echo
        echo "--- $path ---"

        case "$path" in
            *.tsv.gz|*.csv.gz|*.txt.gz)
                gzip -cd "$path" | head -n 30
                ;;
            *.tsv|*.csv|*.txt|*.json|*.yaml|*.yml|*.md)
                head -n 60 "$path"
                ;;
            *)
                echo "[binary or non-previewed file]"
                ;;
        esac
    done < <(
        find "$REGRESSION_DIR" \
          -maxdepth 3 \
          -type f \
          | sort
    )
    echo

    echo "===== CURRENT P3 FROZEN RULES ====="
    column -ts $'\t' "$FROZEN_RULES"
    echo

    echo "===== CURRENT P3 CORRECTED COUNTS ====="
    awk -F '\t' '
        NR == 1 {
            for (i = 1; i <= NF; i++) {
                header[$i] = i
            }
            next
        }
        {
            frozen[$header["frozen_p3_status"]]++
            emitted[$header["standard_p3_evidence_emitted"]]++
        }
        END {
            for (key in frozen) {
                print "frozen_status::" key "\t" frozen[key]
            }
            for (key in emitted) {
                print "standard_evidence_emitted::" key "\t" emitted[key]
            }
        }
    ' "$FROZEN_CLASSIFICATION" \
      | sort \
      | column -ts $'\t'
    echo

    echo "===== EXISTING P3 / EVIDENCE SYMBOL REFERENCES ====="
    grep -RInE \
      'LEFT_ONLY_INTERNAL|RIGHT_ONLY_INTERNAL|partial_internal|lower_bound|P3_|orientation|homopolymer|poly\(A\)|polyA' \
      "$PROJECT_ROOT/scripts" \
      "$PROJECT_ROOT/config" \
      "$PROJECT_ROOT/tests" \
      2>/dev/null \
      | head -n 500 \
      || true
    echo

    echo "===== POSSIBLE PRODUCTION SOURCE DIRECTORIES ====="
    for directory in \
      "$PROJECT_ROOT/src" \
      "$PROJECT_ROOT/rnatr" \
      "$PROJECT_ROOT/rna_tr_scout" \
      "$PROJECT_ROOT/bin" \
      "$PROJECT_ROOT/workflow" \
      "$PROJECT_ROOT/pipeline"
    do
        if [[ -d "$directory" ]]; then
            echo "$directory"
            find "$directory" \
              -maxdepth 3 \
              -type f \
              -printf '  %p\n' \
              | sort
        fi
    done
} > "$REPORT"

{
    printf 'category\tpath\tbytes\n'

    find "$SCHEMA_DIR" \
      -maxdepth 2 \
      -type f \
      -printf 'evidence_schema\t%p\t%s\n'

    find "$REGRESSION_DIR" \
      -maxdepth 3 \
      -type f \
      -printf 'regression\t%p\t%s\n'

    find "$PROJECT_ROOT" \
      -type f \
      \( \
        -name 'pyproject.toml' \
        -o -name 'setup.py' \
        -o -name 'setup.cfg' \
        -o -name '*.py' \
        -o -name 'Snakefile' \
        -o -name '*.smk' \
      \) \
      ! -path "$PROJECT_ROOT/results/*" \
      ! -path "$PROJECT_ROOT/tmp/*" \
      ! -path "$PROJECT_ROOT/logs/*" \
      -printf 'production_candidate\t%p\t%s\n'
} | sort -t $'\t' -k1,1 -k2,2 > "$FILES"

schema_files="$(
    find "$SCHEMA_DIR" \
      -maxdepth 2 \
      -type f \
      | wc -l
)"

regression_files="$(
    find "$REGRESSION_DIR" \
      -maxdepth 3 \
      -type f \
      | wc -l
)"

production_candidate_files="$(
    awk -F '\t' '
        NR > 1 && $1 == "production_candidate" {
            count++
        }
        END {
            print count + 0
        }
    ' "$FILES"
)"

frozen_rule_rows="$(
    awk 'END {print NR-1}' "$FROZEN_RULES"
)"

frozen_classification_rows="$(
    awk 'END {print NR-1}' "$FROZEN_CLASSIFICATION"
)"

status="PASS"

if [[ "$schema_files" -lt 1 ]] \
  || [[ "$regression_files" -lt 1 ]] \
  || [[ "$frozen_rule_rows" -ne 5 ]] \
  || [[ "$frozen_classification_rows" -ne 23 ]]
then
    status="REVIEW"
fi

{
    printf 'metric\tvalue\n'
    printf 'schema_files\t%s\n' "$schema_files"
    printf 'regression_files\t%s\n' "$regression_files"
    printf 'production_candidate_files\t%s\n' "$production_candidate_files"
    printf 'frozen_rule_rows\t%s\n' "$frozen_rule_rows"
    printf 'frozen_classification_rows\t%s\n' "$frozen_classification_rows"
    printf 'files_inventory_rows\t%s\n' "$(
        awk 'END {print NR-1}' "$FILES"
    )"
    printf 'report_bytes\t%s\n' "$(
        stat -c '%s' "$REPORT"
    )"
    printf 'inventory_status\t%s\n' "$status"
} > "$QC"

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in "$FILES" "$QC"; do
        printf '%s\t%s\t%s\t%s\t%s\n' \
          "$(basename "$path")" \
          "$(awk 'END {print NR-1}' "$path")" \
          "$(stat -c '%s' "$path")" \
          "$(sha256sum "$path" | awk '{print $1}')" \
          "$path"
    done

    printf '%s\t%s\t%s\t%s\t%s\n' \
      "$(basename "$REPORT")" \
      "." \
      "$(stat -c '%s' "$REPORT")" \
      "$(sha256sum "$REPORT" | awk '{print $1}')" \
      "$REPORT"
} > "$MANIFEST"

echo "===== QC ====="
column -ts $'\t' "$QC"

echo
echo "===== CANDIDATE FILES ====="
column -ts $'\t' "$FILES"

echo
echo "===== REPORT LOCATION ====="
echo "$REPORT"

echo
echo "===== MANIFEST ====="
column -ts $'\t' "$MANIFEST"

if [[ "$status" != "PASS" ]]; then
    exit 1
fi
