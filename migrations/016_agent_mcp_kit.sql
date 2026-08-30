-- Persist prompts and resources with an agent (tools already live in agent_mcp_tools).
-- Resolved on save so execute can use the kit without re-planning.

CREATE TABLE IF NOT EXISTS agent_mcp_prompts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    mcp_server_id UUID NOT NULL REFERENCES mcp_servers(id) ON DELETE CASCADE,
    prompt_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (agent_id, mcp_server_id, prompt_name)
);

CREATE TABLE IF NOT EXISTS agent_mcp_resources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    mcp_server_id UUID NOT NULL REFERENCES mcp_servers(id) ON DELETE CASCADE,
    resource_uri TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (agent_id, mcp_server_id, resource_uri)
);

CREATE INDEX IF NOT EXISTS idx_agent_mcp_prompts_agent ON agent_mcp_prompts(agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_mcp_resources_agent ON agent_mcp_resources(agent_id);
