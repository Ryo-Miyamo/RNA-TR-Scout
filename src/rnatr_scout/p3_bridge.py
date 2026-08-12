"""Production validation of candidate P3 bridge alignments."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class BridgeAlignmentObservation:
    """Minimal alignment data needed for P3 bridge validation."""

    alignment_present: bool
    alignment_strand: str | None
    query_start: int | None
    reference_start: int | None
    query_coverage: float | None
    identity: float | None
    reference_end: int | None
    bridge_bp: int
    target_entry_bp: int
    query_can_reach_target_entry: bool


@dataclass(frozen=True)
class BridgeAlignmentDecision:
    """Guarded interpretation of one candidate bridge alignment."""

    bridge_status: str
    bridge_valid: bool
    required_reference_end: int
    orientation_consistent: bool
    boundary_connected: bool
    quality_pass: bool
    target_entry_reached: bool
    notes: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _validate_observation(
    observation: BridgeAlignmentObservation,
) -> None:
    if observation.bridge_bp < 0:
        raise ValueError("bridge_bp must be non-negative")

    if observation.target_entry_bp <= 0:
        raise ValueError(
            "target_entry_bp must be positive"
        )

    optional_nonnegative = (
        observation.query_start,
        observation.reference_start,
        observation.reference_end,
    )

    if any(
        value is not None and value < 0
        for value in optional_nonnegative
    ):
        raise ValueError(
            "alignment coordinates must be non-negative"
        )

    for name, value in (
        ("query_coverage", observation.query_coverage),
        ("identity", observation.identity),
    ):
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValueError(
                f"{name} must be between 0 and 1"
            )

    if (
        observation.alignment_strand is not None
        and observation.alignment_strand not in {"+", "-"}
    ):
        raise ValueError(
            "alignment_strand must be '+', '-', or None"
        )


def evaluate_bridge_alignment(
    observation: BridgeAlignmentObservation,
    *,
    minimum_target_entry_bp: int = 12,
    boundary_tolerance_bp: int = 10,
    minimum_identity: float = 0.70,
    minimum_query_coverage: float = 0.70,
) -> BridgeAlignmentDecision:
    """Evaluate whether a normalized alignment proves a P3 bridge.

    Query and candidate reference must both run from the mapped-block
    boundary toward the target. Therefore a valid bridge requires a
    plus-orientation alignment.
    """

    _validate_observation(observation)

    if minimum_target_entry_bp <= 0:
        raise ValueError(
            "minimum_target_entry_bp must be positive"
        )

    if boundary_tolerance_bp < 0:
        raise ValueError(
            "boundary_tolerance_bp must be non-negative"
        )

    if not 0.0 <= minimum_identity <= 1.0:
        raise ValueError(
            "minimum_identity must be between 0 and 1"
        )

    if not 0.0 <= minimum_query_coverage <= 1.0:
        raise ValueError(
            "minimum_query_coverage must be between 0 and 1"
        )

    required_reference_end = (
        observation.bridge_bp
        + min(
            observation.target_entry_bp,
            minimum_target_entry_bp,
        )
    )

    defaults = {
        "required_reference_end": required_reference_end,
        "orientation_consistent": False,
        "boundary_connected": False,
        "quality_pass": False,
        "target_entry_reached": False,
    }

    if not observation.query_can_reach_target_entry:
        return BridgeAlignmentDecision(
            bridge_status=(
                "QUERY_TOO_SHORT_TO_REACH_TARGET"
            ),
            bridge_valid=False,
            notes=(
                "The target-facing query is shorter than the "
                "bridge plus required target-entry support."
            ),
            **defaults,
        )

    if not observation.alignment_present:
        return BridgeAlignmentDecision(
            bridge_status="NO_CANDIDATE_ALIGNMENT",
            bridge_valid=False,
            notes=(
                "No candidate-reference alignment was available."
            ),
            **defaults,
        )

    required_fields = {
        "alignment_strand":
            observation.alignment_strand,
        "query_start": observation.query_start,
        "reference_start": observation.reference_start,
        "query_coverage": observation.query_coverage,
        "identity": observation.identity,
        "reference_end": observation.reference_end,
    }
    missing = [
        name
        for name, value in required_fields.items()
        if value is None
    ]

    if missing:
        raise ValueError(
            "alignment_present is true but fields are missing: "
            + ",".join(missing)
        )

    orientation_consistent = (
        observation.alignment_strand == "+"
    )

    if not orientation_consistent:
        return BridgeAlignmentDecision(
            bridge_status=(
                "ORIENTATION_INCONSISTENT_BRIDGE"
            ),
            bridge_valid=False,
            orientation_consistent=False,
            boundary_connected=False,
            quality_pass=False,
            target_entry_reached=False,
            required_reference_end=(
                required_reference_end
            ),
            notes=(
                "Query and candidate reference were normalized "
                "toward the target, but alignment was reverse."
            ),
        )

    boundary_connected = (
        observation.query_start
        <= boundary_tolerance_bp
        and observation.reference_start
        <= boundary_tolerance_bp
    )

    if not boundary_connected:
        return BridgeAlignmentDecision(
            bridge_status=(
                "ALIGNMENT_NOT_CONNECTED_TO_BLOCK_BOUNDARY"
            ),
            bridge_valid=False,
            orientation_consistent=True,
            boundary_connected=False,
            quality_pass=False,
            target_entry_reached=False,
            required_reference_end=(
                required_reference_end
            ),
            notes=(
                "Alignment does not begin near both normalized "
                "block-boundary sequence starts."
            ),
        )

    quality_pass = (
        observation.identity >= minimum_identity
        and observation.query_coverage
        >= minimum_query_coverage
    )

    if not quality_pass:
        return BridgeAlignmentDecision(
            bridge_status=(
                "LOW_QUALITY_BRIDGE_ALIGNMENT"
            ),
            bridge_valid=False,
            orientation_consistent=True,
            boundary_connected=True,
            quality_pass=False,
            target_entry_reached=False,
            required_reference_end=(
                required_reference_end
            ),
            notes=(
                "Boundary-connected alignment does not satisfy "
                "identity and query-coverage thresholds."
            ),
        )

    target_entry_reached = (
        observation.reference_end
        >= required_reference_end
    )

    if not target_entry_reached:
        return BridgeAlignmentDecision(
            bridge_status=(
                "BRIDGE_STOPS_BEFORE_TARGET_ENTRY"
            ),
            bridge_valid=False,
            orientation_consistent=True,
            boundary_connected=True,
            quality_pass=True,
            target_entry_reached=False,
            required_reference_end=(
                required_reference_end
            ),
            notes=(
                "Alignment supports the bridge but does not reach "
                "the required number of target-entry bases."
            ),
        )

    return BridgeAlignmentDecision(
        bridge_status="BRIDGE_REACHES_TARGET_ENTRY",
        bridge_valid=True,
        orientation_consistent=True,
        boundary_connected=True,
        quality_pass=True,
        target_entry_reached=True,
        required_reference_end=required_reference_end,
        notes=(
            "Plus-orientation, boundary-connected, quality-passing "
            "alignment reaches the required target entry."
        ),
    )
