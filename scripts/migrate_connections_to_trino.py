#!/usr/bin/env python3
"""Migrate legacy direct-Postgres saved connections to Trino catalog bindings.

Converts saved_db_connections.json rows (host/port/user/password) into Trino
catalog + schema bindings and optionally writes Trino catalog property files
so the coordinator can reach the same database.

Usage:
    python scripts/migrate_connections_to_trino.py
    python scripts/migrate_connections_to_trino.py --dry-run
    python scripts/migrate_connections_to_trino.py --migrate-datasets
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from catalog_db import migrate_postgres_sources_to_trino  # noqa: E402
from connections_service import migrate_stored_connections  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate business DB connections to Trino")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show planned changes without writing files or catalog rows",
    )
    parser.add_argument(
        "--no-catalog-files",
        action="store_true",
        help="Skip writing docker/trino/catalog/*.properties from legacy credentials",
    )
    parser.add_argument(
        "--migrate-datasets",
        action="store_true",
        help="Also update catalog data_sources still on connector=postgres",
    )
    args = parser.parse_args()

    result = migrate_stored_connections(
        dry_run=args.dry_run,
        write_catalog=not args.no_catalog_files,
    )
    print(f"Saved connections: {result['changed']} row(s) to migrate")
    for row in result["connections"]:
        print(
            f"  - {row['name']}: postgres → trino catalog={row['catalog']} schema={row['schema']}"
        )
    for path in result["catalog_files"]:
        print(f"  - Trino catalog file: {path}")

    if args.migrate_datasets:
        try:
            dataset_changes = migrate_postgres_sources_to_trino(dry_run=args.dry_run)
        except Exception as exc:
            print(f"Catalog dataset migration failed: {exc}")
            print("Run python scripts/migrate.py first (migration 015 adds connector=trino).")
            return 1
        print(f"Catalog datasets: {len(dataset_changes)} postgres source(s) to migrate")
        for row in dataset_changes:
            print(f"  - {row['name']}: trino catalog={row['catalog']} schema={row['schema']}")

    if args.dry_run:
        print("\nDry run — no files or database rows were changed.")
    else:
        print("\nDone. Restart Trino if it is already running, then test in Settings → Database connections.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
