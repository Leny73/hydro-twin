

"""
sentinel_extractor.py — HydroTwin EO / Weather / Maximalist Meteorology + ML Risk Inference
==========================================================================================

Drop-in public function:
    get_eo_and_weather_data(bbox: list) -> dict

Major changes in this rewrite:
    - Adds OpenWeather One Call 3.0 runtime meteorology.
    - Keeps Open-Meteo as archive/offline fallback.
    - Adds Bulgaria/Pleven calibrated dynamic threshold engine.
    - Separates drought_stress_index from true SPI-style drought_index.
    - Adds synoptic, convective, hydrological, heat, and compound-event proxies.
    - Exports richer supervised features for XGBoost training.

Required env:
    SH_CLIENT_ID
    SH_CLIENT_SECRET

Optional env:
    OPENWEATHER_API_KEY or OWM_API_KEY
    HYDROTWIN_USE_OPENWEATHER_HISTORY=0/1  # default 0; history can be paid / expensive

Install:
    pip install requests python-dotenv pandas numpy xgboost

Run offline:
    python -m backend.sentinel_extractor
"""

from __future__ import annotations

import csv
import json
import logging
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
from dotenv import load_dotenv


load_dotenv(os.path.join(os.path.dirname(__file__), ".env.local"))
load_dotenv(os.path.join(os.path.dirname(__file__), ".env.example"), override=False)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

SH_CLIENT_ID = os.environ.get("SH_CLIENT_ID", "")
SH_CLIENT_SECRET = os.environ.get("SH_CLIENT_SECRET", "")
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY") or os.environ.get("OWM_API_KEY") or ""

SH_TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
SH_STATS_URL = "https://sh.dataspace.copernicus.eu/statistics/v1"
OPENWEATHER_ONECALL_URL = "https://api.openweathermap.org/data/3.0/onecall"
OPENWEATHER_TIMEMACHINE_URL = "https://api.openweathermap.org/data/3.0/onecall/timemachine"
OPENWEATHER_DAY_SUMMARY_URL = "https://api.openweathermap.org/data/3.0/onecall/day_summary"

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MODEL_DIR = os.path.join(PROJECT_ROOT, "data", "models")

FLOOD_MODEL_PATH = os.path.join(MODEL_DIR, "flood_saturation_precursor_xgboost.json")
FLOOD_DETECTION_MODEL_PATH = os.path.join(MODEL_DIR, "flood_detection_xgboost.json")
DROUGHT_MODEL_PATH = os.path.join(MODEL_DIR, "drought_risk_xgboost.json")
MODEL_FEATURES_PATH = os.path.join(MODEL_DIR, "model_features.json")

RISK_LABELS = {
    0: "SAFE",
    1: "LOW_RISK",
    2: "MODERATE_RISK",
    3: "HIGH_RISK",
    4: "VERY_HIGH_RISK",
}

PLEVEN_BASELINES = {
    "precip_mm_7d_avg": 11.0,
    "precip_mm_30d_avg": 45.0,
    "soil_moisture_avg_pct": 30.0,
    "ndvi_apr_avg": 0.50,
    "ndvi_jul_avg": 0.60,
}

AOIS = {
    "pleven_small": [24.5858, 43.3954, 24.6475, 43.4404],
    "pleven_levski": [24.55, 43.35, 25.15, 43.65],
    "danube_belene_svishtov": [25.05, 43.55, 25.45, 43.80],
    "danube_ruse_slivo_pole": [26.00, 43.85, 26.45, 44.05],
    "dobrich_dobrudzha": [27.55, 43.35, 28.05, 43.75],
    "silistra_dobrudzha": [27.00, 43.85, 27.55, 44.10],
    "chirpan_stara_zagora": [25.20, 42.05, 25.75, 42.35],
    "yambol_elhovo": [26.35, 42.00, 26.90, 42.35],
    "maritsa_plovdiv": [24.55, 42.05, 24.95, 42.25],
    "maritsa_harmanli_svilengrad": [25.85, 41.75, 26.35, 42.05],
}

AOI_REGION_HINTS = {
    "pleven": "danubian_plain",
    "danube": "danube_system",
    "dobrich": "dobruja",
    "silistra": "dobruja",
    "chirpan": "thracian_lowland",
    "yambol": "thracian_lowland",
    "maritsa": "thracian_lowland",
}

BASE_FEATURES = [
    # EO
    "ndvi", "ndwi", "s1_moisture", "s1_vv_db", "s1_vh_db", "flood_extent_km2",
    # core hydrometeorology
    "soil_moisture_pct", "soil_moisture_7d_delta",
    "precip_mm_24h", "precip_mm_48h", "precip_mm_72h",
    "precip_mm_7d", "precip_mm_30d", "forecast_precip_24h_mm", "forecast_precip_48h_mm",
    "forecast_precip_72h_mm", "precip_intensity_max_1h_mm",
    "temp_max_c", "temp_min_c", "temp_mean_c", "dew_point_max_c", "dewpoint_depression_min_c",
    "relative_humidity_mean_pct", "relative_humidity_max_pct",
    "pressure_mean_hpa", "pressure_min_hpa", "pressure_drop_24h_hpa", "pressure_drop_48h_hpa",
    "wind_speed_max_ms", "wind_gust_max_ms", "wind_dir_mean_deg",
    "cloud_cover_mean_pct", "cloud_cover_max_pct", "uvi_max",
    "snow_mm_24h", "snow_mm_48h", "snowmelt_proxy",
    # drought and season
    "drought_index",          # reserved for true SPI-like negative index if integrated later
    "drought_stress_index",   # 0..1 local stress proxy
    "week_of_year", "month", "day_of_year",
    "is_spring", "is_summer", "is_autumn", "is_winter",
    # ratios/anomalies
    "precip_7d_ratio_to_pleven_avg", "precip_30d_ratio_to_pleven_avg",
    "soil_moisture_ratio_to_pleven_avg", "ndvi_seasonal_anomaly_proxy",
    # synoptic/convective proxies
    "heavy_rain_hours_24h", "heavy_rain_hours_48h",
    "thunderstorm_hours_48h", "convective_proxy",
    "ivt_proxy", "mediterranean_cyclone_proxy", "cutoff_low_proxy",
    "cyclogenesis_proxy", "blocking_heat_proxy", "synoptic_flood_score",
    # compound flags
    "flash_flood_trigger", "soil_saturation_surge",
    "drought_to_flood_transition", "compound_drought_heat",
    "compound_flood_after_dry_spell",
    # threshold counts become model features too
    "flood_watch_threshold_count", "flood_warning_threshold_count",
    "drought_watch_threshold_count", "drought_warning_threshold_count",
    "alert_confidence",
]

RUNTIME_FEATURES = BASE_FEATURES
TRAINING_FEATURES = [f"feature_t_minus_1_{c}" for c in RUNTIME_FEATURES]

FLOOD_SATURATION_PRECURSOR_FEATURES = [
    f"feature_t_minus_1_{c}" for c in [
        "soil_moisture_pct", "soil_moisture_7d_delta",
        "precip_mm_7d", "precip_mm_30d", "forecast_precip_24h_mm", "forecast_precip_48h_mm",
        "s1_moisture", "ndwi", "flood_extent_km2",
        "pressure_drop_24h_hpa", "pressure_drop_48h_hpa",
        "wind_gust_max_ms", "relative_humidity_mean_pct",
        "precip_7d_ratio_to_pleven_avg", "precip_30d_ratio_to_pleven_avg",
        "heavy_rain_hours_48h", "convective_proxy", "ivt_proxy",
        "mediterranean_cyclone_proxy", "cyclogenesis_proxy", "synoptic_flood_score",
        "flash_flood_trigger", "soil_saturation_surge", "drought_to_flood_transition",
        "is_spring", "is_summer", "is_autumn", "week_of_year",
    ]
]

FLOOD_DETECTION_FEATURES = [
    f"feature_t_minus_0_{c}" for c in [
        "soil_moisture_pct", "soil_moisture_7d_delta",
        "precip_mm_24h", "precip_mm_48h", "precip_mm_7d", "precip_mm_30d",
        "forecast_precip_24h_mm", "forecast_precip_48h_mm", "forecast_precip_72h_mm",
        "precip_intensity_max_1h_mm", "s1_moisture", "ndwi", "flood_extent_km2",
        "pressure_min_hpa", "pressure_drop_24h_hpa", "wind_gust_max_ms",
        "heavy_rain_hours_24h", "heavy_rain_hours_48h", "thunderstorm_hours_48h",
        "convective_proxy", "ivt_proxy", "mediterranean_cyclone_proxy", "cutoff_low_proxy",
        "cyclogenesis_proxy", "synoptic_flood_score",
        "flash_flood_trigger", "soil_saturation_surge", "drought_to_flood_transition",
        "flood_watch_threshold_count", "flood_warning_threshold_count",
        "is_spring", "is_summer", "is_autumn", "month", "week_of_year",
    ]
]

DROUGHT_FEATURES = [
    f"feature_t_minus_1_{c}" for c in [
        "ndvi", "soil_moisture_pct", "soil_moisture_7d_delta",
        "precip_mm_30d", "precip_30d_ratio_to_pleven_avg",
        "temp_max_c", "temp_mean_c", "dewpoint_depression_min_c",
        "relative_humidity_mean_pct", "cloud_cover_mean_pct", "uvi_max",
        "wind_speed_max_ms", "drought_stress_index", "ndvi_seasonal_anomaly_proxy",
        "blocking_heat_proxy", "compound_drought_heat",
        "drought_watch_threshold_count", "drought_warning_threshold_count",
        "is_summer", "is_autumn", "month", "week_of_year",
    ]
]


EVALSCRIPT_NDVI = """
//VERSION=3
function setup() {
  return {
    input:  [{ bands: ["B04", "B08", "SCL", "dataMask"] }],
    output: [{ id: "ndvi", bands: 1, sampleType: "FLOAT32" }, { id: "dataMask", bands: 1, sampleType: "UINT8" }],
    mosaicking: Mosaicking.ORBIT,
  };
}
function evaluatePixel(samples) {
  let valid = samples.filter(s => s.dataMask === 1 && (s.SCL === 4 || s.SCL === 5));
  if (valid.length === 0) return { ndvi: [NaN], dataMask: [0] };
  let mean = valid.reduce((sum, s) => {
    let denom = s.B08 + s.B04;
    return sum + (denom !== 0 ? (s.B08 - s.B04) / denom : 0);
  }, 0) / valid.length;
  return { ndvi: [mean], dataMask: [1] };
}
"""

EVALSCRIPT_NDWI = """
//VERSION=3
function setup() {
  return {
    input:  [{ bands: ["B03", "B08", "SCL", "dataMask"] }],
    output: [{ id: "ndwi", bands: 1, sampleType: "FLOAT32" }, { id: "dataMask", bands: 1, sampleType: "UINT8" }],
    mosaicking: Mosaicking.ORBIT,
  };
}
function evaluatePixel(samples) {
  let valid = samples.filter(s => s.dataMask === 1 && s.SCL !== 3 && s.SCL !== 8 && s.SCL !== 9 && s.SCL !== 10);
  if (valid.length === 0) return { ndwi: [NaN], dataMask: [0] };
  let mean = valid.reduce((sum, s) => {
    let denom = s.B03 + s.B08;
    return sum + (denom !== 0 ? (s.B03 - s.B08) / denom : 0);
  }, 0) / valid.length;
  return { ndwi: [mean], dataMask: [1] };
}
"""

EVALSCRIPT_S1_MOISTURE = """
//VERSION=3
function setup() {
  return {
    input: [{ bands: ["VV", "VH", "dataMask"] }],
    output: [
      { id: "s1_moisture", bands: 1, sampleType: "FLOAT32" },
      { id: "vv_db",       bands: 1, sampleType: "FLOAT32" },
      { id: "vh_db",       bands: 1, sampleType: "FLOAT32" },
      { id: "dataMask",    bands: 1, sampleType: "UINT8" },
    ],
  };
}
function toDb(x) { return 10 * Math.log(x) / Math.LN10; }
function clamp(x, minVal, maxVal) { return Math.max(minVal, Math.min(maxVal, x)); }
function evaluatePixel(sample) {
  if (sample.dataMask === 0 || sample.VV <= 0 || sample.VH <= 0) {
    return { s1_moisture: [NaN], vv_db: [NaN], vh_db: [NaN], dataMask: [0] };
  }
  let vvDb = toDb(sample.VV);
  let vhDb = toDb(sample.VH);
  let moisture = clamp((vvDb - (-25.0)) / 25.0, 0.0, 1.0);
  return { s1_moisture: [moisture], vv_db: [vvDb], vh_db: [vhDb], dataMask: [1] };
}
"""


def _safe_float(x: Any, default: float | None = None) -> float | None:
    try:
        if x is None:
            return default
        val = float(x)
        if math.isnan(val) or math.isinf(val):
            return default
        return val
    except Exception:
        return default


def _round(x: Any, ndigits: int = 3, default: float | None = None) -> float | None:
    val = _safe_float(x, default)
    return round(val, ndigits) if val is not None else default


def _sum(values: list[Any]) -> float:
    return float(sum(_safe_float(v, 0.0) or 0.0 for v in values))


def _mean(values: list[Any], default: float | None = None) -> float | None:
    vals = [_safe_float(v) for v in values]
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else default


def _max(values: list[Any], default: float | None = None) -> float | None:
    vals = [_safe_float(v) for v in values]
    vals = [v for v in vals if v is not None]
    return max(vals) if vals else default


def _min(values: list[Any], default: float | None = None) -> float | None:
    vals = [_safe_float(v) for v in values]
    vals = [v for v in vals if v is not None]
    return min(vals) if vals else default


class Sentinel_Extractor:
    def __init__(
        self,
        sh_client_id: str | None = None,
        sh_client_secret: str | None = None,
        openweather_api_key: str | None = None,
        resolution_degrees: float = 0.01,
        interval_days: int = 30,
        timeout: int = 180,
        flood_model_path: str = FLOOD_MODEL_PATH,
        flood_detection_model_path: str = FLOOD_DETECTION_MODEL_PATH,
        drought_model_path: str = DROUGHT_MODEL_PATH,
    ):
        self.sh_client_id = sh_client_id or SH_CLIENT_ID
        self.sh_client_secret = sh_client_secret or SH_CLIENT_SECRET
        self.openweather_api_key = openweather_api_key or OPENWEATHER_API_KEY
        self.resolution_degrees = resolution_degrees
        self.interval_days = interval_days
        self.timeout = timeout
        self.flood_model_path = flood_model_path
        self.flood_detection_model_path = flood_detection_model_path
        self.drought_model_path = drought_model_path
        self._flood_model = None
        self._flood_detection_model = None
        self._drought_model = None

    # ------------------------------------------------------------------
    # Sentinel Hub
    # ------------------------------------------------------------------

    def get_sh_token(self) -> str:
        if not self.sh_client_id or not self.sh_client_secret:
            logger.warning("SH_CLIENT_ID / SH_CLIENT_SECRET not set.")
            return ""
        try:
            resp = requests.post(
                SH_TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.sh_client_id,
                    "client_secret": self.sh_client_secret,
                },
                timeout=20,
            )
            resp.raise_for_status()
            return resp.json()["access_token"]
        except Exception as exc:
            logger.error("Sentinel Hub token fetch failed: %s", exc)
            return ""

    @staticmethod
    def _data_filter(dataset: str, max_cloud_pct: int = 30) -> dict:
        if dataset == "sentinel-1-grd":
            return {
                "mosaickingOrder": "mostRecent",
                "acquisitionMode": "IW",
                "polarization": "DV",
                "resolution": "HIGH",
                "orbitDirection": "ASCENDING",
            }
        return {"mosaickingOrder": "leastCC", "maxCloudCoverage": max_cloud_pct}

    def sh_statistics(
        self,
        token: str,
        bbox: list[float],
        evalscript: str,
        dataset: str,
        start_date: datetime,
        end_date: datetime,
        aggregation_interval: str,
        max_cloud_pct: int = 30,
    ) -> dict | None:
        if not token:
            return None

        payload = {
            "input": {
                "bounds": {
                    "bbox": bbox,
                    "properties": {"crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"},
                },
                "data": [{"type": dataset, "dataFilter": self._data_filter(dataset, max_cloud_pct)}],
            },
            "aggregation": {
                "timeRange": {
                    "from": start_date.strftime("%Y-%m-%dT00:00:00Z"),
                    "to": end_date.strftime("%Y-%m-%dT23:59:59Z"),
                },
                "aggregationInterval": {"of": aggregation_interval},
                "evalscript": evalscript,
                "resx": self.resolution_degrees,
                "resy": self.resolution_degrees,
            },
            "calculations": {"default": {"statistics": {"default": {"percentiles": {"k": [25, 50, 75]}}}}},
        }

        try:
            resp = requests.post(
                SH_STATS_URL,
                json=payload,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                logger.error("Sentinel Hub %s HTTP %s: %s", dataset, resp.status_code, resp.text[:800])
                return None
            return resp.json()
        except Exception as exc:
            logger.error("Sentinel Hub request failed: %s", exc)
            return None

    @staticmethod
    def _merge_sh_responses(responses: list[dict | None]) -> dict | None:
        valid = [r for r in responses if r and isinstance(r, dict)]
        if not valid:
            return None
        merged = dict(valid[0])
        merged["data"] = []
        for response in valid:
            merged["data"].extend(response.get("data", []))
        merged["data"] = sorted(merged["data"], key=lambda x: x.get("interval", {}).get("from", ""))
        return merged

    @staticmethod
    def _year_chunks(start_date: datetime, end_date: datetime) -> list[tuple[datetime, datetime]]:
        chunks = []
        current = start_date
        while current < end_date:
            chunk_end = min(datetime(current.year + 1, 1, 1, tzinfo=timezone.utc), end_date)
            chunks.append((current, chunk_end))
            current = chunk_end
        return chunks

    @staticmethod
    def extract_interval_dates(sh_response: dict | None) -> list[tuple[str, str]]:
        if not sh_response:
            return []
        out = []
        for item in sh_response.get("data", []):
            start = item.get("interval", {}).get("from", "")[:10]
            end = item.get("interval", {}).get("to", "")[:10]
            if start and end:
                out.append((start, end))
        return out

    @staticmethod
    def extract_interval_mean(sh_response: dict | None, output_band: str) -> dict[str, float | None]:
        result: dict[str, float | None] = {}
        if not sh_response:
            return result
        for interval in sh_response.get("data", []):
            date_key = interval.get("interval", {}).get("from", "")[:10]
            stats = (
                interval.get("outputs", {})
                .get(output_band, {})
                .get("bands", {})
                .get("B0", {})
                .get("stats", {})
            )
            mean = stats.get("mean")
            sample_count = stats.get("sampleCount", 0)
            no_data_count = stats.get("noDataCount", 0)
            result[date_key] = round(float(mean), 4) if mean is not None and sample_count > no_data_count else None
        return result

    @staticmethod
    def extract_mean_from_stats(sh_response: dict | None, output_band: str) -> float | None:
        values = Sentinel_Extractor.extract_interval_mean(sh_response, output_band)
        for _, val in reversed(list(values.items())):
            if val is not None:
                return val
        return None

    # ------------------------------------------------------------------
    # OpenWeather / Open-Meteo meteorology
    # ------------------------------------------------------------------

    def fetch_openweather_onecall(self, lat: float, lon: float) -> dict:
        if not self.openweather_api_key:
            return {}
        try:
            resp = requests.get(
                OPENWEATHER_ONECALL_URL,
                params={
                    "lat": lat,
                    "lon": lon,
                    "appid": self.openweather_api_key,
                    "units": "metric",
                },
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("OpenWeather One Call failed; fallback may be used: %s", exc)
            return {}

    def fetch_openweather_timemachine(self, lat: float, lon: float, dt: datetime) -> dict:
        if not self.openweather_api_key:
            return {}
        try:
            resp = requests.get(
                OPENWEATHER_TIMEMACHINE_URL,
                params={
                    "lat": lat,
                    "lon": lon,
                    "dt": int(dt.timestamp()),
                    "appid": self.openweather_api_key,
                    "units": "metric",
                },
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("OpenWeather timemachine failed: %s", exc)
            return {}

    def fetch_openmeteo_archive_or_forecast(self, lat: float, lon: float, date: str | None = None) -> dict:
        try:
            if date:
                end_dt = datetime.strptime(date, "%Y-%m-%d").date()
                start_dt = end_dt - timedelta(days=30)
                url = "https://archive-api.open-meteo.com/v1/archive"
                params = {
                    "latitude": lat,
                    "longitude": lon,
                    "start_date": start_dt.strftime("%Y-%m-%d"),
                    "end_date": end_dt.strftime("%Y-%m-%d"),
                    "daily": "precipitation_sum,temperature_2m_max,temperature_2m_min,wind_speed_10m_max,wind_gusts_10m_max",
                    "hourly": "soil_moisture_0_to_7cm,relative_humidity_2m,dew_point_2m,surface_pressure,cloud_cover,precipitation",
                    "timezone": "UTC",
                }
            else:
                url = "https://api.open-meteo.com/v1/forecast"
                params = {
                    "latitude": lat,
                    "longitude": lon,
                    "daily": "precipitation_sum,temperature_2m_max,temperature_2m_min,wind_speed_10m_max,wind_gusts_10m_max",
                    "hourly": "soil_moisture_0_to_7cm,relative_humidity_2m,dew_point_2m,surface_pressure,cloud_cover,precipitation",
                    "past_days": 30,
                    "forecast_days": 3,
                    "timezone": "UTC",
                }

            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            daily = data.get("daily", {})
            hourly = data.get("hourly", {})

            precip_daily = [v for v in (daily.get("precipitation_sum", []) or []) if v is not None]
            tmax = [v for v in (daily.get("temperature_2m_max", []) or []) if v is not None]
            tmin = [v for v in (daily.get("temperature_2m_min", []) or []) if v is not None]
            soil = [v * 100 for v in (hourly.get("soil_moisture_0_to_7cm", []) or []) if v is not None]
            hourly_precip = [v for v in (hourly.get("precipitation", []) or []) if v is not None]
            humidity = [v for v in (hourly.get("relative_humidity_2m", []) or []) if v is not None]
            dew = [v for v in (hourly.get("dew_point_2m", []) or []) if v is not None]
            pressure = [v for v in (hourly.get("surface_pressure", []) or []) if v is not None]
            clouds = [v for v in (hourly.get("cloud_cover", []) or []) if v is not None]
            wind = [v for v in (daily.get("wind_speed_10m_max", []) or []) if v is not None]
            gust = [v for v in (daily.get("wind_gusts_10m_max", []) or []) if v is not None]

            soil_current = round(soil[-1], 1) if soil else None
            soil_7d_ago = round(soil[-7 * 24], 1) if len(soil) >= 7 * 24 else None

            return {
                "precip_mm_24h": round(_sum(precip_daily[-1:]), 1) if precip_daily else 0.0,
                "precip_mm_48h": round(_sum(precip_daily[-2:]), 1) if precip_daily else 0.0,
                "precip_mm_72h": round(_sum(precip_daily[-3:]), 1) if precip_daily else 0.0,
                "precip_mm_7d": round(_sum(precip_daily[-7:]), 1) if precip_daily else 0.0,
                "precip_mm_30d": round(_sum(precip_daily[-30:]), 1) if precip_daily else 0.0,
                "forecast_precip_24h_mm": round(_sum(precip_daily[-1:]), 1) if not date and precip_daily else 0.0,
                "forecast_precip_48h_mm": round(_sum(precip_daily[-2:]), 1) if not date and precip_daily else 0.0,
                "forecast_precip_72h_mm": round(_sum(precip_daily[-3:]), 1) if not date and precip_daily else 0.0,
                "precip_intensity_max_1h_mm": _round(_max(hourly_precip[-72:], 0.0), 1, 0.0),
                "temp_max_c": _round(_max(tmax[-7:], None), 1, None),
                "temp_min_c": _round(_min(tmin[-7:], None), 1, None),
                "temp_mean_c": _round(_mean(tmax[-7:] + tmin[-7:], None), 1, None),
                "soil_moisture_pct": soil_current,
                "soil_moisture_7d_delta": round(soil_current - soil_7d_ago, 1) if soil_current is not None and soil_7d_ago is not None else None,
                "relative_humidity_mean_pct": _round(_mean(humidity[-48:], None), 1, None),
                "relative_humidity_max_pct": _round(_max(humidity[-48:], None), 1, None),
                "dew_point_max_c": _round(_max(dew[-48:], None), 1, None),
                "dewpoint_depression_min_c": None,
                "pressure_mean_hpa": _round(_mean(pressure[-48:], None), 1, None),
                "pressure_min_hpa": _round(_min(pressure[-48:], None), 1, None),
                "pressure_drop_24h_hpa": _round((pressure[-24] - pressure[-1]) if len(pressure) >= 24 else 0.0, 1, 0.0),
                "pressure_drop_48h_hpa": _round((pressure[-48] - pressure[-1]) if len(pressure) >= 48 else 0.0, 1, 0.0),
                "wind_speed_max_ms": _round((_max(wind[-3:], 0.0) or 0.0) / 3.6, 2, 0.0),
                "wind_gust_max_ms": _round((_max(gust[-3:], 0.0) or 0.0) / 3.6, 2, 0.0),
                "cloud_cover_mean_pct": _round(_mean(clouds[-48:], None), 1, None),
                "cloud_cover_max_pct": _round(_max(clouds[-48:], None), 1, None),
                "snow_mm_24h": 0.0,
                "snow_mm_48h": 0.0,
            }
        except Exception as exc:
            logger.error("OpenMeteo failed: %s", exc)
            return {}

    @staticmethod
    def _rain_from_openweather_hour(hour: dict) -> float:
        rain = hour.get("rain", {}) or {}
        return float(rain.get("1h", 0.0) or 0.0)

    @staticmethod
    def _snow_from_openweather_hour(hour: dict) -> float:
        snow = hour.get("snow", {}) or {}
        return float(snow.get("1h", 0.0) or 0.0)

    def openweather_runtime_features(self, lat: float, lon: float) -> dict:
        data = self.fetch_openweather_onecall(lat, lon)
        if not data:
            return {}

        current = data.get("current", {}) or {}
        hourly = data.get("hourly", []) or []
        daily = data.get("daily", []) or []

        h24 = hourly[:24]
        h48 = hourly[:48]
        h72 = hourly[:72]
        d8 = daily[:8]

        rain_24 = [self._rain_from_openweather_hour(h) for h in h24]
        rain_48 = [self._rain_from_openweather_hour(h) for h in h48]
        rain_72 = [self._rain_from_openweather_hour(h) for h in h72]
        snow_24 = [self._snow_from_openweather_hour(h) for h in h24]
        snow_48 = [self._snow_from_openweather_hour(h) for h in h48]

        temps = [_safe_float(h.get("temp")) for h in h48]
        temps = [v for v in temps if v is not None]
        dew = [_safe_float(h.get("dew_point")) for h in h48]
        dew = [v for v in dew if v is not None]
        humidity = [_safe_float(h.get("humidity")) for h in h48]
        humidity = [v for v in humidity if v is not None]
        pressure = [_safe_float(h.get("pressure")) for h in h48]
        pressure = [v for v in pressure if v is not None]
        wind = [_safe_float(h.get("wind_speed")) for h in h48]
        wind = [v for v in wind if v is not None]
        gust = [_safe_float(h.get("wind_gust")) for h in h48]
        gust = [v for v in gust if v is not None]
        clouds = [_safe_float(h.get("clouds")) for h in h48]
        clouds = [v for v in clouds if v is not None]
        uvi = [_safe_float(d.get("uvi")) for d in d8]
        uvi = [v for v in uvi if v is not None]

        weather_ids = []
        for h in h48:
            for w in h.get("weather", []) or []:
                wid = w.get("id")
                if wid is not None:
                    weather_ids.append(int(wid))

        thunderstorm_hours_48h = 0
        for h in h48:
            ids = [int(w.get("id")) for w in h.get("weather", []) or [] if w.get("id") is not None]
            if any(200 <= i < 300 for i in ids):
                thunderstorm_hours_48h += 1

        pressure_drop_24h = 0.0
        pressure_drop_48h = 0.0
        if len(pressure) >= 24:
            pressure_drop_24h = max(0.0, pressure[0] - pressure[23])
        if len(pressure) >= 48:
            pressure_drop_48h = max(0.0, pressure[0] - pressure[47])

        dewpoint_depression = None
        if temps and dew and len(temps) == len(dew):
            dewpoint_depression = min([t - d for t, d in zip(temps, dew)])

        wind_speed_max = _max(wind, 0.0) or 0.0
        wind_gust_max = _max(gust, wind_speed_max) or wind_speed_max
        hum_mean = _mean(humidity, None)
        cloud_mean = _mean(clouds, None)
        pressure_min = _min(pressure, None)

        precip_24 = _sum(rain_24)
        precip_48 = _sum(rain_48)
        precip_72 = _sum(rain_72)
        intensity_max = _max(rain_48, 0.0) or 0.0

        heavy_rain_hours_24 = sum(1 for x in rain_24 if x >= 5.0)
        heavy_rain_hours_48 = sum(1 for x in rain_48 if x >= 5.0)

        convective_proxy = min(
            1.0,
            0.35 * min(1.0, thunderstorm_hours_48h / 3.0)
            + 0.25 * min(1.0, intensity_max / 20.0)
            + 0.20 * min(1.0, (hum_mean or 0.0) / 90.0)
            + 0.20 * min(1.0, (dewpoint_depression if dewpoint_depression is not None else 12.0) / 2.0 if dewpoint_depression is not None and dewpoint_depression < 2 else 0.0),
        )

        # Very rough moisture transport proxy: strong low-level wind * relative humidity * precip signal.
        ivt_proxy = min(1.0, (wind_speed_max / 18.0) * ((hum_mean or 0.0) / 100.0) * (1.0 + min(1.0, precip_48 / 60.0)))

        mediterranean_cyclone_proxy = min(
            1.0,
            0.35 * (1.0 if pressure_min is not None and pressure_min < 1005 else 0.0)
            + 0.25 * min(1.0, pressure_drop_24h / 6.0)
            + 0.20 * min(1.0, precip_72 / 60.0)
            + 0.20 * min(1.0, wind_gust_max / 18.0),
        )

        cutoff_low_proxy = min(
            1.0,
            0.45 * min(1.0, thunderstorm_hours_48h / 4.0)
            + 0.30 * min(1.0, cloud_mean / 90.0 if cloud_mean is not None else 0.0)
            + 0.25 * min(1.0, precip_48 / 50.0),
        )

        cyclogenesis_proxy = min(
            1.0,
            0.60 * min(1.0, pressure_drop_24h / 5.0)
            + 0.25 * min(1.0, wind_gust_max / 20.0)
            + 0.15 * min(1.0, precip_24 / 35.0),
        )

        blocking_heat_proxy = min(
            1.0,
            0.45 * (1.0 if (_max(temps, -99) or -99) > 33 else 0.0)
            + 0.25 * (1.0 if (pressure_min or 0) > 1015 else 0.0)
            + 0.20 * (1.0 if (cloud_mean or 100) < 35 else 0.0)
            + 0.10 * min(1.0, (_max(uvi, 0.0) or 0.0) / 8.0),
        )

        synoptic_flood_score = min(
            1.0,
            0.28 * mediterranean_cyclone_proxy
            + 0.22 * cutoff_low_proxy
            + 0.22 * ivt_proxy
            + 0.18 * cyclogenesis_proxy
            + 0.10 * convective_proxy,
        )

        return {
            "precip_mm_24h": round(precip_24, 1),
            "precip_mm_48h": round(precip_48, 1),
            "precip_mm_72h": round(precip_72, 1),
            "forecast_precip_24h_mm": round(precip_24, 1),
            "forecast_precip_48h_mm": round(precip_48, 1),
            "forecast_precip_72h_mm": round(precip_72, 1),
            "precip_intensity_max_1h_mm": round(intensity_max, 1),
            "temp_max_c": _round(_max(temps, current.get("temp")), 1, None),
            "temp_min_c": _round(_min(temps, current.get("temp")), 1, None),
            "temp_mean_c": _round(_mean(temps, current.get("temp")), 1, None),
            "dew_point_max_c": _round(_max(dew, current.get("dew_point")), 1, None),
            "dewpoint_depression_min_c": _round(dewpoint_depression, 1, None),
            "relative_humidity_mean_pct": _round(hum_mean, 1, None),
            "relative_humidity_max_pct": _round(_max(humidity, current.get("humidity")), 1, None),
            "pressure_mean_hpa": _round(_mean(pressure, current.get("pressure")), 1, None),
            "pressure_min_hpa": _round(pressure_min, 1, None),
            "pressure_drop_24h_hpa": round(pressure_drop_24h, 1),
            "pressure_drop_48h_hpa": round(pressure_drop_48h, 1),
            "wind_speed_max_ms": round(wind_speed_max, 2),
            "wind_gust_max_ms": round(wind_gust_max, 2),
            "wind_dir_mean_deg": _round(_mean([h.get("wind_deg") for h in h48], None), 1, None),
            "cloud_cover_mean_pct": _round(cloud_mean, 1, None),
            "cloud_cover_max_pct": _round(_max(clouds, current.get("clouds")), 1, None),
            "uvi_max": _round(_max(uvi, current.get("uvi")), 2, None),
            "snow_mm_24h": round(_sum(snow_24), 1),
            "snow_mm_48h": round(_sum(snow_48), 1),
            "heavy_rain_hours_24h": heavy_rain_hours_24,
            "heavy_rain_hours_48h": heavy_rain_hours_48,
            "thunderstorm_hours_48h": thunderstorm_hours_48h,
            "convective_proxy": round(convective_proxy, 3),
            "ivt_proxy": round(ivt_proxy, 3),
            "mediterranean_cyclone_proxy": round(mediterranean_cyclone_proxy, 3),
            "cutoff_low_proxy": round(cutoff_low_proxy, 3),
            "cyclogenesis_proxy": round(cyclogenesis_proxy, 3),
            "blocking_heat_proxy": round(blocking_heat_proxy, 3),
            "synoptic_flood_score": round(synoptic_flood_score, 3),
        }

    def fetch_weather_features(self, lat: float, lon: float, date: str | None = None) -> dict:
        # Offline history: keep Open-Meteo as default because OpenWeather history can be paid/call-heavy.
        if date:
            use_ow_history = os.environ.get("HYDROTWIN_USE_OPENWEATHER_HISTORY", "0") == "1"
            base = self.fetch_openmeteo_archive_or_forecast(lat, lon, date=date)
            if use_ow_history and self.openweather_api_key:
                dt = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                ow = self.fetch_openweather_timemachine(lat, lon, dt)
                base.update(self._features_from_openweather_timemachine(ow))
            return self._fill_missing_meteo_defaults(base, historical=True)

        # Runtime: OpenWeather first, Open-Meteo fallback/supplement for soil moisture and 30-day precipitation.
        fallback = self.fetch_openmeteo_archive_or_forecast(lat, lon, date=None)
        ow = self.openweather_runtime_features(lat, lon)
        merged = dict(fallback)
        merged.update({k: v for k, v in ow.items() if v is not None})
        # OpenWeather One Call does not provide soil moisture or 30-day observed precip.
        if "soil_moisture_pct" not in merged or merged.get("soil_moisture_pct") is None:
            merged["soil_moisture_pct"] = fallback.get("soil_moisture_pct")
        if "soil_moisture_7d_delta" not in merged or merged.get("soil_moisture_7d_delta") is None:
            merged["soil_moisture_7d_delta"] = fallback.get("soil_moisture_7d_delta")
        if "precip_mm_7d" not in merged or merged.get("precip_mm_7d") is None:
            merged["precip_mm_7d"] = fallback.get("precip_mm_7d", merged.get("precip_mm_72h", 0.0))
        if "precip_mm_30d" not in merged or merged.get("precip_mm_30d") is None:
            merged["precip_mm_30d"] = fallback.get("precip_mm_30d", merged.get("precip_mm_7d", 0.0))
        return self._fill_missing_meteo_defaults(merged, historical=False)

    @staticmethod
    def _features_from_openweather_timemachine(data: dict) -> dict:
        if not data:
            return {}
        hourly = data.get("hourly", []) or []
        current = data.get("current", {}) or {}
        rows = hourly or [current]
        rain = [Sentinel_Extractor._rain_from_openweather_hour(h) for h in rows]
        snow = [Sentinel_Extractor._snow_from_openweather_hour(h) for h in rows]
        pressure = [_safe_float(h.get("pressure")) for h in rows]
        pressure = [p for p in pressure if p is not None]
        wind = [_safe_float(h.get("wind_speed")) for h in rows]
        wind = [w for w in wind if w is not None]
        gust = [_safe_float(h.get("wind_gust")) for h in rows]
        gust = [g for g in gust if g is not None]
        humidity = [_safe_float(h.get("humidity")) for h in rows]
        humidity = [h for h in humidity if h is not None]
        clouds = [_safe_float(h.get("clouds")) for h in rows]
        clouds = [c for c in clouds if c is not None]
        return {
            "precip_mm_24h": round(_sum(rain), 1),
            "snow_mm_24h": round(_sum(snow), 1),
            "pressure_mean_hpa": _round(_mean(pressure, None), 1, None),
            "pressure_min_hpa": _round(_min(pressure, None), 1, None),
            "wind_speed_max_ms": _round(_max(wind, 0.0), 2, 0.0),
            "wind_gust_max_ms": _round(_max(gust, _max(wind, 0.0)), 2, 0.0),
            "relative_humidity_mean_pct": _round(_mean(humidity, None), 1, None),
            "cloud_cover_mean_pct": _round(_mean(clouds, None), 1, None),
        }

    @staticmethod
    def _fill_missing_meteo_defaults(features: dict, historical: bool) -> dict:
        defaults = {
            "precip_mm_24h": 0.0, "precip_mm_48h": 0.0, "precip_mm_72h": 0.0,
            "precip_mm_7d": 0.0, "precip_mm_30d": 0.0,
            "forecast_precip_24h_mm": 0.0, "forecast_precip_48h_mm": 0.0, "forecast_precip_72h_mm": 0.0,
            "precip_intensity_max_1h_mm": 0.0,
            "temp_max_c": 20.0, "temp_min_c": 10.0, "temp_mean_c": 15.0,
            "dew_point_max_c": None, "dewpoint_depression_min_c": None,
            "relative_humidity_mean_pct": None, "relative_humidity_max_pct": None,
            "pressure_mean_hpa": None, "pressure_min_hpa": None,
            "pressure_drop_24h_hpa": 0.0, "pressure_drop_48h_hpa": 0.0,
            "wind_speed_max_ms": 0.0, "wind_gust_max_ms": 0.0, "wind_dir_mean_deg": None,
            "cloud_cover_mean_pct": None, "cloud_cover_max_pct": None, "uvi_max": None,
            "snow_mm_24h": 0.0, "snow_mm_48h": 0.0,
            "heavy_rain_hours_24h": 0, "heavy_rain_hours_48h": 0, "thunderstorm_hours_48h": 0,
            "convective_proxy": 0.0, "ivt_proxy": 0.0,
            "mediterranean_cyclone_proxy": 0.0, "cutoff_low_proxy": 0.0,
            "cyclogenesis_proxy": 0.0, "blocking_heat_proxy": 0.0,
            "synoptic_flood_score": 0.0,
            "soil_moisture_pct": 30.0, "soil_moisture_7d_delta": 0.0,
        }
        out = dict(defaults)
        out.update({k: v for k, v in features.items() if v is not None})
        if historical:
            # Historical rows do not know the future forecast. Use last 24h observation as a conservative proxy.
            out["forecast_precip_24h_mm"] = out.get("forecast_precip_24h_mm") or out.get("precip_mm_24h", 0.0)
            out["forecast_precip_48h_mm"] = out.get("forecast_precip_48h_mm") or out.get("precip_mm_48h", 0.0)
            out["forecast_precip_72h_mm"] = out.get("forecast_precip_72h_mm") or out.get("precip_mm_72h", 0.0)
        return out

    # ------------------------------------------------------------------
    # Derived values, seasonality, regionalization
    # ------------------------------------------------------------------

    @staticmethod
    def compute_flood_extent_km2(bbox: list[float], ndwi: float | None) -> float:
        lon_min, lat_min, lon_max, lat_max = bbox
        area_km2 = abs(lon_max - lon_min) * abs(lat_max - lat_min) * 111.32 ** 2
        return round(max(0.0, ndwi or 0.0) * area_km2 * 0.15, 1)

    @staticmethod
    def compute_drought_stress_index(precip_mm_30d: float | None, soil_moisture_pct: float | None, ndvi: float | None, temp_max_c: float | None = None, humidity_mean: float | None = None) -> float | None:
        if precip_mm_30d is None and soil_moisture_pct is None and ndvi is None and temp_max_c is None:
            return None
        precip = precip_mm_30d if precip_mm_30d is not None else PLEVEN_BASELINES["precip_mm_30d_avg"]
        soil = soil_moisture_pct if soil_moisture_pct is not None else PLEVEN_BASELINES["soil_moisture_avg_pct"]
        veg = ndvi if ndvi is not None else 0.45
        temp = temp_max_c if temp_max_c is not None else 28.0
        rh = humidity_mean if humidity_mean is not None else 55.0

        precip_stress = max(0.0, min(1.0, (PLEVEN_BASELINES["precip_mm_30d_avg"] - precip) / PLEVEN_BASELINES["precip_mm_30d_avg"]))
        soil_stress = max(0.0, min(1.0, (35.0 - soil) / 35.0))
        ndvi_stress = max(0.0, min(1.0, (0.45 - veg) / 0.45))
        heat_stress = max(0.0, min(1.0, (temp - 30.0) / 10.0))
        humidity_stress = max(0.0, min(1.0, (45.0 - rh) / 45.0))
        return round(0.36 * precip_stress + 0.28 * soil_stress + 0.18 * ndvi_stress + 0.12 * heat_stress + 0.06 * humidity_stress, 3)

    @staticmethod
    def week_of_year(date_like: str | datetime | None = None) -> int:
        if date_like is None:
            dt = datetime.now(timezone.utc)
        elif isinstance(date_like, datetime):
            dt = date_like
        else:
            dt = datetime.strptime(str(date_like)[:10], "%Y-%m-%d")
        return dt.isocalendar().week

    @staticmethod
    def _date_from_row(row: dict) -> datetime:
        raw = row.get("end_date") or row.get("data_timestamp") or datetime.now(timezone.utc)
        if isinstance(raw, datetime):
            return raw
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))

    @staticmethod
    def infer_region(aoi_name: str | None, bbox: list[float] | None = None) -> str:
        name = (aoi_name or "").lower()
        for key, region in AOI_REGION_HINTS.items():
            if key in name:
                return region
        if bbox:
            lon_min, lat_min, lon_max, lat_max = bbox
            lat = (lat_min + lat_max) / 2
            lon = (lon_min + lon_max) / 2
            if lat >= 43.5:
                return "danubian_plain"
            if lon >= 27.0 and lat >= 43.2:
                return "dobruja"
            if lat <= 42.5:
                return "thracian_lowland"
        return "danubian_plain"

    @staticmethod
    def add_engineered_features(row: dict, bbox: list[float] | None = None, aoi_name: str | None = None) -> dict:
        dt = Sentinel_Extractor._date_from_row(row)
        month = dt.month
        is_spring = month in [3, 4, 5]
        is_summer = month in [6, 7, 8]
        is_autumn = month in [9, 10, 11]
        is_winter = month in [12, 1, 2]

        p7 = _safe_float(row.get("precip_mm_7d"), 0.0) or 0.0
        p30 = _safe_float(row.get("precip_mm_30d"), 0.0) or 0.0
        fc24 = _safe_float(row.get("forecast_precip_24h_mm"), row.get("precip_mm_24h")) or 0.0
        fc48 = _safe_float(row.get("forecast_precip_48h_mm"), row.get("precip_mm_48h")) or 0.0
        soil = _safe_float(row.get("soil_moisture_pct"), 30.0) or 30.0
        soil_delta = _safe_float(row.get("soil_moisture_7d_delta"), 0.0) or 0.0
        temp = _safe_float(row.get("temp_max_c"), 20.0) or 20.0
        ndvi = _safe_float(row.get("ndvi"), None)
        spi = _safe_float(row.get("drought_index"), None)
        drought_stress = _safe_float(row.get("drought_stress_index"), None)

        if drought_stress is None:
            drought_stress = Sentinel_Extractor.compute_drought_stress_index(
                p30, soil, ndvi, temp, _safe_float(row.get("relative_humidity_mean_pct"), None)
            )

        region = Sentinel_Extractor.infer_region(aoi_name, bbox)

        if month in [4, 5]:
            ndvi_expected = 0.50
        elif month in [6, 7, 8]:
            ndvi_expected = 0.60
        elif month in [9]:
            ndvi_expected = 0.50
        else:
            ndvi_expected = 0.35

        snow = (_safe_float(row.get("snow_mm_48h"), 0.0) or 0.0)
        temp_mean = _safe_float(row.get("temp_mean_c"), 0.0) or 0.0
        snowmelt_proxy = min(1.0, (snow / 20.0) * max(0.0, min(1.0, temp_mean / 8.0)))

        summer_flash = is_summer and fc24 > 60
        general_flash = fc24 > 70 and soil > 80

        drought_to_flood = (
            (spi is not None and spi < -1.5 and fc24 > 60)
            or (spi is None and drought_stress is not None and drought_stress > 0.70 and fc24 > 60)
        )

        compound_heat = (
            ((spi is not None and spi < -1.2) or (spi is None and drought_stress is not None and drought_stress > 0.60))
            and temp > 37
        )

        dry_to_wet = p30 < 13.5 and fc24 > 35

        return {
            "region_code": region,
            "month": month,
            "day_of_year": dt.timetuple().tm_yday,
            "week_of_year": dt.isocalendar().week,
            "is_spring": int(is_spring),
            "is_summer": int(is_summer),
            "is_autumn": int(is_autumn),
            "is_winter": int(is_winter),
            "drought_stress_index": drought_stress,
            "precip_7d_ratio_to_pleven_avg": round(p7 / PLEVEN_BASELINES["precip_mm_7d_avg"], 3),
            "precip_30d_ratio_to_pleven_avg": round(p30 / PLEVEN_BASELINES["precip_mm_30d_avg"], 3),
            "soil_moisture_ratio_to_pleven_avg": round(soil / PLEVEN_BASELINES["soil_moisture_avg_pct"], 3),
            "ndvi_seasonal_anomaly_proxy": round((ndvi - ndvi_expected), 3) if ndvi is not None else None,
            "snowmelt_proxy": round(snowmelt_proxy, 3),
            "flash_flood_trigger": int(general_flash or summer_flash),
            "soil_saturation_surge": int(soil_delta > 20 and p7 > 35),
            "drought_to_flood_transition": int(drought_to_flood),
            "compound_drought_heat": int(compound_heat),
            "compound_flood_after_dry_spell": int(dry_to_wet),
        }

    # ------------------------------------------------------------------
    # Threshold labels
    # ------------------------------------------------------------------

    @staticmethod
    def risk_level_from_score(score: float) -> int:
        if score <= 0:
            return 0
        if score < 2:
            return 1
        if score < 4:
            return 2
        if score < 6:
            return 3
        return 4

    @staticmethod
    def risk_name(level: int | None) -> str | None:
        if level is None:
            return None
        return RISK_LABELS.get(int(level), "UNKNOWN")

    def threshold_risk_from_row(self, row: dict, bbox: list[float] | None = None, aoi_name: str | None = None) -> dict:
        dt = self._date_from_row(row)
        month = dt.month
        region = self.infer_region(aoi_name or row.get("aoi_name"), bbox)

        if month in [3, 4, 5]:
            season = "spring"
            precip_factor = 1.0
            river_factor = 0.8
            drought_enabled = False
            flash_threshold = 70.0
        elif month in [6, 7, 8]:
            season = "summer"
            precip_factor = 1.0
            river_factor = 1.0
            drought_enabled = True
            flash_threshold = 60.0
        elif month in [9, 10, 11]:
            season = "autumn"
            precip_factor = 0.8
            river_factor = 1.0
            drought_enabled = True
            flash_threshold = 70.0
        else:
            season = "winter"
            precip_factor = 1.0
            river_factor = 1.0
            drought_enabled = False
            flash_threshold = 70.0

        if region == "black_sea_coast":
            precip_factor *= 0.8
        elif region == "dobruja":
            drought_enabled = True
        elif region == "mountain":
            precip_factor *= 0.85

        def v(key: str) -> float | None:
            return _safe_float(row.get(key), None)

        p7 = v("precip_mm_7d")
        p30 = v("precip_mm_30d")
        fc24 = v("forecast_precip_24h_mm")
        fc48 = v("forecast_precip_48h_mm")
        fc72 = v("forecast_precip_72h_mm")
        intensity = v("precip_intensity_max_1h_mm")
        soil = v("soil_moisture_pct")
        soil_delta = v("soil_moisture_7d_delta")
        ndvi = v("ndvi")
        ndwi = v("ndwi")
        temp = v("temp_max_c")
        drought_spi = v("drought_index")
        drought_stress = v("drought_stress_index")
        flood_extent = v("flood_extent_km2")
        river_level = v("river_level_m")
        synoptic = v("synoptic_flood_score") or 0.0
        cyclone = v("mediterranean_cyclone_proxy") or 0.0
        cutoff = v("cutoff_low_proxy") or 0.0
        convective = v("convective_proxy") or 0.0
        blocking = v("blocking_heat_proxy") or 0.0
        snowmelt = v("snowmelt_proxy") or 0.0

        fw = fwarn = dw = dwarn = 0
        flood_score = drought_score = 0.0
        reasons: list[str] = []

        # Highest-priority compound / synoptic rules.
        if fc24 is not None and soil is not None and fc24 > flash_threshold and soil > 80:
            fwarn += 1; flood_score = max(flood_score, 6.0)
            reasons.append("flash_flood_trigger")

        if drought_spi is not None and fc24 is not None and drought_spi < -1.5 and fc24 > 60:
            fwarn += 1; flood_score = max(flood_score, 6.0)
            reasons.append("drought_to_flood_transition_spi")
        elif drought_spi is None and drought_stress is not None and fc24 is not None and drought_stress > 0.70 and fc24 > 60:
            fwarn += 1; flood_score = max(flood_score, 6.0)
            reasons.append("drought_to_flood_transition_stress_proxy")

        if synoptic >= 0.85:
            fwarn += 1; flood_score = max(flood_score, 6.0)
            reasons.append("synoptic_extreme_override")
        elif synoptic >= 0.70:
            fw += 1; flood_score += 2.0
            reasons.append("synoptic_early_escalation")

        if cyclone >= 0.70 and fc72 is not None and fc72 > 60:
            fw += 1; flood_score += 1.5
            reasons.append("mediterranean_cyclone_proxy")

        if cutoff >= 0.70 and convective >= 0.60:
            fw += 1; flood_score += 1.5
            reasons.append("cutoff_low_convective_proxy")

        if snowmelt >= 0.50 and p7 is not None and p7 > 25 and month in [3, 4, 5]:
            fw += 1; flood_score += 1.5
            reasons.append("snowmelt_plus_rain_proxy")

        # Flood thresholds.
        if p7 is not None and p7 > 40 * precip_factor:
            fw += 1; flood_score += 1
        if p7 is not None and p7 > 80 * precip_factor:
            fwarn += 1; flood_score += 2
        if fc24 is not None and fc24 > 50 * precip_factor:
            fw += 1; flood_score += 1
        if fc24 is not None and fc24 > 80 * precip_factor:
            fwarn += 1; flood_score += 2
        if fc48 is not None and fc48 > 70 * precip_factor:
            fw += 1; flood_score += 1
        if fc72 is not None and fc72 > 90 * precip_factor:
            fw += 1; flood_score += 1
        if intensity is not None and intensity > 15:
            fw += 1; flood_score += 1
        if intensity is not None and intensity > 25:
            fwarn += 1; flood_score += 2
        if soil is not None and soil > 75:
            fw += 1; flood_score += 1
        if soil is not None and soil > 85:
            fwarn += 1; flood_score += 2
        if river_level is not None and river_level > 0.4 * river_factor:
            fw += 1; flood_score += 1
        if river_level is not None and river_level > 0.8 * river_factor:
            fwarn += 1; flood_score += 2
        if ndwi is not None and ndwi > 0.1:
            fw += 1; flood_score += 1
        if ndwi is not None and ndwi > 0.25:
            fwarn += 1; flood_score += 2
        if flood_extent is not None and flood_extent > 5:
            fw += 1; flood_score += 1
        if flood_extent is not None and flood_extent > 20:
            fwarn += 1; flood_score += 2
        if soil_delta is not None and p7 is not None and soil_delta > 20 and p7 > 35:
            fw += 1; flood_score += 1.5
        if fw >= 2:
            fwarn += 1; flood_score += 1

        # Drought thresholds.
        if drought_enabled:
            if drought_spi is not None:
                spi_watch = -0.8 if region == "dobruja" else -1.0
                if drought_spi < spi_watch:
                    dw += 1; drought_score += 1
                if drought_spi < -1.5:
                    dwarn += 1; drought_score += 2
            elif drought_stress is not None:
                watch = 0.38 if region == "dobruja" else 0.45
                if drought_stress > watch:
                    dw += 1; drought_score += 1
                if drought_stress > 0.70:
                    dwarn += 1; drought_score += 2

            if ndvi is not None and month in [4, 5, 6, 7, 8, 9] and ndvi < 0.25:
                dw += 1; drought_score += 1
            if ndvi is not None and month in [4, 5, 6, 7, 8, 9] and ndvi < 0.15:
                dwarn += 1; drought_score += 2
            if soil is not None and soil < 20:
                dw += 1; drought_score += 1
            if soil is not None and soil < 10:
                dwarn += 1; drought_score += 2
            if p30 is not None and p30 < 0.30 * PLEVEN_BASELINES["precip_mm_30d_avg"]:
                dw += 1; drought_score += 1
            if p30 is not None and p30 < 0.10 * PLEVEN_BASELINES["precip_mm_30d_avg"]:
                dwarn += 1; drought_score += 2
            if temp is not None and temp > 33:
                dw += 1; drought_score += 1
            if temp is not None and temp > 38:
                dwarn += 1; drought_score += 2
            if blocking >= 0.70:
                dw += 1; drought_score += 1.5
            if drought_stress is not None and temp is not None and drought_stress > 0.60 and temp > 37:
                dwarn += 1; drought_score = max(drought_score, 6.0)
                reasons.append("compound_drought_heat_proxy")

        flood_level = self.risk_level_from_score(flood_score)
        drought_level = self.risk_level_from_score(drought_score)

        confidence = 1.0
        if river_level is None:
            confidence -= 0.10
        if drought_spi is None:
            confidence -= 0.05
        if ndwi is None:
            confidence -= 0.10
        if row.get("s1_moisture") is None:
            confidence -= 0.05
        if (p7 or 0) > 40 and soil is not None and soil < 20:
            confidence -= 0.15
            reasons.append("conflicting_high_precip_low_soil")
        if (ndwi is None or (isinstance(ndwi, float) and math.isnan(ndwi))) and flood_extent:
            confidence -= 0.10

        return {
            "season": season,
            "region_code": region,
            "threshold_flood_score": round(flood_score, 3),
            "threshold_drought_score": round(drought_score, 3),
            "flood_risk_level": flood_level,
            "drought_risk_level": drought_level,
            "flood_risk_label": self.risk_name(flood_level),
            "drought_risk_label": self.risk_name(drought_level),
            "flood_watch_threshold_count": fw,
            "flood_warning_threshold_count": fwarn,
            "drought_watch_threshold_count": dw,
            "drought_warning_threshold_count": dwarn,
            "alert_confidence": round(max(0.25, confidence), 2),
            "threshold_reason_codes": reasons,
        }

    # ------------------------------------------------------------------
    # Runtime ML inference
    # ------------------------------------------------------------------

    def _load_xgb_model(self, path: str):
        try:
            from xgboost import XGBClassifier
        except ImportError:
            logger.warning("xgboost not installed; skipping ML inference.")
            return None
        if not os.path.exists(path):
            logger.warning("Model not found: %s", path)
            return None
        model = XGBClassifier()
        model.load_model(path)
        return model

    def load_models(self) -> tuple[Any | None, Any | None, Any | None]:
        if self._flood_model is None:
            self._flood_model = self._load_xgb_model(self.flood_model_path)
        if self._flood_detection_model is None:
            self._flood_detection_model = self._load_xgb_model(self.flood_detection_model_path)
        if self._drought_model is None:
            self._drought_model = self._load_xgb_model(self.drought_model_path)
        return self._flood_model, self._flood_detection_model, self._drought_model

    @staticmethod
    def _runtime_features_from_snapshot(snapshot: dict, lag_prefix: str = "feature_t_minus_1") -> dict:
        return {f"{lag_prefix}_{key}": snapshot.get(key) for key in RUNTIME_FEATURES}

    def predict_ml_risk(self, snapshot: dict) -> dict:
        try:
            import numpy as np
            import pandas as pd
        except ImportError:
            return {"ml_available": False, "reason": "pandas/numpy not installed"}

        flood_precursor_model, flood_detection_model, drought_model = self.load_models()
        if flood_precursor_model is None and flood_detection_model is None and drought_model is None:
            return {"ml_available": False, "reason": "trained models not found or xgboost unavailable"}

        out: dict[str, Any] = {"ml_available": True}

        def predict_with(model, feature_cols, lag_prefix):
            feature_row = self._runtime_features_from_snapshot(snapshot, lag_prefix=lag_prefix)
            X = pd.DataFrame([feature_row])
            for col in feature_cols:
                if col not in X.columns:
                    X[col] = np.nan
            X = X[feature_cols]
            pred = int(model.predict(X)[0])
            proba = model.predict_proba(X)[0]
            return pred, round(float(max(proba)), 3)

        if flood_precursor_model is not None:
            pred, conf = predict_with(flood_precursor_model, FLOOD_SATURATION_PRECURSOR_FEATURES, "feature_t_minus_1")
            out["flood_precursor_risk_level_ml"] = pred
            out["flood_precursor_risk_label_ml"] = self.risk_name(pred)
            out["flood_precursor_risk_confidence_ml"] = conf

        if flood_detection_model is not None:
            pred, conf = predict_with(flood_detection_model, FLOOD_DETECTION_FEATURES, "feature_t_minus_0")
            out["flood_detection_risk_level_ml"] = pred
            out["flood_detection_risk_label_ml"] = self.risk_name(pred)
            out["flood_detection_risk_confidence_ml"] = conf

        if drought_model is not None:
            pred, conf = predict_with(drought_model, DROUGHT_FEATURES, "feature_t_minus_1")
            out["drought_risk_level_ml"] = pred
            out["drought_risk_label_ml"] = self.risk_name(pred)
            out["drought_risk_confidence_ml"] = conf

        return out

    @staticmethod
    def choose_status(flood_label: str, drought_label: str) -> str:
        order = {"SAFE": 0, "LOW_RISK": 1, "MODERATE_RISK": 2, "HIGH_RISK": 3, "VERY_HIGH_RISK": 4}
        flood_level = order.get(flood_label, 0)
        drought_level = order.get(drought_label, 0)
        if flood_level >= drought_level:
            if flood_level >= 3:
                return "FLOOD_WARNING"
            if flood_level == 2:
                return "FLOOD_WATCH"
            return "SAFE"
        if drought_level >= 3:
            return "DROUGHT_WARNING"
        if drought_level == 2:
            return "DROUGHT_WATCH"
        return "SAFE"

    # ------------------------------------------------------------------
    # Current API
    # ------------------------------------------------------------------

    def get_eo_and_weather_data(self, bbox: list[float]) -> dict:
        lon_min, lat_min, lon_max, lat_max = bbox
        centre_lat = (lat_min + lat_max) / 2
        centre_lon = (lon_min + lon_max) / 2

        token = self.get_sh_token()
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=14)
        interval = "P14D"

        ndvi_raw = self.sh_statistics(token, bbox, EVALSCRIPT_NDVI, "sentinel-2-l2a", start, now, interval)
        ndwi_raw = self.sh_statistics(token, bbox, EVALSCRIPT_NDWI, "sentinel-2-l2a", start, now, interval)
        s1_raw = self.sh_statistics(token, bbox, EVALSCRIPT_S1_MOISTURE, "sentinel-1-grd", start, now, interval)

        ndvi = self.extract_mean_from_stats(ndvi_raw, "ndvi")
        ndwi = self.extract_mean_from_stats(ndwi_raw, "ndwi")
        s1_moisture = self.extract_mean_from_stats(s1_raw, "s1_moisture")
        s1_vv_db = self.extract_mean_from_stats(s1_raw, "vv_db")
        s1_vh_db = self.extract_mean_from_stats(s1_raw, "vh_db")

        weather = self.fetch_weather_features(centre_lat, centre_lon)
        drought_stress = self.compute_drought_stress_index(
            weather.get("precip_mm_30d"), weather.get("soil_moisture_pct"), ndvi,
            weather.get("temp_max_c"), weather.get("relative_humidity_mean_pct")
        )

        snapshot = {
            **weather,
            "ndvi": ndvi if ndvi is not None else 0.35,
            "ndwi": ndwi,
            "s1_moisture": s1_moisture,
            "s1_vv_db": s1_vv_db,
            "s1_vh_db": s1_vh_db,
            "river_level_m": None,
            "flood_extent_km2": self.compute_flood_extent_km2(bbox, ndwi),
            "drought_index": None,  # reserved for future true SPI-3
            "drought_stress_index": drought_stress,
            "data_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source": "Sentinel Hub Statistical API + OpenWeather One Call 3.0 + Open-Meteo fallback + local ML risk model",
        }

        snapshot.update(self.add_engineered_features(snapshot, bbox=bbox))
        threshold = self.threshold_risk_from_row(snapshot, bbox=bbox)
        snapshot.update(threshold)

        ml = self.predict_ml_risk(snapshot)
        snapshot["ml"] = ml

        flood_label = (
            ml.get("flood_detection_risk_label_ml")
            or ml.get("flood_precursor_risk_label_ml")
            or snapshot.get("flood_risk_label")
            or "SAFE"
        )
        drought_label = ml.get("drought_risk_label_ml") or snapshot.get("drought_risk_label") or "SAFE"

        snapshot["status_from_model"] = self.choose_status(flood_label, drought_label)
        snapshot["risk_summary"] = {
            "flood": {
                "threshold_label": snapshot.get("flood_risk_label"),
                "threshold_score": snapshot.get("threshold_flood_score"),
                "ml_detection_label": ml.get("flood_detection_risk_label_ml"),
                "ml_detection_confidence": ml.get("flood_detection_risk_confidence_ml"),
                "ml_precursor_label": ml.get("flood_precursor_risk_label_ml"),
                "ml_precursor_confidence": ml.get("flood_precursor_risk_confidence_ml"),
            },
            "drought": {
                "threshold_label": snapshot.get("drought_risk_label"),
                "threshold_score": snapshot.get("threshold_drought_score"),
                "ml_label": ml.get("drought_risk_label_ml"),
                "ml_confidence": ml.get("drought_risk_confidence_ml"),
            },
        }

        return {"timestamp": snapshot.get("data_timestamp"), "bbox": bbox, "data": snapshot}

    # ------------------------------------------------------------------
    # Offline time-series pipeline
    # ------------------------------------------------------------------

    @staticmethod
    def get_time_range(years_back: float) -> tuple[datetime, datetime]:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=int(365 * years_back))
        return start, end

    def fetch_eo_time_series_raw(self, bbox: list[float], years_back: float) -> tuple[dict | None, dict | None, dict | None]:
        token = self.get_sh_token()
        if not token:
            return None, None, None
        start, end = self.get_time_range(years_back)
        chunks = self._year_chunks(start, end)
        interval = f"P{self.interval_days}D"

        ndvi_parts, ndwi_parts, s1_parts = [], [], []
        for idx, (chunk_start, chunk_end) in enumerate(chunks, 1):
            print(f"  Sentinel chunk {idx}/{len(chunks)}: {chunk_start.date()} → {chunk_end.date()}")
            ndvi_parts.append(self.sh_statistics(token, bbox, EVALSCRIPT_NDVI, "sentinel-2-l2a", chunk_start, chunk_end, interval))
            ndwi_parts.append(self.sh_statistics(token, bbox, EVALSCRIPT_NDWI, "sentinel-2-l2a", chunk_start, chunk_end, interval))
            s1_parts.append(self.sh_statistics(token, bbox, EVALSCRIPT_S1_MOISTURE, "sentinel-1-grd", chunk_start, chunk_end, interval))

        return self._merge_sh_responses(ndvi_parts), self._merge_sh_responses(ndwi_parts), self._merge_sh_responses(s1_parts)

    def build_time_series_rows(self, aoi_name: str, bbox: list[float], ndvi_raw: dict | None, ndwi_raw: dict | None, s1_raw: dict | None) -> list[dict]:
        lon_min, lat_min, lon_max, lat_max = bbox
        centre_lat = (lat_min + lat_max) / 2
        centre_lon = (lon_min + lon_max) / 2

        intervals = self.extract_interval_dates(ndvi_raw)
        ndvi_by = self.extract_interval_mean(ndvi_raw, "ndvi")
        ndwi_by = self.extract_interval_mean(ndwi_raw, "ndwi")
        s1_by = self.extract_interval_mean(s1_raw, "s1_moisture")
        vv_by = self.extract_interval_mean(s1_raw, "vv_db")
        vh_by = self.extract_interval_mean(s1_raw, "vh_db")

        rows = []
        for start_date, end_date in intervals:
            ndvi = ndvi_by.get(start_date)
            ndwi = ndwi_by.get(start_date)
            weather = self.fetch_weather_features(centre_lat, centre_lon, end_date)
            drought_stress = self.compute_drought_stress_index(
                weather.get("precip_mm_30d"),
                weather.get("soil_moisture_pct"),
                ndvi,
                weather.get("temp_max_c"),
                weather.get("relative_humidity_mean_pct"),
            )
            row = {
                **weather,
                "aoi_name": aoi_name,
                "start_date": start_date,
                "end_date": end_date,
                "ndvi": ndvi,
                "ndwi": ndwi,
                "s1_moisture": s1_by.get(start_date),
                "s1_vv_db": vv_by.get(start_date),
                "s1_vh_db": vh_by.get(start_date),
                "river_level_m": None,
                "flood_extent_km2": self.compute_flood_extent_km2(bbox, ndwi),
                "drought_index": None,
                "drought_stress_index": drought_stress,
                "data_timestamp": f"{end_date}T23:59:59Z",
                "source": "Sentinel Hub Statistical API + OpenWeather/Open-Meteo meteorology",
            }
            row.update(self.add_engineered_features(row, bbox=bbox, aoi_name=aoi_name))
            row.update(self.threshold_risk_from_row(row, bbox=bbox, aoi_name=aoi_name))
            rows.append(row)
        return rows

    def get_time_series_for_aoi(self, aoi_name: str, bbox: list[float], years_back: float) -> list[dict]:
        ndvi_raw, ndwi_raw, s1_raw = self.fetch_eo_time_series_raw(bbox, years_back)
        return self.build_time_series_rows(aoi_name, bbox, ndvi_raw, ndwi_raw, s1_raw)

    def get_time_series_for_aois(self, aois: dict[str, list[float]], years_back: float) -> list[dict]:
        all_rows = []
        for aoi_name, bbox in aois.items():
            print(f"\nAOI: {aoi_name} {bbox}")
            try:
                rows = self.get_time_series_for_aoi(aoi_name, bbox, years_back)
                print(f"  rows: {len(rows)}")
                all_rows.extend(rows)
            except Exception as exc:
                logger.error("AOI %s failed: %s", aoi_name, exc)
        return all_rows

    # ------------------------------------------------------------------
    # Supervised dataset
    # ------------------------------------------------------------------

    @staticmethod
    def _rows_to_dataframe(rows: list[dict] | None = None, csv_path: str | None = None):
        try:
            import pandas as pd
        except ImportError as exc:
            raise ImportError("Requires pandas.") from exc
        if csv_path:
            df = pd.read_csv(csv_path)
        elif rows is not None:
            df = pd.DataFrame(rows)
        else:
            raise ValueError("Provide rows or csv_path.")
        if "end_date" in df.columns:
            df["end_date"] = pd.to_datetime(df["end_date"])
            sort_cols = [c for c in ["aoi_name", "end_date"] if c in df.columns]
            df = df.sort_values(sort_cols).reset_index(drop=True)
        return df

    def build_supervised_disaster_dataset(
        self,
        rows: list[dict] | None = None,
        csv_path: str | None = None,
        feature_lag_steps: int = 1,
        include_lag0_detection_features: bool = True,
    ):
        import pandas as pd

        df = self._rows_to_dataframe(rows, csv_path)
        group_cols = ["aoi_name"] if "aoi_name" in df.columns else []
        df = df.sort_values(group_cols + ["end_date"]).reset_index(drop=True)

        target_cols = [
            "flood_risk_level", "flood_risk_label",
            "drought_risk_level", "drought_risk_label",
            "threshold_flood_score", "threshold_drought_score",
            "alert_confidence",
            "season", "region_code",
            "threshold_reason_codes",
        ]

        base_features = [c for c in RUNTIME_FEATURES if c in df.columns]

        supervised = pd.DataFrame()
        if "aoi_name" in df.columns:
            supervised["aoi_name"] = df["aoi_name"]
        supervised["target_date"] = df["end_date"]

        for col in target_cols:
            if col in df.columns:
                supervised[col] = df[col]

        if group_cols:
            supervised["feature_date"] = df.groupby("aoi_name")["end_date"].shift(feature_lag_steps)
            for col in base_features:
                supervised[f"feature_t_minus_{feature_lag_steps}_{col}"] = df.groupby("aoi_name")[col].shift(feature_lag_steps)
                if include_lag0_detection_features:
                    supervised[f"feature_t_minus_0_{col}"] = df[col]
        else:
            supervised["feature_date"] = df["end_date"].shift(feature_lag_steps)
            for col in base_features:
                supervised[f"feature_t_minus_{feature_lag_steps}_{col}"] = df[col].shift(feature_lag_steps)
                if include_lag0_detection_features:
                    supervised[f"feature_t_minus_0_{col}"] = df[col]

        return supervised.dropna(subset=["feature_date"]).reset_index(drop=True)

    @staticmethod
    def save_csv(rows_or_df: Any, output_path: str) -> None:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        if hasattr(rows_or_df, "to_csv"):
            rows_or_df.to_csv(output_path, index=False)
            return
        if not rows_or_df:
            raise ValueError("No rows to save.")
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows_or_df[0].keys()))
            writer.writeheader()
            writer.writerows(rows_or_df)

    @staticmethod
    def save_model_feature_list(output_path: str = MODEL_FEATURES_PATH) -> None:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "runtime_features": RUNTIME_FEATURES,
                    "generic_lag1_features": TRAINING_FEATURES,
                    "flood_saturation_precursor_features": FLOOD_SATURATION_PRECURSOR_FEATURES,
                    "flood_detection_features": FLOOD_DETECTION_FEATURES,
                    "drought_features": DROUGHT_FEATURES,
                    "risk_labels": RISK_LABELS,
                    "pleven_baselines": PLEVEN_BASELINES,
                },
                f,
                indent=2,
            )


def get_eo_and_weather_data(bbox: list) -> dict:
    return Sentinel_Extractor().get_eo_and_weather_data(bbox)


_get_sh_token = lambda: Sentinel_Extractor().get_sh_token()
_extract_mean_from_stats = Sentinel_Extractor.extract_mean_from_stats
_fetch_openmeteo = lambda lat, lon, date=None: Sentinel_Extractor().fetch_openmeteo_archive_or_forecast(lat, lon, date)


if __name__ == "__main__":
    processed_path = os.path.join(PROJECT_ROOT, "data", "processed", "eo_weather_timeseries.csv")
    ml_path = os.path.join(PROJECT_ROOT, "data", "ml", "supervised_disaster_dataset.csv")

    YEARS_BACK_MAIN = 3
    INTERVAL_DAYS_MAIN = 30
    RESOLUTION_DEGREES_MAIN = 0.01

    extractor = Sentinel_Extractor(
        interval_days=INTERVAL_DAYS_MAIN,
        resolution_degrees=RESOLUTION_DEGREES_MAIN,
        timeout=180,
    )

    print("STEP 1 — Build multi-AOI EO/weather/meteo-proxy time series")
    rows = extractor.get_time_series_for_aois(AOIS, years_back=YEARS_BACK_MAIN)
    if not rows:
        print("No rows returned.")
        sys.exit(1)
    extractor.save_csv(rows, processed_path)
    print(f"Saved processed data: {processed_path}")
    print(f"Rows: {len(rows)}")

    print("STEP 2 — Build ordinal-risk supervised ML dataset")
    supervised = extractor.build_supervised_disaster_dataset(csv_path=processed_path, feature_lag_steps=1)
    extractor.save_csv(supervised, ml_path)
    extractor.save_model_feature_list(MODEL_FEATURES_PATH)
    print(f"Saved ML data: {ml_path}")
    print(f"Rows: {len(supervised)}")
    print(f"Saved feature list: {MODEL_FEATURES_PATH}")
