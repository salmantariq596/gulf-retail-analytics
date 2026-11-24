"""Daily file drops (ERP inventory, catalog exports, marketing) -> raw_erp, raw_catalog, raw_marketing.

Files are loaded as-is (every column as text, plus `_file_name` and
`_file_date`): typing and deduplication are staging's job, not ingestion's.
The highest `_file_date` loaded is kept in dlt state, so only new files are
read on the next run. Restated marketing files are appended too, and staging
keeps the latest version of each row.
"""

from __future__ import annotations

import re
from pathlib import Path

import dlt
import pandas as pd
import pyarrow as pa

from .config import LANDING_DIR, pipeline

DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def file_resource(name: str, folder: Path, pattern: str):
    @dlt.resource(name=name, write_disposition="append")
    # primary_key=() turns off dlt's boundary dedup: whole files are skipped by date instead.
    def _files(file_date=dlt.sources.incremental("_file_date", initial_value="1900-01-01", primary_key=())):
        last = file_date.last_value
        for path in sorted(folder.glob(pattern), key=lambda p: (DATE_RE.search(p.name).group(1), str(p))):
            fd = DATE_RE.search(path.name).group(1)
            if fd <= last:
                continue
            df = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])
            df["_file_name"] = path.relative_to(LANDING_DIR).as_posix()
            df["_file_date"] = fd
            yield pa.Table.from_pandas(df, preserve_index=False)

    return _files


@dlt.source(name="erp")
def erp_source():
    base = LANDING_DIR / "erp"
    return (file_resource("stock_on_hand", base / "stock_on_hand", "stock_on_hand_*.csv.gz"),
            file_resource("purchase_orders", base / "purchase_orders", "purchase_orders_*.csv"))


@dlt.source(name="catalog")
def catalog_source():
    return file_resource("products", LANDING_DIR / "catalog", "products_*.csv.gz")


@dlt.source(name="marketing")
def marketing_source():
    return file_resource("spend", LANDING_DIR / "marketing", "*/spend_*.csv")


def run_erp():
    return pipeline("najm_erp", "raw_erp").run(erp_source())


def run_catalog():
    return pipeline("najm_catalog", "raw_catalog").run(catalog_source())


def run_marketing():
    return pipeline("najm_marketing", "raw_marketing").run(marketing_source())
