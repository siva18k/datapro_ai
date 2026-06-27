-- Bind list_domains tool on built-in MCP server for existing domains (new domains get it via DEFAULT_MCP_BINDINGS).

INSERT INTO mcp_bindings (domain_id, source_id, capability_type, capability_name, enabled, mcp_server_id)
SELECT d.id, NULL, 'tool', 'list_domains', TRUE, s.id
FROM domains d
CROSS JOIN mcp_servers s
WHERE s.is_builtin = TRUE
  AND NOT EXISTS (
    SELECT 1
    FROM mcp_bindings b
    WHERE b.domain_id = d.id
      AND b.source_id IS NULL
      AND b.capability_type = 'tool'
      AND b.capability_name = 'list_domains'
      AND b.mcp_server_id = s.id
  );
