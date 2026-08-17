# RNA-TR-Scout

RNA-TR-Scout is a tool for detecting and characterizing **tandem-repeat sequences observed in long-read RNA sequencing data**.

It is designed to help researchers find which repeat loci are represented in individual long RNA reads, estimate repeat length and motif structure when possible, and retain the read-level evidence needed for downstream biological analysis.

The currently tested setup is:

- Oxford Nanopore cDNA long-read RNA sequencing
- GRCh38 / GENCODE v50
- Linux x86-64

> **Release:** this source tree is RNA-TR-Scout v0.5.0. See `CHANGELOG.md` and `docs/release/RELEASE_NOTES_v0.5.0.md` for release scope and limitations.

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
python scripts/rnatr_setup_source_checkout_v0.1.1.py
```

The setup downloads and verifies the standard GENCODE resources and the compact RNA-TR-Scout repeat catalog automatically when they are not already available locally.

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

You can also inspect the detected CPU, RAM, temporary-directory, and free-space state:

```bash
rnatr-scout system-info
```

### Start from FASTQ

```bash
rnatr-scout run \
  --fastq sample.fastq.gz \
  --sample-id SAMPLE01 \
  --output-dir rnatr_SAMPLE01
```

RNA-TR-Scout will map the reads with the tested ONT-cDNA splice-aware mapping workflow and then perform repeat analysis. Core shard/concurrency values are selected automatically from the input scale and detected resources unless you provide explicit advanced overrides.

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

## Disk space, CPU, and memory planning

RNA-TR-Scout has been tested on Linux x86-64. For large datasets of roughly five million long reads, the current practical recommended profile is a multi-core system with approximately **128 GB RAM** and **fast local SSD/NVMe storage**.

Large runs can require substantial working disk space because restartable intermediate files and detailed read-level evidence are retained. Exact needs vary with dataset and run settings.

See the [user guide](docs/USER_GUIDE.md) for detailed resource-planning observations, caveats, and current benchmark scope.

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

RNA-TR-Scout has been tested end-to-end with ONT cDNA data on more than one Linux x86-64 computer, with reproducible scientific output for the test datasets used during development. Fresh source checkout, isolated environment creation, network resource installation, automatic Core resource selection, and resume behavior have also been exercised on an independent second Linux x86-64 computer.

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

## License

RNA-TR-Scout software source code is licensed under the **BSD 3-Clause License (`BSD-3-Clause`)**. Copyright (c) 2026 Ryosuke Miyamoto. See [`LICENSE`](LICENSE).

Third-party data, catalog source material, reference resources, and external software dependencies remain subject to their own upstream terms and are not relicensed by the RNA-TR-Scout software license. See [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) and the records under `docs/catalog_resources/third_party/`.

## Documentation

For most users:

- [User guide](docs/USER_GUIDE.md) — installation, input requirements, running the software, outputs, interpretation, resource planning, resume, and troubleshooting
- [Catalog resources](docs/catalog_resources/BUILDING_AND_UPDATING_CATALOGS.md) — for users who need to rebuild or modify repeat catalogs
- [Development guide](DEVELOPMENT.md) — entry points for biology, platform-extension, and performance development
- [Development history](docs/history/DEVELOPMENT_HISTORY_v0.5.0.md) — narrative map of how the project reached the v0.5.0 release line
- [Changelog](CHANGELOG.md) — concise public release-line summary

Ordinary users should use the documented `rnatr-scout` commands. Stage-numbered scripts under `scripts/` are primarily development, validation, and reproducibility history and are **not part of the ordinary user workflow**.

Detailed development, reproducibility, and validation records are kept separately under `docs/release/` and related internal documentation directories. They are not required for ordinary use of RNA-TR-Scout.
