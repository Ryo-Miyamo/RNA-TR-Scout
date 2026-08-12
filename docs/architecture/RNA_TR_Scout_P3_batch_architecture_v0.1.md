# RNA-TR-Scout P3 batch architecture v0.1

作成日: 2026-08-04  
対象: `P3_SOFTCLIP_SIMPLE_PERIODIC_READY = 38,424` candidates  
Production scientific core: RNA-TR-Scout `0.3.2`  
Pilot run: `ENCSR307SHM_pilot100k_mm2splice_v1`

## 1. 設計判断

既存の23件P3 end-to-end regressionを**科学的判定coreの不変checkpoint**とし、batch層はその外側に追加する。batch層は `run_p3_pipeline()` の意味論を変更せず、候補入力、並列実行、checkpoint、retry、集約、監査を担当する。

最初のproduction-compatible engineは、現在凍結済みの **one-query / one-reference isolated minimap2 subprocess** とする。all-query/all-reference combined FASTAはpair isolationを壊しうるため、production callerには使用しない。mappy/in-process方式は、100件と凍結23件でfield-level parityが成立した場合のみ、後続のexperimental engineとして評価する。

## 2. 三層構造

### Layer A: immutable plan

- full simple-ready inventoryを検証する。
- `projection_id`をcandidate primary keyとする。
- seed固定のnested stratified orderを一度だけ作る。
- first 100をbenchmark-100、first 1,000をbenchmark-1,000とする。
- benchmark-100はbenchmark-1,000に必ず包含される。
- source file path、size、SHA-256、package/minimap2 version、selection ruleをrun manifestへ記録する。

### Layer B: immutable prepared input bundles

candidate geometry preparationとalignment executionを分離する。benchmark-100は10件/chunkで10 chunksとする。各chunkは自己完結した入力を持つ。

```text
benchmark100/
  p3_benchmark100.selection.tsv.gz
  p3_benchmark100.prepared_candidates.tsv.gz
  p3_benchmark100.chunk_manifest.tsv
  chunks/
    chunk-00000/
      input/
        candidates.tsv.gz
        queries.fasta.gz
        references.fasta.gz
        raw_reads.fasta.gz
        input_manifest.tsv
```

各candidateについて、raw read、oriented query、candidate reference、source inventory rowのSHA-256を保持する。candidate referenceはmapped-block boundaryからtarget entryへ向かう向きに固定し、GENOMIC_LEFTではreverse-complementする。

### Layer C: restartable executions

prepared inputは変更せず、実行条件ごとに別execution directoryを作る。

```text
executions/
  isolated_subprocess_w1/
  isolated_subprocess_w2/
  isolated_subprocess_w4/
  isolated_subprocess_w8/
```

各chunkはattempt単位でimmutableに保存する。

```text
chunk-00000/
  attempts/
    attempt-0001/
      result.tsv.gz
      failures.tsv.gz
      metrics.tsv
      status.json
  PASS.json
```

`PASS.json`は、input bundle hash、output hash、row count、unique projection countが一致したattemptだけを指す。resume時はvalid PASS chunkをskipし、それ以外のみ新attemptとして実行する。shared mutable TSVには追記しない。

## 3. Nested stratified sampling

primary strata:

- `target_facing_genomic_side`: GENOMIC_LEFT / GENOMIC_RIGHT
- motif length: 1, 2, 3, 4–6, 7–20, 21+
- diagnostic motif signal: zero / positive

secondary strata:

- assignment rank: 1 / 2 / 3+
- MAPQ: <20 / 20–59 / 60
- softclip: 12–29 / 30–59 / 60–119 / 120–249 / 250+
- bridge distance: 0 / 1–10 / 11–30 / 31–100 / 101–500 / 501+
- read candidate multiplicity: 1 / 2–5 / 6+

各stratum内部をseedと`projection_id`のSHA-256で決定論的に並べ、secondary strata、次にprimary strataをweighted-fairにinterleaveする。この単一orderのprefixを用いるため、100→1,000→38,424の順で候補集合がnestedになる。

diagnostic repeat-like windowは**samplingの除外条件にしない**。zero群も含め、実運用に近い候補分布をbenchmarkする。

## 4. Chunk state machine

```text
PLANNED
  -> RUNNING(attempt N)
      -> PASS       : row/hash/guardrail validationを通過
      -> RETRYABLE  : subprocess/non-structural worker failure
      -> FAILED     : input corruption、schema violation、retry上限到達
```

- outputはtemporary siblingへ書き、`fsync`後に`os.replace()`する。
- candidate exceptionはcandidate terminal rowとして保持し、chunk全体から消さない。
- chunk PASS条件は、input candidate数とterminal result数が一致し、missing/duplicate projectionが0であること。
- orchestratorはrun-level lockを取得し、同一executionへの二重書きを防ぐ。
- retryは元のfailed attemptを上書きせず、新attemptを作る。

## 5. Scientific output invariants

batch executionの並列度や再開は、以下を変えてはいけない。

- normalized query/reference bridgeにはPAF strand `+`を要求する。
- reverse-onlyは`ORIENTATION_INCONSISTENT_BRIDGE`。
- target-entry CIGAR projectionなしにrepeat sizingしない。
- motif length 1はhomopolymer reviewで、standard P3 evidenceを出さない。
- one-flank P3からexact allele lengthを出さない。
- P3単独でexpansion/pathogenicityを出さない。

candidateごとにproduction result全体をcanonical JSON化し、`scientific_result_sha256`を作る。worker数を変えても同一candidateのscientific hashは一致しなければならない。runtime、attempt、worker IDなどの実行metadataはhash対象外とする。

## 6. Benchmark-100

### Preflight gate

- package version `0.3.2`
- installed unit tests PASS
- frozen 23-case finalization PASS
- frozen 23-case 713 comparisons mismatch 0

### Concurrency matrix

同じ100候補を以下で実行する。

- workers=1: serial reference
- workers=2
- workers=4
- workers=8

各minimap2 pairは`-t1`を維持するため、最大同時minimap2数はworker数と一致する。まず既存engineのparallel scalingを測り、科学的同一性を確認する。

### Resume test

workers=4 executionを、最初の3 chunks完了後に意図的にpartial stopする。その後`--resume`で残りのみ実行し、最初の3 chunksのPASS pointer、result hash、attempt directoryが変わらないことを検証する。

### Metrics

- run/chunk/candidate wall time
- candidates/sec
- candidate latency median, p90, p95, p99, max
- minimap2 spawn count / non-zero exit count
- execution errors / retries
- bridge status / selected strand / target-entry projection status
- primary status / failure code / sizing status / evidence class
- motif length、target side、softclip、bridge distance別集計
- standard P3 evidence emitted
- homopolymer review
- exact estimate / expansion guardrail failures

## 7. 「偽陽性」の扱い

このpilot subsetにはtruth labelがないため、100件・1,000件だけから統計学的なfalse-positive rateは算出しない。代わりに以下を区別する。

1. **guardrail leakage**: orientation不整合、homopolymer、target-entry未投影などから誤ってstandard evidenceが出た割合。これは0を要求する。
2. **apparent standard-evidence rate**: production rulesを通過した候補率。truth-based false-positive rateとは呼ばない。
3. **manual audit**: benchmark-100でstandard evidenceが出た全件、benchmark-1,000では全件または事前規定sampleをraw read/CIGAR/reference geometryで監査する。

## 8. Benchmark-100 acceptance gate

- 100 input candidates / 100 terminal results
- missing projection 0、duplicate projection 0
- unresolved execution failure 0
- frozen 23 regression unchanged
- workers 1/2/4/8間でscientific field mismatch 0
- resume test PASS、既完了chunkのhash変更0
- exact allele-length guardrail failure 0
- expansion guardrail failure 0
- homopolymerからstandard evidence 0
- standard evidence候補は全件manual-review tableへ抽出

速度が最速でも、科学的hash不一致やresume不成立がある方式は採用しない。

## 9. Benchmark-1,000 gate

benchmark-100 PASS後にのみ、既に固定したfirst 1,000をprepareする。chunk sizeは25を初期値とし、benchmark-100で選定したworker数を使用する。

追加条件:

- shared first 100のscientific hashがbenchmark-100と完全一致
- 1,000 input / 1,000 terminal results
- missing/duplicate 0
- retry後のunresolved failure 0
- peak memoryとtemporary storageが38,424へ線形外挿可能
- throughputが100件時と著しく乖離する場合は原因を監査
- standard evidence候補の全件集約とstratified manual audit

## 10. Full 38,424へ進む条件

benchmark-1,000がPASSし、worker数、chunk size、retry policy、output schemaをfreezeした後に限る。full runは同じnested order、同じprepared input contract、同じscientific coreを使い、Step 11はfull aggregationとQCが終わるまで`in_progress`を維持する。
