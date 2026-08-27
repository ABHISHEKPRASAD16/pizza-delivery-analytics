"""Deploy the schema to Supabase and bulk-load the generated tables.

Uses COPY FROM STDIN rather than pandas.to_sql - 155k order lines over a
network connection takes minutes with INSERTs and seconds with COPY.

Usage:
    python src/load_to_postgres.py              # schema + all data
    python src/load_to_postgres.py --schema-only
    python src/load_to_postgres.py --verify     # just count rows
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pandas as pd
import psycopg2

sys.path.insert(0, str(Path(__file__).parent))
from db import dsn  # noqa: E402

ROOT = Path(__file__).parents[1]
PROC = ROOT / "data" / "processed"
SCHEMA_SQL = ROOT / "sql" / "01_schema.sql"

# (parquet file, target table) - ordered so foreign keys resolve
LOAD_ORDER = [
    ("dim_date",       "core.dim_date"),
    ("dim_item",       "core.dim_item"),
    ("dim_channel",    "core.dim_channel"),
    ("dim_zone",       "core.dim_zone"),
    ("dim_driver",     "core.dim_driver"),
    ("dim_cost_assumption", "core.dim_cost_assumption"),
    ("dim_customer",   "core.dim_customer"),
    ("fct_order",      "core.fct_order"),
    ("fct_order_item", "core.fct_order_item"),
    ("fct_shift",      "core.fct_shift"),
    ("daily_entry",    "staging.daily_entry"),
]


def deploy_schema(conn) -> None:
    print("deploying schema ...")
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
    conn.commit()
    print("  schemas staging / core / mart created, tables reset")


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    """Make a DataFrame safe for COPY.

    Two things bite here:

    1. A nullable integer column (zone_key, actual_min, ... - null on pickup
       orders) is promoted to float64 by pandas and serialises as "4.0".
       Postgres SMALLINT rejects that outright. Cast any all-integral float
       back to nullable Int64. Safe for NUMERIC targets too, since Postgres
       happily accepts "5" for NUMERIC(10,2).
    2. Booleans serialise as "True"/"False"; use the "t"/"f" Postgres prefers.
    """
    df = df.copy()
    for c in df.columns:
        s = df[c]
        if s.dtype == bool or (s.dtype == object and
                               s.dropna().map(type).eq(bool).all() and s.notna().any()):
            df[c] = s.map({True: "t", False: "f"})
        elif s.dtype == "float64":
            nn = s.dropna()
            if len(nn) and (nn % 1 == 0).all():
                df[c] = s.astype("Int64")
    return df


def copy_table(conn, df: pd.DataFrame, table: str) -> int:
    """Stream a DataFrame into Postgres via COPY."""
    df = _prepare(df)
    buf = io.StringIO()
    df.to_csv(buf, index=False, header=False, na_rep="\\N")
    buf.seek(0)

    cols = ", ".join(f'"{c}"' for c in df.columns)
    with conn.cursor() as cur:
        cur.copy_expert(
            f"COPY {table} ({cols}) FROM STDIN WITH (FORMAT csv, NULL '\\N')", buf)
    conn.commit()
    return len(df)


def load_all(conn) -> None:
    print("\nloading data ...")
    total = 0
    for fname, table in LOAD_ORDER:
        df = pd.read_parquet(PROC / f"{fname}.parquet")
        n = copy_table(conn, df, table)
        total += n
        print(f"  {table:<24} {n:>8,} rows")
    print(f"  {'TOTAL':<24} {total:>8,} rows")


def verify(conn) -> None:
    print("\nverifying ...")
    with conn.cursor() as cur:
        for _, table in LOAD_ORDER:
            cur.execute(f"SELECT count(*) FROM {table}")
            print(f"  {table:<24} {cur.fetchone()[0]:>8,}")
        cur.execute("""
            SELECT round(sum(net_revenue)::numeric, 0),
                   round(avg(gross_amount)::numeric, 2),
                   count(*)
            FROM core.fct_order
        """)
        rev, aov, n = cur.fetchone()
        print(f"\n  net revenue  EUR {rev:>12,.0f}")
        print(f"  avg order    EUR {aov:>12,.2f}")
        print(f"  orders       {n:>16,}")


def main() -> None:
    args = sys.argv[1:]
    conn = psycopg2.connect(dsn())
    try:
        if "--verify" in args:
            verify(conn)
            return
        deploy_schema(conn)
        if "--schema-only" not in args:
            load_all(conn)
            verify(conn)
        print("\nDone. Power BI can now connect to the core.* and mart.* tables.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
