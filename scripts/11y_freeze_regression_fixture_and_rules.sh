#!/usr/bin/env bash
set -euo pipefail

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
fi

conda activate rnatr-v03
source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"
FIXTURE_VERSION="v0.3.1"
EXPECTED_CASES=18

P01="$PROJECT_ROOT/results/11_periodic_calibrated/$RUN_ID/v0.3.3/simple_periodic_evidence.calibrated.v0.3.3.tsv.gz"
P2="$PROJECT_ROOT/results/11_p2_periodic/$RUN_ID/p2_alternate_exact_simple_periodic_evidence.tsv.gz"
EVENTS="$PROJECT_ROOT/results/11_exact_events/$RUN_ID/exact_repeat_events.tsv.gz"
REFINED="$PROJECT_ROOT/results/11_extreme_nonexact_refined/$RUN_ID/extreme_nonexact_events.refined.tsv"
ANCHOR_GEOMETRY="$PROJECT_ROOT/results/11_anchor_block_validation/$RUN_ID/repeat_event_geometry.quality_validated.tsv"
FASTQ="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_candidates_v0.3.1/ENCFF260PGB.pilot_100k.rnatr_candidate_all.fastq.gz"

OUTDIR="$PROJECT_ROOT/tests/regression/$FIXTURE_VERSION"
DATADIR="$OUTDIR/data"
QCDIR="$PROJECT_ROOT/qc/11_regression_fixture/$RUN_ID/$FIXTURE_VERSION"
WORKDIR="$PROJECT_ROOT/tmp/11_regression_fixture/$RUN_ID/$FIXTURE_VERSION"

CASES="$OUTDIR/regression_cases.tsv"
RULES="$OUTDIR/decision_rules.tsv"
READS_FASTQ="$DATADIR/regression_reads.fastq.gz"
README="$OUTDIR/README.md"
QC="$QCDIR/regression_fixture.qc.tsv"
MANIFEST="$OUTDIR/regression_fixture.manifest.tsv"
PY="$WORKDIR/build_regression_fixture.py"

mkdir -p "$OUTDIR" "$DATADIR" "$QCDIR" "$WORKDIR"

for path in \
  "$P01" \
  "$P2" \
  "$EVENTS" \
  "$REFINED" \
  "$ANCHOR_GEOMETRY" \
  "$FASTQ"
do
    test -s "$path" || {
        echo "ERROR: missing input: $path" >&2
        exit 1
    }
done

cat > "$PY" <<'PY'
from __future__ import annotations

import csv
import gzip
import json
import sys
from pathlib import Path

import pysam

(
    p01_path,
    p2_path,
    events_path,
    refined_path,
    anchor_geometry_path,
    fastq_path,
    cases_path,
    rules_path,
    reads_fastq_path,
    readme_path,
    qc_path,
    fixture_version,
    expected_cases_text,
) = sys.argv[1:]

EXPECTED_CASES = int(expected_cases_text)


def open_table(path):
    opener = gzip.open if path.endswith(".gz") else open
    with opener(
        path,
        "rt",
        encoding="utf-8",
        newline="",
    ) as handle:
        return list(
            csv.DictReader(handle, delimiter="\t")
        )


def value(row, *names, default="."):
    for name in names:
        if name in row and row[name] not in {"", "."}:
            return row[name]
    return default


def number(row, *names, default=0.0):
    raw = value(row, *names, default=str(default))
    try:
        return float(raw)
    except (TypeError, ValueError):
        return float(default)


def choose_one(rows, predicate, label, sort_key=None):
    selected = [row for row in rows if predicate(row)]

    if not selected:
        raise RuntimeError(
            "No regression source row for {}".format(label)
        )

    if sort_key is None:
        selected.sort(
            key=lambda row: (
                value(row, "read_id"),
                value(row, "projection_id", "event_id"),
            )
        )
    else:
        selected.sort(key=sort_key)

    return selected[0]


def span_status(row):
    return value(
        row,
        "exact_span_sequence_status",
        "span_sequence_status",
        default=".",
    )


def case_from_row(
    case_id,
    category,
    source_artifact,
    source_key,
    row,
    expected_primary_class,
    expected_sizing_status,
    guardrail,
    rationale,
):
    return {
        "fixture_version": fixture_version,
        "case_id": case_id,
        "category": category,
        "source_artifact": source_artifact,
        "source_key": source_key,
        "read_id": value(row, "read_id"),
        "target_region_id": value(
            row,
            "target_region_id",
            "target_region_ids",
        ),
        "representative_locus_id": value(
            row,
            "representative_locus_id",
            "representative_locus_ids",
            "locus_cluster_ids",
        ),
        "canonical_motif": value(
            row,
            "canonical_motif",
            "representative_motif",
            "motifs",
        ),
        "raw_interval_start": value(
            row,
            "tract_read_start",
            "event_start",
            "reference_compatible_repeat_raw_start",
        ),
        "raw_interval_end": value(
            row,
            "tract_read_end",
            "event_end",
            "reference_compatible_repeat_raw_end",
        ),
        "observed_bp": value(
            row,
            "repeat_bp_estimate",
            "repeat_bp_lower_bound",
            "tract_read_bp",
            "representative_span_bp",
            "maximum_tract_bp",
            "reference_compatible_repeat_bp",
        ),
        "source_evidence_class": value(
            row,
            "evidence_class",
            "event_class",
            "refined_triage_disposition",
            "quality_validated_evidence_class",
        ),
        "source_sizing_status": value(
            row,
            "sizing_status",
            "allele_length_status",
        ),
        "expected_primary_class": expected_primary_class,
        "expected_sizing_status": expected_sizing_status,
        "expected_guardrail": guardrail,
        "rationale": rationale,
    }


p01 = open_table(p01_path)
p2 = open_table(p2_path)
events = open_table(events_path)
refined = open_table(refined_path)
anchor_geometry = open_table(anchor_geometry_path)

cases = []

row = choose_one(
    p01,
    lambda r: (
        value(r, "evidence_class") == "SPAN"
        and number(r, "repeat_bp_estimate", "tract_read_bp") >= 12
        and number(r, "purity") >= 0.95
        and span_status(r) in {
            "PERIODIC_EXACT_SPAN",
            "PERIODIC_EXACT_SPAN_PASS",
        }
    ),
    "EXACT_SPAN_PERIODIC",
    sort_key=lambda r: (
        -number(r, "repeat_bp_estimate", "tract_read_bp"),
        value(r, "projection_id"),
    ),
)
cases.append(
    case_from_row(
        "RC001",
        "EXACT_SPAN_PERIODIC",
        p01_path,
        value(row, "projection_id"),
        row,
        "SPAN",
        "exact_span",
        "Exact length comes only from the projected interval between two validated flanks.",
        "Positive exact-SPAN periodic control.",
    )
)

row = choose_one(
    p01,
    lambda r: (
        value(r, "evidence_class") == "SPAN"
        and 0 < number(r, "repeat_bp_estimate", "tract_read_bp") < 12
    ),
    "EXACT_SPAN_SHORT",
)
cases.append(
    case_from_row(
        "RC002",
        "EXACT_SPAN_SHORT",
        p01_path,
        value(row, "projection_id"),
        row,
        "SPAN",
        "exact_span",
        "A short flank-bounded interval remains an exact size even when sequence periodicity is not statistically informative.",
        "Short exact-SPAN control.",
    )
)

row = choose_one(
    p01,
    lambda r: (
        value(r, "evidence_class") == "SPAN"
        and span_status(r)
        in {
            "COMPLEX_OR_LOW_PERIODICITY_EXACT_SPAN",
            "EXACT_SPAN_LOW_PERIODICITY",
        }
    ),
    "EXACT_SPAN_SEQUENCE_REVIEW",
)
cases.append(
    case_from_row(
        "RC003",
        "EXACT_SPAN_SEQUENCE_REVIEW",
        p01_path,
        value(row, "projection_id"),
        row,
        "SPAN",
        "exact_span",
        "Flank geometry fixes total interval length, while low periodicity triggers sequence-model review rather than removal of the exact span.",
        "Low-periodicity exact-SPAN control.",
    )
)

for case_id, evidence_class, category in [
    (
        "RC004",
        "LEFT_ANCHORED_CENSORED_RIGHT",
        "CENSORED_RIGHT_END",
    ),
    (
        "RC005",
        "RIGHT_ANCHORED_CENSORED_LEFT",
        "CENSORED_LEFT_END",
    ),
    (
        "RC006",
        "LEFT_ONLY_INTERNAL",
        "LEFT_ONLY_INTERNAL",
    ),
    (
        "RC007",
        "RIGHT_ONLY_INTERNAL",
        "RIGHT_ONLY_INTERNAL",
    ),
    (
        "RC008",
        "REPEAT_ONLY_UNANCHORED",
        "REPEAT_ONLY_UNANCHORED",
    ),
]:
    row = choose_one(
        p01,
        lambda r, cls=evidence_class: (
            value(r, "evidence_class") == cls
        ),
        category,
        sort_key=lambda r: (
            -number(
                r,
                "repeat_bp_lower_bound",
                "tract_read_bp",
            ),
            value(r, "projection_id"),
        ),
    )

    sizing = {
        "LEFT_ANCHORED_CENSORED_RIGHT": "lower_bound",
        "RIGHT_ANCHORED_CENSORED_LEFT": "lower_bound",
        "LEFT_ONLY_INTERNAL": "partial_internal",
        "RIGHT_ONLY_INTERNAL": "partial_internal",
        "REPEAT_ONLY_UNANCHORED": "no_call",
    }[evidence_class]

    guardrail = {
        "LEFT_ANCHORED_CENSORED_RIGHT": (
            "Lower bound requires a validated left flank and repeat tract reaching the expected raw-read end."
        ),
        "RIGHT_ANCHORED_CENSORED_LEFT": (
            "Lower bound requires a validated right flank and repeat tract reaching the expected raw-read end."
        ),
        "LEFT_ONLY_INTERNAL": (
            "One-flank internal evidence emits neither exact size nor lower bound."
        ),
        "RIGHT_ONLY_INTERNAL": (
            "One-flank internal evidence emits neither exact size nor lower bound."
        ),
        "REPEAT_ONLY_UNANCHORED": (
            "Repeat-only sequence evidence cannot measure an allele without a validated genomic flank."
        ),
    }[evidence_class]

    cases.append(
        case_from_row(
            case_id,
            category,
            p01_path,
            value(row, "projection_id"),
            row,
            evidence_class,
            sizing,
            guardrail,
            "Canonical non-SPAN evidence control.",
        )
    )

event_classes = [
    (
        "RC009",
        "SAME_SEQUENCE_MULTIPLE_TARGET_HYPOTHESES",
        "EVENT_MULTIPLE_TARGETS",
        "MULTIPLE_TARGETS_SAME_SEQUENCE_EVIDENCE",
    ),
    (
        "RC010",
        "SAME_INTERVAL_COMPETING_MOTIFS",
        "EVENT_COMPETING_MOTIFS",
        "COMPETING_MOTIF_MODELS",
    ),
    (
        "RC011",
        "BOUNDARY_VARIANTS_SAME_MOTIF",
        "EVENT_BOUNDARY_VARIANTS",
        "BOUNDARY_AMBIGUOUS_SAME_MOTIF",
    ),
    (
        "RC012",
        "OVERLAPPING_MULTIPLE_REPEAT_MODELS",
        "EVENT_OVERLAPPING_MODELS",
        "COMPETING_OVERLAPPING_MODELS",
    ),
]

for case_id, event_class, category, expected in event_classes:
    row = choose_one(
        events,
        lambda r, cls=event_class: (
            value(r, "event_class") == cls
        ),
        category,
        sort_key=lambda r: (
            -number(r, "event_span_bp"),
            value(r, "event_id"),
        ),
    )
    cases.append(
        case_from_row(
            case_id,
            category,
            events_path,
            value(row, "event_id"),
            row,
            expected,
            "event_model",
            "Sequence evidence is grouped by overlapping raw-read interval before target or motif hypotheses are compared.",
            "Event-model ambiguity control.",
        )
    )

refined_classes = [
    (
        "RC013",
        "EXCLUDE_LOCAL_PERIODIC_OVEREXTENSION",
        "LOCAL_PERIODIC_OVEREXTENSION",
    ),
    (
        "RC014",
        "EXCLUDE_CHIMERIC_OR_MULTISEGMENT",
        "CHIMERIC_OR_MULTISEGMENT",
    ),
    (
        "RC015",
        "EXCLUDE_AMBIGUOUS_MAPPING",
        "AMBIGUOUS_MAPPING",
    ),
]

for case_id, disposition, category in refined_classes:
    row = choose_one(
        refined,
        lambda r, cls=disposition: (
            value(r, "refined_triage_disposition") == cls
        ),
        category,
        sort_key=lambda r: (
            -number(r, "maximum_tract_bp"),
            value(r, "event_id"),
        ),
    )
    cases.append(
        case_from_row(
            case_id,
            category,
            refined_path,
            value(row, "event_id"),
            row,
            disposition,
            "no_call",
            "Recurrence or local periodic score cannot rescue weak locus support, chimeric geometry, or ambiguous mapping.",
            "Negative locus-assignment control.",
        )
    )

row = choose_one(
    anchor_geometry,
    lambda r: (
        value(
            r,
            "quality_validated_evidence_class",
        )
        == "REPEAT_ONLY_END_TRUNCATED"
    ),
    "REPEAT_ONLY_END_TRUNCATED",
)
cases.append(
    case_from_row(
        "RC016",
        "REPEAT_ONLY_END_TRUNCATED",
        anchor_geometry_path,
        value(row, "event_id"),
        row,
        "REPEAT_ONLY_END_TRUNCATED",
        "no_call",
        "A repeat-like tract reaching a raw-read end is not a censored lower bound unless the opposite genomic flank is validated.",
        "End-truncated repeat-only control.",
    )
)

row = choose_one(
    anchor_geometry,
    lambda r: (
        number(r, "rejected_old_anchor_blocks") > 0
        and value(
            r,
            "quality_validated_evidence_class",
        )
        == "REPEAT_ONLY_UNANCHORED_CONFIRMED"
    ),
    "PSEUDO_SPLICE_ANCHOR_REJECTED",
)
cases.append(
    case_from_row(
        "RC017",
        "PSEUDO_SPLICE_ANCHOR_REJECTED",
        anchor_geometry_path,
        value(row, "event_id"),
        row,
        "REPEAT_ONLY_UNANCHORED_CONFIRMED",
        "no_call",
        "Whole-read MAPQ and post-N block presence do not validate a flank; each block must pass CIGAR-level reference-support thresholds.",
        "Insertion-dominated pseudo-anchor negative control.",
    )
)

row = choose_one(
    p2,
    lambda r: (
        value(r, "evidence_class") == "SPAN"
        and int(number(r, "assignment_rank")) > 1
        and number(r, "tract_read_bp") >= 12
        and number(r, "purity") >= 0.95
    ),
    "DISTINCT_P2_EXACT_EVENT",
    sort_key=lambda r: (
        -number(r, "tract_read_bp"),
        value(r, "projection_id"),
    ),
)
cases.append(
    case_from_row(
        "RC018",
        "DISTINCT_P2_EXACT_EVENT",
        p2_path,
        value(row, "projection_id"),
        row,
        "SPAN_EVENT_REQUIRES_EVENT_LEVEL_GROUPING",
        "exact_span",
        "Read-level assignment rank is not an event identity; a lower-ranked target can represent a distinct nonoverlapping repeat event on the same long read.",
        "P2 event-centric modeling control.",
    )
)

if len(cases) != EXPECTED_CASES:
    raise RuntimeError(
        "Expected {} cases, created {}".format(
            EXPECTED_CASES,
            len(cases),
        )
    )

case_ids = [row["case_id"] for row in cases]

if len(set(case_ids)) != len(case_ids):
    raise RuntimeError("Duplicate case IDs")

required_read_ids = {
    row["read_id"]
    for row in cases
    if row["read_id"] not in {"", "."}
}

fastq_records = {}

with pysam.FastxFile(fastq_path) as source:
    for entry in source:
        if entry.name in required_read_ids:
            fastq_records[entry.name] = {
                "sequence": entry.sequence,
                "quality": entry.quality,
                "comment": entry.comment or "",
            }

missing_reads = required_read_ids - set(fastq_records)

with gzip.open(
    reads_fastq_path,
    "wt",
    encoding="utf-8",
) as handle:
    for read_id in sorted(fastq_records):
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

case_fields = [
    "fixture_version",
    "case_id",
    "category",
    "source_artifact",
    "source_key",
    "read_id",
    "target_region_id",
    "representative_locus_id",
    "canonical_motif",
    "raw_interval_start",
    "raw_interval_end",
    "observed_bp",
    "source_evidence_class",
    "source_sizing_status",
    "expected_primary_class",
    "expected_sizing_status",
    "expected_guardrail",
    "rationale",
]

with open(
    cases_path,
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=case_fields,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(cases)

rules = [
    (
        "R001",
        "SPAN_INTERVAL",
        "Both genomic flanks are validated",
        "Use the raw-read interval between flanks as exact span",
        "Do not extend a local motif tract into flanks",
    ),
    (
        "R002",
        "SHORT_EXACT_SPAN",
        "Both flanks validated and interval <12 bp",
        "Retain exact span with reduced sequence confidence",
        "12 bp is an algorithmic periodicity threshold, not a biological repeat threshold",
    ),
    (
        "R003",
        "LOW_PERIODICITY_EXACT",
        "Both flanks validated but motif periodicity is low",
        "Retain exact total span and request sequence-model review",
        "Geometry and sequence model are separate evidence axes",
    ),
    (
        "R004",
        "CENSORED_LOWER_BOUND",
        "One genomic flank validated and repeat tract reaches expected raw-read end",
        "Emit lower bound only",
        "The opposite flank is absent, so exact allele length is unknown",
    ),
    (
        "R005",
        "ONE_FLANK_INTERNAL",
        "One genomic flank validated but tract stops before expected raw-read end",
        "Emit partial_internal",
        "Emit neither exact size nor lower bound",
    ),
    (
        "R006",
        "REPEAT_ONLY",
        "No validated genomic flank",
        "Retain sequence evidence without allele sizing",
        "Repeat-like sequence alone cannot establish locus-bounded allele length",
    ),
    (
        "R007",
        "EVENT_GROUPING",
        "Exact intervals overlap on the same raw read",
        "Create one event and preserve sequence/target hypotheses beneath it",
        "Read-level P1/P2 rank is not an event identifier",
    ),
    (
        "R008",
        "LOCUS_SUPPORT",
        "Detected tract overlaps only a small fraction of the target",
        "Classify local periodic overextension",
        "Recurrence cannot rescue target-overlap failure",
    ),
    (
        "R009",
        "CHIMERA",
        "Chimeric, supplementary, or multi-chromosome evidence undermines locus assignment",
        "Exclude from locus-specific repeat sizing",
        "Keep as regression negative rather than deleting the record",
    ),
    (
        "R010",
        "REFERENCE_ARCHITECTURE",
        "Reference comparison is requested",
        "Measure the actual reference sequence architecture",
        "Catalog interval length is not reference allele length",
    ),
    (
        "R011",
        "FLANK_RESCUE",
        "Residual sequence is tested as a genomic flank",
        "Require unique, high-quality, expected-side alignment",
        "Residual sequence may be repeat continuation, low complexity, adapter, or chimera",
    ),
    (
        "R012",
        "SPLICE_BLOCK_QC",
        "A post-N full-read block is proposed as an anchor",
        "Require block-level match support, span balance, and low indel fractions",
        "Whole-read MAPQ cannot validate an insertion-dominated pseudo-anchor",
    ),
    (
        "R013",
        "EXPANSION_GUARDRAIL",
        "Allele is not bounded by validated flanks",
        "Do not emit reference-relative expansion status",
        "Observed RNA tract length is not complete expressed allele length",
    ),
]

with open(
    rules_path,
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.writer(
        handle,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writerow(
        [
            "rule_id",
            "rule_name",
            "condition",
            "required_action",
            "guardrail",
        ]
    )
    writer.writerows(rules)

with open(
    readme_path,
    "w",
    encoding="utf-8",
) as handle:
    handle.write(
        "# RNA-TR-Scout regression fixture {}\n\n".format(
            fixture_version
        )
    )
    handle.write(
        "This fixture freezes edge cases discovered during the "
        "ENCSR307SHM 100k-read pilot. It is a software regression "
        "set, not a disease or expansion truth set.\n\n"
    )
    handle.write(
        "- Cases: {}\n".format(len(cases))
    )
    handle.write(
        "- Unique raw reads: {}\n".format(
            len(required_read_ids)
        )
    )
    handle.write(
        "- Decision rules: {}\n".format(len(rules))
    )
    handle.write(
        "- Missing raw reads: {}\n\n".format(
            len(missing_reads)
        )
    )
    handle.write(
        "Every future caller revision must preserve the expected "
        "classification and sizing guardrail for these cases, "
        "unless the fixture version is deliberately updated.\n"
    )

status = "PASS"

if (
    len(cases) != EXPECTED_CASES
    or missing_reads
    or len(fastq_records) != len(required_read_ids)
):
    status = "REVIEW"

with open(
    qc_path,
    "w",
    encoding="utf-8",
) as handle:
    handle.write("metric\tvalue\n")
    handle.write(
        "expected_cases\t{}\n".format(
            EXPECTED_CASES
        )
    )
    handle.write(
        "observed_cases\t{}\n".format(
            len(cases)
        )
    )
    handle.write(
        "unique_case_ids\t{}\n".format(
            len(set(case_ids))
        )
    )
    handle.write(
        "unique_read_ids_required\t{}\n".format(
            len(required_read_ids)
        )
    )
    handle.write(
        "fastq_reads_written\t{}\n".format(
            len(fastq_records)
        )
    )
    handle.write(
        "missing_fastq_reads\t{}\n".format(
            len(missing_reads)
        )
    )
    handle.write(
        "decision_rules_written\t{}\n".format(
            len(rules)
        )
    )
    handle.write(
        "audit_status\t{}\n".format(status)
    )

if status != "PASS":
    raise SystemExit(
        "Regression fixture requires review"
    )
PY

echo "===== SHELL AND EMBEDDED PYTHON SYNTAX ====="
python -m py_compile "$PY"
echo "Embedded Python syntax: OK"

rm -f \
  "$CASES" \
  "$RULES" \
  "$READS_FASTQ" \
  "$README" \
  "$QC" \
  "$MANIFEST"

echo
echo "===== BUILD REGRESSION FIXTURE ====="

python "$PY" \
  "$P01" \
  "$P2" \
  "$EVENTS" \
  "$REFINED" \
  "$ANCHOR_GEOMETRY" \
  "$FASTQ" \
  "$CASES" \
  "$RULES" \
  "$READS_FASTQ" \
  "$README" \
  "$QC" \
  "$FIXTURE_VERSION" \
  "$EXPECTED_CASES"

gzip -t "$READS_FASTQ"

echo
echo "===== QC ====="
column -ts $'\t' "$QC"

echo
echo "===== REGRESSION CASES ====="
column -ts $'\t' "$CASES"

echo
echo "===== DECISION RULES ====="
column -ts $'\t' "$RULES"

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in \
      "$CASES" \
      "$RULES" \
      "$QC"
    do
        rows="$(awk 'END {print NR-1}' "$path")"

        printf '%s\t%s\t%s\t%s\t%s\n' \
          "$(basename "$path")" \
          "$rows" \
          "$(stat -c '%s' "$path")" \
          "$(sha256sum "$path" | awk '{print $1}')" \
          "$path"
    done

    rows="$(gzip -cd "$READS_FASTQ" | awk 'END {print NR/4}')"

    printf '%s\t%s\t%s\t%s\t%s\n' \
      "$(basename "$READS_FASTQ")" \
      "$rows" \
      "$(stat -c '%s' "$READS_FASTQ")" \
      "$(sha256sum "$READS_FASTQ" | awk '{print $1}')" \
      "$READS_FASTQ"

    printf '%s\t%s\t%s\t%s\t%s\n' \
      "$(basename "$README")" \
      "." \
      "$(stat -c '%s' "$README")" \
      "$(sha256sum "$README" | awk '{print $1}')" \
      "$README"
} > "$MANIFEST"

echo
echo "===== MANIFEST ====="
column -ts $'\t' "$MANIFEST"

echo
echo "===== COMPLETE ====="
echo "$CASES"
echo "$RULES"
echo "$READS_FASTQ"
echo "$README"
echo "$QC"
