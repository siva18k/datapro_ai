import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AgentFlowGraphCanvas } from "../components/AgentFlowGraphCanvas";
import { AgentFlowInstructionsEditor } from "../components/AgentFlowInstructionsEditor";
import { AgentFlowRunResults, useAgentFlowRun } from "../components/AgentFlowRunPanel";
import { AgentsSidebarPanel, AgentsTopSelector } from "../components/AgentsSidebarPanel";
import { ApiConnectingPanel } from "../components/ApiConnectingPanel";
import { ApiOfflinePanel } from "../components/ApiOfflinePanel";
import { PageHeader } from "../components/PageHeader";
import { api } from "../api/client";
import { useApiPageState } from "../context/ApiConnectionContext";
import { useSetSidebarContent } from "../context/SidebarContext";
import type { Agent, AgentFlowGraph } from "../types";
import { lintAgentFlow } from "../utils/agentFlowLint";
import {
  appendNode,
  emptyAgentFlowGraph,
  parseAgentFlowSteps,
  validateAgentFlowGraph,
} from "../utils/agentFlowGraph";

const DEFAULT_INSTRUCTIONS = `Weekly view of the most expensive items for finance review. Keep amounts in USD.
`;

export function AgentFlowsPage() {
  const qc = useQueryClient();
  const { apiOnline, showConnecting, showOffline, connectingTitle } = useApiPageState();
  const [selectedId, setSelectedId] = useState<string>("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [instructions, setInstructions] = useState(DEFAULT_INSTRUCTIONS);
  const [graph, setGraph] = useState<AgentFlowGraph>(emptyAgentFlowGraph());
  const [enabled, setEnabled] = useState(true);
  const [dirty, setDirty] = useState(false);
  const [dragOverColumn, setDragOverColumn] = useState<0 | 1 | null>(null);
  const [graphError, setGraphError] = useState<string | null>(null);

  const { data: flows, isLoading } = useQuery({
    queryKey: ["agent-flows"],
    queryFn: api.listAgentFlows,
    enabled: apiOnline,
  });

  const { data: agents } = useQuery({
    queryKey: ["agents"],
    queryFn: api.listAgents,
    enabled: apiOnline,
  });

  const { data: flowDetail } = useQuery({
    queryKey: ["agent-flows", selectedId],
    queryFn: () => api.getAgentFlow(selectedId),
    enabled: apiOnline && !!selectedId,
  });

  const enabledAgents = useMemo(
    () => (agents ?? []).filter((a) => a.enabled),
    [agents],
  );

  const agentById = useMemo(() => {
    const map = new Map<string, Agent>();
    for (const a of agents ?? []) map.set(a.id, a);
    return map;
  }, [agents]);

  useEffect(() => {
    if (flows?.length && !selectedId) {
      setSelectedId(flows[0].id);
    }
  }, [flows, selectedId]);

  useEffect(() => {
    if (!flowDetail) return;
    setName(flowDetail.name);
    setDescription(flowDetail.description || "");
    setInstructions(flowDetail.instructions || "");
    setGraph(parseAgentFlowSteps(flowDetail.steps));
    setEnabled(flowDetail.enabled);
    setDirty(false);
    setGraphError(null);
  }, [flowDetail?.id, flowDetail]);

  const markDirty = () => setDirty(true);

  const updateGraph = useCallback((next: AgentFlowGraph) => {
    setGraph(next);
    setGraphError(validateAgentFlowGraph(next));
    markDirty();
  }, []);

  const addAgentToFlow = useCallback((agent: Agent, column: 0 | 1 = 0) => {
    setGraph((prev) => {
      const next = appendNode(
        prev,
        {
          id: crypto.randomUUID(),
          kind: "agent",
          agent_id: agent.id,
          column,
          agent_name: agent.name,
          agent_slug: agent.slug,
        },
        { linkFromLast: prev.nodes.length > 0 },
      );
      setGraphError(validateAgentFlowGraph(next));
      return next;
    });
    markDirty();
  }, []);

  const addTaskToFlow = useCallback((column: 0 | 1 = 0) => {
    setGraph((prev) => {
      const next = appendNode(
        prev,
        {
          id: crypto.randomUUID(),
          kind: "task",
          column,
          title: "",
          instructions: "",
        },
        { linkFromLast: prev.nodes.length > 0 },
      );
      setGraphError(validateAgentFlowGraph(next));
      return next;
    });
    markDirty();
  }, []);

  const createFlow = useMutation({
    mutationFn: () =>
      api.createAgentFlow({
        name: "New flow",
        description: "",
        instructions: DEFAULT_INSTRUCTIONS,
        steps: emptyAgentFlowGraph(),
      }),
    onSuccess: (flow) => {
      void qc.invalidateQueries({ queryKey: ["agent-flows"] });
      setSelectedId(flow.id);
    },
  });

  const saveFlow = useMutation({
    mutationFn: async () => {
      if (!selectedId) return;
      const validationError = validateAgentFlowGraph(graph);
      if (validationError) {
        throw new Error(validationError);
      }
      await api.updateAgentFlow(selectedId, {
        name,
        description,
        instructions,
        steps: {
          v: 2,
          nodes: graph.nodes.map((node) => ({
            id: node.id,
            kind: node.kind === "task" ? "task" : "agent",
            agent_id: node.agent_id,
            column: node.column ?? 0,
            title: node.title || "",
            instructions: node.instructions || "",
          })),
          edges: graph.edges.map((edge) => ({
            from: edge.from,
            to: edge.to,
            handoff: edge.handoff || "",
          })),
        },
        enabled,
      });
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["agent-flows"] });
      void qc.invalidateQueries({ queryKey: ["agent-flows", selectedId] });
      setDirty(false);
      setGraphError(null);
    },
    onError: (err) => {
      setGraphError(String(err));
    },
  });

  const deleteFlow = useMutation({
    mutationFn: () => api.deleteAgentFlow(selectedId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["agent-flows"] });
      setSelectedId("");
    },
  });

  const onDragStart = (e: React.DragEvent, agent: Agent) => {
    e.dataTransfer.setData("application/x-agent-id", agent.id);
    e.dataTransfer.effectAllowed = "copy";
  };

  const onDragStartTask = (e: React.DragEvent) => {
    e.dataTransfer.setData("application/x-flow-task", "1");
    e.dataTransfer.effectAllowed = "copy";
  };

  const lintWarnings = useMemo(
    () => lintAgentFlow(instructions, graph, enabledAgents),
    [instructions, graph, enabledAgents],
  );

  const flowRun = useAgentFlowRun(selectedId);
  const runDisabled = dirty || saveFlow.isPending || !!graphError || flowRun.running;

  const sidebarItems = useMemo(
    () => flows?.map((flow) => ({ id: flow.id, name: flow.name, enabled: flow.enabled })),
    [flows],
  );

  const sidebarPanel = useMemo(
    () => (
      <AgentsSidebarPanel
        title="Flows"
        items={sidebarItems}
        loading={isLoading}
        selectedId={selectedId}
        onSelect={setSelectedId}
        onCreate={() => createFlow.mutate()}
        creating={createFlow.isPending}
        createLabel="+ New flow"
      />
    ),
    [sidebarItems, isLoading, selectedId, createFlow.isPending],
  );
  useSetSidebarContent(sidebarPanel);

  if (showConnecting) {
    return (
      <div className="agent-flows-page">
        <PageHeader title="Agent Flows" description="Connect agents and custom steps so each one can use the previous result" />
        <ApiConnectingPanel title={connectingTitle} />
      </div>
    );
  }

  if (showOffline) {
    return (
      <div className="agent-flows-page">
        <PageHeader title="Agent Flows" description="Connect agents and custom steps so each one can use the previous result" />
        <ApiOfflinePanel />
      </div>
    );
  }

  return (
    <div className="agent-flows-page">
      <PageHeader
        title="Agent Flows"
        description="Connect agents and custom steps so each one can use the previous result"
      />

      <div className="agents-page-split">
        <AgentsTopSelector
          title="Flows"
          items={sidebarItems}
          loading={isLoading}
          selectedId={selectedId}
          onSelect={setSelectedId}
          onCreate={() => createFlow.mutate()}
          creating={createFlow.isPending}
          createLabel="+ New flow"
        />

        <main className="min-w-0 space-y-4">
          {!selectedId ? (
            <div className="card card-pad text-sm" style={{ color: "var(--color-text-muted)" }}>
              Select or create a flow to edit.
            </div>
          ) : (
            <>
              <div className="card card-pad space-y-4">
                <div className="space-y-3">
                  <div className="agent-form-name-row">
                    <div className="field">
                      <label className="label">Name</label>
                      <input
                        className="input max-w-md"
                        value={name}
                        onChange={(e) => {
                          setName(e.target.value);
                          markDirty();
                        }}
                      />
                    </div>
                    <label className="agent-form-enabled">
                      <input
                        type="checkbox"
                        checked={enabled}
                        onChange={(e) => {
                          setEnabled(e.target.checked);
                          markDirty();
                        }}
                      />
                      Enabled
                    </label>
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-medium" style={{ color: "var(--color-text-muted)" }}>
                      Description
                    </label>
                    <input
                      className="input w-full"
                      value={description}
                      onChange={(e) => {
                        setDescription(e.target.value);
                        markDirty();
                      }}
                      placeholder="Short summary of this flow"
                    />
                  </div>
                </div>

                <AgentFlowInstructionsEditor
                  value={instructions}
                  onChange={(v) => {
                    setInstructions(v);
                    markDirty();
                  }}
                  onAgentMentioned={(agent) => addAgentToFlow(agent, 0)}
                />

                <div className="agent-flow-builder">
                  <div className="agent-flow-palette">
                    <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--color-text-muted)" }}>
                      Available steps
                    </h3>
                    <p className="mb-3 text-xs" style={{ color: "var(--color-text-muted)" }}>
                      Drag onto the canvas, or double-click. Custom steps transform the previous result.
                    </p>
                    <div className="agent-flow-palette-list">
                      <div
                        className="agent-flow-agent-card agent-flow-agent-card--task"
                        draggable
                        onDragStart={onDragStartTask}
                        onDoubleClick={() => addTaskToFlow(0)}
                        title="Drag to the canvas or double-click to add"
                      >
                        <span className="agent-flow-agent-card-name">Custom step</span>
                        <span className="agent-flow-agent-card-slug">Instructions only</span>
                        <p className="agent-flow-agent-card-desc">
                          Rank, filter, format, or build HTML from the previous step’s result.
                        </p>
                      </div>
                      {enabledAgents.length === 0 && (
                        <p className="text-sm" style={{ color: "var(--color-text-muted)" }}>
                          No enabled agents. Create agents first, or use Custom step.
                        </p>
                      )}
                      {enabledAgents.map((agent) => (
                        <div
                          key={agent.id}
                          className="agent-flow-agent-card"
                          draggable
                          onDragStart={(e) => onDragStart(e, agent)}
                          onDoubleClick={() => addAgentToFlow(agent, 0)}
                          title="Drag to a column or double-click to add"
                        >
                          <span className="agent-flow-agent-card-name">{agent.name}</span>
                          <span className="agent-flow-agent-card-slug">@{agent.slug}</span>
                          {agent.description && (
                            <p className="agent-flow-agent-card-desc">{agent.description}</p>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="agent-flow-canvas">
                    <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--color-text-muted)" }}>
                      Flow steps
                    </h3>
                    <p className="mb-3 text-xs" style={{ color: "var(--color-text-muted)" }}>
                      Drag the O to connect so later steps receive prior results.
                    </p>
                    <AgentFlowGraphCanvas
                      graph={graph}
                      agentById={agentById}
                      dragOverColumn={dragOverColumn}
                      onGraphChange={updateGraph}
                      onDragOverColumn={setDragOverColumn}
                      onDropAgent={addAgentToFlow}
                      onDropTask={addTaskToFlow}
                    />
                  </div>
                </div>

                {graphError && <p className="alert-error text-sm">{graphError}</p>}
                {lintWarnings.length > 0 && (
                  <div className="alert-warn text-sm" role="status">
                    <p className="font-medium">Check before you save or run</p>
                    <ul className="mt-1 list-disc space-y-1 pl-5">
                      {lintWarnings.map((warning) => (
                        <li key={warning}>{warning}</li>
                      ))}
                    </ul>
                  </div>
                )}

                <div className="flex flex-wrap items-center gap-2 border-t pt-4" style={{ borderColor: "var(--color-border-light)" }}>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    disabled={runDisabled || !selectedId}
                    title={dirty ? "Save changes before running" : undefined}
                    onClick={() => flowRun.run()}
                  >
                    {flowRun.running ? "Running…" : "Run flow"}
                  </button>
                  <button
                    type="button"
                    className="btn btn-primary btn-sm"
                    disabled={!dirty || saveFlow.isPending || !!graphError}
                    onClick={() => saveFlow.mutate()}
                  >
                    {saveFlow.isPending ? "Saving…" : dirty ? "Save changes" : "Saved"}
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    style={{ color: "var(--color-alert-error-text)" }}
                    disabled={deleteFlow.isPending}
                    onClick={() => {
                      if (window.confirm(`Delete flow «${name}»?`)) deleteFlow.mutate();
                    }}
                  >
                    Delete
                  </button>
                </div>
              </div>

              <AgentFlowRunResults liveRun={flowRun.liveRun} running={flowRun.running} error={flowRun.error} />
            </>
          )}
        </main>
      </div>
    </div>
  );
}
