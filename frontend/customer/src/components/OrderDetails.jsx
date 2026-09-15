import { formatDate, formatMoney, formatOrderStatus, formatShipmentStatus } from "../format";

export function OrderDetails({ order }) {
  return (
    <div className="card order-card">
      <div className="order-card-header">
        <div>
          <div className="eyebrow">Order #{order.order_id}</div>
          <h2>{formatOrderStatus(order.status)}</h2>
        </div>
        <div className={`status-pill ${order.is_delayed ? "delayed" : "ontrack"}`}>
          {order.is_delayed ? `Delayed ${order.delay_days}d` : "On track"}
        </div>
      </div>

      {order.is_delayed && (
        <p className="notice">
          This order is running behind — it was expected {formatDate(order.expected_delivery)}. We're sorry
          for the wait.
        </p>
      )}

      <dl className="detail-grid">
        <div>
          <dt>Placed on</dt>
          <dd>{formatDate(order.created_at)}</dd>
        </div>
        <div>
          <dt>Expected delivery</dt>
          <dd>{order.expected_delivery ? formatDate(order.expected_delivery) : "Not yet scheduled"}</dd>
        </div>
        <div>
          <dt>Total</dt>
          <dd>{formatMoney(order.total_amount)}</dd>
        </div>
      </dl>

      {order.shipment && (
        <div className="shipment">
          <h3>Shipment</h3>
          <dl className="detail-grid">
            <div>
              <dt>Carrier</dt>
              <dd>{order.shipment.carrier}</dd>
            </div>
            <div>
              <dt>Tracking number</dt>
              <dd className="mono">{order.shipment.tracking_number}</dd>
            </div>
            <div>
              <dt>Status</dt>
              <dd>{formatShipmentStatus(order.shipment.status)}</dd>
            </div>
            {order.shipment.last_location && (
              <div>
                <dt>Last seen</dt>
                <dd>{order.shipment.last_location}</dd>
              </div>
            )}
          </dl>
        </div>
      )}

      <div className="items">
        <h3>Items</h3>
        <ul>
          {order.items.map((item) => (
            <li key={item.id}>
              <span>Product #{item.product_id}</span>
              <span className="muted">× {item.quantity}</span>
              <span>{formatMoney(item.unit_price)}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
