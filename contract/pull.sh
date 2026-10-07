#!/bin/bash
# Refresh this folder from the export it pins, then write its ORIGIN: the repository, the commit the
# files came from, the export and its version, and each file's sha256, sorted by path
# (tests/test_boundary.py checks the copy against it). Which repository, export and version is the
# import of interface/INTERFACE.json whose "into" is this folder, so the script cannot pin something
# the manifest does not declare; every import folder holds this same script, byte for byte
# (tests/test_boundary.py again), so a fix reaches each. What arrives is data: nothing of the
# provider is run here, and nothing is read from a checkout of it (the interface standard,
# interface/README.md).
#
#   bash <folder>/pull.sh [--ref REF]   from GitHub through gh and the person's own sign-in (REF: main)
#
# REF must be a commit the provider's default branch contains (a merged change, never a pull
# request's branch), and only the files the provider's interface/INTERFACE.json lists under the
# export at that commit, at the version the import names, are taken, each to its path below the
# folder the export's paths share (framework/profiles/<id>.json lands at <id>.json,
# interface/contract/vectors/<name>.json at vectors/<name>.json). A file this copy has and the
# export no longer does is listed for a person to remove in a reviewed commit; nothing is deleted.
set -euo pipefail
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
command -v python3 >/dev/null || fail "python3 is needed to read the manifests"

# This folder's import, from the manifest of the repository it is in.
MINE='
import json, os, re, sys
here = os.path.realpath(sys.argv[1])
root = os.path.dirname(here)
while not os.path.isfile(os.path.join(root, "interface", "INTERFACE.json")):
    if os.path.dirname(root) == root:
        sys.exit("no interface/INTERFACE.json above " + here)
    root = os.path.dirname(root)
with open(os.path.join(root, "interface", "INTERFACE.json"), encoding="utf-8") as fh:
    imports = json.load(fh).get("imports", [])
into = os.path.relpath(here, root)
mine = [i for i in imports if os.path.realpath(os.path.join(root, str(i.get("into")))) == here]
if len(mine) != 1:
    sys.exit("interface/INTERFACE.json names no import into " + into)
repo, export, version = mine[0].get("repository"), mine[0].get("export"), mine[0].get("version")
if not (re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9._-]+", str(repo))
        and re.fullmatch(r"[a-z0-9-]+", str(export)) and type(version) is int):
    sys.exit("the import into %s is not one this script can take" % into)
print(repo, export, version, into)
'
mine=$(python3 -I -c "$MINE" "$HERE") || fail "this folder is not an import of interface/INTERFACE.json"
read -r REPO EXPORT WANT INTO <<< "$mine"

sha=$(gh api "repos/$REPO/commits/$REF" --jq .sha) || fail "could not read $REPO at $REF (is gh signed in?)"
[[ "$sha" =~ ^[0-9a-f]{40}$ ]] || fail "no commit for $REF"
default=$(gh api "repos/$REPO" --jq .default_branch) || fail "could not read $REPO"
[[ "$default" =~ ^[A-Za-z0-9._/-]+$ ]] || fail "$REPO names no default branch"
# identical or ahead: the default branch holds the commit (a merged change)
case "$(gh api "repos/$REPO/compare/$sha...$default" --jq .status)" in
  identical|ahead) ;;
  *) fail "$sha is not on $REPO's $default; take only what was merged there" ;;
esac
fetch() { gh api -H "Accept: application/vnd.github.raw+json" "repos/$REPO/contents/$1?ref=$sha"; }

# The export's paths, as the provider's manifest at that commit lists them, decide what is taken:
# "dir/" is every file under it, "*" matches within one part of a path. Each file lands at its
# path below the folder all the export's paths share. One line per file, sorted by where it lands:
# its path, a tab, where.
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
taken = [line for line in sys.stdin.read().splitlines() if any(r.match(line) for r in rules)]
for line in sorted(taken, key=lambda line: line[len(base):]):
    print("%s\t%s" % (line, line[len(base):]))
'
manifest=$(fetch interface/INTERFACE.json) || fail "$REPO has no interface/INTERFACE.json at $sha"
plan=$(gh api "repos/$REPO/git/trees/$sha?recursive=1" --jq '.tree[] | select(.type == "blob") | .path' \
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
echo "$INTO: ${#taken[@]} file(s) of $EXPORT $WANT from $REPO at $sha"
while IFS= read -r f; do
  rel="${f#"$HERE"/}"
  case "$rel" in ORIGIN|README.md|pull.sh) continue ;; esac
  printf '%s\n' "${taken[@]}" | grep -qxF -- "$rel" && continue
  echo "not in $REPO's export any more: $INTO/$rel (remove it in a reviewed commit)"
done < <(find "$HERE" -type f ! -name '*.part' | LC_ALL=C sort)
