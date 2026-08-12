from __future__ import annotations

import ast
import difflib
import hashlib
import sys
from pathlib import Path

EXPECTED_SOURCE_SHA256 = "4a8fe5115e6697ebb1f3fc8a3d456cc3e2d7a8f63562e6c167dc449564eaf8e8"
STAGE_VERSION = "rnatr_stage15a_native_v041_no_legacy_audit_v0.2.0"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def function_ast(text: str, name: str) -> str:
    tree = ast.parse(text)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.dump(node, include_attributes=False)
    raise RuntimeError(f"function not found: {name}")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


def patch(source: Path, destination: Path, diff_path: Path | None = None) -> None:
    observed = sha256(source)
    if observed != EXPECTED_SOURCE_SHA256:
        raise RuntimeError(
            f"caller integration driver SHA mismatch: {observed} != {EXPECTED_SOURCE_SHA256}"
        )
    original = source.read_text(encoding="utf-8")
    text = original

    text = replace_once(
        text,
        '    old11h_p=P/"results/11_periodic_refinement"/run/"target_constrained_periodic_calls.tsv.gz"\n',
        "",
        "remove old11h path",
    )
    text = replace_once(
        text,
        '    caller02=P/"src/rnatr_scout/general_caller/rnatr_general_repeat_caller_ref_v0.2.0.py"\n',
        "",
        "remove unused caller02 path",
    )
    text = replace_once(
        text,
        "    for p in [jobs_p,proj_p,old11h_p,caller_p,caller02,windows_p]:\n",
        "    for p in [jobs_p,proj_p,caller_p,windows_p]:\n",
        "remove audit-only input requirements",
    )
    text = replace_once(
        text,
        "    old=read_gz_tsv(old11h_p)\n",
        "",
        "remove audit-only table load",
    )
    text = replace_once(
        text,
        '    with gzip.open(out_p,"wt",encoding="utf-8",newline="") as f:\n',
        '    with gzip.open(out_p,"wt",compresslevel=1,encoding="utf-8",newline="") as f:\n',
        "caller gzip level",
    )

    audit_start = text.index("    # Legacy P0/P1 bridge audit.\n")
    audit_end = text.index("    summary=[\n", audit_start)
    text = text[:audit_start] + text[audit_end:]

    text = replace_once(
        text,
        '        ("stage_version","rnatr_general_caller_100k_integration_candidate_v0.1.0"),\n',
        f'        ("stage_version","{STAGE_VERSION}"),\n'
        '        ("scientific_caller_version","rnatr_general_repeat_caller_ref_v0.4.1"),\n'
        '        ("legacy_11f_11h_bridge_audit_executed","false"),\n'
        '        ("legacy_11f_11h_bridge_role","AUDIT_ONLY_NOT_CALL_INPUT"),\n',
        "summary stage version",
    )
    legacy_summary = '''        ("legacy_p01_rows",len(old)),
        ("legacy_p01_called_by_v04",len(old_called)),
        ("legacy_p01_completion_fraction",len(old_called)/len(old) if old else 0),
        ("legacy_p01_motif_concordance_fraction",motif_same/len(old_called) if old_called else 0),
        ("legacy_p01_exact_length_abs_delta_median_bp",statistics.median(deltas) if deltas else "."),
        ("legacy_p01_exact_length_abs_delta_p95_bp",q(deltas,.95) if deltas else "."),
'''
    text = replace_once(text, legacy_summary, "", "remove audit-only summary")
    text = replace_once(
        text,
        '        ("comparison_semantics","SOFTWARE_INTEGRATION_BRIDGE_NOT_LEGACY_TRUTH_NOT_PATHOGENICITY"),\n'
        '        ("next_gate","MAP_V04_CALLS_TO_EVIDENCE_SCHEMA_AND_BUILD_ISOLATED_100K_END_TO_END"),\n'
        '        ("audit_status","PASS" if errors==0 and prior_bad==0 and len(old_called)==len(old) else "REVIEW"),\n',
        '        ("comparison_semantics","SCIENTIFIC_CALL_OUTPUT_ONLY_LEGACY_BRIDGE_AUDIT_OMITTED"),\n'
        '        ("audit_status","PASS" if errors==0 else "FAIL"),\n',
        "replace legacy audit gate",
    )
    text = replace_once(
        text,
        '    if summary[-1][1]!="PASS":\n'
        '        print("Stage 14K caller run retains expected integration REVIEW semantics")\n',
        '    return 0 if errors==0 else 2\n',
        "return caller status",
    )
    text = replace_once(
        text,
        'if __name__=="__main__":\n    main()\n',
        'if __name__=="__main__":\n    raise SystemExit(main())\n',
        "main exit status",
    )

    # The scientific implementation must remain byte-for-byte AST equivalent.
    for function_name in ("load_caller", "init_worker", "geometry_for_call", "split_motifs", "worker"):
        if function_ast(original, function_name) != function_ast(text, function_name):
            raise RuntimeError(f"scientific function changed unexpectedly: {function_name}")

    forbidden = ("old11h_p", "old_called", "legacy_p01_rows", "caller02")
    for token in forbidden:
        if token in text:
            raise RuntimeError(f"audit-only token remains: {token}")
    if 'compresslevel=1' not in text:
        raise RuntimeError("caller compression optimization missing")

    ast.parse(text)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")
    destination.chmod(0o755)
    if diff_path is not None:
        diff_path.parent.mkdir(parents=True, exist_ok=True)
        diff_path.write_text(
            "".join(
                difflib.unified_diff(
                    original.splitlines(keepends=True),
                    text.splitlines(keepends=True),
                    fromfile=str(source),
                    tofile=str(destination),
                )
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    if len(sys.argv) not in {3, 4}:
        raise SystemExit(f"usage: {sys.argv[0]} SOURCE DESTINATION [DIFF]")
    patch(
        Path(sys.argv[1]),
        Path(sys.argv[2]),
        Path(sys.argv[3]) if len(sys.argv) == 4 else None,
    )
