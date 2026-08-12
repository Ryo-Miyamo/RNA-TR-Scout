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
