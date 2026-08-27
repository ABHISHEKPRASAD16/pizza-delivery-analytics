"""Demand forecast - how many orders to expect, 14 days ahead.

Output: mart.forecast_daily

Prophet with weather and calendar regressors. The forecast horizon is 14 days
because that is how far Open-Meteo forecasts for free - so the prediction uses
REAL forecast weather for Potsdam rather than a seasonal average. Rain was the
strongest effect we could identify in the history (+7.3% controlling for month
and weekday), so forecasting with the actual forecast rain matters.

Yearly seasonality is switched OFF deliberately: there is one year of history,
and Prophet fitting a yearly cycle to a single cycle just memorises the noise.
Weekly seasonality plus the regressors carry the signal.

The script backtests on a 28-day holdout and prints the error, so the forecast
comes with an honest accuracy number rather than a claim.
"""
from __future__ import annotations

import logging
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).parent))
from ml_common import banner, daily_frame, write_mart  # noqa: E402
from reference_data import STORE  # noqa: E402

warnings.filterwarnings("ignore")
logging.getLogger("cmdstanpy").setLevel(logging.ERROR)
logging.getLogger("prophet").setLevel(logging.ERROR)

HORIZON = 14
HOLDOUT = 28
REGRESSORS = ["precipitation_mm", "temp_mean_c", "is_rainy",
              "is_public_holiday", "is_school_holiday"]


# --------------------------------------------------------------- weather
def future_weather(start: str, end: str) -> pd.DataFrame:
    """Real Potsdam weather covering recent past AND the forecast window.

    `past_days` lets one call span the gap between the end of our history and
    today, then continue into the forecast.
    """
    resp = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": STORE["lat"], "longitude": STORE["lon"],
            "daily": "temperature_2m_mean,temperature_2m_max,precipitation_sum",
            "past_days": 92, "forecast_days": 16,
            "timezone": "Europe/Berlin",
        }, timeout=60)
    resp.raise_for_status()
    d = resp.json()["daily"]
    w = pd.DataFrame({
        "ds": pd.to_datetime(d["time"]),
        "temp_mean_c": d["temperature_2m_mean"],
        "temp_max_c": d["temperature_2m_max"],
        "precipitation_mm": d["precipitation_sum"],
    }).ffill()
    return w[(w.ds >= start) & (w.ds <= end)].reset_index(drop=True)


def calendar_flags(dates: pd.Series) -> pd.DataFrame:
    """Real Brandenburg public holidays + approximate school holidays."""
    import holidays as hol
    from reference_data import SCHOOL_HOLIDAYS_BB

    bb = hol.Germany(subdiv="BB", years=sorted(dates.dt.year.unique()))
    out = pd.DataFrame({"ds": dates})
    out["is_public_holiday"] = dates.dt.date.map(lambda x: x in bb).astype(int)
    out["is_school_holiday"] = 0
    for _name, s, e in SCHOOL_HOLIDAYS_BB:
        out.loc[(dates >= pd.Timestamp(s)) & (dates <= pd.Timestamp(e)),
                "is_school_holiday"] = 1
    return out


# ----------------------------------------------------------------- model
def fit(train: pd.DataFrame):
    from prophet import Prophet
    m = Prophet(weekly_seasonality=True, yearly_seasonality=False,
                daily_seasonality=False, seasonality_mode="multiplicative",
                changepoint_prior_scale=0.05, interval_width=0.80)
    for r in REGRESSORS:
        m.add_regressor(r)
    m.fit(train)
    return m


def prepare(k: pd.DataFrame) -> pd.DataFrame:
    df = pd.DataFrame({"ds": k.full_date, "y": k.orders})
    df["precipitation_mm"] = k.precipitation_mm.astype(float)
    df["temp_mean_c"] = k.temp_mean_c.astype(float)
    df["is_rainy"] = k.is_rainy.astype(int)
    df["is_public_holiday"] = k.is_public_holiday.astype(int)
    df["is_school_holiday"] = k.is_school_holiday.astype(int)
    return df


def backtest(df: pd.DataFrame) -> tuple[float, float]:
    """Train on everything but the last HOLDOUT days, score on those."""
    train, test = df.iloc[:-HOLDOUT], df.iloc[-HOLDOUT:]
    m = fit(train)
    pred = m.predict(test.drop(columns=["y"]))
    mae = float(np.mean(np.abs(pred.yhat.values - test.y.values)))
    mape = float(np.mean(np.abs(pred.yhat.values - test.y.values) / test.y.values))
    return mae, mape


def main() -> None:
    banner("DEMAND FORECAST  (Prophet + real weather)")

    k = daily_frame()
    df = prepare(k)
    last = df.ds.max()
    print(f"history      {df.ds.min():%Y-%m-%d} -> {last:%Y-%m-%d}  ({len(df)} days)")

    # --- honest accuracy check ----------------------------------------
    mae, mape = backtest(df)
    baseline = float(np.mean(np.abs(
        df.y.iloc[-HOLDOUT:].values - df.y.iloc[-HOLDOUT - 7:-7].values)))
    print(f"\nbacktest on last {HOLDOUT} days")
    print(f"  MAE            {mae:>7.1f} orders/day")
    print(f"  MAPE           {mape:>7.1%}")
    print(f"  naive (t-7d)   {baseline:>7.1f} orders/day  <- beat this to be useful")
    print(f"  improvement    {(1 - mae / baseline):>7.1%}")

    # --- forecast forward ---------------------------------------------
    future_dates = pd.date_range(last + pd.Timedelta(days=1), periods=HORIZON, freq="D")
    w = future_weather(future_dates.min().strftime("%Y-%m-%d"),
                       future_dates.max().strftime("%Y-%m-%d"))
    fut = pd.DataFrame({"ds": future_dates}).merge(w, on="ds", how="left")
    fut = fut.merge(calendar_flags(fut.ds), on="ds", how="left")
    fut["is_rainy"] = (fut.precipitation_mm > 2.0).astype(int)
    fut[REGRESSORS] = fut[REGRESSORS].ffill().bfill()

    model = fit(df)
    pred = model.predict(fut[["ds"] + REGRESSORS])

    aov = float(k.gross_revenue.tail(28).sum() / k.orders.tail(28).sum())
    out = pd.DataFrame({
        "full_date": pred.ds.dt.date,
        "day_name": pred.ds.dt.day_name(),
        "orders_forecast": pred.yhat.round(0).astype(int),
        "orders_lower": pred.yhat_lower.clip(lower=0).round(0).astype(int),
        "orders_upper": pred.yhat_upper.round(0).astype(int),
        "temp_mean_c": fut.temp_mean_c.round(1),
        "precipitation_mm": fut.precipitation_mm.round(1),
        "is_rainy": fut.is_rainy.astype(bool),
        "is_public_holiday": fut.is_public_holiday.astype(bool),
    })
    out["revenue_forecast"] = (out.orders_forecast * aov).round(2)

    print(f"\nnext {HORIZON} days (avg order value EUR {aov:.2f}):")
    print(f"  {'date':<12}{'day':<11}{'orders':>7}{'range':>12}{'rain':>7}{'revenue':>10}")
    for r in out.itertuples(index=False):
        flag = " *" if r.is_public_holiday else ""
        print(f"  {r.full_date!s:<12}{r.day_name:<11}{r.orders_forecast:>7}"
              f"{f'{r.orders_lower}-{r.orders_upper}':>12}"
              f"{r.precipitation_mm:>6.1f}mm{r.revenue_forecast:>10,.0f}{flag}")

    print(f"\n  total          {out.orders_forecast.sum():>6,} orders"
          f"   EUR {out.revenue_forecast.sum():>10,.0f}")

    write_mart(out, "forecast_daily")


if __name__ == "__main__":
    main()
