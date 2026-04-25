import { useMemo } from 'react';

/**
 * CycloneChart.jsx — Synoptic surface-pressure forecast (Windy embed)
 * =====================================================================
 *
 * BF2-4b: embeds Windy.com's official `embed2.html` viewer focused on
 * Bulgaria with the surface-pressure overlay. Shows live isobars
 * (closed lows = cyclones) and a built-in timeline so forecasters can
 * scrub the next ~10 days of synoptic state.
 *
 * Why Windy instead of wetter3.de:
 *   - Windy explicitly supports cross-origin embeds (they ship their
 *     own embed iframe). wetter3.de blocks hotlinking even with
 *     `referrerPolicy="no-referrer"`, which is what we hit in
 *     production.
 *   - Interactive: pan, zoom, scrub timeline. wetter3.de was a static
 *     GIF.
 *   - Multiple data layers built in (pressure, wind, rain, temp).
 *
 * If the Windy iframe is ever blocked, the link in the header lets the
 * user open Windy in a new tab.
 */

const SOURCE_URL = 'https://www.windy.com/?42.7,25.5,5';

function bboxCenter(bbox) {
  if (!Array.isArray(bbox) || bbox.length < 4) return [25.5, 42.7]; // Bulgaria fallback
  return [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2];
}

export default function CycloneChart({ region }) {
  // Centre the embed on the active region if we have it; otherwise use
  // a Bulgaria-wide default so the map still makes sense at first paint.
  const [lon, lat] = useMemo(() => {
    if (region?.longitude != null && region?.latitude != null) {
      return [region.longitude, region.latitude];
    }
    return bboxCenter(region?.bbox);
  }, [region]);

  const embedUrl =
    `https://embed.windy.com/embed2.html` +
    `?lat=${lat.toFixed(2)}&lon=${lon.toFixed(2)}&zoom=5` +
    `&detailLat=${lat.toFixed(2)}&detailLon=${lon.toFixed(2)}` +
    `&overlay=pressure&level=surface` +
    `&menu=&message=true&marker=true` +
    `&calendar=&pressure=true&type=map` +
    `&location=coordinates&detail=` +
    `&metricWind=default&metricTemp=default`;

  return (
    <div>
      <div className="flex items-baseline justify-between gap-2 mb-1.5">
        <p className="text-[10px] uppercase tracking-widest text-gray-400">
          Synoptic field · surface pressure
        </p>
        <a
          href={SOURCE_URL}
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
          src={embedUrl}
          className="w-full h-64 block border-0"
          loading="lazy"
          referrerPolicy="no-referrer-when-downgrade"
          allow="geolocation"
        />
      </div>

      <p className="text-[10px] text-gray-500 leading-relaxed mt-1">
        Closed circular isobars mark cyclones (low pressure). Tightly-packed
        isobars over Bulgaria signal strong synoptic forcing — storm tracks,
        fronts, and heavy precipitation in the next 24–48 h. Use the timeline
        bar to scrub forward.
      </p>
    </div>
  );
}
