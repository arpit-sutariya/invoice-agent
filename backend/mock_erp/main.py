"""Mock accounting system (ERP).

Stands in for the client's real system (NetSuite, SAP, QuickBooks...). The invoice agent only
talks to it over HTTP, the same way it would talk to the real one.

Run from backend/:  uvicorn mock_erp.main:app --port 8001 --reload
Docs:               http://localhost:8001/docs

State is in memory and reloads from data/erp_seed.json on every restart (or POST /admin/reset).
Set ERP_FAIL_RATE=0.2 to make 20% of requests fail with 503, to test retries and error handling.
"""
from __future__ import annotations

import json
import os
import random
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

SEED_FILE = Path(__file__).resolve().parents[1] / "data" / "erp_seed.json"


class PostedLine(BaseModel):
    sku: str
    quantity: int


class PostInvoice(BaseModel):
    vendor_id: str
    invoice_number: str
    po_number: str
    total: str
    lines: list[PostedLine]


class ErpState:
    def __init__(self):
        self.reset()

    def reset(self):
        if not SEED_FILE.exists():
            raise RuntimeError(f"{SEED_FILE} not found. Run: python -m scripts.generate_dataset")
        seed = json.loads(SEED_FILE.read_text())
        self.vendors = {v["id"]: v for v in seed["vendors"]}
        self.pos = {p["po_number"]: p for p in seed["purchase_orders"]}
        self.invoiced: dict[tuple[str, str], int] = {}  # (po_number, sku) -> quantity already invoiced
        self.posted: dict[str, dict] = {}  # erp document id -> posted invoice


def create_app(fail_rate: float | None = None) -> FastAPI:
    app = FastAPI(title="Mock ERP", version="1.0")
    state = ErpState()
    app.state.erp = state
    rate = float(os.getenv("ERP_FAIL_RATE", "0")) if fail_rate is None else fail_rate

    @app.middleware("http")
    async def flaky(request: Request, call_next):
        if rate and request.url.path not in ("/health", "/admin/reset") and random.random() < rate:
            return JSONResponse({"detail": "ERP temporarily unavailable"}, status_code=503)
        return await call_next(request)

    @app.get("/health")
    def health():
        return {"ok": True, "vendors": len(state.vendors), "purchase_orders": len(state.pos)}

    @app.post("/admin/reset")
    def reset():
        state.reset()
        return {"ok": True}

    @app.get("/vendors")
    def vendors():
        return list(state.vendors.values())

    @app.get("/purchase-orders/{po_number}")
    def get_po(po_number: str):
        po = state.pos.get(po_number)
        if not po:
            raise HTTPException(404, f"Purchase order {po_number} not found")
        lines = [{**l, "invoiced_quantity": state.invoiced.get((po_number, l["sku"]), 0)}
                 for l in po["lines"]]
        return {**po, "lines": lines}

    @app.get("/invoices")
    def list_posted():
        return list(state.posted.values())

    @app.post("/invoices", status_code=201)
    def post_invoice(body: PostInvoice):
        po = state.pos.get(body.po_number)
        if not po:
            raise HTTPException(404, f"Purchase order {body.po_number} not found")
        for doc in state.posted.values():
            if doc["vendor_id"] == body.vendor_id and doc["invoice_number"] == body.invoice_number \
                    and not doc["reversed"]:
                raise HTTPException(409, f"Invoice {body.invoice_number} already posted as {doc['id']}")
        doc_id = f"ERP-{uuid.uuid4().hex[:8].upper()}"
        for line in body.lines:
            key = (body.po_number, line.sku)
            state.invoiced[key] = state.invoiced.get(key, 0) + line.quantity
        doc = {"id": doc_id, **body.model_dump(), "reversed": False}
        state.posted[doc_id] = doc
        return doc

    @app.post("/invoices/{doc_id}/reverse")
    def reverse(doc_id: str):
        doc = state.posted.get(doc_id)
        if not doc:
            raise HTTPException(404, f"Document {doc_id} not found")
        if doc["reversed"]:
            raise HTTPException(409, f"Document {doc_id} already reversed")
        for line in doc["lines"]:
            key = (doc["po_number"], line["sku"])
            state.invoiced[key] = state.invoiced.get(key, 0) - line["quantity"]
        doc["reversed"] = True
        return doc

    return app


app = create_app()
