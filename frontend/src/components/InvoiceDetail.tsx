import { useEffect, useState } from "react";
import { api } from "../api";
import type { AuditEvent, Extracted, Invoice, LineItem } from "../types";
import StatusBadge from "./StatusBadge";
import { describe } from "./auditText";

interface Props {
  id: number;
  busy: boolean;
  run: (fn: () => Promise<unknown>) => Promise<void>;
}

const HEADER_FIELDS: { key: keyof Extracted; label: string }[] = [
  { key: "vendor_name", label: "Vendor" },
  { key: "invoice_number", label: "Invoice number" },
  { key: "invoice_date", label: "Invoice date (YYYY-MM-DD)" },
  { key: "po_number", label: "PO number" },
  { key: "subtotal", label: "Subtotal" },
  { key: "tax", label: "Tax" },
  { key: "total", label: "Total" },
];

const emptyLine = (): LineItem => ({ sku: "", description: "", quantity: 1, unit_price: "0.00", amount: "0.00" });

export default function InvoiceDetail({ id, busy, run }: Props) {
  const [inv, setInv] = useState<Invoice | null>(null);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [draft, setDraft] = useState<Extracted | null>(null);
  const [note, setNote] = useState("");

  const load = async () => {
    const [i, a] = await Promise.all([api.get(id), api.audit(id)]);
    setInv(i);
    setDraft(structuredClone(i.extracted));
    setAudit(a);
  };

  useEffect(() => {
    load().catch(() => setInv(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  if (!inv || !draft) return <div className="empty"><p>Loading…</p></div>;

  const editable = inv.status === "needs_review";
  const dirty = JSON.stringify(draft) !== JSON.stringify(inv.extracted);
  const act = (fn: () => Promise<Invoice>) =>
    run(async () => {
      await fn();
      setNote("");
      await load();
    });

  const setField = (key: keyof Extracted, value: string) => setDraft({ ...draft, [key]: value || null });
  const setLine = (idx: number, key: keyof LineItem, value: string) => {
    const lines = draft.line_items.map((l, i) =>
      i !== idx ? l : { ...l, [key]: key === "quantity" ? (value === "" ? null : Number(value)) : value || null });
    setDraft({ ...draft, line_items: lines });
  };

  const save = () => {
    const changes: Partial<Extracted> = {};
    HEADER_FIELDS.forEach(({ key }) => {
      if (draft[key] !== inv.extracted[key]) (changes as any)[key] = draft[key];
    });
    if (JSON.stringify(draft.line_items) !== JSON.stringify(inv.extracted.line_items)) changes.line_items = draft.line_items;
    act(() => api.edit(inv.id, changes));
  };

  return (
    <div className="detail">
      <div className="detail-head">
        <div>
          <h2>{inv.extracted.vendor_name ?? "Unknown vendor"} <span className="muted">· {inv.extracted.invoice_number ?? inv.filename}</span></h2>
          <div className="meta">
            <StatusBadge status={inv.status} />
            <span>Invoice #{inv.id}</span>
            <span>File: {inv.filename}</span>
            <span>Extracted by: {inv.extraction_method}</span>
            {inv.processing_ms != null && <span>{inv.processing_ms} ms</span>}
            {inv.vendor_id && <span>Vendor ID: {inv.vendor_id}</span>}
            {inv.erp_document_id && <span>ERP doc: {inv.erp_document_id}</span>}
          </div>
        </div>
      </div>

      {inv.issues.length > 0 ? (
        <div className="issues">
          <h3>{inv.issues.length} issue{inv.issues.length > 1 ? "s" : ""} found</h3>
          {inv.issues.map((i, n) => (
            <div key={n} className={`issue ${i.code === "DUPLICATE" ? "critical" : ""}`}>
              <span className="code">{i.code}</span> {i.message}
            </div>
          ))}
        </div>
      ) : inv.status === "needs_review" ? (
        <div className="issues ok"><h3>All checks pass</h3><p>Ready to approve.</p></div>
      ) : null}

      {inv.extracted.warnings.length > 0 && (
        <p className="warnings">Extractor warnings: {inv.extracted.warnings.join("; ")}</p>
      )}

      <div className="action-bar">
        {editable ? (
          <>
            <input className="note" placeholder={inv.issues.length ? "Note (required to approve with open issues, or to reject)" : "Note (required to reject)"}
              value={note} onChange={(e) => setNote(e.target.value)} />
            <button className="approve" disabled={busy || dirty} onClick={() => act(() => api.approve(inv.id, note))}
              title={dirty ? "Save your corrections first" : ""}>Approve & post to ERP</button>
            <button className="reject" disabled={busy} onClick={() => act(() => api.reject(inv.id, note))}>Reject</button>
            <button disabled={busy} onClick={() => act(() => api.retry(inv.id))}>Retry</button>
          </>
        ) : (
          <>
            {inv.review_note && <span className="muted">Note: "{inv.review_note}"</span>}
            <button disabled={busy} onClick={() => act(() => api.undo(inv.id))}>
              Undo {inv.status === "approved" ? "approval (reverses ERP posting)" : "rejection"}
            </button>
          </>
        )}
      </div>

      <div className="columns">
        <div className="pdf">
          <iframe title="Invoice PDF" src={api.fileUrl(inv.id)} />
        </div>
        <div className="fields">
          <h3>Extracted fields {editable && <span className="muted small">(edit to correct, then save)</span>}</h3>
          <div className="field-grid">
            {HEADER_FIELDS.map(({ key, label }) => (
              <label key={key}>
                <span>{label}</span>
                <input value={(draft[key] as string | null) ?? ""} disabled={!editable}
                  className={draft[key] !== inv.extracted[key] ? "changed" : ""}
                  onChange={(e) => setField(key, e.target.value)} />
              </label>
            ))}
          </div>

          <h3>Line items</h3>
          <table className="lines">
            <thead><tr><th>SKU</th><th>Description</th><th>Qty</th><th>Unit price</th><th>Amount</th>{editable && <th />}</tr></thead>
            <tbody>
              {draft.line_items.map((l, i) => (
                <tr key={i}>
                  {(["sku", "description", "quantity", "unit_price", "amount"] as (keyof LineItem)[]).map((k) => (
                    <td key={k}>
                      {editable ? (
                        <input value={l[k] ?? ""} onChange={(e) => setLine(i, k, e.target.value)}
                          type={k === "quantity" ? "number" : "text"} />
                      ) : (l[k] ?? "—")}
                    </td>
                  ))}
                  {editable && (
                    <td><button className="icon" aria-label="Remove line"
                      onClick={() => setDraft({ ...draft, line_items: draft.line_items.filter((_, j) => j !== i) })}>×</button></td>
                  )}
                </tr>
              ))}
              {!draft.line_items.length && <tr><td colSpan={6} className="muted">No line items extracted</td></tr>}
            </tbody>
          </table>
          {editable && (
            <div className="edit-actions">
              <button onClick={() => setDraft({ ...draft, line_items: [...draft.line_items, emptyLine()] })}>+ Add line</button>
              <button className="primary" disabled={!dirty || busy} onClick={save}>Save corrections & re-check</button>
              {dirty && <button onClick={() => setDraft(structuredClone(inv.extracted))}>Discard</button>}
            </div>
          )}

          <h3>History</h3>
          <ol className="timeline">
            {audit.map((e) => (
              <li key={e.id}>
                <span className="when">{new Date(e.at).toLocaleTimeString()}</span>
                <span className={`who ${e.actor}`}>{e.actor}</span>
                <span>{describe(e)}</span>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </div>
  );
}
