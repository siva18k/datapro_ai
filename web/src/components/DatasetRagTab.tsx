import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { Dataset, FileRagRow, TableMeta, TableRole } from "../types";

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

type TableRowState = {
  id: string;
  name: string;
  role: TableRole;
  rag_enabled: boolean;
  chunk_size: string;
  chunk_overlap: string;
  ingested?: boolean;
  chunk_count?: number;
};

type FileRowState = {
  file_name: string;
  rag_enabled: boolean;
  chunk_size: string;
  chunk_overlap: string;
  ingested?: boolean;
  chunk_count?: number;
};

type RowSnapshot = {
  rag_enabled: boolean;
  chunk_size: string;
  chunk_overlap: string;
};

type DefaultSnapshot = {
  size: string;
  overlap: string;
};

function numOrNull(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const n = Number(trimmed);
  return Number.isFinite(n) && n > 0 ? Math.round(n) : null;
}

function effectiveChunkSize(row: { chunk_size: string }, defaults: DefaultSnapshot): string {
  return row.chunk_size.trim() || defaults.size;
}

function effectiveChunkOverlap(row: { chunk_overlap: string }, defaults: DefaultSnapshot): string {
  return row.chunk_overlap.trim() || defaults.overlap;
}

function rowNeedsIngest(
  row: {
    role?: TableRole;
    rag_enabled: boolean;
    chunk_size: string;
    chunk_overlap: string;
    ingested?: boolean;
  },
  embedded: RowSnapshot | undefined,
  currentDefaults: DefaultSnapshot,
  embeddedDefaults: DefaultSnapshot,
): boolean {
  if (row.role === "excluded" || !row.rag_enabled) return false;
  if (!row.ingested || !embedded) return true;
  if (embedded.rag_enabled !== row.rag_enabled) return true;

  const sizeNow = effectiveChunkSize(row, currentDefaults);
  const sizeWas = effectiveChunkSize(embedded, embeddedDefaults);
  if (sizeNow !== sizeWas) return true;

  const overlapNow = effectiveChunkOverlap(row, currentDefaults);
  const overlapWas = effectiveChunkOverlap(embedded, embeddedDefaults);
  return overlapNow !== overlapWas;
}

function snapshotFromTable(t: TableMeta): RowSnapshot {
  return {
    rag_enabled: t.rag_enabled ?? t.table_role !== "excluded",
    chunk_size: t.chunk_size != null ? String(t.chunk_size) : "",
    chunk_overlap: t.chunk_overlap != null ? String(t.chunk_overlap) : "",
  };
}

function snapshotFromFile(f: FileRagRow): RowSnapshot {
  return {
    rag_enabled: f.rag_enabled ?? true,
    chunk_size: f.chunk_size != null ? String(f.chunk_size) : "",
    chunk_overlap: f.chunk_overlap != null ? String(f.chunk_overlap) : "",
  };
}

function buildEmbeddedMaps(
  tables: TableMeta[] | undefined,
  files: FileRagRow[] | undefined,
): { tables: Map<string, RowSnapshot>; files: Map<string, RowSnapshot> } {
  const tableMap = new Map<string, RowSnapshot>();
  const fileMap = new Map<string, RowSnapshot>();
  for (const t of tables ?? []) {
    if (t.ingested && (t.rag_enabled ?? t.table_role !== "excluded")) {
      tableMap.set(t.id, snapshotFromTable(t));
    }
  }
  for (const f of files ?? []) {
    if (f.ingested && (f.rag_enabled ?? true)) {
      fileMap.set(f.file_name, snapshotFromFile(f));
    }
  }
  return { tables: tableMap, files: fileMap };
}

export function DatasetRagTab({ dataset }: { dataset: Dataset }) {
  const qc = useQueryClient();
  const isStructured = dataset.source_type === "structured";

  const { data, isLoading, error } = useQuery({
    queryKey: ["dataset-rag", dataset.id],
    queryFn: () => api.getDatasetRag(dataset.id),
  });

  const [profileInstructions, setProfileInstructions] = useState("");
  const [defaultChunkSize, setDefaultChunkSize] = useState("300");
  const [defaultChunkOverlap, setDefaultChunkOverlap] = useState("60");
  const [tableRows, setTableRows] = useState<TableRowState[]>([]);
  const [fileRows, setFileRows] = useState<FileRowState[]>([]);
  const [embeddedTables, setEmbeddedTables] = useState<Map<string, RowSnapshot>>(new Map());
  const [embeddedFiles, setEmbeddedFiles] = useState<Map<string, RowSnapshot>>(new Map());
  const [embeddedDefaults, setEmbeddedDefaults] = useState<DefaultSnapshot>({ size: "300", overlap: "60" });
  const [saveNotice, setSaveNotice] = useState<string | null>(null);
  const [ingestNotice, setIngestNotice] = useState<string | null>(null);

  const currentDefaults = useMemo(
    (): DefaultSnapshot => ({
      size: defaultChunkSize.trim() || "300",
      overlap: defaultChunkOverlap.trim() || "60",
    }),
    [defaultChunkSize, defaultChunkOverlap],
  );

  useEffect(() => {
    if (!data?.profile) return;
    setProfileInstructions(data.profile.instructions || "");
    setDefaultChunkSize(String(data.profile.chunk_size ?? 300));
    setDefaultChunkOverlap(String(data.profile.chunk_overlap ?? 60));
    setEmbeddedDefaults({
      size: String(data.profile.chunk_size ?? 300),
      overlap: String(data.profile.chunk_overlap ?? 60),
    });
  }, [data?.profile]);

  useEffect(() => {
    if (!data) return;
    const embedded = buildEmbeddedMaps(data.tables, data.files);
    setEmbeddedTables(embedded.tables);
    setEmbeddedFiles(embedded.files);

    if (data.tables) {
      setTableRows(
        data.tables.map((t: TableMeta) => ({
          id: t.id,
          name: `${t.table_schema}.${t.table_name}`,
          role: (t.table_role ?? "fact") as TableRole,
          rag_enabled: t.rag_enabled ?? t.table_role !== "excluded",
          chunk_size: t.chunk_size != null ? String(t.chunk_size) : "",
          chunk_overlap: t.chunk_overlap != null ? String(t.chunk_overlap) : "",
          ingested: t.ingested,
          chunk_count: t.chunk_count,
        })),
      );
    }
    if (data.files) {
      setFileRows(
        data.files.map((f: FileRagRow) => ({
          file_name: f.file_name,
          rag_enabled: f.rag_enabled ?? true,
          chunk_size: f.chunk_size != null ? String(f.chunk_size) : "",
          chunk_overlap: f.chunk_overlap != null ? String(f.chunk_overlap) : "",
          ingested: f.ingested,
          chunk_count: f.chunk_count,
        })),
      );
    }
  }, [data]);

  const pendingTableIds = useMemo(
    () =>
      tableRows
        .filter((r) =>
          rowNeedsIngest(r, embeddedTables.get(r.id), currentDefaults, embeddedDefaults),
        )
        .map((r) => r.id),
    [tableRows, embeddedTables, currentDefaults, embeddedDefaults],
  );

  const pendingFileNames = useMemo(
    () =>
      fileRows
        .filter((r) =>
          rowNeedsIngest(r, embeddedFiles.get(r.file_name), currentDefaults, embeddedDefaults),
        )
        .map((r) => r.file_name),
    [fileRows, embeddedFiles, currentDefaults, embeddedDefaults],
  );

  const pendingCount = isStructured ? pendingTableIds.length : pendingFileNames.length;

  const buildSavePayload = () => ({
    profile: {
      chunk_size: Number(defaultChunkSize) || 300,
      chunk_overlap: Number(defaultChunkOverlap) || 60,
      instructions: profileInstructions,
    },
    tables: isStructured
      ? tableRows.map((r) => ({
          id: r.id,
          rag_enabled: r.rag_enabled,
          chunk_size: numOrNull(r.chunk_size),
          chunk_overlap: numOrNull(r.chunk_overlap),
        }))
      : [],
    files: !isStructured
      ? fileRows.map((r) => ({
          file_name: r.file_name,
          rag_enabled: r.rag_enabled,
          chunk_size: numOrNull(r.chunk_size),
          chunk_overlap: numOrNull(r.chunk_overlap),
        }))
      : [],
  });

  const markRowsIngested = (tableIds: string[], fileNames: string[]) => {
    if (tableIds.length) {
      setEmbeddedTables((prev) => {
        const next = new Map(prev);
        for (const id of tableIds) {
          const row = tableRows.find((r) => r.id === id);
          if (row) {
            next.set(id, {
              rag_enabled: row.rag_enabled,
              chunk_size: row.chunk_size,
              chunk_overlap: row.chunk_overlap,
            });
          }
        }
        return next;
      });
      setTableRows((prev) =>
        prev.map((r) =>
          tableIds.includes(r.id) ? { ...r, ingested: true } : r,
        ),
      );
    }
    if (fileNames.length) {
      setEmbeddedFiles((prev) => {
        const next = new Map(prev);
        for (const name of fileNames) {
          const row = fileRows.find((r) => r.file_name === name);
          if (row) {
            next.set(name, {
              rag_enabled: row.rag_enabled,
              chunk_size: row.chunk_size,
              chunk_overlap: row.chunk_overlap,
            });
          }
        }
        return next;
      });
      setFileRows((prev) =>
        prev.map((r) =>
          fileNames.includes(r.file_name) ? { ...r, ingested: true } : r,
        ),
      );
    }
    setEmbeddedDefaults(currentDefaults);
  };

  const save = useMutation({
    mutationFn: () => api.saveDatasetRagSettings(dataset.id, buildSavePayload()),
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: ["dataset-rag", dataset.id] });
      qc.invalidateQueries({ queryKey: ["datasets"] });
      qc.invalidateQueries({ queryKey: ["files", dataset.id] });
      const removed = result.chunks_removed ?? 0;
      setSaveNotice(
        removed > 0
          ? `RAG settings saved — ${removed} chunk(s) removed for deselected items.`
          : "RAG settings saved.",
      );
    },
  });

  const ingest = useMutation({
    mutationFn: async () => {
      const tableIds = isStructured ? [...pendingTableIds] : [];
      const fileNames = !isStructured ? [...pendingFileNames] : [];
      await api.saveDatasetRagSettings(dataset.id, buildSavePayload());
      const result = await api.ingestDatasetRag(dataset.id, {
        table_ids: isStructured ? tableIds : undefined,
        file_names: !isStructured ? fileNames : undefined,
      });
      return { result, tableIds, fileNames };
    },
    onSuccess: ({ result, tableIds, fileNames }) => {
      qc.invalidateQueries({ queryKey: ["dataset-rag", dataset.id] });
      qc.invalidateQueries({ queryKey: ["files", dataset.id] });
      qc.invalidateQueries({ queryKey: ["summary", dataset.id] });

      if (result.skipped) {
        setIngestNotice(result.message ?? "Nothing to ingest — no changed rows.");
        return;
      }

      markRowsIngested(tableIds, fileNames);

      const chunks = result.catalog_chunks ?? result.total_chunks ?? 0;
      const count = tableIds.length || fileNames.length;
      setIngestNotice(
        count > 0
          ? `Ingest complete — ${count} item(s) re-embedded (${chunks} chunk(s)).`
          : `Ingest complete — ${chunks} chunk(s) embedded.`,
      );
    },
  });

  if (isLoading) {
    return <p className="text-sm" style={{ color: "var(--color-text-muted)" }}>Loading RAG settings…</p>;
  }
  if (error) {
    return <p className="alert-error">{error instanceof Error ? error.message : "Failed to load RAG settings"}</p>;
  }

  const hasTargets = isStructured ? tableRows.length > 0 : fileRows.length > 0;

  const ingestButtonLabel =
    pendingCount > 0
      ? ingest.isPending
        ? "Ingesting…"
        : `Ingest & embed (${pendingCount} changed)`
      : ingest.isPending
        ? "Ingesting…"
        : "Ingest & embed";

  return (
    <div className="space-y-5">
      <p className="text-sm" style={{ color: "var(--color-text-muted)" }}>
        {isStructured
          ? "Choose which catalog tables to embed for RAG. Only rows with changes (highlighted) are re-embedded on ingest — unchanged tables are skipped."
          : "Choose which files to embed for RAG. Only changed files are re-embedded. Upload files on the Data tab first."}
      </p>

      <div className="catalog-themed-box space-y-3">
        <p className="text-sm font-medium" style={{ color: "var(--color-text)" }}>
          Dataset defaults
        </p>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <div className="field mb-0">
            <label className="label">Default chunk size</label>
            <input
              className="input"
              type="number"
              min={50}
              value={defaultChunkSize}
              onChange={(e) => setDefaultChunkSize(e.target.value)}
            />
          </div>
          <div className="field mb-0">
            <label className="label">Default chunk overlap</label>
            <input
              className="input"
              type="number"
              min={0}
              value={defaultChunkOverlap}
              onChange={(e) => setDefaultChunkOverlap(e.target.value)}
            />
          </div>
        </div>
        <div className="field mb-0">
          <label className="label">RAG instructions (optional)</label>
          <textarea
            className="textarea min-h-[72px]"
            value={profileInstructions}
            onChange={(e) => setProfileInstructions(e.target.value)}
            placeholder="Extra context embedded with this dataset…"
          />
        </div>
      </div>

      {!hasTargets ? (
        <p className="catalog-themed-box--dashed text-sm" style={{ color: "var(--color-text-muted)" }}>
          {isStructured
            ? "No tables in catalog — add tables on the Data tab first."
            : ["api", "web_url", "sharepoint"].includes(dataset.connector)
                ? "No cached files — sync on the Data tab first, then ingest here."
                : "No files in dataset — upload or sync files on the Data tab first."}
        </p>
      ) : isStructured ? (
        <div className="table-wrap dataset-data-table">
          <table className="data">
            <thead>
              <tr>
                <th className="w-10" aria-label="Include in RAG" />
                <th>Table</th>
                <th>Role</th>
                <th>Chunk size</th>
                <th>Overlap</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {tableRows.map((row, idx) => {
                const excluded = row.role === "excluded";
                const needsIngest = rowNeedsIngest(
                  row,
                  embeddedTables.get(row.id),
                  currentDefaults,
                  embeddedDefaults,
                );
                const rowClass = needsIngest ? "rag-row-pending-ingest" : undefined;
                return (
                  <tr key={row.id} className={rowClass}>
                    <td>
                      <input
                        type="checkbox"
                        checked={row.rag_enabled && !excluded}
                        disabled={excluded}
                        aria-label={`Include ${row.name} in RAG`}
                        onChange={(e) =>
                          setTableRows((prev) =>
                            prev.map((r, i) =>
                              i === idx ? { ...r, rag_enabled: e.target.checked } : r,
                            ),
                          )
                        }
                      />
                    </td>
                    <td className="font-medium">{row.name}</td>
                    <td>{tableRoleLabel(row.role)}</td>
                    <td>
                      <input
                        className="input"
                        style={{ maxWidth: "6rem" }}
                        type="number"
                        min={50}
                        placeholder={defaultChunkSize}
                        disabled={excluded || !row.rag_enabled}
                        value={row.chunk_size}
                        onChange={(e) =>
                          setTableRows((prev) =>
                            prev.map((r, i) =>
                              i === idx ? { ...r, chunk_size: e.target.value } : r,
                            ),
                          )
                        }
                      />
                    </td>
                    <td>
                      <input
                        className="input"
                        style={{ maxWidth: "6rem" }}
                        type="number"
                        min={0}
                        placeholder={defaultChunkOverlap}
                        disabled={excluded || !row.rag_enabled}
                        value={row.chunk_overlap}
                        onChange={(e) =>
                          setTableRows((prev) =>
                            prev.map((r, i) =>
                              i === idx ? { ...r, chunk_overlap: e.target.value } : r,
                            ),
                          )
                        }
                      />
                    </td>
                    <td>
                      {needsIngest ? (
                        <span className="badge badge-warn">
                          {row.ingested ? "Needs re-embed" : "Not embedded"}
                        </span>
                      ) : row.ingested ? (
                        <span className="badge badge-ok">
                          Embedded{row.chunk_count ? ` (${row.chunk_count})` : ""}
                        </span>
                      ) : (
                        <span className="badge badge-muted">Not embedded</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="table-wrap dataset-data-table">
          <table className="data">
            <thead>
              <tr>
                <th className="w-10" aria-label="Include in RAG" />
                <th>File</th>
                <th>Chunk size</th>
                <th>Overlap</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {fileRows.map((row, idx) => {
                const needsIngest = rowNeedsIngest(
                  row,
                  embeddedFiles.get(row.file_name),
                  currentDefaults,
                  embeddedDefaults,
                );
                const rowClass = needsIngest ? "rag-row-pending-ingest" : undefined;
                return (
                  <tr key={row.file_name} className={rowClass}>
                    <td>
                      <input
                        type="checkbox"
                        checked={row.rag_enabled}
                        aria-label={`Include ${row.file_name} in RAG`}
                        onChange={(e) =>
                          setFileRows((prev) =>
                            prev.map((r, i) =>
                              i === idx ? { ...r, rag_enabled: e.target.checked } : r,
                            ),
                          )
                        }
                      />
                    </td>
                    <td className="font-medium">{row.file_name}</td>
                    <td>
                      <input
                        className="input"
                        style={{ maxWidth: "6rem" }}
                        type="number"
                        min={50}
                        placeholder={defaultChunkSize}
                        disabled={!row.rag_enabled}
                        value={row.chunk_size}
                        onChange={(e) =>
                          setFileRows((prev) =>
                            prev.map((r, i) =>
                              i === idx ? { ...r, chunk_size: e.target.value } : r,
                            ),
                          )
                        }
                      />
                    </td>
                    <td>
                      <input
                        className="input"
                        style={{ maxWidth: "6rem" }}
                        type="number"
                        min={0}
                        placeholder={defaultChunkOverlap}
                        disabled={!row.rag_enabled}
                        value={row.chunk_overlap}
                        onChange={(e) =>
                          setFileRows((prev) =>
                            prev.map((r, i) =>
                              i === idx ? { ...r, chunk_overlap: e.target.value } : r,
                            ),
                          )
                        }
                      />
                    </td>
                    <td>
                      {needsIngest ? (
                        <span className="badge badge-warn">
                          {row.ingested ? "Needs re-embed" : "Not embedded"}
                        </span>
                      ) : row.ingested ? (
                        <span className="badge badge-ok">
                          Embedded{row.chunk_count ? ` (${row.chunk_count})` : ""}
                        </span>
                      ) : (
                        <span className="badge badge-muted">Not embedded</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className="btn btn-secondary" disabled={save.isPending} onClick={() => save.mutate()}>
          {save.isPending ? "Saving…" : "Save"}
        </button>
        <button
          type="button"
          className="btn"
          disabled={pendingCount === 0 || ingest.isPending}
          onClick={() => ingest.mutate()}
          title={
            pendingCount === 0
              ? "No rows changed since last embed"
              : `Re-embed ${pendingCount} changed item(s) only`
          }
        >
          {ingestButtonLabel}
        </button>
      </div>
      {pendingCount === 0 && hasTargets && (
        <p className="text-sm" style={{ color: "var(--color-text-muted)" }}>
          All selected items are up to date — change settings or enable new rows to ingest.
        </p>
      )}
      {saveNotice && (
        <p className="alert-ok text-sm" role="status">
          {saveNotice}
        </p>
      )}
      {ingestNotice && (
        <p className="alert-ok text-sm" role="status">
          {ingestNotice}
        </p>
      )}
      {save.isError && (
        <p className="alert-error">{save.error instanceof Error ? save.error.message : "Save failed"}</p>
      )}
      {ingest.isError && (
        <p className="alert-error">{ingest.error instanceof Error ? ingest.error.message : "Ingest failed"}</p>
      )}
    </div>
  );
}
