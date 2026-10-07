#!/bin/bash
# Refresh profiles/ from OpenSpineConsortium/hpcworker's export "profiles" (its composed site
# profiles, one per deployment) and write ORIGIN: the commit they came from, the export and its
# version, and each file's sha256 (tests/test_boundary.py checks the copy against it). The profiles
# are data; nothing of hpcworker is run here, and nothing is read from a checkout of it (the
# interface standard, interface/README.md).
#
#   bash profiles/pull.sh [--ref REF]   from GitHub through gh and the person's own sign-in (REF: main)
#
# REF must be a commit hpcworker's default branch contains (a merged change, never a pull request's
# branch), and only the files its interface/INTERFACE.json lists under the export at that commit are
# taken, each to its path below the folder the export's paths share (framework/profiles/<id>.json
# lands at <id>.json). A profile this copy has and the source no longer does is listed for a person
# to remove in a reviewed commit; nothing is deleted.
set -euo pipefail
REPO=OpenSpineConsortium/hpcworker
EXPORT=profiles WANT=1   # the export, and the version of it the engine reads (src/beethoven_agents/site.py)
REF=main
while [ $# -gt 0 ]; do
  case "$1" in
    --ref) REF="${2:?--ref needs a branch, tag or commit}"; shift 2 ;;
    *) echo "usage: $0 [--ref REF]" >&2; exit 2 ;;
  esac
done
HERE="$(cd "$(dirname "$0")" && pwd)"
fail() { echo "FAILED: $*" >&2; exit 1; }
command -v gh >/dev/null || fail "gh is not installed"
command -v python3 >/dev/null || fail "python3 is needed to read the export's paths"
# The person's own sign-in, never a token from the environment.
GH() { env -u GITHUB_TOKEN -u GH_TOKEN gh "$@"; }

sha=$(GH api "repos/$REPO/commits/$REF" --jq .sha) || fail "could not read $REPO at $REF (is gh signed in?)"
[[ "$sha" =~ ^[0-9a-f]{40}$ ]] || fail "no commit for $REF"
default=$(GH api "repos/$REPO" --jq .default_branch)
case "$(GH api "repos/$REPO/compare/$default...$sha" --jq .status)" in
  identical|behind) ;;
  *) fail "$sha is not on $REPO's $default; take only what was merged there" ;;
esac
fetch() { GH api -H "Accept: application/vnd.github.raw+json" "repos/$REPO/contents/$1?ref=$sha"; }

# The export's paths, as the provider's manifest at that commit lists them, decide what is taken:
# "dir/" is every file under it, "*" matches within one part of a path. Each file lands at its
# path below the folder all the export's paths share. One line per file: its path, a tab, where.
PLAN='
import json, re, sys
export, want, manifest = sys.argv[1], int(sys.argv[2]), json.loads(sys.argv[3])
offered = [e for e in manifest.get("exports", []) if e.get("id") == export]
if not offered or offered[0].get("version") != want:
    sys.exit("export %s version %d is not offered (offered: %s)" % (export, want, ", ".join(
        "%s %s" % (e.get("id"), e.get("version")) for e in manifest.get("exports", []))))
paths = offered[0]["paths"]
def pattern(p):
    body = "[^/]*".join(re.escape(part) for part in p.split("*"))
    return re.compile("^" + body + ("" if p.endswith("/") else "$"))
def folder(p):
    head = p.split("*")[0]
    return head[: head.rfind("/") + 1].rstrip("/").split("/") if "/" in head else []
shared = []
for level in zip(*[folder(p) for p in paths]):
    if len(set(level)) != 1:
        break
    shared.append(level[0])
base = "/".join(shared) + "/" if shared else ""
rules = [pattern(p) for p in paths]
for line in sys.stdin.read().splitlines():
    if any(r.match(line) for r in rules):
        print("%s\t%s" % (line, line[len(base):]))
'
manifest=$(fetch interface/INTERFACE.json) || fail "$REPO has no interface/INTERFACE.json at $sha"
plan=$(GH api "repos/$REPO/git/trees/$sha?recursive=1" --jq '.tree[] | select(.type == "blob") | .path' \
  | python3 -I -c "$PLAN" "$EXPORT" "$WANT" "$manifest") || fail "$REPO at $sha does not offer $EXPORT version $WANT"
[ -n "$plan" ] || fail "no file in the export $EXPORT at $sha"

origin=("repository $REPO" "commit $sha" "export $EXPORT $WANT")
taken=()
while IFS=$'\t' read -r src rel; do
  case "/$rel/" in
    //|*/../*|*/./*|/ORIGIN/|/README.md/|/pull.sh/) fail "$src would land outside this folder or on its own files" ;;
  esac
  dest="$HERE/$rel"
  mkdir -p "$(dirname "$dest")"
  fetch "$src" >"$dest.part" || { rm -f "$dest.part"; fail "could not read $src at $sha"; }
  if [[ "$rel" == *.json ]] && ! python3 -I -m json.tool "$dest.part" >/dev/null 2>&1; then
    rm -f "$dest.part"; fail "$src is not JSON"
  fi
  mv -f "$dest.part" "$dest"
  origin+=("sha256 $(sha256sum "$dest" | cut -d' ' -f1) $rel")
  taken+=("$rel")
done <<< "$plan"
printf '%s\n' "${origin[@]}" >"$HERE/ORIGIN.part"
mv -f "$HERE/ORIGIN.part" "$HERE/ORIGIN"
echo "profiles: ${#taken[@]} file(s) from $REPO at $sha"
while IFS= read -r f; do
  rel="${f#"$HERE"/}"
  case "$rel" in ORIGIN|README.md|pull.sh) continue ;; esac
  printf '%s\n' "${taken[@]}" | grep -qxF "$rel" && continue
  echo "not in $REPO's export any more: profiles/$rel (remove it in a reviewed commit)"
done < <(find "$HERE" -type f ! -name '*.part' | sort)
