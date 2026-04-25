"""
Quick integration test for Sentinel Hub credentials.
Run from WSL: python3 backend/test_sentinel.py

Tests:
  1. OAuth2 token fetch
  2. NDVI statistics request for Pleven Oblast bbox
  3. NDWI statistics request for Pleven Oblast bbox
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env.local"))

SH_CLIENT_ID     = os.environ["SH_CLIENT_ID"]
SH_CLIENT_SECRET = os.environ["SH_CLIENT_SECRET"]
TOKEN_URL        = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
STATS_URL        = "https://sh.dataspace.copernicus.eu/statistics/v1"

# Pleven Oblast bbox: [lon_min, lat_min, lon_max, lat_max]
PLEVEN_BBOX = [23.90, 43.15, 25.20, 43.70]

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

def separator(title):
    print(f"\n{'─'*55}")
    print(f"  {title}")
    print(f"{'─'*55}")

# ── Step 1: Fetch token ───────────────────────────────────────
separator("STEP 1 — OAuth2 token")
print(f"Client ID : {SH_CLIENT_ID}")
print(f"Token URL : {TOKEN_URL}")

resp = requests.post(
    TOKEN_URL,
    data={
        "grant_type":    "client_credentials",
        "client_id":     SH_CLIENT_ID,
        "client_secret": SH_CLIENT_SECRET,
    },
    timeout=15,
)
print(f"HTTP status: {resp.status_code}")

if resp.status_code != 200:
    print("FAILED:", resp.text)
    sys.exit(1)

token_data = resp.json()
token = token_data["access_token"]
expires_in = token_data.get("expires_in", "?")
print(f"✓ Token received  (expires in {expires_in}s)")
print(f"  Token preview: {token[:40]}...")

# ── Step 2: NDVI statistics ───────────────────────────────────
separator("STEP 2 — NDVI Statistical API request")

now   = datetime.now(timezone.utc)
start = (now - timedelta(days=14)).strftime("%Y-%m-%dT00:00:00Z")
end   = now.strftime("%Y-%m-%dT23:59:59Z")
print(f"Time range: {start}  →  {end}")
print(f"Bbox      : {PLEVEN_BBOX}")

payload = {
    "input": {
        "bounds": {
            "bbox":       PLEVEN_BBOX,
            "properties": {"crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"},
        },
        "data": [{
            "type": "sentinel-2-l2a",
            "dataFilter": {"mosaickingOrder": "leastCC"},
        }],
    },
    "aggregation": {
        "timeRange":           {"from": start, "to": end},
        "aggregationInterval": {"of": "P7D"},
        "evalscript":          EVALSCRIPT_NDVI,
        "resx": 0.01,  # 0.01° ≈ 814m at 43°N (CRS84 units = degrees)
        "resy": 0.01,
    },
    "calculations": {
        "default": {
            "statistics": {
                "default": {"percentiles": {"k": [25, 50, 75]}},
            },
        },
    },
}

print(f"Sending payload:\n{json.dumps(payload, indent=2)[:600]}...")

resp2 = requests.post(
    STATS_URL,
    json=payload,
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    timeout=60,
)
print(f"HTTP status: {resp2.status_code}")

if resp2.status_code != 200:
    print("FAILED:", resp2.text[:500])
    sys.exit(1)

data = resp2.json()
intervals = data.get("data", [])
print(f"✓ Response received — {len(intervals)} time interval(s)")

for interval in intervals:
    t_from = interval.get("interval", {}).get("from", "?")
    t_to   = interval.get("interval", {}).get("to",   "?")
    ndvi_stats = (
        interval.get("outputs", {})
                .get("ndvi", {})
                .get("bands", {})
                .get("B0", {})
                .get("stats", {})
    )
    mean         = ndvi_stats.get("mean")
    sample_count = ndvi_stats.get("sampleCount", 0)
    no_data      = ndvi_stats.get("noDataCount", 0)
    p50          = ndvi_stats.get("percentiles", {}).get("50.0")
    valid_pct    = round((sample_count - no_data) / sample_count * 100, 1) if sample_count else 0

    status = "✓" if mean and mean == mean else "✗ (all NaN/cloud)"  # NaN != NaN
    print(f"\n  [{t_from[:10]} → {t_to[:10]}]")
    print(f"    NDVI mean   : {mean}")
    print(f"    NDVI median : {p50}")
    print(f"    Valid pixels: {sample_count - no_data} / {sample_count}  ({valid_pct}%)")
    print(f"    Status      : {status}")

separator("ALL TESTS PASSED")
