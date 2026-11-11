#!/usr/bin/env bash
# wrf_build.sh FLAVOR DEST: WRF v4.8.0 (the release tarball of github.com/wrf-model/WRF) built as CPPWRF's references
# were (docs/team/AGENTW_WRF480.md of CPPWRF): `configure` option 32 (serial, gfortran / gcc) with basic nesting (1),
# `-r8` (FLAVOR r8: PROMOTION = -fdefault-real-8) or `-r8` with -fdefault-double-8 added (FLAVOR r8d8), NetCDF of the
# Debian 13 packages through a directory of links (bin, include, lib), WRFIO_NCD_LARGE_FILE_SUPPORT=1,
# `./compile em_real`. In the Debian 13 container of the suite jobs. DEST gets the build tree; DEST.log the output.
set -euo pipefail
FLAVOR=$1 DEST=$2
URL=https://github.com/wrf-model/WRF/releases/download/v4.8.0/v4.8.0.tar.gz
SHA=${WRF_TARBALL_SHA256:-}
export DEBIAN_FRONTEND=noninteractive
apt-get -qq update > /dev/null
apt-get -qq install -y build-essential gfortran m4 perl tcsh file curl ca-certificates libnetcdf-dev libnetcdff-dev \
  python3-netcdf4 python3-numpy zstd > /dev/null
mkdir -p /opt/netcdf && for d in bin include; do ln -sfn /usr/$d /opt/netcdf/$d; done && ln -sfn /usr/lib/x86_64-linux-gnu /opt/netcdf/lib
export NETCDF=/opt/netcdf WRFIO_NCD_LARGE_FILE_SUPPORT=1
mkdir -p "$(dirname "$DEST")"
cd "$(dirname "$DEST")"
curl -fsSL --retry 5 -o wrf.tar.gz "$URL"
[ -z "$SHA" ] || echo "$SHA  wrf.tar.gz" | sha256sum -c -
sha256sum wrf.tar.gz
rm -rf "$DEST" && mkdir "$DEST" && tar xzf wrf.tar.gz -C "$DEST" --strip-components=1 && rm wrf.tar.gz
cd "$DEST"
printf '32\n1\n' | ./configure -r8 > configure.out 2>&1
[ "$FLAVOR" = r8d8 ] && sed -i 's/^PROMOTION\s*=.*/PROMOTION       =       -fdefault-real-8 -fdefault-double-8/' configure.wrf
grep -E '^(PROMOTION|RWORDSIZE|FCOPTIM|FCBASEOPTS_NO_G|DM_FC|SFC|NETCDFPATH)\b' configure.wrf
./compile em_real -j "$(nproc)" > compile.log 2>&1 || true
# WRF's parallel make can lose a module dependency: continue with fewer jobs (as CPPWRF's tools/bench/fp32_body.sh)
[ -x main/wrf.exe ] && [ -x main/real.exe ] || ./compile em_real -j 2 >> compile.log 2>&1 || true
[ -x main/wrf.exe ] && [ -x main/real.exe ] || ./compile em_real -j 1 >> compile.log 2>&1 || true
ls -la main/wrf.exe main/real.exe
md5sum main/wrf.exe main/real.exe
