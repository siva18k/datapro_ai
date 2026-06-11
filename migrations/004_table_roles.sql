-- Table usage role for structured RAG: metadata-only vs full lookup row embedding

ALTER TABLE table_metadata
    ADD COLUMN IF NOT EXISTS table_role TEXT NOT NULL DEFAULT 'fact';

ALTER TABLE table_metadata DROP CONSTRAINT IF EXISTS table_metadata_table_role_check;
ALTER TABLE table_metadata ADD CONSTRAINT table_metadata_table_role_check
    CHECK (table_role IN ('fact', 'lookup', 'excluded'));
