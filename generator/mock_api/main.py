"""Mock REST API for the Najm Retail online store (source system #2).

Serves what the generator wrote to `online.db` (SQLite) the way a typical
commerce platform API does: an `updated_since` filter for incremental
extraction, with page-number or keyset-cursor pagination.

    GET /customers?updated_since=2026-09-01T00:00:00Z&page=1&page_size=500
    GET /orders?updated_since=...&cursor=<next_cursor>   (lines embedded as a JSON array)
    GET /order_events?updated_since=...

Run locally:  uvicorn mock_api.main:app --app-dir generator --port 8000
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query

DATA_DIR = Path(os.getenv("ONLINE_DATA_DIR", Path(__file__).resolve().parents[2] / "data" / "landing" / "online"))
DB_PATH = DATA_DIR / "online.db"
MAX_PAGE_SIZE = 1000

app = FastAPI(title="Najm Retail — Online Store API (mock)", version="1.0.0")


def _connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise HTTPException(503, "No data yet: run the generator first (najm-gen backfill)")
    conn = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _normalise(ts: str | None) -> str:
    """Accept any ISO-8601 timestamp; compare in the canonical stored format."""
    if not ts:
        return "0000-01-01T00:00:00.000000Z"
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(422, f"updated_since is not ISO-8601: {ts}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _page(table: str, pk: str, updated_since: str | None, page: int, page_size: int,
          cursor: str | None) -> dict:
    """Two pagination styles, like many real APIs:
    - `page` (offset): simple, but cost grows with depth;
    - `cursor` (keyset on updated_at + primary key): constant cost per page.
    """
    since = _normalise(updated_since)
    # closing(): sqlite3's own context manager only ends the transaction, it does not close the
    # connection; a leaked handle locks the file on Windows and blocks a generator reset.
    with closing(_connect()) as conn:
        if cursor:
            c_ts, _, c_pk = cursor.partition("|")
            pk_val = int(c_pk) if table == "order_events" else c_pk
            rows = conn.execute(
                f"SELECT * FROM {table} WHERE updated_at >= ? AND (updated_at, {pk}) > (?, ?) "
                f"ORDER BY updated_at, {pk} LIMIT ?", (since, c_ts, pk_val, page_size + 1)).fetchall()
        else:
            rows = conn.execute(
                f"SELECT * FROM {table} WHERE updated_at >= ? ORDER BY updated_at, {pk} LIMIT ? OFFSET ?",
                (since, page_size + 1, (page - 1) * page_size)).fetchall()
    has_more = len(rows) > page_size
    data = [dict(r) for r in rows[:page_size]]
    next_cursor = f"{data[-1]['updated_at']}|{data[-1][pk]}" if has_more else None
    return {"data": data, "page": None if cursor else page, "page_size": page_size, "has_more": has_more,
            "next_page": page + 1 if has_more and not cursor else None, "next_cursor": next_cursor}


PageQ = Query(1, ge=1)
SizeQ = Query(500, ge=1, le=MAX_PAGE_SIZE)
CursorQ = Query(None, description="opaque keyset cursor from a previous response's next_cursor")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "database": DB_PATH.exists()}


@app.get("/customers")
def customers(updated_since: str | None = None, page: int = PageQ, page_size: int = SizeQ,
              cursor: str | None = CursorQ) -> dict:
    return _page("customers", "online_customer_id", updated_since, page, page_size, cursor)


@app.get("/orders")
def orders(updated_since: str | None = None, page: int = PageQ, page_size: int = SizeQ,
           cursor: str | None = CursorQ) -> dict:
    body = _page("orders", "order_id", updated_since, page, page_size, cursor)
    for o in body["data"]:
        o["lines"] = json.loads(o["lines"])
    return body


@app.get("/order_events")
def order_events(updated_since: str | None = None, page: int = PageQ, page_size: int = SizeQ,
                 cursor: str | None = CursorQ) -> dict:
    return _page("order_events", "event_id", updated_since, page, page_size, cursor)
