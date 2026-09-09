import { useEffect, useMemo, useState } from "react";
import { ApprovalCard } from "./ApprovalCard";

const PAGE_SIZE = 10;

export function ApprovalsSection({ approvals, status, error, onReview }) {
  const sorted = useMemo(
    () => (status === "ready" ? [...approvals].sort((a, b) => new Date(b.created_at) - new Date(a.created_at)) : []),
    [approvals, status],
  );
  const [page, setPage] = useState(1);

  useEffect(() => {
    setPage(1);
  }, [sorted.length]);

  const totalPages = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));

  useEffect(() => {
    setPage((current) => Math.min(current, totalPages));
  }, [totalPages]);

  const visibleApprovals = sorted.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

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

      {status === "ready" && (
        <>
          {visibleApprovals.map((approval) => (
            <ApprovalCard key={approval.id} approval={approval} onReview={onReview} />
          ))}

          {totalPages > 1 && (
            <div className="pagination" aria-label="Approvals pagination">
              <button
                type="button"
                className="page-button"
                disabled={page === 1}
                onClick={() => setPage((current) => Math.max(1, current - 1))}
              >
                Prev
              </button>

              <div className="page-indicator">
                Page {page} of {totalPages}
              </div>

              <button
                type="button"
                className="page-button"
                disabled={page === totalPages}
                onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </section>
  );
}
