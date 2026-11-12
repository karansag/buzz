"""Search query syntax for message search (experimental, task #433).

Supported, in the style of common web search:

    deploy fix          both words, anywhere, any case (AND)
    "exact phrase"      the words together, in this order
    -flaky  -"a b"      leave out messages containing this word or phrase
    gpu OR tpu          either one; OR binds tighter than the AND between
                        terms, so `fix gpu OR tpu` means fix AND (gpu OR tpu)
    from:skink          sent by skink; from:me and from:owner mean the owner
    after:2026-11-01    sent on or after this local date
    before:2026-11-10   sent before this local date

Anything that is not valid syntax is searched as plain text, so a query never
fails to parse: an unclosed quote runs to the end, a bad date is a word.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

OWNER_ALIASES = {"me", "owner", "you"}


@dataclass(frozen=True)
class Term:
    text: str
    phrase: bool = False


@dataclass
class Query:
    # Each clause is an OR-group of terms; all clauses must match.
    clauses: list[list[Term]] = field(default_factory=list)
    excluded: list[Term] = field(default_factory=list)
    senders: list[str] = field(default_factory=list)
    after: float | None = None
    before: float | None = None

    def empty(self) -> bool:
        return not (self.clauses or self.excluded or self.senders
                    or self.after is not None or self.before is not None)

    def highlight(self) -> list[str]:
        """The texts a UI should mark in a matching message."""
        return [t.text for clause in self.clauses for t in clause]


_TOKEN = re.compile(r'(-?)(?:(\w+):)?(?:"([^"]*)"?|(\S+))')


def _date(value: str) -> float | None:
    try:
        return time.mktime(time.strptime(value, "%Y-%m-%d"))
    except ValueError:
        return None


def parse(text: str) -> Query:
    q = Query()
    pending_or = False
    for m in _TOKEN.finditer(text):
        neg, key, quoted, bare = m.group(1), m.group(2), m.group(3), m.group(4)
        phrase = quoted is not None
        value = quoted if phrase else bare
        if not neg and not key and not phrase and value == "OR":
            pending_or = bool(q.clauses)
            continue
        if key and not neg:
            k = key.lower()
            if k == "from" and value:
                q.senders.append("owner" if value.casefold() in OWNER_ALIASES else value)
                continue
            if k in ("after", "before") and (ts := _date(value or "")) is not None:
                if k == "after":
                    q.after = ts
                else:
                    q.before = ts
                continue
        if key:
            # Not an operator: search the whole token, key included.
            value = f"{key}:{value}" if not phrase else f'{key}:"{value}"'
            phrase = False
        value = (value or "").strip()
        if not value:
            pending_or = False
            continue
        term = Term(value.casefold(), phrase)
        if neg:
            q.excluded.append(term)
            pending_or = False
        elif pending_or:
            q.clauses[-1].append(term)
            pending_or = False
        elif [term] not in q.clauses:
            q.clauses.append([term])
    return q


TEXT = "casefold(content || ' ' || COALESCE(context, ''))"


def to_sql(q: Query, text: str = TEXT, sender: str = "sender",
           ts: str = "ts") -> tuple[str, list]:
    """A WHERE fragment (without the word WHERE) and its parameters.

    Matching is literal, case-insensitive substring matching over the message
    text and its context tag. The connection supplies Unicode casefold().
    An empty query matches nothing.
    """
    if q.empty():
        return "0", []
    parts: list[str] = []
    params: list = []
    for clause in q.clauses:
        parts.append("(" + " OR ".join(f"instr({text}, ?) > 0" for _ in clause) + ")")
        params += [t.text for t in clause]
    for t in q.excluded:
        parts.append(f"instr({text}, ?) = 0")
        params.append(t.text)
    if q.senders:
        parts.append(f"{sender} IN ({','.join('?' for _ in q.senders)})")
        params += q.senders
    if q.after is not None:
        parts.append(f"{ts} >= ?")
        params.append(q.after)
    if q.before is not None:
        parts.append(f"{ts} < ?")
        params.append(q.before)
    return " AND ".join(parts), params


def matches(q: Query, message: dict) -> bool:
    """The same rules in Python, for messages already in memory."""
    if q.empty():
        return False
    text = f"{message.get('content') or ''} {message.get('context') or ''}".casefold()
    if any(not any(t.text in text for t in clause) for clause in q.clauses):
        return False
    if any(t.text in text for t in q.excluded):
        return False
    if q.senders and message.get("sender") not in q.senders:
        return False
    ts = message.get("ts") or 0
    if q.after is not None and ts < q.after:
        return False
    if q.before is not None and ts >= q.before:
        return False
    return True
