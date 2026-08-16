# RNA-TR-Scout user guide

RNA-TR-Scout detects and characterizes tandem-repeat sequences observed in long-read RNA sequencing data.

This guide is written for researchers who want to run the software and interpret its outputs. Internal development-stage names, validation fixture names, commit hashes, and release-audit terminology are intentionally kept out of the main workflow.

## 1. What you can start from

RNA-TR-Scout currently supports two main input modes.

### FASTQ input

Provide an ONT-cDNA FASTQ file:

```bash
rnatr-scout run \
  --fastq sample.fastq.gz \
  --sample-id SAMPLE01 \
  --output-dir rnatr_SAMPLE01
```

RNA-TR-Scout will first map the reads to the tested GRCh38 reference setup and then perform tandem-repeat analysis.

### BAM + FASTQ input

If you already have a mapped BAM, provide both the BAM and the original FASTQ:

```bash
rnatr-scout run \
  --fastq sample.fastq.gz \
  --bam sample.sorted.bam \
  --sample-id SAMPLE01 \
  --output-dir rnatr_SAMPLE01
```

The original FASTQ is required because repeat measurement uses the source read sequence. The BAM and FASTQ should represent the same reads with matching read identifiers.

If `--run-id` is omitted, `--sample-id` is used as the run identifier.

## 2. Installation

The current pre-release installation method uses a Git source checkout and an isolated mamba/conda environment.

Requirements for the currently tested setup:

- Linux x86-64
- Git
- mamba or conda
- network access for reference installation unless the required files are already available locally
- the RNA-TR-Scout repeat-catalog bundle

From the repository root:

```bash
python scripts/rnatr_setup_source_checkout_v0.1.1.py \
  --catalog-bundle /path/to/rnatr_catalog_bundle.tar.gz
```

By default, the environment is created at:

```text
~/.local/share/rnatr-scout/envs/source-checkout-v0.1
```

Activate it before running the command-line interface:

```bash
mamba activate ~/.local/share/rnatr-scout/envs/source-checkout-v0.1
```

or:

```bash
conda activate ~/.local/share/rnatr-scout/envs/source-checkout-v0.1
```

The setup checks the required software and installs or verifies the standard reference resources.

At the present pre-release stage, the compact repeat catalog does not yet have a finalized public download location, so the catalog bundle must be supplied explicitly during setup.

To verify an existing installation:

```bash
python scripts/rnatr_setup_source_checkout_v0.1.1.py --verify-only
```

After activating the environment, you can also check resource readiness with:

```bash
rnatr-scout resources-status
```

## 3. Mapping only

To generate a mapped BAM without running repeat analysis:

```bash
rnatr-scout map \
  --fastq sample.fastq.gz \
  --output-bam sample.sorted.bam \
  --sample-id SAMPLE01
```

The standard tested mapping setup uses GRCh38 / GENCODE v50 and minimap2 for ONT-cDNA reads.

Other compatible GRCh38 references may be usable, but the standard reference setup has received the most testing so far.

## 4. What happens during analysis

Conceptually, RNA-TR-Scout performs the following steps:

1. maps each long RNA read to the genome, if a BAM was not supplied;
2. identifies reads that overlap repeat loci in the catalog;
3. projects each candidate repeat locus from genome coordinates onto the original read sequence;
4. examines the projected read sequence for repeat motifs and repeat structure;
5. records repeat events, motif components, interruptions, and cases that could not be fully measured; and
6. writes the evidence in linked tabular files for downstream analysis.

This distinction between **locus projection** and **repeat measurement** is important. A read may overlap and successfully project to a repeat locus even when the current caller cannot produce a final repeat length or motif measurement.

## 5. Output files

A normal run writes its final result package under:

```text
<output-dir>/final/
```

The five main scientific tables are described below.

### `read_evidence.tsv`

This is usually the best table to start with.

Each row represents evidence connecting a read to a candidate repeat locus. It contains the identifiers needed to connect that read-locus observation to repeat calls, events, segments, and interruptions in the other tables.

### `general_repeat_calls.tsv`

This table records repeat-calling attempts for projected candidates.

Importantly, it also records cases in which the locus could be projected onto the read but no final repeat measurement was produced. A missing motif, repeat length, purity, or related value therefore does **not** automatically mean that no repeat exists at that locus.

### `repeat_events.tsv`

This table contains repeat events retained on the original RNA reads after repeat scanning.

A read may contain more than one retained event, depending on the sequence and locus context.

### `repeat_segments.tsv`

This table describes the motif components or repeat segments that make up retained repeat evidence.

It is useful when examining repeat architecture rather than only an overall repeat length.

### `repeat_interruptions.tsv`

This table records interruptions within repeat tracts when they are detected.

It can be used to distinguish a relatively pure repeat from one containing intervening or altered sequence.

Compressed `.tsv.gz` copies of the main tables are also produced.

The output directory contains additional files for reproducibility and quality control, including information about the resources used, input-read consistency, validation, run provenance, and performance.

## 6. How the tables relate to one another

The output is intentionally read-centered rather than being reduced immediately to one row per genomic locus.

For most exploratory analyses:

1. start with `read_evidence.tsv`;
2. identify the reads and loci of interest;
3. join to `general_repeat_calls.tsv` to see whether repeat measurement was attempted and whether a final call was available;
4. use `repeat_events.tsv` and `repeat_segments.tsv` to examine repeat structure; and
5. use `repeat_interruptions.tsv` when interruption structure is relevant.

Stable identifiers are included so that these tables can be joined without relying on row order.

## 7. Important interpretation points

RNA-TR-Scout reports **RNA evidence**. It does not by itself determine the underlying DNA genotype.

### RNA non-observation is not the same as DNA absence

A repeat may fail to appear in RNA data because:

- the locus is not expressed in the sampled tissue;
- the relevant transcript is rare;
- sequencing coverage is insufficient;
- the read does not extend across the repeat;
- RNA processing changes which part of the locus is present in the mature transcript; or
- the repeat-containing molecule is difficult to sequence or map.

Therefore, “not observed” should not be interpreted as “not present in the genome.”

### Some repeat lengths are lower bounds

If a read does not span enough sequence to establish the complete repeat tract, the observed repeat length may represent only a lower bound.

Exact and censored observations should be treated differently in downstream analysis.

### Projection success is not the same as successful repeat measurement

A candidate locus can be mapped successfully onto a read while the repeat caller still cannot provide a final measurement.

This can happen because the sequence does not meet the requirements of the currently implemented calling strategy, because the read context is incomplete, or because the local repeat structure is more complicated than the current caller supports.

### Multiple candidate rows do not necessarily mean multiple biological repeats

The same RNA read can generate multiple technical candidate assignments because of overlapping target regions, alternative alignments, nearby loci, or related mapping/projection possibilities.

These rows should not automatically be counted as separate biological repeat loci.

## 8. Resume after interruption

Runs can be resumed after interruption.

Re-run the same command with `--resume`, using the same output directory and the same input data and identifiers:

```bash
rnatr-scout run \
  --fastq sample.fastq.gz \
  --bam sample.sorted.bam \
  --sample-id SAMPLE01 \
  --output-dir rnatr_SAMPLE01 \
  --resume
```

RNA-TR-Scout checks completed work before reusing it. Re-running `--resume` on an already completed tested run is expected to leave the scientific outputs unchanged.

## 9. Current tested scope

The current standard setup has been tested end-to-end for:

- Oxford Nanopore cDNA long-read RNA sequencing
- Linux x86-64
- GRCh38 / GENCODE v50
- minimap2-based mapping
- the RNA-TR-Scout compact repeat catalog derived from TRExplorer and STRchive resources
- FASTQ-to-final analysis
- mapped-BAM plus source-FASTQ analysis
- interrupted-run resume

The workflow has also been reproduced on more than one Linux x86-64 computer with reproducible scientific outputs for the test data used during development.

This does not imply that every operating system, processor architecture, sequencing platform, reference build, or custom catalog has been tested.

## 10. Areas still under development

The following are not yet part of the standard tested user workflow:

- ONT direct RNA
- PacBio Iso-Seq
- PacBio Kinnex
- non-x86-64 systems
- simplified public package installation
- automatic public download of the compact repeat catalog

Custom references and custom repeat catalogs are possible areas for advanced use, but they have received less testing than the standard setup.

## 11. Catalogs and references

Ordinary users do not need to download or manage the complete upstream TRExplorer and STRchive source repositories.

The standard workflow uses a compact RNA-TR-Scout catalog prepared from those resources.

Users who intentionally want to rebuild or modify the catalog should see:

[`catalog_resources/BUILDING_AND_UPDATING_CATALOGS.md`](catalog_resources/BUILDING_AND_UPDATING_CATALOGS.md)

## 12. Command-line help

```bash
rnatr-scout --help
rnatr-scout run --help
rnatr-scout map --help
rnatr-scout resources-status --help
```

For ordinary use, these commands should be preferred over the internal development scripts stored elsewhere in the repository.

## 13. Development and validation records

Detailed reproducibility, software-validation, and release-engineering records are retained in `docs/release/` and related internal documentation directories.

They are useful for developers, auditors, and future release work, but they are not required reading for researchers who simply want to install and use RNA-TR-Scout.
