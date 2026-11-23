"""LLM extractor: sends the PDF to Claude and asks for the fields as structured output.

Handles unfamiliar layouts and scans (Claude reads the page image when there is no text layer).
Needs ANTHROPIC_API_KEY. Output goes through the same normalisers as the rules extractor, and
every number is still checked by the matching step, so the model is never trusted blindly.
"""
from __future__ import annotations

import base64
from pathlib import Path

from app.schemas import ExtractedInvoice, LineItem

from .normalize import normalize_po, parse_date, parse_money

TOOL = {
    "name": "record_invoice",
    "description": "Record the fields read from the invoice. Use null for anything not shown on the document. "
                   "Copy values exactly as printed; do not calculate or guess.",
    "input_schema": {
        "type": "object",
        "properties": {
            "vendor_name": {"type": ["string", "null"], "description": "The company that issued the invoice (not the customer)"},
            "invoice_number": {"type": ["string", "null"]},
            "invoice_date": {"type": ["string", "null"], "description": "As printed"},
            "po_number": {"type": ["string", "null"], "description": "Customer purchase order number, as printed"},
            "currency": {"type": ["string", "null"]},
            "subtotal": {"type": ["string", "null"]},
            "tax": {"type": ["string", "null"]},
            "total": {"type": ["string", "null"], "description": "Final amount due"},
            "line_items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "sku": {"type": ["string", "null"], "description": "Item/part code as printed"},
                        "description": {"type": ["string", "null"]},
                        "quantity": {"type": ["number", "null"]},
                        "unit_price": {"type": ["string", "null"]},
                        "amount": {"type": ["string", "null"]},
                    },
                },
            },
        },
        "required": ["vendor_name", "invoice_number", "invoice_date", "po_number", "total", "line_items"],
    },
}


def _normalize_sku(raw: str | None) -> str | None:
    """'HEW1111' -> 'HEW-1111' so codes match the ERP's format."""
    if not raw:
        return None
    s = raw.strip().upper().replace(" ", "")
    if len(s) == 7 and s[:3].isalpha() and s[3:].isdigit():
        return f"{s[:3]}-{s[3:]}"
    return s


def extract_llm(path: Path, api_key: str, model: str) -> ExtractedInvoice:
    import anthropic  # imported here so the app runs without it when EXTRACTOR=rules

    client = anthropic.Anthropic(api_key=api_key)
    pdf_b64 = base64.standard_b64encode(path.read_bytes()).decode()
    resp = client.messages.create(
        model=model,
        max_tokens=2000,
        tools=[TOOL],
        tool_choice={"type": "tool", "name": "record_invoice"},
        messages=[{
            "role": "user",
            "content": [
                {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64}},
                {"type": "text", "text": "Extract this supplier invoice with the record_invoice tool."},
            ],
        }],
    )
    data = next(b.input for b in resp.content if b.type == "tool_use")
    items = []
    for li in data.get("line_items") or []:
        qty = li.get("quantity")
        items.append(LineItem(
            sku=_normalize_sku(li.get("sku")), description=li.get("description"),
            quantity=int(qty) if qty is not None else None,
            unit_price=parse_money(li.get("unit_price")), amount=parse_money(li.get("amount"))))
    inv = ExtractedInvoice(
        vendor_name=data.get("vendor_name"),
        invoice_number=data.get("invoice_number"),
        invoice_date=parse_date(data.get("invoice_date")) or data.get("invoice_date"),
        po_number=normalize_po(data.get("po_number")),
        currency=data.get("currency") or "USD",
        subtotal=parse_money(data.get("subtotal")),
        tax=parse_money(data.get("tax")),
        total=parse_money(data.get("total")),
        line_items=items,
    )
    for field in ("vendor_name", "invoice_number", "invoice_date", "total"):
        if not getattr(inv, field):
            inv.warnings.append(f"Could not find {field.replace('_', ' ')}")
    return inv
