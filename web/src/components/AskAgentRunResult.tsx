import { AgentEmailPreview } from "./AgentEmailPreview";
import { AgentRunResearchView } from "./AgentRunResearchView";
import type { AgentRunStep } from "../types";

type Props = {
  agentName: string;
  steps: AgentRunStep[];
  reportHtml?: string | null;
};

export function AskAgentRunResult({ agentName, steps, reportHtml }: Props) {
  const emailStep = steps.find((s) => s.step_id === "email" || s.step_id.endsWith(":email"));
  const emailPayload = emailStep?.payload as {
    to?: string;
    subject?: string;
    html_body?: string;
    smtp_configured?: boolean;
    sent?: boolean;
  } | undefined;

  const emailPreview = emailPayload ? (
    <AgentEmailPreview
      to={String(emailPayload.to ?? "")}
      subject={String(emailPayload.subject ?? "")}
      htmlBody={String(emailPayload.html_body ?? "")}
      smtpConfigured={Boolean(emailPayload.smtp_configured)}
      sent={Boolean(emailPayload.sent)}
    />
  ) : null;

  return (
    <AgentRunResearchView
      entityLabel={agentName}
      entityKind="agent"
      steps={steps}
      reportHtml={reportHtml}
      emailPreview={emailPreview}
    />
  );
}
