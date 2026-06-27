import type { ReactNode } from "react";
import { MarkdownChat } from "./MarkdownChat";
import type { AgentRunStep } from "../types";
import {
  buildAgentNarrative,
  narrativeLeadText,
  runningLeadText,
  type NarrativeBlock,
} from "../utils/agentRunNarrative";

type Props = {
  entityLabel: string;
  entityKind?: "agent" | "flow";
  steps: AgentRunStep[];
  reportHtml?: string | null;
  emailPreview?: ReactNode;
  isRunning?: boolean;
  statusMessage?: string | null;
};

function statusClass(status?: string): string {
  if (status === "error") return "agent-research-line--error";
  if (status === "warn") return "agent-research-line--warn";
  return "";
}

function NarrativeLine({
  children,
  status,
}: {
  children: ReactNode;
  status?: string;
}) {
  return (
    <div className={`agent-research-line ${statusClass(status)}`.trim()}>
      <span className="agent-research-dot" aria-hidden />
      <div className="agent-research-line-body">{children}</div>
    </div>
  );
}

function ExpandBlock({
  label,
  children,
  defaultOpen = false,
}: {
  label: string;
  children: ReactNode;
  defaultOpen?: boolean;
}) {
  return (
    <details className="agent-research-expand" open={defaultOpen}>
      <summary>{label}</summary>
      <div className="agent-research-expand-body">{children}</div>
    </details>
  );
}

function McpGroupBlock({ block }: { block: Extract<NarrativeBlock, { kind: "mcp_group" }> }) {
  return (
    <NarrativeLine status={block.status}>
      <p className="agent-research-text">{block.summary}</p>
      {block.items.length > 0 && (
        <ExpandBlock label={`View ${block.items.length} MCP call${block.items.length === 1 ? "" : "s"}`}>
          <ul className="agent-research-mcp-list">
            {block.items.map((item) => (
              <li key={item.step_id} className={statusClass(item.status)}>
                <span className="agent-research-mcp-message">{item.message}</span>
                {item.payload && Object.keys(item.payload).length > 0 && (
                  <pre className="agent-research-payload">
                    {JSON.stringify(item.payload, null, 2).slice(0, 2_400)}
                  </pre>
                )}
              </li>
            ))}
          </ul>
        </ExpandBlock>
      )}
    </NarrativeLine>
  );
}

function NarrativeBlockView({
  block,
  onOpenReport,
}: {
  block: NarrativeBlock;
  onOpenReport?: () => void;
}) {
  switch (block.kind) {
    case "phase":
      return (
        <p className="agent-research-phase">{block.title}</p>
      );
    case "mcp_group":
      return <McpGroupBlock block={block} />;
    case "plan":
      return (
        <NarrativeLine status={block.status}>
          <p className="agent-research-text">{block.message}</p>
          {block.plan && (
            <ExpandBlock label="View workflow plan">
              <div className="agent-research-markdown">
                <MarkdownChat>{block.plan}</MarkdownChat>
              </div>
            </ExpandBlock>
          )}
        </NarrativeLine>
      );
    case "kpi":
      return (
        <NarrativeLine status={block.status}>
          <p className="agent-research-text">{block.message}</p>
          {(block.summary || block.explanation) && (
            <ExpandBlock label="View KPI details">
              {block.explanation && (
                <p className="agent-research-detail">{block.explanation}</p>
              )}
              {block.summary && (
                <div className="agent-research-markdown">
                  <MarkdownChat>{block.summary}</MarkdownChat>
                </div>
              )}
            </ExpandBlock>
          )}
        </NarrativeLine>
      );
    case "report":
      return (
        <NarrativeLine status={block.status}>
          <p className="agent-research-text">{block.message}</p>
          {onOpenReport && (
            <button type="button" className="agent-research-link" onClick={onOpenReport}>
              Open report preview
            </button>
          )}
        </NarrativeLine>
      );
    case "email":
      return (
        <NarrativeLine status={block.step.status}>
          <p className="agent-research-text">{block.step.message}</p>
        </NarrativeLine>
      );
    case "text":
      return (
        <NarrativeLine status={block.status}>
          <p className="agent-research-text">{block.text}</p>
        </NarrativeLine>
      );
    default:
      return null;
  }
}

function ActiveStatusLine({ message }: { message: string }) {
  return (
    <div className="agent-research-line agent-research-line--active">
      <span className="agent-research-dot agent-research-dot--pulse" aria-hidden />
      <div className="agent-research-line-body">
        <p className="agent-research-text agent-research-text--active">{message}</p>
      </div>
    </div>
  );
}

export function AgentRunResearchView({
  entityLabel,
  entityKind = "agent",
  steps,
  reportHtml,
  emailPreview,
  isRunning = false,
  statusMessage = null,
}: Props) {
  const blocks = buildAgentNarrative(steps);
  const lead = isRunning
    ? runningLeadText(entityLabel, entityKind)
    : narrativeLeadText(blocks, entityLabel, entityKind);

  const openReport = () => {
    if (!reportHtml) return;
    const blob = new Blob([reportHtml], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank", "noopener,noreferrer");
  };

  if (!isRunning && blocks.length === 0) {
    return (
      <div className="chat-assistant agent-research-result">
        <p className="agent-research-lead">
          {entityKind === "flow" ? "Flow" : "Agent"} «{entityLabel}» completed with no step details.
        </p>
      </div>
    );
  }

  const showActiveStatus =
    isRunning &&
    statusMessage &&
    statusMessage.trim().length > 0;

  return (
    <div
      className={`chat-assistant agent-research-result${isRunning ? " agent-research-result--running" : ""}`}
      role={isRunning ? "status" : undefined}
      aria-live={isRunning ? "polite" : undefined}
    >
      <p className="agent-research-lead">{lead}</p>
      {(blocks.length > 0 || showActiveStatus) && (
        <div className="agent-research-body">
          {blocks.map((block, index) => (
            <NarrativeBlockView
              key={`${block.kind}-${index}`}
              block={block}
              onOpenReport={!isRunning && reportHtml ? openReport : undefined}
            />
          ))}
          {showActiveStatus && <ActiveStatusLine message={statusMessage} />}
        </div>
      )}
      {!isRunning && emailPreview && <div className="agent-research-email">{emailPreview}</div>}
    </div>
  );
}
