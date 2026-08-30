import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { api, type McpRegistryPrompt, type McpStatusResponse } from "../api/client";
import { McpPromptEditModal } from "./McpPromptEditModal";
import { McpServersPanel } from "./McpServersPanel";

export function McpSettingsPanel({ envPath }: { envPath: string }) {
  const qc = useQueryClient();
  const [mcpUrl, setMcpUrl] = useState("http://127.0.0.1:8000/mcp");
  const [restartNeeded, setRestartNeeded] = useState(false);
  const [editingPrompt, setEditingPrompt] = useState<string | null>(null);
  const [actionNotice, setActionNotice] = useState<{ ok: boolean; text: string } | null>(null);
  const [saveNotice, setSaveNotice] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  const { data: settings } = useQuery({
    queryKey: ["settings"],
    queryFn: api.getSettings,
  });

  useEffect(() => {
    if (settings?.mcp_url) setMcpUrl(settings.mcp_url);
  }, [settings?.mcp_url]);

  const { data: status, isLoading: statusLoading, refetch: refetchStatus } = useQuery({
    queryKey: ["mcp", "status"],
    queryFn: api.mcpStatus,
    refetchInterval: 15_000,
  });

  const mcpIsRunning = Boolean(status?.reachable || (status?.listener_pids?.length ?? 0) > 0);

  const invalidateMcp = () => {
    void refetchStatus();
    void qc.invalidateQueries({ queryKey: ["mcp"] });
  };

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

  const { data: registry } = useQuery({
    queryKey: ["mcp", "registry"],
    queryFn: api.mcpRegistry,
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
  });

  const { data: log } = useQuery({
    queryKey: ["mcp", "log"],
    queryFn: () => api.mcpLog(),
    enabled: !!status?.running,
  });

  const saveMcpUrl = useMutation({
    mutationFn: () => api.saveSettings({ mcp_url: mcpUrl }),
    onSuccess: (res) => {
      qc.setQueryData(["settings"], res);
      setSaveNotice("MCP URL saved to .env.");
      setSaveError(null);
    },
    onError: (err) => {
      setSaveError(String(err));
      setSaveNotice(null);
    },
  });

  const cursorConfig = useMemo(() => {
    const servers = serversData?.servers?.filter((s) => s.enabled) ?? [];
    const mcpServers: Record<string, { url: string }> = {};
    for (const server of servers) {
      mcpServers[server.slug] = { url: server.url };
    }
    if (!Object.keys(mcpServers).length) {
      const url = status?.url ?? mcpUrl;
      mcpServers.datapro = { url };
    }
    return JSON.stringify({ mcpServers }, null, 2);
  }, [serversData?.servers, status?.url, mcpUrl]);

  return (
    <div className="space-y-4">
      {restartNeeded && (
        <RestartBanner busy={mcpBusy} running={mcpIsRunning} onRestart={() => mcpRestart.mutate()} />
      )}

      <div className="card card-pad space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="font-semibold">Built-in MCP server</h2>
            <p className="mt-1 text-sm" style={{ color: "var(--color-text-muted)" }}>
              Knowledge base search, tools, and prompts for Cursor and Claude Desktop
            </p>
          </div>
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => refetchStatus()}>
            Refresh status
          </button>
        </div>

        <BuiltInServerControls
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

        <div className="field mb-0">
          <label className="label">MCP URL</label>
          <input className="input font-mono text-xs" value={mcpUrl} onChange={(e) => setMcpUrl(e.target.value)} />
          <p className="mt-2 text-xs" style={{ color: "var(--color-text-muted)" }}>
            Used by the API and listed in client config below. Restart MCP after URL changes.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <button type="button" className="btn btn-sm" disabled={saveMcpUrl.isPending} onClick={() => saveMcpUrl.mutate()}>
            {saveMcpUrl.isPending ? "Saving…" : "Save MCP URL"}
          </button>
          <p className="text-xs" style={{ color: "var(--color-text-muted)" }}>Writes to {envPath}</p>
        </div>
        {saveNotice && <p className="alert-ok text-sm">{saveNotice}</p>}
        {saveError && <p className="alert-error text-sm">{saveError}</p>}
      </div>

      <McpServersPanel />

      <div className="card card-pad space-y-3">
        <h2 className="font-semibold">Cursor / Claude Desktop</h2>
        <p className="text-sm" style={{ color: "var(--color-text-muted)" }}>MCP client config for all enabled servers</p>
        <pre className="mcp-code-block">{cursorConfig}</pre>
      </div>

      {registry && (
        <GlobalPromptsCard prompts={registry.prompts} onEdit={(name) => setEditingPrompt(name)} />
      )}

      {log?.log && (
        <details className="card card-pad">
          <summary className="cursor-pointer font-medium">Recent server log</summary>
          <pre className="mt-3 max-h-64 overflow-auto mcp-text-faint">{log.log}</pre>
        </details>
      )}

      {registry && (
        <McpPromptEditModal
          open={editingPrompt != null}
          promptName={editingPrompt ?? ""}
          prompts={registry.prompts}
          serverReachable={!!status?.reachable}
          onClose={() => setEditingPrompt(null)}
          onSaved={() => setRestartNeeded(true)}
        />
      )}
    </div>
  );
}

function BuiltInServerControls({
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
    <div className="mcp-server-card mcp-server-card--builtin space-y-3">
      {statusLoading && <p className="mcp-text-faint text-sm">Checking…</p>}
      {status && !statusLoading && (
        <div className="flex flex-wrap items-center gap-2">
          <span className={`badge ${status.reachable ? "badge-ok" : "badge-muted"}`}>
            {status.reachable ? "Reachable" : "Stopped"}
          </span>
          <span className="badge-muted badge">{status.status_label}</span>
          {status.active_pid != null && <span className="badge-muted badge">PID {status.active_pid}</span>}
          <span className="badge-muted badge">Port {status.port}</span>
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <button type="button" className="btn btn-sm" disabled={busy || isRunning} onClick={onStart}>
          {startPending ? "Starting…" : "Start"}
        </button>
        <button type="button" className="btn btn-secondary btn-sm" disabled={busy || !isRunning} onClick={onStop}>
          {stopPending ? "Stopping…" : "Stop"}
        </button>
        <button type="button" className="btn btn-secondary btn-sm" disabled={busy || !isRunning} onClick={onRestart}>
          {restartPending ? "Restarting…" : "Restart"}
        </button>
      </div>

      {status && (
        <details className="text-sm">
          <summary className="mcp-text-faint cursor-pointer hover:opacity-80">Endpoint, registry & diagnostics</summary>
          <div className="mt-2 space-y-2 mcp-text-faint">
            <p>
              Endpoint: <code className="mcp-code-inline">{status.url}</code>
            </p>
            {capabilities && (
              <p>
                Live: {capabilities.tools.length} tools · {capabilities.resources.length} resources ·{" "}
                {capabilities.prompts.length} prompts
              </p>
            )}
            <p>
              Registry: <code>{registryPath ?? "mcp_registry.json"}</code> — restart after global prompt edits.
            </p>
            {status.source === "external" && (
              <p style={{ color: "var(--color-text-muted)" }}>External process — Stop kills port {status.port}.</p>
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
    <div className="mcp-restart-banner">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p>
          <strong>Restart required.</strong> Built-in registry prompt changes need an MCP restart.
        </p>
        <button type="button" className="btn btn-sm shrink-0" disabled={busy || !running} onClick={onRestart}>
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
        <p className="mt-1 text-sm" style={{ color: "var(--color-text-muted)" }}>
          Built-in server templates — <code className="text-xs">mcp_registry.json</code>
        </p>
      </div>
      <div className="space-y-2">
        {prompts.map((p) => (
          <div key={p.name} className="mcp-list-item mcp-list-item--row">
            <div className="min-w-0 flex-1">
              <p className="font-medium text-sm">{p.name}</p>
              <p className="mt-0.5 mcp-text-muted">{p.description}</p>
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
