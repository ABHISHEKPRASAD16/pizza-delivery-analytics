"""Market basket analysis - what gets ordered together.

Output: mart.basket_rules

Business use: design combo deals and upsell prompts from what customers
already do, rather than from what someone in head office guessed.

Reading the numbers:
  support     how often the pair appears, as a share of all orders
  confidence  P(consequent | antecedent) - "of orders with A, how many had B"
  lift        confidence / baseline rate of B. Lift 1.0 means independent;
              lift 2.0 means twice as likely as chance. LIFT IS THE ONE THAT
              MATTERS - high confidence on a very common item (Cola) is
              trivially true and worth nothing.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from mlxtend.frequent_patterns import association_rules, fpgrowth

sys.path.insert(0, str(Path(__file__).parent))
from ml_common import banner, load, write_mart  # noqa: E402

MIN_SUPPORT = 0.01      # pair must appear in at least 1% of orders
MIN_LIFT = 1.05         # discard pairs that are barely better than chance
MAX_RULES = 200


def build_baskets() -> pd.DataFrame:
    """order_key x item_name boolean matrix."""
    items = load("mart.fct_order_item")[["order_key", "item_key"]]
    names = load("mart.dim_item")[["item_key", "item_name", "category"]]
    df = items.merge(names, on="item_key")

    # Collapse pizza sizes: "Pizza Salami" not "Pizza Salami (Familie 40cm)".
    # Nobody designs a combo around a specific size, and splitting by size
    # fragments the support below the threshold.
    basket = (df.assign(present=True)
                .pivot_table(index="order_key", columns="item_name",
                             values="present", aggfunc="max", fill_value=False))
    return basket.astype(bool)


def main() -> None:
    banner("MARKET BASKET ANALYSIS")

    basket = build_baskets()
    print(f"orders        {len(basket):>8,}")
    print(f"distinct items{basket.shape[1]:>8,}")

    freq = fpgrowth(basket, min_support=MIN_SUPPORT, use_colnames=True, max_len=2)
    print(f"itemsets      {len(freq):>8,}  (support >= {MIN_SUPPORT:.0%})")

    rules = association_rules(freq, metric="lift", min_threshold=MIN_LIFT)
    rules = rules[(rules.antecedents.map(len) == 1) &
                  (rules.consequents.map(len) == 1)].copy()

    rules["item_a"] = rules.antecedents.map(lambda s: next(iter(s)))
    rules["item_b"] = rules.consequents.map(lambda s: next(iter(s)))
    rules = rules[[
        "item_a", "item_b", "support", "confidence", "lift"]].copy()
    rules["support"] = rules.support.round(4)
    rules["confidence"] = rules.confidence.round(4)
    rules["lift"] = rules.lift.round(3)
    rules = (rules.sort_values("lift", ascending=False)
                  .head(MAX_RULES).reset_index(drop=True))
    rules.insert(0, "rule_key", rules.index + 1)

    print(f"rules kept    {len(rules):>8,}  (lift >= {MIN_LIFT})\n")
    print("top 12 by lift:")
    print(f"  {'if they order':<26}{'they also order':<26}{'conf':>7}{'lift':>7}")
    for r in rules.head(12).itertuples(index=False):
        print(f"  {r.item_a:<26}{r.item_b:<26}{r.confidence:>7.1%}{r.lift:>7.2f}")

    write_mart(rules, "basket_rules")


if __name__ == "__main__":
    main()
