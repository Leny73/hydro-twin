import { useEffect, useMemo, useState } from 'react';
import { listReports } from '../lib/reports-api';

/**
 * ReportsList.jsx — public list of submitted incident reports
 * ==============================================================
 *
 * BF2-2 changes:
 *   - Pill-chip region filter (All / Pleven / Yambol / Burgas / Other) with
 *     per-chip counts
 *   - Each card shows both relative time AND absolute date/time
 *   - Metadata row wraps so coordinates can't escape the card on narrow
 *     viewports
 *
 * Refreshes on mount + when ReportForm fires `hydrotwin:reports:changed`.
 * On fetch failure: empty list + small error caption (no fake demo data).
 */

const REGION_OPTIONS = [
  { value: 'ALL',    label: 'All'            },
  { value: 'pleven', label: 'Pleven Oblast'  },
  { value: 'yambol', label: 'Yambol Oblast'  },
  { value: 'burgas', label: 'Burgas Oblast'  },
  { value: 'other',  label: 'Other'          },
];

const REGION_LABELS = REGION_OPTIONS.reduce((acc, o) => {
  if (o.value !== 'ALL') acc[o.value] = o.label;
  return acc;
}, {});

function maskEmail(email) {
  if (!email || !email.includes('@')) return '—';
  const [local, domain] = email.split('@');
  if (local.length <= 1) return `${local}***@${domain}`;
  return `${local[0]}***@${domain}`;
}

function relative(iso) {
  const ts = new Date(iso).getTime();
  if (Number.isNaN(ts)) return '—';
  const diffMin = Math.max(0, Math.round((Date.now() - ts) / 60000));
  if (diffMin < 1)  return 'just now';
  if (diffMin < 60) return `${diffMin} min ago`;
  const h = Math.floor(diffMin / 60);
  if (h < 24) return `${h} h ago`;
  const d = Math.floor(h / 24);
  return `${d} d ago`;
}

function absolute(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString('en-GB', {
    day:    'numeric',
    month:  'short',
    year:   'numeric',
    hour:   '2-digit',
    minute: '2-digit',
  });
}

export default function ReportsList() {
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState(null);
  const [filter,  setFilter]  = useState('ALL');

  const refresh = async () => {
    setLoading(true);
    try {
      const data = await listReports();
      setReports(Array.isArray(data?.reports) ? data.reports : []);
      setError(null);
    } catch (err) {
      console.warn('[HydroTwin] /reports list fetch failed:', err.message);
      setReports([]);
      setError('Could not load reports — please try again later.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    const onChange = () => refresh();
    window.addEventListener('hydrotwin:reports:changed', onChange);
    return () => window.removeEventListener('hydrotwin:reports:changed', onChange);
  }, []);

  // Per-region counts for the chip badges
  const counts = useMemo(() => {
    const out = { ALL: reports.length };
    for (const r of reports) {
      const k = r.region_id ?? 'other';
      out[k] = (out[k] ?? 0) + 1;
    }
    return out;
  }, [reports]);

  const visible = useMemo(() => {
    if (filter === 'ALL') return reports;
    return reports.filter(r => (r.region_id ?? 'other') === filter);
  }, [reports, filter]);

  const filterRegionLabel = filter === 'ALL' ? null : REGION_LABELS[filter] ?? filter;

  return (
    <section className="bg-gray-900/60 border border-gray-800 rounded-xl p-5">
      <header className="mb-4 flex items-center gap-3 flex-wrap">
        <h2 className="text-base font-bold text-white">Recent reports</h2>
        <span className="ml-auto text-[10px] text-gray-500">
          {loading ? 'Loading…' : `${visible.length} of ${reports.length}`}
        </span>
      </header>

      {/* Region filter chips */}
      <div
        className="flex flex-wrap gap-2 mb-4"
        role="tablist"
        aria-label="Filter reports by region"
      >
        {REGION_OPTIONS.map(opt => {
          const active = filter === opt.value;
          const n      = counts[opt.value] ?? 0;
          return (
            <button
              key={opt.value}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => setFilter(opt.value)}
              className={`
                inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full
                text-[11px] uppercase tracking-widest font-semibold
                transition-colors duration-150 cursor-pointer
                ${active
                  ? 'bg-cyan-900/60 border border-cyan-600/70 text-cyan-100'
                  : 'bg-gray-800/60 border border-gray-700/70 text-gray-300 hover:border-gray-500'}
              `}
            >
              <span>{opt.label}</span>
              <span
                className={`tabular-nums text-[10px] px-1.5 py-0.5 rounded-full
                  ${active ? 'bg-cyan-950/80 text-cyan-200' : 'bg-gray-900/80 text-gray-400'}`}
              >
                {n}
              </span>
            </button>
          );
        })}
      </div>

      {error && !loading && (
        <p className="text-[11px] text-yellow-400 border border-yellow-800/60 bg-yellow-950/40
                      px-3 py-2 rounded-md text-center leading-relaxed mb-3">
          ⚠️ {error}
        </p>
      )}

      {!loading && !error && visible.length === 0 && (
        <p className="text-xs text-gray-500 italic text-center py-6">
          {reports.length === 0
            ? 'No reports yet — be the first to submit one above.'
            : `No reports for ${filterRegionLabel} yet.`}
        </p>
      )}

      <ul className="flex flex-col gap-3">
        {visible.map(r => (
          <li
            key={r.report_id}
            className="flex flex-col gap-1.5 p-3 rounded-lg
                       bg-gray-800/40 border border-gray-700/60 overflow-hidden"
          >
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-gray-400">
              <span className="font-bold text-cyan-300 break-words">
                {REGION_LABELS[r.region_id] ?? r.region_id}
              </span>
              <span className="text-gray-600">·</span>
              <span title={absolute(r.submitted_at)}>{relative(r.submitted_at)}</span>
              <span className="text-gray-600">·</span>
              <span className="text-gray-500">{absolute(r.submitted_at)}</span>
              <span className="text-gray-600">·</span>
              <span className="break-all">{maskEmail(r.email)}</span>
              {r.lat !== undefined && r.lng !== undefined && (
                <>
                  <span className="text-gray-600">·</span>
                  <span className="font-mono text-[10px] break-all">
                    {Number(r.lat).toFixed(3)}°N, {Number(r.lng).toFixed(3)}°E
                  </span>
                </>
              )}
            </div>
            <p className="text-sm text-gray-200 leading-relaxed break-words">
              {r.description}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}
