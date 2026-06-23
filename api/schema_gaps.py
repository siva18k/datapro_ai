"""Detect requested dimensions missing from the catalog — skip and note for the user."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass
class SchemaGapAnalysis:
    notes: list[str]
    skip_instructions: str
    join_hints: str = ""


def _table_names(ctx: Any) -> set[str]:
    return {t["table_name"].lower() for t in ctx.tables}


def _column_names(ctx: Any) -> set[str]:
    cols: set[str] = set()
    for table in ctx.tables:
        for col in table.get("columns") or []:
            cols.add(col["column_name"].lower())
    return cols


def _tables_matching(ctx: Any, *fragments: str) -> list[str]:
    names = _table_names(ctx)
    return [n for n in names if any(f in n for f in fragments)]


def _has_column_link(ctx: Any, table_frags: tuple[str, ...], col_frag: str) -> bool:
    for table in ctx.tables:
        if not any(f in table["table_name"].lower() for f in table_frags):
            continue
        for col in table.get("columns") or []:
            if col_frag in col["column_name"].lower():
                return True
    return False


def note_from_sql_error(error_message: str) -> str | None:
    """Turn a PostgreSQL error into a user-facing skip note."""
    text = str(error_message)
    rel = re.search(r'relation "[^"]+\.([^"]+)" does not exist', text, re.I)
    if rel:
        return f"Table «{rel.group(1)}» is not in the catalog — it was skipped."
    rel = re.search(r'relation "([^"]+)" does not exist', text, re.I)
    if rel:
        return f"Table «{rel.group(1)}» is not in the catalog — it was skipped."
    col = re.search(r'column "[^"]+\.([^"]+)" does not exist', text, re.I)
    if col:
        return f"Column «{col.group(1)}» is not available — it was skipped."
    col = re.search(r'column "([^"]+)" does not exist', text, re.I)
    if col:
        return f"Column «{col.group(1)}» is not available — it was skipped."
    if "does not exist" in text.lower():
        return "Some requested data elements are not in the catalog — they were skipped."
    return None


def analyze_schema_gaps(question: str, ctx: Any) -> SchemaGapAnalysis:
    """Heuristic check: which question dimensions are not satisfiable from catalog metadata."""
    notes: list[str] = []
    q = question.lower()

    if re.search(r"\bcustomers?\b", q):
        if not _tables_matching(ctx, "customer"):
            notes.append("Customer — no customer table in the catalog; customer breakdown was skipped.")

    if re.search(r"\bdepartment", q):
        dept_tables = _tables_matching(ctx, "department")
        revenue_context = _tables_matching(ctx, "sales", "order", "invoice", "payment", "revenue")
        customer_context = _tables_matching(ctx, "customer")
        if not dept_tables:
            notes.append("Department — no department tables in the catalog; department breakdown was skipped.")
        elif (revenue_context or customer_context) and not _has_column_link(
            ctx, ("sales", "order", "invoice", "customer"), "department"
        ):
            notes.append(
                "Department — department data is not linked to sales or customer revenue in the catalog; "
                "department breakdown was skipped."
            )

    if re.search(r"\b(revenue|sales)\b", q):
        if not _tables_matching(ctx, "sales", "order", "invoice", "payment", "revenue"):
            notes.append("Revenue — no sales or revenue tables in the catalog; revenue metrics were skipped.")

    if re.search(r"\b(product|products)\b", q):
        if not _tables_matching(ctx, "product", "inventory"):
            notes.append("Product — no product tables in the catalog; product breakdown was skipped.")

    if re.search(r"\b(employee|employees|headcount|staff)\b", q):
        if not _tables_matching(ctx, "employee", "hr_"):
            notes.append("Employee — no HR/employee tables in the catalog; employee metrics were skipped.")

    if re.search(r"\b(country|countries|japan|region)\b", q):
        has_geo = _tables_matching(ctx, "country", "customer", "address", "reference_countr")
        has_country_col = "country_code" in _column_names(ctx) or any("country" in c for c in _column_names(ctx))
        if not has_geo and not has_country_col:
            notes.append("Geography — no country or region fields in the catalog; location filter was skipped.")

    join_hints = ""
    if re.search(r"\bsegment", q):
        segment_tables = _tables_matching(ctx, "segment")
        bridge_tables = [n for n in _table_names(ctx) if "bridge" in n and "segment" in n]
        if segment_tables and bridge_tables:
            qualified = [
                f"{t['table_schema']}.{t['table_name']}"
                for t in ctx.tables
                if "bridge" in t["table_name"].lower() and "segment" in t["table_name"].lower()
            ]
            if qualified:
                join_hints = (
                    "\n\nJoin hints (from catalog — use bridge tables for segments):\n"
                    + "\n".join(f"- For segment breakdowns, join through `{name}`" for name in qualified)
                )

    skip_instructions = ""
    if notes:
        skip_instructions = (
            "\n\nUnavailable dimensions (do NOT invent tables/columns; omit from SQL):\n"
            + "\n".join(f"- {n}" for n in notes)
            + "\n\nWrite SQL that answers as much as possible using only cataloged data."
        )

    return SchemaGapAnalysis(notes=notes, skip_instructions=skip_instructions, join_hints=join_hints)
