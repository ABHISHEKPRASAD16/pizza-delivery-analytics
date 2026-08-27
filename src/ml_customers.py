"""Customer segmentation (RFM) and churn prediction.

Outputs: mart.customer_rfm, mart.customer_churn

RFM is descriptive: it buckets customers by how recently, how often and how
much they order. Churn is predictive: it estimates who is about to stop.

AVOIDING THE OBVIOUS LEAK
-------------------------
The naive churn setup - "label = no order in the last 60 days, feature =
days since last order" - is circular. Recency IS the label, so the model
scores 99% and teaches you nothing.

Instead the timeline is split:

    |<------- observation window ------->|<-- outcome window (60d) -->|
     features computed ONLY from here      label: did they order here?

So the model predicts, from behaviour up to a cutoff, whether the customer
came back afterwards. That is the question worth answering, and the accuracy
number means something.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

sys.path.insert(0, str(Path(__file__).parent))
from ml_common import banner, load, write_mart  # noqa: E402

OUTCOME_DAYS = 60


def orders_frame() -> pd.DataFrame:
    o = load("mart.fct_order")[["order_key", "customer_key", "date_key",
                                "gross_amount", "is_delivery"]]
    d = load("mart.dim_date")[["date_key", "full_date"]]
    df = o.merge(d, on="date_key")
    df["full_date"] = pd.to_datetime(df["full_date"])
    return df


# ------------------------------------------------------------------- RFM
def segment(r: int, f: int, m: int) -> str:
    """Plain-language buckets. Deliberately few - an owner will not act on 11."""
    if r >= 4 and f >= 4:
        return "Champion"
    if r >= 3 and f >= 3:
        return "Loyal"
    if r >= 4 and f <= 2:
        return "New / Promising"
    if r <= 2 and f >= 4:
        return "At risk - was valuable"
    if r <= 2 and f >= 2:
        return "Slipping away"
    if r <= 2:
        return "Lost"
    return "Occasional"


def build_rfm(df: pd.DataFrame) -> pd.DataFrame:
    asof = df.full_date.max()
    g = df.groupby("customer_key").agg(
        last_order=("full_date", "max"),
        first_order=("full_date", "min"),
        frequency=("order_key", "count"),
        monetary=("gross_amount", "sum"),
        avg_order_value=("gross_amount", "mean"),
    ).reset_index()
    g["recency_days"] = (asof - g.last_order).dt.days
    g["tenure_days"] = (asof - g.first_order).dt.days

    # quintiles; recency is reversed - fewer days since last order is better
    g["r_score"] = pd.qcut(g.recency_days, 5, labels=[5, 4, 3, 2, 1]).astype(int)
    g["f_score"] = pd.qcut(g.frequency.rank(method="first"), 5,
                           labels=[1, 2, 3, 4, 5]).astype(int)
    g["m_score"] = pd.qcut(g.monetary.rank(method="first"), 5,
                           labels=[1, 2, 3, 4, 5]).astype(int)
    g["rfm_score"] = g.r_score * 100 + g.f_score * 10 + g.m_score
    g["segment"] = [segment(r, f, m)
                    for r, f, m in zip(g.r_score, g.f_score, g.m_score)]

    g["monetary"] = g.monetary.round(2)
    g["avg_order_value"] = g.avg_order_value.round(2)
    g["last_order"] = g.last_order.dt.date
    g["first_order"] = g.first_order.dt.date
    return g[["customer_key", "first_order", "last_order", "recency_days",
              "tenure_days", "frequency", "monetary", "avg_order_value",
              "r_score", "f_score", "m_score", "rfm_score", "segment"]]


# ----------------------------------------------------------------- churn
def build_churn(df: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    cutoff = df.full_date.max() - pd.Timedelta(days=OUTCOME_DAYS)
    obs, out = df[df.full_date <= cutoff], df[df.full_date > cutoff]

    feat = obs.groupby("customer_key").agg(
        frequency=("order_key", "count"),
        monetary=("gross_amount", "sum"),
        avg_order_value=("gross_amount", "mean"),
        last_order=("full_date", "max"),
        first_order=("full_date", "min"),
        delivery_share=("is_delivery", "mean"),
    ).reset_index()
    feat["recency_days"] = (cutoff - feat.last_order).dt.days
    feat["tenure_days"] = (cutoff - feat.first_order).dt.days
    feat["orders_per_month"] = feat.frequency / (feat.tenure_days / 30.0).clip(lower=1)
    feat["returned"] = feat.customer_key.isin(out.customer_key).astype(int)

    X_cols = ["frequency", "monetary", "avg_order_value", "recency_days",
              "tenure_days", "orders_per_month", "delivery_share"]
    X, y = feat[X_cols], 1 - feat.returned          # 1 = churned

    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y)
    model = HistGradientBoostingClassifier(
        max_iter=200, learning_rate=0.08, random_state=42)
    model.fit(X_tr, y_tr)
    auc = roc_auc_score(y_te, model.predict_proba(X_te)[:, 1])

    feat["churn_probability"] = model.predict_proba(X)[:, 1].round(4)
    feat["risk_band"] = pd.cut(
        feat.churn_probability, [-0.01, 0.33, 0.66, 1.01],
        labels=["Low", "Medium", "High"])
    feat["monetary"] = feat.monetary.round(2)
    feat["avg_order_value"] = feat.avg_order_value.round(2)
    feat["delivery_share"] = feat.delivery_share.round(3)
    feat["orders_per_month"] = feat.orders_per_month.round(2)

    cols = ["customer_key", "frequency", "monetary", "avg_order_value",
            "recency_days", "tenure_days", "orders_per_month",
            "churn_probability", "risk_band"]
    return feat[cols], float(auc)


def main() -> None:
    banner("CUSTOMER SEGMENTATION (RFM) + CHURN")

    df = orders_frame()
    print(f"customers    {df.customer_key.nunique():>8,}")
    print(f"orders       {len(df):>8,}")

    rfm = build_rfm(df)
    print("\nRFM segments:")
    s = (rfm.groupby("segment")
            .agg(customers=("customer_key", "count"),
                 revenue=("monetary", "sum"),
                 avg_orders=("frequency", "mean"))
            .sort_values("revenue", ascending=False))
    total = s.revenue.sum()
    print(f"  {'segment':<24}{'customers':>10}{'revenue':>13}{'% rev':>8}{'avg ord':>9}")
    for name, r in s.iterrows():
        print(f"  {name:<24}{r.customers:>10,.0f}{r.revenue:>13,.0f}"
              f"{r.revenue / total:>8.1%}{r.avg_orders:>9.1f}")

    churn, auc = build_churn(df)
    print(f"\nchurn model (predicting the {OUTCOME_DAYS}-day outcome window)")
    print(f"  ROC-AUC      {auc:>8.3f}   (0.5 = coin flip, 1.0 = perfect)")
    print(f"  churn rate   {(churn.churn_probability > 0.5).mean():>8.1%}")
    print("\n  risk bands:")
    for band, n in churn.risk_band.value_counts().sort_index().items():
        val = churn.loc[churn.risk_band == band, "monetary"].sum()
        print(f"    {band:<8} {n:>6,} customers   EUR {val:>10,.0f} historic value")

    write_mart(rfm, "customer_rfm")
    write_mart(churn, "customer_churn")


if __name__ == "__main__":
    main()
