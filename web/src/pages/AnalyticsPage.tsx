import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { AnalyticsDashboard } from "../components/AnalyticsDashboard";
import { AnalyticsPanel } from "../components/AnalyticsPanel";
import { AgentRunResearchView } from "../components/AgentRunResearchView";
import { PageHeader } from "../components/PageHeader";
import { useSetSidebarContent } from "../context/SidebarContext";
import { api, isAbortError } from "../api/client";
import { AskPromptComposer, buildAskQuestion, type AskAttachment } from "../components/AskPromptComposer";
import type { AnalyticsResponse, Agent, AgentFlow, AgentRunStep } from "../types";
import { buildAskConversationHistory, sessionResetTurns, shouldSendConversationHistory, type ConversationTurn } from "../utils/askConversation";
import { applyAgentRunStreamEvent, createLiveRunState, type LiveAgentRunState } from "../utils/agentRunStream";

export function AnalyticsPage() {
  const [prompt, setPrompt] = useState("");
  const [selectedDomains, setSelectedDomains] = useState<string[]>([]);
  const [dashboard, setDashboard] = useState<AnalyticsResponse | null>(null);
  const [sessionTurns, setSessionTurns] = useState<ConversationTurn[]>([]);
  const [activityStatus, setActivityStatus] = useState<string | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [selectedFlow, setSelectedFlow] = useState<AgentFlow | null>(null);
  const [attachments, setAttachments] = useState<AskAttachment[]>([]);
  const [debugMode, setDebugMode] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [liveRun, setLiveRun] = useState<LiveAgentRunState | null>(null);
  const [completedRun, setCompletedRun] = useState<{
    entityLabel: string;
    entityKind: "agent" | "flow";
    steps: AgentRunStep[];
    reportHtml: string | null;
  } | null>(null);
  const previewRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const { data: settings } = useQuery({
    queryKey: ["settings"],
    queryFn: api.getSettings,
  });
  const conversationTurns = settings?.ask?.conversation_turns ?? 5;

  const sidebarPanel = useMemo(
    () => (
      <AnalyticsPanel
        selectedDomains={selectedDomains}
        onSelectedDomainsChange={setSelectedDomains}
      />
    ),
    [selectedDomains],
  );
  useSetSidebarContent(sidebarPanel);

  useEffect(() => {
    const onChange = () => setIsFullscreen(document.fullscreenElement === previewRef.current);
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  const toggleFullscreen = async () => {
    const el = previewRef.current;
    if (!el) return;
    try {
      if (document.fullscreenElement === el) {
        await document.exitFullscreen();
      } else {
        await el.requestFullscreen();
      }
    } catch {
      /* browser may block without user gesture */
    }
  };

  const run = useMutation({
    mutationFn: ({ text, history }: { text: string; history: ConversationTurn[] }) =>
      api.analyticsStream(
        {
          prompt: text,
          domain_overrides: selectedDomains.length ? selectedDomains : undefined,
          conversation_history: history.length ? history : undefined,
        },
        (message) => setActivityStatus(message),
        abortRef.current?.signal,
      ),
    onMutate: () => setProcessing(true),
    onSettled: () => {
      setProcessing(false);
      setActivityStatus(null);
    },
    onSuccess: (res, variables) => {
      setProcessing(false);
      setDashboard(res);
      const assistantContent = res.summary?.trim() || res.title;
      const userTurn: ConversationTurn = { role: "user", content: variables.text };
      const assistantTurn: ConversationTurn = {
        role: "assistant",
        content: assistantContent,
        question: variables.text,
        sql: res.sql ?? undefined,
        columns: res.columns ?? undefined,
        rows: res.rows ?? undefined,
      };

      if (res.session_reset) {
        setSessionTurns([...sessionResetTurns(res), userTurn, assistantTurn]);
        return;
      }

      setSessionTurns((prev) => [...prev, userTurn, assistantTurn]);
    },
  });

  const agentRun = useMutation({
    mutationFn: async ({ agent, extraInstructions }: { agent: Agent; extraInstructions: string }) => {
      const steps: AgentRunStep[] = [];
      let reportHtml: string | null = null;
      await api.agentRunStream(
        agent.id,
        (event) => {
          setLiveRun((prev) => (prev ? applyAgentRunStreamEvent(prev, event) : prev));
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
        abortRef.current?.signal,
      );
      return { entityLabel: agent.name, entityKind: "agent" as const, steps: [...steps], reportHtml };
    },
    onMutate: ({ agent }) => {
      setCompletedRun(null);
      setProcessing(true);
      setLiveRun(createLiveRunState(agent.name, "agent"));
    },
    onSettled: () => {
      setProcessing(false);
      setLiveRun(null);
      setActivityStatus(null);
    },
    onSuccess: (result) => {
      setProcessing(false);
      setCompletedRun(result);
    },
  });

  const flowRun = useMutation({
    mutationFn: async ({ flow, extraInstructions }: { flow: AgentFlow; extraInstructions: string }) => {
      const steps: AgentRunStep[] = [];
      let reportHtml: string | null = null;
      await api.agentFlowRunStream(
        flow.id,
        (event) => {
          setLiveRun((prev) => (prev ? applyAgentRunStreamEvent(prev, event) : prev));
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
        abortRef.current?.signal,
      );
      return { entityLabel: flow.name, entityKind: "flow" as const, steps: [...steps], reportHtml };
    },
    onMutate: ({ flow }) => {
      setCompletedRun(null);
      setProcessing(true);
      setLiveRun(createLiveRunState(flow.name, "flow"));
    },
    onSettled: () => {
      setProcessing(false);
      setLiveRun(null);
      setActivityStatus(null);
    },
    onSuccess: (result) => {
      setProcessing(false);
      setCompletedRun(result);
    },
  });

  const isPending = run.isPending || agentRun.isPending || flowRun.isPending;
  const submitError = run.isError && !isAbortError(run.error)
    ? String(run.error)
    : agentRun.isError && !isAbortError(agentRun.error)
      ? String(agentRun.error)
      : flowRun.isError && !isAbortError(flowRun.error)
        ? String(flowRun.error)
        : null;

  const startRunAbort = () => {
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    return abortRef.current.signal;
  };

  const stopRun = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    run.reset();
    agentRun.reset();
    flowRun.reset();
    setProcessing(false);
    setActivityStatus(null);
    setLiveRun(null);
  };

  const submit = () => {
    if (isPending) return;
    startRunAbort();

    if (selectedFlow) {
      const extra = buildAskQuestion(prompt, attachments);
      setDashboard(null);
      setCompletedRun(null);
      const flow = selectedFlow;
      setPrompt("");
      setAttachments([]);
      setSelectedFlow(null);
      flowRun.mutate({ flow, extraInstructions: extra });
      return;
    }

    if (selectedAgent) {
      const extra = buildAskQuestion(prompt, attachments);
      setDashboard(null);
      setCompletedRun(null);
      const agent = selectedAgent;
      setPrompt("");
      setAttachments([]);
      setSelectedAgent(null);
      agentRun.mutate({ agent, extraInstructions: extra });
      return;
    }

    const displayText = prompt.trim();
    const text = buildAskQuestion(prompt, attachments);
    if (!text || run.isPending) return;
    setDashboard(null);
    setCompletedRun(null);
    const useFollowUp = shouldSendConversationHistory(sessionTurns, displayText);
    const history = useFollowUp
      ? buildAskConversationHistory(sessionTurns, conversationTurns)
      : [];
    if (!useFollowUp && sessionTurns.length > 0) {
      setSessionTurns([]);
    }
    run.mutate({ text, history });
  };

  const clearSession = () => {
    setDashboard(null);
    setCompletedRun(null);
    setSessionTurns([]);
    setPrompt("");
    setAttachments([]);
    setSelectedAgent(null);
    setSelectedFlow(null);
  };

  const hasSession = sessionTurns.length > 0 || Boolean(dashboard);

  return (
    <div className="analytics-page">
      <div className="shrink-0">
        <PageHeader
          title="Analytics"
          description="Explore your data intelligently"
        />
      </div>

      <div className="card mb-4 shrink-0 md:hidden">
        <AnalyticsPanel
          selectedDomains={selectedDomains}
          onSelectedDomainsChange={setSelectedDomains}
        />
      </div>

      <div className="card analytics-shell mb-0 flex min-h-0 flex-1 flex-col overflow-hidden">
        <div className="analytics-prompt-bar shrink-0 border-b">
          <div className="analytics-prompt-row">
            <div className="min-w-0 flex-1">
              <AskPromptComposer
                value={prompt}
                onChange={setPrompt}
                onSubmit={submit}
                onStop={stopRun}
                isPending={isPending}
                error={submitError}
                attachments={attachments}
                onAttachmentsChange={setAttachments}
                debugMode={debugMode}
                onDebugModeChange={setDebugMode}
                selectedDomains={selectedDomains}
                onSelectedDomainsChange={setSelectedDomains}
                selectedAgent={selectedAgent}
                onSelectedAgentChange={setSelectedAgent}
                selectedFlow={selectedFlow}
                onSelectedFlowChange={setSelectedFlow}
                showDebugToggle={false}
                showAgentFlowSelection={false}
                showDomainPillsInToolbar={true}
                submitOnEnter={false}
              />
            </div>
            {hasSession && (
              <button
                type="button"
                className="analytics-new-chat-btn self-start"
                disabled={isPending}
                onClick={clearSession}
                title="Clear follow-up context and start fresh"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
                  <path d="M12 5v14M5 12h14" />
                </svg>
                New chat
              </button>
            )}
          </div>
          {submitError && !attachments.length && <p className="alert-error mt-2">{submitError}</p>}
        </div>

        <div ref={previewRef} className="analytics-preview min-h-0 flex-1 overflow-y-auto">
          {liveRun && (
            <AgentRunResearchView
              entityLabel={liveRun.entityLabel}
              entityKind={liveRun.entityKind}
              steps={liveRun.steps}
              reportHtml={liveRun.reportHtml}
              isRunning
              statusMessage={liveRun.statusMessage}
            />
          )}
          {completedRun && !liveRun && (
            <AgentRunResearchView
              entityLabel={completedRun.entityLabel}
              entityKind={completedRun.entityKind}
              steps={completedRun.steps}
              reportHtml={completedRun.reportHtml}
              isRunning={false}
            />
          )}
          {dashboard?.session_reset && dashboard.session_summary && (
            <div className="message-bar message-bar--info m-4" role="status">
              <div className="message-bar-inner">
                <p className="message-bar-title">Previous conversation summary</p>
                <p className="message-bar-hint whitespace-pre-wrap">{dashboard.session_summary}</p>
              </div>
            </div>
          )}
          {dashboard?.session_reset && dashboard.new_topic && !dashboard.session_summary && (
            <div className="message-bar message-bar--info m-4" role="status">
              <div className="message-bar-inner">
                <p className="message-bar-hint">New topic — prior context cleared.</p>
              </div>
            </div>
          )}
          {!liveRun && !completedRun && (
            <AnalyticsDashboard
              data={dashboard}
              isRunning={run.isPending}
              activityStatus={activityStatus}
              isFullscreen={isFullscreen}
              onToggleFullscreen={dashboard ? toggleFullscreen : undefined}
            />
          )}
        </div>
      </div>
    </div>
  );
}
