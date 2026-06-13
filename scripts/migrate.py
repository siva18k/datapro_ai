#!/usr/bin/env python3
"""Apply SQL migrations for the multi-domain catalog."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from catalog_db import apply_migrations, ensure_catalog_seeded, verify_catalog_schema  # noqa: E402
from db import get_db_config, knowledge_chunks_has_catalog_columns  # noqa: E402


def _print_chunks_alter_help() -> None:
    schema = get_db_config()["schema"]
    print(
        "\nNote: migration 002 could not alter knowledge_chunks "
        "(your DB user is not the table owner).\n"
        "Catalog tables are fine. Domain-scoped chunk filtering needs a one-time "
        f"run by the table owner on schema `{schema}`:\n"
    )
    print(
        f"""-- Run as owner of knowledge_chunks (e.g. RDS master / table creator)
SET search_path TO {schema};
ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS domain_id UUID REFERENCES domains(id) ON DELETE SET NULL;
ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS source_id UUID REFERENCES data_sources(id) ON DELETE SET NULL;
ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS rag_profile_id UUID REFERENCES rag_profiles(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_domain_id ON knowledge_chunks(domain_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_source_id ON knowledge_chunks(source_id);
"""
    )
    print("Until then, search still works globally (no per-domain chunk tags).\n")


def main() -> int:
    print("Applying catalog migrations...")
    result = apply_migrations()
    print("Seeding default domains and sources...")
    ensure_catalog_seeded()

    schema = get_db_config()["schema"]
    has_cols = knowledge_chunks_has_catalog_columns()
    print(f"Schema: {schema}")
    print(f"knowledge_chunks catalog columns: {'yes' if has_cols else 'no'}")
    if not has_cols:
        if result.get("skipped_knowledge_chunks_alter"):
            _print_chunks_alter_help()
        else:
            print("\nDone, but knowledge_chunks is missing catalog columns. Re-run migrate or apply 002 manually.")
    elif result.get("skipped_knowledge_chunks_alter"):
        print("\nDone — catalog columns already present (002 skipped: not table owner).")
    else:
        print("\nDone — all migrations applied.")

    print("\nVerifying catalog + MCP schema…")
    check = verify_catalog_schema()
    info = check.get("info") or {}
    servers = info.get("mcp_servers") or []
    if servers:
        print(f"MCP servers ({len(servers)}):")
        for s in servers:
            tag = "built-in" if s.get("builtin") else "external"
            print(f"  - {s['slug']} ({tag})")
    optional = [s for s in servers if s.get("slug") == "email_smtp"]
    if optional:
        print("Optional integration: email_smtp (see docs/mcp.md)")
    print(f"Domains: {info.get('domains', '?')}  Domain MCP bindings: {info.get('domain_bindings', '?')}")
    if check["ok"]:
        print("Catalog verification: OK")
    else:
        print("Catalog verification: ISSUES")
        for issue in check["issues"]:
            print(f"  - {issue}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
