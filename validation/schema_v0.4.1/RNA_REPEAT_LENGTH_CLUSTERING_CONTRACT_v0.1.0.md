# RNA repeat-length clustering contract v0.1.0

`repeat_events` remains the read/molecule-level source of truth. Aggregation never replaces or discards those rows.

Default clusters are `UNPHASED_LENGTH_CLUSTER` with neutral labels C1, C2, ... . Length alone must not create allele 1/2, haplotype, maternal/paternal, expanded/normal, or pathogenic labels.

Haplotype/allele semantics require same-molecule SNP phasing, matched DNA, or explicit orthogonal support.

Exact uncensored events are the default fit set. Censored events are inequalities/lower bounds, not exact lengths. They may be excluded or used only by a versioned censor-aware interval-likelihood model. Context-limited events are not used for fitting in the initial contract.

`repeat_length_cluster_id` is distinct from legacy `molecule_cluster_id`.

Stage 14K records clustering as NOT_RUN; this schema does not activate a clustering algorithm.
