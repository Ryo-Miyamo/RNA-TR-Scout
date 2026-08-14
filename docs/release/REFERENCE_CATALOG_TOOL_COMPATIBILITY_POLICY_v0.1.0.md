# RNA-TR-Scout reference, catalog, and tool compatibility policy v0.1.0

Status: post-Freeze release-engineering policy.

## Principle

Exact SHA-256 or exact tool-version matches are **validation-profile fingerprints**, not general
permission gates.

RNA-TR-Scout reports whether the supplied resources match the profile used for validation.
Compatible custom resources may be used, while the output provenance records that exact golden
reproducibility has not been established for that custom profile.

Users are not expected to know whether their files are "the same" as the validated files.
RNA-TR-Scout performs the classification.

Coordinate compatibility is not treated as proof of assembly identity. A custom reference that
passes the current GRCh38 target-coordinate checks is reported as compatible with the current
catalog coordinate space, while remaining outside the exact validated-profile identity.

## Three states

### `VALIDATED_PROFILE`

The resource/tool fingerprint matches the profile used for RNA-TR-Scout validation.

For the current ONT-cDNA mapping profile this means the validated GRCh38 reference resources,
validated frozen catalog resources, and validated mapper version.

### `CUSTOM_COMPATIBLE`

The supplied resource or tool differs from the validated fingerprint, but compatibility checks
required by the current execution path pass.

Execution is allowed. The manifest records the supplied SHA-256 values, tool versions, and the
fact that the run is outside exact golden-validation scope.

### `INCOMPATIBLE`

Required coordinate systems, required contigs/intervals, or required schema/contract elements do
not support the current pipeline. Execution stops with the incompatibility reason.

## Genome reference policy

RNA-TR-Scout was validated with the GENCODE release 50 GRCh38 primary-assembly reference.

Other GRCh38-compatible references are allowed for the mapping adapter when the active RNA-TR-Scout
mapping-target intervals and splice-junction intervals fit within the supplied reference coordinate
space.

Exact FASTA, FAI, MMI, or junction BED12 SHA-256 equality is not required for execution.

The validated SHA-256 values remain useful because they allow automatic recognition of the
validated profile.

If a custom FASTA is supplied, RNA-TR-Scout builds a run-local MMI using the active minimap2.
It must not silently reuse the validated profile's MMI for a different FASTA.

The v0.2 compatibility path does not accept an arbitrary custom MMI. A prebuilt MMI cannot be
independently bound to the supplied FASTA from the index alone, so accepting an unverified custom
MMI could make the effective mapping reference differ silently from the FASTA recorded in
provenance. Future versions may add a cache keyed by a verified FASTA fingerprint.

For the same reason, custom FASTA compatibility is evaluated by scanning the FASTA itself rather
than trusting a user-supplied custom FAI. The exact validated FASTA may use its exact validated FAI.

The reference-compatibility BED is the frozen validated RNA-TR-Scout mapping-target catalog and
cannot be overridden in the v0.2 reference path. Newer/custom TRExplorer or STRchive catalogs
must enter through the separate post-Freeze catalog adapter and validator rather than replacing
the compatibility BED ad hoc.

## minimap2 / samtools policy

The validated ONT-cDNA mapping profile used minimap2 `2.31-r1302` and samtools `1.24`.

Other versions are allowed. A different version is classified as `CUSTOM_TOOL_VERSION`, not as
an automatic failure.

The standard RNA-TR-Scout environment remains pinned to the validated versions for users who want
the tested profile.

If a mapper version differs from the validated version and no explicit MMI is supplied, a run-local
MMI should be generated from the supplied FASTA with that active mapper version.

## TRExplorer / STRchive catalog policy

The same conceptual policy applies to repeat catalogs:

- exact frozen catalog fingerprints -> `VALIDATED_CATALOG_PROFILE`;
- future schema/coordinate-compatible catalogs -> `CUSTOM_COMPATIBLE_CATALOG`;
- incompatible schema or coordinate system -> `INCOMPATIBLE_CATALOG`.

However, custom catalog execution is **not enabled merely by relaxing SHA checks in the frozen
Core**.

TRExplorer/STRchive-derived resources affect locus identity, assignment, overlap/alias behavior,
disease annotation, and candidate multiplicity. Therefore custom catalog support requires a
separate post-Freeze catalog adapter plus schema and coordinate validators.

Until that adapter exists, the frozen Core continues to use its checksum-bound validated catalog
set. This preserves the Local Core Freeze while leaving the software architecture open to newer or
user-supplied catalogs.

## Provenance requirement

Every mapping/future custom-catalog run must record:

- actual resource paths;
- SHA-256 fingerprints;
- detected/declared assembly family;
- compatibility-check result;
- actual tool versions;
- validated-profile match status;
- whether exact golden-validation scope applies.

A custom profile is not described as erroneous merely because it differs from the validated
profile.
