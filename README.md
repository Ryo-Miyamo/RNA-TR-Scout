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

1. maps ONT-cDNA reads to the genome, or accepts a suitable existing RNA-seq BAM;
2. identifies reads that overlap known or candidate tandem-repeat regions;
3. projects the repeat locus onto the original read sequence;
4. searches the read for repeat motifs and repeat structure; and
5. produces read-level tables that can be used for downstream analysis.

The software keeps the original RNA-read evidence so that repeat length, motif structure, interruptions, mapping ambiguity, and incomplete observations can be examined downstream.

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

RNA-TR-Scout will map the reads with the tested ONT-cDNA splice-aware mapping workflow and then perform repeat analysis.

### Start from an existing BAM

```bash
rnatr-scout run \
  --fastq sample.fastq.gz \
  --bam sample.sorted.bam \
  --sample-id SAMPLE01 \
  --output-dir rnatr_SAMPLE01
```

Do not treat `--bam` as accepting an arbitrary BAM. The intended input is a **genome-aligned long-read RNA-seq BAM produced with splice-aware mapping to a compatible reference**. The original FASTQ is also required, and BAM/FASTQ read identifiers must correspond to the same reads.

If you are unsure how an existing BAM was produced, starting from FASTQ and letting RNA-TR-Scout perform the mapping is the safer option.

### Mapping only

```bash
rnatr-scout map \
  --fastq sample.fastq.gz \
  --output-bam sample.sorted.bam \
  --sample-id SAMPLE01
```

## Disk space and memory planning

The standard reference setup downloads approximately **0.9 GB of compressed GENCODE data** (GRCh38 primary-assembly FASTA plus GENCODE v50 primary-assembly GTF), in addition to the RNA-TR-Scout repeat-catalog bundle. The installer expands the reference and builds a minimap2 index, so reference setup requires substantially more space than the compressed download alone. Plan for **tens of GB of free disk space** during initial setup.

Analysis working space depends strongly on the number and length of reads. RNA-TR-Scout currently retains restartable intermediate files and detailed read-level evidence, so large runs can use substantial disk space.

In a **5.31-million-read development run**, approximately **140 GB of checkpoint/work files** were present at one audited restart stage. This is an observed working-data volume, **not a measured peak-disk requirement**. Peak disk usage has not yet been formally benchmarked, so no fixed minimum free-space requirement is claimed for a five-million-read run at this stage.

For the current ONT-cDNA mapping workflow, **32 GB RAM is a sensible practical target**; 16 GB may be tight during human-genome mapping.

See the [user guide](docs/USER_GUIDE.md) for more detail on resource planning.

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

Three points are especially important:

- A repeat that is not observed in RNA should not automatically be interpreted as absent from the genome. The relevant transcript may not have been expressed, sequenced, or covered across the repeat.
- Some repeat measurements are exact, while others are lower bounds because the read or sequence context ends before the full repeat can be resolved.
- A candidate repeat locus can be identified even when the current caller cannot produce a final repeat measurement. A missing motif or repeat length therefore does not necessarily mean that no repeat is present.

The tool preserves these distinctions so that downstream analyses can separate biological signals from limitations of RNA coverage and repeat observability.

## Current limitations of repeat calling

The current automatic caller is designed primarily for periodic tandem-repeat structures and can represent several useful features, including multiple motif components and interruptions in supported calls.

It is **not yet a general solver for highly complex or sequence-variable repeat regions**. Loci with complicated variation-cluster-like architecture or other repeat structures requiring specialized sequence-level interpretation may still be identified as candidate read/locus evidence without receiving a complete automatic repeat measurement.

These cases are retained in the output rather than silently being interpreted as negative calls.

## Currently tested scope

RNA-TR-Scout has been tested end-to-end with ONT cDNA data on more than one Linux x86-64 computer, with reproducible scientific output for the test datasets used during development.

The current standard setup uses:

- GRCh38 / GENCODE v50
- splice-aware minimap2 mapping for ONT cDNA
- a compact RNA-TR-Scout repeat catalog derived from TRExplorer and STRchive resources

Other compatible references or custom repeat catalogs can be explored, but they have not yet been tested as extensively as the standard setup.

The following are planned or still under development:

- more complete analysis of complex sequence-variable repeat architectures
- ONT direct RNA
- PacBio Iso-Seq and Kinnex
- non-x86-64 systems
- simplified public package installation
- automatic public download of the compact repeat catalog

## Documentation

For most users:

- [User guide](docs/USER_GUIDE.md) — installation, input requirements, running the software, outputs, interpretation, resource planning, resume, and troubleshooting
- [Catalog resources](docs/catalog_resources/BUILDING_AND_UPDATING_CATALOGS.md) — for users who need to rebuild or modify repeat catalogs

Detailed development, reproducibility, and validation records are kept separately under `docs/release/` and related internal documentation directories. They are not required for ordinary use of RNA-TR-Scout.
