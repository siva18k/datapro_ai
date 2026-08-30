import { useState, type ReactNode } from "react";
import { api } from "../api/client";
import { AgentEmailPreview } from "./AgentEmailPreview";
import { AgentRunResearchView } from "./AgentRunResearchView";
import { applyAgentRunStreamEvent, createLiveRunState } from "../utils/agentRunStream";

export type AgentRunState = ReturnType<typeof useAgentRun>;

export function useAgentRun(agentId: string, entityLabel = "Test run", entityKind: "agent" | "flow" = "agent") {
  const [running, setRunning] = useState(false);
  const [liveRun, setLiveRun] = useState(() => createLiveRunState(entityLabel, entityKind));
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setRunning(true);
    setError(null);
    setLiveRun(createLiveRunState(entityLabel, entityKind));
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

  return { running, liveRun, error, run, showRun };
}

export function AgentRunResults({
  liveRun,
  running,
  error,
}: {
  liveRun: AgentRunState["liveRun"];
  running: boolean;
  error: string | null;
}) {
  const emailStep = liveRun.steps.find((s) => s.step_id === "email");
  const emailPayload = emailStep?.payload as {
    to?: string;
    subject?: string;
    html_body?: string;
    smtp_configured?: boolean;
    sent?: boolean;
  } | undefined;

  if (!running && liveRun.steps.length === 0 && !error) {
    return null;
  }

  return (
    <div className="agent-run-panel card card-pad mt-4">
      {liveRun.steps.length > 0 || running ? (
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
      ) : null}
      {error && <p className="alert-error mt-2">{error}</p>}
    </div>
  );
}

type Props = {
  agentId: string;
  disabled?: boolean;
  renderRunButton?: (props: { run: () => void; running: boolean; disabled: boolean }) => ReactNode;
};

/** @deprecated Prefer useAgentRun + AgentRunResults with an inline run button. */
export function AgentRunPanel({ agentId, disabled = false, renderRunButton }: Props) {
  const { running, liveRun, error, run, showRun } = useAgentRun(agentId);

  return (
    <>
      {renderRunButton?.({ run, running, disabled: disabled || running })}
      {(showRun || error) && <AgentRunResults liveRun={liveRun} running={running} error={error} />}
    </>
  );
}
