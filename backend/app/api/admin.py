from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.approval_service import approve, get_pending_approvals, reject

router = APIRouter(prefix="/admin", tags=["Admin"])

class ApprovalReview(BaseModel):
    reviewer: str
    notes: str | None = None

@router.get("/approvals/pending")
def list_pending_approvals(db: Session = Depends(get_db)):
    approvals = get_pending_approvals(db)
    return [
        {
            "id": approval.id,
            "event_id": approval.event_id,
            "order_id": approval.customer_id,
            "customer_id": approval.agent_name,
            "agent_name": approval.decision,
            "decision": approval.decision,
            "created_at": approval.created_at
        }
        for approval in approvals
    ]

@router.post("/approvals/{approval_id}/approve")
def approve_approval(approval_id: int, review: ApprovalReview, db: Session = Depends(get_db)):
    try:
        approval, result = approve(db, approval_id, review.reviewer, review.notes)
        return {
            "status": "approved",
            "approval_id": approval.id,
            "ticket_id": result.get("ticket_id")
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@router.post("/approvals/{approval_id}/reject")
def reject_approval(approval_id: int, review: ApprovalReview, db: Session = Depends(get_db)):
    try:
        approval = reject(db, approval_id, review.reviewer, review.notes)
        return {
            "status": "rejected",
            "approval_id": approval.id
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))