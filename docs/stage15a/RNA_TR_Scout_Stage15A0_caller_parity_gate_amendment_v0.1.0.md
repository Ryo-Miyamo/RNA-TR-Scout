# RNA-TR-Scout Stage 15A0 caller parity gate amendment

**Amendment version:** `rnatr_stage15a0_caller_parity_gate_amendment_v0.1.0`  
**Target run:** `ENCSR307SHM_pilot100k_mm2splice_v1`  
**Applies to:** `rnatr_stage15a_contract_preflight_v0.1.1`  
**Scope:** read-only Stage 15A0 gate correction only; no active-pipeline switch and no 5.31M execution

## 1. Host preflight result

The uploaded Stage 15A0 preflight bundle has SHA-256:

```text
67d331c178a8fb867f65e1b79a99b2c48574f5cc7907f6f808abf441ab445d20
```

All actual prerequisite checks passed:

```text
critical_artifact_or_format_failures       0
input_format_failures                      0
missing_or_empty_artifacts                 0
sha_mismatch_artifacts                     0
deterministic_caller_validation_qc_status  PASS
caller_driver_contract_pass                true
exact_v042_validators_present              2
projection_job_order_lockstep              true
frozen_caller_suffix_columns               77
frozen_caller_suffix_rows                  388571
active_pipeline_modified                   false
full_5_31m_run_started                     false
```

The sole `REVIEW` trigger was:

```text
frozen_package_suffix_exact_reference_match  false
```

## 2. Why the v0.1.1 equality test is not the correct materialization gate

The v0.1.1 preflight compares two ordered byte streams:

1. the 77-column suffix extracted from the published 85-column package, rewritten with LF line endings; and
2. the Stage 14G caller reference in its original row order and original line endings.

That test is stricter than the Stage 15A package contract. Materializer v0.1.2 performs both of the following:

1. it copies all 77 caller fields exactly and verifies a lossless suffix hash **before sorting**; and
2. it then sorts the published `general_repeat_calls` rows by `projection_id` before writing the package.

Therefore an exact ordered byte hash of the published package suffix is not expected to match an unsorted caller-input file when caller input order is not already `projection_id` order. Line-ending normalization can create an additional serialization-only difference.

This does **not** justify assuming parity. The corrected gate must prove equality by key and by every field.

## 3. Corrected Stage 15A0 parity contract

Stage 15A0 caller parity passes only when all of the following hold:

```text
A. Stage14G reference vs Stage14K promoted caller artifact
   - decompressed byte SHA-256 exact
   - header exact
   - rows = 388571

B. Stage14G reference vs Stage14K2 package caller suffix
   - package prefix is the frozen 8-column materialization prefix
   - suffix header is the exact 77-column caller header
   - rows = 388571
   - projection_id unique in both inputs
   - projection_id key sets exact
   - every one of the 77 field values exact for every projection_id
   - called attempts = 160315
   - LOW_CONFIDENCE called attempts = 6307
```

The following are recorded but are non-blocking when B passes:

```text
row-order difference
LF/CRLF difference
gzip raw-byte difference
```

## 4. Resolver

Use:

```text
rnatr_stage15a0_resolve_caller_parity_v0.1.0.py
```

Default output:

```text
/mnt/intelssd/rnatr_project/qc/15_stage15a_contract_preflight/
  ENCSR307SHM_pilot100k_mm2splice_v1/
  v0.1.2_caller_parity/
```

The resolver is read-only for all Stage 14 and active-pipeline artifacts. It writes only the new Stage 15A0 QC directory.

## 5. Decision rule

```text
audit_status = PASS
next_gate = READY_TO_FREEZE_STAGE15A_EXECUTION_BUNDLE
```

is required before the isolated 11b → 11d3 → 11e → native caller → schema v0.4.2 runner is executed.

No full 5.31M run is authorized by this amendment.
