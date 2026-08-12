from __future__ import annotations

import unittest

from rnatr_scout.cigar import (
    parse_cigar,
    project_reference_boundary_to_query,
)


class TestCigar(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(
            parse_cigar("5S10M2I5M3D4M"),
            (
                ("S", 5),
                ("M", 10),
                ("I", 2),
                ("M", 5),
                ("D", 3),
                ("M", 4),
            ),
        )

    def test_project_match(self):
        result = project_reference_boundary_to_query(
            query_start=0,
            reference_start=0,
            cigar="10M",
            reference_boundary=7,
        )
        self.assertEqual(result.query_offset, 7)
        self.assertEqual(
            result.status,
            "PROJECTED_WITHIN_MATCHLIKE",
        )

    def test_insertion_advances_query(self):
        result = project_reference_boundary_to_query(
            query_start=0,
            reference_start=0,
            cigar="5M3I5M",
            reference_boundary=8,
        )
        self.assertEqual(result.query_offset, 11)

    def test_deletion_projection(self):
        result = project_reference_boundary_to_query(
            query_start=0,
            reference_start=0,
            cigar="5M3D5M",
            reference_boundary=7,
        )
        self.assertEqual(result.query_offset, 5)
        self.assertEqual(
            result.status,
            "PROJECTED_WITHIN_DELETION",
        )

    def test_after_alignment(self):
        result = project_reference_boundary_to_query(
            query_start=0,
            reference_start=0,
            cigar="5M",
            reference_boundary=6,
        )
        self.assertIsNone(result.query_offset)
        self.assertEqual(
            result.status,
            "BOUNDARY_AFTER_ALIGNMENT",
        )


if __name__ == "__main__":
    unittest.main()
