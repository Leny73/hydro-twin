#!/usr/bin/env python
"""
collect_flood_labels_gfm_stac.py
================================

Collect binary / 3-tier observed flood labels for AOIs using Copernicus GFM via STAC.

Input AOI JSON:
{
  "pleven_small": [24.5858, 43.3954, 24.6475, 43.4404],
  "pleven_levski": [24.55, 43.35, 25.15, 43.65],
  "danube_belene_svishtov": [25.05, 43.55, 25.45, 43.8]
}

Output CSV:
  aoi_name,date_start,date_end,gfm_items,gfm_items_used,
  gfm_flooded_area_km2,gfm_flood_fraction,
  flood_label_binary,flood_label_3tier,source

Install:
  pip install pystac-client requests pandas numpy rasterio shapely pyproj

Example:
  python collect_flood_labels_gfm_stac.py ^
    --aois data/aois.json ^
    --start 2023-04-01 ^
    --end 2026-04-26 ^
    --out data/labels/flood_gfm_stac_labels.csv

Notes:
  - Uses EODC STAC API by default: https://stac.eodc.eu/api/v1
  - Auto-discovers likely GFM collections and flood GeoTIFF/COG assets.
  - If auto-discovery picks the wrong collection, run with --list-collections,
    then pass --collection <collection_id>.
  - Flood pixels are assumed to be value 1 for observed flood extent.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import rasterio
import requests
from pyproj import Geod
from rasterio.mask import mask
from shapely.geometry import box, mapping
from pystac_client import Client


DEFAULT_STAC_URL = "https://stac.eodc.eu/api/v1"

COLLECTION_KEYWORDS = [
    "gfm",
    "global flood monitoring",
    "global-flood-monitoring",
    "observed flood",
    "flood monitoring",
]

ASSET_KEYWORDS = [
    "observed_flood_extent",
    "observed-flood-extent",
    "flood_extent",
    "flood-extent",
    "flood",
    "cog",
    "geotiff",
    "tif",
]


def load_aois(path: str) -> dict[str, list[float]]:


    with open(path, "r", encoding="utf-8") as f:
        aois = json.load(f)
    for name, bbox in aois.items():
        if not isinstance(bbox, list) or len(bbox) != 4:
            raise ValueError(f"{name}: expected [lon_min, lat_min, lon_max, lat_max]")
    return aois


def make_windows(start: str, end: str, window_days: int) -> list[tuple[str, str]]:
    s = datetime.strptime(start, "%Y-%m-%d")
    e = datetime.strptime(end, "%Y-%m-%d")
    windows = []
    cur = s
    while cur <= e:
        win_end = min(cur + timedelta(days=window_days - 1), e)
        windows.append((cur.strftime("%Y-%m-%d"), win_end.strftime("%Y-%m-%d")))
        cur = win_end + timedelta(days=1)
    return windows


def list_candidate_collections(stac_url: str) -> list[str]:
    catalog = Client.open(stac_url)
    matches = []
    for col in catalog.get_collections():
        text = " ".join([
            col.id,
            getattr(col, "title", "") or "",
            getattr(col, "description", "") or "",
        ]).lower()
        if any(k in text for k in COLLECTION_KEYWORDS):
            matches.append(col.id)
    return matches


def choose_collection(stac_url: str, explicit: str | None) -> str:
    if explicit:
        return explicit
    matches = list_candidate_collections(stac_url)
    if not matches:
        raise RuntimeError(
            "No likely GFM collection found. Run --list-collections or inspect "
            "https://stac.eodc.eu/api/v1/collections and pass --collection manually."
        )
    print(f"Auto-selected collection: {matches[0]}")
    if len(matches) > 1:
        print(f"Other candidate collections: {matches[1:]}")
    return matches[0]

def process_downloaded_flood_tiff_to_row(
    *,
    path: Path,
    aoi_name: str,
    bbox: list[float],
    date_start: str,
    date_end: str,
    item_id: str,
    asset_key: str,
    flood_value: int = 1,
    binary_threshold_km2: float = 0.5,
    tier_minor_km2: float = 0.5,
    tier_significant_km2: float = 5.0,
    source: str = "GFM_STAC",
) -> dict[str, Any]:
    """
    Open downloaded GFM GeoTIFF, clip to AOI, detect flood pixels,
    calculate flood area, and return one dataframe-ready row.
    """

    
    stats = flood_stats(path, bbox, flood_value=flood_value)
    area = stats["gfm_flooded_area_km2"]
    fraction = stats["gfm_flood_fraction"]

    return {
        "aoi_name": aoi_name,
        "date_start": date_start,
        "date_end": date_end,
        "target_date": date_end,
        "item_id": item_id,
        "asset_key": asset_key,
        "valid_pixels": stats["valid_pixels"],
        "flood_pixels": stats["flood_pixels"],
        "aoi_area_km2": stats["aoi_area_km2"],
        "gfm_flooded_area_km2": area,
        "gfm_flood_fraction": fraction,
        "flood_detected": int(area >= binary_threshold_km2),
        "flood_label_binary": label_binary(area, binary_threshold_km2),
        "flood_label_3tier": label_3tier(area, tier_minor_km2, tier_significant_km2),
        "binary_threshold_km2": binary_threshold_km2,
        "tier_minor_km2": tier_minor_km2,
        "tier_significant_km2": tier_significant_km2,
        "source": source,
    }


def search_items(
    stac_url: str,
    collection: str,
    bbox: list[float],
    date_start: str,
    date_end: str,
    max_items: int,
) -> list[Any]:
    catalog = Client.open(stac_url)
    search = catalog.search(
        collections=[collection],
        bbox=bbox,
        datetime=f"{date_start}T00:00:00Z/{date_end}T23:59:59Z",
        max_items=max_items,
    )
    return list(search.items())


def choose_asset(item: Any, explicit_asset: str | None = None) -> tuple[str, str]:
    assets = item.assets or {}
    if not assets:
        raise ValueError(f"Item {item.id} has no assets")

    if explicit_asset:
        if explicit_asset not in assets:
            raise KeyError(f"Asset {explicit_asset!r} not found. Available: {list(assets.keys())}")
        return explicit_asset, assets[explicit_asset].href

    scored = []
    for key, asset in assets.items():
        href = asset.href or ""
        title = getattr(asset, "title", "") or ""
        desc = getattr(asset, "description", "") or ""
        media = getattr(asset, "media_type", "") or ""
        text = f"{key} {href} {title} {desc} {media}".lower()
        score = sum(1 for kw in ASSET_KEYWORDS if kw in text)
        if href.lower().endswith((".tif", ".tiff")):
            score += 5
        if "geotiff" in media.lower() or "cog" in media.lower():
            score += 5
        scored.append((score, key, href))

    scored.sort(reverse=True)
    if not scored or scored[0][0] <= 0:
        raise ValueError(f"Could not identify flood raster asset. Available assets: {list(assets.keys())}")
    return scored[0][1], scored[0][2]


def maybe_download(href: str, dst: Path) -> Path:
    if href.startswith("http://") or href.startswith("https://"):
        headers = {}
        token = os.environ.get("GFM_BEARER_TOKEN") or os.environ.get("EODC_BEARER_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        with requests.get(href, headers=headers, stream=True, timeout=180) as r:
            r.raise_for_status()
            with open(dst, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)
        return dst
    return Path(href)


def bbox_area_km2(bbox: list[float]) -> float:
    lon_min, lat_min, lon_max, lat_max = bbox
    geod = Geod(ellps="WGS84")
    lons = [lon_min, lon_max, lon_max, lon_min, lon_min]
    lats = [lat_min, lat_min, lat_max, lat_max, lat_min]
    area_m2, _ = geod.polygon_area_perimeter(lons, lats)
    return abs(area_m2) / 1_000_000.0


def pixel_area_km2(src: rasterio.DatasetReader) -> float:
    t = src.transform
    if src.crs and src.crs.is_projected:
        return abs(t.a * t.e) / 1_000_000.0

    bounds = src.bounds
    lat = (bounds.top + bounds.bottom) / 2
    lon0 = bounds.left
    lon1 = lon0 + abs(t.a)
    lat0 = lat
    lat1 = lat + abs(t.e)
    geod = Geod(ellps="WGS84")
    lons = [lon0, lon1, lon1, lon0, lon0]
    lats = [lat0, lat0, lat1, lat1, lat0]
    area_m2, _ = geod.polygon_area_perimeter(lons, lats)
    return abs(area_m2) / 1_000_000.0


from rasterio.warp import transform_geom
from rasterio.errors import WindowError


def flood_stats(asset_path: Path, bbox: list[float], flood_value: int = 1) -> dict[str, Any]:
    geom_4326 = mapping(box(*bbox))

    with rasterio.open(asset_path) as src:
        # Convert AOI bbox from EPSG:4326 into raster CRS
        if src.crs and str(src.crs).upper() not in ["EPSG:4326", "OGC:CRS84"]:
            geom = transform_geom("EPSG:4326", src.crs, geom_4326)
        else:
            geom = geom_4326

        try:
            arr, _ = mask(src, [geom], crop=True, filled=True)
        except ValueError:
            # Real non-overlap after CRS transform
            return {
                "valid_pixels": 0,
                "flood_pixels": 0,
                "gfm_flooded_area_km2": 0.0,
                "gfm_flood_fraction": 0.0,
                "aoi_area_km2": round(bbox_area_km2(bbox), 4),
                "overlap": 0,
                "raster_crs": str(src.crs),
            }

        data = arr[0]

        valid = np.isfinite(data)
        if src.nodata is not None:
            valid &= data != src.nodata

        valid &= data != 255

        flooded = valid & (data == flood_value)

        valid_pixels = int(valid.sum())
        flood_pixels = int(flooded.sum())
        area = flood_pixels * pixel_area_km2(src)

    aoi_area = bbox_area_km2(bbox)

    return {
        "valid_pixels": valid_pixels,
        "flood_pixels": flood_pixels,
        "gfm_flooded_area_km2": round(float(area), 4),
        "gfm_flood_fraction": round(float(area / aoi_area), 6) if aoi_area > 0 else None,
        "aoi_area_km2": round(aoi_area, 4),
        "overlap": int(valid_pixels > 0),
        "raster_crs": str(src.crs),
    }


def label_binary(area_km2: float, threshold_km2: float) -> int:
    return int(area_km2 >= threshold_km2)


def label_3tier(area_km2: float, minor_km2: float, significant_km2: float) -> int:
    if area_km2 < minor_km2:
        return 0
    if area_km2 < significant_km2:
        return 1
    return 2


def collect_labels(args: argparse.Namespace) -> pd.DataFrame:
    aois = load_aois(args.aois)
    collection = choose_collection(args.stac_url, args.collection)
    rows = []

    tmp_root = Path(args.download_dir)
    tmp_root.mkdir(parents=True, exist_ok=True)

    for aoi_name, bbox in aois.items():
        for date_start, date_end in make_windows(args.start, args.end, args.window_days):
            print(f"[flood] {aoi_name}: {date_start} → {date_end}")

            items = search_items(
                args.stac_url,
                collection,
                bbox,
                date_start,
                date_end,
                args.max_items,
            )

            item_rows = []
            items_used = 0
            asset_keys = set()
            errors = []

            for item in items:
                local = None

                try:
                    asset_key, href = choose_asset(item, args.asset)
                    asset_keys.add(asset_key)

                    safe_item_id = str(item.id).replace("/", "_").replace("\\", "_")
                    safe_asset_key = str(asset_key).replace("/", "_").replace("\\", "_")

                    local = tmp_root / f"{aoi_name}_{date_start}_{safe_item_id}_{safe_asset_key}.tif"
                    path = maybe_download(href, local)

                    row = process_downloaded_flood_tiff_to_row(
                        path=path,
                        aoi_name=aoi_name,
                        bbox=bbox,
                        date_start=date_start,
                        date_end=date_end,
                        item_id=item.id,
                        asset_key=asset_key,
                        flood_value=args.flood_value,
                        binary_threshold_km2=args.binary_threshold_km2,
                        tier_minor_km2=args.tier_minor_km2,
                        tier_significant_km2=args.tier_significant_km2,
                        source=f"GFM_STAC:{collection}",
                    )

                    item_rows.append(row)
                    items_used += 1

                except Exception as exc:
                    errors.append(f"{getattr(item, 'id', 'unknown')}: {exc}")

                finally:
                    if (
                        not args.keep_downloads
                        and local is not None
                        and local.exists()
                    ):
                        try:
                            local.unlink()
                        except Exception:
                            pass

            if item_rows:
                best = max(item_rows, key=lambda r: r["gfm_flooded_area_km2"])

                rows.append({
                    **best,
                    "gfm_items": len(items),
                    "gfm_items_used": items_used,
                    "gfm_asset_keys": ",".join(sorted(asset_keys)),
                    "errors": " | ".join(errors[:3]),
                })

            else:
                rows.append({
                    "aoi_name": aoi_name,
                    "date_start": date_start,
                    "date_end": date_end,
                    "target_date": date_end,
                    "item_id": None,
                    "asset_key": None,
                    "gfm_items": len(items),
                    "gfm_items_used": 0,
                    "gfm_asset_keys": ",".join(sorted(asset_keys)),
                    "valid_pixels": 0,
                    "flood_pixels": 0,
                    "aoi_area_km2": round(bbox_area_km2(bbox), 4),
                    "gfm_flooded_area_km2": 0.0,
                    "gfm_flood_fraction": 0.0,
                    "flood_detected": 0,
                    "flood_label_binary": 0,
                    "flood_label_3tier": 0,
                    "binary_threshold_km2": args.binary_threshold_km2,
                    "tier_minor_km2": args.tier_minor_km2,
                    "tier_significant_km2": args.tier_significant_km2,
                    "source": f"GFM_STAC:{collection}",
                    "errors": " | ".join(errors[:3]),
                })

    df = pd.DataFrame(rows)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)
    return df


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--aois", required=True)
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--out", default="data/labels/flood_gfm_stac_labels.csv")
    p.add_argument("--stac-url", default=DEFAULT_STAC_URL)
    p.add_argument("--collection", default=None)
    p.add_argument("--asset", default=None)
    p.add_argument("--list-collections", action="store_true")
    p.add_argument("--window-days", type=int, default=12)
    p.add_argument("--max-items", type=int, default=100)
    p.add_argument("--flood-value", type=int, default=1)
    p.add_argument("--binary-threshold-km2", type=float, default=0.5)
    p.add_argument("--tier-minor-km2", type=float, default=0.5)
    p.add_argument("--tier-significant-km2", type=float, default=5.0)
    p.add_argument("--download-dir", default="data/raw/gfm_stac")
    p.add_argument("--keep-downloads", action="store_true")
    args = p.parse_args()

    if args.list_collections:
        print("\n".join(list_candidate_collections(args.stac_url)))
        return

    df = collect_labels(args)
    print(f"Saved {len(df)} rows → {args.out}")


if __name__ == "__main__":
    main()
