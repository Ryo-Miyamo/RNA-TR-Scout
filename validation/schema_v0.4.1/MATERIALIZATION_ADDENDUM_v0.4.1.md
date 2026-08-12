# Evidence schema v0.4.1 materialization addendum

- Stage 14K populates edit-operation counts, normalized interruption intervals, purity, and LPS separately.
- Discordance origin fields remain NOT_ASSESSED unless a validated model is invoked.
- Locus clustering tables are optional and absent/empty when clustering is NOT_RUN.
- Stage 14K does not infer allele/haplotype labels.
- Stage 14K does not use censored or context-limited reads as exact cluster observations.
