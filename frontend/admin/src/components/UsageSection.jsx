import { useEffect, useMemo, useState } from "react";
import { jaegerTraceUrl } from "../api";
import { formatCost, formatDuration, formatNumber, relativeTime } from "../format";

const PAGE_SIZE = 10;

function StatTile({ label, value, hint }) {
  return (
    <div className="stat-tile">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
      {hint && <div className="stat-hint">{hint}</div>}
    </div>
  );
}

export function UsageSection({ usage, status, error }) {
  const summary = usage?.summary;
  const byAgent = usage?.by_agent || [];
  const recent = usage?.recent || [];

  const [page, setPage] = useState(1);

  useEffect(() => {
    setPage(1);
  }, [recent.length]);

  const totalPages = Math.max(1, Math.ceil(recent.length / PAGE_SIZE));

  useEffect(() => {
    setPage((current) => Math.min(current, totalPages));
  }, [totalPages]);

  const visible = useMemo(
    () => recent.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE),
    [recent, page],
  );

  return (
    <section>
      <div className="section-head">
        <div className="section-head-title">
          <h2>AI usage</h2>
          <span className="count">
            {status === "ready" ? `${summary?.total_executions ?? 0} runs` : "—"}
          </span>
        </div>
      </div>

      {status === "loading" && <div className="loading">Loading…</div>}

      {status === "error" && <div className="error">Couldn't load usage — {error}</div>}

      {status === "ready" && summary && summary.total_executions === 0 && (
        <div className="empty">No agent runs recorded yet.</div>
      )}

      {status === "ready" && summary && summary.total_executions > 0 && (
        <>
          <div className="stat-grid">
            <StatTile label="Total tokens" value={formatNumber(summary.total_tokens)} />
            <StatTile label="LLM calls" value={formatNumber(summary.total_llm_calls)} />
            <StatTile
              label="Estimated cost"
              value={formatCost(summary.total_cost_usd)}
              hint={summary.cost_incomplete ? "some models unpriced" : null}
            />
            <StatTile label="Agent runs" value={formatNumber(summary.total_executions)} />
          </div>

          <div className="panel" style={{ marginTop: 14 }}>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Agent</th>
                    <th>Model</th>
                    <th>Runs</th>
                    <th>Tokens</th>
                    <th>Avg duration</th>
                    <th>Est. cost</th>
                  </tr>
                </thead>
                <tbody>
                  {byAgent.map((row) => (
                    <tr key={`${row.agent_name}-${row.model}`}>
                      <td>{row.agent_name}</td>
                      <td className="mono">{row.model || "—"}</td>
                      <td>{formatNumber(row.executions)}</td>
                      <td>{formatNumber(row.total_tokens)}</td>
                      <td>{formatDuration(row.avg_duration_ms)}</td>
                      <td>{formatCost(row.cost_usd)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="panel" style={{ marginTop: 14 }}>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Agent</th>
                    <th>Tokens (in/out)</th>
                    <th>Calls</th>
                    <th>Duration</th>
                    <th>Est. cost</th>
                    <th>Trace</th>
                    <th>Ran</th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((run) => {
                    const traceUrl = jaegerTraceUrl(run.trace_id);
                    return (
                      <tr key={run.id}>
                        <td>{run.agent_name}</td>
                        <td>
                          {formatNumber(run.input_tokens)} / {formatNumber(run.output_tokens)}
                        </td>
                        <td>{formatNumber(run.llm_call_count)}</td>
                        <td>{formatDuration(run.duration_ms)}</td>
                        <td>{formatCost(run.cost_usd)}</td>
                        <td>
                          {traceUrl ? (
                            <a className="trace-link" href={traceUrl} target="_blank" rel="noreferrer">
                              trace
                            </a>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td>{relativeTime(run.created_at)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {totalPages > 1 && (
              <div className="pagination" aria-label="Recent AI runs pagination">
                <button
                  type="button"
                  className="page-button"
                  disabled={page === 1}
                  onClick={() => setPage((current) => Math.max(1, current - 1))}
                >
                  Prev
                </button>

                <div className="page-indicator">
                  Page {page} of {totalPages}
                </div>

                <button
                  type="button"
                  className="page-button"
                  disabled={page === totalPages}
                  onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
                >
                  Next
                </button>
              </div>
            )}
          </div>
        </>
      )}
    </section>
  );
}
