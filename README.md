# RNA-TR-Scout

RNA-TR-Scout is a tool for detecting and characterizing **tandem-repeat sequences observed in long-read RNA sequencing data**.

It is designed to help researchers find which repeat loci are represented in individual long RNA reads, estimate repeat length and motif structure when possible, and retain the read-level evidence needed for downstream biological analysis.

The currently tested setup is:

- Oxford Nanopore cDNA long-read RNA sequencing
- GRCh38 / GENCODE v50
- Linux x86-64

> **Development status:** this repository is currently a private pre-release version and is not yet the public RNA-TR-Scout v0.5.0 release.

## What RNA-TR-Scout does

At a high level, RNA-TR-Scout:

1. maps ONT-cDNA reads to the genome, or accepts an existing mapped BAM;
2. identifies reads that overlap known or candidate tandem-repeat regions;
3. projects the repeat locus onto the original read sequence;
4. searches the read for repeat motifs and repeat structure; and
5. produces read-level tables that can be used for downstream analysis.

The software keeps the original RNA-read evidence rather than reducing each locus immediately to a single genotype-like value.

## Quick start

The current installation method uses a Git source checkout and an isolated mamba/conda environment.

From the repository root:

```bash
python scripts/rnatr_setup_source_checkout_v0.1.1.py \
  --catalog-bundle /path/to/rnatr_catalog_bundle.tar.gz
```

The setup creates the default environment at:

```text
~/.local/share/rnatr-scout/envs/source-checkout-v0.1
```

Activate it before running RNA-TR-Scout:

```bash
mamba activate ~/.local/share/rnatr-scout/envs/source-checkout-v0.1
```

or use `conda activate` if you use conda.

Check that the required reference and repeat-catalog resources are ready:

```bash
rnatr-scout resources-status
```

### Start from FASTQ

```bash
rnatr-scout run \
  --fastq sample.fastq.gz \
  --sample-id SAMPLE01 \
  --output-dir rnatr_SAMPLE01
```

RNA-TR-Scout will map the reads with the tested ONT-cDNA mapping workflow and then perform repeat analysis.

### Start from an existing BAM

```bash
rnatr-scout run \
  --fastq sample.fastq.gz \
  --bam sample.sorted.bam \
  --sample-id SAMPLE01 \
  --output-dir rnatr_SAMPLE01
```

The original FASTQ is still required because repeat measurement uses the source read sequence. Read identifiers in the BAM and FASTQ must correspond to the same reads.

### Mapping only

```bash
rnatr-scout map \
  --fastq sample.fastq.gz \
  --output-bam sample.sorted.bam \
  --sample-id SAMPLE01
```

## Main outputs

Results are written under:

```text
<output-dir>/final/
```

The five main result tables are:

| File | What it contains |
|---|---|
| `read_evidence.tsv` | The main read-by-locus evidence table. Start here for most analyses. |
| `general_repeat_calls.tsv` | Repeat-calling attempts for each projected candidate, including candidates that could not be measured. |
| `repeat_events.tsv` | Repeat events retained on the original RNA reads. |
| `repeat_segments.tsv` | Motif components and repeat segments that make up each retained repeat event. |
| `repeat_interruptions.tsv` | Interruptions or changes within repeat tracts when detected. |

Compressed `.tsv.gz` copies are also produced.

Additional files record run provenance, resource identity, validation results, input-read consistency, and performance information.

See the [user guide](docs/USER_GUIDE.md) for a more detailed explanation of the outputs and how they relate to one another.

## Interpreting the results

RNA-TR-Scout reports **what is observed in RNA reads**. It does not by itself establish a DNA genotype.

Three points are especially important:

- A repeat that is not observed in RNA should not automatically be interpreted as absent from the genome. The transcript may not have been expressed, sequenced, or covered across the repeat.
- Some repeat measurements are exact, while others are lower bounds because the read or sequence context ends before the full repeat can be resolved.
- A candidate repeat locus can be identified even when the current caller cannot produce a final repeat measurement. A missing motif or repeat length therefore does not necessarily mean that no repeat is present.

The tool intentionally preserves these distinctions so that downstream analyses can separate biological signals from limitations of RNA coverage and repeat observability.

## Currently tested scope

RNA-TR-Scout has been tested end-to-end with ONT cDNA data on more than one Linux x86-64 computer, with reproducible scientific output for the test datasets used during development.

The current standard setup uses:

- GRCh38 / GENCODE v50
- minimap2 for ONT-cDNA mapping
- a compact RNA-TR-Scout repeat catalog derived from TRExplorer and STRchive resources

Other compatible references or custom repeat catalogs can be explored, but they have not yet been tested as extensively as the standard setup.

The following are planned or still under development:

- ONT direct RNA
- PacBio Iso-Seq and Kinnex
- non-x86-64 systems
- simplified public package installation
- automatic public download of the compact repeat catalog

## Documentation

For most users:

- [User guide](docs/USER_GUIDE.md) — installation, running the software, outputs, interpretation, resume, and troubleshooting
- [Catalog resources](docs/catalog_resources/BUILDING_AND_UPDATING_CATALOGS.md) — for users who need to rebuild or modify repeat catalogs

Detailed development, reproducibility, and validation records are kept separately under `docs/release/` and related internal documentation directories. They are not required for ordinary use of RNA-TR-Scout.
