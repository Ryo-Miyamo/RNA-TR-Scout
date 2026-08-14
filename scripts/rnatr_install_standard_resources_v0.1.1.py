#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

VERSION = "rnatr_install_standard_resources_v0.1.1"
PROFILE_VERSION = "rnatr_standard_resources_validated_profile_v0.1.1"
PROFILE_REL = Path("config/resources/standard_v0.1.1/validated_profile.json")

class ResourceError(RuntimeError):
    pass

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def ensure_file(path: Path) -> None:
    if not path.is_file() or path.is_symlink():
        raise ResourceError(f"required regular file missing/invalid: {path}")

def run(cmd: list[str], check: bool = True):
    p = subprocess.run(
        cmd, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, check=False
    )
    if check and p.returncode != 0:
        raise ResourceError(
            f"command failed rc={p.returncode}: {' '.join(cmd)}\n{p.stdout}"
        )
    return p

def tool_version(exe: str) -> str:
    resolved = shutil.which(exe)
    if not resolved:
        raise ResourceError(f"required executable missing: {exe}")
    p = run([resolved, "--version"])
    return p.stdout.strip().splitlines()[0] if p.stdout.strip() else ""

def load_profile(path: Path) -> dict:
    ensure_file(path)
    obj = json.loads(path.read_text(encoding="utf-8"))
    if obj.get("profile_version") != PROFILE_VERSION:
        raise ResourceError("unsupported standard-resource profile")
    return obj

def atomic_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmpname = tempfile.mkstemp(
        prefix="." + path.name + ".", suffix=".part", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=2, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmpname, path)
    finally:
        if os.path.exists(tmpname):
            os.unlink(tmpname)

def download(url: str, target: Path, expected_sha: str) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file() and not target.is_symlink():
        if sha256_file(target) == expected_sha:
            return "PASS_CACHE_EXACT"

    aria2 = shutil.which("aria2c")
    curl = shutil.which("curl")
    if aria2:
        cmd = [
            aria2, "-x", "8", "-s", "8", "--continue=true",
            "--max-tries=10", "--retry-wait=5",
            "-d", str(target.parent), "-o", target.name, url,
        ]
    elif curl:
        cmd = [
            curl, "-fL", "--retry", "5", "--retry-delay", "3",
            "--continue-at", "-", "-o", str(target), url,
        ]
    else:
        raise ResourceError("automatic download requires aria2c or curl")

    run(cmd)
    ensure_file(target)
    actual = sha256_file(target)
    if actual != expected_sha:
        raise ResourceError(
            f"downloaded file SHA mismatch: {target.name}: "
            f"{actual} != {expected_sha}"
        )
    return "PASS_DOWNLOADED_EXACT"

def resolve_reference_source(entry: dict, source_dir: Path | None, cache: Path):
    if source_dir is not None:
        path = (source_dir / entry["filename"]).resolve()
        ensure_file(path)
        actual = sha256_file(path)
        if actual != entry["sha256"]:
            raise ResourceError(
                f"local source SHA mismatch: {path.name}: "
                f"{actual} != {entry['sha256']}"
            )
        return path, "PASS_LOCAL_SOURCE_EXACT"
    target = cache / entry["filename"]
    return target, download(entry["url"], target, entry["sha256"])

def resolve_catalog_bundle(
    explicit: Path | None,
    profile: dict,
    cache_dir: Path,
) -> tuple[Path, str]:
    entry = profile["catalog_bundle"]
    expected = entry["sha256"]

    if explicit is not None:
        path = explicit.resolve()
        ensure_file(path)
        actual = sha256_file(path)
        if actual != expected:
            raise ResourceError(
                f"catalog bundle SHA mismatch: {actual} != {expected}"
            )
        return path, "PASS_LOCAL_BUNDLE_EXACT"

    url = str(entry.get("public_url", "")).strip()
    if not url:
        raise ResourceError(
            "validated catalog public URL is not finalized yet; "
            "supply --catalog-bundle for this release-engineering candidate"
        )
    target = cache_dir / entry["filename"]
    return target, download(url, target, expected)

def decompress_exact(src: Path, dst: Path, expected_sha: str) -> None:
    fd, tmpname = tempfile.mkstemp(
        prefix="." + dst.name + ".", suffix=".part", dir=str(dst.parent)
    )
    try:
        with gzip.open(src, "rb") as inp, os.fdopen(fd, "wb") as out:
            for block in iter(lambda: inp.read(8 * 1024 * 1024), b""):
                out.write(block)
            out.flush()
            os.fsync(out.fileno())
        tmp = Path(tmpname)
        actual = sha256_file(tmp)
        if actual != expected_sha:
            raise ResourceError(
                f"decompressed SHA mismatch: {dst.name}: "
                f"{actual} != {expected_sha}"
            )
        os.replace(tmp, dst)
    finally:
        if os.path.exists(tmpname):
            os.unlink(tmpname)

def build_junction(gtf: Path, fai: Path, output: Path) -> None:
    rank = {}
    with fai.open("r", encoding="utf-8") as fh:
        for i, raw in enumerate(fh):
            rank[raw.split("\t", 1)[0]] = i

    attr_re = re.compile(r'(\S+) "([^"]*)";')
    tx = {}
    with gtf.open("r", encoding="utf-8") as fh:
        for raw in fh:
            if not raw or raw.startswith("#"):
                continue
            f = raw.rstrip("\n").split("\t")
            if len(f) != 9 or f[2] != "exon":
                continue
            attrs = dict(attr_re.findall(f[8]))
            tid = attrs.get("transcript_id", "")
            if not tid:
                continue
            chrom, strand = f[0], f[6]
            exon = (int(f[3]) - 1, int(f[4]))
            rec = tx.get(tid)
            if rec is None:
                tx[tid] = {"chrom": chrom, "strand": strand, "exons": [exon]}
            elif rec["chrom"] == chrom and rec["strand"] == strand:
                rec["exons"].append(exon)

    rows = []
    for tid, rec in tx.items():
        exons = sorted(set(rec["exons"]))
        if len(exons) < 2:
            continue
        start, end = exons[0][0], exons[-1][1]
        sizes = [b - a for a, b in exons]
        starts = [a - start for a, _ in exons]
        rows.append((
            rank.get(rec["chrom"], 10**9), rec["chrom"], start, end,
            tid, rec["strand"], sizes, starts
        ))
    rows.sort(key=lambda r: (r[0], r[2], r[3], r[4]))

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as out:
        for _, chrom, start, end, tid, strand, sizes, starts in rows:
            out.write("\t".join([
                chrom, str(start), str(end), tid, "0", strand,
                str(start), str(start), "0", str(len(sizes)),
                ",".join(map(str, sizes)) + ",",
                ",".join(map(str, starts)) + ",",
            ]) + "\n")

def inspect_group(root: Path, entries: dict, ready_name: str) -> dict:
    states, exact = {}, True
    for logical, entry in entries.items():
        path = root / entry["relative_path"]
        expected = entry["sha256"]
        if not path.is_file() or path.is_symlink():
            states[logical] = {"status": "MISSING", "sha256": ""}
            exact = False
            continue
        actual = sha256_file(path)
        ok = actual == expected
        states[logical] = {
            "status": "VALIDATED_EXACT" if ok else "MISMATCH",
            "sha256": actual,
        }
        exact = exact and ok
    return {
        "status": ready_name if exact else "INCOMPLETE_OR_MISMATCH",
        "states": states,
    }

def install_reference(
    root: Path,
    profile: dict,
    fasta_gz: Path,
    gtf_gz: Path,
) -> str:
    final_dir = root / profile["reference_directory"]
    pre = inspect_group(
        root, profile["reference_outputs"], "VALIDATED_REFERENCE_PROFILE"
    )
    if final_dir.exists():
        if pre["status"] == "VALIDATED_REFERENCE_PROFILE":
            return "PASS_ALREADY_PRESENT"
        raise ResourceError(
            f"reference directory exists but is not exact validated profile: "
            f"{final_dir}. Refusing automatic replacement."
        )

    mm2 = tool_version("minimap2")
    sam = tool_version("samtools")
    if mm2 != profile["tools"]["minimap2"]["validated_version"]:
        raise ResourceError(
            f"validated setup requires minimap2 "
            f"{profile['tools']['minimap2']['validated_version']}; observed {mm2}"
        )
    if not sam.startswith(profile["tools"]["samtools"]["validated_version_prefix"]):
        raise ResourceError(
            f"validated setup requires "
            f"{profile['tools']['samtools']['validated_version_prefix']}; observed {sam}"
        )

    final_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(
        prefix=f".{final_dir.name}.", suffix=".staging",
        dir=str(final_dir.parent)
    ))
    try:
        fasta = staging / "GRCh38.primary_assembly.genome.fa"
        gtf = staging / "gencode.v50.primary_assembly.annotation.gtf"
        fai = staging / "GRCh38.primary_assembly.genome.fa.fai"
        mmi = staging / "GRCh38.primary_assembly.genome.mmi"
        junction = staging / "junctions/gencode.v50.multi_exon_transcripts.bed12"

        decompress_exact(
            fasta_gz, fasta,
            profile["reference_outputs"]["reference_fasta"]["sha256"]
        )
        decompress_exact(
            gtf_gz, gtf,
            profile["build_inputs"]["primary_annotation_gtf_gz"]["decompressed_sha256"]
        )

        run(["samtools", "faidx", str(fasta)])
        if sha256_file(fai) != profile["reference_outputs"]["reference_fai"]["sha256"]:
            raise ResourceError("FAI exact reconstruction failed")

        run(["minimap2", "-d", str(mmi), str(fasta)])
        if sha256_file(mmi) != profile["reference_outputs"]["reference_mmi"]["sha256"]:
            raise ResourceError("MMI exact reconstruction failed")

        build_junction(gtf, fai, junction)
        if sha256_file(junction) != profile["reference_outputs"]["junction_bed12"]["sha256"]:
            raise ResourceError("junction BED12 exact reconstruction failed")

        # GTF is build-time input for the current mapping runtime.
        gtf.unlink()

        if final_dir.exists():
            raise ResourceError("reference directory appeared during build")
        os.replace(staging, final_dir)
        staging = None
    finally:
        if staging is not None and staging.exists():
            shutil.rmtree(staging, ignore_errors=True)

    post = inspect_group(
        root, profile["reference_outputs"], "VALIDATED_REFERENCE_PROFILE"
    )
    if post["status"] != "VALIDATED_REFERENCE_PROFILE":
        raise ResourceError("published reference profile inspection failed")
    return "PASS_INSTALLED"

def safe_tar_name(name: str) -> bool:
    p = Path(name)
    return bool(name) and not p.is_absolute() and ".." not in p.parts

def install_release_catalog_bundle(
    root: Path,
    profile: dict,
    bundle: Path,
) -> tuple[str, dict]:
    ensure_file(bundle)
    bundle_entry = profile["catalog_bundle"]
    actual_bundle = sha256_file(bundle)
    if actual_bundle != bundle_entry["sha256"]:
        raise ResourceError(
            f"catalog bundle SHA mismatch: {actual_bundle} != "
            f"{bundle_entry['sha256']}"
        )

    pre = inspect_group(
        root, profile["catalog_outputs"], "VALIDATED_CATALOG_PROFILE"
    )
    final_dirs = {
        (root / entry["relative_path"]).parent
        for entry in profile["catalog_outputs"].values()
    }
    if len(final_dirs) != 1:
        raise ResourceError("catalog outputs do not share one runtime directory")
    final_dir = next(iter(final_dirs))

    if final_dir.exists():
        if pre["status"] == "VALIDATED_CATALOG_PROFILE":
            return "PASS_ALREADY_PRESENT", {
                "bundle_layout": "STAGE16L_RELEASE_BUNDLE",
                "runtime_members": 5,
                "metadata_files_seen": 0,
            }
        raise ResourceError(
            f"catalog runtime directory exists but is not exact validated profile: "
            f"{final_dir}. Refusing automatic replacement."
        )

    expected_root = bundle_entry["bundle_root"]
    runtime_subdir = bundle_entry["runtime_subdir"].strip("/")
    expected_by_member = {}
    for logical, entry in profile["catalog_outputs"].items():
        basename = Path(entry["relative_path"]).name
        member = f"{expected_root}/{runtime_subdir}/{basename}"
        expected_by_member[member] = (logical, entry)

    payloads: dict[str, bytes] = {}
    metadata_files_seen = 0

    with tarfile.open(bundle, "r:gz") as tf:
        members = tf.getmembers()
        seen = set()
        roots = set()

        for member in members:
            if not safe_tar_name(member.name):
                raise ResourceError(f"unsafe catalog bundle member: {member.name}")
            if member.name in seen:
                raise ResourceError(f"duplicate catalog bundle member: {member.name}")
            seen.add(member.name)
            if member.name:
                roots.add(Path(member.name).parts[0])

            if member.issym() or member.islnk():
                raise ResourceError(
                    f"catalog bundle links are not allowed: {member.name}"
                )
            if not member.isfile() and not member.isdir():
                raise ResourceError(
                    f"unsupported catalog bundle member type: {member.name}"
                )

        if roots != {expected_root}:
            raise ResourceError(
                f"catalog bundle root mismatch: {sorted(roots)} != "
                f"{[expected_root]}"
            )

        files = {m.name: m for m in members if m.isfile()}
        missing = sorted(set(expected_by_member) - set(files))
        if missing:
            raise ResourceError(
                f"catalog bundle missing runtime members: {missing}"
            )

        for member_name, (logical, entry) in expected_by_member.items():
            member = files[member_name]
            handle = tf.extractfile(member)
            if handle is None:
                raise ResourceError(
                    f"cannot read catalog runtime member: {member_name}"
                )
            data = handle.read()
            actual = sha256_bytes(data)
            if actual != entry["sha256"]:
                raise ResourceError(
                    f"catalog runtime member SHA mismatch: {member_name}: "
                    f"{actual} != {entry['sha256']}"
                )
            payloads[logical] = data

        metadata_files_seen = len(files) - len(expected_by_member)

    final_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(
        prefix=f".{final_dir.name}.",
        suffix=".staging",
        dir=str(final_dir.parent),
    ))
    try:
        for logical, entry in profile["catalog_outputs"].items():
            target = staging / Path(entry["relative_path"]).name
            data = payloads[logical]
            with target.open("wb") as out:
                out.write(data)
                out.flush()
                os.fsync(out.fileno())
            if sha256_file(target) != entry["sha256"]:
                raise ResourceError(
                    f"staged catalog runtime SHA mismatch: {logical}"
                )

        if final_dir.exists():
            raise ResourceError(
                f"catalog runtime directory appeared during install: {final_dir}"
            )
        os.replace(staging, final_dir)
        staging = None
    finally:
        if staging is not None and staging.exists():
            shutil.rmtree(staging, ignore_errors=True)

    post = inspect_group(
        root, profile["catalog_outputs"], "VALIDATED_CATALOG_PROFILE"
    )
    if post["status"] != "VALIDATED_CATALOG_PROFILE":
        raise ResourceError("published catalog profile inspection failed")

    return "PASS_INSTALLED", {
        "bundle_layout": "STAGE16L_RELEASE_BUNDLE",
        "runtime_members": len(expected_by_member),
        "metadata_files_seen": metadata_files_seen,
    }

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Install the standard validated RNA-TR-Scout resources."
    )
    ap.add_argument("--project-root", type=Path, required=True)
    ap.add_argument("--catalog-bundle", type=Path)
    ap.add_argument("--reference-source-dir", type=Path)
    ap.add_argument(
        "--cache-dir",
        type=Path,
        default=Path.home() / ".cache/rnatr-scout/gencode_v50",
    )
    ap.add_argument(
        "--catalog-cache-dir",
        type=Path,
        default=Path.home() / ".cache/rnatr-scout/catalogs",
    )
    ap.add_argument("--validated-profile", type=Path)
    ap.add_argument("--inspect-only", action="store_true")
    args = ap.parse_args()

    root = args.project_root.resolve()
    if not root.is_dir():
        raise ResourceError(f"project root missing: {root}")

    repo_root = Path(__file__).resolve().parent.parent
    profile_path = (
        args.validated_profile.resolve()
        if args.validated_profile
        else repo_root / PROFILE_REL
    )
    profile = load_profile(profile_path)

    ref = inspect_group(
        root, profile["reference_outputs"], "VALIDATED_REFERENCE_PROFILE"
    )
    cat = inspect_group(
        root, profile["catalog_outputs"], "VALIDATED_CATALOG_PROFILE"
    )
    if args.inspect_only:
        ready = (
            ref["status"] == "VALIDATED_REFERENCE_PROFILE"
            and cat["status"] == "VALIDATED_CATALOG_PROFILE"
        )
        print(json.dumps({
            "status": "PASS_STANDARD_RESOURCES_READY" if ready else "NOT_READY",
            "reference": ref,
            "catalog": cat,
        }, indent=2, sort_keys=True))
        return 0 if ready else 2

    source_dir = (
        args.reference_source_dir.resolve()
        if args.reference_source_dir
        else None
    )
    if source_dir is not None and not source_dir.is_dir():
        raise ResourceError(f"reference source directory missing: {source_dir}")

    ref_cache = args.cache_dir.expanduser().resolve()
    catalog_cache = args.catalog_cache_dir.expanduser().resolve()

    fasta_gz, fasta_source = resolve_reference_source(
        profile["build_inputs"]["reference_fasta_gz"],
        source_dir,
        ref_cache,
    )
    gtf_gz, gtf_source = resolve_reference_source(
        profile["build_inputs"]["primary_annotation_gtf_gz"],
        source_dir,
        ref_cache,
    )
    catalog_bundle, catalog_source = resolve_catalog_bundle(
        args.catalog_bundle,
        profile,
        catalog_cache,
    )

    ref_status = install_reference(
        root, profile, fasta_gz, gtf_gz
    )
    cat_status, bundle_info = install_release_catalog_bundle(
        root, profile, catalog_bundle
    )

    ref = inspect_group(
        root, profile["reference_outputs"], "VALIDATED_REFERENCE_PROFILE"
    )
    cat = inspect_group(
        root, profile["catalog_outputs"], "VALIDATED_CATALOG_PROFILE"
    )
    if (
        ref["status"] != "VALIDATED_REFERENCE_PROFILE"
        or cat["status"] != "VALIDATED_CATALOG_PROFILE"
    ):
        raise ResourceError("final standard-resource inspection failed")

    manifest = root / "refs/.rnatr_standard_resource_installation_v0.1.1.json"
    atomic_json(manifest, {
        "status": "PASS_STANDARD_RESOURCES_READY",
        "installer_version": VERSION,
        "profile_version": PROFILE_VERSION,
        "reference_install": ref_status,
        "catalog_install": cat_status,
        "reference_source_fasta": fasta_source,
        "reference_source_gtf": gtf_source,
        "catalog_source": catalog_source,
        "catalog_bundle_sha256": sha256_file(catalog_bundle),
        "catalog_bundle_info": bundle_info,
        "reference": ref,
        "catalog": cat,
        "user_manages_checksums": False,
        "user_builds_fai_mmi_junction_manually": False,
        "legacy_bare_catalog_installer_required": False,
        "catalog_public_url_finalized": bool(
            profile["catalog_bundle"].get("public_url", "")
        ),
    })

    print("STANDARD_RESOURCE_INSTALL\tPASS")
    print(f"version\t{VERSION}")
    print("profile_status\tPASS_STANDARD_RESOURCES_READY")
    print(f"reference_install\t{ref_status}")
    print(f"catalog_install\t{cat_status}")
    print(f"reference_source_fasta\t{fasta_source}")
    print(f"reference_source_gtf\t{gtf_source}")
    print(f"catalog_source\t{catalog_source}")
    print("catalog_bundle_layout\tSTAGE16L_RELEASE_BUNDLE")
    print(f"catalog_runtime_members\t{bundle_info['runtime_members']}")
    print(f"catalog_metadata_files_seen\t{bundle_info['metadata_files_seen']}")
    print("reference_profile\tVALIDATED_REFERENCE_PROFILE")
    print("catalog_profile\tVALIDATED_CATALOG_PROFILE")
    print("legacy_bare_catalog_installer_required\tfalse")
    print("user_manages_checksums\tfalse")
    print("user_builds_fai_mmi_junction_manually\tfalse")
    print(f"manifest\t{manifest}")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
