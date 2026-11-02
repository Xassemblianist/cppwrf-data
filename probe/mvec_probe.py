#!/usr/bin/env python3
"""Hash of glibc libmvec's 2-lane SSE functions (lane 0) over fixed inputs: the vector functions CPPWRF calls
as WRF's gfortran loops do (src/core/backend.hpp). Equal hashes = the machine rounds them as the reference."""
import ctypes
import hashlib
import math
import platform
import struct

m = ctypes.CDLL("libmvec.so.1")
xs = [math.ldexp(1.0 + i / 7919.0, (i % 61) - 30) for i in range(7919 * 4)]
xs += [1.0 + (i - 5000) * 1e-6 for i in range(10000)] + [0.001 * i for i in range(1, 20001)]
out = {}
for name, args in (("_ZGVbN2v_log", 1), ("_ZGVbN2v_exp", 1), ("_ZGVbN2v_sin", 1), ("_ZGVbN2v_cos", 1),
                   ("_ZGVbN2v_atan", 1), ("_ZGVbN2vv_pow", 2)):
    f = getattr(m, name)
    f.restype = ctypes.c_double
    f.argtypes = [ctypes.c_double] * args
    h = hashlib.sha256()
    for x in xs:
        if name.endswith("exp"):
            x = math.log(x)  # exp's argument range
        y = f(x) if args == 1 else f(x, 0.37 + (x % 3.0))
        h.update(struct.pack("<d", y))
    out[name] = h.hexdigest()[:16]
cpu = next((l.split(":", 1)[1].strip() for l in open("/proc/cpuinfo") if l.startswith("model name")), "?")
print(f"cpu: {cpu}")
print(f"glibc: {platform.libc_ver()}")
for k, v in out.items():
    print(f"{k} {v}")
