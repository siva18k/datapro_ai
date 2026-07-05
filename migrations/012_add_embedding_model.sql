-- Migration: add embedding_model column to knowledge_chunks and rag_profiles
-- Run this with psql against your database (schema default: ragpro)

BEGIN;

ALTER TABLE IF EXISTS ragpro.knowledge_chunks
ADD COLUMN IF NOT EXISTS embedding_model text;

ALTER TABLE IF EXISTS ragpro.rag_profiles
ADD COLUMN IF NOT EXISTS embedding_model text;

-- Optional: backfill existing chunks with the chosen default embedding model.
-- Replace 'mistral-embed-2312' with your preferred model name if different.
UPDATE ragpro.knowledge_chunks
SET embedding_model = 'mistral-embed-2312'
WHERE embedding_model IS NULL;

UPDATE ragpro.rag_profiles
SET embedding_model = 'mistral-embed-2312'
WHERE embedding_model IS NULL;

COMMIT;

-- Optional: create unique constraint on (source_file, chunk_id)
-- Run separately if you want to enforce source/chunk uniqueness.
-- ALTER TABLE ragpro.knowledge_chunks
-- ADD CONSTRAINT ux_knowledge_chunks_source_chunk UNIQUE (source_file, chunk_id);
