#!/usr/bin/env python3
"""scan.py TAR < tar stream: one line per member, tab-separated:
  tar type name size mode mtime uid gid uname gname linkname sha256
(type: tarfile's type character, 0 for a regular file; sha256 of the content of regular files, empty otherwise), then
"#END TAR members bytes" (bytes: the stream's length, which must be the tar's size in TARS.txt)."""
import hashlib
import sys
import tarfile


class Counter:
    def __init__(self, f):
        self.f, self.n = f, 0

    def read(self, k=-1):
        b = self.f.read(k)
        self.n += len(b)
        return b


name = sys.argv[1]
src = Counter(sys.stdin.buffer)
out = sys.stdout
n = 0
with tarfile.open(fileobj=src, mode="r|") as t:
    for m in t:
        h = ""
        if m.isreg():
            d = hashlib.sha256()
            f = t.extractfile(m)
            while True:
                b = f.read(8 << 20)
                if not b:
                    break
                d.update(b)
            h = d.hexdigest()
        ty = m.type.decode() if m.type != tarfile.AREGTYPE else "0"
        out.write("\t".join([name, ty, m.name, str(m.size), oct(m.mode), str(int(m.mtime)), str(m.uid), str(m.gid),
                             m.uname, m.gname, m.linkname, h]) + "\n")
        n += 1
while src.read(1 << 20):  # the rest of the stream (end blocks, padding)
    pass
out.write(f"#END\t{name}\t{n}\t{src.n}\n")
