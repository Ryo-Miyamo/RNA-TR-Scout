#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="/mnt/intelssd/rnatr_project"
BUNDLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION="v0.1.0"
META_ROOT="$PROJECT_ROOT/metadata/stage15a/$VERSION/reference_execution_bundle"
SCRIPT_ROOT="$PROJECT_ROOT/scripts"
DOC_ROOT="$PROJECT_ROOT/docs/stage15a"
CONTRACT_ROOT="$META_ROOT/contract"
BACKUP_ROOT="$META_ROOT/backups/$(date -u +%Y%m%dT%H%M%SZ)"
INSTALL_MANIFEST="$META_ROOT/installation_manifest.tsv"
CONSOLE_LOG="$HOME/Downloads/rnatr_stage15a_reference_100k_v0.1.0.console.log"

[[ -d "$PROJECT_ROOT" ]] || {
    echo "ERROR: project root not found: $PROJECT_ROOT" >&2
    exit 1
}

cd "$BUNDLE_DIR"
sha256sum -c SHA256SUMS

mkdir -p "$SCRIPT_ROOT" "$DOC_ROOT" "$CONTRACT_ROOT" "$META_ROOT"

echo -e 'role\tsource\tdestination\tbytes\tsha256\tstatus' > "$INSTALL_MANIFEST"

install_one() {
    local role="$1"
    local src="$2"
    local dest="$3"
    local mode="$4"
    local src_sha dest_sha status rel backup

    [[ -s "$src" ]] || {
        echo "ERROR: install source missing: $src" >&2
        exit 1
    }

    src_sha="$(sha256sum "$src" | awk '{print $1}')"
    status="INSTALLED"
    mkdir -p "$(dirname "$dest")"

    if [[ -e "$dest" ]]; then
        dest_sha="$(sha256sum "$dest" | awk '{print $1}')"
        if [[ "$dest_sha" == "$src_sha" ]]; then
            status="ALREADY_IDENTICAL"
        else
            rel="${dest#/}"
            backup="$BACKUP_ROOT/$rel"
            mkdir -p "$(dirname "$backup")"
            cp -a "$dest" "$backup"
            cp -f "$src" "$dest"
            status="BACKED_UP_AND_REPLACED"
        fi
    else
        cp "$src" "$dest"
    fi

    chmod "$mode" "$dest"
    printf '%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$role" "$src" "$dest" "$(stat -c '%s' "$dest")" "$src_sha" "$status" \
        >> "$INSTALL_MANIFEST"
}

for src in "$BUNDLE_DIR"/scripts/*; do
    install_one SCRIPT "$src" "$SCRIPT_ROOT/$(basename "$src")" 755
done

for src in "$BUNDLE_DIR"/docs/*; do
    install_one DOCUMENT "$src" "$DOC_ROOT/$(basename "$src")" 644
done

for src in "$BUNDLE_DIR"/contract/*; do
    install_one CONTRACT "$src" "$CONTRACT_ROOT/$(basename "$src")" 644
done

install_one README "$BUNDLE_DIR/README_EXECUTE.md" "$META_ROOT/README_EXECUTE.md" 644
install_one BUNDLE_SHA256SUMS "$BUNDLE_DIR/SHA256SUMS" "$META_ROOT/SHA256SUMS" 644
install_one INSTALLER "$BUNDLE_DIR/install_and_run_reference_100k_v0.1.0.sh" "$SCRIPT_ROOT/rnatr_stage15a_install_and_run_reference_100k_v0.1.0.sh" 755

sha256sum "$INSTALL_MANIFEST" > "$INSTALL_MANIFEST.sha256"

echo
printf 'Installed scripts: %s\n' "$SCRIPT_ROOT"
printf 'Installed docs:    %s\n' "$DOC_ROOT"
printf 'Contract root:     %s\n' "$CONTRACT_ROOT"
printf 'Install manifest:  %s\n' "$INSTALL_MANIFEST"
echo

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
    # shellcheck disable=SC1090
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
    conda activate rnatr-v03
fi

set -o pipefail
python "$SCRIPT_ROOT/rnatr_stage15a_run_reference_100k_v0.1.0.py" --workers 16 \
    2>&1 | tee "$CONSOLE_LOG"

OUT_BUNDLE="$HOME/Downloads/rnatr_stage15a_reference_100k_output_v0.1.0.tar.gz"
OUT_SHA="${OUT_BUNDLE}.sha256"
[[ -s "$OUT_BUNDLE" ]] || {
    echo "ERROR: expected output bundle was not created: $OUT_BUNDLE" >&2
    exit 1
}

TMP_REPACK="$(mktemp -d)"
trap 'rm -rf "$TMP_REPACK"' EXIT
tar -xzf "$OUT_BUNDLE" -C "$TMP_REPACK"
mkdir -p "$TMP_REPACK/qc"
cp "$CONSOLE_LOG" "$TMP_REPACK/qc/rnatr_stage15a_reference_100k_v0.1.0.console.log"
tar -czf "${OUT_BUNDLE}.part" -C "$TMP_REPACK" .
mv "${OUT_BUNDLE}.part" "$OUT_BUNDLE"
sha256sum "$OUT_BUNDLE" | tee "$OUT_SHA"

echo
printf 'Console log:  %s\n' "$CONSOLE_LOG"
printf 'Output bundle: %s\n' "$OUT_BUNDLE"
printf 'SHA file:      %s\n' "$OUT_SHA"
