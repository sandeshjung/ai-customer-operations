import json
import logging
import re
import time

from langchain_core.messages import SystemMessage
from langgraph.graph import END, START, StateGraph
from langchain_groq import ChatGroq

from app.agents.models import TriageDecision
from app.core.config import settings
from app.core.tracing import current_trace_id, traced

logger = logging.getLogger(__name__)

llm = ChatGroq(
    model=settings.LLM_MODEL,
    api_key=settings.LLM_API_KEY,
    temperature=0,
)


class TriageState(dict):
    ticket_id: int
    ticket: dict
    customer_history: list[dict]
    policy_context: str
    decision: TriageDecision | None


SYSTEM_PROMPT = """
You are a support ticket triage agent.

Analyze the ticket and determine:
1. Intent (what is the customer asking about?)
2. Priority (should this be LOW, MEDIUM, HIGH, CRITICAL?)
3. Sentiment (how is the customer feeling?)
4. Action (what should we do?)
5. Whether human intervention is required

Use the provided policy context to ground your decisions.
Never invent policy rules.

You MUST output ONLY valid JSON. No markdown. No explanations. Start with { and end with }.
"""


def triage_node(state: TriageState):
    ticket = state["ticket"]
    history = state.get("customer_history", [])

    prompt = f"""
TICKET:
Subject: {ticket['subject']}
Message: {ticket['message']}
Current Priority: {ticket['priority']}

CUSTOMER HISTORY:
{json.dumps(history, indent=2)[:800]}

POLICY CONTEXT:
{state.get('policy_context', 'No policy retrieved')}

Return JSON:
{{
  "intent": "MISSING_PACKAGE | DELIVERY_DELAY | DAMAGED_ITEM | WRONG_ITEM | REFUND_REQUEST | RETURN_REQUEST | GENERAL_INQUIRY",
  "priority": "LOW | MEDIUM | HIGH | CRITICAL",
  "sentiment": "POSITIVE | NEUTRAL | NEGATIVE | FRUSTRATED",
  "action": "AUTO_RESPOND | ROUTE_TO_AGENT | ESCALATE | RESOLVE",
  "reasoning": "short explanation",
  "requires_human": boolean,
  "confidence": 0.0 to 1.0
}}
"""

    start_time = time.perf_counter()
    with traced(
        "llm.triage",
        tracer_name="triage_agent",
        ticket_id=state["ticket_id"],
        model=settings.LLM_MODEL,
    ) as span:
        response = llm.invoke([
            SystemMessage(content=SYSTEM_PROMPT),
            SystemMessage(content=prompt),
        ])
        usage = getattr(response, "usage_metadata", None)
        if usage:
            span.set_attribute("llm.input_tokens", usage.get("input_tokens", 0))
            span.set_attribute("llm.output_tokens", usage.get("output_tokens", 0))
            span.set_attribute("llm.total_tokens", usage.get("total_tokens", 0))
    latency_ms = (time.perf_counter() - start_time) * 1000

    content = response.content.strip()

    # Extract JSON from markdown code blocks if present
    if content.startswith("```"):
        lines = content.splitlines()
        # Remove opening fence
        if lines[0].startswith("```"):
            lines = lines[1:]
        # Remove closing fence
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        content = "\n".join(lines).strip()

    # Fallback: extract first JSON object via regex
    try:
        decision_data = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if not match:
            logger.error(
                "No JSON found in triage response | content=%s",
                content[:500],
            )
            raise ValueError(f"Triage response is not valid JSON: {content[:500]}")
        decision_data = json.loads(match.group())

    decision = TriageDecision.model_validate(decision_data)
    decision.trace_id = current_trace_id()

    logger.info(
        "Triage decision | ticket_id=%s | intent=%s | priority=%s | action=%s | latency_ms=%.2f | trace_id=%s",
        state["ticket_id"],
        decision.intent,
        decision.priority,
        decision.action,
        latency_ms,
        decision.trace_id,
    )

    return {"decision": decision}


def build_triage_graph():
    builder = StateGraph(TriageState)
    builder.add_node("triage", triage_node)
    builder.add_edge(START, "triage")
    builder.add_edge("triage", END)
    return builder.compile()

triage_graph = build_triage_graph()