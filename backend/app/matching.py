"""Business checks: is this invoice safe to pay?

Runs in a fixed order and returns a list of Issues. No issues = safe to approve.
Every check is deterministic code; the LLM (if used) only reads the document.
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable

from app.erp_client import ErpClient, ErpNotFound, ErpUnavailable
from app.extraction.normalize import invoice_key, vendor_key
from app.schemas import ExtractedInvoice, Issue

# What each issue code means, shown in the UI and README
ISSUE_CODES = {
    "UNREADABLE": "No text could be read from the document",
    "MISSING_FIELDS": "Required fields could not be extracted",
    "UNKNOWN_VENDOR": "Vendor is not in the vendor master",
    "DUPLICATE": "Same vendor and invoice number already received",
    "TOTALS_MISMATCH": "Line amounts, subtotal, tax and total don't add up",
    "MISSING_PO": "No purchase order number on the invoice",
    "UNKNOWN_PO": "Purchase order not found in the ERP",
    "VENDOR_MISMATCH": "Purchase order belongs to a different vendor",
    "ITEM_NOT_ON_PO": "Invoiced item is not on the purchase order",
    "QTY_EXCEEDS_PO": "Invoiced quantity exceeds what is left on the PO",
    "PRICE_MISMATCH": "Unit price differs from the PO price",
    "ERP_UNAVAILABLE": "The ERP could not be reached; retry later",
    "EXTRACTION_FAILED": "The extractor crashed on this document",
}


@dataclass
class CheckResult:
    issues: list[Issue]
    vendor_id: str | None
    vendor_key: str | None
    invoice_key: str | None


def D(x) -> Decimal | None:
    return Decimal(str(x)) if x not in (None, "") else None


def match_vendor(name: str | None, vendors: list[dict]) -> dict | None:
    key = vendor_key(name)
    if not key:
        return None
    by_key = {vendor_key(v["name"]): v for v in vendors}
    if key in by_key:
        return by_key[key]
    best = difflib.get_close_matches(key, list(by_key), n=1, cutoff=0.85)
    return by_key[best[0]] if best else None


def check_arithmetic(inv: ExtractedInvoice, tol: Decimal) -> list[dict]:
    problems = []
    line_sum = Decimal("0")
    for i, li in enumerate(inv.line_items, start=1):
        price, amount = D(li.unit_price), D(li.amount)
        if li.quantity is not None and price is not None and amount is not None:
            expected = (price * li.quantity).quantize(Decimal("0.01"))
            if abs(expected - amount) > tol:
                problems.append({"where": f"line {i}", "expected": str(expected), "found": str(amount)})
        line_sum += amount or Decimal("0")
    subtotal, tax, total = D(inv.subtotal), D(inv.tax), D(inv.total)
    if subtotal is not None and inv.line_items and abs(line_sum - subtotal) > tol:
        problems.append({"where": "subtotal", "expected": str(line_sum), "found": str(subtotal)})
    if subtotal is not None and total is not None:
        expected_total = subtotal + (tax or Decimal("0"))
        if abs(expected_total - total) > tol:
            problems.append({"where": "total", "expected": str(expected_total), "found": str(total)})
    return problems


def run_checks(inv: ExtractedInvoice, erp: ErpClient, find_duplicate: Callable[[str, str], int | None],
               price_tolerance_pct: Decimal, amount_tolerance: Decimal) -> CheckResult:
    if not inv.has_text:
        return CheckResult([Issue(code="UNREADABLE", message="No text layer: this looks like a scan or photo. "
                                  "Enable the LLM extractor or enter the fields by hand.")], None, None, None)

    issues: list[Issue] = []
    missing = [f for f in ("vendor_name", "invoice_number", "total") if not getattr(inv, f)]
    if missing or not inv.line_items:
        fields = missing + (["line_items"] if not inv.line_items else [])
        issues.append(Issue(code="MISSING_FIELDS", message=f"Could not read: {', '.join(fields)}",
                            details={"fields": fields}))

    # Local checks first: they need no ERP, so they still work during an ERP outage.
    # 1. Duplicate (keys come from the document itself, never from an ERP lookup)
    vkey = vendor_key(inv.vendor_name) or None
    ikey = invoice_key(inv.invoice_number) or None
    if vkey and ikey:
        dup_id = find_duplicate(vkey, ikey)
        if dup_id is not None:
            return CheckResult([Issue(code="DUPLICATE",
                                      message=f"Invoice {inv.invoice_number} from this vendor was already received "
                                              f"(invoice #{dup_id})", details={"original_id": dup_id})],
                               None, vkey, ikey)

    # 2. Arithmetic on the document itself
    problems = check_arithmetic(inv, amount_tolerance)
    if problems:
        issues.append(Issue(code="TOTALS_MISMATCH",
                            message="Amounts on the invoice don't add up: " +
                                    "; ".join(f"{p['where']} is {p['found']}, expected {p['expected']}" for p in problems),
                            details={"problems": problems}))

    # 3+. Checks against the ERP. If it's down, keep what we found and say so.
    try:
        vendor_id = _erp_checks(inv, erp, issues, price_tolerance_pct)
    except ErpUnavailable as e:
        issues.append(Issue(code="ERP_UNAVAILABLE", message=f"Could not reach the ERP ({e}). Use Retry."))
        vendor_id = None
    return CheckResult(issues, vendor_id, vkey, ikey)


def _erp_checks(inv: ExtractedInvoice, erp: ErpClient, issues: list[Issue], price_tolerance_pct: Decimal) -> str | None:
    """Vendor master, purchase order and line checks. Appends to issues; returns the vendor id."""
    # 3. Vendor
    vendor = match_vendor(inv.vendor_name, erp.vendors())
    if inv.vendor_name and not vendor:
        issues.append(Issue(code="UNKNOWN_VENDOR", message=f"'{inv.vendor_name}' is not in the vendor master",
                            details={"vendor_name": inv.vendor_name}))
    vendor_id = vendor["id"] if vendor else None

    # 4. Purchase order
    if not inv.po_number:
        issues.append(Issue(code="MISSING_PO", message="No purchase order number found on the invoice"))
        return vendor_id
    try:
        po = erp.purchase_order(inv.po_number)
    except ErpNotFound:
        issues.append(Issue(code="UNKNOWN_PO", message=f"{inv.po_number} does not exist in the ERP",
                            details={"po_number": inv.po_number}))
        return vendor_id

    if vendor and po["vendor_id"] != vendor["id"]:
        issues.append(Issue(code="VENDOR_MISMATCH",
                            message=f"{inv.po_number} was issued to vendor {po['vendor_id']}, "
                                    f"but this invoice is from {vendor['name']} ({vendor['id']})",
                            details={"po_vendor_id": po["vendor_id"], "invoice_vendor_id": vendor["id"]}))
        return vendor_id

    # 5. Line by line against the PO
    po_lines = {l["sku"]: l for l in po["lines"]}
    for li in inv.line_items:
        pl = po_lines.get(li.sku or "")
        if not pl:
            issues.append(Issue(code="ITEM_NOT_ON_PO", message=f"{li.sku} ({li.description}) is not on {inv.po_number}",
                                details={"sku": li.sku}))
            continue
        remaining = pl["quantity"] - pl.get("invoiced_quantity", 0)
        if li.quantity is not None and li.quantity > remaining:
            issues.append(Issue(code="QTY_EXCEEDS_PO",
                                message=f"{li.sku}: invoiced {li.quantity}, but only {remaining} left on the PO "
                                        f"(ordered {pl['quantity']})",
                                details={"sku": li.sku, "invoiced": li.quantity, "remaining": remaining}))
        price, po_price = D(li.unit_price), D(pl["unit_price"])
        if price is not None and po_price:
            diff_pct = (price - po_price) / po_price * 100
            if abs(diff_pct) > price_tolerance_pct:
                issues.append(Issue(code="PRICE_MISMATCH",
                                    message=f"{li.sku}: billed {price} each, PO price is {po_price} "
                                            f"({diff_pct:+.1f}%)",
                                    details={"sku": li.sku, "invoice_price": str(price), "po_price": str(po_price),
                                             "diff_pct": f"{diff_pct:.2f}"}))
    return vendor_id
