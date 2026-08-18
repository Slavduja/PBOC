#!/usr/bin/env python3
"""
PBoC Net Liquidity Injection scraper  —  Howell-style "Change YoY" series.

Pulls the People's Bank of China open-market-operation announcements from
pbc.gov.cn, nets each operation against its maturity, accumulates the
outstanding stock of central-bank funding to banks, then produces the
year-over-year change with a 50-day moving average.

Channels scraped (siblings under 货币政策司 › 公开市场业务):
    125475   公开市场业务交易公告         daily reverse repos (7/14-day)
    5492845  买断式逆回购业务公告          outright reverse repos (Oct-2024+)
    5442785  国债买卖业务公告             outright govt-bond operations (Aug-2024+)

The netting is the whole signal:  Net = new operations - maturing operations.
Maturities use the announcement's explicit 到期日 when present, otherwise the
operation date + tenor (a 7-day reverse repo injected on T drains on T+7).
No paid maturity feed (Wind/CEIC/Bloomberg) is required.

Parsing is HTML-table driven (header-mapped), because the flattened-text column
order drifts across years (操作量 vs 投标量/中标量) and unrelated central-bank-bill
notices (央行票据) leak into the stream and must be skipped.

Usage
-----
    pip install -r requirements.txt
    python pboc_scraper.py --max-pages 90      # backfill ~to 2020
    python pboc_scraper.py --incremental       # daily update

Outputs (./output):
    operations.csv          audit trail, one row per operation
    pboc_liquidity.csv      date, daily_net, stock, yoy, yoy_ma50   (RMB bn)
    pboc_liquidity_tv.csv   date, yoy_ma50   (TradingView import)
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from dateutil.relativedelta import relativedelta

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
BASE = "https://www.pbc.gov.cn"
PARENT = "/zhengcehuobisi/125207/125213/125431"

# node id -> human name.  All sit under the same PARENT path.
CHANNELS = {
    "125475":  "交易公告(逆回购)",       # daily reverse repos (+ pre-2024 MLF)
    "125469":  "公开市场业务公告(MLF)",  # MLF operations (2024+ moved here)
    "5492845": "买断式逆回购",           # outright reverse repos
    "5442785": "国债买卖",               # outright govt-bond operations
}

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
OUT = HERE / "output"
MANIFEST = CACHE / "manifest.json"

HEADERS = {"User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")}
REQUEST_SLEEP = 0.4
TIMEOUT = 30
RETRIES = 3

YI = 100_000_000          # 1 亿 = 1e8 RMB
RMB_BN = 1e9              # report in RMB billions

# Operation types.  sign: +adds / -drains liquidity.  drains: reverses at maturity.
OP_TYPES = {
    "买断式逆回购": {"sign": +1, "drains": True},   # match before 逆回购 (longer)
    "逆回购":       {"sign": +1, "drains": True},
    "正回购":       {"sign": -1, "drains": True},
    "中期借贷便利": {"sign": +1, "drains": True},   # MLF
    "常备借贷便利": {"sign": +1, "drains": True},   # SLF
    "抵押补充贷款": {"sign": +1, "drains": True},   # PSL
}
# Announcement types we deliberately ignore (not domestic-liquidity injections)
SKIP_MARKERS = ("央行票据", "票据互换", "国库现金")


# --------------------------------------------------------------------------- #
# HTTP with retry + on-disk cache
# --------------------------------------------------------------------------- #
def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def fetch(sess: requests.Session, url: str, cache_key: str | None = None) -> str:
    if cache_key:
        cached = CACHE / cache_key
        if cached.exists():
            return cached.read_text(encoding="utf-8")
    last = None
    for attempt in range(1, RETRIES + 1):
        try:
            r = sess.get(url, timeout=TIMEOUT)
            r.encoding = "utf-8"
            if r.status_code == 200 and r.text:
                if cache_key:
                    (CACHE / cache_key).write_text(r.text, encoding="utf-8")
                time.sleep(REQUEST_SLEEP)
                return r.text
            last = f"HTTP {r.status_code}"
        except requests.RequestException as e:
            last = str(e)
        time.sleep(REQUEST_SLEEP * attempt * 2)
    raise RuntimeError(f"fetch failed {url}: {last}")


# --------------------------------------------------------------------------- #
# Listing discovery (per channel, paging prefix auto-detected)
# --------------------------------------------------------------------------- #
def channel_base(node: str) -> str:
    return f"{BASE}{PARENT}/{node}"


def paging_prefix(list_html: str) -> str | None:
    """Extract the paging file prefix from '下一页' links, e.g. '17081' or 'b0da893b'."""
    m = re.search(r"queryArticleByCondition\(this,'[^']*/(\w+)-\d+\.html'", list_html)
    return m.group(1) if m else None


def detail_links(node: str, list_html: str) -> list[str]:
    rel = re.findall(rf'href="({re.escape(PARENT)}/{node}/\d+/index\.html)"', list_html)
    seen, out = set(), []
    for r in rel:
        if r not in seen:
            seen.add(r)
            out.append(BASE + r)
    return out


def discover(sess: requests.Session, node: str, max_pages: int,
             known: set[str], incremental: bool) -> list[str]:
    cb = channel_base(node)
    urls, seen_ids = [], set()
    first = fetch(sess, f"{cb}/index.html")
    prefix = paging_prefix(first)

    def harvest(html, page):
        new = 0
        for u in detail_links(node, html):
            aid = u.rsplit("/", 2)[-2]
            if aid in seen_ids:
                continue
            seen_ids.add(aid)
            urls.append(u)
            if aid not in known:
                new += 1
        print(f"    [{CHANNELS[node]}] page {page}: {new} new")
        return new

    harvest(first, 1)
    for page in range(2, max_pages + 1):
        if prefix is None:
            break
        try:
            html = fetch(sess, f"{cb}/{prefix}-{page}.html")
        except RuntimeError:
            break
        if not detail_links(node, html):
            break
        new = harvest(html, page)
        if incremental and new == 0:
            print(f"    [{CHANNELS[node]}] incremental: caught up, stop.")
            break
    return urls


# --------------------------------------------------------------------------- #
# Detail parsing (HTML-table driven)
# --------------------------------------------------------------------------- #
DATE_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")
MATURITY_RE = re.compile(r"到期日为(\d{4})年(\d{1,2})月(\d{1,2})日")
# inline op: "开展了630亿元7天期逆回购操作" / "开展10000亿元买断式逆回购操作，期限为3个月"
INLINE_RE = re.compile(r"开展了?([\d,]+(?:\.\d+)?)亿元([^，。,；]*?)操作")
TENOR_CLAUSE_RE = re.compile(r"期限为?(\d+)(天|个月|年)")
BOND_RE = re.compile(r"净(买入|卖出)债券面值([\d,]+(?:\.\d+)?)亿元")

AMOUNT_COLS = ("中标量", "操作量", "投标量", "操作金额", "金额")
TENOR_COLS = ("期限",)


def _to_bn(cell: str) -> float | None:
    m = re.search(r"([\d,]+(?:\.\d+)?)", cell.replace(" ", ""))
    return float(m.group(1).replace(",", "")) * YI / RMB_BN if m else None


def _tenor_delta(cell: str):
    """'7天' / '3个月（91天）' / '1年' -> relativedelta kwargs. Prefer explicit days."""
    d = re.search(r"(\d+)\s*天", cell)
    if d:
        return {"days": int(d.group(1))}
    mo = re.search(r"(\d+)\s*个月", cell)
    if mo:
        return {"months": int(mo.group(1))}
    y = re.search(r"(\d+)\s*年", cell)
    if y:
        return {"years": int(y.group(1))}
    return None


def _type_from_caption(ctx: str) -> str | None:
    """Map a table caption / headline fragment to an op type (specific first)."""
    if "买断式逆回购" in ctx:
        return "买断式逆回购"
    if "MLF" in ctx or "中期借贷便利" in ctx:
        return "中期借贷便利"
    if "逆回购" in ctx:
        return "逆回购"
    if "正回购" in ctx:
        return "正回购"
    if "SLF" in ctx or "常备借贷便利" in ctx:
        return "常备借贷便利"
    if "PSL" in ctx or "抵押补充贷款" in ctx:
        return "抵押补充贷款"
    return None


def _caption_before(tbl) -> str:
    """Reconstruct the text just before a table, through its '操作情况' caption.

    The type word (e.g. 'MLF') can sit in the node *before* the '操作情况' node,
    so we grab one more node after first seeing the caption marker."""
    ctx, seen = "", False
    for s in tbl.find_all_previous(string=True):
        t = s.strip()
        if not t:
            continue
        ctx = t + ctx
        if seen:
            break
        if "操作情况" in ctx:
            seen = True
        if len(ctx) > 60:
            break
    return ctx[-60:]


def _zoom(html: str):
    soup = BeautifulSoup(html, "html.parser")
    z = soup.find(id="zoom") or soup
    return z, z.get_text(" ", strip=True)


def parse_detail(html: str, url: str) -> list[dict]:
    z, text = _zoom(html)

    if any(mk in text for mk in SKIP_MARKERS):
        return []
    dm = DATE_RE.search(text)
    if not dm:
        return []
    op_day = date(int(dm.group(1)), int(dm.group(2)), int(dm.group(3)))

    # govt-bond outright (permanent, no maturity)
    ops: list[dict] = []
    for direction, am in BOND_RE.findall(text):
        bn = _to_bn(am)
        if bn:
            ops.append(_op(op_day, url, "国债买卖", "outright",
                           (+1 if direction == "买入" else -1) * bn, None))
    if ops:
        return ops

    explicit_mat = None
    mm = MATURITY_RE.search(text)
    if mm:
        explicit_mat = date(int(mm.group(1)), int(mm.group(2)), int(mm.group(3)))

    # ---- primary path: iterate every operation table, typed by its caption ----
    for tbl in z.find_all("table"):
        rows = _table_rows(tbl)
        if len(rows) < 2:
            continue
        header = rows[0]
        amt_i = _find_col(header, AMOUNT_COLS)
        ten_i = _find_col(header, TENOR_COLS)
        if amt_i is None or ten_i is None:
            continue
        op_type = _type_from_caption(_caption_before(tbl))
        if op_type is None:
            continue
        meta = OP_TYPES[op_type]
        for r in rows[1:]:
            if max(amt_i, ten_i) >= len(r):
                continue
            bn = _to_bn(r[amt_i])
            td = _tenor_delta(r[ten_i])
            if not bn or bn == 0 or td is None:
                continue
            mat = explicit_mat or (op_day + relativedelta(**td))
            ops.append(_op(op_day, url, op_type, r[ten_i].replace(" ", ""),
                           meta["sign"] * bn, mat if meta["drains"] else None))

    # ---- fallback: inline headline (no operation table) ----
    if not ops:
        clause = TENOR_CLAUSE_RE.search(text)
        clause_td = _tenor_delta("".join(clause.groups())) if clause else None
        for am, mid in INLINE_RE.findall(text):
            op_type = _type_from_caption(mid)
            if op_type is None:
                continue
            meta = OP_TYPES[op_type]
            bn = _to_bn(am)
            if not bn:
                continue
            td = _tenor_delta(mid)
            tenor_label = mid.strip() or "inline"
            if td is None and clause is not None:          # tenor stated after 操作
                td = clause_td
                tenor_label = "".join(clause.groups())     # e.g. "3个月"
            mat = explicit_mat or (op_day + relativedelta(**td) if td else None)
            ops.append(_op(op_day, url, op_type, tenor_label,
                           meta["sign"] * bn, mat if meta["drains"] else None))

    # de-dup identical rows within a page
    uniq, out = set(), []
    for o in ops:
        k = (o["date"], o["op_type"], o["tenor"], o["amount_bn"])
        if k not in uniq:
            uniq.add(k)
            out.append(o)
    return out


def _op(day, url, typ, tenor, bn, maturity):
    return {"date": day.isoformat(), "url": url, "op_type": typ, "tenor": tenor,
            "amount_bn": round(bn, 4),
            "maturity": maturity.isoformat() if maturity else ""}


def _table_rows(table) -> list[list[str]]:
    out = []
    for tr in table.find_all("tr"):
        cells = [re.sub(r"\s+", "", c.get_text()) for c in tr.find_all(["td", "th"])]
        if any(cells):
            out.append(cells)
    return out


def _find_col(header: list[str], names) -> int | None:
    for i, h in enumerate(header):
        if any(n in h for n in names):
            return i
    return None


# --------------------------------------------------------------------------- #
# Series: net flows -> stock -> YoY -> 50d MA
# --------------------------------------------------------------------------- #
def build_series(ops: list[dict]):
    import pandas as pd
    if not ops:
        raise SystemExit("no operations parsed")
    df = pd.DataFrame(ops)
    df["date"] = pd.to_datetime(df["date"])
    df["maturity"] = pd.to_datetime(df["maturity"], errors="coerce")

    inject = df.groupby("date")["amount_bn"].sum()
    drain = (df.dropna(subset=["maturity"]).groupby("maturity")["amount_bn"].sum())

    # Cap at the last actual operation announcement. Maturities extend into the
    # future (a 3-month repo / 1-year MLF drains months ahead), but future
    # injections are unknown — projecting past today would fake a collapse.
    end = inject.index.max()
    idx = pd.date_range(inject.index.min(), end, freq="D")
    net = inject.reindex(idx, fill_value=0.0) - drain.reindex(idx, fill_value=0.0)

    out = pd.DataFrame({"daily_net": net})
    out["stock"] = out["daily_net"].cumsum()
    out["yoy"] = out["stock"] - out["stock"].shift(365)
    out["yoy_ma50"] = out["yoy"].rolling(50, min_periods=1).mean()
    out.index.name = "date"
    return out.round(1)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--max-pages", type=int, default=90,
                    help="listing pages per channel (~90 ≈ back to 2020)")
    ap.add_argument("--incremental", action="store_true")
    args = ap.parse_args()

    CACHE.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    known = set(json.loads(MANIFEST.read_text())) if MANIFEST.exists() else set()
    sess = _session()

    print("Discovering announcement URLs…")
    urls = []
    for node in CHANNELS:
        urls += discover(sess, node, args.max_pages, known, args.incremental)
    print(f"  {len(urls)} announcements to consider\n")

    print("Fetching + parsing…")
    scraped = set(known)
    for i, url in enumerate(urls, 1):
        aid = url.rsplit("/", 2)[-2]
        fetch(sess, url, cache_key=f"{aid}.html")
        scraped.add(aid)
        if i % 100 == 0:
            print(f"  {i}/{len(urls)} fetched")

    # Always rebuild the series from the ENTIRE cache, not just this delta.
    print("Parsing full cache…")
    all_ops, unparsed = [], 0
    for f in CACHE.glob("*.html"):
        ops = parse_detail(f.read_text(encoding="utf-8"), f.name)
        if not ops:
            unparsed += 1
        all_ops.extend(ops)
    MANIFEST.write_text(json.dumps(sorted(scraped)))
    print(f"  {len(all_ops)} operations parsed, {unparsed} announcements with no op "
          f"(zero-volume days, holidays, or skipped CB-bill notices)")

    with (OUT / "operations.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["date", "op_type", "tenor",
                                           "amount_bn", "maturity", "url"])
        w.writeheader()
        for o in sorted(all_ops, key=lambda x: x["date"]):
            w.writerow(o)

    series = build_series(all_ops)
    series.to_csv(OUT / "pboc_liquidity.csv")
    series[["yoy_ma50"]].to_csv(OUT / "pboc_liquidity_tv.csv")

    print(f"\nWrote operations.csv ({len(all_ops)} ops), pboc_liquidity.csv, "
          f"pboc_liquidity_tv.csv")
    valid = series.dropna(subset=["yoy"])
    if len(valid):
        print(f"\nYoY coverage: {valid.index.min().date()} -> {valid.index.max().date()}")
        print("Latest (RMB bn):")
        print(valid[["daily_net", "stock", "yoy", "yoy_ma50"]].tail(5).to_string())


if __name__ == "__main__":
    main()
