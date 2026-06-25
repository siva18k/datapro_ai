"""LLM-driven follow-up handling for structured SQL / analytics answers."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class PriorStructuredResult:
    question: str
    sql: str | None
    columns: list[str]
    rows: list[list[Any]]


@dataclass
class StructuredFollowUpPlan:
    mode: Literal["transform", "sql"]
    refined_question: str
    notes: list[str] = field(default_factory=list)
    transform_spec: dict[str, Any] | None = None


def extract_prior_structured_result(history: list[dict[str, Any]] | None) -> PriorStructuredResult | None:
    """Most recent assistant turn that includes tabular query results."""
    if not history:
        return None
    for turn in reversed(history):
        if (turn.get("role") or "").strip().lower() != "assistant":
            continue
        columns = turn.get("columns")
        rows = turn.get("rows")
        if not columns or rows is None:
            continue
        return PriorStructuredResult(
            question=(turn.get("question") or "").strip(),
            sql=turn.get("sql"),
            columns=[str(c) for c in columns],
            rows=[list(r) for r in rows],
        )
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


def _col_index(columns: list[str], name: str) -> int | None:
    target = name.strip().lower()
    for i, col in enumerate(columns):
        if col.strip().lower() == target:
            return i
    return None


def apply_structured_transform(
    prior: PriorStructuredResult,
    spec: dict[str, Any],
) -> tuple[list[str], list[list[Any]]]:
    """Apply an LLM-authored transform spec to all prior rows."""
    columns = list(prior.columns)
    rows = [list(r) for r in prior.rows]

    for conv in spec.get("conversions") or []:
        if not isinstance(conv, dict):
            continue
        src = str(conv.get("source_column") or "").strip()
        if not src:
            continue
        src_idx = _col_index(columns, src)
        if src_idx is None:
            continue
        tgt = str(conv.get("target_column") or src).strip()
        factor = conv.get("factor")
        if factor is None:
            continue
        try:
            factor_f = float(factor)
        except (TypeError, ValueError):
            continue
        tgt_idx = _col_index(columns, tgt)
        if tgt_idx is None:
            columns.append(tgt)
            tgt_idx = len(columns) - 1
            for row in rows:
                while len(row) < len(columns):
                    row.append(None)
        for row in rows:
            while len(row) < len(columns):
                row.append(None)
            try:
                raw = row[src_idx]
                if raw is None:
                    row[tgt_idx] = None
                else:
                    row[tgt_idx] = round(float(raw) * factor_f, 4)
            except (TypeError, ValueError):
                row[tgt_idx] = None
        if conv.get("replace") and tgt != src:
            drop_idx = _col_index(columns, src)
            if drop_idx is not None and drop_idx != tgt_idx:
                columns.pop(drop_idx)
                adj_tgt = tgt_idx - 1 if drop_idx < tgt_idx else tgt_idx
                rows = [[r[i] for i in range(len(r)) if i != drop_idx] for r in rows]
                tgt_idx = adj_tgt

    rename_map = spec.get("rename_columns") or {}
    if isinstance(rename_map, dict):
        for old, new in rename_map.items():
            idx = _col_index(columns, str(old))
            if idx is not None:
                columns[idx] = str(new)

    drop_cols = spec.get("drop_columns") or []
    if isinstance(drop_cols, list):
        drop_indices = sorted(
            {idx for name in drop_cols if (idx := _col_index(columns, str(name))) is not None},
            reverse=True,
        )
        for idx in drop_indices:
            columns.pop(idx)
            rows = [[r[i] for i in range(len(r)) if i != idx] for r in rows]

    sort_by = spec.get("sort_by")
    if isinstance(sort_by, dict):
        col = str(sort_by.get("column") or "").strip()
        idx = _col_index(columns, col)
        if idx is not None:
            descending = bool(sort_by.get("descending"))

            def sort_key(row: list[Any]) -> tuple[int, Any]:
                val = row[idx] if idx < len(row) else None
                try:
                    return (0, float(val))
                except (TypeError, ValueError):
                    return (1, str(val) if val is not None else "")

            rows.sort(key=sort_key, reverse=descending)

    return columns, rows


def plan_structured_follow_up(
    question: str,
    history: list[dict[str, Any]] | None,
    prior: PriorStructuredResult | None,
    *,
    model: str,
    backend: str,
    base_url: str,
) -> StructuredFollowUpPlan:
    """Ask the LLM whether to transform prior results or run a new SQL query."""
    from api.llm import generate_answer
    from conversation_context import format_conversation_block

    if not prior or not history:
        return StructuredFollowUpPlan(mode="sql", refined_question=question)

    history_block = format_conversation_block(
        [{"role": t["role"], "content": t["content"]} for t in history if t.get("content")]
    )
    preview_rows = prior.rows[:25]

    prompt = f"""You are a data analyst handling a follow-up to a prior database query.

{history_block}Prior user question: {prior.question or "(unknown)"}
Prior SQL:
{prior.sql or "(none)"}

Prior result — {len(prior.rows)} row(s), columns: {prior.columns}
Sample rows:
{preview_rows}

Latest follow-up message:
{question}

Choose ONE approach:

1. **transform** — The follow-up adjusts the SAME result set (currency/unit conversion, rename, sort, add computed column, drop a column). Keep the same grain/keys (same customers, countries, etc.) — do NOT switch breakdown (e.g. customer → channel).

2. **sql** — The follow-up needs NEW data from the database (different filters, entities, time range, or breakdown).

For **transform**, use your general knowledge where needed (e.g. FX rates). Return a spec Python will apply to every row:
- `conversions`: list of {{source_column, target_column, factor, replace?}}
- optional `rename_columns`, `drop_columns`, `sort_by`: {{column, descending}}

For **sql**, write `refined_question`: a standalone question for the follow-up only.
Preserve prior filters/grouping ONLY when the follow-up explicitly refines the same breakdown
(e.g. "same but for 2024", "also exclude returns", "add customer count to that table").
When the follow-up changes breakdown, time grain, or entities, write a fresh question for the new
request — do NOT carry over dimensions the user did not mention (e.g. do not keep "by channel"
when they now ask for quarterly totals only).

Return ONLY JSON:
{{
  "mode": "transform" | "sql",
  "methodology": "Explain assumptions (e.g. FX rate and date) or why a new query is needed",
  "refined_question": "required for sql mode",
  "transform_spec": {{ ... }} | null
}}
"""
    raw = generate_answer(prompt, model=model, backend=backend, base_url=base_url)
    try:
        data = _parse_json_object(raw)
    except (ValueError, json.JSONDecodeError):
        return StructuredFollowUpPlan(
            mode="sql",
            refined_question=question,
            notes=["Could not interpret follow-up — running a fresh query with conversation context."],
        )

    mode = str(data.get("mode") or "sql").strip().lower()
    methodology = str(data.get("methodology") or "").strip()
    notes = [methodology] if methodology else []

    if mode == "transform":
        spec = data.get("transform_spec")
        if isinstance(spec, dict) and spec.get("conversions"):
            return StructuredFollowUpPlan(
                mode="transform",
                refined_question=question,
                notes=notes,
                transform_spec=spec,
            )

    refined = str(data.get("refined_question") or question).strip() or question
    return StructuredFollowUpPlan(mode="sql", refined_question=refined, notes=notes)
