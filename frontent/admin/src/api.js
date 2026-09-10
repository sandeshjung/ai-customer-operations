const DEFAULT_API_BASE = "http://localhost:8000/api/v1";
const DEFAULT_JAEGER_UI = "http://localhost:16686";

export function getApiBase() {
  return (localStorage.getItem("adminApiBase") || DEFAULT_API_BASE).replace(/\/$/, "");
}

export function setApiBase(value) {
  localStorage.setItem("adminApiBase", value.trim());
}

export function jaegerTraceUrl(traceId) {
  if (!traceId) return null;
  const base = (localStorage.getItem("adminJaegerUrl") || DEFAULT_JAEGER_UI).replace(/\/$/, "");
  return `${base}/trace/${traceId}`;
}

export function getReviewerName() {
  let name = localStorage.getItem("adminReviewerName");
  if (!name) {
    name = window.prompt("Your name (used as the reviewer on approvals):", "admin") || "admin";
    localStorage.setItem("adminReviewerName", name);
  }
  return name;
}

class ApiError extends Error {}

async function request(path, options = {}) {
  const res = await fetch(getApiBase() + path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      // response wasn't JSON — keep statusText
    }
    throw new ApiError(`${res.status} ${detail}`);
  }

  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  pendingApprovals: () => request("/admin/approvals/pending"),
  reviewApproval: (id, action, notes = null) =>
    request(`/admin/approvals/${id}/${action}`, {
      method: "POST",
      body: JSON.stringify({ reviewer: getReviewerName(), notes }),
    }),
  delayedOrders: () => request("/orders/delayed"),
  tickets: (status) => request("/tickets" + (status ? `?status=${status}` : "")),
};
