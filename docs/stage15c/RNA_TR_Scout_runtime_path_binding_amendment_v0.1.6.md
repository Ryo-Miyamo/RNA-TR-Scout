# RNA-TR-Scout Stage 15C runtime path-binding amendment v0.1.6

## Defects addressed before v0.1.5 preflight

Pro audit found that the v0.1.5 11d3 runtime template still pointed to the
500k candidate/window FASTQ subpaths even though `create_shards()` used the
full5312696 paths. The same audit found `BOUND_SOURCE_ROOT` referenced but not
defined in v0.1.5, which would have failed at preflight bundle publication.
Neither v0.1.5 preflight nor v0.1.5 full execution was started.

## v0.1.6 path contract

- Analysis run ID: `ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1`
- Mapping run ID: `ENCSR307SHM_full5312696_mm2splice_v1`
- Runtime-path amendment SHA-256: `c972777c13834ca9c16bc7d4aaecbebb20d46d3518d266a851f17a7b4751d97a`
- Candidate benchmark root: `stage15c_full5312696_v1`
- Candidate FASTQ: `ENCFF260PGB.full5312696.rnatr_candidate_all.fastq.gz`
- Window FASTQ: `ENCFF260PGB.full5312696.rnatr_target_windows.v0.3.3.fastq.gz`
- Expected path checks: `23` per shard / `3312` full run
- All 432 generated scripts are audited before partition and timer start.
- Generated scripts are normalized for shard-specific paths.env and checked
  against frozen per-role SHA-256 values.
- v0.1.4 failed partition and all v0.1.5 artifacts are not reused.

## Bound sources

### 11b
- Source: `/mnt/intelssd/rnatr_project/scripts/stage15c/full5312696_runid_bound_v0.1.5/11b_extract_alignment_segments_and_target_candidates.stage15c_full5312696_runid_bound_v0.1.5.sh`
- Source SHA-256: `bc7523c081434ba7e545a3191aad4e7cb8c4e9d4c1ca771b3658399875a7fcd8`
- Bound: `/mnt/intelssd/rnatr_project/scripts/stage15c/full5312696_runtime_bound_v0.1.6/11b_extract_alignment_segments_and_target_candidates.stage15c_full5312696_runtime_bound_v0.1.6.sh`
- Bound SHA-256: `bc7523c081434ba7e545a3191aad4e7cb8c4e9d4c1ca771b3658399875a7fcd8`

### 11d3
- Source: `/mnt/intelssd/rnatr_project/scripts/stage15c/full5312696_runid_bound_v0.1.5/11d3_project_targets_to_raw_reads.stage15c_full5312696_runid_bound_v0.1.5.sh`
- Source SHA-256: `dede3a9b25f1e8fcc34ccd1ca5f95de7a15184496d7c96eddbfe119c66e57fe5`
- Bound: `/mnt/intelssd/rnatr_project/scripts/stage15c/full5312696_runtime_bound_v0.1.6/11d3_project_targets_to_raw_reads.stage15c_full5312696_runtime_bound_v0.1.6.sh`
- Bound SHA-256: `aa91b0ec33caee71c223ea6ac161de2b2ceb0095ae33a404f85bba51a81553c3`

### 11e
- Source: `/mnt/intelssd/rnatr_project/scripts/stage15c/full5312696_runid_bound_v0.1.5/11e_prepare_motif_scan_jobs.stage15c_full5312696_runid_bound_v0.1.5.sh`
- Source SHA-256: `23c02846128b4cddefdba6879bbd731b30d552d70e9070b5d9122aebf7e5c0e2`
- Bound: `/mnt/intelssd/rnatr_project/scripts/stage15c/full5312696_runtime_bound_v0.1.6/11e_prepare_motif_scan_jobs.stage15c_full5312696_runtime_bound_v0.1.6.sh`
- Bound SHA-256: `23c02846128b4cddefdba6879bbd731b30d552d70e9070b5d9122aebf7e5c0e2`

## Non-modification guarantees

The amendment does not modify the active pipeline, SSOT, schema v0.4.2,
caller v0.4.1, materializer v0.1.2, mapping BAM/FASTQ, accepted 500k
results, or retained v0.1.4 failure provenance.
