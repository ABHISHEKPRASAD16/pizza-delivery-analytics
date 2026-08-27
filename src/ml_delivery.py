"""Delivery time model - and what promise time each zone should actually get.

Outputs: mart.delivery_factors, mart.delivery_promise

The branch currently promises 45 minutes everywhere. The zone analysis showed
Golm missing that on 63% of orders - not because anyone is slow, but because
9.5km plus kitchen time plus driver batching does not fit in 45 minutes. A
promise you structurally cannot keep is a complaint generator, not a target.

So this does two things:

1. Trains a model on actual delivery times and uses SHAP to say WHICH factors
   drive them - distance, kitchen load, rain, daypart.
2. Computes, per zone, the promise time that would actually be met 80% of the
   time. That is a number the branch can put on the website.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import train_test_split

sys.path.insert(0, str(Path(__file__).parent))
from ml_common import banner, load, write_mart  # noqa: E402

SERVICE_LEVEL = 0.80        # promise we intend to hit 80% of the time


def build_frame() -> pd.DataFrame:
    o = load("mart.fct_order")
    o = o[o.is_delivery & o.actual_min.notna()].copy()

    zones = load("mart.dim_zone")[["zone_key", "plz", "district_name",
                                   "distance_km", "base_drive_min"]]
    dates = load("mart.dim_date")[["date_key", "full_date", "day_of_week",
                                   "is_rainy", "temp_mean_c", "precipitation_mm"]]
    daily = load("mart.kpi_daily")[["date_key", "orders"]].rename(
        columns={"orders": "orders_that_day"})

    df = (o.merge(zones, on="zone_key")
            .merge(dates, on="date_key")
            .merge(daily, on="date_key"))
    df["daypart_code"] = df.daypart.map(
        {"Mittag": 0, "Nachmittag": 1, "Abend": 2, "Spaet": 3}).fillna(0)
    df["is_rainy"] = df.is_rainy.astype(int)
    return df


FEATURES = ["distance_km", "base_drive_min", "orders_that_day", "daypart_code",
            "is_rainy", "precipitation_mm", "temp_mean_c", "day_of_week",
            "item_qty"]


def main() -> None:
    banner("DELIVERY TIME MODEL")

    df = build_frame()
    print(f"delivery orders {len(df):>8,}")
    print(f"actual minutes  {df.actual_min.mean():>8.1f} avg, "
          f"{df.actual_min.quantile(0.8):.0f} at p80")

    X, y = df[FEATURES], df.actual_min.astype(float)
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.25, random_state=42)
    model = LGBMRegressor(n_estimators=400, learning_rate=0.05,
                          num_leaves=31, random_state=42, verbose=-1)
    model.fit(X_tr, y_tr)
    mae = mean_absolute_error(y_te, model.predict(X_te))
    naive = mean_absolute_error(y_te, np.full(len(y_te), y_tr.mean()))
    print(f"\nmodel MAE       {mae:>8.2f} min")
    print(f"naive (mean)    {naive:>8.2f} min   -> {1 - mae / naive:.1%} better")

    # --- what actually drives delivery time ---------------------------
    import shap
    expl = shap.TreeExplainer(model)
    sv = expl.shap_values(X_te.sample(min(3000, len(X_te)), random_state=42))
    imp = (pd.DataFrame({"feature": FEATURES,
                         "mean_abs_shap": np.abs(sv).mean(axis=0)})
           .sort_values("mean_abs_shap", ascending=False)
           .reset_index(drop=True))
    imp["mean_abs_shap"] = imp.mean_abs_shap.round(3)
    imp["share_of_effect"] = (imp.mean_abs_shap / imp.mean_abs_shap.sum()).round(4)
    imp.insert(0, "rank", imp.index + 1)

    print("\nwhat drives delivery time (SHAP, minutes of influence):")
    for r in imp.itertuples(index=False):
        bar = "#" * int(r.share_of_effect * 60)
        print(f"  {r.feature:<18}{r.mean_abs_shap:>6.2f} min  {r.share_of_effect:>6.1%} {bar}")

    # --- the promise each zone should carry ---------------------------
    promise = (df.groupby(["zone_key", "plz", "district_name", "distance_km"])
                 .agg(orders=("order_key", "count"),
                      avg_min=("actual_min", "mean"),
                      p80_min=("actual_min", lambda s: s.quantile(SERVICE_LEVEL)),
                      p95_min=("actual_min", lambda s: s.quantile(0.95)),
                      current_late_pct=("is_late", "mean"))
                 .reset_index())
    promise["avg_min"] = promise.avg_min.round(1)
    promise["current_late_pct"] = (promise.current_late_pct * 100).round(1)
    # round the recommendation up to the next 5 minutes - nobody promises 47
    promise["recommended_promise_min"] = (
        np.ceil(promise.p80_min / 5) * 5).astype(int)
    promise["p80_min"] = promise.p80_min.round(0).astype(int)
    promise["p95_min"] = promise.p95_min.round(0).astype(int)
    promise["current_promise_min"] = 45
    promise = promise.sort_values("distance_km").reset_index(drop=True)

    print(f"\npromise times that would be met {SERVICE_LEVEL:.0%} of the time:")
    print(f"  {'PLZ':<7}{'district':<34}{'km':>5}{'p80':>6}{'promise':>9}"
          f"{'now late':>10}")
    for r in promise.itertuples(index=False):
        change = "" if r.recommended_promise_min <= 45 else "  <- raise it"
        print(f"  {r.plz:<7}{r.district_name:<34}{r.distance_km:>5.1f}"
              f"{r.p80_min:>6}{r.recommended_promise_min:>9}"
              f"{r.current_late_pct:>9.1f}%{change}")

    write_mart(imp, "delivery_factors")
    write_mart(promise, "delivery_promise")


if __name__ == "__main__":
    main()
