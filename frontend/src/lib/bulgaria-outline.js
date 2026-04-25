/**
 * bulgaria-outline.js — simplified Bulgaria country boundary
 * ============================================================
 *
 * Hand-simplified national outline (~50 vertices) used as a thin cyan layer
 * on the operational-overview map so Bulgaria reads at a glance against the
 * dark satellite basemap. Avoids a runtime fetch / CDN dependency.
 *
 * Source: Natural Earth 1:50m admin-0 boundaries, manually decimated.
 * Accuracy is "shape-recognisable" — fine for visual emphasis, not for any
 * geometric calculation.
 */

const BULGARIA_OUTLINE = {
  type: 'FeatureCollection',
  features: [
    {
      type: 'Feature',
      properties: { name: 'Bulgaria' },
      geometry: {
        type: 'Polygon',
        coordinates: [[
          [22.35, 44.22],
          [22.66, 44.20],
          [22.94, 43.81],
          [23.40, 43.85],
          [23.66, 43.81],
          [24.10, 43.74],
          [24.62, 43.74],
          [25.34, 43.69],
          [26.05, 43.94],
          [26.65, 44.13],
          [27.50, 44.18],
          [28.04, 43.74],
          [27.97, 43.42],
          [28.06, 42.99],
          [27.79, 42.65],
          [27.80, 42.30],
          [28.02, 42.07],
          [27.71, 41.97],
          [27.40, 42.00],
          [27.01, 42.07],
          [26.62, 41.96],
          [26.32, 41.71],
          [26.10, 41.32],
          [25.81, 41.32],
          [25.41, 41.24],
          [24.78, 41.55],
          [24.50, 41.56],
          [23.79, 41.41],
          [23.42, 41.40],
          [22.92, 41.34],
          [22.88, 41.99],
          [22.50, 42.32],
          [22.43, 42.58],
          [22.55, 42.85],
          [22.34, 43.00],
          [22.41, 43.20],
          [22.55, 43.46],
          [22.99, 43.81],
          [22.69, 44.10],
          [22.35, 44.22],
        ]],
      },
    },
  ],
};

export default BULGARIA_OUTLINE;
