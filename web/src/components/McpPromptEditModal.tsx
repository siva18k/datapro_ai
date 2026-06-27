import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, type McpRegistryPrompt } from "../api/client";

export function McpPromptEditModal({
  open,
  promptName,
  prompts,
  serverReachable,
  onClose,
  onSaved,
}: {
  open: boolean;
  promptName: string;
  prompts: McpRegistryPrompt[];
  serverReachable: boolean;
  onClose: () => void;
  onSaved: () => void;
}) {
  const qc = useQueryClient();
  const saved = prompts.find((p) => p.name === promptName) ?? prompts[0];
  const [description, setDescription] = useState("");
  const [template, setTemplate] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [preview, setPreview] = useState<string | null>(null);
  const [saveNotice, setSaveNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !saved) return;
    setDescription(saved.description);
    setTemplate(saved.template);
    setEnabled(saved.enabled);
    setPreview(null);
    setSaveNotice(null);
  }, [open, saved?.name, saved?.description, saved?.template, saved?.enabled]);

  const save = useMutation({
    mutationFn: () =>
      api.updateMcpPrompt(saved.name, {
        description,
        template,
        enabled,
      }),
    onSuccess: () => {
      onSaved();
      setSaveNotice("Saved. Restart MCP server to apply.");
      void qc.invalidateQueries({ queryKey: ["mcp", "registry"] });
      void qc.invalidateQueries({ queryKey: ["mcp", "bindings"] });
    },
  });

  const previewLive = useMutation({
    mutationFn: () =>
      api.previewMcpPrompt(saved.name, {
        arguments: {
          question: "What is our travel policy?",
          context: "[travel_policy.md - chunk_00] Sample context…",
          domain_name: "HR",
          source_file: "travel_policy.md",
          body: "Sample document body…",
        },
      }),
    onSuccess: (res) => setPreview(res.preview),
  });

  if (!open || !saved) return null;

  const dirty =
    description !== saved.description || template !== saved.template || enabled !== saved.enabled;

  return (
    <div
      className="modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="mcp-prompt-title"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="modal-card max-w-2xl">
        <div className="modal-header">
          <h2 id="mcp-prompt-title" className="text-lg font-semibold">
            Edit global prompt: {saved.name}
          </h2>
          <button type="button" className="btn-ghost btn-sm" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>

        <p className="text-sm text-zinc-500">
          Global prompt — <code className="text-xs">mcp_registry.json</code>. Restart MCP after save.
        </p>

        <label className="mt-4 flex items-center gap-2 text-sm">
          <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
          Enabled in registry
        </label>

        <div className="field mb-0 mt-3">
          <label className="label">Description</label>
          <input className="input" value={description} onChange={(e) => setDescription(e.target.value)} />
        </div>

        <div className="field mb-0 mt-3">
          <label className="label">Template</label>
          <textarea
            className="input min-h-56 font-mono text-xs"
            value={template}
            onChange={(e) => setTemplate(e.target.value)}
          />
        </div>

        {preview && (
          <div className="mt-3">
            <p className="label mb-1">Live preview</p>
            <pre className="max-h-40 overflow-auto rounded-lg bg-zinc-900 p-3 text-xs text-zinc-100">{preview}</pre>
          </div>
        )}

        {saveNotice && <p className="alert-ok mt-3 text-sm">{saveNotice}</p>}
        {save.error && <p className="alert-error mt-3 text-sm">{String(save.error)}</p>}
        {previewLive.error && <p className="alert-error mt-3 text-sm">{String(previewLive.error)}</p>}

        <div className="modal-actions">
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            disabled={!serverReachable || previewLive.isPending}
            onClick={() => previewLive.mutate()}
          >
            {previewLive.isPending ? "Previewing…" : "Preview live"}
          </button>
          <button type="button" className="btn btn-secondary btn-sm" onClick={onClose}>
            Close
          </button>
          <button type="button" className="btn btn-sm" disabled={!dirty || save.isPending} onClick={() => save.mutate()}>
            {save.isPending ? "Saving…" : "Save prompt"}
          </button>
        </div>
      </div>
    </div>
  );
}
