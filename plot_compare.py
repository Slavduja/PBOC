#!/usr/bin/env python3
"""Compare the scraped OMO net-liquidity series vs the CNCBBS balance-sheet YoY
(≈ Howell's metric) extracted from the TradingEconomics SVG."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

omo = pd.read_csv("output/pboc_liquidity.csv", parse_dates=["date"], index_col="date")
bs = pd.read_csv("output/cncbbs_from_svg.csv", parse_dates=["date"]).set_index("date")

start = "2020-01-01"
omo = omo.loc[start:]
bs = bs.loc[start:]

# correlation on overlapping month-ends
merged = pd.DataFrame({
    "omo": omo["yoy_ma50"].resample("MS").last(),
    "bs": bs["bs_yoy_bn"].resample("MS").last(),
}).dropna()
corr = merged["omo"].corr(merged["bs"])

fig, ax = plt.subplots(2, 1, figsize=(12, 8), sharex=True,
                       gridspec_kw={"height_ratios": [1, 1]})

# Panel 1: the truth signal ≈ Howell
ax[0].bar(bs.index, bs["bs_yoy_bn"], width=20, color="#e8912d", alpha=0.85,
          label="CNCBBS balance-sheet YoY  (≈ Howell's metric)")
ax[0].axhline(0, color="#333", lw=0.8)
ax[0].set_ylabel("RMB bn")
ax[0].set_title("PBoC balance-sheet YoY  (from your SVG) — this IS Howell's shape: peak 2025-Q3", loc="left")
ax[0].legend(loc="upper left")
ax[0].grid(axis="y", alpha=0.25)

# Panel 2: the daily OMO scrape
ax[1].plot(omo.index, omo["yoy"], color="#f0a860", lw=0.6, alpha=0.6,
           label="OMO net-liquidity YoY (daily)")
ax[1].plot(omo.index, omo["yoy_ma50"], color="#d9701a", lw=2.2,
           label="OMO net-liquidity YoY, 50-day MA")
ax[1].axhline(0, color="#333", lw=0.8)
ax[1].set_ylabel("RMB bn")
ax[1].set_title(f"Scraped OMO series (reverse+outright repo, MLF thru 2024) — "
                f"diverges 2025+ (missing 2025 MLF).  corr vs CNCBBS = {corr:.2f}", loc="left")
ax[1].legend(loc="upper left")
ax[1].grid(axis="y", alpha=0.25)

fig.tight_layout()
fig.savefig("output/compare.png", dpi=130)
print(f"saved output/compare.png | overlap months={len(merged)} corr={corr:.3f}")
