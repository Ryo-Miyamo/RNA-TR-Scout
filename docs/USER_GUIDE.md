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

RNA-TR-Scout will first map the reads to the tested GRCh38 reference setup using a splice-aware long-read RNA mapping workflow and then perform tandem-repeat analysis.

### BAM + FASTQ input

If you already have a mapped BAM, provide both the BAM and the original FASTQ:

```bash
rnatr-scout run \
  --fastq sample.fastq.gz \
  --bam sample.sorted.bam \
  --sample-id SAMPLE01 \
  --output-dir rnatr_SAMPLE01
```

The BAM should be a **genome-aligned long-read RNA-seq BAM produced with splice-aware mapping to a compatible reference**. An arbitrary DNA-style or non-splice-aware BAM should not be assumed to be suitable.

The original FASTQ is required because repeat measurement uses the source read sequence. The BAM and FASTQ must represent the same reads with matching read identifiers.

The current public workflow checks BAM/FASTQ read identity and basic BAM validity, but it does not fully reconstruct or prove how an externally supplied BAM was mapped. If the mapping history is uncertain, starting from FASTQ and allowing RNA-TR-Scout to perform mapping is the preferred option.

If `--run-id` is omitted, `--sample-id` is used as the run identifier.

## 2. Installation

The current pre-release installation method uses a Git source checkout and an isolated mamba/conda environment.

Requirements for the currently tested setup:

- Linux x86-64
- Git
- mamba or conda
- network access for reference and compact-catalog installation unless the exact required files are already available locally

From the repository root:

```bash
python scripts/rnatr_setup_source_checkout_v0.1.1.py
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

The setup checks the required software and installs or verifies the standard reference resources. The compact RNA-TR-Scout catalog is downloaded from its public release asset and verified by SHA-256 when it is not already available locally.

To verify an existing installation:

```bash
python scripts/rnatr_setup_source_checkout_v0.1.1.py --verify-only
```

After activating the environment, you can check resource readiness with:

```bash
rnatr-scout resources-status
```

You can also inspect the host resources that RNA-TR-Scout sees:

```bash
rnatr-scout system-info
```

## 3. Disk space, CPU, and memory planning

The standard reference installer obtains two GENCODE source files for the tested setup:

- GRCh38 primary-assembly FASTA (`.fa.gz`)
- GENCODE v50 primary-assembly annotation (`.gtf.gz`)

Together these compressed downloads are approximately **0.9 GB**. The installer then decompresses the genome and builds a minimap2 index and junction resource, so the installed reference occupies substantially more space than the original download. Allow **tens of GB of free space** for installation rather than planning from the compressed download size alone.

Run-time storage depends strongly on the number and length of reads because RNA-TR-Scout keeps restartable intermediate files and detailed read-level evidence. For large datasets, temporary and intermediate data can be much larger than the final TSV files.

In a **5.31-million-read development run**, approximately **140 GB of checkpoint/work files** were present at one audited restart stage. This is an observed working-data volume, **not a measured peak-disk requirement**. Peak disk usage has not yet been formally benchmarked, so a fixed minimum free-space requirement for a five-million-read run is not stated yet.

The current release-engineering workflow has been tested on Linux x86-64 hosts with **24 and 36 logical CPUs and approximately 128 GB RAM**. For approximately five-million-read ONT-cDNA datasets, the current practical recommended profile is:

- about 24 or more logical CPU threads;
- approximately 128 GB RAM; and
- fast local SSD/NVMe working storage.

This is a tested/recommended profile rather than an empirical minimum. A lower CPU/RAM minimum for the five-million-read workflow has not yet been established.

For human-genome ONT-cDNA mapping and smaller runs, **32 GB RAM is a comfortable practical target** based on development observations; 16 GB may be tight, especially if other processes are active. This should not be interpreted as evidence that 32 GB is sufficient for the current five-million-read release-scale workflow.

RNA-TR-Scout detects logical CPU count, currently available RAM, selected temporary directory, and free space before Core execution. If `--shards`, `--max-unit-workers`, and `--caller-workers` are omitted, a conservative Core scheduling profile is selected automatically from the input scale and detected resources and written to the run provenance.

Advanced users can provide `--threads`, `--memory-gb`, `--tmp-dir`, or explicit worker-count overrides. Supplied overrides are recorded. In the current release, `--threads` is a Core scheduling budget; the validated ONT-cDNA mapper retains its separately versioned mapping-thread profile.

These values are practical observations rather than hard scientific thresholds. Actual requirements vary with read count, read length, worker settings, filesystem behavior, and retained intermediate state. A formal peak-disk benchmark remains planned so that fixed large-run storage guidance can be based on measured peak usage rather than a speculative safety margin.

## 4. Mapping only

To generate a mapped BAM without running repeat analysis:

```bash
rnatr-scout map \
  --fastq sample.fastq.gz \
  --output-bam sample.sorted.bam \
  --sample-id SAMPLE01
```

The standard tested mapping setup uses GRCh38 / GENCODE v50 and minimap2 with splice-aware mapping for ONT-cDNA reads.

The tested mapping configuration retains secondary alignments and uses transcript-derived splice-junction information. This matters because repeat-containing RNA reads may map ambiguously and because exon-spanning RNA alignments need to be represented correctly.

Other compatible GRCh38 references may be usable, but the standard reference setup has received the most testing so far.

## 5. What happens during analysis

Conceptually, RNA-TR-Scout performs the following steps:

1. maps each long RNA read to the genome, if a BAM was not supplied;
2. identifies reads that overlap repeat loci in the catalog;
3. projects each candidate repeat locus from genome coordinates onto the original read sequence;
4. examines the projected read sequence for repeat motifs and repeat structure;
5. records repeat events, motif components, interruptions, and cases that could not be fully measured; and
6. writes the evidence in linked tabular files for downstream analysis.

This distinction between **locus projection** and **repeat measurement** is important. A read may overlap and successfully project to a repeat locus even when the current caller cannot produce a final repeat length or motif measurement.

## 6. What kinds of repeat structure are currently supported?

The current automatic caller is strongest for **periodic tandem-repeat structures** for which a repeat unit or a small set of repeat motifs can be meaningfully scanned along the read. Supported calls can include multiple motif components and interruption intervals.

RNA-TR-Scout is **not yet a general sequence-assembly or graph-based solver for every complex repeat locus**. In particular, highly sequence-variable regions, complicated variation-cluster-like architectures, or loci requiring specialized locus-specific interpretation may not receive a complete automatic repeat measurement with the current caller.

Such loci can still produce useful read/locus evidence if the genomic candidate can be assigned and projected. When the current calling strategy is not applicable, the result is retained as an unmeasured or unsupported calling attempt rather than being converted into a false negative.

This distinction is important when examining loci whose biological variation is not well described by a simple copy-number change of one periodic motif.

## 7. Output files

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

## 8. How the tables relate to one another

The output is intentionally read-centered rather than being reduced immediately to one row per genomic locus.

For most exploratory analyses:

1. start with `read_evidence.tsv`;
2. identify the reads and loci of interest;
3. join to `general_repeat_calls.tsv` to see whether repeat measurement was attempted and whether a final call was available;
4. use `repeat_events.tsv` and `repeat_segments.tsv` to examine repeat structure; and
5. use `repeat_interruptions.tsv` when interruption structure is relevant.

Stable identifiers are included so that these tables can be joined without relying on row order.

## 9. Important interpretation points

### RNA non-observation does not establish genomic absence

A repeat may fail to appear in RNA data because:

- the locus is not expressed in the sampled tissue;
- the relevant transcript is rare;
- sequencing coverage is insufficient;
- the read does not extend across the repeat;
- RNA processing changes which part of the locus is present in the mature transcript; or
- the repeat-containing molecule is difficult to sequence or map.

Therefore, RNA non-observation should be treated as an observability issue rather than automatically as evidence of genomic absence.

### Some repeat lengths are lower bounds

If a read does not span enough sequence to establish the complete repeat tract, the observed repeat length may represent only a lower bound.

Exact and censored observations should be treated differently in downstream analysis.

### Projection success is not the same as successful repeat measurement

A candidate locus can be mapped successfully onto a read while the repeat caller still cannot provide a final measurement.

This can happen because the sequence does not meet the requirements of the currently implemented calling strategy, because the read context is incomplete, or because the local repeat structure is more complicated than the current caller supports.

### Multiple candidate rows do not necessarily mean multiple biological repeats

The same RNA read can generate multiple technical candidate assignments because of overlapping target regions, alternative alignments, nearby loci, or related mapping/projection possibilities.

These rows should not automatically be counted as separate biological repeat loci.

## 10. Resume after interruption

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

RNA-TR-Scout checks completed work before reusing it. Re-running `--resume` on an already completed tested run is expected to leave the scientific outputs unchanged. The recorded Core resource plan is reused on resume so that a completed run is not silently repartitioned under different worker settings.

## 11. Current tested scope

The current standard setup has been tested end-to-end for:

- Oxford Nanopore cDNA long-read RNA sequencing
- Linux x86-64
- GRCh38 / GENCODE v50
- splice-aware minimap2 mapping
- the RNA-TR-Scout compact repeat catalog derived from TRExplorer and STRchive resources
- FASTQ-to-final analysis
- mapped-BAM plus source-FASTQ analysis
- automatic Core CPU/RAM-aware scheduling
- interrupted-run resume

The workflow has been reproduced on more than one Linux x86-64 computer with reproducible scientific outputs for the test data used during development. An independent second computer has also completed a fresh source checkout, fresh isolated environment creation, network reference/catalog installation, automatic Core resource selection, exact scientific-output validation, and second-resume no-op.

This does not imply that every operating system, processor architecture, sequencing platform, reference build, mapping workflow, or custom catalog has been tested.

## 12. Areas still under development

The following are not yet part of the standard tested user workflow:

- more complete analysis of complex sequence-variable repeat architectures
- ONT direct RNA
- PacBio Iso-Seq
- PacBio Kinnex
- non-x86-64 systems
- simplified public package installation

Custom references and custom repeat catalogs are possible areas for advanced use, but they have received less testing than the standard setup.

## 13. Catalogs and references

Ordinary users do not need to download or manage the complete upstream TRExplorer and STRchive source repositories.

The standard workflow uses a compact RNA-TR-Scout catalog prepared from those resources. The standard installer can retrieve the validated compact catalog automatically and verifies its archive identity before installation.

Users who intentionally want to rebuild or modify the catalog should see:

[`catalog_resources/BUILDING_AND_UPDATING_CATALOGS.md`](catalog_resources/BUILDING_AND_UPDATING_CATALOGS.md)

## 14. Command-line help

```bash
rnatr-scout --help
rnatr-scout run --help
rnatr-scout map --help
rnatr-scout resources-status --help
rnatr-scout system-info --help
```

For ordinary use, these commands should be preferred over the internal development scripts stored elsewhere in the repository.

Stage-numbered scripts are **not part of the ordinary supported user workflow**. They are retained primarily for development history, validation, reproducibility, and release traceability. Developers starting new biology, platform, or performance work should begin with [`../DEVELOPMENT.md`](../DEVELOPMENT.md) and the current contracts linked from it rather than selecting a Stage script by filename.

## 15. Development and validation records

Detailed reproducibility, software-validation, and release-engineering records are retained in `docs/release/` and related internal documentation directories.

They are useful for developers, auditors, and future release work, but they are not required reading for researchers who simply want to install and use RNA-TR-Scout.
