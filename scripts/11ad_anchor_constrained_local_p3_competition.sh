#!/usr/bin/env bash
set -euo pipefail

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
fi

conda activate rnatr-v03
source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"
MODEL_ID="rnatr_p3_anchor_constrained_local_competition_v0.3.1"

INVENTORY="$PROJECT_ROOT/results/11_p3_inventory/$RUN_ID/p3_proximal_inventory.tsv.gz"
ISOLATED="$PROJECT_ROOT/results/11_p3_isolated_pair_validation/$RUN_ID/p3_isolated_pair_validation.tsv.gz"
SPECIFICITY="$PROJECT_ROOT/results/11_p3_bridge_specificity/$RUN_ID/p3_bridge_sequence_specificity.tsv"
FASTQ="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_candidates_v0.3.1/ENCFF260PGB.pilot_100k.rnatr_candidate_all.fastq.gz"
REFERENCE_FASTA="$PROJECT_ROOT/refs/gencode_v50/GRCh38.primary_assembly.genome.fa"

OUTDIR="$PROJECT_ROOT/results/11_p3_anchor_constrained/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_p3_anchor_constrained/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_p3_anchor_constrained/$RUN_ID"

OUTPUT="$OUTDIR/p3_anchor_constrained_local_competition.tsv"
LOCAL_TARGETS="$OUTDIR/p3_anchor_local_target_sets.tsv.gz"
SUMMARY="$OUTDIR/p3_anchor_constrained_local_competition_summary.tsv"
QC="$QCDIR/p3_anchor_constrained_local_competition.qc.tsv"
PARAMETERS="$OUTDIR/${MODEL_ID}.parameters.tsv"
MANIFEST="$OUTDIR/${RUN_ID}.p3_anchor_constrained.manifest.tsv"
PY="$WORKDIR/run_anchor_constrained_local_competition.py"

EXPECTED_INVENTORY_ROWS=211939
EXPECTED_POSITIVES=23
EXPECTED_FASTQ_READS=79176

WORKERS=8
PROGRESS_EVERY=5
TARGET_ENTRY_BP=60
MIN_TARGET_ENTRY_SUPPORT_BP=12
BOUNDARY_TOLERANCE_BP=10
MIN_ALIGNMENT_IDENTITY=0.70
MIN_EFFECTIVE_COVERAGE=0.70
NEAR_BEST_SCORE_FRACTION=0.95

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR"

for path in \
  "$INVENTORY" \
  "$ISOLATED" \
  "$SPECIFICITY" \
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
model_id	$MODEL_ID	Anchor-constrained local target competition for P3 bridges
positive_definition	isolated_combined_status=BRIDGE_PLUS_TARGET_MOTIF_SIGNAL	23 isolated bridge-positive candidates
local_anchor_key	read_id+selected_block_start+selected_block_end+target_facing_genomic_side+strand+raw_softclip_interval	Only targets reachable from the same mapped anchor compete
target_entry_bp	$TARGET_ENTRY_BP	Reference target-entry bases
minimum_target_entry_support_bp	$MIN_TARGET_ENTRY_SUPPORT_BP	Required reference support inside target
boundary_tolerance_bp	$BOUNDARY_TOLERANCE_BP	Query/reference alignment must begin near mapped-block boundary
minimum_alignment_identity	$MIN_ALIGNMENT_IDENTITY	Provisional ONT compatibility threshold
minimum_effective_coverage	$MIN_EFFECTIVE_COVERAGE	Aligned query span divided by min(query length, reference length)
near_best_score_fraction	$NEAR_BEST_SCORE_FRACTION	Local reference groups within 95% of best valid-bridge score
anchor_semantics	original_high_MAPQ_mapping_localizes_region	Bridge sequence is not required to be genome-wide unique
competition_semantics	only_same_anchor_nearby_targets_compete	Genome-wide decoys are diagnostic, not a rejection gate
call_semantics	local_target_adjudication_only	No repeat length, allele length, or expansion call
EOF

cat > "$PY" <<'PY'
from __future__ import annotations

import csv
import gzip
import hashlib
import os
import subprocess
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import pysam

(
    inventory_path,
    isolated_path,
    specificity_path,
    fastq_path,
    reference_fasta_path,
    output_path,
    local_targets_path,
    summary_path,
    qc_path,
    workdir,
    model_id,
    expected_inventory_text,
    expected_positives_text,
    expected_fastq_text,
    workers_text,
    progress_every_text,
    target_entry_text,
    minimum_target_entry_text,
    boundary_tolerance_text,
    minimum_identity_text,
    minimum_effective_coverage_text,
    near_best_fraction_text,
) = sys.argv[1:]

EXPECTED_INVENTORY = int(expected_inventory_text)
EXPECTED_POSITIVES = int(expected_positives_text)
EXPECTED_FASTQ = int(expected_fastq_text)

WORKERS = int(workers_text)
PROGRESS_EVERY = int(progress_every_text)
TARGET_ENTRY_BP = int(target_entry_text)
MINIMUM_TARGET_ENTRY = int(minimum_target_entry_text)
BOUNDARY_TOLERANCE = int(boundary_tolerance_text)
MINIMUM_IDENTITY = float(minimum_identity_text)
MINIMUM_EFFECTIVE_COVERAGE = float(
    minimum_effective_coverage_text
)
NEAR_BEST_FRACTION = float(near_best_fraction_text)

COMPLEMENT = str.maketrans("ACGT", "TGCA")


def reverse_complement(sequence):
    return sequence.translate(COMPLEMENT)[::-1]


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


def anchor_key(row):
    return (
        row["read_id"],
        row["selected_block_start"],
        row["selected_block_end"],
        row["target_facing_genomic_side"],
        row["strand"],
        row["target_facing_raw_start"],
        row["target_facing_raw_end"],
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
        reference_length = int(fields[6])
        reference_start = int(fields[7])
        reference_end = int(fields[8])
        matches = int(fields[9])
        block_length = int(fields[10])

        effective_denominator = min(
            query_length,
            reference_length,
        )
        effective_coverage = (
            (query_end - query_start)
            / effective_denominator
            if effective_denominator
            else 0.0
        )

        rows.append(
            {
                "reference_id": fields[5],
                "query_length": query_length,
                "query_start": query_start,
                "query_end": query_end,
                "reference_length": reference_length,
                "reference_start": reference_start,
                "reference_end": reference_end,
                "identity": (
                    matches / block_length
                    if block_length
                    else 0.0
                ),
                "effective_coverage": effective_coverage,
                "mapq": int(fields[11]),
                "alignment_score": tags.get(
                    "AS",
                    matches,
                ),
            }
        )

    return rows


with gzip.open(
    inventory_path,
    "rt",
    encoding="utf-8",
    newline="",
) as handle:
    inventory_rows = list(
        csv.DictReader(handle, delimiter="\t")
    )

inventory_lookup = {
    row["projection_id"]: row
    for row in inventory_rows
}

inventory_by_anchor = defaultdict(list)

for row in inventory_rows:
    if (
        row["target_facing_raw_start"] == "."
        or row["target_facing_raw_end"] == "."
    ):
        continue

    if int(row["target_facing_softclip_bp"]) <= 0:
        continue

    inventory_by_anchor[anchor_key(row)].append(row)

with gzip.open(
    isolated_path,
    "rt",
    encoding="utf-8",
    newline="",
) as handle:
    isolated_rows = list(
        csv.DictReader(handle, delimiter="\t")
    )

positive_rows = [
    row
    for row in isolated_rows
    if row["isolated_combined_status"]
       == "BRIDGE_PLUS_TARGET_MOTIF_SIGNAL"
]

with open(
    specificity_path,
    "r",
    encoding="utf-8",
    newline="",
) as handle:
    specificity_lookup = {
        row["projection_id"]: row
        for row in csv.DictReader(
            handle,
            delimiter="\t",
        )
    }

required_read_ids = {
    row["read_id"]
    for row in positive_rows
}

fastq_records = {}
fastq_count = 0

with pysam.FastxFile(fastq_path) as source:
    for entry in source:
        fastq_count += 1

        if entry.name in required_read_ids:
            fastq_records[entry.name] = (
                entry.sequence.upper()
            )

missing_reads = required_read_ids - set(fastq_records)

reference = pysam.FastaFile(reference_fasta_path)

local_sets = {}
local_target_rows = []
geometry_errors = 0

for positive in positive_rows:
    projection_id = positive["projection_id"]
    expected = inventory_lookup[projection_id]
    key = anchor_key(expected)
    candidates = inventory_by_anchor.get(key, [])

    if not candidates:
        geometry_errors += 1
        continue

    read_sequence = fastq_records[expected["read_id"]]
    raw_start = int(expected["target_facing_raw_start"])
    raw_end = int(expected["target_facing_raw_end"])
    raw_clip = read_sequence[raw_start:raw_end]

    side = expected["target_facing_genomic_side"]
    strand = expected["strand"]

    reverse_query = (
        (side == "GENOMIC_RIGHT" and strand == "-")
        or (side == "GENOMIC_LEFT" and strand == "+")
    )

    oriented_clip = (
        reverse_complement(raw_clip)
        if reverse_query
        else raw_clip
    )

    reference_records = []
    reference_metadata = {}

    for candidate in candidates:
        candidate_id = candidate["projection_id"]
        target_start = int(candidate["target_start"])
        target_end = int(candidate["target_end"])
        block_start = int(candidate["selected_block_start"])
        block_end = int(candidate["selected_block_end"])

        resolved_contig = resolve_contig(
            reference,
            candidate["target_chrom"],
        )

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

            ref_sequence = reference.fetch(
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

            ref_sequence = reverse_complement(
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
        digest = hashlib.sha256(
            ref_sequence.encode()
        ).hexdigest()
        reference_id = candidate_id + "__LOCALREF"

        reference_records.append(
            (
                reference_id,
                ref_sequence,
            )
        )
        reference_metadata[reference_id] = {
            "projection_id": candidate_id,
            "target_region_id": candidate["target_region_id"],
            "canonical_motifs": candidate[
                "canonical_motifs"
            ],
            "bridge_bp": bridge_bp,
            "target_entry_bp": target_entry_bp,
            "required_reference_end": (
                bridge_bp
                + min(
                    target_entry_bp,
                    MINIMUM_TARGET_ENTRY,
                )
            ),
            "reference_sha256": digest,
        }

        local_target_rows.append(
            {
                "positive_projection_id": projection_id,
                "anchor_read_id": expected["read_id"],
                "local_candidate_projection_id": candidate_id,
                "is_expected_candidate": str(
                    candidate_id == projection_id
                ).lower(),
                "target_region_id": candidate[
                    "target_region_id"
                ],
                "canonical_motifs": candidate[
                    "canonical_motifs"
                ],
                "bridge_bp": bridge_bp,
                "target_entry_bp": target_entry_bp,
                "reference_bp": len(ref_sequence),
                "reference_sha256": digest,
            }
        )

    local_sets[projection_id] = {
        "expected": expected,
        "query_sequence": oriented_clip,
        "reference_records": reference_records,
        "reference_metadata": reference_metadata,
    }

reference.close()

progress_lock = threading.Lock()
progress = {
    "completed": 0,
    "start": time.time(),
}


def run_local_set(projection_id):
    local = local_sets[projection_id]
    expected = local["expected"]
    query_sequence = local["query_sequence"]
    reference_records = local["reference_records"]
    reference_metadata = local[
        "reference_metadata"
    ]

    safe_id = "".join(
        character
        if character.isalnum()
        else "_"
        for character in projection_id
    )
    pair_dir = os.path.join(
        workdir,
        "local_" + safe_id,
    )
    os.makedirs(pair_dir, exist_ok=True)

    query_path = os.path.join(
        pair_dir,
        "query.fa",
    )
    reference_path = os.path.join(
        pair_dir,
        "references.fa",
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
        for reference_id, sequence in reference_records:
            handle.write(
                ">{}\n{}\n".format(
                    reference_id,
                    sequence,
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
        "-N100",
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
            "minimap2 failed for {}".format(
                projection_id
            )
        )

    alignments = parse_paf(completed.stdout)

    try:
        os.remove(query_path)
        os.remove(reference_path)
        os.rmdir(pair_dir)
    except OSError:
        pass

    digest_best = {}
    digest_targets = defaultdict(set)

    for alignment in alignments:
        metadata = reference_metadata.get(
            alignment["reference_id"]
        )

        if metadata is None:
            continue

        boundary_connected = (
            alignment["query_start"]
            <= BOUNDARY_TOLERANCE
            and alignment["reference_start"]
                <= BOUNDARY_TOLERANCE
        )
        quality_pass = (
            alignment["identity"]
            >= MINIMUM_IDENTITY
            and alignment[
                "effective_coverage"
            ] >= MINIMUM_EFFECTIVE_COVERAGE
        )
        reaches_target = (
            alignment["reference_end"]
            >= metadata[
                "required_reference_end"
            ]
        )
        valid_bridge = (
            boundary_connected
            and quality_pass
            and reaches_target
        )

        if not valid_bridge:
            continue

        digest = metadata[
            "reference_sha256"
        ]
        digest_targets[digest].add(
            metadata["projection_id"]
        )

        current = digest_best.get(digest)
        rank = (
            alignment["alignment_score"],
            alignment["effective_coverage"],
            alignment["identity"],
        )

        if current is None:
            digest_best[digest] = alignment
        else:
            current_rank = (
                current["alignment_score"],
                current["effective_coverage"],
                current["identity"],
            )

            if rank > current_rank:
                digest_best[digest] = alignment

    expected_reference_id = (
        projection_id + "__LOCALREF"
    )
    expected_meta = reference_metadata[
        expected_reference_id
    ]
    expected_digest = expected_meta[
        "reference_sha256"
    ]

    ranked_digests = sorted(
        digest_best,
        key=lambda digest: (
            digest_best[digest][
                "alignment_score"
            ],
            digest_best[digest][
                "effective_coverage"
            ],
            digest_best[digest]["identity"],
        ),
        reverse=True,
    )

    best_digest = (
        ranked_digests[0]
        if ranked_digests
        else None
    )
    best_score = (
        digest_best[best_digest][
            "alignment_score"
        ]
        if best_digest
        else None
    )
    expected_alignment = digest_best.get(
        expected_digest
    )
    expected_score = (
        expected_alignment[
            "alignment_score"
        ]
        if expected_alignment
        else None
    )

    near_best_digests = []

    if best_score is not None:
        near_best_digests = [
            digest
            for digest in ranked_digests
            if digest_best[digest][
                "alignment_score"
            ] >= best_score * NEAR_BEST_FRACTION
        ]

    tied_best = (
        sum(
            digest_best[digest][
                "alignment_score"
            ] == best_score
            for digest in ranked_digests
        )
        if best_score is not None
        else 0
    )

    expected_rank = (
        ranked_digests.index(
            expected_digest
        ) + 1
        if expected_digest in ranked_digests
        else None
    )

    if expected_alignment is None:
        local_status = (
            "EXPECTED_TARGET_HAS_NO_VALID_LOCAL_BRIDGE"
        )

    elif expected_score == best_score:
        if tied_best == 1:
            local_status = (
                "EXPECTED_TARGET_UNIQUE_BEST_LOCAL_BRIDGE"
            )
        else:
            local_status = (
                "EXPECTED_TARGET_TIED_BEST_LOCAL_BRIDGE"
            )

    elif (
        best_score is not None
        and expected_score
            >= best_score * NEAR_BEST_FRACTION
    ):
        local_status = (
            "EXPECTED_TARGET_NEAR_BEST_LOCAL_BRIDGE"
        )

    else:
        local_status = (
            "ALTERNATIVE_LOCAL_TARGET_OUTSCORES_EXPECTED"
        )

    if local_status == (
        "EXPECTED_TARGET_UNIQUE_BEST_LOCAL_BRIDGE"
    ):
        interpretation = (
            "ANCHOR_AND_BRIDGE_DISCRIMINATE_EXPECTED_LOCAL_TARGET"
        )
    elif local_status in {
        "EXPECTED_TARGET_TIED_BEST_LOCAL_BRIDGE",
        "EXPECTED_TARGET_NEAR_BEST_LOCAL_BRIDGE",
    }:
        interpretation = (
            "ANCHOR_LOCALIZES_REGION_BUT_TARGET_REMAINS_LOCALLY_AMBIGUOUS"
        )
    elif local_status == (
        "ALTERNATIVE_LOCAL_TARGET_OUTSCORES_EXPECTED"
    ):
        interpretation = (
            "ANCHOR_LOCALIZES_REGION_BUT_ANOTHER_LOCAL_TARGET_IS_BETTER"
        )
    else:
        interpretation = (
            "ISOLATED_BRIDGE_NOT_REPRODUCED_UNDER_LOCAL_COMPETITION"
        )

    specificity = specificity_lookup.get(
        projection_id,
        {},
    )

    result = {
        "model_id": model_id,
        "projection_id": projection_id,
        "read_id": expected["read_id"],
        "expected_target_region_id": expected[
            "target_region_id"
        ],
        "canonical_motifs": expected[
            "canonical_motifs"
        ],
        "anchor_mapq": expected["best_mapq"],
        "selected_block_start": expected[
            "selected_block_start"
        ],
        "selected_block_end": expected[
            "selected_block_end"
        ],
        "target_facing_genomic_side": expected[
            "target_facing_genomic_side"
        ],
        "raw_softclip_bp": expected[
            "target_facing_softclip_bp"
        ],
        "local_candidate_rows": len(
            reference_records
        ),
        "local_unique_reference_groups": len(
            {
                metadata[
                    "reference_sha256"
                ]
                for metadata in reference_metadata.values()
            }
        ),
        "valid_local_bridge_groups": len(
            ranked_digests
        ),
        "expected_reference_group_observed": str(
            expected_alignment
            is not None
        ).lower(),
        "expected_local_rank": (
            expected_rank
            if expected_rank is not None
            else "."
        ),
        "expected_alignment_score": (
            expected_score
            if expected_score is not None
            else "."
        ),
        "best_local_reference_sha256": (
            best_digest
            if best_digest
            else "."
        ),
        "best_local_alignment_score": (
            best_score
            if best_score is not None
            else "."
        ),
        "near_best_local_reference_groups": len(
            near_best_digests
        ),
        "tied_best_local_reference_groups": (
            tied_best
        ),
        "expected_equivalent_local_target_count": len(
            digest_targets.get(
                expected_digest,
                set(),
            )
        ),
        "local_competition_status": (
            local_status
        ),
        "anchor_aware_interpretation": (
            interpretation
        ),
        "global_candidate_set_interpretation": (
            specificity.get(
                "bridge_specificity_interpretation",
                ".",
            )
        ),
        "provisional_p3_status": (
            "ANCHOR_CONSTRAINED_BRIDGE_CANDIDATE"
        ),
        "repeat_length_status": "NOT_ASSESSED",
        "allele_length_status": "NOT_ASSESSED",
        "expansion_status": "NOT_ASSESSED",
    }

    with progress_lock:
        progress["completed"] += 1
        completed_count = progress[
            "completed"
        ]

        if (
            completed_count % PROGRESS_EVERY == 0
            or completed_count == len(local_sets)
        ):
            elapsed = (
                time.time() - progress["start"]
            )
            rate = (
                completed_count / elapsed
                if elapsed
                else 0.0
            )
            remaining = (
                (len(local_sets) - completed_count)
                / rate
                if rate
                else 0.0
            )
            print(
                "[INFO] local anchor sets {}/{}; "
                "{:.1f}/s; ETA {:.1f} min".format(
                    completed_count,
                    len(local_sets),
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
            run_local_set,
            projection_id,
        ): projection_id
        for projection_id in sorted(local_sets)
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
        "No local-competition results generated"
    )

output_fields = list(results[0].keys())

with open(
    output_path,
    "w",
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

local_target_fields = list(
    local_target_rows[0].keys()
)

with gzip.open(
    local_targets_path,
    "wt",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=local_target_fields,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(local_target_rows)

counts = Counter()
summary_groups = defaultdict(
    lambda: {
        "rows": 0,
        "reads": set(),
        "targets": set(),
        "candidate_counts": [],
        "reference_group_counts": [],
        "near_best_counts": [],
    }
)

for row in results:
    counts[
        "local_status::{}".format(
            row["local_competition_status"]
        )
    ] += 1
    counts[
        "interpretation::{}".format(
            row["anchor_aware_interpretation"]
        )
    ] += 1

    group_names = [
        "ALL",
        "local_status::{}".format(
            row["local_competition_status"]
        ),
        "interpretation::{}".format(
            row["anchor_aware_interpretation"]
        ),
    ]

    for group_name in group_names:
        group = summary_groups[group_name]
        group["rows"] += 1
        group["reads"].add(row["read_id"])
        group["targets"].add(
            row["expected_target_region_id"]
        )
        group["candidate_counts"].append(
            int(row["local_candidate_rows"])
        )
        group["reference_group_counts"].append(
            int(
                row[
                    "local_unique_reference_groups"
                ]
            )
        )
        group["near_best_counts"].append(
            int(
                row[
                    "near_best_local_reference_groups"
                ]
            )
        )


def median(values):
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
    "unique_expected_targets",
    "local_candidate_rows_median",
    "local_reference_groups_median",
    "near_best_local_groups_median",
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

        writer.writerow(
            {
                "group": group_name,
                "rows": group["rows"],
                "unique_reads": len(
                    group["reads"]
                ),
                "unique_expected_targets": len(
                    group["targets"]
                ),
                "local_candidate_rows_median": (
                    "{:.6f}".format(
                        median(
                            group[
                                "candidate_counts"
                            ]
                        )
                    )
                ),
                "local_reference_groups_median": (
                    "{:.6f}".format(
                        median(
                            group[
                                "reference_group_counts"
                            ]
                        )
                    )
                ),
                "near_best_local_groups_median": (
                    "{:.6f}".format(
                        median(
                            group[
                                "near_best_counts"
                            ]
                        )
                    )
                ),
            }
        )

status = "PASS"

if (
    len(inventory_rows) != EXPECTED_INVENTORY
    or len(positive_rows) != EXPECTED_POSITIVES
    or fastq_count != EXPECTED_FASTQ
    or missing_reads
    or geometry_errors
    or failures
    or len(results) != EXPECTED_POSITIVES
):
    status = "REVIEW"

with open(
    qc_path,
    "w",
    encoding="utf-8",
) as handle:
    handle.write("metric\tvalue\n")
    handle.write(
        "expected_inventory_rows\t{}\n".format(
            EXPECTED_INVENTORY
        )
    )
    handle.write(
        "observed_inventory_rows\t{}\n".format(
            len(inventory_rows)
        )
    )
    handle.write(
        "expected_positive_pairs\t{}\n".format(
            EXPECTED_POSITIVES
        )
    )
    handle.write(
        "observed_positive_pairs\t{}\n".format(
            len(positive_rows)
        )
    )
    handle.write(
        "candidate_fastq_reads\t{}\n".format(
            fastq_count
        )
    )
    handle.write(
        "missing_positive_reads\t{}\n".format(
            len(missing_reads)
        )
    )
    handle.write(
        "anchor_local_sets\t{}\n".format(
            len(local_sets)
        )
    )
    handle.write(
        "local_target_rows\t{}\n".format(
            len(local_target_rows)
        )
    )
    handle.write(
        "geometry_errors\t{}\n".format(
            geometry_errors
        )
    )
    handle.write(
        "local_alignment_failures\t{}\n".format(
            len(failures)
        )
    )
    handle.write(
        "results_written\t{}\n".format(
            len(results)
        )
    )

    for key, count in sorted(counts.items()):
        handle.write(
            "{}\t{}\n".format(key, count)
        )

    handle.write("repeat_length_calls_emitted\t0\n")
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
        "Anchor-constrained local competition requires review"
    )
PY

echo "===== SHELL AND EMBEDDED PYTHON SYNTAX ====="
python -m py_compile "$PY"
echo "Embedded Python syntax: OK"

rm -f \
  "$OUTPUT" \
  "$LOCAL_TARGETS" \
  "$SUMMARY" \
  "$QC" \
  "${QC}.failures.tsv" \
  "$MANIFEST"

find "$WORKDIR" \
  -maxdepth 1 \
  -type d \
  -name 'local_*' \
  -exec rm -rf {} +

echo
echo "===== RUN ANCHOR-CONSTRAINED LOCAL COMPETITION ====="

python "$PY" \
  "$INVENTORY" \
  "$ISOLATED" \
  "$SPECIFICITY" \
  "$FASTQ" \
  "$REFERENCE_FASTA" \
  "$OUTPUT" \
  "$LOCAL_TARGETS" \
  "$SUMMARY" \
  "$QC" \
  "$WORKDIR" \
  "$MODEL_ID" \
  "$EXPECTED_INVENTORY_ROWS" \
  "$EXPECTED_POSITIVES" \
  "$EXPECTED_FASTQ_READS" \
  "$WORKERS" \
  "$PROGRESS_EVERY" \
  "$TARGET_ENTRY_BP" \
  "$MIN_TARGET_ENTRY_SUPPORT_BP" \
  "$BOUNDARY_TOLERANCE_BP" \
  "$MIN_ALIGNMENT_IDENTITY" \
  "$MIN_EFFECTIVE_COVERAGE" \
  "$NEAR_BEST_SCORE_FRACTION"

gzip -t "$LOCAL_TARGETS"

echo
echo "===== QC ====="
column -ts $'\t' "$QC"

echo
echo "===== SUMMARY ====="
column -ts $'\t' "$SUMMARY"

echo
echo "===== ANCHOR-CONSTRAINED RESULTS ====="
column -ts $'\t' "$OUTPUT"

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in \
      "$OUTPUT" \
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

    rows="$(gzip -cd "$LOCAL_TARGETS" | awk 'END {print NR-1}')"

    printf '%s\t%s\t%s\t%s\t%s\n' \
      "$(basename "$LOCAL_TARGETS")" \
      "$rows" \
      "$(stat -c '%s' "$LOCAL_TARGETS")" \
      "$(sha256sum "$LOCAL_TARGETS" | awk '{print $1}')" \
      "$LOCAL_TARGETS"
} > "$MANIFEST"

echo
echo "===== MANIFEST ====="
column -ts $'\t' "$MANIFEST"
