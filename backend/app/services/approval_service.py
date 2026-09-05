from datetime import datetime

from sqlalchemy.orm import Session

from app.agents.models import AgentDecision
from app.core.logging import get_logger
from app.models.human_approval import ApprovalStatus, HumanApproval
from app.services.action_service import execute_decision

logger = get_logger(__name__)

def create_approval(
        db: Session,
        event_id: str,
        order_id: int,
        customer_id: int,
        agent_name: str,
        decision: AgentDecision
) -> HumanApproval:
    approval = HumanApproval(
        event_id=event_id,
        order_id=order_id,
        customer_id=customer_id,
        agent_name=agent_name,
        decision=decision.model_dump(),
        status=ApprovalStatus.PENDING
    )
    db.add(approval)
    db.commit()
    db.refresh(approval)

    logger.info(
        "Human approval requested",
        extra={
            "approval_id": approval.id,
            "event_id": event_id,
            "order_id": order_id,
            "severity": decision.severity
        }
    )
    return approval

def get_pending_approvals(db: Session, limit: int = 50) -> list[HumanApproval]:
    return (
        db.query(HumanApproval)
        .filter(HumanApproval.status == ApprovalStatus.PENDING)
        .order_by(HumanApproval.created_at.desc())
        .limit(limit)
        .all()
    )

def approve(db: Session, approval_id: int, reviewer: str, notes: str | None = None) -> tuple[HumanApproval, dict]:
    approval = db.get(HumanApproval, approval_id)
    if not approval:
        raise ValueError("Approval not found")

    if approval.status != ApprovalStatus.PENDING:
        raise ValueError(f"Approval already {approval.status}")

    approval.status = ApprovalStatus.APPROVED
    approval.reviewed_by = reviewer
    approval.reviewed_at = datetime.utcnow()
    approval.reviewer_notes = notes

    # reconstruct decision and execute
    decision = AgentDecision.model_validate(approval.decision)
    result = execute_decision(
        db=db,
        order_id=approval.order_id,
        customer_id=approval.customer_id,
        decision=decision
    )

    db.commit()

    logger.info(
        "Approval granted and executed",
        extra={
            "approval_id": approval_id,
            "reviewer": reviewer,
            "ticket_id": result.get("ticket_id")
        }
    )
    return approval, result

def reject(db: Session, approval_id: int, reviewer: str, notes: str | None = None) -> HumanApproval:
    approval = db.get(HumanApproval, approval_id)
    if not approval:
        raise ValueError("Approval not found")

    approval.status = ApprovalStatus.REJECTED
    approval.reviewed_by = reviewer
    approval.reviewed_at = datetime.utcnow()
    approval.reviewer_notes = notes
    db.commit()

    logger.info(
        "Approval rejected",
        extra={
            "approval_id": approval_id,
            "reviewer": reviewer
        }
    )