"""Read/write app connection settings (.env) for the Settings UI."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

PROJECT_DIR = Path(__file__).resolve().parent
ENV_PATH = PROJECT_DIR / ".env"

MANAGED_KEYS = (
    "PGHOST",
    "PGPORT",
    "PGUSER",
    "PGPASSWORD",
    "PGDATABASE",
    "DB_SCHEMA",
    "PGSSLMODE",
    "DATABASE_URL",
    "MCP_URL",
    "EMBEDDING_MODEL",
    "DEFAULT_LLM_BACKEND",
    "DEFAULT_LLM_MODEL",
    "OLLAMA_BASE_URL",
    "MISTRAL_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "OPENROUTER_API_KEY",
)

SECRET_KEYS = frozenset(
    {
        "PGPASSWORD",
        "MISTRAL_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "OPENROUTER_API_KEY",
        "DATABASE_URL",
    }
)


def _parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        values[key] = val
    return values


def _quote_env_value(value: str) -> str:
    if not value:
        return '""'
    if re.search(r'[\s#"\\]', value):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def _write_env_file(path: Path, updates: dict[str, str]) -> None:
    existing_lines: list[str] = []
    seen: set[str] = set()
    if path.exists():
        existing_lines = path.read_text(encoding="utf-8").splitlines()

    out: list[str] = []
    for raw in existing_lines:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            out.append(raw)
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in updates:
            if updates[key]:
                out.append(f"{key}={_quote_env_value(updates[key])}")
            seen.add(key)
        else:
            out.append(raw)

    for key in MANAGED_KEYS:
        if key in updates and key not in seen and updates[key]:
            out.append(f"{key}={_quote_env_value(updates[key])}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")


def _reload_env() -> None:
    if load_dotenv is not None:
        load_dotenv(ENV_PATH, override=True)


def get_raw_settings() -> dict[str, str]:
    file_vals = _parse_env_file(ENV_PATH)
    merged = {k: os.environ.get(k, file_vals.get(k, "")) for k in MANAGED_KEYS}
    for k, v in file_vals.items():
        if k not in merged and k in MANAGED_KEYS:
            merged[k] = v
    return {k: (merged.get(k) or "") for k in MANAGED_KEYS}


def get_embedding_model() -> str:
    from llm_providers import DEFAULT_EMBEDDING_MODEL

    raw = get_raw_settings()
    model = (raw.get("EMBEDDING_MODEL") or DEFAULT_EMBEDDING_MODEL).strip()
    return model or DEFAULT_EMBEDDING_MODEL


def get_llm_settings() -> dict[str, str]:
    from llm_providers import DEFAULT_LLM_BACKEND

    raw = get_raw_settings()
    return {
        "default_backend": (raw.get("DEFAULT_LLM_BACKEND") or DEFAULT_LLM_BACKEND).strip()
        or DEFAULT_LLM_BACKEND,
        "default_model": (raw.get("DEFAULT_LLM_MODEL") or "").strip(),
        "ollama_base_url": (raw.get("OLLAMA_BASE_URL") or "http://localhost:11434").strip()
        or "http://localhost:11434",
    }


def get_public_settings() -> dict[str, Any]:
    from llm_providers import (
        DEFAULT_EMBEDDING_MODEL,
        DEFAULT_LLM_BACKEND,
        EMBEDDING_MODEL_OPTIONS,
        LLM_BACKENDS,
    )

    raw = get_raw_settings()
    public: dict[str, Any] = {
        "env_path": str(ENV_PATH),
        "database": {
            "host": raw.get("PGHOST", ""),
            "port": int(raw["PGPORT"]) if str(raw.get("PGPORT", "")).isdigit() else 5432,
            "user": raw.get("PGUSER", ""),
            "database": raw.get("PGDATABASE", ""),
            "schema": raw.get("DB_SCHEMA", "ragpro"),
            "sslmode": raw.get("PGSSLMODE", "require"),
            "database_url": "",
            "password_set": bool(raw.get("PGPASSWORD")),
        },
        "mcp_url": raw.get("MCP_URL", "http://127.0.0.1:8000/mcp"),
        "embedding_model": get_embedding_model(),
        "embedding_model_options": list(EMBEDDING_MODEL_OPTIONS),
        "llm_backends": LLM_BACKENDS,
        "llm": {
            "default_backend": (raw.get("DEFAULT_LLM_BACKEND") or DEFAULT_LLM_BACKEND).strip()
            or DEFAULT_LLM_BACKEND,
            "default_model": (raw.get("DEFAULT_LLM_MODEL") or "").strip(),
            "ollama_base_url": (raw.get("OLLAMA_BASE_URL") or "http://localhost:11434").strip()
            or "http://localhost:11434",
            "mistral_api_key_set": bool(raw.get("MISTRAL_API_KEY")),
            "openai_api_key_set": bool(raw.get("OPENAI_API_KEY")),
            "anthropic_api_key_set": bool(raw.get("ANTHROPIC_API_KEY")),
            "gemini_api_key_set": bool(raw.get("GEMINI_API_KEY")),
            "openrouter_api_key_set": bool(raw.get("OPENROUTER_API_KEY")),
        },
        # Legacy field for older clients
        "mistral_api_key_set": bool(raw.get("MISTRAL_API_KEY")),
    }
    if raw.get("DATABASE_URL"):
        public["database"]["database_url"] = "***"
        public["database"]["use_database_url"] = True
    else:
        public["database"]["use_database_url"] = False
    return public


def save_settings(payload: dict[str, Any]) -> dict[str, Any]:
    current = get_raw_settings()
    updates: dict[str, str] = dict(current)

    db = payload.get("database") or {}
    use_url = bool(db.get("use_database_url"))
    if use_url:
        url = (db.get("database_url") or "").strip()
        if url and url != "***":
            updates["DATABASE_URL"] = url
        elif current.get("DATABASE_URL"):
            updates["DATABASE_URL"] = current["DATABASE_URL"]
        else:
            updates["DATABASE_URL"] = url
        for key in ("PGHOST", "PGPORT", "PGUSER", "PGPASSWORD", "PGDATABASE"):
            updates[key] = ""
    else:
        updates["DATABASE_URL"] = ""
        if db.get("host") is not None:
            updates["PGHOST"] = str(db.get("host", "")).strip()
        if db.get("port") is not None:
            updates["PGPORT"] = str(db.get("port", 5432))
        if db.get("user") is not None:
            updates["PGUSER"] = str(db.get("user", "")).strip()
        if db.get("database") is not None:
            updates["PGDATABASE"] = str(db.get("database", "")).strip()
        password = db.get("password")
        if password:
            updates["PGPASSWORD"] = str(password)
        if db.get("schema") is not None:
            updates["DB_SCHEMA"] = str(db.get("schema", "ragpro")).strip() or "ragpro"
        if db.get("sslmode") is not None:
            updates["PGSSLMODE"] = str(db.get("sslmode", "require")).strip() or "require"

    if payload.get("mcp_url") is not None:
        updates["MCP_URL"] = str(payload.get("mcp_url", "")).strip()

    if payload.get("embedding_model") is not None:
        updates["EMBEDDING_MODEL"] = str(payload.get("embedding_model", "")).strip()

    llm = payload.get("llm") or {}
    if llm.get("default_backend") is not None:
        updates["DEFAULT_LLM_BACKEND"] = str(llm.get("default_backend", "")).strip()
    if llm.get("default_model") is not None:
        updates["DEFAULT_LLM_MODEL"] = str(llm.get("default_model", "")).strip()
    if llm.get("ollama_base_url") is not None:
        updates["OLLAMA_BASE_URL"] = str(llm.get("ollama_base_url", "")).strip()

    for key_field, env_key in (
        ("mistral_api_key", "MISTRAL_API_KEY"),
        ("openai_api_key", "OPENAI_API_KEY"),
        ("anthropic_api_key", "ANTHROPIC_API_KEY"),
        ("gemini_api_key", "GEMINI_API_KEY"),
        ("openrouter_api_key", "OPENROUTER_API_KEY"),
    ):
        api_key = payload.get(key_field) or llm.get(key_field)
        if api_key:
            updates[env_key] = str(api_key).strip()

    prev_embedding = current.get("EMBEDDING_MODEL", "")
    _write_env_file(ENV_PATH, {k: updates[k] for k in MANAGED_KEYS if updates.get(k) is not None})
    _reload_env()
    for key in MANAGED_KEYS:
        if updates.get(key):
            os.environ[key] = updates[key]
    if updates.get("EMBEDDING_MODEL") and updates.get("EMBEDDING_MODEL") != prev_embedding:
        try:
            from api.deps import clear_embedder_cache

            clear_embedder_cache()
        except Exception:
            pass
    return get_public_settings()


def _resolve_db_config(db: dict[str, Any] | None = None) -> dict[str, Any]:
    from urllib.parse import urlparse, unquote

    current = get_raw_settings()
    db = db or {}
    if db.get("use_database_url"):
        url = (db.get("database_url") or "").strip()
        if not url or url == "***":
            url = current.get("DATABASE_URL", "")
        if not url:
            raise ValueError("DATABASE_URL is required")
        parsed = urlparse(url)
        return {
            "host": parsed.hostname,
            "port": int(parsed.port or 5432),
            "user": parsed.username,
            "password": unquote(parsed.password or ""),
            "database": (parsed.path or "/").lstrip("/"),
            "sslmode": current.get("PGSSLMODE", "require"),
        }

    password = (db.get("password") or "").strip() or current.get("PGPASSWORD", "")
    host = (db.get("host") or current.get("PGHOST", "")).strip()
    user = (db.get("user") or current.get("PGUSER", "")).strip()
    database = (db.get("database") or current.get("PGDATABASE", "")).strip()
    if not all([host, user, password, database]):
        raise ValueError("Host, user, password, and database are required")
    port = db.get("port") or current.get("PGPORT") or 5432
    return {
        "host": host,
        "port": int(port),
        "user": user,
        "password": password,
        "database": database,
        "sslmode": (db.get("sslmode") or current.get("PGSSLMODE") or "require").strip(),
    }


def test_database_connection(overrides: dict[str, Any] | None = None) -> tuple[bool, str]:
    import pg8000.native

    from db import _ssl_context

    try:
        cfg = _resolve_db_config((overrides or {}).get("database"))
    except Exception as exc:
        return False, str(exc)

    try:
        conn = pg8000.native.Connection(
            user=cfg["user"],
            password=cfg["password"],
            host=cfg["host"],
            port=cfg["port"],
            database=cfg["database"],
            ssl_context=_ssl_context(cfg["sslmode"]),
            timeout=10,
        )
        conn.run("SELECT 1")
        conn.close()
        return True, f"Connected to {cfg['database']}@{cfg['host']}:{cfg['port']}"
    except Exception as exc:
        return False, str(exc)
