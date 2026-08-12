# RNA-TR-Scout Architecture Consistency Audit Contract v0.1.0

作成日: 2026-08-09  
状態: `ACTIVE_GOVERNANCE_CONTRACT`

## 1. 目的

RNA-TR-Scoutの主要checkpointで、個別stageのPASSだけでは見つけにくいarchitecture上の不整合を横断監査する。

監査対象:

```text
SSOT
active code / path
schema and frozen scientific contracts
performance gates
validation / restart / artifact contracts
biology roadmap and interpretation roadmap
script and implementation lifecycle
```

必須監査項目:

1. 仕様間の矛盾
2. obsoleteな設計・script・implementationの残存とlifecycle未分類
3. 未実装項目の実装済み扱い
4. freeze済みcontract・schema・validatorの意図しない変更
5. planned項目・release gate・biology roadmapの取りこぼし

## 2. 実施checkpoint

少なくとも以下で実施する。

```text
POST_250K_SCALING
PRE_BIOLOGY_LAYER_IMPLEMENTATION
PRE_RELEASE_CANDIDATE
```

大きなarchitecture変更、active pipeline promotion、schema contract変更の前後には追加監査してよい。毎stageでの実施は要求しない。

## 3. 判定語彙

```text
PASS       contractとevidenceが一致し、追加措置不要
REVIEW     blocking conflictはないが、明示的な追跡・修正・次gate確認が必要
CONFLICT   仕様・SSOT・実装・evidence間にblocking inconsistencyがある
OBSOLETE   historical provenanceとして保存するがcurrent/provisionalではない
OPEN       plannedまたは未検証であり、実装済み・PASSとして扱わない
```

`REVIEW`はStage全体のPASSを意味しない。`CONFLICT`が1件でもあれば次のmajor gateへ進まない。

## 4. Historical evidence amendment

過去QCの記載が実装で十分に証明されていない場合:

1. 過去QCを改変しない
2. original claimを`UNSUPPORTED_AS_IMPLEMENTED`として記録する
3. corrected auditをversioned amendmentとして追加する
4. SSOTではoriginal claimとreplacement evidenceの両方を追跡する

## 5. Script lifecycle

fileが存在するだけでactiveとはみなさない。各script/implementationは少なくとも以下のいずれかへ分類する。

```text
ACTIVE
PROVISIONAL
REFERENCE
SUPPORT
SUPERSEDED
OBSOLETE_FAILED_HISTORICAL
```

active pipelineは`current_pipeline`と実ファイルSHAの一致でのみ決める。

## 6. Post-250k checkpoint result

`post_250k_v0.1.1` audit:

```text
blocking_conflicts                         0
review_items                               3
open_items                                 2
architecture_audit_status                  REVIEW
replacement_checkpoint_logical_parity      PASS
```

主なREVIEW:

- external 250k runに対し内部component path/run IDが100k compatibility aliasを使用
- 5.31M linear projectionは59.858798分で、60分ceilingへのmarginが0.141202分のみ
- Stage15A script 3本がaudit時点でlifecycle未分類

主なOPEN:

- 250k selective resume、arbitrary upstream recovery、full-scale memory/restart
- deterministic 500k、empirical full-scale runtime、30分target、active promotion、G20–G23

## 7. 次gate

```text
register 250k result + checkpoint amendment + audit in SSOT
→ deterministic 500k scaling with corrected checkpoint comparison
→ reassess G06 / G07
```

full 5.31M、active pipeline switch、biology layer実装はまだ許可しない。
