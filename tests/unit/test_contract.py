from __future__ import annotations

import os
import unittest
from pathlib import Path

from rnatr_scout.contract import check_contract


class TestContract(unittest.TestCase):
    def test_v032_contract(self):
        project_root = Path(
            os.environ["RNATR_PROJECT_ROOT"]
        )
        result = check_contract(
            project_root
            / "config"
            / "evidence_schema"
            / "v0.3.2",
            project_root
            / "tests"
            / "regression"
            / "v0.3.2",
        )
        self.assertEqual(
            result["status"],
            "PASS",
            result["failures"],
        )
        self.assertEqual(
            result["regression_cases"],
            20,
        )
        self.assertEqual(
            result["decision_rules"],
            16,
        )


if __name__ == "__main__":
    unittest.main()
