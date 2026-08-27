"""Sanity-check the generated data.

Two jobs:
  1. Are the business numbers plausible for a real branch of this size?
  2. Are the effects we deliberately built in statistically recoverable?

(2) matters most. If an effect is not recoverable here, no downstream model
will find it either, and any dashboard insight based on it would be noise.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

PROC = Path(__file__).parents[1] / "data" / "processed"

# effect name -> (column, coded multiplier)
CODED = {"rainy": 1.11, "hot": 0.88, "cold": 1.08, "ph": 1.15, "sh": 0.94}

PLAUSIBLE = {           # metric -> (low, high) for a real branch
    "aov_eur":        (18.0, 30.0),
    "orders_per_day": (70.0, 200.0),
    "late_pct":       (5.0, 25.0),
    "delivery_min":   (25.0, 50.0),
    "food_cost_pct":  (25.0, 35.0),
    # A branch where these are wrong produces a dashboard that lies about
    # profitability, which is worse than no dashboard.
    "labour_cost_pct": (28.0, 38.0),
    "operating_margin_pct": (5.0, 18.0),
}


def load():
    o = pd.read_parquet(PROC / "fct_order.parquet")
    d = pd.read_parquet(PROC / "dim_date.parquet")
    s = pd.read_parquet(PROC / "fct_shift.parquet")
    return o, d, s


def check_plausibility(o, s) -> bool:
    deliv = o[o.is_delivery]
    net = o.net_revenue.sum()
    total_cost = (o.food_cost.sum() + s.labour_cost.sum() + s.waste_eur.sum()
                  + s.packaging_cost.sum() + s.payment_fees.sum()
                  + s.fixed_cost.sum() + s.royalty_cost.sum())
    actual = {
        "aov_eur":        o.gross_amount.mean(),
        "orders_per_day": o.groupby("date_key").size().mean(),
        "late_pct":       deliv.is_late.mean() * 100,
        "delivery_min":   deliv.actual_min.mean(),
        "food_cost_pct":  o.food_cost.sum() / o.gross_amount.sum() * 100,
        "labour_cost_pct": s.labour_cost.sum() / net * 100,
        "operating_margin_pct": (net - total_cost) / net * 100,
    }
    print("=== business plausibility ===")
    ok = True
    for k, (lo, hi) in PLAUSIBLE.items():
        v = actual[k]
        good = lo <= v <= hi
        ok &= good
        print(f"  {'PASS' if good else 'FAIL'}  {k:<16} {v:8.1f}   expected {lo}-{hi}")
    return ok


def check_effects(o, d) -> bool:
    day = o.groupby("date_key").size().rename("orders").reset_index().merge(d, on="date_key")
    day["rainy"] = day.is_rainy.astype(int)
    day["hot"] = (day.temp_max_c > 28).astype(int)
    day["cold"] = day.is_cold.astype(int)
    day["ph"] = day.is_public_holiday.astype(int)
    day["sh"] = day.is_school_holiday.astype(int)

    model = smf.ols(
        "np.log(orders) ~ rainy + hot + cold + ph + sh + C(day_of_week) + C(month)",
        data=day).fit()

    print("\n=== effect recovery (controlling for month + weekday) ===")
    print(f"  {'effect':<8} {'coded':>8} {'recovered':>11} {'p':>9}   verdict")
    all_sig = True
    for name, mult in CODED.items():
        rec = np.exp(model.params[name]) - 1
        p = model.pvalues[name]
        sig = p < 0.05
        all_sig &= sig
        verdict = "identified" if sig else "NOT identifiable (too few obs)"
        print(f"  {name:<8} {mult - 1:>+7.0%} {rec:>+11.1%} {p:>9.4f}   {verdict}")
    print(f"\n  R2 = {model.rsquared:.3f}  on {len(day)} days")
    return all_sig


def main():
    o, d, s = load()
    plausible = check_plausibility(o, s)
    identified = check_effects(o, d)

    print("\n" + "=" * 60)
    if plausible and identified:
        print("ALL CHECKS PASSED")
    else:
        if not plausible:
            print("WARNING: some business metrics are outside plausible ranges.")
        if not identified:
            print("WARNING: some coded effects are not statistically identifiable.")
            print("         Usually means the date range is too short. Extend")
            print("         DATA_START in .env and re-run fetch_external.py.")


if __name__ == "__main__":
    main()
