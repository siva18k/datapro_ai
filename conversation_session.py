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
- **follow_up** — continues the same analysis thread (refinement, conversion, filter tweak, clarification, sort, same entities/metrics)
- **new_topic** — starts a clearly different question (unrelated domain, metric, dataset, or business question with no dependency on prior answers)

Short acknowledgements like "thanks" after a complete answer are follow_up only if they request more work on the same data; otherwise treat obvious new analytical questions as new_topic.

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
