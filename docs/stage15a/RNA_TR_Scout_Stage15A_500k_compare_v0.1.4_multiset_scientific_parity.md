# Stage 15A deterministic 500k compare amendment v0.1.4

Date: 2026-08-09

## v0.1.3 failure

The cross-run nested 250k comparison correctly removed explicit run-derived
identifiers, but it then imposed a uniqueness requirement on a hand-chosen
natural key.

`repeat_events` legitimately contained more than one row with the same
read/locus/event-index/read-coordinate tuple. Therefore that tuple is not an
identity contract and must not be promoted into one merely for comparison.

## v0.1.4 comparison contract

No new biological identity key is invented.

For the original nested 250k read set:

- explicit run-derived run/projection/alignment/materialization IDs are removed
- every remaining field is retained
- all normalized rows are sorted as a multiset
- duplicate multiplicity is preserved
- row count, normalized header, and full normalized multiset SHA-256 must match

The same rule is applied to caller attempts after excluding explicit
run/projection/alignment IDs.

This is stricter than summary comparison: any non-run-derived field difference,
missing row, extra row, or duplicate-count difference causes failure.

No BAM-to-final stage is rerun or modified.

Active pipeline modification: PROHIBITED
SSOT modification: PROHIBITED
Full 5.31M run: PROHIBITED
