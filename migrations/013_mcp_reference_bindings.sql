-- Bind standard MCP reference resources for existing domains.

INSERT INTO mcp_bindings (domain_id, source_id, capability_type, capability_name, enabled, mcp_server_id)
SELECT d.id, NULL, 'resource', cap.name, TRUE, s.id
FROM domains d
CROSS JOIN mcp_servers s
CROSS JOIN (
    VALUES
        ('ragpro://domains/{domain}/schema'),
        ('ragpro://domains/{domain}/calendar'),
        ('ragpro://domains/{domain}/glossary'),
        ('ragpro://policy/citation-rules')
) AS cap(name)
WHERE s.is_builtin = TRUE
  AND NOT EXISTS (
    SELECT 1
    FROM mcp_bindings b
    WHERE b.domain_id = d.id
      AND b.source_id IS NULL
      AND b.capability_type = 'resource'
      AND b.capability_name = cap.name
      AND b.mcp_server_id = s.id
  );

INSERT INTO mcp_bindings (domain_id, source_id, capability_type, capability_name, enabled, mcp_server_id)
SELECT d.id, NULL, 'prompt', 'domain_sql_context', TRUE, s.id
FROM domains d
CROSS JOIN mcp_servers s
WHERE s.is_builtin = TRUE
  AND NOT EXISTS (
    SELECT 1
    FROM mcp_bindings b
    WHERE b.domain_id = d.id
      AND b.source_id IS NULL
      AND b.capability_type = 'prompt'
      AND b.capability_name = 'domain_sql_context'
      AND b.mcp_server_id = s.id
  );
