import type { AgentFlowGraph, AgentFlowGraphEdge, AgentFlowGraphNode } from "../types";

export function emptyAgentFlowGraph(): AgentFlowGraph {
  return { v: 2, nodes: [], edges: [] };
}

export function linearStepsToGraph(
  steps: Array<{
    agent_id?: string;
    handoff?: string;
    id?: string;
    kind?: "agent" | "task";
    title?: string;
    instructions?: string;
  }>,
): AgentFlowGraph {
  const nodes: AgentFlowGraphNode[] = [];
  const edges: AgentFlowGraphEdge[] = [];
  let prevId: string | null = null;
  let prevHandoff = "";

  steps.forEach((step, index) => {
    const kind = (step as { kind?: string }).kind === "task" || (!step.agent_id && ((step as { instructions?: string }).instructions || (step as { title?: string }).title))
      ? "task"
      : "agent";
    if (kind === "agent" && !step.agent_id) return;
    const nodeId = step.id ?? `n${index}`;
    nodes.push({
      id: nodeId,
      kind,
      agent_id: step.agent_id,
      column: (index % 2) as 0 | 1,
      agent_name: (step as { agent_name?: string }).agent_name,
      agent_slug: (step as { agent_slug?: string }).agent_slug,
      title: (step as { title?: string }).title,
      instructions: (step as { instructions?: string }).instructions,
    });
    if (prevId) {
      edges.push({
        from: prevId,
        to: nodeId,
        handoff: prevHandoff,
      });
    }
    prevHandoff = step.handoff ?? "";
    prevId = nodeId;
  });

  return { v: 2, nodes, edges };
}

export function parseAgentFlowSteps(steps: unknown): AgentFlowGraph {
  if (steps && typeof steps === "object" && !Array.isArray(steps) && (steps as AgentFlowGraph).v === 2) {
    const graph = steps as AgentFlowGraph;
    return {
      v: 2,
      nodes: (graph.nodes ?? []).filter(
        (node) => node.id && (node.kind === "task" || node.agent_id || (node.instructions || node.title)),
      ),
      edges: (graph.edges ?? []).filter((edge) => edge.from && edge.to),
    };
  }
  if (Array.isArray(steps)) {
    return linearStepsToGraph(steps);
  }
  return emptyAgentFlowGraph();
}

export function validateAgentFlowGraph(graph: AgentFlowGraph): string | null {
  const nodeIds = new Set(graph.nodes.map((node) => node.id));
  if (nodeIds.size === 0) return null;

  for (const edge of graph.edges) {
    if (!nodeIds.has(edge.from) || !nodeIds.has(edge.to)) {
      return "Flow connection references a missing step";
    }
    if (edge.from === edge.to) {
      return "A step cannot connect to itself";
    }
  }

  const indegree = new Map<string, number>();
  const adjacency = new Map<string, string[]>();
  for (const node of graph.nodes) {
    indegree.set(node.id, 0);
    adjacency.set(node.id, []);
  }
  for (const edge of graph.edges) {
    indegree.set(edge.to, (indegree.get(edge.to) ?? 0) + 1);
    adjacency.get(edge.from)?.push(edge.to);
  }

  const queue = [...indegree.entries()].filter(([, degree]) => degree === 0).map(([id]) => id);
  let visited = 0;
  while (queue.length > 0) {
    const current = queue.shift();
    if (!current) break;
    visited += 1;
    for (const next of adjacency.get(current) ?? []) {
      const degree = (indegree.get(next) ?? 0) - 1;
      indegree.set(next, degree);
      if (degree === 0) queue.push(next);
    }
  }

  if (visited !== graph.nodes.length) {
    return "Flow has a cycle — remove a connection and try again";
  }
  return null;
}

export function nodeKind(node: AgentFlowGraphNode): "agent" | "task" {
  if (node.kind === "task") return "task";
  if (node.agent_id) return "agent";
  if ((node.instructions || "").trim() || (node.title || "").trim()) return "task";
  return "agent";
}

export function nodeLabel(node: AgentFlowGraphNode, index: number): string {
  if (nodeKind(node) === "task") {
    return (node.title || "").trim() || `Custom step ${index + 1}`;
  }
  return node.agent_name ?? node.agent_slug ?? `Step ${index + 1}`;
}

export function updateNode(
  graph: AgentFlowGraph,
  nodeId: string,
  patch: Partial<AgentFlowGraphNode>,
): AgentFlowGraph {
  return {
    ...graph,
    nodes: graph.nodes.map((node) => (node.id === nodeId ? { ...node, ...patch } : node)),
  };
}

export function appendNode(
  graph: AgentFlowGraph,
  node: AgentFlowGraphNode,
  options?: { linkFromLast?: boolean },
): AgentFlowGraph {
  const edges = [...graph.edges];
  if (options?.linkFromLast && graph.nodes.length > 0) {
    const last = graph.nodes[graph.nodes.length - 1];
    if (last && !edges.some((edge) => edge.from === last.id && edge.to === node.id)) {
      edges.push({ from: last.id, to: node.id, handoff: "" });
    }
  }
  return { v: 2, nodes: [...graph.nodes, node], edges };
}

export function addEdge(
  graph: AgentFlowGraph,
  from: string,
  to: string,
): { graph: AgentFlowGraph; error?: string } {
  if (from === to) {
    return { graph, error: "A step cannot connect to itself" };
  }
  if (graph.edges.some((edge) => edge.from === from && edge.to === to)) {
    return { graph };
  }
  const next: AgentFlowGraph = {
    ...graph,
    edges: [...graph.edges, { from, to, handoff: "" }],
  };
  const validationError = validateAgentFlowGraph(next);
  if (validationError) {
    return { graph, error: validationError };
  }
  return { graph: next };
}

export function removeEdge(graph: AgentFlowGraph, from: string, to: string): AgentFlowGraph {
  return {
    ...graph,
    edges: graph.edges.filter((edge) => !(edge.from === from && edge.to === to)),
  };
}

export function toggleEdge(
  graph: AgentFlowGraph,
  from: string,
  to: string,
): AgentFlowGraph {
  const exists = graph.edges.some((edge) => edge.from === from && edge.to === to);
  return {
    ...graph,
    edges: exists
      ? graph.edges.filter((edge) => !(edge.from === from && edge.to === to))
      : [...graph.edges, { from, to, handoff: "" }],
  };
}

export function updateEdgeHandoff(
  graph: AgentFlowGraph,
  from: string,
  to: string,
  handoff: string,
): AgentFlowGraph {
  return {
    ...graph,
    edges: graph.edges.map((edge) =>
      edge.from === from && edge.to === to ? { ...edge, handoff } : edge,
    ),
  };
}

export function removeNode(graph: AgentFlowGraph, nodeId: string): AgentFlowGraph {
  return {
    v: 2,
    nodes: graph.nodes.filter((node) => node.id !== nodeId),
    edges: graph.edges.filter((edge) => edge.from !== nodeId && edge.to !== nodeId),
  };
}

export type RepositionPlacement = "before" | "after" | "append";

/** Move a node to another column and/or reorder it relative to siblings. */
export function repositionNode(
  graph: AgentFlowGraph,
  nodeId: string,
  options: { column: 0 | 1; targetId?: string | null; placement?: RepositionPlacement },
): AgentFlowGraph {
  const moving = graph.nodes.find((node) => node.id === nodeId);
  if (!moving) return graph;

  const nodes = graph.nodes.filter((node) => node.id !== nodeId);
  const { targetId, placement = "append" } = options;
  let column = options.column;

  let insertIdx = nodes.length;

  if (targetId && placement !== "append") {
    const targetIdx = nodes.findIndex((node) => node.id === targetId);
    if (targetIdx !== -1) {
      column = (nodes[targetIdx].column ?? 0) as 0 | 1;
      insertIdx = placement === "before" ? targetIdx : targetIdx + 1;
    }
  } else {
    let lastInCol = -1;
    for (let i = nodes.length - 1; i >= 0; i -= 1) {
      if ((nodes[i].column ?? 0) === column) {
        lastInCol = i;
        break;
      }
    }
    if (lastInCol !== -1) {
      insertIdx = lastInCol + 1;
    } else if (column === 0) {
      const firstCol1 = nodes.findIndex((node) => (node.column ?? 0) === 1);
      insertIdx = firstCol1 === -1 ? nodes.length : firstCol1;
    }
  }

  nodes.splice(insertIdx, 0, { ...moving, column });
  return { v: 2, nodes, edges: graph.edges };
}

export function incomingTargets(graph: AgentFlowGraph, nodeId: string): AgentFlowGraphEdge[] {
  return graph.edges.filter((edge) => edge.to === nodeId);
}

export function outgoingTargets(graph: AgentFlowGraph, nodeId: string): AgentFlowGraphEdge[] {
  return graph.edges.filter((edge) => edge.from === nodeId);
}
