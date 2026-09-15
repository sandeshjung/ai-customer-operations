from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.agents.models import AgentDecision
from app.core.logging import get_logger
from app.core.tracing import link_from_carrier, traced
from app.models.human_approval import ApprovalStatus, HumanApproval
from app.services.action_service import execute_decision

logger = get_logger(__name__)


def create_approval(
    db: Session,
    event_id: str,
    order_id: int,
    customer_id: int,
    agent_name: str,
    decision: AgentDecision,
) -> HumanApproval:
    approval = HumanApproval(
        event_id=event_id,
        order_id=order_id,
        customer_id=customer_id,
        agent_name=agent_name,
        decision=decision.model_dump(),
        status=ApprovalStatus.PENDING,
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
            "severity": decision.severity,
        },
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


def _claim_approval(
    db: Session, approval_id: int, new_status: str, reviewer: str, notes: str | None
) -> HumanApproval:
    """Atomically transition an approval out of PENDING, or raise.

    Two people (or a double-click, or a retried request) hitting approve/
    reject on the same approval at the same time is a real race with a
    plain read-then-write: both could read status=PENDING before either
    writes, and both proceed — e.g. both approve, both create a ticket.

    UPDATE ... WHERE status = 'PENDING' is a single atomic statement at
    the database level: only one concurrent caller can ever match the
    WHERE clause and flip the row, because the DB serializes concurrent
    writes to the same row. Whoever's UPDATE affects 0 rows lost the
    race and gets a clear error instead of silently duplicating the
    action.
    """
    result = db.execute(
        update(HumanApproval)
        .where(
            HumanApproval.id == approval_id,
            HumanApproval.status == ApprovalStatus.PENDING.value,
        )
        .values(
            status=new_status.value,
            reviewed_by=reviewer,
            reviewed_at=datetime.now(timezone.utc),
            reviewer_notes=notes,
        )
    )
    rowcount = result.rowcount
    result.close()
    db.commit()

    if rowcount == 0:
        existing = db.get(HumanApproval, approval_id)
        if existing is None:
            raise ValueError("Approval not found")
        raise ValueError(f"Approval already {existing.status}")

    # expire on commit means this re-fetches fresh from the db rather than returning a stale in-memory copy.
    return db.get(HumanApproval, approval_id)


def approve(
    db: Session, approval_id: int, reviewer: str, notes: str | None = None
) -> tuple[HumanApproval, dict]:
    approval = _claim_approval(
        db, approval_id, ApprovalStatus.APPROVED, reviewer, notes
    )

    # reconstruct decision and execute
    decision = AgentDecision.model_validate(approval.decision)

    # The original investigation's trace is long finished by the time a
    # human gets to this — Link to it rather than trying to parent under
    # a span that no longer exists.
    original_trace_link = link_from_carrier(decision.trace_context)

    with traced(
        "human_approval.execute",
        tracer_name="approval_service",
        links=[original_trace_link] if original_trace_link else None,
        approval_id=approval_id,
        reviewer=reviewer,
        original_trace_id=decision.trace_id,
    ):
        result = execute_decision(
            db=db,
            order_id=approval.order_id,
            customer_id=approval.customer_id,
            decision=decision,
        )

    db.commit()

    logger.info(
        "Approval granted and executed",
        extra={
            "approval_id": approval_id,
            "reviewer": reviewer,
            "ticket_id": result.get("ticket_id"),
            "actions": result.get("actions"),
            "severity": decision.severity,
            "resolution": decision.resolution,
            "reasoning": decision.reasoning,
            "requires_human": decision.requires_human,
            "trace_id": decision.trace_id,
        },
    )
    return approval, result


def reject(
    db: Session, approval_id: int, reviewer: str, notes: str | None = None
) -> HumanApproval:
    approval = _claim_approval(
        db, approval_id, ApprovalStatus.REJECTED, reviewer, notes
    )

    decision = AgentDecision.model_validate(approval.decision)

    logger.info(
        "Approval rejected",
        extra={
            "approval_id": approval_id,
            "reviewer": reviewer,
            "notes": notes,
            "severity": decision.severity,
            "resolution": decision.resolution,
            "reasoning": decision.reasoning,
            "requires_human": decision.requires_human,
            "trace_id": decision.trace_id,
        },
    )

    return approval
