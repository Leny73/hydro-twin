/**
 * fetch-bg-boundaries.mjs
 * ==============================================================
 * One-shot data prep that swaps the map's polygons over to the
 * official EU source (Eurostat GISCO NUTS / LAU, EPSG:4326, 1:1M)
 * while keeping the GADM-style `GID_2` IDs the backend cache,
 * cron orchestrator and DynamoDB rows already depend on.
 *
 * Outputs (overwrites in place):
 *   frontend/src/lib/bulgaria-outline.js   — NUTS-0  (country)
 *   frontend/src/regions.geojson           — NUTS-3  (Pleven / Yambol / Burgas)
 *   frontend/src/municipalities.geojson    — LAU 2021 geometry +
 *                                            GADM `GID_2 / NAME_1 / NAME_2`
 *
 * Why mix LAU geometry with GADM IDs?
 *   `backend/regions.py` MUNICIPALITIES + REGION_NAMES are keyed by GADM
 *   `GID_2` (e.g. `BGR.13.10_1`). The frontend's cache-first click handler,
 *   the cron job, and the DynamoDB snapshot all share that key. Swapping
 *   to Eurostat LAU codes would break every cached row and force a Lambda
 *   redeploy. We only need the *shape* to be authoritative — so we keep
 *   the IDs and only swap geometry.
 *
 * Usage:
 *   node scripts/fetch-bg-boundaries.mjs
 *
 * Requires Node 18+ (uses built-in fetch).
 */

import { readFile, writeFile } from 'node:fs/promises';
import { dirname, join }       from 'node:path';
import { fileURLToPath }       from 'node:url';

const __dirname  = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT  = join(__dirname, '..');
const FRONTEND   = join(REPO_ROOT, 'frontend');

const NUTS_LVL0  = 'https://gisco-services.ec.europa.eu/distribution/v2/nuts/geojson/NUTS_RG_01M_2021_4326_LEVL_0.geojson';
const NUTS_LVL3  = 'https://gisco-services.ec.europa.eu/distribution/v2/nuts/geojson/NUTS_RG_01M_2021_4326_LEVL_3.geojson';
const LAU_2021   = 'https://gisco-services.ec.europa.eu/distribution/v2/lau/geojson/LAU_RG_01M_2021_4326.geojson';

// NUTS-3 codes per Eurostat 2021 nomenclature
const OBLASTS = [
  {
    nuts:        'BG314',
    id:          'pleven',
    name:        'Pleven Oblast',
    description: 'Northern Bulgaria — Danube floodplain flood risk; Vit, Osam & Iskur tributaries cross the oblast',
    color:       '#3B82F6',
  },
  {
    nuts:        'BG343',
    id:          'yambol',
    name:        'Yambol Oblast',
    description: 'Southeast Bulgaria — Tundzha river basin; Thracian Lowland drought & flash-flood risk',
    color:       '#3B82F6',
  },
  {
    nuts:        'BG341',
    id:          'burgas',
    name:        'Burgas Oblast',
    description: 'Black Sea coast — river-mouth flooding, storm-surge, Mandra-Poda wetlands',
    color:       '#3B82F6',
  },
];

// ── Geometry helpers ─────────────────────────────────────────────────────
function pointInRing([x, y], ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    const denom = (yj - yi) || 1e-12;
    const intersect = ((yi > y) !== (yj > y)) &&
                      (x < ((xj - xi) * (y - yi)) / denom + xi);
    if (intersect) inside = !inside;
  }
  return inside;
}

function pointInPolygon(pt, polygon) {
  if (!pointInRing(pt, polygon[0])) return false;
  for (let i = 1; i < polygon.length; i++) {
    if (pointInRing(pt, polygon[i])) return false;
  }
  return true;
}

function pointInGeometry(pt, geom) {
  if (geom.type === 'Polygon')      return pointInPolygon(pt, geom.coordinates);
  if (geom.type === 'MultiPolygon') return geom.coordinates.some(p => pointInPolygon(pt, p));
  return false;
}

function bboxOfGeometry(geom) {
  let minLon = Infinity, minLat = Infinity, maxLon = -Infinity, maxLat = -Infinity;
  const visit = (arr) => {
    if (typeof arr[0] === 'number') {
      if (arr[0] < minLon) minLon = arr[0];
      if (arr[0] > maxLon) maxLon = arr[0];
      if (arr[1] < minLat) minLat = arr[1];
      if (arr[1] > maxLat) maxLat = arr[1];
      return;
    }
    arr.forEach(visit);
  };
  visit(geom.coordinates);
  return [minLon, minLat, maxLon, maxLat];
}

/** Bbox-center centroid — good enough to test "is this centroid inside polygon X". */
function centroidOfGeometry(geom) {
  const [minLon, minLat, maxLon, maxLat] = bboxOfGeometry(geom);
  return [(minLon + maxLon) / 2, (minLat + maxLat) / 2];
}

/** Area of the intersection of two bboxes [minLon, minLat, maxLon, maxLat]. */
function bboxOverlapArea(a, b) {
  const dx = Math.min(a[2], b[2]) - Math.max(a[0], b[0]);
  const dy = Math.min(a[3], b[3]) - Math.max(a[1], b[1]);
  return dx > 0 && dy > 0 ? dx * dy : 0;
}

// ── Fetch ────────────────────────────────────────────────────────────────
async function fetchJson(url, label) {
  process.stdout.write(`→ ${label} ... `);
  const t0 = Date.now();
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${label}: HTTP ${res.status}`);
  const j = await res.json();
  console.log(`✓ ${j.features?.length ?? 0} features (${((Date.now() - t0) / 1000).toFixed(1)}s)`);
  return j;
}

// ── Step 1: Bulgaria national outline (NUTS-0) ───────────────────────────
async function buildBulgariaOutline() {
  const fc = await fetchJson(NUTS_LVL0, 'NUTS-0 (countries)');
  const bg = fc.features.find(f =>
    (f.properties?.CNTR_CODE ?? f.properties?.NUTS_ID ?? f.id) === 'BG'
  );
  if (!bg) throw new Error('NUTS-0: Bulgaria not found');

  const out = {
    type:     'FeatureCollection',
    features: [{
      type:       'Feature',
      properties: { name: 'Bulgaria' },
      geometry:   bg.geometry,
    }],
  };
  const js =
`/**
 * bulgaria-outline.js — Eurostat NUTS-0 (1:1M, 2021, EPSG:4326)
 * Fetched from ${NUTS_LVL0}
 * via scripts/fetch-bg-boundaries.mjs. Used as a thin cyan layer on the
 * operational-overview map so Bulgaria reads at a glance against the dark
 * satellite basemap.
 */

const BULGARIA_OUTLINE = ${JSON.stringify(out)};

export default BULGARIA_OUTLINE;
`;
  await writeFile(join(FRONTEND, 'src/lib/bulgaria-outline.js'), js, 'utf8');
  console.log('  ✓ frontend/src/lib/bulgaria-outline.js');
}

// ── Step 2: NUTS-3 oblasts ───────────────────────────────────────────────
async function buildOblasts() {
  const fc = await fetchJson(NUTS_LVL3, 'NUTS-3 (regions)');
  const features = OBLASTS.map(o => {
    const found = fc.features.find(f =>
      (f.properties?.NUTS_ID ?? f.id) === o.nuts
    );
    if (!found) throw new Error(`NUTS-3: ${o.nuts} (${o.name}) not found`);
    return {
      type:       'Feature',
      id:         o.id,
      properties: {
        id:          o.id,
        nuts_id:     o.nuts,
        name:        o.name,
        description: o.description,
        color:       o.color,
      },
      geometry: found.geometry,
    };
  });
  const out = { type: 'FeatureCollection', features };
  await writeFile(join(FRONTEND, 'src/regions.geojson'), JSON.stringify(out), 'utf8');
  console.log(`  ✓ frontend/src/regions.geojson (${features.length} oblasts)`);
  return features;
}

// ── Step 3: LAU geometry + GADM IDs ──────────────────────────────────────
async function buildMunicipalities(oblastFeatures) {
  // Read existing GADM file BEFORE we overwrite it. We use it to map every
  // LAU polygon to the GADM `GID_2` the backend already keys cache rows by.
  const gadmRaw = await readFile(join(FRONTEND, 'src/municipalities.geojson'), 'utf8');
  const gadm    = JSON.parse(gadmRaw);
  const gadmIndex = gadm.features.map(f => ({
    feature:  f,
    centroid: centroidOfGeometry(f.geometry),
    bbox:     bboxOfGeometry(f.geometry),
  }));
  console.log(`  ✓ Read ${gadm.features.length} GADM features (legacy IDs)`);

  // Pull the EU LAU file. It's the heavy one — ~150 MB JSON.
  const fc  = await fetchJson(LAU_2021, 'LAU 2021 (all EU)');
  const bg  = fc.features.filter(f =>
    (f.properties?.CNTR_CODE ?? f.properties?.cntr_code) === 'BG'
  );
  console.log(`  ✓ ${bg.length} LAUs in BG`);

  // Spatial intersect: keep only LAUs whose centroid sits inside one of the
  // three monitored oblasts. Then attach the matching GADM ID/name.
  const out = [];
  let unmatchedGadm = 0;
  const usedGadm = new Set();
  for (const lau of bg) {
    const lauCentroid = centroidOfGeometry(lau.geometry);
    const oblast = oblastFeatures.find(o => pointInGeometry(lauCentroid, o.geometry));
    if (!oblast) continue;

    // Match in three layers: GADM-centroid-in-LAU, LAU-centroid-in-GADM,
    // then largest-bbox-overlap. Bbox-center centroids can fall outside an
    // irregular polygon (e.g. coastal municipality with concave outline),
    // so the bbox-overlap fallback rescues the few stubborn cases.
    const lauBbox = bboxOfGeometry(lau.geometry);
    const eligible = gadmIndex.filter(g => !usedGadm.has(g.feature.properties.GID_2));

    let matched = eligible.find(g => pointInGeometry(g.centroid, lau.geometry));
    if (!matched) matched = eligible.find(g => pointInGeometry(lauCentroid, g.feature.geometry));
    if (!matched) {
      let bestArea = 0;
      for (const g of eligible) {
        const area = bboxOverlapArea(lauBbox, g.bbox);
        if (area > bestArea) { bestArea = area; matched = g; }
      }
    }
    if (!matched) {
      unmatchedGadm++;
      console.warn(`    ⚠️  No GADM match for LAU "${lau.properties?.LAU_NAME ?? '?'}" (${lau.properties?.LAU_ID ?? '?'})`);
      continue;
    }
    usedGadm.add(matched.feature.properties.GID_2);

    out.push({
      type:       'Feature',
      properties: {
        // Backend-cache keys (GADM, unchanged)
        GID_2:  matched.feature.properties.GID_2,
        NAME_1: matched.feature.properties.NAME_1,
        NAME_2: matched.feature.properties.NAME_2,
        // Eurostat reference (informational)
        LAU_ID:   lau.properties?.LAU_ID,
        LAU_NAME: lau.properties?.LAU_NAME,
      },
      geometry: lau.geometry,
    });
  }

  console.log(`  ✓ Matched ${out.length}/${bg.length} LAUs to GADM IDs (${unmatchedGadm} unmatched)`);
  await writeFile(
    join(FRONTEND, 'src/municipalities.geojson'),
    JSON.stringify({ type: 'FeatureCollection', features: out }),
    'utf8',
  );
  console.log('  ✓ frontend/src/municipalities.geojson');
}

// ── Run ──────────────────────────────────────────────────────────────────
console.log('🌍 Eurostat GISCO boundary refresh (NUTS-0, NUTS-3, LAU 2021)\n');
await buildBulgariaOutline();
const oblasts = await buildOblasts();
await buildMunicipalities(oblasts);
console.log('\n✅ Done.');
