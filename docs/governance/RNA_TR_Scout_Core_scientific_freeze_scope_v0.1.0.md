# RNA-TR-Scout Core scientific-freeze scope v0.1.0

## Freeze the observable Core contract

The long-term Core Freeze contract consists of:

- repeat-measurement scientific semantics, including interruption, censoring, lower-bound,
  missingness, and context-limited distinctions;
- supported scientific input/profile declarations and the canonical sequence/alignment
  resolution interface;
- five-table output contract and evidence schema v0.4.2;
- portable Core result-manifest/API contract;
- stable public identities and joins:
  `read_id`, molecule identity where defined, `target_source`, `target_region_id`,
  `locus_id`, `evidence_id`, event/call/interruption/caller-record identities;
- determinism, restart/resume, corruption rejection, validation, and atomic-publication
  guarantees;
- known limitations and evidence scope;
- scientific output protected by the canonical golden suite.

## Record, but do not permanently freeze, current implementation details

SSOT records the exact current implementation for reproducibility. Unless a documented
scientific reason requires otherwise, the following are replaceable:

- internal Stage names/numbers;
- shard and worker counts;
- partitioning/parallelization mechanics between versions;
- internal processing order;
- intermediate-file names, layout, paths, and existence;
- file handoff versus streaming;
- stage fusion;
- intermediate-I/O reduction;
- hardware-aware concurrency.

A replacement is acceptable when the applicable golden parity, restart, validator,
publication, and performance gates pass.

## Platform-independent boundary and current profile

### Platform-independent Core

Freeze stable identities, repeat semantics, output/API/schema, logical-resource resolution,
and guarantees.

### Current validated ONT-cDNA profile

Record as a versioned scientific baseline:

- mapping-complete BAM;
- corresponding read-coherent source FASTQ;
- current minimap2 splice mapping baseline upstream of Core timing;
- current orientation, alignment/CIGAR, sequence, and quality interpretation;
- current evidence limitations.

These physical/profile details are not universal requirements for every future platform.

### Future platform adapters/calibration

ONT direct RNA, PacBio Iso-Seq, PacBio Kinnex, and other profiles may provide different
physical resources and metadata. Their adapters/calibration layers should normalize:

- sequence/alignment access;
- read/molecule identity and provenance;
- orientation/strand;
- alignment encoding;
- completeness and observability;
- platform error and quality characteristics.

Full adapter implementation and validation are post-Freeze.

## Performance evidence

- Stage15C: empirical 5.31M BAM-to-final, 60.041256352 min,
  `PASS_WITH_DOCUMENTED_TOLERANCE`.
- Stage15J/L/M: generic unit/sharded scientific parity and restart/publication evidence.
- Do not claim that the generic orchestrator itself has a direct empirical 5.31M runtime
  measurement unless that run is later performed.

The 30-minute objective, stage fusion, streaming, I/O reduction, concurrency changes, and
mapping acceleration remain Performance-lane work.
