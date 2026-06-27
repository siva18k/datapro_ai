import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, type McpBindingItem } from "../api/client";
import { bindingCapabilityName, isLocalPromptBinding } from "../utils/mcpBindingUi";

const DEFAULT_QUESTION = "What datasets and tables are in this domain?";

function paramLabel(key: string): string {
  switch (key) {
    case "top_k":
      return "Top K chunks";
    case "source_file":
      return "Source file";
    default:
      return key.replace(/_/g, " ");
  }
}

function paramPlaceholder(key: string): string {
  switch (key) {
    case "question":
      return DEFAULT_QUESTION;
    case "top_k":
      return "3";
    case "source_file":
      return "e.g. travel_policy.md";
    default:
      return key;
  }
}

export function McpPromptPreviewModal({
  open,
  prompt,
  serverReachable,
  domainId,
  domainName,
  onClose,
}: {
  open: boolean;
  prompt: McpBindingItem | null;
  serverReachable: boolean;
  /** Selected domain — fills domain-scoped prompt arguments on the server. */
  domainId?: string | null;
  domainName?: string | null;
  onClose: () => void;
}) {
  const capabilityName = bindingCapabilityName(prompt ?? { name: "" });
  const isLocal = isLocalPromptBinding(prompt ?? { name: capabilityName });
  const [params, setParams] = useState<Record<string, string>>({});
  const lastAutoPreviewKey = useRef<string | null>(null);

  const { data: meta } = useQuery({
    queryKey: ["mcp", "prompt-meta", capabilityName, domainId],
    queryFn: () => api.mcpPromptMeta(capabilityName, domainId ?? undefined),
    enabled: open && !!capabilityName && (!isLocal || !!domainId),
  });

  const domainFilled = useMemo(
    () => new Set(meta?.domain_filled_parameters ?? []),
    [meta?.domain_filled_parameters],
  );
  const manualParamNames = useMemo(() => {
    if (!meta?.parameters?.length) return [];
    if (!domainId || !meta.domain_context) return meta.parameters;
    return meta.parameters.filter((key) => !domainFilled.has(key));
  }, [meta, domainId, domainFilled]);

  const effectiveParams = useMemo(() => {
    const merged: Record<string, string> = {};
    for (const key of manualParamNames) {
      const value = params[key]?.trim();
      if (value) merged[key] = value;
    }
    return merged;
  }, [manualParamNames, params]);

  const preview = useMutation({
    mutationFn: () =>
      api.previewMcpPrompt(capabilityName, {
        arguments: effectiveParams,
        domainId: domainId ?? undefined,
      }),
  });

  useEffect(() => {
    if (!open) {
      lastAutoPreviewKey.current = null;
      return;
    }
    setParams({});
  }, [open, capabilityName]);

  const canPreview = isLocal ? Boolean(domainId) : serverReachable;

  useEffect(() => {
    if (!open || !capabilityName || !canPreview || meta === undefined) return;
    const previewKey = JSON.stringify({ capabilityName, domainId, mode: "initial" });
    if (lastAutoPreviewKey.current === previewKey) return;
    lastAutoPreviewKey.current = previewKey;
    preview.mutate();
  }, [open, capabilityName, canPreview, meta, domainId]);

  if (!open || !prompt) return null;

  return (
    <div
      className="modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="mcp-prompt-preview-title"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="modal-card max-w-3xl">
        <div className="modal-header">
          <h2 id="mcp-prompt-preview-title" className="text-lg font-semibold">
            Prompt: {prompt.name}
          </h2>
          <button type="button" className="btn-ghost btn-sm" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>

        <p className="text-sm mcp-text-muted">
          {isLocal ? "Rendered from domain-local template." : "Live preview from MCP server."}
        </p>

        <div className="mt-3 space-y-2 text-sm">
          {meta?.description && <p className="mcp-text-muted">{meta.description}</p>}
          {domainId && meta?.domain_context && domainName && (
            <p className="text-xs mcp-text-faint">
              Domain context: <span className="font-medium">{domainName}</span>
              {domainFilled.size > 0 && (
                <>
                  {" "}
                  · auto-filled: {Array.from(domainFilled).join(", ")}
                </>
              )}
            </p>
          )}
        </div>

        {!canPreview && (
          <p className="alert-error mt-3 text-sm">
            {isLocal ? "Select a domain to preview this local prompt." : "Start the MCP server to preview prompt output."}
          </p>
        )}

        {manualParamNames.length > 0 && canPreview && (
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {manualParamNames.map((key) => (
              <div key={key} className={`field mb-0 ${key === "question" ? "sm:col-span-2" : ""}`}>
                <label className="label capitalize">{paramLabel(key)}</label>
                {key === "question" ? (
                  <textarea
                    className="input min-h-20 font-mono text-xs"
                    value={params[key] ?? ""}
                    placeholder={paramPlaceholder(key)}
                    onChange={(e) => setParams((prev) => ({ ...prev, [key]: e.target.value }))}
                  />
                ) : (
                  <input
                    className="input font-mono text-xs"
                    value={params[key] ?? ""}
                    placeholder={paramPlaceholder(key)}
                    onChange={(e) => setParams((prev) => ({ ...prev, [key]: e.target.value }))}
                  />
                )}
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

        {preview.isPending && (
          <p className="mt-4 text-sm mcp-text-muted">Loading preview…</p>
        )}
        {preview.error && <p className="alert-error mt-3 text-sm">{String(preview.error)}</p>}

        {preview.data && (
          <div className="mt-4">
            <p className="label mb-1">Preview</p>
            <pre className="max-h-80 overflow-auto rounded-lg bg-zinc-900 p-3 text-xs text-zinc-100">
              {preview.data.preview}
            </pre>
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
