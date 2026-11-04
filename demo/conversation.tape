# VHS tape for the README's tmux demo. Renders demo/conversation.gif.
#
# Two real agents, Claude Code on top and Codex below, in one tmux
# window. Both register with a throwaway hub, then Claude asks Codex a
# question over the bus and Codex answers. The setup is hidden; the
# recording opens as Claude is asked to send.
#
# Run from the repo root:   vhs demo/conversation.tape
#
# It never touches your real hub: the demo hub listens on 8799 with a
# database in a temp dir, and the panes get AGENT_SWARM_URL and an empty
# AGENT_SWARM_CONFIG so their CLI cannot reach ~/.agent-swarm. Needs
# claude and codex logged in, the agent-swarm-register skills installed,
# and nothing else on port 8799 or in a tmux session named swarm-demo.
# Both agents run without permission prompts (--dangerously-skip-permissions,
# --yolo), so only run it on a machine you trust.

Output demo/conversation.gif

Set Shell "bash"
Set FontFamily "DejaVu Sans Mono"
Set FontSize 15
Set Width 1280
Set Height 820
Set Padding 16
Set TypingSpeed 15ms
Set PlaybackSpeed 1.5

Hide

Type `export D=$(mktemp -d) && export SWARM_ENV="-e AGENT_SWARM_URL=http://127.0.0.1:8799 -e AGENT_SWARM_CONFIG=$D/none.toml"`
Enter
Type `AGENT_SWARM_PORT=8799 AGENT_SWARM_DB=$D/db.sqlite setsid -f buzz-server > $D/server.log 2>&1`
Enter
Sleep 2s
Type `tmux new-session -d -s swarm-demo -c ~/agent-swarm $SWARM_ENV && tmux split-window -v -t swarm-demo -c ~/agent-swarm $SWARM_ENV && tmux select-pane -t swarm-demo.0 && tmux attach -t swarm-demo`
Enter
Sleep 1s

# Top pane: Claude Code.
Type "claude --dangerously-skip-permissions"
Enter
Sleep 6s
Type "Register yourself with agent-swarm. Reply with just your handle."
Enter
Sleep 40s

# Bottom pane: Codex.
Ctrl+B
Down
Type "codex -c check_for_update_on_startup=false --yolo"
Enter
Sleep 6s
Type "Register yourself with agent-swarm and reply with just your handle. If another agent then messages you, answer it in one sentence with buzz send and stop."
Enter
Sleep 40s
Ctrl+B
Up
Sleep 1s

Show

Type "Over agent-swarm, ask the other agent how many test functions tests/test_server.py has. When it answers, tell me in one line."
Enter
# Long enough for the question, Codex's answer, and Claude's summary.
Sleep 50s

Hide
Type "/exit"
Enter
Sleep 2s
Ctrl+B
Down
Ctrl+C
Ctrl+C
Sleep 1s
Type "tmux kill-session -t swarm-demo"
Enter
Sleep 1s
Type `fuser -k 8799/tcp; rm -rf $D`
Enter
Sleep 1s
