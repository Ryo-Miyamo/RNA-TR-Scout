#!/usr/bin/env bash
set -euo pipefail

if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
fi

conda activate rnatr-v03
source /mnt/intelssd/rnatr_project/config/paths.env
cd "$PROJECT_ROOT"

RUN_ID="ENCSR307SHM_pilot100k_mm2splice_v1"

OLD_SCHEMA="$PROJECT_ROOT/config/evidence_schema/v0.3.1"
NEW_SCHEMA="$PROJECT_ROOT/config/evidence_schema/v0.3.2"

OLD_FIXTURE="$PROJECT_ROOT/tests/regression/v0.3.1"
NEW_FIXTURE="$PROJECT_ROOT/tests/regression/v0.3.2"

FROZEN_CLASSIFICATION="$PROJECT_ROOT/results/11_p3_orientation_freeze/$RUN_ID/p3_orientation_corrected_classification.tsv"
SIZING="$PROJECT_ROOT/results/11_p3_target_entry_sizing/$RUN_ID/p3_target_entry_repeat_evidence.tsv"
PAIR_META="$PROJECT_ROOT/results/11_p3_bridge_feasibility/$RUN_ID/p3_bridge_pair_metadata.tsv.gz"
CANDIDATE_FASTQ="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_candidates_v0.3.1/ENCFF260PGB.pilot_100k.rnatr_candidate_all.fastq.gz"

OUTDIR="$PROJECT_ROOT/results/11_schema_regression_v032/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_schema_regression_v032/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_schema_regression_v032/$RUN_ID"
REGRESSION_QCDIR="$PROJECT_ROOT/qc/11_regression_fixture/$RUN_ID/v0.3.2"

QC="$QCDIR/schema_regression_v0.3.2.qc.tsv"
SELECTED="$OUTDIR/p3_regression_cases_selected.tsv"
SUMMARY="$OUTDIR/schema_regression_v0.3.2.summary.tsv"
MANIFEST="$OUTDIR/${RUN_ID}.schema_regression_v0.3.2.manifest.tsv"
PY="$WORKDIR/create_schema_and_regression_v032.py"

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR" "$REGRESSION_QCDIR"

for path in \
  "$OLD_SCHEMA" \
  "$OLD_FIXTURE" \
  "$FROZEN_CLASSIFICATION" \
  "$SIZING" \
  "$PAIR_META" \
  "$CANDIDATE_FASTQ"
do
    test -e "$path" || {
        echo "ERROR: missing required path: $path" >&2
        exit 1
    }
done

if [[ -e "$NEW_SCHEMA" || -e "$NEW_FIXTURE" ]]; then
    echo "ERROR: v0.3.2 output already exists." >&2
    echo "Remove it only after reviewing its contents, then rerun." >&2
    echo "  $NEW_SCHEMA" >&2
    echo "  $NEW_FIXTURE" >&2
    exit 1
fi

SCHEMA_STAGE="$WORKDIR/evidence_schema.v0.3.2.stage"
FIXTURE_STAGE="$WORKDIR/regression.v0.3.2.stage"

rm -rf "$SCHEMA_STAGE" "$FIXTURE_STAGE"
cp -a "$OLD_SCHEMA" "$SCHEMA_STAGE"
cp -a "$OLD_FIXTURE" "$FIXTURE_STAGE"

cat > "$PY" <<'PY'
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

import pysam

(
    schema_stage_text,
    fixture_stage_text,
    frozen_classification_text,
    sizing_text,
    pair_meta_text,
    candidate_fastq_text,
    selected_path_text,
    regression_qc_path_text,
    qc_path_text,
    summary_path_text,
) = sys.argv[1:]

SCHEMA_STAGE = Path(schema_stage_text)
FIXTURE_STAGE = Path(fixture_stage_text)
FROZEN_CLASSIFICATION = Path(
    frozen_classification_text
)
SIZING = Path(sizing_text)
PAIR_META = Path(pair_meta_text)
CANDIDATE_FASTQ = Path(candidate_fastq_text)
SELECTED = Path(selected_path_text)
REGRESSION_QC = Path(regression_qc_path_text)
QC = Path(qc_path_text)
SUMMARY = Path(summary_path_text)

OLD_VERSION = "v0.3.1"
OLD_NUMERIC_VERSION = "0.3.1"
NEW_VERSION = "v0.3.2"
NEW_NUMERIC_VERSION = "0.3.2"

NEW_FAILURE_CODES = {
    "ORIENTATION_INCONSISTENT_BRIDGE":
        "P3 query and candidate reference were normalized "
        "from mapped-block boundary toward target, but only "
        "reverse-orientation sequence compatibility was found.",
    "TARGET_ENTRY_NOT_PROJECTED":
        "A validated plus-orientation bridge did not project "
        "the target-entry boundary through its CIGAR.",
    "HOMOPOLYMER_REVIEW":
        "Mononucleotide A/T tract routed outside the standard "
        "P3 tandem-repeat evidence stream.",
}


def read_tsv(path: Path):
    with path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        return list(
            csv.DictReader(handle, delimiter="\t")
        )


def read_tsv_gz(path: Path):
    with gzip.open(
        path,
        "rt",
        encoding="utf-8",
        newline="",
    ) as handle:
        return list(
            csv.DictReader(handle, delimiter="\t")
        )


def write_tsv(path: Path, rows, fields):
    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path):
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)

            if not block:
                break

            digest.update(block)

    return digest.hexdigest()


def replace_version_fields(value):
    if isinstance(value, dict):
        updated = {}

        for key, child in value.items():
            if (
                key in {
                    "schema_version",
                    "version",
                }
                and child
                == OLD_NUMERIC_VERSION
            ):
                updated[key] = NEW_NUMERIC_VERSION
            else:
                updated[key] = replace_version_fields(
                    child
                )

        return updated

    if isinstance(value, list):
        return [
            replace_version_fields(child)
            for child in value
        ]

    return value


# ---------------------------------------------------------------------
# Schema v0.3.2
# ---------------------------------------------------------------------

schema_version_path = (
    SCHEMA_STAGE / "SCHEMA_VERSION"
)
schema_version_path.write_text(
    NEW_NUMERIC_VERSION + "\n",
    encoding="utf-8",
)

enums_path = (
    SCHEMA_STAGE
    / "dictionaries"
    / "rnatr_v03_enums.tsv"
)
enum_rows = read_tsv(enums_path)
enum_fields = [
    "enum_name",
    "allowed_value",
    "meaning",
]

existing_failure_codes = {
    row["allowed_value"]
    for row in enum_rows
    if row["enum_name"] == "failure_code"
}

for code, meaning in NEW_FAILURE_CODES.items():
    if code not in existing_failure_codes:
        enum_rows.append(
            {
                "enum_name": "failure_code",
                "allowed_value": code,
                "meaning": meaning,
            }
        )

write_tsv(
    enums_path,
    enum_rows,
    enum_fields,
)

json_schema_path = (
    SCHEMA_STAGE
    / "schema"
    / "rnatr_v03_table_schema.json"
)
schema_object = json.loads(
    json_schema_path.read_text(
        encoding="utf-8"
    )
)
schema_object = replace_version_fields(
    schema_object
)

failure_enum = schema_object[
    "enums"
]["failure_code"]

for code in NEW_FAILURE_CODES:
    if code not in failure_enum:
        failure_enum.append(code)

json_schema_path.write_text(
    json.dumps(
        schema_object,
        ensure_ascii=False,
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)

patch_doc = SCHEMA_STAGE / "SCHEMA_PATCH_0.3.2.md"
patch_doc.write_text(
    """# RNA-TR-Scout evidence schema patch 0.3.2

Schema 0.3.2 is a minimal P3 integration patch.

## Added failure codes

- `ORIENTATION_INCONSISTENT_BRIDGE`
- `TARGET_ENTRY_NOT_PROJECTED`
- `HOMOPOLYMER_REVIEW`

## No new table columns

P3 evidence uses the existing fields and enums:

- `LEFT_ANCHORED_CENSORED_RIGHT`
- `RIGHT_ANCHORED_CENSORED_LEFT`
- `LEFT_ONLY_INTERNAL`
- `RIGHT_ONLY_INTERNAL`
- `lower_bound`
- `partial_internal`
- `no_call`

Bridge method details remain in `call_method`, `call_flags`,
`qc_flags`, `failure_code`, and `notes`.

## Guardrails

- Require query/reference normalization from mapped-block
  boundary toward target.
- Require a plus-orientation bridge.
- Require target-entry CIGAR projection before repeat sizing.
- Route mononucleotide A/T tracts to homopolymer review.
- Never emit exact allele length from one-flank P3 evidence.
- Never emit expansion or pathogenicity from P3 evidence alone.
""",
    encoding="utf-8",
)

readme_path = SCHEMA_STAGE / "README.md"
with readme_path.open(
    "a",
    encoding="utf-8",
) as handle:
    handle.write(
        "\n\n## Patch 0.3.2\n\n"
        "Minimal P3 integration adds orientation, target-entry, "
        "and homopolymer failure codes without changing table "
        "columns. See `SCHEMA_PATCH_0.3.2.md`.\n"
    )

manifest_path = SCHEMA_STAGE / "MANIFEST.sha256"
if manifest_path.exists():
    manifest_path.unlink()

schema_manifest_lines = []

for path in sorted(
    item
    for item in SCHEMA_STAGE.rglob("*")
    if item.is_file()
):
    relative = path.relative_to(
        SCHEMA_STAGE
    )
    schema_manifest_lines.append(
        "{}  {}".format(
            sha256(path),
            relative,
        )
    )

manifest_path.write_text(
    "\n".join(schema_manifest_lines)
    + "\n",
    encoding="utf-8",
)

# ---------------------------------------------------------------------
# Regression fixture v0.3.2
# ---------------------------------------------------------------------

frozen_rows = read_tsv(
    FROZEN_CLASSIFICATION
)
sizing_lookup = {
    row["projection_id"]: row
    for row in read_tsv(SIZING)
}
pair_meta_lookup = {
    row["projection_id"]: row
    for row in read_tsv_gz(PAIR_META)
}

orientation_candidates = [
    row
    for row in frozen_rows
    if row["frozen_p3_status"]
       == "REJECT_ORIENTATION_INCONSISTENT_BRIDGE"
]
homopolymer_candidates = [
    row
    for row in frozen_rows
    if row["frozen_p3_status"]
       == "HOMOPOLYMER_REVIEW_NO_STANDARD_P3_EVIDENCE"
]

if not orientation_candidates:
    raise RuntimeError(
        "No orientation-inconsistent P3 candidate"
    )

if len(homopolymer_candidates) != 1:
    raise RuntimeError(
        "Expected one P3 homopolymer candidate"
    )

orientation_row = sorted(
    orientation_candidates,
    key=lambda row: (
        row["target_region_id"],
        row["projection_id"],
    ),
)[0]
homopolymer_row = homopolymer_candidates[0]

selected_rows = [
    {
        "selection_role":
            "P3_ORIENTATION_NEGATIVE",
        **orientation_row,
    },
    {
        "selection_role":
            "P3_HOMOPOLYMER_NEGATIVE",
        **homopolymer_row,
    },
]

write_tsv(
    SELECTED,
    selected_rows,
    list(selected_rows[0].keys()),
)

cases_path = (
    FIXTURE_STAGE / "regression_cases.tsv"
)
case_rows = read_tsv(cases_path)
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

for row in case_rows:
    row["fixture_version"] = NEW_VERSION

existing_case_ids = {
    row["case_id"]
    for row in case_rows
}

if {
    "RC019",
    "RC020",
} & existing_case_ids:
    raise RuntimeError(
        "RC019 or RC020 already exists"
    )


def build_orientation_case(row):
    projection_id = row["projection_id"]
    sizing = sizing_lookup[projection_id]
    pair_meta = pair_meta_lookup[projection_id]

    return {
        "fixture_version": NEW_VERSION,
        "case_id": "RC019",
        "category":
            "P3_ORIENTATION_INCONSISTENT_BRIDGE",
        "source_artifact": str(
            FROZEN_CLASSIFICATION
        ),
        "source_key": projection_id,
        "read_id": row["read_id"],
        "target_region_id":
            row["target_region_id"],
        "representative_locus_id":
            pair_meta.get(
                "representative_locus_id",
                ".",
            ),
        "canonical_motif":
            row["canonical_motif"],
        "raw_interval_start":
            sizing["raw_clip_start"],
        "raw_interval_end":
            sizing["raw_clip_end"],
        "observed_bp":
            sizing["raw_clip_bp"],
        "source_evidence_class":
            row["original_evidence_class"],
        "source_sizing_status":
            row["original_sizing_status"],
        "expected_primary_class":
            "REJECT_ORIENTATION_INCONSISTENT_BRIDGE",
        "expected_sizing_status":
            "no_call",
        "expected_guardrail":
            "After query and reference are normalized from "
            "mapped-block boundary toward target, reverse-only "
            "compatibility cannot establish a P3 bridge.",
        "rationale":
            "P3 negative control for the strand-orientation "
            "false-positive mode discovered in pilot calibration.",
    }


def build_homopolymer_case(row):
    projection_id = row["projection_id"]
    sizing = sizing_lookup[projection_id]
    pair_meta = pair_meta_lookup[projection_id]

    raw_start = sizing["tract_raw_start"]
    raw_end = sizing["tract_raw_end"]
    observed_bp = sizing["tract_bp"]

    if raw_start == "." or raw_end == ".":
        raw_start = sizing["raw_clip_start"]
        raw_end = sizing["raw_clip_end"]
        observed_bp = sizing["raw_clip_bp"]

    return {
        "fixture_version": NEW_VERSION,
        "case_id": "RC020",
        "category":
            "P3_HOMOPOLYMER_REVIEW",
        "source_artifact": str(
            FROZEN_CLASSIFICATION
        ),
        "source_key": projection_id,
        "read_id": row["read_id"],
        "target_region_id":
            row["target_region_id"],
        "representative_locus_id":
            pair_meta.get(
                "representative_locus_id",
                ".",
            ),
        "canonical_motif":
            row["canonical_motif"],
        "raw_interval_start": raw_start,
        "raw_interval_end": raw_end,
        "observed_bp": observed_bp,
        "source_evidence_class":
            row["original_evidence_class"],
        "source_sizing_status":
            row["original_sizing_status"],
        "expected_primary_class":
            "HOMOPOLYMER_REVIEW_NO_STANDARD_P3_EVIDENCE",
        "expected_sizing_status":
            "no_call",
        "expected_guardrail":
            "A plus-orientation target-entry tract with motif "
            "length one is routed to poly(A)/poly(T) or "
            "homopolymer review, not standard P3 evidence.",
        "rationale":
            "P3 negative control preventing mononucleotide "
            "RNA/cDNA low-complexity signal from entering the "
            "standard tandem-repeat evidence stream.",
    }


case_rows.extend(
    [
        build_orientation_case(
            orientation_row
        ),
        build_homopolymer_case(
            homopolymer_row
        ),
    ]
)

write_tsv(
    cases_path,
    case_rows,
    case_fields,
)

rules_path = (
    FIXTURE_STAGE / "decision_rules.tsv"
)
rule_rows = read_tsv(rules_path)
rule_fields = [
    "rule_id",
    "rule_name",
    "condition",
    "required_action",
    "guardrail",
]

existing_rule_ids = {
    row["rule_id"]
    for row in rule_rows
}

new_rules = [
    {
        "rule_id": "R014",
        "rule_name": "P3_ORIENTATION",
        "condition":
            "Query and candidate reference are normalized from "
            "mapped-block boundary toward target",
        "required_action":
            "Require a plus-orientation bridge and reject "
            "reverse-only sequence compatibility",
        "guardrail":
            "Reverse complement similarity does not prove "
            "continuous anchor-to-target geometry",
    },
    {
        "rule_id": "R015",
        "rule_name": "P3_TARGET_ENTRY",
        "condition":
            "A plus-orientation P3 bridge is proposed",
        "required_action":
            "Project the target-entry boundary through a "
            "validated CIGAR before repeat sizing",
        "guardrail":
            "Bridge compatibility alone does not identify the "
            "query coordinate at which the target begins",
    },
    {
        "rule_id": "R016",
        "rule_name": "P3_HOMOPOLYMER",
        "condition":
            "The catalog motif length is one base",
        "required_action":
            "Route to dedicated poly(A)/poly(T) or homopolymer "
            "review and emit no standard P3 evidence",
        "guardrail":
            "RNA/cDNA homopolymer signal may reflect poly(A), "
            "internal priming, low complexity, or sequencing error",
    },
]

for rule in new_rules:
    if rule["rule_id"] in existing_rule_ids:
        raise RuntimeError(
            "{} already exists".format(
                rule["rule_id"]
            )
        )

rule_rows.extend(new_rules)

write_tsv(
    rules_path,
    rule_rows,
    rule_fields,
)

old_fastq = (
    FIXTURE_STAGE
    / "data"
    / "regression_reads.fastq.gz"
)
temporary_fastq = (
    FIXTURE_STAGE
    / "data"
    / "regression_reads.fastq.gz.tmp"
)

existing_records = {}
existing_order = []

with pysam.FastxFile(str(old_fastq)) as source:
    for entry in source:
        if entry.name in existing_records:
            raise RuntimeError(
                "Duplicate existing regression read: {}".format(
                    entry.name
                )
            )

        existing_records[entry.name] = (
            entry.comment,
            entry.sequence,
            entry.quality,
        )
        existing_order.append(entry.name)

required_new_read_ids = {
    orientation_row["read_id"],
    homopolymer_row["read_id"],
}
missing_new_read_ids = (
    required_new_read_ids
    - set(existing_records)
)
new_records = {}

with pysam.FastxFile(
    str(CANDIDATE_FASTQ)
) as source:
    for entry in source:
        if entry.name not in missing_new_read_ids:
            continue

        new_records[entry.name] = (
            entry.comment,
            entry.sequence,
            entry.quality,
        )

if set(new_records) != missing_new_read_ids:
    missing = sorted(
        missing_new_read_ids
        - set(new_records)
    )
    raise RuntimeError(
        "Missing selected P3 reads in candidate FASTQ: {}".format(
            ",".join(missing)
        )
    )

with gzip.open(
    temporary_fastq,
    "wt",
    encoding="utf-8",
) as handle:
    for read_id in existing_order + sorted(
        new_records
    ):
        comment, sequence, quality = (
            existing_records.get(read_id)
            or new_records[read_id]
        )
        header = "@{}".format(read_id)

        if comment:
            header += " " + comment

        handle.write(header + "\n")
        handle.write(sequence + "\n")
        handle.write("+\n")
        handle.write(quality + "\n")

temporary_fastq.replace(old_fastq)

fixture_read_ids = []
with pysam.FastxFile(str(old_fastq)) as source:
    for entry in source:
        fixture_read_ids.append(entry.name)

case_read_ids = {
    row["read_id"]
    for row in case_rows
}
missing_case_reads = (
    case_read_ids - set(fixture_read_ids)
)

readme_path = FIXTURE_STAGE / "README.md"
readme_path.write_text(
    """# RNA-TR-Scout regression fixture v0.3.2

This fixture freezes edge cases discovered during the
ENCSR307SHM 100k-read pilot. It is a software regression set,
not a disease or expansion truth set.

- Cases: {cases}
- Unique raw reads: {reads}
- Decision rules: {rules}
- Missing raw reads: {missing}

Version 0.3.2 adds two P3 negative controls:

- reverse-orientation bridge compatibility
- plus-orientation mononucleotide homopolymer review

Every future caller revision must preserve the expected
classification and sizing guardrail for these cases, unless the
fixture version is deliberately updated.
""".format(
        cases=len(case_rows),
        reads=len(set(fixture_read_ids)),
        rules=len(rule_rows),
        missing=len(missing_case_reads),
    ),
    encoding="utf-8",
)

# ---------------------------------------------------------------------
# Integrity validation
# ---------------------------------------------------------------------

schema_json = json.loads(
    json_schema_path.read_text(
        encoding="utf-8"
    )
)
json_failure_codes = set(
    schema_json["enums"]["failure_code"]
)
tsv_failure_codes = {
    row["allowed_value"]
    for row in read_tsv(enums_path)
    if row["enum_name"] == "failure_code"
}

schema_enum_match = (
    json_failure_codes == tsv_failure_codes
)
new_failure_codes_present = (
    set(NEW_FAILURE_CODES)
    <= json_failure_codes
)

template_mismatches = 0
dictionary_mismatches = 0

for table_name, table_spec in schema_json[
    "tables"
].items():
    expected_columns = [
        column["name"]
        for column in table_spec["columns"]
    ]

    dictionary_path = (
        SCHEMA_STAGE
        / "dictionaries"
        / "{}.columns.tsv".format(
            table_name
        )
    )
    dictionary_rows = read_tsv(
        dictionary_path
    )
    dictionary_rows.sort(
        key=lambda row: int(
            row["column_order"]
        )
    )
    dictionary_columns = [
        row["column_name"]
        for row in dictionary_rows
    ]

    with (
        SCHEMA_STAGE
        / "templates"
        / "{}.tsv".format(
            table_name
        )
    ).open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        template_columns = next(
            csv.reader(
                handle,
                delimiter="\t",
            )
        )

    if dictionary_columns != expected_columns:
        dictionary_mismatches += 1

    if template_columns != expected_columns:
        template_mismatches += 1

case_width_failures = 0
with cases_path.open(
    "r",
    encoding="utf-8",
    newline="",
) as handle:
    raw_case_rows = list(
        csv.reader(handle, delimiter="\t")
    )

for row in raw_case_rows:
    if len(row) != len(case_fields):
        case_width_failures += 1

rule_width_failures = 0
with rules_path.open(
    "r",
    encoding="utf-8",
    newline="",
) as handle:
    raw_rule_rows = list(
        csv.reader(handle, delimiter="\t")
    )

for row in raw_rule_rows:
    if len(row) != len(rule_fields):
        rule_width_failures += 1

selected_case_ids = {
    row["case_id"]
    for row in case_rows
    if row["case_id"] in {
        "RC019",
        "RC020",
    }
}

integrity_status = "PASS"

if (
    not schema_enum_match
    or not new_failure_codes_present
    or dictionary_mismatches
    or template_mismatches
    or len(case_rows) != 20
    or len(rule_rows) != 16
    or selected_case_ids
       != {"RC019", "RC020"}
    or case_width_failures
    or rule_width_failures
    or missing_case_reads
):
    integrity_status = "REVIEW"

with REGRESSION_QC.open(
    "w",
    encoding="utf-8",
) as handle:
    handle.write("metric\tvalue\n")
    handle.write(
        "fixture_version\t{}\n".format(
            NEW_VERSION
        )
    )
    handle.write(
        "regression_cases\t{}\n".format(
            len(case_rows)
        )
    )
    handle.write(
        "unique_case_ids\t{}\n".format(
            len(
                {
                    row["case_id"]
                    for row in case_rows
                }
            )
        )
    )
    handle.write(
        "decision_rules\t{}\n".format(
            len(rule_rows)
        )
    )
    handle.write(
        "unique_fastq_reads\t{}\n".format(
            len(set(fixture_read_ids))
        )
    )
    handle.write(
        "missing_case_reads\t{}\n".format(
            len(missing_case_reads)
        )
    )
    handle.write(
        "p3_regression_cases\t2\n"
    )
    handle.write(
        "fixture_status\t{}\n".format(
            integrity_status
        )
    )

fixture_manifest_path = (
    FIXTURE_STAGE
    / "regression_fixture.manifest.tsv"
)

fixture_artifacts = [
    (
        "regression_cases.tsv",
        cases_path,
        len(case_rows),
    ),
    (
        "decision_rules.tsv",
        rules_path,
        len(rule_rows),
    ),
    (
        "regression_fixture.qc.tsv",
        REGRESSION_QC,
        8,
    ),
    (
        "regression_reads.fastq.gz",
        old_fastq,
        len(set(fixture_read_ids)),
    ),
    (
        "README.md",
        readme_path,
        ".",
    ),
]

with fixture_manifest_path.open(
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
            "artifact",
            "data_rows",
            "bytes",
            "sha256",
            "path",
        ]
    )

    for artifact, path, data_rows in (
        fixture_artifacts
    ):
        writer.writerow(
            [
                artifact,
                data_rows,
                path.stat().st_size,
                sha256(path),
                str(path),
            ]
        )

summary_rows = [
    ("schema_version", NEW_NUMERIC_VERSION),
    (
        "schema_failure_code_count",
        len(json_failure_codes),
    ),
    (
        "new_p3_failure_codes",
        len(NEW_FAILURE_CODES),
    ),
    (
        "schema_enum_match",
        str(schema_enum_match).lower(),
    ),
    (
        "dictionary_mismatch_tables",
        dictionary_mismatches,
    ),
    (
        "template_mismatch_tables",
        template_mismatches,
    ),
    ("regression_cases", len(case_rows)),
    ("decision_rules", len(rule_rows)),
    (
        "unique_regression_reads",
        len(set(fixture_read_ids)),
    ),
    (
        "missing_case_reads",
        len(missing_case_reads),
    ),
    (
        "p3_cases_added",
        2,
    ),
    (
        "integration_status",
        integrity_status,
    ),
]

with SUMMARY.open(
    "w",
    encoding="utf-8",
    newline="",
) as handle:
    writer = csv.writer(
        handle,
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writerow(["metric", "value"])
    writer.writerows(summary_rows)

with QC.open(
    "w",
    encoding="utf-8",
) as handle:
    handle.write("metric\tvalue\n")

    for metric, value in summary_rows:
        handle.write(
            "{}\t{}\n".format(
                metric,
                value,
            )
        )

    handle.write(
        "case_width_failures\t{}\n".format(
            case_width_failures
        )
    )
    handle.write(
        "rule_width_failures\t{}\n".format(
            rule_width_failures
        )
    )

if integrity_status != "PASS":
    raise SystemExit(
        "Schema/regression v0.3.2 integration requires review"
    )
PY

python -m py_compile "$PY"

rm -f \
  "$QC" \
  "$SELECTED" \
  "$SUMMARY" \
  "$MANIFEST" \
  "$REGRESSION_QCDIR/regression_fixture.qc.tsv"

python "$PY" \
  "$SCHEMA_STAGE" \
  "$FIXTURE_STAGE" \
  "$FROZEN_CLASSIFICATION" \
  "$SIZING" \
  "$PAIR_META" \
  "$CANDIDATE_FASTQ" \
  "$SELECTED" \
  "$REGRESSION_QCDIR/regression_fixture.qc.tsv" \
  "$QC" \
  "$SUMMARY"

mv "$SCHEMA_STAGE" "$NEW_SCHEMA"
mv "$FIXTURE_STAGE" "$NEW_FIXTURE"

# Rewrite manifest paths from staging paths to final paths.
sed -i \
  "s|$FIXTURE_STAGE|$NEW_FIXTURE|g" \
  "$NEW_FIXTURE/regression_fixture.manifest.tsv"

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in \
      "$QC" \
      "$SELECTED" \
      "$SUMMARY" \
      "$REGRESSION_QCDIR/regression_fixture.qc.tsv"
    do
        printf '%s\t%s\t%s\t%s\t%s\n' \
          "$(basename "$path")" \
          "$(awk 'END {print NR-1}' "$path")" \
          "$(stat -c '%s' "$path")" \
          "$(sha256sum "$path" | awk '{print $1}')" \
          "$path"
    done

    printf '%s\t%s\t%s\t%s\t%s\n' \
      "evidence_schema_v0.3.2" \
      "." \
      "$(du -sb "$NEW_SCHEMA" | awk '{print $1}')" \
      "." \
      "$NEW_SCHEMA"

    printf '%s\t%s\t%s\t%s\t%s\n' \
      "regression_fixture_v0.3.2" \
      "." \
      "$(du -sb "$NEW_FIXTURE" | awk '{print $1}')" \
      "." \
      "$NEW_FIXTURE"
} > "$MANIFEST"

echo "===== QC ====="
column -ts $'\t' "$QC"

echo
echo "===== SELECTED P3 REGRESSION CASES ====="
column -ts $'\t' "$SELECTED"

echo
echo "===== REGRESSION FIXTURE QC ====="
column -ts $'\t' \
  "$REGRESSION_QCDIR/regression_fixture.qc.tsv"

echo
echo "===== NEW FAILURE CODES ====="
awk -F '\t' '
  NR == 1 {
    print
    next
  }
  $1 == "failure_code" &&
  (
    $2 == "ORIENTATION_INCONSISTENT_BRIDGE" ||
    $2 == "TARGET_ENTRY_NOT_PROJECTED" ||
    $2 == "HOMOPOLYMER_REVIEW"
  ) {
    print
  }
' \
  "$NEW_SCHEMA/dictionaries/rnatr_v03_enums.tsv" \
  | column -ts $'\t'

echo
echo "===== NEW REGRESSION CASES ====="
awk -F '\t' '
  NR == 1 || $2 == "RC019" || $2 == "RC020"
' \
  "$NEW_FIXTURE/regression_cases.tsv" \
  | column -ts $'\t'

echo
echo "===== NEW DECISION RULES ====="
awk -F '\t' '
  NR == 1 || $1 == "R014" || $1 == "R015" || $1 == "R016"
' \
  "$NEW_FIXTURE/decision_rules.tsv" \
  | column -ts $'\t'

echo
echo "===== MANIFEST ====="
column -ts $'\t' "$MANIFEST"
