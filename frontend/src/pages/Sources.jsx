import { useEffect } from 'react';
import { useDashboardContext } from '../components/Layout';

/**
 * Sources.jsx — data provenance reference page
 * ================================================
 *
 * BF1-3: lifts the data-source attribution out of the bottom DataSourcesBar
 * (which is hidden on mobile and tight on desktop) into a proper page that
 * fits any viewport. Linked from the sidebar / mobile drawer.
 */

const SOURCES = [
  {
    icon:    '🛰️',
    name:    'Copernicus Sentinel-1',
    family:  'EU Copernicus Programme',
    what:    'C-band Synthetic Aperture Radar — flood extent mapping, soil moisture proxy from SAR backscatter. Cloud-penetrating, day-and-night.',
    cadence: 'Tile revisit ≈ 6 days (per region)',
    href:    'https://sentinel.esa.int/web/sentinel/missions/sentinel-1',
  },
  {
    icon:    '🛰️',
    name:    'Copernicus Sentinel-2',
    family:  'EU Copernicus Programme',
    what:    'Multispectral optical imagery — vegetation health (NDVI from B4/B8), surface water classification, drought stress indicators.',
    cadence: 'Tile revisit ≈ 5 days (per region)',
    href:    'https://sentinel.esa.int/web/sentinel/missions/sentinel-2',
  },
  {
    icon:    '🛰️',
    name:    'Copernicus Sentinel-3',
    family:  'EU Copernicus Programme',
    what:    'SRAL altimetry — river-level estimation, lake-level monitoring, soil-temperature anomalies.',
    cadence: 'Daily near-global coverage',
    href:    'https://sentinel.esa.int/web/sentinel/missions/sentinel-3',
  },
  {
    icon:    '📡',
    name:    'Galileo GNSS',
    family:  'EU GNSS Programme',
    what:    'Precision positioning & timing for the EO data pipeline — anchors imagery to ground truth and timestamps acquisitions.',
    cadence: 'Continuous',
    href:    'https://www.gsc-europa.eu/galileo/what-is-galileo',
  },
  {
    icon:    '🌧️',
    name:    'OpenMeteo',
    family:  'Weather data API',
    what:    'Hourly precipitation, temperature, soil moisture & forecast. Source for short-term flood / drought signals + the historical ERA5 archive used by replay.',
    cadence: 'Hourly updates · Historical archive 1940 → present',
    href:    'https://open-meteo.com/',
  },
  {
    icon:    '🌡️',
    name:    'ECMWF ERA5',
    family:  'Reanalysis',
    what:    'Global atmospheric reanalysis used for SPI / PDSI drought indices and replay-mode reconstruction of past events.',
    cadence: 'Daily archive (5-day lag)',
    href:    'https://www.ecmwf.int/en/forecasts/dataset/ecmwf-reanalysis-v5',
  },
  {
    icon:    '🌊',
    name:    'NIMH Bulgaria',
    family:  'Bulgarian National Institute of Meteorology & Hydrology',
    what:    'Authoritative national meteorology — threshold calibration, regional baselines, curated reference events for replay.',
    cadence: 'Daily bulletins · WMO 1991-2020 normals',
    href:    'https://www.meteo.bg/en/',
  },
  {
    icon:    '🌿',
    name:    'WMO — World Meteorological Organization',
    family:  'United Nations Specialised Agency',
    what:    'Standardized Precipitation Index (SPI) user guide and drought indicator handbooks — basis for drought threshold calibration and classification rules.',
    cadence: 'Reference standards',
    href:    'https://who.int/',
  },
  {
    icon:    '🌍',
    name:    'World Bank CCKP — Bulgaria',
    family:  'Climate Change Knowledge Portal',
    what:    'Bulgaria climate context for the 1991–2020 climatology derived from observed historical data. Used to understand current climate conditions and future climate scenarios for regional baseline calibration.',
    cadence: 'Annual updates',
    href:    'https://climateknowledgeportal.worldbank.org/country/bulgaria/climate-data-historical',
  },
  {
    icon:    '🔬',
    name:    'IPCC',
    family:  'Intergovernmental Panel on Climate Change',
    what:    'Climate risk scenarios and extreme event projections — long-term context for flood and drought risk assessment in Bulgaria.',
    cadence: 'Assessment cycles every 5–7 years',
    href:    'https://www.ipcc.ch/',
  },
  {
    icon:    '📊',
    name:    'Eurostat',
    family:  'Statistical Office of the European Union',
    what:    'EU-level environmental and climate statistics — regional context for Bulgaria\'s flood and drought exposure across oblasts.',
    cadence: 'Annual updates',
    href:    'https://ec.europa.eu/eurostat/web/main/home',
  },
  {
    icon:    '💧',
    name:    'ISME-HYDRO',
    family:  'Water Resources Management Platform · Mozaika',
    what:    'Comprehensive dam and river monitoring system combining in-situ measurements, satellite data, and deep learning. Official platform of the Bulgarian Executive Agency for Exploitation and Monitoring of the Danube River — issues flood and drought advance warnings for the Danube basin.',
    cadence: 'Real-time in-situ + satellite feeds',
    href:    'https://isme-hydro.com/',
  },
];

export default function Sources() {
  const { setPageMeta } = useDashboardContext();

  useEffect(() => {
    setPageMeta({
      title:        'Data sources',
      subtitle:     'Provenance & refresh cadence across the HydroTwin pipeline',
      showSeverity: false,
    });
  }, [setPageMeta]);

  return (
    <div className="absolute inset-0 overflow-y-auto">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 py-6 flex flex-col gap-5">
        <section className="bg-gray-900/60 border border-gray-800 rounded-xl p-5">
          <h2 className="text-base font-bold text-white mb-1">Powered by trusted data</h2>
          <p className="text-xs text-gray-400 leading-relaxed">
            Every assessment HydroTwin emits is grounded in open Earth-observation
            and weather data. Below is the full list of upstream feeds, what we
            extract from each, and how often they update.
          </p>
        </section>

        <ul className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {SOURCES.map(s => (
            <li
              key={s.name}
              className="bg-gray-900/60 border border-gray-800 rounded-xl p-5 flex flex-col gap-2"
            >
              <div className="flex items-start gap-3">
                <span className="text-2xl flex-shrink-0" aria-hidden="true">{s.icon}</span>
                <div className="min-w-0">
                  <p className="text-sm font-bold text-white leading-tight">{s.name}</p>
                  <p className="text-[10px] uppercase tracking-widest text-gray-500 mt-0.5">
                    {s.family}
                  </p>
                </div>
              </div>
              <p className="text-xs text-gray-300 leading-relaxed">{s.what}</p>
              <div className="flex items-center justify-between gap-3 mt-1 pt-2 border-t border-gray-800/60">
                <span className="text-[10px] text-gray-500">
                  <span className="uppercase tracking-widest">Cadence:</span>{' '}
                  <span className="text-gray-300">{s.cadence}</span>
                </span>
                <a
                  href={s.href}
                  target="_blank"
                  rel="noreferrer"
                  className="text-[10px] uppercase tracking-widest text-cyan-400 hover:text-cyan-300
                             underline whitespace-nowrap"
                >
                  Visit ↗
                </a>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
