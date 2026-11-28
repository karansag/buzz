"""Count the lines of code for the cloned scope, in Python and in Rust.

    python rust/compat/loc.py

Python: only the functions, classes and constants the cloned routes use,
listed below by name. Everything else in those files (teams, boards, remote
nodes, spawn, restart, search, ...) is left out. Imports are left out too.
Rust: every line of every file in rust/buzz-hub/src.

"Code" lines are lines that are not blank, not a comment, and (Python) not
part of a docstring. "All" lines include them.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# Module-level names per file; "Class.method" picks single methods, and
# "create_app.name" picks a route or helper defined inside create_app.
PYTHON = {
    "server.py": [
        "_plain_json", "_read_json", "UNKNOWN_ACTIVITY", "OWNER", "NOTE_GUIDANCE", "STATUS_GUIDANCE", "Principal",
        "LOOPBACK_HOSTS", "TAILSCALE_LOGIN_HEADER", "FORWARDED_HEADERS", "owner_logins", "RegisterReq", "StatusReq",
        "SendReq", "ActorFields", "TaskCreateReq", "TaskUpdateReq", "_protocol_brief", "_run",
        *(f"create_app.{name}" for name in (
            "_authenticate", "_require_owner", "_resolve_caller", "_caller", "_claimed_node", "_own_row_or_403", "_actor",
            "health", "register", "_node_or_422", "_node_of", "_try_snapshot", "_pane_ref", "_offline", "_stale",
            "_annotated_recipients", "_is_alive", "_live_elsewhere", "_reach", "recipients", "whoami", "_reply_original",
            "_queen_target", "_find_team", "_deliver_as", "_missing_recipient", "_dispatch", "_blocking_prompt_error",
            "send", "set_status", "messages", "_notify_assignment", "_notify_team_assignment",
            "_require_registered_assignee", "_require_known_team", "tasks_list", "tasks_create", "tasks_update",
            "_recipients_with_activity", "portal", "state", "_capture_peek", "peek",
        )),
    ],
    "db.py": [
        "SUMMARY_HISTORY", "TASK_STATUSES", "_UNSET", "_write_lock", "_write_depth", "_writes", "_open", "_ThreadConnection",
        "Connections", "connect", "register", "fill_missing_node", "name_taken_by_other", "rename_recipient",
        "_ensure_columns", "lookup_user_by_pane", "lookup_user_by_restored_label", "UNBOUND", "lookup_user_by_agent_id",
        "adopt_agent_id", "get_recipient", "list_recipients", "retired_agents", "is_retired", "was_retired",
        "SUPERVISOR_KEY", "_supervisor_row", "get_supervisor", "record_summary", "summaries_by_user", "create_task",
        "get_task", "list_tasks", "_validate_task_deps", "TaskNoteRequired", "update_task", "get_team", "list_teams",
        "MESSAGE_STATUSES", "record_message", "get_message", "list_pins", "owner_reply_reminder_due",
        "abandon_pending_messages", "fill_missing_worktree_node", "set_message_status", "fetch_messages", "_messages",
        "_message", "hash_token", "node_for_token", "list_nodes", "clear_reservation",
    ],
    "tmux.py": [
        "DEFAULT_FLAVOR", "DEFAULT_SUBMIT_KEY", "FLAVOR_SUBMIT_KEYS", "FLAVOR_COMPACT_COMMANDS", "FLAVOR_SUBMIT_DELAYS",
        "SUBMIT_VERIFY_DELAY", "_has_label_token", "infer_flavor", "local_node", "submit_key_for_flavor",
        "compact_command_for_flavor", "submit_delay_for_flavor", "tag_pane", "_composer_holds_text", "SUBMIT_POLL_INTERVAL",
        "_await_submit", "Uncertain", "_error_text", "deliver", "_tmux_out", "server_id", "resolve_pane", "pane_table",
        "SHELL_COMMANDS", "offline_reason", "capture_pane", "format_message",
    ],
    "nodes.py": [
        "Result", "Resolved", "Unavailable", "new_op_id", "PaneSnapshot", "_stale_server", "LocalNode.__init__",
        "LocalNode.snapshot", "LocalNode.server_id", "LocalNode.resolve", "LocalNode.capture", "LocalNode.screen",
        "LocalNode.deliver", "LocalNode.tag_pane", "LocalNode.spawn_dirs", "NodeRegistry",
    ],
    "names.py": ["pick", "_HISTORY", "used", "pick_unused", "RESERVED", "_VALID_NAME", "InvalidName", "normalize_requested"],
    "activity.py": ["TRUST_PROMPTS", "trust_prompt", "DOWNGRADE_PROMPTS", "downgrade_prompt"],
    "boards.py": ["INITIAL_POSTS", "_newest", "_cursors", "_unread", "unread_count", "clamp_cursors"],
    "message_index.py": ["TABLE", "VOCAB", "BATCH", "_text", "ensure", "_have", "add"],
    "config.py": ["spawn_dirs", "hostname", "_node_name", "load"],
}
# Data both sides hold as a plain list or text: counted apart from logic.
DATA = {"db.py": ["SCHEMA"], "names.py": ["POOL"]}
RUST_DATA = ["schema.sql", "pool.txt", "brief.txt"]


def named(node: ast.AST) -> str | None:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return node.name
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
        return node.targets[0].id
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return node.target.id
    return None


def spans(tree: ast.Module, wanted: list[str]) -> tuple[list[tuple[int, int]], set[str]]:
    """(first line, last line) of each wanted definition, decorators included."""
    found, seen = [], set()

    def take(node: ast.AST, label: str) -> None:
        first = min([node.lineno, *(d.lineno for d in getattr(node, "decorator_list", []))])
        found.append((first, node.end_lineno))
        seen.add(label)

    for node in tree.body:
        name = named(node)
        if name in wanted:
            take(node, name)
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
            for child in node.body:
                label = f"{name}.{named(child)}"
                if label in wanted:
                    take(child, label)
    return found, seen


def docstring_lines(tree: ast.Module) -> set[int]:
    lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                lines.update(range(first.lineno, first.end_lineno + 1))
    return lines


def python_counts(selection: dict[str, list[str]]) -> dict[str, tuple[int, int]]:
    out = {}
    for file, wanted in selection.items():
        source = (REPO / "agent_swarm" / file).read_text()
        tree = ast.parse(source)
        found, seen = spans(tree, wanted)
        missing = set(wanted) - seen
        assert not missing, f"{file}: not found: {sorted(missing)}"
        docs, text = docstring_lines(tree), source.splitlines()
        picked = sorted({n for first, last in found for n in range(first, last + 1)})
        code = [n for n in picked if text[n - 1].strip() and not text[n - 1].strip().startswith("#") and n not in docs]
        out[file] = (len(picked), len(code))
    return out


def rust_counts() -> dict[str, tuple[int, int]]:
    out = {}
    for path in sorted((REPO / "rust/buzz-hub/src").iterdir()):
        text = path.read_text().splitlines()
        code = [line for line in text if line.strip() and not line.strip().startswith("//")]
        out[path.name] = (len(text), len(code))
    return out


def show(title: str, counts: dict[str, tuple[int, int]]) -> tuple[int, int]:
    print(f"\n{title}\n| File | All lines | Code lines |\n|---|---:|---:|")
    for name, (every, code) in counts.items():
        print(f"| {name} | {every} | {code} |")
    total = tuple(sum(c[i] for c in counts.values()) for i in (0, 1))
    print(f"| **total** | {total[0]} | {total[1]} |")
    return total


def main() -> None:
    py = show("Python: logic for the cloned scope", python_counts(PYTHON))
    py_data = show("Python: data (schema text, name pool)", python_counts(DATA))
    rust = rust_counts()
    rs = show("Rust: logic", {k: v for k, v in rust.items() if k not in RUST_DATA})
    rs_data = show("Rust: data (schema text, name pool, brief template)", {k: v for k, v in rust.items() if k in RUST_DATA})
    whole = sum(len(p.read_text().splitlines()) for p in (REPO / "agent_swarm").glob("*.py"))
    print(f"\nPython logic: {py[1]} code lines. Rust logic: {rs[1]} code lines. Ratio {rs[1] / py[1]:.2f}.")
    print(f"Data lines: Python {py_data[0]}, Rust {rs_data[0]}.")
    print(f"All of agent_swarm/*.py: {whole} lines, so the cloned scope is {py[0] / whole:.0%} of it by lines.")


if __name__ == "__main__":
    main()
