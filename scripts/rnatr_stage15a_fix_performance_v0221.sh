#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="/mnt/intelssd/rnatr_project"
RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"
PYTHON_BIN="/home/tokushimaneuro02/miniconda3/envs/rnatr-v03/bin/python"

OLD_RESULT="$PROJECT_ROOT/results/15_stage15a_bam_to_final/$RUN_ID/v0.2.2_performance"
OLD_QC="$PROJECT_ROOT/qc/15_stage15a_bam_to_final/$RUN_ID/v0.2.2_performance"
NEW_RESULT="$PROJECT_ROOT/results/15_stage15a_bam_to_final/$RUN_ID/v0.2.2.1_performance"
NEW_QC="$PROJECT_ROOT/qc/15_stage15a_bam_to_final/$RUN_ID/v0.2.2.1_performance"

OLD_RUNNER="$PROJECT_ROOT/scripts/rnatr_stage15a_run_performance_100k_v0.2.2.py"
OLD_VALIDATOR="$PROJECT_ROOT/scripts/rnatr_stage15a_validate_package_parallel_v0.2.2.py"
FAST_11E="$PROJECT_ROOT/scripts/rnatr_stage15a_fast_motif_jobs_v0.2.2.py"
NEW_RUNNER="$PROJECT_ROOT/scripts/rnatr_stage15a_run_performance_100k_v0.2.2.1.py"
NEW_VALIDATOR="$PROJECT_ROOT/scripts/rnatr_stage15a_validate_package_parallel_v0.2.2.1.py"
SELF_DST="$PROJECT_ROOT/scripts/rnatr_stage15a_fix_performance_v0221.sh"
DOC="$PROJECT_ROOT/docs/stage15a/RNA_TR_Scout_Stage15A_performance_validator_cli_fix_v0.2.2.1.md"
META_ROOT="$PROJECT_ROOT/metadata/stage15a/v0.2.2.1_performance"

OLD_RUNNER_SHA="2ac29866d08bb0e70d7d169d90346386eb9623c63f011cc0a68471822528f96f"
OLD_VALIDATOR_SHA="f3095a7f2af3099e8d960ebfa6d9b5380ba5e384d64122a386d6de49731ff9e2"
FAST_11E_SHA="4dd972027c8b906703fa00c19f2981a8455a1ad9fb2bcc863321505c6619a5f2"
EXPECTED_FAILURE="one or more frozen validators failed: PACKAGE"

DOWNLOADS="$HOME/Downloads"
CONSOLE="$DOWNLOADS/rnatr_stage15a_performance_100k_v0.2.2.1.console.log"
SUCCESS_BUNDLE="$DOWNLOADS/rnatr_stage15a_performance_100k_output_v0.2.2.1.tar.gz"
FAILURE_BUNDLE="$DOWNLOADS/rnatr_stage15a_performance_100k_failure_v0.2.2.1.tar.gz"
PACKAGE_STAGE=""

fail() {
    echo "ERROR: $*" >&2
    exit 2
}

sha_of() {
    sha256sum "$1" | awk '{print $1}'
}

metric() {
    local path="$1"
    local key="$2"
    awk -F '\t' -v key="$key" '$1==key {print $2}' "$path" | tail -n1 | tr -d '\015'
}

cleanup() {
    if [[ -n "${PACKAGE_STAGE:-}" && -d "$PACKAGE_STAGE" ]]; then
        rm -rf "$PACKAGE_STAGE"
    fi
}
trap cleanup EXIT

[[ -x "$PYTHON_BIN" ]] || fail "rnatr-v03 Python not found: $PYTHON_BIN"
[[ -s "$OLD_RUNNER" ]] || fail "missing installed v0.2.2 runner: $OLD_RUNNER"
[[ -s "$OLD_VALIDATOR" ]] || fail "missing installed v0.2.2 parallel validator: $OLD_VALIDATOR"
[[ -s "$FAST_11E" ]] || fail "missing fast 11e implementation: $FAST_11E"
[[ "$(sha_of "$OLD_RUNNER")" == "$OLD_RUNNER_SHA" ]] || fail "unexpected v0.2.2 runner SHA"
[[ "$(sha_of "$OLD_VALIDATOR")" == "$OLD_VALIDATOR_SHA" ]] || fail "unexpected v0.2.2 validator SHA"
[[ "$(sha_of "$FAST_11E")" == "$FAST_11E_SHA" ]] || fail "unexpected fast 11e SHA"

[[ -d "$OLD_RESULT" ]] || fail "v0.2.2 result root missing: $OLD_RESULT"
[[ -d "$OLD_QC" ]] || fail "v0.2.2 QC root missing: $OLD_QC"
[[ -s "$OLD_QC/stage15a_performance_100k.failure.txt" ]] || fail "v0.2.2 failure record missing"
grep -Fq "$EXPECTED_FAILURE" "$OLD_QC/stage15a_performance_100k.failure.txt" || \
    fail "v0.2.2 did not stop for the expected package-validator failure"
[[ -s "$OLD_QC/logs/validators/package_prepublication.log" ]] || fail "v0.2.2 package validator log missing"
grep -Fq "the following arguments are required: --input" \
    "$OLD_QC/logs/validators/package_prepublication.log" || \
    fail "expected flank-validator CLI failure was not found"

[[ ! -e "$NEW_RESULT" ]] || fail "new result root already exists; preserve and review: $NEW_RESULT"
[[ ! -e "$NEW_QC" ]] || fail "new QC root already exists; preserve and review: $NEW_QC"
for output in "$SUCCESS_BUNDLE" "$SUCCESS_BUNDLE.sha256" "$FAILURE_BUNDLE" "$FAILURE_BUNDLE.sha256"; do
    [[ ! -e "$output" ]] || fail "refusing to overwrite: $output"
done

mkdir -p "$PROJECT_ROOT/scripts" "$PROJECT_ROOT/docs/stage15a" "$META_ROOT"
cp -f "${BASH_SOURCE[0]}" "$SELF_DST"
chmod 755 "$SELF_DST"

cat > "$NEW_VALIDATOR" <<'PY_VALIDATOR'
from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

STAGE_VERSION = "rnatr_stage15a_validate_package_parallel_v0.2.2.1"
EXPECTED = {
    "rnatr_v041_validate_package.py": "e978b109d094f665ec62387ffda35c81d0aa9e8156972069f18a1b0b6c49bba5",
    "rnatr_v042_validate_flank_uniqueness.py": "039024835de2bc1f096e562eed69788ecad9e481575b1b8cd58241edf2e87ab5",
    "rnatr_v042_validate_package.py": "45c3995550f57a65b3fec4aab7471d57b7000e19471d4c5cf7f3ae055426984e",
}


@dataclass(frozen=True)
class Component:
    name: str
    marker: str
    arguments: tuple[str, ...]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run_component(path: Path, component: Component) -> dict[str, object]:
    started = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, str(path), *component.arguments],
        text=True,
        capture_output=True,
    )
    return {
        "name": component.name,
        "marker": component.marker,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "elapsed_seconds": time.perf_counter() - started,
        "command": [sys.executable, str(path), *component.arguments],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-dir", required=True, type=Path)
    parser.add_argument("--schema-dir", required=True, type=Path)
    args = parser.parse_args()

    package_dir = args.package_dir.resolve()
    schema_dir = args.schema_dir.resolve()
    read_evidence = package_dir / "read_evidence.tsv.gz"

    if not package_dir.is_dir():
        print(f"ERROR: package directory missing: {package_dir}", file=sys.stderr)
        return 2
    if not read_evidence.is_file() or read_evidence.stat().st_size == 0:
        print(f"ERROR: read evidence input missing: {read_evidence}", file=sys.stderr)
        return 2

    paths = {name: schema_dir / name for name in EXPECTED}
    for name, path in paths.items():
        if not path.is_file() or path.stat().st_size == 0:
            print(f"ERROR: validator component missing: {path}", file=sys.stderr)
            return 2
        observed = sha256(path)
        if observed != EXPECTED[name]:
            print(f"ERROR: validator SHA mismatch: {path}: {observed}", file=sys.stderr)
            return 2

    # The two frozen components have different CLI contracts.
    # v0.2.2 incorrectly passed --package-dir to both.
    components = [
        Component(
            name="rnatr_v041_validate_package.py",
            marker="RNATR_V041_PACKAGE_VALIDATION_PASS",
            arguments=("--package-dir", str(package_dir)),
        ),
        Component(
            name="rnatr_v042_validate_flank_uniqueness.py",
            marker="RNATR_V042_FLANK_UNIQUENESS_VALIDATION_PASS",
            arguments=("--input", str(read_evidence)),
        ),
    ]

    started = time.perf_counter()
    results: dict[str, dict[str, object]] = {}
    with cf.ThreadPoolExecutor(max_workers=2) as pool:
        futures = {
            pool.submit(run_component, paths[item.name], item): item.name
            for item in components
        }
        for future in cf.as_completed(futures):
            result = future.result()
            results[str(result["name"])] = result

    # Preserve the frozen wrapper's logical output order.
    for item in components:
        result = results[item.name]
        if result["stdout"]:
            sys.stdout.write(str(result["stdout"]))
        if result["stderr"]:
            sys.stderr.write(str(result["stderr"]))

    failures: list[str] = []
    for item in components:
        result = results[item.name]
        if int(result["returncode"]) != 0 or item.marker not in str(result["stdout"]):
            failures.append(item.name)

    if failures:
        print(
            "RNATR_V042_PARALLEL_PACKAGE_VALIDATION_FAIL\t" + ",".join(failures),
            file=sys.stderr,
        )
        return 2

    elapsed = time.perf_counter() - started
    print(f"RNATR_V042_PARALLEL_COMPONENT_SECONDS\t{elapsed:.9f}")
    for item in components:
        result = results[item.name]
        print(
            f"RNATR_V042_PARALLEL_COMPONENT\t{item.name}"
            f"\t{float(result['elapsed_seconds']):.9f}"
        )
    print(f"RNATR_V042_PARALLEL_VALIDATOR_VERSION\t{STAGE_VERSION}")
    print("RNATR_V042_PACKAGE_VALIDATION_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
PY_VALIDATOR
chmod 755 "$NEW_VALIDATOR"
NEW_VALIDATOR_SHA="$(sha_of "$NEW_VALIDATOR")"

"$PYTHON_BIN" - "$OLD_RUNNER" "$NEW_RUNNER" "$NEW_VALIDATOR_SHA" <<'PY_PATCH'
from pathlib import Path
import hashlib
import sys

src = Path(sys.argv[1])
dst = Path(sys.argv[2])
new_validator_sha = sys.argv[3]
expected_old_sha = "2ac29866d08bb0e70d7d169d90346386eb9623c63f011cc0a68471822528f96f"
old_validator_sha = "f3095a7f2af3099e8d960ebfa6d9b5380ba5e384d64122a386d6de49731ff9e2"

actual = hashlib.sha256(src.read_bytes()).hexdigest()
if actual != expected_old_sha:
    raise SystemExit(f"old runner SHA mismatch: {actual}")

text = src.read_text(encoding="utf-8")
replacements = [
    (
        'STAGE_VERSION = "rnatr_stage15a_sharded_bam_to_final_performance_v0.2.2"',
        'STAGE_VERSION = "rnatr_stage15a_sharded_bam_to_final_performance_v0.2.2.1"',
        1,
    ),
    ('"v0.2.2_performance"', '"v0.2.2.1_performance"', 2),
    (
        'rnatr_stage15a_validate_package_parallel_v0.2.2.py',
        'rnatr_stage15a_validate_package_parallel_v0.2.2.1.py',
        2,
    ),
    (old_validator_sha, new_validator_sha, 1),
]
for old, new, expected_count in replacements:
    count = text.count(old)
    if count != expected_count:
        raise SystemExit(f"patch anchor count {count} != {expected_count}: {old}")
    text = text.replace(old, new)

compile(text, str(dst), "exec")
dst.write_text(text, encoding="utf-8")
dst.chmod(0o755)
print("PATCHED_RUNNER", dst)
print("PATCHED_RUNNER_SHA256", hashlib.sha256(dst.read_bytes()).hexdigest())
print("PARALLEL_VALIDATOR_SHA256", new_validator_sha)
PY_PATCH

"$PYTHON_BIN" -m py_compile "$NEW_RUNNER" "$NEW_VALIDATOR"

cat > "$DOC" <<EOF_DOC
# Stage 15A performance validator CLI fix v0.2.2.1

Date: 2026-08-08

## Failure classification

Stage 15A performance v0.2.2 completed partitioning, 11b, 11d3, the shared-catalog
motif-job builder, caller/materializer pipelining, global merge, gzip, and all five
generic table validators. It stopped before publication because the new parallel package
validator passed \`--package-dir\` to both frozen components.

The frozen components do not share a CLI:

- \`rnatr_v041_validate_package.py\`: \`--package-dir PACKAGE\`
- \`rnatr_v042_validate_flank_uniqueness.py\`: \`--input PACKAGE/read_evidence.tsv.gz\`

The v0.2.2 failure was therefore an execution-wrapper CLI wiring defect, not evidence
or package semantic failure.

## v0.2.2.1 change

v0.2.2.1 gives each SHA-pinned frozen component its correct argument contract while
retaining parallel execution. It reruns the full isolated 100k performance lane in a new
root to obtain a clean end-to-end timing measurement. The failed v0.2.2 roots remain
preserved.

The original frozen v0.4.2 package wrapper is still run after publication, and the
missing-artifact negative parity fixture remains mandatory.

## Unchanged constraints

- active pipeline: unchanged
- SSOT: unchanged
- scientific caller: unchanged
- materialization/schema semantics: unchanged
- full 5.31M: not run
EOF_DOC

{
    printf 'role\tpath\tbytes\tsha256\n'
    for item in \
        "FIX_SCRIPT|$SELF_DST" \
        "SOURCE_RUNNER_V022|$OLD_RUNNER" \
        "SOURCE_PARALLEL_VALIDATOR_V022|$OLD_VALIDATOR" \
        "FAST_SHARED_CATALOG_11E|$FAST_11E" \
        "RUNNER_V0221|$NEW_RUNNER" \
        "PARALLEL_VALIDATOR_V0221|$NEW_VALIDATOR" \
        "DESIGN_AMENDMENT|$DOC" \
        "V022_FAILURE_RECORD|$OLD_QC/stage15a_performance_100k.failure.txt" \
        "V022_PACKAGE_VALIDATOR_LOG|$OLD_QC/logs/validators/package_prepublication.log"
    do
        role="${item%%|*}"
        path="${item#*|}"
        [[ -s "$path" ]] || fail "manifest source missing: $path"
        printf '%s\t%s\t%s\t%s\n' "$role" "$path" "$(stat -c '%s' "$path")" "$(sha_of "$path")"
    done
} > "$META_ROOT/installation_manifest.tsv"
sha256sum "$META_ROOT/installation_manifest.tsv" > "$META_ROOT/installation_manifest.tsv.sha256"

cat > "$META_ROOT/pending_ssot_registration.tsv" <<'EOF_PENDING'
metric	value
current_ssot_registration	STAGE15A_REFERENCE_V0.1.3_ONLY
performance_results_pending_registration	V0.2.0.1;V0.2.1;V0.2.2_FAILURE;V0.2.2.1_AFTER_REVIEW
active_pipeline_switch	PROHIBITED
full_5_31m_run	PROHIBITED
EOF_PENDING

"$PYTHON_BIN" "$PROJECT_ROOT/metadata/ssot/rnatr_ssot.py" \
    --project-root "$PROJECT_ROOT" validate \
    > "$META_ROOT/ssot_validate.before.log"

rm -f "$CONSOLE"
set +e
(
    set -Eeuo pipefail
    echo "===== Stage 15A performance v0.2.2.1 ====="
    echo "v0.2.2 failure preserved:         $OLD_RESULT"
    echo "corrected validator CLI:          component-specific"
    echo "new isolated result root:         $NEW_RESULT"
    echo "active pipeline switch:           PROHIBITED"
    echo "SSOT modification:                PROHIBITED"
    echo "full 5.31M run:                   PROHIBITED"
    echo "60-min-equivalent 100k budget:    67.762206 seconds"
    "$PYTHON_BIN" "$NEW_RUNNER" --shards 12 --caller-workers-per-shard 2
    "$PYTHON_BIN" "$PROJECT_ROOT/metadata/ssot/rnatr_ssot.py" \
        --project-root "$PROJECT_ROOT" validate \
        > "$META_ROOT/ssot_validate.after.log"
) 2>&1 | tee "$CONSOLE"
RUN_STATUS="${PIPESTATUS[0]}"
set -e

if [[ -d "$NEW_QC" ]]; then
    cp -f "$CONSOLE" "$NEW_QC/rnatr_stage15a_performance_100k_v0.2.2.1.console.log"
fi

SUCCESS=false
FINAL_QC="$NEW_QC/stage15a_performance_100k.qc.tsv"
if [[ "$RUN_STATUS" -eq 0 && -s "$FINAL_QC" ]]; then
    if [[ "$(metric "$FINAL_QC" audit_status)" == "PASS" \
       && "$(metric "$FINAL_QC" correctness_status)" == "PASS" \
       && "$(metric "$FINAL_QC" performance_implementation_status)" == "PASS" \
       && "$(metric "$FINAL_QC" package_exact_logical_parity)" == "true" \
       && "$(metric "$FINAL_QC" fast_motif_jobs_v021_exact_logical_parity)" == "true" \
       && "$(metric "$FINAL_QC" frozen_package_validator_postpublication)" == "PASS" \
       && "$(metric "$FINAL_QC" parallel_validator_missing_artifact_failure_parity)" == "PASS" \
       && "$(metric "$FINAL_QC" active_pipeline_modified)" == "false" \
       && "$(metric "$FINAL_QC" ssot_modified)" == "false" ]]; then
        SUCCESS=true
    fi
fi

PACKAGE_STAGE="$(mktemp -d)"
mkdir -p "$PACKAGE_STAGE/metadata" "$PACKAGE_STAGE/docs" "$PACKAGE_STAGE/scripts" \
         "$PACKAGE_STAGE/console" "$PACKAGE_STAGE/baseline" "$PACKAGE_STAGE/v022_failure"
cp -a "$META_ROOT/." "$PACKAGE_STAGE/metadata/" 2>/dev/null || true
cp -a "$DOC" "$PACKAGE_STAGE/docs/" 2>/dev/null || true
for path in "$NEW_RUNNER" "$NEW_VALIDATOR" "$SELF_DST"; do
    [[ -s "$path" ]] && cp -a "$path" "$PACKAGE_STAGE/scripts/" 2>/dev/null || true
done
[[ -s "$CONSOLE" ]] && cp -a "$CONSOLE" "$PACKAGE_STAGE/console/" 2>/dev/null || true

for path in \
    "$PROJECT_ROOT/qc/15_stage15a_bam_to_final/$RUN_ID/v0.2.0.1_performance/stage15a_performance_100k.qc.tsv" \
    "$PROJECT_ROOT/qc/15_stage15a_bam_to_final/$RUN_ID/v0.2.1_performance/stage15a_performance_100k.qc.tsv" \
    "$PROJECT_ROOT/qc/15_stage15a_bam_to_final/$RUN_ID/v0.2.1_performance/stage15a_performance_timing.tsv"
do
    [[ -s "$path" ]] && cp -a "$path" "$PACKAGE_STAGE/baseline/" 2>/dev/null || true
done
cp -a "$OLD_QC/stage15a_performance_100k.failure.txt" "$PACKAGE_STAGE/v022_failure/" 2>/dev/null || true
cp -a "$OLD_QC/logs/validators/package_prepublication.log" "$PACKAGE_STAGE/v022_failure/" 2>/dev/null || true

if [[ -d "$NEW_QC" ]]; then
    mkdir -p "$PACKAGE_STAGE/qc"
    cp -a "$NEW_QC/." "$PACKAGE_STAGE/qc/" 2>/dev/null || true
fi
if [[ -d "$NEW_RESULT/package_performance" ]]; then
    mkdir -p "$PACKAGE_STAGE/selected/package_performance"
    for name in package_manifest.tsv materialization.qc.tsv; do
        [[ -s "$NEW_RESULT/package_performance/$name" ]] && \
            cp -a "$NEW_RESULT/package_performance/$name" "$PACKAGE_STAGE/selected/package_performance/"
    done
fi
if [[ -d "$NEW_RESULT/shards/shard_000/frozen_scripts" ]]; then
    mkdir -p "$PACKAGE_STAGE/selected/shard_000_frozen_scripts"
    cp -a "$NEW_RESULT/shards/shard_000/frozen_scripts/." \
        "$PACKAGE_STAGE/selected/shard_000_frozen_scripts/" 2>/dev/null || true
fi

if [[ "$SUCCESS" == true ]]; then
    OUTPUT_BUNDLE="$SUCCESS_BUNDLE"
else
    OUTPUT_BUNDLE="$FAILURE_BUNDLE"
fi

tar -czf "$OUTPUT_BUNDLE" -C "$PACKAGE_STAGE" .
sha256sum "$OUTPUT_BUNDLE" | tee "$OUTPUT_BUNDLE.sha256"

echo
echo "===== Stage 15A performance v0.2.2.1 finished ====="
echo "run_exit_code: $RUN_STATUS"
echo "bundle:        $OUTPUT_BUNDLE"
echo "sha_file:      $OUTPUT_BUNDLE.sha256"
if [[ -s "$FINAL_QC" ]]; then
    echo
    cat "$FINAL_QC"
fi

if [[ "$SUCCESS" != true ]]; then
    echo >&2
    echo "ERROR: v0.2.2.1 did not reach correctness/implementation PASS." >&2
    echo "Upload the failure bundle and SHA file shown above." >&2
    exit "${RUN_STATUS:-1}"
fi

echo
echo "Upload the output bundle and SHA file shown above."
exit 0
