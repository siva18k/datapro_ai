import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, type McpOptionalServerSpec, type McpServerRecord } from "../api/client";
import { McpEditServerModal } from "./McpEditServerModal";
import { mcpServerCardClass, mcpServerTagline } from "../utils/mcpServerUi";

export function McpServersPanel() {
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [editingServer, setEditingServer] = useState<McpServerRecord | null>(null);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [description, setDescription] = useState("");
  const [serverKind, setServerKind] = useState<"public" | "enterprise">("public");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

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
    mutationFn: ({
      id,
      data,
    }: {
      id: string;
      data: Parameters<typeof api.updateMcpServer>[1];
    }) => api.updateMcpServer(id, data),
    onSuccess: () => {
      invalidate();
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
    stopServer.isPending;

  const servers = data?.servers ?? [];
  const dismissed = data?.dismissed_optional ?? [];

  return (
    <div className="card card-pad space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-semibold">MCP servers</h2>
          <p className="mt-1 text-sm text-zinc-500">
            Start, edit, or remove servers. Use the in-app Analytics page for SQL dashboards.
          </p>
        </div>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => setShowForm((v) => !v)}>
          {showForm ? "Cancel" : "Add server"}
        </button>
      </div>

      {dismissed.length > 0 && (
        <div className="rounded-lg border border-dashed border-zinc-300 bg-zinc-50 px-3 py-3 text-sm">
          <p className="font-medium text-zinc-800">Removed integrations</p>
          <p className="mt-1 text-zinc-600">These were removed earlier and can be added back:</p>
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
          className="space-y-3 rounded-lg border border-zinc-200 p-3"
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

      {isLoading && <p className="text-sm text-zinc-500">Loading servers…</p>}

      <div className="space-y-2">
        {servers.map((server) => (
          <ServerRow
            key={server.id}
            server={server}
            busy={actionBusy}
            onEdit={() => setEditingServer(server)}
            onStart={() => startServer.mutate(server.id)}
            onStop={() => stopServer.mutate(server.id)}
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

      <McpEditServerModal
        open={editingServer != null}
        server={editingServer}
        saving={saveServer.isPending}
        onClose={() => setEditingServer(null)}
        onSave={(payload) => {
          if (!editingServer) return;
          saveServer.mutate({ id: editingServer.id, data: payload });
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
  onEdit,
  onStart,
  onStop,
  onDelete,
}: {
  server: McpServerRecord;
  busy: boolean;
  onEdit: () => void;
  onStart: () => void;
  onStop: () => void;
  onDelete: () => void;
}) {
  const canManage = Boolean(server.can_manage);
  const isRunning = Boolean(server.running || server.reachable);

  return (
    <div className={`rounded-lg border px-3 py-2.5 text-sm ${mcpServerCardClass(server)}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{server.name}</span>
            {server.is_builtin && <span className="badge-muted badge text-xs">Built-in</span>}
            {canManage && (
              <span className={`badge text-xs ${server.reachable ? "badge-ok" : "badge-muted"}`}>
                {server.reachable ? "On" : "Off"}
              </span>
            )}
          </div>
          <p className="mt-0.5 text-sm text-zinc-600">{mcpServerTagline(server)}</p>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          <button type="button" className="btn btn-secondary btn-sm" disabled={busy} onClick={onEdit}>
            Edit
          </button>
          {canManage && (
            <>
              <button type="button" className="btn btn-sm" disabled={busy || isRunning} onClick={onStart}>
                Start
              </button>
              <button type="button" className="btn btn-secondary btn-sm" disabled={busy || !isRunning} onClick={onStop}>
                Stop
              </button>
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
    </div>
  );
}
