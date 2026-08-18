#!/usr/bin/env python3
"""
Export per-component liquidity series to JSON for the Next.js dashboard.

Each of Howell's components is computed as its own net-stock YoY (RMB bn):
    reverse_repo, outright_repo, mlf, bonds  -> netted from operations.csv
    rrr                                       -> permanent releases (rrr_events.csv)
Plus cncbbs (balance-sheet YoY, the validation truth).

Because YoY(sum) == sum(YoY), the frontend can add any subset of components by
summing their per-component YoY series — that's what the selection boxes do.

Output: dashboard/public/dashboard_data.json  (weekly, to keep it light)
"""
import json
from pathlib import Path

import pandas as pd
from dateutil.relativedelta import relativedelta

HERE = Path(__file__).resolve().parent
OUT = HERE / "dashboard" / "public"
OUT.mkdir(parents=True, exist_ok=True)

ops = pd.read_csv("output/operations.csv", parse_dates=["date", "maturity"])
END = ops["date"].max()                          # last real announcement (truncate here)


def component_stock(df):
    """Daily outstanding-stock series for one component (inject - maturity ladder)."""
    inj = df.groupby("date")["amount_bn"].sum()
    drn = df.dropna(subset=["maturity"]).groupby("maturity")["amount_bn"].sum()
    idx = pd.date_range(inj.index.min(), END, freq="D")
    net = inj.reindex(idx, fill_value=0.0) - drn.reindex(idx, fill_value=0.0)
    return net.cumsum()


def changes(stock, full_idx):
    """Return (12-month change, 3-month change) of a daily stock series, RMB bn."""
    s = stock.reindex(full_idx).ffill().fillna(0.0)
    return s - s.shift(365), s - s.shift(91)      # ~12m YoY, ~3m ROC


FULL = pd.date_range(ops["date"].min(), END, freq="D")

COMPONENTS = {
    "reverse_repo":  ("逆回购",       "Reverse repo"),
    "outright_repo": ("买断式逆回购",  "Outright reverse repo"),
    "mlf":           ("中期借贷便利",  "MLF"),
    "bonds":         ("国债买卖",      "Govt bond ops"),
}

frame = pd.DataFrame(index=FULL)
for key, (cn, _) in COMPONENTS.items():
    df = ops[ops["op_type"] == cn]
    if len(df):
        yoy_s, roc_s = changes(component_stock(df), FULL)
    else:
        yoy_s = roc_s = pd.Series(0.0, index=FULL)
    frame[key] = yoy_s
    frame[key + "_roc3m"] = roc_s

# RRR — permanent releases; change = releases over the trailing window
rrr = pd.read_csv("rrr_events.csv", parse_dates=["effective_date"])
rrr_ev = rrr.groupby("effective_date")["released_bn"].sum().sort_index()
rrr_full = pd.date_range(min(rrr_ev.index.min(), FULL.min()), END, freq="D")
rrr_stock = rrr_ev.reindex(rrr_full, fill_value=0.0).cumsum()
frame["rrr"], frame["rrr_roc3m"] = changes(rrr_stock, FULL)

# CNCBBS balance-sheet change (the truth) — monthly, interpolated to the daily grid
bs = pd.read_csv("output/cncbbs_from_svg.csv", parse_dates=["date"]).set_index("date")
bs_bn = bs["bs_yi"] / 10.0


def bs_change(periods):
    return (bs_bn - bs_bn.shift(periods)).reindex(FULL.union(bs_bn.index)) \
        .sort_index().interpolate(method="time").reindex(FULL)


frame["cncbbs"] = bs_change(12)          # 12-month
frame["cncbbs_roc3m"] = bs_change(3)     # 3-month

# weekly, rounded, drop the leading year with no YoY
weekly = frame.resample("W-FRI").last().round(0)
weekly = weekly.loc[weekly.index >= "2020-06-01"]

records = [{"date": d.strftime("%Y-%m-%d"),
            **{c: (None if pd.isna(v) else float(v)) for c, v in row.items()}}
           for d, row in weekly.iterrows()]

meta = {
    "components": [
        {"key": "reverse_repo",  "label": "Reverse repo",           "color": "#d9701a",
         "complete": True,  "default": True,
         "note": "Daily OMO workhorse. Netted from operations, 2019→now."},
        {"key": "outright_repo", "label": "Outright reverse repo",  "color": "#1f6f8b",
         "complete": False, "default": True,
         "note": "Oct-2024 tool. Per-op from 2025-06; Oct24–May25 needs CEIC."},
        {"key": "mlf",           "label": "MLF",                    "color": "#7b4fb0",
         "complete": False, "default": True,
         "note": "1-year facility. Per-op 2019→2024-08; disclosure stopped after — needs CEIC."},
        {"key": "bonds",         "label": "Govt bond ops",          "color": "#3f9d52",
         "complete": True,  "default": True,
         "note": "Outright bond purchases/sales (permanent), Aug-2024→now."},
        {"key": "rrr",           "label": "RRR cuts",               "color": "#c0392b",
         "complete": True,  "default": False,
         "note": "Permanent reserve releases (curated, PBoC-stated). Off balance sheet — belongs to the wider index."},
    ],
    "truth": {"key": "cncbbs", "label": "CNCBBS balance-sheet (Howell ≈)", "color": "#111111"},
    "measures": [
        {"key": "yoy", "suffix": "", "label": "12-month (YoY)", "short": "YoY"},
        {"key": "roc3m", "suffix": "_roc3m", "label": "3-month ROC", "short": "3M ROC"},
    ],
    "unit": "RMB bn",
    "asof": END.strftime("%Y-%m-%d"),
}

json.dump({"meta": meta, "series": records},
          open(OUT / "dashboard_data.json", "w"), separators=(",", ":"))
print(f"wrote {OUT/'dashboard_data.json'}  ({len(records)} weekly points, "
      f"{len(meta['components'])} components) asof {meta['asof']}")
