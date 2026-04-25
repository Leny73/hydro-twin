import { SEVERITY_ORDER, SEVERITY_META, severityCounts } from '../lib/severity';

/**
 * SeverityCounter.jsx — top-bar "Open alerts by severity" pill
 * ============================================================
 *
 * Tallies the current `regionStatuses` snapshot into the 5 severity tiers
 * (NORMAL / WATCH / WARNING / CRITICAL / INFO) and renders one colored
 * dot + count per tier, matching the v3 mockup.
 *
 * Reads from the same data already fetched by Overview — no extra request.
 */

export default function SeverityCounter({ regionStatuses }) {
  const counts = severityCounts(regionStatuses);

  return (
    <div className="flex items-center gap-3 text-xs">
      <span className="text-gray-400 uppercase tracking-widest text-[10px] hidden md:inline">
        Open alerts by severity
      </span>
      <div className="flex items-center gap-2.5">
        {SEVERITY_ORDER.map(tier => {
          const meta = SEVERITY_META[tier];
          const n    = counts[tier] ?? 0;
          return (
            <div key={tier} className="flex items-center gap-1.5">
              <span
                className={`w-2 h-2 rounded-full ${meta.dot}`}
                aria-hidden="true"
              />
              <span className="text-gray-300 font-semibold">{meta.label}</span>
              <span className="text-white font-bold tabular-nums">{n}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
