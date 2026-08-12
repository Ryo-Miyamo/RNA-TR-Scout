from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

STAGE_VERSION = "rnatr_stage15a_validate_package_parallel_v0.2.2.1"
EXPECTED = {
    "rnatr_v041_validate_package.py": "e978b109d094f665ec62387ffda35c81d0aa9e8156972069f18a1b0b6c49bba5",
    "rnatr_v042_validate_flank_uniqueness.py": "039024835de2bc1f096e562eed69788ecad9e481575b1b8cd58241edf2e87ab5",
    "rnatr_v042_validate_package.py": "45c3995550f57a65b3fec4aab7471d57b7000e19471d4c5cf7f3ae055426984e",
}


@dataclass(frozen=True)
class Component:
    name: str
    marker: str
    arguments: tuple[str, ...]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run_component(path: Path, component: Component) -> dict[str, object]:
    started = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, str(path), *component.arguments],
        text=True,
        capture_output=True,
    )
    return {
        "name": component.name,
        "marker": component.marker,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "elapsed_seconds": time.perf_counter() - started,
        "command": [sys.executable, str(path), *component.arguments],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-dir", required=True, type=Path)
    parser.add_argument("--schema-dir", required=True, type=Path)
    args = parser.parse_args()

    package_dir = args.package_dir.resolve()
    schema_dir = args.schema_dir.resolve()
    read_evidence = package_dir / "read_evidence.tsv.gz"

    if not package_dir.is_dir():
        print(f"ERROR: package directory missing: {package_dir}", file=sys.stderr)
        return 2
    if not read_evidence.is_file() or read_evidence.stat().st_size == 0:
        print(f"ERROR: read evidence input missing: {read_evidence}", file=sys.stderr)
        return 2

    paths = {name: schema_dir / name for name in EXPECTED}
    for name, path in paths.items():
        if not path.is_file() or path.stat().st_size == 0:
            print(f"ERROR: validator component missing: {path}", file=sys.stderr)
            return 2
        observed = sha256(path)
        if observed != EXPECTED[name]:
            print(f"ERROR: validator SHA mismatch: {path}: {observed}", file=sys.stderr)
            return 2

    # The two frozen components have different CLI contracts.
    # v0.2.2 incorrectly passed --package-dir to both.
    components = [
        Component(
            name="rnatr_v041_validate_package.py",
            marker="RNATR_V041_PACKAGE_VALIDATION_PASS",
            arguments=("--package-dir", str(package_dir)),
        ),
        Component(
            name="rnatr_v042_validate_flank_uniqueness.py",
            marker="RNATR_V042_FLANK_UNIQUENESS_VALIDATION_PASS",
            arguments=("--input", str(read_evidence)),
        ),
    ]

    started = time.perf_counter()
    results: dict[str, dict[str, object]] = {}
    with cf.ThreadPoolExecutor(max_workers=2) as pool:
        futures = {
            pool.submit(run_component, paths[item.name], item): item.name
            for item in components
        }
        for future in cf.as_completed(futures):
            result = future.result()
            results[str(result["name"])] = result

    # Preserve the frozen wrapper's logical output order.
    for item in components:
        result = results[item.name]
        if result["stdout"]:
            sys.stdout.write(str(result["stdout"]))
        if result["stderr"]:
            sys.stderr.write(str(result["stderr"]))

    failures: list[str] = []
    for item in components:
        result = results[item.name]
        if int(result["returncode"]) != 0 or item.marker not in str(result["stdout"]):
            failures.append(item.name)

    if failures:
        print(
            "RNATR_V042_PARALLEL_PACKAGE_VALIDATION_FAIL\t" + ",".join(failures),
            file=sys.stderr,
        )
        return 2

    elapsed = time.perf_counter() - started
    print(f"RNATR_V042_PARALLEL_COMPONENT_SECONDS\t{elapsed:.9f}")
    for item in components:
        result = results[item.name]
        print(
            f"RNATR_V042_PARALLEL_COMPONENT\t{item.name}"
            f"\t{float(result['elapsed_seconds']):.9f}"
        )
    print(f"RNATR_V042_PARALLEL_VALIDATOR_VERSION\t{STAGE_VERSION}")
    print("RNATR_V042_PACKAGE_VALIDATION_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
