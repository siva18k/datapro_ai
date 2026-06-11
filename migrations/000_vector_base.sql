-- Base pgvector store for RAG embeddings (run before catalog migrations)
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_file TEXT NOT NULL,
    chunk_id TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    embedding vector(384),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ux_knowledge_chunks_source_chunk UNIQUE (source_file, chunk_id)
);
