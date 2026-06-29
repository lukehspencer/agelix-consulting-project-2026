import argparse
from pathlib import Path

from rag.knowledge_base import build_knowledge_base

_BASE_DIR = Path(__file__).parent.parent
_DIRS = [
    _BASE_DIR / "docs" / "manuals",
    _BASE_DIR / "docs" / "failure_cases",
    Path(__file__).parent / "stored_configs",
]


def main():
    parser = argparse.ArgumentParser(description="Build RAG knowledge base")
    parser.add_argument("--rebuild", action="store_true", help="Force full rebuild")
    args = parser.parse_args()

    for d in _DIRS:
        d.mkdir(parents=True, exist_ok=True)
        gitkeep = d / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.touch()

    chroma_dir = Path(__file__).parent / "chroma_db"
    chroma_dir.mkdir(parents=True, exist_ok=True)

    has_content = False
    for d in _DIRS:
        real_files = [f for f in d.iterdir() if f.name != ".gitkeep"]
        if real_files:
            has_content = True
            break

    if not has_content:
        print("Source directories are empty:")
        print(f"  - docs/manuals/        (place PDF manuals here)")
        print(f"  - docs/failure_cases/  (place failure case .md files here)")
        print(f"  - rag/stored_configs/  (CriteriaConfigs are saved here automatically)")
        print("Knowledge base will be populated as documents are added.")

    count = build_knowledge_base(force_rebuild=args.rebuild)
    print(f"Knowledge base ready. Total documents indexed: {count}")


if __name__ == "__main__":
    main()
