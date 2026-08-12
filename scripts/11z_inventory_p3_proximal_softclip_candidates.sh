#!/usr/bin/env bash
set -euo pipefail

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
fi

conda activate rnatr-v03
source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"
INVENTORY_VERSION="rnatr_p3_proximal_inventory_v0.3.1"

JOBS="$PROJECT_ROOT/results/11_motif_jobs/$RUN_ID/motif_scan_jobs.tsv.gz"
PROJECTION="$PROJECT_ROOT/results/11_projection/$RUN_ID/v0.3.3/read_target_projection.v0.3.3.tsv.gz"
FASTQ="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_candidates_v0.3.1/ENCFF260PGB.pilot_100k.rnatr_candidate_all.fastq.gz"

OUTDIR="$PROJECT_ROOT/results/11_p3_inventory/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_p3_inventory/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_p3_inventory/$RUN_ID"
DATADIR="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_p3_inventory"

INVENTORY="$OUTDIR/p3_proximal_inventory.tsv.gz"
READY="$OUTDIR/p3_softclip_scan_ready.tsv.gz"
SUMMARY="$OUTDIR/p3_proximal_inventory_summary.tsv"
READY_FASTQ="$DATADIR/p3_softclip_scan_ready.unique_reads.fastq.gz"
QC="$QCDIR/p3_proximal_inventory.qc.tsv"
PARAMETERS="$OUTDIR/${INVENTORY_VERSION}.parameters.tsv"
MANIFEST="$OUTDIR/${RUN_ID}.p3_proximal_inventory.manifest.tsv"
PY="$WORKDIR/build_p3_inventory.py"

EXPECTED_JOB_ROWS=388571
EXPECTED_PROJECTION_ROWS=388571
EXPECTED_FASTQ_READS=79176

MIN_SOFTCLIP_BP=12
WINDOW_BP=30
WINDOW_STEP_BP=10
DIAGNOSTIC_PURITY=0.70

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR" "$DATADIR"

for path in "$JOBS" "$PROJECTION" "$FASTQ"; do
    test -s "$path" || {
        echo "ERROR: missing input: $path" >&2
        exit 1
    }
done

cat > "$PARAMETERS" <<EOF
parameter	value	meaning
inventory_version	$INVENTORY_VERSION	P3 proximal candidate inventory
selected_priority	P3_PROXIMAL	Targets near but not exactly overlapped by the selected alignment block
minimum_softclip_bp	$MIN_SOFTCLIP_BP	Minimum target-facing raw soft clip for sequence scanning
diagnostic_window_bp	$WINDOW_BP	Window used only to characterize motif-like content
diagnostic_window_step_bp	$WINDOW_STEP_BP	Sliding-window step
diagnostic_purity	$DIAGNOSTIC_PURITY	Descriptive threshold, not a repeat call
softclip_coordinate_semantics	raw_fastq_zero_based_half_open	Coordinates refer to original raw FASTQ orientation
route_semantics	inventory_not_evidence_call	No SPAN, lower-bound, allele-length, or expansion call
EOF

cat > "$PY" <<'PY'
from __future__ import annotations

import csv
import gzip
import math
import sys
from collections import Counter, defaultdict

import pysam

(
    jobs_path,
    projection_path,
    fastq_path,
    inventory_path,
    ready_path,
    summary_path,
    ready_fastq_path,
    qc_path,
    inventory_version,
    expected_job_rows_text,
    expected_projection_rows_text,
    expected_fastq_reads_text,
    minimum_softclip_text,
    window_bp_text,
    window_step_text,
    diagnostic_purity_text,
) = sys.argv[1:]

EXPECTED_JOB_ROWS = int(expected_job_rows_text)
EXPECTED_PROJECTION_ROWS = int(
    expected_projection_rows_text
)
EXPECTED_FASTQ_READS = int(expected_fastq_reads_text)

MINIMUM_SOFTCLIP = int(minimum_softclip_text)
WINDOW_BP = int(window_bp_text)
WINDOW_STEP = int(window_step_text)
DIAGNOSTIC_PURITY = float(diagnostic_purity_text)

COMPLEMENT = str.maketrans("ACGT", "TGCA")


def reverse_complement(sequence):
    return sequence.translate(COMPLEMENT)[::-1]


def rotations(sequence):
    return [
        sequence[index:] + sequence[:index]
        for index in range(len(sequence))
    ]


def canonical_motif(sequence):
    candidates = []

    for oriented in (
        sequence,
        reverse_complement(sequence),
    ):
        candidates.extend(rotations(oriented))

    return min(candidates)


def phase_purity(sequence, motif):
    if not sequence or not motif:
        return 0.0, "."

    candidates = set(
        rotations(motif)
        + rotations(reverse_complement(motif))
    )

    best_purity = -1.0
    best_orientation = "."

    for candidate in candidates:
        matches = sum(
            base
            == candidate[index % len(candidate)]
            for index, base in enumerate(sequence)
        )
        purity = matches / len(sequence)

        if purity > best_purity:
            best_purity = purity
            best_orientation = candidate

    return best_purity, best_orientation


def diagnostic_windows(sequence, motif):
    if not sequence:
        return {
            "window_count": 0,
            "repeat_like_window_count": 0,
            "best_window_start": ".",
            "best_window_end": ".",
            "best_window_purity": 0.0,
            "best_window_orientation": ".",
        }

    if len(sequence) <= WINDOW_BP:
        intervals = [(0, len(sequence))]
    else:
        intervals = []
        start = 0

        while start < len(sequence):
            end = min(
                len(sequence),
                start + WINDOW_BP,
            )

            if end - start >= MINIMUM_SOFTCLIP:
                intervals.append((start, end))

            if end == len(sequence):
                break

            start += WINDOW_STEP

    best = None
    repeat_like = 0

    for start, end in intervals:
        purity, orientation = phase_purity(
            sequence[start:end],
            motif,
        )

        if purity >= DIAGNOSTIC_PURITY:
            repeat_like += 1

        candidate = (
            purity,
            end - start,
            -start,
            start,
            end,
            orientation,
        )

        if best is None or candidate[:3] > best[:3]:
            best = candidate

    if best is None:
        return {
            "window_count": 0,
            "repeat_like_window_count": 0,
            "best_window_start": ".",
            "best_window_end": ".",
            "best_window_purity": 0.0,
            "best_window_orientation": ".",
        }

    return {
        "window_count": len(intervals),
        "repeat_like_window_count": repeat_like,
        "best_window_start": best[3],
        "best_window_end": best[4],
        "best_window_purity": best[0],
        "best_window_orientation": best[5],
    }


def quantile(values, probability):
    if not values:
        return 0.0

    ordered = sorted(values)

    if len(ordered) == 1:
        return float(ordered[0])

    position = probability * (len(ordered) - 1)
    low = math.floor(position)
    high = math.ceil(position)

    if low == high:
        return float(ordered[low])

    fraction = position - low

    return (
        ordered[low] * (1.0 - fraction)
        + ordered[high] * fraction
    )


# ------------------------------------------------------------------
# Select P3 motif jobs.
# ------------------------------------------------------------------

p3_jobs = {}
job_rows = 0

with gzip.open(
    jobs_path,
    "rt",
    encoding="utf-8",
    newline="",
) as handle:
    reader = csv.DictReader(handle, delimiter="\t")

    for row in reader:
        job_rows += 1

        if row["scan_priority"] != "P3_PROXIMAL":
            continue

        projection_id = row["projection_id"]

        if projection_id in p3_jobs:
            raise RuntimeError(
                "Duplicate P3 projection ID: {}".format(
                    projection_id
                )
            )

        p3_jobs[projection_id] = row

if not p3_jobs:
    raise RuntimeError("No P3_PROXIMAL jobs selected")

# ------------------------------------------------------------------
# Load matching projection rows.
# ------------------------------------------------------------------

projections = {}
projection_rows = 0

with gzip.open(
    projection_path,
    "rt",
    encoding="utf-8",
    newline="",
) as handle:
    reader = csv.DictReader(handle, delimiter="\t")

    for row in reader:
        projection_rows += 1
        projection_id = row["projection_id"]

        if projection_id in p3_jobs:
            projections[projection_id] = row

missing_projections = set(p3_jobs) - set(projections)

# ------------------------------------------------------------------
# Load unique P3 reads from candidate FASTQ.
# ------------------------------------------------------------------

required_read_ids = {
    row["read_id"]
    for row in projections.values()
}

fastq_records = {}
all_fastq_read_count = 0

with pysam.FastxFile(fastq_path) as source:
    for entry in source:
        all_fastq_read_count += 1

        if entry.name in required_read_ids:
            fastq_records[entry.name] = {
                "sequence": entry.sequence.upper(),
                "quality": entry.quality,
                "comment": entry.comment or "",
            }

missing_reads = required_read_ids - set(fastq_records)

# ------------------------------------------------------------------
# Build inventory.
# ------------------------------------------------------------------

columns = [
    "inventory_version",
    "projection_id",
    "read_id",
    "target_region_id",
    "target_source",
    "region_type",
    "representative_locus_id",
    "assignment_rank",
    "read_candidate_target_count",
    "candidate_basis",
    "geometry_class",
    "projection_status",
    "potential_evidence_class",
    "scan_strategy",
    "motif_scan_eligible",
    "canonical_motifs",
    "strand",
    "read_length_bp",
    "best_mapq",
    "target_chrom",
    "target_start",
    "target_end",
    "selected_block_start",
    "selected_block_end",
    "selected_block_distance_bp",
    "genomic_left_anchor_bp",
    "genomic_right_anchor_bp",
    "genomic_left_softclip_bp",
    "genomic_right_softclip_bp",
    "target_facing_genomic_side",
    "validated_anchor_genomic_side",
    "target_facing_softclip_bp",
    "target_facing_raw_start",
    "target_facing_raw_end",
    "target_facing_expected_raw_end",
    "softclip_whole_motif_purity",
    "softclip_best_orientation",
    "diagnostic_window_count",
    "diagnostic_repeat_like_window_count",
    "diagnostic_best_window_start",
    "diagnostic_best_window_end",
    "diagnostic_best_window_purity",
    "diagnostic_best_window_orientation",
    "p3_route",
    "p3_route_reason",
]

inventory_rows = []
ready_rows = []
ready_read_ids = set()
counts = Counter()

for projection_id in sorted(p3_jobs):
    job = p3_jobs[projection_id]
    projection = projections.get(projection_id)

    if projection is None:
        continue

    read_id = projection["read_id"]
    record = fastq_records.get(read_id)

    if record is None:
        continue

    sequence = record["sequence"]
    read_length = len(sequence)
    strand = projection["strand"]
    geometry = projection["geometry_class"]

    left_softclip = int(
        projection["genomic_left_softclip_bp"]
    )
    right_softclip = int(
        projection["genomic_right_softclip_bp"]
    )

    target_side = "."
    anchor_side = "."
    softclip_bp = 0
    raw_start = None
    raw_end = None
    expected_raw_end = "."
    route = "."
    route_reason = "."

    if geometry == "PROXIMAL_RIGHT_WITH_SOFTCLIP":
        target_side = "GENOMIC_RIGHT"
        anchor_side = "GENOMIC_LEFT"
        softclip_bp = right_softclip

        if strand == "+":
            raw_start = read_length - softclip_bp
            raw_end = read_length
            expected_raw_end = "RAW_END"
        else:
            raw_start = 0
            raw_end = softclip_bp
            expected_raw_end = "RAW_START"

    elif geometry == "PROXIMAL_LEFT_WITH_SOFTCLIP":
        target_side = "GENOMIC_LEFT"
        anchor_side = "GENOMIC_RIGHT"
        softclip_bp = left_softclip

        if strand == "+":
            raw_start = 0
            raw_end = softclip_bp
            expected_raw_end = "RAW_START"
        else:
            raw_start = read_length - softclip_bp
            raw_end = read_length
            expected_raw_end = "RAW_END"

    elif geometry in {
        "PROXIMAL_RIGHT_NO_SOFTCLIP",
        "PROXIMAL_LEFT_NO_SOFTCLIP",
    }:
        route = "P3_NO_SOFTCLIP_NEGATIVE_CONTROL"
        route_reason = (
            "Target is proximal but the target-facing alignment "
            "end has no soft-clipped raw sequence"
        )

    elif geometry == "PROXIMAL_ONLY":
        route = "P3_PROXIMAL_ONLY_NEGATIVE_CONTROL"
        route_reason = (
            "No validated target-facing flank/softclip geometry"
        )

    else:
        route = "P3_OTHER_GEOMETRY_REVIEW"
        route_reason = (
            "P3 candidate has an unsupported or unresolved "
            "projection geometry"
        )

    clip_sequence = ""

    if raw_start is not None and raw_end is not None:
        if not (
            0 <= raw_start <= raw_end <= read_length
        ):
            raise RuntimeError(
                "Invalid P3 softclip coordinates for {}: "
                "{}-{} / {}".format(
                    projection_id,
                    raw_start,
                    raw_end,
                    read_length,
                )
            )

        clip_sequence = sequence[raw_start:raw_end]

        if len(clip_sequence) != softclip_bp:
            raise RuntimeError(
                "P3 softclip length mismatch for {}".format(
                    projection_id
                )
            )

        if softclip_bp < MINIMUM_SOFTCLIP:
            route = "P3_SOFTCLIP_TOO_SHORT"
            route_reason = (
                "Target-facing raw softclip is shorter than "
                "the minimum scan length"
            )

        elif projection["projection_status"] != "PASS":
            route = "P3_PROJECTION_REVIEW"
            route_reason = (
                "Target-facing softclip exists but projection "
                "status is not PASS"
            )

        elif job["motif_scan_eligible"] != "true":
            route = "P3_SPECIALIZED_OR_MANUAL_ROUTE"
            route_reason = (
                "Motif job is not eligible for the standard "
                "periodic scanner"
            )

        elif job["scan_strategy"] == "SIMPLE_PERIODIC_SCAN":
            route = "P3_SOFTCLIP_SIMPLE_PERIODIC_READY"
            route_reason = (
                "Target-facing raw softclip is available for "
                "a dedicated proximal simple-periodic caller"
            )

        else:
            route = "P3_SOFTCLIP_SPECIALIZED_MOTIF_READY"
            route_reason = (
                "Target-facing raw softclip is available but "
                "requires a non-simple motif strategy"
            )

    motifs = [
        motif
        for motif in job["canonical_motifs"].split(",")
        if motif and motif != "."
    ]
    diagnostic_motif = (
        canonical_motif(motifs[0])
        if len(motifs) == 1
        and set(motifs[0]).issubset(set("ACGT"))
        else None
    )

    if clip_sequence and diagnostic_motif:
        whole_purity, whole_orientation = phase_purity(
            clip_sequence,
            diagnostic_motif,
        )
        windows = diagnostic_windows(
            clip_sequence,
            diagnostic_motif,
        )
    else:
        whole_purity = 0.0
        whole_orientation = "."
        windows = {
            "window_count": 0,
            "repeat_like_window_count": 0,
            "best_window_start": ".",
            "best_window_end": ".",
            "best_window_purity": 0.0,
            "best_window_orientation": ".",
        }

    output_row = {
        "inventory_version": inventory_version,
        "projection_id": projection_id,
        "read_id": read_id,
        "target_region_id": job["target_region_id"],
        "target_source": job["target_source"],
        "region_type": job["region_type"],
        "representative_locus_id": job[
            "representative_locus_id"
        ],
        "assignment_rank": job["assignment_rank"],
        "read_candidate_target_count": job[
            "read_candidate_target_count"
        ],
        "candidate_basis": job["candidate_basis"],
        "geometry_class": geometry,
        "projection_status": projection[
            "projection_status"
        ],
        "potential_evidence_class": job[
            "potential_evidence_class"
        ],
        "scan_strategy": job["scan_strategy"],
        "motif_scan_eligible": job[
            "motif_scan_eligible"
        ],
        "canonical_motifs": job["canonical_motifs"],
        "strand": strand,
        "read_length_bp": read_length,
        "best_mapq": projection["best_mapq"],
        "target_chrom": projection["target_chrom"],
        "target_start": projection["target_start"],
        "target_end": projection["target_end"],
        "selected_block_start": projection[
            "selected_block_start"
        ],
        "selected_block_end": projection[
            "selected_block_end"
        ],
        "selected_block_distance_bp": projection[
            "selected_block_distance_bp"
        ],
        "genomic_left_anchor_bp": projection[
            "genomic_left_anchor_bp"
        ],
        "genomic_right_anchor_bp": projection[
            "genomic_right_anchor_bp"
        ],
        "genomic_left_softclip_bp": left_softclip,
        "genomic_right_softclip_bp": right_softclip,
        "target_facing_genomic_side": target_side,
        "validated_anchor_genomic_side": anchor_side,
        "target_facing_softclip_bp": softclip_bp,
        "target_facing_raw_start": (
            "."
            if raw_start is None
            else raw_start
        ),
        "target_facing_raw_end": (
            "."
            if raw_end is None
            else raw_end
        ),
        "target_facing_expected_raw_end": (
            expected_raw_end
        ),
        "softclip_whole_motif_purity": (
            "{:.6f}".format(whole_purity)
        ),
        "softclip_best_orientation": whole_orientation,
        "diagnostic_window_count": windows[
            "window_count"
        ],
        "diagnostic_repeat_like_window_count": windows[
            "repeat_like_window_count"
        ],
        "diagnostic_best_window_start": windows[
            "best_window_start"
        ],
        "diagnostic_best_window_end": windows[
            "best_window_end"
        ],
        "diagnostic_best_window_purity": (
            "{:.6f}".format(
                windows["best_window_purity"]
            )
        ),
        "diagnostic_best_window_orientation": windows[
            "best_window_orientation"
        ],
        "p3_route": route,
        "p3_route_reason": route_reason,
    }

    inventory_rows.append(output_row)
    counts["route::{}".format(route)] += 1
    counts["geometry::{}".format(geometry)] += 1
    counts[
        "strategy::{}".format(job["scan_strategy"])
    ] += 1
    counts[
        "candidate_basis::{}".format(
            job["candidate_basis"]
        )
    ] += 1

    if route in {
        "P3_SOFTCLIP_SIMPLE_PERIODIC_READY",
        "P3_SOFTCLIP_SPECIALIZED_MOTIF_READY",
    }:
        ready_rows.append(output_row)
        ready_read_ids.add(read_id)

# ------------------------------------------------------------------
# Write inventory and scan-ready subset.
# ------------------------------------------------------------------

with gzip.open(
    inventory_path,
    "wt",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=columns,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(inventory_rows)

with gzip.open(
    ready_path,
    "wt",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=columns,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(ready_rows)

with gzip.open(
    ready_fastq_path,
    "wt",
    encoding="utf-8",
) as handle:
    for read_id in sorted(ready_read_ids):
        record = fastq_records[read_id]
        header = "@{}".format(read_id)

        if record["comment"]:
            header += " " + record["comment"]

        handle.write(
            "{}\n{}\n+\n{}\n".format(
                header,
                record["sequence"],
                record["quality"],
            )
        )

# ------------------------------------------------------------------
# Summary.
# ------------------------------------------------------------------

summary_groups = defaultdict(
    lambda: {
        "rows": 0,
        "reads": set(),
        "targets": set(),
        "softclips": [],
        "whole_purities": [],
        "best_window_purities": [],
    }
)

for row in inventory_rows:
    group_names = [
        "ALL",
        "route::{}".format(row["p3_route"]),
        "geometry::{}".format(row["geometry_class"]),
        "strategy::{}".format(row["scan_strategy"]),
    ]

    for group_name in group_names:
        group = summary_groups[group_name]
        group["rows"] += 1
        group["reads"].add(row["read_id"])
        group["targets"].add(row["target_region_id"])

        softclip_bp = int(
            row["target_facing_softclip_bp"]
        )

        if softclip_bp > 0:
            group["softclips"].append(softclip_bp)
            group["whole_purities"].append(
                float(
                    row[
                        "softclip_whole_motif_purity"
                    ]
                )
            )
            group["best_window_purities"].append(
                float(
                    row[
                        "diagnostic_best_window_purity"
                    ]
                )
            )

summary_fields = [
    "group",
    "rows",
    "unique_reads",
    "unique_targets",
    "softclip_rows",
    "softclip_bp_median",
    "softclip_bp_p95",
    "softclip_bp_max",
    "whole_motif_purity_median",
    "best_window_purity_median",
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
        softclips = group["softclips"]

        writer.writerow(
            {
                "group": group_name,
                "rows": group["rows"],
                "unique_reads": len(group["reads"]),
                "unique_targets": len(group["targets"]),
                "softclip_rows": len(softclips),
                "softclip_bp_median": (
                    "{:.6f}".format(
                        quantile(softclips, 0.50)
                    )
                    if softclips
                    else "."
                ),
                "softclip_bp_p95": (
                    "{:.6f}".format(
                        quantile(softclips, 0.95)
                    )
                    if softclips
                    else "."
                ),
                "softclip_bp_max": (
                    max(softclips)
                    if softclips
                    else "."
                ),
                "whole_motif_purity_median": (
                    "{:.6f}".format(
                        quantile(
                            group["whole_purities"],
                            0.50,
                        )
                    )
                    if group["whole_purities"]
                    else "."
                ),
                "best_window_purity_median": (
                    "{:.6f}".format(
                        quantile(
                            group[
                                "best_window_purities"
                            ],
                            0.50,
                        )
                    )
                    if group[
                        "best_window_purities"
                    ]
                    else "."
                ),
            }
        )

status = "PASS"

if (
    job_rows != EXPECTED_JOB_ROWS
    or projection_rows
       != EXPECTED_PROJECTION_ROWS
    or all_fastq_read_count
       != EXPECTED_FASTQ_READS
    or missing_projections
    or missing_reads
    or len(inventory_rows) != len(p3_jobs)
):
    status = "REVIEW"

with open(
    qc_path,
    "w",
    encoding="utf-8",
) as handle:
    handle.write("metric\tvalue\n")
    handle.write(
        "expected_job_rows\t{}\n".format(
            EXPECTED_JOB_ROWS
        )
    )
    handle.write(
        "observed_job_rows\t{}\n".format(
            job_rows
        )
    )
    handle.write(
        "expected_projection_rows\t{}\n".format(
            EXPECTED_PROJECTION_ROWS
        )
    )
    handle.write(
        "observed_projection_rows\t{}\n".format(
            projection_rows
        )
    )
    handle.write(
        "expected_candidate_fastq_reads\t{}\n".format(
            EXPECTED_FASTQ_READS
        )
    )
    handle.write(
        "observed_candidate_fastq_reads\t{}\n".format(
            all_fastq_read_count
        )
    )
    handle.write(
        "selected_p3_jobs\t{}\n".format(
            len(p3_jobs)
        )
    )
    handle.write(
        "selected_p3_projection_rows\t{}\n".format(
            len(projections)
        )
    )
    handle.write(
        "missing_p3_projections\t{}\n".format(
            len(missing_projections)
        )
    )
    handle.write(
        "unique_p3_reads_required\t{}\n".format(
            len(required_read_ids)
        )
    )
    handle.write(
        "unique_p3_reads_found\t{}\n".format(
            len(fastq_records)
        )
    )
    handle.write(
        "missing_p3_fastq_reads\t{}\n".format(
            len(missing_reads)
        )
    )
    handle.write(
        "inventory_rows_written\t{}\n".format(
            len(inventory_rows)
        )
    )
    handle.write(
        "scan_ready_rows_written\t{}\n".format(
            len(ready_rows)
        )
    )
    handle.write(
        "scan_ready_unique_reads_written\t{}\n".format(
            len(ready_read_ids)
        )
    )

    for key, count in sorted(counts.items()):
        handle.write(
            "{}\t{}\n".format(key, count)
        )

    handle.write(
        "evidence_calls_emitted\t0\n"
    )
    handle.write(
        "allele_length_calls_emitted\t0\n"
    )
    handle.write(
        "expansion_calls_emitted\t0\n"
    )
    handle.write(
        "audit_status\t{}\n".format(status)
    )

if status != "PASS":
    raise SystemExit(
        "P3 proximal inventory requires review"
    )
PY

echo "===== SHELL AND EMBEDDED PYTHON SYNTAX ====="
python -m py_compile "$PY"
echo "Embedded Python syntax: OK"

rm -f \
  "$INVENTORY" \
  "$READY" \
  "$SUMMARY" \
  "$READY_FASTQ" \
  "$QC" \
  "$MANIFEST"

echo
echo "===== BUILD P3 PROXIMAL INVENTORY ====="

python "$PY" \
  "$JOBS" \
  "$PROJECTION" \
  "$FASTQ" \
  "$INVENTORY" \
  "$READY" \
  "$SUMMARY" \
  "$READY_FASTQ" \
  "$QC" \
  "$INVENTORY_VERSION" \
  "$EXPECTED_JOB_ROWS" \
  "$EXPECTED_PROJECTION_ROWS" \
  "$EXPECTED_FASTQ_READS" \
  "$MIN_SOFTCLIP_BP" \
  "$WINDOW_BP" \
  "$WINDOW_STEP_BP" \
  "$DIAGNOSTIC_PURITY"

gzip -t "$INVENTORY"
gzip -t "$READY"
gzip -t "$READY_FASTQ"

echo
echo "===== P3 INVENTORY QC ====="
column -ts $'\t' "$QC"

echo
echo "===== P3 INVENTORY SUMMARY ====="
column -ts $'\t' "$SUMMARY"

echo
echo "===== FIRST 30 SCAN-READY ROWS ====="
gzip -cd "$READY" \
  | head -n 31 \
  | column -ts $'\t'

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in \
      "$INVENTORY" \
      "$READY"
    do
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

    rows="$(gzip -cd "$READY_FASTQ" | awk 'END {print NR/4}')"

    printf '%s\t%s\t%s\t%s\t%s\n' \
      "$(basename "$READY_FASTQ")" \
      "$rows" \
      "$(stat -c '%s' "$READY_FASTQ")" \
      "$(sha256sum "$READY_FASTQ" | awk '{print $1}')" \
      "$READY_FASTQ"
} > "$MANIFEST"

echo
echo "===== MANIFEST ====="
column -ts $'\t' "$MANIFEST"

echo
echo "===== COMPLETE ====="
echo "$INVENTORY"
echo "$READY"
echo "$SUMMARY"
echo "$READY_FASTQ"
echo "$QC"
