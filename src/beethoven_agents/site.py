"""The site profile, read as data: what the engine takes from the deployment it runs on.

A deployment is one lab's Beethoven on one university's cluster. hpcworker composes one profile per
deployment (``framework/profiles/<id>.json`` there; the design is ``/mnt/project-files/sites/
DESIGN.md``, Linear BEE-198), and an account that installed the launcher keeps its own copy in
``~/.hpcworker/profile.json``. The engine reads either as data and never imports hpcworker
(plan/REPO_SPLIT.md section 2); ``profiles/`` holds the vendored copies with their ``ORIGIN``.

Four values come from it, so that nothing of one university is written into the engine's code:

- the container runtime (``apptainer`` or ``singularity``, the two whose ``exec`` takes the flags
  bee passes) and the module that puts it on the path;
- the folder the lab keeps its images in, and the engine's image there;
- the node-local folder a job's temp goes under. hpcworker's rule, kept here: the profile's
  pattern, then the site's own variable, then ``$TMPDIR`` only when the profile says it is
  node-local (at Wayne State it is CephFS), then ``/scratch/$USER``, then ``/tmp/$USER``.

This module is the reference. ``site.sh`` beside it is its twin in bash, because bee-grid.sh and
containers/build.sh must know the image and the runtime before any container can start; the tests
run both over every vendored profile and over variations of them and compare (tests/test_site.py).
A value that differs between the two is a bug in one of them, never a matter of taste.
"""

from __future__ import annotations

from beartype import beartype
from icontract import ensure, require
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr, field_validator

__all__ = [
    "ENGINE_IMAGE",
    "JOB_VARS",
    "RUNTIMES",
    "ImageStore",
    "SiteProfile",
    "container_dir",
    "engine_image",
    "expand",
    "node_temp_base",
    "runtime_command",
]

# The engine's image, built by containers/build.sh into the lab's image folder.
ENGINE_IMAGE = "claude-verify.sif"
# What bee runs its containers with: both take exec --containall --cleanenv --no-home --bind --env.
RUNTIMES = ("apptainer", "singularity")
# The job-id variables of the three schedulers hpcworker drives, and its own; all name one job.
JOB_VARS = ("SLURM_JOB_ID", "PBS_JOBID", "LSB_JOBID", "HPCW_JOB_ID")


def _plain(value: str) -> bool:
    """A value that can sit in one tab-separated field: site.sh hands values over as such."""
    return "\t" not in value and "\n" not in value and "\r" not in value


def _none_is_empty(value: object) -> object:
    return "" if value is None else value


class ImageStore(BaseModel):
    """Where the lab keeps the launcher's worker image; only its path matters here."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    path: StrictStr = ""

    @field_validator("path", mode="before")
    @classmethod
    def _null_path(cls, value: object) -> object:
        return _none_is_empty(value)

    @field_validator("path")
    @classmethod
    def _one_line(cls, value: str) -> str:
        if not _plain(value):
            raise ValueError("a site value is one line of text, without tabs")
        return value


class SiteProfile(BaseModel):
    """The fields of a composed profile the engine reads: the boundary where the file is checked.

    Unknown fields are ignored, as hpcworker ignores fields a later version adds. What it accepts
    is exactly what site.sh's reader accepts: a field the engine reads is text on one line (site.sh
    passes it as one tab-separated field) or null for empty, ``tmpdir_is_node_local`` is true,
    false or null, and nothing is coerced from another type. The model carries no logic: CrossHair
    does not construct a pydantic model (beethoven-qa's measurement of 2026-10-04), so the rules
    live in the functions below, which take its fields.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    site: StrictStr = Field(min_length=1)
    runtime: StrictStr = ""
    runtime_module: StrictStr = ""
    image_store: ImageStore | None = None
    # A lab-owned field the design adds (DESIGN.md section 4): the image folder, when it is not the
    # folder of image_store's path.
    containers_dir: StrictStr = ""
    node_tmp: StrictStr = ""
    node_tmp_var: StrictStr = ""
    tmpdir_is_node_local: StrictBool = False

    @field_validator(
        "runtime", "runtime_module", "containers_dir", "node_tmp", "node_tmp_var", mode="before"
    )
    @classmethod
    def _null_text(cls, value: object) -> object:
        return _none_is_empty(value)

    @field_validator("tmpdir_is_node_local", mode="before")
    @classmethod
    def _null_flag(cls, value: object) -> object:
        return False if value is None else value

    @field_validator(
        "site", "runtime", "runtime_module", "containers_dir", "node_tmp", "node_tmp_var"
    )
    @classmethod
    def _one_line(cls, value: str) -> str:
        if not _plain(value):
            raise ValueError("a site value is one line of text, without tabs")
        return value


# --- pure logic --------------------------------------------------------------------------------


@beartype
@require(
    lambda user, home, job, slurm_tmpdir, l_scratch, tmpdir: all(
        "$" not in v for v in (user, home, job, slurm_tmpdir, l_scratch, tmpdir)
    ),
    "the values put in are not themselves expanded again",
)
@ensure(lambda result, text: "$" in text or result == text, "a text without $ is unchanged")
@ensure(
    lambda result, text: result.count("$") <= text.count("$"),
    "expanding never adds a $: every reference left was in the text",
)
def expand(
    text: str, user: str, home: str, job: str, slurm_tmpdir: str, l_scratch: str, tmpdir: str
) -> str:
    """The few variables a profile path may name, replaced in hpcworker's order (its
    ``hpcw_expand_job_vars``), never by a shell: ``$USER``, ``$HOME``, the job id under any
    scheduler's name, and ``$SLURM_TMPDIR``, ``$L_SCRATCH`` and ``$TMPDIR`` when they are set.
    Each may be written ``$NAME`` or ``${NAME}``; anything else is left as written."""
    pairs = [("USER", user), ("HOME", home)] + [(v, job) for v in JOB_VARS]
    pairs += [
        (n, v)
        for n, v in (("SLURM_TMPDIR", slurm_tmpdir), ("L_SCRATCH", l_scratch), ("TMPDIR", tmpdir))
        if v
    ]
    for name, value in pairs:
        text = text.replace("${" + name + "}", value).replace("$" + name, value)
    return text


@beartype
@ensure(
    lambda result, containers_dir: not containers_dir or result == containers_dir,
    "the profile's own image folder wins",
)
@ensure(
    lambda result, containers_dir, image_store_path: (
        bool(containers_dir) or image_store_path.startswith(result)
    ),
    "otherwise the folder is a leading part of the worker image's path",
)
@ensure(
    lambda result, containers_dir, image_store_path: (
        bool(containers_dir) or "/" in image_store_path or result == ""
    ),
    "a worker image path without a folder names no folder",
)
def container_dir(containers_dir: str, image_store_path: str) -> str:
    """The lab's image folder: the profile's ``containers_dir``, else the folder of the worker image
    hpcworker runs (everything before its last ``/``), else empty when the profile names neither."""
    if containers_dir:
        return containers_dir
    return image_store_path.rpartition("/")[0]


def _resolved(path: str) -> bool:
    return path.startswith("/") and "$" not in path


@beartype
@ensure(
    lambda result, directory: (result == "") == (not _resolved(directory)),
    "no image unless the folder is absolute with every variable resolved",
)
@ensure(
    lambda result, directory: result == "" or result == directory + "/" + ENGINE_IMAGE,
    "the engine's image, by its one name, in that folder",
)
def engine_image(directory: str) -> str:
    """Where the engine's image is in the lab's image folder (containers/build.sh writes it there),
    given the folder after :func:`expand`; empty, refused, when the folder is relative or names a
    variable that did not resolve."""
    return directory + "/" + ENGINE_IMAGE if _resolved(directory) else ""


@beartype
@ensure(lambda result: result in RUNTIMES or result == "", "a runtime bee can drive, or none")
@ensure(lambda result, runtime: runtime not in RUNTIMES or result == runtime, "a known one is kept")
@ensure(
    lambda result, runtime: runtime != "" or result == "apptainer",
    "a profile that names none means Apptainer, as before",
)
def runtime_command(runtime: str) -> str:
    """The command bee runs containers with: the profile's runtime when it is one of
    :data:`RUNTIMES`, Apptainer when the profile names none, and empty (refused) for a runtime
    whose ``exec`` does not take bee's flags, such as podman or pyxis."""
    if runtime == "":
        return "apptainer"
    return runtime if runtime in RUNTIMES else ""


def _names_the_job(component: str) -> bool:
    return "$" in component and any(v in component for v in JOB_VARS)


def _var_declared(var_name: str, var_value: str) -> bool:
    """The site names a variable for node temp, and the job has it (a name that is not a shell
    variable's counts as unset, as ``${!name}`` cannot read it)."""
    return var_name.isascii() and var_name.isidentifier() and var_value != ""


def _last_resort(
    result: str,
    pattern: str,
    var_name: str,
    var_value: str,
    tmpdir_is_node_local: bool,
    tmpdir: str,
    user: str,
    scratch_writable: bool,
) -> bool:
    declared = (
        pattern != ""
        or _var_declared(var_name, var_value)
        or (tmpdir_is_node_local and tmpdir != "")
    )
    return declared or result == ("/scratch/" + user if scratch_writable else "/tmp/" + user)


@beartype
@require(
    lambda user: user != "" and "/" not in user and "$" not in user and _plain(user),
    "a user name is one path component",
)
@require(
    lambda home, job, slurm_tmpdir, l_scratch, tmpdir: all(
        "$" not in v for v in (home, job, slurm_tmpdir, l_scratch, tmpdir)
    ),
    "the values put in are not themselves expanded again",
)
@ensure(
    lambda result: result == "" or (result.startswith("/") and "$" not in result),
    "an absolute folder with every variable resolved, or empty: refused",
)
@ensure(
    _last_resort,
    "with nothing declared, never $TMPDIR: /scratch/$USER where the job may write, else /tmp/$USER",
)
def node_temp_base(
    pattern: str,
    var_name: str,
    var_value: str,
    tmpdir_is_node_local: bool,
    user: str,
    home: str,
    job: str,
    slurm_tmpdir: str,
    l_scratch: str,
    tmpdir: str,
    scratch_writable: bool,
) -> str:
    """The node-local folder a job of this site puts its temp under; the caller makes one folder of
    its own inside it, per call, and removes only that.

    ``pattern`` is the profile's ``node_tmp`` as written. When its last component names the job, it
    is hpcworker's own job folder (``hpcworker_$SLURM_JOB_ID`` at Wayne State), which is not the
    engine's, so the engine's goes beside it; a pattern that names no job folder
    (``$SLURM_TMPDIR``) is the folder itself. ``var_value`` is the value, in the job, of the
    variable ``node_tmp_var`` names; ``scratch_writable`` whether ``/scratch/$USER`` is a folder
    the job may write. A pattern that does not resolve to an absolute folder is refused, never
    replaced by a guess."""
    if pattern:
        head, sep, last = pattern.rpartition("/")
        raw = head if sep and _names_the_job(last) else pattern
        base = expand(raw, user, home, job, slurm_tmpdir, l_scratch, tmpdir)
    elif _var_declared(var_name, var_value):
        base = var_value + "/" + user
    elif tmpdir_is_node_local and tmpdir:
        base = tmpdir
    elif scratch_writable:
        base = "/scratch/" + user
    else:
        base = "/tmp/" + user
    return base if _resolved(base) else ""
