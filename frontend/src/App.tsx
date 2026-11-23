import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import type { Health, Invoice, Stats } from "./types";
import InvoiceList from "./components/InvoiceList";
import InvoiceDetail from "./components/InvoiceDetail";
import ActivityLog from "./components/ActivityLog";

const FILTERS = [
  { key: "", label: "All" },
  { key: "needs_review", label: "Needs review" },
  { key: "approved", label: "Approved" },
  { key: "rejected", label: "Rejected" },
];

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [filter, setFilter] = useState("needs_review");
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [view, setView] = useState<"review" | "activity">("review");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    try {
      const [h, s, list] = await Promise.all([api.health(), api.stats(), api.list(filter || undefined)]);
      setHealth(h);
      setStats(s);
      setInvoices(list);
    } catch (e) {
      setError(`Can't reach the backend on port 8000. Is it running? (${(e as Error).message})`);
    }
  }, [filter]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const onUpload = (files: FileList | null) => {
    if (!files?.length) return;
    run(async () => {
      const created = await api.upload(files);
      if (created.length) setSelectedId(created[0].id);
    });
  };

  const count = (k: string) => (k ? stats?.by_status[k as keyof Stats["by_status"]] ?? 0 : stats?.total ?? 0);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo">▤</span> Invoice Agent
        </div>
        <nav className="tabs">
          <button className={view === "review" ? "active" : ""} onClick={() => setView("review")}>Review queue</button>
          <button className={view === "activity" ? "active" : ""} onClick={() => setView("activity")}>Activity log</button>
        </nav>
        <div className="health">
          {health && (
            <>
              <span className={`dot ${health.erp_reachable ? "ok" : "bad"}`} />
              ERP {health.erp_reachable ? "connected" : "unreachable"}
              <span className="sep">·</span>
              Extractor: {health.extractor}
              {health.extractor !== "rules" && !health.llm_enabled && " (no API key: rules only)"}
            </>
          )}
        </div>
      </header>

      {error && (
        <div className="error-banner" role="alert">
          {error}
          <button onClick={() => setError(null)} aria-label="Dismiss">×</button>
        </div>
      )}

      {view === "activity" ? (
        <ActivityLog onOpen={(id) => { setSelectedId(id); setFilter(""); setView("review"); }} />
      ) : (
        <main className="layout">
          <aside className="sidebar">
            <div className="actions">
              <button className="primary" disabled={busy} onClick={() => fileInput.current?.click()}>
                Upload PDFs
              </button>
              <button disabled={busy} onClick={() => run(() => api.loadSamples(20))}>
                Load 20 sample invoices
              </button>
              <input ref={fileInput} type="file" accept="application/pdf" multiple hidden
                onChange={(e) => { onUpload(e.target.files); e.target.value = ""; }} />
            </div>
            <div className="filters">
              {FILTERS.map((f) => (
                <button key={f.key} className={filter === f.key ? "active" : ""} onClick={() => setFilter(f.key)}>
                  {f.label} <span className="count">{count(f.key)}</span>
                </button>
              ))}
            </div>
            <InvoiceList invoices={invoices} selectedId={selectedId} onSelect={setSelectedId} />
          </aside>
          <section className="content">
            {selectedId ? (
              <InvoiceDetail key={selectedId} id={selectedId} busy={busy} run={run} />
            ) : (
              <div className="empty">
                <h2>No invoice selected</h2>
                <p>Upload PDFs or load the sample invoices, then pick one from the list.</p>
              </div>
            )}
          </section>
        </main>
      )}
    </div>
  );
}
