import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Map, { Marker, NavigationControl } from 'react-map-gl';
import 'mapbox-gl/dist/mapbox-gl.css';
import { useDashboardContext } from '../components/Layout';

/**
 * Dams.jsx — Dam Reservoir Monitoring Page
 * ==========================================
 *
 * Shows 3 Bulgarian dams (Arda river) as interactive map markers.
 * Data sourced from:
 *   - Historical XLS fill records (data/dams/)
 *   - Sentinel-2 NDWI via Sentinel Hub Statistical API (when creds present)
 *
 * Alert levels:
 *   WATER_REGIME  – fill below historical 25th-percentile → amber
 *   STABLE        – fill within normal range              → green
 *   OPEN_GATES    – fill above historical 75th-percentile → red
 *
 * Layout:
 *   Left/full  – Mapbox satellite map centered on southern Bulgaria
 *   Right panel – Dam detail (fill bar, sparkline, NDWI, alert reason)
 *                 Appears on marker click; bottom-sheet on mobile
 */

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN ?? '';
const API_ENDPOINT =
  import.meta.env.VITE_API_ENDPOINT ??
  'https://YOUR_API_ID.execute-api.us-east-1.amazonaws.com/prod/assess';
const DAMS_ENDPOINT = API_ENDPOINT.replace(/\/assess$/, '/dams');

// ── Set true to always show demo scenarios (all 3 alert states) ───────────────
// Recommended for hackathon pitch — shows STABLE / WATER_REGIME / OPEN_GATES
// regardless of backend availability.
const FORCE_DEMO = false;

// ── Alert-level display metadata ──────────────────────────────────────────────
const ALERT_META = {
  WATER_REGIME: {
    label:   'Water Regime',
    short:   'LOW',
    color:   '#F59E0B',
    bgClass: 'bg-yellow-950/60 border-yellow-600',
    dotClass:'bg-yellow-400',
    icon:    '🟡',
    desc:    'Water-use restrictions advised. Fill is below safe minimum.',
  },
  STABLE: {
    label:   'Stable',
    short:   'OK',
    color:   '#10B981',
    bgClass: 'bg-emerald-950/60 border-emerald-600',
    dotClass:'bg-emerald-400',
    icon:    '✅',
    desc:    'Reservoir operating within normal limits.',
  },
  OPEN_GATES: {
    label:   'Open Gates',
    short:   'HIGH',
    color:   '#EF4444',
    bgClass: 'bg-red-950/60 border-red-600',
    dotClass:'bg-red-500',
    icon:    '🚨',
    desc:    'Spillway opening recommended. Fill exceeds safety threshold.',
  },
};
const DEFAULT_META = ALERT_META.STABLE;

// ── Demo fallback — one dam per alert level ───────────────────────────────────
// Series shape: fill rises steadily to peak, then drops — makes the sparkline
// visually informative and clearly shows where each dam sits vs the thresholds.
function _makeSeries(baseUrl, peakPct, capacity, len = 90) {
  return Array.from({ length: len }, (_, i) => {
    const t      = i / (len - 1);               // 0 → 1
    const fillPct = baseUrl + (peakPct - baseUrl) * Math.sin(Math.PI * t);
    return {
      date:           new Date(Date.UTC(2017, 3, 1 + i)).toISOString().slice(0, 10),
      fill_pct:       Math.round(fillPct * 10) / 10,
      volume_mln_m3:  Math.round((fillPct / 100) * capacity * 10) / 10,
    };
  });
}

const DEMO_RESPONSE = {
  generated_at: new Date().toISOString(),
  dams: [
    {
      // ✅ STABLE — Кърджали sits comfortably between 25% and 90%
      id: 'kardzhali', name: 'Язовир Кърджали', river: 'Арда',
      lat: 41.6333, lon: 25.3400, capacity_mln_m3: 497.236,
      fill_pct: 62.4, volume_mln_m3: 310.3, data_date: '2017-07-30',
      ndwi: 0.31, ndwi_source: 'sentinel-2', ndwi_threshold_high: 0.45, ndwi_threshold_low: 0.18,
      alert_level: 'STABLE',
      alert_reason: 'Reservoir fill 62.4% is within the normal operating range (25.0%–90.0%). No action required.',
      thresholds: { low: 25.0, high: 90.0, mean: 65.2, min: 48.7, max: 81.7 },
      series: _makeSeries(50, 72, 497.236),
    },
    {
      // 🟡 WATER_REGIME — Ст. Кладенец is critically low after a dry summer
      id: 'studen-kladenets', name: 'Язовир Студен Кладенец', river: 'Арда',
      lat: 41.6122, lon: 25.6405, capacity_mln_m3: 387.772,
      fill_pct: 18.7, volume_mln_m3: 72.5, data_date: '2017-09-15',
      ndwi: 0.09, ndwi_source: 'sentinel-2', ndwi_threshold_high: 0.44, ndwi_threshold_low: 0.19,
      alert_level: 'WATER_REGIME',
      alert_reason: 'Reservoir fill 18.7% is below the low-water threshold (25.0%). Prolonged drought has drawn reserves to a critical level. Water-use restrictions are recommended to preserve minimum operational reserves.',
      thresholds: { low: 25.0, high: 90.0, mean: 68.1, min: 54.3, max: 95.8 },
      series: _makeSeries(72, 22, 387.772),  // peaks high then drains to low
    },
    {
      // 🚨 OPEN_GATES — Ивайловград at 93% after heavy spring snowmelt
      id: 'ivaylovgrad', name: 'Язовир Ивайловград', river: 'Арда',
      lat: 41.5839, lon: 26.1071, capacity_mln_m3: 156.702,
      fill_pct: 93.2, volume_mln_m3: 146.1, data_date: '2017-04-18',
      ndwi: 0.54, ndwi_source: 'sentinel-2', ndwi_threshold_high: 0.46, ndwi_threshold_low: 0.21,
      alert_level: 'OPEN_GATES',
      alert_reason: 'Reservoir fill 93.2% exceeds the 90.0% safety threshold. Rapid snowmelt inflow is driving levels toward the dam crest. Spillway gates should be opened immediately to reduce overtopping risk.',
      thresholds: { low: 25.0, high: 90.0, mean: 71.3, min: 59.6, max: 93.2 },
      series: _makeSeries(58, 93, 156.702),
    },
  ],
};

// ── Fill-level sparkline (SVG) ────────────────────────────────────────────────
const VB_W = 360, VB_H = 110;
const M = { top: 8, right: 8, bottom: 22, left: 34 };
const PLOT_W = VB_W - M.left - M.right;
const PLOT_H = VB_H - M.top  - M.bottom;

function Sparkline({ series, thresholds, accentColor }) {
  if (!series?.length) return null;

  const maxFill = 100;
  const minFill = 0;
  const range   = maxFill - minFill || 1;

  const xScale = (i) => M.left + (i / (series.length - 1)) * PLOT_W;
  const yScale = (v) => M.top  + PLOT_H - ((v - minFill) / range) * PLOT_H;

  const linePath = series
    .map((pt, i) => `${i === 0 ? 'M' : 'L'}${xScale(i).toFixed(1)},${yScale(pt.fill_pct).toFixed(1)}`)
    .join(' ');

  const areaPath = [
    `M${M.left},${M.top + PLOT_H}`,
    ...series.map((pt, i) => `L${xScale(i).toFixed(1)},${yScale(pt.fill_pct).toFixed(1)}`),
    `L${M.left + PLOT_W},${M.top + PLOT_H}Z`,
  ].join(' ');

  const yTicks = [0, 25, 50, 75, 100];

  // Date ticks: first, middle, last
  const dateTicks = [0, Math.floor(series.length / 2), series.length - 1];

  return (
    <svg viewBox={`0 0 ${VB_W} ${VB_H}`} className="w-full" aria-label="Fill level history">
      <defs>
        <linearGradient id="fill-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"   stopColor={accentColor} stopOpacity="0.35" />
          <stop offset="100%" stopColor={accentColor} stopOpacity="0.03" />
        </linearGradient>
      </defs>

      {/* Y-axis grid + labels */}
      {yTicks.map(v => (
        <g key={v}>
          <line
            x1={M.left} y1={yScale(v)} x2={M.left + PLOT_W} y2={yScale(v)}
            stroke="#374151" strokeWidth="0.5" strokeDasharray={v === 0 ? "none" : "3,3"}
          />
          <text x={M.left - 4} y={yScale(v)} textAnchor="end" dominantBaseline="middle"
                fontSize="8" fill="#6B7280">{v}%</text>
        </g>
      ))}

      {/* Threshold bands */}
      {thresholds && (
        <>
          {/* Low threshold line */}
          <line
            x1={M.left} y1={yScale(thresholds.low)} x2={M.left + PLOT_W} y2={yScale(thresholds.low)}
            stroke="#F59E0B" strokeWidth="1" strokeDasharray="5,3" opacity="0.7"
          />
          <text x={M.left + PLOT_W - 2} y={yScale(thresholds.low) - 3}
                textAnchor="end" fontSize="7" fill="#F59E0B">LOW</text>
          {/* High threshold line */}
          <line
            x1={M.left} y1={yScale(thresholds.high)} x2={M.left + PLOT_W} y2={yScale(thresholds.high)}
            stroke="#EF4444" strokeWidth="1" strokeDasharray="5,3" opacity="0.7"
          />
          <text x={M.left + PLOT_W - 2} y={yScale(thresholds.high) - 3}
                textAnchor="end" fontSize="7" fill="#EF4444">HIGH</text>
        </>
      )}

      {/* Area fill */}
      <path d={areaPath} fill="url(#fill-grad)" />

      {/* Line */}
      <path d={linePath} fill="none" stroke={accentColor} strokeWidth="1.5" strokeLinejoin="round" />

      {/* Date ticks */}
      {dateTicks.map(i => {
        const pt = series[i];
        if (!pt) return null;
        const d = new Date(`${pt.date}T00:00:00Z`);
        const label = d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
        return (
          <text key={i} x={xScale(i)} y={M.top + PLOT_H + 14}
                textAnchor="middle" fontSize="7.5" fill="#6B7280">{label}</text>
        );
      })}
    </svg>
  );
}

// ── Dam detail panel ──────────────────────────────────────────────────────────
function DamPanel({ dam, onClose }) {
  const meta = ALERT_META[dam.alert_level] ?? DEFAULT_META;

  return (
    <div
      className="
        absolute bottom-0 left-0 right-0
        sm:bottom-auto sm:top-0 sm:right-0 sm:left-auto sm:w-96
        bg-gray-950/95 backdrop-blur-md border-t sm:border-t-0 sm:border-l border-gray-800
        flex flex-col overflow-hidden z-20
        max-h-[70dvh] sm:max-h-full sm:h-full
      "
      role="complementary"
      aria-label={`Dam details: ${dam.name}`}
    >
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-800 flex-shrink-0">
        <div>
          <p className="text-[9px] uppercase tracking-widest text-gray-500">Dam · {dam.river}</p>
          <h2 className="text-sm font-bold text-white leading-tight">{dam.name}</h2>
        </div>
        <button
          onClick={onClose}
          className="ml-auto p-2 rounded-md text-gray-400 hover:text-white hover:bg-gray-800 min-h-[44px] min-w-[44px] flex items-center justify-center"
          aria-label="Close panel"
        >✕</button>
      </div>

      {/* Scrollable body */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">

        {/* Alert badge */}
        <div className={`rounded-lg border p-3 ${meta.bgClass}`}>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xl" aria-hidden="true">{meta.icon}</span>
            <span className="text-sm font-bold" style={{ color: meta.color }}>{meta.label}</span>
            <span className="ml-auto text-[9px] uppercase tracking-widest text-gray-500">Alert level</span>
          </div>
          <p className="text-xs text-gray-300 leading-relaxed">{dam.alert_reason}</p>
        </div>

        {/* Fill level bar */}
        <div>
          <div className="flex items-end justify-between mb-1">
            <span className="text-[10px] uppercase tracking-widest text-gray-500">Fill level</span>
            <span className="text-2xl font-bold tabular-nums" style={{ color: meta.color }}>
              {dam.fill_pct != null ? `${dam.fill_pct.toFixed(1)}%` : '—'}
            </span>
          </div>
          {dam.fill_pct != null && (
            <div className="h-3 rounded-full bg-gray-800 overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-700"
                style={{
                  width: `${Math.min(100, dam.fill_pct)}%`,
                  background: `linear-gradient(to right, ${meta.color}88, ${meta.color})`,
                }}
              />
            </div>
          )}
          {dam.thresholds && (
            <div className="flex justify-between mt-1">
              <span className="text-[9px] text-yellow-500">Low: {dam.thresholds.low}%</span>
              <span className="text-[9px] text-gray-500">Avg: {dam.thresholds.mean}%</span>
              <span className="text-[9px] text-red-500">High: {dam.thresholds.high}%</span>
            </div>
          )}
        </div>

        {/* Key metrics */}
        <div className="grid grid-cols-2 gap-2">
          <MetricCell label="Volume" value={dam.volume_mln_m3 != null ? `${dam.volume_mln_m3.toFixed(0)} Mm³` : '—'} />
          <MetricCell label="Capacity" value={`${dam.capacity_mln_m3} Mm³`} />
          {dam.ndwi != null && (
            <MetricCell
              label={dam.ndwi_source === 'sentinel-2' ? 'NDWI · Sentinel-2 live' : 'NDWI · est. from fill'}
              value={dam.ndwi.toFixed(3)}
              sub={dam.ndwi > 0.3 ? '↑ large water surface' : dam.ndwi > 0.1 ? '↑ moderate water' : '↓ low water surface'}
            />
          )}
          {dam.data_date && (
            <MetricCell label="Data date" value={dam.data_date} />
          )}
        </div>

        {/* NDWI thresholds */}
        {(dam.ndwi_threshold_high != null || dam.ndwi_threshold_low != null) && (
          <div className="rounded-lg bg-gray-900 border border-gray-800 px-3 py-2">
            <p className="text-[9px] uppercase tracking-widest text-gray-500 mb-2">NDWI Thresholds (from historical data)</p>
            <div className="flex gap-4">
              {dam.ndwi_threshold_low != null && (
                <div>
                  <p className="text-[9px] text-yellow-500">Low</p>
                  <p className="text-sm font-bold text-yellow-300 tabular-nums">{dam.ndwi_threshold_low.toFixed(3)}</p>
                </div>
              )}
              {dam.ndwi_threshold_high != null && (
                <div>
                  <p className="text-[9px] text-red-400">High</p>
                  <p className="text-sm font-bold text-red-300 tabular-nums">{dam.ndwi_threshold_high.toFixed(3)}</p>
                </div>
              )}
              {dam.ndwi != null && (
                <div>
                  <p className="text-[9px] text-cyan-400">Current</p>
                  <p className="text-sm font-bold text-cyan-300 tabular-nums">{dam.ndwi.toFixed(3)}</p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Fill history sparkline */}
        {dam.series?.length > 1 && (
          <div>
            <p className="text-[9px] uppercase tracking-widest text-gray-500 mb-1">Fill history</p>
            <div className="rounded-lg bg-gray-900 border border-gray-800 px-2 py-1">
              <Sparkline series={dam.series} thresholds={dam.thresholds} accentColor={meta.color} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function MetricCell({ label, value, sub }) {
  return (
    <div className="rounded-lg bg-gray-900 border border-gray-800 px-3 py-2">
      <p className="text-[9px] uppercase tracking-widest text-gray-500 leading-none mb-1">{label}</p>
      <p className="text-sm font-bold text-white tabular-nums">{value}</p>
      {sub && <p className="text-[9px] text-gray-400 mt-0.5">{sub}</p>}
    </div>
  );
}

// ── Dam marker ────────────────────────────────────────────────────────────────
function DamMarker({ dam, isActive, onClick }) {
  const meta = ALERT_META[dam.alert_level] ?? DEFAULT_META;
  return (
    <Marker longitude={dam.lon} latitude={dam.lat} anchor="center">
      <button
        type="button"
        onClick={onClick}
        title={`${dam.name} — ${meta.label}${dam.fill_pct != null ? ` (${dam.fill_pct.toFixed(1)}%)` : ''}`}
        className="focus:outline-none min-w-[44px] min-h-[44px] flex items-center justify-center"
        aria-label={`${dam.name}: ${meta.label}`}
      >
        <div
          className={`
            relative flex flex-col items-center
            transition-transform duration-150
            ${isActive ? 'scale-125' : 'hover:scale-110'}
          `}
        >
          {/* Pulsing ring on non-stable */}
          {dam.alert_level !== 'STABLE' && (
            <div
              className="absolute inset-0 rounded-full animate-ping opacity-40"
              style={{ backgroundColor: meta.color }}
            />
          )}
          {/* Marker circle */}
          <div
            className="w-8 h-8 rounded-full border-2 border-white/80 shadow-lg flex items-center justify-center text-base"
            style={{ backgroundColor: meta.color }}
          >
            💧
          </div>
          {/* Fill label bubble */}
          {dam.fill_pct != null && (
            <div
              className="mt-0.5 px-1.5 py-0.5 rounded-sm text-[9px] font-bold text-white shadow-md whitespace-nowrap"
              style={{ backgroundColor: `${meta.color}cc` }}
            >
              {dam.fill_pct.toFixed(0)}%
            </div>
          )}
        </div>
      </button>
    </Marker>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function Dams() {
  const { setPageMeta } = useDashboardContext?.() ?? {};
  const [dams,         setDams]         = useState(null);
  const [loading,      setLoading]      = useState(true);
  const [demoMode,     setDemoMode]     = useState(false);
  const [selectedDam,  setSelectedDam]  = useState(null);
  const mapRef = useRef(null);

  useEffect(() => {
    setPageMeta?.({ title: 'Dam Monitor', subtitle: 'Arda River · Sentinel-2 NDWI + historical fill data' });
  }, [setPageMeta]);

  const fetchDams = useCallback(async () => {
    setLoading(true);
    if (FORCE_DEMO) {
      setDams(DEMO_RESPONSE);
      setDemoMode(true);
      setLoading(false);
      return;
    }
    try {
      const res  = await fetch(DAMS_ENDPOINT, { signal: AbortSignal.timeout(12000) });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setDams(data);
      setDemoMode(false);
    } catch (err) {
      console.warn('[DamMonitor] API unavailable — showing demo data:', err.message);
      setDams(DEMO_RESPONSE);
      setDemoMode(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchDams(); }, [fetchDams]);

  const handleMarkerClick = useCallback((dam) => {
    setSelectedDam(prev => prev?.id === dam.id ? null : dam);
    // Fly map to dam
    mapRef.current?.flyTo({ center: [dam.lon, dam.lat], zoom: 11, duration: 800 });
  }, []);

  const alertCounts = useMemo(() => {
    if (!dams) return {};
    return (dams.dams ?? []).reduce((acc, d) => {
      acc[d.alert_level] = (acc[d.alert_level] ?? 0) + 1;
      return acc;
    }, {});
  }, [dams]);

  return (
    <div className="relative w-full h-full flex flex-col overflow-hidden">

      {/* Summary bar */}
      <div className="flex-shrink-0 bg-gray-950/90 border-b border-gray-800 px-4 py-2 flex items-center gap-4 flex-wrap">
        <span className="text-[10px] uppercase tracking-widest text-gray-500">Dam Status</span>
        {Object.entries(ALERT_META).map(([level, meta]) => {
          const count = alertCounts[level] ?? 0;
          return (
            <div key={level} className="flex items-center gap-1.5">
              <span className={`w-2 h-2 rounded-full ${meta.dotClass}`} />
              <span className="text-xs font-semibold" style={{ color: meta.color }}>{meta.label}</span>
              <span className="text-xs text-gray-400 tabular-nums">{count}</span>
            </div>
          );
        })}
        {dams && (
          <span className="ml-auto text-[9px] text-gray-600">
            {demoMode
              ? '🎬 Demo scenarios — all 3 alert states'
              : `Live · Updated: ${new Date(dams.generated_at).toLocaleTimeString('en-GB')}`}
          </span>
        )}
        <button
          onClick={fetchDams}
          disabled={loading}
          className="ml-1 px-2 py-1 rounded text-[10px] font-semibold text-cyan-400 border border-cyan-800 hover:bg-cyan-950 disabled:opacity-40 min-h-[32px]"
        >
          {loading ? '…' : '↺ Refresh'}
        </button>
      </div>

      {/* Map + panel */}
      <div className="flex-1 relative overflow-hidden">
        {MAPBOX_TOKEN ? (
          <Map
            ref={mapRef}
            mapboxAccessToken={MAPBOX_TOKEN}
            initialViewState={{ longitude: 25.70, latitude: 41.61, zoom: 9.0 }}
            style={{ width: '100%', height: '100%' }}
            mapStyle="mapbox://styles/mapbox/satellite-streets-v12"
            fog={{ color: '#0a0a0a', 'high-color': '#000', 'horizon-blend': 0.02 }}
          >
            <NavigationControl position="top-left" />
            {(dams?.dams ?? []).map(dam => (
              <DamMarker
                key={dam.id}
                dam={dam}
                isActive={selectedDam?.id === dam.id}
                onClick={() => handleMarkerClick(dam)}
              />
            ))}
          </Map>
        ) : (
          /* No-token fallback: simple list */
          <div className="w-full h-full overflow-y-auto p-4 space-y-3">
            <p className="text-xs text-yellow-400 mb-4">
              ⚠ No Mapbox token configured — map hidden. Set <code className="text-cyan-300">VITE_MAPBOX_TOKEN</code> to enable.
            </p>
            {(dams?.dams ?? []).map(dam => {
              const meta = ALERT_META[dam.alert_level] ?? DEFAULT_META;
              return (
                <button
                  key={dam.id}
                  type="button"
                  onClick={() => setSelectedDam(prev => prev?.id === dam.id ? null : dam)}
                  className={`w-full text-left rounded-xl border p-4 transition-colors cursor-pointer
                    ${selectedDam?.id === dam.id ? meta.bgClass : 'bg-gray-900 border-gray-800 hover:border-gray-600'}`}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-lg">{meta.icon}</span>
                    <span className="font-bold text-white text-sm">{dam.name}</span>
                    <span className="ml-auto text-xs font-semibold" style={{ color: meta.color }}>{meta.label}</span>
                  </div>
                  <p className="text-xs text-gray-400">{dam.alert_reason}</p>
                </button>
              );
            })}
          </div>
        )}

        {/* Dam detail panel */}
        {selectedDam && (
          <DamPanel
            dam={selectedDam}
            onClose={() => setSelectedDam(null)}
          />
        )}

        {/* Loading overlay */}
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-gray-950/60 z-30">
            <div className="flex flex-col items-center gap-2">
              <div className="w-8 h-8 rounded-full border-2 border-cyan-400 border-t-transparent animate-spin" />
              <span className="text-xs text-gray-400">Loading dam data…</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
