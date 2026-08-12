"""CIGAR parsing and reference-to-query boundary projection."""

from __future__ import annotations

from dataclasses import dataclass
import re

_CIGAR_PATTERN = re.compile(r"([0-9]+)([MIDNSHP=X])")


@dataclass(frozen=True)
class BoundaryProjection:
    """Projected query coordinate for a reference boundary."""

    query_offset: int | None
    status: str


def parse_cigar(cigar: str) -> tuple[tuple[str, int], ...]:
    """Parse a SAM CIGAR into ``(operation, length)`` tuples."""

    if not cigar or cigar == "*":
        raise ValueError("CIGAR must be present")

    operations = tuple(
        (operation, int(length))
        for length, operation in _CIGAR_PATTERN.findall(cigar)
    )

    reconstructed = "".join(
        f"{length}{operation}"
        for operation, length in operations
    )

    if reconstructed != cigar:
        raise ValueError(
            f"invalid or incompletely parsed CIGAR: {cigar!r}"
        )

    if any(length <= 0 for _, length in operations):
        raise ValueError("CIGAR operation lengths must be positive")

    return operations


def project_reference_boundary_to_query(
    *,
    query_start: int,
    reference_start: int,
    cigar: str,
    reference_boundary: int,
) -> BoundaryProjection:
    """Project a 0-based reference boundary through a CIGAR.

    Coordinates are offsets within the query and candidate reference
    sequences used for the local alignment. Insertions advance only
    the query; deletions and ``N`` operations advance only the
    reference. A boundary inside a deletion or skipped region maps to
    the current query cursor and retains an explicit status.
    """

    if min(query_start, reference_start, reference_boundary) < 0:
        raise ValueError("coordinates must be non-negative")

    if reference_boundary < reference_start:
        return BoundaryProjection(
            None,
            "BOUNDARY_BEFORE_ALIGNMENT",
        )

    query_cursor = query_start
    reference_cursor = reference_start

    for operation, length in parse_cigar(cigar):
        if reference_boundary == reference_cursor:
            return BoundaryProjection(
                query_cursor,
                "PROJECTED_AT_OPERATION_BOUNDARY",
            )

        if operation in {"M", "=", "X"}:
            next_reference = reference_cursor + length
            next_query = query_cursor + length

            if (
                reference_cursor
                < reference_boundary
                <= next_reference
            ):
                delta = reference_boundary - reference_cursor
                return BoundaryProjection(
                    query_cursor + delta,
                    "PROJECTED_WITHIN_MATCHLIKE",
                )

            reference_cursor = next_reference
            query_cursor = next_query
            continue

        if operation == "I":
            query_cursor += length
            continue

        if operation in {"D", "N"}:
            next_reference = reference_cursor + length

            if (
                reference_cursor
                < reference_boundary
                <= next_reference
            ):
                status = (
                    "PROJECTED_WITHIN_DELETION"
                    if operation == "D"
                    else "PROJECTED_WITHIN_REFERENCE_SKIP"
                )
                return BoundaryProjection(
                    query_cursor,
                    status,
                )

            reference_cursor = next_reference
            continue

        if operation == "S":
            query_cursor += length
            continue

        if operation in {"H", "P"}:
            continue

        raise ValueError(
            f"unsupported CIGAR operation: {operation}"
        )

    if reference_boundary == reference_cursor:
        return BoundaryProjection(
            query_cursor,
            "PROJECTED_AT_ALIGNMENT_END",
        )

    return BoundaryProjection(
        None,
        "BOUNDARY_AFTER_ALIGNMENT",
    )
