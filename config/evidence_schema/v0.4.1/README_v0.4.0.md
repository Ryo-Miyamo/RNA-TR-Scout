# RNA-TR-Scout evidence schema v0.4.0

Status: FROZEN CANDIDATE; production promotion requires Stage 14K 100k end-to-end materialization PASS.

Tables:
- read_evidence (70 columns; first 46 are v0.3.2-compatible)
- repeat_events (43 columns; normalized non-overlapping event table)
- repeat_segments (38 columns; first 27 are v0.3.2-compatible)
- general_repeat_calls (85 columns; lossless caller-attempt audit)
- repeat_interruptions (20 columns)

Validator: rnatr_v04_validate_tsv.py
Package validator: rnatr_v04_validate_package.py
