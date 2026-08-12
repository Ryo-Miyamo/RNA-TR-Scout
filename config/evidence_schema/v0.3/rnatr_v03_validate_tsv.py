#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import sys
from pathlib import Path

TRUE = {"true", "false"}
INT_TYPES = {"integer"}
FLOAT_TYPES = {"float"}
MISSING = "."

def open_text(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", newline="")
    return path.open("r", encoding="utf-8", newline="")

def validate_value(value: str, spec: dict, enums: dict) -> str | None:
    if value == MISSING or value == "":
        if spec["required"]:
            return "required value is missing"
        return None

    dtype = spec["type"]

    if dtype in INT_TYPES:
        try:
            int(value)
        except ValueError:
            return f"expected integer, got {value!r}"
    elif dtype in FLOAT_TYPES:
        try:
            number = float(value)
            if not math.isfinite(number):
                return f"expected finite float, got {value!r}"
        except ValueError:
            return f"expected float, got {value!r}"
    elif dtype == "boolean":
        if value not in TRUE:
            return f"expected true/false, got {value!r}"
    elif dtype == "enum":
        allowed = set(enums[spec["enum"]])
        if value not in allowed:
            return f"value {value!r} not in enum {spec['enum']}"
    elif dtype == "datetime":
        if "T" not in value:
            return "expected ISO-8601 datetime"

    return None

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate RNA-TR-Scout v0.3 TSV headers and selected values."
    )
    parser.add_argument("--schema", required=True, type=Path)
    parser.add_argument("--table", required=True)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--max-rows", type=int, default=100000)
    args = parser.parse_args()

    schema = json.loads(args.schema.read_text(encoding="utf-8"))
    tables = schema["tables"]

    if args.table not in tables:
        raise SystemExit(f"Unknown table: {args.table}")

    table = tables[args.table]
    specs = table["columns"]
    expected_header = [c["name"] for c in specs]

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

        for line_no, row in enumerate(reader, start=2):
            if len(row) != len(specs):
                errors.append(
                    f"line {line_no}: expected {len(specs)} fields, got {len(row)}"
                )
            else:
                for value, spec in zip(row, specs):
                    message = validate_value(value, spec, schema["enums"])
                    if message:
                        errors.append(
                            f"line {line_no}, {spec['name']}: {message}"
                        )

            rows_checked += 1
            if rows_checked >= args.max_rows or len(errors) >= 100:
                break

    print(f"table={args.table}")
    print(f"rows_checked={rows_checked}")
    print(f"errors={len(errors)}")

    for error in errors[:100]:
        print(error, file=sys.stderr)

    return 1 if errors else 0

if __name__ == "__main__":
    raise SystemExit(main())
