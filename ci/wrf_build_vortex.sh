#!/usr/bin/env bash
# Vortex following (configure nesting 3: -DMOVE_NESTS -DVORTEX_CENTER): the dmpar recipe of wrf_build_dm.sh with
# nesting 3, in its own file so that the cache keys of the serial and wrf_build_dm.sh flavors stay valid.
set -euo pipefail
flavor=$1 dest=$2
case $flavor in
  r8dmvortex) promotion=-r8; word=8 ;;
  r4dmvortex) promotion=; word=4 ;;
  *) echo "unknown vortex flavor: $flavor" >&2; exit 2 ;;
esac
recipe=$(mktemp)
trap 'rm -f "$recipe"' EXIT
sed -e 's/libnetcdff-dev /libnetcdff-dev mpich libmpich-dev /' \
    -e "s/^printf .* | \.\/configure -r8 >/printf '%s\\\\n%s\\\\n' 34 3 | .\/configure $promotion >/" \
    "$(dirname "$0")/wrf_build.sh" > "$recipe"
grep -Fq "34 3 | ./configure $promotion >" "$recipe"
grep -Fq 'mpich libmpich-dev' "$recipe"
bash "$recipe" "$flavor" "$dest"
config=$dest/configure.wrf
grep -q -- '-DDM_PARALLEL' "$config"
if grep -q -- '-DSTUBMPI' "$config"; then exit 1; fi
grep -Eq "^RWORDSIZE[[:space:]]*=[[:space:]]*$word([[:space:]]|$)" "$config"
grep -q -- '-DMOVE_NESTS' "$config"
grep -q -- '-DVORTEX_CENTER' "$config"
