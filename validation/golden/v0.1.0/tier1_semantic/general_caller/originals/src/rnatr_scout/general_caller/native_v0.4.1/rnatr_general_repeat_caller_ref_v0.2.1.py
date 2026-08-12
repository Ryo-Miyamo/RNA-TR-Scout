from __future__ import annotations
import ctypes
import importlib.util
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
BASE_PATH=HERE/"rnatr_general_repeat_caller_ref_v0.2.1_base.py"
LIB_PATH=HERE/"librnatr_native_periodic_kernel_v0.1.0.so"

def _load_base():
    spec=importlib.util.spec_from_file_location("rnatr_general_v021_native_base",BASE_PATH)
    mod=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=mod
    spec.loader.exec_module(mod)
    return mod

base=_load_base()

class _Result(ctypes.Structure):
    _fields_=[
        ("score",ctypes.c_double),
        ("read_start",ctypes.c_int32),
        ("read_end",ctypes.c_int32),
        ("aligned_read_bp",ctypes.c_int32),
        ("motif_path_bp",ctypes.c_int32),
        ("matches",ctypes.c_int32),
        ("mismatches",ctypes.c_int32),
        ("insertions",ctypes.c_int32),
        ("deletions",ctypes.c_int32),
        ("purity",ctypes.c_double),
        ("phase_start",ctypes.c_int32),
        ("phase_end",ctypes.c_int32),
        ("ops_len",ctypes.c_int32),
    ]

_lib=ctypes.CDLL(str(LIB_PATH))
_align=_lib.rnatr_cyclic_local_align
_align.argtypes=[
    ctypes.c_char_p,ctypes.c_int32,ctypes.c_char_p,ctypes.c_int32,
    ctypes.c_double,ctypes.c_double,ctypes.c_double,ctypes.c_double,
    ctypes.c_int32,ctypes.POINTER(_Result),ctypes.c_char_p,ctypes.c_int32,
]
_align.restype=ctypes.c_int

_agreement=_lib.rnatr_periodic_agreement_oriented
_agreement.argtypes=[ctypes.c_char_p,ctypes.c_int32,ctypes.c_char_p,ctypes.c_int32]
_agreement.restype=ctypes.c_double

_lps=_lib.rnatr_exact_periodic_lps_oriented
_lps.argtypes=[ctypes.c_char_p,ctypes.c_int32,ctypes.c_char_p,ctypes.c_int32]
_lps.restype=ctypes.c_int32

def cyclic_local_align(seq:str,motif:str,match:float=2.0,mismatch:float=-3.0,
                       ins:float=-3.0,dele:float=-3.0,max_del:int=2):
    seq=seq.upper();motif=motif.upper()
    if not seq or not motif:
        raise ValueError("sequence and motif must be non-empty")
    cap=len(seq)*(max_del+1)+1
    ops=ctypes.create_string_buffer(cap)
    out=_Result()
    rc=_align(seq.encode("ascii"),len(seq),motif.encode("ascii"),len(motif),
              match,mismatch,ins,dele,max_del,ctypes.byref(out),ops,cap)
    if rc!=0:
        raise RuntimeError(f"native cyclic_local_align failed rc={rc}")
    return base.Alignment(out.score,out.read_start,out.read_end,out.aligned_read_bp,
                          out.motif_path_bp,out.matches,out.mismatches,out.insertions,
                          out.deletions,out.purity,out.phase_start,out.phase_end,
                          motif,ops.value.decode("ascii"))

def _periodic_agreement(segment:str,motif:str):
    segment=segment.upper();motif=motif.upper()
    if not segment or not motif:
        return 0.0,motif
    best=(-1.0,motif)
    for oriented in base._ordered_orientations(motif):
        sc=float(_agreement(segment.encode("ascii"),len(segment),
                            oriented.encode("ascii"),len(oriented)))
        if sc>best[0]:
            best=(sc,oriented)
    return best

def exact_periodic_lps(segment:str,motif:str)->int:
    segment=segment.upper();motif=motif.upper()
    if not segment or not motif:
        return 0
    return int(_lps(segment.encode("ascii"),len(segment),
                    motif.encode("ascii"),len(motif)))

base.cyclic_local_align=cyclic_local_align
base._periodic_agreement=_periodic_agreement
base.exact_periodic_lps=exact_periodic_lps

for _name in dir(base):
    if not _name.startswith("__"):
        globals()[_name]=getattr(base,_name)

globals()["cyclic_local_align"]=cyclic_local_align
globals()["_periodic_agreement"]=_periodic_agreement
globals()["exact_periodic_lps"]=exact_periodic_lps
