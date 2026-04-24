/**
 * App.jsx — HydroTwin Main Application
 * ========================================
 *
 * Architecture:
 *   1. react-map-gl renders a full-screen Mapbox satellite map.
 *   2. REGIONS defines the five clickable monitoring zones (EU + Africa,
 *      aligned with the CASSINI Space for Water focus area).
 *   3. Clicking a region Marker fires a POST to the API Gateway → Lambda.
 *   4. The Lambda response (status, confidence, reasoning) is passed to
 *      AlertPanel, which renders the side panel overlay.
 *
 * Environment variables required (.env.local):
 *   VITE_MAPBOX_TOKEN  – Mapbox public access token
 *   VITE_API_ENDPOINT  – API Gateway endpoint URL
 */

import { useState, useCallback } from 'react';
import Map, { Marker, NavigationControl, ScaleControl } from 'react-map-gl';
import 'mapbox-gl/dist/mapbox-gl.css';
import AlertPanel from './components/AlertPanel';

// ── API / Token configuration ─────────────────────────────────────────────────
const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN ?? '';
const API_ENDPOINT =
  import.meta.env.VITE_API_ENDPOINT ??
  'https://YOUR_API_ID.execute-api.us-east-1.amazonaws.com/prod/assess';

// ── Monitoring regions (CASSINI / Copernicus focus: EU + Africa) ──────────────
// Each region has a centre point for the map marker and a bbox for the extractor.
const REGIONS = [
  {
    id:          'mediterranean-basin',
    name:        'Mediterranean Basin',
    description: 'High drought risk zone — Iberian + North African coast',
    longitude:   13.5,
    latitude:    37.5,
    bbox:        [-6.0, 30.0, 37.0, 47.0],
    color:       '#F59E0B', // amber
  },
  {
    id:          'sahel-region',
    name:        'Sahel Region',
    description: 'Chronic drought belt — 12 °N latitude band across sub-Saharan Africa',
    longitude:   15.0,
    latitude:    14.0,
    bbox:        [-17.0, 10.0, 40.0, 20.0],
    color:       '#EF4444', // red
  },
  {
    id:          'danube-basin',
    name:        'Danube River Basin',
    description: 'Central EU — seasonal snowmelt flood risk (spring peak)',
    longitude:   22.0,
    latitude:    47.5,
    bbox:        [8.0, 42.0, 30.0, 52.0],
    color:       '#3B82F6', // blue
  },
  {
    id:          'po-valley',
    name:        'Po Valley, Italy',
    description: 'Northern Italy agricultural corridor — autumn flash flood risk',
    longitude:   11.0,
    latitude:    45.0,
    bbox:        [6.5, 43.5, 14.5, 46.5],
    color:       '#3B82F6', // blue
  },
  {
    id:          'nile-delta',
    name:        'Nile Delta',
    description: 'Water stress, saltwater intrusion & seasonal Nile flood monitoring',
    longitude:   31.0,
    latitude:    30.5,
    bbox:        [25.0, 22.0, 37.0, 32.0],
    color:       '#F59E0B', // amber
  },
];

// ── Initial map viewport ───────────────────────────────────────────────────────
const INITIAL_VIEW_STATE = {
  longitude: 20.0,
  latitude:  35.0,
  zoom:      3.2,
};

// ── Simulated demo response (shown when the live API is unavailable) ──────────
const buildDemoResponse = (region) => ({
  region_id:  region.id,
  status:     'FLOOD_WATCH',
  confidence: 0.78,
  reasoning:
    '[DEMO MODE] River levels in this zone have risen 0.8 m above the seasonal ' +
    'baseline over the past 72 hours. Soil saturation is at 89 %. Precipitation ' +
    'forecast shows an additional 35 mm expected within 24 hours. Two of the ' +
    'three FLOOD_WATCH thresholds are breached — elevated risk of flash flooding.',
});

// ─────────────────────────────────────────────────────────────────────────────
export default function App() {
  // ── State ─────────────────────────────────────────────────────────────────
  const [selectedRegion, setSelectedRegion] = useState(null); // region object
  const [assessment,     setAssessment]     = useState(null); // Bedrock response
  const [isLoading,      setIsLoading]      = useState(false);
  const [error,          setError]          = useState(null); // non-fatal warning

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
          CASSINI Space for Water · Multi-region Early Warning System
        </span>

        {/* Live pulse indicator */}
        <div className="ml-auto flex items-center gap-1.5 text-xs text-emerald-400 font-semibold">
          <span className="w-2 h-2 bg-emerald-400 rounded-full animate-pulse" aria-hidden="true" />
          LIVE
        </div>
      </header>

      {/* ── Mapbox Map ────────────────────────────────────────────────────── */}
      <Map
        mapboxAccessToken={MAPBOX_TOKEN}
        initialViewState={INITIAL_VIEW_STATE}
        style={{ width: '100%', height: '100%' }}
        mapStyle="mapbox://styles/mapbox/satellite-streets-v12"
        // Fog gives the globe-like atmosphere effect on satellite style
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

        {/* ── Region Markers ──────────────────────────────────────────────── */}
        {REGIONS.map((region) => (
          <Marker
            key={region.id}
            longitude={region.longitude}
            latitude={region.latitude}
            anchor="center"
          >
            {/*
             * The click handler lives on the <button> (not the Marker) so it
             * works correctly in react-map-gl v7 without event propagation issues.
             */}
            <button
              onClick={() => handleRegionClick(region)}
              // 44×44px minimum touch target (WCAG 2.5.5) — critical for mobile
              className="group relative flex items-center justify-center
                         min-w-[44px] min-h-[44px] focus:outline-none"
              title={region.name}
              aria-label={`Assess ${region.name}`}
            >
              {/* Pulse ring — animates continuously to draw attention */}
              <span
                className="absolute w-10 h-10 rounded-full opacity-25 animate-ping"
                style={{ backgroundColor: region.color }}
                aria-hidden="true"
              />
              {/* Core dot — highlighted on hover / when selected */}
              <span
                className={`
                  relative w-5 h-5 rounded-full border-2 border-white shadow-lg
                  cursor-pointer transition-transform duration-150
                  group-hover:scale-125
                  ${selectedRegion?.id === region.id ? 'scale-125 border-cyan-300' : ''}
                `}
                style={{ backgroundColor: region.color }}
              />
              {/* Hover label */}
              <span
                className="absolute top-7 left-1/2 -translate-x-1/2 whitespace-nowrap
                           text-white text-[10px] font-semibold drop-shadow-lg
                           bg-gray-900/80 px-1.5 py-0.5 rounded
                           pointer-events-none
                           opacity-0 group-hover:opacity-100 transition-opacity duration-150"
              >
                {region.name}
              </span>
            </button>
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
