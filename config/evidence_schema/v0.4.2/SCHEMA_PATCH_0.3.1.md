# Evidence schema patch 0.3.1

## Added evidence classes

- `LEFT_ONLY_INTERNAL`
- `RIGHT_ONLY_INTERNAL`

These states retain one-flank, target-overlapping repeat evidence when the
tract does not reach the expected raw-read end. They must not be interpreted
as exact repeat sizes or censored lower bounds.

## Added sizing status

- `partial_internal`

## Rationale

The first target-constrained pilot produced one-flank reads containing a
repeat tract over the target but not continuing to the raw-read boundary.
Classifying those rows as `UNRESOLVED` discarded useful sequence evidence;
classifying them as censored would falsely imply a repeat-length lower bound.
