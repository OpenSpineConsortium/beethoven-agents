# beethoven-agents

The **nested agentic framework** of the Beethoven engine: the hermetic Apptainer image every engine
job runs in, its managed settings and the PreToolUse guard baked into it, the student's own accounts
and the super-master lease, and the orchestration of masters, satellites and headless `claude -p`
steps as Slurm jobs on the grid.

It is one of three repositories: `beethoven-qa` (how code is written and proven), this one, and the
research pipeline (REFORMS, CLAIM, the studies). They depend in one direction only,
qa <- agents <- research. This repository carries a pinned copy of beethoven-qa at
`vendor/beethoven-qa/` and nothing of the research pipeline. It is the compute peer of the
Beethoven launcher (`hpcworker` + `beethoven-extension`), which is the student's interactive Remote
Control worker.

Beethoven runs Claude Code and is not an Anthropic product; "Claude" and "Claude Code" are
Anthropic's marks, used here to say what it runs; "Open OnDemand" is the mark of its publisher.
Vendor: Gregory Schwing, trading as OpenSpineConsortium. Private; the code is proprietary.

## What is settled

- **D1:** every step runs on a flat-rate Claude plan held in the student's own name. No pooled or
  commercial API keys, no gateway, no usage credits, ever. Nothing here reads, copies, prints or
  relays a credential; the engine starts Claude Code where the student's own sign-in already is and
  reads `claude auth status`.
- **D3:** orchestration is Metaflow with `metaflow-slurm`, a plain `sbatch` adapter underneath first.
- **D4:** several accounts of one person, one sign-in directory and one master job per account, one
  super-master lease at a time (`docs/ACCOUNTS.md`).

`CLAUDE.md` holds the rest: the launcher's non-negotiables, the token economy, accounts, parallel
work and what is measured.

## Switching accounts: `bee`

`bee` lists the student's own Claude accounts, one sign-in directory each, and moves a piece of work
from one to the next with the State Management guide's hand-off file, the same way on a laptop
(Windows, macOS, Linux) and on a compute node inside the image (`bee-grid.sh`). Setup and daily use:
`docs/bee/RUNBOOK.md`; what was taken from the guide and what was changed: `docs/bee/STATE_HANDOFF.md`.

```sh
bee account add work         # Claude Code's own sign-in, once, into ~/.beethoven/accounts/work/claude
bee run work                 # Claude Code on that account, with the hand-off hooks and status line
bee continue                 # after a usage limit or /handoff: the next account picks up the work
```

## Use

```sh
pixi install --locked     # the exact environment from the lock
pixi run --locked gate    # lint, typecheck, tests, beethoven-qa's CrossHair/Z3 gate, vendor-check
pixi run hooks            # the pre-push hook runs the same gate before anything leaves the machine
```

The image is built on a compute node inside a Slurm job, never on the login node
(`containers/README.md`).
