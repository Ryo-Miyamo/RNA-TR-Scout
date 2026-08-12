from __future__ import annotations

import unittest

from rnatr_scout.p3 import (
    P3Observation,
    classify_p3,
)


def observation(**updates):
    values = {
        "alignment_strand": "+",
        "target_entry_projected": True,
        "canonical_motif": "CAG",
        "target_facing_genomic_side": "GENOMIC_RIGHT",
        "tract_bp": 30,
        "tract_reaches_expected_raw_end": False,
    }
    values.update(updates)
    return P3Observation(**values)


class TestP3Rules(unittest.TestCase):
    def test_orientation_has_highest_priority(self):
        decision = classify_p3(
            observation(
                alignment_strand="-",
                canonical_motif="A",
            )
        )
        self.assertEqual(
            decision.failure_code,
            "ORIENTATION_INCONSISTENT_BRIDGE",
        )
        self.assertFalse(
            decision.standard_evidence_emitted
        )

    def test_target_entry_projection_required(self):
        decision = classify_p3(
            observation(
                target_entry_projected=False
            )
        )
        self.assertEqual(
            decision.failure_code,
            "TARGET_ENTRY_NOT_PROJECTED",
        )

    def test_homopolymer_is_review_only(self):
        decision = classify_p3(
            observation(canonical_motif="A")
        )
        self.assertEqual(
            decision.failure_code,
            "HOMOPOLYMER_REVIEW",
        )
        self.assertEqual(
            decision.sizing_status,
            "no_call",
        )

    def test_bridge_only_is_no_call(self):
        decision = classify_p3(
            observation(tract_bp=None)
        )
        self.assertEqual(
            decision.failure_code,
            "REPEAT_NOT_FOUND",
        )
        self.assertFalse(
            decision.standard_evidence_emitted
        )

    def test_genomic_right_internal(self):
        decision = classify_p3(observation())
        self.assertEqual(
            decision.evidence_class,
            "LEFT_ONLY_INTERNAL",
        )
        self.assertEqual(
            decision.sizing_status,
            "partial_internal",
        )
        self.assertIsNone(
            decision.repeat_bp_lower_bound
        )

    def test_genomic_left_internal(self):
        decision = classify_p3(
            observation(
                target_facing_genomic_side=(
                    "GENOMIC_LEFT"
                )
            )
        )
        self.assertEqual(
            decision.evidence_class,
            "RIGHT_ONLY_INTERNAL",
        )

    def test_genomic_right_censored(self):
        decision = classify_p3(
            observation(
                tract_reaches_expected_raw_end=True
            )
        )
        self.assertEqual(
            decision.evidence_class,
            "LEFT_ANCHORED_CENSORED_RIGHT",
        )
        self.assertEqual(
            decision.repeat_bp_lower_bound,
            30.0,
        )

    def test_genomic_left_censored(self):
        decision = classify_p3(
            observation(
                target_facing_genomic_side=(
                    "GENOMIC_LEFT"
                ),
                tract_reaches_expected_raw_end=True,
            )
        )
        self.assertEqual(
            decision.evidence_class,
            "RIGHT_ANCHORED_CENSORED_LEFT",
        )

    def test_exact_and_expansion_are_never_emitted(self):
        decision = classify_p3(
            observation(
                tract_reaches_expected_raw_end=True
            )
        )
        self.assertIsNone(
            decision.repeat_bp_estimate
        )
        self.assertEqual(
            decision.expansion_status,
            "NOT_ASSESSED",
        )

    def test_invalid_motif_rejected(self):
        with self.assertRaises(ValueError):
            classify_p3(
                observation(canonical_motif="CAN")
            )


if __name__ == "__main__":
    unittest.main()
