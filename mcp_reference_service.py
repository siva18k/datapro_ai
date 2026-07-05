"""MCP reference resources: catalog schema, domain calendar/glossary, citation policy."""

from __future__ import annotations

from catalog_db import get_domain_reference_doc, list_sources
from structured_orchestrator import build_domain_schema_context

# URIs always loaded by the host when bound (application-controlled context).
REFERENCE_RESOURCE_URIS: dict[str, str] = {
    "schema": "ragpro://domains/{domain}/schema",
    "calendar": "ragpro://domains/{domain}/calendar",
    "glossary": "ragpro://domains/{domain}/glossary",
    "sql_notes": "ragpro://domains/{domain}/sql-notes",
    "citation_rules": "ragpro://policy/citation-rules",
}

DEFAULT_REFERENCE_DOCS: dict[str, dict[str, str]] = {
    "general": {
        "calendar": (
            "# General calendar\n\n"
            "- Use calendar-year quarters (Jan–Mar = Q1) unless a dataset definition says otherwise.\n"
            "- Call `resolve_time_period` for exact SQL date filters.\n"
        ),
        "glossary": (
            "# General glossary\n\n"
            "- Use catalog schema column names exactly as documented.\n"
        ),
    },
}


def expand_domain_uri(uri: str, domain_slug: str | None) -> str:
    if domain_slug and "{domain}" in uri:
        return uri.replace("{domain}", domain_slug)
    return uri


def is_reference_resource_uri(uri: str) -> bool:
    if uri == "ragpro://policy/citation-rules":
        return True
    if not uri.startswith("ragpro://domains/"):
        return False
    return uri.endswith(("/schema", "/calendar", "/glossary", "/sql-notes"))


def reference_uris_for_execution(execution_kind: str) -> tuple[str, ...]:
    """Which reference URIs to auto-attach for this execution path."""
    if execution_kind in ("sql", "hybrid"):
        return ("schema", "calendar", "glossary", "sql_notes")
    if execution_kind == "rag":
        return ("glossary", "citation_rules")
    return ("glossary",)


def build_domain_schema_markdown(domain_id: str) -> str:
    """Catalog schema for SQL — tables, columns, definitions (read-only reference)."""
    structured_sources = [
        s
        for s in list_sources(domain_id=domain_id, source_type="structured", enabled_only=True)
        if s.get("connector") in ("trino", "postgres")
    ]
    if not structured_sources:
        return (
            "# Catalog schema\n\n"
            "No structured Postgres datasets are cataloged in this domain. "
            "Add datasets on the Data tab or use document RAG instead."
        )
    ctx = build_domain_schema_context(domain_id, structured_sources[0]["id"])
    return ctx.to_llm_prompt_block()


def build_domain_calendar_markdown(domain_id: str, *, domain_slug: str | None = None) -> str:
    doc = get_domain_reference_doc(domain_id, "calendar")
    if doc and doc.get("content", "").strip():
        return doc["content"].strip()
    defaults = DEFAULT_REFERENCE_DOCS.get(domain_slug or "", {})
    return defaults.get("calendar", "# Calendar\n\nNo fiscal calendar documented for this domain.")


def build_domain_glossary_markdown(domain_id: str, *, domain_slug: str | None = None) -> str:
    doc = get_domain_reference_doc(domain_id, "glossary")
    if doc and doc.get("content", "").strip():
        return doc["content"].strip()
    defaults = DEFAULT_REFERENCE_DOCS.get(domain_slug or "", {})
    return defaults.get("glossary", "# Glossary\n\nNo domain glossary documented yet.")


def build_domain_sql_notes_markdown(domain_id: str) -> str:
    doc = get_domain_reference_doc(domain_id, "sql_notes")
    if doc and doc.get("content", "").strip():
        return doc["content"].strip()
    return (
        "# SQL conventions\n\n"
        "- READ-ONLY SELECT only; schema-qualify every table.\n"
        "- Use exact column names from the schema resource.\n"
        "- Follow dataset definition join paths and table business rules.\n"
    )


def read_reference_resource_content(uri: str, *, domain_id: str | None, domain_slug: str | None) -> str:
    """Resolve a reference URI to markdown/text content."""
    if uri == "ragpro://policy/citation-rules":
        from mcp_registry import get_prompt_meta, load_registry

        return get_prompt_meta("citation_rules", load_registry())["template"]

    if not domain_id:
        raise ValueError("Domain context required for domain reference resources")

    if uri.endswith("/schema"):
        return build_domain_schema_markdown(domain_id)
    if uri.endswith("/calendar"):
        return build_domain_calendar_markdown(domain_id, domain_slug=domain_slug)
    if uri.endswith("/glossary"):
        return build_domain_glossary_markdown(domain_id, domain_slug=domain_slug)
    if uri.endswith("/sql-notes"):
        return build_domain_sql_notes_markdown(domain_id)

    raise ValueError(f"Unknown reference resource: {uri}")


def gather_domain_reference_texts(domain_id: str, *, domain_slug: str | None = None) -> dict[str, str]:
    """Load all reference markdown blocks for a domain (used by agents / prompts)."""
    return {
        "schema": build_domain_schema_markdown(domain_id),
        "calendar": build_domain_calendar_markdown(domain_id, domain_slug=domain_slug),
        "glossary": build_domain_glossary_markdown(domain_id, domain_slug=domain_slug),
        "sql_notes": build_domain_sql_notes_markdown(domain_id),
    }


def build_domain_sql_context_prompt(
    question: str,
    *,
    domain_name: str,
    schema_text: str,
    calendar_text: str,
    glossary_text: str,
    sql_notes_text: str,
    tool_context: str = "",
) -> str:
    """Assemble a domain SQL context prompt from reference resources."""
    from mcp_registry import get_prompt_meta, load_registry

    template = get_prompt_meta("domain_sql_context", load_registry())["template"]
    return template.format(
        domain_name=domain_name,
        question=question.strip(),
        schema=schema_text.strip(),
        calendar=calendar_text.strip(),
        glossary=glossary_text.strip(),
        sql_notes=sql_notes_text.strip(),
        tool_context=tool_context.strip() or "(none)",
    )
