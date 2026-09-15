import { useState } from "react";
import { relativeTime } from "../format";
import { Badge } from "./Badge";
import { jaegerTraceUrl } from "../api";

export function ApprovalCard({ approval, onReview }) {
    const [pending, setPending] = useState(false);
    const decision = approval.decision || {};
    const severity = decision.severity || "-";
    const traceUrl = jaegerTraceUrl(decision.trace_id);

    async function handleReview(action) {
        setPending(true);
        try {
            await onReview(approval.id, action);
        } finally {
            // On succes the card unmounts 
            setPending(false);
        }
    }
    
    return (
        <div className={`approval sev-${severity}`}>
              <div className="approval-top">
                <div className="approval-meta">
                  <Badge kind="sev" value={severity} />
                  <span className="mono">order #{approval.order_id}</span>
                  <span className="mono">customer #{approval.customer_id}</span>
                  <span>{approval.agent_name}</span>
                  <span>{relativeTime(approval.created_at)}</span>
                  {traceUrl && (
                    <a className="trace-link" href={traceUrl} target="_blank" rel="noreferrer">
                      View trace ↗
                    </a>
                  )}
                </div>
              </div>
        
              <div className="approval-reasoning">
                <span className="label">Recommended action: {decision.resolution || "—"}</span>
                {decision.reasoning || "No reasoning provided."}
              </div>
        
              {decision.customer_message && (
                <div className="approval-reasoning">
                  <span className="label">Draft customer message</span>
                  {decision.customer_message}
                </div>
              )}
        
              <div className="approval-actions">
                <button className="approve" disabled={pending} onClick={() => handleReview("approve")}>
                  Approve
                </button>
                <button className="reject" disabled={pending} onClick={() => handleReview("reject")}>
                  Reject
                </button>
              </div>
            </div>
    )
}