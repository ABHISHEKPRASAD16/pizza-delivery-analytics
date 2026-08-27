"""Shared plumbing for the ML layer.

Every model reads from the warehouse and writes its output back as a
`mart.*` table, so Power BI picks the results up on the next Refresh with no
report changes. Same dual backend as build_marts.py: Supabase when .env is
configured, local Parquet otherwise.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

ROOT = Path(__file__).parents[1]
PROC = ROOT / "data" / "processed"
MART_DIR = PROC / "mart"


def _engine():
    """SQLAlchemy engine, or None when no database is configured."""
    try:
        from sqlalchemy import text
        from db import engine
        eng = engine()
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        return eng
    except Exception:                                        # noqa: BLE001
        return None


ENGINE = _engine()
BACKEND = "postgres" if ENGINE is not None else "local"


def load(table: str) -> pd.DataFrame:
    """Read a warehouse table. Accepts 'core.fct_order' or 'mart.kpi_daily'."""
    schema, _, name = table.partition(".")
    if ENGINE is not None:
        with ENGINE.connect() as conn:
            return pd.read_sql(f"SELECT * FROM {schema}.{name}", conn)

    # local fallback: mart tables live in data/processed/mart, core in processed
    path = (MART_DIR if schema == "mart" else PROC) / f"{name}.parquet"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run generate_data.py and build_marts.py --local first.")
    return pd.read_parquet(path)


def write_mart(df: pd.DataFrame, name: str) -> None:
    """Replace mart.<name> with df."""
    if ENGINE is not None:
        from sqlalchemy import text
        with ENGINE.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS mart.{name}"))
        with ENGINE.begin() as conn:
            df.to_sql(name, conn, schema="mart", if_exists="append", index=False)
    else:
        MART_DIR.mkdir(parents=True, exist_ok=True)
        df.to_parquet(MART_DIR / f"{name}.parquet", index=False)
    print(f"  mart.{name:<24} {len(df):>7,} rows")


def daily_frame() -> pd.DataFrame:
    """One row per day with orders, revenue and the weather/calendar drivers.

    This is the training frame for the forecast and anomaly models.
    """
    k = load("mart.kpi_daily")
    k["full_date"] = pd.to_datetime(k["full_date"])
    return k.sort_values("full_date").reset_index(drop=True)


def banner(title: str) -> None:
    print(f"\n{'=' * 62}\n{title}\n{'=' * 62}")
