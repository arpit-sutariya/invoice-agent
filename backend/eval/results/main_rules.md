# Eval: main set, extractor=rules, ERP fail rate=0.0

| Metric | Result |
| --- | --- |
| Correct outcome (status + reasons) | 100.0% (100/100) |
| Correct status | 100.0% (100/100) |
| **False approvals** (should not pay, got approved) | 0.0% (0/54) |
| Clean invoices auto-approved | 100.0% (46/46) |
| Line items extracted exactly | 94.0% (344/366) |
| Avg processing time per invoice | 15.5 ms |
| Extraction methods used | {'rules': 100} |

## Field accuracy

| Field | All invoices | Readable only (excl. scans) |
| --- | --- | --- |
| vendor_name | 93.0% (93/100) | 100.0% (93/93) |
| invoice_number | 93.0% (93/100) | 100.0% (93/93) |
| invoice_date | 93.0% (93/100) | 100.0% (93/93) |
| po_number | 93.0% (93/100) | 100.0% (93/93) |
| subtotal | 93.0% (93/100) | 100.0% (93/93) |
| tax | 93.0% (93/100) | 100.0% (93/93) |
| total | 93.0% (93/100) | 100.0% (93/93) |

## Outcome by category

| Category | Correct |
| --- | --- |
| clean | 100.0% (40/40) |
| duplicate | 100.0% (8/8) |
| missing_po | 100.0% (7/7) |
| partial | 100.0% (6/6) |
| price_mismatch | 100.0% (9/9) |
| qty_mismatch | 100.0% (8/8) |
| totals_mismatch | 100.0% (6/6) |
| unknown_po | 100.0% (5/5) |
| unreadable | 100.0% (7/7) |
| vendor_mismatch | 100.0% (4/4) |

## Expected vs actual status

| Expected -> actual | Count |
| --- | --- |
| approved -> approved | 46 |
| needs_review -> needs_review | 46 |
| rejected -> rejected | 8 |

## Failure causes

| Cause | Count |
| --- | --- |
| none | 0 |
