import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import {
  api,
  type DomainPrompt,
  type McpBindingCatalogEntry,
  type McpRegistryPrompt,
} from "../api/client";

type PromptSource = "global" | "local";

const DEFAULT_LOCAL_TEMPLATE = `{citation_rules}

Business domain: {domain_name}

## Catalog schema
{schema}

User question:
{question}

Context:
{context}

Answer using only the context above. Cite sources as [source_file - chunk_id].`;

function slugify(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);
}

export function McpAddPromptModal({
  open,
  domainId,
  catalog,
  registryPrompts,
  boundKeys,
  saving,
  onClose,
  onAddGlobal,
}: {
  open: boolean;
  domainId: string;
  catalog: McpBindingCatalogEntry[] | undefined;
  registryPrompts: McpRegistryPrompt[] | undefined;
  boundKeys: Set<string>;
  saving: boolean;
  onClose: () => void;
  onAddGlobal: (serverId: string, capabilityName: string) => void;
}) {
  const qc = useQueryClient();
  const [source, setSource] = useState<PromptSource>("global");
  const [slug, setSlug] = useState("");
  const [slugTouched, setSlugTouched] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [template, setTemplate] = useState(DEFAULT_LOCAL_TEMPLATE);
  const [formError, setFormError] = useState<string | null>(null);

  const builtinEntry = useMemo(
    () => catalog?.find((entry) => entry.server.is_builtin || entry.server.slug === "datapro"),
    [catalog],
  );
  const builtinServerId = builtinEntry?.server.id ?? "";

  const { data: localPrompts } = useQuery({
    queryKey: ["domains", domainId, "prompts"],
    queryFn: () => api.listDomainPrompts(domainId),
    enabled: open && !!domainId,
  });

  const createLocal = useMutation({
    mutationFn: () =>
      api.createDomainPrompt(domainId, {
        slug: slug.trim(),
        name: name.trim(),
        description: description.trim(),
        template,
        bind: true,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["domains", domainId, "prompts"] });
      void qc.invalidateQueries({ queryKey: ["mcp", "bindings", domainId] });
      setName("");
      setSlug("");
      setSlugTouched(false);
      setDescription("");
      setTemplate(DEFAULT_LOCAL_TEMPLATE);
      setFormError(null);
    },
    onError: (err) => setFormError(String(err)),
  });

  useEffect(() => {
    if (!open) return;
    setSource("global");
    setName("");
    setSlug("");
    setSlugTouched(false);
    setDescription("");
    setTemplate(DEFAULT_LOCAL_TEMPLATE);
    setFormError(null);
  }, [open, domainId]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  useEffect(() => {
    if (slugTouched || !name.trim()) return;
    setSlug(slugify(name));
  }, [name, slugTouched]);

  const globalPrompts = useMemo(() => {
    const live = builtinEntry?.prompts ?? [];
    if (live.length) return live;
    return (registryPrompts ?? []).map((p) => ({
      name: p.name,
      description: p.description,
    }));
  }, [builtinEntry?.prompts, registryPrompts]);

  const isGlobalBound = (promptName: string) =>
    Boolean(builtinServerId) &&
    boundKeys.has(`${builtinServerId}:prompt:${promptName}`);

  const isLocalBound = (prompt: DomainPrompt) =>
    Boolean(builtinServerId) &&
    boundKeys.has(`${builtinServerId}:prompt:local:${prompt.slug}`);

  if (!open) return null;

  return (
    <div
      className="modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="add-prompt-title"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="modal-card max-w-2xl">
        <div className="modal-header">
          <div>
            <h2 id="add-prompt-title" className="text-lg font-semibold">
              Add prompt
            </h2>
            <p className="mt-1 text-sm mcp-text-muted">
              Attach a built-in global template or create a domain-local prompt.
            </p>
          </div>
          <button type="button" className="btn-ghost btn-sm shrink-0" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>

        <div className="tabs">
          <button
            type="button"
            className={`tab ${source === "global" ? "tab-active" : ""}`}
            onClick={() => setSource("global")}
          >
            Global
          </button>
          <button
            type="button"
            className={`tab ${source === "local" ? "tab-active" : ""}`}
            onClick={() => setSource("local")}
          >
            Local
          </button>
        </div>

        {source === "global" && (
          <div className="mt-4 max-h-72 space-y-2 overflow-y-auto">
            <p className="text-xs mcp-text-faint">
              Built-in MCP prompts from <code className="mcp-code-inline">mcp_registry.json</code>.
              Restart MCP after editing global templates.
            </p>
            {globalPrompts.length === 0 && (
              <p className="text-sm mcp-text-muted">No global prompts available.</p>
            )}
            {globalPrompts.map((item) => {
              const bound = isGlobalBound(item.name);
              return (
                <div key={item.name} className="mcp-list-item mcp-list-item--row">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="font-medium text-sm">{item.name}</p>
                      <span className="badge-muted badge text-xs">Global</span>
                    </div>
                    {item.description && <p className="mt-0.5 text-sm mcp-text-muted">{item.description}</p>}
                  </div>
                  <button
                    type="button"
                    className="btn btn-sm shrink-0"
                    disabled={saving || bound || !builtinServerId}
                    onClick={() => onAddGlobal(builtinServerId, item.name)}
                  >
                    {bound ? "Added" : "Add"}
                  </button>
                </div>
              );
            })}
          </div>
        )}

        {source === "local" && (
          <div className="mt-4 space-y-4">
            {localPrompts && localPrompts.length > 0 && (
              <div className="max-h-40 space-y-2 overflow-y-auto">
                <p className="text-xs mcp-text-faint">Existing local prompts for this domain</p>
                {localPrompts.map((prompt) => {
                  const bound = isLocalBound(prompt);
                  return (
                    <div key={prompt.id} className="mcp-list-item mcp-list-item--row">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="font-medium text-sm">{prompt.name}</p>
                          <span className="badge-muted badge text-xs">Local</span>
                        </div>
                        <p className="font-mono text-xs mcp-text-faint">local:{prompt.slug}</p>
                      </div>
                      <button
                        type="button"
                        className="btn btn-sm shrink-0"
                        disabled={saving || bound || !builtinServerId}
                        onClick={() => onAddGlobal(builtinServerId, `local:${prompt.slug}`)}
                      >
                        {bound ? "Added" : "Bind"}
                      </button>
                    </div>
                  );
                })}
              </div>
            )}

            <div className="catalog-themed-box space-y-3 p-3">
              <p className="text-sm font-medium">Create local prompt</p>
              <p className="text-xs mcp-text-muted">
                Use placeholders like {"{question}"}, {"{context}"}, {"{domain_name}"}, {"{schema}"},
                {" {calendar}"}, {"{glossary}"}, {"{citation_rules}"}.
              </p>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="field mb-0">
                  <label className="label">Name</label>
                  <input
                    className="input"
                    value={name}
                    placeholder="Finance KPI answer"
                    onChange={(e) => setName(e.target.value)}
                  />
                </div>
                <div className="field mb-0">
                  <label className="label">Slug</label>
                  <input
                    className="input font-mono text-xs"
                    value={slug}
                    placeholder="finance-kpi-answer"
                    onChange={(e) => {
                      setSlugTouched(true);
                      setSlug(e.target.value);
                    }}
                  />
                </div>
              </div>
              <div className="field mb-0">
                <label className="label">Description</label>
                <input
                  className="input"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Optional summary for this domain prompt"
                />
              </div>
              <div className="field mb-0">
                <label className="label">Template</label>
                <textarea
                  className="input min-h-40 font-mono text-xs"
                  value={template}
                  onChange={(e) => setTemplate(e.target.value)}
                />
              </div>
              {formError && <p className="alert-error text-sm">{formError}</p>}
              <button
                type="button"
                className="btn btn-sm"
                disabled={createLocal.isPending || !name.trim() || !slug.trim()}
                onClick={() => createLocal.mutate()}
              >
                {createLocal.isPending ? "Creating…" : "Create & bind"}
              </button>
            </div>
          </div>
        )}

        <div className="modal-actions">
          <button type="button" className="btn btn-secondary btn-sm" onClick={onClose}>
            Done
          </button>
        </div>
      </div>
    </div>
  );
}
