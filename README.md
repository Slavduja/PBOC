# PBoC Net Liquidity Injection — Howell-style tracker

Reconstructs Michael Howell's "PBoC Net Liquidity Injection (Change YoY)" series
from primary-source data: the People's Bank of China daily open-market-operation
announcements (公开市场业务交易公告) on pbc.gov.cn.

## The concept

- **Net = new operations − maturing operations.** The netting *is* the signal.
  A ¥900bn injection with ¥200bn maturing is a **+¥700bn** net add, not +¥900bn.
- Daily net flows accumulate into an **outstanding stock** of central-bank
  funding to banks — the high-frequency analogue of the PBoC balance sheet's
  *Claims on Other Depository Corporations* line.
- Howell plots the **year-over-year change** of that stock, smoothed with a
  **50-day moving average**.

Maturities are reconstructed **deterministically from each operation's tenor**
(a 7-day reverse repo injected on day T drains on day T+7), so no paid
maturity-schedule feed (Wind / CEIC / Bloomberg) is needed.

## Usage

```bash
pip install -r requirements.txt

# Full historical backfill (~95 pages ≈ back to 2020, ~1,900 announcements)
python pboc_scraper.py --max-pages 95

# Daily update — fetch only new announcements, stop at first already-cached page
python pboc_scraper.py --incremental
```

Raw HTML is cached under `./cache/` (keyed by announcement id) so re-runs never
re-fetch. A `manifest.json` tracks scraped ids for incremental mode.

## Outputs (`./output/`)

| File | Contents |
|---|---|
| `operations.csv` | One row per parsed operation — audit trail (date, type, tenor, ¥bn, maturity, url) |
| `pboc_liquidity.csv` | `date, daily_net, stock, yoy, yoy_ma50` — all in **RMB billions** |
| `pboc_liquidity_tv.csv` | `date, yoy_ma50` — minimal file for TradingView CSV import |

## TradingView

TradingView cannot net (its feeds carry gross operation size, not the maturity
schedule), so build the series here and **import `pboc_liquidity_tv.csv`** as a
custom symbol, then overlay copper / gold. Validate the shape against
`ECONOMICS:CNCBBS` (Claims on ODCs YoY, monthly) as a ground-truth anchor.

## Reading the signal

- **Rising** net-liquidity YoY = tailwind for industrial metals (China is the
  marginal copper buyer) and, via global liquidity, for gold.
- The **bullish copper re-entry trigger** is the 50-day MA turning back up
  through zero — the China impulse re-accelerating.

## Known limitations / TODO

- **Op-type coverage.** This scrapes the daily 交易公告 channel (module `17081`).
  It captures reverse repos, outright reverse repos (`买断式逆回购`), MLF, SLF,
  PSL and outright govt-bond operations *when they appear in this stream*. If
  MLF / outright-repo results are published on a separate PBoC channel, add that
  channel's node id + module id (`CHANNEL` / `MODULE_ID` in `pboc_scraper.py`)
  and merge. Check `operations.csv`'s op-type distribution to confirm coverage.
- **Not modelled:** RRR cuts (reserve release), fiscal/government-deposit flows.
  These are monthly and belong to a separate layer; add them for full fidelity
  against Howell's levels. The reverse-repo/MLF stock is the high-frequency core.
- **Maturity on non-business days:** tenor is added as a calendar offset; PBoC
  in practice rolls a weekend maturity to the next business day. The daily
  reindex + 50-day MA absorb this; it does not affect the YoY shape.
- **Pre-2020 announcements** use an older URL id format; discovery stops when a
  listing page yields no modern (19-digit id) detail links.

## Data source

People's Bank of China — 货币政策司 › 公开市场业务 › 公开市场业务交易公告
`https://www.pbc.gov.cn/zhengcehuobisi/125207/125213/125431/125475/index.html`
