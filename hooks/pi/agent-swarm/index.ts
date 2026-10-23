// Registers this Pi session with agent-swarm when it starts in its own tmux
// pane, and puts the protocol brief in the session's context. The checks
// (own pane, hub up) live in `agent-swarm autoregister`; this only feeds it
// what Pi knows and never fails the session.
import { spawn } from "node:child_process";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const BIN = process.env.AGENT_SWARM_BIN ?? "agent-swarm";

function autoregister(input: object): Promise<string> {
  return new Promise((resolve) => {
    const child = spawn(BIN, ["autoregister", "--hook"], { stdio: ["pipe", "pipe", "ignore"] });
    let out = "";
    const timer = setTimeout(() => child.kill(), 15000);
    child.stdout.on("data", (chunk) => (out += chunk));
    child.on("error", () => resolve(""));
    child.on("close", () => {
      clearTimeout(timer);
      resolve(out);
    });
    child.stdin.end(JSON.stringify(input));
  });
}

export default function (pi: ExtensionAPI) {
  pi.on("session_start", async (event, ctx) => {
    // print, json and rpc runs have no pane of their own to receive messages.
    if (ctx.mode !== "tui" || event.reason === "reload") return;
    // The session id lets `agent-swarm restore` resume this session with
    // `pi --session ID`, and gives the hub the same identity when it does.
    const out = await autoregister({
      hook_event_name: "SessionStart",
      session_id: ctx.sessionManager.getSessionId(),
      model: ctx.model?.id,
    });
    let brief = "";
    try {
      brief = JSON.parse(out).hookSpecificOutput?.additionalContext ?? "";
    } catch {
      return;
    }
    if (!brief) return;
    pi.sendMessage(
      { customType: "agent-swarm", content: brief, display: true },
      { deliverAs: "nextTurn" },
    );
  });
}
