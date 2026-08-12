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
        if (
            selected_decision.bridge_status
            == "ORIENTATION_INCONSISTENT_BRIDGE"
        ):
            projection_status = (
                "UNEXPECTED_REVERSE_ALIGNMENT"
            )
        else:
            projection_status = (
                "TARGET_ENTRY_NOT_PROJECTED"
            )

        return PairAlignmentProjection(
            alignment_count=len(pair_alignments),
            selected_alignment=selected_alignment,
            bridge_decision=selected_decision,
            target_entry_query_offset=None,
            target_entry_projection_status=(
                projection_status
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
