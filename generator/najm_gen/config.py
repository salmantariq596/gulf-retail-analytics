"""Profiles, paths and constants shared by the generator."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")


@dataclass(frozen=True)
class Profile:
    name: str
    n_products: int
    n_customers_initial: int       # loyalty + online accounts existing before day 1
    organic_customers_per_day: float
    pos_lines_per_day: float       # all physical stores, before seasonality
    online_orders_per_day: float   # all countries, before seasonality
    marketing_aed_per_day: float   # baseline always-on spend, all channels
    history_days: int


PROFILES: dict[str, Profile] = {
    # ~5 weeks at a fraction of dev volume: the end-to-end check in GitHub Actions
    "ci": Profile("ci", 600, 6_000, 6, 700, 70, 5_000, 35),
    # ~3 months, small enough to iterate on in seconds-to-minutes
    "dev": Profile("dev", 3_000, 40_000, 25, 4_000, 400, 20_000, 92),
    # Target scale from the plan: 3 years, ~20M POS lines, ~2M online orders,
    # 15k products, ~500k customers
    "full": Profile("full", 15_000, 200_000, 120, 18_000, 1_800, 90_000, 1_096),
}


def default_end_date() -> date:
    """Yesterday — keeps source freshness checks meaningful."""
    return date.today() - timedelta(days=1)


# ---- Paths -----------------------------------------------------------------
DATA_DIR = REPO_ROOT / "data"
LANDING_DIR = Path(os.getenv("GEN_OUTPUT_DIR", DATA_DIR / "landing"))
if not LANDING_DIR.is_absolute():
    LANDING_DIR = (REPO_ROOT / LANDING_DIR).resolve()
STATE_PATH = Path(os.getenv("GEN_STATE_PATH", DATA_DIR / "generator_state" / "state.pkl"))
if not STATE_PATH.is_absolute():
    STATE_PATH = (REPO_ROOT / STATE_PATH).resolve()
ONLINE_DB_PATH = LANDING_DIR / "online" / "online.db"
POS_SCHEMA_SQL = REPO_ROOT / "generator" / "sql" / "01_pos_schema.sql"


def postgres_dsn() -> str:
    return (
        f"host={os.getenv('POSTGRES_HOST', 'localhost')} "
        f"port={os.getenv('POSTGRES_PORT', '5432')} "
        f"dbname={os.getenv('POSTGRES_DB', 'najm_pos')} "
        f"user={os.getenv('POSTGRES_USER', 'najm')} "
        f"password={os.getenv('POSTGRES_PASSWORD', 'najm_local_pw')}"
    )


# ---- Business constants ------------------------------------------------------
COUNTRIES = ("AE", "SA", "QA")
CURRENCY = {"AE": "AED", "SA": "SAR", "QA": "QAR"}
VAT_RATE = {"AE": 0.05, "SA": 0.15, "QA": 0.0}
TZ_OFFSET_HOURS = {"AE": 4, "SA": 3, "QA": 3}
TIMEZONE = {"AE": "Asia/Dubai", "SA": "Asia/Riyadh", "QA": "Asia/Qatar"}
# AED per 1 unit of currency (USD pegs: 3.6725 AED, 3.75 SAR, 3.64 QAR)
AED_PER_UNIT = {"AED": 1.0, "SAR": 3.6725 / 3.75, "QAR": 3.6725 / 3.64, "USD": 3.6725}

COUNTRY_SHARE_ONLINE = {"AE": 0.50, "SA": 0.40, "QA": 0.10}
COUNTRY_SHARE_MARKETING = {"AE": 0.50, "SA": 0.40, "QA": 0.10}

# Marketing platforms: share of budget, account currency, CPM (AED), CTR, CAC (AED)
MARKETING_CHANNELS = {
    "google_ads": dict(share=0.32, currency="USD", cpm=25.0, ctr=0.035, cac=550.0),
    "meta":       dict(share=0.26, currency="USD", cpm=18.0, ctr=0.012, cac=450.0),
    "tiktok":     dict(share=0.14, currency="AED", cpm=12.0, ctr=0.009, cac=380.0),
    "snapchat":   dict(share=0.12, currency="SAR", cpm=10.0, ctr=0.008, cac=420.0),
    "email":      dict(share=0.04, currency="AED", cpm=2.0,  ctr=0.030, cac=150.0),
    "affiliate":  dict(share=0.12, currency="AED", cpm=15.0, ctr=0.020, cac=300.0),
}
SEASONAL_CAMPAIGN_CHANNELS = ("google_ads", "meta", "tiktok", "snapchat")

LOYALTY_TIERS = ("blue", "silver", "gold", "platinum")

# Rates of injected problems (see docs/source_systems.md)
DUPLICATE_LINE_RATE = 0.005
VOID_RATE = 0.003
LATE_ORDER_RATE = 0.02
CANCEL_RATE = 0.03
MISSING_STOCK_FILE_RATE = 0.01
NEGATIVE_STOCK_RATE = 0.0001
RETURN_NO_RECEIPT_RATE = 0.15
ONLINE_RETURN_RATE = 0.04
TEST_SKU = "TEST-0000"
