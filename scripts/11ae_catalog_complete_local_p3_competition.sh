#!/usr/bin/env bash
set -euo pipefail

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
fi

conda activate rnatr-v03
source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"
MODEL_ID="rnatr_p3_catalog_complete_local_competition_v0.3.1"

ANCHOR_RESULTS="$PROJECT_ROOT/results/11_p3_anchor_constrained/$RUN_ID/p3_anchor_constrained_local_competition.tsv"
INVENTORY="$PROJECT_ROOT/results/11_p3_inventory/$RUN_ID/p3_proximal_inventory.tsv.gz"
CATALOG="$CATALOG_ROOT/trexplorer_v2/rnatr_pilot_v03/final/RNA-TR-Scout_v0.3.mapping_target_regions.bed.gz"
FASTQ="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_candidates_v0.3.1/ENCFF260PGB.pilot_100k.rnatr_candidate_all.fastq.gz"
REFERENCE_FASTA="$PROJECT_ROOT/refs/gencode_v50/GRCh38.primary_assembly.genome.fa"

OUTDIR="$PROJECT_ROOT/results/11_p3_catalog_local_competition/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_p3_catalog_local_competition/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_p3_catalog_local_competition/$RUN_ID"

OUTPUT="$OUTDIR/p3_catalog_complete_local_competition.tsv"
LOCAL_TARGETS="$OUTDIR/p3_catalog_complete_local_target_sets.tsv.gz"
SUMMARY="$OUTDIR/p3_catalog_complete_local_competition_summary.tsv"
QC="$QCDIR/p3_catalog_complete_local_competition.qc.tsv"
PARAMETERS="$OUTDIR/${MODEL_ID}.parameters.tsv"
MANIFEST="$OUTDIR/${RUN_ID}.p3_catalog_local_competition.manifest.tsv"
PY="$WORKDIR/run_catalog_complete_local_competition.py"

EXPECTED_ANCHOR_RESULTS=23
EXPECTED_INVENTORY_ROWS=211939
EXPECTED_CATALOG_ROWS=349490
EXPECTED_FASTQ_READS=79176

WORKERS=8
PROGRESS_EVERY=5
MAX_LOCAL_RADIUS_BP=2000
TARGET_ENTRY_BP=60
MIN_TARGET_ENTRY_SUPPORT_BP=12
BOUNDARY_TOLERANCE_BP=10
MIN_ALIGNMENT_IDENTITY=0.70
MIN_EFFECTIVE_COVERAGE=0.70
NEAR_BEST_SCORE_FRACTION=0.95

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR"

for path in \
  "$ANCHOR_RESULTS" \
  "$INVENTORY" \
  "$CATALOG" \
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
model_id	$MODEL_ID	Catalog-complete local target competition for P3 bridge-positive anchors
positive_anchors	$EXPECTED_ANCHOR_RESULTS	Anchor-constrained bridge candidates
catalog	$CATALOG	All final mapping target regions
maximum_local_radius_bp	$MAX_LOCAL_RADIUS_BP	Maximum genomic distance from the mapped block edge
reachability_rule	gap_plus_required_target_entry_le_raw_softclip_bp	Only targets reachable by the observed soft clip compete
target_entry_bp	$TARGET_ENTRY_BP	Maximum reference target-entry sequence
minimum_target_entry_support_bp	$MIN_TARGET_ENTRY_SUPPORT_BP	Required reference bases inside the candidate target
boundary_tolerance_bp	$BOUNDARY_TOLERANCE_BP	Query/reference alignment must begin near the mapped-block boundary
minimum_alignment_identity	$MIN_ALIGNMENT_IDENTITY	Provisional ONT compatibility threshold
minimum_effective_coverage	$MIN_EFFECTIVE_COVERAGE	Aligned span divided by min(query length, reference length)
near_best_score_fraction	$NEAR_BEST_SCORE_FRACTION	Local distinct reference groups within 95% of best valid score
anchor_constraint	same_chromosome_same_block_edge_same_target_direction	Competitors are genomic-local, not genome-wide
call_semantics	local_target_adjudication_only	No repeat-length, allele-length, or expansion call
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
    anchor_results_path,
    inventory_path,
    catalog_path,
    fastq_path,
    reference_fasta_path,
    output_path,
    local_targets_path,
    summary_path,
    qc_path,
    workdir,
    model_id,
    expected_anchor_results_text,
    expected_inventory_rows_text,
    expected_catalog_rows_text,
    expected_fastq_reads_text,
    workers_text,
    progress_every_text,
    maximum_radius_text,
    target_entry_text,
    minimum_target_entry_text,
    boundary_tolerance_text,
    minimum_identity_text,
    minimum_effective_coverage_text,
    near_best_fraction_text,
) = sys.argv[1:]

EXPECTED_ANCHOR_RESULTS = int(
    expected_anchor_results_text
)
EXPECTED_INVENTORY_ROWS = int(
    expected_inventory_rows_text
)
EXPECTED_CATALOG_ROWS = int(
    expected_catalog_rows_text
)
EXPECTED_FASTQ_READS = int(
    expected_fastq_reads_text
)

WORKERS = int(workers_text)
PROGRESS_EVERY = int(progress_every_text)
MAXIMUM_RADIUS = int(maximum_radius_text)
TARGET_ENTRY_BP = int(target_entry_text)
MINIMUM_TARGET_ENTRY = int(
    minimum_target_entry_text
)
BOUNDARY_TOLERANCE = int(
    boundary_tolerance_text
)
MINIMUM_IDENTITY = float(minimum_identity_text)
MINIMUM_EFFECTIVE_COVERAGE = float(
    minimum_effective_coverage_text
)
NEAR_BEST_FRACTION = float(
    near_best_fraction_text
)

COMPLEMENT = str.maketrans("ACGT", "TGCA")


def reverse_complement(sequence):
    return sequence.translate(COMPLEMENT)[::-1]


def normalize_chromosome(chromosome):
    value = chromosome

    if value.startswith("chr"):
        value = value[3:]

    if value in {"M", "MT"}:
        value = "MT"

    return value


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

        denominator = min(
            query_length,
            reference_length,
        )
        effective_coverage = (
            (query_end - query_start)
            / denominator
            if denominator
            else 0.0
        )

        rows.append(
            {
                "reference_id": fields[5],
                "query_start": query_start,
                "query_end": query_end,
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


with open(
    anchor_results_path,
    "r",
    encoding="utf-8",
    newline="",
) as handle:
    anchor_rows = list(
        csv.DictReader(handle, delimiter="\t")
    )

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

catalog_by_chromosome = defaultdict(list)
catalog_rows = 0

with gzip.open(
    catalog_path,
    "rt",
    encoding="utf-8",
) as handle:
    for line in handle:
        line = line.rstrip("\n")

        if not line or line.startswith("#"):
            continue

        fields = line.split("\t")

        if len(fields) < 3:
            continue

        try:
            start = int(fields[1])
            end = int(fields[2])
        except ValueError:
            continue

        catalog_rows += 1
        chromosome = fields[0]
        target_id = (
            fields[3]
            if len(fields) >= 4
            and fields[3]
            else "{}:{}-{}".format(
                chromosome,
                start,
                end,
            )
        )

        catalog_by_chromosome[
            normalize_chromosome(chromosome)
        ].append(
            {
                "chromosome": chromosome,
                "start": start,
                "end": end,
                "target_id": target_id,
            }
        )

for chromosome in catalog_by_chromosome:
    catalog_by_chromosome[chromosome].sort(
        key=lambda row: (
            row["start"],
            row["end"],
            row["target_id"],
        )
    )

required_read_ids = {
    row["read_id"]
    for row in anchor_rows
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

missing_reads = (
    required_read_ids
    - set(fastq_records)
)

reference = pysam.FastaFile(
    reference_fasta_path
)

local_sets = {}
local_target_rows = []
geometry_errors = 0
expected_targets_missing_from_catalog = 0

for anchor in anchor_rows:
    projection_id = anchor["projection_id"]
    inventory = inventory_lookup.get(
        projection_id
    )

    if inventory is None:
        geometry_errors += 1
        continue

    read_id = inventory["read_id"]
    read_sequence = fastq_records[read_id]
    raw_start = int(
        inventory["target_facing_raw_start"]
    )
    raw_end = int(
        inventory["target_facing_raw_end"]
    )
    raw_clip = read_sequence[
        raw_start:raw_end
    ]

    side = inventory[
        "target_facing_genomic_side"
    ]
    strand = inventory["strand"]

    reverse_query = (
        (
            side == "GENOMIC_RIGHT"
            and strand == "-"
        )
        or (
            side == "GENOMIC_LEFT"
            and strand == "+"
        )
    )

    oriented_clip = (
        reverse_complement(raw_clip)
        if reverse_query
        else raw_clip
    )

    normalized_chromosome = normalize_chromosome(
        inventory["target_chrom"]
    )
    block_start = int(
        inventory["selected_block_start"]
    )
    block_end = int(
        inventory["selected_block_end"]
    )
    expected_target_id = inventory[
        "target_region_id"
    ]
    expected_start = int(
        inventory["target_start"]
    )
    expected_end = int(
        inventory["target_end"]
    )

    candidate_map = {}

    for catalog_target in catalog_by_chromosome.get(
        normalized_chromosome,
        [],
    ):
        target_start = catalog_target["start"]
        target_end = catalog_target["end"]
        target_length = max(
            0,
            target_end - target_start,
        )
        required_entry = min(
            target_length,
            MINIMUM_TARGET_ENTRY,
        )

        if required_entry <= 0:
            continue

        if side == "GENOMIC_RIGHT":
            gap = target_start - block_end

        elif side == "GENOMIC_LEFT":
            gap = block_start - target_end

        else:
            geometry_errors += 1
            continue

        if gap < 0:
            continue

        if gap > MAXIMUM_RADIUS:
            continue

        if gap + required_entry > len(
            oriented_clip
        ):
            continue

        key = (
            normalize_chromosome(
                catalog_target["chromosome"]
            ),
            target_start,
            target_end,
            catalog_target["target_id"],
        )
        candidate_map[key] = {
            "chromosome": catalog_target[
                "chromosome"
            ],
            "start": target_start,
            "end": target_end,
            "target_id": catalog_target[
                "target_id"
            ],
            "source": "FINAL_MAPPING_CATALOG",
        }

    expected_key = (
        normalized_chromosome,
        expected_start,
        expected_end,
        expected_target_id,
    )

    if expected_key not in candidate_map:
        expected_targets_missing_from_catalog += 1
        candidate_map[expected_key] = {
            "chromosome": inventory[
                "target_chrom"
            ],
            "start": expected_start,
            "end": expected_end,
            "target_id": expected_target_id,
            "source": "EXPECTED_INVENTORY_FALLBACK",
        }

    reference_records = []
    reference_metadata = {}

    for candidate_index, candidate in enumerate(
        sorted(
            candidate_map.values(),
            key=lambda row: (
                row["start"],
                row["end"],
                row["target_id"],
            ),
        ),
        start=1,
    ):
        target_start = candidate["start"]
        target_end = candidate["end"]
        target_length = target_end - target_start
        required_entry = min(
            target_length,
            MINIMUM_TARGET_ENTRY,
        )

        resolved_contig = resolve_contig(
            reference,
            candidate["chromosome"],
        )

        if side == "GENOMIC_RIGHT":
            gap = target_start - block_end
            target_entry_end = min(
                target_end,
                target_start + TARGET_ENTRY_BP,
            )
            reference_sequence = reference.fetch(
                resolved_contig,
                block_end,
                target_entry_end,
            ).upper()

        else:
            gap = block_start - target_end
            target_entry_start = max(
                target_start,
                target_end - TARGET_ENTRY_BP,
            )
            reference_sequence = reverse_complement(
                reference.fetch(
                    resolved_contig,
                    target_entry_start,
                    block_start,
                ).upper()
            )

        reference_id = "LC{:05d}".format(
            candidate_index
        )
        digest = hashlib.sha256(
            reference_sequence.encode()
        ).hexdigest()

        reference_records.append(
            (
                reference_id,
                reference_sequence,
            )
        )
        reference_metadata[
            reference_id
        ] = {
            "target_id": candidate[
                "target_id"
            ],
            "start": target_start,
            "end": target_end,
            "gap_bp": gap,
            "target_entry_bp": min(
                target_length,
                TARGET_ENTRY_BP,
            ),
            "required_reference_end": (
                gap + required_entry
            ),
            "digest": digest,
            "is_expected": (
                candidate["target_id"]
                == expected_target_id
                and target_start
                    == expected_start
                and target_end
                    == expected_end
            ),
            "source": candidate["source"],
        }

        local_target_rows.append(
            {
                "positive_projection_id": projection_id,
                "read_id": read_id,
                "reference_id": reference_id,
                "target_region_id": candidate[
                    "target_id"
                ],
                "target_start": target_start,
                "target_end": target_end,
                "gap_bp": gap,
                "target_entry_bp": min(
                    target_length,
                    TARGET_ENTRY_BP,
                ),
                "reference_bp": len(
                    reference_sequence
                ),
                "reference_sha256": digest,
                "is_expected_target": str(
                    reference_metadata[
                        reference_id
                    ]["is_expected"]
                ).lower(),
                "candidate_source": candidate[
                    "source"
                ],
            }
        )

    local_sets[projection_id] = {
        "anchor": anchor,
        "inventory": inventory,
        "query": oriented_clip,
        "references": reference_records,
        "reference_metadata": (
            reference_metadata
        ),
    }

reference.close()

progress_lock = threading.Lock()
progress = {
    "completed": 0,
    "start": time.time(),
}


def run_local_set(projection_id):
    local = local_sets[projection_id]
    inventory = local["inventory"]
    query_sequence = local["query"]
    reference_records = local[
        "references"
    ]
    reference_metadata = local[
        "reference_metadata"
    ]

    safe_id = "".join(
        character
        if character.isalnum()
        else "_"
        for character in projection_id
    )
    pair_directory = os.path.join(
        workdir,
        "catalog_" + safe_id,
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
        for reference_id, sequence in (
            reference_records
        ):
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

    alignments = parse_paf(
        completed.stdout
    )

    try:
        os.remove(query_path)
        os.remove(reference_path)
        os.rmdir(pair_directory)
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

        if not (
            boundary_connected
            and quality_pass
            and reaches_target
        ):
            continue

        digest = metadata["digest"]
        digest_targets[digest].add(
            metadata["target_id"]
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

    expected_reference_ids = [
        reference_id
        for reference_id, metadata
        in reference_metadata.items()
        if metadata["is_expected"]
    ]

    if len(expected_reference_ids) != 1:
        raise RuntimeError(
            "Expected exactly one expected target for {}".format(
                projection_id
            )
        )

    expected_reference_id = (
        expected_reference_ids[0]
    )
    expected_digest = reference_metadata[
        expected_reference_id
    ]["digest"]

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

    tied_best_count = (
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

    candidate_target_count = len(
        reference_records
    )
    distinct_reference_count = len(
        {
            metadata["digest"]
            for metadata
            in reference_metadata.values()
        }
    )
    expected_equivalent_targets = len(
        digest_targets.get(
            expected_digest,
            set(),
        )
    )

    if expected_alignment is None:
        status = (
            "EXPECTED_TARGET_NO_VALID_BRIDGE"
        )
        interpretation = (
            "Expected bridge was not reproduced under "
            "catalog-complete local competition"
        )

    elif candidate_target_count == 1:
        status = (
            "EXPECTED_ONLY_REACHABLE_TARGET_NO_COMPETITION"
        )
        interpretation = (
            "Anchor and bridge support the expected target, "
            "but no other catalog target is reachable from "
            "this block edge and soft-clip length"
        )

    elif expected_score == best_score:
        if tied_best_count > 1:
            status = (
                "EXPECTED_TARGET_TIED_BEST_DISTINCT_REFERENCE_GROUPS"
            )
            interpretation = (
                "Anchor localizes the region, but distinct "
                "reachable target references tie for best bridge"
            )
        elif expected_equivalent_targets > 1:
            status = (
                "EXPECTED_SEQUENCE_GROUP_BEST_MULTIPLE_EQUIVALENT_TARGETS"
            )
            interpretation = (
                "The best bridge sequence is shared by multiple "
                "reachable local catalog targets"
            )
        else:
            status = (
                "EXPECTED_TARGET_UNIQUE_BEST_LOCAL_CATALOG"
            )
            interpretation = (
                "Expected target is the unique best valid bridge "
                "among all reachable local catalog targets"
            )

    elif (
        best_score is not None
        and expected_score
            >= best_score * NEAR_BEST_FRACTION
    ):
        status = (
            "EXPECTED_TARGET_NEAR_BEST_LOCAL_CATALOG"
        )
        interpretation = (
            "Expected target remains locally plausible but is "
            "not uniquely discriminated"
        )

    else:
        status = (
            "ALTERNATIVE_LOCAL_CATALOG_TARGET_OUTSCORES_EXPECTED"
        )
        interpretation = (
            "Another reachable local catalog target provides "
            "a better valid bridge than the expected target"
        )

    result = {
        "model_id": model_id,
        "projection_id": projection_id,
        "read_id": inventory["read_id"],
        "expected_target_region_id": (
            inventory["target_region_id"]
        ),
        "anchor_mapq": inventory[
            "best_mapq"
        ],
        "target_facing_genomic_side": (
            inventory[
                "target_facing_genomic_side"
            ]
        ),
        "selected_block_start": inventory[
            "selected_block_start"
        ],
        "selected_block_end": inventory[
            "selected_block_end"
        ],
        "raw_softclip_bp": inventory[
            "target_facing_softclip_bp"
        ],
        "reachable_catalog_target_count": (
            candidate_target_count
        ),
        "distinct_local_reference_groups": (
            distinct_reference_count
        ),
        "valid_local_bridge_groups": len(
            ranked_digests
        ),
        "expected_reference_group_observed": str(
            expected_alignment is not None
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
        "best_local_alignment_score": (
            best_score
            if best_score is not None
            else "."
        ),
        "near_best_local_reference_groups": len(
            near_best_digests
        ),
        "tied_best_local_reference_groups": (
            tied_best_count
        ),
        "expected_equivalent_target_count": (
            expected_equivalent_targets
        ),
        "catalog_local_status": status,
        "catalog_local_interpretation": (
            interpretation
        ),
        "previous_anchor_local_status": (
            local["anchor"][
                "local_competition_status"
            ]
        ),
        "repeat_length_status": (
            "NOT_ASSESSED"
        ),
        "allele_length_status": (
            "NOT_ASSESSED"
        ),
        "expansion_status": "NOT_ASSESSED",
    }

    with progress_lock:
        progress["completed"] += 1
        completed_count = progress[
            "completed"
        ]

        if (
            completed_count
            % PROGRESS_EVERY == 0
            or completed_count
            == len(local_sets)
        ):
            elapsed = (
                time.time()
                - progress["start"]
            )
            rate = (
                completed_count / elapsed
                if elapsed
                else 0.0
            )
            remaining = (
                (
                    len(local_sets)
                    - completed_count
                )
                / rate
                if rate
                else 0.0
            )
            print(
                "[INFO] catalog-local sets {}/{}; "
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
            results.append(
                future.result()
            )
        except Exception as error:
            failures.append(
                (
                    projection_id,
                    str(error),
                )
            )

results.sort(
    key=lambda row: row[
        "projection_id"
    ]
)

if not results:
    raise RuntimeError(
        "No catalog-local results generated"
    )

output_fields = list(
    results[0].keys()
)

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
        "reference_counts": [],
        "near_best_counts": [],
    }
)

for row in results:
    counts[
        "status::{}".format(
            row["catalog_local_status"]
        )
    ] += 1

    group_names = [
        "ALL",
        "status::{}".format(
            row["catalog_local_status"]
        ),
    ]

    for group_name in group_names:
        group = summary_groups[
            group_name
        ]
        group["rows"] += 1
        group["reads"].add(
            row["read_id"]
        )
        group["targets"].add(
            row[
                "expected_target_region_id"
            ]
        )
        group["candidate_counts"].append(
            int(
                row[
                    "reachable_catalog_target_count"
                ]
            )
        )
        group["reference_counts"].append(
            int(
                row[
                    "distinct_local_reference_groups"
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
        return float(
            ordered[size // 2]
        )

    return (
        ordered[size // 2 - 1]
        + ordered[size // 2]
    ) / 2.0


summary_fields = [
    "group",
    "rows",
    "unique_reads",
    "unique_expected_targets",
    "reachable_catalog_targets_median",
    "distinct_reference_groups_median",
    "near_best_reference_groups_median",
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

    for group_name in sorted(
        summary_groups
    ):
        group = summary_groups[
            group_name
        ]

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
                "reachable_catalog_targets_median": (
                    "{:.6f}".format(
                        median(
                            group[
                                "candidate_counts"
                            ]
                        )
                    )
                ),
                "distinct_reference_groups_median": (
                    "{:.6f}".format(
                        median(
                            group[
                                "reference_counts"
                            ]
                        )
                    )
                ),
                "near_best_reference_groups_median": (
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
    len(anchor_rows)
       != EXPECTED_ANCHOR_RESULTS
    or len(inventory_rows)
       != EXPECTED_INVENTORY_ROWS
    or catalog_rows
       != EXPECTED_CATALOG_ROWS
    or fastq_count
       != EXPECTED_FASTQ_READS
    or missing_reads
    or geometry_errors
    or failures
    or len(results)
       != EXPECTED_ANCHOR_RESULTS
):
    status = "REVIEW"

with open(
    qc_path,
    "w",
    encoding="utf-8",
) as handle:
    handle.write(
        "metric\tvalue\n"
    )
    handle.write(
        "expected_anchor_results\t{}\n".format(
            EXPECTED_ANCHOR_RESULTS
        )
    )
    handle.write(
        "observed_anchor_results\t{}\n".format(
            len(anchor_rows)
        )
    )
    handle.write(
        "expected_inventory_rows\t{}\n".format(
            EXPECTED_INVENTORY_ROWS
        )
    )
    handle.write(
        "observed_inventory_rows\t{}\n".format(
            len(inventory_rows)
        )
    )
    handle.write(
        "expected_catalog_rows\t{}\n".format(
            EXPECTED_CATALOG_ROWS
        )
    )
    handle.write(
        "observed_catalog_rows\t{}\n".format(
            catalog_rows
        )
    )
    handle.write(
        "expected_fastq_reads\t{}\n".format(
            EXPECTED_FASTQ_READS
        )
    )
    handle.write(
        "observed_fastq_reads\t{}\n".format(
            fastq_count
        )
    )
    handle.write(
        "missing_anchor_reads\t{}\n".format(
            len(missing_reads)
        )
    )
    handle.write(
        "local_sets\t{}\n".format(
            len(local_sets)
        )
    )
    handle.write(
        "local_target_rows\t{}\n".format(
            len(local_target_rows)
        )
    )
    handle.write(
        "expected_targets_added_by_fallback\t{}\n".format(
            expected_targets_missing_from_catalog
        )
    )
    handle.write(
        "geometry_errors\t{}\n".format(
            geometry_errors
        )
    )
    handle.write(
        "alignment_failures\t{}\n".format(
            len(failures)
        )
    )
    handle.write(
        "results_written\t{}\n".format(
            len(results)
        )
    )

    for key, count in sorted(
        counts.items()
    ):
        handle.write(
            "{}\t{}\n".format(
                key,
                count,
            )
        )

    handle.write(
        "repeat_length_calls_emitted\t0\n"
    )
    handle.write(
        "allele_length_calls_emitted\t0\n"
    )
    handle.write(
        "expansion_calls_emitted\t0\n"
    )
    handle.write(
        "audit_status\t{}\n".format(
            status
        )
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
                    error.replace(
                        "\t",
                        " ",
                    ),
                )
            )

if status != "PASS":
    raise SystemExit(
        "Catalog-complete local competition requires review"
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
  -name 'catalog_*' \
  -exec rm -rf {} +

echo
echo "===== RUN CATALOG-COMPLETE LOCAL COMPETITION ====="

python "$PY" \
  "$ANCHOR_RESULTS" \
  "$INVENTORY" \
  "$CATALOG" \
  "$FASTQ" \
  "$REFERENCE_FASTA" \
  "$OUTPUT" \
  "$LOCAL_TARGETS" \
  "$SUMMARY" \
  "$QC" \
  "$WORKDIR" \
  "$MODEL_ID" \
  "$EXPECTED_ANCHOR_RESULTS" \
  "$EXPECTED_INVENTORY_ROWS" \
  "$EXPECTED_CATALOG_ROWS" \
  "$EXPECTED_FASTQ_READS" \
  "$WORKERS" \
  "$PROGRESS_EVERY" \
  "$MAX_LOCAL_RADIUS_BP" \
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
echo "===== CATALOG-COMPLETE LOCAL RESULTS ====="
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
