# RNA-TR-Scout future-extensibility boundary contract v0.1.0

## Status

**PENDING_FINAL_EXACT_ORIGINAL_AUDIT_BEFORE_CORE_FREEZE_GO**

This contract preserves post-Freeze extension boundaries without expanding the current pre-Freeze implementation scope. ROI mode, cohort storage, viewers, alternate assemblies, new platform adapters, and alternate physical output formats are not required before Freeze.

## TARGET_SELECTION_EXTENSION_BOUNDARY

Future target-selection profiles may accept `--regions-bed`, `--locus-list`, disease-repeat panels, known-locus/force-analysis lists, or user-supplied catalogs.

The preferred model subsets target/locus resources while retaining the full read/alignment resources needed by assignment semantics. A targeted analysis of a locus must be capable of scientific parity comparison with catalog-wide analysis of the same locus and input.

The current catalog-wide profile is a validated baseline, not a permanent requirement that all runs use one fixed catalog or discover a locus naturally before it can be evaluated.

## MULTISAMPLE_NAMESPACE_EXTENSION_BOUNDARY

Current Core results are single-run packages with explicit `run_id` and `sample_id` in the portable result manifest. Future cohort identity may safely namespace technical reads as:

`(core_result_manifest_sha256, sample_id, read_id)`

and loci by checksum-bound catalog/reference identity.

The frozen Core does not need a pre-Freeze cohort database. Post-Freeze sidecars or indexed stores may support sample × locus, sample × molecule, and sample × locus × isoform / haplotype / platform views without rewriting the five Core source-of-truth tables.

## PHYSICAL_STORAGE_ABSTRACTION_BOUNDARY

Freeze the logical scientific table model, stable IDs, column semantics, joins, missingness/censoring semantics, manifest provenance, and validation guarantees.

Current TSV/TSV.gz files are the validated reference serialization. They are not the only permitted future physical representation. Parquet, indexed tables, DuckDB/disk-backed query, or other representations may be added when they preserve logical parity, provenance, reverse traceability, and the applicable golden/validator contract.

## READ_INSPECTION_REVERSE_TRACE_BOUNDARY

The frozen interface must preserve logical reverse traceability:

`read_id -> target/locus assignment -> assignment basis/geometry -> read/genome projection -> repeat window/motif -> caller evidence and repeat measurement/status`.

A future inspect-read viewer may use formal outputs, stable IDs, logical resources, or a checksum-bound reconstruction procedure. Historical Stage-internal filenames/paths are not permanent public contracts.

## FORCED_LOCUS_ANALYSIS_EXTENSION_BOUNDARY

Known-locus or force-analysis workflows should reuse the target-selection boundary. They must be able to evaluate an explicitly selected locus without requiring that it first emerge naturally from catalog-wide candidate discovery.

Where scientifically comparable, the same locus and read resources should support targeted-versus-catalog-wide parity checks.

## REFERENCE_ASSEMBLY_CATALOG_ADAPTER_BOUNDARY

GRCh38 and the currently pinned catalogs remain the validated scientific baseline. Assembly, reference, target catalog, and annotation identities must remain versioned and checksum-bound.

The platform-independent Core contract must not assert that only GRCh38 or one catalog serialization is valid. Future assemblies, updated/custom catalogs, and alternate catalog adapters may be added behind explicit versioned resource contracts and validation.

## OUTPUT_ADAPTER_BOUNDARY

The five logical Core tables, stable IDs, semantics, joins, manifest provenance, and validation guarantees are frozen. TSV/TSV.gz is the current reference export, not an immutable universal storage backend.

Future output adapters may produce Parquet, indexed tables, DuckDB-accessible stores, or other query-oriented representations while preserving scientific parity and reverse traceability.

## Final Freeze audit requirement

The final exact-original audit must classify each boundary as one of:

- `BOUNDARY_OPEN`
- `CURRENT_PROFILE_SCOPED`
- `POST_FREEZE_EXTENSION`
- `HARD_COUPLING_REQUIRES_REMEDIATION`

Only a demonstrated hard coupling that unnecessarily blocks a listed extension should trigger pre-Freeze remediation.

## Scope control

**No pre-Freeze implementation** of ROI mode, force-analysis, cohort databases, viewers, alternate storage backends, alternate assemblies/catalog adapters, or new export formats is required by this contract.
