import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, type McpBindingItem } from "../api/client";
import { expandMcpResourceUri } from "../utils/mcpServerUi";

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
  domainSlug,
  domainId,
  onClose,
}: {
  open: boolean;
  resource: McpBindingItem | null;
  serverReachable: boolean;
  /** Selected domain slug from Domain bindings — pre-fills `{domain}` template params. */
  domainSlug?: string | null;
  domainId?: string | null;
  onClose: () => void;
}) {
  const uri = resource?.uri ?? "";
  const [params, setParams] = useState<Record<string, string>>({});
  const lastAutoPreviewKey = useRef<string | null>(null);

  const { data: meta } = useQuery({
    queryKey: ["mcp", "resource-meta", uri],
    queryFn: () => api.mcpResourceMeta(uri),
    enabled: open && !!uri,
  });

  const paramNames = meta?.parameters ?? [];
  const domainFromContext = Boolean(domainSlug?.trim());
  const contextFilledParams = useMemo(() => {
    if (!domainSlug?.trim() || !paramNames.length) return {};
    const initial: Record<string, string> = {};
    for (const key of paramNames) {
      if (key === "domain") initial[key] = domainSlug.trim();
    }
    return initial;
  }, [domainSlug, paramNames]);
  const manualParamNames = domainFromContext ? paramNames.filter((key) => key !== "domain") : paramNames;
  const effectiveParams = useMemo(
    () => ({ ...contextFilledParams, ...params }),
    [contextFilledParams, params],
  );
  const resolvedUri = useMemo(
    () => (uri ? expandMcpResourceUri(uri, effectiveParams) : ""),
    [uri, effectiveParams],
  );
  const allParamsFilled =
    paramNames.length === 0 || paramNames.every((key) => Boolean(effectiveParams[key]?.trim()));
  const isBuiltinReference =
    uri === "ragpro://policy/citation-rules" ||
    /ragpro:\/\/domains\/\{domain\}\/(schema|calendar|glossary|sql-notes)/.test(uri);
  const canPreview = isBuiltinReference ? allParamsFilled : serverReachable && allParamsFilled;

  const preview = useMutation({
    mutationFn: () => api.previewMcpResource(uri, effectiveParams, domainId ?? undefined),
  });

  useEffect(() => {
    if (!open) {
      lastAutoPreviewKey.current = null;
      return;
    }
    setParams({});
  }, [open, uri]);

  useEffect(() => {
    if (!open || !uri || !canPreview || meta === undefined || !allParamsFilled) return;
    const previewKey = JSON.stringify({ uri, domainId, params: effectiveParams });
    if (lastAutoPreviewKey.current === previewKey) return;
    lastAutoPreviewKey.current = previewKey;
    preview.mutate();
  }, [open, uri, canPreview, meta, allParamsFilled, domainId, effectiveParams]);

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

        <p className="text-sm mcp-text-muted">
          {isBuiltinReference
            ? "Preview from catalog reference docs (no MCP restart required)."
            : "Live preview from MCP server."}
        </p>

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
          {resolvedUri && resolvedUri !== uri && (
            <p>
              <span className="font-medium text-zinc-700">Resolved URI:</span>{" "}
              <code className="mcp-code-inline">{resolvedUri}</code>
            </p>
          )}
        </div>

        {!canPreview && (
          <p className="alert-error mt-3 text-sm">
            {!serverReachable && !isBuiltinReference
              ? "Start the MCP server to preview resource content."
              : "Fill required parameters to preview this resource."}
          </p>
        )}

        {manualParamNames.length > 0 && canPreview && (
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {manualParamNames.map((key) => (
              <div key={key} className="field mb-0">
                <label className="label">{key}</label>
                <input
                  className="input font-mono text-xs"
                  value={params[key] ?? ""}
                  placeholder={key}
                  onChange={(e) => setParams((prev) => ({ ...prev, [key]: e.target.value }))}
                />
              </div>
            ))}
            <div className="sm:col-span-2">
              <button
                type="button"
                className="btn btn-sm"
                disabled={preview.isPending || !allParamsFilled}
                onClick={() => preview.mutate()}
              >
                {preview.isPending ? "Loading…" : "Load preview"}
              </button>
            </div>
          </div>
        )}

        {preview.isPending && manualParamNames.length === 0 && (
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
          {canPreview && (
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
