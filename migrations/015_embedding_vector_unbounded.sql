-- Allow mixed historical/new embedding dimensions during migration windows.
-- Older installs used vector(384); current Mistral embeddings are 1024 dims.
-- Using unconstrained vector lets recompute/reingest update rows incrementally.
DO $$
DECLARE
    emb_type text;
BEGIN
    SELECT format_type(a.atttypid, a.atttypmod)
      INTO emb_type
    FROM pg_attribute a
    JOIN pg_class t ON a.attrelid = t.oid
    WHERE t.relname = 'knowledge_chunks'
      AND a.attname = 'embedding'
      AND a.attnum > 0
      AND NOT a.attisdropped
    LIMIT 1;

    IF emb_type IS NULL THEN
        RETURN;
    END IF;

    IF emb_type <> 'vector' THEN
        ALTER TABLE knowledge_chunks
          ALTER COLUMN embedding TYPE public.vector
          USING embedding::public.vector;
    END IF;

    -- IVFFLAT indexes require consistent dimensions across indexed rows.
    -- Drop legacy ANN index so mixed 384/1024 vectors can coexist during transition.
    EXECUTE 'DROP INDEX IF EXISTS ix_knowledge_chunks_embedding_cosine';
END
$$;
