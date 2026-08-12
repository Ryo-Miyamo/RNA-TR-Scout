# RNA-TR-Scout Stage 15A performance candidate v0.2.0

作成日: 2026-08-08  
対象run: `ENCSR307SHM_pilot100k_mm2splice_v1`  
状態: Stage 15A reference/correctness lane v0.1.3 PASS後のperformance candidate

## 1. 前提

Stage 15A v0.1.3では、mapping-complete 100k BAMから以下の経路が隔離実行され、Stage 14のfrozen caller/packageとexact logical parityを満たした。

```text
11b → 11d3 → 11e → 11f → 11h
    → deterministic native general caller v0.4.1
    → materializer v0.1.2
    → evidence schema v0.4.2 package
```

v0.1.3のcorrectness statusはPASSである一方、composed runtimeは333.981925秒であり、5.31Mへの単純線形外挿は約295.7分だった。したがって、Stage 15A全体は`IN_PROGRESS`であり、次gateはperformance candidateである。

## 2. v0.2.0の目的

active pipeline、SSOT、旧referenceを変更せず、同じ100k BAMを用いてexecution architectureのみを高速化する。final 5-table packageはv0.1.3 reference packageとdecompressed byte-exactであることを必須とする。

full 5.31Mは実行しない。

## 3. execution graph

```text
100k coordinate-sorted BAM + candidate FASTQ
    ↓ read_idのSHA-256で6つのread-coherent shardへ分割
parallel 11b
    ↓
parallel 11d3
    ↓
parallel 11e
    ↓
parallel native general caller v0.4.1
    ↓
parallel materializer v0.1.2 semantics
    ↓
5 tableのparallel global k-way merge
    ↓
5 tableのparallel deterministic gzip
    ↓
frozen 5-table validators + frozen package validatorを同時実行
    ↓ 全validator PASS後のみ
fsync + atomic rename
    ↓
v0.1.3 packageとのexact logical parity audit
```

## 4. read-coherent sharding contract

全alignment、candidate FASTQ record、projection、motif job、caller attemptを`read_id`単位で同じshardへ配置する。

materializerのevidence grouping keyは、

```text
(read_id, target_region_id, representative_locus_id)
```

であるため、read単位のshardingでは1つのevidence groupが複数shardへ分断されない。各shard内の元入力相対順序を維持し、final tableはfrozen materializerと同じsort keyでglobal k-way mergeする。

## 5. 11f / 11hの扱い

v0.1.3で使ったpromoted caller integration driverをコード監査した結果、11h tableはcaller task生成、motif選択、repeat call、77-column caller outputの作成には使われず、call作成後のlegacy P0/P1 bridge auditだけに使われていた。

v0.2.0では、scientific caller v0.4.1の関数とcall pathを変更せず、このaudit-only dependencyだけをperformance production pathから外す。正しさは最終`general_repeat_calls`を含む5 table全体のv0.1.3 exact logical parityで判定する。

11f/11h自体とv0.1.3 reference outputは削除・変更しない。

## 6. upstream execution-only patch

active 11b/11d3/11eは変更しない。各shard内の隔離コピーに限り、以下を行う。

- `paths.env`をshard rootへ差し替える
- 11b validatorをfrozen v0.3.1へ固定する
- 11d3/11eの100k固定expected row/read値をenvironment override可能にする
- 11eのreport-only `head -n 30`をfull-consumer `sed -n '1,30p'`へ置換する
- intermediate gzipを`compresslevel=1`にする

scientific classification、coordinate、assignment、projection、motif-job contractは変更しない。

## 7. materialization optimization

materializer v0.1.2のID生成、grouping、eventization、failure/QC/materialization semantics、schema field valuesは維持する。

execution-only変更は以下である。

- 11d3で監査済みの`read_length_bp`と`mean_read_q`を再利用し、materializerでcandidate FASTQを再走査しない
- `DictWriter`用のrow dictionary再構築を避け、同じfield orderのpositional writerを使う
- shardではplain TSVのみ作成する
- final plain TSVをglobal deterministic merge後、gzipを1回だけ作る
- 5 tableのmergeをtable単位で並列化する
- final gzipは`pigz -1 -n`をtable単位で並列実行し、mtime/file-name metadataを持たない再現可能なstreamにする

## 8. validation / publication contract

- frozen generic TSV validator 5本を実行する
- frozen cross-table package validatorを実行する
- 6 validatorをimmutableな`.part` package上で同時実行する
- 1つでもFAILならfinal packageをpublishしない
- 全PASS後にfsyncし、同一filesystem内でatomic renameする
- rename前後のdevice/inode/size一致を確認する
- v0.1.3 reference packageとのdecompressed byte-exact parityを5 tableのplain/gzip双方で確認する

reference comparisonはdevelopment regression auditであり、production BAM-to-final timingには含めない。

## 9. performance gate

100k実測から以下を記録する。

```text
performance_candidate_bam_to_final_seconds
performance_candidate_speedup
conservative_linear_5_31m_projection_minutes
five_m_target_30min
five_m_hard_ceiling_60min
```

30分はtarget、60分はhard ceilingである。v0.2.0がcorrectness PASSでも外挿が60分を超える場合、Stage 15A全体は`IN_PROGRESS`のまま、critical-path optimization v0.2.1へ進む。

## 10. 禁止事項

- active pipeline switch
- SSOT active flag変更
- 旧11f〜11k3またはStage 14/15A referenceの削除・上書き
- full 5.31M実行
- final package parity確認前のproduction promotion
