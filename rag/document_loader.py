import json
from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

_BASE_DIR = Path(__file__).parent.parent
_MANUALS_DIR = _BASE_DIR / "docs" / "manuals"
_FAILURE_CASES_DIR = _BASE_DIR / "docs" / "failure_cases"
_CONFIGS_DIR = Path(__file__).parent / "stored_configs"

_PDF_SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=500, chunk_overlap=50,
)
_MD_SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=300, chunk_overlap=30,
)


def _load_pdfs() -> list[dict]:
    chunks = []
    if not _MANUALS_DIR.exists():
        return chunks
    for pdf_path in sorted(_MANUALS_DIR.glob("*.pdf")):
        try:
            loader = PyPDFLoader(str(pdf_path))
            pages = loader.load()
            splits = _PDF_SPLITTER.split_documents(pages)
            for doc in splits:
                chunks.append({
                    "content": doc.page_content,
                    "source": str(pdf_path.relative_to(_BASE_DIR)),
                    "page": doc.metadata.get("page", 0),
                    "doc_type": "manual",
                })
        except Exception:
            continue
    return chunks


def _load_markdown() -> list[dict]:
    chunks = []
    if not _FAILURE_CASES_DIR.exists():
        return chunks
    for md_path in sorted(_FAILURE_CASES_DIR.glob("*.md")):
        try:
            text = md_path.read_text(encoding="utf-8")
            splits = _MD_SPLITTER.split_text(text)
            for i, chunk in enumerate(splits):
                chunks.append({
                    "content": chunk,
                    "source": str(md_path.relative_to(_BASE_DIR)),
                    "page": i,
                    "doc_type": "failure_case",
                })
        except Exception:
            continue
    return chunks


def _load_configs() -> list[dict]:
    chunks = []
    if not _CONFIGS_DIR.exists():
        return chunks
    for json_path in sorted(_CONFIGS_DIR.glob("*.json")):
        try:
            config = json.loads(json_path.read_text(encoding="utf-8"))
            content = json.dumps(config, indent=2)
            chunks.append({
                "content": content,
                "source": str(json_path.relative_to(_BASE_DIR)),
                "page": 0,
                "doc_type": "criteria_config",
            })
        except Exception:
            continue
    return chunks


def load_all_documents() -> list[dict]:
    return _load_pdfs() + _load_markdown() + _load_configs()
