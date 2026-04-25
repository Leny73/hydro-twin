"""
sentinel_extractor.py — Earth Observation, Weather & Time Series Data
=====================================================================

⚠️  THIS FILE IS OWNED BY THE DATA ANALYSTS TEAM.
    The public function signature and return-dict schema MUST remain unchanged.
    lambda_handler.py imports get_eo_and_weather_data(bbox) directly.

Main class:
    Sentinel_Extractor

Public compatibility function:
    get_eo_and_weather_data(bbox: list) -> dict

Data strategy:
    - Sentinel Hub Statistical API for Sentinel-2 NDVI / NDWI and Sentinel-1 SAR moisture proxy.
    - OpenMeteo archive/forecast APIs for weather and modelled soil moisture.
    - Optional OpenMeteo Flood API for modelled river discharge.
    - Efficient time series: one Sentinel Hub request per EO dataset over the whole period.

Install:
    pip install requests python-dotenv
"""

import csv
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

SH_CLIENT_ID = os.environ.get("SH_CLIENT_ID", "")
SH_CLIENT_SECRET = os.environ.get("SH_CLIENT_SECRET", "")
SH_TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
SH_STATS_URL = "https://sh.dataspace.copernicus.eu/statistics/v1"

# Pleven Oblast bbox: [lon_min, lat_min, lon_max, lat_max]
PLEVEN_BBOX = [23.90, 43.15, 25.20, 43.70]

# ~5 km × 5 km around Pleven, WGS84 / CRS84
PLEVEN_SMALL_BBOX = [24.5858, 43.3954, 24.6475, 43.4404]


# ── Evalscripts ───────────────────────────────────────────────────────────────

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

function toDb(x) {
  return 10 * Math.log(x) / Math.LN10;
}

function clamp(x, minVal, maxVal) {
  return Math.max(minVal, Math.min(maxVal, x));
}

function evaluatePixel(sample) {
  if (sample.dataMask === 0 || sample.VV <= 0 || sample.VH <= 0) {
    return {
      s1_moisture: [NaN],
      vv_db: [NaN],
      vh_db: [NaN],
      dataMask: [0],
    };
  }

  let vvDb = toDb(sample.VV);
  let vhDb = toDb(sample.VH);

  // Relative SAR wetness proxy, not absolute soil moisture.
  // Wider range avoids constant saturation at 1.0.
  let moisture = clamp((vvDb - (-25.0)) / 25.0, 0.0, 1.0);

  return {
    s1_moisture: [moisture],
    vv_db: [vvDb],
    vh_db: [vhDb],
    dataMask: [1],
  };
}
"""


class Sentinel_Extractor:
    """
    Extract current EO/weather values and efficient historical time series.

    Key time-series derived signals:
      - z-score normalization for weather/moisture variables
      - seasonal baseline by week-of-year with nearby-week smoothing
      - smoothed anomaly using exponential weighting
      - cumulative smoothed effect for weather/moisture derived fields
      - Sentinel-derived fields kept raw as requested
    """

    def __init__(
        self,
        sh_client_id: str | None = None,
        sh_client_secret: str | None = None,
        token_url: str = SH_TOKEN_URL,
        stats_url: str = SH_STATS_URL,
        resolution_degrees: float = 0.002,
        interval_days: int = 14,
        timeout: int = 120,
    ):
        self.sh_client_id = sh_client_id or SH_CLIENT_ID
        self.sh_client_secret = sh_client_secret or SH_CLIENT_SECRET
        self.token_url = token_url
        self.stats_url = stats_url
        self.resolution_degrees = resolution_degrees
        self.interval_days = interval_days
        self.timeout = timeout

    # ──────────────────────────────────────────────────────────────────────
    # Sentinel Hub helpers
    # ──────────────────────────────────────────────────────────────────────

    def get_sh_token(self) -> str:
        if not self.sh_client_id or not self.sh_client_secret:
            logger.warning("SH_CLIENT_ID / SH_CLIENT_SECRET not set — skipping Sentinel Hub calls.")
            return ""

        try:
            resp = requests.post(
                self.token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.sh_client_id,
                    "client_secret": self.sh_client_secret,
                },
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json()["access_token"]
        except Exception as exc:
            logger.error("Sentinel Hub token fetch failed: %s", exc)
            return ""

    def _data_filter(self, dataset: str, max_cloud_pct: int = 30) -> dict:
        if dataset == "sentinel-1-grd":
            return {
                "mosaickingOrder": "mostRecent",
                "acquisitionMode": "IW",
                "polarization": "DV",
                "resolution": "HIGH",
                "orbitDirection": "ASCENDING",
            }

        return {
            "mosaickingOrder": "leastCC",
            "maxCloudCoverage": max_cloud_pct,
        }

    def sh_statistics(
        self,
        token: str,
        bbox: list,
        evalscript: str,
        dataset: str = "sentinel-2-l2a",
        days_back: int = 14,
        max_cloud_pct: int = 30,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        aggregation_interval: str | None = None,
    ) -> dict | None:
        if not token:
            return None

        if start_date and end_date:
            start = start_date.strftime("%Y-%m-%dT00:00:00Z")
            end = end_date.strftime("%Y-%m-%dT23:59:59Z")
        else:
            now = datetime.now(timezone.utc)
            start = (now - timedelta(days=days_back)).strftime("%Y-%m-%dT00:00:00Z")
            end = now.strftime("%Y-%m-%dT23:59:59Z")

        payload = {
            "input": {
                "bounds": {
                    "bbox": bbox,
                    "properties": {"crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"},
                },
                "data": [{
                    "type": dataset,
                    "dataFilter": self._data_filter(dataset, max_cloud_pct=max_cloud_pct),
                }],
            },
            "aggregation": {
                "timeRange": {"from": start, "to": end},
                "aggregationInterval": {"of": aggregation_interval or "P1D"},
                "evalscript": evalscript,
                "resx": self.resolution_degrees,
                "resy": self.resolution_degrees,
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
                self.stats_url,
                json=payload,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                logger.error("Sentinel Hub %s failed HTTP %s: %s", dataset, resp.status_code, resp.text[:1000])
                return None
            return resp.json()
        except Exception as exc:
            logger.error("Sentinel Hub Statistical API call failed: %s", exc)
            return None

    @staticmethod
    def extract_mean_from_stats(sh_response: dict | None, output_band: str = "B0") -> float | None:
        if not sh_response:
            return None
        try:
            intervals = sh_response.get("data", [])
            for interval in reversed(intervals):
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
                if mean is not None and sample_count > 0 and sample_count > no_data_count:
                    return round(float(mean), 4)
        except Exception as exc:
            logger.warning("Could not extract mean from SH response: %s", exc)
        return None

    @staticmethod
    def extract_interval_mean(sh_response: dict | None, output_band: str) -> dict[str, float | None]:
        result = {}
        if not sh_response:
            return result

        for interval in sh_response.get("data", []):
            interval_start = interval.get("interval", {}).get("from", "")[:10]
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

            if mean is not None and sample_count > 0 and sample_count > no_data_count:
                result[interval_start] = round(float(mean), 4)
            else:
                result[interval_start] = None

        return result

    @staticmethod
    def extract_interval_dates(sh_response: dict | None) -> list[tuple[str, str]]:
        if not sh_response:
            return []

        intervals = []
        for item in sh_response.get("data", []):
            start = item.get("interval", {}).get("from", "")[:10]
            end = item.get("interval", {}).get("to", "")[:10]
            if start and end:
                intervals.append((start, end))
        return intervals

    # ──────────────────────────────────────────────────────────────────────
    # Weather / river helpers
    # ──────────────────────────────────────────────────────────────────────

    def fetch_openmeteo(self, lat: float, lon: float, date: str | None = None) -> dict:
        """
        If date is None: fetch recent + forecast weather.
        If date is YYYY-MM-DD: fetch 30-day archive ending on that date.
        """
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

            resp = requests.get(url, params=params, timeout=20)
            resp.raise_for_status()
            data = resp.json()

            daily = data.get("daily", {})
            hourly = data.get("hourly", {})

            precip = daily.get("precipitation_sum", []) or []
            temp_max = daily.get("temperature_2m_max", []) or []
            soil_vals = hourly.get("soil_moisture_0_to_7cm", []) or []

            precip_clean = [p for p in precip if p is not None]
            temp_clean = [t for t in temp_max if t is not None]
            soil_clean = [s * 100 for s in soil_vals if s is not None]

            precip_7d = round(sum(precip_clean[-7:]), 1) if precip_clean else 0.0
            precip_30d = round(sum(precip_clean[-30:]), 1) if precip_clean else 0.0
            temp_max_7d = round(max(temp_clean[-7:]), 1) if temp_clean else None

            soil_current = round(soil_clean[-1], 1) if soil_clean else None
            soil_7d_ago = round(soil_clean[-7 * 24], 1) if len(soil_clean) >= 7 * 24 else None
            soil_delta = (
                round(soil_current - soil_7d_ago, 1)
                if soil_current is not None and soil_7d_ago is not None
                else None
            )

            return {
                "precip_mm_7d": precip_7d,
                "precip_mm_30d": precip_30d,
                "temp_max_c": temp_max_7d,
                "soil_moisture_pct": soil_current,
                "soil_moisture_7d_delta": soil_delta,
                "forecast_precip_24h": 0.0 if date else None,
            }

        except Exception as exc:
            logger.error("OpenMeteo request failed: %s", exc)
            return {}

    def fetch_river_discharge(self, lat: float, lon: float, start_date: str, end_date: str) -> dict:
        url = "https://flood-api.open-meteo.com/v1/flood"
        params = {
            "latitude": lat,
            "longitude": lon,
            "daily": "river_discharge",
            "start_date": start_date,
            "end_date": end_date,
            "timezone": "UTC",
        }
        try:
            resp = requests.get(url, params=params, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            discharge = data.get("daily", {}).get("river_discharge", []) or []
            clean = [v for v in discharge if v is not None]
            return {
                "river_discharge_m3s": round(sum(clean) / len(clean), 2) if clean else None,
                "river_discharge_max_m3s": round(max(clean), 2) if clean else None,
            }
        except Exception as exc:
            logger.error("River discharge fetch failed: %s", exc)
            return {
                "river_discharge_m3s": None,
                "river_discharge_max_m3s": None,
            }

    # ──────────────────────────────────────────────────────────────────────
    # Derived metrics
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def compute_flood_extent_km2(bbox: list, ndwi: float | None) -> float:
        lon_min, lat_min, lon_max, lat_max = bbox
        bbox_area_km2 = abs(lon_max - lon_min) * abs(lat_max - lat_min) * 111.32 ** 2
        if ndwi is None:
            return 0.0
        return round(max(0.0, ndwi) * bbox_area_km2 * 0.15, 1)

    @staticmethod
    def compute_drought_index(
        precip_mm_30d: float | None,
        soil_moisture_pct: float | None,
        ndvi: float | None,
    ) -> float | None:
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
    def _mean(values: list[float]) -> float | None:
        clean = [v for v in values if v is not None]
        return sum(clean) / len(clean) if clean else None

    @staticmethod
    def _std(values: list[float]) -> float | None:
        clean = [v for v in values if v is not None]
        if len(clean) < 2:
            return None
        mu = sum(clean) / len(clean)
        var = sum((x - mu) ** 2 for x in clean) / (len(clean) - 1)
        return var ** 0.5

    @staticmethod
    def _safe_z(value: float | None, mean: float | None, std: float | None) -> float | None:
        if value is None or mean is None or std is None or std == 0:
            return None
        return round((value - mean) / std, 4)

    @staticmethod
    def _safe_round(value: float | None, ndigits: int = 4) -> float | None:
        return round(float(value), ndigits) if value is not None else None

    @staticmethod
    def _week_of_year(date_str: str) -> int:
        return datetime.strptime(date_str, "%Y-%m-%d").isocalendar().week

    def add_time_series_signals(
        self,
        rows: list[dict],
        seasonal_window_weeks: int = 2,
        anomaly_alpha: float = 0.25,
        cumulative_alpha: float = 0.88,
    ) -> list[dict]:
        """
        Add engineered time-series signals.

        Weather / moisture variables:
          - Z-score normalization: <field>_z
          - smoothed seasonal anomaly: <field>_anomaly_smooth
          - cumulative exponentially-decayed effect: <field>_cumulative_effect

        Satellite variables:
          - Min-Max normalization only: <field>_minmax
          - raw seasonal anomaly only: <field>_anomaly
          - NO smoothing
          - NO cumulative effect

        Reason:
          Weather/moisture has physical memory.
          Satellite imagery should stay closer to the observed signal.
        """
        if not rows:
            return rows

        weather_moisture_cols = [
            "soil_moisture_pct",
            "precip_mm_7d",
            "precip_mm_30d",
            "temp_max_c",
            "soil_moisture_7d_delta",
            "drought_index",
            "river_discharge_m3s",
            "river_discharge_max_m3s",
        ]

        satellite_cols = [
            "ndvi",
            "ndwi",
            "s1_moisture",
            "s1_vv_db",
            "s1_vh_db",
            "flood_extent_km2",
        ]

        # Add week-of-year.
        for row in rows:
            row["week_of_year"] = self._week_of_year(row["end_date"])

        # ── Weather / moisture: Z-score + smoothed anomaly + cumulative effect.
        for col in weather_moisture_cols:
            values = [row.get(col) for row in rows]
            mu = self._mean(values)
            sigma = self._std(values)

            for row in rows:
                row[f"{col}_z"] = self._safe_z(row.get(col), mu, sigma)

            # Seasonal baseline with nearby-week smoothing.
            for row in rows:
                week = row["week_of_year"]
                nearby_vals = []

                for candidate in rows:
                    candidate_week = candidate["week_of_year"]
                    dist = min(abs(candidate_week - week), 53 - abs(candidate_week - week))
                    if dist <= seasonal_window_weeks:
                        val = candidate.get(col)
                        if val is not None:
                            nearby_vals.append(val)

                seasonal = self._mean(nearby_vals)
                row[f"{col}_seasonal"] = self._safe_round(seasonal)
                row[f"{col}_anomaly"] = self._safe_round(
                    row.get(col) - seasonal
                    if row.get(col) is not None and seasonal is not None
                    else None
                )

            # EWMA smoothing for weather/moisture anomaly.
            previous_smoothed = None
            for row in rows:
                anomaly = row.get(f"{col}_anomaly")
                if anomaly is None:
                    row[f"{col}_anomaly_smooth"] = self._safe_round(previous_smoothed)
                    continue

                if previous_smoothed is None:
                    smoothed = anomaly
                else:
                    smoothed = anomaly_alpha * anomaly + (1 - anomaly_alpha) * previous_smoothed

                previous_smoothed = smoothed
                row[f"{col}_anomaly_smooth"] = self._safe_round(smoothed)

            # Exponentially decayed cumulative effect.
            cumulative = None
            for row in rows:
                smoothed = row.get(f"{col}_anomaly_smooth")
                if smoothed is None:
                    row[f"{col}_cumulative_effect"] = self._safe_round(cumulative)
                    continue

                if cumulative is None:
                    cumulative = smoothed
                else:
                    cumulative = cumulative_alpha * cumulative + smoothed

                row[f"{col}_cumulative_effect"] = self._safe_round(cumulative)

        # ── Satellite: Min-Max normalization + raw seasonal anomaly only.
        for col in satellite_cols:
            clean_values = [row.get(col) for row in rows if row.get(col) is not None]
            vmin = min(clean_values) if clean_values else None
            vmax = max(clean_values) if clean_values else None

            for row in rows:
                value = row.get(col)
                if value is None or vmin is None or vmax is None or vmax == vmin:
                    row[f"{col}_minmax"] = None
                else:
                    row[f"{col}_minmax"] = round((value - vmin) / (vmax - vmin), 4)

            # Seasonal baseline and raw anomaly, but no smoothing.
            for row in rows:
                week = row["week_of_year"]
                nearby_vals = []

                for candidate in rows:
                    candidate_week = candidate["week_of_year"]
                    dist = min(abs(candidate_week - week), 53 - abs(candidate_week - week))
                    if dist <= seasonal_window_weeks:
                        val = candidate.get(col)
                        if val is not None:
                            nearby_vals.append(val)

                seasonal = self._mean(nearby_vals)
                row[f"{col}_seasonal"] = self._safe_round(seasonal)
                row[f"{col}_anomaly"] = self._safe_round(
                    row.get(col) - seasonal
                    if row.get(col) is not None and seasonal is not None
                    else None
                )

        return rows

    # ──────────────────────────────────────────────────────────────────────
    # Current snapshot API
    # ──────────────────────────────────────────────────────────────────────

    def get_eo_and_weather_data(self, bbox: list) -> dict:
        lon_min, lat_min, lon_max, lat_max = bbox
        centre_lat = (lat_min + lat_max) / 2
        centre_lon = (lon_min + lon_max) / 2

        token = self.get_sh_token()

        ndvi_raw = self.sh_statistics(token, bbox, EVALSCRIPT_NDVI, dataset="sentinel-2-l2a", days_back=14)
        ndwi_raw = self.sh_statistics(token, bbox, EVALSCRIPT_NDWI, dataset="sentinel-2-l2a", days_back=14)
        s1_raw = self.sh_statistics(token, bbox, EVALSCRIPT_S1_MOISTURE, dataset="sentinel-1-grd", days_back=14)

        ndvi = self.extract_mean_from_stats(ndvi_raw, output_band="ndvi")
        ndwi = self.extract_mean_from_stats(ndwi_raw, output_band="ndwi")
        s1_moisture = self.extract_mean_from_stats(s1_raw, output_band="s1_moisture")
        s1_vv_db = self.extract_mean_from_stats(s1_raw, output_band="vv_db")
        s1_vh_db = self.extract_mean_from_stats(s1_raw, output_band="vh_db")

        flood_extent_km2 = self.compute_flood_extent_km2(bbox, ndwi)
        weather = self.fetch_openmeteo(centre_lat, centre_lon)
        drought_index = self.compute_drought_index(
            precip_mm_30d=weather.get("precip_mm_30d"),
            soil_moisture_pct=weather.get("soil_moisture_pct"),
            ndvi=ndvi,
        )

        has_sh_data = token != ""
        source_note = (
            "Sentinel Hub Statistical API (S2-L2A NDVI/NDWI + S1-GRD moisture proxy) + OpenMeteo"
            if has_sh_data
            else "OpenMeteo only (Sentinel Hub credentials not set — EO metrics are estimated/null)"
        )

        return {
            # Core EO fields required by lambda_handler.py — do not rename/remove.
            "ndvi": ndvi if ndvi is not None else 0.35,
            "soil_moisture_pct": weather.get("soil_moisture_pct") or 30.0,
            "precip_mm_7d": weather.get("precip_mm_7d") or 0.0,
            "precip_mm_30d": weather.get("precip_mm_30d") or 0.0,
            "river_level_m": None,
            "flood_extent_km2": flood_extent_km2,
            "temp_max_c": weather.get("temp_max_c") or 20.0,
            "drought_index": drought_index,
            "data_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source": source_note,

            # Additional anomaly / EO signals.
            "ndwi": ndwi,
            "soil_moisture_7d_delta": weather.get("soil_moisture_7d_delta"),
            "forecast_precip_24h_mm": weather.get("forecast_precip_24h"),
            "s1_moisture": s1_moisture,
            "s1_moisture_pct": round(s1_moisture * 100, 1) if s1_moisture is not None else None,
            "s1_vv_db": s1_vv_db,
            "s1_vh_db": s1_vh_db,
        }

    # ──────────────────────────────────────────────────────────────────────
    # Efficient time series API
    # ──────────────────────────────────────────────────────────────────────

    def get_time_range(self, years_back: float = 5) -> tuple[datetime, datetime]:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=int(365 * years_back))
        return start, end

    @staticmethod
    def _merge_sh_responses(responses: list[dict | None]) -> dict | None:
        """
        Merge multiple Sentinel Hub Statistical API responses into one response.
        Used to avoid very large multi-year requests that may be dropped by the server.
        """
        valid = [r for r in responses if r and isinstance(r, dict)]
        if not valid:
            return None

        merged = dict(valid[0])
        merged["data"] = []

        for response in valid:
            merged["data"].extend(response.get("data", []))

        merged["data"] = sorted(
            merged["data"],
            key=lambda item: item.get("interval", {}).get("from", ""),
        )
        return merged

    @staticmethod
    def _year_chunks(start_date: datetime, end_date: datetime) -> list[tuple[datetime, datetime]]:
        """
        Split a large time range into yearly chunks.
        This keeps Sentinel Hub requests small enough to avoid RemoteDisconnected errors.
        """
        chunks = []
        current = start_date

        while current < end_date:
            next_year = datetime(current.year + 1, 1, 1, tzinfo=timezone.utc)
            chunk_end = min(next_year, end_date)
            chunks.append((current, chunk_end))
            current = chunk_end

        return chunks

    def fetch_eo_time_series_raw(
        self,
        bbox: list,
        years_back: float = 5,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        chunk_by_year: bool = True,
    ) -> tuple[dict | None, dict | None, dict | None]:
        """
        Fetch NDVI, NDWI and Sentinel-1 moisture time series efficiently.

        Important:
          - Uses one Sentinel Hub request per dataset per chunk.
          - Default chunking is yearly to avoid server disconnects on large requests.
          - Returned responses are merged so downstream code stays unchanged.
        """
        token = self.get_sh_token()
        if not token:
            return None, None, None

        if not start_date or not end_date:
            start_date, end_date = self.get_time_range(years_back)

        interval = f"P{self.interval_days}D"
        chunks = self._year_chunks(start_date, end_date) if chunk_by_year else [(start_date, end_date)]

        ndvi_responses = []
        ndwi_responses = []
        s1_responses = []

        for idx, (chunk_start, chunk_end) in enumerate(chunks, start=1):
            print(
                f"Sentinel chunk {idx}/{len(chunks)}: "
                f"{chunk_start.date()} → {chunk_end.date()}"
            )

            ndvi_responses.append(
                self.sh_statistics(
                    token=token,
                    bbox=bbox,
                    evalscript=EVALSCRIPT_NDVI,
                    dataset="sentinel-2-l2a",
                    start_date=chunk_start,
                    end_date=chunk_end,
                    aggregation_interval=interval,
                )
            )

            ndwi_responses.append(
                self.sh_statistics(
                    token=token,
                    bbox=bbox,
                    evalscript=EVALSCRIPT_NDWI,
                    dataset="sentinel-2-l2a",
                    start_date=chunk_start,
                    end_date=chunk_end,
                    aggregation_interval=interval,
                )
            )

            s1_responses.append(
                self.sh_statistics(
                    token=token,
                    bbox=bbox,
                    evalscript=EVALSCRIPT_S1_MOISTURE,
                    dataset="sentinel-1-grd",
                    start_date=chunk_start,
                    end_date=chunk_end,
                    aggregation_interval=interval,
                )
            )

        return (
            self._merge_sh_responses(ndvi_responses),
            self._merge_sh_responses(ndwi_responses),
            self._merge_sh_responses(s1_responses),
        )

    def build_time_series_rows(
        self,
        bbox: list,
        ndvi_raw: dict | None,
        ndwi_raw: dict | None,
        s1_raw: dict | None,
        include_river_discharge: bool = False,
    ) -> list[dict]:
        lon_min, lat_min, lon_max, lat_max = bbox
        centre_lat = (lat_min + lat_max) / 2
        centre_lon = (lon_min + lon_max) / 2

        intervals = self.extract_interval_dates(ndvi_raw)
        ndvi_by_date = self.extract_interval_mean(ndvi_raw, "ndvi")
        ndwi_by_date = self.extract_interval_mean(ndwi_raw, "ndwi")
        s1_by_date = self.extract_interval_mean(s1_raw, "s1_moisture")
        vv_by_date = self.extract_interval_mean(s1_raw, "vv_db")
        vh_by_date = self.extract_interval_mean(s1_raw, "vh_db")

        rows = []

        for start_date, end_date in intervals:
            ndvi = ndvi_by_date.get(start_date)
            ndwi = ndwi_by_date.get(start_date)
            s1_moisture = s1_by_date.get(start_date)

            weather = self.fetch_openmeteo(centre_lat, centre_lon, end_date)
            drought_index = self.compute_drought_index(
                precip_mm_30d=weather.get("precip_mm_30d"),
                soil_moisture_pct=weather.get("soil_moisture_pct"),
                ndvi=ndvi,
            )

            river = {"river_discharge_m3s": None, "river_discharge_max_m3s": None}
            if include_river_discharge:
                river = self.fetch_river_discharge(centre_lat, centre_lon, start_date, end_date)

            rows.append({
                "start_date": start_date,
                "end_date": end_date,
                "ndvi": ndvi,
                "soil_moisture_pct": weather.get("soil_moisture_pct"),
                "s1_moisture": s1_moisture,
                "s1_vv_db": vv_by_date.get(start_date),
                "s1_vh_db": vh_by_date.get(start_date),
                "precip_mm_7d": weather.get("precip_mm_7d"),
                "precip_mm_30d": weather.get("precip_mm_30d"),
                "river_level_m": None,
                "river_discharge_m3s": river.get("river_discharge_m3s"),
                "river_discharge_max_m3s": river.get("river_discharge_max_m3s"),
                "flood_extent_km2": self.compute_flood_extent_km2(bbox, ndwi),
                "temp_max_c": weather.get("temp_max_c"),
                "drought_index": drought_index,
                "data_timestamp": f"{end_date}T23:59:59Z",
                "ndwi": ndwi,
                "soil_moisture_7d_delta": weather.get("soil_moisture_7d_delta"),
                "forecast_precip_24h_mm": weather.get("forecast_precip_24h"),
                "source": "Sentinel Hub Statistical API + OpenMeteo",
            })

        return rows

    def get_time_series(
        self,
        bbox: list,
        years_back: float = 5,
        include_river_discharge: bool = False,
        add_signals: bool = True,
    ) -> list[dict]:
        ndvi_raw, ndwi_raw, s1_raw = self.fetch_eo_time_series_raw(bbox=bbox, years_back=years_back)
        rows = self.build_time_series_rows(
            bbox=bbox,
            ndvi_raw=ndvi_raw,
            ndwi_raw=ndwi_raw,
            s1_raw=s1_raw,
            include_river_discharge=include_river_discharge,
        )
        if add_signals:
            rows = self.add_time_series_signals(rows)
        return rows

    def save_time_series_csv(self, rows: list[dict], output_path: str) -> None:
        if not rows:
            raise ValueError("No rows to save.")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    # ──────────────────────────────────────────────────────────────────────
    # Plotting helpers
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _rows_to_dataframe(rows: list[dict] | None = None, csv_path: str | None = None):
        """
        Load plotting data from either:
          - rows: list[dict]
          - csv_path: path to a previously saved CSV

        This keeps pandas out of the Lambda runtime path unless plotting is used.
        """
        try:
            import pandas as pd
        except ImportError as exc:
            raise ImportError("Plotting requires pandas. Install with: pip install pandas matplotlib") from exc

        if csv_path:
            df = pd.read_csv(csv_path)
        elif rows is not None:
            df = pd.DataFrame(rows)
        else:
            raise ValueError("Provide either rows or csv_path.")

        if "end_date" in df.columns:
            df["end_date"] = pd.to_datetime(df["end_date"])
            df = df.sort_values("end_date")

        return df

    def plot_relevant_timeseries(
        self,
        rows: list[dict] | None = None,
        csv_path: str | None = None,
        output_path: str | None = None,
        show: bool = False,
    ) -> str | None:
        """
        Plot weather and satellite variables on the same visual scale.

        Important:
          - This rescales values ONLY for plotting.
          - It does NOT modify the saved CSV or the model features.
          - Every plotted variable is Min-Max scaled to [0, 1].

        Weather = blue solid lines.
        Satellite = green/orange/purple dashed lines.
        """
        try:
            import matplotlib.pyplot as plt
        except ImportError as exc:
            raise ImportError("Plotting requires matplotlib. Install with: pip install matplotlib") from exc

        df = self._rows_to_dataframe(rows=rows, csv_path=csv_path)

        weather_cols = [
            "soil_moisture_pct",
            "precip_mm_7d",
            "precip_mm_30d",
            "temp_max_c",
            "drought_index",
        ]

        satellite_cols = [
            "ndvi",
            "ndwi",
            "s1_moisture",
            "flood_extent_km2",
        ]

        weather_cols = [c for c in weather_cols if c in df.columns]
        satellite_cols = [c for c in satellite_cols if c in df.columns]

        def plot_minmax(series):
            series = series.astype(float)
            min_val = series.min(skipna=True)
            max_val = series.max(skipna=True)
            if max_val == min_val:
                return series * 0.0
            return (series - min_val) / (max_val - min_val)

        weather_colors = ["tab:blue", "cornflowerblue", "deepskyblue", "steelblue", "navy"]
        satellite_colors = ["tab:green", "tab:orange", "tab:purple", "olive"]

        plt.figure(figsize=(14, 7))

        for idx, col in enumerate(weather_cols):
            plt.plot(
                df["end_date"],
                plot_minmax(df[col]),
                label=f"Weather — {col}",
                color=weather_colors[idx % len(weather_colors)],
                linewidth=2,
                alpha=0.85,
            )

        for idx, col in enumerate(satellite_cols):
            plt.plot(
                df["end_date"],
                plot_minmax(df[col]),
                label=f"Satellite — {col}",
                color=satellite_colors[idx % len(satellite_colors)],
                linewidth=2,
                linestyle="--",
                alpha=0.95,
            )

        plt.axhline(0, color="black", linewidth=1, alpha=0.25)
        plt.axhline(1, color="black", linewidth=1, alpha=0.25)
        plt.title("Weather vs satellite variables — plot-scaled to 0–1")
        plt.xlabel("Date")
        plt.ylabel("Plot-only Min-Max scale")
        plt.grid(True, alpha=0.3)
        plt.legend(ncol=2)
        plt.tight_layout()

        if output_path:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            plt.savefig(output_path, dpi=160)
            if not show:
                plt.close()
            return output_path

        if show:
            plt.show()
        return None

    def plot_anomaly_effects(
        self,
        rows: list[dict] | None = None,
        csv_path: str | None = None,
        output_path: str | None = None,
        show: bool = False,
    ) -> str | None:
        """
        Plot weather memory effects and satellite anomalies on same visual scale.

        Important:
          - Rescaling is ONLY for plotting.
          - Weather memory effects and satellite anomalies are each Min-Max scaled to [0, 1].
          - Underlying data remains unchanged.
        """
        try:
            import matplotlib.pyplot as plt
        except ImportError as exc:
            raise ImportError("Plotting requires matplotlib. Install with: pip install matplotlib") from exc

        df = self._rows_to_dataframe(rows=rows, csv_path=csv_path)

        weather_effect_cols = [
            "soil_moisture_pct_cumulative_effect",
            "precip_mm_7d_cumulative_effect",
            "precip_mm_30d_cumulative_effect",
            "temp_max_c_cumulative_effect",
            "drought_index_cumulative_effect",
        ]

        satellite_anomaly_cols = [
            "ndvi_anomaly",
            "ndwi_anomaly",
            "s1_moisture_anomaly",
            "flood_extent_km2_anomaly",
        ]

        weather_effect_cols = [c for c in weather_effect_cols if c in df.columns]
        satellite_anomaly_cols = [c for c in satellite_anomaly_cols if c in df.columns]

        def plot_minmax(series):
            series = series.astype(float)
            min_val = series.min(skipna=True)
            max_val = series.max(skipna=True)
            if max_val == min_val:
                return series * 0.0
            return (series - min_val) / (max_val - min_val)

        weather_colors = ["tab:blue", "cornflowerblue", "deepskyblue", "steelblue", "navy"]
        satellite_colors = ["tab:green", "tab:orange", "tab:purple", "olive"]

        plt.figure(figsize=(14, 7))

        for idx, col in enumerate(weather_effect_cols):
            plt.plot(
                df["end_date"],
                plot_minmax(df[col]),
                label=f"Weather memory — {col.replace('_cumulative_effect', '')}",
                color=weather_colors[idx % len(weather_colors)],
                linewidth=2,
            )

        for idx, col in enumerate(satellite_anomaly_cols):
            plt.plot(
                df["end_date"],
                plot_minmax(df[col]),
                label=f"Satellite anomaly — {col.replace('_anomaly', '')}",
                color=satellite_colors[idx % len(satellite_colors)],
                linestyle="--",
                linewidth=2,
                alpha=0.95,
            )

        plt.axhline(0, color="black", linewidth=1, alpha=0.25)
        plt.axhline(1, color="black", linewidth=1, alpha=0.25)
        plt.title("Weather memory vs satellite anomalies — plot-scaled to 0–1")
        plt.xlabel("Date")
        plt.ylabel("Plot-only Min-Max scale")
        plt.grid(True, alpha=0.3)
        plt.legend(ncol=2)
        plt.tight_layout()

        if output_path:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            plt.savefig(output_path, dpi=160)
            if not show:
                plt.close()
            return output_path

        if show:
            plt.show()
        return None

    def add_satellite_past_future_delta_ratios(
        self,
        rows: list[dict] | None = None,
        csv_path: str | None = None,
        horizon_weeks: int = 8,
        interval_days: int | None = None,
        alpha: float = 0.35,
        eps: float = 1e-6,
    ):
        """
        Offline/post-event satellite temporal-asymmetry score.

        For every satellite-derived measure:
          1. Min-Max scale raw satellite signal.
          2. Compute absolute delta between observations.
          3. Compute exponentially weighted previous deltas up to current date.
          4. Compute exponentially weighted subsequent deltas after current date.
          5. Compute ratio:

                weighted_previous_abs_delta / (weighted_future_abs_delta + eps)

        Interpretation:
          ratio ≈ 1   normal / balanced dynamics
          ratio < 1   future response is larger than past response; possible precursor/build-up
          ratio > 1   past response is larger than future response; post-event relaxation/decay

        This intentionally uses future data, so it is for offline pattern discovery,
        validation and event-shape analysis, not real-time prediction.
        """
        try:
            import pandas as pd
            import numpy as np
        except ImportError as exc:
            raise ImportError("This method requires pandas and numpy.") from exc

        df = self._rows_to_dataframe(rows=rows, csv_path=csv_path).copy()

        interval_days = interval_days or self.interval_days
        horizon_steps = max(1, int(round((horizon_weeks * 7) / interval_days)))

        satellite_cols = [
            "ndvi",
            "ndwi",
            "s1_moisture",
            "s1_vv_db",
            "s1_vh_db",
            "flood_extent_km2",
        ]
        satellite_cols = [c for c in satellite_cols if c in df.columns]

        for col in satellite_cols:
            x = pd.to_numeric(df[col], errors="coerce")
            xmin = x.min(skipna=True)
            xmax = x.max(skipna=True)

            if pd.isna(xmin) or pd.isna(xmax) or xmax == xmin:
                df[f"{col}_offline_minmax"] = np.nan
                df[f"{col}_offline_delta"] = np.nan
                df[f"{col}_weighted_previous_abs_delta"] = np.nan
                df[f"{col}_weighted_future_abs_delta"] = np.nan
                df[f"{col}_past_future_delta_ratio"] = np.nan
                continue

            scaled = (x - xmin) / (xmax - xmin)
            delta = scaled.diff()
            abs_delta = delta.abs()

            previous_weighted = []
            future_weighted = []

            for i in range(len(df)):
                # Previous deltas, including the current delta at step 0.
                previous_vals = []
                previous_weights = []
                for step in range(0, horizon_steps + 1):
                    j = i - step
                    if j < 0:
                        break
                    val = abs_delta.iloc[j]
                    if pd.notna(val):
                        previous_vals.append(val)
                        previous_weights.append((1 - alpha) ** step)

                if previous_vals:
                    previous_weighted.append(float(np.average(previous_vals, weights=previous_weights)))
                else:
                    previous_weighted.append(np.nan)

                # Subsequent future deltas only, starting after current date.
                future_vals = []
                future_weights = []
                for step in range(1, horizon_steps + 1):
                    j = i + step
                    if j >= len(df):
                        break
                    val = abs_delta.iloc[j]
                    if pd.notna(val):
                        future_vals.append(val)
                        future_weights.append((1 - alpha) ** (step - 1))

                if future_vals:
                    future_weighted.append(float(np.average(future_vals, weights=future_weights)))
                else:
                    future_weighted.append(np.nan)

            previous_series = pd.Series(previous_weighted, index=df.index)
            future_series = pd.Series(future_weighted, index=df.index)

            df[f"{col}_offline_minmax"] = scaled
            df[f"{col}_offline_delta"] = delta
            df[f"{col}_weighted_previous_abs_delta"] = previous_series
            df[f"{col}_weighted_future_abs_delta"] = future_series
            df[f"{col}_past_future_delta_ratio"] = previous_series / (future_series + eps)

        ratio_cols = [f"{c}_past_future_delta_ratio" for c in satellite_cols]
        ratio_cols = [c for c in ratio_cols if c in df.columns]
        if ratio_cols:
            df["satellite_past_future_delta_ratio_max"] = df[ratio_cols].max(axis=1, skipna=True)
            df["satellite_past_future_delta_ratio_mean"] = df[ratio_cols].mean(axis=1, skipna=True)
            df["satellite_precursor_score"] = 1 / (df["satellite_past_future_delta_ratio_mean"] + eps)

        return df

    def plot_satellite_past_future_delta_ratios(
        self,
        rows: list[dict] | None = None,
        csv_path: str | None = None,
        output_path: str | None = None,
        horizon_weeks: int = 8,
        alpha: float = 0.35,
        precursor_threshold: float = 0.5,
        decay_threshold: float = 2.0,
        show: bool = False,
    ) -> str | None:
        """
        Plot offline previous/future weighted delta ratios for all satellite measures.

        ratio < 1 means future satellite change dominates past change.
        ratio > 1 means past satellite change dominates future change.
        """
        try:
            import matplotlib.pyplot as plt
        except ImportError as exc:
            raise ImportError("Plotting requires matplotlib. Install with: pip install matplotlib") from exc

        df = self.add_satellite_past_future_delta_ratios(
            rows=rows,
            csv_path=csv_path,
            horizon_weeks=horizon_weeks,
            alpha=alpha,
        )

        ratio_cols = [
            "ndvi_past_future_delta_ratio",
            "ndwi_past_future_delta_ratio",
            "s1_moisture_past_future_delta_ratio",
            "s1_vv_db_past_future_delta_ratio",
            "s1_vh_db_past_future_delta_ratio",
            "flood_extent_km2_past_future_delta_ratio",
        ]
        ratio_cols = [c for c in ratio_cols if c in df.columns]

        colors = ["tab:green", "tab:orange", "tab:purple", "olive", "brown", "tab:red"]

        plt.figure(figsize=(14, 7))

        for idx, col in enumerate(ratio_cols):
            plt.plot(
                df["end_date"],
                df[col],
                label=col.replace("_past_future_delta_ratio", ""),
                color=colors[idx % len(colors)],
                linewidth=2,
                alpha=0.85,
            )

        if "satellite_past_future_delta_ratio_mean" in df.columns:
            plt.plot(
                df["end_date"],
                df["satellite_past_future_delta_ratio_mean"],
                label="combined mean satellite ratio",
                color="black",
                linewidth=2.5,
                linestyle="--",
            )

        plt.axhline(1.0, color="gray", linewidth=1.5, alpha=0.8, linestyle=":", label="balanced ≈ 1")
        plt.axhline(precursor_threshold, color="orange", linewidth=1.5, alpha=0.8, linestyle=":", label=f"precursor zone < {precursor_threshold}")
        plt.axhline(decay_threshold, color="red", linewidth=1.5, alpha=0.8, linestyle=":", label=f"post-event decay > {decay_threshold}")

        plt.title(f"Satellite previous/future weighted delta ratios ({horizon_weeks}-week window)")
        plt.xlabel("Date")
        plt.ylabel("weighted previous abs(delta) / weighted future abs(delta)")
        plt.grid(True, alpha=0.3)
        plt.legend(ncol=2)
        plt.tight_layout()

        if output_path:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            plt.savefig(output_path, dpi=160)
            if not show:
                plt.close()
            return output_path

        if show:
            plt.show()
        return None

    # Backward-compatible alias for older calls.
    def add_satellite_future_delta_ratios(self, *args, **kwargs):
        return self.add_satellite_past_future_delta_ratios(*args, **kwargs)

    def plot_satellite_future_delta_ratios(self, *args, **kwargs):
        return self.plot_satellite_past_future_delta_ratios(*args, **kwargs)

    def plot_relationship_matrix(
        self,
        rows: list[dict] | None = None,
        csv_path: str | None = None,
        output_path: str | None = None,
        show: bool = False,
    ) -> str | None:
        """
        Scatter matrix for the most relevant variables.
        Uses pandas plotting so seaborn is not required.
        """
        try:
            import matplotlib.pyplot as plt
            from pandas.plotting import scatter_matrix
        except ImportError as exc:
            raise ImportError("Relationship plots require pandas and matplotlib.") from exc

        df = self._rows_to_dataframe(rows=rows, csv_path=csv_path)
        cols = [
            "soil_moisture_pct",
            "precip_mm_30d",
            "temp_max_c",
            "ndvi",
            "ndwi",
            "s1_moisture",
            "drought_index",
        ]
        cols = [c for c in cols if c in df.columns]

        axarr = scatter_matrix(df[cols].dropna(), figsize=(13, 13), diagonal="hist", alpha=0.7)
        for ax_row in axarr:
            for ax in ax_row:
                ax.grid(True, alpha=0.2)
        plt.suptitle("Relationship matrix: weather + satellite variables", y=1.02)
        plt.tight_layout()

        if output_path:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            plt.savefig(output_path, dpi=160, bbox_inches="tight")
            if not show:
                plt.close()
            return output_path

        if show:
            plt.show()
        return None

    def save_relevant_plots(
        self,
        rows: list[dict] | None = None,
        csv_path: str | None = None,
        output_dir: str = "plots",
    ) -> dict[str, str]:
        """
        Save a plot pack and return paths.

        Use either:
          save_relevant_plots(rows=rows, output_dir="backend/plots")
        or:
          save_relevant_plots(csv_path="backend/eo_weather_timeseries.csv", output_dir="backend/plots")
        """
        if rows is None and csv_path is None:
            raise ValueError("Provide either rows or csv_path.")

        os.makedirs(output_dir, exist_ok=True)
        return {
            "timeseries": self.plot_relevant_timeseries(
                rows=rows,
                csv_path=csv_path,
                output_path=os.path.join(output_dir, "01_weather_satellite_timeseries.png"),
            ),
            "anomaly_effects": self.plot_anomaly_effects(
                rows=rows,
                csv_path=csv_path,
                output_path=os.path.join(output_dir, "02_anomaly_effects.png"),
            ),
            "relationships": self.plot_relationship_matrix(
                rows=rows,
                csv_path=csv_path,
                output_path=os.path.join(output_dir, "03_relationship_matrix.png"),
            ),
            "satellite_past_future_delta_ratios": self.plot_satellite_past_future_delta_ratios(
                rows=rows,
                csv_path=csv_path,
                output_path=os.path.join(output_dir, "04_satellite_past_future_delta_ratios.png"),
            ),
        }

    # ──────────────────────────────────────────────────────────────────────
    # Supervised learning dataset
    # ──────────────────────────────────────────────────────────────────────

    def add_flood_drought_targets(
        self,
        rows: list[dict] | None = None,
        csv_path: str | None = None,
        horizon_weeks: int = 8,
        eps: float = 1e-6,
    ):
        """
        Build flood-specific and drought-specific target variables.

        The idea:
          physical event score = interpretable EO/weather ingredients
          dynamic modifier     = satellite temporal asymmetry signal

        Final targets:
          final_flood_score
          final_drought_score

        These are still proxy labels, not verified ground truth.
        They are useful for hackathon/self-supervised modeling.
        """
        try:
            import pandas as pd
            import numpy as np
        except ImportError as exc:
            raise ImportError("This method requires pandas and numpy.") from exc

        df = self.add_satellite_past_future_delta_ratios(
            rows=rows,
            csv_path=csv_path,
            horizon_weeks=horizon_weeks,
        ).copy()

        if "end_date" in df.columns:
            df["end_date"] = pd.to_datetime(df["end_date"])
            df = df.sort_values("end_date").reset_index(drop=True)

        def minmax_positive(series):
            x = pd.to_numeric(series, errors="coerce")
            xmin = x.min(skipna=True)
            xmax = x.max(skipna=True)

            if pd.isna(xmin) or pd.isna(xmax):
                return pd.Series(0.0, index=df.index)

            if xmax == xmin:
                return pd.Series(0.0, index=df.index)

            return (x - xmin) / (xmax - xmin + eps)

        def positive_anomaly(col):
            if col not in df.columns:
                return pd.Series(np.nan, index=df.index)
            return minmax_positive(pd.to_numeric(df[col], errors="coerce").clip(lower=0))

        def negative_anomaly(col):
            if col not in df.columns:
                return pd.Series(np.nan, index=df.index)
            return minmax_positive((-pd.to_numeric(df[col], errors="coerce")).clip(lower=0))

        # ── Flood ingredients ─────────────────────────────────────────────
        # Flood-like = water expansion + wet radar response + rainfall + surface-water proxy.
        flood_ndwi = positive_anomaly("ndwi_anomaly")
        flood_s1 = positive_anomaly("s1_moisture_anomaly")
        flood_precip_7d = positive_anomaly("precip_mm_7d_anomaly")
        flood_precip_30d = positive_anomaly("precip_mm_30d_anomaly")
        flood_extent = positive_anomaly("flood_extent_km2_anomaly")

        df["flood_physical_score"] = (
            0.30 * flood_ndwi
            + 0.25 * flood_s1
            + 0.20 * flood_precip_7d
            + 0.15 * flood_precip_30d
            + 0.10 * flood_extent
        )

        # ── Drought ingredients ───────────────────────────────────────────
        # Drought-like = vegetation drop + soil moisture deficit + rain deficit + heat stress.
        drought_ndvi_drop = negative_anomaly("ndvi_anomaly")
        drought_soil_drop = negative_anomaly("soil_moisture_pct_anomaly")
        drought_precip_30d_deficit = negative_anomaly("precip_mm_30d_anomaly")
        drought_precip_7d_deficit = negative_anomaly("precip_mm_7d_anomaly")
        drought_heat = positive_anomaly("temp_max_c_anomaly")

        df["drought_physical_score"] = (
            0.30 * drought_ndvi_drop
            + 0.25 * drought_soil_drop
            + 0.20 * drought_precip_30d_deficit
            + 0.10 * drought_precip_7d_deficit
            + 0.15 * drought_heat
        )

        # ── Dynamic modifier from satellite temporal asymmetry ─────────────
        # ratio < 1 means future satellite movement dominates past movement.
        # Convert it to a build-up/instability score: high when ratio is low.
        ratio = pd.to_numeric(df.get("satellite_past_future_delta_ratio_mean"), errors="coerce")
        df["satellite_asymmetry_buildup"] = 1.0 / (ratio + eps)
        df["satellite_asymmetry_buildup_norm"] = minmax_positive(df["satellite_asymmetry_buildup"])

        # Final flood/drought targets.
        df["final_flood_score"] = df["flood_physical_score"] * (1.0 + df["satellite_asymmetry_buildup_norm"])
        df["final_drought_score"] = df["drought_physical_score"] * (1.0 + df["satellite_asymmetry_buildup_norm"])

        # Stable log versions for XGBoost/regression.
        df["final_flood_score_log"] = np.log1p(df["final_flood_score"])
        df["final_drought_score_log"] = np.log1p(df["final_drought_score"])

        # Optional event flags using adaptive high-percentile thresholds.
        flood_threshold = df["final_flood_score"].quantile(0.90)
        drought_threshold = df["final_drought_score"].quantile(0.90)
        df["flood_event_proxy"] = (df["final_flood_score"] >= flood_threshold).astype(int)
        df["drought_event_proxy"] = (df["final_drought_score"] >= drought_threshold).astype(int)

        return df

    def build_supervised_disaster_dataset(
        self,
        rows: list[dict] | None = None,
        csv_path: str | None = None,
        horizon_weeks: int = 8,
        feature_lag_steps: int = 1,
        target_kind: str = "both",
        dropna_target: bool = True,
    ):
        """
        Build the hackathon/prototype ML table.

        Targets at time t:
          final_flood_score
          final_drought_score

        Features:
          all available numeric observations from feature_lag_steps before t.

        With 14-day intervals and feature_lag_steps=1:
          target at t is paired with observations from t - 2 weeks.

        target_kind:
          "both"    -> flood and drought targets
          "flood"   -> flood target only
          "drought" -> drought target only
        """
        try:
            import pandas as pd
        except ImportError as exc:
            raise ImportError("This method requires pandas.") from exc

        df = self.add_flood_drought_targets(
            rows=rows,
            csv_path=csv_path,
            horizon_weeks=horizon_weeks,
        ).copy()

        if "end_date" in df.columns:
            df["end_date"] = pd.to_datetime(df["end_date"])
            df = df.sort_values("end_date").reset_index(drop=True)

        target_map = {
            "flood": ["final_flood_score", "final_flood_score_log", "flood_event_proxy"],
            "drought": ["final_drought_score", "final_drought_score_log", "drought_event_proxy"],
            "both": [
                "final_flood_score",
                "final_flood_score_log",
                "flood_event_proxy",
                "final_drought_score",
                "final_drought_score_log",
                "drought_event_proxy",
            ],
        }
        if target_kind not in target_map:
            raise ValueError("target_kind must be one of: 'both', 'flood', 'drought'")

        target_cols = target_map[target_kind]

        excluded_cols = {
            "start_date",
            "end_date",
            "data_timestamp",
            "source",
            *target_map["both"],
            "flood_physical_score",
            "drought_physical_score",
            "satellite_asymmetry_buildup",
            "satellite_asymmetry_buildup_norm",
        }

        # Avoid leakage: these columns are computed using future information.
        leakage_tokens = [
            "future",
            "past_future",
            "precursor_score",
            "weighted_previous_abs_delta",
            "weighted_future_abs_delta",
            "offline_delta",
            "offline_minmax",
        ]

        candidate_features = []
        for col in df.columns:
            if col in excluded_cols:
                continue
            if any(token in col for token in leakage_tokens):
                continue
            if pd.api.types.is_numeric_dtype(df[col]):
                candidate_features.append(col)

        supervised = pd.DataFrame()
        supervised["target_date"] = df["end_date"]
        supervised["feature_date"] = df["end_date"].shift(feature_lag_steps)

        for target_col in target_cols:
            supervised[target_col] = df[target_col]

        for col in candidate_features:
            supervised[f"feature_t_minus_{feature_lag_steps}_{col}"] = df[col].shift(feature_lag_steps)

        if dropna_target:
            supervised = supervised.dropna(subset=target_cols, how="all")

        supervised = supervised.dropna(subset=["feature_date"])

        return supervised

    def save_supervised_disaster_dataset(
        self,
        rows: list[dict] | None = None,
        csv_path: str | None = None,
        output_path: str = "supervised_disaster_dataset.csv",
        horizon_weeks: int = 8,
        feature_lag_steps: int = 1,
    ) -> str:
        """
        Save the supervised dataset to CSV.
        """
        df = self.build_supervised_disaster_dataset(
            rows=rows,
            csv_path=csv_path,
            horizon_weeks=horizon_weeks,
            feature_lag_steps=feature_lag_steps,
        )
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        df.to_csv(output_path, index=False)
        return output_path


# ─────────────────────────────────────────────────────────────────────────────
# Backward-compatible module-level wrappers
# ─────────────────────────────────────────────────────────────────────────────

def _get_sh_token() -> str:
    return Sentinel_Extractor().get_sh_token()


def _sh_statistics(
    token: str,
    bbox: list,
    evalscript: str,
    dataset: str = "sentinel-2-l2a",
    days_back: int = 14,
    max_cloud_pct: int = 30,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> dict | None:
    return Sentinel_Extractor().sh_statistics(
        token=token,
        bbox=bbox,
        evalscript=evalscript,
        dataset=dataset,
        days_back=days_back,
        max_cloud_pct=max_cloud_pct,
        start_date=start_date,
        end_date=end_date,
    )


def _extract_mean_from_stats(sh_response: dict | None, output_band: str = "B0") -> float | None:
    return Sentinel_Extractor.extract_mean_from_stats(sh_response, output_band)


def _fetch_openmeteo(lat: float, lon: float, date: str | None = None) -> dict:
    return Sentinel_Extractor().fetch_openmeteo(lat, lon, date)


def _fetch_river_discharge(lat: float, lon: float, start_date: str, end_date: str) -> dict:
    return Sentinel_Extractor().fetch_river_discharge(lat, lon, start_date, end_date)


def get_eo_and_weather_data(bbox: list) -> dict:
    """
    Public API imported by lambda_handler.py.
    Signature and core return schema are preserved.
    """
    return Sentinel_Extractor().get_eo_and_weather_data(bbox)


if __name__ == "__main__":
    """
    One-command local pipeline.

    Run from project root:
        python backend/sentinel_extractor.py

    Outputs:
        data/processed/eo_weather_timeseries.csv
        data/ml/supervised_disaster_dataset.csv
        data/plots/*.png

    Design:
        - Sentinel Hub requests are split by year to avoid server disconnects.
        - Resolution is intentionally coarse enough for stable hackathon iteration.
        - Time-series data and ML data are stored separately.
    """

    PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    DATA_DIR = os.path.join(PROJECT_ROOT, "data")
    PROCESSED_DIR = os.path.join(DATA_DIR, "processed")
    ML_DIR = os.path.join(DATA_DIR, "ml")
    PLOTS_DIR = os.path.join(DATA_DIR, "plots")

    os.makedirs(PROCESSED_DIR, exist_ok=True)
    os.makedirs(ML_DIR, exist_ok=True)
    os.makedirs(PLOTS_DIR, exist_ok=True)

    time_series_csv = os.path.join(PROCESSED_DIR, "eo_weather_timeseries.csv")
    supervised_csv = os.path.join(ML_DIR, "supervised_disaster_dataset.csv")

    # Safer defaults after RemoteDisconnected errors.
    # 0.005° ≈ 400–550 m around Pleven.
    # 30-day intervals drastically reduce payload size while preserving usable temporal dynamics.
    YEARS_BACK_MAIN = 5
    INTERVAL_DAYS_MAIN = 30
    RESOLUTION_DEGREES_MAIN = 0.005

    extractor = Sentinel_Extractor(
        interval_days=INTERVAL_DAYS_MAIN,
        resolution_degrees=RESOLUTION_DEGREES_MAIN,
        timeout=180,
    )

    print("───────────────────────────────────────────────────────")
    print("STEP 1 — Build EO/weather time series")
    print("───────────────────────────────────────────────────────")
    print(f"BBOX: {PLEVEN_SMALL_BBOX}")
    print(f"Years back: {YEARS_BACK_MAIN}")
    print(f"Interval days: {INTERVAL_DAYS_MAIN}")
    print(f"Resolution degrees: {RESOLUTION_DEGREES_MAIN}")
    print("Chunking: yearly Sentinel Hub requests")

    try:
        rows = extractor.get_time_series(
            bbox=PLEVEN_SMALL_BBOX,
            years_back=YEARS_BACK_MAIN,
            include_river_discharge=False,
            add_signals=True,
        )
    except Exception as exc:
        print(f"Pipeline failed while building time series: {exc}")
        sys.exit(1)

    if not rows:
        print("No rows returned. Sentinel Hub requests failed or returned empty data.")
        print("Try one of these:")
        print("  - YEARS_BACK_MAIN = 1")
        print("  - INTERVAL_DAYS_MAIN = 60")
        print("  - RESOLUTION_DEGREES_MAIN = 0.01")
        sys.exit(1)

    extractor.save_time_series_csv(rows, time_series_csv)
    print(f"✓ Saved processed time series: {time_series_csv}")
    print(f"  Rows: {len(rows)}")

    print("───────────────────────────────────────────────────────")
    print("STEP 2 — Build supervised flood/drought ML dataset")
    print("───────────────────────────────────────────────────────")
    print("Targets at time t:")
    print("  - final_flood_score / final_flood_score_log")
    print("  - final_drought_score / final_drought_score_log")
    print("Features:")
    print("  - all numeric observations from t - 1 interval")

    try:
        extractor.save_supervised_disaster_dataset(
            csv_path=time_series_csv,
            output_path=supervised_csv,
            horizon_weeks=8,
            feature_lag_steps=1,
        )
    except Exception as exc:
        print(f"Failed to build supervised dataset: {exc}")
        sys.exit(1)

    print(f"✓ Saved supervised ML dataset: {supervised_csv}")

    print("───────────────────────────────────────────────────────")
    print("STEP 3 — Save relevant plots")
    print("───────────────────────────────────────────────────────")

    try:
        plot_paths = extractor.save_relevant_plots(
            csv_path=time_series_csv,
            output_dir=PLOTS_DIR,
        )
        for name, path in plot_paths.items():
            print(f"✓ {name}: {path}")
    except Exception as exc:
        print(f"Plot generation failed: {exc}")
        print("Data files were still created if previous steps succeeded.")

    print("───────────────────────────────────────────────────────")
    print("DONE")
    print("───────────────────────────────────────────────────────")
    print(f"Processed data: {time_series_csv}")
    print(f"ML dataset    : {supervised_csv}")
    print(f"Plots         : {PLOTS_DIR}")
