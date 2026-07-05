"""SQL dialect rules by dataset connector — catalog metadata is PostgreSQL; business SQL is Trino."""

from __future__ import annotations

from sql_sanitize import fix_trino_date_literals

DIALECT_POSTGRESQL = "postgresql"
DIALECT_TRINO = "trino"

_CONNECTOR_DIALECT: dict[str, str] = {
    "postgres": DIALECT_POSTGRESQL,
    "trino": DIALECT_TRINO,
}


def dialect_for_connector(connector: str | None) -> str:
    """Map structured dataset connector to SQL dialect."""
    key = (connector or "trino").strip().lower()
    return _CONNECTOR_DIALECT.get(key, DIALECT_TRINO)


def dialect_for_context(ctx) -> str:
    return dialect_for_connector(getattr(ctx, "connector", None))


def dialect_label(dialect: str) -> str:
    return "PostgreSQL" if dialect == DIALECT_POSTGRESQL else "Trino"


def format_date_literal(iso_date: str, *, dialect: str) -> str:
    """Date literal for WHERE clauses — Trino requires DATE '…'; Postgres accepts both."""
    if dialect == DIALECT_TRINO:
        return f"DATE '{iso_date}'"
    return f"'{iso_date}'"


def date_range_filter(start_iso: str, end_exclusive_iso: str, *, dialect: str) -> str:
    start_lit = format_date_literal(start_iso, dialect=dialect)
    end_lit = format_date_literal(end_exclusive_iso, dialect=dialect)
    return f"<date_column> >= {start_lit} AND <date_column> < {end_lit}"


def prepare_sql_for_execution(sql: str, connector: str | None) -> str:
    """Normalize generated SQL for the execution engine."""
    if dialect_for_connector(connector) == DIALECT_TRINO:
        return fix_trino_date_literals(sql)
    return sql


def _shared_generation_rules() -> str:
    return """
- Return ONLY the SQL (no markdown, no explanation).
- Return exactly ONE read-only SELECT (WITH ... SELECT is allowed) — never multiple statements separated by semicolons.
- Read the Dataset definition section first — it documents scope, join paths, hub/bridge tables, and caveats.
- Read **Table business rules** — apply status filters, revenue definitions, exclusions, and metric logic exactly as written per table.
- Use Column reference for exact column names and types — match natural-language time phrases to date columns via names and labels.
- When the user names a calendar year (e.g. 2024), filter the chosen date column to that year; use relative date math only when they ask relatively (e.g. "last year").
- Use ONLY tables listed under Allowed tables — never invent names like customers, orders, or products.
- Follow join paths from the Dataset definition (especially hub and bridge tables) instead of guessing FKs.
- If a dimension is listed as unavailable below, omit it — do not fail; answer with what exists.
- SELECT only — no INSERT, UPDATE, DELETE, DDL.
- Prefer COUNT/SUM/aggregates when the question asks "how many" or totals.
- For overview / "tell me about" questions, SELECT representative columns with LIMIT 25 (or COUNT + sample rows).
- When prior conversation or query results are provided, treat the latest message as a follow-up — keep the same filters, grouping, and grain unless the user clearly changes scope.
""".strip()


def generation_rules(dialect: str) -> str:
    label = dialect_label(dialect)
    lines = [_shared_generation_rules(), f"- Target engine: **{label}** — follow the SQL dialect line in the schema block."]
    if dialect == DIALECT_TRINO:
        lines.extend(
            [
                "- Schema-qualify every table exactly as catalog.schema.table (three-part Trino names).",
                "- For DATE/TIMESTAMP comparisons use DATE 'YYYY-MM-DD' or TIMESTAMP 'YYYY-MM-DD HH:MM:SS' — bare quoted strings cause TYPE_MISMATCH.",
            ]
        )
    else:
        lines.extend(
            [
                "- Schema-qualify tables as schema.table (two-part PostgreSQL names).",
                "- PostgreSQL accepts ISO date strings in quotes; cast explicitly when types are ambiguous (::date).",
            ]
        )
    return "\n".join(lines)


def repair_rules(dialect: str) -> str:
    label = dialect_label(dialect)
    lines = [
        "- Return ONLY the corrected SELECT (no markdown, no explanation).",
        "- Return exactly ONE read-only SELECT — no semicolon-separated batches, no DDL, no prose after the query.",
        f"- Target engine: **{label}**.",
        "- Read the Dataset definition for correct join paths — use bridge/hub tables as documented.",
        "- Read **Table business rules** — preserve status filters and metric exclusions from the catalog.",
        "- Remove or replace missing tables/columns — skip dimensions that caused the error.",
        "- Use ONLY tables from Allowed tables — map business terms to real catalog names.",
        "- Use Column reference for exact column names — do not invent columns.",
        "- Schema-qualify every table exactly as in the catalog.",
        "- SELECT only. Prefer a partial answer over failing.",
    ]
    if dialect == DIALECT_TRINO:
        lines.append(
            "- For DATE/TIMESTAMP comparisons use DATE 'YYYY-MM-DD' typed literals, not bare strings."
        )
    return "\n".join(lines)


def partial_generation_rules(dialect: str) -> str:
    label = dialect_label(dialect)
    return f"""
- Return exactly ONE SELECT — no semicolon-separated batches.
- Target engine: **{label}**.
- Read the Dataset definition for join paths and caveats before simplifying.
- Read **Table business rules** — keep documented status filters and revenue rules when simplifying.
- Skip any dimension that is missing or caused errors (department, unknown tables, etc.).
- Use ONLY allowed catalog tables and Column reference column names.
- Return ONLY the SQL (no markdown).
""".strip()
