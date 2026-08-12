from __future__ import annotations

import unittest

from rnatr_scout.paf import parse_paf_line


class TestPaf(unittest.TestCase):
    def test_parse_paf_line(self):
        alignment = parse_paf_line(
            "q\t20\t0\t18\t+\tt\t30\t0\t18\t"
            "17\t18\t60\tAS:i:42\tcg:Z:18M"
        )
        self.assertEqual(
            alignment.query_name,
            "q",
        )
        self.assertEqual(
            alignment.target_name,
            "t",
        )
        self.assertEqual(
            alignment.alignment_score,
            42,
        )
        self.assertEqual(
            alignment.cigar,
            "18M",
        )
        self.assertAlmostEqual(
            alignment.identity,
            17 / 18,
        )
        self.assertAlmostEqual(
            alignment.query_coverage,
            18 / 20,
        )

    def test_short_row_rejected(self):
        with self.assertRaises(ValueError):
            parse_paf_line("q\t1")


if __name__ == "__main__":
    unittest.main()
