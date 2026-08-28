import json 

from app.agents.context import DelayedOrderContext
from app.agents.models import AgentDecision
from app.ai.client import client
from app.core.config import settings

SYSTEM_PROMPT = """
You are a delayed-order operations agent.

Your job is to analyze delayed e-commerce orders.

You must:

1. Analyze the order information.
2. Analyze shipment information.
3. Consider the number of delayed days.
4. Determine the severity.
5. Recommend the most appropriate resolution.
6. Decide whether human intervention is required.

Do not invent information.

If required information is missing, prefer escalation
or no action.

Return ONLY valid JSON.

The JSON must contain exactly these fields:

{
  "severity": "LOW | MEDIUM | HIGH | CRITICAL",
  "resolution": "TRACK_SHIPMENT | CONTACT_CARRIER | CONTACT_CUSTOMER | ESCALATE | NO_ACTION",
  "reasoning": "short explanation",
  "customer_message": "message or null",
  "requires_human": true
}
"""

def analyze_delayed_order(
    context: DelayedOrderContext,
) -> AgentDecision:

    response = client.chat.completions.create(
        model=settings.LLM_MODEL,
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
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
        raise ValueError(
            f"LLM returned invalid JSON: {content}"
        ) from exc

    return AgentDecision.model_validate(data)