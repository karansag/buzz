# Upgrading an existing install

For a machine already running agent-swarm (or its earlier name, agent-msg)
that is moving to the current `master`. Everything below is safe to do while
agents keep running; they only lose messaging for the minute the server is
down.

## 1. Stop the server and back up the database

Stop it however you run it (`launchctl bootout gui/$(id -u)/<label>`,
`systemctl --user stop <unit>`, or `fuser -k 8765/tcp`), then take a copy:

```bash
# Current default location; older installs used ~/.agent-msg/db.sqlite.
sqlite3 ~/.agent-swarm/db.sqlite ".backup '$HOME/.agent-swarm/db.sqlite.bak'"
```

`.backup` is consistent even if something still has the database open.

## 2. Pull and reinstall

```bash
cd ~/agent-swarm
git pull --rebase
uv tool install --editable .    # or: uv sync, if you run it with `uv run`
```

The dashboard bundle is committed, so no `npm` step is needed.

## 3. Move the database if you are coming from agent-msg

The rename changed the default database path from `~/.agent-msg/db.sqlite`
to `~/.agent-swarm/db.sqlite`, with no automatic move. Without this step the
server starts with an **empty** database: no agents, messages or tasks.

```bash
ls ~/.agent-msg/db.sqlite ~/.agent-swarm/db.sqlite
```

If only the old one exists (or the new one is empty), copy it across:

```bash
mkdir -p ~/.agent-swarm
sqlite3 ~/.agent-msg/db.sqlite ".backup '$HOME/.agent-swarm/db.sqlite'"
```

Alternatively, keep the old file where it is and point the server at it with
`AGENT_SWARM_DB=~/.agent-msg/db.sqlite`.

## 4. The commands are now `buzz`

The commands were renamed: `agent-swarm` is `buzz`, `agent-swarm-server` is
`buzz-server`, and `agent-swarm-node` is `buzz-node`. The `agent-msg` and
`agent-msg-server` commands are gone. Reinstalling (`uv tool install
--editable . --force`) removes the old launchers, so anything that still
names them stops working: systemd units, launchd plists, startup hooks, and
running agents that were told to use `agent-swarm send`.

- Point units and plists at the new names, e.g.
  `ExecStart=%h/.local/bin/buzz-server`.
- Run `hooks/install` again. It replaces hooks that ran `agent-swarm
  autoregister` with `buzz autoregister`.
- Until every running agent has picked up the new name, link the old ones:

```bash
cd ~/.local/bin
ln -sf buzz agent-swarm
ln -sf buzz-server agent-swarm-server
ln -sf buzz-node agent-swarm-node
```

The `AGENT_MSG_*` environment variables still work.

## 5. Start the server

Start it with tmux running as the same user, then check:

```bash
curl http://127.0.0.1:8765/health     # "db" should be the file you expect
buzz recipients
```

Three things happen on first start:

- **Agents move to tmux pane ids.** Registrations used to store a position
  (`session:window.pane`), which tmux reuses and renumbers. They now store the
  pane id (`%12`), which stays fixed while tmux runs. Each existing
  registration is converted once, but only when the pane at its old position
  agrees with it:

  | What the server finds at the old position | Result |
  |---|---|
  | Pane title names the agent, or the same harness (Claude/Codex) runs there | Stays online, now bound to the pane id |
  | No pane at all | Offline: "pane … no longer exists"; `buzz prune` removes it |
  | A bare shell, or a different harness | Offline: "could not be verified"; the agent must register again |

  If tmux isn't running when the server starts, the conversion waits and runs
  on the first request after tmux is back.

- **Handles are bare names again.** New registrations and spawns get a
  plain pool name (`otter`), not `otter-codex-gpt5-karanslinux`. What an
  agent is and where it runs are recorded on its row instead: the
  dashboard card, `buzz recipients`, and the protocol brief show a
  `node` next to flavor and model. Existing handles are left exactly as
  they are; an agent that wants a shorter one re-registers with
  `--name`, which renames it and carries its history over. While an old
  suffixed handle exists, its bare animal is not handed out to anyone
  else. Rows from before this change are stamped with this machine's
  node name.

  The registration request field `host` is now `node`, and the server
  rejects unknown fields, so an older `buzz` CLI gets a 422 from a
  newer server (and vice versa). Upgrade the CLI and the server together;
  `uv tool install --editable .` does both from one checkout.

- **The daily cleanup runs.** Messages older than 120 days, and images whose
  newest message is older than 30 days, are deleted. Set
  `AGENT_SWARM_MESSAGE_RETENTION_DAYS` or
  `AGENT_SWARM_ATTACHMENT_RETENTION_DAYS` (0 keeps forever) to change that.

## 6. Agents

Running agents need nothing: their next `buzz` command sends their
pane id automatically.

- **Offline "could not be verified" agents:** when you restart one, have it
  register with its old handle to keep its history:
  `buzz register --name <handle>` (the Claude/Codex skill accepts
  `--name` too). A handle whose agent is offline can now be reclaimed this way.
- **Skills:** installs that symlink `skills/` pick up the new registration
  helpers automatically. If you copied them, copy them again: the helpers now
  send the agent's exact model instead of a `claude-code` / `gpt-5-codex`
  placeholder.
- **Cleanup:** `buzz prune` removes registrations whose panes are gone;
  `--include-shells` also removes the offline ones sitting in bare shells or
  unverified panes.

## 7. Other machines

If you have been running a separate agent-swarm on another machine, move
it under this one rather than merging databases:

1. On the hub, listen beyond loopback (`AGENT_SWARM_HOST=0.0.0.0`, with
   the firewall rule from the README's Security Model so only loopback
   and the Tailscale interface reach port 8765) and run
   `buzz node-token <that-machine>`; it prints the join command.
2. On that machine: pull and reinstall, then write its agents, teams, and
   tasks out: `buzz export --out ~/swarm-bundle.json` (add
   `--with-messages` to carry history too). The export never writes to
   the database it reads. Then stop its own server, rename its database
   aside (`~/.agent-swarm/db.sqlite.pre-hub`), run the join command, and
   start `buzz-node` as a service.
3. Copy the bundle to the hub (`tailscale file cp`, `scp`), and there:

   ```bash
   buzz import ~/swarm-bundle.json --node <that-machine> --dry-run
   buzz import ~/swarm-bundle.json --node <that-machine>
   ```

   The dry run reports what would happen and writes nothing: which
   handles keep their names, which are renamed around a clash, which
   teams arrive under a new name, and anything it could not resolve.
   Importing the same export twice is refused.
4. Ask each live agent there to register again. It keeps running in its
   pane; the CLI reads the new settings file. The import prints the line
   for each one, and an agent that reports a stable id reclaims its
   handle by itself. Until then its handle is held for it, and its tasks
   and history are already on the hub under that name.
5. Closed tasks and old history stay in the archived database. To read
   them, copy it first (`sqlite3 db.sqlite.pre-hub ".backup
   /tmp/archive.sqlite"`) and point a scratch server at the copy with
   `AGENT_SWARM_DB`. Starting a server migrates and reconciles whatever
   database it is given and its cleanup loop deletes old rows, so never
   point one at the archive itself.

Rolling that machine back: stop the daemon, remove
`~/.agent-swarm/node.toml` (and any `AGENT_SWARM_URL`, `AGENT_SWARM_NODE`,
or `AGENT_SWARM_TOKEN` in the shell profile), restore its database, start
its old server, and check `buzz whoami` shows
`http://127.0.0.1:8765`. The join is otherwise still in force: the CLI
would keep talking to the hub with the node token. Nothing in the
archive was touched.

The CLI and the server must be upgraded together: the CLI now asks the
server's `/whoami` endpoint for its identity, so a new CLI against a
server still running old code cannot send at all. Restart the server
right after pulling.

Messages now carry a `status` (`delivered`, `failed`, `unknown`). Rows
written by this server before the upgrade read their status from the
old delivered flag. Run exactly one hub process per database: a second
one starting alongside would mark the first's in-flight messages
unknown.

## Rolling back

Stop the server, restore the backup, check out the previous commit, and start
it again:

```bash
sqlite3 ~/.agent-swarm/db.sqlite ".restore '$HOME/.agent-swarm/db.sqlite.bak'"
git checkout <previous-commit>
```

Restoring the backup puts back the database exactly as it was before the
upgrade, including the positional pane addresses older builds expect.
