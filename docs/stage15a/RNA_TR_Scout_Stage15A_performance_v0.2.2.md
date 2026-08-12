# RNA-TR-Scout Stage 15A performance candidate v0.2.2

作成日: 2026-08-08  
対象run: `ENCSR307SHM_pilot100k_mm2splice_v1`

## 1. 入力となる確定状態

Stage 15A v0.2.1は、100k BAM-to-finalについて次を満たした。

- correctness / implementation: PASS
- Stage 14 / Stage 15A reference packageとのexact logical parity: true
- frozen TSV / package validators: PASS
- atomic publication: PASS
- active pipeline / SSOT: unchanged
- full 5.31M: not run

実測は以下だった。

| 指標 | v0.2.1 |
|---|---:|
| BAM-to-final | 81.399995秒 |
| 5.31M単純線形外挿 | 72.0756分 |
| 60分hard ceiling | FAIL |
| 30分target | NOT_MET |

主なcritical path:

| stage | 秒 |
|---|---:|
| partition | 8.6471 |
| 11b | 4.1994 |
| 11d3 | 6.7108 |
| 11e | 7.6734 |
| native caller | 24.6060 |
| materializer | 9.5045 |
| merge | 1.4803 |
| gzip | 0.5914 |
| validators | 17.9683 |

100kで60分相当に必要な上限は約67.76秒であり、v0.2.1から約13.64秒の短縮が必要である。

## 2. v0.2.2の目的

科学的field、ID、row-set、sort、schema、failure/QC/materialization semanticsを一切変更せず、次の低～中リスク実行最適化で60分hard ceiling相当への到達可否を測る。

```text
read-hash partition (12 shards, FASTQ gzip level 0)
  → parallel 11b
  → parallel 11d3
  → shared-catalog fast 11e
  → per-shard caller→materializer pipeline
  → global k-way merge
  → parallel deterministic gzip
  → generic validators + exact frozen component validators in parallel
  → atomic publication
```

## 3. 変更点

### 3.1 shared-catalog fast 11e

v0.2.1では12 shardがそれぞれTRExplorer/STRchive catalogをロードし、motif dictionary、target summary、report-only outputまで生成した。

v0.2.2ではparent processがcatalogを1回だけロードし、Linux `fork` workerへread-only共有する。各workerはproduction callerに必要な`motif_scan_jobs.tsv.gz`とminimal QCだけを生成する。

安全条件:

- active 11eのjob-field semanticsを移植
- projection ID順を維持
- v0.2.1の12 shard job tableとdecompressed byte SHAをpost-timerで全件比較
- 1 shardでも不一致ならFAIL

### 3.2 caller→materializer pipeline

v0.2.1では全caller shard終了後に全materializer shardを開始した。v0.2.2では各shardについてcaller終了直後にmaterializerを開始する。caller / materializer本体はv0.2.1と同じ固定実装である。

### 3.3 package validator component parallelization

frozen `rnatr_v042_validate_package.py`は、正確には次の固定2 componentを逐次subprocess実行していた。

- `rnatr_v041_validate_package.py`
- `rnatr_v042_validate_flank_uniqueness.py`

v0.2.2 candidateは、SHA固定した同じ2 componentを同時実行し、両方のreturn codeとPASS markerを要求する。generic 5-table validatorsも従来どおり並列実行する。

追加安全策:

- publication後に元のfrozen v0.4.2 wrapperをproduction timer外で再実行
- `read_evidence.tsv`と`.tsv.gz`の両方を欠損させたnegative fixtureで、candidate / frozen validatorがともに失敗することを確認
- いずれか不一致ならFAIL

### 3.4 partition FASTQ gzip level 0

shard candidate FASTQは一時intermediateであり、final artifactではない。読み書きのCPU costを下げるためgzip level 0を使用する。read-ID set、record count、sequence/quality使用契約は変更しない。full development auditはproduction timer外で必須のまま維持する。

## 4. 固定benchmark topology

v0.2.2はshard/worker matrixではなく、v0.2.1との直接比較用benchmarkである。

```text
shards                    12
caller workers / shard     2
total caller workers      24
```

別値は受け付けない。

## 5. PASS条件

すべて必須:

- v0.1.3 / v0.2.0.1 / v0.2.1 baseline QC SHA・gate PASS
- active source / caller / materializer / schema / SSOT guard SHA一致
- 11b / 11d3 / fast 11e QC PASS
- caller aggregate 388,571 attempts / 160,315 called / error 0 / nonpositive overlap 18
- final 5-table row count一致
- final package exact logical parity with v0.1.3
- fast 11e exact logical parity with v0.2.1 shard jobs
- generic validators PASS
- parallel exact component validator PASS
- frozen wrapper postpublication PASS
- negative-fixture failure parity PASS
- atomic publication PASS
- active pipeline / SSOT byte-identical
- full 5.31M not started

## 6. 性能判定

```text
100k <= 33.88秒   → 30分target相当
100k <= 67.76秒   → 60分hard ceiling相当
100k >  67.76秒   → hard ceiling未達
```

hard ceilingを満たした場合の次gateは、restart/determinismと250k scalingである。未達の場合はpartition/caller profileを踏まえ、真の11b+11d3融合へ進む。

## 7. SSOT方針

この実行中はSSOTを変更しない。現在のSSOTはStage 15A reference correctness PASSを登録済みであり、そのSHAをguardする。

v0.2.0.1、v0.2.1、v0.2.2のperformance履歴は、v0.2.2評価後に一括登録する。active pipeline switchは別gateまで禁止する。
