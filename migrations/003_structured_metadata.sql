-- Structured source metadata: table/column labels and extended connectors

ALTER TABLE data_sources DROP CONSTRAINT IF EXISTS data_sources_connector_check;
ALTER TABLE data_sources ADD CONSTRAINT data_sources_connector_check
    CHECK (connector IN ('upload', 'file_path', 'api', 'postgres', 'sharepoint', 'web_url'));

CREATE TABLE IF NOT EXISTS table_metadata (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID NOT NULL REFERENCES data_sources(id) ON DELETE CASCADE,
    table_schema TEXT NOT NULL,
    table_name TEXT NOT NULL,
    definition TEXT NOT NULL DEFAULT '',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_id, table_schema, table_name)
);

CREATE TABLE IF NOT EXISTS column_metadata (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    table_metadata_id UUID NOT NULL REFERENCES table_metadata(id) ON DELETE CASCADE,
    column_name TEXT NOT NULL,
    data_type TEXT NOT NULL DEFAULT '',
    labels JSONB NOT NULL DEFAULT '[]'::jsonb,
    description TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (table_metadata_id, column_name)
);

CREATE INDEX IF NOT EXISTS idx_table_metadata_source_id ON table_metadata(source_id);
CREATE INDEX IF NOT EXISTS idx_column_metadata_table_id ON column_metadata(table_metadata_id);
