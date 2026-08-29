from app.agents.models import (
    AgentDecision,
    DelaySeverity,
    ResolutionType
)

def validate_decision(
        decision: AgentDecision
) -> AgentDecision:

    if decision.severity == DelaySeverity.CRITICAL:
        decision.requires_human = True

    if (
        decision.resolution == ResolutionType.ESCALATE
    ):
        decision.requires_human = True

    return decision