import json

from groq import Groq

from app.agents.models import AgentDecision
from app.ai.base import LLMProvider
from app.core.config import settings

class GroqProvider(LLMProvider):

    def __init__(self):
        self.client = Groq(
            api_key=settings.LLM_API_KEY
        )

    def analyze_delayed_order(self, system_prompt, user_input) -> AgentDecision:
        response = self.client.chat.completions.create(
            model=settings.LLM_MODEL,
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_input
                }
            ]
        )

        content = response.choices[0].message.content

        if not content:
            raise ValueError(
                "LLM returned an empty response."
            )
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "LLM returned invalid JSON"
            ) from exc

        return AgentDecision.model_validate(data)