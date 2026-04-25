/**
 * MetricsSparkline.jsx — tiny inline-SVG trend chart
 * ===================================================
 *
 * Pure SVG, no chart libraries. Renders a short numeric series as a
 * smooth polyline with a subtle area fill, a faint mid-line for visual
 * reference, and a highlighted endpoint. Sized to fit inside the
 * AlertPanel without breaking either the mobile bottom sheet or the
 * desktop sidebar layout.
 *
 * Props:
 *   data   – number[] (defaults to a stub series; extractor will return
 *            real arrays once historical data is wired through)
 *   label  – short header string (e.g. "Precipitation · 14d (mm)")
 *   accent – hex colour for the line + area fill + endpoint
 *   unit   – optional suffix shown next to the latest value
 */

// TODO: replace stub when extractor returns historical arrays
const STUB_PRECIP_14D = [12, 18, 22, 15, 30, 45, 60, 55, 48, 35, 28, 20, 15, 18];

const VB_W  = 280;  // viewBox width — actual rendered width is responsive via CSS
const VB_H  = 60;   // viewBox height
const PAD_X = 4;    // horizontal padding so endpoints don't touch the edge
const PAD_Y = 6;    // vertical padding so the line doesn't clip on extremes

export default function MetricsSparkline({
  data   = STUB_PRECIP_14D,
  label  = 'Precipitation · last 14 days',
  accent = '#22D3EE',          // cyan-400 — matches existing AlertPanel cyan accents
  unit   = 'mm',
}) {
  if (!data || data.length < 2) return null;

  const min   = Math.min(...data);
  const max   = Math.max(...data);
  const range = max - min || 1;   // guard against a flat series

  const stepX  = (VB_W - 2 * PAD_X) / (data.length - 1);
  const points = data.map((v, i) => {
    const x = PAD_X + i * stepX;
    const y = PAD_Y + (1 - (v - min) / range) * (VB_H - 2 * PAD_Y);
    return [x, y];
  });

  const linePath = points
    .map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`)
    .join(' ');
  const areaPath = `${linePath} L${points[points.length - 1][0].toFixed(1)},${VB_H} L${PAD_X},${VB_H} Z`;

  const last  = data[data.length - 1];
  const prev  = data[data.length - 2];
  const delta = last - prev;
  const trendArrow = delta > 0 ? '▲' : delta < 0 ? '▼' : '·';
  const trendColor = delta > 0 ? 'text-cyan-300' : delta < 0 ? 'text-emerald-300' : 'text-gray-400';

  return (
    <div>
      <div className="flex items-center justify-between text-[10px] uppercase tracking-widest text-gray-400 mb-1.5">
        <span>{label}</span>
        <span className={`${trendColor} normal-case tracking-normal text-[11px] font-bold`}>
          {trendArrow} {last}{unit ? ` ${unit}` : ''}
        </span>
      </div>
      <div className="bg-gray-800/60 border border-gray-700/60 rounded-lg p-2">
        <svg
          viewBox={`0 0 ${VB_W} ${VB_H}`}
          preserveAspectRatio="none"
          className="w-full h-12 block"
          role="img"
          aria-label={`${label} sparkline — latest value ${last}${unit ? ' ' + unit : ''}`}
        >
          {/* Faint mid-line for visual reference */}
          <line
            x1={PAD_X} x2={VB_W - PAD_X}
            y1={VB_H / 2} y2={VB_H / 2}
            stroke="#374151"            /* gray-700 */
            strokeWidth="1"
            strokeDasharray="2 4"
            vectorEffect="non-scaling-stroke"
          />
          {/* Area fill underneath the trend line */}
          <path d={areaPath} fill={accent} fillOpacity="0.15" />
          {/* The trend line itself */}
          <path
            d={linePath}
            fill="none"
            stroke={accent}
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            vectorEffect="non-scaling-stroke"
          />
          {/* Highlight the latest point */}
          <circle
            cx={points[points.length - 1][0]}
            cy={points[points.length - 1][1]}
            r="2.5"
            fill={accent}
          />
        </svg>
      </div>
    </div>
  );
}
