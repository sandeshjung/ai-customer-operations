import { useCallback, useEffect, useRef, useState } from "react";
import { api, getApiBase, getApiKey, setApiBase, setApiKey } from "./api";
import { useToast } from "./useToast";
import { ApprovalsSection } from "./components/ApprovalsSelection";
import { NotificationsSection } from "./components/NotificationsSection";
import { OrdersSection } from "./components/OrdersSection";
import { TicketsSection } from "./components/TicketsSection";
import { UsageSection } from "./components/UsageSection";

// Approvals/tickets/notifications are small, fast-changing lists — poll them
// often so new activity shows up without a manual refresh. Delayed orders is
// a much larger payload (thousands of rows) that only changes as wall-clock
// dates cross a threshold, so it gets its own, slower interval.
const LIVE_POLL_INTERVAL_MS = 4000;
const ORDERS_POLL_INTERVAL_MS = 20000;

// Generic "list endpoint" state: idle -> loading -> ready | error
function useEndpointState(emptyData = []) {
  const [state, setState] = useState({ status: "loading", data: emptyData, error: "" });
  return [state, setState];
}

const EMPTY_USAGE = { summary: null, by_agent: [], recent: [] };

export default function App() {
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

  const loadLive = useCallback(() => {
    setConnState("pending");
    loadApprovals();
    loadTickets();
    loadNotifications();
    loadUsage();
  }, [loadApprovals, loadTickets, loadNotifications, loadUsage]);

  const loadAll = useCallback(() => {
    loadLive();
    loadOrders();
  }, [loadLive, loadOrders]);

  const loadLiveRef = useRef(loadLive);
  loadLiveRef.current = loadLive;
  useEffect(() => {
    loadLiveRef.current();
    const id = setInterval(() => loadLiveRef.current(), LIVE_POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [ticketStatusFilter]);

  const loadOrdersRef = useRef(loadOrders);
  loadOrdersRef.current = loadOrders;
  useEffect(() => {
    loadOrdersRef.current();
    const id = setInterval(() => loadOrdersRef.current(), ORDERS_POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, []);

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

  return (
    <div className="wrap">
        <header className="top">
            <div>
                <h1>Operations console</h1>
                <div className="sub">Approvals, delayed orders, and support tickets</div>
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
        
        <TicketsSection 
        tickets={tickets.data} 
        status={tickets.status} 
        error={tickets.error}
        statusFilter={ticketStatusFilter}
        onStatusFilterChange={setTicketStatusFilter} />

        <NotificationsSection
                notifications={notifications.data}
                status={notifications.status}
                error={notifications.error}
              />

        <UsageSection
                usage={usage.data}
                status={usage.status}
                error={usage.error}
              />

      <div className={`toast ${toast.show ? "show" : ""} ${toast.kind}`}>{toast.message}</div>

    </div>
  );
}