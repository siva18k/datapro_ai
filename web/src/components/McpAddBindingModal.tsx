import { useEffect, useMemo, useState } from "react";
import type { McpBindingCatalogEntry, McpCatalogCapability } from "../api/client";

type BindingTab = "tools" | "resources" | "prompts";

const TAB_TO_TYPE: Record<BindingTab, "tool" | "resource" | "prompt"> = {
  tools: "tool",
  resources: "resource",
  prompts: "prompt",
};

const TAB_LABEL: Record<BindingTab, string> = {
  tools: "tool",
  resources: "resource",
  prompts: "prompt",
};

function capabilityKey(item: McpCatalogCapability, tab: BindingTab): string {
  if (tab === "resources" && item.uri) return item.uri;
  return item.name;
}

function isAlreadyBound(
  item: McpCatalogCapability,
  tab: BindingTab,
  serverId: string,
  boundKeys: Set<string>,
): boolean {
  const key = `${serverId}:${TAB_TO_TYPE[tab]}:${capabilityKey(item, tab)}`;
  return boundKeys.has(key);
}

export function McpAddBindingModal({
  open,
  tab,
  catalog,
  boundKeys,
  saving,
  onClose,
  onAdd,
}: {
  open: boolean;
  tab: BindingTab;
  catalog: McpBindingCatalogEntry[] | undefined;
  boundKeys: Set<string>;
  saving: boolean;
  onClose: () => void;
  onAdd: (serverId: string, capabilityName: string) => void;
}) {
  const [serverId, setServerId] = useState("");
  const activeServerId = serverId || catalog?.[0]?.server.id || "";
  const activeEntry = catalog?.find((e) => e.server.id === activeServerId);

  useEffect(() => {
    if (open) setServerId("");
  }, [open, tab]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  const items = useMemo(() => {
    if (!activeEntry) return [];
    return activeEntry[tab] ?? [];
  }, [activeEntry, tab]);

  if (!open) return null;

  return (
    <div
      className="modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="add-binding-title"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="modal-card max-w-lg">
        <div className="modal-header">
          <div>
            <h2 id="add-binding-title" className="text-lg font-semibold">
              Add {TAB_LABEL[tab]}
            </h2>
            <p className="mt-1 text-sm text-zinc-500">
              Pick a server and capability to attach to this domain.
            </p>
          </div>
          <button type="button" className="btn-ghost btn-sm shrink-0" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>

        <div className="field mb-0">
          <label className="label">MCP server</label>
          <select
            className="select"
            value={activeServerId}
            onChange={(e) => setServerId(e.target.value)}
          >
            {catalog?.map((entry) => (
              <option key={entry.server.id} value={entry.server.id}>
                {entry.server.name}
                {entry.server.is_builtin ? " (built-in)" : ` (${entry.server.server_kind})`}
                {!entry.reachable ? " — offline" : ""}
              </option>
            ))}
          </select>
        </div>

        {!catalog?.length && (
          <p className="text-sm text-zinc-500">No MCP servers registered yet.</p>
        )}

        <div className="mt-4 max-h-72 space-y-2 overflow-y-auto">
          {items.length === 0 && (
            <p className="text-sm text-zinc-500">
              {activeEntry?.reachable
                ? "No capabilities discovered on this server."
                : "Server is not reachable — showing catalog entries when available."}
            </p>
          )}
          {items.map((item) => {
            const capName = capabilityKey(item, tab);
            const bound = isAlreadyBound(item, tab, activeServerId, boundKeys);
            return (
              <div
                key={`${activeServerId}-${capName}`}
                className="mcp-list-item mcp-list-item--row"
              >
                <div className="min-w-0">
                  <p className="font-medium text-sm">{item.name}</p>
                  {tab === "resources" && item.uri && (
                    <p className="truncate font-mono text-xs text-zinc-500">{item.uri}</p>
                  )}
                  {item.description && (
                    <p className="mt-0.5 text-sm text-zinc-600">{item.description}</p>
                  )}
                </div>
                <button
                  type="button"
                  className="btn btn-sm shrink-0"
                  disabled={saving || bound}
                  onClick={() => onAdd(activeServerId, capName)}
                >
                  {bound ? "Added" : "Add"}
                </button>
              </div>
            );
          })}
        </div>

        <div className="modal-actions">
          <p className="mr-auto self-center text-xs text-zinc-500">
            Add as many as you need, then close when done.
          </p>
          <button type="button" className="btn btn-secondary btn-sm" onClick={onClose}>
            Done
          </button>
        </div>
      </div>
    </div>
  );
}
