import { statusMeta } from '../lib/severity';

/**
 * StatusPill.jsx — compact in-map status badge
 * ================================================
 *
 * BF1-6 + BF2-6: dot + short label (WATCH / WARNING / SAFE) coloured to
 * match the **polygon underneath** (single vocabulary across map, legend,
 * counter, panel, pill). The accessible label keeps the full status text
 * (e.g. "Flood Watch") so screen readers + the title tooltip aren't
 * collapsed.
 *
 * Click handler is forwarded so tapping the pill triggers an assessment
 * (same path as clicking the polygon fill).
 */

export default function StatusPill({ regionName, status, isActive, onClick }) {
  const meta = statusMeta(status);

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
      aria-label={`${regionName}: ${meta.label}`}
      title={`${regionName} — ${meta.label}`}
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
    </button>
  );
}
