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
    "MLX_MODEL_PATH",
    "MISTRAL_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "OPENROUTER_API_KEY",
    "ASK_CONVERSATION_TURNS",
    "TRINO_HOST",
    "TRINO_PORT",
    "TRINO_USER",
    "TRINO_PASSWORD",
    "TRINO_HTTP_SCHEME",
    "TRINO_VERIFY_SSL",
)

SECRET_KEYS = frozenset(
    {
        "PGPASSWORD",
        "MISTRAL_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "OPENROUTER_API_KEY",
        "TRINO_PASSWORD",
        "DATABASE_URL",
    }
)

MIN_API_KEY_LENGTH = 20


def _looks_like_api_key(value: str) -> bool:
    cleaned = (value or "").strip()
    return len(cleaned) >= MIN_API_KEY_LENGTH and "@" not in cleaned


def _sanitize_llm_model_override(value: str) -> str:
    """Reject email/autofill junk stored in the model override slot."""
    cleaned = (value or "").strip()
    if not cleaned:
        return ""
    if "@" in cleaned:
        return ""
    return cleaned


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
            elif key in SECRET_KEYS:
                # Keep existing secrets when save did not supply a new value.
                out.append(raw)
                seen.add(key)
            else:
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


def _purge_invalid_default_llm_model_from_file() -> bool:
    """Drop autofill junk (e.g. email) from DEFAULT_LLM_MODEL in .env."""
    file_vals = _parse_env_file(ENV_PATH)
    raw = (file_vals.get("DEFAULT_LLM_MODEL") or "").strip()
    if not raw or _sanitize_llm_model_override(raw) == raw:
        return False
    _write_env_file(ENV_PATH, {"DEFAULT_LLM_MODEL": ""})
    os.environ.pop("DEFAULT_LLM_MODEL", None)
    return True


def scrub_invalid_managed_settings() -> None:
    """One-time cleanup for bad values saved by browser autofill."""
    if _purge_invalid_default_llm_model_from_file():
        _reload_env()
    if not _sanitize_llm_model_override(os.environ.get("DEFAULT_LLM_MODEL", "")):
        os.environ.pop("DEFAULT_LLM_MODEL", None)


def get_raw_settings() -> dict[str, str]:
    file_vals = _parse_env_file(ENV_PATH)
    merged: dict[str, str] = {}
    for k in MANAGED_KEYS:
        file_v = (file_vals.get(k) or "").strip()
        env_v = (os.environ.get(k) or "").strip()
        if k in SECRET_KEYS:
            file_ok = _looks_like_api_key(file_v)
            env_ok = _looks_like_api_key(env_v)
            if file_ok:
                value = file_v
            elif env_ok:
                value = env_v
            else:
                value = file_v or env_v
        else:
            # Prefer .env so manual edits and Settings saves apply without restarting the API.
            value = file_v or env_v
        if k == "DEFAULT_LLM_MODEL":
            value = _sanitize_llm_model_override(value)
        merged[k] = value
    return {k: (merged.get(k) or "") for k in MANAGED_KEYS}


def get_api_key(env_key: str) -> str:
    """Resolve a provider API key from managed settings (.env with env fallback)."""
    return (get_raw_settings().get(env_key) or "").strip()


def apply_managed_settings_to_env(env: dict[str, str] | None = None) -> dict[str, str]:
    """Overlay managed settings onto a subprocess env (fresh .env wins over stale exports)."""
    out = dict(env or os.environ)
    raw = get_raw_settings()
    for key, value in raw.items():
        if value:
            out[key] = value
        elif key == "DEFAULT_LLM_MODEL":
            out.pop(key, None)
    return out


def get_embedding_model() -> str:
    from llm_providers import DEFAULT_EMBEDDING_MODEL

    raw = get_raw_settings()
    model = (raw.get("EMBEDDING_MODEL") or DEFAULT_EMBEDDING_MODEL).strip()
    if not model or not model.startswith("mistral-embed"):
        return DEFAULT_EMBEDDING_MODEL
    return model


def get_ask_conversation_turns() -> int:
    from conversation_context import DEFAULT_ASK_CONVERSATION_TURNS, MAX_ASK_CONVERSATION_TURNS

    raw = get_raw_settings().get("ASK_CONVERSATION_TURNS", "").strip()
    if not raw:
        return DEFAULT_ASK_CONVERSATION_TURNS
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_ASK_CONVERSATION_TURNS
    return max(0, min(value, MAX_ASK_CONVERSATION_TURNS))


def get_llm_settings() -> dict[str, str]:
    from llm_providers import DEFAULT_LLM_BACKEND

    raw = get_raw_settings()
    return {
        "default_backend": (raw.get("DEFAULT_LLM_BACKEND") or DEFAULT_LLM_BACKEND).strip()
        or DEFAULT_LLM_BACKEND,
        "default_model": _sanitize_llm_model_override(raw.get("DEFAULT_LLM_MODEL") or ""),
        "ollama_base_url": (raw.get("OLLAMA_BASE_URL") or "http://localhost:11434").strip()
        or "http://localhost:11434",
    }


def _parse_database_url(url: str) -> dict[str, Any]:
    from urllib.parse import parse_qs, unquote, urlparse

    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    sslmode = (qs.get("sslmode") or ["require"])[0]
    return {
        "host": parsed.hostname or "",
        "port": int(parsed.port or 5432),
        "user": unquote(parsed.username or ""),
        "password": unquote(parsed.password or ""),
        "database": (parsed.path or "/").lstrip("/") or "",
        "sslmode": sslmode or "require",
        "password_set": bool(parsed.password),
    }


def get_public_settings() -> dict[str, Any]:
    from llm_providers import (
        DEFAULT_EMBEDDING_MODEL,
        DEFAULT_LLM_BACKEND,
        EMBEDDING_MODEL_OPTIONS,
        LLM_BACKENDS,
        MISTRAL_MODEL_OPTIONS,
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
        "mistral_model_options": list(MISTRAL_MODEL_OPTIONS),
        "llm": {
            "default_backend": (raw.get("DEFAULT_LLM_BACKEND") or DEFAULT_LLM_BACKEND).strip()
            or DEFAULT_LLM_BACKEND,
            "default_model": _sanitize_llm_model_override(raw.get("DEFAULT_LLM_MODEL") or ""),
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
        "ask": {
            "conversation_turns": get_ask_conversation_turns(),
            "max_conversation_turns": 20,
        },
    }
    if raw.get("DATABASE_URL"):
        parsed = _parse_database_url(raw["DATABASE_URL"])
        public["database"].update(
            {
                "host": parsed["host"],
                "port": parsed["port"],
                "user": parsed["user"],
                "database": parsed["database"],
                "sslmode": parsed["sslmode"],
                "password_set": parsed["password_set"],
                "database_url": "***",
                "use_database_url": True,
            }
        )
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

    ask = payload.get("ask") or {}
    if ask.get("conversation_turns") is not None:
        from conversation_context import MAX_ASK_CONVERSATION_TURNS

        try:
            turns = int(ask.get("conversation_turns"))
        except (TypeError, ValueError):
            turns = 0
        updates["ASK_CONVERSATION_TURNS"] = str(max(0, min(turns, MAX_ASK_CONVERSATION_TURNS)))

    llm = payload.get("llm") or {}
    if llm.get("default_backend") is not None:
        updates["DEFAULT_LLM_BACKEND"] = str(llm.get("default_backend", "")).strip()
    if llm.get("default_model") is not None:
        updates["DEFAULT_LLM_MODEL"] = _sanitize_llm_model_override(str(llm.get("default_model", "")))
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
        if not api_key:
            continue
        cleaned = str(api_key).strip()
        if len(cleaned) < MIN_API_KEY_LENGTH:
            continue
        updates[env_key] = cleaned

    prev_embedding = current.get("EMBEDDING_MODEL", "")
    write_payload = {k: updates[k] for k in MANAGED_KEYS if updates.get(k) is not None}
    if "DEFAULT_LLM_MODEL" in updates and not updates["DEFAULT_LLM_MODEL"]:
        write_payload["DEFAULT_LLM_MODEL"] = ""
    _write_env_file(ENV_PATH, write_payload)
    _reload_env()
    for key in MANAGED_KEYS:
        value = updates.get(key, "")
        if value:
            os.environ[key] = value
        elif key in updates and not value:
            os.environ.pop(key, None)
    if updates.get("EMBEDDING_MODEL") and updates.get("EMBEDDING_MODEL") != prev_embedding:
        try:
            from api.deps import clear_embedder_cache

            clear_embedder_cache()
        except Exception:
            pass
    return get_public_settings()


def _resolve_db_config(db: dict[str, Any] | None = None) -> dict[str, Any]:
    current = get_raw_settings()
    db = db or {}
    if db.get("use_database_url"):
        url = (db.get("database_url") or "").strip()
        if not url or url == "***":
            url = current.get("DATABASE_URL", "")
        if not url:
            raise ValueError("DATABASE_URL is required")
        parsed_fields = _parse_database_url(url)
        return {
            "host": parsed_fields["host"],
            "port": parsed_fields["port"],
            "user": parsed_fields["user"],
            "password": parsed_fields["password"],
            "database": parsed_fields["database"],
            "sslmode": parsed_fields["sslmode"],
        }

    password = (db.get("password") or "").strip() or current.get("PGPASSWORD", "")
    host = (db.get("host") or current.get("PGHOST", "")).strip()
    user = (db.get("user") or current.get("PGUSER", "")).strip()
    database = (db.get("database") or current.get("PGDATABASE", "")).strip()
    sslmode = (db.get("sslmode") or current.get("PGSSLMODE") or "require").strip()
    port = db.get("port") or current.get("PGPORT") or 5432

    # Match db.get_db_config(): fill missing fields from DATABASE_URL when present.
    if current.get("DATABASE_URL"):
        parsed = _parse_database_url(current["DATABASE_URL"])
        host = host or parsed["host"]
        user = user or parsed["user"]
        password = password or parsed["password"]
        database = database or parsed["database"]
        if not db.get("sslmode") and not current.get("PGSSLMODE"):
            sslmode = parsed["sslmode"] or sslmode
        if not db.get("port") and not current.get("PGPORT"):
            port = parsed["port"] or port

    if not all([host, user, password, database]):
        raise ValueError("Host, user, password, and database are required")
    return {
        "host": host,
        "port": int(port),
        "user": user,
        "password": password,
        "database": database,
        "sslmode": sslmode,
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
