"""Conversation history helpers for multi-turn Ask."""

from __future__ import annotations

import re
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


ATTACHED_DOCS_MARKER = "[Attached documents]"


def has_attached_documents(question: str) -> bool:
    return ATTACHED_DOCS_MARKER in (question or "")


def split_attached_documents(question: str) -> tuple[str, str | None]:
    """Return (user question, attachment block) when Ask composer inlined uploads."""
    if not has_attached_documents(question):
        return (question or "").strip(), None
    before, _, rest = question.partition(ATTACHED_DOCS_MARKER)
    attachment = rest.strip() or None
    return before.strip(), attachment


ATTACHMENT_MAX_CHARS = 12_000

_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "how",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "was",
        "what",
        "when",
        "where",
        "which",
        "who",
        "with",
        "you",
        "your",
    }
)


def _question_tokens(question: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9]+", (question or "").lower())
    return {t for t in tokens if len(t) > 2 and t not in _STOPWORDS}


def _parse_attachment_sections(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    name = "attachment"
    lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("--- ") and line.endswith(" ---"):
            if lines:
                sections.append((name, "\n".join(lines)))
            name = line[4:-4].strip() or "attachment"
            lines = []
        else:
            lines.append(line)
    if lines or not sections:
        sections.append((name, "\n".join(lines)))
    return sections


def _excerpt_section(name: str, content: str, tokens: set[str], budget: int) -> str:
    if budget <= 0 or not content.strip():
        return ""
    lines = content.splitlines()
    if not lines:
        return ""
    is_csv = name.lower().endswith(".csv")
    keep: set[int] = {0} if is_csv else set()
    scored: list[tuple[int, int]] = []
    for i, line in enumerate(lines):
        if is_csv and i == 0:
            continue
        if not line.strip():
            continue
        score = sum(1 for token in tokens if token in line.lower())
        scored.append((score, i))
    scored.sort(key=lambda item: (-item[0], item[1]))
    for score, index in scored:
        if index in keep:
            continue
        if score > 0 or len(keep) < min(80, len(lines)):
            keep.add(index)
        if len(keep) >= 200:
            break
    selected = "\n".join(lines[i] for i in sorted(keep))
    if len(selected) <= budget:
        return selected
    trimmed = selected[:budget]
    if "\n" in trimmed:
        trimmed = trimmed.rsplit("\n", 1)[0]
    return trimmed


def select_relevant_attachment_content(
    question: str,
    attachment_text: str,
    *,
    max_chars: int = ATTACHMENT_MAX_CHARS,
) -> str:
    """Trim large uploads to question-relevant lines while keeping CSV headers."""
    attachment_text = (attachment_text or "").strip()
    if not attachment_text or len(attachment_text) <= max_chars:
        return attachment_text

    tokens = _question_tokens(question)
    sections = _parse_attachment_sections(attachment_text)
    if len(sections) == 1:
        name, content = sections[0]
        excerpt = _excerpt_section(name, content, tokens, max_chars)
        if name != "attachment":
            return f"--- {name} ---\n{excerpt}".strip()
        return excerpt

    per_section = max(max_chars // max(len(sections), 1), 500)
    parts: list[str] = []
    for name, content in sections:
        header = f"--- {name} ---"
        excerpt = _excerpt_section(name, content, tokens, per_section - len(header) - 1)
        if excerpt:
            parts.append(f"{header}\n{excerpt}")
    combined = "\n\n".join(parts)
    if len(combined) <= max_chars:
        return combined
    trimmed = combined[:max_chars]
    if "\n" in trimmed:
        trimmed = trimmed.rsplit("\n", 1)[0]
    return trimmed
