#!/usr/bin/env bash
# fetch_data.sh DEST TAR,TAR,... : the data tars from the release assets (parts of at most 2 GiB, SHA256SUMS), each
# part checked, unpacked into DEST in the given order (a later tar replaces an earlier one's files). The next tar's
# parts download while one is unpacked. Lines "TAR name bytes download_s unpack_s" go to $LOG (default data.txt),
# failures as "DATA_FAILED ..." to setup.out.
#   DATA_REPO (Xassemblianist/cppwrf-data), DATA_TAG (data-v1), PARTS (a scratch directory, default DEST/../parts)
set -uo pipefail
DEST=$1 LIST=$2
REPO=${DATA_REPO:-Xassemblianist/cppwrf-data} TAG=${DATA_TAG:-data-v1}
P=${PARTS:-$(dirname "$DEST")/parts} LOG=${LOG:-data.txt} SETUP=${SETUP:-setup.out}
URL=https://github.com/$REPO/releases/download/$TAG
mkdir -p "$DEST" "$P"
get() {  # get NAME: one asset with retries
  local i
  for i in 1 2 3 4 5; do
    curl -fsSL --retry 3 --connect-timeout 30 -o "$P/$1.tmp" "$URL/$1" && mv "$P/$1.tmp" "$P/$1" && return 0
    sleep $((10 * i))
  done
  return 1
}
export -f get; export P URL
get SHA256SUMS || { echo "DATA_FAILED SHA256SUMS of $REPO $TAG" >> "$SETUP"; exit 1; }
download() {  # download TAR: its parts, 4 at a time, checked; TAR.ok or TAR.failed
  local t=$1 t0=$SECONDS
  grep -E "  ${t//./\\.}\.part[0-9]+$" "$P/SHA256SUMS" > "$P/$t.sums"
  [ -s "$P/$t.sums" ] || { touch "$P/$t.failed"; return; }
  awk '{print $2}' "$P/$t.sums" | xargs -P 4 -I{} bash -c 'get "$1"' _ {} &&
    (cd "$P" && sha256sum -c --quiet "$t.sums") && echo $((SECONDS - t0)) > "$P/$t.ok" || touch "$P/$t.failed"
}
IFS=, read -ra TARS <<< "$LIST"
bad=0 n=${#TARS[@]}
[ "$n" -gt 0 ] && download "${TARS[0]}" &
for ((i = 0; i < n; i++)); do
  t=${TARS[$i]}
  wait  # this tar's download
  [ $((i + 1)) -lt "$n" ] && download "${TARS[$((i + 1))]}" &
  if [ -e "$P/$t.ok" ]; then
    t0=$SECONDS
    # shellcheck disable=SC2046
    if cat $(awk '{print "'"$P"'/" $2}' "$P/$t.sums") | tar xf - -C "$DEST"; then
      echo "TAR $t $(awk '{print $2}' "$P/$t.sums" | (cd "$P" && xargs stat -c %s) | awk '{s += $1} END {print s}') $(cat "$P/$t.ok") $((SECONDS - t0))" >> "$LOG"
    else echo "DATA_FAILED $t (unpack)" >> "$SETUP"; bad=1; fi
    (cd "$P" && awk '{print $2}' "$t.sums" | xargs rm -f)
  else echo "DATA_FAILED $t (download or sha256)" >> "$SETUP"; bad=1; fi
done
wait
# TAR.links (small tars of relative links, listed in SHA256SUMS): links that the re-pack had to leave out (they
# pointed into the reference machine's home), unpacked after every tar of the list, as the original tar's links were
# the last word on Colab (v05_files_data.tar came last there)
for t in "${TARS[@]}"; do
  grep -qE "  ${t//./\\.}\.links$" "$P/SHA256SUMS" || continue
  if get "$t.links" && (cd "$P" && grep -E "  ${t//./\\.}\.links$" SHA256SUMS | sha256sum -c --quiet -) &&
     tar xf "$P/$t.links" -C "$DEST"; then echo "LINKS $t.links" >> "$LOG"; rm -f "$P/$t.links"
  else echo "DATA_FAILED $t.links" >> "$SETUP"; bad=1; fi
done
exit $bad
