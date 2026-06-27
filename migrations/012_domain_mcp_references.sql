-- Domain reference documents exposed as MCP resources (calendar, glossary, sql notes).

CREATE TABLE IF NOT EXISTS domain_reference_docs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    domain_id UUID NOT NULL REFERENCES domains(id) ON DELETE CASCADE,
    doc_type TEXT NOT NULL CHECK (doc_type IN ('calendar', 'glossary', 'sql_notes')),
    content TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (domain_id, doc_type)
);

CREATE INDEX IF NOT EXISTS idx_domain_reference_docs_domain ON domain_reference_docs(domain_id);

-- Seed Finance reference docs (edit via API or SQL as needed).
INSERT INTO domain_reference_docs (domain_id, doc_type, content)
SELECT d.id, 'calendar',
$$# Finance fiscal calendar

- Fiscal year starts **April 1** (use `fiscal_year_start_month=4` with resolve_time_period).
- Quarters: Q1 Apr–Jun, Q2 Jul–Sep, Q3 Oct–Dec, Q4 Jan–Mar (next calendar year).
- Calendar-year reporting is also used for some metrics — check the question wording.
- Always schema-qualify tables and use catalog date columns for filters.
$$
FROM domains d WHERE d.slug = 'finance'
ON CONFLICT (domain_id, doc_type) DO NOTHING;

INSERT INTO domain_reference_docs (domain_id, doc_type, content)
SELECT d.id, 'glossary',
$$# Finance glossary

- **Revenue**: Recognized revenue per documented business rules in dataset definitions.
- **FY / fiscal year**: April–March unless the question specifies calendar year.
- **YTD**: From fiscal or calendar year start through the reference date.
- Prefer exact column names from the catalog schema resource — do not invent tables or columns.
$$
FROM domains d WHERE d.slug = 'finance'
ON CONFLICT (domain_id, doc_type) DO NOTHING;

INSERT INTO domain_reference_docs (domain_id, doc_type, content)
SELECT d.id, 'sql_notes',
$$# Finance SQL conventions

- READ-ONLY `SELECT` only; schema-qualify every table (e.g. `finance_data.customer_profiles`).
- Use join paths from dataset definitions — prefer documented hub/bridge tables over guessed FKs.
- Apply status and business-rule filters documented per table in the schema resource.
$$
FROM domains d WHERE d.slug = 'finance'
ON CONFLICT (domain_id, doc_type) DO NOTHING;
