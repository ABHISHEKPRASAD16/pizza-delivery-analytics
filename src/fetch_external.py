"""Fetch REAL external data for Potsdam and build core.dim_date.

Sources
-------
Weather          : Open-Meteo ERA5 archive (free, no API key)   -> REAL
Public holidays  : `holidays` package, Germany subdiv='BB'      -> REAL
School holidays  : hardcoded in reference_data.SCHOOL_HOLIDAYS_BB -> APPROXIMATE
"""
from __future__ import annotations

import sys
from pathlib import Path

import holidays
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).parent))
from reference_data import STORE, SCHOOL_HOLIDAYS_BB  # noqa: E402

RAW = Path(__file__).parents[1] / "data" / "raw"
RAW.mkdir(parents=True, exist_ok=True)

MONTHS_EN = ["January", "February", "March", "April", "May", "June",
             "July", "August", "September", "October", "November", "December"]
DAYS_EN = ["Monday", "Tuesday", "Wednesday", "Thursday",
           "Friday", "Saturday", "Sunday"]

# German kept alongside: the branch, the till receipt and any colleague
# reading the report are German. English is the primary label.
MONTHS_DE = ["Januar", "Februar", "Maerz", "April", "Mai", "Juni",
             "Juli", "August", "September", "Oktober", "November", "Dezember"]
DAYS_DE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag",
           "Freitag", "Samstag", "Sonntag"]


def fetch_weather(start: str, end: str) -> pd.DataFrame:
    """Daily observed weather for the store's coordinates."""
    resp = requests.get(
        "https://archive-api.open-meteo.com/v1/archive",
        params={
            "latitude": STORE["lat"],
            "longitude": STORE["lon"],
            "start_date": start,
            "end_date": end,
            "daily": ("temperature_2m_mean,temperature_2m_max,"
                      "precipitation_sum,windspeed_10m_max"),
            "timezone": "Europe/Berlin",
        },
        timeout=90,
    )
    resp.raise_for_status()
    daily = resp.json()["daily"]

    df = pd.DataFrame({
        "full_date":        pd.to_datetime(daily["time"]).date,
        "temp_mean_c":      daily["temperature_2m_mean"],
        "temp_max_c":       daily["temperature_2m_max"],
        "precipitation_mm": daily["precipitation_sum"],
        "wind_max_kmh":     daily["windspeed_10m_max"],
    })
    # ERA5 can lag a few days at the tail; carry the last observation forward.
    return df.ffill()


def build_dim_date(start: str, end: str) -> pd.DataFrame:
    dates = pd.date_range(start, end, freq="D")
    df = pd.DataFrame({"full_date": dates.date})
    d = pd.to_datetime(df["full_date"])

    df["date_key"]     = d.dt.strftime("%Y%m%d").astype(int)
    df["year"]         = d.dt.year
    df["quarter"]      = d.dt.quarter
    df["month"]        = d.dt.month
    df["month_name"] = df["month"].map(lambda m: MONTHS_EN[m - 1])
    df["month_name_de"] = df["month"].map(lambda m: MONTHS_DE[m - 1])
    df["iso_week"]     = d.dt.isocalendar().week.astype(int)
    df["day_of_month"] = d.dt.day
    df["day_of_week"]  = d.dt.dayofweek + 1              # 1=Mon .. 7=Sun
    df["day_name"]     = df["day_of_week"].map(lambda x: DAYS_EN[x - 1])
    df["day_name_de"]  = df["day_of_week"].map(lambda x: DAYS_DE[x - 1])
    df["is_weekend"]   = df["day_of_week"].isin([6, 7])

    # --- REAL Brandenburg public holidays -----------------------------
    bb = holidays.Germany(subdiv="BB", years=sorted(df["year"].unique()))
    df["holiday_name"]      = df["full_date"].map(lambda x: bb.get(x))
    df["is_public_holiday"] = df["holiday_name"].notna()

    # --- APPROXIMATE Brandenburg school holidays ----------------------
    df["is_school_holiday"] = False
    for _name, s, e in SCHOOL_HOLIDAYS_BB:
        mask = (d >= pd.Timestamp(s)) & (d <= pd.Timestamp(e))
        df.loc[mask, "is_school_holiday"] = True

    # --- REAL weather -------------------------------------------------
    df = df.merge(fetch_weather(start, end), on="full_date", how="left")
    df["is_rainy"] = df["precipitation_mm"] > 2.0
    df["is_cold"]  = df["temp_mean_c"] < 5.0

    return df[[
        "date_key", "full_date", "year", "quarter", "month",
        "month_name", "month_name_de", "iso_week", "day_of_month",
        "day_of_week", "day_name", "day_name_de", "is_weekend",
        "is_public_holiday", "holiday_name", "is_school_holiday",
        "temp_mean_c", "temp_max_c", "precipitation_mm", "wind_max_kmh",
        "is_rainy", "is_cold",
    ]]


if __name__ == "__main__":
    start = sys.argv[1] if len(sys.argv) > 1 else "2025-09-01"
    end   = sys.argv[2] if len(sys.argv) > 2 else "2026-08-20"

    dim = build_dim_date(start, end)
    out = RAW / "dim_date.csv"
    dim.to_csv(out, index=False)

    print(f"dim_date: {len(dim)} days  {start} -> {end}")
    print(f"  public holidays : {int(dim.is_public_holiday.sum())}")
    print(f"  school-hol days : {int(dim.is_school_holiday.sum())}")
    print(f"  rainy days      : {int(dim.is_rainy.sum())}")
    print(f"  cold days       : {int(dim.is_cold.sum())}")
    print(f"  temp range      : {dim.temp_mean_c.min():.1f} .. {dim.temp_mean_c.max():.1f} C")
    print(f"  -> {out}")
