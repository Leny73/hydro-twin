import { severityOf, SEVERITY_META } from '../lib/severity';

/**
 * StatusPill.jsx — in-map region label with a severity badge
 * ============================================================
 *
 * Replaces the v2 plain text marker. Renders the region name in a dark
 * rounded card with a colored severity tag underneath, matching the v3
 * mockup. Becomes brighter when hovered or selected.
 *
 * Click handler is forwarded so tapping the pill triggers an assessment
 * (same path as clicking the polygon fill underneath).
 */

export default function StatusPill({ regionName, status, isActive, onClick }) {
  const tier = severityOf(status);
  const meta = SEVERITY_META[tier] ?? SEVERITY_META.INFO;

  return (
    <button
      type="button"
      onClick={(e) => { e.stopPropagation(); onClick?.(); }}
      className={`
        pointer-events-auto cursor-pointer select-none
        flex flex-col items-center gap-1
        px-3 py-2 rounded-lg
        bg-gray-950/90 backdrop-blur-sm border
        transition-all duration-150
        ${isActive
          ? 'border-cyan-400 shadow-lg shadow-cyan-500/20 scale-105'
          : 'border-gray-700 hover:border-gray-500'}
      `}
      style={{ minHeight: 44, minWidth: 44 }}
      aria-label={`${regionName}: ${tier}`}
    >
      <div className="flex items-center gap-1.5">
        <span
          className={`w-2 h-2 rounded-full ${meta.dot}`}
          aria-hidden="true"
        />
        <span className="text-[11px] font-bold text-white tracking-wide whitespace-nowrap">
          {regionName}
        </span>
      </div>

      {status ? (
        <span
          className="text-[9px] font-bold tracking-widest uppercase rounded px-1.5 py-0.5"
          style={{
            backgroundColor: `${meta.color}22`,
            color:           meta.color,
            border:          `1px solid ${meta.color}55`,
          }}
        >
          {tier}
        </span>
      ) : (
        <span className="text-[9px] tracking-widest uppercase text-gray-500">
          —
        </span>
      )}
    </button>
  );
}
