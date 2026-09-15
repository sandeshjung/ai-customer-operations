import { useState } from "react";
import { api, getApiBase, setApiBase } from "./api";
import { LookupForm } from "./components/LookupForm";
import { OrderDetails } from "./components/OrderDetails";
import { TicketsList } from "./components/TicketsList";

const GENERIC_ERROR = "We couldn't find an order with that ID and email. Double-check both and try again.";

export default function App() {
  const [status, setStatus] = useState("idle"); // idle | loading | ready | error
  const [order, setOrder] = useState(null);
  const [tickets, setTickets] = useState([]);
  const [errorMessage, setErrorMessage] = useState("");
  const [showSettings, setShowSettings] = useState(false);
  const [apiBaseValue, setApiBaseValue] = useState(getApiBase());

  async function handleLookup(orderId, email) {
    setStatus("loading");
    setErrorMessage("");

    try {
      const foundOrder = await api.lookupOrder(orderId, email);
      setOrder(foundOrder);

      try {
        const foundTickets = await api.ticketsForCustomer(foundOrder.customer_id);
        setTickets(foundTickets);
      } catch {
        setTickets([]);
      }

      setStatus("ready");
    } catch {
      setOrder(null);
      setTickets([]);
      setErrorMessage(GENERIC_ERROR);
      setStatus("error");
    }
  }

  function handleStartOver() {
    setStatus("idle");
    setOrder(null);
    setTickets([]);
    setErrorMessage("");
  }

  function handleApiBaseChange(value) {
    setApiBaseValue(value);
    setApiBase(value);
  }

  return (
    <div className="page">
      <header className="hero">
        <h1>Track your order</h1>
        <p>Enter your order number and the email you used to place it.</p>
      </header>

      <main className="content">
        {status !== "ready" && (
          <div className="card lookup-card">
            <LookupForm onSubmit={handleLookup} submitting={status === "loading"} />
            {status === "error" && <p className="error-message">{errorMessage}</p>}
          </div>
        )}

        {status === "ready" && order && (
          <div className="results">
            <button className="link-button" onClick={handleStartOver}>
              ← Look up a different order
            </button>
            <OrderDetails order={order} />
            <TicketsList tickets={tickets} />
          </div>
        )}
      </main>

      <footer className="footer">
        <button className="link-button muted small" onClick={() => setShowSettings((v) => !v)}>
          {showSettings ? "Hide connection settings" : "Connection settings"}
        </button>
        {showSettings && (
          <div className="settings-row">
            <label htmlFor="apiBase">API base URL</label>
            <input
              id="apiBase"
              className="mono"
              spellCheck={false}
              value={apiBaseValue}
              onChange={(e) => handleApiBaseChange(e.target.value)}
            />
          </div>
        )}
      </footer>
    </div>
  );
}
