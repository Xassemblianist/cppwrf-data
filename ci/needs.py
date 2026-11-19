"""The files a CPPWRF suite check reads from the unpacked data, for a data release in the packs layout (data-v2:
ci/repack/layout.py), where each file is in exactly one pack and a job fetches only the packs of its checks' files.

Index(path): the release's INDEX.tsv (pack, type, name, link target[, size]): every file and link of the data as
the full suite has it (every tar of data-v1 unpacked in vm_data.txt's order, then the TAR.links tars).

case_entries(src, name, idx): the entries a suite case (or special check) of the CPPWRF source `src` reads, from
tests/verify/case_data.py's model of its files (needs()):
  - every entry directly in the directory of each reference file it names (the wrfout files, and so the
    directory's namelist.input, myoutfields.txt, auxhist3 and wrfrst files that wrf_suite.py globs there);
  - each file its configuration and --set list name, and of each directory they name every entry directly in it
    but WRF's outputs (wrfout / wrfrst / auxhist / rsl / log; a drop-in case's run directory as well);
  - links followed: the target of every link among them (a link to a directory: every entry directly in it), and
    the links on the way of every path (a run directory that is a link to another).
top_entries(dirs, idx): every entry under the top directories `dirs` (wrf_runs/run_X), following links into other
top directories (plan.py's tars_for_dirs).
"""
import os
import re
import sys
from collections import defaultdict

OUTPUT = re.compile(r"(wrfout|wrfrst|auxhist\d+)_d\d\d_.*|rsl\..*|.*\.log")


class Index:
    def __init__(self, path=None, rows=None):
        self.ent = {}  # name -> (type, link, pack, size)
        self.kids = defaultdict(set)  # directory -> names of the entries directly in it
        self.tops = defaultdict(set)  # top directory (first two components) -> names
        for r in (rows if rows is not None else self._read(path)):
            self.add(*r)

    @staticmethod
    def _read(path):
        for line in open(path):
            f = line.rstrip("\n").split("\t")
            if len(f) >= 4 and f[1] != "5":
                yield f[0], f[1], f[2], f[3], int(f[4]) if len(f) > 4 and f[4] else 0

    def add(self, pack, typ, name, link, size=0):
        name = name.rstrip("/")
        self.ent[name] = (typ, link, pack, size)
        self.kids[os.path.dirname(name)].add(name)
        self.tops["/".join(name.split("/")[:2])].add(name)

    def target(self, name):
        typ, link, _, _ = self.ent[name]
        if typ != "2" or not link or link.startswith("/"):
            return None
        return os.path.normpath(os.path.join(os.path.dirname(name), link))

    def resolve(self, path, via):
        """`path` with every link on its way followed (the links go to `via`); None if it leads nowhere."""
        parts, cur, n = path.split("/"), "", 0
        while parts:
            cur = parts.pop(0) if not cur else cur + "/" + parts.pop(0)
            if cur in self.ent and self.ent[cur][0] == "2" and parts:  # a link on the way: a directory link
                via.add(cur)
                t = self.target(cur)
                n += 1
                if t is None or n > 40:
                    return None
                cur = t
        return cur

    def closure(self, names):
        """`names` with the targets of their links (a directory's entries directly in it), recursively."""
        out, todo = set(), list(names)
        while todo:
            e = todo.pop()
            if e in out or e not in self.ent:
                continue
            out.add(e)
            t = self.target(e)
            if t is None:
                continue
            via = set()
            r = self.resolve(t, via)
            todo += list(via)
            if r is None:
                continue
            if r in self.ent:
                todo.append(r)
            else:
                todo += list(self.kids.get(r, ()))
        return out

    def dir_or_file(self, path, outputs=True):
        """The entries of a data path: the entry itself, or a directory's entries directly in it (WRF's outputs only
        with `outputs`), with the links on the way."""
        via = set()
        r = self.resolve(path, via)
        out = set(via)
        if r is None:
            return out
        if r in self.ent and r not in self.kids:
            out.add(r)
        for e in self.kids.get(r, ()):
            if outputs or not OUTPUT.fullmatch(os.path.basename(e)):
                out.add(e)
        return out


def case_entries(src, name, idx, _cd={}):
    if "cd" not in _cd:
        sys.path.insert(0, os.path.join(src, "tests", "verify"))
        import case_data  # noqa: E402
        _cd["cd"] = case_data
    files, dirs = _cd["cd"].needs(name)
    want = set()
    for p in files:
        if p:
            want |= idx.dir_or_file(os.path.dirname(p), outputs=True)
            if "*" not in p:
                want |= idx.dir_or_file(p)
    for d in dirs:
        if d:
            want |= idx.dir_or_file(d, outputs=False)
    return idx.closure(want)


def top_of(name):
    return "/".join(name.split("/")[:2])


def top_entries(dirs, idx):
    seen, todo, out = set(), list(dirs), set()
    while todo:
        d = todo.pop()
        if d in seen:
            continue
        seen.add(d)
        for e in idx.tops.get(d, ()):
            out.add(e)
            t = idx.target(e)
            if t is not None:
                todo.append(top_of(t))
    return out


def files_cases(src):
    """[(case, top directories)] of run_wrf_files_test.sh's CASES (plan.py's reading: run, restart and resumed
    directories, the directories its line and its configuration name)."""
    V = os.path.join(src, "tests", "verify")
    txt = open(os.path.join(V, "run_wrf_files_test.sh")).read()
    block = re.search(r'^CASES="\n(.*?)^"', txt, re.S | re.M).group(1)
    out = []
    for line in block.splitlines():
        f = line.split("|")
        if len(f) < 4:
            continue
        dirs = set()
        for x in f[2:4]:
            m = re.match(r"\$R/([^/]+)", x)
            if m:
                dirs.add(f"wrf_runs/{m.group(1)}")
                base = re.sub(r"^(run|rst|rsm)_", "", m.group(1))
                dirs |= {f"wrf_runs/rst_{base}", f"wrf_runs/rsm_{base}"}
        for m in re.finditer(r"\$R/([^/ ]+)", f[4] if len(f) > 4 else ""):
            dirs.add(f"wrf_runs/{m.group(1)}")
        cfg = os.path.join(src, f[1])
        if os.path.exists(cfg):
            for m in re.finditer(r"\$\{CPPWRF_WRF_RUNS\}/([^/\s]+)", open(cfg).read()):
                dirs.add(f"wrf_runs/{m.group(1)}")
        out.append((f[0], dirs))
    return out


DIFF_DIRS = {f"wrf_runs/{d}" for d in ("run_R0_r8", "run_P4_r8", "run_P7_r8", "run_P8_r8", "wrf_run")}


def diff_entries(idx):
    """The differential and ctest job's entries: its run directories (plan.py's), the WRF run files of the
    differential tests (wrf_runs_diff/) and what the data adds to WRF's build trees (wrf_build/), and WRF's ideal
    sounding that ctests such as restart_alarm read (${CPPWRF_WRF_REF}/run_qss/input_sounding)."""
    tops = set(DIFF_DIRS) | {t for t in idx.tops if t.split("/")[0] in ("wrf_runs_diff", "wrf_build")}
    return top_entries(tops, idx) | idx.closure(idx.dir_or_file("wrf_ref/run_qss/input_sounding"))


def checks_dirs(src):
    """The run directories whose namelists the translator tests read (plan.py's)."""
    tt = open(os.path.join(src, "tests", "tools", "test_wrf2cppwrf.py")).read()
    dirs = {f"wrf_runs/{m}" for m in re.findall(r'wrf_runs_path\(\s*"([^"/]+)/', tt)}
    dirs |= {f"wrf_runs/{m}" for m in re.findall(r'_compare_configs\(\s*"([^"/]+)/', tt)}
    dirs |= {f"wrf_ref/{m}" for m in re.findall(r'wrf_ref_path\(\s*"([^"/]+)/', tt)}
    return dirs
