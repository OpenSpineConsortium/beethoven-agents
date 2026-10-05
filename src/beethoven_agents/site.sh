# site.sh: the site profile in bash, sourced by bee/bee-grid.sh and containers/build.sh.
#
# The twin of site.py, which is the reference: the same fields, the same order of rules, the same
# refusals. Both run over every vendored profile and over variations of them in tests/test_site.py,
# and a difference is a bug in one of them. It exists because those two scripts must know the
# container runtime, the image and the node-local temp before any container can start, so the
# profile is read on the compute node itself, with the node's own python3 and its standard library
# only (Python 3.6 on CentOS 7 nodes); nothing here evaluates a value from the profile.
#
# Which profile: BEE_SITE_PROFILE (a file), else BEE_SITE (an id: this checkout's profiles/<id>.json),
# else the account's own copy that hpcworker keeps (HPCW_PROFILE, else $HPCW_HOME/profile.json, else
# ~/.hpcworker/profile.json). After bee_site_resolve ENGINE_DIR returns 0 these are set:
#
#   BEE_SITE_PATH     the profile file read          BEE_SITE_ID       its site id
#   BEE_SITE_RUNTIME  the runtime it names           BEE_SITE_RT       the command bee runs, or empty
#   BEE_SITE_MODULE   the module that loads it       BEE_SITE_IMAGE    the engine's image, or empty
#   BEE_SITE_NODE_TMP the node temp pattern          BEE_SITE_TEMP     the node-local base, or empty
#
# An empty BEE_SITE_RT, BEE_SITE_IMAGE or BEE_SITE_TEMP is a refusal the caller turns into words. On
# return 1, BEE_SITE_WHY says in plain words why no profile was read.

BEE_SITE_ENGINE_IMAGE=claude-verify.sif

# The reader: one line, the fields tab-separated, or a message and exit 3. Values with a tab or a
# line break are refused, as site.py's model refuses them.
_BEE_SITE_READER='
import json, sys
path = sys.argv[1]
def no(msg):
    sys.stderr.write(msg + "\n")
    sys.exit(3)
try:
    with open(path, encoding="utf-8") as fh:
        p = json.load(fh)
except (OSError, ValueError) as e:
    no("the site profile %s cannot be read: %s" % (path, e))
if not isinstance(p, dict):
    no("the site profile %s is not a JSON object" % path)
def text(v, name):
    if v is None:
        return ""
    if not isinstance(v, str) or "\t" in v or "\n" in v or "\r" in v:
        no("the site profile field %s is not one line of text" % name)
    return v
store = p.get("image_store")
if store is not None and not isinstance(store, dict):
    no("the site profile field image_store is not an object")
local = p.get("tmpdir_is_node_local")
if local is not None and not isinstance(local, bool):
    no("the site profile field tmpdir_is_node_local is not true or false")
site = text(p.get("site"), "site")
if not site:
    no("the site profile %s names no site" % path)
row = [site] + [text(p.get(k), k) for k in ("runtime", "runtime_module")]
row.append(text(store.get("path"), "image_store.path") if store else "")
row += [text(p.get(k), k) for k in ("containers_dir", "node_tmp", "node_tmp_var")]
row.append("1" if local else "0")
sys.stdout.write("\t".join(row) + "\n")
'

# TEXT NAME VALUE: TEXT with ${NAME} and $NAME replaced by VALUE, as plain text. The quoted
# replacement keeps bash 5.2 from reading an & in VALUE as the matched text.
_bee_site_sub() {
  local s="$1" a="\${$2}" b="\$$2"
  s=${s//"$a"/"$3"}
  s=${s//"$b"/"$3"}
  printf '%s' "$s"
}

# TEXT: the variables a profile path may name, in hpcworker's order (hpcw_expand_job_vars), never
# by eval: $USER, $HOME, the job id under any scheduler's name, and the node temp variables that
# are set.
bee_site_expand() {
  local s="$1" n job="${SLURM_JOB_ID:-${PBS_JOBID:-${LSB_JOBID:-${JOB_ID:-${HPCW_JOB_ID:-}}}}}"
  s=$(_bee_site_sub "$s" USER "$USER")
  s=$(_bee_site_sub "$s" HOME "${HOME:-}")
  for n in SLURM_JOB_ID PBS_JOBID LSB_JOBID HPCW_JOB_ID; do s=$(_bee_site_sub "$s" "$n" "$job"); done
  for n in SLURM_TMPDIR L_SCRATCH TMPDIR; do
    [ -z "${!n:-}" ] || s=$(_bee_site_sub "$s" "$n" "${!n}")
  done
  printf '%s' "$s"
}

# LINE NAME...: split one tab-separated line into the named variables, keeping empty fields.
_bee_site_split() {
  local _r="$1" _v
  shift
  for _v in "$@"; do
    if [[ "$_r" == *$'\t'* ]]; then
      printf -v "$_v" '%s' "${_r%%$'\t'*}"
      _r="${_r#*$'\t'}"
    else
      printf -v "$_v" '%s' "$_r"
      _r=""
    fi
  done
}

bee_site_resolve() {
  local engine="$1" path line ids store containers var local cdir pat last raw base py
  BEE_SITE_WHY=""
  if [ -n "${BEE_SITE_PROFILE:-}" ]; then
    path="$BEE_SITE_PROFILE"
    [ -f "$path" ] || { BEE_SITE_WHY="no site profile at $path (BEE_SITE_PROFILE)"; return 1; }
  else
    ids="$(cd "$engine/profiles" 2>/dev/null && ls -- *.json 2>/dev/null | sed 's/\.json$//' | tr '\n' ' ')" || ids=""
    ids="${ids% }"
    if [ -n "${BEE_SITE:-}" ]; then
      case "$BEE_SITE" in
        "" | -* | *[!abcdefghijklmnopqrstuvwxyz0123456789-]*) path="" ;;
        *) path="$engine/profiles/$BEE_SITE.json" ;;
      esac
      [ -n "$path" ] && [ -f "$path" ] \
        || { BEE_SITE_WHY="no profile for the site $BEE_SITE here (this copy has: ${ids:-none})"; return 1; }
    else
      path="${HPCW_PROFILE:-${HPCW_HOME:-$HOME/.hpcworker}/profile.json}"
      [ -f "$path" ] || {
        BEE_SITE_WHY="no site profile: this account has no $path (hpcworker install makes it); name the site with BEE_SITE=<id> (this copy has: ${ids:-none}) or a file with BEE_SITE_PROFILE"
        return 1
      }
    fi
  fi
  case "${USER:-}" in
    "" | */* | *'$'*) BEE_SITE_WHY="USER is not set to a plain user name"; return 1 ;;
  esac
  py="${BEE_HOST_PYTHON:-python3}"
  command -v "$py" >/dev/null 2>&1 \
    || { BEE_SITE_WHY="$py is not on this node's path; it reads the site profile (BEE_HOST_PYTHON names another)"; return 1; }
  line="$("$py" -I -c "$_BEE_SITE_READER" "$path" 2>&1)" || { BEE_SITE_WHY="$line"; return 1; }
  line="${line##*$'\n'}" # the row is the last line; anything the node's python said before it is not
  _bee_site_split "$line" BEE_SITE_ID BEE_SITE_RUNTIME BEE_SITE_MODULE store containers \
    BEE_SITE_NODE_TMP var local
  BEE_SITE_PATH="$path"

  # The runtime: Apptainer when the profile names none; refused when its exec takes other flags.
  case "$BEE_SITE_RUNTIME" in
    "") BEE_SITE_RT=apptainer ;;
    apptainer | singularity) BEE_SITE_RT="$BEE_SITE_RUNTIME" ;;
    *) BEE_SITE_RT="" ;;
  esac

  # The image folder: containers_dir, else the folder of the worker image; the engine's image in it.
  if [ -n "$containers" ]; then
    cdir="$containers"
  else
    case "$store" in */*) cdir="${store%/*}" ;; *) cdir="" ;; esac
  fi
  cdir="$(bee_site_expand "$cdir")"
  case "$cdir" in
    /*'$'* | "" | [!/]*) BEE_SITE_IMAGE="" ;;
    *) BEE_SITE_IMAGE="$cdir/$BEE_SITE_ENGINE_IMAGE" ;;
  esac

  # The node-local base: beside hpcworker's own job folder when the pattern's last part names the
  # job, else the pattern's folder itself; then the site's variable, a node-local $TMPDIR,
  # /scratch/$USER, /tmp/$USER.
  pat="$BEE_SITE_NODE_TMP"
  if [ -n "$pat" ]; then
    last="${pat##*/}"
    raw="$pat"
    if [[ "$pat" == */* ]]; then
      case "$last" in
        *'$'*) case "$last" in *SLURM_JOB_ID* | *PBS_JOBID* | *LSB_JOBID* | *HPCW_JOB_ID*) raw="${pat%/*}" ;; esac ;;
      esac
    fi
    base="$(bee_site_expand "$raw")"
  elif [ -n "$var" ] && [[ "$var" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] && [ -n "${!var:-}" ]; then
    base="${!var}/$USER"
  elif [ "$local" = 1 ] && [ -n "${TMPDIR:-}" ]; then
    base="$TMPDIR"
  elif [ -d "/scratch/$USER" ] && [ -w "/scratch/$USER" ]; then
    base="/scratch/$USER"
  else
    base="/tmp/$USER"
  fi
  case "$base" in
    /*'$'* | "" | [!/]*) BEE_SITE_TEMP="" ;;
    *) BEE_SITE_TEMP="$base" ;;
  esac
  return 0
}
