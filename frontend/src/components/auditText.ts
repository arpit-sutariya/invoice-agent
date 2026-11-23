import type { AuditEvent } from "../types";

/** Turns an audit event into one readable sentence. */
export function describe(e: AuditEvent): string {
  const d = e.details as Record<string, any>;
  switch (e.action) {
    case "uploaded": return `Uploaded ${d.filename}`;
    case "extracted": return `Fields extracted (${d.method})${d.warnings?.length ? `: ${d.warnings.join("; ")}` : ""}`;
    case "extraction_failed": return `Extraction crashed: ${d.error}`;
    case "flagged": return `Sent to review: ${(d.issues ?? []).join(", ") || "no issues"}`;
    case "auto_approved": return `Auto-approved, posted to ERP as ${d.erp_document_id}`;
    case "auto_rejected": return `Auto-rejected: ${(d.issues ?? []).join(", ")}`;
    case "approved":
      return `Approved and posted as ${d.erp_document_id}` +
        (d.overridden_issues?.length ? `, overriding ${d.overridden_issues.join(", ")}` : "") +
        (d.note ? `. Note: "${d.note}"` : "");
    case "rejected": return `Rejected. Note: "${d.note}"`;
    case "undo_approval": return `Approval undone; ERP document ${d.reversed_erp_document_id ?? "—"} reversed`;
    case "undo_rejection": return "Rejection undone";
    case "edited": {
      const fields = Object.keys(d.changes ?? {});
      return `Corrected ${fields.length ? fields.join(", ") : "nothing"}; checks re-run: ${(d.issues_after ?? []).join(", ") || "all passed"}`;
    }
    case "retry_requested": return "Retry requested";
    default: return e.action;
  }
}
