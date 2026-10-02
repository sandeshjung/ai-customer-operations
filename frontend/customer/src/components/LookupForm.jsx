import { useState } from "react";

export function LookupForm({ onSubmit, submitting }) {
  const [orderId, setOrderId] = useState("");

  function handleSubmit(e) {
    e.preventDefault();
    const trimmedId = orderId.trim();
    if (!trimmedId) return;
    onSubmit(trimmedId);
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
      <button type="submit" disabled={submitting}>
        {submitting ? "Looking up…" : "Find my order"}
      </button>
    </form>
  );
}
