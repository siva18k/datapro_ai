import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { api } from "../api/client";
import type { ColumnMeta, Dataset, TableMeta } from "../types";
import { CONNECTOR_LABELS } from "../types";

type Tab = "definition" | "connection" | "data";

type PgForm = Record<string, string | number>;

function visibleTabs(connector: string): Tab[] {
  if (connector === "upload" || connector === "file_path") {
    return ["definition", "data"];
  }
  return ["definition", "connection", "data"];
}

function dataTabHint(connector: string): string {
  switch (connector) {
    case "postgres":
      return "Discover tables and edit column labels.";
    case "upload":
      return "Upload files, then ingest to RAG.";
    case "file_path":
      return "Files in dataset folder — ingest to RAG.";
    case "api":
      return "API endpoints (coming soon).";
    case "sharepoint":
      return "SharePoint libraries (coming soon).";
    case "web_url":
      return "Web URLs (coming soon).";
    default:
      return "";
  }
}

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
async function persistConnection(datasetId: string, form: Record<string, string | number>) {
  return api.updateDataset(datasetId, { config: form });
}

export function DatasetPanel({ dataset }: { dataset: Dataset }) {
  const tabs = visibleTabs(dataset.connector);
  const [tab, setTab] = useState<Tab>("definition");
  const qc = useQueryClient();
  const [desc, setDesc] = useState(dataset.description || "");
  const [pgForm, setPgForm] = useState<PgForm>(() => ({ ...(dataset.config as PgForm) }));

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

  const draftDef = useMutation({
    mutationFn: () => api.draftDefinition(dataset.id),
    onSuccess: (r) => setMd(r.markdown),
  });

  const descSaved = useSaveFlash(descSaveCount);
  const defSaved = useSaveFlash(defSaveCount);

  return (
    <div className="card-pad">
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="field mb-0 min-w-[200px] flex-1">
          <label className="label">Short description</label>
          <input className="input" value={desc} onChange={(e) => setDesc(e.target.value)} />
        </div>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => saveDesc.mutate()} disabled={saveDesc.isPending}>
          {saveDesc.isPending ? "Saving…" : "Save description"}
        </button>
        <SaveNotice show={descSaved} message="Description saved" />
        <ErrorNotice error={saveDesc.isError ? saveDesc.error : null} />
      </div>

      <div className="tabs">
        {tabs.map((t) => (
          <button
            key={t}
            type="button"
            className={`tab capitalize ${tab === t ? "tab-active" : ""}`}
            onClick={() => setTab(t)}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "definition" && (
        <div className="space-y-4">
          <p className="text-sm text-zinc-500">Markdown definition for analysts and LLMs.</p>
          <textarea
            className="textarea min-h-[220px] font-mono"
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
            <a
              className="btn btn-secondary"
              href={`data:text/markdown,${encodeURIComponent(md)}`}
              download={`${dataset.slug}_definition.md`}
            >
              Download
            </a>
          </div>
          {md && (
            <details className="rounded-lg border border-zinc-200 bg-zinc-50 p-4">
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
  const [form, setForm] = useState<PgForm>({ ...(dataset.config as PgForm) });
  const qc = useQueryClient();

  useEffect(() => {
    setForm({ ...(dataset.config as PgForm) });
  }, [dataset.id, dataset.config]);

  const [connSaveCount, setConnSaveCount] = useState(0);

  const save = useMutation({
    mutationFn: () => persistConnection(dataset.id, dataset.connector === "postgres" ? pgForm : form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["datasets"] });
      setConnSaveCount((n) => n + 1);
    },
  });

  const connectionSaved = useSaveFlash(connSaveCount);

  const test = useMutation({
    mutationFn: async () => {
      const cfg = dataset.connector === "postgres" ? pgForm : form;
      await persistConnection(dataset.id, cfg);
      return api.testConnection(dataset.id);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["datasets"] }),
  });

  if (dataset.connector === "postgres") {
    const connName = String(pgForm.connection_name ?? "");
    return (
      <div className="space-y-5">
        <p className="text-sm" style={{ color: "var(--color-text-muted)" }}>
          Database credentials for this dataset. Use the <strong>Data</strong> tab to discover and catalog tables.
          {connName ? ` Linked from saved connection «${connName}».` : ""}
        </p>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {(
            [
              ["host", "Host / endpoint"],
              ["port", "Port"],
              ["database", "Database"],
              ["user", "Username"],
              ["password", "Password"],
              ["schema", "Schema"],
            ] as const
          ).map(([key, label]) => (
            <div key={key} className="field mb-0">
              <label className="label">{label}</label>
              <input
                className="input"
                type={key === "password" ? "password" : key === "port" ? "number" : "text"}
                value={String(pgForm[key] ?? "")}
                onChange={(e) =>
                  setPgForm({
                    ...pgForm,
                    [key]: key === "port" ? Number(e.target.value) : e.target.value,
                  })
                }
              />
            </div>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button type="button" className="btn" onClick={() => save.mutate()} disabled={save.isPending}>
            {save.isPending ? "Saving…" : "Save connection"}
          </button>
          <button type="button" className="btn btn-secondary" onClick={() => test.mutate()} disabled={test.isPending}>
            {test.isPending ? "Testing…" : "Test connection"}
          </button>
          <SaveNotice show={connectionSaved} message="Connection saved" />
        </div>
        <ErrorNotice error={save.isError ? save.error : null} />
        {test.data && <p className={test.data.ok ? "alert-ok" : "alert-error"}>{test.data.message}</p>}
        <ErrorNotice error={test.isError ? test.error : null} />
      </div>
    );
  }

  if (dataset.connector === "api" || dataset.connector === "sharepoint" || dataset.connector === "web_url") {
    return (
      <div className="max-w-lg space-y-4">
        <p className="text-sm text-zinc-500">Endpoint — configure data in the Data tab.</p>
        <div className="field mb-0">
          <label className="label">{dataset.connector === "api" ? "Base URL" : "URL"}</label>
          <input
            className="input"
            value={String(form.base_url ?? form.url ?? "")}
            onChange={(e) =>
              setForm({
                ...form,
                ...(dataset.connector === "api" ? { base_url: e.target.value } : { url: e.target.value }),
              })
            }
          />
        </div>
        <button type="button" className="btn" onClick={() => save.mutate()} disabled={save.isPending}>
          {save.isPending ? "Saving…" : "Save connection"}
        </button>
        <SaveNotice show={connectionSaved} message="Connection saved" />
        <ErrorNotice error={save.isError ? save.error : null} />
      </div>
    );
  }

  return null;
}

function PostgresDataTab({ dataset, pgForm }: { dataset: Dataset; pgForm: PgForm }) {
  const qc = useQueryClient();
  const [addCount, setAddCount] = useState(0);
  const [tableSearch, setTableSearch] = useState("");
  const tablesAdded = useSaveFlash(addCount);

  const refresh = useMutation({
    mutationFn: async () => {
      await persistConnection(dataset.id, pgForm);
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
      await persistConnection(dataset.id, pgForm);
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
        <div className="rounded-lg border border-zinc-200 p-4">
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
          <div className="flex max-h-48 flex-wrap gap-2 overflow-auto">
            {filteredRemoteTables.length === 0 && (
              <p className="text-sm text-zinc-500">No tables match &quot;{tableSearch}&quot;.</p>
            )}
            {filteredRemoteTables.map((t) => (
              <label
                key={t}
                className={`flex cursor-pointer items-center gap-1.5 rounded border px-2 py-1 text-sm ${
                  catalogedNames.has(t) ? "border-emerald-300 bg-emerald-50" : "border-zinc-200"
                }`}
              >
                <input
                  type="checkbox"
                  checked={selectedRemote.includes(t)}
                  disabled={catalogedNames.has(t)}
                  onChange={(e) =>
                    setSelectedRemote((prev) => (e.target.checked ? [...prev, t] : prev.filter((x) => x !== t)))
                  }
                />
                {t}
                {catalogedNames.has(t) && <span className="text-xs text-emerald-700">(in catalog)</span>}
              </label>
            ))}
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
  const [tableRole, setTableRole] = useState(table?.table_role ?? "fact");
  useEffect(() => {
    setDef(table?.definition ?? "");
    setTableRole(table?.table_role ?? "fact");
  }, [table?.id, table?.definition, table?.table_role]);

  const saveDef = useMutation({
    mutationFn: () =>
      api.updateTable(active!, { definition: def, table_role: tableRole }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tables"] });
      setTblSaveCount((n) => n + 1);
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

  return (
    <div className="rounded-lg border border-zinc-200 p-4">
      <label className="label">Table metadata &amp; columns ({tables.length} tables)</label>
      <div className="mb-3 flex max-w-md flex-wrap items-center gap-2">
        <select className="select min-w-0 flex-1" value={active} onChange={(e) => setActive(e.target.value)}>
          <option value="">Select a table…</option>
          {tables.map((t) => (
            <option key={t.id} value={t.id}>
              {t.table_schema}.{t.table_name}
            </option>
          ))}
        </select>
        {table && (
          <button
            type="button"
            className="btn-ghost btn-sm shrink-0 text-red-600 hover:bg-red-50"
            disabled={removeTable.isPending}
            onClick={onRemoveTable}
          >
            {removeTable.isPending ? "Removing…" : "Remove"}
          </button>
        )}
      </div>
      <ErrorNotice error={removeTable.isError ? removeTable.error : null} />
      {table && (
        <>
      <div className="mb-2 flex flex-wrap items-end gap-3">
        <div className="field mb-0 min-w-[10rem]">
          <label className="label">Table role</label>
          <select
            className="select"
            value={tableRole}
            onChange={(e) => setTableRole(e.target.value)}
          >
            <option value="fact">Fact / dimension (metadata only)</option>
            <option value="lookup">Lookup (metadata + row embeddings)</option>
            <option value="excluded">Excluded from RAG</option>
          </select>
        </div>
        <p className="pb-2 text-xs" style={{ color: "var(--color-text-faint)" }}>
          Lookup tables embed row values for direct retrieval; facts use catalog text only.
        </p>
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
      {dataset.connector === "postgres" && <PostgresDataTab dataset={dataset} pgForm={pgForm} />}
      {(dataset.connector === "upload" || dataset.connector === "file_path") && (
        <FileDataTab dataset={dataset} />
      )}
      {(dataset.connector === "api" || dataset.connector === "sharepoint" || dataset.connector === "web_url") && (
        <ConnectorDataPlaceholder connector={dataset.connector} />
      )}
    </div>
  );
}

function ConnectorDataPlaceholder({ connector }: { connector: string }) {
  return (
    <div className="rounded-lg border border-dashed border-zinc-200 px-6 py-12 text-center">
      <p className="text-sm font-medium text-zinc-700">{CONNECTOR_LABELS[connector] ?? connector} data sources</p>
      <p className="mt-2 text-sm text-zinc-500">Not wired yet — set endpoint in Connection.</p>
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

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [pendingUploads, setPendingUploads] = useState<File[]>([]);
  const qc = useQueryClient();

  const upload = useMutation({
    mutationFn: () => api.uploadFiles(dataset.id, pendingUploads),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["files", dataset.id] });
      qc.invalidateQueries({ queryKey: ["summary", dataset.id] });
      setPendingUploads([]);
      if (res.saved.length) {
        setSelected(new Set(res.saved));
      }
    },
  });

  const ingest = useMutation({
    mutationFn: () => api.ingest(dataset.id, [...selected]),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["files", dataset.id] });
      qc.invalidateQueries({ queryKey: ["summary", dataset.id] });
      setSelected(new Set());
    },
  });

  const accept = fileTypes?.accept ?? ".pdf,.md,.txt,.json";
  const typeHint = fileTypes?.extensions.join(", ") ?? ".pdf, .md, .txt, .json";

  return (
    <div className="space-y-5">
      <div className="rounded-xl border border-dashed p-4" style={{ borderColor: "var(--color-border)" }}>
        <p className="text-sm font-medium" style={{ color: "var(--color-text)" }}>
          Upload files
        </p>
        <p className="mt-1 text-sm" style={{ color: "var(--color-text-muted)" }}>
          Supported: {typeHint}. Word (.doc) is not supported yet — convert to PDF or text first.
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

      {!files?.length ? (
        <p className="rounded-lg border border-dashed border-zinc-200 py-10 text-center text-sm text-zinc-500">
          No files yet. Upload documents above, then ingest them into the knowledge base.
        </p>
      ) : (
        <>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th className="w-10" />
                  <th>File</th>
                  <th>Status</th>
                  <th>Chunks</th>
                </tr>
              </thead>
              <tbody>
                {files.map((f) => (
                  <tr key={f.name}>
                    <td>
                      <input
                        type="checkbox"
                        checked={selected.has(f.name)}
                        onChange={(e) => {
                          const next = new Set(selected);
                          if (e.target.checked) next.add(f.name);
                          else next.delete(f.name);
                          setSelected(next);
                        }}
                      />
                    </td>
                    <td>{f.name}</td>
                    <td>{f.ingested ? <span className="badge-ok badge">In DB</span> : <span className="badge-muted badge">Pending</span>}</td>
                    <td>{f.chunks}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <button type="button" className="btn mt-4" disabled={!selected.size || ingest.isPending} onClick={() => ingest.mutate()}>
            {ingest.isPending ? "Ingesting…" : `Ingest selected (${selected.size})`}
          </button>
          <ErrorNotice error={ingest.isError ? ingest.error : null} />
        </>
      )}
    </div>
  );
}
