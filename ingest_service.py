from pathlib import Path

from pypdf import PdfReader

from db import delete_chunks_by_source, upsert_chunks
from settings_service import get_embedding_model

CHUNK_SIZE = 300
CHUNK_OVERLAP = 60
DEFAULT_DOCS_PATH = Path("sample_docs")
# Use settings-managed embedding model when creating chunk items
EMBEDDING_MODEL = get_embedding_model()
EMBEDDING_DIMENSIONS = 384
SUPPORTED_EXTENSIONS = {".md", ".txt", ".pdf", ".json"}


def chunk_text(text, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    chunks = []
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap
    return chunks


def list_available_docs(docs_path: Path = DEFAULT_DOCS_PATH) -> list[Path]:
    if not docs_path.exists():
        return []
    return sorted(
        [
            p
            for p in docs_path.iterdir()
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
        ]
    )


def read_file_text(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        reader = PdfReader(str(file_path))
        parts = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                parts.append(text.strip())
        text = "\n\n".join(parts).strip()
        if not text:
            raise ValueError(f"No extractable text found in PDF: {file_path.name}")
        return text
    return file_path.read_text(encoding="utf-8", errors="ignore")


def build_items_for_file(
    file_path: Path,
    *,
    domain_slug: str | None = None,
    source_slug: str | None = None,
    domain_id: str | None = None,
    source_id: str | None = None,
    rag_profile_id: str | None = None,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> list[dict]:
    text = read_file_text(file_path)
    prefix = file_path.stem
    if domain_slug and source_slug:
        prefix = f"{domain_slug}_{source_slug}_{file_path.stem}"
    items = []
    model = get_embedding_model()
    for i, chunk in enumerate(chunk_text(text, chunk_size, chunk_overlap)):
        items.append(
            {
                "id": f"{prefix}_{i}",
                "source_file": file_path.name,
                "chunk_id": f"chunk_{i:02d}",
                "content": chunk,
                "domain_id": domain_id,
                "source_id": source_id,
                "rag_profile_id": rag_profile_id,
                "embedding_model": model,
            }
        )
    return items


def ingest_files(
    file_paths: list[Path],
    embedder,
    replace_existing: bool = True,
    *,
    domain_id: str | None = None,
    source_id: str | None = None,
    rag_profile_id: str | None = None,
    domain_slug: str | None = None,
    source_slug: str | None = None,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> dict:
    report = {
        "files": [],
        "total_chunks": 0,
        "deleted_chunks": 0,
        "errors": [],
    }

    for file_path in file_paths:
        try:
            deleted = 0
            if replace_existing:
                deleted = delete_chunks_by_source(
                    file_path.name,
                    source_id=source_id,
                    domain_id=domain_id,
                )

            items = build_items_for_file(
                file_path,
                domain_slug=domain_slug,
                source_slug=source_slug,
                domain_id=domain_id,
                source_id=source_id,
                rag_profile_id=rag_profile_id,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
            count = upsert_chunks(items, embedder)
            total_chars = sum(len(item["content"]) for item in items)

            report["files"].append(
                {
                    "source_file": file_path.name,
                    "chunks_ingested": count,
                    "chunks_deleted": deleted,
                    "total_chars": total_chars,
                    "file_size_bytes": file_path.stat().st_size,
                    "status": "success",
                }
            )
            report["total_chunks"] += count
            report["deleted_chunks"] += deleted
        except Exception as exc:
            report["errors"].append(
                {
                    "source_file": file_path.name,
                    "error": str(exc),
                    "status": "failed",
                }
            )

    return report


def get_chunking_info() -> dict:
    return {
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "embedding_model": EMBEDDING_MODEL,
        "embedding_dimensions": EMBEDDING_DIMENSIONS,
        "supported_extensions": ", ".join(sorted(SUPPORTED_EXTENSIONS)),
        "chunk_id_format": "chunk_00, chunk_01, ...",
        "row_id_format": "{domain_slug}_{source_slug}_{filename_stem}_{index}",
    }
