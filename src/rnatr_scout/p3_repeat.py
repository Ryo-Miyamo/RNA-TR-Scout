"""Explicit P3 repeat core copied from the validated 11af algorithm.

This validation module is deliberately handwritten and self-contained.
It contains no code extraction, no command-line parsing, and no top-level
pipeline side effects.
"""

from __future__ import annotations

from dataclasses import dataclass

MIN_REPEAT_BP = 12
MIN_PURITY = 0.70
MIN_PATH_RATIO = 0.75
MAX_PATH_RATIO = 1.25
ENTRY_OFFSET = 5
END_TOLERANCE = 10
MAX_DELETIONS = 1

MATCH_SCORE = 3
MISMATCH_PENALTY = 4
INSERTION_PENALTY = 4
DELETION_PENALTY = 4

COMPLEMENT = str.maketrans("ACGT", "TGCA")


def reverse_complement(sequence):
    return sequence.translate(COMPLEMENT)[::-1]


def rotations(sequence):
    return [
        sequence[index:] + sequence[:index]
        for index in range(len(sequence))
    ]


def canonical_motif(sequence):
    candidates = []

    for oriented in (
        sequence,
        reverse_complement(sequence),
    ):
        candidates.extend(rotations(oriented))

    return min(candidates)


@dataclass(frozen=True)
class State:
    score: int
    motif_positions: int
    matches: int
    mismatches: int
    insertions: int
    deletions: int
    starting_phase: int
    orientation: str


def state_rank(state):
    return (
        state.score,
        state.matches,
        state.motif_positions,
        -state.mismatches,
        -state.insertions,
        -state.deletions,
        -state.starting_phase,
    )


def update(container, index, candidate):
    current = container[index]

    if (
        current is None
        or state_rank(candidate)
        > state_rank(current)
    ):
        container[index] = candidate


def prefix_periodicity(sequence, motif):
    orientations = sorted(
        set(
            rotations(motif)
            + rotations(
                reverse_complement(motif)
            )
        )
    )
    prefix_best = [None] * (len(sequence) + 1)

    for orientation in orientations:
        motif_length = len(orientation)
        previous = [
            State(
                score=0,
                motif_positions=0,
                matches=0,
                mismatches=0,
                insertions=0,
                deletions=0,
                starting_phase=phase,
                orientation=orientation,
            )
            for phase in range(motif_length)
        ]

        for sequence_index, base in enumerate(
            sequence,
            start=1,
        ):
            current = [None] * motif_length

            for expected_phase, state in enumerate(
                previous
            ):
                if state is None:
                    continue

                update(
                    current,
                    expected_phase,
                    State(
                        score=(
                            state.score
                            - INSERTION_PENALTY
                        ),
                        motif_positions=(
                            state.motif_positions
                        ),
                        matches=state.matches,
                        mismatches=state.mismatches,
                        insertions=(
                            state.insertions + 1
                        ),
                        deletions=state.deletions,
                        starting_phase=(
                            state.starting_phase
                        ),
                        orientation=orientation,
                    ),
                )

                for deleted in range(
                    MAX_DELETIONS + 1
                ):
                    phase = (
                        expected_phase + deleted
                    ) % motif_length
                    is_match = (
                        base == orientation[phase]
                    )
                    delta = (
                        MATCH_SCORE
                        if is_match
                        else -MISMATCH_PENALTY
                    )
                    delta -= (
                        deleted
                        * DELETION_PENALTY
                    )

                    update(
                        current,
                        (phase + 1)
                        % motif_length,
                        State(
                            score=(
                                state.score + delta
                            ),
                            motif_positions=(
                                state.motif_positions
                                + deleted
                                + 1
                            ),
                            matches=(
                                state.matches
                                + (
                                    1
                                    if is_match
                                    else 0
                                )
                            ),
                            mismatches=(
                                state.mismatches
                                + (
                                    0
                                    if is_match
                                    else 1
                                )
                            ),
                            insertions=(
                                state.insertions
                            ),
                            deletions=(
                                state.deletions
                                + deleted
                            ),
                            starting_phase=(
                                state.starting_phase
                            ),
                            orientation=orientation,
                        ),
                    )

            best_state = max(
                (
                    state
                    for state in current
                    if state is not None
                ),
                key=state_rank,
            )

            existing = prefix_best[
                sequence_index
            ]

            if (
                existing is None
                or state_rank(best_state)
                > state_rank(existing)
            ):
                prefix_best[
                    sequence_index
                ] = best_state

            previous = current

    return prefix_best


def longest_valid_periodic_prefix(
    sequence,
    motif,
):
    if not sequence:
        return None

    prefix_states = prefix_periodicity(
        sequence,
        motif,
    )
    best = None
    motif_length = len(motif)

    for prefix_bp in range(
        MIN_REPEAT_BP,
        len(sequence) + 1,
    ):
        state = prefix_states[prefix_bp]

        if state is None:
            continue

        denominator = (
            state.matches
            + state.mismatches
            + state.insertions
            + state.deletions
        )
        purity = (
            state.matches / denominator
            if denominator
            else 0.0
        )
        observed_units = (
            prefix_bp / motif_length
        )
        path_units = (
            state.motif_positions
            / motif_length
        )
        path_ratio = (
            path_units / observed_units
            if observed_units
            else 0.0
        )

        if (
            purity < MIN_PURITY
            or path_ratio < MIN_PATH_RATIO
            or path_ratio > MAX_PATH_RATIO
            or state.score <= 0
        ):
            continue

        candidate = {
            "prefix_bp": prefix_bp,
            "purity": purity,
            "observed_units": observed_units,
            "path_units": path_units,
            "path_ratio": path_ratio,
            "matches": state.matches,
            "mismatches": state.mismatches,
            "insertions": state.insertions,
            "deletions": state.deletions,
            "score": state.score,
            "orientation": state.orientation,
            "starting_phase": (
                state.starting_phase
            ),
        }

        if (
            best is None
            or (
                candidate["prefix_bp"],
                candidate["purity"],
                candidate["score"],
            )
            > (
                best["prefix_bp"],
                best["purity"],
                best["score"],
            )
        ):
            best = candidate

    return best


def oriented_to_raw_interval(
    oriented_start,
    oriented_end,
    raw_clip_start,
    raw_clip_end,
    transform,
):
    if transform == "AS_RAW":
        return (
            raw_clip_start + oriented_start,
            raw_clip_start + oriented_end,
        )

    if transform == "REVERSE_COMPLEMENT":
        return (
            raw_clip_end - oriented_end,
            raw_clip_end - oriented_start,
        )

    raise ValueError(
        "Unknown orientation transform: {}".format(
            transform
        )
    )


@dataclass(frozen=True)
class RepeatMeasurement:
    """Sequence measurement from one target-facing P3 clip.

    This object measures repeat evidence only. It does not infer an
    expanded allele, DNA genotype, or pathogenicity.
    """

    tract_oriented_start: int | None
    tract_oriented_end: int | None
    tract_raw_start: int | None
    tract_raw_end: int | None
    tract_bp: int
    repeat_units_observed_read: float | None
    repeat_units_motif_path: float | None
    motif_path_to_read_units_ratio: float | None
    matches: int | None
    mismatches: int | None
    insertions: int | None
    deletions: int | None
    purity: float | None
    score: int | None
    selected_orientation: str | None
    entry_offset_selected_bp: int | None
    distance_from_tract_to_oriented_clip_end_bp: int | None
    tract_reaches_expected_raw_end: bool
    evidence_class: str
    sizing_status: str
    repeat_bp_lower_bound: int | None
    allele_length_status: str = (
        "NOT_MEASURABLE_ONE_FLANK_P3"
    )

    def to_contract_dict(self) -> dict[str, object]:
        """Return values formatted as in the frozen 11af TSV."""

        def integer_or_dot(
            value: int | None,
        ) -> int | str:
            return "." if value is None else value

        def float_or_dot(
            value: float | None,
        ) -> str:
            if value is None:
                return "."

            return f"{value:.6f}"

        return {
            "tract_oriented_start":
                integer_or_dot(
                    self.tract_oriented_start
                ),
            "tract_oriented_end":
                integer_or_dot(
                    self.tract_oriented_end
                ),
            "tract_raw_start":
                integer_or_dot(
                    self.tract_raw_start
                ),
            "tract_raw_end":
                integer_or_dot(
                    self.tract_raw_end
                ),
            "tract_bp":
                self.tract_bp,
            "repeat_units_observed_read":
                float_or_dot(
                    self.repeat_units_observed_read
                ),
            "repeat_units_motif_path":
                float_or_dot(
                    self.repeat_units_motif_path
                ),
            "motif_path_to_read_units_ratio":
                float_or_dot(
                    self.motif_path_to_read_units_ratio
                ),
            "matches":
                integer_or_dot(self.matches),
            "mismatches":
                integer_or_dot(self.mismatches),
            "insertions":
                integer_or_dot(self.insertions),
            "deletions":
                integer_or_dot(self.deletions),
            "purity":
                float_or_dot(self.purity),
            "score":
                integer_or_dot(self.score),
            "selected_orientation":
                (
                    self.selected_orientation
                    if self.selected_orientation
                    is not None
                    else "."
                ),
            "entry_offset_selected_bp":
                integer_or_dot(
                    self.entry_offset_selected_bp
                ),
            "distance_from_tract_to_oriented_clip_end_bp":
                integer_or_dot(
                    self.distance_from_tract_to_oriented_clip_end_bp
                ),
            "tract_reaches_expected_raw_end":
                str(
                    self.tract_reaches_expected_raw_end
                ).lower(),
            "evidence_class":
                self.evidence_class,
            "sizing_status":
                self.sizing_status,
            "repeat_bp_lower_bound":
                integer_or_dot(
                    self.repeat_bp_lower_bound
                ),
            "allele_length_status":
                self.allele_length_status,
        }


def _no_repeat_measurement() -> RepeatMeasurement:
    return RepeatMeasurement(
        tract_oriented_start=None,
        tract_oriented_end=None,
        tract_raw_start=None,
        tract_raw_end=None,
        tract_bp=0,
        repeat_units_observed_read=None,
        repeat_units_motif_path=None,
        motif_path_to_read_units_ratio=None,
        matches=None,
        mismatches=None,
        insertions=None,
        deletions=None,
        purity=None,
        score=None,
        selected_orientation=None,
        entry_offset_selected_bp=None,
        distance_from_tract_to_oriented_clip_end_bp=None,
        tract_reaches_expected_raw_end=False,
        evidence_class=(
            "P3_BRIDGE_ONLY_NO_TARGET_ENTRY_REPEAT_TRACT"
        ),
        sizing_status="no_call",
        repeat_bp_lower_bound=None,
    )


def measure_target_entry_repeat(
    *,
    oriented_clip: str,
    motif: str,
    target_entry_query_offset: int | None,
    raw_clip_start: int,
    raw_clip_end: int,
    orientation_transform: str,
    target_facing_genomic_side: str,
    target_entry_projection_status: str,
    query_prefix_matches: bool,
) -> RepeatMeasurement:
    """Measure a periodic tract near a projected target entrance.

    Mononucleotide tracts may be measured here, but downstream decision
    code must continue to route them to homopolymer review rather than
    the standard P3 evidence stream.
    """

    if raw_clip_start < 0:
        raise ValueError(
            "raw_clip_start must be non-negative"
        )

    if raw_clip_end < raw_clip_start:
        raise ValueError(
            "raw_clip_end must be at least raw_clip_start"
        )

    if len(oriented_clip) != (
        raw_clip_end - raw_clip_start
    ):
        raise ValueError(
            "oriented_clip length does not match raw clip interval"
        )

    if orientation_transform not in {
        "AS_RAW",
        "REVERSE_COMPLEMENT",
    }:
        raise ValueError(
            "unsupported orientation_transform"
        )

    if target_facing_genomic_side not in {
        "GENOMIC_RIGHT",
        "GENOMIC_LEFT",
    }:
        raise ValueError(
            "unsupported target_facing_genomic_side"
        )

    if (
        target_entry_projection_status
        != "TARGET_ENTRY_PROJECTED"
        or target_entry_query_offset is None
        or not query_prefix_matches
    ):
        return _no_repeat_measurement()

    if not (
        0
        <= target_entry_query_offset
        <= len(oriented_clip)
    ):
        raise ValueError(
            "target_entry_query_offset is outside oriented clip"
        )

    normalized_motif = canonical_motif(motif)
    minimum_start = max(
        0,
        target_entry_query_offset - ENTRY_OFFSET,
    )
    maximum_start = min(
        len(oriented_clip),
        target_entry_query_offset + ENTRY_OFFSET,
    )

    best_tract = None

    for tract_start in range(
        minimum_start,
        maximum_start + 1,
    ):
        call = longest_valid_periodic_prefix(
            oriented_clip[tract_start:],
            normalized_motif,
        )

        if call is None:
            continue

        tract_end = (
            tract_start + call["prefix_bp"]
        )
        reaches_end = (
            len(oriented_clip) - tract_end
            <= END_TOLERANCE
        )
        candidate = dict(call)
        candidate.update(
            {
                "tract_start": tract_start,
                "tract_end": tract_end,
                "entry_offset": (
                    tract_start
                    - target_entry_query_offset
                ),
                "reaches_clip_end": reaches_end,
            }
        )
        rank = (
            candidate["prefix_bp"],
            candidate["purity"],
            candidate["score"],
            -abs(candidate["entry_offset"]),
        )

        if (
            best_tract is None
            or rank > best_tract["_rank"]
        ):
            candidate["_rank"] = rank
            best_tract = candidate

    if best_tract is None:
        return _no_repeat_measurement()

    tract_raw_start, tract_raw_end = (
        oriented_to_raw_interval(
            best_tract["tract_start"],
            best_tract["tract_end"],
            raw_clip_start,
            raw_clip_end,
            orientation_transform,
        )
    )

    if best_tract["reaches_clip_end"]:
        sizing_status = "lower_bound"
        repeat_bp_lower_bound = (
            best_tract["prefix_bp"]
        )

        if (
            target_facing_genomic_side
            == "GENOMIC_RIGHT"
        ):
            evidence_class = (
                "LEFT_ANCHORED_CENSORED_RIGHT"
            )
        else:
            evidence_class = (
                "RIGHT_ANCHORED_CENSORED_LEFT"
            )

    else:
        sizing_status = "partial_internal"
        repeat_bp_lower_bound = None

        if (
            target_facing_genomic_side
            == "GENOMIC_RIGHT"
        ):
            evidence_class = "LEFT_ONLY_INTERNAL"
        else:
            evidence_class = "RIGHT_ONLY_INTERNAL"

    return RepeatMeasurement(
        tract_oriented_start=(
            best_tract["tract_start"]
        ),
        tract_oriented_end=(
            best_tract["tract_end"]
        ),
        tract_raw_start=tract_raw_start,
        tract_raw_end=tract_raw_end,
        tract_bp=best_tract["prefix_bp"],
        repeat_units_observed_read=(
            best_tract["observed_units"]
        ),
        repeat_units_motif_path=(
            best_tract["path_units"]
        ),
        motif_path_to_read_units_ratio=(
            best_tract["path_ratio"]
        ),
        matches=best_tract["matches"],
        mismatches=best_tract["mismatches"],
        insertions=best_tract["insertions"],
        deletions=best_tract["deletions"],
        purity=best_tract["purity"],
        score=best_tract["score"],
        selected_orientation=(
            best_tract["orientation"]
        ),
        entry_offset_selected_bp=(
            best_tract["entry_offset"]
        ),
        distance_from_tract_to_oriented_clip_end_bp=(
            len(oriented_clip)
            - best_tract["tract_end"]
        ),
        tract_reaches_expected_raw_end=(
            best_tract["reaches_clip_end"]
        ),
        evidence_class=evidence_class,
        sizing_status=sizing_status,
        repeat_bp_lower_bound=(
            repeat_bp_lower_bound
        ),
    )
