import { useEffect, useState } from 'react';
import { listReports } from '../lib/reports-api';

/**
 * ReportsList.jsx — public list of submitted incident reports
 * ==============================================================
 *
 * Refreshes on mount + when ReportForm fires `hydrotwin:reports:changed`.
 * Demo-first: if the API is unreachable, render a small set of seeded
 * mock reports so the page still has content during the demo.
 */

const REGION_LABELS = {
  pleven: 'Pleven Oblast',
  yambol: 'Yambol Oblast',
  burgas: 'Burgas Oblast',
  other:  'Other',
};

const DEMO_REPORTS = [
  {
    report_id:    'demo-1',
    email:        'maria@example.com',
    region_id:    'pleven',
    description:  'Vit river overflowed near our village last night, two basements flooded.',
    lat:          43.40,
    lng:          24.62,
    submitted_at: new Date(Date.now() - 1000 * 60 * 35).toISOString(),
  },
  {
    report_id:    'demo-2',
    email:        'ivan@example.com',
    region_id:    'yambol',
    description:  'Crops drying out — the soil is cracking. No rain for weeks.',
    lat:          42.32,
    lng:          26.61,
    submitted_at: new Date(Date.now() - 1000 * 60 * 60 * 4).toISOString(),
  },
  {
    report_id:    'demo-3',
    email:        'elena@example.com',
    region_id:    'burgas',
    description:  'Storm surge damaged the breakwater near Mandra-Poda. Standing water in low areas.',
    lat:          42.44,
    lng:          27.30,
    submitted_at: new Date(Date.now() - 1000 * 60 * 60 * 12).toISOString(),
  },
];

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

export default function ReportsList() {
  const [reports,   setReports]   = useState([]);
  const [loading,   setLoading]   = useState(true);
  const [demoMode,  setDemoMode]  = useState(false);

  const refresh = async () => {
    setLoading(true);
    try {
      const data = await listReports();
      setReports(Array.isArray(data?.reports) ? data.reports : []);
      setDemoMode(false);
    } catch (err) {
      console.warn('[HydroTwin] /reports list fetch failed:', err.message);
      setReports(DEMO_REPORTS);
      setDemoMode(true);
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

  return (
    <section className="bg-gray-900/60 border border-gray-800 rounded-xl p-5">
      <header className="mb-4 flex items-center gap-3">
        <h2 className="text-base font-bold text-white">Recent reports</h2>
        {demoMode && (
          <span className="text-[10px] text-yellow-400 border border-yellow-800/60 bg-yellow-950/40 px-2 py-0.5 rounded">
            Demo data
          </span>
        )}
        <span className="ml-auto text-[10px] text-gray-500">
          {loading ? 'Loading…' : `${reports.length} report${reports.length === 1 ? '' : 's'}`}
        </span>
      </header>

      {!loading && reports.length === 0 && (
        <p className="text-xs text-gray-500 italic text-center py-6">
          No reports yet — be the first to submit one above.
        </p>
      )}

      <ul className="flex flex-col gap-3">
        {reports.map(r => (
          <li
            key={r.report_id}
            className="flex flex-col gap-1.5 p-3 rounded-lg bg-gray-800/40 border border-gray-700/60"
          >
            <div className="flex items-center gap-3 text-[11px] text-gray-400">
              <span className="font-bold text-cyan-300">
                {REGION_LABELS[r.region_id] ?? r.region_id}
              </span>
              <span className="text-gray-600">·</span>
              <span>{relative(r.submitted_at)}</span>
              <span className="text-gray-600">·</span>
              <span>{maskEmail(r.email)}</span>
              {r.lat !== undefined && r.lng !== undefined && (
                <>
                  <span className="text-gray-600">·</span>
                  <span className="font-mono text-[10px]">
                    {Number(r.lat).toFixed(3)}°N, {Number(r.lng).toFixed(3)}°E
                  </span>
                </>
              )}
            </div>
            <p className="text-sm text-gray-200 leading-relaxed">
              {r.description}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}
