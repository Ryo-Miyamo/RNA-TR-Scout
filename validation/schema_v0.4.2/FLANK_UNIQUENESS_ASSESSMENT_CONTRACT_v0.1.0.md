# Flank uniqueness assessment contract v0.1.0

The projection layer supplies flank-anchor lengths but does not calculate flank uniqueness.
Anchor presence is not equivalent to uniqueness.

- Never infer flank uniqueness from anchor length, MAPQ, geometry class, or competing-locus count.
- Without an explicit assessment, the boolean remains missing (`.`) and status is `NOT_ASSESSED`.
- `ASSESSED_UNIQUE` requires boolean `true`.
- `ASSESSED_NONUNIQUE` requires boolean `false`.
- A later versioned uniqueness module may populate assessed values.

Schema v0.4.2 preserves all v0.4.1 column names as an exact prefix, changes only the
requiredness of the two inherited booleans, and appends explicit status fields.
