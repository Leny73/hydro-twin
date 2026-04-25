"""
sentinel_extractor.py — Earth Observation & Weather Data
=========================================================

⚠️  THIS FILE IS OWNED BY THE DATA ANALYSTS TEAM.
    The function signature and return-dict schema MUST remain unchanged.
    lambda_handler.py imports this directly.

Data strategy:
    All heavy EO computation runs on Sentinel Hub's cloud via the
    Statistical API — no tile downloads, no local rasterio processing.
    Weather metrics come from OpenMeteo (free, no key required).

Sources:
    ┌──────────────────────────────────────────────────────────────────┐
    │  Sentinel Hub Statistical API  (needs SH credentials)           │
    │    → Sentinel-2 L2A  NDVI  (vegetation stress / drought proxy)  │
    │    → Sentinel-2 L2A  NDWI  (open water / flood extent proxy)    │
    │  OpenMeteo API  (free, no API key)                              │
    │    → precipitation (7d + 30d cumulative)                        │
    │    → soil moisture (current + 7-day delta)                      │
    │    → max temperature (7-day)                                     │
    └──────────────────────────────────────────────────────────────────┘

Credentials required (set in backend/.env.local):
    SH_CLIENT_ID       – Sentinel Hub OAuth2 client ID
    SH_CLIENT_SECRET   – Sentinel Hub OAuth2 client secret

Install dependencies:
    pip install requests python-dotenv

How the Sentinel Hub Statistical API works:
    1. POST to /oauth/token  → get a short-lived Bearer token
    2. POST to /api/v1/statistics with:
         - bbox (CRS84 lon/lat)
         - time range
         - evalscript (JS snippet that runs on SH cloud)
         - aggregationInterval (P1D = daily, P7D = weekly)
    3. Response contains per-band statistics: mean, percentiles, etc.
       No imagery is downloaded — only aggregated numbers.

Evalscript reference:
    https://docs.sentinel-hub.com/api/latest/evalscript/v3/
Statistical API reference:
    https://docs.sentinel-hub.com/api/latest/api/statistical/
"""

import logging
import os
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env.local"),  override=True)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env.example"), override=False)

logger = logging.getLogger(__name__)

# ── Sentinel Hub credentials ──────────────────────────────────────────────────
SH_CLIENT_ID     = os.environ.get("SH_CLIENT_ID", "")
SH_CLIENT_SECRET = os.environ.get("SH_CLIENT_SECRET", "")
SH_TOKEN_URL     = "https://services.sentinel-hub.com/oauth/token"
SH_STATS_URL     = "https://services.sentinel-hub.com/api/v1/statistics"

# ─────────────────────────────────────────────────────────────────────────────
#  SENTINEL HUB HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _get_sh_token() -> str:
    """
    Fetch a short-lived OAuth2 Bearer token from Sentinel Hub.
    Tokens are valid for ~1 hour — sufficient for a single Lambda invocation.

    Returns empty string if credentials are not set (graceful fallback).
    """
    if not SH_CLIENT_ID or not SH_CLIENT_SECRET:
        logger.warning("SH_CLIENT_ID / SH_CLIENT_SECRET not set — skipping Sentinel Hub calls.")
        return ""
    try:
        resp = requests.post(
            SH_TOKEN_URL,
            data={
                "grant_type":    "client_credentials",
                "client_id":     SH_CLIENT_ID,
                "client_secret": SH_CLIENT_SECRET,
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]
    except Exception as exc:
        logger.error("Sentinel Hub token fetch failed: %s", exc)
        return ""


def _sh_statistics(token: str, bbox: list, evalscript: str,
                   dataset: str = "sentinel-2-l2a",
                   days_back: int = 14,
                   max_cloud_pct: int = 30) -> dict | None:
    """
    Call the Sentinel Hub Statistical API and return the raw response dict.

    Args:
        token         : Bearer token from _get_sh_token()
        bbox          : [lon_min, lat_min, lon_max, lat_max]  (WGS84)
        evalscript    : JavaScript evalscript string
        dataset       : SH dataset type identifier
        days_back     : how many days of imagery to aggregate over
        max_cloud_pct : reject scenes with cloud cover above this %

    Returns:
        Parsed JSON response dict, or None on any error.
    """
    if not token:
        return None

    now   = datetime.now(timezone.utc)
    start = (now - timedelta(days=days_back)).strftime("%Y-%m-%dT00:00:00Z")
    end   = now.strftime("%Y-%m-%dT23:59:59Z")

    payload = {
        "input": {
            "bounds": {
                "bbox":       bbox,
                "properties": {"crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"},
            },
            "data": [{
                "dataFilter": {
                    "timeRange":       {"from": start, "to": end},
                    "maxCloudCoverage": max_cloud_pct,
                },
                "type": dataset,
            }],
        },
        "aggregation": {
            "timeRange":           {"from": start, "to": end},
            "aggregationInterval": {"of": "P1D"},   # daily buckets
            "evalscript":          evalscript,
            "resx": 120,   # 120 m resolution — fast + cheap for statistics
            "resy": 120,
        },
        "calculations": {
            "default": {
                "statistics": {
                    "default": {
                        "percentiles": {"k": [25, 50, 75]},
                    },
                },
            },
        },
    }

    try:
        resp = requests.post(
            SH_STATS_URL,
            json=payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.error("Sentinel Hub Statistical API call failed: %s", exc)
        return None


def _extract_mean_from_stats(sh_response: dict | None, output_band: str = "B0") -> float | None:
    """
    Walk the SH Statistical API response and return the mean value of the
    most recent daily interval that has valid (non-NaN) data.

    The response structure is:
        data[].outputs.<output_band>.bands.B0.stats.mean
    """
    if not sh_response:
        return None
    try:
        intervals = sh_response.get("data", [])
        # Iterate from most recent backward; skip intervals with no valid pixels
        for interval in reversed(intervals):
            outputs = interval.get("outputs", {})
            band_data = outputs.get(output_band, {})
            stats = band_data.get("bands", {}).get("B0", {}).get("stats", {})
            mean = stats.get("mean")
            sample_count = stats.get("sampleCount", 0)
            no_data_count = stats.get("noDataCount", 0)
            if mean is not None and sample_count > 0 and sample_count > no_data_count:
                return round(float(mean), 4)
    except Exception as exc:
        logger.warning("Could not extract mean from SH response: %s", exc)
    return None


# ── Evalscripts ───────────────────────────────────────────────────────────────
# These run on Sentinel Hub's cloud. Only cloud-free pixels (SCL 4 or 5) are
# included so cloud contamination doesn't skew the index.

# NDVI — Normalised Difference Vegetation Index
# Range: -1 to 1.  Healthy vegetation ≈ 0.4–0.9.  Stressed/bare ≈ 0.1–0.3.
EVALSCRIPT_NDVI = """
//VERSION=3
function setup() {
  return {
    input:  [{ bands: ["B04", "B08", "SCL"] }],
    output: [{ id: "ndvi", bands: 1, sampleType: "FLOAT32" }],
    mosaicking: Mosaicking.ORBIT,
  };
}
function evaluatePixel(samples) {
  // Use only vegetation (4) and bare soil (5) SCL classes — exclude clouds
  let valid = samples.filter(s => s.SCL === 4 || s.SCL === 5);
  if (valid.length === 0) return { ndvi: [NaN] };
  let mean = valid.reduce((sum, s) => {
    let denom = s.B08 + s.B04;
    return sum + (denom !== 0 ? (s.B08 - s.B04) / denom : 0);
  }, 0) / valid.length;
  return { ndvi: [mean] };
}
"""

# NDWI — Normalised Difference Water Index (McFeeters 1996)
# Range: -1 to 1.  Open water > 0.  Flooded areas ≈ 0.0–0.3.
EVALSCRIPT_NDWI = """
//VERSION=3
function setup() {
  return {
    input:  [{ bands: ["B03", "B08", "SCL"] }],
    output: [{ id: "ndwi", bands: 1, sampleType: "FLOAT32" }],
    mosaicking: Mosaicking.ORBIT,
  };
}
function evaluatePixel(samples) {
  let valid = samples.filter(s => s.SCL !== 3 && s.SCL !== 8 && s.SCL !== 9 && s.SCL !== 10);
  if (valid.length === 0) return { ndwi: [NaN] };
  let mean = valid.reduce((sum, s) => {
    let denom = s.B03 + s.B08;
    return sum + (denom !== 0 ? (s.B03 - s.B08) / denom : 0);
  }, 0) / valid.length;
  return { ndwi: [mean] };
}
"""


# ─────────────────────────────────────────────────────────────────────────────
#  OPENMETEO HELPER  (free — no API key)
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_openmeteo(lat: float, lon: float) -> dict:
    """
    Fetch 30 days of historical + 1 day of forecast from OpenMeteo.
    Returns a dict with keys: precip_mm_7d, precip_mm_30d, temp_max_c,
    soil_moisture_pct, soil_moisture_7d_delta, forecast_precip_24h.

    No API key required. See https://open-meteo.com/
    """
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude":         lat,
        "longitude":        lon,
        "daily":            "precipitation_sum,temperature_2m_max",
        "hourly":           "soil_moisture_0_to_7cm",
        "past_days":        30,
        "forecast_days":    2,
        "timezone":         "UTC",
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        daily     = data.get("daily", {})
        precip    = daily.get("precipitation_sum", [])
        temp_max  = daily.get("temperature_2m_max", [])
        hourly    = data.get("hourly", {})
        soil_vals = hourly.get("soil_moisture_0_to_7cm", [])

        # Precipitation totals (skip None values)
        precip_clean = [p for p in precip if p is not None]
        precip_7d    = round(sum(precip_clean[-9:-2]), 1)   # last 7 days (exclude today + tomorrow)
        precip_30d   = round(sum(precip_clean[:-2]),   1)   # last 30 days

        # Forecast precipitation for next 24 h
        forecast_precip_24h = round(sum(p for p in precip[-2:] if p is not None), 1)

        # Max temperature over last 7 days
        temp_clean  = [t for t in temp_max[-9:-2] if t is not None]
        temp_max_7d = round(max(temp_clean), 1) if temp_clean else None

        # Soil moisture: OpenMeteo returns m³/m³ → convert to %
        soil_clean   = [s * 100 for s in soil_vals if s is not None]
        soil_current = round(soil_clean[-1],  1) if soil_clean else None
        soil_7d_ago  = round(soil_clean[-(7 * 24)], 1) if len(soil_clean) >= 7 * 24 else None
        soil_delta   = (round(soil_current - soil_7d_ago, 1)
                        if soil_current is not None and soil_7d_ago is not None else None)

        return {
            "precip_mm_7d":          precip_7d,
            "precip_mm_30d":         precip_30d,
            "temp_max_c":            temp_max_7d,
            "soil_moisture_pct":     soil_current,
            "soil_moisture_7d_delta": soil_delta,        # + = saturating, - = drying
            "forecast_precip_24h":   forecast_precip_24h,
        }

    except Exception as exc:
        logger.error("OpenMeteo request failed: %s", exc)
        return {}


# ─────────────────────────────────────────────────────────────────────────────
#  PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def get_eo_and_weather_data(bbox: list) -> dict:
    """
    Retrieve Earth Observation and weather data for the given bounding box.

    Args:
        bbox (list): [lon_min, lat_min, lon_max, lat_max]

    Returns:
        dict — all keys below are REQUIRED by lambda_handler.py.
               Do NOT rename or remove keys; add extra keys freely.
    """
    lon_min, lat_min, lon_max, lat_max = bbox
    centre_lat = (lat_min + lat_max) / 2
    centre_lon = (lon_min + lon_max) / 2

    # ── 1. Sentinel Hub EO metrics ────────────────────────────────────────
    token = _get_sh_token()

    ndvi_raw  = _sh_statistics(token, bbox, EVALSCRIPT_NDVI,  days_back=14)
    ndwi_raw  = _sh_statistics(token, bbox, EVALSCRIPT_NDWI,  days_back=14)

    ndvi = _extract_mean_from_stats(ndvi_raw, output_band="ndvi")
    ndwi = _extract_mean_from_stats(ndwi_raw, output_band="ndwi")

    # Estimate flood extent from NDWI: if mean NDWI > 0.1 across the bbox,
    # approximate open-water fraction * bbox area in km²
    bbox_area_km2 = abs(lon_max - lon_min) * abs(lat_max - lat_min) * 111.32 ** 2
    flood_extent_km2 = round(max(0.0, ndwi or 0) * bbox_area_km2 * 0.15, 1) if ndwi else 0.0

    # ── 2. OpenMeteo weather metrics ──────────────────────────────────────
    weather = _fetch_openmeteo(centre_lat, centre_lon)

    # ── 3. Assemble final dict ────────────────────────────────────────────
    has_sh_data = token != ""
    source_note = (
        "Sentinel Hub Statistical API (S2-L2A NDVI/NDWI) + OpenMeteo"
        if has_sh_data
        else "OpenMeteo only (Sentinel Hub credentials not set — NDVI/NDWI are estimated)"
    )

    
    ndvi=get_ndvi()
    print(ndvi)

    vv_vh_logratio=get_vv_vh_logratio()
    print(vv_vh_logratio)


    return {

        # ── Core EO fields (required by lambda_handler.py) ────────────────
        "ndvi":               ndvi  if ndvi  is not None else 0.35,
        "soil_moisture_pct":  weather.get("soil_moisture_pct")  or 30.0,
        "precip_mm_7d":       weather.get("precip_mm_7d")       or 0.0,
        "precip_mm_30d":      weather.get("precip_mm_30d")      or 0.0,
        "river_level_m":      None,   # TODO: add Copernicus GloFAS or in-situ gauge
        "flood_extent_km2":   flood_extent_km2,
        "temp_max_c":         weather.get("temp_max_c")         or 20.0,
        "drought_index":      None,   # TODO: compute SPI-3 from ERA5 baseline
        "data_timestamp":     datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source":             source_note,

        # ── Anomaly signals (enrich the Bedrock prompt significantly) ─────
        "ndwi":                       ndwi,
        "soil_moisture_7d_delta":     weather.get("soil_moisture_7d_delta"),
        "forecast_precip_24h_mm":     weather.get("forecast_precip_24h"),
    }
