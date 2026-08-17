from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from rnatr_scout.resource_planner import (
    GIB,
    ResourcePlanError,
    SystemResources,
    count_fastq_reads,
    plan_resources,
)


def system(cpus: int, available_gib: int, total_gib: int | None = None) -> SystemResources:
    total = total_gib or available_gib
    return SystemResources(
        hostname="fixture-host",
        logical_cpus=cpus,
        memory_total_bytes=total * GIB,
        memory_available_bytes=available_gib * GIB,
        tmp_dir="/tmp",
        tmp_free_bytes=500 * GIB,
        cwd_free_bytes=500 * GIB,
    )


class ResourcePlannerTests(unittest.TestCase):
    def test_tier2_auto_profile(self):
        p = plan_resources(read_count=13_959, system=system(24, 128))
        self.assertEqual((p.shards, p.max_unit_workers, p.caller_workers), (1, 1, 2))

    def test_tier3_auto_profile(self):
        p = plan_resources(read_count=100_000, system=system(24, 128))
        self.assertEqual((p.shards, p.max_unit_workers, p.caller_workers), (12, 3, 2))

    def test_500k_auto_profile(self):
        p = plan_resources(read_count=500_000, system=system(24, 128))
        self.assertEqual((p.shards, p.max_unit_workers, p.caller_workers), (12, 12, 2))

    def test_fullscale_auto_profile(self):
        p = plan_resources(read_count=5_312_696, system=system(24, 128))
        self.assertEqual((p.shards, p.max_unit_workers, p.caller_workers), (144, 12, 2))

    def test_lower_memory_reduces_concurrency(self):
        p = plan_resources(read_count=5_312_696, system=system(8, 32))
        self.assertEqual(p.shards, 144)
        self.assertEqual(p.max_unit_workers, 3)
        self.assertEqual(p.caller_workers, 2)
        self.assertLessEqual(p.projected_active_cpu_threads, p.threads_budget)
        self.assertLessEqual(p.projected_active_memory_bytes, p.memory_budget_bytes * 0.70)

    def test_manual_golden_profile_is_preserved(self):
        p = plan_resources(
            read_count=100_000,
            system=system(24, 128),
            shards=12,
            max_unit_workers=3,
            caller_workers=2,
        )
        self.assertEqual(p.mode, "MANUAL_CORE_SCHEDULING")
        self.assertEqual((p.shards, p.max_unit_workers, p.caller_workers), (12, 3, 2))

    def test_unsafe_override_is_rejected(self):
        with self.assertRaises(ResourcePlanError):
            plan_resources(
                read_count=5_312_696,
                system=system(8, 16),
                max_unit_workers=12,
                caller_workers=2,
            )

    def test_fastq_count(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "reads.fastq"
            p.write_text(
                "@r1\nACGT\n+\nIIII\n@r2\nTGCA\n+\nIIII\n",
                encoding="utf-8",
            )
            n, method = count_fastq_reads(p, threads=2)
            self.assertEqual(n, 2)
            self.assertIn(method, {"SEQKIT_STATS_TSV", "PYTHON_FASTQ_LINE_COUNT_FALLBACK"})


if __name__ == "__main__":
    unittest.main()
