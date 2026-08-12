from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import subprocess
import sys
import time
from pathlib import Path

STAGE_VERSION = "rnatr_stage15a_validate_package_parallel_v0.2.2"
EXPECTED = {
    "rnatr_v041_validate_package.py": "e978b109d094f665ec62387ffda35c81d0aa9e8156972069f18a1b0b6c49bba5",
    "rnatr_v042_validate_flank_uniqueness.py": "039024835de2bc1f096e562eed69788ecad9e481575b1b8cd58241edf2e87ab5",
    "rnatr_v042_validate_package.py": "45c3995550f57a65b3fec4aab7471d57b7000e19471d4c5cf7f3ae055426984e",
}
EXPECTED_MARKERS = {
    "rnatr_v041_validate_package.py": "RNATR_V041_PACKAGE_VALIDATION_PASS",
    "rnatr_v042_validate_flank_uniqueness.py": "RNATR_V042_FLANK_UNIQUENESS_VALIDATION_PASS",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run_component(path: Path, package_dir: Path) -> dict[str, object]:
    started = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, str(path), "--package-dir", str(package_dir)],
        text=True,
        capture_output=True,
    )
    return {
        "name": path.name,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "elapsed_seconds": time.perf_counter() - started,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-dir", required=True, type=Path)
    parser.add_argument("--schema-dir", required=True, type=Path)
    args = parser.parse_args()
    package_dir = args.package_dir.resolve()
    schema_dir = args.schema_dir.resolve()
    if not package_dir.is_dir():
        print(f"ERROR: package directory missing: {package_dir}", file=sys.stderr)
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
    components = [
        paths["rnatr_v041_validate_package.py"],
        paths["rnatr_v042_validate_flank_uniqueness.py"],
    ]
    started = time.perf_counter()
    results: dict[str, dict[str, object]] = {}
    with cf.ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(run_component, path, package_dir): path.name for path in components}
        for future in cf.as_completed(futures):
            result = future.result()
            results[str(result["name"])] = result
    # Emit component output in the same logical order as the frozen wrapper.
    for path in components:
        result = results[path.name]
        if result["stdout"]:
            sys.stdout.write(str(result["stdout"]))
        if result["stderr"]:
            sys.stderr.write(str(result["stderr"]))
    failures: list[str] = []
    for path in components:
        result = results[path.name]
        marker = EXPECTED_MARKERS[path.name]
        if int(result["returncode"]) != 0 or marker not in str(result["stdout"]):
            failures.append(path.name)
    if failures:
        print("RNATR_V042_PARALLEL_PACKAGE_VALIDATION_FAIL\t" + ",".join(failures), file=sys.stderr)
        return 2
    elapsed = time.perf_counter() - started
    print(f"RNATR_V042_PARALLEL_COMPONENT_SECONDS\t{elapsed:.9f}")
    for path in components:
        result = results[path.name]
        print(f"RNATR_V042_PARALLEL_COMPONENT\t{path.name}\t{float(result['elapsed_seconds']):.9f}")
    print(f"RNATR_V042_PARALLEL_VALIDATOR_VERSION\t{STAGE_VERSION}")
    print("RNATR_V042_PACKAGE_VALIDATION_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
