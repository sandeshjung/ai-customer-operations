export function Badge({ kind, value }) {
  if (!value) return <span className="badge">—</span>;
  return <span className={`badge ${kind}-${value}`}>{value.replace("_", " ")}</span>;
}
