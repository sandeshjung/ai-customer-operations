from fastapi import APIRouter
from app.core.config import settings

router = APIRouter(prefix="/health", tags=["Health"])

@router.get("/llm")
def llm_health():
    return {
        "provider": "groq",
        "model": settings.LLM_MODEL,
        "configured": bool(settings.LLM_API_KEY),
    }