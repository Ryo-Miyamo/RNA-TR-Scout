# Stage16T user-facing documentation review record v0.1.0

Date: 2026-08-16

## Status

**READY_FOR_OWNER_REVIEW**

Stage16T prepares the user-facing documentation for the current internal release-engineering candidate. This checkpoint is documentation-only and does not modify the frozen scientific Core.

## Base revision

Stage16T branch base:

`2191352170afe284c88cccd92c192efda2465b09`

Immutable Local Core Freeze root:

`4b1981db955a8aa92a2a01e19bbb1cfc2aa0ebfb`

## User-facing documents prepared

1. `README.md`
   - states what RNA-TR-Scout does;
   - identifies the validated ONT-cDNA / Linux x86-64 scope;
   - gives setup and public-CLI examples;
   - describes the five scientific outputs;
   - records Stage16S cross-hardware parity;
   - clearly states that the repository is not yet the public v0.5.0 release.

2. `docs/USER_GUIDE.md`
   - explains FASTQ and BAM+FASTQ input modes;
   - explains source-checkout environment setup and activation;
   - documents `resources-status`, `map`, and `run`;
   - describes output tables and provenance/QC files;
   - explains restart/resume;
   - includes essential RNA-evidence interpretation cautions;
   - defines current validated scope and current non-goals.

3. `docs/release/STAGE16S_CROSS_HARDWARE_PARITY_v0.1.1.md`
   - records the formally accepted second-machine parity result;
   - records frozen native-kernel execution PASS;
   - records Tier2 five-table exact parity and SECOND_RESUME_NOOP PASS;
   - records that the v0.1.0 `repeat_interruptions` mismatch was an expected-SHA transcription error in the validator and not a scientific-output mismatch.

## Source-of-truth checks performed

The documentation was checked directly against the current repository implementation and frozen contracts, including:

- public CLI definitions in `src/rnatr_scout/public_workflow.py`;
- source-checkout setup behavior in `scripts/rnatr_setup_source_checkout_v0.1.1.py`;
- pinned environment in `environment.yml`;
- standard resource installation behavior in `scripts/rnatr_install_standard_resources_v0.1.1.py`;
- frozen scientific input contract in `config/core_runtime/v0.1.0/resource_manifest.json`;
- evidence schema v0.4.2 table names and grains;
- merged-package publication behavior and exact/deterministic output contracts in `scripts/rnatr_core_generic_sharded_v0.1.2.py`.

A documentation issue found during this audit was corrected: the setup helper creates the isolated environment but cannot activate the caller's parent shell, so README/user-guide instructions now explicitly tell the user to activate the created environment before invoking `rnatr-scout`.

## Current intentional release limitations stated in documentation

- compact validated catalog bundle public URL is not finalized;
- accepted distribution path remains Git source checkout rather than a public wheel;
- ONT direct RNA and PacBio Iso-Seq/Kinnex are not yet validated profiles;
- non-x86-64 systems are outside the current validated scope;
- custom references/catalogs are not represented as exact-golden equivalents;
- final public v0.5.0 release decision remains pending.

## Owner visual-review points

Before Stage16T is marked formally complete, confirm that:

1. the README opening explains the software clearly enough for a laboratory user who did not participate in development;
2. the Quick Start is understandable and not overly developer-oriented;
3. the five-table output descriptions are biologically/intuitively understandable enough for intended users;
4. the cautions about RNA evidence versus DNA genotype are appropriately prominent;
5. the description of Stage16S and its v0.1.0 validator correction is accurate and not overclaimed; and
6. the current private/internal status versus future public v0.5.0 status is stated at the right level of prominence.

No Stage16T formal PASS is asserted until this owner-facing review is accepted.
