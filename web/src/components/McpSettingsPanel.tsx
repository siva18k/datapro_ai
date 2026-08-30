import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api, type McpRegistryPrompt } from "../api/client";
import { McpPromptEditModal } from "./McpPromptEditModal";
import { McpServersPanel } from "./McpServersPanel";

export function McpSettingsPanel({ envPath }: { envPath: string }) {
  const qc = useQueryClient();
  const [restartNeeded, setRestartNeeded] = useState(false);
  const [editingPrompt, setEditingPrompt] = useState<string | null>(null);

  const { data: settings } = useQuery({
    queryKey: ["settings"],
    queryFn: api.getSettings,
  });

  const { data: status, refetch: refetchStatus } = useQuery({
    queryKey: ["mcp", "status"],
    queryFn: api.mcpStatus,
    refetchInterval: 15_000,
  });

  const mcpIsRunning = Boolean(status?.reachable || (status?.listener_pids?.length ?? 0) > 0);

  const mcpRestart = useMutation({
    mutationFn: api.mcpRestart,
    onSuccess: (res) => {
      void refetchStatus();
      void qc.invalidateQueries({ queryKey: ["mcp"] });
      if (res.ok) setRestartNeeded(false);
    },
  });

  const { data: registry } = useQuery({
    queryKey: ["mcp", "registry"],
    queryFn: api.mcpRegistry,
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

  const cursorConfig = useMemo(() => {
    const servers = serversData?.servers?.filter((s) => s.enabled) ?? [];
    const mcpServers: Record<string, { url: string }> = {};
    for (const server of servers) {
      mcpServers[server.slug] = { url: server.url };
    }
    if (!Object.keys(mcpServers).length) {
      const url = status?.url ?? settings?.mcp_url ?? "http://127.0.0.1:8000/mcp";
      mcpServers.datapro = { url };
    }
    return JSON.stringify({ mcpServers }, null, 2);
  }, [serversData?.servers, status?.url, settings?.mcp_url]);

  return (
    <div className="space-y-4">
      {restartNeeded && (
        <RestartBanner
          busy={mcpRestart.isPending}
          running={mcpIsRunning}
          onRestart={() => mcpRestart.mutate()}
        />
      )}

      <McpServersPanel envPath={envPath} />

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
