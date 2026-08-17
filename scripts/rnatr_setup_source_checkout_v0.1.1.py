#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile

VERSION = "rnatr_setup_source_checkout_v0.1.1"
EXPECTED_PACKAGE_VERSION = "0.5.0"
EXPECTED_NATIVE_SHA256 = (
    "9745a4e33e9a899ec78417b499ccc35f770b7fd7adfffe1ab533fa14ead3ae69"
)

ENVIRONMENT_FILE = "environment.yml"
RESOURCE_INSTALLER_REL = Path("scripts/rnatr_install_standard_resources_v0.1.1.py")
RESOURCE_PROFILE_REL = Path(
    "config/resources/standard_v0.1.1/validated_profile.json"
)
CORE_RUNNER_REL = Path("scripts/rnatr_core_generic_sharded_v0.1.2.py")
MAPPING_ADAPTER_REL = Path("scripts/rnatr_map_ont_cdna_v0.2.0.py")
NATIVE_REL = Path(
    "src/rnatr_scout/general_caller/native_v0.4.1/"
    "librnatr_native_periodic_kernel_v0.1.0.so"
)

class SetupError(RuntimeError):
    pass

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def ensure_regular(path: Path) -> None:
    if not path.is_file() or path.is_symlink():
        raise SetupError(f"required regular file missing/invalid: {path}")

def run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    p = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if check and p.returncode != 0:
        raise SetupError(
            f"command failed rc={p.returncode}: {' '.join(cmd)}\n{p.stdout}"
        )
    return p

def find_env_manager(explicit: str) -> tuple[str, str]:
    candidates = [explicit] if explicit != "auto" else ["mamba", "conda"]
    for name in candidates:
        path = shutil.which(name)
        if not path:
            continue
        p = run([path, "--version"], check=False)
        if p.returncode == 0:
            return path, p.stdout.strip().splitlines()[0]
    if explicit == "auto":
        raise SetupError(
            "mamba or conda is required to create the validated environment"
        )
    raise SetupError(f"requested environment manager not available: {explicit}")

def run_in_env(
    manager: str,
    prefix: Path,
    argv: list[str],
    *,
    cwd: Path,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return run(
        [manager, "run", "--prefix", str(prefix)] + argv,
        cwd=cwd,
        check=check,
    )

def validate_platform() -> dict:
    system = platform.system()
    machine = platform.machine()
    if system != "Linux":
        raise SetupError(
            f"validated source-checkout setup currently requires Linux; observed {system}"
        )
    if machine not in {"x86_64", "AMD64"}:
        raise SetupError(
            "validated native kernel currently requires x86-64; "
            f"observed {machine}"
        )
    return {"system": system, "machine": machine}

def ensure_git_checkout(root: Path) -> str:
    p = run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=root,
        check=False,
    )
    if p.returncode != 0:
        raise SetupError("project root is not a Git source checkout")
    actual = Path(p.stdout.strip()).resolve()
    if actual != root:
        raise SetupError(
            f"--project-root is not Git toplevel: {root} != {actual}"
        )
    return run(["git", "rev-parse", "HEAD"], cwd=root).stdout.strip()

def env_is_present(prefix: Path) -> bool:
    return (
        prefix.is_dir()
        and (prefix / "conda-meta/history").is_file()
    )

def create_environment(
    manager: str,
    prefix: Path,
    environment_file: Path,
) -> str:
    if prefix.exists():
        if env_is_present(prefix):
            return "PASS_ALREADY_PRESENT"
        raise SetupError(
            f"environment prefix exists but is not a conda environment: {prefix}"
        )

    prefix.parent.mkdir(parents=True, exist_ok=True)
    p = run(
        [
            manager,
            "env",
            "create",
            "--prefix",
            str(prefix),
            "--file",
            str(environment_file),
            "-y",
        ],
        check=False,
    )
    if p.returncode != 0:
        raise SetupError("environment creation failed:\n" + p.stdout)
    if not env_is_present(prefix):
        raise SetupError("environment manager returned success but env is missing")
    return "PASS_CREATED"

def editable_install_state(
    manager: str,
    prefix: Path,
    root: Path,
) -> str:
    probe = run_in_env(
        manager,
        prefix,
        [
            "python",
            "-c",
            (
                "from pathlib import Path; import rnatr_scout; "
                "print(Path(rnatr_scout.__file__).resolve())"
            ),
        ],
        cwd=root,
        check=False,
    )
    if probe.returncode == 0 and probe.stdout.strip():
        module_path = Path(probe.stdout.strip().splitlines()[-1]).resolve()
        try:
            module_path.relative_to(root / "src")
        except ValueError:
            pass
        else:
            return "PASS_ALREADY_PRESENT"

    p = run_in_env(
        manager,
        prefix,
        [
            "python",
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--editable",
            str(root),
        ],
        cwd=root,
        check=False,
    )
    if p.returncode != 0:
        raise SetupError("editable source-checkout install failed:\n" + p.stdout)

    verify = run_in_env(
        manager,
        prefix,
        [
            "python",
            "-c",
            (
                "from pathlib import Path; import rnatr_scout; "
                "print(Path(rnatr_scout.__file__).resolve())"
            ),
        ],
        cwd=root,
    )
    module_path = Path(verify.stdout.strip().splitlines()[-1]).resolve()
    try:
        module_path.relative_to(root / "src")
    except ValueError as exc:
        raise SetupError(
            f"package is not bound to this source checkout: {module_path}"
        ) from exc
    return "PASS_INSTALLED_EDITABLE"

def verify_tool_versions(
    manager: str,
    prefix: Path,
    root: Path,
) -> dict[str, str]:
    commands = {
        "python": ["python", "--version"],
        "samtools": ["samtools", "--version"],
        "bedtools": ["bedtools", "--version"],
        "minimap2": ["minimap2", "--version"],
        "pysam": [
            "python",
            "-c",
            "import pysam; print(pysam.__version__)",
        ],
    }
    observed = {}
    for logical, argv in commands.items():
        p = run_in_env(manager, prefix, argv, cwd=root)
        observed[logical] = p.stdout.strip().splitlines()[0]

    if observed["python"] != "Python 3.10.20":
        raise SetupError(f"Python version drift: {observed['python']}")
    if observed["samtools"] != "samtools 1.24":
        raise SetupError(f"samtools version drift: {observed['samtools']}")
    if observed["bedtools"] not in {"bedtools v2.31.1", "bedtools 2.31.1"}:
        raise SetupError(f"bedtools version drift: {observed['bedtools']}")
    if observed["minimap2"] != "2.31-r1302":
        raise SetupError(f"minimap2 version drift: {observed['minimap2']}")
    if observed["pysam"] != "0.24.0":
        raise SetupError(f"pysam version drift: {observed['pysam']}")
    return observed

def verify_package(
    manager: str,
    prefix: Path,
    root: Path,
) -> dict:
    version = run_in_env(
        manager,
        prefix,
        ["rnatr-scout", "version"],
        cwd=root,
    ).stdout.strip().splitlines()[-1]
    if version != EXPECTED_PACKAGE_VERSION:
        raise SetupError(
            f"rnatr-scout package version drift: {version} != "
            f"{EXPECTED_PACKAGE_VERSION}"
        )

    module_path_text = run_in_env(
        manager,
        prefix,
        [
            "python",
            "-c",
            (
                "from pathlib import Path; import rnatr_scout; "
                "print(Path(rnatr_scout.__file__).resolve())"
            ),
        ],
        cwd=root,
    ).stdout.strip().splitlines()[-1]
    module_path = Path(module_path_text).resolve()
    try:
        module_path.relative_to(root / "src")
    except ValueError as exc:
        raise SetupError(
            f"rnatr_scout import is not source-checkout bound: {module_path}"
        ) from exc

    return {
        "version": version,
        "module_path": str(module_path),
        "source_checkout_bound": True,
    }

def verify_native(
    manager: str,
    prefix: Path,
    root: Path,
) -> dict:
    native = root / NATIVE_REL
    ensure_regular(native)
    actual = sha256_file(native)
    if actual != EXPECTED_NATIVE_SHA256:
        raise SetupError(
            f"native kernel SHA drift: {actual} != {EXPECTED_NATIVE_SHA256}"
        )

    code = (
        "import ctypes, pathlib; "
        f"p=pathlib.Path({str(native)!r}); "
        "ctypes.CDLL(str(p)); print('NATIVE_LOAD\\tPASS')"
    )
    p = run_in_env(
        manager,
        prefix,
        ["python", "-c", code],
        cwd=root,
        check=False,
    )
    if p.returncode != 0 or "NATIVE_LOAD\tPASS" not in p.stdout:
        raise SetupError("native shared-object load failed:\n" + p.stdout)

    return {
        "path": str(NATIVE_REL),
        "sha256": actual,
        "load": "PASS",
    }

def run_self_tests(
    manager: str,
    prefix: Path,
    root: Path,
) -> dict[str, str]:
    core = root / CORE_RUNNER_REL
    mapper = root / MAPPING_ADAPTER_REL
    ensure_regular(core)
    ensure_regular(mapper)

    core_p = run_in_env(
        manager,
        prefix,
        ["python", str(core), "--self-test"],
        cwd=root,
        check=False,
    )
    if core_p.returncode != 0 or "SELF_TEST\tPASS" not in core_p.stdout:
        raise SetupError("Core self-test failed:\n" + core_p.stdout)

    map_p = run_in_env(
        manager,
        prefix,
        ["python", str(mapper), "--self-test"],
        cwd=root,
        check=False,
    )
    if map_p.returncode != 0 or "SELF_TEST\tPASS" not in map_p.stdout:
        raise SetupError("mapping adapter self-test failed:\n" + map_p.stdout)

    return {
        "core_generic_sharded": "PASS",
        "mapping_ont_cdna": "PASS",
    }

def install_or_inspect_resources(
    manager: str,
    prefix: Path,
    root: Path,
    args: argparse.Namespace,
) -> dict:
    installer = root / RESOURCE_INSTALLER_REL
    profile = root / RESOURCE_PROFILE_REL
    ensure_regular(installer)
    ensure_regular(profile)

    if args.skip_resources:
        return {
            "status": "SKIPPED_BY_REQUEST",
            "profile_status": "NOT_CHECKED",
        }

    cmd = [
        "python",
        str(installer),
        "--project-root",
        str(root),
        "--validated-profile",
        str(profile),
    ]
    if args.catalog_bundle is not None:
        cmd += ["--catalog-bundle", str(args.catalog_bundle.resolve())]
    if args.reference_source_dir is not None:
        cmd += [
            "--reference-source-dir",
            str(args.reference_source_dir.resolve()),
        ]
    if args.reference_cache_dir is not None:
        cmd += [
            "--cache-dir",
            str(args.reference_cache_dir.expanduser().resolve()),
        ]
    if args.catalog_cache_dir is not None:
        cmd += [
            "--catalog-cache-dir",
            str(args.catalog_cache_dir.expanduser().resolve()),
        ]

    p = run_in_env(
        manager,
        prefix,
        cmd,
        cwd=root,
        check=False,
    )
    if p.returncode != 0:
        raise SetupError("standard resource setup failed:\n" + p.stdout)
    if "profile_status\tPASS_STANDARD_RESOURCES_READY" not in p.stdout:
        raise SetupError(
            "standard resource setup did not report READY:\n" + p.stdout
        )

    inspect = run_in_env(
        manager,
        prefix,
        [
            "python",
            str(installer),
            "--project-root",
            str(root),
            "--validated-profile",
            str(profile),
            "--inspect-only",
        ],
        cwd=root,
        check=False,
    )
    if inspect.returncode != 0:
        raise SetupError("resource inspect-only failed:\n" + inspect.stdout)
    obj = json.loads(inspect.stdout)
    if obj.get("status") != "PASS_STANDARD_RESOURCES_READY":
        raise SetupError("resource inspect-only status is not READY")

    return {
        "status": "PASS",
        "profile_status": "PASS_STANDARD_RESOURCES_READY",
        "reference_status": obj["reference"]["status"],
        "catalog_status": obj["catalog"]["status"],
    }

def verify_only(
    manager: str,
    prefix: Path,
    root: Path,
    args: argparse.Namespace,
) -> dict:
    if not env_is_present(prefix):
        raise SetupError(f"validated environment missing: {prefix}")

    tools = verify_tool_versions(manager, prefix, root)
    package = verify_package(manager, prefix, root)
    native = verify_native(manager, prefix, root)
    self_tests = run_self_tests(manager, prefix, root)

    if args.skip_resources:
        resources = {
            "status": "SKIPPED_BY_REQUEST",
            "profile_status": "NOT_CHECKED",
        }
    else:
        installer = root / RESOURCE_INSTALLER_REL
        profile = root / RESOURCE_PROFILE_REL
        ensure_regular(installer)
        ensure_regular(profile)

        inspect = run_in_env(
            manager,
            prefix,
            [
                "python",
                str(installer),
                "--project-root",
                str(root),
                "--validated-profile",
                str(profile),
                "--inspect-only",
            ],
            cwd=root,
            check=False,
        )
        if inspect.returncode != 0:
            raise SetupError(
                "resource inspect-only failed during verify-only:\n"
                + inspect.stdout
            )
        obj = json.loads(inspect.stdout)
        if obj.get("status") != "PASS_STANDARD_RESOURCES_READY":
            raise SetupError(
                "resource verify-only inspection is not READY"
            )
        resources = {
            "status": "PASS",
            "profile_status": "PASS_STANDARD_RESOURCES_READY",
            "reference_status": obj["reference"]["status"],
            "catalog_status": obj["catalog"]["status"],
        }

    return {
        "tools": tools,
        "package": package,
        "native": native,
        "self_tests": self_tests,
        "resources": resources,
    }

def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Prepare and verify the validated RNA-TR-Scout Linux x86-64 "
            "source-checkout environment and standard resources."
        )
    )
    ap.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
    )
    ap.add_argument(
        "--env-prefix",
        type=Path,
        default=Path.home()
        / ".local/share/rnatr-scout/envs/source-checkout-v0.1",
    )
    ap.add_argument(
        "--env-manager",
        choices=["auto", "mamba", "conda"],
        default="auto",
    )
    ap.add_argument("--catalog-bundle", type=Path)
    ap.add_argument("--reference-source-dir", type=Path)
    ap.add_argument("--reference-cache-dir", type=Path)
    ap.add_argument("--catalog-cache-dir", type=Path)
    ap.add_argument("--skip-resources", action="store_true")
    ap.add_argument("--verify-only", action="store_true")
    args = ap.parse_args()

    root = args.project_root.resolve()
    env_prefix = args.env_prefix.expanduser().resolve()
    environment_file = root / ENVIRONMENT_FILE
    ensure_regular(environment_file)

    platform_state = validate_platform()
    head = ensure_git_checkout(root)
    manager, manager_version = find_env_manager(args.env_manager)

    if args.verify_only:
        verified = verify_only(manager, env_prefix, root, args)
        print("RNATR_SOURCE_CHECKOUT_SETUP\tPASS")
        print(f"version\t{VERSION}")
        print("mode\tVERIFY_ONLY")
        print(f"git_head\t{head}")
        print(f"env_prefix\t{env_prefix}")
        print("environment\tPASS_ALREADY_PRESENT")
        print("editable_package\tPASS_ALREADY_PRESENT")
        print("native_load\tPASS")
        print("core_self_test\tPASS")
        print("mapping_self_test\tPASS")
        print(
            f"resources\t{verified['resources']['profile_status']}"
        )
        return 0

    environment_status = create_environment(
        manager,
        env_prefix,
        environment_file,
    )
    editable_status = editable_install_state(
        manager,
        env_prefix,
        root,
    )

    tools = verify_tool_versions(manager, env_prefix, root)
    package = verify_package(manager, env_prefix, root)
    native = verify_native(manager, env_prefix, root)
    self_tests = run_self_tests(manager, env_prefix, root)
    resources = install_or_inspect_resources(
        manager,
        env_prefix,
        root,
        args,
    )

    print("RNATR_SOURCE_CHECKOUT_SETUP\tPASS")
    print(f"version\t{VERSION}")
    print("mode\tSETUP")
    print(f"git_head\t{head}")
    print(f"platform\t{platform_state['system']}_{platform_state['machine']}")
    print(f"env_manager\t{manager_version}")
    print(f"env_prefix\t{env_prefix}")
    print(f"environment\t{environment_status}")
    print(f"editable_package\t{editable_status}")
    print(f"package_version\t{package['version']}")
    print("source_checkout_bound\ttrue")
    print("tool_versions\tPASS_VALIDATED")
    print("native_sha\tPASS_EXACT")
    print("native_load\tPASS")
    print(f"core_self_test\t{self_tests['core_generic_sharded']}")
    print(f"mapping_self_test\t{self_tests['mapping_ont_cdna']}")
    print(f"resources\t{resources['profile_status']}")
    print("wheel_required\tfalse")
    print("user_manages_sha\tfalse")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
