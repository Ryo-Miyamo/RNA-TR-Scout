#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import sys
from pathlib import Path

VALIDATOR_VERSION = "0.3.1"
BOOLEAN_VALUES = {"true", "false"}


def open_text(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", newline="")
    return path.open("r", encoding="utf-8", newline="")


def validate_value(value: str, spec: dict, enums: dict) -> str | None:
    dtype = spec["type"]

    # Bugfix v0.3.1:
    # "." is globally used as the missing token, but it is also an explicit
    # allowed value of the strand enum for unmapped records. An explicit enum
    # value takes precedence over the global missing-token interpretation.
    if dtype == "enum":
        allowed = set(enums[spec["enum"]])
        if value in allowed:
            return None

    if value in {"", "."}:
        if spec["required"]:
            return "required value is missing"
        return None

    if dtype == "integer":
        try:
            int(value)
        except ValueError:
            return f"expected integer, got {value!r}"

    elif dtype == "float":
        try:
            number = float(value)
            if not math.isfinite(number):
                return f"expected finite float, got {value!r}"
        except ValueError:
            return f"expected float, got {value!r}"

    elif dtype == "boolean":
        if value not in BOOLEAN_VALUES:
            return f"expected true/false, got {value!r}"

    elif dtype == "enum":
        allowed = set(enums[spec["enum"]])
        return f"value {value!r} not in enum {spec['enum']}"

    elif dtype == "datetime":
        if "T" not in value:
            return "expected ISO-8601 datetime"

    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", required=True, type=Path)
    parser.add_argument("--table", required=True)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--max-rows", type=int, default=100000)
    args = parser.parse_args()

    schema = json.loads(args.schema.read_text(encoding="utf-8"))

    if args.table not in schema["tables"]:
        raise SystemExit(f"Unknown table: {args.table}")

    table = schema["tables"][args.table]
    specs = table["columns"]
    expected_header = [column["name"] for column in specs]

    errors = []
    rows_checked = 0

    with open_text(args.input) as handle:
        reader = csv.reader(handle, delimiter="\t")

        try:
            header = next(reader)
        except StopIteration:
            raise SystemExit("Input is empty")

        if header != expected_header:
            errors.append(
                "Header mismatch.\n"
                f"Expected: {expected_header}\n"
                f"Observed: {header}"
            )

        for line_number, row in enumerate(reader, start=2):
            if len(row) != len(specs):
                errors.append(
                    f"line {line_number}: expected {len(specs)} fields, "
                    f"got {len(row)}"
                )
            else:
                for value, spec in zip(row, specs):
                    message = validate_value(
                        value,
                        spec,
                        schema["enums"],
                    )
                    if message:
                        errors.append(
                            f"line {line_number}, {spec['name']}: "
                            f"{message}"
                        )

            rows_checked += 1

            if rows_checked >= args.max_rows or len(errors) >= 100:
                break

    print(f"validator_version={VALIDATOR_VERSION}")
    print(f"table={args.table}")
    print(f"rows_checked={rows_checked}")
    print(f"errors={len(errors)}")

    for error in errors[:100]:
        print(error, file=sys.stderr)

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
