import { useEffect, useMemo, useState } from "react";
import { Badge } from "./Badge";
import { Modal } from "./Modal";
import { relativeTime } from "../format";

const PAGE_SIZE = 10;

export function NotificationsSection({ notifications, status, error }) {
  const sorted = useMemo(
    () =>
      status === "ready"
        ? [...notifications].sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
        : [],
    [notifications, status],
  );
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    setPage(1);
  }, [sorted.length]);

  const totalPages = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));

  useEffect(() => {
    setPage((current) => Math.min(current, totalPages));
  }, [totalPages]);

  const visible = sorted.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  return (
    <section>
      <div className="section-head">
        <div className="section-head-title">
          <h2>Notifications sent</h2>
          <span className="count">{status === "ready" ? notifications.length : "—"}</span>
        </div>
      </div>

      {status === "loading" && <div className="loading">Loading…</div>}

      {status === "error" && <div className="error">Couldn't load notifications — {error}</div>}

      {status === "ready" && sorted.length === 0 && (
        <div className="empty">No notifications sent yet.</div>
      )}

      {status === "ready" && sorted.length > 0 && (
        <div className="panel">
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Recipient</th>
                  <th>Subject</th>
                  <th>Channel</th>
                  <th>Status</th>
                  <th>Order</th>
                  <th>Sent</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((n) => (
                  <tr
                    key={n.id}
                    className="row-clickable"
                    onClick={() => setSelected(n)}
                    tabIndex={0}
                    role="button"
                    aria-label={`View notification to ${n.recipient}`}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") setSelected(n);
                    }}
                  >
                    <td className="mono">{n.recipient}</td>
                    <td className="subject">{n.subject || "—"}</td>
                    <td>{n.channel}</td>
                    <td>
                      <Badge kind="status" value={n.status} />
                    </td>
                    <td>{n.order_id ? `#${n.order_id}` : "—"}</td>
                    <td>{relativeTime(n.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="pagination" aria-label="Notifications pagination">
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
        </div>
      )}

      <Modal open={!!selected} onClose={() => setSelected(null)} title="Notification">
        {selected && (
          <>
            <dl className="email-preview-meta">
              <dt>To</dt>
              <dd className="mono">{selected.recipient}</dd>
              <dt>Subject</dt>
              <dd>{selected.subject || "—"}</dd>
              <dt>Status</dt>
              <dd>
                <Badge kind="status" value={selected.status} />
              </dd>
              <dt>Channel</dt>
              <dd>{selected.channel}</dd>
              <dt>Customer</dt>
              <dd>#{selected.customer_id}</dd>
              <dt>Order</dt>
              <dd>{selected.order_id ? `#${selected.order_id}` : "No order linked"}</dd>
              <dt>Sent</dt>
              <dd>{relativeTime(selected.created_at)}</dd>
            </dl>

            {selected.error && <p className="email-preview-error">Delivery error: {selected.error}</p>}

            <div className="email-preview-body">{selected.content}</div>
          </>
        )}
      </Modal>
    </section>
  );
}
