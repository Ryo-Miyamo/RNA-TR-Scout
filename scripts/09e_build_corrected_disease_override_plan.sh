#!/usr/bin/env bash
set -euo pipefail

source /mnt/intelssd/rnatr_project/config/paths.env

STRDIR="$CATALOG_ROOT/strchive/current"
CONCORDANCE="$STRDIR/STRchive_vs_TRExplorer.concordance.tsv"
FORCED_AUDIT="$STRDIR/TRExplorer_forced_vs_STRchive.tsv"
PRIORITY="$CATALOG_ROOT/trexplorer_v2/rnatr_pilot_v03/TRExplorer_v2.rnatr_priority_tiers.tsv.gz"
CORE="$CATALOG_ROOT/trexplorer_v2/rnatr_pilot_v03/TRExplorer_v2.rnatr_pilot_core.tsv.gz"

OUTDIR="$STRDIR/finalization"
WORKDIR="$PROJECT_ROOT/tmp/09e_finalize_disease_override_plan"

PLAN="$OUTDIR/STRchive_corrected_override_plan.tsv"
TARGETS="$OUTDIR/STRchive_trexplorer_force_targets.tsv"
FALLBACK="$OUTDIR/STRchive_external_fallback_loci.tsv"
SUMMARY="$OUTDIR/STRchive_corrected_override_plan.summary.tsv"
FORCED_ONLY="$OUTDIR/TRExplorer_forced_only_retained.tsv"

PYTHON_SCRIPT="$WORKDIR/build_corrected_override_plan.py"

mkdir -p "$OUTDIR" "$WORKDIR"

for path in "$CONCORDANCE" "$FORCED_AUDIT" "$PRIORITY" "$CORE"; do
    test -s "$path" || {
        echo "ERROR: missing input: $path" >&2
        exit 1
    }
done

cat > "$PYTHON_SCRIPT" <<'PY'
import csv
import gzip
import sys
from collections import Counter

(
    concordance_path,
    forced_audit_path,
    priority_path,
    core_path,
    plan_path,
    targets_path,
    fallback_path,
    forced_only_path,
    summary_path,
) = sys.argv[1:]

IUPAC = {
    "A": {"A"},
    "C": {"C"},
    "G": {"G"},
    "T": {"T"},
    "R": {"A", "G"},
    "Y": {"C", "T"},
    "S": {"G", "C"},
    "W": {"A", "T"},
    "K": {"G", "T"},
    "M": {"A", "C"},
    "B": {"C", "G", "T"},
    "D": {"A", "G", "T"},
    "H": {"A", "C", "T"},
    "V": {"A", "C", "G"},
    "N": {"A", "C", "G", "T"},
}

COMPLEMENT = str.maketrans(
    "ACGTRYSWKMBDHVN",
    "TGCAYRSWMKVHDBN",
)


def reverse_complement(sequence):
    return sequence.translate(COMPLEMENT)[::-1]


def rotations(sequence):
    return [
        sequence[index:] + sequence[:index]
        for index in range(len(sequence))
    ]


def split_motifs(text):
    values = []
    for separator in [",", ";", "/", "|"]:
        text = text.replace(separator, " ")
    for token in text.split():
        token = token.strip().upper()
        if token and token not in {"NONE", "."}:
            values.append(token)
    return values


def degenerate_match(pattern, concrete):
    pattern = pattern.upper()
    concrete = concrete.upper()

    if len(pattern) != len(concrete) or not pattern:
        return False

    for oriented in (pattern, reverse_complement(pattern)):
        for rotated in rotations(oriented):
            if all(
                base in IUPAC.get(code, {code})
                for code, base in zip(rotated, concrete)
            ):
                return True

    return False


def motif_compatible(reference, pathogenic, candidate):
    candidate = candidate.upper()

    for motif in split_motifs(reference) + split_motifs(pathogenic):
        if degenerate_match(motif, candidate):
            return True

    return False


priority_lookup = {}

with gzip.open(priority_path, "rt", encoding="utf-8", newline="") as handle:
    reader = csv.DictReader(handle, delimiter="\t")

    for row in reader:
        priority_lookup[row["locus_id"]] = {
            "priority_tier": row["priority_tier"],
            "primary_region": row["primary_region"],
            "static_pilot_include": row["static_pilot_include"],
            "forced_disease": row["forced_disease"],
        }

core_ids = set()

with gzip.open(core_path, "rt", encoding="utf-8", newline="") as handle:
    reader = csv.DictReader(handle, delimiter="\t")
    core_ids = {
        row["locus_id"]
        for row in reader
        if row.get("locus_id")
    }

plan_rows = []
target_rows = []
fallback_rows = []
summary = Counter()

with open(concordance_path, encoding="utf-8", newline="") as handle:
    reader = csv.DictReader(handle, delimiter="\t")

    for row in reader:
        candidate = row["best_trexplorer_locus_id"]
        candidate_motif = row["best_trexplorer_motif"]
        original_action = row["external_override_action"]
        original_match = row["match_class"]
        already_forced = row["trexplorer_already_forced"] == "true"

        iupac_compatible = False

        if candidate and candidate_motif:
            iupac_compatible = motif_compatible(
                row["reference_motif"],
                row["pathogenic_motif"],
                candidate_motif,
            )

        if original_action == "ALREADY_FORCED":
            corrected_action = "ALREADY_FORCED"
            corrected_match = original_match
        elif original_action == "FORCE_MATCHED_TREXPLORER_LOCUS":
            corrected_action = "FORCE_MATCHED_TREXPLORER_LOCUS"
            corrected_match = original_match
        elif iupac_compatible and already_forced:
            corrected_action = "ALREADY_FORCED_IUPAC"
            corrected_match = "IUPAC_DEGENERATE_MOTIF_MATCH"
        elif iupac_compatible and candidate:
            corrected_action = "FORCE_MATCHED_TREXPLORER_LOCUS_IUPAC"
            corrected_match = "IUPAC_DEGENERATE_MOTIF_MATCH"
        else:
            corrected_action = "ADD_EXTERNAL_FALLBACK"
            corrected_match = original_match

        metadata = priority_lookup.get(candidate, {})
        in_core = candidate in core_ids if candidate else False

        plan_row = dict(row)
        plan_row.update(
            {
                "iupac_motif_compatible": str(iupac_compatible).lower(),
                "corrected_match_class": corrected_match,
                "corrected_action": corrected_action,
                "candidate_priority_tier": metadata.get(
                    "priority_tier", ""
                ),
                "candidate_primary_region": metadata.get(
                    "primary_region", ""
                ),
                "candidate_static_pilot_include": metadata.get(
                    "static_pilot_include", ""
                ),
                "candidate_currently_in_core": str(in_core).lower(),
            }
        )
        plan_rows.append(plan_row)

        summary[f"action::{corrected_action}"] += 1
        summary[f"match::{corrected_match}"] += 1

        if corrected_action.startswith(
            "FORCE_MATCHED_TREXPLORER_LOCUS"
        ):
            target_rows.append(
                {
                    "strchive_id": row["strchive_id"],
                    "gene": row["gene"],
                    "trexplorer_locus_id": candidate,
                    "trexplorer_motif": candidate_motif,
                    "priority_tier_before_override": metadata.get(
                        "priority_tier", ""
                    ),
                    "primary_region": metadata.get(
                        "primary_region", ""
                    ),
                    "currently_in_static_core": str(in_core).lower(),
                    "override_action": corrected_action,
                }
            )

        if corrected_action == "ADD_EXTERNAL_FALLBACK":
            fallback_rows.append(
                {
                    "strchive_id": row["strchive_id"],
                    "gene": row["gene"],
                    "chrom": row["chrom"],
                    "start": row["start"],
                    "end": row["end"],
                    "reference_motif": row["reference_motif"],
                    "pathogenic_motif": row["pathogenic_motif"],
                    "disease": row["disease"],
                    "analysis_mode": "sequence_level_external_complex",
                    "reason": "no motif-compatible TRExplorer locus",
                }
            )

plan_header = list(plan_rows[0].keys())

with open(plan_path, "w", encoding="utf-8", newline="") as output:
    writer = csv.DictWriter(
        output,
        fieldnames=plan_header,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(plan_rows)

target_header = [
    "strchive_id",
    "gene",
    "trexplorer_locus_id",
    "trexplorer_motif",
    "priority_tier_before_override",
    "primary_region",
    "currently_in_static_core",
    "override_action",
]

with open(targets_path, "w", encoding="utf-8", newline="") as output:
    writer = csv.DictWriter(
        output,
        fieldnames=target_header,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(target_rows)

fallback_header = [
    "strchive_id",
    "gene",
    "chrom",
    "start",
    "end",
    "reference_motif",
    "pathogenic_motif",
    "disease",
    "analysis_mode",
    "reason",
]

with open(fallback_path, "w", encoding="utf-8", newline="") as output:
    writer = csv.DictWriter(
        output,
        fieldnames=fallback_header,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(fallback_rows)

forced_only_rows = []

with open(forced_audit_path, encoding="utf-8", newline="") as handle:
    reader = csv.DictReader(handle, delimiter="\t")

    for row in reader:
        if row["audit_class"] == "TREXPLORER_FORCED_ONLY":
            row["retention_decision"] = "RETAIN"
            row["retention_reason"] = (
                "TRExplorer disease source retained independently of STRchive"
            )
            forced_only_rows.append(row)

forced_header = list(forced_only_rows[0].keys()) if forced_only_rows else []

with open(
    forced_only_path,
    "w",
    encoding="utf-8",
    newline="",
) as output:
    if forced_header:
        writer = csv.DictWriter(
            output,
            fieldnames=forced_header,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(forced_only_rows)

summary["force_targets_total"] = len(target_rows)
summary["force_targets_already_in_core"] = sum(
    row["currently_in_static_core"] == "true"
    for row in target_rows
)
summary["force_targets_missing_from_core"] = sum(
    row["currently_in_static_core"] == "false"
    for row in target_rows
)
summary["external_fallback_loci"] = len(fallback_rows)
summary["trexplorer_forced_only_retained"] = len(forced_only_rows)

status = "PASS"

if (
    len(plan_rows) != 80
    or len(target_rows) != 9
    or len(fallback_rows) != 1
    or summary["action::ALREADY_FORCED"]
       + summary["action::ALREADY_FORCED_IUPAC"] != 70
):
    status = "REVIEW"

with open(summary_path, "w", encoding="utf-8") as output:
    output.write("metric\tvalue\n")
    output.write(f"strchive_loci\t{len(plan_rows)}\n")

    for key, value in sorted(summary.items()):
        output.write(f"{key}\t{value}\n")

    output.write(f"audit_status\t{status}\n")

if status != "PASS":
    raise SystemExit("Corrected disease override plan requires review")
PY

python "$PYTHON_SCRIPT" \
  "$CONCORDANCE" \
  "$FORCED_AUDIT" \
  "$PRIORITY" \
  "$CORE" \
  "$PLAN" \
  "$TARGETS" \
  "$FALLBACK" \
  "$FORCED_ONLY" \
  "$SUMMARY"

echo "===== CORRECTED OVERRIDE SUMMARY ====="
column -ts $'\t' "$SUMMARY"

echo
echo "===== NINE TREXPLORER FORCE TARGETS ====="
column -ts $'\t' "$TARGETS"

echo
echo "===== EXTERNAL FALLBACK ====="
column -ts $'\t' "$FALLBACK"

echo
echo "===== COMPLETE ====="
echo "$PLAN"
echo "$TARGETS"
echo "$FALLBACK"
echo "$FORCED_ONLY"
echo "$SUMMARY"
