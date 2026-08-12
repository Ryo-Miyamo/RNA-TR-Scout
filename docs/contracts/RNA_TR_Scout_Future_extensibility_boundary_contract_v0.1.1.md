# RNA-TR-Scout future-extensibility boundary contract v0.1.1

## Status

`ACCEPTED_FINAL_EXACT_ORIGINAL_AUDIT`

The final exact-original audit found no hard coupling requiring pre-Freeze Core code or
schema remediation.

## Final classifications

| Boundary | Classification | Pre-Freeze remediation |
|---|---|---|
| `TARGET_SELECTION_EXTENSION_BOUNDARY` | `CURRENT_PROFILE_SCOPED` | not required |
| `MULTISAMPLE_NAMESPACE_EXTENSION_BOUNDARY` | `BOUNDARY_OPEN` | not required |
| `PHYSICAL_STORAGE_ABSTRACTION_BOUNDARY` | `POST_FREEZE_EXTENSION` | not required |
| `READ_INSPECTION_REVERSE_TRACE_BOUNDARY` | `BOUNDARY_OPEN` | not required |
| `FORCED_LOCUS_ANALYSIS_EXTENSION_BOUNDARY` | `POST_FREEZE_EXTENSION` | not required |
| `REFERENCE_ASSEMBLY_CATALOG_ADAPTER_BOUNDARY` | `CURRENT_PROFILE_SCOPED` | not required |
| `OUTPUT_ADAPTER_BOUNDARY` | `POST_FREEZE_EXTENSION` | not required |

`HARD_COUPLING_REQUIRES_REMEDIATION`: 0/7.

## Boundary meanings

### Target selection

The current version is catalog-wide. Future ROI, locus-list, disease-panel or user-catalog
profiles may subset target resources behind a versioned contract and should permit
same-locus parity comparison with catalog-wide analysis.

### Multi-sample namespace

Current packages carry `run_id` and `sample_id`. Cross-package read identity is anchored by
`(core_result_manifest_sha256, sample_id, read_id)` and locus identity by checksum-bound
catalog/reference identity. Cohort stores remain sidecars or indexed extensions.

### Physical storage and output adapters

The five logical tables, IDs, joins, semantics, provenance and validation guarantees are
frozen. TSV/TSV.gz is the current validated reference serialization, not the only future
physical representation. Parquet, DuckDB or indexed/query exports require logical parity and
applicable golden/validator checks.

### Read inspection

The accepted logical trace is:

`read_id -> assignment -> basis/geometry -> projection/window -> motif/caller -> evidence`.

A future viewer may consume formal outputs or use checksum-bound reconstruction; historical
Stage filenames are not frozen.

### Forced-locus analysis

Known-locus/force-analysis is not implemented. It may be added through the target-selection
boundary without requiring natural catalog-wide discovery first.

### Reference/assembly/catalog adapters

GRCh38 and current SHA-bound TRExplorer/STRchive resources are the validated profile.
Future assemblies/catalogs require explicit versioned resources and validation; the current
profile is not a universal restriction.

## Scope control

No pre-Freeze implementation of ROI mode, force-analysis, cohort databases, viewers,
alternate storage backends, alternate assemblies/catalog adapters or new output formats is
required by this contract.
