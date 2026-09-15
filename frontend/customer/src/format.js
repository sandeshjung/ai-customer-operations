export function formatDate(value) {
  if (!value) return null;
  return new Date(value).toLocaleDateString(undefined, {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

export function formatMoney(amount) {
  return new Intl.NumberFormat(undefined, { style: "currency", currency: "USD" }).format(amount);
}

const STATUS_LABELS = {
  PENDING: "Pending",
  CONFIRMED: "Confirmed",
  PROCESSING: "Processing",
  SHIPPED: "Shipped",
  DELIVERED: "Delivered",
  CANCELLED: "Cancelled",
  REFUNDED: "Refunded",
};

export function formatOrderStatus(status) {
  return STATUS_LABELS[status] || status;
}

const SHIPMENT_STATUS_LABELS = {
  LABEL_CREATED: "Label created",
  IN_TRANSIT: "In transit",
  OUT_FOR_DELIVERY: "Out for delivery",
  DELIVERED: "Delivered",
  EXCEPTION: "Exception",
  LOST: "Lost",
};

export function formatShipmentStatus(status) {
  return SHIPMENT_STATUS_LABELS[status] || status;
}

const TICKET_STATUS_LABELS = {
  OPEN: "Open",
  IN_PROGRESS: "In progress",
  RESOLVED: "Resolved",
  CLOSED: "Closed",
};

export function formatTicketStatus(status) {
  return TICKET_STATUS_LABELS[status] || status;
}
