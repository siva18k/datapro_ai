"""LLM provider metadata and default models."""

from __future__ import annotations

EMBEDDING_MODEL_OPTIONS = (
    "all-MiniLM-L6-v2",
    "all-mpnet-base-v2",
    "paraphrase-multilingual-MiniLM-L12-v2",
)

DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# Mistral La Plateforme free-tier chat models (Experiment plan rate limits vary by model).
# Embedding, moderation, and audio models are omitted — not used for Ask / Analytics chat.
MISTRAL_MODEL_OPTIONS: list[dict[str, str]] = [
    {
        "id": "codestral-2508",
        "label": "Codestral 2508",
        "hint": "Code & SQL — strong free-tier limits (625K TPM)",
    },
    {
        "id": "ministral-3b-2512",
        "label": "Ministral 3B",
        "hint": "Fast general chat — highest free throughput (1.3M TPM)",
    },
    {
        "id": "ministral-8b-2512",
        "label": "Ministral 8B",
        "hint": "Balanced small model (625K TPM)",
    },
    {
        "id": "ministral-14b-2512",
        "label": "Ministral 14B",
        "hint": "Stronger small model (937K TPM)",
    },
    {
        "id": "devstral-2512",
        "label": "Devstral 2512",
        "hint": "Agentic / coding workflows (1M TPM)",
    },
    {
        "id": "mistral-small-2506",
        "label": "Mistral Small 2506",
        "hint": "General Q&A (2.25M TPM)",
    },
    {
        "id": "mistral-small-2603",
        "label": "Mistral Small 2603",
        "hint": "Latest small general model",
    },
    {
        "id": "open-mistral-nemo",
        "label": "Mistral Nemo",
        "hint": "Open-weights instruct model",
    },
    {
        "id": "magistral-small-2509",
        "label": "Magistral Small",
        "hint": "Reasoning-focused small model",
    },
    {
        "id": "magistral-medium-2509",
        "label": "Magistral Medium",
        "hint": "Reasoning-focused medium model",
    },
    {
        "id": "mistral-medium-2508",
        "label": "Mistral Medium 2508",
        "hint": "Higher quality, moderate rate limits",
    },
    {
        "id": "mistral-medium-2505",
        "label": "Mistral Medium 2505",
        "hint": "Medium general model",
    },
    {
        "id": "mistral-large-2512",
        "label": "Mistral Large 2512",
        "hint": "Best quality — lower free-tier RPS",
    },
    {
        "id": "labs-leanstral-2603",
        "label": "Leanstral 2603 (labs)",
        "hint": "Experimental — very high TPM on free tier",
    },
]

LLM_BACKENDS: list[dict[str, str]] = [
    {"id": "mistral", "label": "Mistral", "default_model": "codestral-2508"},
    {"id": "openai", "label": "OpenAI", "default_model": "gpt-4o-mini"},
    {"id": "anthropic", "label": "Claude (Anthropic)", "default_model": "claude-sonnet-4-20250514"},
    {"id": "gemini", "label": "Gemini (Google)", "default_model": "gemini-2.0-flash"},
    {"id": "openrouter", "label": "OpenRouter", "default_model": "openai/gpt-4o-mini"},
    {"id": "ollama", "label": "Ollama (local)", "default_model": "phi3:mini"},
]

DEFAULT_LLM_BACKEND = "mistral"

DEFAULT_MODELS = {b["id"]: b["default_model"] for b in LLM_BACKENDS}

API_KEY_ENV: dict[str, str] = {
    "mistral": "MISTRAL_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}
