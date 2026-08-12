# RNA-TR-Scout Stage15T final installer hotfix Pro promotion audit v0.1.5

Date: 2026-08-12
Review mode: Pro
Decision: PASS_EXECUTION_AUTHORIZED

## Evidence reviewed

- Stage15T installer v0.1.1 SHA-256: `89169f20dbed2962fd7f1d7c34dd1a319d4a26298e2b64ac24667b65bb8dcbd4`
- v0.1.1 real execution outcome reported by the operator: automatic rollback PASS after a persistent-inventory rejection of an ephemeral golden-work symlink.
- Stage15T hotfix candidate v0.1.2 SHA-256: `d0b50e68852ea40b0eb7cacdc1a477ed0b0b4d7ffdd24a49a7fc2660360ffa9e`
- v0.1.2 real-project read-only audit log SHA-256: `a81d64125d35e9e12fd8b61b21b254dc17a37f1c8114863469cb50491565a474`
- corrected-installer preflight bundle SHA-256: `d2f843a60934d32c0defe98fbd4c6211a8ad3f2de42ce4aba18cc6c0fb682ffd`
- High-mode hotfix build note SHA-256: `e878990bd42a78ab2a926d5d4e12b477e3dda2562a7791885acb7942bfa28762`

The v0.1.2 real-project audit passed all prestate, historical-manifest, SSOT overlay, full SSOT rebuild, owner-approved-payload, scientific-Core/schema, and active-pipeline guards with `project_mutation=false`.

## Exact hotfix adjudication

The v0.1.1 failure was caused by applying persistent no-symlink inventory rules to the isolated full-evidence golden scratch tree. The v0.1.2 patch is technically correct and narrowly scoped:

1. The Stage15T golden-work parent remains in `NEW_PROJECT_TARGETS`, so automatic and explicit rollback continue to remove it.
2. The golden-work parent is excluded from `POSTSTATE_GUARD_TARGETS`, so scratch symlinks are not mistaken for persistent Freeze artifacts.
3. A validated full-evidence golden PASS is required before cleanup.
4. The complete Stage15T golden-work parent is then removed and absence is verified before registration record creation, final manifest generation, final Tier0, output packaging, and poststate-guard capture.
5. Persistent payloads, SSOT state, Freeze evidence, final-manifest inputs, QC outputs, rollback backups, and output bundles retain strict no-symlink handling.
6. The self-test contains a symlink-bearing golden scratch tree and verifies safe cleanup and target-set separation.

No owner-approved Freeze Packet text, Core Technical Completion contract, release-gate content, scientific Core code, evidence schema, active pipeline, SSOT intended final state, golden scientific expectation, or registration scope is changed by this hotfix.

## Promotion to executable v0.1.3

The executable v0.1.3 is promoted from the exact v0.1.2 candidate. Relative to v0.1.2, the only intended changes are:

- installer version and exact required filename;
- replacement of the High-mode build note with this Pro promotion audit;
- provenance fields for the promoted candidate and real-project audit log;
- restoration of the guarded execute branch, requiring the exact confirmation token `LOCAL_CORE_FREEZE_V0.1.0`.

The execution path, rollback paths, persistent targets, ephemeral-target separation, owner-approved payload, SSOT overlay/rebuild logic, golden runner, final manifest, final Tier0, and output contract otherwise remain identical to the audited v0.1.2 candidate.

## Authorization

`rnatr_stage15t_final_core_freeze_installer_v0.1.3` is authorized for guarded execution on the audited project prestate. A failed execution must be handled by the installer's automatic rollback; the operator must not manually rerun or roll back before reviewing the execution log.
