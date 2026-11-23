"""Name pool for server-assigned handles, and validation of requested ones."""

from __future__ import annotations

import random
import re
import sqlite3

POOL = [
    "otter",
    "ferret",
    "badger",
    "panda",
    "tapir",
    "axolotl",
    "puffin",
    "quokka",
    "narwhal",
    "capybara",
    "mongoose",
    "lemur",
    "stoat",
    "marten",
    "ocelot",
    "wombat",
    "pangolin",
    "salamander",
    "kestrel",
    "magpie",
    "hedgehog",
    "raccoon",
    "fennec",
    "dormouse",
    "shrew",
    "manatee",
    "ibis",
    "heron",
    "viper",
    "newt",
    "civet",
    "gecko",
    "meerkat",
    "armadillo",
    "chinchilla",
    "jerboa",
    "vole",
    "weasel",
    "polecat",
    "genet",
    "coati",
    "tarsier",
    "loris",
    "bushbaby",
    "wallaby",
    "bandicoot",
    "echidna",
    "platypus",
    "aardvark",
    "hyrax",
    "dugong",
    "serval",
    "caracal",
    "margay",
    "jackal",
    "coyote",
    "vicuna",
    "alpaca",
    "okapi",
    "gerenuk",
    "dik-dik",
    "duiker",
    "peccary",
    "tenrec",
    "solenodon",
    "colugo",
    "pika",
    "degu",
    "agouti",
    "paca",
    "vizcacha",
    "kinkajou",
    "olingo",
    "cacomistle",
    "ringtail",
    "grison",
    "tayra",
    "linsang",
    "binturong",
    "fossa",
    "quoll",
    "numbat",
    "bilby",
    "potoroo",
    "sifaka",
    "indri",
    "galago",
    "toucan",
    "hornbill",
    "kookaburra",
    "shoveler",
    "avocet",
    "curlew",
    "sandpiper",
    "plover",
    "grebe",
    "cormorant",
    "gannet",
    "skua",
    "tern",
    "shrike",
    "chukar",
    "ptarmigan",
    "quetzal",
    "trogon",
    "hoopoe",
    "bittern",
    "gadwall",
    "smew",
    "goldeneye",
    "merganser",
    "chameleon",
    "iguana",
    "skink",
    "anole",
    "tuatara",
    "caecilian",
]


def pick(taken: set[str], rng: random.Random | None = None) -> str:
    """Return a pool name that none of `taken` uses.

    Handles are bare pool names; what an agent is and where it runs are
    columns on its row, not parts of its name. A handle issued by an earlier
    version, such as "otter-opus" or "otter-codex-gpt5-karanslinux", reserves
    bare "otter" for as long as it exists so the two never coexist. When every
    pool name is taken, a numeric suffix is appended.
    """
    r = rng or random.Random()

    def free(name: str) -> bool:
        return name not in taken and not any(t.startswith(f"{name}-") for t in taken)

    candidates = [n for n in POOL if free(n)]
    if candidates:
        return r.choice(candidates)
    base = r.choice(POOL)
    n = 2
    while f"{base}-{n}" in taken:
        n += 1
    return f"{base}-{n}"


# Handles are bare strings in these tables, not keys into recipients, so a
# retired agent's messages, tasks and status lines still carry its handle.
_HISTORY = (
    "SELECT user_id FROM recipients"
    " UNION SELECT sender FROM messages"
    " UNION SELECT recipient FROM messages"
    " UNION SELECT assignee FROM tasks WHERE assignee IS NOT NULL"
    " UNION SELECT user_id FROM summaries"
    " UNION SELECT archive_id FROM retired_agents"
)


def used(conn: sqlite3.Connection) -> set[str]:
    """Every handle this hub has used: registered agents, and retired ones
    that left messages, tasks or status lines behind."""
    return {row[0] for row in conn.execute(_HISTORY)}


def pick_unused(conn: sqlite3.Connection, rng: random.Random | None = None) -> str:
    """A pool name no agent, past or present, has used.

    A new agent given a retired agent's name would show that agent's
    history as its own (task #288), so we check history as well as active registrations.
    """
    return pick(used(conn), rng)


# Handles the server refuses to hand out: 'owner' is the human operator,
# 'hub' is the server itself (it signs the supervisor's digest nudges).
RESERVED = frozenset({"owner", "hub"})

# 48 rather than 32 because handles issued by earlier versions carried harness,
# model, and host suffixes of up to 35 characters, and an agent that loses its
# pane must still be able to re-request the handle it had.
_VALID_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")


class InvalidName(ValueError):
    """A requested handle that the server will not assign."""


def normalize_requested(name: str) -> str:
    """Validate an agent-requested handle, returning its canonical form.

    Handles are lowercase so routing is case-insensitive; they are used raw in
    tmux pane titles and message headers, so the character set stays tight.
    """
    candidate = name.strip().lower()
    if not _VALID_NAME.match(candidate):
        raise InvalidName(
            "name must be 1-48 characters of lowercase letters, digits or "
            "hyphens, and start with a letter or digit"
        )
    if candidate in RESERVED:
        raise InvalidName(f"'{candidate}' is a reserved handle")
    return candidate
