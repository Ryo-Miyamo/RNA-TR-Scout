#!/usr/bin/env python3
from __future__ import annotations
import argparse,subprocess,sys
from pathlib import Path
def main():
    ap=argparse.ArgumentParser();ap.add_argument("--package-dir",type=Path,required=True);args=ap.parse_args()
    here=Path(__file__).resolve().parent
    subprocess.run([sys.executable,str(here/"rnatr_v04_validate_package.py"),"--package-dir",str(args.package_dir)],check=True)
    subprocess.run([sys.executable,str(here/"rnatr_v041_validate_locus_aggregation.py"),"--package-dir",str(args.package_dir)],check=True)
    print("RNATR_V041_PACKAGE_VALIDATION_PASS")
if __name__=="__main__":main()
