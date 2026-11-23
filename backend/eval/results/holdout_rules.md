# Eval: holdout set, extractor=rules, ERP fail rate=0.0

| Metric | Result |
| --- | --- |
| Correct outcome (status + reasons) | 10.0% (2/20) |
| Correct status | 40.0% (8/20) |
| **False approvals** (should not pay, got approved) | 0.0% (0/8) |
| Clean invoices auto-approved | 0.0% (0/12) |
| Line items extracted exactly | 0.0% (0/72) |
| Avg processing time per invoice | 8.3 ms |
| Extraction methods used | {'rules': 20} |

## Field accuracy

| Field | All invoices | Readable only (excl. scans) |
| --- | --- | --- |
| vendor_name | 0.0% (0/20) | 0.0% (0/20) |
| invoice_number | 0.0% (0/20) | 0.0% (0/20) |
| invoice_date | 0.0% (0/20) | 0.0% (0/20) |
| po_number | 10.0% (2/20) | 10.0% (2/20) |
| subtotal | 0.0% (0/20) | 0.0% (0/20) |
| tax | 0.0% (0/20) | 0.0% (0/20) |
| total | 0.0% (0/20) | 0.0% (0/20) |

## Outcome by category

| Category | Correct |
| --- | --- |
| clean | 0.0% (0/12) |
| missing_po | 100.0% (2/2) |
| price_mismatch | 0.0% (0/3) |
| totals_mismatch | 0.0% (0/3) |

## Expected vs actual status

| Expected -> actual | Count |
| --- | --- |
| approved -> needs_review | 12 |
| needs_review -> needs_review | 8 |

## Failure causes

| Cause | Count |
| --- | --- |
| extraction error: vendor_name, invoice_number, invoice_date, po_number, subtotal, tax, total, line_items | 18 |

## Failures

| File | Category | Layout | Expected | Got | Issues raised | Cause |
| --- | --- | --- | --- | --- | --- | --- |
| holdout_001.pdf | clean | D | approved [] | needs_review | ['MISSING_FIELDS', 'UNKNOWN_VENDOR', 'MISSING_PO'] | extraction error: vendor_name, invoice_number, invoice_date, po_number, subtotal, tax, total, line_items |
| holdout_002.pdf | clean | D | approved [] | needs_review | ['MISSING_FIELDS', 'UNKNOWN_VENDOR', 'MISSING_PO'] | extraction error: vendor_name, invoice_number, invoice_date, po_number, subtotal, tax, total, line_items |
| holdout_003.pdf | clean | D | approved [] | needs_review | ['MISSING_FIELDS', 'UNKNOWN_VENDOR', 'MISSING_PO'] | extraction error: vendor_name, invoice_number, invoice_date, po_number, subtotal, tax, total, line_items |
| holdout_004.pdf | totals_mismatch | D | needs_review ['TOTALS_MISMATCH'] | needs_review | ['MISSING_FIELDS', 'UNKNOWN_VENDOR', 'MISSING_PO'] | extraction error: vendor_name, invoice_number, invoice_date, po_number, subtotal, tax, total, line_items |
| holdout_005.pdf | clean | D | approved [] | needs_review | ['MISSING_FIELDS', 'UNKNOWN_VENDOR', 'MISSING_PO'] | extraction error: vendor_name, invoice_number, invoice_date, po_number, subtotal, tax, total, line_items |
| holdout_006.pdf | clean | D | approved [] | needs_review | ['MISSING_FIELDS', 'UNKNOWN_VENDOR', 'MISSING_PO'] | extraction error: vendor_name, invoice_number, invoice_date, po_number, subtotal, tax, total, line_items |
| holdout_007.pdf | totals_mismatch | D | needs_review ['TOTALS_MISMATCH'] | needs_review | ['MISSING_FIELDS', 'UNKNOWN_VENDOR', 'MISSING_PO'] | extraction error: vendor_name, invoice_number, invoice_date, po_number, subtotal, tax, total, line_items |
| holdout_008.pdf | clean | D | approved [] | needs_review | ['MISSING_FIELDS', 'UNKNOWN_VENDOR', 'MISSING_PO'] | extraction error: vendor_name, invoice_number, invoice_date, po_number, subtotal, tax, total, line_items |
| holdout_009.pdf | price_mismatch | D | needs_review ['PRICE_MISMATCH'] | needs_review | ['MISSING_FIELDS', 'UNKNOWN_VENDOR', 'MISSING_PO'] | extraction error: vendor_name, invoice_number, invoice_date, po_number, subtotal, tax, total, line_items |
| holdout_010.pdf | totals_mismatch | D | needs_review ['TOTALS_MISMATCH'] | needs_review | ['MISSING_FIELDS', 'UNKNOWN_VENDOR', 'MISSING_PO'] | extraction error: vendor_name, invoice_number, invoice_date, po_number, subtotal, tax, total, line_items |
| holdout_011.pdf | clean | D | approved [] | needs_review | ['MISSING_FIELDS', 'UNKNOWN_VENDOR', 'MISSING_PO'] | extraction error: vendor_name, invoice_number, invoice_date, po_number, subtotal, tax, total, line_items |
| holdout_012.pdf | price_mismatch | D | needs_review ['PRICE_MISMATCH'] | needs_review | ['MISSING_FIELDS', 'UNKNOWN_VENDOR', 'MISSING_PO'] | extraction error: vendor_name, invoice_number, invoice_date, po_number, subtotal, tax, total, line_items |
| holdout_013.pdf | clean | D | approved [] | needs_review | ['MISSING_FIELDS', 'UNKNOWN_VENDOR', 'MISSING_PO'] | extraction error: vendor_name, invoice_number, invoice_date, po_number, subtotal, tax, total, line_items |
| holdout_014.pdf | clean | D | approved [] | needs_review | ['MISSING_FIELDS', 'UNKNOWN_VENDOR', 'MISSING_PO'] | extraction error: vendor_name, invoice_number, invoice_date, po_number, subtotal, tax, total, line_items |
| holdout_016.pdf | clean | D | approved [] | needs_review | ['MISSING_FIELDS', 'UNKNOWN_VENDOR', 'MISSING_PO'] | extraction error: vendor_name, invoice_number, invoice_date, po_number, subtotal, tax, total, line_items |
| holdout_017.pdf | price_mismatch | D | needs_review ['PRICE_MISMATCH'] | needs_review | ['MISSING_FIELDS', 'UNKNOWN_VENDOR', 'MISSING_PO'] | extraction error: vendor_name, invoice_number, invoice_date, po_number, subtotal, tax, total, line_items |
| holdout_018.pdf | clean | D | approved [] | needs_review | ['MISSING_FIELDS', 'UNKNOWN_VENDOR', 'MISSING_PO'] | extraction error: vendor_name, invoice_number, invoice_date, po_number, subtotal, tax, total, line_items |
| holdout_020.pdf | clean | D | approved [] | needs_review | ['MISSING_FIELDS', 'UNKNOWN_VENDOR', 'MISSING_PO'] | extraction error: vendor_name, invoice_number, invoice_date, po_number, subtotal, tax, total, line_items |
