# RNA-TR-Scout Stage 15C contract-driven full runner build v0.1.1

This build changes the development control plane, not the scientific core. Builder v0.1.1 is an orchestration/schema-binding amendment: v0.1.0 incorrectly requested top-level QC field names from the resource-model TSV and stopped before runner generation. v0.1.1 binds each file to its own schema and cross-checks the corresponding values across files. The validated 144-shard scientific/execution contract is unchanged.

The sole execution architecture source is the validated Stage 15C 144-shard contract (`aa933d41e75c365a58ba414a85f0415fb100bf29e9ab8974300520eb01738eec`). The generated runner cannot choose a different shard count or full analysis run ID. A post-11b candidate-load hard gate of 164,204 rows/shard is mandatory and is statically required to execute before candidate extraction and before caller/materializer.

The prior v0.1.0 runner (`ec0ab9f75c539e5df280fff9078a3a64f29cd93b3c1b489b085664071688d9c9`) is retained as failure provenance and is rejected by the new auditor. It is used only as an implementation template from which contract-controlled substitutions are made.

The v0.1.1 generated runner is intentionally execution-locked. Only `--preflight` is authorized. Full execution requires a new version after Pro review of the v0.1.1 preflight bundle. Active pipeline, SSOT, core schema, caller, materializer, accepted 500k results, and full BAM/FASTQ are not modified by this build.
