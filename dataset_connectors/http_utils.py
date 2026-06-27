from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

from ingest_service import SUPPORTED_EXTENSIONS


def build_request_headers(config: dict) -> dict[str, str]:
    headers = {"User-Agent": "DATA-Pro-DatasetConnector/1.0"}
    raw = config.get("headers")
    if isinstance(raw, dict):
        headers.update({str(k): str(v) for k, v in raw.items()})
    token = (config.get("auth_token") or "").strip()
    if token and "Authorization" not in headers:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_url(url: str, *, headers: dict[str, str] | None = None, timeout: int = 45) -> tuple[bytes, str]:
    try:
        response = requests.get(url, headers=headers or {}, timeout=timeout, allow_redirects=True)
        response.raise_for_status()
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "?"
        reason = exc.response.reason if exc.response is not None else str(exc)
        raise ValueError(f"HTTP {status} {reason} — {url}") from exc
    except requests.RequestException as exc:
        raise ValueError(f"Cannot reach {url}: {exc}") from exc
    return response.content, response.headers.get("content-type", "")


def strip_html(text: str) -> str:
    text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def safe_asset_filename(asset_id: str, suffix: str) -> str:
    stem = re.sub(r"[^\w.\-]+", "_", asset_id.strip()).strip("._") or "asset"
    if not suffix.startswith("."):
        suffix = f".{suffix}"
    return f"{stem}{suffix}"


def pick_extension(content: bytes, content_type: str, url: str) -> str:
    lowered = content_type.lower()
    path_suffix = Path(urlparse(url).path).suffix.lower()
    if "pdf" in lowered or path_suffix == ".pdf":
        return ".pdf"
    if "json" in lowered or path_suffix == ".json":
        return ".json"
    if path_suffix in SUPPORTED_EXTENSIONS:
        return path_suffix
    if content[:5] == b"%PDF-":
        return ".pdf"
    try:
        json.loads(content.decode("utf-8"))
        return ".json"
    except (UnicodeDecodeError, json.JSONDecodeError):
        pass
    if b"<html" in content[:500].lower() or "html" in lowered:
        return ".txt"
    return ".txt"


def materialize_bytes(dest_dir: Path, asset_id: str, url: str, content: bytes, content_type: str) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    ext = pick_extension(content, content_type, url)
    if ext == ".txt" and (b"<html" in content[:500].lower() or "html" in content_type.lower()):
        text = strip_html(content.decode("utf-8", errors="ignore"))
        target = dest_dir / safe_asset_filename(asset_id, ext)
        target.write_text(text, encoding="utf-8")
        return target
    if ext == ".json":
        try:
            parsed = json.loads(content.decode("utf-8"))
            pretty = json.dumps(parsed, indent=2, ensure_ascii=False)
            target = dest_dir / safe_asset_filename(asset_id, ext)
            target.write_text(pretty + "\n", encoding="utf-8")
            return target
        except (UnicodeDecodeError, json.JSONDecodeError):
            ext = ".txt"
    target = dest_dir / safe_asset_filename(asset_id, ext)
    if ext in {".txt", ".md"}:
        target.write_text(content.decode("utf-8", errors="ignore"), encoding="utf-8")
    else:
        target.write_bytes(content)
    return target


def configured_urls(config: dict) -> list[tuple[str, str]]:
    """Return (asset_id, url) pairs from config."""
    urls: list[tuple[str, str]] = []
    primary = (config.get("url") or "").strip()
    if primary:
        urls.append(("primary", primary))
    extra = config.get("urls") or []
    if isinstance(extra, str):
        extra = [part.strip() for part in extra.split(",") if part.strip()]
    if isinstance(extra, list):
        for idx, item in enumerate(extra):
            if isinstance(item, str) and item.strip():
                urls.append((f"url_{idx + 1}", item.strip()))
    seen: set[str] = set()
    deduped: list[tuple[str, str]] = []
    for asset_id, url in urls:
        if url in seen:
            continue
        seen.add(url)
        deduped.append((asset_id, url))
    return deduped


def configured_api_endpoints(config: dict) -> list[tuple[str, str]]:
    base = (config.get("base_url") or "").strip().rstrip("/")
    if not base:
        return []
    endpoints = config.get("endpoints") or [""]
    if isinstance(endpoints, str):
        endpoints = [part.strip() for part in endpoints.split(",")]
    pairs: list[tuple[str, str]] = []
    for idx, endpoint in enumerate(endpoints):
        path = str(endpoint or "").strip()
        asset_id = path.strip("/").replace("/", "_") or "root"
        if not asset_id or asset_id == "root":
            asset_id = "root" if idx == 0 else f"endpoint_{idx + 1}"
        url = base if not path else urljoin(f"{base}/", path.lstrip("/"))
        pairs.append((asset_id, url))
    return pairs
