from enum import StrEnum

from pydantic import BaseModel, Field

from backend.app.models.support_ticket import TicketPriority

class ResolutionType(StrEnum):
    TRACK_SHIPMENT = "TRACK_SHIPMENT"
    CONTACT_CARRIER = "CONTACT_CARRIER"
    CONTACT_CUSTOMER = "CONTACT_CUSTOMER"
    ESCALATE = "ESCALATE"
    NO_ACTION = "NO_ACTION"

class DelaySeverity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class AgentEvidence(BaseModel):
    source: str
    page: int | None = None 
    chunk_index: int | None = None 

class AgentDecision(BaseModel):
    severity: DelaySeverity

    resolution: ResolutionType

    reasoning: str = Field(
        description="Short explanation for the decision."
    )

    customer_message: str | None = Field(
        default=None,
        description="Draft customer communication if appropriate."
    )

    requires_human: bool = False

    evidence: list[AgentEvidence] = Field(default_factory=list)


class TicketIntent(StrEnum):
    MISSING_PACKAGE = "MISSING_PACKAGE"
    DELIVERY_DELAY = "DELIVERY_DELAY"
    DAMAGED_ITEM = "DAMAGED_ITEM"
    WRONG_ITEM = "WRONG_ITEM"
    REFUND_REQUEST = "REFUND_REQUEST"
    RETURN_REQUEST = "RETURN_REQUEST"
    GENERAL_INQUIRY = "GENERAL_INQUIRY"

class TicketSentiment(StrEnum):
    POSITIVE = "POSITIVE"
    NEUTRAL = "NEUTRAL"
    NEGATIVE = "NEGATIVE"
    FRUSTRATED = "FRUSTRATED"

class TriageAction(StrEnum):
    AUTO_RESPOND = "AUTO_RESPOND"
    ROUTE_TO_AGENT = "ROUTE_TO_AGENT"
    ESCALATE = "ESCALATE"
    RESOLVE = "RESOLVE"

class TriageDecision(BaseModel):
    intent: TicketIntent
    priority: TicketPriority  # reuse existing enum
    sentiment: TicketSentiment
    action: TriageAction
    reasoning: str
    requires_human: bool = False
    confidence: float = Field(ge=0.0, le=1.0)