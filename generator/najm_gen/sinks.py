"""Where generated data lands: PostgreSQL (POS), SQLite behind the mock API
(online store) and CSV files (ERP, catalog, marketing)."""

from __future__ import annotations

import io
import sqlite3
from pathlib import Path

import pandas as pd
import psycopg

from . import config as C

POS_TABLES = ["return_lines", "returns", "payments", "sale_lines", "sales",
              "promotions", "customers", "cashiers", "stores"]


class PostgresSink:
    def __init__(self, dsn: str | None = None):
        dsn = dsn or C.postgres_dsn()
        self._ensure_database(dsn)
        self.conn = psycopg.connect(dsn)
        self._ensure_schema()
        self._ensure_progress_table()

    @staticmethod
    def _ensure_database(dsn: str) -> None:
        """Create the target database if missing (e.g. najm_pos_full next to the dev najm_pos)."""
        params = dict(p.split("=", 1) for p in dsn.split())
        dbname = params.get("dbname", "postgres")
        admin = " ".join(f"{k}={v}" for k, v in {**params, "dbname": "postgres"}.items())
        with psycopg.connect(admin, autocommit=True) as conn:
            if not conn.execute("select 1 from pg_database where datname = %s", (dbname,)).fetchone():
                conn.execute(f'create database "{dbname}"')

    def _ensure_schema(self) -> None:
        """Docker only runs the init script for the default database; apply it to others."""
        if not self.conn.execute("select 1 from information_schema.schemata where schema_name = 'pos'").fetchone():
            self.conn.execute(C.POS_SCHEMA_SQL.read_text(encoding="utf-8"))
            self.conn.commit()

    def _ensure_progress_table(self) -> None:
        """Generator bookkeeping, outside the pos schema so ingestion never sees it."""
        self.conn.execute("create schema if not exists gen_meta")
        self.conn.execute(
            "create table if not exists gen_meta.progress ("
            " id int primary key default 1 check (id = 1), next_day date not null)"
        )
        self.conn.commit()

    def set_progress(self, next_day) -> None:
        """Record the next day to simulate. Not committed here: it commits together with
        the day's data, so the marker and the data can never disagree."""
        self.conn.execute(
            "insert into gen_meta.progress (id, next_day) values (1, %s) "
            "on conflict (id) do update set next_day = excluded.next_day", (next_day,))

    def get_progress(self):
        row = self.conn.execute("select next_day from gen_meta.progress where id = 1").fetchone()
        return row[0] if row else None

    def reset(self) -> None:
        with self.conn.cursor() as cur:
            cur.execute("TRUNCATE " + ", ".join(f"pos.{t}" for t in POS_TABLES) + " RESTART IDENTITY CASCADE")
            cur.execute("delete from gen_meta.progress")
        self.conn.commit()

    def copy(self, table: str, df: pd.DataFrame, columns: list[str]) -> None:
        if df is None or df.empty:
            return
        buf = io.StringIO()
        df[columns].to_csv(buf, index=False, header=False)
        with self.conn.cursor() as cur:
            with cur.copy(f"COPY pos.{table} ({', '.join(columns)}) FROM STDIN WITH (FORMAT csv)") as cp:
                cp.write(buf.getvalue())

    def executemany(self, sql: str, params: list[tuple]) -> None:
        if params:
            with self.conn.cursor() as cur:
                cur.executemany(sql, params)

    def commit(self) -> None:
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()


ONLINE_DDL = """
CREATE TABLE IF NOT EXISTS customers (
    online_customer_id TEXT PRIMARY KEY, email TEXT, first_name TEXT, last_name TEXT,
    loyalty_number TEXT, country_code TEXT, acquisition_channel TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY, customer_id TEXT, channel TEXT, ship_country TEXT, currency TEXT,
    payment_method TEXT, promotion_code TEXT, placed_at TEXT NOT NULL, status TEXT NOT NULL,
    updated_at TEXT NOT NULL, lines TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS order_events (
    event_id INTEGER PRIMARY KEY, order_id TEXT NOT NULL, status TEXT NOT NULL,
    event_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_customers_updated ON customers (updated_at, online_customer_id);
CREATE INDEX IF NOT EXISTS ix_orders_updated ON orders (updated_at, order_id);
CREATE INDEX IF NOT EXISTS ix_events_updated ON order_events (updated_at, event_id);
"""


class OnlineSink:
    """SQLite file read by the FastAPI mock (generator/mock_api)."""

    def __init__(self, path: Path = C.ONLINE_DB_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.executescript(ONLINE_DDL)

    def insert(self, table: str, df: pd.DataFrame) -> None:
        if df is None or df.empty:
            return
        cols = list(df.columns)
        sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})"
        self.conn.executemany(sql, df.astype(object).where(df.notna(), None).itertuples(index=False, name=None))

    def update_orders(self, rows: list[tuple[str, str, str]]) -> None:
        """rows: (status, updated_at, order_id). Status never moves backwards in the
        lifecycle: a cash-on-delivery 'paid' event after 'delivered' only bumps updated_at."""
        rank = ("CASE {c} WHEN 'placed' THEN 1 WHEN 'paid' THEN 2 WHEN 'shipped' THEN 3 "
                "WHEN 'delivered' THEN 4 WHEN 'cancelled' THEN 5 END")
        self.conn.executemany(
            f"UPDATE orders SET status = CASE WHEN {rank.format(c='?1')} > {rank.format(c='status')} "
            "THEN ?1 ELSE status END, updated_at = ?2 WHERE order_id = ?3", rows)

    def commit(self) -> None:
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()


def write_csv(df: pd.DataFrame, path: Path, gzip: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, compression="gzip" if gzip else None)
