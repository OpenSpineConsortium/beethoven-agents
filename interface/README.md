# What beethoven-agents offers other repositories

This repository is one sealed unit of the Beethoven ecosystem. Another repository reaches it only
through what `INTERFACE.json` lists, at a version, through a copy pinned to a commit on `main`, and
never through a checkout of this tree (the interface standard:
https://github.com/OpenSpineConsortium/beethoven/blob/main/INTERFACES.md). Everything not listed is
private and may change in any pull request.

| Export | Kind | Version | What it is | Taken by |
| --- | --- | --- | --- | --- |
| `registry` | schema | 1 | `bee/accounts.schema.json`: bee's `accounts.json` version 1, printed from bee's own model (`RegistryFile` in `src/beethoven_agents/bee/accounts.py`); `bee/usage.schema.json`: `usage/<label>.json`, what bee's status-line hook writes (`src/beethoven_agents/bee/handoff.py`) | beethoven-desktop (both files), beethoven-vscode (`accounts.json`) |

What the two schemas cannot say, and bee holds to as well:

- Both files live in bee's registry folder: `$BEE_REGISTRY_DIR`, else `<$BEETHOVEN_HOME or
  ~/.beethoven>/engine` (an empty value counts as unset). bee replaces each file whole (a temporary
  file, then a rename), mode 0600, in folders it makes 0700, so each is a plain file, never a link.
- `accounts.json`: an absent file is an empty list. Labels are distinct and so are paths; a path is
  absolute, or null for Claude Code's default place (so at most one account is that); a resting
  time (`hibernate_until`) carries its zone, and bee writes it as `YYYY-MM-DDTHH:MM:SSZ`, before the
  year 10000. A list bee cannot read is one it refuses to rewrite.
- `usage/<label>.json`: written only while `BEE_ACCOUNT` names the account and Claude Code sent at
  least one of the two windows; `label` is that name as given.

Not exported, so private until listed here: bee's commands and the rows of `bee account list
--json` (beethoven-desktop and beethoven-vscode name some of them in their sentences),
`switches.log`, the folder layout of `~/.beethoven` (`docs/ACCOUNTS.md` section 2, prose), the
substrate image and its run contract (`containers/README.md`; the research pipeline will take it
when it builds its study image), and the guard and the managed settings baked into the image.

## What this repository takes

| From | Export | Version | Into | Record |
| --- | --- | --- | --- | --- |
| beethoven-qa | `package` | 1 | `vendor/beethoven-qa/` | `vendor/beethoven-qa/ORIGIN` in beethoven-qa's own form (repository, ref, commit, tree digest, file count), taken with its `vendor` command and checked by `pixi run --locked vendor-check` |
| hpcworker | `profiles` | 1 | `profiles/` | `profiles/ORIGIN` (repository, commit, export, one sha256 per file), taken with `profiles/pull.sh` and checked by `tests/test_boundary.py` |

beethoven-qa has not published its own `INTERFACE.json` yet, so `package` version 1 is the name
this manifest expects for the pinned copy; it is reconciled with beethoven-qa's manifest at the
re-pin to beethoven-qa 2.0.0. The profiles were copied before hpcworker published its manifest, so
their record names the commit on hpcworker's `main` the bytes equal and no `export` line; the next
pull writes one. The direction is the engine's: beethoven-qa <- beethoven-agents <- the research
pipeline, with the launcher's data beside it; nothing of the research pipeline is taken here.

## How a client takes the export

With its own `pull.sh` and its own `gh` sign-in, from a commit `main` contains, only the paths this
manifest lists for the export at that commit, into one folder with an `ORIGIN` record (`repository`,
`commit`, `export registry 1`, one `sha256` line per file); its own test run fails when the folder
differs from `ORIGIN`. Both files land at the folder's top (`interface/bee/accounts.schema.json` at
`accounts.schema.json`). A client never reads this repository's checkout and never imports its code.

## How the export changes here

1. The code and the export change in one pull request. `bee/accounts.schema.json` is printed, never
   written by hand: `pixi run --locked python tests/test_interface.py --write`. Until it is,
   `tests/test_interface.py` fails, so the model never moves silently. `bee/usage.schema.json` is
   written by hand, and `tests/test_interface.py` runs the real status-line hook and fails when what
   it writes leaves the schema.
2. The export's `version` goes up when a reader must change its code: a field removed, renamed or
   retyped, a value whose meaning changes. An additive change (a new optional field an older reader
   ignores) keeps the version. `accounts.json` carries its own `version` (1) too; a change that
   raises one raises the other.

## What checks it

- `tests/test_interface.py`: the manifest's shape and the standard it names; every export's paths
  name files and `interface/` holds nothing unlisted; every import is a folder with its record and
  comes from beethoven-qa or hpcworker; the two schemas against the model and the hook.
- `tests/test_boundary.py`: no tracked file reaches another repository's checkout (with a known
  list, empty today, that fails when an entry goes stale); no submodule and no other repository
  checked out in CI; each import equals its `ORIGIN`; `profiles/pull.sh` against a stand-in for
  `gh`. beethoven-qa's boundary command takes these over once the pinned copy carries it.
- `pixi run --locked vendor-check`: the beethoven-qa copy against its record.

All run in `pixi run --locked test` and `vendor-check`, so in the gate before every push and in CI.
