"""Plan and execute MCP tools, resources, and prompts for configurable agents."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from api.llm import generate_answer
from catalog_db import get_domain, get_mcp_server
from mcp_ask_planner import (
    McpToolResult,
    _format_structured_tool_result,
    _normalize_tool_arguments,
    _parse_json_object,
    _try_parse_tool_result,
    execute_mcp_enrichment,
    plan_mcp_enrichment,
)
from mcp_tool_contracts import MCP_TOOL_GUIDE
from mcp_client import (
    call_tool_text,
    check_mcp_server,
    get_default_mcp_url,
    get_prompt_preview,
    read_resource_preview,
)
from mcp_domain_service import domain_mcp_capabilities
from mcp_reference_service import (
    expand_domain_uri,
    gather_domain_reference_texts,
    is_reference_resource_uri,
    read_reference_resource_content,
)

# Write / side-effect tools are not invoked during agent runs unless explicitly needed later.
BLOCKED_AGENT_MCP_TOOLS = frozenset({"ingest_documents", "send_email", "sync_dataset"})

_GROUNDED_PROMPTS = frozenset({"grounded_answer", "domain_grounded_answer"})


@dataclass
class AgentMcpEnrichment:
    reasoning: str = ""
    tool_results: list[McpToolResult] = field(default_factory=list)
    resources: list[dict[str, Any]] = field(default_factory=list)
    prompt_results: list[dict[str, Any]] = field(default_factory=list)
    trace: list[dict[str, Any]] = field(default_factory=list)


def enrich_agent_tool_bindings(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach server_url and drop bindings whose server is missing or disabled."""
    enriched: list[dict[str, Any]] = []
    for tool in tools:
        server_id = tool.get("mcp_server_id")
        tool_name = (tool.get("tool_name") or "").strip()
        if not server_id or not tool_name:
            continue
        server = get_mcp_server(server_id=server_id)
        if not server or not server.get("enabled", True):
            continue
        url = (server.get("url") or "").strip()
        if not url:
            continue
        enriched.append(
            {
                **tool,
                "server_url": url,
                "server_enabled": server.get("enabled", True),
            }
        )
    return enriched


def _summarize_agent_tool_catalog(tools: list[dict[str, Any]]) -> str:
    if not tools:
        return "No MCP tools are bound to this agent."
    lines = ["### Agent-bound tools"]
    for tool in tools:
        name = tool.get("tool_name", "")
        server = tool.get("server_slug") or tool.get("server_name") or "server"
        lines.append(f"- `{name}` on {server} (server_id={tool.get('mcp_server_id')})")
    return "\n".join(lines)


def _heuristic_agent_tool_plan(
    instructions: str,
    tools: list[dict[str, Any]],
    *,
    domain_slug: str | None,
) -> list[dict[str, Any]]:
    """Pick agent-bound tools and default arguments without an LLM."""
    lower = instructions.lower()
    planned: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def add(tool_name: str, arguments: dict[str, str]) -> None:
        for tool in tools:
            if tool.get("tool_name") != tool_name:
                continue
            key = (str(tool.get("mcp_server_id")), tool_name)
            if key in seen:
                return
            seen.add(key)
            planned.append(
                {
                    "tool_name": tool_name,
                    "mcp_server_id": tool.get("mcp_server_id"),
                    "arguments": arguments,
                }
            )
            return

    query = instructions.strip().splitlines()[0][:500] if instructions.strip() else "overview"
    if domain_slug:
        add("list_domain_sources", {"domain": domain_slug})
        add("search_documents", {"query": query, "top_k": "5", "domain": domain_slug})
    else:
        add("list_domains", {})
        add("search_documents", {"query": query, "top_k": "5"})

    if any(
        word in lower
        for word in ("ingested file", "chunk count", "knowledge base file", "embedded document")
    ):
        add("list_sources", {})
        add("knowledge_base_stats", {})
    elif any(word in lower for word in ("how many chunk", "knowledge base stat")):
        add("knowledge_base_stats", {})

    if any(word in lower for word in ("last year", "quarter", "month", "period", "ytd", "fy")):
        add("resolve_time_period", {"requirement": instructions[:800]})

    return planned


def plan_agent_tool_calls(
    instructions: str,
    tools: list[dict[str, Any]],
    *,
    domain_slug: str | None,
    model: str,
    backend: str,
    base_url: str,
) -> tuple[list[dict[str, Any]], str]:
    """Return (planned agent tool calls, reasoning)."""
    if not tools:
        return [], "No agent-bound MCP tools."

    catalog = _summarize_agent_tool_catalog(tools)
    domain_hint = f"Primary domain slug: /{domain_slug}" if domain_slug else "No domain slug in instructions."

    prompt = f"""You plan MCP tool calls for a DATA Pro workflow agent.

{MCP_TOOL_GUIDE}

{domain_hint}

{catalog}

## Agent instructions
{instructions}

Choose which bound MCP tools to invoke and string arguments for each. Prefer tools that gather catalog, document, or time-period context needed by the instructions. Use list_domain_sources for catalog datasets, sync_dataset to refresh remote datasets before search, and list_sources only for ingested document files. Do NOT invent tools outside the list above.

Return ONLY valid JSON:
{{
  "reasoning": "one short sentence",
  "tools": [
    {{
      "tool_name": "search_documents",
      "mcp_server_id": "uuid-from-catalog",
      "arguments": {{"query": "...", "top_k": "5", "domain": "{domain_slug or ""}"}}
    }}
  ]
}}

Rules:
- Include at most one entry per (mcp_server_id, tool_name) pair
- arguments values must be strings
- omit tools that are not useful for these instructions
- at most 6 tools
"""
    try:
        raw = generate_answer(prompt, model=model, backend=backend, base_url=base_url)
        plan = _parse_json_object(raw)
        if not isinstance(plan, dict):
            raise ValueError("plan is not an object")
        reasoning = str(plan.get("reasoning") or "").strip()
        entries = plan.get("tools") if isinstance(plan.get("tools"), list) else []
        valid_ids = {str(t.get("mcp_server_id")) for t in tools}
        valid_names = {t.get("tool_name") for t in tools}
        planned: list[dict[str, Any]] = []
        for entry in entries[:6]:
            if not isinstance(entry, dict):
                continue
            tool_name = str(entry.get("tool_name") or "").strip()
            server_id = str(entry.get("mcp_server_id") or "").strip()
            if tool_name not in valid_names or server_id not in valid_ids:
                continue
            args = entry.get("arguments") if isinstance(entry.get("arguments"), dict) else {}
            planned.append(
                {
                    "tool_name": tool_name,
                    "mcp_server_id": server_id,
                    "arguments": {str(k): str(v) for k, v in args.items()},
                }
            )
        if planned:
            return planned, reasoning or "LLM MCP tool plan."
    except Exception:
        pass

    planned = _heuristic_agent_tool_plan(instructions, tools, domain_slug=domain_slug)
    return planned, "Heuristic MCP tool plan."


def _tool_binding(
    tools: list[dict[str, Any]],
    *,
    tool_name: str,
    mcp_server_id: str,
) -> dict[str, Any] | None:
    for tool in tools:
        if tool.get("tool_name") == tool_name and str(tool.get("mcp_server_id")) == mcp_server_id:
            return tool
    return None


def execute_agent_tool_plan(
    planned_tools: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    *,
    domain_slug: str | None,
) -> tuple[list[McpToolResult], list[dict[str, Any]]]:
    """Invoke agent-bound MCP tools. Returns (results, trace)."""
    results: list[McpToolResult] = []
    trace: list[dict[str, Any]] = []

    for entry in planned_tools:
        tool_name = str(entry.get("tool_name") or "").strip()
        server_id = str(entry.get("mcp_server_id") or "").strip()
        if not tool_name or tool_name in BLOCKED_AGENT_MCP_TOOLS:
            continue
        binding = _tool_binding(tools, tool_name=tool_name, mcp_server_id=server_id)
        if not binding:
            continue
        url = binding.get("server_url")
        if not url:
            continue
        if not check_mcp_server(url):
            trace.append(
                {
                    "kind": "tool",
                    "tool": tool_name,
                    "server": binding.get("server_slug") or binding.get("server_name"),
                    "status": "unreachable",
                }
            )
            continue

        args = _normalize_tool_arguments(
            tool_name,
            entry.get("arguments") if isinstance(entry.get("arguments"), dict) else {},
            domain_slug=domain_slug,
        )
        if tool_name == "resolve_time_period" and not url:
            url = get_default_mcp_url()

        try:
            raw_text = call_tool_text(url, tool_name, args)
        except Exception as exc:
            raw_text = f"[tool error: {exc}]"

        result = McpToolResult(
            tool=tool_name,
            server=binding.get("server_slug") or binding.get("server_name"),
            mcp_url=url,
            arguments=args,
            raw=(raw_text or "")[:8000],
            structured=_try_parse_tool_result(raw_text or ""),
        )
        results.append(result)
        trace.append(
            {
                "kind": "tool",
                "source": "agent",
                "tool": tool_name,
                "server": result.server,
                "mcp_url": url,
                "arguments": args,
                "parsed": result.structured is not None,
            }
        )

    return results, trace


def execute_agent_domain_mcp(
    instructions: str,
    domain: dict[str, Any],
    *,
    model: str,
    backend: str,
    base_url: str,
) -> AgentMcpEnrichment:
    """Run domain-bound MCP resources/tools/prompts (includes search_documents)."""
    enrichment = AgentMcpEnrichment()
    domain_id = domain.get("id")
    domain_slug = domain.get("slug")
    if not domain_id:
        return enrichment

    plan = plan_mcp_enrichment(
        instructions,
        domain_id=domain_id,
        domain_slug=domain_slug,
        execution_kind="hybrid",
        model=model,
        backend=backend,
        base_url=base_url,
    )
    enrichment.reasoning = str(plan.get("reasoning") or "")

    query = instructions.strip().splitlines()[0][:500] if instructions.strip() else "overview"
    ask_enrichment = execute_mcp_enrichment(
        plan,
        question=query,
        domain_id=domain_id,
        domain_slug=domain_slug,
        top_k=5,
        execution_kind="hybrid",
    )
    enrichment.tool_results.extend(ask_enrichment.tool_results)
    enrichment.resources.extend(ask_enrichment.resources)
    for step in ask_enrichment.trace:
        enrichment.trace.append({**step, "source": "domain", "domain": domain_slug})

    domain_tools = {c["capability_name"]: c for c in domain_mcp_capabilities(domain_id, "tool")}
    if "search_documents" in domain_tools and not any(r.tool == "search_documents" for r in enrichment.tool_results):
        binding = domain_tools["search_documents"]
        url = binding.get("server_url")
        if url and check_mcp_server(url):
            query = instructions.strip().splitlines()[0][:500] if instructions.strip() else "overview"
            args = _normalize_tool_arguments(
                "search_documents",
                {"query": query, "top_k": "5"},
                domain_slug=domain_slug,
            )
            try:
                raw_text = call_tool_text(url, "search_documents", args)
            except Exception as exc:
                raw_text = f"[tool error: {exc}]"
            result = McpToolResult(
                tool="search_documents",
                server=binding.get("server_slug") or binding.get("server_name"),
                mcp_url=url,
                arguments=args,
                raw=(raw_text or "")[:8000],
                structured=_try_parse_tool_result(raw_text or ""),
            )
            enrichment.tool_results.append(result)
            enrichment.trace.append(
                {
                    "kind": "tool",
                    "source": "domain",
                    "domain": domain_slug,
                    "tool": "search_documents",
                    "arguments": args,
                    "parsed": result.structured is not None,
                }
            )

    prompt_name = plan.get("mcp_prompt")
    sql_prompts = frozenset({"domain_sql_context"})
    if isinstance(prompt_name, str) and (prompt_name in _GROUNDED_PROMPTS | sql_prompts or prompt_name.startswith("local:")):
        for prompt in domain_mcp_capabilities(domain_id, "prompt"):
            if prompt.get("capability_name") != prompt_name:
                continue
            query = instructions.strip().splitlines()[0][:500] if instructions.strip() else "overview"
            args: dict[str, str] = {"question": query, "top_k": "5"}
            if prompt_name.startswith("local:"):
                from domain_prompt_service import local_prompt_slug, render_domain_local_prompt

                slug = local_prompt_slug(prompt_name)
                try:
                    text = render_domain_local_prompt(
                        domain_id,
                        slug,
                        domain_slug=domain_slug,
                        user_args={"question": query},
                    )
                except Exception as exc:
                    text = f"[prompt error: {exc}]"
                if text and text.strip():
                    enrichment.prompt_results.append(
                        {
                            "name": prompt_name,
                            "domain": domain_slug,
                            "server": "local",
                            "text": text[:12000],
                        }
                    )
                    enrichment.trace.append(
                        {
                            "kind": "prompt",
                            "domain": domain_slug,
                            "prompt": prompt_name,
                            "server": "local",
                        }
                    )
                break
            url = prompt.get("server_url")
            if not url or not check_mcp_server(url):
                continue
            if domain_slug and prompt_name == "domain_grounded_answer":
                args["domain"] = domain_slug
            if prompt_name == "domain_sql_context" and domain_id:
                from catalog_db import get_domain

                domain_row = get_domain(domain_id=domain_id) or {}
                refs = gather_domain_reference_texts(domain_id, domain_slug=domain_slug)
                args["domain"] = domain_slug or ""
                args["domain_name"] = domain_row.get("name") or domain_slug or "Domain"
                args["schema"] = refs["schema"][:8000]
                args["calendar"] = refs["calendar"][:4000]
                args["glossary"] = refs["glossary"][:4000]
                args["sql_notes"] = refs["sql_notes"][:4000]
                tool_lines = []
                for tr in enrichment.tool_results[:4]:
                    tool_lines.append(f"- {tr.tool}: {(tr.raw or '')[:500]}")
                args["tool_context"] = "\n".join(tool_lines) if tool_lines else "(none)"
            try:
                text = get_prompt_preview(url, prompt_name, args)
            except Exception as exc:
                text = f"[prompt error: {exc}]"
            if text and text.strip():
                enrichment.prompt_results.append(
                    {
                        "name": prompt_name,
                        "domain": domain_slug,
                        "server": prompt.get("server_slug") or prompt.get("server_name"),
                        "text": text[:12000],
                    }
                )
                enrichment.trace.append(
                    {
                        "kind": "prompt",
                        "domain": domain_slug,
                        "prompt": prompt_name,
                        "server": prompt.get("server_slug"),
                    }
                )
            break

    return enrichment


def _plan_saved_kit_tools(
    instructions: str,
    tools: list[dict[str, Any]],
    *,
    domain_slug: str | None,
) -> list[dict[str, Any]]:
    query = instructions.strip().splitlines()[0][:500] if instructions.strip() else "overview"
    planned: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for tool in tools:
        name = (tool.get("tool_name") or "").strip()
        server_id = str(tool.get("mcp_server_id") or "")
        if not name or not server_id or name in BLOCKED_AGENT_MCP_TOOLS:
            continue
        key = (server_id, name)
        if key in seen:
            continue
        seen.add(key)
        args: dict[str, str] = {}
        if name == "search_documents":
            args = {"query": query, "top_k": "5"}
        elif name in ("list_domain_sources", "get_rag_profile"):
            if domain_slug:
                args = {"domain": domain_slug}
        elif name == "resolve_time_period":
            args = {"requirement": instructions[:800]}
        elif name == "search_inbox":
            args = {"query": query, "limit": "10"}
        planned.append(
            {
                "tool_name": name,
                "mcp_server_id": server_id,
                "arguments": args,
            }
        )
    return planned[:10]


def _execute_saved_prompt(
    prompt: dict[str, Any],
    *,
    instructions: str,
    domain: dict[str, Any] | None,
    enrichment: AgentMcpEnrichment,
) -> None:
    prompt_name = (prompt.get("prompt_name") or "").strip()
    if not prompt_name:
        return
    domain_id = domain.get("id") if domain else None
    domain_slug = domain.get("slug") if domain else None
    query = instructions.strip().splitlines()[0][:500] if instructions.strip() else "overview"
    args: dict[str, str] = {"question": query, "top_k": "5"}

    if prompt_name.startswith("local:"):
        from domain_prompt_service import local_prompt_slug, render_domain_local_prompt

        if not domain_id:
            return
        slug = local_prompt_slug(prompt_name)
        try:
            text = render_domain_local_prompt(
                domain_id,
                slug,
                domain_slug=domain_slug,
                user_args={"question": query},
            )
        except Exception as exc:
            text = f"[prompt error: {exc}]"
        if text and text.strip():
            enrichment.prompt_results.append(
                {
                    "name": prompt_name,
                    "domain": domain_slug,
                    "server": "local",
                    "text": text[:12000],
                }
            )
            enrichment.trace.append(
                {
                    "kind": "prompt",
                    "source": "kit",
                    "domain": domain_slug,
                    "prompt": prompt_name,
                    "server": "local",
                }
            )
        return

    url = (prompt.get("server_url") or "").strip()
    if not url:
        server = get_mcp_server(server_id=prompt.get("mcp_server_id"))
        url = ((server or {}).get("url") or "").strip()
    if not url or not check_mcp_server(url):
        enrichment.trace.append(
            {
                "kind": "prompt",
                "source": "kit",
                "prompt": prompt_name,
                "status": "unreachable",
            }
        )
        return

    if domain_slug and prompt_name == "domain_grounded_answer":
        args["domain"] = domain_slug
    if prompt_name == "domain_sql_context" and domain_id:
        domain_row = get_domain(domain_id=domain_id) or {}
        refs = gather_domain_reference_texts(domain_id, domain_slug=domain_slug)
        args["domain"] = domain_slug or ""
        args["domain_name"] = domain_row.get("name") or domain_slug or "Domain"
        args["schema"] = refs["schema"][:8000]
        args["calendar"] = refs["calendar"][:4000]
        args["glossary"] = refs["glossary"][:4000]
        args["sql_notes"] = refs["sql_notes"][:4000]
        tool_lines = []
        for tr in enrichment.tool_results[:4]:
            tool_lines.append(f"- {tr.tool}: {(tr.raw or '')[:500]}")
        args["tool_context"] = "\n".join(tool_lines) if tool_lines else "(none)"
    try:
        text = get_prompt_preview(url, prompt_name, args)
    except Exception as exc:
        text = f"[prompt error: {exc}]"
    if text and text.strip():
        enrichment.prompt_results.append(
            {
                "name": prompt_name,
                "domain": domain_slug,
                "server": prompt.get("server_slug") or prompt.get("server_name"),
                "text": text[:12000],
            }
        )
        enrichment.trace.append(
            {
                "kind": "prompt",
                "source": "kit",
                "domain": domain_slug,
                "prompt": prompt_name,
                "server": prompt.get("server_slug"),
            }
        )


def execute_saved_agent_kit(
    instructions: str,
    *,
    agent_tools: list[dict[str, Any]],
    agent_prompts: list[dict[str, Any]],
    agent_resources: list[dict[str, Any]],
    resolved_domains: list[dict[str, Any]],
) -> AgentMcpEnrichment:
    """Run the MCP kit persisted on save — no planner LLM."""
    enrichment = AgentMcpEnrichment(reasoning="Using MCP kit saved with this agent.")
    tools = enrich_agent_tool_bindings(agent_tools)
    domains = resolved_domains[:3] or [None]
    primary = resolved_domains[0] if resolved_domains else {}
    primary_slug = primary.get("slug")

    seen_uris: set[str] = set()
    for domain in domains:
        domain_id = domain.get("id") if domain else None
        domain_slug = domain.get("slug") if domain else None
        for item in agent_resources:
            uri_tmpl = (item.get("resource_uri") or "").strip()
            if not uri_tmpl:
                continue
            uri = expand_domain_uri(uri_tmpl, domain_slug)
            if uri in seen_uris:
                continue
            seen_uris.add(uri)
            try:
                if is_reference_resource_uri(uri) or is_reference_resource_uri(uri_tmpl):
                    content = read_reference_resource_content(
                        uri if is_reference_resource_uri(uri) else expand_domain_uri(uri_tmpl, domain_slug),
                        domain_id=domain_id,
                        domain_slug=domain_slug,
                    )
                    kind = "reference"
                    server_label = "datapro"
                else:
                    server = get_mcp_server(server_id=item.get("mcp_server_id"))
                    url = ((server or {}).get("url") or "").strip()
                    if not url or not check_mcp_server(url):
                        enrichment.trace.append(
                            {
                                "kind": "resource",
                                "source": "kit",
                                "uri": uri,
                                "status": "unreachable",
                            }
                        )
                        continue
                    content = read_resource_preview(url, uri)
                    kind = "optional"
                    server_label = (server or {}).get("slug") or (server or {}).get("name")
            except Exception as exc:
                content = f"[resource error: {exc}]"
                kind = "optional"
                server_label = item.get("server_slug")
            enrichment.resources.append(
                {
                    "uri": uri,
                    "content": (content or "")[:8000],
                    "kind": kind,
                    "server": server_label,
                }
            )
            enrichment.trace.append(
                {
                    "kind": "resource",
                    "source": "kit",
                    "resource_kind": kind,
                    "uri": uri,
                    "server": server_label,
                    "domain": domain_slug,
                }
            )

    if tools:
        planned = _plan_saved_kit_tools(instructions, tools, domain_slug=primary_slug)
        tool_results, trace = execute_agent_tool_plan(planned, tools, domain_slug=primary_slug)
        enrichment.tool_results.extend(tool_results)
        enrichment.trace.extend(trace)

    for domain in domains:
        for prompt in agent_prompts[:4]:
            _execute_saved_prompt(
                prompt,
                instructions=instructions,
                domain=domain if isinstance(domain, dict) else None,
                enrichment=enrichment,
            )
            if len(enrichment.prompt_results) >= 3:
                return enrichment

    return enrichment


def run_agent_mcp_enrichment(
    instructions: str,
    *,
    agent_tools: list[dict[str, Any]],
    resolved_domains: list[dict[str, Any]],
    model: str,
    backend: str,
    base_url: str,
    agent_prompts: list[dict[str, Any]] | None = None,
    agent_resources: list[dict[str, Any]] | None = None,
    use_saved_kit: bool = False,
) -> AgentMcpEnrichment:
    """Plan and execute agent-bound and domain-bound MCP capabilities."""
    if use_saved_kit:
        return execute_saved_agent_kit(
            instructions,
            agent_tools=agent_tools,
            agent_prompts=agent_prompts or [],
            agent_resources=agent_resources or [],
            resolved_domains=resolved_domains,
        )

    enrichment = AgentMcpEnrichment()
    tools = enrich_agent_tool_bindings(agent_tools)
    primary_slug = resolved_domains[0].get("slug") if resolved_domains else None

    if tools:
        planned, reasoning = plan_agent_tool_calls(
            instructions,
            tools,
            domain_slug=primary_slug,
            model=model,
            backend=backend,
            base_url=base_url,
        )
        enrichment.reasoning = reasoning
        tool_results, trace = execute_agent_tool_plan(planned, tools, domain_slug=primary_slug)
        enrichment.tool_results.extend(tool_results)
        enrichment.trace.extend(trace)

    for domain in resolved_domains[:3]:
        domain_enrichment = execute_agent_domain_mcp(
            instructions,
            domain,
            model=model,
            backend=backend,
            base_url=base_url,
        )
        if domain_enrichment.reasoning and not enrichment.reasoning:
            enrichment.reasoning = domain_enrichment.reasoning
        enrichment.tool_results.extend(domain_enrichment.tool_results)
        enrichment.resources.extend(domain_enrichment.resources)
        enrichment.prompt_results.extend(domain_enrichment.prompt_results)
        enrichment.trace.extend(domain_enrichment.trace)

    return enrichment


def format_agent_mcp_context(enrichment: AgentMcpEnrichment | None) -> str:
    """Text block appended to agent prompts (plan, KPI, report)."""
    if not enrichment:
        return ""
    if not (
        enrichment.reasoning
        or enrichment.tool_results
        or enrichment.resources
        or enrichment.prompt_results
    ):
        return ""

    parts: list[str] = []
    if enrichment.reasoning:
        parts.append(f"Planner note: {enrichment.reasoning.strip()}")

    if enrichment.resources:
        ref_items = [i for i in enrichment.resources if i.get("kind") == "reference"]
        opt_items = [i for i in enrichment.resources if i.get("kind") != "reference"]
        if ref_items:
            parts.append("## MCP reference resources")
            for item in ref_items[:8]:
                uri = item.get("uri", "")
                content = (item.get("content") or "").strip()
                if len(content) > 3500:
                    content = content[:3500] + "…"
                parts.append(f"### `{uri}`\n{content}")
        if opt_items:
            parts.append("## MCP inventory resources")
            for item in opt_items[:4]:
                uri = item.get("uri", "")
                content = (item.get("content") or "").strip()
                if len(content) > 2500:
                    content = content[:2500] + "…"
                parts.append(f"### `{uri}`\n{content}")

    if enrichment.tool_results:
        parts.append("## MCP tool results")
        for item in enrichment.tool_results[:8]:
            arg_text = ", ".join(f"{k}={v}" for k, v in item.arguments.items()) if item.arguments else ""
            rendered = _format_structured_tool_result(item)
            source = item.server or "mcp"
            parts.append(f"### `{item.tool}` on {source} ({arg_text})\n{rendered}")

    if enrichment.prompt_results:
        parts.append("## MCP prompts")
        for item in enrichment.prompt_results[:2]:
            name = item.get("name", "prompt")
            domain = item.get("domain")
            label = f"{name} (/ {domain})" if domain else name
            text = (item.get("text") or "").strip()
            if len(text) > 4000:
                text = text[:4000] + "…"
            parts.append(f"### `{label}`\n{text}")

    return (
        "## MCP context\n"
        "Data gathered via bound MCP tools, resources, and prompts. Prefer this over reinventing retrieval.\n\n"
        + "\n\n".join(parts)
    )


def mcp_summary_for_report(enrichment: AgentMcpEnrichment | None) -> str | None:
    """Build a narrative summary from MCP-only results when SQL analytics is unavailable."""
    if not enrichment:
        return None
    chunks: list[str] = []
    for item in enrichment.prompt_results:
        text = (item.get("text") or "").strip()
        if text:
            chunks.append(text)
    for item in enrichment.tool_results:
        if item.tool == "search_documents" and item.structured:
            try:
                docs = item.structured if isinstance(item.structured, list) else json.loads(item.raw)
            except (json.JSONDecodeError, TypeError):
                docs = None
            if isinstance(docs, list) and docs:
                lines = []
                for doc in docs[:5]:
                    if isinstance(doc, dict):
                        source = doc.get("source_file") or doc.get("source") or "document"
                        text = doc.get("text") or doc.get("chunk_text") or ""
                        lines.append(f"- {source}: {str(text)[:400]}")
                if lines:
                    chunks.append("Retrieved documents:\n" + "\n".join(lines))
        elif item.raw and not item.raw.startswith("[tool error"):
            rendered = _format_structured_tool_result(item, max_chars=1500)
            if rendered:
                chunks.append(f"**{item.tool}**: {rendered}")
    if not chunks:
        return None
    combined = "\n\n".join(chunks)
    if len(combined) > 6000:
        combined = combined[:6000] + "…"
    return combined
