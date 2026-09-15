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
  // NOTE: this is a guest-lookup pattern (order ID + the email on the
  // order), not real authentication — there's no customer login/session
  // system. It's only meant to stop someone from casually browsing other
  // customers' orders by guessing IDs, same as most e-commerce "track your
  // order" pages.
  lookupOrder: (orderId, email) =>
    request(`/portal/orders/${encodeURIComponent(orderId)}?email=${encodeURIComponent(email)}`),
  ticketsForCustomer: (customerId) => request(`/tickets?customer_id=${encodeURIComponent(customerId)}`),
};

export { ApiError };
