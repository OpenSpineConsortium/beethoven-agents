#!/bin/bash
# Refresh the vendored site profiles from their canonical home, hpcworker's framework/profiles/, and
# write ORIGIN: the commit they were read at and each file's sha256 (tests/test_site.py checks the
# files against it). Data only, never code: the engine reads these profiles and imports nothing of
# hpcworker (plan/REPO_SPLIT.md section 2).
#
#   bash profiles/pull.sh                  over the person's own gh sign-in, at hpcworker's main
#   bash profiles/pull.sh --from DIR       from a local hpcworker checkout, at its HEAD
#
# Every file is read at one commit, so ORIGIN names a state hpcworker really had. A profile hpcworker
# no longer has is listed for the person to remove in a reviewed commit, never deleted here.
set -euo pipefail
REPO=OpenSpineConsortium/hpcworker
FROM=""
case "${1:-}" in
  --from) FROM="${2:?--from needs a directory}" ;;
  "") ;;
  *) echo "usage: $0 [--from HPCWORKER_DIR]" >&2; exit 2 ;;
esac
cd "$(dirname "$0")"

# The person's own sign-in, never a token from the environment.
GH() { env -u GITHUB_TOKEN -u GH_TOKEN gh "$@"; }

if [ -n "$FROM" ]; then
  [ -z "$(git -C "$FROM" status --porcelain -- framework/profiles)" ] \
    || { echo "FAILED: $FROM has uncommitted changes under framework/profiles" >&2; exit 1; }
  sha=$(git -C "$FROM" rev-parse HEAD)
  names=$(git -C "$FROM" ls-tree --name-only "$sha" framework/profiles/ | sed 's#.*/##')
  fetch() { git -C "$FROM" show "$sha:framework/profiles/$1"; }
else
  sha=$(GH api "repos/$REPO/commits/main" --jq .sha) \
    || { echo "FAILED: could not read $REPO's main (is gh signed in?)" >&2; exit 1; }
  names=$(GH api "repos/$REPO/contents/framework/profiles?ref=$sha" --jq '.[].name') \
    || { echo "FAILED: could not list $REPO/framework/profiles" >&2; exit 1; }
  # Raw bytes, not the JSON envelope, which comes back empty past 1 MB.
  fetch() { GH api -H "Accept: application/vnd.github.raw+json" "repos/$REPO/contents/framework/profiles/$1?ref=$sha"; }
fi

record="repository $REPO
commit $sha
path framework/profiles"
n=0
for f in $(printf '%s\n' "$names" | grep '\.json$'); do
  fetch "$f" >"$f.part" || { rm -f "$f.part"; echo "FAILED $f" >&2; exit 1; }
  python3 -m json.tool "$f.part" >/dev/null 2>&1 || { rm -f "$f.part"; echo "FAILED $f: not JSON" >&2; exit 1; }
  mv -f "$f.part" "$f"
  record="$record
sha256 $(sha256sum "$f" | cut -d' ' -f1) $f"
  echo "pulled $f"
  n=$((n + 1))
done
[ "$n" -gt 0 ] || { echo "FAILED: $REPO/framework/profiles lists no profiles" >&2; exit 1; }
printf '%s\n' "$record" >ORIGIN.part && mv -f ORIGIN.part ORIGIN
for f in *.json; do
  printf '%s\n' "$names" | grep -qx "$f" || echo "hpcworker no longer has $f: remove it in a reviewed commit" >&2
done
echo "ORIGIN: $REPO at $sha"
