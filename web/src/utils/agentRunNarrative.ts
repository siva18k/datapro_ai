import type { AgentRunStep } from "../types";

export type NarrativeBlock =
  | { kind: "phase"; title: string; status?: string }
  | { kind: "text"; text: string; status?: string }
  | {
      kind: "mcp_group";
      summary: string;
      items: AgentRunStep[];
      status?: string;
    }
  | { kind: "plan"; message: string; plan: string; status?: string }
  | {
      kind: "kpi";
      message: string;
      passed?: boolean;
      explanation?: string;
      summary?: string;
      status?: string;
    }
  | { kind: "report"; message: string; status?: string }
  | { kind: "email"; step: AgentRunStep };

function innerStepId(stepId: string): string {
  const colon = stepId.indexOf(":");
  if (colon === -1) return stepId;
  const rest = stepId.slice(colon + 1);
  const head = rest.split(":")[0];
  if (head === "mcp" || ["plan", "kpi", "report", "email", "error"].includes(head)) {
    return rest;
  }
  return stepId;
}

function isMcpStep(step: AgentRunStep): boolean {
  const id = step.step_id;
  const inner = innerStepId(id);
  return (
    inner === "mcp" ||
    inner === "mcp_catalog" ||
    inner === "tools" ||
    inner.startsWith("mcp:") ||
    /^mcp:/i.test(id)
  );
}

function isPhaseMarker(step: AgentRunStep): boolean {
  return step.step_id.endsWith("_start") || step.step_id.endsWith("_done");
}

function mcpItemLabel(step: AgentRunStep): string {
  const payload = step.payload ?? {};
  if (typeof payload.uri === "string") return payload.uri;
  if (typeof payload.tool === "string") return payload.tool;
  if (typeof payload.prompt === "string") return payload.prompt;
  return step.message.replace(/^MCP (tool|resource|prompt) «/i, "").replace(/».*$/, "");
}

export function buildAgentNarrative(steps: AgentRunStep[]): NarrativeBlock[] {
  const blocks: NarrativeBlock[] = [];
  let index = 0;

  while (index < steps.length) {
    const step = steps[index];
    const id = innerStepId(step.step_id);

    if (step.step_id.endsWith("_start")) {
      blocks.push({ kind: "phase", title: step.message, status: step.status });
      index += 1;
      continue;
    }

    if (isMcpStep(step)) {
      const items: AgentRunStep[] = [];
      let summary = "";
      let status: string | undefined;
      while (index < steps.length && isMcpStep(steps[index])) {
        const current = steps[index];
        if (innerStepId(current.step_id) === "mcp") {
          summary = current.message;
          status = current.status;
        } else {
          items.push(current);
        }
        index += 1;
      }
      if (!summary && items.length > 0) {
        const labels = items.slice(0, 4).map(mcpItemLabel);
        summary =
          items.length === 1
            ? `Loaded MCP context via ${labels[0]}.`
            : `Loaded MCP context (${items.length} calls): ${labels.join(", ")}${items.length > 4 ? "…" : ""}.`;
      }
      if (summary || items.length > 0) {
        blocks.push({ kind: "mcp_group", summary, items, status });
      }
      continue;
    }

    if (id === "plan") {
      const plan = String(step.payload?.plan ?? "").trim();
      blocks.push({
        kind: "plan",
        message: step.message || "Planned the workflow.",
        plan,
        status: step.status,
      });
      index += 1;
      continue;
    }

    if (id === "kpi") {
      const payload = step.payload ?? {};
      blocks.push({
        kind: "kpi",
        message: step.message,
        passed: typeof payload.passed === "boolean" ? payload.passed : undefined,
        explanation: typeof payload.explanation === "string" ? payload.explanation : undefined,
        summary: typeof payload.summary === "string" ? payload.summary : undefined,
        status: step.status,
      });
      index += 1;
      continue;
    }

    if (id === "report") {
      blocks.push({ kind: "report", message: step.message, status: step.status });
      index += 1;
      continue;
    }

    if (id === "email") {
      blocks.push({ kind: "email", step });
      index += 1;
      continue;
    }

    if (step.step_id.endsWith("_done")) {
      blocks.push({ kind: "text", text: step.message, status: step.status });
      index += 1;
      continue;
    }

    if (isPhaseMarker(step)) {
      index += 1;
      continue;
    }

    blocks.push({ kind: "text", text: step.message, status: step.status });
    index += 1;
  }

  return blocks;
}

export function narrativeLeadText(
  _blocks: NarrativeBlock[],
  entityLabel: string,
  entityKind: "agent" | "flow" = "agent",
): string {
  const label = entityKind === "flow" ? "Flow" : "Agent";
  return `${label} «${entityLabel}» finished. Here's how the run progressed.`;
}

export function runningLeadText(
  entityLabel: string,
  entityKind: "agent" | "flow" = "agent",
): string {
  const label = entityKind === "flow" ? "Flow" : "Agent";
  return `${label} «${entityLabel}» is running…`;
}
