"""Command-line interface for RNA-TR-Scout."""

from __future__ import annotations

import argparse
import json

from . import __version__
from .batch import classify_p3_tsv
from .cigar import project_reference_boundary_to_query
from .contract import check_contract
from .p3 import P3Observation, classify_p3
from .p3_geometry import (
    candidate_reference_geometry,
    expected_orientation_transform,
)
from .p3_bridge import (
    BridgeAlignmentObservation,
    evaluate_bridge_alignment,
)
from .fasta import fetch_fasta_record
from .p3_pair import run_isolated_pair_alignment


def _boolean(text: str) -> bool:
    normalized = text.strip().lower()

    if normalized in {"true", "yes", "1"}:
        return True

    if normalized in {"false", "no", "0"}:
        return False

    raise argparse.ArgumentTypeError(
        "expected true/false, yes/no, or 1/0"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rnatr-scout",
        description=(
            "Long-read RNA tandem-repeat evidence caller"
        ),
    )
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    subparsers.add_parser(
        "version",
        help="Print package version",
    )

    p3_parser = subparsers.add_parser(
        "p3-classify",
        help="Apply the frozen P3 decision layer",
    )
    p3_parser.add_argument(
        "--alignment-strand",
        required=True,
        choices=["+", "-"],
    )
    p3_parser.add_argument(
        "--target-entry-projected",
        required=True,
        type=_boolean,
    )
    p3_parser.add_argument(
        "--motif",
        required=True,
    )
    p3_parser.add_argument(
        "--target-side",
        required=True,
        choices=[
            "GENOMIC_LEFT",
            "GENOMIC_RIGHT",
        ],
    )
    p3_parser.add_argument(
        "--tract-bp",
        type=int,
        default=None,
    )
    p3_parser.add_argument(
        "--tract-reaches-raw-end",
        type=_boolean,
        default=False,
    )

    batch_parser = subparsers.add_parser(
        "p3-batch-classify",
        help=(
            "Apply P3 decision rules to every row of a TSV"
        ),
    )
    batch_parser.add_argument(
        "--input-tsv",
        required=True,
    )
    batch_parser.add_argument(
        "--output-tsv",
        required=True,
    )

    geometry_parser = subparsers.add_parser(
        "p3-geometry",
        help=(
            "Calculate target-facing orientation and local "
            "candidate-reference coordinates"
        ),
    )
    geometry_parser.add_argument(
        "--alignment-strand",
        required=True,
        choices=["+", "-"],
    )
    geometry_parser.add_argument(
        "--target-side",
        required=True,
        choices=[
            "GENOMIC_LEFT",
            "GENOMIC_RIGHT",
        ],
    )
    geometry_parser.add_argument(
        "--block-start",
        required=True,
        type=int,
    )
    geometry_parser.add_argument(
        "--block-end",
        required=True,
        type=int,
    )
    geometry_parser.add_argument(
        "--target-start",
        required=True,
        type=int,
    )
    geometry_parser.add_argument(
        "--target-end",
        required=True,
        type=int,
    )
    geometry_parser.add_argument(
        "--target-entry-bp",
        type=int,
        default=60,
    )
    geometry_parser.add_argument(
        "--minimum-target-entry-bp",
        type=int,
        default=12,
    )

    projection_parser = subparsers.add_parser(
        "project-reference-boundary",
        help=(
            "Project a candidate-reference boundary through "
            "a CIGAR onto query coordinates"
        ),
    )
    projection_parser.add_argument(
        "--query-start",
        required=True,
        type=int,
    )
    projection_parser.add_argument(
        "--reference-start",
        required=True,
        type=int,
    )
    projection_parser.add_argument(
        "--cigar",
        required=True,
    )
    projection_parser.add_argument(
        "--reference-boundary",
        required=True,
        type=int,
    )

    bridge_parser = subparsers.add_parser(
        "p3-bridge-evaluate",
        help="Evaluate one normalized candidate bridge alignment",
    )
    bridge_parser.add_argument(
        "--alignment-present",
        required=True,
        type=_boolean,
    )
    bridge_parser.add_argument(
        "--alignment-strand",
        choices=["+", "-"],
    )
    bridge_parser.add_argument(
        "--query-start",
        type=int,
    )
    bridge_parser.add_argument(
        "--reference-start",
        type=int,
    )
    bridge_parser.add_argument(
        "--query-coverage",
        type=float,
    )
    bridge_parser.add_argument(
        "--identity",
        type=float,
    )
    bridge_parser.add_argument(
        "--reference-end",
        type=int,
    )
    bridge_parser.add_argument(
        "--bridge-bp",
        required=True,
        type=int,
    )
    bridge_parser.add_argument(
        "--target-entry-bp",
        required=True,
        type=int,
    )
    bridge_parser.add_argument(
        "--query-can-reach-target-entry",
        required=True,
        type=_boolean,
    )
    bridge_parser.add_argument(
        "--minimum-target-entry-bp",
        type=int,
        default=12,
    )
    bridge_parser.add_argument(
        "--boundary-tolerance-bp",
        type=int,
        default=10,
    )
    bridge_parser.add_argument(
        "--minimum-identity",
        type=float,
        default=0.70,
    )
    bridge_parser.add_argument(
        "--minimum-query-coverage",
        type=float,
        default=0.70,
    )

    pair_parser = subparsers.add_parser(
        "p3-align-project-pair",
        help=(
            "Run isolated minimap2 alignment, validate the bridge, "
            "and project the target entry"
        ),
    )
    pair_parser.add_argument(
        "--query-fasta",
        required=True,
    )
    pair_parser.add_argument(
        "--query-id",
        required=True,
    )
    pair_parser.add_argument(
        "--reference-fasta",
        required=True,
    )
    pair_parser.add_argument(
        "--reference-id",
        required=True,
    )
    pair_parser.add_argument(
        "--bridge-bp",
        required=True,
        type=int,
    )
    pair_parser.add_argument(
        "--target-entry-bp",
        required=True,
        type=int,
    )
    pair_parser.add_argument(
        "--query-can-reach-target-entry",
        required=True,
        type=_boolean,
    )

    contract_parser = subparsers.add_parser(
        "contract-check",
        help="Check schema v0.3.2 and regression fixture",
    )
    contract_parser.add_argument(
        "--schema-dir",
        required=True,
    )
    contract_parser.add_argument(
        "--fixture-dir",
        required=True,
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)

    if arguments.command == "version":
        print(__version__)
        return 0

    if arguments.command == "p3-classify":
        observation = P3Observation(
            alignment_strand=arguments.alignment_strand,
            target_entry_projected=(
                arguments.target_entry_projected
            ),
            canonical_motif=arguments.motif,
            target_facing_genomic_side=(
                arguments.target_side
            ),
            tract_bp=arguments.tract_bp,
            tract_reaches_expected_raw_end=(
                arguments.tract_reaches_raw_end
            ),
        )
        decision = classify_p3(observation)
        print(
            json.dumps(
                decision.to_dict(),
                sort_keys=True,
            )
        )
        return 0

    if arguments.command == "p3-batch-classify":
        rows = classify_p3_tsv(
            arguments.input_tsv,
            arguments.output_tsv,
        )
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "rows_written": rows,
                    "output_tsv": arguments.output_tsv,
                },
                sort_keys=True,
            )
        )
        return 0

    if arguments.command == "p3-geometry":
        transform = expected_orientation_transform(
            arguments.alignment_strand,
            arguments.target_side,
        )
        geometry = candidate_reference_geometry(
            block_start=arguments.block_start,
            block_end=arguments.block_end,
            target_start=arguments.target_start,
            target_end=arguments.target_end,
            target_side=arguments.target_side,
            target_entry_bp=arguments.target_entry_bp,
            minimum_target_entry_bp=(
                arguments.minimum_target_entry_bp
            ),
        )
        print(
            json.dumps(
                {
                    "orientation_transform": transform,
                    "fetch_start": geometry.fetch_start,
                    "fetch_end": geometry.fetch_end,
                    "reverse_complement_after_fetch": (
                        geometry.reverse_complement_after_fetch
                    ),
                    "bridge_bp": geometry.bridge_bp,
                    "target_entry_bp": geometry.target_entry_bp,
                    "required_target_entry_bp": (
                        geometry.required_target_entry_bp
                    ),
                    "reference_bp": geometry.reference_bp,
                },
                sort_keys=True,
            )
        )
        return 0

    if arguments.command == "project-reference-boundary":
        projection = project_reference_boundary_to_query(
            query_start=arguments.query_start,
            reference_start=arguments.reference_start,
            cigar=arguments.cigar,
            reference_boundary=(
                arguments.reference_boundary
            ),
        )
        print(
            json.dumps(
                {
                    "query_offset": projection.query_offset,
                    "status": projection.status,
                },
                sort_keys=True,
            )
        )
        return 0

    if arguments.command == "p3-bridge-evaluate":
        observation = BridgeAlignmentObservation(
            alignment_present=arguments.alignment_present,
            alignment_strand=arguments.alignment_strand,
            query_start=arguments.query_start,
            reference_start=arguments.reference_start,
            query_coverage=arguments.query_coverage,
            identity=arguments.identity,
            reference_end=arguments.reference_end,
            bridge_bp=arguments.bridge_bp,
            target_entry_bp=arguments.target_entry_bp,
            query_can_reach_target_entry=(
                arguments.query_can_reach_target_entry
            ),
        )
        decision = evaluate_bridge_alignment(
            observation,
            minimum_target_entry_bp=(
                arguments.minimum_target_entry_bp
            ),
            boundary_tolerance_bp=(
                arguments.boundary_tolerance_bp
            ),
            minimum_identity=arguments.minimum_identity,
            minimum_query_coverage=(
                arguments.minimum_query_coverage
            ),
        )
        print(
            json.dumps(
                decision.to_dict(),
                sort_keys=True,
            )
        )
        return 0

    if arguments.command == "p3-align-project-pair":
        query_sequence = fetch_fasta_record(
            arguments.query_fasta,
            arguments.query_id,
        )
        reference_sequence = fetch_fasta_record(
            arguments.reference_fasta,
            arguments.reference_id,
        )
        result = run_isolated_pair_alignment(
            query_name=arguments.query_id,
            query_sequence=query_sequence,
            target_name=arguments.reference_id,
            target_sequence=reference_sequence,
            bridge_bp=arguments.bridge_bp,
            target_entry_bp=arguments.target_entry_bp,
            query_can_reach_target_entry=(
                arguments.query_can_reach_target_entry
            ),
        )
        print(
            json.dumps(
                result.to_dict(),
                sort_keys=True,
            )
        )
        return 0

    if arguments.command == "contract-check":
        result = check_contract(
            arguments.schema_dir,
            arguments.fixture_dir,
        )
        print(
            json.dumps(
                result,
                sort_keys=True,
            )
        )
        return 0 if result["status"] == "PASS" else 1

    parser.error(
        f"unsupported command: {arguments.command}"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
