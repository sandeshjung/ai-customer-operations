import { useCallback, useEffect, useRef, useState } from "react";
import { api, getApiBase, getApiKey, setApiBase, setApiKey } from "./api";
import { useToast } from "./useToast";
import { ApprovalsSection } from "./components/ApprovalsSelection";
import { NotificationsSection } from "./components/NotificationsSection";
import { OrdersSection } from "./components/OrdersSection";
import { SimulateSection } from "./components/SimulateSection";
import { TicketsSection } from "./components/TicketsSection";
import { UsageSection } from "./components/UsageSection";

// Approvals/tickets/notifications are small, fast-changing lists — poll them
// often so new activity shows up without a manual refresh. Delayed orders is
// a much larger payload (thousands of rows) that only changes as wall-clock
// dates cross a threshold, so it gets its own, slower interval.
const LIVE_POLL_INTERVAL_MS = 4000;
const ORDERS_POLL_INTERVAL_MS = 20000;

// Hash routes (#/tickets) rather than a router dependency: works under both
// the Vite dev server and the nginx container with no server config, and
// back/forward + bookmarks still work.
const PAGES = [
  { id: "overview", label: "Overview", sub: "Pending approvals and delayed orders" },
  { id: "simulate", label: "Simulate", sub: "Send a demo order or complaint through the agents" },
  { id: "tickets", label: "Support tickets", sub: "Every ticket, agent- or customer-created" },
  { id: "notifications", label: "Notifications", sub: "Customer notifications the agents sent" },
  { id: "usage", label: "AI usage", sub: "Token usage and estimated cost per agent run" },
];

function pageFromHash() {
  const id = window.location.hash.replace(/^#\/?/, "");
  return PAGES.some((p) => p.id === id) ? id : "overview";
}

function usePage() {
  const [page, setPage] = useState(pageFromHash);
  useEffect(() => {
    const onHashChange = () => setPage(pageFromHash());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);
  return page;
}

// Generic "list endpoint" state: idle -> loading -> ready | error
function useEndpointState(emptyData = []) {
  const [state, setState] = useState({ status: "loading", data: emptyData, error: "" });
  return [state, setState];
}

const EMPTY_USAGE = { summary: null, by_agent: [], recent: [] };

export default function App() {
  const page = usePage();
  const [approvals, setApprovals] = useEndpointState();
  const [apiBaseValue, setApiBaseValue] = useState(getApiBase());
  const [apiKeyValue, setApiKeyValue] = useState(getApiKey());
  const [connState, setConnState] = useState("pending");
  const [orders, setOrders] = useEndpointState();
  const [tickets, setTickets] = useEndpointState();
  const [notifications, setNotifications] = useEndpointState();
  const [usage, setUsage] = useEndpointState(EMPTY_USAGE);
  const [ticketStatusFilter, setTicketStatusFilter] = useState("");
  const {toast, showToast } = useToast();

  const loadApprovals = useCallback(async () => {
    try {
        const data = await api.pendingApprovals();
        setApprovals({ status: "ready", data, error: "" });
        setConnState("ok");
    } catch (err) {
        setApprovals({ status: "error", data: [], error: err.message });
        setConnState(err.message.startsWith("401") ? "unauthorized" : "err");
    }
  }, [setApprovals]);

  const loadOrders = useCallback(async () => {
    try {
        const data = await api.delayedOrders();
        setOrders({ status: "ready", data, error: "" });
    } catch (err) {
        setOrders({ status: "error", data: [], error: err.message });
    }
  }, [setOrders]);

  const loadTickets = useCallback(async () => {
    try {
        const data = await api.tickets(ticketStatusFilter);
        setTickets({ status: "ready", data, error: "" });
    } catch (err) {
        setTickets({ status: "error", data: [], error: err.message });
    }
  }, [setTickets, ticketStatusFilter]);

  const loadNotifications = useCallback(async () => {
    try {
        const data = await api.notifications();
        setNotifications({ status: "ready", data, error: "" });
    } catch (err) {
        setNotifications({ status: "error", data: [], error: err.message });
    }
  }, [setNotifications]);

  const loadUsage = useCallback(async () => {
    try {
        const data = await api.usage();
        setUsage({ status: "ready", data, error: "" });
    } catch (err) {
        setUsage({ status: "error", data: EMPTY_USAGE, error: err.message });
    }
  }, [setUsage]);

  // Approvals load on every page: they drive the nav badge and the
  // connection indicator. Everything else only loads on the page that shows it.
  const loadLive = useCallback(() => {
    loadApprovals();
    if (page === "tickets") loadTickets();
    if (page === "notifications") loadNotifications();
    if (page === "usage") loadUsage();
  }, [page, loadApprovals, loadTickets, loadNotifications, loadUsage]);

  const loadAll = useCallback(() => {
    setConnState("pending");
    loadLive();
    if (page === "overview") loadOrders();
  }, [page, loadLive, loadOrders]);

  const loadLiveRef = useRef(loadLive);
  loadLiveRef.current = loadLive;
  useEffect(() => {
    loadLiveRef.current();
    const id = setInterval(() => loadLiveRef.current(), LIVE_POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [page, ticketStatusFilter]);

  const loadOrdersRef = useRef(loadOrders);
  loadOrdersRef.current = loadOrders;
  useEffect(() => {
    if (page !== "overview") return undefined;
    loadOrdersRef.current();
    const id = setInterval(() => loadOrdersRef.current(), ORDERS_POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [page]);

  async function handleReviewApproval(id, action) {
    try {
        await api.reviewApproval(id, action);
        showToast(`Approval #${id} ${action === "approve" ? "approved" : "rejected"}.`, "ok");
        loadApprovals();
    } catch (err) {
        showToast(`Couldn't ${action} #${id}: ${err.message}`, "err");
        throw err;
    }
  }

  async function handlePublishDelayedOrders(count) {
    try {
      const result = await api.publishDelayedOrders(count);
      showToast(
        `Published ${result.published_events} delayed-order event(s) — the worker will pick them up shortly. Approvals/tickets will refresh automatically.`,
        "ok",
      );
    } catch (err) {
      showToast(`Couldn't publish delayed orders: ${err.message}`, "err");
    }
  }

  function handleApiBaseChange(value) {
    setApiBaseValue(value);
    setApiBase(value);
    loadAll();
  }

  function handleApiKeyChange(value) {
    setApiKeyValue(value);
    setApiKey(value);
    loadAll();
  }

  const current = PAGES.find((p) => p.id === page);
  const pendingCount = approvals.status === "ready" ? approvals.data.length : 0;

  return (
    <div className="wrap">
        <header className="top">
            <div>
                <h1>Operations console</h1>
                <div className="sub">{current.sub}</div>
            </div>
            <div className="conn">
                <span className="conn-status">
                  <span className={`dot ${connState}`}></span>
                  {connState === "ok" && "Connected"}
                  {connState === "err" && "Can't reach API"}
                  {connState === "unauthorized" && "Invalid API key"}
                  {connState === "pending" && "Connecting…"}
                </span>
                <input
                className="mono"
                spellCheck={false}
                value={apiBaseValue}
                onChange={(e) => handleApiBaseChange(e.target.value)}
                />
                <input
                className="mono"
                type="password"
                placeholder="API key"
                spellCheck={false}
                value={apiKeyValue}
                onChange={(e) => handleApiKeyChange(e.target.value)}
                />
                <button className="ghost" onClick={loadAll}>
                    Refresh
                </button>
            </div>
        </header>

        <nav className="page-nav" aria-label="Sections">
          {PAGES.map((p) => (
            <a
              key={p.id}
              href={`#/${p.id}`}
              className={`page-link ${p.id === page ? "active" : ""}`}
              aria-current={p.id === page ? "page" : undefined}
            >
              {p.label}
              {p.id === "overview" && pendingCount > 0 && (
                <span className="nav-count" title={`${pendingCount} pending approval(s)`}>
                  {pendingCount}
                </span>
              )}
            </a>
          ))}
        </nav>

        {page === "overview" && (
          <>
            <ApprovalsSection
              approvals={approvals.data}
              status={approvals.status}
              error={approvals.error}
              onReview={handleReviewApproval}
            />
            <OrdersSection
              orders={orders.data}
              status={orders.status}
              error={orders.error}
              onPublish={handlePublishDelayedOrders}
            />
          </>
        )}

        {page === "simulate" && (
          <SimulateSection onReview={handleReviewApproval} showToast={showToast} />
        )}

        {page === "tickets" && (
          <TicketsSection
            tickets={tickets.data}
            status={tickets.status}
            error={tickets.error}
            statusFilter={ticketStatusFilter}
            onStatusFilterChange={setTicketStatusFilter}
          />
        )}

        {page === "notifications" && (
          <NotificationsSection
            notifications={notifications.data}
            status={notifications.status}
            error={notifications.error}
          />
        )}

        {page === "usage" && (
          <UsageSection usage={usage.data} status={usage.status} error={usage.error} />
        )}

      <div className={`toast ${toast.show ? "show" : ""} ${toast.kind}`}>{toast.message}</div>

    </div>
  );
}
