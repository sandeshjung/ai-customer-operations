from groq import Groq

from app.core.config import settings

client = Groq(
    api_key=settings.LLM_API_KEY
)