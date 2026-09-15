import { useState } from "react";

export function LookupForm({ onSubmit, submitting }) {
  const [orderId, setOrderId] = useState("");
  const [email, setEmail] = useState("");

  function handleSubmit(e) {
    e.preventDefault();
    const trimmedId = orderId.trim();
    const trimmedEmail = email.trim();
    if (!trimmedId || !trimmedEmail) return;
    onSubmit(trimmedId, trimmedEmail);
  }

  return (
    <form className="lookup-form" onSubmit={handleSubmit}>
      <div className="field">
        <label htmlFor="orderId">Order number</label>
        <input
          id="orderId"
          type="text"
          inputMode="numeric"
          placeholder="e.g. 1042"
          value={orderId}
          onChange={(e) => setOrderId(e.target.value)}
          autoComplete="off"
        />
      </div>
      <div className="field">
        <label htmlFor="email">Email on the order</label>
        <input
          id="email"
          type="email"
          placeholder="you@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="email"
        />
      </div>
      <button type="submit" disabled={submitting}>
        {submitting ? "Looking up…" : "Find my order"}
      </button>
    </form>
  );
}
