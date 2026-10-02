import json

from app.agents.context import DelayedOrderContext
from app.agents.models import AgentDecision
from app.agents.prompts import DELAYED_ORDER_LEGACY_SYSTEM_PROMPT
from app.ai.client import client
from app.core.config import settings


def analyze_delayed_order(
    context: DelayedOrderContext,
) -> AgentDecision:

    response = client.chat.completions.create(
        model=settings.LLM_MODEL,
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": DELAYED_ORDER_LEGACY_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": context.model_dump_json(),
            },
        ],
    )

    content = response.choices[0].message.content

    if not content:
        raise ValueError("LLM returned an empty response")

    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM returned invalid JSON: {content}") from exc

    return AgentDecision.model_validate(data)
