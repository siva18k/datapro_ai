from sentence_transformers import SentenceTransformer

from ingest_service import DEFAULT_DOCS_PATH, ingest_files, list_available_docs

if __name__ == "__main__":
    embedder = SentenceTransformer("all-MiniLM-L6-v2")
    files = list_available_docs(DEFAULT_DOCS_PATH)
    report = ingest_files(files, embedder, replace_existing=True)
    print(f"Ingested {report['total_chunks']} chunks into Postgres.")
    if report["errors"]:
        for err in report["errors"]:
            print(f"ERROR {err['source_file']}: {err['error']}")
