#!/usr/bin/env bash
# Run inside Debian 13 in the Actions workspace. WRFREF_ROOT also permits isolated local runner tests.
set -euo pipefail
mode=$1
job=${WRFREF_ROOT:-/w}
data=$job/data runs=$job/wrf_runs out=$job/out wrf=$job/wrf
here=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$out" "$runs"
export DEBIAN_FRONTEND=noninteractive
packages=(curl ca-certificates libnetcdf22 libnetcdff7 libgfortran5 python3-netcdf4 python3-numpy g++)
case " $BUILDS " in *dm*) packages+=(mpich) ;; esac
apt-get -qq update > "$out/packages.log" 2>&1
apt-get -qq install -y "${packages[@]}" >> "$out/packages.log" 2>&1
{ grep -m1 'model name' /proc/cpuinfo; grep -m1 vendor_id /proc/cpuinfo; echo "nproc $(nproc)"; } > "$out/cpu.txt"
# Reproduce the Intel glibc vector log / log10 bits even on AMD hosts.
g++ -std=c++20 -O2 -ffp-contract=off -fno-exceptions -fno-rtti -fPIC -shared -I"$job/src/src" \
  "$job/src/tests/phys/libmvec_intel.cpp" -o "$job/libmvec_intel.so"
export LD_PRELOAD=$job/libmvec_intel.so
if [ -n "$DATA" ]; then
  LOG=$out/data.txt SETUP=$out/setup.out PARTS=$job/parts bash "$here/fetch_data.sh" "$data" "$DATA"
fi
for fl in $BUILDS; do
  exe=$wrf/WRF-4.8.0-$fl/main/wrf.exe
  test -x "$exe"
  case $fl in
    *dm*)
      printf '#!/bin/sh\nexec mpiexec -launcher fork -n 1 "%s" "$@"\n' "$exe" > "$wrf/wrf_$fl.exe"
      chmod +x "$wrf/wrf_$fl.exe" ;;
    *) ln -sfn "$exe" "$wrf/wrf_$fl.exe" ;;
  esac
done
runner=$job/src/tools/gcp/wrf_ref_run.py
case $mode in
  repro)
    serial=$data/wrf/wrf_r8.exe
    test -x "$serial"
    pids=()
    for build in serial r8dm r8dmmove; do
      exe=$wrf/wrf_$build.exe
      [ "$build" != serial ] || exe=$serial
      python3 "$runner" "$data/runs" "$runs" "$exe" "$build" run_N3s_r8 \
        time_control.run_seconds=600 time_control.history_interval_s=60,60 domains.num_moves=0 run.steps=0 \
        > "$out/repro-$build.log" 2>&1 &
      pids+=("$!")
    done
    failed=0
    for pid in "${pids[@]}"; do wait "$pid" || failed=1; done
    cat "$out"/repro-*.log
    if [ "$failed" = 1 ]; then echo 'REPRO FAILED (WRF run)' | tee "$out/repro.log"; exit 1; fi
    python3 "$here/wrfref_repro.py" "$runs" 2>&1 | tee "$out/repro.log"
    exit ;;
  refs) ;;
  *) exit 2 ;;
esac

(cd "$runs" && bash -e "$job/prep.sh") > "$out/prep.out" 2>&1
run_one() {
  local name base fl
  local -a fields
  read -r -a fields <<< "$1"
  name=${fields[0]} base=${fields[1]} fl=${fields[2]}
  case $base in
    /*) ;;
    */*) base=$data/$base ;;
    *)
      if [ -f "$runs/$base/namelist.input" ]; then base=$runs/$base
      elif [ -f "$data/$base/namelist.input" ]; then base=$data/$base
      elif [ -f "$data/runs/$base/namelist.input" ]; then base=$data/runs/$base
      else base=$data/wrf_runs/$base; fi ;;
  esac
  if [ ! -f "$base/namelist.input" ]; then echo "$name FAILED missing $base/namelist.input"; return 1; fi
  printf '%s base %s (%s)\n' "$name" "$base" "$fl"
  python3 "$runner" "$data" "$runs" "$wrf/wrf_$fl.exe" "$name" "$base" "${fields[@]:3}"
}
export -f run_one
export data runs wrf runner
if [ -s "$job/refs.txt" ]; then
  xargs -d '\n' -r -P "$(nproc)" -I{} bash -e -c 'run_one "$1"' _ {} < "$job/refs.txt" > "$out/refs.out" 2>&1
fi

mapfile -t restarts < "$job/restarts.txt"
if [ "${#restarts[@]}" -gt 0 ]; then
  export CPPWRF_WRF_RUNS=$runs
  for stage in restart resumed; do
    CPPWRF_RESUMED_RESTART_INTERVAL=${RESUMED_RESTART_INTERVAL:-} \
      bash "$job/src/tests/verify/make_${stage}_refs.sh" "${restarts[@]}" >> "$out/refs.out" 2>&1
    prefix=rst
    [ "$stage" = restart ] || prefix=rsm
    for name in "${restarts[@]}"; do
      d=$runs/${prefix}_$name
      if ! grep -q 'SUCCESS COMPLETE WRF' "$d/wrf.log"; then
        echo "$name FAILED ($stage)" >> "$out/refs.out"
        tail -20 "$d/wrf.log" >> "$out/refs.out"
        exit 1
      fi
      compgen -G "$d/wrfout_d01_*" > /dev/null
      if [ "$stage" = restart ] || [ -n "${RESUMED_RESTART_INTERVAL:-}" ]; then
        test -n "$(find "$d" -maxdepth 1 -type f -name 'wrfrst_d01_*' -print -quit)"
      fi
    done
  done
fi

dirs=()
while read -r name base fl sets; do
  dirs+=("run_$name")
  case $fl in
    *dmmove) for d in "$runs/run_$name" "$runs/run_$name/steps"; do
      [ -d "$d" ] || continue
      echo "== ${d#"$runs/"}"
      grep -hE '^ *moving|Grid +[0-9]+ New SW corner|MOAD can not move' "$d"/rsl.error.0000 "$d"/wrf.log || true
    done >> "$out/moves.log" ;;
  esac
done < "$job/refs.txt"
for name in "${restarts[@]}"; do dirs+=("rst_$name" "rsm_$name"); done
shopt -s nullglob
for d in "$runs"/base_*; do [ ! -d "$d" ] || dirs+=("${d##*/}"); done
if [ "${#dirs[@]}" -gt 0 ]; then
  (
    cd "$runs"
    find "${dirs[@]}" -type f \( -name 'wrfout_*' -o -name 'wrfrst_*' -o -name 'auxhist*' -o -name 'wrfinput_*' \
      -o -name 'wrfbdy_*' -o -name 'wrflowinp_*' -o -name 'wrffdda_*' \) -print0 |
      sort -z | xargs -0 -r md5sum | awk '{print "MD5", $2, $1}'
  ) > "$out/refs_md5.txt"
  mkdir -p "$job/fetch"
  if [ "${PORTABLE:-false}" = true ]; then
    python3 "$here/wrfref_archive.py" "$runs" "${dirs[@]}"
  else
    tar cf - -C "$runs" "${dirs[@]}"
  fi | split -b 1900M -d -a 3 - "$job/fetch/refs.tar.part"
fi
if [ -s "$job/rerun.txt" ]; then
  read -ra reruns < "$job/rerun.txt"
  if [ "${#reruns[@]}" -gt 0 ]; then bash "$here/wrf_rerun.sh" "$data" "$out" "${reruns[@]}"; fi
fi
