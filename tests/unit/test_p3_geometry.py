from __future__ import annotations

import unittest

from rnatr_scout.p3_geometry import (
    candidate_reference_geometry,
    expected_orientation_transform,
    orient_candidate_reference,
    orient_target_facing_clip,
)


class TestP3Geometry(unittest.TestCase):
    def test_all_orientation_combinations(self):
        expected = {
            ("+", "GENOMIC_RIGHT"): "AS_RAW",
            ("+", "GENOMIC_LEFT"): "REVERSE_COMPLEMENT",
            ("-", "GENOMIC_RIGHT"): "REVERSE_COMPLEMENT",
            ("-", "GENOMIC_LEFT"): "AS_RAW",
        }

        for key, value in expected.items():
            with self.subTest(key=key):
                self.assertEqual(
                    expected_orientation_transform(*key),
                    value,
                )

    def test_orient_clip(self):
        sequence, transform = orient_target_facing_clip(
            "AACG",
            "+",
            "GENOMIC_LEFT",
        )
        self.assertEqual(sequence, "CGTT")
        self.assertEqual(
            transform,
            "REVERSE_COMPLEMENT",
        )

    def test_right_geometry(self):
        geometry = candidate_reference_geometry(
            block_start=100,
            block_end=150,
            target_start=157,
            target_end=200,
            target_side="GENOMIC_RIGHT",
        )
        self.assertEqual(geometry.fetch_start, 150)
        self.assertEqual(geometry.fetch_end, 200)
        self.assertEqual(geometry.bridge_bp, 7)
        self.assertFalse(
            geometry.reverse_complement_after_fetch
        )

    def test_left_geometry(self):
        geometry = candidate_reference_geometry(
            block_start=100,
            block_end=150,
            target_start=40,
            target_end=90,
            target_side="GENOMIC_LEFT",
            target_entry_bp=20,
        )
        self.assertEqual(geometry.fetch_start, 70)
        self.assertEqual(geometry.fetch_end, 100)
        self.assertEqual(geometry.bridge_bp, 10)
        self.assertTrue(
            geometry.reverse_complement_after_fetch
        )
        self.assertEqual(
            orient_candidate_reference(
                "A" * 30,
                geometry,
            ),
            "T" * 30,
        )

    def test_overlapping_target_rejected(self):
        with self.assertRaises(ValueError):
            candidate_reference_geometry(
                block_start=100,
                block_end=150,
                target_start=145,
                target_end=170,
                target_side="GENOMIC_RIGHT",
            )


if __name__ == "__main__":
    unittest.main()
