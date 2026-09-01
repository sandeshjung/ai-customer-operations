from pathlib import Path
from pypdf import PdfReader

KNOWLEDGE_DIR = Path("data/knowledge")

def load_documents() -> list[dict]:
    documents = []

    for path in KNOWLEDGE_DIR.glob("*.pdf"):
        reader = PdfReader(str(path))
        pages = []
        for page_number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                pages.append({"page": page_number, "text": text})

        documents.append({          # ← moved outside the page loop
            "source": path.name,
            "document_type": "policy",
            "pages": pages
        })

    return documents