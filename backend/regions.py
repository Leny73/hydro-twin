"""
regions.py — Single source of truth for monitored regions
==========================================================

Imported by:
  - subscribe_handler.py (KNOWN_REGIONS whitelist)
  - cron_handler.py      (iterate regions, look up bbox)
  - status_handler.py    (whitelist filter on table scan)

Adding a region:
  1. Append to REGIONS dict here (id → bbox)
  2. Add the polygon feature to frontend/src/regions.geojson
  3. Add the region object to frontend/src/App.jsx REGIONS array
  4. Redeploy both Lambdas (same zip — all three handlers import this module)

bbox format: [lon_min, lat_min, lon_max, lat_max] in WGS84 degrees.
"""

REGIONS: dict[str, list[float]] = {
    "pleven": [23.90, 43.15, 25.20, 43.70],
    "yambol": [26.18, 41.94, 27.05, 42.72],
    "burgas": [26.58, 41.90, 28.04, 42.98],
}

# Display names — passed into the Bedrock prompt so Claude refers to the
# correct oblast in its reasoning instead of falling back to "Pleven Oblast"
# (the only place name in the rules file).
REGION_NAMES: dict[str, str] = {
    "pleven": "Pleven Oblast",
    "yambol": "Yambol Oblast",
    "burgas": "Burgas Oblast",
}

KNOWN_REGIONS = frozenset(REGIONS.keys())
