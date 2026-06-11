# User guide

## UI pages

| Page | Use for |
|------|---------|
| **Data Catalog** | Domains, datasets, connections, tables, uploads |
| **Ask** | Chat; domain override, Top K, debug mode |
| **Analytics** | Natural-language dashboards (Postgres datasets) |
| **RAG** | Chunk settings, ingest / embed |
| **MCP** | Server status, prompts, domain bindings |
| **Settings** | DB, LLM, embeddings, start/stop servers |

**Quick first Ask:** Catalog → ingest files → **RAG** → ingest → **Ask**.

Sample files: `sample_docs/` (General → Sample Documents after migrate).

---

## Domains and datasets

| Term | Meaning |
|------|---------|
| **Domain** | Business area — HR, Finance, Sales, … |
| **Dataset** | One source inside a domain |
| **Connector** | Postgres, upload, file path, API, … |

### Add a domain

**Data Catalog** → sidebar **+** → name your domain.  
Defaults (HR, Finance, Sales, General) are created by `migrate.py`.

### Add a dataset

1. **+ Add dataset** → name + format:

| Format | Use for |
|--------|---------|
| **Postgres** | Structured tables + analytics |
| **Upload** | PDF, Markdown, text, JSON |
| **File path** | Folder on disk (e.g. `sample_docs`) |

2. **Postgres:** pick **Settings → Dataset connections** or create a new connection.

---

## Document datasets (files)

1. **Definition** tab — markdown description for the LLM (optional **AI draft**).
2. **Data** tab — upload files or use file-path folder.
3. **RAG** page — select dataset → **Ingest & embed all files**.

---

## Postgres datasets (structured)

1. **Connection** — test and save DB credentials.
2. **Data** — **Refresh tables** → select → **Add selected**.
3. Edit table roles (**fact** vs **lookup**), descriptions, column labels.
4. **RAG** — **Ingest & embed catalog** (metadata + lookup rows; not full fact tables).
5. **Ask** — SQL/analytics on fact data; RAG helps with schema names.

---

## RAG embeddings

Stored in `ragpro.knowledge_chunks` (pgvector).

### When to re-ingest

| Change | Action |
|--------|--------|
| New/updated files | **Data** tab or RAG **Ingest & embed all files** |
| Catalog metadata changed | RAG **Ingest & embed catalog** |
| Chunk size / instructions | Save profile → re-ingest |
| Embedding model changed | Re-ingest **all** datasets |

### Profile fields

| Field | Purpose |
|-------|---------|
| Chunk size / overlap | How text is split |
| Profile instructions | Retrieval and answer hints |
| Metadata / glossary | Extra terms |

### Verify

- Catalog header — chunk/file counts.
- **Ask** + **Debug mode** — see retrieved chunk IDs.
- `GET /api/stats` — total chunks.

---

## Demo finance warehouse

Optional sample data:

```bash
# DBA once: migrations/finance_data/000_master_bootstrap.sql
python scripts/migrate_finance_data.py --fresh
```

See [migrations/finance_data/README.md](../migrations/finance_data/README.md).

Then add a Postgres dataset in Catalog pointing at that database.
