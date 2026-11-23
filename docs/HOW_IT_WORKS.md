# How it works: a guided tour of the code

Read this with the code open. It follows a single invoice from upload to approval, then covers the design decisions you'll be asked about in interviews.

## 1. Follow one invoice

**Upload.** The UI sends the PDF to `POST /api/invoices` (`app/main.py`, `upload()`). The file is saved to `data/uploads/`, then `InvoiceService.process_file()` takes over.

**`process_file()`** (`app/pipeline.py`) creates a database row with status `processing` and writes an `uploaded` audit event. It then calls `_run()`.

**`_run()`** is the core of the workflow:
1. **Extract** (`app/extraction/__init__.py`, `extract()`):
   - With `EXTRACTOR=auto`, the free rules extractor runs first (`rules.py`). It reads the PDF's text layer with pdfplumber and pulls fields out with patterns.
   - If there's no text or critical fields are missing, and an API key is set, it calls Claude instead (`llm.py`).
   - If extraction crashes, the invoice goes to `needs_review` with `EXTRACTION_FAILED`, never stuck in `processing`.
2. **Check** (`app/matching.py`, `run_checks()`):
   - Local checks run first: readable, duplicate, arithmetic.
   - Then the ERP checks: vendor, PO, lines.
   - Each problem becomes an `Issue(code, message, details)`.
3. **Decide:**
   - `DUPLICATE` → `rejected`.
   - No issues → post to the ERP → `approved`. If the post fails, the invoice goes to `needs_review` with `ERP_UNAVAILABLE`.
   - Anything else → `needs_review`.
4. **Audit:** every step writes an `AuditEvent` row: who, what, from-status, to-status, details.

**Review.** A reviewer opens the invoice in the UI. Each button calls one method on `InvoiceService`:

| Button | Method | Rules it enforces |
|---|---|---|
| Approve & post to ERP | `approve()` | Note required if issues remain; must be postable (known vendor + PO) |
| Reject | `reject()` | Note required |
| Save corrections & re-check | `edit()` | Normalises the values typed in, then re-runs all checks |
| Retry | `retry()` | Re-extracts and re-checks (e.g. after an ERP outage) |
| Undo | `undo()` | Approved → reverses the ERP document; rejected → back to review |

Every method raises `WorkflowError` with an HTTP status when an action isn't allowed. The API turns that into a readable error, and the UI shows it in the red banner.

## 2. The mock ERP

`mock_erp/main.py` is a separate FastAPI app holding vendors, purchase orders and posted invoices in memory (loaded from `data/erp_seed.json`). It tracks how much of each PO line has already been invoiced, which is how `QTY_EXCEEDS_PO` works across several partial invoices.

`app/erp_client.py` is the only code that talks to it. It retries network errors and 5xx responses with backoff (0.2s, 0.4s, 0.8s), and converts every failure into one of three exceptions: `ErpUnavailable`, `ErpNotFound` or `ErpConflict`. The pipeline handles each one explicitly.

To connect a real ERP, you'd replace this one file. That boundary is deliberate.

## 3. The evaluation

`eval/run_eval.py`:
- builds a fresh database and an in-process mock ERP (via FastAPI's `TestClient`, so nothing needs to be running),
- processes every invoice in `data/labels/<set>.json` in order,
- compares the results with the ground truth.

**Metrics it reports and why:**
- **Correct outcome:** right status *and* right reason. Saying "needs review" for the wrong reason wastes the reviewer's time.
- **False approvals:** invoices that shouldn't be paid but were approved. In AP this is the number that matters most, because it means money lost.
- **Clean invoices auto-approved:** the labour saved. Low here means people still do the work.
- **Field accuracy:** per field, with and without scans, so you can tell extraction problems from check-logic problems.
- **Failure causes:** each failure is classified (extraction error, ERP outage, scan, check logic), so you know what to fix next.

`scripts/generate_dataset.py` creates the data. Each scenario type (`clean`, `price_mismatch`, `duplicate`, `unreadable`…) has a known correct outcome. The **holdout** set uses a 4th layout the rules extractor was never written for. That gives an honest measure of how extraction generalizes.

## 4. Design decisions (interview talking points)

1. **The LLM reads; code decides.** Extraction can be fuzzy; approval cannot. A hallucinated number fails the arithmetic or PO check and goes to a human.
2. **Fail safe, never silent.** Every exception path ends in `needs_review` with a reason. Nothing is approved when unsure, and nothing is left in `processing`.
3. **Local checks before remote ones.** The flaky-ERP eval found that duplicate detection depended on the ERP. Moving it before any ERP call fixed it, and the eval guards against a regression.
4. **Cheap first, expensive when needed.** Rules cost nothing and take ~15 ms. The LLM is called only for documents the rules can't read.
5. **Undo is a real reversal.** Undoing an approval reverses the ERP document and releases the PO quantities. It doesn't just change a label.
6. **Overrides need a reason.** Approving despite open issues requires a note, which the audit log stores alongside the overridden issue codes.
7. **One boundary per external system.** `erp_client.py` for the ERP and `extraction/` for document reading. Swapping either one touches one place.

## 5. Exercises to learn the code

1. **Add a check:** flag invoices dated in the future (`FUTURE_DATE`). Add it to `matching.py` and `ISSUE_CODES`, add a test, and run the eval.
2. **Make it stricter:** set `PRICE_TOLERANCE_PCT=0` in `.env`. Which clean invoices now fail, and why?
3. **Break the ERP:** run `ERP_FAIL_RATE=0.5 uvicorn mock_erp.main:app --port 8001`, load samples, then use Retry once it recovers.
4. **Teach the rules a new layout:** make the holdout set pass with the rules extractor by editing `rules.py`. Then ask yourself whether that's a good idea compared with using the LLM (it isn't for every new vendor, which is the point).
5. **Turn on the LLM** and run `python -m eval.run_eval --set holdout --extractor auto`. Record the accuracy and cost.
