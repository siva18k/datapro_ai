"""Normalize LLM-generated SQL into a single read-only statement."""

from __future__ import annotations

import re


def find_statement_terminator(sql: str) -> int | None:
    """
    Return the index of the first semicolon that terminates a SQL statement,
    ignoring semicolons inside string literals or comments.
    """
    i = 0
    n = len(sql)
    in_single = False
    in_double = False
    in_line_comment = False
    in_block_comment = False

    while i < n:
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue

        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue

        if in_single:
            if ch == "'":
                if nxt == "'":
                    i += 2
                    continue
                in_single = False
            i += 1
            continue

        if in_double:
            if ch == '"':
                if nxt == '"':
                    i += 2
                    continue
                in_double = False
            i += 1
            continue

        if ch == "-" and nxt == "-":
            in_line_comment = True
            i += 2
            continue
        if ch == "/" and nxt == "*":
            in_block_comment = True
            i += 2
            continue
        if ch == "'":
            in_single = True
            i += 1
            continue
        if ch == '"':
            in_double = True
            i += 1
            continue
        if ch == ";":
            return i
        i += 1
    return None


def has_multiple_sql_statements(sql: str) -> bool:
    text = sql.strip().rstrip(";").strip()
    if not text:
        return False
    return find_statement_terminator(text) is not None


def take_first_sql_statement(sql: str) -> str:
    text = sql.strip()
    match = re.search(r"\b(with|select)\b", text, re.I)
    if match:
        text = text[match.start() :]
    end = find_statement_terminator(text)
    if end is not None:
        text = text[:end]
    return text.strip().rstrip(";")


def normalize_llm_sql(text: str) -> str:
    """Strip markdown, leading prose, and extra batched statements from LLM output."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return take_first_sql_statement(text)
