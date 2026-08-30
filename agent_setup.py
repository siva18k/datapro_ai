"""Infer agent domains and abilities from instructions — same idea as Ask routing."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from catalog_db import (
    get_agent,
    list_mcp_servers,
    parse_domain_slugs_from_instructions,
    set_agent_mcp_kit,
    update_agent,
)
from catalog_service import resolve_domains
from domain_router import route_question
from mcp_domain_service import domain_mcp_capabilities

# Side-effect tools are saved on the kit but not invoked during MCP enrichment.
_SKIP_SAVE_TOOLS = frozenset({"ingest_documents"})
_EMAIL_TOOL_NAMES = ("send_email", "search_inbox", "mailbox_status")

_KPI_RE = re.compile(r"\b(kpi|pass|fail|threshold|metric|rules?)\b", re.I)
_REPORT_RE = re.compile(
    r"\b(report|html|table|chart|dashboard|list|inventory|summary)\b",
    re.I,
)
_EMAIL_RE = re.compile(r"\b(e-?mail|notify|notification|smtp)\b", re.I)
_GOAL_RE = re.compile(r"##\s*goal\b(.*?)(?=\n##|\Z)", re.I | re.S)


def instructions_goal_text(instructions: str) -> str:
    text = (instructions or "").strip()
    if not text:
        return ""
    match = _GOAL_RE.search(text)
    if match:
        goal = " ".join(match.group(1).split())
        if goal:
            return goal[:800]
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line[:800]
    return text[:800]


def infer_agent_capabilities(instructions: str) -> dict[str, Any]:
    """Guess KPI / report / email from the written goal — no MCP jargon required."""
    text = instructions or ""
    kpi = bool(_KPI_RE.search(text))
    report = bool(_REPORT_RE.search(text))
    email = bool(_EMAIL_RE.search(text))
    if not kpi and not report:
        kpi = True
        report = True
    return {
        "kpi_check": kpi,
        "generate_report": report,
        "send_email": email,
    }


def effective_agent_capabilities(saved: dict[str, Any] | None, instructions: str) -> dict[str, Any]:
    saved = saved or {}
    inferred = infer_agent_capabilities(instructions)
    kpi = bool(saved.get("kpi_check"))
    report = bool(saved.get("generate_report"))
    email = bool(saved.get("send_email"))
    if not kpi and not report:
        kpi = inferred["kpi_check"]
        report = inferred["generate_report"]
    return {
        "kpi_check": kpi,
        "generate_report": report,
        "send_email": email,
        "email_to": (saved.get("email_to") or "").strip(),
    }


def resolve_agent_domains(
    instructions: str,
    embedder=None,
) -> tuple[list[dict], list[str], str]:
    """Slash tokens first; otherwise route the goal like Ask."""
    slugs = parse_domain_slugs_from_instructions(instructions)
    if slugs:
        resolved = resolve_domains(slugs)
        found = {d["slug"] for d in resolved}
        unknown = [s for s in slugs if s not in found]
        return resolved, unknown, "slash"

    goal = instructions_goal_text(instructions)
    if not goal:
        return [], [], "none"

    routing = route_question(goal, embedder)
    routed = routing.get("domain_slugs") or []
    if not routed and routing.get("domain_slug"):
        routed = [routing["domain_slug"]]
    if not routed:
        return [], [], routing.get("method") or "none"
    resolved = resolve_domains(list(routed))
    return resolved, [], routing.get("method") or "routed"


def _is_email_server(server: dict[str, Any]) -> bool:
    slug = (server.get("slug") or "").lower()
    name = (server.get("name") or "").lower()
    kind = (server.get("server_kind") or "").lower()
    return "email" in slug or "email" in name or kind == "email"


def resolve_agent_mcp_kit(
    instructions: str,
    extra_tools: list[dict[str, Any]] | None = None,
    *,
    embedder=None,
) -> dict[str, Any]:
    """Identify tools, prompts, and resources this agent should pin at save time."""
    resolved, unknown, method = resolve_agent_domains(instructions, embedder)
    tools: list[dict[str, str]] = []
    prompts: list[dict[str, str]] = []
    resources: list[dict[str, str]] = []
    seen_tools: set[tuple[str, str]] = set()
    seen_prompts: set[tuple[str, str]] = set()
    seen_resources: set[tuple[str, str]] = set()

    def add_tool(server_id: str | None, name: str | None) -> None:
        tool_name = (name or "").strip()
        if not server_id or not tool_name or tool_name in _SKIP_SAVE_TOOLS:
            return
        key = (str(server_id), tool_name)
        if key in seen_tools:
            return
        seen_tools.add(key)
        tools.append({"mcp_server_id": str(server_id), "tool_name": tool_name})

    def add_prompt(server_id: str | None, name: str | None) -> None:
        prompt_name = (name or "").strip()
        if not server_id or not prompt_name:
            return
        key = (str(server_id), prompt_name)
        if key in seen_prompts:
            return
        seen_prompts.add(key)
        prompts.append({"mcp_server_id": str(server_id), "prompt_name": prompt_name})

    def add_resource(server_id: str | None, uri: str | None) -> None:
        resource_uri = (uri or "").strip()
        if not server_id or not resource_uri:
            return
        key = (str(server_id), resource_uri)
        if key in seen_resources:
            return
        seen_resources.add(key)
        resources.append({"mcp_server_id": str(server_id), "resource_uri": resource_uri})

    for domain in resolved:
        domain_id = domain.get("id")
        if not domain_id:
            continue
        for cap in domain_mcp_capabilities(domain_id, "tool"):
            add_tool(cap.get("mcp_server_id"), cap.get("capability_name"))
        for cap in domain_mcp_capabilities(domain_id, "prompt"):
            add_prompt(cap.get("mcp_server_id"), cap.get("capability_name"))
        for cap in domain_mcp_capabilities(domain_id, "resource"):
            add_resource(cap.get("mcp_server_id"), cap.get("capability_name"))

    for item in extra_tools or []:
        add_tool(item.get("mcp_server_id"), item.get("tool_name"))

    inferred = infer_agent_capabilities(instructions)
    if inferred.get("send_email"):
        for server in list_mcp_servers(enabled_only=True):
            if not _is_email_server(server):
                continue
            for tool_name in _EMAIL_TOOL_NAMES:
                add_tool(server.get("id"), tool_name)

    return {
        "tools": tools,
        "prompts": prompts,
        "resources": resources,
        "domains": [{"id": d.get("id"), "slug": d.get("slug"), "name": d.get("name")} for d in resolved],
        "domain_method": method,
        "unknown_slugs": unknown,
    }


def save_agent_mcp_kit(
    agent_id: str,
    extra_tools: list[dict[str, Any]] | None = None,
    *,
    embedder=None,
) -> dict | None:
    """Resolve required MCP bindings from instructions and persist them on the agent."""
    agent = get_agent(agent_id)
    if not agent:
        return None
    extras = extra_tools
    if extras is None:
        extras = [
            {"mcp_server_id": t.get("mcp_server_id"), "tool_name": t.get("tool_name")}
            for t in (agent.get("tools") or [])
        ]
    kit = resolve_agent_mcp_kit(agent.get("instructions") or "", extras, embedder=embedder)
    set_agent_mcp_kit(
        agent_id,
        tools=kit["tools"],
        prompts=kit["prompts"],
        resources=kit["resources"],
    )
    caps = dict(agent.get("capabilities") or {})
    caps["mcp_kit"] = {
        "resolved_at": datetime.now(timezone.utc).isoformat(),
        "domain_method": kit["domain_method"],
        "domain_slugs": [d.get("slug") for d in kit["domains"] if d.get("slug")],
        "tool_count": len(kit["tools"]),
        "prompt_count": len(kit["prompts"]),
        "resource_count": len(kit["resources"]),
    }
    update_agent(agent_id, capabilities=caps)
    return get_agent(agent_id)
