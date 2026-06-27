import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, type DomainPrompt } from "../api/client";

export function McpLocalPromptEditModal({
  open,
  domainId,
  prompt,
  onClose,
}: {
  open: boolean;
  domainId: string;
  prompt: DomainPrompt | null;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [description, setDescription] = useState("");
  const [template, setTemplate] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !prompt) return;
    setName(prompt.name);
    setSlug(prompt.slug);
    setDescription(prompt.description);
    setTemplate(prompt.template);
    setEnabled(prompt.enabled);
    setNotice(null);
  }, [open, prompt?.id, prompt?.name, prompt?.slug, prompt?.description, prompt?.template, prompt?.enabled]);

  const save = useMutation({
    mutationFn: () =>
      api.updateDomainPrompt(domainId, prompt!.id, {
        name,
        slug,
        description,
        template,
        enabled,
      }),
    onSuccess: () => {
      setNotice("Saved.");
      void qc.invalidateQueries({ queryKey: ["domains", domainId, "prompts"] });
      void qc.invalidateQueries({ queryKey: ["mcp", "bindings", domainId] });
    },
  });

  const remove = useMutation({
    mutationFn: () => api.deleteDomainPrompt(domainId, prompt!.id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["domains", domainId, "prompts"] });
      void qc.invalidateQueries({ queryKey: ["mcp", "bindings", domainId] });
      onClose();
    },
  });

  if (!open || !prompt) return null;

  const dirty =
    name !== prompt.name ||
    slug !== prompt.slug ||
    description !== prompt.description ||
    template !== prompt.template ||
    enabled !== prompt.enabled;

  return (
    <div
      className="modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="local-prompt-title"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="modal-card max-w-2xl">
        <div className="modal-header">
          <h2 id="local-prompt-title" className="text-lg font-semibold">
            Edit local prompt
          </h2>
          <button type="button" className="btn-ghost btn-sm" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>

        <p className="text-sm mcp-text-muted">
          Domain-only template — bound as <code className="mcp-code-inline">local:{prompt.slug}</code>.
        </p>

        <label className="mt-4 flex items-center gap-2 text-sm">
          <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
          Enabled
        </label>

        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <div className="field mb-0">
            <label className="label">Name</label>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="field mb-0">
            <label className="label">Slug</label>
            <input
              className="input font-mono text-xs"
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
            />
          </div>
        </div>

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

        {notice && <p className="alert-ok mt-3 text-sm">{notice}</p>}
        {save.error && <p className="alert-error mt-3 text-sm">{String(save.error)}</p>}
        {remove.error && <p className="alert-error mt-3 text-sm">{String(remove.error)}</p>}

        <div className="modal-actions">
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            disabled={remove.isPending}
            onClick={() => {
              if (window.confirm(`Delete local prompt "${prompt.name}" and its binding?`)) {
                remove.mutate();
              }
            }}
          >
            {remove.isPending ? "Deleting…" : "Delete"}
          </button>
          <button type="button" className="btn btn-secondary btn-sm" onClick={onClose}>
            Close
          </button>
          <button
            type="button"
            className="btn btn-sm"
            disabled={!dirty || save.isPending}
            onClick={() => save.mutate()}
          >
            {save.isPending ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}
