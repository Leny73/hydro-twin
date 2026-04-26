


#!/usr/bin/env python
"""
collect_drought_labels_edo_wcs.py

Download Copernicus EDO CDI drought maps via WCS,
clip to AOIs, and compute drought labels.

Outputs:
- binary label (0/1)
- 3-tier label (0/1/2)
"""
#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

import numpy as np
import pandas as pd
import rasterio
import requests
from rasterio.mask import mask
from rasterio.warp import transform_geom
from shapely.geometry import box, mapping


DEFAULT_WCS_URL = "https://drought.emergency.copernicus.eu/api/wcs"
DEFAULT_COVERAGE_ID = "cdiad"
DEFAULT_MAP = "DO_WCS"


def load_aois(path: str) -> dict[str, list[float]]:
    with open(path, "r", encoding="utf-8") as f:
        aois = json.load(f)

    for name, bbox in aois.items():
        if not isinstance(bbox, list) or len(bbox) != 4:
            raise ValueError(f"{name}: expected [lon_min, lat_min, lon_max, lat_max]")
    return aois


def next_month(dt: datetime, day: int) -> datetime:
    if dt.month == 12:
        return datetime(dt.year + 1, 1, day)
    return datetime(dt.year, dt.month + 1, day)


def month_dates(start: str, end: str, day: int = 1) -> list[str]:
    s = datetime.strptime(start, "%Y-%m-%d")
    e = datetime.strptime(end, "%Y-%m-%d")

    cur = datetime(s.year, s.month, day)
    if cur < s:
        cur = next_month(cur, day)

    out = []
    while cur <= e:
        out.append(cur.strftime("%Y-%m-%d"))
        cur = next_month(cur, day)

    return out


def build_wcs_url(date: str, args: argparse.Namespace, bbox: list[float]) -> str:
    lon_min, lat_min, lon_max, lat_max = bbox

    params = {
        "map": args.map,
        "SERVICE": "WCS",
        "VERSION": "2.0.0",
        "REQUEST": "GetCoverage",
        "coverageID": args.coverage_id,
        "CRS": "EPSG:4326",
        "format": "GEOTIFF",
        "TIME": date,
        "SUBSET": [
            f"Long({lon_min},{lon_max})",
            f"Lat({lat_min},{lat_max})",
        ],
    }

    return f"{args.wcs_url}?{urlencode(params, doseq=True)}"


def download_geotiff(url: str, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)

    with requests.get(url, stream=True, timeout=180) as r:
        r.raise_for_status()

        content_type = (r.headers.get("Content-Type") or "").lower()
        first = next(r.iter_content(1024), b"")

        if (
            len(first) == 0
            or b"ExceptionReport" in first
            or b"<?xml" in first.lower()
            or b"<html" in first.lower()
            or "xml" in content_type
            or "text" in content_type
        ):
            raise RuntimeError(
                f"WCS returned non-GeoTIFF response. "
                f"Content-Type={content_type}. First bytes={first[:200]}"
            )

        with open(path, "wb") as f:
            f.write(first)
            for chunk in r.iter_content(1024 * 1024):
                if chunk:
                    f.write(chunk)

    return path


def aoi_stats(path: Path, bbox: list[float]) -> dict | None:
    geom_4326 = mapping(box(*bbox))

    with rasterio.open(path) as src:
        if src.crs is None or src.transform.is_identity:
            raise RuntimeError(
                f"Downloaded raster is not georeferenced. "
                f"CRS={src.crs}, transform={src.transform}"
            )

        if str(src.crs).upper() not in {"EPSG:4326", "OGC:CRS84"}:
            geom = transform_geom("EPSG:4326", src.crs, geom_4326)
        else:
            geom = geom_4326

        try:
            arr, _ = mask(src, [geom], crop=True, filled=True)
        except ValueError:
            return None

        data = arr[0]

        valid = np.isfinite(data)

        if src.nodata is not None:
            valid &= data != src.nodata

        valid &= data >= 0
        valid &= data < 255

        values = data[valid].astype(int)

    if values.size == 0:
        return None

    unique, counts = np.unique(values, return_counts=True)

    majority = int(unique[np.argmax(counts)])
    max_val = int(unique.max())
    hist = {str(int(k)): int(v) for k, v in zip(unique, counts)}

    return {
        "valid_pixels": int(values.size),
        "cdi_majority": majority,
        "cdi_max": max_val,
        "cdi_mean": round(float(values.mean()), 4),
        "cdi_histogram": json.dumps(hist, sort_keys=True),
    }


def binary_label(value, threshold: int = 1) -> int:
    if value is None:
        return 0
    return int(float(value) >= threshold)


def label_3tier(value, watch: int = 1, severe: int = 3) -> int:
    if value is None or float(value) < watch:
        return 0
    if float(value) < severe:
        return 1
    return 2


def process_downloaded_drought_tiff_to_row(
    *,
    path: Path,
    aoi_name: str,
    bbox: list[float],
    date: str,
    args: argparse.Namespace,
    wcs_url: str,
) -> dict:
    stats = aoi_stats(path, bbox)

    if stats is None:
        return {
            "aoi_name": aoi_name,
            "date": date,
            "target_date": date,
            "coverage_id": args.coverage_id,
            "label_source": args.label_source,
            "valid_pixels": 0,
            "cdi_majority": None,
            "cdi_max": None,
            "cdi_mean": None,
            "cdi_histogram": "{}",
            "selected_cdi_value": None,
            "drought_detected": 0,
            "drought_label_binary": 0,
            "drought_label_3tier": 0,
            "source": f"Copernicus_EDO_WCS:{args.coverage_id}",
            "wcs_url": wcs_url,
            "errors": "no_overlap_or_no_valid_pixels",
        }

    selected = stats["cdi_majority"] if args.label_source == "majority" else stats["cdi_max"]

    return {
        "aoi_name": aoi_name,
        "date": date,
        "target_date": date,
        "coverage_id": args.coverage_id,
        "label_source": args.label_source,
        "valid_pixels": stats["valid_pixels"],
        "cdi_majority": stats["cdi_majority"],
        "cdi_max": stats["cdi_max"],
        "cdi_mean": stats["cdi_mean"],
        "cdi_histogram": stats["cdi_histogram"],
        "selected_cdi_value": selected,
        "drought_detected": binary_label(selected, args.binary_threshold),
        "drought_label_binary": binary_label(selected, args.binary_threshold),
        "drought_label_3tier": label_3tier(
            selected,
            args.tier_watch_threshold,
            args.tier_significant_threshold,
        ),
        "binary_threshold": args.binary_threshold,
        "tier_watch_threshold": args.tier_watch_threshold,
        "tier_significant_threshold": args.tier_significant_threshold,
        "source": f"Copernicus_EDO_WCS:{args.coverage_id}",
        "wcs_url": wcs_url,
        "errors": "",
    }


def error_row(
    *,
    aoi_name: str,
    date: str,
    args: argparse.Namespace,
    wcs_url: str,
    error: str,
) -> dict:
    return {
        "aoi_name": aoi_name,
        "date": date,
        "target_date": date,
        "coverage_id": args.coverage_id,
        "label_source": args.label_source,
        "valid_pixels": 0,
        "cdi_majority": None,
        "cdi_max": None,
        "cdi_mean": None,
        "cdi_histogram": "{}",
        "selected_cdi_value": None,
        "drought_detected": 0,
        "drought_label_binary": 0,
        "drought_label_3tier": 0,
        "binary_threshold": args.binary_threshold,
        "tier_watch_threshold": args.tier_watch_threshold,
        "tier_significant_threshold": args.tier_significant_threshold,
        "source": f"Copernicus_EDO_WCS:{args.coverage_id}",
        "wcs_url": wcs_url,
        "errors": error,
    }


def collect_labels(args: argparse.Namespace) -> pd.DataFrame:
    aois = load_aois(args.aois)
    rows = []

    tmp_dir = Path(args.download_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    for date in month_dates(args.start, args.end, args.day):
        print(f"[drought] {date}")

        for aoi_name, bbox in aois.items():
            wcs_url = build_wcs_url(date, args, bbox)
            safe_name = aoi_name.replace("/", "_").replace("\\", "_")
            tif_path = tmp_dir / f"{safe_name}_{args.coverage_id}_{date}.tif"

            try:
                download_geotiff(wcs_url, tif_path)

                row = process_downloaded_drought_tiff_to_row(
                    path=tif_path,
                    aoi_name=aoi_name,
                    bbox=bbox,
                    date=date,
                    args=args,
                    wcs_url=wcs_url,
                )
                rows.append(row)

            except Exception as exc:
                rows.append(
                    error_row(
                        aoi_name=aoi_name,
                        date=date,
                        args=args,
                        wcs_url=wcs_url,
                        error=str(exc),
                    )
                )

            finally:
                if not args.keep_downloads and tif_path.exists():
                    try:
                        tif_path.unlink()
                    except Exception:
                        pass

    df = pd.DataFrame(rows)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)
    return df


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument("--aois", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--out", default="data/labels/drought_edo_cdi_labels.csv")

    parser.add_argument("--wcs-url", default=DEFAULT_WCS_URL)
    parser.add_argument("--coverage-id", default=DEFAULT_COVERAGE_ID)
    parser.add_argument("--map", default=DEFAULT_MAP)

    parser.add_argument("--day", type=int, default=1)
    parser.add_argument("--label-source", choices=["majority", "max"], default="majority")

    parser.add_argument("--binary-threshold", type=int, default=1)
    parser.add_argument("--tier-watch-threshold", type=int, default=1)
    parser.add_argument("--tier-significant-threshold", type=int, default=3)

    parser.add_argument("--download-dir", default="data/raw/edo_cdi")
    parser.add_argument("--keep-downloads", action="store_true")

    args = parser.parse_args()

    df = collect_labels(args)
    print(f"Saved {len(df)} rows → {args.out}")


if __name__ == "__main__":
    main()