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
  });

  useEffect(() => {
    if (rag?.profile) {
      setProfile({
        chunk_size: rag.profile.chunk_size,
        chunk_overlap: rag.profile.chunk_overlap,
        instructions: rag.profile.instructions,
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
    <div className="rag-page max-w-4xl">
      <PageHeader
        title="RAG Profiles"
        description={
          isStructured
            ? "Catalog metadata & lookup rows"
            : "Chunk settings for documents"
        }
      />

      <div className="card mb-3 card-pad">
        <div className="rag-selector-row flex flex-wrap">
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
        <div className="card rag-profile-card card-pad">
          <div className="rag-profile-header">
            <h2>{rag.source.name}</h2>
            <p>
              {rag.source.domain_name} · {rag.source.connector}
              {isStructured && " · structured"}
            </p>
          </div>

          {isStructured ? (
            <>
              <div className="rag-info-box">
                <p>
                  Embeds catalog metadata and lookup rows — not full fact tables. Use Ask for SQL analytics.
                </p>
              </div>

              {settings?.embedding_model && (
                <p className="rag-embedding-note">
                  Embedding: <code>{settings.embedding_model}</code>
                </p>
              )}

              <div className="rag-fields-grid">
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
                  className="textarea rag-textarea"
                  value={profile.instructions}
                  onChange={(e) => setProfile({ ...profile, instructions: e.target.value })}
                  placeholder="e.g. Finance reference data; prefer catalog labels over guessing column names"
                />
              </div>
            </>
          ) : (
            <>
              <div className="rag-fields-grid">
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
                <p className="rag-embedding-note">
                  Embedding: <code>{settings.embedding_model}</code>
                </p>
              )}

              <div className="field mb-0">
                <label className="label">Profile instructions</label>
                <textarea
                  className="textarea rag-textarea"
                  value={profile.instructions}
                  onChange={(e) => setProfile({ ...profile, instructions: e.target.value })}
                  placeholder="e.g. HR policy documents; cite section numbers"
                />
              </div>
            </>
          )}

          <div className="rag-actions flex flex-wrap">
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
