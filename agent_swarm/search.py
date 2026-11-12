"""The query compiler for conversation search (syntax: see search_query)."""

from . import search_query


def matches(query: str) -> tuple[str, list]:
    """SQL clause and params over bare messages columns.

    Columns refer to messages. The connection supplies Unicode casefold().
    Keep owner/conversation scope outside this function.
    """
    return search_query.to_sql(search_query.parse(query))


def terms(query: str) -> list[str]:
    """The texts a matching message should have highlighted."""
    return search_query.parse(query).highlight()
