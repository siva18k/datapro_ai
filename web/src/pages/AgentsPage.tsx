import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { AgentInstructionsEditor } from "../components/AgentInstructionsEditor";
import { AgentRunResults, useAgentRun } from "../components/AgentRunPanel";
import { AgentToolPicker } from "../components/AgentToolPicker";
import { AgentsSidebarPanel, AgentsTopSelector } from "../components/AgentsSidebarPanel";
import { ApiConnectingPanel } from "../components/ApiConnectingPanel";
import { ApiOfflinePanel } from "../components/ApiOfflinePanel";
import { PageHeader } from "../components/PageHeader";
import { api } from "../api/client";
import { useApiPageState } from "../context/ApiConnectionContext";
import { useSetSidebarContent } from "../context/SidebarContext";
import type { AgentCapabilities, AgentToolBinding } from "../types";

const DEFAULT_INSTRUCTIONS = `## Goal
Describe what this agent monitors or automates.

## Domains
Use /finance or /hr to scope catalog data.

## KPI rules
Define pass or fail criteria in plain language.

## Steps
1. Check the metric against KPI rules.
2. Generate an HTML report with tables and charts as described below.
3. Send email notification to stakeholders.

## Report output
What the HTML report should contain.

## Notifications
Who should be emailed and when.
`;

const DEFAULT_CAPS: AgentCapabilities = {
  kpi_check: true,
  generate_report: true,
  send_email: true,
  email_to: "",
};

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
    setCapabilities({ ...DEFAULT_CAPS, ...agentDetail.capabilities });
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
      });
      await api.setAgentTools(
        selectedId,
        tools.map((t) => ({ mcp_server_id: t.mcp_server_id, tool_name: t.tool_name })),
      );
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
            <p className="text-sm text-zinc-500">Select or create an agent to edit.</p>
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

                <AgentToolPicker
                  selected={tools}
                  onChange={(next) => {
                    setTools(next);
                    markDirty();
                  }}
                  disabled={saveAgent.isPending}
                />

                <fieldset className="field mb-0">
                  <legend className="label mb-2">Abilities</legend>
                  <div className="space-y-2 text-sm">
                    <label className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={!!capabilities.kpi_check}
                        onChange={(e) => {
                          setCapabilities({ ...capabilities, kpi_check: e.target.checked });
                          markDirty();
                        }}
                      />
                      Check KPI (rules in instructions)
                    </label>
                    <label className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={!!capabilities.generate_report}
                        onChange={(e) => {
                          setCapabilities({ ...capabilities, generate_report: e.target.checked });
                          markDirty();
                        }}
                      />
                      Generate HTML report
                    </label>
                    <label className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={!!capabilities.send_email}
                        onChange={(e) => {
                          setCapabilities({ ...capabilities, send_email: e.target.checked });
                          markDirty();
                        }}
                      />
                      Send email (preview only in test run)
                    </label>
                    {capabilities.send_email && (
                      <div className="field mb-0 pl-6">
                        <label className="label">Email to</label>
                        <input
                          className="input"
                          value={capabilities.email_to || ""}
                          onChange={(e) => {
                            setCapabilities({ ...capabilities, email_to: e.target.value });
                            markDirty();
                          }}
                          placeholder="team@example.com"
                        />
                      </div>
                    )}
                  </div>
                </fieldset>

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
