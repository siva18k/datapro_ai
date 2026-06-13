-- Registered MCP servers (built-in DATA Pro + external public/enterprise)

CREATE TABLE IF NOT EXISTS mcp_servers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL,
    server_kind TEXT NOT NULL DEFAULT 'external'
        CHECK (server_kind IN ('builtin', 'public', 'enterprise')),
    transport TEXT NOT NULL DEFAULT 'streamable-http',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    is_builtin BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE mcp_bindings
    ADD COLUMN IF NOT EXISTS mcp_server_id UUID REFERENCES mcp_servers(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_mcp_bindings_server ON mcp_bindings(mcp_server_id);
CREATE INDEX IF NOT EXISTS idx_mcp_servers_enabled ON mcp_servers(enabled);

-- Domain capability bindings scoped to a specific MCP server
ALTER TABLE mcp_bindings
    DROP CONSTRAINT IF EXISTS mcp_bindings_domain_id_source_id_capability_type_capability_name_key;

ALTER TABLE mcp_bindings
    DROP CONSTRAINT IF EXISTS mcp_bindings_domain_id_source_id_capability_type_capability_key;

CREATE UNIQUE INDEX IF NOT EXISTS uq_mcp_bindings_domain_server_cap
    ON mcp_bindings (domain_id, mcp_server_id, capability_type, capability_name)
    WHERE source_id IS NULL AND domain_id IS NOT NULL AND mcp_server_id IS NOT NULL;
