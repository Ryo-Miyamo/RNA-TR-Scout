#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="rnatr_ssot_post_stage6am_update_v0.1.1"
PROJECT_ROOT="/mnt/intelssd/rnatr_project"
CLI="$PROJECT_ROOT/metadata/ssot/rnatr_ssot.py"
SSOT_DB="$PROJECT_ROOT/metadata/ssot/rnatr_ssot.sqlite"
SCRIPT_INSTALL="$PROJECT_ROOT/scripts/00b_update_rnatr_ssot_after_stage6am_v0.1.1.sh"
STAGE6AM_ROOT="$PROJECT_ROOT/results/11_six_sample_frozen_p01_replay/ENCSR307SHM_pilot100k_mm2splice_v1/rnatr_six_sample_frozen_p01_replay_v0.1.5"
STAGE6AM_QC="$PROJECT_ROOT/qc/11_six_sample_frozen_p01_replay/ENCSR307SHM_pilot100k_mm2splice_v1/rnatr_six_sample_frozen_p01_replay_v0.1.5/six_sample_frozen_p01_replay.qc.tsv"
STAGE6AM_SUMMARY="$STAGE6AM_ROOT/six_sample_frozen_p01_replay.summary.tsv"
PROVENANCE="$STAGE6AM_ROOT/run_stage_provenance.tsv"

for p in "$CLI" "$SSOT_DB" "$STAGE6AM_QC" "$STAGE6AM_SUMMARY" "$PROVENANCE"; do
    [[ -s "$p" ]] || { echo "ERROR: missing required file: $p" >&2; exit 2; }
done

python - "$CLI" <<'PY'
from pathlib import Path
import sys, shutil, hashlib, datetime as dt, py_compile

cli = Path(sys.argv[1])
text = cli.read_text(encoding="utf-8")

if 'TOOL_VERSION = "rnatr_ssot_v0.1.2"' in text:
    print("SSOT_SOURCE_ALREADY_UPDATED")
    raise SystemExit(0)

if 'TOOL_VERSION = "rnatr_ssot_v0.1.1"' not in text:
    raise SystemExit("ERROR: unexpected SSOT source version; refusing automatic patch")

text = text.replace(
    'TOOL_VERSION = "rnatr_ssot_v0.1.1"',
    'TOOL_VERSION = "rnatr_ssot_v0.1.2"',
    1,
)

anchor = "    current_metrics = [\n"
if anchor not in text:
    raise SystemExit("ERROR: SSOT current_metrics anchor not found")

insertion = r'''    # Stage 6AM v0.1.5 completed successfully on 2026-08-07.
    stage6am_root = project_root / "results/11_six_sample_frozen_p01_replay/ENCSR307SHM_pilot100k_mm2splice_v1/rnatr_six_sample_frozen_p01_replay_v0.1.5"
    stage6am_qc = project_root / "qc/11_six_sample_frozen_p01_replay/ENCSR307SHM_pilot100k_mm2splice_v1/rnatr_six_sample_frozen_p01_replay_v0.1.5/six_sample_frozen_p01_replay.qc.tsv"
    stage6am_summary = stage6am_root / "six_sample_frozen_p01_replay.summary.tsv"
    stage6am_provenance = stage6am_root / "run_stage_provenance.tsv"

    conn.execute(
        """
        UPDATE open_questions
        SET status='CLOSED',
            blocking=0,
            next_action='Completed: Stage 6AM v0.1.5 passed all six equalized fetal-brain datasets with SSOT-verified scripts and validator_v0.3.1.',
            evidence_path=?,
            effective_at='2026-08-07T03:03:38+00:00'
        WHERE question_key='SIX_SAMPLE_REPLAY'
        """,
        (str(stage6am_qc),),
    )

    conn.execute(
        """
        INSERT OR REPLACE INTO open_questions(
            question_key,question,priority,status,blocking,next_action,evidence_path,effective_at
        ) VALUES(?,?,?,?,?,?,?,?)
        """,
        (
            'PERFORMANCE_OPTIMIZATION_11F_11H',
            'How should the production caller reduce runtime, especially in 11f periodic baseline and 11h target-constrained refinement, and where can CPU parallelization, compiled code, or GPU batching help?',
            'HIGH','OPEN',0,
            'After the current technical-calibration and general-caller contract reach a stable checkpoint, profile 11f/11h first; separate Python overhead, DP compute, repeated work, and I/O, then benchmark CPU parallel, compiled, and GPU implementations against the CPU reference.',
            str(stage6am_provenance),
            '2026-08-07T03:03:38+00:00',
        ),
    )

    conn.execute(
        """
        INSERT OR REPLACE INTO limitations(
            limitation_key,statement,severity,status,mitigation,evidence_path,effective_at
        ) VALUES(?,?,?,?,?,?,?)
        """,
        (
            'CURRENT_RUNTIME_NOT_PRODUCTION_SCALE',
            'The current frozen P0/P1 implementation requires roughly 10-12 minutes per 100k-read sample in full runs; 11f and 11h account for about 80% of measured stage runtime.',
            'HIGH','ACTIVE',
            'Keep the current implementation as the correctness reference, then profile and optimize after the caller contract is stabilized; prioritize elimination of duplicate computation, CPU parallelization/compiled code, and GPU suitability for batched periodic DP.',
            str(stage6am_provenance),
            '2026-08-07T03:03:38+00:00',
        ),
    )

    add_decision(
        conn,
        key='six_sample_replay_complete',
        category='project_state',
        title='Six-sample frozen P0/P1 replay complete',
        statement='Stage 6AM v0.1.5 completed all six equalized 100k-read fetal-brain PromethION comparison datasets with the SSOT-verified frozen pipeline and validator_v0.3.1.',
        status='ACTIVE',
        confidence='HIGH',
        rationale='All six samples passed 11b, raw-read projection, motif-job preparation, baseline/refinement/finalization, exact-span calibration, calibrated evidence, and v0.3.3 span normalization. ENCSR327TOR 11j was reconciled as an expected-count metadata-only issue; no algorithm recomputation was required.',
        evidence_path=str(stage6am_qc),
        effective_at='2026-08-07T03:03:38+00:00',
    )

    add_interpretation(
        conn,
        key='coarse_pipeline_yield_target_within_six_sample_panel',
        fact='The original target pilot has 49,793 final P0/P1 evidence rows and 23,867 exact-span rows; the six equalized comparison datasets span 46,160-53,509 final rows and 22,114-25,886 exact-span rows.',
        interpretation='At coarse pipeline-yield level, the target pilot is within the technical-comparison panel range and does not show a gross global assignment or P0/P1 evidence-yield imbalance.',
        do_not='Do not interpret coarse row-count similarity as evidence that individual repeat loci, repeat lengths, motifs, or biology are normal; locus- and motif-level comparison is the next gate.',
        confidence='HIGH',
        evidence_path=str(stage6am_summary),
        evidence_metrics={
            'target_final_evidence_rows':49793,
            'panel_final_evidence_min':46160,
            'panel_final_evidence_max':53509,
            'target_exact_span_rows':23867,
            'panel_exact_span_min':22114,
            'panel_exact_span_max':25886,
        },
        status='ACTIVE',
        effective_at='2026-08-07T03:03:38+00:00',
    )

'''
text = text.replace(anchor, insertion + anchor, 1)

old_tuple = """        ("SIX_SAMPLE_REPLAY","Can the frozen P0/P1 pipeline be replayed across the six equalized fetal-brain datasets without mixing obsolete validators or implementations?","CRITICAL",1,
         "Resume only after this SSOT database validates the active pipeline and failure history.",str(project_root / "results/11_six_sample_frozen_p01_replay.stage6am_v0.1.1.console.log")),
"""
new_tuple = """        ("SIX_SAMPLE_REPLAY","Can the frozen P0/P1 pipeline be replayed across the six equalized fetal-brain datasets without mixing obsolete validators or implementations?","RESOLVED",0,
         "Completed in Stage 6AM v0.1.5; retain as closed historical gate.",str(project_root / "qc/11_six_sample_frozen_p01_replay/ENCSR307SHM_pilot100k_mm2splice_v1/rnatr_six_sample_frozen_p01_replay_v0.1.5/six_sample_frozen_p01_replay.qc.tsv")),
"""
if old_tuple not in text:
    raise SystemExit("ERROR: SIX_SAMPLE_REPLAY seed tuple not found")
text = text.replace(old_tuple, new_tuple, 1)

old_loop = '            (key,question,priority,"OPEN",blocking,next_action,evidence,"2026-08-06T00:00:00+00:00"),\n'
new_loop = '            (key,question,priority,("CLOSED" if priority=="RESOLVED" else "OPEN"),blocking,next_action,evidence,"2026-08-06T00:00:00+00:00"),\n'
if old_loop not in text:
    raise SystemExit("ERROR: open-question insertion loop not found")
text = text.replace(old_loop, new_loop, 1)

tmp = cli.with_name(cli.name + ".v0.1.2.part")
tmp.write_text(text, encoding="utf-8")
py_compile.compile(str(tmp), doraise=True)

backup_dir = cli.parent / "backups"
backup_dir.mkdir(parents=True, exist_ok=True)
stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
backup = backup_dir / f"rnatr_ssot.py.pre_v0.1.2.{stamp}"
shutil.copy2(cli, backup)
tmp.replace(cli)
cli.chmod(0o755)

print("SSOT_SOURCE_PATCH_PASS")
print(f"backup\t{backup}")
print(f"cli_sha256\t{hashlib.sha256(cli.read_bytes()).hexdigest()}")
PY

SELF="$(readlink -f "$0")"
if [[ "$SELF" != "$SCRIPT_INSTALL" && ! -e "$SCRIPT_INSTALL" ]]; then
    cp "$SELF" "$SCRIPT_INSTALL.part"
    chmod 0755 "$SCRIPT_INSTALL.part"
    mv "$SCRIPT_INSTALL.part" "$SCRIPT_INSTALL"
fi

echo "===== REBUILD SSOT AFTER STAGE 6AM ====="
python "$CLI" --project-root "$PROJECT_ROOT" rebuild

echo
echo "===== VALIDATE ====="
python "$CLI" --project-root "$PROJECT_ROOT" validate

echo
echo "===== CURRENT OPEN QUESTIONS ====="
python "$CLI" --project-root "$PROJECT_ROOT" show questions

echo
echo "===== PERFORMANCE RECORD ====="
python "$CLI" --project-root "$PROJECT_ROOT" query \
  "SELECT limitation_key,severity,statement,mitigation FROM current_known_limitations WHERE limitation_key='CURRENT_RUNTIME_NOT_PRODUCTION_SCALE'"

echo
echo "===== STAGE 6AM DECISION ====="
python "$CLI" --project-root "$PROJECT_ROOT" query \
  "SELECT decision_key,statement,confidence FROM current_decisions WHERE decision_key='six_sample_replay_complete'"

echo
echo "SSOT_STAGE6AM_UPDATE_PASS"
