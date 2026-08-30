import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { AgentAutoSetupPanel } from "../components/AgentAutoSetupPanel";
import { AgentInstructionsEditor } from "../components/AgentInstructionsEditor";
import { AgentRunResults, useAgentRun } from "../components/AgentRunPanel";
import { AgentsSidebarPanel, AgentsTopSelector } from "../components/AgentsSidebarPanel";
import { ApiConnectingPanel } from "../components/ApiConnectingPanel";
import { ApiOfflinePanel } from "../components/ApiOfflinePanel";
import { PageHeader } from "../components/PageHeader";
import { api } from "../api/client";
import { useApiPageState } from "../context/ApiConnectionContext";
import { useSetSidebarContent } from "../context/SidebarContext";
import type { AgentCapabilities, AgentToolBinding } from "../types";
import { inferAgentCapabilities } from "../utils/agentCapabilities";

const DEFAULT_INSTRUCTIONS = `## Goal
What should this agent find or produce? Write it in plain language.

## Domains
Type / to pin a domain (optional). Otherwise a domain is chosen from the goal, like Ask.

## Rules
Any limits — for example price above 20, last quarter only.
`;

const DEFAULT_CAPS: AgentCapabilities = inferAgentCapabilities(DEFAULT_INSTRUCTIONS);

export function AgentsPage() {
  const qc = useQueryClient();
  const { apiOnline, showConnecting, showOffline, connectingTitle } = useApiPageState();
  const [selectedId, setSelectedId] = useState<string>("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [instructions, setInstructions] = useState(DEFAULT_INSTRUCTIONS);
  const [capabilities, setCapabilities] = useState<AgentCapabilities>(DEFAULT_CAPS);
  const [tools, setTools] = useState<AgentToolBinding[]>([]);
  const [enabled, setEnabled] = useState(true);
  const [dirty, setDirty] = useState(false);

  const { data: agents, isLoading } = useQuery({
    queryKey: ["agents"],
    queryFn: api.listAgents,
    enabled: apiOnline,
  });

  const { data: agentDetail } = useQuery({
    queryKey: ["agents", selectedId],
    queryFn: () => api.getAgent(selectedId),
    enabled: apiOnline && !!selectedId,
  });

  useEffect(() => {
    if (agents?.length && !selectedId) {
      setSelectedId(agents[0].id);
    }
  }, [agents, selectedId]);

  useEffect(() => {
    if (!agentDetail) return;
    setName(agentDetail.name);
    setDescription(agentDetail.description || "");
    setInstructions(agentDetail.instructions || "");
    setCapabilities({
      ...inferAgentCapabilities(agentDetail.instructions || ""),
      ...agentDetail.capabilities,
    });
    setTools(agentDetail.tools ?? []);
    setEnabled(agentDetail.enabled);
    setDirty(false);
  }, [agentDetail?.id, agentDetail]);

  const createAgent = useMutation({
    mutationFn: () =>
      api.createAgent({
        name: "New agent",
        description: "",
        instructions: DEFAULT_INSTRUCTIONS,
        capabilities: DEFAULT_CAPS,
      }),
    onSuccess: (agent) => {
      void qc.invalidateQueries({ queryKey: ["agents"] });
      setSelectedId(agent.id);
    },
  });

  const saveAgent = useMutation({
    mutationFn: async () => {
      if (!selectedId) return;
      await api.updateAgent(selectedId, {
        name,
        description,
        instructions,
        capabilities,
        enabled,
        extra_tools: tools.map((t) => ({
          mcp_server_id: t.mcp_server_id,
          tool_name: t.tool_name,
        })),
      });
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["agents"] });
      void qc.invalidateQueries({ queryKey: ["agents", selectedId] });
      setDirty(false);
    },
  });

  const deleteAgent = useMutation({
    mutationFn: () => api.deleteAgent(selectedId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["agents"] });
      setSelectedId("");
    },
  });

  const formatInstructions = useMutation({
    mutationFn: () => api.formatAgentInstructions(selectedId, instructions),
    onSuccess: (res) => {
      setInstructions(res.markdown);
      setCapabilities((prev) => ({
        ...inferAgentCapabilities(res.markdown),
        email_to: prev.email_to,
      }));
      setDirty(true);
    },
  });

  const markDirty = () => setDirty(true);

  const agentRun = useAgentRun(selectedId);
  const runDisabled = dirty || saveAgent.isPending || agentRun.running;

  const sidebarItems = useMemo(
    () => agents?.map((agent) => ({ id: agent.id, name: agent.name, enabled: agent.enabled })),
    [agents],
  );

  const sidebarPanel = useMemo(
    () => (
      <AgentsSidebarPanel
        title="Agents"
        items={sidebarItems}
        loading={isLoading}
        selectedId={selectedId}
        onSelect={setSelectedId}
        onCreate={() => createAgent.mutate()}
        creating={createAgent.isPending}
        createLabel="+ New agent"
      />
    ),
    [sidebarItems, isLoading, selectedId, createAgent.isPending],
  );
  useSetSidebarContent(sidebarPanel);

  if (showConnecting) {
    return (
      <div className="agents-page">
        <PageHeader title="Agents" description="Automated workflows with KPI checks and reports" />
        <ApiConnectingPanel title={connectingTitle} />
      </div>
    );
  }

  if (showOffline) {
    return (
      <div className="agents-page">
        <PageHeader title="Agents" description="Automated workflows with KPI checks and reports" />
        <ApiOfflinePanel title="API server offline" />
      </div>
    );
  }

  return (
    <div className="agents-page">
      <PageHeader
        title="Agents"
        description="Define workflows — KPI checks, reports, and email previews"
      />

      <div className="agents-page-split">
        <AgentsTopSelector
          title="Agents"
          items={sidebarItems}
          loading={isLoading}
          selectedId={selectedId}
          onSelect={setSelectedId}
          onCreate={() => createAgent.mutate()}
          creating={createAgent.isPending}
          createLabel="+ New agent"
        />

        <div className="agents-editor min-w-0">
          {!selectedId && !isLoading && (
            <p className="text-sm" style={{ color: "var(--color-text-muted)" }}>Select or create an agent to edit.</p>
          )}

          {selectedId && agentDetail && (
            <>
              <div className="card card-pad space-y-4">
                <div className="agent-form-name-row">
                  <div className="field">
                    <label className="label">Name</label>
                    <input
                      className="input"
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

                <div className="field mb-0">
                  <label className="label">Short description</label>
                  <input
                    className="input"
                    value={description}
                    onChange={(e) => {
                      setDescription(e.target.value);
                      markDirty();
                    }}
                    placeholder="Weekly revenue monitor"
                  />
                </div>

                <AgentInstructionsEditor
                  value={instructions}
                  onChange={(v) => {
                    setInstructions(v);
                    setCapabilities((prev) => ({
                      ...inferAgentCapabilities(v),
                      email_to: prev.email_to,
                    }));
                    markDirty();
                  }}
                  onFormat={() => formatInstructions.mutate()}
                  formatting={formatInstructions.isPending}
                  disabled={saveAgent.isPending}
                />

                {agentDetail.domain_warnings && agentDetail.domain_warnings.length > 0 && (
                  <p className="alert-error text-sm">
                    Unknown domain slug(s): {agentDetail.domain_warnings.join(", ")}
                  </p>
                )}

                {agentDetail.mcp_kit && !dirty && (
                  <p className="text-xs" style={{ color: "var(--color-text-muted)" }}>
                    Saved MCP kit: {agentDetail.mcp_kit.tool_count ?? 0} tools,{" "}
                    {agentDetail.mcp_kit.prompt_count ?? 0} prompts,{" "}
                    {agentDetail.mcp_kit.resource_count ?? 0} resources
                    {agentDetail.mcp_kit.domain_slugs?.length
                      ? ` · /${agentDetail.mcp_kit.domain_slugs.join(" /")}`
                      : ""}
                    . Used immediately when this agent runs.
                  </p>
                )}

                <AgentAutoSetupPanel
                  capabilities={capabilities}
                  onCapabilitiesChange={(next) => {
                    setCapabilities(next);
                    markDirty();
                  }}
                  tools={tools}
                  onToolsChange={(next) => {
                    setTools(next);
                    markDirty();
                  }}
                  disabled={saveAgent.isPending}
                  mcpKit={agentDetail.mcp_kit}
                />

                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    className="btn btn-secondary"
                    disabled={runDisabled || !selectedId}
                    title={dirty ? "Save changes before running a test" : undefined}
                    onClick={() => agentRun.run()}
                  >
                    {agentRun.running ? "Running…" : "Run test"}
                  </button>
                  <button
                    type="button"
                    className="btn"
                    disabled={saveAgent.isPending || !dirty}
                    onClick={() => saveAgent.mutate()}
                  >
                    {saveAgent.isPending ? "Saving…" : "Save agent"}
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    disabled={deleteAgent.isPending}
                    onClick={() => {
                      if (window.confirm(`Delete agent "${name}"?`)) deleteAgent.mutate();
                    }}
                  >
                    Delete
                  </button>
                </div>

                {saveAgent.isSuccess && !dirty && <p className="alert-ok">Agent saved</p>}
                {saveAgent.isError && <p className="alert-error">{String(saveAgent.error)}</p>}
                {formatInstructions.isError && (
                  <p className="alert-error">{String(formatInstructions.error)}</p>
                )}
              </div>

              <AgentRunResults liveRun={agentRun.liveRun} running={agentRun.running} error={agentRun.error} />
            </>
          )}
        </div>
      </div>
    </div>
  );
}
