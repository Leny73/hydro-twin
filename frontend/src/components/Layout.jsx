import { useEffect, useState } from 'react';
import { Outlet, useLocation, useOutletContext } from 'react-router-dom';
import Sidebar, { MobileNav } from './Sidebar';
import TopBar           from './TopBar';
import DataSourcesBar   from './DataSourcesBar';

/**
 * Layout.jsx — top-level dashboard chrome
 * =========================================
 *
 *   ┌────────────────────────────────────────┐
 *   │ Sidebar │ TopBar                       │
 *   │         │──────────────────────────────│
 *   │         │ <Outlet>                     │
 *   │         │  page content                │
 *   │         │──────────────────────────────│
 *   │         │ DataSourcesBar               │
 *   └────────────────────────────────────────┘
 *
 * Owns the shared `regionStatuses` snapshot so:
 *   - The Overview page reads it for map paint + AlertPanel
 *   - The TopBar reads it for the severity counter
 *   - The Sidebar's "Last updated" widget reads its newest timestamp
 *
 * Pages access the snapshot via `useOutletContext()`; they may also pass a
 * page-specific `title` / `subtitle` via context so the TopBar reflects the
 * current route.
 */

const API_ENDPOINT =
  import.meta.env.VITE_API_ENDPOINT ??
  'https://YOUR_API_ID.execute-api.us-east-1.amazonaws.com/prod/assess';
const STATUS_ENDPOINT = API_ENDPOINT.replace('/assess', '/status');

export default function Layout() {
  const [regionStatuses,    setRegionStatuses]    = useState([]);
  const [statusGeneratedAt, setStatusGeneratedAt] = useState(null);
  const [statusDemoMode,    setStatusDemoMode]    = useState(false);
  const [mobileNavOpen,     setMobileNavOpen]     = useState(false);

  // Auto-close the mobile drawer whenever the route changes
  const location = useLocation();
  useEffect(() => { setMobileNavOpen(false); }, [location.pathname]);

  // Page-specific chrome (set by pages via the outlet context)
  const [pageMeta, setPageMeta] = useState({ title: 'Operational overview', subtitle: 'Clear insights. Timely action.', showSeverity: true });

  // ── Fetch /status snapshot on mount ────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    fetch(STATUS_ENDPOINT)
      .then(r => r.json())
      .then(data => {
        if (cancelled) return;
        setRegionStatuses(Array.isArray(data?.regions) ? data.regions : []);
        setStatusGeneratedAt(data?.generated_at ?? null);
        setStatusDemoMode(!!data?.demo_mode);
      })
      .catch(err => {
        if (cancelled) return;
        console.warn('[HydroTwin] /status fetch failed:', err.message);
        setStatusDemoMode(true);
      });
    return () => { cancelled = true; };
  }, []);

  // ── Newest assessed_at across all regions ──────────────────────────────
  const lastUpdated = (() => {
    if (regionStatuses.length === 0) return statusGeneratedAt;
    const stamps = regionStatuses.map(s => s.assessed_at).filter(Boolean).sort();
    return stamps.length ? stamps[stamps.length - 1] : statusGeneratedAt;
  })();

  // Stale = newest snapshot is over an hour old. Cron runs every 30 min,
  // so >1 h means at least one cycle missed.
  const isStale = lastUpdated
    ? (Date.now() - new Date(lastUpdated).getTime()) > 60 * 60 * 1000
    : false;

  // Allow pages to patch a single region's snapshot (e.g. after a click-time
  // /assess refresh) without forcing a full re-fetch.
  const patchRegionStatus = (region_id, patch) => {
    setRegionStatuses(prev => {
      const others = prev.filter(s => s.region_id !== region_id);
      return [...others, { region_id, ...patch }];
    });
    setStatusGeneratedAt(new Date().toISOString());
    setStatusDemoMode(false);
  };

  return (
    <div className="flex w-screen h-screen bg-gray-950 font-mono text-white overflow-hidden">
      <Sidebar lastUpdated={lastUpdated} isStale={isStale} />
      <MobileNav
        lastUpdated={lastUpdated}
        isStale={isStale}
        isOpen={mobileNavOpen}
        onClose={() => setMobileNavOpen(false)}
      />

      <div className="flex flex-col flex-1 min-w-0">
        <TopBar
          title={pageMeta.title}
          subtitle={pageMeta.subtitle}
          regionStatuses={pageMeta.showSeverity ? regionStatuses : undefined}
          onMenuClick={() => setMobileNavOpen(true)}
        />

        <main className="flex-1 min-h-0 relative overflow-hidden">
          <Outlet context={{
            regionStatuses,
            statusGeneratedAt,
            statusDemoMode,
            lastUpdated,
            isStale,
            patchRegionStatus,
            setPageMeta,
          }} />
        </main>

        <DataSourcesBar />
      </div>
    </div>
  );
}

// Convenience hook so pages don't have to import useOutletContext directly.
export function useDashboardContext() {
  return useOutletContext();
}
