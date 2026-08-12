from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from rnatr_scout.p3_pipeline import (
    run_p3_pipeline,
)


def pair_result(
    *,
    strand,
    projection_status,
    query_offset,
):
    selected = (
        None
        if strand is None
        else SimpleNamespace(strand=strand)
    )

    return SimpleNamespace(
        selected_alignment=selected,
        target_entry_query_offset=query_offset,
        target_entry_projection_status=(
            projection_status
        ),
        to_dict=lambda: {
            "selected_strand": strand,
            "target_entry_query_offset":
                query_offset,
            "target_entry_projection_status":
                projection_status,
        },
    )


class TestP3Pipeline(unittest.TestCase):
    @patch(
        "rnatr_scout.p3_pipeline."
        "run_isolated_pair_alignment"
    )
    def test_reverse_alignment_is_rejected(
        self,
        mocked_alignment,
    ):
        mocked_alignment.return_value = pair_result(
            strand="-",
            projection_status=(
                "UNEXPECTED_REVERSE_ALIGNMENT"
            ),
            query_offset=None,
        )
        raw_read = "A" * 30

        result = run_p3_pipeline(
            query_name="q",
            query_sequence="A" * 10,
            target_name="r",
            target_sequence="T" * 30,
            raw_read_sequence=raw_read,
            raw_clip_start=0,
            raw_clip_end=30,
            raw_alignment_strand="+",
            target_facing_genomic_side=(
                "GENOMIC_RIGHT"
            ),
            canonical_motif="A",
            bridge_bp=5,
            target_entry_bp=20,
            query_can_reach_target_entry=True,
            expected_orientation_transform=(
                "AS_RAW"
            ),
        )

        self.assertEqual(
            result.decision.primary_status,
            "REJECT_ORIENTATION_INCONSISTENT_BRIDGE",
        )
        self.assertFalse(
            result.decision.standard_evidence_emitted
        )

    @patch(
        "rnatr_scout.p3_pipeline."
        "run_isolated_pair_alignment"
    )
    def test_projected_homopolymer_is_review_only(
        self,
        mocked_alignment,
    ):
        mocked_alignment.return_value = pair_result(
            strand="+",
            projection_status=(
                "TARGET_ENTRY_PROJECTED"
            ),
            query_offset=2,
        )
        raw_read = (
            "C"
            + ("A" * 13)
            + ("G" * 20)
        )

        result = run_p3_pipeline(
            query_name="q",
            query_sequence=raw_read[:10],
            target_name="r",
            target_sequence="A" * 30,
            raw_read_sequence=raw_read,
            raw_clip_start=0,
            raw_clip_end=len(raw_read),
            raw_alignment_strand="+",
            target_facing_genomic_side=(
                "GENOMIC_RIGHT"
            ),
            canonical_motif="A",
            bridge_bp=2,
            target_entry_bp=20,
            query_can_reach_target_entry=True,
            expected_orientation_transform=(
                "AS_RAW"
            ),
        )

        self.assertEqual(
            result.repeat_measurement.sizing_status,
            "partial_internal",
        )
        self.assertEqual(
            result.decision.primary_status,
            "HOMOPOLYMER_REVIEW_NO_STANDARD_P3_EVIDENCE",
        )
        self.assertFalse(
            result.decision.standard_evidence_emitted
        )
        self.assertEqual(
            result.decision.expansion_status,
            "NOT_ASSESSED",
        )

    @patch(
        "rnatr_scout.p3_pipeline."
        "run_isolated_pair_alignment"
    )
    def test_no_alignment_is_target_entry_rejection(
        self,
        mocked_alignment,
    ):
        mocked_alignment.return_value = pair_result(
            strand=None,
            projection_status=(
                "TARGET_ENTRY_NOT_PROJECTED"
            ),
            query_offset=None,
        )
        raw_read = "CAG" * 10

        result = run_p3_pipeline(
            query_name="q",
            query_sequence=raw_read[:12],
            target_name="r",
            target_sequence=raw_read,
            raw_read_sequence=raw_read,
            raw_clip_start=0,
            raw_clip_end=len(raw_read),
            raw_alignment_strand="+",
            target_facing_genomic_side=(
                "GENOMIC_RIGHT"
            ),
            canonical_motif="CAG",
            bridge_bp=5,
            target_entry_bp=20,
            query_can_reach_target_entry=True,
        )

        self.assertEqual(
            result.decision.primary_status,
            "REJECT_TARGET_ENTRY_NOT_PROJECTED",
        )

    @patch(
        "rnatr_scout.p3_pipeline."
        "run_isolated_pair_alignment"
    )
    def test_orientation_contract_mismatch_rejected(
        self,
        mocked_alignment,
    ):
        mocked_alignment.return_value = pair_result(
            strand="+",
            projection_status=(
                "TARGET_ENTRY_PROJECTED"
            ),
            query_offset=0,
        )

        with self.assertRaises(ValueError):
            run_p3_pipeline(
                query_name="q",
                query_sequence="AAAA",
                target_name="r",
                target_sequence="AAAA",
                raw_read_sequence="AAAA",
                raw_clip_start=0,
                raw_clip_end=4,
                raw_alignment_strand="+",
                target_facing_genomic_side=(
                    "GENOMIC_RIGHT"
                ),
                canonical_motif="A",
                bridge_bp=0,
                target_entry_bp=4,
                query_can_reach_target_entry=True,
                expected_orientation_transform=(
                    "REVERSE_COMPLEMENT"
                ),
            )


if __name__ == "__main__":
    unittest.main()
