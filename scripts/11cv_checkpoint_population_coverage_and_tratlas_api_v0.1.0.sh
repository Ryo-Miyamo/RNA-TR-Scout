#!/usr/bin/env bash
set -euo pipefail

CHECKPOINT_VERSION="rnatr_step11_population_coverage_tratlas_api_checkpoint_v0.1.0"
RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"
EXPECTED_PACKAGE_VERSION="0.3.2"
EXPECTED_EVENTS="23867"
EXPECTED_LOCI="11042"
EXPECTED_1KG_EXACT="403"
EXPECTED_SAFE="1"
EXPECTED_MANUAL="52"
EXPECTED_NO_CATALOG="10586"
EXPECTED_PILOT_CANDIDATES="5"
EXPECTED_CANDIDATE_READS="56"

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
  # shellcheck disable=SC1091
  source "$HOME/miniconda3/etc/profile.d/conda.sh"
fi

conda activate rnatr-v03
# shellcheck disable=SC1091
source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

TRACKER="$PROJECT_ROOT/metadata/build_tracker/rnatr_build_tracker.py"
TRACKER_DB="$PROJECT_ROOT/metadata/build_tracker/rnatr_build_tracker.sqlite"
TRACKER_ROOT="$PROJECT_ROOT/metadata/build_tracker"
CHECKPOINT_ROOT="$TRACKER_ROOT/checkpoints"
SCRIPT_DEST="$PROJECT_ROOT/scripts/$(basename "$0")"
LATEST_LINK="$CHECKPOINT_ROOT/latest_step11_checkpoint"
LATEST_COVERAGE_LINK="$CHECKPOINT_ROOT/latest_step11_population_reference_coverage_checkpoint"

BACKBONE_QC="$PROJECT_ROOT/qc/11_p01_event_to_locus_backbone/$RUN_ID/rnatr_p01_event_to_locus_backbone_v0.1.0/p01_event_to_locus_backbone.qc.tsv"
SIGNATURE_QC="$PROJECT_ROOT/qc/11_p01_cdna_molecule_signatures/$RUN_ID/rnatr_p01_cdna_molecule_signatures_v0.1.2/p01_cdna_molecule_signatures.qc.tsv"

STAGE6N_QC="$PROJECT_ROOT/qc/11_repeatcatalogs_1kg_genomewide_adapter/$RUN_ID/rnatr_repeatcatalogs_1kg_genomewide_adapter_v0.1.3/repeatcatalogs_1kg_genomewide_adapter.qc.tsv"
STAGE6O_QC="$PROJECT_ROOT/qc/11_p01_repeatcatalogs_1kg_population_comparison/$RUN_ID/rnatr_p01_repeatcatalogs_1kg_population_comparison_v0.1.1/p01_repeatcatalogs_1kg_population_comparison.qc.tsv"
STAGE6P_QC="$PROJECT_ROOT/qc/11_p01_single_read_1kg_max_exceedance_audit/$RUN_ID/rnatr_p01_single_read_1kg_max_exceedance_audit_v0.1.0/p01_single_read_1kg_max_exceedance_audit.qc.tsv"
STAGE6Q_QC="$PROJECT_ROOT/qc/11_p01_multisource_context_precontrol_review/$RUN_ID/rnatr_p01_multisource_context_precontrol_review_v0.1.0/p01_multisource_context_precontrol_review.qc.tsv"
STAGE6R_QC="$PROJECT_ROOT/qc/11_repeatcatalogs_crosswalk_coverage_audit/$RUN_ID/rnatr_repeatcatalogs_crosswalk_coverage_audit_v0.1.2/repeatcatalogs_crosswalk_coverage_audit.qc.tsv"

STAGE6Q_ROOT="$PROJECT_ROOT/results/11_p01_multisource_context_precontrol_review/$RUN_ID/rnatr_p01_multisource_context_precontrol_review_v0.1.0"
STAGE6R_ROOT="$PROJECT_ROOT/results/11_repeatcatalogs_crosswalk_coverage_audit/$RUN_ID/rnatr_repeatcatalogs_crosswalk_coverage_audit_v0.1.2"
STAGE6O_ROOT="$PROJECT_ROOT/results/11_p01_repeatcatalogs_1kg_population_comparison/$RUN_ID/rnatr_p01_repeatcatalogs_1kg_population_comparison_v0.1.1"
STAGE6P_ROOT="$PROJECT_ROOT/results/11_p01_single_read_1kg_max_exceedance_audit/$RUN_ID/rnatr_p01_single_read_1kg_max_exceedance_audit_v0.1.0"

TRATLAS_SCHEMA_QC="$PROJECT_ROOT/qc/11_tratlas_primary_frequency_schema/$RUN_ID/rnatr_tratlas_primary_frequency_schema_v0.1.1/tratlas_primary_frequency_schema.qc.tsv"
TRATLAS_XVAL_ROOT="$PROJECT_ROOT/results/11_tratlas_api_zenodo_crossvalidation/$RUN_ID/rnatr_tratlas_api_zenodo_crossvalidation_v0.1.0"
TRATLAS_XVAL_QC="$PROJECT_ROOT/qc/11_tratlas_api_zenodo_crossvalidation/$RUN_ID/rnatr_tratlas_api_zenodo_crossvalidation_v0.1.0/tratlas_api_zenodo_crossvalidation.qc.tsv"
TRATLAS_XVAL_GROUP="$TRATLAS_XVAL_ROOT/summary/api_vs_zenodo.population_group_summary.tsv"
TRATLAS_XVAL_DETAIL="$TRATLAS_XVAL_ROOT/tables/api_vs_zenodo.allele_frequency_comparison.tsv"

TRATLAS_API_EXTERNAL_ROOT="$PROJECT_ROOT/external_reference/tratlas/public_browser_api"
JS_PROBE_SRC="$HOME/Downloads/tratlas_endpoint_probe/js_endpoint_probe_v0.1.0"
API_PROBE_SRC="$HOME/Downloads/tratlas_endpoint_probe/api_single_locus_v0.1.1/TR137069"
JS_PROBE_DEST="$TRATLAS_API_EXTERNAL_ROOT/javascript_endpoint_probe_v0.1.0"
API_PROBE_DEST="$TRATLAS_API_EXTERNAL_ROOT/single_locus_probe_v0.1.1/TR137069"

required_files=(
  "$TRACKER"
  "$BACKBONE_QC"
  "$SIGNATURE_QC"
  "$STAGE6N_QC"
  "$STAGE6O_QC"
  "$STAGE6P_QC"
  "$STAGE6Q_QC"
  "$STAGE6R_QC"
  "$TRATLAS_SCHEMA_QC"
  "$TRATLAS_XVAL_QC"
  "$TRATLAS_XVAL_GROUP"
  "$TRATLAS_XVAL_DETAIL"
  "$STAGE6Q_ROOT/matrix/p01_locus.multisource_context_matrix.tsv.gz"
  "$STAGE6R_ROOT/tables/p01_locus.repeatcatalogs_crosswalk_coverage_audit.tsv.gz"
  "$STAGE6R_ROOT/tables/p01_locus.repeatcatalogs_safe_equivalence_candidates.tsv"
  "$STAGE6R_ROOT/tables/p01_locus.repeatcatalogs_manual_review_candidates.tsv.gz"
  "$STAGE6R_ROOT/tables/p01_locus.repeatcatalogs_no_catalog_coverage.tsv.gz"
  "$STAGE6O_ROOT/loci/p01_locus.exact_span_repeat_length_overview.tsv"
  "$STAGE6O_ROOT/loci/p01_locus.repeatcatalogs_1kg_population_features.tsv.gz"
  "$STAGE6P_ROOT/tables/single_read_above_max.locus_summary.tsv"
)

for path in "${required_files[@]}"; do
  [[ -s "$path" ]] || {
    echo "ERROR: required checkpoint input is missing or empty: $path" >&2
    exit 1
  }
done

for tool in python sha256sum gzip flock column cp readlink; do
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

require_metric() {
  local file="$1"
  local key="$2"
  local expected="$3"
  local observed
  observed="$(metric "$file" "$key")"
  [[ "$observed" == "$expected" ]] || {
    echo "ERROR: metric mismatch: $file :: $key expected=$expected observed=$observed" >&2
    exit 1
  }
}

installed_version="$(rnatr-scout version)"
[[ "$installed_version" == "$EXPECTED_PACKAGE_VERSION" ]] || {
  echo "ERROR: expected rnatr-scout $EXPECTED_PACKAGE_VERSION; observed $installed_version" >&2
  exit 1
}

require_metric "$BACKBONE_QC" event_to_locus_backbone_status PASS
require_metric "$BACKBONE_QC" source_exact_span_rows "$EXPECTED_EVENTS"
require_metric "$BACKBONE_QC" source_locus_rows "$EXPECTED_LOCI"
require_metric "$SIGNATURE_QC" molecule_signature_build_status PASS
require_metric "$STAGE6N_QC" stage6n_1kg_genomewide_adapter_status PASS
require_metric "$STAGE6O_QC" stage6o_population_comparison_status PASS
require_metric "$STAGE6P_QC" stage6p_technical_audit_status PASS
require_metric "$STAGE6Q_QC" stage6q_multisource_context_status PASS
require_metric "$STAGE6R_QC" stage6r_crosswalk_coverage_audit_status PASS
require_metric "$STAGE6R_QC" all_p01_loci_denominator "$EXPECTED_LOCI"
require_metric "$STAGE6R_QC" current_exact_comparable_loci "$EXPECTED_1KG_EXACT"
require_metric "$STAGE6R_QC" biologically_equivalent_safe_loci "$EXPECTED_SAFE"
require_metric "$STAGE6R_QC" manual_review_only_loci "$EXPECTED_MANUAL"
require_metric "$STAGE6R_QC" no_catalog_coverage_loci "$EXPECTED_NO_CATALOG"
require_metric "$STAGE6R_QC" coverage_expansion_gate_status HOLD
require_metric "$STAGE6P_QC" candidate_locus_rows "$EXPECTED_PILOT_CANDIDATES"
require_metric "$STAGE6P_QC" all_reads_at_candidate_loci "$EXPECTED_CANDIDATE_READS"
require_metric "$TRATLAS_SCHEMA_QC" tratlas_primary_frequency_schema_status PASS
require_metric "$TRATLAS_XVAL_QC" selected_chr1_tr_ids 5
require_metric "$TRATLAS_XVAL_QC" population_group_comparisons 25
require_metric "$TRATLAS_XVAL_QC" failed_population_group_comparisons 2
require_metric "$TRATLAS_XVAL_QC" api_missing_allele_rows 0
require_metric "$TRATLAS_XVAL_QC" zenodo_missing_allele_rows 2
require_metric "$TRATLAS_XVAL_QC" frequency_mismatch_rows 0
require_metric "$TRATLAS_XVAL_QC" api_zenodo_crossvalidation_status FAIL

mkdir -p "$TRACKER_ROOT" "$CHECKPOINT_ROOT" "$PROJECT_ROOT/scripts" "$TRATLAS_API_EXTERNAL_ROOT"
exec 9>"$TRACKER_ROOT/.population_coverage_checkpoint.lock"
if ! flock -n 9; then
  echo "ERROR: another population-coverage checkpoint process holds the lock" >&2
  exit 1
fi

safe_install_script() {
  local source="$1"
  local destination="$2"

  [[ -s "$source" ]] || return 0
  mkdir -p "$(dirname "$destination")"

  if [[ -e "$destination" ]]; then
    if [[ "$(readlink -f "$source")" == "$(readlink -f "$destination")" ]]; then
      chmod +x "$destination"
      return 0
    fi
    if [[ "$(sha256sum "$source" | awk '{print $1}')" != \
          "$(sha256sum "$destination" | awk '{print $1}')" ]]; then
      echo "ERROR: refusing to overwrite different project script: $destination" >&2
      exit 1
    fi
    chmod +x "$destination"
    return 0
  fi

  cp "$source" "$destination"
  chmod +x "$destination"
}

copy_tree_immutable() {
  local source="$1"
  local destination="$2"

  [[ -d "$source" ]] || return 0
  if [[ -e "$destination" ]]; then
    python - "$source" "$destination" <<'PYCOMPARE'
from __future__ import annotations
import hashlib
import sys
from pathlib import Path

source = Path(sys.argv[1])
destination = Path(sys.argv[2])

def inventory(root: Path):
    values = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        values[str(path.relative_to(root))] = (path.stat().st_size, digest)
    return values

if inventory(source) != inventory(destination):
    raise SystemExit(
        f"existing destination differs from source: {destination}"
    )
PYCOMPARE
    return 0
  fi
  mkdir -p "$(dirname "$destination")"
  cp -a "$source" "$destination"
}

SELF="$(readlink -f "$0")"
safe_install_script "$SELF" "$SCRIPT_DEST"

for name in \
  11cr_audit_repeatcatalogs_crosswalk_coverage_v0.1.2.sh \
  11cs_probe_tratlas_frequency_js_endpoints_v0.1.0.sh \
  11ct_probe_tratlas_api_single_locus_v0.1.1.sh \
  11cu_validate_tratlas_api_against_zenodo_chr1_v0.1.0.sh
do
  safe_install_script "$HOME/Downloads/$name" "$PROJECT_ROOT/scripts/$name"
done

copy_tree_immutable "$JS_PROBE_SRC" "$JS_PROBE_DEST"
copy_tree_immutable "$API_PROBE_SRC" "$API_PROBE_DEST"

timestamp="$(date +%Y%m%d_%H%M%S)"
CHECKPOINT_DIR="$CHECKPOINT_ROOT/${timestamp}_step11_population_coverage_tratlas_api"
STAGE_DIR="$CHECKPOINT_ROOT/.stage_${timestamp}_step11_population_coverage_tratlas_api_$$"

mkdir -p "$STAGE_DIR/provenance" "$STAGE_DIR/tracker_exports"

CHECKPOINT_TSV="$STAGE_DIR/population_reference_coverage_checkpoint.tsv"
CHECKPOINT_MD="$STAGE_DIR/RNA-TR-Scout_handoff.md"
SEMANTIC_XVAL="$STAGE_DIR/tratlas_api_zenodo_semantic_validation.tsv"
SOURCE_REGISTRY="$STAGE_DIR/population_reference_source_registry.tsv"
COVERAGE_POLICY="$STAGE_DIR/population_coverage_gate_policy.tsv"
PROVENANCE_TSV="$STAGE_DIR/provenance/checkpoint_provenance.tsv"
ARTIFACT_MANIFEST="$STAGE_DIR/population_reference_coverage_artifact_manifest.tsv"
UNIT_TEST_LOG="$STAGE_DIR/provenance/unit_tests.log"

script_sha256="$(sha256sum "$SELF" | awk '{print $1}')"
tracker_db_before="$(
  if [[ -f "$TRACKER_DB" ]]; then
    sha256sum "$TRACKER_DB" | awk '{print $1}'
  else
    printf '.'
  fi
)"

if [[ -f "$TRACKER_DB" ]]; then
  cp "$TRACKER_DB" "$STAGE_DIR/provenance/rnatr_build_tracker.pre_update.sqlite"
fi

python - \
  "$TRATLAS_XVAL_DETAIL" \
  "$TRATLAS_XVAL_GROUP" \
  "$SEMANTIC_XVAL" <<'PYSEMANTIC'
from __future__ import annotations

import csv
import sys
from pathlib import Path

detail_path = Path(sys.argv[1])
group_path = Path(sys.argv[2])
output_path = Path(sys.argv[3])

with detail_path.open("r", encoding="utf-8", newline="") as handle:
    detail_rows = list(csv.DictReader(handle, delimiter="\t"))

with group_path.open("r", encoding="utf-8", newline="") as handle:
    group_rows = list(csv.DictReader(handle, delimiter="\t"))

non_exact = [
    row for row in detail_rows
    if row["comparison_status"] != "EXACT_FLOAT_MATCH"
]
failed_groups = [
    row for row in group_rows
    if row["group_validation_status"] != "PASS_IDENTICAL_DISTRIBUTION"
]

expected_pairs = {
    ("TR406", "South Asian", "6"),
    ("TR406", "East Asian", "6"),
}
observed_pairs = {
    (row["tr_id"], row["population"], row["allele_repeat_units"])
    for row in non_exact
}

valid = (
    len(detail_rows) == 88
    and len(non_exact) == 2
    and len(failed_groups) == 2
    and observed_pairs == expected_pairs
    and all(
        row["comparison_status"] == "ZENODO_MISSING_ALLELE"
        and float(row["api_frequency"]) == 0.0
        and row["zenodo_frequency"] == "."
        for row in non_exact
    )
    and all(float(row["frequency_sum_delta"]) == 0.0 for row in failed_groups)
)

if not valid:
    raise SystemExit(
        "TR-Atlas semantic crossvalidation pattern does not match the "
        "frozen two zero-frequency-bin representation differences"
    )

rows = [
    ("strict_source_qc_status", "FAIL"),
    (
        "semantic_validation_status",
        "PASS_ZERO_FREQUENCY_BIN_REPRESENTATION_DIFFERENCE",
    ),
    ("selected_tr_ids", "5"),
    ("population_group_comparisons", "25"),
    ("exact_common_frequency_rows", "86"),
    ("zero_frequency_api_only_rows", "2"),
    ("nonzero_frequency_mismatch_rows", "0"),
    ("frequency_sum_delta_in_failed_groups", "0"),
    (
        "interpretation",
        "API and Zenodo distributions are semantically identical for the "
        "tested rows; the API explicitly includes a zero-frequency allele "
        "bin that the Zenodo export omits.",
    ),
    (
        "source_qc_preservation",
        "The original strict FAIL QC is preserved and is not overwritten.",
    ),
]

with output_path.open("w", encoding="utf-8", newline="") as handle:
    writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
    writer.writerow(["metric", "value"])
    writer.writerows(rows)

print("TRATLAS_SEMANTIC_XVAL_STATUS\tPASS")
PYSEMANTIC

cat > "$SOURCE_REGISTRY" <<EOF
source_id	source_role	scope	versioning_status	current_use
REPEATCATALOGS_PAPER_ERA_1KG	DNA_population_reference	174300 components across chr1-22,X	PINNED_GIT_OBJECT_AND_FILE_SHA256	PILOT_EXACT_CONTEXT_403_OF_11042
TRATLAS_CELL2024_RESOURCE	parent_DNA_population_resource	338963 WGS; approximately 0.86M TRs	PUBLICATION_RESOURCE	LABEL_AND_PARENT_PROVENANCE
TRATLAS_ZENODO_10806728_PRIMARY_PREFIX_EXPORTS	pinned_validation_source	5 populations; 50000 rows; chr1 prefix; 1907 TR IDs	PINNED_VERSION_DOI_10.5281_ZENODO_10806728	SCHEMA_AND_API_VALIDATION_ONLY_OUTSIDE_OBSERVED_SCOPE
TRATLAS_PUBLIC_BROWSER_API_MAIN_POPULATION	live_DNA_population_frequency_API	All plus five primary populations per TR ID	UNVERSIONED_LIVE;CACHE_URL_HEADERS_TIME_SHA256	NEXT_PRIMARY_TRATLAS_FREQUENCY_SOURCE_AFTER_CROSSWALK
TRATLAS_PUBLIC_BROWSER_API_SUB_POPULATION	live_DNA_population_frequency_API	detailed subpopulations per TR ID	UNVERSIONED_LIVE;CACHE_URL_HEADERS_TIME_SHA256	SECONDARY_CONTEXT_WITH_FREQUENCY_SUM_GATE
TRATLAS_ZENODO_10806728_TRDS	DNA_population_distance_source	genome-wide population disparity distances	PINNED_VERSION_DOI_10.5281_ZENODO_10806728	DISPARITY_ONLY_NOT_ALLELE_DISTRIBUTION
ALLOFUS_LONG_READ_TR_DISTRIBUTIONS	pending_DNA_population_reference	long-read allele-length and LPS summaries	VERSION_PIN_REQUIRED	COVERAGE_EXPANSION_PENDING
ADOTTO_COMPREHENSIVE_CATALOG	pending_DNA_catalog_and_population_reference	HPRC/HGSVC/1KGP long-read catalog universe	VERSION_PIN_REQUIRED	COVERAGE_EXPANSION_PENDING
HPRC_RELEASE2	pending_DNA_assembly_validation	haplotype-resolved assemblies	RELEASE_PIN_REQUIRED	TARGETED_HARD_CASE_VALIDATION
EOF

cat > "$COVERAGE_POLICY" <<EOF
policy_id	rule	status	detail
COV01	SHOW_COMPARABLE_NUMERATOR_AND_11042_DENOMINATOR	FROZEN	Every candidate and review table must state how many of the 11042 observed P0/P1 loci were population-comparable.
COV02	CURRENT_FIVE_ARE_PILOT_SUBSET_CANDIDATES	FROZEN	The five max-exceedance loci arose only inside the 403-locus RepeatCatalogs/1KG exact subset.
COV03	NO_FINAL_RANKING_BEFORE_COVERAGE_EXPANSION	HOLD	Final ranking remains blocked until population coverage is substantially expanded and weights are calibrated.
COV04	NO_SIMPLE_OVERLAP_AUTOMATIC_CROSSWALK	FROZEN	Locus overlap alone never authorizes population-distribution transfer.
COV05	TRATLAS_API_REQUIRES_TR_ID_CROSSWALK	FROZEN	Only exact or validated biologically-equivalent TR IDs may be queried and interpreted.
COV06	LIVE_API_RESPONSES_REQUIRE_IMMUTABLE_CACHE	FROZEN	Store URL, retrieval time, headers, JSON, and SHA256 for every response.
COV07	NO_DNA_GENOTYPE_OR_PATHOGENICITY_FROM_RNA	FROZEN	DNA references provide context only; RNA molecules are expression-biased and not a personal DNA genotype sample.
COV08	SPECIALIZED_4513_REMAINS_PAUSED	HOLD	Do not restart the large specialized-motif implementation before the coverage architecture is resolved.
EOF

cat > "$CHECKPOINT_TSV" <<EOF
milestone	status	summary	path
p01_event_to_locus_backbone	COMPLETE_PASS	exact_events=23867;unique_reads=23867;loci=11042;single_read_loci=7390;multi_read_loci=3652	$BACKBONE_QC
p01_cdna_molecule_signatures	COMPLETE_PASS	read_collapse=NO;independent_molecule_count=NOT_ESTIMATED;unique_read_support_proxy_only	$SIGNATURE_QC
repeatcatalogs_1kg_adapter	COMPLETE_PASS	components=174300;chromosomes=chr1-22,chrX	$STAGE6N_QC
repeatcatalogs_1kg_population_pilot	COMPLETE_PASS	comparable_loci=403/11042;scope=PILOT_SUBSET_ONLY	$STAGE6O_QC
single_read_above_max_technical_audit	COMPLETE_PASS	candidate_loci=5;all_locus_reads=56;multi_read_above_max_loci=0;final_outlier=NOT_RUN	$STAGE6P_QC
precontrol_multisource_matrix	COMPLETE_PASS	matrix_loci=11042;final_ranking=NOT_RUN	$STAGE6Q_QC
repeatcatalogs_crosswalk_coverage	COMPLETE_PASS	exact=403;safe_candidate=1;manual=52;no_catalog=10586;coverage_gate=HOLD	$STAGE6R_QC
tratlas_zenodo_primary_prefix	VALIDATION_ONLY	rows=50000;tr_ids=1907;observed_scope=chr1_prefix;not_genome_wide	$TRATLAS_SCHEMA_QC
tratlas_public_browser_api	DISCOVERED	main_population_and_sub_population_JSON_endpoints;chr15_TR137069_probe_PASS	$API_PROBE_DEST
tratlas_api_zenodo_crossvalidation	SEMANTIC_PASS	strict_qc=FAIL;25_groups;nonzero_frequency_mismatch=0;two_API_zero_bins_omitted_by_Zenodo	$SEMANTIC_XVAL
population_coverage_gate	HOLD	RepeatCatalogs_exact_coverage=403/11042=3.6497011%;final_ranking_blocked	$COVERAGE_POLICY
specialized_motif_4513	HOLD	large_implementation_not_started	$CHECKPOINT_DIR
step11_overall	IN_PROGRESS	next=TRAtlas_crosswalk_API_cache_AoU_Adotto_HPRC_coverage_expansion	$CHECKPOINT_DIR
EOF

cat > "$CHECKPOINT_MD" <<EOF
# RNA-TR-Scout Step 11 checkpoint — population coverage and TR-Atlas API

- Created: $(date -Is)
- Run: \`$RUN_ID\`
- Package: \`rnatr-scout $installed_version\`
- Step 11: **in_progress**
- Final ranking: **blocked by coverage expansion gate**
- Specialized motif 4,513: **paused**

## Core RNA locus state

- Exact-span events / unique read IDs: **23,867 / 23,867**
- P0/P1 observed loci in the 100k-read pilot: **11,042**
- Single-read loci: **7,390**
- Multiple-read loci: **3,652**
- Unique-read support is not an independent RNA-molecule count.

## RepeatCatalogs / 1KG coverage

- Exact population-comparable loci: **403 / 11,042 (3.6497011%)**
- Provisional biologically-equivalent safe candidate: **1**
- Manual-review only: **52**
- No RepeatCatalogs component at the query interval: **10,586**
- Projected exact + safe before validation: **404 / 11,042 (3.6587575%)**

The principal cause of low coverage is catalog-universe mismatch, not unresolved motif rotation or boundary normalization.

## Five current population exceedances

The five loci were found only inside the 403-locus exact-comparable subset.

- All five were single-read exceedances.
- Multi-read above-max loci: 0.
- Technical audit covered 5 loci / 56 reads.
- No final outlier, personal DNA genotype, pathogenicity, or final ranking call was made.

They remain:

\`PILOT_SUBSET_CANDIDATES_WITHIN_403_OF_11042_LOCI\`

## TR-Atlas

### Pinned Zenodo source

Zenodo version DOI \`10.5281/zenodo.10806728\` contains five 10,000-row primary-frequency prefix exports covering only the beginning of chr1.

- rows: 50,000
- unique TR IDs: 1,907
- coordinate-addressable IDs: 1,906

This source is retained as a pinned validation anchor, not a genome-wide frequency distribution.

### Public browser API

The current TR-Atlas browser calls public JSON endpoints under the legacy \`TRgnomAD/api\` path.

- \`main_population_All.php?trId={TR_ID}&datasetId=main_pop_test\`
- \`sub_population_All.php?trId={TR_ID}&datasetId=sub_pop_test\`

A chr15 locus (\`TR137069\`) was retrieved successfully.

The API–Zenodo chr1 crossvalidation compared 5 TR IDs × 5 populations.

- 86 common allele-frequency rows: exact float match
- nonzero frequency mismatches: 0
- two differences: API explicitly contained allele 6 with frequency 0 for TR406 South Asian / East Asian; the Zenodo export omitted the zero-frequency row
- original strict QC remains FAIL
- semantic addendum: \`PASS_ZERO_FREQUENCY_BIN_REPRESENTATION_DIFFERENCE\`

The live API has no explicit version identifier. Every response must be cached with URL, retrieval timestamp, headers, JSON, and SHA256. Exact allele denominators are not yet available.

## DNA versus RNA

The planned population references are DNA-derived: RepeatCatalogs/1KG, TR-Atlas, AoU, Adotto, HPRC, and STRchive thresholds.

DNA/RNA differences materially affect interpretation:

- expression and tissue specificity
- isoform/splicing boundaries
- 3-prime bias and 5-prime truncation
- allele-specific expression
- transcript instability or NMD
- ONT error
- cDNA RT/PCR slippage and chimera
- RNA editing

Therefore, DNA distributions provide context; RNA does not directly reveal a personal DNA genotype.

However, the present 3.65% RepeatCatalogs coverage problem is mainly a catalog-universe problem: 10,586 RNA loci had no RepeatCatalogs component at the query interval, whereas only small numbers were boundary, motif, compound, or nearby-design mismatches.

## Next required work

1. Acquire and SHA-pin the TR-Atlas GRCh38 BigBed track:
   \`hg38_version7_913341_TRs_wb.bb\`
2. Audit its schema and construct:
   - exact TR ID crosswalk
   - validated biologically-equivalent safe crosswalk
   - manual review
   - no TR-Atlas coverage
3. Query only safely mapped TR IDs through the main-population API using a conservative, resumable cache.
4. Add AoU long-read distributions and Adotto catalog/population resources.
5. Use HPRC assemblies for hard manual cases.
6. Define the quantitative coverage-gate release condition in Pro.
7. Add same-protocol RNA controls before final ranking.

## Frozen restrictions

- Always show comparable numerator / 11,042 denominator.
- Do not call the current five genome-wide candidates.
- Do not infer DNA genotype or pathogenicity from RNA.
- Do not use simple overlap as an automatic crosswalk.
- Do not reconstruct P95/P99/max from TRDS.
- Do not treat the live API as versioned without a cached immutable snapshot.
- Do not start final ranking or specialized motif 4,513 before the gate is released.

## Machine-readable files

- Checkpoint: \`$CHECKPOINT_TSV\`
- Source registry: \`$SOURCE_REGISTRY\`
- Coverage policy: \`$COVERAGE_POLICY\`
- TR-Atlas semantic validation: \`$SEMANTIC_XVAL\`
- Artifact manifest: \`$ARTIFACT_MANIFEST\`
EOF

cat > "$PROVENANCE_TSV" <<EOF
field	value
checkpoint_version	$CHECKPOINT_VERSION
created_at	$(date -Is)
run_id	$RUN_ID
rnatr_scout_version	$installed_version
script_source	$SELF
script_destination	$SCRIPT_DEST
script_sha256	$script_sha256
tracker_db_sha256_before	$tracker_db_before
repeatcatalogs_exact_coverage	403/11042
coverage_gate	HOLD
tratlas_strict_crossvalidation_status	FAIL
tratlas_semantic_crossvalidation_status	PASS_ZERO_FREQUENCY_BIN_REPRESENTATION_DIFFERENCE
final_ranking_executed	0
specialized_large_implementation_started	false
EOF

RNATR_PROJECT_ROOT="$PROJECT_ROOT" \
python -m unittest discover \
  -s "$PROJECT_ROOT/tests/unit" \
  -v > "$UNIT_TEST_LOG" 2>&1

grep -qx 'OK' "$UNIT_TEST_LOG" || {
  cat "$UNIT_TEST_LOG" >&2
  echo "ERROR: unit tests failed" >&2
  exit 1
}

mv "$STAGE_DIR" "$CHECKPOINT_DIR"

# Switch all checkpoint-local variables from the staging path to the final
# immutable checkpoint path, and repair any staging paths embedded in the
# human/machine-readable checkpoint files.
CHECKPOINT_TSV="$CHECKPOINT_DIR/population_reference_coverage_checkpoint.tsv"
CHECKPOINT_MD="$CHECKPOINT_DIR/RNA-TR-Scout_handoff.md"
SEMANTIC_XVAL="$CHECKPOINT_DIR/tratlas_api_zenodo_semantic_validation.tsv"
SOURCE_REGISTRY="$CHECKPOINT_DIR/population_reference_source_registry.tsv"
COVERAGE_POLICY="$CHECKPOINT_DIR/population_coverage_gate_policy.tsv"
PROVENANCE_TSV="$CHECKPOINT_DIR/provenance/checkpoint_provenance.tsv"
ARTIFACT_MANIFEST="$CHECKPOINT_DIR/population_reference_coverage_artifact_manifest.tsv"
UNIT_TEST_LOG="$CHECKPOINT_DIR/provenance/unit_tests.log"

python - "$CHECKPOINT_DIR" "$STAGE_DIR" <<'PYPATHFIX'
from __future__ import annotations
import sys
from pathlib import Path

checkpoint_dir = Path(sys.argv[1])
stage_dir = sys.argv[2]

for relative in (
    "population_reference_coverage_checkpoint.tsv",
    "RNA-TR-Scout_handoff.md",
    "provenance/checkpoint_provenance.tsv",
):
    path = checkpoint_dir / relative
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace(stage_dir, str(checkpoint_dir)),
        encoding="utf-8",
    )
PYPATHFIX

NOTE="Population/reference-control branch checkpoint。P0/P1 exact-span 23,867 unique-read eventsを11,042 lociへ統合。RepeatCatalogs/1KG exact population comparisonは403/11,042 loci（3.6497%）のみ。Stage 6Rはexact 403、safe候補1、manual 52、no-catalog 10,586でPASSし、coverage gateはHOLD。5 max-exceedance lociは403-locus subset内のsingle-read pilot candidatesで、56-read技術監査済み、final outlier/rankingなし。TR-Atlas public browser APIを特定しchr15 frequency取得PASS。chr1 Zenodo 5 TR×5集団照合は非zero frequency mismatch 0、APIのzero-frequency bin 2行がZenodoで省略された表現差のみ。次はTR-Atlas全ゲノムTR-ID crosswalk、cached API取得、AoU/Adotto/HPRCによるcoverage拡張。specialized motif 4,513は停止、Step 11はin_progress。詳細: $CHECKPOINT_DIR"

python "$TRACKER" mark 11 in_progress --note "$NOTE"
python "$TRACKER" export

tracker_db_after="$(
  if [[ -f "$TRACKER_DB" ]]; then
    sha256sum "$TRACKER_DB" | awk '{print $1}'
  else
    printf '.'
  fi
)"

if [[ -f "$TRACKER_DB" ]]; then
  cp "$TRACKER_DB" "$CHECKPOINT_DIR/provenance/rnatr_build_tracker.post_update.sqlite"
fi
printf 'tracker_db_sha256_after\t%s\n' "$tracker_db_after" \
  >> "$CHECKPOINT_DIR/provenance/checkpoint_provenance.tsv"

for exported in \
  rnatr_build_steps.tsv \
  rnatr_build_decisions.tsv \
  rnatr_build_artifacts.tsv
do
  if [[ -s "$TRACKER_ROOT/$exported" ]]; then
    cp "$TRACKER_ROOT/$exported" "$CHECKPOINT_DIR/tracker_exports/$exported"
  fi
done

count_rows() {
  local path="$1"
  case "$path" in
    *.tsv.gz)
      gzip -cd "$path" | awk 'END {print (NR > 0 ? NR - 1 : 0)}'
      ;;
    *.tsv)
      awk 'END {print (NR > 0 ? NR - 1 : 0)}' "$path"
      ;;
    *)
      printf '.\n'
      ;;
  esac
}

add_artifact() {
  local artifact="$1"
  local path="$2"
  [[ -s "$path" ]] || return 0
  printf '%s\t%s\t%s\t%s\t%s\n' \
    "$artifact" \
    "$(count_rows "$path")" \
    "$(stat -c '%s' "$path")" \
    "$(sha256sum "$path" | awk '{print $1}')" \
    "$path" \
    >> "$ARTIFACT_MANIFEST"
}

printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n' > "$ARTIFACT_MANIFEST"

add_artifact checkpoint_table "$CHECKPOINT_DIR/population_reference_coverage_checkpoint.tsv"
add_artifact handoff_summary "$CHECKPOINT_DIR/RNA-TR-Scout_handoff.md"
add_artifact source_registry "$CHECKPOINT_DIR/population_reference_source_registry.tsv"
add_artifact coverage_policy "$CHECKPOINT_DIR/population_coverage_gate_policy.tsv"
add_artifact tratlas_semantic_validation "$CHECKPOINT_DIR/tratlas_api_zenodo_semantic_validation.tsv"
add_artifact checkpoint_provenance "$CHECKPOINT_DIR/provenance/checkpoint_provenance.tsv"
add_artifact unit_tests "$CHECKPOINT_DIR/provenance/unit_tests.log"
add_artifact tracker_db_pre_update "$CHECKPOINT_DIR/provenance/rnatr_build_tracker.pre_update.sqlite"
add_artifact tracker_db_post_update "$CHECKPOINT_DIR/provenance/rnatr_build_tracker.post_update.sqlite"

add_artifact backbone_qc "$BACKBONE_QC"
add_artifact signature_qc "$SIGNATURE_QC"
add_artifact stage6n_qc "$STAGE6N_QC"
add_artifact stage6o_qc "$STAGE6O_QC"
add_artifact stage6p_qc "$STAGE6P_QC"
add_artifact stage6q_qc "$STAGE6Q_QC"
add_artifact stage6r_qc "$STAGE6R_QC"
add_artifact tratlas_schema_qc "$TRATLAS_SCHEMA_QC"
add_artifact tratlas_xval_qc "$TRATLAS_XVAL_QC"
add_artifact tratlas_xval_group "$TRATLAS_XVAL_GROUP"
add_artifact tratlas_xval_detail "$TRATLAS_XVAL_DETAIL"

add_artifact all_locus_overview "$STAGE6O_ROOT/loci/p01_locus.exact_span_repeat_length_overview.tsv"
add_artifact one_kg_population_features "$STAGE6O_ROOT/loci/p01_locus.repeatcatalogs_1kg_population_features.tsv.gz"
add_artifact five_locus_technical_summary "$STAGE6P_ROOT/tables/single_read_above_max.locus_summary.tsv"
add_artifact multisource_matrix "$STAGE6Q_ROOT/matrix/p01_locus.multisource_context_matrix.tsv.gz"
add_artifact crosswalk_all_loci "$STAGE6R_ROOT/tables/p01_locus.repeatcatalogs_crosswalk_coverage_audit.tsv.gz"
add_artifact crosswalk_safe "$STAGE6R_ROOT/tables/p01_locus.repeatcatalogs_safe_equivalence_candidates.tsv"
add_artifact crosswalk_manual "$STAGE6R_ROOT/tables/p01_locus.repeatcatalogs_manual_review_candidates.tsv.gz"
add_artifact crosswalk_no_catalog "$STAGE6R_ROOT/tables/p01_locus.repeatcatalogs_no_catalog_coverage.tsv.gz"

add_artifact checkpoint_script "$SCRIPT_DEST"
for name in \
  11cr_audit_repeatcatalogs_crosswalk_coverage_v0.1.2.sh \
  11cs_probe_tratlas_frequency_js_endpoints_v0.1.0.sh \
  11ct_probe_tratlas_api_single_locus_v0.1.1.sh \
  11cu_validate_tratlas_api_against_zenodo_chr1_v0.1.0.sh
do
  add_artifact "$name" "$PROJECT_ROOT/scripts/$name"
done

if [[ -d "$JS_PROBE_DEST" ]]; then
  while IFS= read -r -d '' path; do
    add_artifact "tratlas_js_probe_$(basename "$path")" "$path"
  done < <(find "$JS_PROBE_DEST" -type f -print0 | sort -z)
fi

if [[ -d "$API_PROBE_DEST" ]]; then
  while IFS= read -r -d '' path; do
    add_artifact "tratlas_api_probe_$(basename "$path")" "$path"
  done < <(find "$API_PROBE_DEST" -type f -print0 | sort -z)
fi

for exported in "$CHECKPOINT_DIR"/tracker_exports/*.tsv; do
  [[ -e "$exported" ]] || continue
  add_artifact "tracker_export_$(basename "$exported")" "$exported"
done

python - "$ARTIFACT_MANIFEST" <<'PYVERIFY'
from __future__ import annotations
import csv
import hashlib
import sys
from pathlib import Path

manifest = Path(sys.argv[1])
errors = []

with manifest.open("r", encoding="utf-8", newline="") as handle:
    reader = csv.DictReader(handle, delimiter="\t")
    required = {"artifact", "bytes", "sha256", "path"}
    if reader.fieldnames is None or not required.issubset(reader.fieldnames):
        raise SystemExit("invalid artifact manifest header")

    for row in reader:
        path = Path(row["path"])
        if not path.is_file():
            errors.append(f"missing:{path}")
            continue
        if path.stat().st_size != int(row["bytes"]):
            errors.append(f"bytes:{path}")
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != row["sha256"]:
            errors.append(f"sha256:{path}")

if errors:
    raise SystemExit("\n".join(errors[:20]))
PYVERIFY

rm -f "$LATEST_LINK" "$LATEST_COVERAGE_LINK"
ln -s "$CHECKPOINT_DIR" "$LATEST_LINK"
ln -s "$CHECKPOINT_DIR" "$LATEST_COVERAGE_LINK"

echo "===== POPULATION-REFERENCE COVERAGE CHECKPOINT ====="
column -ts $'\t' "$CHECKPOINT_DIR/population_reference_coverage_checkpoint.tsv"

echo
echo "===== TR-ATLAS SEMANTIC VALIDATION ====="
column -ts $'\t' "$CHECKPOINT_DIR/tratlas_api_zenodo_semantic_validation.tsv"

echo
echo "===== COVERAGE GATE POLICY ====="
column -ts $'\t' "$CHECKPOINT_DIR/population_coverage_gate_policy.tsv"

echo
echo "===== TRACKER STEP 11 ====="
python "$TRACKER" show 11

echo
echo "===== TRACKER STATUS ====="
python "$TRACKER" status

echo
echo "===== CHECKPOINT LINKS ====="
printf 'latest_step11_checkpoint\t%s\n' "$(readlink -f "$LATEST_LINK")"
printf 'latest_step11_population_reference_coverage_checkpoint\t%s\n' \
  "$(readlink -f "$LATEST_COVERAGE_LINK")"

echo
echo "===== COMPLETE ====="
echo "Installed script: $SCRIPT_DEST"
echo "Checkpoint:       $CHECKPOINT_DIR"
echo "Handoff:          $CHECKPOINT_DIR/RNA-TR-Scout_handoff.md"
echo "Manifest:         $CHECKPOINT_DIR/population_reference_coverage_artifact_manifest.tsv"
echo "Tracker DB before:$tracker_db_before"
echo "Tracker DB after: $tracker_db_after"
echo
echo "Step 11 remains in_progress. Final ranking and specialized motif 4,513 remain blocked."
