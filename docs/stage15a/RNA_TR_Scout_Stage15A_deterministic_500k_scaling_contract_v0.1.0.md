# RNA-TR-Scout Stage 15A Deterministic 500k Scaling Contract v0.1.0

作成日: 2026-08-09  
状態: `READY_FOR_ISOLATED_EXECUTION`  
前提: deterministic 250k v0.1.2 PASS、post-250k Architecture consistency audit v0.1.1 REVIEW / blocking conflicts 0、SSOT registration PASS

## 1. 目的

250kで60分線形外挿が59.858798分と極小marginであったため、full 5.31Mへ進む前にdeterministic 500kでscaling、determinism、formal run-ID contract、corrected checkpoint comparisonを検証する。

## 2. 決定論的500k入力

```text
validated deterministic 250k subset 全件
+ full 5.31M FASTQから固定SHA-256 ruleで選ぶ追加250k
= nested deterministic 500k FASTQ
```

外部run ID:

```text
ENCSR307SHM_stage15a500k_seed20260809_mm2splice_v1
```

100k compatibility aliasは使用しない。11b、11d3、motif jobs、caller、materializer、final packageまで同じformal run IDを伝播する。

500k FASTQは250kと同じminimap2 splice contractでmappingする。mapping時間は別建てで記録し、BAM-to-final timerには含めない。

## 3. BAM-to-final replicate

同一500k BAMとassociated raw-read FASTQから、独立した2 replicateを実行する。

```text
replicate A  PYTHONHASHSEED=0
replicate B  PYTHONHASHSEED=20260808
```

各replicate:

```text
formal-run-ID 500k BAM + raw FASTQ
→ 12 read-coherent shards
→ 11b target assignment
→ candidate FASTQ extraction
→ 11d3 raw-read projection
→ shared-catalog fast motif-job generation
→ native general caller v0.4.1
→ materializer with schema v0.4.2 semantics
→ 5-table merge / deterministic gzip
→ frozen validators
→ atomic publication
```

candidate FASTQ extractionはBAM-to-final timerに含む。

## 4. Corrected checkpoint contract

250k v0.1.2の元checkerはreplicate A/Bを相互比較していなかったため、本runではrole×shard logical comparisonを実装する。

checkpoint key:

```text
(role, shard)
```

final package artifactはbasenameをroleへ組み込み、必ず一意にする。

```text
final_package::general_repeat_calls.tsv
final_package::general_repeat_calls.tsv.gz
...
final_package::package_manifest.tsv
final_package::materialization.qc.tsv
```

比較規則:

```text
compressed TSV           decompressed byte equality
materialization QC       stage version / timingを除くsemantic metrics
package manifest         replicate固有pathを除くartifact/table/rows/bytes/SHA
other deterministic file raw byte equality
```

各replicateでmanifestのbytes/SHAを検証し、corrupted-SHA negative fixtureを拒否する。

## 5. Nested 250k parity

formal run IDが異なるため、以下を分ける。

```text
caller attempts:
    projection_idでsortし全field exact parity

core 5-table:
    run_idおよびrun-derived IDsのみ除外
    natural keyでsort
    全scientific field exact parity
```

caller parityとpackage parityは別booleanとして記録する。

## 6. Performance判定

```text
5.31M linear projection <=60 min   scaling gate PASS
5.31M linear projection <=30 min   target met
```

500kが60分外挿をPASSしても、G06はfull-scale empirical runまでOPENのままとする。

保存する説明変数:

```text
alignment records
candidate rows / reads
projection rows / reads
candidate-window records / bases
caller attempts / called / no-call
5-table row counts
stage wall times
maximum observed stage RSS
temporary + output bytes
```

## 7. 禁止事項

```text
active pipeline変更
SSOT更新
core schema変更
scientific caller semantics変更
full 5.31M execution
biology layer実装開始
historical 100k/250k artifactsの上書き
```

## 8. 次gate

500k PASSかつ60分外挿PASS:

```text
full 5.31M Core Technical Completion run設計
+ full-scale determinism
+ full-scale restart/resume
+ validators / memory / artifact audit
```

500kで60分外挿FAIL:

```text
critical-path optimization
→ 500k再検証
→ full 5.31Mは引き続き禁止
```
