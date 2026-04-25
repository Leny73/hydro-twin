import { useEffect, useMemo, useState } from 'react';
import { fetchRecentPrecipSeries } from '../lib/openmeteo';

/**
 * PrecipitationChart.jsx — 14-day daily precipitation with real axes
 * ====================================================================
 *
 * BF2-4a: replaces the old MetricsSparkline stub with a real chart that
 * fetches OpenMeteo Forecast `past_days=14` for the selected region's
 * centroid and renders proper X-axis (date ticks) + Y-axis (mm scale)
 * inside an SVG. Pure inline SVG, no chart libs.
 *
 * Hover gives the per-day value via an SVG <title> (native browser
 * tooltip — no JS needed).
 *
 * Props:
 *   region  – the currently selected region object. Must expose either
 *             { longitude, latitude } or a `bbox` whose center we use.
 *   accent  – optional hex colour override (defaults to cyan-400)
 */

const VB_W   = 360;
const VB_H   = 140;
const M      = { top: 10, right: 10, bottom: 24, left: 36 };
const PLOT_W = VB_W - M.left - M.right;
const PLOT_H = VB_H - M.top  - M.bottom;
const Y_TICK_COUNT = 4;

function bboxCenter(bbox) {
  if (!Array.isArray(bbox) || bbox.length < 4) return [null, null];
  return [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2];
}

// Round a positive value up to a "nice" axis maximum (1, 2, 5, 10, 20, 50, …)
function niceMax(value) {
  if (!Number.isFinite(value) || value <= 0) return 10;
  const exponent = Math.floor(Math.log10(value));
  const fraction = value / Math.pow(10, exponent);
  const niceFraction = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10;
  return niceFraction * Math.pow(10, exponent);
}

function formatTick(iso) {
  const d = new Date(`${iso}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
}

export default function PrecipitationChart({ region, accent = '#22D3EE' }) {
  const [points, setPoints] = useState(null);
  const [error,  setError]  = useState(null);

  const [lng, lat] = useMemo(() => {
    if (!region) return [null, null];
    if (region.longitude != null && region.latitude != null) {
      return [region.longitude, region.latitude];
    }
    return bboxCenter(region.bbox);
  }, [region]);

  useEffect(() => {
    if (lng == null || lat == null) return;
    let cancelled = false;
    setPoints(null);
    setError(null);
    fetchRecentPrecipSeries({ longitude: lng, latitude: lat, days: 14 })
      .then(p => { if (!cancelled) setPoints(p); })
      .catch(err => {
        console.warn('[HydroTwin] precip fetch failed:', err.message);
        if (!cancelled) setError(err.message);
      });
    return () => { cancelled = true; };
  }, [lng, lat]);

  if (lng == null || lat == null) return null;

  const last  = points?.[points.length - 1]?.value ?? null;
  const total = points ? points.reduce((s, p) => s + p.value, 0) : null;

  return (
    <div>
      <div className="flex items-baseline justify-between gap-2 mb-1.5">
        <p className="text-[10px] uppercase tracking-widest text-gray-400">
          Precipitation · last 14 days
        </p>
        {total != null && (
          <p className="text-[11px] tabular-nums text-gray-300">
            <span className="font-bold" style={{ color: accent }}>
              {total.toFixed(1)} mm
            </span>
            <span className="text-gray-500"> total</span>
          </p>
        )}
      </div>

      <div className="bg-gray-800/60 border border-gray-700/60 rounded-lg p-2">
        {!points && !error && <Skeleton />}
        {error    && <ErrorRow msg={error} />}
        {points   && points.length >= 2 && <Chart points={points} accent={accent} last={last} />}
        {points   && points.length < 2  && <ErrorRow msg="Not enough data points yet." />}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────

function Chart({ points, accent }) {
  const dataMax = Math.max(...points.map(p => p.value));
  const yMax    = niceMax(Math.max(dataMax, 1));   // avoid flat-zero collapse
  const stepX   = PLOT_W / (points.length - 1);

  const xy = points.map((p, i) => {
    const x = M.left + i * stepX;
    const y = M.top + (1 - p.value / yMax) * PLOT_H;
    return [x, y, p];
  });

  const linePath = xy
    .map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`)
    .join(' ');
  const areaPath =
    `${linePath} L${xy[xy.length - 1][0].toFixed(1)},${(M.top + PLOT_H).toFixed(1)} ` +
    `L${xy[0][0].toFixed(1)},${(M.top + PLOT_H).toFixed(1)} Z`;

  // Y ticks: 0, 25%, 50%, 75%, 100%
  const yTicks = Array.from({ length: Y_TICK_COUNT + 1 }, (_, i) => {
    const v = (yMax * i) / Y_TICK_COUNT;
    const y = M.top + (1 - i / Y_TICK_COUNT) * PLOT_H;
    return { v, y };
  });

  // X ticks: first, ~middle, last (3 labels keeps it readable)
  const xTickIdx = points.length >= 5
    ? [0, Math.floor((points.length - 1) / 2), points.length - 1]
    : points.map((_, i) => i);

  return (
    <svg
      viewBox={`0 0 ${VB_W} ${VB_H}`}
      preserveAspectRatio="xMidYMid meet"
      className="w-full h-32 block"
      role="img"
      aria-label={`Precipitation over the last ${points.length} days`}
    >
      {/* Y-axis grid lines + tick labels */}
      {yTicks.map(({ v, y }, i) => (
        <g key={i}>
          <line
            x1={M.left}     x2={VB_W - M.right}
            y1={y.toFixed(1)} y2={y.toFixed(1)}
            stroke="#374151" strokeWidth="1" strokeDasharray="2 4"
            vectorEffect="non-scaling-stroke"
          />
          <text
            x={M.left - 4} y={y + 3}
            textAnchor="end" fontSize="9" fill="#9CA3AF"
          >
            {Math.round(v)}
          </text>
        </g>
      ))}
      {/* Y-axis label */}
      <text
        x={4} y={M.top + 8}
        fontSize="8" fill="#6B7280" letterSpacing="1"
      >
        mm
      </text>

      {/* Area + line */}
      <path d={areaPath}  fill={accent} fillOpacity="0.15" />
      <path
        d={linePath} fill="none" stroke={accent} strokeWidth="2"
        strokeLinecap="round" strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />

      {/* Per-day dots with native tooltip */}
      {xy.map(([x, y, p], i) => (
        <g key={i}>
          <circle
            cx={x.toFixed(1)} cy={y.toFixed(1)}
            r={i === xy.length - 1 ? 3 : 1.8}
            fill={i === xy.length - 1 ? accent : '#22D3EE'}
            fillOpacity={i === xy.length - 1 ? 1 : 0.7}
          >
            <title>{`${formatTick(p.date)} — ${p.value.toFixed(1)} mm`}</title>
          </circle>
        </g>
      ))}

      {/* X-axis baseline */}
      <line
        x1={M.left} x2={VB_W - M.right}
        y1={M.top + PLOT_H} y2={M.top + PLOT_H}
        stroke="#4B5563" strokeWidth="1"
        vectorEffect="non-scaling-stroke"
      />

      {/* X-axis tick labels */}
      {xTickIdx.map(i => (
        <text
          key={i}
          x={(M.left + i * stepX).toFixed(1)}
          y={VB_H - 8}
          fontSize="9" fill="#9CA3AF"
          textAnchor={i === 0 ? 'start' : i === points.length - 1 ? 'end' : 'middle'}
        >
          {formatTick(points[i].date)}
        </text>
      ))}
    </svg>
  );
}

function Skeleton() {
  return (
    <div className="h-32 flex items-center justify-center" aria-busy="true">
      <span className="text-[10px] text-gray-500 tracking-widest uppercase animate-pulse">
        Loading precipitation…
      </span>
    </div>
  );
}

function ErrorRow({ msg }) {
  return (
    <div className="h-32 flex items-center justify-center px-3">
      <span className="text-[10px] text-yellow-500 leading-relaxed text-center">
        ⚠️ {msg}
      </span>
    </div>
  );
}
