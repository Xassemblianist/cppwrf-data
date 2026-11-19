#!/usr/bin/env python3
"""repack.py SOURCE REPACK.tsv OUTDIR < source tar stream: the packs of one data-v1 tar (ci/repack/layout.py's
repack.tsv rows of SOURCE: pack, source tar, member, name in the pack). Each member goes to its pack with its header
(mode, time, owner) under its name in the pack; a hard link as the file it names (its content kept from earlier in the
stream). A pack is closed when its last member is written and handed to `UPLOAD` (default ci/repack/upload.sh: the
parts, their sha256, the upload), at most 2 at once, the stream waiting while the packs on disk exceed --disk bytes.
Writes OUTDIR/members_SOURCE.tsv (pack, type, name, size, sha256 of what was written) and checks that every row was
written."""
import argparse
import hashlib
import io
import os
import subprocess
import sys
import tarfile
import threading
import time
from collections import defaultdict

ap = argparse.ArgumentParser()
ap.add_argument("source")
ap.add_argument("repack")
ap.add_argument("outdir")
ap.add_argument("--work", default="packs")
ap.add_argument("--hardlinks", default="")
ap.add_argument("--disk", type=int, default=7 << 30)
ap.add_argument("--upload", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "upload.sh"))
a = ap.parse_args()

rows = {}  # position of the member in the source stream -> (member name, pack, name in the pack)
left = defaultdict(int)  # pack -> members still to write
for line in open(a.repack):
    p, t, i, m, n = line.rstrip("\n").split("\t")
    if t == a.source:
        rows[int(i)] = (m, p, n)
        left[p] += 1
os.makedirs(a.work, exist_ok=True)
os.makedirs(a.outdir, exist_ok=True)
log = open(os.path.join(a.outdir, f"members_{a.source}.tsv"), "w")
open_ = {}  # pack -> TarFile
ondisk = {}  # pack -> bytes on disk (open or uploading)
lock = threading.Lock()
sem = threading.Semaphore(2)
threads, failed = [], []


def upload(p):
    with sem:
        r = subprocess.run(["bash", a.upload, os.path.join(a.work, p)])
    with lock:
        ondisk.pop(p, None)
        if r.returncode:
            failed.append(p)


def close(p):
    open_.pop(p).close()
    with lock:
        ondisk[p] = os.path.getsize(os.path.join(a.work, p))
    th = threading.Thread(target=upload, args=(p,))
    th.start()
    threads.append(th)


class Hashing:
    def __init__(self, f, keep):
        self.f, self.h, self.keep, self.n = f, hashlib.sha256(), keep, 0

    def read(self, k=-1):
        b = self.f.read(k)
        self.h.update(b)
        self.n += len(b)
        if self.keep is not None:
            self.keep.append(b)
        return b


hl_names = set()  # the files that hard links of this tar name (their content kept for the links)
if a.hardlinks and os.path.exists(a.hardlinks):
    for line in open(a.hardlinks):
        t, n = line.rstrip("\n").split("\t")
        if t == a.source:
            hl_names.add(n.rstrip("/"))
content = {}
src = tarfile.open(fileobj=sys.stdin.buffer, mode="r|")
for pos, m in enumerate(src):
    name = m.name.rstrip("/")
    row = rows.pop(pos, None)
    if row is not None and row[0] != m.name:
        sys.exit(f"repack: member {pos} of {a.source} is {m.name}, not {row[0]}")
    keep = [] if m.isreg() and name in hl_names else None
    if row is None:
        if keep is not None:
            f = Hashing(src.extractfile(m), keep)
            while f.read(8 << 20):
                pass
            content[name] = b"".join(keep)
        continue
    _, p, n = row
    while True:  # the packs on disk: below --disk (the stream waits for the uploads)
        with lock:
            busy = sum(ondisk.values())
        if not ondisk or busy + sum(os.path.getsize(os.path.join(a.work, q)) for q in open_) < a.disk:
            break
        time.sleep(1)
    if p not in open_:
        open_[p] = tarfile.open(os.path.join(a.work, p), "w", format=tarfile.GNU_FORMAT)
    h = tarfile.TarInfo(n)
    h.mode, h.mtime, h.uid, h.gid, h.uname, h.gname = m.mode, m.mtime, m.uid, m.gid, m.uname, m.gname
    if m.issym():
        h.type, h.linkname = tarfile.SYMTYPE, m.linkname
        open_[p].addfile(h)
        log.write(f"{p}\t2\t{n}\t0\t\t{m.linkname}\n")
    elif m.isreg():
        h.type, h.size = tarfile.REGTYPE, m.size
        r = Hashing(src.extractfile(m), keep)
        open_[p].addfile(h, r)
        if r.n != m.size:
            sys.exit(f"repack: {name}: {r.n} bytes read, {m.size} in the header")
        log.write(f"{p}\t0\t{n}\t{m.size}\t{r.h.hexdigest()}\t\n")
    elif m.islnk():
        data = content.get(m.linkname.rstrip("/"))
        if data is None:
            sys.exit(f"repack: hard link {name} -> {m.linkname} without its file's content")
        h.type, h.size = tarfile.REGTYPE, len(data)
        open_[p].addfile(h, io.BytesIO(data))
        log.write(f"{p}\t0\t{n}\t{len(data)}\t{hashlib.sha256(data).hexdigest()}\t\n")
    else:
        sys.exit(f"repack: {name}: member type {m.type}")
    if keep is not None:
        content[name] = b"".join(keep)
    left[p] -= 1
    if left[p] == 0:
        close(p)
src.close()
while sys.stdin.buffer.read(1 << 20):
    pass
for th in threads:
    th.join()
log.close()
bad = [p for p, n in left.items() if n] + failed
if rows:
    print(f"repack: {len(rows)} members of {a.source} not in the stream: {list(rows)[:5]}", file=sys.stderr)
if bad or rows:
    print(f"repack: packs not finished or not uploaded: {bad}", file=sys.stderr)
    sys.exit(1)
