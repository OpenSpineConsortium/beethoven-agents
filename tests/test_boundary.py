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


def pinned() -> list[dict[str, object]]:
    """The imports this repository's tests hold to their ORIGIN: all but beethoven-qa's copy, which
    keeps its own record (ref, commit, tree digest) and its own check, `pixi run --locked
    vendor-check`, which the gate runs."""
    return [i for i in imports() if i["repository"] != "OpenSpineConsortium/beethoven-qa"]


def test_beethoven_qa_is_left_to_its_own_check() -> None:
    qa = [i for i in imports() if i not in pinned()]
    assert qa and {i["into"] for i in qa} == {"vendor/beethoven-qa"}
    for imp in qa:
        assert origin_lines(imp)[0] == f"repository: {imp['repository']}"


@pytest.mark.parametrize("imp", pinned(), ids=lambda i: f"{i['into']}:{i['export']}")
def test_each_import_matches_its_origin(imp: dict[str, object]) -> None:
    lines = origin_lines(imp)
    assert lines[0] == f"repository {imp['repository']}"
    assert re.fullmatch(r"commit [0-9a-f]{40}", lines[1])
    assert lines[2] == f"export {imp['export']} {imp['version']}"
    files = [line.split(" ", 2)[2] for line in lines[3:]]
    assert all(re.fullmatch(r"sha256 [0-9a-f]{64} \S+", line) for line in lines[3:])
    assert files == sorted(files) and len(set(files)) == len(files)
    assert present(REPO / str(imp["into"])) == recorded(lines), (
        f"{imp['into']} differs from its ORIGIN: take a new copy with its pull.sh"
    )


def test_every_import_folder_holds_the_one_pull() -> None:
    # One script, which reads its import from the manifest, so a fix made to one reaches each.
    scripts = {str(i["into"]): REPO / str(i["into"]) / "pull.sh" for i in pinned()}
    assert len(scripts) == len(pinned())  # one folder per import
    first = next(iter(scripts.values())).read_bytes()
    for into, script in scripts.items():
        assert script.read_bytes() == first, f"{into}/pull.sh differs from the others"
        assert os.access(script, os.X_OK), into


# --- rule 3: the pull, against a stand-in for gh -------------------------------------------------

SHA = "5" * 40
TOKEN = "gho_a-value-nothing-may-print"
FAKE_GH = """#!/bin/bash
# A stand-in for gh: answers pull.sh's calls from $FAKE_GH_DIR and records what it was asked.
printf '%s\\n' "$*" >> "$FAKE_GH_DIR/calls"
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


class Pull:
    """One import folder's pull.sh in a scratch repository that carries this repository's
    manifest, with gh answering from local files as hpcworker would."""

    def __init__(self, tmp: Path, into: str) -> None:
        self.gh = tmp / "gh-data"
        self.root = tmp / "repo"
        self.dest = self.root / into
        bin_dir = tmp / "bin"
        for d in (self.gh / "files", self.root / "interface", self.dest, bin_dir):
            d.mkdir(parents=True, exist_ok=True)
        (bin_dir / "gh").write_text(FAKE_GH)
        (bin_dir / "gh").chmod(0o755)
        shutil.copy(REPO / "interface" / "INTERFACE.json", self.root / "interface")
        shutil.copy(REPO / into / "pull.sh", self.dest / "pull.sh")
        (self.gh / "sha").write_text(SHA + "\n")
        (self.gh / "status").write_text("ahead\n")
        self.tree: list[str] = []
        self.exports: list[dict[str, object]] = []
        path = f"{bin_dir}:{os.environ['PATH']}"
        # gh's own sign-in includes the token variables, so they stay set; none may leak.
        self.env = {**os.environ, "PATH": path, "FAKE_GH_DIR": str(self.gh), "GH_TOKEN": TOKEN}

    def provide(self, path: str, data: bytes) -> None:
        (self.gh / "files" / path).parent.mkdir(parents=True, exist_ok=True)
        (self.gh / "files" / path).write_bytes(data)
        self.tree.append(path)
        # in the order given, so a test can hand the pull a listing that is not sorted
        (self.gh / "tree").write_text("\n".join(self.tree) + "\n")

    def offer(self, export: str, version: int, paths: list[str]) -> None:
        self.exports = [e for e in self.exports if e["id"] != export]
        self.exports.append({"id": export, "version": version, "paths": paths})
        manifest = json.dumps({"exports": self.exports}).encode()
        if "interface/INTERFACE.json" in self.tree:
            (self.gh / "files" / "interface" / "INTERFACE.json").write_bytes(manifest)
        else:
            self.provide("interface/INTERFACE.json", manifest)

    def run(self, *args: str) -> subprocess.CompletedProcess[str]:
        done = subprocess.run(
            ["bash", str(self.dest / "pull.sh"), *args],
            capture_output=True,
            text=True,
            env=self.env,
            stdin=subprocess.DEVNULL,
        )
        calls = (self.gh / "calls").read_text() if (self.gh / "calls").exists() else ""
        assert TOKEN not in calls + done.stdout + done.stderr  # never in argv, never printed
        return done

    def names(self) -> list[str]:
        return sorted(p.relative_to(self.dest).as_posix() for p in self.dest.rglob("*"))


def test_pull_takes_only_the_export_at_a_merged_commit(tmp_path: Path) -> None:
    pull = Pull(tmp_path, "profiles")
    ours = (REPO / "profiles" / "wayne.json").read_bytes()
    pull.provide("framework/profiles/wayne.json", ours)
    pull.provide("framework/profiles/README.md", b"not a profile\n")
    pull.provide("framework/lib/profile.py", b"print('never taken')\n")
    pull.offer("profiles", 1, ["framework/profiles/*.json"])
    (pull.dest / "old.json").write_text("{}\n")
    out = pull.run()
    assert out.returncode == 0, out.stderr
    assert (pull.dest / "wayne.json").read_bytes() == ours
    assert pull.names() == ["ORIGIN", "old.json", "pull.sh", "wayne.json"]  # nothing deleted
    record = (pull.dest / "ORIGIN").read_text().splitlines()
    head = ["repository OpenSpineConsortium/hpcworker", f"commit {SHA}", "export profiles 1"]
    assert record[:3] == head
    # the same bytes as this checkout's copy, recorded the same way
    profiles = next(i for i in pinned() if i["into"] == "profiles")
    assert recorded(record) == recorded(origin_lines(profiles))
    assert "export any more: profiles/old.json (remove it in a reviewed commit)" in out.stdout
    calls = (pull.gh / "calls").read_text()
    assert f"compare/{SHA}...main" in calls  # the commit against the default branch


def test_pull_lands_a_folder_export_below_its_folder_sorted(tmp_path: Path) -> None:
    pull = Pull(tmp_path, "contract")
    for path in ("interface/contract/vectors/b.json", "interface/contract/vectors/a.json",
                 "interface/contract/rules.json", "interface/contract/cli.json"):  # fmt: skip
        pull.provide(path, json.dumps({"from": path}).encode())
    pull.provide("interface/testbed/fakebin/sbatch", b"#!/bin/sh\n")
    pull.offer("contract", 1, ["interface/contract/"])
    pull.offer("testbed", 1, ["interface/testbed/"])
    out = pull.run()
    assert out.returncode == 0, out.stderr
    landed = ["cli.json", "rules.json", "vectors/a.json", "vectors/b.json"]
    record = (pull.dest / "ORIGIN").read_text().splitlines()
    assert record[2] == "export contract 1"
    assert [line.split(" ", 2)[2] for line in record[3:]] == landed  # sorted by path
    assert present(pull.dest) == recorded(record)
    assert sorted(set(pull.names()) - {"vectors"}) == sorted(["ORIGIN", "pull.sh", *landed])
    assert json.loads((pull.dest / "vectors" / "a.json").read_text()) == {
        "from": "interface/contract/vectors/a.json"
    }


def test_pull_refuses_what_main_does_not_hold(tmp_path: Path) -> None:
    pull = Pull(tmp_path, "profiles")
    pull.provide("framework/profiles/wayne.json", b"{}\n")
    pull.offer("profiles", 1, ["framework/profiles/*.json"])
    for status in ("behind", "diverged"):  # main is behind the commit, or apart from it
        (pull.gh / "status").write_text(status + "\n")
        out = pull.run("--ref", "claude/some-branch")
        assert out.returncode == 1 and "take only what was merged" in out.stderr
    (pull.gh / "status").write_text("identical\n")
    pull.offer("profiles", 2, ["framework/profiles/*.json"])
    out = pull.run()
    assert out.returncode == 1 and "does not offer profiles version 1" in out.stderr
    assert pull.names() == ["pull.sh"]  # nothing written any time
    assert pull.run("--from", str(tmp_path)).returncode == 2  # never from a checkout


def test_pull_takes_only_what_the_manifest_declares(tmp_path: Path) -> None:
    pull = Pull(tmp_path, "profiles")
    stray = pull.root / "elsewhere"
    stray.mkdir()
    shutil.copy(pull.dest / "pull.sh", stray / "pull.sh")
    out = subprocess.run(
        ["bash", str(stray / "pull.sh")], capture_output=True, text=True, env=pull.env
    )
    assert out.returncode == 1 and "not an import of interface/INTERFACE.json" in out.stderr
    assert not (pull.gh / "calls").exists()  # refused before gh was asked anything
