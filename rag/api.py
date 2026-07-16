import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from rag import knowledge_base

router = APIRouter(prefix="/rag", tags=["rag"])

_BASE_DIR = Path(__file__).parent.parent
_MANUALS_DIR = _BASE_DIR / "docs" / "manuals"
_FAILURE_CASES_DIR = _BASE_DIR / "docs" / "failure_cases"
_CONFIGS_DIR = Path(__file__).parent / "stored_configs"

_CONFIG_TIMESTAMP_RE = re.compile(r"_(\d{8}_\d{6})\.json$")


def _config_timestamp(filename: str) -> str:
    match = _CONFIG_TIMESTAMP_RE.search(filename)
    return match.group(1) if match else ""


@router.post("/upload-document")
async def upload_document(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="Only PDF files are accepted.")

    _MANUALS_DIR.mkdir(parents=True, exist_ok=True)
    dest = _MANUALS_DIR / file.filename

    try:
        content = await file.read()
        dest.write_bytes(content)
        knowledge_base.build_knowledge_base(force_rebuild=False)
    except Exception as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(e))

    return {
        "filename": file.filename,
        "status": "ingested",
        "message": f"'{file.filename}' ingested and added to knowledge base.",
    }


@router.get("/documents")
def list_documents():
    manuals = sorted(p.name for p in _MANUALS_DIR.glob("*.pdf")) if _MANUALS_DIR.exists() else []
    failure_cases = sorted(p.name for p in _FAILURE_CASES_DIR.glob("*.md")) if _FAILURE_CASES_DIR.exists() else []

    config_paths = list(_CONFIGS_DIR.glob("*.json")) if _CONFIGS_DIR.exists() else []
    config_paths.sort(key=lambda p: _config_timestamp(p.name), reverse=True)
    criteria_configs = [p.name for p in config_paths]

    latest_per_asset_type = {}
    for p in config_paths:
        try:
            asset_type = json.loads(p.read_text(encoding="utf-8")).get("asset_type")
        except Exception:
            asset_type = None
        if asset_type and asset_type not in latest_per_asset_type:
            latest_per_asset_type[asset_type] = p.name

    return {
        "manuals": manuals,
        "failure_cases": failure_cases,
        "criteria_configs": criteria_configs,
        "latest_per_asset_type": latest_per_asset_type,
    }


class DeleteRequest(BaseModel):
    filename: str
    doc_type: str


@router.delete("/document")
def delete_document(body: DeleteRequest):
    if body.doc_type == "manual":
        target = _MANUALS_DIR / body.filename
    elif body.doc_type == "failure_case":
        target = _FAILURE_CASES_DIR / body.filename
    elif body.doc_type == "criteria_config":
        target = _CONFIGS_DIR / body.filename
    else:
        raise HTTPException(status_code=422, detail=f"Unknown doc_type: {body.doc_type!r}")

    if not target.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {body.filename}")

    target.unlink()
    knowledge_base.build_knowledge_base(force_rebuild=True)
    return {"filename": body.filename, "status": "deleted"}
