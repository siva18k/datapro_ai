import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { api, type McpBindingItem } from "../api/client";

function formatPreviewContent(content: string, mimeType?: string): string {
  if (mimeType?.includes("json") || content.trimStart().startsWith("{") || content.trimStart().startsWith("[")) {
    try {
      return JSON.stringify(JSON.parse(content), null, 2);
    } catch {
      return content;
    }
  }
  return content;
}

export function McpResourcePreviewModal({
  open,
  resource,
  serverReachable,
  onClose,
}: {
  open: boolean;
  resource: McpBindingItem | null;
  serverReachable: boolean;
  onClose: () => void;
}) {
  const uri = resource?.uri ?? "";
  const [params, setParams] = useState<Record<string, string>>({});

  const { data: meta } = useQuery({
    queryKey: ["mcp", "resource-meta", uri],
    queryFn: () => api.mcpResourceMeta(uri),
    enabled: open && !!uri,
  });

  const paramNames = meta?.parameters ?? [];

  const preview = useMutation({
    mutationFn: () => api.previewMcpResource(uri, params),
  });

  useEffect(() => {
    if (!open) return;
    setParams({});
  }, [open, uri]);

  useEffect(() => {
    if (!open || !uri || !serverReachable || meta === undefined) return;
    if (meta.parameters.length > 0) return;
    preview.mutate();
  }, [open, uri, serverReachable, meta]);

  const displayContent = useMemo(() => {
    if (!preview.data?.content) return "";
    return formatPreviewContent(preview.data.content, preview.data.mime_type ?? meta?.mime_type);
  }, [preview.data, meta?.mime_type]);

  if (!open || !resource) return null;

  return (
    <div
      className="modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="mcp-resource-title"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="modal-card max-w-3xl">
        <div className="modal-header">
          <h2 id="mcp-resource-title" className="text-lg font-semibold">
            Resource: {resource.name}
          </h2>
          <button type="button" className="btn-ghost btn-sm" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>

        <p className="text-sm text-zinc-500">Live preview from MCP server.</p>

        <div className="mt-3 space-y-2 text-sm">
          <p>
            <span className="font-medium text-zinc-700">URI template:</span>{" "}
            <code className="mcp-code-inline">{uri}</code>
          </p>
          {resource.description && <p className="text-zinc-600">{resource.description}</p>}
          {meta?.mime_type && (
            <p className="text-xs text-zinc-500">
              MIME type: <code>{meta.mime_type}</code>
            </p>
          )}
        </div>

        {!serverReachable && (
          <p className="alert-error mt-3 text-sm">Start the MCP server to preview resource content.</p>
        )}

        {paramNames.length > 0 && serverReachable && (
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {paramNames.map((key) => (
              <div key={key} className="field mb-0">
                <label className="label">{key}</label>
                <input
                  className="input font-mono text-xs"
                  value={params[key] ?? ""}
                  placeholder={key === "domain" ? "e.g. finance" : key}
                  onChange={(e) => setParams((prev) => ({ ...prev, [key]: e.target.value }))}
                />
              </div>
            ))}
            <div className="sm:col-span-2">
              <button
                type="button"
                className="btn btn-sm"
                disabled={preview.isPending}
                onClick={() => preview.mutate()}
              >
                {preview.isPending ? "Loading…" : "Load preview"}
              </button>
            </div>
          </div>
        )}

        {preview.isPending && paramNames.length === 0 && (
          <p className="mt-4 text-sm text-zinc-500">Loading preview…</p>
        )}
        {preview.error && <p className="alert-error mt-3 text-sm">{String(preview.error)}</p>}

        {preview.data && (
          <div className="mt-4">
            <p className="label mb-1">
              Preview
              {preview.data.truncated && " (truncated)"}
            </p>
            <p className="mb-2 font-mono text-xs text-zinc-500">{preview.data.uri}</p>
            <pre className="max-h-80 overflow-auto rounded-lg bg-zinc-900 p-3 text-xs text-zinc-100">{displayContent}</pre>
          </div>
        )}

        <div className="modal-actions">
          {paramNames.length === 0 && serverReachable && (
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={preview.isPending}
              onClick={() => preview.mutate()}
            >
              Refresh
            </button>
          )}
          <button type="button" className="btn btn-secondary btn-sm" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
