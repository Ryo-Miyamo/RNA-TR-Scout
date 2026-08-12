# RNA-TR-Scout Core Technical Completion and Freeze Contract v0.1.2 — candidate

作成日: 2026-08-12  
状態: `LOCAL_CORE_FREEZE_ACCEPTANCE_CANDIDATE`  
Local Freeze profile: `LOCAL_CHECKSUMMED_CORE_FREEZE_V0.1.0`  
Planned public release: `v0.5.0`（未登録、Git未binding）

## 1. v0.1.2で解消する曖昧さ

旧v0.1.1は、科学Coreを固定してbiologyへ移るための条件と、clean install・GitHub
release・thesis-citable public versionの条件を一つにまとめていた。本v0.1.2では、
次の二つを明確に分離する。

1. **Local checksummed Core Freeze**  
   検証済みscientific/public Core contractを固定し、biology/performance sidecar laneを
   開始するための境界。
2. **Public/thesis-citable software release**  
   clean-machine install、reference bootstrap、cross-hardware、Git commit/tag、license、
   CITATION.cff等を満たして公開する境界。

Local Freeze成立を、未完のpublic packagingだけで不必要に遅らせない。一方でpublic
release未完を完成済みと表現しない。

## 2. Local Core Freezeで固定するもの

- deterministic native general caller v0.4.1のmeasurement semantics;
- materializer v0.1.2 semantics;
- evidence schema v0.4.2のfive-table contract;
- identity/join/missingness/censoring/context-limited semantics;
- portable result manifest and logical resource interface;
- validators, restart/resume, corruption rejection and atomic publication guarantees;
- canonical golden-protected scientific output;
- current validated profile and its exact resource SHA bindings.

内部Stage名、shard/worker数、内部順序、intermediate path、file handoff/streamingは、
applicable parity/guarantee gateを通る限り永久固定しない。

## 3. Local Freeze gate判定

| Gate | 判定候補 | 根拠 |
|---|---|---|
| Correctness / deterministic semantics | PASS | 100k/250k/500k、Tier1–3 golden |
| Empirical 5.31M BAM-to-final | PASS_WITH_DOCUMENTED_TOLERANCE | 60.041256352 min |
| Release-scale determinism | PASS_WITH_SCOPE_AMENDMENT | Stage15E checkpoint-based reconstruction scope |
| Restart/resume/publication | PASS_WITH_SCOPE_AMENDMENT | selective caller-to-final resume、corruption rejection、second no-op |
| Validators/memory/artifact audit | PASS | full-scale package validation and manifest evidence |
| PRE-RC/PRE-BIOLOGY/final architecture audit | PASS_WITH_SCOPE_AMENDMENT | Stage15P/Q/R/S and exact SSOT supplement |
| Freeze Packet / golden / canonical docs | PASS after guarded Stage15T registration | G32–G34 candidate assets |

Local Core Freeze candidate decision:

`LOCAL_CORE_FREEZE_V0.1.0_ACCEPTED_WITH_SCOPE`

## 4. Biologyとの境界

Freeze後にversioned sidecar/interpretation layerとして実装する。

- transcript / isoform state;
- haplotype state;
- observability and platform calibration;
- molecule independence / duplicate model;
- sample×locus summary;
- purpose-specific ranking;
- candidate dossier.

これらはimmutable Core result manifest SHAとread/evidence/locus identitiesへjoinし、Core
five tablesを書き換えない。

Candidate multiplicityはtechnical assignment countであり、独立biological event count
ではない。alignment confidence、alias/overlap、padding/proximityのbiology weightingは
post-Freezeで行う。

## 5. Local Freeze後も未完のpublic-release要件

- G25 version-pinned reference bootstrap;
- G26 resource detection;
- G27 memory-aware automatic concurrency;
- G28 supported hardware/concurrency間のlogical reproducibility;
- G29 independent clean-machine install;
- G30 minimum/recommended/tested hardware profiles;
- Git repository, full commit SHA and immutable tag;
- source archives/checksums, environment lock, CITATION.cff, CHANGELOG, LICENSE;
- final public v0.5.0 release.

これらはpublic/thesis-citable releaseをblockするが、local checksummed Core Freezeから
biology layerへ進むこと自体はblockしない。

## 6. 性能の正式表現

- Stage15C empirical 5,312,696-read BAM-to-final:
  `60.041256352 min / PASS_WITH_DOCUMENTED_TOLERANCE`;
- mapping time excluded;
- generic orchestrator v0.1.2のdirect empirical 5.31M measurementとは主張しない;
- 30-minute targetはpost-Freeze Performance laneに保持する。

## 7. Git/論文引用

本local Freeze時点ではGit bindingは `NOT_YET_BOUND`。したがって、次の引用形式は
public v0.5.0 release成立後にのみ使用する。

`RNA-TR-Scout v0.5.0 (full Git commit SHA; release date)`

Local Freezeは、その将来releaseで守るべきscientific Core contractを先に固定する。

## 8. 現在の承認手順

1. owner reviews final Packet candidate;
2. read-only Stage15T registration preflight;
3. guarded install/update with rollback;
4. SSOT rebuild/export and snapshot refresh;
5. Core Freeze manifest regeneration;
6. post-registration exact rehash and full-evidence golden verification;
7. register G24/G32–G34 scoped closure;
8. cleanup only by separate approval.
