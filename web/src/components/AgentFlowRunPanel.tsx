import { useState } from "react";
import { api } from "../api/client";
import type { AgentRunStep } from "../types";
import { AgentEmailPreview } from "./AgentEmailPreview";
import { AgentRunStepsList } from "./AgentRunStepsList";

type Props = {
  flowId: string;
  disabled?: boolean;
};

export function AgentFlowRunPanel({ flowId, disabled = false }: Props) {
  const [running, setRunning] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [steps, setSteps] = useState<AgentRunStep[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [reportHtml, setReportHtml] = useState<string | null>(null);

  const emailStep = steps.find((s) => s.step_id.endsWith(":email"));
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
    setSteps([]);
    setStatus(null);
    setReportHtml(null);
    try {
      await api.agentFlowRunStream(flowId, (event) => {
        if (event.type === "status" && event.message) {
          setStatus(event.message);
        }
        if (event.type === "step" && event.step_id) {
          const step: AgentRunStep = {
            step_id: event.step_id,
            message: event.message || "",
            status: event.status,
            payload: event.payload,
          };
          setSteps((prev) => {
            const idx = prev.findIndex((s) => s.step_id === step.step_id);
            if (idx >= 0) {
              const next = [...prev];
              next[idx] = step;
              return next;
            }
            return [...prev, step];
          });
          if (event.step_id.endsWith(":report") && event.payload?.html) {
            setReportHtml(String(event.payload.html));
          }
        }
        if (event.type === "result" && event.payload?.report_html) {
          setReportHtml(String(event.payload.report_html));
        }
      });
    } catch (e) {
      setError(String(e));
    } finally {
      setRunning(false);
      setStatus(null);
    }
  };

  const openReport = () => {
    if (!reportHtml) return;
    const blob = new Blob([reportHtml], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank", "noopener,noreferrer");
  };

  return (
    <div className="agent-run-panel card card-pad mt-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">Test flow</h3>
        <button type="button" className="btn btn-secondary btn-sm" disabled={disabled || running} onClick={run}>
          {running ? "Running…" : "Run flow"}
        </button>
      </div>

      {status && (
        <p className="mt-2 text-sm italic text-zinc-500" role="status">
          {status}
        </p>
      )}

      {steps.length > 0 && (
        <div className="mt-3">
          <AgentRunStepsList steps={steps} />
        </div>
      )}

      {reportHtml && (
        <button type="button" className="btn btn-secondary btn-sm mt-3" onClick={openReport}>
          Open report preview
        </button>
      )}

      {emailPayload && (
        <div className="mt-3">
          <AgentEmailPreview
            to={String(emailPayload.to ?? "")}
            subject={String(emailPayload.subject ?? "")}
            htmlBody={String(emailPayload.html_body ?? "")}
            smtpConfigured={Boolean(emailPayload.smtp_configured)}
            sent={Boolean(emailPayload.sent)}
          />
        </div>
      )}

      {error && <p className="alert-error mt-2">{error}</p>}
    </div>
  );
}
