"""HTTP client for the accounting system, with timeouts and retries.

Every call either returns data or raises ErpUnavailable / ErpNotFound / ErpConflict, so the
pipeline can turn each failure into a known invoice state instead of crashing.
"""
from __future__ import annotations

import time

import httpx


class ErpError(Exception):
    pass


class ErpUnavailable(ErpError):
    """Network error, timeout or 5xx after all retries."""


class ErpNotFound(ErpError):
    pass


class ErpConflict(ErpError):
    pass


class ErpClient:
    def __init__(self, http: httpx.Client, retries: int = 3, backoff_s: float = 0.2):
        self.http = http
        self.retries = retries
        self.backoff_s = backoff_s
        self._vendors_cache: list[dict] | None = None

    @classmethod
    def from_url(cls, base_url: str, timeout_s: float = 5, retries: int = 3) -> "ErpClient":
        return cls(httpx.Client(base_url=base_url, timeout=timeout_s), retries=retries)

    def _request(self, method: str, path: str, **kw) -> httpx.Response:
        last_err = None
        for attempt in range(self.retries):
            try:
                r = self.http.request(method, path, **kw)
            except httpx.HTTPError as e:  # connection refused, timeout...
                last_err = str(e) or e.__class__.__name__
            else:
                if r.status_code < 500:
                    if r.status_code == 404:
                        raise ErpNotFound(r.json().get("detail", "not found"))
                    if r.status_code == 409:
                        raise ErpConflict(r.json().get("detail", "conflict"))
                    r.raise_for_status()
                    return r
                last_err = f"HTTP {r.status_code}"
            time.sleep(self.backoff_s * (2 ** attempt))
        raise ErpUnavailable(f"{method} {path} failed after {self.retries} attempts: {last_err}")

    def health(self) -> bool:
        try:
            self._request("GET", "/health")
            return True
        except ErpError:
            return False

    def vendors(self) -> list[dict]:
        if self._vendors_cache is None:
            self._vendors_cache = self._request("GET", "/vendors").json()
        return self._vendors_cache

    def purchase_order(self, po_number: str) -> dict:
        return self._request("GET", f"/purchase-orders/{po_number}").json()

    def post_invoice(self, payload: dict) -> dict:
        return self._request("POST", "/invoices", json=payload).json()

    def reverse_invoice(self, doc_id: str) -> dict:
        return self._request("POST", f"/invoices/{doc_id}/reverse").json()
