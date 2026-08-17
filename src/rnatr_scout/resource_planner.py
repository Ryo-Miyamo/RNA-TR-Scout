"""Host resource detection and conservative public execution planning."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import gzip
import json
import math
import os
from pathlib import Path
import shutil
import socket
import subprocess

POLICY_VERSION = "rnatr_resource_policy_v0.1.0"
GIB = 1024 ** 3
EMPIRICAL_ACTIVE_UNIT_GIB = 6.0
AUTO_MEMORY_FRACTION = 0.70
MIN_MEMORY_GIB = 8.0
VALIDATED_READ_SCALE_MAX = 5_500_000


class ResourcePlanError(RuntimeError):
    pass


@dataclass(frozen=True)
class SystemResources:
    hostname: str
    logical_cpus: int
    memory_total_bytes: int
    memory_available_bytes: int
    tmp_dir: str
    tmp_free_bytes: int
    cwd_free_bytes: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ResourcePlan:
    policy_version: str
    mode: str
    input_reads: int
    threads_budget: int
    memory_budget_bytes: int
    shards: int
    max_unit_workers: int
    caller_workers: int
    mapping_threads: int
    tmp_dir: str
    estimated_active_unit_memory_bytes: int
    projected_active_memory_bytes: int
    projected_active_cpu_threads: int
    manual_overrides: dict
    warnings: tuple[str, ...]
    system: SystemResources

    def to_dict(self) -> dict:
        obj = asdict(self)
        obj["warnings"] = list(self.warnings)
        return obj


def _read_meminfo() -> tuple[int, int]:
    values: dict[str, int] = {}
    path = Path("/proc/meminfo")
    if path.is_file():
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if ":" not in raw:
                continue
            key, rest = raw.split(":", 1)
            fields = rest.strip().split()
            if not fields:
                continue
            try:
                value = int(fields[0]) * 1024
            except ValueError:
                continue
            values[key] = value
    total = values.get("MemTotal", 0)
    available = values.get("MemAvailable", values.get("MemFree", 0))
    if total <= 0:
        raise ResourcePlanError("could not determine system RAM from /proc/meminfo")
    if available <= 0:
        available = total
    return total, min(total, available)


def detect_system_resources(
    *,
    tmp_dir: Path | None = None,
    cwd: Path | None = None,
) -> SystemResources:
    logical = os.cpu_count() or 1
    total, available = _read_meminfo()
    requested_tmp = tmp_dir or Path(os.environ.get("TMPDIR", "/tmp"))
    tmp = requested_tmp.expanduser().resolve()
    if not tmp.is_dir():
        raise ResourcePlanError(f"tmp directory does not exist: {tmp}")
    if not os.access(tmp, os.W_OK | os.X_OK):
        raise ResourcePlanError(f"tmp directory is not writable/searchable: {tmp}")
    cwd_path = (cwd or Path.cwd()).expanduser().resolve()
    if not cwd_path.exists():
        raise ResourcePlanError(f"resource-report path does not exist: {cwd_path}")
    return SystemResources(
        hostname=socket.gethostname(),
        logical_cpus=max(1, logical),
        memory_total_bytes=total,
        memory_available_bytes=available,
        tmp_dir=str(tmp),
        tmp_free_bytes=shutil.disk_usage(tmp).free,
        cwd_free_bytes=shutil.disk_usage(cwd_path).free,
    )


def count_fastq_reads(path: Path, *, threads: int = 1) -> tuple[int, str]:
    fastq = path.expanduser().resolve()
    if not fastq.is_file() or fastq.is_symlink():
        raise ResourcePlanError(f"FASTQ missing/invalid: {fastq}")

    seqkit = shutil.which("seqkit")
    if seqkit:
        proc = subprocess.run(
            [seqkit, "stats", "-T", "-j", str(max(1, min(8, threads))), str(fastq)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if proc.returncode == 0:
            lines = [line for line in proc.stdout.splitlines() if line.strip()]
            if len(lines) >= 2:
                header = lines[0].split("\t")
                row = lines[1].split("\t")
                if "num_seqs" in header and len(row) == len(header):
                    value = row[header.index("num_seqs")].replace(",", "")
                    try:
                        n = int(value)
                    except ValueError:
                        n = -1
                    if n >= 0:
                        return n, "SEQKIT_STATS_TSV"

    opener = gzip.open if fastq.suffix == ".gz" else open
    line_count = 0
    with opener(fastq, "rb") as fh:
        for _ in fh:
            line_count += 1
    if line_count % 4 != 0:
        raise ResourcePlanError(
            f"FASTQ line count is not divisible by four: {line_count}: {fastq}"
        )
    return line_count // 4, "PYTHON_FASTQ_LINE_COUNT_FALLBACK"


def _auto_shards(reads: int) -> int:
    if reads <= 25_000:
        return 1
    if reads <= 600_000:
        return 12
    raw = max(12, math.ceil(reads / 40_000))
    return int(math.ceil(raw / 12) * 12)


def _auto_work_limit(reads: int) -> int:
    if reads <= 25_000:
        return 1
    if reads <= 150_000:
        return 3
    return min(12, max(3, math.ceil(reads / 40_000)))


def plan_resources(
    *,
    read_count: int,
    system: SystemResources,
    shards: int | None = None,
    max_unit_workers: int | None = None,
    caller_workers: int | None = None,
    threads: int | None = None,
    memory_gb: float | None = None,
    force_resource_overrides: bool = False,
) -> ResourcePlan:
    if read_count < 1:
        raise ResourcePlanError("input read count must be >= 1")
    for label, value in (
        ("shards", shards),
        ("max-unit-workers", max_unit_workers),
        ("caller-workers", caller_workers),
        ("threads", threads),
    ):
        if value is not None and value < 1:
            raise ResourcePlanError(f"{label} must be >= 1")
    if memory_gb is not None and memory_gb <= 0:
        raise ResourcePlanError("memory-gb must be > 0")

    manual: dict[str, object] = {}
    if threads is not None:
        manual["threads"] = threads
    if memory_gb is not None:
        manual["memory_gb"] = memory_gb
    if shards is not None:
        manual["shards"] = shards
    if max_unit_workers is not None:
        manual["max_unit_workers"] = max_unit_workers
    if caller_workers is not None:
        manual["caller_workers"] = caller_workers

    detected_available_gib = system.memory_available_bytes / GIB
    auto_threads = min(
        system.logical_cpus,
        max(2, int(max(MIN_MEMORY_GIB, detected_available_gib) // 2)),
    )
    thread_budget = threads if threads is not None else max(1, auto_threads)
    if thread_budget > system.logical_cpus and not force_resource_overrides:
        raise ResourcePlanError(
            f"threads override exceeds detected logical CPUs: {thread_budget} > {system.logical_cpus}; "
            "use --force-resource-overrides only if intentional"
        )

    memory_budget = (
        int(memory_gb * GIB)
        if memory_gb is not None
        else system.memory_available_bytes
    )
    if memory_budget < MIN_MEMORY_GIB * GIB and not force_resource_overrides:
        raise ResourcePlanError(
            f"available/requested memory is below conservative {MIN_MEMORY_GIB:.0f} GiB planning floor"
        )
    if (
        memory_gb is not None
        and memory_budget > system.memory_available_bytes
        and not force_resource_overrides
    ):
        raise ResourcePlanError(
            "memory-gb override exceeds currently available RAM; use --force-resource-overrides only if intentional"
        )

    selected_caller = caller_workers if caller_workers is not None else (2 if thread_budget >= 2 else 1)
    auto_unit_mem = int(EMPIRICAL_ACTIVE_UNIT_GIB * GIB)
    by_cpu = max(1, thread_budget // selected_caller)
    by_mem = max(1, int((memory_budget * AUTO_MEMORY_FRACTION) // auto_unit_mem))
    by_work = _auto_work_limit(read_count)
    selected_unit = (
        max_unit_workers
        if max_unit_workers is not None
        else max(1, min(12, by_cpu, by_mem, by_work))
    )
    selected_shards = shards if shards is not None else _auto_shards(read_count)
    if selected_shards < selected_unit and not force_resource_overrides:
        raise ResourcePlanError(
            f"shards must be >= max-unit-workers: {selected_shards} < {selected_unit}"
        )

    active_threads = selected_unit * selected_caller
    projected_mem = selected_unit * auto_unit_mem
    if active_threads > thread_budget and not force_resource_overrides:
        raise ResourcePlanError(
            f"selected worker plan exceeds threads budget: {active_threads} > {thread_budget}"
        )
    if projected_mem > memory_budget * AUTO_MEMORY_FRACTION and not force_resource_overrides:
        raise ResourcePlanError(
            "selected worker plan exceeds conservative active-memory planning fraction; "
            "reduce max-unit-workers or use --force-resource-overrides if intentional"
        )

    mapping_threads = max(2, min(24, thread_budget))
    warnings: list[str] = []
    if read_count > VALIDATED_READ_SCALE_MAX:
        warnings.append(
            "INPUT_ABOVE_EMPIRICALLY_VALIDATED_5_31M_SCALE_RESOURCE_POLICY_IS_EXTRAPOLATED"
        )
    warnings.append(
        "DISK_FREE_SPACE_IS_REPORTED_NOT_HARD_GATED_BECAUSE_FULLSCALE_PEAK_DISK_IS_NOT_YET_FORMALLY_BENCHMARKED"
    )
    if force_resource_overrides:
        warnings.append("FORCED_RESOURCE_OVERRIDE_SAFETY_GUARDS_BYPASSED")

    mode = "AUTO"
    if manual:
        mode = "AUTO_WITH_MANUAL_OVERRIDES"
    if all(x is not None for x in (shards, max_unit_workers, caller_workers)):
        mode = "MANUAL_CORE_SCHEDULING"

    return ResourcePlan(
        policy_version=POLICY_VERSION,
        mode=mode,
        input_reads=read_count,
        threads_budget=thread_budget,
        memory_budget_bytes=memory_budget,
        shards=selected_shards,
        max_unit_workers=selected_unit,
        caller_workers=selected_caller,
        mapping_threads=mapping_threads,
        tmp_dir=system.tmp_dir,
        estimated_active_unit_memory_bytes=auto_unit_mem,
        projected_active_memory_bytes=projected_mem,
        projected_active_cpu_threads=active_threads,
        manual_overrides=manual,
        warnings=tuple(warnings),
        system=system,
    )


def write_plan_json(path: Path, plan: ResourcePlan, *, count_method: str) -> None:
    target = path.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    obj = plan.to_dict()
    obj["read_count_method"] = count_method
    tmp = target.with_name("." + target.name + ".part")
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, target)


def load_plan_json(path: Path) -> dict:
    target = path.expanduser().resolve()
    if not target.is_file() or target.is_symlink():
        raise ResourcePlanError(f"resource plan missing/invalid: {target}")
    obj = json.loads(target.read_text(encoding="utf-8"))
    if obj.get("policy_version") != POLICY_VERSION:
        raise ResourcePlanError(
            f"unsupported resource-plan policy: {obj.get('policy_version')!r}"
        )
    return obj
