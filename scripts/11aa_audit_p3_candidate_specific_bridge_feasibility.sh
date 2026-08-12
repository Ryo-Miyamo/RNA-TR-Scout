#!/usr/bin/env bash
set -euo pipefail

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
fi

conda activate rnatr-v03
source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"
MODEL_ID="rnatr_p3_bridge_feasibility_v0.3.1"

INVENTORY="$PROJECT_ROOT/results/11_p3_inventory/$RUN_ID/p3_proximal_inventory.tsv.gz"
FASTQ="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_candidates_v0.3.1/ENCFF260PGB.pilot_100k.rnatr_candidate_all.fastq.gz"
REFERENCE_FASTA="$PROJECT_ROOT/refs/gencode_v50/GRCh38.primary_assembly.genome.fa"

OUTDIR="$PROJECT_ROOT/results/11_p3_bridge_feasibility/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_p3_bridge_feasibility/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_p3_bridge_feasibility/$RUN_ID"
DATADIR="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_p3_bridge_feasibility"

SELECTED="$OUTDIR/p3_bridge_calibration_candidates.tsv.gz"
PAIR_META="$OUTDIR/p3_bridge_pair_metadata.tsv.gz"
PAF="$OUTDIR/p3_bridge_candidate_specific_alignments.paf"
AUDIT="$OUTDIR/p3_bridge_feasibility_audit.tsv.gz"
SUMMARY="$OUTDIR/p3_bridge_feasibility_summary.tsv"
QUERY_FASTA_GZ="$DATADIR/p3_bridge_queries.fasta.gz"
REFERENCE_PAIR_FASTA_GZ="$DATADIR/p3_bridge_candidate_references.fasta.gz"
QC="$QCDIR/p3_bridge_feasibility.qc.tsv"
PARAMETERS="$OUTDIR/${MODEL_ID}.parameters.tsv"
MANIFEST="$OUTDIR/${RUN_ID}.p3_bridge_feasibility.manifest.tsv"

QUERY_FASTA="$WORKDIR/p3_bridge_queries.fa"
REFERENCE_PAIR_FASTA="$WORKDIR/p3_bridge_candidate_references.fa"
PREPARE_PY="$WORKDIR/prepare_p3_bridge_pairs.py"
PARSE_PY="$WORKDIR/parse_p3_bridge_alignments.py"

EXPECTED_INVENTORY_ROWS=211939
EXPECTED_SIMPLE_READY_ROWS=38424
EXPECTED_FASTQ_READS=79176

MIN_MAPQ=20
MIN_SOFTCLIP_BP=12
MIN_TARGET_ENTRY_SUPPORT_BP=12
TARGET_ENTRY_BP=60
BOUNDARY_TOLERANCE_BP=10
MIN_ALIGNMENT_IDENTITY=0.70
MIN_ALIGNMENT_QUERY_COVERAGE=0.70
DIAGNOSTIC_WINDOW_BP=30
DIAGNOSTIC_WINDOW_STEP_BP=10
DIAGNOSTIC_PURITY=0.70

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR" "$DATADIR"

for path in \
  "$INVENTORY" \
  "$FASTQ" \
  "$REFERENCE_FASTA" \
  "${REFERENCE_FASTA}.fai"
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
model_id	$MODEL_ID	P3 candidate-specific bridge feasibility audit
calibration_route	P3_SOFTCLIP_SIMPLE_PERIODIC_READY	Initial simple-periodic proximal cohort
assignment_rank	1	Initial calibration uses rank-1 target hypothesis
minimum_mapq	$MIN_MAPQ	Minimum selected alignment MAPQ
minimum_softclip_bp	$MIN_SOFTCLIP_BP	Minimum target-facing raw soft clip
motif_prefilter	diagnostic_repeat_like_window_count_gt_0	At least one 30-bp window with motif purity >=0.70
target_entry_bp	$TARGET_ENTRY_BP	Reference repeat bases included beyond target boundary
minimum_target_entry_support_bp	$MIN_TARGET_ENTRY_SUPPORT_BP	Reference bases required inside target
boundary_tolerance_bp	$BOUNDARY_TOLERANCE_BP	Maximum query/reference start offset from aligned-block boundary
minimum_alignment_identity	$MIN_ALIGNMENT_IDENTITY	Provisional ONT bridge compatibility threshold
minimum_alignment_query_coverage	$MIN_ALIGNMENT_QUERY_COVERAGE	Minimum candidate-specific query coverage
query_orientation	aligned_block_boundary_toward_target	Raw clip is strand/side normalized
reference_orientation	aligned_block_boundary_toward_target	Target-left references are reverse-complemented
bridge_semantics	feasibility_audit_only	No repeat evidence, allele length, or expansion call
EOF

cat > "$PREPARE_PY" <<'PY'
from __future__ import annotations

import csv
import gzip
import sys

import pysam

(
    inventory_path,
    fastq_path,
    reference_fasta_path,
    selected_path,
    metadata_path,
    query_fasta_path,
    reference_pair_fasta_path,
    query_fasta_gz_path,
    reference_pair_fasta_gz_path,
    model_id,
    expected_inventory_text,
    expected_simple_ready_text,
    expected_fastq_text,
    minimum_mapq_text,
    minimum_softclip_text,
    target_entry_text,
    diagnostic_window_text,
    diagnostic_step_text,
    diagnostic_purity_text,
) = sys.argv[1:]

EXPECTED_INVENTORY = int(expected_inventory_text)
EXPECTED_SIMPLE_READY = int(expected_simple_ready_text)
EXPECTED_FASTQ = int(expected_fastq_text)

MINIMUM_MAPQ = int(minimum_mapq_text)
MINIMUM_SOFTCLIP = int(minimum_softclip_text)
TARGET_ENTRY_BP = int(target_entry_text)
WINDOW_BP = int(diagnostic_window_text)
WINDOW_STEP = int(diagnostic_step_text)
DIAGNOSTIC_PURITY = float(diagnostic_purity_text)

COMPLEMENT = str.maketrans("ACGT", "TGCA")


def reverse_complement(sequence):
    return sequence.translate(COMPLEMENT)[::-1]


def rotations(sequence):
    return [
        sequence[index:] + sequence[:index]
        for index in range(len(sequence))
    ]


def phase_purity(sequence, motif):
    candidates = set(
        rotations(motif)
        + rotations(reverse_complement(motif))
    )
    best_purity = 0.0
    best_orientation = "."

    for candidate in candidates:
        matches = sum(
            base == candidate[index % len(candidate)]
            for index, base in enumerate(sequence)
        )
        purity = matches / len(sequence) if sequence else 0.0

        if purity > best_purity:
            best_purity = purity
            best_orientation = candidate

    return best_purity, best_orientation


def diagnostic_windows(sequence, motif):
    if len(sequence) <= WINDOW_BP:
        intervals = [(0, len(sequence))]
    else:
        intervals = []
        start = 0

        while start < len(sequence):
            end = min(len(sequence), start + WINDOW_BP)

            if end - start >= 12:
                intervals.append((start, end))

            if end == len(sequence):
                break

            start += WINDOW_STEP

    rows = []

    for start, end in intervals:
        purity, orientation = phase_purity(
            sequence[start:end],
            motif,
        )
        rows.append(
            {
                "start": start,
                "end": end,
                "purity": purity,
                "orientation": orientation,
            }
        )

    return rows


def resolve_contig(reference, chromosome):
    references = set(reference.references)
    candidates = [chromosome]

    if chromosome.startswith("chr"):
        candidates.append(chromosome[3:])
    else:
        candidates.append("chr" + chromosome)

    if chromosome in {"M", "MT", "chrM", "chrMT"}:
        candidates.extend(["chrM", "MT", "M"])

    for candidate in candidates:
        if candidate in references:
            return candidate

    raise KeyError(
        "No FASTA contig alias for {}".format(chromosome)
    )


inventory_rows = []
simple_ready_count = 0
selected_rows = []

with gzip.open(
    inventory_path,
    "rt",
    encoding="utf-8",
    newline="",
) as handle:
    reader = csv.DictReader(handle, delimiter="\t")

    for row in reader:
        inventory_rows.append(row)

        if (
            row["p3_route"]
            == "P3_SOFTCLIP_SIMPLE_PERIODIC_READY"
        ):
            simple_ready_count += 1

        if (
            row["p3_route"]
            == "P3_SOFTCLIP_SIMPLE_PERIODIC_READY"
            and int(row["assignment_rank"]) == 1
            and int(row["best_mapq"]) >= MINIMUM_MAPQ
            and int(row["target_facing_softclip_bp"])
                >= MINIMUM_SOFTCLIP
            and int(
                row["diagnostic_repeat_like_window_count"]
            ) > 0
        ):
            selected_rows.append(row)

if not selected_rows:
    raise RuntimeError(
        "No P3 bridge calibration candidates selected"
    )

required_read_ids = {
    row["read_id"]
    for row in selected_rows
}

fastq_records = {}
all_fastq_count = 0

with pysam.FastxFile(fastq_path) as source:
    for entry in source:
        all_fastq_count += 1

        if entry.name in required_read_ids:
            fastq_records[entry.name] = entry.sequence.upper()

missing_reads = required_read_ids - set(fastq_records)

reference = pysam.FastaFile(reference_fasta_path)

selected_fields = list(selected_rows[0].keys())
metadata_rows = []
query_records = []
reference_records = []
geometry_errors = 0

for row in selected_rows:
    projection_id = row["projection_id"]
    read_id = row["read_id"]
    sequence = fastq_records[read_id]

    raw_start = int(row["target_facing_raw_start"])
    raw_end = int(row["target_facing_raw_end"])
    raw_clip = sequence[raw_start:raw_end]

    side = row["target_facing_genomic_side"]
    strand = row["strand"]

    reverse_for_target_orientation = (
        (side == "GENOMIC_RIGHT" and strand == "-")
        or (side == "GENOMIC_LEFT" and strand == "+")
    )

    if reverse_for_target_orientation:
        oriented_clip = reverse_complement(raw_clip)
        orientation_transform = "REVERSE_COMPLEMENT"
    else:
        oriented_clip = raw_clip
        orientation_transform = "AS_RAW"

    resolved_contig = resolve_contig(
        reference,
        row["target_chrom"],
    )
    target_start = int(row["target_start"])
    target_end = int(row["target_end"])
    block_start = int(row["selected_block_start"])
    block_end = int(row["selected_block_end"])

    if side == "GENOMIC_RIGHT":
        bridge_start = block_end
        bridge_end = target_start
        target_entry_start = target_start
        target_entry_end = min(
            target_end,
            target_start + TARGET_ENTRY_BP,
        )

        if bridge_end < bridge_start:
            geometry_errors += 1
            continue

        reference_sequence = reference.fetch(
            resolved_contig,
            bridge_start,
            target_entry_end,
        ).upper()

    elif side == "GENOMIC_LEFT":
        bridge_start = target_end
        bridge_end = block_start
        target_entry_start = max(
            target_start,
            target_end - TARGET_ENTRY_BP,
        )
        target_entry_end = target_end

        if bridge_end < bridge_start:
            geometry_errors += 1
            continue

        reference_sequence = reverse_complement(
            reference.fetch(
                resolved_contig,
                target_entry_start,
                bridge_end,
            ).upper()
        )

    else:
        geometry_errors += 1
        continue

    bridge_bp = bridge_end - bridge_start
    target_entry_bp = (
        target_entry_end - target_entry_start
    )
    expected_reference_bp = (
        bridge_bp + target_entry_bp
    )
    query_bp = min(
        len(oriented_clip),
        expected_reference_bp,
    )
    query_sequence = oriented_clip[:query_bp]

    motifs = [
        motif
        for motif in row["canonical_motifs"].split(",")
        if motif and motif != "."
    ]

    if len(motifs) != 1:
        geometry_errors += 1
        continue

    motif = motifs[0]
    windows = diagnostic_windows(
        oriented_clip,
        motif,
    )
    repeat_like_windows = [
        window
        for window in windows
        if window["purity"] >= DIAGNOSTIC_PURITY
    ]
    target_relevant_windows = [
        window
        for window in repeat_like_windows
        if (
            window["end"] > bridge_bp
            and window["start"]
                < bridge_bp + target_entry_bp
        )
    ]

    best_window = max(
        windows,
        key=lambda window: (
            window["purity"],
            window["end"] - window["start"],
            -window["start"],
        ),
    ) if windows else {
        "start": ".",
        "end": ".",
        "purity": 0.0,
        "orientation": ".",
    }

    query_id = projection_id
    reference_id = projection_id + "__REF"

    query_records.append(
        (query_id, query_sequence)
    )
    reference_records.append(
        (reference_id, reference_sequence)
    )

    metadata_rows.append(
        {
            "model_id": model_id,
            "projection_id": projection_id,
            "query_id": query_id,
            "reference_id": reference_id,
            "read_id": read_id,
            "target_region_id": row["target_region_id"],
            "representative_locus_id": row[
                "representative_locus_id"
            ],
            "canonical_motif": motif,
            "motif_length_bp": len(motif),
            "assignment_rank": row["assignment_rank"],
            "best_mapq": row["best_mapq"],
            "strand": strand,
            "target_facing_genomic_side": side,
            "orientation_transform": orientation_transform,
            "raw_clip_start": raw_start,
            "raw_clip_end": raw_end,
            "raw_clip_bp": len(raw_clip),
            "oriented_clip_bp": len(oriented_clip),
            "query_bp": len(query_sequence),
            "reference_contig": resolved_contig,
            "selected_block_start": block_start,
            "selected_block_end": block_end,
            "target_start": target_start,
            "target_end": target_end,
            "bridge_bp": bridge_bp,
            "target_entry_bp": target_entry_bp,
            "expected_reference_bp": expected_reference_bp,
            "query_can_reach_target_entry": str(
                len(query_sequence) >= bridge_bp + 1
            ).lower(),
            "oriented_repeat_like_window_count": len(
                repeat_like_windows
            ),
            "oriented_target_relevant_window_count": len(
                target_relevant_windows
            ),
            "oriented_best_window_start": best_window[
                "start"
            ],
            "oriented_best_window_end": best_window[
                "end"
            ],
            "oriented_best_window_purity": (
                "{:.6f}".format(
                    best_window["purity"]
                )
            ),
            "oriented_best_window_orientation": best_window[
                "orientation"
            ],
        }
    )

reference.close()

if geometry_errors:
    raise RuntimeError(
        "P3 bridge pair geometry errors: {}".format(
            geometry_errors
        )
    )

if len(metadata_rows) != len(selected_rows):
    raise RuntimeError(
        "Selected/pair count mismatch: {} vs {}".format(
            len(selected_rows),
            len(metadata_rows),
        )
    )

with gzip.open(
    selected_path,
    "wt",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=selected_fields,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(selected_rows)

metadata_fields = list(metadata_rows[0].keys())

with gzip.open(
    metadata_path,
    "wt",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=metadata_fields,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(metadata_rows)

for path, records in [
    (query_fasta_path, query_records),
    (reference_pair_fasta_path, reference_records),
]:
    with open(
        path,
        "w",
        encoding="utf-8",
    ) as handle:
        for sequence_id, sequence in records:
            handle.write(
                ">{}\n{}\n".format(
                    sequence_id,
                    sequence,
                )
            )

for path, records in [
    (query_fasta_gz_path, query_records),
    (
        reference_pair_fasta_gz_path,
        reference_records,
    ),
]:
    with gzip.open(
        path,
        "wt",
        encoding="utf-8",
    ) as handle:
        for sequence_id, sequence in records:
            handle.write(
                ">{}\n{}\n".format(
                    sequence_id,
                    sequence,
                )
            )

prepare_status = "PASS"

if (
    len(inventory_rows) != EXPECTED_INVENTORY
    or simple_ready_count != EXPECTED_SIMPLE_READY
    or all_fastq_count != EXPECTED_FASTQ
    or missing_reads
    or len(metadata_rows) != len(selected_rows)
):
    prepare_status = "REVIEW"

with open(
    metadata_path + ".prepare_qc.tsv",
    "w",
    encoding="utf-8",
) as handle:
    handle.write("metric\tvalue\n")
    handle.write(
        "inventory_rows\t{}\n".format(
            len(inventory_rows)
        )
    )
    handle.write(
        "simple_ready_rows\t{}\n".format(
            simple_ready_count
        )
    )
    handle.write(
        "selected_calibration_rows\t{}\n".format(
            len(selected_rows)
        )
    )
    handle.write(
        "selected_unique_reads\t{}\n".format(
            len(required_read_ids)
        )
    )
    handle.write(
        "candidate_fastq_reads\t{}\n".format(
            all_fastq_count
        )
    )
    handle.write(
        "missing_selected_reads\t{}\n".format(
            len(missing_reads)
        )
    )
    handle.write(
        "pair_metadata_rows\t{}\n".format(
            len(metadata_rows)
        )
    )
    handle.write(
        "geometry_errors\t{}\n".format(
            geometry_errors
        )
    )
    handle.write(
        "prepare_status\t{}\n".format(
            prepare_status
        )
    )

if prepare_status != "PASS":
    raise SystemExit(
        "P3 bridge pair preparation requires review"
    )
PY

cat > "$PARSE_PY" <<'PY'
from __future__ import annotations

import csv
import gzip
import sys
from collections import Counter, defaultdict

(
    metadata_path,
    paf_path,
    audit_path,
    summary_path,
    qc_path,
    model_id,
    minimum_target_entry_text,
    boundary_tolerance_text,
    minimum_identity_text,
    minimum_query_coverage_text,
) = sys.argv[1:]

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

self_alignments = defaultdict(list)
all_paf_rows = 0

with open(
    paf_path,
    "r",
    encoding="utf-8",
) as handle:
    for line in handle:
        line = line.rstrip("\n")

        if not line:
            continue

        all_paf_rows += 1
        fields = line.split("\t")
        query_id = fields[0]
        reference_id = fields[5]

        if (
            query_id not in metadata
            or reference_id
               != metadata[query_id]["reference_id"]
        ):
            continue

        tags = parse_tags(fields[12:])
        query_length = int(fields[1])
        query_start = int(fields[2])
        query_end = int(fields[3])
        reference_start = int(fields[7])
        reference_end = int(fields[8])
        matches = int(fields[9])
        block_length = int(fields[10])

        self_alignments[query_id].append(
            {
                "query_length": query_length,
                "query_start": query_start,
                "query_end": query_end,
                "reference_start": reference_start,
                "reference_end": reference_end,
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
                "alignment_type": tags.get("tp", "."),
            }
        )

audit_rows = []
counts = Counter()

for projection_id in sorted(metadata):
    meta = metadata[projection_id]
    rows = self_alignments.get(
        projection_id,
        [],
    )

    rows.sort(
        key=lambda row: (
            row["alignment_score"],
            row["query_coverage"],
            row["identity"],
        ),
        reverse=True,
    )

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
        status = "QUERY_TOO_SHORT_TO_REACH_TARGET"
        best = None

    elif not rows:
        status = "NO_CANDIDATE_SPECIFIC_ALIGNMENT"
        best = None

    else:
        best = rows[0]
        boundary_connected = (
            best["query_start"]
            <= BOUNDARY_TOLERANCE
            and best["reference_start"]
                <= BOUNDARY_TOLERANCE
        )
        quality_pass = (
            best["identity"] >= MINIMUM_IDENTITY
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
            status = "LOW_QUALITY_BRIDGE_ALIGNMENT"
        elif not reaches_target:
            status = "BRIDGE_STOPS_BEFORE_TARGET_ENTRY"
        else:
            status = "BRIDGE_REACHES_TARGET_ENTRY"

    if (
        status == "BRIDGE_REACHES_TARGET_ENTRY"
        and motif_signal
    ):
        combined = "BRIDGE_PLUS_TARGET_MOTIF_SIGNAL"
    elif status == "BRIDGE_REACHES_TARGET_ENTRY":
        combined = "BRIDGE_ONLY_NO_TARGET_MOTIF_SIGNAL"
    elif motif_signal:
        combined = "TARGET_MOTIF_SIGNAL_WITHOUT_BRIDGE"
    else:
        combined = "NO_BRIDGE_NO_TARGET_MOTIF_SIGNAL"

    counts["bridge_status::{}".format(status)] += 1
    counts["combined_status::{}".format(combined)] += 1

    audit_rows.append(
        {
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
            "target_facing_genomic_side": meta[
                "target_facing_genomic_side"
            ],
            "orientation_transform": meta[
                "orientation_transform"
            ],
            "raw_clip_bp": meta["raw_clip_bp"],
            "query_bp": meta["query_bp"],
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
            "self_alignment_count": len(rows),
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
            "best_alignment_type": (
                best["alignment_type"]
                if best
                else "."
            ),
            "bridge_status": status,
            "combined_bridge_motif_status": combined,
            "evidence_status": "NOT_CALLED",
            "allele_length_status": "NOT_ASSESSED",
            "expansion_status": "NOT_ASSESSED",
        }
    )

audit_fields = list(audit_rows[0].keys())

with gzip.open(
    audit_path,
    "wt",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=audit_fields,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(audit_rows)

summary_groups = defaultdict(
    lambda: {
        "rows": 0,
        "reads": set(),
        "targets": set(),
        "clip_lengths": [],
        "bridge_lengths": [],
        "purities": [],
    }
)

for row in audit_rows:
    group_names = [
        "ALL",
        "bridge_status::{}".format(
            row["bridge_status"]
        ),
        "combined_status::{}".format(
            row["combined_bridge_motif_status"]
        ),
    ]

    for group_name in group_names:
        group = summary_groups[group_name]
        group["rows"] += 1
        group["reads"].add(row["read_id"])
        group["targets"].add(
            row["target_region_id"]
        )
        group["clip_lengths"].append(
            int(row["raw_clip_bp"])
        )
        group["bridge_lengths"].append(
            int(row["bridge_bp"])
        )
        group["purities"].append(
            float(
                row["oriented_best_window_purity"]
            )
        )

summary_fields = [
    "group",
    "rows",
    "unique_reads",
    "unique_targets",
    "softclip_bp_median",
    "bridge_bp_median",
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

        def median(values):
            ordered = sorted(values)
            size = len(ordered)

            if size % 2:
                return float(ordered[size // 2])

            return (
                ordered[size // 2 - 1]
                + ordered[size // 2]
            ) / 2.0

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
                "softclip_bp_median": (
                    "{:.6f}".format(
                        median(
                            group["clip_lengths"]
                        )
                    )
                ),
                "bridge_bp_median": (
                    "{:.6f}".format(
                        median(
                            group["bridge_lengths"]
                        )
                    )
                ),
                "best_window_purity_median": (
                    "{:.6f}".format(
                        median(
                            group["purities"]
                        )
                    )
                ),
            }
        )

status = "PASS"

if (
    len(audit_rows) != len(metadata)
    or not audit_rows
):
    status = "REVIEW"

with open(
    qc_path,
    "w",
    encoding="utf-8",
) as handle:
    handle.write("metric\tvalue\n")
    handle.write(
        "pair_metadata_rows\t{}\n".format(
            len(metadata)
        )
    )
    handle.write(
        "all_paf_rows\t{}\n".format(
            all_paf_rows
        )
    )
    handle.write(
        "queries_with_self_alignment\t{}\n".format(
            len(self_alignments)
        )
    )
    handle.write(
        "audit_rows_written\t{}\n".format(
            len(audit_rows)
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

if status != "PASS":
    raise SystemExit(
        "P3 bridge feasibility audit requires review"
    )
PY

echo "===== SHELL AND EMBEDDED PYTHON SYNTAX ====="
python -m py_compile "$PREPARE_PY"
python -m py_compile "$PARSE_PY"
echo "Embedded Python syntax: OK"

rm -f \
  "$SELECTED" \
  "$PAIR_META" \
  "${PAIR_META}.prepare_qc.tsv" \
  "$QUERY_FASTA" \
  "$REFERENCE_PAIR_FASTA" \
  "$QUERY_FASTA_GZ" \
  "$REFERENCE_PAIR_FASTA_GZ" \
  "$PAF" \
  "$AUDIT" \
  "$SUMMARY" \
  "$QC" \
  "$MANIFEST"

echo
echo "===== PREPARE P3 CANDIDATE-SPECIFIC BRIDGE PAIRS ====="

python "$PREPARE_PY" \
  "$INVENTORY" \
  "$FASTQ" \
  "$REFERENCE_FASTA" \
  "$SELECTED" \
  "$PAIR_META" \
  "$QUERY_FASTA" \
  "$REFERENCE_PAIR_FASTA" \
  "$QUERY_FASTA_GZ" \
  "$REFERENCE_PAIR_FASTA_GZ" \
  "$MODEL_ID" \
  "$EXPECTED_INVENTORY_ROWS" \
  "$EXPECTED_SIMPLE_READY_ROWS" \
  "$EXPECTED_FASTQ_READS" \
  "$MIN_MAPQ" \
  "$MIN_SOFTCLIP_BP" \
  "$TARGET_ENTRY_BP" \
  "$DIAGNOSTIC_WINDOW_BP" \
  "$DIAGNOSTIC_WINDOW_STEP_BP" \
  "$DIAGNOSTIC_PURITY"

gzip -t "$SELECTED"
gzip -t "$PAIR_META"
gzip -t "$QUERY_FASTA_GZ"
gzip -t "$REFERENCE_PAIR_FASTA_GZ"

echo
echo "===== PREPARATION QC ====="
column -ts $'\t' "${PAIR_META}.prepare_qc.tsv"

echo
echo "===== MAP QUERIES TO CANDIDATE-SPECIFIC REFERENCES ====="

minimap2 \
  -x map-ont \
  -k7 \
  -w3 \
  -m10 \
  -s10 \
  -p0.50 \
  -N100 \
  -f0 \
  -c \
  --secondary=yes \
  -t4 \
  "$REFERENCE_PAIR_FASTA" \
  "$QUERY_FASTA" \
  > "$PAF"

echo
echo "===== PARSE SELF-PAIR BRIDGE ALIGNMENTS ====="

python "$PARSE_PY" \
  "$PAIR_META" \
  "$PAF" \
  "$AUDIT" \
  "$SUMMARY" \
  "$QC" \
  "$MODEL_ID" \
  "$MIN_TARGET_ENTRY_SUPPORT_BP" \
  "$BOUNDARY_TOLERANCE_BP" \
  "$MIN_ALIGNMENT_IDENTITY" \
  "$MIN_ALIGNMENT_QUERY_COVERAGE"

gzip -t "$AUDIT"

echo
echo "===== P3 BRIDGE FEASIBILITY QC ====="
column -ts $'\t' "$QC"

echo
echo "===== P3 BRIDGE FEASIBILITY SUMMARY ====="
column -ts $'\t' "$SUMMARY"

echo
echo "===== FIRST 30 BRIDGE+MOTIF ROWS ====="
gzip -cd "$AUDIT" \
  | awk -F '\t' '
      NR == 1 {
          for (i = 1; i <= NF; i++) {
              if ($i == "combined_bridge_motif_status") {
                  column = i
              }
          }
          print
          next
      }
      $column == "BRIDGE_PLUS_TARGET_MOTIF_SIGNAL" {
          print
          count++
          if (count >= 30) {
              exit
          }
      }
  ' \
  | column -ts $'\t'

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in \
      "$SELECTED" \
      "$PAIR_META" \
      "$AUDIT"
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
      "${PAIR_META}.prepare_qc.tsv" \
      "$PAF" \
      "$SUMMARY" \
      "$QC" \
      "$PARAMETERS"
    do
        if [[ "$path" == *.paf ]]; then
            rows="$(awk 'END {print NR}' "$path")"
        else
            rows="$(awk 'END {print NR-1}' "$path")"
        fi

        printf '%s\t%s\t%s\t%s\t%s\n' \
          "$(basename "$path")" \
          "$rows" \
          "$(stat -c '%s' "$path")" \
          "$(sha256sum "$path" | awk '{print $1}')" \
          "$path"
    done

    for path in \
      "$QUERY_FASTA_GZ" \
      "$REFERENCE_PAIR_FASTA_GZ"
    do
        rows="$(gzip -cd "$path" | grep -c '^>')"

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
echo "$SELECTED"
echo "$PAIR_META"
echo "$PAF"
echo "$AUDIT"
echo "$SUMMARY"
echo "$QC"
