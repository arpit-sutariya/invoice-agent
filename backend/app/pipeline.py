"""The workflow: upload -> extract -> check -> decide -> (post to ERP) -> human review -> undo.

Every path ends in one of three states, and every change writes an audit event:
  approved      checks passed (auto) or a reviewer approved; posted to the ERP
  needs_review  something needs a human; the issues list says what
  rejected      duplicate (auto) or a reviewer rejected
"""
from __future__ import annotations

import time
from pathlib import Path

from sqlalchemy import select

from app.config import Settings
from app.db import AuditEvent, Invoice, utcnow
from app.erp_client import ErpClient, ErpConflict, ErpError, ErpUnavailable
from app.extraction import extract
from app.extraction.normalize import normalize_po, parse_money
from app.matching import run_checks
from app.schemas import EditFields, ExtractedInvoice, Issue


class WorkflowError(Exception):
    """A reviewer action that isn't allowed right now. Carries an HTTP status for the API."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


class InvoiceService:
    def __init__(self, session_factory, erp: ErpClient, settings: Settings):
        self.Session = session_factory
        self.erp = erp
        self.settings = settings

    # ------------------------------------------------------------------ helpers
    def _audit(self, s, inv: Invoice, action: str, actor: str = "system", from_status: str | None = None,
               **details):
        s.add(AuditEvent(invoice_id=inv.id, actor=actor, action=action, from_status=from_status,
                         to_status=inv.status, details=details))

    def _find_duplicate(self, s, exclude_id: int):
        def lookup(vkey: str, ikey: str) -> int | None:
            q = select(Invoice.id).where(Invoice.vendor_key == vkey, Invoice.invoice_key == ikey,
                                         Invoice.id != exclude_id,
                                         Invoice.status.in_(["approved", "needs_review"])).order_by(Invoice.id)
            return s.execute(q).scalars().first()
        return lookup

    def _check(self, s, inv: Invoice, extracted: ExtractedInvoice) -> list[Issue]:
        try:
            res = run_checks(extracted, self.erp, self._find_duplicate(s, inv.id),
                             self.settings.price_tolerance_pct, self.settings.amount_tolerance)
        except ErpUnavailable as e:
            return [Issue(code="ERP_UNAVAILABLE", message=f"Could not reach the ERP: {e}. Use Retry.")]
        inv.vendor_id, inv.vendor_key, inv.invoice_key = res.vendor_id, res.vendor_key, res.invoice_key
        return res.issues

    def _post_to_erp(self, inv: Invoice) -> str:
        ex = ExtractedInvoice(**inv.extracted)
        if not inv.vendor_id or not ex.po_number:
            raise WorkflowError("Can't post to the ERP without a known vendor and PO number. "
                                "Correct the fields or reject the invoice.", 422)
        payload = {"vendor_id": inv.vendor_id, "invoice_number": ex.invoice_number, "po_number": ex.po_number,
                   "total": ex.total or "0",
                   "lines": [{"sku": li.sku, "quantity": li.quantity or 0} for li in ex.line_items if li.sku]}
        return self.erp.post_invoice(payload)["id"]

    def _get(self, s, invoice_id: int) -> Invoice:
        inv = s.get(Invoice, invoice_id)
        if not inv:
            raise WorkflowError(f"Invoice {invoice_id} not found", 404)
        return inv

    # ------------------------------------------------------------------ processing
    def process_file(self, path: Path, filename: str) -> Invoice:
        start = time.perf_counter()
        with self.Session() as s:
            inv = Invoice(filename=filename, file_path=str(path), status="processing")
            s.add(inv)
            s.flush()
            self._audit(s, inv, "uploaded", filename=filename)
            self._run(s, inv)
            inv.processing_ms = int((time.perf_counter() - start) * 1000)
            s.commit()
            return inv

    def _run(self, s, inv: Invoice):
        before = inv.status
        try:
            extracted, method = extract(Path(inv.file_path), self.settings.extractor,
                                        self.settings.anthropic_api_key, self.settings.llm_model)
        except Exception as e:  # never leave an invoice stuck in "processing"
            inv.status, inv.extraction_method, inv.extracted = "needs_review", "error", ExtractedInvoice().model_dump()
            inv.issues = [Issue(code="EXTRACTION_FAILED", message=f"{e.__class__.__name__}: {e}").model_dump()]
            self._audit(s, inv, "extraction_failed", from_status=before, error=str(e))
            return
        inv.extraction_method, inv.extracted = method, extracted.model_dump()
        self._audit(s, inv, "extracted", method=method, warnings=extracted.warnings)

        issues = self._check(s, inv, extracted)
        inv.issues = [i.model_dump() for i in issues]
        codes = [i.code for i in issues]

        if "DUPLICATE" in codes:
            inv.status = "rejected"
            self._audit(s, inv, "auto_rejected", from_status=before, issues=codes)
        elif not issues and self.settings.auto_approve:
            try:
                inv.erp_document_id = self._post_to_erp(inv)
                inv.status = "approved"
                self._audit(s, inv, "auto_approved", from_status=before, erp_document_id=inv.erp_document_id)
            except ErpConflict as e:
                inv.status = "rejected"
                inv.issues = [Issue(code="DUPLICATE", message=f"ERP says: {e}").model_dump()]
                self._audit(s, inv, "auto_rejected", from_status=before, issues=["DUPLICATE"])
            except ErpError as e:
                inv.status = "needs_review"
                inv.issues = [Issue(code="ERP_UNAVAILABLE", message=f"Checks passed but posting failed: {e}. "
                                    "Use Retry.").model_dump()]
                self._audit(s, inv, "flagged", from_status=before, issues=["ERP_UNAVAILABLE"])
        else:
            inv.status = "needs_review"
            self._audit(s, inv, "flagged", from_status=before, issues=codes)

    # ------------------------------------------------------------------ reviewer actions
    def approve(self, invoice_id: int, note: str | None) -> Invoice:
        with self.Session() as s:
            inv = self._get(s, invoice_id)
            if inv.status != "needs_review":
                raise WorkflowError(f"Only invoices in review can be approved (this one is {inv.status})")
            open_issues = [i["code"] for i in inv.issues]
            if open_issues and not (note and note.strip()):
                raise WorkflowError("This invoice still has open issues. Add a note explaining why you're "
                                    "approving it anyway.", 422)
            try:
                inv.erp_document_id = self._post_to_erp(inv)
            except ErpConflict as e:
                raise WorkflowError(f"The ERP already has this invoice: {e}", 409)
            except ErpError as e:
                raise WorkflowError(f"Could not post to the ERP: {e}", 503)
            inv.status, inv.review_note = "approved", note
            self._audit(s, inv, "approved", actor="reviewer", from_status="needs_review", note=note,
                        overridden_issues=open_issues, erp_document_id=inv.erp_document_id)
            s.commit()
            return inv

    def reject(self, invoice_id: int, note: str | None) -> Invoice:
        with self.Session() as s:
            inv = self._get(s, invoice_id)
            if inv.status != "needs_review":
                raise WorkflowError(f"Only invoices in review can be rejected (this one is {inv.status})")
            if not (note and note.strip()):
                raise WorkflowError("Add a note saying why the invoice is rejected.", 422)
            inv.status, inv.review_note = "rejected", note
            self._audit(s, inv, "rejected", actor="reviewer", from_status="needs_review", note=note)
            s.commit()
            return inv

    def undo(self, invoice_id: int) -> Invoice:
        """Send an approved or rejected invoice back to review. Approvals are reversed in the ERP."""
        with self.Session() as s:
            inv = self._get(s, invoice_id)
            before = inv.status
            if before == "approved":
                if inv.erp_document_id:
                    try:
                        self.erp.reverse_invoice(inv.erp_document_id)
                    except ErpError as e:
                        raise WorkflowError(f"Could not reverse {inv.erp_document_id} in the ERP: {e}", 503)
                reversed_doc, inv.erp_document_id = inv.erp_document_id, None
                inv.status = "needs_review"
                self._audit(s, inv, "undo_approval", actor="reviewer", from_status=before,
                            reversed_erp_document_id=reversed_doc)
            elif before == "rejected":
                inv.status = "needs_review"
                self._audit(s, inv, "undo_rejection", actor="reviewer", from_status=before)
            else:
                raise WorkflowError("Only approved or rejected invoices can be undone")
            inv.review_note = None
            s.commit()
            return inv

    def edit(self, invoice_id: int, changes: EditFields) -> Invoice:
        """Reviewer corrects extracted fields; the checks run again on the corrected data."""
        with self.Session() as s:
            inv = self._get(s, invoice_id)
            if inv.status != "needs_review":
                raise WorkflowError("Only invoices in review can be edited")
            current = ExtractedInvoice(**inv.extracted)
            updates = changes.model_dump(exclude_unset=True)
            updates.pop("line_items", None)
            if updates.get("po_number"):
                updates["po_number"] = normalize_po(updates["po_number"]) or updates["po_number"].strip()
            for f in ("subtotal", "tax", "total"):
                if updates.get(f):
                    updates[f] = parse_money(updates[f]) or updates[f]
            diff = {k: {"from": getattr(current, k), "to": v} for k, v in updates.items() if getattr(current, k) != v}
            corrected = current.model_copy(update=updates)
            if changes.line_items is not None:
                corrected.line_items = changes.line_items
                diff["line_items"] = {"from": f"{len(current.line_items)} lines", "to": f"{len(changes.line_items)} lines"}
            corrected.has_text = True
            inv.extracted = corrected.model_dump()
            issues = self._check(s, inv, corrected)
            inv.issues = [i.model_dump() for i in issues]
            self._audit(s, inv, "edited", actor="reviewer", from_status="needs_review", changes=diff,
                        issues_after=[i.code for i in issues])
            s.commit()
            return inv

    def retry(self, invoice_id: int) -> Invoice:
        """Re-run extraction and checks, e.g. after the ERP was down."""
        with self.Session() as s:
            inv = self._get(s, invoice_id)
            if inv.status != "needs_review":
                raise WorkflowError("Only invoices in review can be retried")
            self._audit(s, inv, "retry_requested", actor="reviewer", from_status=inv.status)
            self._run(s, inv)
            inv.updated_at = utcnow()
            s.commit()
            return inv
