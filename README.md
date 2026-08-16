# RNA-TR-Scout

> **Internal release-engineering candidate — not the public v0.5.0 release.**

RNA-TR-Scout detects and describes **tandem-repeat evidence observed in long-read RNA sequencing data**. The currently validated user profile is Oxford Nanopore cDNA on Linux x86-64, using the frozen RNA-TR-Scout scientific Core.

## What is validated now

The current release-engineering state has passed:

- fresh Git source-checkout setup in an isolated mamba/conda environment;
- validated GRCh38 / GENCODE v50 reference-resource installation;
- installation and verification of the validated TRExplorer/STRchive-derived RNA-TR-Scout catalog bundle;
- ONT-cDNA FASTQ → minimap2 splice-aware BAM → frozen Core → final output;
- mapped BAM + read-coherent source FASTQ → frozen Core → final output;
- exact golden parity of all five scientific output tables for the validated Tier2 fixture;
- restart/resume and `SECOND_RESUME_NOOP` behavior with unchanged scientific output; and
- Stage16S cross-hardware execution on a second Linux x86-64 PC (`deeplearningboxii`), including frozen native-kernel execution and exact 5/5 scientific-table parity.

Stage16S v0.1.0 initially reported a `repeat_interruptions` SHA mismatch because the validator contained an incorrectly transcribed expected SHA. The scientific output itself matched. Stage16S v0.1.1 re-evaluated against the canonical golden manifest and formally passed.

These results establish parity for the tested Linux x86-64 systems and fixtures; they are not a universal guarantee across arbitrary hardware, operating systems, sequencing platforms, references, or catalogs.

## Quick start

The accepted installation path at this stage is a **Git source checkout**, not a wheel.

From the repository root, create and verify the validated environment and resources:

```bash
python scripts/rnatr_setup_source_checkout_v0.1.1.py \
  --catalog-bundle /path/to/rnatr_catalog_bundle.tar.gz
```

The compact catalog bundle does not yet have a finalized public download URL, so the current release-engineering candidate requires it to be supplied explicitly.

By default the setup helper creates the isolated environment at:

```text
~/.local/share/rnatr-scout/envs/source-checkout-v0.1
```

Activate that environment before using the public CLI, for example:

```bash
mamba activate ~/.local/share/rnatr-scout/envs/source-checkout-v0.1
```

or use `conda activate` if conda is your environment manager.

Check resource readiness:

```bash
rnatr-scout resources-status
```

### Run from ONT-cDNA FASTQ

```bash
rnatr-scout run \
  --fastq sample.fastq.gz \
  --sample-id SAMPLE01 \
  --output-dir rnatr_SAMPLE01
```

RNA-TR-Scout runs the validated minimap2 splice-aware mapping adapter and then the frozen Core.

### Run from an existing BAM

```bash
rnatr-scout run \
  --fastq sample.fastq.gz \
  --bam sample.sorted.bam \
  --sample-id SAMPLE01 \
  --output-dir rnatr_SAMPLE01
```

The source FASTQ remains required in BAM mode. The frozen scientific input contract is **mapped BAM + read-coherent source FASTQ**.

For mapping only:

```bash
rnatr-scout map \
  --fastq sample.fastq.gz \
  --output-bam sample.sorted.bam \
  --sample-id SAMPLE01
```

## Scientific outputs

A normal run publishes its result package under:

```text
<output-dir>/final/
```

The five primary scientific tables are:

| Table | Grain |
|---|---|
| `read_evidence.tsv` / `.tsv.gz` | one row per read × target-region × locus hypothesis |
| `general_repeat_calls.tsv` / `.tsv.gz` | one row per projection/general-caller attempt, including not-attempted records |
| `repeat_events.tsv` / `.tsv.gz` | one row per retained non-overlapping raw-read repeat event |
| `repeat_segments.tsv` / `.tsv.gz` | one row per repeat segment or motif component within read evidence |
| `repeat_interruptions.tsv` / `.tsv.gz` | one row per interruption interval within a general repeat call |

The final package also contains the Core result manifest, package manifest, validation summary, input-coherence record, shard provenance, performance instrumentation, and local resource bindings.

**RNA-TR-Scout reports RNA evidence, not a definitive DNA genotype.** RNA non-observation must not be interpreted as absence of a DNA repeat expansion, and censored repeat measurements are lower bounds rather than exact sizes.

## Documentation

- [User guide](docs/USER_GUIDE.md) — installation, input modes, CLI examples, outputs, restart/resume, interpretation, and validated scope
- [Stage16S cross-hardware parity record](docs/release/STAGE16S_CROSS_HARDWARE_PARITY_v0.1.1.md)
- [Catalog resources](docs/catalog_resources/BUILDING_AND_UPDATING_CATALOGS.md) — validated catalog provenance and advanced custom-catalog rebuilding
- [Clean-install contract](docs/release/CLEAN_INSTALL_CONTRACT_v0.1.0.md)
- [ONT-cDNA mapping contract](docs/release/MAPPING_CONTRACT_ONT_CDNA_v0.1.0.md)
- [Reference/catalog/tool compatibility policy](docs/release/REFERENCE_CATALOG_TOOL_COMPATIBILITY_POLICY_v0.1.0.md)

## Current validated profile

- Platform: Linux x86-64
- Library mode: ONT cDNA
- Reference profile: GRCh38 / GENCODE v50
- Mapping: minimap2 2.31-r1302 validated profile
- Scientific schema: RNA-TR-Scout evidence schema v0.4.2
- Catalog: compact RNA-TR-Scout bundle derived from TRExplorer v2.0 plus pinned STRchive source provenance
- Distribution path: Git source checkout

Compatible custom GRCh38 references may be used through the post-Freeze compatibility-aware mapping adapter, but they are outside exact golden-validation scope. Custom catalogs are likewise treated as custom-compatible resources rather than exact golden-validated replacements.

## Not yet in validated public-release scope

The following remain outside the current validated public-release scope:

- ONT direct RNA;
- PacBio Iso-Seq / Kinnex;
- non-x86-64 systems;
- public wheel installation;
- automatic public download of the compact catalog bundle;
- arbitrary custom catalogs as exact-golden equivalents; and
- the final public `v0.5.0` release decision.

## Frozen scientific baseline

The accepted Local Core Freeze remains immutable:

- Freeze ID: `LOCAL_CORE_FREEZE_V0.1.0`
- immutable root commit: `4b1981db955a8aa92a2a01e19bbb1cfc2aa0ebfb`
- internal tag: `local-core-freeze-v0.1.0-internal`
- final Core Freeze manifest SHA-256: `c9a54b4c01dd67d2b7df9d96ba4c86bbe26c02e2ef6f4180c8f152927129125b`

Post-Freeze commits may improve repository organization, packaging, installation, documentation, compatibility adapters, and release engineering without rewriting that frozen scientific point.

Large sequencing inputs, reference/catalog payloads, SQLite databases, and historical evidence archives are intentionally not stored in Git. Their identities are checksum-bound through release resource manifests or frozen provenance.

## Repository status

This repository is currently **private and intended for laboratory-internal sharing and release preparation**. Do not describe the present repository state as the public RNA-TR-Scout v0.5.0 release.