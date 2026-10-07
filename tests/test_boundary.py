"""The interface standard's rules 1 and 3 for this repository (interface/README.md): nothing here
reads, runs or copies a file of another Beethoven repository's checkout, and what it takes from one
is a pinned copy that matches its ORIGIN, fetched only by its folder's pull.sh.

A line that reaches a sibling checkout fails unless it is on the known list below with its reason,
and an entry that no longer matches fails too, so the list only shrinks. beethoven-qa's own boundary
command takes over these checks once this repository's pinned copy carries it (the re-pin to
beethoven-qa 2.0.0 or later); until then they are this file's.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SELF = Path(__file__).resolve().relative_to(REPO).as_posix()
# every other repository of the ecosystem, the names their checkouts had (the Desktop folders
# ashley and ashley-bridge), and the website's
OTHERS = (
    "beethoven", "beethoven-extension", "beethoven-desktop", "beethoven-qa", "beethoven-research",
    "beethoven-sites", "beethoven-base", "beethoven-vscode", "hpcworker", "ashley",
    "ashley-bridge", "openspineconsortium.github.io", "spinesurg-ct-nnunet",
    "u251-xenograft-rat-rnaseq-study",
)  # fmt: skip
_NAMES = "|".join(re.escape(n) for n in sorted(OTHERS, key=len, reverse=True))
# a path made from this checkout's parent: "../<repo>", or "$(dirname ...)/<repo>" and the like
SIBLING_PATH = re.compile(rf"(?:\.\./|\)/|\}}/)({_NAMES})(?![A-Za-z0-9_.-])")
# a variable whose value is another repository's checkout
CHECKOUT_VAR = re.compile(
    r"\b((?:HPCWORKER|ASHLEY|SITES|QA|BEETHOVEN_(?:SERVICE|QA|RESEARCH|SITES|EXTENSION|DESKTOP"
    r"|VSCODE|BASE|HUB))_DIR)\b"
)
# a clone of another repository of the organisation
CLONE = re.compile(
    rf"\b(?:git clone|gh repo clone)\b[^\n]*?OpenSpineConsortium/({_NAMES})(?![A-Za-z0-9_.-])",
    re.IGNORECASE,
)
CHECKOUT_ACTION_REPO = re.compile(r"^\s*repository:\s*\S+", re.MULTILINE)

# (file, what matched) -> why it is still here and who removes it. Empty since profiles/pull.sh
# lost --from and tests/test_site.py its HPCWORKER_DIR test (2026-10-07).
KNOWN: dict[tuple[str, str], str] = {}


def tracked() -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        capture_output=True,
        check=True,
    ).stdout
    return [f for f in out.decode("utf-8").split("\0") if f]


def text(rel: str) -> str:
    try:
        return (REPO / rel).read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return ""


def scanned(rel: str) -> bool:
    # Prose may name another repository; the pinned copy is beethoven-qa's own tree, held to its
    # record by vendor-check; this file names the others to look for them.
    return not (rel.endswith(".md") or rel.startswith("vendor/") or rel == SELF)


def reaches(rel: str) -> dict[tuple[str, str], str]:
    found: dict[tuple[str, str], str] = {}
    for n, line in enumerate(text(rel).split("\n"), 1):
        for rx in (SIBLING_PATH, CHECKOUT_VAR, CLONE):
            for m in rx.finditer(line):
                found.setdefault((rel, m.group(1)), f"{rel}:{n}: {line.strip()[:160]}")
    return found


# --- rule 1: the repository builds, tests and runs from its own tree -----------------------------


def test_nothing_reaches_a_sibling_checkout() -> None:
    found: dict[tuple[str, str], str] = {}
    for rel in filter(scanned, tracked()):
        found.update(reaches(rel))
    new = {k: v for k, v in found.items() if k not in KNOWN}
    assert new == {}, (
        "these lines reach another repository's checkout; take what is needed from that "
        "repository's interface instead (interface/README.md)"
    )
    assert sorted(k for k in KNOWN if k not in found) == [], "fixed: remove these from KNOWN"


def test_the_scan_sees_what_it_looks_for() -> None:
    # Each pattern on a line of the kind it exists for, and none on this repository's own names.
    assert SIBLING_PATH.search('cp "$(dirname "$HERE")/hpcworker/x" .')
    assert SIBLING_PATH.search("python ../beethoven-qa/tools/x.py")
    assert CHECKOUT_VAR.search('git -C "$HPCWORKER_DIR" show HEAD:x')
    assert CLONE.search("gh repo clone OpenSpineConsortium/beethoven-sites")
    own = (
        "/tmp/${USER}/hpcworker_${SLURM_JOB_ID}",
        "../beethoven-agents",
        "BEETHOVEN_STATE_DIR",
        "git clone https://github.com/OpenSpineConsortium/beethoven-agents",
    )
    for line in own:
        assert not any(rx.search(line) for rx in (SIBLING_PATH, CHECKOUT_VAR, CLONE)), line


def test_no_submodule_and_no_other_repository_checked_out_in_ci() -> None:
    assert not (REPO / ".gitmodules").exists()
    for rel in tracked():
        if rel.startswith(".github/workflows/"):
            assert not CHECKOUT_ACTION_REPO.search(text(rel)), (
                f"{rel} checks out another repository"
            )


# --- rule 3: each import is a pinned copy that matches its ORIGIN --------------------------------


def imports() -> list[dict[str, object]]:
    data = json.loads((REPO / "interface" / "INTERFACE.json").read_text(encoding="utf-8"))
    found = data["imports"]
    assert isinstance(found, list)
    return found


def origin_lines(imp: dict[str, object]) -> list[str]:
    return [line for line in (REPO / str(imp["origin"])).read_text().split("\n") if line]


def present(folder: Path) -> dict[str, str]:
    """Every file of an import's folder but its own three, with its sha256."""
    files = {}
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        rel = path.relative_to(folder).as_posix()
        if rel not in ("ORIGIN", "README.md", "pull.sh") and "__pycache__" not in rel:
            files[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def recorded(lines: list[str]) -> dict[str, str]:
    return {line.split(" ", 2)[2]: line.split(" ")[1] for line in lines if line[:7] == "sha256 "}


@pytest.mark.parametrize("imp", imports(), ids=lambda i: str(i["into"]))
def test_each_import_matches_its_origin(imp: dict[str, object]) -> None:
    lines = origin_lines(imp)
    if imp["repository"] == "OpenSpineConsortium/beethoven-qa":
        # beethoven-qa's copy keeps its own record (ref, commit, tree digest) and its own check,
        # `pixi run --locked vendor-check`, which the gate runs.
        assert lines[0] == f"repository: {imp['repository']}"
        return
    assert lines[0] == f"repository {imp['repository']}"
    assert re.fullmatch(r"commit [0-9a-f]{40}", lines[1])
    assert all(re.fullmatch(r"(repository|commit|export|sha256) .+", line) for line in lines)
    # A copy taken before its provider published INTERFACE.json has no export line; the next pull
    # writes one, and from then on it must name the import's export and version.
    exports = [line for line in lines if line.startswith("export ")]
    assert exports in ([], [f"export {imp['export']} {imp['version']}"])
    assert present(REPO / str(imp["into"])) == recorded(lines), (
        f"{imp['into']} differs from its ORIGIN: take a new copy with its pull.sh"
    )


# --- rule 3: the pull, against a stand-in for gh -------------------------------------------------

SHA = "5" * 40
FAKE_GH = """#!/bin/bash
# A stand-in for gh: answers pull.sh's calls from $FAKE_GH_DIR and records what it was asked.
printf '%s|%s\\n' "${GITHUB_TOKEN-unset}" "$*" >> "$FAKE_GH_DIR/calls"
url=""; for a in "$@"; do case "$a" in repos/*) url="$a" ;; esac; done
case "$url" in
  */commits/*) cat "$FAKE_GH_DIR/sha" ;;
  */compare/*) cat "$FAKE_GH_DIR/status" ;;
  */git/trees/*) cat "$FAKE_GH_DIR/tree" ;;
  */contents/*) p="${url#*/contents/}"; cat "$FAKE_GH_DIR/files/${p%%\\?ref=*}" ;;
  repos/*) echo main ;;
  *) exit 1 ;;
esac
"""
TREE = (
    "framework/lib/profile.py",
    "framework/profiles/README.md",
    "framework/profiles/wayne.json",
    "interface/INTERFACE.json",
)


class Pull:
    """profiles/pull.sh copied into a scratch folder, with gh answering from local files."""

    def __init__(self, tmp: Path) -> None:
        self.gh = tmp / "gh-data"
        self.dest = tmp / "profiles"
        files = self.gh / "files"
        bin_dir = tmp / "bin"
        for d in (files / "framework" / "profiles", files / "interface", self.dest, bin_dir):
            d.mkdir(parents=True)
        (bin_dir / "gh").write_text(FAKE_GH)
        (bin_dir / "gh").chmod(0o755)
        shutil.copy(REPO / "profiles" / "pull.sh", self.dest / "pull.sh")
        shutil.copy(REPO / "profiles" / "wayne.json", files / "framework" / "profiles")
        (files / "framework" / "profiles" / "README.md").write_text("not a profile\n")
        (self.gh / "sha").write_text(SHA + "\n")
        (self.gh / "status").write_text("identical\n")
        (self.gh / "tree").write_text("\n".join(TREE) + "\n")
        self.offer(1)
        path = f"{bin_dir}:{os.environ['PATH']}"
        self.env = {**os.environ, "PATH": path, "FAKE_GH_DIR": str(self.gh), "GITHUB_TOKEN": "x"}

    def offer(self, version: int) -> None:
        export = {"id": "profiles", "version": version, "paths": ["framework/profiles/*.json"]}
        (self.gh / "files" / "interface" / "INTERFACE.json").write_text(
            json.dumps({"exports": [export]})
        )

    def run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(self.dest / "pull.sh"), *args],
            capture_output=True,
            text=True,
            env=self.env,
            stdin=subprocess.DEVNULL,
        )

    def names(self) -> list[str]:
        return sorted(p.name for p in self.dest.iterdir())


def test_pull_takes_only_the_export_at_a_merged_commit(tmp_path: Path) -> None:
    pull = Pull(tmp_path)
    (pull.dest / "old.json").write_text("{}\n")
    out = pull.run()
    assert out.returncode == 0, out.stderr
    ours = REPO / "profiles" / "wayne.json"
    assert (pull.dest / "wayne.json").read_bytes() == ours.read_bytes()
    assert pull.names() == ["ORIGIN", "old.json", "pull.sh", "wayne.json"]  # nothing deleted
    record = (pull.dest / "ORIGIN").read_text().splitlines()
    head = ["repository OpenSpineConsortium/hpcworker", f"commit {SHA}", "export profiles 1"]
    assert record[:3] == head
    # the same bytes as this checkout's copy, recorded the same way
    profiles = next(i for i in imports() if i["into"] == "profiles")
    assert recorded(record) == recorded(origin_lines(profiles))
    assert "export any more: profiles/old.json (remove it in a reviewed commit)" in out.stdout
    calls = (pull.gh / "calls").read_text().splitlines()
    assert calls and all(c.startswith("unset|") for c in calls)  # the person's own sign-in only


def test_pull_refuses_what_main_does_not_hold(tmp_path: Path) -> None:
    pull = Pull(tmp_path)
    (pull.gh / "status").write_text("diverged\n")
    out = pull.run("--ref", "claude/some-branch")
    assert out.returncode == 1 and "take only what was merged" in out.stderr
    pull.offer(2)
    (pull.gh / "status").write_text("behind\n")
    out = pull.run()
    assert out.returncode == 1 and "does not offer profiles version 1" in out.stderr
    assert pull.names() == ["pull.sh"]  # nothing written either time
    assert pull.run("--from", str(tmp_path)).returncode == 2  # never from a checkout
