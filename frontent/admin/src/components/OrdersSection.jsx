export function OrdersSection({ orders, status, error }) {
  const sorted = status === "ready" ? [...orders].sort((a, b) => b.delay_days - a.delay_days) : [];

  return (
    <section>
      <div className="section-head">
        <h2>Delayed orders</h2>
        <span className="count">{status === "ready" ? orders.length : "—"}</span>
      </div>

      {status === "loading" && <div className="loading">Loading…</div>}

      {status === "error" && <div className="error">Couldn't load delayed orders — {error}</div>}

      {status === "ready" && sorted.length === 0 && (
        <div className="empty">Nothing delayed right now.</div>
      )}

      {status === "ready" && sorted.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Order</th>
              <th>Customer</th>
              <th>Expected</th>
              <th>Delay</th>
              <th>Shipment status</th>
              <th>Tracking</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((o) => (
              <tr key={o.order_id}>
                <td>#{o.order_id}</td>
                <td>#{o.customer_id}</td>
                <td>{o.expected_delivery}</td>
                <td>{o.delay_days}d</td>
                <td>{o.shipment_status || "no record"}</td>
                <td>{o.tracking_number || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
