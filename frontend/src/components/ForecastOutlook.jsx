import { useEffect, useMemo, useState } from 'react';
import { fetchForecastOutlook } from '../lib/openmeteo';

/**
 * ForecastOutlook.jsx — next 7-day decision-support forecast row
 * =================================================================
 *
 * Shows seven compact day-cards (today → +6) for the selected region's
 * centroid. Each card carries the day initial, a weather glyph derived
 * from precipitation intensity, expected mm, and max temperature. The
 * goal is *actionable preview* — a mayor can decide today whether to
 * pre-position resources for what's coming, without reading a chart.
 *
 * Data: OpenMeteo Forecast API (daily precipitation_sum + temperature_2m_max).
 */

function bboxCenter(bbox) {
  if (!Array.isArray(bbox) || bbox.length < 4) return [null, null];
  return [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2];
}

// Glyph derived from precip intensity. Keep deliberately coarse — we don't
// have weather_code parsed and intensity is the actionable signal anyway.
function glyphFor(precip_mm) {
  if (precip_mm >= 15) return { icon: '⛈️', tone: 'text-red-300'    };
  if (precip_mm >= 5)  return { icon: '☔',  tone: 'text-blue-300'   };
  if (precip_mm >= 1)  return { icon: '🌦️', tone: 'text-cyan-300'   };
  return                       { icon: '☀️', tone: 'text-yellow-200' };
}

function dayLabel(iso, idx) {
  if (idx === 0) return 'Today';
  const d = new Date(`${iso}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleDateString('en-GB', { weekday: 'short' });
}

export default function ForecastOutlook({ region }) {
  const [days,  setDays]  = useState(null);
  const [error, setError] = useState(null);

  const [lng, lat] = useMemo(() => {
    if (!region) return [null, null];
    if (region.longitude != null && region.latitude != null) {
      return [region.longitude, region.latitude];
    }
    return bboxCenter(region.bbox);
  }, [region]);

  useEffect(() => {
    if (lng == null || lat == null) return;
    let cancelled = false;
    setDays(null);
    setError(null);
    fetchForecastOutlook({ longitude: lng, latitude: lat, days: 7 })
      .then(d => { if (!cancelled) setDays(d); })
      .catch(err => {
        console.warn('[HydroTwin] forecast fetch failed:', err.message);
        if (!cancelled) setError(err.message);
      });
    return () => { cancelled = true; };
  }, [lng, lat]);

  if (lng == null || lat == null) return null;

  const totalPrecip = days ? days.reduce((s, d) => s + d.precip_mm, 0) : null;
  const peakTemp    = days
    ? days.reduce((m, d) => (d.temp_max_c != null && d.temp_max_c > m ? d.temp_max_c : m), -Infinity)
    : null;

  return (
    <div>
      <div className="flex items-baseline justify-between gap-2 mb-1.5">
        <p className="text-[10px] uppercase tracking-widest text-gray-400">
          Next 7 days · forecast
        </p>
        {totalPrecip != null && Number.isFinite(peakTemp) && (
          <p className="text-[11px] tabular-nums text-gray-300">
            <span className="font-bold text-cyan-300">{totalPrecip.toFixed(0)} mm</span>
            <span className="text-gray-500"> · peak </span>
            <span className="font-bold text-orange-300">{peakTemp.toFixed(0)}°</span>
          </p>
        )}
      </div>

      <div className="bg-gray-800/60 border border-gray-700/60 rounded-lg p-2">
        {!days && !error && <Skeleton />}
        {error  && <ErrorRow msg={error} />}
        {days   && days.length > 0 && (
          <ul className="grid grid-cols-7 gap-1.5">
            {days.map((d, i) => {
              const g = glyphFor(d.precip_mm);
              return (
                <li
                  key={d.date}
                  className="flex flex-col items-center gap-0.5 py-1.5 rounded
                             bg-gray-900/40 border border-gray-800/60 text-center"
                  title={`${d.date} — ${d.precip_mm.toFixed(1)} mm, ${
                    d.temp_max_c != null ? `${d.temp_max_c.toFixed(0)} °C max` : 'temp n/a'
                  }`}
                >
                  <span className="text-[9px] uppercase tracking-wider text-gray-400">
                    {dayLabel(d.date, i)}
                  </span>
                  <span className={`text-base leading-none ${g.tone}`} aria-hidden="true">
                    {g.icon}
                  </span>
                  <span className="text-[10px] tabular-nums font-bold text-gray-100">
                    {d.precip_mm < 1 ? '0' : d.precip_mm.toFixed(0)}
                    <span className="text-gray-500 font-normal">mm</span>
                  </span>
                  <span className="text-[10px] tabular-nums text-gray-400">
                    {d.temp_max_c != null ? `${d.temp_max_c.toFixed(0)}°` : '—'}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}

function Skeleton() {
  return (
    <div className="h-20 flex items-center justify-center" aria-busy="true">
      <span className="text-[10px] text-gray-500 tracking-widest uppercase animate-pulse">
        Loading forecast…
      </span>
    </div>
  );
}

function ErrorRow({ msg }) {
  return (
    <div className="h-20 flex items-center justify-center px-3">
      <span className="text-[10px] text-yellow-500 leading-relaxed text-center">
        ⚠️ {msg}
      </span>
    </div>
  );
}
