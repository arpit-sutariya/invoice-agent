"""Generate a synthetic but realistic invoice dataset.

Creates:
  data/erp_seed.json             vendors + purchase orders loaded by the mock ERP
  data/invoices/main/*.pdf       100 invoices in 3 layouts (A, B, C) with messy cases
  data/invoices/holdout/*.pdf    20 invoices in a 4th layout (D) the rules extractor never saw
  data/labels/main.json          ground truth for every main invoice
  data/labels/holdout.json       ground truth for every holdout invoice

Run from backend/:  python -m scripts.generate_dataset
Deterministic: the same seed always produces the same files.
"""
from __future__ import annotations

import copy
import json
import random
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SEED = 42

VENDORS = [
    {"id": "V001", "name": "Acme Industrial Supply", "prefix": "ACM", "tax": "8.25",
     "address": ["1200 Foundry Rd", "Fresno, CA 93721"], "inv_fmt": "INV-{n:05d}"},
    {"id": "V002", "name": "Northwind Packaging Co.", "prefix": "NWP", "tax": "7.25",
     "address": ["88 Harbor Way", "Oakland, CA 94607"], "inv_fmt": "NW-2026-{n:04d}"},
    {"id": "V003", "name": "Bluebird Office Products", "prefix": "BOP", "tax": "8.875",
     "address": ["410 Lexington Ave", "New York, NY 10017"], "inv_fmt": "{n:06d}"},
    {"id": "V004", "name": "Summit Safety Gear LLC", "prefix": "SSG", "tax": "0",
     "address": ["9 Ridge Park Dr", "Bend, OR 97701"], "inv_fmt": "SSG{n:05d}"},
    {"id": "V005", "name": "Harbor Electrical Wholesale", "prefix": "HEW", "tax": "8.25",
     "address": ["3300 Pier Ave", "Long Beach, CA 90802"], "inv_fmt": "HEW-{n:05d}"},
    {"id": "V006", "name": "Pinecrest Janitorial Supplies", "prefix": "PJS", "tax": "7.25",
     "address": ["15 Cedar Ln", "Sacramento, CA 95814"], "inv_fmt": "PJ-{n:04d}"},
    {"id": "V007", "name": "Redline Fasteners Inc.", "prefix": "RLF", "tax": "6.0",
     "address": ["700 Industrial Blvd", "Reno, NV 89502"], "inv_fmt": "RF{n:06d}"},
    {"id": "V008", "name": "Cobalt IT Hardware", "prefix": "CIT", "tax": "8.25",
     "address": ["55 Market St", "San Jose, CA 95113"], "inv_fmt": "CIT-26-{n:04d}"},
]

PRODUCTS = {
    "ACM": [("Steel Shelving Unit 72in", "189.00"), ("Pallet Jack Wheel Kit", "64.50"),
            ("Heavy Duty Hand Truck", "142.00"), ("Shop Vacuum Filter", "18.75"),
            ("Industrial Floor Mat", "56.20"), ("Wire Bin Rack", "97.40")],
    "NWP": [("Corrugated Box 18x12x12", "1.85"), ("Stretch Wrap Roll", "22.40"),
            ("Packing Tape Case", "48.00"), ("Bubble Mailer 10x13", "0.62"),
            ("Void Fill Paper Roll", "39.90"), ("Pallet Corner Board", "0.95")],
    "BOP": [("Copy Paper Case", "44.99"), ("Ballpoint Pens Box", "6.49"),
            ("Ergonomic Desk Chair", "219.00"), ("Whiteboard 4x6", "128.50"),
            ("Toner Cartridge Black", "86.30"), ("File Folders Box", "14.25")],
    "SSG": [("Hard Hat Class E", "24.60"), ("Safety Glasses Clear", "4.10"),
            ("Hi-Vis Vest Class 2", "9.85"), ("Cut Resistant Gloves", "11.40"),
            ("Ear Plugs Dispenser Refill", "52.00"), ("First Aid Kit 50 Person", "74.95")],
    "HEW": [("THHN Wire 12 AWG Spool", "118.00"), ("LED Panel Light 2x4", "62.75"),
            ("GFCI Outlet 20A", "17.90"), ("Conduit EMT 10ft", "8.45"),
            ("Breaker 20A Single Pole", "11.20"), ("Junction Box Steel", "3.65")],
    "PJS": [("Trash Liner Case", "38.50"), ("Floor Cleaner Concentrate", "27.80"),
            ("Microfiber Mop Head", "6.95"), ("Paper Towel Case", "45.60"),
            ("Hand Soap Refill", "19.40"), ("Disinfectant Spray Case", "64.00")],
    "RLF": [("Hex Bolt Box 100", "21.30"), ("Lock Washer Box 500", "12.80"),
            ("Anchor Kit Concrete", "33.15"), ("Machine Screw Assortment", "27.60"),
            ("Threaded Rod 3ft", "5.70"), ("Rivet Box 250", "16.90")],
    "CIT": [("USB-C Dock", "149.00"), ("27in Monitor", "229.00"),
            ("Wireless Keyboard", "39.99"), ("Cat6 Patch Cable 10ft", "4.25"),
            ("Laptop Sleeve 15in", "18.50"), ("Network Switch 24 Port", "189.00")],
}

CENT = Decimal("0.01")


def money(x) -> Decimal:
    return Decimal(str(x)).quantize(CENT, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Building invoice specs (the ground truth)
# ---------------------------------------------------------------------------

class Builder:
    def __init__(self, rng: random.Random):
        self.rng = rng
        self.po_counter = 0
        self.inv_counters = {v["id"]: rng.randint(100, 900) for v in VENDORS}
        self.purchase_orders: list[dict] = []

    def vendor(self):
        return self.rng.choice(VENDORS)

    def new_po(self, vendor, n_lines=None) -> dict:
        self.po_counter += 1
        n_lines = n_lines or self.rng.randint(2, 5)
        items = self.rng.sample(range(6), n_lines)
        lines = []
        for idx in items:
            desc, price = PRODUCTS[vendor["prefix"]][idx]
            lines.append({
                "sku": f"{vendor['prefix']}-{1000 + idx * 37:04d}",
                "description": desc,
                "quantity": self.rng.choice([5, 10, 12, 20, 24, 25, 40, 50, 60, 100, 150, 200]),
                "unit_price": price,
            })
        po = {"po_number": f"PO-2026-{self.po_counter:04d}", "vendor_id": vendor["id"],
              "issued": str(date(2026, 8, 1) + timedelta(days=self.rng.randint(0, 60))),
              "lines": lines}
        self.purchase_orders.append(po)
        return po

    def invoice_from_po(self, vendor, po, category: str) -> dict:
        self.inv_counters[vendor["id"]] += self.rng.randint(1, 9)
        inv_no = vendor["inv_fmt"].format(n=self.inv_counters[vendor["id"]])
        inv_date = date(2026, 9, 1) + timedelta(days=self.rng.randint(0, 75))
        lines = [{"sku": l["sku"], "description": l["description"],
                  "quantity": l["quantity"], "unit_price": l["unit_price"]} for l in po["lines"]]
        return {"category": category, "vendor_id": vendor["id"], "vendor_name": vendor["name"],
                "invoice_number": inv_no, "invoice_date": str(inv_date),
                "po_number": po["po_number"], "currency": "USD", "tax_rate": vendor["tax"],
                "line_items": lines}


def finalize(inv: dict, total_override: Decimal | None = None) -> dict:
    """Compute amounts, subtotal, tax and total from the line items."""
    subtotal = Decimal("0")
    for li in inv["line_items"]:
        amt = money(Decimal(li["unit_price"]) * li["quantity"])
        li["amount"] = str(amt)
        li["unit_price"] = str(money(li["unit_price"]))
        subtotal += amt
    tax = money(subtotal * Decimal(inv["tax_rate"]) / 100)
    total = subtotal + tax
    inv["subtotal"] = str(money(subtotal))
    inv["tax"] = str(tax)
    inv["total"] = str(money(total_override if total_override is not None else total))
    return inv


EXPECTED = {
    "clean": ("approved", []),
    "partial": ("approved", []),
    "price_mismatch": ("needs_review", ["PRICE_MISMATCH"]),
    "qty_mismatch": ("needs_review", ["QTY_EXCEEDS_PO"]),
    "missing_po": ("needs_review", ["MISSING_PO"]),
    "unknown_po": ("needs_review", ["UNKNOWN_PO"]),
    "vendor_mismatch": ("needs_review", ["VENDOR_MISMATCH"]),
    "totals_mismatch": ("needs_review", ["TOTALS_MISMATCH"]),
    "duplicate": ("rejected", ["DUPLICATE"]),
    "unreadable": ("needs_review", ["UNREADABLE"]),
}


def build_specs(b: Builder, plan: dict[str, int]) -> list[dict]:
    rng = b.rng
    specs: list[dict] = []
    approved_pool: list[dict] = []
    order = [c for c, n in plan.items() if c != "duplicate" for _ in range(n)]
    rng.shuffle(order)
    # duplicates are inserted later in the sequence, after their originals
    n_dupes = plan.get("duplicate", 0)

    for cat in order:
        v = b.vendor()
        if cat == "unknown_po":
            po = b.new_po(v)
            b.purchase_orders.pop()  # never sent to the ERP
            po["po_number"] = f"PO-2026-{rng.randint(9000, 9999):04d}"
            inv = finalize(b.invoice_from_po(v, po, cat))
        elif cat == "vendor_mismatch":
            other = rng.choice([x for x in VENDORS if x["id"] != v["id"]])
            other_po = b.new_po(other)
            own_po = b.new_po(v)
            b.purchase_orders.pop()  # invoice lines look normal, but quote another vendor's PO
            inv = b.invoice_from_po(v, own_po, cat)
            inv["po_number"] = other_po["po_number"]
            inv = finalize(inv)
        else:
            po = b.new_po(v)
            inv = b.invoice_from_po(v, po, cat)
            if cat == "partial":
                if len(inv["line_items"]) > 2 and rng.random() < 0.5:
                    inv["line_items"] = inv["line_items"][: len(inv["line_items"]) - 1]
                else:
                    li = rng.choice(inv["line_items"])
                    li["quantity"] = max(1, li["quantity"] // 2)
            elif cat == "price_mismatch":
                li = rng.choice(inv["line_items"])
                li["unit_price"] = str(money(Decimal(li["unit_price"]) * Decimal(str(rng.uniform(1.03, 1.15)))))
            elif cat == "qty_mismatch":
                li = rng.choice(inv["line_items"])
                li["quantity"] += rng.randint(2, 20)
            elif cat == "missing_po":
                inv["po_number"] = None
            inv = finalize(inv)
            if cat == "totals_mismatch":
                inv["total"] = str(money(Decimal(inv["total"]) + Decimal(rng.randint(10, 250))))
        status, reasons = EXPECTED[cat]
        inv["expected_status"], inv["expected_reasons"] = status, reasons
        specs.append(inv)
        if cat in ("clean",):
            approved_pool.append(inv)

    # Insert duplicates: an exact resubmission of an earlier clean invoice
    for _ in range(n_dupes):
        original = rng.choice(approved_pool)
        pos = specs.index(original)
        dup = copy.deepcopy(original)
        dup["category"] = "duplicate"
        dup["expected_status"], dup["expected_reasons"] = EXPECTED["duplicate"]
        dup["duplicate_of"] = original["invoice_number"]
        insert_at = rng.randint(pos + 1, len(specs))
        specs.insert(insert_at, dup)
    return specs


# ---------------------------------------------------------------------------
# PDF rendering: 4 layouts
# ---------------------------------------------------------------------------

def fmt_money(x: str, style: str) -> str:
    d = Decimal(x)
    if style == "dollar":
        return f"${d:,.2f}"
    if style == "usd":
        return f"USD {d:,.2f}"
    return f"{d:.2f}"


def fmt_date(iso: str, style: str) -> str:
    d = date.fromisoformat(iso)
    if style == "us":
        return d.strftime("%m/%d/%Y")
    if style == "long":
        return f"{d.strftime('%b')} {d.day}, {d.year}"
    if style == "dmy":
        return d.strftime("%d %B %Y")
    return iso


def vendor_of(inv):
    return next(v for v in VENDORS if v["id"] == inv["vendor_id"])


def render_a(c: canvas.Canvas, inv: dict):
    """Layout A: classic. Vendor name on top, labelled fields, SKU-first table."""
    v = vendor_of(inv)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, 740, v["name"])
    c.setFont("Helvetica", 9)
    c.drawString(50, 726, v["address"][0])
    c.drawString(50, 714, v["address"][1])
    c.setFont("Helvetica-Bold", 22)
    c.drawRightString(560, 740, "INVOICE")
    c.setFont("Helvetica", 10)
    c.drawString(360, 700, f"Invoice Number: {inv['invoice_number']}")
    c.drawString(360, 686, f"Invoice Date: {fmt_date(inv['invoice_date'], 'iso')}")
    if inv["po_number"]:
        c.drawString(360, 672, f"PO Number: {inv['po_number']}")
    c.drawString(50, 672, "Bill To: Lakeside Manufacturing Inc.")
    y = 630
    c.setFont("Helvetica-Bold", 10)
    for x, h in [(50, "SKU"), (130, "Description"), (360, "Qty"), (420, "Unit Price"), (500, "Amount")]:
        c.drawString(x, y, h)
    c.line(50, y - 4, 560, y - 4)
    c.setFont("Helvetica", 10)
    for li in inv["line_items"]:
        y -= 18
        c.drawString(50, y, li["sku"])
        c.drawString(130, y, li["description"])
        c.drawRightString(385, y, str(li["quantity"]))
        c.drawRightString(475, y, fmt_money(li["unit_price"], "plain"))
        c.drawRightString(560, y, fmt_money(li["amount"], "plain"))
    y -= 30
    c.drawString(400, y, f"Subtotal: {fmt_money(inv['subtotal'], 'dollar')}")
    c.drawString(400, y - 16, f"Tax ({inv['tax_rate']}%): {fmt_money(inv['tax'], 'dollar')}")
    c.setFont("Helvetica-Bold", 11)
    c.drawString(400, y - 34, f"Total Due: {fmt_money(inv['total'], 'dollar')}")
    c.setFont("Helvetica", 8)
    c.drawString(50, 80, "Payment terms: Net 30. Please reference the invoice number with your payment.")


def render_b(c: canvas.Canvas, inv: dict):
    """Layout B: 'TAX INVOICE', supplier block, US dates, USD amounts."""
    v = vendor_of(inv)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(50, 745, "TAX INVOICE")
    c.setFont("Helvetica", 10)
    c.drawString(50, 715, f"Supplier: {v['name']}")
    c.drawString(50, 701, f"{v['address'][0]}, {v['address'][1]}")
    c.drawString(370, 715, f"Invoice #: {inv['invoice_number']}")
    c.drawString(370, 701, f"Date: {fmt_date(inv['invoice_date'], 'us')}")
    if inv["po_number"]:
        c.drawString(370, 687, f"Purchase Order: {inv['po_number']}")
    c.drawString(50, 670, "Customer: Lakeside Manufacturing Inc. / Accounts Payable")
    y = 630
    c.setFont("Helvetica-Bold", 9)
    for x, h in [(50, "Item Code"), (130, "Item"), (360, "Quantity"), (430, "Rate"), (505, "Line Total")]:
        c.drawString(x, y, h)
    c.setFont("Helvetica", 9)
    for li in inv["line_items"]:
        y -= 16
        c.drawString(50, y, li["sku"])
        c.drawString(130, y, li["description"])
        c.drawRightString(395, y, str(li["quantity"]))
        c.drawRightString(465, y, fmt_money(li["unit_price"], "plain"))
        c.drawRightString(555, y, f"{Decimal(li['amount']):,.2f}")
    y -= 34
    c.setFont("Helvetica", 10)
    c.drawString(380, y, f"Sub-total {fmt_money(inv['subtotal'], 'usd')}")
    c.drawString(380, y - 16, f"Sales Tax {fmt_money(inv['tax'], 'usd')}")
    c.setFont("Helvetica-Bold", 11)
    c.drawString(380, y - 34, f"Amount Due {fmt_money(inv['total'], 'usd')}")


def render_c(c: canvas.Canvas, inv: dict):
    """Layout C: messier. 'Bill', 'From:', long dates, description-first table, PO written with a space."""
    v = vendor_of(inv)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, 745, "Bill")
    c.setFont("Helvetica", 10)
    c.drawString(50, 722, f"From: {v['name']}")
    c.drawString(50, 708, v["address"][1])
    c.drawString(330, 745, f"Bill No. {inv['invoice_number']}")
    c.drawString(330, 731, f"Issued {fmt_date(inv['invoice_date'], 'long')}")
    if inv["po_number"]:
        c.drawString(330, 717, f"Your Order Ref {inv['po_number'].replace('PO-', 'PO ')}")
    y = 660
    c.setFont("Helvetica-Oblique", 9)
    for x, h in [(50, "Description"), (270, "Code"), (350, "Qty"), (410, "Price"), (490, "Total")]:
        c.drawString(x, y, h)
    c.setFont("Helvetica", 9)
    for li in inv["line_items"]:
        y -= 15
        c.drawString(50, y, li["description"])
        c.drawString(270, y, li["sku"])
        c.drawString(350, y, str(li["quantity"]))
        c.drawString(410, y, fmt_money(li["unit_price"], "plain"))
        c.drawString(490, y, fmt_money(li["amount"], "plain"))
    y -= 30
    c.drawString(410, y, f"Net {fmt_money(inv['subtotal'], 'plain')}")
    c.drawString(410, y - 14, f"VAT/Tax {fmt_money(inv['tax'], 'plain')}")
    c.setFont("Helvetica-Bold", 10)
    c.drawString(410, y - 30, f"TOTAL {fmt_money(inv['total'], 'plain')}")
    c.setFont("Helvetica", 7)
    c.drawString(50, 60, "Thank you for your business. Late payments subject to 1.5% monthly charge.")


def render_d(c: canvas.Canvas, inv: dict):
    """Layout D (holdout): unfamiliar labels, quantity-first table, day-month-year dates."""
    v = vendor_of(inv)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, 750, "STATEMENT OF CHARGES")
    c.setFont("Helvetica", 9)
    c.drawString(50, 734, "Lakeside Manufacturing Inc. - Accounts Payable Dept.")
    c.drawRightString(560, 750, v["name"])
    c.drawRightString(560, 738, v["address"][0])
    c.drawRightString(560, 726, v["address"][1])
    c.drawString(50, 700, f"Ref: {inv['invoice_number']}")
    c.drawString(200, 700, f"Dated {fmt_date(inv['invoice_date'], 'dmy')}")
    if inv["po_number"]:
        c.drawString(380, 700, f"Ordered under {inv['po_number'].replace('-', '/')}")
    y = 660
    c.setFont("Helvetica-Bold", 9)
    for x, h in [(50, "Units"), (100, "Part"), (180, "Details"), (420, "Each"), (500, "Ext.")]:
        c.drawString(x, y, h)
    c.setFont("Helvetica", 9)
    for li in inv["line_items"]:
        y -= 15
        c.drawString(50, y, str(li["quantity"]))
        c.drawString(100, y, li["sku"].replace("-", ""))
        c.drawString(180, y, li["description"])
        c.drawString(420, y, f"{Decimal(li['unit_price']):,.2f}")
        c.drawString(500, y, f"{Decimal(li['amount']):,.2f}")
    y -= 30
    c.drawString(380, y, f"Goods {Decimal(inv['subtotal']):,.2f}")
    c.drawString(380, y - 14, f"Levies {Decimal(inv['tax']):,.2f}")
    c.setFont("Helvetica-Bold", 10)
    c.drawString(380, y - 30, f"Please pay {Decimal(inv['total']):,.2f} USD")


def render_scanned(path: Path, inv: dict, rng: random.Random):
    """An image-only PDF: looks like a phone photo of a printout, no text layer."""
    img = Image.new("L", (1275, 1650), 235)
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 26)
    except OSError:  # font not installed (e.g. macOS/Windows): use Pillow's built-in one
        try:
            font = ImageFont.load_default(size=26)
        except TypeError:
            font = ImageFont.load_default()
    v = vendor_of(inv)
    y = 120
    for line in [v["name"], "INVOICE", f"Invoice Number: {inv['invoice_number']}",
                 f"Invoice Date: {inv['invoice_date']}",
                 f"PO Number: {inv['po_number'] or ''}", ""] + \
                [f"{li['sku']}  {li['description']}  {li['quantity']}  {li['unit_price']}  {li['amount']}"
                 for li in inv["line_items"]] + ["", f"Total Due: ${Decimal(inv['total']):,.2f}"]:
        d.text((110, y), line, fill=40, font=font)
        y += 48
    img = img.rotate(rng.uniform(-3, 3), fillcolor=200).filter(ImageFilter.GaussianBlur(1.4))
    c = canvas.Canvas(str(path), pagesize=letter)
    c.drawImage(ImageReader(img), 0, 0, width=612, height=792)
    c.save()


RENDERERS = {"A": render_a, "B": render_b, "C": render_c, "D": render_d}


def write_set(name: str, specs: list[dict], layouts: list[str], rng: random.Random):
    out = DATA / "invoices" / name
    out.mkdir(parents=True, exist_ok=True)
    for f in out.glob("*.pdf"):
        f.unlink()
    labels = []
    for i, inv in enumerate(specs, start=1):
        fname = f"{name}_{i:03d}.pdf"
        layout = rng.choice(layouts)
        path = out / fname
        if inv["category"] == "unreadable":
            layout = "scan"
            render_scanned(path, inv, rng)
        else:
            c = canvas.Canvas(str(path), pagesize=letter)
            RENDERERS[layout](c, inv)
            c.save()
        label = {k: inv[k] for k in ("category", "expected_status", "expected_reasons", "vendor_id",
                                     "vendor_name", "invoice_number", "invoice_date", "po_number",
                                     "currency", "subtotal", "tax", "total", "line_items")}
        label["file"] = fname
        label["layout"] = layout
        if "duplicate_of" in inv:
            label["duplicate_of"] = inv["duplicate_of"]
        labels.append(label)
    (DATA / "labels").mkdir(parents=True, exist_ok=True)
    (DATA / "labels" / f"{name}.json").write_text(json.dumps(labels, indent=2))
    return labels


def main():
    rng = random.Random(SEED)
    b = Builder(rng)
    main_plan = {"clean": 40, "partial": 6, "price_mismatch": 9, "qty_mismatch": 8, "missing_po": 7,
                 "unknown_po": 5, "vendor_mismatch": 4, "totals_mismatch": 6, "duplicate": 8,
                 "unreadable": 7}
    holdout_plan = {"clean": 12, "price_mismatch": 3, "missing_po": 2, "totals_mismatch": 3}
    main_specs = build_specs(b, main_plan)
    holdout_specs = build_specs(b, holdout_plan)

    main_labels = write_set("main", main_specs, ["A", "B", "C"], rng)
    holdout_labels = write_set("holdout", holdout_specs, ["D"], rng)

    seed = {"vendors": [{"id": v["id"], "name": v["name"], "address": ", ".join(v["address"])}
                        for v in VENDORS],
            "purchase_orders": b.purchase_orders}
    (DATA / "erp_seed.json").write_text(json.dumps(seed, indent=2))

    from collections import Counter
    print(f"main:    {len(main_labels)} invoices  {dict(Counter(l['category'] for l in main_labels))}")
    print(f"holdout: {len(holdout_labels)} invoices  {dict(Counter(l['category'] for l in holdout_labels))}")
    print(f"ERP seed: {len(seed['vendors'])} vendors, {len(seed['purchase_orders'])} purchase orders")


if __name__ == "__main__":
    main()
