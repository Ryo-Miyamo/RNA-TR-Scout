from __future__ import annotations

import unittest

from rnatr_scout.p3_repeat import (
    measure_target_entry_repeat,
)


class TestP3Repeat(unittest.TestCase):
    def test_internal_homopolymer_measurement(self):
        # Keep more than END_TOLERANCE (10 bp) after the A-rich
        # tract, so this fixture truly represents an internal tract.
        clip = "C" + ("A" * 13) + ("G" * 20)

        result = measure_target_entry_repeat(
            oriented_clip=clip,
            motif="A",
            target_entry_query_offset=2,
            raw_clip_start=100,
            raw_clip_end=100 + len(clip),
            orientation_transform="AS_RAW",
            target_facing_genomic_side=(
                "GENOMIC_RIGHT"
            ),
            target_entry_projection_status=(
                "TARGET_ENTRY_PROJECTED"
            ),
            query_prefix_matches=True,
        )

        self.assertEqual(
            result.sizing_status,
            "partial_internal",
        )
        self.assertEqual(
            result.evidence_class,
            "LEFT_ONLY_INTERNAL",
        )
        self.assertGreaterEqual(
            result.tract_bp,
            12,
        )
        self.assertIsNone(
            result.repeat_bp_lower_bound
        )

    def test_terminal_tract_is_lower_bound(self):
        clip = "CCCAAAAAAAAAAAAA"

        result = measure_target_entry_repeat(
            oriented_clip=clip,
            motif="A",
            target_entry_query_offset=3,
            raw_clip_start=10,
            raw_clip_end=10 + len(clip),
            orientation_transform="AS_RAW",
            target_facing_genomic_side=(
                "GENOMIC_RIGHT"
            ),
            target_entry_projection_status=(
                "TARGET_ENTRY_PROJECTED"
            ),
            query_prefix_matches=True,
        )

        self.assertEqual(
            result.sizing_status,
            "lower_bound",
        )
        self.assertEqual(
            result.evidence_class,
            "LEFT_ANCHORED_CENSORED_RIGHT",
        )
        self.assertEqual(
            result.repeat_bp_lower_bound,
            result.tract_bp,
        )

    def test_reverse_projection_is_no_call(self):
        clip = "A" * 30

        result = measure_target_entry_repeat(
            oriented_clip=clip,
            motif="A",
            target_entry_query_offset=None,
            raw_clip_start=20,
            raw_clip_end=50,
            orientation_transform="AS_RAW",
            target_facing_genomic_side=(
                "GENOMIC_RIGHT"
            ),
            target_entry_projection_status=(
                "UNEXPECTED_REVERSE_ALIGNMENT"
            ),
            query_prefix_matches=True,
        )

        contract = result.to_contract_dict()

        self.assertEqual(
            result.sizing_status,
            "no_call",
        )
        self.assertEqual(
            contract["tract_bp"],
            0,
        )
        self.assertEqual(
            contract["purity"],
            ".",
        )

    def test_query_prefix_mismatch_is_no_call(self):
        clip = "A" * 30

        result = measure_target_entry_repeat(
            oriented_clip=clip,
            motif="A",
            target_entry_query_offset=0,
            raw_clip_start=0,
            raw_clip_end=30,
            orientation_transform="AS_RAW",
            target_facing_genomic_side=(
                "GENOMIC_LEFT"
            ),
            target_entry_projection_status=(
                "TARGET_ENTRY_PROJECTED"
            ),
            query_prefix_matches=False,
        )

        self.assertEqual(
            result.sizing_status,
            "no_call",
        )

    def test_length_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            measure_target_entry_repeat(
                oriented_clip="AAAA",
                motif="A",
                target_entry_query_offset=0,
                raw_clip_start=0,
                raw_clip_end=5,
                orientation_transform="AS_RAW",
                target_facing_genomic_side=(
                    "GENOMIC_RIGHT"
                ),
                target_entry_projection_status=(
                    "TARGET_ENTRY_PROJECTED"
                ),
                query_prefix_matches=True,
            )


if __name__ == "__main__":
    unittest.main()
