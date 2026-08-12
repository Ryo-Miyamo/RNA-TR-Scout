# RNA-TR-Scout Stage 15L v0.1.1 final — Pro audit

## Decision

**PASS_WITH_SCOPE — Stage 15L is complete.**

The generic full-input 12-shard 100k path passed exact scientific-output parity,
intentional-stop/selective-resume, portable result-manifest validation, PRE_BIOLOGY
interface smoke, atomic publication, and a zero-scientific-command second-resume no-op.

This accepts the generic sharded Core behavior as an active-path promotion candidate. It
does not itself mutate SSOT/current_pipeline, close Core Freeze, or close clean-install and
cross-hardware release gates.

## Uploaded final evidence

- Bundle SHA-256:
  `9ea1bb5556f109e1996fc81b081bff4ca7e151a57a2dd114694e874b617eeccd`
- Sidecar parity: PASS
- Tar members: 18
- Artifact-manifest rows: 13
- Manifest coverage/path/size/SHA mismatches: 0
- Unsafe paths, links, special files, or duplicate members: 0

## Exact 100k scientific parity

The final five plain tables exactly match the frozen reference:

- `general_repeat_calls.tsv`: 388,571 rows,
  SHA-256 `21edb2595f24849282cf2d67e9f0a257d756c8d9c82d9619b297fd83d769bf85`
- `read_evidence.tsv`: 388,571 rows,
  SHA-256 `4c66159929b780ff6b637f1842b5fa994b4322e5deae17fef3a24a313d4190f9`
- `repeat_events.tsv`: 160,297 rows,
  SHA-256 `3996edc2491e2ca3f47be5ec5c931f8ac9b2e66213d93e864253a11a4a1bc51e`
- `repeat_segments.tsv`: 161,265 rows,
  SHA-256 `ac8ac589591a9629100b5edc2613bc77b21346eb389d06b57254e7afecb8859e`
- `repeat_interruptions.tsv`: 848 rows,
  SHA-256 `d835cc0786c5972e6fe114d1524d72948010d29dc6ba1ad18e1918b07c7f5556`

The ten plain/gzip scientific artifact entries agree across the package manifest, portable
Core result manifest, and first-resume output-fingerprint ledger.

## Sharding, validation, and interface

- Shards: 12, exactly `shard_000`–`shard_011`
- Total primary reads: 100,000
- Total alignment records: 184,820
- Unit statuses: 12/12 PASS
- Distinct validated unit manifests: 12
- Global package validator: PASS
- Atomic publication: PASS
- Portable manifest absolute paths: none
- Manifest resource IDs/local binding keys: 23/23 exact correspondence
- PRE_BIOLOGY manifest smoke: PASS
- Stable `read_id` to BAM alignment resolution: PASS
- Stable target/locus identity to pinned annotation resolution: PASS

## Restart/no-op result

The intentional stop completed exactly three validated shards. First resume reused those
three and ran the remaining nine. The final harness state records 3 attempts before resume
and 12 after resume.

The second resume reports:

- scientific commands: 0
- new unit attempts: 0
- partition rerun: 0
- global merge/publication: 0
- output fingerprints unchanged: PASS

The 17 published files, totaling 927,895,272 bytes, retained exactly the first-resume
size, mtime, inode, device, and SHA-256 fingerprints. All shared scientific/QC/manifest
files in the first-resume and final evidence bundles are byte-identical. The only intended
harness-state change is:

`FIRST_RESUME_COMPLETE_AWAITING_NOOP` → `COMPLETE`.

## Performance instrumentation

- Unit elapsed range: 26.26–29.56 seconds
- Global merge plus deterministic gzip: 3.245 seconds
- Global package validator: 15.529 seconds

## Preserved project state

- SSOT modified: false
- current pipeline modified: false
- frozen schema modified: false

## Remaining promotion-boundary issue

Stage 15L proves controlled stop between completed shards, selective resume, publication,
and second-resume no-op. It does not directly exercise the narrow crash interval after
atomic output publication but before external `final.json` state persistence.

Before mutating the active path, the production candidate must demonstrate that the
published package can reconstruct the missing final state without rerunning scientific
units or merge/publication. This is the next Stage 15M read-only promotion preflight.
