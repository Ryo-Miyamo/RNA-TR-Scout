"""Pure P3 bridge and one-flank evidence rules.

P3 means that a mapped alignment block stops before a repeat target
and the target-facing raw-read sequence is examined for a bridge into
the target. This module deliberately does not perform alignment or
repeat scanning. It converts validated observations into guarded
evidence classifications.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

TargetSide = Literal["GENOMIC_LEFT", "GENOMIC_RIGHT"]


@dataclass(frozen=True)
class P3Observation:
    """Validated inputs required for the P3 decision layer."""

    alignment_strand: str
    target_entry_projected: bool
    canonical_motif: str
    target_facing_genomic_side: TargetSide
    tract_bp: int | None
    tract_reaches_expected_raw_end: bool


@dataclass(frozen=True)
class P3Decision:
    """Schema-oriented P3 result with mandatory sizing guardrails."""

    primary_status: str
    standard_evidence_emitted: bool
    evidence_class: str
    sizing_status: str
    failure_code: str
    repeat_bp_estimate: float | None
    repeat_bp_lower_bound: float | None
    allele_length_status: str
    expansion_status: str
    notes: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _validate_observation(observation: P3Observation) -> None:
    if observation.alignment_strand not in {"+", "-"}:
        raise ValueError(
            "alignment_strand must be '+' or '-'"
        )

    if observation.target_facing_genomic_side not in {
        "GENOMIC_LEFT",
        "GENOMIC_RIGHT",
    }:
        raise ValueError(
            "target_facing_genomic_side must be "
            "GENOMIC_LEFT or GENOMIC_RIGHT"
        )

    motif = observation.canonical_motif.upper()

    if not motif or any(base not in "ACGT" for base in motif):
        raise ValueError(
            "canonical_motif must contain only A/C/G/T"
        )

    if observation.tract_bp is not None and observation.tract_bp < 0:
        raise ValueError("tract_bp must be non-negative")


def classify_p3(observation: P3Observation) -> P3Decision:
    """Apply frozen P3 v0.3.2 decision rules.

    Rule priority:
      1. Orientation
      2. Target-entry projection
      3. Homopolymer routing
      4. Repeat-tract availability
      5. Censored versus internal one-flank evidence

    Exact allele length and expansion status are intentionally
    unavailable for every P3 result.
    """

    _validate_observation(observation)
    motif = observation.canonical_motif.upper()

    common = {
        "repeat_bp_estimate": None,
        "allele_length_status": "NOT_MEASURABLE_ONE_FLANK_P3",
        "expansion_status": "NOT_ASSESSED",
    }

    if observation.alignment_strand != "+":
        return P3Decision(
            primary_status="REJECT_ORIENTATION_INCONSISTENT_BRIDGE",
            standard_evidence_emitted=False,
            evidence_class="UNRESOLVED",
            sizing_status="no_call",
            failure_code="ORIENTATION_INCONSISTENT_BRIDGE",
            repeat_bp_lower_bound=None,
            notes=(
                "Query and candidate reference were normalized from "
                "mapped-block boundary toward target, but only "
                "reverse-orientation compatibility was observed."
            ),
            **common,
        )

    if not observation.target_entry_projected:
        return P3Decision(
            primary_status="REJECT_TARGET_ENTRY_NOT_PROJECTED",
            standard_evidence_emitted=False,
            evidence_class="UNRESOLVED",
            sizing_status="no_call",
            failure_code="TARGET_ENTRY_NOT_PROJECTED",
            repeat_bp_lower_bound=None,
            notes=(
                "A plus-orientation bridge was not sufficient to "
                "project the target-entry query coordinate through "
                "a validated CIGAR."
            ),
            **common,
        )

    if len(motif) == 1:
        return P3Decision(
            primary_status=(
                "HOMOPOLYMER_REVIEW_NO_STANDARD_P3_EVIDENCE"
            ),
            standard_evidence_emitted=False,
            evidence_class="UNRESOLVED",
            sizing_status="no_call",
            failure_code="HOMOPOLYMER_REVIEW",
            repeat_bp_lower_bound=None,
            notes=(
                "Mononucleotide A/T-like signal is routed to "
                "dedicated homopolymer or poly(A)/poly(T) review."
            ),
            **common,
        )

    if observation.tract_bp is None or observation.tract_bp == 0:
        return P3Decision(
            primary_status=(
                "ORIENTATION_VALID_BRIDGE_ONLY_NO_REPEAT_TRACT"
            ),
            standard_evidence_emitted=False,
            evidence_class="UNRESOLVED",
            sizing_status="no_call",
            failure_code="REPEAT_NOT_FOUND",
            repeat_bp_lower_bound=None,
            notes=(
                "The bridge and target entry are supported, but no "
                "qualifying target-entry repeat tract was measured."
            ),
            **common,
        )

    if observation.tract_reaches_expected_raw_end:
        if observation.target_facing_genomic_side == "GENOMIC_RIGHT":
            evidence_class = "LEFT_ANCHORED_CENSORED_RIGHT"
        else:
            evidence_class = "RIGHT_ANCHORED_CENSORED_LEFT"

        return P3Decision(
            primary_status="P3_CENSORED_LOWER_BOUND",
            standard_evidence_emitted=True,
            evidence_class=evidence_class,
            sizing_status="lower_bound",
            failure_code="NONE",
            repeat_bp_lower_bound=float(observation.tract_bp),
            notes=(
                "One validated genomic flank and a target-entry "
                "repeat tract reaching the expected raw-read end "
                "support a censored lower bound only."
            ),
            **common,
        )

    if observation.target_facing_genomic_side == "GENOMIC_RIGHT":
        evidence_class = "LEFT_ONLY_INTERNAL"
    else:
        evidence_class = "RIGHT_ONLY_INTERNAL"

    return P3Decision(
        primary_status="P3_PARTIAL_INTERNAL",
        standard_evidence_emitted=True,
        evidence_class=evidence_class,
        sizing_status="partial_internal",
        failure_code="NONE",
        repeat_bp_lower_bound=None,
        notes=(
            "One validated genomic flank and an internal "
            "target-entry repeat tract support partial_internal; "
            "neither exact size nor lower bound is emitted."
        ),
        **common,
    )
