# Stage16T user-facing documentation review record v0.1.0

Date: 2026-08-16

## Status

**READY_FOR_OWNER_REVIEW — REVISED USER-FACING DRAFT**

Stage16T prepares the user-facing documentation for the current internal release-engineering candidate. This checkpoint is documentation-only and does not modify the frozen scientific Core.

## Base revision

Stage16T branch base:

`2191352170afe284c88cccd92c192efda2465b09`

Immutable Local Core Freeze root:

`4b1981db955a8aa92a2a01e19bbb1cfc2aa0ebfb`

## Documentation audience decision

Owner review identified that the first draft still exposed too much internal development and validation terminology to ordinary readers. Terms such as `frozen Core`, `Tier2 fixture`, `Stage16S`, `exact golden parity`, `post-Freeze`, and detailed Freeze identifiers are useful for developers and auditors but should not dominate researcher-facing documentation.

The README and user guide were therefore revised with an explicit audience split:

- `README.md`: first-time research users and collaborators;
- `docs/USER_GUIDE.md`: researchers who want to install, run, and interpret RNA-TR-Scout;
- `docs/release/` and related internal records: developers, auditors, reproducibility review, and release engineering.

Internal validation terminology is retained in the audit trail rather than removed from the repository.

## User-facing documents prepared

1. `README.md`
   - explains RNA-TR-Scout in ordinary research language;
   - summarizes the analysis flow from mapping to repeat evidence;
   - gives setup and public-CLI examples;
   - introduces the five main scientific tables in plain language;
   - highlights the main RNA-versus-DNA interpretation cautions;
   - describes tested scope without exposing stage/fixture/golden-validation vocabulary;
   - directs advanced validation readers to internal documentation.

2. `docs/USER_GUIDE.md`
   - explains FASTQ and BAM+FASTQ input modes;
   - explains installation and environment activation;
   - documents `resources-status`, `map`, and `run`;
   - gives a conceptual analysis flow;
   - explains each of the five scientific tables and how to use them together;
   - explains restart/resume;
   - explains RNA non-observation, censored length, projection-versus-measurement, and technical candidate multiplicity in researcher-facing language;
   - describes current tested scope and areas still under development.

3. `docs/release/STAGE16S_CROSS_HARDWARE_PARITY_v0.1.1.md`
   - remains an internal validation record;
   - retains the formally accepted second-machine parity result;
   - retains native-kernel execution, Tier2 five-table exact parity, and SECOND_RESUME_NOOP details;
   - retains the v0.1.0 validator expected-SHA transcription-error record.

## Source-of-truth checks performed

The documentation was checked directly against the current repository implementation and frozen contracts, including:

- public CLI definitions in `src/rnatr_scout/public_workflow.py`;
- source-checkout setup behavior in `scripts/rnatr_setup_source_checkout_v0.1.1.py`;
- pinned environment in `environment.yml`;
- standard resource installation behavior in `scripts/rnatr_install_standard_resources_v0.1.1.py`;
- frozen scientific input contract in `config/core_runtime/v0.1.0/resource_manifest.json`;
- evidence schema v0.4.2 table names and grains;
- merged-package publication behavior and exact/deterministic output contracts in `scripts/rnatr_core_generic_sharded_v0.1.2.py`.

A setup issue identified during the documentation audit remains correctly documented: the setup helper creates the isolated environment but cannot activate the caller's parent shell, so user instructions explicitly activate the created environment before invoking `rnatr-scout`.

## Current intentional release limitations stated in user-facing documentation

User-facing wording now states these limitations without internal release vocabulary:

- compact repeat-catalog public download location is not finalized;
- current installation uses a Git source checkout rather than a simplified public package;
- ONT direct RNA and PacBio Iso-Seq/Kinnex are still under development;
- non-x86-64 systems are not yet part of the standard tested workflow;
- custom references/catalogs have received less testing than the standard setup;
- the repository remains a private pre-release rather than the public v0.5.0 release.

## Owner visual-review points

Before Stage16T is marked formally complete, confirm that:

1. the README now reads like software documentation for a research user rather than an internal validation report;
2. the opening explanation of what RNA-TR-Scout does is understandable;
3. the Quick Start is sufficiently straightforward;
4. the five-table descriptions are biologically/intuitively understandable enough for intended users;
5. the RNA-evidence interpretation cautions are clear without becoming overly technical;
6. the current tested scope is neither understated nor overclaimed; and
7. internal stage/Freeze/golden-validation language is appropriately confined to development/validation records.

No Stage16T formal PASS is asserted until this owner-facing visual review is accepted.
