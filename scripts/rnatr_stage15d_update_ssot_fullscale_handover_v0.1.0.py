#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import textwrap
import traceback
from pathlib import Path
from typing import Any, Iterable

VERSION = "rnatr_stage15d_ssot_fullscale_handover_registration_v0.1.0"
CONFIRM_TOKEN = "REGISTER_STAGE15D_FULLSCALE_V010"
PROJECT_ROOT = Path("/mnt/intelssd/rnatr_project")
DOWNLOADS = Path.home() / "Downloads"

SSOT_ROOT = PROJECT_ROOT / "metadata/ssot"
SSOT_CLI = SSOT_ROOT / "rnatr_ssot.py"
SSOT_DB = SSOT_ROOT / "rnatr_ssot.sqlite"
SSOT_SUMMARY = SSOT_ROOT / "CURRENT_STATE.md"
SSOT_EXPORTS = SSOT_ROOT / "exports"
SSOT_BACKUPS = SSOT_ROOT / "backups"
LOCK_PATH = SSOT_ROOT / ".stage15d_fullscale_handover_ssot_update.lock"

CORE_SCHEMA = PROJECT_ROOT / "config/evidence_schema/v0.4.2/schema/rnatr_v04_table_schema.json"
GATES_V024 = PROJECT_ROOT / "validation/release_gates_v0.2.4.tsv"
GATES_V030 = PROJECT_ROOT / "validation/release_gates_v0.3.0.tsv"

HANDOVER_NAME = "RNA_TR_Scout_handover_Stage15C_full_empirical_to_determinism_restart_20260810.md"
HANDOVER_DOWNLOAD = Path(__file__).resolve().parent / HANDOVER_NAME
HANDOVER_INSTALL = PROJECT_ROOT / "docs/handover" / HANDOVER_NAME
SCRIPT_INSTALL = PROJECT_ROOT / "scripts/rnatr_stage15d_update_ssot_fullscale_handover_v0.1.0.py"
DOC_INSTALL = PROJECT_ROOT / "docs/stage15d/RNA_TR_Scout_Stage15D_fullscale_SSOT_registration_v0.1.0.md"

UPDATE_QC_ROOT = (
    PROJECT_ROOT / "qc/15_stage15d_ssot_update"
    / "ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1"
    / "fullscale_handover_v0.1.0"
)
UPDATE_META_ROOT = PROJECT_ROOT / "metadata/stage15d/ssot_updates/fullscale_handover_v0.1.0"

PREFLIGHT_QC_DOWNLOAD = DOWNLOADS / "rnatr_stage15d_ssot_update_fullscale_handover_v0.1.0.preflight.qc.tsv"
PREFLIGHT_BUNDLE = DOWNLOADS / "rnatr_stage15d_ssot_update_fullscale_handover_v0.1.0_preflight.tar.gz"
SUCCESS_BUNDLE = DOWNLOADS / "rnatr_stage15d_ssot_update_fullscale_handover_v0.1.0_output.tar.gz"
FAILURE_BUNDLE = DOWNLOADS / "rnatr_stage15d_ssot_update_fullscale_handover_v0.1.0_failure.tar.gz"

EXPECTED_BASELINE_CLI_SHA256 = "8aeff1eda5c301e74a9054e786ed19bf5b699ff6aa111221aa2e60f6d733b37b"
EXPECTED_BASELINE_DB_SHA256 = "7edb4eb63e8f04b6fe8d8e67a82a6d9d70ba55c1946c62827d7b133e0d5a4274"
EXPECTED_CORE_SCHEMA_SHA256 = "c0509a0669344dba0b07cd1bb9e71f2aeb01e0196df47ec9178f1d2464b515f1"
EXPECTED_GATES_V024_SHA256 = "90ecf0c5f9cf0ba68361a5538d98aabc63afbe063fec5ee1060a7d0e508cce87"
EXPECTED_HANDOVER_SHA256 = "d42e4c98379dd1e5b42f17771d4622cab568e6c3b028be9458816d5c8cf548ba"

PATCH_MARKER = "# Stage 15D full-scale empirical completion and G31 scope registration v0.1.0"
PATCH_ANCHOR = "\n\n    current_metrics = ["

RUN_100K = "ENCSR307SHM_pilot100k_mm2splice_v1"
RUN_500K = "ENCSR307SHM_stage15a500k_seed20260809_mm2splice_v1"
MAPPING_RUN = "ENCSR307SHM_full5312696_mm2splice_v1"
FULL_RUN = "ENCSR307SHM_stage15c_full5312696_seed20260809_mm2splice_v1"

QC_500K = (
    PROJECT_ROOT / "qc/15_stage15a_bam_to_final" / RUN_500K
    / "v0.1.1_500k_scaling/stage15a_scaling_500k.qc.tsv"
)
STAGE15B_QC = (
    PROJECT_ROOT / "qc/15_stage15b_memory_bounded_validator" / RUN_500K
    / "v0.1.0/stage15b_memory_bounded_validator.qc.tsv"
)
ARCH_QC = (
    PROJECT_ROOT / "qc/15_stage15c_execution_architecture" / RUN_500K
    / "v0.1.1_144shard_500k/stage15c_144shard_execution_architecture.qc.tsv"
)
MAPPING_QC = (
    PROJECT_ROOT / "qc/11_mapping" / MAPPING_RUN
    / f"{MAPPING_RUN}.mapping_qc.tsv"
)
MAPPING_READ_ID_QC = (
    PROJECT_ROOT / "qc/11_mapping" / MAPPING_RUN
    / f"{MAPPING_RUN}.read_id_parity.tsv"
)
FULL_QC = (
    PROJECT_ROOT / "qc/15_stage15c_fullscale_bam_to_final" / FULL_RUN
    / "v0.1.6/stage15c_full_empirical_run.qc.tsv"
)
PACKAGE_MANIFEST = (
    PROJECT_ROOT / "results/15_stage15c_fullscale_bam_to_final" / FULL_RUN
    / "v0.1.6/package_full/package_manifest.tsv"
)
CHECKPOINT_MANIFEST = (
    PROJECT_ROOT / "qc/15_stage15c_fullscale_bam_to_final" / FULL_RUN
    / "v0.1.6/stage15c_fullscale_checkpoint_manifest.tsv"
)
G31_QC = (
    PROJECT_ROOT / "qc/15_stage15d_g31_row_expansion_audit" / FULL_RUN
    / "v0.1.0/stage15d_g31_row_expansion_audit.qc.tsv"
)
G31_RATE = G31_QC.parent / "candidate_entry_rate_and_reason_audit.tsv"
G31_CROSS_SCALE = G31_QC.parent / "cross_scale_comparison.tsv"
G31_HARD = G31_QC.parent / "hard_lineage_and_duplicate_audit.tsv"
G31_CONCENTRATION = G31_QC.parent / "concentration_summary.tsv"

FULL_RUNNER = PROJECT_ROOT / "scripts/rnatr_stage15c_run_full5312696_bam_to_final_v0.1.6.py"
STAGE15B_VALIDATOR = PROJECT_ROOT / "scripts/rnatr_stage15b_validate_package_sharded_memory_bounded_v0.1.0.py"
ARCH_SCRIPT = PROJECT_ROOT / "scripts/rnatr_stage15c_validate_144shard_execution_architecture_v0.1.1.py"
G31_SCRIPT = PROJECT_ROOT / "scripts/rnatr_stage15d_g31_row_expansion_audit_v0.1.0.py"
MAPPING_SCRIPT = PROJECT_ROOT / "scripts/rnatr_stage15c_map_full_ENCSR307SHM_mm2splice_v010.sh"

EVIDENCE_GUARDS: dict[Path, str] = {
    QC_500K: "ef27be62e633e941b21978d8354a928a7ecea33600465fe6620e82640b329e82",
    MAPPING_QC: "96c723fd7248faeca0e674a5a6d59d92c0516e8ae4a63c037d8b5a1150861c3e",
    MAPPING_READ_ID_QC: "47c37eb77fa16847ba9d1b6fe4c8c40dfa9661837c3bc95efda2f330fe3ecd7c",
    STAGE15B_QC: "b5f7f26f91d0edafbdc77de3373b67b8cc9ec3e16fb2f903cec4390a9d47f142",
    ARCH_QC: "43226464ef19572de3fcccef1a6e7fd169e22e20e8fa3b724f9d2f1080ce0437",
    FULL_QC: "3b95addc1e7aa50ddf22d90dab3373025b9c7b41569fcb2aaea7d2910b35fd07",
    PACKAGE_MANIFEST: "335058228a3f3c4205161f3d24b208009175aed5e50f995a74e04100b4f3a738",
    CHECKPOINT_MANIFEST: "f00d67e28413d66730b8c2ffab0f52b9ce9e1553e5cc9a3f9d768e4a7a0083b4",
    G31_QC: "8cfb7eb4c5dc85c554b52deae630f15a3602117a689146ceb7a0c55ef008c163",
    G31_RATE: "474f6280a1a5e98fb3940dc3e941c20b93870b7791da74157678efaf83c4d4fc",
    G31_CROSS_SCALE: "0f5939b753506c44881574cd1f1a217134902ad64bacec4b7dc7dbb534edf904",
    G31_HARD: "47c8579614e2905ef6f68924a0e0b174b1b743658be747d9ebbeee7a9c5e6a5b",
    G31_CONCENTRATION: "c4f92a75afc0cc63ee27052ded3d2b6198b2b0b7071097a4aedc290ad046d836",
    FULL_RUNNER: "cca6b2d4c6e773392d3a8c24cd2fd2a1f0a41a713338b4ccdec1ba7fab5bafcc",
    STAGE15B_VALIDATOR: "1136086f0214bcd11a2a2d71f2e459f433c7fc9f51d170aa3b97826e8808ee99",
    ARCH_SCRIPT: "fe8f4bdada0336d6e8afc0008f5800d920a49a28a1541f10a89b439d88770b72",
    G31_SCRIPT: "fa9c56d6aeb8488e69ed937ac9d89b1a7c62afee9baeb6fe410b5fa2c182d608",
    MAPPING_SCRIPT: "2818b171a0e892b42746e890f98b6705820a2ed9e3a3fad196c07baa7c4c3724",
}

RELEASE_GATES_V030_TEXT = """gate_id\tgate\tlevel\tblocking_for_v1\tstatus\tevidence_or_next_action
G01\tGeneral caller deterministic across hash seeds\talgorithm\ttrue\tPASS\tStage14F2/14G and deterministic 250k/500k evidence
G02\tSynthetic truth and semantic invariants\talgorithm\ttrue\tPASS\tStage14G
G03\tPython/native 100k exact parity\timplementation\ttrue\tPASS\tStage14G all 388571 rows
G04\tNative caller-only projected 5.31M runtime <=30 min\tperformance\tfalse\tPASS\tStage14G projected 18.90 min; BAM-to-final 30-min target remains separate and open
G05\tPrepared-job/native-caller to validated final-evidence package\tproduction\ttrue\tPASS\tStage14K2/14L2
G06\t5M-read BAM-input runtime <=60 min with first-freeze documented tolerance <=62 min\tperformance\ttrue\tPASS_WITH_DOCUMENTED_TOLERANCE\tEmpirical 5,312,696-read BAM-to-final v0.1.6 = 60.041256352 min; strict <=60 was exceeded by 2.475 s; mapping excluded, partition/validators/publication included
G07\t5M-read restartability/memory/artifact audit\tproduction\ttrue\tOPEN\tMemory/storage/checkpoint inventory PASS; release-scale determinism and full-scale selective restart/resume remain required
G08\tReal truth-bearing biological validation\tbiology\ttrue\tOPEN\tDisease/synthetic-RNA/orthogonal truth data
G09\tLarge-cohort RNA technical/background distribution\tpopulation\tfalse\tOPEN\tDefer until production core is frozen
G10\tFASTQ-to-final mapping-inclusive performance\tconvenience\tfalse\tOPEN\tReport minimap2 separately; current full mapping = 75.433333 min
G11\tMismatch/indel/interruption/purity/LPS preserved separately\tschema_contract\ttrue\tPASS\tSchema v0.4.2 retains separate fields and explicit missingness
G12\tBiological-vs-technical origin classifier truth validation\tschema_contract\tfalse\tOPEN\tCurrent package uses NOT_ASSESSED
G13\tRead-level RNA repeat-length distribution retained\tschema_contract\ttrue\tPASS\trepeat_events remains source of truth
G14\tRNA repeat-length clustering algorithm validated\tschema_contract\tfalse\tOPEN\tImplement after core freeze and sufficient same-locus support
G15\tAllele/haplotype labels prohibited without phase evidence\tschema_contract\ttrue\tPASS\tValidator/contract rejects unsupported labels
G16\tCensored/context-limited reads not naively mixed as exact observations\tschema_contract\ttrue\tPASS\tExact-only or explicit censor-aware handling required
G17\tMapping-complete BAM to validated schema v0.4.2 package\tproduction\ttrue\tPASS\t100k/250k/500k and full 5.31M empirical package PASS
G18\tCalled non-locus-anchored attempts retained but not eventized\tmaterialization\ttrue\tPASS\tLossless materialization contract
G19\tfailure_code/qc_flags/materialization_status semantics are distinct\tschema_contract\ttrue\tPASS\tStage14L2 contract
G20\tRead-keyed biology joinability for transcript, haplotype, observability, and molecule independence\tbiology_output\ttrue\tOPEN\tFreeze and validate sidecar schemas after core technical completion
G21\tMolecule-level distribution retained through sample-by-locus summarization\tinterpretation_output\ttrue\tOPEN\tImplement molecule_repeat_state and censor-aware sample_locus_summary
G22\tPurpose-specific ranking lanes with unconditional known-disease retention\tinterpretation_output\ttrue\tOPEN\tImplement biology/triage lanes after core freeze
G23\tResearcher-facing candidate dossier fully traceable to core and sidecars\tinterpretation_output\ttrue\tOPEN\tImplement dossier and reverse-traceability validator
G24\tMajor-checkpoint Architecture consistency audit and closure\tarchitecture_contract\ttrue\tOPEN\tPost-250k completed; PRE_RELEASE_CANDIDATE and PRE_BIOLOGY audits remain mandatory
G25\tAutomatic version-pinned reference bootstrap with resumable download and checksum verification\trelease_readiness\ttrue\tOPEN_PLANNED\tImplement reference manifest/downloader/cache; large references excluded from GitHub
G26\tCPU/RAM/output/tmp resource detection before execution\trelease_readiness\ttrue\tOPEN_PLANNED\tExpose resource report and override provenance
G27\tMemory-aware automatic shard/concurrency selection with manual overrides\trelease_readiness\ttrue\tOPEN_PLANNED\tUse empirical resource model; support --threads --memory-gb --tmp-dir
G28\tScientific logical output reproducibility across supported hardware/concurrency profiles\trelease_readiness\ttrue\tOPEN_PLANNED\tRun cross-profile and cross-machine comparisons before release candidate
G29\tClean-machine clone-to-setup-to-test reproducibility\trelease_readiness\ttrue\tOPEN_PLANNED\tValidate independent clean environment without hidden developer paths
G30\tEmpirical minimum/recommended/tested hardware profiles in README\trelease_readiness\ttrue\tOPEN_PLANNED\tDerive from release-scale measurements
G31-T\tTechnical multiplicity integrity and absence of scale-dependent row runaway\ttechnical_audit\ttrue\tPASS_WITH_SCOPE_AMENDMENT\t11b-through-materialization row conservation, primary ID uniqueness, 0.0311% read-locus excess, stable 100k/500k/full multiplicity, and low target concentration; original v0.1.0 machine FAIL preserved
G31-B\tBiological interpretation of 79.29% candidate entry and ~4.9 loci/read\tbiology_interpretation\tfalse\tOPEN_DEFERRED_TO_BIOLOGY_LAYER\tInterpret catalog overlap, +/-500bp padding, transcript concentration, motif equivalence, and recall-preserving candidate narrowing after technical core freeze
"""

REGISTRATION_DOC = """# RNA-TR-Scout Stage 15D full-scale SSOT registration v0.1.0

This versioned registration records deterministic 500k scaling, the Stage15B
memory-bounded validator, the 144-shard execution architecture, full mapping,
the successful 5,312,696-read empirical BAM-to-final v0.1.6 run, and the G31
scope amendment.

The empirical runtime is recorded exactly as 60.041256352 minutes with status
PASS_WITH_DOCUMENTED_TOLERANCE. It is not rewritten as strict <=60-minute PASS.

The original G31 v0.1.0 machine FAIL is preserved. The adopted scope amendment
closes technical multiplicity integrity for current technical-freeze planning
while deferring biological interpretation of the broad 79.2867% candidate-entry
rate and ~4.9 loci/read to the biology layer.

This update does not promote the Stage15 candidate into current_pipeline and
does not modify schema v0.4.2, caller v0.4.1, materializer v0.1.2, prior QC, or
historical release-gate files.
"""


class UpdateError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def require_file(path: Path) -> None:
    if not path.is_file() or path.stat().st_size <= 0:
        raise UpdateError(f"missing or empty required file: {path}")


def require_sha(path: Path, expected: str) -> None:
    require_file(path)
    observed = sha256_file(path)
    if observed != expected:
        raise UpdateError(f"SHA-256 mismatch: {path}: {observed} != {expected}")


def read_two_column(path: Path) -> dict[str, str]:
    require_file(path)
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        header = next(reader, None)
        if not header or len(header) < 2:
            raise UpdateError(f"invalid two-column TSV: {path}")
        return {row[0]: row[1] for row in reader if len(row) >= 2}


def write_metrics(path: Path, rows: Iterable[tuple[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["metric", "value"])
        for key, value in rows:
            writer.writerow([key, value])


def atomic_write(path: Path, payload: bytes, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name("." + path.name + f".part.{os.getpid()}")
    if temp.exists():
        temp.unlink()
    with temp.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    temp.chmod(mode)
    os.replace(temp, path)


def run_checked(command: list[str], log: Path) -> None:
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w", encoding="utf-8") as handle:
        proc = subprocess.run(command, stdout=handle, stderr=subprocess.STDOUT, text=True)
    if proc.returncode != 0:
        tail = log.read_text(encoding="utf-8", errors="replace")[-5000:]
        raise UpdateError(f"command failed rc={proc.returncode}: {' '.join(map(str, command))}\n{tail}")


def make_manifest(root: Path) -> Path:
    manifest = root / "artifact_manifest.tsv"
    rows: list[tuple[str, int, str]] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file() and p != manifest):
        rows.append((str(path.relative_to(root)), path.stat().st_size, sha256_file(path)))
    with manifest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["relative_path", "bytes", "sha256"])
        writer.writerows(rows)
    return manifest


def make_bundle(root: Path, output: Path) -> str:
    make_manifest(root)
    temp = Path(str(output) + f".part.{os.getpid()}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    temp.unlink(missing_ok=True)
    with tarfile.open(temp, "w:gz", format=tarfile.PAX_FORMAT) as tar:
        tar.add(root, arcname=root.name)
    os.replace(temp, output)
    digest = sha256_file(output)
    Path(str(output) + ".sha256").write_text(
        f"{digest}  {output.name}\n", encoding="utf-8"
    )
    return digest


def parse_release_gates(text: str) -> list[dict[str, str]]:
    rows = list(csv.DictReader(text.splitlines(), delimiter="\t"))
    if not rows:
        raise UpdateError("release-gate text is empty")
    ids = [row["gate_id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise UpdateError("release-gate IDs are not unique")
    by = {row["gate_id"]: row for row in rows}
    required = {
        "G06": "PASS_WITH_DOCUMENTED_TOLERANCE",
        "G07": "OPEN",
        "G24": "OPEN",
        "G25": "OPEN_PLANNED",
        "G30": "OPEN_PLANNED",
        "G31-T": "PASS_WITH_SCOPE_AMENDMENT",
        "G31-B": "OPEN_DEFERRED_TO_BIOLOGY_LAYER",
    }
    for gate, expected in required.items():
        if by.get(gate, {}).get("status") != expected:
            raise UpdateError(f"release-gate status mismatch {gate}")
    return rows


def build_source_insertion(
    *,
    updater_sha256: str,
    handover_sha256: str,
    gates_sha256: str,
    evidence_guards: dict[Path, str] | None = None,
    include_source_guards: bool = True,
) -> str:
    guards = evidence_guards if evidence_guards is not None else EVIDENCE_GUARDS
    guard_literal = repr({str(path): digest for path, digest in guards.items()})
    source_guard_literal = repr({
        str(HANDOVER_INSTALL): handover_sha256,
        str(SCRIPT_INSTALL): updater_sha256,
        str(GATES_V030): gates_sha256,
    }) if include_source_guards else "{}"

    body = f'''{PATCH_MARKER}
stage15d_effective_at = "2026-08-10T00:00:00+00:00"
stage15d_run_500k = "{RUN_500K}"
stage15d_mapping_run = "{MAPPING_RUN}"
stage15d_full_run = "{FULL_RUN}"
stage15d_evidence_guards = {guard_literal}
stage15d_source_guards = {source_guard_literal}

def _s15d_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def _s15d_guard(path_text, expected):
    path = Path(path_text)
    if not path.is_file() or path.stat().st_size <= 0:
        raise RuntimeError(f"Stage15D SSOT evidence missing: {{path}}")
    observed = _s15d_sha256(path)
    if observed != expected:
        raise RuntimeError(f"Stage15D SSOT evidence drift: {{path}}: {{observed}} != {{expected}}")
    return path

for _s15d_path, _s15d_expected in {{**stage15d_evidence_guards, **stage15d_source_guards}}.items():
    _s15d_guard(_s15d_path, _s15d_expected)

_s15d_parent = conn.execute(
    "SELECT dataset_id FROM runs WHERE run_id=?", ("{RUN_100K}",)
).fetchone()
if _s15d_parent is None:
    raise RuntimeError("Stage15D SSOT registration requires the registered 100k parent run")
_s15d_dataset_id = _s15d_parent[0]

def _s15d_stage(key, order, name, purpose, category, implementation_status, notes):
    conn.execute(
        """INSERT INTO stage_definitions(
               stage_key,stage_order,name,purpose,category,implementation_status,notes
           ) VALUES(?,?,?,?,?,?,?)
           ON CONFLICT(stage_key) DO UPDATE SET
               stage_order=excluded.stage_order,name=excluded.name,
               purpose=excluded.purpose,category=excluded.category,
               implementation_status=excluded.implementation_status,
               notes=excluded.notes""",
        (key, order, name, purpose, category, implementation_status, notes),
    )

def _s15d_run(run_id, parent_run_id, role, pipeline_version, status, root_path, notes):
    conn.execute(
        """INSERT INTO runs(
               run_id,dataset_id,parent_run_id,run_role,pipeline_version,status,
               started_at,ended_at,root_path,notes
           ) VALUES(?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(run_id) DO UPDATE SET
               dataset_id=excluded.dataset_id,
               parent_run_id=excluded.parent_run_id,
               run_role=excluded.run_role,
               pipeline_version=excluded.pipeline_version,
               status=excluded.status,
               root_path=excluded.root_path,
               notes=excluded.notes""",
        (run_id, _s15d_dataset_id, parent_run_id, role, pipeline_version, status,
         None, None, root_path, notes),
    )

def _s15d_impl(impl_id, stage_key, version, script_path, script_sha, lifecycle, rationale, evidence_path):
    conn.execute(
        """INSERT OR REPLACE INTO implementations(
               implementation_id,stage_key,version,script_path,script_sha256,
               validator_path,validator_sha256,package_version,parameters_json,
               lifecycle_status,supersedes_implementation_id,rationale,
               evidence_path,effective_at
           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (impl_id,stage_key,version,script_path,script_sha,None,None,"v0.4.2",None,
         lifecycle,None,rationale,evidence_path,stage15d_effective_at),
    )

def _s15d_run_stage(run_id, stage_key, impl_id, attempt, status, qc_path, qc_status, notes):
    conn.execute(
        """INSERT OR REPLACE INTO run_stages(
               run_id,stage_key,implementation_id,attempt_tag,status,command_text,
               qc_path,qc_status,started_at,ended_at,notes
           ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (run_id,stage_key,impl_id,attempt,status,None,qc_path,qc_status,None,None,notes),
    )

def _s15d_metric(run_id, stage_key, name, value_text, value_num, unit, denominator, source_path, status="CURRENT"):
    conn.execute(
        """INSERT OR REPLACE INTO metrics(
               run_id,stage_key,metric_name,value_text,value_num,unit,
               denominator_num,source_path,metric_status,recorded_at
           ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (run_id,stage_key,name,str(value_text),value_num,unit,denominator,
         str(source_path),status,stage15d_effective_at),
    )

def _s15d_decision(key, category, title, statement, confidence, rationale, evidence_path):
    decision_id = "decision_" + hashlib.sha256(key.encode()).hexdigest()[:20]
    conn.execute(
        """INSERT OR REPLACE INTO decisions(
               decision_id,decision_key,category,title,statement,status,confidence,
               effective_at,supersedes_decision_id,rationale,evidence_path
           ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (decision_id,key,category,title,statement,"ACTIVE",confidence,
         stage15d_effective_at,None,rationale,str(evidence_path)),
    )

def _s15d_interpretation(key, fact, interpretation, do_not, confidence, evidence_path, metrics):
    interpretation_id = "interpretation_" + hashlib.sha256(key.encode()).hexdigest()[:20]
    conn.execute(
        """INSERT OR REPLACE INTO interpretations(
               interpretation_id,interpretation_key,fact_statement,interpretation,
               do_not_interpret_as,status,confidence,effective_at,
               supersedes_interpretation_id,evidence_path,evidence_metrics_json
           ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (interpretation_id,key,fact,interpretation,do_not,"ACTIVE",confidence,
         stage15d_effective_at,None,str(evidence_path),json.dumps(metrics,sort_keys=True)),
    )

def _s15d_contract(key, name, state, statement, impl_id, evidence_path):
    contract_id = "contract_" + hashlib.sha256(key.encode()).hexdigest()[:20]
    conn.execute(
        """INSERT OR REPLACE INTO algorithm_contracts(
               contract_id,component_key,component_name,implementation_state,
               contract_statement,active_implementation_id,evidence_path,
               effective_at,status
           ) VALUES(?,?,?,?,?,?,?,?,?)""",
        (contract_id,key,name,state,statement,impl_id,str(evidence_path),
         stage15d_effective_at,"ACTIVE"),
    )

def _s15d_source(path_text, source_type, expected):
    path = _s15d_guard(path_text, expected)
    mtime = __import__("datetime").datetime.fromtimestamp(
        path.stat().st_mtime, __import__("datetime").timezone.utc
    ).replace(microsecond=0).isoformat()
    conn.execute(
        """INSERT INTO source_documents(
               source_type,path,sha256,bytes,mtime_utc,content_status,ingested_at
           ) VALUES(?,?,?,?,?,?,?)
           ON CONFLICT(path) DO UPDATE SET
               source_type=excluded.source_type,sha256=excluded.sha256,
               bytes=excluded.bytes,mtime_utc=excluded.mtime_utc,
               content_status=excluded.content_status,ingested_at=excluded.ingested_at""",
        (source_type,str(path),expected,path.stat().st_size,mtime,"PRESENT",stage15d_effective_at),
    )

_s15d_stage("15A_DETERMINISTIC_500K_SCALING",151.4,"Stage 15A deterministic 500k scaling",
            "Validate exact package/caller/checkpoint reproducibility and empirical scaling before full execution.",
            "production_validation","IMPLEMENTED_WITH_GATE",
            "500k deterministic scaling PASS; full empirical runtime subsequently completed.")
_s15d_stage("15B_MEMORY_BOUNDED_VALIDATOR",151.5,"Stage 15B memory-bounded package validator",
            "Preserve frozen validator accept/reject semantics with shard-bounded memory and global external-sort uniqueness.",
            "validation","IMPLEMENTED_WITH_GATE","100k/500k positive parity and 10 negative fixtures PASS; candidate remains provisional, not active.")
_s15d_stage("15C_FULL_MAPPING",151.6,"Stage 15C full splice-aware mapping",
            "Create the mapping-complete 5,312,696-read BAM with exact FASTQ/BAM read-ID parity.",
            "mapping_validation","IMPLEMENTED_WITH_GATE","Mapping time is reported separately and excluded from BAM-to-final runtime gate.")
_s15d_stage("15C_FULLSCALE_EXECUTION_ARCHITECTURE",151.7,"Stage 15C 144-shard execution architecture",
            "Validate shard count as an execution parameter and bind memory-aware full-scale concurrency.",
            "execution_architecture","IMPLEMENTED_WITH_GATE","500k 12-vs-144-shard exact package parity PASS; cross-hardware determinism remains open.")
_s15d_stage("15C_FULL_EMPIRICAL_BAM_TO_FINAL",151.8,"Stage 15C full 5.31M empirical BAM-to-final",
            "Run mapping-complete full BAM through target assignment, projection, caller, materialization, validation, and atomic publication.",
            "production_validation","IMPLEMENTED_WITH_GATE","Correctness/memory/storage/publication PASS; runtime PASS_WITH_DOCUMENTED_TOLERANCE; restart/determinism open.")
_s15d_stage("15D_G31_ROW_EXPANSION_AUDIT",151.9,"Stage 15D G31 row-expansion and candidate-entry audit",
            "Quantify full-scale row lineage, multiplicity, duplicate/concentration, catalog geometry, and candidate-entry rate.",
            "governance_validation","IMPLEMENTED_WITH_GATE","Original machine FAIL preserved; technical multiplicity accepted by scope amendment, biology interpretation deferred.")

_s15d_run(stage15d_run_500k,"{RUN_100K}","DETERMINISTIC_SCALING_BENCHMARK",
           "rnatr_stage15a_deterministic_500k_scaling_v0.1.4_compare_amendment",
           "PASS","/mnt/intelssd/rnatr_project/results/15_stage15a_bam_to_final/{RUN_500K}/v0.1.1_500k_scaling",
           "Exact package/caller/checkpoint reproducibility and nested-250k parity PASS; active pipeline unchanged.")
_s15d_run(stage15d_mapping_run,"{RUN_100K}","FULL_MAPPING_BENCHMARK",
           "minimap2_splice_cDNA_full_v1","PASS",
           "/mnt/intelssd/rnatr_project/results/11_mapping/{MAPPING_RUN}",
           "5,312,696 primary records with exact FASTQ/BAM read-ID multiset parity; mapping excluded from BAM-to-final gate.")
_s15d_run(stage15d_full_run,stage15d_mapping_run,"FULL_EMPIRICAL_CORE_BENCHMARK",
           "rnatr_stage15c_full5312696_bam_to_final_v0.1.6",
           "PASS_WITH_DOCUMENTED_TOLERANCE",
           "/mnt/intelssd/rnatr_project/results/15_stage15c_fullscale_bam_to_final/{FULL_RUN}/v0.1.6",
           "Full 5.31M BAM-to-final correctness PASS at 60.041256352 min; restart/resume and release-scale determinism remain open.")

_s15d_impl("impl_stage15a_scaling_500k_v0_1_4","15A_DETERMINISTIC_500K_SCALING",
           "v0.1.4_compare_amendment",None,None,"PROVISIONAL",
           "Accepted deterministic 500k scaling evidence; not an active pipeline implementation.","{QC_500K}")
_s15d_impl("impl_stage15b_memory_bounded_validator_v0_1_0","15B_MEMORY_BOUNDED_VALIDATOR",
           "v0.1.0","{STAGE15B_VALIDATOR}","{EVIDENCE_GUARDS[STAGE15B_VALIDATOR]}","PROVISIONAL",
           "Frozen-semantics equivalent memory-bounded package validator; active promotion deferred.","{STAGE15B_QC}")
_s15d_impl("impl_stage15c_full_mapping_v0_1_0","15C_FULL_MAPPING","v0.1.0",
           "{MAPPING_SCRIPT}","{EVIDENCE_GUARDS[MAPPING_SCRIPT]}","REFERENCE",
           "Full mapping implementation used to create the benchmark BAM.","{MAPPING_QC}")
_s15d_impl("impl_stage15c_144shard_architecture_v0_1_1","15C_FULLSCALE_EXECUTION_ARCHITECTURE",
           "v0.1.1","{ARCH_SCRIPT}","{EVIDENCE_GUARDS[ARCH_SCRIPT]}","REFERENCE_AUDIT",
           "Execution-only 144-shard architecture with exact 500k scientific parity.","{ARCH_QC}")
_s15d_impl("impl_stage15c_full_runner_v0_1_6","15C_FULL_EMPIRICAL_BAM_TO_FINAL","v0.1.6",
           "{FULL_RUNNER}","{EVIDENCE_GUARDS[FULL_RUNNER]}","PROVISIONAL",
           "Validated full-scale candidate; explicit active-path promotion remains prohibited.","{FULL_QC}")
_s15d_impl("impl_stage15d_g31_audit_v0_1_0","15D_G31_ROW_EXPANSION_AUDIT","v0.1.0",
           "{G31_SCRIPT}","{EVIDENCE_GUARDS[G31_SCRIPT]}","REFERENCE_AUDIT",
           "Read-only full-scale multiplicity audit; original machine result retained and scope-amended by Pro/user decision.","{G31_QC}")

_s15d_run_stage(stage15d_run_500k,"15A_DETERMINISTIC_500K_SCALING","impl_stage15a_scaling_500k_v0_1_4",
                 "v0.1.4","PASS","{QC_500K}","PASS","500k deterministic package/caller/checkpoint/nested parity PASS.")
_s15d_run_stage(stage15d_run_500k,"15B_MEMORY_BOUNDED_VALIDATOR","impl_stage15b_memory_bounded_validator_v0_1_0",
                 "v0.1.0","PASS","{STAGE15B_QC}","PASS","Frozen/candidate accept-reject equivalence PASS.")
_s15d_run_stage(stage15d_run_500k,"15C_FULLSCALE_EXECUTION_ARCHITECTURE","impl_stage15c_144shard_architecture_v0_1_1",
                 "v0.1.1","PASS","{ARCH_QC}","PASS","12-vs-144 shard scientific output exact parity PASS.")
_s15d_run_stage(stage15d_mapping_run,"15C_FULL_MAPPING","impl_stage15c_full_mapping_v0_1_0",
                 "v0.1.0","PASS","{MAPPING_QC}","PASS","Full mapping and read-ID parity PASS.")
_s15d_run_stage(stage15d_full_run,"15C_FULL_EMPIRICAL_BAM_TO_FINAL","impl_stage15c_full_runner_v0_1_6",
                 "v0.1.6","PASS_WITH_DOCUMENTED_TOLERANCE","{FULL_QC}","PASS","Correctness/memory/storage/publication PASS; runtime exceeded 60 min by 2.475 s within declared tolerance.")
_s15d_run_stage(stage15d_full_run,"15D_G31_ROW_EXPANSION_AUDIT","impl_stage15d_g31_audit_v0_1_0",
                 "v0.1.0","REVIEW_SCOPE_AMENDMENT","{G31_QC}","MACHINE_FAIL_PRESERVED_G31T_PASS_G31B_DEFERRED",
                 "Original machine FAIL remains immutable; technical integrity closed by scope amendment, biology interpretation deferred.")

for _name,_value,_num,_unit,_denom in [
    ("input_reads",500000,500000,"reads",None),
    ("bam_to_final_seconds",335.3816997719696,335.3816997719696,"seconds",None),
    ("full_projection_minutes",59.39270049505812,59.39270049505812,"minutes",None),
    ("candidate_rows",1948859,1948859,"rows",None),
    ("candidate_reads",396549,396549,"reads",500000),
]:
    _s15d_metric(stage15d_run_500k,"15A_DETERMINISTIC_500K_SCALING",_name,_value,_num,_unit,_denom,"{QC_500K}")

for _name,_value,_num,_unit,_denom in [
    ("input_reads",5312696,5312696,"reads",None),
    ("bam_to_final_seconds",3602.475381092,3602.475381092,"seconds",None),
    ("bam_to_final_minutes",60.041256352,60.041256352,"minutes",None),
    ("candidate_reads",4212263,4212263,"reads",5312696),
    ("candidate_rows",20656258,20656258,"rows",None),
    ("caller_called_rows",8524435,8524435,"rows",20656258),
    ("caller_no_call_rows",12131823,12131823,"rows",20656258),
    ("caller_error_rows",0,0,"rows",20656258),
    ("repeat_events_rows",8523140,8523140,"rows",None),
    ("repeat_segments_rows",8573315,8573315,"rows",None),
    ("repeat_interruptions_rows",43399,43399,"rows",None),
    ("maximum_host_used_fraction",0.272065,0.272065,"fraction",1),
    ("peak_temporary_and_output_bytes",146580576495,146580576495,"bytes",None),
    ("minimum_project_free_bytes",165594337280,165594337280,"bytes",None),
    ("checkpoint_rows",1884,1884,"rows",None),
    ("checkpoint_bytes",140029015504,140029015504,"bytes",None),
]:
    _s15d_metric(stage15d_full_run,"15C_FULL_EMPIRICAL_BAM_TO_FINAL",_name,_value,_num,_unit,_denom,"{FULL_QC}")

for _name,_value,_num,_unit,_denom,_source in [
    ("candidate_read_rate",0.792867312566,0.792867312566,"fraction",5312696,"{G31_QC}"),
    ("candidate_rows_per_candidate_read",4.903838625461,4.903838625461,"ratio",4212263,"{G31_QC}"),
    ("candidate_rows_per_input_read",3.888093352226,3.888093352226,"ratio",5312696,"{G31_QC}"),
    ("exact_overlap_candidate_reads",3020451,3020451,"reads",5312696,"{G31_RATE}"),
    ("proximal_only_candidate_reads",1191812,1191812,"reads",5312696,"{G31_RATE}"),
    ("assignment_excess_over_unique_loci",6431,6431,"rows",20656258,"{G31_RATE}"),
]:
    _s15d_metric(stage15d_full_run,"15D_G31_ROW_EXPANSION_AUDIT",_name,_value,_num,_unit,_denom,_source)

_s15d_decision(
    "stage15c_full_empirical_acceptance_v0_1_6","performance_validation",
    "Accept full 5.31M empirical BAM-to-final with documented first-freeze tolerance",
    "The 5,312,696-read BAM-to-final v0.1.6 run completed in 60.041256352 minutes with correctness, memory, storage, validators, runtime-generated script/path binding, and atomic publication PASS. The result is PASS_WITH_DOCUMENTED_TOLERANCE, not strict <=60-minute PASS.",
    "HIGH","The strict threshold was exceeded by only 2.475 seconds and the predeclared thesis/core-freeze tolerance allows <=62 minutes; the 30-minute target remains open.","{FULL_QC}")
_s15d_decision(
    "stage15c_active_promotion_deferred_v0_1_0","architecture_governance",
    "Keep the validated Stage15C candidate provisional until remaining release gates close",
    "Do not modify current_pipeline or promote the Stage15C runner before release-scale determinism, full-scale restart/resume, PRE_RELEASE_CANDIDATE Architecture audit, clean-install, and explicit promotion.",
    "HIGH","Empirical full-scale PASS is necessary but not sufficient for active release promotion.","{FULL_QC}")
_s15d_decision(
    "g31_scope_split_technical_vs_biology_v0_1_0","validation_scope",
    "Split G31 into technical multiplicity integrity and biological candidate-entry interpretation",
    "Preserve the original G31 v0.1.0 machine FAIL. Adopt G31-T PASS_WITH_SCOPE_AMENDMENT because row conservation, primary-ID uniqueness, cross-scale stability, low read-locus excess, and low target concentration show no scale-dependent technical runaway. Defer G31-B candidate-rate and multiplicity meaning to the biology layer as nonblocking for current technical freeze.",
    "HIGH","The machine fail used broader field-level semantic assumptions than the technical runaway question; deep biological interpretation is intentionally deferred by user decision.","{G31_QC}")
_s15d_decision(
    "internal_beta_release_readiness_g25_g30_v0_1_0","release_readiness",
    "Register portable internal-beta requirements as planned blocking gates",
    "G25-G30 require reference bootstrap, hardware detection, adaptive concurrency, cross-hardware logical determinism, clean-machine reproducibility, and empirical hardware documentation. All remain OPEN_PLANNED and must not be reported as implemented.",
    "HIGH","The project is now complex enough that developer-local paths and manual resource tuning are unacceptable release assumptions.","{GATES_V030}")

_s15d_interpretation(
    "stage15c_full_runtime_60_041_minutes_v0_1_0",
    "The empirical BAM-to-final timer was 60.041256352 minutes; mapping was excluded while partition, validators, and atomic publication were included.",
    "This satisfies the predeclared documented first-freeze tolerance but not the strict <=60.000-minute threshold.",
    "Do not report this result as strict 60-minute PASS or as meeting the 30-minute target.",
    "HIGH","{FULL_QC}",{{"seconds_over_60min":2.475381092,"tolerance_ceiling_minutes":62.0}})
_s15d_interpretation(
    "g31_fullscale_multiplicity_scope_v0_1_0",
    "Candidate/projection/caller/general/read_evidence rows were all 20,656,258; unique read-locus rows were 20,649,827; candidate rate and rows/read were stable across 100k, 500k, and full scale.",
    "There is no evidence of scale-dependent row runaway or unexplained post-11b row birth for the current technical scope.",
    "Do not treat this as complete biological validation of every field-level caller/materializer semantic or as proof that candidate entry is optimally narrow.",
    "HIGH","{G31_QC}",{{"read_locus_excess_rows":6431,"candidate_rows":20656258,"top1_target_share":0.002830522}})
_s15d_interpretation(
    "g31_candidate_entry_79pct_v0_1_0",
    "4,212,263 of 5,312,696 reads (79.2867%) entered the broad 11b candidate set; 3,020,451 had exact catalog overlap and 1,191,812 were proximity-only within +/-500 bp.",
    "The rate describes sensitivity-oriented candidate entry in a transcriptome-concentrated RNA dataset and is deferred for biology/algorithmic interpretation.",
    "Do not interpret 79.2867% as repeat-positive prevalence, pathogenicity, expansion prevalence, or final candidate prevalence.",
    "HIGH","{G31_RATE}",{{"candidate_rate":0.792867312566,"exact_overlap_reads":3020451,"proximal_only_reads":1191812}})

_s15d_contract(
    "stage15b_memory_bounded_validator_v0_1_0","Stage15B memory-bounded package validator",
    "EQUIVALENCE_PASS_PROVISIONAL_NOT_ACTIVE",
    "Shard-wise frozen v0.4.2 validation plus exact global external-sort primary-ID uniqueness must preserve frozen accept/reject semantics. Positive 100k/500k and 10 negative fixtures pass. Scope excludes locus aggregation.",
    "impl_stage15b_memory_bounded_validator_v0_1_0","{STAGE15B_QC}")
_s15d_contract(
    "stage15c_fullscale_execution_v0_1_6","Stage15C full-scale execution contract",
    "EMPIRICAL_FULLSCALE_PASS_WITH_TOLERANCE_RESTART_DETERMINISM_OPEN",
    "Use 144 read-coherent shards, concurrency 12, caller workers 2/shard, validator workers 3, 512M external sort, PYTHONHASHSEED=0, prepartition runtime-script/path audit, and post-11b maximum 164204 candidate rows/shard. Full empirical correctness passes; restart/resume and release-scale determinism remain open.",
    "impl_stage15c_full_runner_v0_1_6","{FULL_QC}")
_s15d_contract(
    "g31_technical_multiplicity_integrity_v0_1_0","G31-T technical multiplicity integrity",
    "PASS_WITH_SCOPE_AMENDMENT",
    "Technical freeze accepts row conservation, primary-ID uniqueness, stable cross-scale candidate rate/multiplicity, minimal read-locus excess, and low target concentration as evidence against scale-dependent runaway. The original machine FAIL remains historical evidence.",
    "impl_stage15d_g31_audit_v0_1_0","{G31_QC}")
_s15d_contract(
    "g31_biological_candidate_entry_interpretation_v0_1_0","G31-B biological candidate-entry interpretation",
    "OPEN_DEFERRED_TO_BIOLOGY_LAYER",
    "Interpret the 79.2867% candidate-entry rate, +/-500bp padding, ~4.9 loci/read, catalog overlap, motif equivalence, and recall-preserving narrowing only in the later biology/optimization phase.",
    None,"{G31_RATE}")
_s15d_contract(
    "release_readiness_g25_g30_v0_1_0","Internal-beta release readiness G25-G30",
    "DESIGNED_NOT_IMPLEMENTED",
    "Portable reference bootstrap, resource detection, adaptive concurrency, cross-hardware determinism, clean-machine install, and empirical hardware profiles are required before internal beta/release candidate.",
    None,"{GATES_V030}")

for _key,_statement,_severity,_mitigation,_evidence in [
    ("STAGE15C_FULL_RUNTIME_USES_DOCUMENTED_TOLERANCE","The empirical full BAM-to-final runtime is 60.041256352 minutes and therefore is not strict <=60-minute PASS.","MODERATE","Retain exact wording in SSOT, thesis, release notes, and benchmark tables; continue the 30-minute optimization target.","{FULL_QC}"),
    ("STAGE15C_RELEASE_SCALE_DETERMINISM_OPEN","Release-scale independent deterministic reproduction of the full scientific package has not yet been executed.","HIGH","Run release-scale logical reproducibility before Core Freeze.","{FULL_QC}"),
    ("STAGE15C_FULLSCALE_RESTART_RESUME_OPEN","Full-scale intentional-stop, corrupt-checkpoint rejection, selective resume, clean/resumed parity, and second-resume no-op are not yet validated.","HIGH","Execute the versioned full-scale restart/resume contract using the v0.1.6 checkpoint inventory.","{CHECKPOINT_MANIFEST}"),
    ("G31_BIOLOGICAL_CANDIDATE_ENTRY_DEFERRED","The biological meaning and optimality of the 79.2867% candidate-entry rate and ~4.9 loci/read remain unresolved.","MODERATE","Address in the biology/optimization layer without blocking current technical-freeze planning.","{G31_RATE}"),
    ("STAGE15C_ACTIVE_PIPELINE_NOT_PROMOTED","The empirically validated Stage15C candidate is not the current active pipeline.","HIGH","Promote only after determinism, restart/resume, pre-release audit, and clean-install gates close.","{FULL_QC}"),
]:
    conn.execute(
        """INSERT OR REPLACE INTO limitations(
               limitation_key,statement,severity,status,mitigation,evidence_path,effective_at
           ) VALUES(?,?,?,?,?,?,?)""",
        (_key,_statement,_severity,"ACTIVE",_mitigation,_evidence,stage15d_effective_at),
    )

for _key,_question,_priority,_blocking,_next,_evidence in [
    ("RELEASE_SCALE_DETERMINISM","Does an independent release-scale execution reproduce the full scientific package exactly at the logical level?","CRITICAL",1,"Design and execute a second release-scale comparison with runtime-only metadata excluded from scientific parity.","{FULL_QC}"),
    ("FULLSCALE_RESTART_RESUME","Can the full run reject corrupt checkpoints, selectively resume, match the clean package, and become a second-resume no-op?","CRITICAL",1,"Run intentional-stop/corruption/selective-resume validation from the v0.1.6 checkpoint inventory.","{CHECKPOINT_MANIFEST}"),
    ("PRE_RELEASE_CANDIDATE_ARCHITECTURE_AUDIT","Are SSOT, active paths, frozen schema/contracts, runtime-generated artifacts, restart, biology roadmap, and release gates globally consistent?","CRITICAL",1,"Run PRE_RELEASE_CANDIDATE Architecture consistency audit after determinism/restart.","{FULL_QC}"),
    ("ACTIVE_PATH_PROMOTION","When and how should the validated Stage15 candidate replace the legacy active P0/P1 pipeline?","CRITICAL",1,"Perform explicit versioned promotion only after remaining Core Freeze gates pass.","{FULL_QC}"),
    ("CLEAN_INSTALL_INTERNAL_BETA","Can an independent clean machine install software/references and reproduce a test run without developer-local paths?","HIGH",1,"Implement and validate G25-G30 before v0.5.0-rc1/internal beta.","{GATES_V030}"),
    ("G31_BIOLOGICAL_CANDIDATE_ENTRY_INTERPRETATION","What biological and algorithmic factors explain the broad candidate-entry rate and ~4.9 loci/read, and can entry be narrowed without recall loss?","MODERATE",0,"Defer to biology/optimization phase; retain exact/proximal/catalog-source decomposition.","{G31_RATE}"),
]:
    conn.execute(
        """INSERT OR REPLACE INTO open_questions(
               question_key,question,priority,status,blocking,next_action,evidence_path,effective_at
           ) VALUES(?,?,?,?,?,?,?,?)""",
        (_key,_question,_priority,"OPEN",_blocking,_next,_evidence,stage15d_effective_at),
    )

for _failure_id,_attempt,_summary,_root_cause,_resolution,_source,_superseded in [
    ("stage15c_full_v014_runtime_runid_binding","v0.1.4","Full execution stopped in the first 11b wave after fresh partition.","Runtime-generated 11b scripts retained the deterministic-500k analysis run ID and searched for nonexistent 500k-named shard BAMs.","v0.1.6 audits 432 generated scripts and 3312 path bindings before the timer/partition and uses fresh artifacts.","/mnt/intelssd/rnatr_project/qc/15_stage15c_fullscale_bam_to_final/{FULL_RUN}/v0.1.4/stage15c_full_empirical_run.failure.txt","rnatr_stage15c_full5312696_bam_to_final_v0.1.6"),
    ("stage15c_full_v015_runtime_path_binding","v0.1.5","The v0.1.5 runner was rejected before preflight/execution.","Run ID rebinding did not replace old 500k candidate/window paths and BOUND_SOURCE_ROOT was undefined.","v0.1.6 binds and audits full runtime ID plus path graph; v0.1.5 artifacts were not reused.","/mnt/intelssd/rnatr_project/qc/15_stage15c_runtime_bound_runner_build/{FULL_RUN}/v0.1.5","rnatr_stage15c_full5312696_bam_to_final_v0.1.6"),
]:
    conn.execute(
        """INSERT OR REPLACE INTO failures(
               failure_id,run_id,stage_key,attempt_version,status,summary,
               root_cause,resolution,source_path,superseded_by,recorded_at
           ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (_failure_id,stage15d_full_run,"15C_FULL_EMPIRICAL_BAM_TO_FINAL",_attempt,
         "RESOLVED",_summary,_root_cause,_resolution,_source,_superseded,stage15d_effective_at),
    )

for _path_text,_expected in {{**stage15d_evidence_guards, **stage15d_source_guards}}.items():
    _s15d_source(_path_text,"stage15d_fullscale_registration_evidence",_expected)
'''
    return textwrap.indent(textwrap.dedent(body).rstrip() + "\n", "    ")


def verify_evidence_semantics() -> dict[str, Any]:
    qc500 = read_two_column(QC_500K)
    required500 = {
        "deterministic_500k_scaling": "PASS",
        "package_exact_logical_reproducibility": "true",
        "caller_hashseed_logical_reproducibility": "true",
        "checkpoint_logical_reproducibility": "true",
        "nested_250k_scientific_parity": "true",
        "active_pipeline_modified": "false",
        "ssot_modified": "false",
    }
    for key, expected in required500.items():
        if qc500.get(key) != expected:
            raise UpdateError(f"500k QC mismatch {key}: {qc500.get(key)} != {expected}")

    mapping = read_two_column(MAPPING_QC)
    for key, expected in {
        "expected_input_reads": "5312696",
        "primary_records": "5312696",
        "primary_mapped_reads": "5123713",
        "primary_unmapped_reads": "188983",
        "audit_status": "PASS",
    }.items():
        if mapping.get(key) != expected:
            raise UpdateError(f"full mapping QC mismatch {key}: {mapping.get(key)}")
    mapping_ids = read_two_column(MAPPING_READ_ID_QC)
    for key, expected in {
        "fastq_id_rows": "5312696",
        "bam_primary_id_rows": "5312696",
        "sorted_multiset_exact_parity": "PASS",
    }.items():
        if mapping_ids.get(key) != expected:
            raise UpdateError(f"full mapping read-ID QC mismatch {key}: {mapping_ids.get(key)}")

    s15b = read_two_column(STAGE15B_QC)
    for key, expected in {
        "validator_equivalence_status": "PASS",
        "positive_100k_accept_parity": "PASS",
        "positive_500k_accept_parity": "PASS",
        "negative_fixture_accept_reject_parity": "PASS",
        "candidate_promoted_active": "false",
        "audit_status": "PASS",
    }.items():
        if s15b.get(key) != expected:
            raise UpdateError(f"Stage15B QC mismatch {key}")

    arch = read_two_column(ARCH_QC)
    for key, expected in {
        "shard_count": "144",
        "stage_concurrency": "12",
        "core_package_raw_and_logical_parity_to_12shard": "true",
        "scientific_output_independent_of_12_vs_144_shards": "true",
        "audit_status": "PASS",
    }.items():
        if arch.get(key) != expected:
            raise UpdateError(f"144-shard architecture QC mismatch {key}")

    full = read_two_column(FULL_QC)
    for key, expected in {
        "input_reads": "5312696",
        "runtime_gate": "PASS_WITH_DOCUMENTED_TOLERANCE",
        "memory_gate": "PASS",
        "storage_gate": "PASS",
        "atomic_publication": "PASS",
        "runtime_generated_script_audit_status": "PASS",
        "runtime_generated_path_binding_status": "PASS",
        "package_final_published": "true",
        "release_scale_determinism_executed": "false",
        "fullscale_restart_resume_executed": "false",
        "stage_status": "PASS",
        "audit_status": "PASS",
    }.items():
        if full.get(key) != expected:
            raise UpdateError(f"full empirical QC mismatch {key}: {full.get(key)}")
    minutes = float(full["bam_to_final_minutes"])
    if not (60.0 < minutes <= 62.0):
        raise UpdateError(f"full runtime does not match documented tolerance scope: {minutes}")

    g31 = read_two_column(G31_QC)
    for key, expected in {
        "g31_machine_status": "FAIL_OVEREXPANSION_OR_LINEAGE",
        "g31_core_freeze_gate_status": "FAIL_BLOCKING",
        "stage_row_conservation": "PASS",
        "primary_key_duplicate_status": "PASS",
        "cross_scale_stability_status": "PASS_STABLE",
        "full_5_31m_rerun": "false",
    }.items():
        if g31.get(key) != expected:
            raise UpdateError(f"G31 historical QC mismatch {key}")

    rate = read_two_column(G31_RATE)
    if rate.get("candidate_reads") != "4212263" or rate.get("assignment_excess_over_unique_loci") != "6431":
        raise UpdateError("G31 candidate-rate evidence mismatch")

    return {
        "runtime_minutes": minutes,
        "candidate_rate": float(g31["candidate_read_rate"]),
        "candidate_rows": int(g31["candidate_rows"]),
        "candidate_reads": int(g31["candidate_reads"]),
    }


def verify_baseline(*, require_patch_absent: bool = True) -> dict[str, str]:
    if PROJECT_ROOT != Path("/mnt/intelssd/rnatr_project"):
        raise UpdateError("unexpected project root")
    require_sha(SSOT_CLI, EXPECTED_BASELINE_CLI_SHA256)
    require_sha(SSOT_DB, EXPECTED_BASELINE_DB_SHA256)
    require_sha(CORE_SCHEMA, EXPECTED_CORE_SCHEMA_SHA256)
    require_sha(GATES_V024, EXPECTED_GATES_V024_SHA256)
    require_sha(HANDOVER_DOWNLOAD, EXPECTED_HANDOVER_SHA256)
    for path, expected in EVIDENCE_GUARDS.items():
        require_sha(path, expected)
    source = SSOT_CLI.read_text(encoding="utf-8")
    if require_patch_absent and PATCH_MARKER in source:
        raise UpdateError("SSOT source already contains Stage15D registration marker")
    if source.count(PATCH_ANCHOR) != 1:
        raise UpdateError(f"SSOT source patch anchor count is {source.count(PATCH_ANCHOR)}")
    if GATES_V030.exists():
        raise UpdateError(f"versioned release gate already exists: {GATES_V030}")
    if UPDATE_QC_ROOT.exists() or UPDATE_META_ROOT.exists():
        raise UpdateError("versioned Stage15D SSOT update output already exists")
    require_file(SSOT_EXPORTS / "current_pipeline.tsv")
    con = sqlite3.connect(SSOT_DB)
    try:
        if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise UpdateError("SSOT baseline integrity_check failed")
        if list(con.execute("PRAGMA foreign_key_check")):
            raise UpdateError("SSOT baseline foreign_key_check failed")
        parent = con.execute("SELECT dataset_id FROM runs WHERE run_id=?", (RUN_100K,)).fetchone()
        if parent is None:
            raise UpdateError("registered 100k parent run missing")
    finally:
        con.close()
    return {
        "ssot_cli_sha256": sha256_file(SSOT_CLI),
        "ssot_db_sha256": sha256_file(SSOT_DB),
        "current_pipeline_sha256": sha256_file(SSOT_EXPORTS / "current_pipeline.tsv"),
        "core_schema_sha256": sha256_file(CORE_SCHEMA),
    }


def preflight_payload() -> dict[str, Any]:
    baseline = verify_baseline()
    semantics = verify_evidence_semantics()
    parse_release_gates(RELEASE_GATES_V030_TEXT)
    updater_sha = sha256_file(Path(__file__).resolve())
    gates_sha = sha256_bytes(RELEASE_GATES_V030_TEXT.encode("utf-8"))
    insertion = build_source_insertion(
        updater_sha256=updater_sha,
        handover_sha256=EXPECTED_HANDOVER_SHA256,
        gates_sha256=gates_sha,
    )
    source = SSOT_CLI.read_text(encoding="utf-8")
    patched = source.replace(PATCH_ANCHOR, "\n\n" + insertion + PATCH_ANCHOR, 1)
    compile(patched, str(SSOT_CLI), "exec")
    return {
        **baseline,
        **semantics,
        "updater_sha256": updater_sha,
        "handover_sha256": EXPECTED_HANDOVER_SHA256,
        "release_gates_v030_sha256": gates_sha,
        "source_insertion_sha256": sha256_bytes(insertion.encode("utf-8")),
        "patched_source_compile": "PASS",
        "active_pipeline_modified": "false",
        "core_schema_modified": "false",
        "ssot_mutation_started": "false",
        "preflight_status": "PASS_READY_FOR_PRO_REVIEW",
    }


def run_preflight() -> int:
    payload = preflight_payload()
    DOWNLOADS.mkdir(parents=True, exist_ok=True)
    write_metrics(PREFLIGHT_QC_DOWNLOAD, payload.items())

    parent = Path(tempfile.mkdtemp(prefix="rnatr_stage15d_ssot_preflight_"))
    root = parent / "rnatr_stage15d_ssot_update_fullscale_handover_v0.1.0_preflight"
    root.mkdir()
    shutil.copy2(PREFLIGHT_QC_DOWNLOAD, root / PREFLIGHT_QC_DOWNLOAD.name)
    (root / GATES_V030.name).write_text(RELEASE_GATES_V030_TEXT, encoding="utf-8", newline="\n")
    (root / "source_insertion.py.txt").write_text(
        build_source_insertion(
            updater_sha256=payload["updater_sha256"],
            handover_sha256=EXPECTED_HANDOVER_SHA256,
            gates_sha256=payload["release_gates_v030_sha256"],
        ),
        encoding="utf-8",
        newline="\n",
    )
    shutil.copy2(Path(__file__).resolve(), root / Path(__file__).name)
    shutil.copy2(HANDOVER_DOWNLOAD, root / HANDOVER_DOWNLOAD.name)
    (root / "registration_plan.md").write_text(REGISTRATION_DOC, encoding="utf-8", newline="\n")
    bundle_sha = make_bundle(root, PREFLIGHT_BUNDLE)
    shutil.rmtree(parent, ignore_errors=True)

    print("===== RNA-TR-Scout Stage 15D SSOT update preflight =====")
    for key in (
        "preflight_status", "runtime_minutes", "candidate_rate", "candidate_rows",
        "ssot_cli_sha256", "ssot_db_sha256", "current_pipeline_sha256",
        "updater_sha256", "release_gates_v030_sha256", "source_insertion_sha256",
        "ssot_mutation_started", "active_pipeline_modified", "core_schema_modified",
    ):
        print(f"{key}\t{payload[key]}")
    print(f"PREFLIGHT_QC\t{PREFLIGHT_QC_DOWNLOAD}")
    print(f"OUTPUT_BUNDLE\t{PREFLIGHT_BUNDLE}")
    print(f"OUTPUT_BUNDLE_SHA256\t{bundle_sha}")
    print("NEXT_GATE\tPRO_REVIEW_THEN_EXPLICIT_EXECUTE")
    return 0


def backup_state(backup: Path) -> dict[str, bool]:
    backup.mkdir(parents=True, exist_ok=False)
    preexisting = {
        "gates_v030": GATES_V030.exists(),
        "handover_install": HANDOVER_INSTALL.exists(),
        "script_install": SCRIPT_INSTALL.exists(),
        "doc_install": DOC_INSTALL.exists(),
        "update_qc": UPDATE_QC_ROOT.exists(),
        "update_meta": UPDATE_META_ROOT.exists(),
    }
    for path in (SSOT_CLI, SSOT_DB, SSOT_SUMMARY):
        if path.exists():
            shutil.copy2(path, backup / path.name)
    if SSOT_EXPORTS.exists():
        shutil.copytree(SSOT_EXPORTS, backup / "exports")
    for path in (GATES_V030, HANDOVER_INSTALL, SCRIPT_INSTALL, DOC_INSTALL):
        if path.exists():
            dst = backup / ("versioned_" + path.name)
            shutil.copy2(path, dst)
    (backup / "preexisting.json").write_text(json.dumps(preexisting, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return preexisting


def restore_state(backup: Path, preexisting: dict[str, bool]) -> None:
    for name, target in (
        (SSOT_CLI.name, SSOT_CLI),
        (SSOT_DB.name, SSOT_DB),
        (SSOT_SUMMARY.name, SSOT_SUMMARY),
    ):
        src = backup / name
        if src.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
        elif target.exists() and name == SSOT_SUMMARY.name:
            target.unlink()
    if SSOT_EXPORTS.exists():
        shutil.rmtree(SSOT_EXPORTS)
    if (backup / "exports").exists():
        shutil.copytree(backup / "exports", SSOT_EXPORTS)

    for key, path in (
        ("gates_v030", GATES_V030),
        ("handover_install", HANDOVER_INSTALL),
        ("script_install", SCRIPT_INSTALL),
        ("doc_install", DOC_INSTALL),
    ):
        saved = backup / ("versioned_" + path.name)
        if preexisting.get(key) and saved.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(saved, path)
        elif path.exists():
            path.unlink()
    if not preexisting.get("update_qc") and UPDATE_QC_ROOT.exists():
        shutil.rmtree(UPDATE_QC_ROOT)
    if not preexisting.get("update_meta") and UPDATE_META_ROOT.exists():
        shutil.rmtree(UPDATE_META_ROOT)


def verify_preflight_binding() -> dict[str, str]:
    require_file(PREFLIGHT_QC_DOWNLOAD)
    qc = read_two_column(PREFLIGHT_QC_DOWNLOAD)
    required = {
        "preflight_status": "PASS_READY_FOR_PRO_REVIEW",
        "ssot_mutation_started": "false",
        "active_pipeline_modified": "false",
        "core_schema_modified": "false",
        "updater_sha256": sha256_file(Path(__file__).resolve()),
        "handover_sha256": EXPECTED_HANDOVER_SHA256,
        "ssot_cli_sha256": EXPECTED_BASELINE_CLI_SHA256,
        "ssot_db_sha256": EXPECTED_BASELINE_DB_SHA256,
    }
    for key, expected in required.items():
        if qc.get(key) != expected:
            raise UpdateError(f"preflight binding mismatch {key}: {qc.get(key)} != {expected}")
    expected_gates = sha256_bytes(RELEASE_GATES_V030_TEXT.encode("utf-8"))
    if qc.get("release_gates_v030_sha256") != expected_gates:
        raise UpdateError("preflight release-gate hash differs from current updater")
    return qc


def postcheck(before_pipeline_sha: str, before_schema_sha: str) -> dict[str, Any]:
    run_checked([sys.executable, str(SSOT_CLI), "--project-root", str(PROJECT_ROOT), "rebuild"], UPDATE_QC_ROOT / "logs/ssot_rebuild.log")
    run_checked([sys.executable, str(SSOT_CLI), "--project-root", str(PROJECT_ROOT), "validate"], UPDATE_QC_ROOT / "logs/ssot_validate_after.log")
    if sha256_file(CORE_SCHEMA) != before_schema_sha:
        raise UpdateError("core schema changed during SSOT update")
    after_pipeline_sha = sha256_file(SSOT_EXPORTS / "current_pipeline.tsv")
    if after_pipeline_sha != before_pipeline_sha:
        raise UpdateError("current_pipeline changed during Stage15D SSOT registration")

    con = sqlite3.connect(SSOT_DB)
    try:
        if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise UpdateError("post-update SSOT integrity_check failed")
        if list(con.execute("PRAGMA foreign_key_check")):
            raise UpdateError("post-update SSOT foreign_key_check failed")
        checks = {
            "run_500k": con.execute("SELECT count(*) FROM runs WHERE run_id=? AND status='PASS'", (RUN_500K,)).fetchone()[0],
            "mapping_run": con.execute("SELECT count(*) FROM runs WHERE run_id=? AND status='PASS'", (MAPPING_RUN,)).fetchone()[0],
            "full_run": con.execute("SELECT count(*) FROM runs WHERE run_id=? AND status='PASS_WITH_DOCUMENTED_TOLERANCE'", (FULL_RUN,)).fetchone()[0],
            "full_stage": con.execute("SELECT count(*) FROM stage_definitions WHERE stage_key='15C_FULL_EMPIRICAL_BAM_TO_FINAL'").fetchone()[0],
            "g31_stage": con.execute("SELECT count(*) FROM stage_definitions WHERE stage_key='15D_G31_ROW_EXPANSION_AUDIT'").fetchone()[0],
            "full_impl": con.execute("SELECT count(*) FROM implementations WHERE implementation_id='impl_stage15c_full_runner_v0_1_6' AND lifecycle_status='PROVISIONAL'").fetchone()[0],
            "g31t_contract": con.execute("SELECT count(*) FROM algorithm_contracts WHERE component_key='g31_technical_multiplicity_integrity_v0_1_0' AND implementation_state='PASS_WITH_SCOPE_AMENDMENT' AND status='ACTIVE'").fetchone()[0],
            "g31b_question": con.execute("SELECT count(*) FROM open_questions WHERE question_key='G31_BIOLOGICAL_CANDIDATE_ENTRY_INTERPRETATION' AND blocking=0 AND status='OPEN'").fetchone()[0],
            "restart_question": con.execute("SELECT count(*) FROM open_questions WHERE question_key='FULLSCALE_RESTART_RESUME' AND blocking=1 AND status='OPEN'").fetchone()[0],
            "determinism_question": con.execute("SELECT count(*) FROM open_questions WHERE question_key='RELEASE_SCALE_DETERMINISM' AND blocking=1 AND status='OPEN'").fetchone()[0],
            "pipeline_stage15_active": con.execute("SELECT count(*) FROM current_pipeline WHERE stage_key LIKE '15%'").fetchone()[0],
        }
    finally:
        con.close()
    required_one = [
        "run_500k", "mapping_run", "full_run", "full_stage", "g31_stage",
        "full_impl", "g31t_contract", "g31b_question", "restart_question",
        "determinism_question",
    ]
    if any(checks[key] != 1 for key in required_one) or checks["pipeline_stage15_active"] != 0:
        raise UpdateError(f"SSOT registration postcheck failed: {checks}")

    gates = parse_release_gates(GATES_V030.read_text(encoding="utf-8"))
    return {
        "active_pipeline_before_sha256": before_pipeline_sha,
        "active_pipeline_after_sha256": after_pipeline_sha,
        "active_pipeline_byte_identical": True,
        "core_schema_byte_identical": True,
        "checks": checks,
        "release_gate_rows": len(gates),
    }


def run_execute(confirm: str) -> int:
    if confirm != CONFIRM_TOKEN:
        raise UpdateError(f"--confirm-update must exactly equal {CONFIRM_TOKEN}")
    lock_handle = LOCK_PATH.open("w")
    fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    preflight_qc = verify_preflight_binding()
    baseline = verify_baseline()
    verify_evidence_semantics()

    timestamp = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = SSOT_BACKUPS / f"stage15d_fullscale_handover_v0.1.0_{timestamp}"
    preexisting = backup_state(backup)
    mutation_started = False
    try:
        updater_sha = sha256_file(Path(__file__).resolve())
        gates_payload = RELEASE_GATES_V030_TEXT.encode("utf-8")
        gates_sha = sha256_bytes(gates_payload)
        insertion = build_source_insertion(
            updater_sha256=updater_sha,
            handover_sha256=EXPECTED_HANDOVER_SHA256,
            gates_sha256=gates_sha,
        )

        mutation_started = True
        atomic_write(GATES_V030, gates_payload)
        atomic_write(HANDOVER_INSTALL, HANDOVER_DOWNLOAD.read_bytes())
        atomic_write(SCRIPT_INSTALL, Path(__file__).resolve().read_bytes(), 0o755)
        atomic_write(DOC_INSTALL, REGISTRATION_DOC.encode("utf-8"))

        source = SSOT_CLI.read_text(encoding="utf-8")
        if PATCH_MARKER in source:
            raise UpdateError("SSOT patch marker appeared between preflight and execute")
        if source.count(PATCH_ANCHOR) != 1:
            raise UpdateError("SSOT patch anchor changed between preflight and execute")
        patched = source.replace(PATCH_ANCHOR, "\n\n" + insertion + PATCH_ANCHOR, 1)
        compile(patched, str(SSOT_CLI), "exec")
        atomic_write(SSOT_CLI, patched.encode("utf-8"), 0o755)

        UPDATE_QC_ROOT.mkdir(parents=True, exist_ok=False)
        UPDATE_META_ROOT.mkdir(parents=True, exist_ok=False)
        result = postcheck(
            before_pipeline_sha=baseline["current_pipeline_sha256"],
            before_schema_sha=baseline["core_schema_sha256"],
        )

        qc_rows = [
            ("update_version", VERSION),
            ("full_run_id", FULL_RUN),
            ("preflight_qc", PREFLIGHT_QC_DOWNLOAD),
            ("preflight_updater_sha256", preflight_qc["updater_sha256"]),
            ("ssot_cli_sha256_before", baseline["ssot_cli_sha256"]),
            ("ssot_cli_sha256_after", sha256_file(SSOT_CLI)),
            ("ssot_db_sha256_before", baseline["ssot_db_sha256"]),
            ("ssot_db_sha256_after", sha256_file(SSOT_DB)),
            ("release_gates_v030_sha256", sha256_file(GATES_V030)),
            ("active_pipeline_before_sha256", result["active_pipeline_before_sha256"]),
            ("active_pipeline_after_sha256", result["active_pipeline_after_sha256"]),
            ("active_pipeline_byte_identical", str(result["active_pipeline_byte_identical"]).lower()),
            ("core_schema_byte_identical", str(result["core_schema_byte_identical"]).lower()),
            ("full_empirical_registered", "true"),
            ("runtime_status", "PASS_WITH_DOCUMENTED_TOLERANCE"),
            ("g31_machine_fail_preserved", "true"),
            ("g31_t_status", "PASS_WITH_SCOPE_AMENDMENT"),
            ("g31_b_status", "OPEN_DEFERRED_TO_BIOLOGY_LAYER"),
            ("release_scale_determinism", "OPEN"),
            ("fullscale_restart_resume", "OPEN"),
            ("active_pipeline_modified", "false"),
            ("core_schema_modified", "false"),
            ("audit_status", "PASS"),
            ("next_gate", "DESIGN_RELEASE_SCALE_DETERMINISM_AND_FULLSCALE_RESTART_RESUME"),
        ]
        qc_path = UPDATE_QC_ROOT / "stage15d_fullscale_handover_ssot_update.qc.tsv"
        write_metrics(qc_path, qc_rows)
        (UPDATE_META_ROOT / "registration_contract.json").write_text(
            json.dumps({
                "version": VERSION,
                "confirm_token": CONFIRM_TOKEN,
                "backup": str(backup),
                "preflight": dict(preflight_qc),
                "postcheck": result,
            }, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        parent = Path(tempfile.mkdtemp(prefix="rnatr_stage15d_ssot_output_"))
        root = parent / "rnatr_stage15d_ssot_update_fullscale_handover_v0.1.0"
        for directory in ("qc", "metadata", "docs", "validation", "script", "ssot"):
            (root / directory).mkdir(parents=True, exist_ok=True)
        shutil.copytree(UPDATE_QC_ROOT, root / "qc", dirs_exist_ok=True)
        shutil.copytree(UPDATE_META_ROOT, root / "metadata", dirs_exist_ok=True)
        for path in (HANDOVER_INSTALL, DOC_INSTALL):
            shutil.copy2(path, root / "docs" / path.name)
        shutil.copy2(GATES_V030, root / "validation" / GATES_V030.name)
        shutil.copy2(SCRIPT_INSTALL, root / "script" / SCRIPT_INSTALL.name)
        for path in (SSOT_CLI, SSOT_DB, SSOT_SUMMARY):
            if path.exists():
                shutil.copy2(path, root / "ssot" / path.name)
        for name in ("current_pipeline.tsv", "current_decisions.tsv", "current_interpretations.tsv", "current_algorithm_contract.tsv", "current_known_limitations.tsv", "current_open_questions.tsv", "current_results.tsv", "current_runs.tsv"):
            path = SSOT_EXPORTS / name
            if path.exists():
                shutil.copy2(path, root / "ssot" / name)
        bundle_sha = make_bundle(root, SUCCESS_BUNDLE)
        shutil.rmtree(parent, ignore_errors=True)

        print("===== RNA-TR-Scout Stage 15D SSOT update final =====")
        for key, value in qc_rows:
            print(f"{key}\t{value}")
        print(f"SSOT_CLI\t{SSOT_CLI}")
        print(f"SSOT_DB\t{SSOT_DB}")
        print(f"BACKUP\t{backup}")
        print(f"OUTPUT_BUNDLE\t{SUCCESS_BUNDLE}")
        print(f"OUTPUT_BUNDLE_SHA256\t{bundle_sha}")
        return 0
    except Exception:
        if mutation_started:
            restore_state(backup, preexisting)
        raise
    finally:
        try:
            fcntl.flock(lock_handle, fcntl.LOCK_UN)
            lock_handle.close()
        except Exception:
            pass


def self_test() -> int:
    compile(Path(__file__).read_text(encoding="utf-8"), str(Path(__file__)), "exec")
    parse_release_gates(RELEASE_GATES_V030_TEXT)
    insertion = build_source_insertion(
        updater_sha256="a" * 64,
        handover_sha256="b" * 64,
        gates_sha256="c" * 64,
        evidence_guards={},
        include_source_guards=False,
    )
    compile("def _synthetic_populate(conn, project_root):\n" + insertion, "<stage15d-insertion>", "exec")

    con = sqlite3.connect(":memory:")
    con.executescript("""
    CREATE TABLE source_documents(source_id INTEGER PRIMARY KEY AUTOINCREMENT,source_type TEXT NOT NULL,path TEXT NOT NULL UNIQUE,sha256 TEXT,bytes INTEGER,mtime_utc TEXT,content_status TEXT NOT NULL,ingested_at TEXT NOT NULL);
    CREATE TABLE datasets(dataset_id TEXT PRIMARY KEY);
    CREATE TABLE runs(run_id TEXT PRIMARY KEY,dataset_id TEXT,parent_run_id TEXT,run_role TEXT,pipeline_version TEXT,status TEXT NOT NULL,started_at TEXT,ended_at TEXT,root_path TEXT,notes TEXT);
    CREATE TABLE stage_definitions(stage_key TEXT PRIMARY KEY,stage_order REAL,name TEXT NOT NULL,purpose TEXT,category TEXT,implementation_status TEXT,notes TEXT);
    CREATE TABLE implementations(implementation_id TEXT PRIMARY KEY,stage_key TEXT NOT NULL,version TEXT,script_path TEXT,script_sha256 TEXT,validator_path TEXT,validator_sha256 TEXT,package_version TEXT,parameters_json TEXT,lifecycle_status TEXT NOT NULL,supersedes_implementation_id TEXT,rationale TEXT,evidence_path TEXT,effective_at TEXT NOT NULL);
    CREATE TABLE run_stages(run_stage_id INTEGER PRIMARY KEY AUTOINCREMENT,run_id TEXT NOT NULL,stage_key TEXT NOT NULL,implementation_id TEXT,attempt_tag TEXT NOT NULL,status TEXT NOT NULL,command_text TEXT,qc_path TEXT,qc_status TEXT,started_at TEXT,ended_at TEXT,notes TEXT,UNIQUE(run_id,stage_key,attempt_tag));
    CREATE TABLE metrics(metric_id INTEGER PRIMARY KEY AUTOINCREMENT,run_id TEXT,stage_key TEXT,metric_name TEXT NOT NULL,value_text TEXT NOT NULL,value_num REAL,unit TEXT,denominator_num REAL,source_path TEXT NOT NULL,metric_status TEXT NOT NULL,recorded_at TEXT NOT NULL,UNIQUE(run_id,stage_key,metric_name,source_path));
    CREATE TABLE decisions(decision_id TEXT PRIMARY KEY,decision_key TEXT NOT NULL,category TEXT,title TEXT NOT NULL,statement TEXT NOT NULL,status TEXT NOT NULL,confidence TEXT,effective_at TEXT NOT NULL,supersedes_decision_id TEXT,rationale TEXT,evidence_path TEXT);
    CREATE UNIQUE INDEX one_active_decision_per_key ON decisions(decision_key) WHERE status='ACTIVE';
    CREATE TABLE interpretations(interpretation_id TEXT PRIMARY KEY,interpretation_key TEXT NOT NULL,fact_statement TEXT NOT NULL,interpretation TEXT NOT NULL,do_not_interpret_as TEXT,status TEXT NOT NULL,confidence TEXT,effective_at TEXT NOT NULL,supersedes_interpretation_id TEXT,evidence_path TEXT,evidence_metrics_json TEXT);
    CREATE UNIQUE INDEX one_active_interpretation_per_key ON interpretations(interpretation_key) WHERE status='ACTIVE';
    CREATE TABLE algorithm_contracts(contract_id TEXT PRIMARY KEY,component_key TEXT NOT NULL,component_name TEXT NOT NULL,implementation_state TEXT NOT NULL,contract_statement TEXT NOT NULL,active_implementation_id TEXT,evidence_path TEXT,effective_at TEXT NOT NULL,status TEXT NOT NULL);
    CREATE UNIQUE INDEX one_active_contract_per_component ON algorithm_contracts(component_key) WHERE status='ACTIVE';
    CREATE TABLE limitations(limitation_key TEXT PRIMARY KEY,statement TEXT NOT NULL,severity TEXT,status TEXT NOT NULL,mitigation TEXT,evidence_path TEXT,effective_at TEXT NOT NULL);
    CREATE TABLE open_questions(question_key TEXT PRIMARY KEY,question TEXT NOT NULL,priority TEXT,status TEXT NOT NULL,blocking INTEGER NOT NULL,next_action TEXT,evidence_path TEXT,effective_at TEXT NOT NULL);
    CREATE TABLE failures(failure_id TEXT PRIMARY KEY,run_id TEXT,stage_key TEXT,attempt_version TEXT,status TEXT NOT NULL,summary TEXT NOT NULL,root_cause TEXT,resolution TEXT,source_path TEXT,superseded_by TEXT,recorded_at TEXT NOT NULL);
    INSERT INTO datasets(dataset_id) VALUES('dataset_test');
    INSERT INTO runs(run_id,dataset_id,status) VALUES('ENCSR307SHM_pilot100k_mm2splice_v1','dataset_test','PASS');
    """)
    namespace: dict[str, Any] = {"hashlib": hashlib, "json": json, "Path": Path, "textwrap": textwrap, "csv": csv}
    exec("def _synthetic_populate(conn, project_root):\n" + insertion, namespace)
    namespace["_synthetic_populate"](con, Path("/synthetic"))
    checks = {
        "full_run": con.execute("SELECT count(*) FROM runs WHERE run_id=?", (FULL_RUN,)).fetchone()[0],
        "full_stage": con.execute("SELECT count(*) FROM stage_definitions WHERE stage_key='15C_FULL_EMPIRICAL_BAM_TO_FINAL'").fetchone()[0],
        "g31t": con.execute("SELECT count(*) FROM algorithm_contracts WHERE component_key='g31_technical_multiplicity_integrity_v0_1_0'").fetchone()[0],
        "questions": con.execute("SELECT count(*) FROM open_questions").fetchone()[0],
    }
    con.close()
    if checks["full_run"] != 1 or checks["full_stage"] != 1 or checks["g31t"] != 1 or checks["questions"] < 6:
        raise UpdateError(f"synthetic insertion self-test failed: {checks}")
    print("SELF_TEST_PASS")
    return 0


def failure_bundle(exc: BaseException) -> None:
    try:
        parent = Path(tempfile.mkdtemp(prefix="rnatr_stage15d_ssot_failure_"))
        root = parent / "rnatr_stage15d_ssot_update_fullscale_handover_v0.1.0_failure"
        root.mkdir()
        (root / "failure.txt").write_text(
            f"version\t{VERSION}\n"
            f"exception_type\t{type(exc).__name__}\n"
            f"exception\t{exc}\n\n{traceback.format_exc()}",
            encoding="utf-8",
        )
        if Path(__file__).is_file():
            shutil.copy2(Path(__file__).resolve(), root / Path(__file__).name)
        digest = make_bundle(root, FAILURE_BUNDLE)
        shutil.rmtree(parent, ignore_errors=True)
        print(f"FAILURE_BUNDLE\t{FAILURE_BUNDLE}", file=sys.stderr)
        print(f"FAILURE_BUNDLE_SHA256\t{digest}", file=sys.stderr)
    except Exception as bundle_exc:
        print(f"WARNING: could not create failure bundle: {bundle_exc}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="Register RNA-TR-Scout Stage15B/15C/full empirical/G31 scope state in SSOT with preflight and rollback")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--self-test", action="store_true")
    modes.add_argument("--preflight", action="store_true")
    modes.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-update", default="")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if args.preflight:
        return run_preflight()
    return run_execute(args.confirm_update)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        if "--execute" in sys.argv:
            failure_bundle(exc)
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise