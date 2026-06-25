"""Session lifecycle for multi-turn Ask / Analytics — topic detection and auto-reset."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal

from conversation_context import format_conversation_block


@dataclass
class ConversationSessionDecision:
    effective_history: list[dict[str, Any]]
    is_follow_up: bool
    is_new_topic: bool
    session_reset: bool
    session_summary: str | None
    prior_turn_count: int = 0


def count_user_turns(history: list[dict[str, Any]] | None) -> int:
    if not history:
        return 0
    return sum(1 for turn in history if (turn.get("role") or "").strip().lower() == "user")


def _breakdown_dimensions(text: str) -> set[str]:
    """Rough grouping dimensions mentioned in a question."""
    lower = (text or "").lower()
    dims: set[str] = set()
    markers = {
        "channel": ("channel", "channels"),
        "country": ("country", "countries"),
        "region": ("region", "regions"),
        "quarter": ("quarter", "quarterly", " q1", " q2", " q3", " q4"),
        "month": ("month", "monthly"),
        "year": ("year", "yearly", "annual"),
        "customer": ("customer", "customers"),
        "product": ("product", "products"),
        "category": ("category", "categories"),
        "department": ("department", "departments"),
    }
    for dim, tokens in markers.items():
        if any(token in lower for token in tokens):
            dims.add(dim)
    return dims


def _last_user_message(history: list[dict[str, Any]]) -> str:
    for turn in reversed(history):
        if (turn.get("role") or "").strip().lower() == "user":
            return (turn.get("content") or turn.get("question") or "").strip()
    return ""


def _heuristic_message_intent(
    question: str,
    history: list[dict[str, Any]],
) -> Literal["follow_up", "new_topic"] | None:
    """
    Fast path before the LLM router.

    Returns new_topic when the latest message clearly changes breakdown or scope.
    Returns follow_up for obvious refinements. None when uncertain.
    """
    last = _last_user_message(history)
    if not last:
        return None

    q = question.strip().lower()
    if not q or q == last.lower():
        return "follow_up"

    if re.match(
        r"^(also|and|same|filter|sort|order|convert|exclude|include|only|what about|how about|"
        r"add|drop|remove|keep|limit|show me that|same query)\b",
        q,
    ):
        return "follow_up"

    if len(q.split()) <= 8 and any(
        phrase in q for phrase in ("also", "as well", "same data", "same result", "that table")
    ):
        return "follow_up"

    cur_dims = _breakdown_dimensions(question)
    prev_dims = _breakdown_dimensions(last)
    if cur_dims and prev_dims and cur_dims != prev_dims:
        return "new_topic"

    # Standalone analytical question with no dependency language → fresh query.
    if not re.search(r"\b(that|those|same|previous|prior|above|earlier|it|them)\b", q):
        if cur_dims != prev_dims or (cur_dims and not prev_dims) or (prev_dims and not cur_dims):
            return "new_topic"

    return None


def _parse_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError("LLM did not return JSON")
    return json.loads(match.group(0))


def _history_for_prompt(history: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [{"role": t["role"], "content": t["content"]} for t in history if t.get("content")]


def classify_message_intent(
    question: str,
    history: list[dict[str, Any]],
    *,
    model: str,
    backend: str,
    base_url: str,
) -> Literal["follow_up", "new_topic"]:
    """LLM decides whether the latest message continues the session or starts a new topic."""
    from api.llm import generate_answer

    history_block = format_conversation_block(_history_for_prompt(history))
    prompt = f"""You route user messages in a data Q&A chat.

{history_block}Latest user message:
{question}

Decide whether this message:
- **follow_up** — continues the SAME analysis on the SAME result or breakdown (refinement, conversion, filter tweak, sort, add/remove column, clarification). Examples: "convert to USD", "sort by revenue", "also filter to SHIPPED", "same but for Q2".
- **new_topic** — a standalone question or a different breakdown, metric focus, time grain, or dataset. Examples: prior question was revenue by channel and latest asks quarterly revenue; prior was by country and latest asks by customer.

Changing grouping (channel → quarter, country → product, monthly → quarterly) is **new_topic**, not follow_up.
Short acknowledgements like "thanks" after a complete answer are follow_up only if they request more work on the same data.

Return ONLY JSON:
{{"intent": "follow_up" | "new_topic", "reason": "one short sentence"}}
"""
    raw = generate_answer(prompt, model=model, backend=backend, base_url=base_url)
    try:
        data = _parse_json_object(raw)
        intent = str(data.get("intent") or "follow_up").strip().lower()
        if intent == "new_topic":
            return "new_topic"
    except (ValueError, json.JSONDecodeError, KeyError):
        pass
    return "follow_up"


def summarize_conversation_session(
    history: list[dict[str, Any]],
    *,
    model: str,
    backend: str,
    base_url: str,
) -> str:
    """Summarize a completed multi-turn session before starting a new chat."""
    from api.llm import generate_answer

    history_block = format_conversation_block(_history_for_prompt(history))
    structured_bits: list[str] = []
    for turn in history:
        if (turn.get("role") or "").lower() != "assistant":
            continue
        if turn.get("columns") and turn.get("rows") is not None:
            structured_bits.append(
                f"- Question: {turn.get('question') or turn.get('content', '')[:120]}\n"
                f"  Columns: {turn.get('columns')}\n"
                f"  Rows returned: {len(turn.get('rows') or [])}"
            )
    structured_block = ""
    if structured_bits:
        structured_block = "\nStructured query results in this session:\n" + "\n".join(structured_bits) + "\n"

    prompt = f"""Summarize this data Q&A session for the user. They hit the follow-up limit and are starting a fresh chat.

{history_block}{structured_block}
Write 3–6 bullet points covering:
- Questions asked and main findings
- Key numbers or breakdowns mentioned
- Conversions, filters, or assumptions applied in follow-ups

Use Markdown bullets. Be concise and factual — do not invent data not present in the conversation.
"""
    return generate_answer(prompt, model=model, backend=backend, base_url=base_url).strip()


def prepare_session_context(
    question: str,
    history: list[dict[str, Any]] | None,
    *,
    model: str,
    backend: str,
    base_url: str,
    follow_up_limit: int | None = None,
) -> ConversationSessionDecision:
    """
    Decide effective history for this request.

    - After `follow_up_limit` completed user turns → summarize prior session, reset context.
    - Otherwise LLM classifies follow-up vs new topic; new topics clear history.
    """
    from settings_service import get_ask_conversation_turns

    if not history:
        return ConversationSessionDecision(
            effective_history=[],
            is_follow_up=False,
            is_new_topic=False,
            session_reset=False,
            session_summary=None,
            prior_turn_count=0,
        )

    limit = follow_up_limit if follow_up_limit is not None else get_ask_conversation_turns()
    prior_turn_count = count_user_turns(history)

    if limit > 0 and prior_turn_count >= limit:
        summary = summarize_conversation_session(
            history,
            model=model,
            backend=backend,
            base_url=base_url,
        )
        return ConversationSessionDecision(
            effective_history=[],
            is_follow_up=False,
            is_new_topic=False,
            session_reset=True,
            session_summary=summary,
            prior_turn_count=prior_turn_count,
        )

    heuristic = _heuristic_message_intent(question, history)
    if heuristic == "new_topic":
        return ConversationSessionDecision(
            effective_history=[],
            is_follow_up=False,
            is_new_topic=True,
            session_reset=True,
            session_summary=None,
            prior_turn_count=prior_turn_count,
        )
    if heuristic == "follow_up":
        return ConversationSessionDecision(
            effective_history=list(history),
            is_follow_up=True,
            is_new_topic=False,
            session_reset=False,
            session_summary=None,
            prior_turn_count=prior_turn_count,
        )

    intent = classify_message_intent(
        question,
        history,
        model=model,
        backend=backend,
        base_url=base_url,
    )
    if intent == "new_topic":
        return ConversationSessionDecision(
            effective_history=[],
            is_follow_up=False,
            is_new_topic=True,
            session_reset=True,
            session_summary=None,
            prior_turn_count=prior_turn_count,
        )

    return ConversationSessionDecision(
        effective_history=list(history),
        is_follow_up=True,
        is_new_topic=False,
        session_reset=False,
        session_summary=None,
        prior_turn_count=prior_turn_count,
    )
