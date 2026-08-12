# RNA-TR-Scout evidence schema v0.4.2

Status: FROZEN CANDIDATE pending successful Stage 14K1 materialization.

The projection layer records flank-anchor lengths but does not assess flank uniqueness.
The two inherited booleans are optional, and required status fields explicitly record
`NOT_ASSESSED`, `ASSESSED_UNIQUE`, or `ASSESSED_NONUNIQUE`.

No caller result or biological interpretation is changed.
