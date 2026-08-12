#!/usr/bin/env bash
set -euo pipefail

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
fi

conda activate rnatr-v03
source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"
MODEL_ID="rnatr_p3_isolated_pair_validation_v0.3.1"

PAIR_META="$PROJECT_ROOT/results/11_p3_bridge_feasibility/$RUN_ID/p3_bridge_pair_metadata.tsv.gz"
BATCH_AUDIT="$PROJECT_ROOT/results/11_p3_bridge_feasibility/$RUN_ID/p3_bridge_feasibility_audit.tsv.gz"
QUERY_FASTA="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_p3_bridge_feasibility/p3_bridge_queries.fasta.gz"
REFERENCE_FASTA="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_p3_bridge_feasibility/p3_bridge_candidate_references.fasta.gz"

OUTDIR="$PROJECT_ROOT/results/11_p3_isolated_pair_validation/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_p3_isolated_pair_validation/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_p3_isolated_pair_validation/$RUN_ID"

OUTPUT="$OUTDIR/p3_isolated_pair_validation.tsv.gz"
SUMMARY="$OUTDIR/p3_isolated_pair_validation_summary.tsv"
DUPLICATES="$OUTDIR/p3_candidate_reference_duplicate_groups.tsv"
QC="$QCDIR/p3_isolated_pair_validation.qc.tsv"
PARAMETERS="$OUTDIR/${MODEL_ID}.parameters.tsv"
MANIFEST="$OUTDIR/${RUN_ID}.p3_isolated_pair_validation.manifest.tsv"
PY="$WORKDIR/run_isolated_pair_validation.py"

EXPECTED_PAIRS=1007
EXPECTED_BATCH_BRIDGE_PLUS_MOTIF=6

WORKERS=8
PROGRESS_EVERY=100
MIN_TARGET_ENTRY_SUPPORT_BP=12
BOUNDARY_TOLERANCE_BP=10
MIN_ALIGNMENT_IDENTITY=0.70
MIN_ALIGNMENT_QUERY_COVERAGE=0.70

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR"

for path in \
  "$PAIR_META" \
  "$BATCH_AUDIT" \
  "$QUERY_FASTA" \
  "$REFERENCE_FASTA"
do
    test -s "$path" || {
        echo "ERROR: missing input: $path" >&2
        exit 1
    }
done

command -v minimap2 >/dev/null 2>&1 || {
    echo "ERROR: minimap2 is not available" >&2
    exit 1
}

cat > "$PARAMETERS" <<EOF
parameter	value	meaning
model_id	$MODEL_ID	One-query/one-reference validation of P3 bridge candidates
expected_pairs	$EXPECTED_PAIRS	Selected P3 calibration pairs
workers	$WORKERS	Concurrent isolated minimap2 jobs
minimap2_parameters	-x map-ont -k7 -w3 -m10 -s10 -p0.50 -N10 -f0 -c --secondary=yes -t1	Each job contains exactly one query and one candidate reference
minimum_target_entry_support_bp	$MIN_TARGET_ENTRY_SUPPORT_BP	Reference bases required inside target
boundary_tolerance_bp	$BOUNDARY_TOLERANCE_BP	Maximum query/reference start offset from block boundary
minimum_alignment_identity	$MIN_ALIGNMENT_IDENTITY	Provisional ONT bridge compatibility threshold
minimum_alignment_query_coverage	$MIN_ALIGNMENT_QUERY_COVERAGE	Minimum isolated-pair query coverage
comparison_goal	batch_cross_reference_bias_audit	Detect self-pair loss caused by similar candidate references
call_semantics	validation_only	No repeat evidence, allele-length, or expansion call
EOF

cat > "$PY" <<'PY'
from __future__ import annotations

import csv
import gzip
import hashlib
import os
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import pysam

(
    metadata_path,
    batch_audit_path,
    query_fasta_path,
    reference_fasta_path,
    output_path,
    summary_path,
    duplicates_path,
    qc_path,
    workdir,
    model_id,
    expected_pairs_text,
    expected_batch_bridge_text,
    workers_text,
    progress_every_text,
    minimum_target_entry_text,
    boundary_tolerance_text,
    minimum_identity_text,
    minimum_query_coverage_text,
) = sys.argv[1:]

EXPECTED_PAIRS = int(expected_pairs_text)
EXPECTED_BATCH_BRIDGE = int(
    expected_batch_bridge_text
)
WORKERS = int(workers_text)
PROGRESS_EVERY = int(progress_every_text)
MINIMUM_TARGET_ENTRY = int(
    minimum_target_entry_text
)
BOUNDARY_TOLERANCE = int(
    boundary_tolerance_text
)
MINIMUM_IDENTITY = float(minimum_identity_text)
MINIMUM_QUERY_COVERAGE = float(
    minimum_query_coverage_text
)


def parse_tags(fields):
    tags = {}

    for field in fields:
        parts = field.split(":", 2)

        if len(parts) != 3:
            continue

        name, value_type, value = parts

        if value_type == "i":
            tags[name] = int(value)
        elif value_type == "f":
            tags[name] = float(value)
        else:
            tags[name] = value

    return tags


def parse_paf(text):
    rows = []

    for line in text.splitlines():
        if not line:
            continue

        fields = line.split("\t")

        if len(fields) < 12:
            continue

        tags = parse_tags(fields[12:])
        query_length = int(fields[1])
        query_start = int(fields[2])
        query_end = int(fields[3])
        reference_start = int(fields[7])
        reference_end = int(fields[8])
        matches = int(fields[9])
        block_length = int(fields[10])

        rows.append(
            {
                "query_length": query_length,
                "query_start": query_start,
                "query_end": query_end,
                "strand": fields[4],
                "reference_length": int(fields[6]),
                "reference_start": reference_start,
                "reference_end": reference_end,
                "matches": matches,
                "block_length": block_length,
                "identity": (
                    matches / block_length
                    if block_length
                    else 0.0
                ),
                "query_coverage": (
                    (query_end - query_start)
                    / query_length
                    if query_length
                    else 0.0
                ),
                "mapq": int(fields[11]),
                "alignment_score": tags.get(
                    "AS",
                    matches,
                ),
                "alignment_type": tags.get(
                    "tp",
                    ".",
                ),
                "cigar": tags.get(
                    "cg",
                    ".",
                ),
            }
        )

    rows.sort(
        key=lambda row: (
            row["alignment_score"],
            row["matches"],
            row["query_coverage"],
            row["identity"],
        ),
        reverse=True,
    )

    return rows


with gzip.open(
    metadata_path,
    "rt",
    encoding="utf-8",
    newline="",
) as handle:
    metadata = {
        row["projection_id"]: row
        for row in csv.DictReader(
            handle,
            delimiter="\t",
        )
    }

with gzip.open(
    batch_audit_path,
    "rt",
    encoding="utf-8",
    newline="",
) as handle:
    batch_audit = {
        row["projection_id"]: row
        for row in csv.DictReader(
            handle,
            delimiter="\t",
        )
    }

query_sequences = {}

with pysam.FastxFile(query_fasta_path) as source:
    for entry in source:
        query_sequences[entry.name] = (
            entry.sequence.upper()
        )

reference_sequences = {}

with pysam.FastxFile(reference_fasta_path) as source:
    for entry in source:
        reference_sequences[entry.name] = (
            entry.sequence.upper()
        )

missing_queries = (
    set(metadata) - set(query_sequences)
)

missing_references = {
    projection_id
    for projection_id, row in metadata.items()
    if row["reference_id"]
       not in reference_sequences
}

reference_hash_groups = defaultdict(list)

for projection_id, row in metadata.items():
    sequence = reference_sequences.get(
        row["reference_id"],
        "",
    )
    digest = hashlib.sha256(
        sequence.encode()
    ).hexdigest()
    reference_hash_groups[digest].append(
        projection_id
    )

reference_multiplicity = {}

for digest, projection_ids in (
    reference_hash_groups.items()
):
    for projection_id in projection_ids:
        reference_multiplicity[
            projection_id
        ] = len(projection_ids)

progress_lock = threading.Lock()
progress_state = {
    "completed": 0,
    "start_time": time.time(),
}


def run_pair(projection_id):
    meta = metadata[projection_id]
    query_sequence = query_sequences[
        projection_id
    ]
    reference_id = meta["reference_id"]
    reference_sequence = reference_sequences[
        reference_id
    ]

    safe_id = "".join(
        character
        if character.isalnum()
        else "_"
        for character in projection_id
    )

    pair_directory = os.path.join(
        workdir,
        "pair_" + safe_id,
    )
    os.makedirs(
        pair_directory,
        exist_ok=True,
    )

    query_path = os.path.join(
        pair_directory,
        "query.fa",
    )
    reference_path = os.path.join(
        pair_directory,
        "reference.fa",
    )

    with open(
        query_path,
        "w",
        encoding="utf-8",
    ) as handle:
        handle.write(
            ">{}\n{}\n".format(
                projection_id,
                query_sequence,
            )
        )

    with open(
        reference_path,
        "w",
        encoding="utf-8",
    ) as handle:
        handle.write(
            ">{}\n{}\n".format(
                reference_id,
                reference_sequence,
            )
        )

    command = [
        "minimap2",
        "-x",
        "map-ont",
        "-k7",
        "-w3",
        "-m10",
        "-s10",
        "-p0.50",
        "-N10",
        "-f0",
        "-c",
        "--secondary=yes",
        "-t1",
        reference_path,
        query_path,
    ]

    completed = subprocess.run(
        command,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )

    if completed.returncode != 0:
        raise RuntimeError(
            "minimap2 failed for {} with code {}".format(
                projection_id,
                completed.returncode,
            )
        )

    alignments = parse_paf(
        completed.stdout
    )

    try:
        os.remove(query_path)
        os.remove(reference_path)
        os.rmdir(pair_directory)
    except OSError:
        pass

    bridge_bp = int(meta["bridge_bp"])
    target_entry_bp = int(
        meta["target_entry_bp"]
    )
    required_reference_end = (
        bridge_bp
        + min(
            target_entry_bp,
            MINIMUM_TARGET_ENTRY,
        )
    )
    can_reach = (
        meta["query_can_reach_target_entry"]
        == "true"
    )
    motif_signal = (
        int(
            meta[
                "oriented_target_relevant_window_count"
            ]
        ) > 0
    )

    if not can_reach:
        status = (
            "QUERY_TOO_SHORT_TO_REACH_TARGET"
        )
        best = None

    elif not alignments:
        status = (
            "NO_ISOLATED_PAIR_ALIGNMENT"
        )
        best = None

    else:
        best = alignments[0]
        boundary_connected = (
            best["query_start"]
            <= BOUNDARY_TOLERANCE
            and best["reference_start"]
                <= BOUNDARY_TOLERANCE
        )
        quality_pass = (
            best["identity"]
            >= MINIMUM_IDENTITY
            and best["query_coverage"]
                >= MINIMUM_QUERY_COVERAGE
        )
        reaches_target = (
            best["reference_end"]
            >= required_reference_end
        )

        if not boundary_connected:
            status = (
                "ALIGNMENT_NOT_CONNECTED_TO_BLOCK_BOUNDARY"
            )
        elif not quality_pass:
            status = (
                "LOW_QUALITY_BRIDGE_ALIGNMENT"
            )
        elif not reaches_target:
            status = (
                "BRIDGE_STOPS_BEFORE_TARGET_ENTRY"
            )
        else:
            status = (
                "BRIDGE_REACHES_TARGET_ENTRY"
            )

    if (
        status == "BRIDGE_REACHES_TARGET_ENTRY"
        and motif_signal
    ):
        combined = (
            "BRIDGE_PLUS_TARGET_MOTIF_SIGNAL"
        )
    elif status == "BRIDGE_REACHES_TARGET_ENTRY":
        combined = (
            "BRIDGE_ONLY_NO_TARGET_MOTIF_SIGNAL"
        )
    elif motif_signal:
        combined = (
            "TARGET_MOTIF_SIGNAL_WITHOUT_BRIDGE"
        )
    else:
        combined = (
            "NO_BRIDGE_NO_TARGET_MOTIF_SIGNAL"
        )

    batch = batch_audit.get(
        projection_id,
        {},
    )
    batch_status = batch.get(
        "bridge_status",
        ".",
    )
    batch_combined = batch.get(
        "combined_bridge_motif_status",
        ".",
    )

    if (
        batch_combined
        == "BRIDGE_PLUS_TARGET_MOTIF_SIGNAL"
        and combined
        == "BRIDGE_PLUS_TARGET_MOTIF_SIGNAL"
    ):
        comparison = (
            "BRIDGE_REPRODUCED"
        )
    elif (
        batch_combined
        != "BRIDGE_PLUS_TARGET_MOTIF_SIGNAL"
        and combined
        == "BRIDGE_PLUS_TARGET_MOTIF_SIGNAL"
    ):
        comparison = (
            "BRIDGE_RECOVERED_ONLY_IN_ISOLATED_PAIR"
        )
    elif (
        batch_combined
        == "BRIDGE_PLUS_TARGET_MOTIF_SIGNAL"
        and combined
        != "BRIDGE_PLUS_TARGET_MOTIF_SIGNAL"
    ):
        comparison = (
            "BATCH_BRIDGE_NOT_REPRODUCED"
        )
    else:
        comparison = (
            "NO_BRIDGE_IN_EITHER_ANALYSIS"
        )

    result = {
        "model_id": model_id,
        "projection_id": projection_id,
        "read_id": meta["read_id"],
        "target_region_id": meta[
            "target_region_id"
        ],
        "representative_locus_id": meta[
            "representative_locus_id"
        ],
        "canonical_motif": meta[
            "canonical_motif"
        ],
        "assignment_rank": meta[
            "assignment_rank"
        ],
        "best_mapq": meta["best_mapq"],
        "raw_clip_bp": meta["raw_clip_bp"],
        "query_bp": meta["query_bp"],
        "reference_bp": len(
            reference_sequence
        ),
        "bridge_bp": bridge_bp,
        "target_entry_bp": target_entry_bp,
        "required_target_reference_end": (
            required_reference_end
        ),
        "query_can_reach_target_entry": str(
            can_reach
        ).lower(),
        "target_relevant_motif_window_count": meta[
            "oriented_target_relevant_window_count"
        ],
        "oriented_best_window_purity": meta[
            "oriented_best_window_purity"
        ],
        "reference_sequence_sha256": (
            hashlib.sha256(
                reference_sequence.encode()
            ).hexdigest()
        ),
        "reference_sequence_multiplicity": (
            reference_multiplicity[
                projection_id
            ]
        ),
        "isolated_alignment_count": len(
            alignments
        ),
        "best_query_start": (
            best["query_start"]
            if best
            else "."
        ),
        "best_query_end": (
            best["query_end"]
            if best
            else "."
        ),
        "best_query_coverage": (
            "{:.6f}".format(
                best["query_coverage"]
            )
            if best
            else "."
        ),
        "best_reference_start": (
            best["reference_start"]
            if best
            else "."
        ),
        "best_reference_end": (
            best["reference_end"]
            if best
            else "."
        ),
        "best_identity": (
            "{:.6f}".format(
                best["identity"]
            )
            if best
            else "."
        ),
        "best_alignment_score": (
            best["alignment_score"]
            if best
            else "."
        ),
        "best_alignment_mapq": (
            best["mapq"]
            if best
            else "."
        ),
        "isolated_bridge_status": status,
        "isolated_combined_status": (
            combined
        ),
        "batch_bridge_status": batch_status,
        "batch_combined_status": (
            batch_combined
        ),
        "batch_vs_isolated_comparison": (
            comparison
        ),
        "evidence_status": "NOT_CALLED",
        "allele_length_status": (
            "NOT_ASSESSED"
        ),
        "expansion_status": "NOT_ASSESSED",
    }

    with progress_lock:
        progress_state["completed"] += 1
        completed_count = progress_state[
            "completed"
        ]

        if (
            completed_count % PROGRESS_EVERY == 0
            or completed_count == len(metadata)
        ):
            elapsed = (
                time.time()
                - progress_state["start_time"]
            )
            rate = (
                completed_count / elapsed
                if elapsed
                else 0.0
            )
            remaining = (
                (len(metadata) - completed_count)
                / rate
                if rate
                else 0.0
            )
            print(
                "[INFO] isolated pairs {}/{}; "
                "{:.1f} pairs/s; ETA {:.1f} min".format(
                    completed_count,
                    len(metadata),
                    rate,
                    remaining / 60.0,
                ),
                file=sys.stderr,
                flush=True,
            )

    return result


results = []
failures = []

with ThreadPoolExecutor(
    max_workers=WORKERS
) as executor:
    futures = {
        executor.submit(
            run_pair,
            projection_id,
        ): projection_id
        for projection_id in sorted(metadata)
    }

    for future in as_completed(futures):
        projection_id = futures[future]

        try:
            results.append(future.result())
        except Exception as error:
            failures.append(
                (
                    projection_id,
                    str(error),
                )
            )

results.sort(
    key=lambda row: row["projection_id"]
)

if not results:
    raise RuntimeError(
        "No isolated-pair results generated"
    )

output_fields = list(results[0].keys())

with gzip.open(
    output_path,
    "wt",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=output_fields,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(results)

duplicate_rows = []

for digest, projection_ids in sorted(
    reference_hash_groups.items(),
    key=lambda item: (
        -len(item[1]),
        item[0],
    ),
):
    if len(projection_ids) <= 1:
        continue

    targets = {
        metadata[projection_id][
            "target_region_id"
        ]
        for projection_id in projection_ids
    }
    reads = {
        metadata[projection_id]["read_id"]
        for projection_id in projection_ids
    }

    duplicate_rows.append(
        {
            "reference_sequence_sha256": digest,
            "sequence_multiplicity": len(
                projection_ids
            ),
            "unique_reads": len(reads),
            "unique_targets": len(targets),
            "projection_ids": ";".join(
                sorted(projection_ids)
            ),
            "target_region_ids": ";".join(
                sorted(targets)
            ),
        }
    )

duplicate_fields = [
    "reference_sequence_sha256",
    "sequence_multiplicity",
    "unique_reads",
    "unique_targets",
    "projection_ids",
    "target_region_ids",
]

with open(
    duplicates_path,
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=duplicate_fields,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(duplicate_rows)

counts = Counter()
summary_groups = defaultdict(
    lambda: {
        "rows": 0,
        "reads": set(),
        "targets": set(),
        "multiplicities": [],
        "identities": [],
        "coverages": [],
    }
)

for row in results:
    counts[
        "isolated_bridge_status::{}".format(
            row["isolated_bridge_status"]
        )
    ] += 1
    counts[
        "isolated_combined_status::{}".format(
            row["isolated_combined_status"]
        )
    ] += 1
    counts[
        "comparison::{}".format(
            row[
                "batch_vs_isolated_comparison"
            ]
        )
    ] += 1

    group_names = [
        "ALL",
        "isolated_bridge_status::{}".format(
            row["isolated_bridge_status"]
        ),
        "isolated_combined_status::{}".format(
            row["isolated_combined_status"]
        ),
        "comparison::{}".format(
            row[
                "batch_vs_isolated_comparison"
            ]
        ),
    ]

    for group_name in group_names:
        group = summary_groups[group_name]
        group["rows"] += 1
        group["reads"].add(row["read_id"])
        group["targets"].add(
            row["target_region_id"]
        )
        group["multiplicities"].append(
            int(
                row[
                    "reference_sequence_multiplicity"
                ]
            )
        )

        if row["best_identity"] != ".":
            group["identities"].append(
                float(row["best_identity"])
            )
            group["coverages"].append(
                float(
                    row[
                        "best_query_coverage"
                    ]
                )
            )


def median(values):
    if not values:
        return None

    ordered = sorted(values)
    size = len(ordered)

    if size % 2:
        return float(ordered[size // 2])

    return (
        ordered[size // 2 - 1]
        + ordered[size // 2]
    ) / 2.0


summary_fields = [
    "group",
    "rows",
    "unique_reads",
    "unique_targets",
    "reference_multiplicity_median",
    "identity_median",
    "query_coverage_median",
]

with open(
    summary_path,
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=summary_fields,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()

    for group_name in sorted(summary_groups):
        group = summary_groups[group_name]
        multiplicity_median = median(
            group["multiplicities"]
        )
        identity_median = median(
            group["identities"]
        )
        coverage_median = median(
            group["coverages"]
        )

        writer.writerow(
            {
                "group": group_name,
                "rows": group["rows"],
                "unique_reads": len(
                    group["reads"]
                ),
                "unique_targets": len(
                    group["targets"]
                ),
                "reference_multiplicity_median": (
                    "{:.6f}".format(
                        multiplicity_median
                    )
                ),
                "identity_median": (
                    "{:.6f}".format(
                        identity_median
                    )
                    if identity_median
                    is not None
                    else "."
                ),
                "query_coverage_median": (
                    "{:.6f}".format(
                        coverage_median
                    )
                    if coverage_median
                    is not None
                    else "."
                ),
            }
        )

batch_bridge_count = sum(
    row.get(
        "combined_bridge_motif_status"
    )
    == "BRIDGE_PLUS_TARGET_MOTIF_SIGNAL"
    for row in batch_audit.values()
)

isolated_bridge_count = sum(
    row["isolated_combined_status"]
    == "BRIDGE_PLUS_TARGET_MOTIF_SIGNAL"
    for row in results
)

status = "PASS"

if (
    len(metadata) != EXPECTED_PAIRS
    or len(batch_audit) != EXPECTED_PAIRS
    or len(query_sequences) != EXPECTED_PAIRS
    or len(reference_sequences) != EXPECTED_PAIRS
    or missing_queries
    or missing_references
    or failures
    or len(results) != EXPECTED_PAIRS
    or batch_bridge_count
       != EXPECTED_BATCH_BRIDGE
):
    status = "REVIEW"

with open(
    qc_path,
    "w",
    encoding="utf-8",
) as handle:
    handle.write("metric\tvalue\n")
    handle.write(
        "expected_pairs\t{}\n".format(
            EXPECTED_PAIRS
        )
    )
    handle.write(
        "metadata_pairs\t{}\n".format(
            len(metadata)
        )
    )
    handle.write(
        "batch_audit_rows\t{}\n".format(
            len(batch_audit)
        )
    )
    handle.write(
        "query_sequences\t{}\n".format(
            len(query_sequences)
        )
    )
    handle.write(
        "reference_sequences\t{}\n".format(
            len(reference_sequences)
        )
    )
    handle.write(
        "missing_queries\t{}\n".format(
            len(missing_queries)
        )
    )
    handle.write(
        "missing_references\t{}\n".format(
            len(missing_references)
        )
    )
    handle.write(
        "isolated_pair_failures\t{}\n".format(
            len(failures)
        )
    )
    handle.write(
        "isolated_results_written\t{}\n".format(
            len(results)
        )
    )
    handle.write(
        "unique_reference_sequences\t{}\n".format(
            len(reference_hash_groups)
        )
    )
    handle.write(
        "duplicate_reference_groups\t{}\n".format(
            len(duplicate_rows)
        )
    )
    handle.write(
        "batch_bridge_plus_motif\t{}\n".format(
            batch_bridge_count
        )
    )
    handle.write(
        "isolated_bridge_plus_motif\t{}\n".format(
            isolated_bridge_count
        )
    )

    for key, count in sorted(counts.items()):
        handle.write(
            "{}\t{}\n".format(key, count)
        )

    handle.write("evidence_calls_emitted\t0\n")
    handle.write("allele_length_calls_emitted\t0\n")
    handle.write("expansion_calls_emitted\t0\n")
    handle.write(
        "audit_status\t{}\n".format(status)
    )

if failures:
    with open(
        qc_path + ".failures.tsv",
        "w",
        encoding="utf-8",
    ) as handle:
        handle.write(
            "projection_id\terror\n"
        )
        for projection_id, error in failures:
            handle.write(
                "{}\t{}\n".format(
                    projection_id,
                    error.replace("\t", " "),
                )
            )

if status != "PASS":
    raise SystemExit(
        "Isolated P3 pair validation requires review"
    )
PY

echo "===== SHELL AND EMBEDDED PYTHON SYNTAX ====="
python -m py_compile "$PY"
echo "Embedded Python syntax: OK"

rm -f \
  "$OUTPUT" \
  "$SUMMARY" \
  "$DUPLICATES" \
  "$QC" \
  "${QC}.failures.tsv" \
  "$MANIFEST"

find "$WORKDIR" \
  -maxdepth 1 \
  -type d \
  -name 'pair_*' \
  -exec rm -rf {} +

echo
echo "===== RUN ISOLATED P3 PAIR VALIDATION ====="

python "$PY" \
  "$PAIR_META" \
  "$BATCH_AUDIT" \
  "$QUERY_FASTA" \
  "$REFERENCE_FASTA" \
  "$OUTPUT" \
  "$SUMMARY" \
  "$DUPLICATES" \
  "$QC" \
  "$WORKDIR" \
  "$MODEL_ID" \
  "$EXPECTED_PAIRS" \
  "$EXPECTED_BATCH_BRIDGE_PLUS_MOTIF" \
  "$WORKERS" \
  "$PROGRESS_EVERY" \
  "$MIN_TARGET_ENTRY_SUPPORT_BP" \
  "$BOUNDARY_TOLERANCE_BP" \
  "$MIN_ALIGNMENT_IDENTITY" \
  "$MIN_ALIGNMENT_QUERY_COVERAGE"

gzip -t "$OUTPUT"

echo
echo "===== QC ====="
column -ts $'\t' "$QC"

echo
echo "===== SUMMARY ====="
column -ts $'\t' "$SUMMARY"

echo
echo "===== DUPLICATE REFERENCE GROUPS ====="
column -ts $'\t' "$DUPLICATES" | head -n 31

echo
echo "===== ISOLATED BRIDGE+MOTIF ROWS ====="
gzip -cd "$OUTPUT" \
  | awk -F '\t' '
      NR == 1 {
          for (i = 1; i <= NF; i++) {
              if ($i == "isolated_combined_status") {
                  column = i
              }
          }
          print
          next
      }
      $column == "BRIDGE_PLUS_TARGET_MOTIF_SIGNAL" {
          print
      }
  ' \
  | column -ts $'\t'

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in "$OUTPUT"; do
        rows="$(gzip -cd "$path" | awk 'END {print NR-1}')"

        printf '%s\t%s\t%s\t%s\t%s\n' \
          "$(basename "$path")" \
          "$rows" \
          "$(stat -c '%s' "$path")" \
          "$(sha256sum "$path" | awk '{print $1}')" \
          "$path"
    done

    for path in \
      "$SUMMARY" \
      "$DUPLICATES" \
      "$QC" \
      "$PARAMETERS"
    do
        rows="$(awk 'END {print NR-1}' "$path")"

        printf '%s\t%s\t%s\t%s\t%s\n' \
          "$(basename "$path")" \
          "$rows" \
          "$(stat -c '%s' "$path")" \
          "$(sha256sum "$path" | awk '{print $1}')" \
          "$path"
    done
} > "$MANIFEST"

echo
echo "===== MANIFEST ====="
column -ts $'\t' "$MANIFEST"

echo
echo "===== COMPLETE ====="
echo "$OUTPUT"
echo "$SUMMARY"
echo "$DUPLICATES"
echo "$QC"
