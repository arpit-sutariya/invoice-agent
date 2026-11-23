"""End-to-end tests through the HTTP API, with the mock ERP running in-process.

Run from backend/:  pytest -q
"""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import BACKEND_DIR, settings
from app.erp_client import ErpClient
from app.extraction.normalize import normalize_po, parse_date, parse_money, vendor_key
from app.main import create_app
from mock_erp.main import create_app as create_erp

LABELS = json.loads((BACKEND_DIR / "data" / "labels" / "main.json").read_text())
INVOICES = BACKEND_DIR / "data" / "invoices" / "main"


def first(category: str) -> dict:
    return next(l for l in LABELS if l["category"] == category)


@pytest.fixture
def api(tmp_path: Path):
    erp_http = TestClient(create_erp(fail_rate=0))
    cfg = replace(settings, database_url=f"sqlite:///{tmp_path}/test.db", upload_dir=tmp_path / "uploads",
                  extractor="rules", auto_approve=True)
    client = TestClient(create_app(cfg, ErpClient(erp_http, backoff_s=0)))
    client.erp_http = erp_http
    return client


def upload(api, label: dict) -> dict:
    path = INVOICES / label["file"]
    r = api.post("/api/invoices", files=[("files", (label["file"], path.read_bytes(), "application/pdf"))])
    assert r.status_code == 200, r.text
    return r.json()[0]


# ---------------------------------------------------------------- normalisers
def test_normalizers():
    assert normalize_po("Your Order Ref PO 2026-0012") == "PO-2026-0012"
    assert normalize_po("po/2026/0012") == "PO-2026-0012"
    assert parse_money("USD 1,234.50") == "1234.50"
    assert parse_date("Nov 3, 2026") == "2026-11-03"
    assert parse_date("11/03/2026") == "2026-11-03"
    assert vendor_key("Redline Fasteners Inc.") == vendor_key("REDLINE FASTENERS")


# ---------------------------------------------------------------- automatic outcomes
def test_clean_invoice_is_auto_approved_and_posted(api):
    inv = upload(api, first("clean"))
    assert inv["status"] == "approved"
    assert inv["erp_document_id"].startswith("ERP-")
    posted = api.erp_http.get("/invoices").json()
    assert [d["id"] for d in posted] == [inv["erp_document_id"]]


def test_price_mismatch_goes_to_review(api):
    inv = upload(api, first("price_mismatch"))
    assert inv["status"] == "needs_review"
    assert [i["code"] for i in inv["issues"]] == ["PRICE_MISMATCH"]


def test_resubmitted_invoice_is_rejected_as_duplicate(api):
    original = first("clean")
    upload(api, original)
    dup = upload(api, original)
    assert dup["status"] == "rejected"
    assert dup["issues"][0]["code"] == "DUPLICATE"


def test_scan_without_text_goes_to_review(api):
    inv = upload(api, first("unreadable"))
    assert inv["status"] == "needs_review"
    assert inv["issues"][0]["code"] == "UNREADABLE"


def test_non_pdf_is_refused(api):
    r = api.post("/api/invoices", files=[("files", ("notes.txt", b"hello", "text/plain"))])
    assert r.status_code == 400


# ---------------------------------------------------------------- reviewer actions
def test_approving_with_open_issues_requires_a_note(api):
    inv = upload(api, first("price_mismatch"))
    r = api.post(f"/api/invoices/{inv['id']}/approve", json={})
    assert r.status_code == 422
    r = api.post(f"/api/invoices/{inv['id']}/approve", json={"note": "Price increase agreed by email on 10/2"})
    assert r.status_code == 200
    assert r.json()["status"] == "approved"


def test_reject_requires_note_and_undo_restores_review(api):
    inv = upload(api, first("totals_mismatch"))
    assert api.post(f"/api/invoices/{inv['id']}/reject", json={}).status_code == 422
    r = api.post(f"/api/invoices/{inv['id']}/reject", json={"note": "Total is wrong, asked vendor to reissue"})
    assert r.json()["status"] == "rejected"
    r = api.post(f"/api/invoices/{inv['id']}/undo")
    assert r.json()["status"] == "needs_review"


def test_undo_approval_reverses_erp_posting(api):
    inv = upload(api, first("clean"))
    doc_id = inv["erp_document_id"]
    r = api.post(f"/api/invoices/{inv['id']}/undo")
    assert r.status_code == 200
    assert r.json()["status"] == "needs_review"
    assert api.erp_http.get("/invoices").json()[0]["reversed"] is True
    # quantities are released, so it can be approved again
    r = api.post(f"/api/invoices/{inv['id']}/approve", json={})
    assert r.status_code == 200, r.text
    assert r.json()["erp_document_id"] != doc_id


def test_editing_missing_po_reruns_checks(api):
    label = first("missing_po")
    inv = upload(api, label)
    assert inv["issues"][0]["code"] == "MISSING_PO"
    # the reviewer finds the PO number by looking it up for this vendor in the ERP
    seed = json.loads((BACKEND_DIR / "data" / "erp_seed.json").read_text())
    skus = {li["sku"] for li in label["line_items"]}
    po = next(p for p in seed["purchase_orders"]
              if p["vendor_id"] == label["vendor_id"] and skus <= {l["sku"] for l in p["lines"]})
    r = api.patch(f"/api/invoices/{inv['id']}", json={"po_number": po["po_number"].replace("-", " ")})
    assert r.status_code == 200
    assert r.json()["issues"] == []
    assert r.json()["extracted"]["po_number"] == po["po_number"]
    assert api.post(f"/api/invoices/{inv['id']}/approve", json={}).json()["status"] == "approved"


def test_every_action_is_audited(api):
    inv = upload(api, first("price_mismatch"))
    api.post(f"/api/invoices/{inv['id']}/approve", json={"note": "ok"})
    api.post(f"/api/invoices/{inv['id']}/undo")
    actions = [e["action"] for e in api.get(f"/api/invoices/{inv['id']}/audit").json()]
    assert actions == ["uploaded", "extracted", "flagged", "approved", "undo_approval"]


def test_erp_down_keeps_invoice_in_review(tmp_path):
    erp = ErpClient.from_url("http://127.0.0.1:9", timeout_s=0.2, retries=2)  # nothing listens here
    erp.backoff_s = 0
    cfg = replace(settings, database_url=f"sqlite:///{tmp_path}/t.db", upload_dir=tmp_path / "u",
                  extractor="rules")
    api = TestClient(create_app(cfg, erp))
    inv = upload(api, first("clean"))
    assert inv["status"] == "needs_review"
    assert "ERP_UNAVAILABLE" in [i["code"] for i in inv["issues"]]
