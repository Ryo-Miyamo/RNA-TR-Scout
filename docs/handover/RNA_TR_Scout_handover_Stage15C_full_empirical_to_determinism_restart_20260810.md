# RNA-TR-Scout 引き継ぎサマリー
## Stage 15C full 5.31M empirical completion → release-scale determinism / full-scale restart-resume

作成日: 2026-08-10  
対象project: `/mnt/intelssd/rnatr_project`  
推奨開始設定: **Pro**

---

## 0. 次スレッドで最初に読む要点

RNA-TR-Scoutは、ENCODE ONT cDNA `ENCSR307SHM` の全 **5,312,696 reads**について、mapping済みBAMからschema v0.4.2 final packageまでを、検証済み144-shard architectureで完走した。

```text
full BAM→final empirical runtime    60.041256352 min
runtime判定                         PASS_WITH_DOCUMENTED_TOLERANCE
execution correctness               PASS
memory                              PASS
storage                             PASS
atomic publication                  PASS
package published                   true
```

60分を超えたのは約 **2.475秒**である。これはstrict `<=60.000 min` PASSではなく、事前にfreezeした修士論文用tolerance（`>60～<=62分`）によるPASSとして扱う。30分targetは維持するが、初回Core Freezeではnon-blockingである。

現在のmainline next gateは次の2つである。

```text
1. release-scale determinism
2. full-scale restart/resume
```

その後に、

```text
PRE_RELEASE_CANDIDATE Architecture consistency audit
→ explicit active-path promotion
→ clean-install / GitHub internal beta readiness
→ Core Freeze / v0.5.0-rc1
```

へ進む。

**G31の深いsemantic adjudicationは、ユーザー判断により現時点では実行しない。** 技術的runawayが見られないことを成果として保持し、candidate rate 79.29%や約4.9 loci/readのbiology上の意味づけはbiology phaseへ移管する。

---

## 1. frozen scientific core

```text
scientific caller       native general caller v0.4.1
materializer            v0.1.2
core evidence schema    v0.4.2
```

これらはStage 15B–15Dで変更していない。

```text
active pipeline modified    false
SSOT modified               false  （Stage15C/15D結果はまだ未登録）
core schema modified        false
```

現行active production pipelineは依然として旧P0/P1 11-stage系であり、Stage15 candidateはまだactiveへpromotionしていない。

```text
MAP_SPLICE
11b_TARGET_ASSIGNMENT
11d3_RAW_READ_PROJECTION
11e_MOTIF_JOBS
11f_PERIODIC_BASELINE
11g_BASELINE_AUDIT
11h_PERIODIC_REFINEMENT
11i_INTERNAL_RECLASSIFICATION
11j_EXACT_SPAN_CALIBRATION
11k_CALIBRATED_EVIDENCE
11k3_SPAN_NORMALIZATION
```

Stage15 candidateは、full-scale empirical validation済みの**PROVISIONAL candidate**である。

---

## 2. SSOTの現在地と更新方針

現在のSSOTは、250k deterministic scaling＋post-250k Architecture auditまで登録済みである。

baseline:

```text
SSOT source SHA-256
8aeff1eda5c301e74a9054e786ed19bf5b699ff6aa111221aa2e60f6d733b37b

SSOT SQLite SHA-256
7edb4eb63e8f04b6fe8d8e67a82a6d9d70ba55c1946c62827d7b133e0d5a4274

core schema v0.4.2 SHA-256
c0509a0669344dba0b07cd1bb9e71f2aeb01e0196df47ec9178f1d2464b515f1

release_gates_v0.2.4 SHA-256
90ecf0c5f9cf0ba68361a5538d98aabc63afbe063fec5ee1060a7d0e508cce87
```

未登録:

```text
500k deterministic scaling
Stage15B memory-bounded validator equivalence
Stage15C 144-shard architecture validation
full mapping
full 5.31M empirical BAM→final v0.1.6
G31 auditとそのscope amendment
G25–G30 internal-beta planned requirements
```

この引き継ぎと同時に、preflight-first・rollback付きSSOT updaterを作成した。次スレでは、まずupdaterの`--self-test`と`--preflight`を実行し、preflight bundleをProで監査してから`--execute`する。

SSOT更新によっても、`current_pipeline`・core schema・既存QC・既存release gate fileは変更しない。新規version `release_gates_v0.3.0.tsv`を追加し、過去結果は上書きせずamendmentで登録する。

---

## 3. 500k deterministic scaling

formal run ID:

```text
ENCSR307SHM_stage15a500k_seed20260809_mm2splice_v1
```

主要結果:

```text
input reads                              500,000
replicate A cold BAM→final               335.381699772 sec
replicate B cold BAM→final               334.351324855 sec
conservative full 5.31M projection        59.392700495 min
500k→full 60-min projection              PASS
package raw reproducibility              true
package logical reproducibility          true
caller hash-seed reproducibility         true
checkpoint logical reproducibility       true
nested 250k scientific parity            true
candidate rows                           1,948,859
candidate reads                            396,549
```

QC:

```text
/mnt/intelssd/rnatr_project/qc/15_stage15a_bam_to_final/
ENCSR307SHM_stage15a500k_seed20260809_mm2splice_v1/
v0.1.1_500k_scaling/stage15a_scaling_500k.qc.tsv
```

QC SHA-256:

```text
ef27be62e633e941b21978d8354a928a7ecea33600465fe6620e82640b329e82
```

---

## 4. Stage 15B memory-bounded package validator

旧frozen global validatorは500kで約27.9GB RSSを使用し、full-scaleへ単純外挿するとhost RAMを超えるため、shard-wise frozen validation＋global external-sort uniquenessを用いるbounded validatorを作成した。

結果:

```text
100k frozen/candidate accept parity       PASS
500k frozen/candidate accept parity       PASS
negative fixtures                          10 / 10 PASS
validator equivalence                     PASS
candidate 500k elapsed                    38.8756 sec
candidate max single-shard RSS            2,359,288 kB
old frozen global RSS                     27,887,936 kB
```

candidate:

```text
/mnt/intelssd/rnatr_project/scripts/
rnatr_stage15b_validate_package_sharded_memory_bounded_v0.1.0.py
```

SHA-256:

```text
1136086f0214bcd11a2a2d71f2e459f433c7fc9f51d170aa3b97826e8808ee99
```

Stage15B QC SHA-256:

```text
b5f7f26f91d0edafbdc77de3373b67b8cc9ec3e16fb2f903cec4390a9d47f142
```

Scope:

```text
STAGE15A_READ_COHERENT_SHARDS_CORE_V042_NO_LOCUS_AGGREGATION
```

locus aggregationはNOT_RUNであり、このequivalenceを将来の全packageへ無条件拡張しない。

---

## 5. full FASTQとfull mapping

full FASTQ:

```text
/media/tokushimaneuro02/T9/rnatr_data/downloads/ENCSR307SHM/
ENCFF260PGB.fastq.gz
```

```text
reads       5,312,696
bases       7,165,363,866
bytes       8,995,223,210
MD5         23270f6b994db147df2f4c53f8358b
```

mapping run ID:

```text
ENCSR307SHM_full5312696_mm2splice_v1
```

full BAM:

```text
/mnt/intelssd/rnatr_project/results/11_mapping/
ENCSR307SHM_full5312696_mm2splice_v1/
ENCSR307SHM_full5312696_mm2splice_v1.sorted.bam
```

```text
BAM bytes       9,072,339,104
BAM SHA-256     95fc869291dd471112e31e10f81571b918621d9008580b1d09ddd3a6fefbfb85
mapping rate    96.442804%
median MAPQ     60
FASTQ/BAM primary read-ID multiset parity    PASS
mapping time    75.433333 min
```

mapping時間はBAM→final 60分gateに含めない。

---

## 6. 144-shard execution architecture

正式構成:

```text
read-coherent shards                  144
active shard concurrency               12
caller workers / active shard           2
validator workers                        3
external sort buffer                  512M
PYTHONHASHSEED                            0
partition rule       SHA-256(read_id) modulo shard count
```

500kを12 shardと144 shardで比較し、core 5 tablesのplain/gzip packageでraw/logical exact parityを確認した。

```text
scientific output independent of 12 vs 144 shards    true
500k/144-shard BAM→final                             323.433639 sec
full adjusted projection                             53.665702 min
memory readiness                                     PASS
storage readiness                                    PASS
```

post-11b hard maximum:

```text
164,204 candidate rows / shard
```

full runnerは、11b後に全shardの実測candidate loadを確認し、1 shardでも上限を超えればcaller/materializer開始前に停止する。

architecture QC SHA-256:

```text
43226464ef19572de3fcccef1a6e7fd169e22e20e8fa3b724f9d2f1080ce0437
```

---

## 7. full runner artifact生成で起きた重要な失敗と改善

このthreadでは、project複雑化により、top-level contractからruntime-generated artifactまでの整合性を人手だけで保つ限界が明らかになった。過去失敗は削除せずprovenanceとして保存する。

### v0.1.0–v0.1.3 build/preflight失敗

例:

```text
unvalidated 60-shard案の混入
formal analysis run IDとmapping run IDの混同
mandatory post-11b hard gate欠落
resource-model TSVとtop-level QCのfield名取り違え
生成runnerだけ旧schema名を保持
生成コード中のescape/SyntaxError
```

これを受け、contract-driven buildへ移行した。

```text
validated contract
→ generated runner
→ AST/static audit
→ negative mutation tests
→ dynamic safety tests
→ final-byte hash lock
```

### v0.1.4 full execution failure

v0.1.4はfresh partition完了後、wave 1の11bで停止した。

原因:

```text
runtime-generated 11b scriptが、full run IDではなく
ENCSR307SHM_stage15a500k_seed20260809_mm2splice_v1
のBAM pathを参照した
```

結果:

```text
partition完了
11b未完了
caller/materializer未開始
package publication false
active pipeline/SSOT変更なし
```

### v0.1.5 preflight前に棄却

run IDは修正されたが、11d3に旧500k candidate/window pathが残り、`BOUND_SOURCE_ROOT`も未定義だったため、bundle監査でpreflight前に棄却した。

### v0.1.6で解消

runtime生成される、

```text
144 shards × 3 scripts = 432 scripts
```

について、

```text
旧500k run ID残存             0
mapping run ID混入            0
旧500k runtime path残存        0
expected path一致             PASS
bash syntax                    PASS
3312 path-binding checks       PASS
```

をformal timer開始前に監査するようにした。

---

## 8. full 5.31M empirical BAM→final v0.1.6

analysis run ID:

```text
ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1
```

runner:

```text
/mnt/intelssd/rnatr_project/scripts/
rnatr_stage15c_run_full5312696_bam_to_final_v0.1.6.py
```

runner SHA-256:

```text
cca6b2d4c6e773392d3a8c24cd2fd2a1f0a41a713338b4ccdec1ba7fab5bafcc
```

final QC:

```text
/mnt/intelssd/rnatr_project/qc/15_stage15c_fullscale_bam_to_final/
ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/
v0.1.6/stage15c_full_empirical_run.qc.tsv
```

QC SHA-256:

```text
3b95addc1e7aa50ddf22d90dab3373025b9c7b41569fcb2aaea7d2910b35fd07
```

### performance

```text
bam_to_final_seconds                    3602.475381092
bam_to_final_minutes                    60.041256352
listed_stage_seconds                    3602.331200912
timer_unaccounted_seconds               0.144180180
runtime_gate                            PASS_WITH_DOCUMENTED_TOLERANCE
```

Timer scope:

```text
mapping included       false
partition included     true
validators included    true
atomic publication     included / PASS
```

正式な記載:

> Empirical 5.31M BAM-to-final runtime was 60.0413 minutes. This is not strict ≤60.000-minute PASS; it passes the predeclared documented tolerance for the first thesis/core freeze. The 30-minute target remains open and nonblocking for the first freeze.

### full counts

```text
input reads                    5,312,696
alignment records              9,774,085
primary mapped reads           5,123,713
primary unmapped reads           188,983
candidate reads                4,212,263
candidate rows                20,656,258
projection rows               20,656,258
caller attempt rows           20,656,258
caller called rows             8,524,435
caller no-call rows           12,131,823
caller error rows                      0
general_repeat_calls          20,656,258
read_evidence                 20,656,258
repeat_events                  8,523,140
repeat_segments                8,573,315
repeat_interruptions              43,399
```

### resources

```text
minimum MemAvailable             95,856,824 kB
maximum host used fraction       0.272065
maximum observed child RSS        2,409,004 kB
memory gate                       PASS

peak temporary + output bytes   146,580,576,495
minimum project free bytes      165,594,337,280
storage gate                      PASS
```

resource modelの約146GB予測は実測146.58GBとほぼ一致した。

### checkpoint

```text
checkpoint rows        1,884
checkpoint bytes       140,029,015,504
checkpoint SHA-256     f00d67e28413d66730b8c2ffab0f52b9ce9e1553e5cc9a3f9d768e4a7a0083b4
```

checkpoint manifest path:

```text
/mnt/intelssd/rnatr_project/qc/15_stage15c_fullscale_bam_to_final/
ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/
v0.1.6/stage15c_fullscale_checkpoint_manifest.tsv
```

### final package

```text
/mnt/intelssd/rnatr_project/results/15_stage15c_fullscale_bam_to_final/
ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1/
v0.1.6/package_full
```

10 plain/gzip artifacts合計:

```text
52,420,730,937 bytes
```

package manifest SHA-256:

```text
335058228a3f3c4205161f3d24b208009175aed5e50f995a74e04100b4f3a738
```

---

## 9. G31 row-expansion / candidate-entry audit

G31 v0.1.0はread-only、memory-bounded、144-shard parallelで既存artifactを監査した。

```text
elapsed        395.972777 sec
full rerun     false
```

machine result:

```text
g31_machine_status           FAIL_OVEREXPANSION_OR_LINEAGE
g31_core_freeze_gate_status  FAIL_BLOCKING
```

**このmachine resultは履歴として改変・削除しない。**

ただしPro reviewで、machine hard-failの大部分が、caller attempt tableとread_evidence summary tableをmirror比較した監査側の意味論仮定、およびmotifのrotation/reverse-complement equivalenceを考慮しない文字列一致に由来する可能性が高いと判断した。

一方、technical multiplicityについては次を確認した。

```text
11b assignment rows            20,656,258
11d3 projection rows           20,656,258
11e motif job rows             20,656,258
caller rows                    20,656,258
general_repeat_calls rows      20,656,258
read_evidence rows             20,656,258

stage row conservation         PASS
primary key duplicate          PASS / 0
unique read×locus              20,649,827
excess over unique read×locus       6,431  (0.0311%)
```

scale安定性:

```text
                 candidate rate     rows / candidate read
100k               79.1760%              4.9077
500k               79.3098%              4.9145
full 5.31M         79.2867%              4.9038
```

locus concentration:

```text
top 1 target share       0.2831%
top 10 target share      1.8127%
top 100 target share     6.4507%
```

したがって、full scaleで突然生じたtechnical runawayや、少数locusによる全row支配の所見はない。

---

## 10. candidate read率79.29%の現在の解釈

```text
candidate reads
4,212,263 / 5,312,696 = 79.2867%
```

分解:

```text
exact catalog overlapあり
3,020,451 reads
= candidate readsの71.706%
= 全input readsの56.853%

±500bp proximityのみ
1,191,812 reads
= candidate readsの28.294%
= 全input readsの22.433%

primary-supported candidates
4,068,447 reads
= candidate readsの96.586%
```

catalog geometry:

```text
targets                       349,490
raw interval union            7,438,340 bp  = genomeの0.2400%
±500bp padded union         192,363,072 bp  = genomeの6.2058%
```

RNA readsはtranscribed regionへ非一様に集中するため、genome-wide coverageだけから79.29%を異常とは判定しない。

重要な禁止解釈:

```text
79.29% candidate rate
≠ RNA repeat陽性率
≠ pathogenic repeat率
≠ expanded allele率
≠ final candidate率
```

11bは後段measurementへ渡すためのbroad sensitivity-oriented candidate entryである。

---

## 11. G31の正式なscope split

ユーザー決定により、G31の追加semantic adjudication v0.1.1は**現時点では実行しない**。

### G31-T — technical multiplicity integrity

Core Technical Freeze planning上の扱い:

```text
PASS_WITH_SCOPE_AMENDMENT
```

根拠:

```text
11b以降のrow conservation PASS
primary ID uniqueness PASS
read×locus duplicate excess 0.0311%
100k/500k/fullでcandidate率・multiplicity安定
特定locusへの異常集中なし
full-scale runawayの証拠なし
```

### G31-B — biological candidate-entry / multiplicity interpretation

```text
OPEN_DEFERRED_TO_BIOLOGY_LAYER
nonblocking for current technical freeze
```

持ち越す問い:

```text
79.29% candidate率のbiology上の意味
±500bp paddingの妥当性とrecallへの寄与
約4.9 loci/readのtranscript/cDNA/splice/catalog上の意味
catalog overlap / motif equivalence
candidate entryをrecallを落とさず狭められるか
```

未実行script:

```text
rnatr_stage15d_g31_semantic_adjudication_v011.py
```

これは削除不要だが、現時点では実行しない。

---

## 12. Core Technical Completionの現在地

```text
full 5.31M empirical correctness       PASS
runtime                               PASS_WITH_DOCUMENTED_TOLERANCE
memory                                PASS
storage                               PASS
bounded validator equivalence         PASS
atomic publication                    PASS
runtime-generated script/path audit   PASS
G31-T technical multiplicity          PASS_WITH_SCOPE_AMENDMENT

release-scale determinism             OPEN
full-scale restart/resume             OPEN
PRE_RELEASE_CANDIDATE architecture    OPEN
explicit active-path promotion        OPEN
clean-install/internal beta           OPEN
```

したがってCore Technical Completionは**非常に近いが、まだ未完**である。

---

## 13. 次のmainline — release-scale determinism

目的:

```text
同一input
同一scientific version
同一reference
同一parameters
異なるhash seed / execution attempt
→ final scientific package exact logical parity
```

最低要件:

```text
full-scale second executionまたはcheckpointからの独立再構成
core 5 tables plain/gzip logical SHA比較
caller attempt logical parity
package manifest logical parity
runtime-only fieldsを科学的比較から除外
差異があればfield/key単位dossier
```

disk負荷が非常に大きいため、full 5.31Mを無条件にもう1本丸ごと保持する前に、artifact保持・reuse禁止・比較単位をProで設計する。

---

## 14. 次のmainline — full-scale restart/resume

freeze済み要求:

```text
intentional stop
corrupt checkpoint rejection
selective resume
clean packageとのexact logical parity
second resume no-op
atomic publication
resume provenance
```

現在のfull checkpoint:

```text
1,884 rows
140.0GB
```

これを利用して、どのstage/shardをintentionalにinvalidateするか、再計算範囲、timer scope、既存clean result保持方針を先に設計する。

restart/resume検証でclean runの60.041分benchmarkを上書きしない。

---

## 15. PRE_RELEASE_CANDIDATE Architecture consistency audit

必須監査domain:

```text
SSOT
active code/path
schema/frozen contracts
performance gates
validation/restart/artifact contracts
biology roadmap
release-readiness roadmap
script lifecycle
```

必須観点:

```text
仕様間矛盾
obsolete design/script残存
未実装項目の実装済み扱い
freeze済みcontract drift
planned gateの取りこぼし
runtime-generated artifactまでのcontract binding
```

full runner作成過程でrun ID/path/schema binding defectが実際に起きたため、pre-RC auditではtop-level sourceだけでなくruntime-generated scriptとinstaller/setupも対象にする。

---

## 16. GitHub internal beta / release-readiness G25–G30

すべて`OPEN_PLANNED`であり、未実装をPASS扱いしない。

```text
G25  version-pinned/checksummed reference bootstrap
G26  CPU/RAM/output/tmp resource detection
G27  memory-aware automatic concurrency + manual overrides
G28  cross-hardware/concurrency scientific logical determinism
G29  clean-machine clone→setup→test reproducibility
G30  empirical minimum/recommended/tested hardware profile
```

利用者の理想形:

```text
RNA-TR-Scout本体＋解析対象FASTQ/BAMを用意
→ setupが共通referenceをversion固定・checksum付きで取得
→ hardware-awareにshard/workerを自動調整
→ 同一input/version/referenceならscientific outputは一致
```

大容量reference本体はGitHubへ含めない。

---

## 17. storageと削除方針

full v0.1.6は、途中artifact・checkpointを含めて大容量である。現時点では次を削除・移動しない。

```text
full v0.1.6 result root
full v0.1.6 QC root
package_full
144 shard intermediates
checkpoint manifestが指すartifact
500k accepted results
Stage15B validator evidence
G31 v0.1.0 evidence
v0.1.4 failure provenance
```

restart/determinism設計で何を保持・削除可能か決めるまでは触らない。

---

## 18. 正式runtime policy

```text
<=60.000 min             PASS_STRICT
>60.000 and <=62.000     PASS_WITH_DOCUMENTED_TOLERANCE
>62.000                  FAIL_FOR_FIRST_CORE_FREEZE
30 min                   formal target, nonblocking for first freeze
```

full empirical v0.1.6は、

```text
60.041256352 min
PASS_WITH_DOCUMENTED_TOLERANCE
```

である。strict PASSとは書かない。

---

## 19. 6検体panelの制限

6検体×100kはengineering sanity check用途に限定する。

使用可:

```text
pipeline再現性
gross artifact
実装破綻
大きな検体間差
runtime sanity
```

使用不可:

```text
精密technical uncertainty model
RNA population normal range
pathogenicity threshold
locus/motif/length/support依存の精密背景分布
```

後者はcore freeze後の大規模cohortで行う。

---

## 20. 次スレッドで最初に実行するもの

### A. SSOT updater self-test

```bash
sha256sum \
  ~/Downloads/rnatr_stage15d_update_ssot_fullscale_handover_v010.py

python \
  ~/Downloads/rnatr_stage15d_update_ssot_fullscale_handover_v010.py \
  --self-test
```

### B. read-only preflight

```bash
python \
  ~/Downloads/rnatr_stage15d_update_ssot_fullscale_handover_v010.py \
  --preflight
```

preflightはSSOT、active pipeline、schema、resultsを変更しない。生成bundleを新スレッドでPro監査してから、executeを許可する。

### C. executeはまだ行わない

最終的な更新コマンドは次だが、**preflight bundleのPro監査後まで実行しない**。

```bash
python \
  ~/Downloads/rnatr_stage15d_update_ssot_fullscale_handover_v010.py \
  --execute \
  --confirm-update REGISTER_STAGE15D_FULLSCALE_V010
```

---

## 21. 次スレッドへアップロードする最小ファイル

最低限:

```text
1. RNA_TR_Scout_handover_Stage15C_full_empirical_to_determinism_restart_20260810.md
2. rnatr_stage15d_update_ssot_fullscale_handover_v010.py
3. updater --preflightで生成されるtar.gz
```

過去の37MB G31 bundleやfull package本体を再アップロードする必要はない。必要時のみ既存bundleを参照する。

---

## 22. 次スレ開始時の推奨AI設定

**Pro推奨。**

理由:

```text
SSOT mutationの最終監査
release-scale determinism設計
full-scale restart/resume設計
Core Freeze前の重大なcontract判断
```

単純なscript実行・terminal出力貼付は「高い」でよい。設計・監査・結果判定ではProへ戻す。

---

## 23. 一文での現在地

> RNA-TR-Scoutは、5,312,696-read ONT cDNAのmapping-complete BAMからschema v0.4.2 final packageまでを、144-shard・bounded-memory architectureで実測60.0413分、correctness/memory/storage/publication PASSで完走した。G31ではfull-scale row runawayの証拠がないことを確認し、candidate-entryの生物学的意味はbiology phaseへ移管した。残るCore Technical Completion gateはrelease-scale determinism、full-scale restart/resume、pre-release architecture audit、active promotion、clean-install/internal beta readinessである。
