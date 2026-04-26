import { useEffect } from 'react';
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
        <IncidentsList />
      </div>
    </div>
  );
}
