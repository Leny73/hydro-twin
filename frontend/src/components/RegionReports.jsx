import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { listReports } from '../lib/reports-api';

/**
 * RegionReports.jsx — recent citizen reports for the active region
 * ===================================================================
 *
 * Decision-support angle: pairs the satellite/Bedrock assessment with
 * ground-truth observations submitted via /reports. The full list lives
 * on /reports — this is the in-panel preview (last 3) so a mayor sees
 * "what people on the ground are saying about THIS oblast" without
 * leaving the alert panel.
 *
 * Refreshes on mount + on the `hydrotwin:reports:changed` event fired
 * by ReportForm (so the panel stays current after a submission).
 */

const LIMIT = 3;

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

export default function RegionReports({ region }) {
  const [reports, setReports] = useState(null);
  const [error,   setError]   = useState(null);

  const refresh = async () => {
    try {
      const data = await listReports();
      setReports(Array.isArray(data?.reports) ? data.reports : []);
      setError(null);
    } catch (err) {
      console.warn('[HydroTwin] region reports fetch failed:', err.message);
      setReports([]);
      setError('Could not load citizen reports.');
    }
  };

  useEffect(() => {
    refresh();
    const onChange = () => refresh();
    window.addEventListener('hydrotwin:reports:changed', onChange);
    return () => window.removeEventListener('hydrotwin:reports:changed', onChange);
  }, []);

  const matching = useMemo(() => {
    if (!Array.isArray(reports) || !region?.id) return [];
    return reports
      .filter(r => r.region_id === region.id)
      .sort((a, b) => new Date(b.submitted_at) - new Date(a.submitted_at))
      .slice(0, LIMIT);
  }, [reports, region?.id]);

  const totalForRegion = useMemo(() => {
    if (!Array.isArray(reports) || !region?.id) return 0;
    return reports.filter(r => r.region_id === region.id).length;
  }, [reports, region?.id]);

  return (
    <div>
      <div className="flex items-baseline justify-between gap-2 mb-1.5">
        <p className="text-[10px] uppercase tracking-widest text-gray-400">
          Citizen reports · this oblast
        </p>
        <Link
          to="/reports"
          className="text-[10px] text-cyan-400 hover:text-cyan-300 underline whitespace-nowrap"
        >
          all reports ↗
        </Link>
      </div>

      <div className="bg-gray-800/60 border border-gray-700/60 rounded-lg">
        {reports == null && !error && <Skeleton />}

        {error && (
          <div className="px-3 py-3 text-[10px] text-yellow-500 leading-relaxed text-center">
            ⚠️ {error}
          </div>
        )}

        {reports != null && !error && matching.length === 0 && (
          <div className="px-3 py-4 text-center">
            <p className="text-[11px] text-gray-400 mb-1">
              No reports for {region?.name ?? 'this region'} yet.
            </p>
            <Link
              to="/reports"
              className="text-[10px] text-cyan-400 hover:text-cyan-300 underline"
            >
              Submit the first one →
            </Link>
          </div>
        )}

        {matching.length > 0 && (
          <ul className="divide-y divide-gray-700/50">
            {matching.map(r => (
              <li key={r.report_id} className="px-3 py-2.5 flex flex-col gap-1">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px] text-gray-500">
                  <span className="font-semibold text-cyan-300">
                    {relative(r.submitted_at)}
                  </span>
                  <span className="text-gray-700">·</span>
                  <span className="break-all">{maskEmail(r.email)}</span>
                </div>
                <p className="text-[12px] text-gray-200 leading-snug break-words line-clamp-3">
                  {r.description}
                </p>
              </li>
            ))}
            {totalForRegion > LIMIT && (
              <li className="px-3 py-2 text-center">
                <Link
                  to="/reports"
                  className="text-[10px] text-cyan-400 hover:text-cyan-300 underline"
                >
                  +{totalForRegion - LIMIT} more for {region?.name ?? 'this region'} →
                </Link>
              </li>
            )}
          </ul>
        )}
      </div>
    </div>
  );
}

function Skeleton() {
  return (
    <div className="h-20 flex items-center justify-center" aria-busy="true">
      <span className="text-[10px] text-gray-500 tracking-widest uppercase animate-pulse">
        Loading reports…
      </span>
    </div>
  );
}
