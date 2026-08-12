# RNA-TR-Scout Stage 15A restart/resume 100k audit v0.1.0

This audit validates selective restart/resume without modifying the active
pipeline or SSOT and without running the full 5.31M sample.

The validated v0.2.2.1 100k run is used as immutable checkpoint provenance.
The largest caller shard is recomputed freshly, an intentional interruption is
injected after that caller completes but before its materializer runs, and no
partial final package is published. Resume verifies every checkpoint SHA,
reuses the completed caller and 11 already validated materializer shards,
runs only the missing materializer shard, rebuilds and validates the global
package, publishes it atomically, and requires exact logical parity with
v0.2.2.1. A second resume must be a no-op with an unchanged package manifest.

The scope is caller-checkpoint-to-final selective restart plus verification of
all adopted upstream artifacts. Deterministic 250k BAM-input scaling remains
the next separate gate.
