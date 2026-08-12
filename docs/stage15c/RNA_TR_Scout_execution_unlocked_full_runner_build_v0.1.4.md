# RNA-TR-Scout Stage 15C execution-unlocked full runner build v0.1.4

This build authorizes only the clean empirical `ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1` BAM-to-final run. It is derived from the exact v0.1.3 locked runner (`70d82b1f8cee9c7941a796c2f059ccf88365ea0df0981f10973f18a930c3ea65`) and requires the exact locked preflight bundle (`6534d95e9b8e2907103b6d79957a9e29ced7a4b09d355a0b9af93f85bb21ff8c`).

The validated execution architecture is unchanged: 144 deterministic read-coherent shards, active concurrency 12, caller workers 2 per active shard, validator workers 3, external sort 512M, and a mandatory post-11b hard maximum of 164,204 candidate rows per shard. The gate must pass before candidate extraction and before caller/materializer execution.

The builder verifies that every scientific-processing function inherited from v0.1.3 remains byte-identical. Only the versioned output/provenance paths, execution authorization, unlock verification, final-preflight authorization fields, and success/failure evidence bundles are changed.

The generated v0.1.4 runner is execution-authorized, but execution is still impossible until the exact same v0.1.4 bytes complete `--preflight`. The execute path then requires the exact formal run ID and re-verifies the v0.1.4 preflight artifact manifest, runner SHA-256, unlock contract, locked v0.1.3 evidence, source guards, input binding, memory/storage model, and large input hashes before creating a full-run result root.

Execution-unlock contract SHA-256: `a3d9474208f3519c19d3b48e948e0fc4c9b7fa14b0764446d22a67c37c4de014`
Generated runner SHA-256: `d4a91324d9549991c00c24f2aa610e02bd33d7525271ce3139093d30c17ea3cf`
