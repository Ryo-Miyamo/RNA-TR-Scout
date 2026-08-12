# RNA-TR-Scout Stage 15A3 11e pipefail report fix

Version: v0.1.2  
Date: 2026-08-08  
Run: `ENCSR307SHM_pilot100k_mm2splice_v1`

## 1. Observed v0.1.1 failure

The uploaded failure bundle was internally consistent.

```text
bundle_sha256  e54ba436f7ec1421639b5ac2b98b7262559ada9aad72324894712f23bcc5d503
failed_stage   15A3_11e
exit_status    141
```

Stages completed before the failure:

```text
15A1_11b   PASS   28.307 s
15A2_11d3  PASS   53.462 s
```

Both stages had logical parity with their frozen Stage 11 references. Raw gzip
SHA values differed only because recompression is not byte-stable.

The 11e builder also completed its scientific work and wrote QC with:

```text
expected_projection_rows  388571
observed_projection_rows  388571
unique_projection_ids     388571
audit_status              PASS
```

The process then failed while printing the human-readable “most common
canonical motifs” preview, before the output-manifest section.

## 2. Root cause

The frozen active 11e source contains:

```bash
set -euo pipefail

tail -n +2 "$MOTIF_DICTIONARY" |
  sort -t $'\t' -k4,4nr |
  head -n 30
```

After `head` receives 30 rows it closes its input. `sort` can then receive
SIGPIPE and return 141. With `pipefail`, that non-zero status aborts 11e even
though the builder and QC already passed.

This is a report-only shell control-flow defect. It is not a BAM,
projection, motif-job, or caller discrepancy.

## 3. Corrective action

Stage 15A v0.1.2 creates a new isolated root and patches only the frozen
Stage 15A copy of 11e:

```diff
-      head -n 30
+      sed -n '1,30p'
```

`sed -n '1,30p'` emits the same first 30 rows but consumes the complete
sorted stream, allowing all pipeline components to exit normally.

No builder code, input, output table, row order, manifest definition,
scientific decision rule, or active pipeline file is changed.

## 4. Preservation and prohibitions

- Failed v0.1.0 and v0.1.1 roots are preserved.
- v0.1.2 runs in a newly named isolated result/QC root.
- The active 11e source remains unchanged and is SHA-audited before and after.
- Full 5.31M execution remains prohibited.
- Active pipeline promotion remains prohibited until Stage 15A passes.
