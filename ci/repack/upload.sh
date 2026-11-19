#!/usr/bin/env bash
# upload.sh PACK: a pack file as assets of the release $UP_TAG of $DATA_REPO: parts PACK.part000, ... of at most
# $PART_BYTES (default 1.9 GiB, under the 2 GiB asset limit), each uploaded with retries; "sha256  part" lines go to
# $OUT/sums.txt, "NAME bytes sha256 parts" to $OUT/tars.txt; the files are removed.
set -uo pipefail
f=$1 name=$(basename "$1") OUT=${OUT:-out} PB=${PART_BYTES:-2040109465}
R=${DATA_REPO:-Xassemblianist/cppwrf-data}
size=$(stat -c %s "$f") sha=$(sha256sum "$f" | cut -d' ' -f1)
split -b "$PB" -d -a 3 "$f" "$f.part" && rm -f "$f" || exit 1
n=0
for p in "$f".part*; do
  ok=0
  for i in 1 2 3 4 5 6 7 8; do
    gh release upload "$UP_TAG" "$p" -R "$R" --clobber > /dev/null 2>> "$OUT/upload.err" && { ok=1; break; }
    sleep $((20 * i))
  done
  [ $ok = 1 ] || { echo "upload: $(basename "$p") failed" >&2; exit 1; }
  echo "$(sha256sum "$p" | cut -d' ' -f1)  $(basename "$p")" >> "$OUT/sums.txt"
  rm -f "$p"; n=$((n + 1))
done
echo "$name $size $sha $n" >> "$OUT/tars.txt"
