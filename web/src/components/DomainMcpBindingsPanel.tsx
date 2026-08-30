import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api, type DomainPrompt, type McpBindingItem } from "../api/client";
import { bindingCapabilityName, isLocalPromptBinding } from "../utils/mcpBindingUi";
import { expandMcpResourceUri } from "../utils/mcpServerUi";
import { McpAddBindingModal } from "./McpAddBindingModal";
import { McpAddPromptModal } from "./McpAddPromptModal";
import { McpLocalPromptEditModal } from "./McpLocalPromptEditModal";
import { McpPromptPreviewModal } from "./McpPromptPreviewModal";
import { McpResourcePreviewModal } from "./McpResourcePreviewModal";
import { McpToolViewModal } from "./McpToolViewModal";

type BindingTab = "tools" | "resources" | "prompts";

const TAB_TO_TYPE: Record<BindingTab, "tool" | "resource" | "prompt"> = {
  tools: "tool",
  resources: "resource",
  prompts: "prompt",
};

export function DomainMcpBindingsPanel({
  domainId,
  domainName,
  domainSlug,
  defaultExpanded = false,
}: {
  domainId: string;
  domainName?: string | null;
  domainSlug?: string | null;
  defaultExpanded?: boolean;
}) {
  const qc = useQueryClient();
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [bindingTab, setBindingTab] = useState<BindingTab>("tools");
  const [viewingTool, setViewingTool] = useState<string | null>(null);
  const [viewingResource, setViewingResource] = useState<McpBindingItem | null>(null);
  const [viewingPrompt, setViewingPrompt] = useState<McpBindingItem | null>(null);
  const [editingLocalPrompt, setEditingLocalPrompt] = useState<DomainPrompt | null>(null);
  const [addBindingOpen, setAddBindingOpen] = useState(false);

  const { data: status } = useQuery({
    queryKey: ["mcp", "status"],
    queryFn: api.mcpStatus,
  });

  const { data: registry } = useQuery({
    queryKey: ["mcp", "registry"],
    queryFn: api.mcpRegistry,
  });

  const { data: bindingCatalog } = useQuery({
    queryKey: ["mcp", "binding-catalog"],
    queryFn: api.mcpBindingCatalog,
  });

  const { data: bindings } = useQuery({
    queryKey: ["mcp", "bindings", domainId],
    queryFn: () => api.mcpBindings(domainId),
    enabled: !!domainId && expanded,
  });

  const { data: localPrompts } = useQuery({
    queryKey: ["domains", domainId, "prompts"],
    queryFn: () => api.listDomainPrompts(domainId),
    enabled: !!domainId && expanded,
  });

  const boundKeys = useMemo(() => {
    const keys = new Set<string>();
    if (!bindings) return keys;
    for (const tab of ["tools", "resources", "prompts"] as const) {
      for (const item of bindings.bindings[tab]) {
        if (!item.mcp_server_id) continue;
        const type = TAB_TO_TYPE[tab];
        keys.add(`${item.mcp_server_id}:${type}:${bindingCapabilityName(item)}`);
      }
    }
    return keys;
  }, [bindings]);

  const setBinding = useMutation({
    mutationFn: api.setMcpBinding,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["mcp", "bindings", domainId] });
    },
  });

  const addBinding = useMutation({
    mutationFn: api.addMcpBinding,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["mcp", "bindings", domainId] });
      void qc.invalidateQueries({ queryKey: ["domains", domainId, "prompts"] });
    },
  });

  const removeBinding = useMutation({
    mutationFn: api.removeMcpBinding,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["mcp", "bindings", domainId] });
    },
  });

  const bindingBusy = setBinding.isPending || removeBinding.isPending || addBinding.isPending;
  const enabledCounts = bindings
    ? {
        tools: bindings.bindings.tools.filter((i) => i.enabled).length,
        resources: bindings.bindings.resources.filter((i) => i.enabled).length,
        prompts: bindings.bindings.prompts.filter((i) => i.enabled).length,
      }
    : null;
  const totalBound =
    (enabledCounts?.tools ?? 0) + (enabledCounts?.resources ?? 0) + (enabledCounts?.prompts ?? 0);

  return (
    <div className="catalog-domain-mcp">
      <button
        type="button"
        className="catalog-domain-mcp-toggle"
        onClick={() => setExpanded((open) => !open)}
        aria-expanded={expanded}
      >
        <span className="font-medium">MCP bindings</span>
        <span className="text-sm" style={{ color: "var(--color-text-muted)" }}>
          {totalBound > 0 ? `${totalBound} enabled` : "Tools, resources, and prompts for Ask"}
        </span>
        <span className="catalog-domain-mcp-chevron" aria-hidden="true">
          {expanded ? "▲" : "▼"}
        </span>
      </button>

      {expanded && (
        <div className="catalog-domain-mcp-body space-y-4">
          <p className="text-sm" style={{ color: "var(--color-text-muted)" }}>
            Attach MCP capabilities used when answering questions in{" "}
            <strong>{domainName ?? "this domain"}</strong>. Manage servers under Settings → Servers.
            Browse the full catalog under Settings → MCP.
          </p>

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

          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs" style={{ color: "var(--color-text-muted)" }}>
              {bindingTab === "tools" && "Search and action tools bound to this domain."}
              {bindingTab === "resources" && "Read-only URIs included in domain context."}
              {bindingTab === "prompts" && "Prompt templates used when generating answers."}
            </p>
            <button type="button" className="btn btn-sm" onClick={() => setAddBindingOpen(true)}>
              Add {bindingTab.slice(0, -1)}
            </button>
          </div>

          {bindings && (
            <BindingList
              items={bindings.bindings[bindingTab]}
              showUri={bindingTab === "resources"}
              domainSlug={bindingTab === "resources" ? domainSlug : null}
              allowToolView={bindingTab === "tools"}
              allowResourcePreview={bindingTab === "resources"}
              allowPromptPreview={bindingTab === "prompts"}
              saving={bindingBusy}
              onViewTool={(name) => setViewingTool(name)}
              onPreviewResource={(item) => setViewingResource(item)}
              onPreviewPrompt={(item) => setViewingPrompt(item)}
              onEditLocalPrompt={(item) => {
                const localId = item.local_prompt_id;
                const slug = item.local_slug;
                const found =
                  (localId && localPrompts?.find((p) => p.id === localId)) ||
                  (slug && localPrompts?.find((p) => p.slug === slug));
                if (found) setEditingLocalPrompt(found);
              }}
              onToggle={(item, enabled) =>
                setBinding.mutate({
                  domain_id: domainId,
                  capability_type: TAB_TO_TYPE[bindingTab],
                  capability_name: bindingCapabilityName(item),
                  enabled,
                  mcp_server_id: item.mcp_server_id,
                })
              }
              onRemove={(item) => {
                if (item.id) removeBinding.mutate(item.id);
              }}
            />
          )}

          {bindingTab === "prompts" ? (
            <McpAddPromptModal
              open={addBindingOpen}
              domainId={domainId}
              catalog={bindingCatalog?.servers}
              registryPrompts={registry?.prompts}
              boundKeys={boundKeys}
              saving={addBinding.isPending}
              onClose={() => setAddBindingOpen(false)}
              onAddGlobal={(serverId, capabilityName) =>
                addBinding.mutate({
                  domain_id: domainId,
                  mcp_server_id: serverId,
                  capability_type: "prompt",
                  capability_name: capabilityName,
                })
              }
            />
          ) : (
            <McpAddBindingModal
              open={addBindingOpen}
              tab={bindingTab}
              catalog={bindingCatalog?.servers}
              boundKeys={boundKeys}
              saving={addBinding.isPending}
              onClose={() => setAddBindingOpen(false)}
              onAdd={(serverId, capabilityName) =>
                addBinding.mutate({
                  domain_id: domainId,
                  mcp_server_id: serverId,
                  capability_type: TAB_TO_TYPE[bindingTab],
                  capability_name: capabilityName,
                })
              }
            />
          )}

          {editingLocalPrompt && (
            <McpLocalPromptEditModal
              open={editingLocalPrompt != null}
              domainId={domainId}
              prompt={editingLocalPrompt}
              onClose={() => setEditingLocalPrompt(null)}
            />
          )}

          {viewingPrompt && (
            <McpPromptPreviewModal
              open={viewingPrompt != null}
              prompt={viewingPrompt}
              serverReachable={!!status?.reachable}
              domainId={domainId}
              domainName={domainName}
              onClose={() => setViewingPrompt(null)}
            />
          )}

          {viewingResource && (
            <McpResourcePreviewModal
              open={viewingResource != null}
              resource={viewingResource}
              serverReachable={!!status?.reachable}
              domainSlug={domainSlug}
              domainId={domainId}
              onClose={() => setViewingResource(null)}
            />
          )}

          {viewingTool && (
            <McpToolViewModal open={viewingTool != null} toolName={viewingTool} onClose={() => setViewingTool(null)} />
          )}
        </div>
      )}
    </div>
  );
}

function BindingList({
  items,
  showUri,
  domainSlug,
  allowToolView,
  allowResourcePreview,
  allowPromptPreview,
  saving,
  onViewTool,
  onPreviewResource,
  onPreviewPrompt,
  onEditLocalPrompt,
  onToggle,
  onRemove,
}: {
  items: McpBindingItem[];
  showUri?: boolean;
  domainSlug?: string | null;
  allowToolView?: boolean;
  allowResourcePreview?: boolean;
  allowPromptPreview?: boolean;
  saving: boolean;
  onViewTool?: (name: string) => void;
  onPreviewResource?: (item: McpBindingItem) => void;
  onPreviewPrompt?: (item: McpBindingItem) => void;
  onEditLocalPrompt?: (item: McpBindingItem) => void;
  onToggle: (item: McpBindingItem, enabled: boolean) => void;
  onRemove: (item: McpBindingItem) => void;
}) {
  if (!items.length) {
    return (
      <p className="text-sm" style={{ color: "var(--color-text-muted)" }}>
        No{" "}
        {showUri ? "resources" : allowToolView ? "tools" : allowPromptPreview ? "prompts" : "items"} bound yet. Use
        Add to attach capabilities from any server.
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {items.map((item) => {
        const capName = bindingCapabilityName(item);
        const localPrompt = isLocalPromptBinding(item);
        return (
          <div key={item.id ?? `${item.mcp_server_id}-${capName}`} className="mcp-list-item mcp-list-item--interactive">
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
                <span className="font-medium">{item.name}</span>
                {allowPromptPreview && (
                  <span className="badge-muted badge text-xs">{localPrompt ? "Local" : "Global"}</span>
                )}
                {item.server_name && <span className="badge-muted badge text-xs">{item.server_name}</span>}
              </div>
              {localPrompt && <span className="mt-0.5 block truncate font-mono mcp-text-faint">{capName}</span>}
              {item.description && allowPromptPreview && (
                <span className="mt-0.5 block text-sm mcp-text-muted">{item.description}</span>
              )}
              {showUri && (
                <span className="mt-0.5 block truncate font-mono mcp-text-faint">
                  {expandMcpResourceUri(item.uri ?? item.name, domainSlug ? { domain: domainSlug } : {})}
                </span>
              )}
              {item.server_url && !localPrompt && (
                <span className="mt-0.5 block truncate font-mono mcp-text-faint">{item.server_url}</span>
              )}
            </div>
            {allowToolView && onViewTool && item.server_slug === "datapro" && (
              <button
                type="button"
                className="btn btn-secondary btn-sm shrink-0 self-center"
                onClick={() => onViewTool(capName)}
              >
                View code
              </button>
            )}
            {allowPromptPreview && localPrompt && onEditLocalPrompt && (
              <button
                type="button"
                className="btn btn-secondary btn-sm shrink-0 self-center"
                onClick={() => onEditLocalPrompt(item)}
              >
                Edit
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
            {allowPromptPreview && onPreviewPrompt && (
              <button
                type="button"
                className="btn btn-secondary btn-sm shrink-0 self-center"
                onClick={() => onPreviewPrompt({ ...item, capability_name: capName })}
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
        );
      })}
    </div>
  );
}
