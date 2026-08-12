"""Small sequence utilities used by RNA-TR-Scout."""

from __future__ import annotations

_COMPLEMENT = str.maketrans(
    "ACGTNacgtn",
    "TGCANtgcan",
)


def reverse_complement(sequence: str) -> str:
    """Return the reverse complement of an A/C/G/T/N sequence."""

    invalid = {
        base
        for base in sequence
        if base not in "ACGTNacgtn"
    }

    if invalid:
        raise ValueError(
            "sequence contains unsupported bases: "
            + ",".join(sorted(invalid))
        )

    return sequence.translate(_COMPLEMENT)[::-1]
