"""Conversation history helpers for multi-turn Ask."""

from __future__ import annotations

from typing import Any

DEFAULT_ASK_CONVERSATION_TURNS = 5
MAX_ASK_CONVERSATION_TURNS = 20


def normalize_turns(history: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    """Keep user/assistant turns with non-empty content."""
    if not history:
        return []
    out: list[dict[str, str]] = []
    for turn in history:
        role = (turn.get("role") or "").strip().lower()
        content = (turn.get("content") or "").strip()
        if role not in ("user", "assistant") or not content:
            continue
        out.append({"role": role, "content": content})
    return out


def truncate_history(
    history: list[dict[str, Any]] | None,
    max_turns: int | None = None,
) -> list[dict[str, Any]]:
    """Limit to the most recent N Q&A exchanges (2 messages per turn)."""
    from settings_service import get_ask_conversation_turns

    if not history:
        return []
    limit = max_turns if max_turns is not None else get_ask_conversation_turns()
    if limit <= 0:
        return []
    trimmed = history[-(limit * 2) :]
    out: list[dict[str, Any]] = []
    for turn in trimmed:
        role = (turn.get("role") or "").strip().lower()
        content = (turn.get("content") or "").strip()
        if role not in ("user", "assistant") or not content:
            continue
        entry: dict[str, Any] = {"role": role, "content": content}
        for key in ("question", "sql", "columns", "rows"):
            if turn.get(key) is not None:
                entry[key] = turn[key]
        out.append(entry)
    return out


def format_conversation_block(history: list[dict[str, str]] | None) -> str:
    if not history:
        return ""
    lines: list[str] = []
    for turn in history:
        label = "User" if turn["role"] == "user" else "Assistant"
        lines.append(f"{label}: {turn['content']}")
    return "Prior conversation (for follow-up context):\n" + "\n\n".join(lines) + "\n\n"


def format_prior_result_block(prior: Any) -> str:
    """Summarize the last structured query for SQL / transform follow-ups."""
    if prior is None:
        return ""
    preview = prior.rows[:8]
    return (
        "Prior query result (keep same scope/grain unless the user clearly changes it):\n"
        f"- Question: {prior.question or '(unknown)'}\n"
        f"- SQL: {prior.sql or '(none)'}\n"
        f"- Columns: {prior.columns}\n"
        f"- Row count: {len(prior.rows)}\n"
        f"- Sample rows: {preview}\n\n"
    )


def contextual_question_with_history(
    question: str,
    history: list[dict[str, str]] | None,
) -> str:
    """Expand a short follow-up into a retrieval / routing query."""
    return retrieval_query_with_history(question, history)


def retrieval_query_with_history(
    question: str,
    history: list[dict[str, str]] | None,
) -> str:
    """Expand retrieval query with recent turns so follow-ups stay on topic."""
    if not history:
        return question
    parts: list[str] = []
    for turn in history[-4:]:
        parts.append(turn["content"])
    parts.append(question)
    return "\n".join(parts)
