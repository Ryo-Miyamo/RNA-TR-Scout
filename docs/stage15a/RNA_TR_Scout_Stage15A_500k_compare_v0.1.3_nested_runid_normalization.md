# Stage 15A deterministic 500k compare amendment v0.1.3

Date: 2026-08-09

Replicate A and B of the 500k run both completed successfully. Their corrected
role×shard checkpoint logical comparison also passed with zero logical
differences.

The remaining failure was the nested 250k comparison contract.

11d3 derives alignment_id and projection_id from hashes containing run_id.
Therefore those identifiers are expected to change when moving from the formal
250k run ID to the formal 500k run ID, even for the same underlying read,
alignment, target, and scientific repeat result.

v0.1.3 performs cross-run scientific comparison as follows:

Caller:
- original 250k read set only
- unique stable read_id × target_region_id natural key
- explicit run/projection/alignment IDs excluded
- every remaining caller field compared exactly

Core 5-table package:
- original 250k read set only
- table-specific stable natural keys
- run ID and explicit run-derived projection/alignment/materialization IDs excluded
- every remaining field compared exactly

Any non-run-derived scientific difference still fails the audit.

No BAM-to-final stage is rerun or modified.

Active pipeline modification: PROHIBITED
SSOT modification: PROHIBITED
Full 5.31M run: PROHIBITED
