import type { PipelineTraceDetail, PipelineTraceStep } from "../types";
import { IconDebug } from "./SidebarNavIcons";

interface AskPipelineStepsProps {
  steps: PipelineTraceStep[];
  isActive: boolean;
  /** Full-page debug tab — always expanded, no collapse */
  standalone?: boolean;
  onOpenInTab?: () => void;
}

function CopyButton({ text, label }: { text: string; label: string }) {
  return (
    <button
      type="button"
      className="ask-pipeline-copy"
      onClick={() => void navigator.clipboard.writeText(text)}
      title={`Copy ${label}`}
    >
      Copy
    </button>
  );
}

function MetaRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="ask-pipeline-meta-row">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function TraceDetail({ detail }: { detail: PipelineTraceDetail }) {
  return (
    <div className="ask-pipeline-detail">
      <dl className="ask-pipeline-meta">
        {detail.question && <MetaRow label="Question" value={detail.question} />}
        {detail.top_k != null && <MetaRow label="Top K" value={String(detail.top_k)} />}
        {detail.domain_overrides && detail.domain_overrides.length > 0 && (
          <MetaRow label="Domain scope" value={detail.domain_overrides.join(", ")} />
        )}
        {detail.domain_override && <MetaRow label="Domain override" value={detail.domain_override} />}
        {detail.domain_name && <MetaRow label="Domain" value={detail.domain_name} />}
        {detail.domain_id && <MetaRow label="domain_id" value={detail.domain_id} />}
        {detail.routing_method && <MetaRow label="Routing" value={detail.routing_method} />}
        {detail.routing_confidence != null && (
          <MetaRow label="Confidence" value={detail.routing_confidence.toFixed(3)} />
        )}
        {detail.execution_kind && <MetaRow label="Path" value={detail.execution_kind} />}
        {detail.source_name && <MetaRow label="Dataset" value={detail.source_name} />}
        {detail.source_id && <MetaRow label="source_id" value={detail.source_id} />}
        {detail.retrieval && <MetaRow label="Retrieval" value={detail.retrieval} />}
        {detail.retrieval_query && <MetaRow label="RAG query" value={detail.retrieval_query} />}
        {detail.mcp_url && <MetaRow label="MCP URL" value={detail.mcp_url} />}
        {detail.mcp_tool && <MetaRow label="MCP tool" value={detail.mcp_tool} />}
        {detail.mcp_arguments && (
          <MetaRow label="MCP arguments" value={JSON.stringify(detail.mcp_arguments)} />
        )}
        {detail.row_count != null && <MetaRow label="Rows" value={String(detail.row_count)} />}
        {detail.columns && detail.columns.length > 0 && (
          <MetaRow label="Columns" value={detail.columns.join(", ")} />
        )}
      </dl>

      {detail.llm_prompt && (
        <div className="ask-pipeline-sql-block">
          <div className="ask-pipeline-sql-head">
            <span>LLM prompt</span>
            <CopyButton text={detail.llm_prompt} label="LLM prompt" />
          </div>
          <pre className="ask-pipeline-sql ask-pipeline-sql--compact">{detail.llm_prompt}</pre>
        </div>
      )}

      {detail.sql && (
        <div className="ask-pipeline-sql-block">
          <div className="ask-pipeline-sql-head">
            <span>Executed SQL</span>
            <CopyButton text={detail.sql} label="SQL" />
          </div>
          <pre className="ask-pipeline-sql">{detail.sql}</pre>
        </div>
      )}

      {detail.chunks && detail.chunks.length > 0 && (
        <div className="ask-pipeline-chunks">
          <p className="ask-pipeline-chunks-title">Retrieved chunks (verify in DB)</p>
          <ul className="ask-pipeline-chunks-list">
            {detail.chunks.map((chunk) => (
              <li key={`${chunk.source_file}:${chunk.chunk_id}`} className="ask-pipeline-chunk">
                <div className="ask-pipeline-chunk-head">
                  <span className="ask-pipeline-chunk-file">{chunk.source_file}</span>
                  <span className="ask-pipeline-chunk-id">chunk_id: {chunk.chunk_id}</span>
                  {chunk.distance != null && (
                    <span className="ask-pipeline-chunk-dist">distance: {chunk.distance.toFixed(4)}</span>
                  )}
                </div>
                {(chunk.domain_id || chunk.source_id) && (
                  <div className="ask-pipeline-chunk-ids">
                    {chunk.domain_id && <span>domain_id: {chunk.domain_id}</span>}
                    {chunk.source_id && <span>source_id: {chunk.source_id}</span>}
                  </div>
                )}
                {chunk.text_preview && (
                  <p className="ask-pipeline-chunk-preview">{chunk.text_preview}</p>
                )}
                <div className="ask-pipeline-sql-block">
                  <div className="ask-pipeline-sql-head">
                    <span>Verify SQL</span>
                    <CopyButton text={chunk.verify_sql} label="verify SQL" />
                  </div>
                  <pre className="ask-pipeline-sql ask-pipeline-sql--compact">{chunk.verify_sql}</pre>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export function AskPipelineSteps({
  steps,
  isActive,
  standalone = false,
  onOpenInTab,
}: AskPipelineStepsProps) {
  if (steps.length === 0) return null;

  const usedSql = steps.some((s) => s.phase === "sql" && s.detail?.sql);
  const usedMcp = steps.some(
    (s) => s.phase === "mcp" || s.detail?.retrieval === "mcp" || s.detail?.mcp_tool,
  );
  const usedRag = steps.some(
    (s) =>
      s.phase === "rag" ||
      s.detail?.retrieval === "vector" ||
      Boolean(s.detail?.chunks?.length),
  );

  const header = (
    <>
      <IconDebug className="ask-pipeline-steps-icon" />
      <span className="ask-pipeline-steps-title">
        Pipeline trace
        <span className="ask-pipeline-steps-count">({steps.length} steps)</span>
      </span>
      <span className="ask-pipeline-usage-badges">
        {usedSql && <span className="badge">SQL</span>}
        {usedRag && !usedMcp && <span className="badge">RAG</span>}
        {usedMcp && <span className="badge">MCP</span>}
      </span>
      {isActive && <span className="ask-pipeline-steps-live">Live</span>}
      {!standalone && onOpenInTab && (
        <button
          type="button"
          className="ask-pipeline-open-tab btn btn-secondary btn-sm"
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            onOpenInTab();
          }}
        >
          Open in tab
        </button>
      )}
    </>
  );

  const stepList = (
    <ol className="ask-pipeline-steps-list">
      {steps.map((step, i) => {
        const isLast = i === steps.length - 1;
        const isCurrent = isActive && isLast;
        return (
          <li
            key={`${i}-${step.phase}-${step.message}`}
            className={`ask-pipeline-step${isCurrent ? " ask-pipeline-step--active" : ""}`}
          >
            <div className="ask-pipeline-step-row">
              <span className="ask-pipeline-step-marker" aria-hidden>
                {isCurrent ? (
                  <span className="ask-pipeline-step-pulse" />
                ) : (
                  <span className="ask-pipeline-step-check">✓</span>
                )}
              </span>
              <div className="ask-pipeline-step-body">
                <div className="ask-pipeline-step-text">
                  <span className="ask-pipeline-step-num">Step {i + 1}</span>
                  <span className="ask-pipeline-phase">{step.phase}</span>
                  {step.message}
                </div>
                {step.detail && <TraceDetail detail={step.detail} />}
              </div>
            </div>
          </li>
        );
      })}
    </ol>
  );

  if (standalone) {
    return (
      <div className="ask-pipeline-steps ask-pipeline-steps--standalone">
        <div className="ask-pipeline-steps-summary ask-pipeline-steps-summary--static">
          {header}
        </div>
        {stepList}
      </div>
    );
  }

  return (
    <details className="ask-pipeline-steps" open={isActive}>
      <summary className="ask-pipeline-steps-summary">{header}</summary>
      {stepList}
    </details>
  );
}
