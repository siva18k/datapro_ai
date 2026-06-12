import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { ApiOfflinePanel } from "../components/ApiOfflinePanel";
import { McpPromptEditModal } from "../components/McpPromptEditModal";
import { McpResourcePreviewModal } from "../components/McpResourcePreviewModal";
import { McpToolViewModal } from "../components/McpToolViewModal";
import { PageHeader } from "../components/PageHeader";
import { useApiConnection } from "../context/ApiConnectionContext";
import { api, type McpBindingItem, type McpRegistryPrompt } from "../api/client";

type BindingTab = "tools" | "resources" | "prompts";

export function McpPage() {
  const qc = useQueryClient();
  const { apiOnline, checking: apiChecking } = useApiConnection();
  const [domainId, setDomainId] = useState("");
  const [bindingTab, setBindingTab] = useState<BindingTab>("tools");
  const [restartNeeded, setRestartNeeded] = useState(false);
  const [editingPrompt, setEditingPrompt] = useState<string | null>(null);
  const [viewingTool, setViewingTool] = useState<string | null>(null);
  const [viewingResource, setViewingResource] = useState<McpBindingItem | null>(null);
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

  const setBinding = useMutation({
    mutationFn: api.setMcpBinding,
    onSuccess: () => {
      markRestartNeeded();
      void qc.invalidateQueries({ queryKey: ["mcp", "bindings", activeDomainId] });
    },
  });

  const cursorConfig = useMemo(() => {
    const url = status?.url ?? "http://127.0.0.1:8000/mcp";
    return JSON.stringify({ mcpServers: { datapro: { url } } }, null, 2);
  }, [status?.url]);

  if (!apiOnline && !apiChecking) {
    return (
      <div className="mcp-page space-y-4">
        <PageHeader
          title="MCP Server"
          description="Tools for MCP clients"
        />
        <ApiOfflinePanel />
      </div>
    );
  }

  return (
    <div className="mcp-page space-y-4">
      <PageHeader
        title="MCP Server"
        description="Server, prompts, and bindings"
      >
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => refetchStatus()}>
          Refresh status
        </button>
      </PageHeader>

      {restartNeeded && (
        <RestartBanner
          busy={mcpBusy}
          running={mcpIsRunning}
          onRestart={() => mcpRestart.mutate()}
        />
      )}

      <div className="mcp-page-split">
        <div className="card card-pad space-y-4">
          <div>
            <h2 className="font-semibold">Domain bindings</h2>
            <p className="mt-1 text-sm text-zinc-500">Per-domain access — restart MCP to apply.</p>
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
                    ({bindings.bindings[tab].filter((i) => i.enabled).length}/{bindings.bindings[tab].length})
                  </span>
                )}
              </button>
            ))}
          </div>

          {bindingTab === "tools" && (
            <p className="text-xs text-zinc-500">Global handlers — bindings enable per domain.</p>
          )}

          {bindingTab === "resources" && (
            <p className="text-xs text-zinc-500">Read-only URIs — use Preview to fetch content.</p>
          )}

          {bindingTab === "prompts" && (
            <p className="text-xs text-zinc-500">Edit wording in Global prompts.</p>
          )}

          {bindings && (
            <BindingList
              items={bindings.bindings[bindingTab]}
              showUri={bindingTab === "resources"}
              allowToolView={bindingTab === "tools"}
              allowResourcePreview={bindingTab === "resources"}
              saving={setBinding.isPending}
              onViewTool={(name) => setViewingTool(name)}
              onPreviewResource={(item) => setViewingResource(item)}
              onToggle={(name, enabled) =>
                setBinding.mutate({
                  domain_id: activeDomainId,
                  capability_type: bindingTab === "tools" ? "tool" : bindingTab === "resources" ? "resource" : "prompt",
                  capability_name: name,
                  enabled,
                })
              }
            />
          )}
        </div>

        <div className="space-y-4">
          <div className="card card-pad space-y-3">
            <h2 className="font-semibold">Server</h2>
            {statusLoading && <p className="text-sm text-zinc-500">Checking server…</p>}
            {status && (
              <>
                <div className="flex flex-wrap gap-2">
                  <span className={`badge ${status.reachable ? "badge-ok" : "badge-muted"}`}>
                    {status.reachable ? "Reachable" : "Stopped"}
                  </span>
                  <span className="badge-muted badge">{status.status_label}</span>
                  {status.active_pid != null && <span className="badge-muted badge">PID {status.active_pid}</span>}
                  <span className="badge-muted badge">Port {status.port}</span>
                  {capabilities && (
                    <span className="badge-muted badge">
                      Live: {capabilities.tools.length} tools · {capabilities.resources.length} resources ·{" "}
                      {capabilities.prompts.length} prompts
                    </span>
                  )}
                </div>
                <p className="text-sm">
                  Endpoint:{" "}
                  <code className="rounded bg-zinc-100 px-1.5 py-0.5 text-xs">{status.url}</code>
                </p>
                <p className="text-xs text-zinc-500">
                  Registry: <code className="text-xs">{registry?.registry_path ?? "mcp_registry.json"}</code> — restart to apply changes.
                </p>
                {status.source === "external" && (
                  <p className="text-sm text-zinc-600">External process — Stop kills port {status.port}.</p>
                )}
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    className="btn btn-sm"
                    disabled={mcpBusy || mcpIsRunning}
                    onClick={() => mcpStart.mutate()}
                  >
                    {mcpStart.isPending ? "Starting…" : "Start"}
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    disabled={mcpBusy || !mcpIsRunning}
                    onClick={() => mcpStop.mutate()}
                  >
                    {mcpStop.isPending ? "Stopping…" : "Stop"}
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    disabled={mcpBusy || !mcpIsRunning}
                    onClick={() => mcpRestart.mutate()}
                  >
                    {mcpRestart.isPending ? "Restarting…" : "Restart"}
                  </button>
                </div>
              </>
            )}
            {actionNotice && (
              <p className={actionNotice.ok ? "alert-ok text-sm" : "alert-error text-sm"}>{actionNotice.text}</p>
            )}
          </div>

          <div className="card card-pad space-y-3">
            <h2 className="font-semibold">Cursor / Claude Desktop</h2>
            <p className="text-sm text-zinc-500">MCP client config</p>
            <pre className="overflow-x-auto rounded-lg bg-zinc-900 p-4 text-xs text-zinc-100">{cursorConfig}</pre>
          </div>

          {registry && (
            <GlobalPromptsCard prompts={registry.prompts} onEdit={(name) => setEditingPrompt(name)} />
          )}
        </div>
      </div>

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
          <strong>Restart required.</strong> Saved changes need an MCP restart.
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
          Shared across domains — <code className="text-xs">mcp_registry.json</code>
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
}: {
  items: McpBindingItem[];
  showUri?: boolean;
  allowToolView?: boolean;
  allowResourcePreview?: boolean;
  saving: boolean;
  onViewTool?: (name: string) => void;
  onPreviewResource?: (item: McpBindingItem) => void;
  onToggle: (name: string, enabled: boolean) => void;
}) {
  if (!items.length) {
    return <p className="text-sm text-zinc-500">No capabilities in this category.</p>;
  }

  return (
    <div className="space-y-2">
      {items.map((item) => (
        <div
          key={item.name}
          className="flex gap-3 rounded-lg border border-zinc-200 px-3 py-2.5 text-sm hover:bg-zinc-50"
        >
          <input
            type="checkbox"
            className="mt-0.5 shrink-0"
            checked={item.enabled}
            disabled={saving}
            onChange={(e) => onToggle(item.name, e.target.checked)}
            aria-label={`Enable ${item.name} for this domain`}
          />
          <div className="min-w-0 flex-1">
            <span className="font-medium text-zinc-900">{item.name}</span>
            {showUri && item.uri && (
              <span className="mt-0.5 block truncate font-mono text-xs text-zinc-500">{item.uri}</span>
            )}
            {item.description && <span className="mt-1 block text-zinc-600">{item.description}</span>}
          </div>
          {allowToolView && onViewTool && (
            <button
              type="button"
              className="btn btn-secondary btn-sm shrink-0 self-center"
              onClick={() => onViewTool(item.name)}
            >
              View code
            </button>
          )}
          {allowResourcePreview && onPreviewResource && item.uri && (
            <button
              type="button"
              className="btn btn-secondary btn-sm shrink-0 self-center"
              onClick={() => onPreviewResource(item)}
            >
              Preview
            </button>
          )}
        </div>
      ))}
    </div>
  );
}
