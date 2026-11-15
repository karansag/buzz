# Buzz update talk: outline

Material for a short follow-up to the Oct 27, 2026 intro talk
("Buzz: another bee-themed orchestrator", deck in `buzz-intro-deck`).
It covers what changed between Oct 27 and Nov 14, 2026: 73 commits,
about 12,000 lines added in `agent_swarm/` and `web/src/`.

Use the same Slidev setup as the intro deck (Open Athena theme). The
images are in `svg/`. Each slide below gives a title, a suggested layout, and
the body text. The text is a draft, so shorten it as needed.

---

## 1. Cover

- Layout: `cover`
- Title: **Buzz, three weeks later**
- Subtitle: Karan Sagar · Open Athena · <date of the talk>
- Image: the Buzz bee, as on the first deck's cover.

## 2. Recap in one slide

- Layout: `default`
- Title: **Last time**
- A small local hub knows every agent and its tmux pane.
- `buzz send --to stoat --message "..."` types into stoat's prompt.
- It has tasks, teams with queens, and a dashboard that works on a phone.
- Footnote: the commands are now `buzz`, `buzz-server` and `buzz-node`.
  The `agent-swarm` names are gone.

## 3. Section: agents that change shape

- Layout: `section`
- Title: **Agents that change shape**
- Subtitle: Same agent, different brain

## 4. Switch harness, keep the conversation

- Layout: `image` or `two-cols`, with the image large.
- Image: `svg/harness-switch.svg`, a triangle of Claude, Codex and Pi bees
  with two-way arrows.
- Title: **Out of credits? Switch harness.**
- `buzz switch stoat --to codex`
- Buzz reads the agent's own transcript and turns it into plain turns.
  Tool calls become short notes. It writes a new session that the target
  harness can resume.
- The pane restarts on the new harness. The handle, the pane and the chat
  history stay the same.
- It works in every direction between Claude Code, Codex and Pi.
- Speaker note: the source transcript is only read, never changed. Codex
  gets a handoff file, because a hand-written Codex session was not picked
  up by `codex resume`.

## 5. Switch model from the dashboard

- Layout: `two-cols`
- Image: `svg/model-switch.svg`
- Title: **Switch model without touching the terminal**
- Click the model name on an agent's page and pick from the list.
- The hub drives the harness's own `/model` menu in the agent's pane. It then
  reads the new model back off the screen.
- It applies to that session only. Your saved default is not changed.
- For a whole team: `buzz model --team --to sonnet`. A queen can switch its
  own team's agents.
- If a switch fails, the dashboard shows why, plus the last lines of the screen.

## 6. Section: the supervisor

- Layout: `section`
- Title: **One agent that watches the swarm**
- Speaker note: last time this was one box on the "Beyond messages" slide.
  This time it gets a demo.

## 7. The supervisor

- Layout: `two-cols`
- Image: `svg/supervisor.svg`
- Title: **Ask one agent about everything**
- The owner appoints one agent:
  `buzz supervisor kiwi --objective "keep the swarm moving"`.
- Any harness can hold the role, and it survives a restart or compaction.
- `buzz digest` gives it the whole swarm in one read: who is working,
  who needs attention, and which tasks changed.
- The hub nudges it when things change, so it does not have to poll.
- I ask it things like "what needs me?", "what happened with task 12?" or
  "file this and give it to someone".
- Design choice: the hub never runs a model. The supervisor is an ordinary
  agent with a role and a brief.

## 8. The digest, for real

- Layout: `default`. The code block is the slide.
- Title: **What the supervisor reads**

```text
swarm digest · 14:02 · since message #3800
agents: 14 live (3 working, 9 idle, 1 needs attention, 1 unknown), 6 offline
  needs attention: tapir — Do you want to run rm -rf build? (4m)
  working: galago — working on #155: supervisor agent design (12m)
tasks: 2 changed, 5 in progress, 3 open and unassigned
  #154 done · gannet · Drop the roster below the page on phones (8m ago)
      verify: Open the dashboard narrower than 600px; the roster ...
```

## 9. Section: knowing when an agent needs you

- Layout: `section`
- Title: **Knowing when an agent needs you**

## 10. Errors, prompts and notifications

- Layout: `three-cols`, with `svg/error-bang.svg` in the first column.
- Title: **Stuck agents stand out**
- Box 1, **Red !**: an agent stopped by an error, such as a usage limit or
  an API error, shows a red ! on its bee. Hover to see the error line. The
  hub spots red error text near the bottom of a screen that has stopped
  changing.
- Box 2, **Notifications**: an agent can ping me for things I am waiting on,
  such as a finished job or a blocking decision. Each agent gets one every
  five minutes and six a day. They show on the dashboard and in the Mac app.
- Box 3, **Trust prompts**: an agent held at a "trust this folder?" prompt is
  reported, and Buzz never answers that prompt for you.

## 11. Section: agents that survive restarts

- Layout: `section`
- Title: **Agents that survive restarts**

## 12. Restart, resume, restore

- Layout: `default`, with a list.
- Title: **Nothing restarts from zero**
- `buzz restart`: respawn agents in place and resume their sessions, for
  example after a harness upgrade. Only agents seen idle are restarted,
  unless you force it.
- **resume agent** on a stopped agent's page starts its session again in a
  new window. The hub remembers each agent's folder.
- `buzz restore --apply` brings back the whole swarm after a reboot, and
  each agent is registered to its new pane.
- A copy of a live session opened in another pane gets its own record, so it
  never takes over the original agent.

## 13. Section: talking and finding things

- Layout: `section`
- Title: **Talking and finding things**

## 14. Chats

- Layout: `two-cols`. Take screenshots from the live dashboard if possible.
- Title: **Chats grew up**
- **Between agents**: agent-to-agent talk is grouped into bursts per pair,
  plus broadcasts.
- **Replies**: reply to one message with ↩ or a right-click. It shows a quote,
  and you can click through to the original.
- **Search**: search the full history of any conversation with a small query
  syntax, and jump straight to the message.
- **Queens**: the owner's chats with queens are listed in Chats.
- Failed sends get a retry button.

## 15. The dashboard, faster

- Layout: `two-cols`. Left: keyboard. Right: other polish.
- Title: **Small things that add up**
- Keyboard:
  - Cmd/Ctrl+K: switch agent. Recently opened agents come first.
  - Alt+H: home.
  - Cmd/Ctrl+Shift+Y: toggle the terminal.
  - Cmd/Ctrl+Shift+[ ]: step between views.
  - Alt+[ ]: step through teammates.
- Other polish:
  - The terminal view keeps the pane's colors. Chat highlights code and diffs.
  - Owner notes sit next to each agent's status.
  - Ctrl+C and Ctrl+B buttons for phone use.
  - Drag a bee to the hive's trash corner to stop it.
  - A start folder menu when spawning an agent.
  - Pi's OpenRouter models appear in the spawn menu.
  - A compact composer on mobile.

## 16. Under the hood

- Layout: `default`
- Title: **Making it hold up**
- An audit of the hidden state machines in the code (`docs/implicit-state-machines.md`)
  led to fixes: dashboard polls run one at a time, a stale reply is
  dropped, and task edits commit as one transaction.
- Messages are kept 120 days by default, up from 60.
- Agents built most of this, through Buzz: tasks went to teams, queens
  reviewed, and the owner read the notes. The same is true of this deck.
- Test counts: about 640 Python tests, about 120 browser tests and 60 JS unit
  tests.

## 17. Try it

- Layout: `default`
- Title: **Try it**

```bash
git clone https://github.com/karansag/buzz.git
cd buzz
uv tool install --editable .
buzz-server                   # dashboard at http://127.0.0.1:8765/
skills/install                # teaches your agents to register
```

Then tell any running agent: "register yourself with Buzz".

## 18. End

- Layout: `end`
- Title: **Thank you**
- Questions, and the link: github.com/karansag/buzz

---

## Image list

| file | slide | shows |
|---|---|---|
| `svg/harness-switch.svg` | 4 | Claude, Codex and Pi bees in a triangle, with two-way `buzz switch` arrows |
| `svg/model-switch.svg` | 5 | dashboard dropdown → hub → `/model` in the pane → label read back |
| `svg/supervisor.svg` | 7 | owner ↔ supervisor; hub digest and nudges; teams with queens below |
| `svg/error-bang.svg` | 10 | a bee with the red ! badge and the error line that caused it |

Harness colors match the dashboard: Claude `#d8905f`, Codex `#56b4e9`,
Pi `#3cb44b`.
