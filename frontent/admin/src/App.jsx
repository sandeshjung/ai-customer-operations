import { useCallback, useEffect, useRef, useState } from "react";
import { api, getApiBase, setApiBase } from "./api";
import { useToast } from "./useToast";
import { ApprovalsSection } from "./components/ApprovalsSelection";
import { OrdersSection } from "./components/OrdersSection";
import { TicketsSection } from "./components/TicketsSection";

const POLL_INTERVAL_MS = 20000;

// Generic "list endpoint" state: idle -> loading -> ready | error
function useEndpointState() {
  const [state, setState] = useState({ status: "loading", data: [], error: "" });
  return [state, setState];
}

export default function App() {
  const [approvals, setApprovals] = useEndpointState();
  const [apiBaseValue, setApiBaseValue] = useState(getApiBase());
  const [connState, setConnState] = useState("pending");
  const [orders, setOrders] = useEndpointState();
  const [tickets, setTickets] = useEndpointState();
  const [ticketStatusFilter, setTicketStatusFilter] = useState("");
  const {toast, showToast } = useToast();

  const loadApprovals = useCallback(async () => {
    try {
        const data = await api.pendingApprovals();
        setApprovals({ status: "ready", data, error: "" });
        setConnState("ok");
    } catch (err) {
        setApprovals({ status: "error", data: [], error: err.message });
        setConnState("err");
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

  const loadAll = useCallback(() => {
    setConnState("pending");
    loadApprovals();
    loadOrders();
    loadTickets();
  }, [loadApprovals, loadOrders, loadTickets]);

  const loadAllRef = useRef(loadAll);
  loadAllRef.current = loadAll;
  useEffect(() => {
    loadAllRef.current();
    const id = setInterval(() => loadAllRef.current(), POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [ticketStatusFilter]);

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

  function handleApiBaseChange(value) {
    setApiBaseValue(value);
    setApiBase(value);
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
                <span className={`dot ${connState}`}></span>
                <input 
                className="mono"
                spellCheck={false}
                value={apiBaseValue}
                onChange={(e) => handleApiBaseChange(e.target.value)}
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
        
        <OrdersSection orders={orders.data} status={orders.status} error={orders.error} />
        
        <TicketsSection 
        tickets={tickets.data} 
        status={tickets.status} 
        error={tickets.error}
        statusFilter={ticketStatusFilter}
        onStatusFilterChange={setTicketStatusFilter} />

      <div className={`toast ${toast.show ? "show" : ""} ${toast.kind}`}>{toast.message}</div>

    </div>
  );
}  