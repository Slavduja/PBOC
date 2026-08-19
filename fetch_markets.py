#!/usr/bin/env python3
"""
Fetch market overlays (BTCUSD, S&P 500) for the dashboard, keyless and resilient.

- BTCUSD  : Coinbase daily candles (paginated). Reliable everywhere.
- S&P 500 : Yahoo Finance chart API, with a FRED CSV fallback. These are
            occasionally IP-throttled from some networks (e.g. sandboxes) but work
            fine from GitHub Actions runners.

Writes output/markets.csv  (date, sp500, btcusd) — daily.
Each source is best-effort: if one fails, existing values are preserved so a
transient outage never wipes the series.
"""
from __future__ import annotations

import io
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"
OUT.mkdir(exist_ok=True)
CSV = OUT / "markets.csv"

START = "2019-05-01"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}


def fetch_btc() -> pd.Series | None:
    """Coinbase daily close, paginated 250-day windows."""
    try:
        start = datetime.fromisoformat(START).replace(tzinfo=timezone.utc)
        end = datetime.now(timezone.utc)
        rows = {}
        cur = start
        while cur < end:
            hi = min(cur + pd.Timedelta(days=250), end)
            url = ("https://api.exchange.coinbase.com/products/BTC-USD/candles"
                   f"?granularity=86400&start={cur.isoformat()}&end={hi.isoformat()}")
            r = requests.get(url, headers=UA, timeout=30)
            r.raise_for_status()
            for t, lo, high, op, close, vol in r.json():
                d = datetime.fromtimestamp(t, tz=timezone.utc).date()
                rows[d] = close
            cur = hi
            time.sleep(0.3)
        s = pd.Series(rows).sort_index()
        s.index = pd.to_datetime(s.index)
        return s.rename("btcusd")
    except Exception as e:  # noqa: BLE001
        print(f"  BTC fetch failed: {e}")
        return None


def fetch_sp500() -> pd.Series | None:
    """yfinance (does Yahoo's cookie/crumb handshake + retries), fall back to FRED CSV."""
    # 1) yfinance — same method as macrosimple_engine/providers/yahoo.py.
    #    A raw GET to Yahoo's API gets 429'd; yfinance handles the crumb dance.
    try:
        import yfinance as yf  # lazy import
        for tk in ("^GSPC", "SPY"):
            df = yf.download(tk, start=START, auto_adjust=True, progress=False, threads=False)
            if df is not None and len(df):
                c = df["Close"]
                c = c.iloc[:, 0] if hasattr(c, "columns") else c  # unwrap single-ticker MultiIndex
                c.index = pd.to_datetime(c.index)
                return c.rename("sp500").dropna()
    except Exception as e:  # noqa: BLE001
        print(f"  SP500 via yfinance failed ({e}); trying FRED…")
    # 2) FRED fallback
    try:
        r = requests.get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=SP500",
                         headers=UA, timeout=30)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text))
        df.columns = ["date", "sp500"]
        df["date"] = pd.to_datetime(df["date"])
        df["sp500"] = pd.to_numeric(df["sp500"], errors="coerce")
        return df.dropna().set_index("date")["sp500"]
    except Exception as e:  # noqa: BLE001
        print(f"  SP500 via FRED failed: {e}")
        return None


def main() -> None:
    existing = None
    if CSV.exists():
        existing = pd.read_csv(CSV, parse_dates=["date"]).set_index("date")

    cols = {}
    print("Fetching BTCUSD (Coinbase)…")
    btc = fetch_btc()
    if btc is not None:
        cols["btcusd"] = btc
        print(f"  BTC ok: {len(btc)} days, last {btc.index[-1].date()} = {btc.iloc[-1]:.0f}")
    print("Fetching S&P 500 (Yahoo→FRED)…")
    spx = fetch_sp500()
    if spx is not None:
        cols["sp500"] = spx
        print(f"  SP500 ok: {len(spx)} days, last {spx.index[-1].date()} = {spx.iloc[-1]:.0f}")

    if not cols and existing is None:
        raise SystemExit("no market data fetched and no existing file — aborting")

    fresh = pd.DataFrame(cols) if cols else pd.DataFrame()
    # merge: prefer fresh, keep existing columns/rows we couldn't refetch
    if existing is not None:
        merged = existing.copy()
        for c in fresh.columns:
            merged[c] = fresh[c].reindex(merged.index.union(fresh.index)).sort_index()
        merged = fresh.combine_first(existing) if not fresh.empty else existing
    else:
        merged = fresh
    merged = merged.sort_index()
    merged.index.name = "date"
    merged.to_csv(CSV)
    print(f"wrote {CSV} ({len(merged)} rows, cols: {list(merged.columns)})")


if __name__ == "__main__":
    main()
