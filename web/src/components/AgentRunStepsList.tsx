import { AgentRunResearchView } from "./AgentRunResearchView";
import type { AgentRunStep } from "../types";

type Props = {
  steps: AgentRunStep[];
  entityLabel?: string;
  entityKind?: "agent" | "flow";
  reportHtml?: string | null;
  emailPreview?: React.ReactNode;
  isRunning?: boolean;
  statusMessage?: string | null;
};

/** Research-style narrative timeline for agent / flow run steps. */
export function AgentRunStepsList({
  steps,
  entityLabel = "Agent",
  entityKind = "agent",
  reportHtml,
  emailPreview,
  isRunning = false,
  statusMessage = null,
}: Props) {
  return (
    <AgentRunResearchView
      entityLabel={entityLabel}
      entityKind={entityKind}
      steps={steps}
      reportHtml={reportHtml}
      emailPreview={emailPreview}
      isRunning={isRunning}
      statusMessage={statusMessage}
    />
  );
}
