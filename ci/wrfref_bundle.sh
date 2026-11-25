#!/usr/bin/env bash
# wrfref_bundle.sh CPPWRF_DIR COMMIT OUTPUT.bundle [BASE=origin/main]
# Same thin bundle and refs/heads/ci convention as CPPWRF's ci_submit.sh, with no network or ref updates.
set -euo pipefail
repo=$1
sha=$(git -C "$repo" rev-parse --verify "$2^{commit}")
out=$3
base=$(git -C "$repo" rev-parse --verify "${4:-origin/main}^{commit}")
tmp=$(mktemp "$out.XXXXXX")
trap 'rm -f "$tmp"' EXIT
{
  echo '# v2 git bundle'
  git -C "$repo" rev-list --boundary "$sha" "^$base" | sed -n '/^-/p'
  printf '%s refs/heads/ci\n\n' "$sha"
  printf '%s\n^%s\n' "$sha" "$base" |
    git -C "$repo" pack-objects --revs --thin --stdout --delta-base-offset -q
} > "$tmp"
git -C "$repo" bundle verify "$tmp"
mv "$tmp" "$out"
