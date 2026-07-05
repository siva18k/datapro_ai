"""Trino warehouse connector definitions and catalog property builders.

Industry pattern (Metabase, Superset, DBeaver via Trino): each data source is a Trino
*catalog* with a connector.type, JDBC URL (or cloud account), credentials, and a default schema.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

WAREHOUSE_TYPE_POSTGRESQL = "postgresql"
WAREHOUSE_TYPE_MYSQL = "mysql"
WAREHOUSE_TYPE_MARIADB = "mariadb"
WAREHOUSE_TYPE_SQLSERVER = "sqlserver"
WAREHOUSE_TYPE_ORACLE = "oracle"
WAREHOUSE_TYPE_SNOWFLAKE = "snowflake"
WAREHOUSE_TYPE_REDSHIFT = "redshift"
WAREHOUSE_TYPE_CLICKHOUSE = "clickhouse"
WAREHOUSE_TYPE_CUSTOM = "custom"

# Trino connector.name values we generate catalog files for.
WAREHOUSE_CONNECTORS: dict[str, dict[str, Any]] = {
    WAREHOUSE_TYPE_POSTGRESQL: {
        "label": "PostgreSQL",
        "trino_connector": "postgresql",
        "default_port": 5432,
        "default_database": "postgres",
        "default_schema": "public",
        "group": "relational",
        "description": "PostgreSQL, Aurora Postgres, AlloyDB, and compatible databases.",
        "fields": [
            {"id": "host", "label": "Host", "type": "text", "required": True},
            {"id": "port", "label": "Port", "type": "number", "required": True},
            {"id": "database", "label": "Database", "type": "text", "required": True},
            {"id": "user", "label": "Username", "type": "text", "required": True},
            {"id": "password", "label": "Password", "type": "password", "required": True},
            {
                "id": "sslmode",
                "label": "SSL mode",
                "type": "select",
                "required": False,
                "options": [
                    {"value": "require", "label": "require"},
                    {"value": "verify-full", "label": "verify-full"},
                    {"value": "verify-ca", "label": "verify-ca"},
                    {"value": "prefer", "label": "prefer"},
                    {"value": "disable", "label": "disable"},
                ],
            },
        ],
    },
    WAREHOUSE_TYPE_MYSQL: {
        "label": "MySQL",
        "trino_connector": "mysql",
        "default_port": 3306,
        "default_database": "",
        "default_schema": "",
        "group": "relational",
        "description": "MySQL and MariaDB-compatible servers (native MySQL connector).",
        "fields": [
            {"id": "host", "label": "Host", "type": "text", "required": True},
            {"id": "port", "label": "Port", "type": "number", "required": True},
            {"id": "database", "label": "Database (optional)", "type": "text", "required": False},
            {"id": "user", "label": "Username", "type": "text", "required": True},
            {"id": "password", "label": "Password", "type": "password", "required": True},
        ],
    },
    WAREHOUSE_TYPE_MARIADB: {
        "label": "MariaDB",
        "trino_connector": "mariadb",
        "default_port": 3306,
        "default_database": "",
        "default_schema": "",
        "group": "relational",
        "description": "MariaDB via the dedicated Trino MariaDB connector.",
        "fields": [
            {"id": "host", "label": "Host", "type": "text", "required": True},
            {"id": "port", "label": "Port", "type": "number", "required": True},
            {"id": "database", "label": "Database (optional)", "type": "text", "required": False},
            {"id": "user", "label": "Username", "type": "text", "required": True},
            {"id": "password", "label": "Password", "type": "password", "required": True},
        ],
    },
    WAREHOUSE_TYPE_SQLSERVER: {
        "label": "SQL Server",
        "trino_connector": "sqlserver",
        "default_port": 1433,
        "default_database": "master",
        "default_schema": "dbo",
        "group": "relational",
        "description": "Microsoft SQL Server and Azure SQL.",
        "fields": [
            {"id": "host", "label": "Host", "type": "text", "required": True},
            {"id": "port", "label": "Port", "type": "number", "required": True},
            {"id": "database", "label": "Database", "type": "text", "required": True},
            {"id": "user", "label": "Username", "type": "text", "required": True},
            {"id": "password", "label": "Password", "type": "password", "required": True},
            {
                "id": "encrypt",
                "label": "Encrypt connection",
                "type": "select",
                "required": False,
                "options": [
                    {"value": "true", "label": "true"},
                    {"value": "false", "label": "false"},
                ],
            },
        ],
    },
    WAREHOUSE_TYPE_ORACLE: {
        "label": "Oracle",
        "trino_connector": "oracle",
        "default_port": 1521,
        "default_database": "",
        "default_schema": "",
        "group": "relational",
        "description": "Oracle Database (SID or service name).",
        "fields": [
            {"id": "host", "label": "Host", "type": "text", "required": True},
            {"id": "port", "label": "Port", "type": "number", "required": True},
            {
                "id": "oracle_connect_mode",
                "label": "Connect using",
                "type": "select",
                "required": True,
                "options": [
                    {"value": "service", "label": "Service name"},
                    {"value": "sid", "label": "SID"},
                ],
            },
            {
                "id": "oracle_service",
                "label": "Service name / SID",
                "type": "text",
                "required": True,
            },
            {"id": "user", "label": "Username", "type": "text", "required": True},
            {"id": "password", "label": "Password", "type": "password", "required": True},
        ],
    },
    WAREHOUSE_TYPE_SNOWFLAKE: {
        "label": "Snowflake",
        "trino_connector": "snowflake",
        "default_port": 443,
        "default_database": "",
        "default_schema": "PUBLIC",
        "group": "cloud",
        "description": "Snowflake warehouse (account, role, and compute warehouse).",
        "fields": [
            {
                "id": "snowflake_account",
                "label": "Account locator",
                "type": "text",
                "required": True,
                "placeholder": "xy12345.us-east-1",
            },
            {"id": "database", "label": "Database", "type": "text", "required": True},
            {
                "id": "snowflake_warehouse",
                "label": "Warehouse",
                "type": "text",
                "required": True,
            },
            {
                "id": "snowflake_role",
                "label": "Role (optional)",
                "type": "text",
                "required": False,
            },
            {"id": "user", "label": "Username", "type": "text", "required": True},
            {"id": "password", "label": "Password", "type": "password", "required": True},
        ],
    },
    WAREHOUSE_TYPE_REDSHIFT: {
        "label": "Amazon Redshift",
        "trino_connector": "redshift",
        "default_port": 5439,
        "default_database": "dev",
        "default_schema": "public",
        "group": "cloud",
        "description": "Amazon Redshift via the Trino Redshift connector.",
        "fields": [
            {"id": "host", "label": "Cluster endpoint", "type": "text", "required": True},
            {"id": "port", "label": "Port", "type": "number", "required": True},
            {"id": "database", "label": "Database", "type": "text", "required": True},
            {"id": "user", "label": "Username", "type": "text", "required": True},
            {"id": "password", "label": "Password", "type": "password", "required": True},
            {
                "id": "sslmode",
                "label": "SSL mode",
                "type": "select",
                "required": False,
                "options": [
                    {"value": "require", "label": "require"},
                    {"value": "disable", "label": "disable"},
                ],
            },
        ],
    },
    WAREHOUSE_TYPE_CLICKHOUSE: {
        "label": "ClickHouse",
        "trino_connector": "clickhouse",
        "default_port": 8123,
        "default_database": "default",
        "default_schema": "default",
        "group": "analytics",
        "description": "ClickHouse OLAP database.",
        "fields": [
            {"id": "host", "label": "Host", "type": "text", "required": True},
            {"id": "port", "label": "Port", "type": "number", "required": True},
            {"id": "database", "label": "Database", "type": "text", "required": True},
            {"id": "user", "label": "Username", "type": "text", "required": True},
            {"id": "password", "label": "Password", "type": "password", "required": False},
        ],
    },
    WAREHOUSE_TYPE_CUSTOM: {
        "label": "Custom JDBC (advanced)",
        "trino_connector": "",
        "default_port": 0,
        "default_database": "",
        "default_schema": "public",
        "group": "advanced",
        "description": "Any Trino connector — supply connector.name and JDBC URL manually.",
        "fields": [
            {
                "id": "trino_connector_name",
                "label": "Trino connector.name",
                "type": "text",
                "required": True,
                "placeholder": "postgresql",
            },
            {
                "id": "connection_url",
                "label": "JDBC connection URL",
                "type": "text",
                "required": True,
                "placeholder": "jdbc:postgresql://host:5432/db",
            },
            {"id": "user", "label": "Username", "type": "text", "required": True},
            {"id": "password", "label": "Password", "type": "password", "required": True},
        ],
    },
}


def list_warehouse_connectors_public() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for key, meta in WAREHOUSE_CONNECTORS.items():
        out.append(
            {
                "id": key,
                "label": meta["label"],
                "group": meta["group"],
                "description": meta["description"],
                "default_port": meta["default_port"],
                "default_database": meta["default_database"],
                "default_schema": meta["default_schema"],
                "fields": meta["fields"],
            }
        )
    return out


def normalize_warehouse_type(value: str | None) -> str:
    key = (value or WAREHOUSE_TYPE_POSTGRESQL).strip().lower()
    if key in WAREHOUSE_CONNECTORS:
        return key
    if key in ("postgres", "aurora"):
        return WAREHOUSE_TYPE_POSTGRESQL
    return WAREHOUSE_TYPE_POSTGRESQL


def warehouse_connector_label(warehouse_type: str) -> str:
    meta = WAREHOUSE_CONNECTORS.get(normalize_warehouse_type(warehouse_type))
    return meta["label"] if meta else warehouse_type


def _extra(row: dict[str, Any]) -> dict[str, str]:
    raw = row.get("extra") or {}
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items() if v is not None and str(v).strip()}
    return {}


def _row_value(row: dict[str, Any], key: str, default: str = "") -> str:
    extra = _extra(row)
    if key in extra and str(extra[key]).strip():
        return str(extra[key]).strip()
    return str(row.get(key) or default).strip()


def _jdbc_postgresql_url(row: dict[str, Any]) -> str:
    host = _row_value(row, "host")
    port = int(row.get("port") or 5432)
    database = _row_value(row, "database", "postgres")
    sslmode = _row_value(row, "sslmode", "require").lower()
    params: list[str] = []
    if sslmode in ("require", "verify-ca", "verify-full"):
        params.append("ssl=true")
        if sslmode == "verify-full":
            params.append("sslmode=verify-full")
        elif sslmode == "verify-ca":
            params.append("sslmode=verify-ca")
        else:
            params.append("sslmode=require")
    query = f"?{'&'.join(params)}" if params else ""
    return f"jdbc:postgresql://{host}:{port}/{quote(database, safe='')}{query}"


def _jdbc_mysql_url(row: dict[str, Any]) -> str:
    host = _row_value(row, "host")
    port = int(row.get("port") or 3306)
    database = _row_value(row, "database")
    base = f"jdbc:mysql://{host}:{port}"
    return f"{base}/{quote(database, safe='')}" if database else base


def _jdbc_sqlserver_url(row: dict[str, Any]) -> str:
    host = _row_value(row, "host")
    port = int(row.get("port") or 1433)
    database = _row_value(row, "database", "master")
    encrypt = _row_value(row, "encrypt", "false").lower()
    return (
        f"jdbc:sqlserver://{host}:{port};databaseName={database};encrypt={encrypt}"
    )


def _jdbc_oracle_url(row: dict[str, Any]) -> str:
    host = _row_value(row, "host")
    port = int(row.get("port") or 1521)
    mode = _row_value(row, "oracle_connect_mode", "service").lower()
    service = _row_value(row, "oracle_service")
    if mode == "sid":
        return f"jdbc:oracle:thin:@{host}:{port}:{service}"
    return f"jdbc:oracle:thin:@//{host}:{port}/{service}"


def _jdbc_snowflake_url(row: dict[str, Any]) -> str:
    account = _row_value(row, "snowflake_account")
    return f"jdbc:snowflake://{account}.snowflakecomputing.com"


def _jdbc_redshift_url(row: dict[str, Any]) -> str:
    host = _row_value(row, "host")
    port = int(row.get("port") or 5439)
    database = _row_value(row, "database", "dev")
    return f"jdbc:redshift://{host}:{port}/{quote(database, safe='')}"


def _jdbc_clickhouse_url(row: dict[str, Any]) -> str:
    host = _row_value(row, "host")
    port = int(row.get("port") or 8123)
    database = _row_value(row, "database", "default")
    return f"jdbc:clickhouse://{host}:{port}/{quote(database, safe='')}"


def build_connection_url(row: dict[str, Any]) -> str:
    warehouse_type = normalize_warehouse_type(row.get("warehouse_type"))
    if warehouse_type == WAREHOUSE_TYPE_CUSTOM:
        url = _row_value(row, "connection_url")
        if not url:
            raise ValueError("JDBC connection URL is required for custom connectors.")
        return url
    builders = {
        WAREHOUSE_TYPE_POSTGRESQL: _jdbc_postgresql_url,
        WAREHOUSE_TYPE_MYSQL: _jdbc_mysql_url,
        WAREHOUSE_TYPE_MARIADB: _jdbc_mysql_url,
        WAREHOUSE_TYPE_SQLSERVER: _jdbc_sqlserver_url,
        WAREHOUSE_TYPE_ORACLE: _jdbc_oracle_url,
        WAREHOUSE_TYPE_SNOWFLAKE: _jdbc_snowflake_url,
        WAREHOUSE_TYPE_REDSHIFT: _jdbc_redshift_url,
        WAREHOUSE_TYPE_CLICKHOUSE: _jdbc_clickhouse_url,
    }
    builder = builders.get(warehouse_type)
    if not builder:
        raise ValueError(f"Unsupported warehouse type: {warehouse_type}")
    return builder(row)


def build_catalog_properties(row: dict[str, Any], *, catalog: str) -> str:
    warehouse_type = normalize_warehouse_type(row.get("warehouse_type"))
    meta = WAREHOUSE_CONNECTORS[warehouse_type]
    user = _row_value(row, "user")
    password = row.get("password") or ""
    if warehouse_type != WAREHOUSE_TYPE_CLICKHOUSE and not user:
        raise ValueError(f"Connection «{row.get('name', catalog)}» is missing username.")
    if warehouse_type not in (WAREHOUSE_TYPE_CLICKHOUSE, WAREHOUSE_TYPE_CUSTOM) and not user:
        raise ValueError(f"Connection «{row.get('name', catalog)}» is missing username.")
    if warehouse_type == WAREHOUSE_TYPE_CUSTOM:
        connector_name = _row_value(row, "trino_connector_name")
        if not connector_name:
            raise ValueError("Trino connector.name is required for custom connections.")
    elif warehouse_type == WAREHOUSE_TYPE_SNOWFLAKE:
        if not _row_value(row, "snowflake_account"):
            raise ValueError("Snowflake account locator is required.")
        if not _row_value(row, "database"):
            raise ValueError("Snowflake database is required.")
        if not _row_value(row, "snowflake_warehouse"):
            raise ValueError("Snowflake warehouse is required.")
    elif warehouse_type not in (WAREHOUSE_TYPE_MYSQL, WAREHOUSE_TYPE_MARIADB):
        if not _row_value(row, "host"):
            raise ValueError(f"Connection «{row.get('name', catalog)}» is missing host.")

    trino_connector = (
        _row_value(row, "trino_connector_name")
        if warehouse_type == WAREHOUSE_TYPE_CUSTOM
        else meta["trino_connector"]
    )
    connection_url = build_connection_url(row)

    lines = [
        f"# Trino catalog «{catalog}» — {meta['label']} (managed by DATA Pro).",
        "# Do not commit; see docs/trino.md.",
        f"connector.name={trino_connector}",
        f"connection-url={connection_url}",
    ]
    if user:
        lines.append(f"connection-user={user}")
    lines.append(f"connection-password={password}")

    if warehouse_type == WAREHOUSE_TYPE_SNOWFLAKE:
        account = _row_value(row, "snowflake_account").split(".")[0]
        lines.append(f"snowflake.account={account}")
        lines.append(f"snowflake.database={_row_value(row, 'database')}")
        lines.append(f"snowflake.warehouse={_row_value(row, 'snowflake_warehouse')}")
        role = _row_value(row, "snowflake_role")
        if role:
            lines.append(f"snowflake.role={role}")

    lines.append("")
    return "\n".join(lines)


def parse_catalog_properties(path_text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def infer_warehouse_type_from_catalog_file(props: dict[str, str]) -> str:
    connector = (props.get("connector.name") or "").strip().lower()
    mapping = {
        "postgresql": WAREHOUSE_TYPE_POSTGRESQL,
        "mysql": WAREHOUSE_TYPE_MYSQL,
        "mariadb": WAREHOUSE_TYPE_MARIADB,
        "sqlserver": WAREHOUSE_TYPE_SQLSERVER,
        "oracle": WAREHOUSE_TYPE_ORACLE,
        "snowflake": WAREHOUSE_TYPE_SNOWFLAKE,
        "redshift": WAREHOUSE_TYPE_REDSHIFT,
        "clickhouse": WAREHOUSE_TYPE_CLICKHOUSE,
    }
    if connector in mapping:
        return mapping[connector]
    if connector:
        return WAREHOUSE_TYPE_CUSTOM
    return WAREHOUSE_TYPE_POSTGRESQL


def extract_row_extras_from_catalog(props: dict[str, str], warehouse_type: str) -> dict[str, str]:
    extra: dict[str, str] = {}
    if warehouse_type == WAREHOUSE_TYPE_SNOWFLAKE:
        if props.get("snowflake.account"):
            extra["snowflake_account"] = props["snowflake.account"]
        if props.get("snowflake.warehouse"):
            extra["snowflake_warehouse"] = props["snowflake.warehouse"]
        if props.get("snowflake.role"):
            extra["snowflake_role"] = props["snowflake.role"]
        if props.get("snowflake.database"):
            extra["database"] = props["snowflake.database"]
    if warehouse_type == WAREHOUSE_TYPE_CUSTOM:
        if props.get("connector.name"):
            extra["trino_connector_name"] = props["connector.name"]
        if props.get("connection-url"):
            extra["connection_url"] = props["connection-url"]
    url = props.get("connection-url") or ""
    if warehouse_type == WAREHOUSE_TYPE_ORACLE:
        m = re.search(r"@//([^:]+):(\d+)/([^?]+)", url)
        if m:
            extra["host"] = m.group(1)
            extra["port"] = m.group(2)
            extra["oracle_service"] = m.group(3)
            extra["oracle_connect_mode"] = "service"
        m = re.search(r"@([^:]+):(\d+):([^?]+)", url)
        if m:
            extra["host"] = m.group(1)
            extra["port"] = m.group(2)
            extra["oracle_service"] = m.group(3)
            extra["oracle_connect_mode"] = "sid"
    return extra


def default_schema_for_type(warehouse_type: str) -> str:
    return WAREHOUSE_CONNECTORS[normalize_warehouse_type(warehouse_type)]["default_schema"]


def default_port_for_type(warehouse_type: str) -> int:
    return int(WAREHOUSE_CONNECTORS[normalize_warehouse_type(warehouse_type)]["default_port"])


def validate_warehouse_row(row: dict[str, Any], *, require_password: bool = True) -> None:
    """Validate connection payload against connector field schema."""
    warehouse_type = normalize_warehouse_type(row.get("warehouse_type"))
    meta = WAREHOUSE_CONNECTORS[warehouse_type]
    for field in meta["fields"]:
        field_id = field["id"]
        if field_id == "password":
            if require_password and not str(row.get("password") or "").strip():
                raise ValueError("Database password is required.")
            continue
        if not field.get("required"):
            continue
        if not _row_value(row, field_id):
            raise ValueError(f"{field['label']} is required.")
