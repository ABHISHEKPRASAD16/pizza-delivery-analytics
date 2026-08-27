"""Anomaly detection - which days were genuinely abnormal, and in what way.

Output: mart.anomaly_daily

A raw outlier check on revenue just flags every Saturday. The point is to
find days that are odd AFTER accounting for the things we already know:
weekday, month, weather, holidays. What is left over is the surprise.

For each metric we fit a small regression on those known drivers, then
z-score the residual. |z| > 3 is flagged.

The metrics are chosen so that different failure modes show up separately:
  orders        - demand collapse (equipment failure, road closure)
  discount_rate - margin leakage, possible till abuse
  waste_pct     - over-prepping, or a fridge failure
  late_rate     - a driver short, or an oven running slow

This should independently rediscover the two problems seeded in the data:
an oven outage in February and a discount-abuse window in May.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf

sys.path.insert(0, str(Path(__file__).parent))
from ml_common import banner, daily_frame, write_mart  # noqa: E402

warnings.filterwarnings("ignore")

Z_THRESHOLD = 3.0

METRICS = {
    "orders":        "demand",
    "discount_rate": "margin leakage",
    "waste_pct":     "waste",
    "late_rate_pct": "delivery",
}


def prepare(k: pd.DataFrame) -> pd.DataFrame:
    df = k.copy()
    df["discount_rate"] = (df.discount_total / df.gross_revenue * 100).fillna(0)
    df["waste_pct"] = (df.waste_eur / df.gross_revenue * 100).fillna(0)
    df["is_rainy_i"] = df.is_rainy.astype(int)
    df["ph"] = df.is_public_holiday.astype(int)
    df["sh"] = df.is_school_holiday.astype(int)
    return df


def residual_z(df: pd.DataFrame, metric: str) -> pd.Series:
    """Residual from a model of the KNOWN drivers, scaled to a z-score.

    ROBUST regression (Huber), not OLS. With OLS a sustained anomaly - the
    two-week discount-abuse window - drags that month's coefficient upward,
    so afterwards every NORMAL day in the same month looks abnormally low and
    gets flagged. The anomaly contaminates the baseline it is measured
    against. Huber downweights the outliers while fitting, so the baseline
    stays clean and only the genuinely odd days are flagged.

    Scale uses median/MAD for the same reason: a handful of extreme days must
    not inflate the very threshold meant to catch them.
    """
    # Month belongs in the DEMAND model only. Orders genuinely have seasonality
    # (summer dip, winter peak). Discount rate, waste % and late rate are
    # operational ratios with no seasonal cause - weather is already in the
    # formula explicitly. Leaving C(month) in them is actively harmful: a
    # two-week anomaly is ~45% of a month, too large for a robust fit to
    # downweight, so it redefines that month's baseline and every normal day
    # around it then looks anomalous in the opposite direction.
    terms = ["C(day_of_week)", "is_rainy_i", "ph", "sh", "temp_mean_c"]
    if metric == "orders":
        terms.insert(1, "C(month)")
    formula = f"{metric} ~ " + " + ".join(terms)
    fitted = smf.rlm(formula, data=df, M=sm.robust.norms.HuberT()).fit()
    resid = pd.Series(fitted.resid, index=df.index)

    # Scale PER WEEKDAY, not globally. discount_rate is bimodal - Tuesdays run
    # ~24% on the 2-for-1 promo, other days ~0.8% - so the spread of residuals
    # differs hugely by weekday. A single global MAD is set by the tight
    # non-Tuesday cluster, which then reports a Wednesday that moved 0.6
    # percentage points as a 5-sigma event. Scaling within weekday compares
    # each day against days that actually behave like it.
    def scaled(group: pd.Series) -> pd.Series:
        med = np.median(group)
        mad = np.median(np.abs(group - med))
        scale = mad * 1.4826 if mad > 0 else group.std()
        return (group - med) / (scale if scale > 0 else 1.0)

    return resid.groupby(df.day_of_week).transform(scaled)


def main() -> None:
    banner("ANOMALY DETECTION")

    k = daily_frame()
    df = prepare(k)
    print(f"days analysed {len(df):>8,}")
    print(f"threshold     {Z_THRESHOLD:>8.1f} standard deviations from expected\n")

    rows = []
    for metric, label in METRICS.items():
        z = residual_z(df, metric)
        flagged = df.loc[np.abs(z) > Z_THRESHOLD].copy()
        flagged["metric"] = metric
        flagged["category"] = label
        flagged["z_score"] = z[np.abs(z) > Z_THRESHOLD].round(2)
        flagged["actual"] = df.loc[flagged.index, metric].round(2)
        flagged["direction"] = np.where(flagged.z_score > 0, "high", "low")
        rows.append(flagged[["full_date", "day_name", "metric", "category",
                             "actual", "z_score", "direction"]])
        print(f"  {metric:<16}{len(flagged):>3} anomalies")

    out = (pd.concat(rows)
             .sort_values(["full_date", "metric"])
             .reset_index(drop=True))
    out["full_date"] = pd.to_datetime(out.full_date).dt.date
    out.insert(0, "anomaly_key", out.index + 1)

    print(f"\n{len(out)} anomalies total\n")
    print(f"  {'date':<12}{'day':<11}{'metric':<16}{'actual':>9}{'z':>8}  what")
    for r in out.itertuples(index=False):
        print(f"  {r.full_date!s:<12}{r.day_name:<11}{r.metric:<16}"
              f"{r.actual:>9.2f}{r.z_score:>8.1f}  {r.direction} {r.category}")

    write_mart(out, "anomaly_daily")

    # --- did it find what we seeded? ----------------------------------
    dates = pd.to_datetime(out.full_date)
    oven = out[(dates >= "2026-02-11") & (dates <= "2026-02-13")]
    shrink = out[(dates >= "2026-05-04") & (dates <= "2026-05-17")]
    print("\nseeded-problem check (the model was not told about these):")
    print(f"  oven outage 11-13 Feb      {'FOUND' if len(oven) else 'MISSED':>7}"
          f"   {len(oven)} flags")
    print(f"  discount abuse 4-17 May    {'FOUND' if len(shrink) else 'MISSED':>7}"
          f"   {len(shrink)} flags")


if __name__ == "__main__":
    main()
