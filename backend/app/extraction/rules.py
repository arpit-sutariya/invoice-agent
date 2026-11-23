"""Rules-based extractor: reads the PDF's text layer and pulls fields out with patterns.

Fast, free and fully explainable, but it only knows the label wordings it was written for.
Unfamiliar layouts (see the holdout set) and scans without a text layer are where it fails;
that is what the LLM extractor is for.
"""
from __future__ import annotations

import re
from pathlib import Path

import pdfplumber

from app.schemas import ExtractedInvoice, LineItem

from .normalize import normalize_po, parse_date, parse_money

TITLE_WORDS = {"invoice", "tax invoice", "bill"}
MONEY = r"(?:USD\s*|\$)?\s*(-?[\d,]+\.\d{2})"
DATE = r"(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4}|[A-Za-z]{3,9}\.? \d{1,2}, \d{4}|\d{1,2} [A-Za-z]{3,9} \d{4})"
NEXT_LABEL = re.compile(r"\s+(?:Invoice|Date|Bill|Issued|PO|Purchase|Your Order)\b.*$")

HEADER_PATTERNS = {
    "invoice_number": [r"Invoice\s*(?:Number|No\.?|#)\s*[:#]?\s*([A-Z0-9][A-Z0-9\-]*)",
                       r"Bill\s*No\.?\s*[:#]?\s*([A-Z0-9][A-Z0-9\-]*)"],
    "invoice_date": [rf"Invoice\s*Date\s*:?\s*{DATE}",
                     rf"(?<![A-Za-z])Date\s*:?\s*{DATE}",
                     rf"Issued\s*:?\s*{DATE}"],
    "po_number": [r"(?:PO\s*Number|Purchase\s*Order|Order\s*Ref)\s*[:#]?\s*(PO[\s\-]?\d{4}[\s\-]\d{4})"],
}

TOTAL_PATTERNS = {
    "subtotal": [rf"^(?:Subtotal|Sub-total|Net)\s*:?\s*{MONEY}"],
    "tax": [rf"^(?:Tax(?:\s*\([\d.]+%\))?|Sales\s*Tax|VAT/Tax)\s*:?\s*{MONEY}"],
    "total": [rf"^(?:Total\s*Due|Amount\s*Due|TOTAL)\s*:?\s*{MONEY}"],
}

SKU_RE = re.compile(r"\b([A-Z]{3}-\d{4})\b")
NUM_RE = re.compile(r"^-?[\d,]+(?:\.\d+)?$")


def _first(patterns: list[str], text: str, flags=0) -> str | None:
    for p in patterns:
        m = re.search(p, text, flags)
        if m:
            return m.group(1).strip()
    return None


def _vendor(lines: list[str]) -> str | None:
    for line in lines:
        m = re.match(r"^(?:From|Supplier|Vendor)\s*:\s*(.+)$", line)
        if m:  # the PDF may put another label on the same text line: cut it off
            return NEXT_LABEL.sub("", m.group(1)).strip()
    for line in lines:  # otherwise the first line that isn't a document title
        if line.strip() and line.strip().lower() not in TITLE_WORDS:
            return line.strip()
    return None


def _line_items(lines: list[str]) -> list[LineItem]:
    """A line item = a line with a SKU code that ends in three numbers: quantity, unit price, amount."""
    items = []
    for line in lines:
        sku = SKU_RE.search(line)
        if not sku:
            continue
        tokens = line.split()
        nums = []
        while tokens and NUM_RE.match(tokens[-1]) and len(nums) < 3:
            nums.insert(0, tokens.pop())
        if len(nums) < 3:
            continue
        desc = " ".join(t for t in tokens if t != sku.group(1)).strip()
        qty_raw = nums[0].replace(",", "")
        items.append(LineItem(
            sku=sku.group(1), description=desc or None,
            quantity=int(float(qty_raw)) if qty_raw else None,
            unit_price=parse_money(nums[1]), amount=parse_money(nums[2])))
    return items


def extract_text(path: Path) -> str:
    with pdfplumber.open(path) as pdf:
        return "\n".join((page.extract_text() or "") for page in pdf.pages)


def extract_rules(path: Path) -> ExtractedInvoice:
    text = extract_text(path)
    if len(text.strip()) < 20:
        return ExtractedInvoice(has_text=False, warnings=["No text layer found (scanned or photographed document)"])

    lines = [l.strip() for l in text.splitlines() if l.strip()]
    inv = ExtractedInvoice(
        vendor_name=_vendor(lines),
        invoice_number=_first(HEADER_PATTERNS["invoice_number"], text),
        invoice_date=parse_date(_first(HEADER_PATTERNS["invoice_date"], text)),
        po_number=normalize_po(_first(HEADER_PATTERNS["po_number"], text, re.IGNORECASE)),
        line_items=_line_items(lines),
    )
    for field, patterns in TOTAL_PATTERNS.items():
        raw = None
        for line in lines:
            raw = _first(patterns, line)
            if raw:
                break
        setattr(inv, field, parse_money(raw))

    for field in ("vendor_name", "invoice_number", "invoice_date", "total"):
        if not getattr(inv, field):
            inv.warnings.append(f"Could not find {field.replace('_', ' ')}")
    if not inv.line_items:
        inv.warnings.append("Could not find any line items")
    return inv
