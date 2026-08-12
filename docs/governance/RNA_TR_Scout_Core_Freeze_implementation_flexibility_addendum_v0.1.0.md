# RNA-TR-Scout Core Freeze implementation-flexibility addendum v0.1.0

## Purpose

Core Freeze preserves RNA-TR-Scout scientific behavior and reproducibility. It must not
unnecessarily freeze the current internal execution architecture or make later performance
work prohibitively expensive.

## Long-term frozen contract

The Core Freeze Packet and canonical golden suite should freeze, in principle:

- scientific semantics and explicit missingness/censoring rules;
- scientific input contract;
- output/API contract and frozen evidence schema;
- stable `read_id`, locus/target identity, and other public join identities;
- determinism, restart/resume, validation, and atomic-publication guarantees;
- observable scientific output protected by golden regression;
- documented known limitations and the permitted biology-layer interface.

## Versioned implementation state, not immutable Core contract

SSOT may record the exact current implementation for reproducibility, but the following
should not become permanent requirements unless an explicit scientific reason is documented:

- internal Stage names or numbers;
- intermediate-file existence, names, or fixed paths;
- shard count;
- worker count;
- partitioning and concurrency mechanics across software versions;
- internal stage ordering;
- file-based handoff versus streaming;
- current intermediate I/O layout.

A change to these details is acceptable when it preserves the frozen public contract and
passes the applicable golden, restart, validator, and performance gates.

## Post-Freeze development lanes

### Core-contract lane

Use the strict preflight/audit/registration/re-audit process for changes that alter
scientific semantics, schema/API, stable identities, determinism/restart guarantees,
validation behavior, or frozen scientific output.

### Performance lane

Use a lighter proportional workflow for stage fusion, streaming, intermediate-I/O
reduction, hardware-aware concurrency, internal partitioning changes, and similar
optimizations. Require golden scientific parity, restart/validator checks relevant to the
change, and targeted performance benchmarks.

FASTQ-to-BAM mapping remains a separate scientific baseline. A mapping optimization may be
adopted only after TR-locus recall, locus assignment, and final-output parity pass.

### Biology-sidecar lane

Biology sidecars may evolve independently when they consume the frozen manifest/interface
without rewriting Core source-of-truth tables. Use interface tests, sidecar-specific
validators, and reverse-traceability checks rather than the full Core promotion process for
every sidecar change.

## Current sequence

Do not interrupt the current generic active-path promotion to begin new optimization or
biology work. Complete promotion, post-promotion architecture review, G32–G34, and Core
Freeze first.
