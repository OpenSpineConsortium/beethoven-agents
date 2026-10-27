"""The interface standard's rule 2 for this repository (interface/README.md): the manifest,
interface/INTERFACE.json, declares every export and every import, interface/ holds nothing it does
not list, and each export says what the code really reads and writes: accounts.schema.json is
bee's own model printed, and usage.schema.json holds what bee's status-line hook writes, checked by
running the hook.

    pixi run --locked python tests/test_interface.py --write   rewrites accounts.schema.json
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
INTERFACE = REPO / "interface"
ACCOUNTS_SCHEMA = INTERFACE / "bee" / "accounts.schema.json"
USAGE_SCHEMA = INTERFACE / "bee" / "usage.schema.json"
KINDS = {"contract", "schema", "data", "python", "cli", "files", "program", "text"}
STANDARD = "https://github.com/OpenSpineConsortium/beethoven/blob/main/INTERFACES.md"
# The engine's direction (rule 5): beethoven-qa <- beethoven-agents <- the research pipeline, and
# the launcher's data beside it. Nothing of the research pipeline is ever taken here.
MAY_TAKE_FROM = {"OpenSpineConsortium/beethoven-qa", "OpenSpineConsortium/hpcworker"}


def manifest() -> dict[str, object]:
    data = json.loads((INTERFACE / "INTERFACE.json").read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def tracked() -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        capture_output=True,
        check=True,
    ).stdout
    return [f for f in out.decode("utf-8").split("\0") if f]


def covered(path: str, pattern: str) -> bool:
    """A path an export's pattern names: "dir/" every file under it, "*" within one part."""
    if pattern.endswith("/"):
        return path.startswith(pattern)
    parts, want = path.split("/"), pattern.split("/")
    return len(parts) == len(want) and all(_part(p, w) for p, w in zip(parts, want, strict=True))


def _part(part: str, pattern: str) -> bool:
    head, star, tail = pattern.partition("*")
    if not star:
        return part == pattern
    return len(part) >= len(head) + len(tail) and part.startswith(head) and part.endswith(tail)


def accounts_schema_text() -> str:
    from beethoven_agents.bee.accounts import RegistryFile

    return json.dumps(RegistryFile.model_json_schema(), indent=1) + "\n"


# --- the manifest --------------------------------------------------------------------------------


def test_manifest_names_this_repository_and_the_standard() -> None:
    m = manifest()
    assert set(m) == {"format", "name", "repository", "summary", "standard", "exports", "imports"}
    assert (m["format"], m["name"], m["standard"]) == (1, "beethoven-agents", STANDARD)
    assert m["repository"] == "OpenSpineConsortium/beethoven-agents"


def test_every_export_is_well_formed_and_names_files() -> None:
    exports = manifest()["exports"]
    assert isinstance(exports, list)
    files = tracked()
    for e in exports:
        assert set(e) == {"id", "kind", "version", "summary", "paths", "consumers"}, e
        assert e["kind"] in KINDS and isinstance(e["version"], int) and e["version"] >= 1, e
        for pattern in e["paths"]:
            assert any(covered(f, pattern) for f in files), f"{e['id']}: {pattern} names no file"
    assert len({e["id"] for e in exports}) == len(exports)


def test_every_import_is_a_folder_with_its_record() -> None:
    imports = manifest()["imports"]
    assert isinstance(imports, list)
    for i in imports:
        assert set(i) == {"repository", "export", "version", "into", "origin"}, i
        assert i["repository"] in MAY_TAKE_FROM, i
        assert (REPO / i["into"]).is_dir() and i["origin"] == f"{i['into']}/ORIGIN", i
        assert isinstance(i["version"], int) and i["version"] >= 1, i


def test_interface_holds_nothing_unlisted() -> None:
    exports = manifest()["exports"]
    assert isinstance(exports, list)
    patterns = [p for e in exports for p in e["paths"]]
    own = {"interface/INTERFACE.json", "interface/README.md"}
    for f in tracked():
        if f.startswith("interface/") and f not in own:
            assert any(covered(f, p) for p in patterns), f"{f} is in interface/ but not exported"


def test_the_pattern_rule() -> None:
    assert covered("interface/bee/accounts.schema.json", "interface/bee/")
    assert covered("framework/profiles/wayne.json", "framework/profiles/*.json")
    assert not covered("framework/profiles/sub/wayne.json", "framework/profiles/*.json")
    assert not covered("framework/profiles/README.md", "framework/profiles/*.json")


# --- the registry export -------------------------------------------------------------------------


def test_accounts_schema_is_bees_own_model() -> None:
    assert ACCOUNTS_SCHEMA.read_text(encoding="utf-8") == accounts_schema_text(), (
        "bee's accounts.json model changed: run `pixi run --locked python tests/test_interface.py "
        "--write`, and raise the export's version if a reader must change"
    )


def fits(value: object, schema: dict[str, object]) -> bool:
    """The part of JSON Schema usage.schema.json uses: types, required, no other keys, bounds."""
    kinds = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
    if not any(_is(value, k) for k in kinds):
        return False
    if isinstance(value, dict):
        props = schema["properties"]
        assert isinstance(props, dict)
        return set(value) == set(props) == set(schema["required"]) and all(
            fits(value[k], props[k]) for k in value
        )
    if isinstance(value, int) and not isinstance(value, bool):
        return schema.get("minimum", value) <= value <= schema.get("maximum", value)
    return True


def _is(value: object, kind: object) -> bool:
    checks = {
        "object": lambda v: isinstance(v, dict),
        "string": lambda v: isinstance(v, str),
        "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "null": lambda v: v is None,
    }
    return checks[str(kind)](value)


def test_usage_schema_holds_what_the_status_line_writes(tmp_path: Path) -> None:
    from beethoven_agents.bee import handoff

    schema = json.loads(USAGE_SCHEMA.read_text(encoding="utf-8"))
    env = {
        "BEE_ACCOUNT": "a",
        "BEE_REGISTRY_DIR": str(tmp_path / "registry"),
        "NO_COLOR": "1",
        "BEETHOVEN_STATE_DIR": str(tmp_path / "state"),
    }
    windows: list[dict[str, object]] = [
        {
            "five_hour": {"used_percentage": 93.4, "resets_at": 1_800_000_000},
            "seven_day": {"used_percentage": 50, "resets_at": 1_900_000_000},
        },
        {"five_hour": {"used_percentage": 12, "resets_at": 1_800_000_000}},
        {
            "five_hour": {"used_percentage": 1e300, "resets_at": 10**30},
            "seven_day": {"used_percentage": "nan"},
        },
    ]
    for n, limits in enumerate(windows):
        payload = {
            "rate_limits": limits,
            "cwd": str(tmp_path),
            "session_id": f"s{n}" if n else None,
        }
        handoff._statusline(payload, env)
        written = json.loads((tmp_path / "registry" / "usage" / "a.json").read_text())
        assert fits(written, schema), written
    assert not fits({**written, "extra": 1}, schema) and not fits({**written, "label": 1}, schema)


if __name__ == "__main__" and sys.argv[1:] == ["--write"]:
    ACCOUNTS_SCHEMA.write_text(accounts_schema_text(), encoding="utf-8")
    print(f"wrote {ACCOUNTS_SCHEMA.relative_to(REPO)}")
