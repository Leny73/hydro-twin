import { NavLink } from 'react-router-dom';

/**
 * Sidebar.jsx — fixed-width left navigation
 * ============================================
 *
 * Always-visible nav for the v3 dashboard chrome:
 *   - Logo + brand
 *   - Page links (Overview, Reports)
 *   - "Last updated" widget pinned to the bottom
 *
 * Receives `lastUpdated` and `staleHours` from the parent so the freshness
 * indicator stays in sync with the map's snapshot data without a second
 * fetch or context provider.
 */

function formatRelative(iso) {
  if (!iso) return '—';
  const ts = new Date(iso).getTime();
  if (Number.isNaN(ts)) return '—';
  const diffMin = Math.max(0, Math.round((Date.now() - ts) / 60000));
  if (diffMin < 1)  return 'just now';
  if (diffMin < 60) return `${diffMin} min ago`;
  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24) return `${diffH} h ago`;
  const diffD = Math.floor(diffH / 24);
  return `${diffD} d ago`;
}

export default function Sidebar({ lastUpdated, isStale }) {
  return (
    <aside
      className="hidden lg:flex flex-col w-[200px] flex-shrink-0
                 bg-gray-950 border-r border-gray-800
                 z-30"
      aria-label="Primary navigation"
    >
      {/* ── Brand ─────────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-2 px-5 py-4 border-b border-gray-800">
        <span className="text-2xl select-none" aria-hidden="true">💧</span>
        <span className="text-base font-bold tracking-widest text-cyan-400 uppercase">
          HydroTwin
        </span>
      </div>

      {/* ── Nav links ─────────────────────────────────────────────────────── */}
      <nav className="flex flex-col px-3 py-4 gap-1 flex-1" aria-label="Pages">
        <NavLink to="/"        end className={navClass}>🏠 <span>Overview</span></NavLink>
        <NavLink to="/reports"     className={navClass}>📋 <span>Reports</span></NavLink>
      </nav>

      {/* ── Last-updated widget (bottom) ──────────────────────────────────── */}
      <div className="px-4 py-4 border-t border-gray-800 text-[11px] text-gray-400 leading-relaxed">
        <p className="uppercase tracking-widest text-[9px] text-gray-500 mb-1">
          Last updated
        </p>
        <p className={`font-semibold ${isStale ? 'text-yellow-400' : 'text-gray-200'}`}>
          {isStale && '⚠️ '}{formatRelative(lastUpdated)}
        </p>
      </div>
    </aside>
  );
}

function navClass({ isActive }) {
  return [
    'flex items-center gap-2 px-3 py-2 rounded-md text-sm font-semibold',
    'transition-colors duration-150',
    isActive
      ? 'bg-cyan-950/60 text-cyan-300 border border-cyan-800/60'
      : 'text-gray-400 hover:text-gray-100 hover:bg-gray-900',
  ].join(' ');
}
