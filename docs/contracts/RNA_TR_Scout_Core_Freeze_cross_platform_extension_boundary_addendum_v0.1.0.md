# RNA-TR-Scout Core Freeze cross-platform extension-boundary addendum v0.1.0

## Purpose

The currently validated production profile is ONT cDNA. Core Freeze should preserve that
scientific baseline without turning its present physical input representation or
platform-specific assumptions into universal requirements for all future platforms.

Full ONT direct RNA, PacBio Iso-Seq, and PacBio Kinnex adapters are not required before
Freeze. Freeze must instead preserve an explicit extension boundary.

## Platform-independent Core contract

The long-term platform-independent Core contract should be centered on:

- stable `read_id` and, where appropriate, molecule identity;
- stable locus/target identity;
- scientific semantics of repeat measurement, interruptions, censoring and missingness;
- a stable interface through which Core can resolve canonical read sequence, alignment and
  provenance;
- final output schema, portable result manifest and join contract;
- determinism, restart/resume, validation and atomic-publication guarantees.

## Current ONT cDNA profile

The active ONT cDNA implementation currently uses a mapping-complete BAM plus the
corresponding read-coherent source FASTQ. Its current mapping baseline is minimap2 splice.
This is the validated ONT cDNA profile and current reproducible implementation state.

It must not be generalized into a permanent assertion that every future platform must
physically provide the same BAM+FASTQ pair or the same mapper command.

## Platform-specific adapter/calibration responsibilities

Future platform profiles may absorb platform-specific:

- physical input formats and metadata;
- basecalling/provenance, such as POD5/Dorado resources for ONT direct RNA;
- orientation and strand conventions;
- alignment encoding and CIGAR/platform assumptions;
- completeness, error and observability characteristics;
- platform-specific calibration and quality interpretation.

Conceptually:

ONT cDNA / ONT direct RNA / PacBio Iso-Seq / PacBio Kinnex
    -> platform-specific adapter and calibration
    -> canonical sequence/alignment/stable identity/locus interface
    -> platform-independent repeat-measurement Core

## Freeze-audit requirement

The final PRE_BIOLOGY/Core Freeze audit must reread exact active code, resource/result
manifests, schema and contracts and explicitly identify:

1. which assumptions belong only to the current ONT cDNA profile;
2. which semantics/interfaces are genuinely platform independent;
3. which platform-specific assumptions need a future adapter/calibration boundary;
4. whether any public identity or Core output contract is unnecessarily coupled to a
   physical input format, mapper, orientation convention, CIGAR convention, developer path
   or internal Stage path.

Any unresolved coupling should be recorded as a known limitation or a post-Freeze adapter
requirement, not hidden by assuming the design is already platform neutral.

## Current sequence

Do not interrupt active-path completion or Core Freeze preparation to implement new
cross-platform support. Preserve the extension boundary now; implement and validate
platform-specific adapters after Freeze.
