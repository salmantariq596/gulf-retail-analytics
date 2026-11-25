"""POS (PostgreSQL) -> raw_pos.

Mutable tables (headers, master data) are merged on their primary key; immutable
child rows (lines, payments) are appended. Every table is incremental on a
cursor column, so a re-run only reads rows newer than the stored watermark.
"""

from __future__ import annotations

import dlt
from dlt.sources.sql_database import sql_table

from .config import pipeline, postgres_url

# table: (cursor column, primary key, write disposition)
TABLES = {
    "stores":       ("updated_at", "store_id", "merge"),
    "cashiers":     ("updated_at", "cashier_id", "merge"),
    "customers":    ("updated_at", "customer_id", "merge"),
    "promotions":   ("updated_at", "promotion_id", "merge"),
    "sales":        ("updated_at", "sale_id", "merge"),
    "returns":      ("updated_at", "return_id", "merge"),
    "sale_lines":   ("created_at", "sale_line_id", "append"),
    "payments":     ("paid_at", "payment_id", "append"),
    "return_lines": ("created_at", "return_line_id", "append"),
}


@dlt.source(name="pos")
def pos_source(credentials: str | None = None):
    creds = credentials or postgres_url()
    for table, (cursor, pk, disposition) in TABLES.items():
        res = sql_table(
            credentials=creds, schema="pos", table=table,
            # rows equal to the last cursor value are re-read and dropped by primary key
            # (without it dlt hashes whole rows, which changes when the reflected schema does)
            incremental=dlt.sources.incremental(cursor, primary_key=pk),
            backend="pyarrow", chunk_size=50_000,
            # reflect the table when extracting, not when the source is built: Dagster
            # builds sources at load time and must not need Postgres to start
            defer_table_reflect=True,
        )
        res.apply_hints(primary_key=pk, write_disposition=disposition)
        yield res


def run():
    return pipeline("najm_pos", "raw_pos").run(pos_source())
