import { ApprovalCard } from "./ApprovalCard";

export function ApprovalsSection({ approvals, status, error, onReview }) {
  return (
    <section>
      <div className="section-head">
        <h2>Pending approvals</h2>
        <span className="count">{status === "ready" ? approvals.length : "—"}</span>
      </div>

      {status === "loading" && <div className="loading">Loading…</div>}

      {status === "error" && <div className="error">{error}</div>}

      {status === "ready" && approvals.length === 0 && (
        <div className="empty">No approvals waiting.</div>
      )}

      {status === "ready" &&
        approvals.map((approval) => (
          <ApprovalCard key={approval.id} approval={approval} onReview={onReview} />
        ))}
    </section>
  );
}
