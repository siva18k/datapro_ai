import { useState } from "react";
import { api } from "../api/client";
import type { AgentRunStep } from "../types";
import { AgentEmailPreview } from "./AgentEmailPreview";
import { AgentRunResearchView } from "./AgentRunResearchView";
import { applyAgentRunStreamEvent, createLiveRunState } from "../utils/agentRunStream";

type Props = {
  agentId: string;
  disabled?: boolean;
};

export function AgentRunPanel({ agentId, disabled = false }: Props) {
  const [running, setRunning] = useState(false);
  const [liveRun, setLiveRun] = useState(() => createLiveRunState("Test run", "agent"));
  const [error, setError] = useState<string | null>(null);

  const emailStep = liveRun.steps.find((s) => s.step_id === "email");
  const emailPayload = emailStep?.payload as {
    to?: string;
    subject?: string;
    html_body?: string;
    smtp_configured?: boolean;
    sent?: boolean;
  } | undefined;

  const run = async () => {
    setRunning(true);
    setError(null);
    setLiveRun(createLiveRunState("Test run", "agent"));
    try {
      await api.agentRunStream(agentId, (event) => {
        setLiveRun((prev) => applyAgentRunStreamEvent(prev, event));
      });
    } catch (e) {
      setError(String(e));
    } finally {
      setRunning(false);
      setLiveRun((prev) => ({ ...prev, statusMessage: null }));
    }
  };

  const showRun = running || liveRun.steps.length > 0;

  return (
    <div className="agent-run-panel card card-pad mt-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">Test run</h3>
        <button type="button" className="btn btn-secondary btn-sm" disabled={disabled || running} onClick={run}>
          {running ? "Running…" : "Run test"}
        </button>
      </div>

      {showRun && (
        <div className="mt-3">
          <AgentRunResearchView
            entityLabel={liveRun.entityLabel}
            entityKind={liveRun.entityKind}
            steps={liveRun.steps}
            reportHtml={liveRun.reportHtml}
            isRunning={running}
            statusMessage={liveRun.statusMessage}
            emailPreview={
              !running && emailPayload ? (
                <AgentEmailPreview
                  to={String(emailPayload.to ?? "")}
                  subject={String(emailPayload.subject ?? "")}
                  htmlBody={String(emailPayload.html_body ?? "")}
                  smtpConfigured={Boolean(emailPayload.smtp_configured)}
                  sent={Boolean(emailPayload.sent)}
                />
              ) : undefined
            }
          />
        </div>
      )}

      {error && <p className="alert-error mt-2">{error}</p>}
    </div>
  );
}
