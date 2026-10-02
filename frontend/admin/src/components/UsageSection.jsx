import { Fragment, useEffect, useMemo, useState } from "react";
import { jaegerTraceUrl } from "../api";
import { formatCost, formatDuration, formatNumber, relativeTime } from "../format";
import { Chevron } from "./Chevron";

const PAGE_SIZE = 10;

const AGENT_LABELS = {
  delayed_order_agent: "Delayed-order agent",
  triage_agent: "Triage agent",
};

function StatTile({ label, value, hint, hintTone = "warn" }) {
  return (
    <div className="stat-tile">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
      {hint && <div className={`stat-hint ${hintTone === "muted" ? "muted" : ""}`}>{hint}</div>}
    </div>
  );
}

function taskLabel(task) {
  if (task.kind === "delayed_order") {
    return task.order_id ? `Delayed order #${task.order_id}` : "Delayed order";
  }
  const ticket = task.ticket_id ? `ticket #${task.ticket_id}` : "ticket";
  return `Customer complaint · ${ticket}`;
}

function TaskCost({ cost, incomplete }) {
  return (
    <>
      {formatCost(cost)}
      {incomplete && cost !== null && (
        <span className="cost-flag" title="Some runs used an unpriced model">
          +
        </span>
      )}
    </>
  );
}

export function UsageSection({ usage, status, error }) {
  const summary = usage?.summary;
  const byAgent = usage?.by_agent || [];
  const tasks = usage?.tasks || [];

  const [page, setPage] = useState(1);
  const [expanded, setExpanded] = useState({});

  useEffect(() => {
    setPage(1);
  }, [tasks.length]);

  const totalPages = Math.max(1, Math.ceil(tasks.length / PAGE_SIZE));

  useEffect(() => {
    setPage((current) => Math.min(current, totalPages));
  }, [totalPages]);

  const visible = useMemo(
    () => tasks.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE),
    [tasks, page],
  );

  function toggle(taskId) {
    setExpanded((current) => ({ ...current, [taskId]: !current[taskId] }));
  }

  return (
    <section>
      <div className="section-head">
        <div className="section-head-title">
          <h2>AI usage</h2>
          <span className="count">
            {status === "ready" ? `${tasks.length} tasks` : "—"}
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
            <StatTile
              label="Agent runs"
              value={formatNumber(summary.total_executions)}
              hint={`across ${formatNumber(tasks.length)} tasks`}
              hintTone="muted"
            />
          </div>

          <h3 className="sub-head">Per task</h3>
          <div className="panel">
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Task</th>
                    <th>Agents</th>
                    <th>Tokens</th>
                    <th>LLM calls</th>
                    <th>Duration</th>
                    <th>Est. cost</th>
                    <th>Started</th>
                    <th className="col-details" aria-hidden="true"></th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((task) => {
                    const isExpanded = !!expanded[task.task_id];
                    return (
                      <Fragment key={task.task_id}>
                        <tr className="row-clickable" onClick={() => toggle(task.task_id)}>
                          <td className="subject">{taskLabel(task)}</td>
                          <td>{task.runs.length}</td>
                          <td>{formatNumber(task.total_tokens)}</td>
                          <td>{formatNumber(task.llm_call_count)}</td>
                          <td>{formatDuration(task.duration_ms)}</td>
                          <td>
                            <TaskCost cost={task.cost_usd} incomplete={task.cost_incomplete} />
                          </td>
                          <td>{relativeTime(task.started_at)}</td>
                          <td>
                            <button
                              className="collapse-toggle"
                              type="button"
                              aria-expanded={isExpanded}
                              aria-label={isExpanded ? "Hide agent runs" : "Show agent runs"}
                              onClick={(e) => {
                                e.stopPropagation();
                                toggle(task.task_id);
                              }}
                            >
                              <Chevron />
                            </button>
                          </td>
                        </tr>
                        {isExpanded && (
                          <tr className="detail-row">
                            <td colSpan={8}>
                              <TaskRuns runs={task.runs} />
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {totalPages > 1 && (
              <div className="pagination" aria-label="Tasks pagination">
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

          <h3 className="sub-head">By agent and model</h3>
          <div className="panel">
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
        </>
      )}
    </section>
  );
}

function TaskRuns({ runs }) {
  return (
    <div className="task-runs">
      {runs.map((run, i) => {
        const traceUrl = jaegerTraceUrl(run.trace_id);
        return (
          <div className="task-run" key={run.id}>
            <span className="task-run-step">{i + 1}</span>
            <div className="task-run-body">
              <div className="task-run-head">
                <strong>{AGENT_LABELS[run.agent_name] || run.agent_name}</strong>
                <span className="mono">{run.model || "unknown model"}</span>
                <span>{relativeTime(run.created_at)}</span>
                {traceUrl && (
                  <a className="trace-link" href={traceUrl} target="_blank" rel="noreferrer">
                    View trace ↗
                  </a>
                )}
              </div>
              <div className="task-run-stats">
                <span>
                  <span className="detail-label">Tokens in / out</span>
                  {formatNumber(run.input_tokens)} / {formatNumber(run.output_tokens)}
                </span>
                <span>
                  <span className="detail-label">LLM calls</span>
                  {formatNumber(run.llm_call_count)}
                </span>
                <span>
                  <span className="detail-label">Duration</span>
                  {formatDuration(run.duration_ms)}
                </span>
                <span>
                  <span className="detail-label">Est. cost</span>
                  {formatCost(run.cost_usd)}
                </span>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
