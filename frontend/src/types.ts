export type Status = "processing" | "approved" | "needs_review" | "rejected";

export interface LineItem {
  sku: string | null;
  description: string | null;
  quantity: number | null;
  unit_price: string | null;
  amount: string | null;
}

export interface Extracted {
  vendor_name: string | null;
  invoice_number: string | null;
  invoice_date: string | null;
  po_number: string | null;
  currency: string | null;
  subtotal: string | null;
  tax: string | null;
  total: string | null;
  line_items: LineItem[];
  has_text: boolean;
  warnings: string[];
}

export interface Issue {
  code: string;
  message: string;
  details: Record<string, unknown>;
}

export interface Invoice {
  id: number;
  filename: string;
  status: Status;
  extraction_method: string | null;
  extracted: Extracted;
  issues: Issue[];
  vendor_id: string | null;
  erp_document_id: string | null;
  processing_ms: number | null;
  review_note: string | null;
  created_at: string;
  updated_at: string;
}

export interface AuditEvent {
  id: number;
  invoice_id: number;
  at: string;
  actor: string;
  action: string;
  from_status: string | null;
  to_status: string | null;
  details: Record<string, unknown>;
}

export interface Health {
  ok: boolean;
  erp_reachable: boolean;
  extractor: string;
  llm_enabled: boolean;
  auto_approve: boolean;
}

export interface Stats {
  by_status: Partial<Record<Status, number>>;
  total: number;
  issues: Record<string, number>;
}
