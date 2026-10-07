# hpcworker's contract, pinned

hpcworker's export `contract` version 1 (`interface/contract/` there), copied byte for byte: what a
client may type (`cli.json`), the lines it reads (`lines.json`), the files a worker writes (the
three JSON Schemas), the rules every program that starts or judges Claude Code applies
(`rules.json`), and the vectors hpcworker's real framework printed and wrote (`vectors/`). This
folder is one import of `interface/INTERFACE.json`, under the interface standard's rule 3
(`interface/README.md`).

- What the engine reads: `rules.json`, and only in its tests. bee and the guard keep their own
  lists in code, because the image and a laptop's bee run without this folder, and `tests/bee/`
  holds them to it: every name in `credential_variables` is one bee strips, the guard refuses and
  the image unsets; `agent_markers` is exactly bee's and `bee-grid.sh`'s list; every one of
  `signin_cases` goes through bee's own reading of `claude auth status` with its verdict asserted;
  and the image's managed settings set none of `remote_control_variables`. bee drives no hpcworker
  command and reads no file a worker writes, so the rest of the export has no reader here yet.
- `ORIGIN` names the hpcworker commit the files were read at (on hpcworker's `main`), the export and
  its version, and each file's sha256, sorted by path. `tests/test_boundary.py` fails when a file
  differs from its record, the folder holds a file the record does not list, or the record names
  another export or version than the import.
- `bash contract/pull.sh [--ref REF]` refreshes the files and the record from GitHub, through `gh`
  and the person's own sign-in, from a commit hpcworker's `main` contains, taking only the files
  hpcworker's `interface/INTERFACE.json` lists under `contract` at that commit. It is the same
  script as `profiles/pull.sh`. It never reads a checkout of hpcworker and never deletes: a file the
  export no longer has is listed for a person to remove in a reviewed commit. Never edit a file
  here; a change is hpcworker's, in a pull request there, and arrives with the next pull.
