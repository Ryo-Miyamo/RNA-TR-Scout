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

PACKAGE_DIR="$PROJECT_ROOT/src/rnatr_scout"
UNIT_DIR="$PROJECT_ROOT/tests/unit"

PAIR_META="$PROJECT_ROOT/results/11_p3_bridge_feasibility/$RUN_ID/p3_bridge_pair_metadata.tsv.gz"
QUERY_FASTA="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_p3_bridge_feasibility/p3_bridge_queries.fasta.gz"
REFERENCE_FASTA="$RAW_ROOT/benchmarks/ENCSR307SHM/pilot_100k_seed20260803/rnatr_p3_bridge_feasibility/p3_bridge_candidate_references.fasta.gz"
SIZING="$PROJECT_ROOT/results/11_p3_target_entry_sizing/$RUN_ID/p3_target_entry_repeat_evidence.tsv"

OUTDIR="$PROJECT_ROOT/results/11_production_p3_pair_projection/$RUN_ID"
QCDIR="$PROJECT_ROOT/qc/11_production_p3_pair_projection/$RUN_ID"
WORKDIR="$PROJECT_ROOT/tmp/11_production_p3_pair_projection/$RUN_ID"

REPLAY="$OUTDIR/p3_pair_alignment_projection_replay.tsv"
QC="$QCDIR/p3_pair_alignment_projection_core.qc.tsv"
UNIT_LOG="$OUTDIR/unit_tests.log"
MANIFEST="$OUTDIR/${RUN_ID}.production_p3_pair_projection.manifest.tsv"

STAGE="$WORKDIR/stage"
STAGE_PACKAGE="$STAGE/rnatr_scout"
STAGE_TESTS="$STAGE/tests"

mkdir -p "$OUTDIR" "$QCDIR" "$WORKDIR"

for path in \
  "$PACKAGE_DIR" \
  "$UNIT_DIR" \
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

for path in \
  "$PACKAGE_DIR/fasta.py" \
  "$PACKAGE_DIR/paf.py" \
  "$PACKAGE_DIR/p3_pair.py" \
  "$UNIT_DIR/test_fasta.py" \
  "$UNIT_DIR/test_paf.py" \
  "$UNIT_DIR/test_p3_pair.py"
do
    if [[ -e "$path" ]]; then
        echo "ERROR: target already exists: $path" >&2
        exit 1
    fi
done

command -v minimap2 >/dev/null 2>&1 || {
    echo "ERROR: minimap2 is unavailable" >&2
    exit 1
}

installed_version="$(rnatr-scout version)"

if [[ "$installed_version" != "$PACKAGE_VERSION" ]]; then
    echo "ERROR: unexpected installed version: $installed_version" >&2
    exit 1
fi

rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -a "$PACKAGE_DIR" "$STAGE_PACKAGE"
cp -a "$UNIT_DIR" "$STAGE_TESTS"

cat > "$STAGE_PACKAGE/fasta.py" <<'PY'
"""Minimal FASTA readers without third-party dependencies."""

from __future__ import annotations

import gzip
from pathlib import Path
from typing import Iterator, TextIO


def _open_text(path: Path) -> TextIO:
    if path.suffix == ".gz":
        return gzip.open(
            path,
            "rt",
            encoding="utf-8",
        )

    return path.open(
        "r",
        encoding="utf-8",
    )


def iter_fasta(
    path: str | Path,
) -> Iterator[tuple[str, str]]:
    """Yield ``(record_id, sequence)`` from FASTA or FASTA.gz."""

    path = Path(path)
    record_id: str | None = None
    sequence_parts: list[str] = []

    with _open_text(path) as handle:
        for line_number, line in enumerate(
            handle,
            start=1,
        ):
            line = line.strip()

            if not line:
                continue

            if line.startswith(">"):
                if record_id is not None:
                    yield (
                        record_id,
                        "".join(sequence_parts).upper(),
                    )

                record_id = line[1:].split()[0]

                if not record_id:
                    raise ValueError(
                        f"empty FASTA ID at line {line_number}"
                    )

                sequence_parts = []
                continue

            if record_id is None:
                raise ValueError(
                    "FASTA sequence observed before first header"
                )

            sequence_parts.append(line)

    if record_id is not None:
        yield (
            record_id,
            "".join(sequence_parts).upper(),
        )


def load_fasta(
    path: str | Path,
) -> dict[str, str]:
    """Load FASTA records and reject duplicate identifiers."""

    records: dict[str, str] = {}

    for record_id, sequence in iter_fasta(path):
        if record_id in records:
            raise ValueError(
                f"duplicate FASTA record ID: {record_id}"
            )

        records[record_id] = sequence

    return records


def fetch_fasta_record(
    path: str | Path,
    record_id: str,
) -> str:
    """Fetch one FASTA record by exact identifier."""

    found: str | None = None

    for observed_id, sequence in iter_fasta(path):
        if observed_id != record_id:
            continue

        if found is not None:
            raise ValueError(
                f"duplicate FASTA record ID: {record_id}"
            )

        found = sequence

    if found is None:
        raise KeyError(
            f"FASTA record not found: {record_id}"
        )

    return found
PY

cat > "$STAGE_PACKAGE/paf.py" <<'PY'
"""PAF parsing for minimap2 candidate-pair alignments."""

from __future__ import annotations

from dataclasses import dataclass


def _parse_tags(
    fields: list[str],
) -> dict[str, object]:
    tags: dict[str, object] = {}

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


@dataclass(frozen=True)
class PafAlignment:
    query_name: str
    query_length: int
    query_start: int
    query_end: int
    strand: str
    target_name: str
    target_length: int
    target_start: int
    target_end: int
    residue_matches: int
    alignment_block_length: int
    mapq: int
    tags: dict[str, object]

    @property
    def identity(self) -> float:
        if self.alignment_block_length == 0:
            return 0.0

        return (
            self.residue_matches
            / self.alignment_block_length
        )

    @property
    def query_coverage(self) -> float:
        if self.query_length == 0:
            return 0.0

        return (
            self.query_end - self.query_start
        ) / self.query_length

    @property
    def alignment_score(self) -> int:
        value = self.tags.get(
            "AS",
            self.residue_matches,
        )
        return int(value)

    @property
    def cigar(self) -> str | None:
        value = self.tags.get("cg")

        if value is None:
            return None

        return str(value)


def parse_paf_line(line: str) -> PafAlignment:
    """Parse one non-empty PAF line."""

    fields = line.rstrip("\n").split("\t")

    if len(fields) < 12:
        raise ValueError(
            "PAF line has fewer than 12 fields"
        )

    strand = fields[4]

    if strand not in {"+", "-"}:
        raise ValueError(
            f"invalid PAF strand: {strand!r}"
        )

    alignment = PafAlignment(
        query_name=fields[0],
        query_length=int(fields[1]),
        query_start=int(fields[2]),
        query_end=int(fields[3]),
        strand=strand,
        target_name=fields[5],
        target_length=int(fields[6]),
        target_start=int(fields[7]),
        target_end=int(fields[8]),
        residue_matches=int(fields[9]),
        alignment_block_length=int(fields[10]),
        mapq=int(fields[11]),
        tags=_parse_tags(fields[12:]),
    )

    coordinates = (
        alignment.query_length,
        alignment.query_start,
        alignment.query_end,
        alignment.target_length,
        alignment.target_start,
        alignment.target_end,
        alignment.residue_matches,
        alignment.alignment_block_length,
        alignment.mapq,
    )

    if any(value < 0 for value in coordinates):
        raise ValueError(
            "PAF coordinates and counts must be non-negative"
        )

    if not (
        alignment.query_start
        <= alignment.query_end
        <= alignment.query_length
    ):
        raise ValueError(
            "invalid PAF query interval"
        )

    if not (
        alignment.target_start
        <= alignment.target_end
        <= alignment.target_length
    ):
        raise ValueError(
            "invalid PAF target interval"
        )

    return alignment


def parse_paf(text: str) -> list[PafAlignment]:
    """Parse all non-empty PAF lines."""

    return [
        parse_paf_line(line)
        for line in text.splitlines()
        if line.strip()
    ]
PY

cat > "$STAGE_PACKAGE/p3_pair.py" <<'PY'
"""Isolated P3 candidate-pair alignment and target-entry projection."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import subprocess
import tempfile

from .cigar import (
    BoundaryProjection,
    project_reference_boundary_to_query,
)
from .p3_bridge import (
    BridgeAlignmentDecision,
    BridgeAlignmentObservation,
    evaluate_bridge_alignment,
)
from .paf import PafAlignment, parse_paf


@dataclass(frozen=True)
class PairAlignmentProjection:
    """Selected alignment, bridge decision, and entry projection."""

    alignment_count: int
    selected_alignment: PafAlignment | None
    bridge_decision: BridgeAlignmentDecision
    target_entry_query_offset: int | None
    target_entry_projection_status: str
    target_entry_projection_detail: str

    def to_dict(self) -> dict[str, object]:
        selected = self.selected_alignment

        return {
            "alignment_count": self.alignment_count,
            "selected_query_name": (
                selected.query_name
                if selected is not None
                else None
            ),
            "selected_target_name": (
                selected.target_name
                if selected is not None
                else None
            ),
            "selected_strand": (
                selected.strand
                if selected is not None
                else None
            ),
            "selected_query_start": (
                selected.query_start
                if selected is not None
                else None
            ),
            "selected_query_end": (
                selected.query_end
                if selected is not None
                else None
            ),
            "selected_target_start": (
                selected.target_start
                if selected is not None
                else None
            ),
            "selected_target_end": (
                selected.target_end
                if selected is not None
                else None
            ),
            "selected_identity": (
                selected.identity
                if selected is not None
                else None
            ),
            "selected_query_coverage": (
                selected.query_coverage
                if selected is not None
                else None
            ),
            "selected_alignment_score": (
                selected.alignment_score
                if selected is not None
                else None
            ),
            "selected_cigar": (
                selected.cigar
                if selected is not None
                else None
            ),
            "bridge_decision": (
                self.bridge_decision.to_dict()
            ),
            "target_entry_query_offset": (
                self.target_entry_query_offset
            ),
            "target_entry_projection_status": (
                self.target_entry_projection_status
            ),
            "target_entry_projection_detail": (
                self.target_entry_projection_detail
            ),
        }


def _alignment_rank(
    alignment: PafAlignment,
) -> tuple[int, int, float, float, int]:
    return (
        alignment.alignment_score,
        alignment.residue_matches,
        alignment.query_coverage,
        alignment.identity,
        alignment.mapq,
    )


def _decision_priority(
    decision: BridgeAlignmentDecision,
    alignment: PafAlignment,
) -> tuple[int, tuple[int, int, float, float, int]]:
    if decision.bridge_valid:
        priority = 6
    elif alignment.strand == "+":
        priorities = {
            "BRIDGE_STOPS_BEFORE_TARGET_ENTRY": 5,
            "LOW_QUALITY_BRIDGE_ALIGNMENT": 4,
            "ALIGNMENT_NOT_CONNECTED_TO_BLOCK_BOUNDARY": 3,
        }
        priority = priorities.get(
            decision.bridge_status,
            2,
        )
    else:
        priority = 1

    return (
        priority,
        _alignment_rank(alignment),
    )


def evaluate_pair_alignments(
    alignments: list[PafAlignment],
    *,
    expected_query_name: str,
    expected_target_name: str,
    bridge_bp: int,
    target_entry_bp: int,
    query_can_reach_target_entry: bool,
    minimum_target_entry_bp: int = 12,
    boundary_tolerance_bp: int = 10,
    minimum_identity: float = 0.70,
    minimum_query_coverage: float = 0.70,
) -> PairAlignmentProjection:
    """Select the best biologically valid normalized pair alignment."""

    pair_alignments = [
        alignment
        for alignment in alignments
        if (
            alignment.query_name
            == expected_query_name
            and alignment.target_name
            == expected_target_name
        )
    ]

    if not pair_alignments:
        decision = evaluate_bridge_alignment(
            BridgeAlignmentObservation(
                alignment_present=False,
                alignment_strand=None,
                query_start=None,
                reference_start=None,
                query_coverage=None,
                identity=None,
                reference_end=None,
                bridge_bp=bridge_bp,
                target_entry_bp=target_entry_bp,
                query_can_reach_target_entry=(
                    query_can_reach_target_entry
                ),
            ),
            minimum_target_entry_bp=(
                minimum_target_entry_bp
            ),
            boundary_tolerance_bp=(
                boundary_tolerance_bp
            ),
            minimum_identity=minimum_identity,
            minimum_query_coverage=(
                minimum_query_coverage
            ),
        )

        return PairAlignmentProjection(
            alignment_count=0,
            selected_alignment=None,
            bridge_decision=decision,
            target_entry_query_offset=None,
            target_entry_projection_status=(
                "TARGET_ENTRY_NOT_PROJECTED"
            ),
            target_entry_projection_detail=(
                "NO_PAIR_ALIGNMENT"
            ),
        )

    evaluated: list[
        tuple[PafAlignment, BridgeAlignmentDecision]
    ] = []

    for alignment in pair_alignments:
        decision = evaluate_bridge_alignment(
            BridgeAlignmentObservation(
                alignment_present=True,
                alignment_strand=alignment.strand,
                query_start=alignment.query_start,
                reference_start=alignment.target_start,
                query_coverage=alignment.query_coverage,
                identity=alignment.identity,
                reference_end=alignment.target_end,
                bridge_bp=bridge_bp,
                target_entry_bp=target_entry_bp,
                query_can_reach_target_entry=(
                    query_can_reach_target_entry
                ),
            ),
            minimum_target_entry_bp=(
                minimum_target_entry_bp
            ),
            boundary_tolerance_bp=(
                boundary_tolerance_bp
            ),
            minimum_identity=minimum_identity,
            minimum_query_coverage=(
                minimum_query_coverage
            ),
        )
        evaluated.append(
            (
                alignment,
                decision,
            )
        )

    selected_alignment, selected_decision = max(
        evaluated,
        key=lambda item: _decision_priority(
            item[1],
            item[0],
        ),
    )

    if not selected_decision.bridge_valid:
        return PairAlignmentProjection(
            alignment_count=len(pair_alignments),
            selected_alignment=selected_alignment,
            bridge_decision=selected_decision,
            target_entry_query_offset=None,
            target_entry_projection_status=(
                "TARGET_ENTRY_NOT_PROJECTED"
            ),
            target_entry_projection_detail=(
                "BRIDGE_INVALID:"
                + selected_decision.bridge_status
            ),
        )

    cigar = selected_alignment.cigar

    if cigar is None:
        return PairAlignmentProjection(
            alignment_count=len(pair_alignments),
            selected_alignment=selected_alignment,
            bridge_decision=selected_decision,
            target_entry_query_offset=None,
            target_entry_projection_status=(
                "TARGET_ENTRY_NOT_PROJECTED"
            ),
            target_entry_projection_detail=(
                "CIGAR_MISSING"
            ),
        )

    projection: BoundaryProjection = (
        project_reference_boundary_to_query(
            query_start=selected_alignment.query_start,
            reference_start=selected_alignment.target_start,
            cigar=cigar,
            reference_boundary=bridge_bp,
        )
    )

    projected = (
        projection.query_offset is not None
        and projection.status.startswith(
            "PROJECTED_"
        )
    )

    return PairAlignmentProjection(
        alignment_count=len(pair_alignments),
        selected_alignment=selected_alignment,
        bridge_decision=selected_decision,
        target_entry_query_offset=(
            projection.query_offset
        ),
        target_entry_projection_status=(
            "TARGET_ENTRY_PROJECTED"
            if projected
            else "TARGET_ENTRY_NOT_PROJECTED"
        ),
        target_entry_projection_detail=(
            projection.status
        ),
    )


def run_isolated_pair_alignment(
    *,
    query_name: str,
    query_sequence: str,
    target_name: str,
    target_sequence: str,
    bridge_bp: int,
    target_entry_bp: int,
    query_can_reach_target_entry: bool,
    minimap2_executable: str = "minimap2",
    minimum_target_entry_bp: int = 12,
    boundary_tolerance_bp: int = 10,
    minimum_identity: float = 0.70,
    minimum_query_coverage: float = 0.70,
) -> PairAlignmentProjection:
    """Run minimap2 on exactly one query and one candidate reference."""

    if not query_name or not target_name:
        raise ValueError(
            "query_name and target_name must be non-empty"
        )

    if not query_sequence or not target_sequence:
        raise ValueError(
            "query_sequence and target_sequence must be non-empty"
        )

    with tempfile.TemporaryDirectory(
        prefix="rnatr_p3_pair_"
    ) as directory_text:
        directory = Path(directory_text)
        query_path = directory / "query.fa"
        target_path = directory / "target.fa"

        query_path.write_text(
            f">{query_name}\n{query_sequence}\n",
            encoding="utf-8",
        )
        target_path.write_text(
            f">{target_name}\n{target_sequence}\n",
            encoding="utf-8",
        )

        command = [
            minimap2_executable,
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
            "--cs=long",
            "--secondary=yes",
            "-t1",
            str(target_path),
            str(query_path),
        ]

        completed = subprocess.run(
            command,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        if completed.returncode != 0:
            raise RuntimeError(
                "minimap2 failed with exit code "
                f"{completed.returncode}: "
                f"{completed.stderr.strip()}"
            )

    alignments = parse_paf(completed.stdout)

    return evaluate_pair_alignments(
        alignments,
        expected_query_name=query_name,
        expected_target_name=target_name,
        bridge_bp=bridge_bp,
        target_entry_bp=target_entry_bp,
        query_can_reach_target_entry=(
            query_can_reach_target_entry
        ),
        minimum_target_entry_bp=(
            minimum_target_entry_bp
        ),
        boundary_tolerance_bp=(
            boundary_tolerance_bp
        ),
        minimum_identity=minimum_identity,
        minimum_query_coverage=(
            minimum_query_coverage
        ),
    )
PY

cat > "$STAGE_TESTS/test_fasta.py" <<'PY'
from __future__ import annotations

import gzip
import tempfile
import unittest
from pathlib import Path

from rnatr_scout.fasta import (
    fetch_fasta_record,
    load_fasta,
)


class TestFasta(unittest.TestCase):
    def test_load_plain_fasta(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.fa"
            path.write_text(
                ">a comment\nAC\nGT\n>b\nTT\n",
                encoding="utf-8",
            )
            self.assertEqual(
                load_fasta(path),
                {
                    "a": "ACGT",
                    "b": "TT",
                },
            )

    def test_fetch_gzip_fasta(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.fa.gz"

            with gzip.open(
                path,
                "wt",
                encoding="utf-8",
            ) as handle:
                handle.write(">a\nACGT\n")

            self.assertEqual(
                fetch_fasta_record(path, "a"),
                "ACGT",
            )

    def test_duplicate_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.fa"
            path.write_text(
                ">a\nAC\n>a\nGT\n",
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                load_fasta(path)


if __name__ == "__main__":
    unittest.main()
PY

cat > "$STAGE_TESTS/test_paf.py" <<'PY'
from __future__ import annotations

import unittest

from rnatr_scout.paf import parse_paf_line


class TestPaf(unittest.TestCase):
    def test_parse_paf_line(self):
        alignment = parse_paf_line(
            "q\t20\t0\t18\t+\tt\t30\t0\t18\t"
            "17\t18\t60\tAS:i:42\tcg:Z:18M"
        )
        self.assertEqual(
            alignment.query_name,
            "q",
        )
        self.assertEqual(
            alignment.target_name,
            "t",
        )
        self.assertEqual(
            alignment.alignment_score,
            42,
        )
        self.assertEqual(
            alignment.cigar,
            "18M",
        )
        self.assertAlmostEqual(
            alignment.identity,
            17 / 18,
        )
        self.assertAlmostEqual(
            alignment.query_coverage,
            18 / 20,
        )

    def test_short_row_rejected(self):
        with self.assertRaises(ValueError):
            parse_paf_line("q\t1")


if __name__ == "__main__":
    unittest.main()
PY

cat > "$STAGE_TESTS/test_p3_pair.py" <<'PY'
from __future__ import annotations

import unittest

from rnatr_scout.p3_pair import (
    evaluate_pair_alignments,
)
from rnatr_scout.paf import parse_paf


class TestP3Pair(unittest.TestCase):
    def test_valid_plus_alignment_selected(self):
        alignments = parse_paf(
            "q\t30\t0\t25\t-\tt\t30\t0\t25\t"
            "25\t25\t60\tAS:i:60\tcg:Z:25M\n"
            "q\t30\t0\t22\t+\tt\t30\t0\t22\t"
            "21\t22\t40\tAS:i:50\tcg:Z:22M\n"
        )
        result = evaluate_pair_alignments(
            alignments,
            expected_query_name="q",
            expected_target_name="t",
            bridge_bp=7,
            target_entry_bp=20,
            query_can_reach_target_entry=True,
        )
        self.assertTrue(
            result.bridge_decision.bridge_valid
        )
        self.assertEqual(
            result.selected_alignment.strand,
            "+",
        )
        self.assertEqual(
            result.target_entry_query_offset,
            7,
        )

    def test_reverse_only_rejected(self):
        alignments = parse_paf(
            "q\t30\t0\t25\t-\tt\t30\t0\t25\t"
            "25\t25\t60\tAS:i:60\tcg:Z:25M\n"
        )
        result = evaluate_pair_alignments(
            alignments,
            expected_query_name="q",
            expected_target_name="t",
            bridge_bp=7,
            target_entry_bp=20,
            query_can_reach_target_entry=True,
        )
        self.assertEqual(
            result.bridge_decision.bridge_status,
            "ORIENTATION_INCONSISTENT_BRIDGE",
        )
        self.assertEqual(
            result.target_entry_projection_status,
            "TARGET_ENTRY_NOT_PROJECTED",
        )

    def test_missing_cigar_prevents_projection(self):
        alignments = parse_paf(
            "q\t30\t0\t25\t+\tt\t30\t0\t25\t"
            "25\t25\t60\tAS:i:60\n"
        )
        result = evaluate_pair_alignments(
            alignments,
            expected_query_name="q",
            expected_target_name="t",
            bridge_bp=7,
            target_entry_bp=20,
            query_can_reach_target_entry=True,
        )
        self.assertTrue(
            result.bridge_decision.bridge_valid
        )
        self.assertEqual(
            result.target_entry_projection_detail,
            "CIGAR_MISSING",
        )

    def test_no_pair_alignment(self):
        result = evaluate_pair_alignments(
            [],
            expected_query_name="q",
            expected_target_name="t",
            bridge_bp=7,
            target_entry_bp=20,
            query_can_reach_target_entry=True,
        )
        self.assertEqual(
            result.bridge_decision.bridge_status,
            "NO_CANDIDATE_ALIGNMENT",
        )


if __name__ == "__main__":
    unittest.main()
PY

python - "$STAGE_PACKAGE/cli.py" <<'PYPATCH'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

import_anchor = (
    "from .p3_bridge import (\n"
    "    BridgeAlignmentObservation,\n"
    "    evaluate_bridge_alignment,\n"
    ")\n"
)
import_replacement = (
    import_anchor
    + "from .fasta import fetch_fasta_record\n"
      "from .p3_pair import run_isolated_pair_alignment\n"
)

if import_anchor not in text:
    raise SystemExit(
        "CLI import anchor not found"
    )

text = text.replace(
    import_anchor,
    import_replacement,
    1,
)

parser_anchor = (
    "    contract_parser = subparsers.add_parser(\n"
    "        \"contract-check\",\n"
)
parser_block = """    pair_parser = subparsers.add_parser(
        "p3-align-project-pair",
        help=(
            "Run isolated minimap2 alignment, validate the bridge, "
            "and project the target entry"
        ),
    )
    pair_parser.add_argument(
        "--query-fasta",
        required=True,
    )
    pair_parser.add_argument(
        "--query-id",
        required=True,
    )
    pair_parser.add_argument(
        "--reference-fasta",
        required=True,
    )
    pair_parser.add_argument(
        "--reference-id",
        required=True,
    )
    pair_parser.add_argument(
        "--bridge-bp",
        required=True,
        type=int,
    )
    pair_parser.add_argument(
        "--target-entry-bp",
        required=True,
        type=int,
    )
    pair_parser.add_argument(
        "--query-can-reach-target-entry",
        required=True,
        type=_boolean,
    )

"""

if parser_anchor not in text:
    raise SystemExit(
        "CLI parser anchor not found"
    )

text = text.replace(
    parser_anchor,
    parser_block + parser_anchor,
    1,
)

handler_anchor = (
    "    if arguments.command == \"contract-check\":\n"
)
handler_block = """    if arguments.command == "p3-align-project-pair":
        query_sequence = fetch_fasta_record(
            arguments.query_fasta,
            arguments.query_id,
        )
        reference_sequence = fetch_fasta_record(
            arguments.reference_fasta,
            arguments.reference_id,
        )
        result = run_isolated_pair_alignment(
            query_name=arguments.query_id,
            query_sequence=query_sequence,
            target_name=arguments.reference_id,
            target_sequence=reference_sequence,
            bridge_bp=arguments.bridge_bp,
            target_entry_bp=arguments.target_entry_bp,
            query_can_reach_target_entry=(
                arguments.query_can_reach_target_entry
            ),
        )
        print(
            json.dumps(
                result.to_dict(),
                sort_keys=True,
            )
        )
        return 0

"""

if handler_anchor not in text:
    raise SystemExit(
        "CLI handler anchor not found"
    )

text = text.replace(
    handler_anchor,
    handler_block + handler_anchor,
    1,
)

path.write_text(text, encoding="utf-8")
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
BACKUP="$PROJECT_ROOT/metadata/code_backups/11ar_${timestamp}"
mkdir -p "$BACKUP"

cp "$PACKAGE_DIR/cli.py" "$BACKUP/cli.py"
cp -a "$UNIT_DIR" "$BACKUP/unit_tests"

cp "$STAGE_PACKAGE/fasta.py" \
  "$PACKAGE_DIR/fasta.py"
cp "$STAGE_PACKAGE/paf.py" \
  "$PACKAGE_DIR/paf.py"
cp "$STAGE_PACKAGE/p3_pair.py" \
  "$PACKAGE_DIR/p3_pair.py"
cp "$STAGE_PACKAGE/cli.py" \
  "$PACKAGE_DIR/cli.py"

cp "$STAGE_TESTS/test_fasta.py" \
  "$UNIT_DIR/test_fasta.py"
cp "$STAGE_TESTS/test_paf.py" \
  "$UNIT_DIR/test_paf.py"
cp "$STAGE_TESTS/test_p3_pair.py" \
  "$UNIT_DIR/test_p3_pair.py"

echo
echo "===== INSTALLED PACKAGE UNIT TESTS ====="
RNATR_PROJECT_ROOT="$PROJECT_ROOT" \
python -m unittest discover \
  -s "$UNIT_DIR" \
  -v

echo
echo "===== REPLAY 23 ISOLATED PAIRS WITH PRODUCTION CODE ====="

python - \
  "$PAIR_META" \
  "$QUERY_FASTA" \
  "$REFERENCE_FASTA" \
  "$SIZING" \
  "$REPLAY" \
  "$QC" <<'PYREPLAY'
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
        csv.DictReader(handle, delimiter="\t")
    )

results = []
missing_inputs = 0
bridge_status_counts = Counter()
projection_status_counts = Counter()
query_offset_mismatches = 0

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

    selected = result.selected_alignment

    results.append(
        {
            "projection_id": projection_id,
            "read_id": sizing["read_id"],
            "target_region_id": sizing[
                "target_region_id"
            ],
            "reference_id": reference_id,
            "alignment_count": result.alignment_count,
            "selected_strand": (
                selected.strand
                if selected is not None
                else "."
            ),
            "selected_query_start": (
                selected.query_start
                if selected is not None
                else "."
            ),
            "selected_reference_start": (
                selected.target_start
                if selected is not None
                else "."
            ),
            "selected_reference_end": (
                selected.target_end
                if selected is not None
                else "."
            ),
            "selected_identity": (
                "{:.6f}".format(
                    selected.identity
                )
                if selected is not None
                else "."
            ),
            "selected_query_coverage": (
                "{:.6f}".format(
                    selected.query_coverage
                )
                if selected is not None
                else "."
            ),
            "selected_cigar": (
                selected.cigar
                if (
                    selected is not None
                    and selected.cigar is not None
                )
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
            "expected_projection_status": sizing[
                "target_entry_projection_status"
            ],
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
projection_status_mismatches = sum(
    row["production_projection_status"]
    != row["expected_projection_status"]
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
        "TARGET_ENTRY_PROJECTED"
    ] != 1
    or projection_status_counts[
        "TARGET_ENTRY_NOT_PROJECTED"
    ] != 22
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
        "pair_projection_core_status\t{}\n".format(
            status
        )
    )

if status != "PASS":
    raise SystemExit(
        "Production pair alignment/projection replay requires review"
    )
PYREPLAY

echo
echo "===== INSTALLED CLI HELP ====="
rnatr-scout p3-align-project-pair --help

{
    printf 'artifact\tdata_rows\tbytes\tsha256\tpath\n'

    for path in \
      "$PACKAGE_DIR/fasta.py" \
      "$PACKAGE_DIR/paf.py" \
      "$PACKAGE_DIR/p3_pair.py" \
      "$PACKAGE_DIR/cli.py" \
      "$UNIT_DIR/test_fasta.py" \
      "$UNIT_DIR/test_paf.py" \
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
echo "===== REPLAY ====="
column -ts $'\t' "$REPLAY"

echo
echo "===== MANIFEST ====="
column -ts $'\t' "$MANIFEST"

echo
echo "===== BACKUP ====="
echo "$BACKUP"
