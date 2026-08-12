# RNA-TR-Scout Stage 15A 設計
## 100k mapping-complete BAM → schema v0.4.2 validated package（隔離統合）

**設計版:** `rnatr_stage15a_bam_to_final_isolated_design_v0.1.1`  
**対象run:** `ENCSR307SHM_pilot100k_mm2splice_v1`  
**基準:** Stage 14L2 handover + `rnatr_stage15a_bam_to_final_contract_bundle_v0.1.2.tar.gz`  
**active pipeline switch:** Stage 15A PASSまでは禁止  
**full 5.31M:** Stage 15A PASSまでは実行禁止

---

## 1. 結論

Stage 15Aは、単一の長いshell scriptとしてactive tree上で走らせず、次の二本立てにする。

1. **Reference/replay lane**
   - frozen 11b → 11d3 → 11e
   - validated native general caller v0.4.1
   - materializer v0.1.2
   - frozen schema v0.4.2 validators
   - Stage 14K2 packageとの厳密な回帰比較

2. **Performance-candidate lane**
   - upstream/callerの意味論は変更しない
   - callerのexecution sharding、partitioned materialization、fused/streaming validationを使用
   - reference laneとkeyed semantic equalityを要求
   - production相当のwall timeとして計測する

Stage 15A全体のPASSは、**reference correctness、performance-candidate semantic parity、restartability、atomic publication、5.31Mへの保守的外挿が60分以内**をすべて満たす場合に限る。30分は正式なtargetとして別に`TARGET_MET / TARGET_NOT_MET`を報告する。

---

## 2. 添付bundleの監査結果

添付archiveのSHA-256は、handover記載値と一致した。

```text
8af4e667b7448e9f0a6378447a3dc89f81d634eb44bb9e701ac41b455c4007de
```

bundleはStage 15Aの契約資料として有効だが、単独で実行可能なself-contained bundleではない。bundle外のhost artifactについて、実行前に存在・SHA・依存関係をfreezeする必要がある。

追加照合により、主要なhost pathは次まで特定できた。

```text
Original Stage 14 caller integration driver:
/mnt/intelssd/rnatr_project/results/14_general_caller_100k_integration/
  ENCSR307SHM_pilot100k_mm2splice_v1/v0.1.0/
  run_general_caller_100k_integration.py

Stage 14G deterministic native v0.4.1 integration driver（parity fixture）:
/mnt/intelssd/rnatr_project/results/14_deterministic_general_caller/
  ENCSR307SHM_pilot100k_mm2splice_v1/v0.4.1_validation_v0.1.0/
  integration_native_100k/driver.py

Stage 14K promoted native v0.4.1 integration driver（Stage 15A exact glue）:
/mnt/intelssd/rnatr_project/results/14_v041_schema_v041_100k_end_to_end/
  ENCSR307SHM_pilot100k_mm2splice_v1/v0.1.0/
  run_native_v041_100k.py

Deterministic native v0.4.1 reference calls:
/mnt/intelssd/rnatr_project/results/14_deterministic_general_caller/
  ENCSR307SHM_pilot100k_mm2splice_v1/v0.4.1_validation_v0.1.0/
  integration_native_100k/general_repeat_calls.v0.4.0.tsv.gz

Schema v0.4.2 generic validator:
/mnt/intelssd/rnatr_project/config/evidence_schema/v0.4.2/
  rnatr_v042_validate_tsv.py

Schema v0.4.2 package validator:
/mnt/intelssd/rnatr_project/config/evidence_schema/v0.4.2/
  rnatr_v042_validate_package.py
```

一方、caller v0.4.1がimportする`rnatr_general_repeat_caller_ref_v0.2.1.py`、native runtime dependency、schema freeze manifest全member、Stage 14 package全member、上記glueの**実機上のSHA**はまだこの会話環境から確定できない。これはアルゴリズム不足ではなく、実行glueとvalidation closureをStage 15A contractへ含めるためのhost-side freezeである。最初にread-onlyのStage 15A0 preflightを実行し、exact pathの存在・SHA・caller reference parityを固定する。

---

## 3. 「BAM-input」の正確な定義

Stage 15AのBAM-input modeは、mappingを再実行しないという意味であり、BAM一個だけで完結するという意味ではない。

```text
required mapping-complete input bundle
  ├── sorted BAM
  ├── BAI
  ├── mapping run_manifest
  └── BAMに対応するraw-read FASTQ / sequence store
```

11d3は、secondary alignmentでBAM SEQが省略される場合、hard clipを含むfull raw-read coordinate、sequence/quality、orientation監査を復元するために対応FASTQを必要とする。したがってperformance reportは次のように表記する。

```text
BAM-to-final wall time
= mapping-complete BAM/BAI + associated raw-read sequence store から final packageまで

minimap2 mapping time
= 別建て
```

対象入力は固定する。

```text
BAM:
/mnt/intelssd/rnatr_project/results/11_mapping/
  ENCSR307SHM_pilot100k_mm2splice_v1/
  ENCSR307SHM_pilot100k_mm2splice_v1.sorted.bam

BAM SHA-256:
0b1ec4e051ac1067fe7207c076e1eff10e45335b49190902944496a9461300e6
```

---

## 4. 隔離方式

### 4.1 shadow project root

frozen upstream scriptはpathがactive `$PROJECT_ROOT/results/...`へhard-codeされている。アルゴリズム本体を改変せず、path plumbingだけを隔離するため、Stage 15A専用のshadow project rootを使う。

```text
$PROJECT_ROOT/results/15_stage15a_bam_to_final/$RUN_ID/v0.1.0/
  ├── contract/
  ├── frozen_scripts/
  ├── shadow_project.work/
  │   ├── config/
  │   │   ├── paths.env                 # Stage15A専用
  │   │   └── evidence_schema -> active read-only schema tree
  │   ├── results/
  │   │   ├── 11_mapping/$RUN_ID -> original mapping input, read-only
  │   │   ├── 11_assignment/
  │   │   ├── 11_projection/
  │   │   └── 11_motif_jobs/
  │   ├── qc/
  │   ├── tmp/
  │   └── raw_root/
  │       ├── .../rnatr_candidates...FASTQ -> original read-only FASTQ
  │       └── .../rnatr_projection.../  # isolated window FASTQ output
  ├── caller/
  ├── package_reference.part/
  ├── package_candidate.part/
  ├── comparison/
  ├── timing/
  └── logs/
```

active 11b/11d3/11e filesは直接編集しない。bundle/active ledgerのSHAとhost sourceのSHAが一致したことを確認後、Stage 15A rootへcopyし、**`paths.env`の参照先だけ**をshadow rootへ差し替える。差し替え前後のSHA、diff、許可された変更行をmanifestに保存する。

### 4.2 publication

final candidate packageは最初から`package/`へ書かない。

```text
package_candidate.part/
    ↓ all validators PASS
    ↓ fsync / manifest finalized
    ↓ atomic rename
package_candidate/
```

active production outputへのsymlink切替、copy、SSOT active flag変更はStage 15Aでは行わない。

---

## 5. Stage 15A gate構成

### 15A0 — Contract closure / read-only preflight

必須確認:

- target BAM/BAI/run manifest
- associated FASTQ
- catalog inputs
- frozen 11b/11d3/11e SHA
- caller v0.4.1、v0.2.1依存、native extension/runtime
- exact Stage 14K promoted native v0.4.1 integration driverの存在・CLI/output contract・SHA
- Stage 14G deterministic integration driver/reference calls/QC（parity fixture）
- Stage 14G deterministic validation QC `PASS`
- materializer v0.1.2
- schema v0.4.2 freeze manifest全member
- exact schema v0.4.2 generic/package validatorsとfreeze manifest全member
- Stage 14K2 package全10 artifact
- projection → motif jobの`projection_id` one-to-one/order lockstep
- frozen `general_repeat_calls`から抽出した77列caller suffix reference
- deterministic native v0.4.1 reference callsとのexact TSV parity
- disk/RAM/CPU/tool versions

**PASS条件:** critical artifact/format failureとSHA mismatchが0、Stage 14G deterministic validation QCが`PASS`、Stage 14K promoted native v0.4.1 integration driver contractがPASS、exact v0.4.2 validatorsが2本存在、frozen caller suffixが77列×388,571行、deterministic native reference callsとsuffixがexact一致、upstream lockstep contractが確認できること。

### 15A1 — Isolated 11b replay

実行:

```text
100k BAM → alignment_segments
         → alignment_target_candidates
         → read_target_candidates
```

比較:

- row counts
- header
- decompressed content SHA-256
- `alignment_id` / `read_id` / target key sets
- QC metric equality
- manifestはabsolute pathを除いてnormalizeして比較

**expected downstream cardinality:** `read_target_candidates = 388,571`

### 15A2 — Isolated 11d3 replay

実行:

```text
BAM + read_target_candidates + raw FASTQ
  → read_target_projection.v0.3.3.tsv.gz
  → target-window FASTQ
```

比較:

- projection 388,571 rows
- candidate reads 79,176
- projection ID set/order
- decompressed projection content SHA
- window FASTQ ID/sequence/quality equality
- hardclip/secondary/orientation QC equality

### 15A3 — Isolated 11e replay

実行:

```text
projection → motif_scan_jobs
           → motif dictionary
           → target summary
```

比較:

- 388,571 jobs
- projection ID one-to-one/order lockstep
- all classification fields exact
- decompressed content SHA
- QC metric equality

### 15A4 — Native caller v0.4.1 integration

Stage 14Kがpromoted native caller pathに対して生成し、caller outputのStage 14G deterministic reference parityを通した`run_native_v041_100k.py`をStage 15Aのexact production glueとして使用する。Stage 14Gの`integration_native_100k/driver.py`はdeterministic parity fixtureとして保持し、元のStage 14 integration driverをStage 15Aで再patchする方法はreference provenanceに限定する。algorithm fileを11eへ直接接続する新規glueはこのgateで発明しない。Stage 14K2はcallerを再実行せずvalidated callsを再利用したため、caller execution glueのfreeze対象はStage 14K driver、scientific referenceはStage 14G calls/QCという分担になる。

必須出力:

```text
77-column caller-attempt TSV.gz
one row per projection_id
388,571 rows
```

比較基準は、frozen Stage 14K2 `general_repeat_calls.tsv.gz`の先頭8 materialization columnsを除いた77列suffixである。

PASS条件:

- header exact
- row count 388,571
- projection ID set exact
- full 77-column TSV semantic SHA exact
- called attempts 160,315
- LOW_CONFIDENCE called 6,307
- hash seedを変えた二回目のcaller replayでもexact equality

production wall timeにはcaller一回だけを含め、二回目のdeterminism auditは別計上する。

### 15A5-R — Reference materialization

materializer v0.1.2をshadow projectへ向けて実行し、Stage 14K2 packageと比較する。

expected rows:

```text
general_repeat_calls  388,571
read_evidence         388,571
repeat_events         160,297
repeat_segments       161,265
repeat_interruptions      848
```

18件の`CALLED_NOT_RETAINED`、failure/QC/materialization contract、flank uniqueness `NOT_ASSESSED`を維持する。

### 15A5-P — Performance materialization candidate

reference v0.1.2の意味論を変えず、execution architectureだけを変更する。詳細は第9節。

PASS条件:

- 5 tablesのkeyed semantic equality
- caller 77列suffix lossless equality
- all FKs/cardinalities exact
- failure/QC/materialization semantics exact
- origin status `NOT_ASSESSED`
- clustering `NOT_RUN`
- peak RSSとwall timeを記録

### 15A6 — Validation

二段階で行う。

1. frozen validatorsをreference packageとcandidate packageの両方へ実行
2. fused/streaming validator candidateを実行し、frozen validatorのPASS/countsと一致させる

validator candidateだけのPASSではStage 15Aを通さない。

### 15A7 — Restartability / atomicity

故意に次の位置で一回ずつ中断可能にする。

- 11b後
- 11d3後
- caller shard途中
- materializer partition途中
- package write後・validation前

resume時は、input fingerprint、script SHA、parameter hash、output semantic hashを検証してからskipする。不一致artifactは上書きせず`quarantine/`へ移す。

### 15A8 — Runtime gate

production相当時間:

```text
T_BAM_TO_FINAL =
  T_11b
+ T_11d3
+ T_11e
+ T_caller_one_production_run
+ T_materializer_candidate
+ T_fused_validator_candidate
+ T_manifest_finalize
```

除外して別報告:

- preflight
- frozen artifact comparison
- second hash-seed caller run
- reference v0.1.2 materialization
- frozen validatorsによる二重監査
- minimap2 mapping

---

## 6. 回帰比較の定義

### 6.1 gzip raw SHAだけで判定しない

旧11b/11d3/11eはgzip metadataやwrite chunkによりraw `.gz` SHAが変わりうる。primary equalityは以下とする。

```text
1. decompressed byte SHA-256
2. row count
3. header
4. key set
5. required semantic invariants
```

raw gzip SHAも記録するが、単独ではFAIL理由にしない。

### 6.2 package candidate

performance materializerがrow orderやgzip member構成を変更する場合、各tableをschema-defined keyでcanonical sortしたlogical TSV hashを比較する。

```text
general_repeat_calls: caller_record_id / projection_id
read_evidence:        evidence_id
repeat_events:        evidence_id, event_index, repeat_event_id
repeat_segments:      evidence_id, repeat_event_id, segment_index, repeat_call_id
repeat_interruptions: evidence_id, repeat_event_id, interruption_index, interruption_id
```

値の差は一件でもFAIL。order/compression-only差はmanifestに明示する。

---

## 7. Stage 15AのPASS判定

```text
CORRECTNESS_PASS =
  15A0 + 15A1 + 15A2 + 15A3 + 15A4 + 15A5-R + 15A6 frozen validators

PERFORMANCE_IMPLEMENTATION_PASS =
  15A5-P semantic parity + fused validator parity + restartability + atomicity

PERFORMANCE_HARD_CEILING_PASS =
  conservative 5.31M projection <= 60 min

TARGET_STATUS =
  projected <= 30 min ? TARGET_MET : TARGET_NOT_MET

STAGE15A_PASS =
  CORRECTNESS_PASS
  AND PERFORMANCE_IMPLEMENTATION_PASS
  AND PERFORMANCE_HARD_CEILING_PASS
```

30分未達でも60分以内ならStage 15Aはcorrectness/production hard gateとしてPASS可能だが、release planning上は`TARGET_NOT_MET`を残し、30分達成のperformance workstreamを閉じない。

---

## 8. Runtime scaling

単純なread比は:

```text
5.31M / 100k = 53.1
```

したがって、完全線形なら100k相当budgetは:

```text
30 min target      = 33.90 sec / 100k
60 min hard ceiling = 67.80 sec / 100k
```

ただし最終外挿はstage-specific denominatorを使う。

```text
11b:          BAM alignment records / non-splice blocks
11d3, 11e:    projection attempts
caller:       attempted caller rows × sequence/window complexity
materializer: caller rows + event/segment/interruption rows + output bytes
validator:    table rows + bytes
```

caller-only 100k約21秒は、単純線形で約18.6–18.9分を消費する。30分targetでは残りが約11分しかないため、materializer/validatorだけでなく、**native callerのalgorithmを変えずにinput shardingで並列実行する余地**もStage 15Aで測定する。

一方、60分hard ceilingはprojectionだけでは最終証明にならない。Stage 15Aはfull runを許可するためのgateであり、G06/G07の実測証明はStage 15A PASS後の5.31Mで行う。

---

## 9. Materialization / validation速度改善設計

### 9.1 reference v0.1.2の律速

現在のv0.1.2は:

- callsとprojectionを全件`list[dict]`として保持
- evidence/event/segment/interruptionを全件Python dictとして保持
- global sort
- plain TSVを5表書く
- plainを再読込してgzipを5表逐次作る
- manifest用にplain/gzipを再読込してSHAを計算
- projectionに既に存在するread length/mean Qのためcandidate FASTQを再走査

という構造であり、100kで約68秒、5MではmemoryとI/Oの両方が危険である。

### 9.2 performance candidate: evidence-prefix partition architecture

candidateは`evidence_id`の先頭2 hex文字で256 partitionへ分ける。

```text
calls + projection lockstep stream
    ↓ compute evidence_id
partition 00 ... ff
    ↓ 16 workers
per-partition grouping/materialization/local sort/schema checks
    ↓ deterministic partition order 00 ... ff
final five tables + manifest
```

利点:

- 同一evidenceのattempt/event/segment/interruptionが必ず同一partition
- global all-row Python dict/list不要
- partition単位でmulti-attempt groupingを維持
- deterministic global orderはpartition順で得られ、全体sort不要
- worker再開が可能
- validatorの大部分をpartition内で同時実行可能
- peak RSSは全体row数ではなく最大partition row数に依存

### 9.3 lockstep join

projectionとmotif jobsは11e contract上one-to-oneで、Stage 15A0でorder lockstepを実証する。caller integrationも同順序を維持できる場合、callsとprojectionをzip streamし、388k/20M-row dictionary joinを廃止する。

lockstepが成立しない場合はsilent fallbackせず、外部sort/partition joinへ切り替え、その時間を明示する。

### 9.4 FASTQ再走査

11d3がすでにFASTQ completeness、read length、quality、orientationを監査しprojectionへ保持している。production candidateではmaterializerのFASTQ再走査をデフォルトで省き、次を採用する。

```text
--fastq-audit-mode upstream_attested   # production timing
--fastq-audit-mode independent         # reference/audit lane
```

upstream 11d3 manifest/QC SHAをmaterializer manifestへ参照として記録する。

### 9.5 outputとSHA

- plain TSVとgzipを同じlogical row streamから生成
- write中にSHA/row count/bytesを計算
- manifestのための全ファイル再読込を廃止
- gzipはdeterministic multi-member gzipをpartition並列生成し、00→ff順に連結可能
- `gzip -t`とfull decompressed semantic SHAを最後に一回だけ実施

Stage 15Aでは既存10-artifact packageを維持する。plain TSV廃止は別schema/package contract変更とし、このstageでは行わない。

### 9.6 fused validator

row-local schema/type/enum/required checksはworker内でmaterializationと同時に行う。cross-table関係は同一evidence partition内で完結させ、coordinatorは次だけを集約する。

- total counts
- partition range/order
- global IDs whose prefix determines partition
- package manifest
- contract counters
- frozen validator parity

frozen validatorsはStage 15A correctness gateとして残し、active switch前に削除しない。

---

## 10. 最初に実行するもの

最初の実行はfull integration runnerではなく、read-onlyのStage 15A0 contract preflightとする。

```bash
bash rnatr_stage15a_contract_preflight_v0.1.1.sh
```

このscriptはactive output、SSOT、full 5.31Mを変更せず、次を作る。

```text
qc/15_stage15a_contract_preflight/$RUN_ID/v0.1.1/
  stage15a_contract_preflight.qc.tsv
  stage15a_required_artifacts.tsv
  stage15a_input_format_checks.qc.tsv
  stage15a_caller_driver_contract.qc.tsv
  stage15a_discovered_components.tsv
  stage15a_environment.tsv
  stage15a_frozen_artifacts_and_lockstep.qc.tsv
  stage15a_contract_preflight.log
```

Stage 15A0でhost artifact SHA、exact integration driver、validator closure、deterministic reference parityをfreezeした後に、isolated shadow runnerを確定する。これは設計上の必須gateであり、active pipelineを先に動かすより安全で速い。

---

## 11. この設計版の実行境界

このbundleで直ちに実行するのは**Stage 15A0 read-only preflightだけ**である。11b以降を動かすrunnerは、preflightが記録したhost SHAとdriver contractを埋め込んだうえでv0.1.0として生成する。したがって、この時点では次を行わない。

```text
active 11b/11d3/11eの実行        NO
active outputの上書き             NO
schema v0.4.2へのactive switch     NO
SSOT更新                           NO
full 5.31M run                     NO
```

preflight PASS後のrunnerは、reference/replay laneとperformance-candidate laneを同一isolated rootに構築し、各gateのPASS artifactなしには次へ進まない構造とする。

