#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,gzip
from pathlib import Path

MISSING={"",".","NA","N/A","None","null","nan"}

def read(path):
    op=gzip.open if path.suffix==".gz" else open
    with op(path,"rt",encoding="utf-8",newline="") as f:
        return list(csv.DictReader(f,delimiter="\t"))

def validate_pair(row,side,line):
    b=row[f"{side}_flank_unique"]
    s=row[f"{side}_flank_uniqueness_status"]
    if s=="NOT_ASSESSED":
        if b not in MISSING:
            raise SystemExit(f"line {line}: {side} uniqueness boolean must be missing when NOT_ASSESSED")
    elif s=="ASSESSED_UNIQUE":
        if b!="true":
            raise SystemExit(f"line {line}: {side} ASSESSED_UNIQUE requires boolean true")
    elif s=="ASSESSED_NONUNIQUE":
        if b!="false":
            raise SystemExit(f"line {line}: {side} ASSESSED_NONUNIQUE requires boolean false")
    else:
        raise SystemExit(f"line {line}: invalid {side} flank uniqueness status {s!r}")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",type=Path,required=True)
    args=ap.parse_args()
    rows=read(args.input)
    required={
        "left_flank_unique","right_flank_unique",
        "left_flank_uniqueness_status","right_flank_uniqueness_status",
    }
    if rows:
        missing=required-set(rows[0])
        if missing:
            raise SystemExit(f"missing flank uniqueness columns: {sorted(missing)}")
    for line,row in enumerate(rows,start=2):
        validate_pair(row,"left",line)
        validate_pair(row,"right",line)
    print(f"RNATR_V042_FLANK_UNIQUENESS_VALIDATION_PASS\trows={len(rows)}")

if __name__=="__main__":
    main()
