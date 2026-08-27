-- =====================================================================
-- Pizza Delivery Analytics - MART layer
--
-- This is the ONLY layer Power BI is allowed to touch. Everything here is
-- a materialised table, not a view, because Power BI Import mode reads the
-- whole thing on every refresh and views would re-run the aggregation each
-- time.
--
-- Rebuild is destructive and idempotent: run it as often as you like.
--
-- Written in the common subset of Postgres and DuckDB SQL so the exact same
-- file can be verified locally against Parquet before Supabase exists.
-- =====================================================================

CREATE SCHEMA IF NOT EXISTS mart;

-- ---------------------------------------------------------------------
-- Dimensions: pass-through, but renamed to what a business user expects
-- to see in the Power BI field list.
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS mart.dim_date;
CREATE TABLE mart.dim_date AS
SELECT
    date_key,
    full_date,
    year,
    quarter,
    month,
    month_name,
    month_name_de,
    iso_week,
    day_of_week,
    day_name,
    day_name_de,
    is_weekend,
    is_public_holiday,
    holiday_name,
    is_school_holiday,
    temp_mean_c,
    temp_max_c,
    precipitation_mm,
    is_rainy,
    is_cold,
    -- pre-built sort keys: Power BI sorts text alphabetically otherwise,
    -- which puts April before January and Friday before Monday
    year * 100 + month AS year_month_key,
    month             AS month_sort,
    day_of_week       AS weekday_sort
FROM core.dim_date;

DROP TABLE IF EXISTS mart.dim_item;
CREATE TABLE mart.dim_item AS
SELECT
    item_key,
    item_name,
    category,
    COALESCE(size_name, '-') AS size_name,
    CASE WHEN size_name IS NULL THEN item_name
         ELSE item_name || ' (' || size_name || ')' END AS item_full_name,
    unit_price,
    unit_cost,
    ROUND(unit_price - unit_cost, 2)                        AS unit_margin,
    ROUND((unit_price - unit_cost) * 100.0 / unit_price, 1) AS unit_margin_pct,
    is_vegetarian
FROM core.dim_item;

DROP TABLE IF EXISTS mart.dim_zone;
CREATE TABLE mart.dim_zone AS
SELECT
    zone_key,
    plz,
    district_name,
    plz || ' ' || district_name AS zone_label,
    distance_km,
    base_drive_min,
    delivery_fee
FROM core.dim_zone;

DROP TABLE IF EXISTS mart.dim_channel;
CREATE TABLE mart.dim_channel AS
SELECT
    channel_key,
    channel_name,
    is_aggregator,
    commission_rate,
    CASE WHEN is_aggregator THEN 'Aggregator' ELSE 'Direkt' END AS channel_group
FROM core.dim_channel;

DROP TABLE IF EXISTS mart.dim_driver;
CREATE TABLE mart.dim_driver AS
SELECT driver_key, driver_name, vehicle FROM core.dim_driver;

-- ---------------------------------------------------------------------
-- Order fact, slimmed for Power BI and with margin resolved per order.
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS mart.fct_order;
CREATE TABLE mart.fct_order AS
SELECT
    o.order_key,
    o.date_key,
    o.order_ts,
    o.daypart,
    o.customer_key,
    o.channel_key,
    o.zone_key,
    o.driver_key,
    o.is_delivery,
    o.is_cancelled,
    o.item_qty,
    o.gross_amount,
    o.discount_amount,
    o.delivery_fee,
    o.commission_amount,
    o.net_revenue,
    o.food_cost,
    -- gross margin BEFORE labour; labour only exists at day grain
    ROUND(o.net_revenue - o.food_cost, 2) AS gross_margin,
    o.promised_min,
    o.actual_min,
    o.is_late,
    o.promo_code,
    CASE WHEN o.discount_amount > 0 THEN TRUE ELSE FALSE END AS has_discount
FROM core.fct_order o;

DROP TABLE IF EXISTS mart.fct_order_item;
CREATE TABLE mart.fct_order_item AS
SELECT
    oi.order_item_key,
    oi.order_key,
    oi.date_key,
    oi.item_key,
    oi.quantity,
    oi.line_revenue,
    oi.line_cost,
    ROUND(oi.line_revenue - oi.line_cost, 2) AS line_margin
FROM core.fct_order_item oi;

-- ---------------------------------------------------------------------
-- kpi_daily - the backbone of the dashboard.
--
-- Carries the full cost stack so the report can answer "are we making
-- money", not just "how much did we sell". Revenue alone hides the fact
-- that a Lieferando order can be busy work at almost no profit.
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS mart.kpi_daily;
CREATE TABLE mart.kpi_daily AS
WITH o AS (
    SELECT
        date_key,
        COUNT(*)                                                  AS orders,
        SUM(CASE WHEN is_delivery  THEN 1 ELSE 0 END)             AS delivery_orders,
        SUM(CASE WHEN is_delivery  THEN 0 ELSE 1 END)             AS pickup_orders,
        SUM(CASE WHEN is_cancelled THEN 1 ELSE 0 END)             AS cancelled_orders,
        SUM(gross_amount)                                         AS gross_revenue,
        SUM(discount_amount)                                      AS discount_total,
        SUM(delivery_fee)                                         AS delivery_fee_total,
        SUM(commission_amount)                                    AS commission_total,
        SUM(net_revenue)                                          AS net_revenue,
        SUM(food_cost)                                            AS food_cost,
        SUM(item_qty)                                             AS items_sold,
        AVG(CASE WHEN is_delivery THEN actual_min END)            AS avg_delivery_min,
        SUM(CASE WHEN is_delivery AND is_late THEN 1 ELSE 0 END) * 1.0
            / NULLIF(SUM(CASE WHEN is_delivery THEN 1 ELSE 0 END), 0) AS late_rate
    FROM core.fct_order
    GROUP BY date_key
)
SELECT
    d.date_key,
    d.full_date,
    d.year,
    d.month,
    d.month_name,
    d.month_name_de,
    d.iso_week,
    d.day_of_week,
    d.day_name,
    d.day_name_de,
    d.is_weekend,
    d.is_public_holiday,
    d.is_school_holiday,
    d.temp_mean_c,
    d.precipitation_mm,
    d.is_rainy,

    o.orders,
    o.delivery_orders,
    o.pickup_orders,
    o.cancelled_orders,
    o.items_sold,

    ROUND(o.gross_revenue, 2)      AS gross_revenue,
    ROUND(o.discount_total, 2)     AS discount_total,
    ROUND(o.delivery_fee_total, 2) AS delivery_fee_total,
    ROUND(o.commission_total, 2)   AS commission_total,
    ROUND(o.net_revenue, 2)        AS net_revenue,
    ROUND(o.food_cost, 2)          AS food_cost,
    COALESCE(s.labour_cost, 0)     AS labour_cost,
    COALESCE(s.waste_eur, 0)       AS waste_eur,
    COALESCE(s.packaging_cost, 0)  AS packaging_cost,
    COALESCE(s.payment_fees, 0)    AS payment_fees,
    COALESCE(s.fixed_cost, 0)      AS fixed_cost,
    COALESCE(s.royalty_cost, 0)    AS royalty_cost,
    s.kitchen_hours,
    s.driver_hours,

    -- Two different questions, two different numbers.
    --
    -- contribution_margin answers "did today pay for itself" - it stops at
    -- costs that only exist because the branch opened today.
    --
    -- operating_profit answers "is this branch a business" - it also carries
    -- rent, the franchise licence and everything else that is owed whether
    -- anyone orders a pizza or not. This is the one that matters, and the
    -- one people forget to build.
    ROUND(o.net_revenue - o.food_cost
          - COALESCE(s.labour_cost, 0) - COALESCE(s.waste_eur, 0)
          - COALESCE(s.packaging_cost, 0) - COALESCE(s.payment_fees, 0), 2)
        AS contribution_margin,
    ROUND((o.net_revenue - o.food_cost
           - COALESCE(s.labour_cost, 0) - COALESCE(s.waste_eur, 0)
           - COALESCE(s.packaging_cost, 0) - COALESCE(s.payment_fees, 0))
          * 100.0 / NULLIF(o.net_revenue, 0), 1)
        AS contribution_margin_pct,

    ROUND(o.net_revenue - o.food_cost
          - COALESCE(s.labour_cost, 0) - COALESCE(s.waste_eur, 0)
          - COALESCE(s.packaging_cost, 0) - COALESCE(s.payment_fees, 0)
          - COALESCE(s.fixed_cost, 0) - COALESCE(s.royalty_cost, 0), 2)
        AS operating_profit,
    ROUND((o.net_revenue - o.food_cost
           - COALESCE(s.labour_cost, 0) - COALESCE(s.waste_eur, 0)
           - COALESCE(s.packaging_cost, 0) - COALESCE(s.payment_fees, 0)
           - COALESCE(s.fixed_cost, 0) - COALESCE(s.royalty_cost, 0))
          * 100.0 / NULLIF(o.net_revenue, 0), 1)
        AS operating_margin_pct,

    -- the revenue this day had to clear just to break even
    ROUND((COALESCE(s.fixed_cost, 0) + COALESCE(s.labour_cost, 0))
          * 100.0 / NULLIF(o.net_revenue, 0), 1)
        AS breakeven_load_pct,

    ROUND(o.gross_revenue / NULLIF(o.orders, 0), 2)            AS avg_order_value,
    ROUND(o.food_cost * 100.0 / NULLIF(o.gross_revenue, 0), 1) AS food_cost_pct,
    ROUND(COALESCE(s.labour_cost, 0) * 100.0
          / NULLIF(o.gross_revenue, 0), 1)                     AS labour_cost_pct,
    ROUND(o.delivery_orders * 100.0 / NULLIF(o.orders, 0), 1)  AS delivery_share_pct,
    ROUND(o.avg_delivery_min, 1)                               AS avg_delivery_min,
    ROUND(o.late_rate * 100.0, 1)                              AS late_rate_pct,
    ROUND(o.orders / NULLIF(s.kitchen_hours, 0), 2)            AS orders_per_kitchen_hour,
    ROUND(o.delivery_orders / NULLIF(s.driver_hours, 0), 2)    AS orders_per_driver_hour
FROM core.dim_date d
JOIN o                ON o.date_key = d.date_key
LEFT JOIN core.fct_shift s ON s.date_key = d.date_key;

-- ---------------------------------------------------------------------
-- kpi_zone - which parts of Potsdam are worth delivering to.
--
-- Waldstadt is the home zone and pays no delivery fee; Golm is 9.5km away.
-- Revenue per zone is misleading on its own - margin per driver-minute is
-- the number that decides whether a zone earns its place.
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS mart.kpi_zone;
CREATE TABLE mart.kpi_zone AS
SELECT
    z.zone_key,
    z.plz,
    z.district_name,
    z.plz || ' ' || z.district_name AS zone_label,
    z.distance_km,
    COUNT(*)                                       AS orders,
    ROUND(SUM(o.gross_amount), 2)                  AS gross_revenue,
    ROUND(SUM(o.net_revenue), 2)                   AS net_revenue,
    ROUND(SUM(o.net_revenue - o.food_cost), 2)     AS gross_margin,
    ROUND(AVG(o.gross_amount), 2)                  AS avg_order_value,
    ROUND(AVG(o.actual_min), 1)                    AS avg_delivery_min,
    ROUND(SUM(CASE WHEN o.is_late THEN 1 ELSE 0 END) * 100.0
          / NULLIF(COUNT(*), 0), 1)                AS late_rate_pct,
    -- margin earned per minute a driver spends on the road for this zone
    ROUND(SUM(o.net_revenue - o.food_cost)
          / NULLIF(SUM(o.actual_min), 0), 3)       AS margin_per_drive_minute
FROM core.fct_order o
JOIN core.dim_zone z ON z.zone_key = o.zone_key
WHERE o.is_delivery
GROUP BY z.zone_key, z.plz, z.district_name, z.distance_km;

-- ---------------------------------------------------------------------
-- kpi_item - menu engineering. Popularity and margin together decide
-- whether an item is a star, a workhorse, or dead weight.
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS mart.kpi_item;
CREATE TABLE mart.kpi_item AS
SELECT
    i.item_key,
    i.item_name,
    i.category,
    COALESCE(i.size_name, '-') AS size_name,
    i.unit_price,
    SUM(oi.quantity)                              AS units_sold,
    ROUND(SUM(oi.line_revenue), 2)                AS revenue,
    ROUND(SUM(oi.line_revenue - oi.line_cost), 2) AS margin,
    ROUND(SUM(oi.line_revenue - oi.line_cost) * 100.0
          / NULLIF(SUM(oi.line_revenue), 0), 1)   AS margin_pct,
    COUNT(DISTINCT oi.order_key)                  AS orders_containing
FROM core.fct_order_item oi
JOIN core.dim_item i ON i.item_key = oi.item_key
GROUP BY i.item_key, i.item_name, i.category, i.size_name, i.unit_price;

-- ---------------------------------------------------------------------
-- kpi_channel_daily - the Lieferando question.
--
-- Aggregator orders look like revenue and are partly commission. Splitting
-- the margin by channel is what makes that visible.
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS mart.kpi_channel_daily;
CREATE TABLE mart.kpi_channel_daily AS
SELECT
    o.date_key,
    d.full_date,
    c.channel_key,
    c.channel_name,
    c.is_aggregator,
    COUNT(*)                                   AS orders,
    ROUND(SUM(o.gross_amount), 2)              AS gross_revenue,
    ROUND(SUM(o.commission_amount), 2)         AS commission,
    ROUND(SUM(o.net_revenue), 2)               AS net_revenue,
    ROUND(SUM(o.net_revenue - o.food_cost), 2) AS gross_margin,
    ROUND(AVG(o.gross_amount), 2)              AS avg_order_value
FROM core.fct_order o
JOIN core.dim_channel c ON c.channel_key = o.channel_key
JOIN core.dim_date    d ON d.date_key    = o.date_key
GROUP BY o.date_key, d.full_date, c.channel_key, c.channel_name, c.is_aggregator;

-- ---------------------------------------------------------------------
-- dim_customer with behaviour attached. The RFM segment itself is written
-- later by the ML layer; this is the factual base it scores.
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS mart.dim_customer;
CREATE TABLE mart.dim_customer AS
SELECT
    c.customer_key,
    c.customer_code,
    c.zone_key,
    c.signup_channel,
    c.first_order_date,
    COUNT(o.order_key)                        AS total_orders,
    ROUND(SUM(o.gross_amount), 2)             AS total_spend,
    ROUND(AVG(o.gross_amount), 2)             AS avg_order_value,
    MAX(d.full_date)                          AS last_order_date
FROM core.dim_customer c
LEFT JOIN core.fct_order o ON o.customer_key = c.customer_key
LEFT JOIN core.dim_date  d ON d.date_key     = o.date_key
GROUP BY c.customer_key, c.customer_code, c.zone_key,
         c.signup_channel, c.first_order_date;

-- ---------------------------------------------------------------------
-- The cost assumptions behind operating_profit, exposed to the report so
-- the owner can see (and argue with) what the profit figure rests on.
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS mart.dim_cost_assumption;
CREATE TABLE mart.dim_cost_assumption AS
SELECT
    cost_item,
    cost_type,
    monthly_eur,
    pct_of_revenue,
    ROUND(COALESCE(monthly_eur, 0) * 12, 2) AS annual_eur,
    note
FROM core.dim_cost_assumption;

-- ---------------------------------------------------------------------
-- Connecting the daily form to the reporting.
--
-- The form writes staging.daily_entry. The history comes from order-level
-- data in core.fct_order. Different grains, different columns - the form
-- cannot know food cost or commission, only what is on the till receipt.
--
-- mart.daily_actuals unions them on the columns they SHARE, and stamps each
-- row with where it came from. History wins for dates that have both, since
-- order-level data is richer than a typed daily total.
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS mart.daily_entry;
CREATE TABLE mart.daily_entry AS
SELECT
    business_date,
    total_orders,
    gross_revenue,
    delivery_orders,
    pickup_orders,
    cancelled,
    waste_eur,
    staff_hours,
    driver_hours,
    promo_active,
    promo_note,
    is_closed,
    complaints,
    notes,
    entered_by
FROM staging.daily_entry;

DROP TABLE IF EXISTS mart.daily_actuals;
CREATE TABLE mart.daily_actuals AS
SELECT
    k.full_date                     AS business_date,
    k.orders                        AS total_orders,
    k.gross_revenue,
    k.delivery_orders,
    k.pickup_orders,
    k.waste_eur,
    k.kitchen_hours                 AS staff_hours,
    k.driver_hours,
    k.avg_order_value,
    k.operating_profit,
    FALSE                           AS is_closed,
    'history'                       AS source
FROM mart.kpi_daily k

UNION ALL

SELECT
    e.business_date,
    e.total_orders,
    e.gross_revenue,
    e.delivery_orders,
    e.pickup_orders,
    e.waste_eur,
    e.staff_hours,
    e.driver_hours,
    ROUND(e.gross_revenue / NULLIF(e.total_orders, 0), 2) AS avg_order_value,
    NULL                            AS operating_profit,
    e.is_closed,
    'form'                          AS source
FROM mart.daily_entry e
WHERE e.business_date NOT IN (SELECT full_date FROM mart.kpi_daily);
