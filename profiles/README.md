# Site profiles, vendored as data

The composed site profiles of hpcworker (`framework/profiles/<id>.json` there), copied byte for byte.
One profile describes one deployment: a university's cluster and the lab that runs Beethoven on it.
The engine reads them as data and imports nothing of hpcworker (`plan/REPO_SPLIT.md` section 2); the
design of site modules is `/mnt/project-files/sites/DESIGN.md` (Linear BEE-198, BEE-219).

- `ORIGIN` names the hpcworker commit the files were read at and each file's sha256;
  `tests/test_site.py` fails when a file differs from its record, and, with `HPCWORKER_DIR` set to a
  checkout, when the record differs from that checkout.
- `bash profiles/pull.sh` refreshes the files and the record (`--from DIR` for a local checkout).
  Never edit a profile here; change it in hpcworker and pull.
- What reads them: `bee-grid.sh` and `containers/build.sh`, through `src/beethoven_agents/site.sh`,
  with `BEE_SITE=<id>` (otherwise they read the account's own `~/.hpcworker/profile.json`), and the
  site-literal lint in `tests/test_site.py`, which builds its list of forbidden values from them.
