import { Fragment, useEffect, useMemo, useState } from "react";

const PAGE_SIZE = 10;

export function OrdersSection({ orders, status, error }) {
  const sorted = useMemo(
    () => (status === "ready" ? [...orders].sort((a, b) => b.delay_days - a.delay_days) : []),
    [orders, status],
  );
  const [page, setPage] = useState(1);
  const [expanded, setExpanded] = useState({});

  useEffect(() => {
    setPage(1);
    setExpanded({});
  }, [sorted.length]);

  const totalPages = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));

  useEffect(() => {
    setPage((current) => Math.min(current, totalPages));
  }, [totalPages]);

  const visibleOrders = sorted.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const toggleExpanded = (orderId) => {
    setExpanded((current) => ({
      ...current,
      [orderId]: !current[orderId],
    }));
  };

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
        <>
          <table>
            <thead>
              <tr>
                <th>Order</th>
                <th>Customer</th>
                <th>Expected</th>
                <th>Delay</th>
                <th>Shipment status</th>
                <th>Tracking</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              {visibleOrders.map((o) => {
                const isExpanded = !!expanded[o.order_id];
                return (
                  <Fragment key={o.order_id}>
                    <tr>
                      <td>#{o.order_id}</td>
                      <td>#{o.customer_id}</td>
                      <td>{o.expected_delivery}</td>
                      <td>{o.delay_days}d</td>
                      <td>{o.shipment_status || "no record"}</td>
                      <td>{o.tracking_number || "—"}</td>
                      <td>
                        <button
                          className="collapse-toggle"
                          type="button"
                          onClick={() => toggleExpanded(o.order_id)}
                        >
                          {isExpanded ? "Hide" : "View"}
                        </button>
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr className="detail-row">
                        <td colSpan={7}>
                          <div className="detail-card">
                            <div>
                              <span className="detail-label">Order</span>
                              <strong>#{o.order_id}</strong>
                            </div>
                            <div>
                              <span className="detail-label">Customer</span>
                              <strong>#{o.customer_id}</strong>
                            </div>
                            <div>
                              <span className="detail-label">Shipment</span>
                              <strong>{o.shipment_status || "No shipment record"}</strong>
                            </div>
                            <div>
                              <span className="detail-label">Tracking</span>
                              <strong>{o.tracking_number || "—"}</strong>
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
            <div className="pagination" aria-label="Delayed orders pagination">
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
