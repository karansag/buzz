# README images

| File | What it shows | How it is made |
|------|---------------|----------------|
| `dashboard.gif` | the overview: hive, machines, team sidebar | `node demo/capture.mjs` |
| `agent-page.png` | one agent's page: terminal and owner thread | `node demo/capture.mjs` |
| `phone.png` | the overview and a full-screen chat on a phone | `node demo/capture.mjs` |
| `conversation.gif` | Claude Code and Codex talking over tmux | `vhs demo/conversation.tape` |

## Dashboard images

`capture.mjs` opens the built dashboard in headless Chromium with made-up
agents, tasks, and messages (all in the script), the same way the browser
tests do. It never contacts a hub. The GIF is a screen recording while
the script adds messages and finishes tasks.

```bash
npm ci && npm run build
google-chrome --version          # patched stable Chrome required
node demo/capture.mjs             # needs ffmpeg and ImageMagick (convert)
```

Rebuild first, so the images match the current dashboard. To change the
story, edit `makeState()` and `script` in `capture.mjs`.

## The tmux demo

`conversation.tape` drives a real Claude Code and a real Codex in two
tmux panes. Setup is hidden: it starts a throwaway hub on port 8799 with a
database in a temp dir, opens a tmux session `swarm-demo`, and has both
agents register. The recording starts when Claude is asked to send.

```bash
vhs demo/conversation.tape
```

Before you run it:

- `claude` and `codex` must be logged in, and the register skills
  installed (see the main README).
- Port 8799 and the tmux session name `swarm-demo` must be free.
- Your real hub is never touched: the panes get `AGENT_SWARM_URL` for the
  demo hub and an empty `AGENT_SWARM_CONFIG`.
- Both agents run without permission prompts
  (`--dangerously-skip-permissions`, `--yolo`). Only do this on a machine
  you trust.

The waits are fixed `Sleep`s, because agent output is not predictable. If a
step is cut off, raise the `Sleep` before it; if there is dead air, lower it.
The agents' answers differ on every run, so watch the result before
committing it.
