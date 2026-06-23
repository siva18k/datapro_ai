"""Dataset definition drafting helpers — grounded in catalog metadata."""

from __future__ import annotations

import re
from typing import Any

from catalog_db import get_source, list_columns_by_source, list_table_metadata
from relationship_inference import (
    RELATIONSHIPS_END,
    RELATIONSHIPS_START,
    build_relationships_section,
    merge_relationships_into_definition,
    strip_relationships_section,
)

_ROLE_LABELS = {
    "fact": "fact / dimension",
    "lookup": "lookup",
    "excluded": "excluded",
}


def strip_markdown_fences(text: str) -> str:
    """Remove ``` / ```markdown wrappers from LLM output."""
    text = (text or "").strip()
    pattern = re.compile(r"^```(?:markdown|md)?\s*\n(.*?)\n```\s*", re.DOTALL | re.IGNORECASE)
    match = pattern.match(text)
    if match:
        return (match.group(1).strip() + text[match.end() :]).strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def _catalog_tables_summary(source_id: str) -> tuple[list[dict[str, Any]], str]:
    columns_by_table = list_columns_by_source(source_id)
    tables: list[dict[str, Any]] = []
    for table in list_table_metadata(source_id):
        if not table.get("enabled", True):
            continue
        if (table.get("table_role") or "fact") == "excluded":
            continue
        tables.append({**table, "columns": columns_by_table.get(table["id"], [])})
    tables.sort(key=lambda t: (t["table_schema"], t["table_name"]))

    lines: list[str] = []
    for table in tables:
        role = table.get("table_role") or "fact"
        cols = [c["column_name"] for c in table.get("columns") or []]
        col_text = ", ".join(f"`{c}`" for c in cols) if cols else "(no columns cataloged)"
        lines.append(
            f"- `{table['table_schema']}.{table['table_name']}` ({_ROLE_LABELS.get(role, role)}): {col_text}"
        )
    return tables, "\n".join(lines) if lines else "(no tables cataloged yet)"


def build_definition_draft_prompt(source: dict[str, Any], *, catalog_summary: str) -> str:
    domain_name = source.get("domain_name") or ""
    connector = source.get("connector") or ""
    description = (source.get("description") or "").strip()
    desc_line = f"\nShort description: {description}" if description else ""

    return f"""Write a data-catalog definition in plain markdown for dataset "{source.get('name', '')}" \
in domain "{domain_name}" (connector: {connector}).{desc_line}

CRITICAL RULES:
- Return plain markdown only — do NOT wrap in code fences (no ```markdown).
- Do NOT invent tables or columns — use ONLY what appears in the catalog list below.
- If multiple tables are cataloged, describe the full dataset scope, not just the dataset name.
- Sections to include:
  ## What this dataset is
  ## Core tables (bullet per cataloged table with its real columns)
  ## Common analytics patterns (example joins using schema-qualified table names)
  ## Caveats (only factual limits — missing columns, bridge tables, PII if obvious)
- Keep governance/update cadence to at most 2 short bullets or omit.
- Do not duplicate an auto-generated relationships section — that is appended separately.

Cataloged tables and columns (authoritative — nothing else exists):
{catalog_summary}
"""


def prepare_definition_for_llm(definition_md: str) -> str:
    """Normalize stored definition markdown for SQL / Ask prompts."""
    text = strip_markdown_fences(definition_md or "").strip()
    if not text:
        return "(none)"
    text = text.replace(RELATIONSHIPS_START, "").replace(RELATIONSHIPS_END, "").strip()
    return text


def load_definition_for_prompt(source: dict[str, Any]) -> str:
    from catalog_service import load_dataset_definition

    return prepare_definition_for_llm(load_dataset_definition(source))


def finalize_definition_markdown(source_id: str, draft_md: str) -> str:
    """Strip fences, drop stale relationship blocks from draft, append fresh relationships."""
    human = strip_markdown_fences(strip_relationships_section(draft_md))
    try:
        rel = build_relationships_section(source_id)
        if rel["table_count"] >= 2:
            return merge_relationships_into_definition(human, rel["markdown_section"])
    except ValueError:
        pass
    return human + ("\n" if human else "")


def draft_dataset_definition(source_id: str, *, generate_fn) -> str:
    """Build prompt from catalog, call LLM, return merged definition markdown."""
    source = get_source(source_id=source_id)
    if not source:
        raise ValueError(f"Dataset not found: {source_id}")
    _, catalog_summary = _catalog_tables_summary(source_id)
    prompt = build_definition_draft_prompt(source, catalog_summary=catalog_summary)
    raw = generate_fn(prompt)
    return finalize_definition_markdown(source_id, raw)
