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

# Municipality bboxes — derived from frontend/src/municipalities.geojson.
# IDs match GADM GID_2 codes so the frontend can look up snapshots by the same
# property already bound to each polygon. Cron iterates these in addition to
# the parent oblasts so every municipality polygon paints from cache + a click
# renders instantly (no live Bedrock wait).
MUNICIPALITIES: dict[str, list[float]] = {
    # Burgas municipalities
    "BGR.2.1_1":   [27.0432, 42.6145, 27.4340, 42.8020],   # Aitos
    "BGR.2.2_1":   [27.1964, 42.3619, 27.5690, 42.7250],   # Burgas
    "BGR.2.3_1":   [27.0986, 42.4027, 27.3709, 42.6465],   # Kameno
    "BGR.2.4_1":   [26.7503, 42.4221, 27.1590, 42.8196],   # Karnobat
    "BGR.2.5_1":   [27.2660, 41.8996, 27.7705, 42.2029],   # Malko Tarnovo
    "BGR.2.6_1":   [27.5751, 42.6351, 27.9024, 42.8975],   # Nesebar
    "BGR.2.7_1":   [27.4229, 42.5507, 27.6650, 42.9009],   # Pomorie
    "BGR.2.8_1":   [27.4629, 42.1435, 27.7951, 42.3423],   # Primorsko
    "BGR.2.9_1":   [27.0214, 42.7773, 27.4799, 42.9801],   # Ruen
    "BGR.2.10_1":  [27.2921, 42.1866, 27.7427, 42.4635],   # Sozopol
    "BGR.2.11_1":  [26.8583, 42.0649, 27.3682, 42.4664],   # Sredets
    "BGR.2.12_1":  [26.5761, 42.6577, 27.1031, 42.9500],   # Sungurlare
    "BGR.2.13_1":  [27.6376, 41.9357, 28.0365, 42.2174],   # Tsarevo
    # Pleven municipalities
    "BGR.13.1_1":  [24.9585, 43.5013, 25.2253, 43.7001],   # Belene
    "BGR.13.2_1":  [23.9688, 43.2163, 24.3298, 43.4408],   # Cherven Bryag
    "BGR.13.3_1":  [24.1472, 43.4504, 24.7055, 43.7451],   # Dolna Mitropoliya
    "BGR.13.4_1":  [24.2738, 43.2766, 24.5614, 43.4678],   # Dolni Dabnik
    "BGR.13.5_1":  [24.4386, 43.5434, 24.8248, 43.7652],   # Gulyantsi
    "BGR.13.6_1":  [24.1777, 43.3719, 24.3533, 43.6057],   # Iskar
    "BGR.13.7_1":  [24.0167, 43.3698, 24.2518, 43.6256],   # Knezha
    "BGR.13.8_1":  [24.9103, 43.2867, 25.2748, 43.5689],   # Levski
    "BGR.13.9_1":  [24.8079, 43.5041, 25.1126, 43.7296],   # Nikopol
    "BGR.13.10_1": [24.4125, 43.2263, 24.9472, 43.5860],   # Pleven city
    "BGR.13.11_1": [24.7662, 43.2964, 25.0346, 43.4738],   # Pordim
    # Yambol municipalities
    "BGR.28.1_1":  [26.6970, 41.9694, 27.0462, 42.2993],   # Bolyarovo
    "BGR.28.2_1":  [26.3722, 41.9370, 26.7830, 42.3176],   # Elhovo
    "BGR.28.3_1":  [26.5689, 42.2744, 26.9639, 42.7202],   # Straldzha
    "BGR.28.4_1":  [26.1790, 42.1739, 26.7561, 42.5898],   # Tundzha
    "BGR.28.5_1":  [26.4183, 42.4101, 26.5881, 42.5516],   # Yambol city
}

# Combined view used by the cron orchestrator. Oblasts come first so they
# always get refreshed, even if the run hits the Lambda timeout while still
# working through municipalities.
ALL_REGIONS: dict[str, list[float]] = {**REGIONS, **MUNICIPALITIES}

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


# Map every municipality back to its parent oblast. Used by /subscribe to roll
# clicks on a small polygon up to a single subscription per oblast — one
# email per real event instead of one per municipality.
_OBLAST_PREFIX = {
    "BGR.2.":  "burgas",
    "BGR.13.": "pleven",
    "BGR.28.": "yambol",
}


def parent_oblast(region_id: str) -> str:
    """
    Resolve any region_id to its parent oblast id.

    - Oblast ids ("burgas", "pleven", "yambol") are returned unchanged.
    - Municipality ids ("BGR.2.7_1", "BGR.13.6_1", ...) roll up to the oblast.
    - Anything unrecognised is returned unchanged so the caller can reject it.
    """
    rid = (region_id or "").strip()
    if rid in REGIONS:
        return rid
    for prefix, oblast in _OBLAST_PREFIX.items():
        if rid.startswith(prefix):
            return oblast
    return rid
