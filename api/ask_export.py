"""Generate HTML, CSV, and chart exports from Ask responses."""

from __future__ import annotations

import csv
import html
import io
import json
import re
from typing import Any


def _esc(text: str) -> str:
    return html.escape(str(text))


def _is_markdown_table_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith("|"):
        return True
    if "|---" in stripped or re.match(r"^[\s|:-]+$", stripped) and "|" in stripped:
        return True
    return stripped.count("|") >= 2


def _strip_tabular_markdown(answer: str) -> str:
    """Remove markdown table blocks from an answer; keep narrative prose."""
    lines: list[str] = []
    for line in answer.splitlines():
        stripped = line.strip()
        if not stripped:
            if lines and lines[-1] != "":
                lines.append("")
            continue
        if _is_markdown_table_line(stripped):
            continue
        if re.search(r"\bsorted by\b", stripped, re.I):
            continue
        lines.append(line.rstrip())
    text = "\n".join(lines).strip()
    return re.sub(r"\n{3,}", "\n\n", text)


def _answer_to_html(answer: str) -> str:
    """Minimal markdown-ish to HTML for export pages."""
    lines = answer.splitlines()
    parts: list[str] = []
    in_ul = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("- "):
            if not in_ul:
                parts.append("<ul>")
                in_ul = True
            parts.append(f"<li>{_esc(stripped[2:])}</li>")
        else:
            if in_ul:
                parts.append("</ul>")
                in_ul = False
            if stripped.startswith("**") and stripped.endswith("**"):
                parts.append(f"<p><strong>{_esc(stripped[2:-2])}</strong></p>")
            elif stripped:
                parts.append(f"<p>{_esc(stripped)}</p>")
    if in_ul:
        parts.append("</ul>")
    return "\n".join(parts) if parts else f"<p>{_esc(answer)}</p>"


def _table_html(columns: list[str], rows: list[list[Any]]) -> str:
    if not columns or not rows:
        return ""
    head = "".join(f"<th>{_esc(c)}</th>" for c in columns)
    body_rows = []
    for row in rows[:500]:
        cells = "".join(f"<td>{_esc(row[i] if i < len(row) else '')}</td>" for i in range(len(columns)))
        body_rows.append(f"<tr>{cells}</tr>")
    return f"""
    <section class="data-table">
      <h2>Data</h2>
      <div class="table-wrap"><table>
        <thead><tr>{head}</tr></thead>
        <tbody>{"".join(body_rows)}</tbody>
      </table></div>
    </section>
    """


def build_csv(
    *,
    question: str,
    answer: str,
    columns: list[str] | None,
    rows: list[list[Any]] | None,
) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    if columns and rows:
        writer.writerow(columns)
        for row in rows:
            writer.writerow(row)
        return buf.getvalue()
    writer.writerow(["question", "answer"])
    writer.writerow([question, answer])
    return buf.getvalue()


def _chart_embed_html(
    *,
    question: str,
    answer: str,
    columns: list[str],
    rows: list[list[Any]],
) -> tuple[str, str] | None:
    """Return (chart section HTML, chart script tags) or None if chart cannot be built."""
    numeric_idxs = _numeric_columns(columns, rows)
    numeric_set = set(numeric_idxs)
    label_idx = _pick_label_column(columns, numeric_set)
    value_idx = _pick_value_column(columns, numeric_idxs)

    labels: list[str] = []
    values: list[float] = []
    for row in rows[:50]:
        label = str(row[label_idx]) if label_idx < len(row) else ""
        raw = row[value_idx] if value_idx < len(row) else 0
        try:
            val = float(raw)
        except (TypeError, ValueError):
            continue
        labels.append(label)
        values.append(val)

    if not values:
        return None

    chart_title = _build_chart_title(
        question=question,
        columns=columns,
        label_idx=label_idx,
        value_idx=value_idx,
        row_count=len(values),
    )
    chart_summary = _build_chart_summary(
        answer=answer,
        columns=columns,
        labels=labels,
        values=values,
        label_idx=label_idx,
        value_idx=value_idx,
    )
    dataset_label = _humanize_column(columns[value_idx])
    chart_type = "bar" if len(labels) <= 12 else "line"
    config = {
        "type": chart_type,
        "data": {
            "labels": labels,
            "datasets": [
                {
                    "label": dataset_label,
                    "data": values,
                    "backgroundColor": "rgba(37, 99, 235, 0.65)",
                    "borderColor": "rgb(37, 99, 235)",
                    "borderWidth": 1,
                }
            ],
        },
        "options": {
            "responsive": True,
            "plugins": {
                "title": {"display": False},
                "legend": {"display": False},
            },
            "scales": {"y": {"beginAtZero": True}},
        },
    }
    section = f"""
    <section class="chart-section">
      <h2>{_esc(chart_title)}</h2>
      <p class="chart-summary">{_esc(chart_summary)}</p>
      <div class="chart-box"><canvas id="report-chart"></canvas></div>
    </section>
    """
    script = f"""
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
  <script>
    const reportChartConfig = {json.dumps(config)};
    new Chart(document.getElementById('report-chart'), reportChartConfig);
  </script>
"""
    return section, script


def build_html_page(
    *,
    question: str,
    answer: str,
    columns: list[str] | None = None,
    rows: list[list[Any]] | None = None,
    sql: str | None = None,
    domain_name: str | None = None,
    include_chart: bool = False,
) -> str:
    meta = []
    if domain_name:
        meta.append(f"<span>Domain: {_esc(domain_name)}</span>")
    if sql:
        meta.append(f"<span>SQL query included below</span>")
    meta_html = " · ".join(meta)
    sql_block = (
        f'<section class="sql"><h2>SQL</h2><pre>{_esc(sql)}</pre></section>' if sql else ""
    )
    chart_section = ""
    chart_script = ""
    if include_chart and columns and rows:
        chart_embed = _chart_embed_html(
            question=question,
            answer=answer,
            columns=columns,
            rows=rows,
        )
        if chart_embed:
            chart_section, chart_script = chart_embed
    display_answer = _strip_tabular_markdown(answer) if columns and rows else answer
    answer_section = ""
    if display_answer:
        answer_section = f"""
    <section class="answer">
      <h2>Answer</h2>
      {_answer_to_html(display_answer)}
    </section>"""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{_esc(question[:80])}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 0; background: #f8fafc; color: #0f172a; }}
    .wrap {{ max-width: 900px; margin: 0 auto; padding: 2rem 1.5rem; }}
    h1 {{ font-size: 1.35rem; margin: 0 0 0.5rem; }}
    .meta {{ color: #64748b; font-size: 0.875rem; margin-bottom: 1.5rem; }}
    .answer {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 1.25rem; line-height: 1.6; }}
    section {{ margin-top: 1.5rem; }}
    h2 {{ font-size: 1rem; margin: 0 0 0.75rem; }}
    pre {{ background: #1e293b; color: #e2e8f0; padding: 1rem; border-radius: 8px; overflow: auto; font-size: 0.8rem; }}
    .table-wrap {{ overflow: auto; border: 1px solid #e2e8f0; border-radius: 8px; background: #fff; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 0.875rem; }}
    th, td {{ border-bottom: 1px solid #e2e8f0; padding: 0.5rem 0.75rem; text-align: left; }}
    th {{ background: #f1f5f9; }}
    .chart-summary {{ color: #64748b; font-size: 0.875rem; margin: 0 0 1rem; line-height: 1.5; }}
    .chart-box {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 1.25rem; }}
    .chart-box canvas {{ max-height: 420px; }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>{_esc(question)}</h1>
    <p class="meta">{meta_html}</p>
    {answer_section}
    {_table_html(columns or [], rows or [])}
    {chart_section}
    {sql_block}
  </div>
  {chart_script}
</body>
</html>"""


def _numeric_columns(columns: list[str], rows: list[list[Any]]) -> list[int]:
    indices: list[int] = []
    for i, col in enumerate(columns):
        for row in rows[:20]:
            if i >= len(row):
                continue
            val = row[i]
            if val is None or val == "":
                continue
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                indices.append(i)
                break
            if isinstance(val, str):
                cleaned = val.strip().replace(",", "").replace("$", "").replace(" ", "")
                if re.match(r"^-?\d+(\.\d+)?$", cleaned):
                    indices.append(i)
                    break
    return indices


def _humanize_column(name: str, *, plural: bool = False) -> str:
    """Turn snake_case column ids into readable labels."""
    text = re.sub(r"_+", " ", str(name).strip()).strip()
    if not text:
        return "Values" if plural else "Value"
    label = " ".join(word.capitalize() if word.islower() else word for word in text.split())
    if label.endswith(" Name"):
        base = label[:-5]
        return f"{base}s" if plural else base
    if plural and not label.endswith("s"):
        return f"{label}s"
    return label


def _strip_markdown_for_summary(answer: str) -> str:
    """Remove tables, headings, and markdown noise; keep prose sentences."""
    lines: list[str] = []
    for line in answer.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("|") or "|---" in stripped or stripped.count("|") >= 2:
            continue
        if stripped.startswith("#"):
            stripped = re.sub(r"^#+\s*", "", stripped)
        stripped = re.sub(r"\*\*([^*]+)\*\*", r"\1", stripped)
        stripped = re.sub(r"\*([^*]+)\*", r"\1", stripped)
        stripped = stripped.strip("*_ ")
        if stripped.startswith("(") and stripped.endswith(")"):
            continue
        if re.search(r"\bsorted by\b", stripped, re.I):
            continue
        if stripped and not stripped.startswith("---"):
            lines.append(stripped)
    text = " ".join(lines)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _format_number(value: float, *, currency: bool = False) -> str:
    if currency or abs(value) >= 1_000_000:
        return f"${value:,.2f}"
    if abs(value) >= 1_000:
        return f"{value:,.2f}"
    if float(value).is_integer():
        return f"{int(value):,}"
    return f"{value:,.2f}"


def _question_context_phrase(question: str) -> str:
    """Short filter phrase extracted from the question (e.g. 'from Japan')."""
    q = question.lower()
    phrases: list[str] = []
    country_match = re.search(
        r"\b(from|in)\s+([a-z][a-z\s]{1,30}?)(?:\s+who|\s+that|\s+which|\?|$)",
        q,
    )
    if country_match:
        place = country_match.group(2).strip().title()
        if len(place.split()) <= 3:
            phrases.append(f"from {place}")
    if re.search(r"\bby country\b", q):
        phrases.append("by country")
    if re.search(r"\bby region\b", q):
        phrases.append("by region")
    if re.search(r"\bper month\b", q):
        phrases.append("by month")
    if re.search(r"\bper year\b", q):
        phrases.append("by year")
    return " ".join(phrases[:2])


def _build_chart_title(
    *,
    question: str,
    columns: list[str],
    label_idx: int,
    value_idx: int,
    row_count: int,
) -> str:
    label_h = _humanize_column(columns[label_idx], plural=True)
    value_h = _humanize_column(columns[value_idx])
    context = _question_context_phrase(question)

    q = question.lower()
    if re.search(r"\b(list|top|some|leading|highest|best)\b", q):
        prefix = "Top" if row_count <= 15 else "Leading"
        title = f"{prefix} {label_h} by {value_h}"
    elif re.search(r"\b(trend|over time|by month|by year)\b", q):
        title = f"{value_h} over time"
    elif re.search(r"\b(breakdown|distribution|compare|comparison)\b", q):
        title = f"{value_h} breakdown by {label_h}"
    else:
        title = f"{value_h} by {label_h}"

    if context:
        title = f"{title} {context}"
    return title[:100]


def _build_chart_summary(
    *,
    answer: str,
    columns: list[str],
    labels: list[str],
    values: list[float],
    label_idx: int,
    value_idx: int,
) -> str:
    """One or two readable sentences for context above the chart."""
    label_h = _humanize_column(columns[label_idx]).lower()
    value_h = _humanize_column(columns[value_idx]).lower()
    currency = bool(re.search(r"(revenue|amount|price|cost|profit|sales|usd)", columns[value_idx], re.I))
    n = len(values)

    if n == 0:
        cleaned = _strip_markdown_for_summary(answer)
        return cleaned or "No chartable values were found in this result."

    sorted_pairs = sorted(zip(values, labels), reverse=True)
    top_val, top_label = sorted_pairs[0]
    bottom_val = sorted_pairs[-1][0]

    count_word = f"{n} {'entry' if n == 1 else 'entries'}"
    if "customer" in label_h or "name" in label_h:
        count_word = f"{n} {'customer' if n == 1 else 'customers'}"
    elif "country" in label_h:
        count_word = f"{n} {'country' if n == 1 else 'countries'}"
    elif "product" in label_h:
        count_word = f"{n} {'product' if n == 1 else 'products'}"

    summary = (
        f"The chart compares {count_word} ranked by {value_h}. "
        f"{top_label} leads at {_format_number(top_val, currency=currency)}"
    )
    if n > 1 and bottom_val != top_val:
        summary += f", ranging down to {_format_number(bottom_val, currency=currency)}"
    summary += "."

    cleaned = _strip_markdown_for_summary(answer)
    if (
        cleaned
        and len(cleaned) <= 140
        and "|" not in cleaned
        and not re.search(r"\b(rank|sorted|table|column|provided data)\b", cleaned, re.I)
    ):
        first_sentence = re.split(r"(?<=[.!?])\s+", cleaned)[0]
        if first_sentence and len(first_sentence) > 20:
            summary = f"{first_sentence} {summary}"

    return summary


def _pick_value_column(columns: list[str], numeric_idxs: list[int]) -> int:
    """Prefer metric columns (revenue, amount, count) over numeric ids."""
    if not numeric_idxs:
        return min(1, len(columns) - 1)
    metric = re.compile(
        r"(revenue|amount|total|sum|count|quantity|qty|value|sales|price|cost|profit|score)",
        re.I,
    )
    id_col = re.compile(r"(^|_)id$|_id$", re.I)
    best = numeric_idxs[0]
    best_score = -999
    for i in numeric_idxs:
        col = columns[i]
        score = 0
        if metric.search(col):
            score += 5
        if id_col.search(col):
            score -= 4
        if col.lower() in ("rank", "row", "index"):
            score -= 3
        if score > best_score:
            best_score = score
            best = i
    return best


def _pick_label_column(columns: list[str], numeric_idxs: set[int]) -> int:
    """Prefer human-readable name columns over raw ids for chart labels."""
    readable = re.compile(
        r"(name|customer|country|product|category|region|department|title|label)",
        re.I,
    )
    non_id = re.compile(r"(^|_)id$|_id$", re.I)
    candidates: list[tuple[int, int]] = []
    for i, col in enumerate(columns):
        if i in numeric_idxs:
            continue
        score = 0
        if readable.search(col):
            score += 3
        if non_id.search(col):
            score -= 2
        if col.lower() in ("email", "phone", "uuid"):
            score -= 3
        candidates.append((score, i))
    if candidates:
        candidates.sort(key=lambda x: (-x[0], x[1]))
        if candidates[0][0] > 0:
            return candidates[0][1]
    for i, _col in enumerate(columns):
        if i not in numeric_idxs:
            return i
    return 0


def build_chart_page(
    *,
    question: str,
    answer: str,
    columns: list[str] | None = None,
    rows: list[list[Any]] | None = None,
) -> str:
    if not columns or not rows:
        return build_html_page(
            question=question,
            answer=answer + "\n\n(No tabular data available for a chart. Try a SQL/analytics question.)",
            columns=columns,
            rows=rows,
        )

    numeric_idxs = _numeric_columns(columns, rows)
    numeric_set = set(numeric_idxs)
    label_idx = _pick_label_column(columns, numeric_set)
    value_idx = _pick_value_column(columns, numeric_idxs)

    labels: list[str] = []
    values: list[float] = []
    for row in rows[:50]:
        label = str(row[label_idx]) if label_idx < len(row) else ""
        raw = row[value_idx] if value_idx < len(row) else 0
        try:
            val = float(raw)
        except (TypeError, ValueError):
            continue
        labels.append(label)
        values.append(val)

    if not values:
        return build_html_page(
            question=question,
            answer=answer + "\n\n(Could not derive numeric values for a chart from this result.)",
            columns=columns,
            rows=rows,
        )

    chart_title = _build_chart_title(
        question=question,
        columns=columns,
        label_idx=label_idx,
        value_idx=value_idx,
        row_count=len(values),
    )
    chart_summary = _build_chart_summary(
        answer=answer,
        columns=columns,
        labels=labels,
        values=values,
        label_idx=label_idx,
        value_idx=value_idx,
    )
    dataset_label = _humanize_column(columns[value_idx])

    chart_type = "bar" if len(labels) <= 12 else "line"
    config = {
        "type": chart_type,
        "data": {
            "labels": labels,
            "datasets": [
                {
                    "label": dataset_label,
                    "data": values,
                    "backgroundColor": "rgba(37, 99, 235, 0.65)",
                    "borderColor": "rgb(37, 99, 235)",
                    "borderWidth": 1,
                }
            ],
        },
        "options": {
            "responsive": True,
            "plugins": {
                "title": {"display": False},
                "legend": {"display": False},
            },
            "scales": {"y": {"beginAtZero": True}},
        },
    }

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{_esc(chart_title)}</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 0; background: #0f172a; color: #f8fafc; }}
    .wrap {{ max-width: 960px; margin: 0 auto; padding: 2rem 1.25rem; }}
    h1 {{ font-size: 1.2rem; font-weight: 600; margin: 0 0 0.5rem; line-height: 1.35; }}
    .summary {{ color: #94a3b8; font-size: 0.9rem; margin-bottom: 1.5rem; max-width: 65ch; line-height: 1.55; }}
    .chart-box {{ background: #fff; border-radius: 16px; padding: 1.5rem; }}
    canvas {{ max-height: 420px; }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>{_esc(chart_title)}</h1>
    <p class="summary">{_esc(chart_summary)}</p>
    <div class="chart-box">
      <canvas id="chart"></canvas>
    </div>
  </div>
  <script>
    const config = {json.dumps(config)};
    new Chart(document.getElementById('chart'), config);
  </script>
</body>
</html>"""
