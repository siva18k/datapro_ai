import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type McpBindingCatalogEntry } from "../api/client";
import type { AgentToolBinding } from "../types";

type Props = {
  selected: AgentToolBinding[];
  onChange: (tools: AgentToolBinding[]) => void;
  disabled?: boolean;
};

function toolKey(serverId: string, toolName: string) {
  return `${serverId}:${toolName}`;
}

export function AgentToolPicker({ selected, onChange, disabled = false }: Props) {
  const { data: catalog } = useQuery({
    queryKey: ["mcp", "binding-catalog"],
    queryFn: api.mcpBindingCatalog,
  });

  const selectedKeys = useMemo(
    () => new Set(selected.map((t) => toolKey(t.mcp_server_id, t.tool_name))),
    [selected],
  );

  const entries = catalog?.servers ?? [];

  const toggle = (entry: McpBindingCatalogEntry, toolName: string) => {
    const key = toolKey(entry.server.id, toolName);
    if (selectedKeys.has(key)) {
      onChange(selected.filter((t) => toolKey(t.mcp_server_id, t.tool_name) !== key));
    } else {
      onChange([
        ...selected,
        {
          mcp_server_id: entry.server.id,
          tool_name: toolName,
          server_name: entry.server.name,
          server_slug: entry.server.slug,
        },
      ]);
    }
  };

  return (
    <div className="field mb-0">
      <label className="label">MCP tools</label>
      <p className="mb-2 text-xs text-zinc-500">Select tools this agent may use during a test run.</p>
      <div className="agent-tool-picker max-h-48 overflow-y-auto rounded-lg border p-2" style={{ borderColor: "var(--color-border)" }}>
        {entries.length === 0 && (
          <p className="text-sm" style={{ color: "var(--color-text-muted)" }}>
            No MCP servers registered. Add servers under Settings → MCP.
          </p>
        )}
        {entries.map((entry) => {
          const tools = entry.tools ?? [];
          if (tools.length === 0) return null;
          return (
            <div key={entry.server.id} className="mb-3 last:mb-0">
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-zinc-500">
                {entry.server.name}
              </p>
              <div className="flex flex-wrap gap-1.5">
                {tools.map((tool) => {
                  const active = selectedKeys.has(toolKey(entry.server.id, tool.name));
                  return (
                    <button
                      key={tool.name}
                      type="button"
                      disabled={disabled}
                      className={`ask-composer-pill${active ? " ask-composer-pill--active" : ""}`}
                      onClick={() => toggle(entry, tool.name)}
                    >
                      {tool.name}
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
