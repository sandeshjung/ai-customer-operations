import re

from app.agents.models import (
    AgentDecision,
    DelaySeverity,
    ResolutionType,
    TriageDecision,
)


def validate_decision(decision: AgentDecision) -> AgentDecision:

    if decision.severity == DelaySeverity.CRITICAL:
        decision.requires_human = True

    if decision.resolution == ResolutionType.ESCALATE:
        decision.requires_human = True

    return decision


# Phrases that try to talk to the model rather than describe a problem.
# Deliberately broad: a false positive only routes a ticket to a person.
_INJECTION_PATTERNS = re.compile(
    r"ignore\s+(all\s+|any\s+)?(the\s+)?(previous|prior|above|earlier)\s+"
    r"(instructions|prompts?|rules)"
    r"|disregard\s+(all\s+|the\s+)?(previous|prior|above|earlier|system)"
    r"|system\s*(override|prompt|message)"
    r"|you\s+are\s+now\b"
    r"|admin(istrator)?\s+mode"
    r"|respond\s+only\s+with"
    r"|requires_human\s*[:=]?\s*false"
    r"|<\s*/?\s*customer_(content|history)\s*>",
    re.IGNORECASE,
)


def looks_like_prompt_injection(*texts: str) -> bool:
    return any(_INJECTION_PATTERNS.search(text or "") for text in texts)


def validate_triage_decision(
    decision: TriageDecision, subject: str, message: str
) -> TriageDecision:
    """Code-level backstop for the triage agent, like validate_decision for
    the delayed-order agent: if the ticket text looks like an injection
    attempt, a human must review it — whatever the model decided — so a
    fooled model can't auto-resolve (close) the ticket."""
    if looks_like_prompt_injection(subject, message):
        decision.requires_human = True
    return decision
