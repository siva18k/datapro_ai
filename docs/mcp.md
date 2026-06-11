# MCP Server

DATA Pro exposes a **Model Context Protocol** server so Cursor, Claude Desktop, and other agents can search and ingest your knowledge base. Same `.env` and Postgres store as the UI.

## Start MCP

- **Docker:** `docker compose up datapro-mcp` (or full stack)
- **Local:** `python mcp_server.py`
- **UI:** **Settings → MCP server → Start** or **MCP** page

Endpoint: **http://127.0.0.1:8000/mcp**

## Connect Cursor / Claude Desktop

Copy JSON from the **MCP** page, or use:

```json
{
  "mcpServers": {
    "datapro": {
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

After editing prompts or domain bindings → **Restart MCP**.

### stdio mode

```bash
MCP_TRANSPORT=stdio python mcp_server.py
```

## Tools

| Tool | Description |
|------|-------------|
| `search_documents` | Semantic search over chunks |
| `list_sources` | Ingested files and chunk counts |
| `get_chunk` | One chunk by file + id |
| `knowledge_base_stats` | Totals and embedding model |
| `list_available_documents` | Files under `sample_docs/` |
| `ingest_documents` | Ingest into knowledge base |
| `list_domains` | Catalog domains |
| `list_domain_sources` | Sources in a domain |

## Resources (URIs)

| URI | Description |
|-----|-------------|
| `ragpro://knowledge-base/stats` | DB stats (JSON) |
| `ragpro://knowledge-base/sources` | Ingested sources |
| `ragpro://chunks/{source_file}/{chunk_id}` | One chunk |
| `ragpro://documents/{source_file}` | All chunks for a file |
| `ragpro://sample-docs/{file_name}` | Raw file from `sample_docs/` |
| `ragpro://domains` | Domain list |
| `ragpro://domains/{domain}/sources` | Domain sources |
| `ragpro://domains/{domain}/stats` | Domain stats |

URIs use the `ragpro://` scheme (internal, stable).

## Prompts

| Prompt | Purpose |
|--------|---------|
| `citation_rules` | Grounding instructions |
| `grounded_answer` | Retrieve + build prompt |
| `summarize_document` | Summarize one document |

## Environment

| Variable | Default |
|----------|---------|
| `MCP_TRANSPORT` | `streamable-http` |
| `MCP_HOST` | `0.0.0.0` |
| `MCP_PORT` | `8000` |
| `MCP_PATH` | `/mcp` |
| `DATABASE_URL` / `PG*` | Same as API |
| `DB_SCHEMA` | `ragpro` |

## Agent flow

1. `knowledge_base_stats` or `list_sources` — check data exists.
2. `search_documents(query="...", top_k=3)`.
3. Answer with `[source_file - chunk_id]` citations.

Or read `ragpro://knowledge-base/stats` and use the `grounded_answer` prompt.

Ingest via UI (**RAG** page), `ingest_documents` tool, or `python ingest.py`.
