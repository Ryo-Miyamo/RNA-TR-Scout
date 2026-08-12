# RNA-TR-Scout population-reference hierarchy
## Decision checkpoint — 2026-08-05

## Core decision

RNA-TR-Scout must separate three functions that were previously at risk of being conflated:

1. **Locus/catalog definition** — genomic interval, reference motif, canonical motif, motif size, reference copy number, purity, source catalog.
2. **DNA population distribution** — allele-length and longest-pure-segment distributions measured in long-read DNA cohorts.
3. **RNA molecule measurement** — tract length, motif decomposition, interruptions and censoring measured directly from each RNA read.

No single database is authoritative for all three.

## Adopted hierarchy

### 1. Primary locus and motif catalog: TRExplorer v2

Use TRExplorer v2 as the main GRCh38 locus-addressability and motif-prior layer.

Use:
- coordinates and locus ID
- reference motif and canonical motif
- motif size
- reference copy number
- repeat purity and region size
- source catalog
- disease and gene annotations
- HPRC256 HiFi copy-number histogram when present

Do not treat the catalog motif as the final RNA allele composition. RNA sequence measurement remains primary for the observed molecule.

### 2. Primary population repeat-length and LPS reference: AoU HiFi validation cohort

Use the 2,102-individual PacBio HiFi validation cohort as the primary DNA population distribution.

Primary statistics:
- allele-length percentiles, including P95, P99, P99.9 and observed maximum
- LPS per locus
- LPS per motif
- mean, standard deviation, MAD and mode
- unique lengths and, where available, unique allele sequences

Do not reduce the reference to a single min–max range.

### 3. Independent confirmation layers

- AoU discovery cohort: 543 individuals, higher-depth PacBio HiFi
- AoU/1KGP replication cohort: 500 ONT genomes
- HPRC256: 256 PacBio HiFi genomes, available through TRExplorer
- 1KG Vienna ONT v1.1: 1,019 ONT genomes and 361,362 VAMOS VNTR loci

Keep cohort, platform and caller labels separate. Do not silently pool distributions.

### 4. Disease-specific layer

Use STRchive and, in a later source-specific stage, gnomAD disease-associated STR data for known disease loci and literature thresholds. These are not substitutes for genome-wide population distributions.

### 5. TR-Atlas

Retain the completed pilot metadata cache for provenance and supplementary short-read context. Do not continue a genome-wide individual-page or API crawl. TR-Atlas is not the primary source for long-repeat sizing or motif decomposition.

## Promotion rule for population comparison

A DNA population distribution may be attached to an RNA locus only when:

- build and coordinate convention are verified;
- exact coordinate match or a formally validated safe-equivalent match is established;
- motif equivalence, phase and boundary relationship are recorded;
- source cohort, platform, caller, sample/allele count and missingness are retained;
- the RNA result is described as population context, not as inferred personal DNA genotype.

## Coverage reporting

Every result must retain the global denominator of 11,042 pilot loci and report:

- exact population-comparable coverage;
- validated safe-equivalent coverage;
- source-union coverage;
- no-reference coverage;
- coverage stratified by chromosome, motif size, RNA support bin and locus class.

The current coverage gate remains HOLD until bulk long-read sources are crosswalked and same-protocol RNA controls are introduced.
