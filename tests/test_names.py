"""Tests for the handle pool."""

import random
import sqlite3

from agent_swarm import names


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE recipients (user_id TEXT PRIMARY KEY)")
    conn.execute("CREATE TABLE messages (sender TEXT, recipient TEXT)")
    conn.execute("CREATE TABLE tasks (assignee TEXT)")
    conn.execute("CREATE TABLE summaries (user_id TEXT)")
    conn.execute("CREATE TABLE retired_agents (archive_id TEXT PRIMARY KEY)")
    conn.execute("CREATE TABLE board_posts (author TEXT)")
    conn.execute("CREATE TABLE board_reads (user_id TEXT)")
    return conn


def _take(conn, user_id):
    conn.execute("INSERT INTO recipients (user_id) VALUES (?)", (user_id,))


def test_pick_unused_returns_a_bare_pool_name():
    assert names.pick_unused(_conn()) in names.POOL


def test_pick_unused_avoids_names_already_taken():
    conn = _conn()
    for animal in names.POOL[:-1]:
        _take(conn, animal)
    assert names.pick_unused(conn) == names.POOL[-1]


def test_legacy_suffixed_handle_reserves_its_bare_name():
    # Handles issued by earlier versions carried model and host suffixes.
    # While one exists, its animal is off the table so "otter" and
    # "otter-opus" never coexist.
    conn = _conn()
    for animal in names.POOL[:-2]:
        _take(conn, animal)
    penultimate, last = names.POOL[-2], names.POOL[-1]
    _take(conn, f"{penultimate}-codex-gpt5-workstation")
    assert names.pick_unused(conn) == last


def test_every_generated_handle_can_be_requested_back():
    # An agent that loses its pane reclaims its handle with `register --name`,
    # which runs it through normalize_requested, so nothing generated may be
    # an illegal request. Legacy suffixed handles were up to 35 characters.
    conn = _conn()
    generated = names.pick_unused(conn, rng=random.Random(0))
    assert names.normalize_requested(generated) == generated
    assert names.normalize_requested("salamander-claude-fable-workstation")


def test_pick_unused_falls_back_to_numeric_suffix_when_pool_exhausted():
    conn = _conn()
    for animal in names.POOL:
        _take(conn, animal)
    name = names.pick_unused(conn, rng=random.Random(1))
    base, _, suffix = name.rpartition("-")
    assert base in names.POOL
    assert suffix == "2"
    _take(conn, name)
    again = names.pick_unused(conn, rng=random.Random(1))
    assert again == f"{base}-3"


def test_a_handle_left_in_history_is_not_reissued():
    # Unregistering leaves history on the original handle. Automatic naming
    # must skip it until the history has been moved to an archive.
    for leftover in (
        "INSERT INTO messages VALUES ('{0}', 'owner')",
        "INSERT INTO messages VALUES ('owner', '{0}')",
        "INSERT INTO tasks VALUES ('{0}')",
        "INSERT INTO summaries VALUES ('{0}')",
    ):
        conn = _conn()
        for animal in names.POOL[:-2]:
            _take(conn, animal)
        gone, last = names.POOL[-2], names.POOL[-1]
        conn.execute(leftover.format(gone))
        assert names.pick_unused(conn) == last
        assert gone in names.used(conn)
