# Power BI setup

Connect to `mart.*` only. Never to `core` or `staging` - that is the whole
point of having a mart layer. It lets the model underneath change without
breaking the report.

---

## 1. Connect

**Home → Get Data → More → Database → PostgreSQL database**

| Field | Value |
|---|---|
| Server | `aws-0-eu-central-1.pooler.supabase.com:5432` |
| Database | `postgres` |
| Data Connectivity mode | **Import** |

Note the `:5432` on the server - Power BI wants host and port in one box.

Credentials tab: **Database**, then your `PGUSER` (with the `.projectref`
suffix) and password.

Encryption: **untick "Use encrypted connection"**. Leaving it ticked fails with
a certificate error - see *Known issue* at the bottom of this file for why, and
for the proper fix to apply before any real data is loaded.

### Import, not DirectQuery

A year of this data is about 200k rows and compresses to a few MB in the
VertiPaq engine. Import gives instant slicing and full DAX. DirectQuery would
send a query to Supabase on every click, burn the free tier, and disable half
of DAX. Only revisit this if the data ever outgrows about 10 million rows.

## 2. Load these tables

```
mart.dim_date        mart.kpi_daily
mart.dim_item        mart.kpi_zone
mart.dim_zone        mart.kpi_item
mart.dim_channel     mart.kpi_channel_daily
mart.dim_driver      mart.dim_cost_assumption
mart.dim_customer
mart.fct_order
mart.fct_order_item
```

## 3. Relationships

Power BI will guess some of these. Check them in **Model view** and fix any
that are wrong or missing:

| From | To | Cardinality |
|---|---|---|
| `'mart fct_order'[date_key]` | `'mart dim_date'[date_key]` | many-to-one |
| `'mart fct_order'[channel_key]` | `'mart dim_channel'[channel_key]` | many-to-one |
| `'mart fct_order'[zone_key]` | `'mart dim_zone'[zone_key]` | many-to-one |
| `'mart fct_order'[customer_key]` | `'mart dim_customer'[customer_key]` | many-to-one |
| `'mart fct_order'[driver_key]` | `'mart dim_driver'[driver_key]` | many-to-one |
| `'mart fct_order_item'[order_key]` | `'mart fct_order'[order_key]` | many-to-one |
| `'mart fct_order_item'[item_key]` | `'mart dim_item'[item_key]` | many-to-one |
| `'mart kpi_daily'[date_key]` | `'mart dim_date'[date_key]` | one-to-one |
| `'mart kpi_channel_daily'[date_key]` | `'mart dim_date'[date_key]` | many-to-one |

All should be **single** cross-filter direction. Leave bidirectional alone
unless you have a specific reason - it causes ambiguity errors later.

## 4. Two things people always forget

### Mark the date table

Select `dim_date` → **Table tools → Mark as date table** → date column
`full_date`.

Without this, every time-intelligence measure below silently returns wrong
numbers rather than erroring.

### Fix text sorting

Power BI sorts text alphabetically, so months run April, August, December and
weekdays run Friday, Monday, Saturday. Both are nonsense on an axis. The sort
columns are already in the mart:

- select `'mart dim_date'[month_name]` → **Sort by column** → `month_sort`
- select `'mart dim_date'[day_name]` → **Sort by column** → `weekday_sort`

German equivalents (`month_name_de`, `day_name_de`) are in the same table if
you ever hand the report to a German colleague. Sort those the same way.

## 5. Measures

> **Table naming:** importing from a Postgres schema makes Power BI name the
> tables `mart kpi_daily` - with a SPACE, not a dot. Names containing a space
> must be single-quoted in DAX, which is why every reference below reads
> `'mart kpi_daily'[...]`.

Keep DAX thin. Everything heavy is already aggregated in `kpi_daily`; DAX is
only for what has to respond to a slicer.

Create a blank table called `_Measures` (**Enter data**, delete the column)
and put these in it, so they sit at the top of the field list.

```dax
-- ---------- revenue ----------
Revenue = SUM('mart kpi_daily'[gross_revenue])

Net Revenue = SUM('mart kpi_daily'[net_revenue])

Orders = SUM('mart kpi_daily'[orders])

Avg Order Value = DIVIDE([Revenue], [Orders])

-- ---------- profit: the two numbers that matter ----------
-- Contribution margin stops at costs that exist because today happened.
Contribution Margin = SUM('mart kpi_daily'[contribution_margin])

-- Operating profit also carries rent, the franchise licence and everything
-- else owed whether anyone orders a pizza or not. This is the real one.
Operating Profit = SUM('mart kpi_daily'[operating_profit])

Operating Margin % = DIVIDE([Operating Profit], [Net Revenue])

Food Cost % = DIVIDE(SUM('mart kpi_daily'[food_cost]), [Revenue])

Labour Cost % = DIVIDE(SUM('mart kpi_daily'[labour_cost]), [Revenue])

Fixed Costs = SUM('mart kpi_daily'[fixed_cost])

Franchise Fees = SUM('mart kpi_daily'[royalty_cost])

-- ---------- time intelligence (needs the marked date table) ----------
Revenue Last Week =
CALCULATE([Revenue], DATEADD('mart dim_date'[full_date], -7, DAY))

Revenue WoW % =
DIVIDE([Revenue] - [Revenue Last Week], [Revenue Last Week])

Revenue 7d Avg =
AVERAGEX(
    DATESINPERIOD('mart dim_date'[full_date], MAX('mart dim_date'[full_date]), -7, DAY),
    [Revenue]
)

Revenue YTD = TOTALYTD([Revenue], 'mart dim_date'[full_date])

-- ---------- delivery ----------
-- Averaged from the order fact, not from daily averages: a Saturday with
-- 150 deliveries must not weigh the same as a Tuesday with 80. actual_min
-- is blank on pickup orders and AVERAGE ignores blanks, so this is
-- delivery-only without needing a filter.
Avg Delivery Minutes = AVERAGE('mart fct_order'[actual_min])

Late Rate =
DIVIDE(
    CALCULATE(COUNTROWS('mart fct_order'), 'mart fct_order'[is_late] = TRUE()),
    CALCULATE(COUNTROWS('mart fct_order'), 'mart fct_order'[is_delivery] = TRUE())
)

-- ---------- the aggregator question ----------
Commission Paid = SUM('mart kpi_daily'[commission_total])

Aggregator Share % =
DIVIDE(
    CALCULATE([Revenue], 'mart dim_channel'[is_aggregator] = TRUE()),
    [Revenue]
)

Margin per Order =
DIVIDE(SUM('mart fct_order'[gross_margin]), COUNTROWS('mart fct_order'))
```

## 6. Suggested pages

Five pages. Resist adding more - a franchise owner will look at two.

**1. Overview** - the daily answer
KPI cards: Revenue, Orders, Avg Order Value, **Operating Profit**,
**Operating Margin %**. Line chart of Revenue with `Revenue 7d Avg` overlaid.
Bar chart by `day_name`. Date slicer.

Lead with Operating Profit, not Revenue. Revenue answers "were we busy".
Only profit answers "was it worth opening".

**2. Profit breakdown**
Waterfall visual: Net Revenue → food → packaging → waste → labour → payment
fees → fixed → franchise → Operating Profit. This single visual is the most
useful thing in the report - it shows exactly where the money goes.

Add `dim_cost_assumption` as a table so the owner can see and argue with the
assumptions the profit figure rests on.

**3. Delivery & zones**
Bar chart on `'mart kpi_zone'[zone_label]`. Put `margin_per_drive_minute` next to
`late_rate_pct` - that pairing is what shows Golm earning the least per
driver-minute *and* arriving late most often. Scatter: `distance_km` vs
`late_rate_pct`.

**4. Channels**
`kpi_channel_daily` stacked area over time - shows the drift from phone to app
and Lieferando. Bar chart of **Margin per Order** by channel. A card for
Commission Paid with the yearly total spelled out.

**5. Menu**
`kpi_item` scatter: `units_sold` on x, `margin_pct` on y, bubble size
`revenue`. That is a menu-engineering quadrant - stars top-right, dead weight
bottom-left.

### Free AI visuals worth adding

On page 1, drop in a **Key Influencers** visual: Analyse `'mart kpi_daily'[orders]`,
Explain by `is_weekend`, `is_rainy`, `is_public_holiday`, `day_name`,
`temp_mean_c`. It runs a decision tree and costs nothing.

Also add **Anomaly detection** to the Revenue line chart (Analytics pane →
Find anomalies). It should flag the February oven outage and the May discount
window on its own.

## 7. Scheduled refresh

Publish → **File → Publish → My workspace**.

PostgreSQL needs the **on-premises data gateway (personal mode)** even
against cloud Postgres, because it is not one of the sources Power BI Service
can reach natively.

1. Download "On-premises data gateway (personal mode)" from Microsoft.
2. Install on a PC that stays on - the back-office machine, not a laptop
   someone takes home.
3. Sign in with the same account as Power BI.
4. In Power BI Service: dataset → **Settings → Data source credentials** →
   map the source to the gateway.
5. **Scheduled refresh** → daily → 06:00 Europe/Berlin. That is after the
   nightly ETL and before anyone looks at it.

### If you cannot keep a PC on

Have the ETL also write the marts as Parquet to a OneDrive or SharePoint
folder and point Power BI there instead. The Service reads those natively with
no gateway. `build_marts.py --local` already writes exactly that structure to
`data/processed/mart/`.

## Known issue: Power BI certificate error

Connecting with encryption on fails with:

    The remote certificate is invalid according to the validation procedure.

Supabase signs the pooler certificate with its own private CA:

    subject  CN=*.pooler.supabase.com
    issuer   CN=Supabase Intermediate 2021 CA

Windows does not trust that CA, so Power BI's chain validation fails. The
connection is not broken - psycopg2 with `sslmode=require` negotiates TLS 1.3
fine. Only `verify-full` fails, and Power BI effectively does verify-full.

**Current workaround:** untick "Use encrypted connection" in the Power BI
credentials dialog.

**This leaves the Power BI to Supabase traffic unencrypted.** Acceptable while
the data is synthetic. It is NOT acceptable once real order or customer data is
loaded.

**Proper fix, before real data:**

1. Supabase dashboard -> Project Settings -> Database -> SSL Configuration ->
   Download certificate (`prod-ca-2021.crt`).
2. Double-click the file -> Install Certificate -> Local Machine ->
   Place all certificates in the following store ->
   **Trusted Root Certification Authorities**.
3. Restart Power BI Desktop and reconnect with encryption ticked.

The Python side is unaffected either way - it uses `sslmode=require` and is
already encrypted.

---

## 8. The ML tables

Written by `python src/run_ml.py`. To pull them into an existing report:
**Home → Transform data → New Source → PostgreSQL**, same connection, tick the
`mart.*` tables below. After that, plain **Refresh** keeps them current.

| Table | Rows | What it answers |
|---|---|---|
| `forecast_daily` | 14 | How many orders to expect, per day, for the next fortnight - using the real Open-Meteo weather forecast |
| `customer_rfm` | ~2,000 | Which customers are Champions, Loyal, At risk, Lost |
| `customer_churn` | ~2,000 | Probability each customer stops ordering, plus a Low/Medium/High band |
| `delivery_promise` | 8 | The promise time each PLZ should actually carry |
| `delivery_factors` | 9 | What drives delivery time, ranked by SHAP |
| `basket_rules` | 200 | What gets ordered together, ranked by lift |
| `anomaly_daily` | ~33 | Days that were genuinely abnormal, and on which metric |

### Relationships to add

| From | To |
|---|---|
| `customer_rfm[customer_key]` | `dim_customer[customer_key]` |
| `customer_churn[customer_key]` | `dim_customer[customer_key]` |
| `delivery_promise[zone_key]` | `dim_zone[zone_key]` |

Do NOT relate `forecast_daily` or `anomaly_daily` to `dim_date`.
`forecast_daily` covers FUTURE dates that do not exist in `dim_date`, so the
join would silently drop every row. Use its own `full_date` column on the axis.

### Page 5 - Forecast

Line chart: `kpi_daily[full_date]` vs `Revenue` for history, with
`forecast_daily[full_date]` vs `orders_forecast` continuing it. Add
`orders_lower` / `orders_upper` as a shaded band - the uncertainty is the
point. A forecast presented without its range invites false confidence.

Table beside it: date, day, orders_forecast, precipitation_mm. Seeing the rain
column next to the number is what makes the forecast trustworthy to a manager
rather than a black box.

### Page 6 - Customers

`customer_rfm[segment]` bar chart by count and by `monetary`. The gap between
those two bars IS the insight: Champions are a quarter of customers and half
the revenue.

Table of `customer_churn` filtered to `risk_band = "High"`, sorted by
`monetary` descending. That is the win-back call list, most valuable first.

### Page 7 - Delivery promise

Table from `delivery_promise`: plz, district_name, distance_km,
current_promise_min, recommended_promise_min, current_late_pct.

This is the page that changes a decision. Waldstadt could promise 35 minutes
and does not. Golm is promised 45 and misses it 63% of the time.
