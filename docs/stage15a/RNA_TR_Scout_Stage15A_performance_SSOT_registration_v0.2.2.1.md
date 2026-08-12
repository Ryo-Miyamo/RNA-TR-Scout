# RNA-TR-Scout Stage 15A performance SSOT registration v0.2.2.1

Stage 15A v0.2.2.1 completed the isolated 100k BAM-to-final performance lane with exact logical package parity, frozen validators, post-publication frozen validation, failure-parity testing, and atomic publication.

Registered state:

- 100k BAM-to-final performance implementation: PASS
- measured production timer: 65.76363927999046 seconds
- reference-lane speedup: 5.078519507992296-fold
- conservative 5.31M linear projection: 58.230370558041365 minutes
- 60-minute hard-ceiling projection: PASS
- 30-minute target: TARGET_NOT_MET
- restart/resume validation: OPEN
- deterministic 250k scaling: OPEN
- empirical full 5.31M runtime: NOT RUN
- active pipeline: UNCHANGED

The 58.23-minute value is a 100k-derived linear projection, not an observed 5.31M runtime. Stage 15A therefore remains IN_PROGRESS and the full 5.31M run remains prohibited until restartability and intermediate-scale scaling are validated.
