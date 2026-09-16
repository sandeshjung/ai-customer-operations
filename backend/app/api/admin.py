from app.core.database import get_db
from app.core.pricing import estimate_cost_usd
from app.core.security import require_api_key
from app.models.agent_execution import AgentExecution
from app.models.customer import Customer
from app.models.notification import Notification
from app.services.approval_service import approve, get_pending_approvals, reject
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

router = APIRouter(
    prefix="/admin", tags=["Admin"], dependencies=[Depends(require_api_key)]
)


class ApprovalReview(BaseModel):
    reviewer: str
    notes: str | None = None


@router.get("/approvals/pending")
def list_pending_approvals(db: Session = Depends(get_db)):
    approvals = get_pending_approvals(db)

    customer_ids = {approval.customer_id for approval in approvals}
    emails_by_customer_id = {
        customer.id: customer.email
        for customer in db.query(Customer).filter(Customer.id.in_(customer_ids))
    }

    return [
        {
            "id": approval.id,
            "event_id": approval.event_id,
            "order_id": approval.order_id,
            "customer_id": approval.customer_id,
            "customer_email": emails_by_customer_id.get(approval.customer_id),
            "agent_name": approval.agent_name,
            "decision": approval.decision,
            "created_at": approval.created_at,
        }
        for approval in approvals
    ]


@router.get("/notifications")
def list_notifications(limit: int = 50, db: Session = Depends(get_db)):
    notifications = (
        db.query(Notification)
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "id": notification.id,
            "customer_id": notification.customer_id,
            "order_id": notification.order_id,
            "channel": notification.channel,
            "recipient": notification.recipient,
            "subject": notification.subject,
            "content": notification.content,
            "status": notification.status,
            "error": notification.error,
            "created_at": notification.created_at,
        }
        for notification in notifications
    ]


@router.post("/approvals/{approval_id}/approve")
def approve_approval(
    approval_id: int, review: ApprovalReview, db: Session = Depends(get_db)
):
    try:
        approval, result = approve(db, approval_id, review.reviewer, review.notes)
        return {
            "status": "approved",
            "approval_id": approval.id,
            "ticket_id": result.get("ticket_id"),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/approvals/{approval_id}/reject")
def reject_approval(
    approval_id: int, review: ApprovalReview, db: Session = Depends(get_db)
):
    try:
        approval = reject(db, approval_id, review.reviewer, review.notes)
        return {"status": "rejected", "approval_id": approval.id}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/usage")
def get_usage(limit: int = 100, db: Session = Depends(get_db)):
    """AI usage/cost monitor: token counts and estimated spend per agent run,
    aggregated from AgentExecution rows (populated by agent_service.py and
    triage_service.py from each LLM call's usage_metadata)."""

    # Grouped by (agent_name, model) rather than just agent_name, since cost
    # is priced per model and a deployment may switch LLM_MODEL over time.
    grouped = (
        db.query(
            AgentExecution.agent_name,
            AgentExecution.model,
            func.count(AgentExecution.id).label("executions"),
            func.sum(AgentExecution.input_tokens).label("input_tokens"),
            func.sum(AgentExecution.output_tokens).label("output_tokens"),
            func.sum(AgentExecution.total_tokens).label("total_tokens"),
            func.sum(AgentExecution.llm_call_count).label("llm_calls"),
            func.avg(AgentExecution.duration_ms).label("avg_duration_ms"),
        )
        .group_by(AgentExecution.agent_name, AgentExecution.model)
        .all()
    )

    by_agent = []
    cost_incomplete = False
    for row in grouped:
        cost = estimate_cost_usd(
            row.model, row.input_tokens or 0, row.output_tokens or 0
        )
        if cost is None and (row.input_tokens or row.output_tokens):
            cost_incomplete = True
        by_agent.append(
            {
                "agent_name": row.agent_name,
                "model": row.model,
                "executions": row.executions,
                "input_tokens": row.input_tokens or 0,
                "output_tokens": row.output_tokens or 0,
                "total_tokens": row.total_tokens or 0,
                "llm_calls": row.llm_calls or 0,
                "avg_duration_ms": float(row.avg_duration_ms)
                if row.avg_duration_ms is not None
                else None,
                "cost_usd": cost,
            }
        )

    summary = {
        "total_executions": sum(g["executions"] for g in by_agent),
        "total_input_tokens": sum(g["input_tokens"] for g in by_agent),
        "total_output_tokens": sum(g["output_tokens"] for g in by_agent),
        "total_tokens": sum(g["total_tokens"] for g in by_agent),
        "total_llm_calls": sum(g["llm_calls"] for g in by_agent),
        "total_cost_usd": sum(
            g["cost_usd"] for g in by_agent if g["cost_usd"] is not None
        )
        if by_agent
        else 0.0,
        "cost_incomplete": cost_incomplete,
    }

    recent = (
        db.query(AgentExecution)
        .order_by(AgentExecution.created_at.desc())
        .limit(limit)
        .all()
    )

    return {
        "summary": summary,
        "by_agent": by_agent,
        "recent": [
            {
                "id": execution.id,
                "agent_name": execution.agent_name,
                "event_id": execution.event_id,
                "model": execution.model,
                "input_tokens": execution.input_tokens,
                "output_tokens": execution.output_tokens,
                "total_tokens": execution.total_tokens,
                "llm_call_count": execution.llm_call_count,
                "duration_ms": execution.duration_ms,
                "cost_usd": estimate_cost_usd(
                    execution.model, execution.input_tokens, execution.output_tokens
                ),
                "trace_id": (execution.decision or {}).get("trace_id"),
                "created_at": execution.created_at,
            }
            for execution in recent
        ],
    }
