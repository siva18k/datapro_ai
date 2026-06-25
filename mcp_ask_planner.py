"""Plan and execute domain-bound MCP capabilities during Ask / analytics."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

from api.llm import generate_answer
from catalog_db import get_domain
from mcp_client import call_tool_text, check_mcp_server, get_default_mcp_url
from mcp_domain_service import (
    domain_mcp_capabilities,
    read_bound_resources_for_domain,
)
from temporal_context import format_time_period_hints, has_temporal_signal

# Read-only MCP tools safe to invoke during question answering.
ALLOWED_ASK_MCP_TOOLS = frozenset(
    {
        "search_documents",
        "list_domains",
        "list_domain_sources",
        "get_rag_profile",
        "list_sources",
        "get_chunk",
        "knowledge_base_stats",
        "list_available_documents",
        "resolve_time_period",
    }
)

ALLOWED_ASK_MCP_PROMPTS = frozenset(
    {
        "grounded_answer",
        "domain_grounded_answer",
        "citation_rules",
        "summarize_document",
    }
)

# Heuristic planner is instant; LLM planner adds latency and can block Ask on slow models.
_USE_LLM_MCP_PLANNER = os.environ.get("MCP_LLM_PLANNER", "").strip().lower() in (
    "1",
    "true",
    "yes",
)


@dataclass
class McpToolResult:
    """One MCP tool invocation result — raw text plus optional parsed structure."""

    tool: str
    server: str | None
    mcp_url: str | None
    arguments: dict[str, str]
    raw: str
    structured: Any = None  # parsed JSON when tool returns JSON


@dataclass
class McpAskEnrichment:
    reasoning: str = ""
    resources: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[McpToolResult] = field(default_factory=list)
    mcp_prompt_name: str | None = None
    mcp_prompt_text: str | None = None
    trace: list[dict[str, Any]] = field(default_factory=list)


def _load_domain_bindings(domain_id: str) -> dict[str, list[dict[str, Any]]]:
    """Load all MCP bindings for a domain grouped by type. Single DB round-trip per type."""
    return {
        cap_type: domain_mcp_capabilities(domain_id, cap_type)
        for cap_type in ("tool", "resource", "prompt")
    }


def _has_any_bindings(bindings: dict[str, list[dict[str, Any]]]) -> bool:
    return any(caps for caps in bindings.values())


def has_domain_mcp_bindings(domain_id: str | None) -> bool:
    """True when the domain has any bound MCP tools, resources, or prompts."""
    if not domain_id:
        return False
    return _has_any_bindings(_load_domain_bindings(domain_id))


def summarize_domain_mcp_bindings(
    domain_id: str | None,
    bindings: dict[str, list[dict[str, Any]]] | None = None,
) -> str:
    """Compact catalog of bound MCP tools, resources, and prompts for the planner LLM."""
    if not domain_id:
        return "No domain selected — MCP bindings unavailable."
    if bindings is None:
        bindings = _load_domain_bindings(domain_id)
    if not _has_any_bindings(bindings):
        return "No MCP capabilities are bound to this domain."
    lines: list[str] = []
    for cap_type in ("tool", "resource", "prompt"):
        caps = bindings.get(cap_type) or []
        if not caps:
            continue
        lines.append(f"### {cap_type}s")
        for cap in caps:
            name = cap.get("capability_name", "")
            server = cap.get("server_slug") or cap.get("server_name") or "server"
            lines.append(f"- `{name}` on {server}")
    return "\n".join(lines) if lines else "No MCP capabilities are bound to this domain."


def _parse_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    return json.loads(text)


def _try_parse_tool_result(raw: str) -> Any:
    """
    Attempt to parse raw MCP tool output as JSON.
    Returns the parsed value (dict, list, etc.) or None if not valid JSON.
    Handles both direct JSON and JSON wrapped in a single-key object.
    """
    if not raw:
        return None
    text = raw.strip()
    # Strip markdown fences if present
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    try:
        parsed = json.loads(text)
        return parsed
    except (json.JSONDecodeError, ValueError):
        return None


def _format_structured_tool_result(result: McpToolResult, max_chars: int = 2500) -> str:
    """Human-readable rendering of a tool result, preferring structured data over raw text."""
    structured = result.structured

    if isinstance(structured, list):
        # e.g. list_domain_sources → list of source dicts
        items = structured[:20]
        if items and isinstance(items[0], dict):
            lines = []
            for item in items:
                # Prefer name/slug/description fields
                name = item.get("name") or item.get("slug") or item.get("id") or ""
                desc = item.get("description") or item.get("short_description") or ""
                kind = item.get("connector") or item.get("type") or item.get("source_type") or ""
                parts = [name]
                if kind:
                    parts.append(f"({kind})")
                if desc:
                    parts.append(f"— {desc}")
                lines.append(" ".join(p for p in parts if p))
            rendered = "\n".join(lines)
        else:
            rendered = "\n".join(str(i) for i in items)
        if len(structured) > 20:
            rendered += f"\n… and {len(structured) - 20} more"
        return rendered[:max_chars]

    if isinstance(structured, dict):
        if structured.get("periods") is not None and structured.get("filter"):
            return format_time_period_hints(structured).strip()[:max_chars]
        lines = []
        for k, v in structured.items():
            lines.append(f"{k}: {v}")
        return "\n".join(lines)[:max_chars]

    # Fallback to raw text
    raw = (result.raw or "").strip()
    return raw[:max_chars] + ("…" if len(raw) > max_chars else "")


def _heuristic_mcp_plan(
    question: str,
    *,
    domain_id: str | None,
    domain_slug: str | None,
    execution_kind: str,
    bindings: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Fallback when the planner LLM fails or returns invalid JSON.

    Accepts pre-loaded bindings to avoid redundant DB queries.
    """
    tools: list[dict[str, str]] = []
    use_resources = False
    mcp_prompt: str | None = None

    if domain_id:
        if bindings is None:
            bindings = _load_domain_bindings(domain_id)
        bound_tools = {c["capability_name"] for c in bindings.get("tool", [])}
        bound_prompts = {c["capability_name"] for c in bindings.get("prompt", [])}

        lower = question.lower()
        if "list_domain_sources" in bound_tools and domain_slug and any(
            word in lower for word in ("source", "dataset", "table", "catalog")
        ):
            tools.append({"name": "list_domain_sources", "arguments": {"domain": domain_slug}})
        if "knowledge_base_stats" in bound_tools and any(
            word in lower for word in ("how many", "chunk", "document", "ingested")
        ):
            tools.append({"name": "knowledge_base_stats", "arguments": {}})
        # Bound resources can be large — only prefetch when scope/inventory is unclear.
        use_resources = bool(bindings.get("resource")) and any(
            word in lower
            for word in ("what data", "what is cataloged", "which dataset", "what sources", "what domains")
        )

        if execution_kind == "rag":
            if "domain_grounded_answer" in bound_prompts:
                mcp_prompt = "domain_grounded_answer"
            elif "grounded_answer" in bound_prompts:
                mcp_prompt = "grounded_answer"
        elif execution_kind in ("sql", "hybrid") and "list_domain_sources" in bound_tools and domain_slug:
            if not tools:
                tools.append({"name": "list_domain_sources", "arguments": {"domain": domain_slug}})
        if (
            execution_kind in ("sql", "hybrid")
            and has_temporal_signal(question)
            and not any(t.get("name") == "resolve_time_period" for t in tools)
        ):
            tools.append(
                {
                    "name": "resolve_time_period",
                    "arguments": {"requirement": question.strip()},
                }
            )

    return {
        "use_resources": use_resources,
        "mcp_prompt": mcp_prompt,
        "tools": tools,
        "reasoning": "Heuristic MCP plan (planner LLM unavailable or invalid).",
    }


def plan_mcp_enrichment(
    question: str,
    *,
    domain_id: str | None,
    domain_slug: str | None,
    execution_kind: str,
    model: str,
    backend: str = "mistral",
    base_url: str = "http://localhost:11434",
) -> dict[str, Any]:
    """
    Use the LLM to choose bound MCP resources, tools, and prompts for this question.
    Returns a JSON-like dict: use_resources, mcp_prompt, tools[], reasoning.

    Fast path: if no MCP capabilities are bound for the domain, skip the LLM call
    entirely and return a heuristic plan immediately.
    """
    if not domain_id:
        return _heuristic_mcp_plan(
            question,
            domain_id=domain_id,
            domain_slug=domain_slug,
            execution_kind=execution_kind,
        )

    # Load bindings once — reuse for both the binding-check and summary text.
    bindings = _load_domain_bindings(domain_id)
    if not _has_any_bindings(bindings):
        # No bindings at all — skip LLM, nothing to plan.
        return {
            "use_resources": False,
            "mcp_prompt": None,
            "tools": [],
            "reasoning": "No MCP capabilities bound to domain — skipped planner.",
        }

    binding_summary = summarize_domain_mcp_bindings(domain_id, bindings=bindings)

    if not _USE_LLM_MCP_PLANNER:
        return _heuristic_mcp_plan(
            question,
            domain_id=domain_id,
            domain_slug=domain_slug,
            execution_kind=execution_kind,
            bindings=bindings,
        )

    prompt = f"""You route DATA Pro questions to the right context sources.

Execution path already chosen: **{execution_kind}** (sql = live database, rag = documents only, hybrid = SQL + documents).

Domain MCP bindings:
{binding_summary}

User question:
{question}

Decide which bound MCP capabilities would help answer accurately. Prefer:
- **resources** for domain/source/stats URIs when scope or inventory is unclear
- **list_domain_sources** when the question mentions datasets, sources, or what is cataloged
- **get_rag_profile** only when a specific source slug is named in the question
- **domain_grounded_answer** prompt for rag/hybrid document answers when bound
- Do NOT choose ingest or write tools

Return ONLY valid JSON:
{{
  "use_resources": true,
  "mcp_prompt": "domain_grounded_answer",
  "tools": [{{"name": "list_domain_sources", "arguments": {{"domain": "{domain_slug or "finance"}"}}}}],
  "reasoning": "one short sentence"
}}

Rules:
- tools[].name must appear in the bindings list above
- omit tools or set mcp_prompt to null when not needed
- arguments values must be strings
- at most 2 tools
"""
    try:
        raw = generate_answer(prompt, model=model, backend=backend, base_url=base_url)
        plan = _parse_json_object(raw)
        if not isinstance(plan, dict):
            raise ValueError("plan is not an object")
        return plan
    except Exception:
        return _heuristic_mcp_plan(
            question,
            domain_id=domain_id,
            domain_slug=domain_slug,
            execution_kind=execution_kind,
            bindings=bindings,
        )


def _find_bound_capability(
    domain_id: str,
    capability_type: str,
    capability_name: str,
) -> dict[str, Any] | None:
    for cap in domain_mcp_capabilities(domain_id, capability_type):
        if cap.get("capability_name") == capability_name:
            return cap
    return None


def _normalize_tool_arguments(
    tool_name: str,
    arguments: dict[str, Any] | None,
    *,
    domain_slug: str | None,
) -> dict[str, str]:
    out = {str(k): str(v) for k, v in (arguments or {}).items()}
    if tool_name in ("list_domain_sources", "get_rag_profile", "search_documents") and domain_slug:
        out.setdefault("domain", domain_slug)
    if tool_name == "search_documents":
        out.setdefault("top_k", "5")
    return out


def execute_mcp_enrichment(
    plan: dict[str, Any],
    *,
    question: str,
    domain_id: str | None,
    domain_slug: str | None,
    top_k: int = 5,
) -> McpAskEnrichment:
    """Run the planned MCP resources, tools, and prompts (best-effort)."""
    enrichment = McpAskEnrichment(reasoning=str(plan.get("reasoning") or ""))
    if not domain_id:
        return enrichment

    if plan.get("use_resources"):
        for item in read_bound_resources_for_domain(domain_id, domain_slug=domain_slug):
            enrichment.resources.append(item)
            enrichment.trace.append(
                {
                    "kind": "resource",
                    "uri": item.get("uri"),
                    "server": item.get("server"),
                }
            )

    for entry in (plan.get("tools") or [])[:3]:
        if not isinstance(entry, dict):
            continue
        tool_name = str(entry.get("name") or "").strip()
        if tool_name not in ALLOWED_ASK_MCP_TOOLS or tool_name == "search_documents":
            continue
        binding = _find_bound_capability(domain_id, "tool", tool_name)
        url = binding.get("server_url") if binding else None
        server_label = (binding.get("server_slug") or binding.get("server_name")) if binding else None
        if not url and tool_name == "resolve_time_period":
            url = get_default_mcp_url()
            server_label = "datapro"
        if not url or not check_mcp_server(url):
            continue
        args = _normalize_tool_arguments(
            tool_name,
            entry.get("arguments") if isinstance(entry.get("arguments"), dict) else {},
            domain_slug=domain_slug,
        )
        try:
            raw_text = call_tool_text(url, tool_name, args)
        except Exception as exc:
            raw_text = f"[tool error: {exc}]"

        tool_result = McpToolResult(
            tool=tool_name,
            server=server_label,
            mcp_url=url,
            arguments=args,
            raw=(raw_text or "")[:8000],
            structured=_try_parse_tool_result(raw_text or ""),
        )
        enrichment.tool_results.append(tool_result)
        enrichment.trace.append(
            {
                "kind": "tool",
                "tool": tool_name,
                "mcp_url": url,
                "arguments": args,
                "parsed": tool_result.structured is not None,
            }
        )

    # Prompt previews run a full RAG pass on the MCP server and duplicate local Ask RAG.
    # Answer prompts are built locally from retrieved chunks in ask_runner.

    return enrichment


def format_mcp_context_supplement(enrichment: McpAskEnrichment | None) -> str:
    """Text block for SQL/Python generation or RAG answer prompts."""
    if not enrichment:
        return ""
    parts: list[str] = []
    if enrichment.reasoning:
        parts.append(f"Planner note: {enrichment.reasoning.strip()}")

    if enrichment.resources:
        parts.append("## MCP resources (domain bindings)")
        for item in enrichment.resources[:6]:
            uri = item.get("uri", "")
            content = (item.get("content") or "").strip()
            if len(content) > 2500:
                content = content[:2500] + "…"
            parts.append(f"### `{uri}`\n{content}")

    if enrichment.tool_results:
        parts.append("## MCP tool results")
        for item in enrichment.tool_results[:4]:
            tool = item.tool
            arg_text = ", ".join(f"{k}={v}" for k, v in item.arguments.items()) if item.arguments else ""
            rendered = _format_structured_tool_result(item)
            kind_note = " (structured)" if item.structured is not None else " (text)"
            parts.append(f"### `{tool}`{kind_note} ({arg_text})\n{rendered}")

    if not parts:
        return ""
    return (
        "## MCP domain context\n"
        "Supplementary metadata from bound MCP servers. Use with catalog definition and retrieved chunks; "
        "SQL identifiers still come from Allowed tables / Column reference.\n\n"
        + "\n\n".join(parts)
    )


def resolve_domain_slug(domain_id: str | None, routing: dict[str, Any] | None) -> str | None:
    if routing and routing.get("domain_slug"):
        return routing["domain_slug"]
    if not domain_id:
        return None
    domain = get_domain(domain_id=domain_id)
    return domain.get("slug") if domain else None
