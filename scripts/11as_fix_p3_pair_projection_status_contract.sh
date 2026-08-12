#!/usr/bin/env bash
set -euo pipefail

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
fi

conda activate rnatr-v03
source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"
PACKAGE_VERSION="0.3.2"
CONTRACT_REVISION="1"

PACKAGE_DIR="$PROJECT_ROOT/src/rnatr_scout"
UNIT_DIR="$PROJECT_ROOT/tests/unit"

PAIR_META="$PROJECT_ROOT/results/11_p3_bridge_feasibility/$RUN_ID/p3_bridge_pair_metadata.tsv.gz"
QUERY_FASTA="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_p3_bridge_feasibility/p3_bridge_queries.fasta.gz"
REFERENCE_FASTA="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_p3_bridge_feasibility/p3_bridge_candidate_references.fasta.gz"
SIZING="$PROJECT_ROOT/results/11_p3_target_entry_sizing/$RUN_ID/p3_target_entry_repeat_evidence.tsv"

OUTDIR="$PROJECT_ROOT/results/11_production_p3_pair_projection_fix/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_production_p3_pair_projection_fix/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_production_p3_pair_projection_fix/$RUN_ID"

REPLAY="$OUTDIR/p3_pair_alignment_projection_replay.corrected.tsv"
QC="$QCDIR/p3_pair_alignment_projection_contract_fix.qc.tsv"
UNIT_LOG="$OUTDIR/unit_tests.log"
MANIFEST="$OUTDIR/${RUN_ID}.p3_pair_projection_contract_fix.manifest.tsv"

STAGE="$WORKDIR/stage"
STAGE_PACKAGE="$STAGE/rnatr_scout"
STAGE_TESTS="$STAGE/tests"

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR"

for path in \
  "$PACKAGE_DIR/p3_pair.py" \
  "$UNIT_DIR/test_p3_pair.py" \
  "$PAIR_META" \
  "$QUERY_FASTA" \
  "$REFERENCE_FASTA" \
  "$SIZING"
do
    test -e "$path" || {
        echo "ERROR: missing required path: $path" >&2
        exit 1
    }
done

installed_version="$(rnatr-scout version)"

if [[ "$installed_version" != "$PACKAGE_VERSION" ]]; then
    echo "ERROR: unexpected installed version: $installed_version" >&2
    exit 1
fi

rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -a "$PACKAGE_DIR" "$STAGE_PACKAGE"
cp -a "$UNIT_DIR" "$STAGE_TESTS"

python - \
  "$STAGE_PACKAGE/p3_pair.py" \
  "$STAGE_TESTS/test_p3_pair.py" <<'PYPATCH'
from pathlib import Path
import sys

module_path = Path(sys.argv[1])
test_path = Path(sys.argv[2])

module_text = module_path.read_text(
    encoding="utf-8"
)
test_text = test_path.read_text(
    encoding="utf-8"
)

old_module = "\n".join(
    [
        "    if not selected_decision.bridge_valid:",
        "        return PairAlignmentProjection(",
        "            alignment_count=len(pair_alignments),",
        "            selected_alignment=selected_alignment,",
        "            bridge_decision=selected_decision,",
        "            target_entry_query_offset=None,",
        "            target_entry_projection_status=(",
        '                "TARGET_ENTRY_NOT_PROJECTED"',
        "            ),",
        "            target_entry_projection_detail=(",
        '                "BRIDGE_INVALID:"',
        "                + selected_decision.bridge_status",
        "            ),",
        "        )",
        "",
    ]
)

new_module = "\n".join(
    [
        "    if not selected_decision.bridge_valid:",
        "        if (",
        "            selected_decision.bridge_status",
        '            == "ORIENTATION_INCONSISTENT_BRIDGE"',
        "        ):",
        "            projection_status = (",
        '                "UNEXPECTED_REVERSE_ALIGNMENT"',
        "            )",
        "        else:",
        "            projection_status = (",
        '                "TARGET_ENTRY_NOT_PROJECTED"',
        "            )",
        "",
        "        return PairAlignmentProjection(",
        "            alignment_count=len(pair_alignments),",
        "            selected_alignment=selected_alignment,",
        "            bridge_decision=selected_decision,",
        "            target_entry_query_offset=None,",
        "            target_entry_projection_status=(",
        "                projection_status",
        "            ),",
        "            target_entry_projection_detail=(",
        '                "BRIDGE_INVALID:"',
        "                + selected_decision.bridge_status",
        "            ),",
        "        )",
        "",
    ]
)

if old_module not in module_text:
    if new_module in module_text:
        print(
            "MODULE_ALREADY_PATCHED\t"
            + str(module_path)
        )
    else:
        raise SystemExit(
            "Expected p3_pair.py block was not found"
        )
else:
    module_path.write_text(
        module_text.replace(
            old_module,
            new_module,
            1,
        ),
        encoding="utf-8",
    )
    print(
        "MODULE_PATCHED\t"
        + str(module_path)
    )

old_test = "\n".join(
    [
        "        self.assertEqual(",
        "            result.target_entry_projection_status,",
        '            "TARGET_ENTRY_NOT_PROJECTED",',
        "        )",
        "",
    ]
)

new_test = "\n".join(
    [
        "        self.assertEqual(",
        "            result.target_entry_projection_status,",
        '            "UNEXPECTED_REVERSE_ALIGNMENT",',
        "        )",
        "",
    ]
)

if old_test not in test_text:
    if new_test in test_text:
        print(
            "TEST_ALREADY_PATCHED\t"
            + str(test_path)
        )
    else:
        raise SystemExit(
            "Expected reverse-only test assertion was not found"
        )
else:
    test_path.write_text(
        test_text.replace(
            old_test,
            new_test,
            1,
        ),
        encoding="utf-8",
    )
    print(
        "TEST_PATCHED\t"
        + str(test_path)
    )
PYPATCH

echo "===== STAGED PYTHON SYNTAX ====="
python -m compileall -q \
  "$STAGE_PACKAGE" \
  "$STAGE_TESTS"
echo "Python compileall: PASS"

echo
echo "===== STAGED UNIT TESTS ====="
RNATR_PROJECT_ROOT="$PROJECT_ROOT" \
PYTHONPATH="$STAGE" \
python -m unittest discover \
  -s "$STAGE_TESTS" \
  -v \
  2>&1 | tee "$UNIT_LOG"

timestamp="$(date +%Y%m%d_%H%M%S)"
BACKUP="$PROJECT_ROOT/metadata/code_backups/11as_${timestamp}"
mkdir -p "$BACKUP"

cp "$PACKAGE_DIR/p3_pair.py" \
  "$BACKUP/p3_pair.py"
cp "$UNIT_DIR/test_p3_pair.py" \
  "$BACKUP/test_p3_pair.py"

cp "$STAGE_PACKAGE/p3_pair.py" \
  "$PACKAGE_DIR/p3_pair.py"
cp "$STAGE_TESTS/test_p3_pair.py" \
  "$UNIT_DIR/test_p3_pair.py"

echo
echo "===== INSTALLED PACKAGE UNIT TESTS ====="
RNATR_PROJECT_ROOT="$PROJECT_ROOT" \
python -m unittest discover \
  -s "$UNIT_DIR" \
  -v

echo
echo "===== REPLAY 23 PAIRS AFTER STATUS-CONTRACT FIX ====="

python - \
  "$PAIR_META" \
  "$QUERY_FASTA" \
  "$REFERENCE_FASTA" \
  "$SIZING" \
  "$REPLAY" \
  "$QC" \
  "$CONTRACT_REVISION" <<'PYREPLAY'
from __future__ import annotations

import csv
import gzip
import sys
from collections import Counter
from pathlib import Path

from rnatr_scout.fasta import load_fasta
from rnatr_scout.p3_pair import (
    run_isolated_pair_alignment,
)

pair_meta_path = Path(sys.argv[1])
query_fasta_path = Path(sys.argv[2])
reference_fasta_path = Path(sys.argv[3])
sizing_path = Path(sys.argv[4])
replay_path = Path(sys.argv[5])
qc_path = Path(sys.argv[6])
contract_revision = sys.argv[7]

with gzip.open(
    pair_meta_path,
    "rt",
    encoding="utf-8",
    newline="",
) as handle:
    pair_meta = {
        row["projection_id"]: row
        for row in csv.DictReader(
            handle,
            delimiter="\t",
        )
    }

query_sequences = load_fasta(
    query_fasta_path
)
reference_sequences = load_fasta(
    reference_fasta_path
)

with sizing_path.open(
    "r",
    encoding="utf-8",
    newline="",
) as handle:
    sizing_rows = list(
        csv.DictReader(
            handle,
            delimiter="\t",
        )
    )

results = []
missing_inputs = 0
bridge_status_counts = Counter()
projection_status_counts = Counter()
query_offset_mismatches = 0
projection_status_mismatches = 0

for sizing in sizing_rows:
    projection_id = sizing["projection_id"]
    metadata = pair_meta.get(projection_id)

    if metadata is None:
        missing_inputs += 1
        continue

    reference_id = metadata["reference_id"]
    query_sequence = query_sequences.get(
        projection_id
    )
    reference_sequence = reference_sequences.get(
        reference_id
    )

    if (
        query_sequence is None
        or reference_sequence is None
    ):
        missing_inputs += 1
        continue

    result = run_isolated_pair_alignment(
        query_name=projection_id,
        query_sequence=query_sequence,
        target_name=reference_id,
        target_sequence=reference_sequence,
        bridge_bp=int(metadata["bridge_bp"]),
        target_entry_bp=int(
            metadata["target_entry_bp"]
        ),
        query_can_reach_target_entry=(
            metadata[
                "query_can_reach_target_entry"
            ] == "true"
        ),
    )

    bridge_status = (
        result.bridge_decision.bridge_status
    )
    projection_status = (
        result.target_entry_projection_status
    )

    bridge_status_counts[bridge_status] += 1
    projection_status_counts[
        projection_status
    ] += 1

    expected_offset = sizing[
        "target_entry_query_offset"
    ]
    produced_offset = (
        "."
        if result.target_entry_query_offset
           is None
        else str(
            result.target_entry_query_offset
        )
    )

    if expected_offset != produced_offset:
        query_offset_mismatches += 1

    expected_status = sizing[
        "target_entry_projection_status"
    ]

    if projection_status != expected_status:
        projection_status_mismatches += 1

    selected = result.selected_alignment

    results.append(
        {
            "projection_id": projection_id,
            "read_id": sizing["read_id"],
            "target_region_id": sizing[
                "target_region_id"
            ],
            "reference_id": reference_id,
            "selected_strand": (
                selected.strand
                if selected is not None
                else "."
            ),
            "production_bridge_status": (
                bridge_status
            ),
            "production_bridge_valid": str(
                result.bridge_decision.bridge_valid
            ).lower(),
            "production_target_entry_query_offset": (
                produced_offset
            ),
            "production_projection_status": (
                projection_status
            ),
            "production_projection_detail": (
                result.target_entry_projection_detail
            ),
            "expected_target_entry_query_offset": (
                expected_offset
            ),
            "expected_projection_status": (
                expected_status
            ),
            "projection_status_matches": str(
                projection_status
                == expected_status
            ).lower(),
        }
    )

with replay_path.open(
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=list(results[0].keys()),
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(results)

valid_bridges = sum(
    row["production_bridge_valid"] == "true"
    for row in results
)

status = "PASS"

if (
    len(sizing_rows) != 23
    or len(results) != 23
    or missing_inputs
    or valid_bridges != 1
    or bridge_status_counts[
        "ORIENTATION_INCONSISTENT_BRIDGE"
    ] != 22
    or bridge_status_counts[
        "BRIDGE_REACHES_TARGET_ENTRY"
    ] != 1
    or projection_status_counts[
        "UNEXPECTED_REVERSE_ALIGNMENT"
    ] != 22
    or projection_status_counts[
        "TARGET_ENTRY_PROJECTED"
    ] != 1
    or query_offset_mismatches
    or projection_status_mismatches
):
    status = "REVIEW"

with qc_path.open(
    "w",
    encoding="utf-8",
) as handle:
    handle.write("metric\tvalue\n")
    handle.write("package_version\t0.3.2\n")
    handle.write(
        "pair_projection_contract_revision\t{}\n".format(
            contract_revision
        )
    )
    handle.write(
        "input_pairs\t{}\n".format(
            len(sizing_rows)
        )
    )
    handle.write(
        "pairs_replayed\t{}\n".format(
            len(results)
        )
    )
    handle.write(
        "missing_inputs\t{}\n".format(
            missing_inputs
        )
    )
    handle.write(
        "production_valid_bridges\t{}\n".format(
            valid_bridges
        )
    )
    handle.write(
        "target_entry_query_offset_mismatches\t{}\n".format(
            query_offset_mismatches
        )
    )
    handle.write(
        "projection_status_mismatches\t{}\n".format(
            projection_status_mismatches
        )
    )

    for key, value in sorted(
        bridge_status_counts.items()
    ):
        handle.write(
            "bridge_status::{}\t{}\n".format(
                key,
                value,
            )
        )

    for key, value in sorted(
        projection_status_counts.items()
    ):
        handle.write(
            "projection_status::{}\t{}\n".format(
                key,
                value,
            )
        )

    handle.write(
        "pair_projection_contract_fix_status\t{}\n".format(
            status
        )
    )

if status != "PASS":
    raise SystemExit(
        "Pair-projection status-contract fix requires review"
    )
PYREPLAY

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in \
      "$PACKAGE_DIR/p3_pair.py" \
      "$UNIT_DIR/test_p3_pair.py" \
      "$REPLAY" \
      "$QC" \
      "$UNIT_LOG"
    do
        if [[ "$path" == *.tsv ]]; then
            rows="$(awk 'END {print NR-1}' "$path")"
        else
            rows="."
        fi

        printf '%s\t%s\t%s\t%s\t%s\n' \
          "$(basename "$path")" \
          "$rows" \
          "$(stat -c '%s' "$path")" \
          "$(sha256sum "$path" | awk '{print $1}')" \
          "$path"
    done
} > "$MANIFEST"

echo
echo "===== QC ====="
column -ts $'\t' "$QC"

echo
echo "===== REPLAY STATUS COUNTS ====="
awk -F '\t' '
  NR == 1 {
    next
  }
  {
    bridge[$6]++
    projection[$9]++
  }
  END {
    for (key in bridge) {
      print "bridge_status::" key "\t" bridge[key]
    }
    for (key in projection) {
      print "projection_status::" key "\t" projection[key]
    }
  }
' "$REPLAY" \
  | sort \
  | column -ts $'\t'

echo
echo "===== MANIFEST ====="
column -ts $'\t' "$MANIFEST"

echo
echo "===== BACKUP ====="
echo "$BACKUP"
