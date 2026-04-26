import { statusMeta } from '../lib/severity';

/**
 * StatusPill.jsx — compact in-map status badge
 * ================================================
 *
 * Dot + short label coloured to match the polygons underneath (single
 * vocabulary across map, legend, counter, panel, pill). The pill is fed
 * the *aggregate* status — max severity of (oblast assessment + its child
 * municipalities) — so it never reads "SAFE" while a sub-municipality
 * underneath says "WATCH".
 *
 * `breakdown` (optional) renders a small "N/total" chip when at least one
 * child municipality is at-or-above WATCH, so the user can see the pill
 * is escalated by stressed children rather than the oblast itself.
 *
 * Click handler is forwarded so tapping the pill triggers an assessment
 * (same path as clicking the polygon fill).
 */

export default function StatusPill({ regionName, status, breakdown, isActive, onClick }) {
  const meta = statusMeta(status);
  const accLabel = breakdown
    ? `${regionName}: ${meta.label} — ${breakdown.count} of ${breakdown.total} municipalities alerting`
    : `${regionName}: ${meta.label}`;

  return (
    <button
      type="button"
      onClick={(e) => { e.stopPropagation(); onClick?.(); }}
      className={`
        pointer-events-auto cursor-pointer select-none
        inline-flex items-center gap-1.5
        px-2 py-1 rounded-md
        bg-gray-950/90 backdrop-blur-sm border
        transition-all duration-150
        ${isActive
          ? 'border-cyan-400 shadow-md shadow-cyan-500/20 scale-105'
          : 'border-gray-700 hover:border-gray-500'}
      `}
      aria-label={accLabel}
      title={accLabel}
    >
      <span
        className={`w-2 h-2 rounded-full ${meta.dot}`}
        aria-hidden="true"
      />
      <span
        className="text-[10px] font-bold tracking-widest uppercase whitespace-nowrap"
        style={{ color: meta.color }}
      >
        {meta.short}
      </span>
      {breakdown && (
        <span
          className="text-[9px] font-bold tabular-nums whitespace-nowrap
                     px-1 py-px rounded-sm"
          style={{
            color:           meta.color,
            backgroundColor: `${meta.color}22`,
            border:          `1px solid ${meta.color}44`,
          }}
          aria-hidden="true"
        >
          {breakdown.count}/{breakdown.total}
        </span>
      )}
    </button>
  );
}
