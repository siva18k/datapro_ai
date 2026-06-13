-- Slugs of optional seed MCP servers the user explicitly removed (do not re-seed).

CREATE TABLE IF NOT EXISTS mcp_server_opt_out (
    slug TEXT PRIMARY KEY,
    dismissed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
