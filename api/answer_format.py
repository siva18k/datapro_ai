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
    table_rules: str = "",
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
            "The latest user message is a follow-up. Use prior conversation to interpret it.\n"
            "If notes mention a conversion or transformation, explain it briefly in your answer.\n"
            "Do not change the breakdown or scope unless the user clearly asked to.\n\n"
        )

    rules_block = ""
    if table_rules.strip():
        rules_block = (
            "Catalog table business rules (mention in your answer when they affected the result, "
            "e.g. revenue counts SHIPPED orders only):\n"
            f"{table_rules.strip()}\n\n"
        )

    return f"""You are a business analyst answering in a chat UI.

{history_block}{follow_up_line}{rules_block}User question:
{question}

Query returned {row_count} row(s).
Columns: {columns}
Data sample (for your answer — may be truncated; time bucket columns already use labels like Q1-2024):
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
    conversation_history: list[dict[str, str]] | None = None,
    table_rules: str = "",
) -> str:
    """Brief insight for analytics dashboard — charts/tables render the data."""
    from conversation_context import format_conversation_block

    sample = rows[:max_sample_rows]
    history_block = format_conversation_block(conversation_history)
    skipped = ""
    if gap_notes:
        skipped = (
            "\nNotes (include methodology in your insight when relevant):\n"
            + "\n".join(f"- {n}" for n in gap_notes)
            + "\n"
        )
    follow_up = ""
    if history_block:
        follow_up = (
            "This is a follow-up — keep the same scope/grain as the prior answer unless the user changed it.\n"
        )
    rules_block = ""
    if table_rules.strip():
        rules_block = (
            "Catalog table business rules (mention briefly if they shaped the metric, "
            "e.g. SHIPPED-only revenue):\n"
            f"{table_rules.strip()}\n"
        )
    return f"""You are a business analyst writing a one-line dashboard insight.

{history_block}{follow_up}{rules_block}User question:
{question}
{skipped}
Query returned {len(rows)} row(s).
Columns: {columns}
Sample rows (for context only — do NOT repeat as a table):
{sample}

Reply with ONE or TWO short sentences only:
- State the main finding or headline number.
- If a conversion or assumption was applied, mention it briefly (e.g. FX rate used).
- No markdown tables, bullet lists, or row-by-row dumps.
- No "sorted by" or column listing.
- Bold one key metric if helpful.
"""
