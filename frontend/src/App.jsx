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

import { useState, useCallback, useRef } from 'react';
import Map, { Source, Layer, Marker, NavigationControl, ScaleControl } from 'react-map-gl';
import 'mapbox-gl/dist/mapbox-gl.css';
import AlertPanel from './components/AlertPanel';
import REGIONS_GEOJSON from './regions.geojson';

// ── API / Token configuration ─────────────────────────────────────────────────
const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN ?? '';
const API_ENDPOINT =
  import.meta.env.VITE_API_ENDPOINT ??
  'https://YOUR_API_ID.execute-api.us-east-1.amazonaws.com/prod/assess';

// ── Monitoring regions — Pleven Oblast focus ─────────────────────────────────
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
];

// REGIONS_GEOJSON is imported from ./regions.geojson
// Edit that file to update zone polygon boundaries without touching this file.

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
  longitude: 24.62,
  latitude:  43.42,
  zoom:      9.0,
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
export default function App() {
  // ── State ─────────────────────────────────────────────────────────────────
  const [selectedRegion, setSelectedRegion] = useState(null);
  const [assessment,     setAssessment]     = useState(null);
  const [isLoading,      setIsLoading]      = useState(false);
  const [error,          setError]          = useState(null);
  const [hoveredId,      setHoveredId]      = useState(null); // for hover feature-state

  // mapRef lets us call map.setFeatureState for hover highlighting
  const mapRef = useRef(null);

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
  const handleRegionClick = useCallback((region) => {
    setSelectedRegion(region);
    fetchAssessment(region);
  }, [fetchAssessment]);

  // ── Close panel and return to full-screen map ─────────────────────────────
  const closePanel = useCallback(() => {
    setSelectedRegion(null);
    setAssessment(null);
    setError(null);
  }, []);

  // ── Hover handlers — update Mapbox feature-state for fill opacity/outline ─
  const handleMouseEnter = useCallback((e) => {
    if (!mapRef.current || !e.features?.length) return;
    const map = mapRef.current.getMap();
    const id  = e.features[0].id;
    if (hoveredId !== null && hoveredId !== id) {
      map.setFeatureState({ source: 'regions', id: hoveredId }, { hover: false });
    }
    map.setFeatureState({ source: 'regions', id }, { hover: true });
    map.getCanvas().style.cursor = 'pointer';
    setHoveredId(id);
  }, [hoveredId]);

  const handleMouseLeave = useCallback(() => {
    if (!mapRef.current || hoveredId === null) return;
    const map = mapRef.current.getMap();
    map.setFeatureState({ source: 'regions', id: hoveredId }, { hover: false });
    map.getCanvas().style.cursor = '';
    setHoveredId(null);
  }, [hoveredId]);

  // ── Map click — detect which zone was tapped/clicked ─────────────────────
  const handleMapClick = useCallback((e) => {
    if (!e.features?.length) return;
    const regionId = e.features[0].properties.id;
    const region   = REGIONS.find(r => r.id === regionId);
    if (region) handleRegionClick(region);
  }, [handleRegionClick]);


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
        interactiveLayerIds={['regions-fill']}  // enables onClick + onMouseEnter per feature
        onClick={handleMapClick}
        onMouseEnter={handleMouseEnter}
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

        {/* ── Zone polygon overlays ───────────────────────────────────────── */}
        <Source id="regions" type="geojson" data={REGIONS_GEOJSON}>
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

        {/* ── Zone name labels — centred on each region ──────────────────── */}
        {REGIONS.map((region) => (
          <Marker
            key={region.id}
            longitude={region.longitude}
            latitude={region.latitude}
            anchor="center"
          >
            <div
              onClick={() => handleRegionClick(region)}
              className="pointer-events-auto cursor-pointer select-none
                         px-2 py-0.5 rounded text-[11px] font-bold
                         text-white drop-shadow-lg
                         transition-opacity duration-150"
              style={{
                textShadow: '0 0 6px #000, 0 0 3px #000',
                opacity: hoveredId === region.id || selectedRegion?.id === region.id ? 1 : 0.75,
              }}
              aria-label={`Assess ${region.name}`}
            >
              {region.name}
            </div>
          </Marker>
        ))}
      </Map>

      {/* ── AI Assessment Panel (bottom sheet on mobile, sidebar on desktop) ── */}
      <AlertPanel
        region={selectedRegion}
        assessment={assessment}
        isLoading={isLoading}
        error={error}
        onClose={closePanel}
      />

      {/* ── Click-to-start hint (only visible before first selection) ─────── */}
      {!selectedRegion && !isLoading && (
        <div
          className="absolute bottom-8 left-1/2 -translate-x-1/2 z-20
                     bg-gray-900/80 border border-gray-700 backdrop-blur-sm
                     text-gray-400 text-xs px-5 py-2.5 rounded-full
                     pointer-events-none select-none"
        >
          Tap a region marker to run AI risk assessment
        </div>
      )}
    </div>
  );
}
