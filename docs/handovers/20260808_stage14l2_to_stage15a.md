# RNA-TR-Scout 引き継ぎサマリー
## Stage 14L2 完了 → 次工程 Stage 15A（100k BAM-to-final統合）

作成日: 2026-08-08  
プロジェクトルート: `/mnt/intelssd/rnatr_project`  
対象run: `ENCSR307SHM_pilot100k_mm2splice_v1`

---

## 1. 現在地

RNA-TR-Scoutでは、以下の経路が100k pilotでvalidatedになった。

```text
frozen motif/projection jobs
    ↓
deterministic native general caller v0.4.1
    ↓
evidence schema v0.4.2 materialization
    ↓
5-table generic validation
    ↓
cross-table package validation
```

一方、まだ次の全体経路はvalidatedではない。

```text
mapping-complete BAM
    ↓
target assignment
    ↓
raw-read projection
    ↓
motif jobs
    ↓
native general caller v0.4.1
    ↓
schema v0.4.2 final package
```

したがって、次工程は**active pipelineを切り替えずに、100k BAM-inputからfinal packageまでを隔離実行するStage 15A**である。

---

## 2. Stage 14L2 最終結果

Stage 14L2:

```text
audit_status                                      PASS
schema_version                                    0.4.2
schema_status                                     FROZEN_VALIDATED_PRODUCTION_SCHEMA_CANDIDATE
materializer_version                              rnatr_native_v041_to_evidence_v042_materializer_v0.1.2
package_rerun                                     false
caller_attempt_rows                               388571
called_attempt_rows                               160315
low_confidence_called_rows                        6307
low_confidence_eventized_rows                     6289
called_not_retained_rows                          18
called_not_retained_prior_overlap_nonpositive     18
repeat_event_rows                                 160297
active_pipeline_switched_to_v042                  false
bam_to_final_100k_validated                       false
next_gate                                         DESIGN_AND_RUN_ISOLATED_100K_BAM_TO_FINAL_V042
```

Stage 14L2 script SHA-256:

```text
95cc3637c5372f0f5339653d57a1967a0b0d03d985b1c07dd3951c34b61858ec
```

Stage 14L2後のSSOT:

```text
tool_version     rnatr_ssot_v0.1.2
database_sha256  673ca7c2136146cfd3ea80a22ceeafdabb156b549fe7e15c0d16077ac08f4f7d
ssot_cli_sha256  5496eaed1821e23d6ded93a57e60244ca5fa0cbfe4b13f3be2ef1ac442139811
warnings         0
integrity        PASS
foreign keys     PASS
```

---

## 3. General callerの確定仕様

### 3.1 reference / implementation

- 測定reference:
  - deterministic Python general caller v0.4.1
- production候補:
  - validated native general caller v0.4.1
- native caller path:

```text
/mnt/intelssd/rnatr_project/src/rnatr_scout/general_caller/native_v0.4.1/rnatr_general_repeat_caller_ref_v0.4.1.py
```

- SHA-256:

```text
d5a2e0545afa5d97026c3a6ac0be6bc355e87f4c130bc512b0b3bf9a5bf32351
```

### 3.2 determinism

旧v0.4.0ではPython set/hash順序により、完全同点時のorientationがrunごとに変わる非決定性があった。

v0.4.1では次をfreeze済み。

```text
既存score/rankingは変更しない
完全同点時のみ:
  1. input/canonical orientation
  2. reverse complement
の順に評価し、同点なら1を採用
```

Python/nativeは100k全388,571行で完全一致した。

### 3.3 速度

100k general caller:

```text
deterministic Python  約555秒
native                約21秒
speedup               約26倍
```

5.31M readsへのcaller-only線形外挿:

```text
約18.9分
```

これは**caller-only**であり、BAM-input全pipelineの時間ではない。

---

## 4. Evidence schema / materializer

### 4.1 schema

- schema v0.4.2:
  - `FROZEN_VALIDATED_PRODUCTION_SCHEMA_CANDIDATE`
- active production pipelineにはまだ切り替えていない
- schema path:

```text
/mnt/intelssd/rnatr_project/config/evidence_schema/v0.4.2
```

### 4.2 materializer

Path:

```text
/mnt/intelssd/rnatr_project/src/rnatr_scout/materialization/rnatr_materialize_native_v041_to_evidence_v042_v0.1.2.py
```

SHA-256:

```text
18a67ef312e74257549570ae81a6cca364055240f519d29dc7664e2ea1c429ea
```

### 4.3 100k package

```text
general_repeat_calls  388571
read_evidence         388571
repeat_events         160297
repeat_segments       161265
repeat_interruptions     848
```

以下はすべてPASS。

- caller 77列のlossless保持
- deterministic caller parity
- generic validator（5表）
- cross-table package validator
- flank uniqueness validator
- best caller summary audit
- package manifest検証

### 4.4 flank uniqueness

anchorの存在からuniquenessを推定してはいけない。

現在は全行:

```text
left_flank_unique               .
right_flank_unique              .
left_flank_uniqueness_status    NOT_ASSESSED
right_flank_uniqueness_status   NOT_ASSESSED
```

---

## 5. Failure / QC / materialization contract

以下は異なる次元であり、同じ理由を入れる必要はない。

### `failure_code`

単一のprimary failure classification。

### `qc_flags`

非排他的な複数条件。

### `materialization_status`

caller attemptを対象locusの`repeat_event`として正規化するかどうか。

100kの18件はすべて:

```text
integration_status       CALLED
call_status              LOW_CONFIDENCE
prior_overlap_bp         0
failure_code             GENERAL_CALLER_LOW_CONFIDENCE
qc_flags                 CALLER_LOW_CONFIDENCE;PRIOR_OVERLAP_NONPOSITIVE
materialization_status   CALLED_NOT_RETAINED
repeat_event             作成しない
```

重要:

```text
LOW_CONFIDENCE CALLED          6307
そのうちeventized             6289
CALLED_NOT_RETAINED              18
```

したがって、LOW_CONFIDENCE自体がeventization阻害因子ではない。  
18件は`prior_overlap_bp <= 0`のため、対象locus eventへ昇格しない。ただし`general_repeat_calls`にlosslessに保存する。

Contract:

```text
/mnt/intelssd/rnatr_project/results/14_schema_v042_promotion/ENCSR307SHM_pilot100k_mm2splice_v1/v0.1.2/FAILURE_CODE_QC_FLAGS_MATERIALIZATION_CONTRACT_v0.1.0.md
```

---

## 6. mismatch / indel / interruption / purity / LPS

完成版では以下を混同しない。

```text
match_bp_total
mismatch_bp_total
insertion_bp_total
deletion_bp_total
interruption_bp_total
mismatch_fraction
indel_fraction
edit_fraction
purity
lps_exact_sequence_bp
lps_inferred_bp
```

- mismatch/indelはalignment operation
- interruptionはstructured motif-breaking interval
- purityだけでtechnical/biological originを判定しない
- 現在のorigin statusは:

```text
NOT_ASSESSED
```

biological-vs-technical classifierは未実装・未検証。

---

## 7. RNA repeat length clustering contract

schema/validatorのみ作成済み。algorithmはまだ実装していない。

```text
cluster_analysis_status = NOT_RUN
```

原則:

- `repeat_events`がread/molecule-level source of truth
- clusterは初期状態で`C1`, `C2`, ...の中立ラベル
- repeat長だけでallele 1/2、maternal/paternal、normal/expandedとは呼ばない
- SNP phasing、matched DNA、orthogonal supportがある場合だけhaplotype/alleleへ昇格
- censored readをexact lengthとしてfitしない
- context-limited readを初期fitへ使用しない
- censor-aware modelを使う場合はversioned interval-likelihoodとして明示する
- `repeat_length_cluster_id`は既存`molecule_cluster_id`とは別

---

## 8. Validation framework / release gates

Release gates:

```text
/mnt/intelssd/rnatr_project/validation/release_gates_v0.2.2.tsv
```

主なPASS:

- G01 determinism
- G02 synthetic truth / semantic invariants
- G03 Python/native 100k exact parity
- G04 caller-only 5.31M <=30分予測
- G05 prepared-job → validated final-evidence package
- G11 mismatch/indel/interruption/purity/LPS分離
- G13 read-level distribution保持
- G15 unphased allele label禁止
- G16 censored/context-limitedのnaive exact pooling禁止
- G18 non-locus-anchored callsのlossless保持・非event化
- G19 failure_code / qc_flags / materialization_status分離

主なOPEN:

- G06 5M BAM-input runtime <=60分（target <=30分）
- G07 5M restartability / memory / artifact audit
- G08 real truth-bearing biological validation
- G09 large-cohort RNA background / technical distribution
- G10 FASTQ-to-final mapping-inclusive performance
- G12 biological-vs-technical origin classifier validation
- G14 RNA repeat-length clustering algorithm validation
- G17 100k mapping-complete BAM → schema v0.4.2 package

Truth hierarchy:

```text
Tier 1 constructed truth
> Tier 2 experimental/orthogonal truth
> Tier 3 replicate/cross-platform empirical agreement
> Tier 4 software regression
```

旧出力との一致はsoftware regressionであり、生物学的真値ではない。

---

## 9. 現在のactive pipeline

active pipelineはまだ旧P0/P1系である。

```text
MAP_SPLICE
11b target assignment
11d3 raw-read projection
11e motif jobs
11f parallel periodic baseline
11g baseline audit
11h parallel refinement
11i internal reclassification
11j exact-span calibration
11k calibrated evidence
11k3 span normalization
```

native general caller v0.4.1、materializer v0.1.2、schema v0.4.2はvalidated candidateだが、active pipelineへは未切替。

旧serial/parallel referenceも削除しない。

---

## 10. 次の入力BAM

Stage 15Aで使う第一候補はtarget 100k BAM。

```text
/mnt/intelssd/rnatr_project/results/11_mapping/ENCSR307SHM_pilot100k_mm2splice_v1/ENCSR307SHM_pilot100k_mm2splice_v1.sorted.bam
```

SHA-256:

```text
0b1ec4e051ac1067fe7207c076e1eff10e45335b49190902944496a9461300e6
```

Index:

```text
/mnt/intelssd/rnatr_project/results/11_mapping/ENCSR307SHM_pilot100k_mm2splice_v1/ENCSR307SHM_pilot100k_mm2splice_v1.sorted.bam.bai
```

---

## 11. Stage 15Aの正確な目的

active pipelineを変更せず、隔離環境で次を一度に通す。

```text
100k mapping-complete BAM
    ↓
11b target assignment
    ↓
11d3 raw-read projection
    ↓
11e motif jobs
    ↓
native general caller v0.4.1
    ↓
materializer v0.1.2
    ↓
schema v0.4.2 package
    ↓
full validators / manifest / restartability / runtime
```

### 必須条件

- upstream 11b/11d3/11eの契約を勝手に変更しない
- frozen 100k artifactsと行数・ID集合・SHA/semantic invariantsを比較
- 旧11f〜11k3は削除せずreferenceとして保持
- candidate outputは隔離root
- active pipelineはPASS後まで切り替えない
- native caller outputがdeterministic referenceと一致
- materialized packageがStage14K2 packageと一致、または差がある場合は原因を明示
- restart / resume / atomic rename / manifestを検証
- BAM-input end-to-end wall timeを実測
- 5.31M外挿を更新
- 30分target / 60分hard ceilingを維持

---

## 12. 速度上の次の課題

100kで概算:

```text
native caller       約18〜21秒
materializer        約68秒
package validator   約16秒
```

現在はcallerではなくmaterializationが主な律速。

Stage 15A以降で検討する候補:

- plain TSV + gzipの二重書き出し廃止
- streaming materialization
-全388,571行をPython dictとして保持しない
- output時にSHA/manifestを同時計算
- validatorのstreaming/incremental化
- read metadataの再利用
- FASTQ再走査の回避
-同一tableの再読込削減

完成版performance gate:

```text
5M reads級 mapping-complete BAM入力
target       <=30分
hard ceiling <=60分
```

FASTQ→finalはminimap2 mappingを別時間として報告する。

---

## 13. 6検体panelの扱い

6検体×100kはengineering sanity check専用。

使用可:

- pipeline再現性
- gross artifact
- 実装破綻
- 大きな検体間差
- runtime sanity

使用不可:

- 精密なtechnical uncertainty model
- RNA population normal range
- pathogenicity threshold
- locus/motif/length/support依存の精密背景分布

これらはソフト安定後の大規模cohortで行う。

---

## 14. 引き継ぎbundle

次スレへ再アップロードするbundle:

```text
rnatr_stage15a_bam_to_final_contract_bundle_v0.1.2.tar.gz
```

SHA-256:

```text
8af4e667b7448e9f0a6378447a3dc89f81d634eb44bb9e701ac41b455c4007de
```

bundleには以下を含む。

- current pipeline snapshot
- active source ledger
- target/equalized BAM candidate ledger
- native caller v0.4.1
- materializer v0.1.2
- schema promotion manifest
- release gates v0.2.2
- failure/materialization contract
- 5 output tablesのsample
- active 11b〜11k3 scripts

---

## 15. 次スレで最初に伝える文

以下を新スレ冒頭へ貼る。

> RNA-TR-Scout開発の続きです。添付の引き継ぎサマリーと`rnatr_stage15a_bam_to_final_contract_bundle_v0.1.2.tar.gz`を正として進めてください。Stage14L2までPASSし、deterministic native general caller v0.4.1、materializer v0.1.2、evidence schema v0.4.2はprepared motif/projection jobsからvalidated packageまで100kで検証済みです。ただしactive pipelineはまだ旧P0/P1系で、BAM-to-final 100kは未検証です。次はProで、target 100k BAMから11b→11d3→11e→native caller→schema v0.4.2 packageを隔離実行するStage15Aを設計してください。同時にmaterialization/validation速度を改善し、5M BAM-input 30分目標・60分hard ceilingを維持してください。full 5.31MはStage15A PASS後まで流しません。

---

## 16. モデル設定

次のStage 15Aは、pipeline architecture、重大なコード生成、regression設計、performance設計を同時に扱うため、**Pro推奨**。

Stage 15Aがfreezeした後の単純実行・ログ確認は「高い」へ戻してよい。
