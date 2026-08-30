"""Warn when the flow goal doesn't match the canvas graph."""

from __future__ import annotations

import re
from typing import Any

from agent_flow_graph import incoming_edges, node_kind, node_label, normalize_flow_steps

_MENTION_RE = re.compile(r"@([a-z0-9][a-z0-9_-]*)", re.I)
_LIST_ITEM_RE = re.compile(r"^\s*(?:\d+[\.\)]\s+|[-*]\s+)")
_FOLLOW_UP_RE = re.compile(
    r"\b("
    r"then|next|after that|pick top|top\s+\d+|most expensive|"
    r"html output|create (?:a )?(?:simple )?html|table and graph|"
    r"filter|summarize|rank|format|email"
    r")\b",
    re.I,
)


def _instruction_lines(instructions: str) -> list[str]:
    lines: list[str] = []
    for raw in (instructions or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        lines.append(line)
    return lines


def _action_lines(instructions: str) -> list[str]:
    out: list[str] = []
    for line in _instruction_lines(instructions):
        if _LIST_ITEM_RE.match(line) or _FOLLOW_UP_RE.search(line) or line.startswith("@"):
            out.append(line)
        elif len(line) > 12:
            out.append(line)
    return out


def lint_flow(
    instructions: str,
    steps: Any,
    *,
    known_slugs: set[str] | None = None,
) -> list[str]:
    """Return user-facing warnings. Empty list means the flow looks consistent."""
    graph = normalize_flow_steps(steps)
    nodes = graph.get("nodes") or []
    warnings: list[str] = []

    canvas_slugs = {
        (n.get("agent_slug") or "").strip().lower()
        for n in nodes
        if node_kind(n) == "agent"
    }
    canvas_slugs.discard("")

    mentioned = {m.group(1).lower() for m in _MENTION_RE.finditer(instructions or "")}
    for slug in sorted(mentioned):
        if known_slugs is not None and slug not in known_slugs:
            warnings.append(
                f"Flow goal mentions @{slug}, but no enabled agent has that slug."
            )
        elif slug not in canvas_slugs:
            warnings.append(
                f"Flow goal mentions @{slug}, but that agent is not on the flow canvas. "
                "Drag it into Flow steps or type @ again after the agent exists."
            )

    for node in nodes:
        if node_kind(node) != "task":
            continue
        if not (node.get("instructions") or "").strip():
            title = node_label(node)
            warnings.append(
                f"Custom step «{title}» has no instructions. Write what this step should do "
                "(for example: pick the top 5 rows, then build an HTML table)."
            )

    if len(nodes) >= 2 and not (graph.get("edges") or []):
        warnings.append(
            "The canvas has multiple steps but no connections. Drag the O on a card to the next "
            "step so later steps receive the previous result."
        )

    action_lines = _action_lines(instructions)
    task_count = sum(1 for n in nodes if node_kind(n) == "task")
    if len(action_lines) >= 2 and len(nodes) <= 1:
        warnings.append(
            "Flow goal describes more than one action, but the canvas has "
            f"{'no steps' if not nodes else 'only 1 step'}. "
            "Add a Custom step for follow-up work (top N, HTML, formatting) and connect it "
            "after the agent that fetches data."
        )
    elif len(action_lines) >= 3 and task_count == 0 and len(nodes) < len(action_lines):
        warnings.append(
            "Flow goal looks like a multi-step recipe, but every canvas step is an agent. "
            "Agents only run their own job. Add Custom steps for transforms such as "
            "“pick top 5” or “create HTML”, and connect them in order."
        )
    elif any(_FOLLOW_UP_RE.search(line) for line in action_lines) and task_count == 0 and nodes:
        warnings.append(
            "Flow goal asks for a follow-up (top N, HTML, filter, or format). "
            "That work does not run unless you add a Custom step and connect it to the agent result."
        )

    return warnings
