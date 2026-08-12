# RNA-TR-Scout Single Source of Truth database v0.1.1

## Purpose

The SSOT database separates:

1. **Facts** — runs, stages, scripts, checksums, inputs, outputs, QC, counts.
2. **Decisions** — which implementation or reference is currently adopted and what it supersedes.
3. **Interpretations** — what an observed result means, and what it must not be interpreted as.

The legacy build tracker remains read-only and is imported for provenance.

## Installed paths

```text
/mnt/intelssd/rnatr_project/metadata/ssot/
├── rnatr_ssot.sqlite
├── rnatr_ssot.py
├── CURRENT_STATE.md
├── exports/
└── backups/
```

## Current-state views

- `current_pipeline`
- `current_decisions`
- `current_interpretations`
- `current_algorithm_contract`
- `current_reference_hierarchy`
- `current_known_limitations`
- `current_open_questions`
- `current_results`
- `current_runs`
- `latest_stage_status`
- `current_artifacts`
- `project_dashboard`

## Commands

```bash
SSOT=/mnt/intelssd/rnatr_project/metadata/ssot/rnatr_ssot.py

python "$SSOT" rebuild
python "$SSOT" validate
python "$SSOT" show dashboard
python "$SSOT" show pipeline
python "$SSOT" show algorithm
python "$SSOT" show decisions
python "$SSOT" show interpretations
python "$SSOT" show references
python "$SSOT" show limitations
python "$SSOT" show questions
python "$SSOT" show results
```

Read-only SQL is also available:

```bash
python "$SSOT" query \
  "SELECT * FROM current_pipeline ORDER BY stage_order"
```

## Update policy

After a new pipeline stage finishes, run:

```bash
python /mnt/intelssd/rnatr_project/metadata/ssot/rnatr_ssot.py rebuild
```

The rebuild is atomic. An existing SSOT database is backed up first. The legacy tracker database, raw data, results, QC, scripts, and references are not modified.

A future production wrapper should call `rebuild` only after its own outputs and QC have been atomically finalized.

## Status vocabulary

### Decisions and interpretations

- `ACTIVE`
- `SUPERSEDED`
- `PROVISIONAL`
- `REJECTED`
- `LEGACY`

### Algorithm implementation state

- `IMPLEMENTED`
- `IMPLEMENTED_WITH_GATE`
- `PARTIALLY_IMPLEMENTED`
- `DESIGNED_NOT_IMPLEMENTED`
- `NOT_IMPLEMENTED`
- `DEPRECATED`

## Scientific interpretation rule

For general loci, RNA-TR-Scout reports population-relative longer, shorter, central, or non-comparable observations. It does not assign pathogenicity. Known disease-locus thresholds remain a separate curated context.


## v0.1.1 validator-resolution rule

The adopted alignment-segment validator is recorded as an explicit absolute
path to `validator_v0.3.1`. The SSOT must never promote an unresolved shell
expression such as `$SCHEMA_DIR/...` into `current_pipeline`.

Validation fails if any active script/validator path contains an unexpanded
shell variable, if the current validator file does not exist, or if its SHA-256
cannot be recorded.

