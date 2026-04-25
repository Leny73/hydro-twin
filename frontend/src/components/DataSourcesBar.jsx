/**
 * DataSourcesBar.jsx — bottom "Powered by trusted data" strip
 * ==============================================================
 *
 * Static attribution row pinned to the bottom of the dashboard. Communicates
 * provenance (Copernicus EO, Galileo GNSS, weather feeds) at a glance to
 * municipal authorities — credibility is part of the product story.
 *
 * Logos are emoji placeholders for now; real SVGs can drop in later without
 * touching layout.
 */

const SOURCES = [
  {
    icon:  '🛰️',
    name:  'Copernicus',
    label: 'Sentinel-1 & Sentinel-2',
    sub:   'SAR & Optical data',
  },
  {
    icon:  '📡',
    name:  'Galileo',
    label: 'GNSS positioning',
    sub:   '& timing',
  },
  {
    icon:  '🌧️',
    name:  'Rainfall datasets',
    label: 'OpenMeteo + ERA5',
    sub:   'precipitation data',
  },
];

export default function DataSourcesBar({ dataQuality = 'Good' }) {
  return (
    <footer
      className="flex items-center gap-6 px-6 h-14 flex-shrink-0
                 bg-gray-950/95 border-t border-gray-800
                 text-[11px] text-gray-400 overflow-x-auto z-20"
      aria-label="Data sources"
    >
      <span className="uppercase tracking-widest text-[10px] text-gray-500 flex-shrink-0">
        Powered by trusted data
      </span>

      <div className="flex items-center gap-5">
        {SOURCES.map(s => (
          <div key={s.name} className="flex items-center gap-2 flex-shrink-0">
            <span className="text-base" aria-hidden="true">{s.icon}</span>
            <div className="leading-tight">
              <p className="font-semibold text-gray-300">{s.name}</p>
              <p className="text-[10px] text-gray-500">{s.label} · {s.sub}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="ml-auto flex items-center gap-2 flex-shrink-0">
        <span className="uppercase tracking-widest text-[10px] text-gray-500">
          Data quality
        </span>
        <span className="text-emerald-400 font-bold">{dataQuality}</span>
      </div>
    </footer>
  );
}
