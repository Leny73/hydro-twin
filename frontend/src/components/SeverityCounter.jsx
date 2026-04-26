import { STATUS_ORDER, STATUS_META, statusCounts } from '../lib/severity';

/**
 * SeverityCounter.jsx — top-bar "Open alerts by status" pill
 * ============================================================
 *
 * BF2-6: tally uses the same 5 status codes as the map + legend (single
 * source of truth). Names and colors mirror MapLegend exactly.
 *
 * Responsive collapse:
 *   ≥ md  : full labels    →  🟢 Safe 1 · 🟡 Drought Watch 0 · …
 *   < md  : numbers only   →  🟢 1 · 🟡 0 · 🟠 1 · 🔵 0 · 🔴 0
 */

export default function SeverityCounter({ regionStatuses }) {
  const counts = statusCounts(regionStatuses);

  return (
    <div className="flex items-center gap-2 sm:gap-3 text-xs">
      <span className="text-gray-400 uppercase tracking-widest text-[10px] hidden xl:inline">
        Open alerts by status
      </span>
      <div className="flex items-center gap-2 sm:gap-3 flex-wrap justify-end">
        {STATUS_ORDER.map(code => {
          const meta = STATUS_META[code];
          const n    = counts[code] ?? 0;
          return (
            <div
              key={code}
              className="flex items-center gap-1.5 flex-shrink-0"
              title={`${meta.label}: ${n}`}
            >
              <span
                className={`w-2 h-2 rounded-full ${meta.dot}`}
                aria-hidden="true"
              />
              <span className="text-gray-300 font-semibold hidden md:inline">
                {meta.label}
              </span>
              <span
                className="font-bold tabular-nums"
                style={{ color: n > 0 ? meta.color : '#9CA3AF' }}
              >
                {n}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
