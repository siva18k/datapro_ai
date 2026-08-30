import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type McpBindingItem, type McpCatalogCapability, type McpRegistryPrompt } from "../api/client";
import { McpPromptEditModal } from "./McpPromptEditModal";
import { McpResourcePreviewModal } from "./McpResourcePreviewModal";
import { McpToolViewModal } from "./McpToolViewModal";

type CatalogTab = "tools" | "prompts" | "resources";

type CatalogRow = {
  key: string;
  name: string;
  description: string;
  serverName: string;
  serverReachable: boolean;
  uri?: string;
  prompt?: McpRegistryPrompt;
};

export function McpCatalogPanel() {
  const qc = useQueryClient();
  const [tab, setTab] = useState<CatalogTab>("tools");
  const [viewTool, setViewTool] = useState<string | null>(null);
  const [editPrompt, setEditPrompt] = useState<string | null>(null);
  const [previewResource, setPreviewResource] = useState<McpBindingItem | null>(null);
  const [restartNeeded, setRestartNeeded] = useState(false);

  const { data: catalog, isLoading } = useQuery({
    queryKey: ["mcp", "binding-catalog"],
    queryFn: api.mcpBindingCatalog,
  });

  const { data: registry } = useQuery({
    queryKey: ["mcp", "registry"],
    queryFn: api.mcpRegistry,
  });

  const { data: status, refetch: refetchStatus } = useQuery({
    queryKey: ["mcp", "status"],
    queryFn: api.mcpStatus,
    refetchInterval: 15_000,
  });

  const mcpRestart = useMutation({
    mutationFn: api.mcpRestart,
    onSuccess: (res) => {
      void refetchStatus();
      void qc.invalidateQueries({ queryKey: ["mcp"] });
      if (res.ok) setRestartNeeded(false);
    },
  });

  const registryPrompts = useMemo(() => {
    const map = new Map<string, McpRegistryPrompt>();
    for (const prompt of registry?.prompts ?? []) map.set(prompt.name, prompt);
    return map;
  }, [registry?.prompts]);

  const rows = useMemo(() => {
    const out: CatalogRow[] = [];
    for (const entry of catalog?.servers ?? []) {
      const items =
        tab === "tools" ? entry.tools : tab === "prompts" ? entry.prompts : entry.resources;
      for (const item of items) {
        out.push(toRow(tab, item, entry.server.name, Boolean(entry.reachable), registryPrompts));
      }
    }
    if (tab === "prompts") {
      for (const prompt of registry?.prompts ?? []) {
        if (out.some((row) => row.name === prompt.name)) continue;
        out.push({
          key: `registry:${prompt.name}`,
          name: prompt.name,
          description: prompt.description,
          serverName: "DATA Pro (registry)",
          serverReachable: Boolean(status?.reachable),
          prompt,
        });
      }
    }
    out.sort((a, b) => a.name.localeCompare(b.name));
    return out;
  }, [catalog?.servers, registry?.prompts, registryPrompts, status?.reachable, tab]);

  const counts = useMemo(() => {
    let tools = 0;
    let prompts = registry?.prompts.length ?? 0;
    let resources = 0;
    const promptNames = new Set((registry?.prompts ?? []).map((p) => p.name));
    for (const entry of catalog?.servers ?? []) {
      tools += entry.tools.length;
      resources += entry.resources.length;
      for (const prompt of entry.prompts) promptNames.add(prompt.name);
    }
    prompts = promptNames.size;
    return { tools, prompts, resources };
  }, [catalog?.servers, registry?.prompts]);

  return (
    <div className="space-y-4">
      {restartNeeded && (
        <div className="mcp-restart-banner">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p>
              <strong>Restart required.</strong> Built-in prompt edits need an MCP restart (Settings →
              Servers).
            </p>
            <button
              type="button"
              className="btn btn-sm shrink-0"
              disabled={mcpRestart.isPending || !status?.reachable}
              onClick={() => mcpRestart.mutate()}
            >
              {mcpRestart.isPending ? "Restarting…" : "Restart MCP now"}
            </button>
          </div>
        </div>
      )}

      <div className="card card-pad space-y-4">
        <div>
          <h2 className="font-semibold">MCP catalog</h2>
          <p className="mt-1 text-sm" style={{ color: "var(--color-text-muted)" }}>
            Tools, prompts, and resources from every registered server. Tools can be attached to an
            agent as abilities. Start or add servers on the Servers tab.
          </p>
        </div>

        <div className="tabs">
          {(["tools", "prompts", "resources"] as const).map((id) => (
            <button
              key={id}
              type="button"
              className={`tab capitalize ${tab === id ? "tab-active" : ""}`}
              onClick={() => setTab(id)}
            >
              {id}
              <span className="ml-1.5 text-xs opacity-70">({counts[id]})</span>
            </button>
          ))}
        </div>

        <p className="text-xs" style={{ color: "var(--color-text-muted)" }}>
          {tab === "tools" &&
            "Actions an agent or Ask can call. Attach extras on an agent under Advanced."}
          {tab === "prompts" && "Templates used when generating answers. Built-in prompts can be edited."}
          {tab === "resources" && "Read-only context (schema, glossary, calendar) loaded with a domain."}
        </p>

        {isLoading && (
          <p className="text-sm" style={{ color: "var(--color-text-muted)" }}>
            Loading catalog…
          </p>
        )}

        {!isLoading && rows.length === 0 && (
          <p className="text-sm" style={{ color: "var(--color-text-muted)" }}>
            Nothing discovered. Start the DATA Pro server on the Servers tab and refresh.
          </p>
        )}

        <div className="space-y-2">
          {rows.map((row) => (
            <div key={row.key} className="mcp-list-item mcp-list-item--row">
              <div className="min-w-0 flex-1">
                <p className="font-medium text-sm">{row.name}</p>
                {row.description && (
                  <p className="mt-0.5 mcp-text-muted">{row.description}</p>
                )}
                <p className="mt-1 text-xs" style={{ color: "var(--color-text-muted)" }}>
                  {row.serverName}
                  {row.uri ? ` · ${row.uri}` : ""}
                  {tab === "tools" ? " · Agent ability" : ""}
                </p>
                {!row.serverReachable && (
                  <span className="badge-muted badge mt-1 text-xs">Server offline</span>
                )}
                {row.prompt && !row.prompt.enabled && (
                  <span className="badge-muted badge mt-1 text-xs">Disabled in registry</span>
                )}
              </div>
              {tab === "tools" && (
                <button
                  type="button"
                  className="btn btn-secondary btn-sm shrink-0"
                  onClick={() => setViewTool(row.name)}
                >
                  View
                </button>
              )}
              {tab === "prompts" && row.prompt && (
                <button
                  type="button"
                  className="btn btn-secondary btn-sm shrink-0"
                  onClick={() => setEditPrompt(row.prompt!.name)}
                >
                  Edit
                </button>
              )}
              {tab === "resources" && row.uri && (
                <button
                  type="button"
                  className="btn btn-secondary btn-sm shrink-0"
                  onClick={() =>
                    setPreviewResource({
                      name: row.name,
                      uri: row.uri,
                      enabled: true,
                      description: row.description,
                    })
                  }
                >
                  Preview
                </button>
              )}
            </div>
          ))}
        </div>
      </div>

      <McpToolViewModal open={viewTool != null} toolName={viewTool ?? ""} onClose={() => setViewTool(null)} />
      {registry && (
        <McpPromptEditModal
          open={editPrompt != null}
          promptName={editPrompt ?? ""}
          prompts={registry.prompts}
          serverReachable={!!status?.reachable}
          onClose={() => setEditPrompt(null)}
          onSaved={() => setRestartNeeded(true)}
        />
      )}
      <McpResourcePreviewModal
        open={previewResource != null}
        resource={previewResource}
        serverReachable={!!status?.reachable}
        onClose={() => setPreviewResource(null)}
      />
    </div>
  );
}

function toRow(
  tab: CatalogTab,
  item: McpCatalogCapability,
  serverName: string,
  reachable: boolean,
  registryPrompts: Map<string, McpRegistryPrompt>,
): CatalogRow {
  const name = item.name;
  return {
    key: `${serverName}:${tab}:${item.uri || name}`,
    name,
    description: item.description || "",
    serverName,
    serverReachable: reachable,
    uri: item.uri,
    prompt: tab === "prompts" ? registryPrompts.get(name) : undefined,
  };
}
