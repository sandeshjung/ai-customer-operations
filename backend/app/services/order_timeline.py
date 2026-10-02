"""Per-order view of the agent pipeline: event queued → delayed-order agent →
human review / auto-execute → actions → triage. Also a per-ticket view for a
customer-filed ticket going through triage on its own (build_ticket_timeline). Assembled from rows the
pipeline already writes (agent_executions, human_approvals, support_tickets,
notifications) plus Redis for queue position and dead-lettered events.

Deliberately does not import anything from app.agents.graphs or the worker —
that would load the RAG stack at import time (CLAUDE.md gotcha #1).
"""

import json
from datetime import UTC, datetime

from app.core.logging import get_logger
from app.core.redis import redis_client
from app.events.publisher import EVENT_STREAM
from app.models.agent_execution import AgentExecution
from app.models.human_approval import ApprovalStatus, HumanApproval
from app.models.notification import Notification
from app.models.order import Order
from app.models.support_ticket import SupportTicket
from app.workers.config import CONSUMER_GROUP, DEAD_LETTER_STREAM
from sqlalchemy.orm import Session

logger = get_logger(__name__)

# Mirrors action_service._TRIAGE_WORTHY_RESOLUTIONS: only these resolutions
# publish TICKET_CREATED, so only these ever reach the triage agent.
TRIAGE_RESOLUTIONS = {"ESCALATE", "CONTACT_CUSTOMER"}

DEAD_LETTER_SCAN_LIMIT = 500

DONE = "done"
ACTIVE = "active"
PENDING = "pending"
SKIPPED = "skipped"
FAILED = "failed"


def build_order_timeline(
    db: Session,
    order_id: int,
    event_id: str | None = None,
    message_id: str | None = None,
) -> dict | None:
    """Returns None if the order doesn't exist.

    event_id / message_id are what POST /admin/demo/delayed-order returned;
    with them the timeline can report queue position and dead-lettering
    before the agent has written anything. Without them it still works from
    the DB rows alone.
    """
    order = db.get(Order, order_id)
    if order is None:
        return None

    executions = (
        db.query(AgentExecution)
        .filter(AgentExecution.order_id == order_id)
        .order_by(AgentExecution.created_at.desc())
        .all()
    )
    delay_run = next(
        (
            e
            for e in executions
            if e.agent_name == "delayed_order_agent"
            and (event_id is None or e.event_id == event_id)
        ),
        None,
    )
    triage_run = next((e for e in executions if e.agent_name == "triage_agent"), None)

    approval = (
        db.query(HumanApproval)
        .filter(HumanApproval.order_id == order_id)
        .order_by(HumanApproval.created_at.desc())
        .first()
    )
    tickets = (
        db.query(SupportTicket)
        .filter(SupportTicket.order_id == order_id)
        .order_by(SupportTicket.created_at)
        .all()
    )
    notifications = (
        db.query(Notification)
        .filter(Notification.order_id == order_id)
        .order_by(Notification.created_at)
        .all()
    )

    dead_letters = _dead_letters_for(order_id, event_id)
    queue = _queue_position(message_id) if delay_run is None else None

    stages: list[dict] = []

    # 1. Order created -------------------------------------------------------
    stages.append(_stage("order_created", "Order created", DONE, order.created_at))

    # 2. Waiting for the worker ------------------------------------------------
    order_event_failed = dead_letters.get("ORDER_DELAYED")
    picked_up = delay_run is not None or (queue is not None and queue["picked_up"])
    stages.append(
        _stage(
            "event_queued",
            "ORDER_DELAYED queued",
            DONE if picked_up or order_event_failed else ACTIVE,
            detail={"event_id": event_id, "queue": queue},
        )
    )

    # 3. Delayed-order agent ---------------------------------------------------
    if delay_run is not None:
        stages.append(
            _stage(
                "delay_agent",
                "Delayed-order agent",
                DONE,
                delay_run.created_at,
                _execution_detail(delay_run),
            )
        )
    elif order_event_failed:
        stages.append(
            _stage(
                "delay_agent",
                "Delayed-order agent",
                FAILED,
                detail={"error": order_event_failed},
            )
        )
        return _result(order, event_id, "failed", stages)
    else:
        stages.append(
            _stage(
                "delay_agent",
                "Delayed-order agent",
                ACTIVE if picked_up else PENDING,
            )
        )
        return _result(order, event_id, "in_progress", stages)

    decision = delay_run.decision or {}
    resolution = decision.get("resolution")

    # 4. Human review ----------------------------------------------------------
    if decision.get("requires_human"):
        if approval is None or approval.status == ApprovalStatus.PENDING.value:
            # approval is None only in the instant between the worker
            # committing the execution row and committing the approval.
            stages.append(
                _stage(
                    "human_review",
                    "Human review",
                    ACTIVE,
                    approval.created_at if approval else None,
                    {"approval_id": approval.id if approval else None},
                )
            )
            return _result(order, event_id, "awaiting_approval", stages)

        stages.append(
            _stage(
                "human_review",
                "Human review",
                DONE,
                approval.reviewed_at,
                {
                    "approval_id": approval.id,
                    "outcome": approval.status,
                    "reviewer": approval.reviewed_by,
                    "notes": approval.reviewer_notes,
                },
            )
        )
        if approval.status == ApprovalStatus.REJECTED.value:
            stages.append(
                _stage(
                    "actions",
                    "Actions",
                    SKIPPED,
                    detail={"reason": "Rejected by reviewer — nothing executed."},
                )
            )
            stages.append(_stage("triage", "Triage agent", SKIPPED))
            return _result(order, event_id, "complete", stages)
    else:
        stages.append(
            _stage(
                "human_review",
                "Human review",
                SKIPPED,
                detail={"reason": "Not required — executed automatically."},
            )
        )

    # 5. Actions taken ---------------------------------------------------------
    stages.append(
        _stage(
            "actions",
            "Actions",
            DONE,
            detail={
                "resolution": resolution,
                "tickets": [_ticket_detail(t) for t in tickets],
                "notifications": [_notification_detail(n) for n in notifications],
            },
        )
    )

    # 6. Triage agent ----------------------------------------------------------
    if resolution not in TRIAGE_RESOLUTIONS:
        stages.append(
            _stage(
                "triage",
                "Triage agent",
                SKIPPED,
                detail={"reason": f"{resolution} tickets aren't sent to triage."},
            )
        )
        return _result(order, event_id, "complete", stages)

    if triage_run is not None:
        detail = _execution_detail(triage_run)
        ticket_id = (triage_run.input_data or {}).get("ticket_id")
        ticket = next((t for t in tickets if t.id == ticket_id), None)
        detail["ticket"] = _ticket_detail(ticket) if ticket else None
        stages.append(
            _stage("triage", "Triage agent", DONE, triage_run.created_at, detail)
        )
        return _result(order, event_id, "complete", stages)

    ticket_event_failed = dead_letters.get("TICKET_CREATED")
    if ticket_event_failed:
        stages.append(
            _stage(
                "triage",
                "Triage agent",
                FAILED,
                detail={"error": ticket_event_failed},
            )
        )
        return _result(order, event_id, "failed", stages)

    stages.append(
        _stage(
            "triage",
            "Triage agent",
            ACTIVE,
            detail={"reason": "TICKET_CREATED queued — waiting for the worker."},
        )
    )
    return _result(order, event_id, "in_progress", stages)


# Without an order to narrow by, how many recent triage runs to search for one
# whose input_data names this ticket.
TRIAGE_FALLBACK_SCAN_LIMIT = 200


def build_ticket_timeline(
    db: Session,
    ticket_id: int,
    event_id: str | None = None,
    message_id: str | None = None,
) -> dict | None:
    """Timeline for one ticket going through the triage agent on its own:
    ticket filed → TICKET_CREATED queued → triage. Returns None if the ticket
    doesn't exist. event_id / message_id as in build_order_timeline."""
    ticket = db.get(SupportTicket, ticket_id)
    if ticket is None:
        return None

    triage_run = _find_triage_run(db, ticket, event_id)
    queue = _queue_position(message_id) if triage_run is None else None
    failed = (
        _dead_letters_for(None, event_id).get("TICKET_CREATED") if event_id else None
    )
    picked_up = triage_run is not None or (queue is not None and queue["picked_up"])

    stages = [
        _stage(
            "ticket_created",
            "Ticket filed by customer",
            DONE,
            ticket.created_at,
            {"subject": ticket.subject, "message": ticket.message},
        ),
        _stage(
            "event_queued",
            "TICKET_CREATED queued",
            DONE if picked_up or failed else ACTIVE,
            detail={"event_id": event_id, "queue": queue},
        ),
    ]

    if triage_run is not None:
        detail = _execution_detail(triage_run)
        detail["ticket"] = _ticket_detail(ticket)
        stages.append(
            _stage("triage", "Triage agent", DONE, triage_run.created_at, detail)
        )
        state = "complete"
    elif failed:
        stages.append(
            _stage("triage", "Triage agent", FAILED, detail={"error": failed})
        )
        state = "failed"
    else:
        stages.append(
            _stage("triage", "Triage agent", ACTIVE if picked_up else PENDING)
        )
        state = "in_progress"

    return {
        "ticket": _ticket_detail(ticket) | {"order_id": ticket.order_id},
        "event_id": event_id,
        "state": state,
        "stages": stages,
    }


def _find_triage_run(
    db: Session, ticket: SupportTicket, event_id: str | None
) -> AgentExecution | None:
    query = db.query(AgentExecution).filter(AgentExecution.agent_name == "triage_agent")
    if event_id is not None:
        return (
            query.filter(AgentExecution.event_id == event_id)
            .order_by(AgentExecution.created_at.desc())
            .first()
        )

    if ticket.order_id is not None:
        candidates = query.filter(AgentExecution.order_id == ticket.order_id)
    else:
        candidates = query.order_by(AgentExecution.created_at.desc()).limit(
            TRIAGE_FALLBACK_SCAN_LIMIT
        )
    return next(
        (
            run
            for run in sorted(candidates, key=lambda r: r.created_at, reverse=True)
            if (run.input_data or {}).get("ticket_id") == ticket.id
        ),
        None,
    )


def _result(order: Order, event_id: str | None, state: str, stages: list) -> dict:
    today = datetime.now(UTC).date()
    shipment = order.shipment
    return {
        "order": {
            "id": order.id,
            "customer_id": order.customer_id,
            "customer_email": order.customer.email if order.customer else None,
            "status": order.status,
            "expected_delivery": order.expected_delivery,
            "delay_days": (
                (today - order.expected_delivery).days
                if order.expected_delivery
                else None
            ),
            "created_at": order.created_at,
            "shipment": (
                {
                    "carrier": shipment.carrier,
                    "tracking_number": shipment.tracking_number,
                    "status": shipment.status,
                    "last_location": shipment.last_location,
                }
                if shipment
                else None
            ),
        },
        "event_id": event_id,
        "state": state,
        "stages": stages,
    }


def _stage(key, label, status, at=None, detail=None) -> dict:
    return {
        "key": key,
        "label": label,
        "status": status,
        "at": at,
        "detail": detail or {},
    }


def _execution_detail(execution: AgentExecution) -> dict:
    return {
        "execution_id": execution.id,
        "event_id": execution.event_id,
        "decision": execution.decision,
        "steps": execution.steps or [],
        "model": execution.model,
        "total_tokens": execution.total_tokens,
        "llm_call_count": execution.llm_call_count,
        "duration_ms": execution.duration_ms,
        "trace_id": (execution.decision or {}).get("trace_id"),
    }


def _ticket_detail(ticket: SupportTicket) -> dict:
    return {
        "id": ticket.id,
        "subject": ticket.subject,
        "priority": ticket.priority,
        "status": ticket.status,
        "created_at": ticket.created_at,
    }


def _notification_detail(notification: Notification) -> dict:
    return {
        "id": notification.id,
        "channel": notification.channel,
        "recipient": notification.recipient,
        "subject": notification.subject,
        "status": notification.status,
        "created_at": notification.created_at,
    }


def _stream_id(value: str) -> tuple[int, int]:
    ms, _, seq = value.partition("-")
    return int(ms), int(seq or 0)


def _queue_position(message_id: str | None) -> dict | None:
    """How many events are ahead of message_id in the worker's queue, and
    whether the worker has already picked it up. None if unknown."""
    if not message_id:
        return None
    try:
        groups = redis_client.xinfo_groups(EVENT_STREAM)
        group = next((g for g in groups if g.get("name") == CONSUMER_GROUP), None)
        if group is None:
            return None

        last_delivered = group.get("last-delivered-id") or "0-0"
        if _stream_id(last_delivered) >= _stream_id(message_id):
            return {"picked_up": True, "ahead": 0}

        ahead = redis_client.xrange(
            EVENT_STREAM, min=f"({last_delivered}", max=f"({message_id}"
        )
        return {"picked_up": False, "ahead": len(ahead)}
    except Exception:  # queue position is best-effort display info
        logger.warning("Couldn't read queue position", exc_info=True)
        return None


def _dead_letters_for(order_id: int | None, event_id: str | None) -> dict[str, str]:
    """Maps event_type -> error for dead-lettered events matching event_id,
    or (when order_id is given) any event about that order."""
    found: dict[str, str] = {}
    try:
        entries = redis_client.xrevrange(
            DEAD_LETTER_STREAM, count=DEAD_LETTER_SCAN_LIMIT
        )
    except Exception:  # DLQ lookup is best-effort display info
        logger.warning("Couldn't read dead-letter stream", exc_info=True)
        return found

    for _, fields in entries:
        try:
            event = json.loads(fields.get("event", "{}"))
        except json.JSONDecodeError:
            continue
        event_type = event.get("event_type")
        matches = (event_id is not None and event.get("event_id") == event_id) or (
            order_id is not None
            and (event.get("data") or {}).get("order_id") == order_id
        )
        if matches and event_type not in found:
            found[event_type] = fields.get("error", "unknown error")
    return found
