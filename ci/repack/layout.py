#!/usr/bin/env python3
"""The packs layout of a data release (data-v2) from the member lists of data-v1 (the scan workflow) and a CPPWRF
source (its vm_data.txt order and its checks' files, ci/needs.py).

  layout.py SCANDIR SRC OUTDIR [--max-pack BYTES] [--small BYTES] [--disk BYTES]

The data as the full suite has it: every tar of SCANDIR's lists unpacked in vm_data.txt's order (tars it does not
name after them, by name), a later tar's member replacing an earlier one's, then the TAR.links tars (directories
left out; hard links as the files they name). Each entry goes to the checks that read it (each suite case and special
check, each output files case, the ideal files test, the differential job, the translator tests); the entries of one
source tar read by the same checks form a pack (cut at --max-pack bytes, default 1.75 GiB, in the source tar's order),
so that a job fetches only what its checks read. Entries no check reads go to packs by top directory. Packs below
--small bytes (default 32 MiB) of one source tar are merged (their checks fetch a little more). The packs of a source
tar are written in one pass over it (ci/repack/repack.py), each uploaded when its last member is written: the bytes of
the packs open at once stay below --disk (default 6 GiB; a pack is cut where needed). A pack is named <source tar>.<hash of its entries>.tar: the same content, the same name.

--previous DIR (an earlier OUTDIR of the same release): its packs whose entries are all unchanged are kept (they
are in the release already; repack.tsv holds only the new packs), so data tars added to vm_data.txt later cost only
their own packs and the packs whose entries they replace.

OUTDIR: repack.tsv (pack, source tar, position in its stream, member name, name in the pack), hardlinks.tsv
(source tar, the file a hard link names), INDEX.tsv (pack, type, name, link,
size: the release's index), expected.tsv (name, type, size, sha256, link, mode, mtime: the data a job unpacks, for
the check of the uploaded release), jobs.json (the source tars in at most 10 groups), report.txt."""
import argparse
import hashlib
import json
import os
import re
import sys
from collections import defaultdict

ap = argparse.ArgumentParser()
ap.add_argument("scandir")
ap.add_argument("src")
ap.add_argument("outdir")
ap.add_argument("--max-pack", type=int, default=int(1.75 * 2 ** 30))
ap.add_argument("--small", type=int, default=32 << 20)
ap.add_argument("--disk", type=int, default=6 << 30)
ap.add_argument("--jobs", type=int, default=10)
ap.add_argument("--after", default="", help="tars not in vm_data.txt in this order after its tars (others by name)")
ap.add_argument("--exclude", default="", help="tars left out (superseded)")
ap.add_argument("--previous", help="the OUTDIR of the release's earlier layout: its packs whose entries are all unchanged are kept")
a = ap.parse_args()
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import needs  # noqa: E402

rep = []


def say(*x):
    rep.append(" ".join(str(y) for y in x))
    print(*x, file=sys.stderr)


# the member lists: tar -> [(type, name, size, mode, mtime, uid, gid, uname, gname, link, sha)] in stream order
lists, ends = defaultdict(list), {}
for fn in sorted(os.listdir(a.scandir)):
    if not fn.endswith(".tsv"):
        continue
    for line in open(os.path.join(a.scandir, fn)):
        f = line.rstrip("\n").split("\t")
        if f[0] == "#END":
            ends[f[1]] = (int(f[2]), int(f[3]))
            continue
        lists[f[0]].append((f[1], f[2], int(f[3]), f[4], f[5], f[6], f[7], f[8], f[9], f[10], f[11]))
for t in lists:
    if t not in ends or ends[t][0] != len(lists[t]):
        sys.exit(f"layout: incomplete list of {t}")

V = os.path.join(a.src, "tests", "verify")
vm = [x.strip() for x in open(os.path.join(V, "vm_data.txt")) if x.strip() and not x.startswith("#")]
order = {t: i for i, t in enumerate(vm)}
after = [t for t in a.after.split(",") if t]
order.update({t: len(vm) + i for i, t in enumerate(after) if t not in order})
excl = {t for t in a.exclude.split(",") if t}
tars = sorted([t for t in lists if t.endswith(".tar") and t not in excl], key=lambda t: (order.get(t, 10 ** 6), t))
links = [t + ".links" for t in tars if t + ".links" in lists]
say("source tars", len(tars), "links tars", len(links), "after vm_data.txt's:", " ".join(t for t in tars if t not in vm),
    "left out:", " ".join(sorted(excl)))

# the full suite's data: name -> (tar, position in the tar, as-type, size, mode, mtime, link, sha)
final = {}
over = defaultdict(int)
for t in tars + links:
    hl = {}
    for i, (ty, name, size, mode, mtime, uid, gid, un, gn, link, sha) in enumerate(lists[t]):
        name = name.rstrip("/")
        if ty == "5":
            continue
        if ty == "1":  # a hard link: the file it names (in this tar, earlier)
            src = hl.get(link.rstrip("/"))
            if src is None:
                sys.exit(f"layout: hard link {name} -> {link} in {t} without its file")
            ty, size, sha, link = "0", src[0], src[1], ""
        elif ty not in ("0", "2"):
            sys.exit(f"layout: member type {ty} of {name} in {t}")
        if ty == "0":
            hl[name] = (size, sha)
        if name in final:
            p = final[name]
            if (p[2], p[3], p[7], p[6]) != (ty, size, sha, link):
                over[(p[0], t)] += 1
        final[name] = (t, i, ty, size, mode, mtime, link, sha)
for (x, y), n in sorted(over.items()):
    say(f"replaced: {n} entries of {x} by {y} (another content)")
# a path below another entry that is a file or a link: the tar extraction of data-v1 would have to go through it
for name in final:
    d = os.path.dirname(name)
    while d:
        if d in final:
            say(f"PROBLEM {name} under the {'link' if final[d][2] == '2' else 'file'} {d}")
        d = os.path.dirname(d)
total = sum(v[3] for v in final.values())
say(f"entries {len(final)}, bytes {total} ({total / 2 ** 30:.1f} GiB; data-v1 {sum(ends[t][1] for t in lists) / 2 ** 30:.1f} GiB)")

# the checks reading each entry
idx = needs.Index(rows=[(v[0], v[2], n, v[6], v[3]) for n, v in final.items()])
sys.path.insert(0, V)
import wrf_suite as w  # noqa: E402

cons = {}
allcases = [c[0] for c in w.CASES if c[1] == "cpu_dp" and not w.slow(c[3])]
allcases += (["straka_wrf"] if "straka_wrf" in w.SPECIAL else []) + [f"restart_{t}_fp64" for t, _, _ in w.RESTARTS]
for c in allcases:
    cons["case:" + c] = needs.case_entries(a.src, c, idx)
for c in [c[0] for c in w.CASES if c[1] != "cpu_dp" or w.slow(c[3])]:  # the GPU / slow cases: where they read nothing else
    try:
        cons["other:" + c] = needs.case_entries(a.src, c, idx)
    except Exception as e:  # noqa: BLE001
        say("no files for", c, e)
for n, dirs in needs.files_cases(a.src):
    cons["files:" + n] = needs.top_entries(dirs, idx)
cons["idealfiles"] = set().union(*[cons.get("case:" + c[0], set()) for c in w.CASES
                                   if c[0].startswith("ideal_") and c[1] == "cpu_dp"])
cons["diff"] = needs.diff_entries(idx)
cons["checks"] = needs.top_entries(needs.checks_dirs(a.src), idx)
for k, v in cons.items():
    if not v and not k.startswith("other:"):
        say("PROBLEM no entries for", k)
reader = defaultdict(set)
for k, v in cons.items():
    for e in v:
        reader[e].add(k)
unread = [n for n in final if not reader[n]]
say(f"read by a CPU check: {sum(final[n][3] for n in final if any(not k.startswith('other:') for k in reader[n])) / 2 ** 30:.1f} GiB;"
    f" by none: {len(unread)} entries, {sum(final[n][3] for n in unread) / 2 ** 30:.1f} GiB")

# packs of an earlier layout (--previous) whose entries are all still there, unchanged: kept as they are (in the release)
keep = {}
if a.previous:
    pv, pp = {}, defaultdict(list)
    for line in open(os.path.join(a.previous, "expected.tsv")):
        f = line.rstrip("\n").split("\t")
        pv[f[0]] = (f[1], int(f[2]), f[3], f[4], f[5], f[6])
    for line in open(os.path.join(a.previous, "INDEX.tsv")):
        f = line.rstrip("\n").split("\t")
        pp[f[0]].append(f[2])
    for p, ns in pp.items():
        if all(n in final and (final[n][2], final[n][3], final[n][7], final[n][6], final[n][4], final[n][5]) == pv[n] for n in ns):
            keep[p] = ns
    say(f"kept from the earlier layout: {len(keep)} of {len(pp)} packs, {sum(len(ns) for ns in keep.values())} entries")
kept = {n for ns in keep.values() for n in ns}

# groups: (source tar, the CPU checks reading it) or (source tar, top directory) for the rest
group = {}
for n, v in final.items():
    if n in kept:
        continue
    cpu = frozenset(k for k in reader[n] if not k.startswith("other:"))
    group[n] = (v[0], cpu) if cpu else (v[0], frozenset(reader[n]) or "top:" + needs.top_of(n))
bysrc = defaultdict(lambda: defaultdict(list))  # source tar -> group -> names in stream order
for n in sorted(group, key=lambda n: (final[n][0], final[n][1])):
    bysrc[final[n][0]][group[n]].append(n)


def gsize(ns):
    return sum(final[n][3] for n in ns)


# small groups of a source tar merged: with the group of the most shared readers, else into one rest group
packs = []  # (source tar, [names])
for t in tars + links:
    gs = bysrc.get(t, {})
    big = {g: ns for g, ns in gs.items() if gsize(ns) >= a.small}
    small = sorted([(g, ns) for g, ns in gs.items() if gsize(ns) < a.small], key=lambda x: -gsize(x[1]))
    rest = []
    for g, ns in small:
        best = None
        if isinstance(g[1], frozenset) and g[1]:
            cand = [(len(g[1] & h[1]) / len(g[1] | h[1]), h) for h in big if isinstance(h[1], frozenset) and h[1]]
            cand = [x for x in cand if x[0] >= 0.5]
            if cand:
                best = max(cand, key=lambda x: x[0])[1]
        if best is not None:
            big[best] = big[best] + ns
        else:
            rest += ns
    if rest:
        big[(t, "rest")] = rest
    for g, ns in big.items():
        ns.sort(key=lambda n: final[n][1])
        cur, sz = [], 0
        for n in ns:
            if cur and sz + final[n][3] > a.max_pack:
                packs.append((t, cur))
                cur, sz = [], 0
            cur.append(n)
            sz += final[n][3]
        packs.append((t, cur))


# the disk a source tar's pass needs: the packs open at once (started, not finished) hold their bytes so far
def peak(t, ps):
    first = {i: final[ns[0]][1] for i, (_, ns) in enumerate(ps)}
    last = {i: final[ns[-1]][1] for i, (_, ns) in enumerate(ps)}
    pos = {final[n][1]: (i, final[n][3]) for i, (_, ns) in enumerate(ps) for n in ns}
    cur, best, open_ = 0, 0, defaultdict(int)
    for p in sorted(pos):
        i, s = pos[p]
        open_[i] += s
        cur += s
        best = max(best, cur)
        if p == last[i]:
            cur -= open_.pop(i)
    return best


out = []
for t in tars + links:
    ps = [p for p in packs if p[0] == t]
    while peak(t, ps) > a.disk:  # cut the pack that has been open longest at its middle
        i = max(range(len(ps)), key=lambda i: final[ps[i][1][-1]][1] - final[ps[i][1][0]][1])
        ns = ps[i][1]
        if len(ns) < 2:
            sys.exit(f"layout: {t} cannot keep below --disk")
        ps[i:i + 1] = [(t, ns[:len(ns) // 2]), (t, ns[len(ns) // 2:])]
    say(f"{t}: {len(ps)} packs, {gsize([n for _, ns in ps for n in ns]) / 2 ** 30:.2f} GiB, disk peak {peak(t, ps) / 2 ** 30:.2f} GiB")
    out += ps

# names: <source tar stem>.<hash>.tar, the hash of the pack's entries (name, type, size, sha256, link, mode, time):
# a pack with the same content keeps its name in a later layout
names = []
for t, ns in out:
    stem = re.sub(r"\.tar(\.links)?$", "", t) + (".links" if t.endswith(".links") else "")
    h = hashlib.sha256("".join(f"{n}\t{final[n][2]}\t{final[n][3]}\t{final[n][7]}\t{final[n][6]}\t{final[n][4]}\t{final[n][5]}\n"
                               for n in ns).encode()).hexdigest()[:12]
    names.append(f"{stem}.{h}.tar")
if len(set(names)) != len(names) or set(names) & set(keep):
    sys.exit("layout: two packs with the same name")
os.makedirs(a.outdir, exist_ok=True)
pack_of = {n: p for p, ns in keep.items() for n in ns}
with open(os.path.join(a.outdir, "repack.tsv"), "w") as f:
    for nm, (t, ns) in zip(names, out):
        for n in ns:
            pack_of[n] = nm
            f.write(f"{nm}\t{t}\t{final[n][1]}\t{lists[t][final[n][1]][1]}\t{n}\n")
with open(os.path.join(a.outdir, "hardlinks.tsv"), "w") as f:  # the files hard links name, kept by repack.py
    for t in lists:
        for x in lists[t]:
            if x[0] == "1":
                f.write(f"{t}\t{x[9]}\n")
with open(os.path.join(a.outdir, "INDEX.tsv"), "w") as f:
    for n in sorted(final):
        v = final[n]
        f.write(f"{pack_of[n]}\t{v[2]}\t{n}\t{v[6]}\t{v[3]}\n")
with open(os.path.join(a.outdir, "expected.tsv"), "w") as f:
    for n in sorted(final):
        v = final[n]
        f.write(f"{n}\t{v[2]}\t{v[3]}\t{v[7]}\t{v[6]}\t{v[4]}\t{v[5]}\n")
# the source tars in jobs balanced by bytes (each source tar is streamed once, by one job)
g = [[0, i, []] for i in range(a.jobs)]
for t in sorted({t for t, _ in out}, key=lambda t: -ends[t][1]):
    x = min(g)
    x[0] += ends[t][1]
    x[2].append(t)
json.dump({"include": [{"g": i, "tars": ",".join(ts)} for _, i, ts in sorted(g, key=lambda x: x[1]) if ts]},
          open(os.path.join(a.outdir, "jobs.json"), "w"))
with open(os.path.join(a.outdir, "packs.txt"), "w") as f:  # NAME bytes source-tar entries (kept: "kept")
    for nm, (t, ns) in zip(names, out):
        f.write(f"{nm} {gsize(ns)} {t} {len(ns)}\n")
    for nm, ns in sorted(keep.items()):
        f.write(f"{nm} {gsize(ns)} kept {len(ns)}\n")
names += sorted(keep)
out += [("kept", keep[p]) for p in sorted(keep)]
psz = [gsize(ns) for _, ns in out]
say(f"packs {len(out)}, bytes {sum(psz) / 2 ** 30:.1f} GiB, parts (512 MiB) {sum(max(1, -(-s // (512 << 20))) for s in psz)}")
# what each check fetches against data-v1
bypack = {nm: s for nm, s in zip(names, psz)}
for k in sorted(cons):
    if k.startswith("other:"):
        continue
    ps = {pack_of[e] for e in cons[k]}
    need = gsize(cons[k])
    got = sum(bypack[p] for p in ps)
    rep.append(f"check {k}: {len(ps)} packs {got / 2 ** 30:.2f} GiB (reads {need / 2 ** 30:.2f} GiB)")
open(os.path.join(a.outdir, "report.txt"), "w").write("\n".join(rep) + "\n")
