import { Link } from 'react-router-dom';

/**
 * DataSourcesBar.jsx — bottom "Powered by trusted data" strip (desktop only)
 * ============================================================================
 *
 * BF1-3 / BF1-8: hidden on mobile (sources reachable via the new /sources
 * nav item). Desktop keeps a compact attribution row that wraps cleanly on
 * narrow widths and links to the full Sources page for details.
 *
 * Logos are emoji placeholders for now; real SVGs can drop in later without
 * touching layout.
 */

const SOURCES = [
  { icon: '🛰️', name: 'Copernicus',        sub: 'Sentinel-1 / -2 / -3 · SAR & optical' },
  { icon: '📡',  name: 'Galileo',           sub: 'GNSS positioning & timing'           },
  { icon: '🌧️', name: 'Rainfall datasets', sub: 'OpenMeteo + ERA5 · precipitation'    },
];

export default function DataSourcesBar({ dataQuality = 'Good' }) {
  return (
    <footer
      className="hidden md:flex items-center gap-x-5 gap-y-2 flex-wrap
                 px-6 py-2 min-h-[3.5rem] flex-shrink-0
                 bg-gray-950/95 border-t border-gray-800
                 text-[11px] text-gray-400 z-20"
      aria-label="Data sources"
    >
      <span className="uppercase tracking-widest text-[10px] text-gray-500 flex-shrink-0">
        Powered by trusted data
      </span>

      {SOURCES.map(s => (
        <div key={s.name} className="flex items-center gap-2 flex-shrink-0">
          <span className="text-base" aria-hidden="true">{s.icon}</span>
          <div className="leading-tight">
            <p className="font-semibold text-gray-300">{s.name}</p>
            <p className="text-[10px] text-gray-500">{s.sub}</p>
          </div>
        </div>
      ))}

      <Link
        to="/sources"
        className="text-[10px] uppercase tracking-widest text-cyan-400 hover:text-cyan-300
                   underline whitespace-nowrap flex-shrink-0"
      >
        View all ↗
      </Link>

      <div className="ml-auto flex items-center gap-2 flex-shrink-0">
        <span className="uppercase tracking-widest text-[10px] text-gray-500">
          Data quality
        </span>
        <span className="text-emerald-400 font-bold">{dataQuality}</span>
      </div>
    </footer>
  );
}
