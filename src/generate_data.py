"""Generate synthetic order data for Pizza Delivery Analytics.

The demand model is driven by REAL Potsdam weather and REAL Brandenburg public
holidays (see fetch_external.py), so the relationships the ML layer learns are
grounded in real exogenous variation rather than pure noise.

Effects deliberately built in (these are what the models should rediscover):
  * strong Fri/Sat peak, Monday trough
  * summer dip - Potsdam lakes plus the Uni semester break
  * rain increases delivery orders; heat reduces them
  * public holidays up, 25/26 Dec down, Silvester way up
  * school holidays slightly down (families away)
  * Tuesday 2-for-1 promo
  * channel mix drifting from Telefon toward App and Lieferando
  * the Lieferando 13 percent commission quietly destroying margin
  * seven basket archetypes producing genuine item association rules
  * two injected anomaly windows (discount abuse, oven failure)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import reference_data as R  # noqa: E402

ROOT = Path(__file__).parents[1]
RAW, PROC = ROOT / "data" / "raw", ROOT / "data" / "processed"
PROC.mkdir(parents=True, exist_ok=True)

rng = np.random.default_rng(42)

# ------------------------------------------------------------------ demand
BASE_ORDERS = 95
DOW_FACTOR = {1: 0.82, 2: 0.88, 3: 0.92, 4: 1.00, 5: 1.46, 6: 1.52, 7: 1.22}
MONTH_FACTOR = {1: 1.08, 2: 1.06, 3: 1.02, 4: 0.98, 5: 0.94, 6: 0.89,
                7: 0.84, 8: 0.86, 9: 0.99, 10: 1.06, 11: 1.10, 12: 1.12}
YEARLY_GROWTH = 0.06

DAYPARTS = ["Mittag", "Nachmittag", "Abend", "Spaet"]
DAYPART_P_WEEK = [0.19, 0.13, 0.52, 0.16]
DAYPART_P_WEEKEND = [0.12, 0.11, 0.53, 0.24]
DAYPART_HOURS = {"Mittag": (11, 14), "Nachmittag": (14, 17),
                 "Abend": (17, 21), "Spaet": (21, 24)}

ARCHETYPES = ["Student Solo", "Paar", "Familie", "Party", "Quick", "Pasta", "Light"]
ARCHETYPE_P = [0.24, 0.24, 0.17, 0.04, 0.16, 0.11, 0.04]

# popularity across the 11 pizzas, in reference_data.PIZZAS order
PIZZA_POP = np.array([0.14, 0.17, 0.10, 0.07, 0.11, 0.06, 0.07, 0.07, 0.06, 0.09, 0.06])

N_CUSTOMERS = 2200
KITCHEN_WAGE, DRIVER_WAGE = R.KITCHEN_WAGE, R.DRIVER_WAGE

# Staffing model. A branch doing ~115 orders/day is not run by two people:
# it needs several kitchen staff across a 12-hour service plus 3-4 drivers on
# the road at peak. These coefficients put payroll near 33% of revenue, which
# is where German delivery gastronomy actually sits once employer
# contributions are included.
KITCHEN_BASE, KITCHEN_PER_ORDER = 14.0, 0.21
DRIVER_BASE, DRIVER_PER_DELIVERY = 4.0, 0.25


# ==========================================================================
# dimensions
# ==========================================================================
def build_dim_item() -> pd.DataFrame:
    rows, key = [], 0
    for name, base_price, base_cost, veg in R.PIZZAS:
        for size_name, mult in R.PIZZA_SIZES:
            key += 1
            rows.append((key, name, "Pizza", size_name,
                         round(base_price * mult, 2), round(base_cost * mult, 2), veg))
    for name, cat, price, cost, veg in R.OTHER_ITEMS:
        key += 1
        rows.append((key, name, cat, None, price, cost, veg))
    return pd.DataFrame(rows, columns=[
        "item_key", "item_name", "category", "size_name",
        "unit_price", "unit_cost", "is_vegetarian"])


def build_small_dims():
    ch = pd.DataFrame(R.CHANNELS, columns=[
        "channel_key", "channel_name", "is_aggregator", "commission_rate"])
    zo = pd.DataFrame(R.ZONES, columns=[
        "zone_key", "plz", "district_name", "distance_km",
        "base_drive_min", "delivery_fee"])
    dr = pd.DataFrame(R.DRIVERS, columns=["driver_key", "driver_name", "vehicle"])
    dr["hired_on"] = pd.Timestamp("2024-01-15").date()
    return ch, zo, dr


class Menu:
    """Numpy views over dim_item so basket building stays fast."""

    def __init__(self, items: pd.DataFrame):
        self.price = dict(zip(items.item_key, items.unit_price))
        self.cost = dict(zip(items.item_key, items.unit_cost))
        pz = items[items.category == "Pizza"]
        self.pizza_by_size = {
            size: pz[pz.size_name == size].item_key.to_numpy()
            for size, _ in R.PIZZA_SIZES
        }
        for cat, attr in [("Pasta", "pasta"), ("Salat", "salat"),
                          ("Getraenke", "drinks"), ("Dessert", "dessert")]:
            setattr(self, attr, items[items.category == cat].item_key.to_numpy())
        non_pizza = items[items.category != "Pizza"]
        self.named = dict(zip(non_pizza.item_name, non_pizza.item_key))


def pick_basket(m: Menu, archetype: str, is_summer: bool) -> list[tuple[int, int]]:
    """Return [(item_key, qty), ...]. Archetypes create real co-occurrence."""
    def pizzas(size: str, n: int = 1):
        return [(int(k), 1) for k in rng.choice(m.pizza_by_size[size], size=n, p=PIZZA_POP)]

    def one(arr):
        return [(int(rng.choice(arr)), 1)]

    def named(name):
        return [(int(m.named[name]), 1)]

    b: list[tuple[int, int]] = []
    if archetype == "Student Solo":
        b += pizzas("Normal 30cm")
        if rng.random() < 0.70: b += one(m.drinks)
        if rng.random() < 0.25: b += named("Pommes")
    elif archetype == "Paar":
        b += pizzas("Normal 30cm", 2)
        if rng.random() < (0.55 if is_summer else 0.32): b += one(m.salat)
        b += one(m.drinks) + one(m.drinks)
    elif archetype == "Familie":
        b += pizzas("Familie 40cm", int(rng.integers(2, 4)))
        b += named("Pommes")
        if rng.random() < 0.65: b += named("Chicken Nuggets 9er")
        for _ in range(int(rng.integers(2, 4))): b += one(m.drinks)
        if rng.random() < 0.35: b += one(m.dessert)
    elif archetype == "Party":
        b += pizzas("Familie 40cm", int(rng.integers(3, 6)))
        b += named("Chicken Wings 6er") + named("Chicken Nuggets 9er")
        if rng.random() < 0.60: b += named("Mozzarella Sticks")
        for _ in range(int(rng.integers(3, 6))): b += one(m.drinks)
    elif archetype == "Quick":
        b += pizzas("Klein 24cm")
        if rng.random() < 0.45: b += one(m.drinks)
    elif archetype == "Pasta":
        for _ in range(int(rng.integers(1, 3))): b += one(m.pasta)
        if rng.random() < 0.62: b += named("Knoblauchbrot")
        b += one(m.drinks)
    else:  # Light
        for _ in range(int(rng.integers(1, 3))): b += one(m.salat)
        b += named("Wasser 0,5l")
    return b


# ==========================================================================
# daily demand
# ==========================================================================
def daily_demand(dim_date: pd.DataFrame) -> pd.DataFrame:
    d = dim_date.copy()
    t = np.arange(len(d)) / 365.0

    f = np.full(len(d), float(BASE_ORDERS))
    f *= d["day_of_week"].map(DOW_FACTOR).to_numpy()
    f *= d["month"].map(MONTH_FACTOR).to_numpy()
    f *= (1 + YEARLY_GROWTH) ** t

    # --- REAL weather effects ---------------------------------------------
    rain = d["precipitation_mm"].to_numpy(dtype=float)
    f *= np.where(rain > 8, 1.18, np.where(rain > 2, 1.11, 1.0))
    f *= np.where(d["temp_mean_c"].to_numpy(dtype=float) < 5, 1.08, 1.0)
    f *= np.where(d["temp_max_c"].to_numpy(dtype=float) > 28, 0.88, 1.0)

    # --- REAL holiday effects ---------------------------------------------
    f *= np.where(d["is_public_holiday"].to_numpy(), 1.15, 1.0)
    f *= np.where(d["is_school_holiday"].to_numpy(), 0.94, 1.0)
    md = d["full_date"].astype(str).str.slice(5)
    f = np.where(md.isin(["12-25", "12-26"]), f * 0.55, f)
    f = np.where(md == "12-24", f * 0.70, f)
    f = np.where(md == "12-31", f * 1.45, f)
    f = np.where(md == "01-01", f * 1.30, f)

    promo = (d["day_of_week"] == 2).to_numpy()
    f *= np.where(promo, 1.32, 1.0)

    dk = d["date_key"].to_numpy()
    oven_broken = (dk >= 20260211) & (dk <= 20260213)
    f = np.where(oven_broken, f * 0.35, f)

    out = d[["date_key", "full_date", "day_of_week", "month",
             "is_rainy", "temp_max_c"]].copy()
    out["n_orders"] = rng.poisson(np.maximum(f, 5))
    out["promo_active"] = promo
    out["oven_broken"] = oven_broken
    out["shrinkage"] = (dk >= 20260504) & (dk <= 20260517)
    return out


def build_customers(n: int, n_days: int) -> pd.DataFrame:
    keys = np.arange(1, n + 1)
    # 62 percent exist on day 0; the rest arrive as new customers over the year
    active_from = np.where(rng.random(n) < 0.62, 0, rng.integers(1, n_days, n))
    churn_after = np.where(rng.random(n) < 0.18,
                           rng.integers(30, n_days, n), 10 ** 6)
    return pd.DataFrame({
        "customer_key": keys,
        "customer_code": [f"CUST-{k:05d}" for k in keys],
        "zone_key": rng.choice([z[0] for z in R.ZONES], size=n, p=R.ZONE_WEIGHTS),
        "signup_channel": rng.choice(["Telefon", "Website", "App", "Lieferando"],
                                     size=n, p=[0.22, 0.26, 0.30, 0.22]),
        "loyalty": rng.pareto(1.6, size=n) + 1.0,
        "active_from": active_from,
        "churn_after": churn_after,
    })


# ==========================================================================
# orders
# ==========================================================================
def generate_orders(demand, items, channels, zones, customers):
    menu = Menu(items)
    n_days = len(demand)

    ch_keys = channels.channel_key.to_numpy()
    ch_comm = dict(zip(channels.channel_key, channels.commission_rate))
    abholung_key = int(channels.loc[channels.channel_name == "Abholung", "channel_key"].iloc[0])

    zone_keys = zones.zone_key.to_numpy()
    zone_drive = dict(zip(zones.zone_key, zones.base_drive_min))
    zone_fee = dict(zip(zones.zone_key, zones.delivery_fee))

    cust_loyalty = customers.loyalty.to_numpy()
    cust_active = customers.active_from.to_numpy()
    cust_churn = customers.churn_after.to_numpy()
    cust_keys = customers.customer_key.to_numpy()
    driver_keys = np.array([d[0] for d in R.DRIVERS])

    orders, lines = [], []
    order_key = order_item_key = 0

    for i, row in enumerate(demand.itertuples(index=False)):
        n = int(row.n_orders)
        if n == 0:
            continue
        frac = i / max(n_days - 1, 1)
        is_summer = row.month in (6, 7, 8)

        # channel mix drifts from Telefon toward App / Lieferando
        p_ch = np.array([0.32 - 0.12 * frac, 0.24 - 0.04 * frac,
                         0.16 + 0.10 * frac, 0.16 + 0.06 * frac, 0.12])
        p_ch = p_ch / p_ch.sum()

        p_dp = DAYPART_P_WEEKEND if row.day_of_week in (5, 6, 7) else DAYPART_P_WEEK

        eligible = (cust_active <= i) & (cust_churn > i)
        w = cust_loyalty * eligible
        w = w / w.sum()

        day_ch = rng.choice(ch_keys, size=n, p=p_ch)
        day_dp = rng.choice(DAYPARTS, size=n, p=p_dp)
        day_cust = rng.choice(cust_keys, size=n, p=w)
        day_arch = rng.choice(ARCHETYPES, size=n, p=ARCHETYPE_P)
        day_zone = rng.choice(zone_keys, size=n, p=R.ZONE_WEIGHTS)
        day_drv = rng.choice(driver_keys, size=n)
        load = min(n / 240.0, 1.4)

        for j in range(n):
            order_key += 1
            ck = int(day_ch[j])
            delivery = ck != abholung_key
            zk = int(day_zone[j]) if delivery else None
            dp = str(day_dp[j])

            basket = pick_basket(menu, str(day_arch[j]), is_summer)
            gross = food = qty = 0.0
            for ik, q in basket:
                price, cost = menu.price[ik], menu.cost[ik]
                order_item_key += 1
                lines.append((order_item_key, order_key, int(row.date_key), ik, q,
                              price, round(price * q, 2), round(cost * q, 2)))
                gross += price * q
                food += cost * q
                qty += q

            # --- discounts -------------------------------------------------
            n_pizza = sum(1 for ik, _ in basket if ik in menu.price and ik <= 33)
            disc = 0.0
            if row.promo_active and n_pizza >= 2:
                disc = min(menu.price[basket[0][0]], gross * 0.40)   # 2-for-1
            elif rng.random() < 0.08:
                disc = round(gross * rng.uniform(0.05, 0.15), 2)
            if row.shrinkage and rng.random() < 0.30:                # injected abuse
                disc += round(gross * rng.uniform(0.20, 0.35), 2)
            disc = round(min(disc, gross * 0.6), 2)

            fee = float(zone_fee[zk]) if delivery else 0.0
            comm = round(float(ch_comm[ck]) * (gross - disc), 2)
            net = round(gross - disc + fee - comm, 2)

            # --- delivery time ---------------------------------------------
            promised = actual = late = None
            if delivery:
                kitchen = 13 + 14 * load + rng.normal(0, 4.0)
                drive = float(zone_drive[zk]) * (1.15 if row.is_rainy else 1.0)
                drive *= rng.normal(1.0, 0.20)
                # drivers run 2-3 orders per trip, so most orders wait
                batching = max(0.0, rng.normal(3.0, 2.5))
                if row.oven_broken:
                    kitchen += 25
                actual = int(max(15, round(kitchen + drive + batching)))
                promised = 60 if (dp == "Abend" and load > 0.8) else 45
                late = actual > promised

            lo, hi = DAYPART_HOURS[dp]
            ts = pd.Timestamp(row.full_date) + pd.Timedelta(
                minutes=int(rng.integers(lo * 60, hi * 60)))

            orders.append((
                order_key, int(row.date_key), ts, dp, int(day_cust[j]), ck, zk,
                int(day_drv[j]) if delivery else None, delivery, int(qty),
                round(gross, 2), disc, fee, comm, net, round(food, 2),
                promised, actual, late, bool(rng.random() < 0.015),
                "2FOR1_DI" if (row.promo_active and n_pizza >= 2) else None,
            ))

    fct_order = pd.DataFrame(orders, columns=[
        "order_key", "date_key", "order_ts", "daypart", "customer_key",
        "channel_key", "zone_key", "driver_key", "is_delivery", "item_qty",
        "gross_amount", "discount_amount", "delivery_fee", "commission_amount",
        "net_revenue", "food_cost", "promised_min", "actual_min", "is_late",
        "is_cancelled", "promo_code"])
    fct_item = pd.DataFrame(lines, columns=[
        "order_item_key", "order_key", "date_key", "item_key", "quantity",
        "unit_price", "line_revenue", "line_cost"])
    return fct_order, fct_item


def build_shifts(demand, fct_order, n_days: int) -> pd.DataFrame:
    """Daily operating costs: labour, waste, packaging, fees, fixed, royalty."""
    agg = fct_order.groupby("date_key").agg(
        orders=("order_key", "count"),
        deliveries=("is_delivery", "sum"),
        food=("food_cost", "sum"),
        gross=("gross_amount", "sum"),
        net=("net_revenue", "sum")).reset_index()

    kitchen = np.round(
        KITCHEN_BASE + agg.orders * KITCHEN_PER_ORDER
        + rng.normal(0, 1.6, len(agg)), 1).clip(8)
    driver = np.round(
        DRIVER_BASE + agg.deliveries * DRIVER_PER_DELIVERY
        + rng.normal(0, 1.3, len(agg)), 1).clip(3)
    waste = np.round(agg.food * rng.uniform(0.010, 0.035, len(agg)), 2)

    rates = {name: rate for name, rate, _base, _note in R.VARIABLE_COST_RATES}
    packaging = np.round(agg.gross * rates["Verpackung"], 2)
    payment = np.round(agg.gross * R.CASHLESS_SHARE * rates["Zahlungsgebuehren"], 2)
    royalty = np.round(
        agg.net * (rates["Franchise-Royalty"] + rates["Marketingumlage"]), 2)

    # Fixed costs are monthly; spread them evenly so daily profit is comparable
    # across days. Allocating by revenue instead would flatter weekends and
    # punish Mondays for no operational reason.
    fixed_daily = sum(m for _n, m, _note in R.FIXED_COSTS_MONTHLY) * 12 / 365.0

    return pd.DataFrame({
        "shift_key": np.arange(1, len(agg) + 1),
        "date_key": agg.date_key,
        "kitchen_hours": kitchen,
        "driver_hours": driver,
        "labour_cost": np.round(kitchen * KITCHEN_WAGE + driver * DRIVER_WAGE, 2),
        "waste_eur": waste,
        "packaging_cost": packaging,
        "payment_fees": payment,
        "fixed_cost": round(fixed_daily, 2),
        "royalty_cost": royalty,
    })


def build_cost_assumptions() -> pd.DataFrame:
    rows = [(n, "fix", m, None, note) for n, m, note in R.FIXED_COSTS_MONTHLY]
    rows += [(n, "variabel", None, r, f"{note} ({base})")
             for n, r, base, note in R.VARIABLE_COST_RATES]
    return pd.DataFrame(rows, columns=[
        "cost_item", "cost_type", "monthly_eur", "pct_of_revenue", "note"])


def build_staging(demand, fct_order, fct_shift, dim_date) -> pd.DataFrame:
    """What the employee would have typed into the Streamlit form each night."""
    o = fct_order.groupby("date_key").agg(
        total_orders=("order_key", "count"),
        gross_revenue=("gross_amount", "sum"),
        delivery_orders=("is_delivery", "sum"),
        cancelled=("is_cancelled", "sum")).reset_index()
    o["pickup_orders"] = o.total_orders - o.delivery_orders
    o["gross_revenue"] = o.gross_revenue.round(2)

    df = (o.merge(fct_shift[["date_key", "kitchen_hours", "driver_hours", "waste_eur"]],
                  on="date_key")
            .merge(dim_date[["date_key", "full_date"]], on="date_key")
            .merge(demand[["date_key", "promo_active"]], on="date_key"))

    df = df.rename(columns={"full_date": "business_date",
                            "kitchen_hours": "staff_hours"})
    df["promo_note"] = np.where(df.promo_active, "2for1 Dienstag", None)
    df["is_closed"] = df.total_orders == 0
    df["complaints"] = rng.poisson(0.9, len(df))
    df["notes"] = None
    df["entered_by"] = "Abhishek"
    return df[["business_date", "total_orders", "gross_revenue", "delivery_orders",
               "pickup_orders", "cancelled", "waste_eur", "staff_hours",
               "driver_hours", "promo_active", "promo_note", "is_closed",
               "complaints", "notes", "entered_by"]]


# ==========================================================================
def main():
    dim_date = pd.read_csv(RAW / "dim_date.csv")
    print(f"dim_date        {len(dim_date):>7} days (real weather + BB holidays)")

    dim_item = build_dim_item()
    dim_channel, dim_zone, dim_driver = build_small_dims()
    demand = daily_demand(dim_date)
    dim_customer = build_customers(N_CUSTOMERS, len(dim_date))

    fct_order, fct_order_item = generate_orders(
        demand, dim_item, dim_channel, dim_zone, dim_customer)
    fct_shift = build_shifts(demand, fct_order, len(dim_date))
    dim_cost_assumption = build_cost_assumptions()
    daily_entry = build_staging(demand, fct_order, fct_shift, dim_date)

    # first_order_date from the actual orders; drop generator-only columns
    first = (fct_order.merge(dim_date[["date_key", "full_date"]], on="date_key")
             .groupby("customer_key").full_date.min().rename("first_order_date"))
    dim_customer = (dim_customer.merge(first, on="customer_key", how="left")
                    .drop(columns=["loyalty", "active_from", "churn_after"]))

    tables = {
        "dim_date": dim_date, "dim_item": dim_item, "dim_channel": dim_channel,
        "dim_zone": dim_zone, "dim_driver": dim_driver, "dim_customer": dim_customer,
        "fct_order": fct_order, "fct_order_item": fct_order_item,
        "fct_shift": fct_shift, "daily_entry": daily_entry,
        "dim_cost_assumption": dim_cost_assumption,
    }
    for name, df in tables.items():
        df.to_csv(PROC / f"{name}.csv", index=False)
        df.to_parquet(PROC / f"{name}.parquet", index=False)
        print(f"  {name:<16} {len(df):>7,} rows")

    net = fct_order.net_revenue.sum()
    lines = [
        ("Net revenue",        net),
        ("- Food cost",       -fct_order.food_cost.sum()),
        ("- Packaging",       -fct_shift.packaging_cost.sum()),
        ("- Waste",           -fct_shift.waste_eur.sum()),
        ("- Labour",          -fct_shift.labour_cost.sum()),
        ("- Payment fees",    -fct_shift.payment_fees.sum()),
        ("- Fixed costs",     -fct_shift.fixed_cost.sum()),
        ("- Franchise fees",  -fct_shift.royalty_cost.sum()),
    ]
    print("\n--- Annual P&L ---")
    for label, val in lines:
        print(f"  {label:<20} EUR {val:>11,.0f}   {val / net * 100:>6.1f} %")
    profit = sum(v for _label, v in lines)
    print(f"  {'= Operating profit':<20} EUR {profit:>11,.0f}   "
          f"{profit / net * 100:>6.1f} %")
    print(f"\n  avg order value  EUR {fct_order.gross_amount.mean():>10,.2f}")
    print(f"  late deliveries  {fct_order.is_late.mean() * 100:>13.1f} %")


if __name__ == "__main__":
    main()
