from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from rnatr_scout.batch import (
    classify_p3_row,
    classify_p3_tsv,
)


def base_row():
    return {
        "projection_id": "projection-1",
        "read_id": "read-1",
        "target_region_id": "target-1",
        "best_alignment_strand": "+",
        "target_entry_projection_status":
            "TARGET_ENTRY_PROJECTED",
        "canonical_motif": "CAG",
        "target_facing_genomic_side":
            "GENOMIC_RIGHT",
        "tract_bp": "30",
        "tract_reaches_expected_raw_end":
            "false",
    }


class TestP3Batch(unittest.TestCase):
    def test_row_classification(self):
        result = classify_p3_row(base_row())
        self.assertEqual(
            result["evidence_class"],
            "LEFT_ONLY_INTERNAL",
        )

    def test_orientation_negative(self):
        row = base_row()
        row["best_alignment_strand"] = "-"
        result = classify_p3_row(row)
        self.assertEqual(
            result["failure_code"],
            "ORIENTATION_INCONSISTENT_BRIDGE",
        )

    def test_tsv_atomic_output(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            input_path = directory / "input.tsv"
            output_path = directory / "output.tsv"
            row = base_row()

            with input_path.open(
                "w",
                encoding="utf-8",
                newline="",
            ) as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=list(row.keys()),
                    delimiter="\t",
                    lineterminator="\n",
                )
                writer.writeheader()
                writer.writerow(row)

            count = classify_p3_tsv(
                input_path,
                output_path,
            )
            self.assertEqual(count, 1)
            self.assertTrue(output_path.is_file())

            with output_path.open(
                "r",
                encoding="utf-8",
                newline="",
            ) as handle:
                results = list(
                    csv.DictReader(
                        handle,
                        delimiter="\t",
                    )
                )

            self.assertEqual(
                results[0]["sizing_status"],
                "partial_internal",
            )

    def test_missing_header_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            input_path = directory / "input.tsv"
            output_path = directory / "output.tsv"
            input_path.write_text(
                "projection_id\tread_id\np\tr\n",
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                classify_p3_tsv(
                    input_path,
                    output_path,
                )


if __name__ == "__main__":
    unittest.main()
