"""Build analytics API payload from SQL results (raw data + defaults; UI renders widgets)."""

from __future__ import annotations

import re
from typing import Any

from api.ask_export import (
    _build_chart_title,
    _format_number,
    _humanize_column,
    _numeric_columns,
    _pick_label_column,
    _pick_value_column,
)
from api.analytics_models import AnalyticsChartDefaults, AnalyticsResponse, KpiWidget


def _dashboard_title(prompt: str) -> str:
    text = prompt.strip().splitlines()[0].strip()
    text = re.sub(r"\?$", "", text)
    if len(text) > 80:
        text = text[:77] + "…"
    return text or "Analytics dashboard"


def _is_currency_column(name: str) -> bool:
    return bool(re.search(r"(revenue|amount|price|cost|profit|sales|usd)", name, re.I))


def _brief_summary(summary: str) -> str:
    """Keep a short insight line — strip tables and long markdown dumps."""
    lines: list[str] = []
    for line in summary.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("|") or stripped.count("|") >= 2:
            continue
        if stripped.startswith("#"):
            stripped = re.sub(r"^#+\s*", "", stripped)
        stripped = re.sub(r"\*\*([^*]+)\*\*", r"\1", stripped)
        if stripped and not re.search(r"\bsorted by\b", stripped, re.I):
            lines.append(stripped)
    text = " ".join(lines)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > 280:
        text = text[:277] + "…"
    return text


def build_dashboard(
    *,
    prompt: str,
    summary: str,
    columns: list[str] | None,
    rows: list[list[Any]] | None,
    domain_name: str | None = None,
    routing_method: str | None = None,
    sql: str | None = None,
    notes: list[str] | None = None,
) -> AnalyticsResponse:
    title = _dashboard_title(prompt)
    brief = _brief_summary(summary) if summary else None
    gap_notes = notes or []

    if not columns or not rows:
        return AnalyticsResponse(
            title=title,
            summary=brief
            or (
                "No tabular data returned. Try an analytical question against a "
                "structured postgres dataset (e.g. revenue by country, top customers)."
            ),
            domain_name=domain_name,
            routing_method=routing_method,
            query_kind="structured",
            sql=sql,
            notes=gap_notes,
        )

    numeric_idxs = _numeric_columns(columns, rows)
    numeric_set = set(numeric_idxs)
    kpis: list[KpiWidget] = []

    if len(rows) == 1 and numeric_idxs:
        for idx in numeric_idxs[:4]:
            raw = rows[0][idx] if idx < len(rows[0]) else None
            try:
                val = float(raw)
            except (TypeError, ValueError):
                continue
            kpis.append(
                KpiWidget(
                    label=_humanize_column(columns[idx]),
                    value=_format_number(val, currency=_is_currency_column(columns[idx])),
                )
            )

    chart_defaults: AnalyticsChartDefaults | None = None
    if len(rows) > 1 and numeric_idxs:
        label_idx = _pick_label_column(columns, numeric_set)
        value_idx = _pick_value_column(columns, numeric_idxs)
        chart_type = "bar"
        if re.search(r"\b(breakdown|share|distribution|percent)\b", prompt, re.I):
            chart_type = "pie"
        elif len(rows) > 12:
            chart_type = "line"
        chart_defaults = AnalyticsChartDefaults(
            chart_type=chart_type,  # type: ignore[arg-type]
            label_column=label_idx,
            value_column=value_idx,
            chart_title=_build_chart_title(
                question=prompt,
                columns=columns,
                label_idx=label_idx,
                value_idx=value_idx,
                row_count=min(len(rows), 50),
            ),
        )

    return AnalyticsResponse(
        title=title,
        summary=brief,
        columns=columns,
        rows=rows[:100],
        total_rows=len(rows),
        chart_defaults=chart_defaults,
        kpis=kpis,
        domain_name=domain_name,
        routing_method=routing_method,
        query_kind="structured",
        sql=sql,
        notes=gap_notes,
    )
