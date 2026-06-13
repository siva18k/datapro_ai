import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { ApiOfflinePanel } from "../components/ApiOfflinePanel";
import { McpAddBindingModal } from "../components/McpAddBindingModal";
import { McpPromptEditModal } from "../components/McpPromptEditModal";
import { McpResourcePreviewModal } from "../components/McpResourcePreviewModal";
import { McpServersPanel } from "../components/McpServersPanel";
import { McpToolViewModal } from "../components/McpToolViewModal";
import { PageHeader } from "../components/PageHeader";
import { useApiConnection } from "../context/ApiConnectionContext";
import { api, type McpBindingItem, type McpRegistryPrompt, type McpStatusResponse } from "../api/client";

type BindingTab = "tools" | "resources" | "prompts";

const TAB_TO_TYPE: Record<BindingTab, "tool" | "resource" | "prompt"> = {
  tools: "tool",
  resources: "resource",
  prompts: "prompt",
};

export function McpPage() {
  const qc = useQueryClient();
  const { apiOnline, checking: apiChecking } = useApiConnection();
  const [domainId, setDomainId] = useState("");
  const [bindingTab, setBindingTab] = useState<BindingTab>("tools");
  const [restartNeeded, setRestartNeeded] = useState(false);
  const [editingPrompt, setEditingPrompt] = useState<string | null>(null);
  const [viewingTool, setViewingTool] = useState<string | null>(null);
  const [viewingResource, setViewingResource] = useState<McpBindingItem | null>(null);
  const [addBindingOpen, setAddBindingOpen] = useState(false);
  const [actionNotice, setActionNotice] = useState<{ ok: boolean; text: string } | null>(null);

  const { data: status, isLoading: statusLoading, refetch: refetchStatus } = useQuery({
    queryKey: ["mcp", "status"],
    queryFn: api.mcpStatus,
    enabled: apiOnline,
    refetchInterval: apiOnline ? 15_000 : false,
  });

  const mcpIsRunning = Boolean(status?.reachable || (status?.listener_pids?.length ?? 0) > 0);

  const invalidateMcp = () => {
    void refetchStatus();
    void qc.invalidateQueries({ queryKey: ["mcp"] });
  };

  const markRestartNeeded = () => setRestartNeeded(true);

  const mcpStart = useMutation({
    mutationFn: api.mcpStart,
    onSuccess: (res) => {
      invalidateMcp();
      setActionNotice({ ok: res.ok, text: res.message });
      if (res.ok) setRestartNeeded(false);
    },
    onError: (err) => setActionNotice({ ok: false, text: String(err) }),
  });

  const mcpStop = useMutation({
    mutationFn: api.mcpStop,
    onSuccess: (res) => {
      invalidateMcp();
      setActionNotice({ ok: res.ok, text: res.message });
    },
    onError: (err) => setActionNotice({ ok: false, text: String(err) }),
  });

  const mcpRestart = useMutation({
    mutationFn: api.mcpRestart,
    onSuccess: (res) => {
      invalidateMcp();
      setActionNotice({ ok: res.ok, text: res.message });
      if (res.ok) setRestartNeeded(false);
    },
    onError: (err) => setActionNotice({ ok: false, text: String(err) }),
  });

  const mcpBusy = mcpStart.isPending || mcpStop.isPending || mcpRestart.isPending;

  const { data: domains } = useQuery({
    queryKey: ["domains"],
    queryFn: api.listDomains,
    enabled: apiOnline,
  });

  const activeDomainId = domainId || domains?.[0]?.id || "";

  const { data: registry } = useQuery({
    queryKey: ["mcp", "registry"],
    queryFn: api.mcpRegistry,
    enabled: apiOnline,
  });

  const { data: capabilities } = useQuery({
    queryKey: ["mcp", "capabilities"],
    queryFn: api.mcpCapabilities,
    enabled: !!status?.reachable,
    retry: false,
  });

  const { data: serversData } = useQuery({
    queryKey: ["mcp", "servers"],
    queryFn: api.listMcpServers,
    enabled: apiOnline,
  });

  const { data: bindingCatalog } = useQuery({
    queryKey: ["mcp", "binding-catalog"],
    queryFn: api.mcpBindingCatalog,
    enabled: apiOnline,
  });

  const { data: bindings } = useQuery({
    queryKey: ["mcp", "bindings", activeDomainId],
    queryFn: () => api.mcpBindings(activeDomainId),
    enabled: !!activeDomainId,
  });

  const { data: log } = useQuery({
    queryKey: ["mcp", "log"],
    queryFn: () => api.mcpLog(),
    enabled: !!status?.running,
  });

  const boundKeys = useMemo(() => {
    const keys = new Set<string>();
    if (!bindings) return keys;
    for (const tab of ["tools", "resources", "prompts"] as const) {
      for (const item of bindings.bindings[tab]) {
        if (!item.mcp_server_id) continue;
        const type = TAB_TO_TYPE[tab];
        keys.add(`${item.mcp_server_id}:${type}:${item.name}`);
      }
    }
    return keys;
  }, [bindings]);

  const setBinding = useMutation({
    mutationFn: api.setMcpBinding,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["mcp", "bindings", activeDomainId] });
    },
  });

  const addBinding = useMutation({
    mutationFn: api.addMcpBinding,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["mcp", "bindings", activeDomainId] });
    },
  });

  const removeBinding = useMutation({
    mutationFn: api.removeMcpBinding,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["mcp", "bindings", activeDomainId] });
    },
  });

  const cursorConfig = useMemo(() => {
    const servers = serversData?.servers?.filter((s) => s.enabled) ?? [];
    const mcpServers: Record<string, { url: string }> = {};
    for (const server of servers) {
      mcpServers[server.slug] = { url: server.url };
    }
    if (!Object.keys(mcpServers).length) {
      const url = status?.url ?? "http://127.0.0.1:8000/mcp";
      mcpServers.datapro = { url };
    }
    return JSON.stringify({ mcpServers }, null, 2);
  }, [serversData?.servers, status?.url]);

  if (!apiOnline && !apiChecking) {
    return (
      <div className="mcp-page space-y-4">
        <PageHeader title="MCP Server" description="Tools for MCP clients" />
        <ApiOfflinePanel />
      </div>
    );
  }

  return (
    <div className="mcp-page space-y-4">
      <PageHeader title="MCP Server" description="Servers, domain bindings, and prompts">
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => refetchStatus()}>
          Refresh status
        </button>
      </PageHeader>

      {restartNeeded && (
        <RestartBanner busy={mcpBusy} running={mcpIsRunning} onRestart={() => mcpRestart.mutate()} />
      )}

      <div className="mcp-page-split">
        <div className="card card-pad space-y-4">
          <div>
            <h2 className="font-semibold">Domain bindings</h2>
            <p className="mt-1 text-sm text-zinc-500">
              Attach tools, resources, and prompts from any registered MCP server. Ask uses these
              bindings for the selected domain.
            </p>
          </div>
          <div className="field mb-0 max-w-xs">
            <label className="label">Domain</label>
            <select className="select" value={activeDomainId} onChange={(e) => setDomainId(e.target.value)}>
              {domains?.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          </div>

          <div className="tabs">
            {(["tools", "resources", "prompts"] as const).map((tab) => (
              <button
                key={tab}
                type="button"
                className={`tab capitalize ${bindingTab === tab ? "tab-active" : ""}`}
                onClick={() => setBindingTab(tab)}
              >
                {tab}
                {bindings && (
                  <span className="ml-1.5 text-xs opacity-70">
                    ({bindings.bindings[tab].filter((i) => i.enabled).length}/
                    {bindings.bindings[tab].length})
                  </span>
                )}
              </button>
            ))}
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs text-zinc-500">
              {bindingTab === "tools" && "Search and action tools bound to this domain."}
              {bindingTab === "resources" && "Read-only URIs included in domain context."}
              {bindingTab === "prompts" && "Prompt templates used when generating answers."}
            </p>
            <button
              type="button"
              className="btn btn-sm"
              disabled={!activeDomainId}
              onClick={() => setAddBindingOpen(true)}
            >
              Add {bindingTab.slice(0, -1)}
            </button>
          </div>

          {bindings && (
            <BindingList
              items={bindings.bindings[bindingTab]}
              showUri={bindingTab === "resources"}
              allowToolView={bindingTab === "tools"}
              allowResourcePreview={bindingTab === "resources"}
              saving={setBinding.isPending || removeBinding.isPending}
              onViewTool={(name) => setViewingTool(name)}
              onPreviewResource={(item) => setViewingResource(item)}
              onToggle={(item, enabled) =>
                setBinding.mutate({
                  domain_id: activeDomainId,
                  capability_type: TAB_TO_TYPE[bindingTab],
                  capability_name: item.name,
                  enabled,
                  mcp_server_id: item.mcp_server_id,
                })
              }
              onRemove={(item) => {
                if (item.id) removeBinding.mutate(item.id);
              }}
            />
          )}
        </div>

        <div className="space-y-4">
          <McpServersPanel />

          <BuiltInServerCard
            status={status}
            statusLoading={statusLoading}
            capabilities={capabilities}
            registryPath={registry?.registry_path}
            busy={mcpBusy}
            isRunning={mcpIsRunning}
            onStart={() => mcpStart.mutate()}
            onStop={() => mcpStop.mutate()}
            onRestart={() => mcpRestart.mutate()}
            startPending={mcpStart.isPending}
            stopPending={mcpStop.isPending}
            restartPending={mcpRestart.isPending}
            actionNotice={actionNotice}
          />

          <div className="card card-pad space-y-3">
            <h2 className="font-semibold">Cursor / Claude Desktop</h2>
            <p className="text-sm text-zinc-500">MCP client config for all enabled servers</p>
            <pre className="overflow-x-auto rounded-lg bg-zinc-900 p-4 text-xs text-zinc-100">{cursorConfig}</pre>
          </div>

          {registry && (
            <GlobalPromptsCard prompts={registry.prompts} onEdit={(name) => setEditingPrompt(name)} />
          )}
        </div>
      </div>

      <McpAddBindingModal
        open={addBindingOpen}
        tab={bindingTab}
        catalog={bindingCatalog?.servers}
        boundKeys={boundKeys}
        saving={addBinding.isPending}
        onClose={() => setAddBindingOpen(false)}
        onAdd={(serverId, capabilityName) =>
          addBinding.mutate({
            domain_id: activeDomainId,
            mcp_server_id: serverId,
            capability_type: TAB_TO_TYPE[bindingTab],
            capability_name: capabilityName,
          })
        }
      />

      {viewingResource && (
        <McpResourcePreviewModal
          open={viewingResource != null}
          resource={viewingResource}
          serverReachable={!!status?.reachable}
          onClose={() => setViewingResource(null)}
        />
      )}

      {viewingTool && (
        <McpToolViewModal open={viewingTool != null} toolName={viewingTool} onClose={() => setViewingTool(null)} />
      )}

      {registry && (
        <McpPromptEditModal
          open={editingPrompt != null}
          promptName={editingPrompt ?? ""}
          prompts={registry.prompts}
          serverReachable={!!status?.reachable}
          onClose={() => setEditingPrompt(null)}
          onSaved={markRestartNeeded}
        />
      )}

      {log?.log && (
        <details className="card card-pad">
          <summary className="cursor-pointer font-medium">Recent server log</summary>
          <pre className="mt-3 max-h-64 overflow-auto text-xs text-zinc-600">{log.log}</pre>
        </details>
      )}
    </div>
  );
}

function BuiltInServerCard({
  status,
  statusLoading,
  capabilities,
  registryPath,
  busy,
  isRunning,
  onStart,
  onStop,
  onRestart,
  startPending,
  stopPending,
  restartPending,
  actionNotice,
}: {
  status: McpStatusResponse | undefined;
  statusLoading: boolean;
  capabilities:
    | {
        tools: { name: string; description?: string }[];
        resources: { name?: string; uri?: string }[];
        prompts: { name: string; description?: string }[];
      }
    | undefined;
  registryPath: string | undefined;
  busy: boolean;
  isRunning: boolean;
  onStart: () => void;
  onStop: () => void;
  onRestart: () => void;
  startPending: boolean;
  stopPending: boolean;
  restartPending: boolean;
  actionNotice: { ok: boolean; text: string } | null;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50/90 px-3 py-2.5 space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="font-semibold">Built-in server</h2>
          <p className="mt-0.5 text-sm text-zinc-600">Knowledge base search, tools & prompts</p>
          {statusLoading && <p className="mt-1 text-xs text-zinc-500">Checking…</p>}
          {status && !statusLoading && (
            <p className={`mt-1 text-xs ${status.reachable ? "text-emerald-700" : "text-zinc-500"}`}>
              {status.reachable ? "Running" : "Stopped"}
            </p>
          )}
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          <button type="button" className="btn btn-sm" disabled={busy || isRunning} onClick={onStart}>
            {startPending ? "Starting…" : "Start"}
          </button>
          <button type="button" className="btn btn-secondary btn-sm" disabled={busy || !isRunning} onClick={onStop}>
            {stopPending ? "Stopping…" : "Stop"}
          </button>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            disabled={busy || !isRunning}
            onClick={onRestart}
          >
            {restartPending ? "Restarting…" : "Restart"}
          </button>
        </div>
      </div>

      {status && (
        <details className="text-sm">
          <summary className="cursor-pointer text-xs text-zinc-500 hover:text-zinc-700">
            Endpoint, registry & diagnostics
          </summary>
          <div className="mt-2 space-y-2 text-xs text-zinc-600">
            <p>
              Endpoint:{" "}
              <code className="rounded bg-white/80 px-1.5 py-0.5">{status.url}</code>
            </p>
            <p>
              Port {status.port}
              {status.active_pid != null && <> · PID {status.active_pid}</>}
              {status.status_label && <> · {status.status_label}</>}
            </p>
            {capabilities && (
              <p>
                Live: {capabilities.tools.length} tools · {capabilities.resources.length} resources ·{" "}
                {capabilities.prompts.length} prompts
              </p>
            )}
            <p>
              Registry: <code>{registryPath ?? "mcp_registry.json"}</code> — restart after prompt edits.
            </p>
            {status.source === "external" && (
              <p className="text-zinc-700">External process — Stop kills port {status.port}.</p>
            )}
          </div>
        </details>
      )}

      {actionNotice && (
        <p className={actionNotice.ok ? "alert-ok text-sm" : "alert-error text-sm"}>{actionNotice.text}</p>
      )}
    </div>
  );
}

function RestartBanner({
  busy,
  running,
  onRestart,
}: {
  busy: boolean;
  running: boolean;
  onRestart: () => void;
}) {
  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p>
          <strong>Restart required.</strong> Built-in registry prompt changes need an MCP restart.
        </p>
        <button
          type="button"
          className="btn btn-sm shrink-0"
          disabled={busy || !running}
          onClick={onRestart}
        >
          {busy ? "Restarting…" : "Restart MCP now"}
        </button>
      </div>
    </div>
  );
}

function GlobalPromptsCard({
  prompts,
  onEdit,
}: {
  prompts: McpRegistryPrompt[];
  onEdit: (name: string) => void;
}) {
  return (
    <div className="card card-pad space-y-4">
      <div>
        <h2 className="font-semibold">Global prompts</h2>
        <p className="mt-1 text-sm text-zinc-500">
          Built-in server templates — <code className="text-xs">mcp_registry.json</code>
        </p>
      </div>
      <div className="space-y-2">
        {prompts.map((p) => (
          <div
            key={p.name}
            className="flex flex-wrap items-start justify-between gap-3 rounded-lg border border-zinc-200 px-3 py-2.5"
          >
            <div className="min-w-0 flex-1">
              <p className="font-medium text-sm">{p.name}</p>
              <p className="mt-0.5 text-sm text-zinc-600">{p.description}</p>
              {!p.enabled && <span className="badge-muted badge mt-1 text-xs">Disabled in registry</span>}
            </div>
            <button type="button" className="btn btn-secondary btn-sm shrink-0" onClick={() => onEdit(p.name)}>
              Edit
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

function BindingList({
  items,
  showUri,
  allowToolView,
  allowResourcePreview,
  saving,
  onViewTool,
  onPreviewResource,
  onToggle,
  onRemove,
}: {
  items: McpBindingItem[];
  showUri?: boolean;
  allowToolView?: boolean;
  allowResourcePreview?: boolean;
  saving: boolean;
  onViewTool?: (name: string) => void;
  onPreviewResource?: (item: McpBindingItem) => void;
  onToggle: (item: McpBindingItem, enabled: boolean) => void;
  onRemove: (item: McpBindingItem) => void;
}) {
  if (!items.length) {
    return (
      <p className="text-sm text-zinc-500">
        No {showUri ? "resources" : allowToolView ? "tools" : "prompts"} bound yet. Use Add to attach
        capabilities from any server.
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {items.map((item) => (
        <div
          key={item.id ?? `${item.mcp_server_id}-${item.name}`}
          className="flex gap-3 rounded-lg border border-zinc-200 px-3 py-2.5 text-sm hover:bg-zinc-50"
        >
          <input
            type="checkbox"
            className="mt-0.5 shrink-0"
            checked={item.enabled}
            disabled={saving}
            onChange={(e) => onToggle(item, e.target.checked)}
            aria-label={`Enable ${item.name} for this domain`}
          />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium text-zinc-900">{item.name}</span>
              {item.server_name && (
                <span className="badge-muted badge text-xs">{item.server_name}</span>
              )}
            </div>
            {showUri && (
              <span className="mt-0.5 block truncate font-mono text-xs text-zinc-500">
                {item.uri ?? item.name}
              </span>
            )}
            {item.server_url && (
              <span className="mt-0.5 block truncate font-mono text-xs text-zinc-400">{item.server_url}</span>
            )}
          </div>
          {allowToolView && onViewTool && item.server_slug === "datapro" && (
            <button
              type="button"
              className="btn btn-secondary btn-sm shrink-0 self-center"
              onClick={() => onViewTool(item.name)}
            >
              View code
            </button>
          )}
          {allowResourcePreview && onPreviewResource && (
            <button
              type="button"
              className="btn btn-secondary btn-sm shrink-0 self-center"
              onClick={() => onPreviewResource({ ...item, uri: item.uri ?? item.name })}
            >
              Preview
            </button>
          )}
          <button
            type="button"
            className="btn btn-secondary btn-sm shrink-0 self-center"
            disabled={saving || !item.id}
            onClick={() => onRemove(item)}
          >
            Remove
          </button>
        </div>
      ))}
    </div>
  );
}
