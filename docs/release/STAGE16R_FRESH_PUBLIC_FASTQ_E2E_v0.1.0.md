# Stage16R fresh public FASTQ-to-final validation v0.1.0

Date: 2026-08-15

## Decision

**PASS_WITH_SCOPE — FRESH_MACHINE_EQUIVALENT_PUBLIC_FASTQ_TO_FINAL**

Stage16R validated the public FASTQ-to-final workflow from a fresh private-GitHub clone and a freshly created isolated environment using the public `rnatr-scout run` command. The scientific Core was not modified.

## Source identity

- source HEAD: `2191352170afe284c88cccd92c192efda2465b09`
- remote main: `2191352170afe284c88cccd92c192efda2465b09`
- fresh-clone HEAD: `2191352170afe284c88cccd92c192efda2465b09`
- fresh-clone source: private GitHub origin
- immutable Local Core Freeze root: `4b1981db955a8aa92a2a01e19bbb1cfc2aa0ebfb`
- Freeze tag object: `f14a2aa3e444264dff879a3ac0a1755e9b65917f`

## Authoritative original artifacts

Recovered original files:

- `rnatr_stage16r_fresh_public_fastq_e2e_v0.1.0.json`
  - SHA-256: `4445143bb1f138b39e240a9ed85c8bc0f1b31ff632db9aad781b9a44f60829ee`
- `rnatr_stage16r_fresh_public_fastq_e2e_v0.1.0.txt`
  - SHA-256: `368f68846d76e79e83bfa6b3c143f056a2630b2f1654db1f15638af02e650993`
- `rnatr_stage16r_fresh_public_fastq_e2e_v010.py`
  - SHA-256: `00c33aca303692e1c17b46906898415cf273d21bc263dc3b78f0151b44a18752`
- the runner SHA sidecar independently records the same runner SHA-256.

Stage16V copies these originals unchanged into the canonical SSOT checkpoint area and binds the Stage16R SSOT row to the durable JSON copy.

## Validated workflow

The authoritative Stage16R result records:

- fresh environment: `PASS_CREATED`
- standard resources: `PASS_STANDARD_RESOURCES_READY`
- public command: `rnatr-scout run`
- public input mode: `FASTQ_AUTO_MAPPING`
- exact Tier3 FASTQ identity: `PASS_EXACT`
- mapping: `PASS`
- mapping artifacts present: `PASS_3_OF_3`
- final exact plain-table parity: `PASS_5_OF_5`
- public resume: `PASS_SECOND_RESUME_NOOP`
- mapping was not rerun on resume
- mapping artifacts were unchanged on resume
- post-resume final parity: `PASS_5_OF_5`
- post-E2E setup `--verify-only`: `PASS`
- fresh clone remained Git-clean after setup, E2E execution and resume
- source Git was not mutated
- frozen Core was not modified.

## Exact final scientific tables

| file | rows | SHA-256 |
|---|---:|---|
| `read_evidence.tsv` | 388571 | `4c66159929b780ff6b637f1842b5fa994b4322e5deae17fef3a24a313d4190f9` |
| `general_repeat_calls.tsv` | 388571 | `21edb2595f24849282cf2d67e9f0a257d756c8d9c82d9619b297fd83d769bf85` |
| `repeat_events.tsv` | 160297 | `3996edc2491e2ca3f47be5ec5c931f8ac9b2e66213d93e864253a11a4a1bc51e` |
| `repeat_segments.tsv` | 161265 | `ac8ac589591a9629100b5edc2613bc77b21346eb389d06b57254e7afecb8859e` |
| `repeat_interruptions.tsv` | 848 | `d835cc0786c5972e6fe114d1524d72948010d29dc6ba1ad18e1918b07c7f5556` |

## Timing recorded by the validation

- clone: approximately 1.125 s
- setup: approximately 336.812 s
- public FASTQ-to-final: approximately 289.007 s
- second resume: approximately 38.107 s
- total validation: approximately 685.275 s

These timings describe the Stage16R validation fixture and are not a full-scale performance benchmark.

## Scope boundary

Stage16R is deliberately classified as **fresh-machine-equivalent**, not as the final full-network public-RC installation test.

The validated resource sources were:

- reference: `LOCAL_EXACT_OFFICIAL_GENCODE_CACHE`
- catalog: `LOCAL_EXACT_STAGE16L_RELEASE_BUNDLE`

The result explicitly records:

- `large_reference_network_download = false`
- `full_large_network_download_deferred_to_rc = true`

Therefore Stage16R closes the fresh-clone/fresh-environment/public-command FASTQ-to-final validation for the exact tested resources, but it does **not** close the remaining public-RC gate for downloading all intended large resources from their final public network locations.

## Relationship to Stage16S and later release engineering

Stage16R established the public FASTQ-to-final path on the source revision used for the subsequent portability work. Stage16S then established scoped second-machine exact scientific parity for the tested Tier2 input.

The remaining release-engineering work continues to include final public catalog hosting, full-network fresh installation, any still-required operational resource benchmarking, and the single Pro-level cross-cut audit immediately before public RC.
