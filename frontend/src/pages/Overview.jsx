/**
 * Overview.jsx — operational-overview page
 * ============================================
 *
 * v3 layout owns the chrome (sidebar + topbar + bottom data-sources bar) via
 * <Layout>. This page renders the map area + AlertPanel inside that frame.
 *
 * Features integrated here:
 *   - V3 cache-first click flow (instant render from /status snapshot)
 *   - V3 Bulgaria outline + status pills + bumped polygon opacity
 *   - 🏛️ Municipalities layer (Leny73 / feature/add-municipilities) — Pleven
 *     split into clickable sub-municipalities with per-municipality assessment
 *   - 🕒 History replay (Leny73 / 20260425-history-replay) — date picker +
 *     curated event chips + OpenMeteo archive fetch, all surfaced in AlertPanel
 *
 * Click semantics (all cache-first now — cron snapshots both oblasts and the
 * 29 GADM municipalities every 30 min into HydroTwinStatus):
 *   - Click an oblast StatusPill (Pleven / Yambol / Burgas) → oblast-level
 *     assessment (cache-first via /status snapshot)
 *   - Click a municipality polygon (any oblast)             → municipality-level
 *     assessment (cache-first via /status snapshot;
 *     falls through to live /assess only if no row exists for that GID_2)
 *   - Click a region polygon outside any municipality       → oblast-level click
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import Map, { Source, Layer, Marker, NavigationControl, ScaleControl } from 'react-map-gl';
import 'mapbox-gl/dist/mapbox-gl.css';

import AlertPanel       from '../components/AlertPanel';
import MapLegend        from '../components/MapLegend';
import StatusPill       from '../components/StatusPill';
import REGIONS_GEOJSON  from '../regions.geojson';
import MUNICIPALITIES_GEOJSON from '../municipalities.geojson';
import HISTORICAL_EVENTS      from '../data/historicalEvents.json';
import { fetchHistoricalAssessment } from '../lib/openmeteo';
import BULGARIA_OUTLINE from '../lib/bulgaria-outline';
import { worstStatus, isAlerting } from '../lib/severity';
import { useDashboardContext } from '../components/Layout';

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN ?? '';
const API_ENDPOINT =
  import.meta.env.VITE_API_ENDPOINT ??
  'https://YOUR_API_ID.execute-api.us-east-1.amazonaws.com/prod/assess';

// Hide motorway/road clutter (A1/A2 shields, road labels, etc.) from the
// satellite-streets style on load. We keep city/place labels and the
// satellite imagery — only road network + road shields are dropped.
const ROAD_LAYER_PATTERN = /^(road|bridge|tunnel|motorway)/i;
const hideRoadLayers = (event) => {
  const map = event.target;
  for (const layer of map.getStyle().layers) {
    if (ROAD_LAYER_PATTERN.test(layer.id)) {
      map.setLayoutProperty(layer.id, 'visibility', 'none');
    }
  }
};

// ── Status → polygon fill colour ─────────────────────────────────────────────
const STATUS_COLORS = {
  SAFE:            '#10B981',
  DROUGHT_WATCH:   '#F59E0B',
  DROUGHT_WARNING: '#F97316',
  FLOOD_WATCH:     '#3B82F6',
  FLOOD_WARNING:   '#EF4444',
};
const NEUTRAL_COLOR = '#64748B';

// ── Monitoring oblasts ───────────────────────────────────────────────────────
const REGIONS = [
  {
    id:          'pleven',
    name:        'Pleven Oblast',
    description: 'Northern Bulgaria — Danube floodplain flood risk; Vit, Osam & Iskur tributaries cross the oblast',
    longitude:   24.62,
    latitude:    43.41,
    bbox:        [23.90, 43.15, 25.20, 43.70],
  },
  {
    id:          'yambol',
    name:        'Yambol Oblast',
    description: 'Southeast Bulgaria — Tundzha river basin; Thracian Lowland drought & flash-flood risk',
    longitude:   26.613,
    latitude:    42.329,
    bbox:        [26.18, 41.94, 27.05, 42.72],
  },
  {
    id:          'burgas',
    name:        'Burgas Oblast',
    description: 'Black Sea coast — river-mouth flooding, storm-surge, Mandra-Poda wetlands',
    longitude:   27.306,
    latitude:    42.440,
    bbox:        [26.58, 41.90, 28.04, 42.98],
  },
];

// ── World mask: dark fill everywhere except Bulgaria ─────────────────────────
// Polygon with a Web-Mercator-safe outer ring (lat ±85°) and Bulgaria's
// outer rings as holes, so the basemap stays visible inside Bulgaria and
// gets dimmed everywhere else.
const WORLD_RING = [
  [-180, -85], [180, -85], [180, 85], [-180, 85], [-180, -85],
];
const BULGARIA_MASK = (() => {
  const geom = BULGARIA_OUTLINE.features[0].geometry;
  const holes =
    geom.type === 'Polygon'
      ? [geom.coordinates[0]]
      : geom.coordinates.map((poly) => poly[0]);
  return {
    type:     'FeatureCollection',
    features: [{
      type:       'Feature',
      properties: {},
      geometry:   { type: 'Polygon', coordinates: [WORLD_RING, ...holes] },
    }],
  };
})();

const BG_MASK_LAYER = {
  id:    'bulgaria-mask',
  type:  'fill',
  paint: {
    'fill-color':   '#0A0F1A',
    'fill-opacity': 0.70,
  },
};

// ── Mapbox layer descriptors ─────────────────────────────────────────────────
const BG_OUTLINE_LAYER = {
  id:    'bulgaria-outline',
  type:  'line',
  paint: {
    'line-color':   '#67E8F9',
    'line-width':   1.5,
    'line-opacity': 0.55,
  },
};

const FILL_LAYER = {
  id:     'regions-fill',
  type:   'fill',
  paint:  {
    'fill-color':   ['get', 'color'],
    'fill-opacity': [
      'case',
      ['boolean', ['feature-state', 'hover'], false], 0.55,
      0.42,
    ],
  },
};

const OUTLINE_LAYER = {
  id:    'regions-outline',
  type:  'line',
  paint: {
    'line-color': ['get', 'color'],
    'line-width': [
      'case',
      ['boolean', ['feature-state', 'hover'], false], 3,
      1.8,
    ],
    'line-opacity': 0.95,
  },
};

const SELECTED_LAYER = {
  id:     'regions-selected',
  type:   'line',
  filter: ['==', ['get', 'id'], ''],
  paint:  {
    'line-color':     '#67E8F9',
    'line-width':     3,
    'line-opacity':   1,
    'line-dasharray': [2, 1],
  },
};

const MUNICIPALITIES_FILL_LAYER = {
  id:   'municipalities-fill',
  type: 'fill',
  paint: {
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
    'line-color':   '#60A5FA',
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
    'text-color':       '#EFF6FF',
    'text-halo-color':  '#1E3A5F',
    'text-halo-width':  2,
    'text-halo-blur':   0,
  },
};

const MUNICIPALITIES_SELECTED_LAYER = {
  id:     'municipalities-selected',
  type:   'line',
  filter: ['==', ['get', 'GID_2'], ''],
  paint:  {
    'line-color':     '#67E8F9',
    'line-width':     3,
    'line-opacity':   1,
    'line-dasharray': [2, 1],
  },
};

const INITIAL_VIEW_STATE = {
  longitude: 25.20,
  latitude:  42.75,
  zoom:      6.6,
};

// ── Helpers ──────────────────────────────────────────────────────────────────
function bboxFromGeometry(geometry) {
  const lons = [], lats = [];
  const collect = (arr) => {
    if (typeof arr[0] === 'number') { lons.push(arr[0]); lats.push(arr[1]); return; }
    arr.forEach(collect);
  };
  collect(geometry.coordinates);
  return [Math.min(...lons), Math.min(...lats), Math.max(...lons), Math.max(...lats)];
}

function bboxCenter(bbox) {
  if (!bbox) return [25.0, 42.7];
  return [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2];
}

// Maps GADM NAME_1 region name → HISTORICAL_EVENTS key so municipality clicks
// surface the same curated event chips as the parent oblast (works for all
// three monitored oblasts — was previously hardcoded to Pleven only).
const REGION_NAME_TO_ID = { Pleven: 'pleven', Yambol: 'yambol', Burgas: 'burgas' };

const buildDemoResponse = (region) => ({
  region_id:  region.id,
  status:     'FLOOD_WATCH',
  confidence: 0.78,
  reasoning:
    '[DEMO MODE] River levels in the Vit and Osam rivers have risen 1.1 m above the seasonal ' +
    'baseline over the past 72 hours. Soil saturation across the area is at 91 %. Precipitation ' +
    'forecast shows an additional 38 mm expected within 24 hours.',
  reasoning_structured: {
    whats_happening: 'Rivers across the area are running well above the seasonal baseline and the ground is nearly saturated.',
    why_it_matters:  'Soil saturation sits at **91%** and another **38 mm of rain** is forecast in 24 h — most of it will run off into already-stressed channels.',
    current_context: 'Spring flow is still elevated and the floodplain has limited capacity for additional surface runoff.',
    next_step:       'Pre-position pumps, brief downstream villages, and review evacuation routes in low-lying districts.',
  },
});

// ─────────────────────────────────────────────────────────────────────────────
export default function Overview() {
  const { regionStatuses, statusDemoMode, lastUpdated, patchRegionStatus, setPageMeta } = useDashboardContext();

  useEffect(() => {
    setPageMeta({
      title:        'Operational overview',
      subtitle:     'Clear insights. Timely action.',
      showSeverity: true,
    });
  }, [setPageMeta]);

  // ── URL deep-linking ────────────────────────────────────────────────────
  // ?region=<id> drives selection on initial load + browser back/forward,
  // and clicks update the URL so users can share/email a deep link to the
  // region panel they're looking at.
  const [searchParams, setSearchParams] = useSearchParams();
  const regionParam = searchParams.get('region');

  // ── Selection / live-fetch state ─────────────────────────────────────────
  const [selectedRegion, setSelectedRegion] = useState(null);
  const [assessment,     setAssessment]     = useState(null);
  const [isLoading,      setIsLoading]      = useState(false);
  const [error,          setError]          = useState(null);
  const [hoveredId,      setHoveredId]      = useState(null);
  const hoveredMuniIdRef                    = useRef(null);

  // History-replay state — 'archive' (date picker) and 'curated' (chips) are
  // mutually exclusive; both flow into displayedAssessment below.
  const [replayDate,         setReplayDate]         = useState(null);
  const [replayCuratedEvent, setReplayCuratedEvent] = useState(null);
  const [replayAssessment,   setReplayAssessment]   = useState(null);
  const [replayLoading,      setReplayLoading]      = useState(false);
  const [replayError,        setReplayError]        = useState(null);

  const mapRef = useRef(null);

  // Curated events for the selected region — municipalities inherit their
  // parent oblast's events via parentRegionId (resolved at click time from
  // GADM NAME_1).
  const regionEvents = useMemo(() => {
    if (!selectedRegion) return [];
    const eventKey = selectedRegion.parentRegionId ?? selectedRegion.id;
    return HISTORICAL_EVENTS[eventKey] ?? [];
  }, [selectedRegion]);

  // OpenMeteo archive fetch when a calendar date is picked
  useEffect(() => {
    if (!replayDate || !selectedRegion) {
      setReplayAssessment(null);
      setReplayError(null);
      return;
    }
    let cancelled = false;
    setReplayLoading(true);
    setReplayError(null);

    const [lng, lat] = bboxCenter(selectedRegion.bbox);
    fetchHistoricalAssessment({
      longitude:  selectedRegion.longitude ?? lng,
      latitude:   selectedRegion.latitude  ?? lat,
      replayDate,
      regionId:   selectedRegion.id,
      regionName: selectedRegion.name,
    })
      .then((result) => { if (!cancelled) setReplayAssessment(result); })
      .catch((err) => {
        if (cancelled) return;
        console.warn('[HydroTwin] OpenMeteo fetch failed:', err.message);
        setReplayError('Could not load archive data — try a different date.');
        setReplayAssessment(null);
      })
      .finally(() => { if (!cancelled) setReplayLoading(false); });

    return () => { cancelled = true; };
  }, [replayDate, selectedRegion]);

  // Curated > archive > live (priority order)
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

  // ── Painted oblast polygons ─────────────────────────────────────────────
  const paintedRegions = useMemo(() => {
    const statusByRegion = Object.fromEntries(
      regionStatuses.map(s => [s.region_id, s.status])
    );
    if (selectedRegion && displayedAssessment?.replay && displayedAssessment?.status) {
      statusByRegion[selectedRegion.id] = displayedAssessment.status;
    }
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
  }, [regionStatuses, selectedRegion, displayedAssessment]);

  // ── Painted municipalities ──────────────────────────────────────────────
  // Same shared snapshot as oblasts — cron writes both into HydroTwinStatus
  // and /status returns them in one array, keyed by region_id (= GID_2 for
  // municipalities). No row → polygon stays neutral until clicked.
  const paintedMunicipalities = useMemo(() => {
    const statusByGid = Object.fromEntries(
      regionStatuses.map(s => [s.region_id, s.status])
    );
    if (selectedRegion && displayedAssessment?.replay && displayedAssessment?.status) {
      statusByGid[selectedRegion.id] = displayedAssessment.status;
    }
    return {
      ...MUNICIPALITIES_GEOJSON,
      features: MUNICIPALITIES_GEOJSON.features.map(f => {
        const status = statusByGid[f.properties.GID_2] ?? null;
        const extra  = status ? { color: STATUS_COLORS[status] ?? NEUTRAL_COLOR } : {};
        return { ...f, properties: { ...f.properties, ...extra } };
      }),
    };
  }, [regionStatuses, selectedRegion, displayedAssessment]);

  // ── Live /assess fetch ──────────────────────────────────────────────────
  const fetchAssessment = useCallback(async (region) => {
    setIsLoading(true);
    setError(null);
    setAssessment(null);

    try {
      const response = await fetch(API_ENDPOINT, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ region_id: region.id, bbox: region.bbox }),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);

      const data = await response.json();
      setAssessment(data);

      // Patch the shared snapshot for both oblasts and municipalities — both
      // share the same DynamoDB table and the /status endpoint returns them
      // in one array, so the next page-load picks the click result up too.
      if (data?.status) {
        patchRegionStatus(region.id, {
          status:                data.status,
          confidence:            data.confidence,
          reasoning:             data.reasoning,
          reasoning_structured:  data.reasoning_structured,
          sources:               data.sources ?? [],
          assessed_at:           new Date().toISOString(),
        });
      }
    } catch (err) {
      console.warn('[HydroTwin] Live API unavailable, using demo data:', err.message);
      setAssessment(buildDemoResponse(region));
      setError('Live API unavailable — showing simulated assessment data.');
    } finally {
      setIsLoading(false);
    }
  }, [patchRegionStatus]);

  // Resolve a region ID (either an oblast slug or a GADM municipality GID)
  // into the {id, name, bbox, longitude, latitude, parentRegionId} shape the
  // panel + click handlers expect. Returns null if the ID isn't recognised.
  const findRegionById = useCallback((id) => {
    if (!id) return null;
    const oblast = REGIONS.find(r => r.id === id);
    if (oblast) return oblast;
    const muni = MUNICIPALITIES_GEOJSON.features.find(
      f => f.properties.GID_2 === id
    );
    if (!muni) return null;
    const bbox = bboxFromGeometry(muni.geometry);
    return {
      id:             muni.properties.GID_2,
      name:           muni.properties.NAME_2,
      description:    `${muni.properties.NAME_2} municipality — ${muni.properties.NAME_1} Region`,
      bbox,
      longitude:      (bbox[0] + bbox[2]) / 2,
      latitude:       (bbox[1] + bbox[3]) / 2,
      parentRegionId: REGION_NAME_TO_ID[muni.properties.NAME_1] ?? null,
    };
  }, []);

  // ── Cache-first oblast click ────────────────────────────────────────────
  const handleRegionClick = useCallback((region) => {
    setSelectedRegion(region);
    // Mirror the selection into the URL so the panel state is shareable +
    // survives browser back/forward. `replace: false` so back returns to the
    // map view (no selection) before this page's previous route entry.
    setSearchParams({ region: region.id }, { replace: false });
    setReplayDate(null);
    setReplayCuratedEvent(null);
    setError(null);

    const cached = regionStatuses.find(s => s.region_id === region.id);
    if (cached?.status) {
      setAssessment({
        region_id:             region.id,
        status:                cached.status,
        confidence:            cached.confidence ?? 0,
        reasoning:             cached.reasoning  ?? '',
        reasoning_structured:  cached.reasoning_structured,
        sources:               cached.sources    ?? [],
      });
      setIsLoading(false);
      return;
    }
    fetchAssessment(region);
  }, [regionStatuses, fetchAssessment, setSearchParams]);

  const closePanel = useCallback(() => {
    setSelectedRegion(null);
    setAssessment(null);
    setError(null);
    setReplayDate(null);
    setReplayCuratedEvent(null);
    // Clear ?region from the URL but keep any other params the layout cares
    // about. Today there are none on /, but writing it this way is forward-safe.
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.delete('region');
      return next;
    }, { replace: false });
  }, [setSearchParams]);

  // ── Open from URL on mount + on back/forward navigation ────────────────
  // Runs whenever ?region= changes. We deliberately skip selectedRegion in
  // the deps — clicking already syncs the URL, so re-running on selection
  // change would just be a no-op or worse, a feedback loop.
  useEffect(() => {
    if (!regionParam) return;
    if (selectedRegion?.id === regionParam) return;
    const region = findRegionById(regionParam);
    if (region) handleRegionClick(region);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional one-way URL→state sync
  }, [regionParam]);

  // ── Replay handlers ─────────────────────────────────────────────────────
  const handleReplayDateChange = useCallback((iso) => {
    if (iso && selectedRegion) {
      const matched = regionEvents.find((ev) => iso >= ev.dateStart && iso <= ev.dateEnd);
      if (matched) {
        setReplayDate(iso);
        setReplayCuratedEvent(matched);
        return;
      }
    }
    setReplayDate(iso);
    setReplayCuratedEvent(null);
  }, [selectedRegion, regionEvents]);

  const handleCuratedEventSelect = useCallback((event) => {
    setReplayCuratedEvent(event);
    setReplayDate(null);
  }, []);

  // ── Hover handlers — read both fill layers ──────────────────────────────
  const handleMouseMove = useCallback((e) => {
    if (!mapRef.current) return;
    const map = mapRef.current.getMap();
    const muni = e.features?.find(f => f.layer.id === 'municipalities-fill');
    const reg  = e.features?.find(f => f.layer.id === 'regions-fill');

    const muniId = muni?.id ?? null;
    if (muniId !== hoveredMuniIdRef.current) {
      if (hoveredMuniIdRef.current !== null) {
        map.setFeatureState(
          { source: 'municipalities', id: hoveredMuniIdRef.current },
          { hover: false }
        );
      }
      if (muniId !== null) {
        map.setFeatureState({ source: 'municipalities', id: muniId }, { hover: true });
      }
      hoveredMuniIdRef.current = muniId;
    }

    const regId = reg?.id ?? null;
    if (regId !== hoveredId) {
      if (hoveredId !== null) {
        map.setFeatureState({ source: 'regions', id: hoveredId }, { hover: false });
      }
      if (regId !== null) {
        map.setFeatureState({ source: 'regions', id: regId }, { hover: true });
      }
      setHoveredId(regId);
    }

    map.getCanvas().style.cursor = (muniId !== null || regId !== null) ? 'pointer' : '';
  }, [hoveredId]);

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
    if (hoveredId !== null) {
      map.setFeatureState({ source: 'regions', id: hoveredId }, { hover: false });
      setHoveredId(null);
    }
    map.getCanvas().style.cursor = '';
  }, [hoveredId]);

  // Click: prefer a municipality if one is under the cursor; else fall
  // through to the oblast-level region polygon. Both branches are now
  // cache-first against the shared /status snapshot.
  const handleMapClick = useCallback((e) => {
    if (!e.features?.length) return;
    const muni = e.features.find(f => f.layer.id === 'municipalities-fill');
    if (muni) {
      const bbox = bboxFromGeometry(muni.geometry);
      const muniRegion = {
        id:             muni.properties.GID_2,
        name:           muni.properties.NAME_2,
        description:    `${muni.properties.NAME_2} municipality — ${muni.properties.NAME_1} Region`,
        bbox,
        longitude:      (bbox[0] + bbox[2]) / 2,
        latitude:       (bbox[1] + bbox[3]) / 2,
        parentRegionId: REGION_NAME_TO_ID[muni.properties.NAME_1] ?? null,
      };
      handleRegionClick(muniRegion);
      return;
    }

    const reg = e.features.find(f => f.layer.id === 'regions-fill');
    if (reg) {
      const region = REGIONS.find(r => r.id === reg.properties.id);
      if (region) handleRegionClick(region);
    }
  }, [handleRegionClick]);

  const statusFor = (regionId) =>
    regionStatuses.find(s => s.region_id === regionId)?.status ?? null;

  // ── Oblast pill aggregates ──────────────────────────────────────────────
  // The oblast Bedrock assessment averages metrics across the whole footprint,
  // so its verdict can read "SAFE" while individual municipalities underneath
  // are stressed. We roll the pill up to max(oblast, ...children) so the badge
  // never visually contradicts the polygons it sits on. The breakdown chip
  // ("2/5") shows how many child municipalities are at-or-above WATCH — only
  // when at least one child is alerting, to keep the pill quiet otherwise.
  const oblastAggregates = useMemo(() => {
    const statusByKey = Object.fromEntries(
      regionStatuses.map(s => [s.region_id, s.status])
    );
    const childrenByOblast = {};
    for (const f of MUNICIPALITIES_GEOJSON.features) {
      const parentId = REGION_NAME_TO_ID[f.properties.NAME_1];
      if (!parentId) continue;
      (childrenByOblast[parentId] ??= []).push(f.properties.GID_2);
    }

    const out = {};
    for (const region of REGIONS) {
      const oblastStatus = statusByKey[region.id] ?? null;
      const childGids    = childrenByOblast[region.id] ?? [];
      const childStatuses = childGids
        .map(gid => statusByKey[gid])
        .filter(Boolean);

      const status      = worstStatus([oblastStatus, ...childStatuses]);
      const alertingN   = childStatuses.filter(isAlerting).length;
      const totalN      = childGids.length;

      out[region.id] = {
        status,
        breakdown: alertingN > 0 ? { count: alertingN, total: totalN } : null,
      };
    }
    return out;
  }, [regionStatuses]);

  return (
    <div className="absolute inset-0">
      <Map
        ref={mapRef}
        mapboxAccessToken={MAPBOX_TOKEN}
        initialViewState={INITIAL_VIEW_STATE}
        style={{ width: '100%', height: '100%' }}
        mapStyle="mapbox://styles/mapbox/satellite-streets-v12"
        interactiveLayerIds={['municipalities-fill', 'regions-fill']}
        onClick={handleMapClick}
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
        onLoad={hideRoadLayers}
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

        <Source id="bulgaria-mask" type="geojson" data={BULGARIA_MASK}>
          <Layer {...BG_MASK_LAYER} />
        </Source>

        <Source id="bulgaria-outline" type="geojson" data={BULGARIA_OUTLINE}>
          <Layer {...BG_OUTLINE_LAYER} />
        </Source>

        <Source id="regions" type="geojson" data={paintedRegions} generateId>
          <Layer {...FILL_LAYER} />
          <Layer {...OUTLINE_LAYER} />
          <Layer
            {...SELECTED_LAYER}
            filter={[
              '==',
              ['get', 'id'],
              selectedRegion?.id?.startsWith('BGR.') ? '' : (selectedRegion?.id ?? ''),
            ]}
          />
        </Source>

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
            filter={[
              '==',
              ['get', 'GID_2'],
              selectedRegion?.id?.startsWith('BGR.') ? selectedRegion.id : '',
            ]}
          />
          <Layer {...MUNICIPALITIES_LABEL_LAYER} />
        </Source>

        {REGIONS.map(region => {
          const agg = oblastAggregates[region.id] ?? {};
          return (
            <Marker
              key={region.id}
              longitude={region.longitude}
              latitude={region.latitude}
              anchor="center"
            >
              <StatusPill
                regionName={region.name}
                status={agg.status ?? statusFor(region.id)}
                breakdown={agg.breakdown}
                isActive={selectedRegion?.id === region.id}
                onClick={() => handleRegionClick(region)}
              />
            </Marker>
          );
        })}
      </Map>

      <MapLegend
        lastUpdated={lastUpdated}
        demoMode={statusDemoMode}
      />

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

      {!selectedRegion && !isLoading && (
        <div
          className="absolute left-1/2 -translate-x-1/2 z-20
                     bg-gray-900/85 border border-gray-700 backdrop-blur-sm
                     text-gray-400 text-xs px-5 py-2.5 rounded-full
                     pointer-events-none select-none"
          style={{ bottom: 'calc(1.5rem + env(safe-area-inset-bottom, 0px))' }}
        >
          Tap a region to view assessment
        </div>
      )}
    </div>
  );
}
