"use client";

import { useRef, useState } from "react";

const PAD = { top: 14, right: 14, bottom: 26, left: 46 };
const W = 900;

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
 * lines: [{ key, label, color, dashed?, width? }]
 */
export default function LineChart({ data, lines, height = 340, mini = false }) {
  const ref = useRef(null);
  const [hover, setHover] = useState(null);

  const innerW = W - PAD.left - PAD.right;
  const innerH = height - PAD.top - PAD.bottom;
  const keys = lines.map((l) => l.key);
  const xs = data.map((d) => Date.parse(d.date));
  const xMin = xs[0];
  const xMax = xs[xs.length - 1];

  let yMin = 0;
  let yMax = 0;
  for (const d of data) {
    for (const k of keys) {
      const v = d[k];
      if (v == null) continue;
      if (v < yMin) yMin = v;
      if (v > yMax) yMax = v;
    }
  }
  const pad = (yMax - yMin) * 0.08 || 1;
  yMin -= pad;
  yMax += pad;

  const xScale = (t) => PAD.left + ((t - xMin) / (xMax - xMin || 1)) * innerW;
  const yScale = (v) => PAD.top + innerH - ((v - yMin) / (yMax - yMin || 1)) * innerH;

  const pathFor = (k) => {
    let d = "";
    let started = false;
    data.forEach((row, i) => {
      const v = row[k];
      if (v == null) {
        started = false;
        return;
      }
      d += (started ? " L" : "M") + xScale(xs[i]).toFixed(1) + " " + yScale(v).toFixed(1);
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
    const step = niceStep((yMax - yMin) / 5);
    for (let v = Math.ceil(yMin / step) * step; v <= yMax; v += step) yticks.push(v);
  }

  const zeroY = yScale(0);

  function onMove(e) {
    if (mini) return;
    const rect = ref.current.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * W;
    let best = 0;
    let bd = Infinity;
    xs.forEach((t, i) => {
      const dx = Math.abs(xScale(t) - px);
      if (dx < bd) {
        bd = dx;
        best = i;
      }
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
              <line className="grid" x1={PAD.left} x2={W - PAD.right} y1={yScale(v)} y2={yScale(v)} />
              <text className="ytick" x={PAD.left - 5} y={yScale(v) + 3}>
                {fmt(v)}
              </text>
            </g>
          ))}
        {!mini &&
          years.map((yr, i) => (
            <text key={"x" + i} className="xtick" x={yr.x} y={height - 8}>
              {yr.y}
            </text>
          ))}

        <line className="zero" x1={PAD.left} x2={W - PAD.right} y1={zeroY} y2={zeroY} />

        {lines.map((l) => (
          <path
            key={l.key}
            className="series"
            d={pathFor(l.key)}
            fill="none"
            stroke={l.color}
            strokeWidth={l.width || (mini ? 1.6 : 2.2)}
            strokeDasharray={l.dashed ? "5 4" : ""}
          />
        ))}

        {hover != null && !mini && (
          <g>
            <line className="cursor" x1={xScale(xs[hover])} x2={xScale(xs[hover])} y1={PAD.top} y2={PAD.top + innerH} />
            {lines.map(
              (l) =>
                data[hover][l.key] != null && (
                  <circle key={l.key} cx={xScale(xs[hover])} cy={yScale(data[hover][l.key])} r="3.4" fill={l.color} />
                )
            )}
          </g>
        )}
      </svg>

      {hover != null && !mini && (
        <div className="tooltip">
          <div className="tt-date">{data[hover].date}</div>
          {lines.map(
            (l) =>
              data[hover][l.key] != null && (
                <div key={l.key} className="tt-row">
                  <span className="tt-dot" style={{ background: l.color }} />
                  <span className="tt-label">{l.label}</span>
                  <span className="tt-val">{fmt(data[hover][l.key])}</span>
                </div>
              )
          )}
        </div>
      )}
    </div>
  );
}
