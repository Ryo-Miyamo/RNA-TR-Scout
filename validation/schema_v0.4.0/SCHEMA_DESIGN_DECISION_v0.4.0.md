# Evidence schema v0.4.0 design decision

Status: FROZEN CANDIDATE after Stage 14J v0.1.1 Pro audit; production promotion requires Stage 14K 100k materialization PASS.

## Design
- Preserve all 46 v0.3.2 `read_evidence` columns as an exact prefix and retain its read x target-region x locus-hypothesis grain.
- Preserve all 27 v0.3.2 `repeat_segments` columns as an exact prefix.
- Reuse existing `locus_id`, `motif`, normalized `sizing_status`, and call/status fields instead of creating ambiguous duplicates.
- Add best-attempt summaries plus caller-attempt, called-attempt, error, and repeat-event counts to `read_evidence`.
- Preserve non-overlapping repeat events and compound components through explicit `repeat_event_id` grouping.
- Add typed `general_repeat_calls` to preserve every one of the 77 deterministic caller fields for every attempted projection.
- Add `repeat_interruptions` for normalized interruption intervals while retaining source JSON losslessly.
- Keep caller-native and final-evidence semantics distinct through explicit crosswalks.
- Do not rewrite historical v0.3.2 outputs.

## Observed engineering grain
The 100k deterministic caller file contains 388571 projection attempts grouped into 388571 read-target-locus evidence groups; 0 groups have multiple attempts and the observed maximum is 1. Therefore a one-to-one caller-record/read-evidence design is not assumed.

## Why v0.1.0 was replaced
The first draft duplicated existing locus/motif/status concepts, treated one caller attempt as one read-evidence row, supplied additions-only dictionaries, did not replace the full schema/validator contract, and lacked explicit multi-event and interruption normalization. It must not be executed.
