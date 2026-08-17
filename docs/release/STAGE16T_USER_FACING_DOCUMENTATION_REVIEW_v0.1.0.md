# Stage16T user-facing documentation review record v0.1.0

Date: 2026-08-17

## Status

**PASS — OWNER REVIEW ACCEPTED**

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

## User-facing documents accepted

1. `README.md`
   - explains RNA-TR-Scout in ordinary research language;
   - summarizes the analysis flow from mapping to repeat evidence;
   - gives setup and public-CLI examples;
   - states that existing BAM input should be genome-aligned long-read RNA-seq produced with splice-aware mapping to a compatible reference;
   - introduces the five main scientific tables in plain language;
   - describes current repeat-calling limitations for highly complex or sequence-variable repeat architectures;
   - highlights the main RNA observability cautions without unnecessary genotype language;
   - describes tested scope without exposing stage/fixture/golden-validation vocabulary;
   - directs advanced validation readers to internal documentation.

2. `docs/USER_GUIDE.md`
   - explains FASTQ and BAM+FASTQ input modes and mapping assumptions;
   - explains installation and environment activation;
   - documents `resources-status`, `map`, and `run`;
   - gives a conceptual analysis flow;
   - explains each of the five scientific tables and how to use them together;
   - explains the current boundary for complex sequence-variable repeat architecture;
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
- merged-package publication behavior and exact/deterministic output contracts in `scripts/rnatr_core_generic_sharded_v0.1.2.py`;
- the accepted ONT-cDNA splice-aware mapping contract.

A setup issue identified during the documentation audit remains correctly documented: the setup helper creates the isolated environment but cannot activate the caller's parent shell, so user instructions explicitly activate the created environment before invoking `rnatr-scout`.

## Disk-usage wording correction

Owner review identified that an earlier draft's statement that roughly 300 GB of free working space was a practical target for a five-million-read run could be misread as a measured requirement. That number was a conservative safety margin, not an observed peak.

The user-facing documentation now states only the measured fact available from the full-scale restart audit: approximately **140 GB of checkpoint/work files** were present at one audited stage of a 5.31-million-read run. It explicitly states that this is **not a measured peak-disk requirement** and that peak disk usage has not yet been formally benchmarked.

A formal full-scale peak-disk benchmark should be completed before public release so that storage guidance can be based on measured peak usage. This is a release-engineering/operational benchmark and does not require modification of scientific Core semantics.

## Current intentional release limitations stated in user-facing documentation

User-facing wording states these limitations without internal release vocabulary:

- compact repeat-catalog public download location is not finalized;
- current installation uses a Git source checkout rather than a simplified public package;
- ONT direct RNA and PacBio Iso-Seq/Kinnex are still under development;
- non-x86-64 systems are not yet part of the standard tested workflow;
- more complete automated interpretation of highly complex sequence-variable repeat architectures remains future work;
- custom references/catalogs have received less testing than the standard setup;
- peak disk usage for full-scale runs has not yet been formally benchmarked;
- the repository remains a private pre-release rather than the public v0.5.0 release.

## Owner review acceptance

The owner reviewed the researcher-facing documentation iteratively and requested corrections to:

- internal development terminology exposed in README;
- unnecessary DNA-genotype wording;
- reference/resource sizing information;
- BAM mapping assumptions;
- complex sequence-variable repeat limitations; and
- speculative disk-space guidance.

Those points were incorporated. The owner then explicitly approved proceeding with the current draft state, with final resource sizing to be refined later before public release.

## Decision

**Stage16T PASS.**

The researcher-facing README and user guide are accepted for the current private pre-release repository state. This acceptance does not assert public v0.5.0 readiness and does not close the remaining release-engineering items listed above.
