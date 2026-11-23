"""Shapes of the data passed between steps. Money is kept as strings and parsed with Decimal."""
from __future__ import annotations

from pydantic import BaseModel, Field


class LineItem(BaseModel):
    sku: str | None = None
    description: str | None = None
    quantity: int | None = None
    unit_price: str | None = None
    amount: str | None = None


class ExtractedInvoice(BaseModel):
    vendor_name: str | None = None
    invoice_number: str | None = None
    invoice_date: str | None = None  # ISO yyyy-mm-dd
    po_number: str | None = None     # normalised to PO-YYYY-NNNN
    currency: str | None = "USD"
    subtotal: str | None = None
    tax: str | None = None
    total: str | None = None
    line_items: list[LineItem] = Field(default_factory=list)
    has_text: bool = True            # False = no text layer (scan/photo)
    warnings: list[str] = Field(default_factory=list)


class Issue(BaseModel):
    code: str          # e.g. PRICE_MISMATCH
    message: str       # human-readable, shown to the reviewer
    details: dict = Field(default_factory=dict)


class InvoiceOut(BaseModel):
    id: int
    filename: str
    status: str
    extraction_method: str | None
    extracted: ExtractedInvoice
    issues: list[Issue]
    vendor_id: str | None
    erp_document_id: str | None
    processing_ms: int | None
    review_note: str | None
    created_at: str
    updated_at: str


class AuditOut(BaseModel):
    id: int
    invoice_id: int
    at: str
    actor: str
    action: str
    from_status: str | None
    to_status: str | None
    details: dict


class ReviewAction(BaseModel):
    note: str | None = None


class EditFields(BaseModel):
    """Reviewer corrections. Any field left out stays as extracted."""
    vendor_name: str | None = None
    invoice_number: str | None = None
    invoice_date: str | None = None
    po_number: str | None = None
    subtotal: str | None = None
    tax: str | None = None
    total: str | None = None
    line_items: list[LineItem] | None = None
