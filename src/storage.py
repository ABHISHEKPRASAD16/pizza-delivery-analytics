"""Read/write access to staging.daily_entry.

Talks to Supabase when .env is configured. Falls back to a local parquet file
otherwise, so the form is usable (and demoable) before the database exists.
The fallback is seeded from the generated history so the week-on-week
comparison works straight away.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

PROC = Path(__file__).parents[1] / "data" / "processed"
LOCAL_FILE = PROC / "daily_entry_local.parquet"
SEED_FILE = PROC / "daily_entry.parquet"

FIELDS = [
    "business_date", "total_orders", "gross_revenue", "delivery_orders",
    "pickup_orders", "cancelled", "waste_eur", "staff_hours", "driver_hours",
    "promo_active", "promo_note", "is_closed", "complaints", "notes",
    "entered_by",
]


class DailyEntryStore:
    """One interface, two backends."""

    def __init__(self) -> None:
        self.backend = "local"
        self.reason = ""
        self._engine = None
        try:
            from db import engine
            from sqlalchemy import text
            eng = engine()
            with eng.connect() as conn:
                conn.execute(text("SELECT 1"))
            self._engine = eng
            self.backend = "postgres"
        except Exception as exc:                      # noqa: BLE001
            self.reason = f"{type(exc).__name__}: {exc}"
            self._ensure_local()

    # ------------------------------------------------------------ local
    def _ensure_local(self) -> None:
        if LOCAL_FILE.exists():
            return
        PROC.mkdir(parents=True, exist_ok=True)
        seed = (pd.read_parquet(SEED_FILE)[FIELDS]
                if SEED_FILE.exists() else pd.DataFrame(columns=FIELDS))
        seed.to_parquet(LOCAL_FILE, index=False)

    # ------------------------------------------------------------- read
    def load(self) -> pd.DataFrame:
        if self.backend == "postgres":
            # Pass a Connection, not the Engine. pandas 3.x no longer accepts a
            # bare Engine here and falls through to the DBAPI path, which dies
            # with "'Engine' object has no attribute 'cursor'".
            with self._engine.connect() as conn:
                df = pd.read_sql(
                    f"SELECT {', '.join(FIELDS)} FROM staging.daily_entry", conn)
        else:
            df = pd.read_parquet(LOCAL_FILE)
        if len(df):
            df["business_date"] = pd.to_datetime(df["business_date"]).dt.date
        return df.sort_values("business_date").reset_index(drop=True)

    def get(self, day: date) -> dict | None:
        df = self.load()
        hit = df[df.business_date == day]
        return None if hit.empty else hit.iloc[0].to_dict()

    def missing_days(self, back: int = 14) -> list[date]:
        """Recent dates with no entry - gaps break the forecasting.

        The window ends YESTERDAY, not at the newest entry. Ending it at the
        newest entry would make the most important gap - the days since you
        last filled the form - permanently invisible. Today is excluded
        because the shift is not closed yet.
        """
        df = self.load()
        if df.empty:
            return []
        yesterday = date.today() - timedelta(days=1)
        window = pd.date_range(end=yesterday, periods=back, freq="D").date
        have = set(df.business_date)
        first = df.business_date.min()
        return [d for d in window if d not in have and d >= first]

    # ------------------------------------------------------------ write
    def upsert(self, rec: dict) -> str:
        """Insert, or overwrite if that date already exists. Returns the action."""
        existed = self.get(rec["business_date"]) is not None

        if self.backend == "postgres":
            from sqlalchemy import text
            cols = ", ".join(FIELDS)
            params = ", ".join(f":{f}" for f in FIELDS)
            updates = ", ".join(
                f"{f} = EXCLUDED.{f}" for f in FIELDS if f != "business_date")
            sql = text(
                f"INSERT INTO staging.daily_entry ({cols}) VALUES ({params}) "
                f"ON CONFLICT (business_date) DO UPDATE SET {updates}, "
                f"entered_at = NOW()")
            with self._engine.begin() as conn:
                conn.execute(sql, {f: rec.get(f) for f in FIELDS})
        else:
            df = self.load()
            df = df[df.business_date != rec["business_date"]]
            df = pd.concat([df, pd.DataFrame([rec])[FIELDS]], ignore_index=True)
            df.sort_values("business_date").to_parquet(LOCAL_FILE, index=False)

        return "updated" if existed else "saved"
