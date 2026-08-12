# RNA-TR-Scout Stage 15C runtime-script binding amendment v0.1.5

## Failure addressed

The v0.1.4 clean full run completed a fresh 144-shard BAM/FASTQ partition,
then stopped at the first 11b wave because runtime-generated shard scripts
still contained the obsolete 500k analysis run ID `ENCSR307SHM_stage15a500k_seed20260809_mm2splice_v1`.
No 11b shard passed, caller/materializer did not start, and no final package was published.

## v0.1.5 contract

- Formal analysis run ID: `ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1`
- Mapping run ID: `ENCSR307SHM_full5312696_mm2splice_v1`
- Shards/concurrency: `144` / `12`
- Post-11b hard maximum: `164,204` candidate rows/shard
- Binding amendment SHA-256: `61576df920008f0e96b73e3246dae7a53404c68c380c74f00491aa459983af82`
- The three frozen scientific shell templates are copied byte-for-byte except for
  exact old-analysis-run-ID to full-analysis-run-ID substitution.
- Each bound template must contain zero obsolete IDs, zero mapping IDs, preserve
  all source run-ID anchor lines, and pass `bash -n`.
- The exact Stage15A `setup_shard_files` function is exercised during builder and
  runner preflight on a synthetic shard.
- During execution all 432 generated scripts are audited before partitioning and
  before the formal BAM-to-final timer.
- The failed v0.1.4 partition is never reused; v0.1.5 performs a fresh partition.

## Bound templates

### 11b

- Source: `/mnt/intelssd/rnatr_project/scripts/11b_extract_alignment_segments_and_target_candidates.stage15a500k_runid_v0.1.0.sh`
- Source SHA-256: `ccf37ebbe71451f12d113cb4148e5415ad7cbcd59ef954b7b7dd7a6b69078075`
- Bound: `/mnt/intelssd/rnatr_project/scripts/stage15c/full5312696_runid_bound_v0.1.5/11b_extract_alignment_segments_and_target_candidates.stage15c_full5312696_runid_bound_v0.1.5.sh`
- Bound SHA-256: `bc7523c081434ba7e545a3191aad4e7cb8c4e9d4c1ca771b3658399875a7fcd8`
- Exact run-ID substitutions: `1`

### 11d3

- Source: `/mnt/intelssd/rnatr_project/scripts/11d3_project_targets_to_raw_reads.stage15a500k_runid_v0.1.0.sh`
- Source SHA-256: `d7411df47e54e672ea3c838746402d35787c0d1c2fe0af628e7a7f36d98ea203`
- Bound: `/mnt/intelssd/rnatr_project/scripts/stage15c/full5312696_runid_bound_v0.1.5/11d3_project_targets_to_raw_reads.stage15c_full5312696_runid_bound_v0.1.5.sh`
- Bound SHA-256: `dede3a9b25f1e8fcc34ccd1ca5f95de7a15184496d7c96eddbfe119c66e57fe5`
- Exact run-ID substitutions: `1`

### 11e

- Source: `/mnt/intelssd/rnatr_project/scripts/11e_prepare_motif_scan_jobs.stage15a500k_runid_v0.1.0.sh`
- Source SHA-256: `b648b24f22c96fa5625baf09313500c2ca54668ed318ed0aa49570a10c743e3b`
- Bound: `/mnt/intelssd/rnatr_project/scripts/stage15c/full5312696_runid_bound_v0.1.5/11e_prepare_motif_scan_jobs.stage15c_full5312696_runid_bound_v0.1.5.sh`
- Bound SHA-256: `23c02846128b4cddefdba6879bbd731b30d552d70e9070b5d9122aebf7e5c0e2`
- Exact run-ID substitutions: `1`

## Non-modification guarantees

This amendment does not modify the active pipeline, SSOT, schema v0.4.2,
caller v0.4.1, materializer v0.1.2, mapping BAM/FASTQ, accepted 500k results,
or the retained v0.1.4 failure provenance.
