"""Evaluate the whole pipeline against the labelled dataset.

Run from backend/:
    python -m eval.run_eval                       # main set, rules extractor
    python -m eval.run_eval --set holdout         # unseen layout
    python -m eval.run_eval --extractor auto      # rules + LLM fallback (needs ANTHROPIC_API_KEY)
    python -m eval.run_eval --erp-fail-rate 0.2   # 20% of ERP calls fail: tests retries

Each run starts from a fresh database and a freshly seeded mock ERP, processes invoices in file
order (so duplicates arrive after their originals), and writes eval/results/<set>_<extractor>.md/.json.
"""
from __future__ import annotations

import argparse
import json
import random
import tempfile
import time
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import BACKEND_DIR, settings as base_settings
from app.db import make_session_factory
from app.erp_client import ErpClient
from app.extraction.normalize import invoice_key, vendor_key
from app.pipeline import InvoiceService
from mock_erp.main import create_app as create_erp

FIELDS = ["vendor_name", "invoice_number", "invoice_date", "po_number", "subtotal", "tax", "total"]
RESULTS_DIR = BACKEND_DIR / "eval" / "results"


def same(field: str, got, want) -> bool:
    if field == "vendor_name":
        return vendor_key(got) == vendor_key(want)
    if field == "invoice_number":
        return invoice_key(got) == invoice_key(want)
    return (got or None) == (want or None)


def line_matches(got: list[dict], want: list[dict]) -> int:
    pool = Counter((l.get("sku"), l.get("quantity"), l.get("unit_price"), l.get("amount")) for l in got)
    hits = 0
    for l in want:
        key = (l["sku"], l["quantity"], l["unit_price"], l["amount"])
        if pool[key] > 0:
            pool[key] -= 1
            hits += 1
    return hits


def pct(n: int, d: int) -> str:
    return f"{100 * n / d:.1f}%" if d else "n/a"


def run(set_name: str, extractor: str, erp_fail_rate: float, seed: int = 7) -> dict:
    random.seed(seed)
    labels = json.loads((BACKEND_DIR / "data" / "labels" / f"{set_name}.json").read_text())
    folder = BACKEND_DIR / "data" / "invoices" / set_name

    tmp = tempfile.mkdtemp(prefix="invoice-eval-")
    cfg = replace(base_settings, database_url=f"sqlite:///{tmp}/eval.db", extractor=extractor,
                  auto_approve=True)
    erp_http = TestClient(create_erp(fail_rate=erp_fail_rate))
    svc = InvoiceService(make_session_factory(cfg.database_url), ErpClient(erp_http, retries=3, backoff_s=0),
                         cfg)

    rows = []
    t0 = time.perf_counter()
    for lab in labels:
        inv = svc.process_file(folder / lab["file"], lab["file"])
        ex = inv.extracted
        codes = [i["code"] for i in inv.issues]
        field_ok = {f: same(f, ex.get(f), lab.get(f)) for f in FIELDS}
        hits = line_matches(ex.get("line_items", []), lab["line_items"])
        status_ok = inv.status == lab["expected_status"]
        reasons_ok = (not codes) if lab["expected_status"] == "approved" else \
            all(r in codes for r in lab["expected_reasons"])
        rows.append({"file": lab["file"], "category": lab["category"], "layout": lab["layout"],
                     "expected_status": lab["expected_status"], "status": inv.status,
                     "expected_reasons": lab["expected_reasons"], "issues": codes,
                     "status_ok": status_ok, "outcome_ok": status_ok and reasons_ok,
                     "fields": field_ok, "line_hits": hits, "line_total": len(lab["line_items"]),
                     "method": inv.extraction_method, "ms": inv.processing_ms})
    elapsed = time.perf_counter() - t0
    return summarize(rows, set_name, extractor, erp_fail_rate, elapsed)


def summarize(rows, set_name, extractor, erp_fail_rate, elapsed) -> dict:
    n = len(rows)
    readable = [r for r in rows if r["layout"] != "scan"]
    field_acc = {f: (sum(r["fields"][f] for r in rows), n) for f in FIELDS}
    field_acc_readable = {f: (sum(r["fields"][f] for r in readable), len(readable)) for f in FIELDS}
    lines = (sum(r["line_hits"] for r in rows), sum(r["line_total"] for r in rows))

    should_not_pay = [r for r in rows if r["expected_status"] != "approved"]
    false_approvals = [r for r in should_not_pay if r["status"] == "approved"]
    clean = [r for r in rows if r["expected_status"] == "approved"]
    auto_approved = [r for r in clean if r["status"] == "approved"]

    by_cat = defaultdict(lambda: [0, 0])
    for r in rows:
        by_cat[r["category"]][0] += r["outcome_ok"]
        by_cat[r["category"]][1] += 1
    confusion = Counter((r["expected_status"], r["status"]) for r in rows)

    failures = []
    for r in rows:
        if r["outcome_ok"]:
            continue
        bad_fields = [f for f, ok in r["fields"].items() if not ok]
        if r["line_hits"] < r["line_total"]:
            bad_fields.append("line_items")
        if "ERP_UNAVAILABLE" in r["issues"]:
            cause = "ERP unavailable after retries"
        elif r["layout"] == "scan" and r["method"] == "rules":
            cause = "scan with no text layer (needs LLM extractor)"
        elif bad_fields:
            cause = "extraction error: " + ", ".join(bad_fields)
        else:
            cause = "check logic"
        failures.append({**{k: r[k] for k in ("file", "category", "layout", "expected_status", "status",
                                                "expected_reasons", "issues")}, "cause": cause})

    summary = {
        "set": set_name, "extractor": extractor, "erp_fail_rate": erp_fail_rate, "invoices": n,
        "outcome_accuracy": [sum(r["outcome_ok"] for r in rows), n],
        "status_accuracy": [sum(r["status_ok"] for r in rows), n],
        "false_approvals": [len(false_approvals), len(should_not_pay)],
        "clean_auto_approved": [len(auto_approved), len(clean)],
        "field_accuracy_all": field_acc, "field_accuracy_readable": field_acc_readable,
        "line_item_accuracy": lines,
        "by_category": dict(by_cat), "confusion": {f"{a} -> {b}": c for (a, b), c in sorted(confusion.items())},
        "failure_causes": dict(Counter(f["cause"] for f in failures)),
        "failures": failures,
        "avg_ms_per_invoice": round(sum(r["ms"] or 0 for r in rows) / max(n, 1), 1),
        "total_seconds": round(elapsed, 2),
        "methods": dict(Counter(r["method"] for r in rows)),
    }
    return summary


def to_markdown(s: dict) -> str:
    def f(pair):
        return f"{pct(*pair)} ({pair[0]}/{pair[1]})"
    out = [f"# Eval: {s['set']} set, extractor={s['extractor']}, ERP fail rate={s['erp_fail_rate']}", "",
           "| Metric | Result |", "| --- | --- |",
           f"| Correct outcome (status + reasons) | {f(s['outcome_accuracy'])} |",
           f"| Correct status | {f(s['status_accuracy'])} |",
           f"| **False approvals** (should not pay, got approved) | {f(s['false_approvals'])} |",
           f"| Clean invoices auto-approved | {f(s['clean_auto_approved'])} |",
           f"| Line items extracted exactly | {f(s['line_item_accuracy'])} |",
           f"| Avg processing time per invoice | {s['avg_ms_per_invoice']} ms |",
           f"| Extraction methods used | {s['methods']} |", "",
           "## Field accuracy", "", "| Field | All invoices | Readable only (excl. scans) |", "| --- | --- | --- |"]
    for k in FIELDS:
        out.append(f"| {k} | {f(s['field_accuracy_all'][k])} | {f(s['field_accuracy_readable'][k])} |")
    out += ["", "## Outcome by category", "", "| Category | Correct |", "| --- | --- |"]
    for cat, pair in sorted(s["by_category"].items()):
        out.append(f"| {cat} | {f(pair)} |")
    out += ["", "## Expected vs actual status", "", "| Expected -> actual | Count |", "| --- | --- |"]
    out += [f"| {k} | {v} |" for k, v in s["confusion"].items()]
    out += ["", "## Failure causes", "", "| Cause | Count |", "| --- | --- |"]
    out += [f"| {k} | {v} |" for k, v in sorted(s["failure_causes"].items(), key=lambda x: -x[1])] or ["| none | 0 |"]
    if s["failures"]:
        out += ["", "## Failures", "", "| File | Category | Layout | Expected | Got | Issues raised | Cause |",
                "| --- | --- | --- | --- | --- | --- | --- |"]
        for x in s["failures"]:
            out.append(f"| {x['file']} | {x['category']} | {x['layout']} | {x['expected_status']} "
                       f"{x['expected_reasons']} | {x['status']} | {x['issues']} | {x['cause']} |")
    return "\n".join(out) + "\n"


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--set", default="main", choices=["main", "holdout"])
    p.add_argument("--extractor", default="rules", choices=["rules", "auto", "llm"])
    p.add_argument("--erp-fail-rate", type=float, default=0.0)
    a = p.parse_args()

    s = run(a.set, a.extractor, a.erp_fail_rate)
    md = to_markdown(s)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stem = f"{a.set}_{a.extractor}" + (f"_fail{int(a.erp_fail_rate * 100)}" if a.erp_fail_rate else "")
    (RESULTS_DIR / f"{stem}.md").write_text(md)
    (RESULTS_DIR / f"{stem}.json").write_text(json.dumps(s, indent=2))
    print(md)
    print(f"Saved eval/results/{stem}.md and .json")


if __name__ == "__main__":
    main()
