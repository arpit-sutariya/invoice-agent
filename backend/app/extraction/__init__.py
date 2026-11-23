"""Picks an extractor. 'auto' tries the free rules extractor first and only calls the LLM when the
rules extractor couldn't read the invoice (no text layer or critical fields missing)."""
from __future__ import annotations

from pathlib import Path

from app.schemas import ExtractedInvoice

from .llm import extract_llm
from .rules import extract_rules

CRITICAL = ("vendor_name", "invoice_number", "total")


def needs_fallback(inv: ExtractedInvoice) -> bool:
    return (not inv.has_text) or any(not getattr(inv, f) for f in CRITICAL) or not inv.line_items


def extract(path: Path, mode: str, api_key: str | None, model: str) -> tuple[ExtractedInvoice, str]:
    """Returns (extracted invoice, method used)."""
    if mode == "llm":
        if not api_key:
            raise RuntimeError("EXTRACTOR=llm needs ANTHROPIC_API_KEY")
        return extract_llm(path, api_key, model), "llm"

    inv = extract_rules(path)
    if mode == "auto" and api_key and needs_fallback(inv):
        try:
            return extract_llm(path, api_key, model), "llm_fallback"
        except Exception as e:  # LLM down or bad output: keep the rules result, flag it
            inv.warnings.append(f"LLM fallback failed: {e.__class__.__name__}: {e}")
    return inv, "rules"
