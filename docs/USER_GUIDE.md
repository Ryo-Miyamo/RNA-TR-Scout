# RNA-TR-Scout user guide

RNA-TR-Scout detects and describes tandem-repeat evidence observed in long-read RNA sequencing data. The currently validated user profile is **Oxford Nanopore cDNA on Linux x86-64** with the frozen RNA-TR-Scout scientific Core.

This guide describes the ordinary source-checkout workflow. Stage-numbered development scripts, internal SHA values, and frozen runtime wiring are intentionally not part of the normal user interface.

## 1. What you provide

RNA-TR-Scout supports two user-facing input modes.

### FASTQ mode

Provide a source ONT-cDNA FASTQ. RNA-TR-Scout runs the validated minimap2 splice-aware mapping adapter and then the frozen Core.

```bash
rnatr-scout run \
  --fastq sample.fastq.gz \
  --sample-id SAMPLE01 \
  --output-dir rnatr_SAMPLE01
```

### BAM + FASTQ mode

Provide an already mapped BAM together with the **read-coherent source FASTQ** from which that BAM was produced.

```bash
rnatr-scout run \
  --fastq sample.fastq.gz \
  --bam sample.sorted.bam \
  --sample-id SAMPLE01 \
  --output-dir rnatr_SAMPLE01
```

The FASTQ is not optional in BAM mode. The frozen scientific input contract requires both the mapped alignments and the original read sequences with matching read identifiers.

If `--run-id` is omitted, `--sample-id` is used as the run identifier.

## 2. Installation and validated environment

The accepted distribution path at this stage is a **Git source checkout**, not a wheel.

Requirements for the validated profile:

- Linux x86-64
- Git
- mamba or conda
- network access for reference acquisition unless validated source files are supplied locally
- the validated RNA-TR-Scout catalog bundle

From the repository root, the setup helper creates and verifies the pinned environment, installs the source checkout in editable mode, checks the native periodic kernel, runs Core/mapping self-tests, and installs or verifies the standard resources.

```bash
python scripts/rnatr_setup_source_checkout_v0.1.1.py \
  --catalog-bundle /path/to/rnatr_catalog_bundle.tar.gz
```

By default, the isolated environment is created under:

```text
~/.local/share/rnatr-scout/envs/source-checkout-v0.1
```

The validated environment currently pins Python 3.10.20, pysam 0.24.0, samtools/htslib 1.24, bedtools 2.31.1, minimap2 2.31, and seqkit 2.13.0.

The current release-engineering candidate does not yet have a finalized public URL for the compact catalog bundle. Until that is resolved, supply the validated bundle explicitly with `--catalog-bundle`.

If the environment and resources are already installed, they can be rechecked with:

```bash
python scripts/rnatr_setup_source_checkout_v0.1.1.py --verify-only
```

You can also inspect resource readiness through the public CLI:

```bash
rnatr-scout resources-status
```

## 3. Mapping only

To run only the validated ONT-cDNA mapping adapter:

```bash
rnatr-scout map \
  --fastq sample.fastq.gz \
  --output-bam sample.sorted.bam \
  --sample-id SAMPLE01
```

The validated standard reference profile is GRCh38 / GENCODE v50. Compatible custom GRCh38 references may be used through the post-Freeze compatibility-aware mapping path, but they are outside exact golden-validation scope.

## 4. Output directory

A normal run writes the scientific result package under:

```text
<output-dir>/final/
```

The five primary scientific tables are:

| File | Meaning / grain |
|---|---|
| `read_evidence.tsv` and `.tsv.gz` | One row per read × target-region × locus hypothesis. This is the main evidence-level table and contains the stable `evidence_id`. |
| `general_repeat_calls.tsv` and `.tsv.gz` | One row per projection/general-caller attempt, including attempts that were not callable. |
| `repeat_events.tsv` and `.tsv.gz` | One row per retained non-overlapping repeat event on the raw read. |
| `repeat_segments.tsv` and `.tsv.gz` | One row per repeat segment or motif component within an evidence record. |
| `repeat_interruptions.tsv` and `.tsv.gz` | One row per interruption interval within a general repeat call. |

The plain TSV files are the exact scientific parity artifacts. Deterministic gzip copies are also emitted.

The final directory also contains provenance and QC artifacts such as:

- `core_result_manifest.json`
- `package_manifest.tsv`
- `validation_summary.tsv`
- `input_read_coherence.tsv`
- `shard_manifest.tsv`
- `performance.tsv`
- `resource_bindings.local.json`

These support reproducibility, validation, restart/recovery, and downstream traceability.

## 5. Important interpretation rules

RNA-TR-Scout reports **RNA evidence**, not a definitive DNA genotype.

In particular:

- RNA non-observation must not be interpreted as absence of a DNA repeat expansion.
- Exact repeat length requires appropriate spanning evidence. Censored observations are lower bounds, not exact sizes.
- A projected candidate can exist even when final repeat measurement is unavailable; projection success and successful repeat calling are separate concepts.
- Candidate multiplicity is a technical assignment property and should not automatically be interpreted as multiple independent biological repeat loci.
- Primary, secondary, and supplementary alignments are retained through locus assignment because repeat-containing reads may map ambiguously.

For most downstream analysis, start with `read_evidence.tsv` and join to the other four scientific tables using the stable IDs (`evidence_id`, `repeat_event_id`, `repeat_call_id`, `caller_record_id`, and `interruption_id`).

## 6. Resume after interruption

Runs are restartable. Re-run the same command with `--resume` and the same `--output-dir`, inputs, sample/run identifiers, and scientific configuration.

Example:

```bash
rnatr-scout run \
  --fastq sample.fastq.gz \
  --bam sample.sorted.bam \
  --sample-id SAMPLE01 \
  --output-dir rnatr_SAMPLE01 \
  --resume
```

The frozen restart contract verifies completed work before reusing it. A second resume on an already complete validated run has been tested to reach the `SECOND_RESUME_NOOP` state without changing the five scientific outputs.

## 7. What has been validated

The current internal release-engineering state has passed:

- fresh source-checkout installation on Linux x86-64;
- validated resource installation and verification;
- ONT-cDNA FASTQ → minimap2 splice-aware mapping → frozen Core → final output;
- BAM + read-coherent FASTQ → frozen Core → final output;
- exact five-table golden parity for the validated Tier2 test;
- restart/resume and second-resume no-op behavior;
- execution of the frozen native periodic kernel on a second Linux x86-64 PC (`deeplearningboxii`);
- cross-hardware exact scientific parity of all five Tier2 scientific tables on that second machine.

The Stage16S v0.1.0 validator report initially contained a SHA mismatch for `repeat_interruptions`; this was traced to an incorrectly transcribed expected SHA in the validator, not to a scientific-output difference. Stage16S v0.1.1 re-evaluated against the canonical golden manifest and passed.

These validations demonstrate exact parity for the tested Linux x86-64 systems and fixtures. They should **not** be interpreted as a universal guarantee for every CPU, operating system, sequencing platform, reference, or catalog.

## 8. Current scope and non-goals

Validated now:

- ONT cDNA
- Linux x86-64
- GRCh38 / GENCODE v50 validated reference profile
- validated TRExplorer/STRchive-derived RNA-TR-Scout catalog bundle
- source-checkout installation
- public CLI commands `resources-status`, `map`, and `run`

Not yet part of the validated public release scope:

- ONT direct RNA
- PacBio Iso-Seq / Kinnex
- non-x86-64 platforms
- public wheel installation
- arbitrary custom catalogs as exact-golden equivalents
- automatic public download of the compact catalog bundle
- the final public `v0.5.0` release decision

## 9. Catalogs and references

Ordinary users do not need the complete upstream TRExplorer or STRchive source repositories. The validated runtime uses a compact RNA-TR-Scout catalog bundle derived from TRExplorer v2.0 and a pinned STRchive source snapshot.

Advanced users who intentionally rebuild or update catalogs should follow:

[`catalog_resources/BUILDING_AND_UPDATING_CATALOGS.md`](catalog_resources/BUILDING_AND_UPDATING_CATALOGS.md)

Such catalogs are treated as custom-compatible resources rather than exact golden-validated replacements.

## 10. Getting help from the command line

```bash
rnatr-scout --help
rnatr-scout run --help
rnatr-scout map --help
rnatr-scout resources-status --help
```

The ordinary user workflow should use these public commands rather than directly invoking Stage-numbered development scripts.