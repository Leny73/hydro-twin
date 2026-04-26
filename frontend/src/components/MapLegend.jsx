import { useEffect, useState } from 'react';
import { Layers, ChevronUp, AlertTriangle } from 'lucide-react';

/**
 * MapLegend.jsx — Status colour legend + freshness indicator
 * ============================================================
 *
 * Anchored top-left below the topbar. Shows the five alert colour swatches
 * the polygon fills are painted with, plus a relative "Updated X min ago"
 * line derived from the most recent `assessed_at` in the /status response.
 *
 * Defaults to open on every breakpoint; user can collapse to a small chip
 * via the chevron toggle (BF1-2). When live data is missing we no longer
 * render an "Awaiting first run…" line — the sidebar's freshness widget
 * already carries that info.
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
  const [open, setOpen] = useState(true);

  // Tick once a minute so "X min ago" stays accurate without a page reload
  const [, force] = useState(0);
  useEffect(() => {
    const id = setInterval(() => force(t => t + 1), 60_000);
    return () => clearInterval(id);
  }, []);

  const ageMs    = lastUpdated ? Date.now() - new Date(lastUpdated).getTime() : null;
  const isStale  = ageMs !== null && ageMs > STALE_AFTER_MS;
  const relative = formatRelative(lastUpdated);

  // Collapsed chip — opens legend on click
  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Show status legend"
        aria-expanded="false"
        className="absolute z-20 top-2 left-4
                   w-11 h-11 flex items-center justify-center
                   bg-gray-900/85 backdrop-blur-md border border-gray-700
                   rounded-lg cursor-pointer
                   hover:border-gray-500 transition-colors"
      >
        <Layers className="w-5 h-5 text-gray-300" aria-hidden="true" />
      </button>
    );
  }

  return (
    <div
      className="absolute z-20 top-2 left-4
                 bg-gray-900/85 backdrop-blur-md border border-gray-700
                 rounded-lg p-2.5 select-none
                 w-44"
      aria-label="Status legend"
    >
      <div className="flex items-center justify-between mb-1.5">
        <p className="text-[9px] uppercase tracking-widest text-gray-400">
          Status Legend
        </p>
        <button
          type="button"
          onClick={() => setOpen(false)}
          aria-label="Collapse status legend"
          aria-expanded="true"
          className="w-5 h-5 -my-1 -mr-1 flex items-center justify-center
                     text-gray-500 hover:text-gray-200 cursor-pointer
                     transition-colors"
        >
          <ChevronUp className="w-3.5 h-3.5" aria-hidden="true" />
        </button>
      </div>
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
      {(demoMode || relative) && (
        <div className="border-t border-gray-700/60 pt-1.5">
          {demoMode ? (
            <p className="text-[9px] text-gray-500 leading-snug">
              Live data offline
            </p>
          ) : (
            <p className={`text-[9px] leading-snug flex items-center gap-1 ${isStale ? 'text-yellow-400' : 'text-gray-400'}`}>
              {isStale && <AlertTriangle className="w-2.5 h-2.5 flex-shrink-0" aria-hidden="true" />}
              Updated {relative}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
