"""Pizza Delivery Analytics - analytics dashboard.

Run:  streamlit run src/dashboard.py

Everything the Power BI report shows, in one file, reading straight from
Supabase. No measures, no relationships, no gateway.

Two apps, two jobs:
  app.py        the 90-second nightly entry form (phone)
  dashboard.py  this - the analysis (desktop)
"""
from __future__ import annotations

import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

st.set_page_config(page_title="Pizza Delivery Analytics",
                   page_icon="🍕", layout="wide")


# ---------------------------------------------------------------- loading
@st.cache_data(ttl=600)
def get(table: str) -> pd.DataFrame:
    from ml_common import load
    return load(table)


@st.cache_data(ttl=600)
def backend() -> str:
    from ml_common import BACKEND
    return BACKEND


def eur(x: float, dp: int = 0) -> str:
    return f"€{x:,.{dp}f}"


st.title("🍕 Pizza Delivery Analytics")
st.caption(f"Analytics · data from {backend()}")

try:
    kpi = get("mart.kpi_daily")
except Exception as exc:                                      # noqa: BLE001
    st.error(f"Could not load data: {exc}")
    st.stop()

kpi["full_date"] = pd.to_datetime(kpi["full_date"])

# ----------------------------------------------------------------- filter
lo, hi = kpi.full_date.min().date(), kpi.full_date.max().date()
c1, c2 = st.columns([3, 1])
rng = c1.date_input("Period", (lo, hi), min_value=lo, max_value=hi)
if isinstance(rng, tuple) and len(rng) == 2:
    k = kpi[(kpi.full_date.dt.date >= rng[0]) & (kpi.full_date.dt.date <= rng[1])]
else:
    k = kpi
c2.metric("Days in view", f"{len(k)}")

tabs = st.tabs(["Overview", "Profit", "Delivery & zones", "Forecast",
                "Customers", "Menu", "Daily log"])

# =========================================================== 1. OVERVIEW
with tabs[0]:
    a, b, c, d, e = st.columns(5)
    a.metric("Revenue", eur(k.gross_revenue.sum()))
    b.metric("Orders", f"{int(k.orders.sum()):,}")
    c.metric("Avg order", eur(k.gross_revenue.sum() / max(k.orders.sum(), 1), 2))
    d.metric("Operating profit", eur(k.operating_profit.sum()))
    e.metric("Operating margin",
             f"{k.operating_profit.sum() / max(k.net_revenue.sum(), 1):.1%}")

    st.subheader("Revenue over time")
    daily = k.set_index("full_date")[["gross_revenue"]].copy()
    daily["7-day average"] = daily.gross_revenue.rolling(7).mean()
    daily = daily.rename(columns={"gross_revenue": "Revenue"})
    st.line_chart(daily, height=280)

    left, right = st.columns(2)
    with left:
        st.subheader("By weekday")
        dow = (k.groupby(["day_of_week", "day_name"], as_index=False)
                 .orders.mean().sort_values("day_of_week"))
        # st.bar_chart sorts a string index alphabetically - Friday, Monday,
        # Saturday - exactly the trap Power BI has. Altair lets the order be
        # stated explicitly.
        order = dow.sort_values("day_of_week").day_name.tolist()
        st.altair_chart(
            alt.Chart(dow).mark_bar().encode(
                x=alt.X("day_name:N", sort=order, title=None),
                y=alt.Y("orders:Q", title="Avg orders"),
            ).properties(height=260),
            use_container_width=True)
        st.caption("Saturday runs about 1.9x Monday. Staffing should not be flat.")
    with right:
        st.subheader("Rain vs dry")
        rain = (k.groupby(k.is_rainy.map({True: "Rainy", False: "Dry"}))
                  .orders.mean().rename("Avg orders").to_frame())
        st.bar_chart(rain, height=260)
        st.caption("Raw split understates it - rain lands mostly in low-season "
                   "summer. Controlling for month and weekday, rain is +7.3%.")

# ============================================================= 2. PROFIT
with tabs[1]:
    st.subheader("Where the money goes")
    net = k.net_revenue.sum()
    lines = [
        ("Net revenue", net),
        ("Food cost", -k.food_cost.sum()),
        ("Packaging", -k.packaging_cost.sum()),
        ("Waste", -k.waste_eur.sum()),
        ("Labour", -k.labour_cost.sum()),
        ("Payment fees", -k.payment_fees.sum()),
        ("Fixed costs", -k.fixed_cost.sum()),
        ("Franchise fees", -k.royalty_cost.sum()),
    ]
    pl = pd.DataFrame(lines, columns=["Line", "EUR"])
    pl["% of net revenue"] = (pl.EUR / net * 100).round(1)
    profit = pl.EUR.sum()
    pl.loc[len(pl)] = ["= Operating profit", profit, round(profit / net * 100, 1)]

    shown = pl.copy()
    shown["EUR"] = shown.EUR.map(lambda v: f"{v:,.0f}")
    shown["% of net revenue"] = shown["% of net revenue"].map(lambda v: f"{v:.1f}%")

    left, right = st.columns([1, 1])
    left.dataframe(shown, hide_index=True, use_container_width=True)
    costs = pl[~pl.Line.isin(["Net revenue", "= Operating profit"])]
    right.bar_chart(costs.assign(EUR=costs.EUR.abs()).set_index("Line")[["EUR"]],
                    height=340)

    st.info("**Labour is the biggest cost at 33.6%** - and the only large one "
            "you control day to day. Fixed costs and franchise fees are "
            "contractual; food cost moves with supplier prices.")

    try:
        st.subheader("What the profit figure assumes")
        st.dataframe(get("mart.dim_cost_assumption"), hide_index=True,
                     use_container_width=True)
    except Exception:                                         # noqa: BLE001
        pass

# =================================================== 3. DELIVERY & ZONES
with tabs[2]:
    zones = get("mart.kpi_zone").sort_values("distance_km")
    st.subheader("Zone performance")
    show = zones[["plz", "district_name", "distance_km", "orders",
                  "avg_order_value", "avg_delivery_min", "late_rate_pct",
                  "margin_per_drive_minute"]]
    st.dataframe(show, hide_index=True, use_container_width=True)

    left, right = st.columns(2)
    left.bar_chart(zones.set_index("district_name")[["late_rate_pct"]],
                   height=280)
    left.caption("Late rate by zone")
    right.bar_chart(zones.set_index("district_name")[["margin_per_drive_minute"]],
                    height=280)
    right.caption("Margin earned per driver-minute")

    try:
        promise = get("mart.delivery_promise")
        st.subheader("What each zone should actually promise")
        st.dataframe(
            promise[["plz", "district_name", "distance_km",
                     "current_promise_min", "recommended_promise_min",
                     "current_late_pct"]],
            hide_index=True, use_container_width=True)
        st.warning(
            "**Golm is promised 45 minutes and misses it 63% of the time.** "
            "At 9.5 km the 80th percentile is 54 minutes - that is geometry, "
            "not staff performance. Meanwhile Waldstadt reliably delivers in "
            "33 minutes and is still advertised at 45.")
    except Exception:                                         # noqa: BLE001
        st.caption("Run `python src/run_ml.py` to add recommended promise times.")

# =========================================================== 4. FORECAST
with tabs[3]:
    try:
        fc = get("mart.forecast_daily")
        fc["full_date"] = pd.to_datetime(fc["full_date"])
        st.subheader("Next 14 days")
        a, b = st.columns(2)
        a.metric("Forecast orders", f"{int(fc.orders_forecast.sum()):,}")
        b.metric("Forecast revenue", eur(fc.revenue_forecast.sum()))

        chart = fc.set_index("full_date")[
            ["orders_lower", "orders_forecast", "orders_upper"]].rename(columns={
                "orders_lower": "Low", "orders_forecast": "Forecast",
                "orders_upper": "High"})
        st.line_chart(chart, height=300)

        st.dataframe(
            fc[["full_date", "day_name", "orders_forecast", "orders_lower",
                "orders_upper", "precipitation_mm", "revenue_forecast"]],
            hide_index=True, use_container_width=True)
        st.caption("Forecast uses the real Open-Meteo weather forecast for "
                   "Potsdam. Backtested at 11% error - 32% better than "
                   "assuming the same as last week.")
    except Exception:                                         # noqa: BLE001
        st.info("Run `python src/run_ml.py` to generate the forecast.")

# ========================================================== 5. CUSTOMERS
with tabs[4]:
    try:
        rfm = get("mart.customer_rfm")
        seg = (rfm.groupby("segment")
                  .agg(customers=("customer_key", "count"),
                       revenue=("monetary", "sum"))
                  .sort_values("revenue", ascending=False).reset_index())
        seg["% of revenue"] = (seg.revenue / seg.revenue.sum() * 100).round(1)

        st.subheader("Segments")
        left, right = st.columns([1, 1])
        seg_shown = seg.copy()
        seg_shown["revenue"] = seg_shown.revenue.map(lambda v: f"{v:,.0f}")
        seg_shown["% of revenue"] = seg_shown["% of revenue"].map(
            lambda v: f"{v:.1f}%")
        left.dataframe(seg_shown, hide_index=True, use_container_width=True)
        right.bar_chart(seg.set_index("segment")[["revenue"]], height=300)
        st.success("**Champions are 24% of customers and 53% of revenue.** "
                   "Losing one is worth roughly ten occasional customers.")

        churn = get("mart.customer_churn")
        high = (churn[churn.risk_band == "High"]
                .sort_values("monetary", ascending=False).head(50))
        st.subheader(f"Win-back list — {len(churn[churn.risk_band == 'High']):,} "
                     f"high-risk customers")
        st.dataframe(
            high[["customer_key", "frequency", "monetary", "avg_order_value",
                  "recency_days", "churn_probability"]],
            hide_index=True, use_container_width=True)
        st.caption("Sorted by historic value - call the top of this list first.")
    except Exception:                                         # noqa: BLE001
        st.info("Run `python src/run_ml.py` to generate customer segments.")

# =============================================================== 6. MENU
with tabs[5]:
    items = get("mart.kpi_item")
    st.subheader("Item performance")
    st.dataframe(
        items[["item_name", "category", "size_name", "unit_price", "units_sold",
               "revenue", "margin", "margin_pct"]]
        .sort_values("revenue", ascending=False),
        hide_index=True, use_container_width=True)

    st.subheader("Revenue by category")
    cat = items.groupby("category", as_index=False).revenue.sum()
    st.bar_chart(cat.set_index("category")[["revenue"]], height=260)

    try:
        rules = get("mart.basket_rules").head(15)
        st.subheader("What gets ordered together")
        st.dataframe(
            rules[["item_a", "item_b", "support", "confidence", "lift"]],
            hide_index=True, use_container_width=True)
        st.caption("Lift is the number that matters - 2.0 means twice as "
                   "likely as chance. High confidence on a common item like "
                   "Cola is trivially true and worth nothing.")
    except Exception:                                         # noqa: BLE001
        st.caption("Run `python src/run_ml.py` to add basket rules.")


# ========================================================== 7. DAILY LOG
with tabs[6]:
    st.subheader("What the nightly form has captured")
    st.caption("app.py writes to staging.daily_entry. build_marts.py folds it "
               "into mart.daily_actuals, which is what this page and Power BI "
               "both read. That is the whole link between the form and the "
               "reporting.")
    try:
        act = get("mart.daily_actuals").copy()
        act["business_date"] = pd.to_datetime(act["business_date"])
        act = act.sort_values("business_date", ascending=False)

        a, b, c = st.columns(3)
        a.metric("Days recorded", f"{len(act):,}")
        b.metric("From order data", f"{(act.source == 'history').sum():,}")
        c.metric("From the form", f"{(act.source == 'form').sum():,}")

        st.dataframe(
            act.head(30)[["business_date", "total_orders", "gross_revenue",
                          "avg_order_value", "delivery_orders", "pickup_orders",
                          "staff_hours", "source"]],
            hide_index=True, use_container_width=True)

        gap = (pd.Timestamp.today().normalize()
               - act.business_date.max()).days
        if gap > 1:
            st.warning(f"**Last entry was {gap} days ago.** Gaps distort the "
                       f"forecast - fill them in on the entry form.")
        else:
            st.success("Up to date.")
    except Exception as exc:                                  # noqa: BLE001
        st.info(f"Run `python src/build_marts.py` to build the daily log. ({exc})")
