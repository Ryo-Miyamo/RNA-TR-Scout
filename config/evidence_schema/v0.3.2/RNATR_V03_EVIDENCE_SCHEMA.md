# RNA-TR-Scout v0.3 Evidence Schema

Schema version: **0.3.0**

## Core design

The evidence model deliberately separates:

1. **Alignment evidence** — where and how a read maps.
2. **Sequence evidence** — what repeat structure is observed on the raw read.
3. **Molecule evidence** — whether multiple reads represent independent molecules.
4. **Aggregate evidence** — locus- and region-level summaries.

No table may encode absence of RNA evidence as absence of a DNA repeat expansion.

## Canonical output tables

| Table | Grain | Purpose |
|---|---|---|
| `run_manifest` | one row per run | Full provenance and reproducibility |
| `alignment_segments` | one row per BAM record/segment | Primary, secondary, supplementary and clipping/splicing evidence |
| `read_evidence` | one row per read × target × locus hypothesis | Locus assignment, flank evidence, SPAN/censored class, call summary |
| `repeat_segments` | one row per repeat segment | Raw-read motif, length, purity and interruption detail |
| `molecule_clusters` | one row per inferred molecule | Duplicate/near-duplicate grouping |
| `molecule_membership` | one row per evidence membership | Read-to-molecule linkage and weights |
| `locus_summary` | one row per sample × locus | Candidate ranking and RNA evaluability |
| `region_summary` | one row per sample × analysis region | VC and disease-region interpretation |
| `qc_metrics` | one row per metric | Long-format run and output QC |

## Frozen semantic rules

### Coordinates

- Genomic coordinates: **0-based, end-exclusive**
- Read coordinates: **0-based, end-exclusive**
- `left` and `right` flanks mean **genomic-left** and **genomic-right**, not read 5′/3′.

### SPAN and censored evidence

- `SPAN`: both unique genomic flanks are anchored and repeat boundaries are observed.
- `LEFT_ANCHORED_CENSORED_RIGHT`: genomic-left flank is anchored; repeat continues to the read end without a genomic-right flank.
- `RIGHT_ANCHORED_CENSORED_LEFT`: genomic-right flank is anchored; repeat continues to the read start without a genomic-left flank.
- Censored evidence reports a **lower bound**, never an exact length.

### Alignment retention

Primary, secondary and supplementary alignments are retained until final locus assignment. Low MAPQ is evidence of ambiguity, not an automatic discard rule.

### Molecule independence

Read support and independent-molecule support are separate quantities. PCR-cDNA duplicate-like reads may share one molecule cluster.

### RNA-negative language

Allowed locus-level states include:

- `EVIDENCE_PRESENT`
- `COVERED_NO_OUTLIER_SIGNAL`
- `INSUFFICIENT_COVERAGE`
- `NO_RNA_COVERAGE`
- `AMBIGUOUS`
- `NOT_EVALUATED`

`COVERED_NO_OUTLIER_SIGNAL` means only that no outlier signal was found in the observed RNA. It must not be reported as a DNA-repeat-negative result.

### Analysis modes

- `TR` / `TR_FALLBACK`: copy-number-first, followed by sequence review.
- `VC`: sequence-level analysis across the full variation-cluster region.
- Complex STRchive disease regions: disease-region sequence-level review.

## Missing values and delimiters

- Missing value: `.`
- Booleans: `true` / `false`
- Multi-valued fields: semicolon-separated
- TSV text fields must not contain literal tabs or newlines.

## Stable identifiers

- `evidence_id`: first 24 hex characters of SHA-256 over `run_id|read_id|target_region_id|locus_id`
- `repeat_call_id`: first 24 hex characters of SHA-256 over `evidence_id|segment_index|motif|read_start|read_end`
- `molecule_cluster_id`: deterministic hash of run, sample, locus and representative molecule signature

## Validation

```bash
python rnatr_v03_validate_tsv.py \
  --schema schema/rnatr_v03_table_schema.json \
  --table read_evidence \
  --input read_evidence.tsv.gz
```

The validator checks exact header order, required fields, primitive types and controlled enums.
