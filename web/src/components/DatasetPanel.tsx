import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { api } from "../api/client";
import type { ColumnMeta, Dataset, TableMeta, TableRole } from "../types";
import { CONNECTOR_LABELS } from "../types";
import { isStructuredSqlConnector } from "../utils/structuredSql";
import { mergeRelationshipsSection } from "../utils/definitionRelationships";

import { DatasetRagTab } from "./DatasetRagTab";

type Tab = "definition" | "connection" | "data" | "rag";

type PgForm = Record<string, string | number>;

function tabLabel(tab: Tab): string {
  if (tab === "rag") return "RAG";
  return tab;
}

function visibleTabs(_connector: string): Tab[] {
  return ["definition", "data", "rag", "connection"];
}

const CONNECTOR_OPTIONS = ["trino", "upload", "file_path", "api", "sharepoint", "web_url"] as const;

function normalizeConnectionConfig(connector: string, form: PgForm, existing: PgForm, dataset?: Dataset): Record<string, unknown> {
  const merged = { ...existing, ...form };
  if (connector === "api") {
    const raw = form.endpoints ?? existing.endpoints ?? "";
    const paths =
      typeof raw === "string"
        ? raw
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean)
        : Array.isArray(raw)
          ? raw
          : [""];
    merged.endpoints = paths.length ? paths : [""];
  }
  if (!isStructuredSqlConnector(connector) && dataset && !merged.path) {
    merged.path = `data/${dataset.domain_slug}/${dataset.slug}`;
  }
  return merged;
}

function tableRoleLabel(role?: TableRole): string {
  switch (role) {
    case "lookup":
      return "Lookup";
    case "excluded":
      return "Excluded";
    case "fact":
    default:
      return "Fact / dimension";
  }
}

function dataTabHint(connector: string): string {
  switch (connector) {
    case "trino":
    case "postgres":
      return "Discover tables and edit column labels.";
    case "upload":
      return "Upload files for this dataset.";
    case "file_path":
      return "Set folder path and refresh files.";
    case "api":
      return "Sync API endpoints into the dataset cache, then ingest on RAG.";
    case "sharepoint":
      return "Sync SharePoint content, then ingest on RAG.";
    case "web_url":
      return "Sync web URLs into the dataset cache, then ingest on RAG.";
    default:
      return "";
  }
}

const REMOTE_CONNECTORS = new Set(["api", "web_url", "sharepoint"]);

function SaveNotice({ show, message = "Saved" }: { show: boolean; message?: string }) {
  if (!show) return null;
  return (
    <p className="alert-ok" role="status">
      {message}
    </p>
  );
}

function ErrorNotice({ error }: { error: Error | null }) {
  if (!error) return null;
  return <p className="alert-error">{error.message || "Request failed"}</p>;
}

/** Brief green confirmation — pass a counter incremented on each successful save. */
function useSaveFlash(saveCount: number, ms = 3000) {
  const [show, setShow] = useState(false);
  useEffect(() => {
    if (saveCount < 1) return;
    setShow(true);
    const t = window.setTimeout(() => setShow(false), ms);
    return () => window.clearTimeout(t);
  }, [saveCount, ms]);
  return show;
}

/** Persist connection form to API before operations that read stored config. */
async function persistConnection(
  datasetId: string,
  connector: string,
  form: Record<string, string | number>,
  existing: Record<string, unknown>,
  dataset?: Dataset,
) {
  return api.updateDataset(datasetId, {
    config: normalizeConnectionConfig(connector, form, existing as PgForm, dataset),
  });
}

export function DatasetPanel({
  dataset,
  initialTab,
}: {
  dataset: Dataset;
  initialTab?: Tab;
}) {
  const tabs = useMemo(() => visibleTabs(dataset.connector), [dataset.connector]);
  const [tab, setTab] = useState<Tab>(() =>
    initialTab && visibleTabs(dataset.connector).includes(initialTab) ? initialTab : "definition",
  );
  const initialTabApplied = useRef(false);
  const qc = useQueryClient();
  const [desc, setDesc] = useState(dataset.description || "");
  const [pgForm, setPgForm] = useState<PgForm>(() => ({ ...(dataset.config as PgForm) }));

  useEffect(() => {
    initialTabApplied.current = false;
  }, [dataset.id]);

  useEffect(() => {
    if (!initialTab || initialTabApplied.current) return;
    if (tabs.includes(initialTab)) {
      setTab(initialTab);
      initialTabApplied.current = true;
    }
  }, [dataset.id, initialTab, tabs]);

  useEffect(() => {
    setPgForm({ ...(dataset.config as PgForm) });
  }, [dataset.id, dataset.config]);

  useEffect(() => {
    if (!tabs.includes(tab)) setTab("definition");
  }, [dataset.connector, tab, tabs]);

  const { data: definition } = useQuery({
    queryKey: ["definition", dataset.id],
    queryFn: () => api.getDefinition(dataset.id),
  });

  const [md, setMd] = useState("");
  useEffect(() => {
    if (definition?.markdown != null) setMd(definition.markdown);
  }, [definition?.markdown, dataset.id]);

  const [descSaveCount, setDescSaveCount] = useState(0);
  const [defSaveCount, setDefSaveCount] = useState(0);

  const saveDesc = useMutation({
    mutationFn: () => api.updateDataset(dataset.id, { description: desc }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["datasets"] });
      setDescSaveCount((n) => n + 1);
    },
  });

  const saveDef = useMutation({
    mutationFn: () => api.saveDefinition(dataset.id, md),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["definition", dataset.id] });
      setDefSaveCount((n) => n + 1);
    },
  });

  const descSaved = useSaveFlash(descSaveCount);
  const defSaved = useSaveFlash(defSaveCount);

  const { data: catalogTables } = useQuery({
    queryKey: ["tables", dataset.id],
    queryFn: () => api.catalogTables(dataset.id),
    enabled: tab === "definition" && isStructuredSqlConnector(dataset.connector),
  });

  const catalogTablesFingerprint = useMemo(
    () =>
      catalogTables
        ?.map((t) => `${t.id}:${t.table_role ?? "fact"}:${t.table_schema}.${t.table_name}`)
        .sort()
        .join("|") ?? "",
    [catalogTables],
  );

  const relationshipsFingerprintRef = useRef("");
  const [relationshipsNotice, setRelationshipsNotice] = useState<string | null>(null);

  const refreshRelationships = useMutation({
    mutationFn: () => api.getDefinitionRelationships(dataset.id),
    onSuccess: (data) => {
      setMd((prev) => mergeRelationshipsSection(prev, data.markdown_section));
      const count = data.relationships.length;
      setRelationshipsNotice(
        count
          ? `Relationships updated (${count} join path${count === 1 ? "" : "s"} inferred). Save definition to persist.`
          : "Relationships section updated (no joins inferred yet). Save definition to persist.",
      );
    },
  });

  const draftDef = useMutation({
    mutationFn: () => api.draftDefinition(dataset.id),
    onSuccess: (r) => {
      setMd(r.markdown);
      relationshipsFingerprintRef.current = catalogTablesFingerprint;
      qc.invalidateQueries({ queryKey: ["definition", dataset.id] });
      setRelationshipsNotice("AI draft applied with catalog-grounded content and refreshed relationships.");
    },
  });

  useEffect(() => {
    relationshipsFingerprintRef.current = "";
    setRelationshipsNotice(null);
  }, [dataset.id]);

  useEffect(() => {
    if (tab !== "definition" || !isStructuredSqlConnector(dataset.connector)) return;
    if (definition === undefined) return;
    if ((catalogTables?.length ?? 0) < 2) return;
    if (!catalogTablesFingerprint) return;
    if (catalogTablesFingerprint === relationshipsFingerprintRef.current) return;
    relationshipsFingerprintRef.current = catalogTablesFingerprint;
    refreshRelationships.mutate();
  }, [tab, dataset.connector, definition, catalogTablesFingerprint, catalogTables?.length]);

  return (
    <div className="card-pad">
      <div className="mb-4">
        <label className="label" htmlFor={`dataset-desc-${dataset.id}`}>
          Short description
        </label>
        <div className="flex flex-wrap items-center gap-3">
          <input
            id={`dataset-desc-${dataset.id}`}
            className="input mb-0 min-w-[200px] flex-1"
            value={desc}
            onChange={(e) => setDesc(e.target.value)}
          />
          <button
            type="button"
            className="btn btn-secondary shrink-0"
            onClick={() => saveDesc.mutate()}
            disabled={saveDesc.isPending}
          >
            {saveDesc.isPending ? "Saving…" : "Save description"}
          </button>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <SaveNotice show={descSaved} message="Description saved" />
          <ErrorNotice error={saveDesc.isError ? saveDesc.error : null} />
        </div>
      </div>

      <div className="tabs">
        {tabs.map((t) => (
          <button
            key={t}
            type="button"
            className={`tab ${tab === "rag" ? "" : "capitalize"} ${tab === t ? "tab-active" : ""}`}
            onClick={() => setTab(t)}
          >
            {tabLabel(t)}
          </button>
        ))}
      </div>

      {tab === "definition" && (
        <div className="space-y-4">
          <p className="text-sm text-zinc-500">
            Markdown definition for analysts and LLMs.
            {isStructuredSqlConnector(dataset.connector) && (catalogTables?.length ?? 0) >= 2 && (
              <> Table relationships are inferred from catalog roles and columns and appended automatically below.</>
            )}
          </p>
          <textarea
            className="textarea dataset-definition-textarea font-mono"
            rows={6}
            value={md}
            onChange={(e) => setMd(e.target.value)}
            placeholder="# Dataset definition"
          />
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" className="btn" onClick={() => saveDef.mutate()} disabled={saveDef.isPending}>
              {saveDef.isPending ? "Saving…" : "Save definition"}
            </button>
            <SaveNotice show={defSaved} message="Definition saved" />
            <ErrorNotice error={saveDef.isError ? saveDef.error : null} />
            <button type="button" className="btn btn-secondary" onClick={() => draftDef.mutate()} disabled={draftDef.isPending}>
              {draftDef.isPending ? "Drafting…" : "AI draft"}
            </button>
            {isStructuredSqlConnector(dataset.connector) && (catalogTables?.length ?? 0) >= 2 && (
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => refreshRelationships.mutate()}
                disabled={refreshRelationships.isPending}
              >
                {refreshRelationships.isPending ? "Inferring…" : "Refresh relationships"}
              </button>
            )}
            <a
              className="btn btn-secondary"
              href={`data:text/markdown,${encodeURIComponent(md)}`}
              download={`${dataset.slug}_definition.md`}
            >
              Download
            </a>
          </div>
          {relationshipsNotice && (
            <p className="alert-ok text-sm" role="status">
              {relationshipsNotice}
            </p>
          )}
          <ErrorNotice error={refreshRelationships.isError ? refreshRelationships.error : null} />
          {md && (
            <details className="catalog-themed-box">
              <summary className="cursor-pointer text-sm font-medium">Preview</summary>
              <div className="prose-chat mt-3">
                <ReactMarkdown>{md}</ReactMarkdown>
              </div>
            </details>
          )}
        </div>
      )}

      {tab === "connection" && <ConnectionTab dataset={dataset} pgForm={pgForm} setPgForm={setPgForm} />}
      {tab === "data" && <DataTab dataset={dataset} pgForm={pgForm} />}
      {tab === "rag" && <DatasetRagTab dataset={dataset} />}
    </div>
  );
}

function ConnectionTab({
  dataset,
  pgForm,
  setPgForm,
}: {
  dataset: Dataset;
  pgForm: PgForm;
  setPgForm: (f: PgForm) => void;
}) {
  const connector = dataset.connector;
  const existingConfig = (dataset.config ?? {}) as PgForm;
  const [form, setForm] = useState<PgForm>(() => ({ ...existingConfig }));
  const qc = useQueryClient();

  useEffect(() => {
    const cfg = { ...(dataset.config as PgForm) };
    if (connector === "api" && Array.isArray(cfg.endpoints)) {
      cfg.endpoints = cfg.endpoints.join(", ");
    }
    setForm(cfg);
  }, [dataset.id, dataset.config, connector]);

  const [connSaveCount, setConnSaveCount] = useState(0);

  const saveConfig = async () => {
    const payload = normalizeConnectionConfig(
      connector,
      connector === "trino" || isStructuredSqlConnector(connector) ? pgForm : form,
      existingConfig,
      dataset,
    );
    return api.updateDataset(dataset.id, { config: payload });
  };

  const save = useMutation({
    mutationFn: saveConfig,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["datasets"] });
      qc.invalidateQueries({ queryKey: ["summary", dataset.id] });
      setConnSaveCount((n) => n + 1);
    },
  });

  const connectionSaved = useSaveFlash(connSaveCount);

  const changeConnector = useMutation({
    mutationFn: (next: string) => api.updateDataset(dataset.id, { connector: next }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["datasets"] });
      qc.invalidateQueries({ queryKey: ["summary", dataset.id] });
    },
  });

  const test = useMutation({
    mutationFn: async () => {
      await saveConfig();
      return api.testConnection(dataset.id);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["datasets"] }),
  });

  const connName = String(pgForm.connection_name ?? "");

  return (
    <div className="max-w-3xl space-y-5">
      <div className="field mb-0 max-w-md">
        <label className="label">Connection type</label>
        <select
          className="select"
          value={connector}
          disabled={changeConnector.isPending}
          onChange={(e) => {
            const next = e.target.value;
            if (next !== connector && window.confirm(`Change connection type to ${CONNECTOR_LABELS[next] ?? next}?`)) {
              changeConnector.mutate(next);
            }
          }}
        >
          {CONNECTOR_OPTIONS.map((c) => (
            <option key={c} value={c}>
              {CONNECTOR_LABELS[c]}
            </option>
          ))}
        </select>
        <p className="mt-1 text-xs" style={{ color: "var(--color-text-muted)" }}>
          {CONNECTOR_LABELS[connector] ?? connector} — {dataset.source_type}
        </p>
      </div>

      {isStructuredSqlConnector(connector) && (
        <>
          <p className="text-sm" style={{ color: "var(--color-text-muted)" }}>
            Trino catalog and schema for this dataset. Use the <strong>Data</strong> tab to discover tables.
            {connName ? ` Linked from «${connName}».` : ""}
          </p>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="field mb-0">
              <label className="label">Trino catalog</label>
              <input
                className="input font-mono text-xs"
                value={String(pgForm.catalog ?? "")}
                onChange={(e) => setPgForm({ ...pgForm, catalog: e.target.value })}
              />
            </div>
            <div className="field mb-0">
              <label className="label">Schema</label>
              <input
                className="input font-mono text-xs"
                value={String(pgForm.schema ?? "public")}
                onChange={(e) => setPgForm({ ...pgForm, schema: e.target.value })}
              />
            </div>
          </div>
        </>
      )}

      {connector === "upload" && (
        <p className="text-sm" style={{ color: "var(--color-text-muted)" }}>
          Files upload to <code className="text-xs">{String(existingConfig.path ?? "data/…")}</code>. Use the{" "}
          <strong>Data</strong> tab to add files, then <strong>RAG</strong> to embed.
        </p>
      )}

      {connector === "file_path" && (
        <div className="field mb-0">
          <label className="label">Folder path</label>
          <input
            className="input"
            placeholder="sample_docs or data/domain/dataset"
            value={String(form.path ?? "")}
            onChange={(e) => setForm({ ...form, path: e.target.value })}
          />
        </div>
      )}

      {(connector === "web_url" || connector === "sharepoint") && (
        <>
          <p className="text-sm" style={{ color: "var(--color-text-muted)" }}>
            {connector === "sharepoint" ? "SharePoint or direct document URL." : "Public web page URL."} Sync on the{" "}
            <strong>Data</strong> tab after saving.
          </p>
          <div className="field mb-0">
            <label className="label">URL</label>
            <input
              className="input"
              type="url"
              placeholder="https://…"
              value={String(form.url ?? "")}
              onChange={(e) => setForm({ ...form, url: e.target.value })}
            />
          </div>
          {connector === "sharepoint" && (
            <div className="field mb-0">
              <label className="label">Auth token (optional Bearer)</label>
              <input
                className="input"
                type="password"
                value={String(form.auth_token ?? "")}
                onChange={(e) => setForm({ ...form, auth_token: e.target.value })}
              />
            </div>
          )}
        </>
      )}

      {connector === "api" && (
        <>
          <p className="text-sm" style={{ color: "var(--color-text-muted)" }}>
            REST API source. Sync on the <strong>Data</strong> tab after saving.
          </p>
          <div className="field mb-0">
            <label className="label">Base URL</label>
            <input
              className="input"
              type="url"
              placeholder="https://api.example.com"
              value={String(form.base_url ?? "")}
              onChange={(e) => setForm({ ...form, base_url: e.target.value })}
            />
          </div>
          <div className="field mb-0">
            <label className="label">Endpoints (comma-separated paths)</label>
            <input
              className="input"
              placeholder="/v1/products, /v1/pricing"
              value={String(form.endpoints ?? "")}
              onChange={(e) => setForm({ ...form, endpoints: e.target.value })}
            />
          </div>
          <div className="field mb-0">
            <label className="label">Auth token (optional Bearer)</label>
            <input
              className="input"
              type="password"
              value={String(form.auth_token ?? "")}
              onChange={(e) => setForm({ ...form, auth_token: e.target.value })}
            />
          </div>
        </>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className="btn" onClick={() => save.mutate()} disabled={save.isPending}>
          {save.isPending ? "Saving…" : "Save connection"}
        </button>
        {connector !== "upload" && (
          <button type="button" className="btn btn-secondary" onClick={() => test.mutate()} disabled={test.isPending}>
            {test.isPending ? "Testing…" : "Test connection"}
          </button>
        )}
        <SaveNotice show={connectionSaved} message="Connection saved" />
      </div>
      <ErrorNotice error={save.isError ? save.error : null} />
      {test.data && <p className={test.data.ok ? "alert-ok" : "alert-error"}>{test.data.message}</p>}
      <ErrorNotice error={test.isError ? test.error : null} />
      <ErrorNotice error={changeConnector.isError ? changeConnector.error : null} />
    </div>
  );
}

function PostgresDataTab({ dataset, pgForm }: { dataset: Dataset; pgForm: PgForm }) {
  const qc = useQueryClient();
  const [addCount, setAddCount] = useState(0);
  const [tableSearch, setTableSearch] = useState("");
  const tablesAdded = useSaveFlash(addCount);

  const refresh = useMutation({
    mutationFn: async () => {
      await persistConnection(dataset.id, dataset.connector, pgForm, dataset.config ?? {}, dataset);
      return api.remoteTables(dataset.id);
    },
  });

  const { data: tables, refetch: refetchTables } = useQuery({
    queryKey: ["tables", dataset.id],
    queryFn: () => api.catalogTables(dataset.id),
  });

  const [selectedRemote, setSelectedRemote] = useState<string[]>([]);
  const addTables = useMutation({
    mutationFn: async () => {
      await persistConnection(dataset.id, dataset.connector, pgForm, dataset.config ?? {}, dataset);
      return api.addTables(dataset.id, selectedRemote);
    },
    onSuccess: async () => {
      await refetchTables();
      qc.invalidateQueries({ queryKey: ["summary", dataset.id] });
      qc.invalidateQueries({ queryKey: ["datasets"] });
      setSelectedRemote([]);
      setAddCount((n) => n + 1);
    },
  });

  const catalogedNames = new Set(tables?.map((t) => t.table_name) ?? []);
  const remoteTables = refresh.data?.tables ?? [];
  const q = tableSearch.trim().toLowerCase();
  const filteredRemoteTables = q
    ? remoteTables.filter((t) => t.toLowerCase().includes(q))
    : remoteTables;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-zinc-500">
          {tables?.length
            ? `${tables.length} table(s) in catalog.`
            : "No tables yet — refresh from database."}
        </p>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => refresh.mutate()} disabled={refresh.isPending}>
          {refresh.isPending ? "Loading…" : "Refresh tables"}
        </button>
      </div>
      <ErrorNotice error={refresh.isError ? refresh.error : null} />

      {refresh.data && (
        <div className="catalog-themed-box">
          <div className="mb-2 flex flex-wrap items-center gap-3">
            <label className="label mb-0 min-w-0 flex-1">
              Tables in schema <strong>{String(pgForm.schema || "public")}</strong> ({remoteTables.length} found
              {q ? `, ${filteredRemoteTables.length} shown` : ""})
            </label>
            <input
              type="search"
              className="input table-search-input"
              placeholder="Search…"
              value={tableSearch}
              onChange={(e) => setTableSearch(e.target.value)}
              aria-label="Filter tables"
            />
          </div>
          <div className="table-wrap dataset-data-table">
            <table className="data">
              <thead>
                <tr>
                  <th className="w-10" aria-label="Select" />
                  <th>Table</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {filteredRemoteTables.length === 0 && (
                  <tr>
                    <td colSpan={3} className="text-sm" style={{ color: "var(--color-text-muted)" }}>
                      No tables match &quot;{tableSearch}&quot;.
                    </td>
                  </tr>
                )}
                {filteredRemoteTables.map((t) => {
                  const inCatalog = catalogedNames.has(t);
                  return (
                    <tr key={t}>
                      <td>
                        <input
                          type="checkbox"
                          checked={selectedRemote.includes(t)}
                          disabled={inCatalog}
                          aria-label={`Select ${t}`}
                          onChange={(e) =>
                            setSelectedRemote((prev) =>
                              e.target.checked ? [...prev, t] : prev.filter((x) => x !== t),
                            )
                          }
                        />
                      </td>
                      <td className="font-medium">{t}</td>
                      <td>
                        {inCatalog ? (
                          <span className="badge badge-ok">In catalog</span>
                        ) : (
                          <span className="badge badge-muted">Available</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <button
              type="button"
              className="btn btn-sm"
              disabled={!selectedRemote.length || addTables.isPending}
              onClick={() => addTables.mutate()}
            >
              {addTables.isPending ? "Adding…" : `Add selected (${selectedRemote.length})`}
            </button>
            <SaveNotice show={tablesAdded} message="Tables added — columns synced from database" />
          </div>
          <ErrorNotice error={addTables.isError ? addTables.error : null} />
        </div>
      )}

      {!refresh.data && !tables?.length && (
        <p className="text-sm text-zinc-500">Refresh tables, then add to catalog.</p>
      )}

      {tables && tables.length > 0 && <TableEditor datasetId={dataset.id} tables={tables} />}
    </div>
  );
}

function TableEditor({ datasetId, tables }: { datasetId: string; tables: TableMeta[] }) {
  const [active, setActive] = useState(() => tables[0]?.id ?? "");
  const qc = useQueryClient();
  const table = tables.find((t) => t.id === active);

  useEffect(() => {
    if (active && !tables.some((t) => t.id === active)) {
      setActive("");
    }
  }, [tables, active]);

  const { data: columns, isLoading: columnsLoading } = useQuery({
    queryKey: ["columns", active],
    queryFn: () => api.listColumns(active!),
    enabled: !!active,
  });

  const [syncCount, setSyncCount] = useState(0);
  const [syncNotice, setSyncNotice] = useState<string | null>(null);
  const [tblSaveCount, setTblSaveCount] = useState(0);
  const [labelSaveCount, setLabelSaveCount] = useState(0);
  const [labelEdits, setLabelEdits] = useState<Record<string, string[]>>({});
  const labelEditsRef = useRef(labelEdits);
  labelEditsRef.current = labelEdits;
  const [flushInputs, setFlushInputs] = useState(0);

  useEffect(() => {
    if (columns) {
      setLabelEdits(Object.fromEntries(columns.map((c) => [c.id, [...c.labels]])));
    }
  }, [columns, active]);

  const sync = useMutation({
    mutationFn: () => api.syncColumns(active!),
    onSuccess: (result) => {
      qc.setQueryData(["columns", active], result.columns);
      const s = result.stats;
      const changed = s.added + s.updated + s.removed;
      setSyncNotice(
        changed
          ? `Synced: ${s.added} added, ${s.updated} updated, ${s.removed} removed.`
          : "Schema in sync — no changes.",
      );
      setSyncCount((n) => n + 1);
    },
  });

  const syncFlash = useSaveFlash(syncCount);
  const tblSaved = useSaveFlash(tblSaveCount);
  const labelsSaved = useSaveFlash(labelSaveCount);

  const labelsDirty =
    columns?.some((c) => !labelsEqual(labelEdits[c.id] ?? c.labels, c.labels)) ?? false;

  const saveLabels = useMutation({
    mutationFn: async () => {
      if (!columns) return;
      const edits = labelEditsRef.current;
      const pending = columns.filter((c) => !labelsEqual(edits[c.id] ?? c.labels, c.labels));
      await Promise.all(
        pending.map((c) =>
          api.updateColumn(c.id, { labels: edits[c.id] ?? c.labels, description: c.description }),
        ),
      );
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["columns", active] });
      setLabelSaveCount((n) => n + 1);
    },
  });

  useEffect(() => {
    if (flushInputs === 0) return;
    const timer = window.setTimeout(() => saveLabels.mutate(), 0);
    return () => window.clearTimeout(timer);
  }, [flushInputs]);

  const [def, setDef] = useState(table?.definition ?? "");
  useEffect(() => {
    setDef(table?.definition ?? "");
  }, [table?.id, table?.definition]);

  const saveDef = useMutation({
    mutationFn: () => api.updateTable(active!, { definition: def }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tables"] });
      setTblSaveCount((n) => n + 1);
    },
  });

  const saveRole = useMutation({
    mutationFn: ({ tableId, role }: { tableId: string; role: TableRole }) =>
      api.updateTable(tableId, { table_role: role }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tables"] });
    },
  });

  const removeTable = useMutation({
    mutationFn: () => api.deleteTable(active!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tables", datasetId] });
      qc.invalidateQueries({ queryKey: ["summary", datasetId] });
      qc.invalidateQueries({ queryKey: ["datasets"] });
      setActive("");
    },
  });

  const onRemoveTable = () => {
    if (!table) return;
    const label = `${table.table_schema}.${table.table_name}`;
    if (
      window.confirm(
        `Remove "${label}" from this dataset? Catalog metadata and column labels for this table will be deleted.`,
      )
    ) {
      removeTable.mutate();
    }
  };

  const selectTable = (tableId: string) => setActive(tableId);

  return (
    <div className="catalog-themed-box">
      <label className="label">Table metadata &amp; columns ({tables.length} tables)</label>
      <p className="mb-2 text-xs" style={{ color: "var(--color-text-faint)" }}>
        Click a row to edit the table definition and column labels. Set role from the dropdown in each row.
      </p>
      <div className="table-wrap catalog-table-picker dataset-data-table mb-4">
        <table className="data">
          <thead>
            <tr>
              <th>Table</th>
              <th>Role</th>
            </tr>
          </thead>
          <tbody>
            {tables.map((t) => {
              const isActive = active === t.id;
              const role = t.table_role ?? "fact";
              const roleSaving = saveRole.isPending && saveRole.variables?.tableId === t.id;
              return (
                <tr
                  key={t.id}
                  className={`catalog-table-picker-row${isActive ? " catalog-table-picker-row--active" : ""}`}
                  onClick={() => selectTable(t.id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      selectTable(t.id);
                    }
                  }}
                  tabIndex={0}
                  role="button"
                  aria-pressed={isActive}
                  aria-label={`${t.table_schema}.${t.table_name}, ${tableRoleLabel(role)}`}
                >
                  <td className="font-medium">
                    {t.table_schema}.{t.table_name}
                  </td>
                  <td onClick={(e) => e.stopPropagation()} onKeyDown={(e) => e.stopPropagation()}>
                    <select
                      className="select catalog-table-picker-select"
                      value={role}
                      disabled={roleSaving}
                      aria-label={`Role for ${t.table_schema}.${t.table_name}`}
                      onChange={(e) =>
                        saveRole.mutate({ tableId: t.id, role: e.target.value as TableRole })
                      }
                    >
                      <option value="fact">Fact / dimension</option>
                      <option value="lookup">Lookup</option>
                      <option value="excluded">Excluded</option>
                    </select>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <ErrorNotice error={saveRole.isError ? saveRole.error : null} />
      <ErrorNotice error={removeTable.isError ? removeTable.error : null} />
      {table && (
        <>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2 border-t pt-3" style={{ borderColor: "var(--color-border-light)" }}>
        <p className="text-sm font-medium" style={{ color: "var(--color-text)" }}>
          {table.table_schema}.{table.table_name}
        </p>
        <button
          type="button"
          className="btn-ghost btn-sm shrink-0"
          style={{ color: "var(--color-alert-error-text)" }}
          disabled={removeTable.isPending}
          onClick={onRemoveTable}
        >
          {removeTable.isPending ? "Removing…" : "Remove table"}
        </button>
      </div>
      <textarea
        className="textarea mb-2 min-h-[72px]"
        value={def}
        onChange={(e) => setDef(e.target.value)}
        placeholder="Business definition of this table…"
      />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => saveDef.mutate()} disabled={saveDef.isPending}>
          {saveDef.isPending ? "Saving…" : "Save table definition"}
        </button>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => sync.mutate()} disabled={sync.isPending}>
          {sync.isPending ? "Syncing…" : "Re-sync columns from DB"}
        </button>
        <SaveNotice show={tblSaved} message="Table definition saved" />
        <SaveNotice show={syncFlash} message="Sync complete" />
      </div>
      {syncNotice && <p className="alert-ok text-sm">{syncNotice}</p>}
      <ErrorNotice error={saveDef.isError ? saveDef.error : null} />
      <ErrorNotice error={sync.isError ? sync.error : null} />

      {columnsLoading && <p className="text-sm text-zinc-500">Loading columns…</p>}
      {!columnsLoading && columns?.length === 0 && (
        <p className="alert-error text-sm">No columns — click Re-sync columns from DB.</p>
      )}
      {columns && columns.length > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <button
            type="button"
            className="btn btn-sm"
            disabled={!labelsDirty || saveLabels.isPending}
            onClick={() => setFlushInputs((n) => n + 1)}
          >
            {saveLabels.isPending ? "Saving…" : "Save column labels"}
          </button>
          <SaveNotice show={labelsSaved} message="Column labels saved" />
          <ErrorNotice error={saveLabels.isError ? saveLabels.error : null} />
          {labelsDirty && !saveLabels.isPending && (
            <span className="text-xs" style={{ color: "var(--color-text-faint)" }}>
              Unsaved label changes
            </span>
          )}
        </div>
      )}
      <div className="column-label-list">
        {columns?.map((col) => (
          <ColumnRow
            key={col.id}
            col={col}
            labels={labelEdits[col.id] ?? col.labels}
            savedLabels={col.labels}
            flushInput={flushInputs}
            onLabelsChange={(next) => setLabelEdits((prev) => ({ ...prev, [col.id]: next }))}
          />
        ))}
      </div>
        </>
      )}
    </div>
  );
}

function labelsEqual(a: string[], b: string[]) {
  return a.length === b.length && a.every((v, i) => v === b[i]);
}

function ColumnRow({
  col,
  labels,
  savedLabels,
  flushInput,
  onLabelsChange,
}: {
  col: ColumnMeta;
  labels: string[];
  savedLabels: string[];
  flushInput: number;
  onLabelsChange: (labels: string[]) => void;
}) {
  const [input, setInput] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const labelsRef = useRef(labels);
  labelsRef.current = labels;
  const dirty = !labelsEqual(labels, savedLabels);

  useEffect(() => {
    setInput("");
  }, [col.id, savedLabels]);

  const commitRaw = (raw: string) => {
    const text = raw.trim();
    if (!text) return;
    const next = [...labelsRef.current];
    if (!next.includes(text)) next.push(text);
    onLabelsChange(next);
    setInput("");
  };

  const commitInput = () => commitRaw(input);

  useEffect(() => {
    if (flushInput === 0) return;
    commitRaw(inputRef.current?.value ?? input);
    // Only run when parent requests flush (Save column labels), not on each keystroke.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flushInput]);

  return (
    <div className={`column-label-row${dirty ? " column-label-row-dirty" : ""}`}>
      <div className="column-label-name">
        <span className="font-medium">{col.column_name}</span>{" "}
        <span className="text-zinc-400">({col.data_type || "?"})</span>
      </div>
      <div className="label-bubble-input" onClick={() => inputRef.current?.focus()}>
        {labels.map((label, i) => (
          <span key={`${label}-${i}`} className="label-bubble">
            {label}
            <button
              type="button"
              className="label-bubble-remove"
              aria-label={`Remove ${label}`}
              onClick={(e) => {
                e.stopPropagation();
                onLabelsChange(labels.filter((_, j) => j !== i));
              }}
            >
              ×
            </button>
          </span>
        ))}
        <input
          ref={inputRef}
          className="label-bubble-text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              commitInput();
            } else if (e.key === "Backspace" && !input && labels.length) {
              onLabelsChange(labels.slice(0, -1));
            }
          }}
          placeholder={labels.length ? "Add label, Enter…" : "Type label, press Enter…"}
        />
      </div>
    </div>
  );
}

function DataTab({ dataset, pgForm }: { dataset: Dataset; pgForm: PgForm }) {
  return (
    <div className="space-y-4">
      <p className="text-sm text-zinc-500">{dataTabHint(dataset.connector)}</p>
      {isStructuredSqlConnector(dataset.connector) && <PostgresDataTab dataset={dataset} pgForm={pgForm} />}
      {(dataset.connector === "upload" || dataset.connector === "file_path") && (
        <FileDataTab dataset={dataset} />
      )}
      {REMOTE_CONNECTORS.has(dataset.connector) && <RemoteDataTab dataset={dataset} />}
    </div>
  );
}

function CachedFilesTable({
  files,
}: {
  files: { name: string; size: number; ingested: boolean; chunks: number }[] | undefined;
}) {
  if (!files?.length) {
    return (
      <p className="catalog-themed-box--dashed py-10 text-sm" style={{ color: "var(--color-text-muted)" }}>
        No cached files yet. Sync or upload content, then configure RAG on the RAG tab.
      </p>
    );
  }
  return (
    <div className="table-wrap dataset-data-table">
      <table className="data">
        <thead>
          <tr>
            <th>File</th>
            <th>Status</th>
            <th>Chunks</th>
          </tr>
        </thead>
        <tbody>
          {files.map((f) => (
            <tr key={f.name}>
              <td>{f.name}</td>
              <td>{f.ingested ? <span className="badge-ok badge">In DB</span> : <span className="badge-muted badge">Pending</span>}</td>
              <td>{f.chunks}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatSyncError(err: unknown): string {
  const msg = err instanceof Error ? err.message : String(err);
  if (msg === "Not Found" || msg.includes("404")) {
    return "Sync failed (404). Check the URL on the Connection tab, or restart the API server if you recently updated the app.";
  }
  return msg;
}

function RemoteDataTab({ dataset }: { dataset: Dataset }) {
  const qc = useQueryClient();
  const configuredUrl = String((dataset.config?.url as string | undefined) ?? (dataset.config?.base_url as string | undefined) ?? "");
  const { data: assets } = useQuery({
    queryKey: ["assets", dataset.id],
    queryFn: () => api.listDatasetAssets(dataset.id),
  });
  const { data: files } = useQuery({
    queryKey: ["files", dataset.id],
    queryFn: () => api.listFiles(dataset.id),
  });

  const sync = useMutation({
    mutationFn: () => api.syncDataset(dataset.id, { full: false }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["assets", dataset.id] });
      qc.invalidateQueries({ queryKey: ["files", dataset.id] });
      qc.invalidateQueries({ queryKey: ["summary", dataset.id] });
      qc.invalidateQueries({ queryKey: ["dataset-rag", dataset.id] });
      qc.invalidateQueries({ queryKey: ["datasets"] });
    },
  });

  const lastSync = (dataset.config?.last_sync_at as string | undefined) ?? undefined;
  const syncFailed =
    sync.isSuccess &&
    (sync.data?.errors?.length ?? 0) > 0 &&
    !(sync.data?.assets_added.length || sync.data?.assets_updated.length);
  const syncPartial =
    sync.isSuccess &&
    (sync.data?.errors?.length ?? 0) > 0 &&
    ((sync.data?.assets_added.length ?? 0) > 0 || (sync.data?.assets_updated.length ?? 0) > 0);

  return (
    <div className="space-y-5">
      {!configuredUrl.trim() && (
        <p className="alert-error text-sm">
          No URL configured — open the <strong>Connection</strong> tab, enter the web link, and save before syncing.
        </p>
      )}
      <div className="catalog-themed-box">
        <p className="text-sm font-medium" style={{ color: "var(--color-text)" }}>
          Sync from {CONNECTOR_LABELS[dataset.connector] ?? dataset.connector}
        </p>
        <p className="mt-1 text-sm" style={{ color: "var(--color-text-muted)" }}>
          Fetches remote content into the dataset cache. Use the <strong>RAG</strong> tab to embed cached files.
          {configuredUrl.trim() ? (
            <>
              {" "}
              Source: <span className="break-all">{configuredUrl}</span>
            </>
          ) : null}
          {lastSync ? ` Last sync: ${new Date(lastSync).toLocaleString()}.` : ""}
        </p>
        <p className="mt-2 text-xs" style={{ color: "var(--color-text-muted)" }}>
          Many sites (e.g. Amazon) block automated downloads. If sync fails, upload a PDF/export instead (Uploaded files format).
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            type="button"
            className="btn btn-sm"
            disabled={sync.isPending || !configuredUrl.trim()}
            onClick={() => sync.mutate()}
          >
            {sync.isPending ? "Syncing…" : "Sync now"}
          </button>
          <SaveNotice
            show={sync.isSuccess && !syncFailed && !syncPartial && !!(sync.data?.assets_added.length || sync.data?.assets_updated.length)}
            message={`Synced ${(sync.data?.assets_added.length ?? 0) + (sync.data?.assets_updated.length ?? 0)} file(s)`}
          />
        </div>
        {syncFailed && (
          <p className="alert-error mt-2 text-sm">
            {(sync.data?.errors ?? []).map((e) => e.error || `${e.asset_id}: failed`).join(" ")}
          </p>
        )}
        {syncPartial && (
          <p className="alert-error mt-2 text-sm">
            Partial sync: {(sync.data?.errors ?? []).map((e) => e.error).join("; ")}
          </p>
        )}
        <ErrorNotice error={sync.isError ? new Error(formatSyncError(sync.error)) : null} />
      </div>

      {!!assets?.assets.length && (
        <div className="table-wrap dataset-data-table">
          <table className="data">
            <thead>
              <tr>
                <th>Source</th>
                <th>Kind</th>
                <th>Cached</th>
              </tr>
            </thead>
            <tbody>
              {assets.assets.map((asset) => (
                <tr key={asset.id}>
                  <td className="font-medium">{asset.name}</td>
                  <td>{asset.kind}</td>
                  <td>{asset.synced ? <span className="badge badge-ok">Yes</span> : <span className="badge badge-muted">No</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <CachedFilesTable files={files} />
    </div>
  );
}

function FileDataTab({ dataset }: { dataset: Dataset }) {
  const { data: files } = useQuery({
    queryKey: ["files", dataset.id],
    queryFn: () => api.listFiles(dataset.id),
  });
  const { data: fileTypes } = useQuery({
    queryKey: ["supported-file-types"],
    queryFn: () => api.supportedFileTypes(),
  });

  const [pendingUploads, setPendingUploads] = useState<File[]>([]);
  const [folderPath, setFolderPath] = useState(String((dataset.config?.path as string | undefined) ?? ""));
  const qc = useQueryClient();

  useEffect(() => {
    setFolderPath(String((dataset.config?.path as string | undefined) ?? ""));
  }, [dataset.id, dataset.config]);

  const savePath = useMutation({
    mutationFn: () => api.updateDataset(dataset.id, { config: { ...dataset.config, path: folderPath } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["datasets"] });
      qc.invalidateQueries({ queryKey: ["files", dataset.id] });
    },
  });

  const upload = useMutation({
    mutationFn: () => api.uploadFiles(dataset.id, pendingUploads),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["files", dataset.id] });
      qc.invalidateQueries({ queryKey: ["summary", dataset.id] });
      qc.invalidateQueries({ queryKey: ["dataset-rag", dataset.id] });
      setPendingUploads([]);
    },
  });

  const accept = fileTypes?.accept ?? ".pdf,.md,.txt,.json";
  const typeHint = fileTypes?.extensions.join(", ") ?? ".pdf, .md, .txt, .json";

  return (
    <div className="space-y-5">
      {dataset.connector === "file_path" && (
        <div className="catalog-themed-box">
          <div className="field mb-0">
            <label className="label">Folder path</label>
            <input
              className="input"
              value={folderPath}
              onChange={(e) => setFolderPath(e.target.value)}
              placeholder="sample_docs or data/domain/dataset"
            />
          </div>
          <button type="button" className="btn btn-sm mt-3" disabled={savePath.isPending} onClick={() => savePath.mutate()}>
            {savePath.isPending ? "Saving…" : "Save path"}
          </button>
          <ErrorNotice error={savePath.isError ? savePath.error : null} />
        </div>
      )}
      {dataset.connector === "upload" && (
      <div className="rounded-xl border border-dashed p-4" style={{ borderColor: "var(--color-border)" }}>
        <p className="text-sm font-medium" style={{ color: "var(--color-text)" }}>
          Upload files
        </p>
        <p className="mt-1 text-sm" style={{ color: "var(--color-text-muted)" }}>
          Supported: {typeHint}. Use the <strong>RAG</strong> tab to choose files and run Ingest &amp; embed.
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <label className="btn btn-secondary btn-sm file-upload-btn">
            Choose files
            <input
              type="file"
              className="file-upload-input"
              accept={accept}
              multiple
              onChange={(e) => setPendingUploads(Array.from(e.target.files ?? []))}
            />
          </label>
          <button
            type="button"
            className="btn btn-sm"
            disabled={!pendingUploads.length || upload.isPending}
            onClick={() => upload.mutate()}
          >
            {upload.isPending
              ? "Uploading…"
              : pendingUploads.length
                ? `Save ${pendingUploads.length} file${pendingUploads.length === 1 ? "" : "s"}`
                : "Save files"}
          </button>
        </div>
        {pendingUploads.length > 0 && (
          <p className="mt-2 text-xs" style={{ color: "var(--color-text-muted)" }}>
            Selected: {pendingUploads.map((f) => f.name).join(", ")}
          </p>
        )}
        {upload.data?.skipped?.length ? (
          <p className="alert-error mt-2 text-sm">
            Skipped: {upload.data.skipped.map((s) => `${s.name} (${s.reason})`).join("; ")}
          </p>
        ) : null}
        <SaveNotice show={upload.isSuccess && !!upload.data?.saved.length} message={`Uploaded ${upload.data?.saved.length} file(s)`} />
        <ErrorNotice error={upload.isError ? upload.error : null} />
      </div>
      )}

      <CachedFilesTable files={files} />
    </div>
  );
}
