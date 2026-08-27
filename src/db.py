"""Database connection helper.

Credentials are read, in order, from:

  1. Streamlit secrets  - how Streamlit Community Cloud supplies them
  2. environment / .env - how it works locally

Never hardcode them. `.env` and `.streamlit/secrets.toml` are both gitignored;
on Streamlit Cloud you paste the same five keys into Settings -> Secrets.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = Path(__file__).parents[1]
load_dotenv(ROOT / ".env")

REQUIRED = ["PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD"]


def _from_streamlit() -> dict[str, str]:
    """Streamlit secrets, when running inside Streamlit. Empty otherwise.

    Importing streamlit outside a Streamlit process is harmless, but reading
    st.secrets with no secrets file raises - hence the broad catch. This keeps
    the CLI scripts (generate_data, run_ml, ...) working unchanged.
    """
    try:
        import streamlit as st
        return {k: str(st.secrets[k]) for k in REQUIRED if k in st.secrets}
    except Exception:                                         # noqa: BLE001
        return {}


def _cfg() -> dict[str, str]:
    cfg = _from_streamlit()
    for k in REQUIRED:
        if k not in cfg and os.getenv(k):
            cfg[k] = os.environ[k]

    missing = [k for k in REQUIRED if k not in cfg]
    if missing:
        raise RuntimeError(
            f"Missing credentials: {', '.join(missing)}\n"
            f"Locally: copy .env.example to .env and fill it in.\n"
            f"On Streamlit Cloud: app Settings -> Secrets."
        )
    return cfg


def dsn() -> str:
    """libpq connection string, for psycopg2 / COPY."""
    c = _cfg()
    return (f"host={c['PGHOST']} port={c['PGPORT']} dbname={c['PGDATABASE']} "
            f"user={c['PGUSER']} password={c['PGPASSWORD']} sslmode=require")


def engine():
    """SQLAlchemy engine, for pandas read_sql."""
    c = _cfg()
    from urllib.parse import quote_plus
    url = (f"postgresql+psycopg2://{quote_plus(c['PGUSER'])}:{quote_plus(c['PGPASSWORD'])}"
           f"@{c['PGHOST']}:{c['PGPORT']}/{c['PGDATABASE']}?sslmode=require")
    return create_engine(url, pool_pre_ping=True)


def test_connection() -> bool:
    try:
        with engine().connect() as conn:
            v = conn.execute(text("SELECT version()")).scalar()
        print(f"Connected OK\n  {v.split(',')[0]}")
        return True
    except Exception as exc:
        print(f"Connection FAILED\n  {type(exc).__name__}: {exc}")
        return False


if __name__ == "__main__":
    test_connection()
