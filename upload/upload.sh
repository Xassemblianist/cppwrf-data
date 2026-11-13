#!/usr/bin/env bash
# upload.sh NAME: ci3_up/NAME as an asset of the data release (retries), recorded in sums/parts.txt, then deleted.
set -uo pipefail
D=$HOME/cppwrf_scratch/ci3 U=$HOME/cppwrf_scratch/ci3_up NAME=$1
R=Xassemblianist/cppwrf-data TAG=${CI3_TAG:-data-v1}
f=$U/$NAME
sha=$(sha256sum "$f" | cut -d' ' -f1) size=$(stat -c %s "$f")
rid=$(cat "$D/up/release_id")
for try in 1 2 3 4 5 6; do
  # a stale or half-uploaded asset of that name first
  for id in $(gh api --paginate "repos/$R/releases/$rid/assets?per_page=100" --jq ".[] | select(.name == \"$NAME\") | .id" 2>/dev/null); do
    gh api -X DELETE "repos/$R/releases/assets/$id" > /dev/null 2>&1
  done
  t0=$SECONDS
  if timeout 3600 gh release upload "$TAG" "$f" -R "$R" >> "$D/up/gh.log" 2>&1; then
    got=$(gh api --paginate "repos/$R/releases/$rid/assets?per_page=100" --jq ".[] | select(.name == \"$NAME\" and .state == \"uploaded\") | .size" 2>/dev/null | head -1)
    if [ "$got" = "$size" ]; then
      echo "$NAME $sha $size" >> "$D/sums/parts.txt"
      echo "UP $NAME $size $((SECONDS - t0)) s" >> "$D/up/log.txt"
      rm -f "$f"; exit 0
    fi
  fi
  echo "RETRY $NAME try $try" >> "$D/up/log.txt"; sleep $((60 * try))
done
echo "UPLOAD $NAME" >> "$D/up/FAILED"
rm -f "$f"
exit 1
