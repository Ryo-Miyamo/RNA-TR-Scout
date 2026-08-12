"""Pure P3 orientation and block-to-target geometry rules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .sequence import reverse_complement

AlignmentStrand = Literal["+", "-"]
TargetSide = Literal["GENOMIC_LEFT", "GENOMIC_RIGHT"]
OrientationTransform = Literal[
    "AS_RAW",
    "REVERSE_COMPLEMENT",
]


@dataclass(frozen=True)
class CandidateReferenceGeometry:
    """Reference interval spanning block edge to target entry."""

    fetch_start: int
    fetch_end: int
    reverse_complement_after_fetch: bool
    bridge_bp: int
    target_entry_bp: int
    required_target_entry_bp: int

    @property
    def reference_bp(self) -> int:
        return self.fetch_end - self.fetch_start


def expected_orientation_transform(
    alignment_strand: AlignmentStrand,
    target_side: TargetSide,
) -> OrientationTransform:
    """Return how a raw target-facing clip must be oriented.

    The resulting sequence always runs from the mapped-block boundary
    toward the candidate repeat target.
    """

    if alignment_strand not in {"+", "-"}:
        raise ValueError("alignment_strand must be '+' or '-'")

    if target_side not in {
        "GENOMIC_LEFT",
        "GENOMIC_RIGHT",
    }:
        raise ValueError(
            "target_side must be GENOMIC_LEFT or GENOMIC_RIGHT"
        )

    if (
        alignment_strand == "+"
        and target_side == "GENOMIC_RIGHT"
    ) or (
        alignment_strand == "-"
        and target_side == "GENOMIC_LEFT"
    ):
        return "AS_RAW"

    return "REVERSE_COMPLEMENT"


def orient_target_facing_clip(
    sequence: str,
    alignment_strand: AlignmentStrand,
    target_side: TargetSide,
) -> tuple[str, OrientationTransform]:
    """Orient raw clip from mapped-block boundary toward target."""

    transform = expected_orientation_transform(
        alignment_strand,
        target_side,
    )

    if transform == "AS_RAW":
        return sequence.upper(), transform

    return reverse_complement(sequence).upper(), transform


def candidate_reference_geometry(
    *,
    block_start: int,
    block_end: int,
    target_start: int,
    target_end: int,
    target_side: TargetSide,
    target_entry_bp: int = 60,
    minimum_target_entry_bp: int = 12,
) -> CandidateReferenceGeometry:
    """Build coordinates for ``bridge + target-entry`` reference.

    All genomic coordinates are 0-based, end-exclusive.
    """

    values = (
        block_start,
        block_end,
        target_start,
        target_end,
        target_entry_bp,
        minimum_target_entry_bp,
    )

    if any(value < 0 for value in values):
        raise ValueError("coordinates and lengths must be non-negative")

    if block_end < block_start:
        raise ValueError("block_end must be >= block_start")

    if target_end <= target_start:
        raise ValueError("target_end must be > target_start")

    if target_entry_bp <= 0:
        raise ValueError("target_entry_bp must be positive")

    if minimum_target_entry_bp <= 0:
        raise ValueError(
            "minimum_target_entry_bp must be positive"
        )

    target_length = target_end - target_start
    entry_bp = min(target_length, target_entry_bp)
    required_entry = min(
        target_length,
        minimum_target_entry_bp,
    )

    if target_side == "GENOMIC_RIGHT":
        bridge_bp = target_start - block_end

        if bridge_bp < 0:
            raise ValueError(
                "right-side target overlaps or lies behind block edge"
            )

        return CandidateReferenceGeometry(
            fetch_start=block_end,
            fetch_end=target_start + entry_bp,
            reverse_complement_after_fetch=False,
            bridge_bp=bridge_bp,
            target_entry_bp=entry_bp,
            required_target_entry_bp=required_entry,
        )

    if target_side == "GENOMIC_LEFT":
        bridge_bp = block_start - target_end

        if bridge_bp < 0:
            raise ValueError(
                "left-side target overlaps or lies behind block edge"
            )

        return CandidateReferenceGeometry(
            fetch_start=target_end - entry_bp,
            fetch_end=block_start,
            reverse_complement_after_fetch=True,
            bridge_bp=bridge_bp,
            target_entry_bp=entry_bp,
            required_target_entry_bp=required_entry,
        )

    raise ValueError(
        "target_side must be GENOMIC_LEFT or GENOMIC_RIGHT"
    )


def orient_candidate_reference(
    fetched_sequence: str,
    geometry: CandidateReferenceGeometry,
) -> str:
    """Orient fetched genomic sequence from block edge toward target."""

    if len(fetched_sequence) != geometry.reference_bp:
        raise ValueError(
            "fetched sequence length does not match geometry"
        )

    if geometry.reverse_complement_after_fetch:
        return reverse_complement(fetched_sequence).upper()

    return fetched_sequence.upper()
