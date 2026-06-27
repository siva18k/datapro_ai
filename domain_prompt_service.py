"""Domain-local MCP prompt templates (stored in catalog DB, not mcp_registry.json)."""

from __future__ import annotations

import re

from catalog_db import get_domain, get_domain_prompt
from mcp_reference_service import gather_domain_reference_texts

LOCAL_PROMPT_PREFIX = "local:"

_SAMPLE_QUESTION = "What datasets and tables are in this domain?"
_SAMPLE_CONTEXT = "[travel_policy.md - chunk_00]\nSample retrieved context for preview…"


def is_local_prompt_name(name: str) -> bool:
    return isinstance(name, str) and name.startswith(LOCAL_PROMPT_PREFIX)


def local_prompt_slug(name: str) -> str:
    if not is_local_prompt_name(name):
        return name
    return name[len(LOCAL_PROMPT_PREFIX) :]


def binding_name_for_local(slug: str) -> str:
    return f"{LOCAL_PROMPT_PREFIX}{slug}"


def prompt_template_parameters(template: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for key in re.findall(r"\{(\w+)\}", template):
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


def _citation_rules_text() -> str:
    from mcp_registry import get_prompt_meta, load_registry

    return get_prompt_meta("citation_rules", load_registry())["template"]


def build_local_prompt_context(
    domain_id: str,
    *,
    domain_slug: str | None = None,
    user_args: dict[str, str] | None = None,
) -> dict[str, str]:
    user_args = user_args or {}
    row = get_domain(domain_id=domain_id) or {}
    slug = (domain_slug or row.get("slug") or "").strip()
    domain_name = (row.get("name") or slug or "Domain").strip()
    refs = gather_domain_reference_texts(domain_id, domain_slug=slug or None)
    return {
        "question": user_args.get("question") or _SAMPLE_QUESTION,
        "context": user_args.get("context") or _SAMPLE_CONTEXT,
        "domain": slug,
        "domain_name": domain_name,
        "schema": (user_args.get("schema") or refs.get("schema", ""))[:8000],
        "calendar": (user_args.get("calendar") or refs.get("calendar", ""))[:4000],
        "glossary": (user_args.get("glossary") or refs.get("glossary", ""))[:4000],
        "sql_notes": (user_args.get("sql_notes") or refs.get("sql_notes", ""))[:4000],
        "tool_context": user_args.get("tool_context") or "(none)",
        "citation_rules": user_args.get("citation_rules") or _citation_rules_text(),
    }


def render_domain_prompt_template(
    template: str,
    *,
    domain_id: str,
    domain_slug: str | None = None,
    user_args: dict[str, str] | None = None,
) -> str:
    values = build_local_prompt_context(domain_id, domain_slug=domain_slug, user_args=user_args)
    params = prompt_template_parameters(template)
    fmt_args = {key: values.get(key, "") for key in params}
    try:
        return template.format(**fmt_args)
    except KeyError as exc:
        raise ValueError(f"Missing template variable: {exc.args[0]}") from exc


def render_domain_local_prompt(
    domain_id: str,
    slug: str,
    *,
    domain_slug: str | None = None,
    user_args: dict[str, str] | None = None,
) -> str:
    prompt = get_domain_prompt(domain_id, slug=slug)
    if not prompt:
        raise ValueError(f"Local prompt not found: {slug!r}")
    if not prompt.get("enabled", True):
        raise ValueError(f"Local prompt is disabled: {slug!r}")
    return render_domain_prompt_template(
        prompt["template"],
        domain_id=domain_id,
        domain_slug=domain_slug,
        user_args=user_args,
    )
