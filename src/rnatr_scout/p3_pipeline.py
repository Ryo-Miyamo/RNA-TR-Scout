"""End-to-end production orchestration for one P3 candidate pair."""

from __future__ import annotations

from dataclasses import dataclass

from .p3 import (
    P3Decision,
    P3Observation,
    classify_p3,
)
from .p3_geometry import (
    OrientationTransform,
    orient_target_facing_clip,
)
from .p3_pair import (
    PairAlignmentProjection,
    run_isolated_pair_alignment,
)
from .p3_repeat import (
    RepeatMeasurement,
    measure_target_entry_repeat,
)


@dataclass(frozen=True)
class P3PipelineResult:
    """Integrated alignment, measurement, and guarded decision."""

    orientation_transform: OrientationTransform
    query_prefix_matches: bool
    pair_projection: PairAlignmentProjection
    repeat_measurement: RepeatMeasurement
    decision: P3Decision

    def to_dict(self) -> dict[str, object]:
        return {
            "orientation_transform":
                self.orientation_transform,
            "query_prefix_matches":
                self.query_prefix_matches,
            "pair_projection":
                self.pair_projection.to_dict(),
            "repeat_measurement":
                self.repeat_measurement.to_contract_dict(),
            "decision":
                self.decision.to_dict(),
        }


def run_p3_pipeline(
    *,
    query_name: str,
    query_sequence: str,
    target_name: str,
    target_sequence: str,
    raw_read_sequence: str,
    raw_clip_start: int,
    raw_clip_end: int,
    raw_alignment_strand: str,
    target_facing_genomic_side: str,
    canonical_motif: str,
    bridge_bp: int,
    target_entry_bp: int,
    query_can_reach_target_entry: bool,
    expected_orientation_transform: str | None = None,
    minimap2_executable: str = "minimap2",
) -> P3PipelineResult:
    """Run the production P3 path for one candidate.

    The result remains a sequence-evidence interpretation. Exact allele
    length, expansion status, DNA genotype, and pathogenicity are not
    inferred from a one-flank P3 observation.
    """

    if raw_clip_start < 0:
        raise ValueError(
            "raw_clip_start must be non-negative"
        )

    if raw_clip_end < raw_clip_start:
        raise ValueError(
            "raw_clip_end must be at least raw_clip_start"
        )

    if raw_clip_end > len(raw_read_sequence):
        raise ValueError(
            "raw clip interval exceeds raw read length"
        )

    raw_clip = raw_read_sequence[
        raw_clip_start:raw_clip_end
    ]
    (
        oriented_clip,
        orientation_transform,
    ) = orient_target_facing_clip(
        raw_clip,
        raw_alignment_strand,
        target_facing_genomic_side,
    )

    if (
        expected_orientation_transform is not None
        and orientation_transform
        != expected_orientation_transform
    ):
        raise ValueError(
            "computed orientation transform does not match "
            "the expected frozen transform"
        )

    query_prefix_matches = (
        oriented_clip[
            :len(query_sequence)
        ]
        == query_sequence.upper()
    )

    pair_projection = run_isolated_pair_alignment(
        query_name=query_name,
        query_sequence=query_sequence,
        target_name=target_name,
        target_sequence=target_sequence,
        bridge_bp=bridge_bp,
        target_entry_bp=target_entry_bp,
        query_can_reach_target_entry=(
            query_can_reach_target_entry
        ),
        minimap2_executable=minimap2_executable,
    )

    repeat_measurement = measure_target_entry_repeat(
        oriented_clip=oriented_clip,
        motif=canonical_motif,
        target_entry_query_offset=(
            pair_projection.target_entry_query_offset
        ),
        raw_clip_start=raw_clip_start,
        raw_clip_end=raw_clip_end,
        orientation_transform=orientation_transform,
        target_facing_genomic_side=(
            target_facing_genomic_side
        ),
        target_entry_projection_status=(
            pair_projection.target_entry_projection_status
        ),
        query_prefix_matches=query_prefix_matches,
    )

    selected_alignment = (
        pair_projection.selected_alignment
    )
    decision_alignment_strand = (
        selected_alignment.strand
        if selected_alignment is not None
        else "+"
    )

    decision = classify_p3(
        P3Observation(
            alignment_strand=(
                decision_alignment_strand
            ),
            target_entry_projected=(
                pair_projection.target_entry_projection_status
                == "TARGET_ENTRY_PROJECTED"
            ),
            canonical_motif=canonical_motif,
            target_facing_genomic_side=(
                target_facing_genomic_side
            ),
            tract_bp=repeat_measurement.tract_bp,
            tract_reaches_expected_raw_end=(
                repeat_measurement
                .tract_reaches_expected_raw_end
            ),
        )
    )

    return P3PipelineResult(
        orientation_transform=orientation_transform,
        query_prefix_matches=query_prefix_matches,
        pair_projection=pair_projection,
        repeat_measurement=repeat_measurement,
        decision=decision,
    )
