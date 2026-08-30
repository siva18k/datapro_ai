import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { api, type McpOptionalServerSpec, type McpServerRecord } from "../api/client";
import { McpEditServerModal } from "./McpEditServerModal";
import { mcpServerCardClass, mcpServerTagline } from "../utils/mcpServerUi";

export function McpServersPanel({ envPath }: { envPath?: string }) {
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [editingServer, setEditingServer] = useState<McpServerRecord | null>(null);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [description, setDescription] = useState("");
  const [serverKind, setServerKind] = useState<"public" | "enterprise">("public");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const { data: settings } = useQuery({
    queryKey: ["settings"],
    queryFn: api.getSettings,
  });

  const { data: status } = useQuery({
    queryKey: ["mcp", "status"],
    queryFn: api.mcpStatus,
    refetchInterval: 15_000,
  });

  const { data: log } = useQuery({
    queryKey: ["mcp", "log"],
    queryFn: () => api.mcpLog(),
    enabled: Boolean(status?.running || status?.reachable),
  });

  const { data, isLoading } = useQuery({
    queryKey: ["mcp", "servers"],
    queryFn: api.listMcpServers,
    refetchInterval: (query) => {
      const servers = query.state.data?.servers ?? [];
      const pending = servers.some((s) => s.can_manage && s.running && !s.reachable);
      return pending ? 3000 : 15000;
    },
  });

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["mcp", "servers"] });
    void qc.invalidateQueries({ queryKey: ["mcp", "binding-catalog"] });
    void qc.invalidateQueries({ queryKey: ["mcp", "bindings"] });
    void qc.invalidateQueries({ queryKey: ["mcp", "status"] });
  };

  const createServer = useMutation({
    mutationFn: api.createMcpServer,
    onSuccess: () => {
      invalidate();
      setShowForm(false);
      setName("");
      setUrl("");
      setDescription("");
      setError(null);
      setNotice("MCP server added.");
    },
    onError: (err) => setError(String(err)),
  });

  const saveServer = useMutation({
    mutationFn: async ({
      id,
      data,
      persistEnvUrl,
    }: {
      id: string;
      data: Parameters<typeof api.updateMcpServer>[1];
      persistEnvUrl?: boolean;
    }) => {
      const updated = await api.updateMcpServer(id, data);
      if (persistEnvUrl && data.url) {
        await api.saveSettings({ mcp_url: data.url });
      }
      return updated;
    },
    onSuccess: () => {
      invalidate();
      void qc.invalidateQueries({ queryKey: ["settings"] });
      setEditingServer(null);
      setNotice("MCP server updated.");
      setError(null);
    },
    onError: (err) => setError(String(err)),
  });

  const deleteServer = useMutation({
    mutationFn: api.deleteMcpServer,
    onSuccess: () => {
      invalidate();
      setNotice("MCP server removed. Domain bindings for that server were deleted.");
      setError(null);
    },
    onError: (err) => {
      setError(String(err));
      setNotice(null);
    },
  });

  const restoreServer = useMutation({
    mutationFn: api.restoreMcpServer,
    onSuccess: (res) => {
      invalidate();
      setNotice(`${res.server.name} restored.`);
      setError(null);
    },
    onError: (err) => setError(String(err)),
  });

  const restartBuiltin = useMutation({
    mutationFn: api.mcpRestart,
    onSuccess: (res) => {
      invalidate();
      setNotice(res.message);
      setError(res.ok ? null : res.message);
    },
    onError: (err) => setError(String(err)),
  });

  const startServer = useMutation({
    mutationFn: api.startMcpServer,
    onSuccess: (res) => {
      invalidate();
      setNotice(res.message);
      setError(res.ok ? null : res.message);
    },
    onError: (err) => setError(String(err)),
  });

  const stopServer = useMutation({
    mutationFn: api.stopMcpServer,
    onSuccess: (res) => {
      invalidate();
      setNotice(res.message);
      setError(res.ok ? null : res.message);
    },
    onError: (err) => setError(String(err)),
  });

  const actionBusy =
    saveServer.isPending ||
    deleteServer.isPending ||
    restoreServer.isPending ||
    startServer.isPending ||
    stopServer.isPending ||
    restartBuiltin.isPending;

  const servers = data?.servers ?? [];
  const dismissed = data?.dismissed_optional ?? [];

  const cursorConfig = useMemo(() => {
    const enabled = servers.filter((s) => s.enabled);
    const mcpServers: Record<string, { url: string }> = {};
    for (const server of enabled) {
      mcpServers[server.slug] = { url: server.url };
    }
    if (!Object.keys(mcpServers).length) {
      const fallback = status?.url ?? settings?.mcp_url ?? "http://127.0.0.1:8000/mcp";
      mcpServers.datapro = { url: fallback };
    }
    return JSON.stringify({ mcpServers }, null, 2);
  }, [servers, status?.url, settings?.mcp_url]);

  return (
    <div className="space-y-3">
      <div className="card card-pad space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="font-semibold">MCP servers</h2>
            <p className="mt-1 text-sm" style={{ color: "var(--color-text-muted)" }}>
              DATA Pro is required for Ask and Analytics. Email is an optional add-on you can start or remove.
            </p>
          </div>
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => setShowForm((v) => !v)}>
            {showForm ? "Cancel" : "Add server"}
          </button>
        </div>

        {dismissed.length > 0 && (
          <div className="mcp-themed-box--dashed">
            <p className="font-medium" style={{ color: "var(--color-text)" }}>Removed integrations</p>
            <p className="mt-1 mcp-text-muted">These were removed earlier and can be added back:</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {dismissed.map((spec) => (
                <DismissedServerChip
                  key={spec.slug}
                  spec={spec}
                  busy={restoreServer.isPending}
                  onRestore={() => restoreServer.mutate(spec.slug)}
                />
              ))}
            </div>
          </div>
        )}

        {showForm && (
          <form
            className="mcp-themed-box space-y-3"
            onSubmit={(e) => {
              e.preventDefault();
              if (!name.trim() || !url.trim()) {
                setError("Name and URL are required.");
                return;
              }
              createServer.mutate({
                name: name.trim(),
                url: url.trim(),
                description: description.trim(),
                server_kind: serverKind,
              });
            }}
          >
            <div className="field mb-0">
              <label className="label">Name</label>
              <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="field mb-0">
              <label className="label">URL</label>
              <input
                className="input font-mono text-sm"
                placeholder="https://mcp.example.com/mcp"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
              />
            </div>
            <div className="field mb-0">
              <label className="label">Description</label>
              <input className="input" value={description} onChange={(e) => setDescription(e.target.value)} />
            </div>
            <div className="field mb-0">
              <label className="label">Kind</label>
              <select
                className="select"
                value={serverKind}
                onChange={(e) => setServerKind(e.target.value as "public" | "enterprise")}
              >
                <option value="public">Public</option>
                <option value="enterprise">Enterprise</option>
              </select>
            </div>
            {error && <p className="alert-error text-sm">{error}</p>}
            <button type="submit" className="btn btn-sm" disabled={createServer.isPending}>
              {createServer.isPending ? "Saving…" : "Save server"}
            </button>
          </form>
        )}

        {notice && !showForm && <p className="alert-ok text-sm whitespace-pre-wrap">{notice}</p>}
        {error && !showForm && !editingServer && <p className="alert-error text-sm whitespace-pre-wrap">{error}</p>}
        {isLoading && <p className="text-sm" style={{ color: "var(--color-text-muted)" }}>Loading servers…</p>}

        <div className="space-y-3">
          {servers.map((server) => (
            <ServerRow
              key={server.id}
              server={server}
              busy={actionBusy}
              envPath={envPath}
              savingUrl={saveServer.isPending}
              onSaveUrl={(nextUrl) =>
                saveServer.mutate({
                  id: server.id,
                  data: { url: nextUrl },
                  persistEnvUrl: server.is_builtin,
                })
              }
              onEdit={() => setEditingServer(server)}
              onStart={() => startServer.mutate(server.id)}
              onStop={() => stopServer.mutate(server.id)}
              onRestart={server.is_builtin ? () => restartBuiltin.mutate() : undefined}
              onDelete={() => {
                if (
                  !server.is_builtin &&
                  window.confirm(
                    `Remove MCP server "${server.name}"?\n\nDomain bindings that use this server will also be deleted.`,
                  )
                ) {
                  deleteServer.mutate(server.id);
                }
              }}
            />
          ))}
        </div>
      </div>

      <div className="card card-pad space-y-3">
        <h2 className="font-semibold">Cursor / Claude Desktop</h2>
        <p className="text-sm" style={{ color: "var(--color-text-muted)" }}>
          MCP client config for all enabled servers
        </p>
        <pre className="mcp-code-block">{cursorConfig}</pre>
      </div>

      {log?.log && (
        <details className="card card-pad">
          <summary className="cursor-pointer font-medium">Recent MCP server log</summary>
          <pre className="mt-3 max-h-64 overflow-auto mcp-text-faint">{log.log}</pre>
        </details>
      )}

      <McpEditServerModal
        open={editingServer != null}
        server={editingServer}
        saving={saveServer.isPending}
        onClose={() => setEditingServer(null)}
        onSave={(payload) => {
          if (!editingServer) return;
          saveServer.mutate({
            id: editingServer.id,
            data: payload,
            persistEnvUrl: editingServer.is_builtin,
          });
        }}
      />
    </div>
  );
}

function DismissedServerChip({
  spec,
  busy,
  onRestore,
}: {
  spec: McpOptionalServerSpec;
  busy: boolean;
  onRestore: () => void;
}) {
  return (
    <button type="button" className="btn btn-secondary btn-sm" disabled={busy} onClick={onRestore}>
      Restore {spec.name}
    </button>
  );
}

function ServerRow({
  server,
  busy,
  envPath,
  savingUrl,
  onSaveUrl,
  onEdit,
  onStart,
  onStop,
  onRestart,
  onDelete,
}: {
  server: McpServerRecord;
  busy: boolean;
  envPath?: string;
  savingUrl: boolean;
  onSaveUrl: (url: string) => void;
  onEdit: () => void;
  onStart: () => void;
  onStop: () => void;
  onRestart?: () => void;
  onDelete: () => void;
}) {
  const [url, setUrl] = useState(server.url);
  const canManage = Boolean(server.can_manage);
  const isRunning = Boolean(server.running || server.reachable);
  const urlDirty = url.trim() !== (server.url ?? "").trim();

  useEffect(() => {
    setUrl(server.url);
  }, [server.url]);

  return (
    <div className={mcpServerCardClass(server)}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{server.name}</span>
            {server.is_builtin ? (
              <span className="badge-muted badge text-xs">Required</span>
            ) : server.slug === "email_smtp" ? (
              <span className="badge-muted badge text-xs">Optional</span>
            ) : (
              <span className="badge-muted badge text-xs">{server.server_kind}</span>
            )}
            {canManage && (
              <span className={`badge text-xs ${server.reachable ? "badge-ok" : "badge-muted"}`}>
                {server.reachable ? "On" : "Off"}
              </span>
            )}
            {server.port != null && <span className="badge-muted badge text-xs">Port {server.port}</span>}
          </div>
          <p className="mt-0.5 mcp-text-muted">{mcpServerTagline(server)}</p>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          {!server.is_builtin && (
            <button type="button" className="btn btn-secondary btn-sm" disabled={busy} onClick={onEdit}>
              Edit
            </button>
          )}
          {canManage && (
            <>
              <button type="button" className="btn btn-sm" disabled={busy || isRunning} onClick={onStart}>
                Start
              </button>
              <button type="button" className="btn btn-secondary btn-sm" disabled={busy || !isRunning} onClick={onStop}>
                Stop
              </button>
              {onRestart && (
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  disabled={busy || !isRunning}
                  onClick={onRestart}
                >
                  Restart
                </button>
              )}
            </>
          )}
          {!server.is_builtin && (
            <button
              type="button"
              className="btn btn-secondary btn-sm text-red-700"
              disabled={busy}
              onClick={onDelete}
              aria-label={`Remove ${server.name}`}
            >
              Remove
            </button>
          )}
        </div>
      </div>

      <div className="mt-3">
        <label className="label" htmlFor={`mcp-url-${server.id}`}>
          MCP URL
        </label>
        <div className="flex flex-wrap items-center gap-2">
          <input
            id={`mcp-url-${server.id}`}
            className="input min-w-[16rem] flex-1 font-mono text-xs"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
          <button
            type="button"
            className="btn btn-sm"
            disabled={busy || !urlDirty || !url.trim()}
            onClick={() => onSaveUrl(url.trim())}
          >
            {savingUrl ? "Saving…" : "Save URL"}
          </button>
        </div>
        {server.is_builtin && envPath && (
          <p className="mt-1 text-xs" style={{ color: "var(--color-text-muted)" }}>
            Also written to MCP_URL in {envPath}. Restart after a URL change.
          </p>
        )}
      </div>
    </div>
  );
}
