# RNA-TR-Scout Stage 15A deterministic 250k BAM-input scaling contract v0.1.0

作成日: 2026-08-08  
状態: `DESIGNED_FOR_ISOLATED_EXECUTION`  
対象: ENCSR307SHMの決定論的nested 250k subset  
禁止: active pipeline切替、SSOT更新、full 5.31M実行

## 1. 目的

Stage 15A v0.2.2.1は100k BAM-to-finalで65.7636秒、exact logical parity、frozen validation、atomic publicationをPASSし、5.31Mへの単純線形外挿は58.23分だった。ただし余裕は約3%しかなく、100k startup/cache効果だけではproduction ceilingを保証できない。

本gateは、250kへ入力を増やして次を検証する。

- 100kで確立したscientific semanticsの維持
- Python hash seedを変えた独立2回実行のpackage reproducibility
- stage別scaling、peak RSS、temporary bytes、complexity変数
- 250k checkpoint manifestの完全性
- 100k anchor readsについてのalignment/package exact parity
- 5.31M・60分hard ceilingへの更新外挿

## 2. 入力設計

full 5,312,696-read FASTQはpipelineへ流さない。元の100k pilot readを全件含め、残りから固定seedのSHA-256 bottom-kで150,000 readを追加し、nested 250k FASTQを作る。

```text
original validated 100k reads
  + deterministic additional 150k reads
  = nested 250k reads
```

250kのみを、100kと同じminimap2 splice parameter contractでmappingする。mapping時間はFASTQ-to-BAM preparationとして別建てで報告し、BAM-to-final timerには含めない。

## 3. BAM-inputの正確な意味

本gateのcore timerは以下を入力とする。

```text
mapping-complete 250k BAM + BAI
+ corresponding 250k raw-read FASTQ sequence store
```

100k performance benchmarkではcandidate FASTQが準備済みだった。250kでは11b後のcandidate read抽出をcore timerへ含め、BAM＋associated raw sequence storeからのcold-path時間を測る。比較用にcandidate extractionを差し引いたwarm-equivalent時間も併記する。

## 4. 実行graph

各replicateは12 read-coherent shards × caller 2 workersで実行する。

```text
250k BAM + 250k raw FASTQ
  → read-hash partition
  → parallel 11b
  → parallel candidate FASTQ extraction
  → parallel 11d3
  → shared-catalog fast 11e
  → pipelined native caller v0.4.1 + materializer
  → deterministic global merge + pigz
  → frozen TSV/package validation
  → atomic publication
```

11f/11hはproduction pathから除外したまま、scientific callerやschema semanticsは変更しない。

## 5. Determinism contract

同一250k inputを独立rootで2回実行する。

```text
replicate A: PYTHONHASHSEED=0
replicate B: PYTHONHASHSEED=20260808
```

必須:

- 5 core tablesのplain TSV raw SHA完全一致
- 5 core tablesのdeterministic gzip raw SHA完全一致
- per-shard caller logical SHA一致
- row counts / complexity variables一致
- both packages frozen-validator PASS

## 6. Nested 100k regression

250k mapping中の元100k readについて、100k BAMとのalignment signature parityを要求する。さらに250k packageをread_idでfilterし、元100k v0.2.2.1 packageと5表すべてでordered canonical SHAを比較する。

これは生物学的真値ではなく、input scaleを変えても同一readのsoftware semanticsが変化しないことを確認するsoftware regressionである。

## 7. Performance variables

read数だけでなく以下を記録する。

- alignment records
- candidate rows / candidate reads
- projection rows
- candidate-window records / total bases
- caller attempts / called / no-call / errors
- 5-table rows
- stage wall time
- observed stage peak RSS
- peak temporary/output bytes
- cold BAM-to-final / warm-equivalent time

## 8. Restart / checkpoint scope

250kでは全intermediateとfinal artifactをSHA固定したcheckpoint manifestを作成し、negative fixtureが拒否されることを検証する。

100kで実施済みのintentional stop → selective materializer resumeは再実行しない。したがって、250kではcheckpoint integrityをPASSできるが、250k selective resumeおよびfull-scale restartabilityはOPENのままとする。

## 9. Gate判定

- correctness / determinism / nested regressionがすべてPASSしなければ250k gate FAIL
- 5.31M projectionは2 replicateの遅い方を使用
- projection <=60分: 60分hard-ceiling scaling gate PASS
- projection <=30分: target met
- 60分を超えた場合、full 5.31Mへ進まず、250k profileに基づき11d3+11e融合等へ戻る
- 60分以内なら、次はdeterministic 500k scaling

いずれの場合も、active pipelineとSSOTは本実行中に変更しない。SSOT更新は結果評価後の別gateとする。
