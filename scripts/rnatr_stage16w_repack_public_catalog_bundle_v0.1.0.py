#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import tarfile
import tempfile

VERSION = "rnatr_stage16w_repack_public_catalog_bundle_v0.1.0"
PROFILE_REL = Path("config/resources/standard_v0.1.1/validated_profile.json")
TREX_NOTICE_REL = Path("docs/catalog_resources/third_party/TRExplorer_LICENSE_MIT.txt")
STRCHIVE_NOTICE_REL = Path("docs/catalog_resources/third_party/STRchive_ATTRIBUTION_CC_BY_4.0.txt")


class RepackError(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_profile(repo_root: Path) -> dict:
    path = repo_root / PROFILE_REL
    if not path.is_file():
        raise RepackError(f"profile missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def safe_member_name(name: str) -> bool:
    if not name:
        return False
    p = PurePosixPath(name)
    return not p.is_absolute() and ".." not in p.parts


def expected_runtime_members(profile: dict) -> dict[str, str]:
    root = profile["catalog_bundle"]["bundle_root"]
    subdir = profile["catalog_bundle"]["runtime_subdir"].strip("/")
    out: dict[str, str] = {}
    for entry in profile["catalog_outputs"].values():
        basename = Path(entry["relative_path"]).name
        out[f"{root}/{subdir}/{basename}"] = entry["sha256"]
    return out


def read_existing_bundle(bundle: Path, profile: dict) -> tuple[dict[str, bytes], dict]:
    expected_bundle_sha = profile["catalog_bundle"]["sha256"]
    observed_bundle_sha = sha256_file(bundle)
    if observed_bundle_sha != expected_bundle_sha:
        raise RepackError(
            f"input bundle SHA mismatch: {observed_bundle_sha} != {expected_bundle_sha}"
        )

    expected_root = profile["catalog_bundle"]["bundle_root"]
    expected_runtime = expected_runtime_members(profile)
    payloads: dict[str, bytes] = {}
    roots: set[str] = set()

    with tarfile.open(bundle, "r:gz") as tf:
        seen: set[str] = set()
        for member in tf.getmembers():
            if not safe_member_name(member.name):
                raise RepackError(f"unsafe member: {member.name}")
            if member.name in seen:
                raise RepackError(f"duplicate member: {member.name}")
            seen.add(member.name)
            roots.add(PurePosixPath(member.name).parts[0])
            if member.issym() or member.islnk():
                raise RepackError(f"links are not allowed: {member.name}")
            if member.isdir():
                continue
            if not member.isfile():
                raise RepackError(f"unsupported member type: {member.name}")
            fh = tf.extractfile(member)
            if fh is None:
                raise RepackError(f"cannot extract member: {member.name}")
            payloads[member.name] = fh.read()

    if roots != {expected_root}:
        raise RepackError(f"bundle root mismatch: {sorted(roots)} != {[expected_root]}")

    missing = sorted(set(expected_runtime) - set(payloads))
    if missing:
        raise RepackError(f"missing runtime members: {missing}")

    runtime_sha: dict[str, str] = {}
    for name, expected_sha in expected_runtime.items():
        observed = sha256_bytes(payloads[name])
        runtime_sha[name] = observed
        if observed != expected_sha:
            raise RepackError(
                f"runtime member SHA mismatch: {name}: {observed} != {expected_sha}"
            )

    return payloads, {
        "input_bundle_sha256": observed_bundle_sha,
        "input_file_members": len(payloads),
        "runtime_members": len(expected_runtime),
        "input_metadata_members": len(payloads) - len(expected_runtime),
        "runtime_sha256": runtime_sha,
    }


def deterministic_tar_gz(output: Path, payloads: dict[str, bytes]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, tmpname = tempfile.mkstemp(
        prefix="." + output.name + ".", suffix=".part", dir=str(output.parent)
    )
    os.close(fd)
    tmp = Path(tmpname)
    try:
        with tmp.open("wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0) as gz:
                with tarfile.open(fileobj=gz, mode="w", format=tarfile.PAX_FORMAT) as tf:
                    dirs: set[str] = set()
                    for name in payloads:
                        parts = PurePosixPath(name).parts[:-1]
                        for i in range(1, len(parts) + 1):
                            dirs.add("/".join(parts[:i]))
                    for d in sorted(dirs):
                        info = tarfile.TarInfo(d + "/")
                        info.type = tarfile.DIRTYPE
                        info.mode = 0o755
                        info.uid = info.gid = 0
                        info.uname = info.gname = ""
                        info.mtime = 0
                        tf.addfile(info)
                    for name in sorted(payloads):
                        data = payloads[name]
                        info = tarfile.TarInfo(name)
                        info.size = len(data)
                        info.mode = 0o644
                        info.uid = info.gid = 0
                        info.uname = info.gname = ""
                        info.mtime = 0
                        tf.addfile(info, io.BytesIO(data))
            raw.flush()
            os.fsync(raw.fileno())
        os.replace(tmp, output)
    finally:
        if tmp.exists():
            tmp.unlink()


def verify_output(output: Path, profile: dict) -> dict:
    expected_root = profile["catalog_bundle"]["bundle_root"]
    expected_runtime = expected_runtime_members(profile)
    files: dict[str, bytes] = {}
    with tarfile.open(output, "r:gz") as tf:
        roots: set[str] = set()
        seen: set[str] = set()
        for member in tf.getmembers():
            if not safe_member_name(member.name):
                raise RepackError(f"unsafe output member: {member.name}")
            if member.name in seen:
                raise RepackError(f"duplicate output member: {member.name}")
            seen.add(member.name)
            roots.add(PurePosixPath(member.name).parts[0])
            if member.issym() or member.islnk():
                raise RepackError(f"output links are not allowed: {member.name}")
            if member.isfile():
                fh = tf.extractfile(member)
                if fh is None:
                    raise RepackError(f"cannot extract output member: {member.name}")
                files[member.name] = fh.read()
    if roots != {expected_root}:
        raise RepackError("output root mismatch")

    for name, expected_sha in expected_runtime.items():
        if name not in files:
            raise RepackError(f"output runtime member missing: {name}")
        observed = sha256_bytes(files[name])
        if observed != expected_sha:
            raise RepackError(
                f"output runtime member changed: {name}: {observed} != {expected_sha}"
            )

    notice_prefix = f"{expected_root}/THIRD_PARTY_NOTICES/"
    required_notices = {
        notice_prefix + "TRExplorer_LICENSE_MIT.txt",
        notice_prefix + "STRchive_ATTRIBUTION_CC_BY_4.0.txt",
        f"{expected_root}/RNA_TR_SCOUT_CATALOG_PROVENANCE.json",
    }
    missing_notices = sorted(required_notices - set(files))
    if missing_notices:
        raise RepackError(f"output notice/provenance members missing: {missing_notices}")

    return {
        "output_bundle_sha256": sha256_file(output),
        "output_file_members": len(files),
        "runtime_members_exact": len(expected_runtime),
        "metadata_members": len(files) - len(expected_runtime),
        "required_notice_members_present": True,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Repack the exact validated RNA-TR-Scout catalog bundle with public redistribution notices without changing runtime member bytes."
    )
    ap.add_argument("--repo-root", type=Path, required=True)
    ap.add_argument("--input-bundle", type=Path, required=True)
    ap.add_argument("--output-bundle", type=Path, required=True)
    ap.add_argument("--report-json", type=Path)
    args = ap.parse_args()

    repo_root = args.repo_root.resolve()
    input_bundle = args.input_bundle.resolve()
    output_bundle = args.output_bundle.resolve()
    if not input_bundle.is_file() or input_bundle.is_symlink():
        raise RepackError(f"input bundle missing/invalid: {input_bundle}")
    if output_bundle == input_bundle:
        raise RepackError("output bundle must not overwrite input bundle")

    profile = load_profile(repo_root)
    payloads, input_report = read_existing_bundle(input_bundle, profile)
    root = profile["catalog_bundle"]["bundle_root"]

    trex_notice = repo_root / TREX_NOTICE_REL
    strchive_notice = repo_root / STRCHIVE_NOTICE_REL
    if not trex_notice.is_file() or not strchive_notice.is_file():
        raise RepackError("third-party notice source files are missing")

    payloads[f"{root}/THIRD_PARTY_NOTICES/TRExplorer_LICENSE_MIT.txt"] = trex_notice.read_bytes()
    payloads[f"{root}/THIRD_PARTY_NOTICES/STRchive_ATTRIBUTION_CC_BY_4.0.txt"] = strchive_notice.read_bytes()

    provenance = {
        "schema": "rnatr_public_catalog_provenance_v0.1.0",
        "scientific_profile": profile["profile_version"],
        "bundle_root": root,
        "runtime_member_sha256": input_report["runtime_sha256"],
        "TRExplorer": {
            "upstream_repository": "https://github.com/broadinstitute/trexplorer-catalog",
            "release_basis": "v2.0",
            "license": "MIT",
        },
        "STRchive": {
            "upstream_repository": "https://github.com/dashnowlab/STRchive",
            "source_commit": "88502a64bd47ae464b908757122cc7e4bbeed8c8",
            "version_metadata": "2.24.2",
            "license": "CC BY 4.0",
        },
        "distribution_change": "metadata-only repack for public redistribution notices; five runtime scientific artifacts remain byte-identical",
    }
    payloads[f"{root}/RNA_TR_SCOUT_CATALOG_PROVENANCE.json"] = (
        json.dumps(provenance, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")

    deterministic_tar_gz(output_bundle, payloads)
    output_report = verify_output(output_bundle, profile)

    report = {
        "version": VERSION,
        "status": "PASS_RUNTIME_5_OF_5_EXACT_PUBLIC_METADATA_REPACK",
        "input_bundle": str(input_bundle),
        "output_bundle": str(output_bundle),
        **input_report,
        **output_report,
    }

    report_path = args.report_json.resolve() if args.report_json else output_bundle.with_suffix(output_bundle.suffix + ".stage16w.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = report_path.with_name("." + report_path.name + ".part")
    tmp.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, report_path)

    print("===== RNA-TR-SCOUT STAGE16W PUBLIC CATALOG REPACK =====")
    for key in [
        "status", "input_bundle_sha256", "output_bundle_sha256",
        "runtime_members_exact", "input_metadata_members", "metadata_members",
        "required_notice_members_present",
    ]:
        print(f"{key}\t{report[key]}")
    print(f"output_bundle\t{output_bundle}")
    print(f"report_json\t{report_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
