#!/usr/bin/env python3
"""Load finance_data schema from sample_docs/finance_data_sqls into PostgreSQL.

Creates schema ``finance_data``, applies DDL from the myedw script set (adapted),
then loads seeds. Skips broken/duplicate source files — see migrations/finance_data/README.md.

Usage:
    python scripts/migrate_finance_data.py
    python scripts/migrate_finance_data.py --fresh          # DROP SCHEMA finance_data CASCADE first
    python scripts/migrate_finance_data.py --all-in-one   # use postgres_all_in_one_edw_agentic.sql instead
    python scripts/migrate_finance_data.py --dry-run
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from db import connect, get_db_config  # noqa: E402

SCHEMA = "finance_data"
SOURCE_DIR = PROJECT_DIR / "sample_docs" / "finance_data_sqls"
FIXED_DIR = PROJECT_DIR / "migrations" / "finance_data"

# myedw-based pipeline (recommended)
MYEDW_PIPELINE: list[tuple[str, str | None]] = [
    ("1_1_schema_core.sql", "ddl"),
    ("1_2_schema_customer_sales.sql", "ddl"),
    ("1_3_schema_hr_finance_support_docs.sql", "ddl"),
    ("1_4_schema_views_sanity.sql", "views"),
    ("02_myedw_reference_seed.sql", "seed"),
    ("seed_inventory_products.sql", "fixed"),
    ("03_customer_seed.sql", "seed"),
    ("05_sales_seed.sql", "seed"),
    ("seed_hr.sql", "fixed"),
    ("06_myedw_finance_seed.sql", "seed"),
    ("seed_support.sql", "fixed"),
    ("seed_analytics.sql", "fixed"),
]

SKIP_FILE_PATTERNS = (
    "00_myedw_check_data.sql",  # validation SELECTs only
    "04_inventory_ddl.sql",  # conflicts with 1_2 inventory_products
    "04_inventory_seed.sql",  # syntax errors + wrong inventory model
    "06_schema_hr.sql",  # duplicate HR DDL
    "07_myedw_hr_seed.sql",  # syntax errors; replaced by seed_hr.sql
    "08_myedw_support_seed.sql",  # syntax errors; replaced by seed_support.sql
    "09_analytics_fact_sales.sql",  # replaced by seed_analytics.sql
)


def _read_sql(name: str, kind: str) -> str:
    if kind == "fixed":
        path = FIXED_DIR / name
    else:
        path = SOURCE_DIR / name
    if not path.exists():
        raise FileNotFoundError(path)
    return path.read_text(encoding="utf-8")


def transform_sql(sql: str, *, views_only: bool = False) -> str:
    sql = sql.replace("myedw", SCHEMA)
    sql = sql.replace("MYEDW", SCHEMA.upper())

    lines: list[str] = []
    for line in sql.splitlines():
        upper = line.upper().strip()
        if upper.startswith("DROP SCHEMA"):
            continue
        if re.match(r"CREATE\s+SCHEMA\b", upper):
            continue
        lines.append(line)
    sql = "\n".join(lines)

    if views_only:
        cut = re.search(r"--\s*SANITY\s+CHECKS", sql, re.I)
        if cut:
            sql = sql[: cut.start()]

    # Broken line in 05_sales_seed.sql
    sql = re.sub(
        r"WHERE\s+o\.status\s+IN\s+\([^)]+\)\s*;\s*\n\s*ON CONFLICT DO NOTHING\s*;",
        lambda m: m.group(0).split("ON CONFLICT")[0],
        sql,
        flags=re.I,
    )

    return sql


def split_sql_statements(sql: str) -> list[str]:
    """Split SQL on semicolons, respecting $$ ... $$ blocks."""
    statements: list[str] = []
    buf: list[str] = []
    i = 0
    n = len(sql)
    dollar_tag: str | None = None

    while i < n:
        if dollar_tag is None and sql[i : i + 2] == "$$":
            j = i + 2
            while j < n and sql[j] not in "$\n":
                j += 1
            tag = sql[i:j] if j > i + 2 else "$$"
            if tag == "$$":
                end = sql.find("$$", i + 2)
                if end == -1:
                    buf.append(sql[i:])
                    break
                buf.append(sql[i : end + 2])
                i = end + 2
                continue
            dollar_tag = tag
            buf.append(sql[i:j])
            i = j
            continue

        if dollar_tag is not None:
            end_marker = f"{dollar_tag}$"
            end = sql.find(end_marker, i)
            if end == -1:
                buf.append(sql[i:])
                break
            buf.append(sql[i : end + len(end_marker)])
            i = end + len(end_marker)
            dollar_tag = None
            continue

        if sql[i] == ";":
            stmt = "".join(buf).strip()
            if stmt:
                statements.append(stmt)
            buf = []
            i += 1
            continue

        buf.append(sql[i])
        i += 1

    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


def is_skippable_statement(stmt: str) -> bool:
    s = stmt.strip()
    if not s:
        return True
    upper = s.upper()
    if upper.startswith("SELECT "):
        return True
    if re.match(r"^WITH\s+", upper) and "INSERT" not in upper:
        return True
    if upper.startswith("\\"):
        return True
    return False


def _print_master_help() -> None:
    master_sql = FIXED_DIR / "000_master_bootstrap.sql"
    print(
        "\n*** Permission denied creating schema ***\n"
        "Your app user cannot CREATE SCHEMA on this database.\n"
        "Ask a DBA to run (as master):\n"
        f"  psql ... -f {master_sql}\n"
        "Then re-run this script with --fresh\n"
    )


def run_statement(conn, stmt: str, *, dry_run: bool) -> None:
    preview = re.sub(r"\s+", " ", stmt)[:120]
    if dry_run:
        print(f"  [dry-run] {preview}...")
        return
    try:
        conn.run(stmt)
    except Exception as exc:
        msg = str(exc).lower()
        if "permission denied" in msg and "create schema" in stmt.lower():
            _print_master_help()
            raise SystemExit(1) from exc
        if "must be owner of schema" in msg:
            raise RuntimeError(
                f"Schema owner required for: {preview}...\n"
                "Re-run 000_master_bootstrap.sql with your app DB user as AUTHORIZATION, or run as owner."
            ) from exc
        if "already exists" in msg and "schema" in msg:
            return
        if "duplicate key" in msg and "insert" in stmt.lower():
            print(f"  [warn] duplicate skipped: {preview}...")
            return
        if "already exists" in msg and ("relation" in msg or "42p07" in msg):
            print(f"  [skip] already exists: {preview[:80]}...")
            return
        raise RuntimeError(f"Failed: {preview}...\n{exc}") from exc


def bootstrap(conn, *, fresh: bool, dry_run: bool) -> None:
    if fresh:
        print(f"Attempting DROP SCHEMA {SCHEMA} CASCADE (requires schema owner)...")
        try:
            if not dry_run:
                conn.run(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
        except Exception as exc:
            if "must be owner" in str(exc).lower() or "permission denied" in str(exc).lower():
                print("  [skip] not schema owner — truncating tables in place where possible")
            else:
                raise
    # Schema must already exist (see 000_master_bootstrap.sql); app user often cannot CREATE SCHEMA.
    print(f"Using schema {SCHEMA}...")
    run_statement(conn, f"SET search_path TO {SCHEMA}, public", dry_run=dry_run)


def run_file(conn, name: str, kind: str, *, dry_run: bool) -> None:
    print(f"\n==> {name}")
    raw = _read_sql(name, kind)
    if kind in ("ddl", "seed", "views"):
        raw = transform_sql(raw, views_only=(kind == "views"))
    elif kind == "fixed":
        raw = raw.replace("finance_data", SCHEMA)  # idempotent if SCHEMA constant changes

    for stmt in split_sql_statements(raw):
        if is_skippable_statement(stmt):
            continue
        run_statement(conn, stmt, dry_run=dry_run)


def run_all_in_one(conn, *, dry_run: bool) -> None:
    print("\n==> postgres_all_in_one_edw_agentic.sql (edw → finance_data)")
    raw = (SOURCE_DIR / "postgres_all_in_one_edw_agentic.sql").read_text(encoding="utf-8")
    raw = raw.replace("CREATE SCHEMA IF NOT EXISTS edw", f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    raw = raw.replace("SET search_path TO edw", f"SET search_path TO {SCHEMA}")
    raw = raw.replace("SCHEMA edw", f"SCHEMA {SCHEMA}")
    raw = raw.replace("edw_ro", f"{SCHEMA}_ro")
    # Remove read-only role block (needs CREATEROLE / master)
    raw = re.sub(r"-- Read-only role\s*DO \$\$.*?END\$\$\s*;", "", raw, flags=re.S)

    for stmt in split_sql_statements(raw):
        if is_skippable_statement(stmt):
            continue
        if "CREATE ROLE" in stmt.upper():
            print("  [skip] CREATE ROLE (run as master if needed)")
            continue
        run_statement(conn, stmt, dry_run=dry_run)


def print_summary(conn, *, dry_run: bool) -> None:
    if dry_run:
        return
    tables = conn.run(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = :schema AND table_type = 'BASE TABLE'
        ORDER BY table_name
        """,
        schema=SCHEMA,
    )
    print(f"\n--- {SCHEMA}: {len(tables)} tables ---")
    for (name,) in tables[:20]:
        count = conn.run(f"SELECT COUNT(*) FROM {SCHEMA}.{name}")[0][0]
        print(f"  {name}: {count:,} rows")
    if len(tables) > 20:
        print(f"  ... and {len(tables) - 20} more tables")


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate finance_data schema")
    parser.add_argument("--fresh", action="store_true", help="Drop finance_data schema first")
    parser.add_argument("--all-in-one", action="store_true", help="Use single edw all-in-one SQL file")
    parser.add_argument("--dry-run", action="store_true", help="Print statements only")
    parser.add_argument("--skip-ddl", action="store_true", help="Skip DDL/view files (re-run seeds only)")
    args = parser.parse_args()

    cfg = get_db_config()
    print(f"Database: {cfg['host']}:{cfg['port']}/{cfg['database']}  schema={SCHEMA}")

    conn, _ = connect()
    try:
        bootstrap(conn, fresh=args.fresh, dry_run=args.dry_run)

        if args.all_in_one:
            run_all_in_one(conn, dry_run=args.dry_run)
        else:
            for name, kind in MYEDW_PIPELINE:
                if args.skip_ddl and kind in ("ddl", "views"):
                    print(f"\n==> {name} [skipped]")
                    continue
                run_file(conn, name, kind, dry_run=args.dry_run)

        print_summary(conn, dry_run=args.dry_run)
    finally:
        conn.close()

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
