from app.core.config import settings
from groq import Groq

client = Groq(api_key=settings.LLM_API_KEY)
