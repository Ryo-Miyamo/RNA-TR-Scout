# RNA-TR-Scout post-Freeze governance lanes v0.1.0

## 1. Core-contract lane — strict

Use the full preflight -> Pro audit -> versioned mutation/registration -> post-audit flow
when a change may alter:

- scientific semantics;
- schema/API or stable join identities;
- public input/output contract;
- determinism, restart, corruption rejection, validation, or publication guarantees;
- frozen scientific output;
- accepted evidence interpretation or known limitations.

Required gates include the canonical golden suite and any targeted truth/release-scale
evidence affected by the change.

## 2. Performance lane — proportionate

Use a lighter workflow for internal changes that leave the frozen public/scientific contract
unchanged, including:

- stage fusion and streaming;
- intermediate-I/O reduction;
- internal sharding/partitioning/concurrency changes;
- compiled kernels, GPU/CPU implementations, and hardware-aware scheduling;
- compression or cache changes;
- minimap2 or other mapping acceleration experiments.

Minimum controls:

- quick golden parity during iteration;
- full relevant golden/restart/validator suite before adoption;
- targeted benchmark and resource instrumentation;
- mapping changes additionally require TR-locus recall, locus assignment, and final-output
  parity.

Escalate to the Core-contract lane if scientific output, schema, stable identities, or
guarantees change.

## 3. Biology-sidecar lane — independent and traceable

Biology/interpretation sidecars may evolve without rewriting the frozen five Core tables.
Use:

- manifest/interface compatibility tests;
- sidecar-specific schemas and validators;
- reverse traceability to Core `read_id`/locus/evidence identities;
- sidecar-specific biological truth and ranking validation.

Escalate if the sidecar requires a Core schema/semantics change.

## 4. Platform-adapter/calibration lane — profile-specific

New ONT direct RNA, Iso-Seq, Kinnex, or other profiles may introduce new physical inputs,
orientation, completeness, observability, error, and metadata handling behind the canonical
Core boundary.

Use:

- profile-specific adapter tests;
- identity/sequence/alignment resolution tests;
- profile calibration and truth data;
- shared Core golden tests where applicable;
- final-output and locus-assignment comparisons to the established profile when scientifically
  meaningful.

A new adapter does not require rewriting the platform-independent Core contract unless it
reveals a genuine shared-semantics deficiency.

## 5. Documentation-only lane — lightweight

Editorial corrections, pointers, or historical indexing that do not change contract meaning
need checksum/version tracking and review, but not a full scientific re-execution.

## Escalation rule

When uncertain, classify by **observable contract impact**, not by code size. A large
internal refactor can remain Performance lane if golden and guarantees are unchanged; a
one-line semantic change belongs in the strict Core-contract lane.
