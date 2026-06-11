-- Optional: extend knowledge_chunks with domain/source metadata.
-- Requires table owner privileges. Safe to skip if unavailable.

ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS domain_id UUID REFERENCES domains(id) ON DELETE SET NULL;
ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS source_id UUID REFERENCES data_sources(id) ON DELETE SET NULL;
ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS rag_profile_id UUID REFERENCES rag_profiles(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_domain_id ON knowledge_chunks(domain_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_source_id ON knowledge_chunks(source_id);
