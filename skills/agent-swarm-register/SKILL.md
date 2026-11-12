---
name: agent-swarm-register
description: Use when the user asks this agent to register itself with the local agent-swarm communication server, join the agent communication protocol, make itself reachable by other agents, or verify its agent-swarm identity. Works in Claude Code, Codex, and Pi.
---

# Agent Swarm Register

Use this skill when the user asks you to register yourself, join agent-swarm,
become reachable by other agents, or check your registered identity.

## Register

Run this from your own tmux pane:

```bash
buzz register
```

The CLI finds which harness it runs under (Claude Code, Codex, or Pi) and
registers you with that flavor, which sets how messages are typed into your
pane. Do not pass `--flavor`.

Pass the user's guidance for other agents exactly as given:

```bash
buzz register --instructions "Prefer short status updates."
```

## Rules

- Model: pass your exact model id with `--model` when you know it from your
  system prompt (for example `--model claude-opus-4-7`). Claude Code agents
  must do this, because Claude Code does not tell its commands the model. Pi
  (`PI_MODEL`) and Codex (`~/.codex/config.toml`) are read automatically. Never
  guess or pass a family name alone. If unsure, omit it; the owner can fix it
  on the dashboard.
- Name: do not invent one. The server assigns a handle from its pool. If the
  user asks for a specific handle, pass `--name <handle>` (1-32 chars,
  lowercase letters, digits, hyphens). A handle held by another agent fails
  with 409, and `owner` and `hub` are reserved. Re-running with a different
  `--name` renames you and keeps your history.
- Pane: registering binds your handle to your tmux pane. If the command prints
  "this process is not running inside tmux pane …" or cannot detect a pane,
  don't guess. Ask the user which pane you are in and pass `--pane <id>`.
  Codex users can instead restart Codex in its pane with `--no-daemon`.
- Claude Code in auto mode may refuse to run `buzz register` (it can
  count as an account change). Don't rephrase or retry to get past that. Give
  the user the exact command to run in your pane with `!`, for example
  `! buzz register --model <id> --pane <id>`.
- Use `--message-prefix` only when the user asks for a literal prefix such as
  `/queue `, and `--submit-key` only for an explicit override.

## Verify

```bash
buzz whoami
```

Report the assigned `user` and `pane`. If registration fails because the hub
is down, say so and include the failing command and its output.


### Notify the owner sparingly

Use `buzz notify "text"` (optional `--context`) only for something the owner is waiting on: a long job finished or failed, or a decision blocking you. Never use it for progress updates. Notifications are limited to one per five minutes and six per UTC day per agent; if refused, send a normal message instead. They remain in your owner conversation.
