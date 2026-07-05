-- Allow Trino as structured business-data connector (catalog Postgres unchanged).
ALTER TABLE data_sources DROP CONSTRAINT IF EXISTS data_sources_connector_check;
ALTER TABLE data_sources ADD CONSTRAINT data_sources_connector_check
    CHECK (connector IN ('upload', 'file_path', 'api', 'postgres', 'trino', 'sharepoint', 'web_url'));
