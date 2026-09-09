import { Fragment, useEffect, useMemo, useState } from "react";
import { Badge } from "./Badge";
import { relativeTime } from "../format";

const PAGE_SIZE = 10;

const STATUS_OPTIONS = [
  { value: "", label: "All statuses" },
  { value: "OPEN", label: "Open" },
  { value: "IN_PROGRESS", label: "In progress" },
  { value: "RESOLVED", label: "Resolved" },
  { value: "CLOSED", label: "Closed" },
];

export function TicketsSection({ tickets, status, error, statusFilter, onStatusFilterChange }) {
  const sorted = useMemo(
    () => (status === "ready" ? [...tickets].sort((a, b) => new Date(b.created_at) - new Date(a.created_at)) : []),
    [tickets, status],
  );
  const [page, setPage] = useState(1);
  const [expanded, setExpanded] = useState({});
  const [searchId, setSearchId] = useState("");

  useEffect(() => {
    setPage(1);
    setExpanded({});
  }, [sorted.length, statusFilter]);

  const filteredTickets = useMemo(() => {
    const trimmed = searchId.trim();
    if (!trimmed) return sorted;
    const target = Number(trimmed);
    if (Number.isNaN(target)) return [];
    return sorted.filter((ticket) => ticket.id === target || ticket.customer_id === target || ticket.order_id === target);
  }, [searchId, sorted]);

  const totalPages = Math.max(1, Math.ceil(filteredTickets.length / PAGE_SIZE));

  useEffect(() => {
    setPage((current) => Math.min(current, totalPages));
  }, [totalPages]);

  const visibleTickets = filteredTickets.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const toggleExpanded = (ticketId) => {
    setExpanded((current) => {
      const hasOpen = !!current[ticketId];
      const next = {};
      Object.keys(current).forEach((key) => {
        next[key] = false;
      });
      if (!hasOpen) {
        next[ticketId] = true;
      }
      return next;
    });
  };

  return (
    <section>
      <div className="section-head">
        <h2>Support tickets</h2>
        <select
          className="filter"
          value={statusFilter}
          onChange={(e) => onStatusFilterChange(e.target.value)}
        >
          {STATUS_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {status === "ready" && (
        <div className="list-toolbar">
          <input
            className="search-input"
            type="search"
            inputMode="numeric"
            placeholder="Search ticket/order/customer ID"
            value={searchId}
            onChange={(e) => setSearchId(e.target.value)}
          />
        </div>
      )}

      {status === "loading" && <div className="loading">Loading…</div>}

      {status === "error" && <div className="error">Couldn't load tickets — {error}</div>}

      {status === "ready" && filteredTickets.length === 0 && (
        <div className="empty">{searchId ? "No matching tickets." : "No tickets yet."}</div>
      )}

      {status === "ready" && filteredTickets.length > 0 && (
        <>
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Subject</th>
                <th>Customer</th>
                <th>Order</th>
                <th>Priority</th>
                <th>Status</th>
                <th>Created</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              {visibleTickets.map((t) => {
                const isExpanded = !!expanded[t.id];
                return (
                  <Fragment key={t.id}>
                    <tr>
                      <td>#{t.id}</td>
                      <td className="subject">{t.subject}</td>
                      <td>#{t.customer_id}</td>
                      <td>{t.order_id ? `#${t.order_id}` : "—"}</td>
                      <td>
                        <Badge kind="pri" value={t.priority} />
                      </td>
                      <td>
                        <Badge kind="status" value={t.status} />
                      </td>
                      <td>{relativeTime(t.created_at)}</td>
                      <td>
                        <button
                          className="collapse-toggle"
                          type="button"
                          onClick={() => toggleExpanded(t.id)}
                        >
                          {isExpanded ? "Hide" : "View"}
                        </button>
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr className="detail-row">
                        <td colSpan={8}>
                          <div className="detail-card">
                            <div>
                              <span className="detail-label">Subject</span>
                              <strong>{t.subject}</strong>
                            </div>
                            <div>
                              <span className="detail-label">Customer</span>
                              <strong>#{t.customer_id}</strong>
                            </div>
                            <div>
                              <span className="detail-label">Order</span>
                              <strong>{t.order_id ? `#${t.order_id}` : "No order linked"}</strong>
                            </div>
                            <div className="detail-message">
                              <span className="detail-label">Message</span>
                              <p>{t.message}</p>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>

          {totalPages > 1 && (
            <div className="pagination" aria-label="Tickets pagination">
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
