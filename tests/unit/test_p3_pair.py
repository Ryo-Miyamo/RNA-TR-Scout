from __future__ import annotations

import unittest

from rnatr_scout.p3_pair import (
    evaluate_pair_alignments,
)
from rnatr_scout.paf import parse_paf


class TestP3Pair(unittest.TestCase):
    def test_valid_plus_alignment_selected(self):
        alignments = parse_paf(
            "q\t30\t0\t25\t-\tt\t30\t0\t25\t"
            "25\t25\t60\tAS:i:60\tcg:Z:25M\n"
            "q\t30\t0\t22\t+\tt\t30\t0\t22\t"
            "21\t22\t40\tAS:i:50\tcg:Z:22M\n"
        )
        result = evaluate_pair_alignments(
            alignments,
            expected_query_name="q",
            expected_target_name="t",
            bridge_bp=7,
            target_entry_bp=20,
            query_can_reach_target_entry=True,
        )
        self.assertTrue(
            result.bridge_decision.bridge_valid
        )
        self.assertEqual(
            result.selected_alignment.strand,
            "+",
        )
        self.assertEqual(
            result.target_entry_query_offset,
            7,
        )

    def test_reverse_only_rejected(self):
        alignments = parse_paf(
            "q\t30\t0\t25\t-\tt\t30\t0\t25\t"
            "25\t25\t60\tAS:i:60\tcg:Z:25M\n"
        )
        result = evaluate_pair_alignments(
            alignments,
            expected_query_name="q",
            expected_target_name="t",
            bridge_bp=7,
            target_entry_bp=20,
            query_can_reach_target_entry=True,
        )
        self.assertEqual(
            result.bridge_decision.bridge_status,
            "ORIENTATION_INCONSISTENT_BRIDGE",
        )
        self.assertEqual(
            result.target_entry_projection_status,
            "UNEXPECTED_REVERSE_ALIGNMENT",
        )

    def test_missing_cigar_prevents_projection(self):
        alignments = parse_paf(
            "q\t30\t0\t25\t+\tt\t30\t0\t25\t"
            "25\t25\t60\tAS:i:60\n"
        )
        result = evaluate_pair_alignments(
            alignments,
            expected_query_name="q",
            expected_target_name="t",
            bridge_bp=7,
            target_entry_bp=20,
            query_can_reach_target_entry=True,
        )
        self.assertTrue(
            result.bridge_decision.bridge_valid
        )
        self.assertEqual(
            result.target_entry_projection_detail,
            "CIGAR_MISSING",
        )

    def test_no_pair_alignment(self):
        result = evaluate_pair_alignments(
            [],
            expected_query_name="q",
            expected_target_name="t",
            bridge_bp=7,
            target_entry_bp=20,
            query_can_reach_target_entry=True,
        )
        self.assertEqual(
            result.bridge_decision.bridge_status,
            "NO_CANDIDATE_ALIGNMENT",
        )


if __name__ == "__main__":
    unittest.main()
