# RNA-TR-Scout ONT-cDNA mapping contract v0.1.0

Status: post-Freeze release-engineering mapping adapter contract.

This contract does not modify the frozen BAM-to-final scientific Core.

## Validated profile

- platform/library profile: ONT cDNA
- parameter set: `rnatr_mm2_splice_cDNA_v0.3.1`
- minimap2: `2.31-r1302`
- samtools: `1.24`
- reference: GENCODE v50 GRCh38 primary assembly minimap2 index
- splice junctions: GENCODE v50 multi-exon transcript BED12

## Mapping parameters

`minimap2 -ax splice -t 16 --junc-bed <BED12> --secondary=yes -N 10 --MD --cs=long -R <RG> <MMI> <FASTQ>`

followed by:

`samtools sort -@ 8 -m 1G`

and samtools indexing.

## Resource identity

Exact reference identities are defined by
`config/mapping/ont_cdna_v0.1.0/resource_manifest.json`.

## Determinism interpretation

Stage16F reproduced the complete alignment content but not the raw coordinate-sort tie order.
The accepted release boundary is therefore the order-independent full SAM-record multiset,
together with record counts, read-to-record multiplicity, and header excluding `@PG`.

The newly mapped BAM then reproduced all five frozen Core output tables byte-for-byte.

## Timing boundary

FASTQ-to-BAM mapping time remains separate from the frozen BAM-to-final Core performance gate.
