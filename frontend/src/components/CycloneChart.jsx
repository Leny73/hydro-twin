import { useMemo } from 'react';

/**
 * CycloneChart.jsx — synoptic-scale pressure field for Eastern Europe
 * ======================================================================
 *
 * Two layers of detail in one component:
 *
 *   1. **Inline preview**: a Windy.com embed centred on Eastern Europe with
 *      the surface-pressure overlay. Closed isobars = cyclones. Windy is
 *      used because it ships an officially supported `embed.windy.com/embed2.html`
 *      iframe that renders cleanly in narrow sidebars (the ECMWF Open Charts
 *      product page is desktop-full-screen and won't lay out in <400 px).
 *
 *   2. **"Open ECMWF Z500/T850 ↗"** deep-link with `base_time` + `valid_time`
 *      computed dynamically — one click to the authoritative European
 *      synoptic chart that NIMH / DWD / Météo-France actually use.
 *
 * The deep-link is the value-add for domain experts; the inline embed gives
 * everyone a quick visual cue without leaving the panel.
 */

const ECMWF_PRODUCT  = 'medium-z500-t850';
const ECMWF_PROJ     = 'opencharts_europe';
const ECMWF_FCST_H   = 24;  // valid_time = base + 24 h
const ECMWF_LAG_H    = 8;   // run publishes ~7-8 h after model start

// Most recent 6-hourly run (00z/06z/12z/18z) that has had time to publish.
function latestPublishedRun(now = new Date()) {
  const t = new Date(now.getTime() - ECMWF_LAG_H * 3600_000);
  t.setUTCMinutes(0, 0, 0);
  t.setUTCHours(Math.floor(t.getUTCHours() / 6) * 6);
  return t;
}

function ecmwfStamp(d) {
  const pad = (n) => String(n).padStart(2, '0');
  return (
    `${d.getUTCFullYear()}` +
    `${pad(d.getUTCMonth() + 1)}` +
    `${pad(d.getUTCDate())}` +
    `${pad(d.getUTCHours())}` +
    `${pad(d.getUTCMinutes())}`
  );
}

// Zoom 4 keeps the Eastern-Europe / Black Sea synoptic frame so approaching
// systems from the Atlantic, Med, and Russian plains stay visible — but the
// camera centres on the clicked oblast so the user sees their region in context.
const VIEW_ZOOM = 4;
const FALLBACK = { lon: 25.5, lat: 42.7 }; // Bulgaria centroid

function bboxCenter(bbox) {
  if (!Array.isArray(bbox) || bbox.length < 4) return null;
  return { lon: (bbox[0] + bbox[2]) / 2, lat: (bbox[1] + bbox[3]) / 2 };
}

function regionCenter(region) {
  if (region?.longitude != null && region?.latitude != null) {
    return { lon: region.longitude, lat: region.latitude };
  }
  return bboxCenter(region?.bbox) ?? FALLBACK;
}

export default function CycloneChart({ region }) {
  const windyUrl = useMemo(() => {
    const { lon, lat } = regionCenter(region);
    return (
      `https://embed.windy.com/embed2.html` +
      `?lat=${lat.toFixed(2)}&lon=${lon.toFixed(2)}&zoom=${VIEW_ZOOM}` +
      `&detailLat=${lat.toFixed(2)}&detailLon=${lon.toFixed(2)}` +
      `&overlay=pressure&level=surface` +
      `&menu=&message=true&marker=true` +
      `&calendar=&pressure=true&type=map` +
      `&location=coordinates&detail=` +
      `&metricWind=default&metricTemp=default`
    );
  }, [region]);

  const { ecmwfUrl, validLabel } = useMemo(() => {
    const baseRun   = latestPublishedRun();
    const validTime = new Date(baseRun.getTime() + ECMWF_FCST_H * 3600_000);
    const qs = `base_time=${ecmwfStamp(baseRun)}` +
               `&projection=${ECMWF_PROJ}` +
               `&valid_time=${ecmwfStamp(validTime)}`;
    return {
      ecmwfUrl: `https://charts.ecmwf.int/products/${ECMWF_PRODUCT}?${qs}`,
      validLabel: validTime.toLocaleString('en-GB', {
        weekday: 'short',
        day:     'numeric',
        month:   'short',
        hour:    '2-digit',
        timeZone: 'UTC',
      }) + ' UTC',
    };
  }, []);

  return (
    <div>
      <div className="flex items-baseline justify-between gap-2 mb-1.5">
        <p className="text-[10px] uppercase tracking-widest text-gray-400">
          Synoptic field · surface pressure
        </p>
        <a
          href="https://www.windy.com/?42.7,25.5,5"
          target="_blank"
          rel="noreferrer"
          className="text-[10px] text-cyan-400 hover:text-cyan-300 underline whitespace-nowrap"
        >
          windy.com ↗
        </a>
      </div>

      <div className="bg-gray-800/60 border border-gray-700/60 rounded-lg overflow-hidden">
        <iframe
          title="Surface-pressure forecast — Windy.com"
          src={windyUrl}
          className="w-full h-64 block border-0"
          loading="lazy"
          referrerPolicy="no-referrer-when-downgrade"
          allow="geolocation"
        />
      </div>

      <p className="text-[10px] text-gray-500 leading-relaxed mt-1.5">
        Closed isobars mark cyclones (low pressure). Tightly-packed isobars over
        Bulgaria signal strong synoptic forcing in the next 24-48 h.
      </p>

      <a
        href={ecmwfUrl}
        target="_blank"
        rel="noreferrer"
        className="mt-2 flex items-center justify-between gap-2 px-3 py-2
                   rounded-md bg-gray-800/80 hover:bg-gray-700/80
                   border border-gray-700/60 hover:border-cyan-700/70
                   transition-colors duration-150 cursor-pointer group"
      >
        <span className="flex flex-col min-w-0">
          <span className="text-[10px] uppercase tracking-widest text-gray-400 group-hover:text-gray-200">
            ECMWF · Z500 + 850 hPa T
          </span>
          <span className="text-[11px] text-gray-300 truncate">
            Authoritative chart — valid {validLabel}
          </span>
        </span>
        <span className="text-cyan-400 group-hover:text-cyan-300 text-sm flex-shrink-0">
          ↗
        </span>
      </a>
    </div>
  );
}
