# RNA-TR-Scout Stage 15E determinism/restart acceptance and Stage 15F registration v0.1.1

Stage 15E completed the frozen release-scale determinism and restart/resume gate for the current Stage15 candidate.

Accepted evidence:

- full checkpoint rehash before intentional stop and first resume: 1,884 artifacts, 140,029,015,504 bytes, PASS;
- copied-manifest SHA corruption fixture rejected without modifying the source checkpoint;
- `shard_065` caller rerun under `PYTHONHASHSEED=20260810` with exact logical parity to the baseline hash-seed-0 output;
- selective first resume reused the fresh caller result, executed the target materializer once, reused 143 frozen shards, and reconstructed all 144 shards;
- five plain core tables and ten plain/gzip package-manifest entries matched the clean Stage15C package exactly at the required scientific comparison level;
- all frozen and memory-bounded validators passed before atomic publication;
- the second resume executed zero scientific commands and preserved size, mtime, inode, device, and SHA-256 for 20 scientific artifacts;
- the clean empirical runtime record remained 60.041256352 minutes with `PASS_WITH_DOCUMENTED_TOLERANCE` and was not overwritten.

Formal scope:

`CHECKPOINT_BASED_RELEASE_SCALE_RECONSTRUCTION_NOT_UPSTREAM_BAM_PARTITION_11B_11D3_11E_RERUN`

The accepted evidence closes the current checkpoint-based release-scale reconstruction and selective caller-to-final restart/resume requirement. It does not establish an independent upstream BAM partition/11b/11d3/11e full rerun, arbitrary upstream recovery, or cross-hardware/cross-machine reproducibility. G28 therefore remains open.

This registration does not promote the Stage15 candidate into `current_pipeline`, does not change caller v0.4.1, materializer v0.1.2, or schema v0.4.2, and does not overwrite the clean 60.041256352-minute benchmark. The immediate next gate is the PRE_RELEASE_CANDIDATE Architecture consistency audit, followed by explicit active-path promotion and G25-G30 release-readiness work.

Core Freeze governance prerequisites added before execution:

- an authoritative Core Freeze Packet is required and must be reconstructed from exact original artifacts;
- a versioned golden regression suite with fixed inputs, expected outputs, exact/logical parity rules, validators, manifests, and checksums is required;
- project-wide canonical documentation placement is required, with stage-local copies retained only as history or pointers;
- PRE_RELEASE_CANDIDATE and Core Freeze decisions may not be inferred from conversation summaries or memory; missing or size-capped originals must be requested and reread;
- Downloads cleanup is deferred until authoritative artifacts have been classified and moved to their canonical locations.

These requirements are registered as open blocking Core Freeze gates G32-G34. Stage15E registration does not itself close them or authorize Core Freeze.