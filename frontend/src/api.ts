import type { AuditEvent, Extracted, Health, Invoice, Stats } from "./types";

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, init);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    throw new Error(detail || `Request failed (${res.status})`);
  }
  return body as T;
}

const json = (method: string, data: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(data),
});

export const api = {
  health: () => call<Health>("/health"),
  stats: () => call<Stats>("/stats"),
  list: (status?: string) => call<Invoice[]>(`/invoices${status ? `?status=${status}` : ""}`),
  get: (id: number) => call<Invoice>(`/invoices/${id}`),
  audit: (id: number) => call<AuditEvent[]>(`/invoices/${id}/audit`),
  allAudit: () => call<AuditEvent[]>("/audit"),
  upload: (files: FileList) => {
    const form = new FormData();
    Array.from(files).forEach((f) => form.append("files", f));
    return call<Invoice[]>("/invoices", { method: "POST", body: form });
  },
  loadSamples: (count: number) =>
    call<{ processed: number }>(`/demo/load-samples?count=${count}`, { method: "POST" }),
  edit: (id: number, fields: Partial<Extracted>) => call<Invoice>(`/invoices/${id}`, json("PATCH", fields)),
  approve: (id: number, note: string) => call<Invoice>(`/invoices/${id}/approve`, json("POST", { note })),
  reject: (id: number, note: string) => call<Invoice>(`/invoices/${id}/reject`, json("POST", { note })),
  undo: (id: number) => call<Invoice>(`/invoices/${id}/undo`, { method: "POST" }),
  retry: (id: number) => call<Invoice>(`/invoices/${id}/retry`, { method: "POST" }),
  fileUrl: (id: number) => `/api/invoices/${id}/file#navpanes=0&view=FitH`,
};
