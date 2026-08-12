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
