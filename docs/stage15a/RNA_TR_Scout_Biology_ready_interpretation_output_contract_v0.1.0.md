# RNA-TR-Scout Biology-ready / Interpretation-ready Output Contract v0.1.0

作成日: 2026-08-08  
状態: `DESIGNED_NOT_IMPLEMENTED`  
適用範囲: evidence schema v0.4.2 core packageを保持したまま、RNA biologyと大規模candidate triageを可能にする追加出力契約  
非目標: 本契約はStage 15Aのscientific caller、core 5-table field semantics、active pipelineを変更しない

---

## 1. 結論

RNA-TR-Scoutの現在のcore 5-table packageは、repeat architectureについてはread-levelで十分にlosslessな**repeat-measurement source of truth**である。

一方、現packageだけでは以下を直接検証できない。

1. repeat architectureとtranscript / isoform / splice-junction stateの同一分子内対応
2. 同一haplotype内のRNA molecule間repeat heterogeneity
3. 5′/3′ truncation、mapping reachability、censoringなどを明示的に分離したobservability
4. PCR duplicate、RT duplicate、concatemer、chimera等を考慮したmolecule independence
5. 大量のraw repeat eventsを研究目的別に圧縮したsample×locus summary、ranking、researcher-facing dossier

したがって、core 5-tableを肥大化させず、`read_id` / `evidence_id` / `repeat_event_id`でjoin可能なversioned sidecarとderived interpretation layerを追加する。

---

## 2. 変更しないcore source of truth

evidence schema v0.4.2の以下5表は、repeat measurementの正本として維持する。

```text
general_repeat_calls
read_evidence
repeat_events
repeat_segments
repeat_interruptions
```

保持すべきread/molecule-level情報には、少なくとも以下を含む。

```text
repeat length: exact / lower bound / interval / context-limited
canonical and oriented motif
purity
LPS exact-sequence / inferred
compound repeat segments
structured interruptions
mismatch / insertion / deletion
evidence geometry
left/right boundary status
censoring and sequence-edge contact
alternative motif hypothesis
assignment and competing-locus context
```

`repeat_events`はread/molecule-level repeat distributionのsource of truthであり、sample-level summaryやrankingのために破棄・上書きしない。

---

## 3. Biology join sidecars

すべてのsidecarはversioned schema、explicit missingness、source provenanceを持つ。未評価値は推測で埋めず、`NOT_ASSESSED`、`NOT_AVAILABLE`、`AMBIGUOUS`等を明示する。

### 3.1 `read_transcript_state.tsv.gz`

主キー候補:

```text
run_id + sample_id + read_id + transcript_assignment_id
```

必須候補フィールド:

```text
read_id
gene_id
transcript_id
transcript_name
isoform_assignment_status
junction_chain
splice_junction_count
intron_retention_status
cryptic_splice_status
alternative_first_exon_status
alternative_last_exon_status
polyadenylation_site
transcript_5prime_complete
transcript_3prime_complete
assignment_method
assignment_confidence
assignment_flags
source_annotation_version
```

同一readに複数のtranscript hypothesisがある場合は、単一値へ潰さずranked hypothesesとして保持する。

### 3.2 `read_haplotype_state.tsv.gz`

主キー候補:

```text
run_id + sample_id + read_id + phase_assignment_id
```

必須候補フィールド:

```text
read_id
phase_block_id
haplotype_label
informative_variant_count
informative_variants
phase_source
phase_method
phase_confidence
phase_status
phase_flags
matched_dna_sample_id
```

guardrail:

- phase evidenceなしにallele 1/2、maternal/paternal、normal/expandedと呼ばない
-初期ラベルは中立な`H1`, `H2`, `UNPHASED`, `AMBIGUOUS`
- matched DNA、SNP phasing、orthogonal evidenceがある場合のみ意味付けを昇格する

### 3.3 `read_observability.tsv.gz`

主キー候補:

```text
run_id + sample_id + evidence_id
```

必須候補フィールド:

```text
read_id
evidence_id
locus_id
platform
library_method
target_reachable
left_flank_reachable
right_flank_reachable
repeat_fully_observable
observed_interval_start
observed_interval_end
expected_transcript_position
five_prime_truncation_status
three_prime_end_status
censoring_class
context_limited
mapping_ambiguity_status
sequence_quality_status
observability_status
observability_flags
```

repeat lengthの欠測・lower boundと、真の短いrepeatを混同しないためのsidecarである。

### 3.4 `read_molecule_independence.tsv.gz`

主キー候補:

```text
run_id + sample_id + read_id
```

必須候補フィールド:

```text
read_id
molecule_family_id
independence_status
duplicate_class
duplicate_group_id
umi
rt_duplicate_status
pcr_duplicate_status
concatemer_status
chimera_status
strand_switch_status
independence_confidence
independence_flags
deduplication_method
```

guardrail:

- `read_id`を自動的に独立biological moleculeとみなさない
- UMIなしのcDNAでは完全なduplicate解決を主張しない
- deduplication前後の分布を両方追跡可能にする

---

## 4. Derived molecule-level biology view

### 4.1 `molecule_repeat_state.tsv.gz`

core repeat tablesと4 sidecarをjoinした研究用view。

粒度:

```text
one row per sample × molecule/read × locus × repeat event
```

最低限保持するもの:

```text
repeat architecture
transcript/isoform state
haplotype state
observability state
molecule independence state
all source IDs
join completeness flags
```

研究上の主要query:

> 同一haplotypeに属するRNA molecule間でrepeat length、purity、LPS、interruptions、compound architectureが異なるか。その差がsplice junction、isoform、intron retention、polyadenylation等と対応するか。

このqueryを可能にするため、molecule-level distributionをsample/locus summary作成後も必ず保持する。

---

## 5. Interpretation hierarchy

raw evidenceを直接candidate数として扱わない。次の階層をversionedに構築する。

```text
core raw caller attempt / repeat event
    ↓
molecule-level repeat state
    ↓
sample × locus distribution summary
    ↓
purpose-specific ranking lanes
    ↓
researcher-facing candidate dossier
```

### 5.1 `sample_locus_summary.tsv.gz`

最低限の内容:

```text
sample_id
locus_id
known_disease_locus_status
total_supporting_reads
independent_molecule_count
exact_observation_count
lower_bound_count
context_limited_count
observable_molecule_count
repeat_length_exact_distribution
repeat_length_lower_bound_distribution
purity_distribution
LPS_distribution
interruption_architecture_summary
heterogeneity_metrics
haplotype_stratified_summary
isoform_stratified_summary
technical_confidence_summary
summary_flags
```

exact、lower bound、context-limitedをnaiveに同一分布へ混ぜない。

### 5.2 `candidate_ranking_lanes.tsv.gz`

単一の総合scoreを唯一の順位として採用しない。少なくとも以下のlaneを独立に持つ。

```text
KNOWN_DISEASE
EXPANSION_DISCOVERY
RNA_PROCESSING
REPEAT_HETEROGENEITY
HAPLOTYPE_CONTROLLED
TECHNICAL_CONFIDENCE
```

各行:

```text
sample_id
locus_id
ranking_lane
lane_score
lane_rank
eligibility_status
supporting_feature_json
penalty_feature_json
ranking_model_id
ranking_model_version
ranking_flags
```

原則:

- known disease repeatは閾値にかかわらず`KNOWN_DISEASE` laneで保持する
- technical confidenceはbiology scoreの代替にしない
- purpose-specific lane間のscoreを直接比較しない
- pathogenicity scoreとは呼ばない

### 5.3 `candidate_dossier.jsonl.gz`

各sample×locusについて、研究者がraw TSVを手作業で辿らなくても監査できるdossierを作る。

内容:

```text
candidate identity
ranking lanes
known-disease annotation
sample×locus distribution
representative molecule/event IDs
haplotype-stratified evidence
isoform/splicing-stratified evidence
observability caveats
duplicate/independence caveats
IGV / read-level artifact links
all source table and schema versions
```

dossierから必ずcore rowへ逆追跡できることを要求する。

---

## 6. Readiness audit

現在のv0.4.2 core packageに対する暫定判定:

| 領域 | 現状 |
|---|---|
| repeat length / purity / LPS / interruptions / censoring | `READY_AS_CORE_SOURCE_OF_TRUTH` |
| read-level distribution preservation | `READY` |
| transcript / isoform state | `NOT_IMPLEMENTED` |
| haplotype state | `NOT_IMPLEMENTED` |
| explicit observability sidecar | `PARTIALLY_INFERABLE_BUT_NOT_MATERIALIZED` |
| duplicate / molecule independence | `NOT_IMPLEMENTED` |
| molecule-level joined biology view | `NOT_IMPLEMENTED` |
| sample×locus summary | `NOT_IMPLEMENTED` |
| purpose-specific ranking lanes | `NOT_IMPLEMENTED` |
| researcher-facing dossier | `NOT_IMPLEMENTED` |

したがって、現在のpackageは**repeat-ready**であるが、まだ**biology-ready / interpretation-ready**とは呼ばない。

---

## 7. Validation gates

### G20 Biology joinability

core repeat evidenceから、transcript、haplotype、observability、molecule independence sidecarへlosslessにjoinできる。

### G21 Molecule distribution preservation

molecule-level repeat distributionがsample summary後も保持され、exact/lower-bound/context-limitedが区別される。

### G22 Purpose-specific triage

複数ranking laneとknown-disease retentionが実装され、単一scoreへの過剰圧縮を行わない。

### G23 Dossier traceability

researcher-facing dossierの全主張がcore evidence、sidecar、summary、ranking model versionへ逆追跡できる。

これらはStage 15Aの250k performance scalingを阻害しないが、biology-ready v1 outputおよび大規模cohort triage開始前にはPASSを要求する。

---

## 8. Performanceとの分離

当面はruntimeを分けて報告する。

```text
core_bam_to_final_runtime
biology_enrichment_runtime
interpretation_and_ranking_runtime
```

core performanceの30分target / 60分hard ceilingを、annotationやcohort ranking処理で曖昧にしない。

sidecar生成はcore package publication後に独立再実行可能とし、core callerを再実行せずにannotation、phasing、transcript assignment、ranking modelを更新できる設計とする。

---

## 9. 実装順序

1. 本contractをSSOTへ登録し、G20–G23をOPENとして明示
2. Stage 15A restart/resumeとdeterministic 250k scalingを完了
3. 現core 5-tableを対象に正式なBiology-ready / interpretation-ready auditを実施
4. sidecar schemaとvalidatorをfreeze
5. molecule biology viewとsample×locus summaryを実装
6. purpose-specific ranking lanesをversionedに実装
7. candidate dossierとtraceability validatorを実装
8. truth-bearing disease / synthetic / orthogonal dataでbiology claimsを検証

---

## 10. 禁止事項

```text
core repeat eventsをsummaryだけに置換しない
read_idを無条件に独立moleculeと呼ばない
phase evidenceなしにallele/haplotypeへ生物学的意味を付けない
censored readをexact lengthとして集計しない
technical confidenceをpathogenicityと呼ばない
known-disease locusをgeneric ranking閾値で消さない
単一総合scoreだけで全研究目的を代表させない
sidecar欠測を陰性所見として扱わない
```
