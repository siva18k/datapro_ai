import type { AgentRunStep } from "../types";

export type LiveAgentRunState = {
  entityLabel: string;
  entityKind: "agent" | "flow";
  steps: AgentRunStep[];
  reportHtml: string | null;
  statusMessage: string | null;
};

export type AgentRunStreamEvent = {
  type: string;
  message?: string;
  step_id?: string;
  status?: string;
  payload?: Record<string, unknown>;
};

export function createLiveRunState(
  entityLabel: string,
  entityKind: "agent" | "flow",
): LiveAgentRunState {
  return {
    entityLabel,
    entityKind,
    steps: [],
    reportHtml: null,
    statusMessage: "Starting…",
  };
}

export function applyAgentRunStreamEvent(
  prev: LiveAgentRunState,
  event: AgentRunStreamEvent,
): LiveAgentRunState {
  if (event.type === "status" && event.message) {
    return { ...prev, statusMessage: event.message };
  }

  if (event.type === "step" && event.step_id) {
    const step: AgentRunStep = {
      step_id: event.step_id,
      message: event.message || "",
      status: event.status,
      payload: event.payload,
    };
    const idx = prev.steps.findIndex((s) => s.step_id === step.step_id);
    const steps =
      idx >= 0 ? prev.steps.map((s, i) => (i === idx ? step : s)) : [...prev.steps, step];

    let reportHtml = prev.reportHtml;
    if (
      (event.step_id === "report" || event.step_id.endsWith(":report")) &&
      event.payload?.html
    ) {
      reportHtml = String(event.payload.html);
    }

    return { ...prev, steps, reportHtml };
  }

  if (event.type === "result" && event.payload?.report_html) {
    return { ...prev, reportHtml: String(event.payload.report_html) };
  }

  return prev;
}
