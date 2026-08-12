# RNA-TR-Scout Core Technical Completion and Freeze Contract v0.1.0

作成日: 2026-08-09  
状態: `DESIGNED_NOT_YET_SATISFIED`  
Release profile: `CORE_TECHNICAL_COMPLETION_V1`  
Planned first core release tag: `v0.5.0`（release-candidate時に最終確認）

## 1. 目的

学生の修士論文を含む研究成果から、再現可能な固定software versionを引用できるよう、RNA-TR-Scoutの**core technical implementation**に明確な完了点を置く。

Core Technical Completionはbiology-ready completionとは分離する。以下はcore releaseの対象外であり、安定coreの上にversioned sidecar / interpretation layerとして後続実装する。

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

すべてrelease blockerである。

### CTC01 — Core correctness and deterministic scaling

- 100k BAM→final exact reference parity: PASS
- 250k dual-replicate package/caller/checkpoint logical determinism: PASS
- deterministic 500k dual-replicate scaling: PASS
- nested smaller-subset scientific parity: PASS
- formal run-ID contract: PASS

### CTC02 — Empirical full-scale runtime

5.31M級mapping-complete BAM入力について、mapping時間を含めず、associated raw-read sequence storeからのcandidate extractionを含むcore BAM-to-final wall timeを実測する。

```text
hard ceiling  <= 60 min   BLOCKING
target        <= 30 min   FORMAL TARGET, NON-BLOCKING AT FIRST CORE FREEZE
```

60分は線形外挿ではなく、full-scale empirical runでPASSすること。

### CTC03 — Release-scale determinism

次のどちらか、または同等以上の契約を満たす。

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

### CTC05 — Validators and artifact audit

- five generic TSV validators: PASS
- cross-table package validator: PASS
- flank uniqueness contract validator: PASS
- negative fixture failure parity: PASS
- output manifest rows/bytes/SHA: PASS
- peak memory / temporary bytes / final output bytes recorded

### CTC06 — Pre-release Architecture consistency audit

SSOT、active code/path、schema、performance gates、validation/restart contract、biology roadmapを横断する`PRE_RELEASE_CANDIDATE` auditを実施する。

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
known limitations and open performance target
```

Planned flow:

```text
v0.5.0-rc1 → pre-RC audit and clean-install validation → v0.5.0
```

Tagの付け替えは禁止する。release後の修正は新しいversion/tagにする。

## 4. 30分targetの扱い

30分は正式targetとして維持する。ただし、60分empirical PASS後に30分達成のため大規模なsemantic-risk architecture変更が必要と判断された場合、最初のcore releaseを遅らせない。

```text
60 min empirical PASS + all core blockers PASS
    → Core Technical Completion / v0.5.0 release可

30 min TARGET_NOT_MET
    → release notes / SSOT / thesis limitationsに明示
    → subsequent versionでoptimization継続
```

exact output parityを維持するexecution-only optimizationは`v0.5.x`候補とし、schema/ID/scientific semanticsを変える改造はminor versionを上げる。

## 5. Freeze後の変更規則

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

変更が必要な場合は、versioned migration、regression fixture、release gate、Architecture consistency auditを要求する。

## 6. Biology layerとの境界

biology / interpretation layerはcore package publication後に独立して実行可能とする。

```text
core_bam_to_final_runtime
biology_enrichment_runtime
interpretation_and_ranking_runtime
```

を別々に報告する。biology annotationやranking更新のためcore callerを再実行しない設計を原則とする。

## 7. 修士論文での引用要件

最低限、本文またはMethodsで次を記載できる状態にする。

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

DOI archiveを付与した場合はDOIも併記する。

## 8. 現在地

```text
100k correctness / performance          PASS
100k selective restart/resume           PASS
250k deterministic scaling              PASS
post-250k Architecture audit             REVIEW, blocking conflicts 0
500k deterministic scaling              NEXT
full 5.31M empirical runtime             OPEN
full-scale determinism                   OPEN
full-scale restart/resume                OPEN
pre-release Architecture audit           OPEN
Core Technical Completion                IN_PROGRESS
biology-ready implementation             NOT_STARTED / separate phase
```
