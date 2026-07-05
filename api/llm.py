"""LLM answer generation (Mistral, OpenAI, Claude, Gemini, OpenRouter, Ollama)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import certifi
import requests

from llm_providers import API_KEY_ENV, DEFAULT_MODELS
from settings_service import get_api_key, get_llm_settings
from sql_sanitize import normalize_llm_sql


@lru_cache(maxsize=1)
def _read_project_env() -> dict[str, str]:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return {}
    values: dict[str, str] = {}
    for raw in env_path.read_text(encoding="utf-8").splitlines():
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


def _env_value(key: str) -> str:
    current = (os.environ.get(key) or "").strip()
    if current:
        return current
    return (_read_project_env().get(key) or "").strip()


def _resolve_external_tls_verify(insecure_env: str | None = None) -> str | bool:
    """Resolve TLS verify option for outbound HTTPS API requests."""
    if insecure_env:
        insecure_flag = _env_value(insecure_env).lower()
        if insecure_flag in {"1", "true", "yes", "on"}:
            return False
    generic_insecure = _env_value("LLM_TLS_INSECURE").lower()
    if generic_insecure in {"1", "true", "yes", "on"}:
        return False
    ca_bundle = _env_value("REQUESTS_CA_BUNDLE")
    if ca_bundle:
        return ca_bundle
    ssl_cert_file = _env_value("SSL_CERT_FILE")
    if ssl_cert_file:
        return ssl_cert_file
    return certifi.where()


def resolve_llm_runtime(
    *,
    backend: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
) -> tuple[str, str, str]:
    """Apply Settings defaults when request omits backend/model/base URL."""
    settings = get_llm_settings()
    resolved_backend = (backend or settings["default_backend"] or "mistral").strip().lower()
    resolved_model = (model or settings["default_model"] or "").strip()
    if not resolved_model:
        resolved_model = DEFAULT_MODELS.get(resolved_backend, DEFAULT_MODELS["mistral"])
    resolved_base = (base_url or settings["ollama_base_url"] or "http://localhost:11434").strip()
    return resolved_backend, resolved_model, resolved_base


def _strip_sql_response(text: str) -> str:
    return normalize_llm_sql(text)


_SQL_GENERATION_RULES = """
Rules:
- Return ONLY the SQL (no markdown, no explanation).
- Return exactly ONE read-only SELECT (WITH ... SELECT is allowed) — never multiple statements separated by semicolons.
- Read the Dataset definition section first — it documents scope, join paths, hub/bridge tables, and caveats.
- Read **Table business rules** — apply status filters, revenue definitions, exclusions, and metric logic exactly as written per table.
- Use Column reference for exact column names and types — match natural-language time phrases to date columns via names and labels.
- When the user names a calendar year (e.g. 2024), filter the chosen date column to that year; use relative date math only when they ask relatively (e.g. "last year").
- Use ONLY tables listed under Allowed tables — never invent names like customers, orders, or products.
- Follow join paths from the Dataset definition (especially hub and bridge tables) instead of guessing FKs.
- If a dimension is listed as unavailable below, omit it — do not fail; answer with what exists.
- Schema-qualify every table exactly as shown (e.g. finance_data.customer_profiles).
- SELECT only — no INSERT, UPDATE, DELETE, DDL.
- Prefer COUNT/SUM/aggregates when the question asks "how many" or totals.
- For overview / "tell me about" questions, SELECT representative columns with LIMIT 25 (or COUNT + sample rows).
- When prior conversation or query results are provided, treat the latest message as a follow-up — keep the same filters, grouping, and grain unless the user clearly changes scope.
""".strip()


def _sql_context_block(
    *,
    conversation_history: list[dict[str, str]] | None = None,
    prior_result=None,
) -> str:
    from conversation_context import format_conversation_block, format_prior_result_block

    history_block = format_conversation_block(conversation_history)
    prior_block = format_prior_result_block(prior_result)
    if not history_block and not prior_block:
        return ""
    return f"{history_block}{prior_block}"


def generate_sql(
    question: str,
    schema_context,
    *,
    model: str | None = None,
    backend: str | None = None,
    base_url: str | None = None,
    gap_instructions: str = "",
    rag_supplement: str = "",
    conversation_history: list[dict[str, str]] | None = None,
    prior_result=None,
) -> str:
    """LLM text-to-SQL from catalog schema context."""
    rag_block = f"\n{rag_supplement.strip()}\n" if rag_supplement.strip() else ""
    context_block = _sql_context_block(
        conversation_history=conversation_history,
        prior_result=prior_result,
    )
    prompt = f"""You are a PostgreSQL expert. Write ONE read-only SELECT query to answer the user question.

{schema_context.to_llm_prompt_block()}
{rag_block}
{context_block}User question:
{question}
{gap_instructions}

{_SQL_GENERATION_RULES}
"""
    raw = generate_answer(prompt, model=model, backend=backend, base_url=base_url)
    return _strip_sql_response(raw)


def repair_sql(
    question: str,
    schema_context,
    failed_sql: str,
    error_message: str,
    *,
    model: str | None = None,
    backend: str | None = None,
    base_url: str | None = None,
    gap_instructions: str = "",
    rag_supplement: str = "",
    conversation_history: list[dict[str, str]] | None = None,
    prior_result=None,
) -> str:
    """Rewrite SQL after a validation or PostgreSQL execution error."""
    rag_block = f"\n{rag_supplement.strip()}\n" if rag_supplement.strip() else ""
    context_block = _sql_context_block(
        conversation_history=conversation_history,
        prior_result=prior_result,
    )
    prompt = f"""You are a PostgreSQL expert. Fix the failed query using ONLY cataloged tables.

{schema_context.to_llm_prompt_block()}
{rag_block}
{context_block}User question:
{question}
{gap_instructions}

Failed SQL:
{failed_sql}

Error:
{error_message}

Rules:
- Return ONLY the corrected SELECT (no markdown, no explanation).
- Return exactly ONE read-only SELECT — no semicolon-separated batches, no DDL, no prose after the query.
- Read the Dataset definition for correct join paths — use bridge/hub tables as documented.
- Read **Table business rules** — preserve status filters and metric exclusions from the catalog.
- Remove or replace missing tables/columns — skip dimensions that caused the error.
- Use ONLY tables from Allowed tables — map business terms to real catalog names.
- Use Column reference for exact column names — do not invent columns.
- Schema-qualify every table exactly as in the catalog.
- SELECT only. Prefer a partial answer over failing.
"""
    raw = generate_answer(prompt, model=model, backend=backend, base_url=base_url)
    return _strip_sql_response(raw)


def generate_partial_sql(
    question: str,
    schema_context,
    *,
    failed_sql: str = "",
    error_messages: list[str] | None = None,
    gap_instructions: str = "",
    rag_supplement: str = "",
    model: str | None = None,
    backend: str | None = None,
    base_url: str | None = None,
) -> str:
    """Best-effort SQL when full question cannot be answered — skip missing elements."""
    errors = "\n".join(error_messages or []) or "(none)"
    rag_block = f"\n{rag_supplement.strip()}\n" if rag_supplement.strip() else ""
    prompt = f"""You are a PostgreSQL expert. The user asked a question that could not be fully answered.

{schema_context.to_llm_prompt_block()}
{rag_block}
User question:
{question}
{gap_instructions}

Previous SQL attempts failed:
{failed_sql or "(none)"}

Errors:
{errors}

Write ONE simpler read-only SELECT that answers what you CAN from the catalog only.
- Return exactly ONE SELECT — no semicolon-separated batches.
- Read the Dataset definition for join paths and caveats before simplifying.
- Read **Table business rules** — keep documented status filters and revenue rules when simplifying.
- Skip any dimension that is missing or caused errors (department, unknown tables, etc.).
- Use ONLY allowed catalog tables and Column reference column names.
- Return ONLY the SQL (no markdown).
"""
    raw = generate_answer(prompt, model=model, backend=backend, base_url=base_url)
    return _strip_sql_response(raw)


def _openai_compatible_chat(
    *,
    url: str,
    api_key: str,
    model: str,
    prompt: str,
    extra_headers: dict[str, str] | None = None,
    tls_verify: str | bool = True,
) -> str:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        **(extra_headers or {}),
    }
    try:
        r = requests.post(
            url,
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
            },
            headers=headers,
            timeout=120,
            verify=tls_verify,
        )
    except requests.exceptions.SSLError as exc:
        raise RuntimeError(
            "TLS certificate verification failed contacting LLM provider. "
            "Set REQUESTS_CA_BUNDLE (or SSL_CERT_FILE) in .env to your CA bundle path. "
            "Temporary local workaround: set MISTRAL_TLS_INSECURE=1 for Mistral "
            "or LLM_TLS_INSECURE=1 for all providers."
        ) from exc
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def generate_answer(
    prompt: str,
    *,
    model: str | None = None,
    backend: str | None = None,
    base_url: str | None = None,
) -> str:
    resolved_backend, resolved_model, resolved_base = resolve_llm_runtime(
        backend=backend, model=model, base_url=base_url
    )

    if resolved_backend == "ollama":
        r = requests.post(
            f"{resolved_base.rstrip('/')}/api/generate",
            json={"model": resolved_model, "prompt": prompt, "stream": False},
            timeout=120,
        )
        r.raise_for_status()
        return r.json()["response"]

    if resolved_backend == "anthropic":
        api_key = get_api_key("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set (Settings → LLM)")
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            json={
                "model": resolved_model,
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": prompt}],
            },
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            timeout=120,
        )
        r.raise_for_status()
        data = r.json()
        parts = data.get("content") or []
        return "".join(p.get("text", "") for p in parts if p.get("type") == "text")

    if resolved_backend == "gemini":
        api_key = get_api_key("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set (Settings → LLM)")
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{resolved_model}:generateContent",
            params={"key": api_key},
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=120,
        )
        r.raise_for_status()
        data = r.json()
        candidates = data.get("candidates") or []
        if not candidates:
            raise RuntimeError("Gemini returned no candidates")
        parts = candidates[0].get("content", {}).get("parts") or []
        return "".join(p.get("text", "") for p in parts)

    env_key = API_KEY_ENV.get(resolved_backend, "MISTRAL_API_KEY")
    api_key = get_api_key(env_key)
    if not api_key:
        raise RuntimeError(f"{env_key} is not set (Settings → LLM)")

    if resolved_backend == "openai":
        url = "https://api.openai.com/v1/chat/completions"
        extra_headers = None
    elif resolved_backend == "openrouter":
        url = "https://openrouter.ai/api/v1/chat/completions"
        extra_headers = {
            "HTTP-Referer": "https://datapro.local",
            "X-Title": "DATA Pro",
        }
        tls_verify = _resolve_external_tls_verify()
    else:
        url = "https://api.mistral.ai/v1/chat/completions"
        extra_headers = None
        tls_verify = _resolve_external_tls_verify("MISTRAL_TLS_INSECURE")

    if resolved_backend == "openai":
        tls_verify = _resolve_external_tls_verify()

    return _openai_compatible_chat(
        url=url,
        api_key=api_key,
        model=resolved_model,
        prompt=prompt,
        extra_headers=extra_headers,
        tls_verify=tls_verify,
    )
