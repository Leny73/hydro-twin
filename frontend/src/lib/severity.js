/**
 * severity.js — Status-code → severity-tier mapping
 * ====================================================
 *
 * The map paints polygons by **status code** (5 codes — preserves the flood
 * vs drought visual signal). The top-bar severity counter and the legend
 * group those codes into 4 generic alert tiers (matching the v3 mockup):
 *
 *   SAFE              → NORMAL
 *   DROUGHT_WATCH     → WATCH
 *   FLOOD_WATCH       → WATCH
 *   DROUGHT_WARNING   → WARNING
 *   FLOOD_WARNING     → CRITICAL
 *
 * INFO is reserved — no current status maps to it. Kept for future use
 * (data-quality warnings, system events, manual ops broadcasts).
 */

export const STATUS_TO_SEVERITY = {
  SAFE:            'NORMAL',
  DROUGHT_WATCH:   'WATCH',
  FLOOD_WATCH:     'WATCH',
  DROUGHT_WARNING: 'WARNING',
  FLOOD_WARNING:   'CRITICAL',
};

export const SEVERITY_ORDER = ['NORMAL', 'WATCH', 'WARNING', 'CRITICAL', 'INFO'];

export const SEVERITY_META = {
  NORMAL:   { label: 'NORMAL',   color: '#10B981', dot: 'bg-emerald-400' },
  WATCH:    { label: 'WATCH',    color: '#F59E0B', dot: 'bg-yellow-400'  },
  WARNING:  { label: 'WARNING',  color: '#F97316', dot: 'bg-orange-500'  },
  CRITICAL: { label: 'CRITICAL', color: '#EF4444', dot: 'bg-red-500'     },
  INFO:     { label: 'INFO',     color: '#3B82F6', dot: 'bg-blue-400'    },
};

export function severityOf(status) {
  return STATUS_TO_SEVERITY[status] ?? 'INFO';
}

/**
 * Tally `regionStatuses` into per-tier counts.
 * Returns { NORMAL: n, WATCH: n, WARNING: n, CRITICAL: n, INFO: n }.
 */
export function severityCounts(regionStatuses) {
  const counts = { NORMAL: 0, WATCH: 0, WARNING: 0, CRITICAL: 0, INFO: 0 };
  for (const r of regionStatuses ?? []) {
    const tier = severityOf(r.status);
    counts[tier] = (counts[tier] ?? 0) + 1;
  }
  return counts;
}
