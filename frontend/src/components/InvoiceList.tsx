import type { Invoice } from "../types";
import StatusBadge from "./StatusBadge";

interface Props {
  invoices: Invoice[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}

export default function InvoiceList({ invoices, selectedId, onSelect }: Props) {
  if (!invoices.length) return <p className="muted pad">Nothing here yet.</p>;
  return (
    <ul className="invoice-list">
      {invoices.map((inv) => (
        <li key={inv.id}>
          <button className={inv.id === selectedId ? "selected" : ""} onClick={() => onSelect(inv.id)}>
            <div className="row1">
              <span className="vendor">{inv.extracted.vendor_name ?? inv.filename}</span>
              <span className="amount">{inv.extracted.total ? `$${Number(inv.extracted.total).toLocaleString(undefined, { minimumFractionDigits: 2 })}` : "—"}</span>
            </div>
            <div className="row2">
              <span className="muted">#{inv.id} · {inv.extracted.invoice_number ?? inv.filename}</span>
              <StatusBadge status={inv.status} />
            </div>
            {inv.issues.length > 0 && (
              <div className="codes">
                {inv.issues.map((i) => <span key={i.code} className="code">{i.code}</span>)}
              </div>
            )}
          </button>
        </li>
      ))}
    </ul>
  );
}
