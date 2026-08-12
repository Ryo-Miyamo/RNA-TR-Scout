from __future__ import annotations

import unittest

from rnatr_scout.p3_bridge import (
    BridgeAlignmentObservation,
    evaluate_bridge_alignment,
)


def observation(**updates):
    values = {
        "alignment_present": True,
        "alignment_strand": "+",
        "query_start": 0,
        "reference_start": 0,
        "query_coverage": 0.80,
        "identity": 0.90,
        "reference_end": 30,
        "bridge_bp": 7,
        "target_entry_bp": 60,
        "query_can_reach_target_entry": True,
    }
    values.update(updates)
    return BridgeAlignmentObservation(**values)


class TestP3Bridge(unittest.TestCase):
    def test_valid_bridge(self):
        decision = evaluate_bridge_alignment(
            observation()
        )
        self.assertTrue(decision.bridge_valid)
        self.assertEqual(
            decision.bridge_status,
            "BRIDGE_REACHES_TARGET_ENTRY",
        )
        self.assertEqual(
            decision.required_reference_end,
            19,
        )

    def test_query_too_short(self):
        decision = evaluate_bridge_alignment(
            observation(
                query_can_reach_target_entry=False
            )
        )
        self.assertEqual(
            decision.bridge_status,
            "QUERY_TOO_SHORT_TO_REACH_TARGET",
        )

    def test_no_alignment(self):
        decision = evaluate_bridge_alignment(
            observation(
                alignment_present=False,
                alignment_strand=None,
                query_start=None,
                reference_start=None,
                query_coverage=None,
                identity=None,
                reference_end=None,
            )
        )
        self.assertEqual(
            decision.bridge_status,
            "NO_CANDIDATE_ALIGNMENT",
        )

    def test_reverse_rejected_before_other_checks(self):
        decision = evaluate_bridge_alignment(
            observation(
                alignment_strand="-",
                query_start=100,
                identity=0.10,
            )
        )
        self.assertEqual(
            decision.bridge_status,
            "ORIENTATION_INCONSISTENT_BRIDGE",
        )

    def test_boundary_required(self):
        decision = evaluate_bridge_alignment(
            observation(query_start=11)
        )
        self.assertEqual(
            decision.bridge_status,
            "ALIGNMENT_NOT_CONNECTED_TO_BLOCK_BOUNDARY",
        )

    def test_quality_required(self):
        decision = evaluate_bridge_alignment(
            observation(identity=0.69)
        )
        self.assertEqual(
            decision.bridge_status,
            "LOW_QUALITY_BRIDGE_ALIGNMENT",
        )

    def test_target_entry_required(self):
        decision = evaluate_bridge_alignment(
            observation(reference_end=18)
        )
        self.assertEqual(
            decision.bridge_status,
            "BRIDGE_STOPS_BEFORE_TARGET_ENTRY",
        )

    def test_missing_fields_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_bridge_alignment(
                observation(identity=None)
            )


if __name__ == "__main__":
    unittest.main()
