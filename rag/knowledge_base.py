import json
from pathlib import Path

import chromadb
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

from rag.document_loader import load_all_documents

_CHROMA_DIR = Path(__file__).parent / "chroma_db"
_CONFIGS_DIR = Path(__file__).parent / "stored_configs"
_COLLECTION_NAME = "asset_knowledge"


def _get_embedding_fn():
    return DefaultEmbeddingFunction()


def build_knowledge_base(force_rebuild: bool = False) -> int:
    if force_rebuild and _CHROMA_DIR.exists():
        import shutil
        shutil.rmtree(_CHROMA_DIR)

    _CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(_CHROMA_DIR))
    collection = client.get_or_create_collection(
        name=_COLLECTION_NAME,
        embedding_function=_get_embedding_fn(),
    )

    docs = load_all_documents()
    if not docs:
        return 0

    existing_ids = set(collection.get()["ids"]) if collection.count() > 0 else set()

    new_docs = []
    for doc in docs:
        doc_id = f"{doc['source']}::page={doc['page']}"
        if doc_id not in existing_ids:
            new_docs.append((doc_id, doc))

    if not new_docs:
        return collection.count()

    batch_ids = [d[0] for d in new_docs]
    batch_contents = [d[1]["content"] for d in new_docs]
    batch_metadata = [
        {"source": d[1]["source"], "page": d[1]["page"], "doc_type": d[1]["doc_type"]}
        for d in new_docs
    ]

    collection.add(ids=batch_ids, documents=batch_contents, metadatas=batch_metadata)
    return collection.count()


def query(query_text: str, n_results: int = 5, doc_type: str = None) -> list[str]:
    if not _CHROMA_DIR.exists():
        raise RuntimeError(
            "Knowledge base not found at rag/chroma_db/. "
            "Run 'python -m rag.ingest' to build it."
        )

    client = chromadb.PersistentClient(path=str(_CHROMA_DIR))
    try:
        collection = client.get_collection(
            name=_COLLECTION_NAME,
            embedding_function=_get_embedding_fn(),
        )
    except ValueError:
        raise RuntimeError(
            "Knowledge base collection not found. "
            "Run 'python -m rag.ingest' to build it."
        )

    where_filter = {"doc_type": doc_type} if doc_type else None
    results = collection.query(
        query_texts=[query_text],
        n_results=n_results,
        where=where_filter,
    )

    return results["documents"][0] if results["documents"] else []


def store_criteria_config(criteria_config: dict, asset_type: str) -> Path:
    _CONFIGS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = asset_type.lower().replace(" ", "_").replace("/", "_")
    config_path = _CONFIGS_DIR / f"{safe_name}.json"
    config_path.write_text(json.dumps(criteria_config, indent=2), encoding="utf-8")
    build_knowledge_base()
    return config_path
