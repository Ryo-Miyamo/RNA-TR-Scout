#!/usr/bin/env bash
set -euo pipefail

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
fi

conda activate rnatr-v03
source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

SOURCE="$PROJECT_ROOT/scripts/11az_fix_repeat_core_dependency_closure_and_validate.sh"
QC="$PROJECT_ROOT/qc/11_p3_repeat_core_validation_v3/ENCSR307SHM_pilot100k_mm2splice_v1/p3_repeat_core_positive_validation_v3.qc.tsv"

test -f "$SOURCE" || {
    echo "ERROR: missing source script: $SOURCE" >&2
    exit 1
}

timestamp="$(date +%Y%m%d_%H%M%S)"
BACKUP="$SOURCE.before_future_import_order_fix.$timestamp"
cp -a "$SOURCE" "$BACKUP"

python - "$SOURCE" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

old = """module_parts = [
    '\"\"\"Exact 11af repeat core with runtime constants frozen.\\n\\n'
    "Validation artifact only; no command-line argument "
    'side effects.\\n'
    '\"\"\"',
]

for name, value in sorted(
    synthetic_assignments.items()
):
    module_parts.append(
        f"{name} = {value!r}"
    )

module_parts.extend(
    ast.unparse(node)
    for node in ordered_original_nodes
)

module_source = "\\n\\n".join(
    module_parts
) + "\\n"
"""

new = """future_nodes = [
    node
    for node in ordered_original_nodes
    if (
        isinstance(node, ast.ImportFrom)
        and node.module == "__future__"
    )
]
non_future_nodes = [
    node
    for node in ordered_original_nodes
    if node not in future_nodes
]

module_parts = [
    '\"\"\"Exact 11af repeat core with runtime constants frozen.\\n\\n'
    "Validation artifact only; no command-line argument "
    'side effects.\\n'
    '\"\"\"',
]

module_parts.extend(
    ast.unparse(node)
    for node in future_nodes
)

for name, value in sorted(
    synthetic_assignments.items()
):
    module_parts.append(
        f"{name} = {value!r}"
    )

module_parts.extend(
    ast.unparse(node)
    for node in non_future_nodes
)

module_source = "\\n\\n".join(
    module_parts
) + "\\n"
"""

if old in text:
    path.write_text(
        text.replace(old, new, 1),
        encoding="utf-8",
    )
    print(f"PATCHED\t{path}")
elif new in text:
    print(f"ALREADY_PATCHED\t{path}")
else:
    raise SystemExit(
        "Expected module assembly block was not found; "
        "script left unchanged."
    )
PY

bash -n "$SOURCE"
echo "Patched 11az shell syntax: PASS"

python - "$SOURCE" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

match = re.search(
    r'cat > "\$PY" <<\'PY\'\n(.*?)\nPY\n',
    text,
    flags=re.S,
)

if match is None:
    raise SystemExit(
        "Embedded Python heredoc was not found."
    )

compile(
    match.group(1),
    "embedded_validate_repeat_core_v3.py",
    "exec",
)

print("Patched embedded Python syntax: PASS")
PY

echo
echo "===== RERUN CORRECTED 11az ====="
bash "$SOURCE"

test -s "$QC" || {
    echo "ERROR: expected QC was not created: $QC" >&2
    exit 1
}

status="$(
    awk -F '\t' '
      $1 == "repeat_core_positive_validation_v3_status" {
        print $2
      }
    ' "$QC"
)"

if [[ "$status" != "PASS" ]]; then
    echo "ERROR: validation status is not PASS: $status" >&2
    exit 1
fi

echo
echo "===== FINAL QC ====="
column -ts $'\t' "$QC"

echo
echo "===== PATCH BACKUP ====="
echo "$BACKUP"
