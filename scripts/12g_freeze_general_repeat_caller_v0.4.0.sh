#!/usr/bin/env bash
set -Eeuo pipefail

STAGE_VERSION="rnatr_general_repeat_caller_freeze_v0.4.0"
PROJECT_ROOT="/mnt/intelssd/rnatr_project"
CALLER="$PROJECT_ROOT/src/rnatr_scout/general_caller/rnatr_general_repeat_caller_ref_v0.4.0.py"
STAGE12E_QC="$PROJECT_ROOT/qc/12_general_repeat_caller_disease_sim/v0.4.0_stage12e_wrapper_v0.4.1/general_repeat_caller_stage12e.qc.tsv"
STAGE12F_QC="$PROJECT_ROOT/qc/12_general_repeat_caller_v03_v04_paired_regression_audit/v0.1.0/v03_v04_paired_real_regression.qc.tsv"
NOTE="$PROJECT_ROOT/docs/design/RNA_TR_Scout_general_repeat_caller_reference_v0.4.0.md"
SSOT_CLI="$PROJECT_ROOT/metadata/ssot/rnatr_ssot.py"
SSOT_DB="$PROJECT_ROOT/metadata/ssot/rnatr_ssot.sqlite"
OUTDIR="$PROJECT_ROOT/metadata/general_caller"
FREEZE_MANIFEST="$OUTDIR/general_repeat_caller_freeze_v0.4.0.tsv"
QC_DIR="$PROJECT_ROOT/qc/12_general_repeat_caller_freeze/v0.4.0"
QC="$QC_DIR/general_repeat_caller_freeze.qc.tsv"
SCRIPT_INSTALL="$PROJECT_ROOT/scripts/12g_freeze_general_repeat_caller_v0.4.0.sh"

expected_caller_sha="0be7a10b0dfa5d3ac5b062ae1e136bc7fd8e473cfd3d76ae2a32262f20e961c9"

for p in "$CALLER" "$STAGE12E_QC" "$STAGE12F_QC" "$NOTE" "$SSOT_CLI" "$SSOT_DB"; do
  [[ -s "$p" ]] || { echo "ERROR: required input missing: $p" >&2; exit 2; }
done

got_sha="$(sha256sum "$CALLER" | awk '{print $1}')"
[[ "$got_sha" == "$expected_caller_sha" ]] || { echo "ERROR: v0.4.0 caller SHA mismatch: $got_sha" >&2; exit 2; }

status12e="$(awk -F '\t' '$1=="audit_status"{print $2}' "$STAGE12E_QC" | tr -d '\015' | tail -n1)"
status12f="$(awk -F '\t' '$1=="audit_status"{print $2}' "$STAGE12F_QC" | tr -d '\015' | tail -n1)"
[[ "$status12e" == "PASS" ]] || { echo "ERROR: Stage 12E not PASS: $status12e" >&2; exit 2; }
[[ "$status12f" == "PASS" ]] || { echo "ERROR: Stage 12F not PASS: $status12f" >&2; exit 2; }

if [[ -s "$QC" ]] && awk -F '\t' '$1=="audit_status"{print $2}' "$QC" | tr -d '\015' | grep -qx PASS; then
  echo "STAGE12G_ALREADY_PASS"
  cat "$QC"
  exit 0
fi

mkdir -p "$OUTDIR" "$QC_DIR" "$(dirname "$SCRIPT_INSTALL")"

SELF="$(readlink -f "$0")"
if [[ "$SELF" != "$SCRIPT_INSTALL" && ! -e "$SCRIPT_INSTALL" ]]; then
  cp "$SELF" "$SCRIPT_INSTALL.part"
  chmod 0755 "$SCRIPT_INSTALL.part"
  mv "$SCRIPT_INSTALL.part" "$SCRIPT_INSTALL"
fi

python - "$STAGE12E_QC" "$STAGE12F_QC" "$CALLER" "$NOTE" "$FREEZE_MANIFEST" "$QC" <<'PY'
from pathlib import Path
import csv,sys,hashlib,os

s12e,s12f,caller,note,manifest,qc = map(Path,sys.argv[1:])

def q(path):
    with path.open(encoding="utf-8",newline="") as fh:
        return {r["metric"]:r["value"].rstrip("\r") for r in csv.DictReader(fh,delimiter="\t")}

def f(d,k): return float(d[k])
def i(d,k): return int(float(d[k]))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

e=q(s12e); a=q(s12f)
guards=[
    ("stage12e_pass",e.get("audit_status")=="PASS"),
    ("stage12f_pass",a.get("audit_status")=="PASS"),
    ("simple_periodic_regression",e.get("simple_periodic_regression")=="PASS"),
    ("compound_interruption_lps_regression",e.get("compound_interruption_lps_regression")=="PASS"),
    ("boundary_censor_denovo_regression",e.get("boundary_censor_denovo_regression")=="PASS"),
    ("disease_sim_benchmark",e.get("disease_sim_benchmark")=="PASS"),
    ("disease_motif_accuracy_1",f(e,"disease_exact_boundary_motif_accuracy")>=0.999),
    ("expansion_recovery_p10_ge_0.95",f(e,"expansion_stress_recovery_fraction_p10")>=0.95),
    ("censored_semantics",e.get("censored_semantic_invariants")=="PASS"),
    ("denovo_motif_accuracy_1",f(e,"denovo_motif_accuracy")>=0.999),
    ("compound_classification_1",f(e,"compound_classification_fraction")>=0.999),
    ("interruption_classification_1",f(e,"interruption_classification_fraction")>=0.999),
    ("real_regression_pass",e.get("real_regression_status")=="PASS"),
    ("paired_motif_changed_zero",i(a,"v03_v04_motif_changed_rows")==0),
    ("paired_majority_within_5bp",i(a,"v03_v04_within_5bp_rows")>=45),
]
bad=[name for name,ok in guards if not ok]
if bad: raise SystemExit("ERROR: freeze guard(s) failed: "+", ".join(bad))

manifest_rows=[
    ("freeze_id","GENERAL_REPEAT_CALLER_REF_V0.4.0"),
    ("freeze_status","FROZEN_REFERENCE"),
    ("caller_version","rnatr_general_repeat_caller_ref_v0.4.0"),
    ("caller_path",str(caller)),
    ("caller_sha256",sha(caller)),
    ("design_note_path",str(note)),
    ("design_note_sha256",sha(note)),
    ("stage12e_qc_path",str(s12e)),
    ("stage12f_qc_path",str(s12f)),
    ("disease_exact_boundary_motif_accuracy",e["disease_exact_boundary_motif_accuracy"]),
    ("disease_exact_boundary_abs_error_median_bp",e["disease_exact_boundary_abs_error_median_bp"]),
    ("disease_exact_boundary_abs_error_p95_bp",e["disease_exact_boundary_abs_error_p95_bp"]),
    ("expansion_stress_recovery_fraction_median",e["expansion_stress_recovery_fraction_median"]),
    ("expansion_stress_recovery_fraction_p10",e["expansion_stress_recovery_fraction_p10"]),
    ("denovo_motif_accuracy",e["denovo_motif_accuracy"]),
    ("compound_classification_fraction",e["compound_classification_fraction"]),
    ("interruption_classification_fraction",e["interruption_classification_fraction"]),
    ("paired_real_rows",a["paired_rows"]),
    ("paired_v03_v04_within_5bp_rows",a["v03_v04_within_5bp_rows"]),
    ("paired_v04_more_than_20bp_longer_rows",a["v04_more_than_20bp_longer_rows"]),
    ("paired_v04_new_context_limited_rows",a["v04_new_context_limited_rows"]),
    ("paired_v03_v04_motif_changed_rows",a["v03_v04_motif_changed_rows"]),
    ("interpretation","V0.4_IS_FROZEN_AS_MEASUREMENT_REFERENCE;_OLD_P0P1_IS_NOT_TRUTH;_PROJECTION_WINDOW_EDGE_EXTENSIONS_REMAIN_LOWER_BOUNDS"),
    ("pathogenicity_semantics","NOT_ASSESSED"),
    ("population_normal_range_semantics","NOT_ESTIMATED"),
    ("next_gate","PRODUCTION_INTEGRATION_AND_PERFORMANCE_PROFILING"),
]
manifest.parent.mkdir(parents=True,exist_ok=True)
tmp=manifest.with_name("."+manifest.name+".part")
with tmp.open("w",encoding="utf-8",newline="") as fh:
    w=csv.writer(fh,delimiter="\t"); w.writerow(["metric","value"]); w.writerows(manifest_rows)
os.replace(tmp,manifest)

qc_rows=[
    ("stage_version","rnatr_general_repeat_caller_freeze_v0.4.0"),
    ("caller_sha256",sha(caller)),
    ("freeze_status","FROZEN_REFERENCE"),
    ("simulation_semantics","MEASUREMENT_VALIDATION_NOT_PATHOGENICITY_NOT_POPULATION_CALIBRATION"),
    ("real_regression_semantics","SOFTWARE_REGRESSION_ONLY_FROZEN_P0P1_NOT_BIOLOGICAL_TRUTH"),
    ("boundary_tradeoff_decision","KEEP_V04_EXPANSION_RECOVERY_AND_USE_CONTEXT_LIMITED_LOWER_BOUND_RATHER_THAN_FORCE_AGREEMENT_TO_V03"),
    ("performance_optimization","NEXT"),
    ("production_integration","NEXT"),
    ("audit_status","PASS"),
]
qc.parent.mkdir(parents=True,exist_ok=True)
tmp=qc.with_name("."+qc.name+".part")
with tmp.open("w",encoding="utf-8",newline="") as fh:
    w=csv.writer(fh,delimiter="\t"); w.writerow(["metric","value"]); w.writerows(qc_rows)
os.replace(tmp,qc)

print("===== FREEZE GUARDS =====")
for name,ok in guards: print(f"{name}\t{'PASS' if ok else 'FAIL'}")
print("FREEZE_MANIFEST\t"+str(manifest))
print("FREEZE_QC\t"+str(qc))
PY

echo "===== SSOT UPDATE ====="
CLI_BAK="$SSOT_CLI.pre_stage12g.$(date +%Y%m%d_%H%M%S).bak"
DB_BAK="$SSOT_DB.pre_stage12g.$(date +%Y%m%d_%H%M%S).bak"
cp -a "$SSOT_CLI" "$CLI_BAK"
cp -a "$SSOT_DB" "$DB_BAK"

restore_ssot() {
  rc=$?
  echo "ERROR: Stage 12G SSOT update failed; restoring backups" >&2
  cp -a "$CLI_BAK" "$SSOT_CLI"
  cp -a "$DB_BAK" "$SSOT_DB"
  exit "$rc"
}
trap restore_ssot ERR

python - "$SSOT_CLI" <<'PYSSOT'
from pathlib import Path
import sys,py_compile,hashlib
cli=Path(sys.argv[1]); text=cli.read_text(encoding="utf-8")
marker="# Stage 12G freeze general repeat caller v0.4.0"
if marker in text:
    print("SSOT_STAGE12G_SOURCE_ALREADY_PATCHED")
    raise SystemExit(0)
required=["# Stage 12D boundary/censor/de-novo reference v0.3.0","def add_decision(","def add_interpretation(","def add_contract(","CREATE TABLE open_questions","CREATE TABLE limitations"]
missing=[x for x in required if x not in text]
if missing: raise SystemExit("ERROR: SSOT structural preflight failed: "+", ".join(missing))
anchor="    current_metrics = [\n"
if text.count(anchor)!=1: raise SystemExit("ERROR: SSOT current_metrics anchor not unique")
insertion=r'''    # Stage 12G freeze general repeat caller v0.4.0
    general_ref_v04 = project_root / "src/rnatr_scout/general_caller/rnatr_general_repeat_caller_ref_v0.4.0.py"
    general_ref_v04_note = project_root / "docs/design/RNA_TR_Scout_general_repeat_caller_reference_v0.4.0.md"
    general_ref_v04_freeze = project_root / "metadata/general_caller/general_repeat_caller_freeze_v0.4.0.tsv"
    stage12e_qc = project_root / "qc/12_general_repeat_caller_disease_sim/v0.4.0_stage12e_wrapper_v0.4.1/general_repeat_caller_stage12e.qc.tsv"
    stage12f_qc = project_root / "qc/12_general_repeat_caller_v03_v04_paired_regression_audit/v0.1.0/v03_v04_paired_real_regression.qc.tsv"

    conn.execute("UPDATE open_questions SET status='CLOSED', blocking=0, next_action='General repeat caller reference v0.4.0 frozen after backward regression, disease-inspired/broad simulation benchmark, short-prior expansion stress test, and paired v0.3/v0.4 real-read software regression.', evidence_path=?, effective_at='2026-08-07T07:15:00+00:00' WHERE question_key IN ('GENERAL_REPEAT_CALLER_CONTRACT','GENERAL_REPEAT_CALLER_IMPLEMENTATION')", (str(general_ref_v04_freeze),))
    conn.execute("UPDATE open_questions SET status='OPEN', blocking=1, next_action='Profile the current production path, especially 11f periodic baseline and 11h refinement, then design integration of frozen general caller v0.4.0. Measure Python/DP/I-O shares before choosing CPU compiled or GPU acceleration.', evidence_path=?, effective_at='2026-08-07T07:15:00+00:00' WHERE question_key='PERFORMANCE_OPTIMIZATION_11F_11H'", (str(general_ref_v04_freeze),))
    conn.execute('INSERT OR REPLACE INTO limitations(limitation_key,statement,severity,status,mitigation,evidence_path,effective_at) VALUES(?,?,?,?,?,?,?)', ('V04_LONG_EXTENSION_CONFIDENCE','Reference v0.4.0 intentionally permits locus-anchored tract extension beyond a short projected prior. In the 60-row software regression, 10 calls were >20 bp longer than v0.3; five newly reached projection-window context edges. These differences are not evidence of biological error because the frozen P0/P1 caller is not truth.','MEDIUM','ACTIVE','Keep v0.4.0 expansion recovery. Treat projection-window edge calls as context-limited lower bounds, retain purity and boundary/context metadata, and validate selected long-extension cases on full raw reads or orthogonal truth in later benchmark work.',str(stage12f_qc),'2026-08-07T07:15:00+00:00'))
    add_decision(conn,key='general_repeat_caller_reference_v0_4_0_frozen',category='algorithm_design',title='General repeat caller v0.4.0 frozen',statement='Freeze rnatr_general_repeat_caller_ref_v0.4.0 as the measurement reference implementation. Preserve locus-anchored geometric expansion for recovery of repeats longer than the projected prior; do not force agreement to the legacy P0/P1 caller.',status='ACTIVE',confidence='HIGH',rationale='Backward regressions passed. The 122-case benchmark completed 100%, disease-inspired exact-boundary motif accuracy was 100%, short-prior expansion recovery median was ~100.3% with P10 100%, censoring invariants passed, and de-novo/compound/interruption classification metrics were 100%. Paired real-read comparison showed 50/60 v0.3/v0.4 calls within 5 bp and zero motif changes; projection-window edge extensions are represented as context-limited lower bounds.',evidence_path=str(general_ref_v04_freeze),effective_at='2026-08-07T07:15:00+00:00')
    add_interpretation(conn,key='v04_boundary_tradeoff_stage12f',fact='In the paired 60-row v0.3/v0.4 software regression, 50/60 calls were within 5 bp, 10 were >20 bp longer in v0.4, nine had >25 bp additional extension, five newly reached projection-window context edges, and zero changed motif identity.',interpretation='The observed v0.4 extension tradeoff does not justify truncating the caller back toward the legacy implementation. Simulation truth demonstrates that larger search windows are required to recover repeats substantially longer than the projected prior, while context-edge calls already have lower-bound semantics.',do_not='Do not treat legacy P0/P1 repeat length as ground truth, do not interpret the 60-row set as a biological normal range, and do not infer pathogenicity from the simulated disease-inspired motifs.',confidence='HIGH',evidence_path=str(stage12f_qc),evidence_metrics={'paired_rows':60,'within_5bp':50,'v04_gt20bp_longer':10,'additional_extension_gt25bp':9,'new_context_limited':5,'motif_changed':0},status='ACTIVE',effective_at='2026-08-07T07:15:00+00:00')
    add_contract(conn,key='repeat_definition',name='Repeat definition and sizing',state='FROZEN_REFERENCE_V0.4.0',statement='Frozen reference v0.4.0 uses locus-core motif anchoring followed by geometric tract expansion, raw-read cyclic error-aware sizing, compound/interruption segmentation, and dual LPS semantics. Expansion beyond the projected prior is permitted when the locus remains overlapped; projection-window edges yield context-limited lower bounds.',implementation_id=None,evidence_path=str(general_ref_v04_note))
    add_contract(conn,key='general_caller_freeze',name='General repeat caller freeze',state='FROZEN_V0.4.0',statement='General caller measurement semantics are frozen for production-integration and performance work. Subsequent optimization must preserve v0.4.0 call semantics and pass frozen regression/benchmark gates.',implementation_id=None,evidence_path=str(general_ref_v04_freeze))
'''
text=text.replace(anchor,insertion+anchor,1)
tmp=cli.with_name("."+cli.name+".stage12g.part")
tmp.write_text(text,encoding="utf-8"); py_compile.compile(str(tmp),doraise=True); tmp.replace(cli); cli.chmod(0o755)
print("SSOT_STAGE12G_SOURCE_PATCH_PASS")
print("ssot_cli_sha256\t"+hashlib.sha256(cli.read_bytes()).hexdigest())
PYSSOT

python "$SSOT_CLI" --project-root "$PROJECT_ROOT" rebuild
python "$SSOT_CLI" --project-root "$PROJECT_ROOT" validate
trap - ERR

echo
echo "===== STAGE 12G COMPLETE ====="
cat "$QC"
echo
echo "Freeze manifest: $FREEZE_MANIFEST"
echo "Caller:          $CALLER"
echo "STAGE12G_PASS"
