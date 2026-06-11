import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { PageHeader } from "../components/PageHeader";
import { api } from "../api/client";

export function RagPage() {
  const [domainId, setDomainId] = useState<string>("");
  const [sourceId, setSourceId] = useState<string>("");
  const qc = useQueryClient();

  const { data: domains } = useQuery({ queryKey: ["domains"], queryFn: api.listDomains });
  const { data: datasets } = useQuery({
    queryKey: ["datasets", domainId],
    queryFn: () => api.listDatasets(domainId),
    enabled: !!domainId,
  });

  useEffect(() => {
    if (domains?.length && !domainId) setDomainId(domains[0].id);
  }, [domains, domainId]);

  useEffect(() => {
    if (datasets?.length) setSourceId(datasets[0].id);
  }, [datasets]);

  const { data: rag, isLoading } = useQuery({
    queryKey: ["rag", sourceId],
    queryFn: () => api.getRag(sourceId),
    enabled: !!sourceId,
  });

  const { data: settings } = useQuery({ queryKey: ["settings"], queryFn: api.getSettings });

  const [profile, setProfile] = useState({
    chunk_size: 300,
    chunk_overlap: 60,
    instructions: "",
    metadata_text: "",
  });

  useEffect(() => {
    if (rag?.profile) {
      setProfile({
        chunk_size: rag.profile.chunk_size,
        chunk_overlap: rag.profile.chunk_overlap,
        instructions: rag.profile.instructions,
        metadata_text: rag.profile.metadata_text,
      });
    }
  }, [rag?.profile]);

  const save = useMutation({
    mutationFn: () => api.updateRag(sourceId, profile),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["rag", sourceId] }),
  });

  const indexCatalog = useMutation({
    mutationFn: () => api.indexCatalog(sourceId),
  });

  const reingest = useMutation({
    mutationFn: () => api.reingest(sourceId),
  });

  useEffect(() => {
    save.reset();
    indexCatalog.reset();
    reingest.reset();
  }, [sourceId]);

  const isStructured = rag?.source.source_type === "structured";

  return (
    <div className="max-w-4xl">
      <PageHeader
        title="RAG Profiles"
        description={
          isStructured
            ? "Catalog metadata & lookup rows"
            : "Chunk settings for documents"
        }
      />

      <div className="card mb-4 card-pad">
        <div className="flex flex-wrap gap-4">
          <div className="field mb-0 min-w-[160px]">
            <label className="label">Domain</label>
            <select
              className="select"
              value={domainId}
              onChange={(e) => {
                setDomainId(e.target.value);
                setSourceId("");
              }}
            >
              {domains?.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          </div>
          <div className="field mb-0 min-w-[200px] flex-1">
            <label className="label">Dataset</label>
            <select className="select" value={sourceId} onChange={(e) => setSourceId(e.target.value)}>
              {datasets?.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {isLoading && <p className="text-sm text-zinc-500">Loading profile…</p>}

      {rag && (
        <div className="card card-pad space-y-5">
          <div>
            <h2 className="font-semibold">{rag.source.name}</h2>
            <p className="text-sm text-zinc-500">
              {rag.source.domain_name} · {rag.source.connector}
              {isStructured && " · structured"}
            </p>
          </div>

          {isStructured ? (
            <>
              <div className="rounded-lg border border-blue-100 bg-blue-50/50 p-4 text-sm dark:border-blue-900 dark:bg-blue-950/30">
                <p className="text-zinc-600 dark:text-zinc-400">
                  Embeds catalog metadata and lookup rows — not full fact tables. Use Ask for SQL analytics.
                </p>
              </div>

              {settings?.embedding_model && (
                <p className="text-xs text-zinc-500">
                  Embedding: <code>{settings.embedding_model}</code>
                </p>
              )}

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="field mb-0">
                  <label className="label">Chunk size (metadata text)</label>
                  <input
                    type="number"
                    className="input"
                    value={profile.chunk_size}
                    onChange={(e) => setProfile({ ...profile, chunk_size: Number(e.target.value) })}
                  />
                </div>
                <div className="field mb-0">
                  <label className="label">Overlap</label>
                  <input
                    type="number"
                    className="input"
                    value={profile.chunk_overlap}
                    onChange={(e) => setProfile({ ...profile, chunk_overlap: Number(e.target.value) })}
                  />
                </div>
              </div>

              <div className="field mb-0">
                <label className="label">Profile instructions</label>
                <textarea
                  className="textarea min-h-[80px]"
                  value={profile.instructions}
                  onChange={(e) => setProfile({ ...profile, instructions: e.target.value })}
                  placeholder="e.g. Finance reference data; prefer catalog labels over guessing column names"
                />
              </div>

              <div className="field mb-0">
                <label className="label">Extra glossary (optional)</label>
                <textarea
                  className="textarea min-h-[80px]"
                  value={profile.metadata_text}
                  onChange={(e) => setProfile({ ...profile, metadata_text: e.target.value })}
                  placeholder="Additional terms not captured in column labels…"
                />
              </div>
            </>
          ) : (
            <>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="field mb-0">
                  <label className="label">Chunk size</label>
                  <input
                    type="number"
                    className="input"
                    value={profile.chunk_size}
                    onChange={(e) => setProfile({ ...profile, chunk_size: Number(e.target.value) })}
                  />
                </div>
                <div className="field mb-0">
                  <label className="label">Overlap</label>
                  <input
                    type="number"
                    className="input"
                    value={profile.chunk_overlap}
                    onChange={(e) => setProfile({ ...profile, chunk_overlap: Number(e.target.value) })}
                  />
                </div>
              </div>
              {settings?.embedding_model && (
                <p className="text-xs text-zinc-500">
                  Embedding: <code>{settings.embedding_model}</code>
                </p>
              )}

              <div className="field mb-0">
                <label className="label">Profile instructions</label>
                <textarea
                  className="textarea min-h-[100px]"
                  value={profile.instructions}
                  onChange={(e) => setProfile({ ...profile, instructions: e.target.value })}
                  placeholder="e.g. HR policy documents; cite section numbers"
                />
              </div>

              <div className="field mb-0">
                <label className="label">Metadata text</label>
                <textarea
                  className="textarea min-h-[100px]"
                  value={profile.metadata_text}
                  onChange={(e) => setProfile({ ...profile, metadata_text: e.target.value })}
                  placeholder="Glossary, key terms, lookup hints…"
                />
              </div>
            </>
          )}

          <div className="flex flex-wrap gap-2">
            <button type="button" className="btn" onClick={() => save.mutate()} disabled={save.isPending}>
              {save.isPending ? "Saving…" : "Save profile"}
            </button>
            {isStructured ? (
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => indexCatalog.mutate()}
                disabled={indexCatalog.isPending}
              >
                {indexCatalog.isPending ? "Ingesting & embedding…" : "Ingest & embed catalog"}
              </button>
            ) : (
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => reingest.mutate()}
                disabled={reingest.isPending}
              >
                {reingest.isPending ? "Ingesting & embedding…" : "Ingest & embed all files"}
              </button>
            )}
          </div>

          {save.isSuccess && <p className="alert-ok">Profile saved</p>}
          {indexCatalog.isSuccess && indexCatalog.data != null && (
            <p className="alert-ok">
              Ingested & embedded {indexCatalog.data.catalog_chunks} chunk(s) from{" "}
              {indexCatalog.data.metadata_tables} table(s)
              {indexCatalog.data.lookup_tables > 0
                ? ` (+ ${indexCatalog.data.lookup_tables} lookup table(s) with row data)`
                : ""}
              {indexCatalog.data.removed_chunks > 0
                ? ` — replaced ${indexCatalog.data.removed_chunks} previous chunk(s).`
                : "."}
            </p>
          )}
          {reingest.isSuccess && reingest.data != null && !isStructured && (
            <p className="alert-ok">
              Ingested {Number((reingest.data as { total_chunks?: number }).total_chunks ?? 0)} chunks.
            </p>
          )}
          {(indexCatalog.isError || reingest.isError) && (
            <p className="alert-error">{String(indexCatalog.error ?? reingest.error)}</p>
          )}
        </div>
      )}
    </div>
  );
}
