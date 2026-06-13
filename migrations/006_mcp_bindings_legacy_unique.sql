-- Drop legacy domain binding unique constraint (Postgres may truncate the auto-generated name).
-- Replaced by uq_mcp_bindings_domain_server_cap in 005_mcp_servers.sql.

ALTER TABLE mcp_bindings
    DROP CONSTRAINT IF EXISTS mcp_bindings_domain_id_source_id_capability_type_capability_name_key;

ALTER TABLE mcp_bindings
    DROP CONSTRAINT IF EXISTS mcp_bindings_domain_id_source_id_capability_type_capability_key;
