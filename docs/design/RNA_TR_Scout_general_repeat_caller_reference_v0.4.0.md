# RNA-TR-Scout general repeat caller reference v0.4.0

Stage 12E adds geometrically expanding, locus-anchored search windows after motif anchoring.

Purpose:
- recover long continuous repeat tracts when the projected/catalog prior covers only a short core;
- preserve the v0.3.0 requirement that every accepted tract overlap the projected locus core;
- retain explicit censoring and projection-context semantics from v0.3.0.

The disease-inspired benchmark uses known repeat motifs only as realistic sequence shapes. It does not apply disease thresholds, infer pathogenicity, estimate population normal ranges, or infer personal DNA genotype.

Promotion requires:
- v0.1.0 simple-periodic regression PASS;
- v0.2.0 compound/interruption/LPS regression PASS;
- v0.3.0 boundary/censor/de-novo regression PASS;
- broad simulation semantic invariants PASS;
- short-prior long-expansion recovery median >=0.90 and p10 >=0.80;
- real P0/P1 engineering regression completion, locus anchoring, and no major motif-concordance regression.

Performance optimization remains a separate next-stage task after semantic freeze.
