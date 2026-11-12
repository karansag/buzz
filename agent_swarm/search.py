"""The replaceable query compiler for conversation search."""


def matches(query: str) -> tuple[str, list[str]]:
    """Literal case-insensitive all-words matching; no wildcard/query syntax.

    Columns refer to messages. The connection supplies Unicode casefold().
    Keep owner/conversation scope outside this function.
    """
    words = list(dict.fromkeys(query.casefold().split()))
    if not words:
        return "0", []
    return " AND ".join("instr(casefold(content || ' ' || COALESCE(context, '')), ?) > 0" for _ in words), words
