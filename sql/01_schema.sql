-- =====================================================================
-- Pizza Delivery Analytics - Warehouse
-- Layers:  staging (raw input)  ->  core (star schema)  ->  mart (Power BI)
-- =====================================================================

CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS mart;

-- ---------------------------------------------------------------------
-- STAGING : what the Streamlit form writes, exactly as typed
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS staging.daily_entry CASCADE;
CREATE TABLE staging.daily_entry (
    entry_id        BIGSERIAL PRIMARY KEY,
    business_date   DATE        NOT NULL UNIQUE,
    total_orders    INTEGER     NOT NULL CHECK (total_orders >= 0),
    gross_revenue   NUMERIC(10,2) NOT NULL CHECK (gross_revenue >= 0),
    delivery_orders INTEGER     NOT NULL DEFAULT 0,
    pickup_orders   INTEGER     NOT NULL DEFAULT 0,
    cancelled       INTEGER     NOT NULL DEFAULT 0,
    waste_eur       NUMERIC(10,2) NOT NULL DEFAULT 0,
    staff_hours     NUMERIC(6,2)  NOT NULL DEFAULT 0,
    driver_hours    NUMERIC(6,2)  NOT NULL DEFAULT 0,
    promo_active    BOOLEAN     NOT NULL DEFAULT FALSE,
    promo_note      TEXT,
    -- Distinguishes a genuine Ruhetag from an empty form submitted by mistake.
    -- Without this, zero orders is ambiguous and an accidental save would
    -- silently overwrite a real trading day with zeros.
    is_closed       BOOLEAN     NOT NULL DEFAULT FALSE,
    complaints      INTEGER     NOT NULL DEFAULT 0,
    notes           TEXT,
    entered_by      TEXT,
    entered_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------
-- CORE : dimensions
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS core.dim_date CASCADE;
CREATE TABLE core.dim_date (
    date_key          INTEGER PRIMARY KEY,          -- yyyymmdd
    full_date         DATE    NOT NULL UNIQUE,
    year              SMALLINT NOT NULL,
    quarter           SMALLINT NOT NULL,
    month             SMALLINT NOT NULL,
    month_name        TEXT    NOT NULL,
    month_name_de     TEXT    NOT NULL,
    iso_week          SMALLINT NOT NULL,
    day_of_month      SMALLINT NOT NULL,
    day_of_week       SMALLINT NOT NULL,            -- 1=Mon .. 7=Sun
    day_name          TEXT    NOT NULL,
    day_name_de       TEXT    NOT NULL,
    is_weekend        BOOLEAN NOT NULL,
    is_public_holiday BOOLEAN NOT NULL DEFAULT FALSE,
    holiday_name      TEXT,
    is_school_holiday BOOLEAN NOT NULL DEFAULT FALSE,
    -- real Potsdam weather, joined on the date grain
    temp_mean_c       NUMERIC(5,2),
    temp_max_c        NUMERIC(5,2),
    precipitation_mm  NUMERIC(6,2),
    wind_max_kmh      NUMERIC(6,2),
    is_rainy          BOOLEAN,
    is_cold           BOOLEAN
);

DROP TABLE IF EXISTS core.dim_channel CASCADE;
CREATE TABLE core.dim_channel (
    channel_key     SMALLINT PRIMARY KEY,
    channel_name    TEXT NOT NULL UNIQUE,           -- Telefon, Website, App, Lieferando, Abholung
    is_aggregator   BOOLEAN NOT NULL DEFAULT FALSE,
    commission_rate NUMERIC(5,4) NOT NULL DEFAULT 0 -- e.g. 0.1300 for Lieferando
);

DROP TABLE IF EXISTS core.dim_zone CASCADE;
CREATE TABLE core.dim_zone (
    zone_key       SMALLINT PRIMARY KEY,
    plz            TEXT NOT NULL UNIQUE,            -- Potsdam postal codes
    district_name  TEXT NOT NULL,
    distance_km    NUMERIC(5,2) NOT NULL,
    base_drive_min NUMERIC(5,2) NOT NULL,
    delivery_fee   NUMERIC(5,2) NOT NULL DEFAULT 0
);

DROP TABLE IF EXISTS core.dim_item CASCADE;
CREATE TABLE core.dim_item (
    item_key       SMALLINT PRIMARY KEY,
    item_name      TEXT NOT NULL,
    category       TEXT NOT NULL,                   -- Pizza, Pasta, Salat, Snacks, Dessert, Getraenke
    size_name      TEXT,                            -- Klein / Normal / Familie
    unit_price     NUMERIC(6,2) NOT NULL,
    unit_cost      NUMERIC(6,2) NOT NULL,
    is_vegetarian  BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (item_name, size_name)
);

DROP TABLE IF EXISTS core.dim_driver CASCADE;
CREATE TABLE core.dim_driver (
    driver_key   SMALLINT PRIMARY KEY,
    driver_name  TEXT NOT NULL,
    hired_on     DATE,
    vehicle      TEXT                               -- Roller / Auto / Fahrrad
);

DROP TABLE IF EXISTS core.dim_customer CASCADE;
CREATE TABLE core.dim_customer (
    customer_key     INTEGER PRIMARY KEY,
    customer_code    TEXT NOT NULL UNIQUE,          -- pseudonymous, no PII
    zone_key         SMALLINT REFERENCES core.dim_zone(zone_key),
    first_order_date DATE,
    signup_channel   TEXT
);

-- ---------------------------------------------------------------------
-- CORE : facts
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS core.fct_order CASCADE;
CREATE TABLE core.fct_order (
    order_key         BIGINT PRIMARY KEY,
    date_key          INTEGER  NOT NULL REFERENCES core.dim_date(date_key),
    order_ts          TIMESTAMP NOT NULL,
    daypart           TEXT     NOT NULL,            -- Mittag, Nachmittag, Abend, Spaet
    customer_key      INTEGER  REFERENCES core.dim_customer(customer_key),
    channel_key       SMALLINT NOT NULL REFERENCES core.dim_channel(channel_key),
    zone_key          SMALLINT REFERENCES core.dim_zone(zone_key),
    driver_key        SMALLINT REFERENCES core.dim_driver(driver_key),
    is_delivery       BOOLEAN  NOT NULL,
    item_qty          SMALLINT NOT NULL,
    gross_amount      NUMERIC(8,2) NOT NULL,        -- items before discount
    discount_amount   NUMERIC(8,2) NOT NULL DEFAULT 0,
    delivery_fee      NUMERIC(6,2) NOT NULL DEFAULT 0,
    commission_amount NUMERIC(8,2) NOT NULL DEFAULT 0,
    net_revenue       NUMERIC(8,2) NOT NULL,        -- gross - discount + fee - commission
    food_cost         NUMERIC(8,2) NOT NULL,
    promised_min      SMALLINT,
    actual_min        SMALLINT,
    is_late           BOOLEAN,
    is_cancelled      BOOLEAN NOT NULL DEFAULT FALSE,
    promo_code        TEXT
);
CREATE INDEX idx_fct_order_date    ON core.fct_order(date_key);
CREATE INDEX idx_fct_order_cust    ON core.fct_order(customer_key);
CREATE INDEX idx_fct_order_channel ON core.fct_order(channel_key);
CREATE INDEX idx_fct_order_zone    ON core.fct_order(zone_key);

DROP TABLE IF EXISTS core.fct_order_item CASCADE;
CREATE TABLE core.fct_order_item (
    order_item_key BIGINT PRIMARY KEY,
    order_key      BIGINT   NOT NULL REFERENCES core.fct_order(order_key) ON DELETE CASCADE,
    date_key       INTEGER  NOT NULL REFERENCES core.dim_date(date_key),
    item_key       SMALLINT NOT NULL REFERENCES core.dim_item(item_key),
    quantity       SMALLINT NOT NULL,
    unit_price     NUMERIC(6,2) NOT NULL,
    line_revenue   NUMERIC(8,2) NOT NULL,
    line_cost      NUMERIC(8,2) NOT NULL
);
CREATE INDEX idx_fct_item_order ON core.fct_order_item(order_key);
CREATE INDEX idx_fct_item_item  ON core.fct_order_item(item_key);
CREATE INDEX idx_fct_item_date  ON core.fct_order_item(date_key);

-- One row per trading day: everything it costs to open the doors.
-- Split into the four buckets an owner can actually act on differently:
--   labour     - schedulable
--   packaging  - scales with volume, negotiable with suppliers
--   fixed      - only changes by renegotiating a contract
--   royalty    - contractual, cannot be changed at all
DROP TABLE IF EXISTS core.fct_shift CASCADE;
CREATE TABLE core.fct_shift (
    shift_key      BIGINT PRIMARY KEY,
    date_key       INTEGER NOT NULL REFERENCES core.dim_date(date_key),
    kitchen_hours  NUMERIC(6,2) NOT NULL,
    driver_hours   NUMERIC(6,2) NOT NULL,
    labour_cost    NUMERIC(8,2) NOT NULL,
    waste_eur      NUMERIC(8,2) NOT NULL DEFAULT 0,
    packaging_cost NUMERIC(8,2) NOT NULL DEFAULT 0,
    payment_fees   NUMERIC(8,2) NOT NULL DEFAULT 0,
    fixed_cost     NUMERIC(8,2) NOT NULL DEFAULT 0,  -- daily share of monthly fixed
    royalty_cost   NUMERIC(8,2) NOT NULL DEFAULT 0   -- franchise licence + ad levy
);

-- The cost assumptions, exposed as data so the dashboard can show what the
-- profit figure is built on instead of hiding it in code.
DROP TABLE IF EXISTS core.dim_cost_assumption CASCADE;
CREATE TABLE core.dim_cost_assumption (
    cost_item      TEXT PRIMARY KEY,
    cost_type      TEXT NOT NULL,          -- fix / variabel
    monthly_eur    NUMERIC(10,2),
    pct_of_revenue NUMERIC(6,4),
    note           TEXT
);
