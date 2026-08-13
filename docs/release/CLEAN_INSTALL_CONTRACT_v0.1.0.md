# RNA-TR-Scout clean-install contract v0.1.0

Status: accepted source-checkout release-engineering contract after Stage16B.

This document is post-Freeze release engineering. It does not alter the frozen scientific Core.

## Validated installation path

The validated Stage16B path is:

1. authenticated fresh clone of the private GitHub repository;
2. exact frozen catalog installation with SHA-256 verification;
3. fresh isolated mamba environment;
4. frozen production-entry self-test;
5. native periodic-kernel load smoke;
6. real-read Golden Tier2 BAM + source FASTQ execution;
7. exact five-table row-count and SHA-256 parity;
8. package validation and PRE_BIOLOGY interface smoke.

Stage16B result:
`PASS_WITH_PUBLIC_WHEEL_BLOCKED`

The source-checkout Core clean-install checkpoint itself is accepted as PASS.

## Scientific execution boundary

The frozen Core production path consumes:

- a mapped BAM; and
- the read-coherent source FASTQ.

FASTQ-to-BAM mapping is outside the BAM-to-final Core timing boundary and is validated separately.

## Validated initial platform profile

Stage16B validated:

- Linux x86-64 source checkout;
- Python 3.10.20;
- pysam 0.24.0;
- samtools 1.24;
- htslib 1.24;
- bedtools 2.31.1;
- bash;
- gzip;
- sha256sum;
- git;
- GNU time at `/usr/bin/time`.

The frozen native periodic kernel is currently a prebuilt ELF x86-64 shared object.
Stage16B confirmed successful loading and execution on the validated Linux x86-64 system.

## Frozen catalogs

The following five runtime resources are not Git source payloads.
They are accepted only when their SHA-256 values match
`config/core_runtime/v0.1.0/resource_manifest.json` exactly:

- analysis regions
- disease regions
- mapping target BED
- mapping target BED index
- mapping target TSV

The installer `scripts/install_frozen_core_resources_v0.1.0.py` installs only the
expected member set and rejects unsafe paths or SHA drift.

## Wheel scope

Stage16A showed that the current Python wheel omits the frozen native `.so`.
No C/C++ source/build recipe was found in the active repository inventory.

Therefore **wheel installation is not an accepted Core distribution path at this checkpoint**.
The accepted path is the validated source checkout. Wheel support can be repaired later without
changing the frozen scientific Core.

## Freeze protection

Immutable Local Core Freeze root commit:
`4b1981db955a8aa92a2a01e19bbb1cfc2aa0ebfb`

Internal tag:
`local-core-freeze-v0.1.0-internal`

Neither may be rewritten, moved, amended, rebased, or force-replaced by release engineering.
