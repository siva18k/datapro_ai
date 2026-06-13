import { AgentEmailPreview } from "./AgentEmailPreview";
import { AgentRunStepsList } from "./AgentRunStepsList";
import type { AgentRunStep } from "../types";

type Props = {
  flowName: string;
  steps: AgentRunStep[];
  reportHtml?: string | null;
};

export function AskAgentFlowRunResult({ flowName, steps, reportHtml }: Props) {
  const emailStep = steps.find((s) => s.step_id.endsWith(":email"));
  const emailPayload = emailStep?.payload as {
    to?: string;
    subject?: string;
    html_body?: string;
    smtp_configured?: boolean;
    sent?: boolean;
  } | undefined;

  const openReport = () => {
    if (!reportHtml) return;
    const blob = new Blob([reportHtml], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank", "noopener,noreferrer");
  };

  return (
    <div className="ask-agent-run-result">
      <p className="text-sm font-medium">Flow «{flowName}» completed</p>

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
    </div>
  );
}
