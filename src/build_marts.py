"""Rebuild the mart layer that Power BI reads.

Runs sql/02_marts.sql against whichever backend is available:

  * Supabase, if .env is configured  -> the real thing
  * DuckDB over the local Parquet    -> same SQL, no database needed

Keeping one SQL file for both means the local check actually proves the
Postgres run will work, rather than testing a parallel implementation.

Usage:
    python src/build_marts.py            # auto-detect backend
    python src/build_marts.py --local    # force DuckDB
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

ROOT = Path(__file__).parents[1]
PROC = ROOT / "data" / "processed"
MART_SQL = ROOT / "sql" / "02_marts.sql"

CORE_TABLES = [
    "dim_date", "dim_item", "dim_channel", "dim_zone", "dim_driver",
    "dim_customer", "fct_order", "fct_order_item", "fct_shift",
    "dim_cost_assumption",
]

MART_TABLES = [
    "dim_date", "dim_item", "dim_zone", "dim_channel", "dim_driver",
    "dim_customer", "fct_order", "fct_order_item", "kpi_daily", "kpi_zone",
    "kpi_item", "kpi_channel_daily", "dim_cost_assumption",
    "daily_entry", "daily_actuals",
]


# ---------------------------------------------------------------- postgres
def run_postgres() -> bool:
    try:
        import psycopg2
        from db import dsn
        conn = psycopg2.connect(dsn())
    except Exception as exc:                                  # noqa: BLE001
        print(f"  Postgres unavailable ({type(exc).__name__}), falling back.")
        return False

    print("backend: Supabase Postgres")
    with conn, conn.cursor() as cur:
        cur.execute(MART_SQL.read_text(encoding="utf-8"))
        print("\nmart tables built:")
        for t in MART_TABLES:
            cur.execute(f"SELECT count(*) FROM mart.{t}")
            print(f"  mart.{t:<20} {cur.fetchone()[0]:>9,} rows")
    conn.close()
    return True


# ------------------------------------------------------------------ duckdb
def run_duckdb() -> None:
    import duckdb

    print("backend: DuckDB over local Parquet (no database configured)")
    con = duckdb.connect()
    con.execute("CREATE SCHEMA IF NOT EXISTS core")
    for t in CORE_TABLES:
        path = (PROC / f"{t}.parquet").as_posix()
        con.execute(f"CREATE VIEW core.{t} AS SELECT * FROM read_parquet('{path}')")

    con.execute(MART_SQL.read_text(encoding="utf-8"))

    out = PROC / "mart"
    out.mkdir(exist_ok=True)
    print("\nmart tables built:")
    for t in MART_TABLES:
        n = con.execute(f"SELECT count(*) FROM mart.{t}").fetchone()[0]
        con.execute(
            f"COPY mart.{t} TO '{(out / f'{t}.parquet').as_posix()}' (FORMAT parquet)")
        print(f"  mart.{t:<20} {n:>9,} rows")
    con.close()
    print(f"\nwritten to {out}")


def main() -> None:
    force_local = "--local" in sys.argv
    if force_local or not run_postgres():
        run_duckdb()


if __name__ == "__main__":
    main()
