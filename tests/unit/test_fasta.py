from __future__ import annotations

import gzip
import tempfile
import unittest
from pathlib import Path

from rnatr_scout.fasta import (
    fetch_fasta_record,
    load_fasta,
)


class TestFasta(unittest.TestCase):
    def test_load_plain_fasta(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.fa"
            path.write_text(
                ">a comment\nAC\nGT\n>b\nTT\n",
                encoding="utf-8",
            )
            self.assertEqual(
                load_fasta(path),
                {
                    "a": "ACGT",
                    "b": "TT",
                },
            )

    def test_fetch_gzip_fasta(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.fa.gz"

            with gzip.open(
                path,
                "wt",
                encoding="utf-8",
            ) as handle:
                handle.write(">a\nACGT\n")

            self.assertEqual(
                fetch_fasta_record(path, "a"),
                "ACGT",
            )

    def test_duplicate_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.fa"
            path.write_text(
                ">a\nAC\n>a\nGT\n",
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                load_fasta(path)


if __name__ == "__main__":
    unittest.main()
