"""Build SQL generation hints from catalog metadata and the user question (domain-agnostic)."""

from __future__ import annotations

import re
from typing import Any

from temporal_context import fetch_time_context, format_time_period_hints, has_temporal_signal

_METRIC_QUESTION = re.compile(
    r"\b(revenue|sales|amount|total|count|average|avg|sum|volume|value)\b",
    re.I,
)

_DATE_TYPE_MARKERS = ("date", "timestamp", "time")
_DATE_NAME_MARKERS = ("date", "time", "year", "month", "quarter", "period", "day")
_METRIC_NAME_MARKERS = (
    "amount",
    "revenue",
    "total",
    "count",
    "price",
    "value",
    "qty",
    "quantity",
    "sum",
    "balance",
)


def _question_tokens(question: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", question.lower()) if len(t) > 2}


def _column_labels(col: dict[str, Any]) -> list[str]:
    raw = col.get("labels") or []
    return [str(x).strip() for x in raw if str(x).strip()]


def _looks_like_date_column(col: dict[str, Any]) -> bool:
    dtype = (col.get("data_type") or "").lower()
    if any(marker in dtype for marker in _DATE_TYPE_MARKERS):
        return True
    name = col["column_name"].lower()
    if any(marker in name for marker in _DATE_NAME_MARKERS):
        return True
    for label in _column_labels(col):
        low = label.lower()
        if any(marker in low for marker in _DATE_NAME_MARKERS):
            return True
    return False


def _looks_like_metric_column(col: dict[str, Any]) -> bool:
    name = col["column_name"].lower()
    if any(marker in name for marker in _METRIC_NAME_MARKERS):
        return True
    desc = (col.get("description") or "").lower()
    if any(marker in desc for marker in _METRIC_NAME_MARKERS):
        return True
    for label in _column_labels(col):
        low = label.lower()
        if any(marker in low for marker in _METRIC_NAME_MARKERS):
            return True
    return False


def _table_role_weight(role: str | None) -> float:
    normalized = (role or "fact").lower()
    if normalized == "fact":
        return 2.0
    if normalized in {"dimension", "lookup"}:
        return 0.5
    if normalized == "excluded":
        return -5.0
    return 1.0


def _score_column_for_question(
    question_tokens: set[str],
    table: dict[str, Any],
    col: dict[str, Any],
    *,
    kind: str,
) -> float:
    score = _table_role_weight(table.get("table_role"))
    name = col["column_name"].lower()
    table_name = table["table_name"].lower()

    if kind == "date":
        dtype = (col.get("data_type") or "").lower()
        if "timestamp" in dtype or dtype == "date":
            score += 3.0
        elif any(marker in name for marker in _DATE_NAME_MARKERS):
            score += 2.0
    else:
        if any(marker in name for marker in _METRIC_NAME_MARKERS):
            score += 2.5

    for part in re.split(r"[_\s]+", name):
        if len(part) > 2 and part in question_tokens:
            score += 2.0

    for label in _column_labels(col):
        for part in re.split(r"[\s_]+", label.lower()):
            if len(part) > 2 and part in question_tokens:
                score += 2.5

    for part in re.split(r"[_\s]+", table_name):
        if len(part) > 2 and part in question_tokens:
            score += 1.0

    desc = (col.get("description") or "").lower()
    for tok in question_tokens:
        if tok in desc:
            score += 0.5

    return score


def _format_column_ref(table: dict[str, Any], col: dict[str, Any]) -> str:
    rel = f"{table['table_schema']}.{table['table_name']}"
    labels = _column_labels(col)
    label_text = f", labels: [{', '.join(labels)}]" if labels else ""
    dtype = col.get("data_type") or "?"
    return f"`{rel}`.`{col['column_name']}` ({dtype}{label_text})"


def _rank_columns(
    ctx: Any,
    question: str,
    *,
    kind: str,
    predicate,
) -> list[tuple[float, dict[str, Any], dict[str, Any]]]:
    tokens = _question_tokens(question)
    ranked: list[tuple[float, dict[str, Any], dict[str, Any]]] = []
    for table in ctx.tables or []:
        if not table.get("enabled", True):
            continue
        if (table.get("table_role") or "fact") == "excluded":
            continue
        for col in table.get("columns") or []:
            if not predicate(col):
                continue
            score = _score_column_for_question(tokens, table, col, kind=kind)
            ranked.append((score, table, col))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked


def build_temporal_sql_hints(
    question: str,
    ctx: Any,
    *,
    fiscal_year_start_month: int = 1,
    reference_date: str | None = None,
) -> str:
    """
    When the question has a time dimension, suggest catalog date/metric columns
    and resolved period boundaries — derived from metadata + temporal context service.
    """
    if not ctx or not getattr(ctx, "tables", None):
        return ""
    if not has_temporal_signal(question):
        return ""

    resolved = fetch_time_context(
        question,
        reference_date=reference_date,
        fiscal_year_start_month=fiscal_year_start_month,
    )
    if not resolved:
        resolved = {"periods": []}
    period_block = format_time_period_hints(resolved)

    metric_ranked = _rank_columns(ctx, question, kind="metric", predicate=_looks_like_metric_column)
    metric_score_by_table: dict[str, float] = {}
    for score, table, _col in metric_ranked:
        tid = str(table.get("id") or "")
        if tid:
            metric_score_by_table[tid] = max(metric_score_by_table.get(tid, 0.0), score)

    date_ranked_raw = _rank_columns(ctx, question, kind="date", predicate=_looks_like_date_column)
    date_ranked: list[tuple[float, dict[str, Any], dict[str, Any]]] = []
    for score, table, col in date_ranked_raw:
        tid = str(table.get("id") or "")
        boosted = score + metric_score_by_table.get(tid, 0.0) * 0.75
        date_ranked.append((boosted, table, col))
    date_ranked.sort(key=lambda item: item[0], reverse=True)

    if not date_ranked and not period_block:
        return ""

    lines: list[str] = []
    if period_block:
        lines.append(period_block)
    else:
        lines.extend(["", "Temporal context (from catalog metadata + question):"])

    if date_ranked:
        lines.append("- Candidate date columns (pick the best match; use exact names):")
        seen_refs: set[str] = set()
        for _score, table, col in date_ranked[:4]:
            ref = _format_column_ref(table, col)
            if ref in seen_refs:
                continue
            seen_refs.add(ref)
            lines.append(f"  - {ref}")

    if _METRIC_QUESTION.search(question):
        if metric_ranked:
            lines.append("- Candidate metric columns for aggregation:")
            seen_refs.clear()
            for _score, table, col in metric_ranked[:4]:
                ref = _format_column_ref(table, col)
                if ref in seen_refs:
                    continue
                seen_refs.add(ref)
                lines.append(f"  - {ref}")

    lines.append(
        "- Use schema-qualified catalog table names only; map label phrases to Column reference names."
    )
    lines.append(
        "- Apply filters and business rules documented in Table business rules when present."
    )
    return "\n".join(lines)
