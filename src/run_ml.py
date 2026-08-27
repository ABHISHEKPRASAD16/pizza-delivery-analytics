"""Run the whole ML layer and refresh every mart.* table it produces.

    python src/run_ml.py

Order matters only in that basket analysis is the slowest, so it runs last -
nothing here depends on anything else here. Each module can also be run on
its own while iterating.

Intended to run nightly after the ETL, before Power BI refreshes at 06:00.
"""
from __future__ import annotations

import importlib
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ml_common import BACKEND  # noqa: E402

MODULES = [
    ("ml_forecast",  "demand forecast, 14 days"),
    ("ml_customers", "RFM segments + churn risk"),
    ("ml_delivery",  "delivery time drivers + promise times"),
    ("ml_anomaly",   "days that were genuinely abnormal"),
    ("ml_basket",    "what gets ordered together"),
]


def main() -> None:
    print(f"ML layer  ->  {BACKEND}\n")
    results = []
    for name, what in MODULES:
        start = time.time()
        try:
            importlib.import_module(name).main()
            results.append((name, what, "ok", time.time() - start, ""))
        except Exception as exc:                              # noqa: BLE001
            traceback.print_exc()
            results.append((name, what, "FAILED", time.time() - start,
                            f"{type(exc).__name__}: {exc}"))

    print(f"\n{'=' * 62}\nSUMMARY\n{'=' * 62}")
    for name, what, status, secs, err in results:
        print(f"  {status:<7} {name:<14} {secs:>6.1f}s  {what}")
        if err:
            print(f"          {err}")

    failed = [r for r in results if r[2] != "ok"]
    print(f"\n{len(results) - len(failed)}/{len(results)} models succeeded")
    if failed:
        sys.exit(1)
    print("\nmart tables refreshed. Hit Refresh in Power BI to pull them in.")


if __name__ == "__main__":
    main()
