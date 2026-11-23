import { useEffect, useState } from "react";
import { api } from "../api";
import type { AuditEvent } from "../types";
import { describe } from "./auditText";

export default function ActivityLog({ onOpen }: { onOpen: (invoiceId: number) => void }) {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  useEffect(() => {
    api.allAudit().then(setEvents).catch(() => setEvents([]));
  }, []);

  return (
    <div className="activity">
      <h2>Activity log</h2>
      <p className="muted">Every automatic decision and reviewer action, newest first.</p>
      <table>
        <thead>
          <tr><th>Time</th><th>Invoice</th><th>Who</th><th>What happened</th><th>Status</th></tr>
        </thead>
        <tbody>
          {events.map((e) => (
            <tr key={e.id}>
              <td className="nowrap">{new Date(e.at).toLocaleString()}</td>
              <td><button className="link" onClick={() => onOpen(e.invoice_id)}>#{e.invoice_id}</button></td>
              <td>{e.actor}</td>
              <td>{describe(e)}</td>
              <td className="nowrap muted">{e.from_status && e.from_status !== e.to_status ? `${e.from_status} → ${e.to_status}` : e.to_status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
