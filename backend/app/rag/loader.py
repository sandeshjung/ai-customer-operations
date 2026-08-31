from pathlib import Path

KNOWLEDGE_DIR = Path("data/knowledge")

def load_documents() -> list[dict]:
    documents = []

    for path in KNOWLEDGE_DIR.glob("*.txt"):
        text = path.read_text(encoding="utf-8")

        documents.append(
            {
                "text": text,
                "source": path.name
            }
        )

    return documents