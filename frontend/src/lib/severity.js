/**
 * severity.js — Status code metadata + helpers
 * ===============================================
 *
 * The map paints polygons by **status code** (5 codes — preserves the flood
 * vs drought visual signal). Per BF2-6 we use the same 5 codes as the single
 * source of truth across map, legend, top counter, and pill — same names,
 * same colours, same counts.
 *
 *   SAFE              → green
 *   DROUGHT_WATCH     → amber
 *   DROUGHT_WARNING   → orange
 *   FLOOD_WATCH       → blue
 *   FLOOD_WARNING     → red
 *
 * Legacy 4-tier helpers (`severityOf`, `SEVERITY_META`, `severityCounts`)
 * are kept for backwards compat — but new UI should use the status-code
 * helpers exported below.
 */

export const STATUS_ORDER = [
  'SAFE',
  'DROUGHT_WATCH',
  'DROUGHT_WARNING',
  'FLOOD_WATCH',
  'FLOOD_WARNING',
];

export const STATUS_META = {
  SAFE:            { label: 'Safe',            short: 'SAFE',    color: '#10B981', dot: 'bg-emerald-400' },
  DROUGHT_WATCH:   { label: 'Drought Watch',   short: 'WATCH',   color: '#F59E0B', dot: 'bg-yellow-400'  },
  DROUGHT_WARNING: { label: 'Drought Warning', short: 'WARNING', color: '#F97316', dot: 'bg-orange-500'  },
  FLOOD_WATCH:     { label: 'Flood Watch',     short: 'WATCH',   color: '#3B82F6', dot: 'bg-blue-400'    },
  FLOOD_WARNING:   { label: 'Flood Warning',   short: 'WARNING', color: '#EF4444', dot: 'bg-red-500'     },
};

export function statusMeta(status) {
  return STATUS_META[status] ?? { label: '—', short: '—', color: '#94A3B8', dot: 'bg-slate-400' };
}

/**
 * Tally `regionStatuses` into per-status counts.
 * Returns { SAFE: n, DROUGHT_WATCH: n, DROUGHT_WARNING: n, FLOOD_WATCH: n, FLOOD_WARNING: n }.
 */
export function statusCounts(regionStatuses) {
  const counts = { SAFE: 0, DROUGHT_WATCH: 0, DROUGHT_WARNING: 0, FLOOD_WATCH: 0, FLOOD_WARNING: 0 };
  for (const r of regionStatuses ?? []) {
    if (counts[r.status] !== undefined) counts[r.status] += 1;
  }
  return counts;
}

// ─── Legacy 4-tier helpers ──────────────────────────────────────────────────
// Kept so the StatusPill (and any other consumer) doesn't break. New code
// should use STATUS_META / statusCounts above.

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

export function severityCounts(regionStatuses) {
  const counts = { NORMAL: 0, WATCH: 0, WARNING: 0, CRITICAL: 0, INFO: 0 };
  for (const r of regionStatuses ?? []) {
    const tier = severityOf(r.status);
    counts[tier] = (counts[tier] ?? 0) + 1;
  }
  return counts;
}

/**
 * Picks the worst status from a list, ranked by SEVERITY_ORDER
 * (NORMAL < WATCH < WARNING < CRITICAL). Nulls/undefineds skipped. Used to
 * roll an oblast pill up from its own assessment + its children, so the pill
 * never reads "SAFE" while a sub-municipality underneath says "WATCH".
 */
export function worstStatus(statuses) {
  let best = null;
  let bestTier = -1;
  for (const s of statuses ?? []) {
    if (!s) continue;
    const tier = SEVERITY_ORDER.indexOf(severityOf(s));
    if (tier > bestTier) { best = s; bestTier = tier; }
  }
  return best;
}

/** True if a status is more severe than plain "SAFE". */
export function isAlerting(status) {
  return Boolean(status) && severityOf(status) !== 'NORMAL';
}
