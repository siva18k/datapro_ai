"""Resolve calendar/fiscal periods from natural language for SQL and MCP tools."""

from __future__ import annotations

import calendar
import json
import re
from datetime import date, datetime, timedelta
from typing import Any

_TEMPORAL_SIGNAL = re.compile(
    r"\b("
    r"last year|this year|prior year|previous year|next year|"
    r"last quarter|this quarter|prior quarter|previous quarter|"
    r"ytd|year to date|year-over-year|yoy|"
    r"fy\s?20\d{2}|fiscal year|"
    r"q[1-4]|20\d{2}|"
    r"quarter|quarterly|month|monthly|week|weekly|year|yearly|annual"
    r")\b",
    re.I,
)

_EXPLICIT_YEARS = re.compile(r"\b(20\d{2})\b")
_FY_YEAR = re.compile(r"\bfy\s?(20\d{2})\b", re.I)
_EXPLICIT_QUARTER = re.compile(r"\bq([1-4])\b", re.I)


def _parse_reference_date(value: str | None) -> date:
    if not value:
        return date.today()
    cleaned = value.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(cleaned).date()
    except ValueError:
        return datetime.strptime(cleaned[:10], "%Y-%m-%d").date()


def _month_start(year: int, month: int) -> date:
    return date(year, month, 1)


def _add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _month_end_exclusive(d: date) -> date:
    return _add_months(_month_start(d.year, d.month), 1)


def _calendar_quarter_start(year: int, quarter: int) -> date:
    if quarter not in (1, 2, 3, 4):
        raise ValueError("quarter must be 1-4")
    return date(year, (quarter - 1) * 3 + 1, 1)


def _calendar_quarter_end_exclusive(year: int, quarter: int) -> date:
    start = _calendar_quarter_start(year, quarter)
    return _add_months(start, 3)


def _fiscal_year_start(fiscal_year: int, fy_start_month: int) -> date:
    if fy_start_month == 1:
        return date(fiscal_year, 1, 1)
    return date(fiscal_year - 1, fy_start_month, 1)


def _fiscal_year_end_exclusive(fiscal_year: int, fy_start_month: int) -> date:
    return _fiscal_year_start(fiscal_year + 1, fy_start_month)


def _fiscal_quarter_bounds(fiscal_year: int, quarter: int, fy_start_month: int) -> tuple[date, date]:
    fy_start = _fiscal_year_start(fiscal_year, fy_start_month)
    start = _add_months(fy_start, (quarter - 1) * 3)
    end = _add_months(start, 3)
    return start, end


def _fiscal_year_for_calendar_date(d: date, fy_start_month: int) -> int:
    if fy_start_month == 1:
        return d.year
    fy_start = _fiscal_year_start(d.year, fy_start_month)
    if d >= fy_start:
        return d.year
    return d.year - 1


def _detect_granularity(text: str) -> str:
    lower = text.lower()
    if re.search(r"\b(quarter|quarterly|q[1-4])\b", lower):
        return "quarter"
    if re.search(r"\b(month|monthly)\b", lower):
        return "month"
    if re.search(r"\b(week|weekly)\b", lower):
        return "week"
    return "year"


def _build_period_dict(
    *,
    label: str,
    start: date,
    end_exclusive: date,
    granularity: str,
    calendar_year: int | None = None,
    quarter: int | None = None,
    fiscal_year: int | None = None,
    fiscal_quarter: int | None = None,
) -> dict[str, Any]:
    return {
        "label": label,
        "start": start.isoformat(),
        "end_exclusive": end_exclusive.isoformat(),
        "granularity": granularity,
        "calendar_year": calendar_year,
        "quarter": quarter,
        "fiscal_year": fiscal_year,
        "fiscal_quarter": fiscal_quarter,
    }


def _sql_filter(start: date, end_exclusive: date, *, granularity: str, dialect: str = "trino") -> dict[str, str]:
    from sql_dialect import date_range_filter

    start_s = start.isoformat()
    end_s = end_exclusive.isoformat()
    where = date_range_filter(start_s, end_s, dialect=dialect)
    group = ""
    if granularity == "quarter":
        group = "DATE_TRUNC('quarter', <date_column>)"
    elif granularity == "month":
        group = "DATE_TRUNC('month', <date_column>)"
    elif granularity == "week":
        group = "DATE_TRUNC('week', <date_column>)"
    return {
        "start_inclusive": start_s,
        "end_exclusive": end_s,
        "sql_where": where,
        "sql_group_by": group,
    }


def resolve_time_period(
    requirement: str,
    *,
    reference_date: str | None = None,
    fiscal_year_start_month: int = 1,
    sql_dialect: str = "trino",
) -> dict[str, Any]:
    """
    Turn a natural-language time requirement into concrete periods and SQL filter templates.

    ``fiscal_year_start_month`` is 1 for calendar years; use 4 for an April fiscal year start, etc.
    Replace ``<date_column>`` in SQL snippets with a catalog date column name.
    """
    text = (requirement or "").strip()
    if not text:
        raise ValueError("requirement is required")

    fy_start = max(1, min(int(fiscal_year_start_month or 1), 12))
    ref = _parse_reference_date(reference_date)
    lower = text.lower()
    granularity = _detect_granularity(text)
    use_fiscal = bool(_FY_YEAR.search(text) or re.search(r"\bfiscal year\b", lower)) or fy_start != 1

    explicit_years = [int(y) for y in _EXPLICIT_YEARS.findall(text)]
    fy_match = _FY_YEAR.search(text)
    fiscal_years: list[int] = [int(fy_match.group(1))] if fy_match else []

    if re.search(r"\blast year\b", lower) and not explicit_years and not fiscal_years:
        if use_fiscal:
            fiscal_years = [_fiscal_year_for_calendar_date(ref, fy_start) - 1]
        else:
            explicit_years = [ref.year - 1]
    elif re.search(r"\bthis year\b", lower) and not explicit_years and not fiscal_years:
        if use_fiscal:
            fiscal_years = [_fiscal_year_for_calendar_date(ref, fy_start)]
        else:
            explicit_years = [ref.year]

    explicit_quarter = _EXPLICIT_QUARTER.search(text)
    single_quarter = int(explicit_quarter.group(1)) if explicit_quarter else None

    periods: list[dict[str, Any]] = []
    notes: list[str] = []

    def add_calendar_year(year: int) -> None:
        if granularity == "quarter" and single_quarter:
            start = _calendar_quarter_start(year, single_quarter)
            end = _calendar_quarter_end_exclusive(year, single_quarter)
            periods.append(
                _build_period_dict(
                    label=f"Q{single_quarter}-{year}",
                    start=start,
                    end_exclusive=end,
                    granularity="quarter",
                    calendar_year=year,
                    quarter=single_quarter,
                )
            )
            return
        if granularity == "quarter":
            for q in range(1, 5):
                start = _calendar_quarter_start(year, q)
                end = _calendar_quarter_end_exclusive(year, q)
                periods.append(
                    _build_period_dict(
                        label=f"Q{q}-{year}",
                        start=start,
                        end_exclusive=end,
                        granularity="quarter",
                        calendar_year=year,
                        quarter=q,
                    )
                )
            return
        if granularity == "month":
            for month in range(1, 13):
                start = _month_start(year, month)
                end = _month_end_exclusive(start)
                periods.append(
                    _build_period_dict(
                        label=f"{start.strftime('%B')} {year}",
                        start=start,
                        end_exclusive=end,
                        granularity="month",
                        calendar_year=year,
                    )
                )
            return
        start = date(year, 1, 1)
        end = date(year + 1, 1, 1)
        periods.append(
            _build_period_dict(
                label=str(year),
                start=start,
                end_exclusive=end,
                granularity="year",
                calendar_year=year,
            )
        )

    def add_fiscal_year(fy: int) -> None:
        if granularity == "quarter" and single_quarter:
            start, end = _fiscal_quarter_bounds(fy, single_quarter, fy_start)
            periods.append(
                _build_period_dict(
                    label=f"FQ{single_quarter} FY{fy}",
                    start=start,
                    end_exclusive=end,
                    granularity="quarter",
                    fiscal_year=fy,
                    fiscal_quarter=single_quarter,
                )
            )
            return
        if granularity == "quarter":
            for q in range(1, 5):
                start, end = _fiscal_quarter_bounds(fy, q, fy_start)
                periods.append(
                    _build_period_dict(
                        label=f"FQ{q} FY{fy}",
                        start=start,
                        end_exclusive=end,
                        granularity="quarter",
                        fiscal_year=fy,
                        fiscal_quarter=q,
                    )
                )
            return
        start = _fiscal_year_start(fy, fy_start)
        end = _fiscal_year_end_exclusive(fy, fy_start)
        periods.append(
            _build_period_dict(
                label=f"FY{fy}",
                start=start,
                end_exclusive=end,
                granularity="year",
                fiscal_year=fy,
            )
        )

    if fiscal_years:
        for fy in sorted(set(fiscal_years)):
            add_fiscal_year(fy)
    elif explicit_years:
        for year in sorted(set(explicit_years)):
            add_calendar_year(year)
    elif re.search(r"\blast quarter\b", lower):
        ref_q = ((ref.month - 1) // 3) + 1
        ref_y = ref.year
        if ref_q == 1:
            ref_q, ref_y = 4, ref_y - 1
        else:
            ref_q -= 1
        if use_fiscal:
            fy = _fiscal_year_for_calendar_date(_calendar_quarter_start(ref_y, ref_q), fy_start)
            start, end = _fiscal_quarter_bounds(fy, ref_q, fy_start)
            label = f"FQ{ref_q} FY{fy}"
            periods.append(
                _build_period_dict(
                    label=label,
                    start=start,
                    end_exclusive=end,
                    granularity="quarter",
                    fiscal_year=fy,
                    fiscal_quarter=ref_q,
                )
            )
        else:
            start = _calendar_quarter_start(ref_y, ref_q)
            end = _calendar_quarter_end_exclusive(ref_y, ref_q)
            periods.append(
                _build_period_dict(
                    label=f"Q{ref_q}-{ref_y}",
                    start=start,
                    end_exclusive=end,
                    granularity="quarter",
                    calendar_year=ref_y,
                    quarter=ref_q,
                )
            )
    elif re.search(r"\bthis quarter\b", lower):
        ref_q = ((ref.month - 1) // 3) + 1
        start = _calendar_quarter_start(ref.year, ref_q)
        end = _calendar_quarter_end_exclusive(ref.year, ref_q)
        periods.append(
            _build_period_dict(
                label=f"Q{ref_q}-{ref.year}",
                start=start,
                end_exclusive=end,
                granularity="quarter",
                calendar_year=ref.year,
                quarter=ref_q,
            )
        )
    elif re.search(r"\bytd\b|year to date\b", lower):
        start = date(ref.year, 1, 1) if fy_start == 1 else _fiscal_year_start(_fiscal_year_for_calendar_date(ref, fy_start), fy_start)
        end = ref + timedelta(days=1)
        periods.append(
            _build_period_dict(
                label="YTD",
                start=start,
                end_exclusive=end,
                granularity="month",
                calendar_year=ref.year,
            )
        )
    else:
        notes.append("No explicit year or relative period detected — provide a year, quarter, or phrase like 'last year'.")

    if not periods:
        return {
            "requirement": text,
            "reference_date": ref.isoformat(),
            "fiscal_year_start_month": fy_start,
            "granularity": granularity,
            "periods": [],
            "filter": None,
            "notes": notes,
        }

    overall_start = min(date.fromisoformat(p["start"]) for p in periods)
    overall_end = max(date.fromisoformat(p["end_exclusive"]) for p in periods)
    filt = _sql_filter(overall_start, overall_end, granularity=granularity, dialect=sql_dialect)

    if use_fiscal and fy_start != 1:
        notes.append(f"Using fiscal year starting month {fy_start}.")
    if explicit_years and re.search(r"\blast year\b", lower):
        notes.append("Both an explicit year and 'last year' were present — used explicit year(s).")

    return {
        "requirement": text,
        "reference_date": ref.isoformat(),
        "fiscal_year_start_month": fy_start,
        "granularity": granularity,
        "periods": periods,
        "filter": filt,
        "sql_dialect": sql_dialect,
        "notes": notes,
    }


def has_temporal_signal(text: str) -> bool:
    return bool(_TEMPORAL_SIGNAL.search(text or ""))


def parse_temporal_bucket(value: Any) -> date | None:
    """Parse a SQL bucket value (timestamp/date/string) into a calendar date."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    cleaned = text.replace("Z", "+00:00") if text.endswith("Z") else text
    try:
        return datetime.fromisoformat(cleaned).date()
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[: len(fmt.replace("%f", "000000"))], fmt).date()
        except ValueError:
            continue
    match = re.match(r"^(\d{4}-\d{2}-\d{2})", text)
    if match:
        try:
            return date.fromisoformat(match.group(1))
        except ValueError:
            return None
    return None


def _generic_bucket_label(d: date, granularity: str, *, fy_start: int = 1) -> str:
    """Fallback label when a bucket is not in the resolved period list."""
    if granularity == "quarter":
        if fy_start != 1:
            fy = _fiscal_year_for_calendar_date(d, fy_start)
            fy_start_date = _fiscal_year_start(fy, fy_start)
            month_offset = (d.year - fy_start_date.year) * 12 + (d.month - fy_start_date.month)
            fq = month_offset // 3 + 1
            return f"FQ{fq} FY{fy}"
        quarter = (d.month - 1) // 3 + 1
        return f"Q{quarter}-{d.year}"
    if granularity == "month":
        return d.strftime("%b-%Y")
    if granularity == "week":
        year, week, _ = d.isocalendar()
        return f"W{week:02d}-{year}"
    if granularity == "year":
        if fy_start != 1:
            return f"FY{_fiscal_year_for_calendar_date(d, fy_start)}"
        return str(d.year)
    return d.isoformat()


def display_label_for_bucket(value: Any, resolved: dict[str, Any]) -> str | None:
    """Map a grouped date/timestamp bucket to a human-readable period label."""
    bucket = parse_temporal_bucket(value)
    if bucket is None:
        return None

    periods = resolved.get("periods") or []
    for period in periods:
        start = date.fromisoformat(str(period["start"]))
        end = date.fromisoformat(str(period["end_exclusive"]))
        if start <= bucket < end:
            return str(period.get("label") or _generic_bucket_label(
                bucket,
                str(resolved.get("granularity") or "year"),
                fy_start=int(resolved.get("fiscal_year_start_month") or 1),
            ))

    granularity = str(resolved.get("granularity") or "year")
    fy_start = int(resolved.get("fiscal_year_start_month") or 1)
    return _generic_bucket_label(bucket, granularity, fy_start=fy_start)


def _column_has_temporal_buckets(rows: list[list[Any]], column_index: int) -> bool:
    sample = rows[: min(len(rows), 20)]
    if not sample:
        return False
    hits = 0
    for row in sample:
        if column_index >= len(row):
            continue
        if parse_temporal_bucket(row[column_index]) is not None:
            hits += 1
    return hits >= max(1, len(sample) * 0.5)


def temporal_column_indices(columns: list[str], rows: list[list[Any]]) -> list[int]:
    """Columns whose values look like DATE_TRUNC / timestamp buckets."""
    if not columns or not rows:
        return []
    name_hints = ("quarter", "month", "year", "period", "date", "time", "bucket")
    indices: list[int] = []
    for i, col in enumerate(columns):
        base = col.split(".")[-1].lower()
        if any(hint in base for hint in name_hints) and _column_has_temporal_buckets(rows, i):
            indices.append(i)
    if indices:
        return indices
    return [i for i in range(len(columns)) if _column_has_temporal_buckets(rows, i)]


def detect_temporal_label_column(columns: list[str], rows: list[list[Any]]) -> int | None:
    indices = temporal_column_indices(columns, rows)
    return indices[0] if indices else None


def apply_period_labels_to_rows(
    columns: list[str],
    rows: list[list[Any]],
    label_column: int | None,
    resolved: dict[str, Any],
    *,
    all_temporal_columns: bool = True,
) -> list[list[Any]]:
    """Replace raw DATE_TRUNC bucket values with resolved period labels."""
    if not rows or not resolved.get("periods"):
        return rows

    target_columns: list[int]
    if all_temporal_columns:
        target_columns = temporal_column_indices(columns, rows)
    elif label_column is not None and 0 <= label_column < len(columns):
        target_columns = [label_column]
    else:
        return rows

    if not target_columns:
        return rows

    updated: list[list[Any]] = []
    for row in rows:
        new_row = list(row)
        for col_idx in target_columns:
            if col_idx < len(new_row):
                label = display_label_for_bucket(new_row[col_idx], resolved)
                if label:
                    new_row[col_idx] = label
        updated.append(new_row)
    return updated


def time_context_from_mcp_enrichment(enrichment: Any) -> dict[str, Any] | None:
    for item in getattr(enrichment, "tool_results", []) or []:
        if getattr(item, "tool", None) != "resolve_time_period":
            continue
        structured = getattr(item, "structured", None)
        if isinstance(structured, dict) and structured.get("periods"):
            out = dict(structured)
            out["source"] = "mcp"
            return out
    return None


def resolve_time_context_for_question(
    question: str,
    enrichment: Any | None = None,
) -> dict[str, Any] | None:
    from_mcp = time_context_from_mcp_enrichment(enrichment) if enrichment else None
    if from_mcp:
        return from_mcp
    return fetch_time_context(question)


def format_query_results_with_time_context(
    question: str,
    columns: list[str],
    rows: list[list[Any]],
    *,
    time_context: dict[str, Any] | None = None,
    enrichment: Any | None = None,
) -> tuple[list[str], list[list[Any]], dict[str, Any] | None]:
    """Resolve MCP/local time periods and rewrite temporal bucket cells."""
    resolved = time_context or resolve_time_context_for_question(question, enrichment)
    if not resolved or not resolved.get("periods") or not rows:
        return columns, rows, resolved
    display_rows = apply_period_labels_to_rows(
        columns,
        rows,
        label_column=None,
        resolved=resolved,
        all_temporal_columns=True,
    )
    return columns, display_rows, resolved


def fetch_time_context(
    requirement: str,
    *,
    reference_date: str | None = None,
    fiscal_year_start_month: int = 1,
    sql_dialect: str = "trino",
    mcp_url: str | None = None,
) -> dict[str, Any] | None:
    """
    Resolve time periods for analytics/dashboard display.

    Prefers the local MCP ``resolve_time_period`` tool when reachable; falls back to
    the in-process resolver (same logic as the MCP tool).
    """
    if not has_temporal_signal(requirement):
        return None

    url = mcp_url
    try:
        from mcp_client import call_tool_text, check_mcp_server, get_default_mcp_url

        url = url or get_default_mcp_url()
        if check_mcp_server(url):
            args: dict[str, Any] = {"requirement": requirement.strip()}
            if reference_date:
                args["reference_date"] = reference_date
            if fiscal_year_start_month != 1:
                args["fiscal_year_start_month"] = fiscal_year_start_month
            raw = call_tool_text(url, "resolve_time_period", args)
            parsed = json.loads(raw) if raw else None
            if isinstance(parsed, dict) and parsed.get("periods"):
                parsed["source"] = "mcp"
                return parsed
    except Exception:
        pass

    resolved = resolve_time_period(
        requirement,
        reference_date=reference_date,
        fiscal_year_start_month=fiscal_year_start_month,
        sql_dialect=sql_dialect,
    )
    if not resolved.get("periods"):
        return None
    resolved["source"] = "local"
    return resolved


def format_time_period_hints(resolved: dict[str, Any]) -> str:
    """Compact block for SQL prompts."""
    if not resolved.get("periods"):
        return ""
    lines = [
        "",
        "Resolved time periods (from temporal context service):",
        f"- Granularity: {resolved.get('granularity')}",
    ]
    filt = resolved.get("filter") or {}
    if filt.get("sql_where"):
        lines.append(f"- Overall filter: `{filt['sql_where']}`")
    if filt.get("sql_group_by"):
        lines.append(f"- Suggested grouping: `{filt['sql_group_by']}`")
        lines.append(
            "- Chat/table labels use resolved period names (e.g. Q1-2024) — "
            "DATE_TRUNC buckets are mapped automatically after query execution."
        )
    lines.append("- Periods:")
    for period in resolved["periods"][:8]:
        lines.append(
            f"  - {period['label']}: {period['start']} to {period['end_exclusive']} (exclusive end)"
        )
    if len(resolved["periods"]) > 8:
        lines.append(f"  - … and {len(resolved['periods']) - 8} more")
    for note in resolved.get("notes") or []:
        lines.append(f"- Note: {note}")
    lines.append("- Replace `<date_column>` with the best catalog date column from Column reference.")
    dialect = resolved.get("sql_dialect") or "trino"
    from sql_dialect import dialect_label, format_date_literal

    example = format_date_literal("2024-01-01", dialect=dialect)
    lines.append(
        f"- Date filters ({dialect_label(dialect)}): e.g. `<date_column> >= {example}`."
    )
    return "\n".join(lines)
