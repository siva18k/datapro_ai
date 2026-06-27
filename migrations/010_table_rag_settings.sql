-- Per-table and per-file RAG settings (catalog RAG tab)

ALTER TABLE table_metadata
    ADD COLUMN IF NOT EXISTS rag_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS chunk_size INTEGER,
    ADD COLUMN IF NOT EXISTS chunk_overlap INTEGER;

UPDATE table_metadata
SET rag_enabled = FALSE
WHERE table_role = 'excluded';

ALTER TABLE knowledge_chunks
    ADD COLUMN IF NOT EXISTS table_metadata_id UUID
        REFERENCES table_metadata(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_table
    ON knowledge_chunks(table_metadata_id)
    WHERE table_metadata_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS source_file_rag (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID NOT NULL REFERENCES data_sources(id) ON DELETE CASCADE,
    file_name TEXT NOT NULL,
    rag_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    chunk_size INTEGER,
    chunk_overlap INTEGER,
    last_ingested_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_id, file_name)
);

CREATE INDEX IF NOT EXISTS idx_source_file_rag_source ON source_file_rag(source_id);
