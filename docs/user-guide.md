# User guide

## Pages

**Data Catalog** — domains, datasets, connections, table metadata, uploads.

**Ask** — chat; you can override the domain, tweak Top K, turn on debug mode to see which chunks came back. Follow-up messages reuse prior SQL results (same session until **New chat**) so refinements like “show that in USD” stay on the same breakdown. After **5 follow-ups** (configurable in Settings), the app summarizes the thread and starts a fresh chat automatically. Unrelated questions are detected as a **new topic** and processed without old context.

**Analytics** — natural-language dashboards (needs Postgres datasets). Follow-up prompts in the same session reuse the prior dashboard data until you click **Clear**; the same auto-summary and new-topic rules apply.

**RAG** — chunk size, overlap, ingest.

**MCP** — server status, prompts, domain bindings. Bound tools, resources, and prompts are used automatically during **Ask** and **Analytics** when a domain is routed (planner picks what helps per question).

**Settings** — DB, LLM, embeddings, start/stop API and MCP.

Fastest path to a first answer: Catalog → add files → **RAG** → ingest → **Ask**. After `migrate.py`, `sample_docs/` is wired to General → Sample Documents.

---

## Domains and datasets

A **domain** is a business area — HR, Finance, Sales, whatever you name it. A **dataset** is one source inside that domain (Postgres, upload, folder on disk, etc.).

Default domains are created by `migrate.py`. To add another: **Data Catalog** → **+** in the sidebar.

**Add dataset** → pick a format:

- **Postgres** — live tables, analytics, structured Ask
- **Upload** — PDF, markdown, text, JSON
- **File path** — folder on disk (e.g. `sample_docs`)

For Postgres, pick an existing connection from **Settings → Dataset connections** or create one there.

---

## File-based datasets

1. **Definition** tab — short markdown about what the data is (there's an AI draft button if you want a starting point).
2. **Data** tab — upload files or point at a folder.
3. **RAG** — select the dataset → **Ingest & embed all files**.

---

## Postgres datasets

1. **Connection** — test and save credentials.
2. **Data** — **Refresh tables** → select → **Add selected**.
3. Tweak table roles (fact vs lookup), descriptions, column labels — this matters for SQL generation later.
4. **Definition** — when two or more tables are cataloged, open this tab to auto-append a **Table relationships** section at the bottom. **AI draft** uses only cataloged tables/columns (no invented fields), strips markdown code fences, and refreshes relationships. Use **Refresh relationships** after catalog changes, then **Save definition**. **Ask** blends ingested catalog/document chunks with the definition for SQL when embeddings exist; otherwise it uses the definition and column metadata alone.
5. **RAG** → **Ingest & embed catalog** — indexes metadata and lookup rows, not whole fact tables.
6. **Ask** — structured questions against fact data; RAG helps with schema names.

---

## Embeddings

Chunks live in `ragpro.knowledge_chunks`.

Re-ingest when:

- files change → **Ingest & embed all files**
- you edited catalog metadata → **Ingest & embed catalog**
- chunk size, overlap, or instructions changed → save profile, re-ingest
- embedding model changed → re-ingest **all** datasets (dimensions won't match otherwise)

Profile fields worth caring about: chunk size/overlap, profile instructions, metadata/glossary.

Check it's working: chunk counts in the catalog header, **Ask** with debug mode, or `GET /api/stats`.

---

## Demo finance warehouse

Optional sample EDW-style data:

```bash
# DBA once if needed: migrations/finance_data/000_master_bootstrap.sql
python scripts/migrate_finance_data.py --fresh
```

Details in [migrations/finance_data/README.md](../migrations/finance_data/README.md). Then add a Postgres dataset in the catalog pointing at schema `finance_data`.
