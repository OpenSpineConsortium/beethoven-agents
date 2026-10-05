#!/bin/bash
# Build the substrate image from containers/claude-verify.def and record what was built.
#
# Where it runs: inside a Slurm allocation on a compute node, with --fakeroot (the student has no
# root on the cluster). It refuses to run outside Slurm unless --allow-outside-slurm is given, which
# is for CI runners and nothing else: nothing container-related ever runs on the login node.
#
# Temp and cache go to the compute node's local disk, in a folder of the build's own with a cleanup
# trap. Which disk, which runtime and which module are the site profile's (src/beethoven_agents/
# site.sh, the same reading as bee-grid.sh's): $TMPDIR is used only where the profile says it is
# node-local (at Wayne State it is CephFS, not the node). A CI runner (--allow-outside-slurm) has no
# profile and builds with Apptainer under /tmp/$USER.
#
# What it records, beside the image, in <image>.digest: the sha256 of the .sif, the runtime's
# version, the Claude Code and pixi versions that landed inside, the git SHA of the recipe and the
# lock, and the UTC time. That file is the number to cite; nothing in the recipe is.
set -euo pipefail

usage() { echo "usage: $0 [--out DIR] [--allow-outside-slurm]" >&2; exit 2; }

OUT=""
ALLOW_OUTSIDE=0
while [ $# -gt 0 ]; do
    case "$1" in
        --out) OUT="$2"; shift 2 ;;
        --allow-outside-slurm) ALLOW_OUTSIDE=1; shift ;;
        -h|--help) usage ;;
        *) usage ;;
    esac
done

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
DEF="$HERE/claude-verify.def"
NAME="claude-verify"

if [ -z "${SLURM_JOB_ID:-}" ] && [ "$ALLOW_OUTSIDE" -ne 1 ]; then
    echo "$0: not inside a Slurm job; builds run on a compute node, never the login node" >&2
    echo "       (sbatch a job that runs this script; --allow-outside-slurm is for CI only)" >&2
    exit 1
fi

# shellcheck source=../src/beethoven_agents/site.sh
. "$ROOT/src/beethoven_agents/site.sh"
RT=apptainer
MODULE="${BEE_APPTAINER_MODULE:-}"
BASE="/tmp/${USER:-nobody}"
SITE_IMAGE=""
if bee_site_resolve "$ROOT"; then
    RT="$BEE_SITE_RT"
    [ -n "$RT" ] || { echo "$0: the site profile ($BEE_SITE_PATH) runs containers with $BEE_SITE_RUNTIME; the image needs apptainer or singularity" >&2; exit 1; }
    MODULE="${MODULE:-$BEE_SITE_MODULE}"
    BASE="$BEE_SITE_TEMP"
    [ -n "$BASE" ] || { echo "$0: the site profile's node temp ($BEE_SITE_NODE_TMP) is not a folder on this node" >&2; exit 1; }
    SITE_IMAGE="$BEE_SITE_IMAGE"
elif [ "$ALLOW_OUTSIDE" -ne 1 ]; then
    echo "$0: $BEE_SITE_WHY" >&2
    exit 1
fi
if ! command -v "$RT" >/dev/null 2>&1 && [ -n "$MODULE" ] && type module >/dev/null 2>&1; then
    module load "$MODULE" >/dev/null 2>&1 || true
fi
command -v "$RT" >/dev/null 2>&1 || { echo "$0: $RT not found (module load ${MODULE:-$RT}?)" >&2; exit 1; }

# Node-local scratch for the build, a folder of its own; never the login node's /tmp.
mkdir -p "$BASE"
SCRATCH="$(mktemp -d "$BASE/beethoven_build_${SLURM_JOB_ID:-local$$}_XXXXXX")"
trap 'rm -rf "$SCRATCH"' EXIT
export APPTAINER_TMPDIR="$SCRATCH/tmp" APPTAINER_CACHEDIR="$SCRATCH/cache"
# Singularity reads its own names, and without them falls back to $TMPDIR.
if [ "$RT" = singularity ]; then
    export SINGULARITY_TMPDIR="$APPTAINER_TMPDIR" SINGULARITY_CACHEDIR="$APPTAINER_CACHEDIR"
fi
mkdir -p "$APPTAINER_TMPDIR" "$APPTAINER_CACHEDIR"

OUT="${OUT:-$HERE}"
mkdir -p "$OUT"
SIF="$OUT/$NAME.sif"

# --fakeroot inside Slurm; under CI the runner is root and the flag is not needed.
FAKEROOT=()
if [ "$(id -u)" -ne 0 ]; then FAKEROOT=(--fakeroot); fi

# The recipe copies pixi.toml and pixi.lock by relative path, so build from the repository root.
cd "$ROOT"
"$RT" build "${FAKEROOT[@]}" --force "$SIF" "$DEF"

# Read the versions back from the image rather than trusting what the recipe asked for.
CLAUDE_VERSION="$("$RT" exec --containall --cleanenv --no-home "$SIF" claude --version 2>/dev/null | head -1 || echo unknown)"
PIXI_VERSION="$("$RT" exec --containall --cleanenv --no-home "$SIF" pixi --version 2>/dev/null | head -1 || echo unknown)"
GIT_SHA="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || echo unknown)"
SHA256="$(sha256sum "$SIF" | cut -d' ' -f1)"

{
    echo "image: $NAME.sif"
    echo "sha256: $SHA256"
    echo "built_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "$RT: $("$RT" --version)"
    echo "claude_code: $CLAUDE_VERSION"
    echo "pixi: $PIXI_VERSION"
    echo "recipe_git_sha: $GIT_SHA"
    echo "pixi_lock_sha256: $(sha256sum "$ROOT/pixi.lock" | cut -d' ' -f1)"
    echo "slurm_job: ${SLURM_JOB_ID:-none}"
    echo "node: $(hostname)"
} > "$OUT/$NAME.digest"

echo "built $SIF"
cat "$OUT/$NAME.digest"
# Where bee-grid.sh on this site looks for the image, when the build went elsewhere (--out).
if [ -n "$SITE_IMAGE" ] && [ "$SITE_IMAGE" != "$SIF" ]; then
    echo "bee-grid.sh on this site reads $SITE_IMAGE (build with --out ${SITE_IMAGE%/*} to put it there)"
fi
