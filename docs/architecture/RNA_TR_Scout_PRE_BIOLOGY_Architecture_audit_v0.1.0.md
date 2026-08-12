# RNA-TR-Scout formal PRE_BIOLOGY Architecture audit v0.1.0

## Overall decision

**PASS_WITH_REQUIRED_G32_G34_BUILD**

The post-promotion active Core is internally consistent. No active-code, SSOT, schema,
resource-provenance, restart, validator, or portable-interface conflict requires reversal
of the Stage 15N promotion.

G24 remains **OPEN** until the Core Freeze Packet, canonical executable golden suite, and
canonical project-wide documentation structure are installed and a final exact-original
post-build audit passes. Full biology implementation remains post-Freeze.

## Audited exact-original basis

- Stage 15O bundle SHA-256:
  `b7a82bdd421791fa40cbe270ec467f3d6d728edee6bf32770173c25abc6c7061`
- tar members: 467
- artifact-manifest rows: 378
- manifest path/size/SHA mismatches: 0
- unsafe or duplicate tar members: 0
- formal Stage15 bundles verified: 9
- active resource originals checksum-bound: 25
- post-promotion SSOT validation: PASS
- SQLite integrity: `ok`
- foreign-key errors: 0
- current-pipeline rows: 1
- active stage:
  `CORE_GENERIC_SHARDED_BAM_FASTQ_TO_FINAL`
- ACTIVE implementations: 1
- DISCOVERED implementations: 0

The audit used the collected active code, schema, resource manifest, current SSOT exports,
formal contracts, accepted result manifest, validation/config/docs trees, and formal
evidence bundles. Conversation memory was not treated as authoritative evidence.

## Active Core consistency

The active public entry, generic sharded orchestrator, generic unit, PRE_BIOLOGY smoke,
schema v0.4.2 validators, caller/materializer components, and pinned catalogs all match the
checksums in the active resource manifest.

The public entry and public orchestrator contain no fixed developer-machine path, ENCODE
accession, T9 binding, or Stage-specific run binding.

The active scientific profile accepts:

- a mapping-complete BAM; and
- the corresponding read-coherent source FASTQ.

It publishes the five schema-v0.4.2 scientific tables plus a portable Core result manifest.
Package validation occurs before atomic publication.

## PRE_BIOLOGY interface

The accepted Stage15J/L evidence proves a read-only interface smoke:

- portable manifest -> stable `read_id` -> primary BAM alignment;
- portable manifest -> `target_source + target_region_id + locus_id`
  -> one pinned target/locus annotation;
- no Stage number, dataset name, or developer-machine absolute path is required by the
  portable downstream interface.

This is sufficient for the pre-Freeze **interface** requirement. It is not full biology.
Transcript/isoform, haplotype, observability calibration, molecule-independence, ranking,
and researcher-dossier sidecars remain post-Freeze work.

## Cross-platform boundary

The current implementation is a validated **ONT cDNA profile**, not a fully platform-neutral
physical-input implementation.

Platform-independent Freeze contract:

- stable read/molecule and locus/target identities;
- repeat-measurement scientific semantics;
- canonical sequence/alignment/provenance resolution interface;
- output schema, portable result manifest, and join contract;
- determinism, restart/resume, validation, and atomic-publication guarantees.

Current ONT-cDNA profile or future adapter/calibration responsibility, not universal Core
requirements:

- physical BAM+FASTQ representation;
- a specific minimap2 command;
- ONT-cDNA read-orientation behavior;
- platform-specific CIGAR/hard-clip assumptions;
- platform-specific completeness, error, poly(A), and observability calibration.

The exact scan found 1,214 assumption hits, but zero fixed machine/dataset binding violations
in the public entry or orchestrator. The extension boundary therefore remains open for
future ONT direct RNA, PacBio Iso-Seq, and PacBio Kinnex adapters. Those adapters are not
required before Freeze.

## Determinism, restart, and validation

Accepted evidence includes:

- Stage15J generic real-read single-unit exact parity;
- Stage15L generic 12-shard 100k exact five-table parity;
- intentional stop, selective resume, and second-resume no-op;
- Stage15M recovery after atomic publication with missing external final state and zero
  scientific commands;
- Stage15E scoped release-scale reconstruction/restart evidence;
- validators and atomic publication.

The current SHA-based partition and deterministic merge mechanics are exact current
implementation/restart records. They are not immutable long-term requirements if a future
implementation preserves the frozen scientific output/API, restart and validation
guarantees, and passes golden parity.

## Performance evidence scope

The empirical 5,312,696-read BAM-to-final result of 60.041256352 minutes is Stage15C
full-scale evidence and remains `PASS_WITH_DOCUMENTED_TOLERANCE`. It is not relabeled as a
direct empirical 5.31M benchmark of the generic v0.1.2 orchestrator.

The 30-minute target and mapping acceleration remain post-Freeze Performance-lane work.
Current minimap2 splice mapping remains the scientific mapping baseline.

## Required work before G24/Core Freeze closure

1. **G32 — Core Freeze Packet**
   - concise human-readable scientific/public contract;
   - current ONT-cDNA profile distinguished from platform-independent Core;
   - exact versions, checksums, known limitations, evidence scope, and extension boundaries.

2. **G33 — canonical executable golden regression suite**
   - Tier 0 static contract checks;
   - Tier 1 synthetic/negative semantic fixtures;
   - Tier 2 fixed real-read `shard_088`;
   - Tier 3 fixed 100k sharded/restart fixture;
   - Tier 4 release-scale evidence verification;
   - quick/full modes and explicit exact/logical parity rules.

3. **G34 — project-wide canonical docs/artifact structure**
   - one authoritative location for architecture, governance, contracts, freeze, and golden
     assets;
   - Stage-local documents retained as history or pointers;
   - checksum-backed retention/move/delete plan for Downloads.

4. Run a final post-install exact-original Architecture audit.

## Correctly open, non-conflicting gates

G25–G30, G28, G31-B, G32–G34, biology sidecars, clean-install/public release, and
cross-hardware evidence remain open as documented. Their open status does not invalidate
the current internal scientific Core promotion.
