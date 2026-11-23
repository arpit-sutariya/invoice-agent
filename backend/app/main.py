"""HTTP API for the review UI.

Run from backend/:  uvicorn app.main:app --port 8000 --reload
Docs:               http://localhost:8000/docs
"""
from __future__ import annotations

import shutil
import uuid
from collections import Counter

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import func, select

from app.config import Settings, settings as default_settings
from app.db import AuditEvent, Invoice, make_session_factory
from app.erp_client import ErpClient
from app.matching import ISSUE_CODES
from app.pipeline import InvoiceService, WorkflowError
from app.schemas import AuditOut, EditFields, InvoiceOut, ReviewAction


def to_out(inv: Invoice) -> InvoiceOut:
    return InvoiceOut(id=inv.id, filename=inv.filename, status=inv.status,
                      extraction_method=inv.extraction_method, extracted=inv.extracted, issues=inv.issues,
                      vendor_id=inv.vendor_id, erp_document_id=inv.erp_document_id,
                      processing_ms=inv.processing_ms, review_note=inv.review_note,
                      created_at=inv.created_at.isoformat(), updated_at=inv.updated_at.isoformat())


def audit_out(e: AuditEvent) -> AuditOut:
    return AuditOut(id=e.id, invoice_id=e.invoice_id, at=e.at.isoformat(), actor=e.actor, action=e.action,
                    from_status=e.from_status, to_status=e.to_status, details=e.details or {})


def create_app(settings: Settings = default_settings, erp: ErpClient | None = None) -> FastAPI:
    app = FastAPI(title="Invoice Agent", version="1.0")
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"],
                       allow_headers=["*"])
    Session = make_session_factory(settings.database_url)
    erp = erp or ErpClient.from_url(settings.erp_base_url, settings.erp_timeout_s, settings.erp_retries)
    svc = InvoiceService(Session, erp, settings)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)

    @app.exception_handler(WorkflowError)
    async def workflow_error(_: Request, exc: WorkflowError):
        return JSONResponse({"detail": str(exc)}, status_code=exc.status_code)

    @app.get("/api/health")
    def health():
        return {"ok": True, "erp_reachable": erp.health(), "extractor": settings.extractor,
                "llm_enabled": bool(settings.anthropic_api_key), "auto_approve": settings.auto_approve}

    @app.get("/api/issue-codes")
    def issue_codes():
        return ISSUE_CODES

    @app.get("/api/stats")
    def stats():
        with Session() as s:
            rows = s.execute(select(Invoice.status, func.count()).group_by(Invoice.status)).all()
            counts = {status: n for status, n in rows}
            issues = Counter(i["code"] for inv in s.execute(select(Invoice)).scalars() for i in inv.issues)
        return {"by_status": counts, "total": sum(counts.values()), "issues": dict(issues)}

    @app.post("/api/invoices")
    def upload(files: list[UploadFile] = File(...)):
        out = []
        for f in files:
            if not (f.filename or "").lower().endswith(".pdf"):
                raise HTTPException(400, f"{f.filename}: only PDF files are supported")
            dest = settings.upload_dir / f"{uuid.uuid4().hex[:8]}_{f.filename}"
            with dest.open("wb") as fh:
                shutil.copyfileobj(f.file, fh)
            out.append(to_out(svc.process_file(dest, f.filename)))
        return out

    @app.post("/api/demo/load-samples")
    def load_samples(count: int = Query(20, ge=1, le=100)):
        """Feed the first N invoices from the generated dataset through the pipeline."""
        files = sorted(settings.sample_dir.glob("*.pdf"))[:count]
        if not files:
            raise HTTPException(404, "No sample invoices. Run: python -m scripts.generate_dataset")
        results = []
        for f in files:
            dest = settings.upload_dir / f"{uuid.uuid4().hex[:8]}_{f.name}"
            shutil.copy(f, dest)
            results.append(to_out(svc.process_file(dest, f.name)))
        return {"processed": len(results), "by_status": Counter(r.status for r in results)}

    @app.get("/api/invoices")
    def list_invoices(status: str | None = None):
        with Session() as s:
            q = select(Invoice).order_by(Invoice.id.desc())
            if status:
                q = q.where(Invoice.status == status)
            return [to_out(i) for i in s.execute(q).scalars()]

    @app.get("/api/invoices/{invoice_id}")
    def get_invoice(invoice_id: int):
        with Session() as s:
            inv = s.get(Invoice, invoice_id)
            if not inv:
                raise HTTPException(404, "Invoice not found")
            return to_out(inv)

    @app.get("/api/invoices/{invoice_id}/file")
    def get_file(invoice_id: int):
        with Session() as s:
            inv = s.get(Invoice, invoice_id)
            if not inv:
                raise HTTPException(404, "Invoice not found")
            return FileResponse(inv.file_path, media_type="application/pdf",
                                headers={"Content-Disposition": f'inline; filename="{inv.filename}"'})

    @app.get("/api/invoices/{invoice_id}/audit")
    def invoice_audit(invoice_id: int):
        with Session() as s:
            q = select(AuditEvent).where(AuditEvent.invoice_id == invoice_id).order_by(AuditEvent.id)
            return [audit_out(e) for e in s.execute(q).scalars()]

    @app.get("/api/audit")
    def all_audit(limit: int = 200):
        with Session() as s:
            q = select(AuditEvent).order_by(AuditEvent.id.desc()).limit(limit)
            return [audit_out(e) for e in s.execute(q).scalars()]

    @app.patch("/api/invoices/{invoice_id}")
    def edit(invoice_id: int, body: EditFields):
        return to_out(svc.edit(invoice_id, body))

    @app.post("/api/invoices/{invoice_id}/approve")
    def approve(invoice_id: int, body: ReviewAction):
        return to_out(svc.approve(invoice_id, body.note))

    @app.post("/api/invoices/{invoice_id}/reject")
    def reject(invoice_id: int, body: ReviewAction):
        return to_out(svc.reject(invoice_id, body.note))

    @app.post("/api/invoices/{invoice_id}/undo")
    def undo(invoice_id: int):
        return to_out(svc.undo(invoice_id))

    @app.post("/api/invoices/{invoice_id}/retry")
    def retry(invoice_id: int):
        return to_out(svc.retry(invoice_id))

    return app


app = create_app()
