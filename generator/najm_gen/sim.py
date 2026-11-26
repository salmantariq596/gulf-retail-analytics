"""Day-by-day simulation of Najm Retail.

`init_state` builds reference data as of the start date; `simulate_day` advances
one business day and writes every source system. Running `simulate_day` in a
loop *is* the backfill, so history (price changes, tier changes, store
open/close) is produced exactly as a daily production feed would produce it.

Visibility rule: everything emitted for day d has an `updated_at` / `created_at`
below `horizon(d)` (midnight UAE time) and at or above `horizon(d-1)`, so
incremental extraction by watermark never misses a row.
"""

from __future__ import annotations

import json
import os
import pickle
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd

from . import config as C
from . import reference as R
from .gulf_calendar import is_ramadan, sales_multiplier
from .sinks import OnlineSink, PostgresSink, write_csv

UTC = timezone.utc
HOURS = np.arange(10, 24)
_HW = np.array([3, 4, 5, 5, 5, 6, 7, 8, 9, 10, 10, 9, 7, 4], float)
_HW_RAMADAN = np.array([1, 1, 1, 1, 1, 2, 2, 3, 6, 11, 14, 15, 14, 12], float)
HOUR_W, HOUR_W_RAMADAN = _HW / _HW.sum(), _HW_RAMADAN / _HW_RAMADAN.sum()
_OHW = np.array([2, 1, 1, 1, 1, 1, 2, 3, 4, 5, 6, 6, 6, 6, 6, 6, 6, 7, 8, 9, 10, 10, 8, 4], float)
ONLINE_HOUR_W = _OHW / _OHW.sum()

PAYMENT_METHODS = {
    "AE": (["card", "cash", "apple_pay", "tabby", "gift_card"], [0.55, 0.12, 0.18, 0.10, 0.05]),
    "SA": (["card", "cash", "apple_pay", "tabby", "tamara", "gift_card"], [0.45, 0.15, 0.15, 0.10, 0.12, 0.03]),
    "QA": (["card", "cash", "apple_pay", "gift_card"], [0.60, 0.20, 0.17, 0.03]),
}
STATUS_RANK = {"placed": 1, "paid": 2, "shipped": 3, "delivered": 4, "cancelled": 5}
RETURN_REASONS = (["defective", "changed_mind", "wrong_item", "other"], [0.35, 0.40, 0.15, 0.10])
SALE_COLS = ["sale_id", "receipt_number", "store_id", "register_no", "cashier_id", "customer_id", "sold_at",
             "currency_code", "total_incl_vat", "status", "created_at", "updated_at"]
LINE_COLS = ["sale_line_id", "sale_id", "line_number", "sku", "quantity", "unit_price_incl_vat",
             "discount_incl_vat", "promotion_id", "line_total_incl_vat", "created_at"]
PAY_COLS = ["payment_id", "sale_id", "payment_method", "amount", "currency_code", "paid_at"]
RET_COLS = ["return_id", "store_id", "cashier_id", "customer_id", "original_sale_id", "original_online_order_id",
            "returned_at", "currency_code", "reason_code", "created_at", "updated_at"]
RET_LINE_COLS = ["return_line_id", "return_id", "original_sale_line_id", "sku", "quantity", "refund_incl_vat",
                 "created_at"]
STORE_COLS = ["store_id", "store_code", "store_name_en", "store_name_ar", "country_code", "city", "store_format",
              "currency_code", "timezone", "opened_on", "closed_on", "updated_at"]
CASHIER_COLS = ["cashier_id", "cashier_code", "store_id", "full_name", "hired_on", "is_active", "updated_at"]
CUSTOMER_COLS = ["customer_id", "loyalty_number", "first_name", "last_name", "first_name_ar", "last_name_ar",
                 "email", "phone", "country_code", "home_store_id", "loyalty_tier", "acquisition_channel",
                 "created_at", "updated_at"]
PROMO_COLS = ["promotion_id", "promotion_code", "promotion_name", "discount_type", "discount_value",
              "starts_on", "ends_on", "updated_at"]
ONLINE_CUSTOMER_COLS = ["online_customer_id", "email", "first_name", "last_name", "loyalty_number",
                        "country_code", "acquisition_channel", "created_at", "updated_at"]


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------
def _midnight_utc(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=UTC)


def day_start_utc(d: date, cc: str) -> pd.Timestamp:
    return pd.Timestamp(_midnight_utc(d) - timedelta(hours=C.TZ_OFFSET_HOURS[cc]))


def horizon(d: date) -> pd.Timestamp:
    """End of business day d in the earliest timezone (UAE, UTC+4)."""
    return pd.Timestamp(_midnight_utc(d + timedelta(days=1)) - timedelta(hours=4))


def business_times(rng, d: date, cc: str, n: int) -> pd.DatetimeIndex:
    """Store trading hours 10:00-23:59 local, Ramadan shifts to the evening."""
    w = HOUR_W_RAMADAN if is_ramadan(d) else HOUR_W
    secs = rng.choice(HOURS, n, p=w) * 3600 + rng.integers(0, 3600, n)
    return day_start_utc(d, cc) + pd.to_timedelta(np.sort(secs), unit="s")


def iso(ts) -> pd.Series:
    return pd.Series(pd.to_datetime(ts, utc=True)).dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _ts_on(d: date, hour: int = 6) -> pd.Timestamp:
    return pd.Timestamp(_midnight_utc(d) + timedelta(hours=hour))


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
@dataclass
class State:
    profile: C.Profile
    start: date
    end: date
    seed: int
    current: date
    rng: np.random.Generator
    names: R.NamePool
    stores: pd.DataFrame
    cashiers: pd.DataFrame
    products: pd.DataFrame
    customers: pd.DataFrame
    promotions: pd.DataFrame
    campaigns: pd.DataFrame
    inventory: pd.DataFrame
    pending_returns: pd.DataFrame
    pending_orders: dict
    pending_events: pd.DataFrame
    marketing_recent: pd.DataFrame
    counters: dict

    def save(self, path=C.STATE_PATH) -> None:
        """Crash-safe checkpoint. The bytes are fsynced before the rename (a power cut once left
        a renamed file full of zeros), and the previous checkpoint is kept as <name>.prev."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with open(tmp, "wb") as f:
            pickle.dump(self, f, protocol=pickle.HIGHEST_PROTOCOL)
            f.flush()
            os.fsync(f.fileno())
        if path.exists():
            path.replace(path.with_suffix(".prev"))
        tmp.replace(path)

    @staticmethod
    def load(path=C.STATE_PATH, expect_next_day: date | None = None) -> "State":
        """Load the checkpoint whose next day matches the database (see simulate_day):
        the latest one, or the previous one if the crash came before the day's commit."""
        problems = []
        for candidate in (path, path.with_suffix(".prev")):
            if not candidate.exists():
                continue
            try:
                with open(candidate, "rb") as f:
                    st = pickle.load(f)
            except (pickle.UnpicklingError, EOFError, ValueError, AttributeError) as exc:
                problems.append(f"{candidate.name}: unreadable ({exc.__class__.__name__})")
                continue
            if expect_next_day is None or st.current == expect_next_day:
                if candidate != path:
                    print(f"Using the previous checkpoint {candidate.name}; latest: {problems or 'ahead of the database'}")
                return st
            problems.append(f"{candidate.name}: next day {st.current}")
        raise RuntimeError(
            f"No checkpoint matches the database (next day there: {expect_next_day}); "
            f"{'; '.join(problems) or 'no checkpoint found'}. Start again with `najm-gen backfill`.")

    def next_id(self, key: str, n: int = 1) -> np.ndarray:
        first = self.counters[key]
        self.counters[key] = first + n
        return np.arange(first, first + n)


def _is_open(s, d: date) -> bool:
    closed = s.closed_on if s.closed_on is not None and not pd.isna(s.closed_on) else None
    return s.opened_on <= d and (closed is None or d < closed)


def init_state(profile: C.Profile, start: date, end: date, seed: int) -> State:
    rng = np.random.default_rng(seed)
    names = R.NamePool(seed)
    stores = R.build_stores(rng, end)
    cashiers = R.build_cashiers(rng, stores, names)
    products = R.build_products(rng, profile.n_products, start, end)
    customers, next_pos, next_idx = R.initial_customers(rng, names, stores, profile.n_customers_initial, start)
    st = State(
        profile=profile, start=start, end=end, seed=seed, current=start, rng=rng, names=names,
        stores=stores, cashiers=cashiers, products=products, customers=customers,
        promotions=R.build_promotions(rng, start, end), campaigns=R.build_campaigns(start, end),
        inventory=pd.DataFrame(), pending_returns=pd.DataFrame(), pending_orders={},
        pending_events=pd.DataFrame(columns=["order_id", "status", "event_at", "release_date"]),
        marketing_recent=pd.DataFrame(),
        counters=dict(sale_id=1, sale_line_id=1, payment_id=1, return_id=1, return_line_id=1,
                      pos_customer_id=next_pos, cust_idx=next_idx, order_seq=1, event_id=1,
                      cashier_id=int(cashiers.cashier_id.max()) + 1),
    )
    for s in stores.itertuples():
        if not s.is_online and _is_open(s, start):
            _add_store_inventory(st, s)
    return st


def _add_store_inventory(st: State, s) -> None:
    rng, p = st.rng, st.products
    n_ass = max(50, int(R.FORMAT_ASSORTMENT[s.store_format] * st.profile.n_products / 15_000))
    cand = p.index[p.sku != C.TEST_SKU].to_numpy()
    w = p.popularity.to_numpy()[cand]
    pidx = rng.choice(cand, size=min(n_ass, len(cand)), replace=False, p=w / w.sum())
    share = s.weight / st.stores.loc[~st.stores.is_online, "weight"].sum()
    pop = p.popularity.to_numpy()[pidx]
    expected = st.profile.pos_lines_per_day * share * pop / pop.sum() * 1.3
    target = np.ceil(expected * 21).astype(int) + 2
    inv = pd.DataFrame({
        "store_id": s.store_id, "product_idx": pidx,
        "on_hand": np.round(target * rng.uniform(0.5, 1.0, len(pidx))).astype(int),
        "po_qty": 0, "po_number": None, "ordered_on": None, "expected_on": None, "due_on": None,
        "target": target, "reorder": np.ceil(expected * 7).astype(int) + 1,
    })
    st.inventory = pd.concat([st.inventory, inv], ignore_index=True)


# ---------------------------------------------------------------------------
# Initial load (reference data that exists before day 1)
# ---------------------------------------------------------------------------
def initial_load(st: State, pg: PostgresSink, online: OnlineSink) -> None:
    pg.reset()
    ts = _ts_on(st.start - timedelta(days=1))
    _insert_due_stores(st, st.start - timedelta(days=1), pg, ts)
    cust = st.customers
    _write_customers(cust, pg, online)
    promos = st.promotions.assign(updated_at=ts)
    pg.copy("promotions", promos, PROMO_COLS)
    pg.commit()
    online.commit()


def _insert_due_stores(st: State, d: date, pg: PostgresSink, ts) -> None:
    """POS learns about a store 30 days before it opens."""
    due = st.stores[(~st.stores.inserted) & (st.stores.opened_on.map(lambda o: o - timedelta(days=30) <= d))]
    if due.empty:
        return
    pg.copy("stores", due.assign(updated_at=ts), STORE_COLS)
    cash = st.cashiers[st.cashiers.store_id.isin(due.store_id)]
    pg.copy("cashiers", cash.assign(is_active=True, updated_at=ts), CASHIER_COLS)
    st.stores.loc[due.index, "inserted"] = True


def _write_customers(cust: pd.DataFrame, pg: PostgresSink, online: OnlineSink) -> None:
    if cust.empty:
        return
    pos = cust[cust.pos_customer_id.notna()].assign(
        customer_id=lambda x: x.pos_customer_id.astype("int64"), updated_at=lambda x: x.created_at)
    pg.copy("customers", pos, CUSTOMER_COLS)
    onl = cust[cust.online_customer_id.notna()].assign(
        created_at=lambda x: iso(x.created_at).values, updated_at=lambda x: iso(x.created_at).values)
    online.insert("customers", onl[ONLINE_CUSTOMER_COLS])


# ---------------------------------------------------------------------------
# One simulated day
# ---------------------------------------------------------------------------
def simulate_day(st: State, d: date, pg: PostgresSink, online: OnlineSink, checkpoint: bool = False) -> dict:
    rng = st.rng
    stats: dict = {"date": d.isoformat()}
    _store_lifecycle(st, d, pg)
    _catalog_changes(st, d)
    acquisitions = _marketing(st, d)
    stats["new_customers"] = _new_customers(st, d, acquisitions, pg, online)
    _tier_changes(st, d, pg)

    ctx = _day_context(st, d)
    sold = _pos_sales(st, d, ctx, pg, stats)
    _online_orders(st, d, ctx, stats)
    _emit_online(st, d, online, stats)
    restock = _release_returns(st, d, pg, stats)
    _inventory(st, d, sold, restock, stats)
    _catalog_export(st, d)

    # Crash safety: save the checkpoint (next day = d + 1) BEFORE committing, and commit the
    # progress marker in the same transaction as the POS data. A crash before the commit leaves
    # the database at d, which State.load matches with the previous checkpoint; after it, with
    # the latest. (The online store's SQLite commits a moment earlier, outside that transaction.)
    st.current = d + timedelta(days=1)
    pg.set_progress(st.current)
    if checkpoint:
        st.save()
    online.commit()
    pg.commit()
    return stats


def _store_lifecycle(st: State, d: date, pg: PostgresSink) -> None:
    ts = _ts_on(d)
    _insert_due_stores(st, d, pg, ts)
    for s in st.stores.itertuples():
        if s.is_online:
            continue
        if s.opened_on == d and d != st.start:
            _add_store_inventory(st, s)
        if s.planned_close_on is not None and s.planned_close_on == d:
            st.stores.loc[s.Index, "closed_on"] = d
            pg.executemany("UPDATE pos.stores SET closed_on = %s, updated_at = %s WHERE store_id = %s",
                           [(d, ts.to_pydatetime(), int(s.store_id))])
            pg.executemany("UPDATE pos.cashiers SET is_active = false, updated_at = %s WHERE store_id = %s",
                           [(ts.to_pydatetime(), int(s.store_id))])
            st.inventory = st.inventory[st.inventory.store_id != s.store_id].reset_index(drop=True)


def _catalog_changes(st: State, d: date) -> None:
    """Price/cost changes, re-categorisation and discontinuation, effective from d."""
    rng, p = st.rng, st.products
    real = (p.sku != C.TEST_SKU).to_numpy() & (p.launched_on <= d).to_numpy()
    n = len(p)
    # Price changes are set against the product's reference price (markdowns and
    # restores), not compounded on the current price, and never go below cost + 5%.
    if "base_price_aed" not in p.columns:
        p["base_price_aed"] = p["list_price_aed"]
    price_chg = real & (rng.random(n) < 3 / 365)
    if price_chg.any():
        f = rng.choice([0.80, 0.85, 0.90, 0.95, 1.00, 1.05], price_chg.sum(), p=[0.1, 0.15, 0.2, 0.2, 0.25, 0.1])
        newp = np.round(p.loc[price_chg, "base_price_aed"].to_numpy() * f / 10) * 10 - 1
        floor = np.ceil(p.loc[price_chg, "unit_cost_aed"].to_numpy() * 1.05)
        p.loc[price_chg, "list_price_aed"] = np.maximum.reduce([np.full(newp.size, 9.0), newp, floor])
    cost_chg = real & (rng.random(n) < 1.5 / 365)
    if cost_chg.any():
        # supplier cost moves within +/-8% of where it started, capped at 90% of the reference price
        if "base_cost_aed" not in p.columns:
            p["base_cost_aed"] = p["unit_cost_aed"]
        p.loc[cost_chg, "unit_cost_aed"] = np.round(np.minimum.reduce([
            p.loc[cost_chg, "base_cost_aed"].to_numpy() * rng.uniform(0.92, 1.08, cost_chg.sum()),
            p.loc[cost_chg, "base_price_aed"].to_numpy() * 0.90,
            p.loc[cost_chg, "list_price_aed"].to_numpy() / 1.05,
        ]), 2)
    recat = real & (rng.random(n) < 0.03 / 1096)
    cats = [c[0] for c in R.CATALOG]
    for i in np.flatnonzero(recat):
        p.iat[i, p.columns.get_loc("category")] = rng.choice([c for c in cats if c != p.category.iat[i]])
    disc = real & p.is_active.to_numpy() & (rng.random(n) < 0.02 / 1096)
    p.loc[disc, "is_active"] = False


def _day_context(st: State, d: date) -> dict:
    """Per-day lookups: shelf prices, sampling weights, customer pools, promotions."""
    p = st.products
    launched = (p.launched_on <= d).to_numpy()
    active_factor = np.where(p.is_active.to_numpy(), 1.0, 0.1)
    demand_w = p.popularity.to_numpy() * launched * active_factor
    shelf = {}
    for cc in C.COUNTRIES:
        cur = C.CURRENCY[cc]
        shelf[cc] = np.maximum(1.0, np.round(p.list_price_aed.to_numpy() * (1 + C.VAT_RATE[cc]) / C.AED_PER_UNIT[cur]))
    cust = st.customers
    pools = {}
    for cc in C.COUNTRIES:
        before = (cust.created_at < day_start_utc(d, cc)).to_numpy() & (cust.country_code == cc).to_numpy()
        for kind, col in (("pos", "pos_customer_id"), ("online", "online_customer_id")):
            m = before & cust[col].notna().to_numpy()
            w = cust.activity.to_numpy()[m]
            pools[(cc, kind)] = (np.flatnonzero(m), w / w.sum() if w.size else w)
    promos = {}
    pr = st.promotions
    for cc in C.COUNTRIES:
        act = pr[(pr.starts_on <= d) & (pr.ends_on >= d) & (pr.country_code.isna() | (pr.country_code == cc))]
        promos[cc] = act[~act.promotion_code.isin(["LOYALTY5", "GIFT50"])]
    return dict(launched=launched, demand_w=demand_w, shelf=shelf, pools=pools, promos=promos,
                promo_by_code=pr.set_index("promotion_code"))


def _apply_promotions(rng, ctx, cc: str, gross: np.ndarray, identified: np.ndarray):
    """Returns (promotion_id as Int64 array, discount_incl_vat)."""
    n = gross.size
    promo_id = np.full(n, -1)
    disc = np.zeros(n)
    seasonal = ctx["promos"][cc]
    if len(seasonal):
        p_promo = 0.6 if seasonal.promotion_name.str.contains("White").any() else 0.35
        use = rng.random(n) < p_promo
        pick = seasonal.iloc[rng.integers(0, len(seasonal), n)]
        promo_id = np.where(use, pick.promotion_id.to_numpy(), promo_id)
        disc = np.where(use, np.round(gross * pick.discount_value.to_numpy() / 100, 2), disc)
    pb = ctx["promo_by_code"]
    free = promo_id == -1
    loyal = free & identified & (rng.random(n) < 0.05)
    promo_id[loyal] = pb.loc["LOYALTY5", "promotion_id"]
    disc[loyal] = np.round(gross[loyal] * 0.05, 2)
    gift = free & ~loyal & (rng.random(n) < 0.01) & (gross > 120)
    promo_id[gift] = pb.loc["GIFT50", "promotion_id"]
    disc[gift] = 50.0
    manual = (promo_id == -1) & (rng.random(n) < 0.02)
    disc[manual] = np.round(gross[manual] * rng.uniform(0.05, 0.10, manual.sum()), 2)
    return pd.array(np.where(promo_id == -1, None, promo_id), dtype="Int64"), disc


# ---------------------------------------------------------------------------
# POS
# ---------------------------------------------------------------------------
def _pos_sales(st: State, d: date, ctx: dict, pg: PostgresSink, stats: dict) -> pd.DataFrame:
    rng, prof = st.rng, st.profile
    p = st.products
    skus = p.sku.to_numpy()
    qty_max = p.qty_max.to_numpy()
    test_idx = int(p.index[p.sku == C.TEST_SKU][0])
    total_w = st.stores.loc[~st.stores.is_online, "weight"].sum()
    growth = 1 + 0.08 * (d - st.start).days / 365
    inv_groups = {k: g.product_idx.to_numpy() for k, g in st.inventory.groupby("store_id")}
    sales_frames, line_frames = [], []

    for s in st.stores.itertuples():
        if s.is_online or not _is_open(s, d) or s.store_id not in inv_groups:
            continue
        cc = s.country_code
        cash = st.cashiers[(st.cashiers.store_id == s.store_id)]
        regular = cash[~cash.is_training].cashier_id.to_numpy()
        training = cash[cash.is_training].cashier_id.to_numpy()
        assort = inv_groups[s.store_id]
        w = ctx["demand_w"][assort]
        if w.sum() == 0:
            continue
        w = w / w.sum()
        exp_lines = prof.pos_lines_per_day * s.weight / total_w * sales_multiplier(cc, d) * growth \
            * rng.lognormal(0, 0.08)

        n_sales = int(rng.poisson(exp_lines / 1.7))
        n_test = int(rng.poisson(0.6))
        n_all = n_sales + n_test
        if n_all == 0:
            continue
        lps = np.concatenate([1 + rng.poisson(0.7, n_sales), np.ones(n_test, int)])
        is_test_sale = np.r_[np.zeros(n_sales, bool), np.ones(n_test, bool)]
        sale_ix = np.repeat(np.arange(n_all), lps)
        L = sale_ix.size
        line_no = np.arange(L) - np.repeat(np.cumsum(lps) - lps, lps) + 1
        pidx = rng.choice(assort, L, p=w)
        test_line = is_test_sale[sale_ix]
        pidx = np.where(test_line & (rng.random(L) < 0.5), test_idx, pidx)
        # occasionally a real cashier rings up the test SKU too
        real_ix = np.flatnonzero(~test_line)
        if real_ix.size and rng.random() < 0.05:
            pidx[real_ix[rng.integers(0, real_ix.size)]] = test_idx
        qty = np.where(test_line, 1, 1 + rng.binomial(np.maximum(qty_max[pidx] - 1, 0), 0.25))
        unit = ctx["shelf"][cc][pidx]
        gross = unit * qty

        sold_at = business_times(rng, d, cc, n_all)
        sold_at = sold_at[rng.permutation(n_all)] if n_test else sold_at
        pool_ix, pool_w = ctx["pools"][(cc, "pos")]
        identified = (rng.random(n_all) < 0.45) & ~is_test_sale & (pool_ix.size > 0)
        cust_rows = np.full(n_all, -1)
        if identified.any():
            cust_rows[identified] = rng.choice(pool_ix, identified.sum(), p=pool_w)
        cust_id = np.where(cust_rows >= 0,
                           st.customers.pos_customer_id.to_numpy()[np.maximum(cust_rows, 0)], None)
        promo_id, disc = _apply_promotions(rng, ctx, cc, gross, identified[sale_ix])
        disc = np.where(test_line, 0.0, disc)
        line_total = np.round(gross - disc, 2)

        sale_ids = st.next_id("sale_id", n_all)
        cashier = np.where(is_test_sale, rng.choice(training, n_all), rng.choice(regular, n_all))
        status = np.where((rng.random(n_all) < C.VOID_RATE) & ~is_test_sale, "voided", "completed")
        sales_frames.append(pd.DataFrame({
            "sale_id": sale_ids,
            "receipt_number": [f"{s.store_code}-{d:%y%m%d}-{k:05d}" for k in range(1, n_all + 1)],
            "store_id": s.store_id, "register_no": rng.integers(1, s.registers + 1, n_all),
            "cashier_id": cashier, "customer_id": pd.array(cust_id, dtype="Int64"), "sold_at": sold_at,
            "currency_code": s.currency_code,
            "total_incl_vat": np.round(np.bincount(sale_ix, weights=line_total, minlength=n_all), 2),
            "status": status, "created_at": sold_at, "updated_at": sold_at,
            "country_code": cc, "is_test": is_test_sale,
        }))
        line_frames.append(pd.DataFrame({
            "sale_id": sale_ids[sale_ix], "line_number": line_no, "sku": skus[pidx], "product_idx": pidx,
            "quantity": qty, "unit_price_incl_vat": unit, "discount_incl_vat": disc, "promotion_id": promo_id,
            "line_total_incl_vat": line_total, "created_at": sold_at[sale_ix], "store_id": s.store_id,
            "customer_id": pd.array(cust_id[sale_ix], dtype="Int64"),
            "is_real": ~test_line & (status[sale_ix] == "completed") & (pidx != test_idx),
        }))

    if not sales_frames:
        return pd.DataFrame(columns=["store_id", "product_idx", "quantity"])
    sales = pd.concat(sales_frames, ignore_index=True)
    lines = pd.concat(line_frames, ignore_index=True)
    lines["sale_line_id"] = st.next_id("sale_line_id", len(lines))

    # Till restarts re-send a line: same (sale_id, line_number), new id, slightly later
    dup = lines[rng.random(len(lines)) < C.DUPLICATE_LINE_RATE].copy()
    dup["sale_line_id"] = st.next_id("sale_line_id", len(dup))
    dup["created_at"] = dup["created_at"] + pd.to_timedelta(rng.integers(5, 180, len(dup)), unit="s")
    all_lines = pd.concat([lines, dup], ignore_index=True).sort_values("sale_line_id")

    pays = _payments(st, sales)
    pg.copy("sales", sales, SALE_COLS)
    pg.copy("sale_lines", all_lines, LINE_COLS)
    pg.copy("payments", pays, PAY_COLS)
    _schedule_pos_returns(st, d, lines[lines.is_real], sales)
    stats.update(pos_sales=len(sales), pos_lines=len(all_lines), pos_duplicates=len(dup))
    real = lines[lines.is_real]
    return real.groupby(["store_id", "product_idx"], as_index=False).quantity.sum()


def _payments(st: State, sales: pd.DataFrame) -> pd.DataFrame:
    rng = st.rng
    frames = []
    for cc, g in sales.groupby("country_code"):
        methods, probs = PAYMENT_METHODS[cc]
        m = rng.choice(methods, len(g), p=probs)
        split = rng.random(len(g)) < 0.08
        tot = g.total_incl_vat.to_numpy()
        first = np.where(split, np.round(tot * rng.uniform(0.3, 0.7, len(g)), 2), tot)
        frames.append(pd.DataFrame({"sale_id": g.sale_id.to_numpy(), "payment_method": np.where(split, "card", m),
                                    "amount": first, "currency_code": g.currency_code.to_numpy(),
                                    "paid_at": g.sold_at.to_numpy()}))
        frames.append(pd.DataFrame({"sale_id": g.sale_id.to_numpy()[split], "payment_method": "cash",
                                    "amount": np.round(tot[split] - first[split], 2),
                                    "currency_code": g.currency_code.to_numpy()[split],
                                    "paid_at": g.sold_at.to_numpy()[split]}))
    pays = pd.concat(frames, ignore_index=True)
    pays["payment_id"] = st.next_id("payment_id", len(pays))
    pays["paid_at"] = pd.to_datetime(pays.paid_at, utc=True)
    return pays


def _schedule_pos_returns(st: State, d: date, lines: pd.DataFrame, sales: pd.DataFrame) -> None:
    rng = st.rng
    rr = st.products.return_rate.to_numpy()[lines.product_idx.to_numpy()]
    r = lines[rng.random(len(lines)) < rr]
    if r.empty:
        return
    n = len(r)
    qty = r.quantity.to_numpy()
    rq = np.minimum(qty, 1 + rng.binomial(np.maximum(qty - 1, 0), 0.3))
    receipt = rng.random(n) >= C.RETURN_NO_RECEIPT_RATE
    other_store = rng.random(n) < 0.10
    cust = r.customer_id.astype(object).to_numpy()
    st.pending_returns = pd.concat([st.pending_returns, pd.DataFrame({
        "return_date": [d + timedelta(days=int(x)) for x in 1 + np.minimum(rng.geometric(0.12, n), 29)],
        "store_id": r.store_id.to_numpy(), "other_store": other_store,
        "customer_id": np.where(receipt | (rng.random(n) < 0.5), cust, None),
        "original_sale_id": np.where(receipt, r.sale_id.to_numpy(), None),
        "original_sale_line_id": np.where(receipt, r.sale_line_id.to_numpy(), None),
        "original_online_order_id": None,
        "sku": r.sku.to_numpy(), "product_idx": r.product_idx.to_numpy(), "quantity": rq,
        "refund_incl_vat": np.round(r.line_total_incl_vat.to_numpy() / qty * rq, 2),
        "reason_code": rng.choice(RETURN_REASONS[0], n, p=RETURN_REASONS[1]),
        "country_code": sales.set_index("sale_id").loc[r.sale_id, "country_code"].to_numpy(),
    })], ignore_index=True)


def _release_returns(st: State, d: date, pg: PostgresSink, stats: dict) -> pd.DataFrame:
    pr = st.pending_returns
    if pr.empty:
        stats["returns"] = 0
        return pd.DataFrame(columns=["store_id", "product_idx", "quantity"])
    due = pr[pr.return_date == d].copy()
    st.pending_returns = pr[pr.return_date != d].reset_index(drop=True)
    if due.empty:
        stats["returns"] = 0
        return pd.DataFrame(columns=["store_id", "product_idx", "quantity"])
    rng = st.rng
    stores = st.stores
    open_by_cc = {cc: stores[(~stores.is_online) & (stores.country_code == cc)
                             & stores.apply(lambda s: _is_open(s, d), axis=1)].store_id.to_numpy()
                  for cc in C.COUNTRIES}
    open_set = set(np.concatenate(list(open_by_cc.values())))
    new_store = []
    for row in due.itertuples():
        if row.other_store or row.store_id not in open_set or pd.isna(row.store_id):
            opts = open_by_cc[row.country_code]
            new_store.append(int(opts[rng.integers(0, len(opts))]))
        else:
            new_store.append(int(row.store_id))
    due["store_id"] = new_store

    # One return receipt per (store, original transaction); no-receipt items are separate receipts
    key = np.where(due.original_sale_id.notna(), due.original_sale_id.astype(str),
                   np.where(due.original_online_order_id.notna(), due.original_online_order_id.astype(str),
                            "nr" + pd.Series(np.arange(len(due))).astype(str).to_numpy()))
    due["grp"] = pd.factorize(pd.Series(due.store_id.astype(str).to_numpy() + "|" + key))[0]
    hdr = due.groupby("grp").first().reset_index()
    hdr["return_id"] = st.next_id("return_id", len(hdr))
    cur = stores.set_index("store_id").currency_code
    hdr["currency_code"] = cur.loc[hdr.store_id].to_numpy()
    times = []
    for row in hdr.itertuples():
        times.append(business_times(rng, d, row.country_code, 1)[0])
    hdr["returned_at"] = pd.to_datetime(times, utc=True)
    hdr["created_at"] = hdr["updated_at"] = hdr["returned_at"]
    cash = st.cashiers[~st.cashiers.is_training]
    hdr["cashier_id"] = [int(rng.choice(cash[cash.store_id == s].cashier_id.to_numpy())) for s in hdr.store_id]
    for col in ("customer_id", "original_sale_id"):
        hdr[col] = pd.array(hdr[col].astype(object).where(hdr[col].notna(), None), dtype="Int64")
    due = due.merge(hdr[["grp", "return_id", "returned_at"]], on="grp")
    due["return_line_id"] = st.next_id("return_line_id", len(due))
    due["created_at"] = due["returned_at"]
    due["original_sale_line_id"] = pd.array(
        due.original_sale_line_id.astype(object).where(due.original_sale_line_id.notna(), None), dtype="Int64")
    pg.copy("returns", hdr, RET_COLS)
    pg.copy("return_lines", due, RET_LINE_COLS)
    stats["returns"] = len(hdr)
    back = due[due.reason_code.isin(["changed_mind", "wrong_item"])]
    return back.groupby(["store_id", "product_idx"], as_index=False).quantity.sum()


# ---------------------------------------------------------------------------
# Online store
# ---------------------------------------------------------------------------
def _online_orders(st: State, d: date, ctx: dict, stats: dict) -> None:
    rng, prof = st.rng, st.profile
    p = st.products
    skus = p.sku.to_numpy()
    w = ctx["demand_w"].copy()
    w[p.sku.to_numpy() == C.TEST_SKU] = 0
    w = w / w.sum()
    growth = 1 + 0.15 * (d - st.start).days / 365
    cust = st.customers
    events, n_total = [], 0
    for cc in C.COUNTRIES:
        n = int(rng.poisson(prof.online_orders_per_day * C.COUNTRY_SHARE_ONLINE[cc]
                            * sales_multiplier(cc, d) * growth))
        if n == 0:
            continue
        n_total += n
        pool_ix, pool_w = ctx["pools"][(cc, "online")]
        registered = (rng.random(n) < 0.85) & (pool_ix.size > 0)
        cust_rows = np.full(n, -1)
        if registered.any():
            cust_rows[registered] = rng.choice(pool_ix, registered.sum(), p=pool_w)
        channel = rng.choice(["web", "app"], n, p=[0.45, 0.55])
        pay = rng.choice(["card", "apple_pay", "cod"], n, p=[0.55, 0.20, 0.25])
        secs = rng.choice(24, n, p=ONLINE_HOUR_W) * 3600 + rng.integers(0, 3600, n)
        placed = day_start_utc(d, cc) + pd.to_timedelta(secs, unit="s")
        h = lambda lo, hi: pd.to_timedelta(rng.uniform(lo, hi, n), unit="h")  # noqa: E731
        paid_pre = placed + pd.to_timedelta(rng.uniform(1, 20, n), unit="m")
        shipped = placed + h(18, 60)
        delivered = shipped + (h(6, 30) if cc == "QA" else h(12, 96))
        paid = np.where(pay == "cod", delivered + pd.to_timedelta(rng.uniform(0, 30, n), unit="m"), paid_pre)
        cancelled = rng.random(n) < C.CANCEL_RATE
        cancel_h = np.minimum(47.0, (shipped - placed).total_seconds().to_numpy() / 3600 - 0.5)
        cancel_at = placed + pd.to_timedelta(rng.uniform(0.5, 1, n) * cancel_h, unit="h")
        late = rng.random(n) < C.LATE_ORDER_RATE
        release = [d + timedelta(days=int(k)) if lt else d for lt, k in zip(late, rng.integers(1, 3, n))]

        nl = 1 + rng.poisson(0.5, n)
        pidx = rng.choice(len(p), nl.sum(), p=w)
        qty = 1 + rng.binomial(np.maximum(p.qty_max.to_numpy()[pidx] - 1, 0), 0.25)
        unit = ctx["shelf"][cc][pidx]
        order_ix = np.repeat(np.arange(n), nl)
        seasonal = ctx["promos"][cc]
        use = rng.random(n) < (0.4 if len(seasonal) else 0.0)
        pick = rng.integers(0, max(1, len(seasonal)), n)
        codes = np.where(use, seasonal.promotion_code.to_numpy()[pick] if len(seasonal) else None, None)
        pct = np.where(use, seasonal.discount_value.to_numpy()[pick] if len(seasonal) else 0.0, 0.0)
        disc = np.round(unit * qty * pct[order_ix] / 100, 2)
        starts = np.cumsum(nl) - nl

        for i in range(n):
            seq = st.next_id("order_seq")[0]
            oid = f"{'WEB' if channel[i] == 'web' else 'APP'}-{d.year}-{seq:07d}"
            sl = slice(starts[i], starts[i] + nl[i])
            lines = [dict(line_number=k + 1, sku=str(skus[pidx[j]]), quantity=int(qty[j]),
                          unit_price_incl_vat=float(unit[j]), discount_incl_vat=float(disc[j]))
                     for k, j in enumerate(range(sl.start, sl.stop))]
            cr = cust_rows[i]
            st.pending_orders[oid] = dict(
                order_id=oid, customer_id=cust.online_customer_id.iat[cr] if cr >= 0 else None,
                channel=channel[i], ship_country=cc, currency=C.CURRENCY[cc], payment_method=pay[i],
                promotion_code=codes[i], placed_at=placed[i], lines=json.dumps(lines, ensure_ascii=False))
            ev = [(oid, "placed", placed[i])]
            if cancelled[i]:
                if pay[i] != "cod" and paid_pre[i] < cancel_at[i]:
                    ev.append((oid, "paid", paid_pre[i]))
                ev.append((oid, "cancelled", cancel_at[i]))
            else:
                ev += [(oid, "paid", pd.Timestamp(paid[i])), (oid, "shipped", shipped[i]),
                       (oid, "delivered", delivered[i])]
                _schedule_online_returns(st, oid, cc, cr, lines, pidx[sl], delivered[i])
            events += [(o, s_, pd.Timestamp(t), release[i]) for o, s_, t in ev]
    if events:
        new = pd.DataFrame(events, columns=["order_id", "status", "event_at", "release_date"])
        pe = pd.concat([st.pending_events, new], ignore_index=True)
        pe["event_at"] = pd.to_datetime(pe.event_at, utc=True)
        st.pending_events = pe
    stats["online_orders"] = n_total


def _schedule_online_returns(st: State, oid: str, cc: str, cust_row: int, lines: list, pidx, delivered) -> None:
    rng = st.rng
    rows = []
    pos_id = st.customers.pos_customer_id.iat[cust_row] if cust_row >= 0 else None
    for ln, pi in zip(lines, pidx):
        if rng.random() < C.ONLINE_RETURN_RATE:
            rows.append(dict(
                return_date=(delivered + pd.Timedelta(hours=C.TZ_OFFSET_HOURS[cc])).date()
                + timedelta(days=int(rng.integers(1, 21))),
                store_id=np.nan, other_store=True, customer_id=None if pd.isna(pos_id) else pos_id,
                original_sale_id=None, original_sale_line_id=None, original_online_order_id=oid,
                sku=ln["sku"], product_idx=int(pi), quantity=1,
                refund_incl_vat=round(ln["unit_price_incl_vat"] - ln["discount_incl_vat"] / ln["quantity"], 2),
                reason_code=rng.choice(RETURN_REASONS[0], p=RETURN_REASONS[1]), country_code=cc))
    if rows:
        st.pending_returns = pd.concat([st.pending_returns, pd.DataFrame(rows)], ignore_index=True)


def _emit_online(st: State, d: date, online: OnlineSink, stats: dict) -> None:
    """Publish every event that has happened by the end of day d (and whose
    order is not arriving late) to the API database."""
    rng = st.rng
    pe = st.pending_events
    h_now, h_prev = horizon(d), horizon(d - timedelta(days=1))
    due_mask = (pe.event_at < h_now) & (pe.release_date.map(lambda r: r <= d))
    due = pe[due_mask].copy()
    st.pending_events = pe[~due_mask].reset_index(drop=True)
    if due.empty:
        stats["online_events"] = 0
        return
    span = (h_now - h_prev).total_seconds()
    jitter = pd.to_timedelta(rng.uniform(0, span, len(due)), unit="s")
    due["visible_at"] = np.where(due.event_at >= h_prev, due.event_at, h_prev + jitter)
    due["visible_at"] = pd.to_datetime(due.visible_at, utc=True)
    due = due.sort_values(["visible_at", "event_at"])
    due["event_id"] = st.next_id("event_id", len(due))
    online.insert("order_events", pd.DataFrame({
        "event_id": due.event_id, "order_id": due.order_id, "status": due.status,
        "event_at": iso(due.event_at).values, "updated_at": iso(due.visible_at).values}))

    # Order status = furthest lifecycle stage reached, not the latest event
    # (cash-on-delivery orders are 'paid' after they are 'delivered').
    due["rank"] = due.status.map(STATUS_RANK)
    latest = due.sort_values("rank").groupby("order_id").agg(status=("status", "last"),
                                                             updated_at=("visible_at", "max"))
    new_ids = due.loc[due.status == "placed", "order_id"].unique()
    new_orders = pd.DataFrame([st.pending_orders.pop(o) for o in new_ids])
    if not new_orders.empty:
        new_orders = new_orders.join(latest, on="order_id")
        new_orders["placed_at"] = iso(new_orders.placed_at).values
        new_orders["updated_at"] = iso(new_orders.updated_at).values
        online.insert("orders", new_orders[["order_id", "customer_id", "channel", "ship_country", "currency",
                                            "payment_method", "promotion_code", "placed_at", "status",
                                            "updated_at", "lines"]])
    upd = latest.drop(index=new_ids)
    online.update_orders(list(zip(upd.status, iso(upd.updated_at).values, upd.index)))
    stats["online_events"] = len(due)


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------
def _new_customers(st: State, d: date, acquisitions: dict, pg: PostgresSink, online: OnlineSink) -> int:
    rng, prof = st.rng, st.profile
    countries, channels, created = [], [], []
    shares = {"AE": 0.45, "SA": 0.45, "QA": 0.10}
    for cc in C.COUNTRIES:
        counts = {"organic": int(rng.poisson(prof.organic_customers_per_day * shares[cc]
                                             * sales_multiplier(cc, d)))}
        for ch in C.MARKETING_CHANNELS:
            counts[ch] = acquisitions.get((ch, cc), 0)
        for ch, k in counts.items():
            if k:
                countries += [cc] * k
                channels += [ch] * k
                created += list(business_times(rng, d, cc, k))
    if not countries:
        return 0
    new, st.counters["pos_customer_id"], st.counters["cust_idx"] = R.make_customers(
        rng, st.names, st.stores[st.stores.inserted], np.array(countries), np.array(channels), np.array(created),
        st.counters["pos_customer_id"], st.counters["cust_idx"])
    st.customers = pd.concat([st.customers, new], ignore_index=True)
    _write_customers(new, pg, online)
    return len(new)


def _tier_changes(st: State, d: date, pg: PostgresSink) -> None:
    rng = st.rng
    c = st.customers
    pos_rows = np.flatnonzero(c.pos_customer_id.notna().to_numpy()
                              & (c.created_at < day_start_utc(d, "AE")).to_numpy())
    k = int(rng.poisson(pos_rows.size * 0.0005))
    if k == 0:
        return
    rows = rng.choice(pos_rows, k, replace=False)
    tiers = list(C.LOYALTY_TIERS)
    params = []
    for r in rows:
        cur = tiers.index(c.loyalty_tier.iat[r])
        new = min(cur + 1, 3) if rng.random() < 0.8 else max(cur - 1, 0)
        if new == cur:
            continue
        c.iat[r, c.columns.get_loc("loyalty_tier")] = tiers[new]
        ts = business_times(rng, d, c.country_code.iat[r], 1)[0]
        params.append((tiers[new], ts.to_pydatetime(), int(c.pos_customer_id.iat[r])))
    pg.executemany("UPDATE pos.customers SET loyalty_tier = %s, updated_at = %s WHERE customer_id = %s", params)


# ---------------------------------------------------------------------------
# Marketing
# ---------------------------------------------------------------------------
def _marketing(st: State, d: date) -> dict:
    rng, prof = st.rng, st.profile
    camps = st.campaigns
    # Campaign names drift: platforms let marketers rename campaigns at any time
    drift = rng.random(len(camps)) < 0.002
    camps.loc[drift, "campaign_name"] = camps.loc[drift, "campaign_name"].map(
        lambda s: s.replace(" | ", " - ") if " | " in s else s + " (v2)")
    act = camps[(camps.starts_on <= d) & (camps.ends_on >= d)].copy()
    ch_cfg = C.MARKETING_CHANNELS
    base = np.array([ch_cfg[c]["share"] for c in act.marketing_channel]) \
        * np.array([C.COUNTRY_SHARE_MARKETING[c] for c in act.country_code]) * prof.marketing_aed_per_day
    act["spend_aed"] = base * np.where(act.is_always_on, 1.0, 1.2) * rng.lognormal(0, 0.15, len(act))
    cur = act.marketing_channel.map(lambda c: ch_cfg[c]["currency"])
    act["currency_code"] = cur
    act["spend"] = np.round(act.spend_aed / cur.map(C.AED_PER_UNIT), 2)
    cpm = act.marketing_channel.map(lambda c: ch_cfg[c]["cpm"]).to_numpy()
    ctr = act.marketing_channel.map(lambda c: ch_cfg[c]["ctr"]).to_numpy()
    act["impressions"] = (act.spend_aed / cpm * 1000 * rng.lognormal(0, 0.1, len(act))).astype(int)
    act["clicks"] = rng.binomial(act.impressions.to_numpy(), np.clip(ctr * rng.lognormal(0, 0.1, len(act)), 0, 1))
    act["date"] = d

    acq = act.groupby(["marketing_channel", "country_code"]).spend_aed.sum()
    acquisitions = {k: int(rng.poisson(v / ch_cfg[k[0]]["cac"])) for k, v in acq.items()}

    # Platforms restate the previous two days
    recent = st.marketing_recent
    if not recent.empty:
        recent = recent[recent.date >= d - timedelta(days=2)].copy()
        fix = rng.random(len(recent)) < 0.4
        f = 1 + rng.normal(0, 0.03, fix.sum())
        recent.loc[fix, "spend"] = np.round(recent.loc[fix, "spend"] * f, 2)
        recent.loc[fix, "impressions"] = (recent.loc[fix, "impressions"] * f).astype(int)
        recent.loc[fix, "clicks"] = (recent.loc[fix, "clicks"] * f).astype(int)
        recent["campaign_name"] = recent.campaign_id.map(camps.set_index("campaign_id").campaign_name)
    cols = ["date", "campaign_id", "campaign_name", "marketing_channel", "country_code", "currency_code",
            "spend", "impressions", "clicks"]
    out = pd.concat([act[cols], recent[cols] if not recent.empty else None], ignore_index=True)
    for ch, g in out.groupby("marketing_channel"):
        write_csv(g.sort_values(["date", "campaign_id"]),
                  C.LANDING_DIR / "marketing" / ch / f"spend_{d.isoformat()}.csv")
    st.marketing_recent = out[out.date >= d - timedelta(days=1)].reset_index(drop=True)
    return acquisitions


# ---------------------------------------------------------------------------
# Inventory & catalog
# ---------------------------------------------------------------------------
def _inventory(st: State, d: date, sold: pd.DataFrame, restock: pd.DataFrame, stats: dict) -> None:
    rng = st.rng
    inv = st.inventory.set_index(["store_id", "product_idx"])
    for df, sign in ((sold, -1), (restock, 1)):
        if df is not None and not df.empty:
            q = df.set_index(["store_id", "product_idx"]).quantity
            inv["on_hand"] = inv.on_hand + sign * q.reindex(inv.index, fill_value=0).to_numpy()
    inv["on_hand"] = inv.on_hand.clip(lower=0)

    # Receive purchase orders that are due today
    recv = (inv.po_qty > 0) & (inv.due_on.map(lambda x: not pd.isna(x) and x <= d))
    received = inv[recv].assign(received_on=d)
    inv.loc[recv, "on_hand"] += inv.loc[recv, "po_qty"]
    inv.loc[recv, ["po_qty"]] = 0
    inv.loc[recv, ["po_number", "ordered_on", "expected_on", "due_on"]] = None

    # Raise new purchase orders below the reorder point
    need = (inv.on_hand < inv.reorder) & (inv.po_qty == 0)
    store_code = st.stores.set_index("store_id").store_code
    if need.any():
        n = int(need.sum())
        lead = rng.integers(3, 8, n)
        delay = np.where(rng.random(n) < 0.2, rng.integers(1, 3, n), 0)
        idx = inv.index[need]
        inv.loc[need, "po_qty"] = (inv.loc[need, "target"] - inv.loc[need, "on_hand"]).to_numpy()
        inv.loc[need, "po_number"] = [f"PO-{store_code[s]}-{d:%Y%m%d}" for s in idx.get_level_values(0)]
        inv.loc[need, "ordered_on"] = d
        inv.loc[need, "expected_on"] = [d + timedelta(days=int(x)) for x in lead]
        inv.loc[need, "due_on"] = [d + timedelta(days=int(x + y)) for x, y in zip(lead, delay)]
    created = inv[need].assign(received_on=None)
    st.inventory = inv.reset_index()

    skus = st.products.sku
    cost = st.products.unit_cost_aed
    # Daily PO extract: lines ordered today + lines received today (captured before clearing)
    po = pd.concat([created, received]).reset_index()
    if not po.empty:
        write_csv(_po_extract(po, store_code, skus, cost),
                  C.LANDING_DIR / "erp" / "purchase_orders" / f"purchase_orders_{d.isoformat()}.csv")

    if rng.random() < C.MISSING_STOCK_FILE_RATE:
        stats["stock_file"] = "missing"
        return
    launched = st.products.launched_on.to_numpy()[st.inventory.product_idx.to_numpy()] <= d
    snap = st.inventory[launched]
    on_hand = snap.on_hand.to_numpy().copy()
    neg = rng.random(on_hand.size) < C.NEGATIVE_STOCK_RATE
    on_hand[neg] = -rng.integers(1, 4, neg.sum())
    out = pd.DataFrame({"snapshot_date": d, "store_code": store_code.loc[snap.store_id].to_numpy(),
                        "sku": skus.loc[snap.product_idx].to_numpy(), "qty_on_hand": on_hand,
                        "qty_on_order": snap.po_qty.to_numpy()})
    write_csv(out, C.LANDING_DIR / "erp" / "stock_on_hand" / f"stock_on_hand_{d.isoformat()}.csv.gz", gzip=True)
    stats["stock_rows"] = len(out)


def _po_extract(po: pd.DataFrame, store_code, skus, cost) -> pd.DataFrame:
    return pd.DataFrame({
        "po_number": po.po_number.to_numpy(), "store_code": store_code.loc[po.store_id].to_numpy(),
        "sku": skus.loc[po.product_idx].to_numpy(), "qty_ordered": po.po_qty.to_numpy(),
        "ordered_on": po.ordered_on.to_numpy(), "expected_on": po.expected_on.to_numpy(),
        "received_on": po.received_on.to_numpy(), "unit_cost": cost.loc[po.product_idx].to_numpy(),
        "currency_code": "AED"})


def _catalog_export(st: State, d: date) -> None:
    p = st.products
    out = p[p.launched_on <= d][["sku", "product_name_en", "product_name_ar", "category", "subcategory", "brand",
                                 "unit_cost_aed", "list_price_aed", "is_active", "launched_on"]].copy()
    out["export_date"] = d
    write_csv(out, C.LANDING_DIR / "catalog" / f"products_{d.isoformat()}.csv.gz", gzip=True)
