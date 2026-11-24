"""Reference data: stores, cashiers, products, customers, promotions, campaigns."""

from __future__ import annotations

import string
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd
from faker import Faker

from . import config as C
from .gulf_calendar import seasonal_events

# ---------------------------------------------------------------------------
# Stores: 25 physical + 3 virtual online stores
# (code, name_en, name_ar, country, city, format, status)
#   status: "existing" | "open_1" | "open_2" | "open_3" | "close"
# ---------------------------------------------------------------------------
STORES = [
    ("AE-DXB-01", "Najm The Dubai Mall", "نجم دبي مول", "AE", "Dubai", "flagship", "existing"),
    ("AE-DXB-02", "Najm Mall of the Emirates", "نجم مول الإمارات", "AE", "Dubai", "flagship", "existing"),
    ("AE-DXB-03", "Najm Ibn Battuta", "نجم ابن بطوطة", "AE", "Dubai", "mall", "existing"),
    ("AE-DXB-04", "Najm Dubai Festival City", "نجم دبي فستيفال سيتي", "AE", "Dubai", "mall", "existing"),
    ("AE-DXB-05", "Najm Al Barsha Express", "نجم البرشا إكسبرس", "AE", "Dubai", "express", "open_1"),
    ("AE-AUH-01", "Najm Yas Mall", "نجم ياس مول", "AE", "Abu Dhabi", "flagship", "existing"),
    ("AE-AUH-02", "Najm Al Wahda", "نجم الوحدة", "AE", "Abu Dhabi", "mall", "existing"),
    ("AE-AUH-03", "Najm Marina Mall", "نجم مارينا مول", "AE", "Abu Dhabi", "mall", "existing"),
    ("AE-SHJ-01", "Najm Sahara Centre", "نجم صحارى سنتر", "AE", "Sharjah", "mall", "existing"),
    ("AE-SHJ-02", "Najm City Centre Sharjah", "نجم سيتي سنتر الشارقة", "AE", "Sharjah", "mall", "close"),
    ("AE-AAN-01", "Najm Al Jimi Express", "نجم الجيمي إكسبرس", "AE", "Al Ain", "express", "existing"),
    ("SA-RUH-01", "Najm Riyadh Park", "نجم الرياض بارك", "SA", "Riyadh", "flagship", "existing"),
    ("SA-RUH-02", "Najm Al Nakheel Riyadh", "نجم النخيل الرياض", "SA", "Riyadh", "mall", "existing"),
    ("SA-RUH-03", "Najm Panorama", "نجم بانوراما", "SA", "Riyadh", "mall", "existing"),
    ("SA-RUH-04", "Najm Granada Express", "نجم غرناطة إكسبرس", "SA", "Riyadh", "express", "open_2"),
    ("SA-JED-01", "Najm Red Sea Mall", "نجم رد سي مول", "SA", "Jeddah", "flagship", "existing"),
    ("SA-JED-02", "Najm Mall of Arabia", "نجم مول العرب", "SA", "Jeddah", "mall", "existing"),
    ("SA-JED-03", "Najm Al Andalus Express", "نجم الأندلس إكسبرس", "SA", "Jeddah", "express", "existing"),
    ("SA-DMM-01", "Najm Dhahran Mall", "نجم الظهران مول", "SA", "Dammam", "mall", "existing"),
    ("SA-DMM-02", "Najm Nakheel Dammam Express", "نجم النخيل الدمام إكسبرس", "SA", "Dammam", "express", "existing"),
    ("SA-KHB-01", "Najm Al Rashid Mall", "نجم الراشد مول", "SA", "Khobar", "mall", "existing"),
    ("QA-DOH-01", "Najm Place Vendome", "نجم بلاس فاندوم", "QA", "Doha", "flagship", "existing"),
    ("QA-DOH-02", "Najm Villaggio", "نجم فيلاجيو", "QA", "Doha", "mall", "existing"),
    ("QA-DOH-03", "Najm Doha Festival City", "نجم الدوحة فستيفال سيتي", "QA", "Doha", "mall", "open_3"),
    ("QA-WAK-01", "Najm Al Wakrah Express", "نجم الوكرة إكسبرس", "QA", "Al Wakrah", "express", "existing"),
    ("ONL-AE", "Najm Online UAE", "نجم أونلاين الإمارات", "AE", "Dubai", "online", "existing"),
    ("ONL-SA", "Najm Online KSA", "نجم أونلاين السعودية", "SA", "Riyadh", "online", "existing"),
    ("ONL-QA", "Najm Online Qatar", "نجم أونلاين قطر", "QA", "Doha", "online", "existing"),
]
FORMAT_WEIGHT = {"flagship": 1.8, "mall": 1.0, "express": 0.5, "online": 0.0}
FORMAT_REGISTERS = {"flagship": 6, "mall": 4, "express": 2, "online": 0}
FORMAT_CASHIERS = {"flagship": 10, "mall": 7, "express": 4, "online": 0}
# Assortment (number of SKUs) at full scale; scaled by n_products / 15000
FORMAT_ASSORTMENT = {"flagship": 3000, "mall": 1500, "express": 600, "online": 0}


def build_stores(rng: np.random.Generator, end: date) -> pd.DataFrame:
    """Store master. Opening/closing dates are relative to `end` so both the
    3-month dev window and the 3-year full window contain them."""
    event_dates = {
        "open_1": end - timedelta(days=760),
        "open_2": end - timedelta(days=430),
        "open_3": end - timedelta(days=50),
    }
    close_date = end - timedelta(days=65)
    rows = []
    for i, (code, en, ar, cc, city, fmt, status) in enumerate(STORES, start=1):
        if status in event_dates:
            opened = event_dates[status]
        elif fmt == "online":
            opened = date(2019, 1, 1)
        else:
            opened = date(2012, 1, 1) + timedelta(days=int(rng.integers(0, 365 * 9)))
        rows.append(dict(
            store_id=i, store_code=code, store_name_en=en, store_name_ar=ar,
            country_code=cc, city=city, store_format=fmt,
            currency_code=C.CURRENCY[cc], timezone=C.TIMEZONE[cc],
            opened_on=opened, closed_on=None,
            planned_close_on=close_date if status == "close" else None,
            weight=FORMAT_WEIGHT[fmt] * float(rng.uniform(0.85, 1.15)),
            registers=FORMAT_REGISTERS[fmt], is_online=fmt == "online",
            inserted=False,
        ))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Names
# ---------------------------------------------------------------------------
ARAB_FIRST = [
    ("Mohammed", "محمد"), ("Ahmed", "أحمد"), ("Abdullah", "عبدالله"), ("Khalid", "خالد"),
    ("Omar", "عمر"), ("Ali", "علي"), ("Saeed", "سعيد"), ("Hamad", "حمد"), ("Sultan", "سلطان"),
    ("Faisal", "فيصل"), ("Yousef", "يوسف"), ("Rashid", "راشد"), ("Majed", "ماجد"), ("Nasser", "ناصر"),
    ("Fahad", "فهد"), ("Saud", "سعود"), ("Hassan", "حسن"), ("Ibrahim", "إبراهيم"), ("Tariq", "طارق"),
    ("Fatima", "فاطمة"), ("Aisha", "عائشة"), ("Maryam", "مريم"), ("Noura", "نورة"), ("Sara", "سارة"),
    ("Hessa", "حصة"), ("Latifa", "لطيفة"), ("Reem", "ريم"), ("Shamma", "شما"), ("Alia", "علياء"),
    ("Amna", "آمنة"), ("Huda", "هدى"), ("Layla", "ليلى"), ("Dana", "دانة"), ("Lulwa", "لولوة"),
]
ARAB_LAST = [
    ("Al Mansoori", "المنصوري"), ("Al Nuaimi", "النعيمي"), ("Al Maktoum", "آل مكتوم"),
    ("Al Shamsi", "الشامسي"), ("Al Mazrouei", "المزروعي"), ("Al Ketbi", "الكتبي"),
    ("Al Qahtani", "القحطاني"), ("Al Ghamdi", "الغامدي"), ("Al Otaibi", "العتيبي"),
    ("Al Harbi", "الحربي"), ("Al Zahrani", "الزهراني"), ("Al Dosari", "الدوسري"),
    ("Al Thani", "آل ثاني"), ("Al Kuwari", "الكواري"), ("Al Marri", "المري"),
    ("Al Sulaiti", "السليطي"), ("Al Hashimi", "الهاشمي"), ("Al Suwaidi", "السويدي"),
    ("Al Falasi", "الفلاسي"), ("Al Shehhi", "الشحي"), ("Al Rashidi", "الرشيدي"),
]


class NamePool:
    """Pre-generated name pools; sampling with numpy is ~1000x faster than Faker per row."""

    def __init__(self, seed: int):
        fake = Faker(["en_IN", "en_GB", "en_PH", "en_US"])
        fake.seed_instance(seed)
        self.expat_first = np.array([fake.first_name() for _ in range(800)])
        self.expat_last = np.array([fake.last_name() for _ in range(800)])
        self.arab_first = np.array(ARAB_FIRST)
        self.arab_last = np.array(ARAB_LAST)

    def sample(self, rng: np.random.Generator, n: int, arab_share: float = 0.55) -> pd.DataFrame:
        is_arab = rng.random(n) < arab_share
        af = self.arab_first[rng.integers(0, len(self.arab_first), n)]
        al = self.arab_last[rng.integers(0, len(self.arab_last), n)]
        ef = self.expat_first[rng.integers(0, len(self.expat_first), n)]
        el = self.expat_last[rng.integers(0, len(self.expat_last), n)]
        return pd.DataFrame({
            "first_name": np.where(is_arab, af[:, 0], ef),
            "last_name": np.where(is_arab, al[:, 0], el),
            "first_name_ar": np.where(is_arab, af[:, 1], None),
            "last_name_ar": np.where(is_arab, al[:, 1], None),
        })


def build_cashiers(rng: np.random.Generator, stores: pd.DataFrame, names: NamePool,
                   start_id: int = 1) -> pd.DataFrame:
    rows = []
    cid = start_id
    for s in stores.itertuples():
        n = FORMAT_CASHIERS[s.store_format]
        if n == 0:
            continue
        nm = names.sample(rng, n)
        for k in range(n):
            rows.append(dict(cashier_id=cid, cashier_code=f"{s.store_code}-C{k + 1:02d}",
                             store_id=s.store_id,
                             full_name=f"{nm.first_name[k]} {nm.last_name[k]}",
                             hired_on=max(s.opened_on, date(2015, 1, 1)) + timedelta(days=int(rng.integers(0, 300))),
                             is_training=False))
            cid += 1
        rows.append(dict(cashier_id=cid, cashier_code=f"TRN-{s.store_code}", store_id=s.store_id,
                         full_name="Training Mode", hired_on=s.opened_on, is_training=True))
        cid += 1
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Product catalog
# (category_en, category_ar, sku_prefix, demand_weight, return_rate,
#  [(subcategory_en, subcategory_ar, price_lo_aed, price_hi_aed, max_qty)], brands)
# Prices are list prices in AED excluding VAT.
# ---------------------------------------------------------------------------
CATALOG = [
    ("TV & Audio", "التلفزيونات والصوتيات", "TVA", 0.10, 0.05,
     [("Television", "تلفزيون", 900, 12000, 1), ("Soundbar", "مكبر صوت", 300, 4000, 1),
      ("Headphones", "سماعات رأس", 80, 1800, 2), ("Speaker", "سماعة", 100, 2500, 2)],
     ["Samsung", "LG", "Sony", "TCL", "Hisense", "JBL", "Bose"]),
    ("Mobiles & Tablets", "الهواتف والأجهزة اللوحية", "MOB", 0.16, 0.06,
     [("Smartphone", "هاتف ذكي", 500, 6500, 1), ("Tablet", "جهاز لوحي", 600, 5000, 1),
      ("Smartwatch", "ساعة ذكية", 200, 3500, 1)],
     ["Apple", "Samsung", "Xiaomi", "Huawei", "Honor", "OPPO"]),
    ("Computers", "أجهزة الكمبيوتر", "CMP", 0.09, 0.05,
     [("Laptop", "حاسوب محمول", 1500, 11000, 1), ("Monitor", "شاشة", 400, 4500, 1),
      ("Printer", "طابعة", 250, 2500, 1), ("Keyboard", "لوحة مفاتيح", 60, 700, 2)],
     ["Apple", "HP", "Dell", "Lenovo", "ASUS", "Acer", "Logitech"]),
    ("Gaming", "الألعاب", "GAM", 0.07, 0.04,
     [("Console", "جهاز ألعاب", 1200, 2800, 1), ("Video Game", "لعبة فيديو", 100, 350, 3),
      ("Controller", "يد تحكم", 150, 450, 2)],
     ["Sony", "Microsoft", "Nintendo", "Razer"]),
    ("Cameras", "الكاميرات", "CAM", 0.03, 0.05,
     [("Camera", "كاميرا", 900, 14000, 1), ("Action Camera", "كاميرا رياضية", 700, 2500, 1),
      ("Drone", "طائرة مسيرة", 1500, 8000, 1)],
     ["Canon", "Nikon", "Sony", "GoPro", "DJI", "Fujifilm"]),
    ("Large Appliances", "الأجهزة المنزلية الكبيرة", "LAP", 0.05, 0.03,
     [("Refrigerator", "ثلاجة", 1500, 9000, 1), ("Washing Machine", "غسالة", 1200, 5000, 1),
      ("Air Conditioner", "مكيف هواء", 1400, 6000, 1), ("Dishwasher", "غسالة صحون", 1300, 4500, 1)],
     ["Samsung", "LG", "Bosch", "Midea", "Haier", "Whirlpool"]),
    ("Small Appliances", "الأجهزة المنزلية الصغيرة", "SAP", 0.12, 0.07,
     [("Vacuum Cleaner", "مكنسة كهربائية", 250, 3000, 1), ("Air Fryer", "قلاية هوائية", 200, 1000, 1),
      ("Coffee Machine", "آلة قهوة", 300, 4000, 1), ("Iron", "مكواة", 80, 600, 1),
      ("Hair Dryer", "مجفف شعر", 90, 1800, 1)],
     ["Philips", "Dyson", "Tefal", "Braun", "Nespresso", "Kenwood", "Xiaomi"]),
    ("Kitchen & Dining", "المطبخ والطعام", "KIT", 0.08, 0.06,
     [("Cookware Set", "طقم أواني طهي", 150, 1500, 1), ("Dinner Set", "طقم عشاء", 120, 1200, 1),
      ("Knife Set", "طقم سكاكين", 80, 900, 1), ("Dallah", "دلة", 60, 450, 2)],
     ["Tefal", "Zwilling", "Luminarc", "Tognana", "Royalford"]),
    ("Home & Furniture", "المنزل والأثاث", "HOM", 0.06, 0.08,
     [("Office Chair", "كرسي مكتب", 300, 2500, 1), ("Bedding Set", "طقم مفارش", 150, 1200, 2),
      ("Lamp", "مصباح", 60, 800, 2), ("Rug", "سجادة", 200, 3000, 1)],
     ["Najm Home", "Dar Living", "Sahra Home", "Pan Home"]),
    ("Smart Home", "المنزل الذكي", "SMH", 0.05, 0.06,
     [("Smart Speaker", "مكبر صوت ذكي", 150, 1200, 1), ("Security Camera", "كاميرا مراقبة", 150, 900, 2),
      ("Smart Plug", "قابس ذكي", 40, 150, 4), ("Robot Vacuum", "مكنسة روبوت", 800, 5000, 1)],
     ["Amazon", "Google", "TP-Link", "Xiaomi", "Ring", "Eufy"]),
    ("Accessories", "الإكسسوارات", "ACC", 0.19, 0.04,
     [("Charger", "شاحن", 40, 300, 3), ("Cable", "كابل", 20, 150, 4), ("Phone Case", "غطاء هاتف", 30, 250, 3),
      ("Power Bank", "شاحن متنقل", 60, 400, 2), ("Memory Card", "بطاقة ذاكرة", 30, 400, 3)],
     ["Anker", "Belkin", "Samsung", "Apple", "Baseus", "SanDisk", "Ugreen"]),
]
CATEGORY_AR = {c[0]: c[1] for c in CATALOG}
SUBCATEGORY_AR = {s[0]: s[1] for c in CATALOG for s in c[5]}


def _model_code(rng: np.random.Generator) -> str:
    letters = "".join(rng.choice(list(string.ascii_uppercase), 2))
    return f"{letters}{int(rng.integers(10, 999))}"


def build_products(rng: np.random.Generator, n_products: int, start: date, end: date) -> pd.DataFrame:
    weights = np.array([c[3] for c in CATALOG])
    counts = np.maximum(1, np.round(weights / weights.sum() * n_products)).astype(int)
    rows = []
    for (cat_en, _cat_ar, prefix, cat_w, ret, subs, brands), n in zip(CATALOG, counts):
        for k in range(n):
            sub_en, sub_ar, lo, hi, qmax = subs[int(rng.integers(0, len(subs)))]
            brand = brands[int(rng.integers(0, len(brands)))]
            model = _model_code(rng)
            price = float(np.exp(rng.uniform(np.log(lo), np.log(hi))))
            price = max(9.0, round(price / 10) * 10 - 1)  # 1999-style price points
            cost = round(price * float(rng.uniform(0.55, 0.80)), 2)
            launched = (start + timedelta(days=int(rng.integers(0, max(1, (end - start).days))))
                        if rng.random() < 0.05 else date(2018, 1, 1) + timedelta(days=int(rng.integers(0, 1800))))
            rows.append(dict(
                sku=f"{prefix}-{k + 1:06d}",
                product_name_en=f"{brand} {model} {sub_en}",
                product_name_ar=f"{sub_ar} {brand} {model}",
                category=cat_en, subcategory=sub_en, brand=brand,
                unit_cost_aed=cost, list_price_aed=price, is_active=True, launched_on=launched,
                cat_weight=cat_w, return_rate=ret * float(rng.uniform(0.7, 1.3)), qty_max=qmax,
            ))
    df = pd.DataFrame(rows)
    # Popularity: Zipf over a random ranking, tilted toward cheaper items and busy categories
    rank = rng.permutation(len(df)) + 1
    df["popularity"] = (1.0 / rank ** 0.9) * df["cat_weight"] / df["list_price_aed"] ** 0.35
    df["popularity"] /= df["popularity"].sum()
    test = dict(sku=C.TEST_SKU, product_name_en="TEST ITEM - DO NOT SELL", product_name_ar="صنف تجريبي",
                category="Internal", subcategory="Internal", brand="Najm", unit_cost_aed=0.0,
                list_price_aed=1.0, is_active=True, launched_on=date(2015, 1, 1), cat_weight=0.0,
                return_rate=0.0, qty_max=1, popularity=0.0)
    df = pd.concat([df, pd.DataFrame([test])], ignore_index=True)
    df.index.name = "product_idx"
    return df


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------
ACQ_WEIGHTS_INITIAL = {"organic": 0.45, "google_ads": 0.17, "meta": 0.13, "tiktok": 0.07,
                       "snapchat": 0.06, "email": 0.04, "affiliate": 0.08}
EMAIL_DOMAINS = np.array(["gmail.com", "hotmail.com", "outlook.com", "yahoo.com", "icloud.com"])
PHONE_PREFIX = {"AE": "+9715", "SA": "+9665", "QA": "+9745"}


def make_customers(rng: np.random.Generator, names: NamePool, stores: pd.DataFrame,
                   countries: np.ndarray, channels: np.ndarray, created_at: np.ndarray,
                   next_pos_id: int, next_cust_idx: int) -> tuple[pd.DataFrame, int, int]:
    """Create customers. ~75% join the loyalty programme (POS customer master);
    40% of those also have an online account; the rest are online-only."""
    n = len(countries)
    if n == 0:
        return pd.DataFrame(), next_pos_id, next_cust_idx
    nm = names.sample(rng, n)
    has_loyalty = rng.random(n) < 0.75
    has_online = np.where(has_loyalty, rng.random(n) < 0.40, True)
    pos_ids = np.full(n, pd.NA, dtype=object)
    pos_ids[has_loyalty] = np.arange(next_pos_id, next_pos_id + has_loyalty.sum())
    loyalty = np.array([f"NJ{c}{int(i):08d}" if i is not pd.NA else None for c, i in zip(countries, pos_ids)],
                       dtype=object)
    online_ids = np.array([f"c_{rng.bytes(6).hex()}" if o else None for o in has_online], dtype=object)
    suffix = rng.integers(1, 9999, n)
    email = [f"{f.lower()}.{l.lower().replace(' ', '')}{s}@{d}" for f, l, s, d in
             zip(nm.first_name, nm.last_name, suffix, EMAIL_DOMAINS[rng.integers(0, 5, n)])]
    phone = [f"{PHONE_PREFIX[c]}{int(x):08d}" for c, x in zip(countries, rng.integers(0, 10**8, n))]
    home = []
    physical = stores[~stores.is_online]
    by_country = {c: physical[physical.country_code == c].store_id.to_numpy() for c in C.COUNTRIES}
    for c in countries:
        ids = by_country[c]
        home.append(int(ids[rng.integers(0, len(ids))]))
    tiers = rng.choice(C.LOYALTY_TIERS, n, p=[0.60, 0.25, 0.12, 0.03])
    df = pd.DataFrame({
        "cust_idx": np.arange(next_cust_idx, next_cust_idx + n),
        "pos_customer_id": pos_ids,
        "loyalty_number": loyalty,
        "online_customer_id": online_ids,
        **{k: nm[k].to_numpy() for k in nm.columns},
        "email": email, "phone": phone, "country_code": countries,
        "home_store_id": home, "loyalty_tier": tiers, "acquisition_channel": channels,
        "created_at": pd.to_datetime(created_at, utc=True),
        "activity": rng.lognormal(0.0, 1.0, n),
    })
    return df, next_pos_id + int(has_loyalty.sum()), next_cust_idx + n


def initial_customers(rng, names, stores, n, start: date):
    countries = rng.choice(list(C.COUNTRIES), n, p=[0.45, 0.45, 0.10])
    channels = rng.choice(list(ACQ_WEIGHTS_INITIAL), n, p=list(ACQ_WEIGHTS_INITIAL.values()))
    t0 = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
    secs = rng.integers(60 * 60 * 24, 4 * 365 * 24 * 3600, n)
    created = np.array([t0 - timedelta(seconds=int(s)) for s in secs])
    # Existing customers can only call a store home if it already traded on day 1
    # (pos.customers.home_store_id is a foreign key to pos.stores).
    open_at_start = stores[stores.opened_on <= start]
    return make_customers(rng, names, open_at_start, countries, channels, created, 1, 0)


# ---------------------------------------------------------------------------
# Promotions & campaigns
# ---------------------------------------------------------------------------
def build_promotions(rng: np.random.Generator, start: date, end: date) -> pd.DataFrame:
    rows = [dict(promotion_code="LOYALTY5", promotion_name="Loyalty member 5%", discount_type="percent",
                 discount_value=5.0, starts_on=date(2018, 1, 1), ends_on=date(2030, 12, 31), country_code=None),
            dict(promotion_code="GIFT50", promotion_name="50 off voucher", discount_type="amount",
                 discount_value=50.0, starts_on=date(2018, 1, 1), ends_on=date(2030, 12, 31), country_code=None)]
    seen = set()
    for cc in C.COUNTRIES:
        for name, s, e in seasonal_events(start, end, cc):
            code = "".join(ch for ch in name.upper() if ch.isalnum())[:22]
            is_national = "National" in name or "Founding" in name
            if is_national:
                code = f"{code[:18]}{cc}"
            if code in seen:
                continue
            seen.add(code)
            pct = 25.0 if "White" in name else float(rng.choice([10.0, 15.0, 20.0]))
            rows.append(dict(promotion_code=code, promotion_name=f"{name} sale", discount_type="percent",
                             discount_value=pct, starts_on=s, ends_on=e,
                             country_code=cc if is_national or name.startswith("DSF") else None))
    df = pd.DataFrame(rows)
    df.insert(0, "promotion_id", np.arange(1, len(df) + 1))
    return df


CHANNEL_ABBR = {"google_ads": "GA", "meta": "MT", "tiktok": "TT", "snapchat": "SC", "email": "EM", "affiliate": "AF"}
CHANNEL_LABEL = {"google_ads": "Google Ads", "meta": "Meta", "tiktok": "TikTok", "snapchat": "Snapchat",
                 "email": "Email", "affiliate": "Affiliates"}


def build_campaigns(start: date, end: date) -> pd.DataFrame:
    rows = []
    seq = 1
    for cc in C.COUNTRIES:
        for ch in C.MARKETING_CHANNELS:
            rows.append(dict(campaign_id=f"{CHANNEL_ABBR[ch]}-{cc}-{seq:04d}",
                             campaign_name=f"{cc} | Always-on | {CHANNEL_LABEL[ch]}",
                             marketing_channel=ch, country_code=cc, starts_on=date(2018, 1, 1),
                             ends_on=date(2030, 12, 31), is_always_on=True))
            seq += 1
        for name, s, e in seasonal_events(start, end, cc):
            for ch in C.SEASONAL_CAMPAIGN_CHANNELS:
                rows.append(dict(campaign_id=f"{CHANNEL_ABBR[ch]}-{cc}-{seq:04d}",
                                 campaign_name=f"{cc} | {name} | {CHANNEL_LABEL[ch]}",
                                 marketing_channel=ch, country_code=cc, starts_on=s, ends_on=e,
                                 is_always_on=False))
                seq += 1
    return pd.DataFrame(rows)
