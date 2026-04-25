import { useEffect } from 'react';
import { useDashboardContext } from '../components/Layout';
import ReportForm  from '../components/ReportForm';
import ReportsList from '../components/ReportsList';

/**
 * Reports.jsx — citizen incident-report form + public list
 * ===========================================================
 *
 * Public page (no auth in v3 demo). Anyone can submit a report; anyone can
 * view the list. Production hardening lives in a future sprint.
 *
 * Layout: form on top, list below. The mini-map for pinpointing a location
 * is wired up inside ReportForm.
 */

export default function Reports() {
  const { setPageMeta } = useDashboardContext();

  useEffect(() => {
    setPageMeta({
      title:        'Incident reports',
      subtitle:     'Citizen-submitted observations across Bulgaria',
      showSeverity: false,
    });
  }, [setPageMeta]);

  return (
    <div className="absolute inset-0 overflow-y-auto">
      <div className="max-w-5xl mx-auto px-6 py-6 flex flex-col gap-6">
        <ReportForm />
        <ReportsList />
      </div>
    </div>
  );
}
