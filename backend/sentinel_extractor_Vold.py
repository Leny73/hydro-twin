"""
sentinel_extractor.py — HydroTwin EO/Weather + ML Risk Inference
=================================================================

Main class:
    Sentinel_Extractor

Public Lambda-compatible function:
    get_eo_and_weather_data(bbox: list) -> dict

What this file does:
    1. Runtime/API mode:
        - Fetch today's EO/weather values for a bbox/AOI.
        - Compute deterministic threshold risk labels.
        - Load trained ML classifiers if available.
        - Return flood/drought ML risk predictions.

    2. Offline pipeline mode:
        - Build multi-AOI historical EO/weather time series.
        - Generate threshold-based ordinal labels:
              SAFE / LOW_RISK / MODERATE_RISK / HIGH_RISK / VERY_HIGH_RISK
        - Export supervised dataset for ML training.

Install:
    pip install requests python-dotenv pandas numpy xgboost

Run offline pipeline:
    python -m backend.sentinel_extractor

Runtime Lambda call path:
    lambda_handler.py imports get_eo_and_weather_data(bbox)
"""

from __future__ import annotations

import csv
import json
import logging
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
SH_TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
SH_STATS_URL = "https://sh.dataspace.copernicus.eu/statistics/v1"

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

RISK_TO_STATUS = {
    "SAFE": "SAFE",
    "LOW_RISK": "SAFE",
    "MODERATE_RISK": "WATCH",
    "HIGH_RISK": "WARNING",
    "VERY_HIGH_RISK": "WARNING",
}

# CRS84/WGS84 bbox format: [lon_min, lat_min, lon_max, lat_max]
PLEVEN_SMALL_BBOX = [24.5858, 43.3954, 24.6475, 43.4404]

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

RUNTIME_FEATURES = [
    "ndvi",
    "ndwi",
    "s1_moisture",
    "soil_moisture_pct",
    "soil_moisture_7d_delta",
    "precip_mm_7d",
    "precip_mm_30d",
    "forecast_precip_24h_mm",
    "temp_max_c",
    "drought_index",
    "flood_extent_km2",
    "week_of_year",
]

# Generic model feature list: current runtime values mapped to training-style names.
TRAINING_FEATURES = [f"feature_t_minus_1_{c}" for c in RUNTIME_FEATURES]

# Dedicated flood precursor task:
# prior saturation / wetness state -> flood risk at target date.
FLOOD_SATURATION_PRECURSOR_FEATURES = [
    "feature_t_minus_1_soil_moisture_pct",
    "feature_t_minus_1_soil_moisture_7d_delta",
    "feature_t_minus_1_precip_mm_7d",
    "feature_t_minus_1_precip_mm_30d",
    "feature_t_minus_1_s1_moisture",
    "feature_t_minus_1_ndwi",
    "feature_t_minus_1_flood_extent_km2",
    "feature_t_minus_1_week_of_year",
]

# Dedicated flood detection task:
# current observations -> current flood risk.
FLOOD_DETECTION_FEATURES = [
    f"feature_t_minus_0_{c}"
    for c in [
        "soil_moisture_pct",
        "soil_moisture_7d_delta",
        "precip_mm_7d",
        "precip_mm_30d",
        "forecast_precip_24h_mm",
        "s1_moisture",
        "ndwi",
        "flood_extent_km2",
        "week_of_year",
    ]
]


EVALSCRIPT_NDVI = """
//VERSION=3
function setup() {
  return {
    input:  [{ bands: ["B04", "B08", "SCL", "dataMask"] }],
    output: [
      { id: "ndvi",     bands: 1, sampleType: "FLOAT32" },
      { id: "dataMask", bands: 1, sampleType: "UINT8" },
    ],
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
    output: [
      { id: "ndwi",     bands: 1, sampleType: "FLOAT32" },
      { id: "dataMask", bands: 1, sampleType: "UINT8" },
    ],
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


class Sentinel_Extractor:
    def __init__(
        self,
        sh_client_id: str | None = None,
        sh_client_secret: str | None = None,
        resolution_degrees: float = 0.01,
        interval_days: int = 30,
        timeout: int = 180,
        flood_model_path: str = FLOOD_MODEL_PATH,
        flood_detection_model_path: str = FLOOD_DETECTION_MODEL_PATH,
        drought_model_path: str = DROUGHT_MODEL_PATH,
    ):
        self.sh_client_id = sh_client_id or SH_CLIENT_ID
        self.sh_client_secret = sh_client_secret or SH_CLIENT_SECRET
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
            "calculations": {
                "default": {
                    "statistics": {
                        "default": {"percentiles": {"k": [25, 50, 75]}}
                    }
                }
            },
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
    # Weather
    # ------------------------------------------------------------------

    def fetch_openmeteo(self, lat: float, lon: float, date: str | None = None) -> dict:
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
                    "daily": "precipitation_sum,temperature_2m_max",
                    "hourly": "soil_moisture_0_to_7cm",
                    "timezone": "UTC",
                }
            else:
                url = "https://api.open-meteo.com/v1/forecast"
                params = {
                    "latitude": lat,
                    "longitude": lon,
                    "daily": "precipitation_sum,temperature_2m_max",
                    "hourly": "soil_moisture_0_to_7cm",
                    "past_days": 30,
                    "forecast_days": 2,
                    "timezone": "UTC",
                }

            resp = requests.get(url, params=params, timeout=25)
            resp.raise_for_status()
            data = resp.json()

            daily = data.get("daily", {})
            hourly = data.get("hourly", {})
            precip = [v for v in (daily.get("precipitation_sum", []) or []) if v is not None]
            temp = [v for v in (daily.get("temperature_2m_max", []) or []) if v is not None]
            soil = [v * 100 for v in (hourly.get("soil_moisture_0_to_7cm", []) or []) if v is not None]

            soil_current = round(soil[-1], 1) if soil else None
            soil_7d_ago = round(soil[-7 * 24], 1) if len(soil) >= 7 * 24 else None

            forecast_precip_24h = 0.0
            if not date:
                # For forecast API, daily includes recent + forecast days. Last 1–2 values are forecast.
                forecast_precip_24h = round(sum(precip[-1:]), 1) if precip else 0.0

            return {
                "precip_mm_7d": round(sum(precip[-7:]), 1) if precip else 0.0,
                "precip_mm_30d": round(sum(precip[-30:]), 1) if precip else 0.0,
                "temp_max_c": round(max(temp[-7:]), 1) if temp else None,
                "soil_moisture_pct": soil_current,
                "soil_moisture_7d_delta": round(soil_current - soil_7d_ago, 1) if soil_current is not None and soil_7d_ago is not None else None,
                "forecast_precip_24h": forecast_precip_24h,
            }
        except Exception as exc:
            logger.error("OpenMeteo failed: %s", exc)
            return {}

    # ------------------------------------------------------------------
    # Derived values
    # ------------------------------------------------------------------

    @staticmethod
    def compute_flood_extent_km2(bbox: list[float], ndwi: float | None) -> float:
        lon_min, lat_min, lon_max, lat_max = bbox
        area_km2 = abs(lon_max - lon_min) * abs(lat_max - lat_min) * 111.32 ** 2
        return round(max(0.0, ndwi or 0.0) * area_km2 * 0.15, 1)

    @staticmethod
    def compute_drought_index(precip_mm_30d: float | None, soil_moisture_pct: float | None, ndvi: float | None) -> float | None:
        if precip_mm_30d is None and soil_moisture_pct is None and ndvi is None:
            return None
        precip = precip_mm_30d if precip_mm_30d is not None else 30.0
        soil = soil_moisture_pct if soil_moisture_pct is not None else 30.0
        veg = ndvi if ndvi is not None else 0.35
        precip_stress = max(0.0, min(1.0, (40.0 - precip) / 40.0))
        soil_stress = max(0.0, min(1.0, (35.0 - soil) / 35.0))
        ndvi_stress = max(0.0, min(1.0, (0.45 - veg) / 0.45))
        return round(0.45 * precip_stress + 0.35 * soil_stress + 0.20 * ndvi_stress, 3)

    @staticmethod
    def week_of_year(date_like: str | datetime | None = None) -> int:
        if date_like is None:
            dt = datetime.now(timezone.utc)
        elif isinstance(date_like, datetime):
            dt = date_like
        else:
            dt = datetime.strptime(str(date_like)[:10], "%Y-%m-%d")
        return dt.isocalendar().week

    # ------------------------------------------------------------------
    # Threshold labels: ordinal risk 0–4
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

    def threshold_risk_from_row(self, row: dict) -> dict:
        date_raw = row.get("end_date") or row.get("data_timestamp") or datetime.now(timezone.utc)
        month = datetime.fromisoformat(str(date_raw).replace("Z", "+00:00")).month if isinstance(date_raw, str) else date_raw.month

        if month in [3, 4, 5]:
            season, flood_factor, drought_enabled, flash_threshold = "spring", 1.0, False, 70.0
        elif month in [6, 7, 8]:
            season, flood_factor, drought_enabled, flash_threshold = "summer", 1.0, True, 60.0
        elif month in [9, 10, 11]:
            season, flood_factor, drought_enabled, flash_threshold = "autumn", 0.8, True, 70.0
        else:
            season, flood_factor, drought_enabled, flash_threshold = "winter", 1.0, False, 70.0

        def v(key: str) -> float | None:
            val = row.get(key)
            try:
                return float(val) if val is not None else None
            except Exception:
                return None

        p7 = v("precip_mm_7d")
        p30 = v("precip_mm_30d")
        fc24 = v("forecast_precip_24h_mm")
        soil = v("soil_moisture_pct")
        soil_delta = v("soil_moisture_7d_delta")
        ndvi = v("ndvi")
        ndwi = v("ndwi")
        temp = v("temp_max_c")
        drought_index = v("drought_index")
        flood_extent = v("flood_extent_km2")
        river_level = v("river_level_m")

        fw = fwarn = dw = dwarn = 0
        flood_score = drought_score = 0.0

        if p7 is not None and p7 > 40 * flood_factor:
            fw += 1; flood_score += 1
        if p7 is not None and p7 > 80 * flood_factor:
            fwarn += 1; flood_score += 2
        if fc24 is not None and fc24 > 50:
            fw += 1; flood_score += 1
        if fc24 is not None and fc24 > 80:
            fwarn += 1; flood_score += 2
        if soil is not None and soil > 75:
            fw += 1; flood_score += 1
        if soil is not None and soil > 85:
            fwarn += 1; flood_score += 2
        if river_level is not None and river_level > 0.4:
            fw += 1; flood_score += 1
        if river_level is not None and river_level > 0.8:
            fwarn += 1; flood_score += 2
        if ndwi is not None and ndwi > 0.1:
            fw += 1; flood_score += 1
        if ndwi is not None and ndwi > 0.25:
            fwarn += 1; flood_score += 2
        if flood_extent is not None and flood_extent > 5:
            fw += 1; flood_score += 1
        if flood_extent is not None and flood_extent > 20:
            fwarn += 1; flood_score += 2
        if fc24 is not None and soil is not None and fc24 > flash_threshold and soil > 80:
            fwarn += 1; flood_score += 3
        if soil_delta is not None and p7 is not None and soil_delta > 20 and p7 > 35:
            fw += 1; flood_score += 1.5
        if drought_index is not None and fc24 is not None and drought_index < -1.5 and fc24 > 60:
            fwarn += 1; flood_score += 3
        if fw >= 2:
            fwarn += 1; flood_score += 1

        if drought_enabled:
            if drought_index is not None and drought_index < -1.0:
                dw += 1; drought_score += 1
            if drought_index is not None and drought_index < -1.5:
                dwarn += 1; drought_score += 2
            if ndvi is not None and ndvi < 0.25:
                dw += 1; drought_score += 1
            if ndvi is not None and ndvi < 0.15:
                dwarn += 1; drought_score += 2
            if soil is not None and soil < 20:
                dw += 1; drought_score += 1
            if soil is not None and soil < 10:
                dwarn += 1; drought_score += 2
            if p30 is not None and p30 < 13.5:
                dw += 1; drought_score += 1
            if p30 is not None and p30 < 4.5:
                dwarn += 1; drought_score += 2
            if temp is not None and temp > 33:
                dw += 1; drought_score += 1
            if temp is not None and temp > 38:
                dwarn += 1; drought_score += 2

        flood_level = self.risk_level_from_score(flood_score)
        drought_level = self.risk_level_from_score(drought_score)

        confidence = 1.0
        if river_level is None:
            confidence -= 0.10
        if drought_index is None:
            confidence -= 0.10
        if ndwi is None:
            confidence -= 0.10

        return {
            "season": season,
            "threshold_flood_score": flood_score,
            "threshold_drought_score": drought_score,
            "flood_risk_level": flood_level,
            "drought_risk_level": drought_level,
            "flood_risk_label": self.risk_name(flood_level),
            "drought_risk_label": self.risk_name(drought_level),
            "flood_watch_count": fw,
            "flood_warning_count": fwarn,
            "drought_watch_count": dw,
            "drought_warning_count": dwarn,
            "alert_confidence": round(max(0.3, confidence), 2),
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
            import pandas as pd
            import numpy as np
        except ImportError:
            return {
                "ml_available": False,
                "reason": "pandas/numpy not installed",
            }

        flood_precursor_model, flood_detection_model, drought_model = self.load_models()
        if flood_precursor_model is None and flood_detection_model is None and drought_model is None:
            return {
                "ml_available": False,
                "reason": "trained models not found or xgboost unavailable",
            }

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

        # Runtime note:
        # For a true precursor model, the API should ideally use stored previous AOI values.
        # Until persistence is added, today's values are mapped into the same feature schema.
        # This keeps the model callable, but the result should be interpreted carefully.
        if flood_precursor_model is not None:
            pred, conf = predict_with(
                flood_precursor_model,
                FLOOD_SATURATION_PRECURSOR_FEATURES,
                lag_prefix="feature_t_minus_1",
            )
            out["flood_precursor_risk_level_ml"] = pred
            out["flood_precursor_risk_label_ml"] = self.risk_name(pred)
            out["flood_precursor_risk_confidence_ml"] = conf

        if flood_detection_model is not None:
            pred, conf = predict_with(
                flood_detection_model,
                FLOOD_DETECTION_FEATURES,
                lag_prefix="feature_t_minus_0",
            )
            out["flood_detection_risk_level_ml"] = pred
            out["flood_detection_risk_label_ml"] = self.risk_name(pred)
            out["flood_detection_risk_confidence_ml"] = conf

        if drought_model is not None:
            pred, conf = predict_with(
                drought_model,
                TRAINING_FEATURES,
                lag_prefix="feature_t_minus_1",
            )
            out["drought_risk_level_ml"] = pred
            out["drought_risk_label_ml"] = self.risk_name(pred)
            out["drought_risk_confidence_ml"] = conf

        return out

    @staticmethod
    def choose_status(flood_label: str, drought_label: str) -> str:
        order = {
            "SAFE": 0,
            "LOW_RISK": 1,
            "MODERATE_RISK": 2,
            "HIGH_RISK": 3,
            "VERY_HIGH_RISK": 4,
        }
        flood_level = order.get(flood_label, 0)
        drought_level = order.get(drought_label, 0)

        if flood_level >= drought_level:
            if flood_level >= 3:
                return "FLOOD_WARNING"
            if flood_level == 2:
                return "FLOOD_WATCH"
            return "SAFE"
        else:
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

        weather = self.fetch_openmeteo(centre_lat, centre_lon)
        drought_index = self.compute_drought_index(weather.get("precip_mm_30d"), weather.get("soil_moisture_pct"), ndvi)

        snapshot = {
            "ndvi": ndvi if ndvi is not None else 0.35,
            "soil_moisture_pct": weather.get("soil_moisture_pct") or 30.0,
            "precip_mm_7d": weather.get("precip_mm_7d") or 0.0,
            "precip_mm_30d": weather.get("precip_mm_30d") or 0.0,
            "river_level_m": None,
            "flood_extent_km2": self.compute_flood_extent_km2(bbox, ndwi),
            "temp_max_c": weather.get("temp_max_c") or 20.0,
            "drought_index": drought_index,
            "data_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source": "Sentinel Hub Statistical API + OpenMeteo + local ML risk model",
            "ndwi": ndwi,
            "soil_moisture_7d_delta": weather.get("soil_moisture_7d_delta"),
            "forecast_precip_24h_mm": weather.get("forecast_precip_24h"),
            "s1_moisture": s1_moisture,
            "s1_vv_db": s1_vv_db,
            "s1_vh_db": s1_vh_db,
            "week_of_year": self.week_of_year(),
        }

        threshold = self.threshold_risk_from_row(snapshot)
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
                "threshold_label": snapshot.get("flood_risk_label"),
                "ml_detection_label": ml.get("flood_detection_risk_label_ml"),
                "ml_detection_confidence": ml.get("flood_detection_risk_confidence_ml"),
                "ml_precursor_label": ml.get("flood_precursor_risk_label_ml"),
                "ml_precursor_confidence": ml.get("flood_precursor_risk_confidence_ml"),
            },
            "drought": {
                "threshold_label": snapshot.get("drought_risk_label"),
                "ml_label": ml.get("drought_risk_label_ml"),
                "ml_confidence": ml.get("drought_risk_confidence_ml"),
            },
        }

                # Ensure clean API output with timestamp
        return {
            "timestamp": snapshot.get("data_timestamp"),
            "bbox": bbox,
            "data": snapshot
        }

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
            weather = self.fetch_openmeteo(centre_lat, centre_lon, end_date)
            drought_index = self.compute_drought_index(weather.get("precip_mm_30d"), weather.get("soil_moisture_pct"), ndvi)
            row = {
                "aoi_name": aoi_name,
                "start_date": start_date,
                "end_date": end_date,
                "ndvi": ndvi,
                "ndwi": ndwi,
                "s1_moisture": s1_by.get(start_date),
                "s1_vv_db": vv_by.get(start_date),
                "s1_vh_db": vh_by.get(start_date),
                "soil_moisture_pct": weather.get("soil_moisture_pct"),
                "soil_moisture_7d_delta": weather.get("soil_moisture_7d_delta"),
                "precip_mm_7d": weather.get("precip_mm_7d"),
                "precip_mm_30d": weather.get("precip_mm_30d"),
                "forecast_precip_24h_mm": weather.get("forecast_precip_24h"),
                "temp_max_c": weather.get("temp_max_c"),
                "river_level_m": None,
                "flood_extent_km2": self.compute_flood_extent_km2(bbox, ndwi),
                "drought_index": drought_index,
                "data_timestamp": f"{end_date}T23:59:59Z",
                "source": "Sentinel Hub Statistical API + OpenMeteo",
                "week_of_year": self.week_of_year(end_date),
            }
            row.update(self.threshold_risk_from_row(row))
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
        try:
            import pandas as pd
        except ImportError as exc:
            raise ImportError("Requires pandas.") from exc

        df = self._rows_to_dataframe(rows, csv_path)
        group_cols = ["aoi_name"] if "aoi_name" in df.columns else []
        df = df.sort_values(group_cols + ["end_date"]).reset_index(drop=True)

        target_cols = [
            "flood_risk_level", "flood_risk_label",
            "drought_risk_level", "drought_risk_label",
            "threshold_flood_score", "threshold_drought_score",
            "alert_confidence",
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
                    "generic_lag1_features": TRAINING_FEATURES,
                    "flood_saturation_precursor_features": FLOOD_SATURATION_PRECURSOR_FEATURES,
                    "flood_detection_features": FLOOD_DETECTION_FEATURES,
                },
                f,
                indent=2,
            )


def get_eo_and_weather_data(bbox: list) -> dict:
    return Sentinel_Extractor().get_eo_and_weather_data(bbox)


# Backward-compatible wrappers
_get_sh_token = lambda: Sentinel_Extractor().get_sh_token()
_extract_mean_from_stats = Sentinel_Extractor.extract_mean_from_stats
_fetch_openmeteo = lambda lat, lon, date=None: Sentinel_Extractor().fetch_openmeteo(lat, lon, date)


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

    print("STEP 1 — Build multi-AOI EO/weather time series")
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
