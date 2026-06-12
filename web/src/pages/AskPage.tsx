import { useMutation } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { AskOutputChips } from "../components/AskOutputChips";
import { AskPipelineSteps } from "../components/AskPipelineSteps";
import { ChatAssistantMessage } from "../components/ChatAssistantMessage";
import type { OutputFormat } from "../components/AskOutputOptions";
import { AskPromptComposer, buildAskQuestion, type AskAttachment } from "../components/AskPromptComposer";
import { AskRetrievalPanel } from "../components/AskRetrievalPanel";
import { PageHeader } from "../components/PageHeader";
import { useSetSidebarContent } from "../context/SidebarContext";
import { api } from "../api/client";
import type { AskSource, PipelineTraceStep } from "../types";
import { stripSourceCitations } from "../utils/answerDisplay";

interface Message {
  role: "user" | "assistant";
  content: string;
  question?: string;
  domain_name?: string;
  query_kind?: string;
  sql?: string;
  columns?: string[];
  rows?: unknown[][];
  sources?: AskSource[];
  pipeline_trace?: PipelineTraceStep[];
}

interface AskMutationInput {
  question: string;
  displayQuestion: string;
  topK: number;
  domainOverride: string;
  debug: boolean;
}

export function AskPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [topK, setTopK] = useState(3);
  const [domainOverride, setDomainOverride] = useState("");
  const [outputFormats, setOutputFormats] = useState<OutputFormat[]>([]);
  const [debugMode, setDebugMode] = useState(false);
  const [attachments, setAttachments] = useState<AskAttachment[]>([]);
  const messagesRef = useRef<HTMLDivElement>(null);
  const [activityStatus, setActivityStatus] = useState<string | null>(null);
  const [pipelineTrace, setPipelineTrace] = useState<PipelineTraceStep[]>([]);
  const pipelineTraceRef = useRef<PipelineTraceStep[]>([]);

  const appendPipelineTrace = (step: PipelineTraceStep) => {
    const prev = pipelineTraceRef.current;
    const last = prev[prev.length - 1];
    if (last?.message === step.message && last?.phase === step.phase) return;
    const next = [...prev, step];
    pipelineTraceRef.current = next;
    setPipelineTrace(next);
  };

  const resetPipelineTrace = () => {
    pipelineTraceRef.current = [];
    setPipelineTrace([]);
  };

  const handleDebugModeChange = (enabled: boolean) => {
    setDebugMode(enabled);
    if (!enabled) resetPipelineTrace();
  };

  const sidebarPanel = useMemo(
    () => (
      <AskRetrievalPanel
        topK={topK}
        onTopKChange={setTopK}
        domainOverride={domainOverride}
        onDomainOverrideChange={setDomainOverride}
        outputFormats={outputFormats}
        onOutputFormatsChange={setOutputFormats}
        debugMode={debugMode}
      />
    ),
    [topK, domainOverride, outputFormats, debugMode],
  );
  useSetSidebarContent(sidebarPanel);

  const ask = useMutation({
    mutationFn: ({ question, topK, domainOverride, debug }: AskMutationInput) =>
      api.askStream(
        {
          question,
          top_k: topK,
          domain_override: domainOverride || undefined,
          debug,
        },
        (message) => setActivityStatus(message),
        debug ? (step) => appendPipelineTrace(step) : undefined,
      ),
    onSettled: () => setActivityStatus(null),
    onError: (_err, variables) => {
      if (variables.debug) {
        appendPipelineTrace({
          message: "Request failed — see error above",
          phase: "output",
        });
      }
    },
    onSuccess: (res, variables) => {
      const completedTrace = variables.debug ? [...pipelineTraceRef.current] : undefined;
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: res.answer,
          question: res.question ?? variables.displayQuestion,
          domain_name: res.domain_name,
          query_kind: res.query_kind,
          sql: res.sql,
          columns: res.columns,
          rows: res.rows,
          sources: res.sources,
          pipeline_trace: completedTrace,
        },
      ]);
    },
  });

  useEffect(() => {
    const el = messagesRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, ask.isPending]);

  const submitQuestion = () => {
    const q = buildAskQuestion(input, attachments);
    if (!q || ask.isPending) return;
    if (debugMode) resetPipelineTrace();
    const displayQuestion = input.trim();
    setMessages((prev) => [...prev, { role: "user", content: displayQuestion }]);
    setInput("");
    setAttachments([]);
    ask.mutate({
      question: q,
      displayQuestion,
      topK,
      domainOverride,
      debug: debugMode,
    });
  };

  const lastAssistantTrace = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i];
      if (m.role === "assistant" && m.pipeline_trace?.length) return m.pipeline_trace;
    }
    return [];
  }, [messages]);

  const visiblePipelineTrace = ask.isPending ? pipelineTrace : lastAssistantTrace;

  return (
    <div className="ask-page">
      <div className="shrink-0">
      <PageHeader title="Ask" description="Q&A across domains">
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          onClick={() => {
            setMessages([]);
            resetPipelineTrace();
          }}
        >
          New chat
        </button>
      </PageHeader>
      </div>

      {/* Mobile: retrieval settings inline (desktop uses left sidebar) */}
      <div className="card mb-4 shrink-0 md:hidden">
        <AskRetrievalPanel
          topK={topK}
          onTopKChange={setTopK}
          domainOverride={domainOverride}
          onDomainOverrideChange={setDomainOverride}
          outputFormats={outputFormats}
          onOutputFormatsChange={setOutputFormats}
          debugMode={debugMode}
        />
      </div>

      <div className="card ask-chat flex min-h-0 flex-1 flex-col overflow-hidden">
        <div ref={messagesRef} className="ask-messages min-h-0 flex-1 space-y-4 overflow-y-auto">
          {messages.length === 0 && (
            <div className="py-16 text-center text-sm text-zinc-500">
              <p className="font-medium text-zinc-700">Ask a question</p>
              <p className="mt-2">e.g. travel policy, revenue by region</p>
            </div>
          )}

          {messages.map((m, i) => {
            const displayContent =
              m.role === "assistant" && !debugMode ? stripSourceCitations(m.content) : m.content;
            return (
            <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              {m.role === "user" ? (
                <div className="chat-user">{m.content}</div>
              ) : (
                <div>
                  <ChatAssistantMessage
                    content={displayContent}
                    rowCount={m.rows?.length}
                    exportPayload={{
                      question: m.question ?? "",
                      answer: displayContent,
                      domain_name: m.domain_name,
                      sql: m.sql,
                      columns: m.columns,
                      rows: m.rows,
                    }}
                  />
                  <div className="mt-2 flex flex-wrap gap-2">
                    {m.domain_name && <span className="badge">Domain: {m.domain_name}</span>}
                    {m.query_kind === "structured" && <span className="badge">SQL</span>}
                  </div>
                  {m.role === "assistant" && outputFormats.length > 0 && (
                    <AskOutputChips
                      formats={outputFormats}
                      payload={{
                        question: m.question ?? "",
                        answer: displayContent,
                        domain_name: m.domain_name,
                        sql: m.sql,
                        columns: m.columns,
                        rows: m.rows,
                      }}
                    />
                  )}
                  {debugMode && m.sources && m.sources.length > 0 && (
                    <details className="mt-2 text-xs text-zinc-500">
                      <summary className="cursor-pointer font-medium">Sources ({m.sources.length})</summary>
                      <ul className="mt-2 space-y-2 rounded-lg bg-zinc-50 p-3">
                        {m.sources.map((s, j) => (
                          <li key={j}>
                            <strong>{s.source}</strong> · {s.chunk_id}
                            {s.text && (
                              <p className="mt-1 whitespace-pre-wrap text-zinc-600">{s.text.slice(0, 280)}{s.text.length > 280 ? "…" : ""}</p>
                            )}
                          </li>
                        ))}
                      </ul>
                    </details>
                  )}
                </div>
              )}
            </div>
          );
          })}
        </div>

        {ask.isPending && (
          <div className="ask-status shrink-0">
            <div className="ask-composer-stack">
              <p className="ask-composer-status" role="status" aria-live="polite">
                {activityStatus ?? "Starting…"}
              </p>
            </div>
          </div>
        )}

        <div className="ask-composer shrink-0 border-t border-zinc-100">
          <AskPromptComposer
            value={input}
            onChange={setInput}
            onSubmit={submitQuestion}
            isPending={ask.isPending}
            error={ask.isError ? String(ask.error) : null}
            attachments={attachments}
            onAttachmentsChange={setAttachments}
            debugMode={debugMode}
            onDebugModeChange={handleDebugModeChange}
          />
        </div>
      </div>

      {debugMode && visiblePipelineTrace.length > 0 && (
        <div className="ask-pipeline-panel shrink-0">
          <AskPipelineSteps steps={visiblePipelineTrace} isActive={ask.isPending} />
        </div>
      )}
    </div>
  );
}
