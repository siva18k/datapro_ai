"""Normalize, validate, and order agent flow graphs (nodes + edges)."""

from __future__ import annotations

from collections import deque
from typing import Any


def empty_graph() -> dict[str, Any]:
    return {"v": 2, "nodes": [], "edges": []}


def node_kind(node: dict[str, Any] | None) -> str:
    if not node:
        return "agent"
    kind = str(node.get("kind") or "").strip().lower()
    if kind in {"task", "custom"}:
        return "task"
    if node.get("agent_id"):
        return "agent"
    if (node.get("instructions") or "").strip() or (node.get("title") or "").strip():
        return "task"
    return "agent"


def node_label(node: dict[str, Any] | None, *, fallback: str = "Step") -> str:
    if not node:
        return fallback
    if node_kind(node) == "task":
        return (node.get("title") or "").strip() or "Custom step"
    return (
        (node.get("agent_name") or "").strip()
        or (node.get("agent_slug") or "").strip()
        or fallback
    )


def _normalized_node(node: dict[str, Any], *, index: int) -> dict[str, Any] | None:
    node_id = str(node.get("id") or "").strip()
    if not node_id:
        return None
    kind = node_kind(node)
    column = node.get("column")
    try:
        column_i = int(column) % 2 if column is not None else index % 2
    except (TypeError, ValueError):
        column_i = index % 2
    if kind == "task":
        return {
            "id": node_id,
            "kind": "task",
            "title": (node.get("title") or "").strip(),
            "instructions": (node.get("instructions") or "").strip(),
            "column": column_i,
        }
    agent_id = node.get("agent_id")
    if not agent_id:
        return None
    out: dict[str, Any] = {
        "id": node_id,
        "kind": "agent",
        "agent_id": agent_id,
        "column": column_i,
    }
    if node.get("agent_name"):
        out["agent_name"] = node["agent_name"]
    if node.get("agent_slug"):
        out["agent_slug"] = node["agent_slug"]
    return out


def _is_keepable_node(node: Any) -> bool:
    if not isinstance(node, dict) or not node.get("id"):
        return False
    kind = node_kind(node)
    if kind == "task":
        return True
    return bool(node.get("agent_id"))


def linear_steps_to_graph(steps: list[dict[str, Any]]) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    prev_id: str | None = None
    prev_handoff = ""
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        node_id = str(step.get("id") or f"n{index}")
        raw = {**step, "id": node_id}
        normalized = _normalized_node(raw, index=index)
        if not normalized:
            continue
        nodes.append(normalized)
        if prev_id is not None:
            edges.append(
                {
                    "from": prev_id,
                    "to": node_id,
                    "handoff": prev_handoff,
                }
            )
        prev_handoff = (step.get("handoff") or "").strip()
        prev_id = node_id
    return {"v": 2, "nodes": nodes, "edges": edges}


def normalize_flow_steps(steps: Any) -> dict[str, Any]:
    if isinstance(steps, dict) and steps.get("v") == 2:
        raw_nodes = [n for n in (steps.get("nodes") or []) if _is_keepable_node(n)]
        nodes = []
        for index, node in enumerate(raw_nodes):
            normalized = _normalized_node(node, index=index)
            if normalized:
                nodes.append(normalized)
        edges = [
            e
            for e in (steps.get("edges") or [])
            if isinstance(e, dict) and e.get("from") and e.get("to")
        ]
        return {"v": 2, "nodes": nodes, "edges": edges}
    if isinstance(steps, list):
        return linear_steps_to_graph(steps)
    return empty_graph()


def validate_graph(graph: dict[str, Any]) -> tuple[bool, str]:
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    if not nodes:
        return True, ""
    node_ids = {n["id"] for n in nodes}
    for edge in edges:
        if edge.get("from") not in node_ids or edge.get("to") not in node_ids:
            return False, "Flow connection references a missing step"
        if edge.get("from") == edge.get("to"):
            return False, "A step cannot connect to itself"
    indegree = {node_id: 0 for node_id in node_ids}
    adjacency: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    for edge in edges:
        src = edge["from"]
        dst = edge["to"]
        adjacency[src].append(dst)
        indegree[dst] += 1
    queue = deque([node_id for node_id, degree in indegree.items() if degree == 0])
    visited = 0
    while queue:
        current = queue.popleft()
        visited += 1
        for nxt in adjacency[current]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)
    if visited != len(node_ids):
        return False, "Flow has a cycle — remove a connection and try again"
    return True, ""


def topological_order(graph: dict[str, Any]) -> list[str]:
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    node_ids = [n["id"] for n in nodes]
    indegree = {node_id: 0 for node_id in node_ids}
    adjacency: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    for edge in edges:
        src = edge["from"]
        dst = edge["to"]
        if src not in adjacency or dst not in indegree:
            continue
        adjacency[src].append(dst)
        indegree[dst] += 1
    queue = deque([node_id for node_id in node_ids if indegree[node_id] == 0])
    order: list[str] = []
    while queue:
        current = queue.popleft()
        order.append(current)
        for nxt in adjacency[current]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)
    if len(order) != len(node_ids):
        raise ValueError("Flow has a cycle")
    return order


def incoming_edges(graph: dict[str, Any], node_id: str) -> list[dict[str, Any]]:
    return [edge for edge in (graph.get("edges") or []) if edge.get("to") == node_id]


def node_by_id(graph: dict[str, Any], node_id: str) -> dict[str, Any] | None:
    for node in graph.get("nodes") or []:
        if node.get("id") == node_id:
            return node
    return None
