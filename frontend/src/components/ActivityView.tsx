import { useEffect, useState } from "react";
import { api } from "../api";
import type { AuditEntry } from "../api";
import { describeThrown } from "../lib/errors";

export default function ActivityView() {
  const [entries, setEntries] = useState<AuditEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api.audit().then(setEntries).catch((e) => setError(describeThrown(e)));
  }, []);
  if (error) return <p className="error">{error}</p>;
  if (!entries) return <p className="muted">Loading...</p>;
  return (
    <section>
      <h2>Activity</h2>
      <p className="muted">An append-only record of changes. There are no user accounts yet, so it doesn't say who.</p>
      <table>
        <thead><tr><th>When</th><th>What</th><th>About</th><th>Details</th></tr></thead>
        <tbody>
          {entries.map((e) => (
            <tr key={e.id}>
              <td>{e.at ? new Date(e.at).toLocaleString() : ""}</td>
              <td>{e.action}</td>
              <td>{e.entity_type} {e.entity_id}</td>
              <td><code>{JSON.stringify(e.details)}</code></td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
