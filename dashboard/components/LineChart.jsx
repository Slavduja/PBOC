"use client";

import { useRef, useState } from "react";

const W = 900;
const PAD_L = 46;
const PAD_T = 14;
const PAD_B = 26;

function niceStep(x) {
  if (x <= 0) return 1;
  const p = Math.pow(10, Math.floor(Math.log10(x)));
  const n = x / p;
  return (n >= 5 ? 5 : n >= 2 ? 2 : 1) * p;
}
function fmt(v) {
  const a = Math.abs(v);
  if (a >= 1000) return (v / 1000).toFixed(a >= 10000 ? 0 : 1) + "k";
  return Math.round(v).toString();
}

/**
 * data:  [{ date: "YYYY-MM-DD", <key>: number|null, ... }]
 * lines: [{ key, label, color, dashed?, width?, axis? }]  axis:"right" -> secondary scale
 */
export default function LineChart({ data, lines, height = 340, mini = false }) {
  const ref = useRef(null);
  const [hover, setHover] = useState(null);

  const left = lines.filter((l) => l.axis !== "right");
  const right = lines.filter((l) => l.axis === "right");
  const hasRight = right.length > 0 && !mini;
  const padR = hasRight ? 52 : 14;

  const innerW = W - PAD_L - padR;
  const innerH = height - PAD_T - PAD_B;
  const xs = data.map((d) => Date.parse(d.date));
  const xMin = xs[0];
  const xMax = xs[xs.length - 1];

  function extent(ls, forceZero) {
    let lo = forceZero ? 0 : Infinity;
    let hi = forceZero ? 0 : -Infinity;
    for (const d of data)
      for (const l of ls) {
        const v = d[l.key];
        if (v == null) continue;
        if (v < lo) lo = v;
        if (v > hi) hi = v;
      }
    if (!isFinite(lo)) { lo = 0; hi = 1; }
    const pad = (hi - lo) * 0.08 || 1;
    return [lo - pad, hi + pad];
  }

  const [lMin, lMax] = extent(left, true);
  const [rMin, rMax] = extent(right, false);

  const xScale = (t) => PAD_L + ((t - xMin) / (xMax - xMin || 1)) * innerW;
  const yL = (v) => PAD_T + innerH - ((v - lMin) / (lMax - lMin || 1)) * innerH;
  const yR = (v) => PAD_T + innerH - ((v - rMin) / (rMax - rMin || 1)) * innerH;
  const scaleFor = (l) => (l.axis === "right" ? yR : yL);

  const pathFor = (l) => {
    const sc = scaleFor(l);
    let d = "";
    let started = false;
    data.forEach((row, i) => {
      const v = row[l.key];
      if (v == null) { started = false; return; }
      d += (started ? " L" : "M") + xScale(xs[i]).toFixed(1) + " " + sc(v).toFixed(1);
      started = true;
    });
    return d;
  };

  const years = [];
  if (!mini) {
    const y0 = new Date(xMin).getUTCFullYear();
    const y1 = new Date(xMax).getUTCFullYear();
    for (let y = y0; y <= y1; y++) years.push({ y, x: xScale(Date.parse(y + "-01-01")) });
  }

  const yticks = [];
  if (!mini) {
    const step = niceStep((lMax - lMin) / 5);
    for (let v = Math.ceil(lMin / step) * step; v <= lMax; v += step) yticks.push(v);
  }
  const rticks = [];
  if (hasRight) {
    const step = niceStep((rMax - rMin) / 4);
    for (let v = Math.ceil(rMin / step) * step; v <= rMax; v += step) rticks.push(v);
  }

  const zeroY = yL(0);

  function onMove(e) {
    if (mini) return;
    const rect = ref.current.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * W;
    let best = 0;
    let bd = Infinity;
    xs.forEach((t, i) => {
      const dx = Math.abs(xScale(t) - px);
      if (dx < bd) { bd = dx; best = i; }
    });
    setHover(best);
  }

  return (
    <div className="chart-wrap">
      <svg
        ref={ref}
        viewBox={`0 0 ${W} ${height}`}
        className="chart"
        preserveAspectRatio="none"
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
      >
        {!mini &&
          yticks.map((v, i) => (
            <g key={"y" + i}>
              <line className="grid" x1={PAD_L} x2={W - padR} y1={yL(v)} y2={yL(v)} />
              <text className="ytick" x={PAD_L - 5} y={yL(v) + 3}>{fmt(v)}</text>
            </g>
          ))}
        {hasRight &&
          rticks.map((v, i) => (
            <text key={"r" + i} className="ytick rtick" x={W - padR + 5} y={yR(v) + 3}
                  style={{ textAnchor: "start", fill: right[0].color }}>
              {fmt(v)}
            </text>
          ))}
        {!mini &&
          years.map((yr, i) => (
            <text key={"x" + i} className="xtick" x={yr.x} y={height - 8}>{yr.y}</text>
          ))}

        <line className="zero" x1={PAD_L} x2={W - padR} y1={zeroY} y2={zeroY} />

        {lines.map((l) => (
          <path
            key={l.key}
            className="series"
            d={pathFor(l)}
            fill="none"
            stroke={l.color}
            strokeWidth={l.width || (mini ? 1.6 : 2.2)}
            strokeDasharray={l.dashed ? "5 4" : ""}
            opacity={l.axis === "right" ? 0.9 : 1}
          />
        ))}

        {hover != null && !mini && (
          <g>
            <line className="cursor" x1={xScale(xs[hover])} x2={xScale(xs[hover])} y1={PAD_T} y2={PAD_T + innerH} />
            {lines.map((l) =>
              data[hover][l.key] != null ? (
                <circle key={l.key} cx={xScale(xs[hover])} cy={scaleFor(l)(data[hover][l.key])} r="3.4" fill={l.color} />
              ) : null
            )}
          </g>
        )}
      </svg>

      {hover != null && !mini && (
        <div className="tooltip">
          <div className="tt-date">{data[hover].date}</div>
          {lines.map((l) =>
            data[hover][l.key] != null ? (
              <div key={l.key} className="tt-row">
                <span className="tt-dot" style={{ background: l.color }} />
                <span className="tt-label">{l.label}</span>
                <span className="tt-val">{fmt(data[hover][l.key])}</span>
              </div>
            ) : null
          )}
        </div>
      )}
    </div>
  );
}
