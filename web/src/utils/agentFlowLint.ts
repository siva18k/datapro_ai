import type { Agent, AgentFlowGraph } from "../types";

const MENTION_RE = /@([a-z0-9][a-z0-9_-]*)/gi;
const LIST_ITEM_RE = /^\s*(?:\d+[.)]\s+|[-*]\s+)/;
const FOLLOW_UP_RE =
  /\b(then|next|after that|pick top|top\s+\d+|most expensive|html output|create (?:a )?(?:simple )?html|table and graph|filter|summarize|rank|format|email)\b/i;

function instructionLines(instructions: string): string[] {
  return instructions
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0 && !line.startsWith("#"));
}

function actionLines(instructions: string): string[] {
  return instructionLines(instructions).filter(
    (line) => LIST_ITEM_RE.test(line) || FOLLOW_UP_RE.test(line) || line.startsWith("@") || line.length > 12,
  );
}

function nodeKind(node: AgentFlowGraph["nodes"][number]): "agent" | "task" {
  if (node.kind === "task") return "task";
  if (node.agent_id) return "agent";
  if ((node.instructions || "").trim() || (node.title || "").trim()) return "task";
  return "agent";
}

export function lintAgentFlow(
  instructions: string,
  graph: AgentFlowGraph,
  agents: Agent[],
): string[] {
  const warnings: string[] = [];
  const known = new Set(agents.filter((a) => a.enabled).map((a) => a.slug.toLowerCase()));
  const canvasSlugs = new Set(
    graph.nodes
      .filter((node) => nodeKind(node) === "agent")
      .map((node) => (node.agent_slug || "").toLowerCase())
      .filter(Boolean),
  );

  const mentioned = new Set<string>();
  for (const match of instructions.matchAll(MENTION_RE)) {
    mentioned.add(match[1].toLowerCase());
  }
  for (const slug of [...mentioned].sort()) {
    if (!known.has(slug)) {
      warnings.push(`Flow goal mentions @${slug}, but no enabled agent has that slug.`);
    } else if (!canvasSlugs.has(slug)) {
      warnings.push(
        `Flow goal mentions @${slug}, but that agent is not on the flow canvas. Drag it into Flow steps.`,
      );
    }
  }

  for (const node of graph.nodes) {
    if (nodeKind(node) !== "task") continue;
    if (!(node.instructions || "").trim()) {
      const title = (node.title || "").trim() || "Custom step";
      warnings.push(
        `Custom step «${title}» has no instructions. Write what this step should do (for example: pick the top 5 rows, then build an HTML table).`,
      );
    }
  }

  if (graph.nodes.length >= 2 && graph.edges.length === 0) {
    warnings.push(
      "The canvas has multiple steps but no connections. Drag the O on a card to the next step so later steps receive the previous result.",
    );
  }

  const actions = actionLines(instructions);
  const taskCount = graph.nodes.filter((node) => nodeKind(node) === "task").length;
  if (actions.length >= 2 && graph.nodes.length <= 1) {
    warnings.push(
      `Flow goal describes more than one action, but the canvas has ${graph.nodes.length === 0 ? "no steps" : "only 1 step"}. Add a Custom step for follow-up work (top N, HTML, formatting) and connect it after the agent that fetches data.`,
    );
  } else if (actions.length >= 3 && taskCount === 0 && graph.nodes.length < actions.length) {
    warnings.push(
      "Flow goal looks like a multi-step recipe, but every canvas step is an agent. Add Custom steps for transforms such as “pick top 5” or “create HTML”, and connect them in order.",
    );
  } else if (actions.some((line) => FOLLOW_UP_RE.test(line)) && taskCount === 0 && graph.nodes.length > 0) {
    warnings.push(
      "Flow goal asks for a follow-up (top N, HTML, filter, or format). That work does not run unless you add a Custom step and connect it to the agent result.",
    );
  }

  return warnings;
}
