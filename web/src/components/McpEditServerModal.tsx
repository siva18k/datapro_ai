import { useEffect, useState } from "react";
import type { McpServerRecord } from "../api/client";
import { mcpServerSetupNotes } from "../utils/mcpServerUi";

export function McpEditServerModal({
  open,
  server,
  saving,
  onClose,
  onSave,
}: {
  open: boolean;
  server: McpServerRecord | null;
  saving: boolean;
  onClose: () => void;
  onSave: (data: {
    name?: string;
    url?: string;
    description?: string;
    server_kind?: "public" | "enterprise";
    transport?: string;
    enabled?: boolean;
  }) => void;
}) {
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [description, setDescription] = useState("");
  const [serverKind, setServerKind] = useState<"public" | "enterprise">("public");
  const [transport, setTransport] = useState("streamable-http");
  const [enabled, setEnabled] = useState(true);

  useEffect(() => {
    if (!open || !server) return;
    setName(server.name);
    setUrl(server.url);
    setDescription(server.description ?? "");
    setServerKind(server.server_kind === "enterprise" ? "enterprise" : "public");
    setTransport(server.transport || "streamable-http");
    setEnabled(server.enabled);
  }, [open, server]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open || !server) return null;

  const builtin = server.is_builtin;
  const setupNotes = mcpServerSetupNotes(server);

  return (
    <div
      className="modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="edit-mcp-server-title"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="modal-card max-w-lg">
        <div className="modal-header">
          <div>
            <h2 id="edit-mcp-server-title" className="text-lg font-semibold">
              {server.name}
            </h2>
            <p className="mt-1 text-sm text-zinc-500">MCP server details and settings</p>
          </div>
          <button type="button" className="btn-ghost btn-sm shrink-0" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>

        {server.can_manage && (
          <div className="mb-4 flex flex-wrap gap-2 text-xs">
            <span className={`badge ${server.reachable ? "badge-ok" : "badge-muted"}`}>
              {server.status_label ?? (server.reachable ? "Reachable" : "Stopped")}
            </span>
            {server.port != null && <span className="badge-muted badge">Port {server.port}</span>}
          </div>
        )}

        {setupNotes && (
          <div className="mb-4 mcp-themed-box text-sm whitespace-pre-wrap" style={{ color: "var(--color-text-muted)" }}>
            {setupNotes}
          </div>
        )}

        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (builtin) {
              onSave({ url: url.trim() });
              return;
            }
            if (!name.trim() || !url.trim()) return;
            onSave({
              name: name.trim(),
              url: url.trim(),
              description: description.trim(),
              server_kind: serverKind,
              transport: transport.trim() || "streamable-http",
              enabled,
            });
          }}
        >
          {!builtin && (
            <div className="field mb-0">
              <label className="label">Name</label>
              <input className="input" value={name} onChange={(e) => setName(e.target.value)} required />
            </div>
          )}

          <div className="field mb-0">
            <label className="label">Endpoint URL</label>
            <input
              className="input font-mono text-sm"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              required
            />
          </div>

          {!builtin && (
            <>
              <div className="field mb-0">
                <label className="label">Notes</label>
                <textarea
                  className="input min-h-[4rem] resize-y text-sm"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Optional notes for your team"
                />
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
              <div className="field mb-0">
                <label className="label">Transport</label>
                <input className="input" value={transport} onChange={(e) => setTransport(e.target.value)} />
              </div>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
                Enabled in catalog
              </label>
            </>
          )}

          {builtin && (
            <p className="text-xs text-zinc-500">Built-in server: only the endpoint URL can be changed here.</p>
          )}

          <div className="modal-actions">
            <button type="button" className="btn btn-secondary btn-sm" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="btn btn-sm" disabled={saving}>
              {saving ? "Saving…" : "Save changes"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
