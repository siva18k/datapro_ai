# MCP server

Same Postgres and `.env` as the web app — agents just talk to port 8000 instead of the React UI.

## Start it

- Podman: `podman compose up datapro-mcp` (or the full stack)
- Local: `python mcp_server.py`
- UI: **Settings → MCP server → Start**, or the **MCP** page

Endpoint: http://127.0.0.1:8000/mcp

## Cursor / Claude Desktop

Grab the JSON from the **MCP** page, or paste something like:

```json
{
  "mcpServers": {
    "datapro": {
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

Restart MCP after you change **built-in registry prompts**. Domain bindings apply at ask time without a restart.

## MCP servers & domain bindings

Register multiple MCP servers on the **MCP** page (built-in DATA Pro plus public/enterprise endpoints). Per domain, bind **tools**, **resources**, and **prompts** from any server. Ask uses those bindings for retrieval and prompt templates.

**Prompts** on the domain bindings tab can be **Global** (built-in `mcp_registry.json` templates) or **Local** (per-domain templates stored in `domain_prompts`, bound as `local:{slug}`). Create local prompts in the Add prompt dialog; edit/delete from the bindings list. Local templates support placeholders such as `{question}`, `{context}`, `{domain_name}`, `{schema}`, `{calendar}`, `{glossary}`, `{citation_rules}`. Run migration `014_domain_prompts.sql` before using local prompts.

Default domain bindings include reference **resources** (schema, calendar, glossary, sql-notes, citation-rules), **tools** (`list_domains`, `list_domain_sources`, `search_documents`, `resolve_time_period`), and **prompts** (`domain_sql_context`, `domain_grounded_answer`).

Ask / Analytics **automatically attach bound reference resources** (schema for SQL/hybrid; glossary + citation rules for RAG). Optional inventory resources (`ragpro://domains`, sources, stats) load only when the planner sets `use_resources`.

Edit domain reference docs via API: `PUT /api/domains/{id}/references/calendar` (also `glossary`, `sql_notes`). Finance is seeded with sample FY content in migration `012`.

### Pre-seeded optional integration

After `python scripts/migrate.py`, the catalog includes one optional **public** server:

| Server | Purpose | Start |
|--------|---------|--------|
| **Email (SMTP/IMAP)** | Send mail + search inbox (Gmail app password, etc.) | `python email_mcp_server.py` or `podman compose --profile integrations up -d email-mcp` |

**Email setup:** set `SMTP_*` / `IMAP_*` in `.env` (see `.env.example`). Optional `EMAIL_TO_ALLOWLIST` restricts who can receive mail.

For SQL charts and dashboards, use the in-app **Analytics** page — no separate dashboard MCP server.

**stdio mode** (some clients want this):

```bash
MCP_TRANSPORT=stdio python mcp_server.py
```

## Tool naming (important)

| Tool | What it returns | When to use |
|------|-----------------|-------------|
| `list_domains` | Business domains (HR, Finance, …) | Discovery when domain is unknown |
| `list_domain_sources` | **Catalog datasets** under a domain | Dataset/table inventory for SQL or catalog questions |
| `sync_dataset` | Refresh a remote catalog dataset (API, web link, SharePoint) into its cache | Before RAG ingest when content is stale |
| `list_sources` | **Ingested document files** in the vector KB | Chunk/file inventory — **not** catalog datasets |
| `search_documents` | Semantic chunks | RAG retrieval; optional `domain` filter |
| `get_rag_profile` | RAG settings for a dataset | `source_id` = UUID or slug; pass `domain` when using slug |
| `resolve_time_period` | Calendar/fiscal periods + SQL date filters | Analytics / time-bucket questions |

Ask and Analytics call `search_documents` via a dedicated retrieval path (not the enrichment planner). The planner invokes catalog/time tools such as `list_domain_sources` and `resolve_time_period`.

## Tools (full list)

| Tool | What it does |
|------|----------------|
| `list_domains` | Enabled business domains |
| `list_domain_sources` | Catalog datasets in a domain (`domain` = slug, name, or UUID) |
| `get_rag_profile` | RAG profile for a dataset (`source_id` + optional `domain`) |
| `search_documents` | Semantic search over chunks |
| `list_sources` | Ingested **files** + chunk counts (vector KB, not catalog) |
| `get_chunk` | One chunk by file + id |
| `knowledge_base_stats` | Totals, embedding model |
| `list_available_documents` | Files under `sample_docs/` |
| `ingest_documents` | Run ingest |
| `resolve_time_period` | Calendar/fiscal quarters, months, year boundaries + SQL date filters from natural language. **Analytics** calls this automatically (via MCP when running) to label chart/table buckets such as `Q1-2024` instead of raw `DATE_TRUNC` timestamps. |

## Resources (`ragpro://` URIs)

### Reference resources (host attaches automatically when bound)

| URI | Content |
|-----|---------|
| `ragpro://domains/{domain}/schema` | **Catalog schema for SQL** — tables, columns, types, definitions |
| `ragpro://domains/{domain}/calendar` | Fiscal/calendar conventions (editable per domain) |
| `ragpro://domains/{domain}/glossary` | Business terms and metric definitions |
| `ragpro://domains/{domain}/sql-notes` | SQL join/filter conventions |
| `ragpro://policy/citation-rules` | Document grounding and citation policy |

### Optional inventory resources (planner `use_resources`)

| URI | Content |
|-----|---------|
| `ragpro://domains` | Domain list (same shape as `list_domains`) |
| `ragpro://domains/{domain}/sources` | Catalog datasets (same shape as `list_domain_sources`) |
| `ragpro://domains/{domain}/stats` | Domain chunk stats |
| `ragpro://knowledge-base/stats` | DB stats (JSON) |
| `ragpro://knowledge-base/sources` | Ingested source files |
| `ragpro://chunks/{source_file}/{chunk_id}` | Single chunk |
| `ragpro://documents/{source_file}` | All chunks for a file |
| `ragpro://sample-docs/{file_name}` | Raw file from `sample_docs/` |

## Prompts

- `citation_rules` — grounding instructions (also exposed as `ragpro://policy/citation-rules` resource)
- `grounded_answer` — retrieve + build prompt
- `domain_grounded_answer` — domain-scoped grounded answer (used by **Agents**)
- `domain_sql_context` — SQL prompt from schema/calendar/glossary resources (used by **Agents**; Ask/Analytics inject resources directly)
- `summarize_document` — one-doc summary

## Env vars

| Variable | Default |
|----------|---------|
| `MCP_TRANSPORT` | `streamable-http` |
| `MCP_HOST` | `0.0.0.0` |
| `MCP_PORT` | `8000` |
| `MCP_PATH` | `/mcp` |
| `DATABASE_URL` / `PG*` | Same as API |
| `DB_SCHEMA` | `ragpro` |

## Typical agent flow

1. `list_domains` — pick scope (or use known domain slug)
2. `list_domain_sources(domain="finance")` — catalog datasets for SQL
3. `search_documents(query="...", domain="finance", top_k=3)` — document chunks
4. Answer with `[source_file - chunk_id]` citations

Or read `ragpro://knowledge-base/stats` and use the `grounded_answer` prompt.

Ingest from dataset **RAG** tabs, the `ingest_documents` tool, or `python ingest.py`.

## Extending MCP (tools & resources)

### Layer model

1. **Registry** — `mcp_registry.py` (`REGISTRY_DEFAULTS`) and optional `mcp_registry.json`: URI, description, `enabled` flag.
2. **Implementation** — `mcp_server.py`: FastMCP handlers (`@mcp.tool`, `@mcp.resource`, `@mcp.prompt`).
3. **Reference content** — `mcp_reference_service.py` + `domain_reference_docs` for editable markdown (calendar, glossary, sql-notes). Schema is built from the catalog.
4. **Domain wiring** — `mcp_bindings` in Postgres; defaults in `catalog_db.py` → `DEFAULT_MCP_BINDINGS`; UI on the **MCP** page.

Restart the MCP process after changing **code** in `mcp_server.py` or **prompts** in the registry. Domain bindings and reference-doc content apply without restart.

### Industry standard alignment

| MCP primitive | DATA Pro usage | Standard? |
|---------------|----------------|-----------|
| **Resources** | Read-only URIs (`ragpro://domains/{domain}/schema`, calendar, glossary, …) | Yes — no side effects; host attaches reference resources when bound |
| **Tools** | `search_documents`, `list_domain_sources`, `resolve_time_period`, ingest, … | Yes — actions the planner or client invokes |
| **Prompts** | Global (`mcp_registry.json`) and per-domain local (`domain_prompts`) | Yes — parameterized templates |

Deliberate product choices (still valid for MCP hosts): **domain bindings** scope capabilities per business domain; the **API** can read reference resources from the catalog for UI preview without a live MCP round-trip; Ask/Analytics use a **planner** to choose tools/resources rather than exposing everything every turn.

### Add a new tool

1. Add to `REGISTRY_DEFAULTS["tools"]` in `mcp_registry.py` (name, description, `enabled`).
2. Implement in `mcp_server.py` inside `if is_enabled("tools", "my_tool", REGISTRY):` with `@mcp.tool(...)`.
3. Restart MCP.
4. Bind on **MCP → Domain bindings → Tools → Add** (or add to `DEFAULT_MCP_BINDINGS` for new domains).
5. Optional: teach `mcp_ask_planner.py` to call it when relevant.

### Add a new resource

1. Add URI to `REGISTRY_DEFAULTS["resources"]` in `mcp_registry.py`.
2. Implement `@mcp.resource("ragpro://…")` in `mcp_server.py`.
3. If it should auto-attach like schema/calendar: add to `REFERENCE_RESOURCE_URIS` and `read_reference_resource_content()` in `mcp_reference_service.py`, plus `DEFAULT_MCP_BINDINGS`.
4. Restart MCP and bind on the MCP page.

### Change resource *content* without code

| Resource | How |
|----------|-----|
| Calendar, glossary, sql-notes | `PUT /api/domains/{id}/references/calendar` (or `glossary`, `sql_notes`) |
| Schema | Update catalog datasets, tables, definitions |
| Citation policy | Edit global prompt / `ragpro://policy/citation-rules` in registry |
| Local prompt | MCP page → Prompts → Local |

### Difficulty

- **Content / bindings only** — easy; no deploy of MCP code.
- **New tool or resource in `mcp_server.py`** — moderate; copy an existing handler; one registry entry; restart MCP.
- **Planner + auto-attach behavior** — extra step in `mcp_ask_planner.py` / `mcp_domain_service.py`.

Separate integrations (e.g. `email_mcp_server.py`) are standalone MCP servers registered on the MCP page.
