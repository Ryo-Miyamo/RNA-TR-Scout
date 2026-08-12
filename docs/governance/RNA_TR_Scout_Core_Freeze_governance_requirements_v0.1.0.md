# RNA-TR-Scout Core Freeze governance requirements v0.1.0

Status: **REQUIRED BEFORE CORE FREEZE**

## 1. Role separation

- **Architecture consistency audit** checks cross-domain consistency at defined checkpoints.
- **SSOT** records the current project state.
- **Core Freeze Packet** preserves the concise, authoritative essence of the frozen Core.
- **Golden regression suite** mechanically proves that future changes preserve the frozen scientific-output contract.

## 2. Authoritative-original rule

The PRE_RELEASE_CANDIDATE Architecture audit and Core Freeze must reconstruct active state from the exact original artifacts that govern it: code, SSOT database and exports, schema, contracts, validators, runners, manifests, checksums, and prior formal evidence. Conversation summaries and remembered historical state are not authoritative evidence.

When an original is missing, ambiguous, too large for the collection bundle, or represented only by an inventory/hash, the audit must mark it as unresolved and request the original before finalizing the affected conclusion. No Freeze Packet, golden regression contract, active-path decision, or canonical-docs decision may be finalized by inference from memory.

## 3. Core Freeze Packet

Create a versioned and checksummed formal artifact containing at least:

- active production entry points and path bindings;
- frozen schemas, table/API contracts, join keys such as `read_id`, identifiers, and missingness semantics;
- scientific semantics and exact-versus-logical comparison rules;
- performance, restart/resume, checkpoint, validator, and atomic-publication contracts;
- known limitations and explicitly unproven scopes;
- the supported interface through which biology/interpretation layers may connect without mutating Core semantics;
- source-artifact manifest, versions, SHA-256 bindings, and a reverse-traceability map.

The packet is a compressed freeze-time contract, not a copy of the complete development history.

## 4. Golden regression suite

Create a versioned suite with fixed representative inputs and expected outputs. It must include:

- input manifests and checksums;
- expected raw and/or logical outputs according to an explicit comparison policy;
- schema and validator expectations, including accepted negative fixtures;
- stable IDs and join-key checks;
- commands, environment/version bindings, expected exit states, and machine-readable PASS/FAIL output;
- coverage of lossless read-level repeat evidence, interruptions/purity/LPS/censoring semantics, materialization, restart/no-op behavior, and package publication where applicable.

Future biology additions and 30-minute performance optimization must run this suite before the Core contract is considered preserved.

## 5. Canonical documentation layout

At Core Freeze, promote project-wide authoritative documents to durable canonical locations such as `docs/architecture/`, `docs/governance/`, `docs/contracts/`, `docs/core_freeze/`, and `tests/golden/` or an audited equivalent chosen after inspecting the actual repository. Stage-local copies, including the original `docs/stage15a/` architecture documents, remain as historical records or pointers to the canonical source. There must be one unambiguous authoritative location per contract.

The final layout must be chosen only after the PRE-RC audit has reread the actual repository and formal artifacts.

## 6. Downloads cleanup

Do not delete or relocate active-gate evidence from `~/Downloads` until authoritative artifacts and checksums are classified. After canonicalization, produce a machine-readable inventory separating:

1. authoritative artifacts to preserve or move;
2. active-gate inputs that must remain temporarily;
3. superseded or duplicate files safe to delete;
4. unresolved files requiring review.

Deletion must be explicit and occur only after the preserved destinations and checksums are verified.