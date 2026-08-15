"""Public source-checkout workflows for RNA-TR-Scout."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
import subprocess
import sys

PUBLIC_WORKFLOW_VERSION = "rnatr_public_workflow_v0.1.0"

RESOURCE_INSTALLER_REL = Path(
    "scripts/rnatr_install_standard_resources_v0.1.1.py"
)
RESOURCE_PROFILE_REL = Path(
    "config/resources/standard_v0.1.1/validated_profile.json"
)
MAPPING_ADAPTER_REL = Path("scripts/rnatr_map_ont_cdna_v0.2.0.py")
CORE_ENTRY_REL = Path("scripts/rnatr_core_production_entry_v0.1.0.py")


class PublicWorkflowError(RuntimeError):
    pass


def project_root() -> Path:
    root = Path(__file__).resolve().parents[2]
    required = (
        root / "pyproject.toml",
        root / RESOURCE_INSTALLER_REL,
        root / MAPPING_ADAPTER_REL,
        root / CORE_ENTRY_REL,
    )
    if not all(path.is_file() and not path.is_symlink() for path in required):
        raise PublicWorkflowError(
            "validated public workflow requires an RNA-TR-Scout source checkout"
        )
    return root


def ensure_regular(path: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_file() or resolved.is_symlink():
        raise PublicWorkflowError(
            f"{label} missing/invalid regular file: {resolved}"
        )
    return resolved


def run_command(
    cmd: list[str],
    *,
    cwd: Path,
    dry_run: bool = False,
) -> int:
    if dry_run:
        print("COMMAND\t" + shlex.join(cmd))
        return 0
    proc = subprocess.run(cmd, cwd=str(cwd))
    return proc.returncode


def add_public_subparsers(
    subparsers: argparse._SubParsersAction,
) -> None:
    resources = subparsers.add_parser(
        "resources-status",
        help="Check whether the standard validated runtime resources are ready",
    )
    resources.add_argument(
        "--json",
        action="store_true",
        help="Print the resource inspection JSON returned by the installer",
    )

    mapping = subparsers.add_parser(
        "map",
        help="Map ONT-cDNA FASTQ with the validated/custom-compatible mapper",
    )
    mapping.add_argument("--fastq", required=True, type=Path)
    mapping.add_argument("--output-bam", required=True, type=Path)
    mapping.add_argument("--sample-id", required=True)
    mapping.add_argument("--run-id")
    mapping.add_argument("--expected-fastq-sha256", default="")
    mapping.add_argument("--work-dir", type=Path)
    mapping.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the internal validated command without executing it",
    )

    workflow = subparsers.add_parser(
        "run",
        help=(
            "Run RNA-TR-Scout from source FASTQ, optionally using an existing "
            "mapped BAM. If --bam is omitted, validated ONT-cDNA mapping runs first."
        ),
    )
    workflow.add_argument("--fastq", required=True, type=Path)
    workflow.add_argument("--bam", type=Path)
    workflow.add_argument("--sample-id", required=True)
    workflow.add_argument("--run-id")
    workflow.add_argument("--output-dir", required=True, type=Path)
    workflow.add_argument("--resume", action="store_true")
    workflow.add_argument("--shards", type=int, default=12)
    workflow.add_argument("--max-unit-workers", type=int, default=3)
    workflow.add_argument("--caller-workers", type=int, default=2)
    workflow.add_argument("--pythonhashseed", default="0")
    workflow.add_argument("--expected-bam-sha256", default="")
    workflow.add_argument("--expected-fastq-sha256", default="")
    workflow.add_argument(
        "--dry-run",
        action="store_true",
        help="Print mapping/Core commands without executing them",
    )


def resources_status(arguments: argparse.Namespace) -> int:
    root = project_root()
    installer = root / RESOURCE_INSTALLER_REL
    profile = root / RESOURCE_PROFILE_REL

    proc = subprocess.run(
        [
            sys.executable,
            str(installer),
            "--project-root",
            str(root),
            "--validated-profile",
            str(profile),
            "--inspect-only",
        ],
        cwd=str(root),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if arguments.json:
        print(proc.stdout, end="")
    elif proc.returncode == 0:
        try:
            obj = json.loads(proc.stdout)
        except json.JSONDecodeError:
            print(proc.stdout, end="")
            return 1
        print("RNATR_RESOURCES\tPASS")
        print(f"status\t{obj.get('status', '')}")
        print(
            "reference\t"
            + str(obj.get("reference", {}).get("status", ""))
        )
        print(
            "catalog\t"
            + str(obj.get("catalog", {}).get("status", ""))
        )
    else:
        print(proc.stdout, end="", file=sys.stderr)

    return proc.returncode


def mapping_command(
    *,
    root: Path,
    fastq: Path,
    output_bam: Path,
    sample_id: str,
    run_id: str,
    expected_fastq_sha256: str,
    work_dir: Path | None,
) -> list[str]:
    adapter = root / MAPPING_ADAPTER_REL
    cmd = [
        sys.executable,
        str(adapter),
        "--run",
        "--project-root",
        str(root),
        "--fastq",
        str(fastq),
        "--output-bam",
        str(output_bam),
        "--run-id",
        run_id,
        "--sample-id",
        sample_id,
    ]
    if expected_fastq_sha256:
        cmd += [
            "--expected-fastq-sha256",
            expected_fastq_sha256,
        ]
    if work_dir is not None:
        cmd += ["--work-dir", str(work_dir)]
    return cmd


def map_fastq(arguments: argparse.Namespace) -> int:
    root = project_root()
    fastq = ensure_regular(arguments.fastq, "FASTQ")
    output_bam = arguments.output_bam.expanduser().resolve()
    run_id = arguments.run_id or arguments.sample_id
    work_dir = (
        arguments.work_dir.expanduser().resolve()
        if arguments.work_dir
        else None
    )

    cmd = mapping_command(
        root=root,
        fastq=fastq,
        output_bam=output_bam,
        sample_id=arguments.sample_id,
        run_id=run_id,
        expected_fastq_sha256=arguments.expected_fastq_sha256,
        work_dir=work_dir,
    )
    rc = run_command(cmd, cwd=root, dry_run=arguments.dry_run)
    if rc == 0 and not arguments.dry_run:
        print("RNATR_PUBLIC_MAP\tPASS")
        print(f"run_id\t{run_id}")
        print(f"bam\t{output_bam}")
    return rc


def core_command(
    *,
    root: Path,
    mode: str,
    bam: Path,
    fastq: Path,
    sample_id: str,
    run_id: str,
    work_root: Path,
    output_root: Path,
    control_root: Path,
    shards: int,
    max_unit_workers: int,
    caller_workers: int,
    pythonhashseed: str,
    expected_bam_sha256: str,
    expected_fastq_sha256: str,
) -> list[str]:
    entry = root / CORE_ENTRY_REL
    cmd = [
        sys.executable,
        str(entry),
        mode,
        "--project-root",
        str(root),
        "--bam",
        str(bam),
        "--reads-fastq",
        str(fastq),
        "--run-id",
        run_id,
        "--sample-id",
        sample_id,
        "--work-root",
        str(work_root),
        "--output-root",
        str(output_root),
        "--control-root",
        str(control_root),
        "--shards",
        str(shards),
        "--max-unit-workers",
        str(max_unit_workers),
        "--caller-workers",
        str(caller_workers),
        "--pythonhashseed",
        str(pythonhashseed),
    ]
    if expected_bam_sha256:
        cmd += ["--expected-bam-sha256", expected_bam_sha256]
    if expected_fastq_sha256:
        cmd += ["--expected-fastq-sha256", expected_fastq_sha256]
    return cmd


def run_workflow(arguments: argparse.Namespace) -> int:
    if (
        arguments.shards < 1
        or arguments.max_unit_workers < 1
        or arguments.caller_workers < 1
    ):
        raise PublicWorkflowError(
            "shards/max-unit-workers/caller-workers must be >= 1"
        )

    root = project_root()
    fastq = ensure_regular(arguments.fastq, "source FASTQ")
    run_id = arguments.run_id or arguments.sample_id
    output_dir = arguments.output_dir.expanduser().resolve()

    final_root = output_dir / "final"
    work_root = output_dir / "work" / "core"
    control_root = output_dir / "work" / "control"

    mapping_performed = False
    input_mode = "BAM_PLUS_FASTQ"

    if arguments.bam is not None:
        bam = ensure_regular(arguments.bam, "mapped BAM")
    else:
        input_mode = "FASTQ_AUTO_MAPPING"
        bam = output_dir / "mapping" / f"{run_id}.sorted.bam"

        if arguments.resume:
            bam = ensure_regular(
                bam,
                "resume mapped BAM created by the prior FASTQ-mode run",
            )
        else:
            if output_dir.exists():
                raise PublicWorkflowError(
                    "new FASTQ-mode run requires an unused --output-dir"
                )
            map_cmd = mapping_command(
                root=root,
                fastq=fastq,
                output_bam=bam,
                sample_id=arguments.sample_id,
                run_id=run_id,
                expected_fastq_sha256=(
                    arguments.expected_fastq_sha256
                ),
                work_dir=output_dir / "work" / "mapping",
            )
            rc = run_command(
                map_cmd,
                cwd=root,
                dry_run=arguments.dry_run,
            )
            if rc != 0:
                return rc
            mapping_performed = True

    if not arguments.resume and arguments.bam is not None:
        if output_dir.exists():
            raise PublicWorkflowError(
                "new BAM-mode run requires an unused --output-dir"
            )

    mode = "--resume" if arguments.resume else "--start"
    core_cmd = core_command(
        root=root,
        mode=mode,
        bam=bam,
        fastq=fastq,
        sample_id=arguments.sample_id,
        run_id=run_id,
        work_root=work_root,
        output_root=final_root,
        control_root=control_root,
        shards=arguments.shards,
        max_unit_workers=arguments.max_unit_workers,
        caller_workers=arguments.caller_workers,
        pythonhashseed=arguments.pythonhashseed,
        expected_bam_sha256=arguments.expected_bam_sha256,
        expected_fastq_sha256=arguments.expected_fastq_sha256,
    )
    rc = run_command(
        core_cmd,
        cwd=root,
        dry_run=arguments.dry_run,
    )
    if rc != 0:
        return rc

    if arguments.dry_run:
        print("RNATR_PUBLIC_RUN_DRY_RUN\tPASS")
        print(f"input_mode\t{input_mode}")
        print(f"run_id\t{run_id}")
        return 0

    print("RNATR_PUBLIC_RUN\tPASS")
    print(f"public_workflow_version\t{PUBLIC_WORKFLOW_VERSION}")
    print(f"input_mode\t{input_mode}")
    print(f"mode\t{'RESUME' if arguments.resume else 'START'}")
    print(f"mapping_performed\t{str(mapping_performed).lower()}")
    print(f"run_id\t{run_id}")
    print(f"sample_id\t{arguments.sample_id}")
    print(f"bam\t{bam}")
    print(f"final\t{final_root}")
    return 0


def dispatch_public_command(
    arguments: argparse.Namespace,
) -> int | None:
    if arguments.command == "resources-status":
        return resources_status(arguments)
    if arguments.command == "map":
        return map_fastq(arguments)
    if arguments.command == "run":
        return run_workflow(arguments)
    return None
