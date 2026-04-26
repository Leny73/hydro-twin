import { useEffect } from 'react';
import { NavLink } from 'react-router-dom';

/**
 * Sidebar.jsx — left navigation (static + mobile drawer)
 * ========================================================
 *
 * Two exports share one nav definition:
 *   - <Sidebar />    static, fixed-width, visible only at lg+ (≥1024 px)
 *   - <MobileNav />  fullscreen drawer with backdrop, visible only below lg
 *
 * Layout owns the `mobileNavOpen` state and wires the TopBar hamburger to
 * <MobileNav onClose>. Tapping a nav link inside the drawer auto-closes.
 */

const NAV_LINKS = [
  { to: '/',           end: true,  icon: '🏠', label: 'Overview'  },
  { to: '/incidents',              icon: '🚨', label: 'Incidents' },
  { to: '/dams',                   icon: '💧', label: 'Dams'      },
  { to: '/sources',                icon: '📚', label: 'Sources'   },
];

function navClass({ isActive }) {
  return [
    'flex items-center gap-2 px-3 py-2 rounded-md text-sm font-semibold',
    'min-h-[44px]',
    'transition-colors duration-150',
    isActive
      ? 'bg-cyan-950/60 text-cyan-300 border border-cyan-800/60'
      : 'text-gray-400 hover:text-gray-100 hover:bg-gray-900',
  ].join(' ');
}

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

function formatDateCaption(iso) {
  if (!iso) return 'Awaiting first update';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  const time = d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', hour12: false });
  const isToday = d.toDateString() === new Date().toDateString();
  if (isToday) return `Today, ${time}`;
  const date = d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  return `${date} · ${time}`;
}

function LatestUpdateCard({ lastUpdated, isStale }) {
  const accent = isStale
    ? { ring: 'border-yellow-700/60 bg-yellow-950/40', dot: 'bg-yellow-950 border-yellow-700', big: 'text-yellow-200' }
    : { ring: 'border-cyan-800/40 bg-cyan-950/30',     dot: 'bg-cyan-950 border-cyan-700/60',  big: 'text-cyan-200'   };

  return (
    <div
      className={`mx-3 mb-3 p-3 rounded-lg border flex items-center gap-3 ${accent.ring}`}
      aria-label="Latest data update"
    >
      <div className={`w-10 h-10 rounded-full border flex items-center justify-center flex-shrink-0 ${accent.dot}`}>
        <span className="text-lg" aria-hidden="true">{isStale ? '⚠️' : '🕒'}</span>
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-[9px] uppercase tracking-widest text-gray-500 leading-none mb-1">
          Latest Update
        </p>
        <p className={`text-base font-bold leading-tight truncate ${accent.big}`}>
          {formatRelative(lastUpdated)}
        </p>
        <p className="text-[10px] text-gray-500 leading-tight truncate mt-0.5">
          {formatDateCaption(lastUpdated)}
        </p>
      </div>
    </div>
  );
}

function NavContent({ lastUpdated, isStale, onLinkClick }) {
  return (
    <>
      <div className="flex items-center gap-2 px-5 py-4 border-b border-gray-800">
        <span className="text-2xl select-none" aria-hidden="true">💧</span>
        <span className="text-base font-bold tracking-widest text-cyan-400 uppercase">
          HydroTwin
        </span>
      </div>

      <nav className="flex flex-col px-3 py-4 gap-1 flex-1" aria-label="Pages">
        {NAV_LINKS.map(link => (
          <NavLink
            key={link.to}
            to={link.to}
            end={link.end}
            className={navClass}
            onClick={onLinkClick}
          >
            <span aria-hidden="true">{link.icon}</span>
            <span>{link.label}</span>
          </NavLink>
        ))}
      </nav>

      <LatestUpdateCard lastUpdated={lastUpdated} isStale={isStale} />
    </>
  );
}

export default function Sidebar({ lastUpdated, isStale }) {
  return (
    <aside
      className="hidden lg:flex flex-col w-[200px] flex-shrink-0
                 bg-gray-950 border-r border-gray-800 z-30"
      aria-label="Primary navigation"
    >
      <NavContent lastUpdated={lastUpdated} isStale={isStale} />
    </aside>
  );
}

export function MobileNav({ lastUpdated, isStale, isOpen, onClose }) {
  // Lock body scroll + close on Escape while drawer is open
  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e) => { if (e.key === 'Escape') onClose?.(); };
    window.addEventListener('keydown', onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [isOpen, onClose]);

  return (
    <>
      <div
        className={`lg:hidden fixed inset-0 z-40 bg-black/60 backdrop-blur-sm
                    transition-opacity duration-200
                    ${isOpen ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'}`}
        onClick={onClose}
        aria-hidden="true"
      />
      <aside
        className={`lg:hidden fixed top-0 bottom-0 left-0 z-50 w-[260px] max-w-[80vw]
                    bg-gray-950 border-r border-gray-800 flex flex-col
                    transition-transform duration-200 ease-out
                    ${isOpen ? 'translate-x-0' : '-translate-x-full'}`}
        aria-label="Primary navigation"
        aria-hidden={!isOpen}
      >
        <button
          type="button"
          onClick={onClose}
          aria-label="Close navigation menu"
          className="absolute top-2 right-2 w-11 h-11 flex items-center justify-center
                     rounded-md text-gray-400 hover:text-white hover:bg-gray-800
                     cursor-pointer"
        >
          <span className="text-xl leading-none" aria-hidden="true">✕</span>
        </button>
        <NavContent
          lastUpdated={lastUpdated}
          isStale={isStale}
          onLinkClick={onClose}
        />
      </aside>
    </>
  );
}
