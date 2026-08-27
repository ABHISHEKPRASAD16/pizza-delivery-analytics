"""Check every column that targets an INTEGER type is actually integer-typed.

Parses sql/01_schema.sql for column definitions and compares against the
dtypes _prepare() produces. A float reaching a SMALLINT column is a hard
COPY failure, so this is the check that matters.
"""
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from load_to_postgres import LOAD_ORDER, PROC, _prepare  # noqa: E402

SQL = Path(r"D:\Pizza Analytics\sql\01_schema.sql").read_text(encoding="utf-8")

INT_TYPES = ("SMALLINT", "INTEGER", "BIGINT", "BIGSERIAL")
BOOL_TYPE = "BOOLEAN"


def parse_schema() -> dict[str, dict[str, str]]:
    """table -> {column: TYPE}"""
    out: dict[str, dict[str, str]] = {}
    for m in re.finditer(r"CREATE TABLE (\S+)\s*\((.*?)\n\);", SQL, re.S):
        table, body = m.group(1), m.group(2)
        cols: dict[str, str] = {}
        for line in body.split("\n"):
            line = line.strip().rstrip(",")
            if not line or line.startswith(("--", "UNIQUE", "PRIMARY", "FOREIGN", "CHECK")):
                continue
            parts = line.split()
            if len(parts) >= 2:
                cols[parts[0]] = parts[1].split("(")[0].upper()
        out[table] = cols
    return out


schema = parse_schema()
print(f"parsed {len(schema)} tables from 01_schema.sql\n")

problems = 0
for fname, table in LOAD_ORDER:
    cols = schema.get(table, {})
    df = _prepare(pd.read_parquet(PROC / f"{fname}.parquet"))
    issues = []
    for c in df.columns:
        target = cols.get(c)
        if target is None:
            issues.append(f"{c}: NOT IN SCHEMA")
            continue
        dt = str(df[c].dtype)
        if target in INT_TYPES and not dt.lower().startswith("int"):
            issues.append(f"{c}: {dt} -> {target}")
        if target == BOOL_TYPE and dt not in ("str", "object"):
            issues.append(f"{c}: {dt} -> {target}")
    problems += len(issues)
    status = "OK" if not issues else " | ".join(issues)
    print(f"  {table:<24} {status}")

print(f"\ntype problems: {problems}")
