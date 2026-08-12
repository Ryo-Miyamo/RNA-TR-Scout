# RNA-TR-Scout Core Technical Completion and Freeze Contract v0.1.1

作成日: 2026-08-09  
状態: `DESIGNED_NOT_YET_SATISFIED`  
Release profile: `CORE_TECHNICAL_COMPLETION_V1`  
Planned first core release tag: `v0.5.0`（release-candidate時に最終確認）

## 1. 目的とphase境界

学生の修士論文を含む研究成果から、再現可能な固定software versionを引用できるよう、RNA-TR-Scoutのcore technical implementationに明確な完了点を置く。

Core Technical Completionはbiology-ready completionとは分離する。以下は安定coreの上にversioned sidecar / interpretation layerとして後続実装する。

```text
transcript / isoform state
haplotype state
observability sidecar
molecule independence / duplicate model
sample×locus biology summary
purpose-specific candidate ranking
researcher-facing candidate dossier
```

## 2. Freeze対象となるcore

```text
mapping-complete sorted BAM + BAI
+ associated raw-read sequence store
+ immutable target/catalog/reference contract
    ↓
target assignment
    ↓
raw-read coordinate projection
    ↓
motif-job formation
    ↓
deterministic native general caller v0.4.1
    ↓
evidence schema v0.4.2 materialization
    ↓
5-table validation / package validation
    ↓
atomic final package
```

Core source of truth:

```text
general_repeat_calls
read_evidence
repeat_events
repeat_segments
repeat_interruptions
```

Current frozen semantic components:

```text
scientific caller       deterministic native general caller v0.4.1
materialization base    v0.1.2 semantics
core evidence schema    v0.4.2
failure/QC/materialization contract  frozen Stage14L2 contract
```

## 3. Core Freezeの必須gate

### CTC01 — Core correctness and deterministic scaling

- 100k BAM→final exact reference parity: PASS
- 250k dual-replicate package/caller/checkpoint logical determinism: PASS
- deterministic 500k dual-replicate scaling: PASS
- nested smaller-subset scientific parity: PASS
- formal run-ID contract: PASS

### CTC02 — Empirical full-scale runtime

5.31M級mapping-complete BAM入力について、mapping時間を含めず、associated raw-read sequence storeからのcandidate extractionを含むcore BAM-to-final wall timeを実測する。

```text
engineering benchmark          <= 60.0 min
thesis/core-release tolerance  >60.0 and <=62.0 min
formal target                  <= 30.0 min
```

判定:

```text
<=60.0 min
    PASS_STRICT

>60.0 and <=62.0 min
    PASS_WITH_DOCUMENTED_TOLERANCE
    ただしCTC01/03–08がPASSし、swap/OOM、validator省略、
    不完全publication、再現性低下がないこと

>62.0 min
    FAIL_FOR_FIRST_CORE_FREEZE
```

60分は正式なengineering benchmarkとして維持する。1–2分程度の超過だけを理由に、修士論文用の最初のcore releaseを不必要に遅らせない。実測値とtolerance利用はSSOT、release notes、修士論文へ明記する。

30分は正式targetだが、最初のcore freezeではnon-blockingである。

### CTC03 — Release-scale determinism

次のいずれか、または同等以上を満たす。

1. full-scale BAM-to-final independent replicateのfinal package exact parity
2. full-scale frozen upstream checkpointから、異なるhash seedでcaller/materializer/finalizationを再実行し、caller logical parityと5-table exact logical parityを確認

500kだけのdeterminismをfull-scale determinismとして代用しない。

### CTC04 — Full-scale restart / resume

5.31M級runで意図的停止を入れ、以下を検証する。

```text
incomplete package is never published
checkpoint manifest integrity PASS
corrupted checkpoint is rejected
completed work is reused
missing work only is resumed
resumed final package equals clean final package
second resume is a no-op
atomic publication PASS
```

### CTC05 — Validators, bounded memory, and artifact audit

- five generic TSV validators: PASS
- cross-table package validator: PASS
- flank uniqueness contract validator: PASS
- negative fixture failure parity: PASS
- output manifest rows/bytes/SHA: PASS
- peak memory / temporary bytes / final output bytes recorded
- full-scale validation must complete without swap/OOM
- memory-bounded validator must be shown equivalent to the frozen validator on 100k and 500k positive fixtures plus versioned negative fixtures

A validator that is semantically correct at 500k but has an extrapolated memory requirement exceeding the host RAM is not full-scale ready.

### CTC06 — PRE_RELEASE_CANDIDATE Architecture consistency audit

```text
blocking conflicts = 0
release-blocking REVIEW items = 0
unimplemented items are not represented as implemented
frozen contracts have no unintended drift
obsolete/reference/provisional/active lifecycle is explicit
planned biology work remains preserved
```

### CTC07 — Promotion and clean-install reproducibility

- release candidateをisolated clean environmentから実行可能
- active production pathは明示的promotion gateを通過
- historical reference/audit laneは削除せず保持
- release artifactから同一version/commit/environmentを再構築可能

### CTC08 — Thesis-citable immutable release

GitHub releaseには最低限以下を含む。

```text
immutable semantic-version tag
full 40-character Git commit SHA
source archive checksums
release manifest with component/config/schema SHA-256
environment lock / dependency versions
benchmark input and reference checksums
CITATION.cff
CHANGELOG / release notes
LICENSE
known limitations and open 30-minute target
```

Planned flow:

```text
v0.5.0-rc1 → pre-RC audit and clean-install validation → v0.5.0
```

## 4. Freeze後の変更規則

Core Freeze後、次を無断で変更しない。

```text
core 5-table schema and required fields
ID-generation contract
caller field semantics
failure_code / qc_flags / materialization_status semantics
censoring / exact / context-limited distinction
mismatch / indel / interruption / purity / LPS separation
validator acceptance contract
atomic publication and restart contract
```

## 5. Biology layerとの境界

```text
core_bam_to_final_runtime
biology_enrichment_runtime
interpretation_and_ranking_runtime
```

を別々に報告する。biology annotationやranking更新のためcore callerを再実行しない設計を原則とする。

## 6. 修士論文での引用要件

```text
RNA-TR-Scout version: v0.5.0
Git commit: <full 40-character SHA>
release date: <YYYY-MM-DD>
repository: <GitHub repository>
core schema: v0.4.2
scientific caller: v0.4.1
```

推奨引用表現:

> RNA repeat analysis was performed using RNA-TR-Scout v0.5.0 (Git commit `<SHA>`; released `<DATE>`).

## 7. v0.1.1時点の現在地

```text
100k correctness / performance                   PASS
100k selective restart/resume                    PASS
250k deterministic scaling                       PASS
post-250k Architecture audit                     REVIEW, blocking conflicts 0
500k deterministic scaling                       PASS
500k formal run-ID contract                      PASS
500k checkpoint logical reproducibility          PASS
500k nested-250k scientific parity               PASS
5.31M linear runtime projection                  59.393 min
full-scale empirical runtime                     OPEN
full-scale memory-bounded package validation     OPEN / REQUIRED BEFORE RUN
full-scale determinism                           OPEN
full-scale restart/resume                        OPEN
pre-release Architecture audit                   OPEN
Core Technical Completion                        IN_PROGRESS
biology-ready implementation                     NOT_STARTED / separate phase
```
