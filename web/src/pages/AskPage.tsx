import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { AskAgentFlowRunResult } from "../components/AskAgentFlowRunResult";
import { AskAgentRunResult } from "../components/AskAgentRunResult";
import { AskOutputChips } from "../components/AskOutputChips";
import { AskPipelineSteps } from "../components/AskPipelineSteps";
import { ChatAssistantMessage } from "../components/ChatAssistantMessage";
import type { OutputFormat } from "../components/AskOutputOptions";
import { AskPromptComposer, buildAskQuestion, type AskAttachment } from "../components/AskPromptComposer";
import { AskRetrievalPanel } from "../components/AskRetrievalPanel";
import { PageHeader } from "../components/PageHeader";
import { useSetSidebarContent } from "../context/SidebarContext";
import { api } from "../api/client";
import type { Agent, AgentFlow, AgentRunStep, AskSource, PipelineTraceStep } from "../types";
import { stripSourceCitations } from "../utils/answerDisplay";
import {
  clearPipelineTraceSession,
  openPipelineTraceTab,
  savePipelineTraceSession,
} from "../utils/pipelineTraceSession";
import { buildAskConversationHistory } from "../utils/askConversation";

interface Message {
  role: "user" | "assistant";
  content: string;
  agentName?: string;
  flowName?: string;
  agentRun?: {
    agentName: string;
    steps: AgentRunStep[];
    reportHtml?: string | null;
  };
  flowRun?: {
    flowName: string;
    steps: AgentRunStep[];
    reportHtml?: string | null;
  };
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
  selectedDomains: string[];
  debug: boolean;
  conversationHistory: { role: string; content: string }[];
}

interface AgentMutationInput {
  agent: Agent;
  extraInstructions: string;
  displayQuestion: string;
}

interface FlowMutationInput {
  flow: AgentFlow;
  extraInstructions: string;
  displayQuestion: string;
}

export function AskPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [selectedFlow, setSelectedFlow] = useState<AgentFlow | null>(null);
  const [topK, setTopK] = useState(3);
  const [selectedDomains, setSelectedDomains] = useState<string[]>([]);
  const [outputFormats, setOutputFormats] = useState<OutputFormat[]>([]);
  const [debugMode, setDebugMode] = useState(false);
  const [attachments, setAttachments] = useState<AskAttachment[]>([]);
  const messagesRef = useRef<HTMLDivElement>(null);
  const [activityStatus, setActivityStatus] = useState<string | null>(null);
  const [pipelineTrace, setPipelineTrace] = useState<PipelineTraceStep[]>([]);
  const pipelineTraceRef = useRef<PipelineTraceStep[]>([]);

  const { data: settings } = useQuery({
    queryKey: ["settings"],
    queryFn: api.getSettings,
  });
  const conversationTurns = settings?.ask?.conversation_turns ?? 5;

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
    clearPipelineTraceSession();
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
        selectedDomains={selectedDomains}
        onSelectedDomainsChange={setSelectedDomains}
        outputFormats={outputFormats}
        onOutputFormatsChange={setOutputFormats}
        debugMode={debugMode}
      />
    ),
    [topK, selectedDomains, outputFormats, debugMode],
  );
  useSetSidebarContent(sidebarPanel);

  const ask = useMutation({
    mutationFn: ({ question, topK, selectedDomains, debug, conversationHistory }: AskMutationInput) =>
      api.askStream(
        {
          question,
          top_k: topK,
          domain_overrides: selectedDomains.length ? selectedDomains : undefined,
          conversation_history: conversationHistory.length ? conversationHistory : undefined,
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

  const agentRun = useMutation({
    mutationFn: async ({ agent, extraInstructions }: AgentMutationInput) => {
      const steps: AgentRunStep[] = [];
      let reportHtml: string | null = null;

      await api.agentRunStream(
        agent.id,
        (event) => {
          if (event.type === "status" && event.message) {
            setActivityStatus(event.message);
          }
          if (event.type === "step" && event.step_id) {
            const step: AgentRunStep = {
              step_id: event.step_id,
              message: event.message || "",
              status: event.status,
              payload: event.payload,
            };
            const idx = steps.findIndex((s) => s.step_id === step.step_id);
            if (idx >= 0) steps[idx] = step;
            else steps.push(step);
            if (event.step_id === "report" && event.payload?.html) {
              reportHtml = String(event.payload.html);
            }
          }
        },
        extraInstructions.trim() ? { extra_instructions: extraInstructions } : undefined,
      );

      return { agentName: agent.name, steps: [...steps], reportHtml };
    },
    onSettled: () => setActivityStatus(null),
    onSuccess: (result) => {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "",
          agentRun: result,
        },
      ]);
    },
  });

  const flowRun = useMutation({
    mutationFn: async ({ flow, extraInstructions }: FlowMutationInput) => {
      const steps: AgentRunStep[] = [];
      let reportHtml: string | null = null;

      await api.agentFlowRunStream(
        flow.id,
        (event) => {
          if (event.type === "status" && event.message) {
            setActivityStatus(event.message);
          }
          if (event.type === "step" && event.step_id) {
            const step: AgentRunStep = {
              step_id: event.step_id,
              message: event.message || "",
              status: event.status,
              payload: event.payload,
            };
            const idx = steps.findIndex((s) => s.step_id === step.step_id);
            if (idx >= 0) steps[idx] = step;
            else steps.push(step);
            if (event.step_id.endsWith(":report") && event.payload?.html) {
              reportHtml = String(event.payload.html);
            }
          }
          if (event.type === "result" && event.payload?.report_html) {
            reportHtml = String(event.payload.report_html);
          }
        },
        extraInstructions.trim() ? { extra_instructions: extraInstructions } : undefined,
      );

      return { flowName: flow.name, steps: [...steps], reportHtml };
    },
    onSettled: () => setActivityStatus(null),
    onSuccess: (result) => {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "",
          flowRun: result,
        },
      ]);
    },
  });

  const isPending = ask.isPending || agentRun.isPending || flowRun.isPending;
  const submitError = ask.isError
    ? String(ask.error)
    : agentRun.isError
      ? String(agentRun.error)
      : flowRun.isError
        ? String(flowRun.error)
        : null;

  useEffect(() => {
    const el = messagesRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, isPending]);

  const submitQuestion = () => {
    if (isPending) return;

    if (selectedFlow) {
      const extra = buildAskQuestion(input, attachments);
      const displayQuestion = input.trim()
        ? `@@${selectedFlow.name} ${input.trim()}`
        : `@@${selectedFlow.name}`;
      setMessages((prev) => [
        ...prev,
        {
          role: "user",
          content: displayQuestion,
          flowName: selectedFlow.name,
        },
      ]);
      const flow = selectedFlow;
      setInput("");
      setAttachments([]);
      setSelectedFlow(null);
      flowRun.mutate({ flow, extraInstructions: extra, displayQuestion });
      return;
    }

    if (selectedAgent) {
      const extra = buildAskQuestion(input, attachments);
      const displayQuestion = input.trim()
        ? `@${selectedAgent.name} ${input.trim()}`
        : `@${selectedAgent.name}`;
      setMessages((prev) => [
        ...prev,
        {
          role: "user",
          content: displayQuestion,
          agentName: selectedAgent.name,
        },
      ]);
      const agent = selectedAgent;
      setInput("");
      setAttachments([]);
      setSelectedAgent(null);
      agentRun.mutate({ agent, extraInstructions: extra, displayQuestion });
      return;
    }

    const q = buildAskQuestion(input, attachments);
    if (!q) return;
    if (debugMode) resetPipelineTrace();
    const displayQuestion = input.trim();
    const conversationHistory = buildAskConversationHistory(messages, conversationTurns);
    setMessages((prev) => [...prev, { role: "user", content: displayQuestion }]);
    setInput("");
    setAttachments([]);
    ask.mutate({
      question: q,
      displayQuestion,
      topK,
      selectedDomains,
      debug: debugMode,
      conversationHistory,
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

  useEffect(() => {
    if (!debugMode) {
      clearPipelineTraceSession();
      return;
    }
    if (visiblePipelineTrace.length > 0 || ask.isPending) {
      savePipelineTraceSession({
        steps: visiblePipelineTrace,
        isActive: ask.isPending,
        updatedAt: Date.now(),
      });
    }
  }, [debugMode, visiblePipelineTrace, ask.isPending]);

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
            setSelectedAgent(null);
            setSelectedFlow(null);
          }}
        >
          New chat
        </button>
      </PageHeader>
      </div>

      <div className="card mb-4 shrink-0 md:hidden">
        <AskRetrievalPanel
          topK={topK}
          onTopKChange={setTopK}
          selectedDomains={selectedDomains}
          onSelectedDomainsChange={setSelectedDomains}
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
              <p className="mt-2">Type <code>@</code> to run an agent, <code>@@</code> to run a flow, or ask e.g. travel policy, revenue by region</p>
            </div>
          )}

          {messages.map((m, i) => {
            const displayContent =
              m.role === "assistant" && !debugMode ? stripSourceCitations(m.content) : m.content;
            return (
            <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              {m.role === "user" ? (
                <div className="chat-user">
                  {m.flowName ? (
                    <>
                      <span className="ask-user-flow-tag">@@{m.flowName}</span>
                      {m.content.replace(new RegExp(`^@@${m.flowName}\\s*`), "")}
                    </>
                  ) : m.agentName ? (
                    <>
                      <span className="ask-user-agent-tag">@{m.agentName}</span>
                      {m.content.replace(new RegExp(`^@${m.agentName}\\s*`), "")}
                    </>
                  ) : (
                    m.content
                  )}
                </div>
              ) : m.flowRun ? (
                <AskAgentFlowRunResult
                  flowName={m.flowRun.flowName}
                  steps={m.flowRun.steps}
                  reportHtml={m.flowRun.reportHtml}
                />
              ) : m.agentRun ? (
                <AskAgentRunResult
                  agentName={m.agentRun.agentName}
                  steps={m.agentRun.steps}
                  reportHtml={m.agentRun.reportHtml}
                />
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

        {isPending && (
          <div className="ask-status shrink-0">
            <div className="ask-composer-stack">
              <p className="ask-composer-status" role="status" aria-live="polite">
                {activityStatus ?? "Starting…"}
              </p>
            </div>
          </div>
        )}

        <div className="ask-composer shrink-0">
          <AskPromptComposer
            value={input}
            onChange={setInput}
            onSubmit={submitQuestion}
            isPending={isPending}
            error={submitError}
            attachments={attachments}
            onAttachmentsChange={setAttachments}
            debugMode={debugMode}
            onDebugModeChange={handleDebugModeChange}
            selectedDomains={selectedDomains}
            onSelectedDomainsChange={setSelectedDomains}
            selectedAgent={selectedAgent}
            onSelectedAgentChange={setSelectedAgent}
            selectedFlow={selectedFlow}
            onSelectedFlowChange={setSelectedFlow}
          />
        </div>
      </div>

      {debugMode && visiblePipelineTrace.length > 0 && (
        <div className="ask-pipeline-panel shrink-0">
          <AskPipelineSteps
            steps={visiblePipelineTrace}
            isActive={ask.isPending}
            onOpenInTab={() => openPipelineTraceTab(visiblePipelineTrace, ask.isPending)}
          />
        </div>
      )}
    </div>
  );
}
