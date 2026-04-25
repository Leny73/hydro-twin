import { useEffect, useState } from 'react';

/**
 * MapLegend.jsx — Status colour legend + freshness indicator
 * ============================================================
 *
 * Anchored top-left below the topbar. Shows the five alert colour swatches
 * the polygon fills are painted with, plus a relative "Updated X min ago"
 * line derived from the most recent `assessed_at` in the /status response.
 *
 * Stale-state UX: if the freshest snapshot is older than 60 minutes, the
 * timestamp turns yellow and prefixes ⚠️. Re-renders once a minute so the
 * relative time stays accurate without page reload.
 *
 * Props:
 *   lastUpdated  – ISO-8601 timestamp string (newest assessed_at) or null
 *   demoMode     – bool — true when /status returned demo_mode (table down)
 */

const STATUSES = [
  { code: 'SAFE',            label: 'Safe',            color: '#10B981' },
  { code: 'DROUGHT_WATCH',   label: 'Drought Watch',   color: '#F59E0B' },
  { code: 'DROUGHT_WARNING', label: 'Drought Warning', color: '#F97316' },
  { code: 'FLOOD_WATCH',     label: 'Flood Watch',     color: '#3B82F6' },
  { code: 'FLOOD_WARNING',   label: 'Flood Warning',   color: '#EF4444' },
];

const STALE_AFTER_MS = 60 * 60 * 1000; // 1 hour

function formatRelative(timestamp) {
  if (!timestamp) return null;
  const ageMs = Date.now() - new Date(timestamp).getTime();
  if (ageMs < 0)             return 'just now';
  const minutes = Math.floor(ageMs / 60_000);
  if (minutes < 1)           return 'just now';
  if (minutes < 60)          return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24)            return `${hours} h ago`;
  const days = Math.floor(hours / 24);
  return `${days} d ago`;
}

export default function MapLegend({ lastUpdated, demoMode }) {
  // Tick once a minute so "X min ago" stays accurate without a page reload
  const [, force] = useState(0);
  useEffect(() => {
    const id = setInterval(() => force(t => t + 1), 60_000);
    return () => clearInterval(id);
  }, []);

  const ageMs    = lastUpdated ? Date.now() - new Date(lastUpdated).getTime() : null;
  const isStale  = ageMs !== null && ageMs > STALE_AFTER_MS;
  const relative = formatRelative(lastUpdated);

  return (
    <div
      className="absolute z-20 top-14 left-4 mt-2
                 bg-gray-900/85 backdrop-blur-md border border-gray-700
                 rounded-lg p-2.5 select-none
                 w-44"
      aria-label="Status legend"
    >
      <p className="text-[9px] uppercase tracking-widest text-gray-400 mb-1.5">
        Status Legend
      </p>
      <ul className="space-y-1 mb-2">
        {STATUSES.map(s => (
          <li key={s.code} className="flex items-center gap-2">
            <span
              className="w-3 h-3 rounded-sm flex-shrink-0"
              style={{ backgroundColor: s.color }}
              aria-hidden="true"
            />
            <span className="text-[10px] text-gray-200 leading-none">{s.label}</span>
          </li>
        ))}
      </ul>
      <div className="border-t border-gray-700/60 pt-1.5">
        {demoMode ? (
          <p className="text-[9px] text-yellow-400 leading-snug">
            ⚠️ Snapshot unavailable
          </p>
        ) : relative ? (
          <p className={`text-[9px] leading-snug ${isStale ? 'text-yellow-400' : 'text-gray-400'}`}>
            {isStale && '⚠️ '}Updated {relative}
          </p>
        ) : (
          <p className="text-[9px] text-gray-500 leading-snug">
            Awaiting first run…
          </p>
        )}
      </div>
    </div>
  );
}
