# Stage16AA independent-machine fresh validation v0.1.0

Date: 2026-08-17

## Status

**PASS — INDEPENDENT MACHINE FRESH INSTALL + RESOURCE AUTO-SELECTION + TIER2 EXACT PARITY**

Stage16AA validates the current post-Freeze release-engineering path on the second Linux x86-64 host `deeplearningboxii`.

## Validated source

- source branch: `stage16z-resource-aware-public-cli`
- source HEAD: `b8705454aaf73a6f0364b12f6e95b7d5cb995fc2`
- immutable Core Freeze root: `4b1981db955a8aa92a2a01e19bbb1cfc2aa0ebfb`
- clone mode: authenticated fresh private-GitHub clone
- fresh clone remained Git-clean after validation

## Independent-machine environment

Observed host state:

- hostname: `deeplearningboxii`
- Linux x86-64
- logical CPUs: 36
- total RAM: 134,726,070,272 bytes
- available RAM at planning time: 129,854,144,512 bytes
- selected tmp directory: `/tmp`
- free tmp/work filesystem space at planning time: 313,994,993,664 bytes

A fresh isolated conda environment was created. Standard reference resources were acquired through the network path and validated exact. The compact catalog was acquired through the public RNA-TR-Scout release asset path and validated exact.

## Resource bootstrap

The standard resource installation reported:

- reference source FASTA: `PASS_DOWNLOADED_EXACT`
- reference source GTF: `PASS_DOWNLOADED_EXACT`
- catalog source: `PASS_DOWNLOADED_EXACT`
- reference profile: `VALIDATED_REFERENCE_PROFILE`
- catalog profile: `VALIDATED_CATALOG_PROFILE`
- standard resources: `PASS_STANDARD_RESOURCES_READY`

Catalog outer archive SHA-256:

`54a24e4b60d920c8fec16b2df37b47e40407de42b949b18dc6233e97d85f2fef`

## Tier2 exact fixture

- BAM SHA-256: `0bb240a5293f08bc3231ad3ff0b8aa64bec813404cee4ff48932733726d89c18`
- source FASTQ SHA-256: `59a1704c9c3c386c279f18d9d57320f6b6a91a3d2d54cccc4de8ec5729601a74`

The fixture was supplied outside Git and accepted only after exact SHA verification.

## Automatic resource plan

The public workflow was run without manual Core worker-count overrides. The versioned resource policy selected:

- shards: 1
- concurrent Core units: 1
- caller workers per unit: 2

This exactly matches the expected Tier2 small-run profile.

## Scientific parity

All five plain scientific tables matched the frozen Tier2 golden identities exactly:

| table | rows | SHA-256 |
|---|---:|---|
| `read_evidence.tsv` | 13,959 | `df3d8a780c36e55635f66c2090d1c0aa6e9d651388bff173d2816ba88f107671` |
| `general_repeat_calls.tsv` | 13,959 | `b3ae0bfa87a5c6ba03e23942e485e74d1daa91761216bbe0f1d736fe6f245516` |
| `repeat_events.tsv` | 5,949 | `1f773ad0466f551eeff759264125feeeb267ca5e96d9d333f30dee9832d6749c` |
| `repeat_segments.tsv` | 5,994 | `1848881b2f75606b84f07a0bc82e0119a12a7f3b730bbc9471267d28ea8edd4f` |
| `repeat_interruptions.tsv` | 37 | `2b479e0b3689848b84f8d5ca6cd31e37634a9275a51e235e3c1448a6b87404c8` |

Result: `PASS_5_OF_5`.

A second resume completed as `PASS_SECOND_RESUME_NOOP`, with post-resume five-table parity still `PASS_5_OF_5`.

## Release-gate interpretation

Stage16AA directly supports:

- G25: automatic version-pinned/checksummed reference bootstrap;
- G26: CPU/RAM/tmp/free-space detection and provenance;
- G27: memory-aware automatic Core scheduling with manual override path;
- G28: scoped scientific reproducibility across the supported second Linux x86-64 host;
- G29: clean-machine-equivalent clone → fresh environment → network resources → public test-run reproducibility.

Together with Stage16Z Tier3 validation and prior Stage16S cross-hardware parity, this is sufficient to close G25–G29 for the currently tested Linux x86-64 ONT-cDNA release scope.

## Boundaries

Stage16AA does not establish:

- an empirical minimum CPU/RAM configuration;
- a measured full-scale peak-disk requirement;
- arbitrary hardware/OS portability;
- automatic mapping-thread tuning.

Those statements remain outside the accepted evidence.

Authoritative result JSON SHA-256:

`38ba94527d42bb08e13e600ea7c41ef4768c1571a70b6d1c7e50ab9f82a544f1`
