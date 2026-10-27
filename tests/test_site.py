"""The site profile: every vendored copy read, the reader in Python and its twin in bash agreeing on
every vendored profile and on variations of it, and no site's literal in the engine's code (Linear
BEE-219; /mnt/project-files/sites/DESIGN.md sections 5.3 and 5.4). The copies against their ORIGIN,
and the pull that refreshes them, are tests/test_boundary.py's (the interface standard's rule 3).

The agreement test is the one that matters: bee-grid.sh and containers/build.sh read the profile
with site.sh, before any container exists, and site.py is the reference the gate proves. A row
where the two differ is a bug in one of them.
"""

from __future__ import annotations

import copy
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from beethoven_agents import site

REPO = Path(__file__).resolve().parents[1]
PROFILES = REPO / "profiles"
SITE_SH = REPO / "src" / "beethoven_agents" / "site.sh"


def vendored() -> list[Path]:
    return sorted(PROFILES.glob("*.json"))


def load(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


# --- the vendored copies (tests/test_boundary.py checks them against their ORIGIN) ----------------


@pytest.mark.parametrize("path", vendored(), ids=lambda p: p.stem)
def test_every_profile_is_read_and_names_itself(path: Path) -> None:
    prof = site.SiteProfile.model_validate(load(path))
    assert prof.site == path.stem


# --- the reference, on its own -------------------------------------------------------------------


def test_wayne_state_resolves_to_what_bee_used_before() -> None:
    # The values bee-grid.sh had written into it before the profile was read; the profile must
    # give the same ones, so the change moves them and changes nothing at Wayne State.
    prof = site.SiteProfile.model_validate(load(PROFILES / "wayne.json"))
    assert prof.image_store is not None
    folder = site.container_dir(prof.containers_dir, prof.image_store.path)
    assert site.engine_image(folder) == (
        "/rs/rs_grp_oschome/shared/beethoven/containers/claude-verify.sif"
    )
    assert prof.runtime_module == "apptainer/1.2.2"
    assert site.runtime_command(prof.runtime) == "apptainer"
    local = prof.tmpdir_is_node_local
    node = ("go0000", "/home/go0000", "17", "", "", "/cephfs/tmp")
    base = site.node_temp_base(prof.node_tmp, prof.node_tmp_var, "", local, *node, False)
    assert base == "/tmp/go0000"  # never $TMPDIR: at Wayne State it is CephFS


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        ("/tmp/$USER/hpcworker_$SLURM_JOB_ID", "/tmp/u"),  # beside hpcworker's own job folder
        ("/tmp/${USER}/hpcworker_${SLURM_JOB_ID}", "/tmp/u"),
        ("$SLURM_TMPDIR", "/local/job7"),  # the job's own folder: inside it
        ("$SLURM_TMPDIR/hpcworker_$PBS_JOBID", "/local/job7"),
        ("/local/$USER/$LSB_JOBID", "/local/u"),
        ("/local/$USER", "/local/u"),
        ("hpcworker_$SLURM_JOB_ID", ""),  # relative: refused
        ("/hpcworker_$SLURM_JOB_ID", ""),  # the root: refused
        ("$L_SCRATCH/x", ""),  # a variable this node does not set: refused, never guessed
    ],
)
def test_node_temp_base_from_the_pattern(pattern: str, expected: str) -> None:
    got = site.node_temp_base(
        pattern, "", "", False, "u", "/home/u", "7", "/local/job7", "", "", True
    )
    assert got == expected


def test_node_temp_base_order_after_the_pattern() -> None:
    def base(var: str, value: str, local: bool, tmpdir: str, scratch: bool) -> str:
        return site.node_temp_base("", var, value, local, "u", "/h", "7", "", "", tmpdir, scratch)

    assert base("LOCAL", "/ssd", True, "/t", True) == "/ssd/u"
    assert base("bad-name", "/ssd", True, "/t", True) == "/t"
    assert base("LOCAL", "", True, "/t", True) == "/t"
    assert base("", "", False, "/t", True) == "/scratch/u"
    assert base("", "", False, "/t", False) == "/tmp/u"


def test_runtimes() -> None:
    assert [
        site.runtime_command(r) for r in ("", "apptainer", "singularity", "podman", "pyxis")
    ] == ["apptainer", "apptainer", "singularity", "", ""]


# --- Python and bash agree -----------------------------------------------------------------------


def shell_resolve(profile: Any, env: dict[str, str], tmp: Path) -> dict[str, str] | None:
    path = tmp / "profile.json"
    path.write_text(profile if isinstance(profile, str) else json.dumps(profile))
    script = (
        '. "$1"; if bee_site_resolve "$2"; then '
        'printf "%s\\t%s\\n" site "$BEE_SITE_ID" runtime "$BEE_SITE_RT" module "$BEE_SITE_MODULE" '
        'image "$BEE_SITE_IMAGE" node_temp "$BEE_SITE_TEMP"; '
        'else printf "%s\\n" "$BEE_SITE_WHY" >&2; exit 1; fi'
    )
    out = subprocess.run(
        ["bash", "-c", script, "_", str(SITE_SH), str(REPO)],
        capture_output=True,
        text=True,
        env={**env, "BEE_SITE_PROFILE": str(path)},
    )
    if out.returncode != 0:
        assert out.stderr.strip(), "a refusal says why"
        return None
    return dict(line.split("\t", 1) for line in out.stdout.splitlines())


def reference(profile: Any, env: dict[str, str]) -> dict[str, str] | None:
    try:
        if isinstance(profile, str):
            prof = site.SiteProfile.model_validate_json(profile)
        else:
            prof = site.SiteProfile.model_validate(profile)
    except ValidationError:
        return None
    user, home = env["USER"], env["HOME"]
    job = env.get("SLURM_JOB_ID", "")
    vals = (env.get("SLURM_TMPDIR", ""), env.get("L_SCRATCH", ""), env.get("TMPDIR", ""))
    store = prof.image_store.path if prof.image_store else ""
    folder = site.expand(site.container_dir(prof.containers_dir, store), user, home, job, *vals)
    scratch = Path("/scratch", user)
    writable = scratch.is_dir() and os.access(scratch, os.W_OK)
    var_value = env.get(prof.node_tmp_var, "") if prof.node_tmp_var else ""
    return {
        "site": prof.site,
        "runtime": site.runtime_command(prof.runtime),
        "module": prof.runtime_module,
        "image": site.engine_image(folder),
        "node_temp": site.node_temp_base(
            prof.node_tmp,
            prof.node_tmp_var,
            var_value,
            prof.tmpdir_is_node_local,
            user,
            home,
            job,
            *vals,
            writable,
        ),
    }


def _set(**changes: Any) -> Any:
    def apply(p: dict[str, Any]) -> dict[str, Any]:
        q = copy.deepcopy(p)
        for k, v in changes.items():
            if v is _DROP:
                q.pop(k, None)
            else:
                q[k] = v
        return q

    return apply


_DROP = object()

VARIANTS: dict[str, Any] = {
    "as-is": _set(),
    "singularity": _set(runtime="singularity"),
    "podman": _set(runtime="podman"),
    "no-runtime": _set(runtime=_DROP),
    "null-runtime": _set(runtime=None),
    "no-module": _set(runtime_module=""),
    "containers-dir": _set(containers_dir="/lab/images"),
    "containers-dir-home": _set(containers_dir="$HOME/images"),
    "containers-dir-relative": _set(containers_dir="images"),
    "containers-dir-unset-var": _set(containers_dir="$NOPE/images"),
    "no-image-store": _set(image_store=_DROP),
    "null-image-store": _set(image_store=None),
    "image-store-empty": _set(image_store={}),
    "image-store-no-folder": _set(image_store={"path": "claude-node22"}),
    "image-store-at-root": _set(image_store={"path": "/claude-node22"}),
    "image-store-user": _set(image_store={"path": "/lab/$USER/img/claude-node22"}),
    "node-tmp-slurm": _set(node_tmp="$SLURM_TMPDIR"),
    "node-tmp-slurm-job": _set(node_tmp="$SLURM_TMPDIR/hpcworker_$SLURM_JOB_ID"),
    "node-tmp-braces": _set(node_tmp="/local/${USER}/${SLURM_JOB_ID}"),
    "node-tmp-relative": _set(node_tmp="hpcworker_$SLURM_JOB_ID"),
    "node-tmp-root": _set(node_tmp="/hpcworker_$SLURM_JOB_ID"),
    "node-tmp-tmpdir": _set(node_tmp="$TMPDIR/x"),
    "var": _set(node_tmp="", node_tmp_var="LOCAL_SCRATCH"),
    "var-bad-name": _set(node_tmp="", node_tmp_var="bad-name"),
    "tmpdir-local": _set(node_tmp="", node_tmp_var="", tmpdir_is_node_local=True),
    "tmpdir-not-local": _set(node_tmp="", node_tmp_var="", tmpdir_is_node_local=False),
    "tmpdir-null": _set(node_tmp=None, node_tmp_var=None, tmpdir_is_node_local=None),
    # Refusals: both sides must refuse these.
    "runtime-number": _set(runtime=5),
    "runtime-tab": _set(runtime="apptainer\tx"),
    "module-newline": _set(runtime_module="a\nb"),
    "image-store-text": _set(image_store="/lab/img"),
    "image-store-path-number": _set(image_store={"path": 3}),
    "flag-text": _set(tmpdir_is_node_local="yes"),
    "flag-number": _set(tmpdir_is_node_local=1),
    "site-empty": _set(site=""),
    "site-null": _set(site=None),
    "no-site": _set(site=_DROP),
}

ENVS: dict[str, dict[str, str]] = {
    "plain": {},
    "slurm-tmpdir": {"SLURM_TMPDIR": "/local/job4242"},
    "all-set": {
        "SLURM_TMPDIR": "/local/job4242",
        "TMPDIR": "/cephfs/t",
        "L_SCRATCH": "/ls",
        "LOCAL_SCRATCH": "/ssd",
    },
}


@pytest.mark.parametrize("path", vendored(), ids=lambda p: p.stem)
@pytest.mark.parametrize("variant", sorted(VARIANTS))
@pytest.mark.parametrize("env_name", sorted(ENVS))
def test_bash_and_python_agree(path: Path, variant: str, env_name: str, tmp_path: Path) -> None:
    profile = VARIANTS[variant](load(path))
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(tmp_path / "home"),
        "USER": "student",
        "SLURM_JOB_ID": "4242",
        **ENVS[env_name],
    }
    assert shell_resolve(profile, env, tmp_path) == reference(profile, env)


@pytest.mark.parametrize("text", ["[1, 2]", "not json", '"wayne"'])
def test_bash_and_python_refuse_what_is_not_a_profile(text: str, tmp_path: Path) -> None:
    env = {"PATH": os.environ["PATH"], "HOME": str(tmp_path), "USER": "student"}
    assert shell_resolve(text, env, tmp_path) is None
    assert reference(text, env) is None


# --- no site's literal in the engine's code ------------------------------------------------------

# Prose fields and values every site shares carry no site's identity.
_PROSE = {"notes", "display_name", "session_title"}
_GENERIC_ROOTS = {"/tmp", "/dev", "/usr", "/etc", "/var", "/opt", "/home", "/scratch", "/proc"}


def _strings(value: Any, key: str = "") -> list[tuple[str, str]]:
    if isinstance(value, dict):
        return [s for k, v in value.items() if k not in _PROSE for s in _strings(v, k)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v, key)]
    return [(key, value)] if isinstance(value, str) and value else []


def site_literals(profile: dict[str, Any]) -> list[re.Pattern[str]]:
    """What spells this site: its hosts and domains, its path roots, its partitions, its QoS where
    it is a QoS, its module and host key, and its id as a word."""
    found: set[str] = set()
    words: set[str] = {profile["site"]}
    qos: set[str] = set()
    for key, text in _strings(profile):
        if key.startswith("qos"):
            qos.add(text)
        elif key.startswith("partition"):
            words.add(text)
        elif key == "submit_host":
            words.add(text)
        elif re.match(r"https?://", text):
            host = re.sub(r"https?://([^/:]+).*", r"\1", text)
            found.update({host, ".".join(host.split(".")[-2:])})
        elif text.startswith("/"):
            parts = [c for c in text.split("/") if c][:2]
            root = "/" + "/".join(parts)
            if len(parts) == 2 and "/" + parts[0] not in _GENERIC_ROOTS and "$" not in root:
                found.add(root)
        elif re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+", text):  # a host name
            found.update({text, ".".join(text.split(".")[-2:])})
        elif key in ("runtime_module", "ssh_host_key"):
            found.add(text)
    pats = [re.compile(re.escape(s)) for s in sorted(found)]
    pats += [re.compile(r"(?<![\w.-])" + re.escape(w) + r"(?![\w-])") for w in sorted(words)]
    pats += [re.compile(r"(?:qos[= ]|-q )" + re.escape(q) + r"\b") for q in sorted(qos)]
    return pats


def code_files() -> list[Path]:
    """Everything the engine runs or bakes into its image, and the pull every import folder holds;
    the vendored profiles and the pinned contract are the provider's data (the contract's vectors
    name a site's values on purpose), and the documents describe sites on purpose."""
    skip = {".md", ".json", ".pyc"}
    pulls = sorted(REPO.glob("*/pull.sh"))
    return sorted(
        p
        for r in (REPO / "src", REPO / "containers")
        for p in r.rglob("*")
        if p.is_file() and p.suffix not in skip and "__pycache__" not in p.parts
    ) + [REPO / "containers" / "managed-settings.json", *pulls]


def offences(lines: list[str]) -> list[str]:
    pats = [p for prof in vendored() for p in site_literals(load(prof))]
    return [line for line in lines if any(p.search(line) for p in pats)]


def test_the_lint_knows_wayne_state() -> None:
    # Make it fail on purpose first: each of these is how Wayne State used to be written into code.
    bad = [
        'image="${BEE_IMAGE:-/rs/rs_grp_oschome/shared/beethoven/containers/claude-verify.sif}"',
        'module load "${BEE_APPTAINER_MODULE:-apptainer/1.2.2}"',
        "srun -p secp --qos=secondary -t 1:00:00 --pty bash",
        "#SBATCH --partition=reqp",
        "ssh go0000@grid.wayne.edu",
        "OOD=https://ondemand.grid.wayne.edu",
        "PROFILE=wayne",
    ]
    assert offences(bad) == bad
    fine = [
        "scontrol requeue 123",  # a subcommand, not the QoS
        "a secondary reason",
        "/tmp/$USER/bee_x",
        "module load apptainer",
        "the wayne-state-pilot document",
    ]
    assert offences(fine) == []


def test_no_site_literal_in_the_engines_code() -> None:
    hits = []
    for path in code_files():
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if offences([line]):
                hits.append(f"{path.relative_to(REPO)}:{n}: {line.strip()}")
    assert hits == [], "\n".join(hits)


# --- the image build reads the same profile ------------------------------------------------------

BUILD_SH = REPO / "containers" / "build.sh"


def _fake_runtime(tmp: Path, name: str = "apptainer") -> tuple[Path, Path]:
    """A runtime that records each call's verb and the temp folder it was given under its own
    variable's name, and writes the image it builds."""
    bin_dir = tmp / "bin"
    bin_dir.mkdir(exist_ok=True)
    log = tmp / "runtime.log"
    fake = bin_dir / name
    var = "SINGULARITY_TMPDIR" if name == "singularity" else "APPTAINER_TMPDIR"
    fake.write_text(
        "#!/usr/bin/env bash\n"
        f'printf "%s|%s\\n" "$1" "${{{var}:-}}" >> "{log}"\n'
        'case "$1" in\n'
        '  build) for a in "$@"; do case "$a" in *.sif) : > "$a" ;; esac; done ;;\n'
        '  --version) echo "fake 0" ;;\n'
        "esac\n"
    )
    fake.chmod(0o755)
    return bin_dir, log


def _build(tmp: Path, *args: str, **env: str) -> subprocess.CompletedProcess[str]:
    base = {"PATH": os.environ["PATH"], "HOME": str(tmp / "home"), "USER": "student"}
    return subprocess.run(
        ["bash", str(BUILD_SH), *args], capture_output=True, text=True, env={**base, **env}, cwd=tmp
    )


def test_build_puts_its_temp_where_the_site_says(tmp_path: Path) -> None:
    bin_dir, log = _fake_runtime(tmp_path, "singularity")
    prof = tmp_path / "site.json"
    data = load(PROFILES / "wayne.json")
    prof.write_text(json.dumps({**data, "runtime": "singularity", "node_tmp": "$SLURM_TMPDIR"}))
    node = tmp_path / "node"
    out = _build(
        tmp_path,
        "--out",
        str(tmp_path / "out"),
        PATH=f"{bin_dir}:{os.environ['PATH']}",
        SLURM_JOB_ID="77",
        SLURM_TMPDIR=str(node),
        BEE_SITE_PROFILE=str(prof),
    )
    assert out.returncode == 0, out.stderr
    verb, tmpdir = log.read_text().splitlines()[0].split("|")
    assert verb == "build" and tmpdir.startswith(f"{node}/beethoven_build_77_")
    assert (
        not Path(tmpdir).parent.exists() and node.is_dir()
    )  # its own folder went, the site's stayed
    digest = (tmp_path / "out" / "claude-verify.digest").read_text()
    assert "singularity: fake 0" in digest
    assert "bee-grid.sh on this site reads /rs/" in out.stdout  # the lab's folder, named


def test_build_inside_slurm_needs_a_site_profile(tmp_path: Path) -> None:
    bin_dir, log = _fake_runtime(tmp_path)
    out = _build(
        tmp_path,
        "--out",
        str(tmp_path / "out"),
        PATH=f"{bin_dir}:{os.environ['PATH']}",
        SLURM_JOB_ID="77",
    )
    assert out.returncode == 1 and "no site profile" in out.stderr
    assert not log.exists()


def test_build_on_a_ci_runner_needs_none(tmp_path: Path) -> None:
    bin_dir, log = _fake_runtime(tmp_path)
    out = _build(
        tmp_path,
        "--out",
        str(tmp_path / "out"),
        "--allow-outside-slurm",
        PATH=f"{bin_dir}:{os.environ['PATH']}",
    )
    assert out.returncode == 0, out.stderr
    tmpdir = log.read_text().splitlines()[0].split("|")[1]
    assert tmpdir.startswith("/tmp/student/beethoven_build_local")
    assert not Path(tmpdir).parent.exists()
