# Coming back after a reboot

After the hub machine reboots, the hub comes back on its own: it is a systemd
user service, and lingering is on, so it starts at boot without a login. Its
state is in SQLite. What does not come back is tmux and the agents running in
it. This page covers bringing those back.

## Why tmux-resurrect is not enough

tmux-resurrect saves sessions, windows, pane layout, and each pane's working
directory to `~/.local/share/tmux/resurrect/`, and only when you press the
save key (no tmux-continuum here, so the newest save is whenever you last
pressed it). On restore it rebuilds the layout and restarts only the programs
listed in `@resurrect-processes` (here just `ssh`). A Claude or Codex pane
comes back as a shell in the right directory.

To continue an agent you then have to pick its conversation, and the
directory doesn't say which: many agents run in `~/agent-swarm` or
`~/oa/marin`, and `claude --continue` takes the newest conversation in that
directory, which is usually the wrong one. Pane ids (`%12`) also restart from
`%0` in a new tmux server, so nothing that remembers a pane id is valid
after a reboot.

## What agent-swarm does

The hub already knows, for each registered agent, its harness session id:
the id `claude --resume`, `codex resume`, `pi --session`, and
`hermes --resume` take. That id names one conversation exactly.
Codex agents are always restarted with `codex resume ID --yolo`.

`agent-swarm snapshot` saves this machine's tmux layout to
`~/.agent-swarm/snapshots/<time>.json`: every session, window (index, name,
layout), and pane (index, working directory), and for each pane running a
registered agent, its handle, harness, session id, and model. A snapshot
identical to the newest one is not written again; the newest 100 are kept.

`agent-swarm restore` reads the newest snapshot taken under an earlier tmux
server (snapshots of the new, near-empty server after the reboot are
skipped) and prints what it would do. `agent-swarm restore --apply` does it:

- creates each missing session and window at its old index, splits it into
  its old panes in their old directories, and applies the saved layout;
- types the resume command into each agent's pane, 5 seconds apart
  (`--stagger`), with the same flags as a dashboard spawn: Claude in auto
  permission mode, Codex with `--yolo`.

Each resumed harness re-registers from its startup hook with the same session
id, and the hub gives it back its handle, team, and history, so the new pane
ids do not matter.

Restore is safe to run more than once, and alongside tmux-resurrect:

- It never resumes a session that is already running: one the hub sees alive
  in a pane, or one whose id is on a running process's command line. Two
  processes on one session would both write its transcript.
- It does not reshape an existing window. In a window that exists, an agent
  goes back only into the pane at its old position, and only if that pane is
  a bare shell (as tmux-resurrect leaves it). A pane running anything else is
  left alone, and the plan says so.
- Pane numbering is restored even if the current `pane-base-index` differs.
  If creating or splitting a window fails, its remaining steps are skipped;
  other windows continue. The shell is checked again immediately before a
  launch, and each saved session id is launched at most once per plan.

## Use

Install once (the timer takes a snapshot every 5 minutes):

```bash
cp ~/agent-swarm/systemd/agent-swarm-snapshot.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now agent-swarm-snapshot.timer
agent-swarm snapshot          # take one now; prints sessions, panes, agents
```

After a reboot:

```bash
agent-swarm restore           # dry run: the plan and each resume command
agent-swarm restore --apply   # do it
tmux attach
```

`agent-swarm restore --from ~/.agent-swarm/snapshots/<time>.json` restores an
older snapshot.

## Limits

- Only registered agents with a session id are resumed. A harness that never
  registered comes back as a shell in its directory. Pi sends its session id
  from the version of the Pi extension that ships with this change, so a Pi
  agent started before it has no id until it restarts.
- A resumed agent remembers its conversation, not what its shell was doing:
  background jobs, servers, and `sleep` loops it started are gone.
- The snapshot is up to 5 minutes old. An agent started in the last 5
  minutes before the reboot is missed; one stopped in that window comes back.
- Restore runs on the machine whose tmux it restores; each node keeps its own
  snapshots. The timer here is for Linux; a Mac node would need a launchd
  agent running `agent-swarm snapshot`.
- It does not start at boot by itself: an agent coming back costs memory and
  tokens, so restoring is a command you run.
