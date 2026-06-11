import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

export function McpToolViewModal({
  open,
  toolName,
  onClose,
}: {
  open: boolean;
  toolName: string;
  onClose: () => void;
}) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["mcp", "tool", toolName],
    queryFn: () => api.mcpToolDetail(toolName),
    enabled: open && !!toolName,
  });

  if (!open) return null;

  return (
    <div
      className="modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="mcp-tool-title"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="modal-card max-w-3xl">
        <div className="modal-header">
          <h2 id="mcp-tool-title" className="text-lg font-semibold">
            Tool: {toolName}
          </h2>
          <button type="button" className="btn-ghost btn-sm" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>

        <p className="text-sm text-zinc-500">Handler in <code className="text-xs">mcp_server.py</code></p>

        {isLoading && <p className="mt-4 text-sm text-zinc-500">Loading…</p>}
        {error && <p className="alert-error mt-4 text-sm">{String(error)}</p>}

        {data && (
          <div className="mt-4 space-y-4">
            <div>
              <p className="label mb-1">What it does</p>
              <p className="text-sm text-zinc-700">{data.description}</p>
              {data.live_description && data.live_description !== data.description && (
                <p className="mt-2 text-xs text-zinc-500">
                  Live server description: {data.live_description}
                </p>
              )}
            </div>

            {data.input_schema && (
              <div>
                <p className="label mb-1">Input schema (live server)</p>
                <pre className="max-h-40 overflow-auto rounded-lg bg-zinc-900 p-3 text-xs text-zinc-100">
                  {JSON.stringify(data.input_schema, null, 2)}
                </pre>
              </div>
            )}

            <div>
              <p className="label mb-1">Implementation ({data.implementation_path})</p>
              {data.implementation ? (
                <pre className="max-h-80 overflow-auto rounded-lg bg-zinc-900 p-3 text-xs text-zinc-100">
                  {data.implementation}
                </pre>
              ) : (
                <p className="text-sm text-zinc-500">Source not found in mcp_server.py.</p>
              )}
            </div>
          </div>
        )}

        <div className="modal-actions">
          <button type="button" className="btn btn-secondary btn-sm" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
