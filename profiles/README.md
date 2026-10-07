# Site profiles, vendored as data

The composed site profiles of hpcworker (`framework/profiles/<id>.json` there, its export `profiles`
version 1), copied byte for byte. One profile describes one deployment: a university's cluster and
the lab that runs Beethoven on it. The engine reads them as data and imports nothing of hpcworker
(`plan/REPO_SPLIT.md` section 2); the design of site modules is `/mnt/project-files/sites/DESIGN.md`
(Linear BEE-198, BEE-219). This folder is one import of `interface/INTERFACE.json`, under the
interface standard's rule 3 (`interface/README.md`).

- `ORIGIN` names the hpcworker commit the files were read at (on hpcworker's `main`), the export and
  its version, and each file's sha256. The copy now here was taken before hpcworker published its
  manifest, so its record has no `export` line yet; the next pull writes one.
  `tests/test_boundary.py` fails when a file differs from its record or the folder holds a file the
  record does not list.
- `bash profiles/pull.sh [--ref REF]` refreshes the files and the record from GitHub, through `gh`
  and the person's own sign-in, from a commit hpcworker's `main` contains, taking only the files
  hpcworker's `interface/INTERFACE.json` lists under `profiles` at that commit. It never reads a
  checkout of hpcworker and never deletes: a profile hpcworker no longer has is listed for a person
  to remove in a reviewed commit. Never edit a profile here; change it in hpcworker and pull.
- What reads them: `bee-grid.sh` and `containers/build.sh`, through `src/beethoven_agents/site.sh`,
  with `BEE_SITE=<id>` (otherwise they read the account's own `~/.hpcworker/profile.json`), and the
  site-literal lint in `tests/test_site.py`, which builds its list of forbidden values from them.
