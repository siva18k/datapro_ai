# MCP server

Same Postgres and `.env` as the web app — agents just talk to port 8000 instead of the React UI.

## Start it

- Docker: `docker compose up datapro-mcp` (or the full stack)
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

### Pre-seeded optional integration

After `python scripts/migrate.py`, the catalog includes one optional **public** server:

| Server | Purpose | Start |
|--------|---------|--------|
| **Email (SMTP/IMAP)** | Send mail + search inbox (Gmail app password, etc.) | `python email_mcp_server.py` or `docker compose --profile integrations up -d email-mcp` |

**Email setup:** set `SMTP_*` / `IMAP_*` in `.env` (see `.env.example`). Optional `EMAIL_TO_ALLOWLIST` restricts who can receive mail.

For SQL charts and dashboards, use the in-app **Analytics** page — no separate dashboard MCP server.

**stdio mode** (some clients want this):

```bash
MCP_TRANSPORT=stdio python mcp_server.py
```

## Tools

| Tool | What it does |
|------|----------------|
| `search_documents` | Semantic search over chunks |
| `list_sources` | Files + chunk counts |
| `get_chunk` | One chunk by file + id |
| `knowledge_base_stats` | Totals, embedding model |
| `list_available_documents` | Files under `sample_docs/` |
| `ingest_documents` | Run ingest |
| `list_domains` | Catalog domains |
| `list_domain_sources` | Sources in a domain |

## Resources (`ragpro://` URIs)

| URI | Content |
|-----|---------|
| `ragpro://knowledge-base/stats` | DB stats (JSON) |
| `ragpro://knowledge-base/sources` | Ingested sources |
| `ragpro://chunks/{source_file}/{chunk_id}` | Single chunk |
| `ragpro://documents/{source_file}` | All chunks for a file |
| `ragpro://sample-docs/{file_name}` | Raw file from `sample_docs/` |
| `ragpro://domains` | Domain list |
| `ragpro://domains/{domain}/sources` | Sources in domain |
| `ragpro://domains/{domain}/stats` | Domain stats |

## Prompts

- `citation_rules` — grounding instructions
- `grounded_answer` — retrieve + build prompt
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

1. `knowledge_base_stats` or `list_sources` — make sure there's data
2. `search_documents(query="...", top_k=3)`
3. Answer with `[source_file - chunk_id]` citations

Or read `ragpro://knowledge-base/stats` and use the `grounded_answer` prompt.

Ingest from the **RAG** page, the `ingest_documents` tool, or `python ingest.py`.
