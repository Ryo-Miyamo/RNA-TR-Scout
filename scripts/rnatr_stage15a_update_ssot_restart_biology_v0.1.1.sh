#!/usr/bin/env bash
set -Eeuo pipefail
umask 022

PROJECT_ROOT="/mnt/intelssd/rnatr_project"
RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"
UPDATE_VERSION="rnatr_stage15a_restart_biology_ssot_registration_v0.1.1"
# v0.1.1 fixes report-schema-aware active guard comparison and embedded-Python newline escaping.
SSOT_ROOT="$PROJECT_ROOT/metadata/ssot"
SSOT_CLI="$SSOT_ROOT/rnatr_ssot.py"
SSOT_DB="$SSOT_ROOT/rnatr_ssot.sqlite"
SSOT_SUMMARY="$SSOT_ROOT/CURRENT_STATE.md"
SSOT_EXPORTS="$SSOT_ROOT/exports"
SSOT_BACKUPS="$SSOT_ROOT/backups"
LOCK_PATH="$SSOT_ROOT/.stage15a_restart_biology_ssot_update.lock"

BASE_QC="$PROJECT_ROOT/qc/15_stage15a_bam_to_final/$RUN_ID/v0.2.3_restart_resume_100k"
BASE_RESULT="$PROJECT_ROOT/results/15_stage15a_bam_to_final/$RUN_ID/v0.2.3_restart_resume_100k"
RESTART_QC="$BASE_QC/stage15a_restart_resume_100k.qc.tsv"
PREPARE_QC="$BASE_QC/stage15a_restart_prepare.qc.tsv"
NOOP_QC="$BASE_QC/stage15a_restart_noop.qc.tsv"
PACKAGE_COMPARISON="$BASE_QC/comparison/stage15a_performance_package_comparison.tsv"
ACTIVE_BEFORE="$BASE_QC/contract/active_guards_before.tsv"
ACTIVE_AFTER="$BASE_QC/contract/active_guards_after.tsv"
SSOT_GUARDS_AFTER="$BASE_QC/contract/ssot_guards_after.tsv"
CHECKPOINT_MANIFEST="$BASE_RESULT/checkpoints/checkpoint_manifest.tsv"
PACKAGE_MANIFEST="$BASE_RESULT/package_resume/package_manifest.tsv"
RESTART_RUNNER="$PROJECT_ROOT/scripts/rnatr_stage15a_restart_resume_100k_v0.1.0.py"
RESTART_INSTALLER="$PROJECT_ROOT/scripts/rnatr_stage15a_restart_resume_100k_v010.sh"
CORE_SCHEMA="$PROJECT_ROOT/config/evidence_schema/v0.4.2/schema/rnatr_v04_table_schema.json"

SCRIPT_INSTALL="$PROJECT_ROOT/scripts/rnatr_stage15a_update_ssot_restart_biology_v0.1.1.sh"
CONTRACT_INSTALL="$PROJECT_ROOT/docs/stage15a/RNA_TR_Scout_Biology_ready_interpretation_output_contract_v0.1.0.md"
GATES_INSTALL="$PROJECT_ROOT/validation/release_gates_v0.2.3.tsv"
META_INSTALL="$PROJECT_ROOT/metadata/stage15a/ssot_updates/restart_biology_v0.1.1"
QC_INSTALL="$PROJECT_ROOT/qc/15_stage15a_ssot_update/$RUN_ID/restart_biology_v0.1.1"

DOWNLOADS="$HOME/Downloads"
OUTPUT_BUNDLE="$DOWNLOADS/rnatr_stage15a_ssot_update_restart_biology_v0.1.1_output.tar.gz"
FAILURE_BUNDLE="$DOWNLOADS/rnatr_stage15a_ssot_update_restart_biology_v0.1.1_failure.tar.gz"

EXPECTED_CLI_SHA="90acacb80a281b9c7a3a60ef9771c987fd515ab09825ac969787708d27b6bb33"
EXPECTED_DB_SHA="93e20ba78fe63f91380bfb788e56a2317afe2d8214976526386c2a39d01887d9"
EXPECTED_RESTART_QC_SHA="2882679389df77b3fe859e76a234f3bf2bd5cdbce6a8daace995fd31274c2f65"
EXPECTED_PREPARE_QC_SHA="d2a50710c4c853086b01d8072e4bad584ba83fc3ad5b9e6ef7038c853ef8bec9"
EXPECTED_NOOP_QC_SHA="8dac76f5aecfc5a660667247a1ef00987a2e599c833bb7bd894c08376130ec4f"
EXPECTED_COMPARISON_SHA="03c5201b082bae0f4b635c61e9007d6c566a866ca8ad76e8a25c58b04a92525c"
EXPECTED_CHECKPOINT_SHA="4c2672c3e23340e00bc07c65684ed161c74f06fada65af91c7e9ece501423952"
EXPECTED_PACKAGE_MANIFEST_SHA="f50b0e65a1b33b28c8e5ef9a00512a87926f4745cd598477dd1f090fa7cdb6a6"
EXPECTED_RUNNER_SHA="4f9159e47a1fb9df1c3496181b24181102fb760463d0fd38c3236216bd448b44"
EXPECTED_INSTALLER_SHA="cc88df360cab0430e2bb3ba8bef1355ace5013ea501b81b046af568ff93d3bec"
EXPECTED_CONTRACT_SHA="90a86b3b5391abfbd17b6766254af307134f21a9357b50f8b28b0004d7148a87"
EXPECTED_GATES_SHA="5e7938b097fe2210e3cb159c10f424c11f2633f6d4452114fa894f359da681db"
PATCH_MARKER="# Stage 15A restart/resume and biology-ready output contract registration v0.1.0"

PYTHON_BIN="${PYTHON_BIN:-python}"
SELF="$(readlink -f "$0")"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
WORK_PARENT="$PROJECT_ROOT/tmp/15_stage15a_ssot_update/$RUN_ID"
WORK_ROOT="$WORK_PARENT/restart_biology.$STAMP.$$"
LOG_ROOT="$WORK_ROOT/logs"
BUNDLE_ROOT="$WORK_ROOT/bundle"
BACKUP_DIR=""
MUTATION_STARTED=false
SUCCESS=false
PREEXISTING_EXPORTS=false
PREEXISTING_CONTRACT=false
PREEXISTING_GATES=false

say() { printf '%s
' "$*"; }
die() { printf 'ERROR: %s
' "$*" >&2; return 2; }
sha256_file() { sha256sum "$1" | awk '{print $1}'; }

restore_state() {
    [[ -n "$BACKUP_DIR" && -d "$BACKUP_DIR" ]] || return 0
    say "Restoring pre-update state..."
    cp -a "$BACKUP_DIR/rnatr_ssot.py" "$SSOT_CLI" 2>/dev/null || true
    cp -a "$BACKUP_DIR/rnatr_ssot.sqlite" "$SSOT_DB" 2>/dev/null || true
    if [[ -f "$BACKUP_DIR/CURRENT_STATE.md" ]]; then cp -a "$BACKUP_DIR/CURRENT_STATE.md" "$SSOT_SUMMARY"; else rm -f "$SSOT_SUMMARY"; fi
    if [[ -d "$BACKUP_DIR/exports" ]]; then rm -rf "$SSOT_EXPORTS"; cp -a "$BACKUP_DIR/exports" "$SSOT_EXPORTS"; elif [[ "$PREEXISTING_EXPORTS" == false ]]; then rm -rf "$SSOT_EXPORTS"; fi
    if [[ "$PREEXISTING_CONTRACT" == true ]]; then cp -a "$BACKUP_DIR/biology_contract.md" "$CONTRACT_INSTALL"; else rm -f "$CONTRACT_INSTALL"; fi
    if [[ "$PREEXISTING_GATES" == true ]]; then cp -a "$BACKUP_DIR/release_gates_v0.2.3.tsv" "$GATES_INSTALL"; else rm -f "$GATES_INSTALL"; fi
}

pack_failure() {
    local rc="$1" line="$2" command_text="$3"
    set +e
    mkdir -p "$WORK_ROOT/failure" "$DOWNLOADS"
    {
        printf 'metric	value
'
        printf 'update_version	%s
' "$UPDATE_VERSION"
        printf 'exit_code	%s
' "$rc"
        printf 'line	%s
' "$line"
        printf 'command	%s
' "$command_text"
        printf 'mutation_started	%s
' "$MUTATION_STARTED"
        printf 'timestamp_utc	%s
' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    } > "$WORK_ROOT/failure/failure.tsv"
    tar -czf "$FAILURE_BUNDLE.part" -C "$WORK_ROOT" . 2>/dev/null || true
    if [[ -s "$FAILURE_BUNDLE.part" ]]; then
        mv -f "$FAILURE_BUNDLE.part" "$FAILURE_BUNDLE"
        sha256sum "$FAILURE_BUNDLE" > "$FAILURE_BUNDLE.sha256"
        printf 'Failure bundle: %s
' "$FAILURE_BUNDLE" >&2
        printf 'Failure SHA:    %s
' "$FAILURE_BUNDLE.sha256" >&2
    fi
}

on_error() {
    local rc="$1" line="$2" command_text="$3"
    trap - ERR
    set +e
    printf 'ERROR: update failed at line %s (exit %s): %s
' "$line" "$rc" "$command_text" >&2
    if [[ "$MUTATION_STARTED" == true ]]; then restore_state; fi
    pack_failure "$rc" "$line" "$command_text"
    exit "$rc"
}
trap 'on_error "$?" "$LINENO" "$BASH_COMMAND"' ERR

for command_name in "$PYTHON_BIN" sha256sum tar flock awk grep cmp cp mv readlink base64; do
    command -v "$command_name" >/dev/null 2>&1 || die "required command not found: $command_name"
done
[[ -d "$PROJECT_ROOT" ]] || die "project root not found: $PROJECT_ROOT"
mkdir -p "$WORK_PARENT" "$WORK_ROOT" "$LOG_ROOT" "$BUNDLE_ROOT" "$DOWNLOADS" "$SSOT_BACKUPS"
exec 9>"$LOCK_PATH"
flock -n 9 || die "another SSOT update holds $LOCK_PATH"

say "===== STAGE 15A RESTART + BIOLOGY CONTRACT SSOT UPDATE PREFLIGHT ====="
say "restart/resume:          REGISTER SELECTIVE 100K PASS"
say "250k scaling:            KEEP OPEN / NEXT"
say "biology-ready contract:  REGISTER DESIGNED / OPEN"
say "core schema:             DO NOT MODIFY"
say "active pipeline:         DO NOT MODIFY"
say "full 5.31M:              DO NOT RUN"

for p in "$SSOT_CLI" "$SSOT_DB" "$RESTART_QC" "$PREPARE_QC" "$NOOP_QC" "$PACKAGE_COMPARISON" "$ACTIVE_BEFORE" "$ACTIVE_AFTER" "$SSOT_GUARDS_AFTER" "$CHECKPOINT_MANIFEST" "$PACKAGE_MANIFEST" "$RESTART_RUNNER" "$RESTART_INSTALLER" "$CORE_SCHEMA"; do
    [[ -s "$p" ]] || die "required file missing or empty: $p"
done

[[ "$(sha256_file "$SSOT_CLI")" == "$EXPECTED_CLI_SHA" ]] || die "unexpected SSOT source SHA"
[[ "$(sha256_file "$SSOT_DB")" == "$EXPECTED_DB_SHA" ]] || die "unexpected SSOT DB SHA"
[[ "$(sha256_file "$RESTART_QC")" == "$EXPECTED_RESTART_QC_SHA" ]] || die "restart QC SHA mismatch"
[[ "$(sha256_file "$PREPARE_QC")" == "$EXPECTED_PREPARE_QC_SHA" ]] || die "prepare QC SHA mismatch"
[[ "$(sha256_file "$NOOP_QC")" == "$EXPECTED_NOOP_QC_SHA" ]] || die "noop QC SHA mismatch"
[[ "$(sha256_file "$PACKAGE_COMPARISON")" == "$EXPECTED_COMPARISON_SHA" ]] || die "comparison SHA mismatch"
[[ "$(sha256_file "$CHECKPOINT_MANIFEST")" == "$EXPECTED_CHECKPOINT_SHA" ]] || die "checkpoint manifest SHA mismatch"
[[ "$(sha256_file "$PACKAGE_MANIFEST")" == "$EXPECTED_PACKAGE_MANIFEST_SHA" ]] || die "package manifest SHA mismatch"
[[ "$(sha256_file "$RESTART_RUNNER")" == "$EXPECTED_RUNNER_SHA" ]] || die "restart runner SHA mismatch"
[[ "$(sha256_file "$RESTART_INSTALLER")" == "$EXPECTED_INSTALLER_SHA" ]] || die "restart installer SHA mismatch"
"$PYTHON_BIN" - "$ACTIVE_BEFORE" "$ACTIVE_AFTER" <<'PY_ACTIVE_GUARD'
import csv, sys

before_path, after_path = sys.argv[1], sys.argv[2]

def load_before(path):
    with open(path, newline="", encoding="utf-8") as h:
        rows = list(csv.DictReader(h, delimiter="\t"))
    if not rows or set(rows[0]) != {"path", "sha256", "status"}:
        raise SystemExit(f"unexpected active-before schema: {path}")
    out = {}
    for row in rows:
        if row["status"] != "PASS":
            raise SystemExit(f"active-before non-PASS row: {row}")
        out[row["path"]] = row["sha256"]
    return out

def load_after(path):
    with open(path, newline="", encoding="utf-8") as h:
        rows = list(csv.DictReader(h, delimiter="\t"))
    if not rows or set(rows[0]) != {"path", "before_sha256", "after_sha256", "status"}:
        raise SystemExit(f"unexpected active-after schema: {path}")
    out = {}
    for row in rows:
        if row["status"] != "PASS":
            raise SystemExit(f"active-after non-PASS row: {row}")
        if row["before_sha256"] != row["after_sha256"]:
            raise SystemExit(f"active file changed during restart audit: {row['path']}")
        out[row["path"]] = row["after_sha256"]
    return out

before = load_before(before_path)
after = load_after(after_path)
if before != after:
    missing = sorted(set(before) - set(after))
    extra = sorted(set(after) - set(before))
    changed = sorted(k for k in set(before) & set(after) if before[k] != after[k])
    raise SystemExit(
        f"active implementation semantic guard mismatch: "
        f"missing={missing} extra={extra} changed={changed}"
    )
print(f"ACTIVE_IMPLEMENTATION_SEMANTIC_GUARD_PASS\tfiles={len(before)}")
PY_ACTIVE_GUARD

"$PYTHON_BIN" "$SSOT_CLI" --project-root "$PROJECT_ROOT" validate 2>&1 | tee "$LOG_ROOT/ssot_validate_before.log"

"$PYTHON_BIN" - "$SSOT_DB" "$WORK_ROOT/current_pipeline.before.tsv" <<'PY_PIPELINE'
import csv, sqlite3, sys
con=sqlite3.connect(sys.argv[1]); con.row_factory=sqlite3.Row
rows=con.execute("SELECT * FROM current_pipeline ORDER BY stage_order,stage_key").fetchall()
with open(sys.argv[2],"w",newline="",encoding="utf-8") as h:
    if rows:
        w=csv.DictWriter(h,fieldnames=rows[0].keys(),delimiter="	",lineterminator="\n")
        w.writeheader(); w.writerows(dict(r) for r in rows)
PY_PIPELINE
CORE_SCHEMA_SHA_BEFORE="$(sha256_file "$CORE_SCHEMA")"

BACKUP_DIR="$SSOT_BACKUPS/pre_stage15a_restart_biology_v0.1.1_$STAMP"
mkdir -p "$BACKUP_DIR"
cp -a "$SSOT_CLI" "$BACKUP_DIR/rnatr_ssot.py"
cp -a "$SSOT_DB" "$BACKUP_DIR/rnatr_ssot.sqlite"
[[ -f "$SSOT_SUMMARY" ]] && cp -a "$SSOT_SUMMARY" "$BACKUP_DIR/CURRENT_STATE.md"
if [[ -d "$SSOT_EXPORTS" ]]; then PREEXISTING_EXPORTS=true; cp -a "$SSOT_EXPORTS" "$BACKUP_DIR/exports"; fi
if [[ -f "$CONTRACT_INSTALL" ]]; then PREEXISTING_CONTRACT=true; cp -a "$CONTRACT_INSTALL" "$BACKUP_DIR/biology_contract.md"; fi
if [[ -f "$GATES_INSTALL" ]]; then PREEXISTING_GATES=true; cp -a "$GATES_INSTALL" "$BACKUP_DIR/release_gates_v0.2.3.tsv"; fi

MUTATION_STARTED=true
mkdir -p "$(dirname "$SCRIPT_INSTALL")" "$(dirname "$CONTRACT_INSTALL")" "$(dirname "$GATES_INSTALL")" "$META_INSTALL" "$QC_INSTALL"
cp -a "$SELF" "$SCRIPT_INSTALL"
chmod 0755 "$SCRIPT_INSTALL"

printf '%s' 'IyBSTkEtVFItU2NvdXQgQmlvbG9neS1yZWFkeSAvIEludGVycHJldGF0aW9uLXJlYWR5IE91dHB1dCBDb250cmFjdCB2MC4xLjAKCuS9nOaIkOaXpTogMjAyNi0wOC0wOCAgCueKtuaFizogYERFU0lHTkVEX05PVF9JTVBMRU1FTlRFRGAgIArpgannlKjnr4Tlm7I6IGV2aWRlbmNlIHNjaGVtYSB2MC40LjIgY29yZSBwYWNrYWdl44KS5L+d5oyB44GX44Gf44G+44G+44CBUk5BIGJpb2xvZ3njgajlpKfopo/mqKFjYW5kaWRhdGUgdHJpYWdl44KS5Y+v6IO944Gr44GZ44KL6L+95Yqg5Ye65Yqb5aWR57SEICAK6Z2e55uu5qiZOiDmnKzlpZHntITjga9TdGFnZSAxNUHjga5zY2llbnRpZmljIGNhbGxlcuOAgWNvcmUgNS10YWJsZSBmaWVsZCBzZW1hbnRpY3PjgIFhY3RpdmUgcGlwZWxpbmXjgpLlpInmm7TjgZfjgarjgYQKCi0tLQoKIyMgMS4g57WQ6KuWCgpSTkEtVFItU2NvdXTjga7nj77lnKjjga5jb3JlIDUtdGFibGUgcGFja2FnZeOBr+OAgXJlcGVhdCBhcmNoaXRlY3R1cmXjgavjgaTjgYTjgabjga9yZWFkLWxldmVs44Gn5Y2B5YiG44GrbG9zc2xlc3PjgaoqKnJlcGVhdC1tZWFzdXJlbWVudCBzb3VyY2Ugb2YgdHJ1dGgqKuOBp+OBguOCi+OAggoK5LiA5pa544CB54++cGFja2FnZeOBoOOBkeOBp+OBr+S7peS4i+OCkuebtOaOpeaknOiovOOBp+OBjeOBquOBhOOAggoKMS4gcmVwZWF0IGFyY2hpdGVjdHVyZeOBqHRyYW5zY3JpcHQgLyBpc29mb3JtIC8gc3BsaWNlLWp1bmN0aW9uIHN0YXRl44Gu5ZCM5LiA5YiG5a2Q5YaF5a++5b+cCjIuIOWQjOS4gGhhcGxvdHlwZeWGheOBrlJOQSBtb2xlY3VsZemWk3JlcGVhdCBoZXRlcm9nZW5laXR5CjMuIDXigLIvM+KAsiB0cnVuY2F0aW9u44CBbWFwcGluZyByZWFjaGFiaWxpdHnjgIFjZW5zb3JpbmfjgarjganjgpLmmI7npLrnmoTjgavliIbpm6LjgZfjgZ9vYnNlcnZhYmlsaXR5CjQuIFBDUiBkdXBsaWNhdGXjgIFSVCBkdXBsaWNhdGXjgIFjb25jYXRlbWVy44CBY2hpbWVyYeetieOCkuiAg+aFruOBl+OBn21vbGVjdWxlIGluZGVwZW5kZW5jZQo1LiDlpKfph4/jga5yYXcgcmVwZWF0IGV2ZW50c+OCkueglOeptuebrueahOWIpeOBq+Wcp+e4ruOBl+OBn3NhbXBsZcOXbG9jdXMgc3VtbWFyeeOAgXJhbmtpbmfjgIFyZXNlYXJjaGVyLWZhY2luZyBkb3NzaWVyCgrjgZfjgZ/jgYzjgaPjgabjgIFjb3JlIDUtdGFibGXjgpLogqXlpKfljJbjgZXjgZvjgZrjgIFgcmVhZF9pZGAgLyBgZXZpZGVuY2VfaWRgIC8gYHJlcGVhdF9ldmVudF9pZGDjgadqb2lu5Y+v6IO944GqdmVyc2lvbmVkIHNpZGVjYXLjgahkZXJpdmVkIGludGVycHJldGF0aW9uIGxheWVy44KS6L+95Yqg44GZ44KL44CCCgotLS0KCiMjIDIuIOWkieabtOOBl+OBquOBhGNvcmUgc291cmNlIG9mIHRydXRoCgpldmlkZW5jZSBzY2hlbWEgdjAuNC4y44Gu5Lul5LiLNeihqOOBr+OAgXJlcGVhdCBtZWFzdXJlbWVudOOBruato+acrOOBqOOBl+OBpue2reaMgeOBmeOCi+OAggoKYGBgdGV4dApnZW5lcmFsX3JlcGVhdF9jYWxscwpyZWFkX2V2aWRlbmNlCnJlcGVhdF9ldmVudHMKcmVwZWF0X3NlZ21lbnRzCnJlcGVhdF9pbnRlcnJ1cHRpb25zCmBgYAoK5L+d5oyB44GZ44G544GNcmVhZC9tb2xlY3VsZS1sZXZlbOaDheWgseOBq+OBr+OAgeWwkeOBquOBj+OBqOOCguS7peS4i+OCkuWQq+OCgOOAggoKYGBgdGV4dApyZXBlYXQgbGVuZ3RoOiBleGFjdCAvIGxvd2VyIGJvdW5kIC8gaW50ZXJ2YWwgLyBjb250ZXh0LWxpbWl0ZWQKY2Fub25pY2FsIGFuZCBvcmllbnRlZCBtb3RpZgpwdXJpdHkKTFBTIGV4YWN0LXNlcXVlbmNlIC8gaW5mZXJyZWQKY29tcG91bmQgcmVwZWF0IHNlZ21lbnRzCnN0cnVjdHVyZWQgaW50ZXJydXB0aW9ucwptaXNtYXRjaCAvIGluc2VydGlvbiAvIGRlbGV0aW9uCmV2aWRlbmNlIGdlb21ldHJ5CmxlZnQvcmlnaHQgYm91bmRhcnkgc3RhdHVzCmNlbnNvcmluZyBhbmQgc2VxdWVuY2UtZWRnZSBjb250YWN0CmFsdGVybmF0aXZlIG1vdGlmIGh5cG90aGVzaXMKYXNzaWdubWVudCBhbmQgY29tcGV0aW5nLWxvY3VzIGNvbnRleHQKYGBgCgpgcmVwZWF0X2V2ZW50c2Djga9yZWFkL21vbGVjdWxlLWxldmVsIHJlcGVhdCBkaXN0cmlidXRpb27jga5zb3VyY2Ugb2YgdHJ1dGjjgafjgYLjgorjgIFzYW1wbGUtbGV2ZWwgc3VtbWFyeeOChHJhbmtpbmfjga7jgZ/jgoHjgavnoLTmo4Tjg7vkuIrmm7jjgY3jgZfjgarjgYTjgIIKCi0tLQoKIyMgMy4gQmlvbG9neSBqb2luIHNpZGVjYXJzCgrjgZnjgbnjgabjga5zaWRlY2Fy44GvdmVyc2lvbmVkIHNjaGVtYeOAgWV4cGxpY2l0IG1pc3NpbmduZXNz44CBc291cmNlIHByb3ZlbmFuY2XjgpLmjIHjgaTjgILmnKroqZXkvqHlgKTjga/mjqjmuKzjgafln4vjgoHjgZrjgIFgTk9UX0FTU0VTU0VEYOOAgWBOT1RfQVZBSUxBQkxFYOOAgWBBTUJJR1VPVVNg562J44KS5piO56S644GZ44KL44CCCgojIyMgMy4xIGByZWFkX3RyYW5zY3JpcHRfc3RhdGUudHN2Lmd6YAoK5Li744Kt44O85YCZ6KOcOgoKYGBgdGV4dApydW5faWQgKyBzYW1wbGVfaWQgKyByZWFkX2lkICsgdHJhbnNjcmlwdF9hc3NpZ25tZW50X2lkCmBgYAoK5b+F6aCI5YCZ6KOc44OV44Kj44O844Or44OJOgoKYGBgdGV4dApyZWFkX2lkCmdlbmVfaWQKdHJhbnNjcmlwdF9pZAp0cmFuc2NyaXB0X25hbWUKaXNvZm9ybV9hc3NpZ25tZW50X3N0YXR1cwpqdW5jdGlvbl9jaGFpbgpzcGxpY2VfanVuY3Rpb25fY291bnQKaW50cm9uX3JldGVudGlvbl9zdGF0dXMKY3J5cHRpY19zcGxpY2Vfc3RhdHVzCmFsdGVybmF0aXZlX2ZpcnN0X2V4b25fc3RhdHVzCmFsdGVybmF0aXZlX2xhc3RfZXhvbl9zdGF0dXMKcG9seWFkZW55bGF0aW9uX3NpdGUKdHJhbnNjcmlwdF81cHJpbWVfY29tcGxldGUKdHJhbnNjcmlwdF8zcHJpbWVfY29tcGxldGUKYXNzaWdubWVudF9tZXRob2QKYXNzaWdubWVudF9jb25maWRlbmNlCmFzc2lnbm1lbnRfZmxhZ3MKc291cmNlX2Fubm90YXRpb25fdmVyc2lvbgpgYGAKCuWQjOS4gHJlYWTjgavopIfmlbDjga50cmFuc2NyaXB0IGh5cG90aGVzaXPjgYzjgYLjgovloLTlkIjjga/jgIHljZjkuIDlgKTjgbjmvbDjgZXjgZpyYW5rZWQgaHlwb3RoZXNlc+OBqOOBl+OBpuS/neaMgeOBmeOCi+OAggoKIyMjIDMuMiBgcmVhZF9oYXBsb3R5cGVfc3RhdGUudHN2Lmd6YAoK5Li744Kt44O85YCZ6KOcOgoKYGBgdGV4dApydW5faWQgKyBzYW1wbGVfaWQgKyByZWFkX2lkICsgcGhhc2VfYXNzaWdubWVudF9pZApgYGAKCuW/hemgiOWAmeijnOODleOCo+ODvOODq+ODiToKCmBgYHRleHQKcmVhZF9pZApwaGFzZV9ibG9ja19pZApoYXBsb3R5cGVfbGFiZWwKaW5mb3JtYXRpdmVfdmFyaWFudF9jb3VudAppbmZvcm1hdGl2ZV92YXJpYW50cwpwaGFzZV9zb3VyY2UKcGhhc2VfbWV0aG9kCnBoYXNlX2NvbmZpZGVuY2UKcGhhc2Vfc3RhdHVzCnBoYXNlX2ZsYWdzCm1hdGNoZWRfZG5hX3NhbXBsZV9pZApgYGAKCmd1YXJkcmFpbDoKCi0gcGhhc2UgZXZpZGVuY2XjgarjgZfjgathbGxlbGUgMS8y44CBbWF0ZXJuYWwvcGF0ZXJuYWzjgIFub3JtYWwvZXhwYW5kZWTjgajlkbzjgbDjgarjgYQKLeWIneacn+ODqeODmeODq+OBr+S4reeri+OBqmBIMWAsIGBIMmAsIGBVTlBIQVNFRGAsIGBBTUJJR1VPVVNgCi0gbWF0Y2hlZCBETkHjgIFTTlAgcGhhc2luZ+OAgW9ydGhvZ29uYWwgZXZpZGVuY2XjgYzjgYLjgovloLTlkIjjga7jgb/mhI/lkbPku5jjgZHjgpLmmIfmoLzjgZnjgosKCiMjIyAzLjMgYHJlYWRfb2JzZXJ2YWJpbGl0eS50c3YuZ3pgCgrkuLvjgq3jg7zlgJnoo5w6CgpgYGB0ZXh0CnJ1bl9pZCArIHNhbXBsZV9pZCArIGV2aWRlbmNlX2lkCmBgYAoK5b+F6aCI5YCZ6KOc44OV44Kj44O844Or44OJOgoKYGBgdGV4dApyZWFkX2lkCmV2aWRlbmNlX2lkCmxvY3VzX2lkCnBsYXRmb3JtCmxpYnJhcnlfbWV0aG9kCnRhcmdldF9yZWFjaGFibGUKbGVmdF9mbGFua19yZWFjaGFibGUKcmlnaHRfZmxhbmtfcmVhY2hhYmxlCnJlcGVhdF9mdWxseV9vYnNlcnZhYmxlCm9ic2VydmVkX2ludGVydmFsX3N0YXJ0Cm9ic2VydmVkX2ludGVydmFsX2VuZApleHBlY3RlZF90cmFuc2NyaXB0X3Bvc2l0aW9uCmZpdmVfcHJpbWVfdHJ1bmNhdGlvbl9zdGF0dXMKdGhyZWVfcHJpbWVfZW5kX3N0YXR1cwpjZW5zb3JpbmdfY2xhc3MKY29udGV4dF9saW1pdGVkCm1hcHBpbmdfYW1iaWd1aXR5X3N0YXR1cwpzZXF1ZW5jZV9xdWFsaXR5X3N0YXR1cwpvYnNlcnZhYmlsaXR5X3N0YXR1cwpvYnNlcnZhYmlsaXR5X2ZsYWdzCmBgYAoKcmVwZWF0IGxlbmd0aOOBruasoOa4rOODu2xvd2VyIGJvdW5k44Go44CB55yf44Gu55+t44GEcmVwZWF044KS5re35ZCM44GX44Gq44GE44Gf44KB44Guc2lkZWNhcuOBp+OBguOCi+OAggoKIyMjIDMuNCBgcmVhZF9tb2xlY3VsZV9pbmRlcGVuZGVuY2UudHN2Lmd6YAoK5Li744Kt44O85YCZ6KOcOgoKYGBgdGV4dApydW5faWQgKyBzYW1wbGVfaWQgKyByZWFkX2lkCmBgYAoK5b+F6aCI5YCZ6KOc44OV44Kj44O844Or44OJOgoKYGBgdGV4dApyZWFkX2lkCm1vbGVjdWxlX2ZhbWlseV9pZAppbmRlcGVuZGVuY2Vfc3RhdHVzCmR1cGxpY2F0ZV9jbGFzcwpkdXBsaWNhdGVfZ3JvdXBfaWQKdW1pCnJ0X2R1cGxpY2F0ZV9zdGF0dXMKcGNyX2R1cGxpY2F0ZV9zdGF0dXMKY29uY2F0ZW1lcl9zdGF0dXMKY2hpbWVyYV9zdGF0dXMKc3RyYW5kX3N3aXRjaF9zdGF0dXMKaW5kZXBlbmRlbmNlX2NvbmZpZGVuY2UKaW5kZXBlbmRlbmNlX2ZsYWdzCmRlZHVwbGljYXRpb25fbWV0aG9kCmBgYAoKZ3VhcmRyYWlsOgoKLSBgcmVhZF9pZGDjgpLoh6rli5XnmoTjgavni6znq4tiaW9sb2dpY2FsIG1vbGVjdWxl44Go44G/44Gq44GV44Gq44GECi0gVU1J44Gq44GX44GuY0ROQeOBp+OBr+WujOWFqOOBqmR1cGxpY2F0Zeino+axuuOCkuS4u+W8teOBl+OBquOBhAotIGRlZHVwbGljYXRpb27liY3lvozjga7liIbluIPjgpLkuKHmlrnov73ot6Hlj6/og73jgavjgZnjgosKCi0tLQoKIyMgNC4gRGVyaXZlZCBtb2xlY3VsZS1sZXZlbCBiaW9sb2d5IHZpZXcKCiMjIyA0LjEgYG1vbGVjdWxlX3JlcGVhdF9zdGF0ZS50c3YuZ3pgCgpjb3JlIHJlcGVhdCB0YWJsZXPjgag0IHNpZGVjYXLjgpJqb2lu44GX44Gf56CU56m255Sodmlld+OAggoK57KS5bqmOgoKYGBgdGV4dApvbmUgcm93IHBlciBzYW1wbGUgw5cgbW9sZWN1bGUvcmVhZCDDlyBsb2N1cyDDlyByZXBlYXQgZXZlbnQKYGBgCgrmnIDkvY7pmZDkv53mjIHjgZnjgovjgoLjga46CgpgYGB0ZXh0CnJlcGVhdCBhcmNoaXRlY3R1cmUKdHJhbnNjcmlwdC9pc29mb3JtIHN0YXRlCmhhcGxvdHlwZSBzdGF0ZQpvYnNlcnZhYmlsaXR5IHN0YXRlCm1vbGVjdWxlIGluZGVwZW5kZW5jZSBzdGF0ZQphbGwgc291cmNlIElEcwpqb2luIGNvbXBsZXRlbmVzcyBmbGFncwpgYGAKCueglOeptuS4iuOBruS4u+imgXF1ZXJ5OgoKPiDlkIzkuIBoYXBsb3R5cGXjgavlsZ7jgZnjgotSTkEgbW9sZWN1bGXplpPjgadyZXBlYXQgbGVuZ3Ro44CBcHVyaXR544CBTFBT44CBaW50ZXJydXB0aW9uc+OAgWNvbXBvdW5kIGFyY2hpdGVjdHVyZeOBjOeVsOOBquOCi+OBi+OAguOBneOBruW3ruOBjHNwbGljZSBqdW5jdGlvbuOAgWlzb2Zvcm3jgIFpbnRyb24gcmV0ZW50aW9u44CBcG9seWFkZW55bGF0aW9u562J44Go5a++5b+c44GZ44KL44GL44CCCgrjgZPjga5xdWVyeeOCkuWPr+iDveOBq+OBmeOCi+OBn+OCgeOAgW1vbGVjdWxlLWxldmVsIGRpc3RyaWJ1dGlvbuOCknNhbXBsZS9sb2N1cyBzdW1tYXJ55L2c5oiQ5b6M44KC5b+F44Ga5L+d5oyB44GZ44KL44CCCgotLS0KCiMjIDUuIEludGVycHJldGF0aW9uIGhpZXJhcmNoeQoKcmF3IGV2aWRlbmNl44KS55u05o6lY2FuZGlkYXRl5pWw44Go44GX44Gm5omx44KP44Gq44GE44CC5qyh44Gu6ZqO5bGk44KSdmVyc2lvbmVk44Gr5qeL56+J44GZ44KL44CCCgpgYGB0ZXh0CmNvcmUgcmF3IGNhbGxlciBhdHRlbXB0IC8gcmVwZWF0IGV2ZW50CiAgICDihpMKbW9sZWN1bGUtbGV2ZWwgcmVwZWF0IHN0YXRlCiAgICDihpMKc2FtcGxlIMOXIGxvY3VzIGRpc3RyaWJ1dGlvbiBzdW1tYXJ5CiAgICDihpMKcHVycG9zZS1zcGVjaWZpYyByYW5raW5nIGxhbmVzCiAgICDihpMKcmVzZWFyY2hlci1mYWNpbmcgY2FuZGlkYXRlIGRvc3NpZXIKYGBgCgojIyMgNS4xIGBzYW1wbGVfbG9jdXNfc3VtbWFyeS50c3YuZ3pgCgrmnIDkvY7pmZDjga7lhoXlrrk6CgpgYGB0ZXh0CnNhbXBsZV9pZApsb2N1c19pZAprbm93bl9kaXNlYXNlX2xvY3VzX3N0YXR1cwp0b3RhbF9zdXBwb3J0aW5nX3JlYWRzCmluZGVwZW5kZW50X21vbGVjdWxlX2NvdW50CmV4YWN0X29ic2VydmF0aW9uX2NvdW50Cmxvd2VyX2JvdW5kX2NvdW50CmNvbnRleHRfbGltaXRlZF9jb3VudApvYnNlcnZhYmxlX21vbGVjdWxlX2NvdW50CnJlcGVhdF9sZW5ndGhfZXhhY3RfZGlzdHJpYnV0aW9uCnJlcGVhdF9sZW5ndGhfbG93ZXJfYm91bmRfZGlzdHJpYnV0aW9uCnB1cml0eV9kaXN0cmlidXRpb24KTFBTX2Rpc3RyaWJ1dGlvbgppbnRlcnJ1cHRpb25fYXJjaGl0ZWN0dXJlX3N1bW1hcnkKaGV0ZXJvZ2VuZWl0eV9tZXRyaWNzCmhhcGxvdHlwZV9zdHJhdGlmaWVkX3N1bW1hcnkKaXNvZm9ybV9zdHJhdGlmaWVkX3N1bW1hcnkKdGVjaG5pY2FsX2NvbmZpZGVuY2Vfc3VtbWFyeQpzdW1tYXJ5X2ZsYWdzCmBgYAoKZXhhY3TjgIFsb3dlciBib3VuZOOAgWNvbnRleHQtbGltaXRlZOOCkm5haXZl44Gr5ZCM5LiA5YiG5biD44G45re344Gc44Gq44GE44CCCgojIyMgNS4yIGBjYW5kaWRhdGVfcmFua2luZ19sYW5lcy50c3YuZ3pgCgrljZjkuIDjga7nt4/lkIhzY29yZeOCkuWUr+S4gOOBrumghuS9jeOBqOOBl+OBpuaOoeeUqOOBl+OBquOBhOOAguWwkeOBquOBj+OBqOOCguS7peS4i+OBrmxhbmXjgpLni6znq4vjgavmjIHjgaTjgIIKCmBgYHRleHQKS05PV05fRElTRUFTRQpFWFBBTlNJT05fRElTQ09WRVJZClJOQV9QUk9DRVNTSU5HClJFUEVBVF9IRVRFUk9HRU5FSVRZCkhBUExPVFlQRV9DT05UUk9MTEVEClRFQ0hOSUNBTF9DT05GSURFTkNFCmBgYAoK5ZCE6KGMOgoKYGBgdGV4dApzYW1wbGVfaWQKbG9jdXNfaWQKcmFua2luZ19sYW5lCmxhbmVfc2NvcmUKbGFuZV9yYW5rCmVsaWdpYmlsaXR5X3N0YXR1cwpzdXBwb3J0aW5nX2ZlYXR1cmVfanNvbgpwZW5hbHR5X2ZlYXR1cmVfanNvbgpyYW5raW5nX21vZGVsX2lkCnJhbmtpbmdfbW9kZWxfdmVyc2lvbgpyYW5raW5nX2ZsYWdzCmBgYAoK5Y6f5YmHOgoKLSBrbm93biBkaXNlYXNlIHJlcGVhdOOBr+mWvuWApOOBq+OBi+OBi+OCj+OCieOBmmBLTk9XTl9ESVNFQVNFYCBsYW5l44Gn5L+d5oyB44GZ44KLCi0gdGVjaG5pY2FsIGNvbmZpZGVuY2Xjga9iaW9sb2d5IHNjb3Jl44Gu5Luj5pu/44Gr44GX44Gq44GECi0gcHVycG9zZS1zcGVjaWZpYyBsYW5l6ZaT44Guc2NvcmXjgpLnm7TmjqXmr5TovIPjgZfjgarjgYQKLSBwYXRob2dlbmljaXR5IHNjb3Jl44Go44Gv5ZG844Gw44Gq44GECgojIyMgNS4zIGBjYW5kaWRhdGVfZG9zc2llci5qc29ubC5nemAKCuWQhHNhbXBsZcOXbG9jdXPjgavjgaTjgYTjgabjgIHnoJTnqbbogIXjgYxyYXcgVFNW44KS5omL5L2c5qWt44Gn6L6/44KJ44Gq44GP44Gm44KC55uj5p+744Gn44GN44KLZG9zc2llcuOCkuS9nOOCi+OAggoK5YaF5a65OgoKYGBgdGV4dApjYW5kaWRhdGUgaWRlbnRpdHkKcmFua2luZyBsYW5lcwprbm93bi1kaXNlYXNlIGFubm90YXRpb24Kc2FtcGxlw5dsb2N1cyBkaXN0cmlidXRpb24KcmVwcmVzZW50YXRpdmUgbW9sZWN1bGUvZXZlbnQgSURzCmhhcGxvdHlwZS1zdHJhdGlmaWVkIGV2aWRlbmNlCmlzb2Zvcm0vc3BsaWNpbmctc3RyYXRpZmllZCBldmlkZW5jZQpvYnNlcnZhYmlsaXR5IGNhdmVhdHMKZHVwbGljYXRlL2luZGVwZW5kZW5jZSBjYXZlYXRzCklHViAvIHJlYWQtbGV2ZWwgYXJ0aWZhY3QgbGlua3MKYWxsIHNvdXJjZSB0YWJsZSBhbmQgc2NoZW1hIHZlcnNpb25zCmBgYAoKZG9zc2llcuOBi+OCieW/heOBmmNvcmUgcm9344G46YCG6L+96Leh44Gn44GN44KL44GT44Go44KS6KaB5rGC44GZ44KL44CCCgotLS0KCiMjIDYuIFJlYWRpbmVzcyBhdWRpdAoK54++5Zyo44GudjAuNC4yIGNvcmUgcGFja2FnZeOBq+WvvuOBmeOCi+aaq+WumuWIpOWumjoKCnwg6aCY5Z+fIHwg54++54q2IHwKfC0tLXwtLS18CnwgcmVwZWF0IGxlbmd0aCAvIHB1cml0eSAvIExQUyAvIGludGVycnVwdGlvbnMgLyBjZW5zb3JpbmcgfCBgUkVBRFlfQVNfQ09SRV9TT1VSQ0VfT0ZfVFJVVEhgIHwKfCByZWFkLWxldmVsIGRpc3RyaWJ1dGlvbiBwcmVzZXJ2YXRpb24gfCBgUkVBRFlgIHwKfCB0cmFuc2NyaXB0IC8gaXNvZm9ybSBzdGF0ZSB8IGBOT1RfSU1QTEVNRU5URURgIHwKfCBoYXBsb3R5cGUgc3RhdGUgfCBgTk9UX0lNUExFTUVOVEVEYCB8CnwgZXhwbGljaXQgb2JzZXJ2YWJpbGl0eSBzaWRlY2FyIHwgYFBBUlRJQUxMWV9JTkZFUkFCTEVfQlVUX05PVF9NQVRFUklBTElaRURgIHwKfCBkdXBsaWNhdGUgLyBtb2xlY3VsZSBpbmRlcGVuZGVuY2UgfCBgTk9UX0lNUExFTUVOVEVEYCB8CnwgbW9sZWN1bGUtbGV2ZWwgam9pbmVkIGJpb2xvZ3kgdmlldyB8IGBOT1RfSU1QTEVNRU5URURgIHwKfCBzYW1wbGXDl2xvY3VzIHN1bW1hcnkgfCBgTk9UX0lNUExFTUVOVEVEYCB8CnwgcHVycG9zZS1zcGVjaWZpYyByYW5raW5nIGxhbmVzIHwgYE5PVF9JTVBMRU1FTlRFRGAgfAp8IHJlc2VhcmNoZXItZmFjaW5nIGRvc3NpZXIgfCBgTk9UX0lNUExFTUVOVEVEYCB8CgrjgZfjgZ/jgYzjgaPjgabjgIHnj77lnKjjga5wYWNrYWdl44GvKipyZXBlYXQtcmVhZHkqKuOBp+OBguOCi+OBjOOAgeOBvuOBoCoqYmlvbG9neS1yZWFkeSAvIGludGVycHJldGF0aW9uLXJlYWR5Kirjgajjga/lkbzjgbDjgarjgYTjgIIKCi0tLQoKIyMgNy4gVmFsaWRhdGlvbiBnYXRlcwoKIyMjIEcyMCBCaW9sb2d5IGpvaW5hYmlsaXR5Cgpjb3JlIHJlcGVhdCBldmlkZW5jZeOBi+OCieOAgXRyYW5zY3JpcHTjgIFoYXBsb3R5cGXjgIFvYnNlcnZhYmlsaXR544CBbW9sZWN1bGUgaW5kZXBlbmRlbmNlIHNpZGVjYXLjgbhsb3NzbGVzc+OBq2pvaW7jgafjgY3jgovjgIIKCiMjIyBHMjEgTW9sZWN1bGUgZGlzdHJpYnV0aW9uIHByZXNlcnZhdGlvbgoKbW9sZWN1bGUtbGV2ZWwgcmVwZWF0IGRpc3RyaWJ1dGlvbuOBjHNhbXBsZSBzdW1tYXJ55b6M44KC5L+d5oyB44GV44KM44CBZXhhY3QvbG93ZXItYm91bmQvY29udGV4dC1saW1pdGVk44GM5Yy65Yil44GV44KM44KL44CCCgojIyMgRzIyIFB1cnBvc2Utc3BlY2lmaWMgdHJpYWdlCgropIfmlbByYW5raW5nIGxhbmXjgahrbm93bi1kaXNlYXNlIHJldGVudGlvbuOBjOWun+ijheOBleOCjOOAgeWNmOS4gHNjb3Jl44G444Gu6YGO5Ymw5Zyn57iu44KS6KGM44KP44Gq44GE44CCCgojIyMgRzIzIERvc3NpZXIgdHJhY2VhYmlsaXR5CgpyZXNlYXJjaGVyLWZhY2luZyBkb3NzaWVy44Gu5YWo5Li75by144GMY29yZSBldmlkZW5jZeOAgXNpZGVjYXLjgIFzdW1tYXJ544CBcmFua2luZyBtb2RlbCB2ZXJzaW9u44G46YCG6L+96Leh44Gn44GN44KL44CCCgrjgZPjgozjgonjga9TdGFnZSAxNUHjga4yNTBrIHBlcmZvcm1hbmNlIHNjYWxpbmfjgpLpmLvlrrPjgZfjgarjgYTjgYzjgIFiaW9sb2d5LXJlYWR5IHYxIG91dHB1dOOBiuOCiOOBs+Wkp+imj+aooWNvaG9ydCB0cmlhZ2Xplovlp4vliY3jgavjga9QQVNT44KS6KaB5rGC44GZ44KL44CCCgotLS0KCiMjIDguIFBlcmZvcm1hbmNl44Go44Gu5YiG6ZuiCgrlvZPpnaLjga9ydW50aW1l44KS5YiG44GR44Gm5aCx5ZGK44GZ44KL44CCCgpgYGB0ZXh0CmNvcmVfYmFtX3RvX2ZpbmFsX3J1bnRpbWUKYmlvbG9neV9lbnJpY2htZW50X3J1bnRpbWUKaW50ZXJwcmV0YXRpb25fYW5kX3JhbmtpbmdfcnVudGltZQpgYGAKCmNvcmUgcGVyZm9ybWFuY2Xjga4zMOWIhnRhcmdldCAvIDYw5YiGaGFyZCBjZWlsaW5n44KS44CBYW5ub3RhdGlvbuOChGNvaG9ydCByYW5raW5n5Yem55CG44Gn5puW5pin44Gr44GX44Gq44GE44CCCgpzaWRlY2Fy55Sf5oiQ44GvY29yZSBwYWNrYWdlIHB1YmxpY2F0aW9u5b6M44Gr54us56uL5YaN5a6f6KGM5Y+v6IO944Go44GX44CBY29yZSBjYWxsZXLjgpLlho3lrp/ooYzjgZvjgZrjgathbm5vdGF0aW9u44CBcGhhc2luZ+OAgXRyYW5zY3JpcHQgYXNzaWdubWVudOOAgXJhbmtpbmcgbW9kZWzjgpLmm7TmlrDjgafjgY3jgovoqK3oqIjjgajjgZnjgovjgIIKCi0tLQoKIyMgOS4g5a6f6KOF6aCG5bqPCgoxLiDmnKxjb250cmFjdOOCklNTT1TjgbjnmbvpjLLjgZfjgIFHMjDigJNHMjPjgpJPUEVO44Go44GX44Gm5piO56S6CjIuIFN0YWdlIDE1QSByZXN0YXJ0L3Jlc3VtZeOBqGRldGVybWluaXN0aWMgMjUwayBzY2FsaW5n44KS5a6M5LqGCjMuIOePvmNvcmUgNS10YWJsZeOCkuWvvuixoeOBq+ato+W8j+OBqkJpb2xvZ3ktcmVhZHkgLyBpbnRlcnByZXRhdGlvbi1yZWFkeSBhdWRpdOOCkuWun+aWvQo0LiBzaWRlY2FyIHNjaGVtYeOBqHZhbGlkYXRvcuOCkmZyZWV6ZQo1LiBtb2xlY3VsZSBiaW9sb2d5IHZpZXfjgahzYW1wbGXDl2xvY3VzIHN1bW1hcnnjgpLlrp/oo4UKNi4gcHVycG9zZS1zcGVjaWZpYyByYW5raW5nIGxhbmVz44KSdmVyc2lvbmVk44Gr5a6f6KOFCjcuIGNhbmRpZGF0ZSBkb3NzaWVy44GodHJhY2VhYmlsaXR5IHZhbGlkYXRvcuOCkuWun+ijhQo4LiB0cnV0aC1iZWFyaW5nIGRpc2Vhc2UgLyBzeW50aGV0aWMgLyBvcnRob2dvbmFsIGRhdGHjgadiaW9sb2d5IGNsYWltc+OCkuaknOiovAoKLS0tCgojIyAxMC4g56aB5q2i5LqL6aCFCgpgYGB0ZXh0CmNvcmUgcmVwZWF0IGV2ZW50c+OCknN1bW1hcnnjgaDjgZHjgavnva7mj5vjgZfjgarjgYQKcmVhZF9pZOOCkueEoeadoeS7tuOBq+eLrOeri21vbGVjdWxl44Go5ZG844Gw44Gq44GECnBoYXNlIGV2aWRlbmNl44Gq44GX44GrYWxsZWxlL2hhcGxvdHlwZeOBuOeUn+eJqeWtpueahOaEj+WRs+OCkuS7mOOBkeOBquOBhApjZW5zb3JlZCByZWFk44KSZXhhY3QgbGVuZ3Ro44Go44GX44Gm6ZuG6KiI44GX44Gq44GECnRlY2huaWNhbCBjb25maWRlbmNl44KScGF0aG9nZW5pY2l0eeOBqOWRvOOBsOOBquOBhAprbm93bi1kaXNlYXNlIGxvY3Vz44KSZ2VuZXJpYyByYW5raW5n6Za+5YCk44Gn5raI44GV44Gq44GECuWNmOS4gOe3j+WQiHNjb3Jl44Gg44GR44Gn5YWo56CU56m255uu55qE44KS5Luj6KGo44GV44Gb44Gq44GECnNpZGVjYXLmrKDmuKzjgpLpmbDmgKfmiYDopovjgajjgZfjgabmibHjgo/jgarjgYQKYGBgCg==' | base64 -d > "$CONTRACT_INSTALL"
printf '%s' 'Z2F0ZV9pZAlnYXRlCWxldmVsCWJsb2NraW5nX2Zvcl92MQlzdGF0dXMJZXZpZGVuY2Vfb3JfbmV4dF9hY3Rpb24KRzAxCUdlbmVyYWwgY2FsbGVyIGRldGVybWluaXN0aWMgYWNyb3NzIGhhc2ggc2VlZHMJYWxnb3JpdGhtCXRydWUJUEFTUwlTdGFnZSAxNEYyIGFuZCAxNEcKRzAyCVN5bnRoZXRpYyB0cnV0aCBhbmQgc2VtYW50aWMgaW52YXJpYW50cwlhbGdvcml0aG0JdHJ1ZQlQQVNTCVN0YWdlIDE0RwpHMDMJUHl0aG9uL25hdGl2ZSAxMDBrIGV4YWN0IHBhcml0eQlpbXBsZW1lbnRhdGlvbgl0cnVlCVBBU1MJU3RhZ2UgMTRHIGFsbCAzODg1NzEgcm93cwpHMDQJTmF0aXZlIGNhbGxlci1vbmx5IHByb2plY3RlZCA1LjMxTSBydW50aW1lIDw9MzAgbWluCXBlcmZvcm1hbmNlCWZhbHNlCVBBU1MJU3RhZ2UgMTRHIHByb2plY3RlZCAxOC45MCBtaW4KRzA1CTEwMGsgcHJlcGFyZWQtam9iL25hdGl2ZS1jYWxsZXIgdG8gdmFsaWRhdGVkIGZpbmFsLWV2aWRlbmNlIHBhY2thZ2UJcHJvZHVjdGlvbgl0cnVlCVBBU1MJU3RhZ2UxNEsyLzE0TDI7IHN0YXJ0cyBmcm9tIGZyb3plbiBtb3RpZi9wcm9qZWN0aW9uIGpvYnMsIG5vdCBCQU0KRzA2CTVNLXJlYWQgQkFNLWlucHV0IHJ1bnRpbWUgPD02MCBtaW4JcGVyZm9ybWFuY2UJdHJ1ZQlPUEVOCVN0YWdlMTVBIHYwLjIuMi4xIDEwMGsgbGluZWFyIHByb2plY3Rpb24gaXMgNTguMjMgbWluLCBidXQgZGV0ZXJtaW5pc3RpYyAyNTBrL2ludGVybWVkaWF0ZSBzY2FsaW5nIGFuZCBlbXBpcmljYWwgZnVsbC1zY2FsZSBydW50aW1lIHJlbWFpbiB1bnZhbGlkYXRlZApHMDcJNU0tcmVhZCByZXN0YXJ0YWJpbGl0eS9tZW1vcnkvYXJ0aWZhY3QgYXVkaXQJcHJvZHVjdGlvbgl0cnVlCU9QRU4JMTAwayBzZWxlY3RpdmUgY2FsbGVyLWNoZWNrcG9pbnQtdG8tZmluYWwgcmVzdGFydCBQQVNTOyB1cHN0cmVhbSBhcmJpdHJhcnktc3RhZ2UgcmVjb3ZlcnksIHBlYWstbWVtb3J5IHNjYWxpbmcsIGFuZCBmdWxsLXNjYWxlIGF1ZGl0IHJlbWFpbiBvcGVuCkcwOAlSZWFsIHRydXRoLWJlYXJpbmcgYmlvbG9naWNhbCB2YWxpZGF0aW9uCWJpb2xvZ3kJdHJ1ZQlPUEVOCURpc2Vhc2Uvc3ludGhldGljLVJOQS9vcnRob2dvbmFsIHRydXRoIGRhdGEKRzA5CUxhcmdlLWNvaG9ydCBSTkEgdGVjaG5pY2FsL2JhY2tncm91bmQgZGlzdHJpYnV0aW9uCXBvcHVsYXRpb24JZmFsc2UJT1BFTglEZWZlciB1bnRpbCBwcm9kdWN0aW9uIGNhbGxlciBzdGFibGUgYW5kIGZhc3QKRzEwCUZBU1RRLXRvLWZpbmFsIG1hcHBpbmctaW5jbHVzaXZlIHBlcmZvcm1hbmNlCWNvbnZlbmllbmNlCWZhbHNlCU9QRU4JUmVwb3J0IG1pbmltYXAyIHNlcGFyYXRlbHkKRzExCU1pc21hdGNoL2luZGVsL2ludGVycnVwdGlvbi9wdXJpdHkvTFBTIHByZXNlcnZlZCBzZXBhcmF0ZWx5CXNjaGVtYV9jb250cmFjdAl0cnVlCVBBU1MJU2NoZW1hIHYwLjQuMiByZXRhaW5zIHNlcGFyYXRlIGZpZWxkcyBhbmQgZXhwbGljaXQgbWlzc2luZ25lc3MKRzEyCUJpb2xvZ2ljYWwtdnMtdGVjaG5pY2FsIG9yaWdpbiBjbGFzc2lmaWVyIHRydXRoIHZhbGlkYXRpb24Jc2NoZW1hX2NvbnRyYWN0CWZhbHNlCU9QRU4JRGV2ZWxvcCBvbmx5IGFmdGVyIHRydXRoLWJlYXJpbmcgZXZpZGVuY2U7IGN1cnJlbnQgcGFja2FnZSB1c2VzIE5PVF9BU1NFU1NFRApHMTMJUmVhZC1sZXZlbCBSTkEgcmVwZWF0LWxlbmd0aCBkaXN0cmlidXRpb24gcmV0YWluZWQJc2NoZW1hX2NvbnRyYWN0CXRydWUJUEFTUwlyZXBlYXRfZXZlbnRzIHJlbWFpbnMgc291cmNlIG9mIHRydXRoCkcxNAlSTkEgcmVwZWF0LWxlbmd0aCBjbHVzdGVyaW5nIGFsZ29yaXRobSB2YWxpZGF0ZWQJc2NoZW1hX2NvbnRyYWN0CWZhbHNlCU9QRU4JSW1wbGVtZW50IGFmdGVyIHByb2R1Y3Rpb24gbWF0ZXJpYWxpemF0aW9uIGFuZCBzdWZmaWNpZW50IHNhbWUtbG9jdXMgc3VwcG9ydApHMTUJQWxsZWxlL2hhcGxvdHlwZSBsYWJlbHMgcHJvaGliaXRlZCB3aXRob3V0IHBoYXNlIGV2aWRlbmNlCXNjaGVtYV9jb250cmFjdAl0cnVlCVBBU1MJVmFsaWRhdG9yL2NvbnRyYWN0IHJlamVjdHMgdW5zdXBwb3J0ZWQgYmlvbG9naWNhbCBhbGxlbGUgbGFiZWxzCkcxNglDZW5zb3JlZC9jb250ZXh0LWxpbWl0ZWQgcmVhZHMgbm90IG5haXZlbHkgbWl4ZWQgYXMgZXhhY3Qgb2JzZXJ2YXRpb25zCXNjaGVtYV9jb250cmFjdAl0cnVlCVBBU1MJRXhhY3Qtb25seSBvciBleHBsaWNpdCBjZW5zb3ItYXdhcmUgaGFuZGxpbmcgcmVxdWlyZWQKRzE3CTEwMGsgbWFwcGluZy1jb21wbGV0ZSBCQU0gaW5wdXQgdG8gdmFsaWRhdGVkIHNjaGVtYSB2MC40LjIgcGFja2FnZQlwcm9kdWN0aW9uCXRydWUJUEFTUwlTdGFnZTE1QSByZWZlcmVuY2UgdjAuMS4zIGFuZCBleGFjdC1wYXJpdHkgcGVyZm9ybWFuY2UgdjAuMi4yLjEKRzE4CUNhbGxlZCBub24tbG9jdXMtYW5jaG9yZWQgYXR0ZW1wdHMgcmV0YWluZWQgYnV0IG5vdCBldmVudGl6ZWQJbWF0ZXJpYWxpemF0aW9uCXRydWUJUEFTUwkxOCBhdHRlbXB0cyByZXRhaW5lZCBsb3NzbGVzc2x5IGFuZCBub3QgZXZlbnRpemVkCkcxOQlmYWlsdXJlX2NvZGUvcWNfZmxhZ3MvbWF0ZXJpYWxpemF0aW9uX3N0YXR1cyBzZW1hbnRpY3MgYXJlIGRpc3RpbmN0CXNjaGVtYV9jb250cmFjdAl0cnVlCVBBU1MJU3RhZ2UxNEwyIGNvbnRyYWN0CkcyMAlSZWFkLWtleWVkIGJpb2xvZ3kgam9pbmFiaWxpdHkgZm9yIHRyYW5zY3JpcHQsIGhhcGxvdHlwZSwgb2JzZXJ2YWJpbGl0eSwgYW5kIG1vbGVjdWxlIGluZGVwZW5kZW5jZQliaW9sb2d5X291dHB1dAl0cnVlCU9QRU4JRnJlZXplIGFuZCB2YWxpZGF0ZSBmb3VyIHZlcnNpb25lZCBzaWRlY2FyIHNjaGVtYXMgYWZ0ZXIgU3RhZ2UxNUEgc2NhbGluZyBhcmNoaXRlY3R1cmUgc3RhYmlsaXplcwpHMjEJTW9sZWN1bGUtbGV2ZWwgZGlzdHJpYnV0aW9uIHJldGFpbmVkIHRocm91Z2ggc2FtcGxlLWJ5LWxvY3VzIHN1bW1hcml6YXRpb24JaW50ZXJwcmV0YXRpb25fb3V0cHV0CXRydWUJT1BFTglJbXBsZW1lbnQgbW9sZWN1bGVfcmVwZWF0X3N0YXRlIGFuZCBjZW5zb3ItYXdhcmUgc2FtcGxlX2xvY3VzX3N1bW1hcnkgd2l0aG91dCBkaXNjYXJkaW5nIGNvcmUgZXZlbnRzCkcyMglQdXJwb3NlLXNwZWNpZmljIHJhbmtpbmcgbGFuZXMgd2l0aCB1bmNvbmRpdGlvbmFsIGtub3duLWRpc2Vhc2UgcmV0ZW50aW9uCWludGVycHJldGF0aW9uX291dHB1dAl0cnVlCU9QRU4JSW1wbGVtZW50IHNlcGFyYXRlIEtOT1dOX0RJU0VBU0UsIEVYUEFOU0lPTl9ESVNDT1ZFUlksIFJOQV9QUk9DRVNTSU5HLCBSRVBFQVRfSEVURVJPR0VORUlUWSwgSEFQTE9UWVBFX0NPTlRST0xMRUQsIGFuZCBURUNITklDQUxfQ09ORklERU5DRSBsYW5lcwpHMjMJUmVzZWFyY2hlci1mYWNpbmcgY2FuZGlkYXRlIGRvc3NpZXIgaXMgZnVsbHkgdHJhY2VhYmxlIHRvIGNvcmUgYW5kIHNpZGVjYXIgZXZpZGVuY2UJaW50ZXJwcmV0YXRpb25fb3V0cHV0CXRydWUJT1BFTglJbXBsZW1lbnQgZG9zc2llciBzY2hlbWEgYW5kIHJldmVyc2UtdHJhY2VhYmlsaXR5IHZhbGlkYXRvciBiZWZvcmUgYmlvbG9neS1yZWFkeSB2MS9jb2hvcnQgdHJpYWdlCg==' | base64 -d > "$GATES_INSTALL"
[[ "$(sha256_file "$CONTRACT_INSTALL")" == "$EXPECTED_CONTRACT_SHA" ]] || die "installed biology contract SHA mismatch"
[[ "$(sha256_file "$GATES_INSTALL")" == "$EXPECTED_GATES_SHA" ]] || die "installed release gates SHA mismatch"

"$PYTHON_BIN" - "$SSOT_CLI" <<'PY_PATCH'
from pathlib import Path
import sys
path=Path(sys.argv[1])
text=path.read_text(encoding="utf-8")
marker='# Stage 15A restart/resume and biology-ready output contract registration v0.1.0'
block='    # Stage 15A restart/resume and biology-ready output contract registration v0.1.0\n    stage15a_restart_effective_at = "2026-08-08T13:40:00+00:00"\n    stage15a_restart_run_id = "ENCSR307SHM_pilot100k_mm2splice_v1"\n    stage15a_restart_stage_key = "15A_RESTART_RESUME_VALIDATION"\n    stage15a_biology_stage_key = "BIOLOGY_READY_OUTPUT_AUDIT"\n\n    stage15a_restart_root = project_root / "qc/15_stage15a_bam_to_final/ENCSR307SHM_pilot100k_mm2splice_v1/v0.2.3_restart_resume_100k"\n    stage15a_restart_result_root = project_root / "results/15_stage15a_bam_to_final/ENCSR307SHM_pilot100k_mm2splice_v1/v0.2.3_restart_resume_100k"\n    stage15a_restart_qc = stage15a_restart_root / "stage15a_restart_resume_100k.qc.tsv"\n    stage15a_restart_prepare_qc = stage15a_restart_root / "stage15a_restart_prepare.qc.tsv"\n    stage15a_restart_noop_qc = stage15a_restart_root / "stage15a_restart_noop.qc.tsv"\n    stage15a_restart_comparison = stage15a_restart_root / "comparison/stage15a_performance_package_comparison.tsv"\n    stage15a_restart_checkpoint_manifest = stage15a_restart_result_root / "checkpoints/checkpoint_manifest.tsv"\n    stage15a_restart_package_manifest = stage15a_restart_result_root / "package_resume/package_manifest.tsv"\n    stage15a_restart_runner = project_root / "scripts/rnatr_stage15a_restart_resume_100k_v0.1.0.py"\n    stage15a_restart_installer = project_root / "scripts/rnatr_stage15a_restart_resume_100k_v010.sh"\n    stage15a_biology_contract = project_root / "docs/stage15a/RNA_TR_Scout_Biology_ready_interpretation_output_contract_v0.1.0.md"\n    stage15a_release_gates_v023 = project_root / "validation/release_gates_v0.2.3.tsv"\n\n    def stage15a_metric_map(path: Path) -> dict[str, str]:\n        header, rows = read_tsv(path)\n        if header != ["metric", "value"]:\n            raise SSOTError(f"expected metric/value TSV: {path}")\n        return {row["metric"]: row["value"] for row in rows}\n\n    stage15a_restart_values = stage15a_metric_map(stage15a_restart_qc)\n    stage15a_restart_expected = {\n        "stage_version": "rnatr_stage15a_restart_resume_100k_v0.1.0",\n        "run_id": stage15a_restart_run_id,\n        "source_performance_version": "v0.2.2.1_performance",\n        "restart_scope": "FRESH_CALLER_CHECKPOINT_TO_FINAL_WITH_SELECTIVE_MATERIALIZER_RESUME",\n        "checkpoint_rows_verified": "138",\n        "checkpoint_negative_fixture_rejected": "PASS",\n        "completed_caller_reused_on_resume": "true",\n        "partial_package_published_before_resume": "false",\n        "resumed_materializer_logical_parity": "true",\n        "package_exact_logical_parity": "true",\n        "package_exact_raw_parity": "true",\n        "frozen_tsv_validators": "PASS",\n        "parallel_exact_component_package_validator": "PASS",\n        "frozen_package_validator_postpublication": "PASS",\n        "negative_fixture_failure_parity": "PASS",\n        "atomic_publication": "PASS",\n        "active_pipeline_modified": "false",\n        "ssot_modified": "false",\n        "full_5_31m_run_started": "false",\n        "restart_resume_validated": "true",\n        "stage15a_overall_status": "IN_PROGRESS",\n        "audit_status": "PASS",\n        "next_gate": "BUILD_AND_RUN_DETERMINISTIC_250K_BAM_INPUT_SCALING_NOT_FULL_5_31M",\n    }\n    for stage15a_restart_metric, stage15a_restart_wanted in stage15a_restart_expected.items():\n        stage15a_restart_observed = stage15a_restart_values.get(stage15a_restart_metric)\n        if stage15a_restart_observed != stage15a_restart_wanted:\n            raise SSOTError(\n                f"Stage 15A restart QC mismatch {stage15a_restart_metric}: "\n                f"{stage15a_restart_observed!r} != {stage15a_restart_wanted!r}"\n            )\n\n    stage15a_prepare_values = stage15a_metric_map(stage15a_restart_prepare_qc)\n    for key, wanted in {\n        "fresh_caller_logical_parity": "true",\n        "partial_package_published": "false",\n        "intentional_interruption_status": "PASS",\n        "expected_exit_code": "75",\n    }.items():\n        if stage15a_prepare_values.get(key) != wanted:\n            raise SSOTError(f"Stage 15A prepare QC mismatch {key}")\n\n    stage15a_noop_values = stage15a_metric_map(stage15a_restart_noop_qc)\n    for key, wanted in {\n        "resume_mode": "NOOP_COMPLETE_CHECKPOINT",\n        "package_unchanged": "true",\n        "audit_status": "PASS",\n    }.items():\n        if stage15a_noop_values.get(key) != wanted:\n            raise SSOTError(f"Stage 15A no-op QC mismatch {key}")\n\n    stage15a_comparison_header, stage15a_comparison_rows = read_tsv(stage15a_restart_comparison)\n    if len(stage15a_comparison_rows) != 10:\n        raise SSOTError(f"expected 10 restart package comparison rows, found {len(stage15a_comparison_rows)}")\n    for row in stage15a_comparison_rows:\n        if row.get("header_equal") != "true" or row.get("raw_equal") != "true" or row.get("logical_equal") != "true":\n            raise SSOTError(f"restart package parity failed for {row.get(\'role\')}")\n\n    ensure_stage(\n        conn,\n        stage15a_restart_stage_key,\n        order=151.1,\n        name="Stage 15A selective restart/resume validation",\n        purpose="Validate checkpoint integrity, intentional interruption, selective materializer resume, exact package parity, no-op resume, and atomic publication for the 100k isolated performance candidate.",\n        category="production_validation",\n        status="IMPLEMENTED_WITH_GATE",\n        notes="100k caller-checkpoint-to-final selective restart PASS. This does not establish arbitrary upstream-stage recovery, peak-memory scaling, or full 5.31M restartability.",\n    )\n    conn.execute(\n        """\n        INSERT OR REPLACE INTO implementations(\n            implementation_id,stage_key,version,script_path,script_sha256,\n            validator_path,validator_sha256,package_version,parameters_json,\n            lifecycle_status,supersedes_implementation_id,rationale,\n            evidence_path,effective_at\n        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)\n        """,\n        (\n            "impl_stage15a_restart_resume_100k_v0_1_0",\n            stage15a_restart_stage_key,\n            "rnatr_stage15a_restart_resume_100k_v0.1.0",\n            str(stage15a_restart_runner),\n            sha256_file(stage15a_restart_runner),\n            None,\n            None,\n            "evidence_schema_v0.4.2",\n            json.dumps(\n                {\n                    "scope": "fresh_caller_checkpoint_to_final_selective_materializer_resume",\n                    "source_performance_version": "v0.2.2.1_performance",\n                    "intentional_exit_code": 75,\n                    "checkpoint_rows": 138,\n                    "adopted_upstream_shards": 12,\n                    "resumed_materializer_shards": 1,\n                    "second_resume_noop_required": True,\n                    "full_5_31m_run": False,\n                },\n                ensure_ascii=False,\n                sort_keys=True,\n            ),\n            "PROVISIONAL",\n            None,\n            "Validated selective 100k restart/resume with exact raw and logical package parity, negative checkpoint rejection, no partial publication, atomic publication, and an unchanged no-op second resume. Full-scale and arbitrary upstream-stage restart remain open.",\n            str(stage15a_restart_qc),\n            stage15a_restart_effective_at,\n        ),\n    )\n\n    add_decision(\n        conn,\n        key="stage15a_restart_resume_scope_v0_1_0",\n        category="production_validation",\n        title="Accept selective 100k restart/resume and retain full-scale restart gate",\n        statement="Stage 15A v0.1.0 passes fresh-caller-checkpoint-to-final selective restart/resume for the 100k exact-parity performance candidate. G07 remains OPEN because arbitrary upstream-stage recovery, peak-memory behavior, and full-scale restartability are not yet validated.",\n        status="ACTIVE",\n        confidence="HIGH",\n        rationale="An intentional exit 75 occurred after a fresh caller checkpoint and before one materializer shard; no partial final package was published. Resume verified 138 checkpoint rows, reused completed work, rebuilt a byte-identical package, and a second resume was a no-op.",\n        evidence_path=str(stage15a_restart_qc),\n        effective_at=stage15a_restart_effective_at,\n    )\n\n    add_interpretation(\n        conn,\n        key="stage15a_restart_resume_100k_scope",\n        fact="The 100k restart audit completed with checkpoint integrity, negative-fixture rejection, selective reuse, exact package parity, atomic publication, and no-op second resume all PASS.",\n        interpretation="The v0.2.2.1 production candidate has a validated checkpoint-to-final restart path suitable for proceeding to deterministic 250k scaling.",\n        do_not="Do not interpret this as validation of arbitrary interruption at 11b/11d3/11e, full-scale memory safety, empirical 5.31M restartability, Stage 15A completion, or authorization for the full 5.31M run.",\n        confidence="HIGH",\n        evidence_path=str(stage15a_restart_qc),\n        evidence_metrics={\n            "checkpoint_rows_verified": 138,\n            "package_exact_logical_parity": True,\n            "package_exact_raw_parity": True,\n            "partial_package_published_before_resume": False,\n            "restart_resume_validated": True,\n        },\n        status="ACTIVE",\n        effective_at=stage15a_restart_effective_at,\n    )\n\n    add_contract(\n        conn,\n        key="stage15a_restart_resume_v0_1_0",\n        name="Stage 15A selective restart/resume contract v0.1.0",\n        state="100K_SELECTIVE_RESTART_PASS_250K_AND_FULL_SCALE_OPEN",\n        statement="The current candidate must verify checkpoint hashes, reject corrupt checkpoints, avoid partial publication, reuse completed caller/materializer shards, rebuild an exact-parity package, publish atomically, and produce an unchanged no-op second resume. The validated scope is caller-checkpoint-to-final at 100k, not arbitrary-stage or full-scale restart.",\n        implementation_id="impl_stage15a_restart_resume_100k_v0_1_0",\n        evidence_path=str(stage15a_restart_qc),\n    )\n\n    add_contract(\n        conn,\n        key="stage15a_performance_candidate_v0221",\n        name="Stage 15A performance candidate v0.2.2.1",\n        state="100K_PROJECTED_60MIN_PASS_RESTART_PASS_250K_OPEN",\n        statement="v0.2.2.1 remains the current exact-parity isolated performance candidate. Its 65.763639-second 100k timer projects to 58.230371 minutes for 5.31M and its selective 100k caller-checkpoint-to-final restart path is validated. Deterministic 250k/intermediate scaling, arbitrary upstream-stage recovery, empirical full-scale runtime, and the 30-minute target remain open.",\n        implementation_id="impl_stage15a_performance_v0_2_2_1",\n        evidence_path=str(stage15a_restart_qc),\n    )\n\n    conn.execute(\n        """\n        INSERT OR REPLACE INTO limitations(\n            limitation_key,statement,severity,status,mitigation,evidence_path,effective_at\n        ) VALUES(?,?,?,?,?,?,?)\n        """,\n        (\n            "STAGE15A_RESTART_SCOPE_IS_SELECTIVE_100K",\n            "Restart/resume is validated only from a fresh caller checkpoint through selective materializer resume, merge, validation, and atomic publication at 100k. Arbitrary interruption at upstream stages, peak-memory scaling, and full 5.31M restartability are not established.",\n            "HIGH",\n            "ACTIVE",\n            "Run deterministic 250k scaling with memory and temporary-byte capture; extend checkpoint coverage before any full-depth execution.",\n            str(stage15a_restart_qc),\n            stage15a_restart_effective_at,\n        ),\n    )\n\n    conn.execute(\n        """\n        INSERT OR REPLACE INTO open_questions(\n            question_key,question,priority,status,blocking,next_action,evidence_path,effective_at\n        ) VALUES(?,?,?,?,?,?,?,?)\n        """,\n        (\n            "GENERAL_CALLER_PRODUCTION_INTEGRATION",\n            "Can the exact-parity Stage 15A candidate preserve its projected <=60-minute runtime, determinism, bounded memory, artifact completeness, and restart contract as BAM input increases?",\n            "CRITICAL",\n            "OPEN",\n            1,\n            "Run deterministic 250k BAM-input scaling next. Capture stage wall time, peak RSS, temporary bytes, alignment/candidate/window/output complexity variables, package reproducibility, and checkpoint behavior. Do not run full 5.31M or change current_pipeline.",\n            str(stage15a_restart_qc),\n            stage15a_restart_effective_at,\n        ),\n    )\n\n    ensure_stage(\n        conn,\n        stage15a_biology_stage_key,\n        order=152.0,\n        name="Biology-ready and interpretation-ready output audit",\n        purpose="Preserve lossless molecule-level repeat architecture while adding read-keyed transcript, haplotype, observability, and molecule-independence sidecars plus traceable sample-level interpretation outputs.",\n        category="biology_output_contract",\n        status="PAUSED",\n        notes="Contract designed and registered. Implementation begins after Stage 15A scaling architecture stabilizes; G20-G23 remain OPEN and are blocking for biology-ready v1/cohort triage, not for the immediate 250k performance benchmark.",\n    )\n\n    add_decision(\n        conn,\n        key="biology_ready_core_sidecar_separation_v0_1_0",\n        category="biology_output_architecture",\n        title="Keep schema v0.4.2 core repeat tables stable and add read-keyed biology sidecars",\n        statement="The v0.4.2 core 5-table package remains the repeat-measurement source of truth. Transcript/isoform, haplotype, observability, and duplicate/molecule-independence states will be added as versioned read/evidence-keyed sidecars rather than by inflating or rewriting the core tables.",\n        status="ACTIVE",\n        confidence="HIGH",\n        rationale="The core already preserves repeat length, purity, LPS, segments, interruptions, alignment discordance, geometry, and censoring. The missing biology dimensions have different provenance, update cadence, missingness, and validation requirements and therefore belong in independently versioned sidecars.",\n        evidence_path=str(stage15a_biology_contract),\n        effective_at=stage15a_restart_effective_at,\n    )\n\n    add_decision(\n        conn,\n        key="purpose_specific_candidate_ranking_lanes_v0_1_0",\n        category="interpretation_output_architecture",\n        title="Use purpose-specific ranking lanes rather than one universal score",\n        statement="Candidate triage will maintain separate KNOWN_DISEASE, EXPANSION_DISCOVERY, RNA_PROCESSING, REPEAT_HETEROGENEITY, HAPLOTYPE_CONTROLLED, and TECHNICAL_CONFIDENCE lanes. Known disease repeats are retained independently of generic ranking thresholds.",\n        status="ACTIVE",\n        confidence="HIGH",\n        rationale="Expansion discovery, RNA processing, heterogeneity, phase-controlled evidence, and technical confidence answer different scientific questions and should not be collapsed into a single opaque score.",\n        evidence_path=str(stage15a_biology_contract),\n        effective_at=stage15a_restart_effective_at,\n    )\n\n    add_interpretation(\n        conn,\n        key="core_v042_repeat_ready_not_biology_ready",\n        fact="The v0.4.2 core package losslessly preserves read-level repeat calls/events, repeat length state, purity, LPS, compound segments, structured interruptions, discordance operations, geometry, and censoring, but it does not yet materialize transcript/isoform, haplotype, explicit observability, molecule-independence, sample-locus summary, multi-lane ranking, or dossier outputs.",\n        interpretation="The current output is repeat-ready and suitable as the immutable substrate for biology enrichment, but it is not yet biology-ready or interpretation-ready for large-cohort triage.",\n        do_not="Do not call read_id an independent biological molecule without evidence, infer haplotypes or allele meaning without phase evidence, treat sidecar missingness as a negative result, or replace molecule-level distributions with summary-only output.",\n        confidence="HIGH",\n        evidence_path=str(stage15a_biology_contract),\n        evidence_metrics={\n            "core_table_count": 5,\n            "biology_sidecar_count_designed": 4,\n            "ranking_lane_count_designed": 6,\n            "biology_ready_status": "NOT_IMPLEMENTED",\n        },\n        status="ACTIVE",\n        effective_at=stage15a_restart_effective_at,\n    )\n\n    add_contract(\n        conn,\n        key="biology_ready_read_keyed_sidecars_v0_1_0",\n        name="Biology-ready read-keyed sidecar contract v0.1.0",\n        state="DESIGNED_NOT_IMPLEMENTED",\n        statement="Versioned sidecars must provide transcript/isoform state, haplotype state, observability, and molecule independence with explicit missingness and provenance, joinable by read_id/evidence_id without altering the core repeat source of truth.",\n        implementation_id=None,\n        evidence_path=str(stage15a_biology_contract),\n    )\n    add_contract(\n        conn,\n        key="interpretation_hierarchy_v0_1_0",\n        name="Molecule-to-dossier interpretation hierarchy v0.1.0",\n        state="DESIGNED_NOT_IMPLEMENTED",\n        statement="Interpretation proceeds from raw repeat evidence to molecule_repeat_state, censor-aware sample_locus_summary, purpose-specific ranking lanes, and researcher-facing dossier. Molecule-level distributions and reverse traceability are mandatory.",\n        implementation_id=None,\n        evidence_path=str(stage15a_biology_contract),\n    )\n\n    conn.execute(\n        """\n        INSERT OR REPLACE INTO limitations(\n            limitation_key,statement,severity,status,mitigation,evidence_path,effective_at\n        ) VALUES(?,?,?,?,?,?,?)\n        """,\n        (\n            "CORE_V042_NOT_YET_BIOLOGY_OR_INTERPRETATION_READY",\n            "The core package does not yet contain versioned transcript/isoform, haplotype, explicit observability, or molecule-independence sidecars and does not yet generate sample-locus summaries, purpose-specific ranking lanes, or researcher-facing dossiers.",\n            "HIGH",\n            "ACTIVE",\n            "Complete the formal output audit and implement G20-G23 after Stage 15A scaling architecture stabilizes, while preserving the core 5-table package and read-level distributions.",\n            str(stage15a_biology_contract),\n            stage15a_restart_effective_at,\n        ),\n    )\n\n    conn.execute(\n        """\n        INSERT OR REPLACE INTO open_questions(\n            question_key,question,priority,status,blocking,next_action,evidence_path,effective_at\n        ) VALUES(?,?,?,?,?,?,?,?)\n        """,\n        (\n            "BIOLOGY_READY_INTERPRETATION_OUTPUT_AUDIT",\n            "Can the final output support same-haplotype molecule-level repeat heterogeneity, repeat-to-isoform/splicing association, observability-aware inference, molecule-independence-aware support, purpose-specific triage, and fully traceable researcher dossiers without losing core read-level repeat information?",\n            "CRITICAL",\n            "OPEN",\n            1,\n            "After deterministic scaling stabilizes the production architecture, audit the current core package against G20-G23, freeze sidecar schemas and validators, then implement molecule_repeat_state, sample_locus_summary, ranking lanes, and dossier traceability.",\n            str(stage15a_biology_contract),\n            stage15a_restart_effective_at,\n        ),\n    )\n\n    for stage15a_restart_source_path, stage15a_restart_source_type in [\n        (stage15a_restart_qc, "stage15a_restart_resume_qc"),\n        (stage15a_restart_prepare_qc, "stage15a_restart_prepare_qc"),\n        (stage15a_restart_noop_qc, "stage15a_restart_noop_qc"),\n        (stage15a_restart_comparison, "stage15a_restart_package_comparison"),\n        (stage15a_restart_checkpoint_manifest, "stage15a_restart_checkpoint_manifest"),\n        (stage15a_restart_package_manifest, "stage15a_restart_package_manifest"),\n        (stage15a_restart_runner, "stage15a_restart_runner"),\n        (stage15a_restart_installer, "stage15a_restart_installer"),\n        (stage15a_biology_contract, "biology_ready_output_contract"),\n        (stage15a_release_gates_v023, "release_gates"),\n    ]:\n        source_document(conn, stage15a_restart_source_path, stage15a_restart_source_type, force_hash=True)\n\n    for metric_name, metric_value, metric_unit in [\n        ("restart_resume_validated", 1, None),\n        ("restart_checkpoint_rows_verified", 138, "rows"),\n        ("restart_materializer_resume_seconds", float(stage15a_restart_values["materializer_resume_seconds"]), "seconds"),\n        ("restart_validator_seconds", float(stage15a_restart_values["validator_seconds"]), "seconds"),\n        ("restart_package_exact_raw_parity", 1, None),\n        ("restart_noop_manifest_unchanged", 1, None),\n    ]:\n        add_current_metric(\n            conn,\n            run_id=stage15a_restart_run_id,\n            stage_key=stage15a_restart_stage_key,\n            name=metric_name,\n            value=metric_value,\n            source_path=str(stage15a_restart_qc),\n            unit=metric_unit,\n        )'
anchor="\n\n\n    current_metrics = ["
if marker in text:
    raise SystemExit("SSOT source already contains restart/biology patch marker; refusing an ambiguous rerun")
if text.count(anchor) != 1:
    raise SystemExit(f"SSOT patch anchor count != 1: {text.count(anchor)}")
text=text.replace(anchor,"\n\n"+block+anchor,1)
compile(text,str(path),"exec")
tmp=path.with_suffix(path.suffix+".stage15a_restart_biology.part")
tmp.write_text(text,encoding="utf-8")
tmp.replace(path)
print("SSOT_RESTART_BIOLOGY_SOURCE_PATCH_PASS")
PY_PATCH

"$PYTHON_BIN" -m py_compile "$SSOT_CLI"
"$PYTHON_BIN" "$SSOT_CLI" --project-root "$PROJECT_ROOT" rebuild 2>&1 | tee "$LOG_ROOT/ssot_rebuild.log"
"$PYTHON_BIN" "$SSOT_CLI" --project-root "$PROJECT_ROOT" validate 2>&1 | tee "$LOG_ROOT/ssot_validate_after.log"

"$PYTHON_BIN" - "$SSOT_DB" "$WORK_ROOT/current_pipeline.after.tsv" "$WORK_ROOT/postcheck.tsv" <<'PY_POST'
import csv, sqlite3, sys
con=sqlite3.connect(sys.argv[1]); con.row_factory=sqlite3.Row
rows=con.execute("SELECT * FROM current_pipeline ORDER BY stage_order,stage_key").fetchall()
with open(sys.argv[2],"w",newline="",encoding="utf-8") as h:
    if rows:
        w=csv.DictWriter(h,fieldnames=rows[0].keys(),delimiter="	",lineterminator="\n")
        w.writeheader(); w.writerows(dict(r) for r in rows)
checks=[]
def check(name, ok, detail):
    checks.append((name,"PASS" if ok else "FAIL",str(detail)))
    if not ok: raise SystemExit(f"{name} failed: {detail}")
check("sqlite_integrity",con.execute("PRAGMA integrity_check").fetchone()[0]=="ok","ok")
check("foreign_keys",len(con.execute("PRAGMA foreign_key_check").fetchall())==0,0)
check("restart_impl",con.execute("SELECT COUNT(*) FROM implementations WHERE implementation_id='impl_stage15a_restart_resume_100k_v0_1_0' AND lifecycle_status='PROVISIONAL'").fetchone()[0]==1,1)
check("restart_contract",con.execute("SELECT COUNT(*) FROM algorithm_contracts WHERE component_key='stage15a_restart_resume_v0_1_0' AND implementation_state='100K_SELECTIVE_RESTART_PASS_250K_AND_FULL_SCALE_OPEN'").fetchone()[0]==1,1)
check("performance_contract_advanced",con.execute("SELECT COUNT(*) FROM algorithm_contracts WHERE component_key='stage15a_performance_candidate_v0221' AND implementation_state='100K_PROJECTED_60MIN_PASS_RESTART_PASS_250K_OPEN'").fetchone()[0]==1,1)
check("biology_contract",con.execute("SELECT COUNT(*) FROM algorithm_contracts WHERE component_key='biology_ready_read_keyed_sidecars_v0_1_0' AND implementation_state='DESIGNED_NOT_IMPLEMENTED'").fetchone()[0]==1,1)
check("interpretation_contract",con.execute("SELECT COUNT(*) FROM algorithm_contracts WHERE component_key='interpretation_hierarchy_v0_1_0' AND implementation_state='DESIGNED_NOT_IMPLEMENTED'").fetchone()[0]==1,1)
check("biology_open_question",con.execute("SELECT COUNT(*) FROM open_questions WHERE question_key='BIOLOGY_READY_INTERPRETATION_OUTPUT_AUDIT' AND status='OPEN'").fetchone()[0]==1,1)
check("restart_stage_not_active",con.execute("SELECT COUNT(*) FROM current_pipeline WHERE stage_key='15A_RESTART_RESUME_VALIDATION'").fetchone()[0]==0,0)
check("biology_stage_not_active",con.execute("SELECT COUNT(*) FROM current_pipeline WHERE stage_key='BIOLOGY_READY_OUTPUT_AUDIT'").fetchone()[0]==0,0)
check("current_pipeline_count",con.execute("SELECT COUNT(*) FROM current_pipeline").fetchone()[0]==11,11)
with open(sys.argv[3],"w",newline="",encoding="utf-8") as h:
    w=csv.writer(h,delimiter="	",lineterminator="\n"); w.writerow(["check","status","detail"]); w.writerows(checks)
PY_POST

cmp -s "$WORK_ROOT/current_pipeline.before.tsv" "$WORK_ROOT/current_pipeline.after.tsv" || die "current_pipeline changed"
[[ "$(sha256_file "$CORE_SCHEMA")" == "$CORE_SCHEMA_SHA_BEFORE" ]] || die "core schema changed"

CLI_SHA_AFTER="$(sha256_file "$SSOT_CLI")"
DB_SHA_AFTER="$(sha256_file "$SSOT_DB")"
PIPELINE_SHA="$(sha256_file "$WORK_ROOT/current_pipeline.after.tsv")"

cat > "$QC_INSTALL/stage15a_restart_biology_ssot_update.qc.tsv" <<EOF_QC
metric	value
update_version	$UPDATE_VERSION
run_id	$RUN_ID
ssot_cli_sha256_before	$EXPECTED_CLI_SHA
ssot_cli_sha256_after	$CLI_SHA_AFTER
ssot_db_sha256_before	$EXPECTED_DB_SHA
ssot_db_sha256_after	$DB_SHA_AFTER
active_pipeline_sha256_before	$PIPELINE_SHA
active_pipeline_sha256_after	$PIPELINE_SHA
active_pipeline_byte_identical	true
active_pipeline_stage_count	11
core_schema_modified	false
restart_resume_registered	true
restart_scope	FRESH_CALLER_CHECKPOINT_TO_FINAL_WITH_SELECTIVE_MATERIALIZER_RESUME
restart_resume_validated	true
full_scale_restart_validated	false
deterministic_250k_scaling	OPEN
biology_ready_contract_registered	true
biology_sidecars_implemented	false
interpretation_layer_implemented	false
release_gates_version	v0.2.3
stage15a_overall_status	IN_PROGRESS
full_5_31m_run_started	false
audit_status	PASS
next_gate	BUILD_AND_RUN_DETERMINISTIC_250K_BAM_INPUT_SCALING_NOT_FULL_5_31M
EOF_QC

cp -a "$WORK_ROOT/current_pipeline.before.tsv" "$META_INSTALL/"
cp -a "$WORK_ROOT/current_pipeline.after.tsv" "$META_INSTALL/"
cp -a "$WORK_ROOT/postcheck.tsv" "$META_INSTALL/"
cp -a "$CONTRACT_INSTALL" "$META_INSTALL/"
cp -a "$GATES_INSTALL" "$META_INSTALL/"
cp -a "$QC_INSTALL/stage15a_restart_biology_ssot_update.qc.tsv" "$META_INSTALL/"

mkdir -p "$BUNDLE_ROOT/qc" "$BUNDLE_ROOT/metadata" "$BUNDLE_ROOT/docs" "$BUNDLE_ROOT/validation" "$BUNDLE_ROOT/script" "$BUNDLE_ROOT/evidence" "$BUNDLE_ROOT/ssot"
cp -a "$QC_INSTALL/stage15a_restart_biology_ssot_update.qc.tsv" "$BUNDLE_ROOT/qc/"
cp -a "$LOG_ROOT" "$BUNDLE_ROOT/qc/logs"
cp -a "$WORK_ROOT/current_pipeline.before.tsv" "$WORK_ROOT/current_pipeline.after.tsv" "$WORK_ROOT/postcheck.tsv" "$BUNDLE_ROOT/metadata/"
cp -a "$CONTRACT_INSTALL" "$BUNDLE_ROOT/docs/"
cp -a "$GATES_INSTALL" "$BUNDLE_ROOT/validation/"
cp -a "$SCRIPT_INSTALL" "$BUNDLE_ROOT/script/"
cp -a "$RESTART_QC" "$PREPARE_QC" "$NOOP_QC" "$PACKAGE_COMPARISON" "$CHECKPOINT_MANIFEST" "$PACKAGE_MANIFEST" "$BUNDLE_ROOT/evidence/"
cp -a "$SSOT_SUMMARY" "$SSOT_CLI" "$SSOT_DB" "$BUNDLE_ROOT/ssot/"
cp -a "$SSOT_EXPORTS" "$BUNDLE_ROOT/ssot/exports"

"$PYTHON_BIN" - "$BUNDLE_ROOT" <<'PY_MANIFEST'
from pathlib import Path
import hashlib, csv, sys
root=Path(sys.argv[1]); rows=[]
for p in sorted(x for x in root.rglob('*') if x.is_file()):
    rows.append((str(p.relative_to(root)),p.stat().st_size,hashlib.sha256(p.read_bytes()).hexdigest()))
with (root/'artifact_manifest.tsv').open('w',newline='',encoding='utf-8') as h:
    w=csv.writer(h,delimiter='	',lineterminator='\n'); w.writerow(['path','bytes','sha256']); w.writerows(rows)
PY_MANIFEST

rm -f "$OUTPUT_BUNDLE" "$OUTPUT_BUNDLE.sha256"
tar -czf "$OUTPUT_BUNDLE" -C "$BUNDLE_ROOT" .
sha256sum "$OUTPUT_BUNDLE" | tee "$OUTPUT_BUNDLE.sha256"
SUCCESS=true

say ""
say "===== STAGE 15A RESTART + BIOLOGY CONTRACT SSOT UPDATE COMPLETE ====="
cat "$QC_INSTALL/stage15a_restart_biology_ssot_update.qc.tsv"
say "Output bundle: $OUTPUT_BUNDLE"
say "SHA file:      $OUTPUT_BUNDLE.sha256"
say "Next gate:     deterministic 250k BAM-input scaling; not full 5.31M"
