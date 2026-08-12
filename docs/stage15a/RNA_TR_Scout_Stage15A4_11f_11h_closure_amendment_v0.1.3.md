# RNA-TR-Scout Stage 15A4 upstream-closure amendment v0.1.3

作成日: 2026-08-08  
対象run: `ENCSR307SHM_pilot100k_mm2splice_v1`  
対象工程: Stage 15A isolated 100k BAM-to-final reference lane

## 1. v0.1.2 failureの分類

Stage 15A v0.1.2では、次が完了し、frozen active referenceとのsemantic parityを通過した。

```text
15A1  11b target assignment       PASS
15A2  11d3 raw-read projection    PASS
15A3  11e motif-job preparation   PASS
```

その後、promoted native v0.4.1 integration driverは次の入力を要求して停止した。

```text
results/11_periodic_refinement/
  ENCSR307SHM_pilot100k_mm2splice_v1/
  target_constrained_periodic_calls.tsv.gz
```

したがって、v0.1.2の失敗はcaller algorithm、native kernel、BAM、projection、motif jobs、schemaの異常ではない。Stage 15A設計上の**upstream execution-graph closure不足**である。

## 2. 確定した実行契約

Stage 14G/14Kでvalidationされたpromoted caller glueは、11e motif jobsだけでなく、historical P0/P1 branchの11h outputをpriorとして使用する。11hは11f baselineを入力とするため、Stage 15A reference laneの正しい最小閉包は次である。

```text
mapping-complete BAM
  -> 11b target assignment
  -> 11d3 raw-read projection
  -> 11e motif-job preparation
  -> 11f simple-periodic baseline
  -> 11h target-constrained periodic refinement
  -> deterministic native general caller v0.4.1
  -> materializer v0.1.2
  -> evidence schema v0.4.2 validators
  -> final package
```

`11g`は11f outputの監査工程であり、promoted callerの直接入力ではない。Stage 15A correctness gateでは、fresh 11f/11h outputsをfrozen active referenceへexact semantic comparisonすることで同等以上の閉包を与える。

## 3. 禁止する便法

次を禁止する。

1. active projectのhistorical 11h artifactをStage 15A shadow rootへ単純linkして、BAM-to-finalと称すること。
2. validatedされていない新規11e-to-caller adapterを発明すること。
3. active 11f/11h scriptまたはactive production outputを編集・上書きすること。
4. reference lane完了前に5.31M full datasetを実行すること。

## 4. v0.1.3 resume方針

v0.1.3は、v0.1.2で完了した11b/11d3/11eを無条件には再利用しない。各stageについて、

- completion marker
- output path・bytes・SHA-256
- frozen referenceとのrow/header/decompressed-content parity
- measured elapsed time

を再検証した後、read-only symlinkとして新しいv0.1.3 shadow rootへ接続する。BAM-to-final composed runtimeには、v0.1.2で実測した11b/11d3/11e時間を含める。

11fと11hはv0.1.3 shadow root内でfresh executionする。両者のcalls、top500、summary、QC、parametersがactive frozen referenceとsemantic exact一致した後にのみcallerを起動する。

## 5. isolation / provenance

- active pipeline switch: prohibited
- active output modification: prohibited
- SSOT modification: not performed in this repair run
- full 5.31M execution: prohibited
- historical 11h artifact reuse: prohibited
- new direct adapter: not created
- v0.1.2 failure artifacts: preserved
- v0.1.3 result/QC root: new versioned directories

## 6. v0.1.3 PASS条件

以下をすべて満たすこと。

1. v0.1.2 11b/11d3/11e resume source verification PASS。
2. fresh 11f output 49,793 rows、frozen active referenceとsemantic exact parity。
3. fresh 11h output 49,793 rows、frozen active referenceとsemantic exact parity。
4. native caller 388,571 rows、Stage 14G deterministic referenceとexact parity。
5. hash seedを変えたcaller再実行とexact parity。
6. materializer v0.1.2 outputがfrozen Stage 14K2 packageとexact logical parity。
7. generic 5-table validatorとcross-table package validatorがPASS。
8. atomic final-package publicationがPASS。
9. active scriptsおよびactive 11f/11h outputsのbefore/after fingerprintが不変。
10. active pipeline/SSOTを変更せず、full 5.31Mを開始していないこと。

reference lane PASS後もStage 15A全体は`IN_PROGRESS`とし、次gateはperformance candidate、restartability、resource/performance validationである。
