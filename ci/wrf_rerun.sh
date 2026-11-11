#!/usr/bin/env bash
# wrf_rerun.sh DATA OUT DIR:FLAVOR ... : WRF again in a copy of each reference directory DATA/DIR (its namelist.input
# and inputs unchanged: links; its WRF outputs left out) with /w/wrf/WRF-4.8.0-FLAVOR/main/wrf.exe, then the MD5 of
# every wrfout / wrfrst / auxhist file it wrote against the reference's: one line "SAME DIR FILE MD5" or
# "DIFF DIR FILE MD5 REFMD5" (or "MISSING DIR FILE", "WRF-FAILED DIR") per file into OUT/rerun.log, which ends with
# "exit N" (0: every file the same).
set -uo pipefail
DATA=$1 OUT=$2; shift 2
mkdir -p "$OUT"; L=$OUT/rerun.log; : > "$L"
bad=0
run_one() {
  local dir=${1%%:*} fl=${1##*:} src=$DATA/${1%%:*} R=$OUT/rerun/${1%%:*}
  rm -rf "$R"; mkdir -p "$R"
  for f in "$src"/*; do
    b=$(basename "$f")
    case $b in wrfout_*|wrfrst_*|auxhist*|rsl.*|*.log|*.exe|namelist.output|steps) ;; *) [ -d "$f" ] || ln -s "$(readlink -f "$f")" "$R/$b" ;; esac
  done
  ln -sfn "/w/wrf/WRF-4.8.0-$fl/main/wrf.exe" "$R/wrf.exe"
  (cd "$R" && OMP_NUM_THREADS=1 ./wrf.exe > wrf.log 2>&1)
  grep -q "SUCCESS COMPLETE WRF" "$R/wrf.log" || { echo "WRF-FAILED $dir $(tail -2 "$R/wrf.log" | tr '\n' ' ')"; return; }
  for f in "$src"/wrfout_* "$src"/wrfrst_* "$src"/auxhist*; do
    [ -f "$f" ] || continue
    b=$(basename "$f")
    if [ ! -f "$R/$b" ]; then echo "MISSING $dir $b"; continue; fi
    m=$(md5sum < "$R/$b" | cut -c1-32) r=$(md5sum < "$f" | cut -c1-32)
    [ "$m" = "$r" ] && echo "SAME $dir $b $m" || echo "DIFF $dir $b $m $r"
  done
}
export -f run_one; export DATA OUT
printf '%s\n' "$@" | xargs -P "$(nproc)" -I{} bash -c 'run_one "$1"' _ {} >> "$L" 2>&1
grep -qE '^(DIFF|MISSING|WRF-FAILED) ' "$L" && bad=1
grep -q '^SAME ' "$L" || bad=1
echo "exit $bad" >> "$L"
exit $bad
