/**
 * openmeteo.js — Historical weather fetch + status derivation
 * ============================================================
 *
 * Calls OpenMeteo Historical Archive (free, no auth, CORS-enabled) to fetch
 * the 30 days ending on `replayDate` for the given lon/lat, then derives a
 * HydroTwin-shaped assessment so the AlertPanel can render the same way it
 * does for live data.
 *
 * Why OpenMeteo and not Sentinel: it requires no auth, returns instantly,
 * and covers the keys that drive the alert thresholds (precipitation,
 * temperature). Sentinel-derived fields (NDVI, flood extent) are left null
 * until Alexandre's extractor adds `replay_date` support — see
 * specs/06-history-replay/01-design.md (Tier B).
 */

const ARCHIVE_URL  = 'https://archive-api.open-meteo.com/v1/archive';
const FORECAST_URL = 'https://api.open-meteo.com/v1/forecast';

/**
 * Fetch recent daily precipitation (mm) for a point, for the last N days.
 * Uses the Forecast API with `past_days` because the Archive API lags ~5 d.
 *
 * @returns {Promise<{ date: string, value: number }[]>}  daily series, oldest first
 */
export async function fetchRecentPrecipSeries({ longitude, latitude, days = 14 }) {
  const url = new URL(FORECAST_URL);
  url.searchParams.set('latitude',       latitude);
  url.searchParams.set('longitude',      longitude);
  url.searchParams.set('daily',          'precipitation_sum');
  url.searchParams.set('past_days',      String(days));
  url.searchParams.set('forecast_days',  '1');
  url.searchParams.set('timezone',       'auto');

  const res = await fetch(url.toString());
  if (!res.ok) throw new Error(`OpenMeteo HTTP ${res.status}`);
  const data = await res.json();

  const dates  = data?.daily?.time ?? [];
  const values = data?.daily?.precipitation_sum ?? [];
  const points = dates.map((d, i) => ({
    date:  d,
    value: Number.isFinite(values[i]) ? Number(values[i]) : 0,
  }));
  return points.slice(-days);
}

// ── Threshold rules — simplified from backend/meteorology_rules.md ──────────
// The full ruleset is the authoritative one in the Bedrock prompt. This is a
// frontend approximation good enough for archive playback.
// Drought threshold raised to ≤ 15 mm/30d so the 2007 Bulgarian heatwave
// (11.6 mm/30d, 41.5 °C — a textbook DROUGHT_WARNING event in NIMH records)
// classifies correctly. Floods detected via local precipitation only — basin-
// driven river floods (Danube, Carpathian snowmelt) need Sentinel-3 altimetry
// and won't trigger from point precip alone. See specs/06-history-replay/.
function deriveStatus({ precip_mm_7d, precip_mm_30d, temp_max_c }) {
  if (precip_mm_7d >= 150)                        return 'FLOOD_WARNING';
  if (precip_mm_7d >= 100)                        return 'FLOOD_WATCH';
  if (precip_mm_30d <= 15 && temp_max_c >= 38)    return 'DROUGHT_WARNING';
  if (precip_mm_30d <= 30 && temp_max_c >= 32)    return 'DROUGHT_WATCH';
  return 'SAFE';
}

// Sum the last `n` daily values in an array, ignoring null entries.
function sumLast(arr, n) {
  if (!Array.isArray(arr) || arr.length === 0) return 0;
  const slice = arr.slice(Math.max(0, arr.length - n));
  return slice.reduce((acc, v) => acc + (Number.isFinite(v) ? v : 0), 0);
}

function maxLast(arr, n) {
  if (!Array.isArray(arr) || arr.length === 0) return null;
  const slice = arr.slice(Math.max(0, arr.length - n));
  const finite = slice.filter((v) => Number.isFinite(v));
  return finite.length ? Math.max(...finite) : null;
}

// ── ISO date helpers (local, UTC-safe) ──────────────────────────────────────
function isoDay(date) {
  return date.toISOString().slice(0, 10);
}
function offsetDays(isoDate, days) {
  const d = new Date(`${isoDate}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return isoDay(d);
}

// ── Reasoning template ──────────────────────────────────────────────────────
function buildReasoning({
  replayDate, regionName, status,
  precip_mm_7d, precip_mm_30d, temp_max_c,
}) {
  const dayLabel = new Date(`${replayDate}T00:00:00Z`).toLocaleDateString(
    'en-GB', { day: 'numeric', month: 'long', year: 'numeric' },
  );

  const headline = {
    FLOOD_WARNING:   'Flood Warning conditions reached on this day.',
    FLOOD_WATCH:     'Elevated flood-watch conditions on this day.',
    DROUGHT_WARNING: 'Severe drought conditions on this day.',
    DROUGHT_WATCH:   'Early drought-watch signal on this day.',
    SAFE:            'No threshold breached — conditions within seasonal norms.',
  }[status];

  const lines = [
    `**Historical reconstruction — ${dayLabel} · ${regionName}.**`,
    '',
    headline,
    '',
    `- **7-day precipitation:** ${precip_mm_7d.toFixed(0)} mm`,
    `- **30-day precipitation:** ${precip_mm_30d.toFixed(0)} mm`,
    `- **Peak temperature (last 3 days):** ${temp_max_c != null ? `${temp_max_c.toFixed(1)} °C` : '—'}`,
  ];

  if (status === 'SAFE') {
    lines.push('');
    lines.push('_Note: status reflects **local precipitation only**. River floods driven by upstream snowmelt or distant catchment rain (e.g. Danube, Carpathian basins) require Sentinel-3 altimetry and are not visible at this point._');
  }

  lines.push('');
  lines.push('_Source: OpenMeteo Historical Archive (ERA5 reanalysis). NDVI, soil moisture, and river-level metrics require the Tier B extractor — pending._');

  return lines.join('\n');
}

/**
 * Fetch + transform OpenMeteo Historical data into a HydroTwin assessment.
 *
 * @param {object} args
 * @param {number} args.longitude
 * @param {number} args.latitude
 * @param {string} args.replayDate  ISO YYYY-MM-DD (must be in the past)
 * @param {string} args.regionId
 * @param {string} args.regionName
 * @returns {Promise<{ status, confidence, reasoning, region_id, replay, replay_date, snapshot }>}
 */
export async function fetchHistoricalAssessment({
  longitude, latitude, replayDate, regionId, regionName,
}) {
  const start = offsetDays(replayDate, -29); // 30-day window inclusive
  const end   = replayDate;

  const url = new URL(ARCHIVE_URL);
  url.searchParams.set('latitude',  latitude);
  url.searchParams.set('longitude', longitude);
  url.searchParams.set('start_date', start);
  url.searchParams.set('end_date',   end);
  url.searchParams.set('daily', 'precipitation_sum,temperature_2m_max');
  url.searchParams.set('timezone', 'auto');

  const res = await fetch(url.toString());
  if (!res.ok) {
    throw new Error(`OpenMeteo HTTP ${res.status}`);
  }
  const data = await res.json();

  const precipDaily = data?.daily?.precipitation_sum ?? [];
  const tempDaily   = data?.daily?.temperature_2m_max ?? [];

  const precip_mm_7d  = sumLast(precipDaily, 7);
  const precip_mm_30d = sumLast(precipDaily, 30);
  const temp_max_c    = maxLast(tempDaily, 3);

  const status = deriveStatus({ precip_mm_7d, precip_mm_30d, temp_max_c: temp_max_c ?? 0 });

  // Confidence rises with how clearly we're past a threshold. Quick heuristic.
  let confidence = 0.7;
  if (status === 'FLOOD_WARNING')   confidence = Math.min(0.97, 0.7 + (precip_mm_7d - 150) / 200);
  if (status === 'FLOOD_WATCH')     confidence = Math.min(0.9,  0.7 + (precip_mm_7d - 100) / 250);
  if (status === 'DROUGHT_WARNING') confidence = 0.92;
  if (status === 'DROUGHT_WATCH')   confidence = 0.78;
  if (status === 'SAFE')            confidence = 0.85;

  return {
    region_id:  regionId,
    status,
    confidence: Number(confidence.toFixed(2)),
    reasoning:  buildReasoning({
      replayDate, regionName, status,
      precip_mm_7d, precip_mm_30d, temp_max_c,
    }),
    replay:      true,
    replay_kind: 'archive',
    replay_date: replayDate,
    snapshot: {
      precip_mm_7d,
      precip_mm_30d,
      temp_max_c,
      data_timestamp: `${replayDate}T12:00:00Z`,
      source: 'OpenMeteo Historical Archive (ERA5)',
    },
  };
}
