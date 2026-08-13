#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import os
from pathlib import Path
import tarfile
import tempfile

VERSION = "rnatr_install_frozen_core_resources_v0.1.0"
EXPECTED = [('analysis_regions', 'catalogs/trexplorer_v2/rnatr_pilot_v03/final/TRExplorer_v2.rnatr_pilot_analysis_regions.final.tsv.gz', '562802c3757785d0ef7d4b7b10ac5582b53bdce1d380d76dccb15711a2ebf9d3'), ('disease_regions', 'catalogs/trexplorer_v2/rnatr_pilot_v03/final/STRchive_disease_regions.final.tsv.gz', '056ae07de7b8f6299fadcabfefb7b596bc2c5a35591c06870dbed4d7fb519796'), ('mapping_target_bed', 'catalogs/trexplorer_v2/rnatr_pilot_v03/final/RNA-TR-Scout_v0.3.mapping_target_regions.bed.gz', '6ec444b0ffcb9da4452b24d1654ed6c4b945c3cd3e8379e4e4cbe6e72931cfe2'), ('mapping_target_bed_index', 'catalogs/trexplorer_v2/rnatr_pilot_v03/final/RNA-TR-Scout_v0.3.mapping_target_regions.bed.gz.tbi', '9803a3b268e9a7ca30edbf4c312a0d60b90a9bb9c34fdcd243348caa9bc4e77d'), ('mapping_target_tsv', 'catalogs/trexplorer_v2/rnatr_pilot_v03/final/RNA-TR-Scout_v0.3.mapping_target_regions.tsv.gz', '3edffe6f5d31922ca0c58759186639e77f51c48745ac5e22ad3aad0a010fec75')]

class InstallError(RuntimeError):
    pass

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Install checksum-bound RNA-TR-Scout frozen Core catalog resources."
    )
    ap.add_argument("--bundle", type=Path, required=True)
    ap.add_argument("--project-root", type=Path, required=True)
    args = ap.parse_args()

    root = args.project_root.resolve()
    bundle = args.bundle.resolve()
    if not root.is_dir():
        raise InstallError(f"project root missing: {root}")
    if not bundle.is_file():
        raise InstallError(f"bundle missing: {bundle}")

    expected_by_path = {rel: (logical, sha) for logical, rel, sha in EXPECTED}
    rows = []

    with tarfile.open(bundle, "r:gz") as tf:
        members = [m for m in tf.getmembers() if m.isfile()]
        names = {m.name for m in members}
        if names != set(expected_by_path):
            raise InstallError(
                "bundle member set mismatch: "
                f"extra={sorted(names-set(expected_by_path))} "
                f"missing={sorted(set(expected_by_path)-names)}"
            )

        for member in members:
            rel = Path(member.name)
            if rel.is_absolute() or ".." in rel.parts or not rel.parts or rel.parts[0] != "catalogs":
                raise InstallError(f"unsafe member: {member.name}")

            logical, expected_sha = expected_by_path[member.name]
            target = (root / rel).resolve()
            try:
                target.relative_to(root)
            except ValueError as exc:
                raise InstallError(f"target escapes project root: {target}") from exc

            target.parent.mkdir(parents=True, exist_ok=True)

            if target.exists():
                if target.is_symlink() or not target.is_file():
                    raise InstallError(f"invalid existing target: {target}")
                actual = sha256_file(target)
                if actual != expected_sha:
                    raise InstallError(
                        f"existing target SHA mismatch: {target}: "
                        f"{actual} != {expected_sha}"
                    )
                rows.append(
                    (logical, member.name, target.stat().st_size, actual, "PASS_ALREADY_PRESENT")
                )
                continue

            extracted = tf.extractfile(member)
            if extracted is None:
                raise InstallError(f"cannot read member: {member.name}")

            fd, tmpname = tempfile.mkstemp(
                prefix="." + target.name + ".", suffix=".part", dir=str(target.parent)
            )
            try:
                with os.fdopen(fd, "wb") as out:
                    for block in iter(lambda: extracted.read(8 * 1024 * 1024), b""):
                        out.write(block)
                    out.flush()
                    os.fsync(out.fileno())
                tmp = Path(tmpname)
                actual = sha256_file(tmp)
                if actual != expected_sha:
                    raise InstallError(
                        f"extracted SHA mismatch: {member.name}: "
                        f"{actual} != {expected_sha}"
                    )
                os.replace(tmp, target)
            finally:
                if os.path.exists(tmpname):
                    os.unlink(tmpname)

            rows.append(
                (logical, member.name, target.stat().st_size, expected_sha, "PASS_INSTALLED")
            )

    manifest = root / "catalogs/.rnatr_core_resource_installation_v0.1.0.tsv"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    with manifest.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow(["logical_name", "relative_path", "bytes", "sha256", "status"])
        w.writerows(rows)

    print("RESOURCE_INSTALL\tPASS")
    print(f"version\t{VERSION}")
    print(f"installed_manifest\t{manifest}")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=__import__("sys").stderr)
        raise
