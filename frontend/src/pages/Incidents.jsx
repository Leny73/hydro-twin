import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useDashboardContext } from '../components/Layout';
import IncidentsList from '../components/IncidentsList';

/**
 * Incidents.jsx — municipality view of citizen-submitted incidents
 * ===================================================================
 *
 * Read-only on purpose: the dashboard is a tool for municipalities, not
 * for citizens. Citizens submit through the public /submit page; what
 * lands there shows up here for triage.
 */

export default function Incidents() {
  const { setPageMeta } = useDashboardContext();

  useEffect(() => {
    setPageMeta({
      title:        'Citizen incidents',
      subtitle:     'Ground-truth observations submitted from the field',
      showSeverity: false,
    });
  }, [setPageMeta]);

  return (
    <div className="absolute inset-0 overflow-y-auto">
      <div className="max-w-5xl mx-auto px-6 py-6 flex flex-col gap-6">
        <Link
          to="/submit"
          className="bg-cyan-950/40 border border-cyan-700/50 rounded-xl p-5 flex items-center gap-4
                     hover:border-cyan-500/70 hover:bg-cyan-950/60 transition-colors group"
        >
          <span className="text-2xl flex-shrink-0" aria-hidden="true">📝</span>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-bold text-white leading-tight group-hover:text-cyan-300 transition-colors">
              Submit an incident
            </p>
            <p className="text-xs text-gray-400 leading-relaxed mt-0.5">
              Report a flood or drought observation from the field — visible on the dashboard within seconds.
            </p>
          </div>
          <span className="text-cyan-500 group-hover:text-cyan-300 transition-colors text-lg flex-shrink-0">↗</span>
        </Link>
        <IncidentsList />
      </div>
    </div>
  );
}
