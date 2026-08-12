# RNA-TR-Scout Stage 15A performance critical-path candidate v0.2.1

作成日: 2026-08-08  
対象run: `ENCSR307SHM_pilot100k_mm2splice_v1`

## 1. v0.2.0.1実測

Stage 15A performance v0.2.0.1は100kでcorrectness/implementationともにPASSした。

- final 5-table package: v0.1.3 referenceとexact logical parity
- frozen TSV validators: PASS
- frozen package validator: PASS
- atomic publication: PASS
- active pipeline / SSOT: unchanged
- full 5.31M: not run
- BAM-to-final production timer: 99.788350秒
- 5.31M linear projection: 88.357528分
- 60分hard ceiling: FAIL
- 30分target: NOT_MET

主要timing:

| component | seconds |
|---|---:|
| partition | 8.752 |
| 11b | 5.591 |
| 11d3 | 8.089 |
| 11e | 6.703 |
| native caller | 24.686 |
| materializer | 12.462 |
| merge | 1.434 |
| gzip | 0.683 |
| validators | 18.015 |

列挙stage合計は約86.4秒であり、残り約13.4秒はtimed lane内に残っていたdevelopment-only reread/auditである。

## 2. v0.2.1の変更

科学的caller、materialization semantics、schema、final validators、final package contractは変更しない。

低リスクのexecution変更のみ行う。

1. `12 shards × 2 caller workers/shard`
   - caller総worker数は24のまま
   - single-processである11b/11d3/11e/materializerのshard粒度を細かくする
2. shard BAMのBAIを作らない
   - isolated 11b/11d3はいずれも`fetch(until_eof=True)`で順次走査する
   - active scriptは変更せず、isolated copyのpreflight-only BAI checkだけを除く
   - `samtools quickcheck`は維持する
3. production timer内では小さいQC summaryだけを読む
   - 11b candidate count
   - 11d3 projection count
   - 11e motif-job count
   - caller QC counters
4. 以下のfull development regressionはfinal validation/atomic publication後、production timer外で必ず実行する
   - shard BAM/FASTQ SHA-256
   - assignment/FASTQ read-ID set equality
   - projection/job exact order digest
   - caller output row recount
   - v0.1.3 package exact logical parity
5. frozen TSV validatorsとfrozen package validatorはproduction timer内に残す
6. package validatorをproduction後にcProfileでもう一度実行し、次段階の律速解析資料を保存する

## 3. PASS contract

- all final table row counts unchanged
- final package exact logical parity with v0.1.3
- frozen TSV validators PASS
- frozen package validator PASS before publication
- atomic publication PASS
- full post-timer development audit PASS
- active pipeline byte-identical
- SSOT byte-identical
- full 5.31M not run

性能判定:

- 100k <= 33.88秒: 30分target相当
- 100k <= 67.76秒: 60分hard ceiling相当
- 100k > 67.76秒: hard ceiling未達

## 4. 次gate

- 60分相当PASS: restart/determinismとdeterministic 250k scalingへ進む
- 未達: validator profile、shard/worker matrix、11d3+11e融合を検討する
- caller fast-pathはupstream/output最適化後まで保留する

## 5. 禁止事項

- active pipeline switch禁止
- SSOT更新禁止（結果評価後に別scriptで記録）
- full 5.31M実行禁止
- reference/audit lane削除禁止
- scientific field semantics変更禁止
