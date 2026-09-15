import { useState } from "react";

const MAX_COUNT = 20;

export function PublishDelayedOrders({ onPublish }) {
  const [count, setCount] = useState(3);
  const [pending, setPending] = useState(false);

  async function handleClick() {
    setPending(true);
    try {
      await onPublish(count);
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="publish-control">
      <input
        className="mono publish-count"
        type="number"
        min={1}
        max={MAX_COUNT}
        value={count}
        disabled={pending}
        onChange={(e) => {
          const next = Number(e.target.value);
          if (Number.isNaN(next)) return;
          setCount(Math.min(MAX_COUNT, Math.max(1, next)));
        }}
      />
      <button className="ghost" disabled={pending} onClick={handleClick}>
        {pending ? `Publishing… (~${count * 5}s)` : `Publish ${count} to event stream`}
      </button>
    </div>
  );
}
