/**
 * App.jsx — HydroTwin Main Application
 * ========================================
 *
 * Architecture:
 *   1. react-map-gl renders a full-screen Mapbox satellite map.
 *   2. REGIONS defines six Bulgarian hydro-risk zones rendered as coloured
 *      GeoJSON polygon overlays (fill + outline) instead of point markers.
 *   3. Clicking or tapping a zone fires a POST to the API Gateway → Lambda.
 *   4. Hovering a zone raises its opacity and changes the cursor to pointer.
 *   5. The Lambda response is passed to AlertPanel (bottom sheet / sidebar).
 *
 * Environment variables required (.env.local):
 *   VITE_MAPBOX_TOKEN  – Mapbox public access token
 *   VITE_API_ENDPOINT  – API Gateway endpoint URL
 */

import { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import Map, { Source, Layer, Marker, NavigationControl, ScaleControl } from 'react-map-gl';
import 'mapbox-gl/dist/mapbox-gl.css';
import AlertPanel from './components/AlertPanel';
import MapLegend from './components/MapLegend';
import REGIONS_GEOJSON from './regions.geojson';
import HISTORICAL_EVENTS from './data/historicalEvents.json';
import { fetchHistoricalAssessment } from './lib/openmeteo';
import MUNICIPALITIES_GEOJSON from './municipalities.geojson';

// ── API / Token configuration ─────────────────────────────────────────────────
const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN ?? '';
const API_ENDPOINT =
  import.meta.env.VITE_API_ENDPOINT ??
  'https://YOUR_API_ID.execute-api.us-east-1.amazonaws.com/prod/assess';
// /status sits next to /assess on the same API Gateway. Derive instead of asking
// for a second env var so deployments stay simple.
const STATUS_ENDPOINT = API_ENDPOINT.replace('/assess', '/status');

// ── Status → polygon fill colour (matches AlertPanel.STATUS_META) ────────────
const STATUS_COLORS = {
  SAFE:            '#10B981',
  DROUGHT_WATCH:   '#F59E0B',
  DROUGHT_WARNING: '#F97316',
  FLOOD_WATCH:     '#3B82F6',
  FLOOD_WARNING:   '#EF4444',
};
// Neutral grey used when no snapshot is available yet (first cron run pending,
// table down, or /status fetch failed). Keeps the polygon visible without
// implying a status it doesn't have.
const NEUTRAL_COLOR = '#64748B'; // slate-500

// ── Monitoring regions ───────────────────────────────────────────────────────
// Centre coordinates + bbox kept here for label Markers and API calls.
// Polygon shapes live in regions.geojson — edit that file to update boundaries.
const REGIONS = [
  {
    id:          'pleven',
    name:        'Pleven Oblast',
    description: 'Northern Bulgaria — Danube floodplain flood risk; Vit, Osam & Iskur tributaries cross the oblast',
    longitude:   24.62,
    latitude:    43.41,
    bbox:        [23.90, 43.15, 25.20, 43.70],
    color:       '#3B82F6', // blue — flood risk
  },
  {
    id:          'yambol',
    name:        'Yambol Oblast',
    description: 'Southeast Bulgaria — Tundzha river basin; Thracian Lowland drought & flash-flood risk',
    longitude:   26.613,
    latitude:    42.329,
    bbox:        [26.18, 41.94, 27.05, 42.72],
    color:       '#F59E0B', // amber — drought-prone
  },
  {
    id:          'burgas',
    name:        'Burgas Oblast',
    description: 'Black Sea coast — river-mouth flooding, storm-surge, Mandra-Poda wetlands',
    longitude:   27.306,
    latitude:    42.440,
    bbox:        [26.58, 41.90, 28.04, 42.98],
    color:       '#06B6D4', // cyan — coastal
  },
];

// REGIONS_GEOJSON is imported from ./regions.geojson
// Edit that file to update zone polygon boundaries without touching this file.

// ── Pleven municipality layer descriptors ─────────────────────────────────────
const MUNICIPALITIES_FILL_LAYER = {
  id:   'municipalities-fill',
  type: 'fill',
  paint: {
    // If the municipality has been assessed, show its status colour; else neutral blue
    'fill-color':   ['coalesce', ['get', 'color'], '#3B82F6'],
    'fill-opacity': [
      'case',
      ['boolean', ['feature-state', 'hover'], false], 0.65,
      ['has', 'color'], 0.50,
      0.30,
    ],
  },
};

const MUNICIPALITIES_OUTLINE_LAYER = {
  id:   'municipalities-outline',
  type: 'line',
  paint: {
    'line-color':   '#60A5FA', // blue-400
    'line-width':   2,
    'line-opacity': 1,
  },
};

const MUNICIPALITIES_LABEL_LAYER = {
  id:     'municipalities-label',
  type:   'symbol',
  layout: {
    'text-field':      ['get', 'NAME_2'],
    'text-font':       ['DIN Offc Pro Medium', 'Arial Unicode MS Regular'],
    'text-size':       12,
    'text-anchor':     'center',
    'text-max-width':  8,
  },
  paint: {
    'text-color':       '#EFF6FF', // blue-50
    'text-halo-color':  '#1E3A5F',
    'text-halo-width':  2,
    'text-halo-blur':   0,
  },
};

// Cyan dashed ring on the selected municipality
const MUNICIPALITIES_SELECTED_LAYER = {
  id:     'municipalities-selected',
  type:   'line',
  filter: ['==', ['get', 'GID_2'], ''], // updated dynamically
  paint:  {
    'line-color':     '#67E8F9', // cyan-300
    'line-width':     3,
    'line-opacity':   1,
    'line-dasharray': [2, 1],
  },
};

// ── Mapbox layer descriptors (static objects — defined outside component) ─────
// Fill layer: semi-transparent colour, brightens on hover via feature-state.
const FILL_LAYER = {
  id:     'regions-fill',
  type:   'fill',
  paint:  {
    'fill-color':   ['get', 'color'],
    'fill-opacity': [
      'case',
      ['boolean', ['feature-state', 'hover'], false], 0.45,
      0.18,
    ],
  },
};

// Outline layer: solid border in the zone's colour, thickens on hover.
const OUTLINE_LAYER = {
  id:    'regions-outline',
  type:  'line',
  paint: {
    'line-color': ['get', 'color'],
    'line-width': [
      'case',
      ['boolean', ['feature-state', 'hover'], false], 3,
      1.5,
    ],
    'line-opacity': 0.9,
  },
};

// Selected outline: bright cyan pulse ring shown on the active zone.
const SELECTED_LAYER = {
  id:     'regions-selected',
  type:   'line',
  filter: ['==', ['get', 'id'], ''], // filter updated dynamically
  paint:  {
    'line-color':   '#67E8F9', // cyan-300
    'line-width':   3,
    'line-opacity': 1,
    'line-dasharray': [2, 1],
  },
};

const INITIAL_VIEW_STATE = {
  longitude: 24.55,
  latitude:  43.42,
  zoom:      7.5,
};

// ── Simulated demo response (shown when the live API is unavailable) ──────────
const buildDemoResponse = (region) => ({
  region_id:  region.id,
  status:     'FLOOD_WATCH',
  confidence: 0.78,
  reasoning:
    '[DEMO MODE] River levels in the Vit and Osam rivers have risen 1.1 m above the seasonal ' +
    'baseline over the past 72 hours. Soil saturation across Pleven Oblast is at 91 %. Precipitation ' +
    'forecast shows an additional 38 mm expected within 24 hours. The Danube floodplain in the ' +
    'Nikopol area is at elevated risk — two of three FLOOD_WATCH thresholds are breached.',
});

// ─────────────────────────────────────────────────────────────────────────────
// Utility: compute [lon_min, lat_min, lon_max, lat_max] from any GeoJSON geometry
function bboxFromGeometry(geometry) {
  const lons = [], lats = [];
  const collect = (arr) => {
    if (typeof arr[0] === 'number') { lons.push(arr[0]); lats.push(arr[1]); return; }
    arr.forEach(collect);
  };
  collect(geometry.coordinates);
  return [Math.min(...lons), Math.min(...lats), Math.max(...lons), Math.max(...lats)];
}

// ─────────────────────────────────────────────────────────────────────────────
export default function App() {
  // ── State ─────────────────────────────────────────────────────────────────
  const [selectedRegion, setSelectedRegion] = useState(null);
  const [assessment,     setAssessment]     = useState(null);
  const [isLoading,      setIsLoading]      = useState(false);
  const [error,          setError]          = useState(null);
  // hoveredMuniId stored in a ref (not state) so mouse handlers never
  // get recreated on every hover, keeping them stable for Mapbox.
  const hoveredMuniIdRef = useRef(null);

  // Municipality on-demand assessment cache (keyed by GID_2)
  const [muniStatuses, setMuniStatuses] = useState({});

  // ── Replay state (two mutually exclusive modes) ──────────────────────────
  // 'archive'  → user picked a calendar date → real OpenMeteo fetch
  // 'curated'  → user picked an event chip   → pre-baked snapshot
  const [replayDate,         setReplayDate]         = useState(null); // ISO YYYY-MM-DD
  const [replayCuratedEvent, setReplayCuratedEvent] = useState(null); // event object
  const [replayAssessment,   setReplayAssessment]   = useState(null); // archive-mode synthesised
  const [replayLoading,      setReplayLoading]      = useState(false);
  const [replayError,        setReplayError]        = useState(null);

  // Curated events available for the selected region.
  const regionEvents = useMemo(() => {
    if (!selectedRegion) return [];
    return HISTORICAL_EVENTS[selectedRegion.id] ?? [];
  }, [selectedRegion]);

  // When replayDate is set, fetch OpenMeteo Historical and build a synthetic
  // assessment with the same shape as the live API response.
  useEffect(() => {
    if (!replayDate || !selectedRegion) {
      setReplayAssessment(null);
      setReplayError(null);
      return;
    }
    let cancelled = false;
    setReplayLoading(true);
    setReplayError(null);

    fetchHistoricalAssessment({
      longitude:  selectedRegion.longitude,
      latitude:   selectedRegion.latitude,
      replayDate,
      regionId:   selectedRegion.id,
      regionName: selectedRegion.name,
    })
      .then((result) => {
        if (cancelled) return;
        setReplayAssessment(result);
      })
      .catch((err) => {
        if (cancelled) return;
        console.warn('[HydroTwin] OpenMeteo fetch failed:', err.message);
        setReplayError('Could not load archive data — try a different date.');
        setReplayAssessment(null);
      })
      .finally(() => {
        if (!cancelled) setReplayLoading(false);
      });

    return () => { cancelled = true; };
  }, [replayDate, selectedRegion]);

  // Displayed assessment: curated > archive > live (priority order).
  const displayedAssessment = useMemo(() => {
    if (replayCuratedEvent) {
      return {
        region_id:   replayCuratedEvent.regionId,
        status:      replayCuratedEvent.severity,
        confidence:  replayCuratedEvent.confidence,
        reasoning:   replayCuratedEvent.reasoning,
        replay:      true,
        replay_kind: 'curated',
        replay_date: replayCuratedEvent.peakDate,
        curated:     replayCuratedEvent,
      };
    }
    if (replayDate) return replayAssessment;
    return assessment;
  }, [replayCuratedEvent, replayDate, replayAssessment, assessment]);

  // V2-2: pre-computed status snapshot (one entry per region from /status)
  const [regionStatuses,    setRegionStatuses]    = useState([]);
  const [statusGeneratedAt, setStatusGeneratedAt] = useState(null);
  const [statusDemoMode,    setStatusDemoMode]    = useState(false);

  // mapRef lets us call map.setFeatureState for hover highlighting
  const mapRef = useRef(null);

  // ── V2-2: fetch /status on mount so polygons paint by current status ──────
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
        // Snapshot endpoint unavailable — polygons fall back to neutral grey
        // and the legend shows a "Snapshot unavailable" badge. Map still works.
        console.warn('[HydroTwin] /status fetch failed:', err.message);
        setStatusDemoMode(true);
      });
    return () => { cancelled = true; };
  }, []);

  // ── Derive the painted GeoJSON (base shapes + status-driven fill colour) ──
  const paintedRegions = useMemo(() => {
    const statusByRegion = Object.fromEntries(
      regionStatuses.map(s => [s.region_id, s.status])
    );
    return {
      ...REGIONS_GEOJSON,
      features: REGIONS_GEOJSON.features.map(f => {
        const status = statusByRegion[f.properties.id] ?? null;
        return {
          ...f,
          properties: {
            ...f.properties,
            status,
            color: STATUS_COLORS[status] ?? NEUTRAL_COLOR,
          },
        };
      }),
    };
  }, [regionStatuses]);

  // ── Painted municipalities GeoJSON — fill colour updated after each assessment
  const paintedMunicipalities = useMemo(() => ({
    ...MUNICIPALITIES_GEOJSON,
    features: MUNICIPALITIES_GEOJSON.features.map(f => {
      const s = muniStatuses[f.properties.GID_2];
      const extra = s ? { color: s.color } : {};
      return { ...f, properties: { ...f.properties, ...extra } };
    }),
  }), [muniStatuses]);

  // Sync municipality status colour after a successful on-demand assessment
  useEffect(() => {
    if (!assessment?.status || !selectedRegion?.id) return;
    if (!selectedRegion.id.startsWith('BGR.')) return; // only municipality IDs
    setMuniStatuses(prev => ({
      ...prev,
      [selectedRegion.id]: {
        status: assessment.status,
        color:  STATUS_COLORS[assessment.status] ?? NEUTRAL_COLOR,
      },
    }));
  }, [assessment, selectedRegion]);

  // Newest assessed_at across all regions — drives the legend's freshness line
  const latestAssessedAt = useMemo(() => {
    if (regionStatuses.length === 0) return null;
    const stamps = regionStatuses
      .map(s => s.assessed_at)
      .filter(Boolean)
      .sort();
    return stamps.length ? stamps[stamps.length - 1] : null;
  }, [regionStatuses]);

  // ── Fetch assessment from API Gateway → Lambda ────────────────────────────
  const fetchAssessment = useCallback(async (region) => {
    setIsLoading(true);
    setError(null);
    setAssessment(null);

    try {
      const response = await fetch(API_ENDPOINT, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({
          region_id: region.id,
          bbox:      region.bbox,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();
      setAssessment(data);

      // Keep the cached map paint in sync with on-demand fetches — when the
      // user clicks a region, the polygon recolours to match the latest live
      // status without waiting for the next cron run.
      if (data?.status) {
        setRegionStatuses(prev => {
          const others = prev.filter(s => s.region_id !== region.id);
          return [
            ...others,
            {
              region_id:   region.id,
              status:      data.status,
              confidence:  data.confidence,
              reasoning:   data.reasoning,
              sources:     data.sources ?? [],
              assessed_at: new Date().toISOString(),
            },
          ];
        });
        setStatusGeneratedAt(new Date().toISOString());
        setStatusDemoMode(false);
      }

    } catch (err) {
      // API unavailable — fall back to demo data so the UI always renders
      console.warn('[HydroTwin] Live API unavailable, using demo data:', err.message);
      setAssessment(buildDemoResponse(region));
      setError('Live API unavailable — showing simulated assessment data.');
    } finally {
      setIsLoading(false);
    }
  }, []);

  // ── Region marker click handler ───────────────────────────────────────────
  // Cache-first: the cron-populated /status snapshot already carries status +
  // confidence + reasoning + sources for every region, so we render it
  // instantly instead of spinning up a fresh Bedrock call on every click.
  // Fall back to live /assess only if no snapshot exists for this region
  // (initial load still in flight, /status fetch failed, or first-ever run).
  const handleRegionClick = useCallback((region) => {
    setSelectedRegion(region);
    setReplayDate(null);          // exit any replay mode
    setReplayCuratedEvent(null);
    setError(null);

    const cached = regionStatuses.find(s => s.region_id === region.id);
    if (cached?.status) {
      setAssessment({
        region_id:  region.id,
        status:     cached.status,
        confidence: cached.confidence ?? 0,
        reasoning:  cached.reasoning ?? '',
        sources:    cached.sources ?? [],
      });
      setIsLoading(false);
      return;
    }

    fetchAssessment(region);
  }, [regionStatuses, fetchAssessment]);

  // ── Close panel and return to full-screen map ─────────────────────────────
  const closePanel = useCallback(() => {
    setSelectedRegion(null);
    setAssessment(null);
    setError(null);
    setReplayDate(null);
    setReplayCuratedEvent(null);
  }, []);

  // ── Replay handlers — mutually exclusive ─────────────────────────────────
  // Calendar pick: if the date falls inside a curated event's window, activate
  // that chip (pre-baked data, accurate for basin-driven floods) while keeping
  // the user's chosen date in the picker. Otherwise use OpenMeteo archive.
  const handleReplayDateChange = useCallback((iso) => {
    if (iso && selectedRegion) {
      const events = HISTORICAL_EVENTS[selectedRegion.id] ?? [];
      const matched = events.find((ev) => iso >= ev.dateStart && iso <= ev.dateEnd);
      if (matched) {
        setReplayDate(iso);
        setReplayCuratedEvent(matched);
        return;
      }
    }
    setReplayDate(iso);
    setReplayCuratedEvent(null);
  }, [selectedRegion]);

  // Curated chip pick: switches to curated mode and clears any archive date.
  // Re-clicking the active chip (event === null) exits replay entirely.
  const handleCuratedEventSelect = useCallback((event) => {
    setReplayCuratedEvent(event);
    setReplayDate(null);
  }, []);

  // ── Hover handler — single mousemove is more reliable than enter/leave ──
  const handleMouseMove = useCallback((e) => {
    if (!mapRef.current) return;
    const map = mapRef.current.getMap();
    const feature = e.features?.find(f => f.layer.id === 'municipalities-fill');
    const id = feature?.id ?? null;

    if (id !== hoveredMuniIdRef.current) {
      if (hoveredMuniIdRef.current !== null) {
        map.setFeatureState(
          { source: 'municipalities', id: hoveredMuniIdRef.current },
          { hover: false }
        );
      }
      if (id !== null) {
        map.setFeatureState({ source: 'municipalities', id }, { hover: true });
      }
      hoveredMuniIdRef.current = id;
    }
    map.getCanvas().style.cursor = id !== null ? 'pointer' : '';
  }, []);

  const handleMouseLeave = useCallback(() => {
    if (!mapRef.current) return;
    const map = mapRef.current.getMap();
    if (hoveredMuniIdRef.current !== null) {
      map.setFeatureState(
        { source: 'municipalities', id: hoveredMuniIdRef.current },
        { hover: false }
      );
      hoveredMuniIdRef.current = null;
    }
    map.getCanvas().style.cursor = '';
  }, []);

  // ── Map click — only municipalities are interactive ──────────────────────
  const handleMapClick = useCallback((e) => {
    if (!e.features?.length) return;
    const feature = e.features[0];
    if (feature.layer.id !== 'municipalities-fill') return;
    const bbox = bboxFromGeometry(feature.geometry);
    const muniRegion = {
      id:          feature.properties.GID_2,
      name:        feature.properties.NAME_2,
      description: `${feature.properties.NAME_2} municipality — ${feature.properties.NAME_1} Region`,
      bbox,
    };
    setSelectedRegion(muniRegion);
    setError(null);
    fetchAssessment(muniRegion);
  }, [fetchAssessment]);


  // ─────────────────────────────────────────────────────────────────────────
  return (
    <div className="relative w-screen h-screen bg-gray-950 font-mono">

      {/* ── Topbar ────────────────────────────────────────────────────────── */}
      <header className="absolute top-0 left-0 right-0 z-20 flex items-center gap-3 px-5 py-3 bg-gray-950/90 backdrop-blur-md border-b border-gray-800">
        <span className="text-2xl select-none" aria-hidden="true">💧</span>
        <h1 className="text-base font-bold tracking-widest text-cyan-400 uppercase">
          HydroTwin
        </h1>
        <span className="hidden sm:block text-xs text-gray-500">
          CASSINI Space for Water · Bulgaria Early Warning System
        </span>

        {/* Live pulse indicator */}
        <div className="ml-auto flex items-center gap-1.5 text-xs text-emerald-400 font-semibold">
          <span className="w-2 h-2 bg-emerald-400 rounded-full animate-pulse" aria-hidden="true" />
          LIVE
        </div>
      </header>

      {/* ── Mapbox Map ────────────────────────────────────────────────────── */}
      <Map
        ref={mapRef}
        mapboxAccessToken={MAPBOX_TOKEN}
        initialViewState={INITIAL_VIEW_STATE}
        style={{ width: '100%', height: '100%' }}
        mapStyle="mapbox://styles/mapbox/satellite-streets-v12"
        interactiveLayerIds={['municipalities-fill']}  // only municipalities are interactive
        onClick={handleMapClick}
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
        fog={{
          range:            [0.5, 10],
          color:            '#0c1a2e',
          'high-color':     '#061e43',
          'horizon-blend':  0.05,
          'space-color':    '#000510',
          'star-intensity': 0.6,
        }}
      >
        <NavigationControl position="bottom-right" />
        <ScaleControl      position="bottom-left"  unit="metric" />

        {/* ── Pleven municipality boundaries ──────────────────────────────── */}
        <Source
          id="municipalities"
          type="geojson"
          data={paintedMunicipalities}
          promoteId="GID_2"
        >
          <Layer {...MUNICIPALITIES_FILL_LAYER} />
          <Layer {...MUNICIPALITIES_OUTLINE_LAYER} />
          <Layer
            {...MUNICIPALITIES_SELECTED_LAYER}
            filter={['==', ['get', 'GID_2'], selectedRegion?.id?.startsWith('BGR.') ? selectedRegion.id : '']}
          />
          <Layer {...MUNICIPALITIES_LABEL_LAYER} />
        </Source>

        {/* ── Zone polygon overlays — painted by current status (V2-2) ───── */}
        <Source id="regions" type="geojson" data={paintedRegions} generateId>
          {/* Semi-transparent fill — brightens on hover */}
          <Layer {...FILL_LAYER} />
          {/* Coloured border */}
          <Layer {...OUTLINE_LAYER} />
          {/* Cyan dashed outline on the selected zone */}
          <Layer
            {...SELECTED_LAYER}
            filter={['==', ['get', 'id'], selectedRegion?.id ?? '']}
          />
        </Source>

        {/* ── Oblast boundary labels (non-interactive) ──────────────────── */}
        {REGIONS.map((region) => (
          <Marker
            key={region.id}
            longitude={region.longitude}
            latitude={region.latitude}
            anchor="center"
          >
            <div
              className="pointer-events-none select-none
                         px-2 py-0.5 rounded text-[11px] font-bold
                         text-white/60 drop-shadow-lg"
              style={{ textShadow: '0 0 6px #000, 0 0 3px #000' }}
            >
              {region.name}
            </div>
          </Marker>
        ))}
      </Map>

      {/* ── Status legend + freshness indicator (V2-2) ──────────────────── */}
      <MapLegend
        lastUpdated={latestAssessedAt ?? statusGeneratedAt}
        demoMode={statusDemoMode}
      />

      {/* ── AI Assessment Panel (bottom sheet on mobile, sidebar on desktop) ── */}
      <AlertPanel
        region={selectedRegion}
        assessment={displayedAssessment}
        isLoading={replayCuratedEvent ? false : (replayDate ? replayLoading : isLoading)}
        error={replayDate ? replayError : (replayCuratedEvent ? null : error)}
        onClose={closePanel}
        replayDate={replayDate}
        onReplayDateChange={handleReplayDateChange}
        curatedEvents={regionEvents}
        replayCuratedEvent={replayCuratedEvent}
        onCuratedEventSelect={handleCuratedEventSelect}
      />

      {/* ── Click-to-start hint (only visible before first selection) ─────── */}
      {!selectedRegion && !isLoading && (
        <div
          className="absolute bottom-8 left-1/2 -translate-x-1/2 z-20
                     bg-gray-900/80 border border-gray-700 backdrop-blur-sm
                     text-gray-400 text-xs px-5 py-2.5 rounded-full
                     pointer-events-none select-none"
        >
          Tap a municipality to run AI risk assessment
        </div>
      )}
    </div>
  );
}
