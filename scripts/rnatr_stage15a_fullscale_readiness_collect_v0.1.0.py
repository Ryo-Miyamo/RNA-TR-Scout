#!/usr/bin/env python3
from __future__ import annotations

import ast
import base64
import csv
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import traceback
from pathlib import Path
from typing import Any

VERSION = "rnatr_stage15a_fullscale_readiness_collection_v0.1.0"
PROJECT_ROOT = Path("/mnt/intelssd/rnatr_project")
RUN_ID = "ENCSR307SHM_stage15a500k_seed20260809_mm2splice_v1"

QC_ROOT = (
    PROJECT_ROOT / "qc/15_stage15a_bam_to_final" / RUN_ID
    / "v0.1.1_500k_scaling"
)
RESULT_ROOT = (
    PROJECT_ROOT / "results/15_stage15a_bam_to_final" / RUN_ID
    / "v0.1.1_500k_scaling"
)
OUT_ROOT = (
    PROJECT_ROOT / "qc/15_stage15a_fullscale_readiness" / RUN_ID / "v0.1.0"
)

DOWNLOADS = Path.home() / "Downloads"
SUCCESS_BUNDLE = DOWNLOADS / "rnatr_stage15a_fullscale_readiness_v0.1.0.tar.gz"
FAILURE_BUNDLE = DOWNLOADS / "rnatr_stage15a_fullscale_readiness_v0.1.0_failure.tar.gz"

SSOT_CLI = PROJECT_ROOT / "metadata/ssot/rnatr_ssot.py"
SSOT_DB = PROJECT_ROOT / "metadata/ssot/rnatr_ssot.sqlite"
SSOT_CLI_SHA = "8aeff1eda5c301e74a9054e786ed19bf5b699ff6aa111221aa2e60f6d733b37b"
SSOT_DB_SHA = "7edb4eb63e8f04b6fe8d8e67a82a6d9d70ba55c1946c62827d7b133e0d5a4274"

FINAL_QC = QC_ROOT / "stage15a_scaling_500k.qc.tsv"
FINAL_QC_SHA = "ef27be62e633e941b21978d8354a928a7ecea33600465fe6620e82640b329e82"

SCHEMA_DIR = PROJECT_ROOT / "config/evidence_schema/v0.4.2"
V041_PACKAGE_VALIDATOR = SCHEMA_DIR / "rnatr_v041_validate_package.py"
V042_PACKAGE_WRAPPER = SCHEMA_DIR / "rnatr_v042_validate_package.py"
V042_FLANK_VALIDATOR = SCHEMA_DIR / "rnatr_v042_validate_flank_uniqueness.py"
V042_TSV_VALIDATOR = SCHEMA_DIR / "rnatr_v042_validate_tsv.py"
PARALLEL_VALIDATOR = PROJECT_ROOT / "scripts/rnatr_stage15a_validate_package_parallel_v0.2.2.1.py"

EXPECTED_COMPONENT_SHA = {
    V041_PACKAGE_VALIDATOR: "e978b109d094f665ec62387ffda35c81d0aa9e8156972069f18a1b0b6c49bba5",
    V042_PACKAGE_WRAPPER: "45c3995550f57a65b3fec4aab7471d57b7000e19471d4c5cf7f3ae055426984e",
    V042_FLANK_VALIDATOR: "039024835de2bc1f096e562eed69788ecad9e481575b1b8cd58241edf2e87ab5",
    PARALLEL_VALIDATOR: "b635ed213b65cee005914f0fded9337871903a7e5682f9a897dff9cbc9bb0b09",
}

SELECTED_SOURCE_PATHS = [
    PROJECT_ROOT / "scripts/rnatr_stage15a_run_performance_100k_v0.2.2.1.py",
    PROJECT_ROOT / "scripts/rnatr_stage15a_run_scaling_500k_v0.1.1.py",
    PROJECT_ROOT / "scripts/rnatr_stage15a_compare_scaling_500k_v0.1.4.py",
    PROJECT_ROOT / "scripts/rnatr_stage15a_fast_motif_jobs_scaling_v0.2.2.2.py",
    PROJECT_ROOT / "scripts/rnatr_stage15a_native_v041_runid_adapter_v0.2.1.py",
    PROJECT_ROOT / "scripts/rnatr_materialize_native_v041_to_evidence_v042_runid_adapter_v0.2.1.py",
    PROJECT_ROOT / "src/rnatr_scout/materialization/rnatr_materialize_native_v041_to_evidence_v042_v0.1.2.py",
]

SELECTED_QC_PATHS = [
    FINAL_QC,
    QC_ROOT / "stage15a_scaling_500k_stage_model.tsv",
    QC_ROOT / "stage15a_scaling_500k_package_reproducibility.tsv",
    QC_ROOT / "stage15a_scaling_500k_caller_reproducibility.tsv",
    QC_ROOT / "stage15a_scaling_500k_checkpoint_logical_reproducibility.tsv",
    QC_ROOT / "stage15a_scaling_500k_checkpoint_reproducibility.qc.tsv",
    QC_ROOT / "stage15a_scaling_500k_nested_250k_caller_parity.tsv",
    QC_ROOT / "stage15a_scaling_500k_nested_250k_package_semantic_parity.tsv",
    QC_ROOT / "replicate_A/stage15a_scaling_500k_replicate.qc.tsv",
    QC_ROOT / "replicate_B/stage15a_scaling_500k_replicate.qc.tsv",
    QC_ROOT / "replicate_A/stage15a_performance_validators.tsv",
    QC_ROOT / "replicate_B/stage15a_performance_validators.tsv",
    QC_ROOT / "replicate_A/15AS4_native_caller.per_shard.tsv",
    QC_ROOT / "replicate_A/15AS5_materializer.per_shard.tsv",
    QC_ROOT / "replicate_A/stage15a_scaling_500k_temp_bytes.tsv",
]

CONTRACT_B64 = "IyBSTkEtVFItU2NvdXQgQ29yZSBUZWNobmljYWwgQ29tcGxldGlvbiBhbmQgRnJlZXplIENvbnRyYWN0IHYwLjEuMQoK5L2c5oiQ5pelOiAyMDI2LTA4LTA5ICAK54q25oWLOiBgREVTSUdORURfTk9UX1lFVF9TQVRJU0ZJRURgICAKUmVsZWFzZSBwcm9maWxlOiBgQ09SRV9URUNITklDQUxfQ09NUExFVElPTl9WMWAgIApQbGFubmVkIGZpcnN0IGNvcmUgcmVsZWFzZSB0YWc6IGB2MC41LjBg77yIcmVsZWFzZS1jYW5kaWRhdGXmmYLjgavmnIDntYLnorroqo3vvIkKCiMjIDEuIOebrueahOOBqHBoYXNl5aKD55WMCgrlrabnlJ/jga7kv67lo6voq5bmlofjgpLlkKvjgoDnoJTnqbbmiJDmnpzjgYvjgonjgIHlho3nj77lj6/og73jgarlm7rlrppzb2Z0d2FyZSB2ZXJzaW9u44KS5byV55So44Gn44GN44KL44KI44GG44CBUk5BLVRSLVNjb3V044GuY29yZSB0ZWNobmljYWwgaW1wbGVtZW50YXRpb27jgavmmI7norrjgarlrozkuobngrnjgpLnva7jgY/jgIIKCkNvcmUgVGVjaG5pY2FsIENvbXBsZXRpb27jga9iaW9sb2d5LXJlYWR5IGNvbXBsZXRpb27jgajjga/liIbpm6LjgZnjgovjgILku6XkuIvjga/lronlrppjb3Jl44Gu5LiK44GrdmVyc2lvbmVkIHNpZGVjYXIgLyBpbnRlcnByZXRhdGlvbiBsYXllcuOBqOOBl+OBpuW+jOe2muWun+ijheOBmeOCi+OAggoKYGBgdGV4dAp0cmFuc2NyaXB0IC8gaXNvZm9ybSBzdGF0ZQpoYXBsb3R5cGUgc3RhdGUKb2JzZXJ2YWJpbGl0eSBzaWRlY2FyCm1vbGVjdWxlIGluZGVwZW5kZW5jZSAvIGR1cGxpY2F0ZSBtb2RlbApzYW1wbGXDl2xvY3VzIGJpb2xvZ3kgc3VtbWFyeQpwdXJwb3NlLXNwZWNpZmljIGNhbmRpZGF0ZSByYW5raW5nCnJlc2VhcmNoZXItZmFjaW5nIGNhbmRpZGF0ZSBkb3NzaWVyCmBgYAoKIyMgMi4gRnJlZXpl5a++6LGh44Go44Gq44KLY29yZQoKYGBgdGV4dAptYXBwaW5nLWNvbXBsZXRlIHNvcnRlZCBCQU0gKyBCQUkKKyBhc3NvY2lhdGVkIHJhdy1yZWFkIHNlcXVlbmNlIHN0b3JlCisgaW1tdXRhYmxlIHRhcmdldC9jYXRhbG9nL3JlZmVyZW5jZSBjb250cmFjdAogICAg4oaTCnRhcmdldCBhc3NpZ25tZW50CiAgICDihpMKcmF3LXJlYWQgY29vcmRpbmF0ZSBwcm9qZWN0aW9uCiAgICDihpMKbW90aWYtam9iIGZvcm1hdGlvbgogICAg4oaTCmRldGVybWluaXN0aWMgbmF0aXZlIGdlbmVyYWwgY2FsbGVyIHYwLjQuMQogICAg4oaTCmV2aWRlbmNlIHNjaGVtYSB2MC40LjIgbWF0ZXJpYWxpemF0aW9uCiAgICDihpMKNS10YWJsZSB2YWxpZGF0aW9uIC8gcGFja2FnZSB2YWxpZGF0aW9uCiAgICDihpMKYXRvbWljIGZpbmFsIHBhY2thZ2UKYGBgCgpDb3JlIHNvdXJjZSBvZiB0cnV0aDoKCmBgYHRleHQKZ2VuZXJhbF9yZXBlYXRfY2FsbHMKcmVhZF9ldmlkZW5jZQpyZXBlYXRfZXZlbnRzCnJlcGVhdF9zZWdtZW50cwpyZXBlYXRfaW50ZXJydXB0aW9ucwpgYGAKCkN1cnJlbnQgZnJvemVuIHNlbWFudGljIGNvbXBvbmVudHM6CgpgYGB0ZXh0CnNjaWVudGlmaWMgY2FsbGVyICAgICAgIGRldGVybWluaXN0aWMgbmF0aXZlIGdlbmVyYWwgY2FsbGVyIHYwLjQuMQptYXRlcmlhbGl6YXRpb24gYmFzZSAgICB2MC4xLjIgc2VtYW50aWNzCmNvcmUgZXZpZGVuY2Ugc2NoZW1hICAgIHYwLjQuMgpmYWlsdXJlL1FDL21hdGVyaWFsaXphdGlvbiBjb250cmFjdCAgZnJvemVuIFN0YWdlMTRMMiBjb250cmFjdApgYGAKCiMjIDMuIENvcmUgRnJlZXpl44Gu5b+F6aCIZ2F0ZQoKIyMjIENUQzAxIOKAlCBDb3JlIGNvcnJlY3RuZXNzIGFuZCBkZXRlcm1pbmlzdGljIHNjYWxpbmcKCi0gMTAwayBCQU3ihpJmaW5hbCBleGFjdCByZWZlcmVuY2UgcGFyaXR5OiBQQVNTCi0gMjUwayBkdWFsLXJlcGxpY2F0ZSBwYWNrYWdlL2NhbGxlci9jaGVja3BvaW50IGxvZ2ljYWwgZGV0ZXJtaW5pc206IFBBU1MKLSBkZXRlcm1pbmlzdGljIDUwMGsgZHVhbC1yZXBsaWNhdGUgc2NhbGluZzogUEFTUwotIG5lc3RlZCBzbWFsbGVyLXN1YnNldCBzY2llbnRpZmljIHBhcml0eTogUEFTUwotIGZvcm1hbCBydW4tSUQgY29udHJhY3Q6IFBBU1MKCiMjIyBDVEMwMiDigJQgRW1waXJpY2FsIGZ1bGwtc2NhbGUgcnVudGltZQoKNS4zMU3ntJptYXBwaW5nLWNvbXBsZXRlIEJBTeWFpeWKm+OBq+OBpOOBhOOBpuOAgW1hcHBpbmfmmYLplpPjgpLlkKvjgoHjgZrjgIFhc3NvY2lhdGVkIHJhdy1yZWFkIHNlcXVlbmNlIHN0b3Jl44GL44KJ44GuY2FuZGlkYXRlIGV4dHJhY3Rpb27jgpLlkKvjgoBjb3JlIEJBTS10by1maW5hbCB3YWxsIHRpbWXjgpLlrp/muKzjgZnjgovjgIIKCmBgYHRleHQKZW5naW5lZXJpbmcgYmVuY2htYXJrICAgICAgICAgIDw9IDYwLjAgbWluCnRoZXNpcy9jb3JlLXJlbGVhc2UgdG9sZXJhbmNlICA+NjAuMCBhbmQgPD02Mi4wIG1pbgpmb3JtYWwgdGFyZ2V0ICAgICAgICAgICAgICAgICAgPD0gMzAuMCBtaW4KYGBgCgrliKTlrpo6CgpgYGB0ZXh0Cjw9NjAuMCBtaW4KICAgIFBBU1NfU1RSSUNUCgo+NjAuMCBhbmQgPD02Mi4wIG1pbgogICAgUEFTU19XSVRIX0RPQ1VNRU5URURfVE9MRVJBTkNFCiAgICDjgZ/jgaDjgZdDVEMwMS8wM+KAkzA444GMUEFTU+OBl+OAgXN3YXAvT09N44CBdmFsaWRhdG9y55yB55Wl44CBCiAgICDkuI3lrozlhahwdWJsaWNhdGlvbuOAgeWGjeePvuaAp+S9juS4i+OBjOOBquOBhOOBk+OBqAoKPjYyLjAgbWluCiAgICBGQUlMX0ZPUl9GSVJTVF9DT1JFX0ZSRUVaRQpgYGAKCjYw5YiG44Gv5q2j5byP44GqZW5naW5lZXJpbmcgYmVuY2htYXJr44Go44GX44Gm57at5oyB44GZ44KL44CCMeKAkzLliIbnqIvluqbjga7otoXpgY7jgaDjgZHjgpLnkIbnlLHjgavjgIHkv67lo6voq5bmlofnlKjjga7mnIDliJ3jga5jb3JlIHJlbGVhc2XjgpLkuI3lv4XopoHjgavpgYXjgonjgZvjgarjgYTjgILlrp/muKzlgKTjgah0b2xlcmFuY2XliKnnlKjjga9TU09U44CBcmVsZWFzZSBub3Rlc+OAgeS/ruWjq+irluaWh+OBuOaYjuiomOOBmeOCi+OAggoKMzDliIbjga/mraPlvI90YXJnZXTjgaDjgYzjgIHmnIDliJ3jga5jb3JlIGZyZWV6ZeOBp+OBr25vbi1ibG9ja2luZ+OBp+OBguOCi+OAggoKIyMjIENUQzAzIOKAlCBSZWxlYXNlLXNjYWxlIGRldGVybWluaXNtCgrmrKHjga7jgYTjgZrjgozjgYvjgIHjgb7jgZ/jga/lkIznrYnku6XkuIrjgpLmuoDjgZ/jgZnjgIIKCjEuIGZ1bGwtc2NhbGUgQkFNLXRvLWZpbmFsIGluZGVwZW5kZW50IHJlcGxpY2F0ZeOBrmZpbmFsIHBhY2thZ2UgZXhhY3QgcGFyaXR5CjIuIGZ1bGwtc2NhbGUgZnJvemVuIHVwc3RyZWFtIGNoZWNrcG9pbnTjgYvjgonjgIHnlbDjgarjgotoYXNoIHNlZWTjgadjYWxsZXIvbWF0ZXJpYWxpemVyL2ZpbmFsaXphdGlvbuOCkuWGjeWun+ihjOOBl+OAgWNhbGxlciBsb2dpY2FsIHBhcml0eeOBqDUtdGFibGUgZXhhY3QgbG9naWNhbCBwYXJpdHnjgpLnorroqo0KCjUwMGvjgaDjgZHjga5kZXRlcm1pbmlzbeOCkmZ1bGwtc2NhbGUgZGV0ZXJtaW5pc23jgajjgZfjgabku6PnlKjjgZfjgarjgYTjgIIKCiMjIyBDVEMwNCDigJQgRnVsbC1zY2FsZSByZXN0YXJ0IC8gcmVzdW1lCgo1LjMxTee0mnJ1buOBp+aEj+Wbs+eahOWBnOatouOCkuWFpeOCjOOAgeS7peS4i+OCkuaknOiovOOBmeOCi+OAggoKYGBgdGV4dAppbmNvbXBsZXRlIHBhY2thZ2UgaXMgbmV2ZXIgcHVibGlzaGVkCmNoZWNrcG9pbnQgbWFuaWZlc3QgaW50ZWdyaXR5IFBBU1MKY29ycnVwdGVkIGNoZWNrcG9pbnQgaXMgcmVqZWN0ZWQKY29tcGxldGVkIHdvcmsgaXMgcmV1c2VkCm1pc3Npbmcgd29yayBvbmx5IGlzIHJlc3VtZWQKcmVzdW1lZCBmaW5hbCBwYWNrYWdlIGVxdWFscyBjbGVhbiBmaW5hbCBwYWNrYWdlCnNlY29uZCByZXN1bWUgaXMgYSBuby1vcAphdG9taWMgcHVibGljYXRpb24gUEFTUwpgYGAKCiMjIyBDVEMwNSDigJQgVmFsaWRhdG9ycywgYm91bmRlZCBtZW1vcnksIGFuZCBhcnRpZmFjdCBhdWRpdAoKLSBmaXZlIGdlbmVyaWMgVFNWIHZhbGlkYXRvcnM6IFBBU1MKLSBjcm9zcy10YWJsZSBwYWNrYWdlIHZhbGlkYXRvcjogUEFTUwotIGZsYW5rIHVuaXF1ZW5lc3MgY29udHJhY3QgdmFsaWRhdG9yOiBQQVNTCi0gbmVnYXRpdmUgZml4dHVyZSBmYWlsdXJlIHBhcml0eTogUEFTUwotIG91dHB1dCBtYW5pZmVzdCByb3dzL2J5dGVzL1NIQTogUEFTUwotIHBlYWsgbWVtb3J5IC8gdGVtcG9yYXJ5IGJ5dGVzIC8gZmluYWwgb3V0cHV0IGJ5dGVzIHJlY29yZGVkCi0gZnVsbC1zY2FsZSB2YWxpZGF0aW9uIG11c3QgY29tcGxldGUgd2l0aG91dCBzd2FwL09PTQotIG1lbW9yeS1ib3VuZGVkIHZhbGlkYXRvciBtdXN0IGJlIHNob3duIGVxdWl2YWxlbnQgdG8gdGhlIGZyb3plbiB2YWxpZGF0b3Igb24gMTAwayBhbmQgNTAwayBwb3NpdGl2ZSBmaXh0dXJlcyBwbHVzIHZlcnNpb25lZCBuZWdhdGl2ZSBmaXh0dXJlcwoKQSB2YWxpZGF0b3IgdGhhdCBpcyBzZW1hbnRpY2FsbHkgY29ycmVjdCBhdCA1MDBrIGJ1dCBoYXMgYW4gZXh0cmFwb2xhdGVkIG1lbW9yeSByZXF1aXJlbWVudCBleGNlZWRpbmcgdGhlIGhvc3QgUkFNIGlzIG5vdCBmdWxsLXNjYWxlIHJlYWR5LgoKIyMjIENUQzA2IOKAlCBQUkVfUkVMRUFTRV9DQU5ESURBVEUgQXJjaGl0ZWN0dXJlIGNvbnNpc3RlbmN5IGF1ZGl0CgpgYGB0ZXh0CmJsb2NraW5nIGNvbmZsaWN0cyA9IDAKcmVsZWFzZS1ibG9ja2luZyBSRVZJRVcgaXRlbXMgPSAwCnVuaW1wbGVtZW50ZWQgaXRlbXMgYXJlIG5vdCByZXByZXNlbnRlZCBhcyBpbXBsZW1lbnRlZApmcm96ZW4gY29udHJhY3RzIGhhdmUgbm8gdW5pbnRlbmRlZCBkcmlmdApvYnNvbGV0ZS9yZWZlcmVuY2UvcHJvdmlzaW9uYWwvYWN0aXZlIGxpZmVjeWNsZSBpcyBleHBsaWNpdApwbGFubmVkIGJpb2xvZ3kgd29yayByZW1haW5zIHByZXNlcnZlZApgYGAKCiMjIyBDVEMwNyDigJQgUHJvbW90aW9uIGFuZCBjbGVhbi1pbnN0YWxsIHJlcHJvZHVjaWJpbGl0eQoKLSByZWxlYXNlIGNhbmRpZGF0ZeOCkmlzb2xhdGVkIGNsZWFuIGVudmlyb25tZW5044GL44KJ5a6f6KGM5Y+v6IO9Ci0gYWN0aXZlIHByb2R1Y3Rpb24gcGF0aOOBr+aYjuekuueahHByb21vdGlvbiBnYXRl44KS6YCa6YGOCi0gaGlzdG9yaWNhbCByZWZlcmVuY2UvYXVkaXQgbGFuZeOBr+WJiumZpOOBm+OBmuS/neaMgQotIHJlbGVhc2UgYXJ0aWZhY3TjgYvjgonlkIzkuIB2ZXJzaW9uL2NvbW1pdC9lbnZpcm9ubWVudOOCkuWGjeani+evieWPr+iDvQoKIyMjIENUQzA4IOKAlCBUaGVzaXMtY2l0YWJsZSBpbW11dGFibGUgcmVsZWFzZQoKR2l0SHViIHJlbGVhc2Xjgavjga/mnIDkvY7pmZDku6XkuIvjgpLlkKvjgoDjgIIKCmBgYHRleHQKaW1tdXRhYmxlIHNlbWFudGljLXZlcnNpb24gdGFnCmZ1bGwgNDAtY2hhcmFjdGVyIEdpdCBjb21taXQgU0hBCnNvdXJjZSBhcmNoaXZlIGNoZWNrc3VtcwpyZWxlYXNlIG1hbmlmZXN0IHdpdGggY29tcG9uZW50L2NvbmZpZy9zY2hlbWEgU0hBLTI1NgplbnZpcm9ubWVudCBsb2NrIC8gZGVwZW5kZW5jeSB2ZXJzaW9ucwpiZW5jaG1hcmsgaW5wdXQgYW5kIHJlZmVyZW5jZSBjaGVja3N1bXMKQ0lUQVRJT04uY2ZmCkNIQU5HRUxPRyAvIHJlbGVhc2Ugbm90ZXMKTElDRU5TRQprbm93biBsaW1pdGF0aW9ucyBhbmQgb3BlbiAzMC1taW51dGUgdGFyZ2V0CmBgYAoKUGxhbm5lZCBmbG93OgoKYGBgdGV4dAp2MC41LjAtcmMxIOKGkiBwcmUtUkMgYXVkaXQgYW5kIGNsZWFuLWluc3RhbGwgdmFsaWRhdGlvbiDihpIgdjAuNS4wCmBgYAoKIyMgNC4gRnJlZXpl5b6M44Gu5aSJ5pu06KaP5YmHCgpDb3JlIEZyZWV6ZeW+jOOAgeasoeOCkueEoeaWreOBp+WkieabtOOBl+OBquOBhOOAggoKYGBgdGV4dApjb3JlIDUtdGFibGUgc2NoZW1hIGFuZCByZXF1aXJlZCBmaWVsZHMKSUQtZ2VuZXJhdGlvbiBjb250cmFjdApjYWxsZXIgZmllbGQgc2VtYW50aWNzCmZhaWx1cmVfY29kZSAvIHFjX2ZsYWdzIC8gbWF0ZXJpYWxpemF0aW9uX3N0YXR1cyBzZW1hbnRpY3MKY2Vuc29yaW5nIC8gZXhhY3QgLyBjb250ZXh0LWxpbWl0ZWQgZGlzdGluY3Rpb24KbWlzbWF0Y2ggLyBpbmRlbCAvIGludGVycnVwdGlvbiAvIHB1cml0eSAvIExQUyBzZXBhcmF0aW9uCnZhbGlkYXRvciBhY2NlcHRhbmNlIGNvbnRyYWN0CmF0b21pYyBwdWJsaWNhdGlvbiBhbmQgcmVzdGFydCBjb250cmFjdApgYGAKCiMjIDUuIEJpb2xvZ3kgbGF5ZXLjgajjga7looPnlYwKCmBgYHRleHQKY29yZV9iYW1fdG9fZmluYWxfcnVudGltZQpiaW9sb2d5X2VucmljaG1lbnRfcnVudGltZQppbnRlcnByZXRhdGlvbl9hbmRfcmFua2luZ19ydW50aW1lCmBgYAoK44KS5Yil44CF44Gr5aCx5ZGK44GZ44KL44CCYmlvbG9neSBhbm5vdGF0aW9u44KEcmFua2luZ+abtOaWsOOBruOBn+OCgWNvcmUgY2FsbGVy44KS5YaN5a6f6KGM44GX44Gq44GE6Kit6KiI44KS5Y6f5YmH44Go44GZ44KL44CCCgojIyA2LiDkv67lo6voq5bmlofjgafjga7lvJXnlKjopoHku7YKCmBgYHRleHQKUk5BLVRSLVNjb3V0IHZlcnNpb246IHYwLjUuMApHaXQgY29tbWl0OiA8ZnVsbCA0MC1jaGFyYWN0ZXIgU0hBPgpyZWxlYXNlIGRhdGU6IDxZWVlZLU1NLUREPgpyZXBvc2l0b3J5OiA8R2l0SHViIHJlcG9zaXRvcnk+CmNvcmUgc2NoZW1hOiB2MC40LjIKc2NpZW50aWZpYyBjYWxsZXI6IHYwLjQuMQpgYGAKCuaOqOWlqOW8leeUqOihqOePvjoKCj4gUk5BIHJlcGVhdCBhbmFseXNpcyB3YXMgcGVyZm9ybWVkIHVzaW5nIFJOQS1UUi1TY291dCB2MC41LjAgKEdpdCBjb21taXQgYDxTSEE+YDsgcmVsZWFzZWQgYDxEQVRFPmApLgoKIyMgNy4gdjAuMS4x5pmC54K544Gu54++5Zyo5ZywCgpgYGB0ZXh0CjEwMGsgY29ycmVjdG5lc3MgLyBwZXJmb3JtYW5jZSAgICAgICAgICAgICAgICAgICBQQVNTCjEwMGsgc2VsZWN0aXZlIHJlc3RhcnQvcmVzdW1lICAgICAgICAgICAgICAgICAgICBQQVNTCjI1MGsgZGV0ZXJtaW5pc3RpYyBzY2FsaW5nICAgICAgICAgICAgICAgICAgICAgICBQQVNTCnBvc3QtMjUwayBBcmNoaXRlY3R1cmUgYXVkaXQgICAgICAgICAgICAgICAgICAgICBSRVZJRVcsIGJsb2NraW5nIGNvbmZsaWN0cyAwCjUwMGsgZGV0ZXJtaW5pc3RpYyBzY2FsaW5nICAgICAgICAgICAgICAgICAgICAgICBQQVNTCjUwMGsgZm9ybWFsIHJ1bi1JRCBjb250cmFjdCAgICAgICAgICAgICAgICAgICAgICBQQVNTCjUwMGsgY2hlY2twb2ludCBsb2dpY2FsIHJlcHJvZHVjaWJpbGl0eSAgICAgICAgICBQQVNTCjUwMGsgbmVzdGVkLTI1MGsgc2NpZW50aWZpYyBwYXJpdHkgICAgICAgICAgICAgICBQQVNTCjUuMzFNIGxpbmVhciBydW50aW1lIHByb2plY3Rpb24gICAgICAgICAgICAgICAgICA1OS4zOTMgbWluCmZ1bGwtc2NhbGUgZW1waXJpY2FsIHJ1bnRpbWUgICAgICAgICAgICAgICAgICAgICBPUEVOCmZ1bGwtc2NhbGUgbWVtb3J5LWJvdW5kZWQgcGFja2FnZSB2YWxpZGF0aW9uICAgICBPUEVOIC8gUkVRVUlSRUQgQkVGT1JFIFJVTgpmdWxsLXNjYWxlIGRldGVybWluaXNtICAgICAgICAgICAgICAgICAgICAgICAgICAgT1BFTgpmdWxsLXNjYWxlIHJlc3RhcnQvcmVzdW1lICAgICAgICAgICAgICAgICAgICAgICAgT1BFTgpwcmUtcmVsZWFzZSBBcmNoaXRlY3R1cmUgYXVkaXQgICAgICAgICAgICAgICAgICAgT1BFTgpDb3JlIFRlY2huaWNhbCBDb21wbGV0aW9uICAgICAgICAgICAgICAgICAgICAgICAgSU5fUFJPR1JFU1MKYmlvbG9neS1yZWFkeSBpbXBsZW1lbnRhdGlvbiAgICAgICAgICAgICAgICAgICAgIE5PVF9TVEFSVEVEIC8gc2VwYXJhdGUgcGhhc2UKYGBgCg=="
PROFILE_B64 = "Z2F0ZV9pZAlyZXF1aXJlbWVudAlibG9ja2luZ19mb3JfY29yZV9mcmVlemUJY3VycmVudF9zdGF0dXMJZXZpZGVuY2Vfb3JfbmV4dF9hY3Rpb24KQ1RDMDEJQ29yZSBjb3JyZWN0bmVzcywgZm9ybWFsIHJ1bi1JRCBjb250cmFjdCwgYW5kIGRldGVybWluaXN0aWMgNTAwayBkdWFsLXJlcGxpY2F0ZSBzY2FsaW5nCXRydWUJUEFTUwk1MDBrIHYwLjEuMSBleGVjdXRpb24gcGx1cyB2MC4xLjQgY29tcGFyZSBhbWVuZG1lbnQ6IGV4YWN0IEEvQiBwYWNrYWdlIGFuZCBjYWxsZXIgZGV0ZXJtaW5pc20sIGNoZWNrcG9pbnQgbG9naWNhbCByZXByb2R1Y2liaWxpdHksIG5lc3RlZC0yNTBrIHNjaWVudGlmaWMgcGFyaXR5CkNUQzAyCUVtcGlyaWNhbCA1LjMxTS1jbGFzcyBCQU0taW5wdXQgY29yZSBydW50aW1lOyA8PTYwIG1pbiBzdHJpY3QgYmVuY2htYXJrIG9yIDw9NjIgbWluIGRvY3VtZW50ZWQgdGhlc2lzIHRvbGVyYW5jZQl0cnVlCU9QRU4JNTAwayBsaW5lYXIgcHJvamVjdGlvbiA1OS4zOTI3MDAgbWluOyBlbXBpcmljYWwgZnVsbCBydW4gcmVxdWlyZWQKQ1RDMDMJUmVsZWFzZS1zY2FsZSBoYXNoLXNlZWQgLyBwYWNrYWdlIGRldGVybWluaXNtCXRydWUJT1BFTglGdWxsLXNjYWxlIGFsdGVybmF0ZS1zZWVkIGNhbGxlci9tYXRlcmlhbGl6ZXIgZmluYWxpemF0aW9uIG9yIGluZGVwZW5kZW50IGZ1bGwgcmVwbGljYXRlCkNUQzA0CUZ1bGwtc2NhbGUgc2VsZWN0aXZlIHJlc3RhcnQvcmVzdW1lIGFuZCBuby1vcCBzZWNvbmQgcmVzdW1lCXRydWUJT1BFTglJbnRlbnRpb25hbCBmdWxsLXNjYWxlIGNoZWNrcG9pbnQgc3RvcCwgY29ycnVwdC1jaGVja3BvaW50IHJlamVjdGlvbiwgc2VsZWN0aXZlIHJlc3VtZSwgZXhhY3QgZmluYWwgcGFyaXR5CkNUQzA1CUZ1bGwtc2NhbGUgdmFsaWRhdG9ycywgYm91bmRlZCBtZW1vcnksIG5lZ2F0aXZlIGZpeHR1cmUsIGF0b21pYyBwdWJsaWNhdGlvbiwgbWVtb3J5IGFuZCBhcnRpZmFjdCBhdWRpdAl0cnVlCVJFVklFVwk1MDBrIHBhY2thZ2UgdmFsaWRhdG9yIHBlYWsgUlNTIDI3ODg4NjU2IGtCOyBuYWl2ZSBmdWxsLXNjYWxlIHByb2plY3Rpb24gZXhjZWVkcyBob3N0IFJBTSwgc28gbWVtb3J5LWJvdW5kZWQgZXF1aXZhbGVudCB2YWxpZGF0b3IgaXMgcmVxdWlyZWQgYmVmb3JlIGZ1bGwgcnVuCkNUQzA2CVBSRV9SRUxFQVNFX0NBTkRJREFURSBBcmNoaXRlY3R1cmUgY29uc2lzdGVuY3kgYXVkaXQgd2l0aCBubyBibG9ja2luZyBjb25mbGljdHMgb3IgcmVsZWFzZS1ibG9ja2luZyBSRVZJRVcJdHJ1ZQlPUEVOCVJ1biBhZnRlciBmdWxsLXNjYWxlIGdhdGVzIGFuZCBiZWZvcmUgcmVsZWFzZSB0YWcKQ1RDMDcJRXhwbGljaXQgYWN0aXZlLXBhdGggcHJvbW90aW9uIGFuZCBjbGVhbi1pbnN0YWxsIHJlcHJvZHVjaWJpbGl0eQl0cnVlCU9QRU4JUmVsZWFzZS1jYW5kaWRhdGUgaW5zdGFsbC9ydW4gdmFsaWRhdGlvbiB3aGlsZSBwcmVzZXJ2aW5nIHJlZmVyZW5jZS9hdWRpdCBsYW5lCkNUQzA4CUltbXV0YWJsZSB0aGVzaXMtY2l0YWJsZSBHaXRIdWIgcmVsZWFzZSB3aXRoIHRhZywgZnVsbCBjb21taXQgU0hBLCBjaGVja3N1bXMsIGVudmlyb25tZW50IGxvY2sgYW5kIENJVEFUSU9OLmNmZgl0cnVlCU9QRU4JUHJlcGFyZSB2MC41LjAtcmMxIHRoZW4gZmluYWwgdjAuNS4wIGFmdGVyIGFsbCBibG9ja2VycyBQQVNTCkNUQzA5CTUuMzFNLWNsYXNzIEJBTS1pbnB1dCBydW50aW1lIDw9MzAgbWludXRlcwlmYWxzZQlUQVJHRVRfTk9UX01FVAlNYWludGFpbiBhcyBmb3JtYWwgdGFyZ2V0OyBjb250aW51ZSBpbiBhIHN1YnNlcXVlbnQgdmVyc2lvbiBpZiBzdWJzdGFudGlhbCByZWRlc2lnbiBpcyByZXF1aXJlZApDVEMxMAlCaW9sb2d5L2ludGVycHJldGF0aW9uIGxheWVyIHJlbWFpbnMgc2VwYXJhdGVseSB2ZXJzaW9uZWQgYW5kIGRvZXMgbm90IGJsb2NrIGNvcmUgZnJlZXplCWZhbHNlCVBBU1MJRzIwLUcyMyByZW1haW4gT1BFTiBmb3IgdGhlIHBvc3QtY29yZSBiaW9sb2d5IHBoYXNlCg=="


class AuditError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def ensure_file(path: Path) -> None:
    if not path.is_file() or path.stat().st_size <= 0:
        raise AuditError(f"missing or empty file: {path}")


def read_metrics(path: Path) -> dict[str, str]:
    ensure_file(path)
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames != ["metric", "value"]:
            raise AuditError(f"unexpected metric TSV schema: {path}: {reader.fieldnames}")
        return {row["metric"]: row["value"] for row in reader}


def write_tsv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    if not rows:
        raise AuditError(f"refusing empty TSV: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = list(rows[0])
    temp = path.with_name("." + path.name + ".part")
    with temp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temp, path)


def write_metrics(path: Path, rows: list[tuple[str, Any]]) -> None:
    write_tsv(
        path,
        [{"metric": key, "value": str(value)} for key, value in rows],
        ["metric", "value"],
    )


def safe_copy(src: Path, dst: Path) -> None:
    ensure_file(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def install_exact_bytes(data: bytes, dst: Path, mode: int = 0o644) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(data).hexdigest()
    if dst.exists():
        if not dst.is_file() or sha256_file(dst) != digest:
            raise AuditError(f"refusing to overwrite different file: {dst}")
    else:
        dst.write_bytes(data)
    dst.chmod(mode)


def run_capture(command: list[str], output: Path, allow_failure: bool = False) -> int:
    proc = subprocess.run(command, text=True, capture_output=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "$ " + " ".join(command) + "\n\n" + proc.stdout + proc.stderr,
        encoding="utf-8",
    )
    if proc.returncode != 0 and not allow_failure:
        raise AuditError(f"command failed ({proc.returncode}): {command}")
    return proc.returncode


def parse_memtotal_bytes() -> int:
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        if line.startswith("MemTotal:"):
            return int(line.split()[1]) * 1024
    raise AuditError("MemTotal not found")


def locate_package_manifest() -> Path:
    candidates = sorted((RESULT_ROOT / "replicate_A").rglob("package_manifest.tsv"))
    if len(candidates) != 1:
        raise AuditError(f"expected exactly one replicate-A package_manifest.tsv, found {len(candidates)}")
    return candidates[0]


def ast_inventory(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))
    counts = {
        "source_path": str(path),
        "source_sha256": sha256_file(path),
        "source_lines": len(text.splitlines()),
        "function_defs": 0,
        "class_defs": 0,
        "list_comprehensions": 0,
        "set_comprehensions": 0,
        "dict_comprehensions": 0,
        "generator_expressions": 0,
        "calls_list": 0,
        "calls_set": 0,
        "calls_dict": 0,
        "calls_sorted": 0,
        "calls_csv_dictreader": 0,
        "calls_readlines": 0,
        "calls_subprocess": 0,
    }
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            counts["function_defs"] += 1
        elif isinstance(node, ast.ClassDef):
            counts["class_defs"] += 1
        elif isinstance(node, ast.ListComp):
            counts["list_comprehensions"] += 1
        elif isinstance(node, ast.SetComp):
            counts["set_comprehensions"] += 1
        elif isinstance(node, ast.DictComp):
            counts["dict_comprehensions"] += 1
        elif isinstance(node, ast.GeneratorExp):
            counts["generator_expressions"] += 1
        elif isinstance(node, ast.Call):
            name = ""
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                name = node.func.attr
                if (
                    isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "csv"
                    and node.func.attr == "DictReader"
                ):
                    counts["calls_csv_dictreader"] += 1
                if (
                    isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "subprocess"
                ):
                    counts["calls_subprocess"] += 1
            if name == "list":
                counts["calls_list"] += 1
            elif name == "set":
                counts["calls_set"] += 1
            elif name == "dict":
                counts["calls_dict"] += 1
            elif name == "sorted":
                counts["calls_sorted"] += 1
            elif name == "readlines":
                counts["calls_readlines"] += 1
    return counts


def build_manifest(root: Path) -> None:
    rows = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == "artifact_manifest.tsv":
            continue
        rows.append({
            "relative_path": str(path.relative_to(root)),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        })
    write_tsv(root / "artifact_manifest.tsv", rows)


def make_bundle(root: Path, bundle: Path) -> None:
    bundle.unlink(missing_ok=True)
    Path(str(bundle) + ".sha256").unlink(missing_ok=True)
    with tarfile.open(bundle, "w:gz", format=tarfile.PAX_FORMAT) as tar:
        tar.add(root, arcname=root.name)
    digest = sha256_file(bundle)
    Path(str(bundle) + ".sha256").write_text(
        f"{digest}  {bundle}\n", encoding="utf-8"
    )


def main() -> int:
    if PROJECT_ROOT != Path("/mnt/intelssd/rnatr_project"):
        raise AuditError(f"unexpected project root: {PROJECT_ROOT}")
    if OUT_ROOT.exists():
        raise AuditError(f"output root exists; preserve and review: {OUT_ROOT}")
    if SUCCESS_BUNDLE.exists() or FAILURE_BUNDLE.exists():
        raise AuditError("Downloads output bundle already exists; refusing overwrite")

    ensure_file(FINAL_QC)
    if sha256_file(FINAL_QC) != FINAL_QC_SHA:
        raise AuditError("500k final QC SHA mismatch")

    metrics = read_metrics(FINAL_QC)
    required = {
        "deterministic_500k_scaling": "PASS",
        "package_exact_logical_reproducibility": "true",
        "package_exact_raw_reproducibility": "true",
        "caller_hashseed_logical_reproducibility": "true",
        "checkpoint_logical_reproducibility": "true",
        "nested_250k_scientific_parity": "true",
        "formal_run_id_contract": "PASS",
        "run_id_compatibility_alias_used": "false",
        "active_pipeline_modified": "false",
        "ssot_modified": "false",
        "full_5_31m_run_started": "false",
        "audit_status": "PASS",
    }
    for key, wanted in required.items():
        if metrics.get(key) != wanted:
            raise AuditError(f"500k gate mismatch {key}={metrics.get(key)!r} != {wanted!r}")

    for path, expected in EXPECTED_COMPONENT_SHA.items():
        ensure_file(path)
        observed = sha256_file(path)
        if observed != expected:
            raise AuditError(f"component SHA mismatch {path}: {observed} != {expected}")

    ensure_file(V042_TSV_VALIDATOR)
    ensure_file(SSOT_CLI)
    ensure_file(SSOT_DB)
    if sha256_file(SSOT_CLI) != SSOT_CLI_SHA:
        raise AuditError("current SSOT source SHA mismatch")
    if sha256_file(SSOT_DB) != SSOT_DB_SHA:
        raise AuditError("current SSOT DB SHA mismatch")

    OUT_ROOT.mkdir(parents=True, exist_ok=False)
    for sub in ("sources", "schema", "qc", "system", "docs", "metadata", "logs"):
        (OUT_ROOT / sub).mkdir()

    # Install immutable provenance copies.
    contract_data = base64.b64decode(CONTRACT_B64)
    profile_data = base64.b64decode(PROFILE_B64)
    install_exact_bytes(
        contract_data,
        PROJECT_ROOT / "docs/stage15a/RNA_TR_Scout_Core_Technical_Completion_and_Freeze_contract_v0.1.1.md",
    )
    install_exact_bytes(
        profile_data,
        PROJECT_ROOT / "validation/profiles/core_technical_completion_release_profile_v0.1.1.tsv",
    )
    install_exact_bytes(
        Path(__file__).read_bytes(),
        PROJECT_ROOT / "scripts/rnatr_stage15a_fullscale_readiness_collect_v0.1.0.py",
        0o755,
    )

    (OUT_ROOT / "docs/RNA_TR_Scout_Core_Technical_Completion_and_Freeze_contract_v0.1.1.md").write_bytes(contract_data)
    (OUT_ROOT / "docs/core_technical_completion_release_profile_v0.1.1.tsv").write_bytes(profile_data)
    safe_copy(Path(__file__), OUT_ROOT / "sources" / Path(__file__).name)

    # Exact validator/schema sources.
    for path in sorted(SCHEMA_DIR.rglob("*")):
        if path.is_file():
            safe_copy(path, OUT_ROOT / "schema" / path.relative_to(SCHEMA_DIR))
    for path in SELECTED_SOURCE_PATHS + [PARALLEL_VALIDATOR]:
        ensure_file(path)
        safe_copy(path, OUT_ROOT / "sources" / path.name)
    for path in SELECTED_QC_PATHS:
        ensure_file(path)
        safe_copy(path, OUT_ROOT / "qc" / path.name)

    package_manifest = locate_package_manifest()
    safe_copy(package_manifest, OUT_ROOT / "qc" / "replicate_A.package_manifest.tsv")

    # Read-only SSOT and system audits.
    run_capture(
        [sys.executable, str(SSOT_CLI), "--project-root", str(PROJECT_ROOT), "validate"],
        OUT_ROOT / "logs/ssot_validate.log",
    )
    Path(OUT_ROOT / "system/proc_meminfo.txt").write_text(
        Path("/proc/meminfo").read_text(encoding="utf-8"), encoding="utf-8"
    )
    for command, name, allow in [
        (["free", "-b"], "free_b.txt", False),
        (["df", "-B1", str(PROJECT_ROOT)], "df_project_root.txt", False),
        (["df", "-T", str(PROJECT_ROOT)], "df_type_project_root.txt", False),
        (["findmnt", "-T", str(PROJECT_ROOT)], "findmnt_project_root.txt", True),
        (["lscpu"], "lscpu.txt", False),
        (["lsblk", "-b", "-o", "NAME,SIZE,FSTYPE,MOUNTPOINTS"], "lsblk.txt", True),
        (["bash", "-lc", "ulimit -a"], "ulimit.txt", False),
        (["du", "-sb", str(RESULT_ROOT), str(QC_ROOT)], "du_500k_roots.txt", False),
    ]:
        run_capture(command, OUT_ROOT / "system" / name, allow_failure=allow)

    # Source inventory for the memory-heavy frozen validator.
    inventories = [
        ast_inventory(V041_PACKAGE_VALIDATOR),
        ast_inventory(V042_PACKAGE_WRAPPER),
        ast_inventory(V042_FLANK_VALIDATOR),
        ast_inventory(PARALLEL_VALIDATOR),
    ]
    write_tsv(OUT_ROOT / "metadata/validator_static_source_inventory.tsv", inventories)

    scale = 5_312_696 / 500_000
    runtime_seconds = float(metrics["conservative_500k_bam_to_final_cold_seconds"])
    projected_minutes = runtime_seconds * scale / 60.0
    validator_rss_kb = max(
        int(metrics["replicate_A_maximum_observed_stage_rss_kbytes"]),
        int(metrics["replicate_B_maximum_observed_stage_rss_kbytes"]),
    )
    temp_bytes = max(
        int(metrics["replicate_A_peak_temporary_and_output_bytes"]),
        int(metrics["replicate_B_peak_temporary_and_output_bytes"]),
    )
    memtotal_bytes = parse_memtotal_bytes()
    stat = os.statvfs(PROJECT_ROOT)
    free_bytes = stat.f_bavail * stat.f_frsize

    manifest_fields, manifest_rows = None, []
    with package_manifest.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        manifest_fields = reader.fieldnames
        manifest_rows = list(reader)
    final_package_bytes_500k = 0
    for row in manifest_rows:
        for candidate in ("bytes", "size_bytes"):
            if candidate in row and row[candidate] not in ("", "."):
                final_package_bytes_500k += int(row[candidate])
                break

    projected_validator_bytes = int(validator_rss_kb * 1024 * scale)
    projected_temp_bytes = int(temp_bytes * scale)
    projected_final_bytes = int(final_package_bytes_500k * scale)
    recommended_free_bytes = max(
        int(projected_temp_bytes * 1.7),
        projected_temp_bytes + projected_final_bytes * 2,
    )

    memory_status = (
        "BLOCKED_MEMORY_BOUNDED_VALIDATOR_REQUIRED"
        if projected_validator_bytes > int(memtotal_bytes * 0.80)
        else "REVIEW"
    )
    storage_status = (
        "PASS_CURRENT_FREE_SPACE"
        if free_bytes >= recommended_free_bytes
        else "BLOCKED_INSUFFICIENT_FREE_SPACE"
    )

    projection_rows = [
        {"metric": "full_read_count", "value": 5_312_696},
        {"metric": "benchmark_read_count", "value": 500_000},
        {"metric": "scale_factor", "value": f"{scale:.9f}"},
        {"metric": "500k_conservative_seconds", "value": f"{runtime_seconds:.9f}"},
        {"metric": "linear_full_projection_minutes", "value": f"{projected_minutes:.9f}"},
        {"metric": "strict_engineering_benchmark_minutes", "value": "60.0"},
        {"metric": "thesis_release_tolerance_minutes", "value": "62.0"},
        {"metric": "strict_60_margin_minutes", "value": f"{60.0 - projected_minutes:.9f}"},
        {"metric": "tolerance_62_margin_minutes", "value": f"{62.0 - projected_minutes:.9f}"},
        {"metric": "500k_max_observed_stage_rss_kbytes", "value": validator_rss_kb},
        {"metric": "naive_full_validator_rss_gib", "value": f"{projected_validator_bytes / 2**30:.6f}"},
        {"metric": "host_memtotal_gib", "value": f"{memtotal_bytes / 2**30:.6f}"},
        {"metric": "memory_readiness_status", "value": memory_status},
        {"metric": "500k_peak_temp_and_output_bytes", "value": temp_bytes},
        {"metric": "naive_full_temp_and_output_gb", "value": f"{projected_temp_bytes / 1e9:.6f}"},
        {"metric": "500k_final_package_bytes", "value": final_package_bytes_500k},
        {"metric": "naive_full_final_package_gb", "value": f"{projected_final_bytes / 1e9:.6f}"},
        {"metric": "recommended_minimum_free_space_gb", "value": f"{recommended_free_bytes / 1e9:.6f}"},
        {"metric": "current_project_filesystem_free_gb", "value": f"{free_bytes / 1e9:.6f}"},
        {"metric": "storage_readiness_status", "value": storage_status},
    ]
    write_tsv(OUT_ROOT / "fullscale_resource_projection.tsv", projection_rows, ["metric", "value"])

    full_authorized = memory_status != "BLOCKED_MEMORY_BOUNDED_VALIDATOR_REQUIRED" and storage_status.startswith("PASS")
    readiness = (
        "READY_FOR_FULL_EMPIRICAL_RUN"
        if full_authorized
        else "REVIEW_MEMORY_BOUNDED_VALIDATOR_REQUIRED_BEFORE_FULL_RUN"
    )

    write_metrics(
        OUT_ROOT / "fullscale_readiness.qc.tsv",
        [
            ("audit_version", VERSION),
            ("run_id", RUN_ID),
            ("deterministic_500k_scaling", metrics["deterministic_500k_scaling"]),
            ("formal_run_id_contract", metrics["formal_run_id_contract"]),
            ("checkpoint_logical_reproducibility", metrics["checkpoint_logical_reproducibility"]),
            ("nested_250k_scientific_parity", metrics["nested_250k_scientific_parity"]),
            ("linear_5_31m_projection_minutes", f"{projected_minutes:.9f}"),
            ("strict_60min_projection", "PASS" if projected_minutes <= 60 else "FAIL"),
            ("thesis_62min_tolerance_projection", "PASS" if projected_minutes <= 62 else "FAIL"),
            ("memory_readiness_status", memory_status),
            ("storage_readiness_status", storage_status),
            ("full_empirical_run_authorized", str(full_authorized).lower()),
            ("active_pipeline_modified", "false"),
            ("ssot_modified", "false"),
            ("full_5_31m_run_started", "false"),
            ("audit_status", "PASS"),
            ("readiness_status", readiness),
            ("next_gate", "BUILD_MEMORY_BOUNDED_PACKAGE_VALIDATOR_AND_500K_EQUIVALENCE_TEST"),
        ],
    )

    build_manifest(OUT_ROOT)
    make_bundle(OUT_ROOT, SUCCESS_BUNDLE)

    print("===== RNA-TR-Scout full-scale readiness collection =====")
    print(f"500k deterministic scaling\t{metrics['deterministic_500k_scaling']}")
    print(f"5.31M linear projection minutes\t{projected_minutes:.6f}")
    print(f"strict 60-minute projection\t{'PASS' if projected_minutes <= 60 else 'FAIL'}")
    print(f"thesis 62-minute tolerance\t{'PASS' if projected_minutes <= 62 else 'FAIL'}")
    print(f"naive full validator RSS GiB\t{projected_validator_bytes / 2**30:.3f}")
    print(f"host RAM GiB\t{memtotal_bytes / 2**30:.3f}")
    print(f"readiness status\t{readiness}")
    print("full 5.31M started\tfalse")
    print(f"OUTPUT_BUNDLE\t{SUCCESS_BUNDLE}")
    print(f"OUTPUT_SHA_FILE\t{SUCCESS_BUNDLE}.sha256")
    return 0


def failure_bundle(exc: BaseException) -> None:
    temp = Path(os.environ.get("TMPDIR", "/tmp")) / "rnatr_fullscale_readiness_failure_v010"
    shutil.rmtree(temp, ignore_errors=True)
    temp.mkdir(parents=True)
    (temp / "failure.txt").write_text(
        "".join(traceback.format_exception(exc)), encoding="utf-8"
    )
    try:
        shutil.copy2(Path(__file__), temp / Path(__file__).name)
    except Exception:
        pass
    make_bundle(temp, FAILURE_BUNDLE)


if __name__ == "__main__":
    try:
        rc = main()
    except BaseException as exc:
        try:
            failure_bundle(exc)
            print(f"ERROR: {exc}", file=sys.stderr)
            print(f"Failure bundle: {FAILURE_BUNDLE}", file=sys.stderr)
            print(f"Failure SHA: {FAILURE_BUNDLE}.sha256", file=sys.stderr)
        except Exception as pack_exc:
            print(f"failure packaging also failed: {pack_exc}", file=sys.stderr)
        raise
    else:
        raise SystemExit(rc)
