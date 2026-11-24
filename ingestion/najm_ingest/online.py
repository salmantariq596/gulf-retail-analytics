"""Online store REST API -> raw_online.

Each endpoint is read incrementally with `updated_since` = the highest
`updated_at` already loaded, page by page. Orders are merged on order_id, so a
status change replaces the order row (and its nested lines in orders__lines);
events are append-only.
"""

from __future__ import annotations

from collections.abc import Iterator

import dlt
import requests

from .config import API_BASE_URL, pipeline

EPOCH = "1970-01-01T00:00:00.000000Z"
PAGE_SIZE = 1000


def TS() -> dict:  # noqa: N802 - a fresh dict per hint: dlt mutates column hints in place
    return {"data_type": "timestamp"}


def _paginate(path: str, updated_since: str) -> Iterator[list[dict]]:
    """Keyset pagination: follow next_cursor until has_more is false."""
    params = {"updated_since": updated_since, "page_size": PAGE_SIZE}
    with requests.Session() as s:
        while True:
            r = s.get(f"{API_BASE_URL}{path}", params=params, timeout=60)
            r.raise_for_status()
            body = r.json()
            if body["data"]:
                yield body["data"]
            if not body["has_more"]:
                return
            params["cursor"] = body["next_cursor"]


# `updated_at` stays an ISO string during extraction so the incremental cursor compares
# like-for-like with the API; dlt's timestamp autodetection types it in the destination.
@dlt.resource(name="customers", primary_key="online_customer_id", write_disposition="merge",
              columns={"created_at": TS()})
def customers(updated_at=dlt.sources.incremental("updated_at", initial_value=EPOCH)):
    yield from _paginate("/customers", updated_at.last_value)


@dlt.resource(name="orders", primary_key="order_id", write_disposition="merge",
              columns={"placed_at": TS()})
def orders(updated_at=dlt.sources.incremental("updated_at", initial_value=EPOCH)):
    yield from _paginate("/orders", updated_at.last_value)


@dlt.resource(name="order_events", primary_key="event_id", write_disposition="merge",
              columns={"event_at": TS()})
def order_events(updated_at=dlt.sources.incremental("updated_at", initial_value=EPOCH)):
    yield from _paginate("/order_events", updated_at.last_value)


@dlt.source(name="online")
def online_source():
    return customers, orders, order_events


def run():
    return pipeline("najm_online", "raw_online").run(online_source())
