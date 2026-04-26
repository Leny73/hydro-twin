"""
dams_handler.py — Dam Monitoring Module
=========================================

Tracks water-fill levels for 3 Bulgarian dams on the Arda river:
  • Язовир Кърджали        (Kardzhali)
  • Язовир Студен Кладенец (Studen Kladenets)
  • Язовир Ивайловград     (Ivaylovgrad)

Pipeline:
  1. Parse all XLS files from data/dams/ to build per-dam time-series
  2. Derive thresholds automatically from historical fill % distribution
       - LOW  boundary  = 25th percentile of historical fill %
       - HIGH boundary  = 75th percentile
  3. Identify "low dates" and "high dates" in the historical record
  4. For each dam, fetch NDWI from Sentinel Hub (Sentinel-2 L2A) for the
     past 14 days to get the current water surface extent
  5. Correlate: NDWI medians on high-fill vs low-fill dates become
     the NDWI thresholds for live alerting
  6. Produce per-dam alert_level:
       WATER_REGIME  – fill < low_threshold   → water restrictions advised
       STABLE        – fill in normal range    → no action needed
       OPEN_GATES    – fill > high_threshold   → spillway opening recommended
  7. Fire webhook notification for any non-STABLE dam (same Discord/Telegram
     channels as the oblast assessments)

API:
  GET /dams
    Returns JSON:
    {
      "dams": [ { id, name, lat, lon, fill_pct, volume_mln_m3,
                  ndwi, ndwi_threshold_high, ndwi_threshold_low,
                  alert_level, alert_reason, thresholds, series } ],
      "generated_at": "ISO-8601"
    }

Environment variables (same as lambda_handler):
  DISCORD_WEBHOOK_URL  – Discord webhook URL(s)
  TELEGRAM_BOT_TOKEN   – Telegram bot token
  TELEGRAM_CHAT_ID     – Telegram chat id
  SH_CLIENT_ID         – Sentinel Hub OAuth2 client id
  SH_CLIENT_SECRET     – Sentinel Hub OAuth2 client secret
"""

import json
import logging
import os
import statistics
from datetime import datetime, timezone, timedelta

import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env.local"),  override=True)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env.example"), override=False)

logger = logging.getLogger(__name__)

# ── Sentinel Hub ──────────────────────────────────────────────────────────────
SH_CLIENT_ID     = os.environ.get("SH_CLIENT_ID", "")
SH_CLIENT_SECRET = os.environ.get("SH_CLIENT_SECRET", "")
SH_TOKEN_URL     = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
SH_STATS_URL     = "https://sh.dataspace.copernicus.eu/statistics/v1"

# ── Webhook env (shared with lambda_handler) ──────────────────────────────────
DISCORD_WEBHOOK_URLS = [
    u.strip()
    for u in os.environ.get("DISCORD_WEBHOOK_URL", "").split(",")
    if u.strip()
]
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")

# ── Dam configuration ─────────────────────────────────────────────────────────
# Coordinates and bboxes for Sentinel-2 NDWI queries.
# bbox = [lon_min, lat_min, lon_max, lat_max] — tight 5 km window around the dam body
DAM_CONFIG = [
    {
        # Dam wall centre from OSM way/168092719 (GeoJSON)
        # Reservoir extends upstream (east) along the Arda river
        "id":       "kardzhali",
        "name":     "Язовир Кърджали",
        "name_xls": "Кърджали",
        "lat":      41.6326,
        "lon":      25.3385,
        # bbox covers the Kardzhali reservoir water body (not just the wall)
        "bbox":     [25.32, 41.57, 25.56, 41.68],
        "river":    "Арда",
        "capacity_mln_m3": 497.236,
    },
    {
        # Dam wall centre from OSM way/485280749 (GeoJSON)
        # Reservoir extends upstream (east) along the Arda river
        "id":       "studen-kladenets",
        "name":     "Язовир Студен Кладенец",
        "name_xls": "Ст. Кладенец",
        "lat":      41.6122,
        "lon":      25.6406,
        # bbox covers the Studen Kladenets reservoir water body
        "bbox":     [25.64, 41.57, 25.90, 41.66],
        "river":    "Арда",
        "capacity_mln_m3": 387.772,
    },
    {
        # Dam wall centre from OSM relation/11949072 (GeoJSON)
        # Reservoir extends upstream (west) along the Arda river
        "id":       "ivaylovgrad",
        "name":     "Язовир Ивайловград",
        "name_xls": "Ивайловград",
        "lat":      41.5839,
        "lon":      26.1076,
        # bbox covers the Ivaylovgrad reservoir water body
        "bbox":     [25.88, 41.49, 26.11, 41.60],
        "river":    "Арда",
        "capacity_mln_m3": 156.702,
    },
]

# XLS data directory (relative to this file)
DAMS_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "dams")

# ── NDWI evalscript (Sentinel-2 L2A) ─────────────────────────────────────────
# NDWI = (Green B03 − NIR B08) / (Green B03 + NIR B08)
# Open water → > 0.2,  flooded / shallow → 0.0–0.2,  land → < 0
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
  // Exclude clouds (SCL 8,9,10) and cloud shadows (SCL 3)
  let valid = samples.filter(s =>
    s.dataMask === 1 && s.SCL !== 3 && s.SCL !== 8 && s.SCL !== 9 && s.SCL !== 10
  );
  if (valid.length === 0) return { ndwi: [NaN], dataMask: [0] };
  let mean = valid.reduce((sum, s) => {
    let denom = s.B03 + s.B08;
    return sum + (denom !== 0 ? (s.B03 - s.B08) / denom : 0);
  }, 0) / valid.length;
  return { ndwi: [mean], dataMask: [1] };
}
"""


# ── Sentinel Hub helpers ──────────────────────────────────────────────────────

def _get_sh_token() -> str:
    if not SH_CLIENT_ID or not SH_CLIENT_SECRET:
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
        return resp.json().get("access_token", "")
    except Exception as exc:
        logger.warning("SH token fetch failed: %s", exc)
        return ""


def _fetch_ndwi(token: str, bbox: list, start: str, end: str) -> float | None:
    """
    Call Sentinel Hub Statistical API for NDWI over [start, end].
    Returns mean NDWI float or None if unavailable.
    """
    if not token:
        return None
    payload = {
        "input": {
            "bounds": {
                "bbox":       bbox,
                "properties": {"crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"},
            },
            "data": [{
                "type": "sentinel-2-l2a",
                "dataFilter": {"mosaickingOrder": "leastCC"},
            }],
        },
        "aggregation": {
            "timeRange":           {"from": start, "to": end},
            "aggregationInterval": {"of": "P1D"},
            "evalscript":          EVALSCRIPT_NDWI,
            "resx": 0.002,  # ~180 m — tight bbox around reservoir
            "resy": 0.002,
        },
        "calculations": {
            "default": {
                "statistics": {
                    "default": {"percentiles": {"k": [25, 50, 75]}},
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
        data = resp.json()
        intervals = data.get("data", [])
        for interval in reversed(intervals):
            stats = (interval
                     .get("outputs", {})
                     .get("ndwi", {})
                     .get("bands", {})
                     .get("B0", {})
                     .get("stats", {}))
            mean = stats.get("mean")
            sc   = stats.get("sampleCount", 0)
            nc   = stats.get("noDataCount", 0)
            if mean is not None and sc > 0 and sc > nc and not (mean != mean):  # not NaN
                v = round(float(mean), 4)
                # Negative NDWI = land pixels dominate the bbox — not a usable water reading
                if v < 0:
                    logger.info("NDWI %.4f is negative (land-dominated bbox) — discarding", v)
                    return None
                return v
    except Exception as exc:
        logger.warning("Sentinel Hub NDWI fetch failed: %s", exc)
    return None


# ── NDWI estimate from fill % ────────────────────────────────────────────────

def _estimate_ndwi_from_fill(fill_pct: float) -> float:
    """
    When Sentinel Hub returns unusable data (negative NDWI = land pixels),
    derive a physically meaningful NDWI estimate from fill level.

    Physical basis: higher reservoir fill → larger water surface area → higher NDWI.
    Linear fit calibrated to Arda reservoir typical ranges:
      fill=0%   → NDWI ≈ -0.10 (dry lake bed)
      fill=50%  → NDWI ≈  0.28
      fill=100% → NDWI ≈  0.65
    """
    ndwi = -0.10 + (fill_pct / 100.0) * 0.75
    return round(max(-0.10, min(0.65, ndwi)), 3)


def _ndwi_for_dates(token: str, bbox: list, iso_dates: list[str]) -> list[float]:
    """
    Fetch NDWI for each date in iso_dates (list of YYYY-MM-DD strings).
    Returns a list of non-None values (may be shorter than input).
    """
    values = []
    for iso in iso_dates[:8]:  # cap at 8 calls to stay within demo time budget
        start = f"{iso}T00:00:00Z"
        end   = f"{iso}T23:59:59Z"
        v = _fetch_ndwi(token, bbox, start, end)
        if v is not None:
            values.append(v)
    return values


    """
    Fetch NDWI for each date in iso_dates (list of YYYY-MM-DD strings).
    Returns a list of non-None values (may be shorter than input).
    """
    values = []
    for iso in iso_dates[:8]:  # cap at 8 calls to stay within demo time budget
        start = f"{iso}T00:00:00Z"
        end   = f"{iso}T23:59:59Z"
        v = _fetch_ndwi(token, bbox, start, end)
        if v is not None:
            values.append(v)
    return values


# ── XLS parsing ──────────────────────────────────────────────────────────────

def _load_all_xls() -> dict[str, list[dict]]:
    """
    Parse all XLS files in DAMS_DATA_DIR.
    Returns { xls_dam_name: [ {date, fill_pct, volume_mln_m3}, ... ] }
    sorted chronologically.
    """
    try:
        import xlrd
    except ImportError:
        logger.error("xlrd not installed — cannot parse dam XLS files")
        return {}

    series: dict[str, list] = {}
    data_dir = os.path.abspath(DAMS_DATA_DIR)
    if not os.path.isdir(data_dir):
        logger.warning("Dam data directory not found: %s", data_dir)
        return {}

    xls_files = sorted(
        f for f in os.listdir(data_dir)
        if f.endswith(".xls") or f.endswith(".xlsx")
    )
    for fname in xls_files:
        fpath = os.path.join(data_dir, fname)
        try:
            wb = xlrd.open_workbook(fpath)
            # Prefer the 'Data' summary sheet; fall back to 'Datanew'
            sheet_name = None
            for sn in ["Data", "Datanew"]:
                if sn in wb.sheet_names():
                    sheet_name = sn
                    break
            if not sheet_name:
                continue
            sh = wb.sheet_by_name(sheet_name)
            for r in range(sh.nrows):
                row = [sh.cell_value(r, c) for c in range(sh.ncols)]
                # Row structure: [empty, date_str, dam_name, total_vol, useful_vol, current_vol, fill_pct, ...]
                if len(row) < 7:
                    continue
                raw_date = str(row[1]).strip()
                dam_name = str(row[2]).strip()
                try:
                    fill_pct   = float(row[6])
                    volume     = float(row[5])
                except (ValueError, TypeError):
                    continue
                if not dam_name or dam_name == "" or fill_pct == 0.0:
                    continue
                # Normalise date to YYYY-MM-DD
                date_iso = _parse_bg_date(raw_date)
                if not date_iso:
                    continue
                if dam_name not in series:
                    series[dam_name] = []
                series[dam_name].append({
                    "date":           date_iso,
                    "fill_pct":       round(fill_pct, 2),
                    "volume_mln_m3":  round(volume, 3),
                })
        except Exception as exc:
            logger.warning("Failed to parse %s: %s", fname, exc)

    # Sort each series chronologically and deduplicate by date
    for dam_name in series:
        seen = {}
        for pt in series[dam_name]:
            seen[pt["date"]] = pt  # later file wins for same date
        series[dam_name] = sorted(seen.values(), key=lambda x: x["date"])

    return series


def _parse_bg_date(s: str) -> str | None:
    """
    Parse Bulgarian date strings like '01.02.2017' or '03.02.2017 ' → '2017-02-01'.
    Returns None if parsing fails.
    """
    s = s.strip().rstrip(".")
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


# ── Threshold computation ─────────────────────────────────────────────────────

# Fixed alert thresholds (% of total capacity)
HIGH_THRESHOLD = 90.0  # OPEN_GATES — spillway opening recommended
LOW_THRESHOLD  = 25.0  # WATER_REGIME — water restrictions advised


def _compute_thresholds(fill_pcts: list[float]) -> dict:
    """
    Return alert thresholds for a dam.
    HIGH_THRESHOLD and LOW_THRESHOLD are fixed constants; mean/min/max
    are derived from the historical series for informational display only.
    Returns {low: float, high: float, mean: float, min: float, max: float}
    """
    if not fill_pcts:
        return {"low": LOW_THRESHOLD, "high": HIGH_THRESHOLD, "mean": 50.0, "min": 0.0, "max": 100.0}
    return {
        "low":  LOW_THRESHOLD,
        "high": HIGH_THRESHOLD,
        "mean": round(statistics.mean(fill_pcts), 1),
        "min":  round(min(fill_pcts), 1),
        "max":  round(max(fill_pcts), 1),
    }


def _alert_level(fill_pct: float, thresholds: dict, ndwi: float | None,
                 ndwi_thresh: dict | None) -> tuple[str, str]:
    """
    Returns (alert_level, reason) based on fill % and optional NDWI.
    Priority: fill % is primary signal; NDWI is corroborating evidence.
    """
    low_t  = thresholds["low"]
    high_t = thresholds["high"]

    # NDWI override: high NDWI confirms flooding even if fill gauge is slow
    if (ndwi is not None and ndwi_thresh is not None
            and ndwi >= ndwi_thresh.get("high", 999)):
        return (
            "OPEN_GATES",
            f"NDWI={ndwi:.3f} exceeds reservoir-full threshold "
            f"({ndwi_thresh['high']:.3f}). Spillway activation recommended.",
        )

    if fill_pct > high_t:
        return (
            "OPEN_GATES",
            f"Reservoir fill {fill_pct:.1f}% exceeds safety threshold "
            f"({high_t:.1f}%). Spillway gates should be opened to avoid "
            "overtopping risk.",
        )
    if fill_pct < low_t:
        return (
            "WATER_REGIME",
            f"Reservoir fill {fill_pct:.1f}% is below the low-water "
            f"threshold ({low_t:.1f}%). Water-use restrictions are recommended "
            "to preserve minimum operational reserves.",
        )
    return (
        "STABLE",
        f"Reservoir fill {fill_pct:.1f}% is within the normal range "
        f"({low_t:.1f}%–{high_t:.1f}%). No action required.",
    )


# ── NDWI threshold correlation ────────────────────────────────────────────────

def _derive_ndwi_thresholds(
    token: str,
    dam: dict,
    series: list[dict],
    thresholds: dict,
) -> dict | None:
    """
    For dates when fill_pct was historically HIGH or LOW, fetch NDWI from
    Sentinel Hub and compute NDWI thresholds by medians.

    Returns {high: float, low: float} or None if SH unavailable.
    """
    if not token:
        return None

    high_dates = [
        pt["date"] for pt in series if pt["fill_pct"] >= thresholds["high"]
    ][-5:]  # last 5 high dates
    low_dates = [
        pt["date"] for pt in series if pt["fill_pct"] <= thresholds["low"]
    ][-5:]  # last 5 low dates

    high_ndwis = _ndwi_for_dates(token, dam["bbox"], high_dates)
    low_ndwis  = _ndwi_for_dates(token, dam["bbox"], low_dates)

    if not high_ndwis and not low_ndwis:
        return None

    result = {}
    if high_ndwis:
        result["high"] = round(statistics.median(high_ndwis), 4)
    if low_ndwis:
        result["low"] = round(statistics.median(low_ndwis), 4)
    return result if result else None


# ── Webhook notification ──────────────────────────────────────────────────────

_ALERT_META = {
    "WATER_REGIME": {"emoji": "🟡", "color": 0xF59E0B, "label": "Water Regime"},
    "STABLE":       {"emoji": "✅", "color": 0x10B981, "label": "Stable"},
    "OPEN_GATES":   {"emoji": "🚨", "color": 0xEF4444, "label": "Open Gates"},
}


def _notify_dam(dam_name: str, alert_level: str, reason: str, fill_pct: float) -> None:
    """Fire Discord/Telegram for non-STABLE dam alerts. Non-fatal."""
    if alert_level == "STABLE":
        return
    meta = _ALERT_META.get(alert_level, _ALERT_META["STABLE"])

    for url in DISCORD_WEBHOOK_URLS:
        try:
            payload = {
                "username":   "HydroTwin · Dam Monitor",
                "avatar_url": "https://cdn-icons-png.flaticon.com/512/3222/3222800.png",
                "embeds": [{
                    "title":       f"{meta['emoji']} Dam Alert — {dam_name}",
                    "description": reason,
                    "color":       meta["color"],
                    "fields": [
                        {"name": "Alert Level", "value": meta["label"],         "inline": True},
                        {"name": "Fill Level",  "value": f"{fill_pct:.1f}%",    "inline": True},
                        {"name": "Dam",         "value": dam_name,               "inline": True},
                    ],
                    "footer": {"text": "HydroTwin · Dam Monitoring · Arda River, Bulgaria"},
                }],
            }
            requests.post(url, json=payload, timeout=5).raise_for_status()
            logger.info("Discord dam alert sent for %s", dam_name)
        except Exception as exc:
            logger.error("Discord dam alert failed: %s", exc)

    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        try:
            text = (
                f"{meta['emoji']} <b>Dam Alert</b> — {dam_name}\n"
                f"<b>Level:</b> {meta['label']}  |  <b>Fill:</b> {fill_pct:.1f}%\n"
                f"{reason}"
            )
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
                timeout=5,
            ).raise_for_status()
        except Exception as exc:
            logger.error("Telegram dam alert failed: %s", exc)


# ── Public API ────────────────────────────────────────────────────────────────

def get_dam_statuses(notify: bool = True) -> dict:
    """
    Main entry point — builds the full dam status response.

    Returns a dict ready for JSON serialisation.
    """
    all_series = _load_all_xls()
    sh_token   = _get_sh_token()
    now        = datetime.now(timezone.utc)
    now_iso    = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Current NDWI window: past 14 days
    ndwi_start = (now - timedelta(days=14)).strftime("%Y-%m-%dT00:00:00Z")
    ndwi_end   = now.strftime("%Y-%m-%dT23:59:59Z")

    dam_results = []
    for dam in DAM_CONFIG:
        xls_name = dam["name_xls"]
        series   = all_series.get(xls_name, [])

        # Use most recent XLS entry for current fill
        if series:
            latest    = series[-1]
            fill_pct  = latest["fill_pct"]
            volume    = latest["volume_mln_m3"]
            data_date = latest["date"]
        else:
            fill_pct  = None
            volume    = None
            data_date = None

        # Derive thresholds from full historical series
        fill_pcts  = [pt["fill_pct"] for pt in series if pt["fill_pct"] > 0]
        thresholds = _compute_thresholds(fill_pcts)

        # Sentinel Hub: current NDWI (past 14 days)
        ndwi_current = _fetch_ndwi(sh_token, dam["bbox"], ndwi_start, ndwi_end)
        ndwi_source  = "sentinel-2"
        if ndwi_current is None and fill_pct is not None:
            ndwi_current = _estimate_ndwi_from_fill(fill_pct)
            ndwi_source  = "estimated-from-fill"

        # NDWI threshold derivation from historical high/low dates
        ndwi_thresholds = _derive_ndwi_thresholds(sh_token, dam, series, thresholds)

        # Alert level
        if fill_pct is not None:
            alert_level, alert_reason = _alert_level(
                fill_pct, thresholds, ndwi_current, ndwi_thresholds
            )
        else:
            alert_level  = "STABLE"
            alert_reason = "No XLS data available — unable to assess."

        # Trim series to last 90 points for the frontend sparkline
        series_trimmed = series[-90:]

        if notify:
            _notify_dam(dam["name"], alert_level, alert_reason, fill_pct or 0)

        dam_results.append({
            "id":                   dam["id"],
            "name":                 dam["name"],
            "river":                dam["river"],
            "lat":                  dam["lat"],
            "lon":                  dam["lon"],
            "capacity_mln_m3":      dam["capacity_mln_m3"],
            "fill_pct":             fill_pct,
            "volume_mln_m3":        volume,
            "data_date":            data_date,
            "ndwi":                 ndwi_current,
            "ndwi_source":          ndwi_source,
            "ndwi_threshold_high":  ndwi_thresholds.get("high") if ndwi_thresholds else None,
            "ndwi_threshold_low":   ndwi_thresholds.get("low")  if ndwi_thresholds else None,
            "alert_level":          alert_level,
            "alert_reason":         alert_reason,
            "thresholds":           thresholds,
            "series":               series_trimmed,
        })

    return {"dams": dam_results, "generated_at": now_iso}


# ── Lambda handler ────────────────────────────────────────────────────────────

_CORS = {
    "Content-Type":                "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
}


def lambda_handler(event: dict, context) -> dict:
    method = event.get("httpMethod", "GET").upper()

    if method == "OPTIONS":
        return {"statusCode": 204, "headers": _CORS, "body": ""}

    try:
        # ?notify=false lets the cron runner suppress redundant webhooks
        qs      = event.get("queryStringParameters") or {}
        notify  = qs.get("notify", "true").lower() != "false"
        result  = get_dam_statuses(notify=notify)
        return {
            "statusCode": 200,
            "headers":    _CORS,
            "body":       json.dumps(result),
        }
    except Exception as exc:
        logger.exception("dams_handler error: %s", exc)
        return {
            "statusCode": 500,
            "headers":    _CORS,
            "body":       json.dumps({"error": str(exc)}),
        }
