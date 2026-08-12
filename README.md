# RNA-TR-Scout

> **Internal laboratory snapshot — not the public v0.5.0 release.**

This repository currently contains the internal Git history beginning from the accepted
RNA-TR-Scout Local Core Freeze.

## Frozen internal baseline

- Freeze ID: `LOCAL_CORE_FREEZE_V0.1.0`
- immutable root commit: `4b1981db955a8aa92a2a01e19bbb1cfc2aa0ebfb`
- internal tag: `local-core-freeze-v0.1.0-internal`
- final Core Freeze manifest SHA-256:
  `c9a54b4c01dd67d2b7df9d96ba4c86bbe26c02e2ef6f4180c8f152927129125b`

The root commit is intended to remain an exact internal snapshot of the accepted Local Core
Freeze. Subsequent commits may improve repository organization, documentation, packaging,
installation, and release engineering without rewriting that frozen point.

## Current scope

The validated current profile is ONT cDNA with the frozen RNA-TR-Scout scientific Core.
Large sequencing inputs, reference/catalog payloads, SQLite databases, and historical evidence
archives are intentionally not stored in Git. Their frozen identities remain checksum-bound by
the Core Freeze manifest.

Biology-layer interpretation, clean-install validation, cross-hardware release readiness, and
the public `v0.5.0` release remain later work.

## Repository status

This repository is **private and intended for laboratory-internal sharing at this stage**.
Do not describe the current repository state as the public RNA-TR-Scout v0.5.0 release.
