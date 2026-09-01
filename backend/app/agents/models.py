from enum import StrEnum

from pydantic import BaseModel, Field

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