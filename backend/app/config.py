"""All settings come from environment variables (or backend/.env). See .env.example."""
from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{BACKEND_DIR / 'data' / 'app.db'}")
    upload_dir: Path = Path(os.getenv("UPLOAD_DIR", str(BACKEND_DIR / "data" / "uploads")))
    sample_dir: Path = BACKEND_DIR / "data" / "invoices" / "main"
    erp_base_url: str = os.getenv("ERP_BASE_URL", "http://localhost:8001")
    erp_timeout_s: float = float(os.getenv("ERP_TIMEOUT_S", "5"))
    erp_retries: int = int(os.getenv("ERP_RETRIES", "3"))
    # rules | llm | auto  (auto = rules first, LLM fallback when rules can't read the invoice)
    extractor: str = os.getenv("EXTRACTOR", "auto")
    anthropic_api_key: str | None = os.getenv("ANTHROPIC_API_KEY") or None
    llm_model: str = os.getenv("LLM_MODEL", "claude-haiku-5-5")
    auto_approve: bool = os.getenv("AUTO_APPROVE", "true").lower() == "true"
    # a unit price may differ from the PO by this percentage before it is flagged
    price_tolerance_pct: Decimal = Decimal(os.getenv("PRICE_TOLERANCE_PCT", "0.5"))
    # arithmetic checks allow this much rounding difference
    amount_tolerance: Decimal = Decimal(os.getenv("AMOUNT_TOLERANCE", "0.02"))


settings = Settings()
