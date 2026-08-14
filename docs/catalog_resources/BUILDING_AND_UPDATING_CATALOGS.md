# Building and updating RNA-TR-Scout catalogs

## Who needs this document?

Most RNA-TR-Scout users do not need to build a catalog.

The standard validated workflow uses the small RNA-TR-Scout catalog bundle prepared from
TRExplorer and STRchive. Users do not need the complete upstream TRExplorer or STRchive source
datasets for ordinary analysis, and they do not need to type or compare SHA-256 values manually.
RNA-TR-Scout uses checksums internally to identify and verify the validated resource profile.

This document is primarily for:

- reproducibility and provenance review;
- RNA-TR-Scout developers;
- advanced users who intentionally want to rebuild the catalog from newer upstream resources; or
- investigators who need to audit how the validated catalog was derived.

The historical Stage 09 scripts record the accepted build semantics, but they contain
developer-local paths and are not yet a polished public `rnatr-catalog build` interface.

## Standard validated catalog

The validated GRCh38 runtime catalog is a processed RNA-TR-Scout resource bundle rather than a copy
of the complete upstream datasets.

Its upstream basis is:

- **TRExplorer v2.0**
- **STRchive source commit**
  `88502a64bd47ae464b908757122cc7e4bbeed8c8`
  - the `CITATION.cff` at that commit reports version **2.24.2**
  - that version metadata reports release date **2026-07-23**

Important STRchive provenance detail: the Git tag `v2.24.2` itself points to commit
`48c509371d3804b491787321f6f4b2e99758e69b`, whereas the RNA-TR-Scout source snapshot used for
the frozen disease-region derivation is source commit
`88502a64bd47ae464b908757122cc7e4bbeed8c8`, whose repository version metadata still reports
2.24.2. Therefore RNA-TR-Scout records the exact source commit rather than assuming that the tag
name alone identifies the source snapshot.

The frozen RNA-TR-Scout profile contains:

- 349,410 TRExplorer-derived analysis-region rows;
- 80 STRchive-derived disease-region rows; and
- 349,490 combined mapping-target rows.

The five validated runtime catalog artifacts total approximately 23.5 MB, much smaller than the
complete upstream resources.

## Why RNA-TR-Scout keeps checksums

Checksums are mainly an internal reproducibility mechanism, not a user-facing requirement.

For example, the STRchive-derived runtime file contains the 80 disease regions after RNA-TR-Scout
selection/transformation. Its SHA-256 identifies that exact processed file. This is different from
the upstream STRchive version:

- upstream version/commit answers: **which STRchive source snapshot was used?**
- processed-file SHA-256 answers: **which exact RNA-TR-Scout runtime artifact was produced and
  validated?**

Ordinary users should normally never need to inspect these hashes. The installer/runtime validator
uses them automatically.

## Exact validated runtime artifacts

For reproducibility, the exact frozen artifacts are recorded here:

| Role | Frozen artifact | SHA-256 |
|---|---|---|
| TRExplorer analysis regions | `TRExplorer_v2.rnatr_pilot_analysis_regions.final.tsv.gz` | `562802c3757785d0ef7d4b7b10ac5582b53bdce1d380d76dccb15711a2ebf9d3` |
| STRchive disease regions | `STRchive_disease_regions.final.tsv.gz` | `056ae07de7b8f6299fadcabfefb7b596bc2c5a35591c06870dbed4d7fb519796` |
| combined mapping targets, BED | `RNA-TR-Scout_v0.3.mapping_target_regions.bed.gz` | `6ec444b0ffcb9da4452b24d1654ed6c4b945c3cd3e8379e4e4cbe6e72931cfe2` |
| combined mapping targets, BED index | `RNA-TR-Scout_v0.3.mapping_target_regions.bed.gz.tbi` | `9803a3b268e9a7ca30edbf4c312a0d60b90a9bb9c34fdcd243348caa9bc4e77d` |
| combined mapping targets, TSV | `RNA-TR-Scout_v0.3.mapping_target_regions.tsv.gz` | `3edffe6f5d31922ca0c58759186639e77f51c48745ac5e22ad3aad0a010fec75` |

Exact equality to these identities means `VALIDATED_CATALOG_PROFILE` for this frozen profile.

## TRExplorer-derived analysis regions

The validated TRExplorer branch was built from TRExplorer v2 resources. Two important upstream
assets recorded during release engineering are:

- `TRExplorer.repeat_catalog_v2.hg38.1_to_1000bp_motifs.EH.with_annotations.json.gz`
- `TRExplorer.variation_clusters_and_isolated_TRs_v2.hg38.TRGT.bed.gz`

Historical builder:

- `scripts/09a_build_trexplorer_rnatr_master_tables_v3.sh`

This builder converted the annotated TRExplorer catalog into the RNA-TR-Scout locus master and
converted the TRExplorer variation-cluster / isolated-TR representation into an RNA-TR-Scout
analysis-region master.

## RNA-oriented selection

Historical builder:

- `scripts/09c_build_rnatr_priority_tiers_and_pilot_core.sh`

This stage combined the TRExplorer locus/analysis-region data with RNA/GENCODE annotation context
and RNA-TR-Scout selection rules. For the validated profile, the coordinate/reference context is
GRCh38 with GENCODE v50.

An upstream TRExplorer locus is not automatically equivalent to an RNA-TR-Scout runtime target.
RNA-TR-Scout adds its own region, identity, analysis-mode, selection, and validation semantics.

## STRchive-derived disease regions

The frozen disease-region runtime artifact contains 80 rows.

The RNA-TR-Scout source provenance for this branch is:

- upstream repository: `dashnowlab/STRchive`
- source commit: `88502a64bd47ae464b908757122cc7e4bbeed8c8`
- version metadata at that source commit: `2.24.2`
- version metadata date: `2026-07-23`

RNA-TR-Scout freezes the derived disease-region artifact rather than depending on whatever STRchive
content is current on the day a future user installs the software.

## Final combined mapping target

Historical finalizer:

- `scripts/09f2_resume_finalize_pilot_catalog.sh`

The final mapping target is a **combined TRExplorer + STRchive target set**.

The accepted final construction semantics are:

1. Read the final TRExplorer analysis-region table.
2. Emit TRExplorer rows into the common RNA-TR-Scout 8-column target schema.
3. Mark those rows with `target_source=TRExplorer`.
4. Read the final STRchive disease-region table.
5. Emit disease-region rows into the same target schema.
6. Mark those rows with `target_source=STRchive` and preserve the disease-region analysis hint and
   matched TRExplorer locus identifier when available.
7. Concatenate the two record sets.
8. Sort them using the accepted GRCh38 genome order.
9. bgzip the TSV representation.
10. bgzip the BED representation.
11. tabix-index the BED.

The common columns are:

- `chrom`
- `start`
- `end`
- `target_region_id`
- `target_source`
- `region_type`
- `analysis_mode`
- `representative_locus_id`

The finalization step preserves source identity rather than collapsing everything into an anonymous
coordinate union.

Accepted row counts:

- TRExplorer: **349,410**
- STRchive: **80**
- combined: **349,490**

## Stage16K reconstruction

Post-Freeze release engineering reconstructed the three derived mapping-target artifacts from the
two frozen source-side runtime artifacts using the historical final builder semantics.

Stage16K result:

- mapping-target TSV exact SHA: PASS
- mapping-target BED exact SHA: PASS
- mapping-target TBI exact SHA: PASS
- exact reconstructed files: 3/3
- uncompressed TSV content: exact
- uncompressed BED content: exact

This demonstrates that the final mapping-target files can be reconstructed exactly from the frozen
analysis-region and disease-region runtime artifacts.

## What standard users install

Standard users should receive/use the RNA-TR-Scout validated catalog bundle, which contains the
five compact runtime artifacts above. They do **not** need to download and process the complete
TRExplorer or STRchive source distributions.

The current source-checkout installer consumes this prebuilt catalog bundle and verifies the exact
resource identities automatically.

The full upstream resources are needed only when someone intentionally wants to:

- rebuild from a newer upstream release;
- audit the transformation from source data;
- change RNA-TR-Scout catalog-selection rules; or
- construct a new catalog profile.

## Advanced: incorporating newer TRExplorer or STRchive releases

A newer upstream release is allowed as a future/custom input, but it should first be adapted into a
new RNA-TR-Scout catalog profile rather than being treated as byte-for-byte interchangeable with
the already validated runtime artifacts.

The intended future workflow is:

```text
new TRExplorer / STRchive source
        |
        v
record upstream version / commit / source provenance
        |
        v
RNA-TR-Scout catalog importer / adapter
        |
        v
normalize RNA-TR-Scout catalog schemas
        |
        v
RNA-oriented selection + disease-region transformation
        |
        v
catalog validation
        |
        v
combined mapping-target construction
        |
        v
manifest + checksums + provenance
        |
        v
CUSTOM_COMPATIBLE_CATALOG
```

The adaptation/validation step is used because newer upstream resources may change coordinates,
identifiers, motif or region definitions, overlap relationships, or disease-locus representation.
Those changes may be valid, but they should be represented explicitly as a new catalog profile
instead of being confused with the already validated one.

At minimum, a future catalog adapter/validator should check:

- coordinate/reference compatibility;
- required schema and field types;
- stable and unique RNA-TR-Scout locus/region identifiers;
- motif representation and required motif fields;
- interval validity;
- duplicate identifiers;
- TRExplorer analysis-region semantics;
- STRchive disease-region semantics;
- overlap/alias consequences that can affect technical candidate multiplicity;
- combined target-source provenance; and
- output integrity and checksums.

## Catalog compatibility classes

### `VALIDATED_CATALOG_PROFILE`

The exact frozen five-file catalog profile validated with this RNA-TR-Scout release profile.

### `CUSTOM_COMPATIBLE_CATALOG`

A separately built catalog that passes the RNA-TR-Scout catalog adaptation/validation path. It may
be allowed to execute, but it is outside the exact golden-validation scope of the frozen validated
profile.

### `INCOMPATIBLE_CATALOG`

A catalog that fails required coordinate, schema, identity, or other compatibility checks.

## Portable custom catalog builder status

A polished public command such as:

```bash
rnatr-catalog build ...
```

has **not yet** been promoted as a supported public interface.

Until that portable adapter/builder exists, the historical Stage 09 scripts should be treated as
provenance for the validated build, not as a promise that arbitrary future TRExplorer/STRchive
versions can be processed unchanged.

## Release and licensing note

Technical reconstructability and public redistribution rights are separate issues. The validated
catalog bundle records third-party provenance and notices separately from the runtime compatibility
logic.

Documenting or later implementing the post-Freeze custom-catalog path does not alter the frozen
RNA-TR-Scout scientific Core.
