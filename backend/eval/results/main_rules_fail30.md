# Eval: main set, extractor=rules, ERP fail rate=0.3

| Metric | Result |
| --- | --- |
| Correct outcome (status + reasons) | 94.0% (94/100) |
| Correct status | 95.0% (95/100) |
| **False approvals** (should not pay, got approved) | 0.0% (0/54) |
| Clean invoices auto-approved | 89.1% (41/46) |
| Line items extracted exactly | 94.0% (344/366) |
| Avg processing time per invoice | 15.1 ms |
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
| clean | 90.0% (36/40) |
| duplicate | 100.0% (8/8) |
| missing_po | 100.0% (7/7) |
| partial | 83.3% (5/6) |
| price_mismatch | 100.0% (9/9) |
| qty_mismatch | 100.0% (8/8) |
| totals_mismatch | 100.0% (6/6) |
| unknown_po | 80.0% (4/5) |
| unreadable | 100.0% (7/7) |
| vendor_mismatch | 100.0% (4/4) |

## Expected vs actual status

| Expected -> actual | Count |
| --- | --- |
| approved -> approved | 41 |
| approved -> needs_review | 5 |
| needs_review -> needs_review | 46 |
| rejected -> rejected | 8 |

## Failure causes

| Cause | Count |
| --- | --- |
| ERP unavailable after retries | 6 |

## Failures

| File | Category | Layout | Expected | Got | Issues raised | Cause |
| --- | --- | --- | --- | --- | --- | --- |
| main_011.pdf | unknown_po | C | needs_review ['UNKNOWN_PO'] | needs_review | ['ERP_UNAVAILABLE'] | ERP unavailable after retries |
| main_016.pdf | partial | B | approved [] | needs_review | ['ERP_UNAVAILABLE'] | ERP unavailable after retries |
| main_042.pdf | clean | C | approved [] | needs_review | ['ERP_UNAVAILABLE'] | ERP unavailable after retries |
| main_063.pdf | clean | B | approved [] | needs_review | ['ERP_UNAVAILABLE'] | ERP unavailable after retries |
| main_066.pdf | clean | A | approved [] | needs_review | ['ERP_UNAVAILABLE'] | ERP unavailable after retries |
| main_099.pdf | clean | B | approved [] | needs_review | ['ERP_UNAVAILABLE'] | ERP unavailable after retries |
