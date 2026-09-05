import json 
import logging
import time
from langchain_core.messages import SystemMessage
from langgraph.graph import END, START, StateGraph
from langchain_groq import ChatGroq

from app.agents.models import TriageDecision
from app.core.config import settings
from app.rag.service import retrieve_policy

logger = logging.getLogger(__name__)
llm = ChatGroq(model=settings.LLM_MODEL, api_key=settings.LLM_API_KEY, temperature=0)

class TriageState(dict):
    ticket_id:int
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

Use search_policy to retrieve relevant company policies.
Never invent policy rules.

Return ONLY valid JSON matching the required schema.
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
    {json.dumps(history, indent=2)[:1000]}

    POLICY CONTEXT:
    {state.get('policy_context', 'No policy retrieved')}

    Analyze and return JSON:
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

    structured_llm = llm.with_structured_output(TriageDecision)
    decision = structured_llm.invoke(
        [
            SystemMessage(content=SYSTEM_PROMPT),
            SystemMessage(content=prompt)
        ]
    )
    logger.info(
        "Triage decision | ticket_id=%s | intent=%s | priority=%s | action=%s",
        state["ticket_id"], decision.intent, decision.priority, decision.action,
    )
    return {"decision": decision}

def build_triage_graph():
    builder = StateGraph(TriageState)
    builder.add_node("triage", triage_node)
    builder.add_edge(START, "triage")
    builder.add_edge("triage", END)
    return builder.compile()

triage_graph = build_triage_graph()