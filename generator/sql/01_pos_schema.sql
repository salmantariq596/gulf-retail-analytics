-- Najm Retail POS backend (source system #1).
-- Modeled on a typical retail POS: store master, cashiers, loyalty customers,
-- sale headers/lines, payments, returns. Runs automatically on first start
-- of the Postgres container (docker-entrypoint-initdb.d).
--
-- Deliberate source-system realities (do NOT "fix" here — the warehouse handles them):
--   * Prices are VAT-inclusive, in the store's local currency.
--   * Till restarts re-send lines: same (sale_id, line_number), new sale_line_id.
--   * Returns may have no original_sale_id (no receipt).
--   * Training-mode cashiers (cashier_code LIKE 'TRN-%') create test sales.
--   * Timestamps are UTC (timestamptz); stores operate in UTC+3/UTC+4.

CREATE SCHEMA IF NOT EXISTS pos;
SET search_path TO pos;

CREATE TABLE stores (
    store_id        SERIAL PRIMARY KEY,
    store_code      VARCHAR(10)  NOT NULL UNIQUE,      -- e.g. AE-DXB-01, ONL-AE
    store_name_en   VARCHAR(100) NOT NULL,
    store_name_ar   VARCHAR(100) NOT NULL,
    country_code    CHAR(2)      NOT NULL,             -- AE, SA, QA
    city            VARCHAR(50)  NOT NULL,
    store_format    VARCHAR(20)  NOT NULL,             -- flagship, mall, express, online
    currency_code   CHAR(3)      NOT NULL,             -- AED, SAR, QAR
    timezone        VARCHAR(40)  NOT NULL,             -- Asia/Dubai, Asia/Riyadh, Asia/Qatar
    opened_on       DATE         NOT NULL,
    closed_on       DATE,
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE cashiers (
    cashier_id      SERIAL PRIMARY KEY,
    cashier_code    VARCHAR(20)  NOT NULL UNIQUE,      -- TRN-* = training mode
    store_id        INT          NOT NULL REFERENCES stores (store_id),
    full_name       VARCHAR(100) NOT NULL,
    hired_on        DATE         NOT NULL,
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- Loyalty programme = customer master (shared with online via loyalty_number)
CREATE TABLE customers (
    customer_id          SERIAL PRIMARY KEY,
    loyalty_number       VARCHAR(12)  NOT NULL UNIQUE,
    first_name           VARCHAR(60),
    last_name            VARCHAR(60),
    first_name_ar        VARCHAR(60),
    last_name_ar         VARCHAR(60),
    email                VARCHAR(120),
    phone                VARCHAR(20),
    country_code         CHAR(2)      NOT NULL,
    home_store_id        INT          REFERENCES stores (store_id),
    loyalty_tier         VARCHAR(10)  NOT NULL,          -- blue, silver, gold, platinum
    acquisition_channel  VARCHAR(20)  NOT NULL,          -- organic, google_ads, meta, tiktok, snapchat, email, affiliate
    created_at           TIMESTAMPTZ  NOT NULL,
    updated_at           TIMESTAMPTZ  NOT NULL
);

CREATE TABLE promotions (
    promotion_id     SERIAL PRIMARY KEY,
    promotion_code   VARCHAR(30)  NOT NULL UNIQUE,
    promotion_name   VARCHAR(100) NOT NULL,
    discount_type    VARCHAR(10)  NOT NULL,              -- percent, amount
    discount_value   NUMERIC(10,2) NOT NULL,
    starts_on        DATE         NOT NULL,
    ends_on          DATE         NOT NULL,
    updated_at       TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE sales (
    sale_id          BIGSERIAL PRIMARY KEY,
    receipt_number   VARCHAR(30)  NOT NULL,              -- printed on receipt, unique per store
    store_id         INT          NOT NULL REFERENCES stores (store_id),
    register_no      SMALLINT     NOT NULL,
    cashier_id       INT          NOT NULL REFERENCES cashiers (cashier_id),
    customer_id      INT          REFERENCES customers (customer_id),  -- NULL = anonymous walk-in
    sold_at          TIMESTAMPTZ  NOT NULL,
    currency_code    CHAR(3)      NOT NULL,
    total_incl_vat   NUMERIC(12,2) NOT NULL,
    status           VARCHAR(10)  NOT NULL DEFAULT 'completed',  -- completed, voided
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE sale_lines (
    sale_line_id     BIGSERIAL PRIMARY KEY,              -- new id on till re-send (duplicates!)
    sale_id          BIGINT       NOT NULL REFERENCES sales (sale_id),
    line_number      SMALLINT     NOT NULL,
    sku              VARCHAR(20)  NOT NULL,              -- joins to catalog CSV
    quantity         INT          NOT NULL,
    unit_price_incl_vat NUMERIC(12,2) NOT NULL,
    discount_incl_vat   NUMERIC(12,2) NOT NULL DEFAULT 0,
    promotion_id     INT          REFERENCES promotions (promotion_id),
    line_total_incl_vat NUMERIC(12,2) NOT NULL,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE payments (
    payment_id       BIGSERIAL PRIMARY KEY,
    sale_id          BIGINT       NOT NULL REFERENCES sales (sale_id),
    payment_method   VARCHAR(20)  NOT NULL,              -- cash, card, apple_pay, tabby, tamara, gift_card
    amount           NUMERIC(12,2) NOT NULL,
    currency_code    CHAR(3)      NOT NULL,
    paid_at          TIMESTAMPTZ  NOT NULL
);

CREATE TABLE returns (
    return_id        BIGSERIAL PRIMARY KEY,
    store_id         INT          NOT NULL REFERENCES stores (store_id),
    cashier_id       INT          NOT NULL REFERENCES cashiers (cashier_id),
    customer_id      INT          REFERENCES customers (customer_id),
    original_sale_id BIGINT       REFERENCES sales (sale_id),   -- NULL = no receipt / online purchase
    original_online_order_id VARCHAR(30),                       -- set when an online order is returned in store
    returned_at      TIMESTAMPTZ  NOT NULL,
    currency_code    CHAR(3)      NOT NULL,
    reason_code      VARCHAR(20)  NOT NULL,              -- defective, changed_mind, wrong_item, other
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE return_lines (
    return_line_id   BIGSERIAL PRIMARY KEY,
    return_id        BIGINT       NOT NULL REFERENCES returns (return_id),
    original_sale_line_id BIGINT  REFERENCES sale_lines (sale_line_id),
    sku              VARCHAR(20)  NOT NULL,
    quantity         INT          NOT NULL,
    refund_incl_vat  NUMERIC(12,2) NOT NULL,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- Indexes the ingestion layer relies on for incremental extracts
CREATE INDEX ix_sales_updated_at      ON sales (updated_at);
CREATE INDEX ix_sale_lines_created_at ON sale_lines (created_at);
CREATE INDEX ix_sale_lines_sale_id    ON sale_lines (sale_id);
CREATE INDEX ix_returns_updated_at    ON returns (updated_at);
CREATE INDEX ix_customers_updated_at  ON customers (updated_at);
CREATE INDEX ix_payments_sale_id      ON payments (sale_id);
