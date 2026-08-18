# PBoC Liquidity Index — Methodology & Findings (in detail)

Full technical record of reverse-engineering Michael Howell's "PBoC Net Liquidity
Injection (Change YoY)" chart, the data pipeline built to reconstruct it, why a
pure operation-scrape cannot faithfully replicate it, and the two working signals
we landed on.

---

## 1. What Howell's metric actually is

Howell's chart plots the **year-over-year change in the outstanding stock of
PBoC funding to the banking system**, smoothed with a **50-day moving average**,
in RMB billions. Conceptually it is the high-frequency analogue of the PBoC
balance-sheet line **"Claims on Other Depository Corporations"** — i.e. how much
central-bank credit is outstanding to banks.

Two design choices make it *his*, not a raw feed:

1. **Netting.** Every operation is counted **net of maturities**:
   `Net = new operations − maturing operations`. A ¥900bn MLF with ¥200bn
   maturing is a **+¥700bn** net injection, not +¥900bn. This is the entire
   signal — get it wrong and the series is meaningless.
2. **YoY of the stock.** Daily net flows accumulate into an outstanding *stock*;
   he plots that stock's 1-year change. Algebraically this equals the trailing
   365-day sum of daily net flows.

### The tools that feed it
- 7- and 14-day reverse repos (the daily OMO workhorse)
- Outright reverse repos (买断式逆回购, introduced Oct 2024)
- MLF — Medium-term Lending Facility (net of maturities)
- PSL, SLF
- Outright government-bond purchases/sales (from Aug 2024)
- RRR changes (a cut releases locked reserves = a liquidity add)
- Government / fiscal deposit flows at the PBoC

Practitioners assemble this from **Wind / CEIC / Bloomberg**, because those feeds
carry the **maturity schedule** needed to net — which the free feeds do not.

---

## 2. Our data pipeline (`pboc_scraper.py`)

### 2.1 Source
Primary source, no paid feed: the PBoC website's own announcement channels, all
siblings under 货币政策司 › 公开市场业务
(`/zhengcehuobisi/125207/125213/125431/`):

| Node | Channel | Captures |
|---|---|---|
| `125475` | 公开市场业务交易公告 | Daily reverse repos (+ MLF through 2024) |
| `5492845` | 买断式逆回购业务公告 | Outright reverse repos (Oct 2024+) |
| `5442785` | 国债买卖业务公告 | Outright govt-bond ops (Aug 2024+) |

(`125469` 公开市场业务公告 was tested and **dropped** — it holds *policy notices*,
dealer lists and rule changes, not operation results.)

### 2.2 Discovery / pagination
The site runs the huilan/aisite eportal CMS. Listing pagination is **not** static
`index_N.html`; page N is `{paging-prefix}-{N}.html`, where the prefix is read
from the "下一页" link (`queryArticleByCondition(this,'…/17081-2.html')`). The
scraper fetches page 1, extracts the prefix, then walks pages until a page yields
no detail links. Detail-article ids are 19-digit timestamps on recent pages and
short serials (e.g. `5815859`) on older ones — both accepted.

### 2.3 Parsing (the hard part)
Announcement bodies live in `<div id="zoom">`. Parsing is **HTML-table driven,
header-mapped**, because flattened-text parsing fails on three real-world quirks:

1. **Column-order drift.** The amount column moves across years — early pages use
   `期限 | 操作量 | 操作利率`; later ones `期限 | 操作利率 | 投标量 | 中标量`.
   We map by header name (amount priority: 中标量 > 操作量 > 投标量; tenor: 期限).
2. **Multiple operations per announcement.** A single notice can contain both an
   MLF table *and* a reverse-repo table. We iterate **every** `<table>` and type
   each by the caption immediately preceding it (`MLF操作情况`, `逆回购操作情况`,
   `买断式逆回购操作情况`). Both operations are emitted.
3. **Contaminating notices.** Central-bank-bill issues (央行票据), bill swaps and
   treasury-cash notices leak into the stream — skipped via `SKIP_MARKERS`.

Format variants handled:
- **Table format** (most days): amount + tenor read from the typed table.
- **Inline format** (newest daily + outright/MLF): `开展了630亿元7天期逆回购操作`
  and `开展10000亿元买断式逆回购操作，期限为3个月（91天），到期日为…`.
- **Bond format**: `净买入债券面值1000亿元` → signed, outright (no maturity).
- **Zero-op days**: `逆回购操作量为零` → no injection row (maturity ladder still drains).

### 2.4 Units landmine
All amounts are in **亿元 (100 million RMB)**. `630亿元` = **¥63bn**, not ¥630m.
The auto-translation renders this wrong; the parser hard-codes ×1e8 and reports
everything in RMB **billions**.

### 2.5 Netting & maturity
- **Injection** booked on the operation date.
- **Maturity** booked on the explicit `到期日` when the notice states one
  (outright repos do), otherwise `operation_date + tenor` — deterministic,
  because a 7-day repo injected on T drains on T+7. Tenor parsing prefers explicit
  days (`3个月（91天）` → 91d), else months, else years.
- Outright **bond** purchases have *no* maturity (permanent holdings change).

### 2.6 Series construction (`build_series`)
```
daily_net  = Σ injections(day)  −  Σ maturities(day)
stock      = cumsum(daily_net)                 # outstanding CB funding to banks
yoy        = stock − stock.shift(365)          # Howell's "Change YoY"
yoy_ma50   = yoy.rolling(50).mean()
```
**Truncation:** the series is capped at the last actual announcement date.
Maturities extend into the future (a 3-month repo / 1-year MLF drains months
ahead) but future *injections* are unknown, so projecting past today would fake a
collapse. This was a real bug, now fixed.

### 2.7 Coverage achieved
1,844 announcements scraped, **~1,700 operations**, YoY coverage **2020-05 →
2026-07**. Op mix: reverse repo 1,592 · outright repo 27 · MLF 87 (2019–2024 only).

---

## 3. Why the pure scrape cannot replicate Howell

The reconstructed series matched the balance-sheet truth in 2020–2023 but
**inverted in 2024–2026**. Root cause, proven from the data:

- **PBoC stopped publishing per-operation MLF results in 2025.** Only one 2025
  page mentions MLF, and only in passing (`为对冲MLF到期` — "to offset MLF
  maturities"). MLF moved to monthly aggregate disclosure.
- So the pipeline books the **2024 MLF injections**, drains them at their 1-year
  maturity in **2025**, but never sees the **2025 renewals**. Result: the series
  **troughs in 2025 exactly where the truth peaks.** Correlation vs the balance
  sheet: **−0.20** (near-inverted).
- RRR reserve releases and fiscal-deposit flows are likewise not per-operation on
  pbc.gov.cn. Adding them would not fix the *sign*; the missing 2025 MLF is the
  killer, and that data sits behind Wind/CEIC (paid).

**Validation anchor.** The CNCBBS balance sheet (total assets) was extracted from
a TradingEconomics SVG (126 monthly bars, 2017→2025-11; y-axis 321K–511K 亿元)
by parsing bar geometry and calibrating against the axis labels. Its YoY **peaks
2025-Q3 at +6,360bn**, matching Howell's chart shape almost exactly. This confirms
Howell's metric ≈ CNCBBS Claims-on-ODCs YoY — and that the balance sheet, being
inherently net, already captures every tool.

---

## 4. The two signals (`build_signals.py`)

### PATH 1 — OMO Fast
- **Build:** all scraped ops **except MLF** → net → stock → YoY → 50d MA.
- **Rationale:** MLF is the only incompletely-captured tool; removing it makes the
  series internally consistent. Correlation vs truth **−0.20 → +0.45**.
- **Role:** daily leading edge. Reverse-repo flows move before the monthly balance
  sheet prints. **Read its turns through zero, not its absolute level.**
- **Limit:** a *component* proxy — blind to RRR/fiscal-driven months.
- **File:** `output/signal_omo_fast.csv`.

### PATH 2 — Anchored Nowcast
- **Build:** `L(t) = B(latest monthly balance-sheet anchor) + Σ OMO net flow since
  that anchor`; YoY of `L`, 50d MA. Snaps to the true balance sheet each month
  (which nets *every* tool), rides daily OMO in between.
- **Rationale:** complete like the balance sheet, daily like the scrape. The
  month-boundary "snaps" are informative — a large snap = liquidity OMO didn't
  explain (RRR / fiscal). Correlation vs truth **+0.56**, the best of the three.
- **Role:** primary level + direction signal.
- **Limit — important:** only as fresh as the last balance-sheet print. Our SVG
  ends 2025-11, so the 2026 tail is *stale-anchor drift, not signal* (latest
  −167 is an artifact). In production a monthly CNCBBS refresh re-anchors it and
  the drift resets.
- **File:** `output/signal_nowcast.csv`.

| | Path 1 | Path 2 |
|---|---|---|
| Completeness | reverse+outright repo only | all tools (via anchor) |
| Corr vs truth | +0.45 | +0.56 |
| Freshness | always current | as fresh as last CNCBBS print |
| Use | intra-month tripwire (turns) | dashboard level + direction |

**Combined use:** Path 2 is the dashboard number; Path 1 is the tripwire between
anchors. When Path 1 turns hard, Path 2's next monthly snap tends to confirm.

---

## 5. Reading it for copper / gold

- Rising PBoC net-liquidity YoY = tailwind for industrial metals (China = the
  marginal copper buyer) and, via global liquidity, for gold.
- **Truth (CNCBBS YoY):** peaked 2025-Q3 (+6,360), printed +3,700 by 2025-11 —
  **decelerating** → copper headwind.
- **Path 1 (OMO fast):** re-accelerated into mid-2026 (+4,559, rising).
- **Net read:** mixed — the complete measure was rolling over as of the last
  balance-sheet data, but the high-frequency OMO edge has turned back up. **The
  single most valuable next data point is a CNCBBS refresh past 2025-11** to
  re-anchor Path 2 and resolve the conflict. Bullish copper re-entry trigger
  remains the 50-day MA turning back up through zero on the complete signal.

---

## 6. Files

| File | Purpose |
|---|---|
| `pboc_scraper.py` | Scrape + net + build the OMO series. `--incremental` for daily updates |
| `build_signals.py` | Build Path 1 + Path 2 from `operations.csv` + CNCBBS |
| `plot_compare.py` | OMO-vs-CNCBBS diagnostic |
| `output/operations.csv` | Audit trail, one row per operation |
| `output/pboc_liquidity.csv` | Raw OMO series (incl. MLF, for reference) |
| `output/signal_omo_fast.csv` | **Path 1** |
| `output/signal_nowcast.csv` | **Path 2** |
| `output/cncbbs_from_svg.csv` | Balance-sheet series extracted from the SVG |
| `output/signals.png` | Three-panel comparison |

### To keep it live
- **Daily:** `python pboc_scraper.py --incremental` then `python build_signals.py`.
- **Monthly:** replace `China_Central_Bank_Balance_Sheet.svg` with a fresh export
  (or wire a CNCBBS pull) so Path 2 re-anchors. Re-run `build_signals.py`.
