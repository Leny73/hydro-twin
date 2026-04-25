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
    # Oblast-level (legacy / cron)
    "pleven": "Pleven Oblast",
    "yambol": "Yambol Oblast",
    "burgas": "Burgas Oblast",
    # Burgas municipalities
    "BGR.2.1_1":  "Aitos Municipality, Burgas Oblast",
    "BGR.2.2_1":  "Burgas Municipality, Burgas Oblast",
    "BGR.2.3_1":  "Kameno Municipality, Burgas Oblast",
    "BGR.2.4_1":  "Karnobat Municipality, Burgas Oblast",
    "BGR.2.5_1":  "Mалko Tarnovo Municipality, Burgas Oblast",
    "BGR.2.6_1":  "Nesebar Municipality, Burgas Oblast",
    "BGR.2.7_1":  "Pomorie Municipality, Burgas Oblast",
    "BGR.2.8_1":  "Primorsko Municipality, Burgas Oblast",
    "BGR.2.9_1":  "Ruen Municipality, Burgas Oblast",
    "BGR.2.10_1": "Sozopol Municipality, Burgas Oblast",
    "BGR.2.11_1": "Sredets Municipality, Burgas Oblast",
    "BGR.2.12_1": "Sungurlare Municipality, Burgas Oblast",
    "BGR.2.13_1": "Tsarevo Municipality, Burgas Oblast",
    # Pleven municipalities
    "BGR.13.1_1":  "Belene Municipality, Pleven Oblast",
    "BGR.13.2_1":  "Cherven Bryag Municipality, Pleven Oblast",
    "BGR.13.3_1":  "Dolna Mitropoliya Municipality, Pleven Oblast",
    "BGR.13.4_1":  "Dolni Dabnik Municipality, Pleven Oblast",
    "BGR.13.5_1":  "Gulyantsi Municipality, Pleven Oblast",
    "BGR.13.6_1":  "Iskar Municipality, Pleven Oblast",
    "BGR.13.7_1":  "Knezha Municipality, Pleven Oblast",
    "BGR.13.8_1":  "Levski Municipality, Pleven Oblast",
    "BGR.13.9_1":  "Nikopol Municipality, Pleven Oblast",
    "BGR.13.10_1": "Pleven Municipality, Pleven Oblast",
    "BGR.13.11_1": "Pordim Municipality, Pleven Oblast",
    # Yambol municipalities
    "BGR.28.1_1": "Bolyarovo Municipality, Yambol Oblast",
    "BGR.28.2_1": "Elhovo Municipality, Yambol Oblast",
    "BGR.28.3_1": "Straldzha Municipality, Yambol Oblast",
    "BGR.28.4_1": "Tundzha Municipality, Yambol Oblast",
    "BGR.28.5_1": "Yambol Municipality, Yambol Oblast",
}

KNOWN_REGIONS = frozenset(REGIONS.keys())
