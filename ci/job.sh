#!/usr/bin/env bash
# One job of the suite workflow, in the Debian 13 container (the compilers, glibc / libmvec, NetCDF and Python of the
# machines that made the references; tools/colab/remote_chroot_job.sh's packages). /w is the runner's workspace:
# /w/src (the CPPWRF source), /w/build (its CPU FP64 build), /w/data (the unpacked tars), /w/out (the logs).
#
#   job.sh setup | build | suite CASES TARS | files CASES TARS | idealfiles - TARS | diff - TARS | checks - TARS
#
# Logs as tools/gcp/suite_body.sh writes them: setup.out (a failed setup), cmake.log, suite.log, files_<case>.log,
# idealfiles.log, diff.log, ctest.log, unit.log, selftest.log; versions.txt (packages, CPU), data.txt (the tars),
# each ending with "exit N" where suite_body.sh's do.
set -uo pipefail
KIND=$1 CASES=${2:-} TARS=${3:-}
[ "$CASES" = - ] && CASES=
W=/w O=/w/out
mkdir -p $O; touch $O/setup.out
export DEBIAN_FRONTEND=noninteractive
packages() {
  apt-get -qq update > /dev/null && apt-get -qq install -y build-essential cmake gfortran libnetcdf-dev libnetcdff-dev \
    python3-netcdf4 python3-numpy curl ca-certificates git ccache zstd > $O/packages.log 2>&1 \
    || { echo "SETUP_FAILED packages (packages.log)" >> $O/setup.out; exit 1; }
  dpkg-query -W -f='${Package} ${Version}\n' libc6 libgcc-s1 gcc-14 g++-14 gfortran-14 cmake libnetcdf22 libnetcdff7 \
    python3.13 python3-numpy python3-netcdf4 > $O/versions.txt 2>&1
  { grep -m1 'model name' /proc/cpuinfo; grep -m1 vendor_id /proc/cpuinfo; echo "nproc $(nproc)"
    free -g | awk 'NR == 2 {print "RAM", $2, "GB"}'; df -h /w | awk 'NR == 2 {print "disk", $2, "free", $4}'; } >> $O/versions.txt
}
build() {  # the CPU FP64 binary as suite_body.sh builds it (-march=skylake: the reference workstation's instructions)
  export CCACHE_DIR=/w/.ccache CCACHE_MAXSIZE=2G
  cmake -S $W/src -B $W/build -DCMAKE_BUILD_TYPE=Release -DCPPWRF_DOUBLE=ON -DCPPWRF_ENABLE_CUDA=OFF -DCPPWRF_NATIVE=OFF \
    -DCMAKE_CXX_COMPILER_LAUNCHER=ccache -DCMAKE_CXX_FLAGS="-march=skylake -mtune=skylake" "$@" > $O/cmake.log 2>&1 &&
    cmake --build $W/build -j"$(nproc)" --target cppwrf >> $O/cmake.log 2>&1 || { echo "BUILD_FAILED (cmake.log)" >> $O/setup.out; return 1; }
  ccache -s >> $O/cmake.log 2>&1
}
data() {  # the tars of this job
  [ -n "$TARS" ] || return 0
  LOG=$O/data.txt SETUP=$O/setup.out PARTS=/w/parts bash /w/ci/ci/fetch_data.sh $W/data "$TARS"
  df -h /w | awk 'NR == 2 {print "disk after data", $2, "used", $3, "free", $4}' >> $O/versions.txt
}
env_runs() { export CPPWRF_WRF_RUNS=$W/data/wrf_runs CPPWRF_WRF_REF=$W/data/wrf_ref CPPWRF_SCRATCH=/w/scratch; mkdir -p /w/scratch; }
T=$(nproc)
case $KIND in
  build)
    packages; build || exit 1 ;;
  suite)
    packages; data; env_runs; cd $W/src
    OMP_NUM_THREADS=$T python3 tests/verify/wrf_suite.py --cpu-dp $W/build/cppwrf --jobs 1 --out /w/scratch/suite \
      --only "$CASES" --exact > $O/suite.log 2>&1
    echo "exit $?" >> $O/suite.log ;;
  files)
    packages; data; env_runs; cd $W/src
    for c in ${CASES//,/ }; do
      OMP_NUM_THREADS=$T bash tests/verify/run_wrf_files_test.sh $W/build "$c" > "$O/files_$c.log" 2>&1
      echo "exit $? $c" >> "$O/files_$c.log"
    done ;;
  idealfiles)
    packages; data; env_runs; cd $W/src
    OMP_NUM_THREADS=$T python3 tests/verify/ideal_files_test.py $W/build > $O/idealfiles.log 2>&1
    echo "exit $?" >> $O/idealfiles.log ;;
  diff)  # the differential tests and the other ctest tests (their own build with -DCPPWRF_DIFF_TESTS=ON)
    packages; data
    case ,$TARS, in *,diff_data.tar,*) ;; *)  # WRF's build trees from the wrf-build release (ci/wrf_build.sh)
      key=$(sha256sum /w/ci/ci/wrf_build.sh | cut -c1-12); mkdir -p /w/wrfb $W/data/wrf_build
      for fl in r8 r8d8; do
        if curl -fsSL --retry 5 "https://github.com/${DATA_REPO:-Xassemblianist/cppwrf-data}/releases/download/wrf-build/wrf-4.8.0-$fl-$key.tar.zst" |
             zstd -dq | tar xf - -C /w/wrfb; then
          # files a data tar adds to the build tree (port_c01_diff.tar: wrf_build/r8/run/...) go into it
          if [ -d $W/data/wrf_build/$fl ] && [ ! -L $W/data/wrf_build/$fl ]; then
            cp -a $W/data/wrf_build/$fl/. /w/wrfb/WRF-4.8.0-$fl/ && rm -rf $W/data/wrf_build/$fl
          fi
          ln -sfn /w/wrfb/WRF-4.8.0-$fl $W/data/wrf_build/$fl
        else echo "DATA_FAILED wrf-build wrf-4.8.0-$fl-$key.tar.zst" >> $O/setup.out; fi
      done ;;
    esac
    cd $W/src
    export CCACHE_DIR=/w/.ccache CCACHE_MAXSIZE=2G CMAKE_CXX_COMPILER_LAUNCHER=ccache
    OMP_NUM_THREADS=4 bash tools/gcp/run_diff_tests.sh $W/src $W/build_diff $W/data $O > $O/diff_setup.out 2>&1
    cat $O/diff_setup.out >> $O/setup.out ;;
  checks)  # the translator's unit tests and the comparators' self-test
    packages; data; env_runs; cd $W/src
    CPPWRF_BIN=$W/build/cppwrf OMP_NUM_THREADS=1 python3 tests/tools/test_wrf2cppwrf.py -v > $O/unit.log 2>&1; echo "exit $?" >> $O/unit.log
    python3 tests/verify/selftest.py > $O/selftest.log 2>&1; echo "exit $?" >> $O/selftest.log ;;
  *) echo "job.sh: unknown kind $KIND" >> $O/setup.out; exit 2 ;;
esac
echo "$KIND $SECONDS" > $O/wall.txt
# the job's status: nothing in setup.out, every log ends well
bad=0
grep -q . $O/setup.out && bad=1
for f in $O/suite.log $O/idealfiles.log $O/diff.log $O/ctest.log $O/unit.log $O/selftest.log; do
  [ -f "$f" ] && ! grep -qx "exit 0" "$f" && bad=1
done
for f in $O/files_*.log; do [ -f "$f" ] && grep -qE "^exit [1-9]" "$f" && bad=1; done
case $KIND in diff) [ -f $O/diff.log ] && [ -f $O/ctest.log ] || bad=1 ;; esac
exit $bad
