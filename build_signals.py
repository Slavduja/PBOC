#!/usr/bin/env python3
"""
Build the two China-liquidity signals from the scraped operations + the CNCBBS
balance-sheet series extracted from the TradingEconomics SVG.

PATH 1  "OMO fast"     — reverse repo + outright repo + bonds, MLF dropped.
                         Fully captured 2020->now, internally consistent.
                         Role: high-frequency early-warning. Read its TURNS.

PATH 2  "Anchored nowcast" — monthly balance sheet (complete: nets every tool)
                         as the level anchor, plus the daily OMO net flow as the
                         intra-month increment. Equals the true balance sheet at
                         each month boundary, moves daily in between.
                         Role: complete AND daily.

Outputs: output/signal_omo_fast.csv, output/signal_nowcast.csv, output/signals.png
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from pboc_scraper import build_series

# --------------------------------------------------------------------------- #
# Load
# --------------------------------------------------------------------------- #
ops = pd.read_csv("output/operations.csv")
bs = pd.read_csv("output/cncbbs_from_svg.csv", parse_dates=["date"]).set_index("date")
bs_bn = bs["bs_yi"] / 10.0            # 亿元 -> RMB billions (1亿 = 0.1bn)

# =========================================================================== #
# PATH 1 — OMO fast (drop MLF, the only incompletely-captured tool)
# =========================================================================== #
p1_ops = ops[ops["op_type"] != "中期借贷便利"].to_dict("records")
p1 = build_series(p1_ops)
p1.to_csv("output/signal_omo_fast.csv")

# =========================================================================== #
# PATH 2 — Balance-sheet-anchored daily nowcast
#   L(t) = B(most-recent month anchor) + Σ OMO net flow since that anchor
#   -> hits the true monthly balance sheet at each boundary, OMO texture within
# =========================================================================== #
idx = p1.index                                   # daily calendar of the OMO series
# effective anchor value + its date, carried forward each day
grid = bs_bn.reindex(idx.union(bs_bn.index)).sort_index()
anchor_val = grid.ffill().reindex(idx)
anchor_date = (pd.Series(grid.index, index=grid.index)
               .where(grid.notna()).ffill().reindex(idx))
# cumulative OMO net flow since the current anchor (resets at each new anchor)
net = p1["daily_net"]
within = net.groupby(anchor_date.values).cumsum()

# Component 4 — RRR: permanent reserve releases the balance sheet does NOT
# capture (an RRR cut shifts PBoC liabilities, leaving total assets unchanged).
# Its YoY contribution = releases in the trailing 12 months.
rrr = pd.read_csv("rrr_events.csv", parse_dates=["effective_date"])
rrr_ev = rrr.groupby("effective_date")["released_bn"].sum().sort_index()
full = pd.date_range(min(rrr_ev.index.min(), idx.min()), idx.max(), freq="D")
rrr_cum = rrr_ev.reindex(full, fill_value=0.0).cumsum().reindex(idx)

nowcast_level = anchor_val + within + rrr_cum
nowcast = pd.DataFrame({"level": nowcast_level})
nowcast["yoy"] = nowcast["level"] - nowcast["level"].shift(365)
nowcast["yoy_ma50"] = nowcast["yoy"].rolling(50, min_periods=1).mean()
nowcast = nowcast.round(1)
nowcast.to_csv("output/signal_nowcast.csv")

# =========================================================================== #
# Correlations vs the truth (CNCBBS YoY), on overlapping months
# =========================================================================== #
truth = bs_bn - bs_bn.shift(12)                  # monthly balance-sheet YoY (bn)
def corr_vs_truth(daily_yoy):
    m = pd.DataFrame({"s": daily_yoy.resample("MS").last(),
                      "t": truth.resample("MS").last()}).dropna()
    return m["s"].corr(m["t"]), len(m)
c1, n1 = corr_vs_truth(p1["yoy"])
c2, n2 = corr_vs_truth(nowcast["yoy"])

# =========================================================================== #
# Plot
# =========================================================================== #
fig, ax = plt.subplots(3, 1, figsize=(12, 11), sharex=True)

ax[0].bar(bs.index, truth.reindex(bs.index), width=20, color="#e8912d", alpha=0.85)
ax[0].axhline(0, color="#333", lw=0.8)
ax[0].set_title("TRUTH — CNCBBS balance-sheet YoY (≈ Howell). Complete, monthly.", loc="left")
ax[0].set_ylabel("RMB bn"); ax[0].grid(axis="y", alpha=0.25)

ax[1].plot(p1.index, p1["yoy"], color="#f0a860", lw=0.6, alpha=0.5)
ax[1].plot(p1.index, p1["yoy_ma50"], color="#d9701a", lw=2.2)
ax[1].axhline(0, color="#333", lw=0.8)
ax[1].set_title(f"PATH 1 — OMO fast (reverse+outright repo, no MLF). Daily. "
                f"corr vs truth = {c1:.2f}", loc="left")
ax[1].set_ylabel("RMB bn"); ax[1].grid(axis="y", alpha=0.25)

ax[2].bar(bs.index, truth.reindex(bs.index), width=20, color="#e8912d", alpha=0.30)
ax[2].plot(nowcast.index, nowcast["yoy"], color="#1f6f8b", lw=0.7, alpha=0.6)
ax[2].plot(nowcast.index, nowcast["yoy_ma50"], color="#12455a", lw=2.2)
ax[2].axhline(0, color="#333", lw=0.8)
ax[2].set_title(f"PATH 2 — Anchored nowcast (balance sheet + daily OMO + RRR). "
                f"Daily & complete (all 4 components). corr vs truth = {c2:.2f}", loc="left")
ax[2].set_ylabel("RMB bn"); ax[2].grid(axis="y", alpha=0.25)

fig.tight_layout()
fig.savefig("output/signals.png", dpi=130)
print(f"PATH1 corr vs truth = {c1:.3f} (n={n1})")
print(f"PATH2 corr vs truth = {c2:.3f} (n={n2})   [now incl. component 4: RRR]")
print(f"RRR events loaded: {len(rrr)} | trailing-12m RRR release @ latest = "
      f"{(rrr_cum.iloc[-1]-rrr_cum.iloc[-366] if len(rrr_cum)>366 else float('nan')):.0f} bn")
print("latest values (RMB bn):")
print(f"  truth (CNCBBS YoY) : {truth.dropna().iloc[-1]:.0f}  @ {truth.dropna().index[-1].date()}")
print(f"  PATH1 yoy_ma50     : {p1['yoy_ma50'].iloc[-1]:.0f}  @ {p1.index[-1].date()}")
print(f"  PATH2 yoy_ma50     : {nowcast['yoy_ma50'].iloc[-1]:.0f}  @ {nowcast.index[-1].date()}")
print("saved output/signal_omo_fast.csv, output/signal_nowcast.csv, output/signals.png")
