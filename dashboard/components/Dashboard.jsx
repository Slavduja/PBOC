"use client";

import { useEffect, useMemo, useState } from "react";
import LineChart from "./LineChart";

function lastNonNull(series, key) {
  for (let i = series.length - 1; i >= 0; i--) {
    if (series[i][key] != null) return series[i][key];
  }
  return null;
}
function fmtBn(v) {
  if (v == null) return "—";
  const s = v >= 0 ? "+" : "−";
  return s + Math.abs(Math.round(v)).toLocaleString();
}

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [sel, setSel] = useState(null);
  const [showTruth, setShowTruth] = useState(true);
  const [measure, setMeasure] = useState("yoy"); // "yoy" | "roc3m"
  const [overlay, setOverlay] = useState("none"); // "none" | "sp500" | "btcusd"
  const [refreshing, setRefreshing] = useState(false);
  const [status, setStatus] = useState(null); // { ok, text }

  const sfx = measure === "roc3m" ? "_roc3m" : "";
  const BASE = process.env.NEXT_PUBLIC_BASE_PATH || "";
  const IS_STATIC = process.env.NEXT_PUBLIC_STATIC === "1";

  // Load (or reload) the series JSON; preserve the current selection.
  async function loadData() {
    const r = await fetch(BASE + "/dashboard_data.json?t=" + Date.now(), { cache: "no-store" });
    const d = await r.json();
    setData(d);
    setSel((prev) => {
      if (prev) return prev;
      const init = {};
      d.meta.components.forEach((c) => (init[c.key] = c.default));
      return init;
    });
    return d;
  }

  useEffect(() => {
    loadData();
  }, []);

  async function handleRefresh() {
    if (refreshing) return;
    setRefreshing(true);
    setStatus({ ok: true, text: "Scraping PBoC + rebuilding…" });
    try {
      const r = await fetch("/api/refresh", { method: "POST" });
      const res = await r.json();
      if (!r.ok || !res.ok) throw new Error(res.error || "refresh failed");
      const d = await loadData();
      setStatus({ ok: true, text: "Updated to " + d.meta.asof });
    } catch (e) {
      setStatus({ ok: false, text: "Update failed — " + String(e.message).slice(0, 120) });
    } finally {
      setRefreshing(false);
    }
  }

  const combined = useMemo(() => {
    if (!data || !sel) return [];
    return data.series.map((row) => {
      let s = 0;
      let any = false;
      data.meta.components.forEach((c) => {
        const k = c.key + sfx;
        if (sel[c.key] && row[k] != null) {
          s += row[k];
          any = true;
        }
      });
      return {
        date: row.date,
        index: any ? s : null,
        cncbbs: row["cncbbs" + sfx],
        sp500: row.sp500 ?? null,
        btcusd: row.btcusd ?? null,
      };
    });
  }, [data, sel, sfx]);

  if (!data || !sel) return <div className="loading">Loading PBoC liquidity data…</div>;

  const { meta, series } = data;
  const nSel = Object.values(sel).filter(Boolean).length;
  const measures = meta.measures || [{ key: "yoy", suffix: "", short: "YoY" }];
  const measureShort = (measures.find((m) => m.key === measure) || measures[0]).short;

  const markets = meta.markets || [];
  const indexLines = [{ key: "index", label: "Composed index", color: "#111827", width: 2.6 }];
  if (showTruth)
    indexLines.push({
      key: "cncbbs",
      label: meta.truth.label + " · " + measureShort,
      color: "#c9974a",
      dashed: true,
      width: 2,
    });
  const overlayMkt = markets.find((m) => m.key === overlay);
  if (overlayMkt)
    indexLines.push({
      key: overlayMkt.key,
      label: overlayMkt.label,
      color: overlayMkt.color,
      width: 2,
      axis: "right",
    });

  const latestIndex = lastNonNull(combined, "index");
  const latestTruth = lastNonNull(combined, "cncbbs");

  return (
    <div className="wrap">
      <div className="header">
        <div className="header-main">
          <h1>PBoC Net Liquidity Injection — Component Dashboard</h1>
          <div className="sub">
            Reconstruction of Michael Howell&rsquo;s metric ·{" "}
            {measure === "roc3m" ? "3-month change" : "12-month (YoY) change"}, {meta.unit} ·{" "}
            <span className="asof">as of {meta.asof}</span>
          </div>
        </div>
        <div className="header-actions">
          <div className="segmented" role="group" aria-label="Measure window">
            {measures.map((m) => (
              <button
                key={m.key}
                className={"seg" + (measure === m.key ? " active" : "")}
                onClick={() => setMeasure(m.key)}
                title={m.label}
              >
                {m.short}
              </button>
            ))}
          </div>
          {!IS_STATIC && (
            <button className="refresh-btn" onClick={handleRefresh} disabled={refreshing}>
              <span className={"spinner" + (refreshing ? " spin" : "")} aria-hidden />
              {refreshing ? "Updating…" : "Refresh data"}
            </button>
          )}
          {!IS_STATIC && status && (
            <div className={"refresh-status " + (status.ok ? "ok" : "err")}>{status.text}</div>
          )}
          {IS_STATIC && <div className="refresh-status ok">snapshot · rebuild to update</div>}
        </div>
      </div>

      <div className="section-title">Components — tick to include in the composed index</div>
      <div className="grid">
        {meta.components.map((c) => {
          const on = sel[c.key];
          const latest = lastNonNull(series, c.key + sfx);
          return (
            <div key={c.key} className={"card " + (on ? "on" : "off")}>
              <div className="card-head">
                <span className="swatch" style={{ background: c.color }} />
                <span className="card-title">{c.label}</span>
                <span className={"badge " + (c.complete ? "ok" : "partial")}>
                  {c.complete ? "complete" : "partial"}
                </span>
              </div>
              <div className={"card-latest " + (latest >= 0 ? "pos" : "neg")}>
                {fmtBn(latest)} <small>bn {measureShort}</small>
              </div>
              <LineChart
                data={series}
                lines={[{ key: c.key + sfx, label: c.label, color: c.color }]}
                height={90}
                mini
              />
              <div className="card-note">{c.note}</div>
              <label className="chk">
                <input type="checkbox" checked={on} onChange={() => setSel({ ...sel, [c.key]: !on })} />
                Include in index
              </label>
            </div>
          );
        })}
      </div>

      <div className="section-title">Composed index</div>
      <div className="panel">
        <div className="panel-head">
          <h2>
            Composed index <span style={{ color: "var(--muted)", fontWeight: 400 }}>({nSel} components)</span>
          </h2>
          <div className="panel-latest">
            latest <b>{fmtBn(latestIndex)}</b> bn
            {showTruth && (
              <>
                {"  ·  "}truth <b>{fmtBn(latestTruth)}</b> bn
              </>
            )}
          </div>
          <div className="controls">
            <label className="overlay-select">
              Overlay market
              <select value={overlay} onChange={(e) => setOverlay(e.target.value)}>
                <option value="none">None</option>
                {markets.map((m) => (
                  <option key={m.key} value={m.key}>{m.label}</option>
                ))}
              </select>
            </label>
            <label className="chk">
              <input type="checkbox" checked={showTruth} onChange={() => setShowTruth(!showTruth)} />
              Balance-sheet truth
            </label>
          </div>
        </div>

        <div className="legend">
          {indexLines.map((l) => (
            <span key={l.key}>
              <span className="ln" style={{ background: l.color, opacity: l.dashed ? 0.7 : 1 }} />
              {l.label}
            </span>
          ))}
        </div>

        <LineChart data={combined} lines={indexLines} height={360} />

        <div className="footnote">
          The composed index sums the YoY contribution of each ticked component (YoY of a sum equals the sum of
          YoYs). The dashed line is the CNCBBS balance-sheet YoY — the validation anchor, ≈ Howell&rsquo;s chart.
          Components marked <b>partial</b> have a known data gap (see the note on the card) and understate their
          contribution in the most recent months until filled from CEIC.
        </div>
      </div>
    </div>
  );
}
