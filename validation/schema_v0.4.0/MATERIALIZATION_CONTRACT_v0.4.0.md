# General caller v0.4.1 to evidence v0.4.0 materialization contract

## Table grain
- `general_repeat_calls`: one row for every projection/caller attempt, including not-attempted records.
- `read_evidence`: one row per read x target-region x locus hypothesis, preserving the v0.3.2 grain.
- Multiple projection/caller attempts may map many-to-one to one `evidence_id`.
- `repeat_segments`: one row per retained repeat component; non-overlapping events and compound components are both preserved.
- `repeat_interruptions`: one row per normalized interruption interval.

## Evidence identity and aggregation
- `evidence_id` retains SHA-256(run_id|read_id|target_region_id|locus_id), first 24 hex.
- Caller attempts are grouped by that read-target-locus key.
- `caller_attempt_count`, `caller_called_count`, and `caller_error_count` summarize all grouped attempts.
- `best_projection_id` and `best_caller_record_id` refer only to the deterministic best attempt; raw attempts are never discarded.

## Multi-event contract
1. CALLED attempts are sorted by raw tract coordinates.
2. Positive-overlap raw intervals belong to the same repeat event and compete as hypotheses for that event.
3. Non-overlapping intervals are retained as separate events on the same read-target-locus evidence.
4. The primary attempt within each event is selected deterministically by:
   CALLED > not-called; PASS > LOW_CONFIDENCE; EXACT_SPAN > any lower-bound state > LOW_CONFIDENCE;
   then prior_overlap_bp, score_per_read_bp, purity, and MAPQ descending;
   assignment_rank ascending; projection_id lexical ascending.
5. Compound components from a retained primary attempt materialize as multiple `repeat_segments` rows sharing one `repeat_event_id`.
6. All competing/unused attempts remain in `general_repeat_calls` with explicit `materialization_status`.
7. The best event for read-level summary uses the same ranking; all retained events remain queryable.

## Existing-field reuse
- `representative_locus_id` populates existing `locus_id`; no duplicate locus column is added.
- `oriented_motif` populates existing `motif`; `canonical_motif` remains canonical.
- `best_mapq` populates existing `mapq_best`.
- `read_candidate_target_count` yields `competing_locus_count=max(0,n-1)`.

## Status normalization
- Best CALLED + EXACT_SPAN -> final `sizing_status=exact_span`.
- Best CALLED + LOWER_BOUND_* / CONTEXT_LIMITED_LOWER_BOUND -> `sizing_status=lower_bound`.
- Best CALLED + LOW_CONFIDENCE -> `sizing_status=no_call`, `qc_status=WARN`.
- No CALLED attempts -> `repeat_call_count=0`, `sizing_status=not_attempted` or `no_call`, with explicit GENERAL_CALLER_* failure code.
- Caller-native statuses remain losslessly available in `general_repeat_calls` and as best-caller summary fields; they are not silently conflated with final evidence statuses.

## Geometry normalization
- SPAN -> `evidence_class=SPAN` when exact-span conditions hold.
- LEFT_CENSORED -> `RIGHT_ANCHORED_CENSORED_LEFT`.
- RIGHT_CENSORED -> `LEFT_ANCHORED_CENSORED_RIGHT`.
- BOTH_CENSORED -> `BOTH_SIDES_CENSORED`.
- Internal/no-flank projection geometry -> `REPEAT_ONLY_UNANCHORED` when a tract is called.
- Otherwise -> `UNRESOLVED` or the existing no-repeat class dictated by projection/finalization rules.
Caller geometry remains separately available as `caller_evidence_geometry`.

## Repeat lengths
- `exact_repeat_bp` populates `repeat_bp_estimate` only for exact-span calls.
- `interval_lower_bp`, cross-checked with `lower_bound_bp`, populates `repeat_bp_lower_bound`.
- `interval_upper_bp` populates `repeat_bp_upper_bound` when finite.
- `repeat_units_estimate` is emitted only when the selected best event has an unambiguous primary motif; compound calls may leave it missing.

## Deterministic IDs
- caller_record_id: SHA-256(GENERAL_CALL|run_id|projection_id|caller_version), first 24 hex.
- repeat_event_id: SHA-256(REPEAT_EVENT|evidence_id|event_index|event_start|event_end), first 24 hex.
- repeat_call_id: SHA-256(REPEAT_SEGMENT|repeat_event_id|segment_index|read_start|read_end|canonical_motif), first 24 hex.
- interruption_id: SHA-256(INTERRUPTION|repeat_event_id|interruption_index|read_start|read_end), first 24 hex.

## Truth and interpretation guardrails
This schema records RNA repeat measurement. It does not infer DNA genotype, pathogenicity, or population-normal range.
