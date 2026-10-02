const DEFAULT_API_BASE = "http://localhost:8000/api/v1";

export function getApiBase() {
  return (localStorage.getItem("customerApiBase") || DEFAULT_API_BASE).replace(/\/$/, "");
}

export function setApiBase(value) {
  localStorage.setItem("customerApiBase", value.trim());
}

class ApiError extends Error {}

async function request(path) {
  const res = await fetch(getApiBase() + path);

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      // response wasn't JSON — keep statusText
    }
    throw new ApiError(detail, { cause: res.status });
  }

  return res.json();
}

export const api = {
  // NOTE: public lookup by order number alone — no authentication. See the
  // comment in backend/app/api/customer_portal.py for the trade-off.
  lookupOrder: (orderId) => request(`/portal/orders/${encodeURIComponent(orderId)}`),
  ticketsForCustomer: (customerId) => request(`/tickets?customer_id=${encodeURIComponent(customerId)}`),
};

export { ApiError };
