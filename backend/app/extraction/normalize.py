"""Helpers that turn messy strings into clean values. Shared by every extractor."""
from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

_PO_RE = re.compile(r"PO[\s\-/#:]*?(\d{4})[\s\-/]?(\d{4})", re.IGNORECASE)


def normalize_po(raw: str | None) -> str | None:
    """'PO 2026-0012', 'po/2026/0012', 'PO-2026-0012' -> 'PO-2026-0012'."""
    if not raw:
        return None
    m = _PO_RE.search(raw)
    return f"PO-{m.group(1)}-{m.group(2)}" if m else None


def parse_money(raw: str | None) -> str | None:
    """'$1,234.56', 'USD 1,234.56', '1234.56' -> '1234.56'. Returns None if not a number."""
    if raw is None:
        return None
    cleaned = re.sub(r"[^\d.\-]", "", str(raw))
    if not cleaned:
        return None
    try:
        return str(Decimal(cleaned).quantize(Decimal("0.01")))
    except InvalidOperation:
        return None


_DATE_FORMATS = ["%Y-%m-%d", "%m/%d/%Y", "%b %d, %Y", "%B %d, %Y", "%d %B %Y", "%d %b %Y",
                 "%d/%m/%Y", "%Y/%m/%d"]


def parse_date(raw: str | None) -> str | None:
    if not raw:
        return None
    raw = raw.strip().rstrip(".")
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


_SUFFIXES = re.compile(r"\b(inc|llc|ltd|co|corp|corporation|company|the)\b")


def vendor_key(name: str | None) -> str:
    """Lowercase, no punctuation, no legal suffixes: 'Redline Fasteners Inc.' -> 'redline fasteners'."""
    if not name:
        return ""
    s = re.sub(r"[^a-z0-9 ]", " ", name.lower())
    s = _SUFFIXES.sub(" ", s)
    return " ".join(s.split())


def invoice_key(number: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (number or "").upper())
