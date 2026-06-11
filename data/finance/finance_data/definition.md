# finance_data

Postgres schema with the demo EDW — GL, AP, customers, sales, HR, support, reference tables. Meant for trying structured Ask and analytics against something that looks like a real warehouse without connecting to production.

Load it with `python scripts/migrate_finance_data.py --fresh` (see migrations/finance_data/README.md). Point a Postgres dataset in the catalog at schema `finance_data`.

Fact tables for analytics; lookup/reference tables for joins and RAG catalog ingest. Refresh is manual — it's sample data, not a live feed.
