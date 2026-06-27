-- Per-domain prompt templates (local), bound via mcp_bindings as local:{slug}.

CREATE TABLE IF NOT EXISTS domain_prompts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    domain_id UUID NOT NULL REFERENCES domains(id) ON DELETE CASCADE,
    slug TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    template TEXT NOT NULL DEFAULT '',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (domain_id, slug)
);

CREATE INDEX IF NOT EXISTS idx_domain_prompts_domain ON domain_prompts(domain_id);
