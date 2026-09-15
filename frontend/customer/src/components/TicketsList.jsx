import { formatDate, formatTicketStatus } from "../format";

export function TicketsList({ tickets }) {
  if (tickets.length === 0) {
    return (
      <div className="card">
        <h3>Support tickets</h3>
        <p className="muted">No support tickets for this order's account yet.</p>
      </div>
    );
  }

  return (
    <div className="card">
      <h3>Support tickets</h3>
      <ul className="tickets">
        {tickets.map((ticket) => (
          <li key={ticket.id}>
            <div className="ticket-row">
              <span className="ticket-subject">{ticket.subject}</span>
              <span className={`status-pill status-${ticket.status.toLowerCase()}`}>
                {formatTicketStatus(ticket.status)}
              </span>
            </div>
            <div className="muted small">Opened {formatDate(ticket.created_at)}</div>
          </li>
        ))}
      </ul>
    </div>
  );
}
