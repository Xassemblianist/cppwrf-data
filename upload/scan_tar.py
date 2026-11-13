#!/usr/bin/env python3
"""Scan a tar stream (stdin) for personal traces: home paths, the user / host name, the e-mail name.
Writes one line per hit: KIND MEMBER PATTERN CONTEXT; KIND = text | binary | netcdf | symlink | name.
Last line: SUMMARY members=N bytes=B hits_text=.. hits_binary=.. hits_netcdf=.. hits_symlink=.. hits_name=.. unames=..
"""
import re
import sys
import tarfile

PAT = re.compile(rb"/home/|ostriquetrum|omerkaan")
CH = 8 << 20


def kind_of(head):
    if head[:4] in (b"CDF\x01", b"CDF\x02", b"CDF\x05") or head[:8] == b"\x89HDF\r\n\x1a\n":
        return "netcdf"
    if b"\x00" in head[:4096]:
        return "binary"
    return "text"


def main():
    out = open(sys.argv[1], "w")
    counts = {k: 0 for k in ("text", "binary", "netcdf", "symlink", "name")}
    unames = set()
    n = nbytes = 0
    names = open(sys.argv[1][:-4] + ".names", "w")
    with tarfile.open(fileobj=sys.stdin.buffer, mode="r|") as tf:
        for m in tf:
            n += 1
            unames.add(f"{m.uname}:{m.gname}")
            names.write(f"{m.type.decode() if isinstance(m.type, bytes) else m.type}\t{m.size}\t{m.name}\t{m.linkname}\n")
            if PAT.search(m.name.encode()):
                counts["name"] += 1
                out.write(f"name {m.name} - -\n")
            if m.issym() or m.islnk():
                if PAT.search(m.linkname.encode()):
                    counts["symlink"] += 1
                    out.write(f"symlink {m.name} -> {m.linkname}\n")
                continue
            if not m.isfile():
                continue
            f = tf.extractfile(m)
            tail = b""
            first = True
            kind = "text"
            hits = 0
            while True:
                b = f.read(CH)
                if not b:
                    break
                nbytes += len(b)
                if first:
                    kind = kind_of(b)
                    first = False
                buf = tail + b
                for h in PAT.finditer(buf):
                    if h.end() <= len(tail):
                        continue
                    hits += 1
                    if hits <= 5:
                        ctx = buf[max(0, h.start() - 40):h.end() + 60]
                        out.write(f"{kind} {m.name} {h.group().decode()} {ctx!r}\n")
                tail = buf[-32:]
            if hits:
                counts[kind] += 1
                if hits > 5:
                    out.write(f"{kind} {m.name} ... {hits} hits in all\n")
            out.flush()
    out.write(f"SUMMARY members={n} bytes={nbytes} " + " ".join(f"hits_{k}={v}" for k, v in counts.items())
              + f" unames={','.join(sorted(unames))}\n")
    out.close()
    names.close()


main()
