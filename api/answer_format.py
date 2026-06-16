"""Shared instructions for readable chat-formatted LLM answers."""

from __future__ import annotations

from typing import Any

CHAT_RESPONSE_FORMAT = """
Format your reply for a chat window — clear, scannable, and human-readable. Never dump raw data.

Use Markdown:
- Open with **one sentence** stating the main answer or insight.
- Use **bullet points** for lists, steps, or multiple findings.
- Use a **markdown table** when comparing several items with multiple fields (keep ≤10 rows in chat).
  Put each table row on its own line (header, separator, then one row per line). Never collapse the whole table onto one line.
- Use **bold** for key metrics, names, and labels; use *italics* sparingly for notes or caveats.
- Keep paragraphs short (2–3 sentences at most).

When result sets are large (more than ~10 rows or many columns):
- Highlight only the top rows or most important values in chat.
- Mention that the user can open the **HTML export** for the complete table.
- Do not paste the entire dataset as unformatted text.

Stay accurate to the provided data. Do not invent values.
""".strip()


def build_sql_summary_prompt(
    *,
    question: str,
    columns: list[str],
    rows: list[list[Any]],
    max_sample_rows: int = 15,
    conversation_history: list[dict[str, str]] | None = None,
) -> str:
    from conversation_context import format_conversation_block

    row_count = len(rows)
    sample = rows[:max_sample_rows]
    large = row_count > 10
    history_block = format_conversation_block(conversation_history)

    extra = ""
    if large:
        extra = (
            f"\nThe full result has {row_count} rows — show at most 10 in a table and "
            "tell the user they can use **Generate HTML** (or the HTML export option) "
            "for the complete data.\n"
        )

    follow_up_line = ""
    if history_block:
        follow_up_line = (
            "The latest user message may be a follow-up — use prior conversation only to interpret it.\n\n"
        )

    return f"""You are a business analyst answering in a chat UI.

{history_block}{follow_up_line}User question:
{question}

Query returned {row_count} row(s).
Columns: {columns}
Data sample (for your answer — may be truncated):
{sample}
{extra}
{CHAT_RESPONSE_FORMAT}
"""


def build_analytics_summary_prompt(
    *,
    question: str,
    columns: list[str],
    rows: list[list[Any]],
    max_sample_rows: int = 8,
    gap_notes: list[str] | None = None,
) -> str:
    """Brief insight for analytics dashboard — charts/tables render the data."""
    sample = rows[:max_sample_rows]
    skipped = ""
    if gap_notes:
        skipped = (
            "\nSome requested dimensions were unavailable:\n"
            + "\n".join(f"- {n}" for n in gap_notes)
            + "\nThe SQL omitted those elements — summarize what the data does show.\n"
        )
    return f"""You are a business analyst writing a one-line dashboard insight.

User question:
{question}
{skipped}
Query returned {len(rows)} row(s).
Columns: {columns}
Sample rows (for context only — do NOT repeat as a table):
{sample}

Reply with ONE or TWO short sentences only:
- State the main finding or headline number.
- No markdown tables, bullet lists, or row-by-row dumps.
- No "sorted by" or column listing.
- Bold one key metric if helpful.
"""
