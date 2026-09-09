import { Badge } from "./Badge";
import { relativeTime } from "../format";

const STATUS_OPTIONS = [
  { value: "", label: "All statuses" },
  { value: "OPEN", label: "Open" },
  { value: "IN_PROGRESS", label: "In progress" },
  { value: "RESOLVED", label: "Resolved" },
  { value: "CLOSED", label: "Closed" },
];

export function TicketsSection({ tickets, status, error, statusFilter, onStatusFilterChange }) {
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

      {status === "loading" && <div className="loading">Loading…</div>}

      {status === "error" && <div className="error">Couldn't load tickets — {error}</div>}

      {status === "ready" && tickets.length === 0 && <div className="empty">No tickets yet.</div>}

      {status === "ready" && tickets.length > 0 && (
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
            </tr>
          </thead>
          <tbody>
            {tickets.map((t) => (
              <tr key={t.id}>
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
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
