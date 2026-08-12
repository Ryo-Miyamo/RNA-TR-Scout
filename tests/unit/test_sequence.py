from __future__ import annotations

import unittest

from rnatr_scout.sequence import reverse_complement


class TestSequence(unittest.TestCase):
    def test_reverse_complement(self):
        self.assertEqual(
            reverse_complement("ACGTN"),
            "NACGT",
        )

    def test_invalid_base(self):
        with self.assertRaises(ValueError):
            reverse_complement("ACGU")


if __name__ == "__main__":
    unittest.main()
